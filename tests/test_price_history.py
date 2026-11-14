"""
Tests for the daily price cache behind the portfolio history chart (#52):
the tables and ensure_price_history in app/core/price_history.py.

No network: the yfinance download is replaced by a fake.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.shares_models import PriceFetchState, PriceHistory


class TestTables:

    def test_close_is_stored_per_ticker_and_day(self, db_session):
        db_session.add_all([
            PriceHistory(ticker="EUNL.DE", day=date(2026, 3, 2),
                         close=Decimal("100.5")),
            PriceHistory(ticker="EUNL.DE", day=date(2026, 3, 3),
                         close=Decimal("101.25"))])
        db_session.flush()
        closes = [r.close for r in db_session.query(PriceHistory)
                  .order_by(PriceHistory.day)]
        assert closes == [Decimal("100.500000"), Decimal("101.250000")]

    def test_same_ticker_and_day_twice_is_rejected(self, db_session):
        for _ in range(2):
            db_session.add(PriceHistory(ticker="EUNL.DE",
                                        day=date(2026, 3, 2),
                                        close=Decimal("1")))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_fetch_state_round_trip(self, db_session):
        db_session.add(PriceFetchState(ticker="EUNL.DE",
                                       fetched_through=date(2026, 3, 9)))
        db_session.flush()
        assert db_session.get(PriceFetchState, "EUNL.DE") \
            .fetched_through == date(2026, 3, 9)
