from tests.conftest import cycle_id


def test_farmer_can_record_observation_and_activity(farmer):
    cycle = cycle_id(farmer, "Tomato")
    obs = farmer.post("/api/v1/plant-intelligence/observations", json={
        "crop_cycle_id": cycle, "growth_stage": "flowering", "height_cm": 22.5,
        "measurements": {"leaf_count": 14}, "measurement_source": "manual", "notes": "Morning inspection"
    })
    assert obs.status_code == 201, obs.text
    activity = farmer.post("/api/v1/plant-intelligence/activities", json={
        "crop_cycle_id": cycle, "activity_type": "watering", "description": "Watered after checking soil",
        "quantity": 2, "unit": "litres"
    })
    assert activity.status_code == 201, activity.text
    timeline = farmer.get(f"/api/v1/plant-intelligence/crops/{cycle}/timeline")
    assert timeline.status_code == 200
    body = timeline.json()
    assert body["observations"][0]["growth_stage"] == "flowering"
    assert body["observations"][0]["measurement_source"] == "manual"
    assert body["activities"][0]["activity_type"] == "watering"


def test_farmer_cannot_read_another_organizations_plant_timeline(farmer, other_farmer):
    cycles = other_farmer.get("/api/v1/crop-cycles").json()
    cycle = next(c["id"] for c in cycles if c["status"] != "closed")
    response = farmer.get(f"/api/v1/plant-intelligence/crops/{cycle}/timeline")
    assert response.status_code == 404


def test_linked_activity_requires_source_record_id(farmer):
    cycle = cycle_id(farmer, "Tomato")
    response = farmer.post("/api/v1/plant-intelligence/activities", json={
        "crop_cycle_id": cycle, "activity_type": "pesticide", "description": "Imported pesticide record",
        "source": "agastya_record"
    })
    assert response.status_code == 422


def test_language_preference_is_persisted_for_account(farmer):
    response = farmer.patch("/api/v1/auth/me", json={"preferred_language": "ml"})
    assert response.status_code == 200, response.text
    me = farmer.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["preferred_language"] == "ml"


def test_invalid_language_preference_is_rejected(farmer):
    response = farmer.patch("/api/v1/auth/me", json={"preferred_language": "xx"})
    assert response.status_code == 422


def test_recommendations_require_configured_guidance_and_recorded_measurements(farmer, admin):
    cycles = farmer.get("/api/v1/crop-cycles").json()
    cycle = next(c for c in cycles if c["status"] != "closed")
    cycle_id_value = cycle["id"]
    crop_id_value = cycle["crop"]["id"]
    recorded = farmer.post("/api/v1/plant-intelligence/observations", json={
        "crop_cycle_id": cycle_id_value, "measurements": {"soil_moisture_pct": 10, "sunlight_hours": 1},
        "measurement_source": "manual", "notes": "Values entered by farmer"
    })
    assert recorded.status_code == 201, recorded.text
    saved = admin.put(f"/api/v1/plant-intelligence/guidance/{crop_id_value}", json={
        "soil_moisture_min_pct": 30, "sunlight_min_hours": 6,
        "fertilizer_guidance": "Review soil test before selecting a fertilizer.",
        "disease_guidance": None, "source_reference": "Agronomist-reviewed crop protocol v1"
    })
    assert saved.status_code == 200, saved.text
    result = farmer.get(f"/api/v1/plant-intelligence/crops/{cycle_id_value}/recommendations").json()
    assert {item["type"] for item in result["items"]} == {"water", "light", "fertilizer"}
    assert all(item["source_reference"] == "Agronomist-reviewed crop protocol v1" for item in result["items"])


def test_only_admin_can_configure_crop_guidance(farmer):
    cycles = farmer.get("/api/v1/crop-cycles").json()
    crop_id_value = cycles[0]["crop"]["id"]
    response = farmer.put(f"/api/v1/plant-intelligence/guidance/{crop_id_value}", json={
        "source_reference": "not allowed"
    })
    assert response.status_code == 403
