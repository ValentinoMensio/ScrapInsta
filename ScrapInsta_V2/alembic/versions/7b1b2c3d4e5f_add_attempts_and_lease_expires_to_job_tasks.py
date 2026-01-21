"""add_attempts_and_lease_expires_to_job_tasks

Revision ID: 7b1b2c3d4e5f
Revises: cd727dba1590
Create Date: 2026-01-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b1b2c3d4e5f"
down_revision: Union[str, None] = "cd727dba1590"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Para idempotencia en consumer + tasks largas:
    # - attempts: cuántas veces se leaseó/reclamó la task
    # - lease_expires_at: deadline explícito (NOW()+TTL) para reclaim y prevención de doble-trabajo
    # - leased_by: quién está procesando (idempotencia ante doble delivery inevitable)
    op.add_column("job_tasks", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("job_tasks", sa.Column("lease_expires_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("job_tasks", sa.Column("leased_by", sa.String(length=128), nullable=True))

    op.create_index(
        "idx_job_tasks_status_lease_expires",
        "job_tasks",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_job_tasks_status_lease_expires", table_name="job_tasks")
    op.drop_column("job_tasks", "leased_by")
    op.drop_column("job_tasks", "lease_expires_at")
    op.drop_column("job_tasks", "attempts")


