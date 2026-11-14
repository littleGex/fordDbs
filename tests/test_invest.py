# tests/test_invest.py
"""
Tests for app/core/investments.py.

NOTE ON THIS REWRITE: an earlier hand-written version of this file
included `test_fetch_live_prices_integration`, which called the real
Yahoo Finance API with no mocking and asserted a hardcoded price range
(e.g. `50 < results["AIR.PA"] < 300`). This is fragile by design --
it fails on any real market move, any yfinance API change, or simply
no network access (as in this sandboxed environment), and it makes
the suite non-deterministic. Real-API verification has real value as
a manual smoke test, so it's kept below as `test_live_api_smoke_test`,
explicitly marked `@pytest.mark.live_api` and EXCLUDED from normal
`pytest` runs (see pytest.ini). Run it deliberately with:

    pytest -m live_api

All other tests in this file use mocked yfinance responses and are
fully deterministic.
"""
import math
import pytest
import pandas as pd
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from app.core.investments import fetch_live_prices, get_portfolio_summary
from app.models.shares_models import EtfTransaction


class TestFetchLivePricesLogic:

    @patch("yfinance.download")
    def test_returns_latest_close_price_per_ticker(self, mock_download):
        mock_data = pd.DataFrame(
            {
                ("Close", "AAPL"): [150.0, 155.0],
                ("Close", "AIR.PA"): [110.0, 112.0],
            },
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        )
        mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
        mock_download.return_value = mock_data

        results = fetch_live_prices({"AAPL", "AIR.PA"})

        assert results["AAPL"] == 155.0
        assert results["AIR.PA"] == 112.0

    @patch("yfinance.download")
    def test_rounds_price_to_two_decimal_places(self, mock_download):
        mock_data = pd.DataFrame(
            {("Close", "AAPL"): [150.0, 155.4567]},
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        )
        mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
        mock_download.return_value = mock_data

        results = fetch_live_prices({"AAPL"})

        assert results["AAPL"] == 155.46

    @patch("yfinance.download")
    def test_empty_dataframe_returns_zero_for_all_tickers(
        self, mock_download
    ):
        mock_download.return_value = pd.DataFrame()

        results = fetch_live_prices({"AAPL", "AIR.PA"})

        assert results == {"AAPL": 0.0, "AIR.PA": 0.0}

    @patch("yfinance.download")
    def test_missing_ticker_in_response_defaults_to_zero(
        self, mock_download
    ):
        """
        If yfinance returns data for some but not all requested
        tickers (e.g. a delisted or mistyped symbol), the missing
        ticker should default to 0.0 rather than raising a KeyError.
        """
        mock_data = pd.DataFrame(
            {("Close", "AAPL"): [150.0, 155.0]},
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        )
        mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
        mock_download.return_value = mock_data

        results = fetch_live_prices({"AAPL", "NOTREAL"})

        assert results["AAPL"] == 155.0
        assert results["NOTREAL"] == 0.0

    @patch("yfinance.download")
    def test_all_nan_series_defaults_to_zero(self, mock_download):
        mock_data = pd.DataFrame(
            {("Close", "AAPL"): [float("nan"), float("nan")]},
            index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        )
        mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
        mock_download.return_value = mock_data

        results = fetch_live_prices({"AAPL"})

        assert results["AAPL"] == 0.0

    @patch("yfinance.download")
    def test_download_exception_does_not_propagate(self, mock_download):
        """
        A network failure or yfinance error must not crash the
        caller -- it should degrade to 0.0 prices so the rest of the
        dashboard can still render.
        """
        mock_download.side_effect = ConnectionError("network down")

        results = fetch_live_prices({"AAPL"})

        assert results["AAPL"] == 0.0

    def test_empty_ticker_set_returns_empty_dict(self):
        assert fetch_live_prices(set()) == {}


@pytest.mark.live_api
class TestFetchLivePricesLiveSmokeTest:
    """
    Opt-in only: hits the real Yahoo Finance API. Run explicitly with
    `pytest -m live_api`. Not included in normal test runs because it
    is non-deterministic (depends on live market data and network
    availability) and would make the suite flaky in CI.
    """

    def test_live_api_smoke_test(self):
        test_tickers = {"AAPL"}
        results = fetch_live_prices(test_tickers)

        assert set(results.keys()) == test_tickers
        price = results["AAPL"]
        assert isinstance(price, (float, int))
        assert math.isfinite(price)
        assert price > 0, "A price of 0.0 usually means the fetch failed"


