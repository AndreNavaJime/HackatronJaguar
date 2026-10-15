"""PantheraSENSE simulated IoT ingestion — isolated from wildlife observations.

Only authenticated, explicitly simulated DHT22 data are accepted. This proof of
concept retains at most 30 samples in this Python process, NOT in a database.
It has no geographic coordinates, photo ingestion, or real 5G claims.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hmac
import os
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from typing import Literal

router = APIRouter(prefix="/api/sense", tags=["PantheraSENSE / simulated IoT"])

MAX_REQUEST_BYTES = 2048
STALE_AFTER_SECONDS = 150
_samples: deque[dict] = deque(maxlen=30)
_samples_lock = Lock()


class SimulatedReading(BaseModel):
    device_id: str = Field(pattern=r"^PANTHERASENSE-[0-9]{2,3}$", max_length=32)
    project: Literal["PantheraSENSE"]
    simulation: Literal[True]
    temperature_c: float = Field(ge=-40, le=85, allow_inf_nan=False)
    humidity_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    uptime_s: int = Field(ge=0, le=31536000)
    reading_number: int = Field(ge=1, le=2000000000)

    class Config:
        extra = "forbid"


@router.post("/ingest", status_code=202)
async def ingest_simulation(request: Request):
    """Require per-deployment secret; fail closed if not configured in Render."""
    secret = os.getenv("PANTHERASENSE_INGEST_KEY", "")
    if len(secret) < 16:
        raise HTTPException(503, "Recepción IoT no habilitada: falta clave de servidor.")

    provided = request.headers.get("X-PantheraSense-Key", "")
    if not provided or not hmac.compare_digest(provided, secret):
        raise HTTPException(401, "Credenciales IoT inválidas.")

    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Medición demasiado grande.")

    try:
        reading = SimulatedReading.model_validate_json(bytes(raw))
    except (ValidationError, ValueError):
        raise HTTPException(422, "JSON de medición simulada inválido.") from None

    received_at = datetime.now(timezone.utc).isoformat()
    sample = dict(reading.model_dump())
    sample["received_at_utc"] = received_at
    with _samples_lock:
        _samples.append(sample)
    return {"accepted": True, "device_id": sample["device_id"],
            "received_at_utc": received_at, "storage": "ephemeral_process_memory"}


@router.get("/latest")
def latest_simulation():
    """Public read-only preview: explicitly simulated values, never sensitive data."""
    with _samples_lock:
        samples = list(_samples)
    if not samples:
        return {"status": "waiting", "simulation": True,
                "storage": "ephemeral_process_memory", "latest": None, "history": []}

    sample = samples[-1]
    age = (datetime.now(timezone.utc) -
           datetime.fromisoformat(sample["received_at_utc"])).total_seconds()
    return {"status": "live" if age <= STALE_AFTER_SECONDS else "stale",
            "simulation": True, "storage": "ephemeral_process_memory",
            "latest": sample, "history": samples[-12:]}
