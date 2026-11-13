# ISIN Instruments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Key ETF/stock instruments by ISIN and resolve each ISIN to a Yahoo ticker priced in EUR, with manual override and linking of existing rows (#38).

**Architecture:** A pure resolver (`app/core/instruments.py`) takes injectable lookup functions (OpenFIGI, Yahoo search, Yahoo quote). A service layer in the same module stores results in a new `instruments` table and keeps `ticker_symbol` on linked transactions and schedules in sync. A new parents-only router exposes it; the admin page gets an Instruments section.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, yfinance 1.7.0, urllib (OpenFIGI), Vue 3 + axios, pytest.

**Spec:** `docs/superpowers/specs/2026-11-12-isin-instruments-design.md`

## Global Constraints

- Only candidates Yahoo prices in currency `EUR` (from Yahoo metadata, never inferred from the suffix) can be picked or set by hand.
- Preference: first accepted `.DE` candidate, else first accepted candidate. Candidate order: OpenFIGI first, then Yahoo search, de-duplicated.
- Reference check tolerance: 5% (`PRICE_TOLERANCE = Decimal("0.05")`), against Yahoo's close on the reference date.
- HTTP timeouts about 10 seconds. `resolve_isin` never raises for network problems.
- An instrument with `manual_override = true` is never changed by an automatic lookup.
- Every ticker change goes through `set_instrument_ticker`, which updates `ticker_symbol` on linked `etf_transactions` and `etf_purchase_schedule` rows.
- New endpoints live under `/v1/investments` behind `require_parent`.
- ISINs and tickers are normalised with `.strip().upper()` on input.
- Repo is public: tests and docs use public ISINs only (e.g. `IE00B4L5Y983`, `IE00BK5BQT80`, `DE0005933931`), never a real export.
- flake8 7.4.1 clean (`.flake8`). Stage files by name; never `git commit -a` (the working tree has the user's `.idea/` edits).

## Review Focus

1. ISIN typed in lower case or with spaces (`" ie00b4l5y983 "`) must be accepted as `IE00B4L5Y983`, not rejected or stored twice. Test in Task 2 and Task 5.
2. Manual ticker typed as `"eunl.de "` must be stored as `EUNL.DE`. Test in Task 5.
3. Linking the same ticker twice must return zero counts the second time, not 404 and not an error. Test in Task 4.
4. Yahoo returning a NaN close (gaps in history) must count as "no Yahoo data", never as a price. Test in Task 3.
5. Overriding an instrument whose schedule is linked must change the schedule's `ticker_symbol`, since the scheduler buys by it. Test in Task 4.

---

### Task 1: Instrument model and migration

**Files:**
- Modify: `app/models/shares_models.py` (add `Instrument`; add `isin` to `EtfTransaction` and `EtfPurchaseSchedule`)
- Create: `alembic/versions/a7c3e9f1b2d4_add_instruments_and_isin.py` (`down_revision = 'f2a9c4e7d1b3'`)
- Test: `tests/test_instruments.py`

**Interfaces:**
- Produces: `Instrument` with columns exactly as the spec's data model table; `EtfTransaction.isin` and `EtfPurchaseSchedule.isin` (`String(12)`, nullable, indexed, `ForeignKey("instruments.isin")`).

- [ ] **Step 1: Write the failing test**

```python
def test_transaction_can_link_to_instrument(db_session):
    db_session.add(Instrument(isin="IE00B4L5Y983", yahoo_ticker="EUNL.DE",
                              currency="EUR"))
    db_session.add(EtfTransaction(ticker_symbol="EUNL.DE", isin="IE00B4L5Y983",
                                  fiat_invested=Decimal("10"),
                                  shares_acquired=Decimal("0.1")))
    db_session.flush()
    inst = db_session.get(Instrument, "IE00B4L5Y983")
    assert inst.manual_override is False
    assert inst.created_at is not None
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_instruments.py -q`. Expected: FAIL, `ImportError` for `Instrument`.

- [ ] **Step 3: Add the model and columns.** `manual_override` gets both `default=False` and `server_default=sa.false()`.

- [ ] **Step 4: Write the migration.** `upgrade()` creates `instruments` only if `sa.inspect(op.get_bind()).has_table("instruments")` is false (the app's startup `create_all` may already have made it), then adds `isin` + index + FK to both tables. `downgrade()` drops them in reverse.

- [ ] **Step 5: Run** the test again. Expected: PASS.

- [ ] **Step 6: Verify the migration on a scratch database.**

```bash
docker exec forddbs-test-db createdb -U test forddbs_migration_test
```
Then, with `POSTGRES_USER=test POSTGRES_PASSWORD=test DB_HOST=localhost DB_PORT=5434 POSTGRES_DB=forddbs_migration_test`: create `etf_transactions` and `etf_purchase_schedule` as they are on `main` (`git show main:app/models/shares_models.py`, via a short script using a separate `MetaData`), run `.venv/bin/alembic stamp f2a9c4e7d1b3`, `upgrade head`, `downgrade -1`, `upgrade head`. Expected: each succeeds; after upgrade both tables have `isin`. Repeat once with `instruments` pre-created to prove the existence check. Drop the scratch database afterwards.

- [ ] **Step 7: Commit** `app/models/shares_models.py`, the migration and the test: `feat(investments): add instruments table and isin columns`.

### Task 2: ISIN validation and the resolver

**Files:**
- Create: `app/core/instruments.py`
- Test: `tests/test_instruments.py`

**Interfaces:**
- Produces:
  - `normalize_isin(value: str) -> str`: strip + upper, then validate; raises `ValueError` if invalid.
  - `Candidate` and `Resolution` dataclasses exactly as in the spec.
  - `resolve_isin(isin, reference: tuple[date, Decimal] | None = None, *, figi_tickers, yahoo_search, yahoo_quote) -> Resolution`. Defaults for the three keyword arguments come from Task 3; until then the tests always pass fakes.
  - `PRICE_TOLERANCE = Decimal("0.05")`.

Fakes for tests: `figi_tickers=lambda isin: [...]`, `yahoo_search=lambda isin: [(symbol, shortname), ...]`, `yahoo_quote=lambda ticker, on: QUOTES[ticker]` where `QUOTES` maps ticker to `(currency, Decimal close or None)`, and a missing ticker raises `LookupError`.

- [ ] **Step 1: Write the failing tests** (one function each):
  - `test_valid_isins_pass`: `normalize_isin(" ie00b4l5y983 ") == "IE00B4L5Y983"`; also `IE00BK5BQT80`, `DE0005933931`, `US0079031078`.
  - `test_bad_check_digit_rejected`: `IE00B4L5Y984` raises `ValueError`; so do `"IE00B4L5Y98"` and `"1E00B4L5Y983"`.
  - `test_invalid_isin_makes_no_lookup`: lookups that `raise AssertionError`; `resolve_isin("XX123")` raises `ValueError`.
  - `test_prefers_de_over_other_eur`: figi `["EUNL.DE"]`, search `["IMAE.AS"]`, both EUR → `ticker == "EUNL.DE"`, `currency == "EUR"`.
  - `test_rejects_usd_listing`: figi `[]`, search `["IWDA.L"]` priced USD → `ticker is None`; candidate `reason` contains `"USD"`.
  - `test_rejects_gbp_priced_de_ticker`: `MWRD.DE` in GBP, `MWRE.DE` in EUR → picks `MWRE.DE`.
  - `test_falls_back_to_non_de_eur_listing`: `SPYS.DE` raises `LookupError`, `SMC.PA` EUR → `SMC.PA`.
  - `test_reference_within_tolerance_resolves`: reference `(date(2026, 2, 16), Decimal("98.27"))`, close `98.13` → resolved.
  - `test_reference_off_by_more_than_5_percent_unresolved`: close `110` against `98.27` → `ticker is None`, `"off"` in `note`.
  - `test_reference_date_passed_to_quote`: the fake records `on`; equals the reference date. Without a reference `on is None` and `"not checked"` in `note`.
  - `test_one_source_failing_uses_the_other`: figi raises `OSError`, search gives an EUR ticker → resolved.
  - `test_all_lookups_failing_says_retry`: figi and search both raise `OSError` → `ticker is None`, `"lookup failed, retry later"` in `note`.
  - `test_no_candidates_unresolved`: both return `[]` → `ticker is None`.
  - `test_duplicates_checked_once`: figi and search both return `EUNL.DE`; the quote fake is called once.
  - `test_name_from_search`: search `[("EUNL.DE", "iShares Core MSCI World")]` → `name == "iShares Core MSCI World"`; no shortname anywhere → `name is None`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_instruments.py -q`. Expected: the new tests FAIL with `ImportError`.

- [ ] **Step 3: Implement.** ISIN check digit: letters to numbers (`A`=10 … `Z`=35), concatenate the first 11 characters' digits, then Luhn over that string must give the 12th character. `Resolution.name` is the first non-empty search shortname. Errors from each source are caught per source; a quote error makes that candidate rejected with reason `"no Yahoo data"`.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Commit** `app/core/instruments.py` and the test: `feat(investments): resolve ISINs to EUR Yahoo tickers`.

### Task 3: Real lookup functions

**Files:**
- Modify: `app/core/instruments.py`
- Test: `tests/test_instruments.py`

**Interfaces:**
- Produces (and become `resolve_isin`'s defaults):
  - `figi_tickers(isin: str) -> list[str]`: POST `https://api.openfigi.com/v3/mapping` with `[{"idType": "ID_ISIN", "idValue": isin}]`, timeout 10; tickers where `exchCode == "GR"`, each + `".DE"`, de-duplicated, order kept.
  - `yahoo_search(isin: str) -> list[tuple[str, str | None]]`: `(symbol, shortname)` from `yf.Search(isin, max_results=10, news_count=0).quotes`.
  - `yahoo_quote(ticker: str, on: date | None) -> tuple[str | None, Decimal | None]`: currency from `yf.Ticker(ticker).fast_info["currency"]`; close from `history(start=on - 5 days, end=on + 1 day)` (or `period="5d"` when `on` is None), last non-NaN `Close` as `Decimal(str(round(x, 4)))`; `None` when there is none.

- [ ] **Step 1: Write the failing tests** (patch `urllib.request.urlopen` and `yf.Ticker` / `yf.Search` in `app.core.instruments`):
  - `test_figi_tickers_keeps_german_composite_only`: response data with `exchCode` `"GR"` (`EUNL`), `"GY"` (`EUNL`) and `"LN"` (`IWDA`) → `["EUNL.DE"]`.
  - `test_figi_tickers_no_match_returns_empty`: response `[{"warning": "No identifier found."}]` → `[]`.
  - `test_yahoo_quote_skips_nan_close`: history with closes `[131.5, NaN]` → `("EUR", Decimal("131.5"))`; all-NaN → `("EUR", None)`.
  - `test_resolve_isin_uses_real_lookups_by_default`: `inspect.signature(resolve_isin).parameters["figi_tickers"].default is figi_tickers` (same for the other two).
  - Live, marked `@pytest.mark.live_api`: `test_live_resolves_public_isin`: `resolve_isin("IE00B4L5Y983").ticker == "EUNL.DE"`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_instruments.py -q`. Expected: new tests FAIL.

- [ ] **Step 3: Implement** the three functions and wire them in as defaults.

- [ ] **Step 4: Run** the tests, then `.venv/bin/python -m pytest tests/test_instruments.py --run-live-api -q -k live`. Expected: PASS (the live one needs network).

- [ ] **Step 5: Commit**: `feat(investments): OpenFIGI and Yahoo lookups for ISIN resolution`.

### Task 4: Service layer

**Files:**
- Modify: `app/core/instruments.py`
- Test: `tests/test_instruments.py`

**Interfaces:**
- Consumes: `Instrument`, `EtfTransaction.isin`, `EtfPurchaseSchedule.isin` (Task 1); `resolve_isin`, `normalize_isin`, `Resolution` (Task 2).
- Produces (none of them commit; callers do):
  - `set_instrument_ticker(db, instrument, ticker: str, currency: str, *, manual: bool) -> None`
  - `apply_resolution(db, instrument, resolution: Resolution) -> None`: stores `name` (only if the instrument has none), `resolution_note`; calls `set_instrument_ticker(..., manual=False)` when resolved, else leaves `yahoo_ticker` as it is.
  - `get_or_resolve(db, isin: str, name: str | None = None, reference=None, *, resolver=resolve_isin) -> Instrument`
  - `re_resolve(db, instrument, *, resolver=resolve_isin) -> Instrument`: raises `PermissionError` if `manual_override`.
  - `link_ticker(db, instrument, ticker_symbol: str) -> dict`: returns `{"transactions": n, "schedules": n, "conflicts": n}`; raises `LookupError` if no row at all has that ticker.
  - `reference_for(db, isin: str) -> tuple[date, Decimal] | None`: latest linked transaction (by `transaction_date`) with non-zero shares; price = `abs(fiat_invested) / abs(shares_acquired)`.

- [ ] **Step 1: Write the failing tests** (use `db_session`; `resolver` is a fake returning a fixed `Resolution`):
  - `test_set_ticker_updates_linked_transactions_and_schedules`: one linked transaction and one linked schedule with ticker `OLD`, one unlinked `OLD` row; after `set_instrument_ticker(..., "EUNL.DE", "EUR", manual=True)`: linked rows are `EUNL.DE`, the unlinked one is still `OLD`, `manual_override is True`, `resolved_at` set.
  - `test_get_or_resolve_creates_then_caches`: the fake counts calls; two calls with `" ie00b4l5y983"` and `"IE00B4L5Y983"` → one instrument, one resolver call.
  - `test_get_or_resolve_unresolved_is_not_retried`: resolver returns no ticker; second call makes no resolver call.
  - `test_re_resolve_refuses_override`: `manual_override=True` → `PermissionError`.
  - `test_apply_resolution_keeps_given_name`: instrument created with name `"My fund"`; resolution name `"Other"` → name stays `"My fund"`.
  - `test_link_sets_isin_and_syncs_ticker`: resolved instrument `EUNL.DE`; two transactions and one schedule with ticker `IWDA`, `isin` NULL → counts `{"transactions": 2, "schedules": 1, "conflicts": 0}`; rows now have the ISIN and ticker `EUNL.DE`.
  - `test_link_unresolved_keeps_ticker`: unresolved instrument → rows get the ISIN, ticker unchanged.
  - `test_link_counts_conflicts`: a row with that ticker already linked to another ISIN → not changed, `conflicts == 1`.
  - `test_link_twice_returns_zero_counts` (Review Focus 3): second call → all counts 0, no exception.
  - `test_link_unknown_ticker_raises`: `LookupError`.
  - `test_reference_for_latest_fill`: two linked transactions → `(date of the later, abs(fiat)/abs(shares))`; none → `None`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_instruments.py -q`. Expected: new tests FAIL.

- [ ] **Step 3: Implement.** Bulk updates via `db.query(...).filter(... .isin == isin).update({...}, synchronize_session="fetch")`.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Commit**: `feat(investments): store instruments and keep linked tickers in sync`.

### Task 5: API

**Files:**
- Create: `app/api/v1/instruments.py` (`instruments_router = APIRouter()`)
- Modify: `app/main.py` (include it with `prefix="/v1/investments"`, `tags=["Investments"]`, `dependencies=[Depends(require_parent)]`)
- Modify: `app/api/v1/shares.py` (`create_schedule` gains `isin: Optional[str] = None`)
- Test: `tests/test_instruments_api.py`

**Interfaces:**
- Consumes: Task 4's functions; `yahoo_quote` and `PRICE_TOLERANCE` (Tasks 2–3).
- Produces: the endpoints in the spec's API table. Instrument JSON: `{isin, name, yahoo_ticker, currency, status, resolution_note, resolved_at, transactions, schedules}`; `status` is `"override"` if `manual_override`, else `"resolved"` if `yahoo_ticker`, else `"unresolved"`. The 409 mismatch body: `{"detail": {"message": ..., "reference_date", "reference_price", "close"}}`.

Tests patch `app.core.instruments.figi_tickers`, `yahoo_search` and `yahoo_quote` with fakes, so the real defaults are never called. Use `parent_client` and `client` fixtures.

- [ ] **Step 1: Write the failing tests:**
  - `test_add_isin_resolves_and_lists`: POST `{"isin": " ie00b4l5y983 "}` → 200, `isin == "IE00B4L5Y983"`, `status == "resolved"`; GET lists it once.
  - `test_add_existing_isin_does_not_look_up_again`.
  - `test_add_invalid_isin_400`.
  - `test_resolve_refuses_override_409`, `test_resolve_unknown_isin_404`.
  - `test_override_normalises_ticker` (Review Focus 2): PUT `{"yahoo_ticker": "eunl.de "}` → stored `EUNL.DE`, `status == "override"`.
  - `test_override_rejects_non_eur_400`.
  - `test_override_mismatch_409_then_confirm`: linked transaction with fill price 98.27; quote close 110 → 409 with the numbers; same PUT with `"confirm": true` → 200.
  - `test_override_updates_linked_schedule` (Review Focus 5): linked schedule's `ticker_symbol` becomes the new ticker.
  - `test_link_returns_counts` and `test_link_unknown_ticker_404`.
  - `test_schedule_with_resolved_isin_uses_its_ticker`: POST `/v1/investments/etf/schedule?ticker=x&amount=10&day=5&isin=IE00B4L5Y983` → schedule ticker `EUNL.DE`, `isin` set.
  - `test_schedule_with_unresolved_isin_400`.
  - `test_instruments_require_login`: unauthenticated GET → 401.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_instruments_api.py -q`. Expected: FAIL (404s).

- [ ] **Step 3: Implement** the router and the `create_schedule` change. Map `ValueError` → 400, `LookupError` → 404, `PermissionError` → 409. Commit the session after each successful change.

- [ ] **Step 4: Run** the tests, then the full suite `.venv/bin/python -m pytest -q` and `.venv/bin/flake8 .`. Expected: all pass, flake8 silent.

- [ ] **Step 5: Commit**: `feat(investments): instruments API and ISIN on schedules`.

### Task 6: Admin page

**Files:**
- Modify: `investments-frontend/src/views/AdminView.vue`

**Interfaces:**
- Consumes: Task 5's endpoints via the existing `api` axios instance (paths start `/investments/...`).

- [ ] **Step 1: Add the Instruments section** as in the spec's admin page section: table, unresolved rows highlighted, per-row Re-resolve (hidden for overrides) / Set ticker / Link existing ticker, Add ISIN form, optional ISIN on the schedule form. On a 409 from Set ticker, show the reference date, fill price and close in a `confirm()` and resend with `confirm: true`. Errors use `(e.response?.data?.detail?.message || e.response?.data?.detail || e.message)`.

- [ ] **Step 2: Verify** `cd investments-frontend && npm run build`. Expected: build succeeds. Then restore the tracked `dist/` (`git checkout -- investments-frontend/dist && git clean -f investments-frontend/dist`).

- [ ] **Step 3: Check it in a browser** against a local API on the test database (fakes not needed: add a public ISIN for real). Expected: add, list, override, link all work.

- [ ] **Step 4: Commit**: `feat(investments): manage instruments in the admin panel`.

### Task 7: Finish

- [ ] **Step 1:** Full suite, flake8, frontend build: all green.
- [ ] **Step 2:** Push `feat/isin-instruments`, open a PR that closes #38 and states the deploy order: build, then `docker compose run --rm api alembic -c /code/alembic.ini upgrade head`, then `docker compose up -d api investments-ui`.
