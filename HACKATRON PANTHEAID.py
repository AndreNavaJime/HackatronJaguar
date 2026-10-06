# -*- coding: utf-8 -*-

"""
============================================================
HACKATRON 5G - PANTHERAID
MEGADETECTOR EDGE DEMO
============================================================

PIPELINE:

CAMERA-TRAP VIDEO
        ↓
EDGE PROCESSING
        ↓
MEGADETECTOR V6
        ↓
¿HAY ANIMAL?
   ↓            ↓
  NO            SI
   ↓            ↓
DESCARTAR    GUARDAR CANDIDATO
                 ↓
             [5G]
                 ↓
        [PANTHERAID / RE-ID]

IMPORTANTE:
MegaDetector NO identifica la especie.
MegaDetector NO identifica individuos.

Solo detecta:
0 = animal
1 = person
2 = vehicle

Este demo prueba la etapa Edge:
filtrar información antes de transmitirla.
============================================================
"""

# ============================================================
# 1. IMPORTS
# ============================================================

from pathlib import Path
import zipfile
import time
import shutil

import cv2
import pandas as pd
import matplotlib.pyplot as plt
import torch

from PytorchWildlife.models import detection as pw_detection


# ============================================================
# 2. CONFIGURACION
# ============================================================

BASE_DIR = Path(r"E:\HACKATRON 5H")

ZIP_FILE = BASE_DIR / "1_videos.zip"

VIDEOS_DIR = BASE_DIR / "JaguarID_videos"

OUTPUT_DIR = BASE_DIR / "MEGADETECTOR_DEMO"

TEMP_DIR = OUTPUT_DIR / "00_temp_frames"

CANDIDATES_DIR = OUTPUT_DIR / "01_candidates_for_pantheraid"

ANNOTATED_DIR = OUTPUT_DIR / "02_animal_detections"


# ------------------------------------------------------------
# CUANTOS SEGUNDOS ENTRE CADA FRAME ANALIZADO
# ------------------------------------------------------------

SAMPLE_EVERY_SECONDS = 1.0


# ------------------------------------------------------------
# CONFIANZA MINIMA
# ------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.25


# ------------------------------------------------------------
# PARA PRIMERA PRUEBA
#
# Tu video dura ~30 segundos.
# Con 1 frame/segundo analizará ~31 imágenes.
#
# None = procesar todas las muestras disponibles.
# ------------------------------------------------------------

MAX_SAMPLES = None


# ------------------------------------------------------------
# VIDEO QUE VAMOS A USAR
#
# 0 = primer video
# 1 = segundo
# etc.
# ------------------------------------------------------------

VIDEO_INDEX = 0


# ============================================================
# 3. CREAR CARPETAS
# ============================================================

for folder in [
    VIDEOS_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
    CANDIDATES_DIR,
    ANNOTATED_DIR
]:
    folder.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# 4. ENCABEZADO
# ============================================================

print("\n")
print("=" * 65)
print("HACKATRON 5G - PANTHERAID")
print("MEGADETECTOR EDGE PIPELINE")
print("=" * 65)


# ============================================================
# 5. BUSCAR VIDEOS YA EXTRAIDOS
# ============================================================

VIDEO_EXTENSIONS = (
    ".avi",
    ".mp4",
    ".mov",
    ".mkv",
    ".mpeg",
    ".mpg",
    ".m4v"
)


def find_videos(folder):

    found = []

    for file in folder.rglob("*"):

        if (
            file.is_file()
            and
            file.suffix.lower() in VIDEO_EXTENSIONS
        ):

            found.append(file)

    return sorted(found)


video_files = find_videos(
    VIDEOS_DIR
)


# ============================================================
# 6. SI NO HAY VIDEOS EXTRAIDOS, EXTRAER ZIP
# ============================================================

if len(video_files) == 0:

    print("\nNo encontré videos extraídos.")

    if not ZIP_FILE.exists():

        raise FileNotFoundError(
            "\nNo encontré:\n"
            + str(ZIP_FILE)
        )

    print("\nDescomprimiendo ZIP...")

    with zipfile.ZipFile(
        ZIP_FILE,
        "r"
    ) as zip_ref:

        zip_ref.extractall(
            VIDEOS_DIR
        )

    print("ZIP descomprimido.")

    video_files = find_videos(
        VIDEOS_DIR
    )


