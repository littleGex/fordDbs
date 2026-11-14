"""
API tests for POST /v1/investments/etf/import/trade-republic (#45) and
the instruments' imported count. The lookups are patched to return
nothing, so these never touch the network.
"""
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.tr_import import ImportSaveError
from app.models.shares_models import EtfTransaction, Instrument

URL = "/v1/investments/etf/import/trade-republic"
SAMPLE = (Path(__file__).parent / "fixtures"
          / "tr_export_sample.csv").read_text()


@pytest.fixture(autouse=True)
def no_network():
    with patch("app.core.instruments.figi_tickers", lambda isin: []), \
            patch("app.core.instruments.yahoo_search", lambda isin: []):
        yield


def test_import_returns_counts(parent_client):
    resp = parent_client.post(URL, json={"csv_data": SAMPLE})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"imported", "skipped_duplicates", "ignored",
                         "unknown", "unresolved", "warnings", "dry_run"}
    assert body["imported"] == 6
    assert body["ignored"] == {"cash": 4, "liquidation cancelled": 1}
    assert body["unknown"] == [
        {"line": 19, "category": "CORPORATE_ACTION", "type": "SPLIT"}]
    assert body["dry_run"] is False


def test_dry_run_stores_nothing(parent_client, db_session):
    resp = parent_client.post(URL, json={"csv_data": SAMPLE,
                                         "dry_run": True})

    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 6
    assert resp.json()["dry_run"] is True
    assert db_session.query(EtfTransaction).count() == 0


def test_parse_error_is_400(parent_client):
    header = SAMPLE.splitlines()[0].replace(',"transaction_id"', "")
    resp = parent_client.post(URL, json={"csv_data": header + "\n"})

    assert resp.status_code == 400
    assert "transaction_id" in resp.json()["detail"]


def test_too_large_is_413(parent_client):
    from app.api.v1.tr_import import MAX_IMPORT_BYTES
    resp = parent_client.post(
        URL, json={"csv_data": "x" * (MAX_IMPORT_BYTES + 1)})

    assert resp.status_code == 413


def test_save_error_is_400(parent_client):
    message = "Could not save the import; nothing was imported"
    with patch("app.api.v1.tr_import.import_tr_export",
               side_effect=ImportSaveError(message)):
        resp = parent_client.post(URL, json={"csv_data": SAMPLE})

    assert resp.status_code == 400
    assert resp.json()["detail"] == message


def test_requires_login(client):
    assert client.post(URL, json={"csv_data": SAMPLE}).status_code == 401


def test_instruments_show_imported_count(parent_client, db_session):
    parent_client.post(URL, json={"csv_data": SAMPLE})
    db_session.add(Instrument(isin="IE00B5BMR087", yahoo_ticker="SXR8.DE",
                              currency="EUR", manual_override=False))
    db_session.flush()
    db_session.add(EtfTransaction(ticker_symbol="SXR8.DE",
                                  isin="IE00B5BMR087",
                                  fiat_invested=Decimal("10"),
                                  shares_acquired=Decimal("1")))
    db_session.flush()

    listed = {i["isin"]: i for i in
              parent_client.get("/v1/investments/instruments").json()}

    assert listed["IE00B4L5Y983"]["imported"] == 2
    assert listed["IE00B5BMR087"]["imported"] == 0
