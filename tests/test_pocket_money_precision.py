# tests/test_pocket_money_precision.py
"""
Regression tests for the original bug report:

    "A child has 14,63 EUR credit on their account and spent 15 EUR,
    the app rejects the deduction as it is more than the child has."

Root cause: balance/amount columns were Float, and repeated float
addition/subtraction drifted the stored balance away from its true
decimal value (e.g. 14.63 stored as 14.629999999999999), causing
comparisons like `balance < amount` to behave unpredictably.

Fix: columns migrated to NUMERIC(10, 2) and all arithmetic in the
router goes through Decimal.

These tests intentionally build up balances via the SAME deposit/
withdraw code paths a real user would hit (not by setting `balance`
directly), so they exercise the exact accumulation pattern that
caused the original bug.
"""
import pytest

pytestmark = pytest.mark.integration


class TestFloatPrecisionRegression:

    def test_deposit_accumulation_produces_exact_balance(
        self, client, make_child
    ):
        """
        4.99 + 9.64 = 14.63 exactly. Under the old Float column this
        was famously stored as 14.629999999999999 in plain Python.
        After the Numeric migration, the stored balance must be
        EXACTLY 14.63.
        """
        child = make_child(name="Penelope", balance="0.00")

        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 4.99, "description": "Birthday money"},
        )
        resp = client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 9.64, "description": "Chore reward"},
        )

        assert resp.status_code == 200
        assert resp.json()["new_balance"] == 14.63

    def test_withdraw_exact_balance_succeeds(self, client, make_child):
        """
        The exact scenario from the bug report: balance is 14.63,
        spend is 14.63 (the full balance) — must succeed, not be
        rejected as "insufficient funds".
        """
        child = make_child(name="Penelope", balance="0.00")
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 4.99, "description": "Birthday money"},
        )
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 9.64, "description": "Chore reward"},
        )

        resp = client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 14.63, "description": "Toy"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["new_balance"] == 0.00

    def test_withdraw_more_than_balance_is_correctly_rejected(
        self, client, make_child
    ):
        """
        Sanity check for the inverse case: a GENUINE insufficient-funds
        situation (14.63 balance, 15.00 withdrawal) must still be
        rejected with 422, not silently allowed.
        """
        child = make_child(name="Penelope", balance="0.00")
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 4.99, "description": "Birthday money"},
        )
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 9.64, "description": "Chore reward"},
        )

        resp = client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 15.00, "description": "Toy"},
        )

        assert resp.status_code == 422
        assert "Insufficient funds" in resp.json()["detail"]

    def test_insufficient_funds_returns_422_not_404(
        self, client, make_child
    ):
        """
        404 means "not found" and should be reserved for a missing
        child. Insufficient funds is a business-rule rejection and
        must be 422, so clients can distinguish the two cases.
        """
        child = make_child(name="Dominic", balance="5.00")

        resp = client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 10.00, "description": "Toy"},
        )

        assert resp.status_code == 422

    def test_many_small_transactions_do_not_drift_balance(
        self, client, make_child
    ):
        """
        Stress test: 20 deposits of 0.10 each should sum to EXACTLY
        2.00, not 1.9999999999999998 (a classic float accumulation
        failure that would NOT have been caught by a single-pair test).
        """
        child = make_child(name="Dominic", balance="0.00")

        for _ in range(20):
            client.post(
                f"/v1/pocket-money/deposit/{child.id}",
                params={"amount": 0.10, "description": "Allowance"},
            )

        resp = client.get(f"/v1/pocket-money/balance/{child.name}")
        assert resp.json()["balance"] == 2.00

    def test_repeated_deposit_withdraw_returns_to_zero_exactly(
        self, client, make_child
    ):
        """
        Deposit then withdraw the same odd-decimal amount 10 times.
        Any float drift would leave a residual fraction of a cent.
        """
        child = make_child(name="Dominic", balance="0.00")

        for _ in range(10):
            client.post(
                f"/v1/pocket-money/deposit/{child.id}",
                params={"amount": 3.33, "description": "in"},
            )
            client.post(
                f"/v1/pocket-money/withdraw/{child.id}",
                params={"amount": 3.33, "description": "out"},
            )

        resp = client.get(f"/v1/pocket-money/balance/{child.name}")
        assert resp.json()["balance"] == 0.00
