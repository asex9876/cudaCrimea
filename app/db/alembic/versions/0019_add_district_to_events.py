"""Add district column to events

Revision ID: 0019
Revises: 0018
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add district column to events table
    op.add_column('events', sa.Column('district', sa.String(length=200), nullable=True))

    # Create index for district filtering
    op.create_index('ix_events_district', 'events', ['district'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_events_district', table_name='events')
    op.drop_column('events', 'district')
