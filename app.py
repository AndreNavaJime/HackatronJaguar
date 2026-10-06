# -*- coding: utf-8 -*-

"""
=========================================================
JAGUARID EDGE MONITORING NODE
EDGE WILDLIFE INTELLIGENCE · HACKATRON 5G
=========================================================

ARCHITECTURE

Camera Trap / SD / Wokwi-ESP32
    ↓
Edge Monitoring Node
    ↓
Video / Image Ingest
    ↓
MegaDetector V6
    ↓
Animal Event Filtering
    ↓
Candidate Animal Images
    ↓
Reduced Transmission Payload
    ↓
5G Communication Layer (estimated/simulated)
    ↓
Monitoring Database / JaguarID Registry
    ↓
Researcher Validation / downstream PantheraID-compatible workflow

PLUS:
Copernicus Data Space STAC
    ├─ Sentinel-1 GRD (SAR)
    └─ Sentinel-2 L2A (optical)
for environmental acquisition context around camera stations.

IMPORTANT SCIENTIFIC LIMITS

MegaDetector:
- Detects animal / person / vehicle
- DOES NOT identify species
- DOES NOT identify individual animals

Species and individual IDs are researcher annotations unless validated
downstream models are later integrated.

Detection-confidence statistics describe behavior within the analyzed
material. They DO NOT constitute external validation, accuracy estimates,
calibration evidence, generalization evidence or evidence against overfitting.

The 5G section is a deterministic transmission estimate based on payload size,
user-selected throughput and latency. It is NOT a live 5G network measurement.

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
import pandas as pd
import requests
import streamlit as st
import torch

from PytorchWildlife.models import detection as pw_detection

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
# STREAMLIT CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="JaguarID | Edge Wildlife Monitoring",
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
    .block-container {max-width: 1380px; padding-top: 2rem; padding-bottom: 5rem;}
    h1 {font-size: 2.25rem !important; font-weight: 650 !important; letter-spacing: -0.035em;}
    h2 {font-size: 1.45rem !important; font-weight: 620 !important; letter-spacing: -0.02em; margin-top: 2.3rem !important;}
    h3 {font-weight: 600 !important; letter-spacing: -0.01em;}
    p {line-height: 1.55;}
    div[data-testid="stMetric"] {
        border: 1px solid rgba(110,110,110,0.22);
        border-radius: 7px;
        padding: 0.95rem 1rem;
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
        margin: 0.9rem 0 1.7rem 0;
        padding: 0.95rem 1.05rem;
        border: 1px solid rgba(110,110,110,0.18);
        border-radius: 10px;
        background: rgba(120,120,120,0.018);
    }

    .brand-panel-label {
        font-size: 0.67rem;
        letter-spacing: 0.13em;
        text-transform: uppercase;
        opacity: 0.48;
        margin-bottom: 0.8rem;
    }

    .brand-row {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.65rem;
    }

    .brand-logo-card,
    .brand-vector-card {
        min-height: 68px;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0.55rem 0.85rem;
        border: 1px solid rgba(110,110,110,0.14);
        border-radius: 8px;
        background: rgba(255,255,255,0.72);
        box-sizing: border-box;
    }

    .brand-logo-card.cqu {
        min-width: 255px;
        flex: 1.45 1 255px;
    }

    .brand-logo-card.copernicus {
        min-width: 235px;
        flex: 1.25 1 235px;
    }

    .brand-vector-card {
        min-width: 155px;
        flex: 0.8 1 155px;
        gap: 0.65rem;
    }

    .brand-logo-card img {
        display: block;
        width: auto;
        max-width: 100%;
        object-fit: contain;
    }

    .brand-logo-card.cqu img {
        height: 48px;
    }

    .brand-logo-card.copernicus img {
        height: 46px;
    }

    .brand-logo-card.sentinel-logo {
        min-width: 185px;
        flex: 0.95 1 185px;
    }

    .brand-logo-card.sentinel-logo img {
        height: 46px;
        width: auto;
        max-width: 100%;
        object-fit: contain;
    }

    .brand-symbol {
        font-weight: 760;
        font-size: 1.18rem;
        letter-spacing: -0.025em;
        line-height: 1;
        white-space: nowrap;
    }

    .brand-symbol.sentinel {
        font-size: 0.96rem;
        letter-spacing: 0.01em;
    }

    .brand-meta {
        display: flex;
        flex-direction: column;
        line-height: 1.15;
        white-space: nowrap;
    }

    .brand-meta strong {
        font-size: 0.72rem;
        font-weight: 650;
        letter-spacing: 0.045em;
        text-transform: uppercase;
    }

    .brand-meta span {
        font-size: 0.66rem;
        opacity: 0.58;
        margin-top: 0.2rem;
    }

    .brand-disclaimer {
        margin-top: 0.72rem;
        font-size: 0.68rem;
        line-height: 1.45;
        opacity: 0.48;
    }

    @media (prefers-color-scheme: dark) {
        .brand-logo-card,
        .brand-vector-card {
            background: rgba(255,255,255,0.95);
            color: #111111;
        }
    }

    @media (max-width: 700px) {
        .brand-logo-card.cqu,
        .brand-logo-card.copernicus,
        .brand-vector-card {
            min-width: 100%;
            flex-basis: 100%;
        }

        .brand-logo-card.cqu img {
            height: 44px;
        }

        .brand-logo-card.copernicus img {
            height: 42px;
        }
    }

    </style>
    """,
    unsafe_allow_html=True,
)

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
    "camera_latitude": 9.7489,
    "camera_longitude": -83.7534,
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
        return "JaguarID_Observation"
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return text or "JaguarID_Observation"


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
        "User-Agent": "JaguarID-Hackatron5G/1.0",
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
    timestamp = datetime.now().astimezone()

    return {
        "event_id": "EDGE-" + uuid.uuid4().hex[:8].upper(),
        "timestamp": timestamp.isoformat(),
        "camera_id": camera_id.strip() or "CAMERA-UNASSIGNED",
        "event": "new_capture",
        "source": "JaguarID software simulator",
        "wifi_status": "CONNECTED",
        "wifi_rssi_dbm": -61,
        "sd_status": "READY",
        "latitude": float(latitude),
        "longitude": float(longitude),
        "status": "RECEIVED",
    }


