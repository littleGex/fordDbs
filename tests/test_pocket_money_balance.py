# tests/test_pocket_money_balance.py
"""
Tests for the core balance-moving endpoints: deposit, withdraw,
adjust, adjust-balance, and balance lookup.
"""
import pytest

pytestmark = pytest.mark.integration


class TestDeposit:

    def test_deposit_increases_balance(self, client, make_child):
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 5.00, "description": "Pocket money"},
        )

        assert resp.status_code == 200
        assert resp.json()["new_balance"] == 15.00

    def test_deposit_creates_transaction_record(
        self, client, make_child, db_session
    ):
        from app.models.user_models import Transaction

        child = make_child(balance="0.00")
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 5.00, "description": "Pocket money"},
        )

        txn = (
            db_session.query(Transaction)
            .filter(Transaction.child_id == child.id)
            .first()
        )
        assert txn is not None
        assert txn.category == "Deposit"
        assert float(txn.amount) == 5.00

    def test_deposit_rejects_zero_amount(self, client, make_child):
        child = make_child(balance="0.00")

        resp = client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 0, "description": "Nothing"},
        )

        assert resp.status_code == 422

    def test_deposit_rejects_negative_amount(self, client, make_child):
        child = make_child(balance="0.00")

        resp = client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": -5.00, "description": "Should fail"},
        )

        assert resp.status_code == 422

    def test_deposit_unknown_child_returns_404(self, client):
        resp = client.post(
            "/v1/pocket-money/deposit/999999",
            params={"amount": 5.00, "description": "Ghost child"},
        )

        assert resp.status_code == 404

    def test_new_balance_is_json_number_not_string(self, client, make_child):
        """
        Guards against Decimal serializing as a JSON string instead of
        a number, which would break frontend numeric handling.
        """
        child = make_child(balance="0.00")

        resp = client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 5.00, "description": "Pocket money"},
        )

        assert isinstance(resp.json()["new_balance"], (int, float))


class TestWithdraw:

    def test_withdraw_decreases_balance(self, client, make_child):
        child = make_child(balance="20.00")

        resp = client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 8.50, "description": "Toy"},
        )

        assert resp.status_code == 200
        assert resp.json()["new_balance"] == 11.50

    def test_withdraw_creates_negative_transaction(
        self, client, make_child, db_session
    ):
        from app.models.user_models import Transaction

        child = make_child(balance="20.00")
        client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 8.50, "description": "Toy"},
        )

        txn = (
            db_session.query(Transaction)
            .filter(Transaction.child_id == child.id)
            .first()
        )
        assert float(txn.amount) == -8.50

    def test_withdraw_unknown_child_returns_404(self, client):
        resp = client.post(
            "/v1/pocket-money/withdraw/999999",
            params={"amount": 5.00, "description": "Ghost child"},
        )

        assert resp.status_code == 404

    def test_withdraw_response_includes_transaction_id(
        self, client, make_child
    ):
        child = make_child(balance="20.00")

        resp = client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 5.00, "description": "Toy"},
        )

        assert "transaction_id" in resp.json()
        assert resp.json()["transaction_id"] is not None


class TestAdjustBalance:

    def test_adjust_balance_sets_exact_value(self, client, make_child):
        child = make_child(balance="10.00")

        resp = client.patch(
            f"/v1/pocket-money/adjust-balance/{child.id}",
            params={"new_balance": 42.50},
        )

        assert resp.status_code == 200
        assert resp.json()["new_balance"] == 42.50

    def test_adjust_balance_rejects_negative(self, client, make_child):
        child = make_child(balance="10.00")

        resp = client.patch(
            f"/v1/pocket-money/adjust-balance/{child.id}",
            params={"new_balance": -5.00},
        )

        assert resp.status_code == 422

    def test_adjust_balance_creates_correction_transaction(
        self, client, make_child, db_session
    ):
        from app.models.user_models import Transaction

        child = make_child(balance="10.00")
        client.patch(
            f"/v1/pocket-money/adjust-balance/{child.id}",
            params={"new_balance": 25.00},
        )

        txn = (
            db_session.query(Transaction)
            .filter(
                Transaction.child_id == child.id,
                Transaction.category == "Correction",
            )
            .first()
        )
        assert txn is not None
        assert float(txn.amount) == 15.00  # 25.00 - 10.00

    def test_new_balance_is_json_number_not_string(self, client, make_child):
        child = make_child(balance="10.00")

        resp = client.patch(
            f"/v1/pocket-money/adjust-balance/{child.id}",
            params={"new_balance": 25.00},
        )

        assert isinstance(resp.json()["new_balance"], (int, float))


class TestAdjustMoney:
    """Tests for the /adjust/{child_id} password-protected dispatcher."""

    def test_positive_amount_deposits(
        self, client, make_child, admin_password
    ):
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/adjust/{child.id}",
            params={
                "amount": 5.00,
                "description": "Bonus",
                "category": "Deposit",
                "password": admin_password,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["new_balance"] == 15.00

    def test_negative_amount_withdraws(
        self, client, make_child, admin_password
    ):
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/adjust/{child.id}",
            params={
                "amount": -3.00,
                "description": "Fine",
                "category": "Behaviour Deductions",
                "password": admin_password,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["new_balance"] == 7.00

    def test_zero_amount_makes_no_adjustment(
        self, client, make_child, admin_password
    ):
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/adjust/{child.id}",
            params={
                "amount": 0,
                "description": "No-op",
                "category": "Correction",
                "password": admin_password,
            },
        )

        assert resp.status_code == 200
        assert "No adjustment" in resp.json()["message"]

    def test_wrong_password_rejected(self, client, make_child):
        child = make_child(balance="10.00")

        resp = client.post(
            f"/v1/pocket-money/adjust/{child.id}",
            params={
                "amount": 5.00,
                "description": "Bonus",
                "category": "Deposit",
                "password": "wrong-password",
            },
        )

        assert resp.status_code == 403


class TestGetBalance:

    def test_get_balance_by_name(self, client, make_child):
        make_child(name="Penelope", balance="16.97")

        resp = client.get("/v1/pocket-money/balance/Penelope")

        assert resp.status_code == 200
        assert resp.json() == {"name": "Penelope", "balance": 16.97}

    def test_get_balance_unknown_child_returns_404(self, client):
        resp = client.get("/v1/pocket-money/balance/NoSuchChild")
        assert resp.status_code == 404
