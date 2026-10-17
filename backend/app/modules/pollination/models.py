from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamped, enum_check, utcnow, UTCDateTime


class BookingStatus(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    RESCHEDULE_PROPOSED = "reschedule_proposed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


OPEN_BOOKING_STATUSES = (BookingStatus.REQUESTED, BookingStatus.ACCEPTED, BookingStatus.RESCHEDULE_PROPOSED)


class ProviderProfile(Timestamped, Base):
    __tablename__ = "pollination_providers"
    __table_args__ = (
        sa.CheckConstraint("colonies_total >= 0", name="colonies_nonneg"),
        sa.CheckConstraint("service_radius_km IS NULL OR service_radius_km > 0", name="radius_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(60), nullable=False, default="Apiary")
    pollinator: Mapped[str] = mapped_column(String(80), nullable=False, default="Apis mellifera (managed honey bee)")
    base_district: Mapped[str] = mapped_column(String(80), nullable=False)
    base_state: Mapped[str] = mapped_column(String(80), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    service_radius_km: Mapped[float | None] = mapped_column(Float)
    colonies_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    crops: Mapped[list[ProviderCrop]] = relationship(cascade="all, delete-orphan")
    service_areas: Mapped[list[ProviderServiceArea]] = relationship(cascade="all, delete-orphan")
    availability: Mapped[list[ProviderAvailability]] = relationship(
        cascade="all, delete-orphan", order_by="ProviderAvailability.start_date"
    )


class ProviderCrop(Base):
    __tablename__ = "provider_crops"
    provider_id: Mapped[int] = mapped_column(ForeignKey("pollination_providers.id", ondelete="CASCADE"), primary_key=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crop_references.id"), primary_key=True)
    crop = relationship("CropReference", lazy="joined")


class ProviderServiceArea(Base):
    __tablename__ = "provider_service_areas"
    __table_args__ = (sa.UniqueConstraint("provider_id", "district", "state", name="uq_service_area"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("pollination_providers.id", ondelete="CASCADE"), index=True)
    district: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)


class ProviderAvailability(Timestamped, Base):
    __tablename__ = "provider_availability"
    __table_args__ = (
        sa.CheckConstraint("end_date >= start_date", name="window_order"),
        sa.CheckConstraint("colonies_available > 0", name="colonies_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("pollination_providers.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    colonies_available: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255))


class PollinationBooking(Timestamped, Base):
    __tablename__ = "pollination_bookings"
    __table_args__ = (
        enum_check("status", [s.value for s in BookingStatus]),
        sa.CheckConstraint("end_date >= start_date", name="window_order"),
        sa.CheckConstraint("colonies_requested > 0", name="colonies_positive"),
        sa.CheckConstraint(
            "proposed_end_date IS NULL OR proposed_start_date IS NULL OR proposed_end_date >= proposed_start_date",
            name="proposed_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("pollination_providers.id"), index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    colonies_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=BookingStatus.REQUESTED)
    proposed_start_date: Mapped[date | None] = mapped_column(Date)
    proposed_end_date: Mapped[date | None] = mapped_column(Date)
    farmer_note: Mapped[str | None] = mapped_column(Text)
    provider_note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    provider: Mapped[ProviderProfile] = relationship(lazy="joined")
    crop_cycle = relationship("CropCycle", lazy="joined")
    events: Mapped[list[BookingEvent]] = relationship(order_by="BookingEvent.id")

    __mapper_args__ = {"version_id_col": version}


class BookingEvent(Timestamped, Base):
    __tablename__ = "pollination_booking_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("pollination_bookings.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    actor = relationship("User", lazy="joined")
