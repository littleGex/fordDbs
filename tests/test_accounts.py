# tests/test_accounts.py
"""
Self-registration with admin approval, the admin/parent/adult/child
roles, and the server-side recovery command (app/cli.py).
"""
import pytest
from datetime import datetime, timezone

from app import cli
from app.core.auth import verify_pw
from app.models.user_models import User

pytestmark = pytest.mark.integration

BASE = "/v1/family-photos"
THIS_YEAR = datetime.now(timezone.utc).year


def register(client, name="Newbie", birth_year=1980, **extra):
    return client.post(f"{BASE}/users", data={
        "username": name.lower(), "display_name": name,
        "password": "pw", "birth_year": birth_year, **extra})


@pytest.fixture
def admin_client(client_for, make_user):
    return client_for(make_user(username="boss", role="admin"))


class TestRegistration:

    def test_registration_creates_a_pending_account(self, client,
                                                    db_session):
        resp = register(client)

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        user = db_session.query(User).filter_by(username="newbie").one()
        assert user.status == "pending"

    @pytest.mark.parametrize("age,role", [
        (40, "adult"), (18, "adult"), (17, "child"), (6, "child")])
    def test_birth_year_picks_child_or_adult(self, client, db_session,
                                             age, role):
        register(client, birth_year=THIS_YEAR - age)

        user = db_session.query(User).filter_by(username="newbie").one()
        assert user.role == role

    def test_caller_cannot_choose_a_role(self, client, db_session):
        register(client, role="parent")

        user = db_session.query(User).filter_by(username="newbie").one()
        assert user.role == "adult"

    def test_birth_year_is_required(self, client):
        resp = client.post(f"{BASE}/users", data={
            "username": "x", "display_name": "X", "password": "pw"})

        assert resp.status_code == 422

    @pytest.mark.parametrize("birth_year", [1800, THIS_YEAR + 1])
    def test_implausible_birth_year_rejected(self, client, birth_year):
        assert register(client, birth_year=birth_year).status_code == 422

    def test_duplicate_username_rejected(self, client, make_user):
        make_user(username="newbie")

        assert register(client).status_code == 400

    def test_pending_requests_are_capped(self, client, make_user):
        for n in range(10):
            make_user(username=f"waiting{n}", status="pending")

        assert register(client).status_code == 429

    def test_pending_account_cannot_log_in(self, client, db_session):
        register(client)
        user = db_session.query(User).filter_by(username="newbie").one()

        resp = client.post(f"{BASE}/login",
                           json={"user_id": user.id, "password": "pw"})

        assert resp.status_code == 403
        assert "waiting for approval" in resp.json()["detail"]

    def test_pending_account_is_not_listed(self, client, admin_client):
        register(client)

        options = client.get(f"{BASE}/login-options").json()
        users = admin_client.get(f"{BASE}/users").json()

        assert "Newbie" not in [u["display_name"] for u in options]
        assert "newbie" not in [u["username"] for u in users]

    def test_token_of_a_deactivated_account_stops_working(
            self, client_for, make_user, db_session):
        user = make_user(role="adult")
        client = client_for(user)
        user.status = "pending"
        db_session.commit()

        assert client.get(f"{BASE}/feed").status_code == 401

    def test_set_password_route_is_gone(self, client, make_user):
        user = make_user()

        resp = client.post(f"{BASE}/users/set-password",
                           json={"user_id": user.id, "password": "x"})

        assert resp.status_code in (404, 405)

    def test_account_without_password_cannot_log_in(self, client,
                                                    make_user):
        user = make_user()

        resp = client.post(f"{BASE}/login",
                           json={"user_id": user.id, "password": "x"})

        assert resp.status_code == 403


class TestApproval:

    def test_admin_sees_pending_requests(self, admin_client, make_user):
        waiting = make_user(username="newbie", role="adult",
                            status="pending")
        make_user(username="regular")

        resp = admin_client.get(f"{BASE}/admin/pending")

        assert resp.status_code == 200
        assert [u["id"] for u in resp.json()] == [waiting.id]

    def test_approve_activates_and_allows_login(self, client, admin_client,
                                                db_session):
        register(client)
        user = db_session.query(User).filter_by(username="newbie").one()

        approved = admin_client.post(
            f"{BASE}/admin/users/{user.id}/approve")
        login = client.post(f"{BASE}/login",
                            json={"user_id": user.id, "password": "pw"})

        assert approved.status_code == 200
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "adult"

    def test_approve_can_correct_the_suggested_role(self, admin_client,
                                                    make_user, db_session):
        user = make_user(role="adult", status="pending")

        resp = admin_client.post(f"{BASE}/admin/users/{user.id}/approve",
                                 json={"role": "child"})

        assert resp.json()["role"] == "child"
        db_session.refresh(user)
        assert (user.role, user.status) == ("child", "active")

    @pytest.mark.parametrize("role", ["parent", "admin", "wizard"])
    def test_approve_cannot_hand_out_parent_or_admin(self, admin_client,
                                                     make_user, db_session,
                                                     role):
        user = make_user(role="adult", status="pending")

        resp = admin_client.post(f"{BASE}/admin/users/{user.id}/approve",
                                 json={"role": role})

        assert resp.status_code == 422
        db_session.refresh(user)
        assert user.status == "pending"

    def test_reject_deletes_the_pending_account(self, admin_client,
                                                make_user, db_session):
        user = make_user(username="newbie", status="pending")

        resp = admin_client.post(f"{BASE}/admin/users/{user.id}/reject")

        assert resp.status_code == 200
        assert db_session.query(User).filter_by(
            username="newbie").first() is None

    @pytest.mark.parametrize("action", ["approve", "reject"])
    def test_active_accounts_cannot_be_approved_or_rejected(
            self, admin_client, make_user, db_session, action):
        user = make_user(username="regular")

        resp = admin_client.post(f"{BASE}/admin/users/{user.id}/{action}")

        assert resp.status_code == 400
        assert db_session.query(User).filter_by(
            username="regular").first() is not None


