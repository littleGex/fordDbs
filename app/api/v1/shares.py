import csv
import io
from fastapi import (APIRouter, Depends,
                     HTTPException)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.investments import get_portfolio_summary
from app.database.database import get_db
from app.models.shares_models import (EmployeeShare, EtfTransaction,
                                      EtfPurchaseSchedule)
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation


logger = logging.getLogger("app.api.investments")
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
        transaction_date: Optional[str] = None,
        fees: float = 0.0,
        db: Session = Depends(get_db)
):
    """Allows manual entry of ETF buy or sell transactions.

    transaction_date is YYYY-MM-DD and defaults to now.
    """
    if transaction_type not in ["buy", "sell"]:
        raise HTTPException(status_code=400,
                            detail="transaction_type must be 'buy' or 'sell'")
    if fees < 0:
        raise HTTPException(status_code=400,
                            detail="fees must not be negative")
    if transaction_date:
        try:
            txn_date = _parse_etf_date(transaction_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid transaction_date. Use YYYY-MM-DD")
    else:
        txn_date = datetime.now()

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
        transaction_date=txn_date,
        fees=fees
    )
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)
    return new_txn


# --- ETF TRANSACTIONS (CSV bulk import) ---

ETF_CSV_REQUIRED_COLUMNS = ("ticker", "fiat_amount", "shares_acquired",
                            "transaction_date")


def _parse_etf_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d")


def _parse_etf_decimal(value: str, field: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"invalid {field} {value!r}")
    if not number.is_finite():
        raise ValueError(f"invalid {field} {value!r}")
    return number


def _parse_etf_csv_row(row: dict) -> EtfTransaction:
    """Turn one CSV row into an EtfTransaction; ValueError if invalid.

    The sign of fiat_amount and shares_acquired comes from
    transaction_type, not the CSV: buys are stored positive and sells
    negative, as in record_etf_transaction.
    """
    def cell(name):
        return (row.get(name) or "").strip()

    ticker = cell("ticker").upper()
    if not ticker:
        raise ValueError("ticker is empty")

    transaction_type = (cell("transaction_type") or "buy").lower()
    if transaction_type not in ("buy", "sell"):
        raise ValueError(
            f"transaction_type must be 'buy' or 'sell', got "
            f"{cell('transaction_type')!r}")

    fiat = abs(_parse_etf_decimal(cell("fiat_amount"), "fiat_amount"))
    shares = abs(_parse_etf_decimal(cell("shares_acquired"),
                                    "shares_acquired"))
    fees = _parse_etf_decimal(cell("fees") or "0", "fees")
    if fees < 0:
        raise ValueError("fees must not be negative")

    try:
        txn_date = _parse_etf_date(cell("transaction_date"))
    except ValueError:
        raise ValueError(
            f"invalid transaction_date {cell('transaction_date')!r}, "
            "use YYYY-MM-DD")

    sign = 1 if transaction_type == "buy" else -1
    return EtfTransaction(
        ticker_symbol=ticker,
        fiat_invested=sign * fiat,
        shares_acquired=sign * shares,
        fees=fees,
        transaction_type=transaction_type,
        entry_type="import",
        transaction_date=txn_date,
    )


@shares_router.post("/etf/bulk-add")
def bulk_add_etf_transactions(data: dict, db: Session = Depends(get_db)):
    """Import ETF transactions from CSV in one all-or-nothing transaction.

    Header row required. Columns: ticker, fiat_amount, shares_acquired,
    transaction_date (YYYY-MM-DD), and optionally fees (default 0) and
    transaction_type (buy/sell, default buy). Other columns are ignored.
    """
    csv_text = data.get("csv_data") or ""
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise HTTPException(status_code=400,
                            detail="No CSV data provided")

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    reader.fieldnames = [name.strip().lower()
                         for name in reader.fieldnames]
    missing = [c for c in ETF_CSV_REQUIRED_COLUMNS
               if c not in reader.fieldnames]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing column(s): {', '.join(missing)}")

    transactions = []
    for row in reader:
        try:
            transactions.append(_parse_etf_csv_row(row))
        except ValueError as e:
            # line_num counts the header, so it matches the line the
            # user sees in their file.
            raise HTTPException(status_code=400,
                                detail=f"row {reader.line_num}: {e}")

    if not transactions:
        raise HTTPException(status_code=400,
                            detail="No rows to import")

    try:
        db.add_all(transactions)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("ETF CSV import failed while saving")
        raise HTTPException(
            status_code=400,
            detail="Could not save the import (a value may be too large); "
                   "nothing was imported")

    return {"imported": len(transactions)}


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
                    db: Session = Depends(get_db)):
    schedule = db.query(EtfPurchaseSchedule).filter(
        EtfPurchaseSchedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404,
                            detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return {"detail": "Schedule removed"}


@shares_router.patch("/shares/update-ticker")
def update_ticker(old_ticker: str,
                  new_ticker: str,
                  db: Session = Depends(get_db)):
    shares = db.query(EmployeeShare).filter(
        EmployeeShare.ticker_symbol == old_ticker.upper()).all()
    if not shares:
        raise HTTPException(status_code=404,
                            detail="Ticker not found")

    for share in shares:
        share.ticker_symbol = new_ticker.upper()

    db.commit()
    return {"message": f"Updated {len(shares)} records to {new_ticker}"}
