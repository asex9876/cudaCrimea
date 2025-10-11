"""editorial pins

Revision ID: 0002_editorial_pins
Revises: 0001_init_models
Create Date: 2025-09-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_editorial_pins"
down_revision = "0001_init_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editorial_pins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title_override", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("active_from", sa.Date(), nullable=False),
        sa.Column("active_to", sa.Date(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("item_type IN ('event','place')", name="ck_pins_item_type"),
    )
    op.create_index("ix_pins_city_date", "editorial_pins", ["city", "active_from", "active_to"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pins_city_date", table_name="editorial_pins")
    op.drop_table("editorial_pins")

