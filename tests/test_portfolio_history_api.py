"""
API tests for GET /v1/investments/etf/history (#52). The price cache
fill and live prices are patched, so these never touch the network.
"""
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.models.shares_models import EtfTransaction

URL = "/v1/investments/etf/history"
MODULE = "app.api.v1.portfolio_history"


@pytest.fixture
def patched():
    with patch(f"{MODULE}.ensure_price_history", return_value={}) as ensure, \
            patch(f"{MODULE}.fetch_live_prices",
                  return_value={"EUNL.DE": 120.0}) as live, \
            patch(f"{MODULE}.berlin_today", return_value=date(2026, 3, 3)):
        yield ensure, live


def test_returns_points_stale_and_as_of(parent_client, db_session, patched):
    ensure, _ = patched
    ensure.return_value = {"SMC.PA": date(2026, 3, 1), "ABC.DE": None}
    db_session.add(EtfTransaction(
        ticker_symbol="EUNL.DE", transaction_date=datetime(2026, 3, 2),
        fiat_invested=Decimal("100"), shares_acquired=Decimal("1")))
    db_session.flush()

    resp = parent_client.get(URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"points", "stale", "as_of"}
    assert body["as_of"] == "2026-03-03"
    assert body["stale"] == [{"ticker": "ABC.DE", "through": None},
                             {"ticker": "SMC.PA", "through": "2026-03-01"}]
    assert body["points"][-1] == {"date": "2026-03-03", "value": 120.0,
                                  "invested": 100.0}


def test_empty_portfolio(parent_client, patched):
    resp = parent_client.get(URL)

    assert resp.status_code == 200, resp.text
    assert resp.json()["points"] == []
    assert resp.json()["stale"] == []


def test_requires_login(client):
    assert client.get(URL).status_code == 401
