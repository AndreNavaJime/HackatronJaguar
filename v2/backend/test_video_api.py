"""Integration tests for the v2 camera-trap video prototype.

Tests use a fake detector, not actual MegaDetector weights. OpenCV writes
a tiny local AVI and the background task is polled until completion.
"""
import base64
import errno
import io
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

pytest.importorskip("cv2")
pytest.importorskip("reportlab")
import cv2
import numpy as np

import main
import video_api


@pytest.fixture()
def client():
    return TestClient(main.app)


def _short_avi():
    """Create a small, locally decodable MJPEG clip."""
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as folder:
        path = Path(folder) / "camera.avi"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (80, 64))
        if not writer.isOpened():
            pytest.skip("El OpenCV del entorno no tiene codificador MJPEG.")
        for index in range(15):
            frame = np.zeros((64, 80, 3), dtype=np.uint8)
            frame[:] = (20, 110 + index, 35)
            writer.write(frame)
        writer.release()
        return path.read_bytes()


@pytest.fixture(autouse=True)
def isolate_model_prerequisites(monkeypatch):
    """Video tests use a fake detector; don't require heavyweight AI weights."""
    monkeypatch.setattr(video_api, "_video_prerequisites", lambda: {
        "ready_for_attempt": True,
        "modules": {"opencv": True, "pytorchwildlife": True, "torch": True, "reportlab": True},
        "missing": [], "message": "Bibliotecas disponibles para pruebas simuladas.",
        "instructions": [], "model_weights_checked": False, "codec_checked": False,
    })


def test_missing_dependencies_decline_upload_before_file_transfer(client, monkeypatch):
    monkeypatch.setattr(video_api, "_video_prerequisites", lambda: {
        "ready_for_attempt": False,
        "modules": {"opencv": False, "pytorchwildlife": False, "torch": False, "reportlab": True},
        "missing": ["opencv", "pytorchwildlife", "torch"],
        "message": "No se puede analizar video: faltan dependencias.",
        "instructions": ["Instalá MegaDetector: python -m pip install -r requirements-ai.txt"],
        "model_weights_checked": False, "codec_checked": False,
    })
    report = client.get("/api/videos/preflight")
    assert report.status_code == 200
    assert not report.json()["ready_for_attempt"]
    response = client.post("/api/videos/uploads",
                           headers={"X-Video-Name": "camara.avi", "X-Video-Size": "125000000"})
    assert response.status_code == 503
    assert "faltan dependencias" in response.json()["detail"]


def test_unexpected_video_failure_has_diagnostic_stage(client, monkeypatch):
    def broken_detector(_image, _threshold):
        raise RuntimeError("unexpected mock runtime issue")

    monkeypatch.setattr(video_api, "detect_image", broken_detector)
    response = client.post("/api/videos/jobs",
                           headers={"X-Video-Name": "camera.avi"}, content=_short_avi())
    assert response.status_code == 202
    identifier = response.json()["job_id"]
    for _ in range(100):
        payload = client.get(f"/api/videos/jobs/{identifier}").json()
        if payload["state"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert payload["state"] == "failed"
    assert payload["error_code"] == "unexpected_error"
    assert "Analizando fotograma" in payload["error"]
    assert "RuntimeError" in payload["error"]
    assert "unexpected mock runtime issue" not in payload["error"]


def test_video_size_limit(client):
    assert video_api.MAX_VIDEO_BYTES == 1024 * 1024 * 1024
    assert video_api.MAX_DURATION_SECONDS == 3600
    response = client.post(
        '/api/videos/uploads',
        headers={'X-Video-Name': 'muy_grande.mp4',
                 'X-Video-Size': str(video_api.MAX_VIDEO_BYTES + 1)},
    )
    assert response.status_code == 413
    assert '1 GB' in response.json()['detail']



def test_one_gib_upload_session_does_not_allocate_video_in_ram(client, monkeypatch):
    """Accept the max declared size without creating or uploading a 1-GiB fixture."""
    monkeypatch.setattr(video_api, "_disk_capacity_for_upload", lambda size: {
        "can_accept": True, "free_bytes": 10 * 1024**3,
        "required_bytes": size + 2 * 1024**3, "message": "Espacio adecuado",
    })
    size = 1024**3
    response = client.post(
        "/api/videos/uploads",
        headers={"X-Video-Name": "camaratrampa.avi", "X-Video-Size": str(size)},
    )
    assert response.status_code == 201, response.text
    upload_id = response.json()["upload_id"]
    assert response.json()["expected_bytes"] == size
    snapshot = client.get(f"/api/videos/jobs/{upload_id}").json()
    assert snapshot["expected_bytes"] == size
    assert snapshot["received_bytes"] == 0
    canceled = client.delete(f"/api/videos/uploads/{upload_id}")
    assert canceled.status_code == 204


def test_insufficient_disk_rejects_large_upload(client, monkeypatch):
    usage = type("Usage", (), {"free": 2 * 1024**3})()
    monkeypatch.setattr(video_api.shutil, "disk_usage", lambda _: usage)
    size = 1024**3
    preflight = client.get("/api/videos/preflight", params={"expected_bytes": size})
    assert preflight.status_code == 200
    data = preflight.json()
    assert data["max_video_bytes"] == size
    assert not data["storage"]["can_accept"]
    assert not data["ready_for_attempt"]
    response = client.post(
        "/api/videos/uploads",
        headers={"X-Video-Name": "video.avi", "X-Video-Size": str(size)},
    )
    assert response.status_code == 507
    assert "Espacio insuficiente" in response.json()["detail"]


def test_disk_full_during_chunk_returns_actionable_error(client, monkeypatch):
    """ENOSPC during an upload is reported as HTTP 507, not a vague 500."""
    from pathlib import Path
    monkeypatch.setattr(video_api, "_disk_capacity_for_upload", lambda size: {
        "can_accept": True, "free_bytes": 10 * 1024**3,
        "required_bytes": size, "message": "Espacio para comenzar.",
    })
    created = client.post("/api/videos/uploads",
                          headers={"X-Video-Name": "test.avi", "X-Video-Size": "2000"})
    assert created.status_code == 201, created.text
    identifier = created.json()["upload_id"]
    original_open = Path.open

    def failed_write(path, mode="r", *args, **kwargs):
        if path.name == "entrada.avi" and mode == "ab":
            raise OSError(errno.ENOSPC, "No space left on device")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failed_write)
    response = client.put(f"/api/videos/uploads/{identifier}/chunks?offset=0",
                          content=b"x" * 500)
    assert response.status_code == 507, response.text
    assert "sin espacio" in response.json()["detail"]
    assert client.delete(f"/api/videos/uploads/{identifier}").status_code == 204


