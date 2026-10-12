"""Structured PantheraLAB study reports with reproducible exports.

Stateless report generation. No remote media retrieval, no cloud writes.
Every sighting links an encounter; every encounter links a deployment.
"""
from __future__ import annotations

import base64
import binascii
import csv
import html
import io
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

router = APIRouter(prefix="/api/science/studies", tags=["Scientific study reports"])
MAX_BODY = 2_400_000
MAX_LENGTHS = {"deployments": 80, "individuals": 200, "encounters": 300, "sightings": 600}
ID_PATTERN = re.compile(r"^[\w.-]{1,90}$", re.UNICODE)


async def parse_payload(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BODY:
            raise HTTPException(413, "El conjunto de datos excede el limite del servicio de informes.")
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "JSON invalido.") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("study"), dict):
        raise HTTPException(422, "Se requiere un proyecto de investigacion.")
    study = payload["study"]
    if not study.get("study_id") or not study.get("title"):
        raise HTTPException(422, "Proyecto sin ID o titulo.")
    for field, maximum in MAX_LENGTHS.items():
        rows = payload.get(field)
        if not isinstance(rows, list) or len(rows) > maximum or any(not isinstance(v, dict) for v in rows):
            raise HTTPException(422, "Cantidad o formato invalido de " + field)
    if not isinstance(payload.get("redact_coordinates", True), bool):
        raise HTTPException(422, "La opcion de privacidad debe ser booleana.")
    if payload.get("language", "es") not in ("es", "en"):
        raise HTTPException(422, "Idioma invalido.")
    study_id = study["study_id"]
    indexes = {}
    for key, id_key in [("deployments", "deployment_id"), ("individuals", "individual_id"),
                        ("encounters", "encounter_id"), ("sightings", "sighting_id")]:
        ids = [item.get(id_key) for item in payload[key]]
        if any(not isinstance(v, str) or not ID_PATTERN.fullmatch(v) for v in ids) or len(set(ids)) != len(ids):
            raise HTTPException(422, "Identificadores duplicados o invalidos en " + key)
        indexes[key] = set(ids)
    for key in ("deployments", "individuals", "encounters"):
        if any(row.get("study_id") != study_id for row in payload[key]):
            raise HTTPException(422, "Relaciones de proyecto inconsistentes.")
    if any(e.get("deployment_id") not in indexes["deployments"] for e in payload["encounters"]):
        raise HTTPException(422, "Evento vinculado a estacion inexistente.")
    if any(s.get("encounter_id") not in indexes["encounters"] for s in payload["sightings"]):
        raise HTTPException(422, "Observacion vinculada a evento inexistente.")
    if any(s.get("individual_id") and s.get("individual_id") not in indexes["individuals"]
           for s in payload["sightings"]):
        raise HTTPException(422, "Observacion vinculada a individuo inexistente.")
    return payload


def evidence_jpeg(event):
    """Validate compact JPEG thumbnail data; never fetch external URLs."""
    text = event.get("thumbnail_data_url")
    if not text:
        return None
    if not isinstance(text, str) or len(text) > 75_000 or not text.startswith("data:image/jpeg;base64,"):
        raise ValueError("Miniatura invalida o demasiado grande.")
    try:
        raw = base64.b64decode(text.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Miniatura con formato base64 invalido.") from exc
    if len(raw) > 55_000 or not raw.startswith(b"\xff\xd8\xff"):
        raise ValueError("Miniatura JPEG invalida.")
    from PIL import Image as PillowImage, UnidentifiedImageError
    try:
        with PillowImage.open(io.BytesIO(raw)) as check:
            if check.format != "JPEG" or check.width > 640 or check.height > 640 or check.width < 1 or check.height < 1:
                raise ValueError("Dimensiones de imagen no permitidas.")
            check.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Miniatura dañada.") from exc
    return raw


def flatten(data, private=False):
    # The redacted dataset cannot be reverse-geolocated from station coordinate fields.
    p = json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))
    if private:
        for station in p["deployments"]:
            for k in ("latitude", "longitude"):
                station[k] = None
    return p


