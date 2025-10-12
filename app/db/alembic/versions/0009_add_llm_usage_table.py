"""add llm_usage table for token tracking

Revision ID: 0009
Revises: 1c064442d6af
Create Date: 2025-10-12 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '0009'
down_revision = '1c064442d6af'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create llm_usage table
    op.create_table(
        'llm_usage',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('service', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False, server_default='ai-mediator'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_rub', sa.Float(), nullable=True),
        sa.Column('metadata', JSONB, nullable=False, server_default="'{}'::jsonb"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for performance
    op.create_index('ix_llm_usage_service_date', 'llm_usage', ['service', 'created_at'])
    op.create_index('ix_llm_usage_model_date', 'llm_usage', ['model', 'created_at'])
    op.create_index('ix_llm_usage_date', 'llm_usage', ['created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_llm_usage_date', table_name='llm_usage')
    op.drop_index('ix_llm_usage_model_date', table_name='llm_usage')
    op.drop_index('ix_llm_usage_service_date', table_name='llm_usage')

    # Drop table
    op.drop_table('llm_usage')
