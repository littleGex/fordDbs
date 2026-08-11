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

From your project root (where `app/` and `pytest.ini` live):

```bash
pytest
```

`live_api` tests are **always skipped automatically**, with no flag
needed -- this is enforced in `conftest.py` via a
`pytest_collection_modifyitems` hook, not via `addopts`. (An earlier
approach used `pytest -m "not live_api"`, but that has a sharp edge:
pytest's `-m` flag on the command line *replaces* any marker filter
set via `addopts` rather than combining with it, so
`pytest -m "not integration"` would have silently let `live_api` tests
back in. The hook-based approach avoids that entirely -- `-m` is now
free to use for `integration`/`unit` filtering with no risk of
re-including `live_api` tests by accident.)

If you used different ports/credentials for the test container, override
via environment variables:

```bash
TEST_DB_HOST=localhost \
TEST_DB_PORT=5434 \
TEST_POSTGRES_USER=test \
TEST_POSTGRES_PASSWORD=test \
TEST_POSTGRES_DB=forddbs_test \
pytest
```

Defaults already match the `docker run` command above, so if you used
it verbatim you can just run `pytest` with no env vars.

### Running only fast (non-DB) tests

```bash
pytest -m "not integration"
```

This runs `TestCalculateAge`, all of `test_utils.py`, and the mocked
parts of `test_invest.py` -- useful as a quick pre-commit check
without needing the test database running. (`live_api` tests remain
skipped automatically, as always.)

### Running the live API smoke test deliberately

```bash
pytest --run-live-api
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
  session. Under Postgres's READ COMMITTED isolation, that independent
  connection can only see rows that were *actually* committed —
  `db_session`'s "commits" happen inside an externally-managed
  transaction (`connection.begin()`) that's only ever rolled back, so
  they're invisible to it. These tests use the `make_real_child` /
  `real_child_age_10` fixtures instead, which commit through their own
  independent connection so `run_weekly_payout()` can genuinely find
  and update the rows, and clean themselves up for real afterward
  (`make_real_child`'s fixture teardown in `conftest.py`). If a test
  using these fixtures fails partway through in a way that skips
  teardown, you may need to manually clear test rows from the
  `forddbs_test` database — this only affects the disposable test DB,
  never production.

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
| `test_family_photos.py` | The `liked_by` avatar feature: empty/single/multiple likers, display-name fallback, avatar URL presence, like/unlike toggling, auth requirement, consistency across `/feed`, `/archive`, `/albums/{id}/photos` |

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
  `@pytest.mark.live_api` smoke test, excluded from normal runs by
  default (run deliberately with `pytest --run-live-api`).

## Bugs found and fixed while building out this suite

- **`update_child` (`app/api/v1/pocket_money.py`)** committed the
  updated `Child` but never called `db.refresh(child)` before
  returning it. SQLAlchemy expires an object's attributes on commit by
  default, so the JSON response FastAPI serialized back was missing
  fields entirely (`KeyError: 'name'` in
  `test_update_child_name`) rather than returning stale data. Fixed by
  adding the same `db.refresh(child)` call `add_child` and
  `adjust_balance` already use.
- **`TestRunWeeklyPayout` (`test_scheduler.py`)** — 3 of its 5 tests
  were failing, and the other 2 were passing vacuously (not actually
  exercising `run_weekly_payout` against any data). Root cause was a
  test-fixture isolation gap, not an app bug: see the "Safety
  guardrails" note above on `make_real_child`. Fixed by switching
  these tests to fixtures that commit through a genuinely separate
  connection.

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
- **`bcrypt` is missing from `requirements.txt`** entirely, despite
  `passlib`'s `CryptContext(schemes=["bcrypt"], ...)` requiring it as a
  backend. In a clean environment this makes every password hash/verify
  call (user creation, login, password reset) throw an uncaught
  `passlib.exc.MissingBackendError`, which surfaces to a browser as a
  confusing CORS failure rather than a clear error. Additionally,
  whatever the latest `bcrypt` happens to be (5.0.0 as of this
  writing) is incompatible with this pinned `passlib` 1.7.4 --
  `bcrypt==4.0.1` is confirmed compatible. Needs a pin added to
  `requirements.txt`.
- **CI**: none of this runs automatically yet. Once you're happy with
  local results, a GitHub Actions workflow with a `postgres:15-alpine`
  service container would let this run on every push with no manual
  `docker run` step.
