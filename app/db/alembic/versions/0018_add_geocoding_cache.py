"""Add geocoding_cache table

Revision ID: 0018
Revises: 0017
Create Date: 2025-10-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create geocoding_cache table
    op.create_table(
        'geocoding_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('query', sa.String(length=500), nullable=False),
        sa.Column('lat', sa.Numeric(precision=10, scale=8), nullable=False),
        sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=False),
        sa.Column('district', sa.String(length=200), nullable=True),
        sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('query')
    )

    # Create index on query column
    op.create_index('ix_geocoding_cache_query', 'geocoding_cache', ['query'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_geocoding_cache_query', table_name='geocoding_cache')
    op.drop_table('geocoding_cache')
