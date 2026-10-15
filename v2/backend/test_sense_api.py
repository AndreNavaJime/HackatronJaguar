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


def test_empty_dashboard_uses_cloud_demo_without_wokwi():
    response = client.get("/api/sense/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert data["simulation"] is True
    assert data["source"] == "cloud_simulation"
    assert data["storage"] == "computed_on_demand"
    assert data["generated_on_request"] is True
    assert data["latest"]["device_id"] == "PANTHERASENSE-CLOUD-01"
    assert len(data["history"]) == 12
    assert not sense_api._samples  # Synthetic samples are not persisted.


def test_absent_secret_disables_endpoint(monkeypatch):
    monkeypatch.delenv("PANTHERASENSE_INGEST_KEY")
    response = client.post("/api/sense/ingest", json=VALID,
                           headers={"X-PantheraSense-Key": KEY})
    assert response.status_code == 503


def test_missing_or_bad_key_rejected():
    assert client.post("/api/sense/ingest", json=VALID).status_code == 401
    assert client.post("/api/sense/ingest", json=VALID,
                       headers={"X-PantheraSense-Key": "wrong"}).status_code == 401
    assert client.get("/api/sense/latest").json()["source"] == "cloud_simulation"
    assert not sense_api._samples


def test_valid_telemetry_is_visible_but_temporary():
    response = client.post("/api/sense/ingest", json=VALID,
                           headers={"X-PantheraSense-Key": KEY})
    assert response.status_code == 202, response.text
    assert response.json()["storage"] == "ephemeral_process_memory"
    recent = client.get("/api/sense/latest").json()
    assert recent["status"] == "live"
    assert recent["source"] == "wokwi_virtual"
    assert recent["generated_on_request"] is False
    assert recent["latest"]["temperature_c"] == 24.0
    assert recent["latest"]["humidity_pct"] == 40
    assert recent["latest"]["simulation"] is True
    assert recent["latest"]["gas_alert"] is False  # Legacy Wokwi is compatible.
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
    {"gas_alert": "not-a-bool"},
])
def test_invalid_or_sensitive_payload_rejected(changes):
    payload = dict(VALID, **changes)
    response = client.post("/api/sense/ingest", json=payload,
                           headers={"X-PantheraSense-Key": KEY})
    assert response.status_code == 422, response.text


def test_mq2_simulated_gas_signal_reaches_dashboard():
    payload = dict(VALID, gas_alert=True)
    response = client.post("/api/sense/ingest", json=payload,
                           headers={"X-PantheraSense-Key": KEY})
    assert response.status_code == 202
    data = client.get("/api/sense/latest").json()
    assert data["source"] == "wokwi_virtual"
    assert data["simulation"] is True
    assert data["latest"]["gas_alert"] is True
    assert data["history"][0]["gas_alert"] is True
    assert "fire_confirmed" not in data["latest"]
    assert "latitude" not in data["latest"]


def test_next_normal_message_clears_gas_signal():
    for n, alarm in [(1, True), (2, False)]:
        payload = dict(VALID, reading_number=n, gas_alert=alarm)
        assert client.post("/api/sense/ingest", json=payload,
                           headers={"X-PantheraSense-Key": KEY}).status_code == 202
    data = client.get("/api/sense/latest").json()
    assert data["latest"]["gas_alert"] is False
    assert data["history"][-2]["gas_alert"] is True


def test_oversize_json_rejected():
    response = client.post("/api/sense/ingest",
                           content=b'{' + b' ' * 4096 + b'}',
                           headers={"X-PantheraSense-Key": KEY,
                                    "Content-Type": "application/json"})
    assert response.status_code == 413


def test_cloud_demo_is_repeatable_with_fresh_clock_and_no_storage():
    from datetime import datetime, timezone, timedelta
    stamp = datetime(2026, 10, 15, 12, 0, 11, tzinfo=timezone.utc)
    before = sense_api._cloud_demo_samples(stamp)
    assert before == sense_api._cloud_demo_samples(stamp + timedelta(seconds=10))
    after = sense_api._cloud_demo_samples(stamp + timedelta(seconds=30))
    assert after[-2] == before[-1]
    assert after[-1]["reading_number"] == before[-1]["reading_number"] + 1
    assert -40 <= after[-1]["temperature_c"] <= 85
    assert 0 <= after[-1]["humidity_pct"] <= 100
    assert not sense_api._samples


def test_stale_virtual_wokwi_readings_switch_to_cloud():
    from datetime import datetime, timedelta, timezone
    assert client.post("/api/sense/ingest", json=VALID,
                       headers={"X-PantheraSense-Key": KEY}).status_code == 202
    with sense_api._samples_lock:
        sense_api._samples[-1]["received_at_utc"] = (
            datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    result = client.get("/api/sense/latest").json()
    assert result["source"] == "cloud_simulation"
    assert result["generated_on_request"] is True
    assert len(sense_api._samples) == 1  # Actual Wokwi history is unchanged.


def test_only_recent_samples_kept():
    for i in range(32):
        payload = dict(VALID, reading_number=i + 1)
        assert client.post("/api/sense/ingest", json=payload,
                           headers={"X-PantheraSense-Key": KEY}).status_code == 202
    result = client.get("/api/sense/latest").json()
    assert result["latest"]["reading_number"] == 32
    assert len(result["history"]) == 12
    assert len(sense_api._samples) == 30