def test_large_single_post_must_use_chunked_endpoint(client):
    response = client.post(
        "/api/videos/jobs", headers={"X-Video-Name": "video.avi"},
        content=b"x" * (video_api.MAX_UPLOAD_CHUNK_BYTES + 1)
    )
    assert response.status_code == 413
    assert "bloques" in response.json()["detail"]


def test_video_input_validation(client):
    assert client.post("/api/videos/jobs", headers={"X-Video-Name": "not-a-video.txt"}, content=b"x").status_code == 415
    assert client.post("/api/videos/jobs", headers={"X-Video-Name": "empty.mp4"}, content=b"").status_code == 400
    assert client.post("/api/videos/jobs?threshold=1.2", headers={"X-Video-Name": "test.mp4"}, content=b"abc").status_code == 422
    assert client.get("/api/videos/jobs/nonexistent").status_code == 404


def test_video_processing_end_to_end_mock(client, monkeypatch):
    calls = []

    def fake_detector(image, threshold):
        calls.append(threshold)
        retained = len(calls) % 2 == 1
        detections = ([{"class_name": "animal", "confidence": 0.87,
                        "bbox_xyxy": [5, 8, 40, 44]}] if retained else [])
        bio = io.BytesIO()
        image.save(bio, "JPEG")
        encoded = "data:image/jpeg;base64," + base64.b64encode(bio.getvalue()).decode("ascii")
        return {
            "model": "MegaDetector V6 (MODELO SIMULADO)",
            "device": "cpu",
            "inference_seconds": 0.003,
            "detections": detections,
            "counts": {"animal": int(retained), "person": 0, "vehicle": 0},
            "annotated_image": encoded,
        }

    monkeypatch.setattr(video_api, "detect_image", fake_detector)
    raw = _short_avi()
    response = client.post(
        "/api/videos/jobs?threshold=0.25&sample_seconds=0.5&max_samples=6",
        headers={"X-Video-Name": "camera.avi", "Content-Type": "video/x-msvideo"},
        content=raw,
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    for _ in range(100):
        status = client.get("/api/videos/jobs/" + job_id)
        assert status.status_code == 200, status.text
        state = status.json()["state"]
        if state in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert state == "completed", status.json()
    data = status.json()["result"]
    assert data["totals"]["sampled"] == 6
    assert data["totals"]["retained"] == 3
    assert data["totals"]["discarded"] == 3
    assert data["totals"]["animals"] == 3
    assert data["totals"]["estimated_payload_reduction"] >= 0
    assert len(data["frames"]) == 6
    assert len(data["candidates"]) == 3
    assert len(data["rows"]) == 6
    assert calls == [0.25] * 6
    for kind in ("csv", "zip", "pdf"):
        reply = client.get("/api/videos/jobs/" + job_id + "/download?kind=" + kind)
        assert reply.status_code == 200, (kind, reply.text[:300])
        assert len(reply.content) > 100
        if kind == "pdf":
            assert reply.content.startswith(b"%PDF-")
        if kind == "zip":
            with zipfile.ZipFile(io.BytesIO(reply.content)) as archive:
                names = archive.namelist()
                assert "resultados_por_fotograma.csv" in names
                assert len([name for name in names if name.startswith("candidatos/")]) == 3
                assert len([name for name in names if name.startswith("retenidos/")]) == 3


def test_corrupt_video_reports_clear_error(client):
    response = client.post(
        "/api/videos/jobs", headers={"X-Video-Name": "corrupto.mp4"}, content=b"not video"
    )
    assert response.status_code == 202
    identifier = response.json()["job_id"]
    for _ in range(60):
        payload = client.get("/api/videos/jobs/" + identifier).json()
        if payload["state"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert payload["state"] == "failed"
    assert "OpenCV" in payload["error"] or "video" in payload["error"]


def test_chunked_video_upload_and_inference(client, monkeypatch):
    """Exercise the same upload protocol that the React frontend uses."""
    calls = []

    def fake_detector(image, threshold):
        calls.append(image.size)
        bio = io.BytesIO()
        image.save(bio, "JPEG")
        encoded = "data:image/jpeg;base64," + base64.b64encode(bio.getvalue()).decode("ascii")
        return {
            "model": "MegaDetector V6 (SIMULACIÓN)",
            "device": "cpu",
            "inference_seconds": 0.002,
            "detections": [{"class_name": "animal", "confidence": 0.8,
                            "bbox_xyxy": [10, 10, 55, 50]}],
            "counts": {"animal": 1, "person": 0, "vehicle": 0},
            "annotated_image": encoded,
        }

    monkeypatch.setattr(video_api, "detect_image", fake_detector)
    data = _short_avi()
    start = client.post(
        "/api/videos/uploads?threshold=0.25&sample_seconds=0.5&max_samples=5",
        headers={"X-Video-Name": "camara.avi", "X-Video-Size": str(len(data))},
    )
    assert start.status_code == 201, start.text
    upload_id = start.json()["upload_id"]
    assert start.json()["chunk_max_bytes"] >= 8192

    not_complete = client.post("/api/videos/uploads/" + upload_id + "/complete")
    assert not_complete.status_code == 409

    wrong = client.put(
        f"/api/videos/uploads/{upload_id}/chunks?offset=1",
        content=data[:1000],
    )
    assert wrong.status_code == 409

    step = max(256, len(data) // 7)
    for offset in range(0, len(data), step):
        piece = data[offset:offset + step]
        uploaded = client.put(
            f"/api/videos/uploads/{upload_id}/chunks?offset={offset}",
            content=piece,
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["received_bytes"] == offset + len(piece)

    done = client.post(f"/api/videos/uploads/{upload_id}/complete")
    assert done.status_code == 202, done.text
    assert done.json()["job_id"] == upload_id

    for _ in range(100):
        state = client.get("/api/videos/jobs/" + upload_id)
        assert state.status_code == 200, state.text
        payload = state.json()
        if payload["state"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert payload["state"] == "completed", payload
    assert payload["result"]["totals"]["sampled"] == 5
    assert payload["result"]["totals"]["retained"] == 5
    assert len(calls) == 5
    for kind in ("csv", "zip", "pdf"):
        reply = client.get(f"/api/videos/jobs/{upload_id}/download?kind={kind}")
        assert reply.status_code == 200, kind
        assert reply.content


def test_chunk_session_rejects_oversize_and_supports_cancel(client):
    start = client.post(
        "/api/videos/uploads",
        headers={"X-Video-Name": "test.mp4", "X-Video-Size": "5"},
    )
    assert start.status_code == 201, start.text
    identifier = start.json()["upload_id"]
    too_many = client.put(
        f"/api/videos/uploads/{identifier}/chunks?offset=0",
        content=b"123456",
    )
    assert too_many.status_code == 413
    assert client.get(f"/api/videos/jobs/{identifier}").json()["state"] == "uploading"
    canceled = client.delete(f"/api/videos/uploads/{identifier}")
    assert canceled.status_code == 204
    assert client.get(f"/api/videos/jobs/{identifier}").status_code == 404
