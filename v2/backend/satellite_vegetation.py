"""Real, bounded vegetation statistics from open Sentinel-2 imagery.

Earth Search indexes freely accessible Level-2A COGs; ESA WorldCover 2021
supplies a separate, historic tree-cover classification. No satellite results
are ever generated from demonstration constants.

Area: at most 2 km radius, 96x96 sample grid, max three scenes per request.
Caveat: mean NDVI / NDMI is not animal presence or a forest-loss estimate.
"""
from __future__ import annotations

import json
import logging
import math
import time
from threading import Lock
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/science/vegetation", tags=["Sentinel-2 / Vegetación"])
log = logging.getLogger("pantheralab.vegetation")
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
S2_COLLECTION = "sentinel-2-c1-l2a"
WORLD_COVER_BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
SIZE = 96
_analysis_lock = Lock()
_last_analysis_at = 0.0
MIN_ANALYSIS_INTERVAL = 45.0  # global demo throttle; protect the free Render instance
WORLD_COVER_CLASSES = (10,)
VALID_SCL_CLASSES = (4, 5, 7)  # vegetation, bare soil, unclassified; no water/cloud/shadow


class VegetationQuery(BaseModel):
    latitude: float = Field(ge=-85, le=85, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    radius_km: float = Field(default=0.5, ge=0.2, le=2, allow_inf_nan=False)
    days_back: int = Field(default=90, ge=15, le=180)
    max_cloud_cover: float = Field(default=35, ge=0, le=80, allow_inf_nan=False)


def _read_json(url: str, payload: dict, max_bytes: int = 1_300_000) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "PantheraLAB-VegetationResearch/0.1",
    }, method="POST")
    with urlopen(request, timeout=18) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Respuesta geoespacial demasiado grande")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Respuesta STAC inválida")
    return result


def _search_scenes(q: VegetationQuery):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=q.days_back)
    payload = {
        "collections": [S2_COLLECTION],
        "intersects": {"type": "Point", "coordinates": [q.longitude, q.latitude]},
        "datetime": start.strftime("%Y-%m-%dT%H:%M:%SZ") + "/" + now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query": {"eo:cloud_cover": {"lte": q.max_cloud_cover}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        "limit": 12,
    }
    result = _read_json(EARTH_SEARCH, payload)
    features = result.get("features", [])
    if not isinstance(features, list):
        raise ValueError("La colección STAC no contiene escenas válidas")
    return features[:12]


def _approved_asset(asset: dict, world_cover: bool = False) -> str:
    url = asset.get("href") if isinstance(asset, dict) else None
    if not isinstance(url, str) or len(url) > 1600:
        raise ValueError("Recurso satelital inválido")
    parsed = urlsplit(url)
    allowed = (
        {"esa-worldcover.s3.eu-central-1.amazonaws.com"} if world_cover else
        {
            "e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com",
            "e84-earth-search-sentinel-data.s3.amazonaws.com",
            "sentinel-cogs.s3.us-west-2.amazonaws.com",
        }
    )
    if (parsed.scheme != "https" or parsed.hostname not in allowed or
            parsed.username or parsed.password or parsed.port or not parsed.path.endswith(".tif")):
        raise ValueError("Origen geoespacial no autorizado")
    return url


def _sample_band(asset: dict, dst_crs, dst_transform, resampling, world_cover=False):
    import rasterio
    from rasterio.warp import reproject

    href = _approved_asset(asset, world_cover=world_cover)
    arr = np.zeros((SIZE, SIZE), dtype=np.float32)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_TIMEOUT="12",
        GDAL_HTTP_MAX_RETRY="0",
        GDAL_CACHEMAX=24,
    ):
        with rasterio.open(href) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=arr,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=src.nodata,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_nodata=0,
                resampling=resampling,
                num_threads=1,
            )
    return arr


def _scaled_reflectance(raw, asset):
    """STAC raster:bands contains the scale and processing baseline offset."""
    bands = asset.get("raster:bands", []) if isinstance(asset, dict) else []
    band = bands[0] if isinstance(bands, list) and bands and isinstance(bands[0], dict) else {}
    scale = float(band.get("scale", 0.0001))
    offset = float(band.get("offset", 0))
    if not (math.isfinite(scale) and math.isfinite(offset) and 0 < scale <= 1 and -2 <= offset <= 2):
        raise ValueError("Corrección radiométrica fuera de límites")
    return raw * scale + offset


