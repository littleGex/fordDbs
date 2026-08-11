# tests/test_scheduler.py
"""
Tests for app/core/scheduler.py — the weekly pocket money payout job.

Split into:
  - TestCalculateAge: pure function, no DB, runs fast and always.
  - TestRunWeeklyPayout: integration tests against real Postgres,
    including a regression test for the Decimal/float TypeError that
    broke the live job after the Numeric migration.
"""
import pytest
from datetime import date
from decimal import Decimal

from app.core.scheduler import calculate_age, run_weekly_payout


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
