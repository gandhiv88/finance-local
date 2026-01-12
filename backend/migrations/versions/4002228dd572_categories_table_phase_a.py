"""categories table phase A

Revision ID: 4002228dd572
Revises: 81ffd451440d
Create Date: 2026-01-12 06:50:18.620790

"""
"""categories table phase A

Revision ID: <auto>
Revises: <auto>
Create Date: <auto>
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "4002228dd572"
down_revision = "81ffd451440d"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Create categories table
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("household_id", "parent_id", "name", name="uq_categories_household_parent_name"),
    )
    op.create_index("ix_categories_household_id", "categories", ["household_id"])
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_index("ix_categories_household_name", "categories", ["household_id", "name"])

    # 2) Add category_id column to transactions (nullable for now)
    op.add_column("transactions", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    op.create_foreign_key(
        "fk_transactions_category_id",
        "transactions",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3) If merchant_overrides exists and currently uses category string, add category_id (nullable for now)
    # If the table doesn't exist yet, you can skip this block and add it when you create the table.
    try:
        op.add_column("merchant_overrides", sa.Column("category_id", sa.Integer(), nullable=True))
        op.create_index("ix_merchant_overrides_category_id", "merchant_overrides", ["category_id"])
        op.create_foreign_key(
            "fk_merchant_overrides_category_id",
            "merchant_overrides",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="SET NULL",
        )
    except Exception:
        # Table might not exist yet in your schema; ignore for now
        pass

    # 4) Same for category_rules
    try:
        op.add_column("category_rules", sa.Column("category_id", sa.Integer(), nullable=True))
        op.create_index("ix_category_rules_category_id", "category_rules", ["category_id"])
        op.create_foreign_key(
            "fk_category_rules_category_id",
            "category_rules",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="SET NULL",
        )
    except Exception:
        pass


def downgrade():
    # Reverse order: drop FKs/indexes/cols, then table
    try:
        op.drop_constraint("fk_category_rules_category_id", "category_rules", type_="foreignkey")
        op.drop_index("ix_category_rules_category_id", table_name="category_rules")
        op.drop_column("category_rules", "category_id")
    except Exception:
        pass

    try:
        op.drop_constraint("fk_merchant_overrides_category_id", "merchant_overrides", type_="foreignkey")
        op.drop_index("ix_merchant_overrides_category_id", table_name="merchant_overrides")
        op.drop_column("merchant_overrides", "category_id")
    except Exception:
        pass

    op.drop_constraint("fk_transactions_category_id", "transactions", type_="foreignkey")
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_column("transactions", "category_id")

    op.drop_index("ix_categories_household_name", table_name="categories")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_index("ix_categories_household_id", table_name="categories")
    op.drop_table("categories")

