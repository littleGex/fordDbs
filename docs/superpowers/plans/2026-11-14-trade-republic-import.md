# Trade Republic Export Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the Trade Republic transaction export into `etf_transactions`, linked by ISIN, deduplicated by Trade Republic's `transaction_id`, with a dry run and an admin-page file picker.

**Architecture:** A pure parser (`parse_tr_export`) turns the CSV into buys/sells plus ignored/unknown counts. An import service (`import_tr_export`) dedupes against `external_id`, resolves ISINs through #38's `get_or_resolve` under a time budget, inserts rows inside a savepoint, and commits or (dry run) rolls back. A small router exposes it; the admin page gets an import card and a double-counting warning on the schedule form.

**Tech Stack:** FastAPI, SQLAlchemy 2, Postgres, Alembic, pytest (real Postgres test DB on port 5434), Vue 3 + Vite.

**Spec:** `docs/superpowers/specs/2026-11-14-trade-republic-import-design.md`

## Global Constraints

- Never commit a real export; `.gitignore` gets `*Transaction_export*.csv`. Fixtures use public ISINs, invented ids and invented amounts, and not the ISINs from the #45 sample.
- Amounts are `Decimal`; buys stored positive, sells negative (`shares_acquired`, `fiat_invested`); `fees` always >= 0.
- `entry_type="import"` for every imported row; the import never reads or writes `entry_type="scheduled"` rows.
- `transaction_date` = the CSV `date` column (trade date) at midnight, never `datetime`.
- External id for a netted liquidation: `liquidation:<ISIN>`.
- `RESOLVE_BUDGET_SECONDS = 60`; note for ISINs not looked up: `"not looked up yet, press Re-resolve"`.
- Size limit 5 MB (`MAX_IMPORT_BYTES = 5 * 1024 * 1024`), checked on the server (413) and in the browser.
- Ignored reasons are exactly `"cash"` and `"liquidation cancelled"`.
- Endpoint: `POST /v1/investments/etf/import/trade-republic`, parents only, body `{"csv_data": str, "dry_run": bool = false}`.
- flake8 7.4.1 clean, max-complexity 14.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Stage files by name; never commit `dist/`, `node_modules/` or `.idea/`.

## Review Focus

1. **File starts with a UTF-8 BOM and uses CRLF line endings** (Windows/Excel round-trip): it must parse exactly like a clean file. Test in Task 2.
2. **Export taken mid-liquidation** (share rows present, proceeds not yet booked): imports a sell with `fiat_invested` 0; the next export with proceeds is skipped as a duplicate with a warning, never a second sell. Test in Task 3.
3. **Re-import after a ticker was set by hand**: new rows get the instrument's current ticker, not the ISIN, and the instrument is not looked up again. Test in Task 3.
4. **Header-only file** returns all-zero counts (not an error); **empty text** is a missing-columns error. Test in Task 2.
5. **ISIN with no buy in the file** (only a sell or a liquidation): resolved with reference `None`. Test in Task 3.

---

### Task 1: `external_id` column, migration, gitignore

**Files:**
- Modify: `app/models/shares_models.py` (`EtfTransaction`)
- Create: `alembic/versions/c4d8e2a6f0b1_add_external_id_to_etf_transactions.py`
- Modify: `.gitignore`
- Test: `tests/test_tr_import.py` (new)

**Interfaces:**
- Produces: `EtfTransaction.external_id = Column(String, nullable=True, unique=True)`.

- [ ] **Step 1: Write the failing test** in `tests/test_tr_import.py`:

```python
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
```

- [ ] **Step 2: Run it** — `.venv/bin/python -m pytest tests/test_tr_import.py -q`. Expected: FAIL (`external_id` is an invalid keyword argument).

- [ ] **Step 3: Add the column** to `EtfTransaction`, with a comment: Trade Republic `transaction_id`, or `liquidation:<ISIN>`; NULL for rows not imported from an export.

