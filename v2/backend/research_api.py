"""PantheraEDGE scientific observation tools for the PantheraLAB mobile PWA.

Prototype contract: validation and exports are stateless. Nothing is stored in
Supabase or on the server; browser-held observations must be exported manually.
Coordinates and environment readings are never inferred from demo defaults.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

router = APIRouter(prefix="/api/research", tags=["PantheraEDGE science"])
STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"


class ScientificObservation(BaseModel):
    """Researcher-provided observations; identification is never AI-inferred."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    observation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    observation_name: str = Field(default="", max_length=160)
    observer: str = Field(default="", max_length=160)
    institution: str = Field(default="", max_length=160)
    project_code: str = Field(default="", max_length=80)
    protocol: str = Field(default="", max_length=500)
    camera_id: str = Field(default="", max_length=100)
    camera_model: str = Field(default="", max_length=150)
    study_site: str = Field(default="", max_length=200)
    deployed_at: str = Field(default="", max_length=32)
    retrieved_at: str = Field(default="", max_length=32)
    camera_trap_nights: float | None = Field(default=None, ge=0, le=100000)
    event_datetime_utc: str = Field(default="", max_length=40)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinate_provenance: Literal["sin_verificar", "gps", "estacion", "investigador"] = "sin_verificar"
    altitude_m: float | None = Field(default=None, ge=-500, le=9000)
    temperature_c: float | None = Field(default=None, ge=-60, le=70)
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    environmental_source: str = Field(default="", max_length=220)
    species: str = Field(default="", max_length=160)
    individual_id: str = Field(default="", max_length=100)
    identification_method: Literal["pendiente", "anotacion_visual", "modelo_validado", "otro"] = "pendiente"
    evidence_quality: Literal["sin_evaluar", "baja", "media", "alta"] = "sin_evaluar"
    validation_status: Literal["pendiente", "validada_investigador", "verificada_campo", "rechazada"] = "pendiente"
    sex: Literal["desconocido", "hembra", "macho", "indeterminado"] = "desconocido"
    age_class: Literal["desconocida", "juvenil", "subadulto", "adulto", "indeterminada"] = "desconocida"
    viewpoint: Literal["desconocido", "izquierdo", "derecho", "frontal", "posterior", "otro"] = "desconocido"
    behavior: str = Field(default="", max_length=300)
    habitat_type: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=3000)
    limitations: str = Field(default="", max_length=1500)
    media_reference: str = Field(default="", max_length=300)
    edge_event_id: str = Field(default="", max_length=120)
    edge_event_timestamp: str = Field(default="", max_length=60)
    edge_transport: str = Field(default="", max_length=100)
    edge_hmac_status: str = Field(default="", max_length=40)
    edge_analysis: dict | None = None

    @model_validator(mode="after")
    def check_field_evidence(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitud y longitud deben registrarse juntas, o dejarse ambas en blanco.")
        if (self.temperature_c is not None or self.humidity_percent is not None or self.altitude_m is not None) and not self.environmental_source:
            raise ValueError("Indicá la fuente de las mediciones ambientales o dejá esos valores sin completar.")
        if self.deployed_at and self.retrieved_at and self.deployed_at > self.retrieved_at:
            raise ValueError("La fecha de retiro no puede ser anterior a la instalación.")
        return self


def observation_geojson(obs: ScientificObservation) -> dict:
    properties = obs.model_dump(exclude={"latitude", "longitude"})
    properties["scientific_caveat"] = "Identificación de especie e individuo informada por investigador; MegaDetector no las determina."
    geometry = None
    if obs.latitude is not None and obs.longitude is not None:
        geometry = {"type": "Point", "coordinates": [obs.longitude, obs.latitude]}
    return {"type": "Feature", "geometry": geometry, "properties": properties}


@router.post("/validate")
def validate_observation(observation: ScientificObservation):
    return {
        "status": "validated",
        "observation": observation.model_dump(),
        "geojson": observation_geojson(observation),
        "stored": False,
        "note": "Validación de formato y rangos; no equivale a verificación científica ni guarda datos en servidor.",
    }


@router.post("/pdf")
def export_pdf(observation: ScientificObservation):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
    except ImportError as error:
        raise HTTPException(status_code=503, detail="Instalá reportlab para generar informes PDF.") from error

    labels = [
        ("ID observación", observation.observation_id),
        ("Observación", observation.observation_name),
        ("Investigador", observation.observer),
        ("Institución", observation.institution),
        ("Proyecto", observation.project_code),
        ("Protocolo", observation.protocol),
        ("Cámara", observation.camera_id),
        ("Modelo de cámara", observation.camera_model),
        ("Sitio de estudio", observation.study_site),
        ("Instalación / retiro", f"{observation.deployed_at or 'No registrado'} / {observation.retrieved_at or 'No registrado'}"),
        ("Esfuerzo (noches-cámara)", observation.camera_trap_nights),
        ("Fecha evento UTC", observation.event_datetime_utc),
        ("Latitud / longitud", f"{observation.latitude}, {observation.longitude}" if observation.latitude is not None else "No registradas"),
        ("Fuente de coordenadas", observation.coordinate_provenance),
        ("Altitud (m)", observation.altitude_m),
        ("Temperatura (°C)", observation.temperature_c),
        ("Humedad relativa (%)", observation.humidity_percent),
        ("Fuente de datos ambientales", observation.environmental_source),
        ("Especie anotada", observation.species),
        ("Individuo anotado", observation.individual_id),
        ("Método de identificación", observation.identification_method),
        ("Calidad de evidencia", observation.evidence_quality),
        ("Estado de validación", observation.validation_status),
        ("Sexo / edad / perspectiva", f"{observation.sex} / {observation.age_class} / {observation.viewpoint}"),
        ("Comportamiento", observation.behavior),
        ("Hábitat", observation.habitat_type),
        ("Referencia multimedia", observation.media_reference),
        ("Evento PantheraEDGE", observation.edge_event_id),
        ("Hora del evento Edge", observation.edge_event_timestamp),
        ("Transporte Edge", observation.edge_transport),
        ("Verificación HMAC", observation.edge_hmac_status),
        ("Limitaciones y sesgos", observation.limitations),
        ("Notas de campo", observation.notes),
    ]
    if observation.edge_analysis:
        model = observation.edge_analysis.get("model", "No indicado")
        labels += [
            ("Análisis de detección", model),
            ("Fotogramas muestreados", observation.edge_analysis.get("sampled")),
            ("Fotogramas retenidos", observation.edge_analysis.get("retained")),
            ("Detecciones animales", observation.edge_analysis.get("animals")),
            ("Confianza máxima", observation.edge_analysis.get("max_confidence")),
        ]

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    paragraph = lambda value: Paragraph(escape(str(value if value not in (None, "") else "No registrado")), styles["BodyText"])
    rows = [[paragraph(name), paragraph(value)] for name, value in labels]
    table = LongTable(rows, colWidths=[5.1 * cm, 11.3 * cm], repeatRows=0, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5ce")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf2ed")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [
        Paragraph("PantheraEDGE | Informe de observación científica", styles["Title"]),
        Spacer(1, 0.4 * cm), table, Spacer(1, 0.5 * cm),
        Paragraph("Limitaciones metodológicas", styles["Heading2"]),
        Paragraph("MegaDetector detecta animales, personas y vehículos. No identifica especies ni individuos. "
                  "La confianza no equivale a precisión validada. Los metadatos son aportados por el investigador; "
                  "no se deducen medidas ambientales ni coordenadas de ejemplo. "
                  "Este informe no acredita validación externa ni transmisión a Supabase.", styles["BodyText"]),
    ]
    doc.build(story)
    return Response(content=buffer.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="PantheraEDGE_{observation.observation_id}.pdf"'})


def _stac_search(payload: dict) -> dict:
    request = URLRequest(
        STAC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "PantheraLAB-SciencePrototype/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=18) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"Catálogo Copernicus no disponible: {type(error).__name__}") from error
    return {"count": len(result.get("features", [])), "items": [
        {
            "id": item.get("id"),
            "datetime": item.get("properties", {}).get("datetime"),
            "cloud_cover": item.get("properties", {}).get("eo:cloud_cover"),
            "platform": item.get("properties", {}).get("platform"),
        }
        for item in result.get("features", [])[:10]
    ]}


@router.get("/copernicus")
def copernicus_context(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_km: float = Query(5, ge=1, le=50),
    days_back: int = Query(30, ge=5, le=90),
    max_cloud_cover: int = Query(40, ge=0, le=100),
):
    import math
    from datetime import timedelta, timezone
    # Clamp search near poles and keep the bbox within valid longitude bounds.
    lat_delta = radius_km / 111.32
    lon_delta = radius_km / (111.32 * max(abs(math.cos(math.radians(latitude))), 0.01))
    bbox = [max(-180, longitude - lon_delta), max(-90, latitude - lat_delta),
            min(180, longitude + lon_delta), min(90, latitude + lat_delta)]
    now = datetime.now(timezone.utc)
    date_range = ((now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
                  + "/" + now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    common = {"bbox": bbox, "datetime": date_range, "limit": 10}
    s1 = _stac_search({**common, "collections": ["sentinel-1-grd"]})
    s2 = _stac_search({**common, "collections": ["sentinel-2-l2a"],
                       "query": {"eo:cloud_cover": {"lte": max_cloud_cover}}})
    return {
        "sentinel_1": s1, "sentinel_2": s2, "queried_at": now.isoformat(),
        "bbox": bbox,
        "note": "Metadatos de adquisición, no mediciones locales ni índices NDVI/deforestación.",
    }
