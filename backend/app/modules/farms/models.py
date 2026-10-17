from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType, Timestamped, enum_check, UTCDateTime


class CycleStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    HARVESTING = "harvesting"
    CLOSED = "closed"


class CropReference(Timestamped, Base):
    __tablename__ = "crop_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    scientific_name: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    growth_stages: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # Whether managed pollinators are commonly used for this crop (reference data, admin-managed).
    pollinator_dependent: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    # Class-name prefix used by the crop-vision model (e.g. "Tomato"); null when not covered.
    vision_label_prefix: Mapped[str | None] = mapped_column(String(60))


class Farm(Timestamped, Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    village: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_source: Mapped[str | None] = mapped_column(String(80))

    fields: Mapped[list[Field]] = relationship(back_populates="farm", order_by="Field.name")

    __table_args__ = (
        sa.CheckConstraint("latitude IS NULL OR (latitude BETWEEN -90 AND 90)", name="lat_range"),
        sa.CheckConstraint("longitude IS NULL OR (longitude BETWEEN -180 AND 180)", name="lon_range"),
    )


class Field(Timestamped, Base):
    __tablename__ = "fields"
    __table_args__ = (
        sa.UniqueConstraint("farm_id", "name", name="uq_fields_farm_name"),
        sa.CheckConstraint("area_ha > 0", name="area_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    area_ha: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False), nullable=False)
    soil_type: Mapped[str | None] = mapped_column(String(60))
    irrigation: Mapped[str | None] = mapped_column(String(60))

    farm: Mapped[Farm] = relationship(back_populates="fields")
    cycles: Mapped[list[CropCycle]] = relationship(back_populates="field", order_by="CropCycle.sowing_date.desc()")


class CropCycle(Timestamped, Base):
    __tablename__ = "crop_cycles"
    __table_args__ = (
        enum_check("status", [s.value for s in CycleStatus]),
        sa.CheckConstraint(
            "expected_flowering_end IS NULL OR expected_flowering_start IS NULL "
            "OR expected_flowering_end >= expected_flowering_start",
            name="flowering_order",
        ),
        sa.CheckConstraint(
            "expected_harvest_date IS NULL OR expected_harvest_date >= sowing_date", name="harvest_after_sowing"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crop_references.id"), nullable=False)
    variety: Mapped[str | None] = mapped_column(String(80))
    season: Mapped[str | None] = mapped_column(String(40))
    sowing_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_flowering_start: Mapped[date | None] = mapped_column(Date)
    expected_flowering_end: Mapped[date | None] = mapped_column(Date)
    expected_harvest_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CycleStatus.ACTIVE)
    current_stage: Mapped[str | None] = mapped_column(String(60))
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    field: Mapped[Field] = relationship(back_populates="cycles")
    crop: Mapped[CropReference] = relationship(lazy="joined")


class GrowthStageRecord(Timestamped, Base):
    __tablename__ = "growth_stage_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(60), nullable=False)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
