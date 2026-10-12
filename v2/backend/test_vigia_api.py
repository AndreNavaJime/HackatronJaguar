"""Tests for optional authenticated Wokwi VIGÍA intake (no real radio or AI)."""
import os

import pytest
from fastapi.testclient import TestClient

from main import app
import vigia_api


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    monkeypatch.delenv("PANTHERA_VIGIA_INGEST_TOKEN", raising=False)
    monkeypatch.delenv("PANTHERA_VIGIA_DASHBOARD_TOKEN", raising=False)
    with vigia_api._event_lock:
        vigia_api._events.clear()


@pytest.fixture
def client():
    return TestClient(app)


def payload():
    return {
        "data": {"cam_id": "BROWNING-HP5U-01", "trigger": "pir",
                 "ts": "2026-10-05T00:00:00Z", "lat": "10.512", "lon": "-85.201"},
        "files": {"frames": ("IMG_0001.JPG", b"\\xff\\xd8\\xff\\xe0" + b"x" * 40, "image/jpeg")},
    }


def test_disabled_ingest_fails_closed(client):
    response = client.post("/api/edge/vigia/capture", **payload())
    assert response.status_code == 503
    assert client.get("/api/edge/vigia/status").json()["configured"] is False


def test_wrong_ingest_token_rejected(client, monkeypatch):
    monkeypatch.setenv("PANTHERA_VIGIA_INGEST_TOKEN", "real-test-node-secret")
    response = client.post("/api/edge/vigia/capture", headers={"X-Panthera-Node-Token": "wrong"}, **payload())
    assert response.status_code == 401
    assert client.get("/api/edge/vigia/status").json()["received_count"] == 0


def test_wokwi_capture_ack_and_idempotency(client, monkeypatch):
    monkeypatch.setenv("PANTHERA_VIGIA_INGEST_TOKEN", "real-test-node-secret")
    monkeypatch.setenv("PANTHERA_VIGIA_DASHBOARD_TOKEN", "real-test-dashboard-secret")
    auth = {"X-Panthera-Node-Token": "real-test-node-secret"}
    first = client.post("/api/edge/vigia/capture", headers=auth, **payload())
    assert first.status_code == 200, first.text
    assert first.json()["accepted"] is True
    assert first.json()["analyzed"] is False
    assert first.json()["saved"] is False
    assert first.json()["duplicate"] is False
    second = client.post("/api/edge/vigia/capture", headers=auth, **payload())
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert client.get("/api/edge/vigia/status").json()["received_count"] == 1
    assert client.get("/api/edge/vigia/latest").status_code == 401
    latest = client.get("/api/edge/vigia/latest", headers={
        "X-Panthera-Dashboard-Token": "real-test-dashboard-secret",
    })
    assert latest.status_code == 200
    event = latest.json()["event"]
    assert event["camera_id"] == "BROWNING-HP5U-01"
    assert event["latitude"] == 10.512
    assert event["source"] == "vigia_multipart"
    assert event["image_validated"] is False
    assert "5G no verificado" in event["transport"]


def test_invalid_coordinates_are_rejected(client, monkeypatch):
    monkeypatch.setenv("PANTHERA_VIGIA_INGEST_TOKEN", "secret")
    body = payload()
    body["data"]["lat"] = "nan"
    response = client.post("/api/edge/vigia/capture", headers={"X-Panthera-Node-Token": "secret"}, **body)
    assert response.status_code == 422


def test_invalid_media_and_oversized_content(client, monkeypatch):
    monkeypatch.setenv("PANTHERA_VIGIA_INGEST_TOKEN", "secret")
    body = payload()
    body["files"] = {"frames": ("invalid.jpg", b"not-a-jpeg", "image/jpeg")}
    assert client.post("/api/edge/vigia/capture", headers={"X-Panthera-Node-Token": "secret"}, **body).status_code == 422
    result = client.post("/api/edge/vigia/capture",
                         headers={"X-Panthera-Node-Token": "secret", "Content-Length": str(vigia_api.MAX_MULTIPART_BYTES + 1)},
                         **payload())
    assert result.status_code == 413
