"""Monthly restore test from the NAS (#31)."""
import gzip
import hashlib
import io
import json
import tarfile

import pytest

import ops.backup.restore_test as rt
from backup_fakes import FakeRunner
from ops.backup.common import Config
from ops.backup.steps import StepResult

pytestmark = pytest.mark.unit


@pytest.fixture
def cfg(tmp_path):
    root = tmp_path / "share" / "fordDbs-backups"
    root.mkdir(parents=True)
    docker = tmp_path / "docker"
    (docker / "fordDbs").mkdir(parents=True)
    (docker / "fordDbs" / ".env").write_text(
        "MINIO_ROOT_USER=root\nMINIO_ROOT_PASSWORD=rootpw\n")
    return Config(backup_root=root, ntfy_url="https://ntfy.example/t",
                  age_recipient="age1abc", minio_reader_key="r",
                  minio_reader_secret="s", docker_root=docker,
                  lock_path=tmp_path / "backup.lock")


DUMP = (b"\\restrict abc123\n-- Dumped by pg_dump version 18.0\n"
        b"SET statement_timeout = 0;\nSET transaction_timeout = 0;\n"
        b"CREATE TABLE public.users (id int);\n"
        b"ALTER TABLE public.users OWNER TO dad;\n\\unrestrict abc123\n")


def put_dumps(cfg):
    for db in cfg.databases:
        folder = cfg.backup_root / "postgres" / db / "last"
        folder.mkdir(parents=True)
        (folder / f"{db}-latest.sql.gz").write_bytes(gzip.compress(DUMP))


def test_dump_owners():
    assert rt.dump_owners(b"ALTER TABLE public.users OWNER TO dad;\n"
                          b"ALTER SCHEMA x OWNER TO app;\n") == {"dad", "app"}


def test_prepare_dump_drops_lines_pg15_cannot_run():
    out = rt.prepare_dump(DUMP)

    assert b"\\restrict" not in out and b"\\unrestrict" not in out
    assert b"transaction_timeout" not in out
    assert b"SET statement_timeout = 0;" in out
    assert b"CREATE TABLE public.users" in out


def test_counts_ok():
    assert rt.counts_ok({"users": 3}, {"users": 3}) == []
    assert rt.counts_ok({"users": 0}, {"users": 3})
    assert rt.counts_ok({"users": 4}, {"users": 3})
    assert rt.counts_ok({"users": 0}, {"users": 0}) == []


def db_runner(restore_code=0, restored=b"3\n", live=b"3\n"):
    return FakeRunner({
        "docker exec -i restoretest-pg": restore_code,
        "docker exec restoretest-pg-forddbs psql -tA": restored,
        "docker exec restoretest-pg-chore_tracker psql -tA": restored,
        "docker exec postgres_db": live,
        "docker exec chore-tracker-db-1": live,
    })


class TestRestoreDatabases:

    def test_restores_and_compares_counts(self, cfg):
        put_dumps(cfg)
        fake = db_runner()

        r = rt.restore_databases(cfg, fake, sleep=lambda s: None)

        assert r.ok, r.detail
        restore = [c for c in fake.calls if c[0][:3] == ["docker", "exec",
                                                         "-i"]]
        assert len(restore) == 2
        assert b"transaction_timeout" not in restore[0][1]["stdin"]
        assert "ON_ERROR_STOP=1" in restore[0][0]
        roles = fake.commands("docker exec restoretest-pg-forddbs psql -U "
                              "postgres -c CREATE ROLE")
        assert roles and '"dad"' in roles[0][-1]
        created = fake.commands("docker exec restoretest-pg-chore_tracker "
                                "psql -U postgres -c CREATE DATABASE")
        assert created

    def test_containers_have_no_ports_and_are_removed(self, cfg):
        put_dumps(cfg)
        fake = db_runner()

        rt.restore_databases(cfg, fake, sleep=lambda s: None)

        for cmd in fake.commands("docker run"):
            assert "-p" not in cmd and "--publish" not in cmd
            assert cmd[cmd.index("--name") + 1].startswith("restoretest-")
        assert ["docker", "rm", "-f", "restoretest-pg-forddbs"] in \
            fake.commands("docker rm")

    def test_restore_failure_still_cleans_up(self, cfg):  # Review Focus 5
        put_dumps(cfg)
        fake = db_runner(restore_code=3)

        r = rt.restore_databases(cfg, fake, sleep=lambda s: None)

        assert not r.ok and "forddbs" in r.detail
        assert ["docker", "rm", "-f", "restoretest-pg-forddbs"] in \
            fake.commands("docker rm")
        assert ["docker", "rm", "-f", "restoretest-pg-chore_tracker"] in \
            fake.commands("docker rm")

    def test_empty_restore_fails(self, cfg):
        put_dumps(cfg)

        r = rt.restore_databases(cfg, db_runner(restored=b"0\n"),
                                 sleep=lambda s: None)

        assert not r.ok and "users" in r.detail

    def test_missing_dump_fails(self, cfg):
        r = rt.restore_databases(cfg, db_runner(), sleep=lambda s: None)

        assert not r.ok and "no dump" in r.detail

    def test_server_never_ready_fails_and_cleans_up(self, cfg):
        put_dumps(cfg)
        fake = db_runner()
        fake.responses["docker exec restoretest-pg-forddbs pg_isready"] = 2
        naps = []

        r = rt.restore_databases(cfg, fake, sleep=naps.append)

        assert not r.ok and "not ready" in r.detail
        assert len(naps) >= 60
        assert ["docker", "rm", "-f", "restoretest-pg-forddbs"] in \
            fake.commands("docker rm")


