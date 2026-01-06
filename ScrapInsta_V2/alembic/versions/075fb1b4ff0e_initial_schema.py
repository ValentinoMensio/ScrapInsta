"""initial_schema

Revision ID: 075fb1b4ff0e
Revises: 
Create Date: 2026-01-05 18:46:28.182711

Schema inicial consolidado con sistema multi-tenant completo.
Incluye: clients, client_limits, y client_id en todas las tablas desde el inicio.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '075fb1b4ff0e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================
    # Clientes (Multi-Tenant)
    # =========================
    op.create_table(
        'clients',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('api_key_hash', sa.String(length=255), nullable=False),
        sa.Column('status', sa.Enum('active', 'suspended', 'deleted', name='client_status'), nullable=False, server_default='active'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('idx_clients_status', 'clients', ['status'], unique=False)

    op.create_table(
        'client_limits',
        sa.Column('client_id', sa.String(length=64), nullable=False),
        sa.Column('requests_per_minute', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('requests_per_hour', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('requests_per_day', sa.Integer(), nullable=False, server_default='10000'),
        sa.Column('messages_per_day', sa.Integer(), nullable=False, server_default='500'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('client_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # =========================
    # Perfiles analizados
    # =========================
    op.create_table(
        'profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('followers', sa.Integer(), nullable=True),
        sa.Column('followings', sa.Integer(), nullable=True),
        sa.Column('posts', sa.Integer(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('privacy', sa.Enum('public', 'private', 'unknown', name='privacy'), nullable=True, server_default='unknown'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )
    op.create_index('ix_profiles_username', 'profiles', ['username'], unique=False)
    op.create_index('idx_profiles_updated_at', 'profiles', ['updated_at'], unique=False)

    op.create_table('profile_analysis',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('rubro', sa.String(length=128), nullable=True),
        sa.Column('engagement_score', sa.Float(), nullable=True),
        sa.Column('success_score', sa.Float(), nullable=True),
        sa.Column('analyzed_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4'
    )
    op.create_index('idx_profile_analysis_profile_id', 'profile_analysis', ['profile_id'], unique=False)
    op.create_index('idx_profile_analysis_analyzed_at', 'profile_analysis', ['analyzed_at'], unique=False)

    # =========================
    # Seguimientos de perfiles
    # =========================
    op.create_table('followings',
        sa.Column('username_origin', sa.String(length=64), nullable=False),
        sa.Column('username_target', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('username_origin', 'username_target'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('ix_followings_origin', 'followings', ['username_origin'], unique=False)
    op.create_index('ix_followings_target', 'followings', ['username_target'], unique=False)
    op.create_index('idx_followings_created_at', 'followings', ['created_at'], unique=False)

    # ============================================
    # Job Store (con client_id desde el inicio)
    # ============================================
    op.create_table('jobs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('batch_size', sa.Integer(), nullable=False),
        sa.Column('extra_json', sa.JSON(), nullable=True),
        sa.Column('total_items', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'done', 'error', name='job_status'), nullable=False, server_default='pending'),
        sa.Column('client_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('idx_jobs_status_created', 'jobs', ['status', 'created_at'], unique=False)
    op.create_index('idx_jobs_status_updated', 'jobs', ['status', 'updated_at'], unique=False)
    op.create_index('idx_jobs_client_status', 'jobs', ['client_id', 'status'], unique=False)
    op.create_index('idx_jobs_client_created', 'jobs', ['client_id', 'created_at'], unique=False)

    op.create_table('job_tasks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=191), nullable=False),
        sa.Column('task_id', sa.String(length=191), nullable=False),
        sa.Column('correlation_id', sa.String(length=191), nullable=True),
        sa.Column('account_id', sa.String(length=191), nullable=True),
        sa.Column('username', sa.String(length=191), nullable=True),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('status', sa.Enum('queued', 'sent', 'ok', 'error', name='task_status'), nullable=True, server_default='queued'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.Column('client_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True, onupdate=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('sent_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('finished_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id', name='uk_task_id'),
        sa.UniqueConstraint('job_id', 'username', 'account_id', name='uk_job_username_account'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('idx_job_tasks_account_status_created', 'job_tasks', ['account_id', 'status', 'created_at'], unique=False)
    op.create_index('idx_job_tasks_job_status', 'job_tasks', ['job_id', 'status'], unique=False)
    op.create_index('idx_job_tasks_job_task', 'job_tasks', ['job_id', 'task_id'], unique=False)
    op.create_index('idx_job_tasks_job_id', 'job_tasks', ['job_id'], unique=False)
    op.create_index('idx_job_tasks_status_created', 'job_tasks', ['status', 'created_at'], unique=False)
    op.create_index('idx_job_tasks_status_finished', 'job_tasks', ['status', 'finished_at'], unique=False)
    op.create_index('idx_job_tasks_client_status', 'job_tasks', ['client_id', 'status'], unique=False)
    op.create_index('idx_job_tasks_client_created', 'job_tasks', ['client_id', 'created_at'], unique=False)

    op.create_table(
        'messages_sent',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('client_username', sa.String(length=191), nullable=False),
        sa.Column('client_id', sa.String(length=64), nullable=False),
        sa.Column('dest_username', sa.String(length=191), nullable=False),
        sa.Column('job_id', sa.String(length=191), nullable=True),
        sa.Column('task_id', sa.String(length=191), nullable=True),
        sa.Column('last_sent_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_username', 'dest_username', name='uq_messages_sent_client_dest'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_index('idx_messages_sent_dest', 'messages_sent', ['dest_username'], unique=False)
    op.create_index('idx_messages_sent_client', 'messages_sent', ['client_username'], unique=False)
    op.create_index('idx_messages_sent_last_sent', 'messages_sent', ['last_sent_at'], unique=False)
    op.create_index('idx_messages_sent_client_id', 'messages_sent', ['client_id'], unique=False)
    op.create_index('idx_messages_sent_client_id_dest', 'messages_sent', ['client_id', 'dest_username'], unique=False)

    # Cliente por defecto
    op.execute("""
        INSERT INTO clients (id, name, email, api_key_hash, status)
        VALUES ('default', 'Default Client', NULL, '', 'active')
        ON DUPLICATE KEY UPDATE id=id
    """)


def downgrade() -> None:
    op.drop_index('idx_messages_sent_client_id_dest', table_name='messages_sent')
    op.drop_index('idx_messages_sent_client_id', table_name='messages_sent')
    op.drop_index('idx_messages_sent_last_sent', table_name='messages_sent')
    op.drop_index('idx_messages_sent_client', table_name='messages_sent')
    op.drop_index('idx_messages_sent_dest', table_name='messages_sent')
    op.drop_table('messages_sent')
    
    op.drop_index('idx_job_tasks_client_created', table_name='job_tasks')
    op.drop_index('idx_job_tasks_client_status', table_name='job_tasks')
    op.drop_index('idx_job_tasks_status_finished', table_name='job_tasks')
    op.drop_index('idx_job_tasks_status_created', table_name='job_tasks')
    op.drop_index('idx_job_tasks_job_id', table_name='job_tasks')
    op.drop_index('idx_job_tasks_job_task', table_name='job_tasks')
    op.drop_index('idx_job_tasks_job_status', table_name='job_tasks')
    op.drop_index('idx_job_tasks_account_status_created', table_name='job_tasks')
    op.drop_table('job_tasks')
    
    op.drop_index('idx_jobs_client_created', table_name='jobs')
    op.drop_index('idx_jobs_client_status', table_name='jobs')
    op.drop_index('idx_jobs_status_updated', table_name='jobs')
    op.drop_index('idx_jobs_status_created', table_name='jobs')
    op.drop_table('jobs')
    
    op.drop_index('idx_followings_created_at', table_name='followings')
    op.drop_index('ix_followings_target', table_name='followings')
    op.drop_index('ix_followings_origin', table_name='followings')
    op.drop_table('followings')
    
    try:
        op.drop_index('idx_profile_analysis_analyzed_at', table_name='profile_analysis')
    except Exception:
        pass
    op.drop_index('idx_profile_analysis_profile_id', table_name='profile_analysis')
    op.drop_table('profile_analysis')
    
    op.drop_index('idx_profiles_updated_at', table_name='profiles')
    op.drop_index('ix_profiles_username', table_name='profiles')
    op.drop_table('profiles')
    
    op.drop_table('client_limits')
    op.drop_index('idx_clients_status', table_name='clients')
    op.drop_table('clients')

