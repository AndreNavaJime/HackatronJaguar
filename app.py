# -*- coding: utf-8 -*-

"""
=========================================================
JAGUARID
EDGE WILDLIFE INTELLIGENCE
HACKATRON 5G
=========================================================

WORKFLOW

Camera Trap
    ↓
Edge AI
    ↓
MegaDetector V6
    ↓
Wildlife Event Filtering
    ↓
Candidate Animal Images
    ↓
Reduced 5G Payload
    ↓
JaguarID Scientific Observation
    ↓
Researcher Validation
    ↓
Individual Encounter Registry


IMPORTANT

MegaDetector:
- Detects animal / person / vehicle
- DOES NOT identify species
- DOES NOT identify individual animals

Species identification and individual IDs are currently
researcher-provided annotations.

Future validated downstream models could add:
- species classification
- jaguar validation
- individual re-identification
=========================================================
"""


# =========================================================
# IMPORTS
# =========================================================

import io
import os
import re
import tempfile
import time
import uuid
import zipfile

from datetime import datetime
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import torch

from PytorchWildlife.models import detection as pw_detection

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
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
    page_title="JaguarID | Wildlife Observation Platform",
    page_icon="🐆",
    layout="wide",
)


# =========================================================
# SCIENTIFIC UI
# =========================================================

