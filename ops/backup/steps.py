"""
The steps of the nightly NAS backup (#31). Each returns a StepResult and
never raises for an expected failure; run_backup() wraps the unexpected.
"""
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlsplit

from ops.backup.common import CommandError, Config, is_cifs_mount

STALE_AFTER = timedelta(hours=36)
MC_ALIAS = "backup"


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""
    data: dict = field(default_factory=dict)


def mc_env(cfg: Config) -> dict:
    """The read-only MinIO login, for mc only and never on a command
    line or on disk."""
    url = urlsplit(cfg.minio_url)
    user = quote(cfg.minio_reader_key, safe="")
    secret = quote(cfg.minio_reader_secret, safe="")
    return {f"MC_HOST_{MC_ALIAS}":
            f"{url.scheme}://{user}:{secret}@{url.netloc}"}


def bucket_path(cfg: Config) -> str:
    return f"{MC_ALIAS}/{cfg.bucket}"


def check_target(cfg: Config, runner) -> StepResult:
    share = cfg.backup_root.parent
    if not is_cifs_mount(share, runner):
        return StepResult("checks", False, f"{share} is not mounted")
    try:
        out = runner.run(["mc", "du", "--json", bucket_path(cfg)],
                         env=mc_env(cfg)).stdout
        bucket_bytes = int(json.loads(out.decode().splitlines()[-1])["size"])
    except (CommandError, ValueError, KeyError, IndexError) as exc:
        return StepResult("checks", False,
                          f"MinIO not answering ({type(exc).__name__})")
    cfg.backup_root.mkdir(exist_ok=True)
    free = shutil.disk_usage(cfg.backup_root).free
    if free < 2 * bucket_bytes:
        return StepResult("checks", False,
                          f"not enough space on the NAS ({free} bytes free)",
                          {"bucket_bytes": bucket_bytes})
    return StepResult("checks", True, data={"bucket_bytes": bucket_bytes})


def _newest(folder: Path) -> Optional[Path]:
    dumps = [p for p in folder.glob("*.sql.gz") if p.is_file()] \
        if folder.is_dir() else []
    return max(dumps, key=lambda p: p.stat().st_mtime) if dumps else None


def copy_databases(cfg: Config, runner, now: datetime) -> StepResult:
    problems, newest_names = [], {}
    for db in cfg.databases:
        source = cfg.postgres_source / db
        if _newest(source / "daily") is None:
            problems.append(f"{db}: no dumps on the Pi, not copied")
            continue
        newest = _newest(source / "last") or _newest(source / "daily")
        newest_names[db] = newest.name
        made = datetime.fromtimestamp(newest.stat().st_mtime, now.tzinfo)
        if now - made > STALE_AFTER:
            problems.append(f"{db}: newest dump older than 36 h")
        target = cfg.backup_root / "postgres" / db
        target.mkdir(parents=True, exist_ok=True)
        try:
            runner.run(["rsync", "-a", "--delete", f"{source}/",
                        f"{target}/"])
        except CommandError as exc:
            problems.append(f"{db}: rsync exited {exc.returncode}")
    return StepResult("databases", not problems, "; ".join(problems),
                      {"newest": newest_names})
