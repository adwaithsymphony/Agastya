from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Float, Integer, String, Text, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UTCDateTime, JSONType, utcnow


class PlantObservation(Timestamped, Base):
    __tablename__ = "plant_intelligence_observations"
    __table_args__ = (
        CheckConstraint("height_cm IS NULL OR height_cm >= 0", name="plant_height_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    growth_stage: Mapped[str | None] = mapped_column(String(80))
    height_cm: Mapped[float | None] = mapped_column(Float)
    measurements: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    measurement_source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    notes: Mapped[str | None] = mapped_column(Text)


class PlantActivity(Timestamped, Base):
    __tablename__ = "plant_intelligence_activities"
    __table_args__ = (
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="plant_activity_quantity_nonnegative"),
        UniqueConstraint("crop_cycle_id", "source", "source_record_id", "activity_type", name="uq_plant_activity_source_record"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    source_record_id: Mapped[int | None] = mapped_column(Integer)


class CropCareGuidance(Timestamped, Base):
    __tablename__ = "plant_intelligence_crop_guidance"
    __table_args__ = (
        CheckConstraint("soil_moisture_min_pct IS NULL OR (soil_moisture_min_pct >= 0 AND soil_moisture_min_pct <= 100)", name="plant_guidance_soil_moisture_range"),
        CheckConstraint("sunlight_min_hours IS NULL OR (sunlight_min_hours >= 0 AND sunlight_min_hours <= 24)", name="plant_guidance_sunlight_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crop_references.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    soil_moisture_min_pct: Mapped[float | None] = mapped_column(Float)
    sunlight_min_hours: Mapped[float | None] = mapped_column(Float)
    fertilizer_guidance: Mapped[str | None] = mapped_column(Text)
    disease_guidance: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    verified_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
