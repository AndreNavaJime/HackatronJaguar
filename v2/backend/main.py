"""PantheraID v2 API — photo intake and optional MegaDetector V6."""
import hashlib
import io
from importlib.util import find_spec

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError

from detection import DetectorUnavailable, detect_image

MAX_IMAGE_BYTES = 12 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000

app = FastAPI(title='PantheraID API', version='0.3.0')
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
    return {'status': 'ok', 'service': 'PantheraID API', 'version': '0.3.0'}


@app.get('/api/capabilities')
def capabilities():
    return {
        'modules': ['PantheraID', 'PantheraMONITORING', 'PantheraEDGE'],
        'image_intake': 'available',
        'animal_detection': 'optional_dependencies_installed' if find_spec('PytorchWildlife') else 'requires_pytorchwildlife',
        'individual_identification': 'not_validated',
        'video_analysis': 'not_migrated',
        'supabase': 'not_configured',
        'edge_ingestion': 'not_migrated',
    }


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
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f'Falló la inferencia de MegaDetector ({type(error).__name__}). Revisá la terminal de Python.') from error
