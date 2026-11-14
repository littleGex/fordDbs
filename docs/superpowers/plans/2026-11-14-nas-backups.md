# Scheduled Backups to the NAS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A nightly systemd job on the Pi that copies the databases, the photos and the encrypted `.env` secrets to the NAS share, plus a monthly restore test, both reporting to ntfy (#31).

**Architecture:** Python standard-library scripts in `ops/backup/`, run from the repo checkout on the Pi (`python3 -m ops.backup.backup`). Every external command (`rsync`, `mc`, `docker`, `age`, `findmnt`, `tar`) goes through one `Runner`, which tests replace with a recording fake. Pure logic (retention, guards, verification, messages) is unit-tested in CI; the real commands are exercised on the Pi during rollout.

**Tech Stack:** Python 3.11+ stdlib (`subprocess`, `tarfile`, `urllib.request`, `fcntl`, `hashlib`, `json`), systemd timers, rsync, mc (MinIO client), docker, age.

**Spec:** `docs/superpowers/specs/2026-11-14-nas-backups-design.md`

## Global Constraints

- Standard library only; must run on Python 3.11 (CI) and 3.13 (Pi).
- Backup root: `BACKUP_ROOT` from config, on the Pi `/mnt/nas/alan/fordDbs-backups`; its mount point must be CIFS (`findmnt` FSTYPE `cifs` or `smb3`), never a plain folder.
- NAS layout exactly as the spec: `postgres/<db>/{daily,weekly,monthly,last}`, `photos/files/`, `photos/volume/YYYY-MM.tar.gz`, `secrets/YYYY-MM-DD.tar.age`, `status/last-success.json`.
- Databases: `forddbs`, `chore_tracker`; source `~/docker/postgres-backups/backups/<db>/`; stale if the newest dump is older than 36 h.
- Retention: `photos/volume` newest 6; `secrets` last 30 days plus the newest of each of the last 6 months; never delete the newest file; never touch files whose names don't match the pattern.
- Photos: `mc mirror` without `--remove`/`--overwrite`, as read-only MinIO user `backup-reader` via the `MC_HOST_backup` env var (never written to disk by the job). Bucket `family-photos`, volume `forddbs_minio_data`, tar image `forddbs-api`.
- Secrets: `~/docker/*/.env`, skipping folders whose name contains `.bak`, tar → `age -r <AGE_RECIPIENT>`.
- Every output file: written as `.<name>.part` in the target folder, renamed when complete, removed on failure.
- ntfy: failure title `fordDbs backup failed`, body `<steps> (see journalctl -u fordDbs-backup)`, priority `high`; Sunday summary `fordDbs backup OK: 2 databases, <n> photos (<size>), last volume <YYYY-MM>`; restore `restore test passed: 2 databases, <n> photos` / `restore test failed: <parts>`. Counts, sizes and step names only.
- Restore test: containers named `restoretest-*`, no `-p`, removed in `finally`.
- Timers: backup `*-*-* 03:30:00`, restore `Sun *-*-01..07 04:30:00`, both `Persistent=true`, `User=dad`, `WorkingDirectory=/home/dad/docker/fordDbs`. Pi timezone is Europe/Berlin.
- Nothing in the repo contains the ntfy topic, keys, NAS model or address.

## Review Focus

