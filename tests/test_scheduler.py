# tests/test_scheduler.py
"""
Tests for app/core/scheduler.py — the weekly pocket money payout job
and the scheduled ETF purchases job.

Split into:
  - TestCalculateAge: pure function, no DB, runs fast and always.
  - TestRunWeeklyPayout: integration tests against real Postgres,
    including a regression test for the Decimal/float TypeError that
    broke the live job after the Numeric migration.
"""
import logging
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from app.core.scheduler import (BERLIN_TZ, calculate_age,
                                run_monthly_etf_purchases, run_weekly_payout)
from app.models.shares_models import EtfPurchaseSchedule, EtfTransaction


# ---------------------------------------------------------------------
# Pure function tests — no database required
# ---------------------------------------------------------------------

class TestCalculateAge:

    def test_age_with_birthday_already_passed_this_year(self):
        birth_date = date(2016, 3, 15)
        reference = date(2026, 6, 19)  # birthday (Mar 15) already passed

        assert calculate_age(birth_date, reference) == 10

    def test_age_with_birthday_not_yet_reached_this_year(self):
        birth_date = date(2016, 12, 25)
        reference = date(2026, 6, 19)  # birthday (Dec 25) hasn't happened yet

        assert calculate_age(birth_date, reference) == 9

    def test_age_on_exact_birthday(self):
        birth_date = date(2016, 6, 19)
        reference = date(2026, 6, 19)

        assert calculate_age(birth_date, reference) == 10

    def test_age_returns_zero_for_missing_birth_date(self):
        assert calculate_age(None) == 0

    def test_age_for_newborn(self):
        birth_date = date(2026, 1, 1)
        reference = date(2026, 6, 19)

        assert calculate_age(birth_date, reference) == 0

    def test_age_birthday_still_upcoming_same_year(self):
        """
        Covers a scenario from a previous hand-written test that also
        asserted `age * 0.5 == 5.5` directly. That assertion didn't
        exercise the app at all -- it just re-proved Python float
        multiplication, and it happened to encode the exact float
        pattern that later broke production (see
        TestRunWeeklyPayout.test_payout_does_not_raise_type_error).
        This version checks only what calculate_age is actually
        responsible for: the age. Payout math is tested separately,
        against the real Decimal-based code path.
        """
        birth_date = date(2015, 11, 1)
        reference = date(2026, 2, 1)  # birthday (Nov 1) not yet reached

        assert calculate_age(birth_date, reference) == 10

    def test_age_birthday_just_passed_same_year(self):
        birth_date = date(2015, 11, 1)
        reference = date(2026, 11, 2)  # birthday (Nov 1) passed yesterday

        assert calculate_age(birth_date, reference) == 11


# ---------------------------------------------------------------------
# Integration tests — require the real Postgres test database
# ---------------------------------------------------------------------

