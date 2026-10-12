"""Low-memory, non-AI video screening for the free PantheraID deployment.

Uses frame differences, not wildlife classification. Motion in vegetation,
camera shake and lighting changes can produce positive scores; stationary
wildlife can be missed. No model confidence or species inference is made.
"""
from __future__ import annotations

import csv
import io
import logging
import math
import time
import zipfile
from pathlib import Path

logger = logging.getLogger("pantheraid.video.lite")

MAX_LITE_DURATION_SECONDS = 180
LITE_FRAME_MAX_SIDE = 640
LITE_COMPARE_SIDE = 320


def _write_lite_pdf(path, metadata, totals, rows, example_jpeg):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as ReportImage

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.7 * cm,
                            rightMargin=1.7 * cm, topMargin=1.7 * cm, bottomMargin=1.7 * cm)
    story = [
        Paragraph("PANTHERALAB | PantheraID 2.0", styles["Title"]),
        Paragraph("Preseleccion por cambios visuales (OpenCV, SIN inteligencia artificial)", styles["Heading2"]),
        Spacer(1, .35 * cm),
        Paragraph("Archivo: " + __import__("html").escape(metadata["filename"]), styles["Normal"]),
        Paragraph("Duracion: %.1f s | Muestreo: %.1f s | FPS: %.2f" %
                  (metadata["duration_seconds"], metadata["sample_seconds"], metadata["fps"]), styles["Normal"]),
        Paragraph("Fotogramas evaluados: %d | Con cambio visual: %d | Sin cambio visual: %d" %
                  (totals["sampled"], totals["retained"], totals["discarded"]), styles["Normal"]),
        Paragraph("Umbral de cambio visual: %.1f%% | No es una probabilidad de animal." %
                  (100 * metadata["threshold"]), styles["Normal"]),
        Spacer(1, .35 * cm),
    ]
    table = [["Muestra", "Tiempo (s)", "Cambio visual (%)", "Decision"]]
    for row in rows:
        table.append([str(row["sample"]), str(row["video_time_seconds"]),
                      "%.1f" % (row["motion_score"] * 100), row["edge_decision"]])
    chart = Table(table, colWidths=[2.5 * cm, 3.1 * cm, 4.3 * cm, 6.5 * cm], repeatRows=1)
    chart.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173d45")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#9bb5c3")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(chart)
    if example_jpeg:
        from PIL import Image
        im = Image.open(io.BytesIO(example_jpeg))
        w, h = im.size
        scale = min(16 * cm / w, 7 * cm / h)
        story += [Spacer(1, .3 * cm), Paragraph("Fotograma de referencia", styles["Heading3"]),
                  ReportImage(io.BytesIO(example_jpeg), width=w * scale, height=h * scale)]
    story += [Spacer(1, .4 * cm),
              Paragraph("Limitaciones cientificas importantes", styles["Heading3"]),
              Paragraph(
                "Esta herramienta NO utiliza inteligencia artificial ni MegaDetector. "
                "NO detecta animales, personas ni vehiculos, y NO identifica jaguares, especies o individuos. "
                "Compara muestras separadas en el tiempo mediante diferencias de brillo de pixeles. "
                "Lluvia, sombras, vegetacion, movimientos de camara y cambios de iluminacion pueden activar alertas. "
                "Un animal inmovil, fuera de las muestras o pequeno puede pasar inadvertido. "
                "Revise TODOS los fotogramas; no infiera ausencia de fauna. "
                "Las cifras de bytes se refieren solo a JPEG muestreados, no a ahorro de trafico 5G medido.",
                styles["Normal"]),
              Paragraph("Herramienta exploratoria; resultados no validados como indicador de biodiversidad.",
                        styles["Normal"])]
    doc.build(story)


