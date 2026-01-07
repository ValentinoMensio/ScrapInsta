"""add_lease_ttl_to_job_tasks

Revision ID: cd727dba1590
Revises: 075fb1b4ff0e
Create Date: 2026-01-06 20:51:34.433516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd727dba1590'
down_revision: Union[str, None] = '075fb1b4ff0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('job_tasks', sa.Column('leased_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('job_tasks', sa.Column('lease_ttl', sa.Integer(), nullable=True, server_default='300'))
    
    op.create_index(
        'idx_job_tasks_status_leased',
        'job_tasks',
        ['status', 'leased_at'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_job_tasks_status_leased', table_name='job_tasks')
    op.drop_column('job_tasks', 'lease_ttl')
    op.drop_column('job_tasks', 'leased_at')