@pytest.mark.integration
class TestRunWeeklyPayout:
    """
    NOTE: run_weekly_payout() opens its own SessionLocal() rather than
    using FastAPI's dependency-injected session, so it does NOT go
    through the db_session/app fixtures' transaction rollback -- and,
    under Postgres's READ COMMITTED isolation, it can only ever see
    rows that were *actually* committed. Children created via
    make_child/child_age_10 (bound to db_session's externally-managed,
    never-truly-committed transaction) are invisible to it. These
    tests use make_real_child/real_child_age_10 instead, which commit
    through their own independent connection so run_weekly_payout()
    can actually find and update the rows -- and clean themselves up
    for real afterward (see make_real_child in conftest.py).
    """

    def test_payout_does_not_raise_type_error(
        self, db_engine, real_child_age_10
    ):
        """
        REGRESSION: previously raised
        `TypeError: unsupported operand type(s) for +=:
        'decimal.Decimal' and 'float'`
        because payout_amount was computed as `age * 0.5` (a plain
        float) and added directly to a Decimal balance column. This
        test calls the real job function end-to-end and would have
        failed loudly against the original code.
        """
        run_weekly_payout()  # must not raise

    def test_payout_amount_is_half_age_in_euros(
        self, db_engine, real_child_age_10, db_session
    ):
        run_weekly_payout()

        from app.models.user_models import Child

        refreshed = (
            db_session.query(Child)
            .filter(Child.id == real_child_age_10.id)
            .first()
        )
        # age 10 -> 10 * 0.5 = 5.00
        assert refreshed.balance == Decimal("5.00")

    def test_payout_creates_pocket_money_transaction(
        self, db_engine, real_child_age_10, db_session
    ):
        run_weekly_payout()

        from app.models.user_models import Transaction

        txn = (
            db_session.query(Transaction)
            .filter(
                Transaction.child_id == real_child_age_10.id,
                Transaction.category == "Pocket Money",
            )
            .first()
        )
        assert txn is not None
        assert txn.amount == Decimal("5.00")
        assert "Age 10" in txn.description

    def test_payout_skips_children_without_birth_date(
        self, db_engine, make_real_child, db_session
    ):
        child = make_real_child(
            name="NoBirthDate", balance="0.00", birth_date=None
        )

        run_weekly_payout()

        from app.models.user_models import Child

        refreshed = (
            db_session.query(Child).filter(Child.id == child.id).first()
        )
        assert refreshed.balance == Decimal("0.00")

    def test_payout_accumulates_on_top_of_existing_balance(
        self, db_engine, make_real_child, db_session
    ):
        today = date.today()
        birth_date = date(today.year - 8, today.month, today.day)
        child = make_real_child(
            name="HasSavings", balance="12.34", birth_date=birth_date
        )

        run_weekly_payout()

        from app.models.user_models import Child

        refreshed = (
            db_session.query(Child).filter(Child.id == child.id).first()
        )
        # 12.34 existing + (8 * 0.5 = 4.00) = 16.34
        assert refreshed.balance == Decimal("16.34")


# ---------------------------------------------------------------------
# Scheduled ETF purchases (issues #35, #36)
#
# run_monthly_etf_purchases() takes an optional session and "now" so
# these tests can run it inside the rollback-wrapped db_session and
# pretend it is any day of the month. Yahoo prices are mocked.
# ---------------------------------------------------------------------

def _berlin(*args):
    return BERLIN_TZ.localize(datetime(*args))


@pytest.fixture
def make_schedule(db_session):
    def _make(ticker="VTI", amount="100.00", day=15, is_active=True,
              last_executed_date=None, created_at=datetime(2026, 1, 1)):
        schedule = EtfPurchaseSchedule(
            ticker_symbol=ticker, fiat_amount=Decimal(amount),
            execution_day=day, is_active=is_active,
            last_executed_date=last_executed_date, created_at=created_at)
        db_session.add(schedule)
        db_session.flush()
        return schedule

    return _make


@pytest.fixture
def prices():
    """Mocked fetch_live_prices; set prices.return_value to change."""
    with patch("app.core.scheduler.fetch_live_prices") as mock:
        mock.side_effect = lambda tickers: {t: 50.0 for t in tickers}
        yield mock


def _scheduled_buys(db_session):
    return (db_session.query(EtfTransaction)
            .filter(EtfTransaction.entry_type == "scheduled")
            .order_by(EtfTransaction.transaction_id).all())


def _run(db_session, *now):
    run_monthly_etf_purchases(db=db_session, now=_berlin(*now))
    db_session.expire_all()


