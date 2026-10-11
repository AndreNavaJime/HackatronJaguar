# -*- coding: utf-8 -*-

"""
=========================================================
PANTHERA LAB · PANTHERAEDGE
CLOUD MONITORING & SCIENTIFIC REVIEW · HACKATRON 5G
=========================================================

REFERENCE ARCHITECTURE (aligned with the Panthera Lab system diagram)

FIELD / SENSES
PantheraCAM + camera traps + FIREWATCH / virtual sensors
    ↓  Wi-Fi 2.4 GHz / LoRa (low-cost last mile)
PANTHERAEDGE / LOCAL REFLEX
MegaDetector V6 + sensor fusion + configurable event threshold
Offline queue + local beacon / alert + MQTT/HTTP bridge
    ↓  filtered event evidence
5G TRUNK
CPE / radio / 5G core (4G or satellite fallback when required)
    ↓
PANTHERA LAB CLOUD / BRAIN
Cloud ingest + optional Panthera Contract v1.0 HMAC validation
Storage / database + PantheraID + PantheraMONITORING
    ↓
INSTITUTIONAL OUTPUTS
SINAC / researchers / guardaparques / emergency-response integrations

THIS STREAMLIT APPLICATION IS THE PANTHERAEDGE SCIENTIFIC WORKSPACE.
It includes a local MegaDetector demonstration and a preview of downstream
cloud monitoring/institutional reporting. It does not replace the physical
field Edge hardware, PantheraID identification model or monitoring dashboard.

IMPORTANT SCIENTIFIC LIMITS

MegaDetector:
- Detects animal / person / vehicle
- DOES NOT identify species
- DOES NOT identify individual animals

Species and individual IDs are researcher annotations unless validated
PantheraID/downstream models are later integrated.

Detection-confidence statistics describe behavior within the analyzed
material. They DO NOT constitute external validation, accuracy estimates,
calibration evidence, generalization evidence or evidence against overfitting.

Network metrics are reference estimates unless explicitly entered as measured
testbed values. They must not be presented as live 5G measurements otherwise.

The Sentinel section queries real Copernicus catalogue metadata. It does NOT
by itself infer forest loss, NDVI, flooding, habitat change or ecological causality.
=========================================================
"""

# =========================================================
# IMPORTS
# =========================================================

import io
import json
import math
import hashlib
import hmac
import os
import re
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st
import torch

from PIL import Image as PILImage


try:
    from PytorchWildlife.models import detection as pw_detection
    PYTORCHWILDLIFE_IMPORT_ERROR = None
except Exception as _pytorchwildlife_import_error:
    pw_detection = None
    PYTORCHWILDLIFE_IMPORT_ERROR = str(_pytorchwildlife_import_error)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as PDFImage,
    PageBreak,
)

# =========================================================
# PANTHERAID / SUPABASE DATA EXCHANGE
# =========================================================

PANTHERA_SUPABASE_URL = "https://ektzomyqcmbcvfrlccrn.supabase.co"
PANTHERA_TABLE_NAME = "pantheraid-monitoring"
PANTHERA_REST_ROOT = PANTHERA_SUPABASE_URL + "/rest/v1/"
PANTHERA_TABLE_ENDPOINT = PANTHERA_REST_ROOT + PANTHERA_TABLE_NAME

PANTHERA_CONTRACT_VERSION = "panthera-v1.0"
PANTHERA_EVENT_SIGNATURE_FIELDS = {"signature", "hmac", "hmac_sha256"}

# Confirmed from the PantheraID Supabase table editor (2026-10-07).
# id and created_at are database-managed and are intentionally not sent.
PANTHERA_CONFIRMED_COLUMNS = [
    "numero_detection",
    "latitude",
    "longitude",
    "temperature",
    "humidity",
    "type_identify",
    "species",
    "image_url",
    "altitude",
]

PANTHERA_STORAGE_BUCKET = "capturas-animales"
PANTHERA_STORAGE_UPLOAD_BASE = (
    PANTHERA_SUPABASE_URL
    + f"/storage/v1/object/{PANTHERA_STORAGE_BUCKET}"
)
PANTHERA_STORAGE_PUBLIC_BASE = (
    PANTHERA_SUPABASE_URL
    + f"/storage/v1/object/public/{PANTHERA_STORAGE_BUCKET}"
)


def get_panthera_supabase_key():
    """
    Read the public Supabase key from Streamlit Secrets.
    The key is intentionally NOT hard-coded in this source file.
    """
    for secret_name in (
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_ANON_KEY",
        "PANTHERA_SUPABASE_KEY",
    ):
        try:
            value = st.secrets.get(secret_name)
        except Exception:
            value = None
        if value:
            return str(value).strip()
    return None


def panthera_headers(prefer_return=True):
    key = get_panthera_supabase_key()
    if not key:
        raise RuntimeError(
            "Supabase key not configured. Add SUPABASE_PUBLISHABLE_KEY "
            "to Streamlit Secrets before transmitting records."
        )

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }

    if prefer_return:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal"

    return headers


@st.cache_data(ttl=300, show_spinner=False)
def get_pantheraid_schema_info():
    """
    Discover the PantheraID PostgREST schema exposed by Supabase.

    Returns a dictionary with the detected table columns when the OpenAPI
    document is available. Failure to inspect the schema does not disable
    transmission; it only disables pre-flight column filtering.
    """
    key = get_panthera_supabase_key()
    if not key:
        return {"available": False, "columns": [], "error": "Supabase key is not configured."}

    try:
        response = requests.get(
            PANTHERA_REST_ROOT,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/openapi+json",
            },
            timeout=15,
        )
        response.raise_for_status()
        document = response.json()

        definitions = document.get("definitions", {})
        table_definition = definitions.get(PANTHERA_TABLE_NAME)

        # Some PostgREST/OpenAPI versions expose schemas under components/schemas.
        if table_definition is None:
            table_definition = (
                document.get("components", {})
                .get("schemas", {})
                .get(PANTHERA_TABLE_NAME)
            )

        properties = (table_definition or {}).get("properties", {})
        columns = list(properties.keys())

        if not columns:
            return {
                "available": True,
                "columns": PANTHERA_CONFIRMED_COLUMNS.copy(),
                "error": None,
                "source": "owner-confirmed",
            }

        return {
            "available": True,
            "columns": columns,
            "error": None,
            "source": "openapi",
        }
    except Exception as error:
        # OpenAPI introspection can be hidden by Supabase/RLS configuration.
        # The PantheraID owner supplied the exact table structure, so use that
        # confirmed schema rather than guessing field names.
        return {
            "available": True,
            "columns": PANTHERA_CONFIRMED_COLUMNS.copy(),
            "error": str(error),
            "source": "owner-confirmed",
        }


def filter_pantheraid_payload(payload, schema_info):
    """Keep only fields that exist in the live PantheraID table schema."""
    if not schema_info or not schema_info.get("available"):
        return payload.copy(), []

    allowed = set(schema_info.get("columns", []))
    filtered = {key: value for key, value in payload.items() if key in allowed}
    ignored = [key for key in payload if key not in allowed]
    return filtered, ignored


def upload_full_frame_to_supabase(image_bytes, object_path):
    """
    Upload one complete retained frame to the public Supabase Storage bucket.
    Returns the public URL generated from the bucket/object path.
    """
    clean_path = str(object_path).lstrip("/")
    upload_url = f"{PANTHERA_STORAGE_UPLOAD_BASE}/{clean_path}"

    headers = panthera_headers(prefer_return=False)
    headers["Content-Type"] = "image/jpeg"
    headers["x-upsert"] = "false"

    response = requests.post(
        upload_url,
        data=image_bytes,
        headers=headers,
        timeout=30,
    )

    # If the exact object already exists, keep using its public URL.
    # Supabase commonly returns 400/409 for an existing object depending on API version.
    if response.status_code not in (200, 201, 400, 409):
        raise RuntimeError(
            f"Supabase Storage error {response.status_code}: {response.text}"
        )

    if response.status_code in (400, 409):
        detail = response.text.lower()
        if "exist" not in detail and "duplicate" not in detail:
            raise RuntimeError(
                f"Supabase Storage error {response.status_code}: {response.text}"
            )

    return f"{PANTHERA_STORAGE_PUBLIC_BASE}/{clean_path}"



def panthera_storage_object_path(image_url):
    """Return the bucket-relative object path from a PantheraID public Storage URL."""
    prefix = PANTHERA_STORAGE_PUBLIC_BASE.rstrip("/") + "/"
    value = str(image_url or "").strip()
    if not value.startswith(prefix):
        return None
    from urllib.parse import unquote
    return unquote(value[len(prefix):])


def delete_pantheraid_record(numero_detection, image_url):
    """
    Delete one PantheraID row using both numero_detection and image_url.
    Using both filters is safer than numero_detection alone because the latter
    is not the primary key in the shared table.
    """
    response = requests.delete(
        PANTHERA_TABLE_ENDPOINT,
        params={
            "numero_detection": f"eq.{int(numero_detection)}",
            "image_url": f"eq.{str(image_url)}",
        },
        headers=panthera_headers(prefer_return=True),
        timeout=20,
    )

    if not response.ok:
        detail = response.text
        detail_lower = detail.lower()
        if (
            response.status_code in (401, 403)
            or "row-level security" in detail_lower
            or "permission denied" in detail_lower
        ):
            raise RuntimeError(
                "PantheraID DELETE was blocked by Supabase permissions/RLS. "
                "The table owner must allow DELETE for the publishable/anon role. "
                f"Database response {response.status_code}: {detail}"
            )
        raise RuntimeError(
            f"PantheraID DELETE error {response.status_code}: {detail}"
        )

    return response.status_code


def delete_panthera_storage_object(image_url):
    """Delete one image from the PantheraID Storage bucket through the Storage API."""
    object_path = panthera_storage_object_path(image_url)
    if not object_path:
        raise RuntimeError("Could not derive the Storage object path from image_url.")

    delete_url = f"{PANTHERA_STORAGE_UPLOAD_BASE}/{object_path}"
    response = requests.delete(
        delete_url,
        headers=panthera_headers(prefer_return=False),
        timeout=20,
    )

    if not response.ok:
        detail = response.text
        detail_lower = detail.lower()
        if (
            response.status_code in (401, 403)
            or "row-level security" in detail_lower
            or "permission denied" in detail_lower
        ):
            raise RuntimeError(
                "Storage DELETE was blocked by Supabase permissions/RLS. "
                "The bucket owner must allow DELETE on storage.objects for this role. "
                f"Storage response {response.status_code}: {detail}"
            )
        raise RuntimeError(
            f"Supabase Storage DELETE error {response.status_code}: {detail}"
        )

    return response.status_code


def insert_pantheraid_record(payload):
    """
    Insert one record into the PantheraID monitoring table.
    Field names intentionally preserve the exact case supplied by PantheraID.
    """
    response = requests.post(
        PANTHERA_TABLE_ENDPOINT,
        json=payload,
        headers=panthera_headers(prefer_return=True),
        timeout=20,
    )
    if not response.ok:
        detail = response.text
        detail_lower = detail.lower()

        if (
            response.status_code in (401, 403)
            or "row-level security" in detail_lower
            or "rls" in detail_lower
            or "permission denied" in detail_lower
        ):
            raise RuntimeError(
                "PantheraID INSERT was blocked by Supabase permissions/RLS. "
                "The table owner must allow INSERT for the anon/publishable role. "
                f"Database response {response.status_code}: {detail}"
            )

        raise RuntimeError(
            f"PantheraID table error {response.status_code}: {detail}"
        )
    return response.status_code


def next_panthera_detection_number():
    """
    Prefer a database-derived consecutive number when SELECT is permitted.
    If the public policy allows INSERT only, fall back to a session-local counter.
    """
    key = get_panthera_supabase_key()
    if key:
        try:
            response = requests.get(
                PANTHERA_TABLE_ENDPOINT,
                params={
                    "select": "numero_detection",
                    "order": "numero_detection.desc",
                    "limit": 1,
                },
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                },
                timeout=12,
            )
            if response.ok:
                rows = response.json()
                if rows:
                    current = int(rows[0].get("numero_detection") or 0)
                    st.session_state.pantheraid_detection_counter = max(
                        int(st.session_state.get("pantheraid_detection_counter", 1)),
                        current + 1,
                    )
        except Exception:
            pass

    value = int(st.session_state.get("pantheraid_detection_counter", 1))
    st.session_state.pantheraid_detection_counter = value + 1
    return value


def build_pantheraid_payload(
    numero_detection,
    latitude,
    longitude,
    altitude,
    temperature,
    humidity,
    image_url,
    species=None,
):
    return {
        "numero_detection": int(numero_detection),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "temperature": float(temperature) if temperature is not None else None,
        "humidity": float(humidity) if humidity is not None else None,
        "type_identify": "animal",
        "species": species,
        "image_url": str(image_url),
        "altitude": float(altitude) if altitude is not None else None,
    }


# =========================================================
# STREAMLIT CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="PantheraEDGE | Panthera Lab",
    page_icon="🐆",
    layout="wide",
)

# =========================================================
# GLOBAL VISUAL SYSTEM
# =========================================================

