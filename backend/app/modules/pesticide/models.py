from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType, Timestamped, enum_check, UTCDateTime


class LabelVerification(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"


class LabelSource(StrEnum):
    MANUAL = "manual"
    OCR = "ocr"
    DEMO_SEED = "demo_seed"


class ApplicationStatus(StrEnum):
    ACTIVE = "active"
    VOIDED = "voided"


class HarvestStatus(StrEnum):
    RESTRICTED = "restricted"
    UPCOMING = "upcoming"
    ELIGIBLE = "eligible"
    UNKNOWN = "unknown"


class PesticideProduct(Timestamped, Base):
    __tablename__ = "pesticide_products"
    __table_args__ = (sa.UniqueConstraint("trade_name", "formulation", name="uq_product_name_formulation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_name: Mapped[str] = mapped_column(String(120), nullable=False)
    active_ingredient: Mapped[str | None] = mapped_column(String(160))
    formulation: Mapped[str | None] = mapped_column(String(60))
    product_type: Mapped[str | None] = mapped_column(String(40))
    registrant: Mapped[str | None] = mapped_column(String(160))
    registration_ref: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    labels: Mapped[list[ProductLabel]] = relationship(back_populates="product", order_by="ProductLabel.id")


class ProductLabel(Timestamped, Base):
    """A label version's rule for one crop. Only VERIFIED rows are used by the harvest engine."""

    __tablename__ = "product_labels"
    __table_args__ = (
        enum_check("verification_status", [v.value for v in LabelVerification]),
        enum_check("source_kind", [v.value for v in LabelSource]),
        sa.CheckConstraint("phi_days IS NULL OR phi_days >= 0", name="phi_non_negative"),
        sa.CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="validity_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("pesticide_products.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crop_references.id"), nullable=False, index=True)
    label_version: Mapped[str] = mapped_column(String(60), nullable=False)
    phi_days: Mapped[int | None] = mapped_column(Integer)
    dose_min: Mapped[float | None] = mapped_column(Numeric(10, 3, asdecimal=False))
    dose_max: Mapped[float | None] = mapped_column(Numeric(10, 3, asdecimal=False))
    dose_unit: Mapped[str | None] = mapped_column(String(40))
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, default=LabelSource.MANUAL)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default=LabelVerification.UNVERIFIED)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    product: Mapped[PesticideProduct] = relationship(back_populates="labels")
    crop = relationship("CropReference", lazy="joined")


class PesticideApplication(Timestamped, Base):
    __tablename__ = "pesticide_applications"
    __table_args__ = (
        enum_check("status", [s.value for s in ApplicationStatus]),
        sa.CheckConstraint("dose_value > 0", name="dose_positive"),
        sa.CheckConstraint("treated_area_ha IS NULL OR treated_area_ha > 0", name="area_positive"),
        sa.CheckConstraint("recorded_phi_days IS NULL OR recorded_phi_days >= 0", name="recorded_phi_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("pesticide_products.id"), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    dose_value: Mapped[float] = mapped_column(Numeric(10, 3, asdecimal=False), nullable=False)
    dose_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    treated_area_ha: Mapped[float | None] = mapped_column(Numeric(10, 2, asdecimal=False))
    application_method: Mapped[str | None] = mapped_column(String(60))
    target_problem: Mapped[str | None] = mapped_column(String(120))
    recorded_phi_days: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=ApplicationStatus.ACTIVE)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    void_reason: Mapped[str | None] = mapped_column(String(255))

    product: Mapped[PesticideProduct] = relationship(lazy="joined")
    recorder = relationship("User", foreign_keys=[recorded_by], lazy="joined")


class HarvestAssessment(Timestamped, Base):
    """Persisted snapshot of a harvest-eligibility calculation (history is retained)."""

    __tablename__ = "harvest_assessments"
    __table_args__ = (enum_check("status", [s.value for s in HarvestStatus]),)

    id: Mapped[int] = mapped_column(primary_key=True)
    crop_cycle_id: Mapped[int] = mapped_column(ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    earliest_eligible_date: Mapped[date | None] = mapped_column(Date)
    governing_application_id: Mapped[int | None] = mapped_column(ForeignKey("pesticide_applications.id"))
    unresolved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(60), nullable=False)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    computed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
