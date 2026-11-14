# Scheduled backups to the NAS (#31)

Date: 2026-11-14
Issue: #31. Related: #18 (MinIO image move), #59 (first bucket backup).

## Goal

The Pi has a single disk. Today the photos have no scheduled backup, and
the database backups never leave the Pi. After this change:

- Every night the databases, the photos and the apps' `.env` secrets are
  copied to the home NAS, in plain files (secrets encrypted).
- A failed or missing backup reaches a phone via ntfy; a weekly "all good"
  message makes silence itself a warning.
- Once a month the newest backups are restored from the NAS into throwaway
  containers and checked, and the result is reported.
- The README says where the backups are and how to restore each part.

## Decisions

1. **NAS:** the existing home NAS share the Pi already mounts over SMB at
   `/mnt/nas/alan` (an automount, owner `dad`). Backups go to a new folder
   in it, `fordDbs-backups/`. No new NAS user or share. The NAS has no
   snapshots, so the job only adds dated copies and its retention can never
   empty a folder. (A second, off-site copy is out of scope.)
2. **The Pi pushes.** A systemd timer runs a script from this repo.
3. **Alerts:** ntfy (public ntfy.sh, long random topic kept only in the
   Pi's config), on every failure plus a Sunday summary. Messages carry
   step names, counts and sizes only, never family data.
4. **Encryption:** only the secrets bundle, with `age`, to a public key in
   the config. The private key lives in the user's password manager, never
   on the Pi. Photos and dumps stay plain, so they open without a key.
5. **Language:** Python 3 standard library only (the Pi has 3.13), tested
   with pytest in CI. External commands go through one runner that tests
   replace with a fake.

## NAS layout

```
fordDbs-backups/
  postgres/forddbs/{daily,weekly,monthly,last}/…sql.gz
  postgres/chore_tracker/{daily,weekly,monthly,last}/…sql.gz
  photos/files/…                   plain copy of the bucket, never deletes
  photos/volume/YYYY-MM.tar.gz     monthly exact copy of the MinIO volume
  secrets/YYYY-MM-DD.tar.age       all apps' .env files, age-encrypted
  status/last-success.json         time, counts, sizes; no secrets
```

Retention:

- `postgres/`: mirrors the Pi's `postgres-backup-local` folders
  (`~/docker/postgres-backups/backups/<db>/`, 7 daily, 4 weekly,
  6 monthly), deletions included, but see the guard below.
- `photos/files/`: never deletes; a photo deleted in the app stays.
- `photos/volume/`: newest 6.
- `secrets/`: everything from the last 30 days, plus the newest file of
  each of the last 6 months.
- Retention never deletes the newest file of a folder, and deletes nothing
  in a folder holding fewer files than the rule keeps.

## Backup job (`ops/backup/backup.py`, `fordDbs-backup.timer`)

Daily at 03:30 Europe/Berlin (after the midnight dumps), as `dad`,
`Persistent=true`, guarded by a lock file. Each step runs even if an
earlier one failed; the run fails if any step failed. Output goes to the
journal.

1. **Checks.** The backup root's mount point is a CIFS/SMB mount
   (`findmnt` lists `cifs` or `smb3`; on the automount it lists `autofs`
   first), never a plain folder on the Pi's disk. Only this check stops
   every later step. A separate `minio` check (MinIO answers, NAS free
   space at least 2 × the bucket size) gates only the photo and volume
   steps, so the databases and secrets are still copied when MinIO is
   down.
2. **Databases.** For each database folder: fail if the newest
   `*.sql.gz` in `last/` (or `daily/`) is older than 36 h. Guard: if the
   source `daily/` folder holds no dump, skip the copy and fail, so a
   broken source never deletes NAS copies. Otherwise
   `rsync -rt --delete --no-links` the folder (the share holds no
   symlinks, owners or modes; the `-latest` symlink is skipped).
3. **Photos.** `mc mirror` without `--remove` or `--overwrite` from the
   bucket to `photos/files/` (an existing file that differs is left alone,
   and the size check below reports it), logged
   in as a read-only MinIO user `backup-reader` (policy `readonly`, bucket
   `family-photos`), passed to `mc` only through the `MC_HOST_backup`
   environment variable, so the job never writes an mc config file. Then
   verify: every object in the bucket exists in `photos/files/` with the
   same size.
4. **Volume copy.** If `photos/volume/<this month>.tar.gz` is missing:
   tar the whole volume read-only through `forddbs-api`, leaving out
   `.minio.sys/tmp`, `.minio.sys/multipart` and `.minio.sys/config`
   (MinIO's users and their secrets: secrets are only stored encrypted).
   MinIO is live, so tar's exit 1 ("file changed") is accepted; the copy
   counts as good when it lists one `xl.meta` per bucket object. Written
   to a temporary name, then renamed.
5. **Secrets.** Pack `~/docker/*/.env` (skipping folders whose name
   contains `.bak`) into a tar, pipe it through `age -r <public key>` to a
   temporary name, rename.
6. **Retention** for `photos/volume/` and `secrets/` as above.
7. **Status.** Write `status/last-success.json` only when every step
   passed: `{finished_at, databases: {name: newest_dump}, photos:
   {objects, bytes}, volume: name, secrets: name}`.

Every file is written under a temporary name in the target folder and
renamed when complete. A SIGTERM (systemd timeout or shutdown) or crash
still sends a failure alert. The restore test waits up to 90 minutes for
a running backup and reports "skipped" if it can't start, and removes
leftover `restoretest-*` containers before it starts as well as after.
A failing command's last stderr lines go to the journal, never to ntfy.

**Notifications.** Failure: `fordDbs backup failed: <steps> (see journalctl
-u fordDbs-backup)`, priority high. Sunday runs that pass: `fordDbs backup
OK: 2 databases, <n> photos (<size>), last volume <YYYY-MM>`. If ntfy
itself can't be reached, the journal still has the result.

**Config** (`~/.config/fordDbs-backup/env`, mode 600, example in the repo):
`BACKUP_ROOT`, `NTFY_URL`, `AGE_RECIPIENT`, `MINIO_ALIAS_URL`,
`BACKUP_READER_KEY`/`SECRET`, paths with defaults matching the Pi.

## Restore test (`ops/backup/restore_test.py`, `fordDbs-restore-test.timer`)

First Sunday of the month, 04:30. Only throwaway containers with no host
ports, named `restoretest-*`, removed in a `finally` even on failure.

- **Databases:** newest dump of each database from the NAS into a
  `postgres:15-alpine` container. Pass if the restore exits 0 and, for
  key tables (forddbs: `users`, `photos`, `etf_transactions`;
  chore_tracker: `user`, `chore`, `completion`), the restored row
  count is > 0 when the live count is > 0, and not above the live count.
- **Photos:** newest volume copy from the NAS into a MinIO container
  (same image and root credentials as production, on a temporary volume).
  Pass if its object count equals the archive's and every object's
  checksum matches the file in `photos/files/`.
- **Secrets:** newest file starts with the `age` header and is not empty.
  (Decryption is checked by hand on the Mac at setup, then yearly.)
- Report to ntfy either way: `restore test passed: 2 databases, <n>
  photos` or the failing part.

## Files

`ops/backup/backup.py`, `ops/backup/restore_test.py`,
`ops/backup/common.py` (runner, config, notify, safe writes, retention),
`ops/backup/systemd/*.service|*.timer`, `ops/backup/env.example`,
`ops/backup/install.sh`, tests under `tests/ops/`, README section.

## Testing

- Retention: daily/monthly selection, never deletes the newest, nothing
  deleted below the keep count.
- Guards: empty source folder skips the copy and fails; stale dump (> 36 h)
  fails; backup root that is not a CIFS mount fails before writing.
- Safe writes: a failed write leaves no file under the final name.
- Steps continue after an earlier failure; overall result is failure.
- Photo verification: missing or different-size file is reported.
- Volume step skipped when this month's copy exists.
- Notifications: failure text names the failed steps; Sunday summary only
  on Sundays and only when everything passed; no data beyond counts.
- Restore test: containers are removed even when a check fails; table
  count rules.
- Real commands are checked on the Pi during rollout (first run by hand,
  then the restore test once).

## Rollout

1. User: `age-keygen` on the Mac, private key into the password manager,
   public key to Claude; install the ntfy app and subscribe to the topic.
2. With the user's OK: create the MinIO user `backup-reader` (readonly on
   `family-photos`) in production.
3. Install `age` on the Pi; `chmod 600 ~/docker/chore-tracker/.env`
   (currently readable by all users); write the config; run
   `install.sh`; run the backup by hand; inspect the NAS folder; run the
   restore test once.
4. User: decrypt the secrets file once on the Mac.
5. README: where backups live and how to restore a database, the photos
   (from the volume copy or from the plain files) and the secrets.

Rollback: disable both timers; nothing in the apps changes.

## Out of scope

Data of finance-hub, steuer-hub and the trading bot (separate issue); an
off-site copy (USB disk or cloud); the unused `postgres-backups/backup/`
folder.
