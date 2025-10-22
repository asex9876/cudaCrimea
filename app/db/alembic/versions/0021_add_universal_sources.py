"""Add universal sources table for AI-powered parsing

Revision ID: 0021
Revises: 0020
Create Date: 2025-10-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create universal_sources table
    op.create_table(
        'universal_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('parse_interval_minutes', sa.Integer(), server_default=sa.text('30'), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('parsing_strategy', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('total_parsed', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_parsed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Create indexes
    op.create_index('ix_universal_sources_url', 'universal_sources', ['url'], unique=True)
    op.create_index('ix_universal_sources_is_active', 'universal_sources', ['is_active'], unique=False)
    op.create_index('ix_universal_sources_last_parsed_at', 'universal_sources', ['last_parsed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_universal_sources_last_parsed_at', table_name='universal_sources')
    op.drop_index('ix_universal_sources_is_active', table_name='universal_sources')
    op.drop_index('ix_universal_sources_url', table_name='universal_sources')
    op.drop_table('universal_sources')
