# -*- coding: utf-8 -*-

"""
=========================================================
JAGUARID - EDGE WILDLIFE INTELLIGENCE
HACKATRON 5G
=========================================================

Camera Trap
    ↓
Edge AI
    ↓
MegaDetector V6
    ↓
Wildlife Event Filtering
    ↓
Candidate Observation
    ↓
5G
    ↓
JaguarID Scientific Observation
    ↓
Researcher Validation
    ↓
Individual Encounter History

IMPORTANT
MegaDetector:
- detects animal / person / vehicle
- does NOT identify species
- does NOT identify individual animals

Species and individual IDs are researcher-provided annotations
unless validated downstream models are integrated.
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
# STREAMLIT CONFIG
# =========================================================

st.set_page_config(
    page_title="JaguarID | Edge Wildlife Intelligence",
    page_icon="🐆",
    layout="wide",
)


# =========================================================
# LIGHT UI CUSTOMIZATION
# =========================================================

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1400px;
    }

    h1, h2, h3 {
        letter-spacing: -0.02em;
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(120,120,120,0.18);
        border-radius: 10px;
        padding: 14px;
    }

    div[data-testid="stMetricLabel"] {
        font-size: 0.82rem;
    }

    .workflow-step {
        border-left: 3px solid #777;
        padding: 0.15rem 0 0.8rem 1rem;
        margin: 0 0 0.3rem 0;
    }

    .workflow-number {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        opacity: 0.62;
        margin-bottom: 0.1rem;
    }

    .workflow-title {
        font-size: 1rem;
        font-weight: 650;
        margin-bottom: 0.15rem;
    }

    .workflow-description {
        font-size: 0.84rem;
        opacity: 0.72;
    }

    .scientific-note {
        padding: 0.9rem 1rem;
        border: 1px solid rgba(120,120,120,0.20);
        border-radius: 8px;
        margin-top: 0.5rem;
        font-size: 0.9rem;
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
# HELPERS
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
# PDF GENERATOR
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
        fontSize=22,
        leading=27,
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "JaguarIDSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=18,
    )

    section_style = ParagraphStyle(
        "JaguarIDSection",
        parent=styles["Heading2"],
        fontSize=14,
        leading=17,
        spaceBefore=14,
        spaceAfter=8,
    )

    note_style = ParagraphStyle(
        "JaguarIDNote",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#555555"),
    )

    # FIX:
    # ReportLab does not always include styles["Caption"].
    # We define our own style so the PDF works consistently.
    caption_style = ParagraphStyle(
        "JaguarIDCaption",
        parent=styles["BodyText"],
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
            "Edge Wildlife Intelligence · Scientific Observation Report",
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
                    colors.HexColor("#F1F3F5"),
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
                    0.4,
                    colors.HexColor("#CCCCCC"),
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

    story.append(summary_table)

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
                    colors.HexColor("#F1F3F5"),
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
                    0.4,
                    colors.HexColor("#CCCCCC"),
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
                "<b>Scientific interpretation note:</b> "
                "MegaDetector performs object detection for animals, "
                "people and vehicles. Species and individual identity "
                "included in this report are researcher-supplied "
                "annotations unless a validated downstream "
                "classification or re-identification model is integrated."
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
                "Candidate Wildlife Images",
                section_style,
            )
        )

        story.append(
            Paragraph(
                (
                    "Candidate detections retained by the Edge AI "
                    "for scientific review."
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
            candidate_images[:6]
        ):

            rgb_image = candidate["image"]

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

            pdf_image = PDFImage(
                image_buffer,
                width=pdf_width,
                height=pdf_height,
            )

            story.append(
                pdf_image
            )

            story.append(
                Paragraph(
                    (
                        f"Candidate {index + 1} · "
                        f"Video time: "
                        f"{candidate['time']:.1f} s · "
                        f"MegaDetector confidence: "
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
# HEADER
# =========================================================

st.title(
    "JaguarID"
)

st.markdown(
    """
    **Edge Wildlife Intelligence Platform**

    Camera-trap video is processed locally using Edge AI.
    Relevant wildlife observations are retained while non-relevant
    frames can be discarded before transmission.
    """
)

st.caption(
    "Camera Trap · Edge AI · MegaDetector · 5G · Scientific Observation"
)


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header(
    "Analysis Settings"
)

confidence_threshold = st.sidebar.slider(
    "Detection confidence",
    min_value=0.10,
    max_value=0.90,
    value=0.25,
    step=0.05,
)

sample_seconds = st.sidebar.slider(
    "Sample every X seconds",
    min_value=0.5,
    max_value=5.0,
    value=1.0,
    step=0.5,
)

max_samples = st.sidebar.slider(
    "Maximum frames to analyze",
    min_value=3,
    max_value=30,
    value=10,
    step=1,
)

st.sidebar.info(
    "MegaDetector inference runs locally in the cloud environment. "
    "For this prototype, 5–10 sampled frames are recommended "
    "for responsive CPU processing."
)

st.sidebar.divider()

st.sidebar.caption(
    "JaguarID · Research Prototype"
)


# =========================================================
# 1. OBSERVATION METADATA
# =========================================================

st.header(
    "1. Observation Metadata"
)

st.caption(
    "Scientific context supplied by the researcher."
)

meta_col1, meta_col2 = st.columns(2)

with meta_col1:

    observation_name = st.text_input(
        "Observation name",
        placeholder="e.g. Jaguar encounter - CT07",
    )

    camera_id = st.text_input(
        "Camera / Station ID",
        placeholder="e.g. CT-07",
    )

    study_site = st.text_input(
        "Study site",
        placeholder="e.g. Sector A",
    )

with meta_col2:

    species_label = st.text_input(
        "Species identification",
        placeholder="e.g. Panthera onca",
    )

    individual_id = st.text_input(
        "Individual ID",
        placeholder="e.g. JAG-003 or Unknown",
    )

    observer_name = st.text_input(
        "Observer / Researcher",
        placeholder="Researcher name",
    )

observation_notes = st.text_area(
    "Field notes",
    placeholder=(
        "Behavior, habitat, environmental conditions, "
        "sex, age class, direction of movement or other observations."
    ),
)

st.markdown(
    """
    <div class="scientific-note">
        <b>Annotation note.</b>
        Species and individual identity are researcher-provided.
        MegaDetector detects animals, people and vehicles but does not
        determine species or individual identity.
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 2. VIDEO
# =========================================================

