# -*- coding: utf-8 -*-

"""
=========================================================
PANTHERAID EDGE DEMO - HACKATRON 5G
=========================================================

Pipeline demostrado:

CAMERA-TRAP VIDEO
        ↓
EDGE
        ↓
MEGADETECTOR V6
        ↓
ANIMAL DETECTION
        ↓
FILTER
        ↓
CANDIDATE IMAGE
        ↓
[5G]
        ↓
[PANTHERAID / RE-ID]

MegaDetector:
- Detecta animal / persona / vehiculo
- NO identifica especie
- NO identifica individuo

La app recibe un video del usuario.
No depende de archivos locales E:\\...
=========================================================
"""

# =========================================================
# IMPORTS
# =========================================================

import tempfile
import time
from pathlib import Path

import cv2
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import torch

from PytorchWildlife.models import detection as pw_detection


# =========================================================
# CONFIGURACION STREAMLIT
# =========================================================

st.set_page_config(
    page_title="PantheraID Edge Demo",
    page_icon="🐆",
    layout="wide"
)


# =========================================================
# TITULO
# =========================================================

st.title("🐆 PantheraID Edge Demo")

st.markdown(
    """
    **Camera Trap → Edge AI → MegaDetector → 5G → PantheraID**

    Esta prueba demuestra cómo un nodo Edge puede filtrar
    datos de una cámara trampa antes de transmitirlos.
    """
)


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("⚙️ Analysis Settings")

confidence_threshold = st.sidebar.slider(
    "Detection confidence",
    min_value=0.10,
    max_value=0.90,
    value=0.25,
    step=0.05
)

sample_seconds = st.sidebar.slider(
    "Sample every X seconds",
    min_value=0.5,
    max_value=5.0,
    value=1.0,
    step=0.5
)

max_samples = st.sidebar.slider(
    "Maximum frames to analyze",
    min_value=3,
    max_value=30,
    value=10,
    step=1
)

st.info(
    "Edge AI inference is running locally using MegaDetector. "
    "For this cloud demo, analyzing 5–10 sampled frames is recommended "
    "to keep processing fast and responsive on CPU."
)

# =========================================================
# CARGAR MODELO
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
        version="MDV6-yolov9-c"
    )

    return model, device


# =========================================================
# UPLOAD
# =========================================================

st.subheader("1. Upload camera-trap video")

uploaded_video = st.file_uploader(
    "Choose a video",
    type=[
        "avi",
        "mp4",
        "mov",
        "mkv"
    ]
)


if uploaded_video is None:

    st.info(
        "Upload a camera-trap video to begin."
    )

    st.stop()


# =========================================================
# MOSTRAR VIDEO ORIGINAL
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
        "The browser could not preview this video format, "
        "but MegaDetector can still analyze it."
    )


# =========================================================
# BOTON
# =========================================================

run_analysis = st.button(
    "🚀 RUN EDGE ANALYSIS",
    type="primary",
    use_container_width=True
)


if not run_analysis:

    st.stop()


# =========================================================
# GUARDAR VIDEO TEMPORAL
# =========================================================

video_suffix = (
    Path(uploaded_video.name).suffix
)

if video_suffix == "":

    video_suffix = ".avi"


with tempfile.NamedTemporaryFile(
    delete=False,
    suffix=video_suffix
) as temp_video:

    temp_video.write(
        uploaded_video.getvalue()
    )

    video_path = temp_video.name


# =========================================================
# LEER VIDEO
# =========================================================

cap = cv2.VideoCapture(
    video_path
)


if not cap.isOpened():

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


duration = (
    total_frames / fps
)


# =========================================================
# INFO VIDEO
# =========================================================

st.subheader("2. Video information")


c1, c2, c3, c4 = st.columns(4)


c1.metric(
    "Duration",
    f"{duration:.1f} s"
)

c2.metric(
    "FPS",
    f"{fps:.1f}"
)

c3.metric(
    "Resolution",
    f"{width} × {height}"
)

c4.metric(
    "Total frames",
    f"{total_frames:,}"
)


# =========================================================
# CARGAR MEGADETECTOR
# =========================================================

st.subheader("3. Loading MegaDetector")

with st.spinner(
    "Loading MegaDetector V6..."
):

    model, device = load_model()


st.success(
    f"MegaDetector loaded on {device.upper()}"
)


