from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType, Timestamped, enum_check, utcnow, UTCDateTime

GRADES = ("A", "B", "C")
UNITS_TO_KG = {"kg": Decimal("1"), "quintal": Decimal("100"), "tonne": Decimal("1000")}


class BatchStatus(StrEnum):
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    NEEDS_DESTINATION = "needs_destination"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CLOSED = "closed"


class AssignmentStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED_BY_BUYER = "cancelled_by_buyer"
    SUPERSEDED = "superseded"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class ShipmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class DemandStatus(StrEnum):
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"


class RerouteTrigger(StrEnum):
    BUYER_CANCELLED = "buyer_cancelled"
    DISRUPTION = "disruption"
    UNASSIGNED = "unassigned"


class BuyerProfile(Timestamped, Base):
    __tablename__ = "buyer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    buyer_type: Mapped[str] = mapped_column(String(60), nullable=False)
    district: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    receiving_capacity_kg_per_day: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    delivery_preference: Mapped[str] = mapped_column(String(20), nullable=False, default="either")
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (enum_check("delivery_preference", ["buyer_pickup", "farm_delivery", "either"]),)


class BuyerDemand(Timestamped, Base):
    __tablename__ = "buyer_demands"
    __table_args__ = (
        enum_check("status", [s.value for s in DemandStatus]),
        sa.CheckConstraint("quantity_kg > 0", name="qty_positive"),
        sa.CheckConstraint("valid_until >= valid_from", name="validity_order"),
        sa.CheckConstraint("delivery_end >= delivery_start", name="delivery_order"),
        sa.CheckConstraint("max_distance_km IS NULL OR max_distance_km > 0", name="distance_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyer_profiles.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crop_references.id"), nullable=False, index=True)
    accepted_grades: Mapped[list] = mapped_column(JSONType, nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_start: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_end: Mapped[date] = mapped_column(Date, nullable=False)
    max_distance_km: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=DemandStatus.OPEN)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    buyer: Mapped[BuyerProfile] = relationship(lazy="joined")
    crop = relationship("CropReference", lazy="joined")


class ProduceBatch(Timestamped, Base):
    __tablename__ = "produce_batches"
    __table_args__ = (
        enum_check("status", [s.value for s in BatchStatus]),
        enum_check("grade", list(GRADES)),
        enum_check("unit", list(UNITS_TO_KG)),
        sa.CheckConstraint("quantity_value > 0", name="qty_positive"),
        sa.CheckConstraint("quantity_kg > 0", name="qty_kg_positive"),
        sa.CheckConstraint("shelf_life_days IS NULL OR shelf_life_days > 0", name="shelf_life_positive"),
        sa.CheckConstraint("deliver_by IS NULL OR deliver_by >= available_from", name="deliver_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    crop_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("crop_cycles.id"), index=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crop_references.id"), nullable=False)
    quantity_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default="kg")
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    grade: Mapped[str] = mapped_column(String(2), nullable=False)
    quality_notes: Mapped[str | None] = mapped_column(Text)
    harvested_on: Mapped[date] = mapped_column(Date, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    shelf_life_source: Mapped[str | None] = mapped_column(String(20))
    storage_condition: Mapped[str | None] = mapped_column(String(80))
    available_from: Mapped[date] = mapped_column(Date, nullable=False)
    deliver_by: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=BatchStatus.UNASSIGNED)
    harvest_check_status: Mapped[str | None] = mapped_column(String(16))
    harvest_check_details: Mapped[dict | None] = mapped_column(JSONType)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    crop = relationship("CropReference", lazy="joined")
    crop_cycle = relationship("CropCycle")
    assignments: Mapped[list[BatchAssignment]] = relationship(
        back_populates="batch", order_by="BatchAssignment.id.desc()"
    )

    __mapper_args__ = {"version_id_col": version}


class RerouteRun(Timestamped, Base):
    __tablename__ = "reroute_runs"
    __table_args__ = (enum_check("trigger", [t.value for t in RerouteTrigger]),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("produce_batches.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(20), nullable=False)
    matches: Mapped[list[BuyerMatch]] = relationship(order_by="BuyerMatch.rank.asc().nulls_last(), BuyerMatch.id")


class BuyerMatch(Timestamped, Base):
    __tablename__ = "buyer_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("reroute_runs.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("produce_batches.id", ondelete="CASCADE"), index=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("buyer_demands.id"), nullable=False)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyer_profiles.id"), nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    remaining_demand_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    components: Mapped[dict] = mapped_column(JSONType, default=dict)
    reasons: Mapped[list] = mapped_column(JSONType, default=list)
    tradeoffs: Mapped[list] = mapped_column(JSONType, default=list)
    exclusions: Mapped[list] = mapped_column(JSONType, default=list)

    buyer: Mapped[BuyerProfile] = relationship(lazy="joined")
    demand: Mapped[BuyerDemand] = relationship(lazy="joined")


class BatchAssignment(Base):
    __tablename__ = "batch_assignments"
    __table_args__ = (
        enum_check("status", [s.value for s in AssignmentStatus]),
        sa.CheckConstraint("quantity_kg > 0", name="qty_positive"),
        sa.Index(
            "uq_batch_one_active_assignment",
            "batch_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("produce_batches.id", ondelete="CASCADE"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyer_profiles.id"), nullable=False, index=True)
    demand_id: Mapped[int | None] = mapped_column(ForeignKey("buyer_demands.id"), index=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("buyer_matches.id"))
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=AssignmentStatus.ACTIVE)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ended_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    end_reason: Mapped[str | None] = mapped_column(Text)

    batch: Mapped[ProduceBatch] = relationship(back_populates="assignments")
    buyer: Mapped[BuyerProfile] = relationship(lazy="joined")
    demand: Mapped[BuyerDemand | None] = relationship(lazy="joined")
    shipment: Mapped[Shipment | None] = relationship(back_populates="assignment", uselist=False)


class Shipment(Timestamped, Base):
    __tablename__ = "shipments"
    __table_args__ = (enum_check("status", [s.value for s in ShipmentStatus]),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("produce_batches.id", ondelete="CASCADE"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("batch_assignments.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ShipmentStatus.SCHEDULED)
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    assignment: Mapped[BatchAssignment] = relationship(back_populates="shipment")
    events: Mapped[list[ShipmentEvent]] = relationship(order_by="ShipmentEvent.id")


class ShipmentEvent(Timestamped, Base):
    __tablename__ = "shipment_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
