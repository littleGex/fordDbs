# tests/test_instruments.py
"""
Tests for ISIN instruments (#38): the Instrument model, ISIN validation,
the ticker resolver and the service layer in app/core/instruments.py.

Only public ISINs are used here; the repo is public.
"""
import io
import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from app.core import instruments
from app.core.instruments import (Resolution, apply_resolution,
                                  get_or_resolve, link_ticker,
                                  normalize_isin, re_resolve, reference_for,
                                  resolve_isin, set_instrument_ticker)
from app.models.shares_models import (EtfPurchaseSchedule, EtfTransaction,
                                      Instrument)


class TestInstrumentModel:

    def test_transaction_can_link_to_instrument(self, db_session):
        db_session.add(Instrument(isin="IE00B4L5Y983",
                                  yahoo_ticker="EUNL.DE", currency="EUR"))
        db_session.flush()
        db_session.add(EtfTransaction(
            ticker_symbol="EUNL.DE", isin="IE00B4L5Y983",
            fiat_invested=Decimal("10"), shares_acquired=Decimal("0.1")))
        db_session.flush()

        inst = db_session.get(Instrument, "IE00B4L5Y983")
        db_session.refresh(inst)
        assert inst.manual_override is False
        assert inst.created_at is not None


# ---------------------------------------------------------------------
# ISIN validation and resolve_isin, with fake lookups shaped like the
# 2026-11-12 spike results (see the spec).
# ---------------------------------------------------------------------

class FakeLookups:
    """figi/search/quote stand-ins. quotes maps ticker ->
    (currency, close); a ticker missing from it raises LookupError."""

    def __init__(self, figi=(), search=(), quotes=None,
                 figi_error=None, search_error=None):
        self.figi_result = list(figi)
        self.search_result = list(search)
        self.quotes = quotes or {}
        self.figi_error = figi_error
        self.search_error = search_error
        self.quote_calls = []

    def figi(self, isin):
        if self.figi_error:
            raise self.figi_error
        return self.figi_result

    def search(self, isin):
        if self.search_error:
            raise self.search_error
        return self.search_result

    def quote(self, ticker, on):
        self.quote_calls.append((ticker, on))
        if ticker not in self.quotes:
            raise LookupError(ticker)
        return self.quotes[ticker]

    def resolve(self, isin, reference=None):
        return resolve_isin(isin, reference, figi_tickers=self.figi,
                            yahoo_search=self.search,
                            yahoo_quote=self.quote)


EUR = "EUR"


class TestNormalizeIsin:

    def test_valid_isins_pass(self):
        assert normalize_isin(" ie00b4l5y983 ") == "IE00B4L5Y983"
        for isin in ("IE00BK5BQT80", "DE0005933931", "US0079031078"):
            assert normalize_isin(isin) == isin

    @pytest.mark.parametrize("bad", ["IE00B4L5Y984", "IE00B4L5Y98",
                                     "1E00B4L5Y983", "", "IE00B4L5Y9833"])
    def test_bad_isin_rejected(self, bad):
        with pytest.raises(ValueError):
            normalize_isin(bad)


