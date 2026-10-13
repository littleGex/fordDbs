# tests/test_household_auth.py
"""
Login and role checks on the investments and utilities routers: both are
parents (and admin) only.
"""
import pytest
from unittest.mock import patch

from app.models.shares_models import EtfPurchaseSchedule

pytestmark = pytest.mark.integration

ROUTES = [
    ("get", "/v1/investments/dashboard-summary", {}),
    ("post", "/v1/investments/shares/add", {"params": {
        "ticker": "ABC", "num_shares": 1, "vest_date": "2026-01-01",
        "purchase_price": 1}}),
    ("post", "/v1/investments/shares/bulk-add", {"json": {"csv_data": ""}}),
    ("post", "/v1/investments/etf/transaction", {"params": {
        "ticker": "ABC", "fiat_amount": 1, "shares_acquired": 1,
        "transaction_date": "2026-01-01"}}),
    ("get", "/v1/investments/etf/schedules", {}),
    ("post", "/v1/investments/etf/schedule", {"params": {
        "ticker": "ABC", "amount": 1, "day": 1}}),
    ("delete", "/v1/investments/etf/schedule/1", {}),
    ("patch", "/v1/investments/shares/update-ticker", {"params": {
        "old_ticker": "ABC", "new_ticker": "XYZ"}}),
    ("post", "/v1/utilities/add-util", {"params": {
        "util_date": "2026-01-01", "utility": "water",
        "util_reading": 1}}),
    ("get", "/v1/utilities/dashboard", {}),
    ("put", "/v1/utilities/update-reading", {"params": {
        "util_date": "2026-01-01", "utility": "water", "value": 1}}),
]


class TestParentsOnly:

    @pytest.mark.parametrize("method,path,kwargs", ROUTES)
    def test_no_token_returns_401(self, client, method, path, kwargs):
        assert getattr(client, method)(path, **kwargs).status_code == 401

    @pytest.mark.parametrize("role", ["adult", "child"])
    @pytest.mark.parametrize("method,path,kwargs", ROUTES)
    def test_adults_and_children_get_403(self, client_for, make_user,
                                         role, method, path, kwargs):
        client = client_for(make_user(role=role))

        assert getattr(client, method)(path, **kwargs).status_code == 403

    @pytest.mark.parametrize("role", ["parent", "admin"])
    def test_parents_and_admin_can_read_both_dashboards(
            self, client_for, make_user, role):
        client = client_for(make_user(role=role))

        with patch("app.core.investments.fetch_live_prices",
                   return_value={}):
            investments = client.get("/v1/investments/dashboard-summary")
        utilities = client.get("/v1/utilities/dashboard")

        assert investments.status_code == 200
        assert utilities.status_code == 200

    def test_parent_can_add_and_read_a_utility_reading(self, parent_client):
        added = parent_client.post("/v1/utilities/add-util", params={
            "util_date": "2026-01-01", "utility": "water",
            "util_reading": 12.5})

        assert added.status_code == 200
        dashboard = parent_client.get("/v1/utilities/dashboard").json()
        assert dashboard["latest"]["readings"]["water"] == 12.5

    def test_schedule_delete_needs_no_shared_password(
            self, parent_client, db_session):
        schedule = EtfPurchaseSchedule(ticker_symbol="ABC", fiat_amount=50,
                                       execution_day=1)
        db_session.add(schedule)
        db_session.commit()

        resp = parent_client.delete(
            f"/v1/investments/etf/schedule/{schedule.schedule_id}")

        assert resp.status_code == 200
        assert db_session.query(EtfPurchaseSchedule).count() == 0
