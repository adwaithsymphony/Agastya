"""Add longitudinal plant intelligence records.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.create_table(
        "plant_intelligence_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crop_cycle_id", sa.Integer(), sa.ForeignKey("crop_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("growth_stage", sa.String(80)),
        sa.Column("height_cm", sa.Float()),
        sa.Column("measurements", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("measurement_source", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("height_cm IS NULL OR height_cm >= 0", name="ck_plant_intelligence_observations_plant_height_nonnegative"),
    )
    op.create_index("ix_plant_intelligence_observations_crop_cycle_id", "plant_intelligence_observations", ["crop_cycle_id"])
    op.create_index("ix_plant_intelligence_observations_created_by", "plant_intelligence_observations", ["created_by"])
    op.create_table(
        "plant_intelligence_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crop_cycle_id", sa.Integer(), sa.ForeignKey("crop_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_type", sa.String(32), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Float()),
        sa.Column("unit", sa.String(40)),
        sa.Column("source", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("source_record_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_plant_intelligence_activities_plant_activity_quantity_nonnegative"),
        sa.UniqueConstraint("crop_cycle_id", "source", "source_record_id", "activity_type", name="uq_plant_activity_source_record"),
    )
    op.create_index("ix_plant_intelligence_activities_crop_cycle_id", "plant_intelligence_activities", ["crop_cycle_id"])
    op.create_index("ix_plant_intelligence_activities_created_by", "plant_intelligence_activities", ["created_by"])
    op.create_table(
        "plant_intelligence_crop_guidance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crop_id", sa.Integer(), sa.ForeignKey("crop_references.id", ondelete="CASCADE"), nullable=False),
        sa.Column("soil_moisture_min_pct", sa.Float()),
        sa.Column("sunlight_min_hours", sa.Float()),
        sa.Column("fertilizer_guidance", sa.Text()),
        sa.Column("disease_guidance", sa.Text()),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("soil_moisture_min_pct IS NULL OR (soil_moisture_min_pct >= 0 AND soil_moisture_min_pct <= 100)", name="ck_plant_intelligence_crop_guidance_plant_guidance_soil_moisture_range"),
        sa.CheckConstraint("sunlight_min_hours IS NULL OR (sunlight_min_hours >= 0 AND sunlight_min_hours <= 24)", name="ck_plant_intelligence_crop_guidance_plant_guidance_sunlight_range"),
        sa.UniqueConstraint("crop_id", name="uq_plant_intelligence_crop_guidance_crop_id"),
    )
    op.create_index("ix_plant_intelligence_crop_guidance_crop_id", "plant_intelligence_crop_guidance", ["crop_id"])

def downgrade() -> None:
    op.drop_index("ix_plant_intelligence_crop_guidance_crop_id", table_name="plant_intelligence_crop_guidance")
    op.drop_table("plant_intelligence_crop_guidance")
    op.drop_index("ix_plant_intelligence_activities_created_by", table_name="plant_intelligence_activities")
    op.drop_index("ix_plant_intelligence_activities_crop_cycle_id", table_name="plant_intelligence_activities")
    op.drop_table("plant_intelligence_activities")
    op.drop_index("ix_plant_intelligence_observations_created_by", table_name="plant_intelligence_observations")
    op.drop_index("ix_plant_intelligence_observations_crop_cycle_id", table_name="plant_intelligence_observations")
    op.drop_table("plant_intelligence_observations")
