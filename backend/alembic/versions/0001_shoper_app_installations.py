"""shoper_app_installations table (App Store OAuth installations)

Revision ID: 0001_shoper_app_installations
Revises:
Create Date: 2026-07-12

The rest of the schema is still managed by Base.metadata.create_all at app
startup; this migration guards with has_table so both paths coexist.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_shoper_app_installations"
down_revision = None
branch_labels = None
depends_on = None

TABLE = "shoper_app_installations"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "store_id",
            sa.Integer(),
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shoper_shop_id", sa.String(length=128), nullable=False),
        sa.Column("shop_url", sa.String(length=255), nullable=False),
        sa.Column("application_code", sa.String(length=128), nullable=True),
        sa.Column("application_version", sa.Integer(), nullable=True),
        sa.Column("trial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uninstalled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_auth_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("store_id", name="uq_shoper_app_installations_store_id"),
        sa.UniqueConstraint(
            "shoper_shop_id", name="uq_shoper_app_installations_shoper_shop_id"
        ),
    )
    op.create_index(
        "ix_shoper_app_installations_store_id", TABLE, ["store_id"]
    )
    op.create_index(
        "ix_shoper_app_installations_shoper_shop_id", TABLE, ["shoper_shop_id"]
    )
    op.create_index("ix_shoper_app_installations_status", TABLE, ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE):
        op.drop_table(TABLE)
