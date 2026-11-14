"""
Nightly backup of the databases, photos and secrets to the NAS (#31).
Run by fordDbs-backup.timer:  python3 -m ops.backup.backup
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from ops.backup.common import (AlreadyRunning, Runner, atomic_write,
                               exclusive_lock, exit_on_sigterm, human_size,
                               load_config, notify)
from ops.backup.steps import (StepResult, apply_retention, check_storage,
                              check_target, copy_databases, mirror_photos,
                              pack_secrets, volume_copy)

DEFAULT_CONFIG = Path.home() / ".config" / "fordDbs-backup" / "env"
JOURNAL_HINT = "(see journalctl -u fordDbs-backup)"


def _step(name, func, *args, **kwargs) -> StepResult:
    """An unexpected exception fails this step only, by type name."""
    try:
        result = func(*args, **kwargs)
    except Exception as exc:
        result = StepResult(name, False, f"crashed: {type(exc).__name__}")
    status = "ok" if result.ok else "FAILED"
    print(f"{result.name}: {status} {result.detail}".rstrip(), flush=True)
    return result


def _write_status(cfg, now, results) -> None:
    by_name = {r.name: r.data for r in results}
    status = {"finished_at": now.isoformat(),
              "databases": by_name["databases"].get("newest", {}),
              "photos": by_name["photos"],
              "volume": by_name["volume"].get("volume"),
              "secrets": by_name["secrets"].get("secrets")}
    folder = cfg.backup_root / "status"
    folder.mkdir(exist_ok=True)
    atomic_write(folder / "last-success.json",
                 lambda p: p.write_text(json.dumps(status, indent=2) + "\n"))


def _summary(cfg, results) -> str:
    by_name = {r.name: r.data for r in results}
    photos = by_name["photos"]
    volume = (by_name["volume"].get("volume") or "none").split(".")[0]
    return (f"fordDbs backup OK: {len(cfg.databases)} databases, "
            f"{photos['objects']} photos ({human_size(photos['bytes'])}), "
            f"last volume {volume}")


def run_backup(cfg, runner, now: datetime, notifier=notify) -> int:
    today = now.date()
    results = [_step("checks", check_target, cfg, runner)]
    if results[0].ok:
        storage = _step("minio", check_storage, cfg, runner)
        results.append(storage)
        results.append(_step("databases", copy_databases, cfg, runner, now))
        if storage.ok:
            photos = _step("photos", mirror_photos, cfg, runner)
            results.append(photos)
            results.append(_step("volume", volume_copy, cfg, runner, today,
                                 objects=photos.data.get("objects")
                                 if photos.ok else None))
        results.append(_step("secrets", pack_secrets, cfg, runner, today))
        results.append(_step("retention", apply_retention, cfg, today))
    failed = [r.name for r in results if not r.ok]
    if failed:
        delivered = notifier(cfg.ntfy_url, "fordDbs backup failed",
                             f"{', '.join(failed)} {JOURNAL_HINT}", "high")
    else:
        _write_status(cfg, now, results)
        delivered = True
        if now.weekday() == 6:
            delivered = notifier(cfg.ntfy_url, "fordDbs backup OK",
                                 _summary(cfg, results))
    if not delivered:
        print("ntfy: not delivered", flush=True)
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    exit_on_sigterm()
    try:
        with exclusive_lock(cfg.lock_path):
            return run_backup(cfg, Runner(), datetime.now().astimezone())
    except AlreadyRunning:
        print("another backup or restore test is running", flush=True)
        return 0
    except BaseException as exc:  # crash, timeout or shutdown: say so
        notify(cfg.ntfy_url, "fordDbs backup failed",
               f"interrupted ({type(exc).__name__}) {JOURNAL_HINT}", "high")
        raise


if __name__ == "__main__":
    sys.exit(main())
