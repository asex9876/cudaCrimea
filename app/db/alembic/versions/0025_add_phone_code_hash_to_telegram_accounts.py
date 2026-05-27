"""Add phone_code_hash to telegram_accounts

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('telegram_accounts', sa.Column('phone_code_hash', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('telegram_accounts', 'phone_code_hash')
