"""Backup steps (#31): NAS check, databases, photos, volume, secrets."""
import io
import json
import os
import tarfile
from datetime import date, datetime, timedelta, timezone

import pytest

from backup_fakes import FakeRunner
from ops.backup.common import Config
from ops.backup.steps import (apply_retention, check_storage, check_target,
                              copy_databases,
                              list_bucket, mc_env, mirror_photos,
                              pack_secrets, volume_copy)

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

    def test_ok_on_cifs(self, cfg):
        r = check_target(cfg, FakeRunner({"findmnt": b"autofs\ncifs\n"}))

        assert r.ok, r.detail
        assert cfg.backup_root.is_dir()

    def test_storage_ok_with_space(self, cfg):
        cfg.backup_root.mkdir()
        r = check_storage(cfg, FakeRunner({"mc du": b'{"size": 1000}\n'}))

        assert r.ok, r.detail
        assert r.data["bucket_bytes"] == 1000

    def test_storage_fails_when_minio_down(self, cfg):
        cfg.backup_root.mkdir()
        r = check_storage(cfg, FakeRunner({"mc du": 1}))

        assert not r.ok and "MinIO" in r.detail

    def test_storage_fails_without_space(self, cfg):
        cfg.backup_root.mkdir()
        r = check_storage(cfg, FakeRunner({"mc du": b'{"size": %d}'
                                           % 10 ** 18}))

        assert not r.ok and "space" in r.detail

    def test_mc_credentials_only_in_env(self, cfg):
        cfg.backup_root.mkdir()
        fake = FakeRunner({"mc du": b'{"size": 1}'})

        check_storage(cfg, fake)

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
            ["rsync", "-rt", "--delete", "--no-links",
             f"{cfg.postgres_source}/{db}/",
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
        copied = [c[4] for c in fake.commands("rsync")]
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


TODAY = date(2026, 11, 14)


def listing(objects):
    lines = [json.dumps({"status": "success", "type": "file", "key": k,
                         "size": len(v)}) for k, v in objects.items()]
    lines.append(json.dumps({"status": "success", "type": "folder",
                             "key": "profiles/", "size": 0}))
    return ("\n".join(lines) + "\n").encode()


def put_files(cfg, objects):
    for key, body in objects.items():
        path = cfg.backup_root / "photos" / "files" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)


OBJECTS = {"a.jpg": b"abc", "profiles/3_ab.jpg": b"xy"}


class TestPhotos:

    def test_list_bucket_skips_folders(self, cfg):
        assert list_bucket(cfg, FakeRunner({"mc ls": listing(OBJECTS)})) \
            == {"a.jpg": 3, "profiles/3_ab.jpg": 2}

    def test_mirror_verifies_nested_keys(self, cfg):  # Review Focus 3
        put_files(cfg, OBJECTS)

        r = mirror_photos(cfg, FakeRunner({"mc ls": listing(OBJECTS)}))

        assert r.ok, r.detail
        assert r.data == {"objects": 2, "bytes": 5}

    def test_mirror_reports_missing_and_wrong_size(self, cfg):
        put_files(cfg, {"a.jpg": b"abcd"})

        r = mirror_photos(cfg, FakeRunner({"mc ls": listing(OBJECTS)}))

        assert not r.ok
        assert "2 of 2" in r.detail and "profiles/3_ab.jpg" in r.detail

    def test_mirror_never_removes_or_overwrites(self, cfg):
        put_files(cfg, OBJECTS)
        fake = FakeRunner({"mc ls": listing(OBJECTS)})

        mirror_photos(cfg, fake)

        cmd, kwargs = fake.calls[0]
        assert cmd == ["mc", "mirror", "--json", "backup/family-photos",
                       str(cfg.backup_root / "photos" / "files")]
        assert kwargs["env"]["MC_HOST_backup"].startswith("http://reader:")

    def test_mirror_failure_fails_the_step(self, cfg):
        r = mirror_photos(cfg, FakeRunner({"mc mirror": 1,
                                           "mc ls": listing({})}))

        assert not r.ok and "mc mirror" in r.detail


def volume_tar(keys):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for key in keys:
            info = tarfile.TarInfo(f"./family-photos/{key}/xl.meta")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"m"))
        sys_meta = tarfile.TarInfo("./.minio.sys/config/config.json/xl.meta")
        sys_meta.size = 1
        tar.addfile(sys_meta, io.BytesIO(b"m"))
    return buffer.getvalue()


