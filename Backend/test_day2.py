# test_day2.py -- End-to-end verification of Day 2 backend features.

import sys
import json
import traceback

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

results = []


def run_test(name, fn):
    """Run a test function; record pass/fail."""
    try:
        fn()
        results.append((name, "PASS", ""))
        print(f"  [OK]   {name}")
    except AssertionError as e:
        results.append((name, "FAIL", str(e)))
        print(f"  [FAIL] {name}: {e}")
    except Exception as e:
        results.append((name, "ERROR", f"{type(e).__name__}: {e}"))
        print(f"  [ERR]  {name}: {type(e).__name__}: {e}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Module-level tests (no server)
# ---------------------------------------------------------------------------

def test_classifier_facility_tags():
    """Classified features should carry osm_id and industrial_type."""
    from classifier import classify_thermal_points
    firms = json.load(open("data/firms_points.geojson"))
    osm = json.load(open("data/osm_industrial.geojson"))
    result = classify_thermal_points(firms, osm)
    assert result["type"] == "FeatureCollection"
    industrial = [f for f in result["features"] if f["properties"]["inside_industrial"]]
    assert len(industrial) > 0, "Expected at least 1 industrial point"
    sample = industrial[0]["properties"]
    assert "osm_id" in sample, "Missing osm_id in classified feature"
    assert "industrial_type" in sample, "Missing industrial_type in classified feature"


def test_classifier_200m_buffer():
    """Verify that the 200m buffer catches points near (but outside) zone edges."""
    from classifier import BUFFER_METERS
    assert BUFFER_METERS == 200, f"Expected BUFFER_METERS=200, got {BUFFER_METERS}"


def test_baseline_engine():
    """Baseline engine should produce clusters with all required fields."""
    from classifier import classify_thermal_points
    from baseline_engine import compute_baselines
    firms = json.load(open("data/firms_points.geojson"))
    osm = json.load(open("data/osm_industrial.geojson"))
    classified = classify_thermal_points(firms, osm)
    facilities = compute_baselines(classified)
    assert facilities["type"] == "FeatureCollection"
    assert len(facilities["features"]) >= 1, "Expected at least 1 cluster"
    sample = facilities["features"][0]["properties"]
    for key in ("cluster_id", "frequency_count", "baseline_frp_mean",
                "baseline_frp_std", "max_temp_k", "is_persistent", "source_type"):
        assert key in sample, f"Missing key: {key}"
    meta = facilities["metadata"]
    assert "persistent_count" in meta
    assert "cluster_count" in meta


def test_baseline_empty_input():
    """Baseline engine must return empty FeatureCollection for empty input."""
    from baseline_engine import compute_baselines
    result = compute_baselines({"type": "FeatureCollection", "features": []})
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 0
    assert result["metadata"]["cluster_count"] == 0


def test_weather_service_smoke_vector():
    """Smoke vector computation should return correct bearing and endpoint."""
    from weather_service import compute_smoke_vector
    sv = compute_smoke_vector(
        origin_lat=22.8, origin_lon=86.2,
        wind_speed_kmh=10.0, wind_direction_deg=90.0,  # wind from east
    )
    assert "bearing_deg" in sv
    assert "distance_km" in sv
    assert "end_lat" in sv
    assert "end_lon" in sv
    # Smoke should travel westward (270 deg) since wind is from east (90 deg)
    assert 260 <= sv["bearing_deg"] <= 280, f"Expected ~270, got {sv['bearing_deg']}"
    assert sv["distance_km"] == 20.0, f"Expected 20 km (10 km/h x 2h), got {sv['distance_km']}"


def test_weather_enrich_alerts():
    """enrich_alerts should add weather + smoke_vector to each feature."""
    from weather_service import enrich_alerts
    mock_alerts = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [86.2, 22.8]},
            "properties": {"frp": 100.0, "classification": "Industrial Fire Alert"},
        }],
    }
    enriched = enrich_alerts(mock_alerts)
    assert len(enriched["features"]) == 1
    props = enriched["features"][0]["properties"]
    assert "weather" in props, "Missing weather data"
    assert "smoke_vector" in props, "Missing smoke_vector"
    w = props["weather"]
    for k in ("temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m"):
        assert k in w, f"Missing weather key: {k}"


def test_weather_fallback():
    """Weather service should not crash and should return fallback on bad coords."""
    from weather_service import fetch_weather, FALLBACK_WEATHER
    # Coordinates in the middle of the ocean -- API may error or return data
    result = fetch_weather(0.0, 0.0)
    assert isinstance(result, dict)
    assert "temperature_2m" in result
    assert "wind_speed_10m" in result


# ---------------------------------------------------------------------------
# FastAPI TestClient endpoint tests (frontend contract verification)
# ---------------------------------------------------------------------------

