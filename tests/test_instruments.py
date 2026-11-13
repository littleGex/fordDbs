# tests/test_instruments.py
"""
Tests for ISIN instruments (#38): the Instrument model, ISIN validation,
the ticker resolver and the service layer in app/core/instruments.py.

Only public ISINs are used here; the repo is public.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.core.instruments import normalize_isin, resolve_isin
from app.models.shares_models import EtfTransaction, Instrument


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
