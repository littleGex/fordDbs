# tests/test_login_hardening.py
"""
Login attempt limits, session expiry, token invalidation and password
length (issue #17).
"""
import pytest
from datetime import datetime, timedelta, timezone

from jose import jwt

from app import cli
from app.core.auth import SECRET_KEY, ALGORITHM
from app.core import rate_limit

pytestmark = pytest.mark.integration

BASE = "/v1/family-photos"
GOOD = "correct-horse"


def login(client, user, password=GOOD, address=None):
    headers = {"CF-Connecting-IP": address} if address else {}
    return client.post(f"{BASE}/login", headers=headers,
                       json={"user_id": user.id, "password": password})


def token_with(user, expires_in, **claims):
    return jwt.encode(
        {"sub": str(user.id),
         "exp": datetime.now(timezone.utc) + expires_in, **claims},
        SECRET_KEY, algorithm=ALGORITHM)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user(make_user):
    return make_user(username="dad", role="parent", password=GOOD)


class TestLoginAttemptLimit:

    def test_locked_after_five_wrong_passwords(self, client, user):
        for _ in range(5):
            assert login(client, user, "wrong").status_code == 401

        resp = login(client, user, "wrong")

        assert resp.status_code == 429
        assert "Try again in 15 minutes" in resp.json()["detail"]
        assert int(resp.headers["Retry-After"]) > 0

    def test_right_password_is_also_refused_while_locked(self, client, user):
        for _ in range(5):
            login(client, user, "wrong")

        assert login(client, user).status_code == 429

    def test_four_wrong_then_right_still_works_and_resets(self, client,
                                                          user):
        for _ in range(4):
            login(client, user, "wrong")

        assert login(client, user).status_code == 200
        # The count started again, so four more misses don't lock
        for _ in range(4):
            login(client, user, "wrong")
        assert login(client, user).status_code == 200

    def test_lock_is_per_device(self, client, user):
        for _ in range(5):
            login(client, user, "wrong", address="203.0.113.1")

        assert login(client, user, address="203.0.113.1").status_code == 429
        assert login(client, user, address="203.0.113.2").status_code == 200

    def test_lock_is_per_account(self, client, user, make_user):
        other = make_user(username="mum", password=GOOD)
        for _ in range(5):
            login(client, user, "wrong")

        assert login(client, other).status_code == 200

    def test_guessing_from_many_devices_locks_the_account(self, client,
                                                          user):
        for n in range(25):
            resp = login(client, user, "wrong", address=f"203.0.113.{n}")
            assert resp.status_code == 401

        assert login(client, user, address="198.51.100.9").status_code == 429

    def test_lock_expires(self, client, user, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(rate_limit.time, "monotonic",
                            lambda: clock["now"])
        for _ in range(5):
            login(client, user, "wrong")
        assert login(client, user).status_code == 429

        clock["now"] += 15 * 60 + 1

        assert login(client, user).status_code == 200

    def test_admin_password_reset_lifts_the_lock(self, client, client_for,
                                                 user, make_user):
        for _ in range(5):
            login(client, user, "wrong")
        admin = client_for(make_user(role="admin"))

        admin.post(f"{BASE}/admin/users/{user.id}/reset-password",
                   json={"password": "brand-new-pw"})

        assert login(client, user, "brand-new-pw").status_code == 200

    def test_missing_password_counts_as_wrong_not_a_crash(self, client,
                                                          user):
        resp = client.post(f"{BASE}/login", json={"user_id": user.id})

        assert resp.status_code == 401

    @pytest.mark.parametrize("user_id", [
        "admin' --", "1", 1.5, True, None, [1]])
    def test_non_numeric_user_id_is_rejected_not_a_crash(self, client,
                                                         user_id):
        resp = client.post(f"{BASE}/login",
                           json={"user_id": user_id, "password": GOOD})

        assert resp.status_code == 422


class TestRegistrationLimit:

    def register(self, client, n, address="203.0.113.1"):
        return client.post(f"{BASE}/users",
                           headers={"CF-Connecting-IP": address}, data={
                               "username": f"new{n}", "display_name": "New",
                               "password": "password1", "birth_year": 1980})

    def test_sixth_request_from_one_device_is_refused(self, client):
        for n in range(5):
            assert self.register(client, n).status_code == 200

        assert self.register(client, 5).status_code == 429
        assert self.register(client, 6,
                             address="203.0.113.2").status_code == 200

    def test_rejected_requests_do_not_use_up_the_allowance(self, client):
        for n in range(6):
            resp = client.post(f"{BASE}/users", data={
                "username": f"bad{n}", "display_name": "Bad",
                "password": "short", "birth_year": 1980})
            assert resp.status_code == 422


class TestPasswordLength:

    @pytest.mark.parametrize("password,status", [
        ("1234567", 422), ("12345678", 200)])
    def test_registration(self, client, password, status):
        resp = client.post(f"{BASE}/users", data={
            "username": "newbie", "display_name": "Newbie",
            "password": password, "birth_year": 1980})

        assert resp.status_code == status

    def test_admin_reset_rejects_a_short_password(self, client_for, user,
                                                  make_user):
        admin = client_for(make_user(role="admin"))

        resp = admin.post(f"{BASE}/admin/users/{user.id}/reset-password",
                          json={"password": "short"})

        assert resp.status_code == 422
        assert "at least 8" in resp.json()["detail"]

    def test_existing_short_passwords_still_log_in(self, client, make_user):
        child = make_user(username="kid", role="child", password="abc")

        assert login(client, child, "abc").status_code == 200


class TestSessionExpiry:

    def test_recently_expired_token_can_be_refreshed(self, client, user):
        token = token_with(user, -timedelta(days=29))

        resp = client.post(f"{BASE}/refresh", headers=bearer(token))

        assert resp.status_code == 200
        fresh = resp.json()["access_token"]
        assert client.get(f"{BASE}/feed",
                          headers=bearer(fresh)).status_code == 200

    def test_token_expired_over_30_days_ago_cannot_be_refreshed(
            self, client, user):
        token = token_with(user, -timedelta(days=31))

        resp = client.post(f"{BASE}/refresh", headers=bearer(token))

        assert resp.status_code == 401

    def test_expired_token_is_refused_on_normal_routes(self, client, user):
        token = token_with(user, -timedelta(minutes=1))

        assert client.get(f"{BASE}/feed",
                          headers=bearer(token)).status_code == 401


class TestTokenVersion:

    def test_tokens_issued_before_versions_existed_keep_working(
            self, client, user):
        legacy = token_with(user, timedelta(hours=1))  # no "ver" claim

        assert client.get(f"{BASE}/feed",
                          headers=bearer(legacy)).status_code == 200

    def test_admin_reset_logs_the_user_out_everywhere(
            self, client, client_for, user, make_user):
        old = login(client, user).json()["access_token"]
        expired_old = token_with(user, -timedelta(days=1), ver=0)
        admin = client_for(make_user(role="admin"))

        admin.post(f"{BASE}/admin/users/{user.id}/reset-password",
                   json={"password": "brand-new-pw"})

        assert client.get(f"{BASE}/feed",
                          headers=bearer(old)).status_code == 401
        assert client.get(f"{BASE}/me",
                          headers=bearer(old)).status_code == 401
        assert client.post(f"{BASE}/refresh",
                           headers=bearer(expired_old)).status_code == 401
        new = login(client, user, "brand-new-pw").json()["access_token"]
        assert client.get(f"{BASE}/feed",
                          headers=bearer(new)).status_code == 200

    def test_resetting_one_user_does_not_log_out_another(
            self, client, client_for, user, make_user):
        other = make_user(username="mum", password=GOOD)
        others_token = login(client, other).json()["access_token"]
        admin = client_for(make_user(role="admin"))

        admin.post(f"{BASE}/admin/users/{user.id}/reset-password",
                   json={"password": "brand-new-pw"})

        assert client.get(f"{BASE}/feed",
                          headers=bearer(others_token)).status_code == 200

    def test_refreshed_token_carries_the_current_version(self, client, user):
        token = login(client, user).json()["access_token"]

        fresh = client.post(f"{BASE}/refresh",
                            headers=bearer(token)).json()["access_token"]

        assert jwt.decode(fresh, SECRET_KEY,
                          algorithms=[ALGORITHM])["ver"] == 0

    def test_cli_reset_logs_the_user_out_and_enforces_length(
            self, client, user, db_session, monkeypatch):
        monkeypatch.setattr(cli, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        old = login(client, user).json()["access_token"]

        with pytest.raises(SystemExit):
            cli.main(["reset-password", "dad", "--password", "short"])
        assert client.get(f"{BASE}/feed",
                          headers=bearer(old)).status_code == 200

        cli.main(["reset-password", "dad", "--password", "long-enough"])

        assert client.get(f"{BASE}/feed",
                          headers=bearer(old)).status_code == 401
