# app/api/v1/tr_import.py
"""
Trade Republic export import (#45). Mounted under /v1/investments,
parents only (see app/main.py).
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.tr_import import ImportSaveError, import_tr_export
from app.database.database import get_db

tr_import_router = APIRouter()

# A year of monthly savings plans is a few tens of KB.
MAX_IMPORT_BYTES = 5 * 1024 * 1024


class TrImportRequest(BaseModel):
    csv_data: str
    dry_run: bool = False


@tr_import_router.post("/etf/import/trade-republic")
def import_trade_republic(body: TrImportRequest,
                          db: Session = Depends(get_db)):
    """Import a Trade Republic transaction export. Rows already
    imported are skipped; with dry_run nothing is stored."""
    if len(body.csv_data.encode()) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413,
                            detail="Export is larger than 5 MB")
    try:
        result = import_tr_export(db, body.csv_data, dry_run=body.dry_run)
    except (ValueError, ImportSaveError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return asdict(result)
