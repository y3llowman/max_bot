from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('businesses',
    sa.Column('inn', sa.String(length=12), nullable=False),
    sa.Column('name', sa.String(length=500), nullable=False),
    sa.Column('subject_type', sa.String(length=2), nullable=False),
    sa.Column('category', sa.Integer(), nullable=False),
    sa.Column('ogrn', sa.String(length=15), nullable=False),
    sa.Column('main_activity_code', sa.String(length=20), nullable=False),
    sa.Column('main_activity_name', sa.String(length=500), nullable=False),
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
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('inn')
    )
    op.create_table('laws',
    sa.Column('eo_number', sa.String(length=32), nullable=False),
    sa.Column('header', sa.String(length=500), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('published', sa.Date(), nullable=False),
    sa.Column('topics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('region', sa.String(length=2), nullable=True),
    sa.Column('amended', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('effective', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pages', sa.Integer(), nullable=True),
    sa.Column('pdf_size', sa.Integer(), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('eo_number')
    )
    op.create_index(op.f('ix_laws_published'), 'laws', ['published'], unique=False)
    op.create_table('radar_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inn', sa.String(length=12), nullable=False),
    sa.Column('type', sa.String(length=48), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('key', sa.String(length=200), nullable=False),
    sa.Column('source', sa.String(length=8), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('due', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('in_list', sa.Boolean(), nullable=False),
    sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_radar_events_inn'), 'radar_events', ['inn'], unique=False)
    op.create_index('uq_event_condition_open', 'radar_events', ['key'], unique=True, postgresql_where=sa.text("kind = 'condition' AND resolved_at IS NULL"))
    op.create_index('uq_event_once', 'radar_events', ['key'], unique=True, postgresql_where=sa.text("kind = 'once'"))
    op.create_table('registry_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inn', sa.String(length=12), nullable=False),
    sa.Column('source', sa.String(length=8), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('data_hash', sa.String(length=40), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_registry_snapshots_inn'), 'registry_snapshots', ['inn'], unique=False)
    op.create_index('ix_snap_inn_src_time', 'registry_snapshots', ['inn', 'source', 'fetched_at'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('max_user_id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=True),
    sa.Column('first_name', sa.String(length=255), nullable=True),
    sa.Column('last_name', sa.String(length=255), nullable=True),
    sa.Column('language_code', sa.String(length=32), nullable=True),
    sa.Column('photo_url', sa.String(length=2048), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_staff', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notification_settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('notifications_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('awaiting_mid', sa.String(length=64), nullable=True),
    sa.Column('awaiting_since', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_max_user_id'), 'users', ['max_user_id'], unique=True)
    op.create_table('business_profiles',
    sa.Column('inn', sa.String(length=12), nullable=False),
    sa.Column('tax_regime', sa.String(length=16), nullable=True),
    sa.Column('has_employees', sa.Boolean(), nullable=True),
    sa.Column('headcount', sa.Integer(), nullable=True),
    sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('bank_biks', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('okved_main', sa.String(length=20), nullable=True),
    sa.Column('region_code', sa.String(length=2), nullable=True),
    sa.Column('has_licenses', sa.Boolean(), nullable=True),
    sa.Column('patent_from', sa.Date(), nullable=True),
    sa.Column('patent_to', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['inn'], ['businesses.inn'], ),
    sa.PrimaryKeyConstraint('inn')
    )
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=True),
    sa.Column('template', sa.String(length=48), nullable=False),
    sa.Column('label', sa.String(length=16), nullable=False),
    sa.Column('dedup_key', sa.String(length=200), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('max_message_id', sa.String(length=64), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('keyboard', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['radar_events.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedup_key')
    )
    op.create_index(op.f('ix_notifications_scheduled_at'), 'notifications', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_table('user_businesses',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('inn', sa.String(length=12), nullable=False),
    sa.Column('connected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['inn'], ['businesses.inn'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'inn')
    )
    op.create_index(op.f('ix_user_businesses_inn'), 'user_businesses', ['inn'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_businesses_inn'), table_name='user_businesses')
    op.drop_table('user_businesses')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_scheduled_at'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_table('business_profiles')
    op.drop_index(op.f('ix_users_max_user_id'), table_name='users')
    op.drop_table('users')
    op.drop_index('ix_snap_inn_src_time', table_name='registry_snapshots')
    op.drop_index(op.f('ix_registry_snapshots_inn'), table_name='registry_snapshots')
    op.drop_table('registry_snapshots')
    op.drop_index('uq_event_once', table_name='radar_events', postgresql_where=sa.text("kind = 'once'"))
    op.drop_index('uq_event_condition_open', table_name='radar_events', postgresql_where=sa.text("kind = 'condition' AND resolved_at IS NULL"))
    op.drop_index(op.f('ix_radar_events_inn'), table_name='radar_events')
    op.drop_table('radar_events')
    op.drop_index(op.f('ix_laws_published'), table_name='laws')
    op.drop_table('laws')
    op.drop_table('businesses')