def _scene_stats(scene: dict, q: VegetationQuery):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import transform

    assets = scene.get("assets", {})
    if not isinstance(assets, dict) or not {"red", "nir", "swir16", "scl"}.issubset(assets):
        return None

    # Sentinel-2 L2A operates in a projected UTM zone. A point near a tile edge
    # will have nodata around it; the valid-pixel fraction makes this visible.
    red_asset = assets["red"]
    red_href = _approved_asset(red_asset)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_TIMEOUT="12", GDAL_HTTP_MAX_RETRY="0"):
        with rasterio.open(red_href) as src:
            crs = src.crs
            if crs is None or not crs.is_projected:
                raise ValueError("Se requiere una proyección métrica Sentinel-2")
    xs, ys = transform("EPSG:4326", crs, [q.longitude], [q.latitude])
    cx, cy = xs[0], ys[0]
    half = q.radius_km * 1000
    t = from_origin(cx - half, cy + half, (2 * half) / SIZE, (2 * half) / SIZE)

    raw_red = _sample_band(assets["red"], crs, t, Resampling.bilinear)
    raw_nir = _sample_band(assets["nir"], crs, t, Resampling.bilinear)
    raw_swir = _sample_band(assets["swir16"], crs, t, Resampling.bilinear)
    scl = _sample_band(assets["scl"], crs, t, Resampling.nearest).astype(np.uint8)

    red = _scaled_reflectance(raw_red, assets["red"])
    nir = _scaled_reflectance(raw_nir, assets["nir"])
    swir = _scaled_reflectance(raw_swir, assets["swir16"])

    valid = (
        np.isin(scl, VALID_SCL_CLASSES) &
        (raw_red > 0) & (raw_nir > 0) & (raw_swir > 0) &
        (red >= 0) & (nir >= 0) & (swir >= 0) &
        (red <= 1.25) & (nir <= 1.25) & (swir <= 1.25) &
        ((nir + red) > 0.02) & ((nir + swir) > 0.02)
    )

    valid_count = int(np.count_nonzero(valid))
    if valid_count < 75:
        return None

    ndvi = (nir[valid] - red[valid]) / (nir[valid] + red[valid])
    ndmi = (nir[valid] - swir[valid]) / (nir[valid] + swir[valid])
    cloud = scene.get("properties", {}).get("eo:cloud_cover")
    return {
        "scene_id": str(scene.get("id", ""))[:180],
        "acquired_at": str(scene.get("properties", {}).get("datetime", ""))[:60],
        "cloud_cover_scene_pct": round(float(cloud), 1) if isinstance(cloud, (float, int)) and math.isfinite(cloud) else None,
        "valid_pixel_fraction": round(valid_count / valid.size, 3),
        "sampled_valid_pixels": valid_count,
        "ndvi_mean": round(float(np.mean(ndvi)), 4),
        "ndmi_mean": round(float(np.mean(ndmi)), 4),
        "ndvi_greater_0_4_pct": round(float(np.count_nonzero(ndvi > 0.4) * 100 / valid_count), 1),
    }


def _world_cover_tile(q: VegetationQuery):
    """Class 10 represents mapped 'tree cover' in ESA WorldCover 2021 (not loss)."""
    def part(num, latitude):
        low = int(math.floor(num / 3) * 3)
        return ("N" if low >= 0 else "S") + f"{abs(low):02d}" if latitude else (
            ("E" if low >= 0 else "W") + f"{abs(low):03d}"
        )
    name = f"ESA_WorldCover_10m_2021_v200_{part(q.latitude, True)}{part(q.longitude, False)}_Map.tif"
    return WORLD_COVER_BASE + name


