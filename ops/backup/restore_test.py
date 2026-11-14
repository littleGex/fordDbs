"""
Monthly restore test (#31): restore the newest backups from the NAS into
throwaway containers (no ports, always removed) and check them.
Run by fordDbs-restore-test.timer:  python3 -m ops.backup.restore_test
"""
import argparse
import gzip
import hashlib
import json
import re
import secrets
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ops.backup.common import (AlreadyRunning, CommandError, Runner,
                               exclusive_lock, load_config, notify)
from ops.backup.steps import StepResult, count_objects

DEFAULT_CONFIG = Path.home() / ".config" / "fordDbs-backup" / "env"
PG_IMAGE = "postgres:15-alpine"
MINIO_CONTAINER = "restoretest-minio"
MINIO_VOLUME = "restoretest-minio"
WAIT_TRIES = 60
KEY_TABLES = {"forddbs": ("users", "photos", "etf_transactions"),
              "chore_tracker": ('"user"', "chore", "completion")}
# live container, and the database inside it the dump was taken from
LIVE = {"forddbs": ("postgres_db", "postgres"),
        "chore_tracker": ("chore-tracker-db-1", "chore_tracker")}
OWNER = re.compile(rb"OWNER TO ([A-Za-z_][A-Za-z0-9_]*);")
# Dumps come from pg_dump 18; the servers run Postgres 15, whose psql
# rejects \restrict and whose server rejects transaction_timeout.
PG15_INCOMPATIBLE = re.compile(
    rb"^(\\restrict |\\unrestrict |SET transaction_timeout = )")


def dump_owners(sql: bytes) -> set:
    return {m.decode() for m in OWNER.findall(sql)}


def prepare_dump(sql: bytes) -> bytes:
    return b"".join(line for line in sql.splitlines(keepends=True)
                    if not PG15_INCOMPATIBLE.match(line))


def counts_ok(restored: dict, live: dict) -> list:
    problems = []
    for table, count in restored.items():
        if count == 0 and live.get(table, 0) > 0:
            problems.append(f"{table} is empty")
        elif count > live.get(table, 0):
            problems.append(f"{table} has more rows than live")
    return problems