def get_remote_edge_event(endpoint_url):
    endpoint_url = endpoint_url.strip()

    if not endpoint_url:
        raise ValueError("Remote Edge endpoint is empty.")

    response = requests.get(
        endpoint_url,
        timeout=10,
        headers={"User-Agent": "JaguarID-EdgeNode/1.0"},
    )
    response.raise_for_status()
    return response.json()


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
        Paragraph("JaguarID", title_style),
        Paragraph(
            "EDGE WILDLIFE INTELLIGENCE · SCIENTIFIC OBSERVATION REPORT",
            subtitle_style,
        ),
    ]

    story.append(Paragraph("Observation Summary", section_style))

    summary_rows = [
        ["Observation ID", escape_pdf_text(observation.get("observation_id", ""))],
        ["Observation name", escape_pdf_text(observation.get("observation_name", ""))],
        [
            "Analysis date",
            f'{observation.get("analysis_date", "")} {observation.get("analysis_time", "")}',
        ],
        ["Observer / Researcher", escape_pdf_text(observation.get("observer", ""))],
        ["Camera / Station", escape_pdf_text(observation.get("camera_id", ""))],
        ["Study site", escape_pdf_text(observation.get("study_site", ""))],
        ["Latitude", str(observation.get("camera_latitude", "Not specified"))],
        ["Longitude", str(observation.get("camera_longitude", "Not specified"))],
        ["Species annotation", escape_pdf_text(observation.get("species", ""))],
        ["Individual ID", escape_pdf_text(observation.get("individual_id", ""))],
        ["Source video", escape_pdf_text(observation.get("source_video", ""))],
        ["Edge event ID", escape_pdf_text(observation.get("edge_event_id", "Not available"))],
    ]

    story.append(_styled_table(summary_rows, [5 * cm, 11 * cm]))

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
        story.append(Paragraph("Estimated 5G Communication Layer", section_style))

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
    '<div class="jaguarid-kicker">Wildlife Monitoring Research Prototype</div>',
    unsafe_allow_html=True,
)

st.title("JaguarID Edge Monitoring Node")