# ============================================================
# 7. VERIFICAR VIDEOS
# ============================================================

if len(video_files) == 0:

    raise RuntimeError(
        "No se encontraron videos."
    )


print(
    "\nVideos disponibles:",
    len(video_files)
)


for i, video in enumerate(
    video_files
):

    print(
        f"{i}: {video.name}"
    )


# ============================================================
# 8. SELECCIONAR VIDEO
# ============================================================

if VIDEO_INDEX >= len(video_files):

    raise IndexError(
        "VIDEO_INDEX no existe."
    )


video_path = (
    video_files[
        VIDEO_INDEX
    ]
)


print("\n")
print("=" * 65)
print("VIDEO SELECCIONADO")
print("=" * 65)

print(
    video_path
)


# ============================================================
# 9. ABRIR VIDEO
# ============================================================

cap = cv2.VideoCapture(
    str(video_path)
)


if not cap.isOpened():

    raise RuntimeError(
        "OpenCV no pudo abrir el video."
    )


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


duration_seconds = (
    total_frames / fps
)


print("\nInformación:")

print(
    "Resolución:",
    width,
    "x",
    height
)

print(
    "FPS:",
    round(fps, 2)
)

print(
    "Frames totales:",
    total_frames
)

print(
    "Duración:",
    round(
        duration_seconds,
        2
    ),
    "segundos"
)


# ============================================================
# 10. HARDWARE
# ============================================================

print("\n")
print("=" * 65)
print("HARDWARE")
print("=" * 65)


if torch.cuda.is_available():

    DEVICE = "cuda"

else:

    DEVICE = "cpu"


print(
    "\nDispositivo:",
    DEVICE.upper()
)


if DEVICE == "cpu":

    print(
        "Esto funcionará en CPU, "
        "pero será más lento que GPU."
    )


# ============================================================
# 11. CARGAR MEGADETECTOR
# ============================================================

print("\n")
print("=" * 65)
print("CARGANDO MEGADETECTOR V6")
print("=" * 65)


print(
    "\nModelo: MDV6-yolov9-c"
)

print(
    "La primera ejecución puede descargar "
    "los pesos automáticamente."
)


model_start = time.time()


model = pw_detection.MegaDetectorV6(
    device=DEVICE,
    pretrained=True,
    version="MDV6-yolov9-c"
)


model_load_time = (
    time.time()
    -
    model_start
)


print(
    "\nMegaDetector cargado."
)

print(
    "Tiempo de carga:",
    round(
        model_load_time,
        2
    ),
    "segundos"
)


# ============================================================
# 12. CLASES
# ============================================================

CLASS_NAMES = {
    0: "animal",
    1: "person",
    2: "vehicle"
}


# ============================================================
# 13. PREPARAR VIDEO DE SALIDA
# ============================================================

OUTPUT_WIDTH = (
    width
    if width % 2 == 0
    else width - 1
)


OUTPUT_HEIGHT = (
    height
    if height % 2 == 0
    else height - 1
)


output_video_path = (
    OUTPUT_DIR /
    "EDGE_MegaDetector_demo.mp4"
)


fourcc = cv2.VideoWriter_fourcc(
    *"mp4v"
)


video_writer = cv2.VideoWriter(
    str(output_video_path),
    fourcc,
    2.0,
    (
        OUTPUT_WIDTH,
        OUTPUT_HEIGHT
    )
)


# ------------------------------------------------------------
# FALLBACK AVI
# ------------------------------------------------------------

if not video_writer.isOpened():

    print(
        "\nMP4 no disponible. "
        "Intentando AVI..."
    )

    output_video_path = (
        OUTPUT_DIR /
        "EDGE_MegaDetector_demo.avi"
    )

    fourcc = cv2.VideoWriter_fourcc(
        *"MJPG"
    )

    video_writer = cv2.VideoWriter(
        str(output_video_path),
        fourcc,
        2.0,
        (
            OUTPUT_WIDTH,
            OUTPUT_HEIGHT
        )
    )


if not video_writer.isOpened():

    raise RuntimeError(
        "No pude crear el video de salida."
    )


# ============================================================
# 14. INTERVALO DE MUESTREO
# ============================================================

frame_interval = max(
    1,
    int(
        fps *
        SAMPLE_EVERY_SECONDS
    )
)


print("\n")
print("=" * 65)
print("INICIANDO PIPELINE")
print("=" * 65)