- [ ] **Step 4: Run it** — same command. Expected: 2 passed.

- [ ] **Step 5: Write the migration** `c4d8e2a6f0b1`, `down_revision = 'a7c3e9f1b2d4'`: `upgrade` adds `external_id` (`sa.String()`, nullable) and unique constraint `uq_etf_transactions_external_id`; `downgrade` drops the constraint, then the column.

- [ ] **Step 6: Verify the migration on a scratch database** (test Postgres container, port 5434): create database `tr_mig`; build its tables with `Base.metadata.create_all` from `main`'s models (checked out in a temporary worktree), `alembic stamp a7c3e9f1b2d4`, then on this branch `alembic upgrade head` → `downgrade -1` → `upgrade head`, checking `\d etf_transactions` after each. Drop `tr_mig` and the worktree.
  Expected: column and constraint present after each upgrade, absent after the downgrade, no errors.

- [ ] **Step 7: Add `*Transaction_export*.csv`** to `.gitignore`; check with `git check-ignore -v Transaction_export_2026.csv`. Expected: the new rule is printed.

- [ ] **Step 8: Commit** `feat(investments): external_id on ETF transactions for import dedupe` (model, migration, `.gitignore`, test).

---

### Task 2: Parser

**Files:**
- Create: `app/core/tr_import.py`
- Create: `tests/fixtures/tr_export_sample.csv`
- Test: `tests/test_tr_import.py`

**Interfaces:**
- Consumes: `normalize_isin(value: str) -> str` (raises `ValueError`) from `app.core.instruments`.
- Produces (in `app/core/tr_import.py`):
  - `@dataclass ParsedTxn(line: int, external_id: str, isin: str, name: Optional[str], transaction_type: str, trade_date: date, shares: Decimal, fiat: Decimal, fees: Decimal, price: Optional[Decimal])`
  - `@dataclass ParseResult(transactions: List[ParsedTxn], ignored: Dict[str, int], unknown: List[dict])`
  - `parse_tr_export(csv_text: str) -> ParseResult` (raises `ValueError` with a message naming the line)
  - constants `LIQUIDATION_PREFIX = "liquidation:"`, `IGNORED_CASH = "cash"`, `IGNORED_LIQUIDATION_CANCELLED = "liquidation cancelled"`, `REQUIRED_COLUMNS` (the 11 columns in the spec).

- [ ] **Step 1: Create the fixture** `tests/fixtures/tr_export_sample.csv`, all fields double-quoted, with the spec's full 23-column header and these rows in this order (columns not listed are empty; `account_type` is `DEFAULT`; `currency` `EUR` unless stated):