class TestRoleChange:

    @pytest.mark.parametrize("role", ["child", "adult", "parent"])
    def test_admin_can_set_a_role(self, admin_client, make_user, role):
        user = make_user(role="adult")

        resp = admin_client.post(f"{BASE}/admin/users/{user.id}/role",
                                 json={"role": role})

        assert resp.status_code == 200
        assert resp.json()["role"] == role

    def test_admin_role_cannot_be_granted_from_the_api(self, admin_client,
                                                       make_user):
        user = make_user(role="parent")

        resp = admin_client.post(f"{BASE}/admin/users/{user.id}/role",
                                 json={"role": "admin"})

        assert resp.status_code == 422

    def test_an_admins_role_cannot_be_changed(self, client_for, make_user,
                                              db_session):
        admin = make_user(role="admin")

        resp = client_for(admin).post(
            f"{BASE}/admin/users/{admin.id}/role", json={"role": "adult"})

        assert resp.status_code == 403
        db_session.refresh(admin)
        assert admin.role == "admin"

    def test_admin_can_reset_a_password(self, client, admin_client,
                                        make_user):
        user = make_user(password="old")

        reset = admin_client.post(
            f"{BASE}/admin/users/{user.id}/reset-password",
            json={"password": "new"})
        login = client.post(f"{BASE}/login",
                            json={"user_id": user.id, "password": "new"})

        assert reset.status_code == 200
        assert login.status_code == 200


ADMIN_ROUTES = [
    ("get", "/admin/pending", None),
    ("post", "/admin/users/{id}/approve", None),
    ("post", "/admin/users/{id}/reject", None),
    ("post", "/admin/users/{id}/role", {"role": "adult"}),
    ("post", "/admin/users/{id}/reset-password", {"password": "x"}),
]


class TestAdminOnly:

    @pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
    def test_no_token_returns_401(self, client, make_user, method, path,
                                  body):
        target = make_user(status="pending")

        resp = getattr(client, method)(
            BASE + path.replace("{id}", str(target.id)))

        assert resp.status_code == 401

    @pytest.mark.parametrize("role", ["parent", "adult", "child"])
    @pytest.mark.parametrize("method,path,body", ADMIN_ROUTES)
    def test_non_admins_get_403(self, client_for, make_user, db_session,
                                role, method, path, body):
        target = make_user(status="pending")
        client = client_for(make_user(role=role))
        kwargs = {"json": body} if body else {}

        resp = getattr(client, method)(
            BASE + path.replace("{id}", str(target.id)), **kwargs)

        assert resp.status_code == 403
        db_session.refresh(target)
        assert target.status == "pending"


class TestRoleAbilities:

    def test_adult_cannot_manage_pocket_money(self, client_for, make_user,
                                              make_child):
        child = make_child(name="Kid", balance="10.00")
        client = client_for(make_user(role="adult"))

        assert client.get("/v1/pocket-money/children").json() == []
        assert client.get(
            f"/v1/pocket-money/history/{child.id}").status_code == 403
        assert client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 1, "description": "x"}).status_code == 403
        assert client.get("/v1/pocket-money/deductions").status_code == 403

    def test_adult_can_use_fordstagram(self, client_for, make_user):
        client = client_for(make_user(role="adult"))

        assert client.get(f"{BASE}/feed").status_code == 200

    def test_admin_passes_parent_checks(self, admin_client, make_child):
        make_child(name="Kid")

        assert admin_client.get(
            "/v1/pocket-money/deductions").status_code == 200
        assert len(admin_client.get(
            "/v1/pocket-money/children").json()) == 1

    @pytest.mark.parametrize("role,expected", [
        ("admin", 200), ("parent", 200), ("adult", 403), ("child", 403)])
    def test_only_parents_and_admin_delete_others_photos(
            self, client_for, make_user, make_photo, minio_test_bucket,
            role, expected):
        photo = make_photo(make_user(username="uploader"))

        resp = client_for(make_user(role=role)).delete(
            f"{BASE}/{photo.id}")

        assert resp.status_code == expected


class TestRecoveryCli:
    """app/cli.py opens its own session, so point it at the test one."""

    @pytest.fixture(autouse=True)
    def use_test_session(self, monkeypatch, db_session):
        monkeypatch.setattr(cli, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)

    def test_reset_password(self, make_user, db_session):
        user = make_user(username="dad", password="forgotten")

        cli.main(["reset-password", "dad", "--password", "fresh"])

        db_session.refresh(user)
        assert verify_pw("fresh", user.hashed_password)

    def test_set_role_can_make_an_admin(self, make_user, db_session):
        user = make_user(username="dad", role="parent")

        cli.main(["set-role", "dad", "admin"])

        db_session.refresh(user)
        assert user.role == "admin"

    def test_activate(self, make_user, db_session):
        user = make_user(username="newbie", status="pending")

        cli.main(["activate", "newbie"])

        db_session.refresh(user)
        assert user.status == "active"

    def test_create_user_for_a_fresh_install(self, db_session):
        cli.main(["create-user", "dad", "Dad", "admin",
                  "--password", "first"])

        user = db_session.query(User).filter_by(username="dad").one()
        assert (user.role, user.status) == ("admin", "active")
        assert verify_pw("first", user.hashed_password)

    def test_unknown_user_exits_with_a_message(self):
        with pytest.raises(SystemExit) as exc:
            cli.main(["activate", "nobody"])

        assert "nobody" in str(exc.value)
