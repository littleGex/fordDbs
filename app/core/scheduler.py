# app/core/scheduler.py
import logging
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, time, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.models.user_models import Child, Transaction
from app.models.shares_models import EtfPurchaseSchedule, EtfTransaction
from app.core.investments import fetch_live_prices
from app.core.price_history import ensure_price_history


logger = logging.getLogger(__name__)
BERLIN_TZ = pytz.timezone("Europe/Berlin")

# EtfTransaction.shares_acquired is NUMERIC(12, 6).
SHARES_QUANTUM = Decimal("0.000001")
# A scheduled buy still missing its price this many days after its due
# date is logged as an error rather than a warning.
PRICE_FAILURE_ERROR_DAYS = 3


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

            age = calculate_age(child.birth_date)
            payout_amount = (Decimal(age) * Decimal("0.5")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            if payout_amount > 0:
                current_balance = Decimal(str(child.balance)).quantize(
                    Decimal("0.01")
                )
                child.balance = current_balance + payout_amount

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


def _estimate_shares(fiat_amount, price: Decimal) -> Decimal:
    """Shares bought for fiat_amount at price, rounded to the
    shares_acquired column's 6 decimal places."""
    return (Decimal(fiat_amount) / price).quantize(SHARES_QUANTUM,
                                                   rounding=ROUND_HALF_UP)


def _previous_month_due_date(day: int, today: date) -> date:
    return (today.replace(day=1) - timedelta(days=1)).replace(day=day)


def _is_due_this_month(db: Session, schedule: EtfPurchaseSchedule,
                       today: date) -> bool:
    """For a schedule whose day this month has passed and that has not
    run this month: should it buy now?

    May set last_executed_date (see the upgrade case) and logs a
    warning if an earlier month was missed.
    """
    due_date = today.replace(day=schedule.execution_day)
    created = schedule.created_at.date() if schedule.created_at else None

    # A schedule set up after this month's day starts next month.
    if created and created > due_date:
        return False

    if schedule.last_executed_date is None:
        # Before last_executed_date was written, a schedule that had
        # already bought this month still has it NULL. Count that buy
        # instead of buying again.
        already_bought = db.query(EtfTransaction).filter(
            EtfTransaction.ticker_symbol == schedule.ticker_symbol,
            EtfTransaction.fiat_invested == schedule.fiat_amount,
            EtfTransaction.entry_type == "scheduled",
            EtfTransaction.transaction_date >= datetime.combine(
                due_date, time.min)
        ).first()
        if already_bought:
            schedule.last_executed_date = due_date
            return False
    else:
        prev_due = _previous_month_due_date(schedule.execution_day, today)
        if (schedule.last_executed_date < prev_due
                and not (created and created > prev_due)):
            logger.warning(
                f"Scheduled buy for {schedule.ticker_symbol} missed: "
                f"due {prev_due} (last made {schedule.last_executed_date})"
                ". Only this month is caught up; add it by hand if needed.")

    return True


def run_monthly_etf_purchases(db: Session = None, now: datetime = None):
    """
    Scheduled task: runs daily and makes each active schedule's buy
    for this month once its execution_day has arrived.

    - A buy is due once this month's execution_day has passed and the
      schedule has not run this month (last_executed_date). A day the
      Pi was down is therefore caught up on the next run, with a
      warning that it is late.
    - last_executed_date is set to this month's due date in the same
      commit as the buy, and the due schedules are locked while the
      job runs, so a second run (restart, misfire catch-up) does not
      buy again.
    - If no price can be fetched the schedule stays due and the next
      daily run retries. From PRICE_FAILURE_ERROR_DAYS after the due
      date this is logged as an error instead of a warning.
    - Only this month is caught up; an earlier missed month is logged
      as a warning, not bought.
    - The rows are estimates: shares come from Yahoo's latest close,
      not the broker's real fill price, and fees are 0. They are kept
      as entry_type="scheduled" so a later import of the real fills
      (#39) can find and replace them.

    db and now are for tests; the scheduler calls this with neither.
    """
    own_session = db is None
    db = db or SessionLocal()
    now = now or datetime.now(BERLIN_TZ)
    today = now.date()
    month_start = today.replace(day=1)

    try:
        candidates = db.query(EtfPurchaseSchedule).filter(
            EtfPurchaseSchedule.is_active.is_(True),
            EtfPurchaseSchedule.execution_day <= today.day,
            or_(EtfPurchaseSchedule.last_executed_date.is_(None),
                EtfPurchaseSchedule.last_executed_date < month_start)
        ).with_for_update().all()

        schedules = [s for s in candidates
                     if _is_due_this_month(db, s, today)]

        live_prices = (fetch_live_prices(
            {s.ticker_symbol for s in schedules}) if schedules else {})

        for schedule in schedules:
            due_date = today.replace(day=schedule.execution_day)
            price = live_prices.get(schedule.ticker_symbol, 0.0)

            price = Decimal(str(price))
            if price.is_finite() and price > 0:
                shares_acquired = _estimate_shares(schedule.fiat_amount,
                                                   price)

                new_txn = EtfTransaction(
                    ticker_symbol=schedule.ticker_symbol,
                    fiat_invested=schedule.fiat_amount,
                    shares_acquired=shares_acquired,
                    entry_type="scheduled",
                    transaction_date=now,
                    # Linked like its schedule, so a later ticker change
                    # for the ISIN renames this row too.
                    isin=schedule.isin
                )
                db.add(new_txn)
                schedule.last_executed_date = due_date
                logger.info(
                    f"Executed scheduled buy: {schedule.ticker_symbol} "
                    f"({shares_acquired} shares)")
                if today > due_date:
                    logger.warning(
                        f"Scheduled buy for {schedule.ticker_symbol} "
                        f"made late: due {due_date}, bought {today}.")
            elif (today - due_date).days >= PRICE_FAILURE_ERROR_DAYS:
                logger.error(
                    f"Scheduled buy for {schedule.ticker_symbol} due "
                    f"{due_date} still not made "
                    f"{(today - due_date).days} days later: no live "
                    "price. Will keep retrying; check the price source "
                    "or add it by hand.")
            else:
                logger.warning(
                    f"Skipped {schedule.ticker_symbol}: "
                    "Could not fetch live price; will retry on the "
                    "next run.")

        db.commit()
    except Exception as e:
        logger.error(f"Error during monthly ETF purchase: {e}")
        db.rollback()
    finally:
        if own_session:
            db.close()


def run_price_history_refresh(db: Session = None):
    """Fetch yesterday's closes for the portfolio history chart (#52),
    so the dashboard rarely waits on Yahoo."""
    own_session = db is None
    db = db or SessionLocal()
    try:
        stale = ensure_price_history(db)
        db.commit()
        if stale:
            logger.warning("Price history not up to date for %s",
                           sorted(stale))
    except Exception:
        db.rollback()
        logger.exception("Price history refresh failed")
    finally:
        if own_session:
            db.close()


def start_scheduler():
    """Initializes and starts the background scheduler."""
    scheduler = BackgroundScheduler(timezone=BERLIN_TZ)
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
    # Daily 06:00: cache yesterday's closes for the portfolio history
    scheduler.add_job(run_price_history_refresh,
                      'cron',
                      hour=6,
                      minute=0,
                      misfire_grace_time=86400)
    scheduler.start()
    logger.info(
        "Scheduler started with Europe/Berlin timezone.")
    logger.info(
        "Jobs: Weekly Payouts (Fri 07:30), ETF Purchases (Daily 09:00)")
