from sqlalchemy import (Column, Integer, String, DateTime, Numeric,
                        Boolean, func, Date, Text, ForeignKey, false)
from app.database.database import Base


class EmployeeShare(Base):
    __tablename__ = "employee_shares"

    share_id = Column(Integer, primary_key=True, index=True)
    ticker_symbol = Column(String, nullable=False, index=True)
    grant_date = Column(DateTime, server_default=func.now())
    vest_date = Column(DateTime, nullable=False, index=True)

    # Using Numeric(precision, scale) for financial accuracy
    num_shares = Column(Numeric(12, 4), nullable=False)
    purchase_price = Column(Numeric(10, 2), default=0.0)


class EtfTransaction(Base):
    __tablename__ = "etf_transactions"

    transaction_id = Column(Integer, primary_key=True, index=True)
    ticker_symbol = Column(String, nullable=False, index=True)
    transaction_date = Column(DateTime, server_default=func.now())
    transaction_type = Column(String, default="buy")  # 'buy' or 'sell'

    fiat_invested = Column(Numeric(
        10, 2), nullable=False)  # Positive for buy, negative for sell
    shares_acquired = Column(Numeric(
        12, 6), nullable=False)  # Positive for buy, negative for sell
    fees = Column(Numeric(10, 2), default=0.0)

    # ISIN this row belongs to (see Instrument); NULL for rows that
    # were never linked. ticker_symbol is kept in sync with the
    # instrument's yahoo_ticker.
    isin = Column(String(12), ForeignKey("instruments.isin"),
                  nullable=True, index=True)

    # Trade Republic transaction_id, or "liquidation:<ISIN>" for a
    # netted liquidation sell; NULL for rows not imported from an
    # export. Unique, so a re-import skips rows already stored.
    external_id = Column(String, nullable=True, unique=True)

    # Track how the entry was created: "manual", "import" (CSV) or
    # "scheduled". Scheduled rows are estimates (Yahoo close price, no
    # fees), not the broker's real fill; see run_monthly_etf_purchases.
    entry_type = Column(String, default="manual")


class EtfPurchaseSchedule(Base):
    __tablename__ = "etf_purchase_schedule"

    schedule_id = Column(Integer, primary_key=True, index=True)
    ticker_symbol = Column(String, nullable=False)
    fiat_amount = Column(Numeric(10, 2), nullable=False)

    # Day of month (1-28) to avoid leap year/short month issues
    execution_day = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)

    last_executed_date = Column(Date, nullable=True)

    isin = Column(String(12), ForeignKey("instruments.isin"),
                  nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())


class Instrument(Base):
    """A fund or stock, keyed by ISIN, with the Yahoo ticker used to
    price it (see app/core/instruments.py)."""
    __tablename__ = "instruments"

    isin = Column(String(12), primary_key=True)
    # NULL means unresolved: no EUR listing found or checked yet.
    yahoo_ticker = Column(String, nullable=True)
    name = Column(String, nullable=True)
    # Currency Yahoo reports for yahoo_ticker; always EUR when set.
    currency = Column(String(3), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    # Set by hand in the admin panel; automatic lookups never change it.
    manual_override = Column(Boolean, nullable=False, default=False,
                             server_default=false())
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class PriceHistory(Base):
    """Unadjusted daily close (EUR) per Yahoo ticker, for the portfolio
    history chart. Only finished days are stored."""
    __tablename__ = "price_history"

    ticker = Column(String, primary_key=True)
    day = Column(Date, primary_key=True)
    close = Column(Numeric(14, 6), nullable=False)
    fetched_at = Column(DateTime, server_default=func.now())


class PriceFetchState(Base):
    """How far each ticker's closes have been fetched, so days without a
    close (weekends, holidays) aren't asked for again."""
    __tablename__ = "price_fetch_state"

    ticker = Column(String, primary_key=True)
    fetched_through = Column(Date, nullable=False)
