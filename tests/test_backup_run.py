"""The nightly backup run (#31): step order, status file, ntfy."""
import json
from datetime import datetime, timezone

import pytest

import ops.backup.backup as backup
from backup_fakes import FakeRunner
from ops.backup.common import Config, exclusive_lock
from ops.backup.steps import StepResult

pytestmark = pytest.mark.unit

SATURDAY = datetime(2026, 11, 14, 3, 30, tzinfo=timezone.utc)
SUNDAY = datetime(2026, 11, 15, 3, 30, tzinfo=timezone.utc)
STEPS = ("check_target", "check_storage", "copy_databases", "mirror_photos",
         "volume_copy", "pack_secrets", "apply_retention")


@pytest.fixture
def cfg(tmp_path):
    root = tmp_path / "share" / "fordDbs-backups"
    root.mkdir(parents=True)
    return Config(backup_root=root, ntfy_url="https://ntfy.example/t",
                  age_recipient="age1abc", minio_reader_key="r",
                  minio_reader_secret="s",
                  lock_path=tmp_path / "backup.lock")


OK = {
    "check_target": StepResult("checks", True),
    "check_storage": StepResult("minio", True, data={"bucket_bytes": 5}),
    "copy_databases": StepResult("databases", True, data={"newest": {
        "forddbs": "f.sql.gz", "chore_tracker": "c.sql.gz"}}),
    "mirror_photos": StepResult("photos", True,
                                data={"objects": 2, "bytes": 5}),
    "volume_copy": StepResult("volume", True,
                              data={"volume": "2026-11.tar.gz"}),
    "pack_secrets": StepResult("secrets", True,
                               data={"secrets": "2026-11-14.tar.age",
                                     "files": 5}),
    "apply_retention": StepResult("retention", True, data={"deleted": 0}),
}


@pytest.fixture
def steps(monkeypatch):
    called, results = [], dict(OK)

    def stub(name):
        def run(*args, **kwargs):
            called.append(name)
            result = results[name]
            if isinstance(result, Exception):
                raise result
            return result
        return run

    for name in STEPS:
        monkeypatch.setattr(backup, name, stub(name))
    return called, results


class Sent(list):
    def __call__(self, url, title, message, priority="default"):
        self.append((title, message, priority))
        return True


def status(cfg):
    path = cfg.backup_root / "status" / "last-success.json"
    return json.loads(path.read_text()) if path.exists() else None


def test_all_ok_writes_status_and_no_alert_on_weekday(cfg, steps):
    sent = Sent()

    assert backup.run_backup(cfg, FakeRunner(), SATURDAY, sent) == 0

    assert steps[0] == list(STEPS)
    data = status(cfg)
    assert data["finished_at"] == SATURDAY.isoformat()
    assert data["photos"] == {"objects": 2, "bytes": 5}
    assert data["databases"] == {"forddbs": "f.sql.gz",
                                 "chore_tracker": "c.sql.gz"}
    assert data["volume"] == "2026-11.tar.gz"
    assert data["secrets"] == "2026-11-14.tar.age"
    assert sent == []


def test_sunday_sends_summary(cfg, steps):
    sent = Sent()

    backup.run_backup(cfg, FakeRunner(), SUNDAY, sent)

    assert sent == [("fordDbs backup OK",
                     "fordDbs backup OK: 2 databases, 2 photos (5 B), "
                     "last volume 2026-11", "default")]


def test_failed_step_does_not_stop_later_steps(cfg, steps):
    called, results = steps
    results["mirror_photos"] = StepResult("photos", False, "1 of 2 missing")
    sent = Sent()

    assert backup.run_backup(cfg, FakeRunner(), SUNDAY, sent) == 1

    assert called == list(STEPS)
    assert status(cfg) is None
    assert sent == [("fordDbs backup failed",
                     "photos (see journalctl -u fordDbs-backup)", "high")]


def test_unmounted_target_stops_everything(cfg, steps):  # Review Focus 1
    called, results = steps
    results["check_target"] = StepResult("checks", False, "not mounted")
    sent = Sent()

    assert backup.run_backup(cfg, FakeRunner(), SATURDAY, sent) == 1

    assert called == ["check_target"]
    assert sent[0][1].startswith("checks ")


def test_step_exception_becomes_failure(cfg, steps):
    called, results = steps
    results["copy_databases"] = OSError("gone")
    sent = Sent()

    assert backup.run_backup(cfg, FakeRunner(), SATURDAY, sent) == 1

    assert "mirror_photos" in called
    assert sent[0][1].startswith("databases ")


def test_ntfy_down_keeps_result(cfg, steps):  # Review Focus 4
    called, results = steps

    def down(*args, **kwargs):
        return False

    assert backup.run_backup(cfg, FakeRunner(), SUNDAY, down) == 0
    results["pack_secrets"] = StepResult("secrets", False, "age missing")
    assert backup.run_backup(cfg, FakeRunner(), SUNDAY, down) == 1


def test_main_second_instance_exits_quietly(cfg, tmp_path, monkeypatch):
    env = tmp_path / "env"
    env.write_text(f"BACKUP_ROOT={cfg.backup_root}\nNTFY_URL=https://n/t\n"
                   "AGE_RECIPIENT=age1\nBACKUP_READER_KEY=r\n"
                   f"BACKUP_READER_SECRET=s\nLOCK_PATH={cfg.lock_path}\n")
    ran = []
    monkeypatch.setattr(backup, "run_backup", lambda *a, **k: ran.append(1))

    with exclusive_lock(cfg.lock_path):
        assert backup.main(["--config", str(env)]) == 0

    assert ran == []


def test_minio_down_still_copies_databases_and_secrets(cfg, steps):
    called, results = steps
    results["check_storage"] = StepResult("minio", False, "MinIO down")
    sent = Sent()

    assert backup.run_backup(cfg, FakeRunner(), SATURDAY, sent) == 1

    assert called == ["check_target", "check_storage", "copy_databases",
                      "pack_secrets", "apply_retention"]
    assert sent == [("fordDbs backup failed",
                     "minio (see journalctl -u fordDbs-backup)", "high")]


def env_file(cfg, tmp_path):
    env = tmp_path / "env"
    env.write_text(f"BACKUP_ROOT={cfg.backup_root}\nNTFY_URL=https://n/t\n"
                   "AGE_RECIPIENT=age1\nBACKUP_READER_KEY=r\n"
                   f"BACKUP_READER_SECRET=s\nLOCK_PATH={cfg.lock_path}\n")
    return env


def test_main_crash_or_kill_still_alerts(cfg, tmp_path, monkeypatch):
    import signal
    previous = signal.getsignal(signal.SIGTERM)
    sent = []
    monkeypatch.setattr(backup, "notify",
                        lambda url, title, msg, prio="default":
                        sent.append((title, msg, prio)) or True)

    def killed(*a, **k):
        raise SystemExit(143)
    monkeypatch.setattr(backup, "run_backup", killed)
    try:
        with pytest.raises(SystemExit):
            backup.main(["--config", str(env_file(cfg, tmp_path))])
        assert signal.getsignal(signal.SIGTERM) is not previous
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert sent == [("fordDbs backup failed",
                     "interrupted (SystemExit) "
                     "(see journalctl -u fordDbs-backup)", "high")]
