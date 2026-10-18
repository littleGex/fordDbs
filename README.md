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

Tests that actually upload a file (image or video, in
`test_family_photos_video_upload.py`) also need a disposable test MinIO
instance -- same idea as the test Postgres above:

```bash
docker run --rm -d \
    --name forddbs-test-minio \
    -e MINIO_ROOT_USER=testadmin \
    -e MINIO_ROOT_PASSWORD=testpassword \
    -p 9002:9000 \
    pgsty/minio:RELEASE.2026-08-04T00-00-00Z server /data
```

Port `9002` (not `9000`, which your real `minio` container already uses)
so the two can run side by side. Without this, `conftest.py`'s
`minio_test_bucket` fixture skips those specific tests with a clear
message rather than failing on a raw `NameResolutionError` three layers
deep in MinIO's SDK -- that's what you'll see if you run the suite
without starting this container.

## Install test dependencies

From your project root (where `requirements.txt` lives):

```bash
pip install pytest httpx --break-system-packages
```

(`httpx` is required by FastAPI's `TestClient`.)

Video upload tests also need `ffmpeg`/`ffprobe` on `PATH` — same
requirement the app itself has in production (see "Video uploads"
below). On macOS: `brew install ffmpeg`. Like the MinIO container above,
if it's missing those specific tests are skipped automatically rather
than failing the run.

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
| `test_pocket_money_admin.py` | child CRUD |
| `test_pocket_money_auth.py` | login required on every pocket-money route (401), parent/child roles (403), chore-tracker service key |
| `test_accounts.py` | self-registration (pending, birth-year role, limits), admin approval/reject/role/reset routes, role abilities, the recovery CLI |
| `test_household_auth.py` | investments and utilities routes are parents-and-admin only (401 without a token, 403 for adult and child) |
| `test_login_hardening.py` | wrong-password lock-out per device and per account, registration limit, minimum password length, refresh time limit, logging a user out everywhere on a password reset |
| `test_game.py` | `GET /v1/game/family`: game token or any login, response limited to key and birthday, game token rejected on other routes, CLI data entry. `/v1/game/settings`: saving and reading back, version conflicts (409), the field checks including `swapRooms`, `pronoun`, `away`, `swapDesks` and `assign` (422), size (413) and save (429) limits |
| `test_pocket_money_wishes.py` | wish CRUD, negative-cost guards, `cost` column Numeric-precision regression |
| `test_pocket_money_deductions.py` | deduction catalog CRUD, deduct-batch (incl. the dict-subscript regression) |
| `test_pocket_money_stats.py` | history, stats aggregation (incl. total_spent regression) |
| `test_scheduler.py` | `calculate_age` (pure), `run_weekly_payout` (incl. the Decimal/float TypeError regression) |
| `test_utils.py` | Utility-meter dashboard helpers (rewritten against real `utils_core.py` -- see note below) |
| `test_invest.py` | `fetch_live_prices` mocked logic + opt-in live-API smoke test (rewritten -- see note below) |
| `test_family_photos.py` | The `liked_by` avatar feature: empty/single/multiple likers, display-name fallback, avatar URL presence, like/unlike toggling, auth requirement, consistency across `/feed`, `/archive`, `/albums/{id}/photos` |
| `test_family_photos_video_upload.py` | Video upload support: server-side 30s duration enforcement (real ffprobe check, not client-trusted), H.264/AAC MP4 transcoding, corrupt-input rejection, image-path regression |

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
- **`alembic/env.py` never actually ran a migration.** It defined
  `run_migrations_offline()`/`run_migrations_online()` but was missing
  the final `if context.is_offline_mode(): ... else: ...` dispatch call
  that invokes either one — so `alembic upgrade head` always exited 0
  having silently done nothing. Fixed by adding the dispatch call. See
  "Video uploads & deploying this change" below for the full story,
  including a second, separate issue found on the deployed Pi.
- **`Wish.cost`** was still a `Float` column, missed during the earlier
  `Numeric` migration of `balance`/`amount`/`default_amount`. Unlike
  that original bug (which only surfaced after repeated float
  addition), a single stored value often round-trips fine through
  Postgres, so the regression tests added
  (`TestWishCostPrecision` in `test_pocket_money_wishes.py`) check the
  column's actual type and that a fresh read-back is a `Decimal`, not
  a number that happens to survive one round trip. Migration:
  `alembic/versions/824ea1ae3c03_convert_wish_cost_to_numeric.py`.

## Known gaps / suggested next steps

- **Most of `shares.py`** has no functional tests beyond the auth
  checks in `test_household_auth.py` and the price-fetching unit tests.
- **CI**: `.github/workflows/tests.yml` now runs the full suite on PRs
  and pushes to `main`, via a `postgres:15-alpine` service container
  plus an `ffmpeg` install step for the video upload tests. A separate
  `flake8` job checks the code style with the settings in `.flake8`;
  run `flake8 .` locally before pushing.

## Video uploads & deploying this change

Photos and videos share one `/upload` endpoint and one `Photo` model,
distinguished by a new `media_type` column (`"image"` or `"video"`).
Uploaded videos are transcoded server-side to H.264/AAC MP4 (~720p cap)
via `ffmpeg`, with the 30-second limit enforced from `ffprobe`'s actual
decoded duration — never trusted from the client. See `app/core/media.py`.

**This needs `ffmpeg`/`ffprobe` on `PATH`** wherever `/upload` runs — now
included in the root `Dockerfile`. A full `docker compose build api`
(not just a restart) is required to pick this up.

### Applying the schema change to a live database

`app/main.py`'s startup only runs `Base.metadata.create_all()`, which
creates *missing* tables but never `ALTER`s an existing one — so a fresh
deploy alone will **not** add `media_type`/`duration_seconds` to an
already-existing `photos` table. This needs `alembic upgrade head` run
once, manually, after deploying.

Two pre-existing issues were found and fixed while getting this working,
worth knowing before you run it:

1. `alembic/env.py` was missing its dispatch call (see "Bugs found and
   fixed" above) — without this fix, `alembic upgrade head` always did
   nothing, silently, and always would have, independent of anything
   else here.
2. The Pi's deployed image contains an incomplete migration chain (one
   file whose parent revision was never included), **and** the live
   database has no `alembic_version` table at all — Alembic has never
   actually managed this database; the schema has been driven entirely
   by `create_all()` plus, apparently, some manual changes along the way.

Given that, upgrading the Pi isn't a plain `alembic upgrade head`. The
safe sequence, since there's no existing Alembic bookkeeping to protect:

```bash
# 1. Deploy the new image (has the ffmpeg + env.py fix + new migration file)
docker compose build api && docker compose up -d api

# 2. One-time only: tell Alembic the DB is already at the pre-video-upload
#    revision -- this writes one bookkeeping row, it runs no schema SQL.
docker exec database_manager_api alembic -c /code/alembic.ini stamp 26a815029608

# 3. Now apply the one real migration (adds media_type/duration_seconds):
docker exec database_manager_api alembic -c /code/alembic.ini upgrade head

# 4. Verify:
docker exec postgres_db psql -U dad -d postgres -c '\d photos'
```

(User/db confirmed by inspecting the running containers directly —
the app actually connects as `dad` to a database literally named
`postgres`, via `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` from
`.env`, not the `DB_USER`/`DB_NAME` vars docker-compose.yaml also sets
on the `api` service — `get_db_url()` in `app/database/database.py`
only reads the `POSTGRES_*` names.)

After this, `alembic_version` genuinely reflects reality and future
migrations can just be `alembic upgrade head` as normal.

## Accounts, roles & approval

Each role includes the abilities of the ones below it:

| Role | Can do |
|---|---|
| `admin` | Everything a parent can, plus approve or reject account requests, set roles, reset passwords |
| `parent` | Manage pocket money and deductions, remove anyone's photos and messages |
| `adult` | Fordstagram and messaging |
| `child` | Fordstagram, messaging, and their own pocket-money account |

"Add Profile" on the Fordstagram login screen is open to anyone, but it
only creates a **pending** account: it can't log in and isn't listed
until the admin approves it (👥 in the nav bar). The birth year entered
on the form only picks `child` or `adult` (18 and over) and is not
stored. `parent` is handed out by the admin afterwards; `admin` can only
be set from the server.

Deploying this for the first time needs the `status` column:

```bash
docker exec database_manager_api alembic -c /code/alembic.ini upgrade head
```

### Login limits and sessions

- Five wrong passwords for an account from one device lock that device
  out of the account for 15 minutes; 25 from anywhere lock the account
  for everyone for 15 minutes. An admin password reset lifts the lock.
- At most five account requests an hour from one device.
- New and reset passwords need at least 8 characters. Existing shorter
  passwords keep working.
- A login lasts as long as the app is opened at least every 30 days;
  after that the token can no longer be refreshed.
- Resetting a password (in the app or with `app.cli`) logs that account
  out everywhere.

The lock-out counters are kept in the API process (`app/core/rate_limit.py`),
so they reset when the `api` container restarts, and they rely on the
API running as a single process.

### Recovery from the server

If the admin is locked out, or on a fresh install with no admin yet,
`app/cli.py` works directly on the database:

```bash
docker exec -it database_manager_api python -m app.cli list
docker exec -it database_manager_api python -m app.cli reset-password dad
docker exec -it database_manager_api python -m app.cli set-role dad admin
docker exec -it database_manager_api python -m app.cli activate grandad
docker exec -it database_manager_api python -m app.cli create-user dad "Dad" admin
```

`reset-password` and `create-user` prompt for the password.

## Ford House game: family birthdays

`GET /v1/game/family` gives the Ford House game (`littleGex/ford_games`)
the four players' birthdays and nothing else:

```json
{ "players": [ { "key": "girl", "birthday": "YYYY-MM-DD" }, ... ] }
```

It accepts any family login, or `GAME_TOKEN` from `.env` as the bearer
token. The game token is rejected on every other route. The game is a
public static site, so the token must never be committed to it: enter it
in the game once per device and keep it in that browser.

Who is which player, and the parents' birthdays, are entered on the
server so they never pass through git:

```bash
docker exec -it database_manager_api python -m app.cli set-game-child Penelope girl
docker exec -it database_manager_api python -m app.cli set-game-parent dad dad YYYY-MM-DD
```

The game's origin has to be in `ALLOWED_ORIGINS`.

## Ford House game: settings

`GET` and `PUT /v1/game/settings` hold the game's settings in one
document shared by every family device, so a change made on one shows
up on the others. Same access as `/v1/game/family`: any family login,
or the game token.

```json
{ "version": 3, "updated_at": "...",
  "settings": {
    "players": { "girl": { "name": "Pia", "look": { "hair": "long", ... } }, ... },
    "off": ["dragon"],
    "swapRooms": true,
    "swapDesks": false,
    "assign": { "dragon": ["boy", "girl"] } } }
```

- `players`: `dad`, `mum`, `girl` and `boy`, each with an optional
  `name` (at most 16 letters, numbers, spaces and `- ' .`; `null` means
  the usual nickname), `pronoun` (`she`, `he` or `they`; `null` means the
  usual one: he for Dad and Dude, she for Mum and P), `look` (colours as
  `#rrggbb`, the game's hair styles, `glasses` and `beard` as
  true/false) and `away`.
- `away`: true when a grown-up is left out, for a family with one
  grown-up. Only Dad or Mum can be away, never both.
- `off`: the job groups switched off, each at most once.
- `swapRooms`: true when P and Dude have swapped bedrooms. Optional;
  older game versions leave it out.
- `swapDesks`: true when Mum and Dad have swapped desks at home (Mum at
  the desk in the dressing room, Dad in the attic office). Optional.
- `assign`: who does the household chores when it isn't the usual
  people: `cook`, `bike`, `solar`, `sofabed` and `dragon`, each to one or
  more of the four players, nobody twice. Optional; a chore left out
  goes to the usual people.

The checks mirror the game's own, so anything else gets `422` and
nothing is saved. A field may be left out but not set to `null`,
except a player and a player's `name`, `pronoun` and `look`. Colours
are stored in lowercase and names trimmed.

A save sends the `version` it started from as `base_version`:

```json
{ "base_version": 3, "settings": { ... } }
```

If another device saved in between, the answer is `409` with the
current settings, so the game can re-apply its change and try again.
Before the first save `GET` answers `version` 0 and `settings` `null`.
Bodies over 8 KB get `413`, and more than 30 saves a minute from one
device get `429`. Like the login limits, that count is kept in the API
process and resets when it restarts.
