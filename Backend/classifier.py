"""
classifier.py
Spatial join of NASA FIRMS thermal points against OSM industrial polygons.
Classifies each point as:
  - "Industrial Fire Alert"     (inside industrial zone, FRP spike > 3x baseline)
  - "Routine Operational Heat"  (inside industrial zone, steady FRP)
  - "Natural/Wildfire"          (outside industrial zones)
"""

import logging
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape, Point
from shapely.ops import unary_union

logger = logging.getLogger(__name__)

# Classification thresholds
BUFFER_METERS = 200          # Buffer around industrial polygons
FRP_SPIKE_MULTIPLIER = 3.0   # FRP > 3x zone mean = Alert
FRP_ALERT_ABSOLUTE = 50.0    # Always alert if FRP > 50 MW inside industrial zone
FRP_MIN_OPERATIONAL = 5.0    # Minimum FRP to be considered operational heat

# Classification labels
CLASS_ALERT = "Industrial Fire Alert"
CLASS_ROUTINE = "Routine Operational Heat"
CLASS_NATURAL = "Natural/Wildfire"

# Color codes (returned in payload for frontend consumption)
CLASS_COLORS = {
    CLASS_ALERT: "#dc2626",    # stark red
    CLASS_ROUTINE: "#f59e0b",  # amber
    CLASS_NATURAL: "#10b981",  # emerald
}