# ---------------------------------------------------------------------------
# ETF transaction endpoints (app/api/v1/shares.py)
#
# These hit the real API against the test Postgres database, unlike the
# mocked fetch_live_prices tests above.
# ---------------------------------------------------------------------------

ETF_BULK_URL = "/v1/investments/etf/bulk-add"
ETF_SINGLE_URL = "/v1/investments/etf/transaction"
ETF_HEADER = ("ticker,fiat_amount,shares_acquired,transaction_date,"
              "fees,transaction_type")


def _etf_rows(db_session):
    from app.models.shares_models import EtfTransaction
    return (db_session.query(EtfTransaction)
            .order_by(EtfTransaction.transaction_id).all())


class TestEtfBulkAdd:

    def test_persists_dates_fees_and_amounts(self, parent_client,
                                             db_session):
        csv_data = "\n".join([
            ETF_HEADER,
            "vti,1000.00,10.5,2024-01-15,5.00,buy",
            "VXUS,500.25,7.2,2023-06-30,2.50,buy",
        ])

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 200, resp.text
        assert resp.json()["imported"] == 2
        rows = _etf_rows(db_session)
        assert [r.ticker_symbol for r in rows] == ["VTI", "VXUS"]
        assert [r.transaction_date for r in rows] == [
            datetime(2024, 1, 15), datetime(2023, 6, 30)]
        assert [r.fees for r in rows] == [Decimal("5.00"), Decimal("2.50")]
        assert rows[1].fiat_invested == Decimal("500.25")
        assert rows[0].shares_acquired == Decimal("10.5")
        assert all(r.entry_type == "import" for r in rows)

    def test_header_row_is_not_imported(self, parent_client, db_session):
        csv_data = ETF_HEADER + "\nVTI,100,1,2024-01-01,0,buy\n"

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 200, resp.text
        assert len(_etf_rows(db_session)) == 1

    def test_bad_row_rolls_back_whole_import(self, parent_client,
                                             db_session):
        csv_data = "\n".join([
            ETF_HEADER,
            "VTI,100,1,2024-01-01,0,buy",
            "VTI,100,1,2024-13-01,0,buy",
        ])

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 400
        assert "row 3" in resp.json()["detail"]
        assert _etf_rows(db_session) == []

    @pytest.mark.parametrize("fiat,shares", [("250", "2"), ("-250", "-2")])
    def test_sell_is_stored_negative_whatever_sign_given(
            self, parent_client, db_session, fiat, shares):
        csv_data = (ETF_HEADER
                    + f"\nVTI,{fiat},{shares},2024-02-01,1.00,sell")

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 200, resp.text
        (row,) = _etf_rows(db_session)
        assert row.transaction_type == "sell"
        assert row.fiat_invested == Decimal("-250")
        assert row.shares_acquired == Decimal("-2")

    def test_buy_is_stored_positive_whatever_sign_given(self, parent_client,
                                                        db_session):
        csv_data = ETF_HEADER + "\nVTI,-250,-2,2024-02-01,0,buy"

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 200, resp.text
        (row,) = _etf_rows(db_session)
        assert row.fiat_invested == Decimal("250")
        assert row.shares_acquired == Decimal("2")

    def test_blank_fees_and_type_default_to_zero_and_buy(self, parent_client,
                                                         db_session):
        csv_data = ETF_HEADER + "\nVTI,100,1,2024-01-01,,"

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 200, resp.text
        (row,) = _etf_rows(db_session)
        assert row.fees == Decimal("0")
        assert row.transaction_type == "buy"

    def test_extra_columns_are_ignored(self, parent_client, db_session):
        csv_data = (ETF_HEADER + ",external_id\n"
                    "VTI,100,1,2024-01-01,0,buy,abc-123")

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 200, resp.text
        assert len(_etf_rows(db_session)) == 1

    @pytest.mark.parametrize("csv_data,expected", [
        ("", "No CSV data"),
        (ETF_HEADER, "No rows"),
        ("ticker,fiat_amount\nVTI,100", "Missing column"),
        (ETF_HEADER + "\nVTI,100,1,2024-01-01,0,hold", "transaction_type"),
        (ETF_HEADER + "\nVTI,abc,1,2024-01-01,0,buy", "fiat_amount"),
        (ETF_HEADER + "\nVTI,NaN,1,2024-01-01,0,buy", "fiat_amount"),
        (ETF_HEADER + "\nVTI,100,1,2024-01-01,-1,buy", "fees"),
        (ETF_HEADER + "\n,100,1,2024-01-01,0,buy", "ticker"),
    ])
    def test_rejects_invalid_input(self, parent_client, db_session,
                                   csv_data, expected):
        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 400
        assert expected in resp.json()["detail"]
        assert _etf_rows(db_session) == []

    def test_value_too_large_for_column_rolls_back(self, parent_client,
                                                   db_session):
        # fiat_invested is Numeric(10, 2): max 99,999,999.99
        csv_data = "\n".join([
            ETF_HEADER,
            "VTI,100,1,2024-01-01,0,buy",
            "VTI,1000000000,1,2024-01-01,0,buy",
        ])

        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 400
        assert "nothing was imported" in resp.json()["detail"]
        assert _etf_rows(db_session) == []

    def test_rejects_non_string_csv_data(self, parent_client, db_session):
        resp = parent_client.post(ETF_BULK_URL, json={"csv_data": 123})

        assert resp.status_code == 400
        assert _etf_rows(db_session) == []

    def test_requires_login(self, client):
        csv_data = ETF_HEADER + "\nVTI,100,1,2024-01-01,0,buy"

        resp = client.post(ETF_BULK_URL, json={"csv_data": csv_data})

        assert resp.status_code == 401


