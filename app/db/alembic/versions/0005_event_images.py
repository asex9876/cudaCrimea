"""event images gallery

Revision ID: 0005_event_images
Revises: 0004_curated_cards
Create Date: 2025-09-15 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0005_event_images"
down_revision = "0004_curated_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index("ix_event_images_event_prio", "event_images", ["event_id", "priority"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_event_images_event_prio", table_name="event_images")
    op.drop_table("event_images")

