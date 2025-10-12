"""add bot_settings table

Revision ID: 0010
Revises: 0009
Create Date: 2025-10-12 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create bot_settings table (singleton)
    op.create_table(
        'bot_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_name', sa.String(), nullable=False, server_default='CudaCrimea Bot'),
        sa.Column('bot_username', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('about', sa.String(), nullable=True),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('welcome_message', sa.String(), nullable=False,
                  server_default='Привет! Я помогу найти, куда пойти в Крыму/Севастополе. Выберите город:'),
        sa.Column('commands', JSONB, nullable=False,
                  server_default=sa.text("'[{\"command\":\"start\",\"description\":\"Старт / выбор города\"},{\"command\":\"menu\",\"description\":\"Показать меню\"}]'::jsonb")),
        sa.Column('menu_buttons', JSONB, nullable=False,
                  server_default=sa.text("'[{\"text\":\"🎤 Куда сходить\",\"action\":\"what_to_do\"},{\"text\":\"🍽 Где поесть\",\"action\":\"food\"},{\"text\":\"✍ Предложить событие\",\"action\":\"ugc\"}]'::jsonb")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('id = 1', name='ck_bot_settings_singleton')
    )

    # Insert default settings row
    op.execute("""
        INSERT INTO bot_settings (id, bot_name, welcome_message, commands, menu_buttons)
        VALUES (
            1,
            'CudaCrimea Bot',
            'Привет! Я помогу найти, куда пойти в Крыму/Севастополе. Выберите город:',
            '[{"command":"start","description":"Старт / выбор города"},{"command":"menu","description":"Показать меню"}]'::jsonb,
            '[{"text":"🎤 Куда сходить","action":"what_to_do"},{"text":"🍽 Где поесть","action":"food"},{"text":"✍ Предложить событие","action":"ugc"}]'::jsonb
        )
    """)


def downgrade() -> None:
    # Drop table
    op.drop_table('bot_settings')