st.markdown(
    """
    <div class="jaguarid-subtitle">
        Edge-assisted processing of camera-trap video for wildlife-event filtering,
        structured observations, reduced network transmission and satellite context.
    </div>
    <div class="technical-strip">
        Camera Trap · Video Ingest · Copernicus · Sentinel · ESP32/Wokwi · Edge AI · MegaDetector V6 · 5G · Registry
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
<div class="brand-panel-label">Research · Data · Connectivity Context</div>
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
<strong>Connectivity</strong>
<span>Edge transmission model</span>
</div>
</div>
<div class="brand-logo-card sentinel-logo">
<img src="https://download.esa.int/multimedia/mission_logos/EO/sentinel-2_logo/sentinel-2.jpg" alt="Sentinel-2" loading="eager">
</div>
</div>
<div class="brand-disclaimer">
Institutional, programme and technology references identify research,
data or technical context only and do not imply endorsement,
certification or sponsorship of this prototype.
</div>
</div>"""

st.markdown(
    brand_html,
    unsafe_allow_html=True,
)


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("Analysis Parameters")

confidence_threshold = st.sidebar.slider(
    "Detection confidence",
    min_value=0.10,
    max_value=0.90,
    value=0.25,
    step=0.05,
)

sample_seconds = st.sidebar.slider(
    "Sampling interval (seconds)",
    min_value=0.5,
    max_value=5.0,
    value=1.0,
    step=0.5,
)

max_samples = st.sidebar.slider(
    "Maximum sampled frames",
    min_value=3,
    max_value=30,
    value=10,
    step=1,
)

st.sidebar.info(
    "MegaDetector inference is executed in the Streamlit runtime. "
    "The 5G module is an estimate, and the Sentinel module queries "
    "Copernicus catalogue metadata."
)

st.sidebar.divider()
st.sidebar.caption("JaguarID · HACKATRON 5G Research Prototype")

# =========================================================
# 1. OBSERVATION METADATA
# =========================================================

st.header("1. Observation Metadata")

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
        "Observation name",
        placeholder="Example: Jaguar encounter CT-07",
    )
    camera_id = st.text_input(
        "Camera / Station ID",
        placeholder="Example: CT-07",
    )
    study_site = st.text_input(
        "Study site",
        placeholder="Example: Osa Peninsula / Sector A",
    )

with meta_col2:
    species_label = st.text_input(
        "Species identification",
        placeholder="Example: Panthera onca",
    )
    individual_id = st.text_input(
        "Individual ID",
        placeholder="Example: JAG-003 or Unknown",
    )
    observer_name = st.text_input(
        "Observer / Researcher",
        placeholder="Researcher name",
    )

observation_notes = st.text_area(
    "Field notes",
    placeholder=(
        "Behavior, habitat context, environmental conditions, sex, age class, "
        "direction of movement, camera conditions or other relevant observations."
    ),
)

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
# 2. CAMERA-TRAP VIDEO
# =========================================================

st.header("2. Camera-Trap Video")

uploaded_video = st.file_uploader(
    "Select video",
    type=["avi", "mp4", "mov", "mkv"],
)

video_ready = uploaded_video is not None

if not video_ready:
    st.info(
        "Upload a camera-trap video to begin the Edge AI analysis."
    )

if video_ready:
    current_file_signature = (
        uploaded_video.name,
        uploaded_video.size,
    )

    if st.session_state.current_uploaded_file != current_file_signature:
        st.session_state.current_uploaded_file = current_file_signature
        st.session_state.analysis_result = None

    st.success(f"Loaded: {uploaded_video.name}")

    try:
        st.video(uploaded_video.getvalue())
    except Exception:
        st.warning(
            "The browser could not preview this format. "
            "The file may still be processed by OpenCV."
        )

    run_analysis = st.button(
        "Run Edge Analysis",
        type="primary",
        use_container_width=True,
    )
else:
    run_analysis = False


# =========================================================
# ANALYSIS AVAILABILITY GUARD
# =========================================================

if not video_ready:
    st.stop()


# =========================================================
# 3. EDGE AI PROCESSING
# =========================================================

st.header("3. Edge AI Processing")

st.markdown(
    """
    <div class="section-intro">
        MegaDetector V6 analyzes sampled video frames close to the data source,
        applies the wildlife-event filter and retains candidate animal regions
        before wide-area transmission.
    </div>
    """,
    unsafe_allow_html=True,
)

