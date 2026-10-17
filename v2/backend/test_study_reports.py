"""Integration tests for the longitudinal PantheraLAB study export pipeline."""
import base64
import io
import json
import zipfile

from fastapi.testclient import TestClient
from PIL import Image

from main import app

client = TestClient(app)


def study_data(redact=True, thumbnail=False):
    image = io.BytesIO()
    Image.new("RGB", (100, 70), color=(30, 90, 53)).save(image, format="JPEG")
    photo = "data:image/jpeg;base64," + base64.b64encode(image.getvalue()).decode()
    return {
        "study": {"study_id": "STUDY-OSA", "title": "Monitoreo de jaguares - Osa",
                  "lead": "Investigadora", "organization": "Laboratorio", "methodology": "Camaras trampa",
                  "objectives": "Registrar encuentros", "start_date": "2026-01-01", "end_date": "2026-10-12"},
        "deployments": [{
            "deployment_id": "DEP-01", "study_id": "STUDY-OSA", "camera_id": "CT-07",
            "site": "Corcovado", "latitude": 8.493, "longitude": -83.58,
            "altitude_m": 90, "operational_days": 14, "deployed_at": "2026-01-01",
            "retrieved_at": "2026-01-15",
        }],
        "individuals": [{
            "individual_id": "JAG-003", "study_id": "STUDY-OSA", "species": "Panthera onca",
            "sex": "male", "age_class": "adult", "marks": "Rosetas laterales derechas",
            "status": "verified", "validated_by": "Investigadora",
            "reference_image_url": "https://example.org/jaguar.jpg",
        }, {
            "individual_id": "JAG-004", "study_id": "STUDY-OSA", "species": "Panthera onca",
            "sex": "unknown", "status": "provisional",
        }],
        "encounters": [{
            "encounter_id": "EVT-01", "study_id": "STUDY-OSA", "deployment_id": "DEP-01",
            "occurred_at": "2026-10-08T12:00:00Z", "observer": "Investigadora",
            "temperature_c": 24, "humidity_percent": 86,
            "environment_source": "manual", "image_url": "https://example.org/raw_01.jpg",
            "thumbnail_data_url": photo if thumbnail else "",
        }, {
            "encounter_id": "EVT-02", "study_id": "STUDY-OSA", "deployment_id": "DEP-01",
            "occurred_at": "2026-10-10T12:00:00Z", "temperature_c": None,
            "humidity_percent": None, "environment_source": "unprovided",
        }],
        "sightings": [{
            "sighting_id": "OBS-01", "encounter_id": "EVT-01", "species": "Panthera onca",
            "individual_id": "JAG-003", "identification_status": "verified",
            "behavior": "walking", "reviewer": "Investigadora",
        }, {
            "sighting_id": "OBS-02", "encounter_id": "EVT-01", "species": "Panthera onca",
            "individual_id": "JAG-004", "identification_status": "tentative",
            "behavior": "resting",
        }, {
            "sighting_id": "OBS-03", "encounter_id": "EVT-02", "species": "Panthera onca",
            "individual_id": "JAG-003", "identification_status": "verified",
            "behavior": "marking", "reviewer": "Investigadora",
        }],
        "redact_coordinates": redact, "language": "es",
    }


def test_report_contains_full_study_and_multiple_animals():
    response = client.post("/api/science/studies/report?kind=pdf", json=study_data())
    assert response.status_code == 200, response.text[:240]
    assert response.content.startswith(b"%PDF-")
    assert len(response.content) > 1500
    assert "no-store" in response.headers["cache-control"]


def test_study_zip_includes_reproducible_descriptive_statistics():
    response = client.post("/api/science/studies/report?kind=zip", json=study_data())
    assert response.status_code == 200, response.text[:200]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        stats = json.loads(archive.read("statistics.json"))
        assert stats["capture_events"] == 2
        assert stats["animal_sightings"] == 3
        assert stats["verified_individuals"] == 1
        assert stats["observations_by_species"]["Panthera onca"] == 3
        assert stats["captures_by_camera"]["CT-07"] == 2
        assert stats["captures_by_month_utc"]["2026-10"] == 2
        assert stats["sightings_by_identification_status"]["verified"] == 2
        assert stats["sightings_by_identification_status"]["tentative"] == 1
        assert stats["reported_camera_days"] == 14
        assert round(stats["events_per_100_reported_camera_days"], 2) == 14.29
        assert stats["environmental_measurements"]["temperature_c"]["count"] == 1
        assert stats["environmental_measurements"]["temperature_c"]["mean"] == 24
        assert stats["environmental_measurements"]["humidity_percent"]["mean"] == 86
        assert "population" in stats["interpretation"]
        assert "latitude" not in stats and "longitude" not in stats


