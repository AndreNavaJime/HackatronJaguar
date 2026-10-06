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
<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA9AAAAJQCAIAAADpCxvTAAEAAElEQVR42uz9a7BsW3bXB47HnHOtzNzP87iPurfeulUlqUqUKIEQBoMEEXbb0YTbbYK2P9AERJfcEGFDG0z7ER1hh93Bl3aAHYGlAoRsGizaAjXYCoSALlNGBkl1papSSSrV49bzPs9rvzJzrTXnGKM/zMw8uZ9nn9etc2+Nn6SrffbJXLlyrcx1/nOs//gPNDNwHMdxHMdxnMvxyz/2f/v/3nq22Xu1+d//538e/uJ/Av/pf/kvwz/7f/wX8J//h/AX/u//v+/6A1c/+ROv/JG/81/Cf1H/6vBTf+nP/uNn/o3vO3rp6r/xp3746iVfJf/yh9f/GH/H5y+/h/+XH/3TL774mY997KN/5cf/4gO8wU+/+JmP/+ifBoBP/Phf/IGPffTTL37mxz/xky+++Jkf/fgf+9GP/7EH2CC64HYcx3Ecx3GeNKrgpnf8SX3lLwNA+NBfx83fcXnBDQAPprYrP/6JnwSAj33soz/wsY/++Cd+8sc/8ZP3K99/+w/8/tVTXHA7juM4juM4TxZ2+MsAsFLY8vJf5uf+5Ju8D1Vz/+jH/9inX/xMLW8/2NNdcDuO4ziO4zjO44X8EDiO4ziO4ziOC27HcRzHcRzHccHtOI7jOI7jOI4LbsdxHMdxHMdxwe04juM4juM4Lrgdx3Ecx3Ecx3HB7TiO4ziO4zguuB3HcRzHcRzHBbfjOI7jOI7jOC64HcdxHMdxHMcFt+M4juM4juO44HYcx3Ecx3Ec5yEIj2m78y7nUsz8CDuOc5IUw6iNfhlxHOdxX0Yc5wnhsVS4hyxD9n8mHcc5m1zKkMUvI47jPNbLiOO8zQV3P2Q/so7jnIfZva8SfhlxHOchLyOO8zYX3KpelXIc56GuEn4ZcRzHrxKOC27HcRzHcRzHcVxwO47jOI7jOI4LbsdxHMdxHMdxwf1oePnlVz73uc+XUuofh2G4dev2rVu379y5U39ZSplOpwAwm81+8Rc/fevWbQDo++FXf/Wzb7xxAwBU9dd+7ddffvmVEz87jvMdxa1bt3/xFz89m81WPx8cHNS/MrP9/YN6bTk6OlpdZ4Zh6Pvh05/+lW9962VbBqBMp9NSipl9+csvffnLL9Xf37p1+1d/9bN9P/hxdhzHcd5igvtrX/v6Jz/5KUT823/774gIABwcHH7+87/xS7/06U984q/3fS8if+Wv/OR/+9/+1WEY/sf/8Weeeebpn/u5n9/b2//pn/67zPzJT37qS1/6yj/8h//4jTfe+Gf/7J//+q//5vrPfi4d58nhM5/53A//8P/u8W3/4ODg7//9n33uuWf/zt/5ezdv3vzc5z7/3HPP/sRP/I2quVX1q1/92uc//xt/62/9f37lVz7zL/7FL/2jf/RPPv/539jb2/+lX/rl69evf+pTv/DZz/4aAHzpS1/5c3/uP3nppa/+yq985tOf/pWXXvrqpz71C3t7e3/rb/3tEMLf+Bv/Q71SOY7z9ruMOM6bSXgzX+yVV1573/ve+5GPfO+LL/7qwcHB7u7utWtXf9/v+z2f+tQ/+9f+tX9lMpn8b//bL167drVpUv0nM6U4Go37vu+6/oUX3t+2zW/+5hdu3rz1h//wv/nqq69+/vO/ube3V3/+whe++L3f+91+Oh3nEaKqv/EbX1j98Xu+50NEl1qif+Yzn/vMZz5XfwCAj370+x7H7g1DHo/HbdtsbW398A//y4eHhylFZgYAZv7oR7/v4ODg5Zdf+d2/+3f97M/+3MbG5vvf/97r16899dR1VY0xxhjn8/n/8r986od+6AcB4Atf+OKP/MjvSyn9vb/3P29sTD784e/9yEe+95d/+cW9vf2rV6/4h8FxHv4aUkq5/NXgzbmMOM7bU3C/8ML7/8pf+esvvvirr7762irNZz6ff/3r3/zBH/ydN27c/OpXv/YH/+AP/+zP/hwRXb165Sd/8v999eqVq1evXL9+7S/9pb9cinzgA99lZiEwAJjp6mfHcR45RPTn//x/uvrjz/7s373kE//Mn/nzqx8++tHve7T/Un7mM5/r++GDH/xA2zY/9mN/9UMf+mCM8bXXXv+pn/rp69evNk2zeuRv/uYXX3jh/SGEj3zkw8z8T//p//qOd7zjX/qXftfP/Mz/9I1vfPP3//7f+0/+yT/9vb/3d3/xi18GgL7vU0r1iX0/rG/HcZxHcg358Ie/5/JXg8d6GXGct7ngvn792n/8H/+5vh/+5t/8qbZd/Hv2xhs327ZtmrS3t//aa6//tb/2333ta19/z3vejYj/0X/0Z3/+5//J5z//G3/oD/3rf+gP/eu//MsvTqfzg4PD6XSmajs723fu7NefJ5Oxn0vHeeRcXmSv88lP/oPPfOZzf+bP/PlPfvIfPPJdeu9732OmX/jCFz74wRf+6B/9d37qp3765Zdfef755/70n/5TP/Mz/9NLL331Ax94oT7yy1/+yo/8yO8DgPe97z0AMJ//9t/6rS+mlP7IH/k/fuELX/zUp36hlPKzP/sPv/GNb7766utXr+7eunVrd3d3PB5dubL7W7/1RTOLMYYQ/GPgOI/kGqKqT8hlxHHe5oL7xo2b/+Af/Pze3v5v/+0fnU6nf+Ev/L/+3J/70/P5PKUIAC+88P7/4D/4927duv33/t7//IM/+AM/9mN/7e/+3b//xS9+6U/8if/zz//8P7l589arr7727/67f2J7e/Nv/I3/IaX4b/1b/4crV66sfvZz6ThPFI+pIrW9vVVl90/8xH//yiuvvfba69Pp9L/6r/6bd7zj2W9+85u/5/f80H/2n/0///gf/6PPP//cbDZLKc3n87/5N//21tbm5z736//2v/2Hf+zH/uqVK7tf/OKX//Af/jc/+MEXAODv//2f/dCHPtA07U//9M+0bfMH/+CPvOc97/7H//iTP/ET//21a9e2tjb9VDrOI+GSnrQ34TLiOG8+uGrVf4TsH87v+ZhSys/93D/6A3/g949GIz8NjvMdyPbm6CEvI6cxs09+8lMf/vD3PPXUdT/CjvMdfhlxHBfccHh4CACbm149chz/l/KRCe75fN513e7urh9ex/HLiOM8OXzb7IkutR3HeeSMRiO/aeY4juM8afikScdxHMdxHMdxwe04juM4juM4LrjvbpTQj6zjOA9zlfDLiOM4fpVwXHBfRJMi+rfAcZwLrxJ+GXEc57FeRhznbS64U+To0yIcxzkLREgxpMh+GXEc57FeRhznCfrQPo5YwMqQpR/yaoS74zgOETYpXv6fSb+MOI7zkJcRx3mbC27HcRzHcRzHcTylxHEcx3Ecx3FccDuO4ziO4ziOC27HcRzHcRzHcVxwO47jOI7jOI4LbsdxHMdxHMdxwe04juM4juM4jgtux3Ecx3Ecx3HB7TiO4ziO4zguuB3HcRzHcRzHuS/C49v0rTt7dw4O+2Hwo/wkkGJAxCGXM2eLMnNgfubaLpjFwKYqpQy399L2FqVIIRARAKjqbDZvmiaEgPgod8/MTFVFAMBUy3RWpnNIgTdGMTaIiEREhEQvv3FzOuvqs4ZcvvK1l7/5ymvdkD/4/nfdvLX/vnc9+9yzT6naL3z6c4i4u7353uefnff9Z3/jy9/zwnufffrqbN792he+8srrN5sYdne2UowvvOedOzubX/vmqzdu779x89ZHPvT+qztbv/rrX3rH09e/9errr75xCwA++j0v9Dl//Vuvdn1+13PPfOC9z7/y+s0vf/1b/ZB/24e+63d9//fsbG0cezuqUoqqIiIiEvPrt/dykeu720U0xdCkuPia7B3sH00D8bXdrfGoXW1BVAcZIgcDIECmBxliXLSo6Zl/papFZbW/CHjPM1QOjgCRJyOZzqXredRSk4DJRLQfkCiORiGl+vD+zj4ipp2tk5804jv709t7B/6VdBznwWhS2t3avLq744fCeQvxuEa7f/PV1w+Ojvz4Pjl85Wsvi+l7n382xQALsbw4+ZHDl7/+rS9+7Vug+oH3v+v7Xnjv5ri1eUfMYdxyCMQMiCIyDFlERqOWmR/HTh6T3aJlOivzOacmbk4wMC7UKyERANx64+Zo1I42JrkIAMbAr9+6M+/7UoSICJGJ1KyIMBEAAIKImEFgVjUkJEADKyJmxswhBDAzMwMDgxBYVVUNAOorFxEEAERVrdtExOtXdiaj5thbEFFVM8vTOZQSJiOKEYmOZt2dgyNRferq7uZkBACv3bx9cDR7+touGBxMZ7tbGxvj0WItIYOZRY6ED34bSlTFBODs73iWoiYIeG+1vXpruZQ7B4AYd7cwhuXqwgAACbUeRmIwM1VArGfqrso3C8RHR92tvQNR9W+l4zgPzNbGxjuffdqPg/MdLbhv3dl77eYtP7hPFF/+6rfU7L3vfDal9PVvvfr6zdubG+MPvu9dIYSXvv7yqzdu1Z8PD6e3bu9vb00ODo6K6Y/8ru//2suvHxzNjmbzWh1//pnr3/eh90/G7ePb1Ytl90r+ai4UAgWGtWL7/uG0H/L25mTeDQfTqagWkaoIHwfPXr+yORnf3e+q0M10yMPBIUBVnBbGY24SEgIiMb9xa280ambzftymrY1JffYbt+60TbO1MX6Eu6emomLnCO5a5FZTwstq7nucODAmrsV46XoT4aapp2wdRr5z4EVux3EelmeuXfU6t/NW4bF4uO8cHPqRfWIJTG2T3vP8s9969cbN2/tm+tqN2+985qmtzcn25uQ973y2qLx+6854Mjo8mr1+a68fCiJ+z3e957vf/+6u63e3N1OKf/bP/od//I//ia985aXLKj/V2Wx+eHg0DPmea7zqweAYiRmZ4tZGe+0qMnY3bg139nXIVdeWUrqDg5Lz+nO3NydPXd1pUtzZmrzr2afe+9wzL7zrucm4rRr9xKs8jMaMgZ97+tpKbZuZiIiIigwHh/3ePjWp2d1urmyHUZsPDvs7e1L3vBQmvHFrb9TEjVErOWspZvawO3SfiGpRMbNHpbYBoBbji4qaUYpmIEM+vQYwMEJ4M9+s4zhvS1xsOG8l9fU4Nuq+7ScWZj6azb/y9ZdTiosSstl41BxMZ8/AtUDc9VlE3/ns9Z2tzddu3M5FcimqFgL/8q994YPvfec7n7nORKr63ve+bzy+VDk259INvZGGGFT18PBoNGpjjKcfWbQwchWeiIjMSGSqaqYAYXsDxPo7B0gYRi2PWiI0Ecm5OrzPE3HPPXXNAF67cVtVr+5uNTG9euPWrOsNAB7oDs8z169sTsYrX05dAICZdP1wcIREaWebU0REA6he5zKdD3sH3KYwHu1sjHc2xgCgImaGACYiuWiKj3g9jSRYXwIBIEsWVUJaSntDhEeltg2sukQIUUwwF8gFY9BcEFFLQSJKkQBVZXtzomq39/0fS8dxXGw43xE8FkvJr3/pK35knzS+/NVvvX7zjqgS4rzvd3e2Xnvj1u/4bd99/epO3+d/8aufNzUz2xiP+ly+6z3PXb+y+6lf+iyi7Wxt7mxuvHHzdts2THTtyvaHP/DeyCSiITAippRiDKfLsznnYcilFEQMTVCQURxVv8FsNl8oQqKUIhENkkULVpltyBxW9l8tJc87UKWUkAkAtB/KvJOuN4C0tcGjdqXRa2Plmcq7ftBx9bPZqzduT+cdAIyadG13u0nx1Ru3j5b7dh7jUXttd6tNCQCq9cXMtJRyODVRbBM1TQiBAhORAZiqVZ9JLuVoZlJ4MuK2tZzLdC5dHzcnYTJGopv7hwfTOQCkFK7vbo/bR+DbyZrVtKpqNStSLtUi+cAXFKSquYlIc5Gu11y4SUBooloKiHGKIHrQDQe5+BfTcb4z0VqnuEzhoNZTzuF7X3i/H0zHBbfzBDGb9yIKAEwECKpmZuNxy4SIaAYHh9OdrY0Yw97BUWBqmjQMueuHzcm4SUHEAGAYcoj87PUro7ZZKexhGLquR8QYY9MkRBTRvu8RsWlSvVAOkvvSj+JITQMxIdUEj67rmRnJ8nw+f+MWxsCjxrKGccvjtokNIU1fu2Gmo6u7FONKvFaxK11fph2YctOESYshwNLhveqtvIC6maVSxPqbV2/cOq25UwyBecjl+pXtjfEY8W5zJJiVWVdmc24SjRpDNDNkjjEx0/KF1qrgfZ8Pp5ozhcijFhE0Fx613KSFYiU+nM/v7B/FwNWAfu3K9qqZ8oEFt6ioGZg91o9Z9cYE5movMVUwA1rV1IFxYfI2s1t7B17kdpzvQI4OD2fz+eUfPx6NNjY3XXA7b2mCH4LvEMZrSRpniCSAKzub73j62s3be6M21fJDCLzTbrzj+tWaYdd1PXMIkel4/TillFICgK7rjo6mABBCaNtGTFaV5voSRUuRYhwAkBADhtGoPTqaqWYzCdd3qk7VUvr9w2jGE4oxhUmLxBRCNZkA80J2A+B4FEatFpF51928g4HDaMSjBomgRvJdaDWpZfETv+HARKhqzPz01Z3JqD3+ADQzlYXul2HICw/JJsWIiIbY9z2Ixmjrz6r2GBXhpuGUlqZtBIByOM37h5JCmIwpRpUyadLGM9fuHBxOQiOqN27vier2sr3yPiUwgAEgqJktS92PcQW/eFOLVzmVUqIAQEa4xL+YjvMdqLZ3tjZ/x0e/j+hSXWSq+qWXvrp3cHie5nactwRe4XYAAN757FNt9Ryf+jysVNFsNm+adMlAwEFykaxmo9ga2FAGA2MMtTaMiKvAu1JkurdHbYRAo9QGCllLn3vtejBoUhNTg0h4us/OTNcK3mAm/VBmnebMKdYwPlgpu0sUvJdbhRNl72N/u/SQmEiZzmTIK4mPRMQLA/p0OosxprM82atSdz3ai2p9kdL1Mp0hUZiMqG2QSExrwIgh3NmfTkajqrkPp7M7B0dDztd3d7Y376HCs2Q1RcQsWc3oMQvu9aCS81Z3TBwo1KN8686+F7kd5zsHVb158+bv+6EfvKTaXj3rn/7zX7x27drpZ3mF23mr4BVuBwDgW6/dSDE8e/1qig/7kZjnOSGJCgIC6Dx3TFyXdgaqBogABlly1dw29KPReDr0VlSH+ahtYoyxmcyJy3Q2fe2G5bL1/Dvi5FSDJiLVgrdZrXlz23CTTFT6ftg/BAMetWHcIjMsZ9DcU3mfLnuvlOJdW8i8y4dTijHtbNXSOzGvb3Y8HnVdlzOc7g1FIl575GKziDFwnIykH2Q6z0czbhOOWmC8m6diAABv3Nqbdd213e3JqL15Z/+lb75ydXtrY9wiwMVvjZHNxB6pgXtVpzcztdqOSRfXrRFRTcWEkREghhCYi4h/Bx3nO0RwA8B9qe3V41X1fp/oOC64nScLM+uH/PVXXg/M73jqanNWabZavS8mS0FAM6vVawJSM1FhJARUuBtCV1QChfmdO7M3bm0+/+zOznbWrGa5z/N5ZwYhcBpNJu/e0ZIphIs13LrVRBFDGIfxSHMps667cZtiCOMRNWllNbmgt/Ls47Nqjsw5H07BLG1vUor1pU+7Vmov6TBkRAyX2HkkqlXzumbQImXeldv7lGLYGBuQqe0dHs26HsCuX1kYXa7tbl/Z3jw6mt65sz8etU2T6JSLY/1frESU5dzZk/cLIQUO9EC2kDpdCBG3Nie5FC9yO47jOC64ne8g2Z1L+carb7zz2evtckb3itpGWa0T5+tHqwPDEYFqxXWpx3hNmYmpmoLBcDjdfO7pNBkDYlFRVQvGgdo4YuRh6HMpMcb6itWLcpF4rS+4LHhTiikG2JpIP5TZ3A6nlFKYtBSCmOHS5H1xwXt9cmSZzmXecdvUqvm6h+Q0zExUanPqPc3KC0NzzUBUJcQUJjoZ5f1Dmc1p0l7Zntw5mI3bph9yKVLVf52LOWKmPMs509ZmbBta80aLygl5HfmJ+MoXFSOIGBDg6s4WALjmdhzHcd7G+N0Z5wyJ+c1Xb3T9yXxTIqr2h4uElAgAMDECwfnWBUZiotn0IFzZ5PEYEPsy1KonE4/S2Exnw6yADHnouv7oaHpwcHh4eHR4eFSK3FO81rk5dSg9MvOoba7spCvbyNTf3u9u3inTmYqoqpQipajI6fgOM1MRKUVVpRv6m7d1GNLOZtwYUwgUAp+vtpdLlKa+wuUPPhJxCBwjhcAhxM0NKyKzHtV2t8azbp5S2Bg1KlKlufTDcHCIgQnMut6KSClFpC/DLM97GewsJ/q3/7qDCGZ1MYCIXO8SOI7zHcwnPvGJH/iBH3jxxRf9UDhvS7zC7ZyjuV+7cbrOzUy1z+/csi6RaEkcxeRiaW5FDVD7DI0CcxOSZgUAUZn208TRwIhoPB6vmxbMrOv6vjcAUNW2bUII5+3MqnpdeysJkTY4box1yGXelaPbFCNPWkoJEe14wftuc2SRPJ1akTiZUJuqFwXvJbWP6//7Pv7VZ6IAlGLYmOSjmXYDjZormxtMVPMQ8+FUcwFGahtuGxCReW+zOY8TACFRQH6SP2NiCobVerSzOVHVWz7s3XEcx3HB7XynaW445dgOIeSczxPcg+ShZDXrSg9mRHS6P0/7QYcMgctsniYT3WgHLI0xIY1i25VeRcMi48JEZaazQKEJqSozRByNRqsUkb7vcy6r6TnnvRcigmqSrsq7SSlF00UkNugRt02YjFa9lbDKMZx1ZTqjFOP2JnFAwoWH5NTbV9M+95FjOO7ZiDHUie+rTO7LQzUQpklglmdzEwnjESDKkMusC5Mxj5pqGkHDPOtFtQmMSAZvgbg9OtZqiVe2N8189qTjfCfy4pLVzwDw8Y9/3I+M44LbeZvTpPj0td3TNm4iyrkwhzPFbeIYOYhI0ZKtkB0zlZhqPjjiUQsxhJhG4w1iLlqy5KEMasrEiaOq1KcFDqKKAIgwz10bmho2t54i0rZttVjP5x0RikiMMaV05nrgZIw3Ko7aMGo1F5n3/Y07GJjHLbcNEumQ8+ERAKbtTYrhvObIFaKKiGIiRQJHxsUBYua+HwDwAQQ3ACARmUHbAIB0fb5zMKgiYdyY1CxCRUMxMEDV2CRiUlWki/w8T9KiTnVZ5EbElZkbEVPgxNymkJhnQz6c90XVv5iO87bkR3/0R1c/f+ITn6g/uOB2XHA7byUQH2S2YD/k9fL2PHdmCgBtbDmyqpqdnf4mKn3pAYDwZOKzqYaNCTEVVUEr0o+ojRyLipmpWaJASCkkETEwMEAABMxSCHCeu1FsTwc8I2IIzDyqdfeu63POMcYLnBwL30iN8TYljBRD2JpoP5RZV45m1VXCbcOj5p7NkZXIoZbk68oB8K68ZuZV+vj9nz6EKtXbpo6iNDXAxeLB0FTBEIwAAumsE7W4MTF4wJd701DTWtsuKgYQKaw0NzMfTaeBqAncBCaiSZvaFKf9cDTv9TFPynQc583nx3/8x6vUfvHFFz/+8Y9/7GMf82PiuOB23mKYQYzh6u5GYD48mo9Hzc07Bzkv2vhiDKXIBcNuBsmipQro2uJmaEMZODCf4yppYstEXe5grcKdD6YYmNtU534XLauXbGPT5R6WNohc8moHCKloYaR7yqzV2MK2bYYh9/1wscmkPoeYAdjUTNVMsUbyiWguFAIFrnZtOstDcpbmjog4lHzCihNjyLmIaAgPYqpGRAwBTa0GnpCtdl5BQcUQEYwmraWQZ511XcTWSAHxvqIP32S1vfxwHJs2j4g7m5OtcVtyzvuHMutg1BgAEY1TLEVmQ/YvteO8zagK+2Mf+9iLL774sY99zAW344LbeUuCCIRIhFubo5t3DktZREM8dXUrprCuDsXk5q1DAHz22pW2SQCQOPamAFBUwGw6zBBARFcafTbMmdhAE6fqw0bAee7AFiNOEBEBw8YI1mquBES0qJEjIBOnkBhpNsyJCGt9G6Co1GxBAE0hXTC/cF2xNU0Skfl8bgZEFGO4oLES6pR5qspbTbVq2VU8NiIWFYKF8+Fe6xtQ06KFiFaPJyJVQUQAfoiTSKd7IBmYsCgaAAIBpUjzHnKxJGgEYEqCfNkRm2/qZxIIAc2UiSPHE2eQiEIIMBnlo5lM5yZKbYNtQ1SHJjmO87aV3Y7jgtt5S5JiuLqzUWuriHh1d/P1G3s5i5nduHXw1PXt9dGSBCEwXdvdqWq70oTGAECGIiUAISKyWJ0SjoAAgwzjOFo4cQG70tdibEA2AFEhROsyMlFapHITUX1MrXImjl3uelMzy0WQkJGk5orUATrVe2AWKFzGKcHM4/EYarJ4LkdH0xhD0zSXjPFeKT8A6EuvpowcONxTc9dabFEJpusPbpqmlPI4xqQ1oUmQhjKICAKEUSuzbri9D8zcpjBqDcFAnyjNXae7R05w3tjLepqIuG3EjBri8ahXLaKuth3nbSy4P/3pT/txcFxwO28lEPGpa1sxBAC4O3sGgBCfvrZz+87hvM9n+jS2t8dAVj3aXe6WChVrzJ9AncrLagLAAKhgYFDVMBMjYhNSlzumEDgWzTVG0BKYqhWBwKsYkKKlL0MTEhM3selzX0yqrs2SV2obANTU1GJsL+9LXpTPEVNKKcWc8zDkGAMR6XLM+wVPrIhK3VViElUj4Htobms4AZ/MAkTEOgTzcaRNI2AKTcEsIpACQauzHgBk3oNBmIwUwLQg1uGaT4DgBhgkI+CJ2vbpU0AxaE8mCgCTUZsNOo8xcRzHcVxwO99eiAjArl/diiGs6+zjj8GrVzarJ+S0/gvMgDDPczAgwuX9eyNA4pC1AAAomFmWIloIEJkHGcwscqz5fW1sa+UycRKVoiWTWSmYNYxbYAYAJl4XvghoYG1smLgvAyynfysYLivHvfQNNJcxlhxXbwCAKaXpdFaDAYmQmUO4d5Y2E6tZttKXnpGJ0sWPv0BBIuLFEeYPp7khcgwUBug1WtgcA4Dmkue9EabxCInrHB9ARP52VrvrMo+R1LQvPRHXjsmTn9IQAkDp+/qRBQAV2ZmMwWdSOo7jOC64nW8vddbMjVsH169tNRTP16Dn1ncJCQwYzyuFGgJWIR6I1WqciAFAoCAqWbKoNqHhpdxn4iwZDCwyMJd5H9oGA0Ntl9O7xhImJiQEBDPGpcPbLIWkpkUKAooJnROQck9SSvN5B2Cqhljt3fGevZWRQ331c9wPlyXGOAwD4gO2Tl5AUak3BCJHJBYWQiBA4kQ554NpPpoBYBw1aTIGRi1STf3fnjXhmhtdVMlMTIsUJgrHlXe1ciOzHM2EEDcn9ay5jdtxHMdxwe08CbLbbtw8qHfmn7q2HR+RwstaGFnNAGEYMhErqJoxUi1SEnLtLzyhh5vYEHFfeg4kfTYRBQPC2lkoJmUxWR2zlKw5UEBYyCpCGmQQVQJEQjAsWooWNWOi2qm5/lrzPK+13jPWCmYhBGaKcWEEn83mIvceKs5Icv4S5bJCk2qFWx+mdfKMkyLZzAixul9qByqQgQGYxck4jFstxdSkz9O9g2ZjEtukomb67S11AwAiqJlKEROykyac2r0aNsYAVltbkWh3a0NVvcjtOI7juOB2ngjNXQXr6zf2nr62E+MjEHkGVlQCBUKMDXZ5rmLEvLJRiNXa9skBkwhYR7UXKWEyMrEyndKooZgAQc2yZAJkqs2YkEsJtFbGNkBA5qCq2TIAECy6KnsbAvGqk7LLXdXo58m7GMO6kySEMAxDTfK+6EvCgYkB4eFq3BBCMHvETm41K1qPCYkKIoGZmNajRIFAASkSIrcpH87623e0beLmpJpMvu1Z3WpKiIFYTEHLur0EiWAx7AYRsRpLEDHFGAPnIv41d5y3KL/5m1/0g+C44Hbebsr79Zt7T1/bjvGMc11UEODMGeynHlkIsDqqpU4tYUKGMggxMrOaNqEJ5xisZ8M8haSoIoVDmGztDEMvIsyMACsDCSOpFV6qbTFRtfVZ64RoaoZWf4MEWUpfBq4eZRUFE9UzR+QQsUhZH9lTZ1KKCBFeLIIfiTCNMcxmcwBI6ZEJ7hSi5cV09CxFVep6Q02JGBAN0eqoHMO0NbFRW45m0mcKDGbf9pRuxFXmOsJy0vuxtVqd8lNnFSECwOZkNORye//Av92O8xblu7/7A/f7lNd+4Z/7cXNccDtPvubeR8AU2QB2tsfMdHjUbW1M4HJ22KyFkQgXw9pVhZFrU2axoqag0MY2nN/OSIh96ZvQtKEBhFwGQJOup9EImdc1Fi7CBkFMCYgYEUBUIgczExUkLFoYGAFNTUFraLeBEXGdvWhnva1hGEII68IaEWKMfd+r2ptjaWbmR1tURsAmNvUHNcsiRUvtRFS1rIWIsB5eBFDAGIAInox5jfW81zmjhFhN/Ku/NTMwsCwAgIFxOSkHEZmJCNVDAh3HcRwX3M4TpbkBrBvUDN64eVDFWSm6sz05T/5Vn3QV5IHCMmYbAGA1vVDNiKihpsbtnffqXe7ElBCLFgEsWswMA4OyqcLaNMSiZWXcWA/gq1JMTBFx+V8hZEAMEAAXwosIwZgA8CxXyZkiE7HGJtqb468IgUsREeVH559e3Z1gIlFWUFz+kaDOilncHwACUAMmVSXR6j/5the5l7Hc4aJM7uNsb05ExJ3cjuM4jgtu54mjiq6VvRsR1BQR6Kw2PqagmhGIkWkpesRUVXjpmSZETjzv5syTCwQ3EYEutVWN+wMgJCbWPhsAhwAAiERUC5l4SnQhAAQORayYMIVFViBioFC0ZCl1LE51kpwp3ZiplFJKSSky87rgW7iEHz/MPAxZVfgxNCwGChBAVGr0Xh3zeXeZUQvGZkAoWbgIxidjGg6CaBGVwOGYh7v+b2AA0CKLUMX6iUKkJ298puM4juO44HaO8dTVrZRiLVvj2SoIIoWsZfW3RcXAAsfjtWKDCF3fj5DOE5GRY4Zc/eJgECgUK1kLMUHDeTrFdkxq1DaL2uzxHVLThps6DSdrIaDIcbUGMLVIEQAY+eKI7pQiAHRdf6LUrWrMb545IaVYSqn+9cehuUvNR695Mrawd6OBqYEZiMCQQ0yUwsK/8+2GkABBTVUlm901ltS7D8yUonS9dD2OR6sbETubHlfiOI7jvGXwKtF3KDfvHOVSVoLr4Gj++s399eSHailJlMS0ToUkJDDLkle26aqWNtpJk5phGHSRKXFauyMAEqCaAWIMMXJkYmYOMcXJOKWkaMPQldncTm1EzeZ5LipFxFQjB0aqVu88lGHIdebOPQfi1PRxIjohMt9kzcnMZiCij8lHHTgSkmgxsEXPIWCtDevRvOxNCYliqHOFnqjPpIGpqZqunzKoBm4iLQVscXsEAO7Z5+o4juM4Tw5e4f4ORVVv3DpEhKtXNg8OZsNQ1OyNG/uA0DRxc6OdtCNGBgQsmDUTMiEix6x50WKIADUqBDBEHobBzpeQuGiCRFHpcqemuLAMwKgdZynUJgSUrrdcTA0Dr4TwIjMOoI3NIEOWPEgmpMQRwC62j58m5ywibdusnkXEIkqkb5qAa5rU970IhvDov4CBmOMoaymSbXnYawYIMpv0EGMd9gliZopUT4Tde/1RXR2q1f6D9ChXKqsGSjPTUmyxTjNTraPd66Se9Zf0IrfjOI7jgtt5C2huALh569BsUW0VVQCYz4euy7fwqG3S9SvbAICGYgUpFJNIkRCLFAJSMAPoyxCI7cKCbeCAiKKaKBWTIkVVsxVEtGJiysiIyG0DAMPeITWJR83KV81IWTIiFSlWXdcExsB8d2xNlqymkeN5OdywaN+UFNK6to4xDEPuui6l9DgU8BnLD0REUn3ATs0spWZ6XLB9RioAZrryQgMCNSmYyayTruc28bhFZiOqXadVdBsonh7/bgYApoqGqLiYWAP2KMdV1rASMwPTKr5XH9N+MDNOcVGvX2l0L3I7ztuCT3ziE5/4xCfWf/Pxj3/84x//uB8ZxwW383aT3SeUT52IOJ13cBs2NhpcTo8MxKJSwMCAEBgpWwGwokVIur4fte2ZGggBAwUmQ0ACKlK09lEaFJO7HYuIABC3N0wU7G49s+alUPUYmCFhCpHxbrfnUIasWc2KipkFYkSKHNbFd1GRom3TnogkR8SUolno+x4A3hzNnVLs+0FE7uvlikqRrKaJ08WPZOJRHA0yVBGbrRAgM9KowRR13oOqzDpVVWZkRgA0U9PQNiFFzQUQEAmJDBQUQAxUy5BlOleAuDUJbTK1B69zr1laqr+ciAAIVPL0ULoBYwA1E6EUw6ilEBARnwDTueM4juO44HYeGWY2nXejSWwpVsW9SBkBI8Sspc4kEVUDQ8JhGBpNFxQdEbCo9KWvc8jBoI6wCXgsnRqJytGMm4QpAqKZpRCzFFFBRCLmpf1AVOp8eAMDwICEiHWbosVAV7Pfq/QEAF6fYbmmud9kMbec5nOfZwRMzQygl8EAIocL1XkpKrB4ihmgIhIjIlIK5WgGgBSDliL9AADEBGpFDQ0oMBIhoIpUx770GcBsNTGnyPqK6EHUti41tykYQJHcDzoMJkpNE7c2anmeYsQaSsJ8uqBex+KYeSC347yF8Xq244Lbcc1tt28dXbkyaZsEgMXEQA0AkQm0VqR1OXdm1LYiQkRnau4si6ASwpr+BzUCpXb1Vavx3aHrk5Fp7bEEAxvKgICBY+BAy9C/mtjdlV5NGWmV273KBBRVIwOEvgxFC4DJhbNSmLnvB3izitwxBpH7y+RGgEBBtAAiXbg8qGqbkMwUwAIyrteimxh4ox+KBU6BTQQMkKjMe1C1UvJsLjlD08RRw0TlaKalAKIVCaMWwYauB2Zuk5kh0X0rbwMEkG4YprP6vqAIBuZRSzFiuOsUqjMmF8uhU285MIfAORf/qjqO4zguuJ23MKI6m+bAHEOIFLJmMBCVVaG4en8ZOYbYzfsz1eo8d7U+jYCEqMvYwaqPzYwQVRWgDnlHZC59D0MObUtMmot0vYrRaKSE3DTEvAqcXjgTToYJGhMvC8mKgJIlUODzC/B1DuUwDAAYAj/uA1szuRHvI5M7UBAQA1LVrBkQGPm8s1ZvIzARI6Gt30FAJLKAWgQJMXK1kiMRjxs9mpfDKTcxjtvSDX0/EDOIcJO4ibWfNRDB4aw/OGpgI7aNqgLivb0lZotoQgBEGmZdnnUxJWY2ERgRBiYOi+5cXnbNXnjnYTIe9UP2vknHcRzHBbfzlqeGiohpGxo1zVYQcDGjEBEMAayNDRM3TTMMOSU8ISKJaDl2RbNabZGsgYNtbIvkWo4lxJoKp2CWIgOU2RzM1HS0sRliQkTpeisyzLoSwGgxQOe0IkMAAiwqorW8DWYQw0WRJlXnIb55fXh1Z+6rdZKJiwogmFqt369TZwAxkdUEbkLVmuFoaEBIi0GeiIYmAEdH87FqY0rEHJiQaWsCMqpBjiEELgXEsE2YIhIhVh+J0UbLMyjTGRnwqKlOcTx/5WBqoEaIQy59N7Ap9jnGEEYNEtV6vYoAGFdP+eUOiE/AcRzHcVxwO28TxpMGyBalSSQCYiKrUlG1DnDpcj+KGALnnE9vIXEEigDQla72PppZE1JNGzQzMVVVRTAzIjQDIkIDiMwhECKnRMQAwKMWAfrcDUO2bggcjBCKUgw8apC5rhAAsZiwGhMlHuWSIeJlZs28mZPeU4pd16tqjPHywrEaRRR0KAMECBSKSq1nq6mYMLABiAkpQb17YGYAumw8VVMxLSKIiATIkYiAEAwAEZa6mThaDAC2sHMQQl2NmBFi2BhZn/N0Jl0fNsaYGNQA16d81ihwADM0G7q+TOdQpNpc0qhNmxNkJlre1YixdJ0MOY79uuQ4juO44Ha+w0gcRqlFQEICsfU2NQMTEQAAhFmeMxIinW5iw6WzmpANVE1pac4FgMBclAoUAANAUR3FtqioCsSgiIy0FmSCADAab2ieWYqEZAaEaEMp0zmPWoqBkKqCTzEGDqZmAsjQlyGFe4zIIaK+H2p0CV+61PpgIGLbNl3Xi+j9CG4sYEtTcx3facsqviWOqxO0Os4ApiYAqGCmQkiMZAZtk0ZNU46mGAKP+LhcBjBEOiufGxEICRFaohDKdF76PoaRIQAs7CXVPVJXZQiABtjnQBSvbC4StQmJ+XQrpKnC4u7J5Y7hsRRxx3GeaOqFTvX+5h7UNC2/neW44Ha+A66SQMtkwKA2gMEy+8IW9UlEAFCzUF3T51SIEZGQEyVca5FEwDY0nZnBooQqqmJSpWQbmtMzEZEohpRLFlMiRCRqEwauWSqwps6HPueciUhUDJUUB8np/MmU1cltZqUIADxuzS2mIbKKXn7YOxO32NbZn/VdBGIlHiQzsgGIZARgJDGpdiBEYOR6J6GepsOjrk3N9uaEEIeRFZNlOfq4mD2vHRJBwQANAwHhMJ0P/cAxpFFLIYAqEeUhD33GwMxk8x5V42TMKa3c3kSERNVEREhaCnGgNtzX8M8YQ4qxP+u+iuM4T6DgHo9GX3rpqy+8772XFNCq+qWXvjoejVxwOy64nbc5g2Q1rf15gUOWbGBMRESiqqaIyMRmpqBqVkTorPQ9WCbZ4SkZ18sgpnVmu5mFEKQIIgSKtffx9FMSx0hhkFwkV3Et/YAA1CYkKvuH3DZzm6NSSpGIiomYiAohFRUxDcRnTsmpl3VEzLksGvgeD2qaZVBTyYrYXP6FEDFwWB0TBGSkRNGw5iFCnSCDQIvgPV2I2FWiomo9ayQmJQ8GiPH+1hVYTSZqPBlhCjYUHcogszhqVK10vWUxMwATQg4hTkbcJOK7ITZimnNvoIRUvS06DFpKnIwvvxvjUdv1Q7/vgttx3hpsbG7uHRz+03/+i/fzNR9tbG76oXNccDtvc7p51pFVZy8C1oHhiaMBBGIArvKrOokDhWEYCDHGeEbi9TkVU1WlZR6FgomW5eDDc5+FgL3UefJYTBg4jFvtczmccZPiZKwIpcsNR5EOmmRoq+RBMUFDkZJCOq/UXdcMXdcTUUrp8lkilydLWURkM1YRfPkSzoljwhyYoGgREDNLIZlq1sLVUoKw8uCr6eFR13dlo0UAICRcRr7Q/ZSWETCEAGoFMmKCEC1n6Ya8f6QAoW14MlYCNCVD4kBhaSCpJnKV+r+IaGBqKoChbXTeDQeHcWNyyTGW3jfpOG9FzT2eTE6PXTvvUuzfcccFt/MdwbwbRDUu/xg5VqNC4qiqi5mRS8ewmlKkXApzYL63gOtLX7Qg0KrYzEhFhQAN7MS0yBNPrHl/UD0VpoYAKUBAIyJiUI1NErSydxRtBAYUA8YAiIvgaMSipS89IjUhnX6hGEMI3PeDqj5ywT2UQVUIkZCJCAweZn5LdcmrWf2hDqRExHpG1NTMEImBCGkyaQPzwXSGiFsbY0JiAsL7rXATIlHAYqJQJxBFDgERgaqZnxRMVRCIiIkXidpZctGCgHUPTbRIUSkxpDBuYDIufS9DDm1zyT1hImYSUf+qOs5bBZfRjgtuxzmJ2bGuNDMdxbZG+yEjKBQtooqAaouWylJKkxLAva+naoZAhCimq5Dm6gs3FTU9w1tcn6i6dKGAmQUKAFBACNnAxMQUAgcgwJ1NM0BRAJB+oBhwad6oXvPadBjpZEm+zltpmjQMGQBCCI/Qzk1EWYupNiExcinlkfT+4V0ZymZQVOohBTS0erQhcmg3GpXDImWQXPJwX2GI1VJPi4ZFJKKiQsQhJFOtDxBTtYKIyByIaZmJXl8RABixlt7LrDcwjlHNpnfuIAKHkO/shdFodGX3MvuzORkNpdzxNG7HcRzHBbfzVhbcx4Rg4rTe78jEjDzTuQGkEKvC4xiKyD07DvsyACydDAZNaAwsS64am4kXAc9n91/SIo2aaDXCPTIMpRfVFFKxEjkwc1+jxENAgHw4RSJcc0sjIJipaqc9E9X58+tdlUSUUsw5d12O8ZFFlzBxTRRhYhVb5m08ArW9CmmpXZV19VJUAO3wqJt3Qz3a41GKDeWSLdyNClmOCrLqyCckW54CA6gJgwCGgFkzICamSBEDIiJTqB+VIkWkGAAjBg7rph01xbUzqMNgiJQiEhkYcgIwQUxXd2NMl1+6sJfKHMdxHBfcztuJk2Xg5f+kkAIxYVHTEEM37zOWGMMF8tRMwe7qzF6Ghed4uWWRkgGrMF09K2tmZCaKGIpJQF5JOgRoQjPIUEqpbZ3VZXHXr9KmMu8CAKW4/o7UVM2qHDSzzrQNzXHNnVRNpORclrL7IcXx3cbHqnIfvsJNRIvGUCIAMtBAodb+D47mh9PZeNSMRwkJY+DAXIvMOmQjghBqjAkhgoGYYO1hBYsca7NskWIAMcTlhEvrc7/o4ERcfTYCBzEpJoFCOG6RZ2IDIKRADGAZCoagzGKCgEZgBoxoTHY/h9ddJY7jOI4LbudtpbBPU6Q0IRExAgQOYICIo1FbivT9UENCTjxFVPoy4NrGiei04qwF4PqYrCWXoSrTNlBVqwR0wnCCiIlT1gIAajos8k+41tEpRsrlDKmKqzGKAKBiOs/zyClypKWUZEaiyGw5577vU4ohhIepdq/2nAhVDUDPS3e56OBrEVNVCRTMzABSaALxIIMoqqmCTmf9dNaJKBOORy0gINZR6yZgFgIQiorVwUMYqAZpL9chiFi0FClqxsQBQ5X1AKAq1XoT+dgCJnIMEE8XnquVu67QtAgQKpKZLlz1gERESGBW3xcCrNIPL8BdJY7jOI4LbuctzLPXrzQpxnDRR2WliWF9xg1RjFgnKZ4W3LVhDu/+UH82NSVaaGgzIyRVUURCElkI5YbT6jFnB5gg1npnUamzVwANkGpEN4/afHAUzKhJZ8pfxFoXhzoF8dSWkSjVoO75fB5CvLiKf0liDMMwIGKM9/+tNAOALIUQGZmIxLQmNqro3sG0H8rGRhsDMxHR4tjWZ0aOiqoGiASmhExIshhdiYjAFNRMlzEmCDBIL7o4ayvbz+mPxPnLDBiOZmCGzKqCkZAWxhXCu7PuzcxMDCxQYLiH4HZXieM4juOC23lLwkQGFkO4vX9IRDubGzdu72+M283J6KVvvnp772DIZWdr4/3vesfonECJ/YOjz37hK9/17ueuX9k5oUpXVoeaWaGgjKG6QVYmEwNTMzE1sMSpCU1XOl1KvUupWA4JIwCIStWjBgaEFANcqM8IkYhrvsfp9JLaTBkXo+xL1/V1LOVDHW3mEML9hgMWlb4MZlaL8GoGplKnTgIQIiDubG4QkpiY6cqirdU6byiqtY3SiEQhMEOd3ElcjdxF8t2WSkQ1raM9iTgQM3LRcsn1hgw5H02RiWNEJoqRTItJTQ0nXKQWrOS7LqMML3WuA8cQcin+zXUcx3FccDtvGVTVAF67ebuIAGDXD7/w6V/7gY98aDJuA3OT0s07+8x8Z/+oDgk3gKPpjJnHo3Y6mxHR4axrUpqMRweHUwPY3tpIy/LtSkVVfzAA1NmTbJylECwMD4QkWoAWUd+BgqFdJlJjGHIId9v1kJGJEbAvvZnVwePnPhmBkQMFwosMHlV2pxRFtJRSRfNDfRtD6Loe8bITjAfJdQgRIpqpqdravlU3vJoSU+SACkVBtCwcHbYIGDE1BTMTFQUAhACEWqQuTKz6cHBVFEertm4AAmQKCxPRZT5OImAaJ2MKDERYB99YEZW6fGJiJs5aqp+7TqRnCvf0k1Qmo7Yf8m13lTiO4zguuJ23EM9cv3J773A5NNtyKYdH01IKGMzm/a07+0POb9y889qNW7N5/zt/24e++cobR7N51w8f+dD7X/r6y7Ou2xyPb+0dqOqtO/vTWXdlZ+sHP/o9W5uT//q//m/+1X/1X/ngBz+wkK3HytULo0gdhoJ4LLtjZRC/51KBmdaTs6uarwMmwUxzJmaIZ08RV7PEl9V5iLXOneX8+ZqXBBejfy67BVWtpndEIOQCYqY1lqSuJpZR3As5KypmUNsia9meAI1ASjEi5GRgRaWGKoLVsZQGgDWo0QzUFA0Mrc5jx+WxveS7M0BkWs9krLK+ZnKLKQNHCmZal1uIFIgvuX0iqgEyZuZfXsdxHMcFt/PWYDrv5PgksJUcVNVcxAy2NkYffN+7Pv/Fl77y9Vf2Dg5HbTtq29feuHXj9t67n3vm6Wu7N+/sA0CMgZhefv3GtOs+86svfu5zn3vppZf+/X//33vf+9574kWr3goUshQmYCRmCrQMwbicukMkESWyE5XipVEY09ZG6Xqbzblt8FRZmoD6MhQqhAxgtdR98Ss2TSpFptNZCKFp0gPL7pWn4jJbCMwApmBghoiRopkFDnx8b1eHLnECwKIFamL6crXDTVPL3TWkBZGIFosTRmJaFPuzZFtOo8Tad7l0BC0lrkWO692Txw6+qooQAgAMkouUuiUzUJO6MFjK5cWY0VrzvvzR25qMSyl3Do78y+s4juO44HbeGhzN5msmBbiyvZVimM27N27vHc3mtcY567pcyrwfYghdP7zz2aebJjYpvvzaG9tbG1sbEw789Zdff/dzzzx19cqvf/ElVf3+7/8oIl6/fu25595xllbGmvNNSINkA4uXNhWsbQSWc+KPf9yJOY2KFiVjRBOReUdtQyEAwKJqi4gAhGhmWXPiSJdwsNQOUWYWKaVICA+Y1R0CD0NGhBDu/d1k4iJFROpLRYqBwwWLkqJFTZZZ3biKQZS+JyIeMQCIKhHVInGNBwkcGHkoOUsGAEMmpMiRkbOULGWtjn6Rt15zQQSKEQDM1EwRefFCRGZWtFQTUa2FmxneZzA5Mz2kq8dxHMdxXHA7byrrajswxxB2tja//PVvfe1br6a0SHxrUvrsb34ZAb7vQ+9/5bWbL792g5k+/MH3bW1uNDEgwqhJWxuTG7fvpBhDCFJksrHxgz/4O0MI52mjVaJz4giX7pkDgKxlMXLS7Ex3Ry3oRooA0NV5LjHqUHTIlCIy11y8RWidLYYmXrLeXANMEEPf98MwPFhoYB13rKqXaZ1cuN6J4F79hYMMRcRA1yPJYTHC0zAwrszuWNWwMXHkUOeJDpKzDNVcYmZEzAunhync7WGNa9OCznhrMWgpJqJUp+eAqiDWrHSVZUOn6GL9QGuJ7PdxRWMKzEXEv7+O4zjOk8Nj8Tv++pe+4kf2bQMzq+oz165MRs3RrCtFAICZltqLqn25TVENRI0Ix23TDTnFwETTeQc14I9I1dCkaVLTNPQYQtwGyWqaOJqaqjLzea8iKn3pF3EcZpqLDhmJsIkptaLFbJFCDQBNaML9lNhVFQCGIatq06T7rbmaWdf1IXCM8R4LDFlUnQmJKQQ6t6yeJReVpcI+vremZd4hUWgaXLi9Q524uRjGrlK0VBVeA7arCocaAa5SdXpAXmU1nve+pOsAkNvG1gLX1bRIKSq1oF60mBkjEVG4/5sbqnpr/9ADuR3nO4TvfeH9fhCctwRe4XYuIsVwbXcnBo4xEOLWxviYwB1yKSWN2hAYAInu2jjSco7jJo3XYzdUdTabz2az0Wj0yO/+q6qCGoCq4ZmekiV1uoqCiqkBcAwUgqnmeWeqTTsSlZq1Fzneb8BzfbMpRRHJOcN9ppfUKO57FrmHMshyIjxTCHxRcyEiEqCdJYIDBY6NgiGhmoXlpqoOZmKt9o9FNX1V2waouSK4Ko3fu5ZvagC23iarpnV9wkRmJiaJ4+KlgR9gVeaB3I7jOI4LbuctxpXtrXHb1FEpJyhFzDSlRMtZKucJoHUlRkTj8aiU0vdD0zTrQSKPAAQ0EJVSJMV4UaIfICwr9AAoKoGD1XehNuwdWCBqG8BFhsYD7MvK05LzfScGMnPOGQBTOqdCb1rTANFMTCPcw+68iCjRu96YWmNGRCLGAIBAHLMWM60iOEtZTbw3gNrJuppFv3YYL/umTASZ6Lg3XVSyFgQkxFX3JyObwcX18gtoUmyb1PWDf38dx3EcF9zOk861na0Ug6ognuFVWNqU76EjT4teIooxItJ0Oo0xtm3z8GMaq3SrQpIQwez0lPiTu4GkgIikqimkQAHAwiYZALcIZvPDQw6x66dpYxJHI7j/nUTEEILq0PdDSumex+rEEy8YgkOITJxLtdDUnb/HSoSQMhQyRMAaZlJvAjBRHjoiMuaqtnPJaqagDFQbK8Ggxo88mAKuaM4qyvHYdE8DqzOOartkNa7UNs3VS6lplizV8I0U7hVdMmqacdu44HYcx3FccDtPLtWcPRm1bUoxhHWjyHHsgYVyza6eTMbzeXdwcDQaNfHCgvSl9Fyd3wK2NB/fY2uRQiC+c3B0NJuPmgQGWxuTw+l82nVtSiK6NWra8cjGY1Adjqahbehepuoz32lKSVWHYRChlC6bGBhC6PtB5GzBXWeqG5uK0YXmmfXjEykQspkS0UrRImBoGkBUMFFdZPOpVOOHmAJgCnGVzPjgJ6gO1jl+M4SQAFBMllGGuDCc4LFjiFCHaAqQwb3HvGPbpBTjsIiQdxzHcRwX3M4T9YFgvn5lO4bATEx0gYmWiB9yyAszj0YjMxuGoev6EEKMUUQALITIzPe1ea0G4eWklns+FxH3D6YHR7OcS84CYLOuF1FRLVmu7m6PN8arVGzJOc+7iEghPNg7bZom59J1nRnUAJPLLHsu6GlGwNpTeJmqc3WGAEAgJDq5til9X0yt4TpvSFQNDA0EFJajQB+mtl3hFE3V1JDvboqJ20j1nWbNp6YgASwnvdfBkxfP/lwxbpuNcXt73wW34ziO44Lb+XbzzLUrdw4O+yFXhff01d0mxRQXtUwRWU0sP61yanoJXq68eq4IYwIAokY15Vz6fqi/KaXkPIQQajPemTtwSlOaqDAx2F3/tJqKSi17i2nkuD4UphuGGrqyyBXRstrU3sHR4XR2bXd73DaIGMfj4fDIRCA84FeGiFKKZiHnknOpKvzip6QUhyGXguep8zPl6dmvjtiEdN5TOAbVooAAxhjCcgKOqAAiIz+82gYAjjHP5kX7OB6tLxvqHmXJahoonF7jqVnRIqqL0jtQCnTvox1jCFzPr+M4juO44Ha+TeeeuUnx2etX9g9n47ZBhLZJp+XOeePKiTDn8jDDzIuWXHINDAkciJKZrW+sVrv7PscY7uk5aUIyA0QouRBRlixFFdTMCLC2P554ytWdrRh4/3B2OrY5l5ILvH7rDhNV2R0n4zLvTJWYMQS8RBRG0bIeJl0XJynFruuHIaeEF/eMMjOzVGNJjOHhghSRzj96piaqyEhIamoqgUP1kOjxM/JQICLRaekuKjXPscYCnrEeIGpjO5QsJoh4VtrKGUzGbZ+z5wM6juM4LridbyfXr2zXYvaV7Q0ANFMRWa9YV4V3nsxdzSN8YLJkQCgqCEJETHzCeF1fmohFStd1tdvyhO6s6XhEbKaEFCjUuGgzq3l2CkYUwCzwyQntMYSdzc2N8fjO/uHRrKup28f2MJcMcPPO/vUrO6MmhVFrRWTIjHSm4B7KkLU0IcEiVi8zhcTHlgqIWOfAd10XY1zlJ55JXWY8jrD8Y4LbrE67QTBEXAWY1COJ+MiSZErfI2Jo22OvXn1AZnRW6na9R6GmzJwwAlw2GIWJ2hRjDDUlxnEcx3FccDtvNqMmtc2igY+ZzY7NlayISZVcZ9Yda1y0yIO7StSMah6caZaCTCeqsMvdQ6LIHPq+Z7YTQndh3TaFOoelaOBARKBQ51UyICOFUO3Op2QZEzNd290uIrmI6CIWep1+yDdv71+/st02yZgxcJl3rIlTPBFdQkSg1uW+6khC4rPuANQ58GY1huSisG1ErKOFLjN48oERNCM43XwZ66TPR/dCcTyqiyBcTMfUIiVrQcQYUqQznOLLgEIgozNvU1zAeNRuDF7kdhzHcVxwO98m+lzWFXadTVO0dKUHACaqYXAGljiJiJhEjifkDjNX1/WDCe5IoRaVcTHx1M5Td3VqetOkpfuZ1sWrShE1JgoYFBdD3YmoqAAAEQeOF4+KDIGfurpra12Kt+7sz7q+/q2ZdcPw2s3bT13dHbcNhkAxGkDph+7OHsXYbm9RDHU/A4WishqKft6RQcTlTJyAeFe3r4rZy+oy1rfzWIvcWITAKNLaWkvZbLX+GSSram2iXU26ubeOX060WXvXpDpoQU6pPmDQTICJ47ndnwiAoGaDZFJJF06PP7maIho1aepxJY7jOI4LbufbgqqeSKpeeQkATGtOBaBZ7WZbCNHE6YQ74sIgjXtARDUqjpDCKTV/hn5i7vuh67q2bVeaO1Jc2UiGPoc6lRwAoI4apzP78E6T4rHvwlNXd2/tHbRNms272bw3syEXkUXxm5tkIqXrwqjhmJCwaKlHSVQJSVWBgIBq4fjMVxyNWjPLOfd9D0uH97q2ZuYQAhEyh3vWwh+G2I7QpJiuJq7zMgykaMlSVBURVCRCvPwEHwMTlXoXYfGBIbRS1KwK7kBM2C7e9jlrLSZmlWKCAGZmcH+fNo8rcRzHcVxwO99OXrt559nrV9eFZi1JVulT/0uIBoBY5XgdU3LcdRCDqpyf1X0RNaGiqihRIVxYSrIWRj6zya9tm/m8m06PmEMN11vFNq9Kwqt8ktrwd/kojxP6+9ruFhNtjNqienA0PZrOD6ezFEOTIiIicxyNzMyKTOedMSADGiCiqgGYmjKxogU62whRletxKzzWoT31reec63QhMz0vkPuRIMOAiKFhNauV7EBhdchsmW5ePyFMRpc912ZgRUvVzeunffVu71kvr+mHiFjbT+/3Y0ZEO1sbqrZ3eORfecdxHMcFt/Nm0w/5xu29p67uxBCKFlGBsyaE4/I/qtKrAiITxWWWMzN3XU/EzPctaokIDc0MAUULACSOYmKqvZUUUpG8GDq49pTRqK1xhCLadb2ZhRBiDGa2rvsDcaCgpn0ZAICQ4qmmyYuJIdRXjACRuRSZdX2+eZuJru5sjdoGmS3n20fTo66/urs1bloxISSzWtkFVcV7DWq5QEbXVPIaaVJzWh7TJwEDIyJRNADg1eQgAADGRU52USlaDLRoCcRgcLF3P0suWmqkyKosnedzFYnHmyYv8zlZivwHcS4F5hjZv++O4ziOC27n28Os66uTW02r8L1IliGCAYAVKWHZ33bCBXF/Og8wUuy0r0MrRUunUjeFiH3pVbWGZ4c1gy8tx/EQETMDmKr1/ZBzDoFXhofqCe5KqVGDBvpQ35PARKiq/aAAUG7dYebAJKL9kEX19t7h0awbj+OoaeoOG8BQBjMoKrXILaZ4YTzfGQsSRCIWETPr+37Rw8pExLB03j+Cyrety+eTfat1Go5pRkAAVBVDAgMzY+YsWUwZiYnX1zM1XaQa2e8exqbVIMh0v5+Th+zc3JyMcxYvcjuO4zguuJ1vA9UtUFSyFLqX9WKlexZO2uVja1aJKhHdv6sEkZBqxggg1LrpQtyD1SE1QxkoNKdb5RAxBDIzRGWmEELf97PZfDRqmRkBixawVWn0oSTb3sFR1w9Xd7bmXT/r+iEXyKX6P+pSY8hFzdo2iIqaUY12QVSVoUhGJKTI8X7Fce0WjTES3R2Uo4uRmqiqOZda4H+oj4EarC1IVLX2sIqYiIjIIrkFoeYHDpiZuWlSPbCmqgR8opCPSMg1ybuIoBoCSs61DfTNvswxNykS0ekIGsdxHMdxwe28GYgWAqwxzKtSNdHZ+rtak497CR5KyyaOWbOqnihk1j+Kiil+9dXXbt052JiM3/P805PRXUPC7b3Dz3/xpXnXfe8L73vm+pW2bXMe5vM5c2iaxMiCUkQWpuSHmOAyGbdNk4ggJBxPohkcTbu+PxbwLKKqtdNUFdDEFrITtC5ssuQsQ+QU6D4cDnUpw0wrwU20SjJhZs25DMNQy+H1YfcV1FhzEKVIP53B8gbCctWDKUWzWPtoVW1llFfVIQ/FipoZmKoQMq2VriNFMFATJmJk6QZQ5SYhMyC++R/yOgdn78CL3I7jOI4LbudNJIawudmqSW31IwBVTaEx06znzgphCpHvitdSSikSY3iA8vZCWCNGir32dVgMLnW3miJSoPgrv/7FO/tH25uTr37zFUTb2pjMu35zMp6MR7f3DiajUY2rm3Xdnb3DIZdru9td333z1Rshhqeu7ozaptbRH/JYxQBmJlaYEQADs5odHM77PgNAYEaEeTfEwClFXFuLEBKgqVmVoXyfe1ITQuhYuN6q6RAAah09IEIptRhtS3S1FqoV6+ocqcK9/kZVidhyZmZumrpNNc1a1LThxBxWWyhSxBQRzdTApKgV48BMYX2g5mJVgJg4ipIOg0pBImobCg+17HmoKx3zqGmmsfM5OI7jOI4LbufN49ruVkysJrCMJSEiJipqhGfLZzVr+JhVt1oaHtIkgIgpJAAwA7FSRBAXWYH7+9NXXr/1gfe+813PPX0wPQKgb716Yxjybxx87YPve/dvvfSNOjymH3KTIgDuHx7dvLN/eDQLTGrWpgSqP/VTf/sjH/nw93//R1NKD7aHdUh7HbJTx6RzClVW7u1PY+LJaFSlagh3u0drUspKsDKzgvYiqppCDHSpb18tKl/wgJWLexV4Uv9zfCOr32D9YZWFgojAhEQUuOr7mtV4Yg8NqpFoEQOJtLgHUX0yZ94MWYh7ZGDjJiES4LfzAz8eNRvDyOfgOI7jOC64nTePFAMSqsi6toP12Laz5N+6+Ms5187Fhy9bLkQ8AllkDKKFiQ0sl1JERuNmczLigPsH09dv3t4/PDo8mj339FOHR9MPvf/dzPytV984OJp1fT+bd0MubRNffv02Eb7wnue/9OUvf/azn93b23v++eefe+4dD7yHwzLtZP0gpBS2xoljDInNjOzYsUNEXmlMBKh2Z1NRNbvsV09ELzla6JJOkqrg13V87gckoxAWgtsWKezrW6vz1de2AilGNMxDCYFDOPvtVIc3IuCb7ts+DRPtbm6o6v7h1L/+juM4jgtu53FBiLXmem13GwlVBQFXFo5aAg3EiIt5N2g1VmPlYaC+DAjAxKZAiDHyA5tJVkqups6lEM0W49AJo4IOOTejMB43X/jy1/cPprf29nIWQHj2qav9kOsb2dqcxMDffNVev3Hr3c8/O2obABDVd77j6Vdev3FwNH3mHc/8yT/1f21Sc+XKlYfYTay14eptvvtbg6BGZmBQI/BOyM3TKYu6SKeWE7EeF+jjRztlcq0tdfkbWtzS0Ls1+WMvWUNsju0VmIJF5irRzxvKYyKIgPykpPKFwKOmmc66srbOdBzHcRwX3M6j5PrVncPpfDJqRk1TpNS5MEstToEXc2QYWU1BtYbYVRlGq4Q4QEIqJvjQmXR9GWpEiZoWJTMj1MWgEyBCbFL46Pe+8M1X3ri9d9A26flndu7sH5rZ888+tTEZvfPZpzfGo1zK7vbm9uYGEY5HrYGNmqaU8o6nr+1sbWxvb+7sbiVOTA8h+87RvCpKKVIIi1wVoHu1kBojGZqYFJV4r4FBqkqED7mkuSSqJiJEFCBkHQbJ1UbPxLXsffLxpoAQY+z7oZRywq6zfzSdzfvNcdsyfbt822cyGbX9MNzx7knHcRzHBbfzOHj66u6oSYyYYrTlFMZ1/aSqjLzw5lIEy0ysZqKCtaMRkCkEYiYWeAQJa2oKi+ALEhUEEENEYbwbvH11d3MyaoYhc6C2SU9d2zFTptCm5vlnrrVNUtXdrQ0iKiLLcTxUiqhq2yQAE9UBcvOgrZNFZZC8Kvquj66U6YyatAqWrkcV7pWuiFCXE3TPvI5SZBk3/hgxFQBCM0QkQsZgoPXOg2ipM9XVjg2YRCSo2e3nyOlcZDqb98PAiFsbk+0Q4MmQ3cy0s7WpZm4scRzHcVxwO4+YUZPGoyYwB2YRRQTRxTgYAzMzQrY1IwEiRg6IVHIPdbo7EKxiNwBCCMMwwHJE+UOypsUsS1HTSDGFVKVeGDNMRnWIY4rJwBLHdfXcNmd0Q3Zdz8wCBeyhiqyM1IQ0lEFMDYzh7tYoRTAz1epRPu81VtPREVFMI4fI8TKGa2YS0Xv2TT4kNTwEEQnvVtPVDEAXg43AzjhfSFlKLoUMT3u4tzfG47ap/Zld1x/O5puT8RPyXYhuLHEcx3FccDuPg93tzbBMaDYDVQnExGRmgwxVFoqKsa07trPkYmJmaEBEvLSdQA3qflARWLQUkVozPnMrqlqgBAq0iN6gqlZtMXQHLvPaqhoCV3Vo1YX8QDuMiIzcxKYvfVExsFrsR0RKSfrhruBGrAuYE95trcITjACZWEyl9M0lXC4PMKhFVO43BlGGTERhLbMv8iKiBBHrrY/TxxvrO0VUNRE9se6KIcSlCh+GvH9whIAbk9ET8nWYjJp+GLmxxHEcx3HB7Twanrq6mwK3TXO3LktUAy3UtGrHwGElsNafy8TBzMwC8WKg+pqSCyGUIg8wO3ARMAdnD5M3UwMMy8yNdQsH3msc5rGdZzKzyFFMRR+2lklIgSIiVVFbFeey3fCuD15MwU66J8zUAKoz3tTq3YNLdkwCXCp7pNp+ajtmIK4zgy6pvDlFxGPhNLQW4VfzSc6cr05IBkZMACYi593r2JiM+pyH8gQFYDOzG0scx3EcF9zOowERR01qUjz+y2Ut1kxMzCxQOLPaSkiJo4GdqduYuSZU3NdoQwAIGIBArE45PLlxRATAIqXqPAMIFOj+y+m1ny8RRQqB+EylXiexM/Fltk+IZTE10gzMgABAcyFAYF7NvT9t4w4UixYFJSAAq22pl4rwQxuGft5Z2zQppWM5faaqUhdFhFS01MlBjEREWbKaBr5c1HcRIIJ4xl/pcq1yYm9tmextppFZi5mdK7hDCCGEg6NpDPxkGUvaZjrvSnFjieM4juOC23kIzOyNW3eeuX4lnnLZFi1FSk3iExMRiRRPq8CLi8p1zOT9mksQMVBgMCOrSnGxs8vBivXPWUoV/TXJpBrN1+dcnpDOdLyDj4hURZWZz1HbpkVLUWHjE6bwlWnkmOAmomzZZFWZl1mHRBT5zCMkogdH8yKyORmnxAiAiIZkBnUiJBNdXIE2sKOue+ONvStbW9eubKcUV6K2ZilWW06BUqRY9XhQEJVa1Ce8XMMlnZu9Xu+BnPm5UtBF32e9W3J+OGBlyGV4wqY8jttmazLeOzjSR5u86DiO4zguuL/TmPfDazdun9bcg+Q61B0BVVXNikgbm8vbf1XtAfwkx3Q8LmwJdycgkompaFlMKAcjwColwUBBBlFCqtGBJwR3ATlh1Ygxdl0/n3cppZTSiXw9Va1+CRNDgLjU3GralwEAmpDWtmY6ZBgKEmjfU5MwMhJh4DNzpqez7nO/+dLewZGZtU367hfec3Vnk5kNIJeswRDRFNqUYghdP4hokyIgDkMmohRZzbohd31+7ebttmmKyDCT0aiJIVRXuqog4sLygUiA1V+epQBYPOeuxZln4/SCQVSqoF+eoHUJXm30C4sRIWGAris5l6Y5e5YnEabA4QkYf3Ps8se8s7mhanuHbuZ2HMdxXHA7j0FzN5yKlur0BYA6TR3vp6+wlBLCw46ZRMRbdw76Ia/9Bna3N9sYAMAARIuZrXuI1c7wfxuYqFb78rrgRiQz67qemYiO2SYCMWFT3RdFBQCZyMzEFsaRvgxMFCgQUpl3phaa1qxYKToUmc6paepE9DXpuvj/X/vma9NZ9753PbsxGf3WV7759W++9ltf+cZ7nn9mMhl9/VuvjUftwdF0/2C6u7V5ZWfr1p39g8Pp09ev9sOwfzhFhA++752H0/k3XnkdAI6ms8lo9PqN27f3Dyfj9sMfeN+zT139Z//rL0y2Jt/9Pd+NizBvxDrZcTG53cSkJqKsJrSLSlXnYe2XUGMBjdZ19tIUs2wPBVxX24RYj6qY0EJPMxGLSJ2LeebajIg48BN3BQy8u71h4GZux3EcxwW38yg0t+qx++ZMvChvm8KyyDnIkHjRGngxIqKqIUQ1KzLE45aM+6LrBwPY2hgHZgC4vXdgBqvqLCEWKVkLmBFx9XOfUPmDZFFFRDFBu9spiIgxhrq3ORciXpeDiFgnREK1sjASUtZspoRo1Vhiax6VGDgGBEbCMgxahM6Y6lKdI3B7/3A8at/x9LXNjdHN2/u37hy8fvPOtSvbMYa9g6NvvXqjSTGG8MrrN/cOjubzLsYwHrVmJio37+yHGLquv7K9OR41X/nGK2ZWW11fef3WM9euPnXtyhd/64uf/bXP/Z/+nT/yAz/wMYK1N1XFMaKZqeoqxlFWVnuDLKUa9xc7zwSrc4cAAEVLoLAMX6cTBndEtMUSZfF6iNA0se8HkcJ8RpHbzIqoiD6BX40YwpXtTQBwze04juO44HYeGapWzRWEFDlmzXXKSW2CM46XKVmXIrW8ncugpgVKzZZ+gP25trsNiCkuOiP3D6e37uxPm2ZnaxJDqJYGBCDiwHWU/MlXCcT17YiW06HRANA0aTabn5aDRUvRQkiBmZHUTE2rwwUB62DI+qakz9wSIBIgc9Bo1iicquYSLerBWxvj127cuXlnPxd54+ZeCCEwd/2wfzjNufRD3t6cXN3d3tnaULOrV7b29o9efu0NIrx+dXve98OQ+yG3bWrbBhH3DqZXtrfe+exTQy5ZBMyef/757d3td77znWce0kWKIggilaJ9zkTYpoRIRWXIRdgoETOLap9VrTSAAFBE6lzJgpmZiFjVBIx58YFR1WEQM0BEZgSFbsgpQAyMRP1QRCHFUBPEcynMFEMgIqInaeCka27HcRzHBbfz6CXFWmsjIuRcAICIanYeACBS5FAuHZ+3qrkKaPVfG1zWj1L7NavcR8QTY2uubG+K6p39w9dv5eu7202KkSIAiCmeaTeuKwdCQCRENa350Md1MNUA8jpEpqgULXVTNRWx1vvN7roylsdqIaCRafFEycv2RDJRo0UI90rp1oPz3nc9O+TyhS9/ox/yeNRe3d0iwldevzUZtWb2rnc81ff56996bXd7s2nS3v7R/sHR1Ss7s67fOzwahvzc09c3J+OXX7s1apMppBj2j45u7UnOud4H+KEf+l3IlNp0wXEmoMOj+cHhvIiA2cZklEI4nM1zLgYwbpurO5vTeV+N5sxMhKqWcwGEGHhna5JSvL13CAC725OUAiDM58PB4bya/tsmbozbeTe0TUox3t47GHIBwFGbru1uF5Ebt/falK5d2SYErPN/Hs2KUes5fbSae9y2s3mfS/HLheM4juOC27lvEPHq9hZVQVmLn4iqYoY1qbrLnYGpWqSAl3OG2FI+MVIxITDRgnTZxBI1UyuBw2kBXfU3E71xa09EACIRRYzB7ALXytKJTlX2nqE+iQCsSFHQmpZdrSkppKq2i4qo2HJTahY5MLKp5unMzJAJay6HGSJZYCjFikBApJMvuTkZf/Dd73j26s6Xv/HqG7f2EOC73vt8k2IIhIBtk4Zc5l0fI8cY+j6r2mjU5FxKEUDYnIzNrOtyCrGUAqBiRkQEuL21QURXrlypQ4vOTBGp5CwHhzNC3N2eiAgC7R1NCfHK7qaq7R9Mb+0dzvtBRba3JkRUpfzN2wcx8M7ORpvC4dF8yEVF501MKQJYKWJmmxsjADiadrP5kEsRtaPZXNWubG8aABMhwuHRrOsHM5h1feCAyI8kDKRaZVSNGc70iz8w47bZnIzuHByZh5Y4juM4LridB9AoMbCqMlONFmFeTr9BRMAmNDVs+3582LYcFUkAUkSawJcscZtZNUnXrsQz4wjnXb8+eXt9FMvFnPcWUorzecdAhlY9I2ampqsJi2aaNdNycns9IIiYZ3NACE2LzIiYOBYV0QIEGAIUAVU4lQeifT9p04hp44PvPej6GMKV3c1lIPoikkVtQ2vZfgsBFnM0GQmRDBQAtzeRAEuRogWZ2tRECqLSS19L9dWlfd6R6YdiBpONdntzrGrTeW8G43GzszkR09m8K0XaFGed7h/Oxm3TbsUQOESOMYzbpKqzbkghCGnX5clYYuS6dKnekjVlXwBgczLaGLeANRxm6HPeGI+KyNF0Pm6bhW3pUaweF5/aR+1QYabtzYmourHEcRzHccHtPJjmVkQqpZhZjPHEqJpL58fBUIawiN7Dvh9UtWmbNjQGxsj3FXKCgGKKCkZnjJzshkFUb+8fMfOJwT0PKqeYmYd+oEjEZKCEtQWTlgchkJTlYsJqZovmokVCm3i5D4RkVsyAkJBBs0g/MCQMDADS9QCIhGCAgQlxq0nbu1vHS+C21I7AcLckXx3kCEAIqgZokYJkRUAOLCZDGZS0rgYCMSENlkWFgc68sUCEqlqWvmwwMLVSpDZNiioCjkZNk0LO5Wjex8hbm+PV7s26oesHNQMDRJx0be1ALaUcTudFpE1xPEr7h4UIRTQXAQAzKEUOZ7PpvGPiUqQkAbAYQn36w0NU7SSP3hO+MHMb7B+55nYcx3FccDv3pTWJamXQ7ORd+CEPClpdymZ2PHn6LnWKipioaZf7wCHGCGA5FzCjtbmJfemZmIkRMEuucxBrUPRKVddMOjVrOCCeLRZ3tzY3J+Pb+4dv3Lozapvtzcnp2T2XZxhynYjJzAQYKSponb9zd+I9Yh2yU2MHEwci0jyENlGMJ1YvZopAgAhMqKq5EEIt4CKjFjFa3EYo0zk3hmcFVJ+Yl85IdeJ9HQ5fvSKqGkIIgQdZ+MtrN2eRAoDMjMu57qdHFI2a1DZp/3A2nXWq1jYppXA067ohm5mpjdrmaLqwdIsoEa1CAFXtaDqPMWyMWwA4OJzNu2EyburSZWPSdv2gYjX6JsXADR0czbt+qJ+3XMq4bTYnYxE9nM6GoVzd3Rq37SP5POPjbL+MIVzZ2QRwze04juO44HbuB7WFMEJctA/W35cipQgsp5KfP/x8MW5wZQnIktvYMjIz931PtJhoqKpFRFQjW6BQRKoVpM4+rGYMBAzEgUJtbTzxokMZFDRxWji5mY+ms6NZV0rZnIxj4BDCfXXLmdkwZDPgGsQdwzBkU0AiPqX1iaio1gpv3bfS9dw0ePwVmbioiCkaIBNR0iGbqOSMREgEwZAQidCAmgRVjN9LJiJiDfhbxjWaqMJyMKeaFi1mSMxoWFRUVUVheVJOBpObGdnWVptSKEUQcdQmYur7IWdBxKaJIVDJMuSiajGGdhQAbXtzTExmNh61MVDbJgCIkVVBzUZtChyaNqTEOWsMYXtjklJoUmya1PUZzJgJoBm1Te0QjZH7IccYHonl2sxqxb62/CIuci0fOJXyTM09HjXTebduanIcx3EcF9zOPTTKdN6lGELgoQwGVgeXVJ8BAVXDSZ2d0pfBTFNI1eKsplVnr2bNEKKoQk30QIwxDkNpGiQiMSFCsLszVtSUgJi4lJJlkdlnapHCaYVUtNSnCEqd5zJqUmROIewfTW/tHexubay855d538NQzKoy45VMjxFUNQ8ZQqB4THOriqryYsdQS0FmOiUTAwVlHSSrKSMrAqX6VWJACiFmRTNFAEOgFMvBkTWJ2+aee7y+AqkW7eqEQcTIsd43qGsYJq6e7yxZVE873KtPPaUQAptB1f8AkGKragB1OWCjJg3TWVZJ41S96+NRqmuDjUmzOtLjUWNqSNg0ISUAhBDqUoLquihy2NnkPBaRAgZMHGMgooOj2XTeTUZtE+Mj+jivzpjBIvFGCJGIGPlRFb9HbbO1Md47PDqRXu84juM4Lridczmad5sbIzRQMDBTkzqvBBkBDBEJFwnSZiqmAFAFJSGBHStF13L1asvMTCSqhmirud8EAAZEWJ3QiMjIaiqmhKhmBaDaOWowiKogUk30qy9RxSUAqOqobY66bjbv949mADAZj+5qLrNly6PVn5cpFjXIgpjDelEfAEJgVSTCUkREwppThZAYF0eDECUPAgqg0Y7lDNbWSSbOkosKGISYGLkvPQIFCkwsJlSDvVUoRbxccXe9Sk1IRYqqhsAAdKKltdpRRKWq9HpaAYAAl4EtuKz+2noK9iI/G8DAAnLgKCGYrRIVgZci+/hbrh+V479GsHrKDLRoNaADWcnCRER0OJ3d3j9sUtgcjx5VokiN2SFCA8iaRcTAAEhEjSzyo5H1gXl7c6Kqe95A6TiO47jgdi6JiEzn8zEmJgbEdQOJmDacCKkvfXV6gFleqG0EgDocp4q8qslq0+Rq4zGGIed+EFEhJlpkocB6S+JiKo0ZAIppoLAwsoDV/ArVEjkF4qKl1EQLBFU1gxCoVp1FtBTp+75W6IkQAFepzKsZ9QuvNgHzed2EC4ZhqA9eiVEDUBNGHuZzKcVCtYOc9NsgUkASVQBhYsbARIEDAiERARAQAmYtpWQTeZCp5mbIWEo5sSo49kaQEkcxLVKqs0LA6rFCpFoOL6hgKoArLV4Pu5lhFeKLexUIxx9zWQW8zFep/60OeFHdPzw6PJpN2mZrYxzv/+3XhdPqvKzf1kBEQ1vcMKlpLWaIgPiIk7l3tzfNGygdx3EcF9zO5clZzZZjzIkAoKrnWqw1NTPrSm9qRGQGTUiIVGQhfxdyx6AOfVxXZQqqIEBGiGYGAjFGAzUzMRGRKsUCx4hoZoNkMWXjOg1FVOrGCbFGYtdWy7qrzEhE1dmytTGejNu1kYWICGa00mTr+uyeB4SImMMwZA5iaLUybWAAgZG6bqYMxEHNipRlNssJUagEmDhWt0at2eNyhVMWtxEIAt+XFlxM3kEgQuKLnltvHZCRmZHh8vaF1XK1muKaH321ZFDT+k6zDKJFtNRR8FD/D+nyaTMnCv9qgGBNanJf5vMuBooBhzzknBERCWOo7bb3Vts5lxpkWRcPqwJ59bLXPERbnmyzRZPqo/3K1NASAzhwze04juO44HYuAyEioCmaoS0jKcy0mjd66avMiiHW/Omall1LjXcHLiIqmJhkLVXbIYCCGVg1SVdrR8mFmYEgS1mGd0CV0dUaXrQEYka2KknNEDFLXto5FvXsYcgpxZqvAgDTeTceteFB0+WsplavybIQAoD1eQAyCFADuhMHQmomk9x3OhSLAfnsgT6LtcFy2vxKkYtK1iImYGA5Vx16Gaonp+alAIABhEjE9+62jBwAYJBctACY2N1iP9w129QoGlAzMgNEUysmilUr22KCptkDOKGXbiIDg+lsPvSlSSE1sX6A6tmvETfDMADgcvZnnZ+0aMfV5Tilxd4b9L0yU9MkAALAIqVoqSsDwprqYmbGxJEjPo6gwBiubm+Ca27HcRzHBbdzGeZ9v7M1YWbEAGBiIqpVJfdlgFVhGEGXLugmNlqbI9c6+dhITFUXoctLYbfIizAEJmYgM5OsRoaECBCWmnXV/7eoYVc7OC6kfZZMSIFCDZAOIaz8HgDQ9YOI3ltYm53OjitdJ8MQmpZThLUp9yGEXIqIFBQDSyHVZ4amQaKchwKWpSic0ehpZguNiCcVMFFNPYfaXXrJufdVsTJFABOVQGEYcgGphf8LV1NULUBrKyWs56d6RQCRAA1MTcxUDQmIiNTMiiAbYkAgNVmfbH8pEOukdwDr+9LNBzSLgUNkDrR892C4CFQxBV6MXqLlR8gAIEsxESQ0MzEL1RVkDIY5l74fEAGZgOq7WcwtAsRAIZ51/8E1t+M4juOC23mzyUVu7x9d390OgQGAjGptG5FUhYjElKzapmtMs2YptKwur6tJBloWvFe/XfQvRgq1lmkKAcOQBwTQ6rg1CMTrNWwAMNM6V6WWNqt1RFVNISwDOtYF7uF0FiNfkMldigAYLkqod58rw6BFLKqK4NpmEbFJad51JUuMwRYmZAMAy4XUmpiQCe/H3ExIkYKxDdMpGFCT8HJuB0IEQ9FiAGpKpqZWGyEveJao1LpvPXMIaPWE1OIyLjomcfkShqRmZlJPBKdYRTbCZRcGK9QUDBGBFDRLnvdg2DRVAONylvuikE1I1a1EdDLeUU0VFSnUJcdCpyNEYsagKvVTKSqShZgAwbDOTA3prEmlj1xzj9s0nc1F1a8kjuM4jgtu5yKm8+7qztZKFK4XBWU5JPxuCCDVuMDakXZM0ZzQN2JqZgjQcA2Sw1yKmrShjRaLZEVFNAFgOuYPLouQDYDlcMf6+2HIIbAilTIQYaSF69cAjmbzLIWJYowEsDkZr88vPDiaTmcdABDRztZGk+IqALvMutJ1nJKKUAgQq5sFGYmZ27YppWSRhRl63nOMgMgpUThXz0VOsPTSnKG5MeQuKyO0CRCq/ebEpqoituVfmRkhVZtKjYhRMlgLYzlP9ZbaQbiMF7GFcsaFq2Rx9Gxx9gAB1AAUjACsiKJB4OVMe7BzQtlPU11JWhSKWCkBMaWY2ohLf1Gtr9ckE0AgRKXFEqJogZqxaFqbdOt9DjQERDUVk4BMjEQBAMxAVXLOuRRDCIFTiPes/T8qxm27ORk8tMRxHMdxwe3cAzO7eWf/qas7JyrERFSkrFdhESlyqDPA8V5VT0IEpLodUcm5iBYzEJUQgpmhaQhMpwbN1LBqAFCzyJGQRZdpG6agIioBw3qFXVRn8x4AmHpEnPU9E6cYtjbGh9P5wdE0F1k4wkth5jYPTYppYyO0jYogIcWouUhRIEREAYgcAwcmppxzzqqFY6QYsCafnK/nLu7SY6K0uVnyQIB1bDsjq0mV41XR2sKWAgCAhgaWQowc6lBJAGgazDlfEFQCAHW0Z9aCBlSDVlSXaYwL03ytcy/aJc0EkBAJUE2BkInvOqkXjpzLfaJy0ZyNiAIDQCTjFOt9iUUPJgDUonvNMkFCBCIUk1xy4KBmWXKWjFi180LqIyCYFRM2XeauADMbQDGVXIDO+EQ9xmtl4J2tTTU3ljiO4zguuJ17MZ13p2d5UB0bAqCmiRMSAiAh5pIB7z1JG5EWAR2IACBWqqorWgKHOtwRawbd6fksVhsumRf6KXTDsLKDEGIgJjxzBKYCQJkLADBT1w/9kFejAc2sG7LZMJdyvW005zzvarmaYyyzuRSDhgGpqrvIEURgyCaCTcNNui8lp6Z1vvp6wTWrWCSbC4XIIYhprfnWx+My7K7eUSCkQExEKy1e/8vMpYiZXbjgIURKHKu2DhRqVqCoiInVfllcRgEiRWY1LSJisloyGZKagN3f5HQDUAMRBVEw4xh5WSlfOVtw0QC66I5kYgDIkuv+FMlFi9Xs9uMfKjQTlSKZeO10oDETWlTRUkpK6U377qQYrmxvAtjB0cyvJI7jOI4LbuciDo5mV7Y3TwwiwYVOrWF+Qkj1Pv499JYZETGFlVeEiVlZ1ywQRBRjLCUD4IlgbKaaeWfV32JmUpSAOAZAy1ICR8Z7RziL6HTend63NsVcCJs2pACIFAPFAABh1GIp/eEMmtiMRkyMta+RKDEb3sPCcUr6S9FSZ9A0iHWHs+R6f0BKibX2L8rECbnoYugmV80NZgCh5myck4VSe1jPm2mfJSMCIosKAgViJg5mQlp1LZjVVZbWzBkIgQIYLBIbawMsISAQEcGly8ZmWgSQiKkMucabnBiXs3SwVEeLqSko0LKELyZqBoCMJ1dVy/sqqKaD5MCBkcRUzQIHYhIpOZecS9OkC8r/j1xzT0btrOtL8anvjuM4jgtu5wLBPZ1tbYzXBbcBqFmdglI0VwOAqF7s5RUVosVgxdUvCSmF1Je+yvesJVFkJoAgoiKldsstg7drgDUAQM51LA7EwERc518+zLBuMyuq25uTtk370xkAboZFUgqnRCGAgZSMRSnFWo7VnEPbDheq2xNHQNZioVeaUZfVZSgCTAVUShYTxBiI6jRENTPTKtMN7ILs8BC4FBPR8x6zclYoyGpaJyIGZEIcShYrtvRwIy7GwBMRKSEhJgREYywq99UbWmMRAYACA6j1A0rRjEiIzHB8cCYgUDVngxUVWGah0CIE5+z3ZWCqJpBFJRDXRy5abykiUiml6/oYtWnepFL3qG02J6O9gyPzoe+O4ziOC27nXJkocjidEU2qxmHmattARKNQA+m0qu21ie4nqE5rMxgkNzVQedkTWU0RBlYHxVfVXn29qigipZQTeX81mYSZaTGoEQAwYFiXdosQjfsh5zLv+iGXedcDwmzexRh2NicpRiSK41EoUUW0ZArRRCUXpMwpiijRMc09yABwbHZm3SsRERVCYqLV31oNJq/W9lhnatpiIqNpDY2ux3AogwEkiuuLlpO6k2hZwT37XKyeS0iGJ+fDB2Y1qecrcgwU6gPUNBAzBennCkohEtr9JllbHU8TRiGGkgsAmIgVw6BIhGunGBeu7MWnosaNn6O017a/+BASIIhpQK7mpXrwYwzMNAy5lEKElxmp8wgumsw7Gxsi5mZux3EcxwW3cxEHR7PNySiGICJVey1qybhQaUpaZfeZekjXzAOiMpTBwBgDL6unTCwqgMc0Yp2mXt0RdUg7M1UhLlJ/vsjMgKcCopsUA7Oq9rnoOXlts65f/VyKYIdgtru9GUPIUhQkBs6zOXLmECiwlhKbNIiIHBPcZlZUCJnWdpBWzmlQRq4xiwCgujRdM2FZjJ6pLu1qqyAkUSXkJjSwVqK+QHNf6rwiBubTDw5cBftdQ3zRYmZMgRAtBEQAokRU3yZc0lFjVhttEYCYOUZEpMBgplnUCoWAzLi8l2JgurxngvfqDah+9OV4JgNAJmY6OYGIiJom5ZxLEUR8c7wl0c3cjuM4jgtu557U5sKaPTfIIKaRqtkWa9/eYiQknpc6bHV4YlWKRYWQaE0uBwpViwPUiIy7lfI12W11gneRIiIxBNHF6JYT8dsAsLO1kUvph7z6ze7W5mTcEqGpFVEzm3V91/f5whZDMzuczTfGI0DImhEgA2ggAC19J7MZIoZRW03nNRZj6X5hwjo15qQNvQlJlwM7YeEnKWoaOTCxYSj9YGrAJqpqykSMXEyoBoms9Vne2ju4dWefia9f2dmYjIjwvNN349be4WyOAE9d3d3enCx2Bgnh7qEehvzVb71KhM8/81TbJljzeKgpwSKf21QQiZDrPQQDK1JML3K53D2edWhkdfDXFHCKdQySqZmI5oKBa+TLIgQFDJdzTy9cPADhcsYmAkAdwHm2xz3GSCSliIjW0aSP+xuUYriyvVXXrn49cRzHcVxwO2dzZ//o2u42M9XOuaLZDJgoYapCqCZpnCezAIwp1KGGteBNx7rlUE3VFA1r9ffEloiICMysz72AKJqAopkaqipkAIO2aVa2k3HbBOYe7gruPuctGjfprougbdKtPVPt5W6F+QxE9Pb+YUw8GTUcWE2NsUZY06RFJAhUZwOJSClCRDGG+gZFhYBMjdcKyUzMcMw7gYiJY+BIiJACFAUiRag9gipaoFSzBCHT8rbArTsHn/+tl/qcq6R+Fq8OQwaArc1J1w+lFBGNMWxMRiJ65+Do5u396WweA6cYjmbzGMLGZJRzPpzOYgiT8WjvcDqddbvbW4H5xKkMxzpiF4kpS2lbo2OA7pUNWB+GS0c+BjbV2m+KzMhghMZqojLvkZlSQKpzJ+HeOd+2CDapr8PEdH77bJ2AA4CllL7vQwirUvcw5GEY6uKBiJgphHBaka9/YC6p111zO47jOC64nXsw7bpd3QzLqS6iiogGICpMLHZhFJ2BATBxlrwUcMdq0kXFzCJHMaXzR5NUDUTVe7wsg+NyZHrOuT6gPnh3a6OIrIrcs3lXtjYaiOsCCBEWs9YvZNb1NNAwFCKajFOIXPUiVVMEMwCEUE3nambDMCiooZUsRsYUVPMJG/r6m4oc17sPQ5OG6YxSxBiKFDVjDqJSYzqyYp2+Oe/6V2/cCjE8/8z1zY3xN155fW//cDrr3vmOp45m81t7B4T/f/b+o8myLMvSxDY555JHlZkac3MazCOiKrMAqerq6ikERKSlBQKgRxCgBXP8Aoxq1j+h/0dCunsECAQ9qGx0SVUniczIIB5OjKope/zee87eG4Nz3zNVMzVzM2dJ4nwDFyOq+qg9X2fftddCM/v5jz+6f/vo3vEhE/32D8unJ+ePnp2uN40q3Lt9uGna5boZDipEbJqu60KMMhkPZuenf/7n/+Onn376L/7FnwLAtSL0K7PmGGOUmF4ENcXXJJaYmYUY22CIXPRPAjqWVQeiblD3f8KMzEZqJKYqmwaZqSiQ3kLRbmMFwdDSXq9KNCUkx+6mpx3S+kF6kxAiM5nBbosUDEAABbHrCu+v5glaMpWbpqPg2w/IC+/qqlyuNpo3KDOZTCbzevjf/tt/+53/0OfnF/mZ/UeClWUhKmqSFEsa4gqobCtpXvN9hkiEJCZpS9Kzv6bhAAiJmbeVJa/1DyAiE6lZiiVJ1SjJpCCqyeKSBJD3rnDOoDeQJJ1UFv6q6iWiuiyjyNdWcJtZjBJCjFEGVVUVZbJ2cErCTjYSepFjGCWqmnfecz89DSFePQ+89KCupeMRaRuIyfliF8+SLiCk2W1aBEx1M6JyOVt452aL5dPnF6cXl977y9nCDO4eHZ6cnVdlcfvWQV0WTdc9O7u4mC/M4N7x0XrTLNfN2cXs+dkFEz1+dnZ6ftmFcD6b701Gf/Ef/8Of/dmfPXjw4Kc//elL91bSGYYwSOxiAADvnGPfH6yuLDaaiDStiWoIJoqOkYl2A2NEi4II5Bxce/iIzP0g3EC7zkTI8ZsH6NupO26jEy1qFFNEvD6eh9RJqaJRREGT65uI0rkRCJxj3OWb912qeHXObQZmL66K7F4+2x7e8I3lR2p21eyUyWR+MI4PD/KTkPlHQZ5w/xFrbbP5ajMdj3zqxwbszbsI21zml1WymloSi2AEEDQiIBi8eo1+Z5MQ0yABBEpXvKTId19JSOgwWREMTFTS3QOC1Bb5wlhSV+x4NAhmdjFfrjaNmTnm1JOj2lf6iKi99cSx7eJy1RSuKLwzs1cj6voWHurFcVLYSZPFGM30RovCy//SBlVsWtOGy0LRokYDYyQzVJWI4ojPZ/MuhNGgPjm9+OrJiZmNBrWZSZQocrS/d+f44PHJ8xDC6dnl5Xx5MV9ITEF+wI7VTFQO9if70/G6aRer9d5kdPvoAACGdf3P/tkvp9PpT37ykxukLRESBo1m4J2nF7ZyE4OUV7N97VLvJvaSuj8p7SQycOGlaeOm4arE60cRJMKCTM0iglpcb5CIq/JtOi3TmzM1+KQe+BTzsmm75XrDjGXF6ZJMcn0zkXcFAhqZARgoGCD0pzcVizGuVr0PhJmc88yUlgp2L2Va7U1f8IbX1zu3Pxmb5QXKTCaTyWTBnbkJVT27nN062PeuN2YgEgK0sYPrCdzJ4+GdS2EgyQKR8v4UUpg07LYGr+vpVKb4NfPml5K8zcBIPUCwmNJCdoqn9L70/mK+TKo69d1sKxvN3v3KPiKs1o2oHu1NrzrCr38NvmRj2AZioEgMIaRw8TfcCjnHhWqIIlExCbv+qY2qam0kQgYRXTXt4d707q3D5WrTtN1oUA8GlZomH/ZkPBoMamJerDeX8+Wtw/396fhyvnx6cs5Ed48PVW2+XI2Hg1/+5KP0FB0d7E3Hw/t3jm5U26ZqIojOkQPAq2X1TIyKXTLU928DRUR0pICmBiJI1/YYiRmKwlS1aZGZXsnGRkIsPJhBBwYQ1w0icv0m2Z3iSvrGU4S0G7A9LHWzxWo4KHxRiQgh7a6omKmYCqTLCP2Cb9oKRULvPaU/7z3rCkDJgvLCzY5Jn3+9pbvwbljXuQ0nk8lkMllwZ25muW4QL4/297xjAHBb4YtXOlxg60v25IwsSCQAz15UFIygTzW50TSiZmD2ug7Fm7VpPx0nAEBPIQRVY7727aV3h/uTy/kyXcr/ZlK713MAorpaN474YG/s3yVXzjlGhBDi2xTlcFFI00YTKBwCIKCaqfXDY1U93BuX3qf1x8lgqKpNGwCgqoq27ZhoMh58+qMPCu8HVcl8786tg+GgHlTlfLFcN21VlqNh3XVhtW6qsqirct00bRuGwzpFlLz+MMDIRK8EgRMSErrU7GO606ESNKqyY3Z9fPvVgwgVHsy0CxojIJL3N7wvEKksYHsOi+sGAHhQ3fwmQUj3z6xPiI8WGTmKrjetmQIiAQHa1i6Szgea5L2qpZNh7xJBQwPn2LNX05SQI0HNrCzL6w8FX3rXvYG6LMaD+nKR23AymUwmkwV35jWam3B+uD9xzND7RhSNFBSREMkRJ1t1ipzz7ILGNPRN+oaIXmfRJsSUPM3G8O5Zbcwk0o+ur6qxNsSuC5PhYA7rb2uf3Sqk5WYzGtb+HYOcmdnMXi3Ked1Xg4m2nSGQY7viUEZE52g6GU6nQxBgZO9fTM13z8CgrtKfHEzHB9Nx+vVkNNybjL13ADCsq/3tnw8H1dfef+lCStG+8W/Tq5zaNMEAEZBR2tbUqHApy+WGo06S3Ygmaiz4mh++k939sWfTgAHXvRfFzLY2EiIis+0NJd0M1rTdummJiAmBwDTJbQNAAjADJkR0QcPuu9LLbdDbwcEszcsVrO3Cbj6NiKmH9Uq2CX/t0Ws6HolqNpZkMplMJgvuzE2C02yxXu9NRlvBbYxp2t33JhJRVCGDXS2OJ4dvURMI2zQMUUFAR+4t59yikpSQmQGiiSQf9e4LCu/mi1UUUVVmQsA3RwG+1Y2KXswWy9VmbzIsi3foCWfm1OPj/dcEV7uqtBgsdrLemPeuLgHJTKMoqKV1TUcuxMCersr3t4nE/qYvvxrSm1/B7fJiuhvkCo1R1ExU8XULhYjknWKULpAz8q//qEmyG0C7YGradKaKRIZgjoARAVQh2euTNkeiTdPNl2szq6uiror+QHLl3u7WavtC+xc3179rkw+q/x0BMznkK8827d4VXdd674qve0sUqQ3HYL7KmjuTyWQyWXBnXkHVzi7ntw72vGNC8lwA2NW5tUg0MkuhbNfrzaMKv7Eo0bPvYgcAbz/htu3oMaqUXBBTjGIWzYyZneNhXcEBnJ7Pouh3KETXTQvQRhHneDoeVm8nu1PHeArgc6m18fXqFRgJHVelAUgT0lYiMjnvEJGRobcr07u8fPqN5XjvJn9zzyVS4XyqoYkiEchAcFv9+dpTFyI6h6LwmoOQmqY9xn6W7RkBIAgoIpGpahcMDLw3dtsLLAYIIUrTBOd4MCgcEzOpKlNann1x46K6jb55+Q4YGKRNUOuTWJzrWz+vPzlApADWdaHrAm1xjm+8mlF4PxrWm7YLMeZPlUwmk8lkwZ15meV6AwC3Dqb+eqYbbGeBotEMDPtm8jSu7mInJkoOER3enLftyIEDRsa3VtxMHKMAoCfn2CGgQURDADQzEWHeau6LWdu92Or7TkiLmDHK0f5r1yhflqRESXMjYjJa3EiQIKoqJsk1EYWJdbOhuuC6NDMiJCTnylcd1W9U/KCqMYqZfq3/IYQQQvTeJwsKXjks2ZaX4g4dcZpum5k2DYRYFaUrPDJHCSmoZLsday9JbgCw10Q0phtiZCRUlahipuAYkVNKJCEQIBlKGyICeodMBEhMTOIdT8YDUYkxoqF3HtCCxrQBYGYKqRSUAF9pqrcX54Q+n0eFNb4UOIgIzERUMJOIpl3MGGOMwXvv/Q3vjaosxsP6Yr4EsBClbUNR+D4AJ5PJZDJZcGcy1zQ3AGzjSnaVk2l+qKqKKagbo0YAU+mYHL9+xewlHfMWChJTFQkRBYkIaKBpmxIN0zwUEYZ1FZarmUin9p0LmnXTnl7MBnU1GtTefb38ZWZmEREifJ2ZW81SkF/BhQFgZd55bNvkfgCEaOIQfKqofGu89yKaAmREFADT0DdG2Q2/d3nSMUpqXvTeqcirQXjpMsLVR0BX/BWm6tkVVUnMSVCnObeaqYpdD7dJr2WySb+UEmiQzB4aNabEm2TvUFNCh2hRAL0DgOQV0i5ADOgdsSsK74YDAHPk0jWBKGKoaqaqKf8FEalv7bGrdffb2zYFI3vRHK8qonLjGzVVx3vfH0hCiF0I1oW2S8VMnLaG078aBCyLYjIcrNv2cr5cLjd3jg+9c1FkV8sKtosDz2QymUwW3JmsucGiRES82lxjaRSqcafG1FRUOusK5+ldvBCvI6TYCLDUOU/GQABoCsbAYAjQO8qHdUVMym62XKdS9O+KlDnYdmHTtGXhx8NB4d3XCt+27USkL+8UEUkmE4xRkqRT0bIoy6JIHmMiqqaTtmtNhZzrExffcb009cwn6Zz0dBLfSdKl5UvbiksidI5jjIvFCkw1RvbeqRKl01Rqdbz5gCEiZsaFR+5ra3Z5jqKiKGCv5EJ61zXdar6OW305qMvkugZIlywUkBxxFGtCePr8oi7KO7cOCKFX/WTeF1CIqXWbzfPnzwP5O0eHk9EgHRLAkIiW6yZKrMrCMV57xyKeXyxW62Y0rJu2844P9seImIrrU1AMAjIRI3/9ORDg8fOzi8vFJx/cDyE8enoqqmomIv/sp58Q0e++eLhYrh/cO35+dvG7zx91XYgiH75393K+mC9WP/rovdl8dXY5Pz7ae9f13Ewmk8lkwZ35p6m5PftkhAUEVdvqGDDTbUBxXwejplGjNwffhaMasfdFdF2YzVcxCDJOx8P1polBD6bjrsPFuhnU5Wa9qQjH43q+Wl/OlnBlh288GjDRcr2pysI5Xq2bECMCFIWvq3KzabsQkggsvBPVQV0VhVssN4hQFj7E2LZxUJdqtto0p+czZhoO6oPpuOm60vuqLJbrTeFd8cJagGbatnHn9zWDGOM27IILZvDm2G13IFFMwDM0AsqOPKU+xnc3ZG+LeCTGKCLJWHJldN33liOSc+wcxxC6xQodu6JQS+4OFpHkS4lRiKgoiqv2GImiIiZidoN3SE1TM+hLf4WIIcSHT56fXM4BwDF9cP/OvduHXQypUCZGdWRMbKZNExaLTeviatV47z56cFfNQgjsmZzrQlTgppV1CAeTSQgxiBD0T9mXj541Tffjj94D31u9C+9FJER5+vz8crY6Ptrvuu5ofxqCiigl8w9C10VmQqA2hg4jInnvCLELwcyKwl+d9qvp84vLpyfnH71/F5HOZ4suBCY6ObsYDeqqLP72t18wk6ienl++d+dW4f3J2cXnD58w8x++ejIcVEx0fjHbn44ZUVXZue9rHTaTyWQyWXBn/oFrbiY63Js4x4XzZkZIhgaIoqKg0Dt6gQijqSefdu++5Xg7SEBEJnbEyVOxCpu/+e0XYIAEhffOsagOBzUh/uo3nz24e/v3Xz6aVOWf/PInZxfzs4sZEc0WK+9d4d2gLlfrzRePnh0f7t0+2j+/nK3WDSFt2vbe8eFq0zRtR0QAOB0Pv3ry7HB/+uH9u8+en1dVcefo4PnZ5eNnZx+/f+/W4d4fvnqy3jSMNBrWHz2465g2zpWFb7uOmZmorkomNLN0LBFVNXXkkBCROFXVX9dVGmOU2K1WKhLXm3pvmvI1xNRUmfjqk6mqZnb1h5jZzgECYIgkIgDAzM455j7kJH2Zman2ZfX93p8a1RUXnopis2kQwTk2MyI1I1WLUVTbsiyS1Tt0oV2tEMlXJV/3LifHESExssENdm1f+KP9ycV8uVhv7t05UtW/+e3ns8VqNKhGw0HThtV6E6Omez1bLEWsaVsmWizXIcb5cj0dDW8d7q3WzfOzi7YLo0H18MnJr3+/2TTtdDz88N7t4aC6PJ+vmrb0/vn5JSJ6x0f7e5tNczFfLlbr4aC+nC26rotRfvOHr7xzpfd1VXYxXMwWw0E1GQ5DkOV6s2m6o8O90aB++vxMRe8cH/74oweOd/mMatt13p1Lpyx9iPHLx89Gg3qxWh3u711czpnon//0E0QIITx88vxwf4oIJ2eXOxfL53/47P/353/+yY9//C//k3+dP3MymUwmC+7MHyOL1RoRp5NB4X26NN9JMFUzQ0sF3ygmHh1TuvSPau9QsxdVVAWR0sKf9dJNMPXdpCpvMzM4u5h9cP/OdDT46998PqirwnGM0SGenl/uT0ZnF7OHTTuejtME+sHd47/49e+J8GA6ds49/upJCOHZ6cVkNGzaTk0P9ibdWbiYLdZN65iHA59CJ5q2/eyLR4Oqmi2WiKM2hNPzy/VmczGbT0aD52cXKnr71sGgrtoQZrPVX/zP//Hjjz9+8P4HAAEAoohn8s47x4BmyaiLgIQpPePlh9+23WyhDg0BmGhQmePUWC4aAfDqlQIRabtOVb336ZLCdq+xv+TQdR2AMpNzfHWwDX2k9A1OCTOVpk0R4Gxmam3TGgARARgRMFPXxRiCSgxdiOsNIJajoasq5msPR1TEtG9s3LZR9nfSwFQd4+GoPqlLMbt3fHR2Mf/i4TNmOr+cD+uaiIrCNV3XzLv37twS0S7EwntmerKVvCdnFxfzJSKIaFUW89Xm7HLhvTvan56eXxbO/fSjB8xsAGcXs7OL+Xt3b51fzh89PZ2MhkcHUzVVs7btLmbLddM5x8Pan88WzclZF4J37mK2rIp5WXoGiCE+enJyuD89v5zPl+sg8v69225QwXaKD73nW0MUSeGVYKNhHaKczxaH+1PnKM31owohRpF05Do62DuYjv/us6/GowEALJfL58+effDhh/nTJpPJZLLgzvyRomaL1bquPREikqqI9VIDt80jBXtHjsCCRM9OVACB+bVpJMmZTYiOXNSoqoRqfTBb/5OT/t4KOFBRU7u4nHdtSwBupzFT6DJx4d2grj776kmM8c6tw1sHe8OqnE5G79+7PV+uN5vmYG9ycnaxaVsA2DTdxWyx3jT13jSFi7ddJMLREOqqZOYnJ6fz5Wp/Oj67mCHSneOji9nicG/64O7xxWwxWywRcTio/v3/9D/9f/7f/6///f/h/3j3/oO0JrjaNI5ob+LIkagQYQrMY+Lkjb6udkFDJO98WWDhASFqkm6WYkwKd62YM0aJEhUVFR05IjTDVM6ydZLEGCMihGAxyivbeKZqRFQUPolvDcFEkdlUNQIzi4qq9SefZHZhJrMYzcysCyjih4OiKl99OEzcz7URHKCCikRtOwmRHGPKQXGMTABAiF0bvHN3jg+athPRIPH20f5y3czmyzvHh6t108XonSeEtgvIeO/46Pxyvt40w0F1fLg/qMvPvnrShjAZD+/ePrpcLJsukHPELkWFTyejj9+/F6M8fX6+Nx3fvnUQRS7nS8DCwER0WFdF6YNo0wXHdO/OrS6ELkRTPZwOweDzJ6frpplORs6xiHQxeGHod0MVAZ+fXv67f/+ruipDjM6xARzt703Ho/WmKYvi7GJ2dLj39OTs3/2HXzkmUf3wvbtd1yFVHzy48/zicrVuwODBBx/87/6L/+LWreP8aZPJZDJZcGf+eEm1eUjoHafqcjUTU9quoyFiJx30kz8UVQU1sBTk9/JPMw0SAUwADIyTRwX6QD8mRKD+JjSmpDlGshDAFBF84T/9yQchyOcPn55fzhEQiYqiIKIfffje+eX8d58/PNibqAqAeefGw/qzrx6radcFJrq4nLdtKL1HgPWmee/OcRTpQigLz8xmoGrv3TmeL1eL1brtwvPzS1XzzjVtd3pxWRXlaDi4uJyfnF1Mx8Pbd+7+r/7X/5v3HryvfaW8iUJEbbvgPCNB6kd0xHx9A9JETVW6gETFZLzrdyTidBqJqY0FUVVFJNWSR4nkkMk7cp7dq76dq2mAfXAIJM89pIeGiCISAhKRtK2EaIh+OCBO9Z9IKma9cSXEIKKtaBvCw5PzqvTv375VjQbkHNINgesI6JA1hNi0gMhloUEsCjoGJiJGIiT2VcWrFpFu39qfr9bnl/PxaDioqtlyxcyOyTtOC53OO8f87PR8NKhV9Ve//QMi3js+XG8a54gIC+8GB3ttCL/+3efeueOjfTMrClcU3nuHaQPA8fHRQVUWv/nDV5umHdQlEQ0H9XQ8XDfN+eWcGY8OpmZ2djkbDweT0WC+XDnv0nd3IXbrjapVZZH2ExDSFQu8d/tIREW1LsthXfvCOWbPbjSsuhjB8GBvsj8d3zrYe3Z6bmYHe5PDvcnlYhFVDvbHf/LpJ6fn80FVDupyf/8gf85kMplMFtyZP3Y2m248rI3J+kFm3/64S4JLSg6xzwcUs5feUsk6kpS0Y5fillXVsUtKvQ9KA2JiIjaJZsBEhExI3hej4eDDB3fv3j4sCtc0Yb5cf/7oGQK+d+94OhkOBtV0PLx7fDhfrhyzc25Q19679aZdb5oP7t/en47bLjx8ctK03e2j/dtHB6LatF2IMUZp2tQNTo55NKz3p+Plar1ab0zt1sF0PBykzciui6kG8mBvUpbFT372M6Kf95aXF6rXmrarqqJ0hUgHAEwv3B2xaZFQg6TYa/Luaps6IXn2UaOoMJJEVdBkGhFVZCBiR+5qVaeqpVs8Pb+8mC8mo+G920dVWTw7vWjb7uhgKqpnF7PRYDAZDc4u5yIyHQ0vZovz8wszONifjkfD+eV8tlh55w73J8O6mq8357OFRBkPB23XXcyXZ5dzxzydjAfjw6s982ApLtIAIbYtApJjZE7HJ+8LY1JGAjSwdOffu3N8tLe3Nx4xk3NusVxXlXeOD7vxcFBPxvWtw73JePijD99zzIh462BvUJdmtlo3o0E9GtardVOW3jGPBoOi6F/i0aDan46R4P69o6Nu4ojNYDgoP35w94P7t5FwsVgDwnBQEVHXxYvZ4vLZMkSZjocfPbhTeDdfruuqrMriqB3X3rH3g+EAADZNCwCjQVUUDiHtCpsBHOyP96ajZH+6cgUDAcyXjICjUeXZTcfDe8eHKWMRwIbDSk0B4M7tg73JaLVumi7kYMBMJpP5IwG/jyzYX/329/mZ/Sfy/gAYj+rxuCai0hUAECSmdUZRdcxMHGKIKtjnCmPlyxexzSpb6wgJaOnKLnZqykiIZKYGye1szK5gnxIG1RSRGAkAmk3z+PGz8f5oNB4wMSHPZquL2QIAjg6mVVk8P7/cn4wHg+rZ83NAPNwbn13MvePC+4v5cjgqR4M6ipycXmyarq78ZDQ6O58vV02UKNrL/bIouhDGo0FVFOezRV0WdVWmDLi27ZKdPUZR08loWJXF62IlHPNkWE/Ho5Qvx8iIaCKm2s4X7D0VBTnu58Q3BX2k6TIhOXbJMdLGXrunJ0REYowAKCGC6u8fPX12PktLmT/9+MHeZPQf/vo3z88v/8UvflxX1Z//x18N6+pPfvbJZ18+RsKfvH//6en54+fn57P5e3ePU4CGY+5CHA3qw/3J6fksqcw7tw7OLmbz5XpvMgLED+7dvnf7wDnHzKoqUcJ6TYjsPRGpCBJxWeyKb5AoaowqKZbPETPd6CM3Mdl9Am3dQvT2mR0xRhF1jhU0aAQzQkoLALsizCSF1QwRTOHZ6cWz5xdmtjcd3b9zVPhUqwRxtY5NS4OKC09bWxQCKJiapK1QNRVTRkaEKJIWfLHP9QYDTTdIRJ79q5HeZqagZtaFsFpvVqu2i5I/ZDKZb8MvfvxJfhIy/yjIE+7MmzCA1bodjwYF+xRs7FOkHSCTpl84doiU/Aj6UkgFQlopExMmR4CeXReDmIIpAnju8y62eYNASDu9biqF4w/eu6NMSJj06+H+5HB/sruFB3d7C+zd48OXfjEZD6PGFLF89/YBIolGBCr8QYwChojomAFATMFgtly1XdibjIZ15b1bbZoQovfuYG/ylk+XqCYX73BQ77zOGqWdz5Mk5aJ4Q4l6mnObBiZ2joNENYkqqGCmAWDna9fQgSoSz+bL07PLo4Pp3nhYFv7p8/P1plks10+end09Pgxd+MPz88mguric11UlKkeHe/Wwnv316uxirmqjYf2jD+/PFqvff/FosVqndJpbB9O6Kjdt27QdMzMTM/32t7//q7/6y08//fSXv/xl35VDiI6JmAoPu5jD7aNjZGQEA0J63fkEER2+1UdQiFFEvXO7fU1RjVFiiMzEzCpmfT0TKmjaC9jergGAgakaKB7tT4/2p2rqnUuvUX+5JkaTyI6RMJUQQR8535cqIRgCMhIipDfV7sxk1gt6REzLCLpdbL2mtrVPZix8ATXEqDGZhjKZTCaTBXfmjxxRZXwxodyp4au/ICY1NewtyDsY2bNPU0/X17+7SBIlAhgivxR+9xKx6cJyVUzGDIiv6Y3/mvc3udRLn26dkYJE51PQMqX8kN2P9d6FEGfL1WrTwOYbnU/Muiir9RrAiBABvXey2QBiMRpyWX7tT6DkXEEMIbRdJ6YqAjE6ZFAjJlcUDOa8J+eQ6f37d4B4td6cX873JuMvHj1tmvZgMrqczYvC1XWpZk9OLy5ni48e3AWi0XAwGg2Hg3q9ac3scG9y//atyWjw5aOnRPTB/TuL1epyvqyrMkZFSr3vaGa/+tWv/uzP/p9E/POf/9xEEBGdR3bI9DoxzcDvFMouqs/PLh8+eR5ivHWwd+/20aDun7EnJ+fz5eqD+3fGw9rMROTp84vTi9nR/vT20f5W6KOYQt/rri9NygmwE3n4+BQAPvng7qvNPlR4jWJRXgo9REQCBjCDfnz+0vsfem837DLIDSxqTFdy0gFSNdnj7cU7RW1QVYg0X67zh0wmk8lkwZ3JAABczpchxr3J+HUl54TUK47rsvjVC+sF++SOwNfPPvufyUzemcj64sLUivHI1zU5hrdQ3kECAiJSkMjEbmsSiCrJSSUmDllNkwedkAZ1iXW1btq2++aNlWrWdsEV5J1zyN1qrSGUo9HbqO0k2UVEJKqoNI1RehJ84T0ZIhExmRkxI3MIcb7aEGFZFo+ePlfVZFGo6+r5+SUyi+r9e0ddiF89PQmigPjFo2dN286Xq8loqKJPn5/VdTlbrEKUwqOoDuv66cm59y5Ega3Ng5l+8YufDwbVj370Y1UJXUAAl1oewVL+t3PudYX2byDG9L0MAM9OL37z2VdRxDs+u5zbtqrz+Ojg/HL+9PlZjFJX5fHhnqp+8ejJ5Xw1Gtabtvvy8bNN245HA0O7uFwQ4uHBVETni9WgrqbjIRM9O7tYb5onz86GdX18uPfs9MLMjg/3ppNRGoEjE3n3qp8lja3TkPx1XO1hvaKoRUEJkZAQCBGJKDmvRMTUPDOURdt23Q3BMplMJpPJgjvzR8bFfLlp2ihiAAfTsePXNmB/bfFNCjlJ24Squi1ovxkuPBdTFXFlpSqAsD49c3VVjkfI/PXK1QQR1YSBdjfk2QcJaX1NTBkprYECIBut19237IcnwrIqfOEIAbtgQXxdK4KI8Ovvc4wxxfkppBIZRDR0iI7IpdyO4tXnFhGdoy5EM3vv7jGYjSfF4d6krkp2vFxviOhgbzIe1ptNO6hL55yqnp7PxsPBRw/uMvHDpydfPnqmZu/fu12VxfnlvOnC8dH+veOj2WJ5MVuGGJOX/Re//MUvf/kLjRJjNFNRky6wiPOsairadcF7772nd/Bgg0jsuliWnogfPj5ZLFe/+MlH09Gwi/H8cnF2OVss17PFKoqsN+18uT45vTg5vWCm+Wpdlu75+eXJ2cViua6rUtS8d4vFerZcz1cbVX367Ozj9++VhT+7mD988nw0rFeb1gy+ePjs/HJORE3T/bgsqtIDJCO2ahRy8uq769d/8+s//3f/46c///Rf/6f/yQ1vNrAkuNP7avvq9G7yqOIYPBdX/yq1kDrHNhpeLpbZzJ3JZDJZcGf+2Fms+qve8+VaVQvvzXQyGr1u2v1mgRWhH+chADMzvja3O02yybnqYA9SmnRUadrgnB/U+MZ5qmMXJJgZQup9DCn/Ow0q0wLc7lZU1RG1bZwtViHEb/l0+YKZmQ2kbX1RFnUVREIIXRe2VwBM1ZI9OqVfA4CYiAoSOgVQAzAqvfNFWjC98Slyjj96cG9/Omm7MBxUKspMk/HQOzceDmaLZVSZjOthXf/Jzz9h4kFVvn/v9mQ0YOa9yYiZp+PhYrVmpslkUPri6GC6Wm8K76fjUdN2y3X/uk/HIwRQ0dg0AFgURZAoaIoqhkDAxGgYQlDVsiy+dtRtZqmFPoSIiCIqYl3oiGg0qMfjYduGR09PF8t1F8JsuUpFmHduHTw/u3z09ASJAK0qitW6adpw+2j/Rx++l8Ic10232bTpaSai46P9wruzyxkRPrh3vFhtlqv1ydll23bOsaouV+uynCAgMYOodA2XxavP9R/+8Pl/99/+94h4s+DenpQg2b4hJV6qwYta0JdOZbS98kNEIjpbrqJq/qjJZDKZLLgzGVDV+XJNRGbWBanLgpmiKCKMBrVjXqw2dVXcOAJPg2QxFRXPLqoQIMM7SHYkqvan3WIZVmt2jqs3mTQICQAVxADI1AwUMTUFpn0/AFQVQzVTBDCD9aYJ33rQqGrrTcdMZVkDt0gIiN77GGW7M9dXrJuZiIbQpQhEQ0VTbFUQAYHYEZEjftWTc5WqLO7cuiHLeW8y2puMRLWLrZge7E0K5wnJOd4ZowHgYG88nQxSoohCHI3KvckwJTYO6vJgb/zyo4sR+91Add6lMw8jeVcw0molMcayLL7u0CXJhUKEReGdS5c77PbR4dnl4n/+9e8mw2GIcnJ23rQdE6Wg67brnj0/ny2W3nsiulwsYpDhsK6qYrnePHr6vO3i+eVstWlCF6qqYKZBXe7vjQCw9MVsvnp6crZebwrnEHGxWhfeVWWxu+yAjl1dx/VGu0ju5ef8009/9l/93/6vH3/y8ctSG8zM1BQA6cUKpRmk1B5LbhNRjRp3x7yrm8HOufFoICrz9WbbuJrJZDKZLLgzWXarAsBitd40LRNFVUToukiEq01Tbvzh3iRGCVEGdbkT36Ki265KM8PthXiEd1uF9IPazCR05N2bjSVMROajCoAhYGrtSSESSfgmqURIBqCmReG4If3Wg8amCWZWusIPhyayObvwdY2OvXN05ZpAiq3oOkAiRQ3zJYo5dn44wNInT/zXWnTeDBM5dibRvWY5NaoECaKSuj7NgOj1fiEmX9cAoCoQIQZRVmTSPqZDk3x8gy/fzEKIZkZEzHR1EM4M7929FUROTs+7LoxGg4/qu20X1KwoHBMN64qJ9qfjo4M9Jjo5v0SE/emImc8vFiHKeFiPh/W6aWOMdV0SEaERIjE9uHcLCVX1+Gh/bzquSj8aVkx8uD8eD+sXe5Clp/6peJmPPv7oo48/uuEQmCIIkWi3MWlmBmllFvuLNGDWLxWkTJKUG8jbV8R7NxzUbReaELOZO5PJZLLgzmSuyzWRKP1IeLZcJa3QdgGs/6vCHzjmpu02Taugg7pME18EJGQDhXcPHkHmYjSMTasxUlpIe51ARBITAtxJmKvLbQj9L5mYARCxdIUjdz5bfJulySS5miZczleHexPvnYSAhBojAEjbkmMzMFUuPKfiRAACBFFZNeXBflFVX+tQfxfNzYSEN6ltUemkUxVEJKDdGSQdQm7+aWUBAKRK7DB0RmhEKTgv5eKpatO0ZuacKwr/qtpWVeecu8mMVFflTz5678HdW6pWVyUCNG3X52dvrf5EVJUlAtw9PlTTsvBEdP/4lohUVWEGTduJioEqGG7HzocHk+GokqhE5B0z89HBRNXqqrh2TwwAEejd3pMvP1eYnu5r28OIoKbRJAl0FQUAI+eoLwcty2I0rGWxymbuTCaTyYI7k3mTytz9en7F8+2YZ8vVcrVBxK6LxIQIpS8QoSwLenfBnSQNFz5umti0fjh41QCQULNUJp8k0etuS00RMAnT8XCwWG2+peBOrNbNaDAohnW1NwUADREQNAU6g4X1RrqO6zpVsovGcjQCX/m6Tmo7qqS+FTPj68Ux6VrBmxMVr8nBmx53UtuWRv62zc9O3S6qxPSGFzquN4BYVBUQJU8FIcUYiZKyN9VU0IPuyksjIq+q7dSaTkjJOeOYx8PB7m+9f+0H1HBQvfgUq1/8wMK7IKGNXT+oTlE1CHVZYtkfugBgWFe7TUfYOkOSuQi+0XvyhWI3QKLXXLdJLz8SopkGCaKRkFPR6Xg4ULXZchUlm7kzmUwmC+5M5q2Zr9Zqum5a6V0om1RXvqYWEauyIKLCudGg5psUXm9BeTVzDQGJAVFDtNc7QFKPDLxw2b4qj1JBoCko2w2h0YRor2y8vSVqNl+uCs9lUQAAeQcA6WxgZl41tm1oWwTQSGDq2Lm9YVK6ahokmGm69RKvmd1FRdIQ+psrQ1BTNXPkDEBVtvYeULMoAcCu1shfe9KiqCp7nw4GlpoYQUKIzLQzcMcYRUTVmElEE8z00mzbzJbrzWbTErBjHg7quip3N7vetE9PzwdVmXzqqYU0uTJUbLncRJHRsF6vm7YLx0f7ZeHbLjx69lxBbh/vA4CZCoBGPTm9NIB7dw6Tvyi9qdTs9Gy2adqjw2lZOEBUU+uEvHuDteaNx041A37lIGRgaYchXd9JJyUDiyKAwsaO2Dk3Hg5EZLHeSDZzZzKZTBbcmczbqjrVl3o9zEzERBSS+QTAO9e0XVUVo7p6KThPVM0UEV8Vf6kOkAuPb8ooRGInKsHCa+SRpRL1VNwNAPPlugvhu3r4q00DAEf707J4uUvFD2oFkChEKG0b244GlTkiZESMGlNvopleXbADgKhRTNQ0CKTw6G9235i4QGQkUVEQMwNCAEPEdAh5/WsqXBR87RHd8MXMffKjqu6Cum88Vq037WdfPO66SEij4eCT9++NR4O2C95xF8LlfGlqIUrTtobmHRvoatN+9fD5+cWciIaDarnaeOcGdalaRdHlaiMq0/GIENUMEEIXTy/mzvHedAQGROgce8+rdfP8bNbnGCIQohIj6M7c/67P6s6ndONfJW8PXTE1EZKBqUqnamzkaDIaitpq0+QGykwmk8mCO5P5zggxzpZx3TRN0x1Mx1ddBGqSRtCIeDU9UFSiioRQ1BUSqenVKfh2ANxXwUsfs32DFELA5CchpPQ1/cYbIjseVqVzbrXeNF34xqtsq02DiId7k/IVQ7MhEpOJCBgUDjwJmGpMkR3b2sKUyd1nPEdJaju1jYsjBfiGgvuFjqdeLyMi9G3k+Lo+dukCqFHhd5mMRIjIAEAk113LyMzMrKopdvrVfG41jSpRZLneiBgjrTdNVXhmPr+cFUWxNxmGGM8uZ8v1+uxy7r177+7R8dH+05OLR09Pjw/3p+OhiJ5fLk7OLkIMRVHcPjoIUebLpaqtN22MAmhEtFxthoP64ePTy/lCVUfDwd50eHJ6eXY+G48H0+nwuNzTNuhqQ2WBRGb2DS4g4Gs2RvtX0/AlRb4btANY1EjIzvN4WIcY27xAmclkMllwZzLfteyW2XKlZoV3k9HAb60XyfURJFyVgClbw0KAwSCqqCkhmlmahQOiiCgiMfVJETdJp/T1aaKcercBYFCV6bdpFhuifHvJs9o03rt9Gl3zLqsiEahGjVA4Vxa7VnCwF3ZzNFDoU+bUtJOAL+QbfhtLyVXlXfDXq3YzAzVTQSa6flUh7VqapeyZV34+3ZzKnc4PUWOv8k2T9N+03XrTPHt+HiXeOT40gJPTi8l4eDAdzxerLx+dTMejy9mCmX768ft7k6GILlfry/nSOXd2MWu7wETnl4sQBBBEZL5c3z0+DDGenc9CiG3oJqPhs9OLz7964r07Ptw/n80//+rp0f4Uk92E+sKabzbkft2zZ9AbWcxeuMR3o3REMjBMW6FVOY6iuQ0nk8lksuDOZL4PFqs1IoYQvXeT0YCIVQXAekGMAADbVTNsm7atGuIi5dltbc0vRt1RIqWtvqQLX5KPAEyczCpGllKxiWgyGqR7Mlusmq779tHIZrZcbQZVuRPcqhpCBASTaIhmaiLoHLx6Nkihcr1CtV7eAjIRX7eafH9IFwDMRAGAvMObzM19XbmpKNu2WujNdy+Nt/vjg6Fjrqvycr48vbgcDeq7t49Ozs67LvjCN223NxnduXUYYmzaTk2rqji7mD99frZpmxDiYr0+2Bv/5OP3/+73X6w2TVWUaTHx8HCaLgbcv3MUYry4WIQYy8LfvrW/XG0uF6vbR/t3bx9umnaz6aQLbOpHAy6K9CS/wVfzziDgVmdfex+CASAzp4stjh0hEcNoUMcoslpLbsPJZDKZLLgzme8cM5tvZXdKWVbrE96ufV0QdKRolFYbzQgQk8hOrgiAqJGBETHNDuH6tfyd7ANL1lqCbYTFumkvZoum+87M3CHG2WLlmJOxxMyiRCAgRgSGGOH15gFL3YX9Qp46Lhw5fo3l4xtKalEzY77hZ6aDCGCfNE3Mr4Z4iEiMUUQVgCSkUa5DMExuHksnhKv6W7QPlOwNMwghxEL9eDggohAjE5dFyuyzo4PpsK4++/JxFLlza78s/P3bR5tN+/svH3nHo9FAzbx3BpaWMomRHCEhE6qhc0yE3nFROEK8nC3BoCjcpz/6oG3bz754HEXvHh9wSqvcPsDkZf+uhtzpmoT28+wr2ZRIRMjItM2HCRbSOuygLtVstlzlz4RMJpPJgjuT+R5ltwEcTEcpWm5X6WcAiKQaXF2x96lR0kBhW/O3U4QGIKpb/X2lZBsBgQxMVDSt1SEAgGffhrBp2uW66b51wftLLNeb0aBOgjspLgPDwhGgiFoXjejVBdDkbwkSe5c54nc+2E79Ozf/laq0HSDwFdP21W+MMapqusLATMSEiKpiBhEtScy+5Qj97m6LSpCwc94PB9WHD26v1g0z741Ho8HgcrFYbTbTyfByvpgv1+/duXV8tH8xW1SlPzyYEMFkMvjxR/efn89UdG86VlVRLUv34P5xjOLYtV3HTMO6UpNBXY6G9fv3jiejwdnFYjSsbx3tTcfD6Xg4X65n8+Wgqg4mQyZEX+1i3RGQANRUTLbJ8fgtn2cz3b0DX5ynABRMNe6qWBHUxAgpdYUu15v8gZDJZDJZcGcy3xeL1RoAjvYm7EhUzDQ1wxMieRfmK1Rz04kSMLKqGvSN2qlq28wMFIB3UilZaQkpteGoKVjqnAcEIKQocb5ctV38Ph7Ocr0pC+89qxkivlj0JAQFWTdUeCr8tRGyAQJGjSR9ibqoinWeHON3Vo5DRIg37fsZgBky36C2RULbhRjRcVEUiIiEBppORLA1o6dZcX9SMgMAMQnSZ7CAgYAO6vL9+8eqimm5Emk4KlU1BHnyrJiMh/fvHO1PR8dHUwDow/UQU3f9rtwxrckO630EJGJEiCpgpqZ7e2NCHA2r0WjgvC9Ld+/2AQAg0KAu79za1xA1BKCXS5RSH1AKlDQw0WT6/4ay26C/UgNbswpuDUNRoqpYytUBNADDZHmiyWjQtN2uXiqTyWQyWXBnMt+L5kbEybhGslT+4skZmIkgIrNjYiIgoEZbUzM0R86TBwCj5MNQu+Im2a0bqu721VLPoqlp23XfXwTyarMZDWsk6EKX1uPSn3PhlTAuVmaGziG/kHRqCohoGDWm8kLRCACOvjO1jYjMr6kEEkGmPju8j8DunxyL0ttgVDGFABJ20okIAtIrzS8isVVlcmkLFK7Uf/bqcxfGompghFgW7r17txDRXdnpJCSFPp392kOAvoLHwFQtNcuY9dErKXmmrooHd4+IKB3G+tJ1NYsREemmkp0Uj5NeCH3VmPQuaht67xPYLmAe0AB42zlkJgqYenA8OxWLMRbejwb15WKZPwoymUwmC+5M5nskzZ6J0BEbAAGqaQhNtTd1VZWGryn7T0EZ2fMV94KJRoVtNfh2IKqEzMQMhEiiAmabphPV5aqJ31s0hBksVxtAM9WdYdrMVMSicFGgu1a+029JpuwPA6AXE/rvJqDkbe6ygbSdmaXg85SdiMTkmKnQtpUQ0lCbkAouUmDhS3cPARQgqhAxISkZvlDu0KdzGPRz9CvxK/6mBvgbH3vfSg9G6RoHXJPG6RdMxAVtbRtAiCaiIQLh68pKr98CfHPfvKXTAhtoOhZ4duklZnJEhBK6KIjIREzOEStqjIJgo0GVkhPzR0Emk8lkwZ3JfI+ib9N0o0G9k9HWdGBGzu9CuKNE3CZjRIkp7WEr3vCllUQ19ejTvDzF0q2bdrHYiL7Wzfxdsd40heOydLtQajVVFYuxb5PZqnBAMNOd9wC3MpIQHfMPk09C3oOqhIhgSNsTAgBtTSbee1PdtXgSEhNHja9qVQZMMjy5upMItu1K6JP/x/89feX9//q/+foD2GtUb1osvep+6W0tKXJku765C1EBgP6o4Nwb6pNgG09JgN/ynEOISD6VGaUqewPr36jkgQEQHPntyBuJydSYaDKszSz1KGUymUwmC+5M5rtnvlrTpmm7cLg39s5J223OLvxoSEwpyBmR0jpainq4KkYJyRFHBdj22gCiI7dcNzEKIviCveOmCV2QH6BnxDERATtGQlON60ZBkQgIgVAhidLkeO7VGG4LepjYsUsP6huPWs1MzegVx3YqAHq5zhMRmN0bujwdW2Nd05kaEbF3Kb4aX9MAIyq7m+sfCABc9fCowjftziRAu3KjaV0zXQ1IVz/AwHDb646oIVgUemNZKUCaSCshfptYmDSAR8BkiNq9Ra8o+ORr6nuO1CxqMDMiUlUiHA0qVd203e4HIoLmBvhMJpPJgjuT+a5Q1flyBWB7g1qXK2R2dYXMIFHNVEPpiphyHsA8F1c1tyOnqtEE+i533jTdxWzZhYgIw0E1GdU/zKMgRO+YPRMhAErbaduhd957LjzQNjjFLCktQvLkREVMmNi7AgFEVUwUkwok3CZG36hxRUXBrgabRI1RxRE7crtulxSBIibp1++kLH1ZxBAlhk60sMocqBmh3TQM3lk9cJfLiIBw1Y9O33xyf/Xxmxmk40ryhW+n2mqqoAhoqhYVEN98iy+C/L7RJYXkcsGX7+QN2YsiYgZMpKbJxR5FEEFNDQEYUGFYl2bWxchMhXebpsufDJlMJpMFdybzHTNfrqULQ5XR4YEry16v9ZFt5Mlv56YvBI2YqoqoMHHKp4tRL+erlPpnButNa2YhCsD3OyxExNGwrgq3LcUEU+W65LIsfMnMOzWclCLj1pueauAJCTBo6CM+MO3bEUAvuJnYk8Mr+eJRJUpIJxBPvRwV1ajRwHrXu6kj9uwNIKoAxDQSTuaQr1XeiOiLwjkvEtbrJsRAxAh442bh1WrMFz8ZEQDu/9f/jYm8edL8bkp3u4jZy3hA7c88pKYIoF0HBlyV8PrHuFPb72rgsa3bXbfXTBSM8U3Pp4EZGmDKTIz9Yq9B0utmhgweeYRV2wXvHSKu1m3+TMhkMpksuDOZ755VF4ypRkxv3CARwAgxqnh2Dl99P1vq6mPk5F9oms3VC/Gq9gMIFwQYDeq98QjMosW020feq0QzvapOHTk10V2OHiIhuu0aaGrctN4BAkH7IXf6YkbaZQVGjUEimKWpOSNz3+cCZiYqCmJ9PRAwMhERoqhGEzMjRLZr66dvenSEZmiYlhGJifBdnpn+F9+d2r7xYADbnVoyNBEAQHdDic8uUxIQ0lvrG9vl+zbT9O2miMivz5YxtCjR0GAXnwJ9bRDt9n0ZCnLOMwI0bcifBplMJpMFdybzfbEWjWYlAAAQUsq42MrTl7+YkcGl0XafVVeXpU1AVJer9XfebvMGhnXlmKPEnaUYmSyYiKgZv5CG/ai9N1sDKIAnYuJoktKm03nBwBCxr5w0s+ubob1RBNQMREVJGUhUtgaJNBcHQlTVqJGAKbmIAaAfhAshEb+V3DRVVSGipA4VDLaHge/1Wb0WdgJIiLvp8g2eFgNAsCgmSmXxUrh4sn9cPwzQN0vdTtddDPuVTQAgIAQQFQGBbdrgVTM3YSp4B+k3UDHlJ9KL2ksDAGZighglGbuzhzuTyWSy4M5kvi+W603hvXfs2e0k1+smkYx91p6YgqlztDcerpt29UPlrFWlLwrvHHahU1Di3sWLTIBoYGpixmmiqapqxkgKZhYNkABEo6pEE1NLTfVJ1e0K3gmJmfm6cx0Ag3QESNgLx6gxiiDiVSm5lcVGyDuJzKRq9pbDXTU1RPZOQwxNB4RGwNwHY79ugfJb6uwrtnXcddP0kXvb1cOr30KAmrZRVQHsBrVtCogEiPTdJMC8aqGJElP9DQExCQCkawiI6NiRaRTpjwtgmJp3kNJZwhExcbLaJw936d0mz7kzmUwmC+5M5ntivlyPB7V3TEhvE9S2C6qLKm3bSYTletOFH0is1HUxHFSmFiUiYz9LTjpPBMmpaaoQT9tyuK1Z6aUg9HYIMyNCRk51h1GjqiGkSkL2uzi5F5qbEQq74h7uJ68pjq8vf0GXyoOua+t38lFEFVEhJhVUVY3KROBJUY2A6btMDb8+hzYEwt4zTklw96L5FYmfpPlWzdqrahu/hXvkbSV4OswAAmCUmH5bsMe0tCoiKgagoNibiWi3ZHltaxPBe1cWLojEqPkDIZPJZLLgzmS+e8ys6UJZFvx2w8g0Wexabbq2aUMI8Ye8Fi+iIiJRiCjl+lkf/we4TQiJGtPUFuBFEyERmZmZFuzTpJOQruzeYafdNvbj5inyVdNwmuAykWhfEpTSoN9mOfJrX5D0w31ZGEBsAykyYIyiqFT69JKlcTd9FwPvXQVN8sz0TyYgv8VPRkS7mtX9Q6nt7e0BETFyZwoAIqLkEDRIEBXYlr2nV5SupRxq3DZ0ppOS964UjTGvTmYymUwW3JnM98NitR5UJZfF16ttjWq22bTz5SYE+eHv6qbpvGfvuI+JvqIJKW0KGkQVTFNMMzBLgYBEFCWKKQK6KwkkCU8OXfoTI/yajUM17SSktPK+lFHVe58OAN/2Q4ScsqlK+sm+8AzsvcembUMrbRSLZoaM5JzRt5LbqUPnm8p0kBBJjAr//antXdvOa18LVSTsw+MRokYEVDNEQgBCRnRmJulyx7Wfg2aakk8QwTkuC69qOR8wk8lk/uFD+SnI/GOk7cLlYhXi1289iupm084Wfz9qGwCYCBH74L8oesXPgESqybZtsv0VEZVcePaOXOEKQgwaxeRV6enZeXae/dtM+k01hXynVvM0WbdtH5DoN+/9IaSCvWef9kGZXVEWzOzLwvtCty0+IEAGhPjDvwSpzt1EURQQYFfzCQYI36XaNtM3P40ICpbCH9OLGCWqmSNOG59EXLgiXZq4usRpsN0G7V99IKK6KA6m4+Ggyh8ImUwm8w+cPOHO/GNlvlwBQKqffJM0b+Ni2cQof1/3ExElqBIwOQXp28yTlvKs6xbQqPC7bUhPxW7wnPzJhIjveDZWEVBD7sMQCcmxA0Xt6+IREJJ3nICCRlVxN+cqvq3mTnkmYpoqewCAnXOgykCEaBjbTkXIfSfxf2Y35pC8VgQrAFgUJOKygG3oB34P6esIbxpvIyBh34JpBmaqYASqBlGjGTBaOh4AwrUFhVTlA7jr0UkWo7IoDqakpiFEQiLCnBiYyWQyWXBnMj+o5m67MF+uw9+f2gaATdOFEL1zdVmmvh1EEpPdAp+JgDkm1iQOr8010+yTb5xha4wmulPVAKAhIqGGqDECERcFb+0TTEzIUaNoNDBCZnKEFDUGCQCA2jdNfoPHqNaPzz3vmn2wX/1EgD6r2+A7WvBLvffwRmkLuw1LM4gCagiIhL1Ffjss/m4TVG4sknxVcyP2h640DhfVaDH5thUsaDSzq2b3dEbDvqIzmf7FVMEsSCSGvcmg7SKnntDFugsCBimBPpPJZDJZcGcy36/m3jRtF8I3Nkt8A70FN91YFE3e7dW68YWrK6fbvhtX19K0GBVKQEO4nl39hiTs2LRx02gMrixVlJg1Bo3RD4dmhkQSApj1CjAt4RGBEbEHxNT3noSymRJgjPHtg7cTKdibiaPGNnRE5MiJiYAgoJiqCb6QjKCqpob0rTUubpO333wMAFNVjGJdRMdUOEuXEdLTAikM8e/HVoeA1K9HEgIKGCNh7/NRBNyV8vTrpgYpkQYQzMxEDVK4oJCidy69/w2MJsO2DQbWhWhq7DhGaZoAAETEhAYgUXKCdyaTyWTBncl8N5q7i1G/5zkfIq7Wm/PLedN2h/vT/emYiQD6BpYUH2IGUeTk7OL0Yn77aK96setpxAzM2gYjIu/VTFQZ7Wsnr3GzMVH2HplANMkx8p68Z+8AEVZrU9MYt7IUTTXdG2IGh2KhaxoxAQPpZTEBuatSL9Uu0k0pKGraSadmJfZV8AaWEhivHDosNewgAAHEKKELvnDfMuv6asS1bUt/cJt7+OLLDMggWWuoLBQBAK4nbePfyzt26ygBQkLAZA7pI7evLFxaX2ikqIAK1gVFQGYgBAVm7Ds9rz5kwMK7wjvtcwa18K4L0TETIhGlfPRm063zqmUmk8lkwZ3JvKvmZsL96dhdbwgP8YdIADSAKPro6Wny5jZNp6oH+1Pn+GI2b9swHQ+bpn349Plq3RDCoC594dquQSTyxFWpUUzUnKmZaURE/0osyUuQ91SzK0sA8MMbvtIPByoCqkn9p9VIQAazGIKFVkw1CjKBWRJtoeuInfM+6Wk1jSJqWvDLeSZmFiVqb9kwz17ZokTc2dMREUDMDIyBEJC8YwAVCY0CESISId/Ur/62mnurSlPSiAHC1qSR3M8SAoi6okCmtIDI+A9lTXx3QgCEXcPntYNEqunpZ9toMcqmSXGAxOSYEAjEtkaTNNyGF92WiMjJY0Kl98XUXbW7EGIW3JlMJpMFdybzzqw2zWhYM9HO3btpuh9gV9LMJqPB3ni0Wm+YabVuzi/n600TVbourjcNMzvHj0/O2rYjoi8ePZuMh08ff/nb3/7uk08+/unPflLXNVeF2otkvSiBkNzXhP31uvZNopwZrpxAuCg0dVnGELsAiG5QpXFvqt2BaBKCoQGiWEpNUTFhuia3RSWqiEY1Q0BRRZSUc5Luf6rvAehdK0leknfkWKJIFDOzKAomIQ15EYnYvXMieBoU0zbOXEySkBUAELMYibhv9DR71w3JNGC+cQnSto6WK8WQ+PadmrvI8J3sNnjxc2x7hWCnpVFNQwQAds5ELEZgJkQVMQDyrnfIGChYXxfaZ7X3zfAvOcsJkZlEssk7k8lksuDOZN4FNYsiQWOSYZ79fLnqQvy+bxcRV+um9N4M1KztwnQyLAvfdfHR0+cP7t1+//5tEX345OTu8dHB3uQ3n305X65ml7P/4f/7P5jpxz/6uDA1VRVBdOy8IxIV0cjX/dwvP9700LbD6bdEVETFELgs8ZpLGDREQlY0iQEIU8Kd7QTcFY0bJIhpmhanrwnSiWra+dsufSL0shvUDNGSL5m9Y+8AQGOMIaooAqoaEBLTuwru7c2hmKaMakIEQIkBgpBz6J1Ar2bfNekl1RAZgF1PM7T0qM0QMBmW0hIk7twz6T8GV/rnX6e8wfqUwJ1CJgMzU0IiIDC1KNoGDRGdo7IwEYuiIYimmnowAPQewCAamhkDMKXX4rWf+94N63K5atSylzuTyWSy4M5k3l5KigaJTilVo4cgXfdDrEsy0cXlYr5czRbL0fDW6flMVaqyHFTleDRYrtZfPHwyGg7KsricL1frDROVhftX//pficn9+/eGw4GZIjOakYJDclwwSZAgJjfm9GkIliL/+B0i9tRUVKOKmr40tbW+UIZUFRwR8zY5MBVDkqUAQSRIRe4mhOTZp98amIhoL8ERt0uRafqbRrZqmqTni1ErE5N3SGjQNZ2a2Bsn0CYKYMh01XiNvWRNevpF0yQZqm5H2n1TDL5rBHi6t+ngoWlI3/8ES3NjSM6NrcE9ZZr3t/niud2GnfdPJqbsFLzy5BsY2m7ILampHgGhP8MFWTeICOzQM3k2MSTSGNExGkAQ07RGaaCGVYFYEOHWl29w3YFjZkQwHFZq1rYhijoiIkxh8KJZgmcymUwW3JnM6wSZWdN0YFaWnhBXm02QHyINUM3qqrycLw/2Jkf707osZotVVRaj4eDwYO/scrbZNKPh4P6dW5ezRdN2d48Pq6Iwhf/s3/xnRMxAohGJmJHUoBOzSI4QMMZoIBYFDcg7AIibBpnCaoNMXBTEb2uAVtUgoR//J216xS6cpsJKpCKmZvRChaeq8SgCAJ590pbJwoFbn4aq2rZMJ31n+j4BTY4I6WvrDc2IKKnkpMapTx+3VH6ZNO4NFg6RfqIfABFpu3VKiHCT8YYcqELaEvyWry8iUkoSxHQ54fo9xKtfmWbisItU3+p17YU/EhikYTwhwbZ3lACREI1EVUERiQiT4DY1iwJmWJXo2BAMAYnZ1agKYCBqXZQ2QMoaF2Ui9AUoOCQkMjBRMXgxpE9TeMc0GlaV9yGkFEJQs05Eg1gee2cymUwW3JnM61iumrYNg7okxiQjfgjBrXq4PznYn6TfTsfDu8dHWy8BHO5Pdtr1+HAfDBAhRF2umsK7YV2z43RaQGRkCG0LACAAZjHGqIpRmTkpp3axZOdMFYm48OTcW97DXssiqtmLrMBXxaWBRkn+j9h1ZEDOSYxIRFUZNTpyjIzcT2o76UQFkWAbb3dVg25n24aAjlNduSS5p8ltvFO0jqST2EVhdc69tPmqXdcbKoikC4ZAX2ekMREAQPfdfL4hIiO/1dvJXq5277/3iv5OkhyuFvfsQmC2cYDJrwKQtkCNBxXVFRAaplG4EiIQGgASIyEzIpGGqG1rMVqMZkxMzrkkuNU0Femk6wBmBmoeqawdlGXbNNIFIyTyqtb9vebWZzKZTBbcmcw/dEKU+XLzwn77g3Bjw8i2m2X7u+u/jG3XRQEkX7iqLNNyp6USHMdkBqAEBERcsy9Lcqwiriw1hGI8Smr7LcP1klJM8+lOgoFth7XXvowKb451tZEQwRHEaIAKCCGi92pmKoSUHpYjiiKistXWNwj4lIeYsq4JUNGY6FWlb2DIhGbSBHAEYlikdUV0zABmooZIhUMkdqxdkC6kbs7Xql5RMPgOAr+vy+63+pqbAsJxZ+pGYOQUP5JOQYQE1/6W0uHEVC31IPVvZsM+nhENTV9EiQMgk2MyRCSLUYPAekNVaeil69AxE5tKst0joqqaKYpaJ1EVEZ0oRgHH5CgwR9Hs7c5kMpksuDOZr9eX//CJIpeLpage7o0L3/dBhhAA0ZWlqgJHAORtkSQiuqqMAOQcl+Xb3xARpeeEiQsANVOT1wlGcIRB0BCrEohIAYiNQK4s9vVPMygh2Svp11dVJiOmjJKgEQGo3wh8UfPYn0AQ2TEhAbOphqYzNUQAz+n++6JIBgxC1FRc3xogUuHgyrjedqZtIiTqmybBwICQvkGppNnX91m+qrnxFf2f0k6S4TzNvBVUTBCQkNTSdQAgRCb25INGAQEzYAaiuNowInPVXyzZetcxlecgEBIDgRnXFUAjTWeiJqqEXJXsPSAEC721BwAMNKqsN2iAjkENzEAVgjGTZ2rzkDuTyWSy4M5k/smwWK0BYFhXdVV455xzqhpCTDqUmZKfFwCQqBiPivHoXW9it9WHgMQkql1U2MaJXMsqAaOyoBINIElV5zxFCxYMELBP5wAAs5DE4tdK0mQsgW24R1pphVSiCf1BgoCoKpOOVJGw6UwVGVUVTNmXpS8N+uRvLBwZWxtAVRo1MCo8ESNir2vVdguMov0uJgN8Xcziy1L7pXXDb3EEBDPtLTf48t+Iaf/SpERFMzERjUmkEyE5p9BaiFcvk2x/lO3WQgVU0MAx1xUAaoiy3vQT8BS8iARbT0u/7+kcIbhBrV2ImxYBSLWsiqgCWXBnMplMFtyZzD8xzb3eNKNhvT8ZFYVvmjaEAABqBh0gIe9qYphT2Ib1/YqafAfbv+rVnKqKSJ8RAoAI6W93lSiMLBIV9IXpwlJ4H6Yg875yBQCJTIOqIru0FimgapryOeBtpr+IoJomswYKkJJMrnXQ0NYdoaZAiIU3i+jYVwUSOmLsg/cgxfA5cjBwqho3TcqiVgjsPTADAhACoMWI6GiXy/6uCnl7GsHvoo3y1WhF7VtI8UodqSVfe38xIW1eIiATl0Wfp659MPgV5Q0pp9vALGXKoHNE0naybrQLwi16B46YKbnJ1RRAiR140TYQM5ZoZhqFC+dKbwhi1rYx/9vMZDKZLLgzmX86iOpssTKz8WAQYowxRpEYpbf5EhGhd25QV2mhcGePNtuJ7z73I+lbM7Xt6h5u4zUAII3MmUj7BJHtjDRFhUCfGLKdEIOoSGzFNAUUpg1Ieo05+saR8G5UTEDJN35j3WPv/AAkROfAhBDQIXvXm22iSdS+1ybVyCso1xWZQhCNUbqALOgdIqJnC2aiSEzI38DP/82k9ksbk7sfdcPPByBkQLQ0kNdeNCORgl79OiMAQjCzLqBjADIGUVNRxxSirDftcFAVhUt3Oa3rknmL0URSIQ4qRNFls/GFH9alEWqMFoUKh0RA5AYkIugIEOu6QMY5NG0b8r/NTCaTyYI7k/knxWK1adsgqvGmQEPnOERJ09DS+7L0hfdEfTyfiEhSVwDM5Ny1XpsUVCKiquq9IyLnHJqISvKabBV53xOZxDwBdYuVgbm6JCADUFMmotc0yCTJ/5JzIlm38UUSxw0idSvKX3QkOseOPF+JK0ljewBj6mf5jp2aRTUqPRVeQ5AY+9sjQu80BIxAnmTrMHn7Jshv/CIqKBn1N7cN3t4dRXaXBRgZej+9pVgS0JTfogy8zeTGZAMyJm2ChshVAVUxm28ePjvtQhwNa+/dcrl+cO+4KEbp+IQAhmjMVFe2vQOgupivPn98crA/+fi9u2YmUUS1GlQpACeaIhNQSkmBovCTMS4Amqy5M5lMJgvuTOafEmbWhtfqmxhlETcAQIiNDwOtfIgIWFdl7/5+TQoeInKPhhBjjM45xw61b6JJ7evbxAxIARligoYUVU2xSi2KekNCdipy3wrlbdfNtVu/+vvdHP5q78620nLX1YjQz/Vp910IQIRJuqZGSTU10xTwgYhcFMAU2w4QlLfiMeUggu0U8Pf38iUTuRkoKCJK6vpJMX9bLfzKU2HJqGP9bNwAwQBodxHADIioLEBBm1Y2jYh++ejZX//28+Oj/RhjURTL1dqdnM+Xq+Ggni9WVVkuVitTO5yOh2Xx5MnppuumoyGazRdLJPyD2Xy5dkTH03E5whBjGzvyTNRffEiG8rJwNB3AbNO0Xf63mclkMllwZzJ/XKQC+bYLSeSNh3VVFgjomMvSu9fUT27ajgm9dyHEGMU5ZGIGBgAxxW0fCiGpqaiAGiCWe2ONaXgejV9MoK+oZVMzNNv24Hz9oWLr57aUPcfIBbNqH0WXOtMNLMRwzZuefN5oZiYaI4CoEBJe8bcgETGDqgUBUPLOzFCNiMCMkL7v1wX6swdAimQxNUs9QWh4w5ODW22NCMiY7B+9zu5/AX1gIDM61qZVMcc8HFST0fBgfxyjnJy1eLn46vFJXRUxyu1bB18+erbeNAfTyd3jw99/9dgzP3t+MR5UANCsm0fL9dOzS2Lq7t8Bsv/wF3/Rhu7n/+zn7z14z/qK+nQ1gLzD6aTGBTRtl3MCM5lMJgvuTOaPFDObL9fz5RoRvXPDuvK+/0dNW/9CCqZYbRpm3h+PnHPJJe69643dSGoKfSlLSn9WSKNuJPYeALq2MUd0PY5wu1nYb1kCvtaM8aL5pa99MbN+pO2YmTiigMSdJkdGEGu61jvvHCMSE0VNhe2gySzd+zBod7uE/T2MbatRtGlADUcD+BaD7Rtt2Te+EOlGqI/iNtyWAeFLNTc7tf3S6cVeGOrBzERMFURNFcxADBGpKhnpYG9yZ705u5hdzheT8dAx709HXQhn57P3790aDarjw73lenN6PkfCuir/+U8++rvff/Vsttgbj1S1LPzH79+bL1fzzaYNw7/8y796evLsg48+wBevFKJh2jetyoKILufQNiGHc2cymUwW3JnMH7vy7kLorjhS+paU5KoAS/aMsvDT0RCAk+Z2rtfcKSpbVZmYep8xmamaOucKV0uM0he/2zV3uPXKEkB3IdGv3rckuPt1QDMAdOySt9sAgkQ12RUF9XNftq4NIURfutKXjpiAxBAJqY9q0X7pUIGIdzebogPZsaybFIFnYAqGpn0U9htU741K+i1c3dcUOYL1UYD4lnp9K7LVQgRNIrt33wMCMmPhkBGZ26a7PFsZwnBYbZouxCiiy9VGREajwen5bLlpzy/m3jvHNKjLs/PZ549POpW9vTEhNSGeX8wGdRW6MBzW73/w/n/5X/6f/vbvfv3Tn/7UtvU6jlwax6emHSr4YIqXuGraIKL531omk8lkwZ3JZHa6066Gc6gKAKw3bVUUKWRPRAF6zc1IwUA0GhghMREhMZJtY0nK4aALnXQBmbHw8CI7bycnCcEIrtbQ9Oo5DU2ZyMzS3JSQmDhIEEvR3paiVFJ8npqFEETURM1MBM1bVBGVFNqdFHnhiqgiGg0A7epCJIIZEvnRUNtOo0DqbgRLD/xF8Q68YSifHsI3jOImREDedUVus0OuFPS8qsINLERdN/21CcfkHDoGov7QEgXAXOHKyoeLGKPcPT482BufXy4QYFCXk9HgybPTwXBgAIw4HQ9vHe6h2mK12p9O7t+5NVus1Kxpu/lqNRhUR/t7hvDRJx99+PGHbdepqIAxoVm6kABE5Bx5coQ4Hol3HIKuNk3+x5XJZDJZcGcymdeSenYAgImYkRHruiq8TwncAJ6QkIiRrjqee1sDISJYFDVDx4qo250/6PcaX0jTlCqd1h93WX6OHACIipoGCVHjrhySkFMAoplFE4miYs4zIBL3jZS7EXiU6Nh5LlJkNcHOgn6tG/JF0DWgI37xiPAHeraT7E4WHUNA2/qjX6fjRQHBjYeQfOm4va8IIGpgyFwW/PH79z58746qMRMA3D0+hOQcivHerX3yHrZ1kgRwNKpD2/mqLNjfOtqPGpkoihARI0WNZlA4XxVliCHdLxFN6eDOvQh3995VZSVRo8S2yxHdmUwmkwV3JpN5C82NAN67q4NWAmJyTDflZBsgIJWFBZEQUAWcI6Y0q06LjAbA0G8HioklGb2V7KKSilfExJIRxHpHByI48o4YUvliVCVlh8SEmPYiCRE9+6jRQFN0nZqkOJOrIjoFnvCuaIZIYyBRdn9vn3UpBLDvmbf+SMB0w25rf6JI2XzXjd/W20sQAEwFRJn7g4hzBGYaBMBcVV59NpJRnqKgqIF4x5aiFRmhTzBEAIgqBb8IYVTVrgvp/LM9OVDBBRNHjJNJPV/kiO5MJpPJgjuTybwFBhBC3LQdb+vjRaQojKh4ye1ASKUr2tiJCnhGR9YFCJGoQMAoYn1Xi4kJAvWLj4hpsE1mQWIydfTJJEQmqmAO2ZEDhJ1ERkBK3Trc92ImqQcAnh2ABYmApqZoSEiGvSMF+rG67swbqanRDEz1jc9DvyiIW5EKb9Og+Q1kN+A2yYTe5hte+j0YWBRD1aY1M65KIwIzJNQoiEjeX31xzYyQfFUTETnvvN95aa5evkgx7cBXD1dmZle7S/szA5iZlUUxneDlzLo8585kMpksuDOZzNto7vWmRcTxoPbOMROAhRBSavdLX0xIRqamBAjOq0iyl5BziE5UNElX06TRiNiRc8RqKqqEREiEAMBiikieffqCl2+ImEQJ0oT7RSk6ITlyfZO5aZQI11vTd3nbKXLbDCRGRCTv3qC2zXZC2wzATAGQUt/8d00ymdyo+BHelAFCjpHIzCxEE0XHKgKioIqOLQpVJTJdU81gaqoSVVU1aiuYNkpLf33FE1+6pmG9gfulx2+qKqoIUHi3Nx3O5+tXa3FeSod0TGVZAJiohk5E885lJpPJgjuTyfzxIarL9cY7LgpXuMLMQoiq8aUZJwB4dmzUSadmwESE1kXpAgKiY0RkxJSKHVUQwBEn57SaXm2xAQBGYle87i5575LR5NUqHyZmYlHpJKQYkJePBGbRxIAYGUAVQGJk9cCvVdyI20iWtGdqSfymlMQbujO/i3OO7cJP8EWM4BtvIj2/AMZEpQczFUHitB6KhX95Ip7yXwDAO3REgKYa1hsT9aW37Y5pWmD17G+Q+NdVuJoFjakjiZCrgnECuNg0bXixhIp9yw8iFp6d48K78ahWsy7Ey9lKuiy4M5lMFtyZTOaPEgQ0hBQY4shVVZnKcVTNOb4qvAiJkQ0ipIqX0lMHMXRkjhwTMRMn1SumhP2eoiN3o2X5dSTly0xvEJ+p1vFmXQq0rc8EXw8AN9J1WJU3Gjlwa0ZBwHQnxSQZP9RMVRGRkL/jZ7xPeDG6kiDOSIpob5M/mNLTmd/8mr44jSADABK5upKuAzWjF0cIM4saabsmm9qHAEBEdgceAxOVKJEQ03WJToLzPJ0MeNVEkRDEDBBB1RD7EXhR8K5GlIm8c9mFkslksuDOZDJ/pBAhgIlGMQAAT957R4QxSgjRuWv2kiT4tgNaoLLALlgUIxIQjYKiEdQAxJCLCvsFR1U1JgJANSEgInqD4FYVs9d+gaiEGACMiV8dcvfR46ZpoRKRVJMN462aJhEIIIr2QX4pzvw7PuH00+rrrwIiIX2vE2ByztS07dygfnHWAgsxMDtHydttiMhMMQoAOse92taYHPlpHF6wJyRB2d/jGGWzCTFK03Vpdk6IKhaCVmUhKgTIHoaDomm7nOSdyWSy4M5kMn+MRNGm6ZyjwvtkqkBEZiairgshXLOXXJkrG7zYMzRtO3LMyBYV0VRiVGNfOOT0XVGjKACiaPTkCyrecJdElEhfP8RFRLS0GggGBlGUENNQPCV7M1FfbOmZzIU2kIH3X/+JR4gAbAgEqKCYHCXfKwhpEtzHktj3FlyYipBELQo63mluQFCVaFa4YmfmCSHO5ou0jkoMReEQsetktVww06CuvHOqulhtYtSqLArPy3XTdiFdf2gu5oX3gyoQ4WBQMhE7Gg7K+XIDubAyk8lkwZ3JZP7YMLP1pjOAulJHjBUWREmelWXxir3Etqp0u8voPTLLpoUgVHoelkoQ2lZDsC5AxbAd30YJBpb6F9U0eRi2XZUvNGYyfK83zcn5Zdt26U/2p+O9yQj6hMEIffw2gMF6056ez4lwNKyrwpdVoaBqyshJwJrB87PLAPjg3i3n+A1PhEYxUWQiJgN7JyfMt9DbmKbIVyqDvi+Jj8xgFhZLPx3v3CmwzU0HAFUTVSIMIk/PLh8/e16WhXd8fOugKv2jx6ddF4lwfzq+c3xwPps9enpqCoNBeXy433bh4ZMTx/zR+/faLjx8fIKIReHu3z26dTh1zKNBLdFydU4mk8mCO5PJ/JGy2XRNE5ioG0pdlkRYeu8cb+0lMQRLI+dtPfp2zy/Nw0cDU91G6iEy66YRDL4sAZGQPKfWm4iAqTPSkzcwUUUEhy8+i5iZWRar9ZePTx4+fa5qRweTD+7dEdEuhKJ0UWLbBQCQqMQ4X2wePnlOBIO6mo6Ht2/tdyGEGMfDIQCsNhsV/fLZmapNRoNkbhmPBoO6fOkZ0C5I0wEhGauAmWFVIf4QNTkIQIQp3sXse5yoIxN5F7tgMaoaOQe0PT1tbzVVTnYS5svVk5Oz48P95XqzWG6Gw/rx0+cfP7i3Wje/+t3nJ+cX55fzsiyO9qfrTXt+uWi7+MWjp+Ph8Ohgumm6v/ntH967dzweDNKpSVSZeVBXWXBnMpksuDOZzB8vZhZFLufLOa0d06CuqqKoSl94n+wlMUZM6gw1Rdlt9SKaGTE79mluLUxYOgA0VeQ05CYmUuv932YWJKT1xNRAee2DybnpZPTjsuxCbLvwi598vFiu/+Z3n4voeDzounB+OffeLZdrJBwPB6KqCqt103XxYrbsQjCz6XjEzM/PL8Gs68JoUD9+cnoxmyPSwcH0owd3BoNrmlujAIIfD81M2tZCFArsHRJ9v087GCEysO3+4PuE64rrSkO0PjQEyREwpxRBACBCQibs1ISZq7Loutg0nap9+N6dP/3Fjy7mi/ZX4TefPawq/6/+9NNBXXUhXsyWz06fjAb1aFA9enp67/bR/t4EANmx965pu6r0IrkZPpPJZMGdyWQySXqqdqpdWALAeDgY1hUzlYUnRFVVNTUQi2nBrlfgCIwMACnyAgFRAc1i0yIzFx6JENCRF41iqqrb2Gwge3mRjojqsnTE3rGIlEXxu9OHT5+fHe3vnZxepN27yWi4XK43TXv71kHbBTNgZiQ6ny0Kz3dvHz15etbFaGZ74xEAPD09X643o7ocD4dPn50N6/LD9++8UL1q5Bm8S75wLDwTWYiqho7IOfhBRt27ywffN+QdeWci2gUNalGQqOsEEE2E69qT2/bjYBQJMVZVMV+uTy8u58tV13XpEsHZxXy+WIcoi9Xm9PxyMh6FEC/ny9u3Du4dH84Wq999/mizaT/98QcIREB6ZWnypdDuTCaTyYI7k8n8kbJYrRertfduPKjrsiwL7z2LiEUTFQUFREIgJkSIEoMGR56JfFUhoKwbDIEcAyIjMQIikKmamUoqVLzRtuGT9n0Rhw2L5doMyqJAwL3J6MP37oYYuxDuHh+u102IYmYxRibqty0RwGw0qN+7c3R2OT87vyREdo4YEUBilKZNu4OWVKAqOocABmhg7D04J21nXQADZEL+vizdZqCg+oOvEyIzVyRdsBDNWdN2aMBA6nxqJqqKoiqLQV0yD+4cHfzui0e/+exR07ZE9Kc//+Tk9OIPXz4pCp/cPlG0KgomUtUvHz1l5rLwB9Ox964L8fR8zkRRZHumQscsqvL38LgzmUwmC+5MJvMPjxDi+WzheD0e1lVZIGLhfeF9CDFIVFAzI0QDICAzVUvZ3uKGNRtqFOuCxsjeu7oCADVtTUXVEQOYqFztjOw/nhzvTyfL9abw7r07xzEKIE5HQzVTFed4Oh6paunL0XBAiKo2X63KwovIs5Pz4aA6PtrvuuC9Hw2qu7cO67q6XK42bTeZDg9Gg7Bac10RkUYhx31ZC3FK4FZQA+CqNFXtAoiQMwAg/x1/bKalyai9BR5+YPmJSIUnxyYK7Ng7T94Nau3CrcNpkAhgd24dvnfn1mg4GNTVydnF/nRy9/bB3t7w6GDy2VdPz84Xg7ocDqo7tw7v3DoIMZ5fzpfrTeHccr052JscH+2nI5OovHhHdd26ayd7e6pKTFXpwUBUX22vzGQymX8CfC9X9H7129/nZzaT+ScMEY2H9aAqCQkRVAQIisIbgKrseg4JyLFDA2m7sF7HdVNOx+V0AgBm1kknqoQopkxcbP3fOwxgudpsmmY8qIuyWK42m7YbDWow2zRtXVcp1NkxrTZNVRYAsNpsyrIfuA4GlamuN01dlhYlSKyHg7YLMcpwUBWMEgJ7n4bcCKhmRFSwT705bezUNJ0iLEQ0MzFQ5boExGTsTqbnq3Ef3xADNJOm07bjQYXeAeEP9mpqjNqFdNrxrrQYy8n4xV0zEIkxRudcqsIxsCixk+CI2zaenF2m/41cqZzs4yNfMo3sfrtaLv/6L//i7PT5v/pP/83RrePCu4ODceG4acPJ6Sz/+8q8Pb/48Sf5Scj8oyBPuDOZzLtLNNXZYjVbrJhpVNfesSMyBgUVMSJAfpF2x8ToGZmKyciPBv1PME35JMnJzdtaymvzAIDxsC49p/H5dDycjofpr0bD+upXDgfV9s8rAEh98moqKnVVmIih1XWNnouCEbGX10y4SwXB/nFFFEfMxKUrxBTMxASLwswgjb5DBDPyzlRTSzsxA9M33q1MUYmEbIg/ZCuMiWiISKSioAaOkYnKgq7kt/QNR0hq0LTdMMWxGxgAATK6wuGgqpKfBAFSKdILm1Df45m8/piK6FV1tVr97a9+9fTp048++fHRreMQZTZfjYc1EVZl0bQBssskk8lkwZ3JZDIJEZ0tV4RYl0UQcUzECMiQSmcAosYoUduOHWPhW4kQhJmdI0IE3Ek6ULXFag0AjrnpukFV1lUJAMwsIqrKb2GhJiQRXbWNmbFDIDNTFUHn1jF263Y4rDwTESFA18V101ZlMR4MVWVbQ25J+jMxA5uZAwcAUaKiIpOAQVSNoiLI3A/4Q+St6P8GIKSayStz8u8xjBsAwFSl6TREKjyYoXdKdH6xuFw89Y7Hw+H+dByjPH52BgCOqfAewKLodDxUtdls9ejkBIE8+6osisKfnD7ftF1ZFNPxEBGfn12CGTseDeu6KtebZrFcq9lwUI8G9e07t/+3//l//td/+Zf//E/+ufe+abvNppMo08lwf284X6zVDAE1O0wymUwW3JlMJpNQs1XTdjFWRVFX3jufGiDTXFNVpG3RF0DFZtM+O7kc1tW920em/RDUTLsQQeX3XzxOcX7z1er+7SNmTmnfqhYlOGeO2cxU1QAQ0TGZQZSISI4ZEZq2e3xy9vzs0sCm4+Gto6knhCjk8cmz88vZ8icfv8eDigkVbL7cnJ7N7tw62B9xE2MUccxq1oWIAOzY1FQVEQ0NER26qAKO2Xs1YzBCMjBpWhMhESS60VsioqrGnHT+TfIXTFUMzHZujO8VMwsREYu9cf9bg+Vq/XefffXVk5P9ydh5d/vogBD//V/++vhwvyyLqvBN2/3kowfDuooiZxezX/3d54vlZjwaHB/u701GXz0+iSKierg/HQ3q//DXvz7YmyDSZDx8cOf4s4ePN5vGzOqqun/n1q3DvTt37925e4+IBlUZQkhj8S7EuioO9kdqRoAhysXlsu1i/ieWyWSy4M5kMhkAgBAlxI0BABATsiMgQ0QiIu8VAUyDxK+ePBvWAwOYL1ZqNhyUVVksVusQ5OGTZ3VdGZiprdbN8/NLABhUVeHdcrUJIvuTESLMl5uUKngwHavZxWzhnbt9tL83GT98evrXf/dZVRZ1VZy0oesCIoDB3t54tW6en13WVVkW/mBvDAAPnzyPQeK+Pj+/fHZ2HqMMh7V3brVqCPFgbyoiz88vp+PR0cFkfnnRNM39D95LghgBAMmxFxUoS+MoXeDCv5Rkomqzxfr07LILcTiobh1Mh8PKrJflvdEZ0MCCarJepO6bvnIdbPvFaGBbl8buD7/pASmKiVBZ9L/H3gBSFP5HH9z/5c8+/t3nj37/xcNbh/t1WXz0/t2qLEXky0fPmAkRCPHBvWNE+Nvff/WjD+977/7qbz/78YfvHe5Pf//Fo88fPjk8mA7q+p9/+uPzy/lnXz4ixPl8+S//5FNE/OLR08+/enx8tJduue1C280AgAjL0o1HVTp/qGqIqmZl4bLgzmQyWXBnMpnMNZbrTRdCXRaFZ+8du52zudeLatZ23W8+/+rsfFZ4n2K8Q5TRoJotVlVdnZ7Pzmfzs8tZFBWRsvCO+eTsEhD2J+N0E3VVzBarvfFoUFePn52K6s9//OGf/OxHT56dOqZ/87/85XBQtW34zR+++tvffr5p2vv3jquiWG+a52cX66ZN+YbPTi+IsGk75/j5+eVwUI3qGhEfPX0eorx35xYz/+7zh3/68x83m8V//9/9tyLyf/mv/s/jyQQRk028i62aMRIQIZl2AUi59LtnY75c//p3X55eXFZFURQ+xDga1qt1M6jL8XDQtmG9aYLEqigAoFk146qAdbNoWvZufzIys4vZoiy8c26xXHnvhnXdtO2m7YaD6nB/UnyDyBQzUzW1G1MOiWk4qKbjQao6Wq43nz98Mh2PpuNRUubOOSKFAI6ciHZdVLUuhLoq264bDKqyKLo2diGcnJ4v15tBVTJTVZXDQR1iHFTV87NLlZen+KrWtKHuYll4UW2asN50McrV3O5MJpPJgjuTyWR6uhCjSOX9oLYSPTNT4UXEVCnZtU1F5MG943u3b/36959//vDphw/u/OmnP/qLv/l96tVZrZtbB3uffHD/7GL+7PR8o613fPvoIIrMFsvxsP7ZJx988ejps9OL6Xh459bB6cVsvWnTHqSabZoWEZumRYOj/eli05hCCDIdjz798YePnj7/7IvH49FwbzKq61Kizhar+7ePfvTRe6tVM1+uo+jF5bzpurIo7h4f/vKnH//qr//q/Oz87t07i8VyNB6bmXceALrYqUU1QyIuSDaNNg2CARE5BqSz8/lsvvwXP//R3duH60371ePn//GvfhtFyrI4mI67EE8vZiJCSJPR4OJyPhkNp+Phl0+eA8K920eF97/9w5dHB/sGtmna6WgwHY+eX8wuZou98fCfffrJvdsH7/zyIBKT2g1qW0UXq/Xvv3j87Pl5VRbj0WA0HHz44K5jbtsQQnx6es7M0/FwNKgN0gapEFHh/W/+8NXB3uRyviTCyWjw8Jku15sQ4q3D/b3p+GK2ePzsVNXOZ/O9yYgY5RXNHaPMF5vxyNouLletapbamUwmC+5MJpN5Paq2bjtRBYCqQjNDNRNVM0JiQgAmRkMloul4GIN8+ehkuW5Gw5qZDqbjsvBPTs5mixUiDgeDLgQi2hvWhCiqVVmURdGFsFw3w7ocVCUTOab37txartZ/89s/lGUpUVartYHVZZn2JEOMT56dXc6Xe5PRcFA3beuZp6NRWfjlavPlw2dtG4IIEdZVSUSOCcvCOf7Tf/End+7fadrmzt07ZkZIabHSs0+9PIQIAFRX6KK2nQGYd+S9mgICOzYzM5jNl8T0b/7009/84eGjp6cH+5PbR/sHe+Pfff74wd3jvfHwD189uXf78Ccfv/f8fHZ+OT/an+7vTe7ePvjy0bN/+Sc/G9bVydllG8Lh/mS52swWy28iuCHVDYFFSZGI/f8MmAd1dblY/u7zh8O6+sWPPxTVpydnDx+fMFNZFINBdXo+W642Hz+4Ox7WVeH3JiPvuK7L+3duff7waSpIev/+nbLw729u/+yT92fz1aZp3797DKqPnp2KKjN99OCeqt14EEDE+XzThuwhyWQyWXBnMpnM29GGCOtGTKuq4IJBtSC6fbSPRGZaFL707vho7+7xYdt1q3Vz63ByuD9FQBUT1UdPn683ze2jg48e3D2/nC+W67Lwx4f7YlqWxfHhfll4AJgtluPh4GBvHEVuH+0DwBcPn6xX6zu3Dm8d7j0/uwDEg70JIQ7q0swOp5MH948B4MtHz0R0fzq6c7z/xaOn66a5fXhoYKfnl+PRYH86Kbwzs1SGuX+4LxrNlImZep3KxB4sSNxKRoTCucJrF2TTgNqkruqy+O0fHp1dzCVq2wUze3xy2nXdcFh75kFdlkVRlsVgUDVtu2naxydn3ru265L9fVCX0/HI8enTk/PhsD55fvH05PTenVvf6oVBBAANga8I7qosfvzxez/68D4RFoV3jkKIR/vT7bcAIqSThvcekfam45//6ANRa0O4dbh3uD8NITjvCudE9WeffOA9379zNB0PC+//F7/8yU8/+WC13izXG7uS2H0VZiwKN5uv8z+cTCbzT49cfJPJZL5fvKNBVdae0RQQ2TlwbAhgpmZMREBpUZKJnPOEtFhtfvOHr07OLpjow/fufvLBfceU9gV79bfNaTazGCXGmJQxIjKzRokhsndFWaQwweufc/biAxC0i10nHQJ6LkpXwDZD+upno1r6skBIpSs8+92fi4qopp+pZmbWZ5GoaQihCycXi7/77KtNiEcH0+PDvfPL+fPz+f50dP/OrfWmqcpiMKiePDt7786t5XL11cOndV2dzZdMNJ2Op+NhF8LH79/9/eePvnx0Mh4NJqPhfLkChPFwcLg/eXDvGypvDVFDcHX1rtuX6bxBSDFK13WGOFusRLVpu1f/b1IW/nBvwsx1WYjobLE8ny30Nf/TQUQkzKbtzDuRi28yWXBnMplMjyMaDspqUEAIIEreUeEMwMAY2booIZgZO1cNR0SEgFG0aTsE8N55x/T6WhkziDEamHcOAEII3aZhZi68qnnvdgHeImIA7vqyYNQYJKgpIpVcvNowv/0y6WKXBPdOkQcJQSMhpROAmqYROO4ytM2kDRoFqzLFAqqaqhEhAoj2hwRV49T42AbyTtPjRUzVjMxoaqKGiEwoqqJGiIjwUs7g2enZ559/cev41vvvP/gawd110naurtC99jqniEbRsnj5C4jIkQODEIIZeO/aEJ+cnKkZIl71XiOCY56Mhnvj0eVieTFfIKJkSZ3JgjvzxwflpyCTyXzfRNXVut2sWioKP6hA1TpBTbGBaG1nm44UNMYYuiCxk84xjoeDpuuenJytm/b/z96fx1mWXfWd6Fpr732GO8aUkZFzZc2TSqW5kECSJYOYhAEDUtuAZcBAv/bU7Y/N83vutv0xhm5jeM3UBslmsJglQCALDWgqSaWppKpSTaoxKyvnzJjjTuecvfda749942ZkZERkZGZkSSX2Fz6lyIh7pn2G+9vrrPVb64TgwtLK4nJXBFa6vbnF5VPn5o+fmi0ri4hG6yxNEmOMMURorQ0Kr6zs6dmF2fmldRFWTTo3eaISZq58xcKbzBlUoo2AWHbhMyzshQVktIgIAyCu6VjD3guzSo3WhBh6LkJo1wgISiERht8Euz9gFvZahZxwCX3lmWX1wyAgRGg0hWVXtyshK/qxx77667/2/9z/xS9d4nxI6EqEwrKF2u70iqXl7qCorPUXiHVm660ApGmqlKoq670PfUNVmEmsiekkxtTzrKiq+aUVZtmO2kbEeMtEIpFvtMBTHIJIJPLCaO6itFqrNDPsGZw3mAGAtyWkRicaENn7qhjoNGXP3apvvRw9cbrbL4zW1rrQfrJRqxVl9ehTzxljXvPS246eOHNublEr7ZnTxBijvHW5VqhU1REiHBQVgOR5trTSe/b5E+PtZr2WO+fKyuZZ2qzXlCIIFXuEW6g9EfHsWbwwA0iiEghd2QEVEpECEQeAAL1BUZW2Uc9FoLPcUcyt8dalFDAMinJ5qcOVRUU6L51nQKzl2fzicj3PJsebWo/i9NwflP2iQMTUmFqe9vrFSre/b2Zqamrim7/5dS+5685Lng5hBhZKzBaCu6ystX5+sZulpt2qmTUJ3yxc+SrFRCliRld5AGAWZrdu0HqDgoWb9bpWynm/VlUTbRDtVorS1ACLZymr2GYyEolEwR2JRCKXg2fu90vnfZJopVXoHiOlBxEhBQqQSJxn51Y6g+dOnO30i35R1fLs3Pxitz8oyqrVqF9/cG8tS53zYfFhhkaCAji3uDK/uNTv9ffunhLAk+fmW43a0kqHRXZPTggAs1SVe+746cXlTlGWB/ZM33Bon1IJABAiAVrvEDFV6cWy27GrXAWICWmFGgAEgJC0Upq0Y1d5R4ACcPLM/HPHTt96w8E8S549drpdy3SWukGZJCZJTFXZyro0MUarQVEJSJ4mRuullf4TR05UZSUAjWa9si7P0l2TY195/JndU+PGHEqM9p6N0Qj4/Imzz58822zUEq2mJsYq606enZscb91+x+2333H7ds4FO+eL0rQbm30gSfREu7680h+Utigr7ECzkY9sv0OznspXqUq1NopcmpiqshsGzMvKifSMPi+4iZCINNHFglsrmhirA2B/UEbBHYlEouCORCKRyxXcwuKs90VhE6OzzCSJ0fUahOxnEEJSKQLA7Km5hU7v4J7p+cXllV5x9OQZ59z+memllc65uYXrDuwJ7ciHgFjnrHXWuUTrDvOZ2Xmldb/fn5kcW0HUWtXreX9QhIrDheVOniVZmtIavxFC0qQ9s/fsyWu86NmIiEgsLACKCAA0KU2hIlM8ewFWpASgKMtjJ88mWu2d2cUs3UF5/PRsp1/Uanm7WV/u9MrStpr10HkHASbGmwf2Treb9YN7p0+enhWAA3umF5c7YUOH9u02Ws8trAyKcqXb3zM9uWfXRFVVRHj4wMyJU+eePHJs3+5dk2Ot0bFsjbCIcypJdK229SeN0a1WjZd7ZeWs82Vp1/bZQUAQdOw1qSxNJrC53OlW1rkL/bNDF8uirNb+JqT9WOtCUvsFMwERa71SZK1TimLCdyQSiYI7EolELg8R8CKevXW+KG2WmlotTRJDSLJqHhIkGilCosSY1LjS2pVu7/jpc0ZrpZRWKkmSlU7v2KmzSysdo7UxeqXbP31urtvri8B4uwGArSzd3Wp0e/1aPSfEE6fP5VnqnG82alqpo8dPDYpi/55dxuTDpyFp0MDCa5OwRygkTcp6Wfe3YFQiAIRKkRIBEWg1awD4/Imz9VrWK8qiskVRzs4vJWkiIlqrlW6PRbRWidFPP3eyXst3T7Ynx5tnz80nidk10To3v/jcsdN5nobAthduNxsr3d6hfbtD8L2WpQf3Thutek+Wx06dJcLbbjy4rXPAzKVFTaQuXcOjiJLEWOdredJs5OvPJjALIGpjNBFprTrdfndQeGYRUUpliRER69xINocyUK3U1ES7snZhqdPrFxfMyjz3B1WrkWuttFZRcEcikSi4I5FI5EqVN4Bj7heVZ27UJUkMESJS8NebmmwvLHWOnjittWrm2fREu9WoV9a1GrWxViNJzIE900/0n3/kySNaqQN7pjv9ARE16jWjNTM3G3WjtfhaWq81G7UsTbI0GWs2iNAZDiWGe3ZPTYy11BrzE0TUFIy3N3YpCZWCF9oFSuUsAmQmBQDPvvAVgLQa9d27JkIvGPY8KEpmJqXyWu6Zz80tGq1bzcbkeMsYPSiqKuROCMAarW+9d72+IiLEWi1XRHumJw/tnx4MSgEoKzu3uLKw1BGBWp4VZbntkRfUSuXpJT8Z6iY73b7WasMxQcAQVkdErZVSpIiMVoOyYpE8SyfHWkVZnZlfGH7fKJVniWc2iSpdCSCNelaUVVDVRJQmWmtqtXJnfa9XVlfXAQfD1E2Ar4EZVyQSiUTBHYlEXhywyKC0AtAQSBNDKAICCOPtxt133NgflOK9VFWzXtd5bVCUeZ7W8wwADu6dnhxv9fpFlib9QXFqdn6i3br1hkOIIgKhvA8RjVJGU2JM3qhPjrfLqiJErRUiiUijnmdpcl6JinjP3vsQrF0nMQlRkfLCQXOHv3r2LGzU8EHqhT27JDGNWr5392Rl7ZFjp+t51mrUmvW8V1REWMvzWpZU1tXy9OzsotYqz8x4uzHcYaMSY4IubjfruybHrHW1LCNF3vvUDGscE2Mq67769PNFacfbjXotOzO7ANvz9hDnfVluR3BX1q10+kpRLU+b9XxDRUuo1v4zSYzWqmZdGEMRURrHx+orK4PQ8L7drFfOKoXeMzMjQZ4n3W4BAFpRq1UzmgiJEhwbqy8t96z1oxkOEWqtqmpbKlwpyrNkdCDbXCoSiUSi4I5EIt+YFKXNkjRPyDkHwfVDKEtNlhpfVuyTJK+lSVqvZWu1XaOWN2o5APSLYtdEe/fU5NR4a30cViTVBCJKq8nxFgB4753zAEJESqm18WwREeFhWPTiZyVpMhQcu1lYoQIARUSYEBELiwCLR8CZqcmxRqOWpzdet3es3TBag8igP9hNpI1GgLJyE61GlqeziysCMDXeatRzYTZa7Z4Y04pWuv1BWc5Mj99yw8G5+eXEmFot7fUHaWJAgBTt3jVey1MiatTzsVajKKp2s65oWzavlBgkEs+4ZUqJZ66s00qlqVnrT3Lh6IpjGwxbzq+fSGvtnGVGQChdRQonJhrAOL/YOTu/5L3PszRNdFnZej3N06Hgts53OoPJ8QYAIGCa6LFWbX6x63nYuMhoNT5WX1jqbUc9K0WNeiYiaWLKys4tdGJ2SiQS+RoSG99EIpGvPfU8a9ZzEQFgY/QovZgr663VaZokKZG6XIdmtrZc7qCibKy9tqViaE4ZeqdTsMIGYRZmDwBKabWJGGVhEVlXnujZO/ZevGePAISKLtpPrixbh4TiPZJia1EpVKSydLhjLOI8F2VZ2RNLndnF5cOHZqanxhWSAODOuVOL91xaIFJZssXHBkU1t9CpZcnkRHPTVYkgYmay9Srcusq6NE2QoHQlAFjn+oOq0ynWrSFNTLtZW+kMiqoCAGNUu1XL0ySMR69fLC2f7/SepWZ6ql1W9tzcyiW/uYjQGMVexsbqzDIYVP1BGW+0bzxi45vIi4UY4Y5EIl97eoNiUFZZYjKjETFZ1buUGAGxRcHMaZZrdXmPLDsYVP1e1myta2AeEo6996McEmYfNK0IqM3dPgjp4swNAfHsAAABCZE2UsaUGDKrCeKICjKuLFsrzBi2t7pQaszN1x+4CfYzMos48QgAgBrVjgw1EqFWwpcO92pFWWYuId9BLnhL4H01KKz3AsBGK1JGGef9YGA73WKDE2Rdf1C2m3XoQllWzvHych/akCSmKKt1i7BIVTkiylJTlNXWkptZytIBwOzcilJUq6VJomNiSSQSiYI7Eon8jYaZ+0VprWtRpo0etVFUSUKkvHWuqjBFQoLVjjOXDPqSNjrNUG8QrkZErbXW4L1nZkSy1oZQt4gkSaLUZTTiRUCGoe4M+7ZOlYKEGr7zv0dFyArWykYcfZyRUKFCYBYhxJGFy9UiIp5FBFhAYOu07yTRtc1TvUO2PQg4dkYNdbmrqsHSImgtXhQRSmLSxFa+0x1seAQs0u0X1vlmvVZUFkSs8ysrg1YTB/1q3f5VlZtf6kyMNVvNvLJuwxQRIjRGY3hh4Fhrcs5rTa1m5vN0calbRs39DUSo6IhEouCORCKRy8N53xuURJRmhlaTklErsLYqBsH1GRUxiFJakaItZbcwqzQ1tfoWW1RKKaUAIF0toKwqW1VVlqXbzOLQpJVRXrxnZmG4UFoKgGcGkPXe3oggwtYprdfp7Q3lLexERgk7L9ZRmmB6iemEUmSMHmWrX6y2w0wA1kwGhBkQdauBiNVKzxYFipg0QSKt1br+8GspK1tWy+eFtXVzCyvBM3HgL1jKWr+w1KnXUt6kKT0RNeuZUoQI/UFVr6XdXqkIFSplYGK8ubjUZZar9D+JfG1RikQkS9N9u6fiaESi4I5EIpHLRgBK66A3YJEsS4ZxbgSVpkrED4rSDSgxSOiNJ6USZTZoUrOKqddcUfiq1Hl+GY9FrQDAWqu1pu1VIiKiRq0p1BE6xx5W49wizMIhML9+GaUgGHcPlT2u09sYslx2bHCH28JtHFRi9No2N+v3HRABPHtCYgYhARZXFK6qBDwaQ0TA7AW894Sold5CcG889XKhvHU91vq1id0XLzW30EmMHmvX63mqtRpv10eTBKWo2cgr66LgfpESXrnkaeq83z05HgckEgV3JBKJXLksLCrHPACANDNBi2KwoGvkGlA8+6ryRSnG+IQQkJAujkYLM1sHLKgv70FHRFqDtbaqrDFaqctInl7NG1mfVYIbfRK0EufYezq/hwjAw5kHBl0rnnmnKiaHynMnVoYIBERIAuC9k8r6qqLEKG18r3D9QTY+Rkb3+4VlPyhe0ILFyrrZ+ZU00e1WLU0MrIbknePZ+ZUdHczINVbYWbr2Ltq/e1cck0gU3JFIJLJzmsn53qBQCk1iQv92EEFEhYiKVJpKry+D0gJ441Odrst8EO99Zdl5MlqlyeVunYiSJKkqa+3QzGRz9Trcu3Up2qNM7tAdZkOJh0QswEWJNUJYleiy+l8WEAEQlJ2QyCLsnLBQlu7ICcLhEaMmBaUrl1fSdouy1JUDADD1XGUJO2+9734t7EFEpKzs8kp/rF03RoUMHgC4RqWTiKiVUorWNrGPXLk0USoxGhD3x6SRSBTckUgkcm01d+V7vbIOmKYmRChHYWMkNM26sPiqQseoQJhHmRIi4opSmE2jfsXhzNDGxVpbVpUxGnGTOLqI9dazT1QSTFQUKRa23oY5AIZu5iAXF1OGAwEBriyF9BIEEAHPodBSmIFQKXU1WSXCAsLsPJcVIG7tBnj5ax/6l4fXDpAaUko168LMlWPPiVKTzdrcsq9CseYLqrmhrNzScr/ZzLLEEFJiaKxdn92Gq+AVXC21PM3TdNYtRcPvq6SWpbU8m2g341BEouCORCKRaw6L9IsqVMfpROHFjnsEAMDWFdxXpLQxCIiKOORpqKv10UNEAXDOeXGoKFFmZMdxfheQCMmK88J6VYIzs6yWOQapLSICcLH4J62xrsQzOxdC2uKZiwoExHt2Do3WjRoCgQyzTLYnslmcDz+M/kmJocTssKgFcezRUDoxZvsD9g4RBUQQMNEilVQVVtVElnRZKufL0MT+hdPcUpSV8258rB66imqiNNFFucO7wczLnV6n10+NGfgY5L5yqY2IsRQyEgV3JBKJvKAIQFFZ6Eq9nqRpslZuCggzQ6IREJx34m2vJESTZuA4yF7x/nITuNfJNWYWECICEN4oLBo8OggRQLwwrqpwAB/cABmEmYkUhUg3XqiaQ1oGESgSxywWCMV7YUEiShJxTpzHsGVFoHBb+22dLyoRFudVLdN5BtcscTk0DfLsVWKAyLNXSEQEgDpFBsuVhaKcnp4qPZ84O/fCX0XO8dJSf3wcjdZKU6uVF7PXRPczyyCmlFwmRKQItdYIsH8mpmhHouCORCKRr4nmFikqiwiKFCV0QSf2YYAZISEWFk1AJAIqMVpnSHSVm0bExCQsbK1VmjbsPCMiLIyIjj0LwzB/BCC4AeJQfyskFg5ZMYQbRaqJUCMhYmqICGTomc0D8f1C5emqpQlcUjqz8+y8ylPUSjyT0df6BAkAaYVePHsACLMLZCyt1aQky0yjBkjO26/VVWSdX1ruT0+1EJCAVmc6gIhGqaKy8Ub72kgQrRp5nqVJq1GLoxGJgjsSiUS+tpobitIBFI06GKMRg+hEWlOnSEiKUJMOanWnnCiUIqON90xCBBs6UgOsFkcSEgB68AISItcKFQuvdmZHDOnOoDbeO0IBHKaeIAzXoZXvFOA81TJMDMKaIDduon+9B4SQPXL1s45tzEsAAFxZVcudZNe4VtqQBgBbFVzZvN3ERh0AKuu6/eJrehmB90IakDDPEkRQSmmlmvX87PwSM1+ucWHkajBaGa3rtXy81YijEYmCOxKJRL4uCJ5uzjKBJ0JSCgkFQqo0rm0Zw8wiMvLyw6s2+EiM0UpVlfXO64vywhUSKG29sHjPTIgaVYiLD/O2BTUpFkGACioWJryEeAUaZn8DC2qlapk47/sFMVOWrtaNItAGByeeAeAKjFmuQm8jiABhMtFGQhapXKUYbX+wruHmC1w0uQ7r/NJKb6xZN0btmmydn56Im5xoeMcLS92ouV8AlKLUmGa91m7W42hEouCORCKRry+yLGm3mkYrZq4qi4LKGOctD809gIFRkJCcOFg1ilCkrl5zE5HWKjSBv9giUCGBMoTIIoSUKAMhjXu1OX2Q0CysSCN7z0y0jQg8DhvQK6XEex6UXFkQIK2ACLUCoPWaW8CXpesX6eTYC3diRNg6rqyp5YhKmG1ZsGVAACI8P0VBegHC7VvtpgwGFXuZmmiSQgQUEBZmEAQ0Rk+ON5dWeuxjH8prBRFlaZKnyeRYK45GJAruSCQS+XpkpdvXSk2Nt4nIGOOcY8dEisV55lEaCQs770VEoQrJ1Jp24EGnlGJma22SJOvyVUSEAJG0gGzYCH2oNpASRRbAskPB4OYx7EYJAhsG4wkBEESQUGmFleNB6QYFEOlmHREACGjYJV6YhQWVSifG8IWStuLZlyWIqDQFIgldM50vVrq1md1IGKLaYeJQz9NOr/+1vYqsc8vdfr2Whj6ahDRKqU+Mnp5sW+cWFrvWMXN099tJ8ixNjZl+IaeCkUgU3JFIJHIFOO+d81orpUiEysqyMAwzugEAvPcheVpEGFhAUFBErj6lGxGNMdY655wxZiS1A1s3xzkvT0EEQKNSSrMwMxMCCHjh0Lhxg5QLAgAEBmCgRJPRUlauX3BREmaoABggOCFaC4DCrHaotc025Lb4srQrPdOsgwjLMHOdjNa1XJgBqCxKBCBFA+uWOr2v+SXELL1e6R03GhkAEGKS6LUzHyKaGG90e0WnW8Q7bmekdpogYnQgiUTBHYlEIi8OOt2+0Tq8j9Zae+aydEPPCRgWUDp2QdSGXjni/WqvR9xQdstqbnHQzZt9DFZzxZ3zSmkiDOqN2eNGDXE2EagCAIlOQnMch8jMDEKICOjD5GHDJQlDVgqwQGKUCBel7w9ULQMAYEFAZQwaAy9g23LxjETZ9AR4RqMBMdMpADCoygmKsHO2P2AR57krYt3XRYa0iAyKalBUiJAlyeR4y7FNjIFhW1AkwjxPur3ia5pz/g0CIR7YMx3HIRKJgjsSibxYSZMEREpbhZyAIJYJaBTSVqsS3LHXpFVI3b1QkzKzZcfsWUQRGWU06s2EmlIEq77aAECEAAoRibalc0NWyehnTdqKUyiatACgtwIgwlssDwiIhJgCoh8Uvl8AAGpFSoFW4D0QAV1z0S2eg1l40NxIChBCSjRACMeL73VFK/FWkUbEiVq+PCiKyq7OO74elDcMyurk2fk8S6YmzrcEQkBNKkl0WcZk7quS2kSUmCgzIpEouCORyIsN79lap1RorQJpmiJhWVUSfK8BZNiGBlZbPUIIWrN49qwwZO3CKJId/gdxtchRNtDZQcGLiLUOEbRetUBBVOrK1S0hpfq8nYge9oR3vNpAZwOCOQkIpkZpghA9riz7EhNNSUKJBq2uheY+n3fB4ovSF6VpNUKj+GAPLgCFKwFAmDEziTGsgBPDZeU7A7FVvVlHBM8izI4lJEkTkVb0NaxTFBHnPSKx+NFkTGlqt2qLi72vk6j8i4ssTRDAGJ2lyVgzuv5FIlFwRyKRayBfcNUee+tI5toWNhv+lVkAgFYL7wK9wcA6127U8ywFAKUoMYkw9PoDQAlSWAgZVlubBAktEvSiZS9eEEmTUqQAIDR/ZBYiREAGWQ2Qiwgwi3OOmUPZHyIgXsN6REJSpNh72CI1BAEoeHwTCEACqp6L8zwofX8Akg2zyXdUc4euPQoJAMR7VCqdaAOer/gcTlQk9N0kRPDISKSUIq1FxBWlMdRSCaL2zIOy8iwAkCSmVa/NLiyFnpUiUlp3lTFwRaS1qra/HgH2InhBrr/Rany8vrjUi16B2wcB8iyN6dqRyAZ3x7V4t/fY08/GkY1E/gbSGxRFURJRliRZlm6daIGI1jkATLQ63zV9mE8NRVX1BwUI5HmaZekFNnoI7Xrdefbsd423EfH07Hyn2987PZWnxntGAiQkTbLajh2HDSCDiwYSYahfXP09ICIhhkhtogwhee8BhoJ7bWWk1mpUNHmNcOytry7tZiiw2nsSQECc534hzLrdAARQOzYxEBAf+mgCIiJ54dKqNIHh9EOAiEUQQ0/7CzS6JiWeubJoFFvnBoWu1VxVKdJ5s6H1+qBPUVanZufdVcSVEbGWpRPt5vxSZ1CW2/yOy1IzPdVeN3X0wuLlzOyyxGzu7VF7wdW2MWkc9siLghjhjkQiO4O17tmjJ+cXl7M00Vrv37Nr1+R4YnRVWQBUivqDEkBqeea8ryrrvT964kxi9A2H9otwWVmjdZoapdTi0sqR46cHgwIR263mgT3TSiGzpIlBRBY5Wyw+f/xMUVU3Hd6vlTp1di5Lk727pwalXen2sjRp1DLnKs8eAEUw0ZoIB6WtKqs0Jcmw6lEpHdKyhznfpDUqEalsxcxKKe9Za50k5oUcyZDxInApxY1r2ryzICFogtKL9agJUHYqyC2rHYaCjEZFupaxdeIcAIr3qpYT4drYf5iihIg4KlJ5CiHXPE3YOfJeWHpLy83xMaQLS04RFJIDfxV7K5V1nnlqonXyzJxf9SVExM2c/oho3SkOCluT8sJ5nvT7ZbzBLwkRxdh2JBIFdyQSueYoogN7p/fN7Hrm6Imnnzu+0ukf2DN94sw5532WJidPz4rIoQMzK93+2dmFRi1f7nYVqbKylbXdXr+e59cf2rd71/iZuG6jGwAAvHpJREFU2QUies3L7lCKnPNnZuePnjjtPM/smkyM7nT7RDS/uASAJ0/POu/Pzi2kSeI99wfF0ROn983suuvW67vLi8ePHZ/Zt39icjLRGhG8CBI6x1VVBMFttDaJBpA0MaSI2RfOeee11saYi+OvLwwi4jiYq2w7So0YsqF9UQX3EiQEWaPIr24CEELXhOiZBcAD6zSBJBHhYQAbMajqNXu03u8lFHxSkoAxvqhcbzDo9pI01el5a/MsSXZPjZ+ZW9g6qxsRDCkg3PBjRqtGLS/KCgkzkyCAVkprPShDirlU7oJsE6PVWLsOq78RESc+NKhXisaaNe+4rGy8wbcmewH7m0YiUXBHIpG/uQjI4nLHOQ+AzXodQic/lk63z56np8aN0cLS7w8mx1q33HDw6InTRhvnPBHedeuNTx45dm5ucWq87T0rIiIMPhLLnf7BvTPtZuPk2dmFpY4x+sZD+2amxvuDot1qzi8u337T4aWV7tzicmLMwb0ze3ZPWc/3f/nBT3z0r9/8rd/63W/97lqWCoogEyoEcMIIYCvf65dlZRERPOR5rghZnFIqz7Ov7UjiqvK7DAdxBDRG1dH3B743UKqGqHfGJRBBAQ1/IPLsh8HsoYImVIqd48qS0RBM0IVDivxmelnlKaWJG1RVVanErD3MLE12T46fODu3VhOHwtZg9a0IU6KpRk2y9MzcYmVdSA0KWfhElOcpAGitpsbbrXpt3catc+fmlwZluVokQGliUFaz0Nc0IQp5/1qrifHG3PxKLKDcVGonCRLu3z21I2tzgwEZQzrqk0gU3JFIJLKxjgKt9Vi72W7Ulzu92YWlhaWV3mBARERUWZckppZnRpskSdI0JaSirEJ95Eq3x8xJliqtWs3aufnF02fntNZlZQGkrGyvP0BAo1WamFazxszLnW5lLYuUlZ1oN83UhAifOTd/9MTpG6/bd+ONN+ybmb775S+r13N2zntWmoJ1oAJUpPNGlmcJCwtAMajml5byNG3W6+byjcxEREBoh+optdJExMxePAtvqzX9anoJJook5dKK9ajUqrPIVeptZGDPnogISJFal9GMhAjgegPdyMkYAdnOiLF32nkhKYqyVssvvJAwvNwY/YaIEq1Z2GhdS0zKrBKj03TPrslzC0tKkfecGK2VIqLxVgMAtFIXq20AMFpPT47PLS71+kWSmNSY6akxz955F/K2V11uRuWzYLSammjGZO4NUYoO7t0xp203GCwfPV7fPZ2Nt3fk/UwkEgV3JBL5xlLbhPU8nxpP987sYu8BYWFp5eTZWUW0d/eUMfrE6dm5+TLbOz0+1iQio1Sjlh8/Mzs51vJETzx7bGKsuXdmCkT2TE955udOnEbE/TPTk+OtU2fn5xeX987smkxaQaO3m/WTZ2aLsmrW89n5pUGatFuNoiiLqto7PXVo7+6xW28AAC9sXSUoIlJVVmtNhAyiCBQq0MOe6JJJmhlFRFdk82e99eJTna7Rn1cFIQkKs0Bolr491R9yjxEQRMBx8GeBHYpyIxICOvYQphYXrpWMNs3asDBVYKvwdqhHdI6LSiqbTU9drGKJMEuMRfSeHbNSlGqdKhprNhGRna86XVOvAUCamAOXnzdstJocayHizNTE8LuQNCGVrlJICOjFefZGmdG+EVEtT/qDMkrudZdFLdux10EisnLiVGPfjDLGFQUgkjaIgErFoY686G+W6FISiUR2BKVUMPrwzBJc9oYtGCWYXsuwfG1orSGjarbV71oAYBFmRoTQWWZV1A1FZ9BzWithbtZr4+0mACpC5xkRtSJm9ix0YScaL75ylePQqEVAQGudZVko6fPsHTsWYfZK6Uynm0kBWM0xWJfmwcKVt9ZbhRQSl1OV4g4F51jYenuJOLesFjayF89QeV+VaIxu1oBwnV4XZhBBpUBEQqklbCvVm0VYmJBYGEA0rY/XcFW5fqHbjWBOstWqrHO9PnoBgWRiLEmS9cMlAAi+qnrLnaWySo2ebDeBRUTK5WVTr/uySpoNfQ0yf4aWLMyO/bo2Sc75+aVuWcZk7vPkWXpg5wolhXnl+Mnm/r1iXbHScYNBNjaGhDrLAAGVEma6UHxHl5LIi4UY4Y5EIjuDD0Z6I1EViuuu7HtX4MKVXUBVMQB4zyKiFQFA+G9IANAXhagVKkNGBEQJaRIvCDgyARERzx4AQgR3M9UbfPFYmFAlOln7OUIKySSj+IVll6idMTYJztze+dVdQ1xt7jOcAoTtehbruKzEeUSkLEOF4j0AARIMbQ2HYlc8U2qAhauKkgQAUCkg3HqSQIgIxMKEyBsFalBryhJvrUnSLRUtAKLKUtRag/K8xhGSg42jCAtpJZ7TxMzkme32qpWuMJNWKkmKxeW03WJ3TXrlIKAmDQRaeGALWqO5tVaTY43ZhY61sQPlMPf9wE7bkjT2zpBSoFQ9S9l7UspbW650SJHOM1eWpl4nophtEomCOxKJRF4Ilrs9ABhrNZQifak3zlppJBQBTUq0VFVVVVUIrGqlBcB6u7XqdeIqZxFREDz7dRFcQlRIIoJDB/CdfAOuSYPGylUiEmQ2IirSEmzGQ9jfi5QWnNeNGmolhCDAzop1qJU4J54pMSACRMJcLXdMPUdjAIGtk6oipSlN8FLW6QoVbNJUBxFBwK/0zVS6udoWFNCAxaA0DS3CQWYrAnbOFWWQ2uwcGVN1ukmzobOMiKpuL2k1B7Nztl+YRh0VJde4hWFo8O68V2uOVms1NdGMBZSI2G7Ud020d3a1bjAAJLXqcx+C2cqYfGIMENnapF4P2URkTHwGRqLgjkQikRfiK3+521vu9trN+tRYW12qz4tCBcPsCUzTtKqqwaAwxihFIfEZQC6Omo0yoIlIK42hnwt7uFBSa9JkSEQUXZNkU00KdeK8C/WIChUJigCGPA8RZi/MaDRqBYRICIBERpgBkNIEAYRZPKMiSgxKhkSE5NmTVuDZF5WUpUrM1eTLKmOopbZWsYAAiW5MTnprvfe+rLBWY+fdoNC1fK03hVmtpFRZmijFtnJlZeq1tNVINqqGvEa6ex1Gq6nJ1uz8ivsbqbnDa5AsMTuutkXE9gfZ2NiGWwWAILJVmrjKKgCldaxhjUTBHYlEItfyyaVU8BJh5rKy3f6g3axf1hqSJDHGOOfLsgpt2xl4bV6yiHjxIKCUwtCekkiEQUBAQlL12hyMi+sId1yOeGGjtELFznlvw86ERi9iLWjCPBVCGKbGCJJSWntmFlbBv4+GqS+EZMgoUg4sAJCmipDLynX7pt0cpqDQ5ZmuiGfX6wuL0WqLZVkE2JMiNkor5awrBgMtIgKbOcEhkU4TSJOJmxuXZ5V41aiNnGeMVrv+xmjuNDGwxqFSKSKkvdOTO74hts4VJXtPW9oE6Tz3ZTmYX6xNTriqStI8Pg8jUXBHIpHINRLcNNFq1GtX9V2LiMZoY3RVVbZySWKCmEZEz956G8rmEkgUKQRIlGEWB5aZ+36gaJjMjYh4LbW2iAAziBCgMDMAW+v6BVsHIkEEmUYNNDlgQWDh0KzeECkkDwwiAmt0KgIKsHgFpEghkmevlJYUyBi2TtiDZ8pSYAHCbSnv0Foyz2jLrpwiIsCI2nrHjsuiKjvdJM/Y2vru6UstKIT0gqntkLi/mdWj0Wpyojm/0PnG1tx5mh7YswtEXGl1dm372oiI0nrl2PGJm2+8xCwoTRsz0+y9+OiMHomCOxKJRK4Z1vMOJtEmSaK1sbay1hljjNEhM1ohCYj1tnQlIhllVuOdokmxcL/sEVGiEk36GglBYfbOsvMQmtQjsThflMKcjLWQCIRRKUD07ENfGGFRRFppQqy8ZfYsLCAEREgsIiKalCEzisqjUp5BQNhbX5RkDBBxWfmyoiRRqRmafG+uvEVAvBfmrQU3AICgiPT65amzc1VhNeJNE+O6Xi+tIyalSBEJgLAAAiIKs2cuqlJAUp1qReram8SFUloE3MJVMTV6aqI5942luRExWX3PQIQH9uwKo1EsLTVmpq/ppnWa0K7Jdf1Kt4CUSlvN+DCMRMEdiUQi1wpm9syXlk0hMBqUBGzqwiEgRCGx2zrnlCIEXPUlRBEBdgLgvHXD9YQ+54QKmbl0JSs2yux4qFuYvXO+cuwsV3Zk/4eKTL2mhm/eCRGRSAjYWmQGBBax3oWW7MEjMVRzhjix0TpRF0QrPXvrLCAyoarlI+c1ylIuK9cvVJKwsyrPETf2EEQE1PqSBuSIqBAr686cWzh9dqHVqDmBxcXlBOH4UqfZqE+Otybazcra5ZWe0SrLksXljnV+aaVDRMKyZ3pqaqJ9raPciJjohIULWyCSbNJAKDF6erI1+41SQ6mI8jzdu2vy4uHQSSLeX2s/bFKqe+Zc1o4tbyJRcEcikcjXASLivPee19VKeuZRi29A8MyVqzx7QEh1sk5lwihRO2RgA2qtmLksK2O0IYMIXnzl7apl+Pp8BgQMVZIsXLjSkDbK7OAxMrMws7W+PwABSgxlaahrREREGnn5MUvws1MU+rb4IBA5mB4irHZPBEVqNA7DZoqAChUZcuwcC6wmUbAIIOg8k0y4smwdUolaISm8qERVmLmsUCmlLp14sLjceeDRp/bN7Lrxun3PHj31yLPH7rr9huOnz423W4nRrWZtcWXl0a8+V6/nzUbtySPH9k1PlZVl4bn55TzLCDHPU03U6feN1opUaa0I1PM0SxNYk3B89bLbKOOFPXtNGjYq0TNG7941fnZ2yboXq1cgIiKC0bqWZZuVQqKiqtNNx9rXeleae2fY+9jXPRIFdyQSiXxdsNzpKaWmxlprFerSSrfyVbtZU6iIKHh4AIImrWiDx51jX/kKh9YLaJTJstQ5Z60DcFprUkik4FJmCAjIwi7YBSICoIRWNRia9qBcbo/1ILe957LioqI0UXkGwSiNiEUIkUXYOiJiluByqFGr0JhGwsaREAQJ8Xywf20VoGeuXBnmDI69iChUI09xBtaotNLOO0qM1kqc49KKL1SjhgJD2T2UtohabV3utubowHl/bm7h8WeUIuoVxfOnzi53e93+wGgan6iH9Ji5xaXjp87ecN2+fTNTX3n8WQQsq+qrzxzt9PozuyZ3T0189ksP75meqtez0+fmEeDQ/j2vfultztqTJ0/W6/U9e2auVv4BGmWUcBgZLxdIahYGQEMqTc3+3VMnz85Z719cvhmhFjg1OjFmenJsi48ljTp7vuZBbgFfVUmtHp9vkSi4I5FI5GuPUkRE6sKU4kFRWucSo1mExWGw0ANRpJLV9OvV1uerrUxICRjn3doG6lprpZS1lpmRaNhcJjRsgU2TUkTEiyusaKUBsPIVIWrSXjjYcgcLFFmtX9xafwf3Ea6s7Q9IK8rSYKENSALgPINnEUnTxHuPSLVaXpbW2ioIdVKUpIkiQkRmRxRa/QgiyWq/zLAdL4yCmrSIC2knI42lQSGgCBiVsDAoKUEIyZelKwopra7VkJCMFgBfVb5fpJuLtnU067WJseYzR0/sn9m10umJyCvuvAkQv/L4M/v37SLCytmVTs95ztIktItHAq31DQf3ZWnyuQceJURSdPjAniePHLv79puyNLn/K189fGDPysLsv/7X/9+7737pv/23/8eOXGyElJtMRFiYw6sDBJDwVgSc90YZY/S+mV1n5xatc1/noW5ENFoF03RjdC1PxzZ3NGeWoiyt81qRcs5bx2nCAkZRnmeIWJRVZS0CpmlSVVZrlaWJ9743KIejR5gYU5QlCJhEK1JFWa3dRGK0UlSUlbAYo9NWy9tK6+g9EomCOxKJRL52EKHRqtHIW426oaEzoPMMAL1BoZVqNWqVt6GTPAEgkUIVgrjBe0SR0kojoBd23sGqLUlCZtSwBhGV0tZaay0qZOEQH0ZEtYltRdDQDFy4YrXYToW+8c47RUqhGvVpNyox6lKPXxEAQQA/qASQEoNIzrM2Kmid0fQg/JDnlKbGOW+tA5CqsEp5pZR3DJqMUY69iBORMBMI1ZNqqBpdyPAOzdsvOC4Ivt6KhRUpQdG6xsJUq3Fl3aDQkgoIM6NWl3Ued09NaKWeePZYYoxSyjqPiEliVtsY4Xi71W7WH33yuTtvOYyIwe/Qsy+t1VoTUpYmUxNjR46fstYpUsZohVSr1b/5m1/35je/ecd1arqa1R1qTwEg0WZkJWm02j8zZa07cXbu61BzI4AxGhEV0f7ttYcUkbnF5YefeHal02u36nfefP3S0sqTzxy1Au00ecXL78yy5KGvPnPm3KLRdPjA3iPHT+2dnnr5nTctLHc++pkv12s5ItTydPfUxNPPnQCQmenJqYmxBx59qpalzNIvikYt37d7V5aY506crqydHG/fcWBPPdE6j4I7EgV3JBKJfM3UNrWaeb2WOu+rqqKEAGBppbu40kUApajdrBtljDKeufIVC+MafzfHrvJWCSOiJh0i1449CycqSfQFycdKEVFSVZW3bBLDwF5YmBn4Yqs4BFSIMpSwalSgGRyvQ+Vl4UoREWFEFOGtk0zCwkCk6jXo9bkoVWJMYkhtanGNiEoppVSaJsM4NxEiGmucs4lKjBInPlUJALBw6SrHjpAIkGEoH0Uk/BIg2I0LCStQsJoYrUh58eBBADAxKtHgBb03WcrWcWXR6OH+b55FrRTV8qzVqE2OtzrdPhFNTY49+OjTaWpuOLRvrNXodPuteq3dqu+ZnuwNiudPnq3nuSLSRh05dqrb7++f2T0zPbnc6TYbtev273nwsacSY64/uGdqckzR+L/4F//bWtW49p3GTsjulIicd7D61mItxuj9u6dOnJ1zq+kliKiVeuElOAYAQp2DIjqw5/JsRkrrPv7ZB8bbjVe85JYzswtHT5x+4NEnX37bTbumxh/56jMf++yX983s+uozz7/hNXdX1p4+N+9WTfpE5Nz8wptvfWVIWfnCg49dt3/PeLsxu7C8awI63f6rX3pbrze494sP3XP3HYvLnY9/7svf/KqXjrUan/vyI8tzC9/97W9YWFgYDAb79u2LD71IFNyRSCTywj6tFLWatWYjX+kMFpe7iNhu1hXR0kqXmSfazanx9lppnmHqxFtvQ2Vk5Ss3slUWCBLEC4LI2tj2OqGWpqlzrqosIKACQWQQ2lzihM7nF4ieIPVEJASPQ5ybHXg0m5sJeu+dtSAi3ouAShOdJoC4TfeGIL6H46YVIjjnjdEJnm98k2gDTkKkVkAUKU2ahcP/h4GiVUsWAFCkFCkRMWjCVwcLV67yipVOAACdd52equUAgISUJJup3Mmx1mtfeaciQpDXveolSpPR+tYbDgBAkmgRaTTyu++8ARGNUq99xR3OeyKFAALXAwIB5mnGzAf3TuVZ+pJbrr/1hoPMkqXrK1ZZuPJWIa12AA25+leuv0dlsltUxxqjD+zZdW5+qbIWAIzW05Njp2cXmEOiEIyEqdFhJgM7JcdxtUUTAqRpkiZGIY21GlewKhHp9gYnTp99y+tfPd5u7N+z64lnjtWy7FUvuwOYDct7PnZfUZZ3337jDQf3CMvhA3s+eO8X1oy8HD91jhD379m9d/fUU88dP7hv9+EDe4SFEK/bt/v5U+cQ4cC+6XPzi9NTE3fffqOIFMudv/7iQ9bzO9/5rvvu++xf/MWf02V2X4pEouCORCKRq1ESmOdJnicIqBQlRotItz9oNfKxdn250ye6QEJ5dtZZWHVgCH3dGRiRQnXjWi9nxw4Q1nZl9+wtO4VKk1Ja1bSuKmtdJQQC4ok3SyzZYv/hfKo3A0DlKlac6mS9+BNh79k58ewHhTinarnOM1QqRKyvYOiIyDlbFKVSSmslIkopWZNSopBApPJVWICAwn6qCxPlmdl7b4wJx+LZO/ajoaA0SZKEnePKApKvKkoMsAzD3UHqDqc7YhQCgPeiELUiADFmGEcHAEJMVusvtaZgygKjoDtiYQtCRIWlr1KVJBsVa4ZoPYg4cZWrwrWgiBQpQoXXsoOOVmpdL8aDq9Fl5/zZ+UUiBMA9uybCb06em2Pe2Fo+pFyvVfwAwp6B0HsWgJCQHcp2iTDLk2Y99+y1UpnOruaWS7Ru1PLZ+cXE6EFZiYjzvLDUydJkubK1PGvW8rnZ+U5nb7nS6QsCgPO+NyiL0hLivt27gCBJ9MG9u284uPeZoyf/+lNffNNrXiYivqpCzxoUqGdpUZSLC8vG6IVOt9WsE6FSeu/evbFxeyQK7kgkEnlBEZFur9RKj7fT8WZzrNl07Lx3IVc7yzWh8sxBHbKw9Y5BgkbTShOSR4+IhAjBUcQ7GUrMILzQsx/2MgT0wsxegK23RmmtdJIYACmqEjUGB491iSU8bIW4cTWkgHhmAQEBRCBSICDCzrtR0xwZOZN4L8zsnDCrPFNpgkRbJJNcEiIyRpdl5b0DgOSi3jRDD5PVQsCg8zQqRPTMo/C/yFBzK6WY2Xq7/s0AAhlNRvtB4VZ6ulXnskKjERC1AsTQkFK8BxEMWenOA4JJ9CWnK7CaugMAis6PGGySOh7Ocjih6vwhiPVWxBpltFJXEOqWYQHtBTt2GV+6Wu3bPbXuN4f27rbOnTg7B8OkeQpTCwAwSq1NuRYR1x+w85QlC52+c37fzNToT6F+AAA0Kd6GUf1WYw5Qr2V333Hzp+9/eP+eXcsr3QN7d++emvjE57483m6eOD376rtvnxhrffTT99svP+I9e+sQcWFp+bNffsR5ztJ0dmERAMrKnp1b2D05ISBj9RpXZUJYLq3Ybi9LEmHZ1258NUs//rkH22PNYyfP3POyO7TS//Jf/ov40It8o4WNroWH0WNPPxtHNhKJ7CxE2G7W2s16UMZBvRGSALAwIibqfAVb5avKWQRURKtBU2LgkcAaOgYGuS0hrIteWEA06ZD5TcFiD8Aoo0gxc1GWzlmVaEW0TnAPJbUIIYb8h3XizwsjIIWQuwAAhMxpTSrVKQCw964sJYQ6i1KcB0Jdr6nEkFJK66txZBMRa521VilKkoSIPPvSlQBAW0brtdJrM5W9995zkpgwXVkb4d5008xiHQCyc1xVul4jo73ztqgAUSnSqQFmILrcGUVI+8lNvqHarnwFcol5SKK2265cVv/PsQuzBgDJzAte2yfiKgsiKk0ulvsCUjnr2RMiC9eS2tVPdI+dOje/uDI53jq4d9o6fv7EmU6/v3tqYv/MFLPML62cPDObGL1/evLZI8dIa5UkRVkFQ/QwJ9k7Pfn8iVNEarqROZ0sd/u33nDg1PMnlyt7y6F9OksHRfX8ybODoti7e3Jm1+RlyRJj0vhsjETBHYlEIjtGvZ6NtWqKKMjrUIk4bPsyjAUaTSpk6HrxzMwiLF5EEClIbQHBVfk7csgGkaEjHiKA0JrOLyIsOMz5DlrZWc/MShMhIQ1f5YcwcFCxnkNRplonXASAiNZaeofkcq10ePUvIt452+25Tg8Qda0GClWaKK2V1lffe09Eqsoyc54PMw0cu8pVIZ4KF5keigiDJMqM8pVFxDkPIMYYEbHsHDuCi2VfqLA8/0WDF42F915YxFqdGF9VflCqxJh283KPSBBqG6leL7605dZzCSKVbK9RUai7deJDCnL4pSJllLlsh/Wrl9ze9+cWsrG2SpMNJwbWO89ORK5McG/WNmjNlMMHg6B12fBsbbnSySfG155zYfZlNVhYrM9Mh5aoYRs71UsyCu7Ii4WYUhKJRF4cDAZlYnSjnoUva15tRxKksIA4tiyekBDRehd0gwiwCIgnpODEV3kLIhoVEjKzFyFUw+aUQUSsURgCokDhmgRxY7RzLJ5FA3sfslSCfYdW2ihjvR1Vxa3VoCw+fH4UEg7R9AsSbUVQK0oMOz9S26QU7FDfRKXUUKaudquRYQOXocxCvCAXfnWucV5tW1sRKWMgTCqCk+BFilu8+DCNEYHR9CNkrQACszjHjrk3sFN5Zhp1laZ8oT3zFcMSUolQLjUa21Tbjn3pynARrFWi4SVJaEKJL2ArckTMxlqb9RhCQEPas9Okr2j02HqbqPXh85AQb70FASIaeCsiqUnXboW0Vsa4qhLnTb0WFrO9vnhu7Nl9weuL2Lk9EgV3JBKJfH3CLCiY6tSzc+zgwmzp1U7m7NgPC8tEUIap1YoUIlbODpXBas50f1BZ5+v11HlWSl3sVTIy+LvguakVe7SVJSJUEJrJe/G2soqUUhqZvawrrJQgtb1wKPsLWTFr+18Ks3gPAkikUiKtEPFqUrc3Qtam9mpSejUI6tgVtkAYquSQkwAAzjujdBgHrZWIHiZUIIiIZ8fCI9UVOg2F1wiazKoq9WG0beWq0iqtvOfeoHTMiLi00p8cb6xa2F2u9lwflffsB7ZQpFKdqM1bhA59IbeBX1XbF82gxHnr2BGi8y41GV5RSveVzSiKxeXa1ARsbhCZX1GuCwsPqkIRVd6G2YisnlXHjjnY7IQ7iDzw+jFETJqNqtvrnTk3dsN1SASIOs/ZeYxmI5EouOMQRCKRFwVB1A7sIBQmIgDj0LNirQBTQzsLWG0RKcMuixDiq0FQUn9QsgizdLqDXr/UivI8adQyQEHEkBq+oX3cUEEi6EShYHDnJoMESpFiYVsNgtHHumVXG6AjAKzKcRE4b8hNSoExLIJa+X4BgFgn9p5g1c7uqvUcERFRWVZZll6k0kgrzcyOPSJicBMHFBDnXcgqERHvWUBKWylFmrRW2vqhpd3IgCUUj66ZaSAAsOeiqErry+5AQEQgS830VHs0D/DWKtiWTJTVwSQgWjNHYmHHLsyanHcjf/GLVXqwONyO2i42UturZ3LYBUlQ+lU/NKTcYD93zgV8dBLTsbav7Kjn0c5MxUSsd6HsWEAqb8OpD8ehiNYdxcbGiIimXjONuu10k3YrDFN/drZ1IDpqR6LgjkQikRcDzUbeatZk6Bs9SinZJMgHyCDWOWFx1iNSmhoWr0gJwnKn1+0W54Uac8VcWdcflM1GrZYnXpiQiEiEL1IUgIAQEjCIUDx6MqCREBBBEJFCpaZjDxBCxRLCwETkvVPDZHEAAec9Ahplhv1ZlNLGeEQAFGu5sgDgrQVEpbUy5irHkIiIlNvI9RkBNGkkFFcKyGoJKQCCFzZDTRb+I04csDLKJCrRpK13IhyUJQIkKkXE0lVBBIc4qNKq0arpogIQQLTWhYYsw61rpWuXVtth+7KqZZVSaxt2ikjocBRKGwnVJisZ1stuDQsXtlSbhmYFQDx7RQphmF1T+Uou3JkQSk+U2cHgtwiIs7CjIl5ESl+tnmBh9mFCEmYvlbfiJdHGrzrZs0h2seAWEWZBNPUa6eEMjb2rz0zHx1ckEgV3JBJ5cUCoFFHpKhAIdh9BEwTlHcLS6xYZDKpOp1j7m3o9JcS1anst1vrFpY6z+Vi7HgTExbFJXI02AwILoyIQX1mbUaaVYmAR0aS9eBZ23pNSKpgAglTOKqQQ3yU8340ydIAnIKONhNUaJd75sgIVlD8pra/x8A59V3KTBZUc+tpYdsjovNNKM3vnvcn02iR1QtKkSucIQxQUiUhEiEgudKYjxCwxRitzUf6xWGe7/XRybGu1jYiZyTbTx3a1R2aYE3nxG6aCiADBdvsHbS188YLK0AtMCHBVrbLwwBa5yXZKcyOhStPloyfGbzq8I1I7xLO996OJ4rppRuh/RKiMSQo7ICTY6NWB976YX8gmxnWSqCwFAF8UVadXm56Kj69IJAruSCRyDUHE1WYmV4v1lfUmJOaOtLVnBtzY2A5hA13V65Vbb8UYnaT6UgcFIoKARicE6Mk79pWtmJUxBgFZhIA0ac/eswfwiBTsAmFkfhIkNwCLOF+JSKLIsavYMolBhUSu2xXndLPBAN65ncrn3vp8jJQ3ISU6JVbMQy3rvCdFIKAubMEja/SXY2crq1FrpR3wxYHYDYPLqLWuX8JSg2B9I8+1R+S8gwv07jC5aL1kB8yTbbWDCTMHZg/DH3hd8pImtb31ACIWtsh2TnMDkWnU2LrNSie3eyWAVL4KcWtFJCBO/NqXBkOhoDQAeHZefC2pla6SDc+i85Qkyhgw5zcQ1XYkEgV3JBK5toS2zMw7ILcVkVaKkIblhgBD5QoMAoI08sw+3zTkiqzHEqPzNLmEWsUhzFx6q0kRIisone0XBQKERjlJkhhlvHjnHTOvNQOBNTWCweWQiCpvR2KOQTBLDLVct1ctLFGWYgtBRCXJ1Q/m9mUfBSsPBQDgnLPeKTNMhhmlR4uICKvh+CMiJcokyoTQKXtZI3YBCZVC9kzqQhdzZi4rlSVbXgNKq42/s0L2Nl3KEVxt2wcwjFKm07WbKFxJV9wTHnHgikSZkIJytXeWUrVdk4P5xXxqct1IXt5eASY6Kd0wmYSZE2VGcyRcdbA5Pwjeg4ZUJykkF98XZbeXtVtrzqn05xdatZi9HYlEwR2JRK4lV9PrLthcE2Fw72g28mYjRyQAYWCUoWAN8i54lskaGUEIAKiVMkYzi/d+m9stCtszZaO+ad6CF1agAMCzv0C8ImhD2ihEVKCExTmnlAqhbgt22Dlw1Y8j1EqG9G5hCYcKCATExADIwCoxutnwgzJ0TUSlyPuraX8DIRfmiuKsoeRUoR6psZGUDL54zGy9G4W+EVGTEQDv/cjVZFhleHFCAgJuLhzDJGcLtW0vpbbD9gxd+VceIWU6LWxxSVm/6RoAw9TLKLMjlZTZWPtq1PZo6AkpOMkQUignXTWth8qVa3sbCcJmvuOImLWbQy/NcG+CxPB2JBIFdyQS+Tp+MClqN2v1i1RveJE9MgAhRC9SeTu0+QNBAC8sIkYZrXVq0sl2e6nTnV9c8dtT/6FhpPch6owbCS8cWU+EVPLR70PTeEQyWjOzrVwVrAMR0yT1xJWvmFkAglk4AIJ4QKBhkgoqIKMMIlpvGQGFQvKGL6uQP8Ai6qqH90pTfIY+jMGNRKMaaS9EVKBJMSGtlcWEmKqEiT0zIhS29OxR0HtWF04bEPAKsmVCEN15D5c6ojDDCXkdVyx2QwZ5OIlXLLtZeGAHinSItV/h5Ie56vaUMSq92jceCGCUrkREGBGdd5451Un4U6rTBKRyVbhmFFLlbbpJe07Uun92Nmk1dJ4jorBUnZ5OY2OaSCRMuSORSOTrjHotq9e3lWirkBAwiGmNioat09Gzl9VU77FmY/fUeLo9iw/veXmlf+rswtJK72JhSkgKVehzqZBoI7XE4kOtoTKUZSkROef6/YFzTnhoTwgACpVR2iidqIRQwbDoEx27YCVulDHakNaoNQKItaRUCPh/LdR2yIknBBQAo41Ryah0kpmdc+vU9gWDRhTcBrXSYQ6xLtEo9CPcYtu4Kq9ljXItXVnYIkRnt7H/CAgD23feCcgVjFvpqsrbYVPSq/neRRLhgR30bd96K8OGQJexK2ytGxQq2xkti4BD2/JwT1048wlpJ+EWY5HN1Pbwk61m1e27Xh8Awu3oyzI+0CIRiBHuSCTyog8bIBKq4K4gIIkyiU7WRTEbtdx7nltaZpbNFGewRFt1DoHBoFJEjXoWMkFCIxhmQUSt1IbBbxYJ5ZIeWEQYOVirIBrv2VUWkYTFi3cgXvksy4JlHoWmPAIsQgSerWdWpBJtSCkwImnCZemLAtIURQjgyqonvffMkl2RUCMiY7QilSoVutmH6joZCmFhlg2HJUjMRBkbUjtQANFVzmTmfF6KVrqRj9qsrItABzvwgR0oUohkSIc0krDmy1KWiMqzF4DtJ3Ovnd3JcMbEO5CHjQQAjn3lrSF9eXkmSPnkxE5aDYIoUtZbQtroBkGtFAvXknzr8TW13NRyX1WhViFtNTvHT7UPH4yPqUgkCu5IJPL1x2UKCS8+tHlHRBbu24EhnegLQnHtZl1rNb+4UlTrI6mI4L30B6V1Ls+SLE0BxDMvd/pLK/2FxRUWmZxozy8sLa6sNOq1Gw/tbdTzNDGhnyWdr4AUHHYVR0IFCCxeBEEwSZK1MjfI06qqmNkYY4xOFFpnQ8IJrBZVVt5q0lopnaUewPULdl7XcvaetL4Co8DQJPLKhFowJ7TWqlC9qkJFLFvrENGYS7Q3JySjTOkqJ54IgcE5R2oY12frqk5XT7RAJLiCrHP0C0MiIizOumpDF8jtcwVqGxFHrV5GHRl35EoP9abDPBNtLqm5RcQVBTCnY+0dudtYuPLWe0dEXjhT2cU7mep0VNR7yd0rO52s3QYi8bwde/VIJAruSCQSeWGVNmJilDGXl6isUMH52sVQMXlBddewQpGHrRDXbbEoq6eeO352diFPEwA8sG/3gT3T1jlFpBQtdTpFaYuyPDe3sGf3ZGrMM0dPdrr9l995c2JMp9tPjGq1akligvrUWhlthpWBiMwMAkRm3UaVwjzPmLmqqm63VEohIrAIQEhaGYXikQiVUnkGiLbXB8QryyVg5mH94pWfHUCktZHs0O9dba+Ok5BSnZAnACES9szsObxVUJQ06mobRY2hT+TVXGNEV5sGLyI73sQ95JlUziY62XrdSGTqNXF+R7bLwoNqEGolvbBR+mpnKQJZqwUsVbcLCEmjdmV+QZFIFNyRSCRyrWg18lYrh/NGFlf4RW29FZAQ5A5m2Jq0995dJFOIcG5hyVr3TS+/Y6zVrKxbWu585fFnZucX8iw9tH8PInZ7/aqq5haXB2WZGAMCy92ecx4Qz5ybV4puvG7fK+66+eTx4089+fTNt9x8/Q2HAYJ4FtyyMI6IsixLU7HWFWUJKIrUUBMjJjoJxhpIyJ5ZBBC5sipLryCTm4iUUszuis+OUkpEqup8Z3hEVJfjmhI0NzOXrhKU8zFj71xlMUsIrq0yC3Mw690WyvKSCrV05VWmcW8u5dl6u7W0FRFflL6srr5iMrS8IVIMYkhfHNu+7MFxznb7riyzsRYl2tRq8ZkWiUTBHYlEvu7wwtafV4SIqFDRZarukH5QeRsanVhfBUuQLE1qWdobFBfKF7DOIYDRpiirk2dmn33+5Hi79YZ7Xn7izLlzc4u1WtZs1Jr1mtZqvN1a7vS0UlmWjo+1u73+q192e1FW5+YWz5xbPPLskd979++/+VvfHAR32G0PLMzOea03FaaImCQmSYy1tj8YMIjWKsvSkOFdeVvYQgkqTWS0OI9EdEXmgKuam+kq0iGY/RXnpQzPMrO11qQm9BAKZs+IlKrk2mnZkcQU9gjoEEI3zVEy+jYXhxAj35FmThsOjnei9BaJJYioazkS7UDkWMCzR8BLJGdvc2XMneMn03Y7nxzvz803ZnbHB1okEgV3JBL5ekQRXUF+7QbKEgkA7NBTYmibnRhTr2WDslxnkdFq1BeXOyfPzk2Nt4sqqHPp9gfWOqWIkBg4OJMAAIIQgoh47ytrV1b6oZiyKt11193wz//Xf3bw0AFYtdQYaUcRBri0RDbGtI1xzjvnCAiC8ze7oR8fizgfTCqICK5Ic1+lQlNKKaWLosjzK5RoIfFGGU1EImy0QUAHlc7Isd+m2sbQ3mjbn79YN3vxxFT6EgC2KbhFpPIVAomIXN2kZctDw8rZVCdb74orCmE29dpVbque7FgQmq2r750JvZmy8bH4NItEouCORCJfr+xQ3DBUB6rVLuUjxpoNRTS3tGKtG+m/yfG2CDx99PiRYyemxsfuvOX6lW7vkSefbTfqhw/s6fUHlXVJYrIs0UpprVvNerc/WFhaadTzY6dPG20OH9hbq+eE+fTM7iwzzMLALBw6iHjx1jmt9TajwlorES7LKs8zQspN7shVVSnsxTpYrVZUlx/gvJqiyZFEIyJ3FQnEzIwAtewCva5AlYM+UrpZWx9Z7XqIgFrp0O3Igt1Og8nNdmPAhSJCQC9+s6bxFywC4tgz22B0eA1vAuHKV8kWBnyIpl67yhZIOw4lpn9urr57FwBE++1IZP1tK9fgvdhjTz8bRzYSiVwB7Wat3dqBkNvI2zioMRbx4jXpTKeA0O0N1mpuGOZaEACCiGcmRCJaG6XG9XOB1YpGgGa9pojOLSyFfyZG1+upViQc+mEiAprE5NllJMiGMDARam2CPPbOuarisuKiojzVeaaT5HKls3POWpfnV5Wqa62rqqp+RbFVZq4qa4xR61okiriyLLt91aozDNX8WiWNiIqUvqiqktkXriKiYZ7MZX6jCYgI5Em2HW+Q0lfXLpPk4r3aIs2Dne+fO9fYu+fra7Lsva8qlaZIL1yLD2Oiso+8OIgR7kgk8vX0nS0yagiP5+32rkSyrFVshAiovLhuZROVNOs1EZhbXPbMIejAzGsb0TMAnO8Gf4lo7kqvr843eEfr2TM06qnzLrjXGW30ZTYVJyKtVVVZETHGDMeBha0TYTL6SocGN7PKvoxVICBu1YZdRLZIt6CN+gW5shzML6btljEJCytSnv2afG5EpA3HEJE0KS9cS3IWtt6KAKBstxmkgGdf2DI32aWOGhNl1rV2FwgHq0RYk/bsd+g2gK2TqklRbdcuriwl5uvkzuXKdk6dqc9Mv5BqOxKJgjsSiUSuhJXuYKU7CD+3W7V280rCqF4YRNaZxxEgoWaQ4PLdatSM0YvLnUFRema8imQWa51DJCIAqeVpq5WHtoijtotX9iJRKZVlVJbVYFDUajkR6TQBET8owDGY1SO5TK0MO2ADspXY7xfl0kp33+6pDTQZc1VZpdTFcpyUMo06aY3BII9ZkcqT3LMXFiTSm3j5IeLIcJ2QEp2wMACWXGxnVubFI+LWKRwydHjcaHIoopXWpBSpIPeDHA8JMOpKqz/zbZQwemttr59PTiB97R33hNkWRfvQAYjuf5FIFNyRSOTFhfAVJhwT4GY+ybjael2RytMkn55c7vQWV7pGK89cWRu08eVK5MToZiNPU02ELCIiXhgFCZHDyhgNXfbzFhHTNLHWlmWVJEYAkBCVYuc0ZsAC6kpyuK/2vAhba5PEbGEIuO7EhS6ezCzCF+cACLMrSl+UwMLO+2JQdXvt6w4ioCYNl6NaEVChYtlWJ8jh+sO7lE0+z8Klq0J1JtH5kgCBkbnKhr7gQoCJTgpXrjU6FABmv7WP+LZsFhFNLVeJGczN55MTqL4WQeU1F1LV6ZJSUW1HIlFwRyKRFx8h1N1u1S7W3EEhsVy2F7UEwQjsnFOkUp22m/V2sx7+Oiir/qAoqqrXLy5rtWVlq0XXqGVj7RoCACIhAqBRmi4q3LxczU1Ezjn2fpiZ7j0ZPZw9XCYjI+0kuXIL55DuElpObqhiK+cWljuTY62gyoJA3yy2HQQ3EmXjY24wWDl2XCWmfejA1Vw5iKi18d559ojIIiFAzsLrEkI8MyHVNsknEZHKWwQIEnntXAUBCUlAgqlO+ORqeFsQMEsyFhZmISVhBxBAgIG3HltD280SQaVMs8HOEhq4ivyrKxLbUnW6iEhaqzQBZtNuxUdWJBIFdyQS+QbR3CLCIIYMIbHnTVX1ZoIGMQjV0MqxdKUAaNJBkOVpkqfJ4kr3cgV32LFuvxCQdrsWkpQJUdMOPGO11iBQlRWJuP6AFOl6LWRSX4ESRUTv+Wr2J/SlJ8IN/byJMNGaVzPjq8oys9Y6z/MNncjZuarbC8WlKjHt6w7oLLvKPGAENKQJkIVzkzt2YaoiLCyMhCwS8j2CTA1Fio4dApg1rpSIaMgUdoMu7gIiCIk63wAoVUnlK+c9gAQt7tiF7JvQg2nU03Gzi1Y2aqt+iXlFmpTLK26wpLM0HW+/MJpbmMV7lSQgwszcH6gsiw+rSCQK7kgk8g2iuUOIMdWpJlV5uy5geYEmDLpri2cfaUSsXOWZRTFiQkgIKCCIQIQiV5J7bZTeQWPj89KKEAn9oAT2utUIYe8rU1ciwHzlgnu1qhWzTdrLh72qKhsEt4jUaltlJKNSOk1tvw+IJs/Zewz+MAKAw+ZBIiAgtGbSta4uc8NKTUWqltRgjYY2ylSuIlIJqoEdrH5MD6qBVpqZEdCCDa8mIBSpslVEoQYXkZx3QUEjolZmbWY5IqY6Tdd8qSYqMco49tm25l0iAtWl2kxedGFQNj7GTdc9c85XVX1m+gVQ250Tp+oz0yrd1CRnTeYShonZBbMhGJ6pcCERIYfkMUJCXHsqmTlMEZlFQBCREFkEtqzKjUSi4I5EIpGr1dwM4sUDi/NbtSi/pBS13rIIIYVW6qWtAICIWFglsHf3RL9frXT7AuD9dq0nWo3a1Hj7WowAISoiH+K0zKD11uHti6cKOFSuwuyZxXtWV5T46z2XZbVFnnGamLFWY2mla60rimJrtT3cMaKqKIvFldae3VktKyvXHxTLnS4hHdw3LQK9QTG3sDSzayJLE+v8ufnFXr+4+fD+sAZmWVzpnpmdv+Om6y41jJSZTEQsu2CEokl59iwiAl5YIQWnES+eEEHAe0+IAlJLaiKiSGlUla+2mc4UYu2wmnMCiALD5o7qwglDCI0zk5AOaTAiEj7jPROt6s61ZxaBEBFRkOoz0+Xi8ugcbbgrO+IdjkStg/t9WQ5m52u7Ji++DkXk1Ln5ufllIsyzbP/MrmePn/JuGOzP87TXL2698VBi9GNPPZ/n6XX7dh89eXZxuTM51jq4d3p+aeX0ufk7b71eEz365HOTE+1dE2PPnTiz0ulOjY8d2jd9/PTs4lLnzlsOa63KykZbwMiLBfXv/t2/2/GVzi4sxpGNRCI7SFk5EEhTQ4ienfVuaHF90fc9C8tFFiUXf8ZLePUfwmoYpDwLh9UpokZeI6Juf7D9nWQWIsrS5FqMgIiIZ7ZeRCgxm0W4mdk5NxgUg0HhPTvnyrIqSxsKFpmZWUKI8YoFd8jGNkZv/hlfWVfLUwDYTrI4KVoclJ944NFOrz89NfHEs89/4aHHSalBWc5MTVjnTpye/ewDj9x0aD8pVVbV8yfPzi0uHdwzzSKe2Xs+c27+yPFTh/fv3abpoWc/Cp8DhuB0gqtukghIiM67kaLVSitSiKiQEFGTNspsfY1drHcJMFEJs9eklaJgkGLZKaTK+qeePXn0+TP9XllPEgB4/tS5I8dO7p6arKz90sNPiEC9lh15/vQjTz57Znb++OlzJ06fOze32KznInD/w09Y58fHGsqYorJfePCxk2fnjp+ePXrizIkzs6fOzp44Mzu7sLxvZteOzQC1VkniygpE6MLZlwCcm1/61BcfQsKnjx4/eWZ2UJZnZhd6g8FKr1/P87/4yKeI6MDMrvu+/Eijln/lq88+/MSzSWIeePTJheXOeKv1h3/xkXqez0xPfvhTX5yZnrrvS48889xxY/TnHni0qlyamPf81Sd275rYNTH+0FefObAnNpCPvDiIEe5IJPLioNMbIGKrmStUW5hzbCcLZMNCRoVKQEBEBRVOeLkJJda5oqxajdqOp9JiKFVMDDjvPHvnldZ4kSKvKltVNk1NmibGcLqm21/opGOtdc4F3Y2YaX0Fximracmw1Skoqmp+caVVz7e5UiSyno+fm288ewxCDgnzSqf43AOPPvP8CSIlIifOzN7/8Fd3TYx75rKq7v3CVwZFeW5+cc/01IE9u53zAlKWJbMYo7c4tOCobb117IkIAQGkXw1GUedVd21aO0O73GSPi87g0MwkXS3QDC6EqZairI4+f/ZLDz9xx82Hnz95upWoqZnphx5/uijKsUZ9sp4//szRp5878V1vem2/KE+fWziwd3evP3DOTU9NWO9PnTzz+DNHz80vXLfnHm9d5dxjTx+98+brQaSsqseffu6VL7kNMVSvSlVVzLJZOtClZ30glbOJNghIRouI7feUMevi3AhgjH7za19x+tz8h+79wg2H9rWb9X0zuxCx1aw3G/XHnz4yNdEGgJVO78kjx97xA9/RbjXnF5fe9Yfv37d7157dU1/8yuPTk+MgMrewdPz0uR//oe+u17I7b7n+D973kb/9La++7cZDX3jgscP79zzw6FPf9PK74rMx8qIgZkFFIpEXByKw3Okvr/S3Tq2+YqnLwp49gyCiF9+vBpWrLncly93eufmlne/gO0plFgmhbWftxWqb2Teb9SRJLm5MQ0RpmuR5nud5mmZlWRVFcUX7OWyds0XlZS1Lr9s3s2tiLDSA3M6pFeZmLds9Of6Vrz4zKCsAYJbZ+cVnj516/atfdusNh4qytM5Xld27e2qs1XDOV9YZre952e2z8wtzC4udXv/kyVP/9t/++x/7sR9/z3vee0nh6IFH1woCalKbZVwQKVkNfu84oVO9UmStc9beefjAnt27zpw8s7i0ct3M1FePHFNpphAnx5qfuf8hdrZWS1991621LK3X8ntedns9z55+7titNxw6N7d4bn7RDQoQIKSJ8fbkRHtqfCw4S6Zp0m7WO53uv//3/+Gnfuqnr0JtV9bbXtm33gGASkxSrxdLKxfPuAZF+b4Pf+pj93355sMHAGB+aeWJZ489eeQYeyGiN7zm5Z/47APM7LwHgDRNQDhL0sQY5z0ifsurXvrXn7mfRax1idFJqkU4S1NFxN4TUZ5nDz72dFDtkciLghjhjkQiLyZWuoOitK1mnmfpxXHkkFl7ee/6R7oKkfD8goZ0ohOA/uWup9Pvk6Kp8fYORrlFxHvP7ENtGSIxi3Mu5FKLSFlWzLx1u/VQjmZC+Fcr73lpaaVWy9YGwre5J5cMcgOAUiSiy7LM8/wSYruyviyVMbt3TWqtH33ySKtRDxMMIqzV0qxvjNYAkKbpvpldz588AwDG6Imx1sRYOzEJgwDAvn17//7f/3u/93u//4M/+AOXlLkE6IKXtsBmFXih5U2e5CIS+l9ek7gXqVtvvG7/zPT84vJit9d0bOr1N7/ulakxzaUV1PrVd9+5e3LszNxinpjbazXFfP3BfTIs4pT9e2b27p7av2faCqatJjn/yrtuNVoj4q5a7bWvuGtm1yQi1vMsTdO77777nnvuUeryvvoFxLMPBa5aJ8H+BRAVKUUKURHSyFiGRKYnxr/lVXdff3Cv0SrPsqMnTgPAeLsFAJ7961551+03H2426ifPzF5/cO+uyYmzs0uT4625xeW3vOE1B/fOIODdd9zUbjbOzC7ccsOhVqN+5tziWKuxsLTyHX/rdbt3jdfyfO/uXY89feTbX39PfCRGouCORCKRa0Jl3fxit9X0rUZtneYONttX34BDBJx4z25kjbJ9mKXbHyRGtxv1HTxqRBTPIKKTVCli75eXO0SklGL2Sulms37JNQRjPhEwRqcp5Xlqret2e8aYdHup50SotUJE70XtiP5kERGdpUTYatT2TE8sLncq60jR2FjTOf/eD3xCa93I87DpkFetiAiH2fekiIi0Uoj0kpfc+X/9Xz+/ncFMVKJIEVLhyotmFDx0MFwNayOiQnWNrmfn/amzc865zKjUmH5RLC53xpp1y76eZ3MLS4Cgifbvnnry6PGJsVawBxER72VhqdNu1suyEpHFle6eqXFEVErtn9nVqOe9fnFufrGWZ+EY8jx/+9vfdiXXHqBCVXkbBkFAiEjWDKavrF6TpoKIWZqMtRrhdgCAflH0iwIBx9vNei1HxIN7d5dVpZW69YaDx0+fO3riTKOe33L9waqyWZoQ0nX791TWaa1uu/G6E2dmnz9xptmoHT4wvdLtI9FYq/7S225s1PL4PIy8WMCdf/UJ8NjTz8aRjUQi1/bhhdhsZK1mvjYbe8Om7ldAcC9RpJZWuucWlq5gDe1GfXpyLCRze/ZrO71fgfz33nvr/KAQWyXjY6QUbal2nfPeu22GrkUkNKbZpuwOhZh5nl3Smk1EnPMikiQbZz8L+3K5M5ibpyzH8bEkMYnWZWWtc4gYUk0G/YHyTljG9uyuqipNk6pyIRVBK5WmptcviAgBGvX8smdHwqUrg6E4ITnrQ8C7LEsEREKjdb3eCOex3x/86Z/95fjYeFkV1rof+Lt/R2vlnH/f+9537txZEdm7d9/3fd/3VlX18z//82984xvf8IY3PPXUU+9617v27NnT7XYPHDh4xx23f/KTn3zqqadvvvmmN77xjWfOnD1x/Lgxxnr/lm//LsdSzzNg9gDzs7MPPfhwu9V88tmjr37VK171yrvqtdrRYyd+53d++9Ybb3z8qade9erXfOe3f9vJs3O7J8frtcx5f+zk2UYtG2s3T5yem54aq+dZUVZPPfv8H//h709MTJ44cewf/79+em5ubmZm5rrrrttiTE6dOvXMM8/MzMz8p//0Cz/7s/9hZmbm/e9//8OPPPIzP/Ov1t59o7uMPYt36lLVsSdOnHrqqWff9KZvCf/84Ic+tnfPbuvcK19x99af3PoCUyrGDSMvDqJLSSQSebGSpiZfX/4leNUt91gEkYJ5s3WurKoQpbssysp65lqeFq4MLnKIeGUtJ4VZmNlaX5SUpTpJCHHr1jDMIsLbrIkMMVFjjHPc7/eZRan1FiihhU2wNwk1l9uxHwmBWOfchpYmLFyxc96VSx2d6NbkREiEMFqliUkToxBdUTSztNao11oNbXRiDBEZo8MHjNGEmCYmMToxVyK8ggMJESnSCsg7ruU1rZXRJs8zo/VgUGg9bGJ/76c+12w2z547VxblTTddv7i4NDMz/cwzz5w+feYd73jHq1/9au/d2NjY0aNHRWBpaem2225fXFys1xvveMc7XvWqV33lKw9967d+62te85qlpaWf+Ikfr6rqxIkTP/rDP3zXbbd1ej0Qd9sNh+uJaY+3q07n0cefYO9tUdx+283dleVbb7vFaPXxD33ozW9+099609964xvf8NnPfHrfvr2PPPTghz74V8x83aFDj37loT9773vGJ8YP7Nvz8Y99/C//8i+KwWBmenLQ7/+jn/ixb37da6uq+tjHPjY/v+Cc/dM//dMsy+6//0t/8Rd/sWfPnmaz+Vd/9cHw85EjRz7xiU/s27dvbm6u3W7PzMx84pOfTNN0Zs/M7/7uf//CF75w3fWHn3r66Q9+8INfuv9Lhw8frtVy8Xx2dvY33/k7D33lkdtuu+VjH//0u9/9J0Q0OTn+Pz7wofe85y87ne7y0spHPvrJPTPTH/7Ixx977ImDB/Zpre777Bc/+KGPjY+1mXl+fqFWyx988OETJ05/5KOf3Ld35nf/+x/d/6UHb7rx+q8+8dQf/OF7szT94Ic+9pfv//C+vTOTkxPO+bIsr6ZnaiQSBXckEolcGs+ChCOltZkhIAuHrhnbF2ECXPlKBLznflFegeAGgCxJssw49gjBBVmryxfcwcrPW8eDQgghTbRWpNTWPtyXFNyjSPBoWBBRKcqyFBGLogyLh7Rv7733oXdksB1kETZGV84O7KD0JYOYTXq7MAuzN8asPR2WLQsjoHMWRHSW1aemHHDlLIfEdBHx7K1lZqmqwfyCadRBBNXO53UgIAKx56qySZKEyUZwXSSiJDEAw38++NBXROQNb3jdN7/unizLnnzqmZtuvP7JJ59stVoHDhwAgOnpaaXUvfd+6lWveuXZs+fq9Roz//Zv/87HPvaxj33sY29961v379/vnHvkkUdf8pKXHDlypNlo7NuzR+eZs+7o88/fdvvtCICkjh45WlTWMH/Pd7/l+hsOHzl6bGJsLM+yL375S694xSsSIpMkJ0+eFJbTZ07/xE/8xOc+97myLI8cOfJDP/iDn7z3UxMT408++dRP//RPPfTQV175ylcmifnVX/3Ve++995577imK8qUvvevIkede85rXdLvdwaD4tm/71o985CODwcBaG36+6aab8rx24MCBwaBYWVmpNxplVZZFeejQoW+65548z3vd3qmTp1/5ylfedONNDzzw4M233EyK3vvev/w73/ltt9x+yxNPPFMUxU/95D/45Cc/Xa/Xnnji6X/+z376wQe/cvDggVot2717emlp+W0/9H2f+/z9Y+0xrfWP/sjbPvThj7aarV6/Pzk58aUvP3jDDYeTRD935Pm3v/37DxzY95nPfL7T6bzuta9Jk/TZZ597+9u+j5nr9bqI5HmGGL0fIi8O4ruYSCTyYsU5v7DYdda3W3WAkMGNIlKUVgTyzIzEpQDQ5US9Q9IqgJTWWuevbPdWen0PrtnMCCnV6aXbvIuE1oyIoc8lY9h5Zl+U7Fm3Gp7ZC6irC+F3eoMTZ2YRIE2TqbFWs1ETkZVuf35pZWKsxZ6Xu73JsVZRdnqDcnGlRwhZmgzKChGNUs16Xs+zsqwYQrEieO8KKNXqa4G1sl6Eac0UyLMf2GIY7yECADsYuOWOaGAG6Rdpks6deY60qs9MO+/BGJ1l2fiY7fcpv1YJuyLsvc+ydKNO9USkvPda6127poX5Ix/5uLXu5ptunJmZBoCpqakvf/mB1772tQDwV3/1wVtvveXo0ecmJycQ8f77v3T33S9961vf+j3f89b3vvdPl5aW1q55anLqgQceeO1rXwuIR597bvf4RJjeoPD+QwePHj9ViH/v+z803mpa5vZ42xdFq944dvT5u+56yaDTPXXi5M2HrhtvtfygyJN0ZWmp2+s++vDDhw9fZ4w5cGC/1jrLsiNHjiRJ8nM/93MnTpz48Ic/vGvXNADUavnU1NTS0tLs7Lmnn376xhtvBIC1PweazSYzf+ELX7jjzjtmz537zKc/nWVZuz02NTWZpkmz0dBKdzqd4XQNsd5qGqVFuNlsAkC9Ue/1+ocOHdRahVSl4Gxz6NDBNYMwEf5knV3tLikA4L337LMsazYby8srBw8emJyYyLL0da99zZ+85y/q9fynfvId8QEYiYI7EolEXji6/aJXlAQoAG4Tcay1ajayWp4AICCI8IZW3Osoyqo/KK54x1qN2q6JdoglW3YgsFUatwh7H0z0PDOzECECinO+KNl73aiRIsc8GBQifFnWIuuYX1z+0sNP1PKsPygQ4XWvvGt6Yuyxp557+uiJl91+03i7+ZXHn7nrthvGW40nnj126uxcs1GbmZo4duosEg0Gg7Jyr7rr1psP7wcBYREtLMDs6aJOOt6zcz7Ps/NHCRLS2XOTefaFlOlYS+WZ7/bF+3R6MqckaTQoS1jYCFrrkiwFAFOr+7IkY67FJSRh/ynd5K8SVOArX/HS9/3FB1qtlnN2bn7+nnteCQDXX3/DF794/y/90i8x8w033Dg/P/+KV7ziDW94Q1VV73znO0ci+9u//S3vfOc7b7vttkajAQDi/fUHDz78wAO/8qu/mmVZo9F4/bd882fv/ayIvPZb7mk16vsP7f/KQ4/s3bf3+eePfftb3pzlGeTZt3/3d73zN9/58KOPnps994Y3vGHXvr1/9Od/ttzteudfd889Dz/66PzS4rFjx2655ZbRzs/MzPzWb/3W+9///pWVle/93u/13t97770hHn/w4MFPf/rTaZr1et3v/M7v/OIXvxh+vu222z7wgQ9MTU0CwI033vBXH/rgG9/0BgFQShHRgw8+cNPNNyPgn/3pnxlj3vjGN4YN3XzzjX/0x3+2uLD07d/5bffd97mzZ8/Ozy+89ptes7A4HIH2WOu+z38ZdXL44L7R7v3F+z/4xJNPj4+PHziw77/91u8/+ODDvV7vjW943WOPP/WKl931B3/43m63+/pvee3pM+fKsmLhj37s3l27Jur1enzuRV50xKLJSCTyNynGoKjRyOu1ZJsZ1Z3uYHG5dyUb0mq81RhvNUNZnvMOEAEkVWmikw0knfchkm07PVREWvuyEudREaWJylKVJqFW0jk/GBSIWKttWra4ddHk0RNnHn7i2VfddWuzUXvwsac7vcGdNx9+9MkjidH9QXHPy+988sjzzvnrD+578LGndk2Mn5tf2DUxtrjcvfHQvl0T7aefP3ns5Jk3fdPLH3v0kXvv/eTP/OufEWFjzLoQvmdflhUCpmkCCCGHZGALhWR0okmFz1SuCmktRCp0lvHs+3YgLMCQGJMlGQCwtVW3Z5oNFKm6/Wx8Jw2YmcVaa4zecDyJlPeMCGrnElqEmZ0no8OxC7PtD06ePeecu+GGwyCynanFwsLCAw888Lf/9t8WZtvrk9HCotNEAGhHc288+5HhZjiPn/j4J17+8pdPTEys/Vhl3dnZhUFR1mv59ORYUVazC0uHD+wJqfy9QXFubnHfzK40ubxZU1lWELy6N4JIxcda5EXBNUl+SmMRQyQS+brEeV5a7p0+u9TtlZdskiMipNCYK/lGRwQvvm8Hlasc+6FfIYBlV3lb2LKwZYhnh4JIYWbr3KAgpVSWAkLSbmQzU9n0ZNJuqjQhGloda62azXqSmE6nVxTllWs+AKN1nqYrne6pc/ODspwcbwPi0nJ3cnxsbnFldmFJkdq7e0pRaOQuSJDnaWI0KvrqE1/95V/+5ZMnT33mU5+pClsVdhS+cexWBp1Ot+vFVVB1y26/7FeusmyDYvPsAMCxL2xJSCwyUtsw9OITozQhAq+mmCsFgJ0Tp4TZ9vvVSueFi0shKkVXlse/wSUVRgkR8fz1h0RJvXbo0IHDBw8I8zYD+Y1G48477xwu3myoJEEiOyiQdvibXZHSNEzo16QVqTvvvDOE6teIcn7queNLS8vNZn1ppfPkkWOeeWH5fE+cs7MLvX4xO7+0ZiTkUhMhLooSEYyJb+MjL/5wz7VY6XireWZuPg5uJBL5+oRZlpZ7S8u9ZiMfa23Vid05tvZKcriNUXlmQMSJJyRA8cwIwOztUOmjoIRMEmetL0oelLqWU57CKEKJq9B625AkMYibptAAwNbFZMy80u3Pzi8dO3W2lmfn5hYGg/Krzxx1no+ePP2SW29oN+ornd71B/fqYW8dEICyskeOnT526tzUWOvVr3rJO//rb8zPzt94441aa2ttrzeo1TJAsM4CA2gQAgRc9UZkBEQiL8yuCq0KEdGyQ0TnLSEGVefZK1ACwCjMPnj2AQAqIqRypZuNjyPhjl4RApdTVnuF22D2ZYVK+bJEIm8taZ2MzNqDrgcgvd3v5SRJZmZmLlC9VQVyTQ4EEde+mVm3XRHpD8pOr/+KO27WiiZazS8/9uSgqEaDW1Z2YWnl0P6ZYyfP7tk9CSIf+MBf9fv9LXzBrbUAELrQe7/ZdY7xaRb5Gy24J8fH+kW50u3G8Y1EIl/PdLqDTnegFDUbeauRX6zCroxaLWm3agIAAoTKi1dImck8e8/Oswup5GBFg1JI4JmLirKU8nTosb2qtLfYChEFP4+LP6a1EtlUcCuiXr/44kOP5Vl2/cG9WZKcOjf3xnvubtbrR0+cfvzpo0VRTk+Nn5mdP7B3utPtK00i0u31H3r86cSY6/bvufPmw+y51qg3Go0Q+jXGiMjS0kqaJ17YlZ7FExFpEhKtVWpS733RL6rKKq1MqpEQREIiCgICoGM/qPpEJAgEkOqUHYejQ6K01UxbTV9V1Uo3HdvZnt6ISLKJVL2gFc5VzvS8J8Sk2RDm4GW9bidQX/mXchiiS4h+EcuWkC5RUXAFWwcINb7VSgdqNYDzPjoiMre4XK/lRVmRUgtLnYl2o9PpbJGiUxSlMUatjs9mnySKFiWRFw3XJIc7ML+4tLjSKasqjnIkEnlRYLRqNWv1WrpWkV9WDnetloyPNRSSgLAwy7BGMFEJApaudOwAgELnQs/IwM75QUFIptVQWpPW24xQBsO+0K39igTS2mnF2lbtuPp7HPXuDNkvIaZurTXGCIplm+rUrNFt3vv+oKiqihRleQIARiWlLcuyDGWgpIg0AQ/D+8ooQhSWILKZ2bMXEAREQQ06+PSdX39ly6VlnedJc8fK5pzznU43TZPaJm0LRy4l21yhMLtBodLEV5aUYmtZBJhVmqBSSOri6tIXhtChPbSpT3W6sytn5iePHLPOT461FpY7imjv7qmnnzsxs2vCM5+bX5zZNQEAzNLp9V5yyw1bX9jOuUtd1RjVdiQK7kgkEolEIpFIJLI6dY9DEIlEIpFIJBKJRMEdiUQikUgkEolEwR2JRCKRSCQSiUSi4I5EIpFIJBKJRKLgjkQikUgkEolEouCORCKRSCQSiUQiUXBHIpFIJBKJRCJRcEcikUgkEolEIlFwRyKRSCQSiUQikSi4I5FIJBKJRCKRKLgjkUgkEolEIpEouCORSCQSiUQikUgU3JFIJBKJRCKRSBTckUgkEolEIpFIFNyRSCQSiUQikUgkCu5IJBKJRCKRSORFgb4WK/2FX/iFf/bP/lkc3EgkEolEIteOJEniIEReFMQIdyQSiUQikUgkEgV3JBKJRCKRSCQSBXckEolEIpFIJBKJgjsSiUQikUgkEomCOxKJRCKRSCQSiYI7EolEIpFIJBKJRMEdiUQikUgkEolEwR2JRCKRSCQSiUTBvSN47x948OHTZ84CwNLyyue/8KWyLNd+YHZ27ujRYwDw5+/7wP33P7DFqgaD4pd/5TcXF5fW/nJxcemXf+U3B4Nis6WWl1f+zf/+H48fP7n9dW7Ik08+vbLS2eIwv/LwY+EDKyudrzz8mPd+O+Nz9Oixj3/i05/+zOd7/f66P62sdE6cOLXFss88c2TdYK7jxIlTv/br77LWhn+++/f+5NOf+fwlVzha6r3v/cuf+/lf+i+/8VsPP/LY1qf4mWeOeO8//ZnPb73+F5gnn3rmX/3Mv33ooUe2+MzKSucXf+nXtzizI/78fR944omnd3D3rniFn/7M59/9e3+y/ZWvuwzCGrZzprz3jz72RFmWs7Nzs7Nz626c//CzvzA3v7Ajj4hw/az95dz8wn/42V9Yd19f8oJfx0f++hMf+etP7OxFtf0LZkP++7v/aLO7KdyeF+/z2kUuOexz8wvvfNfvXnz4l1xwdBbCUhuelLUcO3biN37zt+/77BeYeTsHfvFFeAWMnmBbnIXRka4b6nWLbHiBrbvLRvfI0aPHwi3w8U98+t5777vcy/7i22f7N/iOP3auksu9ByORKLhfOKrK/tZv/d5/+2+/JyIf/egn//Mv/lqn2wuPxW63BwBPPPlMeK51u71BUa6sdJxzYdlut1eWVfi5LKtev7+ysuKZwz/D4p55ZWXl4s+P1t9qNX/mX/2zffv2rP0AMy8tr4QNjdYZcM6trHREBABEZLQ//+MDHzl16kz45dLyymhDo8N897v/+GMfvxcAPv+FL/2333p3VVkA6PV6YXER6fcHYbVh/8Oz/tOf+XxRFAf27/2VX/nNMC1xzvV6PQA4derM/V96cN3nwwfCzx//xKfDYIpIp9MdffMxc78/AIB9+/b81E++wxgTtg6rWx9tItDvD8KyYYWjpRYWF3/yJ9/xj37iR++847Z1+zAYFKPTVFX2Yx//VDjetWtbe/gjyrIaDd1oP9euebT4uoPacMGLN7F2qXPn5t761u+4++6XXDyGow21Ws1//L/8o1arORrYdWfq4kNYe4Cb/X7tUuu2u/ZANjwdm+3q+Z83l0Frtzs6kNEJvXjn1w7X6Lpae1X/+Z+/v9PtPfHkM088+czaHR4MBhvu7dYrXPub0VGvu37CCqs1QzQ6qM0u+NHVGMZ2dHm8+U2vf/ObXn/Jy3Lt5bTF2Q9bWXvBjP66dg0bnsHRHv69/+kHwt20dkNrb8+1+xwYLbJu2Le+hNauauvzFXZjdBbCUheflLUsLCy+90//8kd+5G3tdjtEK9YdzsVnZ+2zaIsrZMMLeN0Qhaf6utv24itzNG4XL7LuAtvixI0UcLgFnnnmyM233Pi7v/uHjz3+xLrH4BaPrLW3z9oDHF02a3958Q2+xdiGTaz75dpFtniSXLzs2st46++IqKUikUuivyZbbbaai4tLx4+ffPiRx/fsmQGAT9573x/84XuVUt/xljd94t77VpY77XYLAN71X393bGys0aj/m//Pv/gvv/FbJ0+eXlhY/Ff/6p8CwH/42f+8Z2b3mTNnw+Lvfvcfm8R88+vuectb3hSeDv/5F39t9PmFhaX3vPd9eZ476/7x//Ljv/f77/nJn3zHu9/9x8899/zBgwfe/vbv+9VffZfWmtn/v3/mf137pfi//x8/V9lqbm7h7W/7/je/6Vt+9j/+YlXZlU7nR3/k7Z+57wtzc/M/8iNv+6sP/vXpU2e7vd7/8W/+ZdDxgQMH9s7Oznc63Weeee7QwQPe+9/4zd9uNBonT57+0R/5oQ9+6KOtVuvLX37ox/7hD589d+7ZZ4+ePHnqe976HQDQbDavu+7gG9/wzV/4wpdvv/2WP/mT9+3bt6der83Ozj38yOMzu6dZ+HOfv7+W11760juUUn/1wY++5M7bdk/vuu++L3S7vR/54bf99u/8/uHDh5544qmf+sl3fOpTn3v0sa++5dve9E3f9Kr5hcU/+7P3/8gPv+0Xf+nXb7jh8AMPPXzd4UNPPf1s2ES73dq1a+p97/vAHXfcurCw+F3f9W1hhT/wd7/nQx/+2Bve8Lr77vuCUqrVbL7kJbfPLyyM9qHb6Z06fUYr9R3f+a1TkxP3f+nBz372i1mWHTy4/3/8jw8//fSzCwuL//Sf/ORv/fbvh8P/h+/4n6and83NL/y7f/d/vvrVLz969Pjb3vZ9jzz8eNjPtUf39NNHarXcWvud3/Gt7/qv//3gwf0nTp56+w99/3/6z7/ysrvvOnLk6P/80z82GAze9V/f/cpX3n3jjYc///kvrd3EYFD86q+9MwzF3//7P/jXH/1kVVY33nDdnj0zn7nv86MxX1xaHh31T//UP/z9P3jPD/7A9/7S/+/Xd++enp2bbzUb7XbLe//jP/bDf/CHf1qr5U88+fT/9s//53CWf+d3/zDs4d/9/rdmWTb6Pv6zP3v/q171sqNHj/3Tf/JTv/f7fzLaq6efOfK5z9/fajanpiZf//rXrh2BsOza0/H93/fdALDZrv7Tf/KT7/qv/71Wqz3//PFbb70pfE//1m//wU/8+I889fSzzz137MyZM6PtlmX5h3/0p/v3703T9Lu+69vCZfB///J/2b9/38T4WLPVQKQwXGGQv+et3/GXf/nB6647eMP1173sZXet00B//dFPriyvTE9P3XLzjU89/ezv/u4f3nXXHadPnwWA+z77hdEBfse3/+3NVjgYFP/x535x79498/Pz3/t3vivN0j/5k/ddd93Bbrd72203h+vn7W/7/jRN7vvsFz75yftmZqYHRbn2Jnr9679p7QU/ujZ+6f/+f17x8pe+6lUv/7Vff9dL77rzq1996oYbruv1+7fcfOPY2Fg4hLVjuO6yXF5e+Y3f/J0bbzw8MTF+9uy5xx9/8vrrr+v1ev/oJ3509Ml/8KNv+8v3f5jZT01NvvlNr/+T97zv7/+9Hxyd5R/4u29975++P6zhb73xm9eNyetf/9qf+/lfesXLX/qWt7x5anLi/f/jw7fdevNDX3nk8cefDGfnh37we9fenp/93P2e+fHHnvjBH/ieqrIf/sjHx8bat992CykaDXtRFL/5zt/50R95+5e+/BAA7Jqa/OS9nynL6iUvuf2uu+4YnbjPfu5+ANi9e9fF5yvcbsePnxztxuHDh0Z3sdZaRD772S8mSdLt9t7+tu8Le/IP3/H3EBEAlFKzs3PPPvvcS+68HRH/6I//bDRu/+D/395dx7dxpXsDPzNiti3JkpnZcRzbieM4zGmgaZKmjLvbpbu7d3nve7e73b3LzNBuuyljoGFGO7GTGBLbMTODJFvM8/4x7XQqQ9I22dLv+8kfzujMmQPPGT0ajaQH7/nb359mZ+cLjz3y0ss72XErmV904OCxB+6/a7oI8fl8/OW2b/+R6YaIPVc/9/wr7LLlBxW/p/v2H0lMiC8rr2AXSGtrh8lkevCBu6trrnABZjKZDx469tjnHtq950BWZvqYycQ/M08mk8mijIaNG9eeOVPe1zvAPw3yVxP/lPXgg3ezy0enizhzppyLPfZEvXLl0vr6a1yY7dy1j7/ACSH8hbz9zs3cIR59+P4//+VJrTZ83dqVO3ftYzd++Yuflcmk58oqDh48unz5YrFIdKmqhp3rYJDhzlFf+Pyjk/d94L67djz7MhvGMTFRMz9HPPa5h5RKBTIqgI/WFW5CiFwmTUtL3rlrn1qt1Ou0Ho9n//4jpQuKF5TMa2puK5gze+nShZs2riWEfObRBx7/329KJZK+vgGTyfzTn3z/kUfu27v30JEjJx956N6f/fTx7OwMr9d38tS5b37zyz9+4nuVF6smxifYi8H88n19A+vXrd5+5+boaKPRaCSEDAwODQ4O/+LnP/zud74aHxf7ta9+Pi4+Znh41GKxvOu1gUr5/f/3zcc+99DEhPXatWaFQvGbX/+4dEFxZ2dPRnrqQw/eIxQKm5vbVq5cEmU0dHR28/eVSqV6va7yYlV0lEGpVPT3D3b39EVHG9VqZV1do9Pp2nz7bUlJCVpt+Pziotl5OYFAoK6+kdtdE6YOBALHjp9OSIiLijL09PSVls5fu2ZFQcHskyfPpqYkR0cbq6pqz549/19f+syd225fvHhBaWnxgw/e3dXVHR0ddee22xctWlBTU0fR1Pbtm0tK5nI1t7S2p6Qk3XP3loI5swkh3CE6Orp8Xt/mzevvuXurSqVMTIhnK5Qr5ISQjPTU0tLi22+/TSgS+nw+rg21tXUikZBhmE2b1um0EYSQuUVzFiyYt/3OzUKhkKuts7OH6357exfbkry8nAcfuHvbtk319Y1sO/m9Y2sWi8Vb7tjY1tbh9foiI/WEIYNDw7k5WY88fG9BwWyr1Xb8xJkHH7xr29ZNYRpNyCHq669xQ9Ha0rFq5dL161ezr/FCxpxrJ3cNLy4u5rOfeWDVyqXFxUV33LHBbncEg8zm22/TRoQPDgz1DwyxxbgWctk2a8uWjffesy09LfXSpWquVc3NbeXllQ/ef9f9923v6upx2B38EWB35E8Hey1quqb29Q0EAsGHH7pnxYolPp+fEKJQKHS6iO7u3paWtihjJH80JBLJvfds27JlI/f+b339tbi42Afu375+/WqKotkt3CCPjIwyDFNYmM+9IcBRKBSrVi7dunVTRnoqIaSi4tJ99925aeO6qCiD1+vjd/DixaoZKoyLi3nk4XuXLl00PmE9dercli0b7rt3m9fri42JZuNHIhEHAoFLl6o/99kHbr/9NplUwl9EhCFcwPNjIzUl+d57tkVEhOfmZH3m0ftLS4uXLV204bY1g4MjXBdmCEuBQMAQJi0tecniBeygPfTg3RRFNzQ2cyUrKqocDsfnH3t429ZN7LzzG9bd3cfVwF44DJl0toXsYmHxZydkeRJCBDSdnp7S1NzW0tpeWJjP5rj8YQ+ZoPT0lKVLFgoEdFVV7eTTb8h88Zcbvxn8Vcwt6rvv2jJ37py6+kZ+SwghGo36+9//1tWr1777Pz8aGRnlj1tF5WVudi5X1XLjJpFKZw45kUjEX24zDxHvMsc7QTV5iGQyKbdA5uTnsnfO8AMspLYpz8yThWnUgUAg5DTI7xr/lBXwB9jlI5NK+bHHngBjY6K4jZcv14Ys8JBQ4R+if2BAr9c9+sj9ZrOF29jb99adk2vWrFi8aMHZc+e5ueafo3p7+ybvOzg0zIXxdZ8jkG0DfESvcBNC8vNn/fo3f/7Kf33u3LkLFEWLJeLEhLic3CypRHLs+Cm7/a3blwUCAS0Q0DTFvtE83R2EAb+fOx/x3/7myufmZD719HOJCfEP3L/9nTeOmSB760h9feMzO178+te+2NvTb3/3u2M0TdECgUAgeKtOn499H42mKYlUTAgRi0QymTQ7K2Pu3AKVUul0uqRSCU3T3DPf3//+zOcfe3h4ZFQkEkZHGdlrTkqFwmS2/PRnv1u6pDQ8POzZ514pKpqzZMnC7u5e7tDNza3R0Uan05WVmZaYlDB//tzBgSFCiFAoCAsLy87OiIgIp6kF/3r6uZCOiyUSrsGEEJqmaWqmV1ZqlYo7RF3dtRuZPoHgnTZIJRKlUjExYf3X08/fue32+PjYKXfhd1+lVPIf8vn8FEVRFEVTNL93bM0DA0N//PM/Fy8sSUqKz8vLyZ+d6/P5a2quTnUIUcghQoaC74UXX5885jNwuVzj4xOvvLrz4YfuramtCwbeeh/2vnvvZFv4xc8/wr4tw+f2eMQSMdcquUxWVT1FDsSOwOTpkEol77Wpc/Lzaq/U+by+6GgjfzQOHjp23X3FEgk3yGq1an5x0b79hxsbm29bt+pGTyhCgVgseqdCsfgGK5TJpDdSf0gU1dVfC2k2GxvcYPLZbLYbCUulUvGdb33lQsWlHc++FB4ezr6xHgwGxLzoMpssnV3dM9SzdGkpW8Ojj9wfMibsKE3ZwhnMzsvZf+AoRVHz5s7p6OiaufDx46dFYvGyZYsOHz5x3fniL7djx09ftyWzcrNefW03IVRRYT7/jgWZVHr/fXeePhN99uwFgVDAjZtE8k4MWCzjISt3hpCbmLDuePalkOX2wXELxGCIvG7hG1x67R1dBoN++fLF/NPg5LCc+Xw1dGiEpmj+RrvNHnIRZ4YFKxKJzp+/SFFUyJByZ+yQua55+6Msbo+HFtACAT1537xZ2WwYv4/nCAD4qCTc8XGxj332odzc7HPnLojFos2bbvvjn/8ZGalbtnRRWmrKj//v12ySzYmJicrISP3Sf30rEAg+/r/fCjLBH/3oV7vfPODz+cRi0e2bbvvVr//EMMzGDWt0Om13T5/ZYuGXHx4ZDfgDXp/v8JETG9avJYTEREdlpKd+5avfMURG3n3XHSMjYz/52W8tlnGapl1uz+nTZdu2bgppc25u9sFDxz/zua+KxeIfPfE9r9f7fz/9zXe/87XcnKwf/+TXarXqoQfv+f3v//a1r32h4O234OPjYv/7a18wGCLPX7gYGalXKhW7dx+QyaQrVyzp7u6RSqV2h3PCavP5fOfPX+zt7cvJyfT5/Dt37j146FhSYvzGDWsj9brnXnh1Vm52eHhYdnbGxYtVGo16fnHha6/tSUtLzkhPXbx4wV/+9nRyUkJJyVyZTPbSS2/cvmldf//Ak089Nzwy8sUvPHru3IWQjqSmJO7ff+TpZ16orr6SmBi/oGQudwixWBzyhulLL72xetWy0HdGaJprQ1pqckdnN5vXsgmiWCyy2e1vvPGmMcrAXffld/+2dSslkghCSH1D4793vNTT0/fYYw9VVFxmnxi4mpMSE+obrul0OrFIlJmZfv7CxaNHT9I0vbB0Pr8xK1cseepfz+flZSckxIUcIj0t5dixU9xQNDa28HLcd8b8xuPWbBnftXt/T08fm6xca2w6f6GSbeH4+MTPfvH7//e9r7Np9759h1pa2txud1FhfktLO9eq0gXFTz71nFQqSUtLUSgV/BG4fLmmta2dPx3sHbfTNVWv1wkE9JNPPdve3llQ8NalvqSk+OdfeHXFiiXR0Ub+aEzuS25u9vETZ3Y8+7JMJo2Pj712rfmeu7ceO3aKHeTExPjm5jaPxzMrN/sf//z37Lxc/psk4WGaV17dpVIq8vNnzS0qYN/jHhgcpmma38H8/Fnl5ysnVzi5MaULip974VW9TqtSKePiYtj4ueOODUqlYk5+3tPPvCAWi51OV0gUcQE/ODg8ZWxc1+Sw7OnpO3zkpEqlCAsL83q9r7y6S6uNiIoyZKSnXrxYzZZcu2a5QqH429+fVqmU69auCqknb1Z25cVqtgY2pEMmfeYmhSxPdqNOp3U6nXK5XKF4a3f+sIvFYr/f/8tf/dHj8WzYsMYfCDTU1nm8XqFAIBQKh0dGJyas3KvBkPnin0zelcy9exVz/73jjg0ajWZiwsowzPcf/+k3vv6liIjwgYGhfz39vEQqsVltX/j8I+cvXOTGrbAgv7Kyip2dDevXcOO2dMlCQgi7QqeLEP5yu+4QTcbvKbeRWyDsKUsgEPADTC6XDw+P/OSnv3U4HFmZ6fylJ5WIr9ZdW1hazH+xdPp0WWtbh1wu+9IXHnlj517+aZDftZCwZJfPljs2TF6hRmMkt3HN6mWTF/i73srgHWL1quWTN96+6Tb2DYqQUys719w5KjEh/vz5iyH7zpmTd+bMeTaMZ+flzPwccdf2OwwGPTIqgBlQ3IeBbqJf//rXX/va1z5S/Xz6mReKiuZERur+9OcnH3n43vS0lA+3PezHHzdtXNvS0tbY2LJ58/pPYfCNmcy7du177HMPfTK64/f79+8/smbNCvamSULIooXzP1Uj8MnD3sjL3T4LrP37jyQkxM2alY1x+/i6wXPUR1/ICwAAXOH+kBXMyXvyyR0ikWjliiWpKUkfenvCw8O6urr//o9/+/3+u9/+tNynjYCmFQr5J6Y7Tqdr+fLF7K0RUon4UzgCnzxymUwkEmIc+N7YuVcmk+XmZmHcPtZu8BwFADfLp+UKNwAAAHzC4Ao3fFzglyYBAAAAAJBwAwAAAAAg4QYAAAAAACTcAAAAAABIuG/Y7j0Hmppab1HlbW0d3M/ysQKBQFtbRyAQOHrs1NFjpxBAAAAAAPARTbg9Hq/H42UYxmazs7/dGAwGnU4X+6jf73c4HJP/ZhjG6XQxDMMvzG1k/+YqJIS4XG6/388dkf2hbJbT6eKK+f1+7iF+DSdPnbPZHfw2eL2+EyfPer2+FcsXsz9Kwm9eSFX8owMAAADAp9OH8FWpLpf7V7/+k1Ybvm7typ279sXHx/b1Dzxw3107nn05NTUpIiI8Jibqtdf2xMREaTTq7KyM02fKPB7vrFnZIpHo4MGjy5cvjo2Jfva5V4qK8tPTUzweD/tbYhKJZPudm//8lyfZCu/evuV3f/hbYcHsNWtW6LQRZeUV7e1d/f0Dmzaus4xP7NlzICcn02y2fOHzj/zil3+Ijo4ymUybb1+fmpr85788mZSU0NTUsnLl0vLySrvdsXTpwosXq9g2CIXC8+cvSqXS+PhYoVBoMOhfe21PYmK83W6//77t/KoGBoYGBoeEAsG621bptBEINQAAAIBPJ8ETTzxx0ys9f/78/PnT/n6V3+9vaW1/5OH7enp6W1raMzPTBweHIyP1be0d84sL580tePX1PYZIvcGgb25uW75iSUR4eFdXd09PX2xsTHJy4orli3ft3rdp09oli0sNhsjWto7lyxYVFuXX118T0DRXoVYX4XZ5Hn3kPoVcTgiJjjbSFNXU3Or3B9RqVWZm+prVy5uaWjIz0vv6Bx5+6B6xROL2eMxms9fru+fuLQxDnA6nWqO6++6tSYnxKpWKbcMdm9ebLZZ779k2NDxCCLl0qXrt2hXLly26cOFSdLTRZDJzVRHCjI9P3LF5fUR4GOIMAADg5icxAgEGAT4WhB/SCqEpihJLJElJ8Xl5Ofmzc9VqVd6s7AsVl3Y8+5JapcrKTEtMSpg/f2552QWxRLJs2aLDh09cd2nxK/T5/DU1VymKYh964cXXi4rmLFmysLu7d+YaJh/i+PHTIrGYawMf+7OCU1q+fPHEhPVfTz9/57bb4+NjEWoAAAAASLj/09LTUo4dO3X06EmapufMyTtz5rxKpQgLC5udl/PcC6/Oys0ODw8LBIO1tXUer1fIy4NXrljy1L+ez8vLTkpKmK7ChaXvusTu8/nOn7/Y29uXk5N53SY9+dRzwyMjX/zCoyOjYy+99IZerxsaGmbbIBaLbHb7G2+8aYwySKXS0gXFz73wql6nVamUBkMkV08gGHxj5142d/f7/d9//Kff+PqXIiLCEXAAAAAAnzb4aXcAAAD4WMJPu8PHBb6HGwAAAAAACTcAAAAAABJuAAAAAABAwg0AAAAAgIQbAAAAAAAJNwAAAAAAIOEGAAAAAEDCDQAAAACAhBsAAAAAAJBwAwAAAAAg4QYAAAAAQMINAAAAAAAfBMUwDEYBAAAAAOAWwRVuAAAAAAAk3AAAAAAASLgBAAAAAAAJNwAAAAAAEm4AAAAAACTcAAAAAACAhBsAAAAAAAk3AAAAAAASbgAAAAAAQMINAAAAAICEGwAAAAAACTcAAAAAACDhBgAAAABAwg0AAAAAgIQbAAAAAACQcAMAAAAAIOEGAAAAAEDCjSEAAAAAAEDCDQAAAACAhBsAAAAAAJBwAwAAAAAg4QYAAAAAQMINAAAAAABIuAEAAAAAkHADAAAAACDhBgAAAAAAJNwAAAAAAEi4AQAAAACQcAMAAAAAABJuAAAAAAAk3AAAAAAASLgBAAAAAAAJNwAAAAAAEm4AAAAAACTcAAAAAACAhBsAAAAAAAk3AAAAAAAg4QYAAAAAQMINAAAAAICEGwAAAAAAkHADAAAAACDhBgAAAABAwg0AAAAAAEi4AQAAAACQcN8Im83+5788uefNAx9uM+x2x29/99c39x5kGOZ97D48MvrEj35xoeLSh9L48vOVv/ntXwYGhhDuAAAAAJ+QhJthmBMnz9z3wGMbb7/3Zz//3YTVOl3Js2fPFxQt5f5t2nzv2JiJX8Dj8Rw7frqmpu59NGNszLRp872r127t7OxmtzQ2tixdvnHyUa5flcl8/Pjpc2UVPp/PbLZ87rGvVV6suvHde3v7jxw9VVFx+f2NJ9uRrXc+NDw8QghxOl2f/+I3fvjEL25w97a2jv0HjkxMWBHuAAAAAP95wltR6alT5378f7/esH6NXC57+ZVdDofzxz/6H4FAMF35hx+6Nzs7gxAik0lVKuXNbczYmKm65kpSUgIh5OKlKqvVplar3msliQlxu3Y+LxIJhULh8HBXa1uHx+258d2LCvOPH9stk0o/SEc6O7t37tr3xS88iqgFAAAA+LQn3EuXLpydP0sbEc4wzOiYqbr6isUyrtNppyufPzt38eIF/C1Nza2//e1fxsbMpQuLvV4vu3HCav3rX/914e3rxCql4sc/+p/ExPhdu/a9/sabfn9g69aNd9+1RSh8V6dioqNOny7fsH6Nz+c/fbo8MzPdbrezD5lM5r//45nKi9VqtfLRR+5bvmwxRVFv7Nx76XLNhttWP/X0czar/d57t23busliGf/u957Iysq4+64tv/39X+12x//95NeJifG//MUTarWKa8Dy5Ys+8+gDcrmsra3jl7/646OP3L//wJExk/kLjz3869/8ecuWjdu2bpqyfoqi2C4PDY+ybZuVm/X4978tk72ToxcUzN5/4OjGDWu12gh+B7t7ev/wh3+0tXcaDfovf+mz+fmzCCEej2fHsy8fPnzCYNQbIiMnF46JMf7P976eEB+HNQAAAABwS92SW0pomtZGhLN/+/1+mUwWkgSHqL1Sf/zEmeMnzrD3fvT29n/jm9/v6x/cvHl9Z2f32JiZEBIIBH71qz9VVF7+vx/9z7q1K8bHJzIy0mQy2YsvvfHHP/9zyZLSDRtW//0fz5w4eTak8gUL5rW1dfT2DXR0dA2PjEZFGdjtdrvj8R/87PiJM9u2bjQaIn/ww5+fPHWWEOJwOI4dO/XEj38ZHx/r9nie+tdzXV09wWBweGSUvStDo1EHg8H0jNS8vByhUPjiS2/85nd/zc3NXrlyyauv7fndH/7m9/t9Pn9rW8f3f/DTkZHRZUsXisWigcEhh8MxXf39A4Pf/vYPtLqI3/z6x1HGSEJIRkaqQPCu2UlMiBPQ9Kuv72aYILdxcHD4m996vK298757t3l9vm995wf1DY0Mwzz9zAtP/eu57OyMOfl5ZeUV/MKjY2OPfe5Bn8//xBO/tNsdWAMAAAAAt5Twltbe0NBUVlbxyMP3hoVpZii249mX2D++9tXPJyUlXLxUZTKZf//bny5YMG/9base/exXCCETE9bmlrY5+Xn5+bMkEslrr+9ZtnShVCbds+fApo3rvvylzxJCOrt6Tp48u3LFEv7tKyKRSKVSVlfVjo6Z4uJiEuLjWlvbCSFXrtZfvFT9nW99Zfv2O8bHJ77y1e++9vqbJfPnEUJUKuWf/viLnOzMnbv2/vwXfxgYHMpQpbK1RUcbb9+47tSpc3fdecfixQtMZsuePQeK5xV+77tfE4vFgUBw1+59W+/YyBZetKjk+//vm0KhsLGxhd/fyfVThBoaHvn2t76SkZ5aWlq8c9e+9betFovF/L3i4mL0et3Lr+xcumQht/HkqbO9vf3sWC0omffYF/77jZ17Y6Kjzpw9XzJ/7g8e/7ZEIpFKJf/e8RJbeHx84h9//11qSlJycuI3v/X9trYO9oo4AAAAAHz8Eu7BweEnfvzL7KyMrVs2zVzyD7/7Gf+Wko6ObplMGh4exi+j0agz0lMbrjU1t7Sdv1ApFoujY6JGhkct4+Ovvrb71dd2s8Xmzi3weLxyuYzbUa/Xzp1bcPT4aZ/Pt37dqoZrzez2traOYDBoNBrYyhMS465ebXA6nYQQiqJoiiaE6HW6YDAY8AemaznbgLy8HIlEQgjJzcnc8exLo6Njer2OEJKUGD/lpf3J9aekJhkNkafPlCckxlVUXE6Ij5vyXvbNt9929Nip19940+/3s1taWtq5sdLqIuJiYwYHh4eGRiyW8cyMNLZVnJaWdrPZsv2uR7gtVqsNawAAAADgY5lwD4+Mfvd/npDLZT/84XeVSsV72jcyUufz+Tyed30qUSAQbNu66Xv/78ff+vYP1GrlD3/wnZTkxIGBQZlMtmhhyVe/8hhFUYQQiUTCz7ZZa1Yv37vvsEwmnTu3gEu442JjCCFs5up0uYaHRsLCNCEXla8rQhuuUioDwQDDMBRFdXb1yGTS9/GhzOgo4223rdq1a9+lyzUZGanf+O8vheTKLIMh8p67tz751LMatYrERBNC4uNjGYYJMkFCiN3uGBoayc7OiIgIk0olbrc7EAjwL/ZHRuo0GvUvf/5EcnICIYSiac17byoAAAAAvCe35B7uwcHhr/3397q6etasXl5Xd429OXt4ZHT7XY98+SvfdjpdIeW5e7hPnymfsFpzcrKCQeaV13b19Q3s3LVvcHCYEOLz+V546fVFC+fvfH3Hi88/WbqgmKIoo9FQMCfvXNkF9kv62ju6uE9Y8iUnJ6amJM0tmhMfH8ttzMnJTEpKeOXVXZ2d3YcPH69vaCpdUHwjubJer1OrVcdPnBkYGArTqOfNK6iouFxWVlFf37h//5H0tNTU1OT3OmI9vX0HDh79n+99/c3dL/zmVz+OjjZOV3LVyqVRUYb2ji72vwtK5lEU9fIrO/v6Bnbu3Ds8Mrp8+eLw8LD09NTKi1Vl5RX19Y0HDhxlCy9aWOL3B159bZfNZnc4nR0dXTN8dQwAAAAA3BS35Ar30WMnW1raCSG//d1f2S1f++rnV65c6nK5nQ5XMBgMKc/dw61Wq/7+19/mz8695+6tz7/w6vHjZ0rmz01JSSSEiESiosL83//h77t27yeE0DQ9b27Bz3/2g298/Uter/eJH/0yGAyqVMofPv6d5csXh9SvVCr+9MdfCAQCfn5pMET++Ef/8/gPfrb1zocEAsGmjWsfuP+uG+ldWlryypVLd+3ad+p02V///KuvfvXzDqfz69/832AwmJmR9oPHv/1er+gTQvQ6XVpqyre+8wP2vxKJ5DOP3v+ZR+9nL9vzaTTqe+/Z9r8NP2H/m5mZ9n8/+n9P/PiXBw8ek0gkn3/soRXLFwuFws9+5oGOjq6vf+N/w8PDliwuZT8POmtW9uP/+81f/vpPW+98iKbpBSXzsrPSFQoFlgEAAADArUO9v59OfH+cTpdQKLjB2zacTlcgEOBuZTabLV/6r29t3bJp2dKFhJBDh4//8U///OMffl66oJgt7Ha7w8I0NP3ertkzDDMxYRWLxZNvRJmZzWYXCATcXk6ny+v1ajTqySnyjaiovPyzn//uZz993GiI9Pn8P/nZbwb6h/71rz9xX/Yys2AwOD4+oVQq+GMbDAatVptSqQi5j5wtLJVK32uXAQAAAOB9EP4nD/aeMryQwhMTVrN5fHh4JBAMBgPB5pa2KKMhMTGeK/z+0keKomb+BpXphHyo8X03gNXfP2C12kwms9EQaTKZB/qHsrMzwjTqG9ydpumISak5TdNTdm3KwgAAAABwi/xHr3B/EAzDHDt26q9/f7q/f1ClUubPnvXf//2FT8zvtjidrr//45n9B47YbHajMXLN6uXsD+ggQAEAAACQcAMAAAAAwLRoDAEAAAAAABJuAAAAAAAk3AAAAAAAgIQbAAAAAAAJNwAAAAAAEm4AAAAAAEDCDQAAAACAhBsAAAAAAAk3AAAAAAAg4QYAAAAAQMINAAAAAICE+xZgGMbpdDEM82kba5/P53Z7MFYAAAAAnyqCJ5544qZXGggELly4VH6+MuD3GwyRFEVxDwWDwdd37rXZ7NqIcLFYxH/oI2V0dEwsFgkEgskbnU7XocPHkpMTQx6d2ZjJ/MYbe5VKhV6ndbs94xNWuVxWX984MjIWGamfbq9jx053dHY5HY7Ozu64uBhuu9VqPXb8dHp6Kvvfnp6+q3XXEuJjb7Ax+w8cMRojJRLJlI/29g1YrTaJWMw28tYNclNza2trO79f768M61xZBUWIRqPmtnDjfFNa63Z7Dh0+kRAfJxQKQ14UjYyOyWWyKYN5ur3eK36olJdXut0erTbiP7MW+F2YubPXreFCxeWQObopzZt5llta2gmhaJo+daqsqrpWIhGHh4fZ7fajR0/V1V9TKhUajdpksrS0tBoMkS6X+9q1JqPRcFOW0nQB7HA4PR73dHu915hha2MYMvNeJpPl4KFjV67Wd3Z0x8XFWsbHDx0+0d7eGRmpczpdBw8dq29oZAjR67U2m+1CxaWJiQm9Xuf1+qqqr4yNmrTaCPaMd+VKXU9vf5Bh1CplVfUVpVIeCASrqq9ERRlomr7BLryPGL7BYZm55uuecgEAbpFbcoW7qblVKBLefdeWmJjoYDDInisdDifDMG63RygQZGWmHTl6sr9/yOl0+Xw+7jqux+MNBAKBQMBqs7Hb3R6P2+Nxuz0MwzgcTu4KMfsQt7vNZueXZ4/l8/k8Hi/3t81mZy8Vu90e/t9cAa/X63A42XrOlVUMD4+FNIbdKJVK1q5dKRaL+U3i785PxdiGsSlybExUakoSIWRgcLCm+orT6SKEMITh9prcR7vDUTAnLycnq6hoDnsUruX8Q/j9fm6Lx+P1+XwOhzMQCEyu863+Bpl3/ffdV9Anxicmxif4jQwpzB6UrTPkcGwj2WH3er3c5AaDQbfHww4Rd7iU5MSiojlTDp3P57PabIFAgCvj8XjZweRPGT94+O1kR4nfBX7juaDiWhtS8+ShdjpdLpeLG3P+kLpc7rKyCrNlPCTMQvYKiWouhqd8lD9QgUDAZrP7/e8MTlHRnJSURP4shHSEnRePx+twOvmtZTfabHYuNvjzOLl8SBdm7iy3JLmYmRyuIS9U+O0PWeyTV3QwGOR6x2/klLPMP9DwyKjD4bh4qTohIW7rlo1qtcrj8R44eKy4uPD2TesuXa7p7RtwOBznL1zq6x/0+329fQOTl/DkeeEvpckDyzWPDeC3OuL2sO1sbm691tjCFnC7PSHnQPacGQgEJkdjSD0stjav1zvdXm/n5Q6DIfKeu7du2rROIBCUlVWuW7ty+fLFAgHNPnTnttsnxifqGxrHxszz5ha6XO7aK/Vt7Z3paSm0gL58uebthelQKZWdHV1Op+vcuQuDgyNWq9ViGRcIBJNn3OfzuVxutmtcT90eDxvDU55buBP75IHld5B9smDLBAIBbtVzNU95vgIA+ERd4fZ4vJcv1xoN+shIPU3T9fWNFy9VjY2Zrl1rVqlV9fXXpFJpd1ePVCa12mzd3b2Eonft2peVmX7u3AWZTHLpUs24ZaLyUnViQvyrr+0eGhyOijKeOHHGbLZUVV+JiAhXqZQ2m+3pZ14MBoPh4WFv7j3k9XjOX7gUFWV89bXdJpO5rbVjeGTU6XTtefOARqPxeDxHjpx0OJzXGptVatWhw8eDDBMIBHp7+y9eqhoaHBkdHbXZHHv2HmKCzKnTZdHRxiu1dVKZVC6XXzh/iW2M0RBZU3NVKpNKxOKy8orU1OQDB46azZbLVbVCoXB0ZIzbPTMjTSQSut2enbv2ej2ec2UVOp22v39gYGAoMTFBLBY1N7cODAxFRIR7vb6y8kp2r/S0lCNHTvL7aLXaqi7XhIVpRsdMZvO4x+s7fOQE24u4uJienr7U1OS9ew+ZzObOrh6xWJSUlEAIOXfu/IWKSzar7eKl6oyM1IMHj3GNdLk9Bw4cDfj9TS2ts/NyWls7uO7zr8CNjIwFgwGLZZxtZFiYhhBS39BUVl7h8/lEQuGlyzXjE9aysgtJSQmVlZe5w2VnZ1AU1djYwg77yOio2Tyu0ajf2Lk3Jtq4c+e+MZO5oaHJ7fFERxkJIY2NLSaT2WQyhwydw+HctWs/Q4jNbh8dNbFl3tx3yOvx7tt/xO12V168rFAohodHTSYzW39SUvzw8GiYRm212Wuqr3T39I4MjzodTrYLfX0DXAQmxMe9/MrOocHh2NhoqVTS2NgyuWany3X4yAmny115sSo9PaWxsaWsvMLpcvf19efkZB45coI/TUPDo3V119QqhdvtOXrs1JR7paenlJVVsoGUnJRw4uTZuLjYvr6B9raO2NgYp9N19ux5LuZfeXUXN1AR4eFvvPGmx+O51tgSHW1kr8xdqLhE0/SFiktjJtP4+IRWGyEUChobW3bu2isUCo6fOJuclFBVXXv6dJlWqz1/vpJrbXXNlbKyCo/HU36+MiUlqfx8JTePly5XTy7f3d3LdWHWrGyhUDhdZwUCgc1me/Kp5xgmyGZmXq+PG8OUlKSurp6U5MSBgaEwjVqjUQcCgTNny7mjSyRij8fLzoter9t/4Ai3ot/YuddkMl+6VH3lSoPT4aysrEpPTzl06Dgb1QKBwDRm4s/y5Hju6ekL06hpmq5vaIyJidLptAMDQy6Xa9asHIFAQNN0f99AWJjG5/d3dfUkxMf39vWz7x1xS5hrCTcvgUCQv5QqL17mBjY1NZmNEO7MYDKZZTLJ08+8GAgGy89XKOSKnt4+64RVp4tQKpVt7Z0d7Z38c6Barbp6tcFiGeeOxS18Q6Tumbfr0ajV4eFhPp/val2DdcIaHh5WX9845V6pqckURU1MWEdGRnW6CIYhYrGopaXNZrPHxEQrFIqJCevEhDUhIc5isXi8vtycLEJIa1uH0RCZmZkmk0ndHs/EhC0+PnZ0dMzn9UVHG1ta2tQaldfj9fq8NE2LxeJAMBgy4zHRxv0HjkRHR506fS4+Pu7goWN2m10kEtXUXh0cGqFpmn2vg/8EYTTon3nmxWAwaDBGikWis+fK+QN7+XIN10G73TEwMBQZqT92/JRIJDp+4jR7Vr/W2EzTdG/fwJTnq4kJKyEEV7gB4BNyhTsuNnrz7evOX7j08ss7HQ5nU0vr0iULly5Z6PX6ZFKJ0WiYNSvbGGXIzkpPTIi3jE9YLJbISF1Xd0+QCRoMkUVF+R6PZ2xszOVyaSPCV61e5vV6RkZG1WqVUqkwWyzsURIT4hYtKhkeGfX7/TKZTCaVTkxMGI2G5csWL1u2sK93wOfzlS6Yl5uTWVN9Va/TKpQKp9NFEcrvD2i1EUZjZE1tnV6nU6uVY2NmQsii0vmlpcV6vVYmk7LN02kjuMaIxSJ2I/vmtcUy7vP7Fy0qWbliSXNTK393n89LCBkYGDQY9CUl8xaUzGtta4+JiY6Ni9Vo1DRNs38nJsbz9xocHArpo0ajNkYZEhPjBbSAEFJdVcv1wuv1sW0IMsyypYvmFs0RicTssAhFosWLFpSUzFMoFKOjJn4jmxpblixZMH/+3IT4OJ8vENL9d4UFLeA3MhgMNjW3rF61bN7cAoMhct7cwmAgYLPZLZZx/uHYVhFC2GFnm83R63VLlywsnlfIvzjHChk6gUBAC2ixWJSelsIvU1IyLyUlaeHCksKCfI9n6utVsTFRqanJdrujb2CQ7UJ8fCw/Am02GxtU3I0Nk2tuamxZsGDeooXzI8LDBgaGmlpa16xePm9ugV6vGxszhUyTXqc1Gg0ZGemtrR3T7SWRSLhA8vv9UUZDd0/vwMBQfHwcIUQul/Fjnj9QAwODUdGG0tLiosL8kJ4qFAqXy52VmS6RvDX1y5YuKimZl5gY3z8wSFH0ylVLlUo5v7UikXjF8sWLFy+QSqVmyzh/HieXN5nN/C68NYlTdXZwcJh9NC0tecni0tIFxa2tHfwxHB4eCX2hLxDwj85uZOfFbLHwVzQ7GoUF+UWF+SUl81Rqlclk4aK6pbmNneWYmKgZ4pkQkpubtXjxggMHj+7bdzgYDEikUna7TCYlFEUIUSqV0VGG1rZ2bpeu7p7JLWHnhb+UCCH8gW3v6Ao5M7CSkxMWL3orwOLjYlNSktgbV6KMhpBzoEaj5h8rZOFz9TgcTkKISCRia4uM1E+3l8fjZdtgNls6OrrHx8dpmr799ts0YZqnn3m+4VoTIeT8hco//+XJ/oGhWbnZwWCwsallaGhYIpWwF5UbG1uysjIIISazxWiMVCgVDMN0dfWkpCZ5PN7h4RG9Xhsy44GAf9/+I/mzZ0VG6nQ6XU9vn1QqGZ+wjoyMRkUZuWEJBoP85Wm1OdgTu0IuDxnYMZOJ38GEhLi+/gGz2SIWicLDNOxZnX2hxTDMdOcrPOUDwIdFeCsqZRhGpVJtuWPDmbPlY2MmXhpHUfS7UnyVShkMBtvaOjMz0trbO3W6CLNlvLr6ysoVSxxOJyGEomnCEJFIpFKrkpLik5MTZLK3btakBTRFUWKRKCIiPDk5ITklUSgQXmtsIYQEg4xEJqEFNJvzSaXSqGhjXGx0ZkaaXC67956t1TVXW5rbpFJJfHysRqMSCkUdHV2TOzI8MspvzLSvWq53MzdFXf+FjVAonNxHPn4v2BsMBAKBgL7Rl0y0QCCWiPhzwe/+jU+uw+E8fOTE+ttW+QPBad83EXyguJJKJXdtv6O9veuNXfsyM1JDEveZXa6qFYtFq1YuPVd2YYpBoCmKptmguiEURQsEIl53rjtNU+41Omqqb7jGBVJCYvz58kqhSKjXa2cOM4FQQE8zxYsXlUxMTOzavX/dupU63h2rNE3JpFKKoihChSycisoqdnnSNE0Yhj+PU5Zvb+u8kSEKWdQMYVRK5bsLUDcSRey8TLmir7v0BALB5HgOBoM0TQeDAfZvQ6T+vnvv3LfvMCGkt6fX5ysUiUS9vf3c6OXl5b755kHu1cUMLeEvJf55j6ZpmVRy42eGKc+BIR8Ombzwb2wRvbMX95IsKsqYnz+LbSohJDcnMzYm6ty5C7Nn5y4oKV60cD43bnmzcsI0muqq2ugow/HjZ7KzMiIiwoLBoMUynp6WIhKJxBLx0PBoUeGcwYGh/v4h9p43/oybxsy5s7JbWtpSU5Nioo1V1VeSkhIs5vGOzu5lSxeNjpqmXJ40TbMn9skDK5VI+RvlcplSqaiuvhoXFxMeHsae1dtaO2Tvvpv/Rs5XAAAf14S7trau4mKVRqViGGbe3MJ5RQX7DxwRi8VGQ6RSoXj7yUx89Pjp5UsXh4eFdXf3JCTEHX/7U4CDg8NHjp7s7OwunlfIFo6ICDcaIo+dOKNSKOfOLYiICOOOlZAQd/VqQ1l5pUgomjevYHR07NDhYxMTtuJ5hdxtf3PnFuzdd2h4eEQul0eEhzc1tRBCIg367OyMEyfPxsVFRxmNoU9XEsmeNw/NnTuHa8ziRSXsRvZpKSIiXKeN2PPmgYkJ2/Jli6xWW0gNbMMOHDw6OmratHGd3W7nHlIqlfX112iKUqtV3FNLeLhmuj5O7sWs3Ozx8QmGYQLB4O49B2x2e/xUHysMaSRF0/v2HUpOTuzu6V28qKR4XiHXfZvd7nQ6ly1dNLmRCxbMo2l6XlHBnjcP6vXauNjoiQnrqdNlbW0dM39MUxOm2blz75Ur9Vab9T3Fz+Dg8IWKS2qVUiGX0dO/VgmpXywWdXX3SiTixsaWhvpGgUjEdWFu4ZzJETiDwsL8ffsPR0SEB/z+6CjDRErSrt37I8LDxiesk0NRLBa5XK79B44UFxedPHl2yr34Ub14UYk2IjwYDIaHaUQiEdflkJhnGSIjT50qczicPT19CxeWcNt9Pt++/Uc0ahXDMBLxW+nUmXPlPb1945bxkvnz+geGJi8cv8938tQ5tVolFovCwtST5zGkfMq7u8AO8pSdZR/t6Og+fOREb2//+ttWS6VSbgxjoqMuXa41mczsHMXHxxJCpouikBV93ajmZnne3AIunrOzMxiGOXjomMlsoSl63tzCM2fLO9q7xBKJSqmIi4vNybU99a/nZDKZRqMumT+3v3+QEKJQyHNyMhoamq7bkuTkJG4pEVLCH9ikpISBgaEZzgyEEKVScejwcYYws3KzaZqefA6cbuFnZ6VPV5vX551ur/nFRezGq1fr+/r6FXL5gtLiAwePCmja6/EWFr3rzRO327Nv/2GFQj40NDJvbsGZs+W1V+vMFktrW0f+7FypVMoGrVqtGhoclsmkmjBNa3unTCrlrxqjwRBpiJydl1tTc6W+/lpqasrQ0DAb213dPfxPuLLnFt7yfFe6/O6I1YR0PD0t9cDBo6WlxS0t7dxZ3efzUxQ13flKIpE0NbVkZ2fQNL4SFwD+o6hb9JVz7GeqxG+nAgzDBIPBkCs3Pp+PSzj42M8MTT4hsgn0lN8N4vV6RSKRx+M9dvz0iuWLpVJJyO4Mw3i9PvZKD7+ekHbeeGO4JtE0PcM3Nly3wI33MaQXHI/HO/P3vfDbEFI/1302DGZuJzeJU87mTen+dPHznuqfcuONt3nK8iHjNt00zbAXP5AYhjl9piw7O9Pw9r2kM4TZlJM+eerr6xsJIRkZqZPXFNeMc2UVCfGxMTFRXPBPOSb8Zs8QkCG7W63Ws+curFu7khv8mcd85kfZFf1eV9bksOEP0eTgv5GQmK4l/NpCBvaDRP6NL/wPvtcMgzxl+xubWmRSKXub2fuY0xtfbpzJA8s3MjJ69WrDypVLpwzU93G+AgD4mF3hZlM3/tMeRVGTz3dTZtszZLcznDHZY1EUJZdL2Q9CTW4P98TDryeknTfemOs26QYLvKfy/F5wrvs0zK8zpH6u+zeSGXCTOOVs3pTu3/i8zFD/lBtvvM1Tlg/Zd7qqZtiLCySv17t3/+EogyHy7VsXZg6zKSd98tQLRcLp1hTXDKlUIhQKuf9ONyYzdHyGzlIULZPJQhbXje8+5Yp+r1M/OWz4QzQ5+G8kJKZrCX/fkIH9IJH/XmPgg+w1wyBP2f7wMM3MX+T3XlfZdXecPLCcjo6uU6fLtm7ZOF2D38f5CgDg1qHwoyoAAAAAALcO7mMDAAAAAEDCDQAAAACAhBsAAAAAAJBwAwAAAAB8ChJut9szZgr9QTiGYYZHRtmvSLtx5eWVLS3tt7S1DofTZrNN15F9+4+43R5+p+rrG9mvaXt/PuDu01VotVr3HzjCbuH/PYNzZRU9PX03PqfcUAAAAADALUy4fT6fx+O12ew+n48Q4vF4PR6vw+lkGMbt9jgcToZhBgYHa6qvsL/yzW10udxlZRVmy7jb7WG/V9Xj8fp8PrfH43S6uJ8E9/l8Npud+36VoqI5KSmJDMM4HE7+z4YzDMO1gTsEwzBuj8fr9bL/9fl87N9sMX5J/oGam1uvNba43R72KFxO6XS6XK53jsjvFEMYtlr2iG6PJ2R3n8/HPup0utiGORxOq9Vqs9mDTJDbnas8EAhYbTb+FrfbwzaPHWGbzR4IBPgD5XS6uL5MabrCISPMNZLbPnncQoYCAAAAAFi35Hu4m5vbTp0+V1SYf62xZeuWjVeu1re1dixbvtjpcLa1d6jVKofDqY0IHxszjYyM2u0OdqPT6crLyzWbLf19/QKh0O/z5+XlnDh5ZvbsWa+9trugIG9gYCg3NyssLKys7EJMdJTd4Vi3diVFURcvVSfExw4ODVss49qIiMzMNJVK6XZ79rx5IC42RqGQ0wK6o6OLPcTKFUtfevmN6GijzWZPTk6UiMXnyivycrNbWtvvvmtLe3tnW3uHXCZXqRSxcbFnzpSlpaXodbqh4RGf1xcXG1NVVavRqIeGRxYtLDGZzA3XmqKijKOjY4SQYDA4PDTCdooQUlZeaZ2wtbS2b7ljw67d+3XaiNLS+ceOndJo1INDw7Nn5/p9fkJIamryzl37bt+0tqGhyefz2x0OiUSijQi7UFnF7n73XVtkMqnT6Sovr1Qo5L39A1s2rxeJRMMjoydPnk1NTTZE6tvbO/sHBiMiwttaO2bn57a1dmzYuNY0Zh4bM42ZzFlT/TodIaSzs/uyqqZ/YDA3N0tAC7jCSqWS7XiU8a1fEDx9piwiPCxCq+VGPi42pux8JX/c+EMBAAAAALc24SaELFu6KDc3y+ly9w8MUhS9ctXSuNiYXXv2r1y+RK1W7XnzYHh4WCDIxMfH8jfKpBKj0ZCRkR4MBk+eOhsbGy0WiZQKWVpa8pLFpT09fZeragU0rddpFUrFyOiYx+OVSiXsERUKRW9ff/G8QpVKSQgZGBg0GPSlpcXBYJB/CJvNptfrli5ZODIy2t3TJxGLF5XOz83NsoyPO52umtq65KQEgYAeHTXZ7c5Fi0oS4uMIIU6nkxBC09TIyGhcXIzd4TCZzU0trWtWL5dKpRMTVkIITdMxMdH+QDAxMb6+vpGr1uv1aiPCV61e5rA7fH7/okUlZrOlrKwiJSWJP2ITVlvBnLzxcavT6RAKRdzuPp9XJpPK5bKiovza2rqxsTGXyyUSiSRisd8f0Goj4uJiunv6Fi9aEBamDgaDSxaX0rTA4/ZkZKRSNNXZ1TM0NKzX6SbPUVJSwuLFC9hRvX3TOq6w3zfAdby7p6+65oqAFixdsnDv3kPcyPv9fq6Fbrc7ZCgAAAAAgHNr7+GmaUomlVIURREqZDuZ9NOGNE1Rb//enlwuUyoV1dVXY2KiuR9BZAijUiqlUmlUtDEtNWnd2pX831HLzclcv271iZNnOzu7Z2gPNf1P+tE0JZVK4uNjs7MzVqxYMrmASCRSqVVJSfELS4sz0lNFght9uULRNHn3bR30pF8+S0tNPnWmvH9gIDMzY3INwyOjFZWXFy6cz+bBhJCwMM2992w1mczHjp2e8qDHj59RyOXLli4UCkUztI0d1ekKe71esVjs8/vN5nH+yAuFQv643fhQAAAAAHza3Ko86cy58p7evnHLeMn8ef0DQ4QQmqbnFRXsP3BELBYbDZGRev3p02U0Rc0tnMNtDA/TuFyu/QeOrFu7Mj0t9cDBo6WlxYGAv6Oj+/CRE729/etvWy2VSvfuOzQ8PCKXy+cXF72VNTLMiZNnaZpyu90ymZQQkpAQd/Vqw779RwQCOj8vlzuEUqGYrs0CAV08r/DEybNxcdFRRmNhYf7efYeMxsjw8DBDpP7Q4eOlpcVGQ+SxE2dUCuXcuQUpKUm7du+PCA8bf/uyrlKprK+/RlOUWq2a/GPpERHhOm3EnjcPTEzYli9bRNH0zp17r1ypt9qshBCT2WK32SUiUX//AMMwk3cfHBw+cvRkZ2f34kUlhJCWlvamphZCSKRB7/P5J3fHH/DX1FwdGR1LTU2SSCRNTS0JCbHj4xNWq1WtVhNCurp6uFGtqb3KFeZ3XCwWp6Umi0Si8xculswv2n/gKDvy/GGkKIo/FC6X66WX39i2bZNapcICAwAAALglP+3OfsNGRkaqSBR6bZVhmGAwKHj39d0pN46MjF692rBy5VKr1Xr23IV1a1fSNM2moQzDeL0+/uVtltfrFYlE/FQ1EAiwe015iCmxnwgUi8XTNYz9NCe7kf/3DeKaxP87GAyeOHF2wYJ5Eon4zb2HVq1cwubEfOyXt9C8K/TXPbrP55s8BdM1hl94uuGabuRDGhMMBmka3zgJAAAAQMgtusItFAkJIVOmehRFTU7jJm/s6Og6dbps65aNhBCKomUyGb8ARVFT5nxslszH7TXlcad+CUJRXD1T7sXf8p5S7Rl2p2laqZTv3XeIFggy0lJUU10bnpzCXvfoM2fbITXwC083XNONfEhVyLYBAAAA3smgbsUVbgAAAAAAYOFKJAAAAAAAEm4AAAAAACTcAAAAAACAhBsAAAAAAAk3AAAAAAASbgAAAAAAQMINAAAAAICEGwAAAAAACTcAAAAAACDhBgAAAABAwg0AAAAAgIQbAAAAAACQcAMAAAAAfEQJb0WlIyNjV+saCCFhYZo5+bMEAgEh5OChY+lpKampyTfxQAzDOF0uuUxGURTmEgAAAAA+gm7JFe6mppaWlrb82bmpKUk0TRNCvF6v0+ny+fyEkEAgEAgE2JLBYNDv9/P35T86w3av10sIcbncO3a87HK5ue0+n49hGPZvl8vN/R3C7/cHg0GGYXw+3+QdAQAAAABuFuEtrV0sFrtc7p/+7Lepqcm1tVdzsjPrGxrPnbtgtztMZvM9d209eOiYUqlISkrYsH4NIaSi8nJZeUXAH1i6pLT2Sv22bbe7Xa7TZ8qTkxPLz1cG/IHlyxa1tnVca2yOCA/XasMTE+PLyytkMun9990pFouffOpZiUQsEonWrlnxzL9fVKmU/f2D3/zGl48dP52TnanXa197fc/2Ozf//Be/j4oyli4o3rP3YG5OZlZm+pWr9RRF9/b2f+W/PhcREY6wAAAAAICbRfDEE0/c9Eq7u3trr9ZLpVKxWDQwMEgIefCBux0OZ6Re19zcVlg4Oy0tRSqRtrd3hoWpY2NimppbiwrzCSHPP/9aelqKVhvR2dmdkpJks9oGh4bjYmOOHTvNbu/o6FIqlSuWL1lQMre2tm79batNZssD92+XSqWEkKrqK+HhYRvWr2lsavH7/I88fC/DMIODQy63O1KvUyjkDdeacnIy+/oG/vtrXzh56uz621avWLGEYZjDR07OmZPndrslUklsTDTCAgAAAABullt1hTstNXnliiWEkNraOv72wsLZzzzzYkRE+P333bn/wJGszIzk5IQFC+aJRKJgMKhQyHJyMrUR4RKJxOVy79t/iBCqaOsc/vYjR09Od9DHPvdQV3fvb377l+XLFgmEgpBHA8Ege9OIQCCgKMrpdHEPGQz62Xk5+bNz1WoVYgIAAAAAbqJbdYV75859DY3NV67UF88rPHToeGtre0tLa96sHItlvLrmSmSkXqNRJyclvvb6bqfTZTZbUlKSaJqmaHr3ngPj4xM0RaWkJJ0rqxCLRSUl8/jbLeMT3OXq4uLC02fKBgeGUlKSAoHAv3e8ZLPZrFbb6lXLz5VduFrX0N7RdcfmDVar7eVXd9bXNzIMM2dOXsO1prlzC9Rq1ZNP7RgZHZNIpePj43X1jV1dPYkJ8XK5DGEBAAAAADcL9R/+pOCuXftKF87X67R//stT9927TafTYg4AAAAA4BNM+B8+XnxC3L93vCQSCmfPztVqIzABAAAAAPDJRuG78AAAAAAAbh380iQAAAAAABJuAAAAAAAk3AAAAAAAgIQbAAAAAAAJNwAAAAAAEm4AAAAAAEDCDQAAAACAhBsAAAAAAAk3AAAAAAAg4QYAAAAAQMINAAAAAICEGwAAAAAAPgjhLax7926yZw8xmQghRKslmzeTO+741A602WwZH5/weLyEEIlEHBamiYgIR/wBAAAAfOIJnnjiiVtS8Q9+QE6fJlbrW/91uUhzM6mrI8uWhRTs7e3fuWuf1+eLjjJSFMVtHx4Z/clPfxMMBGNiooTCm/DC4Pz5i729/XFxMTMXc7ncr7y6Mz0tVSR656AOp1MoEPCb95709w+63W6DQR8dbdTrtX5/wOFwOBxOtVrFLxYIBKprrl5rbB4eGdVGRIhEohs/BMMwTpdLJBRObmRnZ3dV9ZWOzm6n06XTaS9eqj569JROp1UqFezhRkbH9HqtUCjs7e2/1tjMHrq3t7+xqYXdztbjdLoOHTqelpZiNltGRsfCwjRNTS0isYgipKWlXauN4A495RhynE7Xc8+/mpmRdiMdNJstr7+xd/bs3OkKTFmb3+/3eLxTHh0AAADgP+zW3FKyezdpaiJOZ0hmRJqayO7d/G3j4xO7du+7a/tmmVQ6OmZiUyWfz0cIMZssRYVzCgpmnzpdNt1xgsGg3+/n/uv1etm0NRAI8DNRtsLi4sLi4kIuI2QYJqQkV95qtTMMQwjx+XzsH88++7LZbOHvG1L5zCmj3+9PSIiTy+XsFr1em5AQ5/f7uTpZHo93z5sH4uJilArFU/96LhAIhHRwcrODwaDb7WYf2rHjZZfLPXlYzp4773a782fnJiTEXbpcMzw0ctf2zf0Dgzabgz2cVCL581+e6usbaG1tDw8P+8c//91wranhWpOApp/594tcZweHhnU6LU3TVqvt2LFTLpf7+Rdeu3ateWzMVFF5maZprjH8MZxMLpc9cP92uVwWMnHcqw6ud4FAwOfz2e32ydPNHYtfG1egtbXjwMGjWN4AAADwUXBrLgHu2fNWtr19O3nwQUIIee458tprxOkke/bwbyyhKKqvb6C3b2DWrGyKoioqL588eZYQkpub1dnZc7WuoaLyssUy7na7+/oGttyx4djx0zQtWLF80ZGjpxYvKjl2/PT4+ETpgmKKpvfuPZibm5WSnFRx8XLAH1i+bNHcuQUTE9bf/f5vOdkZ+ki9gKYJIRRN79mzPzY2prOzOyMjtaur5xtf/3JrazshpKhozr93vHT3XVvYVO+FF18LBILd3b2bNq4rK6twOJwPPXjPc8+/olIp+/sHv/mNLx85cqK69ur84qLNt6+fYTDGxydUKtXk7Xq9dmhoJOTGEgEt0EaEC4VCoVDQ3NL25psHlUpFUlKCRqOZ3GyHw/HCS6+HadRhYZrExPjy8gqZTDp/fhG314b1a/iVSyRigUBQU1u3ZEnp/OIip9PFHk5sNMgvXIyM1MXGRvf09Ekk4syMtJzsTKvVdulyjc/nE4vFhJCe7t709BRCiFYb4fP5BgeHVGpVd3cvTdOxMVFtbR1cY+7ctpkQYrPbn3/h1YKC2deuNa1du/LH//erHz7+3WPHTxXMyTt5quyRh++Vy2VOp+ufT+4IC9OYTOZ779n6i1/+MScns62tg52Ug4ePxcXGWq1Wp9P105/9NjraaLc7FiwojjJG8o+149mX775ry+9+/9fISP3o6OiWOzadK7twta4hKspQuqAYixwAAAA+XLfmlpKnn37rj1/+8q0/Zs8mL71ECCEuF7n3Xq6gVCopXTDv2LHTzz3/SnZO1r79hz/z6AOLFpecPHlu0eISnTZizerlGo1665aNE+MTdrtjeHg0EAhIJBKtNnx2Xm6kQd/e3hnwB9QqZUpy4qaN61586Y30tBStNqKjo6uwMN/j8VyouLRwYUnxvIKenj5CCGGYzIy0jRvX9vT0PvrI/S6XW61SOZ1OQkh0dFRtbV1ublZ9Q2NBweysrAyX01VVc2XjhjU2u/3+++7s6Oz2+/yPPHwvwzCDg0NOl3vlyqWLFy2YeTCGhkYSEuImbxeJRENDI3q9ltvi8/n37ju0b/+Rw0dOPPbYw2fOlIeFqWNjYpqaW/V6bXZWZkizT546u+G2NRvWrzl3rqK4uMjt9jxw//aDh45xexUV5gsEgitX6oeGRgLBoEajSUtLTkyM/8c//93Q0DQrN3v/gSMHDx4rP1+5ffsdBkNkU3Prs8+9kpWZnpmZRlHUmTPl0dFRycmJ5O3bXQrm5AkEArFYfPlyjcvtToiPGxkZtdns6empp06d4xoTFxfT2Nh0/vzFNWtWJCclVlXVSiUSp9OlVCqGhkYKC/LrGxrn5M8SiUQNDU0NDY05OZlDQyN6vc7t8XzxC49arTalQnHmXPnnH3tkVm5We3tnfv6s9vauRx6+Lz0t+eSpc13dPfxjtba25+Zmdff0febR+2UymdfrzZuVo9Go165ZgRUOAAAAH7oP+VtKGIaRyWQPPXj3hvVrLl+ukYjFk8uwNxikpaVUVF42Gg1SqaTy4uXEhLjDR060tXWsWLFELBETQthbjRUKWU5O5uJFJffcvZUQotGof/iD74yOjj39zAv8OilC0bQgtDGECQbfupnBarX+/R/PzJ6dm5GeyhWQiMUC4Tt70TRNUzd5ALUREb/6xRMl8+cGAgGRSJiVmTFvXsFnHr1fKBBObjb/rgxeHv/OXtxtzfmzc1euWBIZqQsGgwnxsT98/Dtut2dwaFgbEfGrX/7oj3/4RWZGGiEkMyPtR098r7un12Qyl5+vnLDaFi0qeftlw7A2Ipy91E1RVExMVH19U3ZWukqlbGpqNRoNIY3p7x/MyEirqbmqUimlUmlVde384qLKyiq5XCaTSfkl4+Pj8mfnPvLIfdHRxht6jSgQTNlxAAAAgI+mW3NLiVb71peTPPfcO7eUcA/xdHZ2/+Of/1Zr1OPjE1/5r89FRxuf2fEiIWR+cZFMIiWEREcbX3zptegoY0HB7OGR0RXLF2u14Y2NLXq9LhAI1NQ0uT2e9NRkLhUrKZn38is709NSMjPSCgpmd3X3Hjp0TKVShoVpZmhvpEH/z3/uOFt2weP20ALaarWOjpktFssbO9/s7u4lhCgU8pde3rlt66aTp87988kdlvGJ//rSZw8fOXEjgyGRiJ1OJ3cDN2d01CSRiKdMKNfftvrV13Zv2LDmhRdezZuVEx4eJpFIJpcsXVD8yqu7VCpldHRUbEyU3W7fs+dAQUH+q6/uZPdateqtj6i++vrus2UX4uNiVUrFxUvVYrFYpVJG6nX82i5X1R4/cSY8TBMMMsMjo7//w99zczKHhoYffuhelUrZ3d0Xz7tOHx1lPHHibHh4eHSU8XJVrUqp4DdGr9MmJMSvv23VgQNHGxqaMjJSDxw4ev996Tt371u0cD7/oOnpqYePnjx0+LiAFnDJPftipiA/7+//eCZMo2ZvBR8YGHzqX89Zxse3b9ssFov4x5o8MmFhmsrKy7ilBAAAAD4KqOk+2faB7N5NXn459EOThBC5nNxzz6ftywHNZovNZp98V0l3d69KpfxYfDkgwzC7du9bt3bVh3Vp2el0/XvHS+xt31i0AAAA8PFya24pueMOkplJQq7pyuUkM/NT+FXcERHhQqGwu7t3dNT0dvro7O7uFQqFH5ev4vb5/Pn5eR9isisUCrIy04RCAVYsAAAAfOzcmivcLPzwDQ9++AYAAAAACTcAAAAAANxkNIYAAAAAAAAJNwAAAAAAEm4AAAAAAEDCDQAAAACAhBsAAAAAAAk3AAAAAAAg4QYAAAAAQMINAAAAAICEGwAAAAAAkHADAAAAACDhBgAAAABAwg0AAAAAAEi4AQAAAACQcAMAAAAAIOEGAAAAAICbR3jrqjabLePjEx6PF6MMH30SiTgsTBMREY6hAAAAgJuLYhjmVtTb3z/o9/v1eq1cLscow0ff6KjJ6XQKhcKYmCiMBgAAANxEt+SWErPZ4vf7ExLikG3Dx4Ver01IiPP7/WazZYZifr+/rb2zqam1qam1rb3TarVeqLjEPVp7pW5oeOQ/1maGYTxe7+TXzMFg0Ov1EULq6q+NjIx9WEN63WZM1/7r8np9FZWX2coJIQ6Hkz8LHxzb4M7O7s7O7vfasPLySq5hN+g9Hcjv9/v9/pARmGxoeOSNnXubmlsrL1bxRzhkrN5rH2eeMrby67YtZJwn9+79Hf3DWm7v2w1O5U3X09M3NDxitzsuXapuamr1+/1jY6amptaOjq7/ZDMAkHDfBOPjE0i14WOado+PT8xQQCAQRBkNPp/P5/NFGQ0URXk8HoZh2KfhvFk5hkg9ISQQCPCfmBmGCQQCk7fzc4tgMMjWEwwGub34f0/e0efzX7hwyefzc7uzjw4Pj9Y3NLIFAoEA/yiTsxmv18e8bfJxuWq5LkxuGLc9pP7rNoPf/un4fL4pUxy328NrTMDj8fAf5Y9zSA3soRmGYXML/rhxg8A1eLrkj18/NwIMw4hEwuLiQrFYNDm1um7ixa8zpH5utPkpstvtYZjglNFCCLFZbbPzcjLSU4sK8ymK4necG6tAIODz+/ht41fCBsbMU8ZuDAaD3AiwlXOzE9KRkArZceY/xH8BwN+XnabpAn5y9ycP+8xTMDnC+ZWzLZkhXKdb4NMN43uaypAtIUM6OYynDE7uuAzDmC0WpVJ5+XJNRmaaThdhsUy0trb7fD61WnX8xGmrzYYnAoBb4Zbcw+3xeJOTtRhc+NiRy+Uzf+qAoiiFQi6VSgghCoXcbncM9A+dK6sYHRlduXJpe0dXlNHQ2tYhEgoEAsGcOXkikaiqqra7py8xMd7pdFKEsoyPL1u6qKGhcXBoWKfV+ny+wsLZh4+cDNNokpMTW1rbpBKJTqeNjjFeuHDJEKk3Gg1+v7+1rYMJMhkZqSMjo4NDw3K5XKmQa3URbW0dIqFQqVSYzRapTDprVo5UIm5sbO7rH1SrVX6fv6LyslKpUCrkhYVzzp47L5fJHA7nsmULhUJha1tHbW1deHjY2JjJaIg0mcwrVy71eLxV1bVsGwhFxkZNUpk0LS3lwvmL0dFGpUoZHhbW2NTsdLpSU5Li42PLyivUKlVdfePqVUubmtu4+gkhUzajoDC/srJKQNMejycmJoptf3FxYTDInDlbvrB0/vETpzMz0qRSqdlisdnsfn/AYhlfvLjEbLIQQhIS4s9fuFhUOIedjtbW9rr6xoiIcJfL/daWto7a2jq9Xudxe1asWFxRefmdGszjV6/UR0cbKZoeHh4RiURutyc8TGO12dauWTE4ONzbN2AxW+YVF/ITnbPnzhcU5Pt9vvqGptIF8wghFy9VB4NBk8m8etXyurqG7p6++PjYocEhQlH5s3Pb2rsSE+ImJqyzZ+devFiVkBBfV3+NGxaBQHD6dNmcOXmNjc2EorIy0xsamiIjddU1V/oHhrg2s3GysHT+6TPlapXSZrcXFebHxES73e6Ga80ul0smk5rNlrLyCrvdUVSYLxKJuVmbNSubLeb3+xUKRUtr24KSYm7q586dw/brxMmzNEWNT1hn5WZx+V9d3TWtNiIlNanu6jWJVDxumVi1alldXcPkkNPpIurrG6OjjXq9rqW1nRASFxeTlJjAewEZKCuv4jpSVnaBUFRR0RyjIdLr9R08dCxSr+vt64syGjo7u9nwTkqKv9bY4nK5lCple3snu++SxaU1tXUBv18ml2nU6skBr1TIR0bGuJhMS0shhFy8WMW1mR/5WVlpvb39OblZBw4c3bB+zbXG5pTkRJ1OOzIyVlZeER1tjI4yBoNBLhJsNnt1dW1CQrzZbElMiGePnpubVVN7demShdU1V6OMhoGBwckLXKGQe72+M2fKpxzGkpJ5NziV/HnJyEht7+jiYq+29urg0DA/jFevWl5VXcu1oamppbunLyE+1uF0sStu2bJFLpebpmipRGx3OEZGxlKSEymKamtrl0olOp02NTWpra2zYE4engsAbjrBE088cdMrHRsz6fVIuOFj6Uail73tRKuN8Hp9Nrt9yeJSt8cjlUjsdodKqTSbLXK5PC8vl73SOTA4lJWVHqnXNVxrjo+P9fq8IqHQ6/NlZqRlZaW3tXeGR4Q7Hc7lyxdfa2yRy6Th4eFDwyORen3/wOCs3GyDQV9RWRUZqVco5KNjJqlMmpmRlpKS1NvXPys3x+F0zi8uMlssHq+3sCBfIZfRNC2VSuVyWU525vDIaFZmOltYLBYPDg5FR0dZrbbwcI1cLjebzEZjZF5ejsVsKS2d7/P7pRJJW3sn1wa5TOb1+QoL8sUiUUdHV2pqclJivEIhV6mVo6NjwSAjkUp8Xt+svByHw6FSqYaHR7j6lUrllM1ITUmKjNTbbPaR0dHZs/PcHs/84iKRSCQQCMbGTDRN2212iqICwaBIKLKMjy9bulATpu7t6WNf5ISFaXr7+qOjowYGh2JijFeuNixevCAmOmp0dCwxMZ4QwnZqVm724NCwTCYbGhp+pwaJRK/X5efnjYyOZWakpaYmjVsmli1bNDQ0bDQY9HodO0RqldLr9amUSq/XS1GURq0Zt4zb7Xa9XqfRqCmKitTrfV5vT29fSnLimMmclZWelJgwNDSydOlCpULZ29efkpLU0dml1UYMDA4pFIqhoWFuWBQKucvldrvdE1Y7wzBCgVChVBCGiYoysm1WqVRNTa1snAiEAp/PX1o6XywS+Xx+rTZCKBQKBHR0tDEmJnrMZF749kM9vf3crCXEx4rFYoGANhoidTrtwOAQf+pVKqVlfDw8LGxgcGj58sUioZCNZIZhqqqvLFw4PzU1eXR0LBAILlgwjxAyMWENBIOTQ85qter1utzc7MtVtQtL56elpTQ1tugjdcPDo3Fxsb19/RqNht8Rt8uzdOnCMI2aEDIwMEQIKZk/1+v1qZSKuvomNrzNlvHkpIToaKNGo+YWi9fjddgdS5cujIuN0WjUkwOeECKXy7iYZD+DMTwyxrWZ332DQT8yOiYUiLw+n1QimZiwJicnCgSCq1frZ+VmZ2WmazRqjUbNRQIhJCrKODsvd2zMpNNpKZqeX1zEMMzA4FBiYvzg0LBKqbTa7JMXeHh4WE9P33TDmJgYf4NTSVEUNy9yuZwfe5bxiZAwlsukra0dXBucLndWVnpGeiq34pKTk0wmk1QqDQ8PS05OHBwcPnnynD5SN24Zl8vlWm2E0+my2+zR0fgcC8DH5Ao3wKfZ4kUlJrPl6LGTK5YvkcmkNE1ThCKEqNXKmJio2NhoqVRiefvGFZqmKIqiaIqiKAFNRUUZdTptcnKiTCZdu2ZFbW1d/8CgRCKKjjYqFQqhUHCtsWXyEWflZtvtjjNny+fOLdBO/0Ur4eFhsbHRsXExcpn0nWv2hKLod24tC2mDw+Fkq92wYU1TU2tZeWV4uEYoEGRlZQwNjeh12oaGxmPHTuXPnsUwzJT1hzCZLQ0NTYUFsy2Tbt2J1OuamloTk+KGhkbHJyZysrMGB4dCyjCEYSbdOTDt2U0opKl33TVH83pKUzSh3nno/PmLSUnxGZmpIZXExkZdvFRDCElKSiCEuFzusvKKhaXz+wcG2QrZyaXe/oMQIpFI1Gp1c0ubXq+jKSpkWCIjddXVVw0Gvcvt7uruLizIHx19133MXJzQNN3fP3RDF054syYQCGaY+mBg2ptkuLsOhEIhTVPXPShN0wKBQCic9kkkpCMUmbpOfnj39vaH7OtwOEZGR2cO+IZrTVxMXjfyOzt7env7khITOju71WoV+6rY6/NdJxIoavKYBAMBfgzwF/iND+PMU8mfl5DYmzKMQ04yFKFCVpzJZElNTWYYRiAQzJqVrdVFtLS0i4Rvxczo2JhWG4FzOMCtgO/hBriZAoHAubKK3t4+sUjMT300GrVEIqmuuVJX1+DxeP0+38VLVSdPnQ3TaOQyGVsmJSX5ytX65ubWrq6e3t7+ysoqu8OhUCiSkxIvXaq+dq0p5BNmIpHQ4/bU1FytvFjV0tpOEUokErIX/Do7utraO/mFDYbIiQlrfUPjtYYmvz8wXft5beiurr7CVmu3O86eO2+12eRyGRNkensHamrrmGDQ4/GOWybEIrHdbg8PDw+pf8pmEEImxicuXa5xOBxCIe1xe2pr69j7UHU6rdliiQgPl0okAlpgMOilUsmZs+XV1VfS0lJUalVNbd3xE2dsNjtNUy6Xy+F0JcTHnjlTXnnx8pQ9UqkU/BquM3HBQGtbR0NDM00LaJoaHhkRCoWDQyNisVgoFFAUJZFI2JJOp7Oqupa9xWU6cbExLc1thkj95GFXq9VWmy08PEyn01qtdqVSEdJmXpx4Jtcsl8vq6huHhoanmbUe9o7t6aaeYYjdZheJRISQM2fK6xuaaFrAZocpKUknTp69cOGiQCiwjE+cPXehs6uHfd8gJORqa+vYvlAUlZKcWH6+8tSpc7FxMVKJ1G6zezwel8vFjtiUHYmM1A0PjZw9d6G3t48Qih/ebO9cLhe3r1wuowh1+nRZ5cWqYDAwZcDzY3LyiIVMgcEYaRmfiIoymC3jkZF6tkxGRtq5sgsVlZe7e/r4kUAIqamtO3vugsvpMhoNbN8JoWxW+4GDRzu7eqZb4OxxpxvGG59K/ryYTOaZY0+tVoW0IWTFeTyeIBOUyaROp2vfvsP7Dxw5V3YhKTGeEHK5qnbnzr1Wqy0hIe70mfL29i6czAFurlvytYCNjS1ZWemfmDEKBoOXLtc0NDStWrlUq414+ZWd99y9VS6XzbzXoUPH09KSU1OTuS3sh4Rkky7+BQKBhoam1NRkuVzW29uv1qg0avWNt2rd2pVRUYab0tPOzu72ji5CiNEQmfv2nZ0zczqdUqmUf+Hw4+4/E73s3Z83a+I+LP39A263NyUl8dq1ZpFIeN2k9mPqypV6nS4iJiYaTxifNq2t7YSQT0xgDw2PuN2exIQ4zCzAfx6ucF/fpcs1w0Mjd23f3D8wKBQKH7h/O5tt+/1+n89HCPF6p/iYncPp5D5Nz74n2NraceDgUS7J5j4R7/F4n/73Czt37WUYpvJi1UD/UEiByRiG+ctf/2WxjN+1ffPYmIl91cRvxpRtCykQDAa5trHOnjvvdrvzZ+cmTDojh5Tkvvlhx7Mvz/w9ejCliIjw675m++jTaDTtHZ2nTp0zmS0JCfGfyJmqqqqlKAp3tX46qdQqlVr1iemOTCo1ROowrQAfCtzDfX0CgaDmSt2SJaXzi4ucTte/d7x09113/O73f4uM1Hd392q1EUKhwGiMXH/b6tde3/OlL37mjZ17c7Iz2X3b2jqOHT89Pj4xb15hfX3j1bqGqCiDQCAoL6/w+wPLly2aO7eAEJKclDgwMNTx9vdhVVReZgssW7qw8mLVljs2HDt+mqYFK5YvOnL01KOP3Ge2jDNMcNXKpex9eE6n84UXXxcIBHa749FH7/vFL/4Q0rY7t23+55M7wsI0JpP53nu2/vZ3f42KMi5YMO/Klfrx8YnSBcWLFy94V1gIBf98cse2bbe7Xa7TZ8rnzS14Y+depVKRlJSg0Wj27NmfnJxkt9s3blhbVlbhcDi//a2vIE7ek0/GRSalUrF61bJP9kwVFuYjXD+1jIbIT1J3NBo15hQACfdHV1Fhvl6n/f0f/67XaR984C52Y3R01CMP31tRcUkoFGZnZ7z2+p4p901JSRKJRXv2HBgeGlm9allMTNT84qJf/PKP7E0LNbV1bMItFApvv/22o0dPRkSEBwLBEyfOsgVqr9RnpKd1dHR7vT6K8vf09GdkpBJCmGCQ/WIH9ihyufyu7XecOVPe2dnt9Xgnt62lpc3hcMyalW0ymYeGRhIT4//ry58jhMTERO3Zc6Cvb4BrcEdHt1QqzZuVk5KS1NLc5nS5crIzz5w9Hx1t1Ot0jU0tc/Jn3b7ptqKiOf/e8VJiYvzChfO337kZQQIAAACAhPv9CwaD8fGxP3z8O7/7/d8G3v21CVN+Qp9/K8jhIyfEYvGKFUuamlq5jQqFLCcnUxsRzn0MixASHxerjQivqa3Lyc7iFxgbM72xc29GRtrExETlxct3brudECKVSm02+8SElb1i0d3de+Toya1bNvbyUueQtsXHx+XPzp0zJ8/n9QkEAoqiDh0+Prlt+bNz2avdebNy9u0/RAhVPK/wytX6rMyM5OSEBQvmXblaj5AAAAAAQMJ9M+0/cPTChYtisVilUhre/lT7ZHK5fHh49P9+8uvx8Ym8WTkikbCltU0gENTUXHV7POmpyWFhmsrKqqgoQ0nJvJdf2ZmelpKZkVZQMJurYeXKpceOnxYIaH6BzMz04ZHRFcsXa7XhjY0ter2OEKJUKhYunP+DJ36u00aEhWnWrF7e3z/4yqu7zWbzlG1LT089cvTkocPHBbRg0aIS7oUB1zau5Kuv7zlbdiE+Lvau7ZvtdqdSKVcqFaULinc8+3LerOzw8DD+iwRCiEIhf+nlnV/9ymOIEwAAAIAp4VtKABC9AAAAcAvhW0oAAAAAAJBwAwAAAAAg4QYAAAAAACTcAAAAAABIuAEAAAAAkHBPRyIRO51ODC587IyOmiQSMcYBAAAAPuoJd1iYZnTUhMGFjx2n0xkWpsE4AAAAwE10S76HmxDS3z/o9/vlcrler8Uow8ci1R4dNQmFwpiYKIwGAAAAfAwSbkKI2WwZH5/weLwYZfjok0jEYWGaiIhwDAUAAAB8bBJuAAAAAADAt5QAAAAAACDhBgAAAABAwg0AAAAAAEi4AQAAAACQcAMAAAAAIOEGAAAAAAAk3AAAAAAASLgBAAAAAD6JhLeoXp/PZzabHQ4HfljnU4WiKIVCERERIRKJECHwQSIEQYIgwWkEPvhpBOCjEre34jzl8/n6+vrUarVUKpVKpRjlT5Xx8XGr1RobGzvDqRARggiZOUIQJAgSnEbgg59GAD7hCffw8LBQKAwLC8P4fmpPhX6/32AwIELg/UUIggRwGoEPfhoB+Oi4JfdwOxwOnAQ/zaRSqcPhQITA+44QBAngNAIf/DQC8AlPuHE7Hc6DM8cAIgQRct0YQJAgSHAagQ94GgH46Pj/9/s6hohPsqQAAAAASUVORK5CYII=" alt="Sentinel-2" loading="eager">
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

st.subheader("Camera Geolocation")

geo_col1, geo_col2 = st.columns(2)

with geo_col1:
    camera_latitude = st.number_input(
        "Latitude",
        min_value=-90.0,
        max_value=90.0,
        value=9.7489,
        step=0.0001,
        format="%.6f",
        help="WGS84 latitude. Replace the default with the actual camera coordinate.",
    )

with geo_col2:
    camera_longitude = st.number_input(
        "Longitude",
        min_value=-180.0,
        max_value=180.0,
        value=-83.7534,
        step=0.0001,
        format="%.6f",
        help="WGS84 longitude. Replace the default with the actual camera coordinate.",
    )

camera_map_df = pd.DataFrame({"lat": [camera_latitude], "lon": [camera_longitude]})
st.map(camera_map_df, zoom=7)

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
        "Upload a camera-trap video to begin the Edge AI analysis. "
        "You can still review the satellite and Edge-node modules below."
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
# 3. COPERNICUS / SENTINEL CONTEXT
# =========================================================

st.header("3. Copernicus / Sentinel Environmental Context")

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


# =========================================================
# 4. EDGE MONITORING NODE
# =========================================================

st.header("4. Edge Monitoring Node")

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



# =========================================================
# ANALYSIS AVAILABILITY GUARD
# =========================================================

if not video_ready:
    st.stop()


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
# 6. DETECTION CONFIDENCE STATISTICS
# =========================================================

st.header("6. Detection Confidence Statistics")

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
# 7. 5G COMMUNICATION LAYER
# =========================================================

st.header("7. 5G Communication Layer")

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
# 8. EDGE-TO-SCIENCE WORKFLOW
# =========================================================

st.header("8. Edge-to-Science Workflow")

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

workflow_html = '<div class="workflow-container">'

for number, title, description in workflow:
    workflow_html += f"""
        <div class="workflow-row">
            <div class="workflow-number">{number}</div>
            <div class="workflow-title">{title}</div>
            <div class="workflow-description">{description}</div>
        </div>
    """

workflow_html += "</div>"

st.markdown(
    workflow_html,
    unsafe_allow_html=True,
)

# =========================================================
# 9. EDGE FILTERING CHART
# =========================================================

st.header("9. Edge Filtering Outcome")

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
# 10. TEMPORAL CONFIDENCE PROFILE
# =========================================================

st.header("10. Temporal Detection Confidence")

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
# 11. CONFIDENCE DISTRIBUTION
# =========================================================

st.header("11. Detection Confidence Distribution")

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
# 12. DATA REDUCTION
# =========================================================

st.header("12. Estimated Candidate Data Reduction")

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
# 13. CANDIDATE ANIMAL IMAGES
# =========================================================

st.header("13. Candidate Animal Images")

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

    candidates_zip = create_candidates_zip(
        observation["observation_id"],
        candidate_images,
    )

    st.download_button(
        label="Download all candidate images · ZIP",
        data=candidates_zip,
        file_name=safe_filename(observation["observation_id"]) + "_candidate_images.zip",
        mime="application/zip",
        use_container_width=True,
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
                    label="Download PNG",
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
            f"Showing the first 12 of {len(candidate_images)} candidates. "
            "The ZIP contains all retained images."
        )

# =========================================================
# 14. FRAME-LEVEL EDGE DECISIONS
# =========================================================

st.header("14. Frame-Level Edge Decisions")

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
# 15. SCIENTIFIC OBSERVATION
# =========================================================

st.header("15. Scientific Observation")

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
    "Save Observation to JaguarID Registry",
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
# 16. OBSERVATION REGISTRY
# =========================================================

st.header("16. Observation Registry")

st.markdown(
    """
    <div class="section-intro">
        Observations saved during the current application session.
        This registry is temporary and is not yet a persistent database.
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
# 17. FRAME-LEVEL DATA
# =========================================================

st.header("17. Frame-Level Analysis Data")

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
# 18. SCIENTIFIC REPORT
# =========================================================

st.header("18. Scientific Observation Report")

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
    )

    st.caption(
        "The report includes observation metadata, Edge AI metrics, confidence "
        "statistics, estimated network metrics, Sentinel acquisition context, "
        "annotations and up to six candidate animal images."
    )

except Exception as pdf_error:
    st.error(
        "The video analysis was completed successfully, but the PDF report could not be generated."
    )
    st.code(str(pdf_error))

# =========================================================
# 19. ANALYSIS SUMMARY
# =========================================================

st.divider()
st.header("19. Analysis Summary")

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
