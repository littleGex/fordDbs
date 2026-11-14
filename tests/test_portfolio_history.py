"""
Tests for portfolio_history (#52): holdings, invested and value per day
from etf_transactions, priced by cached closes and fill prices.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.portfolio_history import portfolio_history
from app.models.shares_models import EtfTransaction, PriceHistory

MON = date(2026, 3, 2)


def d(day):
    return date(2026, 3, day)


@pytest.fixture
def add_txn(db_session):
    def _add(ticker, day, fiat, shares, fees="0"):
        db_session.add(EtfTransaction(
            ticker_symbol=ticker,
            transaction_date=datetime.combine(day, datetime.min.time()),
            fiat_invested=Decimal(fiat), shares_acquired=Decimal(shares),
            fees=Decimal(fees)))
        db_session.flush()
    return _add


@pytest.fixture
def add_close(db_session):
    def _add(ticker, day, close):
        db_session.add(PriceHistory(ticker=ticker, day=day,
                                    close=Decimal(close)))
        db_session.flush()
    return _add


def by_date(points):
    return {p["date"]: p for p in points}


def value_on(points, day):
    return by_date(points)[day.isoformat()]["value"]


def test_shares_and_invested_build_on_trade_dates(db_session, add_txn):
    add_txn("EUNL.DE", d(2), "100", "1", fees="1")
    add_txn("EUNL.DE", d(4), "50", "0.5")

    points = portfolio_history(db_session, d(5), {})

    assert [p["date"] for p in points] == [
        "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"]
    assert [p["invested"] for p in points] == [101.0, 101.0, 151.0, 151.0]


def test_sell_lowers_invested_by_proceeds_minus_fee(db_session, add_txn):
    add_txn("EUNL.DE", d(2), "100", "1", fees="1")
    add_txn("EUNL.DE", d(3), "-60", "-0.5", fees="1")

    points = portfolio_history(db_session, d(3), {})

    assert points[-1]["invested"] == 42.0


def test_weekend_carries_fridays_close(db_session, add_txn, add_close):
    add_txn("EUNL.DE", d(5), "100", "2")
    add_close("EUNL.DE", d(6), "110")

    points = portfolio_history(db_session, d(8), {})

    assert value_on(points, d(7)) == 220.0
    assert value_on(points, d(8)) == 220.0


def test_fill_price_where_no_close(db_session, add_txn):
    add_txn("EUNL.DE", d(2), "100", "1")

    points = portfolio_history(db_session, d(4), {})

    assert [p["value"] for p in points] == [100.0, 100.0, 100.0]


def test_close_wins_over_fill_on_same_day(db_session, add_txn, add_close):
    add_txn("EUNL.DE", d(2), "100", "1")
    add_close("EUNL.DE", d(2), "104")

    assert value_on(portfolio_history(db_session, d(2), {}), d(2)) == 104.0


def test_liquidated_fund_priced_at_fills_then_zero(db_session, add_txn):
    add_txn("IE00BK5BQT80", d(2), "11", "1")
    add_txn("IE00BK5BQT80", d(4), "12", "1")
    add_txn("IE00BK5BQT80", d(6), "-24", "-2")

    points = portfolio_history(db_session, d(7), {})

    assert value_on(points, d(2)) == 11.0
    assert value_on(points, d(4)) == 24.0
    assert value_on(points, d(6)) == 0.0
    assert value_on(points, d(7)) == 0.0


def test_zero_share_or_zero_fiat_rows_give_no_price(db_session, add_txn):
    add_txn("EUNL.DE", d(2), "100", "1")
    add_txn("EUNL.DE", d(3), "0", "-0.5")

    assert value_on(portfolio_history(db_session, d(3), {}), d(3)) == 50.0


def test_today_uses_live_price(db_session, add_txn, add_close):
    add_txn("EUNL.DE", d(2), "100", "2")
    add_close("EUNL.DE", d(2), "110")

    points = portfolio_history(db_session, d(3), {"EUNL.DE": 115.0})

    assert value_on(points, d(2)) == 220.0
    assert value_on(points, d(3)) == 230.0


def test_missing_live_price_carries_last_price(db_session, add_txn,
                                               add_close):
    add_txn("EUNL.DE", d(2), "100", "2")
    add_close("EUNL.DE", d(2), "110")

    points = portfolio_history(db_session, d(3), {"EUNL.DE": 0.0})

    assert value_on(points, d(3)) == 220.0


def test_sold_out_then_rebought(db_session, add_txn, add_close):
    add_txn("EUNL.DE", d(2), "100", "1")
    add_txn("EUNL.DE", d(3), "-105", "-1")
    add_txn("EUNL.DE", d(5), "240", "2")

    points = portfolio_history(db_session, d(5), {})

    assert value_on(points, d(4)) == 0.0
    assert value_on(points, d(5)) == 240.0


def test_first_trade_today(db_session, add_txn):
    add_txn("EUNL.DE", d(2), "100", "1")

    points = portfolio_history(db_session, d(2), {"EUNL.DE": 101.0})

    assert points == [{"date": "2026-03-02", "value": 101.0,
                       "invested": 100.0}]


def test_no_transactions_gives_empty_list(db_session):
    assert portfolio_history(db_session, d(2), {}) == []