def test_missing_sampling_effort_does_not_generate_fake_camera_rates():
    data = study_data()
    data["deployments"][0]["operational_days"] = None
    response = client.post("/api/science/studies/report?kind=zip", json=data)
    assert response.status_code == 200, response.text[:200]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        stats = json.loads(archive.read("statistics.json"))
        assert stats["reported_camera_days"] is None
        assert stats["events_per_100_reported_camera_days"] is None


def test_study_zip_exports_relations_without_coordinates_by_default():
    response = client.post("/api/science/studies/report?kind=zip", json=study_data())
    assert response.status_code == 200, response.text[:250]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert set(["PantheraLAB_informe_integral.pdf", "study.json", "encounters.csv",
                "sightings.csv", "individuals.csv", "deployments.csv",
                "stations.geojson", "observations_flat.csv"]).issubset(archive.namelist())
    records = json.loads(archive.read("study.json"))
    assert records["deployments"][0]["latitude"] is None
    assert records["deployments"][0]["longitude"] is None
    assert len(records["sightings"]) == 3
    assert len(records["encounters"]) == 2
    assert "JAG-003" in archive.read("individuals.csv").decode()
    assert "EVT-02" in archive.read("observations_flat.csv").decode()
    geo = json.loads(archive.read("stations.geojson"))
    assert geo["features"][0]["geometry"] is None


def test_private_report_can_include_precise_locations_only_by_explicit_flag():
    response = client.post("/api/science/studies/report?kind=zip", json=study_data(False))
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    geo = json.loads(archive.read("stations.geojson"))
    assert geo["features"][0]["geometry"]["coordinates"] == [-83.58, 8.493]


def test_reference_thumbnail_is_in_pdf_and_archival_zip():
    response = client.post("/api/science/studies/report?kind=zip", json=study_data(thumbnail=True))
    assert response.status_code == 200, response.text[:300]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert "reference_thumbnails/EVT-01.jpg" in archive.namelist()
    assert archive.read("reference_thumbnails/EVT-01.jpg").startswith(b"\xff\xd8\xff")
    data = json.loads(archive.read("study.json"))
    assert data["encounters"][0]["thumbnail_filename"] == "reference_thumbnails/EVT-01.jpg"
    assert "thumbnail_data_url" not in data["encounters"][0]
    assert archive.read("PantheraLAB_informe_integral.pdf").startswith(b"%PDF-")


def test_links_cannot_reference_other_study_records():
    data = study_data()
    data["sightings"][0]["individual_id"] = "UNKNOWN"
    response = client.post("/api/science/studies/report", json=data)
    assert response.status_code == 422
    data = study_data()
    data["encounters"][0]["deployment_id"] = "DEP-MISSING"
    response = client.post("/api/science/studies/report", json=data)
    assert response.status_code == 422
    data = study_data()
    data["individuals"][0]["study_id"] = "SOMEONE-ELSE"
    response = client.post("/api/science/studies/report", json=data)
    assert response.status_code == 422


def test_duplicate_sightings_rejected_and_invalid_thumbnail_fails():
    data = study_data()
    data["sightings"][0]["sighting_id"] = "OBS-02"
    response = client.post("/api/science/studies/report", json=data)
    assert response.status_code == 422
    data = study_data()
    data["encounters"][0]["thumbnail_data_url"] = "data:image/jpeg;base64,MALFORMED"
    response = client.post("/api/science/studies/report", json=data)
    assert response.status_code == 422


def test_report_kind_and_oversize_guard():
    data = study_data()
    assert client.post("/api/science/studies/report?kind=docx", json=data).status_code == 422
    data["study"]["objectives"] = "X" * 2_410_000
    assert client.post("/api/science/studies/report", json=data).status_code == 413


