"""Backup steps (#31): NAS check, databases, photos, volume, secrets."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from backup_fakes import FakeRunner
from ops.backup.common import Config
from ops.backup.steps import check_target, copy_databases, mc_env

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 14, 3, 30, tzinfo=timezone.utc)


def make_cfg(tmp_path, **kw):
    return Config(backup_root=tmp_path / "share" / "fordDbs-backups",
                  ntfy_url="https://ntfy.example/t", age_recipient="age1abc",
                  minio_reader_key="reader", minio_reader_secret="secret",
                  postgres_source=tmp_path / "src",
                  docker_root=tmp_path / "docker", **kw)


@pytest.fixture
def cfg(tmp_path):
    (tmp_path / "share").mkdir()
    return make_cfg(tmp_path)


def dump(cfg, db, folder, name, age_hours):
    path = cfg.postgres_source / db / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    stamp = (NOW - timedelta(hours=age_hours)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def fresh_dumps(cfg, age_hours=1):
    for db in cfg.databases:
        dump(cfg, db, "daily", f"{db}-20261114.sql.gz", age_hours)
        dump(cfg, db, "last", f"{db}-latest.sql.gz", age_hours)


class TestCheckTarget:

    def test_refuses_plain_folder(self, cfg):
        r = check_target(cfg, FakeRunner({"findmnt": b"ext4\n"}))

        assert not r.ok and "not mounted" in r.detail
        assert not cfg.backup_root.exists()

    def test_ok_on_cifs_with_space(self, cfg):
        r = check_target(cfg, FakeRunner({"findmnt": b"cifs\n",
                                          "mc du": b'{"size": 1000}\n'}))

        assert r.ok, r.detail
        assert r.data["bucket_bytes"] == 1000
        assert cfg.backup_root.is_dir()

    def test_fails_when_minio_down(self, cfg):
        r = check_target(cfg, FakeRunner({"findmnt": b"cifs\n",
                                          "mc du": 1}))

        assert not r.ok and "MinIO" in r.detail

    def test_fails_without_space(self, cfg):
        r = check_target(cfg, FakeRunner({"findmnt": b"cifs\n",
                                          "mc du": b'{"size": %d}'
                                          % 10 ** 18}))

        assert not r.ok and "space" in r.detail

    def test_mc_credentials_only_in_env(self, cfg):
        fake = FakeRunner({"findmnt": b"cifs\n", "mc du": b'{"size": 1}'})

        check_target(cfg, fake)

        cmd, kwargs = fake.calls[-1]
        assert cmd[:2] == ["mc", "du"]
        assert "secret" not in " ".join(cmd)
        assert kwargs["env"] == {
            "MC_HOST_backup": "http://reader:secret@localhost:9000"}


def test_mc_env_quotes_special_characters(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg = Config(**{**cfg.__dict__, "minio_reader_secret": "a/b@c"})

    assert mc_env(cfg) == {
        "MC_HOST_backup": "http://reader:a%2Fb%40c@localhost:9000"}


class TestCopyDatabases:

    def test_copied_when_fresh(self, cfg):
        fresh_dumps(cfg)
        fake = FakeRunner()

        r = copy_databases(cfg, fake, NOW)

        assert r.ok, r.detail
        assert fake.commands("rsync") == [
            ["rsync", "-a", "--delete", f"{cfg.postgres_source}/{db}/",
             f"{cfg.backup_root}/postgres/{db}/"] for db in cfg.databases]
        assert r.data["newest"] == {"forddbs": "forddbs-latest.sql.gz",
                                    "chore_tracker":
                                        "chore_tracker-latest.sql.gz"}

    def test_empty_daily_skips_rsync_and_fails(self, cfg):  # Review Focus 2
        fresh_dumps(cfg)
        for p in (cfg.postgres_source / "forddbs").rglob("*.sql.gz"):
            p.unlink()
        fake = FakeRunner()

        r = copy_databases(cfg, fake, NOW)

        assert not r.ok and "forddbs" in r.detail
        copied = [c[3] for c in fake.commands("rsync")]
        assert copied == [f"{cfg.postgres_source}/chore_tracker/"]

    def test_stale_dump_fails_but_still_copies(self, cfg):  # Review Focus 2
        fresh_dumps(cfg, age_hours=40)
        fake = FakeRunner()

        r = copy_databases(cfg, fake, NOW)

        assert not r.ok and "older than 36 h" in r.detail
        assert len(fake.commands("rsync")) == 2

    def test_rsync_failure_fails_the_step(self, cfg):
        fresh_dumps(cfg)

        r = copy_databases(cfg, FakeRunner({"rsync": 23}), NOW)

        assert not r.ok and "rsync" in r.detail
