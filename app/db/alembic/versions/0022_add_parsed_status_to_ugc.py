"""Add parsed status to UGC submissions

Revision ID: 0022
Revises: 0021
Create Date: 2025-10-22
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new column for AI-structured flag
    op.add_column('ugc_submissions', sa.Column('is_ai_structured', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    # Add new column for parser source
    op.add_column('ugc_submissions', sa.Column('parser_source', sa.String(100), nullable=True))

    # Drop old constraint
    op.drop_constraint('ck_ugc_status', 'ugc_submissions', type_='check')

    # Add new constraint with 'parsed' status
    op.create_check_constraint(
        'ck_ugc_status',
        'ugc_submissions',
        "status IN ('pending','approved','rejected','auto_approved','parsed')"
    )

    # Create index for parsed events
    op.create_index('ix_ugc_submissions_parsed', 'ugc_submissions', ['status', 'is_ai_structured'])


def downgrade() -> None:
    op.drop_index('ix_ugc_submissions_parsed', table_name='ugc_submissions')
    op.drop_constraint('ck_ugc_status', 'ugc_submissions', type_='check')
    op.create_check_constraint(
        'ck_ugc_status',
        'ugc_submissions',
        "status IN ('pending','approved','rejected','auto_approved')"
    )
    op.drop_column('ugc_submissions', 'parser_source')
    op.drop_column('ugc_submissions', 'is_ai_structured')