def process_lightweight(identifier):
    """Run bounded motion screening; keeps the existing job and download protocol."""
    import video_api as api

    with api._LOCK:
        job = api._JOBS.get(identifier)
        if job is None:
            return
        source = Path(job["source"])
        folder = Path(job["directory"])
        filename = job["filename"]
        sample_seconds = job["sample_seconds"]
        max_samples = job["max_samples"]
        threshold = job.get("motion_threshold", .035)

    try:
        import cv2
        import numpy as np
        from PIL import Image
        api._change(identifier, state="processing", stage="Leyendo video para análisis ligero…")
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise api.VideoError("OpenCV no pudo leer el video. Probá exportarlo como MP4 (H.264).")
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if not math.isfinite(fps) or fps <= 0 or fps > 240:
                raise api.VideoError("No se pudo determinar el FPS del video.")
            if frame_count < 1 or width < 1 or height < 1 or width * height > api.MAX_FRAME_PIXELS:
                raise api.VideoError("Metadatos o resolución de video no admitidos (máximo 4K).")
            duration = frame_count / fps
            if duration > MAX_LITE_DURATION_SECONDS:
                raise api.VideoError("En modo gratuito, usá un video de máximo 3 minutos.")
            indices = []
            candidate = 0
            while candidate < frame_count and len(indices) < max_samples:
                indices.append(candidate)
                candidate = max(candidate + 1, round(len(indices) * sample_seconds * fps))
            api._change(identifier, total=len(indices), stage="Comparando cambios visuales…")
            frames, rows = [], []
            previous_gray = None
            input_bytes = retained_bytes = 0
            scores = []
            example_jpeg = None
            archive = folder / "fotogramas_y_candidatos.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4) as output:
                for position, frame_index in enumerate(indices, start=1):
                    api._change(identifier, stage="Revisando fotograma %d de %d…" % (position, len(indices)))
                    if not cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
                        raise api.VideoError("El códec no permite acceder a este fotograma.")
                    ok, frame_bgr = cap.read()
                    if not ok or frame_bgr is None:
                        raise api.VideoError("No se pudo decodificar el fotograma %d." % position)
                    h, w = frame_bgr.shape[:2]
                    if max(w, h) > LITE_FRAME_MAX_SIDE:
                        ratio = LITE_FRAME_MAX_SIDE / max(w, h)
                        frame_bgr = cv2.resize(frame_bgr, (max(1, int(w * ratio)), max(1, int(h * ratio))),
                                               interpolation=cv2.INTER_AREA)
                    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                    if max(gray.shape) > LITE_COMPARE_SIDE:
                        ratio = LITE_COMPARE_SIDE / max(gray.shape)
                        gray = cv2.resize(gray, (max(1, int(gray.shape[1] * ratio)),
                                                 max(1, int(gray.shape[0] * ratio))), interpolation=cv2.INTER_AREA)
                    gray = cv2.GaussianBlur(gray, (5, 5), 0)
                    motion_score = 0.0
                    if previous_gray is not None:
                        difference = cv2.absdiff(previous_gray, gray)
                        # Fraction of significantly changed pixels; NOT a probability of wildlife.
                        motion_score = float(np.count_nonzero(difference > 30) / difference.size)
                    previous_gray = gray
                    review = position > 1 and motion_score >= threshold
                    image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
                    jpeg = api._jpeg_bytes(image, quality=77)
                    input_bytes += len(jpeg)
                    if example_jpeg is None:
                        example_jpeg = jpeg
                    if review:
                        retained_bytes += len(jpeg)
                        output.writestr("revision_sugerida/fotograma_%03d.jpg" % position, jpeg)
                    output.writestr("todos_los_fotogramas/fotograma_%03d.jpg" % position, jpeg)
                    seconds = round(frame_index / fps, 2)
                    scores.append(motion_score)
                    frames.append({
                        "sample": position, "time_seconds": seconds, "retained": review,
                        "counts": {"animal": 0, "person": 0, "vehicle": 0},
                        "max_animal_confidence": 0.0, "motion_score": round(motion_score, 4),
                        "inference_seconds": 0.0, "image": api._image_data_url(jpeg), "detections": [],
                    })
                    rows.append({
                        "sample": position, "video_time_seconds": seconds,
                        "animals": 0, "persons": 0, "vehicles": 0,
                        "max_animal_confidence": 0, "motion_score": round(motion_score, 4),
                        "edge_decision": "REVISAR" if review else ("REFERENCIA" if position == 1 else "SIN_CAMBIO"),
                        "input_jpeg_bytes": len(jpeg), "candidate_jpeg_bytes": 0, "inference_seconds": 0,
                    })
                    api._change(identifier, processed=position)
                csv_path = folder / "resultados_por_fotograma.csv"
                with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=[
                        "sample", "video_time_seconds", "motion_score", "edge_decision", "input_jpeg_bytes"])
                    writer.writeheader()
                    for row in rows:
                        writer.writerow({key: row[key] for key in writer.fieldnames})
                output.write(csv_path, arcname="resultados_por_fotograma.csv")
            retained = sum(frame["retained"] for frame in frames)
            total = len(frames)
            totals = {
                "sampled": total, "retained": retained, "discarded": total - retained,
                "animals": 0, "persons": 0, "vehicles": 0,
                "mean_confidence": 0, "max_confidence": 0, "animal_detection_count": 0,
                "mean_inference_seconds": 0, "mean_motion": sum(scores) / max(1, total),
                "positive_frame_rate": 100 * retained / max(1, total),
                "estimated_payload_reduction": 100 * (1 - retained_bytes / max(1, input_bytes)),
                "input_jpeg_bytes": input_bytes, "retained_jpeg_bytes": retained_bytes,
            }
            metadata = {
                "mode": "lite", "model": "OpenCV: diferencia de fotogramas (SIN IA)",
                "device": "CPU", "filename": filename,
                "source_width": width, "source_height": height,
                "analysis_width": frames and image.width or 0,
                "analysis_height": frames and image.height or 0,
                "fps": round(fps, 3), "duration_seconds": round(duration, 2),
                "total_video_frames": frame_count, "sample_seconds": sample_seconds,
                "threshold": threshold,
            }
            api._change(identifier, stage="Preparando descargas científicas…")
            pdf_path = folder / "informe_pantheraid.pdf"
            _write_lite_pdf(pdf_path, metadata, totals, rows, example_jpeg)
            with zipfile.ZipFile(archive, "a", compression=zipfile.ZIP_DEFLATED) as output:
                output.write(pdf_path, arcname="informe_pantheraid.pdf")
            result = {
                "metadata": metadata, "totals": totals, "rows": rows, "frames": frames,
                "candidates": [],
                "note": "Modo gratuito SIN IA: solo identifica cambios visuales entre fotogramas. "
                        "NO detecta animales ni especies; revisar todas las muestras, incluso las estables.",
            }
            api._change(identifier, state="completed", stage="Preselección visual completada", result=result)
            logger.info("Video ligero %s finalizado: %d muestras, %d con cambios", identifier, total, retained)
        finally:
            cap.release()
    except Exception as error:
        logger.exception("Error en el modo ligero de video %s", identifier)
        # Do not disclose filesystem paths or stack traces to the public endpoint.
        message = str(error) if isinstance(error, api.VideoError) else (
            "No se pudo completar el análisis ligero. Revisá los registros de Render.")
        api._change(identifier, state="failed", stage="Análisis interrumpido", error=message)
    finally:
        source.unlink(missing_ok=True)
