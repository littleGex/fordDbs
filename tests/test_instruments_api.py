# tests/test_instruments_api.py
"""
API tests for /v1/investments/instruments (#38) and ISIN on schedules.

The OpenFIGI / Yahoo lookups are patched with fakes, so these never
touch the network. Only public ISINs are used.
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.models.shares_models import (EtfPurchaseSchedule, EtfTransaction,
                                      Instrument)

BASE = "/v1/investments/instruments"
ISIN = "IE00B4L5Y983"


@pytest.fixture
def lookups():
    """Fake lookups. Edit .figi / .search / .quotes in a test."""
    class Fake:
        figi = ["EUNL.DE"]
        search = [("EUNL.DE", "iShares Core MSCI World")]
        quotes = {"EUNL.DE": ("EUR", Decimal("131.63")),
                  "IWDA.L": ("USD", Decimal("145.51")),
                  "SXR8.DE": ("EUR", Decimal("110"))}
        figi_calls = 0

        def figi_tickers(self, isin):
            Fake.figi_calls += 1
            return list(self.figi)

        def yahoo_search(self, isin):
            return list(self.search)

        def yahoo_quote(self, ticker, on):
            if ticker not in self.quotes:
                raise LookupError(ticker)
            return self.quotes[ticker]

    fake = Fake()
    with patch("app.core.instruments.figi_tickers", fake.figi_tickers), \
            patch("app.core.instruments.yahoo_search", fake.yahoo_search), \
            patch("app.core.instruments.yahoo_quote", fake.yahoo_quote):
        yield fake


@pytest.fixture
def linked_txn(db_session):
    """An instrument (unresolved) with one linked transaction at a fill
    price of 98.27 EUR."""
    db_session.add(Instrument(isin=ISIN, manual_override=False))
    db_session.flush()
    txn = EtfTransaction(ticker_symbol="OLD", isin=ISIN,
                         fiat_invested=Decimal("98.27"),
                         shares_acquired=Decimal("1"),
                         transaction_date=datetime(2026, 2, 16, 10, 0))
    db_session.add(txn)
    db_session.flush()
    return txn


class TestInstrumentsApi:

    def test_add_isin_resolves_and_lists(self, parent_client, lookups):
        resp = parent_client.post(BASE, json={"isin": " ie00b4l5y983 "})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["isin"] == ISIN
        assert body["yahoo_ticker"] == "EUNL.DE"
        assert body["status"] == "resolved"
        assert body["name"] == "iShares Core MSCI World"
        assert body["transactions"] == 0 and body["schedules"] == 0

        listed = parent_client.get(BASE).json()
        assert [i["isin"] for i in listed] == [ISIN]

    def test_add_unresolvable_isin_is_listed_as_unresolved(
            self, parent_client, lookups):
        lookups.figi, lookups.search = [], [("IWDA.L", None)]
        body = parent_client.post(BASE, json={"isin": ISIN}).json()
        assert body["status"] == "unresolved"
        assert "USD" in body["resolution_note"]

    def test_add_existing_isin_does_not_look_up_again(self, parent_client,
                                                      lookups):
        parent_client.post(BASE, json={"isin": ISIN})
        parent_client.post(BASE, json={"isin": ISIN})
        assert lookups.figi_calls == 1

    def test_add_invalid_isin_400(self, parent_client, lookups):
        resp = parent_client.post(BASE, json={"isin": "IE00B4L5Y984"})
        assert resp.status_code == 400

    def test_resolve_runs_lookup_again(self, parent_client, lookups):
        lookups.figi, lookups.search = [], []
        parent_client.post(BASE, json={"isin": ISIN})
        lookups.figi = ["EUNL.DE"]

        resp = parent_client.post(f"{BASE}/{ISIN}/resolve")

        assert resp.status_code == 200, resp.text
        assert resp.json()["yahoo_ticker"] == "EUNL.DE"

    def test_resolve_refuses_override_409(self, parent_client, lookups):
        parent_client.post(BASE, json={"isin": ISIN})
        parent_client.put(f"{BASE}/{ISIN}/ticker",
                          json={"yahoo_ticker": "EUNL.DE"})
        resp = parent_client.post(f"{BASE}/{ISIN}/resolve")
        assert resp.status_code == 409

    def test_resolve_unknown_isin_404(self, parent_client, lookups):
        resp = parent_client.post(f"{BASE}/{ISIN}/resolve")
        assert resp.status_code == 404

    def test_override_normalises_ticker(self, parent_client, lookups):
        parent_client.post(BASE, json={"isin": ISIN})
        resp = parent_client.put(f"{BASE}/{ISIN}/ticker",
                                 json={"yahoo_ticker": "eunl.de "})
        assert resp.status_code == 200, resp.text
        assert resp.json()["yahoo_ticker"] == "EUNL.DE"
        assert resp.json()["status"] == "override"

    def test_override_rejects_non_eur_400(self, parent_client, lookups):
        parent_client.post(BASE, json={"isin": ISIN})
        resp = parent_client.put(f"{BASE}/{ISIN}/ticker",
                                 json={"yahoo_ticker": "IWDA.L"})
        assert resp.status_code == 400
        assert "USD" in resp.json()["detail"]

    def test_override_rejects_unknown_ticker_400(self, parent_client,
                                                 lookups):
        parent_client.post(BASE, json={"isin": ISIN})
        resp = parent_client.put(f"{BASE}/{ISIN}/ticker",
                                 json={"yahoo_ticker": "NOPE.DE"})
        assert resp.status_code == 400

    def test_override_mismatch_409_then_confirm(self, parent_client,
                                                lookups, linked_txn):
        resp = parent_client.put(f"{BASE}/{ISIN}/ticker",
                                 json={"yahoo_ticker": "SXR8.DE"})

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["reference_date"] == "2026-02-16"
        assert Decimal(detail["reference_price"]) == Decimal("98.27")
        assert Decimal(detail["close"]) == Decimal("110")

        resp = parent_client.put(f"{BASE}/{ISIN}/ticker",
                                 json={"yahoo_ticker": "SXR8.DE",
                                       "confirm": True})
        assert resp.status_code == 200, resp.text
        assert resp.json()["yahoo_ticker"] == "SXR8.DE"

    def test_override_updates_linked_rows(self, parent_client, lookups,
                                          linked_txn, db_session):
        schedule = EtfPurchaseSchedule(ticker_symbol="OLD", isin=ISIN,
                                       fiat_amount=Decimal("50"),
                                       execution_day=15)
        db_session.add(schedule)
        db_session.flush()
        lookups.quotes["EUNK.DE"] = ("EUR", Decimal("98.13"))

        resp = parent_client.put(f"{BASE}/{ISIN}/ticker",
                                 json={"yahoo_ticker": "EUNK.DE"})

        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert schedule.ticker_symbol == "EUNK.DE"
        assert linked_txn.ticker_symbol == "EUNK.DE"
        assert resp.json()["schedules"] == 1

    def test_zero_cost_linked_transaction_does_not_500(
            self, parent_client, lookups, linked_txn, db_session):
        # Review fix: reference price 0 used to raise DivisionByZero.
        db_session.add(EtfTransaction(
            ticker_symbol="OLD", isin=ISIN, fiat_invested=Decimal("0"),
            shares_acquired=Decimal("1"),
            transaction_date=datetime(2026, 3, 1, 10, 0)))
        db_session.flush()
        lookups.quotes["EUNK.DE"] = ("EUR", Decimal("98.13"))

        assert parent_client.post(
            f"{BASE}/{ISIN}/resolve").status_code == 200
        resp = parent_client.put(f"{BASE}/{ISIN}/ticker",
                                 json={"yahoo_ticker": "EUNK.DE"})
        assert resp.status_code == 200, resp.text

    def test_link_returns_counts(self, parent_client, lookups, db_session):
        parent_client.post(BASE, json={"isin": ISIN})
        db_session.add(EtfTransaction(ticker_symbol="IWDA",
                                      fiat_invested=Decimal("10"),
                                      shares_acquired=Decimal("1")))
        db_session.flush()

        resp = parent_client.post(f"{BASE}/{ISIN}/link",
                                  json={"ticker_symbol": "iwda"})

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"transactions": 1, "schedules": 0,
                               "conflicts": 0}

    def test_link_unknown_ticker_404(self, parent_client, lookups):
        parent_client.post(BASE, json={"isin": ISIN})
        resp = parent_client.post(f"{BASE}/{ISIN}/link",
                                  json={"ticker_symbol": "NOPE"})
        assert resp.status_code == 404

    def test_unlink_returns_counts(self, parent_client, lookups,
                                   linked_txn, db_session):
        resp = parent_client.post(f"{BASE}/{ISIN}/unlink")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"transactions": 1, "schedules": 0}
        db_session.expire_all()
        assert linked_txn.isin is None

    def test_unlink_unknown_isin_404(self, parent_client, lookups):
        assert parent_client.post(
            f"{BASE}/{ISIN}/unlink").status_code == 404

    def test_unlink_requires_login(self, client):
        assert client.post(f"{BASE}/{ISIN}/unlink").status_code == 401

    def test_instruments_require_login(self, client):
        assert client.get(BASE).status_code == 401


class TestScheduleWithIsin:

    URL = "/v1/investments/etf/schedule"

    def test_schedule_with_resolved_isin_uses_its_ticker(
            self, parent_client, lookups, db_session):
        parent_client.post(BASE, json={"isin": ISIN})

        resp = parent_client.post(self.URL, params={
            "ticker": "x", "amount": 10, "day": 5,
            "isin": " ie00b4l5y983"})

        assert resp.status_code == 200, resp.text
        (schedule,) = db_session.query(EtfPurchaseSchedule).all()
        assert schedule.ticker_symbol == "EUNL.DE"
        assert schedule.isin == ISIN

    def test_schedule_with_unresolved_isin_400(self, parent_client,
                                               lookups, db_session):
        lookups.figi, lookups.search = [], []
        parent_client.post(BASE, json={"isin": ISIN})

        resp = parent_client.post(self.URL, params={
            "ticker": "x", "amount": 10, "day": 5, "isin": ISIN})

        assert resp.status_code == 400
        assert db_session.query(EtfPurchaseSchedule).count() == 0

    def test_schedule_with_unknown_isin_400(self, parent_client, lookups):
        resp = parent_client.post(self.URL, params={
            "ticker": "x", "amount": 10, "day": 5, "isin": ISIN})
        assert resp.status_code == 400

    def test_schedule_without_isin_unchanged(self, parent_client,
                                             db_session):
        resp = parent_client.post(self.URL, params={
            "ticker": "vti", "amount": 10, "day": 5})
        assert resp.status_code == 200, resp.text
        (schedule,) = db_session.query(EtfPurchaseSchedule).all()
        assert schedule.ticker_symbol == "VTI"
        assert schedule.isin is None

    def test_schedule_with_isin_needs_no_ticker(self, parent_client,
                                                lookups, db_session):
        parent_client.post(BASE, json={"isin": ISIN})
        resp = parent_client.post(self.URL, params={
            "amount": 10, "day": 5, "isin": ISIN})
        assert resp.status_code == 200, resp.text
        (schedule,) = db_session.query(EtfPurchaseSchedule).all()
        assert schedule.ticker_symbol == "EUNL.DE"

    def test_schedule_needs_ticker_or_isin(self, parent_client,
                                           db_session):
        resp = parent_client.post(self.URL, params={"amount": 10, "day": 5})
        assert resp.status_code == 400
        assert db_session.query(EtfPurchaseSchedule).count() == 0

    def test_list_schedules_returns_them(self, parent_client, db_session):
        # Regression: response_model=List[dict] could not serialise ORM
        # rows, so any existing schedule made this a 500.
        db_session.add(EtfPurchaseSchedule(
            ticker_symbol="EUNL.DE", isin=None, fiat_amount=Decimal("50"),
            execution_day=15, is_active=True))
        db_session.flush()

        resp = parent_client.get("/v1/investments/etf/schedules")

        assert resp.status_code == 200, resp.text
        (row,) = resp.json()
        assert row["ticker_symbol"] == "EUNL.DE"
        assert row["execution_day"] == 15
        assert row["isin"] is None
