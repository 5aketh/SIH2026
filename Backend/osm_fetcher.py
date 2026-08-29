"""
osm_fetcher.py
Queries the OpenStreetMap Overpass API for industrial land-use polygons
within a bounding box, converts to GeoJSON, and caches locally.
"""

import json
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Same bounding box as FIRMS: south, west, north, east (Overpass format)
BBOX_OVERPASS = "5.0,60.0,40.0,100.0"

OVERPASS_QUERY = f"""
[out:json][timeout:60];
(
  way["landuse"="industrial"]({BBOX_OVERPASS});
  relation["landuse"="industrial"]({BBOX_OVERPASS});
  way["industrial"~"^(factory|plant|oil_terminal|refinery|chemical|steel|power|warehouse)$"]({BBOX_OVERPASS});
  way["amenity"="industrial"]({BBOX_OVERPASS});
);
out body;
>;
out skel qt;
"""

import os
DATA_DIR = Path(os.environ.get("PYROGUARD_DATA_DIR", str(Path(__file__).parent / "data")))
OUTPUT_PATH = DATA_DIR / "osm_industrial.geojson"
CACHE_MAX_AGE_SECONDS = 86400  # 24 hours (OSM data changes slowly)


def is_cache_fresh() -> bool:
    if not OUTPUT_PATH.exists():
        return False
    age = datetime.now(timezone.utc).timestamp() - OUTPUT_PATH.stat().st_mtime
    return age < CACHE_MAX_AGE_SECONDS


def fetch_overpass() -> dict | None:
    logger.info("Querying Overpass API for industrial polygons...")
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": OVERPASS_QUERY},
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Overpass: received {len(data.get('elements', []))} elements")
        return data
    except Exception as e:
        logger.error(f"Overpass fetch failed: {e}. Using mock industrial zones.")
        return None


def overpass_to_geojson(overpass_data: dict) -> dict:
    """
    Convert Overpass JSON (nodes + ways) to GeoJSON Polygon FeatureCollection.
    Builds polygons from way node references.
    """
    if not overpass_data:
        return generate_mock_osm_data()

    elements = overpass_data.get("elements", [])
    # Build node lookup: id -> (lon, lat)
    nodes = {
        e["id"]: (e["lon"], e["lat"])
        for e in elements
        if e["type"] == "node" and "lon" in e and "lat" in e
    }

    features = []
    for elem in elements:
        if elem["type"] != "way":
            continue
        node_refs = elem.get("nodes", [])
        coords = [nodes[n] for n in node_refs if n in nodes]
        if len(coords) < 4:
            continue
        # Close the ring if not closed
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        tags = elem.get("tags", {})
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "osm_id": elem["id"],
                "name": tags.get("name", "Industrial Zone"),
                "landuse": tags.get("landuse", "industrial"),
                "industrial": tags.get("industrial", ""),
            },
        })

    logger.info(f"OSM: converted {len(features)} industrial polygons")

    if len(features) < 10:
        # Too few real polygons — supplement with mock data
        logger.info("OSM: supplementing with mock industrial zones")
        mock = generate_mock_osm_data()
        features.extend(mock["features"])

    return {"type": "FeatureCollection", "features": features}


def generate_mock_osm_data() -> dict:
    """
    Generate mock industrial polygon GeoJSON for Indian industrial zones.
    These are approximate bounding boxes of real industrial areas.
    """
    zones = [
        # (center_lat, center_lon, radius_deg, name)
        (22.80, 86.18, 0.08, "Jamshedpur Steel Plant Complex"),
        (22.30, 73.15, 0.06, "Vadodara GIDC Petrochemical"),
        (21.17, 72.83, 0.05, "Surat Industrial Estate"),
        (28.67, 77.42, 0.07, "Delhi Okhla Industrial Area"),
        (19.08, 72.88, 0.06, "Mumbai Thane Industrial Belt"),
        (13.00, 77.57, 0.05, "Bangalore Industrial Area"),
        (17.37, 78.48, 0.06, "Hyderabad Patancheru Industrial"),
        (22.57, 88.36, 0.07, "Kolkata Industrial Belt"),
        (26.85, 80.95, 0.05, "Kanpur Industrial Area"),
        (18.52, 73.85, 0.06, "Pune Pimpri Industrial"),
        (20.46, 85.88, 0.05, "Bhubaneswar Industrial"),
        (23.03, 72.55, 0.07, "Ahmedabad GIDC Industrial"),
        (11.00, 76.97, 0.05, "Coimbatore Textile Industrial"),
        (28.45, 77.03, 0.06, "Gurgaon Auto Industrial"),
        (25.60, 85.10, 0.04, "Hajipur Industrial Area"),
    ]

    features = []
    for lat, lon, r, name in zones:
        # Create approximate rectangular polygon
        coords = [
            [lon - r, lat - r * 0.6],
            [lon + r, lat - r * 0.6],
            [lon + r, lat + r * 0.6],
            [lon - r, lat + r * 0.6],
            [lon - r, lat - r * 0.6],  # close ring
        ]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "osm_id": f"mock_{name.replace(' ', '_')}",
                "name": name,
                "landuse": "industrial",
                "industrial": "factory",
            },
        })

    logger.info(f"OSM Mock: generated {len(features)} industrial zone polygons")
    return {"type": "FeatureCollection", "features": features}


def get_osm_geojson(force_refresh: bool = False) -> dict:
    """
    Return OSM industrial polygons as GeoJSON. Uses cache if fresh.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh and is_cache_fresh():
        logger.info("OSM: loading industrial polygons from cache")
        with open(OUTPUT_PATH, "r") as f:
            return json.load(f)

    raw = fetch_overpass()
    geojson = overpass_to_geojson(raw)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(geojson, f)

    logger.info(f"OSM: saved {len(geojson['features'])} polygons to {OUTPUT_PATH}")
    return geojson
