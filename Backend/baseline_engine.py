"""
baseline_engine.py
Spatial clustering of thermal detections using DBSCAN to identify
persistent industrial heat sources (flare stacks, kilns, etc.).

Produces a GeoJSON FeatureCollection of cluster centroids with
baseline FRP statistics.
"""

import logging
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

# DBSCAN parameters
# eps ≈ 0.0036° ≈ 400 m at Indian latitudes (~22–28° N)
DBSCAN_EPS_DEG = 0.0036
DBSCAN_MIN_SAMPLES = 2

# A cluster is "persistent" if it has enough points and low FRP variance
PERSISTENT_MIN_COUNT = 3
PERSISTENT_MAX_CV = 0.5  # coefficient of variation (std / mean)


def _extract_industrial_points(classified_geojson: dict) -> pd.DataFrame:
    """Pull lat/lon/frp/brightness/zone info from classified GeoJSON features
    that are inside industrial zones (both Alerts and Routine)."""
    rows = []
    for feat in classified_geojson.get("features", []):
        props = feat.get("properties", {})
        if not props.get("inside_industrial", False):
            continue
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        rows.append({
            "longitude": coords[0],
            "latitude": coords[1],
            "frp": float(props.get("frp", 0.0)),
            "brightness": float(props.get("brightness", 0.0)),
            "zone_name": props.get("zone_name"),
            "osm_id": props.get("osm_id"),
            "industrial_type": props.get("industrial_type"),
            "classification": props.get("classification"),
        })
    return pd.DataFrame(rows)


def compute_baselines(classified_geojson: dict) -> dict:
    """
    Cluster industrial thermal detections with DBSCAN and compute
    per-cluster baseline statistics.

    Args:
        classified_geojson: The output of classify_thermal_points().

    Returns:
        GeoJSON FeatureCollection of cluster centroid Points, each with:
          - cluster_id, centroid_lat, centroid_lon
          - frequency_count, baseline_frp_mean, baseline_frp_std
          - max_temp_k, zone_name, osm_id, industrial_type
          - is_persistent, source_type
    """
    df = _extract_industrial_points(classified_geojson)

    if df.empty:
        logger.warning("No industrial points for baseline computation")
        return {"type": "FeatureCollection", "features": [], "metadata": {"cluster_count": 0, "persistent_count": 0}}

    # --- DBSCAN clustering on (lat, lon) ---
    coords = df[["latitude", "longitude"]].values
    clustering = DBSCAN(eps=DBSCAN_EPS_DEG, min_samples=DBSCAN_MIN_SAMPLES, metric="euclidean")
    df["cluster_label"] = clustering.fit_predict(coords)

    # Drop noise points (label == -1)
    clustered = df[df["cluster_label"] >= 0].copy()

    if clustered.empty:
        logger.info("DBSCAN found no clusters (all points are noise)")
        return {"type": "FeatureCollection", "features": [], "metadata": {"cluster_count": 0, "persistent_count": 0}}

    # --- Aggregate per cluster ---
    agg = clustered.groupby("cluster_label").agg(
        centroid_lat=("latitude", "mean"),
        centroid_lon=("longitude", "mean"),
        frequency_count=("frp", "size"),
        baseline_frp_mean=("frp", "mean"),
        baseline_frp_std=("frp", "std"),
        max_temp_k=("brightness", "max"),
        zone_name=("zone_name", lambda s: s.mode().iloc[0] if len(s.mode()) > 0 else s.iloc[0]),
        osm_id=("osm_id", "first"),
        industrial_type=("industrial_type", "first"),
    ).reset_index()

    # std is NaN for single-element groups (shouldn't happen with min_samples=2, but guard)
    agg["baseline_frp_std"] = agg["baseline_frp_std"].fillna(0.0)

    # Persistence classification
    agg["cv"] = np.where(
        agg["baseline_frp_mean"] > 0,
        agg["baseline_frp_std"] / agg["baseline_frp_mean"],
        0.0,
    )
    agg["is_persistent"] = (
        (agg["frequency_count"] >= PERSISTENT_MIN_COUNT)
        & (agg["cv"] < PERSISTENT_MAX_CV)
    )
    agg["source_type"] = np.where(
        agg["is_persistent"],
        "Verified Persistent Industrial Source",
        "Transient Heat Source",
    )

    # --- Build GeoJSON ---
    features = []
    for _, row in agg.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(row["centroid_lon"], 6), round(row["centroid_lat"], 6)],
            },
            "properties": {
                "cluster_id": int(row["cluster_label"]),
                "centroid_lat": round(row["centroid_lat"], 6),
                "centroid_lon": round(row["centroid_lon"], 6),
                "frequency_count": int(row["frequency_count"]),
                "baseline_frp_mean": round(float(row["baseline_frp_mean"]), 2),
                "baseline_frp_std": round(float(row["baseline_frp_std"]), 2),
                "max_temp_k": round(float(row["max_temp_k"]), 1),
                "zone_name": row["zone_name"],
                "osm_id": row["osm_id"],
                "industrial_type": row["industrial_type"],
                "is_persistent": bool(row["is_persistent"]),
                "source_type": row["source_type"],
            },
        })

    persistent_count = int(agg["is_persistent"].sum())
    logger.info(
        f"Baseline engine: {len(features)} clusters found, "
        f"{persistent_count} verified persistent sources"
    )

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "cluster_count": len(features),
            "persistent_count": persistent_count,
        },
    }
