"""add missing columns city and images

Revision ID: 1c064442d6af
Revises: 0008
Create Date: 2025-10-12 07:54:18.744526
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '1c064442d6af'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add city column to events table
    op.add_column('events', sa.Column('city', sa.String(), nullable=False, server_default='Симферополь'))

    # Add images column to events table (JSONB array)
    op.add_column('events', sa.Column('images', JSONB, nullable=True))

    # Remove server_default after adding (we only needed it for existing rows)
    op.alter_column('events', 'city', server_default=None)

    # Add city column to venues table
    op.add_column('venues', sa.Column('city', sa.String(), nullable=True))

    # Add images column to ugc_submissions table
    op.add_column('ugc_submissions', sa.Column('images', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove columns in reverse order
    op.drop_column('ugc_submissions', 'images')
    op.drop_column('venues', 'city')
    op.drop_column('events', 'images')
    op.drop_column('events', 'city')
