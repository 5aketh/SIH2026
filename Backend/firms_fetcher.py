"""
firms_fetcher.py
Downloads NASA FIRMS thermal anomaly data (MODIS/VIIRS) for the last 24h,
converts to GeoJSON, and caches locally.
"""

import os
import json
import logging
import requests
import pandas as pd
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# NASA FIRMS API configuration
# Get a free key at: https://firms.modaps.eosdis.nasa.gov/api/area/
# If not set (or set to the literal string "DEMO_KEY" / empty), the fetcher
# will skip the live API call and use local cached / mock data instead.
FIRMS_API_KEY = os.environ.get("FIRMS_API_KEY", "").strip()

# Bounding box: India + surrounding industrial regions (lon_min, lat_min, lon_max, lat_max)
# Format for FIRMS: west,south,east,north
BBOX = "60.0,5.0,100.0,40.0"

# VIIRS S-NPP — 375m resolution, best for industrial heat detection
FIRMS_URL = (
    f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_API_KEY}"
    f"/VIIRS_SNPP_NRT/{BBOX}/1"  # 1 day
)

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_PATH = DATA_DIR / "firms_points.geojson"
CACHE_MAX_AGE_SECONDS = 1800  # 30 minutes


def is_cache_fresh() -> bool:
    """Check if cached file exists and is less than 30 minutes old."""
    if not OUTPUT_PATH.exists():
        return False
    age = datetime.now(timezone.utc).timestamp() - OUTPUT_PATH.stat().st_mtime
    return age < CACHE_MAX_AGE_SECONDS


def fetch_firms_csv() -> pd.DataFrame:
    """Download FIRMS CSV from NASA API and return as DataFrame.
    
    Returns mock data immediately (with an INFO log) when no valid API key
    is configured, so the server stays operational without credentials.
    """
    # --- Guard: no API key available ---
    if not FIRMS_API_KEY or FIRMS_API_KEY.upper() in ("DEMO_KEY", "NONE", ""):
        logger.info(
            "No API key found. Defaulting to local cache. "
            "Set FIRMS_API_KEY env variable to enable live data."
        )
        return generate_mock_firms_data()

    logger.info(f"Fetching FIRMS data from NASA API (bbox={BBOX})")
    try:
        resp = requests.get(FIRMS_URL, timeout=30)
        resp.raise_for_status()
        content = resp.text.strip()
        if not content or content.startswith("Error") or "DOCTYPE" in content:
            logger.warning("FIRMS API returned invalid data; using fallback mock data")
            return generate_mock_firms_data()
        df = pd.read_csv(StringIO(content))
        logger.info(f"FIRMS: downloaded {len(df)} thermal points")
        return df
    except Exception as e:
        logger.error(f"FIRMS fetch failed: {e}. Using mock data.")
        return generate_mock_firms_data()