| line | datetime | date | category / type | asset_class | symbol (name) | shares | price | amount | fee | tax | transaction_id |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 2025-05-13T12:18:59Z | 2025-05-13 | CASH / TRANSFER_INBOUND | | | | | 0.94 | | | cash-0001 |
| 3 | 2025-05-14T15:35:15Z | 2025-05-14 | CASH / CUSTOMER_INPAYMENT | | | | | 100.00 | | | cash-0002 |
| 4 | 2025-05-16T07:08:23Z | 2025-05-16 | TRADING / BUY | FUND | IE00B4L5Y983 (Core MSCI World USD (Acc)) | 0.150000 | 100.000000 | -15.00 | | | tx-0001 |
| 5 | 2025-06-03T09:00:00Z | 2025-06-02 | TRADING / BUY | FUND | IE00B4L5Y983 (Core MSCI World USD (Acc)) | 1.000000 | 101.500000 | -101.50 | -1.00 | | tx-0002 |
| 6 | 2025-06-10T10:00:00Z | 2025-06-10 | TRADING / BUY | STOCK | US0378331005 (Apple) | 0.500000 | 180.000000 | -90.00 | -1.00 | | tx-0003 |
| 7 | 2025-07-16T13:13:42Z | 2025-07-16 | TRADING / BUY | FUND | IE00BK5BQT80 (FTSE All-World USD (Acc)) | 2.000000 | 11.000000 | -22.00 | | | tx-0004 |
| 8 | 2025-12-23T13:56:04Z | 2025-12-11 | CORPORATE_ACTION / LIQUIDATION_DIVIDEND | FUND | IE00BK5BQT80 | -2.000000 | | | | | ca-0001 (currency empty) |
| 9 | 2025-12-24T08:44:43Z | 2025-12-11 | CORPORATE_ACTION / LIQUIDATION_DIVIDEND_CANCELLED | FUND | IE00BK5BQT80 | 2.000000 | | | | | ca-0002 (currency empty) |
| 10 | 2025-12-24T08:46:51Z | 2025-12-11 | CORPORATE_ACTION / LIQUIDATION_DIVIDEND | FUND | IE00BK5BQT80 | -2.000000 | | | | | ca-0003 (currency empty) |
| 11 | 2025-12-23T13:56:15Z | 2025-12-23 | CASH / LIQUIDATION_PROCEEDS | FUND | IE00BK5BQT80 | | | 24.00 | | -0.50 | lp-0001 |
| 12 | 2025-12-24T08:44:49Z | 2025-12-24 | CASH / LIQUIDATION_PROCEEDS | FUND | IE00BK5BQT80 | | | -24.00 | | 0.50 | lp-0002 |
| 13 | 2025-12-24T08:47:01Z | 2025-12-24 | CASH / LIQUIDATION_PROCEEDS | FUND | IE00BK5BQT80 | | | 24.00 | | -0.50 | lp-0003 |
| 14 | 2026-01-05T09:00:00Z | 2026-01-05 | CORPORATE_ACTION / LIQUIDATION_DIVIDEND | FUND | LU0380865021 (Euro STOXX 50 EUR (Acc)) | -1.000000 | | | | | ca-0004 (currency empty) |
| 15 | 2026-01-06T09:00:00Z | 2026-01-05 | CORPORATE_ACTION / LIQUIDATION_DIVIDEND_CANCELLED | FUND | LU0380865021 | 1.000000 | | | | | ca-0005 (currency empty) |
| 16 | 2026-01-28T09:25:20Z | 2026-01-27 | CASH / EARNINGS | FUND | IE00B4L5Y983 | | | 0.000000 | | -1.00 | cash-0003 |
| 17 | 2026-02-02T09:00:00Z | 2026-02-02 | CASH / DIVIDEND | STOCK | US0378331005 | | | 0.07 | | -0.02 | cash-0004 |
| 18 | 2026-03-02T10:00:00Z | 2026-03-02 | TRADING / SELL | STOCK | US0378331005 | -0.200000 | 190.000000 | 38.00 | -1.00 | | tx-0005 |
| 19 | 2026-04-01T09:00:00Z | 2026-04-01 | CORPORATE_ACTION / SPLIT | STOCK | US0378331005 | 0.500000 | | | | | ca-0006 (currency empty) |