def _newest(folder: Path, pattern: str):
    files = sorted(folder.glob(pattern)) if folder.is_dir() else []
    files = [f for f in files if f.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _wait(runner, cmd, sleep, env=None) -> bool:
    for _ in range(WAIT_TRIES):
        if runner.run(cmd, env=env, check=False).returncode == 0:
            return True
        sleep(1)
    return False


def _count(runner, cmd) -> int:
    return int(runner.run(cmd).stdout.decode().strip() or 0)


def _restore_one(cfg, runner, db, sleep) -> list:
    folder = cfg.backup_root / "postgres" / db
    dump = _newest(folder / "last", "*.sql.gz") or \
        _newest(folder / "daily", "*.sql.gz")
    if dump is None:
        return [f"{db}: no dump on the NAS"]
    sql = gzip.decompress(dump.read_bytes())
    container = f"restoretest-pg-{db}"
    live_container, target = LIVE[db]
    try:
        runner.run(["docker", "run", "-d", "--name", container, "-e",
                    f"POSTGRES_PASSWORD={secrets.token_hex(16)}", PG_IMAGE])
        if not _wait(runner, ["docker", "exec", container, "pg_isready",
                              "-h", "127.0.0.1", "-U", "postgres"], sleep):
            return [f"{db}: server not ready"]
        psql = ["docker", "exec", container, "psql", "-U", "postgres"]
        for role in sorted(dump_owners(sql) - {"postgres"}):
            runner.run(psql + ["-c", f'CREATE ROLE "{role}"'])
        if target != "postgres":
            runner.run(psql + ["-c", f'CREATE DATABASE "{target}"'])
        runner.run(["docker", "exec", "-i", container, "psql", "-U",
                    "postgres", "-d", target, "-v", "ON_ERROR_STOP=1", "-q"],
                   stdin=prepare_dump(sql))
        restored, live = {}, {}
        for table in KEY_TABLES[db]:
            query = f"select count(*) from {table}"
            restored[table] = _count(runner, [
                "docker", "exec", container, "psql", "-tA", "-U", "postgres",
                "-d", target, "-c", query])
            live[table] = _count(runner, [
                "docker", "exec", live_container, "sh", "-c",
                f'psql -tA -U "$POSTGRES_USER" -d {target} -c \'{query}\''])
        return [f"{db}: {p}" for p in counts_ok(restored, live)]
    except CommandError as exc:
        return [f"{db}: {exc.cmd[3] if len(exc.cmd) > 3 else exc.cmd[0]} "
                f"exited {exc.returncode}"]
    finally:
        runner.run(["docker", "rm", "-f", container], check=False)


def restore_databases(cfg, runner, sleep=time.sleep) -> StepResult:
    problems = []
    for db in cfg.databases:
        problems += _restore_one(cfg, runner, db, sleep)
    return StepResult("databases", not problems, "; ".join(problems))


def _minio_root(cfg) -> tuple:
    values = {}
    env_file = cfg.docker_root / "fordDbs" / ".env"
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values["MINIO_ROOT_USER"], values["MINIO_ROOT_PASSWORD"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_restored(cfg, runner, archive_objects, mc) -> StepResult:
    exec_mc = ["docker", "exec", "-e", "MC_HOST_r", MINIO_CONTAINER]
    out = runner.run(exec_mc + ["mc", "ls", "--recursive", "--json",
                                f"r/{cfg.bucket}"], env=mc).stdout
    keys = [json.loads(line)["key"] for line in out.decode().splitlines()
            if line.strip() and json.loads(line).get("type") != "folder"]
    if len(keys) != archive_objects:
        return StepResult("photos", False,
                          f"restored {len(keys)} photos, archive holds "
                          f"{archive_objects}")
    files = cfg.backup_root / "photos" / "files"
    bad = []
    for key in keys:
        restored = runner.run(exec_mc + [
            "sh", "-c", f'mc cat "r/{cfg.bucket}/$0" | sha256sum', key],
            env=mc).stdout.decode().split()[0]
        local = files / key
        if not local.is_file() or _sha256(local) != restored:
            bad.append(key)
    if bad:
        return StepResult("photos", False,
                          f"{len(bad)} of {len(keys)} checksums differ: "
                          f"{', '.join(sorted(bad)[:5])}")
    return StepResult("photos", True, data={"objects": len(keys)})


def restore_photos(cfg, runner, sleep=time.sleep) -> StepResult:
    volume_dir = cfg.backup_root / "photos" / "volume"
    archive = _newest(volume_dir, "*.tar.gz")
    if archive is None:
        return StepResult("photos", False, "no volume copy on the NAS")
    try:
        with tarfile.open(archive, "r:gz") as tar:
            archive_objects = count_objects(tar, cfg.bucket)
        user, password = _minio_root(cfg)
    except (OSError, tarfile.TarError, KeyError) as exc:
        return StepResult("photos", False,
                          f"cannot read backup ({type(exc).__name__})")
    root_env = {"MINIO_ROOT_USER": user, "MINIO_ROOT_PASSWORD": password}
    mc = {"MC_HOST_r": f"http://{quote(user, safe='')}:"
                       f"{quote(password, safe='')}@localhost:9000"}
    try:
        image = runner.run(["docker", "inspect", "family_photos_storage",
                            "--format", "{{.Config.Image}}"]
                           ).stdout.decode().strip()
        runner.run(["docker", "volume", "create", MINIO_VOLUME])
        runner.run(["docker", "run", "--rm", "-v", f"{MINIO_VOLUME}:/data",
                    "-v", f"{volume_dir}:/backup:ro", "--entrypoint", "tar",
                    cfg.tar_image, "-C", "/data", "-xzf",
                    f"/backup/{archive.name}"])
        runner.run(["docker", "run", "-d", "--name", MINIO_CONTAINER,
                    "-e", "MINIO_ROOT_USER", "-e", "MINIO_ROOT_PASSWORD",
                    "-v", f"{MINIO_VOLUME}:/data", image, "server", "/data"],
                   env=root_env)
        if not _wait(runner, ["docker", "exec", "-e", "MC_HOST_r",
                              MINIO_CONTAINER, "mc", "ls",
                              f"r/{cfg.bucket}"], sleep, env=mc):
            return StepResult("photos", False, "MinIO did not start")
        return _check_restored(cfg, runner, archive_objects, mc)
    except CommandError as exc:
        return StepResult("photos", False,
                          f"{' '.join(exc.cmd[:2])} exited {exc.returncode}")
    finally:
        runner.run(["docker", "rm", "-f", MINIO_CONTAINER], check=False)
        runner.run(["docker", "volume", "rm", MINIO_VOLUME], check=False)


def check_secrets(cfg) -> StepResult:
    newest = _newest(cfg.backup_root / "secrets", "*.tar.age")
    if newest is None:
        return StepResult("secrets", False, "no secrets file on the NAS")
    with open(newest, "rb") as handle:
        header = handle.read(32)
    if not header.startswith(b"age-encryption.org/v1"):
        return StepResult("secrets", False, f"{newest.name} is not age")
    return StepResult("secrets", True, data={"secrets": newest.name})


def run_restore_test(cfg, runner, notifier=notify,
                     sleep=time.sleep) -> int:
    results = []
    for name, check in (("databases", lambda: restore_databases(
                            cfg, runner, sleep=sleep)),
                        ("photos", lambda: restore_photos(
                            cfg, runner, sleep=sleep)),
                        ("secrets", lambda: check_secrets(cfg))):
        try:
            result = check()
        except Exception as exc:
            result = StepResult(name, False,
                                f"crashed: {type(exc).__name__}")
        print(f"{result.name}: {'ok' if result.ok else 'FAILED'} "
              f"{result.detail}".rstrip(), flush=True)
        results.append(result)
    failed = [r.name for r in results if not r.ok]
    if failed:
        message, priority = f"restore test failed: {', '.join(failed)}", \
            "high"
    else:
        photos = results[1].data.get("objects", 0)
        message, priority = (f"restore test passed: {len(cfg.databases)} "
                             f"databases, {photos} photos"), "default"
    if not notifier(cfg.ntfy_url, "fordDbs restore test", message,
                    priority):
        print("ntfy: not delivered", flush=True)
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    try:
        with exclusive_lock(cfg.lock_path):
            print(f"restore test started {datetime.now().astimezone():%c}",
                  flush=True)
            return run_restore_test(cfg, Runner())
    except AlreadyRunning:
        print("another backup or restore test is running", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