class TestEtfSingleTransaction:

    def test_persists_given_date_and_fees(self, parent_client, db_session):
        resp = parent_client.post(ETF_SINGLE_URL, params={
            "ticker": "vti", "fiat_amount": 100, "shares_acquired": 1,
            "transaction_date": "2024-03-05", "fees": 1.25,
        })

        assert resp.status_code == 200, resp.text
        (row,) = _etf_rows(db_session)
        assert row.transaction_date == datetime(2024, 3, 5)
        assert row.fees == Decimal("1.25")

    def test_date_defaults_to_now(self, parent_client, db_session):
        before = datetime.now()
        resp = parent_client.post(ETF_SINGLE_URL, params={
            "ticker": "VTI", "fiat_amount": 100, "shares_acquired": 1,
        })

        assert resp.status_code == 200, resp.text
        (row,) = _etf_rows(db_session)
        assert row.transaction_date >= before.replace(microsecond=0)
        assert row.fees == Decimal("0")

    def test_rejects_bad_date(self, parent_client, db_session):
        resp = parent_client.post(ETF_SINGLE_URL, params={
            "ticker": "VTI", "fiat_amount": 100, "shares_acquired": 1,
            "transaction_date": "05/03/2024",
        })

        assert resp.status_code == 400
        assert _etf_rows(db_session) == []

    def test_rejects_negative_fees(self, parent_client, db_session):
        resp = parent_client.post(ETF_SINGLE_URL, params={
            "ticker": "VTI", "fiat_amount": 100, "shares_acquired": 1,
            "fees": -1,
        })

        assert resp.status_code == 400
        assert _etf_rows(db_session) == []


class TestSummaryInvested:
    """The dashboard's ETF invested is net money put in, fees included
    (#52)."""

    def _summary_etf(self, db_session, ticker):
        with patch("app.core.investments.fetch_live_prices",
                   return_value={ticker: 120.0}):
            summary = get_portfolio_summary(db_session)
        return next(e for e in summary["etfs"] if e["ticker"] == ticker)

    def test_invested_includes_fees(self, db_session):
        db_session.add_all([
            EtfTransaction(ticker_symbol="EUNL.DE",
                           fiat_invested=Decimal("100.00"),
                           fees=Decimal("1.00"), shares_acquired=Decimal("1")),
            EtfTransaction(ticker_symbol="EUNL.DE",
                           fiat_invested=Decimal("-50.00"),
                           fees=Decimal("1.00"),
                           shares_acquired=Decimal("-0.5"))])
        db_session.flush()
        assert self._summary_etf(db_session, "EUNL.DE")[
            "total_invested"] == 52.0

    def test_missing_fees_count_as_zero(self, db_session):
        db_session.add(EtfTransaction(ticker_symbol="EUNL.DE",
                                      fiat_invested=Decimal("100.00"),
                                      shares_acquired=Decimal("1")))
        db_session.flush()
        # The ORM fills the column default for None, so write a real NULL
        db_session.query(EtfTransaction).update({EtfTransaction.fees: None})
        assert self._summary_etf(db_session, "EUNL.DE")[
            "total_invested"] == 100.0