st.markdown(
    """
    <style>

    html, body, [class*="css"] {
        font-family:
            "Civis",
            "Source Sans 3",
            "Source Sans Pro",
            "Segoe UI",
            Arial,
            sans-serif;
    }

    .block-container {
        max-width: 1380px;
        padding-top: 2rem;
        padding-bottom: 5rem;
    }

    h1 {
        font-size: 2.25rem !important;
        font-weight: 650 !important;
        letter-spacing: -0.035em;
        margin-bottom: 0.15rem !important;
    }

    h2 {
        font-size: 1.45rem !important;
        font-weight: 620 !important;
        letter-spacing: -0.02em;
        margin-top: 2.2rem !important;
        margin-bottom: 0.8rem !important;
    }

    h3 {
        font-weight: 600 !important;
        letter-spacing: -0.01em;
    }

    p {
        line-height: 1.55;
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(120, 120, 120, 0.22);
        border-radius: 8px;
        padding: 0.95rem 1rem;
        background: rgba(120, 120, 120, 0.025);
    }

    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem;
        letter-spacing: 0.025em;
        text-transform: uppercase;
        opacity: 0.72;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 600;
    }

    .jaguarid-kicker {
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        opacity: 0.60;
        margin-bottom: 0.35rem;
    }

    .jaguarid-subtitle {
        max-width: 820px;
        font-size: 1rem;
        opacity: 0.82;
        margin-bottom: 0.5rem;
    }

    .technical-strip {
        margin-top: 0.7rem;
        margin-bottom: 1.5rem;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        opacity: 0.58;
    }

    .scientific-note {
        border-left: 3px solid rgba(90, 90, 90, 0.65);
        padding: 0.75rem 1rem;
        margin-top: 0.75rem;
        margin-bottom: 1.25rem;
        background: rgba(120, 120, 120, 0.04);
        font-size: 0.88rem;
        line-height: 1.5;
    }

    .workflow-container {
        margin-top: 0.8rem;
        border-top: 1px solid rgba(120, 120, 120, 0.18);
    }

    .workflow-row {
        display: grid;
        grid-template-columns: 70px minmax(160px, 230px) 1fr;
        gap: 1rem;
        align-items: start;
        padding: 0.85rem 0;
        border-bottom: 1px solid rgba(120, 120, 120, 0.18);
    }

    .workflow-number {
        font-size: 0.74rem;
        letter-spacing: 0.10em;
        opacity: 0.48;
        padding-top: 0.1rem;
    }

    .workflow-title {
        font-weight: 620;
        font-size: 0.95rem;
    }

    .workflow-description {
        opacity: 0.72;
        font-size: 0.88rem;
        line-height: 1.45;
    }

    .section-intro {
        font-size: 0.90rem;
        opacity: 0.72;
        max-width: 850px;
        margin-bottom: 1rem;
    }

    .candidate-metadata {
        font-size: 0.77rem;
        opacity: 0.68;
        margin-top: -0.25rem;
        margin-bottom: 0.4rem;
    }

    .prototype-box {
        padding: 1rem 1.1rem;
        border: 1px solid rgba(120, 120, 120, 0.22);
        border-radius: 8px;
        background: rgba(120, 120, 120, 0.025);
        margin-top: 0.5rem;
    }

    @media (max-width: 700px) {

        .workflow-row {
            grid-template-columns: 45px 1fr;
        }

        .workflow-description {
            grid-column: 2;
        }
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SESSION STATE
# =========================================================

if "observation_registry" not in st.session_state:
    st.session_state.observation_registry = []

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "current_uploaded_file" not in st.session_state:
    st.session_state.current_uploaded_file = None


# =========================================================
# GENERAL HELPERS
# =========================================================

def safe_filename(text):

    text = str(text).strip()

    if not text:
        return "JaguarID_Observation"

    text = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        text,
    )

    text = text.strip("_")

    return text or "JaguarID_Observation"


def escape_pdf_text(text):

    text = str(text)

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def image_to_png_bytes(rgb_image):
    """
    Convert RGB numpy image into PNG bytes.
    """

    bgr_image = cv2.cvtColor(
        rgb_image,
        cv2.COLOR_RGB2BGR,
    )

    success, encoded = cv2.imencode(
        ".png",
        bgr_image,
    )

    if not success:
        return None

    return encoded.tobytes()


def create_candidates_zip(
    observation_id,
    candidate_images,
):
    """
    Package all retained wildlife candidate crops
    into one ZIP archive.
    """

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:

        for index, candidate in enumerate(
            candidate_images,
            start=1,
        ):

            png_data = image_to_png_bytes(
                candidate["image"]
            )

            if png_data is None:
                continue

            time_string = (
                f"{candidate['time']:.1f}"
                .replace(".", "_")
            )

            filename = (
                f"{safe_filename(observation_id)}"
                f"_candidate_{index:03d}"
                f"_t{time_string}s.png"
            )

            archive.writestr(
                filename,
                png_data,
            )

    zip_buffer.seek(0)

    return zip_buffer.getvalue()


def figure_to_png_bytes(
    figure,
    dpi=300,
):
    """
    Export a matplotlib figure as publication-quality PNG.
    """

    buffer = io.BytesIO()

    figure.savefig(
        buffer,
        format="png",
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
    )

    buffer.seek(0)

    return buffer.getvalue()


# =========================================================
# MEGADETECTOR
# =========================================================

@st.cache_resource
def load_model():

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    model = pw_detection.MegaDetectorV6(
        device=device,
        pretrained=True,
        version="MDV6-yolov9-c",
    )

    return model, device


# =========================================================
# PDF REPORT
# =========================================================

def create_observation_pdf(
    observation,
    candidate_images,
):

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
        leading=27,
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

    story = []

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "JaguarID",
            title_style,
        )
    )

    story.append(
        Paragraph(
            (
                "EDGE WILDLIFE INTELLIGENCE · "
                "SCIENTIFIC OBSERVATION REPORT"
            ),
            subtitle_style,
        )
    )

    # -----------------------------------------------------
    # OBSERVATION SUMMARY
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "Observation Summary",
            section_style,
        )
    )

    summary_data = [
        [
            "Observation ID",
            escape_pdf_text(
                observation["observation_id"]
            ),
        ],
        [
            "Observation name",
            escape_pdf_text(
                observation["observation_name"]
            ),
        ],
        [
            "Analysis date",
            (
                f'{observation["analysis_date"]} '
                f'{observation["analysis_time"]}'
            ),
        ],
        [
            "Observer / Researcher",
            escape_pdf_text(
                observation["observer"]
            ),
        ],
        [
            "Camera / Station",
            escape_pdf_text(
                observation["camera_id"]
            ),
        ],
        [
            "Study site",
            escape_pdf_text(
                observation["study_site"]
            ),
        ],
        [
            "Species annotation",
            escape_pdf_text(
                observation["species"]
            ),
        ],
        [
            "Individual ID",
            escape_pdf_text(
                observation["individual_id"]
            ),
        ],
        [
            "Source video",
            escape_pdf_text(
                observation["source_video"]
            ),
        ],
    ]

    summary_table = Table(
        summary_data,
        colWidths=[
            5 * cm,
            11 * cm,
        ],
    )

    summary_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#F3F4F5"),
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold",
                ),
                (
                    "FONTNAME",
                    (1, 0),
                    (1, -1),
                    "Helvetica",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#C9CDD1"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(
        summary_table
    )

    # -----------------------------------------------------
    # EDGE AI ANALYSIS
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "Edge AI Analysis",
            section_style,
        )
    )

    analysis_data = [
        [
            "Video duration",
            f'{observation["duration_seconds"]:.1f} s',
        ],
        [
            "Resolution",
            observation["resolution"],
        ],
        [
            "Frame rate",
            f'{observation["fps"]:.1f} FPS',
        ],
        [
            "Frames analyzed",
            str(
                observation["frames_analyzed"]
            ),
        ],
        [
            "Frames retained",
            str(
                observation["frames_retained"]
            ),
        ],
        [
            "Frames discarded",
            str(
                observation["frames_discarded"]
            ),
        ],
        [
            "Animal detections",
            str(
                observation["animal_detections"]
            ),
        ],
        [
            "Person detections",
            str(
                observation["person_detections"]
            ),
        ],
        [
            "Vehicle detections",
            str(
                observation["vehicle_detections"]
            ),
        ],
        [
            "Maximum animal confidence",
            f'{observation["maximum_animal_confidence"]:.1%}',
        ],
        [
            "Estimated payload reduction",
            f'{observation["estimated_payload_reduction"]:.1f}%',
        ],
        [
            "Inference device",
            observation["device"],
        ],
        [
            "Processing time",
            f'{observation["processing_seconds"]:.1f} s',
        ],
    ]

    analysis_table = Table(
        analysis_data,
        colWidths=[
            7 * cm,
            9 * cm,
        ],
    )

    analysis_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#F3F4F5"),
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#C9CDD1"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(
        analysis_table
    )

    # -----------------------------------------------------
    # RESEARCH NOTES
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "Research Notes",
            section_style,
        )
    )

    story.append(
        Paragraph(
            escape_pdf_text(
                observation["notes"]
            ),
            styles["BodyText"],
        )
    )

    story.append(
        Spacer(
            1,
            12,
        )
    )

    story.append(
        Paragraph(
            (
                "<b>Interpretation note:</b> "
                "MegaDetector performs object detection for animals, "
                "people and vehicles. Species and individual identity "
                "included in this report are researcher-provided "
                "annotations unless a validated downstream model "
                "is integrated."
            ),
            note_style,
        )
    )

    # -----------------------------------------------------
    # CANDIDATE IMAGES
    # -----------------------------------------------------

    if len(candidate_images) > 0:

        story.append(
            PageBreak()
        )

        story.append(
            Paragraph(
                "Candidate Animal Images",
                section_style,
            )
        )

        story.append(
            Paragraph(
                (
                    "Animal detections retained by the Edge filtering "
                    "stage for scientific review."
                ),
                styles["BodyText"],
            )
        )

        story.append(
            Spacer(
                1,
                10,
            )
        )

        for index, candidate in enumerate(
            candidate_images[:6],
            start=1,
        ):

            rgb_image = (
                candidate["image"]
            )

            bgr_image = cv2.cvtColor(
                rgb_image,
                cv2.COLOR_RGB2BGR,
            )

            success_encode, encoded = cv2.imencode(
                ".jpg",
                bgr_image,
            )

            if not success_encode:
                continue

            image_buffer = io.BytesIO(
                encoded.tobytes()
            )

            img_height, img_width = (
                rgb_image.shape[:2]
            )

            max_width = 12 * cm
            max_height = 8 * cm

            if img_height > 0:
                aspect = (
                    img_width
                    /
                    img_height
                )
            else:
                aspect = 1

            pdf_width = max_width
            pdf_height = (
                pdf_width
                /
                aspect
            )

            if pdf_height > max_height:

                pdf_height = max_height

                pdf_width = (
                    pdf_height
                    *
                    aspect
                )

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
                        f"Candidate {index:02d} · "
                        f"Video time {candidate['time']:.1f} s · "
                        f"MegaDetector confidence "
                        f"{candidate['confidence']:.2f}"
                    ),
                    caption_style,
                )
            )

    doc.build(
        story
    )

    buffer.seek(0)

    return buffer.getvalue()


# =========================================================
# APPLICATION HEADER
# =========================================================

st.markdown(
    """
    <div class="jaguarid-kicker">
        Wildlife Monitoring Research Prototype
    </div>
    """,
    unsafe_allow_html=True,
)

st.title(
    "JaguarID"
)

st.markdown(
    """
    <div class="jaguarid-subtitle">
        Edge-assisted processing of camera-trap video for structured
        wildlife observations and reduced transmission of non-relevant data.
    </div>

    <div class="technical-strip">
        Camera Trap · Edge AI · MegaDetector V6 · 5G · Observation Registry
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header(
    "Analysis Parameters"
)

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
    (
        "MegaDetector inference is executed in the cloud runtime. "
        "For this prototype, 5–10 sampled frames provide a practical "
        "balance between analysis coverage and CPU processing time."
    )
)