print(
    "\nAnalizando aproximadamente "
    "1 frame cada",
    SAMPLE_EVERY_SECONDS,
    "segundos."
)


# ============================================================
# 15. CONTADORES
# ============================================================

records = []


frame_number = 0

sample_number = 0


frames_kept = 0

frames_discarded = 0


total_animals = 0

total_persons = 0

total_vehicles = 0


total_input_bytes = 0

total_candidate_bytes = 0


processing_start = time.time()


# ============================================================
# 16. PROCESAR VIDEO
# ============================================================

while True:

    success, frame = cap.read()


    if not success:

        break


    # --------------------------------------------------------
    # ANALIZAR SOLO CADA X SEGUNDOS
    # --------------------------------------------------------

    if (
        frame_number %
        frame_interval != 0
    ):

        frame_number += 1

        continue


    sample_number += 1


    # --------------------------------------------------------
    # LIMITE OPCIONAL
    # --------------------------------------------------------

    if (
        MAX_SAMPLES is not None
        and
        sample_number > MAX_SAMPLES
    ):

        break


    video_time = (
        frame_number /
        fps
    )


    print(
        f"\rMuestra {sample_number}"
        f" | video: {video_time:.1f}s",
        end="",
        flush=True
    )


    # ========================================================
    # GUARDAR FRAME TEMPORAL
    #
    # Usamos JPG porque es la ruta más sencilla y robusta
    # para MegaDetector.
    # ========================================================

    temp_frame_path = (
        TEMP_DIR /
        f"sample_{sample_number:04d}.jpg"
    )


    cv2.imwrite(
        str(temp_frame_path),
        frame
    )


    # ========================================================
    # TAMANO DEL FRAME ORIGINAL
    # ========================================================

    try:

        input_bytes = (
            temp_frame_path.stat().st_size
        )

    except:

        input_bytes = 0


    total_input_bytes += (
        input_bytes
    )


    # ========================================================
    # MEGADETECTOR
    # ========================================================

    inference_start = time.time()


    result = model.single_image_detection(
        str(temp_frame_path),
        det_conf_thres=(
            CONFIDENCE_THRESHOLD
        )
    )


    inference_time = (
        time.time()
        -
        inference_start
    )


    detections = (
        result[
            "detections"
        ]
    )


    # ========================================================
    # VARIABLES DE ESTE FRAME
    # ========================================================

    animal_count = 0

    person_count = 0

    vehicle_count = 0


    max_animal_confidence = 0.0


    candidate_bytes_frame = 0


    annotated = (
        frame.copy()
    )


    # ========================================================
    # PROCESAR DETECCIONES
    # ========================================================

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
                    "unknown"
                )
            )


            x1, y1, x2, y2 = [
                int(value)
                for value
                in boxes[
                    detection_index
                ]
            ]


            # ------------------------------------------------
            # LIMITAR COORDENADAS
            # ------------------------------------------------

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


            # =================================================
            # ANIMAL
            # =================================================

            if label == "animal":

                animal_count += 1

                total_animals += 1


                max_animal_confidence = max(
                    max_animal_confidence,
                    confidence
                )


                # ---------------------------------------------
                # RECORTAR ANIMAL
                # ---------------------------------------------

                crop = frame[
                    y1:y2,
                    x1:x2
                ]


                if crop.size > 0:

                    candidate_name = (
                        f"{video_path.stem}"
                        f"_sample_{sample_number:04d}"
                        f"_time_{video_time:06.1f}s"
                        f"_conf_{confidence:.2f}.jpg"
                    )


                    candidate_path = (
                        CANDIDATES_DIR /
                        candidate_name
                    )


                    cv2.imwrite(
                        str(candidate_path),
                        crop
                    )


                    try:

                        crop_bytes = (
                            candidate_path
                            .stat()
                            .st_size
                        )

                    except:

                        crop_bytes = 0


                    candidate_bytes_frame += (
                        crop_bytes
                    )


                    total_candidate_bytes += (
                        crop_bytes
                    )


            # =================================================
            # PERSON
            # =================================================

            elif label == "person":

                person_count += 1

                total_persons += 1


            # =================================================
            # VEHICLE
            # =================================================

            elif label == "vehicle":

                vehicle_count += 1

                total_vehicles += 1


            # =================================================
            # DIBUJAR BOX
            # =================================================

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


            box_text = (
                f"{label.upper()} "
                f"{confidence:.2f}"
            )


            cv2.putText(
                annotated,
                box_text,
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


    # ========================================================
    # DECISION DEL EDGE
    # ========================================================

    if animal_count > 0:

        keep = True

        frames_kept += 1

        decision = (
            "KEEP -> NEXT STAGE"
        )

    else:

        keep = False

        frames_discarded += 1

        decision = (
            "DISCARD AT EDGE"
        )


    # ========================================================
    # PANEL SUPERIOR NEGRO
    # ========================================================

    cv2.rectangle(
        annotated,
        (
            0,
            0
        ),
        (
            min(
                width,
                850
            ),
            160
        ),
        (
            0,
            0,
            0
        ),
        -1
    )


    # ========================================================
    # TEXTO DE DEMO
    # ========================================================

    cv2.putText(
        annotated,
        "PANTHERAID - EDGE / MEGADETECTOR",
        (
            20,
            35
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (
            255,
            255,
            255
        ),
        2
    )


    cv2.putText(
        annotated,
        f"Video time: {video_time:.1f} sec",
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
        f"EDGE DECISION: {decision}",
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
            140
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


    # ========================================================
    # AJUSTAR DIMENSIONES PARA VIDEO
    # ========================================================

    if (
        annotated.shape[1] != OUTPUT_WIDTH
        or
        annotated.shape[0] != OUTPUT_HEIGHT
    ):

        video_frame = cv2.resize(
            annotated,
            (
                OUTPUT_WIDTH,
                OUTPUT_HEIGHT
            )
        )

    else:

        video_frame = annotated


    # ========================================================
    # GUARDAR VIDEO DEMO
    # ========================================================

    video_writer.write(
        video_frame
    )


    # ========================================================
    # GUARDAR JPG ANOTADO SOLO SI HAY ANIMAL
    # ========================================================

    if keep:

        annotated_path = (
            ANNOTATED_DIR /
            (
                f"detection_"
                f"{sample_number:04d}"
                f"_time_"
                f"{video_time:06.1f}s.jpg"
            )
        )


        cv2.imwrite(
            str(annotated_path),
            annotated
        )


    # ========================================================
    # GUARDAR RESULTADO
    # ========================================================

    records.append(
        {
            "sample_number":
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
                    else "DISCARD"
                ),

            "input_jpeg_bytes":
                input_bytes,

            "candidate_jpeg_bytes":
                candidate_bytes_frame,

            "inference_seconds":
                round(
                    inference_time,
                    3
                )
        }
    )


    frame_number += 1


# ============================================================
# 17. CERRAR ARCHIVOS
# ============================================================

cap.release()

video_writer.release()


processing_time = (
    time.time()
    -
    processing_start
)


# ============================================================
# 18. DATAFRAME
# ============================================================

df = pd.DataFrame(
    records
)


if len(df) == 0:

    raise RuntimeError(
        "No se procesaron muestras."
    )


# ============================================================
# 19. GUARDAR CSV
# ============================================================

csv_path = (
    OUTPUT_DIR /
    "megadetector_results.csv"
)


df.to_csv(
    csv_path,
    index=False
)


# ============================================================
# 20. CALCULOS
# ============================================================

total_samples = len(df)


discard_percentage = (
    frames_discarded /
    total_samples *
    100
)


keep_percentage = (
    frames_kept /
    total_samples *
    100
)


input_mb = (
    total_input_bytes /
    1024 /
    1024
)


candidate_mb = (
    total_candidate_bytes /
    1024 /
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


# ============================================================
# 21. RESULTADOS EN CONSOLA
# ============================================================

print("\n\n")
print("=" * 65)
print("RESULTADOS")
print("=" * 65)


print(
    "\nVideo:",
    video_path.name
)


print(
    "\nMuestras analizadas:",
    total_samples
)


print(
    "Muestras con animal:",
    frames_kept
)


print(
    "Muestras descartadas:",
    frames_discarded
)


print(
    "\nEDGE KEEP RATE:",
    round(
        keep_percentage,
        2
    ),
    "%"
)


print(
    "EDGE DISCARD RATE:",
    round(
        discard_percentage,
        2
    ),
    "%"
)


print(
    "\nAnimales detectados:",
    total_animals
)


print(
    "Personas detectadas:",
    total_persons
)


print(
    "Vehículos detectados:",
    total_vehicles
)


print(
    "\nDatos originales analizados:",
    round(
        input_mb,
        3
    ),
    "MB"
)


print(
    "Datos candidatos:",
    round(
        candidate_mb,
        3
    ),
    "MB"
)


print(
    "\nREDUCCION ESTIMADA DE PAYLOAD:",
    round(
        payload_reduction,
        2
    ),
    "%"
)


print(
    "\nNOTA:"
)

print(
    "Esto estima reducción usando JPG."
)

print(
    "NO representa todavía tráfico 5G real."
)


print(
    "\nInferencia promedio:",
    round(
        average_inference,
        3
    ),
    "segundos por muestra"
)


print(
    "Tiempo total:",
    round(
        processing_time,
        2
    ),
    "segundos"
)


# ============================================================
# 22. GRAFICO 1
# EDGE FILTER
# ============================================================

plt.figure(
    figsize=(
        8,
        5
    )
)


plt.bar(
    [
        "Discarded at Edge",
        "Kept for next stage"
    ],
    [
        frames_discarded,
        frames_kept
    ]
)


plt.ylabel(
    "Sampled frames"
)


plt.title(
    "MegaDetector Edge Filtering"
)


plt.tight_layout()


plt.savefig(
    OUTPUT_DIR /
    "03_edge_filtering.png",
    dpi=200
)


plt.show()


# ============================================================
# 23. GRAFICO 2
# CONFIDENCE VS TIME
# ============================================================

plt.figure(
    figsize=(
        10,
        5
    )
)


plt.plot(
    df[
        "video_time_seconds"
    ],
    df[
        "max_animal_confidence"
    ],
    marker="o"
)


plt.axhline(
    y=CONFIDENCE_THRESHOLD,
    linestyle="--"
)


plt.xlabel(
    "Video time (seconds)"
)


plt.ylabel(
    "Animal confidence"
)


plt.title(
    "MegaDetector Detection Through Time"
)


plt.ylim(
    0,
    1.05
)


plt.tight_layout()


plt.savefig(
    OUTPUT_DIR /
    "04_detection_timeline.png",
    dpi=200
)


plt.show()


# ============================================================
# 24. GRAFICO 3
# REDUCCION DE PAYLOAD
# ============================================================

plt.figure(
    figsize=(
        8,
        5
    )
)


plt.bar(
    [
        "Raw sampled JPG",
        "Animal candidates"
    ],
    [
        input_mb,
        candidate_mb
    ]
)


plt.ylabel(
    "Estimated data (MB)"
)


plt.title(
    "Estimated Data Reduction Before Transmission"
)


plt.tight_layout()


plt.savefig(
    OUTPUT_DIR /
    "05_payload_reduction.png",
    dpi=200
)


plt.show()


# ============================================================
# 25. GRAFICO 4
# TIEMPO DE INFERENCIA
# ============================================================

plt.figure(
    figsize=(
        10,
        5
    )
)


plt.plot(
    df[
        "video_time_seconds"
    ],
    df[
        "inference_seconds"
    ],
    marker="o"
)


plt.xlabel(
    "Video time (seconds)"
)


plt.ylabel(
    "Inference time (seconds)"
)


plt.title(
    "MegaDetector Edge Processing Time"
)


plt.tight_layout()


plt.savefig(
    OUTPUT_DIR /
    "06_inference_time.png",
    dpi=200
)


plt.show()


# ============================================================
# 26. LIMPIAR FRAMES TEMPORALES
# ============================================================

try:

    shutil.rmtree(
        TEMP_DIR
    )

except:

    pass


# ============================================================
# 27. FINAL
# ============================================================

print("\n")
print("=" * 65)
print("DEMO COMPLETADO")
print("=" * 65)


print(
    "\nCARPETA DE RESULTADOS:"
)

print(
    OUTPUT_DIR
)


print(
    "\nVIDEO CON DETECCIONES:"
)

print(
    output_video_path
)


print(
    "\nCANDIDATOS PARA SIGUIENTE ETAPA:"
)

print(
    CANDIDATES_DIR
)


print(
    "\nCSV:"
)

print(
    csv_path
)


print("\nPIPELINE DEMOSTRADO:")

print(
    "VIDEO -> EDGE -> MEGADETECTOR "
    "-> ANIMAL FILTER -> CANDIDATE "
    "-> [5G] -> [PANTHERAID]"
)


print("\nDONE :)")