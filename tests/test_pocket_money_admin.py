# tests/test_pocket_money_admin.py
"""
Tests for child management endpoints on the pocket money router.
Login and role checks live in test_pocket_money_auth.py.
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def client(parent_client):
    """Every pocket-money route needs a login; default to a parent."""
    return parent_client


class TestAddChild:

    def test_add_child_with_birth_date(self, client):
        resp = client.post(
            "/v1/pocket-money/add-child/Penelope",
            params={"birth_date": "2016-03-15"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Penelope"
        assert body["balance"] == 0.0

    def test_add_child_without_birth_date(self, client):
        resp = client.post(
            "/v1/pocket-money/add-child/Dominic",
        )

        assert resp.status_code == 200
        assert resp.json()["birth_date"] is None


class TestGetChildren:

    def test_get_all_children(self, client, make_child):
        make_child(name="Penelope")
        make_child(name="Dominic")

        resp = client.get("/v1/pocket-money/children")

        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert {"Penelope", "Dominic"}.issubset(names)

    def test_get_child_id_by_name(self, client, make_child):
        child = make_child(name="Penelope")

        resp = client.get("/v1/pocket-money/child-id/Penelope")

        assert resp.status_code == 200
        assert resp.json() == {"id": child.id, "name": "Penelope"}

    def test_get_child_id_unknown_name_returns_404(self, client):
        resp = client.get("/v1/pocket-money/child-id/NoSuchChild")
        assert resp.status_code == 404


class TestUpdateChild:

    def test_update_child_name(self, client, make_child):
        child = make_child(name="OldName")

        resp = client.patch(
            f"/v1/pocket-money/child/{child.id}",
            params={"name": "NewName"},
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    def test_update_unknown_child_returns_404(self, client):
        resp = client.patch(
            "/v1/pocket-money/child/999999",
            params={"name": "NewName"},
        )

        assert resp.status_code == 404


class TestDeleteChild:

    def test_delete_child(self, client, make_child):
        child = make_child(name="ToDelete")

        resp = client.delete(
            f"/v1/pocket-money/child/{child.id}",
        )

        assert resp.status_code == 200

        # confirm it's actually gone
        follow_up = client.get("/v1/pocket-money/child-id/ToDelete")
        assert follow_up.status_code == 404

    def test_delete_unknown_child_returns_404(self, client):
        resp = client.delete(
            "/v1/pocket-money/child/999999",
        )

        assert resp.status_code == 404