class TestRunMonthlyEtfPurchases:

    def test_buys_on_due_day_and_records_execution(
            self, db_session, make_schedule, prices):
        schedule = make_schedule(day=15)

        _run(db_session, 2026, 11, 15, 9, 0)

        (buy,) = _scheduled_buys(db_session)
        assert buy.ticker_symbol == "VTI"
        assert buy.fiat_invested == Decimal("100.00")
        assert buy.shares_acquired == Decimal("2")
        assert schedule.last_executed_date == date(2026, 11, 15)

    def test_second_run_same_day_does_not_buy_again(
            self, db_session, make_schedule, prices):
        make_schedule(day=15)

        _run(db_session, 2026, 11, 15, 9, 0)
        _run(db_session, 2026, 11, 15, 9, 5)

        assert len(_scheduled_buys(db_session)) == 1

    def test_not_due_yet_does_nothing(self, db_session, make_schedule,
                                      prices):
        schedule = make_schedule(day=15)

        _run(db_session, 2026, 11, 12, 9, 0)

        assert _scheduled_buys(db_session) == []
        assert schedule.last_executed_date is None
        prices.assert_not_called()

    def test_missed_day_is_bought_late_with_warning(
            self, db_session, make_schedule, prices, caplog):
        schedule = make_schedule(day=10)

        with caplog.at_level(logging.WARNING, logger="app.core.scheduler"):
            _run(db_session, 2026, 11, 12, 9, 0)

        (buy,) = _scheduled_buys(db_session)
        assert buy.transaction_date.date() == date(2026, 11, 12)
        assert schedule.last_executed_date == date(2026, 11, 10)
        assert "late" in caplog.text and "VTI" in caplog.text

    def test_missed_day_is_caught_up_only_once(
            self, db_session, make_schedule, prices):
        make_schedule(day=10)

        _run(db_session, 2026, 11, 12, 9, 0)
        _run(db_session, 2026, 11, 13, 9, 0)
        _run(db_session, 2026, 11, 30, 9, 0)

        assert len(_scheduled_buys(db_session)) == 1

    def test_buys_again_next_month(self, db_session, make_schedule, prices):
        schedule = make_schedule(day=15,
                                 last_executed_date=date(2026, 10, 15))

        _run(db_session, 2026, 11, 15, 9, 0)

        assert len(_scheduled_buys(db_session)) == 1
        assert schedule.last_executed_date == date(2026, 11, 15)

    def test_schedule_created_after_due_day_waits_for_next_month(
            self, db_session, make_schedule, prices):
        make_schedule(day=5, created_at=datetime(2026, 11, 10, 18, 0))

        _run(db_session, 2026, 11, 12, 9, 0)

        assert _scheduled_buys(db_session) == []

    def test_inactive_schedule_is_skipped(self, db_session, make_schedule,
                                          prices):
        make_schedule(day=15, is_active=False)

        _run(db_session, 2026, 11, 15, 9, 0)

        assert _scheduled_buys(db_session) == []

    def test_price_failure_leaves_schedule_due_for_retry(
            self, db_session, make_schedule, prices):
        schedule = make_schedule(day=15)
        prices.side_effect = lambda tickers: {t: 0.0 for t in tickers}

        _run(db_session, 2026, 11, 15, 9, 0)

        assert _scheduled_buys(db_session) == []
        assert schedule.last_executed_date is None

        prices.side_effect = lambda tickers: {t: 50.0 for t in tickers}
        _run(db_session, 2026, 11, 16, 9, 0)

        assert len(_scheduled_buys(db_session)) == 1
        assert schedule.last_executed_date == date(2026, 11, 15)

    def test_existing_buy_from_before_upgrade_is_not_repeated(
            self, db_session, make_schedule, prices):
        # Before this fix last_executed_date was never written, so a
        # schedule that already bought this month has it NULL.
        schedule = make_schedule(day=1)
        db_session.add(EtfTransaction(
            ticker_symbol="VTI", fiat_invested=Decimal("100.00"),
            shares_acquired=Decimal("2"), entry_type="scheduled",
            transaction_date=datetime(2026, 11, 1, 9, 0)))
        db_session.flush()

        _run(db_session, 2026, 11, 12, 9, 0)

        assert len(_scheduled_buys(db_session)) == 1
        assert schedule.last_executed_date == date(2026, 11, 1)

    def test_older_missed_month_is_warned_not_bought(
            self, db_session, make_schedule, prices, caplog):
        make_schedule(day=15, last_executed_date=date(2026, 9, 15))

        with caplog.at_level(logging.WARNING, logger="app.core.scheduler"):
            _run(db_session, 2026, 11, 15, 9, 0)

        assert len(_scheduled_buys(db_session)) == 1
        assert "missed" in caplog.text and "2026-10-15" in caplog.text

    def test_other_schedules_buy_of_same_ticker_does_not_count(
            self, db_session, make_schedule, prices):
        # A second VTI schedule (different amount) bought on the 11th;
        # this schedule's missed buy for the 10th must still happen.
        schedule = make_schedule(day=10, amount="100.00")
        db_session.add(EtfTransaction(
            ticker_symbol="VTI", fiat_invested=Decimal("250.00"),
            shares_acquired=Decimal("5"), entry_type="scheduled",
            transaction_date=datetime(2026, 11, 11, 9, 0)))
        db_session.flush()

        _run(db_session, 2026, 11, 12, 9, 0)

        assert len(_scheduled_buys(db_session)) == 2
        assert schedule.last_executed_date == date(2026, 11, 10)
