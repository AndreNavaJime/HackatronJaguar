"""Tests for scientific monitoring and Edge APIs (no network or model weights)."""
import hashlib
import hmac
import json
import os

import pytest
from fastapi.testclient import TestClient

import main
import scientific_api


@pytest.fixture
def client():
    return TestClient(main.app)


def test_scientific_capabilities_honestly_label_prototype(client):
    response = client.get("/api/science/capabilities")
    assert response.status_code == 200
    assert response.json()["observation_storage"] == "browser_local_persistent_not_synced"
    assert response.json()["research_schema"] == "studies_deployments_encounters_sightings_individuals"
    assert response.json()["live_5g_measurements"] is False


def test_scientific_report_export_is_real_pdf(client):
    record = {
        "observation_id": "OBS-TEST-01", "observation_name": "Osa transect",
        "camera_id": "CT-07", "species": "Panthera onca",
        "validation_status": "researcher_review_pending",
        "camera_latitude": 9.7, "camera_longitude": -83.7,
    }
    reply = client.post("/api/science/reports/observation", json=record)
    assert reply.status_code == 200, reply.text[:200]
    assert reply.headers["content-type"].startswith("application/pdf")
    assert reply.content[:5] == b"%PDF-"
    assert len(reply.content) > 1000


def test_scientific_report_rejects_oversized_content(client):
    response = client.post("/api/science/reports/observation",
                           json={"notes": "x" * 14000})
    assert response.status_code == 413


def test_copernicus_validation_prevents_unbounded_queries(client):
    response = client.post("/api/science/sentinel/search",
                           json={"latitude": 90.2, "longitude": -85, "radius_km": 5})
    assert response.status_code == 422
    response = client.post("/api/science/sentinel/search",
                           json={"latitude": 10, "longitude": -85, "radius_km": 150})
    assert response.status_code == 422
    response = client.post("/api/science/sentinel/search",
                           json={"latitude": 10, "longitude": -85, "days_back": 400})
    assert response.status_code == 422


def test_copernicus_wrapper_without_external_connection(client, monkeypatch):
    def fake_search(query):
        assert query.latitude == 9.7
        assert query.radius_km == 5
        return {"source": "test mock catalogue", "sentinel_1": [],
                "sentinel_2": [], "bbox": [], "queried_at": "now"}
    monkeypatch.setattr(scientific_api, "_search_catalogue", fake_search)
    reply = client.post("/api/science/sentinel/search", json={"latitude": 9.7, "longitude": -83.6})
    assert reply.status_code == 200
    assert reply.json()["source"] == "test mock catalogue"


def test_edge_event_validation_unverified_demo(client, monkeypatch):
    monkeypatch.delenv("PANTHERA_HMAC_SECRET", raising=False)
    reply = client.post("/api/edge/validate", json={
        "event_id": "EDGE-01", "camera_id": "CT-07",
        "location": {"latitude": 9.7, "longitude": -83.8},
        "environment": {"temperature": 27, "humidity": 78},
    })
    assert reply.status_code == 200, reply.text
    payload = reply.json()
    assert payload["saved"] is False
    assert payload["verification"] == "NOT_CONFIGURED"
    assert payload["event"]["camera_id"] == "CT-07"
    assert payload["event"]["latitude"] == 9.7
    assert payload["event"]["temperature"] == 27


def test_edge_requires_proper_hmac_when_key_configured(client, monkeypatch):
    key = "test-only-secret"
    monkeypatch.setenv("PANTHERA_HMAC_SECRET", key)
    event = {"event_id": "EDGE-02", "camera_id": "CT-08", "event": "new_capture"}
    missing = client.post("/api/edge/validate", json=event)
    assert missing.status_code == 403
    signed = dict(event)
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    signed["hmac_sha256"] = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    valid = client.post("/api/edge/validate", json=signed)
    assert valid.status_code == 200, valid.text
    assert valid.json()["verification"] == "VALID"
    signed["camera_id"] = "CHANGED"
    tampered = client.post("/api/edge/validate", json=signed)
    assert tampered.status_code == 403
