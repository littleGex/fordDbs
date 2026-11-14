"""
Tests for the Trade Republic export import (#45): the external_id
column, the parser and the import service in app/core/tr_import.py.

The fixture is synthetic: public ISINs, invented ids and amounts. Never
commit a real export.
"""
import csv
import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.instruments import Resolution, set_instrument_ticker
from app.core.tr_import import (NOT_LOOKED_UP, ImportSaveError,
                                import_tr_export, parse_tr_export)
from app.models.shares_models import (EtfPurchaseSchedule, EtfTransaction,
                                      Instrument)

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


def drop(text, *tids):
    """The export without the rows with these transaction_ids."""
    keep = [line for line in text.splitlines()
            if not any(f'"{tid}"' in line for tid in tids)]
    return "\n".join(keep) + "\n"


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


TICKERS = {"IE00B4L5Y983": "EUNL.DE", "US0378331005": "APC.DE",
           "IE00BK5BQT80": "VWCE.DE"}
UNRELATED_ISIN = "IE00B5BMR087"


class FakeResolver:
    def __init__(self, tickers=None):
        self.tickers = dict(TICKERS if tickers is None else tickers)
        self.calls = []

    def __call__(self, isin, reference=None):
        self.calls.append((isin, reference))
        ticker = self.tickers.get(isin)
        return Resolution(isin=isin, ticker=ticker,
                          currency="EUR" if ticker else None, name=None,
                          candidates=[],
                          note="picked" if ticker else "no EUR listing")

    def reference_for(self, isin):
        return dict(self.calls)[isin]


def imported_rows(db):
    return {t.external_id: t for t in db.query(EtfTransaction).filter(
        EtfTransaction.entry_type == "import")}