def _world_cover_stats(q: VegetationQuery):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    href = _world_cover_tile(q)
    # Reject areas crossing 3-degree tile boundaries rather than silently
    # treating uncovered pixels as non-forest.
    delta_lat = q.radius_km / 111.32
    delta_lon = q.radius_km / (111.32 * max(.01, math.cos(math.radians(q.latitude))))
    if (math.floor((q.latitude - delta_lat) / 3) != math.floor((q.latitude + delta_lat) / 3) or
            math.floor((q.longitude - delta_lon) / 3) != math.floor((q.longitude + delta_lon) / 3)):
        return None, "Área cruza límites de mosaicos WorldCover; se omitió clasificación histórica."
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_TIMEOUT="12", GDAL_HTTP_MAX_RETRY="0"):
        with rasterio.open(_approved_asset({"href": href}, world_cover=True)) as src:
            crs = src.crs
    if crs is None:
        raise ValueError("WorldCover sin referencia espacial")
    # WorldCover is EPSG:4326: construct a window in degrees (NOT metres).
    if not crs.is_geographic:
        raise ValueError("La capa WorldCover debe estar en coordenadas geográficas")
    t = from_origin(q.longitude - delta_lon, q.latitude + delta_lat,
                    (2 * delta_lon)/SIZE, (2 * delta_lat)/SIZE)
    raw = _sample_band({"href": href}, crs, t, Resampling.nearest, world_cover=True)
    valid = raw > 0
    count = int(np.count_nonzero(valid))
    if count < 100:
        return None, "WorldCover no tiene suficiente cobertura de píxeles para esta zona."
    # Class 10 contains natural forest AND some tree plantations: it is NOT
    # a percent canopy measure nor a certified forest/non-forest classifier.
    percentage = float(np.count_nonzero(raw[valid] == 10) * 100 / count)
    return round(percentage, 1), None


def _analyze(q: VegetationQuery):
    try:
        scenes = _search_scenes(q)
    except (URLError, HTTPError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as error:
        log.warning("Earth Search unavailable: %s", type(error).__name__)
        raise HTTPException(502, "El catálogo abierto Sentinel-2 no está disponible. Intentá más tarde.") from None
    if not scenes:
        raise HTTPException(404, "No hay escenas Sentinel-2 que cumplan las fechas y la nubosidad solicitadas.")

    chosen = []
    warnings = []
    for scene in scenes[:3]:
        try:
            stats = _scene_stats(scene, q)
            if stats:
                chosen.append(stats)
            else:
                warnings.append("Una escena no tuvo suficientes píxeles terrestres válidos.")
        except (ValueError, OSError, RuntimeError) as error:
            log.warning("Skipping Sentinel scene: %s", type(error).__name__)
            warnings.append("No se pudo procesar una de las escenas abiertas.")

    if not chosen:
        raise HTTPException(422,
            "Las escenas no aportaron suficientes píxeles válidos; probá otro período o menor nubosidad.")

    tree_cover = None
    try:
        tree_cover, issue = _world_cover_stats(q)
        if issue:
            warnings.append(issue)
    except (ValueError, OSError, RuntimeError) as error:
        log.warning("WorldCover unavailable: %s", type(error).__name__)
        warnings.append("WorldCover 2021 no estuvo disponible; se omitió cobertura arbórea histórica.")

    return {
        "source": "Earth Search / Sentinel-2 C1 L2A surface reflectance COGs",
        "tree_cover_source": "ESA WorldCover 2021 v200 class 10 (historical classification)",
        "analysis_type": "real_pixel_sample_experimental",
        "queried_at_utc": datetime.now(timezone.utc).isoformat(),
        "radius_km": q.radius_km,
        "grid_size": f"{SIZE}x{SIZE}",
        "latest": chosen[0],
        "previous": chosen[1] if len(chosen) >= 2 else None,
        "ndvi_mean_change_between_scenes": round(chosen[0]["ndvi_mean"] - chosen[1]["ndvi_mean"], 4) if len(chosen) > 1 else None,
        "tree_cover_worldcover_2021_pct": tree_cover,
        "warnings": list(dict.fromkeys(warnings)),
        "limitations": (
            "NDVI mide verdor, NDMI es un índice de humedad de vegetación; ninguno mide fauna o "
            "deforestación directamente. El umbral NDVI>0.4 NO representa porcentaje de bosque. "
            "WorldCover 2021 clase 10 es cobertura arbórea clasificada en 2021 (incluye plantaciones), "
            "no cobertura forestal actual ni pérdida anual. Las escenas pueden tener estacionalidad "
            "y nubosidad residual; las diferencias entre dos fechas NO demuestran deforestación. "
            "El área se muestrea en una cuadrícula limitada alrededor del punto."
        ),
    }


@router.post("/analyze")
async def analyze_vegetation(query: VegetationQuery):
    global _last_analysis_at
    if not _analysis_lock.acquire(blocking=False):
        raise HTTPException(429, "Ya se está procesando una consulta satelital. Esperá a que termine.")
    try:
        now = time.monotonic()
        if now - _last_analysis_at < MIN_ANALYSIS_INTERVAL:
            raise HTTPException(429, "Esperá 45 segundos entre consultas satelitales en el servidor gratuito.")
        _last_analysis_at = now
        return await run_in_threadpool(_analyze, query)
    finally:
        _analysis_lock.release()
