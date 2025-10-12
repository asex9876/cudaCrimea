"""add parsed_messages table

Revision ID: 0011
Revises: 0010
Create Date: 2025-10-12 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, BIGINT


# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create parsed_messages table
    op.create_table(
        'parsed_messages',
        sa.Column('id', UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('channel_username', sa.String(), nullable=False),
        sa.Column('message_id', BIGINT, nullable=False),
        sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('event_created', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('event_id', UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel_username', 'message_id', name='uq_parsed_messages_channel_msg')
    )

    # Create indexes
    op.create_index('ix_parsed_messages_channel', 'parsed_messages', ['channel_username'])
    op.create_index('ix_parsed_messages_parsed_at', 'parsed_messages', ['parsed_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_parsed_messages_parsed_at', 'parsed_messages')
    op.drop_index('ix_parsed_messages_channel', 'parsed_messages')

    # Drop table
    op.drop_table('parsed_messages')
