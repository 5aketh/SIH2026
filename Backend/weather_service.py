"""
weather_service.py
Fetches real-time meteorological data from the Open-Meteo API (free, no key)
and computes 2-hour smoke dispersion vectors for fire alert points.
"""

import math
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Open-Meteo endpoint (free, no API key required)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Defaults when the API is unreachable or rate-limited
FALLBACK_WEATHER = {
    "temperature_2m": 30.0,       # °C
    "relative_humidity_2m": 50,    # %
    "wind_speed_10m": 5.0,        # km/h
    "wind_direction_10m": 0,      # degrees (from north)
}

# Smoke dispersion projection
DISPERSION_HOURS = 2              # project 2 hours forward
EARTH_RADIUS_KM = 6371.0


# ── Weather fetch ─────────────────────────────────────────────────────────────

def fetch_weather(lat: float, lon: float) -> dict:
    """
    Fetch current weather conditions for a single coordinate.

    Returns a dict with keys:
        temperature_2m, relative_humidity_2m, wind_speed_10m, wind_direction_10m
    Falls back to defaults on any error.
    """
    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        return {
            "temperature_2m": current.get("temperature_2m", FALLBACK_WEATHER["temperature_2m"]),
            "relative_humidity_2m": current.get("relative_humidity_2m", FALLBACK_WEATHER["relative_humidity_2m"]),
            "wind_speed_10m": current.get("wind_speed_10m", FALLBACK_WEATHER["wind_speed_10m"]),
            "wind_direction_10m": current.get("wind_direction_10m", FALLBACK_WEATHER["wind_direction_10m"]),
        }
    except Exception as e:
        logger.warning(f"Weather fetch failed for ({lat:.2f}, {lon:.2f}): {e}. Using fallback.")
        return dict(FALLBACK_WEATHER)


# ── Smoke dispersion vector ──────────────────────────────────────────────────

def compute_smoke_vector(
    origin_lat: float,
    origin_lon: float,
    wind_speed_kmh: float,
    wind_direction_deg: float,
    hours: float = DISPERSION_HOURS,
) -> dict:
    """
    Project a smoke dispersion endpoint from an origin point.

    Wind direction convention (meteorological): the direction FROM which
    the wind blows.  Smoke travels in the OPPOSITE direction, so we add 180°.

    Returns:
        bearing_deg:  bearing from north (0-360) that smoke travels toward
        distance_km:  projected distance over *hours*
        end_lat:      destination latitude
        end_lon:      destination longitude
    """
    distance_km = wind_speed_kmh * hours
    # Smoke travels downwind (opposite of wind-from direction)
    smoke_bearing_deg = (wind_direction_deg + 180.0) % 360.0

    bearing_rad = math.radians(smoke_bearing_deg)
    lat_rad = math.radians(origin_lat)
    lon_rad = math.radians(origin_lon)
    angular_dist = distance_km / EARTH_RADIUS_KM

    end_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(angular_dist)
        + math.cos(lat_rad) * math.sin(angular_dist) * math.cos(bearing_rad)
    )
    end_lon_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_dist) * math.cos(lat_rad),
        math.cos(angular_dist) - math.sin(lat_rad) * math.sin(end_lat_rad),
    )

    return {
        "bearing_deg": round(smoke_bearing_deg, 1),
        "distance_km": round(distance_km, 2),
        "end_lat": round(math.degrees(end_lat_rad), 6),
        "end_lon": round(math.degrees(end_lon_rad), 6),
    }


# ── Batch enrichment ─────────────────────────────────────────────────────────

def enrich_alerts(alerts_geojson: dict) -> dict:
    """
    Enrich alert features with weather data and smoke dispersion vectors.

    Coordinates are rounded to 0.1° (~11 km) to deduplicate API calls
    for nearby points.  Results are attached as ``weather`` and
    ``smoke_vector`` properties on each feature.

    Args:
        alerts_geojson: GeoJSON FeatureCollection of alert features.

    Returns:
        The same FeatureCollection with weather + smoke_vector injected.
    """
    features = alerts_geojson.get("features", [])
    if not features:
        return alerts_geojson

    # --- Deduplicate weather lookups by rounding to ~11 km grid ---
    grid_cache: dict[tuple, dict] = {}
    grid_keys: list[tuple] = []

    for feat in features:
        coords = feat.get("geometry", {}).get("coordinates") or []
        lon = coords[0] if isinstance(coords, (list, tuple)) and len(coords) > 0 else 0.0
        lat = coords[1] if isinstance(coords, (list, tuple)) and len(coords) > 1 else 0.0
        key = (round(lat, 1), round(lon, 1))
        grid_keys.append(key)
        if key not in grid_cache:
            grid_cache[key] = None  # placeholder — will be filled below

    # Fetch unique grid cells in parallel
    unique_keys = [k for k, v in grid_cache.items() if v is None]
    logger.info(f"Weather: fetching {len(unique_keys)} unique grid cells for {len(features)} alerts")

    def _fetch(key):
        return key, fetch_weather(key[0], key[1])

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_fetch, k): k for k in unique_keys}
        for future in as_completed(futures):
            try:
                key, weather = future.result()
                grid_cache[key] = weather
            except Exception as e:
                k = futures[future]
                logger.warning(f"Weather thread error for {k}: {e}")
                grid_cache[k] = dict(FALLBACK_WEATHER)

    # --- Attach weather + smoke vector to each feature ---
    enriched_features = []
    for feat, key in zip(features, grid_keys):
        weather = grid_cache.get(key, dict(FALLBACK_WEATHER))
        coords = feat.get("geometry", {}).get("coordinates", [0, 0])
        lon, lat = coords[0], coords[1]

        smoke = compute_smoke_vector(
            origin_lat=lat,
            origin_lon=lon,
            wind_speed_kmh=weather["wind_speed_10m"],
            wind_direction_deg=weather["wind_direction_10m"],
        )

        enriched_feat = dict(feat)
        enriched_props = dict(enriched_feat.get("properties", {}))
        enriched_props["weather"] = weather
        enriched_props["smoke_vector"] = smoke
        enriched_feat["properties"] = enriched_props
        enriched_features.append(enriched_feat)

    result = dict(alerts_geojson)
    result["features"] = enriched_features
    logger.info(f"Weather enrichment complete for {len(enriched_features)} alerts")
    return result