- [ ] **Step 2: Write the failing parser tests** (class `TestParseTrExport`, fixture loaded with `Path(__file__).parent / "fixtures" / "tr_export_sample.csv"`; a helper `by_id(result)` maps `external_id` → `ParsedTxn`):
  - `test_fixture_yields_six_transactions`: ids == `{"tx-0001", "tx-0002", "tx-0003", "tx-0004", "tx-0005", "liquidation:IE00BK5BQT80"}`.
  - `test_savings_plan_buy`: tx-0001 → `transaction_type "buy"`, isin `IE00B4L5Y983`, shares `Decimal("0.150000")`, fiat `Decimal("15.00")`, fees `Decimal("0")`, price `Decimal("100.000000")`, trade_date `date(2025, 5, 16)`, name `"Core MSCI World USD (Acc)"`, line 4.
  - `test_buy_amount_excludes_fee_and_uses_trade_date`: tx-0002 → fiat `101.50`, fees `1.00`, trade_date `date(2025, 6, 2)` (not 3).
  - `test_stock_buy_is_imported`: tx-0003 isin `US0378331005`, shares `0.5`.
  - `test_sell_is_negative`: tx-0005 → `"sell"`, shares `-0.2`, fiat `-38.00`, fees `1.00`.
  - `test_liquidation_is_netted_to_one_sell`: `liquidation:IE00BK5BQT80` → `"sell"`, shares `Decimal("-2")`, fiat `Decimal("-24.00")`, fees 0, trade_date `date(2025, 12, 24)`, price None, line 13.
  - `test_cancelled_liquidation_and_cash_rows_are_ignored`: `ignored == {"cash": 4, "liquidation cancelled": 1}`.
  - `test_unknown_type_is_reported_with_line`: `unknown == [{"line": 19, "category": "CORPORATE_ACTION", "type": "SPLIT"}]`.
  - `test_bom_and_crlf_parse_the_same` (Review Focus 1): `"﻿" + text.replace("\n", "\r\n")` gives the same ids and ignored counts.
  - `test_header_only_gives_empty_result` (Review Focus 4): transactions `[]`, ignored `{}`, unknown `[]`.
  - Errors, each `pytest.raises(ValueError, match=...)`: empty text → `"missing column"`; header without `transaction_id` → `"transaction_id"`; tx-0002's currency changed to `USD` → `"line 5"`; tx-0001's amount `"abc"` → `"line 4"`; tx-0004's id changed to `tx-0001` → `"tx-0001"`; tx-0001's symbol `"IE00B4L5Y984"` (bad check digit) → `"line 4"`; tx-0001's transaction_id empty → `"line 4"`.

- [ ] **Step 3: Run them** — `.venv/bin/python -m pytest tests/test_tr_import.py -q -k Parse`. Expected: collection error, `app.core.tr_import` does not exist.

- [ ] **Step 4: Implement `parse_tr_export`.** Strip a leading BOM; `csv.DictReader(io.StringIO(text))`; header names stripped and lower-cased; line numbers from `reader.line_num`. Every row with a non-empty `transaction_id` goes into a seen-set first (duplicate → `ValueError` naming the id and line). Dispatch on `(category, type)`: TRADING BUY/SELL → `ParsedTxn` (currency must be `EUR`, ISIN via `normalize_isin`, `Decimal` parsing; any `InvalidOperation`/`ValueError` re-raised as `ValueError(f"line {n}: ...")`); CORPORATE_ACTION `LIQUIDATION_DIVIDEND`/`_CANCELLED` and CASH `LIQUIDATION_PROCEEDS` → accumulate per ISIN (shares sum, amount sum, latest date, last line, name); other CASH → `ignored["cash"]`; anything else → `unknown`. After the loop, emit one sell per ISIN whose net shares != 0, else count `"liquidation cancelled"`. Keep each helper under complexity 14.

- [ ] **Step 5: Run them** — same command. Expected: all pass.

- [ ] **Step 6: Commit** `feat(investments): parse the Trade Republic transaction export` (parser, fixture, tests).

---

### Task 3: Import service

**Files:**
- Modify: `app/core/tr_import.py`
- Test: `tests/test_tr_import.py`

**Interfaces:**
- Consumes: `parse_tr_export`, `ParsedTxn` (Task 2); `get_or_resolve(db, isin, name=None, reference=None, *, resolver)`, `Resolution`, `resolve_isin`, `set_instrument_ticker` from `app.core.instruments`; `Instrument`, `EtfTransaction`.
- Produces:
  - `@dataclass ImportResult(imported: int, skipped_duplicates: int, ignored: Dict[str, int], unknown: List[dict], unresolved: List[str], warnings: List[str], dry_run: bool)`
  - `class ImportSaveError(Exception)` — raised after rollback when the database rejects the rows.
  - `import_tr_export(db: Session, csv_text: str, *, dry_run: bool = False, resolver: Optional[Callable] = None, clock: Callable[[], float] = time.monotonic) -> ImportResult`. `resolver=None` means `app.core.instruments.resolve_isin` looked up at call time (so tests that patch the lookup functions still apply).
  - constants `RESOLVE_BUDGET_SECONDS = 60`, `NOT_LOOKED_UP = "not looked up yet, press Re-resolve"`.

