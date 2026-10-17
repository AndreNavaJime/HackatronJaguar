"""Experimental jaguar flank matching using OpenCV local features.

This is NOT the HotSpotter package, species classification, or scientifically
validated individual identification. Results are candidate matches for review.
No photos, local features, or biological records are persisted.
"""
import base64
import io
import json
import threading
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError

router = APIRouter(prefix="/api/individuals", tags=["experimental-reidentification"])
_INFERENCE_SEMAPHORE = threading.BoundedSemaphore(1)

MAX_BYTES = 8 * 1024 * 1024
MAX_REFERENCES = 6
MAX_PIXELS = 24_000_000
MAX_SIDE = 680
VALID_FLANKS = {"left", "right", "unknown"}
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _photo(file: UploadFile) -> Image.Image:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Solo se admiten fotografías JPEG, PNG y WebP.")
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Cada fotografía debe tener un máximo de 8 MB.")
    if not data:
        raise HTTPException(422, "Se recibió una fotografía vacía.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "El contenido no es JPEG, PNG o WebP.")
            if image.width * image.height > MAX_PIXELS:
                raise HTTPException(413, "La fotografía supera 24 megapíxeles.")
            image.load()
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            rgb.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            return rgb
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "No se pudo decodificar la fotografía.") from exc


def _features(image: Image.Image, sift):
    arr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    arr = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(arr)
    keypoints, descriptors = sift.detectAndCompute(arr, None)
    return arr, keypoints or [], descriptors