def test_scoped_individual_history_and_capture_reports():
    data = study_data(thumbnail=True)
    individual = client.post("/api/science/studies/report?kind=pdf&individual_id=JAG-003", json=data)
    assert individual.status_code == 200, individual.text[:300]
    assert individual.content[:5] == b"%PDF-"
    assert "JAG-003" in individual.headers["content-disposition"]
    single_capture = client.post("/api/science/studies/report?kind=pdf&encounter_id=EVT-01", json=data)
    assert single_capture.status_code == 200, single_capture.text[:300]
    assert single_capture.content[:5] == b"%PDF-"
    assert "EVT-01" in single_capture.headers["content-disposition"]
    assert client.post("/api/science/studies/report?kind=pdf&individual_id=UNKNOWN",
                       json=data).status_code == 422
    assert client.post("/api/science/studies/report?kind=zip&individual_id=JAG-003",
                       json=data).status_code == 422
    assert client.post("/api/science/studies/report?kind=pdf&individual_id=JAG-003&encounter_id=EVT-01",
                       json=data).status_code == 422



def test_multiple_frames_of_one_analysis_stay_in_one_capture():
    data = study_data(thumbnail=True)
    data["encounters"][0]["source_analysis_id"] = "ANL-0001"
    data["encounters"][0]["source_video_name"] = "jaguar_osa.mp4"
    data["encounters"][0]["analysis_method"] = "OpenCV visual-change screening"
    data["encounters"][0]["analysis_samples"] = 8
    data["encounters"][0]["evidence_frames"] = [
        {"sample": 3, "time_seconds": 2.1, "motion_score": .07,
         "data_url": data["encounters"][0]["thumbnail_data_url"]},
        {"sample": 5, "time_seconds": 4.1, "motion_score": .03,
         "data_url": data["encounters"][0]["thumbnail_data_url"]},
    ]
    response = client.post("/api/science/studies/report?kind=zip", json=data)
    assert response.status_code == 200, response.text[:300]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert "reference_thumbnails/EVT-01.jpg" in archive.namelist()
    assert "reference_thumbnails/EVT-01_frame_3.jpg" in archive.namelist()
    assert "reference_thumbnails/EVT-01_frame_5.jpg" in archive.namelist()
    study = json.loads(archive.read("study.json"))
    assert len(study["encounters"]) == 2
    assert len(study["sightings"]) == 3
    first = study["encounters"][0]
    assert first["source_analysis_id"] == "ANL-0001"
    assert len(first["evidence_frames"]) == 2
    assert all("data_url" not in item for item in first["evidence_frames"])
    assert "jaguar_osa.mp4" in archive.read("observations_flat.csv").decode("utf-8")
    assert archive.read("PantheraLAB_informe_integral.pdf").startswith(b"%PDF-")


def test_reject_duplicate_video_analysis_and_unbounded_frame_gallery():
    dataset = study_data()
    for encounter in dataset["encounters"]:
        encounter["source_analysis_id"] = "ANL-DUPLICATE"
    assert client.post("/api/science/studies/report", json=dataset).status_code == 422
    dataset = study_data()
    dataset["encounters"][0]["evidence_frames"] = [
        {"sample": k, "time_seconds": float(k), "motion_score": .1,
         "data_url": "data:image/jpeg;base64,xxx"} for k in range(6)]
    assert client.post("/api/science/studies/report", json=dataset).status_code == 422


def test_inspected_photograph_provenance_export():
    data = study_data(thumbnail=True)
    event = data["encounters"][0]
    event["source_media_type"] = "image"
    event["source_video_name"] = "camera_07_2026.jpg"
    event["source_sha256"] = "abcdef1234" * 6 + "abcd"
    event["source_analysis_id"] = "ANL-IMAGE-01"
    event["analysis_method"] = "Photograph format inspection (no species identification)"
    event["analysis_samples"] = 1
    reply = client.post("/api/science/studies/report?kind=zip", json=data)
    assert reply.status_code == 200, reply.text[:200]
    with zipfile.ZipFile(io.BytesIO(reply.content)) as archive:
        assert "reference_thumbnails/EVT-01.jpg" in archive.namelist()
        flat = archive.read("observations_flat.csv").decode("utf-8")
        assert "camera_07_2026.jpg" in flat
        assert "Photograph format inspection" in flat
        assert "abcdef1234" in flat
        study = json.loads(archive.read("study.json"))
        assert study["encounters"][0]["source_media_type"] == "image"
        assert archive.read("PantheraLAB_informe_integral.pdf").startswith(b"%PDF-")