class TestResolveIsin:

    def test_invalid_isin_makes_no_lookup(self):
        def boom(*args):
            raise AssertionError("no lookup expected")

        with pytest.raises(ValueError):
            resolve_isin("XX123", figi_tickers=boom, yahoo_search=boom,
                         yahoo_quote=boom)

    def test_prefers_de_over_other_eur(self):
        f = FakeLookups(figi=["EUNL.DE"], search=[("IMAE.AS", None)],
                        quotes={"EUNL.DE": (EUR, Decimal("131.63")),
                                "IMAE.AS": (EUR, Decimal("131.60"))})
        r = f.resolve("IE00B4L5Y983")
        assert r.ticker == "EUNL.DE"
        assert r.currency == "EUR"

    def test_rejects_usd_listing(self):
        f = FakeLookups(search=[("IWDA.L", None)],
                        quotes={"IWDA.L": ("USD", Decimal("145.51"))})
        r = f.resolve("IE00B4L5Y983")
        assert r.ticker is None
        (cand,) = r.candidates
        assert cand.accepted is False
        assert "USD" in cand.reason

    def test_rejects_gbp_priced_de_ticker(self):
        f = FakeLookups(figi=["MWRD.DE", "MWRE.DE"],
                        quotes={"MWRD.DE": ("GBP", Decimal("113.11")),
                                "MWRE.DE": (EUR, Decimal("125.07"))})
        assert f.resolve("IE00B4L5Y983").ticker == "MWRE.DE"

    def test_falls_back_to_non_de_eur_listing(self):
        f = FakeLookups(figi=["SPYS.DE"], search=[("SMC.PA", None)],
                        quotes={"SMC.PA": (EUR, Decimal("374.65"))})
        r = f.resolve("IE00B4L5Y983")
        assert r.ticker == "SMC.PA"
        assert [c.reason for c in r.candidates if not c.accepted] == [
            "no Yahoo data"]

    def test_eur_listing_without_close_rejected(self):
        f = FakeLookups(figi=["EUNL.DE"], quotes={"EUNL.DE": (EUR, None)})
        assert f.resolve("IE00B4L5Y983").ticker is None

    def test_reference_within_tolerance_resolves(self):
        f = FakeLookups(figi=["EUNK.DE"],
                        quotes={"EUNK.DE": (EUR, Decimal("98.13"))})
        r = f.resolve("IE00B4L5Y983", (date(2026, 2, 16), Decimal("98.27")))
        assert r.ticker == "EUNK.DE"

    def test_reference_off_by_more_than_5_percent_unresolved(self):
        f = FakeLookups(figi=["EUNK.DE"],
                        quotes={"EUNK.DE": (EUR, Decimal("110"))})
        r = f.resolve("IE00B4L5Y983", (date(2026, 2, 16), Decimal("98.27")))
        assert r.ticker is None
        assert "off" in r.note

    def test_reference_date_passed_to_quote(self):
        f = FakeLookups(figi=["EUNL.DE"],
                        quotes={"EUNL.DE": (EUR, Decimal("131.63"))})
        f.resolve("IE00B4L5Y983", (date(2026, 2, 16), Decimal("131")))
        assert f.quote_calls == [("EUNL.DE", date(2026, 2, 16))]

        g = FakeLookups(figi=["EUNL.DE"],
                        quotes={"EUNL.DE": (EUR, Decimal("131.63"))})
        r = g.resolve("IE00B4L5Y983")
        assert g.quote_calls == [("EUNL.DE", None)]
        assert "not checked" in r.note

    def test_one_source_failing_uses_the_other(self):
        f = FakeLookups(figi_error=OSError("timeout"),
                        search=[("EUNL.DE", None)],
                        quotes={"EUNL.DE": (EUR, Decimal("131.63"))})
        assert f.resolve("IE00B4L5Y983").ticker == "EUNL.DE"

    def test_all_lookups_failing_says_retry(self):
        f = FakeLookups(figi_error=OSError("down"),
                        search_error=OSError("down"))
        r = f.resolve("IE00B4L5Y983")
        assert r.ticker is None
        assert "lookup failed, retry later" in r.note

    def test_no_candidates_unresolved(self):
        r = FakeLookups().resolve("IE00B4L5Y983")
        assert r.ticker is None
        assert r.candidates == []

    def test_duplicates_checked_once(self):
        f = FakeLookups(figi=["EUNL.DE"], search=[("EUNL.DE", None)],
                        quotes={"EUNL.DE": (EUR, Decimal("131.63"))})
        f.resolve("IE00B4L5Y983")
        assert len(f.quote_calls) == 1

    def test_name_from_search(self):
        f = FakeLookups(search=[("IWDA.L", None),
                                ("EUNL.DE", "iShares Core MSCI World")],
                        quotes={"EUNL.DE": (EUR, Decimal("131.63"))})
        assert f.resolve("IE00B4L5Y983").name == "iShares Core MSCI World"
        assert FakeLookups().resolve("IE00B4L5Y983").name is None


# ---------------------------------------------------------------------
# Real lookups, with the HTTP and yfinance layers patched.
# ---------------------------------------------------------------------

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _figi_response(payload):
    return _FakeResponse(json.dumps(payload).encode())


class _FakeTicker:
    def __init__(self, currency, closes):
        self.fast_info = {"currency": currency}
        self._closes = closes

    def history(self, **kwargs):
        index = pd.date_range("2026-02-12", periods=len(self._closes))
        return pd.DataFrame({"Close": self._closes}, index=index)


