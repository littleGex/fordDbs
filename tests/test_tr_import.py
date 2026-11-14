"""
Tests for the Trade Republic export import (#45): the external_id
column, the parser and the import service in app/core/tr_import.py.

The fixture is synthetic: public ISINs, invented ids and amounts. Never
commit a real export.
"""
import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.tr_import import parse_tr_export
from app.models.shares_models import EtfTransaction

FIXTURE = Path(__file__).parent / "fixtures" / "tr_export_sample.csv"
SAMPLE = FIXTURE.read_text()


def edit(text, tid, **changes):
    """The export with columns of one row (found by transaction_id)
    changed."""
    rows = list(csv.DictReader(io.StringIO(text)))
    for row in rows:
        if row["transaction_id"] == tid:
            row.update(changes)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]),
                            quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def by_id(result):
    return {t.external_id: t for t in result.transactions}


class TestExternalIdColumn:

    def test_external_id_is_unique(self, db_session):
        for _ in range(2):
            db_session.add(EtfTransaction(
                ticker_symbol="EUNL.DE", fiat_invested=Decimal("1"),
                shares_acquired=Decimal("1"), external_id="tx-1"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_external_id_is_optional(self, db_session):
        txn = EtfTransaction(ticker_symbol="EUNL.DE",
                             fiat_invested=Decimal("1"),
                             shares_acquired=Decimal("1"))
        db_session.add(txn)
        db_session.flush()
        assert txn.external_id is None


class TestParseTrExport:

    def test_fixture_yields_six_transactions(self):
        assert set(by_id(parse_tr_export(SAMPLE))) == {
            "tx-0001", "tx-0002", "tx-0003", "tx-0004", "tx-0005",
            "liquidation:IE00BK5BQT80"}

    def test_savings_plan_buy(self):
        t = by_id(parse_tr_export(SAMPLE))["tx-0001"]
        assert t.transaction_type == "buy"
        assert t.isin == "IE00B4L5Y983"
        assert t.shares == Decimal("0.150000")
        assert t.fiat == Decimal("15.00")
        assert t.fees == Decimal("0")
        assert t.price == Decimal("100.000000")
        assert t.trade_date == date(2025, 5, 16)
        assert t.name == "Core MSCI World USD (Acc)"
        assert t.line == 4

    def test_buy_amount_excludes_fee_and_uses_trade_date(self):
        t = by_id(parse_tr_export(SAMPLE))["tx-0002"]
        assert t.fiat == Decimal("101.50")
        assert t.fees == Decimal("1.00")
        assert t.trade_date == date(2025, 6, 2)

    def test_stock_buy_is_imported(self):
        t = by_id(parse_tr_export(SAMPLE))["tx-0003"]
        assert t.isin == "US0378331005"
        assert t.shares == Decimal("0.5")

    def test_sell_is_negative(self):
        t = by_id(parse_tr_export(SAMPLE))["tx-0005"]
        assert t.transaction_type == "sell"
        assert t.shares == Decimal("-0.2")
        assert t.fiat == Decimal("-38.00")
        assert t.fees == Decimal("1.00")

    def test_liquidation_is_netted_to_one_sell(self):
        t = by_id(parse_tr_export(SAMPLE))["liquidation:IE00BK5BQT80"]
        assert t.transaction_type == "sell"
        assert t.isin == "IE00BK5BQT80"
        assert t.shares == Decimal("-2")
        assert t.fiat == Decimal("-24.00")
        assert t.fees == Decimal("0")
        assert t.trade_date == date(2025, 12, 24)
        assert t.price is None
        assert t.line == 13

    def test_cancelled_liquidation_and_cash_rows_are_ignored(self):
        assert parse_tr_export(SAMPLE).ignored == {
            "cash": 4, "liquidation cancelled": 1}

    def test_unknown_type_is_reported_with_line(self):
        assert parse_tr_export(SAMPLE).unknown == [
            {"line": 19, "category": "CORPORATE_ACTION", "type": "SPLIT"}]

    def test_bom_and_crlf_parse_the_same(self):
        clean = parse_tr_export(SAMPLE)
        windows = parse_tr_export("\ufeff" + SAMPLE.replace("\n", "\r\n"))
        assert set(by_id(windows)) == set(by_id(clean))
        assert windows.ignored == clean.ignored
        assert windows.unknown == clean.unknown

    def test_header_only_gives_empty_result(self):
        result = parse_tr_export(SAMPLE.splitlines()[0] + "\n")
        assert result.transactions == []
        assert result.ignored == {}
        assert result.unknown == []

    def test_empty_text_is_missing_columns(self):
        with pytest.raises(ValueError, match="(?i)missing column"):
            parse_tr_export("")

    def test_missing_transaction_id_column(self):
        header = SAMPLE.splitlines()[0].replace(',"transaction_id"', "")
        with pytest.raises(ValueError, match="transaction_id"):
            parse_tr_export(header + "\n")

    def test_non_eur_trade_is_rejected(self):
        with pytest.raises(ValueError, match="line 5"):
            parse_tr_export(edit(SAMPLE, "tx-0002", currency="USD"))

    def test_unparseable_amount_is_rejected(self):
        with pytest.raises(ValueError, match="line 4"):
            parse_tr_export(edit(SAMPLE, "tx-0001", amount="abc"))

    def test_duplicate_transaction_id_is_rejected(self):
        with pytest.raises(ValueError, match="tx-0001"):
            parse_tr_export(edit(SAMPLE, "tx-0004",
                                 transaction_id="tx-0001"))

    def test_invalid_isin_is_rejected(self):
        with pytest.raises(ValueError, match="line 4"):
            parse_tr_export(edit(SAMPLE, "tx-0001", symbol="IE00B4L5Y984"))

    def test_empty_transaction_id_on_trade_is_rejected(self):
        with pytest.raises(ValueError, match="line 4"):
            parse_tr_export(edit(SAMPLE, "tx-0001", transaction_id=""))
