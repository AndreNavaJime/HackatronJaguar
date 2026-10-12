"""PantheraLAB scientific modules, migrated from the original Streamlit app.py.

Public APIs deliberately expose NO unauthenticated cloud database writes or
unrestricted user-specified URL proxying. Coordinates and ecological records
are only sent when the user explicitly requests an external catalogue lookup
or PDF generation; no observations are stored on this server.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import io
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/science", tags=["PantheraMONITORING / Research"])
edge_router = APIRouter(prefix="/api/edge", tags=["PantheraEDGE"])
log = logging.getLogger("pantheralab.science")
STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"
CONTRACT_VERSION = "panthera-v1.0"
SIGNATURE_FIELDS = frozenset(("signature", "hmac", "hmac_sha256"))


class SatelliteQuery(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=5, ge=1, le=50)
    days_back: int = Field(default=30, ge=5, le=90)
    max_cloud_cover: float = Field(default=40, ge=0, le=100)


def _search_catalogue(query: SatelliteQuery):
    lat, lon = query.latitude, query.longitude
    if not all(math.isfinite(value) for value in (lat, lon, query.radius_km, query.max_cloud_cover)):
        raise HTTPException(422, "Las coordenadas y parámetros deben ser finitos.")
    dlat = query.radius_km / 111.32
    dlon = query.radius_km / (111.32 * max(math.cos(math.radians(lat)), .01))
    bbox = [max(-180, lon - dlon), max(-90, lat - dlat),
            min(180, lon + dlon), min(90, lat + dlat)]
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=query.days_back)
    date_range = start.strftime("%Y-%m-%dT%H:%M:%SZ") + "/" + now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def fetch(collection, limit_cloud=False):
        payload = {"collections": [collection], "bbox": bbox, "datetime": date_range,
                   "limit": 10, "sortby": [{"field": "properties.datetime", "direction": "desc"}]}
        if limit_cloud:
            payload["query"] = {"eo:cloud_cover": {"lte": query.max_cloud_cover}}
        request = URLRequest(STAC_URL, data=json.dumps(payload).encode("utf-8"),
                             headers={"Content-Type": "application/json",
                                      "User-Agent": "PantheraLAB-Hackatron5G/2.0"},
                             method="POST")
        try:
            with urlopen(request, timeout=18) as response:
                if response.status != 200:
                    raise ValueError("HTTP %s" % response.status)
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("Respuesta demasiado grande del catálogo")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("Formato de catálogo inesperado")
                features = data.get("features", [])
                if not isinstance(features, list):
                    raise ValueError("Lista de adquisiciones inválida")
                items = []
                for item in features[:10]:
                    props = item.get("properties", {})
                    items.append({
                        "id": str(item.get("id", ""))[:180],
                        "datetime": str(props.get("datetime", ""))[:60],
                        "platform": str(props.get("platform", props.get("constellation", "")))[:90],
                        "orbit_state": str(props.get("sat:orbit_state", ""))[:40],
                        "cloud_cover": props.get("eo:cloud_cover") if isinstance(props.get("eo:cloud_cover"), (int, float)) else None,
                        "sensor": collection,
                    })
                return items
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            log.warning("Copernicus %s query error: %s", collection, type(exc).__name__)
            raise HTTPException(502, "El catálogo Copernicus no respondió para " + collection +
                                ". Intentá otra fecha o volvé a consultar.") from exc

    s1 = fetch("sentinel-1-grd")
    s2 = fetch("sentinel-2-l2a", True)
    return {"source": "Copernicus Data Space STAC (real catalogue metadata)",
            "queried_at": now.isoformat(), "bbox": bbox,
            "sentinel_1": s1, "sentinel_2": s2,
            "disclaimer": "Metadatos de adquisición únicamente; no se calculó NDVI, deforestación ni presencia de fauna."}


@router.post("/sentinel/search")
async def search_sentinel(query: SatelliteQuery):
    return await run_in_threadpool(_search_catalogue, query)


@router.get("/capabilities")
def module_capabilities():
    return {
        "satellite_catalogue": "available_on_request",
        "scientific_reports": "pdf_json_csv_geojson",
        "observation_storage": "browser_session_only",
        "supabase": "credentials_present_but_auth_pending" if
            os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_PUBLISHABLE_KEY") else "not_configured",
        "edge_cloud_ingestion": "manual_validated_demo_only",
        "live_5g_measurements": False,
        "notes": "Sin autenticación de usuarios no habilitamos escritura pública en Supabase."
    }


async def _bounded_json(request: Request, size_limit=16000):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > size_limit:
            raise HTTPException(413, "La solicitud supera el tamaño permitido.")
    try:
        obj = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Se requiere un objeto JSON válido.") from None
    if not isinstance(obj, dict):
        raise HTTPException(422, "Se requiere un objeto JSON.")
    return obj


@edge_router.post("/validate")
async def validate_edge_event(request: Request):
    source = await _bounded_json(request, size_limit=8192)
    if "event" in source and isinstance(source["event"], dict):
        source = source["event"]
    if len(source) > 80:
        raise HTTPException(422, "Demasiados campos en el evento.")
    secret = os.getenv("PANTHERA_HMAC_SECRET", "").strip()
    supplied = next((str(source[key]).strip().lower()
                     for key in ("hmac_sha256", "hmac", "signature") if source.get(key)), None)
    if secret:
        if not supplied:
            raise HTTPException(403, "Evento rechazado: falta firma HMAC configurada.")
        if len(supplied) != 64 or any(ch not in "0123456789abcdef" for ch in supplied):
            raise HTTPException(403, "Firma HMAC inválida.")
        canonical = json.dumps({k: v for k, v in source.items() if k not in SIGNATURE_FIELDS},
                               sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               default=str).encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(403, "Firma HMAC no coincide; evento rechazado.")
        status = "VALID"
    else:
        status = "NOT_CONFIGURED"
    loc = source.get("location") if isinstance(source.get("location"), dict) else {}
    env = source.get("environment") if isinstance(source.get("environment"), dict) else {}
    det = source.get("detection") if isinstance(source.get("detection"), dict) else {}

    def pick(*values):
        return next((v for v in values if v is not None and v != ""), None)

    def finite_float(value, minimum, maximum):
        if value is None:
            return None
        try:
            number = float(value)
            return number if math.isfinite(number) and minimum <= number <= maximum else None
        except (ValueError, TypeError, OverflowError):
            return None

    normalized = {
        "contract_version": str(source.get("contract_version") or CONTRACT_VERSION)[:40],
        "event_id": str(pick(source.get("event_id"), source.get("id")) or "EDGE-UNASSIGNED")[:100],
        "timestamp": str(pick(source.get("timestamp"), source.get("created_at")) or datetime.now(timezone.utc).isoformat())[:50],
        "camera_id": str(pick(source.get("camera_id"), source.get("node_id")) or "CAMERA-UNASSIGNED")[:100],
        "event": str(pick(source.get("event_type"), source.get("event")) or "field_capture")[:80],
        "status": str(source.get("status") or "RECEIVED")[:40],
        "latitude": finite_float(pick(source.get("latitude"), loc.get("latitude")), -90, 90),
        "longitude": finite_float(pick(source.get("longitude"), loc.get("longitude")), -180, 180),
        "altitude": finite_float(pick(source.get("altitude"), loc.get("altitude")), -500, 9000),
        "temperature": finite_float(pick(source.get("temperature"), env.get("temperature")), -80, 85),
        "humidity": finite_float(pick(source.get("humidity"), env.get("humidity")), 0, 100),
        "class": str(pick(source.get("class"), det.get("class"), det.get("label")) or "")[:100],
        "confidence": finite_float(pick(source.get("confidence"), det.get("confidence")), 0, 1),
        "image_url": str(pick(source.get("image_url"), source.get("image")) or "")[:1024],
        "clip_url": str(pick(source.get("clip_url"), source.get("video_url")) or "")[:1024],
        "transport": str(pick(source.get("transport"), source.get("link")) or "HTTP demo")[:100],
        "hmac_status": status,
        "source": "external_event_validated" if status == "VALID" else "demo_unverified",
    }
    return {"accepted": True, "verification": status, "saved": False,
            "event": normalized, "note": "Evento normalizado sin almacenamiento en el servidor."}


@router.post("/reports/observation")
async def observation_pdf(request: Request):
    record = await _bounded_json(request, size_limit=12000)

    def safe(key, maxlen=220):
        value = record.get(key)
        if value is None or value == "":
            return "No proporcionado"
        return html.escape(str(value)[:maxlen], quote=True)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.6*cm, bottomMargin=1.6*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallScience", parent=styles["Normal"], fontSize=8.2, leading=12))
    story = [Paragraph("PANTHERA LAB | PantheraMONITORING", styles["Title"]),
             Paragraph("Registro científico de observación", styles["Heading2"]),
             Paragraph("Datos introducidos por la persona investigadora; no implican identificación automática.",
                       styles["SmallScience"]), Spacer(1, .4*cm)]
    fields = [
        ("Identificador", "observation_id"), ("Observación", "observation_name"),
        ("Cámara / estación", "camera_id"), ("Sitio", "study_site"),
        ("Observador", "observer"), ("Fecha UTC del evento", "event_datetime_utc"),
        ("Latitud WGS84", "camera_latitude"), ("Longitud WGS84", "camera_longitude"),
        ("Altitud (m)", "altitude_m"), ("Temperatura (C)", "temperature_c"),
        ("Humedad (%)", "humidity_percent"), ("Especie (anotación)", "species"),
        ("ID individual (manual)", "individual_id"), ("Sexo", "sex"),
        ("Clase de edad", "age_class"), ("Ángulo", "viewpoint"),
        ("Comportamiento", "behavior"), ("Estado de validación", "validation_status"),
        ("Evento EDGE", "edge_event_id"), ("Imagen URL", "image_url"),
        ("Video URL", "video_url"),
    ]
    values = [[Paragraph(label, styles["SmallScience"]), Paragraph(safe(key), styles["SmallScience"])]
              for label, key in fields]
    table = Table(values, colWidths=[5.8*cm, 10.8*cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e6f2ef")),
        ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#b5c6d0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, .4*cm), Paragraph("Notas de campo", styles["Heading3"]),
              Paragraph(safe("notes", 3000), styles["SmallScience"]),
              Paragraph("Hábitat / microhábitat", styles["Heading3"]),
              Paragraph(safe("habitat_notes", 1500), styles["SmallScience"]),
              Spacer(1, .35*cm), Paragraph("Límites metodológicos", styles["Heading3"]),
              Paragraph("Especie e individuo son anotaciones humanas salvo validación independiente. "
                        "Los sensores y la conectividad no han sido verificados por este informe. "
                        "Un cambio visual en OpenCV no equivale a detección de fauna. "
                        "Las coordenadas de especies sensibles deben protegerse antes de publicar.",
                        styles["SmallScience"])]
    doc.build(story)
    return Response(buffer.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="PantheraMONITORING_informe.pdf"',
                             "Cache-Control": "no-store"})
