import base64
import io
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

import main
import detection

client = TestClient(main.app)


def image_bytes(format='JPEG'):
    buf = io.BytesIO()
    Image.new('RGB', (320, 200), '#46704f').save(buf, format=format)
    return buf.getvalue()


def test_health():
    assert client.get('/api/health').json()['status'] == 'ok'


def test_photo_inspect():
    r = client.post('/api/images/inspect', content=image_bytes())
    assert r.status_code == 200, r.text
    assert r.json()['width'] == 320 and r.json()['saved'] is False


def test_invalid():
    assert client.post('/api/images/inspect', content=b'no').status_code == 422
    assert client.post('/api/images/inspect', content=b'').status_code == 400
    assert client.post('/api/images/detect?threshold=1.5', content=image_bytes()).status_code == 422


def test_megadetector_mock(monkeypatch):
    calls = []

    class MockModel:
        def single_image_detection(self, image_path, det_conf_thres):
            assert Path(image_path).exists()
            calls.append(image_path)
            return {'detections': SimpleNamespace(
                xyxy=[(20, 30, 170, 140), (210, 20, 270, 110)],
                confidence=[0.92, 0.83],
                class_id=[0, 1],
            )}

    monkeypatch.setattr(detection, '_get_model', lambda: (MockModel(), 'cpu'))
    r = client.post('/api/images/detect?threshold=0.4', content=image_bytes())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['counts'] == {'animal': 1, 'person': 1, 'vehicle': 0}
    assert data['detections'][0]['bbox_xyxy'] == [20, 30, 170, 140]
    Image.open(io.BytesIO(base64.b64decode(data['annotated_image'].split(',')[1]))).verify()
    assert not Path(calls[0]).exists()


def test_unavailable(monkeypatch):
    def unavailable():
        raise detection.DetectorUnavailable('Instalá PytorchWildlife')

    monkeypatch.setattr(detection, '_get_model', unavailable)
    r = client.post('/api/images/detect', content=image_bytes())
    assert r.status_code == 503
