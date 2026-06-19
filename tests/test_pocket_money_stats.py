# tests/test_pocket_money_stats.py
"""Tests for transaction history and combined stats endpoints."""
import pytest

pytestmark = pytest.mark.integration


class TestHistory:

    def test_history_returns_transactions_newest_first(
        self, client, make_child
    ):
        child = make_child(balance="0.00")
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 5.00, "description": "First"},
        )
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 3.00, "description": "Second"},
        )

        resp = client.get(f"/v1/pocket-money/history/{child.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["description"] == "Second"

    def test_history_respects_limit(self, client, make_child):
        child = make_child(balance="0.00")
        for i in range(5):
            client.post(
                f"/v1/pocket-money/deposit/{child.id}",
                params={"amount": 1.00, "description": f"txn {i}"},
            )

        resp = client.get(
            f"/v1/pocket-money/history/{child.id}", params={"limit": 2}
        )

        assert len(resp.json()) == 2

    def test_history_empty_for_new_child(self, client, make_child):
        child = make_child(balance="0.00")

        resp = client.get(f"/v1/pocket-money/history/{child.id}")

        assert resp.json() == []


class TestCombinedStats:

    def test_stats_total_spent_excludes_deposits(
        self, client, make_child
    ):
        """
        REGRESSION: total_spent originally summed ALL categories
        including 'Deposit' (a positive amount), making total_spent
        misleadingly low or positive. It must only reflect spending
        (negative) categories.
        """
        child = make_child(balance="0.00")
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 20.00, "description": "Allowance"},
        )
        client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={"amount": 5.00, "description": "Toy"},
        )

        resp = client.get(f"/v1/pocket-money/stats/{child.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_spent"] == -5.00

    def test_stats_spending_summary_by_category(self, client, make_child):
        child = make_child(balance="0.00")
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 20.00, "description": "Allowance"},
        )
        client.post(
            f"/v1/pocket-money/withdraw/{child.id}",
            params={
                "amount": 5.00,
                "description": "Toy",
                "category": "Spend",
            },
        )

        resp = client.get(f"/v1/pocket-money/stats/{child.id}")

        body = resp.json()
        assert body["spending_summary"]["Deposit"] == 20.00
        assert body["spending_summary"]["Spend"] == -5.00

    def test_stats_wishes_bought_counts_goal_met_transactions(
        self, client, make_child, db_session
    ):
        from app.models.user_models import Transaction

        child = make_child(balance="0.00")
        db_session.add(
            Transaction(
                child_id=child.id,
                amount=-10,
                description="Bought a goal item",
                category="Goal Met",
            )
        )
        db_session.commit()

        resp = client.get(f"/v1/pocket-money/stats/{child.id}")

        assert resp.json()["wishes_bought"] == 1

    def test_stats_values_are_json_numbers(self, client, make_child):
        """
        Guards against func.sum() over a Numeric column returning a
        Decimal that gets serialized as a string instead of a number.
        """
        child = make_child(balance="0.00")
        client.post(
            f"/v1/pocket-money/deposit/{child.id}",
            params={"amount": 20.00, "description": "Allowance"},
        )

        resp = client.get(f"/v1/pocket-money/stats/{child.id}")

        body = resp.json()
        for value in body["spending_summary"].values():
            assert isinstance(value, (int, float))
        assert isinstance(body["total_spent"], (int, float))