st.sidebar.divider()

st.sidebar.caption(
    "JaguarID · Hackatron 5G"
)


# =========================================================
# 1. OBSERVATION METADATA
# =========================================================

st.header(
    "1. Observation Metadata"
)

st.markdown(
    """
    <div class="section-intro">
        Research context supplied by the observer. Species and individual
        identity are manual scientific annotations in the current prototype.
    </div>
    """,
    unsafe_allow_html=True,
)

meta_col1, meta_col2 = (
    st.columns(2)
)

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
        placeholder="Example: Sector A",
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
        "Behavior, habitat context, environmental conditions, "
        "sex, age class, direction of movement, camera conditions "
        "or other relevant observations."
    ),
)

st.markdown(
    """
    <div class="scientific-note">
        <b>Methodological note.</b>
        MegaDetector identifies the presence of animals, people and vehicles.
        It does not identify species or individual animals. Species and
        individual IDs entered here represent researcher annotations.
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 2. CAMERA-TRAP VIDEO
# =========================================================

st.header(
    "2. Camera-Trap Video"
)

uploaded_video = st.file_uploader(
    "Select video",
    type=[
        "avi",
        "mp4",
        "mov",
        "mkv",
    ],
)

if uploaded_video is None:

    st.info(
        "Upload a camera-trap video to begin the analysis."
    )

    st.stop()


# =========================================================
# RESET ANALYSIS WHEN VIDEO CHANGES
# =========================================================

current_file_signature = (
    uploaded_video.name,
    uploaded_video.size,
)

if (
    st.session_state.current_uploaded_file
    != current_file_signature
):

    st.session_state.current_uploaded_file = (
        current_file_signature
    )

    st.session_state.analysis_result = None


# =========================================================
# VIDEO PREVIEW
# =========================================================

st.success(
    f"Loaded: {uploaded_video.name}"
)

try:

    st.video(
        uploaded_video.getvalue()
    )

except Exception:

    st.warning(
        (
            "The browser could not preview this video format. "
            "The file may still be processed by OpenCV."
        )
    )


# =========================================================
# RUN ANALYSIS
# =========================================================

run_analysis = st.button(
    "Run Edge Analysis",
    type="primary",
    use_container_width=True,
)


# =========================================================
# PROCESS VIDEO
# =========================================================

if run_analysis:

    # -----------------------------------------------------
    # SAVE TEMP VIDEO
    # -----------------------------------------------------

    video_suffix = (
        Path(
            uploaded_video.name
        ).suffix
    )

    if video_suffix == "":
        video_suffix = ".avi"

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=video_suffix,
    ) as temp_video:

        temp_video.write(
            uploaded_video.getvalue()
        )

        video_path = (
            temp_video.name
        )

    # -----------------------------------------------------
    # OPEN VIDEO
    # -----------------------------------------------------

    cap = cv2.VideoCapture(
        video_path
    )

    if not cap.isOpened():

        try:
            os.remove(
                video_path
            )
        except Exception:
            pass

        st.error(
            "OpenCV could not open the uploaded video."
        )

        st.stop()

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    total_frames = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    if fps <= 0:
        fps = 30.0

    duration = (
        total_frames
        /
        fps
        if fps > 0
        else 0
    )

    # -----------------------------------------------------
    # VIDEO INFORMATION
    # -----------------------------------------------------

    st.subheader(
        "Video Characteristics"
    )

    c1, c2, c3, c4 = (
        st.columns(4)
    )

    c1.metric(
        "Duration",
        f"{duration:.1f} s",
    )

    c2.metric(
        "Frame rate",
        f"{fps:.1f} FPS",
    )

    c3.metric(
        "Resolution",
        f"{width} × {height}",
    )

    c4.metric(
        "Total frames",
        f"{total_frames:,}",
    )

    # -----------------------------------------------------
    # LOAD MODEL
    # -----------------------------------------------------

    st.subheader(
        "Edge Inference"
    )

    with st.spinner(
        "Initializing MegaDetector V6..."
    ):

        model, device = (
            load_model()
        )

    st.success(
        (
            "MegaDetector V6 initialized · "
            f"{device.upper()} inference"
        )
    )

    st.caption(
        (
            "Model output classes: animal, person and vehicle. "
            "Species and individual identity are not inferred at this stage."
        )
    )

    # -----------------------------------------------------
    # CLASS LABELS
    # -----------------------------------------------------

    CLASS_NAMES = {
        0: "animal",
        1: "person",
        2: "vehicle",
    }

    frame_interval = max(
        1,
        int(
            fps
            *
            sample_seconds
        ),
    )

    # -----------------------------------------------------
    # ANALYSIS VARIABLES
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # PROGRESS
    # -----------------------------------------------------

    st.subheader(
        "Processing"
    )

    progress_bar = st.progress(
        0
    )

    status_text = st.empty()

    live_image = st.empty()

    processing_start = (
        time.time()
    )

    # -----------------------------------------------------
    # FRAME LOOP
    # -----------------------------------------------------

    while True:

        success, frame = (
            cap.read()
        )

        if not success:
            break

        if (
            frame_number
            %
            frame_interval
            != 0
        ):

            frame_number += 1

            continue

        sample_number += 1

        if sample_number > max_samples:
            break

        video_time = (
            frame_number
            /
            fps
        )

        status_text.write(
            (
                f"Analyzing sample "
                f"{sample_number}/{max_samples} · "
                f"video time {video_time:.1f} s"
            )
        )

        # -------------------------------------------------
        # TEMP FRAME
        # -------------------------------------------------

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".jpg",
        ) as temp_frame:

            frame_path = (
                temp_frame.name
            )

        cv2.imwrite(
            frame_path,
            frame,
        )

        try:

            frame_bytes = (
                Path(
                    frame_path
                )
                .stat()
                .st_size
            )

        except Exception:

            frame_bytes = 0

        total_input_bytes += (
            frame_bytes
        )

        # -------------------------------------------------
        # MODEL INFERENCE
        # -------------------------------------------------

        inference_start = (
            time.time()
        )

        try:

            result = (
                model.single_image_detection(
                    frame_path,
                    det_conf_thres=confidence_threshold,
                )
            )

        except Exception as error:

            try:
                os.remove(
                    frame_path
                )
            except Exception:
                pass

            cap.release()

            try:
                os.remove(
                    video_path
                )
            except Exception:
                pass

            st.error(
                (
                    "MegaDetector inference failed: "
                    f"{error}"
                )
            )

            st.stop()

        inference_seconds = (
            time.time()
            -
            inference_start
        )

        detections = (
            result["detections"]
        )

        try:
            os.remove(
                frame_path
            )
        except Exception:
            pass

        # -------------------------------------------------
        # FRAME COUNTERS
        # -------------------------------------------------

        animal_count = 0

        person_count = 0

        vehicle_count = 0

        max_animal_confidence = 0.0

        candidate_bytes_frame = 0

        annotated = (
            frame.copy()
        )

        # -------------------------------------------------
        # DETECTIONS
        # -------------------------------------------------

        if (
            detections is not None
            and
            len(detections) > 0
        ):

            boxes = (
                detections.xyxy
            )

            confidences = (
                detections.confidence
            )

            class_ids = (
                detections.class_id
            )

            for detection_index in range(
                len(boxes)
            ):

                confidence = float(
                    confidences[
                        detection_index
                    ]
                )

                class_id = int(
                    class_ids[
                        detection_index
                    ]
                )

                label = (
                    CLASS_NAMES.get(
                        class_id,
                        "unknown",
                    )
                )

                x1, y1, x2, y2 = [
                    int(value)
                    for value
                    in boxes[
                        detection_index
                    ]
                ]

                # -----------------------------------------
                # LIMIT COORDINATES
                # -----------------------------------------

                x1 = max(
                    0,
                    min(
                        x1,
                        width - 1,
                    ),
                )

                y1 = max(
                    0,
                    min(
                        y1,
                        height - 1,
                    ),
                )

                x2 = max(
                    x1 + 1,
                    min(
                        x2,
                        width,
                    ),
                )

                y2 = max(
                    y1 + 1,
                    min(
                        y2,
                        height,
                    ),
                )

                # -----------------------------------------
                # ANIMAL
                # -----------------------------------------

                if label == "animal":

                    animal_count += 1

                    total_animals += 1

                    max_animal_confidence = max(
                        max_animal_confidence,
                        confidence,
                    )

                    crop = frame[
                        y1:y2,
                        x1:x2,
                    ]

                    if crop.size > 0:

                        crop_rgb = cv2.cvtColor(
                            crop,
                            cv2.COLOR_BGR2RGB,
                        )

                        candidate_images.append(
                            {
                                "image":
                                    crop_rgb,

                                "confidence":
                                    confidence,

                                "time":
                                    video_time,

                                "sample":
                                    sample_number,
                            }
                        )

                        success_encode, encoded = (
                            cv2.imencode(
                                ".jpg",
                                crop,
                            )
                        )

                        if success_encode:

                            crop_bytes = (
                                len(
                                    encoded
                                )
                            )

                            candidate_bytes_frame += (
                                crop_bytes
                            )

                            total_candidate_bytes += (
                                crop_bytes
                            )

                # -----------------------------------------
                # PERSON
                # -----------------------------------------

                elif label == "person":

                    person_count += 1

                    total_people += 1

                # -----------------------------------------
                # VEHICLE
                # -----------------------------------------

                elif label == "vehicle":

                    vehicle_count += 1

                    total_vehicles += 1

                # -----------------------------------------
                # DRAW DETECTION
                # -----------------------------------------

                cv2.rectangle(
                    annotated,
                    (
                        x1,
                        y1,
                    ),
                    (
                        x2,
                        y2,
                    ),
                    (
                        0,
                        255,
                        0,
                    ),
                    2,
                )

                detection_label = (
                    f"{label.upper()} "
                    f"{confidence:.2f}"
                )

                cv2.putText(
                    annotated,
                    detection_label,
                    (
                        x1,
                        max(
                            30,
                            y1 - 10,
                        ),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (
                        0,
                        255,
                        0,
                    ),
                    2,
                )

        # -------------------------------------------------
        # EDGE DECISION
        # -------------------------------------------------

        keep = (
            animal_count > 0
        )

        if keep:

            frames_kept += 1

            decision = (
                "RETAIN · ANIMAL EVENT"
            )

        else:

            frames_discarded += 1

            decision = (
                "DISCARD · NO ANIMAL EVENT"
            )

        # -------------------------------------------------
        # FRAME OVERLAY
        # -------------------------------------------------

        cv2.rectangle(
            annotated,
            (
                0,
                0,
            ),
            (
                min(
                    width,
                    780,
                ),
                135,
            ),
            (
                0,
                0,
                0,
            ),
            -1,
        )

        cv2.putText(
            annotated,
            "JAGUARID · EDGE INFERENCE",
            (
                20,
                32,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (
                255,
                255,
                255,
            ),
            2,
        )

        cv2.putText(
            annotated,
            (
                f"Video time: "
                f"{video_time:.1f} s"
            ),
            (
                20,
                64,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (
                255,
                255,
                255,
            ),
            1,
        )

        cv2.putText(
            annotated,
            (
                f"Decision: "
                f"{decision}"
            ),
            (
                20,
                96,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (
                255,
                255,
                255,
            ),
            1,
        )

        cv2.putText(
            annotated,
            (
                "Max animal confidence: "
                f"{max_animal_confidence:.2f}"
            ),
            (
                20,
                126,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (
                255,
                255,
                255,
            ),
            1,
        )

        annotated_rgb = cv2.cvtColor(
            annotated,
            cv2.COLOR_BGR2RGB,
        )

        annotated_images.append(
            {
                "image":
                    annotated_rgb,

                "time":
                    video_time,

                "decision":
                    decision,
            }
        )

        live_image.image(
            annotated_rgb,
            caption=(
                f"Sample {sample_number} · "
                f"{decision}"
            ),
            use_container_width=True,
        )

        # -------------------------------------------------
        # STRUCTURED RECORD
        # -------------------------------------------------

        records.append(
            {
                "sample":
                    sample_number,

                "video_time_seconds":
                    round(
                        video_time,
                        2,
                    ),

                "animals":
                    animal_count,

                "persons":
                    person_count,

                "vehicles":
                    vehicle_count,

                "max_animal_confidence":
                    round(
                        max_animal_confidence,
                        4,
                    ),

                "edge_decision":
                    (
                        "RETAIN"
                        if keep
                        else "DISCARD"
                    ),

                "input_jpeg_bytes":
                    frame_bytes,

                "candidate_jpeg_bytes":
                    candidate_bytes_frame,

                "inference_seconds":
                    round(
                        inference_seconds,
                        3,
                    ),
            }
        )

        progress_value = min(
            sample_number
            /
            max_samples,
            1.0,
        )

        progress_bar.progress(
            progress_value
        )

        frame_number += 1

    # -----------------------------------------------------
    # CLOSE VIDEO
    # -----------------------------------------------------

    cap.release()

    try:
        os.remove(
            video_path
        )
    except Exception:
        pass

    processing_seconds = (
        time.time()
        -
        processing_start
    )

    progress_bar.progress(
        1.0
    )

    status_text.success(
        "Edge analysis completed."
    )

    # -----------------------------------------------------
    # DATAFRAME
    # -----------------------------------------------------

    df = pd.DataFrame(
        records
    )

    if len(df) == 0:

        st.error(
            "No frames were processed."
        )

        st.stop()

    # -----------------------------------------------------
    # METRICS
    # -----------------------------------------------------

    total_samples = len(
        df
    )

    keep_percentage = (
        frames_kept
        /
        total_samples
        *
        100
    )

    discard_percentage = (
        frames_discarded
        /
        total_samples
        *
        100
    )

    input_mb = (
        total_input_bytes
        /
        1024
        /
        1024
    )

    candidate_mb = (
        total_candidate_bytes
        /
        1024
        /
        1024
    )

    if total_input_bytes > 0:

        payload_reduction = (
            (
                total_input_bytes
                -
                total_candidate_bytes
            )
            /
            total_input_bytes
            *
            100
        )

    else:

        payload_reduction = 0

    average_inference = float(
        df[
            "inference_seconds"
        ].mean()
    )

    max_confidence_global = float(
        df[
            "max_animal_confidence"
        ].max()
    )

    # -----------------------------------------------------
    # STRUCTURED OBSERVATION
    # -----------------------------------------------------

    analysis_timestamp = (
        datetime.now()
    )

    observation_id = (
        "OBS-"
        +
        analysis_timestamp.strftime(
            "%Y%m%d"
        )
        +
        "-"
        +
        uuid.uuid4().hex[
            :6
        ].upper()
    )

    observation = {

        "observation_id":
            observation_id,

        "observation_name":
            (
                observation_name.strip()
                if observation_name.strip()
                else observation_id
            ),

        "analysis_date":
            analysis_timestamp.strftime(
                "%Y-%m-%d"
            ),

        "analysis_time":
            analysis_timestamp.strftime(
                "%H:%M:%S"
            ),

        "observer":
            (
                observer_name.strip()
                or "Not specified"
            ),

        "camera_id":
            (
                camera_id.strip()
                or "Not specified"
            ),

        "study_site":
            (
                study_site.strip()
                or "Not specified"
            ),

        "species":
            (
                species_label.strip()
                or "Unassigned"
            ),

        "individual_id":
            (
                individual_id.strip()
                or "Unassigned"
            ),

        "notes":
            (
                observation_notes.strip()
                or "No notes"
            ),

        "source_video":
            uploaded_video.name,

        "duration_seconds":
            round(
                duration,
                2,
            ),

        "resolution":
            f"{width} × {height}",

        "fps":
            round(
                fps,
                2,
            ),

        "frames_analyzed":
            total_samples,

        "frames_retained":
            frames_kept,

        "frames_discarded":
            frames_discarded,

        "animal_detections":
            total_animals,

        "person_detections":
            total_people,

        "vehicle_detections":
            total_vehicles,

        "maximum_animal_confidence":
            round(
                max_confidence_global,
                4,
            ),

        "estimated_payload_reduction":
            round(
                payload_reduction,
                2,
            ),

        "processing_seconds":
            round(
                processing_seconds,
                2,
            ),

        "device":
            str(
                device
            ).upper(),
    }

    # -----------------------------------------------------
    # STORE ANALYSIS
    # -----------------------------------------------------

    st.session_state.analysis_result = {

        "observation":
            observation,

        "df":
            df,

        "candidate_images":
            candidate_images,

        "annotated_images":
            annotated_images,

        "frames_kept":
            frames_kept,

        "frames_discarded":
            frames_discarded,

        "discard_percentage":
            discard_percentage,

        "keep_percentage":
            keep_percentage,

        "payload_reduction":
            payload_reduction,

        "input_mb":
            input_mb,

        "candidate_mb":
            candidate_mb,

        "average_inference":
            average_inference,

        "total_animals":
            total_animals,

        "total_people":
            total_people,

        "total_vehicles":
            total_vehicles,

        "confidence_threshold":
            confidence_threshold,
    }


# =========================================================
# REQUIRE ANALYSIS
# =========================================================

if (
    st.session_state.analysis_result
    is None
):

    st.info(
        "Run the Edge analysis to continue."
    )

    st.stop()


# =========================================================
# RESTORE ANALYSIS
# =========================================================

result = (
    st.session_state.analysis_result
)

observation = (
    result["observation"]
)

df = (
    result["df"]
)

candidate_images = (
    result["candidate_images"]
)

annotated_images = (
    result["annotated_images"]
)

frames_kept = (
    result["frames_kept"]
)

frames_discarded = (
    result["frames_discarded"]
)

discard_percentage = (
    result["discard_percentage"]
)

keep_percentage = (
    result["keep_percentage"]
)

payload_reduction = (
    result["payload_reduction"]
)

input_mb = (
    result["input_mb"]
)

candidate_mb = (
    result["candidate_mb"]
)

average_inference = (
    result["average_inference"]
)

total_animals = (
    result["total_animals"]
)

total_people = (
    result["total_people"]
)

total_vehicles = (
    result["total_vehicles"]
)

confidence_threshold_used = (
    result[
        "confidence_threshold"
    ]
)

total_samples = len(
    df
)


# =========================================================
# 3. EDGE RESULTS
# =========================================================

st.divider()

st.header(
    "3. Edge Analysis Results"
)

st.markdown(
    """
    <div class="section-intro">
        Summary statistics derived from sampled frames processed by
        MegaDetector at the Edge stage.
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = (
    st.columns(4)
)

m1.metric(
    "Frames analyzed",
    total_samples,
)

m2.metric(
    "Frames retained",
    frames_kept,
)

m3.metric(
    "Frames discarded",
    f"{discard_percentage:.1f}%",
)

m4.metric(
    "Payload reduction",
    f"{payload_reduction:.1f}%",
)

m5, m6, m7, m8 = (
    st.columns(4)
)

m5.metric(
    "Animal detections",
    total_animals,
)

m6.metric(
    "Sampled input",
    f"{input_mb:.2f} MB",
)

m7.metric(
    "Candidate output",
    f"{candidate_mb:.2f} MB",
)

m8.metric(
    "Mean inference time",
    f"{average_inference:.1f} s",
)

st.caption(
    (
        "Estimated payload reduction is calculated from sampled JPEG frames "
        "and retained animal crops. It is not a direct measurement of 5G "
        "network throughput or total source-video compression."
    )
)


# =========================================================
# 4. WORKFLOW
# =========================================================

st.header(
    "4. Edge-to-Science Workflow"
)

st.markdown(
    """
    <div class="section-intro">
        Functional architecture represented by the current prototype.
    </div>
    """,
    unsafe_allow_html=True,
)

workflow = [
    (
        "01",
        "Camera Trap",
        "Acquisition of raw field video.",
    ),
    (
        "02",
        "Edge Inference",
        "Selected frames are analyzed locally before network transmission.",
    ),
    (
        "03",
        "MegaDetector V6",
        "Detection of animals, people and vehicles.",
    ),
    (
        "04",
        "Wildlife Event Filter",
        "Frames without animal detections are excluded from the candidate set.",
    ),
    (
        "05",
        "Candidate Image",
        "Detected animal regions are retained as scientific review candidates.",
    ),
    (
        "06",
        "5G Transmission",
        "Only reduced, relevant data need to be prioritized for transmission.",
    ),
    (
        "07",
        "JaguarID Observation",
        "AI output is combined with metadata to create a structured record.",
    ),
    (
        "08",
        "Researcher Validation",
        "Species, individual identity and ecological context are reviewed manually.",
    ),
]

workflow_html = (
    '<div class="workflow-container">'
)

for (
    number,
    title,
    description,
) in workflow:

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
# 5. EDGE FILTERING CHART
# =========================================================

st.header(
    "5. Edge Filtering Outcome"
)

st.markdown(
    """
    <div class="section-intro">
        Distribution of sampled frames according to the Edge filtering decision.
    </div>
    """,
    unsafe_allow_html=True,
)

filter_labels = [
    "Retained",
    "Discarded",
]

filter_values = [
    frames_kept,
    frames_discarded,
]

fig1, ax1 = plt.subplots(
    figsize=(8.4, 4.7),
    dpi=150,
)

bars = ax1.bar(
    filter_labels,
    filter_values,
    width=0.52,
)

for bar, value in zip(
    bars,
    filter_values,
):

    if total_samples > 0:

        percentage = (
            value
            /
            total_samples
            *
            100
        )

    else:

        percentage = 0

    ax1.text(
        (
            bar.get_x()
            +
            bar.get_width()
            /
            2
        ),
        (
            bar.get_height()
            +
            max(
                total_samples * 0.015,
                0.05,
            )
        ),
        (
            f"{value} frames\n"
            f"{percentage:.1f}%"
        ),
        ha="center",
        va="bottom",
        fontsize=9,
    )

ax1.set_ylabel(
    "Number of sampled frames",
    fontsize=10,
)

ax1.set_title(
    "Edge Filtering Outcome",
    fontsize=13,
    fontweight="semibold",
    pad=12,
)

ax1.grid(
    axis="y",
    linestyle=":",
    linewidth=0.6,
    alpha=0.45,
)

ax1.spines[
    "top"
].set_visible(False)

ax1.spines[
    "right"
].set_visible(False)

ax1.spines[
    "left"
].set_alpha(0.5)

ax1.spines[
    "bottom"
].set_alpha(0.5)

ax1.tick_params(
    labelsize=9
)

fig1.tight_layout()

filtering_png = (
    figure_to_png_bytes(
        fig1,
        dpi=300,
    )
)

st.pyplot(
    fig1,
    use_container_width=True,
)

plt.close(
    fig1
)

st.download_button(
    label="Export filtering figure · PNG 300 dpi",
    data=filtering_png,
    file_name=(
        safe_filename(
            observation[
                "observation_id"
            ]
        )
        +
        "_edge_filtering.png"
    ),
    mime="image/png",
)


# =========================================================
# 6. CONFIDENCE PROFILE
# =========================================================

st.header(
    "6. Detection Confidence Profile"
)

st.markdown(
    """
    <div class="section-intro">
        Maximum animal-detection confidence observed in each sampled frame
        across video time.
    </div>
    """,
    unsafe_allow_html=True,
)

x_values = (
    df[
        "video_time_seconds"
    ]
)

y_values = (
    df[
        "max_animal_confidence"
    ]
)

fig2, ax2 = plt.subplots(
    figsize=(10, 4.8),
    dpi=150,
)

ax2.plot(
    x_values,
    y_values,
    linewidth=1.7,
    marker="o",
    markersize=4.5,
)

ax2.axhline(
    y=confidence_threshold_used,
    linestyle="--",
    linewidth=1.1,
    label=(
        "Detection threshold "
        f"({confidence_threshold_used:.2f})"
    ),
)

ax2.fill_between(
    x_values,
    0,
    y_values,
    alpha=0.07,
)

ax2.set_xlabel(
    "Video time (s)",
    fontsize=10,
)

ax2.set_ylabel(
    "Maximum animal confidence",
    fontsize=10,
)

ax2.set_ylim(
    0,
    1.0,
)

ax2.set_title(
    "Temporal Profile of Animal Detection Confidence",
    fontsize=13,
    fontweight="semibold",
    pad=12,
)

ax2.grid(
    axis="both",
    linestyle=":",
    linewidth=0.6,
    alpha=0.45,
)

ax2.spines[
    "top"
].set_visible(False)

ax2.spines[
    "right"
].set_visible(False)

ax2.spines[
    "left"
].set_alpha(0.5)

ax2.spines[
    "bottom"
].set_alpha(0.5)

ax2.tick_params(
    labelsize=9
)

ax2.legend(
    frameon=False,
    fontsize=9,
)

fig2.tight_layout()

confidence_png = (
    figure_to_png_bytes(
        fig2,
        dpi=300,
    )
)

st.pyplot(
    fig2,
    use_container_width=True,
)

plt.close(
    fig2
)

st.download_button(
    label="Export confidence figure · PNG 300 dpi",
    data=confidence_png,
    file_name=(
        safe_filename(
            observation[
                "observation_id"
            ]
        )
        +
        "_confidence_profile.png"
    ),
    mime="image/png",
)


# =========================================================
# 7. DATA REDUCTION
# =========================================================

st.header(
    "7. Estimated Candidate Data Reduction"
)

st.markdown(
    """
    <div class="section-intro">
        Comparison between sampled-frame image volume and the animal
        candidate crops retained for downstream review.
    </div>
    """,
    unsafe_allow_html=True,
)

payload_labels = [
    "Sampled input",
    "Candidate output",
]

payload_values = [
    input_mb,
    candidate_mb,
]

fig3, ax3 = plt.subplots(
    figsize=(8.4, 4.7),
    dpi=150,
)

payload_bars = ax3.bar(
    payload_labels,
    payload_values,
    width=0.52,
)

for bar, value in zip(
    payload_bars,
    payload_values,
):

    ax3.text(
        (
            bar.get_x()
            +
            bar.get_width()
            /
            2
        ),
        (
            bar.get_height()
            +
            max(
                max(payload_values) * 0.02,
                0.001,
            )
        ),
        f"{value:.3f} MB",
        ha="center",
        va="bottom",
        fontsize=9,
    )

ax3.set_ylabel(
    "Estimated image payload (MB)",
    fontsize=10,
)

ax3.set_title(
    "Estimated Data Retained Before Transmission",
    fontsize=13,
    fontweight="semibold",
    pad=12,
)

ax3.grid(
    axis="y",
    linestyle=":",
    linewidth=0.6,
    alpha=0.45,
)

ax3.spines[
    "top"
].set_visible(False)

ax3.spines[
    "right"
].set_visible(False)

ax3.spines[
    "left"
].set_alpha(0.5)

ax3.spines[
    "bottom"
].set_alpha(0.5)

ax3.tick_params(
    labelsize=9
)

fig3.tight_layout()

payload_png = (
    figure_to_png_bytes(
        fig3,
        dpi=300,
    )
)

st.pyplot(
    fig3,
    use_container_width=True,
)

plt.close(
    fig3
)

st.download_button(
    label="Export payload figure · PNG 300 dpi",
    data=payload_png,
    file_name=(
        safe_filename(
            observation[
                "observation_id"
            ]
        )
        +
        "_payload_reduction.png"
    ),
    mime="image/png",
)

st.caption(
    (
        "This estimate is based on JPEG sizes of sampled frames and "
        "detected animal crops. It represents a prototype data-reduction "
        "indicator, not a direct 5G traffic measurement."
    )
)


# =========================================================
# 8. CANDIDATE ANIMAL IMAGES
# =========================================================

st.header(
    "8. Candidate Animal Images"
)

st.markdown(
    """
    <div class="section-intro">
        Animal crops retained by MegaDetector for researcher review.
        These images are not automatically confirmed as jaguars unless
        validated by a researcher or a future species-classification model.
    </div>
    """,
    unsafe_allow_html=True,
)

if len(candidate_images) == 0:

    st.warning(
        "No animal candidates were detected in the sampled frames."
    )

else:

    candidate_count = len(
        candidate_images
    )

    st.success(
        (
            f"{candidate_count} candidate animal "
            f"{'image was' if candidate_count == 1 else 'images were'} retained."
        )
    )

    candidates_zip = create_candidates_zip(
        observation[
            "observation_id"
        ],
        candidate_images,
    )

    st.download_button(
        label="Download all candidate images · ZIP",
        data=candidates_zip,
        file_name=(
            safe_filename(
                observation[
                    "observation_id"
                ]
            )
            +
            "_candidate_images.zip"
        ),
        mime="application/zip",
        use_container_width=True,
    )

    st.caption(
        (
            "ZIP files contain original candidate crops as PNG images "
            "with observation ID, candidate number and video timestamp "
            "embedded in each filename."
        )
    )

    st.divider()

    display_candidates = (
        candidate_images[
            :12
        ]
    )

    columns = (
        st.columns(3)
    )

    for index, candidate in enumerate(
        display_candidates,
        start=1,
    ):

        column = (
            columns[
                (index - 1)
                %
                3
            ]
        )

        with column:

            st.image(
                candidate[
                    "image"
                ],
                use_container_width=True,
            )

            st.markdown(
                (
                    f"**Candidate {index:02d}**  \n"
                    f"Video time: {candidate['time']:.1f} s  \n"
                    f"Detection confidence: {candidate['confidence']:.2f}"
                )
            )

            png_data = (
                image_to_png_bytes(
                    candidate[
                        "image"
                    ]
                )
            )

            if png_data is not None:

                time_string = (
                    f"{candidate['time']:.1f}"
                    .replace(
                        ".",
                        "_",
                    )
                )

                candidate_filename = (
                    f"{safe_filename(observation['observation_id'])}"
                    f"_candidate_{index:03d}"
                    f"_t{time_string}s.png"
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
            (
                f"Showing the first 12 of "
                f"{len(candidate_images)} candidates. "
                "The ZIP archive contains all retained candidates."
            )
        )


# =========================================================
# 9. EDGE DECISIONS
# =========================================================

st.header(
    "9. Frame-Level Edge Decisions"
)

st.markdown(
    """
    <div class="section-intro">
        Annotated sampled frames showing model detections and the
        resulting retain/discard decision.
    </div>
    """,
    unsafe_allow_html=True,
)

for index, item in enumerate(
    annotated_images,
    start=1,
):

    with st.expander(
        (
            f"Sample {index:02d} · "
            f"t={item['time']:.1f} s · "
            f"{item['decision']}"
        )
    ):

        st.image(
            item[
                "image"
            ],
            use_container_width=True,
        )


# =========================================================
# 10. SCIENTIFIC OBSERVATION
# =========================================================

st.header(
    "10. Scientific Observation"
)

st.markdown(
    """
    <div class="section-intro">
        Structured observation combining automated detection results with
        researcher-supplied ecological metadata.
    </div>
    """,
    unsafe_allow_html=True,
)

obs1, obs2, obs3 = (
    st.columns(3)
)

obs1.metric(
    "Observation ID",
    observation[
        "observation_id"
    ],
)

obs2.metric(
    "Species annotation",
    observation[
        "species"
    ],
)

obs3.metric(
    "Individual ID",
    observation[
        "individual_id"
    ],
)

detail_col1, detail_col2 = (
    st.columns(2)
)

with detail_col1:

    st.markdown(
        f"""
        **Observation name**  
        {observation["observation_name"]}

        **Camera / Station**  
        {observation["camera_id"]}

        **Study site**  
        {observation["study_site"]}
        """
    )

with detail_col2:

    st.markdown(
        f"""
        **Observer / Researcher**  
        {observation["observer"]}

        **Source video**  
        {observation["source_video"]}

        **Analysis date**  
        {observation["analysis_date"]} {observation["analysis_time"]}
        """
    )

with st.expander(
    "Research / Field Notes",
    expanded=True,
):

    st.write(
        observation[
            "notes"
        ]
    )

st.caption(
    (
        "Species and individual identity in this record are "
        "researcher-provided annotations."
    )
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
        item[
            "observation_id"
        ]
        for item
        in st.session_state.observation_registry
    ]

    if (
        observation[
            "observation_id"
        ]
        not in existing_ids
    ):

        st.session_state.observation_registry.append(
            observation.copy()
        )

        st.success(
            (
                f'Observation '
                f'{observation["observation_id"]} '
                f'was added to the current JaguarID registry.'
            )
        )

    else:

        st.info(
            (
                "This observation is already present "
                "in the current session registry."
            )
        )


# =========================================================
# 11. REGISTRY
# =========================================================

st.header(
    "11. Observation Registry"
)

st.markdown(
    """
    <div class="section-intro">
        Observations saved during the current application session.
        This prototype registry is temporary and is not yet a persistent database.
    </div>
    """,
    unsafe_allow_html=True,
)

if (
    len(
        st.session_state.observation_registry
    )
    == 0
):

    st.info(
        "No observations have been saved during this session."
    )

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
        "maximum_animal_confidence",
        "estimated_payload_reduction",
    ]

    visible_columns = [
        column
        for column
        in preferred_columns
        if column
        in registry_df.columns
    ]

    st.dataframe(
        registry_df[
            visible_columns
        ],
        use_container_width=True,
        hide_index=True,
    )

    registry_count = len(
        st.session_state.observation_registry
    )

    assigned_individuals = {

        obs[
            "individual_id"
        ]

        for obs
        in st.session_state.observation_registry

        if obs[
            "individual_id"
        ]
        not in [
            "Unassigned",
            "Unknown",
            "",
        ]
    }

    unique_individuals = len(
        assigned_individuals
    )

    r1, r2 = (
        st.columns(2)
    )

    r1.metric(
        "Saved observations",
        registry_count,
    )

    r2.metric(
        "Assigned individuals",
        unique_individuals,
    )

    # -----------------------------------------------------
    # INDIVIDUAL ENCOUNTER HISTORY
    # -----------------------------------------------------

    if unique_individuals > 0:

        st.subheader(
            "Individual Encounter History"
        )

        individual_history = (
            registry_df[
                registry_df[
                    "individual_id"
                ].isin(
                    assigned_individuals
                )
            ]
            .groupby(
                "individual_id",
                as_index=False,
            )
            .agg(
                observations=(
                    "observation_id",
                    "count",
                ),
                first_recorded=(
                    "analysis_date",
                    "min",
                ),
                last_recorded=(
                    "analysis_date",
                    "max",
                ),
            )
        )

        st.dataframe(
            individual_history,
            use_container_width=True,
            hide_index=True,
        )

        repeated = (
            individual_history[
                individual_history[
                    "observations"
                ]
                > 1
            ]
        )

        if len(repeated) > 0:

            st.info(
                (
                    "Repeated individual IDs are present across saved "
                    "observations. These represent researcher-assigned "
                    "encounter histories and should not be interpreted "
                    "as automated individual re-identification."
                )
            )


