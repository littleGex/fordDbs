# tests/test_pocket_money_wishes.py
"""Tests for the wish-list endpoints."""
import pytest

pytestmark = pytest.mark.integration


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
