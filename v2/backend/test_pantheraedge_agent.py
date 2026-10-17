"""Scientific contract tests for the optional external PantheraEDGE agent.

No camera, internet or detector weights are required to run these checks.
"""
import importlib.util
from pathlib import Path
import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "tools/edge_agent/pantheraedge_capture.py"
SPEC = importlib.util.spec_from_file_location("pantheraedge_capture", MODULE_PATH)
assert SPEC and SPEC.loader
edge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(edge)


def test_detector_frames_remain_on_local_gateway():
    assert edge.validate_local_detector(
        "http://127.0.0.1:8000/api/live/wildlife-frame?threshold=0.3")
    with pytest.raises(ValueError):
        edge.validate_local_detector("https://public-render.example/api/live/wildlife-frame")
    with pytest.raises(ValueError):
        edge.validate_local_detector("http://user:secret@localhost:8000/api/live/wildlife-frame")
    with pytest.raises(ValueError):
        edge.validate_local_detector("http://localhost:8000/api/unrelated")


def test_animal_proposals_stay_provisional_and_people_are_excluded():
    assert edge.evaluate_detection({"counts": {"animal": 1, "person": 0},
        "detections": [{"class_name": "animal", "confidence": .74}]}) == (True, False, .74)
    assert edge.evaluate_detection({"counts": {"animal": 1, "person": 1},
        "detections": [{"class_name": "animal", "confidence": .75}]}) == (False, True, .75)
    assert edge.evaluate_detection({"counts": {"animal": 0, "person": 0},
        "detections": []}) == (False, False, 0)


def test_broken_detector_must_not_trigger_recording():
    for bad in [
        {}, {"counts": {"animal": "1", "person": 0}},
        {"counts": {"animal": 0, "person": None}},
        {"counts": {"animal": -1, "person": 0}},
    ]:
        with pytest.raises(ValueError):
            edge.evaluate_detection(bad)
