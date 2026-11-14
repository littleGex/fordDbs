"""
Shared helpers for the NAS backups (#31): config, the command runner,
safe writes, the run lock, ntfy, the NAS mount check and retention.

Standard library only: this runs with the Pi's own python3.
"""
import fcntl
import os
import re
import subprocess
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import IO, Callable, Optional

REQUIRED_KEYS = ("BACKUP_ROOT", "NTFY_URL", "AGE_RECIPIENT",
                 "BACKUP_READER_KEY", "BACKUP_READER_SECRET")
VOLUME_NAME = re.compile(r"^\d{4}-\d{2}\.tar\.gz$")
SECRETS_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.tar\.age$")
CIFS_TYPES = {"cifs", "smb3"}


class ConfigError(Exception):
    pass


class AlreadyRunning(Exception):
    pass


class CommandError(Exception):
    def __init__(self, cmd, returncode, stderr=b""):
        self.cmd, self.returncode, self.stderr = list(cmd), returncode, stderr
        super().__init__(f"{cmd[0]} exited {returncode}")


@dataclass(frozen=True)
class Config:
    backup_root: Path
    ntfy_url: str
    age_recipient: str
    minio_reader_key: str
    minio_reader_secret: str
    minio_url: str = "http://localhost:9000"
    postgres_source: Path = Path("/home/dad/docker/postgres-backups/backups")
    docker_root: Path = Path("/home/dad/docker")
    databases: tuple = ("forddbs", "chore_tracker")
    bucket: str = "family-photos"
    minio_volume: str = "forddbs_minio_data"
    tar_image: str = "forddbs-api"
    lock_path: Path = Path.home() / ".cache" / "fordDbs-backup.lock"


OPTIONAL = {"MINIO_URL": ("minio_url", str),
            "POSTGRES_SOURCE": ("postgres_source", Path),
            "DOCKER_ROOT": ("docker_root", Path),
            "LOCK_PATH": ("lock_path", Path)}


def load_config(path: Path) -> Config:
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    missing = [k for k in REQUIRED_KEYS if not values.get(k)]
    if missing:
        raise ConfigError(f"missing in {path}: {', '.join(missing)}")
    extra = {field: kind(values[key]) for key, (field, kind)
             in OPTIONAL.items() if values.get(key)}
    return Config(backup_root=Path(values["BACKUP_ROOT"]),
                  ntfy_url=values["NTFY_URL"],
                  age_recipient=values["AGE_RECIPIENT"],
                  minio_reader_key=values["BACKUP_READER_KEY"],
                  minio_reader_secret=values["BACKUP_READER_SECRET"],
                  **extra)


class Runner:
    """Runs external commands. Never logs the environment it passes."""

    def run(self, cmd, *, stdin: Optional[bytes] = None,
            stdout: Optional[IO] = None, env: Optional[dict] = None,
            check: bool = True) -> subprocess.CompletedProcess:
        full_env = {**os.environ, **env} if env else None
        result = subprocess.run(
            list(cmd), input=stdin,
            stdout=stdout if stdout is not None else subprocess.PIPE,
            stderr=subprocess.PIPE, env=full_env)
        if check and result.returncode:
            raise CommandError(cmd, result.returncode, result.stderr)
        return result


def atomic_write(dest: Path, write: Callable[[Path], None]) -> None:
    """write() fills a hidden .part file next to dest; it becomes dest
    only once complete, and is removed if anything fails."""
    dest = Path(dest)
    part = dest.with_name(f".{dest.name}.part")
    try:
        write(part)
        os.replace(part, dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


@contextmanager
def exclusive_lock(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AlreadyRunning(str(path)) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _post(url: str, body: bytes, headers: dict) -> None:
    request = urllib.request.Request(url, data=body, headers=headers,
                                     method="POST")
    with urllib.request.urlopen(request, timeout=10):
        pass


def notify(url: str, title: str, message: str, priority: str = "default",
           post=None) -> bool:
    """Send an ntfy message. Never raises: a lost alert must not change
    the backup's own result."""
    try:
        (post or _post)(url, message.encode(),
                        {"Title": title, "Priority": priority})
        return True
    except Exception:
        return False


def is_cifs_mount(path: Path, runner) -> bool:
    """True only if path is on the NAS share. Listing it first triggers
    the automount; a plain folder on the Pi's own disk never counts."""
    try:
        os.listdir(path)
    except OSError:
        return False
    result = runner.run(["findmnt", "-n", "-o", "FSTYPE", "-T", str(path)],
                        check=False)
    return result.returncode == 0 and \
        (result.stdout or b"").decode().strip() in CIFS_TYPES


def volumes_to_delete(names, keep: int = 6):
    dated = sorted(n for n in names if VOLUME_NAME.match(n))
    return dated[:-keep] if len(dated) > keep else []


def _month_start(day: date, back: int) -> date:
    month = day.year * 12 + day.month - 1 - back
    return date(month // 12, month % 12 + 1, 1)


def secrets_to_delete(names, today: date, days: int = 30, months: int = 6):
    """Keep the last `days` days plus the newest file of each of the
    previous `months` calendar months; never the newest file."""
    dated = sorted(n for n in names if SECRETS_NAME.match(n))
    if not dated:
        return []
    recent_from = (today - timedelta(days=days - 1)).isoformat()
    oldest_month = _month_start(today, months).isoformat()[:7]
    this_month = today.isoformat()[:7]
    newest_per_month = {}
    for name in dated:
        if oldest_month <= name[:7] < this_month:
            newest_per_month[name[:7]] = name
    keep = {n for n in dated if n[:10] >= recent_from}
    keep |= set(newest_per_month.values()) | {dated[-1]}
    return [n for n in dated if n not in keep]


def human_size(n: int) -> str:
    for unit, size in (("GB", 10 ** 9), ("MB", 10 ** 6), ("KB", 10 ** 3)):
        if n >= size:
            if unit == "GB":
                return f"{n / size:.1f} GB"
            return f"{round(n / size)} {unit}"
    return f"{n} B"
