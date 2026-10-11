"""PantheraID v2: API foundation and image intake. Run from v2/backend."""
import hashlib
import io

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 12 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000

app = FastAPI(title="PantheraID API", version="0.2.0")
# Frontend uses the Vite same-origin proxy during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PantheraID API", "version": "0.2.0"}


@app.get("/api/capabilities")
def capabilities():
    return {
        "modules": ["PantheraID", "PantheraMONITORING", "PantheraEDGE"],
        "image_intake": "available",
        "animal_detection": "not_migrated",
        "individual_identification": "not_validated",
        "video_analysis": "not_migrated",
        "supabase": "not_configured",
        "edge_ingestion": "not_migrated",
    }


@app.post("/api/images/inspect")
async def inspect_image(request: Request):
    """Validate image bytes and return basic file metadata.

    This is NOT animal detection or individual identification.
    Files are processed in memory and never saved by this endpoint.
    """
    image_data = bytearray()
    async for chunk in request.stream():
        image_data.extend(chunk)
        if len(image_data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="La imagen supera el límite de 12 MB.")
    if not image_data:
        raise HTTPException(status_code=400, detail="No se recibió ninguna imagen.")

    content = bytes(image_data)
    try:
        with Image.open(io.BytesIO(content)) as img:
            if img.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Usá JPEG, PNG o WebP.")
            img.load()  # Confirm the image is decodable, not just a header.
            width, height = img.size
            image_format = img.format
            mode = img.mode
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="La imagen no se pudo leer.")

    return {
        "status": "received",
        "format": image_format,
        "width": width,
        "height": height,
        "color_mode": mode,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "saved": False,
        "animal_detection": False,
        "note": "Recepción validada. Todavía no se ha ejecutado MegaDetector ni identificado ningún jaguar.",
    }
