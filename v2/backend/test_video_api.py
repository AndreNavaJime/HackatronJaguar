"""Integration tests for the v2 camera-trap video prototype.

Tests use a fake detector, not actual MegaDetector weights. OpenCV writes
a tiny local AVI and the background task is polled until completion.
"""
import base64
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


def test_video_size_limit(client):
    assert video_api.MAX_VIDEO_BYTES == 250 * 1024 * 1024
    response = client.post(
        '/api/videos/uploads',
        headers={'X-Video-Name': 'muy_grande.mp4',
                 'X-Video-Size': str(video_api.MAX_VIDEO_BYTES + 1)},
    )
    assert response.status_code == 413
    assert '250 MB' in response.json()['detail']


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