- [ ] **Step 1: Write the failing tests** (class `TestImportTrExport`; reuse a `FakeResolver` like `tests/test_instruments.py`'s, recording calls, configurable `tickers: dict[isin -> ticker or None]`; `run(db_session, text, **kw)` calls `import_tr_export(db_session, text, resolver=fake, **kw)`):
  - `test_rows_are_linked_with_the_instruments_ticker`: tickers `{IE00B4L5Y983: "EUNL.DE", US0378331005: "APC.DE", IE00BK5BQT80: "VWCE.DE"}` → `result.imported == 6`; tx-0001 row has `ticker_symbol "EUNL.DE"`, `isin "IE00B4L5Y983"`, `entry_type "import"`, `transaction_date == datetime(2025, 5, 16)`, `fees == Decimal("0.00")`; tx-0002 `fees == Decimal("1.00")`.
  - `test_unresolved_isin_uses_isin_as_ticker_and_is_renamed_later`: IE00BK5BQT80 → None; its rows have `ticker_symbol "IE00BK5BQT80"`; `result.unresolved == ["IE00BK5BQT80"]`; after `set_instrument_ticker(db, inst, "VWCE.DE", "EUR", manual=True)` and flush, both rows (buy and liquidation sell) read `"VWCE.DE"`.
  - `test_latest_buy_is_the_reference`: the call for IE00B4L5Y983 got reference `(date(2025, 6, 2), Decimal("101.500000"))`.
  - `test_isin_without_buy_has_no_reference` (Review Focus 5): text with only line 18 (the sell) under the header → resolver called with `("US0378331005", None)`.
  - `test_existing_instrument_is_not_looked_up` (Review Focus 3): pre-create `Instrument(isin="IE00B4L5Y983", yahoo_ticker="IWDA.DE", manual_override=True, currency="EUR")` → no resolver call for that ISIN; its rows read `"IWDA.DE"`.
  - `test_reimport_skips_everything`: second run → `imported == 0`, `skipped_duplicates == 6`, `warnings == []`, row count unchanged.
  - `test_changed_liquidation_net_warns` (Review Focus 2): first import a copy without lines 11–13 (proceeds not booked) → liquidation row has `fiat_invested == 0`; then import the full fixture → `skipped_duplicates` includes it, `len(warnings) == 1` and the warning contains `"IE00BK5BQT80"`; still exactly one `liquidation:IE00BK5BQT80` row.
  - `test_dry_run_stores_nothing`: `dry_run=True` → `result.imported == 6`, `result.dry_run is True`; afterwards zero `EtfTransaction` rows and zero `Instrument` rows; a row and an instrument created by the test *before* the dry run still exist (proves the savepoint, not a full rollback).
  - `test_time_budget_leaves_rest_unresolved`: fake clock returning `0, 0, 61, 61, …` → the first ISIN is looked up, later ones are not; their instruments have `resolution_note == NOT_LOOKED_UP`; their ISINs are in `unresolved`; all 6 rows still imported.
  - `test_database_error_rolls_everything_back`: tx-0001 amount `-123456789012.00` (overflows `Numeric(10, 2)`) → `pytest.raises(ImportSaveError)`; afterwards zero imported rows and zero instruments.
  - `test_scheduled_rows_are_untouched`: a pre-existing `entry_type="scheduled"` row for `EUNL.DE` (no isin) is unchanged after import.

- [ ] **Step 2: Run them** — `.venv/bin/python -m pytest tests/test_tr_import.py -q -k Import`. Expected: ImportError on `import_tr_export`.

- [ ] **Step 3: Implement `import_tr_export`.** Parse (let `ValueError` propagate). `savepoint = db.begin_nested()`. Look up existing `external_id`s with one `IN` query; split parsed rows into new and duplicates; for duplicate liquidation ids compare stored `shares_acquired`/`fiat_invested` with the new net (quantized to 6 / 2 places) and warn `f"{isin}: liquidation in this export ({shares} shares, {fiat} EUR) differs from the one already imported; kept the stored one"`. Resolve ISINs of new rows in first-appearance order: reference = latest buy `(trade_date, price)` or None; once `clock() - start >= RESOLVE_BUDGET_SECONDS`, pass a resolver that returns `Resolution(isin, None, None, None, [], NOT_LOOKED_UP)` instead. Insert `EtfTransaction`s (ticker = `instrument.yahoo_ticker or isin`), `db.flush()`. On `SQLAlchemyError`: `savepoint.rollback()`, log, raise `ImportSaveError("Could not save the import; nothing was imported")`. Dry run → `savepoint.rollback()`; otherwise `savepoint.commit()` then `db.commit()`. `unresolved` = sorted ISINs of new rows whose instrument has no `yahoo_ticker`.

- [ ] **Step 4: Run them** — same command. Expected: all pass. Then `.venv/bin/python -m pytest tests/test_tr_import.py tests/test_instruments.py -q`. Expected: all pass.

- [ ] **Step 5: Commit** `feat(investments): import Trade Republic exports with dedupe and dry run`.

---

### Task 4: API endpoint and `imported` count

**Files:**
- Create: `app/api/v1/tr_import.py`
- Modify: `app/main.py` (mount under `/v1/investments` with `require_parent`, like `instruments_router`)
- Modify: `app/api/v1/instruments.py` (`_to_json`)
- Test: `tests/test_tr_import_api.py` (new)

**Interfaces:**
- Consumes: `import_tr_export`, `ImportSaveError`, `ImportResult` (Task 3).
- Produces: `tr_import_router` with `POST /etf/import/trade-republic`, body model `TrImportRequest(csv_data: str, dry_run: bool = False)`; `MAX_IMPORT_BYTES = 5 * 1024 * 1024`. Instrument JSON gains `"imported": int`.

- [ ] **Step 1: Write the failing tests** (patch the lookup functions like `tests/test_instruments_api.py`'s `lookups` fixture so no network is used; whether the fixture's ISINs resolve doesn't matter, these tests check counts; `URL = "/v1/investments/etf/import/trade-republic"`):
  - `test_import_returns_counts`: 200; JSON keys exactly `{"imported", "skipped_duplicates", "ignored", "unknown", "unresolved", "warnings", "dry_run"}`; `imported == 6`; `ignored == {"cash": 4, "liquidation cancelled": 1}`; `unknown == [{"line": 19, "category": "CORPORATE_ACTION", "type": "SPLIT"}]`.
  - `test_dry_run_stores_nothing`: `dry_run: true` → `imported == 6`, `dry_run` true, `EtfTransaction` count 0.
  - `test_parse_error_is_400`: header-only text minus `transaction_id` → 400, detail mentions `transaction_id`.
  - `test_too_large_is_413`: `csv_data = "x" * (MAX_IMPORT_BYTES + 1)` → 413.
  - `test_save_error_is_400`: patch `app.api.v1.tr_import.import_tr_export` to raise `ImportSaveError("Could not save the import; nothing was imported")` → 400 with that detail.
  - `test_requires_login`: anonymous `client` → 401.
  - `test_instruments_show_imported_count`: after an import, `GET /v1/investments/instruments` → the `IE00B4L5Y983` entry has `imported == 2`, and an instrument with only a manual linked row has `imported == 0`.

- [ ] **Step 2: Run them** — `.venv/bin/python -m pytest tests/test_tr_import_api.py -q`. Expected: failures (404s / ImportError).

- [ ] **Step 3: Implement** the router (size check on `len(body.csv_data.encode())` before parsing → 413 `"Export is larger than 5 MB"`; `ValueError` → 400 with its message; `ImportSaveError` → 400 with its message; return `dataclasses.asdict(result)`), mount it in `app/main.py`, and add `"imported"` to `_to_json` (count of the instrument's `EtfTransaction`s with `entry_type == "import"`).

- [ ] **Step 4: Run them** — same command, then `.venv/bin/python -m pytest tests/test_instruments_api.py -q`. Expected: all pass.

- [ ] **Step 5: Commit** `feat(investments): Trade Republic import endpoint`.

---

### Task 5: Admin page

**Files:**
- Modify: `investments-frontend/src/views/AdminView.vue`

**Interfaces:**
- Consumes: the endpoint and `imported` field (Task 4); existing `api`, `errorText`, `fetchInstruments`, `fetchSchedules`, `instruments`.

No frontend test framework exists; verification is the build plus a browser check.

- [ ] **Step 1: Import card** in `.forms-grid`, titled "Import Trade Republic export", with a hint ("Trade Republic app → Profile → Transaction export. Check the file first; re-importing skips rows already imported."): `<input type="file" accept=".csv">`, buttons "Check file" (dry run) and "Import", both disabled with no file or while running. The file is read with `file.text()`; over 5 MB (`5 * 1024 * 1024` bytes, by `file.size`) shows an error instead of sending. Results render in the card (not `alert`): "Would import N" / "Imported N", duplicates skipped, ignored by reason, unknown rows (`line N: CATEGORY / TYPE`), warnings, and unresolved ISINs with "set their tickers in Instruments below". Errors render in the same place via `errorText`. After a real import, call `fetchInstruments()` and `fetchSchedules()`.

- [ ] **Step 2: Schedule warning** in `createSchedule`: before posting, find an instrument whose `isin` equals the trimmed ISIN, or (no ISIN given) whose `yahoo_ticker` equals the upper-cased ticker, with `imported > 0`; if found, `confirm("Trade Republic fills for this fund are imported; an app schedule would count them twice. Create anyway?")` and stop on cancel.

- [ ] **Step 3: Build** — `cd investments-frontend && npm run build`, then restore the tracked build output: `git checkout -- dist && git clean -fq dist` (and `node_modules/.vite` if touched). Expected: `✓ built`, and `git status` shows only `AdminView.vue` among frontend files.

- [ ] **Step 4: Browser check** against a local API (test DB) and `npm run dev`: if Claude in Chrome is connected, check-file then import the fixture, re-import (all skipped), and the schedule warning. Otherwise exercise the same requests with curl and record that the page was not clicked through. Restore any `dist/`/`.vite` changes afterwards.

- [ ] **Step 5: Commit** `feat(investments): import Trade Republic exports from the admin page`.

---

### Task 6: Full verification and PR

- [ ] **Step 1:** `.venv/bin/python -m pytest -q > <workspace>/suite.log 2>&1; tail -1 <workspace>/suite.log` and `.venv/bin/flake8 .`. Expected: all pass (previous 554 + new), flake8 silent.
- [ ] **Step 2:** Mark the spec's `Testing` items covered; nothing else in docs changes.
- [ ] **Step 3:** Push `feat/tr-import` and open a PR that closes #45 and #39. Body: what it does, the rollout order (back up → build `api investments-ui` → `docker compose run --rm --no-deps api alembic -c /code/alembic.ini upgrade head` → `docker compose up -d api investments-ui` → "Check file" with the real export → "Import" → set tickers for unresolved ISINs), whether the page was clicked through, and known follow-ups. Public ISINs only, no holdings, no export contents. Do not merge.