st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: "Civis","Source Sans 3","Source Sans Pro","Segoe UI",Arial,sans-serif;
    }
    .block-container {max-width: 1380px; padding-top: 1.25rem; padding-bottom: 3rem;}
    h1 {font-size: 2.25rem !important; font-weight: 650 !important; letter-spacing: -0.035em;}
    h2 {font-size: 1.35rem !important; font-weight: 620 !important; letter-spacing: -0.02em; margin-top: 1.5rem !important;}
    h3 {font-weight: 600 !important; letter-spacing: -0.01em;}
    p {line-height: 1.55;}
    div[data-testid="stMetric"] {
        border: 1px solid rgba(110,110,110,0.22);
        border-radius: 7px;
        padding: 0.70rem 0.85rem;
        background: rgba(120,120,120,0.025);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.75rem; letter-spacing: 0.035em; text-transform: uppercase; opacity: 0.70;
    }
    div[data-testid="stMetricValue"] {font-size: 1.45rem; font-weight: 600;}

    /* Primary scientific actions */
    div.stButton > button[kind="primary"],
    div.stDownloadButton > button[kind="primary"] {
        font-weight: 650;
        border-radius: 7px;
        min-height: 2.65rem;
    }

    /* Secondary actions remain visually lighter */
    div.stButton > button:not([kind="primary"]),
    div.stDownloadButton > button:not([kind="primary"]) {
        border-radius: 7px;
    }

    .registry-danger-note {
        font-size: 0.78rem;
        opacity: 0.68;
        margin-top: 0.35rem;
        margin-bottom: 0.65rem;
    }
    .jaguarid-kicker {
        font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.17em; opacity: 0.58; margin-bottom: 0.35rem;
    }
    .jaguarid-subtitle {max-width: 900px; font-size: 1rem; opacity: 0.80; line-height: 1.55;}
    .technical-strip {
        margin-top: 0.75rem; margin-bottom: 1.6rem; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.09em; opacity: 0.55;
    }
    .section-intro {
        max-width: 980px; font-size: 0.90rem; opacity: 0.72; line-height: 1.55; margin-bottom: 1rem;
    }
    .scientific-note {
        border-left: 3px solid rgba(90,90,90,0.7); padding: 0.8rem 1rem;
        background: rgba(120,120,120,0.045); font-size: 0.88rem; line-height: 1.55;
        margin-top: 0.8rem; margin-bottom: 1.2rem;
    }
    .workflow-container {margin-top: 0.8rem; border-top: 1px solid rgba(120,120,120,0.18);}
    .workflow-row {
        display: grid; grid-template-columns: 70px minmax(160px,230px) 1fr; gap: 1rem;
        align-items: start; padding: 0.85rem 0; border-bottom: 1px solid rgba(120,120,120,0.18);
    }
    .workflow-number {font-size: 0.72rem; letter-spacing: 0.11em; opacity: 0.48;}
    .workflow-title {font-weight: 620; font-size: 0.94rem;}
    .workflow-description {opacity: 0.72; font-size: 0.87rem; line-height: 1.45;}
    .interpretation-box, .method-box {
        padding: 1rem 1.1rem; border: 1px solid rgba(120,120,120,0.22);
        border-radius: 7px; background: rgba(120,120,120,0.025); line-height: 1.55;
    }
    @media (max-width: 700px) {
        .workflow-row {grid-template-columns: 45px 1fr;}
        .workflow-description {grid-column: 2;}
    }

    .brand-panel {
        margin: 1.0rem 0 1.9rem 0;
        padding: 0.95rem 0.4rem 0.55rem 0.4rem;
        border: 0;
        border-top: 1px solid rgba(110,110,110,0.12);
        border-bottom: 1px solid rgba(110,110,110,0.12);
        background: transparent;
    }

    .brand-panel-label {
        text-align: center;
        font-size: 0.72rem;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        opacity: 0.52;
        margin-bottom: 1.0rem;
    }

    .brand-row {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: center;
        gap: 1.8rem;
    }

    .brand-logo-card,
    .brand-vector-card {
        min-height: 58px;
        min-width: 150px;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0.35rem 0.55rem;
        border: 0;
        background: transparent;
        box-sizing: border-box;
        color: rgba(80,80,80,0.72);
    }

    .brand-logo-card.cqu {min-width: 225px;}
    .brand-logo-card.copernicus {min-width: 210px;}
    .brand-logo-card.sentinel-logo {min-width: 150px;}

    .brand-logo-card img {
        display: block;
        width: auto;
        max-width: 100%;
        height: 43px;
        object-fit: contain;
        filter: grayscale(100%);
        opacity: 0.62;
        transition: opacity 0.18s ease;
    }

    .brand-logo-card:hover img {opacity: 0.82;}

    .brand-logo-card.cqu img {height: 45px;}
    .brand-logo-card.copernicus img {height: 43px;}
    .brand-logo-card.sentinel-logo img {height: 42px;}

    .brand-vector-card {
        gap: 0.55rem;
        opacity: 0.72;
    }

    .brand-symbol {
        font-weight: 720;
        font-size: 1.22rem;
        letter-spacing: -0.025em;
        line-height: 1;
        white-space: nowrap;
        color: rgba(70,70,70,0.78);
    }

    .brand-meta {
        display: flex;
        flex-direction: column;
        line-height: 1.12;
        white-space: nowrap;
    }

    .brand-meta strong {
        font-size: 0.70rem;
        font-weight: 650;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }

    .brand-meta span {
        font-size: 0.64rem;
        opacity: 0.68;
        margin-top: 0.2rem;
    }

    .brand-disclaimer {
        margin-top: 0.8rem;
        text-align: center;
        font-size: 0.66rem;
        line-height: 1.4;
        opacity: 0.42;
    }

    @media (prefers-color-scheme: dark) {
        .brand-logo-card img {
            filter: grayscale(100%) brightness(1.55);
            opacity: 0.72;
        }
        .brand-vector-card, .brand-symbol {color: rgba(225,225,225,0.72);}
    }

    @media (max-width: 700px) {
        .brand-row {gap: 0.65rem;}
        .brand-logo-card,
        .brand-vector-card {
            min-width: 46%;
            flex: 1 1 46%;
        }
        .brand-logo-card img {height: 38px;}
    }


    .architecture-ribbon {
        display: grid;
        grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr auto 1fr;
        gap: 0.55rem;
        align-items: stretch;
        margin: 1.0rem 0 1.35rem 0;
    }
    .architecture-step {
        border: 1px solid rgba(110,110,110,0.22);
        border-radius: 9px;
        padding: 0.75rem 0.8rem;
        background: rgba(120,120,120,0.025);
        min-height: 82px;
    }
    .architecture-step.blue {
        border-color: rgba(45,118,190,0.42);
        background: rgba(45,118,190,0.055);
    }
    .architecture-step .num {
        font-size: 0.64rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        opacity: 0.52;
    }
    .architecture-step strong {display:block; margin-top:0.28rem; font-size:0.90rem;}
    .architecture-step span {display:block; margin-top:0.28rem; font-size:0.72rem; opacity:0.66; line-height:1.35;}
    .architecture-arrow {display:flex; align-items:center; justify-content:center; opacity:0.38; font-size:1.15rem;}
    .contract-badge {
        display:inline-block; padding:0.22rem 0.48rem; border:1px solid rgba(110,110,110,0.24);
        border-radius:999px; font-size:0.68rem; letter-spacing:0.04em; opacity:0.72; margin-right:0.35rem;
    }
    @media (max-width: 950px) {
        .architecture-ribbon {grid-template-columns: 1fr;}
        .architecture-arrow {transform: rotate(90deg); min-height: 18px;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# LANGUAGE / IDIOMA
# =========================================================

language_choice = st.sidebar.radio(
    "Language / Idioma",
    ["English", "Español"],
    horizontal=True,
    index=1,
    key="jaguarid_language",
)
UI_LANGUAGE = "es" if language_choice == "Español" else "en"


def T(english, spanish):
    """Return a UI label in the language selected by the user."""
    return spanish if UI_LANGUAGE == "es" else english


# =========================================================
# SESSION STATE
# =========================================================

DEFAULT_STATE = {
    "observation_registry": [],
    "analysis_result": None,
    "current_uploaded_file": None,
    "edge_node_events": [],
    "latest_edge_event": None,
    "satellite_result": None,
    "satellite_query_signature": None,
    "event_datetime_utc": None,
    "temperature_c": None,
    "humidity_percent": None,
    "sex": "unknown",
    "age_class": "unknown",
    "viewpoint": "unknown",
    "behavior": "",
    "habitat_notes": "",
    "image_url": "",
    "video_url": "",
    "validation_status": "researcher_review_pending",
    "altitude_m": None,
    "pantheraid_detection_counter": 1,
    "pantheraid_transmission_log": [],
    "pantheraid_delete_notice": None,
    "manual_observation_id": "OBS-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper(),
    "current_uploaded_image": None,
    "camera_latitude": 9.7489,
    "camera_longitude": -83.7534,
    "latest_hmac_status": "NOT_CHECKED",
    "latest_event_contract": PANTHERA_CONTRACT_VERSION,
    "network_metric_source": "reference",
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

# =========================================================
# GENERAL HELPERS
# =========================================================

def safe_filename(text):
    text = str(text).strip()
    if not text:
        return "PantheraMONITORING_Observation"
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return text or "PantheraMONITORING_Observation"


def escape_pdf_text(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def image_to_png_bytes(rgb_image):
    bgr_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    success, encoded = cv2.imencode(".png", bgr_image)
    return encoded.tobytes() if success else None


def figure_to_png_bytes(figure, dpi=600):
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    buffer.seek(0)
    return buffer.getvalue()


def create_candidates_zip(observation_id, candidate_images):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, candidate in enumerate(candidate_images, start=1):
            png_data = image_to_png_bytes(candidate["image"])
            if png_data is None:
                continue
            time_string = f"{candidate['time']:.1f}".replace(".", "_")
            filename = (
                f"{safe_filename(observation_id)}"
                f"_candidate_{index:03d}_t{time_string}s.png"
            )
            archive.writestr(filename, png_data)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def confidence_statistics(candidate_images, total_samples, frames_kept):
    confidence_values = [float(x["confidence"]) for x in candidate_images]

    if not confidence_values:
        return {
            "count": 0,
            "maximum": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "minimum": 0.0,
            "std": 0.0,
            "range": 0.0,
            "positive_frame_rate": 0.0,
        }

    series = pd.Series(confidence_values, dtype="float64")
    maximum = float(series.max())
    minimum = float(series.min())

    return {
        "count": len(confidence_values),
        "maximum": maximum,
        "mean": float(series.mean()),
        "median": float(series.median()),
        "minimum": minimum,
        "std": float(series.std(ddof=0)),
        "range": maximum - minimum,
        "positive_frame_rate": (frames_kept / total_samples * 100) if total_samples else 0.0,
    }


# =========================================================
# COPERNICUS / EDGE / NETWORK HELPERS
# =========================================================

COPERNICUS_STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"


def radius_bbox(latitude, longitude, radius_km):
    latitude = float(latitude)
    longitude = float(longitude)
    radius_km = float(radius_km)

    lat_delta = radius_km / 111.32
    cos_lat = max(math.cos(math.radians(latitude)), 0.01)
    lon_delta = radius_km / (111.32 * cos_lat)

    return [
        longitude - lon_delta,
        latitude - lat_delta,
        longitude + lon_delta,
        latitude + lat_delta,
    ]


@st.cache_data(ttl=900, show_spinner=False)
def search_copernicus_stac(
    latitude,
    longitude,
    radius_km,
    days_back,
    max_cloud_cover,
):
    """
    Public metadata query to the Copernicus Data Space STAC catalogue.
    No authentication is required for catalogue discovery.
    """
    bbox = radius_bbox(latitude, longitude, radius_km)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=int(days_back))
    datetime_range = (
        start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        + "/"
        + end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    results = {
        "sentinel_1": [],
        "sentinel_2": [],
        "bbox": bbox,
        "queried_at": end_time.isoformat(),
        "error": None,
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "PantheraLAB-Hackatron5G/1.0",
    }

    sentinel_1_payload = {
        "collections": ["sentinel-1-grd"],
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": 10,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }

    sentinel_2_payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": 10,
        "query": {"eo:cloud_cover": {"lte": float(max_cloud_cover)}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }

    try:
        response_1 = requests.post(
            COPERNICUS_STAC_URL,
            json=sentinel_1_payload,
            headers=headers,
            timeout=20,
        )
        response_1.raise_for_status()
        results["sentinel_1"] = response_1.json().get("features", [])

        response_2 = requests.post(
            COPERNICUS_STAC_URL,
            json=sentinel_2_payload,
            headers=headers,
            timeout=20,
        )
        response_2.raise_for_status()
        results["sentinel_2"] = response_2.json().get("features", [])

    except Exception as error:
        results["error"] = str(error)

    return results


def latest_satellite_summary(items):
    if not items:
        return None

    item = items[0]
    props = item.get("properties", {})

    return {
        "id": item.get("id", "Unknown"),
        "datetime": props.get("datetime", "Unknown"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "platform": props.get("platform", props.get("constellation", "Unknown")),
        "orbit_state": props.get("sat:orbit_state", "Unknown"),
    }


def satellite_items_dataframe(items, sensor_name):
    rows = []
    for item in items:
        props = item.get("properties", {})
        rows.append(
            {
                "sensor": sensor_name,
                "product_id": item.get("id", "Unknown"),
                "acquisition": props.get("datetime", "Unknown"),
                "cloud_cover": props.get("eo:cloud_cover"),
                "platform": props.get("platform", props.get("constellation", "Unknown")),
                "orbit_state": props.get("sat:orbit_state", "Unknown"),
            }
        )
    return pd.DataFrame(rows)


def estimate_network_transmission(payload_mb, throughput_mbps, latency_ms):
    payload_mb = max(float(payload_mb), 0.0)
    throughput_mbps = max(float(throughput_mbps), 0.001)
    latency_ms = max(float(latency_ms), 0.0)

    transfer_seconds = (payload_mb * 8.0) / throughput_mbps
    latency_seconds = latency_ms / 1000.0

    return {
        "payload_mb": payload_mb,
        "throughput_mbps": throughput_mbps,
        "latency_ms": latency_ms,
        "transfer_seconds": transfer_seconds,
        "estimated_total_seconds": transfer_seconds + latency_seconds,
    }


def create_simulated_edge_event(camera_id, latitude, longitude):
    timestamp = datetime.now(timezone.utc)

    return {
        "contract_version": PANTHERA_CONTRACT_VERSION,
        "event_id": "EDGE-" + uuid.uuid4().hex[:8].upper(),
        "timestamp": timestamp.isoformat(),
        "camera_id": camera_id.strip() or "CAMERA-UNASSIGNED",
        "event": "new_capture",
        "source": "PantheraCAM local simulator",
        "stage": "field_capture",
        "transport": "Wi-Fi 2.4 / LoRa demo",
        "wifi_status": "CONNECTED",
        "wifi_rssi_dbm": -61,
        "sd_status": "READY",
        "latitude": float(latitude),
        "longitude": float(longitude),
        "status": "RECEIVED",
        "hmac_status": "NOT_CHECKED",
    }


def get_remote_edge_event(endpoint_url):
    endpoint_url = endpoint_url.strip()

    if not endpoint_url:
        raise ValueError("Remote Edge endpoint is empty.")

    response = requests.get(
        endpoint_url,
        timeout=10,
        headers={"User-Agent": "PantheraLAB-Monitoring/1.0"},
    )
    response.raise_for_status()
    return response.json()


def get_panthera_hmac_secret():
    """Optional shared secret used by the PantheraEDGE -> Cloud ingest contract."""
    try:
        value = st.secrets.get("PANTHERA_HMAC_SECRET")
    except Exception:
        value = None
    return str(value).strip() if value else None


def canonical_panthera_event_bytes(event):
    """Canonical JSON bytes used for prototype HMAC-SHA256 verification."""
    clean_event = {
        key: value
        for key, value in dict(event or {}).items()
        if key not in PANTHERA_EVENT_SIGNATURE_FIELDS
    }
    return json.dumps(
        clean_event,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def verify_panthera_event_hmac(event):
    """
    Verify a hex HMAC-SHA256 signature when the shared secret is configured.
    For the hackathon prototype, unsigned events remain usable only when no
    PANTHERA_HMAC_SECRET has been configured.
    """
    secret = get_panthera_hmac_secret()
    signature = None
    for field in ("hmac_sha256", "hmac", "signature"):
        if event.get(field):
            signature = str(event.get(field)).strip().lower()
            break

    if not secret:
        return "NOT_CONFIGURED", True
    if not signature:
        return "MISSING", False

    expected = hmac.new(
        secret.encode("utf-8"),
        canonical_panthera_event_bytes(event),
        hashlib.sha256,
    ).hexdigest().lower()

    is_valid = hmac.compare_digest(signature, expected)
    return ("VALID" if is_valid else "INVALID"), is_valid


def normalize_panthera_edge_event(event):
    """Normalize common PantheraEDGE event fields without inventing missing data."""
    source = dict(event or {})
    location = source.get("location") if isinstance(source.get("location"), dict) else {}
    environment = source.get("environment") if isinstance(source.get("environment"), dict) else {}
    detection = source.get("detection") if isinstance(source.get("detection"), dict) else {}

    return {
        **source,
        "contract_version": source.get("contract_version") or PANTHERA_CONTRACT_VERSION,
        "event_id": source.get("event_id") or source.get("id") or "EDGE-UNASSIGNED",
        "timestamp": source.get("timestamp") or source.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "camera_id": source.get("camera_id") or source.get("node_id") or "CAMERA-UNASSIGNED",
        "event": source.get("event") or source.get("event_type") or "wildlife_event",
        "status": source.get("status") or "RECEIVED",
        "latitude": source.get("latitude", location.get("latitude")),
        "longitude": source.get("longitude", location.get("longitude")),
        "altitude": source.get("altitude", location.get("altitude")),
        "temperature": source.get("temperature", environment.get("temperature")),
        "humidity": source.get("humidity", environment.get("humidity")),
        "class": source.get("class") or detection.get("class") or detection.get("label"),
        "confidence": source.get("confidence", detection.get("confidence")),
        "image_url": source.get("image_url") or source.get("image"),
        "clip_url": source.get("clip_url") or source.get("video_url"),
        "transport": source.get("transport") or source.get("link") or "HTTP/MQTT bridge",
    }


def build_observation_geojson(observation):
    """Create a compact GeoJSON Feature for institutional / GIS interchange."""
    lon = observation.get("camera_longitude")
    lat = observation.get("camera_latitude")
    geometry = None
    if lon is not None and lat is not None:
        geometry = {"type": "Point", "coordinates": [float(lon), float(lat)]}

    properties = {
        "observation_id": observation.get("observation_id"),
        "camera_id": observation.get("camera_id"),
        "study_site": observation.get("study_site"),
        "organization": observation.get("organization"),
        "project_code": observation.get("project_code"),
        "sampling_protocol": observation.get("sampling_protocol"),
        "camera_nights": observation.get("camera_nights"),
        "identification_method": observation.get("identification_method"),
        "evidence_quality": observation.get("evidence_quality"),
        "environmental_source": observation.get("environmental_source"),
        "event_datetime_utc": observation.get("event_datetime_utc"),
        "species": observation.get("species"),
        "individual_id": observation.get("individual_id"),
        "validation_status": observation.get("validation_status"),
        "temperature_c": observation.get("temperature_c"),
        "humidity_percent": observation.get("humidity_percent"),
        "altitude_m": observation.get("altitude_m"),
        "image_url": observation.get("image_url"),
        "video_url": observation.get("video_url"),
        "edge_event_id": observation.get("edge_event_id"),
    }
    return {"type": "Feature", "geometry": geometry, "properties": properties}


# =========================================================
# MATPLOTLIB SCIENTIFIC SETTINGS
# =========================================================

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [
            "Civis",
            "Source Sans 3",
            "Source Sans Pro",
            "DejaVu Sans",
            "Arial",
        ],
        "font.size": 9,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "axes.linewidth": 0.7,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 8.5,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    }
)

CIVIDIS = plt.get_cmap("cividis")
CIVIDIS_DARK = CIVIDIS(0.15)
CIVIDIS_MID = CIVIDIS(0.48)
CIVIDIS_LIGHT = CIVIDIS(0.82)

# =========================================================
# MEGADETECTOR
# =========================================================

@st.cache_resource
def load_model():
    if pw_detection is None:
        raise RuntimeError(
            "PytorchWildlife could not be imported in this environment. "
            f"Import detail: {PYTORCHWILDLIFE_IMPORT_ERROR}"
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"

    model = pw_detection.MegaDetectorV6(
        device=device,
        pretrained=True,
        version="MDV6-yolov9-c",
    )

    return model, device


# =========================================================
# PDF GENERATOR
# =========================================================

def _styled_table(rows, col_widths):
    table = Table(rows, colWidths=col_widths)

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F3F4")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9CDD1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    return table


def create_observation_pdf(observation, candidate_images):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.7 * cm,
        leftMargin=1.7 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.7 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "JaguarIDTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "JaguarIDSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=18,
    )

    section_style = ParagraphStyle(
        "JaguarIDSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        spaceBefore=14,
        spaceAfter=8,
    )

    note_style = ParagraphStyle(
        "JaguarIDNote",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#555555"),
    )

    caption_style = ParagraphStyle(
        "JaguarIDCaption",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#666666"),
        spaceBefore=4,
        spaceAfter=10,
    )

    story = [
        Paragraph("PantheraMONITORING", title_style),
        Paragraph(
            "PANTHERA LAB · SCIENTIFIC MONITORING REPORT",
            subtitle_style,
        ),
    ]

    story.append(Paragraph("Observation Summary", section_style))

    summary_rows = [
        ["Observation ID", escape_pdf_text(observation.get("observation_id", ""))],
        [T("Observation name", "Nombre de la observación"), escape_pdf_text(observation.get("observation_name", ""))],
        [
            "Analysis date",
            f'{observation.get("analysis_date", "")} {observation.get("analysis_time", "")}',
        ],
        [T("Observer / Researcher", "Observador / Investigador"), escape_pdf_text(observation.get("observer", ""))],
        ["Camera / Station", escape_pdf_text(observation.get("camera_id", ""))],
        [T("Study site", "Sitio de estudio"), escape_pdf_text(observation.get("study_site", ""))],
        [T("Institution / NGO", "Institución / ONG"), escape_pdf_text(observation.get("organization", ""))],
        [T("Project code", "Código del proyecto"), escape_pdf_text(observation.get("project_code", ""))],
        [T("Sampling protocol", "Protocolo de muestreo"), escape_pdf_text(observation.get("sampling_protocol", ""))],
        [T("Camera model", "Modelo de cámara"), escape_pdf_text(observation.get("camera_model", ""))],
        [T("Deployment date", "Fecha de instalación"), escape_pdf_text(observation.get("deployment_date", ""))],
        [T("Retrieval date", "Fecha de retiro"), escape_pdf_text(observation.get("retrieval_date", ""))],
        [T("Latitude", "Latitud"), str(observation.get("camera_latitude", "Not specified"))],
        [T("Longitude", "Longitud"), str(observation.get("camera_longitude", "Not specified"))],
        ["Species annotation", escape_pdf_text(observation.get("species", ""))],
        [T("Individual ID", "ID del individuo"), escape_pdf_text(observation.get("individual_id", ""))],
        ["Media type", escape_pdf_text(observation.get("media_type", "none"))],
        ["Source video", escape_pdf_text(observation.get("source_video", ""))],
        ["Source image", escape_pdf_text(observation.get("source_image", ""))],
        ["Edge event ID", escape_pdf_text(observation.get("edge_event_id", "Not available"))],
    ]

    story.append(_styled_table(summary_rows, [5 * cm, 11 * cm]))

    story.append(Paragraph("Monitoring & Reporting Variables", section_style))

    reporting_rows = [
        ["Event date/time (UTC)", escape_pdf_text(observation.get("event_datetime_utc", "Not specified"))],
        ["Altitude", (
            f'{observation.get("altitude_m"):.1f} m'
            if observation.get("altitude_m") is not None else "Not specified"
        )],
        ["Temperature", (
            f'{observation.get("temperature_c"):.1f} °C'
            if observation.get("temperature_c") is not None else "Not specified"
        )],
        ["Relative humidity", (
            f'{observation.get("humidity_percent"):.1f}%'
            if observation.get("humidity_percent") is not None else "Not specified"
        )],
        [T("Sex", "Sexo"), escape_pdf_text(observation.get("sex", "unknown"))],
        [T("Age class", "Clase de edad"), escape_pdf_text(observation.get("age_class", "unknown"))],
        ["Viewpoint", escape_pdf_text(observation.get("viewpoint", "unknown"))],
        ["Behavior", escape_pdf_text(observation.get("behavior", "") or "Not specified")],
        ["Validation status", escape_pdf_text(observation.get("validation_status", "researcher_review_pending"))],
        ["Camera nights", str(observation.get("camera_nights") if observation.get("camera_nights") is not None else "Not specified")],
        ["Identification method", escape_pdf_text(observation.get("identification_method", "not_verified"))],
        ["Evidence quality", escape_pdf_text(observation.get("evidence_quality", "not_assessed"))],
        ["Environmental source", escape_pdf_text(observation.get("environmental_source", "not_specified"))],
        ["Habitat category", escape_pdf_text(observation.get("habitat_category", ""))],
        ["Image URL / URI", escape_pdf_text(observation.get("image_url", "") or "Not specified")],
        ["Video URL / URI", escape_pdf_text(observation.get("video_url", "") or "Not specified")],
    ]
    story.append(_styled_table(reporting_rows, [7 * cm, 9 * cm]))

    if observation.get("habitat_notes"):
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "<b>Habitat / microhabitat:</b> "
                + escape_pdf_text(observation.get("habitat_notes", "")),
                note_style,
            )
        )

    if observation.get("sampling_limitations"):
        story.append(Paragraph(
            "<b>Sampling limitations:</b> " + escape_pdf_text(observation.get("sampling_limitations", "")),
            note_style,
        ))

    story.append(Paragraph("Edge AI Analysis", section_style))

    analysis_rows = [
        ["Video duration", f'{observation.get("duration_seconds", 0):.1f} s'],
        ["Resolution", observation.get("resolution", "")],
        ["Frame rate", f'{observation.get("fps", 0):.1f} FPS'],
        ["Frames analyzed", str(observation.get("frames_analyzed", 0))],
        ["Frames retained", str(observation.get("frames_retained", 0))],
        ["Frames discarded", str(observation.get("frames_discarded", 0))],
        ["Animal detections", str(observation.get("animal_detections", 0))],
        ["Person detections", str(observation.get("person_detections", 0))],
        ["Vehicle detections", str(observation.get("vehicle_detections", 0))],
        [
            "Estimated payload reduction",
            f'{observation.get("estimated_payload_reduction", 0):.1f}%',
        ],
        ["Inference device", observation.get("device", "")],
        ["Processing time", f'{observation.get("processing_seconds", 0):.1f} s'],
    ]

    story.append(_styled_table(analysis_rows, [7 * cm, 9 * cm]))

    story.append(Paragraph("Detection Confidence Statistics", section_style))

    confidence_rows = [
        ["Retained animal detections", str(observation.get("confidence_count", 0))],
        ["Peak detection confidence", f'{observation.get("confidence_max", 0):.1%}'],
        ["Mean detection confidence", f'{observation.get("confidence_mean", 0):.1%}'],
        ["Median detection confidence", f'{observation.get("confidence_median", 0):.1%}'],
        ["Minimum detection confidence", f'{observation.get("confidence_min", 0):.1%}'],
        ["Confidence standard deviation", f'{observation.get("confidence_std", 0):.1%}'],
        ["Confidence range", f'{observation.get("confidence_range", 0):.1%}'],
        [
            "Detection-positive sampled frames",
            f'{observation.get("positive_frame_rate", 0):.1f}%',
        ],
    ]

    story.append(_styled_table(confidence_rows, [8 * cm, 8 * cm]))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "<b>Interpretation:</b> These values summarize confidence behavior "
            "among detections in this specific analyzed video. They do not measure "
            "model accuracy, precision, recall, calibration, generalization or overfitting.",
            note_style,
        )
    )

    if "network_throughput_mbps" in observation:
        story.append(Paragraph("5G Trunk / Connectivity Layer", section_style))

        network_rows = [
            ["Assumed uplink throughput", f'{observation.get("network_throughput_mbps", 0):.1f} Mbps'],
            ["Assumed latency", f'{observation.get("network_latency_ms", 0):.0f} ms'],
            ["Sampled input payload", f'{observation.get("input_mb", 0):.3f} MB'],
            ["Candidate payload", f'{observation.get("candidate_mb", 0):.3f} MB'],
            ["Avoided transmission", f'{observation.get("transmission_avoided_mb", 0):.3f} MB'],
            ["Raw estimated transmission", f'{observation.get("raw_transmission_seconds", 0):.3f} s'],
            ["Edge estimated transmission", f'{observation.get("edge_transmission_seconds", 0):.3f} s'],
            ["Estimated time avoided", f'{observation.get("transmission_time_saved_seconds", 0):.3f} s'],
        ]

        story.append(_styled_table(network_rows, [8 * cm, 8 * cm]))
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "<b>Network note:</b> These are deterministic estimates under "
                "user-selected network assumptions. They are not measured 5G KPIs.",
                note_style,
            )
        )

    if "sentinel1_latest" in observation or "sentinel2_latest" in observation:
        story.append(Paragraph("Copernicus / Sentinel Context", section_style))

        sentinel_rows = [
            ["Sentinel-1 latest acquisition", escape_pdf_text(observation.get("sentinel1_latest", "Not available"))],
            ["Sentinel-2 latest acquisition", escape_pdf_text(observation.get("sentinel2_latest", "Not available"))],
            [
                "Sentinel-2 cloud cover",
                (
                    f'{observation["sentinel2_cloud_cover"]:.1f}%'
                    if observation.get("sentinel2_cloud_cover") is not None
                    else "Not available"
                ),
            ],
        ]

        story.append(_styled_table(sentinel_rows, [8 * cm, 8 * cm]))
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "<b>Remote-sensing note:</b> Satellite catalogue availability provides "
                "environmental acquisition context only. It does not by itself establish "
                "forest loss, flooding, habitat change or ecological causality.",
                note_style,
            )
        )

    story.append(Paragraph("Panthera LAB Cloud Persistence", section_style))
    panthera_rows = [
        ["Storage bucket", escape_pdf_text(observation.get("pantheraid_storage_bucket", PANTHERA_STORAGE_BUCKET))],
        ["Transmission records", str(observation.get("pantheraid_transmitted_records", 0))],
        ["Last transmission status", escape_pdf_text(observation.get("pantheraid_last_status", "Not transmitted"))],
        ["Last image URL", escape_pdf_text(observation.get("pantheraid_last_image_url", "Not available"))],
    ]
    story.append(_styled_table(panthera_rows, [7 * cm, 9 * cm]))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "<b>Cloud note:</b> Only complete retained event frames are persisted by this prototype. "
            "Species remains null unless explicitly researcher-validated.",
            note_style,
        )
    )

    story.append(Paragraph("Research Notes", section_style))
    story.append(
        Paragraph(
            escape_pdf_text(observation.get("notes", "No notes")),
            styles["BodyText"],
        )
    )

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "<b>Scientific interpretation note:</b> MegaDetector performs object detection "
            "for animals, people and vehicles. Species and individual identity included in "
            "this report are researcher-supplied annotations unless a validated downstream "
            "classification or re-identification model is integrated.",
            note_style,
        )
    )

    if candidate_images:
        story.append(PageBreak())
        story.append(Paragraph("Candidate Animal Images", section_style))
        story.append(
            Paragraph(
                "Animal detections retained by the Edge filtering stage for scientific review.",
                styles["BodyText"],
            )
        )
        story.append(Spacer(1, 10))

        for index, candidate in enumerate(candidate_images[:6], start=1):
            rgb_image = candidate["image"]
            bgr_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
            success_encode, encoded = cv2.imencode(".png", bgr_image)

            if not success_encode:
                continue

            image_buffer = io.BytesIO(encoded.tobytes())
            img_height, img_width = rgb_image.shape[:2]
            max_width = 12 * cm
            max_height = 8 * cm
            aspect = (img_width / img_height) if img_height > 0 else 1
            pdf_width = max_width
            pdf_height = pdf_width / aspect

            if pdf_height > max_height:
                pdf_height = max_height
                pdf_width = pdf_height * aspect

            story.append(
                PDFImage(
                    image_buffer,
                    width=pdf_width,
                    height=pdf_height,
                )
            )

            story.append(
                Paragraph(
                    (
                        f"Candidate {index:02d} · Video time {candidate['time']:.1f} s · "
                        f"MegaDetector confidence {candidate['confidence']:.3f}"
                    ),
                    caption_style,
                )
            )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# =========================================================
