"""Key the CORE tables by (store_id, shoper id) so two shops can't overwrite each other.

Revision ID: 0002_store_scoped_core_keys
Revises: 0001_baseline
Create Date: 2026-09-29

Shoper numbers orders, products, customers, categories and order lines per shop, so shop A's
order #100 and shop B's order #100 share an id. The CORE tables were keyed by that id alone and
the transform upserts ON CONFLICT (<id>), so the second shop silently overwrote the first.

fact_order_items and dim_categories had no store_id at all; it is added and backfilled from the
parent order / the RAW categories. Existing rows are kept, so no re-transform is needed.

Downgrade restores the single-column keys and fails if two shops already share an id.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_store_scoped_core_keys"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# table -> shoper id column
SIMPLE_KEYS = {
    "fact_orders": "order_id",
    "dim_products": "product_id",
    "dim_customers": "customer_id",
}


def upgrade() -> None:
    # Foreign keys point at the old single-column keys, so they go first.
    op.drop_constraint("fact_order_items_order_id_fkey", "fact_order_items", type_="foreignkey")
    op.drop_constraint("dim_categories_parent_id_fkey", "dim_categories", type_="foreignkey")

    for table, id_col in SIMPLE_KEYS.items():
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, ["store_id", id_col])

    # fact_order_items: every line belongs to an existing order (the FK guaranteed it).
    op.add_column("fact_order_items", sa.Column("store_id", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE fact_order_items i SET store_id = o.store_id
        FROM fact_orders o WHERE o.order_id = i.order_id
    """)
    op.alter_column("fact_order_items", "store_id", nullable=False)
    op.create_foreign_key(
        "fact_order_items_store_id_fkey", "fact_order_items", "stores", ["store_id"], ["id"])
    op.create_index(op.f("ix_fact_order_items_store_id"), "fact_order_items", ["store_id"])
    op.drop_constraint("fact_order_items_pkey", "fact_order_items", type_="primary")
    op.create_primary_key("fact_order_items_pkey", "fact_order_items", ["store_id", "order_item_id"])
    op.create_foreign_key(
        "fact_order_items_order_fkey", "fact_order_items", "fact_orders",
        ["store_id", "order_id"], ["store_id", "order_id"])

    # dim_categories: take the shop from the RAW row it was built from. A category with no RAW row
    # left is stale and would be rebuilt by the next transform anyway, so it is dropped.
    op.add_column("dim_categories", sa.Column("store_id", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE dim_categories d SET store_id = r.store_id
        FROM raw_categories r WHERE r.category_id = d.category_id
    """)
    op.execute("DELETE FROM dim_categories WHERE store_id IS NULL")
    op.execute("""
        UPDATE dim_categories c SET parent_id = NULL
        WHERE parent_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM dim_categories p
            WHERE p.store_id = c.store_id AND p.category_id = c.parent_id
        )
    """)
    op.alter_column("dim_categories", "store_id", nullable=False)
    op.create_foreign_key(
        "dim_categories_store_id_fkey", "dim_categories", "stores", ["store_id"], ["id"])
    op.create_index(op.f("ix_dim_categories_store_id"), "dim_categories", ["store_id"])
    op.drop_constraint("dim_categories_pkey", "dim_categories", type_="primary")
    op.create_primary_key("dim_categories_pkey", "dim_categories", ["store_id", "category_id"])
    op.create_foreign_key(
        "dim_categories_parent_fkey", "dim_categories", "dim_categories",
        ["store_id", "parent_id"], ["store_id", "category_id"])


def downgrade() -> None:
    op.drop_constraint("dim_categories_parent_fkey", "dim_categories", type_="foreignkey")
    op.drop_constraint("dim_categories_pkey", "dim_categories", type_="primary")
    op.create_primary_key("dim_categories_pkey", "dim_categories", ["category_id"])
    op.drop_index(op.f("ix_dim_categories_store_id"), table_name="dim_categories")
    op.drop_constraint("dim_categories_store_id_fkey", "dim_categories", type_="foreignkey")
    op.drop_column("dim_categories", "store_id")
    op.create_foreign_key(
        "dim_categories_parent_id_fkey", "dim_categories", "dim_categories",
        ["parent_id"], ["category_id"])

    op.drop_constraint("fact_order_items_order_fkey", "fact_order_items", type_="foreignkey")
    op.drop_constraint("fact_order_items_pkey", "fact_order_items", type_="primary")
    op.create_primary_key("fact_order_items_pkey", "fact_order_items", ["order_item_id"])
    op.drop_index(op.f("ix_fact_order_items_store_id"), table_name="fact_order_items")
    op.drop_constraint("fact_order_items_store_id_fkey", "fact_order_items", type_="foreignkey")
    op.drop_column("fact_order_items", "store_id")

    for table, id_col in SIMPLE_KEYS.items():
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, [id_col])

    op.create_foreign_key(
        "fact_order_items_order_id_fkey", "fact_order_items", "fact_orders",
        ["order_id"], ["order_id"])