# =========================================================
# CLASES
# =========================================================

CLASS_NAMES = {
    0: "animal",
    1: "person",
    2: "vehicle"
}


# =========================================================
# MUESTREO
# =========================================================

frame_interval = max(
    1,
    int(
        fps * sample_seconds
    )
)


# =========================================================
# VARIABLES
# =========================================================

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


# =========================================================
# UI DE PROGRESO
# =========================================================

st.subheader("4. Edge processing")

progress_bar = st.progress(0)

status_text = st.empty()

live_image = st.empty()


processing_start = time.time()


# =========================================================
# PROCESAR VIDEO
# =========================================================

while True:

    success, frame = cap.read()

    if not success:

        break


    # -----------------------------------------------------
    # Saltar frames
    # -----------------------------------------------------

    if (
        frame_number
        % frame_interval
        != 0
    ):

        frame_number += 1
        continue


    sample_number += 1


    if sample_number > max_samples:

        break


    video_time = (
        frame_number / fps
    )


    status_text.write(
        f"Analyzing sample {sample_number}/{max_samples} "
        f"— video time {video_time:.1f}s"
    )


    # =====================================================
    # TEMP JPG
    # =====================================================

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".jpg"
    ) as temp_frame:

        frame_path = temp_frame.name


    cv2.imwrite(
        frame_path,
        frame
    )


    # =====================================================
    # ESTIMAR INPUT
    # =====================================================

    try:

        frame_bytes = (
            Path(frame_path)
            .stat()
            .st_size
        )

    except Exception:

        frame_bytes = 0


    total_input_bytes += (
        frame_bytes
    )


    # =====================================================
    # INFERENCIA
    # =====================================================

    inference_start = time.time()


    result = model.single_image_detection(
        frame_path,
        det_conf_thres=confidence_threshold
    )


    inference_seconds = (
        time.time()
        -
        inference_start
    )


    detections = (
        result["detections"]
    )


    # =====================================================
    # FRAME RESULTS
    # =====================================================

    animal_count = 0

    person_count = 0

    vehicle_count = 0

    max_animal_confidence = 0.0

    candidate_bytes_frame = 0


    annotated = frame.copy()


    # =====================================================
    # DETECTIONS
    # =====================================================

    if (
        detections is not None
        and
        len(detections) > 0
    ):

        boxes = detections.xyxy

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


            label = CLASS_NAMES.get(
                class_id,
                "unknown"
            )


            x1, y1, x2, y2 = [
                int(value)
                for value
                in boxes[
                    detection_index
                ]
            ]


            # =============================================
            # Limitar coordenadas
            # =============================================

            x1 = max(
                0,
                min(
                    x1,
                    width - 1
                )
            )

            y1 = max(
                0,
                min(
                    y1,
                    height - 1
                )
            )

            x2 = max(
                x1 + 1,
                min(
                    x2,
                    width
                )
            )

            y2 = max(
                y1 + 1,
                min(
                    y2,
                    height
                )
            )


            # =============================================
            # ANIMAL
            # =============================================

            if label == "animal":

                animal_count += 1

                total_animals += 1


                max_animal_confidence = max(
                    max_animal_confidence,
                    confidence
                )


                crop = frame[
                    y1:y2,
                    x1:x2
                ]


                if crop.size > 0:

                    crop_rgb = cv2.cvtColor(
                        crop,
                        cv2.COLOR_BGR2RGB
                    )


                    candidate_images.append(
                        {
                            "image":
                                crop_rgb,

                            "confidence":
                                confidence,

                            "time":
                                video_time
                        }
                    )


                    success_encode, encoded = (
                        cv2.imencode(
                            ".jpg",
                            crop
                        )
                    )


                    if success_encode:

                        crop_bytes = (
                            len(encoded)
                        )

                        candidate_bytes_frame += (
                            crop_bytes
                        )

                        total_candidate_bytes += (
                            crop_bytes
                        )


            # =============================================
            # PERSON
            # =============================================

            elif label == "person":

                person_count += 1

                total_people += 1


            # =============================================
            # VEHICLE
            # =============================================

            elif label == "vehicle":

                vehicle_count += 1

                total_vehicles += 1


            # =============================================
            # DRAW BOX
            # =============================================

            cv2.rectangle(
                annotated,
                (
                    x1,
                    y1
                ),
                (
                    x2,
                    y2
                ),
                (
                    0,
                    255,
                    0
                ),
                3
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
                        y1 - 10
                    )
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (
                    0,
                    255,
                    0
                ),
                2
            )


    # =====================================================
    # EDGE DECISION
    # =====================================================

    keep = (
        animal_count > 0
    )


    if keep:

        frames_kept += 1

        decision = (
            "KEEP → NEXT STAGE"
        )

    else:

        frames_discarded += 1

        decision = (
            "DISCARD AT EDGE"
        )


    # =====================================================
    # OVERLAY
    # =====================================================

    cv2.rectangle(
        annotated,
        (
            0,
            0
        ),
        (
            min(
                width,
                820
            ),
            145
        ),
        (
            0,
            0,
            0
        ),
        -1
    )


    cv2.putText(
        annotated,
        "PANTHERAID EDGE DEMO",
        (
            20,
            35
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (
            255,
            255,
            255
        ),
        2
    )


    cv2.putText(
        annotated,
        (
            f"Video time: "
            f"{video_time:.1f}s"
        ),
        (
            20,
            70
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (
            255,
            255,
            255
        ),
        2
    )


    cv2.putText(
        annotated,
        (
            f"EDGE: "
            f"{decision}"
        ),
        (
            20,
            105
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (
            255,
            255,
            255
        ),
        2
    )


    cv2.putText(
        annotated,
        (
            "Animal confidence: "
            f"{max_animal_confidence:.2f}"
        ),
        (
            20,
            135
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (
            255,
            255,
            255
        ),
        2
    )


    # =====================================================
    # Convertir para Streamlit
    # =====================================================

    annotated_rgb = cv2.cvtColor(
        annotated,
        cv2.COLOR_BGR2RGB
    )


    annotated_images.append(
        {
            "image":
                annotated_rgb,

            "time":
                video_time,

            "decision":
                decision
        }
    )


    # =====================================================
    # LIVE PREVIEW
    # =====================================================

    live_image.image(
        annotated_rgb,
        caption=(
            f"Sample {sample_number} "
            f"— {decision}"
        ),
        use_container_width=True
    )


    # =====================================================
    # DATA RECORD
    # =====================================================

    records.append(
        {
            "sample":
                sample_number,

            "video_time_seconds":
                round(
                    video_time,
                    2
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
                    4
                ),

            "edge_decision":
                (
                    "KEEP"
                    if keep
                    else
                    "DISCARD"
                ),

            "input_jpeg_bytes":
                frame_bytes,

            "candidate_jpeg_bytes":
                candidate_bytes_frame,

            "inference_seconds":
                round(
                    inference_seconds,
                    3
                )
        }
    )


    # =====================================================
    # PROGRESS
    # =====================================================

    progress_value = min(
        sample_number / max_samples,
        1.0
    )


    progress_bar.progress(
        progress_value
    )


    frame_number += 1


# =========================================================
# CERRAR VIDEO
# =========================================================

cap.release()


processing_seconds = (
    time.time()
    -
    processing_start
)


progress_bar.progress(1.0)

status_text.success(
    "Edge analysis completed."
)


# =========================================================
# DATAFRAME
# =========================================================

df = pd.DataFrame(
    records
)


if len(df) == 0:

    st.error(
        "No frames were processed."
    )

    st.stop()


# =========================================================
# METRICAS
# =========================================================

total_samples = len(df)


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


average_inference = (
    df[
        "inference_seconds"
    ].mean()
)


# =========================================================
# RESULTADOS PRINCIPALES
# =========================================================

st.divider()

st.header("5. Edge Results")


m1, m2, m3, m4 = st.columns(4)


m1.metric(
    "Frames analyzed",
    total_samples
)


m2.metric(
    "Frames kept",
    frames_kept
)


m3.metric(
    "Discarded at Edge",
    f"{discard_percentage:.1f}%"
)


m4.metric(
    "Estimated payload reduction",
    f"{payload_reduction:.1f}%"
)


# =========================================================
# MAS METRICAS
# =========================================================

m5, m6, m7, m8 = st.columns(4)


m5.metric(
    "Animal detections",
    total_animals
)


m6.metric(
    "Raw sampled data",
    f"{input_mb:.2f} MB"
)


m7.metric(
    "Candidate data",
    f"{candidate_mb:.2f} MB"
)


m8.metric(
    "Avg inference",
    f"{average_inference:.1f} s"
)


st.caption(
    "Payload reduction is estimated from JPEG sizes. "
    "It is not a real 5G traffic measurement."
)


# =========================================================
# PIPELINE
# =========================================================

st.header("6. Pipeline")

st.markdown(
    """
    ### 📹 Camera Trap
    ↓  
    ### 🧠 Edge AI
    ↓  
    ### 🐾 MegaDetector
    ↓  
    ### 🔍 Animal Filter
    ↓  
    ### 🖼 Candidate Image
    ↓  
    ### 📡 5G
    ↓  
    ### 🐆 PantheraID / Individual Re-ID
    """
)


# =========================================================
# GRAFICO 1
# =========================================================

st.header("7. Edge Filtering")

fig1, ax1 = plt.subplots(
    figsize=(7, 4)
)

ax1.bar(
    [
        "Discarded at Edge",
        "Kept"
    ],
    [
        frames_discarded,
        frames_kept
    ]
)

ax1.set_ylabel(
    "Frames"
)

ax1.set_title(
    "MegaDetector Edge Filtering"
)

st.pyplot(
    fig1
)

plt.close(
    fig1
)


# =========================================================
# GRAFICO 2
# =========================================================

st.header("8. Detection Confidence Through Time")

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
    marker="o"
)

ax2.axhline(
    y=confidence_threshold,
    linestyle="--"
)

ax2.set_xlabel(
    "Video time (seconds)"
)

ax2.set_ylabel(
    "Animal confidence"
)

ax2.set_ylim(
    0,
    1.05
)

ax2.set_title(
    "MegaDetector Detection Timeline"
)

st.pyplot(
    fig2
)

plt.close(
    fig2
)


# =========================================================
# GRAFICO 3
# =========================================================

st.header("9. Estimated Data Reduction")

fig3, ax3 = plt.subplots(
    figsize=(7, 4)
)

ax3.bar(
    [
        "Raw sampled frames",
        "Animal crops"
    ],
    [
        input_mb,
        candidate_mb
    ]
)

ax3.set_ylabel(
    "Estimated MB"
)

ax3.set_title(
    "Data Before Transmission"
)

st.pyplot(
    fig3
)

plt.close(
    fig3
)


# =========================================================
# CANDIDATES
# =========================================================

st.header(
    "10. Candidate Images for PantheraID"
)


if len(candidate_images) == 0:

    st.warning(
        "No animal candidates were detected."
    )

else:

    st.write(
        f"{len(candidate_images)} candidate detections found."
    )


    # Mostrar maximo 12 para que no se vuelva enorme

    display_candidates = (
        candidate_images[:12]
    )


    columns = st.columns(3)


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
                f"t={candidate['time']:.1f}s | "
                f"confidence="
                f"{candidate['confidence']:.2f}"
            ),
            use_container_width=True
        )


# =========================================================
# FRAMES ANOTADOS
# =========================================================

st.header(
    "11. Edge Decisions"
)


for item in annotated_images:

    with st.expander(
        (
            f"t={item['time']:.1f}s "
            f"— {item['decision']}"
        )
    ):

        st.image(
            item[
                "image"
            ],
            use_container_width=True
        )


# =========================================================
# TABLA
# =========================================================

st.header(
    "12. Analysis Data"
)


st.dataframe(
    df,
    use_container_width=True
)


# =========================================================
# CSV DOWNLOAD
# =========================================================

csv_data = (
    df.to_csv(
        index=False
    )
    .encode(
        "utf-8"
    )
)


st.download_button(
    label="⬇️ Download analysis CSV",
    data=csv_data,
    file_name="pantheraid_edge_results.csv",
    mime="text/csv"
)


# =========================================================
# RESUMEN
# =========================================================

st.divider()


st.success(
    (
        f"Edge filtering discarded "
        f"{discard_percentage:.1f}% "
        f"of sampled frames and produced an estimated "
        f"{payload_reduction:.1f}% reduction "
        f"in image payload."
    )
)


st.info(
    """
    **Next integration step**

    Candidate image  
    → species/jaguar validation  
    → 5G transmission  
    → PantheraID API  
    → individual identity + confidence  
    → dashboard / alert
    """
)


st.caption(
    (
        f"Analysis completed in "
        f"{processing_seconds:.1f} seconds."
    )
)
