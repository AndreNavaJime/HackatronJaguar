"""No-network proof that PantheraFIRE never fabricates real fire events."""
from fastapi.testclient import TestClient
import main
import fire_public_events as fire

client = TestClient(main.app)


def fixture():
    return {"events": [
        {"id": "EONET_123", "title": "Wildfire near a protected area",
         "closed": None,
         "categories": [{"id": "wildfires", "title": "Wildfires"}],
         "sources": [{"id": "INCIWEB", "url": "https://source.example/incident"}],
         "geometry": [{"date": "2026-10-15T00:00:00Z", "type": "Point", "coordinates": [-84, 10]}]},
        {"id": "EONET_124", "title": "Old closed fire",
         "closed": "2026-10-12T00:00:00Z",
         "categories": [{"id": "wildfires"}],
         "sources": [], "geometry": []},
        {"id": "EONET_999", "title": "Storm must not look like fire",
         "closed": None, "categories": [{"id": "severeStorms"}]},
    ]}


def test_nasa_event_projection_provenance_and_no_invented_alerts():
    data = fire._project_events(fixture(), "costa_rica", 30)
    assert data["source"] == "NASA EONET API v3"
    assert data["type"] == "reported_wildfire_events_not_active_fire_detections"
    assert data["count_returned"] == 2
    event = data["events"][0]
    assert event["open_in_catalogue"] is True
    assert event["reported_at"] == "2026-10-15T00:00:00Z"
    assert event["reference_url"] == "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_123"
    assert "confidence" not in event
    assert "possible_fire" not in event
    assert data["events"][1]["open_in_catalogue"] is False
    assert "NO" in data["limitations"]


def test_nasa_endpoint_caches_results_and_scopes_to_requested_region(monkeypatch):
    fire.CACHE.clear()
    calls=[]
    def fetch(region,days):
        calls.append((region,days))
        return fixture()
    monkeypatch.setattr(fire,"_read_public_events",fetch)
    first=client.get("/api/fire/nasa-events?region=costa_rica&days=30")
    assert first.status_code == 200, first.text
    again=client.get("/api/fire/nasa-events?region=costa_rica&days=30")
    assert again.status_code == 200
    assert calls == [("costa_rica", 30)]
    other=client.get("/api/fire/nasa-events?region=world&days=30")
    assert other.status_code == 200
    assert calls[-1] == ("world",30)
    fire.CACHE.clear()


def test_invalid_queries_rejected_before_any_external_request():
    for path in [
        "/api/fire/nasa-events?region=../../internal",
        "/api/fire/nasa-events?days=100000",
        "/api/fire/nasa-events?days=0",
        "/api/fire/nasa-events?days=nan",
    ]:
        response=client.get(path)
        assert response.status_code == 422


def test_empty_catalogue_does_not_claim_area_is_fire_free():
    response=fire._project_events({"events": []},"costa_rica",30)
    assert response["events"] == []
    assert response["count_returned"] == 0
    assert "Empty results" in response["limitations"]
