"""
main.py — PyroGuard AI FastAPI Backend
NASA FIRMS + OSM Industrial Fire Detection System
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from firms_fetcher import get_firms_geojson
from osm_fetcher import get_osm_geojson
from classifier import classify_thermal_points, CLASS_ALERT, CLASS_ROUTINE, CLASS_NATURAL
from baseline_engine import compute_baselines
from weather_service import enrich_alerts

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("pyroguard")

# ── In-memory cache ───────────────────────────────────────────────────────────
_cache: dict = {
    "classified_geojson": None,
    "facilities_geojson": None,   # persistent heat source clusters
    "alerts_geojson": None,       # weather-enriched critical alerts
    "stats": None,
}


def run_pipeline(force_refresh: bool = False) -> dict:
    """Run the full FIRMS → OSM → classify → baseline → weather pipeline."""
    logger.info(f"Running pipeline (force_refresh={force_refresh})")

    # Step 1: Ingest data
    firms_data = get_firms_geojson(force_refresh=force_refresh)
    osm_data = get_osm_geojson(force_refresh=force_refresh)

    # Step 2: Classify thermal points
    classified = classify_thermal_points(firms_data, osm_data)
    _cache["classified_geojson"] = classified

    # Step 3: Baseline engine — cluster persistent industrial sources
    facilities = compute_baselines(classified)
    _cache["facilities_geojson"] = facilities

    # Step 4: Extract alert features and enrich with weather + smoke vectors
    alert_features = [
        f for f in classified.get("features", [])
        if f.get("properties", {}).get("classification") == CLASS_ALERT
    ]
    alerts_geojson = {"type": "FeatureCollection", "features": alert_features}
    enriched_alerts = enrich_alerts(alerts_geojson)

    # Step 5: Reshape into frontend-compatible property schemas
    _cache["alerts_geojson"] = _reshape_alerts(enriched_alerts)
    _cache["facilities_geojson"] = _reshape_facilities(facilities)

    # Step 5: Build expanded stats
    meta = classified.get("metadata", {})
    facilities_meta = facilities.get("metadata", {})
    all_frps = [
        f.get("properties", {}).get("frp", 0.0)
        for f in classified.get("features", [])
    ]
    avg_frp = round(sum(all_frps) / len(all_frps), 2) if all_frps else 0.0

    _cache["stats"] = {
        "total_scanned": meta.get("total_points", 0),
        "alert_count": meta.get("alert_count", 0),
        "routine_count": meta.get("routine_count", 0),
        "natural_count": meta.get("natural_count", 0),
        "industrial_zone_count": meta.get("industrial_zone_count", 0),
        "persistent_sources": facilities_meta.get("persistent_count", 0),
        "active_emergencies": len(alert_features),
        "cluster_count": facilities_meta.get("cluster_count", 0),
        "average_frp": avg_frp,
    }

    logger.info("Pipeline complete. Cache updated.")
    return classified


# ── Frontend payload reshaping ────────────────────────────────────────────────

def _reshape_alerts(enriched_geojson: dict) -> dict:
    """Reshape enriched alert features to the strict frontend property contract.

    Frontend expects per-feature properties:
        id, category, frp, facility_name, wind_speed, smoke_bearing
    """
    features = []
    for i, feat in enumerate(enriched_geojson.get("features", [])):
        props = feat.get("properties", {})
        weather = props.get("weather", {})
        smoke = props.get("smoke_vector", {})
        features.append({
            "type": "Feature",
            "geometry": feat.get("geometry"),
            "properties": {
                "id": i + 1,
                "category": "Industrial Fire Alert",
                "frp": float(props.get("frp", 0.0)),
                "facility_name": props.get("zone_name") or None,
                "wind_speed": float(weather.get("wind_speed_10m", 5.0)),
                "wind_direction": float(weather.get("wind_direction_10m", 0)),
                "temperature": float(weather.get("temperature_2m", 30.0)),
                "humidity": float(weather.get("relative_humidity_2m", 50)),
                "smoke_bearing": float(smoke.get("bearing_deg", 0.0)),
                "smoke_distance_km": float(smoke.get("distance_km", 0.0)),
                "smoke_end_lat": smoke.get("end_lat"),
                "smoke_end_lon": smoke.get("end_lon"),
                # Preserve full nested objects for advanced frontend usage
                "weather": weather,
                "smoke_vector": smoke,
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _reshape_facilities(facilities_geojson: dict) -> dict:
    """Reshape baseline cluster features to the strict frontend property contract.

    Frontend expects per-feature properties:
        category, frp_baseline, frequency_count, facility_name
    """
    features = []
    for feat in facilities_geojson.get("features", []):
        props = feat.get("properties", {})
        features.append({
            "type": "Feature",
            "geometry": feat.get("geometry"),
            "properties": {
                "cluster_id": props.get("cluster_id"),
                "category": "Routine Operational Heat",
                "frp_baseline": float(props.get("baseline_frp_mean", 0.0)),
                "frp_std": float(props.get("baseline_frp_std", 0.0)),
                "frequency_count": int(props.get("frequency_count", 0)),
                "facility_name": props.get("zone_name") or None,
                "osm_id": props.get("osm_id"),
                "industrial_type": props.get("industrial_type"),
                "max_temp_k": props.get("max_temp_k"),
                "is_persistent": props.get("is_persistent", False),
                "source_type": props.get("source_type"),
            },
        })
    metadata = facilities_geojson.get("metadata", {})
    return {"type": "FeatureCollection", "features": features, "metadata": metadata}


# ── Lifespan: warm up pipeline on startup ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PyroGuard AI starting up — warming pipeline...")
    try:
        run_pipeline()
    except Exception as e:
        logger.error(f"Startup pipeline error: {e}")
    yield
    logger.info("PyroGuard AI shutting down.")


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="PyroGuard AI — Industrial Fire Detection API",
    description=(
        "Ingests NASA FIRMS thermal anomaly data, cross-references with "
        "OpenStreetMap industrial boundaries, classifies heat points, "
        "clusters persistent sources, and enriches alerts with weather data."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: allow Vite frontend on port 3000 and any localhost variant
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _ensure_pipeline():
    """Run pipeline if cache is cold. Returns True on success."""
    if any(_cache.get(k) is None for k in ("classified_geojson", "facilities_geojson", "alerts_geojson", "stats")):
        try:
            run_pipeline()
        except Exception as e:
            logger.error(f"Pipeline error on demand: {e}")
            raise HTTPException(status_code=503, detail="Classification pipeline unavailable")
    return True

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    """Health check and API info."""
    return {
        "service": "PyroGuard AI",
        "status": "operational",
        "version": "2.0.0",
        "endpoints": {
            "thermal_points": "/api/v1/thermal-points",
            "facilities": "/api/v1/facilities",
            "alerts": "/api/v1/alerts",
            "stats": "/api/v1/stats",
            "refresh": "POST /api/v1/refresh",
            "docs": "/docs",
        },
    }


@app.get("/api/v1/thermal-points", tags=["Data"])
def get_thermal_points():
    """
    Returns classified thermal anomaly points as a GeoJSON FeatureCollection.

    Each feature has properties:
    - frp: Fire Radiative Power (MW)
    - brightness: brightness temperature (K)
    - acq_date, acq_time: acquisition datetime
    - satellite: satellite identifier
    - confidence: detection confidence
    - classification: one of 'Industrial Fire Alert', 'Routine Operational Heat', 'Natural/Wildfire'
    - color: hex color for frontend rendering
    - zone_name: name of industrial zone if inside one (else null)
    - osm_id: OSM identifier of matched industrial polygon (else null)
    - industrial_type: type of industrial facility (else null)
    - frp_zone_mean: mean FRP of the zone for context (else null)
    - inside_industrial: boolean
    """
    _ensure_pipeline()
    return JSONResponse(content=_cache["classified_geojson"])


@app.get("/api/v1/facilities", tags=["Data"])
def get_facilities():
    """
    Returns GeoJSON of identified persistent industrial heat source clusters.

    Each feature has properties:
    - category: "Routine Operational Heat"
    - frp_baseline: rolling mean FRP (MW)
    - frequency_count: total detections in cluster
    - facility_name: matched OSM facility name (or null)
    - cluster_id, osm_id, industrial_type, max_temp_k
    - is_persistent, source_type
    """
    _ensure_pipeline()
    return JSONResponse(content=_cache["facilities_geojson"])


@app.get("/api/v1/alerts", tags=["Data"])
def get_alerts():
    """
    Returns currently active critical fire anomalies enriched with weather.

    Each feature has properties:
    - id: sequential integer
    - category: "Industrial Fire Alert"
    - frp: Fire Radiative Power (MW)
    - facility_name: matched OSM facility name (or null)
    - wind_speed: current wind speed (km/h)
    - smoke_bearing: projected smoke plume bearing (degrees from north)
    - weather: full weather object
    - smoke_vector: full dispersion vector object
    """
    _ensure_pipeline()
    return JSONResponse(content=_cache["alerts_geojson"])


@app.get("/api/v1/stats", tags=["Data"])
def get_stats():
    """
    Returns aggregated summary statistics.
    """
    _ensure_pipeline()
    return {
        "status": "ok",
        "data": _cache["stats"],
        "classifications": {
            "alert": CLASS_ALERT,
            "routine": CLASS_ROUTINE,
            "natural": CLASS_NATURAL,
        },
        "colors": {
            CLASS_ALERT: "#dc2626",
            CLASS_ROUTINE: "#f59e0b",
            CLASS_NATURAL: "#10b981",
        },
    }


@app.post("/api/v1/refresh", tags=["Control"])
def refresh_data(background_tasks: BackgroundTasks):
    """
    Force re-fetch of FIRMS and OSM data, re-run classification.
    Runs in background so the response is immediate.
    """
    background_tasks.add_task(run_pipeline, force_refresh=True)
    return {"status": "refresh_queued", "message": "Data refresh started in background."}
