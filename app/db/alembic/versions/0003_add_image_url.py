"""add image_url to events and places

Revision ID: 0003_add_image_url
Revises: 0002_editorial_pins
Create Date: 2025-09-14 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_add_image_url"
down_revision = "0002_editorial_pins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("image_url", sa.Text(), nullable=True))
    op.add_column("places", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("places", "image_url")
    op.drop_column("events", "image_url")

