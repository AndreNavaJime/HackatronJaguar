"""PantheraID v2 API — photo intake and optional MegaDetector V6."""
import hashlib
import io
import logging
from importlib.util import find_spec
import os
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError

from detection import DetectorUnavailable, detect_image
from rosette_patterns import analyze_patterns
from live_ai import (capabilities as live_capabilities, wildlife_frame, fire_frame,
                     LiveModelUnavailable)
from video_api import router as video_router
from scientific_api import router as scientific_router, edge_router
from study_reports import router as study_report_router
from sense_api import router as sense_router
from satellite_vegetation import router as vegetation_router

logger = logging.getLogger('pantheraid.api')

MAX_IMAGE_BYTES = 12 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000

app = FastAPI(title='PantheraID API', version='0.4.0')
app.include_router(video_router)
app.include_router(scientific_router)
app.include_router(edge_router)
app.include_router(study_report_router)
app.include_router(sense_router)
app.include_router(vegetation_router)
# Same-origin Vite proxy serves /api calls in Codespaces; restrict external CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173'],
    allow_credentials=False,
    allow_methods=['GET'],
    allow_headers=['*'],
)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'PantheraID API', 'version': '0.4.0'}


@app.get('/api/capabilities')
def capabilities():
    return {
        'modules': ['PantheraID', 'PantheraMONITORING', 'PantheraEDGE'],
        'image_intake': 'available',
        'image_auto_analysis': 'lightweight_texture_available',
        'heavy_photo_ai': 'enabled' if (os.getenv('PANTHERA_ENABLE_HEAVY_IMAGE_AI') == '1' and find_spec('PytorchWildlife')) else 'disabled',
        'rosette_texture': 'exploratory_contours_not_reidentification',
        'animal_detection': 'optional_dependencies_installed' if find_spec('PytorchWildlife') else 'requires_pytorchwildlife',
        'individual_identification': 'not_validated',
        'video_analysis': 'lite_available' if find_spec('cv2') else 'requires_opencv',
        'video_lightweight': 'available' if find_spec('cv2') and find_spec('reportlab') else 'requires_opencv_and_reportlab',
        'video_ai': 'optional_dependencies_installed' if find_spec('PytorchWildlife') else 'requires_pytorchwildlife',
        'video_exports': ['csv', 'zip', 'pdf'],
        'video_job_storage': 'temporary_one_hour',
        'supabase': 'not_configured',
        'edge_ingestion': 'not_migrated',
        'live_ai': live_capabilities(),
    }


@app.get('/api/live/capabilities')
def live_capability_status():
    return live_capabilities()


@app.post('/api/live/wildlife-frame')
async def analyze_live_wildlife_frame(request: Request, threshold: float = Query(0.30, ge=0.1, le=0.9)):
    # Same 12 MB/image-type validation as PantheraID. Source files are not stored.
    _, frame, _, _ = await _read_image(request)
    try:
        return await run_in_threadpool(wildlife_frame, frame, threshold)
    except LiveModelUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post('/api/fire/frame')
async def analyze_live_fire_frame(request: Request):
    _, frame, _, _ = await _read_image(request)
    try:
        return await run_in_threadpool(fire_frame, frame)
    except LiveModelUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


async def _read_image(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail='La imagen supera el límite de 12 MB.')
    if not data:
        raise HTTPException(status_code=400, detail='No se recibió ninguna imagen.')
    content = bytes(data)
    try:
        with Image.open(io.BytesIO(content)) as original:
            if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise HTTPException(status_code=415, detail='Usá JPEG, PNG o WebP.')
            if original.width * original.height > 40_000_000:
                raise HTTPException(status_code=413, detail='La imagen supera el límite de 40 megapíxeles.')
            image_format, mode = original.format, original.mode
            original.load()
            image = ImageOps.exif_transpose(original).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail='La imagen no se pudo leer.')
    return content, image, image_format, mode


@app.post('/api/images/inspect')
async def inspect_image(request: Request):
    content, image, image_format, mode = await _read_image(request)
    return {
        'status': 'received',
        'format': image_format,
        'width': image.width,
        'height': image.height,
        'color_mode': mode,
        'size_bytes': len(content),
        'sha256': hashlib.sha256(content).hexdigest(),
        'saved': False,
        'animal_detection': False,
        'note': 'Recepción validada. Todavía no se ha ejecutado MegaDetector ni identificado ningún jaguar.',
    }


@app.post('/api/images/detect')
async def detect(request: Request, threshold: float = Query(0.25, ge=0.1, le=0.9)):
    _, image, _, _ = await _read_image(request)
    try:
        return await run_in_threadpool(detect_image, image, threshold)
    except DetectorUnavailable as error:
        logger.warning('MegaDetector no disponible: %s', error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception('Falló la inferencia de MegaDetector')
        raise HTTPException(status_code=500, detail=f'Falló la inferencia de MegaDetector ({type(error).__name__}). Revisá la terminal de Python.') from error


def _analyze_photo(image: Image.Image, threshold: float):
    """Lightweight default; real MegaDetector only with explicit operator opt-in.

    512 MB free Render instances cannot be assumed to fit PyTorch and weights.
    The fallback is image texture exploration, NOT animal/species detection.
    """
    started = time.perf_counter()
    heavy_enabled = (os.getenv('PANTHERA_ENABLE_HEAVY_IMAGE_AI') == '1'
                     and find_spec('PytorchWildlife') is not None)
    if heavy_enabled:
        try:
            result = detect_image(image, threshold)
            result['rosette_patterns'] = analyze_patterns(image, result.get('detections', []))
            result['animal_detection_performed'] = True
            return result
        except DetectorUnavailable as error:
            logger.warning('MegaDetector unavailable; image texture only: %s', error)

    patterns = analyze_patterns(image, [], allow_full_image=True)
    # The preview is an actual CPU-processed image, not a fake detection.
    preview = patterns['samples'][0]['annotated_crop'] if patterns['samples'] else ''
    return {
        'model': 'Contornos de textura exploratorios (sin detector de animales)',
        'device': 'cpu', 'threshold': threshold,
        'inference_seconds': round(time.perf_counter() - started, 3),
        'counts': {'animal': 0, 'person': 0, 'vehicle': 0},
        'detections': [], 'annotated_image': preview,
        'animal_detection_performed': False,
        'rosette_patterns': patterns,
        'note': (
            'Solo se exploraron regiones anulares de la fotografía. '
            'No se ejecutó IA para detectar animales o determinar especie. '
            'No se confirma ninguna roseta ni identidad.'
        ),
    }

@app.post('/api/images/analyze')
async def analyze_photo(request: Request, threshold: float = Query(0.25, ge=0.1, le=0.9)):
    _, image, _, _ = await _read_image(request)
    try:
        return await run_in_threadpool(_analyze_photo, image, threshold)
    except DetectorUnavailable as error:
        logger.warning('Modelo IA no disponible para fotografías: %s', error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception('Falló el análisis automático de fotografía')
        raise HTTPException(
            status_code=500,
            detail='No se completó el análisis. Revisá la disponibilidad de IA en el servidor.'
        ) from error