st.header(
    "2. Camera-Trap Video"
)

uploaded_video = st.file_uploader(
    "Choose a camera-trap video",
    type=[
        "avi",
        "mp4",
        "mov",
        "mkv",
    ],
)

if uploaded_video is None:

    st.info(
        "Upload a camera-trap video to begin."
    )

    st.stop()


# =========================================================
# RESET RESULTS WHEN FILE CHANGES
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
    f"Video loaded: {uploaded_video.name}"
)

try:

    st.video(
        uploaded_video.getvalue()
    )

except Exception:

    st.warning(
        "The browser could not preview this format, "
        "but the file may still be analyzed by OpenCV."
    )


# =========================================================
# RUN ANALYSIS
# =========================================================

run_analysis = st.button(
    "RUN EDGE ANALYSIS",
    type="primary",
    use_container_width=True,
)


# =========================================================
# ANALYSIS
# =========================================================

if run_analysis:

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
            "OpenCV could not open this video."
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

    if fps > 0:
        duration = (
            total_frames
            /
            fps
        )
    else:
        duration = 0

    # -----------------------------------------------------
    # VIDEO INFO
    # -----------------------------------------------------

    st.subheader(
        "Video Information"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Duration",
        f"{duration:.1f} s",
    )

    c2.metric(
        "FPS",
        f"{fps:.1f}",
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
    # MODEL
    # -----------------------------------------------------

    st.subheader(
        "Edge AI"
    )

    with st.spinner(
        "Initializing MegaDetector V6..."
    ):

        model, device = (
            load_model()
        )

    st.success(
        (
            "MegaDetector V6 ready · "
            f"{device.upper()} inference"
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
        "Edge Processing"
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
    # PROCESS LOOP
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

        if (
            sample_number
            >
            max_samples
        ):
            break

        video_time = (
            frame_number
            /
            fps
        )

        status_text.write(
            (
                f"Analyzing sample "
                f"{sample_number}/{max_samples} "
                f"· video time "
                f"{video_time:.1f}s"
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
        # INFERENCE
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
                                "image": crop_rgb,
                                "confidence": confidence,
                                "time": video_time,
                                "sample": sample_number,
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
                # BOX
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
                    3,
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
                    0.8,
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
                "KEEP - WILDLIFE EVENT"
            )

        else:

            frames_discarded += 1

            decision = (
                "DISCARD AT EDGE"
            )

        # -------------------------------------------------
        # OVERLAY
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
                    820,
                ),
                145,
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
            "JAGUARID EDGE AI",
            (
                20,
                35,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
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
                f"{video_time:.1f}s"
            ),
            (
                20,
                70,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
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
                f"EDGE: "
                f"{decision}"
            ),
            (
                20,
                105,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
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
                "Animal confidence: "
                f"{max_animal_confidence:.2f}"
            ),
            (
                20,
                135,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (
                255,
                255,
                255,
            ),
            2,
        )

        annotated_rgb = (
            cv2.cvtColor(
                annotated,
                cv2.COLOR_BGR2RGB,
            )
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
            caption=(
                f"Sample {sample_number} "
                f"· {decision}"
            ),
            use_container_width=True,
        )

        # -------------------------------------------------
        # RECORD
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
                        "KEEP"
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
    # OBSERVATION OBJECT
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
# RESTORE RESULTS
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
# 3. RESULTS
# =========================================================

st.divider()

st.header(
    "3. Edge AI Results"
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
    "Discarded at Edge",
    f"{discard_percentage:.1f}%",
)

m4.metric(
    "Estimated payload reduction",
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
    "Raw sampled data",
    f"{input_mb:.2f} MB",
)

m7.metric(
    "Candidate data",
    f"{candidate_mb:.2f} MB",
)

m8.metric(
    "Average inference",
    f"{average_inference:.1f} s",
)

st.caption(
    "Payload reduction is estimated from JPEG sizes of sampled frames "
    "and retained animal crops. It is not a direct measurement of 5G traffic."
)


# =========================================================
# 4. CLEAN WORKFLOW
# =========================================================

st.header(
    "4. Edge-to-Science Workflow"
)

st.caption(
    "Processing architecture demonstrated by the prototype."
)

workflow = [
    (
        "01",
        "Camera Trap",
        "Raw field video acquisition",
    ),
    (
        "02",
        "Edge AI",
        "Local inference before network transmission",
    ),
    (
        "03",
        "MegaDetector",
        "Animal, person and vehicle detection",
    ),
    (
        "04",
        "Wildlife Event Filter",
        "Frames without detected wildlife are discarded",
    ),
    (
        "05",
        "Candidate Observation",
        "Relevant wildlife imagery is retained",
    ),
    (
        "06",
        "5G Transmission",
        "Reduced candidate payload is prepared for transmission",
    ),
    (
        "07",
        "JaguarID",
        "Detection is converted into a structured scientific observation",
    ),
    (
        "08",
        "Researcher Validation",
        "Species, individual ID and field context are validated by the researcher",
    ),
]

for (
    step_number,
    step_title,
    step_description,
) in workflow:

    st.markdown(
        f"""
        <div class="workflow-step">
            <div class="workflow-number">
                STEP {step_number}
            </div>
            <div class="workflow-title">
                {step_title}
            </div>
            <div class="workflow-description">
                {step_description}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 5. EDGE FILTERING
# =========================================================

st.header(
    "5. Edge Filtering"
)

fig1, ax1 = plt.subplots(
    figsize=(7, 4)
)

ax1.bar(
    [
        "Discarded",
        "Retained",
    ],
    [
        frames_discarded,
        frames_kept,
    ],
)

ax1.set_ylabel(
    "Frames"
)

ax1.set_title(
    "Sampled Frames After Edge Filtering"
)

st.pyplot(
    fig1
)

plt.close(
    fig1
)


# =========================================================
# 6. CONFIDENCE
# =========================================================

st.header(
    "6. Detection Confidence"
)

fig2, ax2 = plt.subplots(
    figsize=(9, 4)
)

ax2.plot(
    df[
        "video_time_seconds"
    ],
    df[
        "max_animal_confidence"
    ],
    marker="o",
)

ax2.axhline(
    y=confidence_threshold_used,
    linestyle="--",
)

ax2.set_xlabel(
    "Video time (seconds)"
)

ax2.set_ylabel(
    "Animal confidence"
)

ax2.set_ylim(
    0,
    1.05,
)

ax2.set_title(
    "Animal Detection Confidence Through Time"
)

st.pyplot(
    fig2
)

plt.close(
    fig2
)


# =========================================================
# 7. DATA REDUCTION
# =========================================================

st.header(
    "7. Estimated Data Reduction"
)

fig3, ax3 = plt.subplots(
    figsize=(7, 4)
)

ax3.bar(
    [
        "Sampled frames",
        "Wildlife candidates",
    ],
    [
        input_mb,
        candidate_mb,
    ],
)

ax3.set_ylabel(
    "Estimated MB"
)

ax3.set_title(
    "Estimated Image Payload Before Transmission"
)

st.pyplot(
    fig3
)

plt.close(
    fig3
)


# =========================================================
# 8. CANDIDATES
# =========================================================

st.header(
    "8. Candidate Wildlife Detections"
)

if len(candidate_images) == 0:

    st.warning(
        "No animal candidates were detected."
    )

else:

    st.success(
        (
            f"{len(candidate_images)} "
            "candidate wildlife detections retained."
        )
    )

    st.caption(
        "Candidate images are retained for researcher review "
        "or future downstream species / individual re-identification."
    )

    display_candidates = (
        candidate_images[
            :12
        ]
    )

    columns = (
        st.columns(3)
    )

    for index, candidate in enumerate(
        display_candidates
    ):

        column = columns[
            index % 3
        ]

        column.image(
            candidate[
                "image"
            ],
            caption=(
                f"t={candidate['time']:.1f}s · "
                f"confidence={candidate['confidence']:.2f}"
            ),
            use_container_width=True,
        )


# =========================================================
# 9. EDGE DECISIONS
# =========================================================

st.header(
    "9. Edge Decisions"
)

for item in annotated_images:

    with st.expander(
        (
            f"t={item['time']:.1f}s · "
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
# 10. OBSERVATION
# =========================================================

st.header(
    "10. Scientific Observation"
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
    "Species",
    observation[
        "species"
    ],
)

obs3.metric(
    "Individual",
    observation[
        "individual_id"
    ],
)

st.markdown(
    f"""
    **Observation name:** {observation["observation_name"]}  
    **Camera / Station:** {observation["camera_id"]}  
    **Study site:** {observation["study_site"]}  
    **Observer:** {observation["observer"]}  
    **Source video:** {observation["source_video"]}  
    **Analysis date:** {observation["analysis_date"]} {observation["analysis_time"]}
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
    "Species and individual identity are researcher-provided annotations."
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
                f'was saved to the JaguarID Registry.'
            )
        )

    else:

        st.info(
            "This observation is already stored in the current registry."
        )


# =========================================================
# 11. REGISTRY
# =========================================================

st.header(
    "11. JaguarID Observation Registry"
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
    # INDIVIDUAL HISTORY
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

            st.success(
                (
                    "Repeated individual IDs were found across observations. "
                    "These represent researcher-assigned encounter histories, "
                    "not automated individual re-identification."
                )
            )


# =========================================================
# 12. ANALYSIS DATA
# =========================================================

st.header(
    "12. Analysis Data"
)

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)


# =========================================================
# CSV
# =========================================================

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
    label="Download Analysis Data (CSV)",
    data=csv_data,
    file_name=csv_filename,
    mime="text/csv",
    use_container_width=True,
)


# =========================================================
# 13. REPORT
# =========================================================

st.header(
    "13. Scientific Observation Report"
)

st.markdown(
    """
    Generate a portable report containing observation metadata,
    Edge AI results, researcher annotations and retained wildlife imagery.
    """
)

report_name = st.text_input(
    "Report file name",
    value=(
        observation[
            "observation_name"
        ]
    ),
    help=(
        "Choose a descriptive name for the exported report."
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
        label="Download Scientific Observation Report (PDF)",
        data=pdf_data,
        file_name=pdf_filename,
        mime="application/pdf",
        use_container_width=True,
    )

    st.caption(
        "The report includes observation metadata, Edge AI metrics, "
        "researcher annotations and up to six candidate wildlife images."
    )

except Exception as pdf_error:

    st.error(
        (
            "The analysis was completed successfully, "
            "but the PDF report could not be generated."
        )
    )

    st.code(
        str(
            pdf_error
        )
    )


# =========================================================
# FINAL SUMMARY
# =========================================================

st.divider()

st.success(
    (
        f"Edge filtering discarded "
        f"{discard_percentage:.1f}% "
        f"of sampled frames and produced an estimated "
        f"{payload_reduction:.1f}% reduction "
        f"in candidate image payload."
    )
)

st.subheader(
    "Prototype Scope"
)

st.markdown(
    """
    **Current prototype**

    Camera-trap video → Edge detection → wildlife-event filtering →
    reduced candidate data → structured scientific observation →
    researcher validation → encounter registry.

    **Potential future extensions**

    Validated species classification, individual re-identification,
    persistent cloud database, camera-network integration and
    field alerts.
    """
)

st.caption(
    (
        "JaguarID is a research prototype. "
        "MegaDetector performs object detection; "
        "species and individual identity currently require "
        "researcher validation."
    )
)