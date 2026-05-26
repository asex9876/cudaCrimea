"""Change images column type to JSONB

Revision ID: 0012
Revises: 0011
Create Date: 2025-01-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change images column from VARCHAR to JSONB
    # Use USING clause to convert existing string data to JSONB
    # NULL values will remain NULL, empty strings will become NULL
    op.execute("""
        DO $$
        BEGIN
            IF (SELECT data_type FROM information_schema.columns
                WHERE table_name='events' AND column_name='images') = 'character varying' THEN
                ALTER TABLE events ALTER COLUMN images TYPE JSONB
                USING CASE WHEN images IS NULL OR images = '' THEN NULL ELSE images::jsonb END;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Convert JSONB back to VARCHAR (lossy operation)
    op.execute("""
        ALTER TABLE events
        ALTER COLUMN images
        TYPE VARCHAR
        USING CASE
            WHEN images IS NULL THEN NULL
            ELSE images::text
        END
    """)