def _evidence(query, reference, qkp, rkp, matches):
    if not matches:
        return None
    drawn = cv2.drawMatches(
        query, qkp, reference, rkp, matches[:24], None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    if drawn.shape[1] > 1240:
        scale = 1240 / drawn.shape[1]
        drawn = cv2.resize(drawn, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", drawn, [cv2.IMWRITE_JPEG_QUALITY, 72])
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode() if ok else None


def _score(qkp, qdes, rkp, rdes, matcher):
    if qdes is None or rdes is None or len(qdes) < 3 or len(rdes) < 3:
        return [], 0, 0.0
    def ratio_matches(source, target):
        good = {}
        for pair in matcher.knnMatch(source, target, k=2):
            if len(pair) == 2 and pair[0].distance < 0.72 * pair[1].distance:
                good[pair[0].queryIdx] = pair[0]
        return good
    forward = ratio_matches(qdes, rdes)
    reverse = ratio_matches(rdes, qdes)
    mutual = [m for m in forward.values()
              if m.trainIdx in reverse and reverse[m.trainIdx].trainIdx == m.queryIdx]
    if len(mutual) < 4:
        return [], len(mutual), 0.0
    origin = np.float32([qkp[m.queryIdx].pt for m in mutual]).reshape(-1, 1, 2)
    target = np.float32([rkp[m.trainIdx].pt for m in mutual]).reshape(-1, 1, 2)
    try:
        _, mask = cv2.estimateAffinePartial2D(
            origin, target, method=cv2.RANSAC, ransacReprojThreshold=9.0,
            maxIters=1500, confidence=0.97,
        )
    except cv2.error:
        mask = None
    aligned = [m for m, keep in zip(mutual, mask.ravel()) if keep] if mask is not None else []
    if len(aligned) < 3:
        return aligned, len(mutual), 0.0
    xy = np.float32([qkp[m.queryIdx].pt for m in aligned])
    spread = float(np.ptp(xy[:, 0]) * np.ptp(xy[:, 1]))
    return aligned, len(mutual), spread


def compare_images(query: Image.Image, references: list[Image.Image],
                   labels: list[str], flanks: list[str], query_flank: str):
    cv2.setNumThreads(1)
    if not hasattr(cv2, "SIFT_create"):
        raise HTTPException(503, "Esta versión de OpenCV no incluye SIFT.")
    sift = cv2.SIFT_create(nfeatures=850)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    qgray, qkp, qdes = _features(query, sift)
    candidates = []
    for index, (image, label, flank) in enumerate(zip(references, labels, flanks)):
        # Cross-flank comparisons are biologically unreliable; do not rank them.
        if query_flank != "unknown" and flank != "unknown" and query_flank != flank:
            candidates.append({
                "label": label, "reference_index": index, "reference_flank": flank,
                "status": "incompatible_flank", "tentative_matches": 0,
                "coherent_matches": 0, "spread_fraction": 0.0, "evidence_image": None,
            })
            continue
        rgray, rkp, rdes = _features(image, sift)
        coherent, tentative, spread = _score(qkp, qdes, rkp, rdes, matcher)
        spread_fraction = spread / max(1, qgray.shape[0] * qgray.shape[1])
        supported = len(coherent) >= 7 and tentative >= 9 and spread_fraction >= 0.012
        candidates.append({
            "label": label, "reference_index": index, "reference_flank": flank,
            "status": "candidate_for_review" if supported else "insufficient_evidence",
            "tentative_matches": tentative, "coherent_matches": len(coherent),
            "spread_fraction": round(spread_fraction, 4),
            "evidence_image": _evidence(qgray, rgray, qkp, rkp, coherent) if coherent else None,
        })
    candidates.sort(key=lambda c: (
        c["status"] == "candidate_for_review",
        c["coherent_matches"], c["spread_fraction"], c["tentative_matches"],
    ), reverse=True)
    return {
        "method": "SIFT + mutual ratio test + geometric RANSAC (OpenCV)",
        "engine": "opencv_local_features_v1",
        "hotspotter_installed": False,
        "is_machine_learning_species_detector": False,
        "scientifically_validated": False,
        "identity_verified": False,
        "query_flank": query_flank,
        "reference_count": len(references),
        "query_keypoints": len(qkp),
        "candidates": candidates,
        "note": (
            "Coincidencias locales exploratorias, NO probabilidades ni identidades "
            "confirmadas. Compará recortes del MISMO costado del jaguar. "
            "Fotos con fondo, iluminación, postura o ángulo distintos pueden generar "
            "falsas coincidencias y falsos negativos. La revisión humana es obligatoria."
        ),
    }


@router.post("/compare")
async def compare_individuals(
    query: Annotated[UploadFile, File()],
    references: Annotated[list[UploadFile], File()],
    labels: Annotated[str, Form()],
    flanks: Annotated[str, Form()],
    query_flank: Annotated[str, Form()] = "unknown",
):
    if not 1 <= len(references) <= MAX_REFERENCES:
        raise HTTPException(422, f"Seleccioná entre 1 y {MAX_REFERENCES} referencias.")
    try:
        names = json.loads(labels)
        sides = json.loads(flanks)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Metadatos de referencia incorrectos.") from exc
    if not isinstance(names, list) or not isinstance(sides, list) or len(names) != len(references) or len(sides) != len(references):
        raise HTTPException(422, "Cada referencia necesita un código y un costado.")
    if any(not isinstance(n, str) or not n.strip() or len(n.strip()) > 80 for n in names):
        raise HTTPException(422, "Cada individuo necesita un código de 1 a 80 caracteres.")
    if query_flank not in VALID_FLANKS or any(s not in VALID_FLANKS for s in sides):
        raise HTTPException(422, "Costado inválido: usá izquierdo, derecho o desconocido.")
    photos = [await _photo(query)]
    for file in references:
        photos.append(await _photo(file))
    if not _INFERENCE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(429, "El comparador ya está analizando otra solicitud. Reintentá en unos momentos.")
    try:
        try:
            return await run_in_threadpool(
                compare_images, photos[0], photos[1:], [name.strip() for name in names],
                sides, query_flank,
            )
        except cv2.error as exc:
            raise HTTPException(503, "OpenCV no pudo completar la comparación.") from exc
    finally:
        _INFERENCE_SEMAPHORE.release()
