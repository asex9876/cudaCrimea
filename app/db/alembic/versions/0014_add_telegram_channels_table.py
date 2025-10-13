"""Add telegram_channels table for channel management

Revision ID: 0014
Revises: 0013
Create Date: 2025-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'telegram_channels',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('channel_id', sa.BigInteger(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default=sa.text("'active'"), nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('last_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('total_messages_seen', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('total_parsed', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('total_published', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('added_by', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_telegram_channels_status', 'telegram_channels', ['status'])
    op.create_index('ix_telegram_channels_username', 'telegram_channels', ['username'])


def downgrade() -> None:
    op.drop_index('ix_telegram_channels_username', 'telegram_channels')
    op.drop_index('ix_telegram_channels_status', 'telegram_channels')
    op.drop_table('telegram_channels')
