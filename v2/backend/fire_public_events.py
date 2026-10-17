"""Public NASA EONET wildfire EVENT catalogue for PantheraFIRE.

EONET incident entries are external catalogue reports, NOT active thermal pixels,
automatic fire alarms, local sensor measurements, or evidence of a fire
at any particular camera. This endpoint contains no private camera data.
NASA FIRMS thermal detections require a separate operator MAP_KEY.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock
import json
import time
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/fire", tags=["fire-public-events"])

BASE = "https://eonet.gsfc.nasa.gov/api/v3/events"
REGIONS = {
    "world": None,
    "costa_rica": "-86.1,11.3,-82.3,8.0",
    "central_america": "-93.0,18.0,-77.0,6.0",
    "africa": "-18.0,38.0,52.0,-35.0",
    "asia": "25.0,82.0,180.0,-12.0",
    "europe": "-12.0,72.0,45.0,34.0",
    "north_america": "-170.0,84.0,-50.0,7.0",
    "south_america": "-82.0,13.0,-34.0,-56.0",
    "oceania": "110.0,0.0,180.0,-50.0",
}
LOCK = Lock()
CACHE: dict[tuple[str, int], tuple[float, dict]] = {}
TTL_SECONDS = 900
MAX_RESPONSE = 1_200_000


def _read_public_events(region: str, days: int) -> dict:
    params = {"category": "wildfires", "status": "all", "days": str(days), "limit": "100"}
    if REGIONS[region]:
        params["bbox"] = REGIONS[region]
    url = BASE + "?" + urlencode(params)
    # Fixed origin, fixed path and fixed param names: no arbitrary URL proxy or SSRF.
    request = Request(url, headers={
        "User-Agent": "PantheraLAB-FIRE-research/1.0",
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=10) as response:
            content = response.read(MAX_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=503,
                            detail="No se pudo consultar el catálogo NASA EONET. Reintentá más tarde.") from exc
    if len(content) > MAX_RESPONSE:
        raise HTTPException(status_code=502, detail="La respuesta de NASA excede el límite de seguridad.")
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=502, detail="NASA EONET devolvió datos no interpretables.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise HTTPException(status_code=502, detail="Formato inesperado del catálogo NASA EONET.")
    return data


def _project_events(response: dict, region: str, days: int) -> dict:
    events = []
    for event in response.get("events", []):
        if not isinstance(event, dict):
            continue
        categories = event.get("categories", [])
        if not isinstance(categories, list) or not any(
            isinstance(x, dict) and x.get("id") == "wildfires" for x in categories
        ):
            continue
        event_id = event.get("id")
        title = event.get("title")
        if not isinstance(event_id, str) or not isinstance(title, str):
            continue
        if not event_id or len(event_id) > 128 or not event_id.replace("-", "").replace("_", "").isalnum():
            continue
        sources = event.get("sources", [])
        names = [
            str(x.get("id"))[:55] for x in sources
            if isinstance(x, dict) and isinstance(x.get("id"), str)
        ] if isinstance(sources, list) else []
        geometries = event.get("geometry", [])
        when = None
        if isinstance(geometries, list):
            for item in reversed(geometries):
                if isinstance(item, dict) and isinstance(item.get("date"), str):
                    when = item["date"][:35]
                    break
        closed = event.get("closed")
        events.append({
            "id": event_id,
            "title": title[:190],
            "reported_at": when,
            "open_in_catalogue": closed is None,
            "sources": names[:8],
            "reference_url": BASE + "/" + event_id,
        })
    # NASA may apply LIMIT upstream before regional filtering; do not claim completeness.
    return {
        "source": "NASA EONET API v3",
        "type": "reported_wildfire_events_not_active_fire_detections",
        "region": region,
        "days": days,
        "queried_at_utc": datetime.now(timezone.utc).isoformat(),
        "events": events[:100],
        "count_returned": len(events[:100]),
        "limitations": (
            "NASA EONET catalogues reported natural events; it is not a comprehensive "
            "real-time active-fire detection system. Empty results do NOT prove no fires. "
            "This feed is NOT NASA FIRMS hotspot data, a camera smoke detector, "
            "emergency dispatch, or an automatic safety alert."
        ),
    }


@router.get("/nasa-events")
def nasa_wildfire_events(
    region: Literal["world", "costa_rica", "central_america", "africa", "asia", "europe", "north_america", "south_america", "oceania"] = "central_america",
    days: int = Query(30, ge=7, le=90),
):
    key = (region, days)
    with LOCK:
        previous = CACHE.get(key)
        if previous and time.monotonic() - previous[0] < TTL_SECONDS:
            return previous[1]
    raw = _read_public_events(region, days)
    projected = _project_events(raw, region, days)
    with LOCK:
        CACHE[key] = (time.monotonic(), projected)
    return projected