def table_rows(p):
    study = p["study"]
    stations = {x["deployment_id"]: x for x in p["deployments"]}
    events = {x["encounter_id"]: x for x in p["encounters"]}
    ids = {x["individual_id"]: x for x in p["individuals"]}
    output = []
    for s in p["sightings"]:
        e = events[s["encounter_id"]]
        d = stations[e["deployment_id"]]
        candidate = ids.get(s.get("individual_id") or "", {})
        output.append({
            "study_id": study["study_id"], "study_title": study["title"],
            "event_id": e["encounter_id"], "timestamp": e.get("occurred_at", ""),
            "camera_id": d.get("camera_id", ""), "station_id": d["deployment_id"],
            "site": d.get("site", ""), "latitude": d.get("latitude"), "longitude": d.get("longitude"),
            "sighting_id": s["sighting_id"], "species": s.get("species", ""),
            "individual_id": s.get("individual_id") or "", "individual_status": candidate.get("status", ""),
            "identification": s.get("identification_status", ""),
            "sex": s.get("sex", ""), "age_class": s.get("age_class", ""),
            "behavior": s.get("behavior", ""), "viewpoint": s.get("viewpoint", ""),
            "reviewer": s.get("reviewer", ""),
            "temperature_c": e.get("temperature_c"),
            "humidity_percent": e.get("humidity_percent"),
            "environment_source": e.get("environment_source", ""),
            "image_url": e.get("image_url", ""), "video_url": e.get("video_url", ""),
            "edge_event_id": e.get("edge_event_id", ""),
        })
    return output


