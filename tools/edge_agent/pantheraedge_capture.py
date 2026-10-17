"""PantheraEDGE field prototype: unattended camera-event capture on a field gateway.

Requires: pip install opencv-python-headless
Requires a local, separately deployed wildlife detector that provides:
POST http://127.0.0.1:8000/api/live/wildlife-frame -> {counts:{animal,person},detections:[...]}
See docs/pantheralive-hybrid-edge-testbed.md. This does NOT enable AI on free Render,
upload footage, send notifications, identify individuals, or guarantee species IDs.
"""
from __future__ import annotations
import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid


def validate_local_detector(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Use a LOCAL HTTP detector only. Do not send field frames to remote services.")
    if parts.username or parts.password or parts.fragment:
        raise ValueError("Detector URL cannot contain credentials or fragments.")
    if not parts.path.startswith("/api/live/wildlife-frame"):
        raise ValueError("Expected a PantheraEDGE-compatible local wildlife-frame endpoint.")
    return url


def evaluate_detection(payload: dict) -> tuple[bool, bool, float]:
    """Returns animal_candidate, possible_person, detector_score (not ID probability)."""
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("Detector returned no counts (model not ready?).")
    animals = counts.get("animal")
    people = counts.get("person")
    if isinstance(animals, bool) or isinstance(people, bool) or not (
        isinstance(animals, int) and isinstance(people, int)
        and animals >= 0 and people >= 0
    ):
        raise ValueError("Detector returned invalid animal/person counts.")
    scores = [
        x.get("confidence", 0) for x in payload.get("detections", [])
        if isinstance(x, dict) and x.get("class_name") == "animal"
    ]
    valid = [float(x) for x in scores if isinstance(x, (int, float))
             and not isinstance(x, bool) and 0 <= x <= 1]
    return animals > 0 and people == 0, people > 0, max(valid, default=0.0)


def detector_call(url: str, image_bytes: bytes, timeout: float) -> tuple[bool, bool, float]:
    req = Request(url, data=image_bytes, method="POST",
                  headers={"Content-Type": "image/jpeg", "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        data = response.read(100_000)
    return evaluate_detection(json.loads(data))


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous PantheraEDGE field clip recorder")
    parser.add_argument("--source", required=True, help="Local camera index (0), video device, or RTSP address")
    parser.add_argument("--camera-id", required=True, help="Non-sensitive station identifier")
    parser.add_argument("--study-id", default="", help="Optional local study ID")
    parser.add_argument("--output", default="./edge_clips", help="Local PRIVATE directory")
    parser.add_argument("--detector", default="http://127.0.0.1:8000/api/live/wildlife-frame")
    parser.add_argument("--fps", type=int, default=8, help="Stored video frames per second, 2-15")
    parser.add_argument("--pre", type=int, default=3, help="Seconds before confirmed detection, 0-8")
    parser.add_argument("--post", type=int, default=5, help="Seconds after last detected animal, 2-15")
    parser.add_argument("--max-seconds", type=int, default=24, help="Maximum single event clip, 8-90")
    parser.add_argument("--interval", type=float, default=1.5, help="Inference interval in seconds, 0.5-10")
    args = parser.parse_args()
    validate_local_detector(args.detector)
    if not (2 <= args.fps <= 15 and 0 <= args.pre <= 8 and 2 <= args.post <= 15
            and 8 <= args.max_seconds <= 90 and .5 <= args.interval <= 10):
        parser.error("Recording parameters out of supported bounds.")
    if not args.camera_id or len(args.camera_id) > 80:
        parser.error("camera-id is required (max 80 characters).")
    if not all(c.isalnum() or c in "-_" for c in args.camera_id):
        parser.error("camera-id must contain only letters, numbers, hyphens or underscores.")

    # Import only on the field machine; regular PantheraLAB / test suite does not need OpenCV.
    try:
        import cv2  # type: ignore
    except ImportError:
        parser.error("Install opencv-python-headless on the gateway (not Render static site).")

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = int(args.source) if args.source.isdigit() else args.source
    camera = cv2.VideoCapture(source)
    if not camera.isOpened():
        raise RuntimeError("Could not open camera stream. Check local RTSP or USB access.")

    active = True
    def stop(*_):
        nonlocal active
        active = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    frames = deque(maxlen=max(1, args.fps * args.pre))
    writer = None
    clip_path: Path | None = None
    frame_limit = args.max_seconds * args.fps
    sample_at = inspect_at = last_animal = 0.0
    started = utc_start = ""
    written = 0
    score = 0.0
    cooldown_until = 0.0
    drop_clip = False

    def finish_clip() -> None:
        nonlocal writer, clip_path, written, started, utc_start, score, drop_clip
        if writer is None:
            return
        writer.release()
        writer = None
        if clip_path is None:
            return
        if drop_clip or written < args.fps or not clip_path.exists() or clip_path.stat().st_size < 1024:
            clip_path.unlink(missing_ok=True)
        else:
            metadata = {
                "contract_version": "panthera-live-clip-v1",
                "event_id": clip_path.stem,
                "camera_id": args.camera_id,
                "study_id": args.study_id or None,
                "captured_at": utc_start,
                "source": "edge_gateway",
                "candidate_class": "animal",
                "detector_score": round(score, 4),
                "model": "external local wildlife detector (verify separately)",
                "review_state": "pending",
                "clip_bytes": clip_path.stat().st_size,
                "duration_ms": round(written * 1000 / args.fps),
                "clip_filename": clip_path.name,
                "storage": "private_gateway_local_disk",
                "species_verified": False,
                "network_measurement": False,
                "notification_delivered": False
            }
            clip_path.with_suffix(".json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"EVENT {clip_path.stem} written locally; needs researcher review", flush=True)
        clip_path = None
        written = 0
        drop_clip = False
        score = 0.0

    print("PantheraEDGE running on field gateway. No cloud upload, no remote push alerts.", flush=True)
    try:
        while active:
            ok, frame = camera.read()
            if not ok:
                print("Camera feed stopped; exit for supervisor restart.", flush=True)
                break
            now = time.monotonic()
            if now < sample_at:
                continue
            sample_at = now + 1 / args.fps
            frame = cv2.resize(frame, (640, 360))
            if writer is not None:
                writer.write(frame)
                written += 1
                if written >= frame_limit:
                    finish_clip()
                    cooldown_until = now + args.post
            else:
                frames.append(frame.copy())

            if now >= inspect_at:
                inspect_at = now + args.interval
                image_ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                if not image_ok:
                    continue
                try:
                    detected, people, confidence = detector_call(args.detector, jpeg.tobytes(), timeout=6.0)
                except Exception as exc:
                    print(f"Detector unavailable; NOT recording based on movement: {type(exc).__name__}", flush=True)
                    # A silent or broken detector must not be treated as evidence of no animal.
                    continue
                if people and writer is not None:
                    drop_clip = True
                    finish_clip()
                    cooldown_until = now + args.post
                elif detected:
                    last_animal = now
                    if writer is not None:
                        score = max(score, confidence)
                    elif now >= cooldown_until:
                        utc_start = datetime.now(timezone.utc).isoformat()
                        clip_path = output / ("EDGE_" + uuid.uuid4().hex + ".mp4")
                        writer = cv2.VideoWriter(str(clip_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                                 args.fps, (640, 360))
                        if not writer.isOpened():
                            raise RuntimeError("VideoWriter failed: check MP4 codec availability on gateway.")
                        started = utc_start
                        score = confidence
                        written = 0
                        for buffered_frame in frames:
                            writer.write(buffered_frame)
                            written += 1
                        frames.clear()
                if writer is not None and now - last_animal > args.post:
                    finish_clip()
                    cooldown_until = now + args.post
    finally:
        finish_clip()
        camera.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
