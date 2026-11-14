"""
The steps of the nightly NAS backup (#31). Each returns a StepResult and
never raises for an expected failure; run_backup() wraps the unexpected.
"""
import io
import json
import shutil
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlsplit

from ops.backup.common import (CommandError, Config, atomic_write,
                               is_cifs_mount, secrets_to_delete,
                               volumes_to_delete)

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


def list_bucket(cfg: Config, runner) -> dict:
    """key -> size for every object in the bucket."""
    out = runner.run(["mc", "ls", "--recursive", "--json", bucket_path(cfg)],
                     env=mc_env(cfg)).stdout
    objects = {}
    for line in out.decode().splitlines():
        if line.strip():
            entry = json.loads(line)
            if entry.get("type") != "folder" and "key" in entry:
                objects[entry["key"]] = int(entry["size"])
    return objects


def mirror_photos(cfg: Config, runner) -> StepResult:
    """Plain copy of the bucket. Never removes or overwrites a file on
    the NAS; differences are reported by the size check."""
    files = cfg.backup_root / "photos" / "files"
    files.mkdir(parents=True, exist_ok=True)
    problems = []
    try:
        runner.run(["mc", "mirror", "--json", bucket_path(cfg), str(files)],
                   env=mc_env(cfg))
    except CommandError as exc:
        problems.append(f"mc mirror exited {exc.returncode}")
    try:
        objects = list_bucket(cfg, runner)
    except (CommandError, ValueError) as exc:
        problems.append(f"could not list the bucket "
                        f"({type(exc).__name__})")
        return StepResult("photos", False, "; ".join(problems))
    bad = sorted(key for key, size in objects.items()
                 if not (files / key).is_file()
                 or (files / key).stat().st_size != size)
    if bad:
        problems.append(f"{len(bad)} of {len(objects)} photos missing or "
                        f"different on the NAS: {', '.join(bad[:5])}")
    return StepResult("photos", not problems, "; ".join(problems),
                      {"objects": len(objects),
                       "bytes": sum(objects.values())})


def count_objects(tar: tarfile.TarFile, bucket: str) -> int:
    """Objects of `bucket` in a volume archive: one xl.meta each."""
    prefixes = (f"./{bucket}/", f"{bucket}/")
    return sum(1 for m in tar.getmembers()
               if m.name.startswith(prefixes) and m.name.endswith("/xl.meta"))


def volume_copy(cfg: Config, runner, today, objects: Optional[int]
                ) -> StepResult:
    """Monthly exact copy of the whole MinIO volume (bucket and MinIO's
    own metadata), read-only, verified by counting one xl.meta per object
    in the bucket."""
    folder = cfg.backup_root / "photos" / "volume"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{today:%Y-%m}.tar.gz"
    if (folder / name).exists():
        return StepResult("volume", True, "exists", {"volume": name})
    if objects is None:
        return StepResult("volume", False, "photo count unknown")

    def write(part: Path) -> None:
        with open(part, "wb") as handle:
            runner.run(["docker", "run", "--rm", "--entrypoint", "tar",
                        "-v", f"{cfg.minio_volume}:/data:ro", cfg.tar_image,
                        "-C", "/data", "-czf", "-", "."],
                       stdout=handle)
        with tarfile.open(part, "r:gz") as tar:
            found = count_objects(tar, cfg.bucket)
        if found != objects:
            raise ValueError(f"archive holds {found} objects, "
                             f"bucket {objects}")

    try:
        atomic_write(folder / name, write)
    except (CommandError, ValueError, tarfile.TarError, OSError) as exc:
        return StepResult("volume", False, str(exc))
    return StepResult("volume", True, data={"volume": name})


def _env_files(docker_root: Path) -> list:
    if not docker_root.is_dir():
        return []
    return sorted(p for p in docker_root.glob("*/.env")
                  if p.is_file() and ".bak" not in p.parent.name)


def pack_secrets(cfg: Config, runner, today) -> StepResult:
    """Every app's .env, encrypted to the owner's age key. The private
    key never touches the Pi."""
    folder = cfg.backup_root / "secrets"
    folder.mkdir(parents=True, exist_ok=True)
    env_files = _env_files(cfg.docker_root)
    if not env_files:
        return StepResult("secrets", False,
                          f"no .env files under {cfg.docker_root}")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in env_files:
            tar.add(path, arcname=f"{path.parent.name}/.env")
    name = f"{today:%Y-%m-%d}.tar.age"

    def write(part: Path) -> None:
        runner.run(["age", "-r", cfg.age_recipient, "-o", str(part)],
                   stdin=buffer.getvalue())
        if not part.is_file() or part.stat().st_size == 0:
            raise ValueError("age wrote nothing")

    try:
        atomic_write(folder / name, write)
    except (CommandError, ValueError, OSError) as exc:
        return StepResult("secrets", False, str(exc))
    return StepResult("secrets", True,
                      data={"secrets": name, "files": len(env_files)})


def apply_retention(cfg: Config, today) -> StepResult:
    deleted = 0
    for folder, choose in (
            (cfg.backup_root / "photos" / "volume", volumes_to_delete),
            (cfg.backup_root / "secrets",
             lambda names: secrets_to_delete(names, today))):
        if folder.is_dir():
            for name in choose([p.name for p in folder.iterdir()]):
                (folder / name).unlink()
                deleted += 1
    return StepResult("retention", True, data={"deleted": deleted})
