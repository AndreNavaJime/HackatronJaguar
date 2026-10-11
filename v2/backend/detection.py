"""Optional MegaDetector V6 inference for PantheraID 2.0.

MegaDetector detects animal/person/vehicle, not species or individual identity.
The model is lazy-loaded on first request and reused in this server process.
"""
import base64
import io
import threading
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

DETECTOR_VERSION = 'MDV6-yolov9-c'
CLASS_NAMES = {0: 'animal', 1: 'person', 2: 'vehicle'}
_MODEL_LOCK = threading.Lock()
_MODEL = None
_MODEL_DEVICE = None


class DetectorUnavailable(Exception):
    """Raised when model dependencies or weights cannot be loaded."""


def _get_model():
    global _MODEL, _MODEL_DEVICE
    if _MODEL is None:
        try:
            import torch
            from PytorchWildlife.models import detection as pw_detection
        except (ImportError, OSError) as error:
            raise DetectorUnavailable(
                'Falta MegaDetector o alguna dependencia. Instalá primero '
                '`python -m pip install -r requirements-ai.txt` en v2/backend. '
                f'Detalle: {error}'
            ) from error
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        try:
            model = pw_detection.MegaDetectorV6(
                device=device, pretrained=True, version=DETECTOR_VERSION
            )
        except Exception as error:
            raise DetectorUnavailable(
                'MegaDetector no pudo inicializarse. Verificá conexión, memoria '
                'disponible y descarga de pesos. '
                f'Detalle: {type(error).__name__}: {error}'
            ) from error
        _MODEL = model
        _MODEL_DEVICE = device
    return _MODEL, _MODEL_DEVICE


def _render_image(image, records):
    annotated = image.copy().convert('RGB')
    draw = ImageDraw.Draw(annotated)
    line_width = max(2, round(min(annotated.size) / 160))
    palette = {'animal': '#70e7a4', 'person': '#f8c168', 'vehicle': '#8fc9ff'}
    for record in records:
        x1, y1, x2, y2 = record['bbox_xyxy']
        color = palette.get(record['class_name'], '#ffffff')
        draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)
        label = f"{record['class_name'].upper()} {record['confidence']:.2f}"
        top = max(0, y1 - 19)
        label_width = max(80, len(label) * 8)
        draw.rectangle((x1, top, min(image.width, x1 + label_width), min(image.height, top + 18)), fill='#092117')
        draw.text((x1 + 3, top + 2), label, fill='#ffffff')
    buffer = io.BytesIO()
    annotated.save(buffer, format='JPEG', quality=89, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def detect_image(image: Image.Image, threshold: float):
    """Run inference on an already validated, EXIF-oriented image.

    Lock serializes CPU/GPU inference to reduce memory pressure in demo Codespaces.
    Temporary JPEG is unlinked on both success and failure.
    """
    rgb = image.convert('RGB')
    path = None
    with _MODEL_LOCK:
        model, device = _get_model()
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', prefix='pantheraid_', delete=False) as temp:
                path = Path(temp.name)
                rgb.save(temp, format='JPEG', quality=94)
            start = time.perf_counter()
            result = model.single_image_detection(str(path), det_conf_thres=threshold)
            elapsed = time.perf_counter() - start
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    if not isinstance(result, dict) or 'detections' not in result:
        raise ValueError('Respuesta inesperada de MegaDetector.')

    records = []
    det = result['detections']
    if det is not None:
        for coordinates, confidence, class_id in zip(det.xyxy, det.confidence, det.class_id):
            score = float(confidence)
            if score < threshold:
                continue
            kind = CLASS_NAMES.get(int(class_id), 'unknown')
            x1, y1, x2, y2 = [int(round(float(v))) for v in coordinates]
            x1 = max(0, min(x1, rgb.width - 1))
            y1 = max(0, min(y1, rgb.height - 1))
            x2 = max(x1 + 1, min(x2, rgb.width))
            y2 = max(y1 + 1, min(y2, rgb.height))
            records.append({
                'class_name': kind,
                'confidence': round(score, 4),
                'bbox_xyxy': [x1, y1, x2, y2],
            })
    counts = {label: sum(r['class_name'] == label for r in records) for label in CLASS_NAMES.values()}
    return {
        'model': f'MegaDetector V6 ({DETECTOR_VERSION})',
        'device': device,
        'threshold': threshold,
        'inference_seconds': round(elapsed, 3),
        'counts': counts,
        'detections': records,
        'annotated_image': _render_image(rgb, records),
        'note': 'MegaDetector detecta animales, personas y vehículos. No identifica especies ni jaguares individuales.',
    }
