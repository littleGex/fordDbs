# tests/test_pocket_money_deductions.py
"""
Tests for the deduction catalog CRUD and the batch deduction endpoint.

Includes a named regression test for a bug found during code review:
`deduct_batch` originally accessed `DeductionItem` (a Pydantic model)
using dict-style subscripting (`i['name']`), which raises
`TypeError: 'DeductionItem' object is not subscriptable` against any
real request — the function had never actually been exercised
end-to-end before. The fix uses attribute access (`i.name`).
"""
import pytest

pytestmark = pytest.mark.integration


class TestDeductionTypeCRUD:

    def test_create_deduction_type(self, client, admin_password):
        resp = client.post(
            "/v1/pocket-money/deductions",
            params={"password": admin_password},
            json={"name": "Unmade Bed", "default_amount": 0.50},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Unmade Bed"
        assert float(body["default_amount"]) == 0.50

    def test_create_duplicate_deduction_type_rejected(
        self, client, admin_password, make_deduction_type
    ):
        make_deduction_type(name="Unmade Bed")

        resp = client.post(
            "/v1/pocket-money/deductions",
            params={"password": admin_password},
            json={"name": "Unmade Bed", "default_amount": 1.00},
        )

        assert resp.status_code == 400

    def test_create_deduction_type_wrong_password_rejected(self, client):
        resp = client.post(
            "/v1/pocket-money/deductions",
            params={"password": "wrong"},
            json={"name": "Unmade Bed", "default_amount": 0.50},
        )

        assert resp.status_code == 403

    def test_get_deduction_types(self, client, make_deduction_type):
        make_deduction_type(name="Unmade Bed", default_amount="0.50")
        make_deduction_type(name="Dirty Dishes", default_amount="0.25")

        resp = client.get("/v1/pocket-money/deductions")

        assert resp.status_code == 200
        names = {d["name"] for d in resp.json()}
        assert {"Unmade Bed", "Dirty Dishes"}.issubset(names)

    def test_update_deduction_type(
        self, client, admin_password, make_deduction_type
    ):
        dtype = make_deduction_type(name="Unmade Bed", default_amount="0.50")

        resp = client.patch(
            f"/v1/pocket-money/deductions/{dtype.id}",
            params={"password": admin_password},
            json={"default_amount": 0.75},
        )

        assert resp.status_code == 200
        assert float(resp.json()["default_amount"]) == 0.75

    def test_delete_deduction_type(
        self, client, admin_password, make_deduction_type
    ):
        dtype = make_deduction_type(name="Unmade Bed")

        resp = client.delete(
            f"/v1/pocket-money/deductions/{dtype.id}",
            params={"password": admin_password},
        )

        assert resp.status_code == 200


class TestDeductBatchRegression:
    """
    Named regression suite for the deduct_batch dict-subscript bug.
    """

    def test_deduct_batch_does_not_raise_type_error(
        self, client, admin_password, make_child
    ):
        """
        REGRESSION: previously raised
        `TypeError: 'DeductionItem' object is not subscriptable`
        on every real call, because the items were accessed as
        `i['name']` instead of `i.name`. This test would have failed
        loudly against the original code.
        """
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/deduct-batch/{child.id}",
            params={"password": admin_password},
            json=[
                {"name": "Unmade Bed", "count": 1, "total": 0.50},
                {"name": "Dirty Dishes", "count": 2, "total": 0.50},
            ],
        )

        assert resp.status_code == 200, resp.text

    def test_deduct_batch_withdraws_sum_of_totals(
        self, client, admin_password, make_child
    ):
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/deduct-batch/{child.id}",
            params={"password": admin_password},
            json=[
                {"name": "Unmade Bed", "count": 1, "total": 0.50},
                {"name": "Dirty Dishes", "count": 2, "total": 0.50},
            ],
        )

        assert resp.status_code == 200
        # 10.00 - (0.50 + 0.50) = 9.00
        assert resp.json()["new_balance"] == 9.00

    def test_deduct_batch_description_includes_item_names(
        self, client, admin_password, make_child, db_session
    ):
        from app.models.user_models import Transaction

        child = make_child(balance="10.00")
        client.post(
            f"/v1/pocket-money/deduct-batch/{child.id}",
            params={"password": admin_password},
            json=[{"name": "Unmade Bed", "count": 1, "total": 0.50}],
        )

        txn = (
            db_session.query(Transaction)
            .filter(
                Transaction.child_id == child.id,
                Transaction.category == "Behaviour Deductions",
            )
            .first()
        )
        assert txn is not None
        assert "Unmade Bed" in txn.description

    def test_deduct_batch_insufficient_funds_rejected(
        self, client, admin_password, make_child
    ):
        child = make_child(balance="0.50")

        resp = client.post(
            f"/v1/pocket-money/deduct-batch/{child.id}",
            params={"password": admin_password},
            json=[{"name": "Big Fine", "count": 1, "total": 5.00}],
        )

        assert resp.status_code == 422

    def test_deduct_batch_wrong_password_rejected(self, client, make_child):
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/deduct-batch/{child.id}",
            params={"password": "wrong"},
            json=[{"name": "Unmade Bed", "count": 1, "total": 0.50}],
        )

        assert resp.status_code == 403
