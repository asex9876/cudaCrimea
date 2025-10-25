"""Add parse_interval_minutes to telegram_channels

Revision ID: 0024
Revises: 0023
Create Date: 2025-10-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add parse_interval_minutes column
    op.add_column('telegram_channels', sa.Column('parse_interval_minutes', sa.Integer(), server_default=sa.text('45'), nullable=False))


def downgrade() -> None:
    # Remove parse_interval_minutes column
    op.drop_column('telegram_channels', 'parse_interval_minutes')
