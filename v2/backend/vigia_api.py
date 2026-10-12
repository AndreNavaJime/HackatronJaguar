"""Authenticated opt-in VIGÍA (Wokwi ESP32) multipart capture adapter.

The sketch sends cam_id, trigger, ts, lat, lon and a JPEG field named frames.
This prototype acknowledges receipt and keeps *metadata only* in process memory.
It neither stores camera media nor runs MegaDetector or measures a 5G link.
The Wokwi sketch must be updated to send HTTPS with an authentication header.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile

router = APIRouter(prefix="/api/edge/vigia", tags=["VIGÍA node integration"])
MAX_JPEG_BYTES = 12 * 1024 * 1024
MAX_MULTIPART_BYTES = MAX_JPEG_BYTES + 8192
MAX_EVENT_HISTORY = 20
_events: OrderedDict[str, dict] = OrderedDict()
_event_lock = Lock()


def _authorized(request: Request, env_var: str, header: str) -> None:
    expected = os.environ.get(env_var, "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Integración VIGÍA no configurada en el servidor.")
    supplied = request.headers.get(header, "")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Credencial VIGÍA no válida.")


def _field(form: object, name: str, limit: int = 120) -> str:
    value = form.get(name)  # type: ignore[attr-defined]
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="Falta el campo " + name + ".")
    value = value.strip()
    if not value or len(value) > limit:
        raise HTTPException(status_code=422, detail="Campo VIGÍA inválido: " + name + ".")
    return value


def _coord(form: object, name: str, minimum: float, maximum: float) -> float:
    value = _field(form, name, 32)
    try:
        number = float(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Coordenada inválida: " + name + ".") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise HTTPException(status_code=422, detail="Coordenada fuera de rango: " + name + ".")
    return number


@router.get("/status")
def vigia_status():
    """Non-sensitive connection status; never reveals camera locations or tokens."""
    with _event_lock:
        count = len(_events)
    configured = bool(os.environ.get("PANTHERA_VIGIA_INGEST_TOKEN", "").strip())
    return {
        "configured": configured,
        "dashboard_configured": bool(os.environ.get("PANTHERA_VIGIA_DASHBOARD_TOKEN", "").strip()),
        "received_count": count,
        "mode": "metadata_only",
        "message": "Receptor preparado; esperando capturas autenticadas." if configured
                   else "Pendiente de configurar credenciales y adaptar el sketch de VIGÍA.",
    }


@router.get("/latest")
def vigia_latest(request: Request):
    """Sensitive field metadata is visible only with a separate dashboard secret."""
    _authorized(request, "PANTHERA_VIGIA_DASHBOARD_TOKEN", "x-panthera-dashboard-token")
    with _event_lock:
        event = dict(next(reversed(_events.values()))) if _events else None
    return {"event": event, "configured": True,
            "message": "Última captura VIGÍA (solo metadatos)." if event
                       else "Todavía no hay capturas recibidas."}


@router.post("/capture")
async def vigia_capture(request: Request):
    """Accept sketch-compatible form fields; fail closed until a token is set."""
    _authorized(request, "PANTHERA_VIGIA_INGEST_TOKEN", "x-panthera-node-token")
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(status_code=415, detail="VIGÍA debe enviar multipart/form-data.")
    length = request.headers.get("content-length")
    if length is None:
        raise HTTPException(status_code=411, detail="VIGÍA debe indicar Content-Length.")
    try:
        content_length = int(length)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Content-Length inválido.") from exc
    if content_length <= 0 or content_length > MAX_MULTIPART_BYTES:
        raise HTTPException(status_code=413, detail="Captura VIGÍA supera el límite de 12 MiB.")

    async with request.form(max_files=1, max_fields=8) as form:
        camera_id = _field(form, "cam_id")
        trigger = _field(form, "trigger", 40)
        timestamp = _field(form, "ts", 60)
        latitude = _coord(form, "lat", -90, 90)
        longitude = _coord(form, "lon", -180, 180)
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Hora VIGÍA inválida; usar ISO 8601.") from exc

        frame = form.get("frames")
        if not isinstance(frame, UploadFile):
            raise HTTPException(status_code=422, detail="VIGÍA debe incluir el archivo frames.")
        filename = Path((frame.filename or "capture.jpg").replace("\\", "/")).name
        if not filename.lower().endswith((".jpg", ".jpeg")):
            raise HTTPException(status_code=415, detail="VIGÍA solo admite archivos JPG.")
        if frame.content_type not in {"image/jpeg", "application/octet-stream", None}:
            raise HTTPException(status_code=415, detail="Tipo de archivo no admitido.")
        contents = await frame.read(MAX_JPEG_BYTES + 1)
        if len(contents) > MAX_JPEG_BYTES:
            raise HTTPException(status_code=413, detail="JPG mayor a 12 MiB.")
        if len(contents) < 4 or not contents.startswith(b"\xff\xd8\xff"):
            raise HTTPException(status_code=422, detail="No se reconoce la cabecera JPG.")

    # Wokwi creates a placeholder with a JPEG header, not a decodable photograph.
    # Never label this data as a valid image, AI detection, or 5G measurement.
    digest = hashlib.sha256(contents).hexdigest()
    key = hashlib.sha256((camera_id + "\n" + filename + "\n" + digest).encode()).hexdigest()
    event_id = "VIGIA-" + key[:20].upper()
    event = {
        "contract_version": "panthera-v1.0",
        "event_id": event_id,
        "camera_id": camera_id,
        "timestamp": timestamp,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "event": "new_capture",
        "trigger": trigger,
        "status": "RECEIVED_METADATA_ONLY",
        "transport": "Wi-Fi informado por VIGÍA; 5G no verificado",
        "latitude": latitude,
        "longitude": longitude,
        "filename": filename,
        "size_bytes": len(contents),
        "sha256": digest,
        "image_validated": False,
        "analyzed": False,
        "saved": False,
        "source": "vigia_multipart",
        "auth_status": "TOKEN_VERIFIED",
        "hmac_status": "NOT_APPLICABLE",
    }
    with _event_lock:
        duplicate = key in _events
        if not duplicate:
            _events[key] = event
            while len(_events) > MAX_EVENT_HISTORY:
                _events.popitem(last=False)
    return {
        "accepted": True,
        "event_id": event_id,
        "duplicate": duplicate,
        "saved": False,
        "analyzed": False,
        "message": "Captura recibida; solo metadatos. No se ejecutó MegaDetector.",
    }
