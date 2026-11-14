#!/usr/bin/env bash
# Install and enable the NAS backup timers (#31). Run on the Pi from the
# repo checkout: ops/backup/install.sh
set -euo pipefail

config="$HOME/.config/fordDbs-backup/env"
if [[ ! -f "$config" ]]; then
  echo "Missing $config (copy ops/backup/env.example and fill it in)." >&2
  exit 1
fi
if [[ "$(stat -c %a "$config")" != "600" ]]; then
  echo "$config must be mode 600 (chmod 600 $config)." >&2
  exit 1
fi
for tool in rsync mc age docker findmnt; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
# Debian's "mc" package is Midnight Commander; the job needs the MinIO
# client, on systemd's PATH (e.g. /usr/local/bin/mc).
if ! mc --version 2>/dev/null | grep -qi minio; then
  echo "mc is not the MinIO client (install it to /usr/local/bin/mc)." >&2
  exit 1
fi

here="$(cd "$(dirname "$0")" && pwd)"
for unit in fordDbs-backup.service fordDbs-backup.timer \
            fordDbs-restore-test.service fordDbs-restore-test.timer; do
  sudo install -m 644 "$here/systemd/$unit" "/etc/systemd/system/$unit"
done
sudo systemctl daemon-reload
sudo systemctl enable --now fordDbs-backup.timer fordDbs-restore-test.timer
systemctl list-timers --no-pager 'fordDbs-*'