class TestRealLookups:

    def test_figi_tickers_keeps_german_composite_only(self):
        payload = [{"data": [
            {"ticker": "EUNL", "exchCode": "GR"},
            {"ticker": "EUNL", "exchCode": "GY"},
            {"ticker": "IWDA", "exchCode": "LN"},
            {"ticker": "EUNL", "exchCode": "GR"},
        ]}]
        with patch("app.core.instruments.urllib.request.urlopen",
                   return_value=_figi_response(payload)) as urlopen:
            assert instruments.figi_tickers("IE00B4L5Y983") == ["EUNL.DE"]
        request = urlopen.call_args.args[0]
        assert json.loads(request.data) == [
            {"idType": "ID_ISIN", "idValue": "IE00B4L5Y983"}]
        assert urlopen.call_args.kwargs["timeout"] == 10

    def test_figi_tickers_no_match_returns_empty(self):
        payload = [{"warning": "No identifier found."}]
        with patch("app.core.instruments.urllib.request.urlopen",
                   return_value=_figi_response(payload)):
            assert instruments.figi_tickers("IE00B4L5Y983") == []

    def test_yahoo_search_returns_symbols_and_names(self):
        search = MagicMock()
        search.return_value.quotes = [
            {"symbol": "IWDA.L", "shortname": "iShares MSCI World"},
            {"symbol": "EUNL.DE"},
        ]
        with patch("app.core.instruments.yf.Search", search):
            assert instruments.yahoo_search("IE00B4L5Y983") == [
                ("IWDA.L", "iShares MSCI World"), ("EUNL.DE", None)]

    def test_yahoo_quote_skips_nan_close(self):
        with patch("app.core.instruments.yf.Ticker",
                   return_value=_FakeTicker("EUR", [131.5, float("nan")])):
            assert instruments.yahoo_quote(
                "EUNL.DE", date(2026, 2, 13)) == ("EUR", Decimal("131.5"))
        with patch("app.core.instruments.yf.Ticker",
                   return_value=_FakeTicker("EUR", [float("nan")] * 2)):
            assert instruments.yahoo_quote("EUNL.DE", None) == ("EUR", None)

    def test_yahoo_quote_unknown_ticker_is_lookup_error(self):
        ticker = MagicMock()
        type(ticker).fast_info = PropertyMock(side_effect=KeyError("x"))
        with patch("app.core.instruments.yf.Ticker", return_value=ticker):
            with pytest.raises(LookupError):
                instruments.yahoo_quote("XMWO.DE", None)

    def test_resolve_isin_uses_real_lookups_by_default(self):
        with patch("app.core.instruments.figi_tickers",
                   return_value=["EUNL.DE"]) as figi, \
                patch("app.core.instruments.yahoo_search",
                      return_value=[]) as search, \
                patch("app.core.instruments.yahoo_quote",
                      return_value=("EUR", Decimal("131.63"))) as quote:
            assert resolve_isin("IE00B4L5Y983").ticker == "EUNL.DE"
        figi.assert_called_once_with("IE00B4L5Y983")
        search.assert_called_once_with("IE00B4L5Y983")
        quote.assert_called_once_with("EUNL.DE", None)


@pytest.mark.live_api
def test_live_resolves_public_isin():
    """Opt-in: hits OpenFIGI and Yahoo. Run with --run-live-api."""
    assert resolve_isin("IE00B4L5Y983").ticker == "EUNL.DE"


# ---------------------------------------------------------------------
# Service layer (database).
# ---------------------------------------------------------------------

ISIN = "IE00B4L5Y983"
OTHER_ISIN = "IE00BK5BQT80"


class FakeResolver:
    def __init__(self, ticker="EUNL.DE", name="iShares Core MSCI World"):
        self.ticker = ticker
        self.name = name
        self.calls = []

    def __call__(self, isin, reference=None):
        self.calls.append((isin, reference))
        return Resolution(isin=isin, ticker=self.ticker,
                          currency="EUR" if self.ticker else None,
                          name=self.name, candidates=[],
                          note="picked" if self.ticker else "unresolved")


@pytest.fixture
def add_txn(db_session):
    def _add(ticker, isin=None, fiat="100.00", shares="1",
             when=datetime(2026, 2, 16, 10, 0)):
        txn = EtfTransaction(ticker_symbol=ticker, isin=isin,
                             fiat_invested=Decimal(fiat),
                             shares_acquired=Decimal(shares),
                             transaction_date=when)
        db_session.add(txn)
        db_session.flush()
        return txn
    return _add


