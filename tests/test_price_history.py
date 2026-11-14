"""
Tests for the daily price cache behind the portfolio history chart (#52):
the tables and ensure_price_history in app/core/price_history.py.

No network: the yfinance download is replaced by a fake.
"""
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.price_history import cached_closes, ensure_price_history
from app.models.shares_models import (EtfTransaction, PriceFetchState,
                                      PriceHistory)

THROUGH = date(2026, 3, 9)  # a Monday


def frame(closes, multi=True):
    """A yfinance-shaped frame: {ticker: {date: close}}."""
    days = sorted({d for series in closes.values() for d in series})
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in days])
    if not multi:
        (series,) = closes.values()
        return pd.DataFrame({"Close": [series.get(d) for d in days],
                             "Open": [series.get(d) for d in days]},
                            index=index)
    data = {("Close", t): [series.get(d, float("nan")) for d in days]
            for t, series in closes.items()}
    data.update({("Open", t): [1.0] * len(days) for t in closes})
    result = pd.DataFrame(data, index=index)
    result.columns = pd.MultiIndex.from_tuples(result.columns)
    return result


class FakeDownload:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else pd.DataFrame()
        self.error = error
        self.calls = []

    def __call__(self, tickers, start, end, **kwargs):
        self.calls.append((sorted(tickers), start, end, kwargs))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def add_txn(db_session):
    def _add(ticker, day, fiat="100", shares="1", fees="0"):
        db_session.add(EtfTransaction(
            ticker_symbol=ticker, transaction_date=datetime.combine(
                day, datetime.min.time()),
            fiat_invested=Decimal(fiat), shares_acquired=Decimal(shares),
            fees=Decimal(fees)))
        db_session.flush()
    return _add


def state(db, ticker):
    row = db.get(PriceFetchState, ticker)
    return row.fetched_through if row else None


def set_state(db, ticker, through):
    db.merge(PriceFetchState(ticker=ticker, fetched_through=through))
    db.flush()


def stored(db, ticker):
    return {r.day: r.close for r in db.query(PriceHistory).filter(
        PriceHistory.ticker == ticker)}


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


