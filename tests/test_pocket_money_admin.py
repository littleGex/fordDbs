# tests/test_pocket_money_admin.py
"""
Tests for child management endpoints and admin-password protection
across the pocket money router.
"""
import pytest

pytestmark = pytest.mark.integration


class TestAddChild:

    def test_add_child_with_correct_password(self, client, admin_password):
        resp = client.post(
            "/v1/pocket-money/add-child/Penelope",
            params={"password": admin_password, "birth_date": "2016-03-15"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Penelope"
        assert body["balance"] == 0.0

    def test_add_child_without_birth_date(self, client, admin_password):
        resp = client.post(
            "/v1/pocket-money/add-child/Dominic",
            params={"password": admin_password},
        )

        assert resp.status_code == 200
        assert resp.json()["birth_date"] is None

    def test_add_child_wrong_password_rejected(self, client):
        resp = client.post(
            "/v1/pocket-money/add-child/Intruder",
            params={"password": "not-the-password"},
        )

        assert resp.status_code == 403


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

    def test_update_child_name(self, client, make_child, admin_password):
        child = make_child(name="OldName")

        resp = client.patch(
            f"/v1/pocket-money/child/{child.id}",
            params={"name": "NewName", "password": admin_password},
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    def test_update_child_wrong_password_rejected(self, client, make_child):
        child = make_child(name="OldName")

        resp = client.patch(
            f"/v1/pocket-money/child/{child.id}",
            params={"name": "NewName", "password": "wrong"},
        )

        assert resp.status_code == 403

    def test_update_unknown_child_returns_404(self, client, admin_password):
        resp = client.patch(
            "/v1/pocket-money/child/999999",
            params={"name": "NewName", "password": admin_password},
        )

        assert resp.status_code == 404


class TestDeleteChild:

    def test_delete_child(self, client, make_child, admin_password):
        child = make_child(name="ToDelete")

        resp = client.delete(
            f"/v1/pocket-money/child/{child.id}",
            params={"password": admin_password},
        )

        assert resp.status_code == 200

        # confirm it's actually gone
        follow_up = client.get("/v1/pocket-money/child-id/ToDelete")
        assert follow_up.status_code == 404

    def test_delete_child_wrong_password_rejected(self, client, make_child):
        child = make_child(name="ToDelete")

        resp = client.delete(
            f"/v1/pocket-money/child/{child.id}",
            params={"password": "wrong"},
        )

        assert resp.status_code == 403

    def test_delete_unknown_child_returns_404(self, client, admin_password):
        resp = client.delete(
            "/v1/pocket-money/child/999999",
            params={"password": admin_password},
        )

        assert resp.status_code == 404


class TestVerifyAdmin:

    def test_correct_password_authenticates(self, client, admin_password):
        resp = client.post(
            "/v1/pocket-money/verify-admin",
            params={"password": admin_password},
        )

        assert resp.status_code == 200
        assert resp.json()["success"] == "authenticated"

    def test_wrong_password_returns_401(self, client):
        resp = client.post(
            "/v1/pocket-money/verify-admin",
            params={"password": "wrong"},
        )

        assert resp.status_code == 401
