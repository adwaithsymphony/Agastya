from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType, Timestamped, enum_check, UTCDateTime


class PredictionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    UNCERTAIN = "uncertain"
    UNSUPPORTED_INPUT = "unsupported_input"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    AWAITING = "awaiting_review"
    REVIEWED = "reviewed"


class ReviewDecision(StrEnum):
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    INCONCLUSIVE = "inconclusive"
    IMAGE_UNUSABLE = "image_unusable"


class UploadedImage(Timestamped, Base):
    __tablename__ = "uploaded_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    retain_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source_note: Mapped[str | None] = mapped_column(String(255))


class CropObservation(Timestamped, Base):
    __tablename__ = "crop_observations"
    __table_args__ = (
        enum_check("status", [s.value for s in PredictionStatus]),
        enum_check("review_status", [s.value for s in ReviewStatus]),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_images.id"))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=PredictionStatus.PENDING)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default=ReviewStatus.NOT_REQUIRED)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    image: Mapped[UploadedImage | None] = relationship(lazy="joined")
    predictions: Mapped[list[ModelPrediction]] = relationship(
        back_populates="observation", order_by="ModelPrediction.id.desc()"
    )
    reviews: Mapped[list[HumanReview]] = relationship(order_by="HumanReview.id.desc()")


class ModelRegistryEntry(Timestamped, Base):
    __tablename__ = "model_registry"
    __table_args__ = (sa.UniqueConstraint("key", "version", name="uq_model_registry_key_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    task: Mapped[str] = mapped_column(String(80), nullable=False)
    framework: Mapped[str] = mapped_column(String(40), nullable=False)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    classes: Mapped[list] = mapped_column(JSONType, default=list)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)
    license: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ModelPrediction(Timestamped, Base):
    __tablename__ = "model_predictions"
    __table_args__ = (
        enum_check("status", [s.value for s in PredictionStatus]),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("crop_observations.id", ondelete="CASCADE"), index=True)
    model_registry_id: Mapped[int | None] = mapped_column(ForeignKey("model_registry.id"))
    model_key: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    predicted_class: Mapped[str | None] = mapped_column(String(120))
    predicted_crop: Mapped[str | None] = mapped_column(String(60))
    predicted_condition: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[float | None] = mapped_column(Float)
    top_k: Mapped[list] = mapped_column(JSONType, default=list)
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    status_reason: Mapped[str | None] = mapped_column(String(80))
    review_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    observation: Mapped[CropObservation] = relationship(back_populates="predictions")


class HumanReview(Timestamped, Base):
    __tablename__ = "human_reviews"
    __table_args__ = (enum_check("decision", [d.value for d in ReviewDecision]),)

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("crop_observations.id", ondelete="CASCADE"), index=True)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("model_predictions.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reviewed_label: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(String(255))

    reviewer = relationship("User", lazy="joined")