@pytest.fixture
def add_schedule(db_session):
    def _add(ticker, isin=None):
        schedule = EtfPurchaseSchedule(ticker_symbol=ticker, isin=isin,
                                       fiat_amount=Decimal("50"),
                                       execution_day=15)
        db_session.add(schedule)
        db_session.flush()
        return schedule
    return _add


@pytest.fixture
def instrument(db_session):
    def _make(isin=ISIN, ticker=None, manual=False, name=None):
        inst = Instrument(isin=isin, yahoo_ticker=ticker,
                          currency="EUR" if ticker else None,
                          manual_override=manual, name=name)
        db_session.add(inst)
        db_session.flush()
        return inst
    return _make


class TestServiceLayer:

    def test_set_ticker_updates_linked_transactions_and_schedules(
            self, db_session, instrument, add_txn, add_schedule):
        inst = instrument()
        linked_txn = add_txn("OLD", isin=ISIN)
        linked_schedule = add_schedule("OLD", isin=ISIN)
        unlinked = add_txn("OLD")

        set_instrument_ticker(db_session, inst, "EUNL.DE", "EUR",
                              manual=True)
        db_session.flush()
        db_session.expire_all()

        assert linked_txn.ticker_symbol == "EUNL.DE"
        assert linked_schedule.ticker_symbol == "EUNL.DE"
        assert unlinked.ticker_symbol == "OLD"
        assert inst.manual_override is True
        assert inst.resolved_at is not None

    def test_get_or_resolve_creates_then_caches(self, db_session):
        resolver = FakeResolver()
        first = get_or_resolve(db_session, " ie00b4l5y983", resolver=resolver)
        second = get_or_resolve(db_session, ISIN, resolver=resolver)

        assert first is second
        assert first.yahoo_ticker == "EUNL.DE"
        assert first.name == "iShares Core MSCI World"
        assert len(resolver.calls) == 1
        assert db_session.query(Instrument).count() == 1

    def test_get_or_resolve_passes_reference(self, db_session):
        resolver = FakeResolver()
        ref = (date(2026, 2, 16), Decimal("98.27"))
        get_or_resolve(db_session, ISIN, reference=ref, resolver=resolver)
        assert resolver.calls == [(ISIN, ref)]

    def test_get_or_resolve_unresolved_is_not_retried(self, db_session):
        resolver = FakeResolver(ticker=None)
        inst = get_or_resolve(db_session, ISIN, resolver=resolver)
        get_or_resolve(db_session, ISIN, resolver=resolver)

        assert inst.yahoo_ticker is None
        assert inst.resolution_note == "unresolved"
        assert len(resolver.calls) == 1

    def test_get_or_resolve_rejects_invalid_isin(self, db_session):
        with pytest.raises(ValueError):
            get_or_resolve(db_session, "IE00B4L5Y984",
                           resolver=FakeResolver())

    def test_re_resolve_refuses_override(self, db_session, instrument):
        inst = instrument(ticker="EUNL.DE", manual=True)
        with pytest.raises(PermissionError):
            re_resolve(db_session, inst, resolver=FakeResolver())

    def test_re_resolve_updates_ticker(self, db_session, instrument,
                                       add_txn):
        inst = instrument()
        txn = add_txn("OLD", isin=ISIN)
        re_resolve(db_session, inst, resolver=FakeResolver("EUNL.DE"))
        db_session.flush()
        db_session.expire_all()
        assert inst.yahoo_ticker == "EUNL.DE"
        assert txn.ticker_symbol == "EUNL.DE"
        assert inst.manual_override is False

    def test_apply_resolution_keeps_given_name(self, db_session,
                                               instrument):
        inst = instrument(name="My fund")
        apply_resolution(db_session, inst,
                         FakeResolver(name="Other")(ISIN))
        assert inst.name == "My fund"

    def test_link_sets_isin_and_syncs_ticker(
            self, db_session, instrument, add_txn, add_schedule):
        instrument(ticker="EUNL.DE")
        t1, t2 = add_txn("IWDA"), add_txn("IWDA")
        schedule = add_schedule("IWDA")

        counts = link_ticker(db_session, db_session.get(Instrument, ISIN),
                             " iwda ")
        db_session.flush()
        db_session.expire_all()

        assert counts == {"transactions": 2, "schedules": 1,
                          "conflicts": 0}
        for row in (t1, t2, schedule):
            assert row.isin == ISIN
            assert row.ticker_symbol == "EUNL.DE"

    def test_link_unresolved_keeps_ticker(self, db_session, instrument,
                                          add_txn):
        inst = instrument()
        txn = add_txn("IWDA")
        link_ticker(db_session, inst, "IWDA")
        db_session.flush()
        db_session.expire_all()
        assert txn.isin == ISIN
        assert txn.ticker_symbol == "IWDA"

    def test_link_counts_conflicts(self, db_session, instrument, add_txn):
        inst = instrument()
        instrument(isin=OTHER_ISIN)
        other = add_txn("IWDA", isin=OTHER_ISIN)
        add_txn("IWDA")

        counts = link_ticker(db_session, inst, "IWDA")
        db_session.flush()
        db_session.expire_all()

        assert counts == {"transactions": 1, "schedules": 0,
                          "conflicts": 1}
        assert other.isin == OTHER_ISIN

    def test_link_twice_returns_zero_counts(self, db_session, instrument,
                                            add_txn):
        inst = instrument()
        add_txn("IWDA")
        link_ticker(db_session, inst, "IWDA")
        db_session.flush()
        assert link_ticker(db_session, inst, "IWDA") == {
            "transactions": 0, "schedules": 0, "conflicts": 0}

    def test_link_twice_after_ticker_sync_returns_zero_counts(
            self, db_session, instrument, add_txn):
        # Linking renames IWDA rows to EUNL.DE; linking IWDA again
        # finds no rows under that name any more but must not fail.
        inst = instrument(ticker="EUNL.DE")
        add_txn("IWDA")
        link_ticker(db_session, inst, "IWDA")
        db_session.flush()
        assert link_ticker(db_session, inst, "IWDA") == {
            "transactions": 0, "schedules": 0, "conflicts": 0}

    def test_link_unknown_ticker_raises(self, db_session, instrument):
        with pytest.raises(LookupError):
            link_ticker(db_session, instrument(), "NOPE")

    def test_reference_for_skips_zero_cost_and_scheduled_rows(
            self, db_session, instrument, add_txn):
        # Review fix: a zero-cost row (gifted share) gave price 0 and a
        # DivisionByZero 500; scheduled rows are estimates at the old
        # ticker's price, not real fills.
        instrument()
        add_txn("X", isin=ISIN, fiat="98.27", shares="1",
                when=datetime(2026, 2, 16, 10, 0))
        add_txn("X", isin=ISIN, fiat="0", shares="1",
                when=datetime(2026, 3, 1, 10, 0))
        scheduled = add_txn("X", isin=ISIN, fiat="145.00", shares="1",
                            when=datetime(2026, 3, 15, 9, 0))
        scheduled.entry_type = "scheduled"
        db_session.flush()

        assert reference_for(db_session, ISIN) == (
            date(2026, 2, 16), Decimal("98.27"))

    def test_reference_for_ignores_rows_without_date(
            self, db_session, instrument, add_txn):
        instrument()
        add_txn("X", isin=ISIN, fiat="98.27", shares="1",
                when=datetime(2026, 2, 16, 10, 0))
        undated = add_txn("X", isin=ISIN, fiat="50", shares="1")
        undated.transaction_date = None
        db_session.flush()

        assert reference_for(db_session, ISIN) == (
            date(2026, 2, 16), Decimal("98.27"))

    def test_reference_for_latest_fill(self, db_session, instrument,
                                       add_txn):
        instrument()
        assert reference_for(db_session, ISIN) is None
        add_txn("X", isin=ISIN, fiat="100.00", shares="1",
                when=datetime(2026, 1, 16, 10, 0))
        add_txn("X", isin=ISIN, fiat="-98.27", shares="-1",
                when=datetime(2026, 2, 16, 10, 0))
        add_txn("X", isin=ISIN, fiat="0", shares="0",
                when=datetime(2026, 3, 1, 10, 0))
        assert reference_for(db_session, ISIN) == (
            date(2026, 2, 16), Decimal("98.27"))
