"""Reorder events table columns to match model definition

Revision ID: 0013
Revises: 0012
Create Date: 2025-01-15

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop and recreate events table with correct column order (table is empty, safe to drop)

    # Step 1: Drop all foreign keys pointing to events table
    op.execute("ALTER TABLE event_images DROP CONSTRAINT IF EXISTS event_images_event_id_fkey")
    op.execute("ALTER TABLE ugc_submissions DROP CONSTRAINT IF EXISTS ugc_submissions_event_id_fkey")
    op.execute("ALTER TABLE placement_requests DROP CONSTRAINT IF EXISTS placement_requests_event_id_fkey")
    op.execute("ALTER TABLE scheduled_posts DROP CONSTRAINT IF EXISTS scheduled_posts_event_id_fkey")
    op.execute("ALTER TABLE ad_interactions DROP CONSTRAINT IF EXISTS ad_interactions_event_id_fkey")
    op.execute("ALTER TABLE parsed_messages DROP CONSTRAINT IF EXISTS parsed_messages_event_id_fkey")

    # Step 2: Drop events table
    op.execute("DROP TABLE IF EXISTS events CASCADE")

    # Step 3: Create new table with correct column order matching the model
    op.execute("""
        CREATE TABLE events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title TEXT NOT NULL,
            date DATE NOT NULL,
            time TIME,
            price_min INTEGER,
            price_max INTEGER,
            is_free BOOLEAN DEFAULT false NOT NULL,
            category TEXT NOT NULL,
            city VARCHAR,
            venue_name TEXT NOT NULL,
            address TEXT NOT NULL,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            description VARCHAR,
            image_url TEXT,
            images JSONB,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL,
            quality_score DOUBLE PRECISION DEFAULT 0 NOT NULL,
            event_type VARCHAR DEFAULT 'free' NOT NULL,
            advertiser_id UUID,
            pricing_model VARCHAR,
            price_paid INTEGER,
            budget INTEGER,
            spent_budget INTEGER DEFAULT 0,
            position VARCHAR,
            views INTEGER DEFAULT 0 NOT NULL,
            clicks INTEGER DEFAULT 0 NOT NULL,
            status VARCHAR DEFAULT 'active' NOT NULL,
            is_approved BOOLEAN DEFAULT true NOT NULL,
            duplicate_of UUID,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT ck_events_category CHECK (category IN ('concert','theatre','kids','tour','party','expo','other')),
            CONSTRAINT ck_events_type CHECK (event_type IN ('free','paid')),
            CONSTRAINT ck_events_pricing_model CHECK (pricing_model IS NULL OR pricing_model IN ('fixed','cpc','cpm')),
            CONSTRAINT ck_events_position CHECK (position IS NULL OR position IN ('standard','top','pinned')),
            CONSTRAINT ck_events_status CHECK (status IN ('draft','active','past','pending_moderation'))
        )
    """)

    # Step 4: Add foreign keys
    op.execute("ALTER TABLE events ADD CONSTRAINT events_advertiser_id_fkey FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE events ADD CONSTRAINT events_duplicate_of_fkey FOREIGN KEY (duplicate_of) REFERENCES events(id) ON DELETE SET NULL")

    # Step 5: Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_events_date ON events(date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_events_category ON events(category)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_events_lat_lon ON events(lat, lon)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_events_type_status ON events(event_type, status)")

    # Step 6: Recreate foreign keys in other tables pointing to events
    op.execute("ALTER TABLE event_images ADD CONSTRAINT event_images_event_id_fkey FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE ugc_submissions ADD CONSTRAINT ugc_submissions_event_id_fkey FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE placement_requests ADD CONSTRAINT placement_requests_event_id_fkey FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE scheduled_posts ADD CONSTRAINT scheduled_posts_event_id_fkey FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE ad_interactions ADD CONSTRAINT ad_interactions_event_id_fkey FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE parsed_messages ADD CONSTRAINT parsed_messages_event_id_fkey FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL")


def downgrade() -> None:
    # This migration cannot be easily reverted
    # You would need to manually restore from backup
    raise NotImplementedError("Cannot downgrade column reordering migration")
