"""Regression checks for field provenance and stateless observation exports."""
import unittest

from pydantic import ValidationError
from research_api import ScientificObservation, observation_geojson, export_pdf, copernicus_context
from unittest.mock import patch


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

    def test_pdf_report_is_generated(self):
        response = export_pdf(ScientificObservation(**self.base, institution="Conservación"))
        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF-"))
        self.assertIn("OBS-TEST-01", response.headers["content-disposition"])

    def test_sentinel_queries_only_fixed_collections(self):
        with patch("research_api._stac_search", side_effect=[
            {"count": 1, "items": [{"id": "S1", "datetime": "2026-10-10", "cloud_cover": None}]},
            {"count": 1, "items": [{"id": "S2", "datetime": "2026-10-10", "cloud_cover": 10}]},
        ]) as searched:
            response = copernicus_context(latitude=9.2, longitude=-83.1,
                                          radius_km=5, days_back=30, max_cloud_cover=40)
            self.assertEqual(response["sentinel_1"]["count"], 1)
            self.assertEqual(response["sentinel_2"]["count"], 1)
            self.assertEqual(searched.call_args_list[0].args[0]["collections"], ["sentinel-1-grd"])
            self.assertEqual(searched.call_args_list[1].args[0]["collections"], ["sentinel-2-l2a"])

    def test_unknown_extra_data_is_rejected(self):
        with self.assertRaises(ValidationError):
            ScientificObservation(**self.base, invented_measurement=42)


if __name__ == "__main__":
    unittest.main()