class TestImportTrExport:

    def run(self, db, text=SAMPLE, resolver=None, **kw):
        return import_tr_export(db, text, resolver=resolver or FakeResolver(),
                                **kw)

    def test_rows_are_linked_with_the_instruments_ticker(self, db_session):
        result = self.run(db_session)
        rows = imported_rows(db_session)
        assert result.imported == 6
        first = rows["tx-0001"]
        assert first.ticker_symbol == "EUNL.DE"
        assert first.isin == "IE00B4L5Y983"
        assert first.entry_type == "import"
        assert first.transaction_type == "buy"
        assert first.transaction_date == datetime(2025, 5, 16)
        assert first.fees == Decimal("0.00")
        assert rows["tx-0002"].fees == Decimal("1.00")
        sell = rows["liquidation:IE00BK5BQT80"]
        assert sell.shares_acquired == Decimal("-2")
        assert sell.fiat_invested == Decimal("-24.00")

    def test_unresolved_isin_uses_isin_as_ticker_and_is_renamed_later(
            self, db_session):
        tickers = dict(TICKERS, IE00BK5BQT80=None)
        result = self.run(db_session, resolver=FakeResolver(tickers))
        assert result.unresolved == ["IE00BK5BQT80"]
        rows = imported_rows(db_session)
        assert rows["tx-0004"].ticker_symbol == "IE00BK5BQT80"

        set_instrument_ticker(db_session,
                              db_session.get(Instrument, "IE00BK5BQT80"),
                              "VWCE.DE", "EUR", manual=True)
        db_session.flush()
        db_session.expire_all()
        rows = imported_rows(db_session)
        assert rows["tx-0004"].ticker_symbol == "VWCE.DE"
        assert rows["liquidation:IE00BK5BQT80"].ticker_symbol == "VWCE.DE"

    def test_latest_buy_is_the_reference(self, db_session):
        fake = FakeResolver()
        self.run(db_session, resolver=fake)
        assert fake.reference_for("IE00B4L5Y983") == (
            date(2025, 6, 2), Decimal("101.500000"))

    def test_isin_without_buy_has_no_reference(self, db_session):
        lines = SAMPLE.splitlines()
        fake = FakeResolver()
        self.run(db_session, lines[0] + "\n" + lines[17] + "\n",
                 resolver=fake)
        assert fake.calls == [("US0378331005", None)]

    def test_existing_instrument_is_not_looked_up(self, db_session):
        db_session.add(Instrument(isin="IE00B4L5Y983", yahoo_ticker="IWDA.DE",
                                  currency="EUR", manual_override=True))
        db_session.flush()
        fake = FakeResolver()
        self.run(db_session, resolver=fake)
        assert "IE00B4L5Y983" not in dict(fake.calls)
        assert imported_rows(db_session)["tx-0001"].ticker_symbol == \
            "IWDA.DE"

    def test_reimport_skips_everything(self, db_session):
        self.run(db_session)
        result = self.run(db_session)
        assert result.imported == 0
        assert result.skipped_duplicates == 6
        assert result.warnings == []
        assert len(imported_rows(db_session)) == 6

    def test_changed_liquidation_net_warns(self, db_session):
        self.run(db_session, drop(SAMPLE, "lp-0001", "lp-0002", "lp-0003"))
        sell = imported_rows(db_session)["liquidation:IE00BK5BQT80"]
        assert sell.fiat_invested == 0

        result = self.run(db_session)
        assert result.skipped_duplicates == 6
        assert len(result.warnings) == 1
        assert "IE00BK5BQT80" in result.warnings[0]
        assert db_session.query(EtfTransaction).filter(
            EtfTransaction.external_id == "liquidation:IE00BK5BQT80"
        ).count() == 1

    def test_dry_run_stores_nothing(self, db_session):
        db_session.add(Instrument(isin=UNRELATED_ISIN, manual_override=False))
        db_session.add(EtfTransaction(ticker_symbol="SXR8.DE",
                                      fiat_invested=Decimal("10"),
                                      shares_acquired=Decimal("1")))
        db_session.flush()

        result = self.run(db_session, dry_run=True)

        assert result.imported == 6
        assert result.dry_run is True
        assert imported_rows(db_session) == {}
        assert [i.isin for i in db_session.query(Instrument)] == [
            UNRELATED_ISIN]
        assert db_session.query(EtfTransaction).count() == 1

    def test_time_budget_leaves_rest_unresolved(self, db_session):
        ticks = iter([0, 0] + [61] * 50)
        fake = FakeResolver()
        result = self.run(db_session, resolver=fake,
                          clock=lambda: next(ticks))
        assert [isin for isin, _ in fake.calls] == ["IE00B4L5Y983"]
        assert result.unresolved == ["IE00BK5BQT80", "US0378331005"]
        assert db_session.get(Instrument, "US0378331005").resolution_note \
            == NOT_LOOKED_UP
        assert result.imported == 6

    def test_database_error_rolls_everything_back(self, db_session):
        too_big = edit(SAMPLE, "tx-0001", amount="-123456789012.00")
        with pytest.raises(ImportSaveError):
            self.run(db_session, too_big)
        assert imported_rows(db_session) == {}
        assert db_session.query(Instrument).count() == 0

    def test_scheduled_rows_are_untouched(self, db_session):
        scheduled = EtfTransaction(ticker_symbol="EUNL.DE",
                                   fiat_invested=Decimal("50"),
                                   shares_acquired=Decimal("0.4"),
                                   entry_type="scheduled")
        db_session.add(scheduled)
        db_session.flush()
        self.run(db_session)
        db_session.expire_all()
        assert scheduled.isin is None
        assert scheduled.external_id is None
        assert scheduled.fiat_invested == Decimal("50.00")

    def test_liquidation_cancelled_after_import_warns(self, db_session):
        self.run(db_session)
        cancelled = drop(SAMPLE, "ca-0003", "lp-0003")
        assert parse_tr_export(cancelled).ignored[
            "liquidation cancelled"] == 2

        result = self.run(db_session, cancelled)

        assert len(result.warnings) == 1
        assert "IE00BK5BQT80" in result.warnings[0]
        assert "cancelled" in result.warnings[0]

    def test_app_rows_for_an_imported_fund_warn(self, db_session):
        db_session.add(EtfTransaction(ticker_symbol="EUNL.DE",
                                      fiat_invested=Decimal("50"),
                                      shares_acquired=Decimal("0.4"),
                                      entry_type="scheduled"))
        db_session.add(EtfPurchaseSchedule(ticker_symbol="APC.DE",
                                           fiat_amount=Decimal("25"),
                                           execution_day=15))
        db_session.flush()

        result = self.run(db_session)

        assert len(result.warnings) == 2
        world = next(w for w in result.warnings if "IE00B4L5Y983" in w)
        apple = next(w for w in result.warnings if "US0378331005" in w)
        assert "1 transaction" in world
        assert "1 active schedule" in apple

    def test_inactive_schedule_does_not_warn(self, db_session):
        db_session.add(EtfPurchaseSchedule(ticker_symbol="APC.DE",
                                           fiat_amount=Decimal("25"),
                                           execution_day=15,
                                           is_active=False))
        db_session.flush()
        assert self.run(db_session).warnings == []
