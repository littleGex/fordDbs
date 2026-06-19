# Pocket Money Test Suite

Tests for `app/api/v1/pocket_money.py` and `app/core/scheduler.py`
(`run_weekly_payout` / `calculate_age`).

## Why a real Postgres database?

The bug this suite primarily guards against (float-precision drift in
money columns) is specific to how Python's `float` interacts with a
real `NUMERIC` column on round-trip through Postgres. SQLite's loose
type affinity would not reliably reproduce the original failure mode,
so these tests intentionally run against a disposable real Postgres
instance rather than SQLite or mocks.

## One-time setup: start a disposable test database

Run this alongside your existing `postgres_db` container — it's
separate and safe to throw away:

```bash
docker run --rm -d \
    --name forddbs-test-db \
    -e POSTGRES_USER=test \
    -e POSTGRES_PASSWORD=test \
    -e POSTGRES_DB=forddbs_test \
    -p 5434:5432 \
    postgres:15-alpine
```

This binds to host port `5434` (not `5433`, which your real `postgres_db`
container already uses) so the two can run side by side without
colliding.

## Install test dependencies

From your project root (where `requirements.txt` lives):

```bash
pip install pytest httpx --break-system-packages
```

(`httpx` is required by FastAPI's `TestClient`.)

## Running the tests

From your project root, with `tests/` alongside `app/`:

```bash
pytest -m "not live_api"
```

`live_api` tests call the real Yahoo Finance API and are excluded by
default for determinism. **Always include `-m "not live_api"`** (or a
more specific marker expression, e.g. `-m "not live_api and not integration"`)
in your standard run command -- pytest's `-m` flag on the command line
*replaces* any marker filter rather than combining with one set via
`addopts`, so there is no fully "automatic" exclusion; it must be
specified explicitly each time, which is why every example in this
README includes it.

If you used different ports/credentials for the test container, override
via environment variables:

```bash
TEST_DB_HOST=localhost \
TEST_DB_PORT=5434 \
TEST_POSTGRES_USER=test \
TEST_POSTGRES_PASSWORD=test \
TEST_POSTGRES_DB=forddbs_test \
pytest -m "not live_api"
```

Defaults already match the `docker run` command above, so if you used
it verbatim you can just run `pytest -m "not live_api"` with no env vars.

### Running only fast (non-DB) tests

```bash
pytest -m "not integration and not live_api"
```

This runs `TestCalculateAge`, all of `test_utils.py`, and the mocked
parts of `test_invest.py` -- useful as a quick pre-commit check
without needing the test database running.

### Running the live API smoke test deliberately

```bash
pytest -m live_api
```

Only do this when you want to manually verify Yahoo Finance
connectivity end-to-end. Expect occasional failures unrelated to your
code (market closed, rate limiting, network issues) -- this is a
smoke test, not a regression guard.

### Running a single file or test

```bash
pytest tests/test_pocket_money_precision.py
pytest tests/test_pocket_money_precision.py::TestFloatPrecisionRegression::test_withdraw_exact_balance_succeeds
```

## Safety guardrails built into conftest.py

- `db_engine` refuses to run (`pytest.exit`) if it can't connect to the
  test database, or if the resolved database name doesn't look like a
  test database — this is a deliberate safeguard against ever running
  destructive tests against your real `forddbs` production data.
- Every test runs inside a transaction that's rolled back afterward
  (`db_session` fixture), so most tests leave zero trace.
- **Exception:** `test_scheduler.py`'s `TestRunWeeklyPayout` tests call
  `run_weekly_payout()` directly, which opens its **own** database
  session (`SessionLocal()`) rather than using the injected test
  session. This means those specific tests commit for real and clean
  up manually via an explicit `_cleanup()` helper. If a test in that
  class fails partway through, you may need to manually clear test
  rows from the `forddbs_test` database — this only affects the
  disposable test DB, never production.

## What's covered

| File | Covers |
|---|---|
| `test_pocket_money_precision.py` | The original bug report (14.63€/15€) + float-drift stress tests |
| `test_pocket_money_balance.py` | deposit, withdraw, adjust-balance, adjust, balance lookup |
| `test_pocket_money_admin.py` | child CRUD, password protection |
| `test_pocket_money_wishes.py` | wish CRUD, negative-cost guards |
| `test_pocket_money_deductions.py` | deduction catalog CRUD, deduct-batch (incl. the dict-subscript regression) |
| `test_pocket_money_stats.py` | history, stats aggregation (incl. total_spent regression) |
| `test_scheduler.py` | `calculate_age` (pure), `run_weekly_payout` (incl. the Decimal/float TypeError regression) |
| `test_utils.py` | Utility-meter dashboard helpers (rewritten against real `utils_core.py` -- see note below) |
| `test_invest.py` | `fetch_live_prices` mocked logic + opt-in live-API smoke test (rewritten -- see note below) |

## Notes on rewritten tests

Three hand-written tests were found in the repo during this review
that didn't actually test the real code correctly. They've been
rewritten and folded into this suite:

- **`test_pocket_logic.py` → merged into `test_scheduler.py`**: the
  original asserted `age * 0.5 == 5.5` directly, which only re-proves
  Python float arithmetic and doesn't exercise the app. It happened to
  encode the exact float pattern that later broke `run_weekly_payout`
  in production. The real scenarios are preserved as
  `test_age_birthday_still_upcoming_same_year` /
  `test_age_birthday_just_passed_same_year`, asserting only the age
  calculation -- payout math is verified separately against the real
  Decimal-based code in `TestRunWeeklyPayout`.

- **`test_utils.py`**: the original asserted `feb_record["usage"]["net_elect"]`
  and `feb_record["is_february"]`, neither of which exist anywhere in
  the real `_calculate_deltas_and_net` function (it only ever produces
  `date`, `readings`, `usage`, `resets`). This test could never have
  passed against the actual code. Rewritten against the function as it
  actually exists, including a new test for the meter-reset detection
  branch that wasn't covered before.

- **`test_invest.py`**: the original `test_fetch_live_prices_integration`
  called the real Yahoo Finance API with no mocking and asserted a
  hardcoded price range, making it fragile and non-deterministic (and
  unusable in network-restricted environments like CI sandboxes).
  Rewritten with full mocking for deterministic logic tests, plus
  several new edge cases (missing ticker, all-NaN series, download
  exception). The real-API check is preserved as an explicitly opt-in
  `@pytest.mark.live_api` smoke test, excluded from normal runs.

## Known gaps / suggested next steps

- **`db_manager.py` and most of `shares.py`** have little to no
  authentication on data-mutating endpoints (flagged separately,
  outside this suite's scope) -- not covered by tests here since the
  priority is fixing the auth gap itself before testing around it.
- **`Wish.cost`** is still a `Float` column in `user_models.py` (it was
  missed during the earlier `Numeric` migration of `balance`/`amount`/
  `default_amount`). The wish tests in this suite use round numbers
  that won't expose drift, but this is worth fixing for consistency --
  flagging it here rather than silently working around it.
- **CI**: none of this runs automatically yet. Once you're happy with
  local results, a GitHub Actions workflow with a `postgres:15-alpine`
  service container would let this run on every push with no manual
  `docker run` step.