if not run_analysis and st.session_state.analysis_result is None:
    st.info("Use “Run Edge Analysis” above to start processing this video.")
elif not run_analysis and st.session_state.analysis_result is not None:
    st.success("Existing Edge analysis loaded for the current video.")


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

    st.subheader("Video Characteristics")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Duration", f"{duration:.1f} s")
    c2.metric("Frame rate", f"{fps:.1f} FPS")
    c3.metric("Resolution", f"{width} × {height}")
    c4.metric("Total frames", f"{total_frames:,}")

    st.subheader("Edge Inference")

    with st.spinner("Initializing MegaDetector V6..."):
        model, device = load_model()

    st.success(f"MegaDetector V6 initialized · {device.upper()} inference")

    st.caption(
        "Model output classes: animal, person and vehicle. "
        "Species and individual identity are not inferred at this stage."
    )

    CLASS_NAMES = {
        0: "animal",
        1: "person",
        2: "vehicle",
    }

    frame_interval = max(1, int(fps * sample_seconds))

    records = []
    candidate_images = []
    annotated_images = []

    sample_number = 0
    frame_number = 0
    frames_kept = 0
    frames_discarded = 0
    total_animals = 0
    total_people = 0
    total_vehicles = 0
    total_input_bytes = 0
    total_candidate_bytes = 0

    st.subheader("Processing")

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
            "JAGUARID · EDGE INFERENCE",
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
    candidate_mb = total_candidate_bytes / 1024 / 1024

    payload_reduction = (
        ((total_input_bytes - total_candidate_bytes) / total_input_bytes * 100)
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
        "source_video": uploaded_video.name,
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
# REQUIRE ANALYSIS
# =========================================================

if st.session_state.analysis_result is None:
    st.info("Run the Edge analysis to continue.")
    st.stop()

# =========================================================
# RESTORE ANALYSIS
# =========================================================

result = st.session_state.analysis_result
observation = result["observation"].copy()
df = result["df"]
candidate_images = result["candidate_images"]
annotated_images = result["annotated_images"]
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

st.session_state.analysis_result["observation"] = observation.copy()

# =========================================================
# 5. EDGE RESULTS
# =========================================================

st.divider()
st.header("5. Edge Analysis Results")

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

m1.metric("Frames analyzed", total_samples)
m2.metric("Frames retained", frames_kept)
m3.metric("Frames discarded", f"{discard_percentage:.1f}%")
m4.metric("Payload reduction", f"{payload_reduction:.1f}%")

m5, m6, m7, m8 = st.columns(4)

m5.metric("Animal detections", total_animals)
m6.metric("Sampled input", f"{input_mb:.2f} MB")
m7.metric("Candidate output", f"{candidate_mb:.2f} MB")
m8.metric("Mean inference time", f"{average_inference:.2f} s")

st.caption(
    "Estimated payload reduction is calculated from sampled JPEG frames and "
    "retained animal crops. It is not a direct measurement of 5G throughput "
    "or source-video compression."
)

# =========================================================
# DETECTION CONFIDENCE STATISTICS
# =========================================================

st.subheader("Detection Confidence Statistics")

st.markdown(
    """
    <div class="section-intro">
        Statistical summary of MegaDetector confidence values for retained
        animal detections. These metrics describe consistency within this
        video and should not be interpreted as validation accuracy.
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

    r1.metric("Peak confidence", f"{confidence_stats['maximum']:.1%}")
    r2.metric("Mean confidence", f"{confidence_stats['mean']:.1%}")
    r3.metric("Median confidence", f"{confidence_stats['median']:.1%}")
    r4.metric("Minimum confidence", f"{confidence_stats['minimum']:.1%}")

    r5, r6, r7, r8 = st.columns(4)

    r5.metric("Standard deviation", f"{confidence_stats['std']:.1%}")
    r6.metric("Confidence range", f"{confidence_stats['range']:.1%}")
    r7.metric("Animal detections", confidence_stats["count"])
    r8.metric(
        "Positive sampled frames",
        f"{confidence_stats['positive_frame_rate']:.1f}%",
    )

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
# 5. CAMERA GEOLOCATION & SPATIAL CONTEXT
# =========================================================

st.header("5. Camera Geolocation & Spatial Context")

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
        "Latitude",
        min_value=-90.0,
        max_value=90.0,
        step=0.0001,
        format="%.6f",
        key="camera_latitude",
        help="WGS84 latitude of the camera / monitoring station.",
    )

with geo_col2:
    st.number_input(
        "Longitude",
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

st.markdown(
    """
    <div class="scientific-note">
        <b>Spatial interpretation.</b>
        The point represents the camera station associated with the observation.
        It is used to attach spatial metadata to the record and to define the
        search area for Copernicus / Sentinel context.
    </div>
    """,
    unsafe_allow_html=True,
)

observation["camera_latitude"] = camera_latitude
observation["camera_longitude"] = camera_longitude
st.session_state.analysis_result["observation"] = observation.copy()


# =========================================================
# 6. COPERNICUS / SENTINEL CONTEXT
# =========================================================

st.header("6. Copernicus / Sentinel Environmental Context")

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
        "Search radius (km)",
        min_value=1,
        max_value=50,
        value=5,
        step=1,
    )

with sat_col2:
    satellite_days_back = st.slider(
        "Search period (days)",
        min_value=5,
        max_value=90,
        value=30,
        step=5,
    )

with sat_col3:
    sentinel2_cloud_limit = st.slider(
        "Sentinel-2 maximum cloud cover",
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

if st.button("Query Copernicus Data Space", use_container_width=True):
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

        st.markdown(
            """
            <div class="scientific-note">
                <b>Interpretation boundary.</b>
                Satellite availability provides environmental acquisition context.
                It does not establish that a wildlife detection was caused by a
                forest, vegetation, flood or habitat-change event. Derived ecological
                indicators require a separate remote-sensing workflow and validation.
            </div>
            """,
            unsafe_allow_html=True,
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

st.session_state.analysis_result["observation"] = observation.copy()


# =========================================================
# 7. EDGE MONITORING NODE
# =========================================================

st.header("7. Edge Monitoring Node")

st.markdown(
    """
    <div class="section-intro">
        Software representation of the field node. It can run in simulator mode
        today and is prepared to poll a remote JSON endpoint when the ESP32/Wokwi
        or physical prototype is connected through a small backend.
    </div>
    """,
    unsafe_allow_html=True,
)

edge_mode = st.radio(
    "Edge event source",
    ["Software simulator", "Remote ESP32 / Wokwi endpoint"],
    horizontal=True,
)

if edge_mode == "Software simulator":
    edge_c1, edge_c2 = st.columns([1, 2])

    with edge_c1:
        simulate_event = st.button(
            "Simulate New Camera Event",
            use_container_width=True,
        )

    if simulate_event:
        simulated_event = create_simulated_edge_event(
            camera_id,
            camera_latitude,
            camera_longitude,
        )
        st.session_state.latest_edge_event = simulated_event
        st.session_state.edge_node_events.append(simulated_event)

    with edge_c2:
        st.caption(
            "This represents the message that would normally arrive when the field "
            "controller detects a new capture on the camera/SD."
        )

else:
    remote_edge_endpoint = st.text_input(
        "Remote Edge JSON endpoint",
        placeholder="https://your-backend.example/api/latest-event",
        help=(
            "Recommended architecture: ESP32/Wokwi POSTs to a tiny API or broker; "
            "JaguarID polls a JSON endpoint exposed by that service."
        ),
    )

    if st.button("Poll Edge Node", use_container_width=True):
        try:
            remote_event = get_remote_edge_event(remote_edge_endpoint)
            st.session_state.latest_edge_event = remote_event
            st.session_state.edge_node_events.append(remote_event)
            st.success("Edge event received.")
        except Exception as error:
            st.error(f"The Edge endpoint could not be read: {error}")

latest_edge_event = st.session_state.latest_edge_event

if latest_edge_event:
    e1, e2, e3, e4 = st.columns(4)

    e1.metric(
        "Node status",
        latest_edge_event.get("status", "RECEIVED"),
    )

    e2.metric(
        "Wi-Fi",
        latest_edge_event.get("wifi_status", "Unknown"),
    )

    wifi_rssi = latest_edge_event.get("wifi_rssi_dbm")

    e3.metric(
        "Wi-Fi RSSI",
        f"{wifi_rssi} dBm" if wifi_rssi is not None else "N/A",
    )

    e4.metric(
        "SD status",
        latest_edge_event.get("sd_status", "Unknown"),
    )

    with st.expander("Latest Edge event JSON", expanded=False):
        st.json(latest_edge_event)

else:
    st.info(
        "No Edge event has been received yet. The video can still be analyzed manually."
    )

st.markdown(
    """
    <div class="scientific-note">
        <b>Prototype boundary.</b>
        Streamlit is not being used as a permanent inbound IoT server. For a physical
        ESP32 deployment, use a small API/message broker between the field node and
        this dashboard.
    </div>
    """,
    unsafe_allow_html=True,
)




# Synchronize the latest field-node event with the scientific observation.
if st.session_state.latest_edge_event:
    observation["edge_event_id"] = st.session_state.latest_edge_event.get(
        "event_id",
        observation.get("edge_event_id", "Not available"),
    )

st.session_state.analysis_result["observation"] = observation.copy()


# =========================================================
# 8. 5G COMMUNICATION LAYER
# =========================================================

st.header("8. 5G Communication Layer")

st.markdown(
    """
    <div class="section-intro">
        Estimated transmission performance before and after Edge filtering.
        Throughput and latency are configurable assumptions, not live 5G measurements.
    </div>
    """,
    unsafe_allow_html=True,
)

network_col1, network_col2 = st.columns(2)

with network_col1:
    simulated_5g_throughput = st.number_input(
        "Assumed uplink throughput (Mbps)",
        min_value=0.1,
        max_value=1000.0,
        value=20.0,
        step=1.0,
    )

with network_col2:
    simulated_5g_latency = st.number_input(
        "Assumed network latency (ms)",
        min_value=0.0,
        max_value=1000.0,
        value=25.0,
        step=5.0,
    )

raw_network = estimate_network_transmission(
    input_mb,
    simulated_5g_throughput,
    simulated_5g_latency,
)

edge_network = estimate_network_transmission(
    candidate_mb,
    simulated_5g_throughput,
    simulated_5g_latency,
)

transmission_time_saved = max(
    raw_network["estimated_total_seconds"]
    - edge_network["estimated_total_seconds"],
    0.0,
)

avoided_mb = max(
    input_mb - candidate_mb,
    0.0,
)

n1, n2, n3, n4 = st.columns(4)

n1.metric("Before Edge", f"{input_mb:.3f} MB")
n2.metric("After Edge", f"{candidate_mb:.3f} MB")
n3.metric("Avoided transmission", f"{avoided_mb:.3f} MB")
n4.metric("Payload reduction", f"{payload_reduction:.1f}%")

n5, n6, n7, n8 = st.columns(4)

n5.metric("Assumed uplink", f"{simulated_5g_throughput:.1f} Mbps")
n6.metric("Assumed latency", f"{simulated_5g_latency:.0f} ms")
n7.metric(
    "Raw transmission",
    f"{raw_network['estimated_total_seconds']:.3f} s",
)
n8.metric(
    "Edge transmission",
    f"{edge_network['estimated_total_seconds']:.3f} s",
)

st.metric(
    "Estimated transmission time avoided",
    f"{transmission_time_saved:.3f} s",
)

st.markdown(
    """
    <div class="scientific-note">
        <b>Network interpretation boundary.</b>
        These values are deterministic estimates derived from payload size,
        user-defined uplink throughput and user-defined latency. They are not
        measured 5G KPIs.
    </div>
    """,
    unsafe_allow_html=True,
)

observation["network_throughput_mbps"] = simulated_5g_throughput
observation["network_latency_ms"] = simulated_5g_latency
observation["raw_transmission_seconds"] = raw_network["estimated_total_seconds"]
observation["edge_transmission_seconds"] = edge_network["estimated_total_seconds"]
observation["transmission_time_saved_seconds"] = transmission_time_saved
observation["transmission_avoided_mb"] = avoided_mb
observation["input_mb"] = input_mb
observation["candidate_mb"] = candidate_mb

st.session_state.analysis_result["observation"] = observation.copy()

# =========================================================
# 9. EDGE-TO-SCIENCE WORKFLOW
# =========================================================

st.header("9. Edge-to-Science Workflow")

workflow = [
    ("01", "Camera Trap / SD", "Field camera records a wildlife event and stores the capture locally."),
    ("02", "ESP32 / Field Controller", "Field controller detects a new capture and publishes an event over the local communication link."),
    ("03", "Edge Monitoring Node", "Video or images are processed close to the field source before wide-area transmission."),
    ("04", "MegaDetector V6", "Frames are screened for animal, person and vehicle objects."),
    ("05", "Wildlife Event Filter", "Non-animal samples are excluded and relevant candidate regions are retained."),
    ("06", "5G Communication Layer", "Reduced wildlife-event packages are prioritized for transmission."),
    ("07", "Monitoring Database", "Observation metadata, candidate imagery and Edge metrics are stored as structured records."),
    ("08", "Researcher Validation", "Species and individual identity are validated or supplied by researchers or downstream validated systems."),
    ("09", "Copernicus / Sentinel", "Satellite acquisitions provide independent environmental context around camera stations."),
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

st.markdown(
    workflow_html,
    unsafe_allow_html=True,
)

# =========================================================
# 10. EDGE FILTERING CHART
# =========================================================

st.header("10. Edge Filtering Outcome")

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

# =========================================================
# 11. TEMPORAL CONFIDENCE PROFILE
# =========================================================

st.header("11. Temporal Detection Confidence")

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

# =========================================================
# 12. CONFIDENCE DISTRIBUTION
# =========================================================

st.header("12. Detection Confidence Distribution")

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

# =========================================================
# 13. DATA REDUCTION
# =========================================================

st.header("13. Estimated Candidate Data Reduction")

payload_labels = ["Sampled input", "Candidate output"]
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

# =========================================================
# 14. CANDIDATE ANIMAL IMAGES
# =========================================================

st.header("14. Candidate Animal Images")

st.markdown(
    """
    <div class="section-intro">
        Animal crops retained by MegaDetector for researcher review.
        These images are not automatically confirmed as jaguars.
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
            label="Download all candidate images · ZIP",
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
# 15. FRAME-LEVEL EDGE DECISIONS
# =========================================================

st.header("15. Frame-Level Edge Decisions")

for index, item in enumerate(
    annotated_images,
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
# 16. SCIENTIFIC OBSERVATION
# =========================================================

st.header("16. Scientific Observation")

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
    "Individual ID",
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

        **Source video**  
        {observation["source_video"]}

        **Edge event ID**  
        {observation["edge_event_id"]}

        **Analysis date**  
        {observation["analysis_date"]} {observation["analysis_time"]}
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
# SAVE OBSERVATION
# =========================================================

save_observation = st.button(
    "Save Observation",
    type="primary",
    use_container_width=True,
)

if save_observation:
    existing_ids = [
        item["observation_id"]
        for item in st.session_state.observation_registry
    ]

    if observation["observation_id"] not in existing_ids:
        st.session_state.observation_registry.append(
            observation.copy()
        )

        st.success(
            f'Observation {observation["observation_id"]} was added '
            "to the current JaguarID registry."
        )
    else:
        st.info(
            "This observation is already present in the current session registry."
        )

# =========================================================
# 17. OBSERVATION REGISTRY
# =========================================================

st.header("17. Observation Registry")

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
        "species",
        "individual_id",
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


    st.subheader("Registry Management")

    removable_ids = registry_df["observation_id"].tolist()

    selected_remove_id = st.selectbox(
        "Observation to remove",
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
        "I confirm that I want to remove this observation",
        key="registry_remove_confirm",
    )

    if st.button(
        "Remove Observation",
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
        st.subheader("Individual Encounter History")

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
# 18. FRAME-LEVEL DATA
# =========================================================

st.header("18. Frame-Level Analysis Data")

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
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
    + "_JaguarID_Data.csv"
)

st.download_button(
    label="Download frame-level data · CSV",
    data=csv_data,
    file_name=csv_filename,
    mime="text/csv",
    use_container_width=True,
)

# =========================================================
# 19. SCIENTIFIC REPORT
# =========================================================

st.header("19. Scientific Observation Report")

st.markdown(
    """
    <div class="section-intro">
        Export observation metadata, Edge AI measurements, confidence statistics,
        estimated 5G transmission metrics, Sentinel catalogue context, researcher
        annotations and representative candidate images.
    </div>
    """,
    unsafe_allow_html=True,
)

report_name = st.text_input(
    "Report file name",
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
        + "_JaguarID_Report.pdf"
    )

    st.download_button(
        label="Download Scientific Observation Report · PDF",
        data=pdf_data,
        file_name=pdf_filename,
        mime="application/pdf",
        use_container_width=True,
        type="primary",
    )

    st.caption(
        "The report includes observation metadata, camera coordinates, Edge AI "
        "metrics, confidence statistics, estimated network metrics, latest "
        "Sentinel-1 / Sentinel-2 acquisition context, researcher annotations "
        "and up to six candidate animal images. The full Sentinel catalogue "
        "remains available separately as CSV or JSON."
    )

except Exception as pdf_error:
    st.error(
        "The video analysis was completed successfully, but the PDF report could not be generated."
    )
    st.code(str(pdf_error))

# =========================================================
# 20. ANALYSIS SUMMARY
# =========================================================

st.divider()
st.header("20. Analysis Summary")

st.markdown(
    f"""
    <div class="interpretation-box">

    <b>Edge filtering</b><br><br>

    {total_samples} sampled frames were analyzed.
    {frames_kept} contained one or more detected animal events and
    {frames_discarded} were discarded at the Edge.

    The candidate-image payload was approximately
    <b>{payload_reduction:.1f}% smaller</b> than the sampled-frame
    image payload used in this prototype calculation.

    <br><br>

    <b>Detection confidence</b><br><br>

    MegaDetector produced {confidence_stats["count"]} retained animal
    detections. Mean confidence was
    <b>{confidence_stats["mean"]:.1%}</b>,
    median confidence was
    <b>{confidence_stats["median"]:.1%}</b>,
    and peak confidence was
    <b>{confidence_stats["maximum"]:.1%}</b>.

    Confidence standard deviation was
    <b>{confidence_stats["std"]:.1%}</b>.

    <br><br>

    <b>Estimated network effect</b><br><br>

    Under an assumed uplink of
    <b>{simulated_5g_throughput:.1f} Mbps</b>
    and latency of
    <b>{simulated_5g_latency:.0f} ms</b>,
    the sampled payload would require approximately
    <b>{raw_network["estimated_total_seconds"]:.3f} s</b>,
    whereas the retained candidate payload would require approximately
    <b>{edge_network["estimated_total_seconds"]:.3f} s</b>.

    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Interpretation Limits")

st.markdown(
    """
    <div class="method-box">

    <b>Detection statistics</b><br><br>

    They describe how consistent MegaDetector confidence scores were among
    detections for this specific analyzed video. They do not establish model
    accuracy, precision, recall, calibration, generalization or absence of overfitting.

    <br><br>

    <b>Network statistics</b><br><br>

    The 5G section is a deterministic estimate using user-selected throughput
    and latency. It is not a live telecommunications benchmark.

    <br><br>

    <b>Satellite context</b><br><br>

    The current Sentinel module discovers real catalogue acquisitions around
    the camera. It does not yet calculate NDVI, forest disturbance, flood extent,
    moisture or habitat-change indicators.

    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Prototype Scope")

st.markdown(
    """
    **Current implementation**

    Camera-trap video → Edge event → sampled MegaDetector inference →
    animal-event filtering → candidate extraction → reduced-payload estimate →
    configurable 5G communication estimate → structured scientific observation →
    Sentinel acquisition context → researcher validation → temporary registry.

    **Near-term hardware integration**

    Wokwi/ESP32 or physical ESP32 → small HTTP/MQTT backend →
    JaguarID Edge Monitoring Node.

    **Potential remote-sensing extension**

    Sentinel-1/Sentinel-2 processing through Sentinel Hub or openEO for
    validated vegetation, flood or forest-change indicators.

    **Potential biological extension**

    Persistent observation database, validated species classification,
    individual jaguar re-identification, PantheraID-compatible downstream
    integration and multi-camera encounter history.
    """
)

st.caption(
    "JaguarID is a research prototype. MegaDetector performs object detection; "
    "species and individual identity currently require researcher validation."
)