def test_endpoint_root():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "2.0.0"
    assert "facilities" in data["endpoints"]
    assert "alerts" in data["endpoints"]


def test_endpoint_thermal_points():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/api/v1/thermal-points")
    assert resp.status_code == 200, f"Status {resp.status_code}"
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0


def test_endpoint_facilities_strict_schema():
    """Facilities endpoint must return exact frontend-expected property keys."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/api/v1/facilities")
    assert resp.status_code == 200, f"Status {resp.status_code}"
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 1, "Expected at least 1 facility cluster"
    props = data["features"][0]["properties"]
    # Strict frontend contract
    assert props["category"] == "Routine Operational Heat", f"category={props.get('category')}"
    assert "frp_baseline" in props, "Missing frp_baseline"
    assert isinstance(props["frp_baseline"], float), f"frp_baseline type={type(props['frp_baseline'])}"
    assert "frequency_count" in props, "Missing frequency_count"
    assert isinstance(props["frequency_count"], int), f"frequency_count type={type(props['frequency_count'])}"
    assert "facility_name" in props, "Missing facility_name"


def test_endpoint_alerts_strict_schema():
    """Alerts endpoint must return exact frontend-expected property keys."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/api/v1/alerts")
    assert resp.status_code == 200, f"Status {resp.status_code}"
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    if data["features"]:
        props = data["features"][0]["properties"]
        # Strict frontend contract
        assert "id" in props, "Missing id"
        assert isinstance(props["id"], int), f"id type={type(props['id'])}"
        assert props["category"] == "Industrial Fire Alert", f"category={props.get('category')}"
        assert "frp" in props, "Missing frp"
        assert isinstance(props["frp"], float), f"frp type={type(props['frp'])}"
        assert "facility_name" in props, "Missing facility_name"
        assert "wind_speed" in props, "Missing wind_speed"
        assert isinstance(props["wind_speed"], float), f"wind_speed type={type(props['wind_speed'])}"
        assert "smoke_bearing" in props, "Missing smoke_bearing"
        assert isinstance(props["smoke_bearing"], float), f"smoke_bearing type={type(props['smoke_bearing'])}"


def test_endpoint_stats():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200, f"Status {resp.status_code}"
    data = resp.json()
    assert data["status"] == "ok"
    stats = data["data"]
    for key in ("total_scanned", "persistent_sources", "active_emergencies", "average_frp"):
        assert key in stats, f"Missing stats key: {key}"


def test_empty_dataset_returns_200():
    """Endpoints must return HTTP 200 with empty FeatureCollection, never crash."""
    from main import _reshape_alerts, _reshape_facilities
    empty = {"type": "FeatureCollection", "features": []}
    alerts = _reshape_alerts(empty)
    assert alerts["type"] == "FeatureCollection"
    assert len(alerts["features"]) == 0

    empty_fac = {"type": "FeatureCollection", "features": [], "metadata": {"cluster_count": 0, "persistent_count": 0}}
    facilities = _reshape_facilities(empty_fac)
    assert facilities["type"] == "FeatureCollection"
    assert len(facilities["features"]) == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 64)
    print("  PyroGuard Day 2 -- Verification Suite (Frontend-Compatible)")
    print("=" * 64 + "\n")

    print("-- Module-level tests --")
    run_test("Classifier facility tags (osm_id, industrial_type)", test_classifier_facility_tags)
    run_test("200m spatial buffer constant", test_classifier_200m_buffer)
    run_test("Baseline engine (DBSCAN clusters)", test_baseline_engine)
    run_test("Baseline engine (empty input)", test_baseline_empty_input)
    run_test("Smoke vector computation", test_weather_service_smoke_vector)
    run_test("Weather alert enrichment", test_weather_enrich_alerts)
    run_test("Weather fallback on bad coords", test_weather_fallback)

    print("\n-- Endpoint tests (strict frontend contract) --")
    run_test("GET /", test_endpoint_root)
    run_test("GET /api/v1/thermal-points", test_endpoint_thermal_points)
    run_test("GET /api/v1/facilities (strict schema)", test_endpoint_facilities_strict_schema)
    run_test("GET /api/v1/alerts (strict schema)", test_endpoint_alerts_strict_schema)
    run_test("GET /api/v1/stats", test_endpoint_stats)
    run_test("Empty dataset returns 200", test_empty_dataset_returns_200)

    # Summary
    print("\n" + "=" * 64)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s != "PASS")
    print(f"  Results: {passed} passed, {failed} failed out of {len(results)} tests")

    if failed:
        print("\n  Failed tests:")
        for name, status, msg in results:
            if status != "PASS":
                print(f"    [x] [{status}] {name}: {msg}")

    print("=" * 64 + "\n")
    sys.exit(1 if failed else 0)
