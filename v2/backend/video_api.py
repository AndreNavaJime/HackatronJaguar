"""Bounded, asynchronous camera-trap video analysis for PantheraID 2.0.

Each job runs in a single worker, keeps its artifacts in a temporary directory,
and expires after one hour. This development-mode service is intentionally
single-process/in-memory and MUST NOT be exposed publicly without authentication,
rate limits, persistent storage and a real queue.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from PIL import Image

from detection import DetectorUnavailable, detect_image

logger = logging.getLogger("pantheraid.video")
router = APIRouter(prefix="/api/videos", tags=["Video"])

MAX_VIDEO_BYTES = 250 * 1024 * 1024
MAX_UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
UPLOAD_TTL_SECONDS = 1800
MAX_DURATION_SECONDS = 600
MAX_FRAME_PIXELS = 3840 * 2160
MAX_SAMPLES = 24
MODEL_FRAME_MAX_SIDE = 960
JOB_TTL_SECONDS = 3600
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}

_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pantheraid-video")


class VideoError(Exception):
    """A clear, user-facing validation or decoding error."""


def _prune():
    now = time.time()
    dirs = []
    with _LOCK:
        for identifier, job in list(_JOBS.items()):
            finished = job.get("finished_at", job["created_at"])
            expired = (job["state"] in ("completed", "failed") and now - finished >= JOB_TTL_SECONDS)
            stale_upload = (job["state"] == "uploading" and now - job.get("last_upload_at", job["created_at"]) >= UPLOAD_TTL_SECONDS)
            if expired or stale_upload:
                dirs.append(job["directory"])
                del _JOBS[identifier]
    for path in dirs:
        shutil.rmtree(path, ignore_errors=True)


def _change(identifier, **updates):
    with _LOCK:
        job = _JOBS.get(identifier)
        if job:
            job.update(updates)
            if updates.get("state") in ("completed", "failed"):
                job["finished_at"] = time.time()


def _snapshot(identifier):
    _prune()
    with _LOCK:
        job = _JOBS.get(identifier)
        if job is None:
            raise HTTPException(status_code=404, detail="El análisis no existe o ya expiró.")
        return {
            "job_id": identifier,
            "state": job["state"],
            "stage": job.get("stage", ""),
            "processed": job.get("processed", 0),
            "total": job.get("total", 0),
            "error": job.get("error"),
            "result": job.get("result") if job["state"] == "completed" else None,
            "filename": job.get("filename", ""),
        }


def _jpeg_bytes(image: Image.Image, quality=84):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def _image_data_url(jpeg: bytes):
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def _write_csv(path: Path, rows):
    fieldnames = [
        "sample", "video_time_seconds", "animals", "persons", "vehicles",
        "max_animal_confidence", "edge_decision", "input_jpeg_bytes",
        "candidate_jpeg_bytes", "inference_seconds"
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_pdf(path: Path, metadata, totals, rows, example_jpeg):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as ReportImage
    )

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, topMargin=1.7 * cm, bottomMargin=1.7 * cm,
        leftMargin=1.7 * cm, rightMargin=1.7 * cm
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ScientificNote", parent=styles["Normal"], fontSize=8.3,
        leading=12, textColor=colors.HexColor("#375b48")
    ))
    story = [
        Paragraph("PANTHERALAB | PantheraID 2.0", styles["Title"]),
        Paragraph("Informe preliminar de análisis de video", styles["Heading2"]),
        Spacer(1, 0.3 * cm),
        Paragraph("Medio: " + _xml_escape(metadata["filename"]), styles["Normal"]),
        Paragraph(
            "MegaDetector V6 | " + _xml_escape(metadata["model"]) +
            " | " + _xml_escape(metadata["device"]) +
            " | umbral " + f'{metadata["threshold"]:.0%}',
            styles["Normal"]
        ),
        Spacer(1, 0.35 * cm),
    ]
    fields = [
        ["Duración de video", f'{metadata["duration_seconds"]:.2f} s'],
        ["Resolución original", f'{metadata["source_width"]} x {metadata["source_height"]} px'],
        ["FPS reportados", f'{metadata["fps"]:.2f}'],
        ["Intervalo de muestreo", f'{metadata["sample_seconds"]:.1f} s'],
        ["Fotogramas analizados", str(totals["sampled"])],
        ["Con animales / sin animales", f'{totals["retained"]} / {totals["discarded"]}'],
        ["Detecciones animales / personas / vehículos",
         f'{totals["animals"]} / {totals["persons"]} / {totals["vehicles"]}'],
        ["Confianza media animales", f'{totals["mean_confidence"]:.1%}'],
        ["Tasa de fotogramas positivos", f'{totals["positive_frame_rate"]:.1f}%'],
        ["Reducción estimada de carga JPEG", f'{totals["estimated_payload_reduction"]:.1f}%'],
    ]
    table = Table(fields, colWidths=[9 * cm, 7.5 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef5ee")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c2d5c8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
    ]))
    story += [table, Spacer(1, 0.4 * cm)]
    if example_jpeg:
        image = Image.open(io.BytesIO(example_jpeg))
        w, h = image.size
        scale = min(16.0 * cm / w, 7.0 * cm / h)
        story += [
            Paragraph("Ejemplo de fotograma anotado", styles["Heading3"]),
            ReportImage(io.BytesIO(example_jpeg), width=w * scale, height=h * scale),
            Spacer(1, 0.25 * cm),
        ]
    story += [
        Paragraph("Límites científicos y técnicos", styles["Heading3"]),
        Paragraph(
            "MegaDetector detecta animales, personas y vehículos; no identifica especies "
            "ni individuos. Las detecciones por fotograma no representan animales únicos. "
            "La confianza no es exactitud validada. El muestreo puede omitir animales "
            "entre fotogramas. La reducción de carga compara JPEG de muestras con JPEG "
            "de fotogramas retenidos; NO mide tráfico real, latencia ni ahorro 5G.",
            styles["ScientificNote"]
        ),
        Paragraph(
            "Fuente: video proporcionado por la persona usuaria. Resultados generados "
            "localmente en la simulación de PantheraEDGE; requieren revisión experta.",
            styles["ScientificNote"]
        ),
    ]
    doc.build(story)


def _xml_escape(value):
    from xml.sax.saxutils import escape
    return escape(str(value))


def _process(identifier):
    with _LOCK:
        job = _JOBS.get(identifier)
        if job is None:
            return
        source = Path(job["source"])
        folder = Path(job["directory"])
        threshold = job["threshold"]
        sample_seconds = job["sample_seconds"]
        max_samples = job["max_samples"]
        filename = job["filename"]

    try:
        import cv2
        _change(identifier, state="processing", stage="Leyendo metadatos de video…")
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise VideoError("OpenCV no pudo abrir el archivo. Verificá que el video use un códec compatible.")

        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if not math.isfinite(fps) or fps <= 0 or fps > 240:
                raise VideoError("No se pudo determinar la tasa de fotogramas (FPS) del video.")
            if frame_count <= 0 or width <= 0 or height <= 0:
                raise VideoError("El video no contiene metadatos válidos de fotogramas o resolución.")
            if width * height > MAX_FRAME_PIXELS:
                raise VideoError("La resolución supera el límite de 3840 x 2160 píxeles.")
            duration = frame_count / fps
            if duration > MAX_DURATION_SECONDS:
                raise VideoError("El video supera 10 minutos. Para el prototipo usá un fragmento más corto.")

            # Frames are selected by nominal presentation time. For variable-frame-rate
            # video the reported positions are estimates, not per-frame timestamps.
            indices = []
            candidate = 0
            while candidate < frame_count and len(indices) < max_samples:
                indices.append(candidate)
                candidate = max(candidate + 1, round(len(indices) * sample_seconds * fps))
            if not indices:
                raise VideoError("No se encontraron fotogramas para analizar.")

            _change(identifier, total=len(indices), stage="Cargando MegaDetector V6…")
            rows = []
            frames = []
            crops = []
            example_jpeg = None
            input_bytes = 0
            retained_bytes = 0
            animal_confidences = []
            totals = {"sampled": 0, "retained": 0, "discarded": 0,
                      "animals": 0, "persons": 0, "vehicles": 0}
            archive = folder / "fotogramas_y_candidatos.zip"

            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as zip_out:
                for position, frame_number in enumerate(indices, start=1):
                    _change(identifier, stage=f"Analizando fotograma {position} de {len(indices)}…")
                    if not cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number):
                        raise VideoError("El códec no permite acceder a los fotogramas solicitados.")
                    ok, frame_bgr = cap.read()
                    if not ok or frame_bgr is None:
                        raise VideoError(
                            "No se pudo decodificar el fotograma " + str(position) +
                            ". Verificá que el video no esté dañado."
                        )
                    rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(rgb_frame)
                    if max(image.size) > MODEL_FRAME_MAX_SIDE:
                        ratio = MODEL_FRAME_MAX_SIDE / max(image.size)
                        target = (max(1, round(image.width * ratio)),
                                  max(1, round(image.height * ratio)))
                        image = image.resize(target, Image.Resampling.LANCZOS)

                    sample_jpeg = _jpeg_bytes(image, quality=85)
                    input_bytes += len(sample_jpeg)
                    found = detect_image(image, threshold)
                    detections = found["detections"]
                    counts = found["counts"]
                    animal_count = counts["animal"]
                    is_retained = animal_count > 0
                    if is_retained:
                        totals["retained"] += 1
                        retained_bytes += len(sample_jpeg)
                        zip_out.writestr(f"retenidos/fotograma_{position:03d}.jpg", sample_jpeg)
                    else:
                        totals["discarded"] += 1

                    totals["animals"] += animal_count
                    totals["persons"] += counts["person"]
                    totals["vehicles"] += counts["vehicle"]
                    totals["sampled"] += 1
                    time_seconds = frame_number / fps
                    animal_scores = [
                        det["confidence"] for det in detections if det["class_name"] == "animal"
                    ]
                    animal_confidences.extend(animal_scores)
                    max_confidence = max(animal_scores, default=0.0)
                    candidate_bytes = 0

                    for detection_index, det in enumerate(detections, start=1):
                        if det["class_name"] != "animal":
                            continue
                        x1, y1, x2, y2 = det["bbox_xyxy"]
                        crop = image.crop((x1, y1, x2, y2))
                        if crop.width < 1 or crop.height < 1:
                            continue
                        jpeg = _jpeg_bytes(crop, quality=90)
                        candidate_bytes += len(jpeg)
                        candidate_name = f"candidatos/muestra_{position:03d}_animal_{detection_index:02d}.jpg"
                        zip_out.writestr(candidate_name, jpeg)
                        # Render at most 24 crops inline; ZIP contains every sampled crop.
                        if len(crops) < 24:
                            crops.append({
                                "sample": position,
                                "time_seconds": round(time_seconds, 2),
                                "confidence": det["confidence"],
                                "bbox_xyxy": det["bbox_xyxy"],
                                "image": _image_data_url(jpeg),
                                "filename": Path(candidate_name).name,
                            })

                    # detect_image supplies an annotated JPEG data URL at the same
                    # analysis resolution. Decode only when archiving/reporting.
                    import base64
                    annotated_jpeg = base64.b64decode(found["annotated_image"].split(",", 1)[1])
                    if is_retained:
                        zip_out.writestr(f"anotados/muestra_{position:03d}.jpg", annotated_jpeg)
                        if example_jpeg is None:
                            example_jpeg = annotated_jpeg
                    frames.append({
                        "sample": position,
                        "time_seconds": round(time_seconds, 2),
                        "retained": is_retained,
                        "counts": counts,
                        "max_animal_confidence": round(max_confidence, 4),
                        "inference_seconds": found["inference_seconds"],
                        "image": found["annotated_image"],
                        "detections": detections,
                    })
                    rows.append({
                        "sample": position,
                        "video_time_seconds": round(time_seconds, 2),
                        "animals": counts["animal"],
                        "persons": counts["person"],
                        "vehicles": counts["vehicle"],
                        "max_animal_confidence": round(max_confidence, 4),
                        "edge_decision": "RETAIN" if is_retained else "DISCARD",
                        "input_jpeg_bytes": len(sample_jpeg),
                        "candidate_jpeg_bytes": candidate_bytes,
                        "inference_seconds": found["inference_seconds"],
                    })
                    _change(identifier, processed=position)

                csv_path = folder / "resultados_por_fotograma.csv"
                _write_csv(csv_path, rows)
                zip_out.write(csv_path, arcname="resultados_por_fotograma.csv")

            total_input = max(1, input_bytes)
            totals.update({
                "positive_frame_rate": 100 * totals["retained"] / totals["sampled"],
                "estimated_payload_reduction": 100 * (1 - retained_bytes / total_input),
                "input_jpeg_bytes": input_bytes,
                "retained_jpeg_bytes": retained_bytes,
                "mean_confidence": sum(animal_confidences) / len(animal_confidences) if animal_confidences else 0.0,
                "max_confidence": max(animal_confidences, default=0.0),
                "animal_detection_count": len(animal_confidences),
                "mean_inference_seconds": sum(row["inference_seconds"] for row in rows) / len(rows),
            })
            metadata = {
                "filename": filename,
                "source_width": width,
                "source_height": height,
                "analysis_width": image.width,
                "analysis_height": image.height,
                "fps": round(fps, 3),
                "duration_seconds": round(duration, 2),
                "total_video_frames": frame_count,
                "sample_seconds": sample_seconds,
                "threshold": threshold,
                "model": found["model"],
                "device": found["device"].upper(),
            }
            _change(identifier, stage="Generando informe y descargas…")
            pdf_path = folder / "informe_pantheraid.pdf"
            _write_pdf(pdf_path, metadata, totals, rows, example_jpeg)
            result = {
                "metadata": metadata, "totals": totals, "rows": rows,
                "frames": frames, "candidates": crops,
                "note": (
                    "Simulación de filtrado PantheraEDGE sobre fotogramas muestreados. "
                    "RETAIN significa al menos una detección animal; no demuestra especie, "
                    "identidad individual ni presencia/ausencia entre muestras."
                ),
            }
            _change(identifier, state="completed", stage="Análisis completado",
                    result=result)
            logger.info("Video %s completado: %d muestras, %d animales",
                        identifier, totals["sampled"], totals["animals"])
        finally:
            cap.release()
    except (VideoError, DetectorUnavailable) as error:
        logger.warning("Video %s no procesado: %s", identifier, error)
        _change(identifier, state="failed", stage="Análisis interrumpido", error=str(error))
    except Exception:
        logger.exception("Error inesperado en análisis de video %s", identifier)
        _change(identifier, state="failed", stage="Análisis interrumpido",
                error="Ocurrió un error al procesar el video. Revisá la terminal de Python.")
    finally:
        source.unlink(missing_ok=True)


def _upload_name(request: Request):
    raw_name = unquote(request.headers.get("x-video-name", "camara.mp4"))
    filename = Path(raw_name.replace("\\", "/")).name[:120] or "camara.mp4"
    extension = Path(filename).suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Formato no admitido. Usá MP4, MOV, AVI o MKV.")
    return filename, extension


@router.post("/uploads", status_code=201)
async def begin_chunked_upload(
    request: Request,
    threshold: float = Query(0.25, ge=0.10, le=0.90),
    sample_seconds: float = Query(1.0, ge=0.5, le=5.0),
    max_samples: int = Query(8, ge=1, le=MAX_SAMPLES),
):
    """Reserve an upload session without transmitting the video in one big request.

    The browser subsequently PUTs sequential <=8-MiB chunks. Unlike a single
    250-MB POST, this also works through proxies with a per-request body limit.
    """
    _prune()
    filename, extension = _upload_name(request)
    try:
        expected = int(request.headers.get("x-video-size", "0"))
    except ValueError:
        raise HTTPException(status_code=400, detail="El tamaño declarado del video no es válido.")
    if expected <= 0:
        raise HTTPException(status_code=400, detail="El video está vacío o no se indicó su tamaño.")
    if expected > MAX_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail="El video supera 250 MB.")

    with _LOCK:
        if any(job["state"] in ("uploading", "processing") for job in _JOBS.values()):
            raise HTTPException(status_code=429, detail="Ya hay un video en proceso. Esperá a que termine.")
        identifier = uuid.uuid4().hex
        directory = tempfile.mkdtemp(prefix="pantheraid_video_")
        source = Path(directory) / ("entrada" + extension)
        _JOBS[identifier] = {
            "state": "uploading", "stage": "Recibiendo video por bloques…",
            "created_at": time.time(), "last_upload_at": time.time(),
            "directory": directory, "source": str(source), "filename": filename,
            "threshold": threshold, "sample_seconds": sample_seconds, "max_samples": max_samples,
            "expected_size": expected, "received_bytes": 0,
            "upload_lock": asyncio.Lock(),
            "processed": 0, "total": 0, "error": None, "result": None,
        }
    logger.info("Sesión de video %s iniciada (%.2f MiB)", identifier, expected / (1024 * 1024))
    return {"upload_id": identifier, "chunk_max_bytes": MAX_UPLOAD_CHUNK_BYTES,
            "expected_bytes": expected}


@router.put("/uploads/{identifier}/chunks")
async def upload_video_chunk(request: Request, identifier: str, offset: int = Query(..., ge=0)):
    _prune()
    with _LOCK:
        job = _JOBS.get(identifier)
        if not job or job["state"] != "uploading" or "upload_lock" not in job:
            raise HTTPException(status_code=404, detail="La sesión de carga no existe o ya terminó.")
        upload_lock = job["upload_lock"]

    async with upload_lock:
        with _LOCK:
            job = _JOBS.get(identifier)
            if not job or job["state"] != "uploading":
                raise HTTPException(status_code=409, detail="La carga ya no está disponible.")
            start = job["received_bytes"]
            expected = job["expected_size"]
            source = Path(job["source"])
            if offset != start:
                raise HTTPException(
                    status_code=409,
                    detail=f"Orden incorrecto de bloques: el servidor esperaba el byte {start}."
                )
        length = request.headers.get("content-length")
        if length:
            try:
                declared = int(length)
            except ValueError:
                raise HTTPException(status_code=400, detail="Tamaño de bloque inválido.")
            if declared > MAX_UPLOAD_CHUNK_BYTES or start + declared > expected:
                raise HTTPException(status_code=413, detail="El bloque supera el tamaño permitido.")

        received = 0
        try:
            with source.open("ab") as sink:
                async for piece in request.stream():
                    received += len(piece)
                    if received > MAX_UPLOAD_CHUNK_BYTES or start + received > expected:
                        raise HTTPException(
                            status_code=413, detail="El bloque supera 8 MB o el tamaño declarado."
                        )
                    sink.write(piece)
            if received == 0:
                raise HTTPException(status_code=400, detail="El bloque recibido está vacío.")
        except BaseException:
            # A disconnected browser must not leave a corrupt partial chunk.
            if source.exists():
                with source.open("r+b") as sink:
                    sink.truncate(start)
            raise
        _change(identifier, received_bytes=start + received, last_upload_at=time.time())
        return {"upload_id": identifier, "received_bytes": start + received,
                "expected_bytes": expected}


@router.post("/uploads/{identifier}/complete", status_code=202)
async def finish_chunked_upload(identifier: str):
    _prune()
    with _LOCK:
        job = _JOBS.get(identifier)
        if not job or "upload_lock" not in job:
            raise HTTPException(status_code=404, detail="La carga no existe o ya terminó.")
        upload_lock = job["upload_lock"]

    async with upload_lock:
        with _LOCK:
            job = _JOBS.get(identifier)
            if not job or job["state"] != "uploading":
                raise HTTPException(status_code=409, detail="La carga ya no está disponible.")
            if job["received_bytes"] != job["expected_size"]:
                raise HTTPException(
                    status_code=409, detail="La carga está incompleta. Faltan bloques del video."
                )
            source = Path(job["source"])
            if not source.exists() or source.stat().st_size != job["expected_size"]:
                raise HTTPException(status_code=409, detail="El archivo recibido no coincide con su tamaño.")
            job.update(state="processing", stage="Preparando análisis…")
        _EXECUTOR.submit(_process, identifier)
    return {"job_id": identifier, "state": "processing", "message": "Video completo; análisis iniciado."}


@router.delete("/uploads/{identifier}", status_code=204)
async def cancel_chunked_upload(identifier: str):
    with _LOCK:
        job = _JOBS.get(identifier)
        if not job or job["state"] != "uploading" or "upload_lock" not in job:
            raise HTTPException(status_code=404, detail="La carga no existe o ya finalizó.")
        upload_lock = job["upload_lock"]
    async with upload_lock:
        with _LOCK:
            job = _JOBS.get(identifier)
            if not job or job["state"] != "uploading":
                raise HTTPException(status_code=409, detail="El análisis ya comenzó.")
            _JOBS.pop(identifier, None)
        shutil.rmtree(job["directory"], ignore_errors=True)


@router.post("/jobs", status_code=202)
async def create_video_job(
    request: Request,
    threshold: float = Query(0.25, ge=0.10, le=0.90),
    sample_seconds: float = Query(1.0, ge=0.5, le=5.0),
    max_samples: int = Query(8, ge=1, le=MAX_SAMPLES),
):
    _prune()
    raw_name = unquote(request.headers.get("x-video-name", "camara.mp4"))
    filename = Path(raw_name.replace("\\", "/")).name[:120] or "camara.mp4"
    extension = Path(filename).suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Formato no admitido. Usá MP4, MOV, AVI o MKV.")
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_VIDEO_BYTES:
                raise HTTPException(status_code=413, detail="El video supera 250 MB.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Tamaño de solicitud inválido.")

    with _LOCK:
        if any(job["state"] in ("uploading", "processing") for job in _JOBS.values()):
            raise HTTPException(status_code=429, detail="Ya hay un video en proceso. Esperá a que termine.")
        identifier = uuid.uuid4().hex
        directory = tempfile.mkdtemp(prefix="pantheraid_video_")
        source = Path(directory) / ("entrada" + extension)
        _JOBS[identifier] = {
            "state": "uploading", "stage": "Recibiendo video…", "created_at": time.time(),
            "directory": directory, "source": str(source), "filename": filename,
            "threshold": threshold, "sample_seconds": sample_seconds, "max_samples": max_samples,
            "processed": 0, "total": 0, "error": None, "result": None,
        }

    size = 0
    try:
        with source.open("wb") as sink:
            async for block in request.stream():
                size += len(block)
                if size > MAX_VIDEO_BYTES:
                    raise HTTPException(status_code=413, detail="El video supera 250 MB.")
                sink.write(block)
        if not size:
            raise HTTPException(status_code=400, detail="El archivo está vacío.")
        _change(identifier, state="processing", stage="Preparando análisis…")
        _EXECUTOR.submit(_process, identifier)
    except BaseException:
        with _LOCK:
            _JOBS.pop(identifier, None)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return {"job_id": identifier, "state": "processing", "message": "Video recibido; análisis iniciado."}


@router.get("/jobs/{identifier}")
def get_video_job(identifier: str):
    return _snapshot(identifier)


@router.get("/jobs/{identifier}/download")
def download_video_job(identifier: str, kind: str = Query("zip", pattern="^(zip|csv|pdf)$")):
    snapshot = _snapshot(identifier)
    if snapshot["state"] != "completed":
        raise HTTPException(status_code=409, detail="El análisis todavía no terminó.")
    with _LOCK:
        directory = Path(_JOBS[identifier]["directory"])
    files = {
        "zip": ("fotogramas_y_candidatos.zip", "application/zip"),
        "csv": ("resultados_por_fotograma.csv", "text/csv; charset=utf-8"),
        "pdf": ("informe_pantheraid.pdf", "application/pdf"),
    }
    file_name, media_type = files[kind]
    target = directory / file_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="No se encontró el archivo solicitado.")
    return FileResponse(target, media_type=media_type, filename=file_name)
