"""curated cards

Revision ID: 0004_curated_cards
Revises: 0003_add_image_url
Create Date: 2025-09-14 00:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_curated_cards"
down_revision = "0003_add_image_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "curated_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("button_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("active_from", sa.Date(), nullable=False),
        sa.Column("active_to", sa.Date(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("item_type IN ('event','place','external')", name="ck_cards_item_type"),
    )
    op.create_index("ix_cards_city_date", "curated_cards", ["city", "active_from", "active_to"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cards_city_date", table_name="curated_cards")
    op.drop_table("curated_cards")

