# tests/test_pocket_money_auth.py
"""
Login and role checks on the pocket money router: every route needs a
token, parents can do everything, a child can only see their own
profile, and other backends (the chore tracker) may look up a child and
deposit using a service key.
"""
import pytest
from decimal import Decimal

from app.models.user_models import Wish

pytestmark = pytest.mark.integration

SERVICE_KEY = "test-service-key"

# (method, path, kwargs) for every pocket-money route; {id} is a child id
ALL_ROUTES = [
    ("get", "/balance/Kid", {}),
    ("patch", "/adjust-balance/{id}", {"params": {"new_balance": 1}}),
    ("post", "/add-child/New", {}),
    ("get", "/children", {}),
    ("get", "/child-id/Kid", {}),
    ("patch", "/child/{id}", {"params": {"name": "X"}}),
    ("delete", "/child/{id}", {}),
    ("post", "/adjust/{id}", {"params": {
        "amount": 1, "description": "d", "category": "c"}}),
    ("post", "/deposit/{id}", {"params": {"amount": 1, "description": "d"}}),
    ("get", "/history/{id}", {}),
    ("post", "/withdraw/{id}", {"params": {"amount": 1, "description": "d"}}),
    ("get", "/wishes/{id}", {}),
    ("post", "/wish/{id}", {"params": {"item_name": "Bike", "cost": 1}}),
    ("get", "/stats/{id}", {}),
    ("delete", "/wish/1", {}),
    ("patch", "/wish/1", {"params": {"cost": 1}}),
    ("get", "/deductions", {}),
    ("post", "/deduct-batch/{id}", {"json": []}),
    ("post", "/deductions", {"json": {"name": "N", "default_amount": 1}}),
    ("patch", "/deductions/1", {"json": {"name": "N"}}),
    ("delete", "/deductions/1", {}),
]

# Routes a child may never call, even for their own profile
PARENT_ONLY_ROUTES = [
    r for r in ALL_ROUTES
    if r[1] not in ("/balance/Kid", "/children", "/history/{id}",
                    "/wishes/{id}", "/wish/{id}", "/stats/{id}",
                    "/wish/1")
]

# Routes a child may call, but only for their own profile
OWN_PROFILE_ROUTES = [
    ("get", "/history/{id}", {}),
    ("get", "/wishes/{id}", {}),
    ("get", "/stats/{id}", {}),
    ("post", "/wish/{id}", {"params": {"item_name": "Bike", "cost": 1}}),
]


def call(client, method, path, kwargs, child_id=1, **extra):
    url = "/v1/pocket-money" + path.replace("{id}", str(child_id))
    return getattr(client, method)(url, **kwargs, **extra)


@pytest.fixture
def make_linked_child(db_session, make_child, make_user):
    """make_linked_child(name) -> (child, user): a child with a login."""
    def _make(name="Kid", balance="10.00"):
        user = make_user(role="child")
        child = make_child(name=name, balance=balance)
        child.user_id = user.id
        db_session.commit()
        return child, user

    return _make


@pytest.fixture
def service_key(monkeypatch):
    monkeypatch.setenv("POCKET_MONEY_SERVICE_KEY", SERVICE_KEY)
    return {"X-Service-Key": SERVICE_KEY}


class TestLoginRequired:

    @pytest.mark.parametrize("method,path,kwargs", ALL_ROUTES)
    def test_no_token_returns_401(self, client, method, path, kwargs):
        assert call(client, method, path, kwargs).status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/v1/pocket-money/children",
                          headers={"Authorization": "Bearer not-a-token"})
        assert resp.status_code == 401

    def test_verify_admin_is_gone(self, parent_client):
        resp = parent_client.post("/v1/pocket-money/verify-admin",
                                  params={"password": "anything"})
        assert resp.status_code == 404

    def test_old_admin_password_no_longer_grants_access(
        self, client, make_child, admin_password
    ):
        child = make_child(name="Kid", balance="10.00")

        resp = client.delete(f"/v1/pocket-money/child/{child.id}",
                             params={"password": admin_password})

        assert resp.status_code == 401