class TestEnsurePriceHistory:

    def test_first_fill_fetches_from_first_trade_in_one_call(
            self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        add_txn("APC.DE", date(2026, 3, 4))
        fake = FakeDownload(frame({
            "EUNL.DE": {date(2026, 3, 2): 100.0, date(2026, 3, 3): 101.0,
                        THROUGH: 102.0},
            "APC.DE": {date(2026, 3, 4): 180.0, THROUGH: 181.0}}))

        result = ensure_price_history(db_session, through=THROUGH,
                                      download=fake)

        assert result == {}
        assert len(fake.calls) == 1
        tickers, start, end, kwargs = fake.calls[0]
        assert tickers == ["APC.DE", "EUNL.DE"]
        assert (start, end) == (date(2026, 3, 2), date(2026, 3, 10))
        assert kwargs["auto_adjust"] is False
        assert stored(db_session, "EUNL.DE") == {
            date(2026, 3, 2): Decimal("100.000000"),
            date(2026, 3, 3): Decimal("101.000000"),
            THROUGH: Decimal("102.000000")}
        assert stored(db_session, "APC.DE") == {
            date(2026, 3, 4): Decimal("180.000000"),
            THROUGH: Decimal("181.000000")}
        assert state(db_session, "EUNL.DE") == THROUGH
        assert state(db_session, "APC.DE") == THROUGH

    def test_only_missing_days_are_fetched(self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        add_txn("APC.DE", date(2026, 3, 2))
        set_state(db_session, "EUNL.DE", date(2026, 3, 5))
        set_state(db_session, "APC.DE", THROUGH)
        fake = FakeDownload(frame({"EUNL.DE": {date(2026, 3, 6): 103.0}}))

        ensure_price_history(db_session, through=THROUGH, download=fake)

        tickers, start, _, _ = fake.calls[0]
        assert tickers == ["EUNL.DE"]
        assert start == date(2026, 3, 6)

    def test_current_tickers_make_no_call(self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        set_state(db_session, "EUNL.DE", THROUGH)
        fake = FakeDownload()
        assert ensure_price_history(db_session, through=THROUGH,
                                    download=fake) == {}
        assert fake.calls == []

    def test_weekend_without_closes_is_not_refetched_or_stale(
            self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        set_state(db_session, "EUNL.DE", date(2026, 3, 6))
        sunday = date(2026, 3, 8)
        fake = FakeDownload(pd.DataFrame())

        assert ensure_price_history(db_session, through=sunday,
                                    download=fake) == {}
        assert state(db_session, "EUNL.DE") == sunday
        ensure_price_history(db_session, through=sunday, download=fake)
        assert len(fake.calls) == 1

    def test_isin_ticker_rows_are_never_fetched(self, db_session, add_txn):
        add_txn("IE00BK5BQT80", date(2026, 3, 2))
        add_txn("EUNL.DE", date(2026, 3, 2))
        fake = FakeDownload(frame({"EUNL.DE": {date(2026, 3, 2): 100.0}}))

        ensure_price_history(db_session, through=THROUGH, download=fake)

        assert fake.calls[0][0] == ["EUNL.DE"]
        assert state(db_session, "IE00BK5BQT80") is None

    def test_bad_closes_are_dropped(self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        add_txn("APC.DE", date(2026, 3, 2))
        set_state(db_session, "APC.DE", date(2026, 3, 4))
        fake = FakeDownload(frame({
            "EUNL.DE": {date(2026, 3, 2): float("nan"),
                        date(2026, 3, 3): 0.0, date(2026, 3, 4): -1.0,
                        date(2026, 3, 5): 100.0,
                        date(2026, 3, 10): 105.0},
            "APC.DE": {date(2026, 3, 3): 170.0, date(2026, 3, 5): 180.0}}))

        ensure_price_history(db_session, through=THROUGH, download=fake)

        assert list(stored(db_session, "EUNL.DE")) == [date(2026, 3, 5)]
        assert list(stored(db_session, "APC.DE")) == [date(2026, 3, 5)]

    def test_repeated_fill_is_harmless(self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        fake = FakeDownload(frame({"EUNL.DE": {date(2026, 3, 2): 100.0}}))
        ensure_price_history(db_session, through=THROUGH, download=fake)
        set_state(db_session, "EUNL.DE", date(2026, 3, 1))

        ensure_price_history(db_session, through=THROUGH, download=fake)

        assert len(stored(db_session, "EUNL.DE")) == 1

    def test_download_failure_marks_stale_and_changes_nothing(
            self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        add_txn("APC.DE", date(2026, 3, 2))
        set_state(db_session, "EUNL.DE", date(2026, 3, 5))
        fake = FakeDownload(error=RuntimeError("Yahoo is down"))

        result = ensure_price_history(db_session, through=THROUGH,
                                      download=fake)

        assert result == {"EUNL.DE": date(2026, 3, 5), "APC.DE": None}
        assert db_session.query(PriceHistory).count() == 0
        assert state(db_session, "EUNL.DE") == date(2026, 3, 5)
        assert state(db_session, "APC.DE") is None

    def test_unknown_ticker_stays_stale_and_is_retried(self, db_session,
                                                       add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        add_txn("NOPE.DE", date(2026, 3, 2))
        fake = FakeDownload(frame({"EUNL.DE": {THROUGH: 100.0}}))

        assert ensure_price_history(db_session, through=THROUGH,
                                    download=fake) == {"NOPE.DE": None}
        assert state(db_session, "NOPE.DE") is None
        ensure_price_history(db_session, through=THROUGH, download=fake)
        assert fake.calls[1][0] == ["NOPE.DE"]

    def test_empty_download_on_weekdays_is_retried_and_stale(
            self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        set_state(db_session, "EUNL.DE", date(2026, 3, 4))
        fake = FakeDownload(pd.DataFrame())

        result = ensure_price_history(db_session, through=THROUGH,
                                      download=fake)

        assert result == {"EUNL.DE": date(2026, 3, 4)}
        assert state(db_session, "EUNL.DE") == date(2026, 3, 4)
        ensure_price_history(db_session, through=THROUGH, download=fake)
        assert len(fake.calls) == 2

    def test_state_advances_only_to_last_close(self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        fake = FakeDownload(frame({"EUNL.DE": {date(2026, 3, 2): 100.0,
                                               date(2026, 3, 5): 101.0}}))

        result = ensure_price_history(db_session, through=THROUGH,
                                      download=fake)

        assert state(db_session, "EUNL.DE") == date(2026, 3, 5)
        assert result == {"EUNL.DE": date(2026, 3, 5)}

    def test_weekend_after_last_close_counts_as_fetched(self, db_session,
                                                        add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        sunday = date(2026, 3, 8)
        fake = FakeDownload(frame({"EUNL.DE": {date(2026, 3, 6): 100.0}}))

        assert ensure_price_history(db_session, through=sunday,
                                    download=fake) == {}
        assert state(db_session, "EUNL.DE") == sunday

    def test_single_ticker_flat_columns_are_read(self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        fake = FakeDownload(frame({"EUNL.DE": {date(2026, 3, 2): 100.0}},
                                  multi=False))

        ensure_price_history(db_session, through=THROUGH, download=fake)

        assert stored(db_session, "EUNL.DE") == {
            date(2026, 3, 2): Decimal("100.000000")}

    def test_new_ticker_after_change_is_fetched_from_first_trade(
            self, db_session, add_txn):
        add_txn("EUNL.DE", date(2026, 3, 2))
        set_state(db_session, "EUNL.DE", THROUGH)
        db_session.query(EtfTransaction).update(
            {EtfTransaction.ticker_symbol: "IWDA.DE"})
        fake = FakeDownload(frame({"IWDA.DE": {date(2026, 3, 2): 99.0}}))

        ensure_price_history(db_session, through=THROUGH, download=fake)

        tickers, start, _, _ = fake.calls[0]
        assert (tickers, start) == (["IWDA.DE"], date(2026, 3, 2))

    def test_cached_closes_sorted_per_ticker(self, db_session):
        db_session.add_all([
            PriceHistory(ticker="EUNL.DE", day=date(2026, 3, 3),
                         close=Decimal("101")),
            PriceHistory(ticker="EUNL.DE", day=date(2026, 3, 2),
                         close=Decimal("100")),
            PriceHistory(ticker="APC.DE", day=date(2026, 3, 2),
                         close=Decimal("180"))])
        db_session.flush()
        assert cached_closes(db_session, ["EUNL.DE"]) == {"EUNL.DE": [
            (date(2026, 3, 2), Decimal("100.000000")),
            (date(2026, 3, 3), Decimal("101.000000"))]}
