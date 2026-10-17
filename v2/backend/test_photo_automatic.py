"""Contract tests for the automatic photo flow (no heavyweight model download)."""
import io

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import main


def photo_bytes():
    image = Image.new("RGB", (320, 240), "#ddbf8b")
    draw = ImageDraw.Draw(image)
    for x, y in [(90, 75), (120, 80), (150, 100), (190, 130)]:
        draw.ellipse((x-11, y-9, x+11, y+9), outline="#291e13", width=5)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def fake_result(with_person=False):
    detections = [
        {"class_name": "animal", "confidence": 0.91,
         "bbox_xyxy": [45, 45, 260, 210]},
    ]
    if with_person:
        detections.append({
            "class_name": "person", "confidence": 0.72,
            "bbox_xyxy": [265, 35, 300, 100],
        })
    return {
        "model": "mock-detector", "device": "cpu", "threshold": 0.25,
        "inference_seconds": 0.01,
        "counts": {"animal": 1, "person": int(with_person), "vehicle": 0},
        "detections": detections, "annotated_image": "data:image/jpeg;base64,aGVsbG8=",
        "note": "Detección preliminar",
    }


def test_photo_auto_returns_integrated_pattern_preview(monkeypatch):
    monkeypatch.setattr(main, "detect_image", lambda image, threshold: fake_result())
    response = TestClient(main.app).post("/api/images/analyze", content=photo_bytes())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["counts"]["animal"] == 1
    patterns = result["rosette_patterns"]
    assert patterns["status"] == "exploratory"
    assert patterns["scientifically_validated"] is False
    assert patterns["identity_verified"] is False
    assert len(patterns["samples"]) == 1
    assert patterns["samples"][0]["annotated_crop"].startswith("data:image/jpeg;base64,")


def test_photo_auto_skips_pattern_review_when_person_present(monkeypatch):
    monkeypatch.setattr(main, "detect_image", lambda image, threshold: fake_result(True))
    result = TestClient(main.app).post("/api/images/analyze", content=photo_bytes()).json()
    assert result["rosette_patterns"]["status"] == "skipped_people_present"
    assert result["rosette_patterns"]["samples"] == []


def test_photo_auto_invalid_file_and_threshold():
    client = TestClient(main.app)
    assert client.post("/api/images/analyze", content=b"bad").status_code == 422
    assert client.post("/api/images/analyze?threshold=9", content=photo_bytes()).status_code == 422
