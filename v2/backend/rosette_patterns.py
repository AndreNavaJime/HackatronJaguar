"""Exploratory rosette-like texture proposals inside detected animal crops.

Not a species classifier, a trained rosette detector, or individual re-identification.
Bounding boxes are heuristic suggestions for human visual review only.
No source photographs are persisted.
"""
import base64
import io

from PIL import Image, ImageDraw, ImageOps

MAX_ANIMALS = 2
MAX_MARKERS = 24
MAX_CROP_SIDE = 560


def _data_url(picture: Image.Image) -> str:
    output = io.BytesIO()
    picture.convert("RGB").save(output, format="JPEG", quality=83, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _rosette_like_regions(crop: Image.Image) -> list[list[int]]:
    """Locate bounded dark rings. Heuristic: NOT validated true jaguar rosettes."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    pixels = np.asarray(crop.convert("RGB"))
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    mask = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 31, 7,
    )
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    h, w = gray.shape
    max_area = max(200, 0.05 * h * w)
    found = []
    for index, contour in enumerate(contours):
        child = int(hierarchy[0][index][2])
        if child < 0:
            continue
        area = cv2.contourArea(contour)
        hole = cv2.contourArea(contours[child])
        if not (20 <= area <= max_area and 0.06 <= hole / max(area, 1) <= 0.8):
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw < 7 or bh < 7 or not 0.42 <= bw / bh <= 2.4:
            continue
        if x == 0 or y == 0 or x + bw >= w or y + bh >= h:
            continue
        found.append((area, [int(x), int(y), int(x + bw), int(y + bh)]))
    found.sort(key=lambda v: v[0], reverse=True)
    boxes = []
    for _, candidate in found:
        cx = (candidate[0] + candidate[2]) / 2
        cy = (candidate[1] + candidate[3]) / 2
        if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes):
            continue
        boxes.append(candidate)
        if len(boxes) >= MAX_MARKERS:
            break
    return boxes


def analyze_patterns(image: Image.Image, detections: list[dict], allow_full_image: bool = False) -> dict:
    """Return small visual references for animal boxes only; no identity claim."""
    if any(item.get("class_name") == "person" for item in detections):
        return {
            "status": "skipped_people_present", "samples": [],
            "identity_verified": False, "scientifically_validated": False,
            "note": "Se omitió el análisis de pelaje porque se detectaron personas.",
        }
    animals = sorted(
        (d for d in detections if d.get("class_name") == "animal"),
        key=lambda d: float(d.get("confidence", 0)), reverse=True,
    )[:MAX_ANIMALS]
    samples = []
    # Render free plan cannot safely run PyTorch models in 512 MB; this
    # fallback explores generic image texture without guessing an animal ID.
    if not animals and allow_full_image:
        animals = [{"bbox_xyxy": [0, 0, image.width, image.height]}]
    for animal in animals:
        box = animal.get("bbox_xyxy", [])
        if not isinstance(box, list) or len(box) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in box]
        x1 = max(0, min(image.width - 1, x1))
        y1 = max(0, min(image.height - 1, y1))
        x2 = max(x1 + 1, min(image.width, x2))
        y2 = max(y1 + 1, min(image.height, y2))
        crop = image.convert("RGB").crop((x1, y1, x2, y2))
        if min(crop.size) < 24:
            continue
        crop.thumbnail((MAX_CROP_SIDE, MAX_CROP_SIDE), Image.Resampling.LANCZOS)
        crop = ImageOps.autocontrast(crop, cutoff=1)
        proposals = _rosette_like_regions(crop)
        preview = crop.copy()
        drawer = ImageDraw.Draw(preview)
        for candidate in proposals:
            drawer.rectangle(candidate, outline="#edba65", width=2)
        samples.append({
            "animal_bbox_xyxy": [x1, y1, x2, y2],
            "texture_regions_xyxy": proposals,
            "annotated_crop": _data_url(preview),
        })
    return {
        "status": ("exploratory_full_image" if samples and allow_full_image and not detections
                   else "exploratory" if samples else "no_animal_region"),
        "method": "contrast_contours_v1",
        "samples": samples,
        "identity_verified": False,
        "scientifically_validated": False,
        "note": (
            "Los recuadros amarillos son regiones oscuras con formas anulares "
            "propuestas por un algoritmo exploratorio. No prueban que sean rosetas "
            "de jaguar. No determinan especie ni identifican individuos."
        ),
    }