def geojson_to_gdf(geojson: dict, crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Convert a GeoJSON FeatureCollection to a GeoDataFrame."""
    if not geojson or not geojson.get("features"):
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    geometries = []
    properties = []
    for feat in geojson["features"]:
        try:
            geom = shape(feat["geometry"])
            geometries.append(geom)
            properties.append(feat.get("properties", {}))
        except Exception as e:
            logger.debug(f"Skipping malformed feature: {e}")
            continue

    gdf = gpd.GeoDataFrame(properties, geometry=geometries, crs=crs)
    return gdf


def classify_thermal_points(firms_geojson: dict, osm_geojson: dict) -> dict:
    """
    Main classification pipeline.

    Args:
        firms_geojson: FIRMS thermal points as GeoJSON FeatureCollection
        osm_geojson:   OSM industrial polygons as GeoJSON FeatureCollection

    Returns:
        Classified GeoJSON FeatureCollection with added properties:
          - classification: str
          - color: str (hex)
          - frp: float
          - zone_name: str or None
          - frp_zone_mean: float or None
    """
    logger.info("Starting classification pipeline...")

    # --- Load into GeoDataFrames ---
    firms_gdf = geojson_to_gdf(firms_geojson)
    osm_gdf = geojson_to_gdf(osm_geojson)

    if firms_gdf.empty:
        logger.warning("No FIRMS points to classify")
        return {"type": "FeatureCollection", "features": [], "metadata": {}}

    # Ensure FRP column
    if "frp" not in firms_gdf.columns:
        firms_gdf["frp"] = 0.0
    firms_gdf["frp"] = pd.to_numeric(firms_gdf["frp"], errors="coerce").fillna(0.0)

    # --- Project to UTM (meters) for buffering ---
    # Use EPSG:32644 (UTM zone 44N — covers most of India)
    utm_crs = "EPSG:32644"
    firms_utm = firms_gdf.to_crs(utm_crs)

    # Initialize output columns
    firms_gdf["classification"] = CLASS_NATURAL
    firms_gdf["color"] = CLASS_COLORS[CLASS_NATURAL]
    firms_gdf["zone_name"] = None
    firms_gdf["osm_id"] = None
    firms_gdf["industrial_type"] = None
    firms_gdf["frp_zone_mean"] = None
    firms_gdf["inside_industrial"] = False

    if not osm_gdf.empty:
        osm_utm = osm_gdf.to_crs(utm_crs)

        # Buffer industrial polygons by BUFFER_METERS
        osm_buffered = osm_utm.copy()
        osm_buffered["geometry"] = osm_utm.geometry.buffer(BUFFER_METERS)

        # Spatial join: find which FIRMS points fall inside buffered industrial zones
        # Carry osm_id, name, and industrial columns for facility-level tagging
        join_cols = ["geometry"]
        for c in ("name", "osm_id", "industrial"):
            if c in osm_buffered.columns:
                join_cols.append(c)
        try:
            joined = gpd.sjoin(
                firms_utm,
                osm_buffered[join_cols],
                how="left",
                predicate="within",
            )
            # Determine zone name column (geopandas may suffix with _right if collision)
            zone_col = "name_right" if "name_right" in joined.columns else "name"
            osm_id_col = "osm_id_right" if "osm_id_right" in joined.columns else "osm_id"
            ind_type_col = "industrial_right" if "industrial_right" in joined.columns else "industrial"
        except Exception as e:
            logger.error(f"Spatial join failed: {e}")
            joined = firms_utm.copy()
            zone_col = "name"
            joined[zone_col] = None
            joined["index_right"] = None

        # Identify industrial points
        in_zone_mask = joined["index_right"].notna()
        firms_gdf.loc[in_zone_mask.values, "inside_industrial"] = True

        # Assign zone names (take first match if multiple)
        zone_names = joined.groupby(joined.index)[zone_col].first()
        firms_gdf["zone_name"] = zone_names.reindex(firms_gdf.index).values

        # Assign osm_id and industrial_type from the join
        if osm_id_col in joined.columns:
            osm_ids = joined.groupby(joined.index)[osm_id_col].first()
            firms_gdf["osm_id"] = osm_ids.reindex(firms_gdf.index).values
        if ind_type_col in joined.columns:
            ind_types = joined.groupby(joined.index)[ind_type_col].first()
            firms_gdf["industrial_type"] = ind_types.reindex(firms_gdf.index).values


        logger.info(
            f"Classification: {in_zone_mask.sum()} points inside industrial zones "
            f"out of {len(firms_gdf)} total"
        )

        # --- FRP Spike Detection per Zone ---
        # For each industrial zone, compute mean FRP of all points inside it.
        # Points with FRP > 3x mean (or > absolute threshold) become alerts.
        industrial_mask = firms_gdf["inside_industrial"]

        if industrial_mask.any():
            industrial_pts = firms_gdf[industrial_mask].copy()

            # Drop any pre-existing frp_zone_mean column to avoid merge conflicts
            # on repeated pipeline runs (firms_gdf initialises it to None above).
            if "frp_zone_mean" in industrial_pts.columns:
                industrial_pts = industrial_pts.drop(columns=["frp_zone_mean"])

            # Compute per-zone mean FRP using transform so no join/merge is needed
            # (avoids 'columns overlap but no suffix specified' on repeated calls).
            industrial_pts["frp_zone_mean"] = industrial_pts.groupby(
                "zone_name"
            )["frp"].transform("mean")

            # Classification rules
            def classify_point(row):
                frp = row["frp"]
                mean_frp = row.get("frp_zone_mean", frp)
                if mean_frp is None or pd.isna(mean_frp):
                    mean_frp = frp

                # Rule 1: Absolute FRP spike
                if frp >= FRP_ALERT_ABSOLUTE:
                    return CLASS_ALERT
                # Rule 2: Relative FRP spike (>3x zone mean)
                if mean_frp > 0 and frp > FRP_SPIKE_MULTIPLIER * mean_frp:
                    return CLASS_ALERT
                # Rule 3: No historical baseline (lone point, no history)
                if frp > FRP_ALERT_ABSOLUTE * 0.6:  # > 30 MW alone
                    return CLASS_ALERT
                # Rule 4: Operational heat
                if frp >= FRP_MIN_OPERATIONAL:
                    return CLASS_ROUTINE
                # Rule 5: Very low FRP inside zone — still routine
                return CLASS_ROUTINE

            industrial_pts["classification"] = industrial_pts.apply(classify_point, axis=1)
            industrial_pts["color"] = industrial_pts["classification"].map(CLASS_COLORS)

            # Write back to main dataframe
            firms_gdf.loc[industrial_mask, "classification"] = industrial_pts["classification"].values
            firms_gdf.loc[industrial_mask, "color"] = industrial_pts["color"].values
            firms_gdf.loc[industrial_mask, "frp_zone_mean"] = industrial_pts["frp_zone_mean"].values

    # --- Build output GeoJSON ---
    features = []
    for idx, row in firms_gdf.iterrows():
        geom = row.geometry
        if geom is None or not geom.is_valid:
            continue

        props = {
            "frp": round(float(row.get("frp", 0)), 2),
            "brightness": round(float(row.get("bright_ti4", 0) or 0), 1),
            "acq_date": str(row.get("acq_date", "")),
            "acq_time": str(row.get("acq_time", "")),
            "satellite": str(row.get("satellite", "N")),
            "confidence": str(row.get("confidence", "nominal")),
            "classification": row["classification"],
            "color": row["color"],
            "zone_name": row.get("zone_name"),
            "frp_zone_mean": (
                round(float(row["frp_zone_mean"]), 2)
                if row.get("frp_zone_mean") is not None and not pd.isna(row.get("frp_zone_mean", float("nan")))
                else None
            ),
            "inside_industrial": bool(row["inside_industrial"]),
            "osm_id": row.get("osm_id"),
            "industrial_type": row.get("industrial_type"),
        }

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [geom.x, geom.y],
            },
            "properties": props,
        })

    # Summary stats
    class_counts = firms_gdf["classification"].value_counts().to_dict()
    metadata = {
        "total_points": len(features),
        "alert_count": class_counts.get(CLASS_ALERT, 0),
        "routine_count": class_counts.get(CLASS_ROUTINE, 0),
        "natural_count": class_counts.get(CLASS_NATURAL, 0),
        "industrial_zone_count": int(len(osm_gdf)) if not osm_gdf.empty else 0,
    }

    logger.info(
        f"Classification complete: {metadata['alert_count']} alerts, "
        f"{metadata['routine_count']} routine, {metadata['natural_count']} natural"
    )

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": metadata,
    }
