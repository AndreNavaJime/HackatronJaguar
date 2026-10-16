"""Opt-in inference adapters for live camera frames.

No frames are persisted. Packages, model weights and suitable compute must be
explicitly provided by an operator; there are no simulated inference results.
Never mistake detector/texture predictions for validated species or wildfires.
"""
import logging
import os
import threading
from importlib.util import find_spec
from pathlib import Path

from PIL import Image

from detection import detect_image

log = logging.getLogger('pantheralab.live_ai')
_species_lock = threading.Lock()
_fire_lock = threading.Lock()
_species_model = None
_fire_model = None


class LiveModelUnavailable(Exception):
    pass


def wildlife_enabled():
    return find_spec('PytorchWildlife') is not None


def species_enabled():
    name = os.getenv('PANTHERA_SPECIESNET_MODEL', '').strip()
    return bool(name) and find_spec('speciesnet') is not None


def fire_enabled():
    path = os.getenv('PANTHERA_PYRO_MODEL_PATH', '').strip()
    return bool(path) and Path(path).is_file() and find_spec('pyroengine') is not None


def capabilities():
    return {
        'wildlife_detector': 'available' if wildlife_enabled() else 'unavailable',
        'speciesnet': 'configured' if species_enabled() else 'not_configured',
        'fire_detector': 'configured' if fire_enabled() else 'not_configured',
        'frigate_bridge': 'requires_gateway',
        'remote_webrtc': 'requires_gateway',
    }


def _classify_species(frame: Image.Image, detections: list[dict]):
    """SpeciesNet crop classifier uses the highest-confidence MegaDetector animal.

    Human frames are excluded in wildlife_frame. Results are hypotheses only.
    """
    global _species_model
    if not species_enabled():
        return None
    with _species_lock:
        try:
            if _species_model is None:
                from speciesnet.classifier import SpeciesNetClassifier
                _species_model = SpeciesNetClassifier(
                    model_name=os.environ['PANTHERA_SPECIESNET_MODEL'].strip()
                )
            candidates = sorted(
                (item for item in detections
                 if item.get('class_name') == 'animal'
                 and isinstance(item.get('bbox_xyxy'), list)
                 and len(item['bbox_xyxy']) == 4),
                key=lambda item: item.get('confidence', 0), reverse=True,
            )
            if not candidates:
                return None
            x1, y1, x2, y2 = candidates[0]['bbox_xyxy']
            x1 = max(0, min(frame.width - 1, int(x1)))
            y1 = max(0, min(frame.height - 1, int(y1)))
            x2 = max(x1 + 1, min(frame.width, int(x2)))
            y2 = max(y1 + 1, min(frame.height, int(y2)))
            cropped = frame.convert('RGB').crop((x1, y1, x2, y2))
            if cropped.width < 12 or cropped.height < 12:
                return None
            preprocessed = _species_model.preprocess(cropped)
            result = _species_model.predict('camera_frame.jpg', preprocessed)
            classes = result.get('classifications', {})
            labels = classes.get('classes', [])
            scores = classes.get('scores', [])
            return [
                {'label': str(label), 'score': round(float(score), 4)}
                for label, score in list(zip(labels, scores))[:5]
            ]
        except Exception as error:
            log.exception('SpeciesNet inference error')
            raise LiveModelUnavailable('La clasificación SpeciesNet falló. Revisá el servicio de IA.') from error


def wildlife_frame(frame: Image.Image, threshold: float):
    if not wildlife_enabled():
        raise LiveModelUnavailable('MegaDetector no está instalado en este servidor.')
    try:
        output = detect_image(frame, threshold)
    except Exception as error:
        log.exception('MegaDetector runtime error')
        raise LiveModelUnavailable('MegaDetector no pudo procesar el fotograma.') from error
    counts = output.get('counts', {})
    # Never classify, preserve or publish a frame containing a person.
    species = None
    status = 'not_run'
    if counts.get('animal', 0)>0 and counts.get('person', 0)==0:
        if species_enabled():
            try:
                species = _classify_species(frame, output.get('detections', []))
                status = 'suggested' if species else 'not_available'
            except LiveModelUnavailable:
                status = 'error'
        else:
            status = 'not_configured'
    return {
        'model': output['model'],
        'counts': counts,
        'detections': output.get('detections', []),
        'speciesnet': {'status': status, 'suggestions': species or []},
        'image_saved': False,
        'species_verified': False,
        'note': 'Detectores preliminares: revisión humana necesaria.',
    }


def fire_frame(frame: Image.Image):
    global _fire_model
    if not fire_enabled():
        raise LiveModelUnavailable('PyroEngine no está configurado en este servidor.')
    with _fire_lock:
        try:
            if _fire_model is None:
                from pyroengine import Engine
                _fire_model = Engine(model_path=os.environ['PANTHERA_PYRO_MODEL_PATH'].strip())
            confidence = float(_fire_model.predict(frame.convert('RGB')))
            if not 0.0 <= confidence <= 1.0:
                raise ValueError('confidence out of range')
        except Exception as error:
            log.exception('PyroEngine inference error')
            raise LiveModelUnavailable('PyroEngine no pudo analizar el fotograma.') from error
    return {
        'model': 'PyroEngine',
        'possible_fire': confidence>=0.5,
        'confidence': round(confidence, 4),
        'verified': False,
        'alert_dispatched': False,
        'image_saved': False,
        'note': 'Indicio de modelo sin validar; NO es un aviso de emergencia.',
    }
