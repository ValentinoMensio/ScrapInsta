"""create profiles, reels, profile_analysis

Revision ID: 20251013_0002
Revises: 20251011_0001
Create Date: 2025-10-13 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251013_0002"
down_revision = "20251011_0001"
branch_labels = None
depends_on = None


def upgrade():
    # profiles
    op.create_table(
        "profiles",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),

        sa.Column("followers", sa.BigInteger(), nullable=True),
        sa.Column("followings", sa.BigInteger(), nullable=True),
        sa.Column("posts", sa.BigInteger(), nullable=True),

        sa.Column("is_verified", sa.Boolean(), nullable=True),
        sa.Column("privacy", sa.String(length=32), nullable=True),  # 'public'|'private'|'unknown'
        sa.Column("account_type", sa.String(length=32), nullable=True),  # opcional

        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("username", name="uq_profiles_username"),
    )
    op.create_index("ix_profiles_username", "profiles", ["username"], unique=True)

    # reels
    op.create_table(
        "reels",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),               # shortcode
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(), nullable=True),

        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("profile_id", "code", name="uq_reels_profile_code"),
    )
    op.create_index("ix_reels_profile", "reels", ["profile_id"], unique=False)
    op.create_index("ix_reels_code", "reels", ["code"], unique=False)

    # profile_analysis (traza del análisis)
    op.create_table(
        "profile_analysis",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),  # 'selenium'|'cache'|'api'
        sa.Column("rubro", sa.String(length=255), nullable=True),

        # snapshots rápidos
        sa.Column("engagement_score", sa.Float(), nullable=True),
        sa.Column("success_score", sa.Float(), nullable=True),

        sa.Column("analyzed_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_profile_analysis_profile", "profile_analysis", ["profile_id"], unique=False)


def downgrade():
    op.drop_index("ix_profile_analysis_profile", table_name="profile_analysis")
    op.drop_table("profile_analysis")

    op.drop_index("ix_reels_code", table_name="reels")
    op.drop_index("ix_reels_profile", table_name="reels")
    op.drop_table("reels")

    op.drop_index("ix_profiles_username", table_name="profiles")
    op.drop_table("profiles")
