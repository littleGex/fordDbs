"""Shared helpers for the NAS backups (#31)."""
from datetime import date, timedelta
from pathlib import Path

import pytest

from backup_fakes import FakeRunner
from ops.backup.common import (AlreadyRunning, ConfigError, atomic_write,
                               exclusive_lock, human_size, is_cifs_mount,
                               load_config, notify, secrets_to_delete,
                               volumes_to_delete)

pytestmark = pytest.mark.unit

REQUIRED = ("BACKUP_ROOT=/nas/b\nNTFY_URL=https://ntfy.example/t\n"
            "AGE_RECIPIENT=age1abc\nBACKUP_READER_KEY=reader\n"
            "BACKUP_READER_SECRET=secret\n")


def test_load_config_reads_values_and_defaults(tmp_path):
    path = tmp_path / "env"
    path.write_text("# backup settings\n" + REQUIRED)

    cfg = load_config(path)

    assert cfg.backup_root == Path("/nas/b")
    assert cfg.ntfy_url == "https://ntfy.example/t"
    assert cfg.minio_reader_secret == "secret"
    assert cfg.databases == ("forddbs", "chore_tracker")
    assert cfg.minio_url == "http://localhost:9000"
    assert cfg.bucket == "family-photos"


def test_load_config_names_missing_keys(tmp_path):
    path = tmp_path / "env"
    path.write_text("BACKUP_ROOT=/nas/b\n")

    with pytest.raises(ConfigError, match="AGE_RECIPIENT"):
        load_config(path)


def test_atomic_write_renames_when_complete(tmp_path):
    atomic_write(tmp_path / "a.txt", lambda p: p.write_text("x"))

    assert (tmp_path / "a.txt").read_text() == "x"
    assert list(tmp_path.iterdir()) == [tmp_path / "a.txt"]


def test_atomic_write_leaves_nothing_on_failure(tmp_path):
    def boom(part):
        part.write_text("half")
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        atomic_write(tmp_path / "a.txt", boom)

    assert list(tmp_path.iterdir()) == []


def test_second_lock_raises_already_running(tmp_path):
    lock = tmp_path / "sub" / "backup.lock"
    with exclusive_lock(lock):
        with pytest.raises(AlreadyRunning):
            with exclusive_lock(lock):
                pass
    with exclusive_lock(lock):
        pass


def test_notify_sends_title_priority_and_body():
    sent = []

    assert notify("https://n/t", "T", "body", "high",
                  post=lambda *a: sent.append(a)) is True
    assert sent == [("https://n/t", b"body",
                     {"Title": "T", "Priority": "high"})]


def test_notify_swallows_errors():
    def raising(*a):
        raise OSError("offline")

    assert notify("https://n/t", "T", "b", post=raising) is False


def test_cifs_mount_detected(tmp_path):
    fake = FakeRunner({"findmnt": b"cifs\n"})

    assert is_cifs_mount(tmp_path, fake) is True
    assert fake.calls[0][0] == ["findmnt", "-n", "-o", "FSTYPE", "-T",
                                str(tmp_path)]


def test_automount_reports_autofs_then_cifs(tmp_path):
    assert is_cifs_mount(tmp_path, FakeRunner({"findmnt": b"autofs\ncifs\n"}))


def test_untriggered_automount_is_not_a_mount(tmp_path):
    assert not is_cifs_mount(tmp_path, FakeRunner({"findmnt": b"autofs\n"}))


def test_lock_waits_for_the_holder_then_gives_up(tmp_path):
    lock = tmp_path / "backup.lock"
    naps = []
    with exclusive_lock(lock):
        with pytest.raises(AlreadyRunning):
            with exclusive_lock(lock, wait_seconds=5, sleep=naps.append):
                pass
    assert len(naps) == 5


def test_failed_command_prints_stderr_tail(capsys):
    from ops.backup.common import CommandError, Runner
    with pytest.raises(CommandError):
        Runner().run(["sh", "-c", "echo first >&2; echo boom >&2; exit 3"])

    out = capsys.readouterr().out
    assert "sh exited 3" in out and "boom" in out


def test_smb3_mount_detected(tmp_path):
    assert is_cifs_mount(tmp_path, FakeRunner({"findmnt": b"smb3\n"}))


def test_plain_folder_is_not_a_mount(tmp_path):
    assert is_cifs_mount(tmp_path, FakeRunner({"findmnt": b"ext4\n"})) \
        is False


def test_missing_folder_is_not_a_mount(tmp_path):
    fake = FakeRunner()

    assert is_cifs_mount(tmp_path / "nope", fake) is False
    assert fake.calls == []


def test_volumes_keep_newest_six():
    names = [f"2026-{m:02d}.tar.gz" for m in range(1, 10)] + ["notes.txt"]

    assert volumes_to_delete(names) == [
        "2026-01.tar.gz", "2026-02.tar.gz", "2026-03.tar.gz"]


def test_volumes_nothing_deleted_at_or_below_keep():
    assert volumes_to_delete(["2026-01.tar.gz"]) == []
    assert volumes_to_delete(
        [f"2026-{m:02d}.tar.gz" for m in range(1, 7)]) == []


def daily_names(first, last):
    day, names = first, []
    while day <= last:
        names.append(f"{day.isoformat()}.tar.age")
        day += timedelta(days=1)
    return names


def test_secrets_keep_30_days_and_newest_per_month():
    today = date(2026, 11, 14)
    names = daily_names(date(2026, 4, 1), today) + ["x.age"]

    deleted = secrets_to_delete(names, today)

    kept = set(names) - set(deleted) - {"x.age"}
    month_ends = {"2026-05-31.tar.age", "2026-06-30.tar.age",
                  "2026-07-31.tar.age", "2026-08-31.tar.age",
                  "2026-09-30.tar.age", "2026-10-31.tar.age"}
    recent = set(daily_names(today - timedelta(days=29), today))
    assert kept == recent | month_ends
    assert "2026-04-30.tar.age" in deleted
    assert "x.age" not in deleted


def test_secrets_never_deletes_newest():
    assert secrets_to_delete(["2025-01-01.tar.age"],
                             date(2026, 11, 14)) == []


def test_human_size():
    assert human_size(5) == "5 B"
    assert human_size(452_000_000) == "452 MB"
    assert human_size(2_700_000_000) == "2.7 GB"
