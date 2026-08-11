# tests/test_pocket_money_wishes.py
"""Tests for the wish-list endpoints."""
import pytest
from decimal import Decimal

pytestmark = pytest.mark.integration


class TestWishCostPrecision:
    """
    Regression tests for Wish.cost: it was a Float column even after
    Child.balance/Transaction.amount/DeductionType.default_amount were
    all migrated to Numeric(10, 2) -- flagged as a known gap in
    README.md, now fixed. Unlike the original balance-drift bug (which
    only showed up after repeated addition), a single Float value often
    round-trips fine through Postgres, so the meaningful regression
    check here is the column's actual type, not a specific "unlucky"
    number.
    """

    def test_cost_column_is_numeric_not_float(self, db_session):
        from sqlalchemy import inspect

        columns = {c["name"]: c for c in
                  inspect(db_session.bind).get_columns("wishes")}
        assert str(columns["cost"]["type"]) == "NUMERIC(10, 2)"

    def test_stored_cost_round_trips_as_exact_decimal(
        self, client, make_child, db_session
    ):
        from app.models.user_models import Wish

        child = make_child()
        wish_id = client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Lego Set", "cost": 19.99},
        ).json()["id"]

        # Fresh query, same as any other request would do -- not the
        # same in-memory object add_wish returned.
        db_session.expire_all()
        wish = db_session.query(Wish).filter(Wish.id == wish_id).first()

        assert wish.cost == Decimal("19.99")
        assert isinstance(wish.cost, Decimal)


class TestAddWish:

    def test_add_wish(self, client, make_child):
        child = make_child()

        resp = client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Lego Set", "cost": 29.99},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["item_name"] == "Lego Set"
        assert float(body["cost"]) == 29.99

    def test_add_wish_rejects_negative_cost(self, client, make_child):
        child = make_child()

        resp = client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Mystery Item", "cost": -5.00},
        )

        assert resp.status_code == 422


class TestGetWishes:

    def test_get_wishes_for_child(self, client, make_child):
        child = make_child()
        client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Lego Set", "cost": 29.99},
        )
        client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Bike", "cost": 150.00},
        )

        resp = client.get(f"/v1/pocket-money/wishes/{child.id}")

        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_wishes_empty_for_new_child(self, client, make_child):
        child = make_child()

        resp = client.get(f"/v1/pocket-money/wishes/{child.id}")

        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateWish:

    def test_update_wish_cost(self, client, make_child):
        child = make_child()
        created = client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Lego Set", "cost": 29.99},
        ).json()

        resp = client.patch(
            f"/v1/pocket-money/wish/{created['id']}",
            params={"cost": 24.99},
        )

        assert resp.status_code == 200
        assert float(resp.json()["cost"]) == 24.99

    def test_update_wish_rejects_negative_cost(self, client, make_child):
        child = make_child()
        created = client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Lego Set", "cost": 29.99},
        ).json()

        resp = client.patch(
            f"/v1/pocket-money/wish/{created['id']}",
            params={"cost": -10.00},
        )

        assert resp.status_code == 422

    def test_update_unknown_wish_returns_404(self, client):
        resp = client.patch(
            "/v1/pocket-money/wish/999999",
            params={"cost": 10.00},
        )

        assert resp.status_code == 404


class TestDeleteWish:

    def test_delete_wish(self, client, make_child):
        child = make_child()
        created = client.post(
            f"/v1/pocket-money/wish/{child.id}",
            params={"item_name": "Lego Set", "cost": 29.99},
        ).json()

        resp = client.delete(f"/v1/pocket-money/wish/{created['id']}")

        assert resp.status_code == 200

        follow_up = client.get(f"/v1/pocket-money/wishes/{child.id}")
        assert follow_up.json() == []

    def test_delete_unknown_wish_returns_404(self, client):
        resp = client.delete("/v1/pocket-money/wish/999999")
        assert resp.status_code == 404
