import csv
import io
import os
from fastapi import (APIRouter, Depends,
                     HTTPException)
from sqlalchemy.orm import Session
from typing import List
from app.core.investments import get_portfolio_summary
from app.database.database import get_db
from app.models.shares_models import (EmployeeShare, EtfTransaction,
                                      EtfPurchaseSchedule)
import logging
from datetime import datetime


logger = logging.getLogger("app.api.investments")
SECRET_PASSWORD = os.getenv("ADMIN_PASSWORD")
shares_router = APIRouter()


@shares_router.get("/dashboard-summary")
def get_dashboard(db: Session = Depends(get_db)):
    """
    Returns aggregated data for dashboard.
    Shares (Total, Available, Pending) and EFTs (Value and Investment).
    """
    return get_portfolio_summary(db)


# --- EMPLOYEE SHARES CRUD ---

@shares_router.post("/shares/add")
def add_employee_share(
        ticker: str,
        num_shares: float,
        vest_date: str,
        purchase_price: float = 0.0,
        db: Session = Depends(get_db)
):
    try:
        parsed_vest_date = datetime.strptime(
            vest_date.strip(), "%Y-%m-%d")

        new_share = EmployeeShare(
            ticker_symbol=ticker.upper(),
            num_shares=num_shares,
            vest_date=parsed_vest_date,
            purchase_price=purchase_price
        )
        db.add(new_share)
        db.commit()
        db.refresh(new_share)
        return new_share
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD")


@shares_router.post("/shares/bulk-add")
def bulk_add_shares(data: dict, db: Session = Depends(get_db)):
    csv_text = data.get("csv_data", "")
    if not csv_text:
        raise HTTPException(status_code=400,
                            detail="No CSV data provided")

    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)

    try:
        for row in reader:
            # Handle the empty purchase_price case (e.g., the trailing comma)
            price_val = row.get('purchase_price')
            price = float(price_val) if (price_val and
                                         price_val.strip()) else 0.0

            new_share = EmployeeShare(
                ticker_symbol=row['ticker'].upper().strip(),
                num_shares=float(row['num_shares']),
                vest_date=datetime.strptime(
                    row['vest_date'].strip(), "%Y-%m-%d"),
                purchase_price=price
            )
            db.add(new_share)

        db.commit()
        return {"message": "Successfully imported shares"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400,
                            detail=f"Error parsing CSV: {str(e)}")


# --- ETF TRANSACTIONS (Manual/Ad-hoc) ---

@shares_router.post("/etf/transaction")
def record_etf_transaction(
        ticker: str,
        fiat_amount: float,
        shares_acquired: float,
        transaction_type: str = "buy",
        entry_type: str = "manual",
        db: Session = Depends(get_db)
):
    """Allows manual entry of ETF buy or sell transactions."""
    if transaction_type not in ["buy", "sell"]:
        raise HTTPException(status_code=400,
                            detail="transaction_type must be 'buy' or 'sell'")

    # For sells, shares_acquired should be negative and
    # fiat_amount should be positive (proceeds)
    if transaction_type == "sell":
        shares_acquired = -abs(shares_acquired)
        # fiat_amount remains positive for proceeds

    new_txn = EtfTransaction(
        ticker_symbol=ticker.upper(),
        fiat_invested=fiat_amount if
        transaction_type == "buy" else -fiat_amount,
        shares_acquired=shares_acquired,
        transaction_type=transaction_type,
        entry_type=entry_type,
        transaction_date=datetime.now()
    )
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)
    return new_txn


# --- ETF SCHEDULE CRUD ---

@shares_router.get("/etf/schedules", response_model=List[dict])
def get_schedules(db: Session = Depends(get_db)):
    return db.query(EtfPurchaseSchedule).all()


@shares_router.post("/etf/schedule")
def create_schedule(
        ticker: str,
        amount: float,
        day: int,
        db: Session = Depends(get_db)
):
    if not (1 <= day <= 28):
        raise HTTPException(
            status_code=400,
            detail="Day must be between 1 and 28")

    schedule = EtfPurchaseSchedule(
        ticker_symbol=ticker.upper(),
        fiat_amount=amount,
        execution_day=day
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@shares_router.delete("/etf/schedule/{schedule_id}")
def delete_schedule(schedule_id: int,
                    password: str,
                    db: Session = Depends(get_db)):
    if password != SECRET_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden")

    schedule = db.query(EtfPurchaseSchedule).filter(
        EtfPurchaseSchedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404,
                            detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return {"detail": "Schedule removed"}
