from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .db import Base


class Household(Base):
    __tablename__ = "households"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    users = relationship("User", back_populates="household")
    bank_accounts = relationship("BankAccount", back_populates="household")
    categories = relationship("Category", back_populates="household")
    merchants = relationship("Merchant", back_populates="household")
    merchant_overrides = relationship("MerchantOverride", back_populates="household")
    category_rules = relationship("CategoryRule", back_populates="household")
    budgets = relationship("Budget", back_populates="household")
    monthly_summaries = relationship("MonthlyCategorySummary", back_populates="household")

    def __repr__(self):
        return f"<Household(id={self.id}, name='{self.name}')>"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False, index=True)
    name = Column(String)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, index=True)  # "admin" | "member" | "viewer"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="users")
    uploads = relationship("Import", back_populates="uploaded_by_user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False, index=True)
    bank_code = Column(String, index=True)  # e.g. "bofa"
    display_name = Column(String, nullable=False)
    currency = Column(String, default="USD")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="bank_accounts")
    imports = relationship("Import", back_populates="bank_account")
    transactions = relationship("Transaction", back_populates="bank_account")

    def __repr__(self):
        return f"<BankAccount(id={self.id}, display_name='{self.display_name}', bank_code='{self.bank_code}')>"


class Import(Base):
    __tablename__ = "imports"

    id = Column(Integer, primary_key=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False, index=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    original_filename = Column(String)
    stored_path = Column(String)
    bank_code = Column(String, index=True)
    statement_start_date = Column(Date, nullable=True)
    statement_end_date = Column(Date, nullable=True)
    imported_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    bank_account = relationship("BankAccount", back_populates="imports")
    uploaded_by_user = relationship("User", back_populates="uploads")
    transactions = relationship("Transaction", back_populates="import_record")

    def __repr__(self):
        return f"<Import(id={self.id}, filename='{self.original_filename}', imported={self.imported_count})>"


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("household_id", "parent_id", "name", name="uq_category_name"),
    )

    id = Column(Integer, primary_key=True)
    household_id = Column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="categories")
    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    transactions = relationship("Transaction", back_populates="category")
    merchants = relationship("Merchant", back_populates="default_category")
    merchant_overrides = relationship("MerchantOverride", back_populates="category")
    category_rules = relationship("CategoryRule", back_populates="category")
    budgets = relationship("Budget", back_populates="category")
    monthly_summaries = relationship("MonthlyCategorySummary", back_populates="category")

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint("household_id", "merchant_key", name="uq_merchant_key"),
    )

    id = Column(Integer, primary_key=True)
    household_id = Column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    merchant_key = Column(String, nullable=False, index=True)  # normalized stable key
    display_name = Column(String, nullable=False)  # human friendly name
    default_category_id = Column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    confidence = Column(Numeric(3, 2), default=1.0)  # for future ML/heuristics
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="merchants")
    default_category = relationship("Category", back_populates="merchants")
    transactions = relationship("Transaction", back_populates="merchant_ref")

    def __repr__(self):
        return f"<Merchant(id={self.id}, merchant_key='{self.merchant_key}')>"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    bank_account_id = Column(
        Integer, ForeignKey("bank_accounts.id"), nullable=False, index=True
    )
    import_id = Column(
        Integer, ForeignKey("imports.id"), nullable=False, index=True
    )
    posted_date = Column(Date, index=True)
    description = Column(String, nullable=False)
    merchant = Column(String, nullable=True, index=True)  # raw/parsed merchant
    merchant_key = Column(String, nullable=True, index=True)  # normalized key
    merchant_id = Column(
        Integer, ForeignKey("merchants.id"), nullable=True, index=True
    )
    amount = Column(Numeric(12, 2), nullable=False)
    category_id = Column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    fingerprint = Column(String, unique=True, index=True)  # used for dedupe
    is_reviewed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    bank_account = relationship("BankAccount", back_populates="transactions")
    import_record = relationship("Import", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    merchant_ref = relationship("Merchant", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, date={self.posted_date})>"


class MerchantOverride(Base):
    __tablename__ = "merchant_overrides"

    id = Column(Integer, primary_key=True)
    household_id = Column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    merchant_key = Column(String, index=True)  # normalized merchant string
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="merchant_overrides")
    category = relationship("Category", back_populates="merchant_overrides")

    def __repr__(self):
        return f"<MerchantOverride(id={self.id}, merchant_key='{self.merchant_key}')>"


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id = Column(Integer, primary_key=True)
    household_id = Column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    pattern = Column(String)  # regex or simple contains
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    priority = Column(Integer, default=100)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="category_rules")
    category = relationship("Category", back_populates="category_rules")

    def __repr__(self):
        return f"<CategoryRule(id={self.id}, pattern='{self.pattern}')>"


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "month", "category_id", name="uq_budget_month_category"
        ),
    )

    id = Column(Integer, primary_key=True)
    household_id = Column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    month = Column(Date, nullable=False, index=True)  # first day of month
    category_id = Column(
        Integer, ForeignKey("categories.id"), nullable=False, index=True
    )
    limit_amount = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="budgets")
    category = relationship("Category", back_populates="budgets")

    def __repr__(self):
        return f"<Budget(id={self.id}, month={self.month}, category_id={self.category_id})>"


class MonthlyCategorySummary(Base):
    __tablename__ = "monthly_category_summaries"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "month", "category_id", name="uq_summary_month_category"
        ),
    )

    id = Column(Integer, primary_key=True)
    household_id = Column(
        Integer, ForeignKey("households.id"), nullable=False, index=True
    )
    month = Column(Date, nullable=False, index=True)  # first day of month
    category_id = Column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )  # null = Uncategorized
    income_total = Column(Numeric(12, 2), default=0)
    expense_total = Column(Numeric(12, 2), default=0)  # absolute sum of negatives
    net_total = Column(Numeric(12, 2), default=0)  # income - expenses
    tx_count = Column(Integer, default=0)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    household = relationship("Household", back_populates="monthly_summaries")
    category = relationship("Category", back_populates="monthly_summaries")

    def __repr__(self):
        return f"<MonthlyCategorySummary(id={self.id}, month={self.month})>"
