from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.config import get_settings
from app.core.events import audit, notify, org_user_ids, role_user_ids
from app.core.storage import get_storage, new_key
from app.ml.crop_vision import CropVisionModel, get_model
from app.modules.farms.models import CropCycle
from app.modules.identity.models import Role, User
from app.modules.monitoring.images import validate_image
from app.modules.monitoring.models import (
    CropObservation,
    ModelPrediction,
    ModelRegistryEntry,
    PredictionStatus,
    ReviewStatus,
    UploadedImage,
)


def ensure_registry(db: Session, model: CropVisionModel | None = None) -> ModelRegistryEntry | None:
    model = model or get_model()
    if not model.available or not model.card:
        return None
    card = model.card
    entry = db.scalar(
        select(ModelRegistryEntry).where(ModelRegistryEntry.key == card["key"], ModelRegistryEntry.version == card["version"])
    )
    if entry is None:
        entry = ModelRegistryEntry(
            key=card["key"],
            version=card["version"],
            name=card["name"],
            task=card["task"],
            framework=card["framework"],
            artifact_sha256=card.get("artifact_sha256"),
            classes=card.get("classes", []),
            metrics=card.get("metrics", {}),
            license=f"Weights: {card['backbone']['license']}; training data: {card['training_data']['license']}",
            status="active",
            notes="\n".join(card.get("limitations", [])),
        )
        db.add(entry)
        db.flush()
    return entry


def run_inference(db: Session, obs: CropObservation, cycle: CropCycle, image_bytes: bytes) -> ModelPrediction:
    model = get_model()
    result = model.predict(image_bytes, expected_crop_prefix=cycle.crop.vision_label_prefix)
    entry = ensure_registry(db, model) if result.model_version else None
    pred = ModelPrediction(
        observation_id=obs.id,
        model_registry_id=entry.id if entry else None,
        **{k: v for k, v in result.to_dict().items()},
    )
    db.add(pred)
    obs.status = result.status
    if result.review_recommended and obs.review_status != ReviewStatus.REVIEWED:
        obs.review_status = ReviewStatus.AWAITING
    db.flush()
    return pred


def create_observation(
    db: Session,
    *,
    user: User,
    cycle: CropCycle,
    raw: bytes,
    filename: str | None,
    notes: str | None,
    observed_at: datetime | None,
    source_note: str | None = None,
) -> CropObservation:
    img = validate_image(raw)
    key = new_key("observations", img.ext)
    get_storage().put(key, img.data, img.content_type)
    image = UploadedImage(
        storage_key=key,
        original_filename=(filename or "")[:255] or None,
        content_type=img.content_type,
        size_bytes=len(img.data),
        width=img.width,
        height=img.height,
        sha256=img.sha256,
        uploaded_by=user.id,
        retain_until=now_utc() + timedelta(days=get_settings().image_retention_days),
        source_note=source_note,
    )
    db.add(image)
    db.flush()
    obs = CropObservation(
        crop_cycle_id=cycle.id,
        image_id=image.id,
        observed_at=observed_at or now_utc(),
        notes=notes,
        status=PredictionStatus.PENDING,
        review_status=ReviewStatus.NOT_REQUIRED,
        created_by=user.id,
    )
    db.add(obs)
    db.flush()
    pred = run_inference(db, obs, cycle, img.data)
    audit(db, actor_id=user.id, action="observation.created", entity_type="crop_observation", entity_id=obs.id,
          after={"prediction_status": pred.status, "model": pred.model_key, "version": pred.model_version})
    if obs.review_status == ReviewStatus.AWAITING:
        notify(
            db,
            role_user_ids(db, Role.REVIEWER),
            event_type="observation.review_requested",
            title=f"{cycle.crop.name} observation needs review",
            body=f"{cycle.field.farm.name} · {cycle.field.name}. Model status: {pred.status.replace('_', ' ')}.",
            entity_type="crop_observation",
            entity_id=obs.id,
            link=f"/app/observations/{obs.id}",
        )
    return obs


def notify_review(db: Session, obs: CropObservation, reviewer: User, decision: str) -> None:
    cycle = db.get(CropCycle, obs.crop_cycle_id)
    notify(
        db,
        org_user_ids(db, cycle.field.farm.organization_id, Role.FARMER),
        event_type="observation.reviewed",
        title=f"Review recorded for your {cycle.crop.name} observation",
        body=f"{reviewer.full_name}: {decision.replace('_', ' ')}.",
        entity_type="crop_observation",
        entity_id=obs.id,
        link=f"/app/observations/{obs.id}",
    )
