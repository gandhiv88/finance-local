import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import BankAccount, Import, User
from ..auth.deps import get_current_user, require_roles
from ..ingest.service import ingest_import

router = APIRouter(prefix="/imports", tags=["imports"])


# Response schema
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


@router.post("", response_model=ImportOut)
async def create_import(
    file: UploadFile = File(...),
    bank_account_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> ImportOut:
    """
    Upload a PDF statement for import.
    """
    # Validate file is PDF
    filename = file.filename or ""
    content_type = file.content_type or ""
    
    if not (filename.lower().endswith(".pdf") or content_type == "application/pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed",
        )

    # Verify bank account exists and belongs to user's household
    bank_account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == bank_account_id,
            BankAccount.household_id == current_user.household_id,
        )
        .first()
    )

    if not bank_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank account not found",
        )

    # Create Import record (without stored_path initially to get the ID)
    import_record = Import(
        bank_account_id=bank_account_id,
        uploaded_by_user_id=current_user.id,
        original_filename=filename,
        bank_code=bank_account.bank_code,
        imported_count=0,
        skipped_count=0,
        warning_count=0,
    )
    db.add(import_record)
    db.flush()  # Get the import ID

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Store file with import ID as filename
    stored_path = os.path.join(settings.UPLOAD_DIR, f"{import_record.id}.pdf")
    
    try:
        content = await file.read()
        with open(stored_path, "wb") as f:
            f.write(content)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file",
        )

    # Update stored_path and commit
    import_record.stored_path = stored_path
    db.commit()

    # Trigger parsing
    try:
        ingest_import(db, import_record.id)
    except ValueError as e:
        # Parser error - update warning count and continue
        import_record.warning_count = 1
        db.commit()
        db.refresh(import_record)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse statement: {str(e)}",
        )
    except Exception:
        # Unexpected error
        import_record.warning_count = 1
        db.commit()
        db.refresh(import_record)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while parsing the statement",
        )

    db.refresh(import_record)
    return import_record


@router.get("", response_model=List[ImportOut])
def list_imports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ImportOut]:
    """
    List recent imports for the user's household.
    """
    imports = (
        db.query(Import)
        .join(BankAccount, Import.bank_account_id == BankAccount.id)
        .filter(BankAccount.household_id == current_user.household_id)
        .order_by(Import.created_at.desc())
        .limit(50)
        .all()
    )
    return imports
