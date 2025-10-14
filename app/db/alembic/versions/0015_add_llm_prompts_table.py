"""Add llm_prompts table for prompt management

Revision ID: 0015
Revises: 0014
Create Date: 2025-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'llm_prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('prompt_type', sa.String(), nullable=False),
        sa.Column('system_prompt', sa.String(), nullable=False),
        sa.Column('user_prompt_template', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("prompt_type IN ('classifier','extractor')", name='ck_llm_prompts_type')
    )
    op.create_index('ix_llm_prompts_type_active', 'llm_prompts', ['prompt_type', 'is_active'])

    # Insert default prompts based on current implementation
    op.execute("""
        INSERT INTO llm_prompts (name, prompt_type, system_prompt, description, is_active)
        VALUES (
            'Default Classifier',
            'classifier',
            'Ты классификатор. Ответь JSON {is_event: boolean, reasons: string[]}. is_event=true только если текст описывает конкретное событие / мероприятие (дата, место, афиша). Не добавляй ничего кроме JSON.',
            'Стандартный промпт для классификации событий',
            true
        ),
        (
            'Default Extractor',
            'extractor',
            'Ты — извлекатель фактов о событиях в Крыму/Севастополе. Верни JSON: {title, date_iso, time_24h|null, venue_name, address, price_min, price_max, category in [concert|theatre|kids|tour|party|expo|other], source_url}. Если нет данных — null. Не придумывай.',
            'Стандартный промпт для извлечения данных о событиях',
            true
        )
    """)


def downgrade() -> None:
    op.drop_index('ix_llm_prompts_type_active', 'llm_prompts')
    op.drop_table('llm_prompts')
