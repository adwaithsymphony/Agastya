import io

import numpy as np
from PIL import Image

from app.core.config import BACKEND_DIR
from app.ml.crop_vision import CropVisionModel, get_model, set_model
from tests.conftest import cycle_id

LEAVES = BACKEND_DIR / "seed_assets" / "leaves"


def _upload(client, cycle, data, name="leaf.jpg", ctype="image/jpeg", notes=None):
    files = {"image": (name, data, ctype)}
    form = {"crop_cycle_id": str(cycle)}
    if notes:
        form["notes"] = notes
    return client.post("/api/v1/observations", data=form, files=files)


def test_upload_runs_real_inference_and_persists(farmer, db):
    tomato = cycle_id(farmer, "Tomato")
    r = _upload(farmer, tomato, (LEAVES / "tomato_septoria_leaf_spot_0.jpg").read_bytes(), notes="spots")
    assert r.status_code == 201, r.text
    body = r.json()
    p = body["prediction"]
    assert p["model_key"] == "crop-vision-plantvillage" and p["model_version"] == "1.0.0"
    assert p["predicted_class"] == "Tomato___Septoria_leaf_spot"
    assert 0 < p["confidence"] <= 1 and len(p["top_k"]) == 3
    assert body["status"] == "completed" and body["review_status"] == "awaiting_review"
    # persisted and visible after reload
    again = farmer.get(f"/api/v1/observations/{body['id']}").json()
    assert again["prediction"]["id"] == p["id"]
    timeline = farmer.get(f"/api/v1/crop-cycles/{tomato}/timeline").json()
    assert any(i["kind"] == "observation" and i["id"] == body["id"] for i in timeline)
    img = farmer.get(f"/api/v1/observations/{body['id']}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


def test_healthy_leaf_does_not_require_review(farmer):
    r = _upload(farmer, cycle_id(farmer, "Tomato"), (LEAVES / "tomato_healthy_0.jpg").read_bytes()).json()
    assert r["status"] == "completed" and r["review_status"] == "not_required"


def test_crop_mismatch_is_uncertain(farmer):
    r = _upload(farmer, cycle_id(farmer, "Capsicum"), (LEAVES / "tomato_septoria_leaf_spot_0.jpg").read_bytes()).json()
    assert r["status"] == "uncertain" and r["prediction"]["status_reason"] == "predicted_crop_mismatch"


def test_unsupported_crop_reports_unsupported_input(farmer):
    r = _upload(farmer, cycle_id(farmer, "Mustard"), (LEAVES / "tomato_healthy_0.jpg").read_bytes()).json()
    assert r["status"] == "unsupported_input"
    assert r["prediction"]["status_reason"] == "crop_not_covered_by_model"


def test_non_leaf_image_is_rejected_by_ood_guard(farmer):
    rng = np.random.default_rng(0)
    buf = io.BytesIO()
    Image.fromarray((rng.random((300, 300, 3)) * 255).astype("uint8")).save(buf, format="PNG")
    r = _upload(farmer, cycle_id(farmer, "Tomato"), buf.getvalue(), name="noise.png", ctype="image/png").json()
    assert r["status"] == "unsupported_input" and r["prediction"]["status_reason"] == "image_not_recognised_as_leaf"


def test_invalid_files_rejected(farmer):
    tomato = cycle_id(farmer, "Tomato")
    r = _upload(farmer, tomato, b"this is not an image", name="fake.jpg")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_image"
    tiny = io.BytesIO()
    Image.new("RGB", (20, 20)).save(tiny, format="PNG")
    assert _upload(farmer, tomato, tiny.getvalue(), name="tiny.png").status_code == 422
    gif = io.BytesIO()
    Image.new("RGB", (100, 100)).save(gif, format="GIF")
    assert _upload(farmer, tomato, gif.getvalue(), name="x.gif", ctype="image/gif").status_code == 422
    truncated = (LEAVES / "tomato_healthy_0.jpg").read_bytes()[:2000]
    assert _upload(farmer, tomato, truncated).status_code == 422


def test_model_unavailable_records_failure_without_fabricated_result(farmer, tmp_path):
    original = get_model()
    set_model(CropVisionModel(tmp_path))  # empty directory: no model files
    try:
        r = _upload(farmer, cycle_id(farmer, "Tomato"), (LEAVES / "tomato_healthy_0.jpg").read_bytes())
        assert r.status_code == 201
        p = r.json()["prediction"]
        assert r.json()["status"] == "failed"
        assert p["predicted_class"] is None and p["confidence"] is None and p["top_k"] == []
        assert p["status_reason"] == "model_files_missing"
        status = farmer.get("/api/v1/model-predictions/status").json()
        assert status["available"] is False
    finally:
        set_model(original)
    # re-analysis once the model is back produces a genuine result
    obs_id = r.json()["id"]
    again = farmer.post(f"/api/v1/observations/{obs_id}/reanalyze").json()
    assert again["prediction"]["status"] == "completed" and len(again["predictions"]) == 2


def test_review_flow_and_notification(farmer, reviewer):
    queue = reviewer.get("/api/v1/reviews/queue").json()
    uncertain = [o for o in queue["items"] if o["status"] == "uncertain"]
    assert uncertain, "seed should include an uncertain observation"
    oid = uncertain[0]["id"]
    bad = reviewer.post(f"/api/v1/observations/{oid}/reviews", json={"decision": "corrected"})
    assert bad.status_code == 422
    r = reviewer.post(f"/api/v1/observations/{oid}/reviews", json={
        "decision": "corrected", "reviewed_label": "Tomato — late blight", "notes": "Water-soaked lesions."})
    assert r.status_code == 201
    obs = farmer.get(f"/api/v1/observations/{oid}").json()
    assert obs["review_status"] == "reviewed"
    # model output is retained separately from the human review
    assert obs["prediction"]["predicted_class"] == "Tomato___Early_blight"
    assert obs["reviews"][0]["reviewed_label"] == "Tomato — late blight"
    notes = farmer.get("/api/v1/notifications?unread=true").json()["items"]
    assert any(n["event_type"] == "observation.reviewed" and n["entity_id"] == oid for n in notes)
