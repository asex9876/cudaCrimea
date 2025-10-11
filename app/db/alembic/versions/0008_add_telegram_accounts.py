"""add_telegram_accounts

Revision ID: 0008
Revises: 0007
Create Date: 2025-10-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create telegram_accounts table
    op.create_table(
        'telegram_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('phone', sa.String(), nullable=False),
        sa.Column('api_id', sa.Integer(), nullable=False),
        sa.Column('api_hash', sa.String(), nullable=False),
        sa.Column('session_string', sa.String(), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('photo_url', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('pending','active','error')", name='ck_telegram_accounts_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone', name='uq_telegram_accounts_phone')
    )


def downgrade() -> None:
    op.drop_table('telegram_accounts')