1. NAS share not mounted (automount timing out, or the folder exists empty on the Pi's disk): no file is written to the Pi's own disk, and the run fails loudly.
2. `postgres-backup-local` stopped weeks ago: the stale check fails the run, and `rsync --delete` never runs against an empty `daily/` source.
3. A photo object key with sub-folders (`profiles/3_ab12cd.jpg`, `avatars/…`): mirrored and verified at the same relative path.
4. ntfy unreachable: the backup result still stands (exit code, journal), and the notify error doesn't mask it.
5. Restore test fails half-way (dump with an error, MinIO won't start): the `restoretest-*` containers and volume are still removed.

Each has a test in the owning task below.

---

### Task 1: Shared helpers (`ops/backup/common.py`)

**Files:**
- Create: `ops/__init__.py`, `ops/backup/__init__.py` (empty), `ops/backup/common.py`
- Create: `tests/backup_fakes.py` (FakeRunner, test-only)
- Test: `tests/test_backup_common.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Config`: `backup_root: Path`, `ntfy_url: str`, `age_recipient: str`, `minio_url: str` (default `http://localhost:9000`), `minio_reader_key: str`, `minio_reader_secret: str`, `postgres_source: Path` (default `/home/dad/docker/postgres-backups/backups`), `docker_root: Path` (default `/home/dad/docker`), `databases: tuple = ("forddbs", "chore_tracker")`, `bucket: str = "family-photos"`, `minio_volume: str = "forddbs_minio_data"`, `tar_image: str = "forddbs-api"`, `lock_path: Path` (default `~/.cache/fordDbs-backup.lock`).
  - `load_config(path: Path) -> Config` — `KEY=VALUE` lines, `#` comments, required: `BACKUP_ROOT NTFY_URL AGE_RECIPIENT BACKUP_READER_KEY BACKUP_READER_SECRET`; missing → `ConfigError` naming the keys.
  - `class Runner`: `run(cmd: list[str], *, stdin: bytes | None = None, stdout: IO | None = None, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess` (captures stdout as bytes unless `stdout` given; `env` is merged over `os.environ`). `CommandError(cmd, returncode, stderr)` on failure when `check`. Never logs `env`.
  - `atomic_write(dest: Path, write: Callable[[Path], None]) -> None`.
  - `exclusive_lock(path: Path)` — context manager using `fcntl.flock(LOCK_EX | LOCK_NB)`; raises `AlreadyRunning`.
  - `notify(url: str, title: str, message: str, priority: str = "default", post=None) -> bool` — POST body `message`, headers `Title`, `Priority`; `post` defaults to a `urllib.request` call with 10 s timeout; returns False (never raises) on any error.
  - `is_cifs_mount(path: Path, runner: Runner) -> bool` — `os.listdir(path)` first (triggers the automount; OSError → False), then `findmnt -n -o FSTYPE -T <path>`; True for `cifs`/`smb3`.
  - `volumes_to_delete(names: list[str], keep: int = 6) -> list[str]` — names matching `^\d{4}-\d{2}\.tar\.gz$`.
  - `secrets_to_delete(names: list[str], today: date, days: int = 30, months: int = 6) -> list[str]` — names matching `^\d{4}-\d{2}-\d{2}\.tar\.age$`.
  - `human_size(n: int) -> str` (`"452 MB"`, base 1000, no decimals below GB, one decimal at GB).
- `tests/backup_fakes.py`: `FakeRunner(responses: dict[str, object] | None)` — `.calls` list of `(cmd, kwargs)`; a response is matched by the longest key that is a prefix of `" ".join(cmd)`; value is `bytes` (stdout), an `int` (returncode, raises `CommandError` if non-zero and `check`), or a callable `(cmd, kwargs) -> bytes`; unmatched commands return `b""`. When `stdout` is passed, the fake writes the response bytes into it.

- [ ] **Step 1: Write the failing tests** (`pytestmark = pytest.mark.unit`)

```python
def test_load_config_reads_values_and_defaults(tmp_path): ...
    # file with the 5 required keys + a comment line
    assert cfg.backup_root == Path("/nas/b") and cfg.databases == ("forddbs", "chore_tracker")
    assert cfg.minio_url == "http://localhost:9000"
def test_load_config_names_missing_keys(tmp_path):
    with pytest.raises(ConfigError, match="AGE_RECIPIENT"): ...
def test_atomic_write_renames_when_complete(tmp_path):
    atomic_write(tmp_path / "a.txt", lambda p: p.write_text("x"))
    assert (tmp_path / "a.txt").read_text() == "x" and list(tmp_path.iterdir()) == [tmp_path / "a.txt"]
def test_atomic_write_leaves_nothing_on_failure(tmp_path):
    with pytest.raises(RuntimeError): atomic_write(tmp_path / "a.txt", boom)
    assert list(tmp_path.iterdir()) == []
def test_second_lock_raises_already_running(tmp_path): ...
def test_notify_sends_title_priority_and_body():
    sent = []; assert notify("https://n/t", "T", "body", "high", post=lambda *a: sent.append(a)) is True
    # sent[0] == ("https://n/t", b"body", {"Title": "T", "Priority": "high"})
def test_notify_swallows_errors():
    assert notify("https://n/t", "T", "b", post=raising) is False
def test_cifs_mount_detected(tmp_path):
    assert is_cifs_mount(tmp_path, FakeRunner({"findmnt": b"cifs\n"})) is True
def test_plain_folder_is_not_a_mount(tmp_path):
    assert is_cifs_mount(tmp_path, FakeRunner({"findmnt": b"ext4\n"})) is False
def test_missing_folder_is_not_a_mount(tmp_path):
    assert is_cifs_mount(tmp_path / "nope", FakeRunner()) is False
def test_volumes_keep_newest_six():
    names = [f"2026-{m:02d}.tar.gz" for m in range(1, 10)] + ["notes.txt"]
    assert volumes_to_delete(names) == ["2026-01.tar.gz", "2026-02.tar.gz", "2026-03.tar.gz"]
def test_volumes_nothing_deleted_at_or_below_keep():
    assert volumes_to_delete(["2026-01.tar.gz"]) == []
def test_secrets_keep_30_days_and_newest_per_month():
    today = date(2026, 11, 14)
    names = daily names 2026-04-01 .. 2026-11-14 + "x.age"
    deleted = secrets_to_delete(names, today)
    kept = set(names) - set(deleted) - {"x.age"}
    assert all(n >= "2026-10-15" or n in {"2026-05-31","2026-06-30","2026-07-31","2026-08-31","2026-09-30","2026-10-31"} for n in kept)
    assert "2026-04-30.tar.age" in deleted and "x.age" not in deleted
def test_secrets_never_deletes_newest():
    assert secrets_to_delete(["2025-01-01.tar.age"], date(2026, 11, 14)) == []
def test_human_size():
    assert human_size(452_000_000) == "452 MB" and human_size(2_700_000_000) == "2.7 GB"
```

(“Newest of each of the last 6 months” = the 6 calendar months before the current one; the current month is covered by the 30 days.)

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_backup_common.py -q` — Expected: FAIL, `ModuleNotFoundError: No module named 'ops'`.
- [ ] **Step 3: Implement** `ops/backup/common.py` and `tests/backup_fakes.py` per the Interfaces block.
- [ ] **Step 4: Run** the tests and `.venv/bin/flake8 ops tests/test_backup_common.py tests/backup_fakes.py` — Expected: all pass, flake8 clean.
- [ ] **Step 5: Commit** `feat(backup): shared helpers for NAS backups`

### Task 2: Target check and database copy (`ops/backup/steps.py`)

**Files:**
- Create: `ops/backup/steps.py`
- Test: `tests/test_backup_steps.py`

**Interfaces:**
- Consumes: Task 1 `Config`, `Runner`, `is_cifs_mount`.
- Produces:
  - `@dataclass StepResult`: `name: str`, `ok: bool`, `detail: str = ""`, `data: dict = field(default_factory=dict)`.
  - `check_target(cfg, runner) -> StepResult` (name `"checks"`): fails if `cfg.backup_root.parent` (the share folder) is not a CIFS mount; otherwise creates `backup_root` if missing; fails if `shutil.disk_usage(backup_root).free < 2 * bucket_bytes` where `bucket_bytes` comes from `mc du --json backup/<bucket>` (`size` field); fails if that `mc` call fails (MinIO unreachable). `data={"bucket_bytes": n}`.
  - `copy_databases(cfg, runner, now: datetime) -> StepResult` (name `"databases"`): per db — newest `*.sql.gz` by mtime in `<src>/<db>/last`, else `daily`; none in `daily/` → fail that db, skip rsync; newest older than 36 h → fail that db but still rsync; else `rsync -a --delete <src>/<db>/ <root>/postgres/<db>/`. `data={"newest": {db: filename}}`. Detail names failed dbs.
  - `mc_env(cfg) -> dict` — `{"MC_HOST_backup": "http://<key>:<secret>@<host:port>"}` built from `cfg.minio_url`.
- Every `mc` call passes `env=mc_env(cfg)`.

- [ ] **Step 1: Write the failing tests** (`unit`)

```python
def test_check_target_refuses_plain_folder(tmp_path):
    r = check_target(cfg(tmp_path), FakeRunner({"findmnt": b"ext4"}))
    assert not r.ok and "not mounted" in r.detail and not (tmp_path / "share" / "fordDbs-backups").exists()
def test_check_target_ok_on_cifs_with_space(tmp_path):
    r = check_target(cfg(tmp_path), FakeRunner({"findmnt": b"cifs", "mc du": b'{"size": 1000}'}))
    assert r.ok and r.data["bucket_bytes"] == 1000
def test_check_target_fails_when_minio_down(tmp_path):
    r = check_target(cfg(tmp_path), FakeRunner({"findmnt": b"cifs", "mc du": 1}))
    assert not r.ok and "MinIO" in r.detail
def test_mc_credentials_only_in_env(tmp_path):
    fake = FakeRunner({"findmnt": b"cifs", "mc du": b'{"size": 1}'}); check_target(cfg(tmp_path), fake)
    cmd, kw = fake.calls[-1]
    assert "secret" not in " ".join(cmd) and kw["env"]["MC_HOST_backup"] == "http://reader:secret@localhost:9000"
def test_databases_copied_when_fresh(tmp_path): # dumps 1 h old in last/ and daily/
    assert r.ok and rsync calls == [["rsync", "-a", "--delete", f"{src}/forddbs/", f"{root}/postgres/forddbs/"], ...chore_tracker]
def test_empty_daily_skips_rsync_and_fails(tmp_path):
    assert not r.ok and "forddbs" in r.detail and no rsync call for forddbs; chore_tracker still copied
def test_stale_dump_fails_but_still_copies(tmp_path): # newest 40 h old
    assert not r.ok and "older than 36 h" in r.detail and rsync for that db was called
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_backup_steps.py -q` — Expected: FAIL, no module `ops.backup.steps`.
- [ ] **Step 3: Implement** the three functions in `ops/backup/steps.py`.
- [ ] **Step 4: Run** tests + flake8 — Expected: pass, clean.
- [ ] **Step 5: Commit** `feat(backup): NAS mount check and database copy`

### Task 3: Photos, volume copy, secrets (`ops/backup/steps.py`)

**Files:**
- Modify: `ops/backup/steps.py`
- Test: `tests/test_backup_steps.py` (append)

**Interfaces:**
- Consumes: Task 1 `atomic_write`, `volumes_to_delete`, `secrets_to_delete`; Task 2 `StepResult`, `mc_env`.
- Produces:
  - `list_bucket(cfg, runner) -> dict[str, int]` — `mc ls --recursive --json backup/<bucket>`; one JSON object per line; `key` → `size`, skipping entries with `type == "folder"`.
  - `mirror_photos(cfg, runner) -> StepResult` (name `"photos"`): `mc mirror --json backup/<bucket> <root>/photos/files` (no `--remove`, no `--overwrite`; a non-zero exit is a failure); then `list_bucket` and compare each key with `<root>/photos/files/<key>`: missing or different size → listed in detail (first 5 keys + count). `data={"objects": n, "bytes": total}`.
  - `volume_copy(cfg, runner, today: date, objects: int) -> StepResult` (name `"volume"`): skip (ok, detail `"exists"`) if `photos/volume/<YYYY-MM>.tar.gz` exists; else `atomic_write` it via `runner.run(["docker", "run", "--rm", "--entrypoint", "tar", "-v", f"{cfg.minio_volume}:/data:ro", cfg.tar_image, "-C", "/data", "-czf", "-", cfg.bucket], stdout=f)`, verifying inside the write callback with `tarfile` that the count of members ending in `/xl.meta` equals `objects` (mismatch raises → no file). `data={"volume": name}`.
  - `pack_secrets(cfg, runner, today: date) -> StepResult` (name `"secrets"`): tar (in memory, `tarfile` `w:gz`) every `<docker_root>/*/.env` whose folder name has no `.bak`, arcname `<folder>/.env`; `atomic_write` `secrets/<YYYY-MM-DD>.tar.age` via `runner.run(["age", "-r", cfg.age_recipient, "-o", str(part)], stdin=tar_bytes)`. No `.env` found → fail. `data={"secrets": name, "files": n}`.
  - `apply_retention(cfg, today: date) -> StepResult` (name `"retention"`): delete `volumes_to_delete` in `photos/volume` and `secrets_to_delete` in `secrets`; `data={"deleted": n}`.

- [ ] **Step 1: Write the failing tests** (`unit`)

```python
def test_mirror_verifies_nested_keys(tmp_path):  # Review Focus 3
    bucket listing: "a.jpg" 3 bytes, "profiles/3_ab.jpg" 2 bytes; files written at those relative paths
    assert r.ok and r.data == {"objects": 2, "bytes": 5}
def test_mirror_reports_missing_and_wrong_size(tmp_path):
    assert not r.ok and "profiles/3_ab.jpg" in r.detail and "2 of 2" in r.detail
def test_mirror_never_removes_or_overwrites(tmp_path):
    cmd = mirror call; assert "--remove" not in cmd and "--overwrite" not in cmd
def test_volume_copy_skipped_when_month_exists(tmp_path):
    assert r.ok and r.detail == "exists" and no docker call
def test_volume_copy_writes_verified_archive(tmp_path):
    fake docker run returns a real tar.gz with 2 "family-photos/<k>/xl.meta" members
    assert (root/"photos/volume/2026-11.tar.gz").exists() and r.ok
def test_volume_copy_count_mismatch_leaves_no_file(tmp_path):
    objects=3 → not r.ok and photos/volume holds no file (no .part either)
def test_secrets_skip_bak_folders_and_encrypt(tmp_path):
    docker_root has fordDbs/.env, chore-tracker/.env, trading-bot.bak-1/.env
    age stdin tar lists ["chore-tracker/.env", "fordDbs/.env"]; age called with -r <recipient>; file secrets/2026-11-14.tar.age exists
def test_secrets_fail_without_env_files(tmp_path): ...
def test_retention_deletes_only_old(tmp_path):
    8 volumes + 40 daily secrets → 2 volumes deleted, newest of each kept; unrelated "README" untouched
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_backup_steps.py -q` — Expected: new tests FAIL (`ImportError` for the new names).
- [ ] **Step 3: Implement** the five functions.
- [ ] **Step 4: Run** tests + flake8 — Expected: pass, clean.
- [ ] **Step 5: Commit** `feat(backup): photo mirror, monthly volume copy and encrypted secrets`

### Task 4: The backup run (`ops/backup/backup.py`)

**Files:**
- Create: `ops/backup/backup.py`
- Test: `tests/test_backup_run.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `run_backup(cfg, runner, now: datetime, notifier=notify) -> int` — order: `check_target`; if it failed, stop there (nothing else may write) and notify; else `copy_databases`, `mirror_photos`, `volume_copy(objects=photos.data.get("objects"))` (skipped as failed if photos failed), `pack_secrets`, `apply_retention`. Each step wrapped so an unexpected exception becomes a failed `StepResult` with the exception type name. Logs one line per step to stdout (journal). All ok → write `status/last-success.json` via `atomic_write` (`finished_at` ISO, `databases`, `photos`, `volume`, `secrets`) and, if `now.weekday() == 6`, send the Sunday summary. Any failure → failure notification, priority `high`. Returns 0 / 1. A notifier returning False only logs `ntfy: not delivered`.
  - `main(argv=None) -> int` — `--config` (default `~/.config/fordDbs-backup/env`), takes `exclusive_lock(cfg.lock_path)` (already running → log, return 0), calls `run_backup(load_config(...), Runner(), datetime.now().astimezone())`. `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 1: Write the failing tests** (`unit`; steps patched with `monkeypatch` on `ops.backup.backup`)

```python
def test_all_ok_writes_status_and_no_alert_on_weekday(tmp_path):
    assert run_backup(...) == 0 and json.loads(status)["photos"] == {"objects": 2, "bytes": 5} and sent == []
def test_sunday_sends_summary(tmp_path):
    sent == [("fordDbs backup OK", "fordDbs backup OK: 2 databases, 2 photos (5 B), last volume 2026-11", "default")]
def test_failed_step_does_not_stop_later_steps(tmp_path):
    photos fails → secrets and retention still ran; exit 1; status file not written
    sent == [("fordDbs backup failed", "photos (see journalctl -u fordDbs-backup)", "high")]
def test_unmounted_target_stops_everything(tmp_path):  # Review Focus 1
    checks fails → no other step called, exit 1, alert names "checks"
def test_step_exception_becomes_failure(tmp_path):
    databases raises OSError → exit 1, alert names "databases"
def test_ntfy_down_keeps_result(tmp_path):  # Review Focus 4
    notifier returns False → run_backup returns 1 for a failure and 0 for success
def test_main_second_instance_exits_quietly(tmp_path): ...
```

(`human_size` below 1000 renders as `"<n> B"`.)

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_backup_run.py -q` — Expected: FAIL, no module `ops.backup.backup`.
- [ ] **Step 3: Implement** `run_backup` and `main`.
- [ ] **Step 4: Run** tests + flake8 — Expected: pass, clean.
- [ ] **Step 5: Commit** `feat(backup): nightly backup run with ntfy alerts`

### Task 5: Restore test (`ops/backup/restore_test.py`)

**Files:**
- Create: `ops/backup/restore_test.py`
- Test: `tests/test_backup_restore.py`

**Interfaces:**
- Consumes: Task 1 helpers; Task 2 `StepResult`.
- Produces:
  - `KEY_TABLES = {"forddbs": ("users", "photos", "etf_transactions"), "chore_tracker": ('"user"', "chore", "completion")}`.
  - `LIVE = {"forddbs": ("postgres_db", "postgres"), "chore_tracker": ("chore-tracker-db-1", "chore_tracker")}` — live container and database; live counts via `docker exec <c> sh -c 'psql -tA -U "$POSTGRES_USER" -d <db> -c "<sql>"'`.
  - `dump_owners(sql_head: bytes) -> set[str]` — role names from `OWNER TO <role>;` lines.
  - `counts_ok(restored: dict[str, int], live: dict[str, int]) -> list[str]` — problems: restored 0 while live > 0, or restored > live.
  - `restore_databases(cfg, runner, sleep=time.sleep) -> StepResult` (name `"databases"`): per db, newest dump from `<root>/postgres/<db>/last` else `daily`; `docker run -d --name restoretest-pg-<db> -e POSTGRES_PASSWORD=<secrets.token_hex(16)> postgres:15-alpine` (no `-p`); wait with `pg_isready` up to 60 × 1 s; `CREATE ROLE` each dump owner; `CREATE DATABASE <db>` unless `postgres`; restore with `psql -v ON_ERROR_STOP=1` fed the gunzipped dump on stdin; compare `KEY_TABLES` counts with live. Containers removed in `finally` (`docker rm -f`).
  - `restore_photos(cfg, runner, sleep=time.sleep) -> StepResult` (name `"photos"`): newest `photos/volume/*.tar.gz`; `docker volume create restoretest-minio`; untar into it with `docker run --rm -i -v restoretest-minio:/data <tar_image> tar -C /data -xzf -` (archive on stdin); image from `docker inspect family_photos_storage --format {{.Config.Image}}`; root user/password from `<docker_root>/fordDbs/.env` (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`), passed with `-e`; `docker run -d --name restoretest-minio -v restoretest-minio:/data <image> server /data`; wait until `docker exec restoretest-minio mc alias set r http://localhost:9000 <u> <p>` succeeds (60 × 1 s); list with `mc ls --recursive --json r/<bucket>`; for each key `docker exec restoretest-minio sh -c 'mc cat "r/<bucket>/$0" | sha256sum' <key>` vs `hashlib.sha256` of `photos/files/<key>`. Fail on count mismatch with the archive's `xl.meta` count or any checksum mismatch. `finally`: `docker rm -f restoretest-minio`, `docker volume rm restoretest-minio`. `data={"objects": n}`.
  - `check_secrets(cfg) -> StepResult` (name `"secrets"`): newest `secrets/*.tar.age` exists, non-empty, starts with `b"age-encryption.org/v1"`.
  - `run_restore_test(cfg, runner, notifier=notify, sleep=time.sleep) -> int`; `main(argv=None)` like Task 4 (same lock).

- [ ] **Step 1: Write the failing tests** (`unit`)

```python
def test_dump_owners():
    assert dump_owners(b"ALTER TABLE public.users OWNER TO dad;\nALTER SCHEMA x OWNER TO app;") == {"dad", "app"}
def test_counts_ok():
    assert counts_ok({"users": 3}, {"users": 3}) == []
    assert counts_ok({"users": 0}, {"users": 3}) and counts_ok({"users": 4}, {"users": 3})
def test_restore_db_container_has_no_ports_and_is_removed(tmp_path):
    every "docker run" cmd lacks "-p"; last calls include ["docker", "rm", "-f", "restoretest-pg-forddbs"]
def test_restore_failure_still_cleans_up(tmp_path):  # Review Focus 5
    psql restore returns 3 → not r.ok and rm -f called for the container
def test_photos_cleanup_after_minio_never_starts(tmp_path):  # Review Focus 5
    alias set always fails → not r.ok; "docker rm -f restoretest-minio" and "docker volume rm restoretest-minio" called; sleep called 60 times
def test_photos_checksum_mismatch_reported(tmp_path): ...
def test_secrets_check_needs_age_header(tmp_path): ...
def test_run_restore_test_reports_pass_and_fail(tmp_path):
    pass → ("restore test passed: 2 databases, 2 photos"); fail → ("restore test failed: photos", priority "high")
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_backup_restore.py -q` — Expected: FAIL, no module.
- [ ] **Step 3: Implement** `ops/backup/restore_test.py`.
- [ ] **Step 4: Run** tests + flake8 — Expected: pass, clean.
- [ ] **Step 5: Commit** `feat(backup): monthly restore test from the NAS`

### Task 6: Units, installer, docs

**Files:**
- Create: `ops/backup/systemd/fordDbs-backup.service`, `fordDbs-backup.timer`, `fordDbs-restore-test.service`, `fordDbs-restore-test.timer`, `ops/backup/env.example`, `ops/backup/install.sh`
- Modify: `README.md` (new section "Backups")
- Test: `tests/test_backup_units.py`

**Interfaces:**
- Services: `Type=oneshot`, `User=dad`, `WorkingDirectory=/home/dad/docker/fordDbs`, `ExecStart=/usr/bin/python3 -m ops.backup.backup` / `ops.backup.restore_test`, `TimeoutStartSec=2h`. Timers per Global Constraints, `[Install] WantedBy=timers.target`.
- `install.sh`: `set -euo pipefail`; `sudo install -m 644` the four units to `/etc/systemd/system/`; `sudo systemctl daemon-reload`; `sudo systemctl enable --now fordDbs-backup.timer fordDbs-restore-test.timer`; refuses to run if `~/.config/fordDbs-backup/env` is missing or not mode 600.
- `env.example`: every key with placeholder values and a comment; no real values.
- README: where backups live; how to restore a database (`gunzip -c … | docker exec -i postgres_db psql …`), photos (stop MinIO, untar the volume copy into the volume; or copy single files from `photos/files`), secrets (`age -d -i key.txt …`); yearly decrypt check; how to read the journal and run each job by hand.

- [ ] **Step 1: Write the failing test** (`unit`): parse each unit with `configparser` (`strict=False`) and assert the `OnCalendar`, `Persistent=true`, `User=dad`, `WorkingDirectory`, `ExecStart` values above; assert `env.example` contains every required key from `load_config` and that `install.sh` has a `set -euo pipefail` line.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_backup_units.py -q` — Expected: FAIL (files missing).
- [ ] **Step 3: Create** the files and the README section.
- [ ] **Step 4: Run** the test, `bash -n ops/backup/install.sh`, full suite `.venv/bin/python -m pytest -q`, `.venv/bin/flake8 .` — Expected: all pass, clean.
- [ ] **Step 5: Commit** `feat(backup): systemd timers, installer and restore docs`

### Task 7: Pull request

- [ ] Push `feat/nas-backups`; open a PR "feat(ops): scheduled backups to the NAS (#31)" that says rollout follows merge and needs the user's age public key and ntfy subscription. Do not merge.

## After merge: rollout (needs the user; not part of the PR)

1. User: `age-keygen` on the Mac; private key into the password manager; send the public key. Install ntfy and subscribe to a topic Claude generates (sent in chat, never committed).
2. With the user's OK: on the Pi, `mc admin user add` `backup-reader` and attach the `readonly` policy (scoped to `family-photos` with a custom policy if the built-in one is too broad).
3. `sudo apt install age`; `chmod 600 ~/docker/chore-tracker/.env`; write `~/.config/fordDbs-backup/env` (600); `git pull`; `ops/backup/install.sh`.
4. Run `python3 -m ops.backup.backup` by hand; inspect the NAS folder (counts, sizes, status file); run `python3 -m ops.backup.restore_test` once; check both ntfy messages arrive.
5. User: decrypt the newest secrets file on the Mac.