# APPLICATION HEADER
# =========================================================

st.markdown(
    f'<div class="jaguarid-kicker">{T("PantheraEDGE Scientific Workspace", "PantheraEDGE · Laboratorio científico")}</div>',
    unsafe_allow_html=True,
)

st.title(T("PantheraEDGE · Panthera Lab", "PantheraEDGE · Panthera Lab"))

st.markdown(
    f"""
    <div class="jaguarid-subtitle">
        {T(
            "Scientific camera-trap analysis, researcher annotations, event filtering and exports. Cloud monitoring is a preview, not a connected production dashboard.",
            "Análisis científico de cámaras trampa, anotaciones de investigadores, filtrado de eventos y exportaciones. La sección de monitoreo es una vista de demostración, no un dashboard productivo conectado."
        )}
    </div>
    <div class="technical-strip">
        PantheraCAM · PantheraEDGE · 5G · Panthera LAB Cloud · PantheraMONITORING · PantheraID
    </div>
    <div class="architecture-ribbon">
        <div class="architecture-step"><div class="num">1 · Campo</div><strong>PantheraCAM / Sensores</strong><span>Captura local · Wi-Fi / LoRa · SD</span></div>
        <div class="architecture-arrow">→</div>
        <div class="architecture-step"><div class="num">2 · Edge</div><strong>PantheraEDGE</strong><span>MegaDetector · fusión · cola offline</span></div>
        <div class="architecture-arrow">→</div>
        <div class="architecture-step blue"><div class="num">3 · Troncal</div><strong>5G</strong><span>Evidencia filtrada · 4G/satélite fallback</span></div>
        <div class="architecture-arrow">→</div>
        <div class="architecture-step"><div class="num">4 · Nube</div><strong>Panthera LAB</strong><span>Ingesta · storage · PantheraID · dashboard</span></div>
        <div class="architecture-arrow">→</div>
        <div class="architecture-step"><div class="num">5 · Salida</div><strong>Instituciones</strong><span>SINAC · investigadores · guardaparques</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# RESEARCH / TECHNOLOGY BRAND STRIP
# =========================================================

# IMPORTANT:
# Keep the HTML flush-left. Markdown interprets indented HTML as a code block.

CQU_LOGO_URL = (
    "https://www.cqu.edu.cn/__local/9/3A/2A/"
    "99808910D1AFBED502CF94BF329_5B24A270_1E97F.png?e=.png"
)

COPERNICUS_LOGO_URL = (
    "https://climate.copernicus.eu/sites/default/files/custom-uploads/"
    "branding/Copernicus%20vecto%20def%20%20Europe%27s%20eyes%20on%20Earth.png"
)

brand_html = f"""<div class="brand-panel">
<div class="brand-panel-label">{T("Research · Data · Connectivity Context", "Investigación · Datos · Conectividad")}</div>
<div class="brand-row">
<div class="brand-logo-card cqu">
<img src="{CQU_LOGO_URL}" alt="Chongqing University" loading="eager">
</div>
<div class="brand-logo-card copernicus">
<img src="{COPERNICUS_LOGO_URL}" alt="Copernicus" loading="eager">
</div>
<div class="brand-vector-card">
<div class="brand-symbol">5G</div>
<div class="brand-meta">
<strong>{T("Connectivity", "Conectividad")}</strong>
<span>{T("Edge transmission model", "Modelo de transmisión Edge")}</span>
</div>
</div>
<div class="brand-logo-card sentinel-logo">
<img src="https://download.esa.int/multimedia/mission_logos/EO/sentinel-2_logo/sentinel-2.jpg" alt="Sentinel-2" loading="eager">
</div>
</div>
<div class="brand-disclaimer">
{T(
"Institutions, programmes and technologies shown here identify research, data or technical context only; they do not imply endorsement or sponsorship.",
"Las instituciones, programas y tecnologías mostradas identifican únicamente el contexto de investigación, datos o tecnología; no implican respaldo ni patrocinio."
)}
</div>
</div>"""

st.markdown(
    brand_html,
    unsafe_allow_html=True,
)


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header(T("Analysis Parameters", "Parámetros de análisis"))

confidence_threshold = st.sidebar.slider(
    T("PantheraEDGE event threshold", "Umbral de evento PantheraEDGE"),
    min_value=0.10,
    max_value=0.90,
    value=0.60,
    step=0.05,
    help=T(
        "Configurable prototype threshold. 0.60 is an initial demo value and is not yet a biologically validated optimum.",
        "Umbral configurable del prototipo. 0,60 es un valor inicial de demo y aún no es un óptimo validado biológicamente."
    ),
)

sample_seconds = st.sidebar.slider(
    T("Sampling interval (seconds)", "Intervalo de muestreo (segundos)"),
    min_value=0.5,
    max_value=5.0,
    value=1.0,
    step=0.5,
)

max_samples = st.sidebar.slider(
    T("Maximum sampled frames", "Máximo de frames muestreados"),
    min_value=3,
    max_value=30,
    value=10,
    step=1,
)


st.sidebar.divider()
st.sidebar.caption("Panthera Lab · HACKATRON 5G · PantheraEDGE Scientific Prototype")

st.sidebar.divider()
show_technical_diagnostics = st.sidebar.toggle(
    T("Show technical diagnostics", "Mostrar diagnósticos técnicos"),
    value=False,
    help=T("Shows frame-level tables, annotated-frame review and other engineering diagnostics.", "Muestra tablas por frame, revisión de frames anotados y otros diagnósticos técnicos."),
)
compact_view = not show_technical_diagnostics

# =========================================================
# 1. OBSERVATION METADATA
# =========================================================

st.header(T("1. Observation & Field Metadata", "1. Observación y metadatos de campo"))

st.markdown(
    """
    <div class="section-intro">
        Scientific context supplied by the observer. Species and individual
        identity are manual annotations in the current prototype.
    </div>
    """,
    unsafe_allow_html=True,
)

meta_col1, meta_col2 = st.columns(2)

with meta_col1:
    observation_name = st.text_input(
        T("Observation name", "Nombre de la observación"),
        placeholder="Example: Jaguar encounter CT-07",
    )
    camera_id = st.text_input(
        T("Camera / Station ID", "ID de cámara / estación"),
        placeholder="Example: CT-07",
    )
    study_site = st.text_input(
        T("Study site", "Sitio de estudio"),
        placeholder="Example: Osa Peninsula / Sector A",
    )

with meta_col2:
    species_label = st.text_input(
        T("Species identification", "Identificación de especie"),
        placeholder="Example: Panthera onca",
    )
    individual_id = st.text_input(
        T("Individual ID", "ID del individuo"),
        placeholder="Example: JAG-003 or Unknown",
    )
    observer_name = st.text_input(
        T("Observer / Researcher", "Observador / Investigador"),
        placeholder="Researcher name",
    )

observation_notes = st.text_area(
    T("Field notes", "Notas de campo"),
    placeholder=(
        "General field notes, uncertainty, camera conditions or other relevant observations."
    ),
)

# Optional research provenance fields are retained across image, video and manual records.
with st.expander(
    T("Research protocol & data provenance", "Protocolo científico y procedencia de los datos"),
    expanded=False,
):
    provenance_left, provenance_right = st.columns(2)
    with provenance_left:
        organization_name = st.text_input(
            T("Research institution / NGO", "Institución / ONG responsable"),
            key="research_organization",
        )
        project_code = st.text_input(
            T("Project or study code", "Código del proyecto o estudio"),
            key="research_project_code",
        )
        study_protocol = st.text_input(
            T("Sampling protocol / methodology", "Protocolo de muestreo / metodología"),
            key="research_protocol",
        )
        camera_model = st.text_input(
            T("Camera model", "Modelo de cámara"),
            key="research_camera_model",
        )
        deployment_date = st.text_input(
            T("Deployment date (YYYY-MM-DD)", "Fecha de instalación (AAAA-MM-DD)"),
            placeholder="2026-10-01",
            key="research_deployment_date",
        )
        retrieval_date = st.text_input(
            T("Retrieval date (YYYY-MM-DD)", "Fecha de retiro (AAAA-MM-DD)"),
            placeholder="2026-10-08",
            key="research_retrieval_date",
        )
    with provenance_right:
        sampling_effort_nights = st.number_input(
            T("Sampling effort (camera-nights)", "Esfuerzo de muestreo (noches-cámara)"),
            min_value=0.0,
            step=1.0,
            value=None,
            key="research_camera_nights",
            help=T(
                "Leave blank when effort has not been calculated from deployment records.",
                "Dejar vacío si el esfuerzo no se ha calculado con registros de instalación.",
            ),
        )
        identification_method = st.selectbox(
            T("Species / individual identification method", "Método de identificación de especie / individuo"),
            ["not_verified", "researcher_visual_review", "expert_validated", "external_model_unverified"],
            key="research_identification_method",
            help=T(
                "MegaDetector does not identify species or individual jaguars.",
                "MegaDetector no identifica especies ni jaguares individuales.",
            ),
        )
        evidence_quality = st.selectbox(
            T("Evidence quality", "Calidad de la evidencia"),
            ["not_assessed", "high", "medium", "low", "unusable"],
            key="research_evidence_quality",
        )
        environmental_source = st.selectbox(
            T("Environmental data source", "Fuente de datos ambientales"),
            ["not_specified", "camera_sensor", "field_measurement", "weather_station", "researcher_estimate"],
            key="research_environmental_source",
        )
        camera_habitat = st.text_input(
            T("Habitat category", "Categoría de hábitat"),
            placeholder=T("e.g. primary forest, secondary forest, riverbank", "p. ej. bosque primario, secundario, ribera"),
            key="research_habitat_category",
        )
        sampling_notes = st.text_area(
            T("Sampling limitations / biases", "Limitaciones / sesgos de muestreo"),
            key="research_sampling_notes",
        )

st.caption(
    T(
        "Extra research metadata are optional and exported with the observation; they do not alter MegaDetector predictions.",
        "Estos metadatos son opcionales, se exportan con la observación y no modifican las predicciones de MegaDetector.",
    )
)

st.subheader(T("Monitoring & Reporting Variables", "Variables de monitoreo y reporte"))

st.markdown(
    """
    <div class="section-intro">
        Additional structured variables for camera-trap monitoring and downstream reporting.
        These fields are optional unless required by the study protocol, NGO or authority.
    </div>
    """,
    unsafe_allow_html=True,
)

report_col1, report_col2, report_col3 = st.columns(3)

with report_col1:
    event_datetime_input = st.text_input(
        "Event date/time (UTC, ISO 8601)",
        value=st.session_state.get("event_datetime_utc") or "",
        placeholder="2026-10-06T12:45:00Z",
        help="Timestamp associated with the camera event when available.",
        key="event_datetime_utc_input",
    )
    altitude_m = st.number_input(
        T("Altitude (m)", "Altitud (m)"),
        min_value=-500.0,
        max_value=9000.0,
        value=(float(st.session_state["altitude_m"])
               if st.session_state.get("altitude_m") is not None else None),
        step=1.0,
        key="altitude_m_input",
        help="Camera-station altitude in metres. Keep as a configurable field unless supplied by the field node.",
    )
    temperature_c = st.number_input(
        T("Temperature (°C)", "Temperatura (°C)"),
        min_value=-50.0,
        max_value=80.0,
        value=(float(st.session_state["temperature_c"])
               if st.session_state.get("temperature_c") is not None else None),
        step=0.1,
        key="temperature_c_input",
    )

with report_col2:
    humidity_percent = st.number_input(
        T("Relative humidity (%)", "Humedad relativa (%)"),
        min_value=0.0,
        max_value=100.0,
        value=(float(st.session_state["humidity_percent"])
               if st.session_state.get("humidity_percent") is not None else None),
        step=1.0,
        key="humidity_percent_input",
    )
    sex_label = st.selectbox(
        T("Sex", "Sexo"),
        options=["unknown", "female", "male", "undetermined"],
        key="sex_input",
    )

with report_col3:
    age_class_label = st.selectbox(
        T("Age class", "Clase de edad"),
        options=["unknown", "juvenile", "subadult", "adult", "undetermined"],
        key="age_class_input",
    )
    observation_viewpoint = st.selectbox(
        T("Observation viewpoint", "Ángulo de observación"),
        options=["unknown", "left", "right", "frontal", "rear", "other"],
        key="observation_viewpoint_input",
    )

behavior_text = st.text_input(
    T("Observed behavior", "Comportamiento observado"),
    value=st.session_state.get("behavior", ""),
    placeholder="walking, resting, feeding, scent-marking, interaction, unknown",
    key="behavior_input",
)

habitat_notes = st.text_area(
    T("Habitat / microhabitat notes", "Notas de hábitat / microhábitat"),
    value=st.session_state.get("habitat_notes", ""),
    placeholder="Forest type, trail, river edge, canopy condition, disturbance context, etc.",
    key="habitat_notes_input",
)

media_col1, media_col2 = st.columns(2)
with media_col1:
    external_image_url = st.text_input(
        T("Image URL / storage URI", "URL de imagen / URI de almacenamiento"),
        value=st.session_state.get("image_url", ""),
        placeholder="https://... or Supabase storage URI",
        key="image_url_input",
    )
with media_col2:
    external_video_url = st.text_input(
        T("Video URL / storage URI", "URL de video / URI de almacenamiento"),
        value=st.session_state.get("video_url", ""),
        placeholder="https://... or Supabase storage URI",
        key="video_url_input",
    )

validation_status = st.selectbox(
    T("Record validation status", "Estado de validación del registro"),
    options=[
        "researcher_review_pending",
        "researcher_validated",
        "field_verified",
        "rejected",
    ],
    key="validation_status_input",
)

st.session_state["event_datetime_utc"] = event_datetime_input.strip() or None
st.session_state["altitude_m"] = float(altitude_m) if altitude_m is not None else None
st.session_state["temperature_c"] = float(temperature_c) if temperature_c is not None else None
st.session_state["humidity_percent"] = float(humidity_percent) if humidity_percent is not None else None
st.session_state["sex"] = sex_label
st.session_state["age_class"] = age_class_label
st.session_state["viewpoint"] = observation_viewpoint
st.session_state["behavior"] = behavior_text.strip()
st.session_state["habitat_notes"] = habitat_notes.strip()
st.session_state["image_url"] = external_image_url.strip()
st.session_state["video_url"] = external_video_url.strip()
st.session_state["validation_status"] = validation_status
if any(value is not None for value in (altitude_m, temperature_c, humidity_percent)):
    if environmental_source == "not_specified":
        st.warning(T(
            "For scientific traceability, indicate the origin of altitude, temperature and humidity measurements.",
            "Para la trazabilidad científica, indicá de dónde provienen las mediciones de altitud, temperatura y humedad.",
        ))

# Camera coordinates are stored independently from the video analysis.
# The editable map is shown later, after Edge Results.
camera_latitude = float(st.session_state["camera_latitude"])
camera_longitude = float(st.session_state["camera_longitude"])

st.markdown(
    """
    <div class="scientific-note">
        <b>Methodological note.</b>
        MegaDetector identifies the presence of animals, people and vehicles.
        It does not determine species or individual identity. Species and individual
        IDs entered here represent researcher annotations.
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# 2. OPTIONAL MEDIA INPUT
# =========================================================

st.header(T("2. Local Edge Demo Media", "2. Multimedia para demo Edge local"))

st.markdown(
    """
    <div class="section-intro">
        This optional mode reproduces PantheraEDGE filtering inside the Streamlit demo.
        In the target architecture, camera media is processed at the field Edge node and the cloud
        receives filtered events rather than continuous raw video.
    </div>
    """,
    unsafe_allow_html=True,
)

uploaded_video = None
uploaded_image = None
run_analysis = False
run_image_analysis = False

with st.expander(T("Add optional camera-trap media", "Agregar multimedia de cámara trampa"), expanded=True):
    media_col_video, media_col_image = st.columns(2)

    with media_col_video:
        uploaded_video = st.file_uploader(
            T("Video", "Video"),
            type=["avi", "mp4", "mov", "mkv"],
            key="camera_trap_video",
            help="Optional camera-trap video for sampled MegaDetector analysis.",
        )

        if uploaded_video is not None:
            current_file_signature = (
                uploaded_video.name,
                uploaded_video.size,
            )

            if st.session_state.current_uploaded_file != current_file_signature:
                st.session_state.current_uploaded_file = current_file_signature
                st.session_state.analysis_result = None
                st.session_state.pantheraid_transmission_log = []

            st.success(f"Video loaded: {uploaded_video.name}")

            try:
                st.video(uploaded_video.getvalue())
            except Exception:
                st.caption(
                    "Browser preview is unavailable for this format; OpenCV may still process it."
                )

            run_analysis = st.button(
                T("Run Video Analysis", "Analizar video"),
                type="primary",
                use_container_width=True,
                key="run_video_edge_analysis",
            )

    with media_col_image:
        uploaded_image = st.file_uploader(
            T("Still image / frame", "Imagen fija / frame"),
            type=["jpg", "jpeg", "png", "webp"],
            key="camera_trap_image",
            help="Optional still frame for single-image MegaDetector analysis.",
        )

        if uploaded_image is not None:
            image_signature = (
                uploaded_image.name,
                uploaded_image.size,
            )

            if st.session_state.current_uploaded_image != image_signature:
                st.session_state.current_uploaded_image = image_signature
                st.session_state.analysis_result = None
                st.session_state.pantheraid_transmission_log = []

            image_preview = bytes_to_rgb_image(uploaded_image.getvalue())
            st.image(
                image_preview,
                caption=uploaded_image.name,
                use_container_width=True,
            )

            run_image_analysis = st.button(
                T("Run Image Analysis", "Analizar imagen"),
                type="primary",
                use_container_width=True,
                key="run_image_edge_analysis",
            )

    if uploaded_video is None and uploaded_image is None:
        st.caption(
            "No media attached. This is valid: continue with metadata, mapping, "
            "Sentinel context, Edge-node information, registry and PDF reporting."
        )

# =========================================================
# 3. EDGE AI PROCESSING
# =========================================================

st.header(T("3. PantheraEDGE Local Simulation", "3. Simulación local PantheraEDGE"))

st.markdown(
    """
    <div class="section-intro">
        Demo-only local execution of MegaDetector. Production flow places this filtering in PantheraEDGE before the 5G trunk.
    </div>
    """,
    unsafe_allow_html=True,
)

if not run_analysis and not run_image_analysis and st.session_state.analysis_result is None:
    st.info("No AI analysis is required for a manual field record. Add media above when automated detection is needed.")
elif not run_analysis and not run_image_analysis and st.session_state.analysis_result is not None:
    st.success("Existing Edge analysis loaded for the current media item.")


# =========================================================
# IMAGE ANALYSIS
# =========================================================

if run_image_analysis and uploaded_image is not None:
    image_bytes = uploaded_image.getvalue()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_image:
        temp_image.write(image_bytes)
        image_path = temp_image.name

    try:
        rgb_image = bytes_to_rgb_image(image_bytes)
        bgr_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
        height, width = bgr_image.shape[:2]

        st.subheader(T("Image Characteristics", "Características de la imagen"))
        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("Resolution", f"{width} × {height}")
        ic2.metric("Input size", f"{len(image_bytes) / 1024 / 1024:.3f} MB")
        ic3.metric("Samples analyzed", "1")

        with st.spinner("Initializing MegaDetector V6..."):
            model, device = load_model()

        inference_start = time.time()
        result_md = model.single_image_detection(
            image_path,
            det_conf_thres=confidence_threshold,
        )
        inference_seconds = time.time() - inference_start

        CLASS_NAMES = {0: "animal", 1: "person", 2: "vehicle"}
        detections = result_md["detections"]

        candidate_images = []
        annotated_images = []
        retained_full_frames = []
        total_animals = 0
        total_people = 0
        total_vehicles = 0
        max_animal_confidence = 0.0
        total_candidate_bytes = 0

        annotated = bgr_image.copy()

        if detections is not None and len(detections) > 0:
            boxes = detections.xyxy
            confidences = detections.confidence
            class_ids = detections.class_id

            for detection_index in range(len(boxes)):
                confidence = float(confidences[detection_index])
                class_id = int(class_ids[detection_index])
                label = CLASS_NAMES.get(class_id, "unknown")

                x1, y1, x2, y2 = [int(v) for v in boxes[detection_index]]
                x1 = max(0, min(x1, width - 1))
                y1 = max(0, min(y1, height - 1))
                x2 = max(x1 + 1, min(x2, width))
                y2 = max(y1 + 1, min(y2, height))

                if label == "animal":
                    total_animals += 1
                    max_animal_confidence = max(max_animal_confidence, confidence)
                    crop = bgr_image[y1:y2, x1:x2]
                    if crop.size > 0:
                        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                        candidate_images.append(
                            {
                                "image": crop_rgb,
                                "confidence": confidence,
                                "time": 0.0,
                                "sample": 1,
                                "bbox_xyxy": [x1, y1, x2, y2],
                            }
                        )
                        ok_crop, enc_crop = cv2.imencode(".jpg", crop)
                        if ok_crop:
                            total_candidate_bytes += len(enc_crop)
                elif label == "person":
                    total_people += 1
                elif label == "vehicle":
                    total_vehicles += 1

                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    annotated,
                    f"{label.upper()} {confidence:.2f}",
                    (x1, max(30, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                )

        keep = total_animals > 0
        frames_kept = 1 if keep else 0
        frames_discarded = 0 if keep else 1
        decision = "RETAIN · ANIMAL EVENT" if keep else "DISCARD · NO ANIMAL EVENT"

        if keep:
            ok_full, enc_full = cv2.imencode(
                ".jpg",
                bgr_image,
                [int(cv2.IMWRITE_JPEG_QUALITY), 90],
            )
            if ok_full:
                retained_full_frames.append(
                    {
                        "sample": 1,
                        "time": 0.0,
                        "animal_count": total_animals,
                        "jpeg_bytes": enc_full.tobytes(),
                    }
                )

        annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        annotated_images.append(
            {
                "image": annotated_rgb,
                "time": 0.0,
                "decision": decision,
            }
        )

        input_mb = len(image_bytes) / 1024 / 1024
        retained_payload_bytes = sum(
            len(item.get("jpeg_bytes", b"")) for item in retained_full_frames
        )
        candidate_mb = retained_payload_bytes / 1024 / 1024
        payload_reduction = (
            ((len(image_bytes) - retained_payload_bytes) / len(image_bytes) * 100)
            if len(image_bytes) > 0
            else 0.0
        )

        df = pd.DataFrame(
            [
                {
                    "sample": 1,
                    "video_time_seconds": 0.0,
                    "animals": total_animals,
                    "persons": total_people,
                    "vehicles": total_vehicles,
                    "max_animal_confidence": round(max_animal_confidence, 4),
                    "edge_decision": "RETAIN" if keep else "DISCARD",
                    "input_jpeg_bytes": len(image_bytes),
                    "candidate_jpeg_bytes": total_candidate_bytes,
                    "inference_seconds": round(inference_seconds, 3),
                }
            ]
        )

        confidence_stats = confidence_statistics(candidate_images, 1, frames_kept)
        analysis_timestamp = datetime.now()
        observation_id = (
            "OBS-" + analysis_timestamp.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
        )

        observation = {
            "observation_id": observation_id,
            "observation_name": observation_name.strip() or observation_id,
            "analysis_date": analysis_timestamp.strftime("%Y-%m-%d"),
            "analysis_time": analysis_timestamp.strftime("%H:%M:%S"),
            "observer": observer_name.strip() or "Not specified",
            "camera_id": camera_id.strip() or "Not specified",
            "study_site": study_site.strip() or "Not specified",
            "camera_latitude": float(camera_latitude),
            "camera_longitude": float(camera_longitude),
            "species": species_label.strip() or "Unassigned",
            "individual_id": individual_id.strip() or "Unassigned",
            "notes": observation_notes.strip() or "No notes",
            "event_datetime_utc": st.session_state.get("event_datetime_utc") or "Not specified",
            "altitude_m": st.session_state.get("altitude_m"),
            "temperature_c": st.session_state.get("temperature_c"),
            "humidity_percent": st.session_state.get("humidity_percent"),
            "sex": st.session_state.get("sex", "unknown"),
            "age_class": st.session_state.get("age_class", "unknown"),
            "viewpoint": st.session_state.get("viewpoint", "unknown"),
            "behavior": st.session_state.get("behavior", ""),
            "habitat_notes": st.session_state.get("habitat_notes", ""),
            "image_url": st.session_state.get("image_url", ""),
            "video_url": st.session_state.get("video_url", ""),
            "validation_status": st.session_state.get("validation_status", "researcher_review_pending"),
            "source_video": "Not applicable",
            "source_image": uploaded_image.name,
            "media_type": "image",
            "edge_event_id": (
                st.session_state.latest_edge_event.get("event_id", "Not available")
                if st.session_state.latest_edge_event
                else "Not available"
            ),
            "duration_seconds": 0.0,
            "resolution": f"{width} × {height}",
            "fps": 0.0,
            "frames_analyzed": 1,
            "frames_retained": frames_kept,
            "frames_discarded": frames_discarded,
            "animal_detections": total_animals,
            "person_detections": total_people,
            "vehicle_detections": total_vehicles,
            "estimated_payload_reduction": round(payload_reduction, 2),
            "processing_seconds": round(inference_seconds, 2),
            "device": str(device).upper(),
            "confidence_count": confidence_stats["count"],
            "confidence_max": confidence_stats["maximum"],
            "confidence_mean": confidence_stats["mean"],
            "confidence_median": confidence_stats["median"],
            "confidence_min": confidence_stats["minimum"],
            "confidence_std": confidence_stats["std"],
            "confidence_range": confidence_stats["range"],
            "positive_frame_rate": confidence_stats["positive_frame_rate"],
            "input_mb": input_mb,
            "candidate_mb": candidate_mb,
        }

        st.session_state.analysis_result = {
            "observation": observation,
            "df": df,
            "candidate_images": candidate_images,
            "annotated_images": annotated_images,
            "retained_full_frames": retained_full_frames,
            "frames_kept": frames_kept,
            "frames_discarded": frames_discarded,
            "discard_percentage": float(frames_discarded * 100.0),
            "keep_percentage": float(frames_kept * 100.0),
            "payload_reduction": payload_reduction,
            "input_mb": input_mb,
            "candidate_mb": candidate_mb,
            "average_inference": inference_seconds,
            "total_animals": total_animals,
            "total_people": total_people,
            "total_vehicles": total_vehicles,
            "confidence_threshold": confidence_threshold,
            "confidence_stats": confidence_stats,
        }

        st.success("Image Edge analysis completed.")

    except Exception as error:
        st.error(f"Image analysis failed: {error}")

    finally:
        try:
            os.remove(image_path)
        except Exception:
            pass


# =========================================================
# VIDEO ANALYSIS
# =========================================================

if run_analysis:
    video_suffix = Path(uploaded_video.name).suffix or ".avi"

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=video_suffix,
    ) as temp_video:
        temp_video.write(uploaded_video.getvalue())
        video_path = temp_video.name

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        try:
            os.remove(video_path)
        except Exception:
            pass

        st.error("OpenCV could not open the uploaded video.")
        st.stop()

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if fps <= 0:
        fps = 30.0

    duration = total_frames / fps if fps > 0 else 0

    st.subheader(T("Video Characteristics", "Características del video"))

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Duration", f"{duration:.1f} s")
    c2.metric("Frame rate", f"{fps:.1f} FPS")
    c3.metric("Resolution", f"{width} × {height}")
    c4.metric("Total frames", f"{total_frames:,}")

    st.subheader(T("Edge Inference", "Inferencia Edge"))

    with st.spinner("Initializing MegaDetector V6..."):
        model, device = load_model()

    st.success(f"MegaDetector V6 initialized · {device.upper()} inference")


    CLASS_NAMES = {
        0: "animal",
        1: "person",
        2: "vehicle",
    }

    frame_interval = max(1, int(fps * sample_seconds))

    records = []
    candidate_images = []
    annotated_images = []
    retained_full_frames = []

    sample_number = 0
    frame_number = 0
    frames_kept = 0
    frames_discarded = 0
    total_animals = 0
    total_people = 0
    total_vehicles = 0
    total_input_bytes = 0
    total_candidate_bytes = 0

    st.subheader(T("Processing", "Procesamiento"))

    progress_bar = st.progress(0)
    status_text = st.empty()
    live_image = st.empty()

    processing_start = time.time()

    while True:
        success, frame = cap.read()

        if not success:
            break

        if frame_number % frame_interval != 0:
            frame_number += 1
            continue

        sample_number += 1

        if sample_number > max_samples:
            break

        video_time = frame_number / fps

        status_text.write(
            f"Analyzing sample {sample_number}/{max_samples} · video time {video_time:.1f} s"
        )

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".jpg",
        ) as temp_frame:
            frame_path = temp_frame.name

        cv2.imwrite(frame_path, frame)

        try:
            frame_bytes = Path(frame_path).stat().st_size
        except Exception:
            frame_bytes = 0

        total_input_bytes += frame_bytes

        inference_start = time.time()

        try:
            result_md = model.single_image_detection(
                frame_path,
                det_conf_thres=confidence_threshold,
            )
        except Exception as error:
            try:
                os.remove(frame_path)
            except Exception:
                pass

            cap.release()

            try:
                os.remove(video_path)
            except Exception:
                pass

            st.error(f"MegaDetector inference failed: {error}")
            st.stop()

        inference_seconds = time.time() - inference_start
        detections = result_md["detections"]

        try:
            os.remove(frame_path)
        except Exception:
            pass

        animal_count = 0
        person_count = 0
        vehicle_count = 0
        max_animal_confidence = 0.0
        candidate_bytes_frame = 0
        annotated = frame.copy()

        if detections is not None and len(detections) > 0:
            boxes = detections.xyxy
            confidences = detections.confidence
            class_ids = detections.class_id

            for detection_index in range(len(boxes)):
                confidence = float(confidences[detection_index])
                class_id = int(class_ids[detection_index])
                label = CLASS_NAMES.get(class_id, "unknown")

                x1, y1, x2, y2 = [
                    int(value)
                    for value in boxes[detection_index]
                ]

                x1 = max(0, min(x1, width - 1))
                y1 = max(0, min(y1, height - 1))
                x2 = max(x1 + 1, min(x2, width))
                y2 = max(y1 + 1, min(y2, height))

                if label == "animal":
                    animal_count += 1
                    total_animals += 1

                    max_animal_confidence = max(
                        max_animal_confidence,
                        confidence,
                    )

                    crop = frame[y1:y2, x1:x2]

                    if crop.size > 0:
                        crop_rgb = cv2.cvtColor(
                            crop,
                            cv2.COLOR_BGR2RGB,
                        )

                        candidate_images.append(
                            {
                                "image": crop_rgb,
                                "confidence": confidence,
                                "time": video_time,
                                "sample": sample_number,
                                "bbox_xyxy": [x1, y1, x2, y2],
                            }
                        )

                        success_encode, encoded = cv2.imencode(".jpg", crop)

                        if success_encode:
                            crop_bytes = len(encoded)
                            candidate_bytes_frame += crop_bytes
                            total_candidate_bytes += crop_bytes

                elif label == "person":
                    person_count += 1
                    total_people += 1

                elif label == "vehicle":
                    vehicle_count += 1
                    total_vehicles += 1

                cv2.rectangle(
                    annotated,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2,
                )

                detection_label = f"{label.upper()} {confidence:.2f}"

                cv2.putText(
                    annotated,
                    detection_label,
                    (x1, max(30, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                )

        keep = animal_count > 0

        if keep:
            frames_kept += 1
            decision = "RETAIN · ANIMAL EVENT"

            full_frame_encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
            full_frame_success, full_frame_encoded = cv2.imencode(
                ".jpg",
                frame,
                full_frame_encode_params,
            )
            if full_frame_success:
                retained_full_frames.append(
                    {
                        "sample": sample_number,
                        "time": video_time,
                        "animal_count": animal_count,
                        "jpeg_bytes": full_frame_encoded.tobytes(),
                    }
                )
        else:
            frames_discarded += 1
            decision = "DISCARD · NO ANIMAL EVENT"

        cv2.rectangle(
            annotated,
            (0, 0),
            (min(width, 780), 135),
            (0, 0, 0),
            -1,
        )

        cv2.putText(
            annotated,
            "PANTHERAEDGE · LOCAL INFERENCE DEMO",
            (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
        )

        cv2.putText(
            annotated,
            f"Video time: {video_time:.1f} s",
            (20, 64),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            1,
        )

        cv2.putText(
            annotated,
            f"Decision: {decision}",
            (20, 96),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            1,
        )

        cv2.putText(
            annotated,
            f"Max animal confidence: {max_animal_confidence:.2f}",
            (20, 126),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            1,
        )

        annotated_rgb = cv2.cvtColor(
            annotated,
            cv2.COLOR_BGR2RGB,
        )

        annotated_images.append(
            {
                "image": annotated_rgb,
                "time": video_time,
                "decision": decision,
            }
        )

        live_image.image(
            annotated_rgb,
            caption=f"Sample {sample_number} · {decision}",
            use_container_width=True,
        )

        records.append(
            {
                "sample": sample_number,
                "video_time_seconds": round(video_time, 2),
                "animals": animal_count,
                "persons": person_count,
                "vehicles": vehicle_count,
                "max_animal_confidence": round(max_animal_confidence, 4),
                "edge_decision": "RETAIN" if keep else "DISCARD",
                "input_jpeg_bytes": frame_bytes,
                "candidate_jpeg_bytes": candidate_bytes_frame,
                "inference_seconds": round(inference_seconds, 3),
            }
        )

        progress_bar.progress(
            min(sample_number / max_samples, 1.0)
        )

        frame_number += 1

    cap.release()

    try:
        os.remove(video_path)
    except Exception:
        pass

    processing_seconds = time.time() - processing_start

    progress_bar.progress(1.0)
    status_text.success("Edge analysis completed.")

    df = pd.DataFrame(records)

    if df.empty:
        st.error("No frames were processed.")
        st.stop()

    total_samples = len(df)

    keep_percentage = (
        frames_kept / total_samples * 100
        if total_samples
        else 0.0
    )

    discard_percentage = (
        frames_discarded / total_samples * 100
        if total_samples
        else 0.0
    )

    input_mb = total_input_bytes / 1024 / 1024
    retained_payload_bytes = sum(
        len(item.get("jpeg_bytes", b"")) for item in retained_full_frames
    )
    candidate_mb = retained_payload_bytes / 1024 / 1024

    payload_reduction = (
        ((total_input_bytes - retained_payload_bytes) / total_input_bytes * 100)
        if total_input_bytes > 0
        else 0.0
    )

    average_inference = float(df["inference_seconds"].mean())

    confidence_stats = confidence_statistics(
        candidate_images,
        total_samples,
        frames_kept,
    )

    analysis_timestamp = datetime.now()

    observation_id = (
        "OBS-"
        + analysis_timestamp.strftime("%Y%m%d")
        + "-"
        + uuid.uuid4().hex[:6].upper()
    )

    observation = {
        "observation_id": observation_id,
        "observation_name": observation_name.strip() or observation_id,
        "analysis_date": analysis_timestamp.strftime("%Y-%m-%d"),
        "analysis_time": analysis_timestamp.strftime("%H:%M:%S"),
        "observer": observer_name.strip() or "Not specified",
        "camera_id": camera_id.strip() or "Not specified",
        "study_site": study_site.strip() or "Not specified",
        "camera_latitude": float(camera_latitude),
        "camera_longitude": float(camera_longitude),
        "species": species_label.strip() or "Unassigned",
        "individual_id": individual_id.strip() or "Unassigned",
        "notes": observation_notes.strip() or "No notes",
        "event_datetime_utc": st.session_state.get("event_datetime_utc") or "Not specified",
        "altitude_m": st.session_state.get("altitude_m"),
        "temperature_c": st.session_state.get("temperature_c"),
        "humidity_percent": st.session_state.get("humidity_percent"),
        "sex": st.session_state.get("sex", "unknown"),
        "age_class": st.session_state.get("age_class", "unknown"),
        "viewpoint": st.session_state.get("viewpoint", "unknown"),
        "behavior": st.session_state.get("behavior", ""),
        "habitat_notes": st.session_state.get("habitat_notes", ""),
        "image_url": st.session_state.get("image_url", ""),
        "video_url": st.session_state.get("video_url", ""),
        "validation_status": st.session_state.get("validation_status", "researcher_review_pending"),
        "source_video": uploaded_video.name,
        "source_image": "Not applicable",
        "media_type": "video",
        "edge_event_id": (
            st.session_state.latest_edge_event.get("event_id", "Not available")
            if st.session_state.latest_edge_event
            else "Not available"
        ),
        "duration_seconds": round(duration, 2),
        "resolution": f"{width} × {height}",
        "fps": round(fps, 2),
        "frames_analyzed": total_samples,
        "frames_retained": frames_kept,
        "frames_discarded": frames_discarded,
        "animal_detections": total_animals,
        "person_detections": total_people,
        "vehicle_detections": total_vehicles,
        "estimated_payload_reduction": round(payload_reduction, 2),
        "processing_seconds": round(processing_seconds, 2),
        "device": str(device).upper(),
        "confidence_count": confidence_stats["count"],
        "confidence_max": confidence_stats["maximum"],
        "confidence_mean": confidence_stats["mean"],
        "confidence_median": confidence_stats["median"],
        "confidence_min": confidence_stats["minimum"],
        "confidence_std": confidence_stats["std"],
        "confidence_range": confidence_stats["range"],
        "positive_frame_rate": confidence_stats["positive_frame_rate"],
        "input_mb": input_mb,
        "candidate_mb": candidate_mb,
    }

    st.session_state.analysis_result = {
        "observation": observation,
        "df": df,
        "candidate_images": candidate_images,
        "annotated_images": annotated_images,
        "retained_full_frames": retained_full_frames,
        "frames_kept": frames_kept,
        "frames_discarded": frames_discarded,
        "discard_percentage": discard_percentage,
        "keep_percentage": keep_percentage,
        "payload_reduction": payload_reduction,
        "input_mb": input_mb,
        "candidate_mb": candidate_mb,
        "average_inference": average_inference,
        "total_animals": total_animals,
        "total_people": total_people,
        "total_vehicles": total_vehicles,
        "confidence_threshold": confidence_threshold,
        "confidence_stats": confidence_stats,
    }

# =========================================================
# RESTORE ANALYSIS OR CREATE FIELD-RECORD DEFAULTS
# =========================================================

analysis_available = st.session_state.analysis_result is not None

if analysis_available:
    result = st.session_state.analysis_result
    observation = result["observation"].copy()
    df = result["df"]
    candidate_images = result["candidate_images"]
    annotated_images = result["annotated_images"]
    retained_full_frames = result.get("retained_full_frames", [])
    frames_kept = result["frames_kept"]
    frames_discarded = result["frames_discarded"]
    discard_percentage = result["discard_percentage"]
    keep_percentage = result["keep_percentage"]
    payload_reduction = result["payload_reduction"]
    input_mb = result["input_mb"]
    candidate_mb = result["candidate_mb"]
    average_inference = result["average_inference"]
    total_animals = result["total_animals"]
    total_people = result["total_people"]
    total_vehicles = result["total_vehicles"]
    confidence_threshold_used = result["confidence_threshold"]
    confidence_stats = result["confidence_stats"]
    total_samples = len(df)
else:
    now = datetime.now()
    observation = {
        "observation_id": st.session_state.manual_observation_id,
        "observation_name": observation_name.strip() or st.session_state.manual_observation_id,
        "analysis_date": now.strftime("%Y-%m-%d"),
        "analysis_time": now.strftime("%H:%M:%S"),
        "observer": observer_name.strip() or "Not specified",
        "camera_id": camera_id.strip() or "Not specified",
        "study_site": study_site.strip() or "Not specified",
        "camera_latitude": float(camera_latitude),
        "camera_longitude": float(camera_longitude),
        "species": species_label.strip() or "Unassigned",
        "individual_id": individual_id.strip() or "Unassigned",
        "notes": observation_notes.strip() or "No notes",
        "event_datetime_utc": st.session_state.get("event_datetime_utc") or "Not specified",
        "altitude_m": st.session_state.get("altitude_m"),
        "temperature_c": st.session_state.get("temperature_c"),
        "humidity_percent": st.session_state.get("humidity_percent"),
        "sex": st.session_state.get("sex", "unknown"),
        "age_class": st.session_state.get("age_class", "unknown"),
        "viewpoint": st.session_state.get("viewpoint", "unknown"),
        "behavior": st.session_state.get("behavior", ""),
        "habitat_notes": st.session_state.get("habitat_notes", ""),
        "image_url": st.session_state.get("image_url", ""),
        "video_url": st.session_state.get("video_url", ""),
        "validation_status": st.session_state.get("validation_status", "researcher_review_pending"),
        "source_video": "Not provided",
        "source_image": "Not provided",
        "media_type": "none",
        "edge_event_id": (
            st.session_state.latest_edge_event.get("event_id", "Not available")
            if st.session_state.latest_edge_event
            else "Not available"
        ),
        "duration_seconds": 0.0,
        "resolution": "Not applicable",
        "fps": 0.0,
        "frames_analyzed": 0,
        "frames_retained": 0,
        "frames_discarded": 0,
        "animal_detections": 0,
        "person_detections": 0,
        "vehicle_detections": 0,
        "estimated_payload_reduction": 0.0,
        "processing_seconds": 0.0,
        "device": "Not used",
        "confidence_count": 0,
        "confidence_max": 0.0,
        "confidence_mean": 0.0,
        "confidence_median": 0.0,
        "confidence_min": 0.0,
        "confidence_std": 0.0,
        "confidence_range": 0.0,
        "positive_frame_rate": 0.0,
        "input_mb": 0.0,
        "candidate_mb": 0.0,
    }
    df = pd.DataFrame(
        columns=[
            "sample",
            "video_time_seconds",
            "animals",
            "persons",
            "vehicles",
            "max_animal_confidence",
            "edge_decision",
            "input_jpeg_bytes",
            "candidate_jpeg_bytes",
            "inference_seconds",
        ]
    )
    candidate_images = []
    annotated_images = []
    retained_full_frames = []
    frames_kept = 0
    frames_discarded = 0
    discard_percentage = 0.0
    keep_percentage = 0.0
    payload_reduction = 0.0
    input_mb = 0.0
    candidate_mb = 0.0
    average_inference = 0.0
    total_animals = 0
    total_people = 0
    total_vehicles = 0
    confidence_threshold_used = confidence_threshold
    confidence_stats = confidence_statistics([], 0, 0)
    total_samples = 0

# =========================================================
# UPDATE METADATA AFTER ANALYSIS
# =========================================================

observation["observation_name"] = observation_name.strip() or observation["observation_name"]
observation["camera_id"] = camera_id.strip() or observation["camera_id"]
observation["study_site"] = study_site.strip() or observation["study_site"]
observation["camera_latitude"] = float(camera_latitude)
observation["camera_longitude"] = float(camera_longitude)
observation["species"] = species_label.strip() or observation["species"]
observation["individual_id"] = individual_id.strip() or observation["individual_id"]
observation["observer"] = observer_name.strip() or observation["observer"]
observation["notes"] = observation_notes.strip() or observation["notes"]
observation["event_datetime_utc"] = st.session_state.get("event_datetime_utc") or observation.get("event_datetime_utc", "Not specified")
observation["altitude_m"] = st.session_state.get("altitude_m")
observation["temperature_c"] = st.session_state.get("temperature_c")
observation["humidity_percent"] = st.session_state.get("humidity_percent")
observation["sex"] = st.session_state.get("sex", "unknown")
observation["age_class"] = st.session_state.get("age_class", "unknown")
observation["viewpoint"] = st.session_state.get("viewpoint", "unknown")
observation["behavior"] = st.session_state.get("behavior", "")
observation["habitat_notes"] = st.session_state.get("habitat_notes", "")
observation["image_url"] = st.session_state.get("image_url", "")
observation["video_url"] = st.session_state.get("video_url", "")
observation["validation_status"] = st.session_state.get("validation_status", "researcher_review_pending")
# This common update runs for manual, image and video observations.
observation.update({
    "organization": organization_name.strip(),
    "project_code": project_code.strip(),
    "sampling_protocol": study_protocol.strip(),
    "camera_model": camera_model.strip(),
    "deployment_date": deployment_date.strip(),
    "retrieval_date": retrieval_date.strip(),
    "camera_nights": float(sampling_effort_nights) if sampling_effort_nights is not None else None,
    "identification_method": identification_method,
    "evidence_quality": evidence_quality,
    "environmental_source": environmental_source,
    "habitat_category": camera_habitat.strip(),
    "sampling_limitations": sampling_notes.strip(),
})

observation["edge_event_id"] = (
    st.session_state.latest_edge_event.get("event_id", "Not available")
    if st.session_state.latest_edge_event
    else observation.get("edge_event_id", "Not available")
)

latest_s1 = None
latest_s2 = None

if (
    st.session_state.satellite_result
    and
    not st.session_state.satellite_result.get("error")
):
    latest_s1 = latest_satellite_summary(
        st.session_state.satellite_result.get("sentinel_1", [])
    )
    latest_s2 = latest_satellite_summary(
        st.session_state.satellite_result.get("sentinel_2", [])
    )

observation["sentinel1_latest"] = (
    latest_s1["datetime"]
    if latest_s1
    else "Not available"
)

observation["sentinel2_latest"] = (
    latest_s2["datetime"]
    if latest_s2
    else "Not available"
)

observation["sentinel2_cloud_cover"] = (
    latest_s2.get("cloud_cover")
    if latest_s2
    else None
)

if st.session_state.analysis_result is not None:
    st.session_state.analysis_result["observation"] = observation.copy()

# =========================================================
# 4. EDGE RESULTS
# =========================================================

st.divider()
st.header(T("4. Detection Results", "4. Resultados de detección"))

if not analysis_available:
    st.info("No AI media analysis is attached to this observation. Scientific modules remain fully available.")

st.markdown(
    """
    <div class="section-intro">
        Summary statistics derived from sampled frames processed by MegaDetector
        at the Edge stage.
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = st.columns(4)

m1.metric(T("Frames analyzed", "Frames analizados"), total_samples)
m2.metric(T("Frames retained", "Frames retenidos"), frames_kept)
m3.metric(T("Animal detections", "Detecciones de animales"), total_animals)
m4.metric(T("Payload reduction", "Reducción de datos"), f"{payload_reduction:.1f}%")

if not compact_view:
    m5, m6, m7, m8 = st.columns(4)
    m5.metric("Frames discarded", f"{discard_percentage:.1f}%")
    m6.metric("Sampled input", f"{input_mb:.2f} MB")
    m7.metric("Filtered event payload", f"{candidate_mb:.2f} MB")
    m8.metric("Mean inference time", f"{average_inference:.2f} s")

st.caption(
    "Estimated payload reduction is calculated from sampled JPEG frames and "
    "retained full event frames. It is not a direct measurement of 5G throughput "
    "or source-video compression."
)

# =========================================================
# DETECTION CONFIDENCE STATISTICS
# =========================================================

st.subheader(T("Detection Confidence Statistics", "Estadísticas de confianza de detección"))

st.markdown(
    """
    <div class="section-intro">
        Summary of confidence values for retained animal detections.
    </div>
    """,
    unsafe_allow_html=True,
)

if confidence_stats["count"] == 0:
    st.warning(
        "No animal detections were retained, so confidence statistics cannot be estimated."
    )
else:
    r1, r2, r3, r4 = st.columns(4)

    r1.metric("Mean confidence", f"{confidence_stats['mean']:.1%}")
    r2.metric("Median confidence", f"{confidence_stats['median']:.1%}")
    r3.metric("Peak confidence", f"{confidence_stats['maximum']:.1%}")
    r4.metric("Positive frames", f"{confidence_stats['positive_frame_rate']:.1f}%")

    if not compact_view:
        r5, r6, r7, r8 = st.columns(4)
        r5.metric("Minimum confidence", f"{confidence_stats['minimum']:.1%}")
        r6.metric("Standard deviation", f"{confidence_stats['std']:.1%}")
        r7.metric("Confidence range", f"{confidence_stats['range']:.1%}")
        r8.metric("Animal detections", confidence_stats["count"])

    st.markdown(
        """
        <div class="scientific-note">
            <b>Interpretation boundary.</b>
            A high mean or low dispersion indicates relatively consistent
            confidence values for detections in this video. It does not
            demonstrate model accuracy, generalization, calibration or absence
            of overfitting. Those questions require independent labelled data.
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# 14. CANDIDATE ANIMAL IMAGES
# =========================================================

st.header(T("5. Candidate Animal Images", "5. Imágenes candidatas de animales"))

st.markdown(
    """
    <div class="section-intro">
        Visual evidence retained by MegaDetector for researcher review.
        Candidate crops remain visible because visual inspection is part of the
        scientific validation workflow. These images are not automatically confirmed as jaguars.
    </div>
    """,
    unsafe_allow_html=True,
)

if not candidate_images:
    st.warning("No animal candidates were detected in the sampled frames.")
else:
    candidate_count = len(candidate_images)

    st.success(
        f"{candidate_count} candidate animal "
        f"{'image was' if candidate_count == 1 else 'images were'} retained."
    )

    st.caption(
        "Review and download individual candidate images directly as PNG. "
        "Batch export is available only as a secondary option."
    )

    display_candidates = candidate_images[:12]
    candidate_columns = st.columns(3)

    for index, candidate in enumerate(
        display_candidates,
        start=1,
    ):
        column = candidate_columns[(index - 1) % 3]

        with column:
            st.image(
                candidate["image"],
                use_container_width=True,
            )

            st.markdown(
                f"**Candidate {index:02d}**  \n"
                f"Video time: {candidate['time']:.1f} s  \n"
                f"Detection confidence: {candidate['confidence']:.3f}"
            )

            png_data = image_to_png_bytes(
                candidate["image"]
            )

            if png_data is not None:
                time_string = f"{candidate['time']:.1f}".replace(".", "_")

                candidate_filename = (
                    f"{safe_filename(observation['observation_id'])}"
                    f"_candidate_{index:03d}_t{time_string}s.png"
                )

                st.download_button(
                    label=f"Download candidate {index:02d} · PNG",
                    data=png_data,
                    file_name=candidate_filename,
                    mime="image/png",
                    key=(
                        f"candidate_png_"
                        f"{observation['observation_id']}_"
                        f"{index}"
                    ),
                    use_container_width=True,
                )

    if len(candidate_images) > 12:
        st.caption(
            f"Showing the first 12 of {len(candidate_images)} candidates."
        )

    with st.expander("Optional batch export", expanded=False):
        candidates_zip = create_candidates_zip(
            observation["observation_id"],
            candidate_images,
        )

        st.download_button(
            label=T("Download all candidate images · ZIP", "Descargar todas las imágenes candidatas · ZIP"),
            data=candidates_zip,
            file_name=(
                safe_filename(observation["observation_id"])
                + "_candidate_images.zip"
            ),
            mime="application/zip",
            use_container_width=True,
            key="candidate_batch_zip",
        )

        st.caption(
            "Use this only when the complete candidate set is needed as a batch."
        )


# =========================================================
# 10. EDGE FILTERING CHART
# =========================================================

if analysis_available:
    st.header(T("6. Detection Analytics", "6. Analítica de detección"))
    st.subheader(T("Edge Filtering Outcome", "Resultado del filtrado Edge"))

    filter_labels = ["Retained", "Discarded"]
    filter_values = [frames_kept, frames_discarded]
    filter_colors = [CIVIDIS_DARK, CIVIDIS_LIGHT]

    fig1, ax1 = plt.subplots(figsize=(8.4, 4.7), dpi=180)

    bars = ax1.bar(
        filter_labels,
        filter_values,
        width=0.52,
        color=filter_colors,
        edgecolor="none",
    )

    for bar, value in zip(bars, filter_values):
        percentage = (value / total_samples * 100) if total_samples else 0

        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(total_samples * 0.02, 0.06),
            f"{value} frames\n{percentage:.1f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax1.set_ylabel("Number of sampled frames")
    ax1.set_title("Edge Filtering Outcome", fontweight="semibold", pad=12)
    ax1.grid(axis="y", linestyle=":", linewidth=0.55, alpha=0.42)
    ax1.set_axisbelow(True)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    fig1.tight_layout()

    filtering_png = figure_to_png_bytes(fig1, dpi=600)

    st.pyplot(fig1, use_container_width=True)
    plt.close(fig1)

    st.download_button(
        label="Export filtering figure · PNG 600 dpi",
        data=filtering_png,
        file_name=safe_filename(observation["observation_id"]) + "_edge_filtering_600dpi.png",
        mime="image/png",
    )
else:
    st.header(T("6. Detection Analytics", "6. Analítica de detección"))
    st.caption("Available after optional image/video Edge analysis.")

# =========================================================
# 11. TEMPORAL CONFIDENCE PROFILE
# =========================================================

if analysis_available:
    st.subheader(T("Temporal Detection Confidence", "Confianza de detección temporal"))

    x_values = df["video_time_seconds"]
    y_values = df["max_animal_confidence"]

    fig2, ax2 = plt.subplots(figsize=(10, 4.8), dpi=180)

    ax2.plot(
        x_values,
        y_values,
        linewidth=1.8,
        marker="o",
        markersize=4.8,
        color=CIVIDIS_DARK,
    )

    ax2.axhline(
        y=confidence_threshold_used,
        linestyle="--",
        linewidth=1.15,
        color=CIVIDIS_LIGHT,
        label=f"Detection threshold ({confidence_threshold_used:.2f})",
    )

    ax2.fill_between(
        x_values,
        0,
        y_values,
        color=CIVIDIS_MID,
        alpha=0.10,
    )

    ax2.set_xlabel("Video time (s)")
    ax2.set_ylabel("Maximum animal confidence")
    ax2.set_ylim(0, 1.0)
    ax2.set_title(
        "Temporal Profile of Animal Detection Confidence",
        fontweight="semibold",
        pad=12,
    )
    ax2.grid(axis="both", linestyle=":", linewidth=0.55, alpha=0.42)
    ax2.set_axisbelow(True)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.legend(frameon=False)
    fig2.tight_layout()

    confidence_timeline_png = figure_to_png_bytes(
        fig2,
        dpi=600,
    )

    st.pyplot(fig2, use_container_width=True)
    plt.close(fig2)

    st.download_button(
        label="Export temporal confidence figure · PNG 600 dpi",
        data=confidence_timeline_png,
        file_name=safe_filename(observation["observation_id"]) + "_confidence_timeline_600dpi.png",
        mime="image/png",
    )
else:
    st.subheader(T("Temporal Detection Confidence", "Confianza de detección temporal"))
    st.caption("Available after optional image/video Edge analysis.")

# =========================================================
# 12. CONFIDENCE DISTRIBUTION
# =========================================================

if analysis_available:
    st.subheader(T("Detection Confidence Distribution", "Distribución de confianza de detección"))

    confidence_values = [
        float(candidate["confidence"])
        for candidate in candidate_images
    ]

    if not confidence_values:
        st.info("No retained animal detections are available for a confidence distribution.")
    else:
        fig3, ax3 = plt.subplots(figsize=(9, 4.8), dpi=180)

        if len(confidence_values) == 1:
            ax3.scatter(
                confidence_values,
                [1],
                s=80,
                color=CIVIDIS_DARK,
            )
            ax3.set_ylabel("Observation")
            ax3.set_yticks([1])
        else:
            bin_count = min(
                10,
                max(4, len(confidence_values)),
            )

            ax3.hist(
                confidence_values,
                bins=bin_count,
                range=(0, 1),
                color=CIVIDIS_MID,
                edgecolor=CIVIDIS_DARK,
                linewidth=0.7,
            )
            ax3.set_ylabel("Detection count")

        ax3.axvline(
            confidence_stats["mean"],
            color=CIVIDIS_DARK,
            linewidth=1.4,
            linestyle="-",
            label=f"Mean ({confidence_stats['mean']:.2f})",
        )

        ax3.axvline(
            confidence_stats["median"],
            color=CIVIDIS_LIGHT,
            linewidth=1.3,
            linestyle="--",
            label=f"Median ({confidence_stats['median']:.2f})",
        )

        ax3.set_xlim(0, 1.0)
        ax3.set_xlabel("MegaDetector animal confidence")
        ax3.set_title(
            "Distribution of Retained Animal Detection Confidence",
            fontweight="semibold",
            pad=12,
        )
        ax3.grid(axis="y", linestyle=":", linewidth=0.55, alpha=0.42)
        ax3.set_axisbelow(True)
        ax3.spines["top"].set_visible(False)
        ax3.spines["right"].set_visible(False)
        ax3.legend(frameon=False)
        fig3.tight_layout()

        confidence_distribution_png = figure_to_png_bytes(
            fig3,
            dpi=600,
        )

        st.pyplot(fig3, use_container_width=True)
        plt.close(fig3)

        st.download_button(
            label="Export confidence distribution · PNG 600 dpi",
            data=confidence_distribution_png,
            file_name=safe_filename(observation["observation_id"]) + "_confidence_distribution_600dpi.png",
            mime="image/png",
        )
else:
    st.subheader(T("Detection Confidence Distribution", "Distribución de confianza de detección"))
    st.caption("Available after optional image/video Edge analysis.")

# =========================================================
# 13. DATA REDUCTION
# =========================================================

if analysis_available:
    st.subheader(T("Estimated Candidate Data Reduction", "Reducción estimada de datos candidatos"))

    payload_labels = ["Sampled input", "Filtered event payload"]
    payload_values = [input_mb, candidate_mb]
    payload_colors = [CIVIDIS_DARK, CIVIDIS_LIGHT]

    fig4, ax4 = plt.subplots(figsize=(8.4, 4.7), dpi=180)

    payload_bars = ax4.bar(
        payload_labels,
        payload_values,
        width=0.52,
        color=payload_colors,
        edgecolor="none",
    )

    for bar, value in zip(payload_bars, payload_values):
        ax4.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(max(payload_values) * 0.02, 0.001),
            f"{value:.3f} MB",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax4.set_ylabel("Estimated image payload (MB)")
    ax4.set_title(
        "Estimated Data Retained Before Transmission",
        fontweight="semibold",
        pad=12,
    )
    ax4.grid(axis="y", linestyle=":", linewidth=0.55, alpha=0.42)
    ax4.set_axisbelow(True)
    ax4.spines["top"].set_visible(False)
    ax4.spines["right"].set_visible(False)
    fig4.tight_layout()

    payload_png = figure_to_png_bytes(
        fig4,
        dpi=600,
    )

    st.pyplot(fig4, use_container_width=True)
    plt.close(fig4)

    st.download_button(
        label="Export payload figure · PNG 600 dpi",
        data=payload_png,
        file_name=safe_filename(observation["observation_id"]) + "_payload_reduction_600dpi.png",
        mime="image/png",
    )

    st.caption(
        "This estimate is based on JPEG sizes of sampled frames and detected "
        "animal crops. It is a prototype data-reduction indicator, not direct 5G traffic."
    )
else:
    st.subheader(T("Estimated Candidate Data Reduction", "Reducción estimada de datos candidatos"))
    st.caption("Available after optional image/video Edge analysis.")

# =========================================================
# 5. CAMERA GEOLOCATION & SPATIAL CONTEXT
# =========================================================

st.header(T("7. Camera Location & Spatial Context", "7. Ubicación de cámara y contexto espacial"))

st.markdown(
    """
    <div class="section-intro">
        Geographic position of the camera station that produced this observation.
        These coordinates refer to the monitoring station, not to an inferred
        location of the animal within the video.
    </div>
    """,
    unsafe_allow_html=True,
)

geo_col1, geo_col2 = st.columns(2)

with geo_col1:
    st.number_input(
        T("Latitude", "Latitud"),
        min_value=-90.0,
        max_value=90.0,
        step=0.0001,
        format="%.6f",
        key="camera_latitude",
        help="WGS84 latitude of the camera / monitoring station.",
    )

with geo_col2:
    st.number_input(
        T("Longitude", "Longitud"),
        min_value=-180.0,
        max_value=180.0,
        step=0.0001,
        format="%.6f",
        key="camera_longitude",
        help="WGS84 longitude of the camera / monitoring station.",
    )

camera_latitude = float(st.session_state["camera_latitude"])
camera_longitude = float(st.session_state["camera_longitude"])

camera_map_df = pd.DataFrame(
    {
        "lat": [camera_latitude],
        "lon": [camera_longitude],
    }
)

st.map(camera_map_df, zoom=7)


observation["camera_latitude"] = camera_latitude
observation["camera_longitude"] = camera_longitude
if st.session_state.analysis_result is not None:
    st.session_state.analysis_result["observation"] = observation.copy()


# =========================================================
# 6. COPERNICUS / SENTINEL CONTEXT
# =========================================================

st.header(T("8. Copernicus / Sentinel Context", "8. Contexto Copernicus / Sentinel"))

st.markdown(
    """
    <div class="section-intro">
        Real Copernicus Data Space catalogue discovery around the camera.
        Sentinel-1 contributes cloud-independent SAR acquisition context;
        Sentinel-2 contributes optical multispectral acquisition context.
    </div>
    """,
    unsafe_allow_html=True,
)

sat_col1, sat_col2, sat_col3 = st.columns(3)

with sat_col1:
    satellite_radius_km = st.slider(
        T("Search radius (km)", "Radio de búsqueda (km)"),
        min_value=1,
        max_value=50,
        value=5,
        step=1,
    )

with sat_col2:
    satellite_days_back = st.slider(
        T("Search period (days)", "Periodo de búsqueda (días)"),
        min_value=5,
        max_value=90,
        value=30,
        step=5,
    )

with sat_col3:
    sentinel2_cloud_limit = st.slider(
        T("Sentinel-2 maximum cloud cover", "Cobertura máxima de nubes Sentinel-2"),
        min_value=0,
        max_value=100,
        value=40,
        step=5,
        format="%d%%",
    )

satellite_signature = (
    round(float(camera_latitude), 6),
    round(float(camera_longitude), 6),
    int(satellite_radius_km),
    int(satellite_days_back),
    int(sentinel2_cloud_limit),
)

if st.session_state.satellite_query_signature != satellite_signature:
    # Do not erase a previous query silently if only metadata fields changed elsewhere.
    pass

if st.button(T("Query Copernicus Data Space", "Consultar Copernicus Data Space"), use_container_width=True):
    with st.spinner("Searching Sentinel acquisitions around the camera..."):
        st.session_state.satellite_result = search_copernicus_stac(
            camera_latitude,
            camera_longitude,
            satellite_radius_km,
            satellite_days_back,
            sentinel2_cloud_limit,
        )
        st.session_state.satellite_query_signature = satellite_signature

satellite_result = st.session_state.satellite_result
latest_s1 = None
latest_s2 = None

if satellite_result:
    if satellite_result.get("error"):
        st.warning(
            "Copernicus Data Space could not be queried: "
            + satellite_result["error"]
        )
    else:
        sentinel1_items = satellite_result.get("sentinel_1", [])
        sentinel2_items = satellite_result.get("sentinel_2", [])

        latest_s1 = latest_satellite_summary(sentinel1_items)
        latest_s2 = latest_satellite_summary(sentinel2_items)

        s1m, s2m, s3m, s4m = st.columns(4)

        s1m.metric("Sentinel-1 acquisitions", len(sentinel1_items))
        s2m.metric("Sentinel-2 acquisitions", len(sentinel2_items))
        s3m.metric("Monitoring radius", f"{satellite_radius_km} km")

        s2_cloud = (
            latest_s2.get("cloud_cover")
            if latest_s2
            else None
        )

        s4m.metric(
            "Latest S2 cloud",
            f"{s2_cloud:.1f}%" if s2_cloud is not None else "N/A",
        )

        sat_left, sat_right = st.columns(2)

        with sat_left:
            st.subheader("Sentinel-1 SAR")

            if latest_s1:
                st.markdown(
                    f"""
                    **Latest product**  
                    `{latest_s1["id"]}`

                    **Acquisition**  
                    {latest_s1["datetime"]}

                    **Platform**  
                    {latest_s1["platform"]}

                    **Orbit state**  
                    {latest_s1["orbit_state"]}
                    """
                )
            else:
                st.info("No Sentinel-1 GRD products were returned for this query.")

        with sat_right:
            st.subheader("Sentinel-2 L2A")

            if latest_s2:
                cloud_text = (
                    f'{latest_s2["cloud_cover"]:.1f}%'
                    if latest_s2.get("cloud_cover") is not None
                    else "Not reported"
                )

                st.markdown(
                    f"""
                    **Latest product**  
                    `{latest_s2["id"]}`

                    **Acquisition**  
                    {latest_s2["datetime"]}

                    **Cloud cover**  
                    {cloud_text}

                    **Platform**  
                    {latest_s2["platform"]}
                    """
                )
            else:
                st.info(
                    "No Sentinel-2 L2A products meeting the cloud criterion were returned."
                )

        satellite_frames = []

        df_s1 = satellite_items_dataframe(
            sentinel1_items,
            "Sentinel-1 GRD",
        )

        df_s2 = satellite_items_dataframe(
            sentinel2_items,
            "Sentinel-2 L2A",
        )

        if not df_s1.empty:
            satellite_frames.append(df_s1)

        if not df_s2.empty:
            satellite_frames.append(df_s2)

        if satellite_frames:
            satellite_df = pd.concat(
                satellite_frames,
                ignore_index=True,
            )

            with st.expander("Satellite acquisition catalogue", expanded=False):
                st.dataframe(
                    satellite_df,
                    use_container_width=True,
                    hide_index=True,
                )

                satellite_csv = (
                    satellite_df
                    .to_csv(index=False)
                    .encode("utf-8")
                )

                satellite_metadata = {
                    "camera_station": {
                        "camera_id": camera_id.strip() or "Not specified",
                        "study_site": study_site.strip() or "Not specified",
                        "latitude": float(camera_latitude),
                        "longitude": float(camera_longitude),
                    },
                    "query": {
                        "radius_km": int(satellite_radius_km),
                        "days_back": int(satellite_days_back),
                        "sentinel2_max_cloud_cover_percent": int(sentinel2_cloud_limit),
                        "queried_at": satellite_result.get("queried_at"),
                        "bbox": satellite_result.get("bbox"),
                    },
                    "sentinel_1_grd": sentinel1_items,
                    "sentinel_2_l2a": sentinel2_items,
                }

                satellite_json = json.dumps(
                    satellite_metadata,
                    indent=2,
                    ensure_ascii=False,
                ).encode("utf-8")

                sat_download_1, sat_download_2 = st.columns(2)

                with sat_download_1:
                    st.download_button(
                        "Download catalogue · CSV",
                        data=satellite_csv,
                        file_name=(
                            safe_filename(
                                camera_id.strip()
                                or observation["observation_id"]
                            )
                            + "_Sentinel_Catalogue.csv"
                        ),
                        mime="text/csv",
                        use_container_width=True,
                        key="satellite_catalogue_csv",
                    )

                with sat_download_2:
                    st.download_button(
                        "Download metadata · JSON",
                        data=satellite_json,
                        file_name=(
                            safe_filename(
                                camera_id.strip()
                                or observation["observation_id"]
                            )
                            + "_Sentinel_Metadata.json"
                        ),
                        mime="application/json",
                        use_container_width=True,
                        key="satellite_metadata_json",
                    )

                st.caption(
                    "CSV is convenient for analysis; JSON preserves the catalogue "
                    "metadata and query context for reproducibility."
                )


else:
    st.info(
        "Query Copernicus to retrieve recent Sentinel-1 and Sentinel-2 acquisition metadata."
    )



# Synchronize the most recent satellite context with the current observation.
_current_sat = st.session_state.satellite_result

if _current_sat and not _current_sat.get("error"):
    _latest_s1 = latest_satellite_summary(_current_sat.get("sentinel_1", []))
    _latest_s2 = latest_satellite_summary(_current_sat.get("sentinel_2", []))

    observation["sentinel1_latest"] = (
        _latest_s1["datetime"] if _latest_s1 else "Not available"
    )
    observation["sentinel2_latest"] = (
        _latest_s2["datetime"] if _latest_s2 else "Not available"
    )
    observation["sentinel2_cloud_cover"] = (
        _latest_s2.get("cloud_cover") if _latest_s2 else None
    )
    observation["sentinel_query_radius_km"] = int(satellite_radius_km)
    observation["sentinel_query_days_back"] = int(satellite_days_back)
    observation["sentinel2_cloud_limit"] = int(sentinel2_cloud_limit)
    observation["sentinel_query_time"] = _current_sat.get("queried_at", "Not available")
else:
    observation["sentinel1_latest"] = observation.get(
        "sentinel1_latest", "Not available"
    )
    observation["sentinel2_latest"] = observation.get(
        "sentinel2_latest", "Not available"
    )
    observation["sentinel2_cloud_cover"] = observation.get(
        "sentinel2_cloud_cover", None
    )

if st.session_state.analysis_result is not None:
    st.session_state.analysis_result["observation"] = observation.copy()


# =========================================================
# 9. PANTHERACAM / PANTHERAEDGE EVENT INGEST
# =========================================================

st.header(T("9. PantheraEDGE Event Ingest", "9. Ingesta de eventos PantheraEDGE"))

st.markdown(
    f"""
    <div class="section-intro">
        {T(
            "This is the cloud-side entry point. PantheraCAM and field sensors feed PantheraEDGE over the low-cost local link; PantheraEDGE filters locally and sends structured evidence toward Panthera LAB over 5G. Streamlit consumes an HTTP bridge in the prototype; MQTT/FastAPI can sit behind that bridge.",
            "Este es el punto de entrada del lado nube. PantheraCAM y los sensores alimentan PantheraEDGE por el enlace local de bajo costo; PantheraEDGE filtra localmente y envía evidencia estructurada hacia Panthera LAB por 5G. En el prototipo Streamlit consume un puente HTTP; MQTT/FastAPI puede operar detrás de ese puente."
        )}
    </div>
    <span class="contract-badge">{PANTHERA_CONTRACT_VERSION}</span>
    <span class="contract-badge">HMAC-SHA256 optional in prototype</span>
    <span class="contract-badge">offline queue compatible</span>
    """,
    unsafe_allow_html=True,
)

ingest_mode = st.radio(
    T("Event source", "Fuente del evento"),
    [
        T("PantheraCAM local demo", "Demo local PantheraCAM"),
        T("PantheraEDGE HTTP bridge", "Puente HTTP PantheraEDGE"),
        T("Manual record only", "Solo registro manual"),
    ],
    horizontal=True,
    key="panthera_ingest_mode",
)

if ingest_mode == T("PantheraCAM local demo", "Demo local PantheraCAM"):
    edge_c1, edge_c2 = st.columns([1, 2])
    with edge_c1:
        simulate_event = st.button(
            T("Simulate PantheraCAM capture", "Simular captura PantheraCAM"),
            use_container_width=True,
            key="simulate_pantheracam_capture",
        )
    if simulate_event:
        simulated_event = create_simulated_edge_event(
            camera_id,
            camera_latitude,
            camera_longitude,
        )
        st.session_state.latest_edge_event = simulated_event
        st.session_state.latest_hmac_status = "NOT_CHECKED"
        st.session_state.edge_node_events.append(simulated_event)
    with edge_c2:
        st.caption(
            T(
                "This simulates the field capture notice. Use the Local Edge Demo media section above to reproduce MegaDetector filtering when the physical node is unavailable.",
                "Esto simula el aviso de captura en campo. Use la sección de demo Edge local para reproducir el filtrado de MegaDetector cuando el nodo físico no esté disponible."
            )
        )

elif ingest_mode == T("PantheraEDGE HTTP bridge", "Puente HTTP PantheraEDGE"):
    remote_edge_endpoint = st.text_input(
        T("PantheraEDGE event endpoint", "Endpoint de eventos PantheraEDGE"),
        placeholder="https://backend.example/api/latest-event",
        help=T(
            "Expected prototype path: field MQTT/HTTP -> FastAPI/broker -> JSON endpoint -> PantheraMONITORING.",
            "Ruta esperada del prototipo: MQTT/HTTP de campo -> FastAPI/broker -> endpoint JSON -> PantheraMONITORING."
        ),
        key="pantheraedge_event_endpoint",
    )

    if st.button(T("Poll PantheraEDGE", "Consultar PantheraEDGE"), use_container_width=True, key="poll_pantheraedge"):
        try:
            remote_event_raw = get_remote_edge_event(remote_edge_endpoint)
            remote_event = normalize_panthera_edge_event(remote_event_raw)
            hmac_status, hmac_accepted = verify_panthera_event_hmac(remote_event)
            st.session_state.latest_hmac_status = hmac_status

            if not hmac_accepted:
                st.error(
                    T(
                        f"Event rejected by Panthera LAB ingest validation: HMAC {hmac_status}.",
                        f"Evento rechazado por la validación de ingesta Panthera LAB: HMAC {hmac_status}."
                    )
                )
            else:
                st.session_state.latest_edge_event = remote_event
                st.session_state.latest_event_contract = remote_event.get("contract_version", PANTHERA_CONTRACT_VERSION)
                st.session_state.edge_node_events.append(remote_event)
                st.success(T("PantheraEDGE event accepted by cloud ingest.", "Evento PantheraEDGE aceptado por la ingesta de nube."))
        except Exception as error:
            st.error(f"PantheraEDGE endpoint error: {error}")

else:
    st.caption(
        T(
            "No field event is required. Continue with the manual scientific record and cloud modules.",
            "No se requiere evento de campo. Continúe con el registro científico manual y los módulos de nube."
        )
    )

latest_edge_event = st.session_state.latest_edge_event

if latest_edge_event:
    normalized_event = normalize_panthera_edge_event(latest_edge_event)
    e1, e2, e3, e4 = st.columns(4)
    e1.metric(T("Ingest status", "Estado de ingesta"), normalized_event.get("status", "RECEIVED"))
    e2.metric(T("Contract", "Contrato"), normalized_event.get("contract_version", PANTHERA_CONTRACT_VERSION))
    e3.metric("HMAC", st.session_state.get("latest_hmac_status", "NOT_CHECKED"))
    confidence_value = normalized_event.get("confidence")
    e4.metric(
        T("Event confidence", "Confianza del evento"),
        f"{float(confidence_value):.1%}" if confidence_value is not None else "N/A",
    )

    event_c1, event_c2 = st.columns(2)
    with event_c1:
        st.markdown(
            f"""
            **Event ID:** `{normalized_event.get('event_id')}`  
            **Camera / node:** `{normalized_event.get('camera_id')}`  
            **Event:** `{normalized_event.get('event')}`  
            **Timestamp:** `{normalized_event.get('timestamp')}`
            """
        )
    with event_c2:
        st.markdown(
            f"""
            **Transport:** `{normalized_event.get('transport')}`  
            **Class:** `{normalized_event.get('class') or 'N/A'}`  
            **Image:** {normalized_event.get('image_url') or 'N/A'}  
            **Clip:** {normalized_event.get('clip_url') or 'N/A'}
            """
        )

    with st.expander(T("Latest PantheraEDGE event JSON", "JSON del último evento PantheraEDGE"), expanded=False):
        st.json(normalized_event)
else:
    st.info(T("No PantheraEDGE event has been ingested yet.", "Todavía no se ha ingerido un evento PantheraEDGE."))

# Synchronize cloud record fields that are safe to derive from an ingested event.
if latest_edge_event:
    normalized_event = normalize_panthera_edge_event(latest_edge_event)
    observation["edge_event_id"] = normalized_event.get("event_id", observation.get("edge_event_id", "Not available"))
    observation["edge_contract_version"] = normalized_event.get("contract_version", PANTHERA_CONTRACT_VERSION)
    observation["edge_hmac_status"] = st.session_state.get("latest_hmac_status", "NOT_CHECKED")
    observation["edge_transport"] = normalized_event.get("transport")
    observation["edge_event_timestamp"] = normalized_event.get("timestamp")
    if normalized_event.get("image_url") and not observation.get("image_url"):
        observation["image_url"] = normalized_event.get("image_url")
    if normalized_event.get("clip_url") and not observation.get("video_url"):
        observation["video_url"] = normalized_event.get("clip_url")

if st.session_state.analysis_result is not None:
    st.session_state.analysis_result["observation"] = observation.copy()


# =========================================================
# 10. 5G TRUNK / CONNECTIVITY BENCHMARK
# =========================================================

st.header(T("10. 5G Trunk & Connectivity", "10. Troncal 5G y conectividad"))

st.markdown(
    """
    <div class="section-intro">
        PantheraEDGE sends filtered evidence across the wide-area trunk. Values can be used as
        reference assumptions today and replaced by measured Nokia/testbed values during the demo.
        4G or satellite remain fallback paths; the local Edge keeps its offline queue if the trunk fails.
    </div>
    """,
    unsafe_allow_html=True,
)

network_metric_mode = st.radio(
    T("Metric source", "Fuente de métricas"),
    [T("Reference / estimated", "Referencia / estimada"), T("Measured testbed values", "Valores medidos en testbed")],
    horizontal=True,
    key="network_metric_mode_radio",
)

metric_is_measured = network_metric_mode == T("Measured testbed values", "Valores medidos en testbed")
network_col1, network_col2 = st.columns(2)

with network_col1:
    simulated_5g_throughput = st.number_input(
        T("5G uplink throughput (Mbps)", "Throughput de subida 5G (Mbps)"),
        min_value=0.1,
        max_value=1000.0,
        value=20.0,
        step=1.0,
        help=T("Enter measured throughput when testbed data is available.", "Ingrese el throughput medido cuando existan datos del testbed."),
    )

with network_col2:
    simulated_5g_latency = st.number_input(
        T("5G latency / RTT reference (ms)", "Latencia / RTT 5G de referencia (ms)"),
        min_value=0.0,
        max_value=1000.0,
        value=25.0,
        step=1.0,
        help=T("Use the same definition consistently across 5G and 4G comparisons.", "Use la misma definición de forma consistente en comparaciones 5G y 4G."),
    )

raw_network = estimate_network_transmission(input_mb, simulated_5g_throughput, simulated_5g_latency)
edge_network = estimate_network_transmission(candidate_mb, simulated_5g_throughput, simulated_5g_latency)
transmission_time_saved = max(raw_network["estimated_total_seconds"] - edge_network["estimated_total_seconds"], 0.0)
avoided_mb = max(input_mb - candidate_mb, 0.0)

n1, n2, n3, n4 = st.columns(4)
n1.metric(T("Raw sampled input", "Entrada cruda muestreada"), f"{input_mb:.3f} MB")
n2.metric(T("Filtered event payload", "Payload filtrado del evento"), f"{candidate_mb:.3f} MB")
n3.metric(T("Avoided WAN traffic", "Tráfico WAN evitado"), f"{avoided_mb:.3f} MB")
n4.metric(T("Payload reduction", "Reducción de payload"), f"{payload_reduction:.1f}%")

n5, n6, n7, n8 = st.columns(4)
n5.metric(T("5G uplink", "Subida 5G"), f"{simulated_5g_throughput:.1f} Mbps")
n6.metric(T("Latency / RTT input", "Latencia / RTT ingresado"), f"{simulated_5g_latency:.0f} ms")
n7.metric(T("Raw transfer estimate", "Transferencia cruda estimada"), f"{raw_network['estimated_total_seconds']:.3f} s")
n8.metric(T("Filtered transfer estimate", "Transferencia filtrada estimada"), f"{edge_network['estimated_total_seconds']:.3f} s")

source_label = T("MEASURED INPUT", "ENTRADA MEDIDA") if metric_is_measured else T("REFERENCE INPUT", "ENTRADA DE REFERENCIA")
st.caption(f"{source_label} · " + T(
    "Transfer times are deterministic calculations from payload, throughput and latency; they are not themselves packet-level measurements.",
    "Los tiempos de transferencia son cálculos deterministas a partir del payload, throughput y latencia; no son por sí mismos mediciones a nivel de paquetes."
))

with st.expander(T("Optional 4G fallback comparison", "Comparación opcional con fallback 4G"), expanded=False):
    fourg_c1, fourg_c2 = st.columns(2)
    with fourg_c1:
        fallback_4g_throughput = st.number_input("4G uplink (Mbps)", min_value=0.1, max_value=500.0, value=8.0, step=0.5)
    with fourg_c2:
        fallback_4g_latency = st.number_input("4G latency / RTT (ms)", min_value=0.0, max_value=1000.0, value=60.0, step=1.0)
    fallback_edge = estimate_network_transmission(candidate_mb, fallback_4g_throughput, fallback_4g_latency)
    f1, f2, f3 = st.columns(3)
    f1.metric("5G filtered transfer", f"{edge_network['estimated_total_seconds']:.3f} s")
    f2.metric("4G filtered transfer", f"{fallback_edge['estimated_total_seconds']:.3f} s")
    delta = fallback_edge['estimated_total_seconds'] - edge_network['estimated_total_seconds']
    f3.metric(T("Difference", "Diferencia"), f"{delta:.3f} s")

observation["network_metric_source"] = "measured_input" if metric_is_measured else "reference_input"
observation["network_throughput_mbps"] = simulated_5g_throughput
observation["network_latency_ms"] = simulated_5g_latency
observation["raw_transmission_seconds"] = raw_network["estimated_total_seconds"]
observation["edge_transmission_seconds"] = edge_network["estimated_total_seconds"]
observation["transmission_time_saved_seconds"] = transmission_time_saved
observation["transmission_avoided_mb"] = avoided_mb
observation["input_mb"] = input_mb
observation["candidate_mb"] = candidate_mb

if st.session_state.analysis_result is not None:
    st.session_state.analysis_result["observation"] = observation.copy()

# =========================================================
# 11. PANTHERA LAB CLOUD PERSISTENCE
# =========================================================

st.header(T("11. Panthera LAB Cloud Persistence", "11. Persistencia en Nube Panthera LAB"))

st.markdown(
    """
    <div class="section-intro">
        Prototype cloud persistence uses Supabase as the current Panthera LAB storage/database backend.
        Retained event evidence is uploaded to <code>capturas-animales</code> and structured monitoring
        variables are inserted into <code>pantheraid-monitoring</code>. In the target architecture,
        PantheraEDGE talks to a cloud ingest/API layer first; Supabase remains an internal persistence service.
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Species is sent only when the observation has been explicitly researcher-validated."
)

panthera_key_available = bool(get_panthera_supabase_key())

panthera_schema_info = (
    get_pantheraid_schema_info()
    if panthera_key_available
    else {"available": False, "columns": [], "error": "Supabase key is not configured."}
)

pc1, pc2, pc3, pc4 = st.columns(4)
pc1.metric(T("Retained full frames", "Frames completos retenidos"), len(retained_full_frames))
pc2.metric(T("Animal detections", "Detecciones de animales"), len(candidate_images))
pc3.metric(T("Storage bucket", "Bucket de almacenamiento"), PANTHERA_STORAGE_BUCKET)
pc4.metric(T("Connection key", "Clave de conexión"), T("Configured", "Configurada") if panthera_key_available else T("Missing", "Faltante"))

if panthera_key_available:
    st.caption(
        T(
            "Note: Supabase RLS is enabled on PantheraID. Reading existing rows may be restricted; "
            "transmission requires an INSERT policy and deletion requires DELETE permission.",
            "Nota: PantheraID tiene RLS habilitado. La lectura de filas puede estar restringida; "
            "la transmisión requiere una política INSERT y la eliminación requiere permiso DELETE."
        )
    )

    if panthera_schema_info.get("available"):
        detected_columns = panthera_schema_info.get("columns", [])
        schema_source = panthera_schema_info.get("source", "openapi")
        source_label = (
            "owner-confirmed table structure"
            if schema_source == "owner-confirmed"
            else "Supabase OpenAPI"
        )
        st.caption(
            f"PantheraID schema loaded · {len(detected_columns)} writable/known column(s) · "
            f"source: {source_label}."
        )
        with st.expander("PantheraID schema diagnostics", expanded=False):
            st.write("Detected columns:")
            st.code("\n".join(detected_columns))
    else:
        st.caption(
            "PantheraID schema auto-discovery is unavailable; transmission will use the "
            "configured payload and report the exact database error if a field is rejected."
        )

if not retained_full_frames:
    st.caption("PantheraID transmission requires an analyzed image/video frame. The rest of PantheraMONITORING does not.")

if not panthera_key_available:
    st.warning(
        "Supabase transmission is disabled until SUPABASE_PUBLISHABLE_KEY is added "
        "to Streamlit Secrets. Do not paste the key into app.py."
    )

send_validated_species = st.checkbox(
    T("Send researcher-validated species when available", "Enviar especie validada por investigador cuando esté disponible"),
    value=False,
    help=(
        "Off by default. When disabled, species is always sent as null. "
        "Enable only after the species annotation has been researcher validated."
    ),
    key="pantheraid_send_validated_species",
)

species_for_panthera = None
if send_validated_species:
    species_candidate = str(observation.get("species", "")).strip()
    validation_value = str(observation.get("validation_status", "")).strip()
    if (
        species_candidate
        and species_candidate not in {"Unassigned", "Unknown", "None", "null"}
        and validation_value in {"researcher_validated", "field_verified"}
    ):
        species_for_panthera = species_candidate
    else:
        st.info(
            "A validated species is not currently available, so species will remain null."
        )

transmit_panthera = st.button(
    T("Persist Retained Events in Panthera LAB", "Persistir eventos retenidos en Panthera LAB"),
    type="primary",
    use_container_width=True,
    disabled=(not panthera_key_available or not retained_full_frames or not candidate_images),
    key="transmit_pantheraid_records",
)

if transmit_panthera:
    frame_by_sample = {
        int(item["sample"]): item
        for item in retained_full_frames
        if item.get("jpeg_bytes")
    }

    upload_url_by_sample = {}
    transmission_rows = []
    transmit_progress = st.progress(0)
    transmit_status = st.empty()

    total_to_send = len(candidate_images)

    for detection_index, candidate in enumerate(candidate_images, start=1):
        sample_id = int(candidate.get("sample", 0))
        frame_record = frame_by_sample.get(sample_id)

        if not frame_record:
            transmission_rows.append(
                {
                    "detection": detection_index,
                    "sample": sample_id,
                    "status": "ERROR",
                    "detail": "Full frame unavailable",
                    "numero_detection": None,
                    "image_url": None,
                }
            )
            continue

        try:
            transmit_status.write(
                f"Transmitting detection {detection_index}/{total_to_send}..."
            )

            if sample_id not in upload_url_by_sample:
                timestamp_token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                camera_token = safe_filename(observation.get("camera_id", "camera"))
                observation_token = safe_filename(observation["observation_id"])

                object_path = (
                    f"{camera_token}/{observation_token}/"
                    f"sample_{sample_id:03d}_{timestamp_token}.jpg"
                )

                upload_url_by_sample[sample_id] = upload_full_frame_to_supabase(
                    frame_record["jpeg_bytes"],
                    object_path,
                )

            numero_detection = next_panthera_detection_number()

            candidate_payload = build_pantheraid_payload(
                numero_detection=numero_detection,
                latitude=observation.get("camera_latitude"),
                longitude=observation.get("camera_longitude"),
                altitude=observation.get("altitude_m"),
                temperature=observation.get("temperature_c"),
                humidity=observation.get("humidity_percent"),
                image_url=upload_url_by_sample[sample_id],
                species=species_for_panthera,
            )

            payload, ignored_fields = filter_pantheraid_payload(
                candidate_payload,
                panthera_schema_info,
            )

            if panthera_schema_info.get("available") and not payload:
                raise RuntimeError(
                    "PantheraID schema was detected, but none of the PantheraMONITORING payload fields "
                    "match the table columns."
                )

            insert_pantheraid_record(payload)

            transmission_rows.append(
                {
                    "detection": detection_index,
                    "sample": sample_id,
                    "status": "SENT",
                    "detail": (
                        "Inserted successfully"
                        if not ignored_fields
                        else "Inserted successfully; ignored unsupported fields: " + ", ".join(ignored_fields)
                    ),
                    "numero_detection": numero_detection,
                    "image_url": upload_url_by_sample[sample_id],
                }
            )

            st.session_state.pantheraid_transmission_log.append(
                {
                    "observation_id": observation["observation_id"],
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "payload": payload,
                    "sample": sample_id,
                    "candidate_index": detection_index,
                }
            )

        except Exception as error:
            transmission_rows.append(
                {
                    "detection": detection_index,
                    "sample": sample_id,
                    "status": "ERROR",
                    "detail": str(error),
                    "numero_detection": None,
                    "image_url": upload_url_by_sample.get(sample_id),
                }
            )

        transmit_progress.progress(min(detection_index / max(total_to_send, 1), 1.0))

    transmit_status.empty()

    transmission_df = pd.DataFrame(transmission_rows)
    successful_sends = int((transmission_df["status"] == "SENT").sum())
    failed_sends = int((transmission_df["status"] == "ERROR").sum())

    if successful_sends:
        st.success(
            f"{successful_sends} event record(s) persisted in Panthera LAB / Supabase."
        )
    if failed_sends:
        st.warning(
            f"{failed_sends} detection record(s) could not be transmitted. "
            "Review the details below."
        )

    st.dataframe(
        transmission_df,
        use_container_width=True,
        hide_index=True,
    )

# Show deletion result after a rerun.
if st.session_state.get("pantheraid_delete_notice"):
    notice = st.session_state.pop("pantheraid_delete_notice")
    if notice.get("level") == "success":
        st.success(notice.get("message"))
    else:
        st.warning(notice.get("message"))

if st.session_state.pantheraid_transmission_log:
    with st.expander(
        T("Manage transmitted detections", "Gestionar detecciones transmitidas"),
        expanded=False,
    ):
        st.caption(
            T(
                "Deletion is intentionally limited to records persisted by PantheraMONITORING in this session. "
                "If several detections share the same full-frame image, the image is kept until the last "
                "current-session reference is removed.",
                "La eliminación se limita a registros persistidos por PantheraMONITORING en esta sesión. "
                "Si varias detecciones comparten el mismo frame completo, la imagen se conserva hasta "
                "eliminar la última referencia de la sesión."
            )
        )

        delete_options = []
        for index, item in enumerate(st.session_state.pantheraid_transmission_log):
            payload = item.get("payload", {})
            delete_options.append(
                (
                    index,
                    f"#{payload.get('numero_detection')} · "
                    f"{T('sample', 'muestra')} {item.get('sample')} · "
                    f"{item.get('observation_id')}"
                )
            )

        selected_delete_label = st.selectbox(
            T("Detection to delete", "Detección a eliminar"),
            options=[label for _, label in delete_options],
            key="pantheraid_delete_selection",
        )
        selected_delete_index = next(
            idx for idx, label in delete_options if label == selected_delete_label
        )
        selected_item = st.session_state.pantheraid_transmission_log[selected_delete_index]
        selected_payload = selected_item.get("payload", {})
        selected_url = selected_payload.get("image_url")
        selected_number = selected_payload.get("numero_detection")

        same_url_count = sum(
            1
            for item in st.session_state.pantheraid_transmission_log
            if item.get("payload", {}).get("image_url") == selected_url
        )

        st.write(
            T("Image reference count in this session:", "Referencias a esta imagen en la sesión:"),
            same_url_count,
        )

        delete_confirm = st.checkbox(
            T(
                "I understand this permanently deletes the PantheraID database record.",
                "Entiendo que esto elimina permanentemente el registro de PantheraID."
            ),
            key="pantheraid_delete_confirm",
        )

        if st.button(
            T("Delete detection", "Eliminar detección"),
            type="primary",
            use_container_width=True,
            disabled=not delete_confirm,
            key="pantheraid_delete_button",
        ):
            try:
                delete_pantheraid_record(selected_number, selected_url)

                storage_message = ""
                if same_url_count <= 1 and selected_url:
                    try:
                        delete_panthera_storage_object(selected_url)
                        storage_message = T(
                            " The associated Storage image was also deleted.",
                            " La imagen asociada en Storage también fue eliminada."
                        )
                    except Exception as storage_error:
                        storage_message = T(
                            f" The database row was deleted, but the Storage image could not be deleted: {storage_error}",
                            f" La fila de la base fue eliminada, pero la imagen de Storage no pudo eliminarse: {storage_error}"
                        )
                else:
                    storage_message = T(
                        " The shared Storage image was kept because another transmitted detection still references it.",
                        " La imagen compartida se conservó porque otra detección transmitida todavía la referencia."
                    )

                del st.session_state.pantheraid_transmission_log[selected_delete_index]
                st.session_state.pantheraid_delete_notice = {
                    "level": "success",
                    "message": T(
                        f"Detection #{selected_number} was deleted from PantheraID.{storage_message}",
                        f"La detección #{selected_number} fue eliminada de PantheraID.{storage_message}"
                    ),
                }
                st.rerun()

            except Exception as delete_error:
                st.error(
                    T(
                        f"Deletion failed: {delete_error}",
                        f"No se pudo eliminar: {delete_error}"
                    )
                )


if st.session_state.pantheraid_transmission_log:
    with st.expander(
        T("Panthera LAB persistence log", "Registro de persistencia Panthera LAB"),
        expanded=False,
    ):
        log_rows = []
        for item in st.session_state.pantheraid_transmission_log:
            payload = item.get("payload", {})
            log_rows.append(
                {
                    "sent_at": item.get("sent_at"),
                    "observation_id": item.get("observation_id"),
                    "numero_detection": payload.get("numero_detection"),
                    "sample": item.get("sample"),
                    "latitude": payload.get("latitude"),
                    "longitude": payload.get("longitude"),
                    "altitude": payload.get("altitude"),
                    "temperature": payload.get("temperature"),
                    "humidity": payload.get("humidity"),
                    "type_identify": payload.get("type_identify"),
                    "species": payload.get("species"),
                    "image_url": payload.get("image_url"),
                }
            )

        st.dataframe(
            pd.DataFrame(log_rows),
            use_container_width=True,
            hide_index=True,
        )

# =========================================================
# 11B. INSTITUTIONAL OUTPUTS
# =========================================================

st.subheader(T("Institutional Outputs", "Salidas institucionales"))
st.markdown(
    """
    <div class="section-intro">
        The cloud layer converts the same validated event into formats or APIs appropriate for each consumer.
        Only GeoJSON/JSON export is implemented here; CAP, Camtrap DP and guardaparque alert adapters remain integration targets.
    </div>
    """,
    unsafe_allow_html=True,
)

out1, out2, out3, out4 = st.columns(4)
out1.metric("SINAC", "GeoJSON")
out2.metric(T("Researchers", "Investigadores"), "JSON / CSV")
out3.metric("CNE / Bomberos", T("CAP adapter · planned", "Adaptador CAP · previsto"))
out4.metric(T("Rangers", "Guardaparques"), T("Alert/API · planned", "Alerta/API · prevista"))

current_geojson = build_observation_geojson(observation)
geojson_bytes = json.dumps(current_geojson, ensure_ascii=False, indent=2, default=str).encode("utf-8")
st.download_button(
    T("Download observation · GeoJSON", "Descargar observación · GeoJSON"),
    data=geojson_bytes,
    file_name=safe_filename(observation["observation_id"]) + ".geojson",
    mime="application/geo+json",
    use_container_width=True,
    key="download_observation_geojson",
)

# =========================================================
# 18. SCIENTIFIC OBSERVATION
# =========================================================

st.header(T("12. Scientific Observation", "12. Observación científica"))

obs1, obs2, obs3 = st.columns(3)

obs1.metric(
    "Observation ID",
    observation["observation_id"],
)

obs2.metric(
    "Species annotation",
    observation["species"],
)

obs3.metric(
    T("Individual ID", "ID del individuo"),
    observation["individual_id"],
)

detail_col1, detail_col2 = st.columns(2)

with detail_col1:
    st.markdown(
        f"""
        **Observation name**  
        {observation["observation_name"]}

        **Camera / Station**  
        {observation["camera_id"]}

        **Study site**  
        {observation["study_site"]}

        **Coordinates**  
        {observation["camera_latitude"]:.6f}, {observation["camera_longitude"]:.6f}
        """
    )

with detail_col2:
    st.markdown(
        f"""
        **Observer / Researcher**  
        {observation["observer"]}

        **Media type**  
        {observation.get("media_type", "none")}

        **Source video**  
        {observation.get("source_video", "Not provided")}

        **Source image**  
        {observation.get("source_image", "Not provided")}

        **Edge event ID**  
        {observation["edge_event_id"]}

        **Analysis date**  
        {observation["analysis_date"]} {observation["analysis_time"]}

        **Event date/time (UTC)**  
        {observation.get("event_datetime_utc", "Not specified")}

        **Validation status**  
        {observation.get("validation_status", "researcher_review_pending")}
        """
    )

st.subheader(T("Structured Monitoring Variables", "Variables estructuradas de monitoreo"))
sm1, sm2, sm3, sm4, sm5 = st.columns(5)
sm1.metric(
    "Altitude",
    f"{observation.get('altitude_m'):.0f} m"
    if observation.get("altitude_m") is not None else "N/A",
)
sm2.metric(
    "Temperature",
    f"{observation.get('temperature_c'):.1f} °C"
    if observation.get("temperature_c") is not None else "N/A",
)
sm3.metric(
    "Humidity",
    f"{observation.get('humidity_percent'):.1f}%"
    if observation.get("humidity_percent") is not None else "N/A",
)
sm4.metric(T("Sex", "Sexo"), observation.get("sex", "unknown"))
sm5.metric(T("Age class", "Clase de edad"), observation.get("age_class", "unknown"))

st.markdown(
    f"""
    **Viewpoint:** {observation.get("viewpoint", "unknown")}  
    **Behavior:** {observation.get("behavior", "") or "Not specified"}  
    **Research institution:** {observation.get("organization") or "Not specified"}  
    **Project code:** {observation.get("project_code") or "Not specified"}  
    **Sampling effort:** {observation.get("camera_nights") if observation.get("camera_nights") is not None else "Not specified"} camera-nights  
    **Identification method:** {observation.get("identification_method", "not_verified")}  
    **Environmental data source:** {observation.get("environmental_source", "not_specified")}  
    **Habitat / microhabitat:** {observation.get("habitat_notes", "") or "Not specified"}  
    **Image URL / URI:** {observation.get("image_url", "") or "Not specified"}  
    **Video URL / URI:** {observation.get("video_url", "") or "Not specified"}
    """
)

with st.expander(
    "Research / Field Notes",
    expanded=True,
):
    st.write(
        observation["notes"]
    )

st.caption(
    "Species and individual identity in this record are researcher-provided annotations."
)

# =========================================================
# STRUCTURED OBSERVATION EXPORT
# =========================================================

observation_export = observation.copy()
observation_export["pantheraid_integration"] = {
    "table_endpoint": PANTHERA_TABLE_ENDPOINT,
    "storage_bucket": PANTHERA_STORAGE_BUCKET,
    "transmitted_records": len(st.session_state.pantheraid_transmission_log),
}

observation_json_bytes = json.dumps(
    observation_export,
    indent=2,
    ensure_ascii=False,
    default=str,
).encode("utf-8")

st.download_button(
    T("Download current observation · JSON", "Descargar observación actual · JSON"),
    data=observation_json_bytes,
    file_name=safe_filename(observation["observation_id"]) + "_observation.json",
    mime="application/json",
    use_container_width=True,
    key="download_current_observation_json",
)

# =========================================================
# SAVE OBSERVATION
# =========================================================

save_observation = st.button(
    T("Save Observation", "Guardar observación"),
    type="primary",
    use_container_width=True,
)

if save_observation:
    existing_ids = [
        item["observation_id"]
        for item in st.session_state.observation_registry
    ]

    if observation["observation_id"] not in existing_ids:
        st.session_state.observation_registry.append(observation.copy())
        st.success(
            f'Observation {observation["observation_id"]} was added '
            "to the current PantheraMONITORING registry."
        )
    else:
        st.session_state.observation_registry = [
            observation.copy() if item.get("observation_id") == observation["observation_id"] else item
            for item in st.session_state.observation_registry
        ]
        st.success(
            f'Observation {observation["observation_id"]} was updated '
            "in the current PantheraMONITORING registry."
        )

# =========================================================
# 19. OBSERVATION REGISTRY
# =========================================================

st.header(T("13. Observation Registry", "13. Registro de observaciones"))

st.markdown(
    """
    <div class="section-intro">
        Observations saved during the current application session.
        Records can be reviewed or removed here. This registry is temporary
        and is not yet a persistent database.
    </div>
    """,
    unsafe_allow_html=True,
)

if not st.session_state.observation_registry:
    st.info("No observations have been saved during this session.")
else:
    registry_df = pd.DataFrame(
        st.session_state.observation_registry
    )

    preferred_columns = [
        "observation_id",
        "observation_name",
        "analysis_date",
        "camera_id",
        "study_site",
        "organization",
        "project_code",
        "sampling_protocol",
        "camera_model",
        "camera_nights",
        "identification_method",
        "evidence_quality",
        "environmental_source",
        "species",
        "individual_id",
        "event_datetime_utc",
        "altitude_m",
        "temperature_c",
        "humidity_percent",
        "sex",
        "age_class",
        "viewpoint",
        "behavior",
        "validation_status",
        "image_url",
        "video_url",
        "animal_detections",
        "confidence_mean",
        "confidence_median",
        "confidence_std",
        "positive_frame_rate",
        "estimated_payload_reduction",
        "transmission_avoided_mb",
        "sentinel1_latest",
        "sentinel2_latest",
    ]

    visible_columns = [
        column
        for column in preferred_columns
        if column in registry_df.columns
    ]

    st.dataframe(
        registry_df[visible_columns],
        use_container_width=True,
        hide_index=True,
    )

    backup_csv_col, backup_json_col = st.columns(2)
    with backup_csv_col:
        st.download_button(
            T("Back up registry · CSV", "Respaldar registro · CSV"),
            data=registry_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="PantheraEDGE_registro.csv",
            mime="text/csv",
            key="backup_registry_csv",
            use_container_width=True,
        )
    with backup_json_col:
        st.download_button(
            T("Back up registry · JSON", "Respaldar registro · JSON"),
            data=json.dumps(st.session_state.observation_registry, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
            file_name="PantheraEDGE_registro.json",
            mime="application/json",
            key="backup_registry_json",
            use_container_width=True,
        )

    registry_count = len(
        st.session_state.observation_registry
    )

    assigned_individuals = {
        obs["individual_id"]
        for obs in st.session_state.observation_registry
        if obs.get("individual_id") not in ["Unassigned", "Unknown", ""]
    }

    rr1, rr2 = st.columns(2)

    rr1.metric(
        "Saved observations",
        registry_count,
    )

    rr2.metric(
        "Assigned individuals",
        len(assigned_individuals),
    )


    st.subheader(T("Registry Management", "Gestión del registro"))

    removable_ids = registry_df["observation_id"].tolist()

    selected_remove_id = st.selectbox(
        T("Observation to remove", "Observación a eliminar"),
        options=removable_ids,
        index=0,
        help="Select an observation currently stored in this session registry.",
        key="registry_remove_id",
    )

    st.markdown(
        '<div class="registry-danger-note">'
        'Removal affects only the current temporary session registry.'
        '</div>',
        unsafe_allow_html=True,
    )

    remove_confirm = st.checkbox(
        T("I confirm that I want to remove this observation", "Confirmo que deseo eliminar esta observación"),
        key="registry_remove_confirm",
    )

    if st.button(
        T("Remove Observation", "Eliminar observación"),
        type="primary",
        use_container_width=True,
        disabled=not remove_confirm,
        key="registry_remove_button",
    ):
        st.session_state.observation_registry = [
            item
            for item in st.session_state.observation_registry
            if item.get("observation_id") != selected_remove_id
        ]

        st.success(
            f"Observation {selected_remove_id} was removed from the current session registry."
        )
        st.rerun()

    if assigned_individuals:
        st.subheader(T("Individual Encounter History", "Historial de encuentros por individuo"))

        individual_history = (
            registry_df[
                registry_df["individual_id"].isin(
                    assigned_individuals
                )
            ]
            .groupby(
                "individual_id",
                as_index=False,
            )
            .agg(
                observations=("observation_id", "count"),
                first_recorded=("analysis_date", "min"),
                last_recorded=("analysis_date", "max"),
            )
        )

        st.dataframe(
            individual_history,
            use_container_width=True,
            hide_index=True,
        )

        if len(
            individual_history[
                individual_history["observations"] > 1
            ]
        ) > 0:
            st.info(
                "Repeated individual IDs represent researcher-assigned encounter "
                "histories, not automated individual re-identification."
            )

# =========================================================
# 21. SCIENTIFIC REPORT
# =========================================================

st.header(T("14. Final Scientific Report", "14. Informe científico final"))

st.markdown(
    """
    <div class="section-intro">
        Export the current observation, AI results, environmental context and Panthera LAB persistence status.
    </div>
    """,
    unsafe_allow_html=True,
)

report_name = st.text_input(
    T("Report file name", "Nombre del archivo del informe"),
    value=observation["observation_name"],
    help="Choose a descriptive name for the exported report.",
)

try:
    pdf_data = create_observation_pdf(
        observation,
        candidate_images,
    )

    pdf_filename = (
        safe_filename(report_name)
        + "_PantheraMONITORING_Report.pdf"
    )

    st.download_button(
        label=T("Download Scientific Observation Report · PDF", "Descargar informe de observación científica · PDF"),
        data=pdf_data,
        file_name=pdf_filename,
        mime="application/pdf",
        use_container_width=True,
        type="primary",
    )

    st.caption(
        "The report includes observation metadata, camera coordinates, Edge AI "
        "metrics, confidence statistics, estimated network metrics, latest "
        "Sentinel-1 / Sentinel-2 acquisition context, Panthera LAB persistence status, researcher annotations "
        "and up to six candidate animal images. The full Sentinel catalogue "
        "remains available separately as CSV or JSON."
    )

except Exception as pdf_error:
    st.error(
        "The scientific record is available, but the PDF report could not be generated."
    )
    st.code(str(pdf_error))


# =========================================================
# TECHNICAL APPENDIX
# =========================================================

st.divider()
st.header(T("Technical Appendix", "Apéndice técnico"))
st.caption(
    "Engineering diagnostics, architecture and methodological notes are kept here "
    "so they do not interrupt the scientific review workflow."
)

# =========================================================
# 17. FRAME-LEVEL EDGE DECISIONS
# =========================================================

st.subheader(T("Annotated Frame Review", "Revisión de frames anotados"))

if compact_view and annotated_images:
    st.caption(f"{len(annotated_images)} annotated frame(s) available. Disable Compact scientific view to inspect them.")

for index, item in enumerate(
    annotated_images if not compact_view else [],
    start=1,
):
    with st.expander(
        f"Sample {index:02d} · t={item['time']:.1f} s · {item['decision']}"
    ):
        st.image(
            item["image"],
            use_container_width=True,
        )

# =========================================================
# 20. FRAME-LEVEL DATA
# =========================================================

st.subheader(T("Frame-Level Analysis Data", "Datos de análisis por frame"))

if not compact_view:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.caption(
        f"{len(df)} frame-level record(s) available. Disable Compact scientific view to inspect the table."
        if len(df)
        else "No frame-level AI records are associated with this field observation."
    )

csv_data = df.to_csv(
    index=False
).encode(
    "utf-8"
)

csv_filename = (
    safe_filename(
        observation["observation_name"]
    )
    + "_PantheraMONITORING_Data.csv"
)

st.download_button(
    label="Download frame-level data · CSV",
    data=csv_data,
    file_name=csv_filename,
    mime="text/csv",
    use_container_width=True,
)

# =========================================================
# PANTHERA LAB REFERENCE ARCHITECTURE
# =========================================================

st.subheader(T("System Architecture", "Arquitectura del sistema"))

workflow = [
    ("01", "Campo · sentidos", "PantheraCAM, Browning/Pi cameras, FIREWATCH and virtual sensors capture locally; Wi-Fi 2.4 GHz / LoRa is the low-cost last mile."),
    ("02", "PantheraEDGE · médula", "MegaDetector V6, sensor fusion, event threshold, offline queue and local alerting reduce raw media before wide-area transmission."),
    ("03", "Troncal 5G", "Filtered evidence crosses the 5G trunk; 4G or satellite can act as fallback. Testbed measurements replace reference values when available."),
    ("04", "Nube Panthera LAB · cerebro", "Cloud ingest validates the event contract/HMAC, persists evidence, runs PantheraID/downstream verification and feeds PantheraMONITORING."),
    ("05", "Salida institucional", "Validated events are exposed to SINAC, researchers, guardaparques and future emergency-response adapters in the format each consumer needs."),
    ("06", "Copernicus / Sentinel", "Remote-sensing acquisitions enter through the cloud as independent environmental context; they are not treated as field-sensor measurements."),
]

workflow_rows = []

for number, title, description in workflow:
    workflow_rows.append(
        (
            '<div class="workflow-row">'
            f'<div class="workflow-number">{number}</div>'
            f'<div class="workflow-title">{title}</div>'
            f'<div class="workflow-description">{description}</div>'
            '</div>'
        )
    )

workflow_html = (
    '<div class="workflow-container">'
    + "".join(workflow_rows)
    + '</div>'
)

with st.expander("View system architecture", expanded=False):
    st.markdown(
        workflow_html,
        unsafe_allow_html=True,
    )

# =========================================================
# 22. ANALYSIS SUMMARY
# =========================================================

with st.expander("Interpretation, limitations & prototype scope", expanded=False):
    st.divider()
    st.subheader(T("Interpretation & Methodological Limits", "Interpretación y límites metodológicos"))

    if analysis_available:
        st.markdown(
            f"""
            <div class="interpretation-box">
            <b>Edge filtering</b><br><br>
            {total_samples} sampled frame(s) were analyzed; {frames_kept} were retained and
            {frames_discarded} were discarded. Filtered event payload reduction was
            <b>{payload_reduction:.1f}%</b> in the prototype calculation.<br><br>
            <b>Detection confidence</b><br><br>
            {confidence_stats["count"]} retained animal detection(s); mean
            <b>{confidence_stats["mean"]:.1%}</b>, median
            <b>{confidence_stats["median"]:.1%}</b>, peak
            <b>{confidence_stats["maximum"]:.1%}</b>.<br><br>
            <b>Estimated network effect</b><br><br>
            Under {simulated_5g_throughput:.1f} Mbps uplink and {simulated_5g_latency:.0f} ms latency,
            estimated transmission changes from
            <b>{raw_network["estimated_total_seconds"]:.3f} s</b> to
            <b>{edge_network["estimated_total_seconds"]:.3f} s</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="interpretation-box">
            <b>Field-record mode</b><br><br>
            This observation contains scientific metadata without an attached AI media analysis.
            Geolocation, environmental variables, Sentinel context, Edge-node metadata,
            registry and PDF reporting remain available. Detection and network-reduction metrics
            are intentionally reported as not evaluated.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader(T("Interpretation Limits", "Límites de interpretación"))

    with st.expander("Scientific interpretation limits", expanded=not compact_view):
        st.markdown(
        """
        <div class="method-box">

        <b>Detection statistics</b><br><br>

        They describe how consistent MegaDetector confidence scores were among
        detections for this specific analyzed video. They do not establish model
        accuracy, precision, recall, calibration, generalization or absence of overfitting.

        <br><br>

        <b>Network statistics</b><br><br>

        The connectivity section accepts either reference assumptions or manually entered testbed measurements. Transfer-time values shown by the app are deterministic calculations from those inputs, not packet-level measurements by themselves.

        <br><br>


        <br><br>

        <b>Satellite context</b><br><br>

        The current Sentinel module discovers real catalogue acquisitions around
        the camera. It does not yet calculate NDVI, forest disturbance, flood extent,
        moisture or habitat-change indicators.

        </div>
        """,
            unsafe_allow_html=True,
        )

    st.subheader(T("Prototype Scope", "Alcance del prototipo"))

    st.markdown(
        """
        **Current implementation**

        PantheraCAM/field-event simulation or HTTP event ingest → optional local PantheraEDGE demo →
        filtered event evidence → 5G reference/measured-input model → Panthera LAB cloud persistence (Supabase backend) →
        PantheraMONITORING scientific review → PantheraID/downstream identity workflow → GeoJSON/JSON outputs →
        Copernicus/Sentinel environmental context.

        **Target hardware/network integration**

        PantheraCAM / Browning / FIREWATCH → Wi-Fi or LoRa → PantheraEDGE → MQTT/HTTP + offline queue →
        CPE / 5G radio & core → Panthera LAB ingest/API → persistence + PantheraID + PantheraMONITORING.

        **Potential remote-sensing extension**

        Sentinel-1/Sentinel-2 processing through Sentinel Hub or openEO for
        validated vegetation, flood or forest-change indicators.

        **Potential biological extension**

        Persistent observation and reference databases, validated species classification,
        locally calibrated jaguar re-identification, PantheraID-compatible downstream
        integration and multi-camera encounter history.
        """
    )

    st.caption(
        "PantheraMONITORING is a research prototype aligned to the Panthera Lab cloud architecture. MegaDetector performs object detection; "
        "Species and individual identity are handled downstream through PantheraID and researcher validation. "
        "Environmental/reporting fields must be aligned to the exact study, NGO or SINAC template before operational deployment."
    )
