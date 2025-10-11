"""init models

Revision ID: 0001_init_models
Revises: 
Create Date: 2025-09-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_init_models"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("tg_id", sa.BigInteger(), primary_key=True),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("home_lat", sa.Float(), nullable=True),
        sa.Column("home_lon", sa.Float(), nullable=True),
        sa.Column("prefs", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # events
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time", sa.Time(), nullable=True),
        sa.Column("price_min", sa.Integer(), nullable=True),
        sa.Column("price_max", sa.Integer(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("venue_name", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("quality_score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("category IN ('concert','theatre','kids','tour','party','expo','other')", name="ck_events_category"),
    )
    op.create_index("ix_events_date", "events", ["date"], unique=False)
    op.create_index("ix_events_category", "events", ["category"], unique=False)
    op.create_index("ix_events_lat_lon", "events", ["lat", "lon"], unique=False)

    # places
    op.create_table(
        "places",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("price_level", sa.SmallInteger(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("category IN ('cafe','bar','restaurant','dessert','coffee','other')", name="ck_places_category"),
    )
    op.create_index("ix_places_lat_lon", "places", ["lat", "lon"], unique=False)

    # event_place_link
    op.create_table(
        "event_place_link",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("places.id", ondelete="CASCADE"), primary_key=True),
    )

    # ads_slots
    op.create_table(
        "ads_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("active_from", sa.Date(), nullable=False),
        sa.Column("active_to", sa.Date(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("type IN ('event','place','banner')", name="ck_ads_slots_type"),
    )
    op.create_index("ix_ads_slots_city_active", "ads_slots", ["city", "active_from", "active_to"], unique=False)

    # clicks
    op.create_table(
        "clicks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_tg", sa.BigInteger(), nullable=False),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("item_type IN ('event','place')", name="ck_clicks_item_type"),
        sa.CheckConstraint("action IN ('details','call','route','book')", name="ck_clicks_action"),
    )
    op.create_index("ix_clicks_user_tg_ts_desc", "clicks", ["user_tg", sa.text("ts DESC")], unique=False)

    # Trigger for updated_at on events
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS trigger AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_events_updated_at
            BEFORE UPDATE ON events
            FOR EACH ROW
            EXECUTE PROCEDURE set_updated_at();
            """
        )
    )


def downgrade() -> None:
    # Drop trigger and function first
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_events_updated_at ON events"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS set_updated_at"))

    # Drop indexes and tables in reverse order
    op.drop_index("ix_clicks_user_tg_ts_desc", table_name="clicks")
    op.drop_table("clicks")

    op.drop_index("ix_ads_slots_city_active", table_name="ads_slots")
    op.drop_table("ads_slots")

    op.drop_table("event_place_link")

    op.drop_index("ix_places_lat_lon", table_name="places")
    op.drop_table("places")

    op.drop_index("ix_events_lat_lon", table_name="events")
    op.drop_index("ix_events_category", table_name="events")
    op.drop_index("ix_events_date", table_name="events")
    op.drop_table("events")

    op.drop_table("users")