PHOTOS = {"a.jpg": b"abc", "profiles/3_ab.jpg": b"xy"}


def put_photo_backup(cfg, objects=PHOTOS, files=PHOTOS):
    folder = cfg.backup_root / "photos" / "volume"
    folder.mkdir(parents=True)
    with tarfile.open(folder / "2026-11.tar.gz", "w:gz") as tar:
        for key in objects:
            info = tarfile.TarInfo(f"./family-photos/{key}/xl.meta")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"m"))
    for key, body in files.items():
        path = cfg.backup_root / "photos" / "files" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)


def photo_runner(objects=PHOTOS, alias_code=0):
    listing = "\n".join(json.dumps({"type": "file", "key": k,
                                    "size": len(v)})
                        for k, v in objects.items()).encode()

    def checksum(cmd, kwargs):
        key = cmd[-1]
        return (hashlib.sha256(objects[key]).hexdigest() + "  -\n").encode()

    return FakeRunner({
        "docker inspect family_photos_storage": b"minio/minio:tag\n",
        "docker exec -e MC_HOST_r restoretest-minio mc ls r/": alias_code,
        "docker exec -e MC_HOST_r restoretest-minio mc ls --recursive":
            listing,
        "docker exec -e MC_HOST_r restoretest-minio sh -c": checksum,
    })


class TestRestorePhotos:

    def test_restores_and_compares_checksums(self, cfg):
        put_photo_backup(cfg)
        fake = photo_runner()

        r = rt.restore_photos(cfg, fake, sleep=lambda s: None)

        assert r.ok, r.detail
        assert r.data == {"objects": 2}
        server_call = [c for c in fake.calls
                       if c[0][:3] == ["docker", "run", "-d"]][0]
        server, kwargs = server_call
        assert "-p" not in server
        assert "MINIO_ROOT_PASSWORD" in server
        assert kwargs["env"]["MINIO_ROOT_PASSWORD"] == "rootpw"
        assert server[-3:] == ["minio/minio:tag", "server", "/data"]
        for cmd, kw in fake.calls:
            assert "rootpw" not in " ".join(cmd)
        listed = [kw for c, kw in fake.calls if "--recursive" in c][0]
        assert listed["env"]["MC_HOST_r"] == \
            "http://root:rootpw@localhost:9000"
        untar = fake.commands("docker run --rm")[0]
        assert f"{cfg.backup_root / 'photos' / 'volume'}:/backup:ro" in untar
        assert untar[-4:] == ["-C", "/data", "-xzf",
                              "/backup/2026-11.tar.gz"]

    def test_checksum_mismatch_reported(self, cfg):
        put_photo_backup(cfg, files={"a.jpg": b"abd",
                                     "profiles/3_ab.jpg": b"xy"})

        r = rt.restore_photos(cfg, photo_runner(), sleep=lambda s: None)

        assert not r.ok and "a.jpg" in r.detail

    def test_count_mismatch_reported(self, cfg):
        put_photo_backup(cfg, objects={**PHOTOS, "c.jpg": b"c"})

        r = rt.restore_photos(cfg, photo_runner(), sleep=lambda s: None)

        assert not r.ok and "3" in r.detail and "2" in r.detail

    def test_cleanup_after_minio_never_starts(self, cfg):  # Focus 5
        put_photo_backup(cfg)
        naps = []

        fake = photo_runner(alias_code=1)
        r = rt.restore_photos(cfg, fake, sleep=naps.append)

        assert not r.ok and "did not start" in r.detail
        assert len(naps) == 60
        assert ["docker", "rm", "-f", "restoretest-minio"] in \
            fake.commands("docker rm")
        assert ["docker", "volume", "rm", "restoretest-minio"] in \
            fake.commands("docker volume rm")

    def test_root_password_never_on_failure_detail(self, cfg):
        put_photo_backup(cfg)

        r = rt.restore_photos(cfg, photo_runner(alias_code=1),
                              sleep=lambda s: None)

        assert "rootpw" not in r.detail


