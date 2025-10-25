"""Add end_date to events for multi-day events

Revision ID: 0023
Revises: 0022
Create Date: 2025-10-22
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add end_date column for multi-day events
    op.add_column('events', sa.Column('end_date', sa.Date(), nullable=True))

    # Create index for archiving queries
    op.create_index('ix_events_end_date', 'events', ['end_date'])


def downgrade() -> None:
    op.drop_index('ix_events_end_date', table_name='events')
    op.drop_column('events', 'end_date')
