"""systemd units, example config and installer for the backups (#31)."""
import configparser
from pathlib import Path

import pytest

from ops.backup.common import REQUIRED_KEYS

pytestmark = pytest.mark.unit

UNITS = Path(__file__).resolve().parent.parent / "ops" / "backup"


def unit(name):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(UNITS / "systemd" / name)
    return parser


@pytest.mark.parametrize("name,module", [
    ("fordDbs-backup.service", "ops.backup.backup"),
    ("fordDbs-restore-test.service", "ops.backup.restore_test")])
def test_services_run_as_dad_from_the_checkout(name, module):
    service = unit(name)["Service"]

    assert service["Type"] == "oneshot"
    assert service["User"] == "dad"
    assert service["WorkingDirectory"] == "/home/dad/docker/fordDbs"
    assert service["ExecStart"] == f"/usr/bin/python3 -m {module}"
    assert service["TimeoutStartSec"] == "2h"


@pytest.mark.parametrize("name,calendar", [
    ("fordDbs-backup.timer", "*-*-* 03:30:00"),
    ("fordDbs-restore-test.timer", "Sun *-*-01..07 04:30:00")])
def test_timers(name, calendar):
    timer = unit(name)

    assert timer["Timer"]["OnCalendar"] == calendar
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"


def test_env_example_lists_every_required_key():
    text = (UNITS / "env.example").read_text()

    for key in REQUIRED_KEYS:
        assert f"\n{key}=" in f"\n{text}"


def test_installer_is_strict():
    lines = (UNITS / "install.sh").read_text().splitlines()

    assert "set -euo pipefail" in lines


def test_installer_checks_mc_is_the_minio_client():
    text = (UNITS / "install.sh").read_text()

    assert "mc --version" in text and "grep -qi minio" in text


def readme_backups():
    text = (UNITS.parent.parent / "README.md").read_text()
    return text[text.index("## Backups to the NAS"):]


def test_readme_photo_restore_checks_the_archive_before_deleting():
    section = readme_backups()

    assert "docker compose stop minio" not in section
    assert "docker stop family_photos_storage" in section
    restore = section[section.index("**All photos"):]
    assert restore.index("tar -tzf") < restore.index("rm -rf")