class TestVolumeCopy:

    def test_skipped_when_month_exists(self, cfg):
        folder = cfg.backup_root / "photos" / "volume"
        folder.mkdir(parents=True)
        (folder / "2026-11.tar.gz").write_bytes(b"x")
        fake = FakeRunner()

        r = volume_copy(cfg, fake, TODAY, objects=2)

        assert r.ok and r.detail == "exists" and fake.calls == []

    def test_writes_verified_archive(self, cfg):
        fake = FakeRunner({"docker run": volume_tar(OBJECTS)})

        r = volume_copy(cfg, fake, TODAY, objects=2)

        assert r.ok, r.detail
        assert r.data == {"volume": "2026-11.tar.gz"}
        assert (cfg.backup_root / "photos" / "volume" /
                "2026-11.tar.gz").stat().st_size > 0
        cmd = fake.calls[0][0]
        assert cmd[:8] == [
            "docker", "run", "--rm", "--entrypoint", "tar", "-v",
            "forddbs_minio_data:/data:ro", "forddbs-api"]
        assert cmd[-5:] == ["-C", "/data", "-czf", "-", "."]
        for skipped in ("./.minio.sys/tmp", "./.minio.sys/multipart",
                        "./.minio.sys/config"):
            assert f"--exclude={skipped}" in cmd
        assert "--warning=no-file-changed" in cmd
        assert "--ignore-failed-read" in cmd

    def test_tar_exit_1_accepted_when_count_matches(self, cfg):
        fake = FakeRunner({"docker run": volume_tar(OBJECTS)})
        fake.responses["docker run"] = lambda cmd, kw: (
            kw["stdout"].write(volume_tar(OBJECTS)) and None) or 1

        r = volume_copy(cfg, fake, TODAY, objects=2)

        assert r.ok, r.detail

    def test_tar_exit_2_fails(self, cfg):
        fake = FakeRunner()
        fake.responses["docker run"] = lambda cmd, kw: (
            kw["stdout"].write(volume_tar(OBJECTS)) and None) or 2

        r = volume_copy(cfg, fake, TODAY, objects=2)

        assert not r.ok

    def test_count_mismatch_leaves_no_file(self, cfg):
        fake = FakeRunner({"docker run": volume_tar(OBJECTS)})

        r = volume_copy(cfg, fake, TODAY, objects=3)

        assert not r.ok and "2" in r.detail and "3" in r.detail
        assert list((cfg.backup_root / "photos" / "volume").iterdir()) == []

    def test_without_photo_count_it_fails(self, cfg):
        r = volume_copy(cfg, FakeRunner(), TODAY, objects=None)

        assert not r.ok


def fake_age(seen):
    def run(cmd, kwargs):
        seen.append(kwargs["stdin"])
        out = cmd[cmd.index("-o") + 1]
        with open(out, "wb") as f:
            f.write(b"age-encryption.org/v1\n...")
        return b""
    return run


class TestSecrets:

    def test_skip_bak_folders_and_encrypt(self, cfg):
        for folder in ("fordDbs", "chore-tracker", "trading-bot.bak-1"):
            (cfg.docker_root / folder).mkdir(parents=True)
            (cfg.docker_root / folder / ".env").write_text("K=v\n")
        (cfg.docker_root / "no-env").mkdir()
        seen = []
        fake = FakeRunner({"age": fake_age(seen)})

        r = pack_secrets(cfg, fake, TODAY)

        assert r.ok, r.detail
        assert r.data == {"secrets": "2026-11-14.tar.age", "files": 2}
        with tarfile.open(fileobj=io.BytesIO(seen[0]), mode="r:gz") as tar:
            assert sorted(tar.getnames()) == ["chore-tracker/.env",
                                              "fordDbs/.env"]
        cmd = fake.calls[0][0]
        assert cmd[:3] == ["age", "-r", "age1abc"]
        assert (cfg.backup_root / "secrets" / "2026-11-14.tar.age").exists()

    def test_fail_without_env_files(self, cfg):
        cfg.docker_root.mkdir()

        r = pack_secrets(cfg, FakeRunner(), TODAY)

        assert not r.ok and "no .env" in r.detail

    def test_age_failure_leaves_no_file(self, cfg):
        (cfg.docker_root / "fordDbs").mkdir(parents=True)
        (cfg.docker_root / "fordDbs" / ".env").write_text("K=v\n")

        r = pack_secrets(cfg, FakeRunner({"age": 1}), TODAY)

        assert not r.ok
        assert list((cfg.backup_root / "secrets").iterdir()) == []


def test_retention_deletes_only_old(cfg):
    volumes = cfg.backup_root / "photos" / "volume"
    secrets = cfg.backup_root / "secrets"
    volumes.mkdir(parents=True)
    secrets.mkdir(parents=True)
    for m in range(3, 11):
        (volumes / f"2026-{m:02d}.tar.gz").write_bytes(b"v")
    for n in range(40):
        day = TODAY - timedelta(days=n)
        (secrets / f"{day.isoformat()}.tar.age").write_bytes(b"s")
    (secrets / "README").write_text("keep")

    r = apply_retention(cfg, TODAY)

    assert r.ok
    assert sorted(p.name for p in volumes.iterdir())[0] == "2026-05.tar.gz"
    assert (secrets / "README").exists()
    assert (secrets / "2026-10-31.tar.age").exists()
    assert not (secrets / "2026-10-07.tar.age").exists()
    assert r.data["deleted"] == 2 + 10
