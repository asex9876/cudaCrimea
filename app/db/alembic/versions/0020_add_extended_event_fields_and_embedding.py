"""Add extended event fields and embedding for AI parsing

Revision ID: 0020
Revises: 0019
Create Date: 2025-10-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add extended metadata fields
    op.add_column('events', sa.Column('age_restriction', sa.String(length=5), nullable=True))
    op.add_column('events', sa.Column('organizer', sa.String(length=500), nullable=True))
    op.add_column('events', sa.Column('end_time', sa.Time(), nullable=True))
    op.add_column('events', sa.Column('duration_minutes', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('capacity', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('recurring_pattern', sa.String(length=50), nullable=True))
    op.add_column('events', sa.Column('ticket_type', sa.String(length=20), nullable=True))

    # Add embedding field for semantic search
    op.add_column('events', sa.Column('embedding', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Add CHECK constraints
    op.create_check_constraint(
        'ck_events_age_restriction',
        'events',
        "age_restriction IS NULL OR age_restriction IN ('0+','6+','12+','16+','18+')"
    )
    op.create_check_constraint(
        'ck_events_ticket_type',
        'events',
        "ticket_type IS NULL OR ticket_type IN ('sale','booking','free','registration')"
    )

    # Update category constraint to include 'sport'
    op.drop_constraint('ck_events_category', 'events', type_='check')
    op.create_check_constraint(
        'ck_events_category',
        'events',
        "category IN ('concert','theatre','kids','tour','party','expo','other','sport')"
    )


def downgrade() -> None:
    # Drop CHECK constraints
    op.drop_constraint('ck_events_age_restriction', 'events', type_='check')
    op.drop_constraint('ck_events_ticket_type', 'events', type_='check')

    # Restore original category constraint
    op.drop_constraint('ck_events_category', 'events', type_='check')
    op.create_check_constraint(
        'ck_events_category',
        'events',
        "category IN ('concert','theatre','kids','tour','party','expo','other')"
    )

    # Drop columns
    op.drop_column('events', 'embedding')
    op.drop_column('events', 'ticket_type')
    op.drop_column('events', 'recurring_pattern')
    op.drop_column('events', 'capacity')
    op.drop_column('events', 'duration_minutes')
    op.drop_column('events', 'end_time')
    op.drop_column('events', 'organizer')
    op.drop_column('events', 'age_restriction')