class TestChildRole:

    @pytest.mark.parametrize("method,path,kwargs", PARENT_ONLY_ROUTES)
    def test_parent_only_routes_return_403_for_own_profile(
        self, client_for, make_linked_child, method, path, kwargs
    ):
        child, user = make_linked_child()

        resp = call(client_for(user), method, path, kwargs, child.id)

        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path,kwargs", OWN_PROFILE_ROUTES)
    def test_child_can_use_own_profile(
        self, client_for, make_linked_child, method, path, kwargs
    ):
        child, user = make_linked_child()

        resp = call(client_for(user), method, path, kwargs, child.id)

        assert resp.status_code == 200

    @pytest.mark.parametrize("method,path,kwargs", OWN_PROFILE_ROUTES)
    def test_child_cannot_use_a_siblings_profile(
        self, client_for, make_linked_child, method, path, kwargs
    ):
        _, user = make_linked_child(name="Kid")
        sibling, _ = make_linked_child(name="Sibling")

        resp = call(client_for(user), method, path, kwargs, sibling.id)

        assert resp.status_code == 403

    def test_child_reads_own_balance_but_not_a_siblings(
        self, client_for, make_linked_child
    ):
        _, user = make_linked_child(name="Kid", balance="7.50")
        make_linked_child(name="Sibling")
        client = client_for(user)

        own = client.get("/v1/pocket-money/balance/Kid")
        other = client.get("/v1/pocket-money/balance/Sibling")
        unknown = client.get("/v1/pocket-money/balance/NoSuchChild")

        assert own.status_code == 200
        assert own.json() == {"name": "Kid", "balance": 7.5}
        assert other.status_code == 403
        assert unknown.status_code == 403

    def test_children_list_only_contains_own_profile(
        self, client_for, make_linked_child
    ):
        child, user = make_linked_child(name="Kid")
        make_linked_child(name="Sibling")

        resp = client_for(user).get("/v1/pocket-money/children")

        assert resp.status_code == 200
        assert [c["id"] for c in resp.json()] == [child.id]

    def test_child_without_a_linked_profile_sees_nothing(
        self, client_for, make_user, make_child
    ):
        child = make_child(name="Kid")
        client = client_for(make_user(role="child"))

        assert client.get("/v1/pocket-money/children").json() == []
        assert client.get(
            f"/v1/pocket-money/history/{child.id}").status_code == 403

    def test_child_can_edit_and_delete_only_own_wishes(
        self, client_for, make_linked_child, db_session
    ):
        child, user = make_linked_child(name="Kid")
        sibling, _ = make_linked_child(name="Sibling")
        own = Wish(child_id=child.id, item_name="Bike", cost=Decimal("50"))
        theirs = Wish(child_id=sibling.id, item_name="Doll",
                      cost=Decimal("20"))
        db_session.add_all([own, theirs])
        db_session.commit()
        client = client_for(user)

        assert client.patch(f"/v1/pocket-money/wish/{theirs.id}",
                            params={"cost": 1}).status_code == 403
        assert client.delete(
            f"/v1/pocket-money/wish/{theirs.id}").status_code == 403
        assert client.patch(f"/v1/pocket-money/wish/{own.id}",
                            params={"cost": 45}).status_code == 200
        assert client.delete(
            f"/v1/pocket-money/wish/{own.id}").status_code == 200

    def test_child_cannot_withdraw_own_money(
        self, client_for, make_linked_child, db_session
    ):
        child, user = make_linked_child(balance="10.00")

        resp = client_for(user).post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 5, "description": "Sweets"})

        assert resp.status_code == 403
        db_session.refresh(child)
        assert child.balance == Decimal("10.00")


class TestParentRoles:

    @pytest.mark.parametrize("role", ["parent", "admin"])
    def test_parent_and_admin_can_manage_any_child(
        self, client_for, make_user, make_child, role
    ):
        child = make_child(name="Kid", balance="10.00")
        client = client_for(make_user(role=role))

        listed = client.get("/v1/pocket-money/children")
        withdrawn = client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 4, "description": "Sweets"})

        assert [c["id"] for c in listed.json()] == [child.id]
        assert withdrawn.status_code == 200
        assert withdrawn.json()["new_balance"] == 6.0


class TestServiceKey:

    def test_service_key_can_look_up_and_deposit(
        self, client, make_child, service_key, db_session
    ):
        child = make_child(name="Kid", balance="10.00")

        lookup = client.get("/v1/pocket-money/child-id/Kid",
                            headers=service_key)
        deposit = client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 2.5, "description": "Chores"},
            headers=service_key)

        assert lookup.json() == {"id": child.id, "name": "Kid"}
        assert deposit.status_code == 200
        db_session.refresh(child)
        assert child.balance == Decimal("12.50")

    def test_wrong_service_key_returns_401(
        self, client, make_child, service_key
    ):
        make_child(name="Kid")

        resp = client.get("/v1/pocket-money/child-id/Kid",
                          headers={"X-Service-Key": "wrong"})

        assert resp.status_code == 401

    def test_service_key_rejected_when_not_configured(
        self, client, make_child, monkeypatch
    ):
        monkeypatch.delenv("POCKET_MONEY_SERVICE_KEY", raising=False)
        make_child(name="Kid")

        resp = client.get("/v1/pocket-money/child-id/Kid",
                          headers={"X-Service-Key": ""})

        assert resp.status_code == 401

    def test_wrong_service_key_does_not_fall_back_to_a_parent_token(
        self, parent_client, make_child, service_key
    ):
        make_child(name="Kid")

        resp = parent_client.get("/v1/pocket-money/child-id/Kid",
                                 headers={"X-Service-Key": "wrong"})

        assert resp.status_code == 401

    @pytest.mark.parametrize("method,path,kwargs", [
        r for r in ALL_ROUTES
        if r[1] not in ("/child-id/Kid", "/deposit/{id}")
    ])
    def test_service_key_is_not_accepted_on_other_routes(
        self, client, make_child, service_key, method, path, kwargs
    ):
        child = make_child(name="Kid", balance="10.00")

        resp = call(client, method, path, kwargs, child.id,
                    headers=service_key)

        assert resp.status_code == 401
