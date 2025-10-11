"""add paid placements models

Revision ID: 0007_add_paid_placements
Revises: 0006_scheduler_notification
Create Date: 2025-10-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0007_add_paid_placements'
down_revision = '0006_scheduler_notification'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create advertisers table
    op.create_table(
        'advertisers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('contact_person', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('balance', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_advertisers_email', 'advertisers', ['email'])

    # Create placement_requests table
    op.create_table(
        'placement_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('advertiser_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_title', sa.String(), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('event_time', sa.Time(), nullable=True),
        sa.Column('event_description', sa.String(), nullable=True),
        sa.Column('event_venue', sa.String(), nullable=True),
        sa.Column('event_address', sa.String(), nullable=True),
        sa.Column('pricing_model', sa.String(), nullable=False),
        sa.Column('position', sa.String(), server_default="'standard'", nullable=False),
        sa.Column('budget', sa.Integer(), nullable=False),
        sa.Column('price_per_unit', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), server_default="'pending'", nullable=False),
        sa.Column('reject_reason', sa.String(), nullable=True),
        sa.Column('invoice_url', sa.String(), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['advertiser_id'], ['advertisers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='SET NULL'),
        sa.CheckConstraint("pricing_model IN ('fixed','cpc','cpm')", name='ck_placement_pricing_model'),
        sa.CheckConstraint("position IN ('standard','top','pinned')", name='ck_placement_position'),
        sa.CheckConstraint("status IN ('pending','approved','rejected','paid','active','completed')", name='ck_placement_status'),
    )
    op.create_index('ix_placement_requests_status', 'placement_requests', ['status'])
    op.create_index('ix_placement_requests_advertiser', 'placement_requests', ['advertiser_id'])

    # Create ad_interactions table
    op.create_table(
        'ad_interactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('interaction_type', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.CheckConstraint("interaction_type IN ('view','click')", name='ck_ad_interactions_type'),
    )
    op.create_index('ix_ad_interactions_event', 'ad_interactions', ['event_id', 'created_at'])
    op.create_index('ix_ad_interactions_type', 'ad_interactions', ['interaction_type'])

    # Create ugc_submissions table
    op.create_table(
        'ugc_submissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('raw_text', sa.String(), nullable=False),
        sa.Column('images', postgresql.JSONB(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('extracted_data', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.String(), server_default="'pending'", nullable=False),
        sa.Column('reject_reason', sa.String(), nullable=True),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('moderated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('pending','approved','rejected','auto_approved')", name='ck_ugc_status'),
    )
    op.create_index('ix_ugc_submissions_status', 'ugc_submissions', ['status'])
    op.create_index('ix_ugc_submissions_user', 'ugc_submissions', ['user_id'])

    # Extend events table with paid placement fields
    op.add_column('events', sa.Column('is_free', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('events', sa.Column('description', sa.String(), nullable=True))
    op.add_column('events', sa.Column('event_type', sa.String(), server_default="'free'", nullable=False))
    op.add_column('events', sa.Column('advertiser_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('events', sa.Column('pricing_model', sa.String(), nullable=True))
    op.add_column('events', sa.Column('price_paid', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('budget', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('spent_budget', sa.Integer(), server_default='0', nullable=True))
    op.add_column('events', sa.Column('position', sa.String(), nullable=True))
    op.add_column('events', sa.Column('views', sa.Integer(), server_default='0', nullable=False))
    op.add_column('events', sa.Column('clicks', sa.Integer(), server_default='0', nullable=False))
    op.add_column('events', sa.Column('status', sa.String(), server_default="'active'", nullable=False))
    op.add_column('events', sa.Column('is_approved', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('events', sa.Column('duplicate_of', postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key('fk_events_advertiser', 'events', 'advertisers', ['advertiser_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_events_duplicate', 'events', 'events', ['duplicate_of'], ['id'], ondelete='SET NULL')

    # Update existing rows to ensure they match constraints
    op.execute("UPDATE events SET event_type = 'free' WHERE event_type IS NULL OR event_type NOT IN ('free', 'paid')")
    op.execute("UPDATE events SET status = 'active' WHERE status IS NULL OR status NOT IN ('draft', 'active', 'past', 'pending_moderation')")

    op.create_check_constraint('ck_events_type', 'events', "event_type IN ('free','paid')")
    op.create_check_constraint('ck_events_pricing_model', 'events', "pricing_model IS NULL OR pricing_model IN ('fixed','cpc','cpm')")
    op.create_check_constraint('ck_events_position', 'events', "position IS NULL OR position IN ('standard','top','pinned')")
    op.create_check_constraint('ck_events_status', 'events', "status IN ('draft','active','past','pending_moderation')")

    op.create_index('ix_events_type_status', 'events', ['event_type', 'status'])

    # Drop obsolete tables
    op.drop_table('event_place_link')
    op.drop_table('ads_slots')
    op.drop_table('clicks')


def downgrade() -> None:
    # Drop new indexes and constraints from events
    op.drop_index('ix_events_type_status', 'events')
    op.drop_constraint('ck_events_status', 'events')
    op.drop_constraint('ck_events_position', 'events')
    op.drop_constraint('ck_events_pricing_model', 'events')
    op.drop_constraint('ck_events_type', 'events')
    op.drop_constraint('fk_events_duplicate', 'events')
    op.drop_constraint('fk_events_advertiser', 'events')

    # Drop new columns from events
    op.drop_column('events', 'duplicate_of')
    op.drop_column('events', 'is_approved')
    op.drop_column('events', 'status')
    op.drop_column('events', 'clicks')
    op.drop_column('events', 'views')
    op.drop_column('events', 'position')
    op.drop_column('events', 'spent_budget')
    op.drop_column('events', 'budget')
    op.drop_column('events', 'price_paid')
    op.drop_column('events', 'pricing_model')
    op.drop_column('events', 'advertiser_id')
    op.drop_column('events', 'event_type')
    op.drop_column('events', 'description')
    op.drop_column('events', 'is_free')

    # Drop new tables
    op.drop_table('ugc_submissions')
    op.drop_table('ad_interactions')
    op.drop_table('placement_requests')
    op.drop_table('advertisers')

    # Recreate old tables (simplified - may need adjustment)
    # For now, skipping recreation as it's unlikely we'll downgrade