# =========================================================
# 12. FRAME-LEVEL DATA
# =========================================================

st.header(
    "12. Frame-Level Analysis Data"
)

st.markdown(
    """
    <div class="section-intro">
        Structured results for each sampled frame analyzed by MegaDetector.
    </div>
    """,
    unsafe_allow_html=True,
)

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)

csv_data = (
    df.to_csv(
        index=False
    )
    .encode(
        "utf-8"
    )
)

csv_filename = (
    safe_filename(
        observation[
            "observation_name"
        ]
    )
    +
    "_JaguarID_Data.csv"
)

st.download_button(
    label="Download frame-level data · CSV",
    data=csv_data,
    file_name=csv_filename,
    mime="text/csv",
    use_container_width=True,
)


# =========================================================
# 13. SCIENTIFIC REPORT
# =========================================================

st.header(
    "13. Scientific Observation Report"
)

st.markdown(
    """
    <div class="section-intro">
        Export observation metadata, Edge AI metrics, researcher annotations
        and representative candidate animal images in a portable PDF report.
    </div>
    """,
    unsafe_allow_html=True,
)

report_name = st.text_input(
    "Report file name",
    value=(
        observation[
            "observation_name"
        ]
    ),
    help=(
        "Choose a descriptive name for the exported observation report."
    ),
)

