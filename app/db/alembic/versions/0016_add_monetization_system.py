"""Add monetization system: settings, placements, user geo

Revision ID: 0016
Revises: 0015
Create Date: 2025-10-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create monetization_settings table
    op.create_table(
        'monetization_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('setting_key', sa.String(50), nullable=False, unique=True),
        sa.Column('setting_value', sa.Numeric(10, 2), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('setting_key', name='uq_monetization_settings_key')
    )

    # Insert default monetization settings
    op.execute("""
        INSERT INTO monetization_settings (setting_key, setting_value) VALUES
        ('cost_per_lead', 50.00),
        ('conversion_general', 3.00),
        ('conversion_city', 5.00),
        ('conversion_zone', 7.00),
        ('q_less_2h', 3.0),
        ('q_2h_6h', 2.7),
        ('q_6h_12h', 2.2),
        ('q_12h_24h', 2.0),
        ('q_24h_30h', 1.8),
        ('q_30h_36h', 1.5),
        ('q_36h_48h', 1.3),
        ('q_more_48h', 1.0),
        ('q_hot', 1.0)
    """)

    # 2. Extend placements table (placement_requests)
    op.add_column('placement_requests', sa.Column('placement_type', sa.String(50), nullable=True))
    op.add_column('placement_requests', sa.Column('target_city', sa.String(100), nullable=True))
    op.add_column('placement_requests', sa.Column('target_zone', sa.String(100), nullable=True))
    op.add_column('placement_requests', sa.Column('calculated_price', sa.Numeric(10, 2), nullable=True))
    op.add_column('placement_requests', sa.Column('audience_size', sa.Integer(), nullable=True))
    op.add_column('placement_requests', sa.Column('conversion_rate', sa.Numeric(5, 2), nullable=True))
    op.add_column('placement_requests', sa.Column('time_coefficient', sa.Numeric(3, 1), nullable=True))

    # Add check constraint for placement_type
    op.create_check_constraint(
        'ck_placement_requests_type',
        'placement_requests',
        "placement_type IS NULL OR placement_type IN ('broadcast_all','broadcast_city','broadcast_zone','hot')"
    )

    # 3. Extend users table with geolocation
    op.add_column('users', sa.Column('zone', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('lat', sa.Numeric(10, 8), nullable=True))
    op.add_column('users', sa.Column('lon', sa.Numeric(11, 8), nullable=True))
    op.add_column('users', sa.Column('location_updated_at', sa.DateTime(timezone=True), nullable=True))

    # Create index for geolocation queries
    op.create_index('ix_users_city_zone', 'users', ['city', 'zone'])


def downgrade() -> None:
    # Remove users extensions
    op.drop_index('ix_users_city_zone', 'users')
    op.drop_column('users', 'location_updated_at')
    op.drop_column('users', 'lon')
    op.drop_column('users', 'lat')
    op.drop_column('users', 'zone')

    # Remove placement_requests extensions
    op.drop_constraint('ck_placement_requests_type', 'placement_requests')
    op.drop_column('placement_requests', 'time_coefficient')
    op.drop_column('placement_requests', 'conversion_rate')
    op.drop_column('placement_requests', 'audience_size')
    op.drop_column('placement_requests', 'calculated_price')
    op.drop_column('placement_requests', 'target_zone')
    op.drop_column('placement_requests', 'target_city')
    op.drop_column('placement_requests', 'placement_type')

    # Drop monetization_settings table
    op.drop_table('monetization_settings')