class TestSecretsCheck:

    def test_needs_age_header(self, cfg):
        folder = cfg.backup_root / "secrets"
        folder.mkdir()
        (folder / "2026-11-13.tar.age").write_bytes(
            b"age-encryption.org/v1\n-> X25519 ...")
        (folder / "2026-11-14.tar.age").write_bytes(b"plain text")

        assert not rt.check_secrets(cfg).ok

    def test_valid_newest_file_passes(self, cfg):
        folder = cfg.backup_root / "secrets"
        folder.mkdir()
        (folder / "2026-11-14.tar.age").write_bytes(
            b"age-encryption.org/v1\n-> X25519 ...")

        assert rt.check_secrets(cfg).ok

    def test_missing_secrets_fail(self, cfg):
        assert not rt.check_secrets(cfg).ok


class Sent(list):
    def __call__(self, url, title, message, priority="default"):
        self.append((title, message, priority))
        return True


def test_run_restore_test_reports_pass_and_fail(cfg, monkeypatch):
    monkeypatch.setattr(rt, "restore_databases", lambda *a, **k:
                        StepResult("databases", True))
    monkeypatch.setattr(rt, "restore_photos", lambda *a, **k:
                        StepResult("photos", True, data={"objects": 2}))
    monkeypatch.setattr(rt, "check_secrets", lambda *a, **k:
                        StepResult("secrets", True))
    sent = Sent()

    assert rt.run_restore_test(cfg, FakeRunner(), sent) == 0
    assert sent == [("fordDbs restore test",
                     "restore test passed: 2 databases, 2 photos",
                     "default")]

    monkeypatch.setattr(rt, "restore_photos", lambda *a, **k:
                        StepResult("photos", False, "1 checksum differs"))
    sent.clear()
    assert rt.run_restore_test(cfg, FakeRunner(), sent) == 1
    assert sent == [("fordDbs restore test",
                     "restore test failed: photos", "high")]


def test_leftover_containers_removed_before_start(cfg):
    put_dumps(cfg)
    put_photo_backup(cfg)
    fake = db_runner()
    fake.responses.update(photo_runner().responses)

    rt.restore_databases(cfg, fake, sleep=lambda s: None)
    rt.restore_photos(cfg, fake, sleep=lambda s: None)

    cmds = [c for c, _ in fake.calls]
    first_pg = cmds.index(["docker", "rm", "-f", "restoretest-pg-forddbs"])
    assert first_pg < next(i for i, c in enumerate(cmds)
                           if c[:2] == ["docker", "run"])
    created = cmds.index(["docker", "volume", "create", "restoretest-minio"])
    assert ["docker", "volume", "rm", "restoretest-minio"] in cmds[:created]


def env_for(cfg, tmp_path):
    env = tmp_path / "env"
    env.write_text(f"BACKUP_ROOT={cfg.backup_root}\nNTFY_URL=https://n/t\n"
                   "AGE_RECIPIENT=age1\nBACKUP_READER_KEY=r\n"
                   f"BACKUP_READER_SECRET=s\nLOCK_PATH={cfg.lock_path}\n"
                   f"DOCKER_ROOT={cfg.docker_root}\n")
    return env


def test_skipped_restore_test_is_reported(cfg, tmp_path, monkeypatch):
    import signal
    from ops.backup.common import exclusive_lock
    previous = signal.getsignal(signal.SIGTERM)
    sent = []
    monkeypatch.setattr(rt, "notify", lambda url, title, msg, prio="default":
                        sent.append((title, msg, prio)) or True)
    monkeypatch.setattr(rt, "LOCK_WAIT_SECONDS", 0)
    try:
        with exclusive_lock(cfg.lock_path):
            assert rt.main(["--config", str(env_for(cfg, tmp_path))]) == 1
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert sent == [("fordDbs restore test",
                     "restore test skipped: backup still running", "high")]
