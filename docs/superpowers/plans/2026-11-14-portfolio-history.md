# Portfolio Value Over Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chart ETF and stock market value against net money invested (fees included) per day, backed by a server-side cache of daily Yahoo closes.

**Architecture:** Two tables (`price_history`, `price_fetch_state`) cache unadjusted daily closes and per-ticker fetch progress. `ensure_price_history` fills only missing ranges in one batched `yf.download`. `portfolio_history` rebuilds holdings and invested per calendar day from `etf_transactions`, pricing each ticker from cached closes and its own fill prices. A parents-only endpoint serves the series; a 06:00 job keeps the cache warm; the dashboard draws it with range buttons. The summary's ETF invested starts including fees.

**Tech Stack:** FastAPI, SQLAlchemy 2 (Postgres `insert ... on_conflict_do_nothing`), Alembic, yfinance 1.7.0, pandas, APScheduler, pytest (Postgres on 5434), Vue 3 + Chart.js 4.

**Spec:** `docs/superpowers/specs/2026-11-14-portfolio-history-design.md`

## Global Constraints

- Closes are fetched with `auto_adjust=False` and read from the `Close` column; one batched `yf.download(..., interval="1d", progress=False, timeout=10)` per fill.
- Only days before today (Europe/Berlin) are cached; `through` defaults to yesterday in Europe/Berlin.
- Rows whose `ticker_symbol` is a valid ISIN (#38's `normalize_isin` succeeds and returns it unchanged) are never fetched.
- Invested = running sum of `fiat_invested + coalesce(fees, 0)` over all `etf_transactions` rows (every `entry_type`); the same definition in `get_grouped_etfs`.
- Price on day d = latest observation on or before d among cached closes (`close > 0`) and fill prices `|fiat| / |shares|` (rows with non-zero shares and fiat); a close wins over a fill on the same date; on today a live price > 0 wins.
- Endpoint `GET /v1/investments/etf/history`, parents only; response `{"points": [{"date", "value", "invested"}], "stale": [{"ticker", "through"}], "as_of"}`.
- Scheduler job at 06:00 Europe/Berlin, `misfire_grace_time=86400`.
- No network in tests; `download` is injectable and defaults to `yf.download` looked up at call time.
- flake8 7.4.1 clean, max-complexity 14. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; stage files by name; never commit `dist/`, `node_modules/` or `.idea/`.

## Review Focus

1. **Single-ticker download** — yfinance may return flat (non-MultiIndex) columns when one ticker is requested; closes must still be read. Test in Task 3.
2. **Ticker changed after the cache was filled** (Set ticker / Link): the new ticker has no fetch state, so its history is fetched from its first trade date on the next call. Test in Task 3.
3. **Live price missing today** (Yahoo down, live price 0): today's point carries the last known price, never values the holding at 0. Test in Task 4.
4. **Holding sold to zero and bought again later**: value is 0 in between and resumes from the new buy, priced by the newest observation. Test in Task 4.
5. **First and only trade today**: one point, priced by the live price or the fill. Test in Task 4.

---

### Task 1: Tables and migration

**Files:**
- Modify: `app/models/shares_models.py`
- Create: `alembic/versions/e5f1a3c7d9b2_add_price_history.py`
- Test: `tests/test_price_history.py` (new)

**Interfaces:**
- Produces: `PriceHistory(ticker: String PK, day: Date PK, close: Numeric(14, 6) not null, fetched_at: DateTime server_default now())`, `__tablename__ = "price_history"`; `PriceFetchState(ticker: String PK, fetched_through: Date not null)`, `__tablename__ = "price_fetch_state"`.

- [ ] **Step 1: Failing tests** `TestTables`: `test_close_is_stored_per_ticker_and_day` (add two rows same ticker different days, flush, query back closes as `Decimal`); `test_same_ticker_and_day_twice_is_rejected` (`IntegrityError` on flush); `test_fetch_state_round_trip`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_price_history.py -q`. Expected: ImportError on `PriceHistory`.
- [ ] **Step 3: Add the two models.**
- [ ] **Step 4: Run** — expected 3 passed.
- [ ] **Step 5: Migration** `e5f1a3c7d9b2`, `down_revision = 'c4d8e2a6f0b1'`: create both tables if they don't exist (startup `create_all` may have made them, as in `a7c3e9f1b2d4`); downgrade drops both. Verify on scratch database `ph_mig` in the test container: `create_all` from `main`'s models (temporary worktree), `stamp c4d8e2a6f0b1`, then on this branch `upgrade head` → `downgrade -1` → `upgrade head`, listing the two tables after each; also `upgrade head` once on a database where `create_all` already made them. Run alembic as `.venv/bin/python -m alembic`. Expected: tables present / absent / present; no error when they pre-exist. Drop `ph_mig`, remove the worktree.
- [ ] **Step 6: Commit** `feat(investments): price history cache tables`.

---

### Task 2: Summary invested includes fees

**Files:**
- Modify: `app/core/investments.py` (`get_grouped_etfs`)
- Test: `tests/test_invest.py` (append class `TestSummaryInvested`)

**Interfaces:**
- Produces: `get_grouped_etfs` rows' `total_invested` = `sum(fiat_invested + coalesce(fees, 0))`.

- [ ] **Step 1: Failing test** `test_invested_includes_fees`: rows `EUNL.DE` (fiat 100.00, fees 1.00, shares 1) and (fiat −50.00, fees 1.00, shares −0.5); `get_portfolio_summary(db_session)` with `app.core.investments.fetch_live_prices` patched to return `{"EUNL.DE": 120.0}`; the `EUNL.DE` entry has `total_invested == 52.0`; and `test_missing_fees_count_as_zero` (one row with `fees=None` → invested equals fiat).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_invest.py -q -k SummaryInvested`. Expected: FAIL (50.0 != 52.0).
- [ ] **Step 3: Change** `get_grouped_etfs` to sum `fiat_invested + func.coalesce(fees, 0)`.
- [ ] **Step 4: Run** — expected pass; then `.venv/bin/python -m pytest tests/test_invest.py -q` all pass.
- [ ] **Step 5: Commit** `fix(investments): count fees in ETF invested`.

---

### Task 3: `ensure_price_history`

**Files:**
- Create: `app/core/price_history.py`
- Test: `tests/test_price_history.py`

**Interfaces:**
- Consumes: `PriceHistory`, `PriceFetchState` (Task 1); `normalize_isin` from `app.core.instruments`.
- Produces:
  - `BERLIN = pytz.timezone("Europe/Berlin")`; `berlin_today() -> date`.
  - `ensure_price_history(db: Session, tickers: Optional[Iterable[str]] = None, *, through: Optional[date] = None, download: Optional[Callable] = None) -> Dict[str, Optional[date]]` — returns stale tickers → their `fetched_through` (or None). Does not commit.
  - `cached_closes(db: Session, tickers: Iterable[str]) -> Dict[str, List[Tuple[date, Decimal]]]` (sorted by day) for Task 4.

- [ ] **Step 1: Failing tests** (class `TestEnsurePriceHistory`; helper `frame(closes: dict[ticker -> dict[date -> float]], multi=True)` building a yfinance-shaped DataFrame with `("Close", ticker)` columns, or flat `Close` column when `multi=False`; `FakeDownload` recording `(tickers, start, end, kwargs)` and returning a set frame or raising; transactions added with an `add_txn(ticker, day, fiat, shares, fees=0)` fixture; `THROUGH = date(2026, 3, 9)` (a Monday)):
  - `test_first_fill_fetches_from_first_trade_in_one_call`: EUNL.DE first trade 2026-03-02, APC.DE 2026-03-04 → one call with both tickers, `start == date(2026, 3, 2)`, `end == date(2026, 3, 10)`, `kwargs["auto_adjust"] is False`; returned closes stored; both states `fetched_through == THROUGH`; result `{}`.
  - `test_only_missing_days_are_fetched`: state EUNL.DE through 2026-03-05 → call starts 2026-03-06 and lists only EUNL.DE (APC.DE state at THROUGH).
  - `test_current_tickers_make_no_call`: all states at THROUGH → download not called.
  - `test_weekend_without_closes_is_not_refetched_or_stale`: state at Friday 2026-03-06, `through=date(2026, 3, 8)` (Sunday), download returns an empty frame → state moves to 2026-03-08; a second call makes no download; result `{}`.
  - `test_isin_ticker_rows_are_never_fetched`: rows with ticker `IE00BK5BQT80` → not in any call.
  - `test_bad_closes_are_dropped`: NaN, 0 and −1 closes, and a row dated after `through`, are not stored; a row dated before the ticker's missing start is not stored.
  - `test_repeated_fill_is_harmless`: a close already cached for a day is returned again (state reset to before it) → no error, one row.
  - `test_download_failure_marks_stale_and_changes_nothing`: download raises → result has both tickers (values = previous `fetched_through` or None); no rows or states written.
  - `test_unknown_ticker_is_marked_fetched`: frame lacks a requested ticker → its state is set, it has no rows, not stale.
  - `test_single_ticker_flat_columns_are_read` (Review Focus 1): `multi=False` frame for one ticker → its closes stored.
  - `test_new_ticker_after_change_is_fetched_from_first_trade` (Review Focus 2): EUNL.DE state at THROUGH; rename its rows to `IWDA.DE` → the next call fetches `IWDA.DE` from the first trade date.
  - `test_cached_closes_sorted_per_ticker`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_price_history.py -q -k Ensure`. Expected: ImportError.
- [ ] **Step 3: Implement.** Missing start per ticker = state + 1 day, else first `transaction_date.date()`; call download once with the union, `start` = earliest missing start, `end = through + 1 day`. Read `Close` per ticker from a MultiIndex frame (`frame["Close"][ticker]` when present) or the flat `Close` column when exactly one ticker was requested; drop NaN/≤0, days outside `[start_of_ticker, through]`. Insert with `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_nothing()`; upsert states with `on_conflict_do_update`. On download exception: `logger.exception`, return stale for all requested, write nothing. Keep helpers under complexity 14.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** `feat(investments): cache daily closes for portfolio history`.

---

### Task 4: `portfolio_history`

**Files:**
- Create: `app/core/portfolio_history.py`
- Test: `tests/test_portfolio_history.py` (new)

**Interfaces:**
- Consumes: `cached_closes` (Task 3); `EtfTransaction`.
- Produces: `portfolio_history(db: Session, today: date, live_prices: Dict[str, float]) -> List[dict]` with `{"date": "YYYY-MM-DD", "value": float, "invested": float}` per calendar day, rounded to cents.

- [ ] **Step 1: Failing tests** (rows via `add_txn(ticker, day, fiat, shares, fees=0)`, closes via direct `PriceHistory` rows; `points_by_date(result)` helper):
  - `test_shares_and_invested_build_on_trade_dates`: buy 2026-03-02 (fiat 100, fees 1, shares 1), buy 2026-03-04 (fiat 50, shares 0.5); today 2026-03-05 → 4 points; invested 101, 101, 151, 151.
  - `test_sell_lowers_invested_by_proceeds_minus_fee`: buy (100, 1 fee, 1 share), sell (−60, fee 1, −0.5) → invested after sell 42.
  - `test_weekend_carries_fridays_close`: closes Fri 2026-03-06 = 110, none Sat/Sun → Sat and Sun value = shares × 110.
  - `test_fill_price_where_no_close`: no closes, buy 1 share for 100 → value 100 that day and carried.
  - `test_close_wins_over_fill_on_same_day`: fill 100 and close 104 on the trade day → value 104.
  - `test_liquidated_fund_priced_at_fills_then_zero`: ticker `IE00BK5BQT80`, buys at 11 then liquidation sell −2 shares / −24 → value at buys from fills, 0 from the liquidation day.
  - `test_zero_share_or_zero_fiat_rows_give_no_price`: buy at 100, then a liquidation row with fiat 0 and −0.5 shares the next day → price still 100 (no 0 price).
  - `test_today_uses_live_price`: close yesterday 110, live 115 → today's value = shares × 115.
  - `test_missing_live_price_carries_last_price` (Review Focus 3): live price 0 → today = shares × last close.
  - `test_sold_out_then_rebought` (Review Focus 4): buy, sell all, buy again at a new price → 0 in between, then new shares × newest observation.
  - `test_first_trade_today` (Review Focus 5): one row today, live 101 → `[{"date": today, "value": shares × 101, ...}]`.
  - `test_no_transactions_gives_empty_list`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_portfolio_history.py -q`. Expected: ImportError.
- [ ] **Step 3: Implement.** Load rows ordered by `transaction_date`; per ticker build observations = closes (`close > 0`) plus fills (non-zero shares and fiat), kept as a sorted list of `(day, source_rank, price)` with close ranked after fill so it wins on ties; walk days from the first trade to `today`, applying that day's rows, advancing each ticker's observation pointer, and on `today` overriding with a live price > 0. Floats only at the output; accumulate in `Decimal`.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** `feat(investments): rebuild portfolio value per day`.

---

### Task 5: Endpoint and daily job

**Files:**
- Create: `app/api/v1/portfolio_history.py` (`history_router`)
- Modify: `app/main.py` (mount under `/v1/investments`, `require_parent`), `app/core/scheduler.py`
- Test: `tests/test_portfolio_history_api.py` (new), `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `ensure_price_history`, `berlin_today` (Task 3), `portfolio_history` (Task 4), `fetch_live_prices` from `app.core.investments`.
- Produces: `GET /etf/history` on `history_router`; `run_price_history_refresh(db: Session = None) -> None` in `app/core/scheduler.py`.

- [ ] **Step 1: Failing API tests** (patch `app.api.v1.portfolio_history.ensure_price_history` and `...fetch_live_prices`; `URL = "/v1/investments/etf/history"`):
  - `test_returns_points_stale_and_as_of`: one buy, ensure returns `{"SMC.PA": date(2026, 3, 6)}` → 200; keys `{"points", "stale", "as_of"}`; `stale == [{"ticker": "SMC.PA", "through": "2026-03-06"}]`; last point value = shares × live price.
  - `test_empty_portfolio`: `points == []`, `stale == []`.
  - `test_requires_login`: 401.
- [ ] **Step 2: Failing scheduler tests:** `test_price_refresh_job_registered_at_six` (patch `app.core.scheduler.BackgroundScheduler`; `start_scheduler()`; one `add_job` call with `run_price_history_refresh`, `'cron'`, `hour=6`, `minute=0`, `misfire_grace_time=86400`); `test_price_refresh_runs_ensure_and_commits` (patch `app.core.scheduler.ensure_price_history`; call with `db_session` → called once with `db_session`).
- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/test_portfolio_history_api.py tests/test_scheduler.py -q`. Expected: new tests fail (404 / ImportError / no such job).
- [ ] **Step 4: Implement** the router (ensure → commit → tickers from rows → live prices → `portfolio_history(db, berlin_today(), live)`; `stale` as list sorted by ticker with ISO dates or None) and the job (own `SessionLocal` when `db` is None, commit, log and swallow exceptions, close its own session).
- [ ] **Step 5: Run** — expected pass; then `.venv/bin/python -m pytest tests/test_scheduler.py tests/test_invest.py -q` all pass.
- [ ] **Step 6: Commit** `feat(investments): portfolio history endpoint and daily price refresh`.

---

### Task 6: Dashboard chart

**Files:**
- Modify: `investments-frontend/src/views/DashboardView.vue`

No frontend test framework; verification is the build plus a local run.

- [ ] **Step 1:** After the summary loads, fetch `/investments/etf/history` (its own try/catch; failure hides the section and logs). Section "Value over time" under the Total Wealth card, hidden when `points` is empty: line "Value" (`#4a90e2`, filled) and "Invested" (`#95a5a6`, `stepped: true`), `pointRadius: 0`, x-axis `maxTicksLimit: 6`, y-axis `€` ticks as elsewhere; tooltip (`mode: 'index'`, `intersect: false`) shows value, invested and gain € and % (gain % = gain / invested when invested > 0). Range buttons 1M, 6M, YTD, 1Y, All (default) filter points client-side by date. Under the chart, one line per stale ticker: "Prices for {ticker} are up to date only until {date}" (or "have not been fetched yet" when `through` is null).
- [ ] **Step 2: Build** `cd investments-frontend && npm run build`; restore `git checkout -- dist && git clean -fq dist`. Expected `✓ built`; only `DashboardView.vue` modified.
- [ ] **Step 3: Local run:** scratch DB, local API with the Trade Republic fixture imported, real Yahoo; `GET /etf/history` twice: first fills the cache, second makes no download (check `price_fetch_state`, timing). If Claude in Chrome is connected, view the chart; otherwise say so.
- [ ] **Step 4: Commit** `feat(investments): value over time chart on the dashboard`.

---

### Task 7: Verify and PR

- [ ] **Step 1:** Full suite to a log file in the workspace, tail; `.venv/bin/flake8 .`. Expected: all pass, flake8 silent.
- [ ] **Step 2:** Push `feat/portfolio-history`, open a PR closing #52: what it does, the invested-includes-fees change to the card, the migration deploy order (back up → build `api investments-ui` → `docker compose run --rm --no-deps api alembic -c /code/alembic.ini upgrade head` → `docker compose up -d api investments-ui`), first load fills the cache, whether the chart was viewed in a browser. No holdings or amounts. Do not merge.