def csv_bytes(rows):
    buffer = io.StringIO(newline="")
    if rows:
        keys = list(rows[0])
        writer = csv.DictWriter(buffer, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for item in rows:
            # Avoid formula execution in spreadsheet applications.
            writer.writerow({k: "'"+v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                             else v for k, v in item.items()})
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def pdf_document(p):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, Image as ReportImage

    lang = p.get("language", "es")
    english = lang == "en"
    def tr(es, en):
        return en if english else es
    def safe(value, maximum=650):
        if value is None or value == "":
            return tr("No registrado", "Not recorded")
        return html.escape(str(value)[:maximum], quote=True).replace("\n", "<br/>")
    def para(value, style, maxlen=650):
        return Paragraph(safe(value, maxlen), style)
    def number(value):
        return str(value) if value is not None else "—"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="PantheraSmall", parent=styles["Normal"], fontSize=8.3, leading=12,
                              spaceAfter=3, textColor=colors.HexColor("#243344")))
    styles.add(ParagraphStyle(name="PantheraMicro", parent=styles["Normal"], fontSize=7, leading=10,
                              spaceAfter=2))
    styles["Title"].textColor = colors.HexColor("#0d5263")
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=A4, leftMargin=1.6*cm, rightMargin=1.6*cm,
                            topMargin=1.6*cm, bottomMargin=1.6*cm)
    story = []
    study = p["study"]
    deps = {d["deployment_id"]: d for d in p["deployments"]}
    events = {e["encounter_id"]: e for e in p["encounters"]}
    indiv = {i["individual_id"]: i for i in p["individuals"]}
    per_individual = defaultdict(list)
    for sight in p["sightings"]:
        if sight.get("individual_id"):
            per_individual[sight["individual_id"]].append(sight)
    validated = {s["individual_id"] for s in p["sightings"]
                 if s.get("individual_id") in indiv and s.get("identification_status") == "verified"
                 and indiv[s["individual_id"]].get("status") == "verified"}
    counts = (len(p["deployments"]), len(p["encounters"]), len(p["sightings"]), len(validated))
    scope = p.get("report_scope", "study")
    document_name = {
        "study": tr("Informe científico integral", "Consolidated scientific report"),
        "individual": tr("Ficha longitudinal de individuo", "Individual longitudinal profile"),
        "encounter": tr("Informe de evento de captura", "Capture-event report"),
    }.get(scope, tr("Informe científico integral", "Consolidated scientific report"))
    story.extend([Paragraph("PANTHERA LAB", styles["Title"]),
                  Paragraph(document_name, styles["Heading1"]),
                  para(study.get("title", ""), styles["Heading2"]),
                  para(tr("Proyecto", "Project") + ": " + study.get("study_id", ""), styles["PantheraSmall"]),
                  para(tr("Responsable", "Lead researcher") + ": " + str(study.get("lead", "")), styles["PantheraSmall"]),
                  para(tr("Institución", "Organization") + ": " + str(study.get("organization", "")), styles["PantheraSmall"]),
                  para(tr("Generado (UTC)", "Generated (UTC)") + ": " + datetime.now(timezone.utc).isoformat(),
                       styles["PantheraSmall"]),
                  Spacer(1, .45*cm)])
    story.append(Paragraph(tr("Resumen del proyecto", "Project summary"), styles["Heading2"]))
    story.append(para(study.get("objectives", ""), styles["PantheraSmall"], 2500))
    story.append(Paragraph(tr("Diseño metodológico", "Sampling methodology"), styles["Heading2"]))
    story.append(para(study.get("methodology", ""), styles["PantheraSmall"], 2500))
    story.append(para(tr("Periodo", "Study period") + ": " + str(study.get("start_date", "")) +
                      " — " + str(study.get("end_date", "")), styles["PantheraSmall"]))
    story.append(Paragraph(tr("Indicadores descriptivos", "Descriptive indicators"), styles["Heading2"]))
    story.append(para(tr("Estaciones", "Deployments") + ": %d   |   " % counts[0] +
                      tr("Eventos de captura", "Capture events") + ": %d   |   " % counts[1] +
                      tr("Observaciones de animales", "Animal observations") + ": %d   |   " % counts[2] +
                      tr("Individuos con identidad validada", "Verified individual identities") + ": %d" % counts[3],
                      styles["PantheraSmall"]))
    effort = [d.get("operational_days") for d in p["deployments"]]
    if effort and all(isinstance(v, (int,float)) and math.isfinite(v) and v >= 0 for v in effort):
        story.append(para(tr("Esfuerzo declarado (días-cámara)", "Reported camera-days") +
                          ": " + str(sum(effort)), styles["PantheraSmall"]))
    else:
        story.append(para(tr("Esfuerzo de muestreo: no completo. No se ha estimado densidad poblacional.",
                             "Sampling effort: incomplete. No population density estimate was made."),
                          styles["PantheraSmall"]))
    story.append(Paragraph(tr("Estaciones y despliegues", "Camera deployments"), styles["Heading2"]))
    for d in p["deployments"]:
        statement = "%s / %s · %s · %s → %s · %s" % (d.get("camera_id", ""),
            d["deployment_id"], d.get("site",""), d.get("deployed_at","—"),
            d.get("retrieved_at","—"),
            tr("Coordenadas omitidas", "Coordinates withheld") if p.get("redact_coordinates", True) else
                "%s, %s" % (number(d.get("latitude")), number(d.get("longitude"))))
        story.append(para(statement, styles["PantheraSmall"], 500))
        story.append(para(tr("Altitud (m)", "Altitude (m)") + ": "+number(d.get("altitude_m"))+
                          " · " + tr("Días operativos declarados", "Declared operational days") +
                          ": "+number(d.get("operational_days"))+
                          " · "+tr("Notas de estación","Station notes")+": "+str(d.get("notes","")),
                          styles["PantheraMicro"],1000))
    story.append(Paragraph(tr("Catálogo de individuos", "Individual catalogue"), styles["Heading2"]))
    if not indiv:
        story.append(para(tr("No se han registrado individuos.", "No individuals recorded."), styles["PantheraSmall"]))
    for person in p["individuals"]:
        person_id = person["individual_id"]
        sightings = per_individual[person_id]
        event_count = len(set(s["encounter_id"] for s in sightings))
        story.append(para(person_id+" · "+str(person.get("species",""))+
             " · "+tr("Estado", "Status")+": "+str(person.get("status", ""))+
             " · "+tr("Encuentros asociados","Linked encounters")+": "+str(event_count),
             styles["PantheraSmall"]))
        story.append(para(tr("Sexo", "Sex")+": "+str(person.get("sex", ""))+
                          " · "+tr("Rasgos", "Distinguishing features")+": "+
                          str(person.get("marks", "")), styles["PantheraMicro"], 800))
        story.append(para(tr("Responsable de validación", "Validated by")+": "+
                          str(person.get("validated_by", ""))+
                          " · "+tr("Imagen de referencia","Reference image")+": "+
                          str(person.get("reference_image_url", ""))+
                          " · "+tr("Notas de identificación","Identity notes")+": "+
                          str(person.get("notes","")), styles["PantheraMicro"], 1100))
        for sight in sorted(sightings, key=lambda s: events[s["encounter_id"]].get("occurred_at", "")):
            e = events[sight["encounter_id"]]
            d = deps[e["deployment_id"]]
            story.append(para("• "+str(e.get("occurred_at", ""))+" · "+str(d.get("camera_id", ""))+
                  " · "+str(sight.get("behavior", ""))+" · "+
                  str(sight.get("identification_status", "")), styles["PantheraMicro"]))
    story.append(Paragraph(tr("Eventos de captura y observaciones", "Capture events and observations"),
                            styles["Heading2"]))
    for e in sorted(p["encounters"],key=lambda row: row.get("occurred_at","")):
        d = deps[e["deployment_id"]]
        title = str(e["encounter_id"])+"  ·  "+str(e.get("occurred_at", ""))+"  ·  "+str(d.get("camera_id", ""))
        story.append(para(title, styles["Heading3"]))
        story.append(para(tr("Observador", "Observer")+": "+str(e.get("observer",""))+" · "+
                          tr("Temperatura", "Temperature")+": "+number(e.get("temperature_c"))+" °C · "+
                          tr("Humedad", "Humidity")+": "+number(e.get("humidity_percent"))+"% · "+
                          tr("Fuente ambiental", "Environmental data source")+": "+
                          str(e.get("environment_source", "")), styles["PantheraSmall"]))
        story.append(para(tr("Notas", "Field notes")+": "+str(e.get("notes", "")), styles["PantheraSmall"], 1000))
        thumb = evidence_jpeg(e)
        if thumb:
            from PIL import Image as PillowImage
            with PillowImage.open(io.BytesIO(thumb)) as image:
                w, h = image.size
            scale = min(1.0, 7.5*cm/w, 5.5*cm/h)
            story.append(ReportImage(io.BytesIO(thumb), width=w*scale, height=h*scale))
            story.append(para(tr("Miniatura de referencia; conservar original por separado.",
                                 "Reference thumbnail; archive original separately."), styles["PantheraMicro"]))
        story.append(para(tr("Evidencia visual (referencias de archivos externos)",
                             "Visual evidence (external file references)")+": "+
                          " | ".join(v for v in [str(e.get("image_url","")),str(e.get("video_url",""))] if v),
                          styles["PantheraMicro"], 1100))
        related = [s for s in p["sightings"] if s["encounter_id"] == e["encounter_id"]]
        if not related:
            story.append(para(tr("No hay observaciones asociadas.", "No linked animal observations."),
                              styles["PantheraSmall"]))
        for s in related:
            story.append(para("• "+str(s.get("species", ""))+" · "+tr("Individuo","Individual")+
                 ": "+str(s.get("individual_id") or tr("Sin identificar","Unidentified"))+
                 " · "+tr("Identificación", "Identification")+": "+str(s.get("identification_status",""))+
                 " · "+tr("Sexo", "Sex")+": "+str(s.get("sex",""))+
                 " · "+tr("Edad estimada", "Estimated age")+": "+str(s.get("age_class",""))+
                 " · "+tr("Orientación", "Viewpoint")+": "+str(s.get("viewpoint",""))+
                 " · "+tr("Conducta", "Behavior")+": "+str(s.get("behavior", ""))+
                 " · "+tr("Revisión", "Review")+": "+str(s.get("reviewer", ""))+
                 " · "+tr("Notas", "Notes")+": "+str(s.get("notes", "")),
                 styles["PantheraSmall"], 1750))
    story.append(Paragraph(tr("Límites e interpretación", "Methodological limitations"),styles["Heading2"]))
    story.append(para(tr(
        "Los registros provienen de anotaciones humanas. Una identidad individual requiere revisión de evidencias; "
        "varias fotografías no equivalen a varios individuos. Los eventos tampoco implican independencia "
        "estadística. La cantidad de encuentros no determina abundancia o densidad poblacional. "
        "OpenCV examina cambios visuales, no especies. Coordenadas y evidencia sensible requieren controles de acceso.",
        "Entries are human annotations. Individual identity requires evidence review; multiple photographs "
        "do not imply multiple animals. Events are not automatically statistically independent. Encounter "
        "counts do not determine population size or density. OpenCV detects visual changes, not species. "
        "Sensitive coordinates and evidence require access controls."), styles["PantheraSmall"], 1900))
    doc.build(story)
    return buff.getvalue()


