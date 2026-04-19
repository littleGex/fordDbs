# app/core/scheduler.py
import logging
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.models.user_models import Child, Transaction
from app.models.shares_models import EtfPurchaseSchedule, EtfTransaction
from app.core.investments import fetch_live_prices


logger = logging.getLogger(__name__)
BERLIN_TZ = pytz.timezone("Europe/Berlin")


def calculate_age(birth_date: date,
                  reference_date: date = None) -> int:
    """
    Calculates age.
    reference_date is used for testing, else defaults to today.
    """
    if not birth_date:
        return 0

    # Use the provided reference (for tests) or the real 'today'
    target = reference_date or date.today()

    return target.year - birth_date.year - (
            (target.month, target.day) < (birth_date.month, birth_date.day))


def run_weekly_payout():
    """Scheduled task: Runs every Friday @ 07:30"""
    db: Session = SessionLocal()
    try:
        children = db.query(Child).all()
        for child in children:
            if not child.birth_date:
                continue

            # This call is now safe because reference_date defaults to None
            age = calculate_age(child.birth_date)
            payout_amount = age * 0.5

            if payout_amount > 0:
                child.balance += payout_amount
                new_trans = Transaction(
                    child_id=child.id,
                    amount=payout_amount,
                    description=f"Weekly Pocket Money (Age {age})",
                    category="Pocket Money"
                )
                db.add(new_trans)

        db.commit()
    finally:
        db.close()


def run_monthly_etf_purchases():
    """
    Scheduled task: Runs daily to check if today is an execution day
    for any active ETF purchase schedules.
    """
    db: Session = SessionLocal()
    today_day = datetime.now(BERLIN_TZ).day

    try:
        # 1. Check for schedules set for today (e.g., the 15th)
        schedules = db.query(EtfPurchaseSchedule).filter(
            EtfPurchaseSchedule.execution_day == today_day,
            EtfPurchaseSchedule.is_active == True
        ).all()

        if not schedules:
            return

        # 2. Get unique tickers and fetch latest market prices
        tickers = {s.ticker_symbol for s in schedules}
        live_prices = fetch_live_prices(tickers)

        for schedule in schedules:
            price = live_prices.get(schedule.ticker_symbol, 0.0)

            if price > 0:
                # Calculate fractional shares: Amount / Price
                shares_acquired = float(schedule.fiat_amount) / price

                new_txn = EtfTransaction(
                    ticker_symbol=schedule.ticker_symbol,
                    fiat_invested=schedule.fiat_amount,
                    shares_acquired=shares_acquired,
                    entry_type="scheduled",
                    transaction_date=datetime.now(BERLIN_TZ)
                )
                db.add(new_txn)
                logger.info(
                    f"Executed scheduled buy: {schedule.ticker_symbol} "
                    f"({shares_acquired} shares)")
            else:
                logger.warning(
                    f"Skipped {schedule.ticker_symbol}: "
                    "Could not fetch live price.")

        db.commit()
    except Exception as e:
        logger.error(f"Error during monthly ETF purchase: {e}")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    """Initializes and starts the background scheduler."""
    scheduler = BackgroundScheduler(BERLIN_TZ)
    # Runs every Friday at 07:30
    scheduler.add_job(run_weekly_payout,
                      'cron',
                      day_of_week='fri',
                      hour=7,
                      minute=30,
                      misfire_grace_time=86400)
    # New Job: Monthly ETF Purchases
    # Runs daily at 09:00 to check if any schedules match the current day
    scheduler.add_job(run_monthly_etf_purchases,
                      'cron',
                      hour=9,
                      minute=0,
                      misfire_grace_time=86400)
    scheduler.start()
    logger.info(
        "Scheduler started with Europe/Berlin timezone.")
    logger.info(
        "Jobs: Weekly Payouts (Fri 07:30), ETF Purchases (Daily 09:00)")
