from sqlalchemy import (Column, Integer, String, DateTime, Numeric,
                        Boolean, func, Date)
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

    fiat_invested = Column(Numeric(10, 2), nullable=False)  # Positive for buy, negative for sell
    shares_acquired = Column(Numeric(12, 6), nullable=False)  # Positive for buy, negative for sell
    fees = Column(Numeric(10, 2), default=0.0)

    # Track how the entry was created
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

    created_at = Column(DateTime, server_default=func.now())
