from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr


# User schemas
class UserCreate(BaseModel):
    name: Optional[str] = None
    email: EmailStr
    password: str
    role: Literal["admin", "member", "viewer"] = "member"


class UserOut(BaseModel):
    id: int
    household_id: int
    name: Optional[str]
    email: str
    role: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Bank Account schemas
class BankAccountCreate(BaseModel):
    bank_code: Optional[str] = None  # e.g. "bofa"
    display_name: str
    currency: str = "USD"


class BankAccountOut(BaseModel):
    id: int
    household_id: int
    bank_code: Optional[str]
    display_name: str
    currency: str
    created_at: datetime

    class Config:
        from_attributes = True


# Admin user management schemas
class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str


# Self-service user schemas
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MeUpdateRequest(BaseModel):
    name: Optional[str] = None


# Import schemas
class ImportOut(BaseModel):
    id: int
    bank_account_id: int
    original_filename: Optional[str]
    bank_code: Optional[str]
    imported_count: int
    skipped_count: int
    warning_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# Category schemas
class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryOut(BaseModel):
    id: int
    household_id: int
    name: str
    parent_id: Optional[int]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Transaction schemas
class TransactionOut(BaseModel):
    id: int
    bank_account_id: int
    import_id: int
    posted_date: date
    description: str
    merchant: Optional[str]
    amount: Decimal
    category_id: Optional[int]
    category: Optional[CategoryOut] = None
    is_reviewed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    is_reviewed: Optional[bool] = None
    create_merchant_override: Optional[bool] = False
