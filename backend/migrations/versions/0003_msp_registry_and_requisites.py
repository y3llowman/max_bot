from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('msp_registry',
    sa.Column('inn', sa.String(length=12), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('subject_type', sa.String(length=2), nullable=False),
    sa.Column('category', sa.Integer(), nullable=False),
    sa.Column('ogrn', sa.String(length=15), nullable=False),
    sa.Column('main_activity_code', sa.String(length=20), nullable=False),
    sa.Column('main_activity_name', sa.Text(), nullable=False),
    sa.Column('region_code', sa.String(length=10), nullable=False),
    sa.Column('is_new', sa.Boolean(), nullable=False),
    sa.Column('date_registered', sa.String(length=20), nullable=False),
    sa.Column('date_excluded', sa.String(length=20), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('website', sa.String(length=255), nullable=True),
    sa.Column('employees_num', sa.Integer(), nullable=True),
    sa.Column('has_licenses', sa.Boolean(), nullable=False),
    sa.Column('is_hitech', sa.Boolean(), nullable=False),
    sa.Column('is_partnership', sa.Boolean(), nullable=False),
    sa.Column('is_social', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('inn')
    )
    op.create_table('msp_registry_loads',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('source', sa.String(length=500), nullable=False),
    sa.Column('data_date', sa.Date(), nullable=True),
    sa.Column('records', sa.Integer(), nullable=False),
    sa.Column('loaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('business_profiles', sa.Column('kpp', sa.String(length=9), nullable=True))
    op.add_column('business_profiles', sa.Column('address', sa.Text(), nullable=True))
    op.add_column('business_profiles', sa.Column('director_position', sa.String(length=100), nullable=True))
    op.add_column('business_profiles', sa.Column('director_name', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('business_profiles', 'director_name')
    op.drop_column('business_profiles', 'director_position')
    op.drop_column('business_profiles', 'address')
    op.drop_column('business_profiles', 'kpp')
    op.drop_table('msp_registry_loads')
    op.drop_table('msp_registry')
