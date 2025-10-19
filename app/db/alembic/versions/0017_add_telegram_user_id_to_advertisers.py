"""Add telegram_user_id to advertisers

Revision ID: 0017
Revises: 0016
Create Date: 2025-10-19

"""
from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add telegram_user_id column to advertisers
    op.add_column('advertisers', sa.Column('telegram_user_id', sa.BigInteger(), nullable=True))

    # Create unique index for telegram_user_id
    op.create_index('ix_advertisers_telegram_user_id', 'advertisers', ['telegram_user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_advertisers_telegram_user_id', table_name='advertisers')
    op.drop_column('advertisers', 'telegram_user_id')
