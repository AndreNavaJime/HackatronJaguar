"""Opt-in read-only PantheraEDGE HTTP bridge.

The upstream endpoint URL is set by the deployment operator, never supplied
by a browser request. This avoids exposing an arbitrary-URL fetch/SSRF proxy.
No events are persisted and no Supabase credentials are required.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as URLRequest, urlopen

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/edge", tags=["PantheraEDGE events"])
SIGNATURE_FIELDS = {"signature", "hmac", "hmac_sha256"}
CONTRACT_VERSION = "panthera-v1.0"


def normalize_event(raw: dict) -> dict:
    location = raw.get("location") if isinstance(raw.get("location"), dict) else {}
    environment = raw.get("environment") if isinstance(raw.get("environment"), dict) else {}
    detection = raw.get("detection") if isinstance(raw.get("detection"), dict) else {}
    return {
        "contract_version": raw.get("contract_version") or CONTRACT_VERSION,
        "event_id": raw.get("event_id") or raw.get("id") or "SIN-ID",
        "timestamp": raw.get("timestamp") or raw.get("created_at"),
        "camera_id": raw.get("camera_id") or raw.get("node_id") or "SIN-CAMARA",
        "event": raw.get("event") or raw.get("event_type") or "wildlife_event",
        "status": raw.get("status") or "RECEIVED",
        "transport": raw.get("transport") or raw.get("link") or "HTTP bridge",
        "latitude": raw.get("latitude", location.get("latitude")),
        "longitude": raw.get("longitude", location.get("longitude")),
        "temperature": raw.get("temperature", environment.get("temperature")),
        "humidity": raw.get("humidity", environment.get("humidity")),
        "class": raw.get("class") or detection.get("class") or detection.get("label"),
        "confidence": raw.get("confidence", detection.get("confidence")),
        "image_url": raw.get("image_url") or raw.get("image"),
        "clip_url": raw.get("clip_url") or raw.get("video_url"),
        "hmac_status": "NOT_CHECKED",
        "source": "configured_http_bridge",
    }


def verify_event_signature(raw: dict, secret: str) -> str:
    if not secret:
        return "NOT_CONFIGURED"
    signature = next((str(raw[key]).strip().lower() for key in ("hmac_sha256", "hmac", "signature") if raw.get(key)), "")
    if not signature:
        return "MISSING"
    payload = {key: value for key, value in raw.items() if key not in SIGNATURE_FIELDS}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, default=str).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return "VALID" if hmac.compare_digest(expected, signature) else "INVALID"


@router.get("/bridge")
def get_edge_event():
    upstream = os.environ.get("PANTHERA_EDGE_BRIDGE_URL", "").strip()
    if not upstream:
        return {"configured": False, "event": None,
                "message": "El puente de eventos no está configurado. Usá la demo local."}
    parsed = urlparse(upstream)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=503, detail="PANTHERA_EDGE_BRIDGE_URL debe ser una URL HTTPS válida sin credenciales.")
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        raise HTTPException(status_code=503, detail="No se permiten destinos de loopback.")
    # Operator-configured endpoint only. Production needs network egress policy
    # and upstream auth. URL redirects are disabled to limit unintended hops.
    class NoRedirect(__import__("urllib.request", fromlist=["HTTPRedirectHandler"]).HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None
    opener = __import__("urllib.request", fromlist=["build_opener"]).build_opener(NoRedirect())
    req = URLRequest(upstream, headers={"User-Agent": "PantheraLAB-EDGE/1.0",
                                       "Accept": "application/json"})
    try:
        with opener.open(req, timeout=10) as response:
            if int(response.headers.get("Content-Length", "0")) > 65536:
                raise HTTPException(status_code=502, detail="Respuesta del nodo demasiado grande.")
            payload = response.read(65537)
            if len(payload) > 65536:
                raise HTTPException(status_code=502, detail="Respuesta del nodo demasiado grande.")
            raw = json.loads(payload)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Puente HTTP no disponible: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="El nodo debe devolver un objeto JSON.")
    sig_status = verify_event_signature(raw, os.environ.get("PANTHERA_HMAC_SECRET", "").strip())
    if sig_status in {"MISSING", "INVALID"}:
        raise HTTPException(status_code=403, detail=f"Evento rechazado: HMAC {sig_status}.")
    normalized = normalize_event(raw)
    normalized["hmac_status"] = sig_status
    return {"configured": True, "event": normalized,
            "message": "Evento recibido del endpoint configurado. No almacenado en base de datos."}
