"""No-network quality checks for open Sentinel-2 and WorldCover analysis."""
import math

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from rasterio.crs import CRS

import main
import satellite_vegetation as veg

client = TestClient(main.app)
S3 = "https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/"


def query(**extra):
    return veg.VegetationQuery(
        latitude=9.7, longitude=-83.7, radius_km=0.5,
        days_back=90, max_cloud_cover=40, **extra
    )


def example_scene():
    return {
        "id": "REAL-S2-SCENE",
        "properties": {"datetime": "2026-10-01T16:00:00Z", "eo:cloud_cover": 8},
        "assets": {name: {
            "href": S3 + name + ".tif",
            "raster:bands": [{"scale": 0.0001, "offset": -0.1}],
        } for name in ("red", "nir", "swir16", "scl")}
    }


def test_rejects_bad_input_no_external_requests():
    for payload in [
        {"latitude": 91, "longitude": -84},
        {"latitude": 9, "longitude": -84, "radius_km": 99},
        {"latitude": 9, "longitude": -84, "days_back": 500},
        {"latitude": 9, "longitude": -84, "max_cloud_cover": 200},
        {"latitude": "NaN", "longitude": -84},
    ]:
        r = client.post("/api/science/vegetation/analyze", json=payload)
        assert r.status_code == 422, r.text


def test_asset_whitelist_and_scheme_rejection():
    good = {"href": S3 + "red.tif"}
    assert veg._approved_asset(good).endswith("red.tif")
    for url in (
        "http://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/red.tif",
        "https://evil.example/red.tif",
        "https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com.evil.com/x.tif",
        "file:///etc/passwd",
    ):
        with pytest.raises(ValueError):
            veg._approved_asset({"href": url})


def test_baseline_offset_is_applied_before_index():
    asset = {"raster:bands": [{"scale": .0001, "offset": -.1}]}
    values = veg._scaled_reflectance(np.array([5000, 8000], dtype=np.float32), asset)
    assert np.allclose(values, [.4, .7])


def test_real_index_math_cloud_mask_and_scene_metadata(monkeypatch):
    import rasterio
    class FakeSource:
        crs = CRS.from_epsg(32617)
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(rasterio, "open", lambda _: FakeSource())

    # raw 5000 red->0.4, raw 9000 nir->0.8, raw 4000 swir->0.3
    def sample(asset, crs, transform, resampling, world_cover=False):
        name=asset["href"].split("/")[-1]
        if name == "red.tif": return np.full((96,96), 5000, dtype=np.float32)
        if name == "nir.tif": return np.full((96,96), 9000, dtype=np.float32)
        if name == "swir16.tif": return np.full((96,96), 4000, dtype=np.float32)
        if name == "scl.tif":
            mask=np.full((96,96), 4, dtype=np.float32)
            mask[:24,:] = 9  # high-probability clouds
            return mask
        raise AssertionError(name)
    monkeypatch.setattr(veg, "_sample_band", sample)
    result=veg._scene_stats(example_scene(), query())
    assert result
    assert abs(result["ndvi_mean"] - (0.8-0.4)/(0.8+0.4)) < .001
    assert abs(result["ndmi_mean"] - (0.8-0.3)/(0.8+0.3)) < .001
    assert result["valid_pixel_fraction"] == .75
    assert result["ndvi_greater_0_4_pct"] == 0
    assert result["cloud_cover_scene_pct"] == 8


def test_worldcover_2021_tile_reference_and_class(monkeypatch):
    import rasterio
    class FakeSource:
        crs = CRS.from_epsg(4326)
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(rasterio, "open", lambda _: FakeSource())
    def sampled(asset, crs, dst_transform, resampling, world_cover=False):
        assert world_cover
        assert dst_transform.a < .0002  # geographic units, not metres
        arr=np.full((96,96), 20, dtype=np.float32)  # shrub
        arr[:48,:]=10  # trees
        return arr
    monkeypatch.setattr(veg, "_sample_band", sampled)
    # Longitude -83.7 lies in the -84 to -81 tile => W084.
    assert veg._world_cover_tile(query()).endswith("N09W084_Map.tif")
    percentage, warning=veg._world_cover_stats(query())
    assert percentage==50.0
    assert warning is None


def test_bounded_analysis_selects_real_scenes_and_warns_about_semantics(monkeypatch):
    monkeypatch.setattr(veg, "_search_scenes", lambda q: [example_scene(), example_scene()])
    stats={
        "ndvi_mean":.64,"ndmi_mean":.39,"valid_pixel_fraction":.84,
        "acquired_at":"2026-10-01T16:00:00Z","scene_id":"REAL-S2-SCENE",
        "cloud_cover_scene_pct":8.0,"sampled_valid_pixels":800,
        "ndvi_greater_0_4_pct":97.0
    }
    monkeypatch.setattr(veg, "_scene_stats", lambda s,q: dict(stats))
    monkeypatch.setattr(veg, "_world_cover_stats", lambda q: (74.2,None))
    result=veg._analyze(query())
    assert result["latest"]["ndvi_mean"]==.64
    assert result["tree_cover_worldcover_2021_pct"]==74.2
    assert result["analysis_type"]=="real_pixel_sample_experimental"
    assert "NO" in result["limitations"] or "no" in result["limitations"].lower()
    r=client.post("/api/science/vegetation/analyze", json={
        "latitude":9.7,"longitude":-83.7,"radius_km":.5
    })
    assert r.status_code==200,r.text
    assert r.json()["latest"]["ndvi_mean"]==.64


def test_no_imagery_fails_clearly(monkeypatch):
    monkeypatch.setattr(veg, "_search_scenes", lambda q: [])
    with pytest.raises(HTTPException) as exc:
        veg._analyze(query())
    assert exc.value.status_code==404