try:

    pdf_data = (
        create_observation_pdf(
            observation,
            candidate_images,
        )
    )

    pdf_filename = (
        safe_filename(
            report_name
        )
        +
        "_JaguarID_Report.pdf"
    )

    st.download_button(
        label="Download Scientific Observation Report · PDF",
        data=pdf_data,
        file_name=pdf_filename,
        mime="application/pdf",
        use_container_width=True,
    )

    st.caption(
        (
            "The PDF includes observation metadata, Edge AI metrics, "
            "researcher annotations and up to six representative "
            "candidate animal images."
        )
    )

except Exception as pdf_error:

    st.error(
        (
            "The video analysis was completed successfully, "
            "but the PDF report could not be generated."
        )
    )

    st.code(
        str(
            pdf_error
        )
    )


# =========================================================
# FINAL INTERPRETATION
# =========================================================

st.divider()

st.header(
    "Analysis Summary"
)

st.markdown(
    f"""
    <div class="prototype-box">

    <b>Edge filtering result</b><br><br>

    {total_samples} sampled frames were analyzed.
    {frames_kept} were retained as animal events and
    {frames_discarded} were discarded at the Edge.

    The resulting candidate-image payload was approximately
    <b>{payload_reduction:.1f}% smaller</b> than the sampled-frame
    image payload used in this prototype calculation.

    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader(
    "Prototype Scope"
)

st.markdown(
    """
    **Current implementation**

    Camera-trap video → sampled Edge inference → animal-event filtering →
    candidate image extraction → structured scientific observation →
    researcher validation → temporary encounter registry.

    **Potential extensions**

    Persistent observation database, validated species classification,
    individual jaguar re-identification, multi-camera encounter history,
    location-aware monitoring, automated alerts and field-network integration.
    """
)

st.caption(
    (
        "JaguarID is a research prototype. MegaDetector performs "
        "object detection; species and individual identity currently "
        "require researcher validation."
    )
)