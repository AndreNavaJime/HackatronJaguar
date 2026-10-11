"""Regression checks for field provenance and stateless observation exports."""
import unittest

from pydantic import ValidationError
from research_api import ScientificObservation, observation_geojson


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.base = {"observation_id": "OBS-TEST-01"}

    def test_unspecified_coordinates_are_not_fabricated(self):
        feature = observation_geojson(ScientificObservation(**self.base))
        self.assertIsNone(feature["geometry"])
        self.assertEqual(feature["properties"]["coordinate_provenance"], "sin_verificar")

    def test_geojson_uses_longitude_latitude_order(self):
        obs = ScientificObservation(**self.base, latitude=8.62, longitude=-83.12,
                                    coordinate_provenance="gps")
        feature = observation_geojson(obs)
        self.assertEqual(feature["geometry"]["coordinates"], [-83.12, 8.62])

    def test_environmental_readings_require_provenance(self):
        with self.assertRaises(ValidationError):
            ScientificObservation(**self.base, temperature_c=25.0)
        obs = ScientificObservation(**self.base, temperature_c=25.0,
                                    environmental_source="sensor logger")
        self.assertEqual(obs.temperature_c, 25.0)

    def test_half_coordinate_is_rejected(self):
        with self.assertRaises(ValidationError):
            ScientificObservation(**self.base, latitude=9.9)

    def test_invalid_ranged_values_are_rejected(self):
        with self.assertRaises(ValidationError):
            ScientificObservation(**self.base, humidity_percent=160, environmental_source="sensor")

    def test_deployment_cannot_follow_retrieval(self):
        with self.assertRaises(ValidationError):
            ScientificObservation(**self.base, deployed_at="2026-10-20", retrieved_at="2026-10-10")

    def test_unknown_extra_data_is_rejected(self):
        with self.assertRaises(ValidationError):
            ScientificObservation(**self.base, invented_measurement=42)


if __name__ == "__main__":
    unittest.main()