def build_output(p, kind):
    private = p.get("redact_coordinates", True)
    data = flatten(p, private)
    pdf = pdf_document(data)
    if kind == "pdf":
        return pdf, "application/pdf", "PantheraLAB_informe_integral.pdf"
    # The archive includes compact reference thumbnails, not original media.
    image_files = {}
    for e in data["encounters"]:
        image = evidence_jpeg(e)
        if image:
            path = "reference_thumbnails/" + e["encounter_id"] + ".jpg"
            image_files[path] = image
            e["thumbnail_filename"] = path
        e.pop("thumbnail_data_url", None)
    stations = data["deployments"]
    geo = {"type":"FeatureCollection", "features": [
        {"type":"Feature",
         "geometry": {"type":"Point","coordinates":[d["longitude"], d["latitude"]]}
            if d.get("longitude") is not None and d.get("latitude") is not None else None,
         "properties": {k: v for k,v in d.items() if k not in ("latitude", "longitude")}}
        for d in stations]}
    manifest = {
        "format":"PantheraLAB v1 study export (NOT Camtrap DP certified)",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "coordinate_privacy":"redacted" if private else "precise_coordinates_included",
        "evidence":"uploaded JPEG reference thumbnails included when supplied; original media only cited by URL",
        "scientific_notes":"Descriptive counts only. Human-reviewed identities. No population estimate.",
    }
    files = {
        "PantheraLAB_informe_integral.pdf": pdf,
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        "study.json": json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"),
        "deployments.csv": csv_bytes(stations),
        "individuals.csv": csv_bytes(data["individuals"]),
        "encounters.csv": csv_bytes(data["encounters"]),
        "sightings.csv": csv_bytes(data["sightings"]),
        "observations_flat.csv": csv_bytes(table_rows(data)),
        "stations.geojson": json.dumps(geo, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        "LEEME.txt": ("PantheraLAB: estudio exportado. Coordenadas "+
            ("omitidas" if private else "incluidas bajo responsabilidad del investigador")+
            ". Las miniaturas JPEG cargadas se incluyen; los videos y fotografias originales se referencian por URL.\n").encode("utf-8")
    }
    files.update(image_files)
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, body in files.items():
            archive.writestr(path, body)
    return result.getvalue(), "application/zip", "PantheraLAB_datos_estudio.zip"


def scope_report(data, individual_id=None, encounter_id=None):
    """Create a self-contained, consistent subset for an animal or a capture."""
    if individual_id and encounter_id:
        raise HTTPException(422, "Seleccione un solo tipo de informe.")
    if not individual_id and not encounter_id:
        return data, "PantheraLAB_informe_integral.pdf"
    p = dict(data)
    if individual_id:
        target = next((i for i in p["individuals"] if i["individual_id"] == individual_id), None)
        if target is None:
            raise HTTPException(422, "El individuo solicitado no pertenece al proyecto.")
        p["individuals"] = [target]
        p["sightings"] = [x for x in p["sightings"] if x.get("individual_id") == individual_id]
        event_ids = {x["encounter_id"] for x in p["sightings"]}
        p["encounters"] = [x for x in p["encounters"] if x["encounter_id"] in event_ids]
        p["report_scope"] = "individual"
        name = "PantheraLAB_individuo_" + individual_id + ".pdf"
    else:
        event = next((e for e in p["encounters"] if e["encounter_id"] == encounter_id), None)
        if event is None:
            raise HTTPException(422, "La captura solicitada no pertenece al proyecto.")
        p["encounters"] = [event]
        p["sightings"] = [x for x in p["sightings"] if x["encounter_id"] == encounter_id]
        individual_ids = {x["individual_id"] for x in p["sightings"] if x.get("individual_id")}
        p["individuals"] = [x for x in p["individuals"] if x["individual_id"] in individual_ids]
        p["report_scope"] = "encounter"
        name = "PantheraLAB_captura_" + encounter_id + ".pdf"
    dep_ids = {e["deployment_id"] for e in p["encounters"]}
    p["deployments"] = [d for d in p["deployments"] if d["deployment_id"] in dep_ids]
    return p, name


@router.post("/report")
async def study_report(request: Request, kind: str = Query("pdf", pattern="^(pdf|zip)$"),
                       individual_id: str | None = Query(None, pattern=r"^[\w.-]{1,90}$"),
                       encounter_id: str | None = Query(None, pattern=r"^[\w.-]{1,90}$")):
    data = await parse_payload(request)
    if kind != "pdf" and (individual_id or encounter_id):
        raise HTTPException(422, "Los paquetes ZIP se generan para el estudio completo.")
    data, pdf_name = scope_report(data, individual_id, encounter_id)
    try:
        body, mime, name = await run_in_threadpool(build_output, data, kind)
    except (ValueError, TypeError, OverflowError) as error:
        raise HTTPException(422, "No se pudo procesar el conjunto de datos.") from error
    if kind == "pdf":
        name = pdf_name
    return Response(body, media_type=mime, headers={
        "Content-Disposition": 'attachment; filename="'+name+'"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
