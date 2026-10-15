"""PantheraSENSE simulated IoT ingestion — isolated from wildlife observations.

Authenticated Wokwi DHT22 messages remain optional and are stored in ephemeral
memory. When no recent Wokwi readings exist, the public dashboard generates a
clearly labeled, deterministic CLOUD DEMO on demand, without credentials,
background jobs or persistence. Never confuse synthetic data with field data.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hmac
import math
import os
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from typing import Literal

router = APIRouter(prefix="/api/sense", tags=["PantheraSENSE / simulated IoT"])

MAX_REQUEST_BYTES = 2048
STALE_AFTER_SECONDS = 150
CLOUD_INTERVAL_SECONDS = 30
CLOUD_HISTORY_LENGTH = 12
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
    # Optional digital threshold flag from simulated MQ-2; no fire confirmation.
    gas_alert: bool = False

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


def _cloud_demo_samples(now: datetime) -> list[dict]:
    """Return synthetic 30-second snapshots. No timer, sensor or storage is involved.

    Values are repeatable for the same UTC interval across process restarts.
    They have NO location, calibrated model, field provenance or climatic meaning.
    """
    current_slot = int(now.timestamp() // CLOUD_INTERVAL_SECONDS)
    result = []
    for slot in range(current_slot - CLOUD_HISTORY_LENGTH + 1, current_slot + 1):
        stamp = slot * CLOUD_INTERVAL_SECONDS
        day_phase = 2 * math.pi * ((stamp % 86400) / 86400)
        variation = 2 * math.pi * ((stamp % 2100) / 2100)
        temperature = round(24.0 + 2.3 * math.sin(day_phase) +
                            0.5 * math.sin(variation), 1)
        humidity = round(43.0 - 6.0 * math.sin(day_phase) +
                         1.8 * math.cos(variation), 1)
        result.append({
            "device_id": "PANTHERASENSE-CLOUD-01",
            "project": "PantheraSENSE",
            "simulation": True,
            "temperature_c": temperature,
            "humidity_pct": humidity,
            "reading_number": slot,
            "received_at_utc": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
        })
    return result


@router.get("/latest")
def latest_simulation():
    """Prefer fresh virtual Wokwi telemetry; otherwise show labeled cloud DEMO.

    The cloud data is generated only on GET; no continuous recording, no 24/7
    scheduled task, no replacement for physical measurements or actual 5G.
    """
    now = datetime.now(timezone.utc)
    with _samples_lock:
        samples = list(_samples)
    if samples:
        age = (now - datetime.fromisoformat(samples[-1]["received_at_utc"])).total_seconds()
        if 0 <= age <= STALE_AFTER_SECONDS:
            return {"status": "live", "simulation": True,
                    "source": "wokwi_virtual",
                    "storage": "ephemeral_process_memory",
                    "generated_on_request": False,
                    "latest": samples[-1], "history": samples[-12:]}

    generated = _cloud_demo_samples(now)
    return {"status": "live", "simulation": True,
            "source": "cloud_simulation",
            "storage": "computed_on_demand",
            "generated_on_request": True,
            "latest": generated[-1], "history": generated}
