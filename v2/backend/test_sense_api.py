"""Simulation-only PantheraSENSE ingest/read contract — no external network."""
import pytest
from fastapi.testclient import TestClient

import main
import sense_api

client = TestClient(main.app)
KEY = "test-only-device-token-123456789"
VALID = {
    "device_id": "PANTHERASENSE-01",
    "project": "PantheraSENSE",
    "simulation": True,
    "temperature_c": 24.0,
    "humidity_pct": 40.0,
    "uptime_s": 7,
    "reading_number": 1,
}


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    with sense_api._samples_lock:
        sense_api._samples.clear()
    monkeypatch.setenv("PANTHERASENSE_INGEST_KEY", KEY)
    yield
    with sense_api._samples_lock:
        sense_api._samples.clear()


def test_empty_dashboard_waits():
    response = client.get("/api/sense/latest")
    assert response.status_code == 200
    assert response.json()["status"] == "waiting"
    assert response.json()["simulation"] is True


def test_absent_secret_disables_endpoint(monkeypatch):
    monkeypatch.delenv("PANTHERASENSE_INGEST_KEY")
    response = client.post("/api/sense/ingest", json=VALID,
                           headers={"X-PantheraSense-Key": KEY})
    assert response.status_code == 503


def test_missing_or_bad_key_rejected():
    assert client.post("/api/sense/ingest", json=VALID).status_code == 401
    assert client.post("/api/sense/ingest", json=VALID,
                       headers={"X-PantheraSense-Key": "wrong"}).status_code == 401
    assert client.get("/api/sense/latest").json()["latest"] is None


def test_valid_telemetry_is_visible_but_temporary():
    response = client.post("/api/sense/ingest", json=VALID,
                           headers={"X-PantheraSense-Key": KEY})
    assert response.status_code == 202, response.text
    assert response.json()["storage"] == "ephemeral_process_memory"
    recent = client.get("/api/sense/latest").json()
    assert recent["status"] == "live"
    assert recent["latest"]["temperature_c"] == 24.0
    assert recent["latest"]["humidity_pct"] == 40
    assert recent["latest"]["simulation"] is True
    assert len(recent["history"]) == 1


@pytest.mark.parametrize("changes", [
    {"simulation": False},
    {"project": "Another project"},
    {"humidity_pct": 102},
    {"temperature_c": 999},
    {"temperature_c": "NaN"},
    {"reading_number": -1},
    {"device_id": "../secret"},
    {"latitude": 10.4},
])
def test_invalid_or_sensitive_payload_rejected(changes):
    payload = dict(VALID, **changes)
    response = client.post("/api/sense/ingest", json=payload,
                           headers={"X-PantheraSense-Key": KEY})
    assert response.status_code == 422, response.text


def test_oversize_json_rejected():
    response = client.post("/api/sense/ingest",
                           content=b'{' + b' ' * 4096 + b'}',
                           headers={"X-PantheraSense-Key": KEY,
                                    "Content-Type": "application/json"})
    assert response.status_code == 413


def test_only_recent_samples_kept():
    for i in range(32):
        payload = dict(VALID, reading_number=i + 1)
        assert client.post("/api/sense/ingest", json=payload,
                           headers={"X-PantheraSense-Key": KEY}).status_code == 202
    result = client.get("/api/sense/latest").json()
    assert result["latest"]["reading_number"] == 32
    assert len(result["history"]) == 12
    assert len(sense_api._samples) == 30