def generate_mock_firms_data() -> pd.DataFrame:
    """
    Generate realistic mock FIRMS data for India when the API is unavailable.
    Includes known industrial zones (Jamshedpur steel belt, Gujarat petrochemical,
    Delhi NCR, Mumbai industrial corridor) plus natural fire points.
    """
    import numpy as np
    rng = np.random.default_rng(42)

    records = []
    now = datetime.now(timezone.utc)

    # Industrial zone clusters (real Indian industrial areas)
    industrial_clusters = [
        # (lat, lon, name, frp_mean, count)
        (22.80, 86.18, "Jamshedpur Steel Belt", 45.0, 12),
        (22.30, 73.15, "Vadodara Petrochemical", 28.0, 8),
        (21.17, 72.83, "Surat Industrial Zone", 18.0, 6),
        (28.67, 77.42, "Delhi NCR Industrial", 15.0, 10),
        (19.08, 72.88, "Mumbai Thane Industrial", 22.0, 7),
        (13.00, 77.57, "Bangalore Electronic City", 12.0, 5),
        (17.37, 78.48, "Hyderabad Pharma Zone", 20.0, 6),
        (22.57, 88.36, "Kolkata Industrial Belt", 30.0, 9),
        (26.85, 80.95, "Kanpur Industrial", 25.0, 7),
        (18.52, 73.85, "Pune Auto Industrial", 16.0, 5),
    ]

    # Fire alert cluster (simulates an active fire in an industrial zone)
    alert_clusters = [
        (22.81, 86.20, "Jamshedpur ALERT", 180.0, 3),
        (21.19, 72.84, "Surat ALERT", 145.0, 2),
    ]

    # Natural fire clusters (forests, agricultural burning)
    natural_clusters = [
        (24.0, 82.0, "Madhya Pradesh Forest", 8.0, 15),
        (15.0, 76.0, "Karnataka Scrubland", 5.0, 10),
        (25.5, 85.0, "Bihar Agricultural Burn", 6.0, 12),
        (20.0, 84.0, "Odisha Forest", 9.0, 8),
        (30.5, 78.0, "Uttarakhand Forest", 12.0, 6),
    ]

    for lat_c, lon_c, name, frp_mean, count in industrial_clusters + alert_clusters:
        for _ in range(count):
            frp = max(1.0, rng.normal(frp_mean, frp_mean * 0.15))
            records.append({
                "latitude": lat_c + rng.uniform(-0.05, 0.05),
                "longitude": lon_c + rng.uniform(-0.05, 0.05),
                "bright_ti4": 300 + frp * 0.5 + rng.normal(0, 5),
                "bright_ti5": 290 + frp * 0.3,
                "frp": round(frp, 2),
                "acq_date": now.strftime("%Y-%m-%d"),
                "acq_time": now.strftime("%H%M"),
                "satellite": "N",
                "confidence": rng.choice(["nominal", "high"]),
                "version": "2.0NRT",
                "daynight": "D",
            })

    for lat_c, lon_c, name, frp_mean, count in natural_clusters:
        for _ in range(count):
            frp = max(0.5, rng.normal(frp_mean, 2.0))
            records.append({
                "latitude": lat_c + rng.uniform(-0.3, 0.3),
                "longitude": lon_c + rng.uniform(-0.3, 0.3),
                "bright_ti4": 290 + frp * 0.4,
                "bright_ti5": 285 + frp * 0.2,
                "frp": round(frp, 2),
                "acq_date": now.strftime("%Y-%m-%d"),
                "acq_time": now.strftime("%H%M"),
                "satellite": "N",
                "confidence": "nominal",
                "version": "2.0NRT",
                "daynight": "D",
            })

    df = pd.DataFrame(records)
    logger.info(f"Mock FIRMS: generated {len(df)} synthetic thermal points")
    return df


def df_to_geojson(df: pd.DataFrame) -> dict:
    """Convert a FIRMS DataFrame to a GeoJSON FeatureCollection."""
    features = []
    required = {"latitude", "longitude"}
    if not required.issubset(df.columns):
        logger.error("FIRMS DataFrame missing required lat/lon columns")
        return {"type": "FeatureCollection", "features": []}

    for _, row in df.iterrows():
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (ValueError, TypeError):
            continue

        props = {k: (None if pd.isna(v) else v) for k, v in row.items()
                 if k not in ("latitude", "longitude")}
        # Ensure FRP is always present as a float
        props["frp"] = float(props.get("frp", 0.0) or 0.0)

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features}


def get_firms_geojson(force_refresh: bool = False) -> dict:
    """
    Return FIRMS data as GeoJSON. Uses cache if fresh, otherwise re-fetches.

    When no FIRMS_API_KEY is configured the function:
      1. Returns the existing on-disk cache if it exists (any age).
      2. Falls back to synthetic mock data if no cache file is present.
    This ensures the server never crashes due to a missing API key.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    no_key = not FIRMS_API_KEY or FIRMS_API_KEY.upper() in ("DEMO_KEY", "NONE", "")

    if not force_refresh and is_cache_fresh():
        logger.info("FIRMS: loading from cache")
        with open(OUTPUT_PATH, "r") as f:
            return json.load(f)

    # If there is no API key and a (possibly stale) cache exists, reuse it.
    if no_key and OUTPUT_PATH.exists():
        logger.info(
            "No API key found. Defaulting to local cache "
            f"({OUTPUT_PATH.name})."
        )
        with open(OUTPUT_PATH, "r") as f:
            return json.load(f)

    df = fetch_firms_csv()  # returns mock data when key is absent
    geojson = df_to_geojson(df)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(geojson, f)

    logger.info(f"FIRMS: saved {len(geojson['features'])} features to {OUTPUT_PATH}")
    return geojson
