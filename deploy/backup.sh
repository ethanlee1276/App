#!/usr/bin/env bash
# Back up the two databases that cannot be rebuilt.
#
#   ./deploy/backup.sh          # local snapshot
#   ./deploy/backup.sh --check        # restore the newest one and verify it
#   ./deploy/backup.sh --test-remote  # prove the offsite leg round-trips
#
# Nightly:
#   0 4 * * *  /srv/qellys/deploy/backup.sh >> /var/log/qellys-backup.log 2>&1
#
# WHAT IS AND IS NOT WORTH BACKING UP:
#   accounts.db  — other people's accounts. IRREPLACEABLE.
#   ledger.db    — the bet journal and the public record. IRREPLACEABLE:
#                  it is the evidence the whole positioning rests on.
#   history.db   — skipped. It is large and it rebuilds from `ingest.py`.
#   web/data/    — skipped. Rebuilds from the pipeline.
#
# THE BACKUP API RATHER THAN `cp`. Copying a live SQLite file gets you a
# torn snapshot when a write lands mid-copy — and with WAL enabled the
# copy can miss committed data sitting in the -wal file entirely. The
# backup API takes a consistent snapshot of a database being written to,
# which is the only kind this server has.
#
# Driven through PYTHON, not the `sqlite3` CLI. The CLI is a separate
# package that is not installed by default on Ubuntu — found by running
# this script, where it failed at `sqlite3: command not found`. Python is
# already a hard requirement for the app, so using it here means the
# backup cannot be the thing that is missing on the day it is needed.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
DEST="${QB_BACKUP_DIR:-$ROOT/backups}"
KEEP="${QB_BACKUP_KEEP:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DBS=("data/accounts.db" "data/ledger.db")

# /etc/qellys/env IS WHERE THIS IS CONFIGURED, and until 2026-08-22 this
# script was the one thing that never read it. `setenv.sh` writes there,
# systemd reads it, engine/secrets.py reads it for every Python tool —
# and this, the script the variable exists FOR, looked only at whatever
# shell happened to invoke it.
#
# So a correctly configured box reported "QB_BACKUP_REMOTE is not set" on
# every deploy, and `--check` answered "OFFSITE: none" — the one command
# whose whole job is to say whether the data is protected, saying no when
# the answer was yes. Ethan and I both read that as "it was never set up"
# and nearly redid an hour of work that was already done.
#
# The nightly cron was unaffected, because docs/BACKUPS.md puts the
# variable inline on the cron line — which is what disguised the bug.
#
# Same rule as engine/secrets.py: read-only, additive, and the ambient
# environment always wins, so the cron line and an explicit
# QB_BACKUP_REMOTE=... prefix still override the file.
#
# PARSED, NOT SOURCED. This file holds the Stripe secret key; `source`
# would execute whatever is in it and pull every secret into a shell
# that has no use for them. One `sed` for the one variable we want.
QB_ENV_FILE="${QB_ENV_FILE:-/etc/qellys/env}"
if [[ -z "${QB_BACKUP_REMOTE:-}" && -r "$QB_ENV_FILE" ]]; then
  _from_file="$(sed -n 's/^[[:space:]]*QB_BACKUP_REMOTE[[:space:]]*=[[:space:]]*//p' \
                "$QB_ENV_FILE" | tail -1)"
  _from_file="${_from_file%\"}"; _from_file="${_from_file#\"}"
  _from_file="${_from_file%\'}"; _from_file="${_from_file#\'}"
  [[ -n "$_from_file" ]] && export QB_BACKUP_REMOTE="$_from_file"
  unset _from_file
fi

mkdir -p "$DEST"

# OFFSITE IS THE PART THAT MATTERS. A backup on the same disk as the
# database survives a mistake and not a dead server, and the dead server
# is the case you are actually buying insurance against.
#
# TWO KINDS OF DESTINATION, because the natural one for a few megabytes
# of irreplaceable data is object storage and rsync cannot speak to it.
# rsync alone meant the only supported answer was "own a second machine",
# which for this is the wrong shape and the reason it stayed unset for
# weeks.
#
#   user@host:/path   -> rsync over ssh   (a box you own)
#   /mnt/somewhere    -> rsync            (an attached volume)
#   b2:bucket/path    -> rclone           (Backblaze, S3, Spaces, …)
#
# Told apart by the `@`: an rclone remote is `name:path` and never
# carries one, an ssh target always does.
remote_kind() {
  local r="$1"
  if [[ "$r" == *"@"* ]]; then echo rsync
  elif [[ "$r" =~ ^[A-Za-z0-9_-]+: ]]; then echo rclone
  else echo rsync
  fi
}

push_remote() {
  if [[ -z "${QB_BACKUP_REMOTE:-}" ]]; then
    echo "NOTE: QB_BACKUP_REMOTE is not set — these backups are on the same"
    echo "      disk as the databases, which does not survive losing the box."
    echo "      ./deploy/backup.sh --test-remote once you have set one."
    return 0
  fi
  local kind; kind="$(remote_kind "$QB_BACKUP_REMOTE")"
  echo "syncing to $QB_BACKUP_REMOTE ($kind)"
  # NOT `set -e`'s problem: a failed upload must be LOUD and must not
  # take the local backup with it. The snapshot on this disk is already
  # written and valid by the time we get here, and exiting non-zero from
  # the middle of a nightly cron is how you find out months later that
  # the whole job stopped.
  if [[ "$kind" == "rclone" ]]; then
    if ! command -v rclone >/dev/null 2>&1; then
      echo "  FAILED: rclone is not installed. apt install rclone"
      return 1
    fi
    rclone sync --config "${QB_RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}" \
      "$DEST/" "$QB_BACKUP_REMOTE/" || {
        echo "  FAILED: rclone could not sync. Backups are LOCAL ONLY."; return 1; }
  else
    rsync -az --delete "$DEST/" "$QB_BACKUP_REMOTE/" || {
      echo "  FAILED: rsync could not reach it. Backups are LOCAL ONLY."; return 1; }
  fi
  echo "  offsite copy updated"
}

if [[ "${1:-}" == "--test-remote" ]]; then
  # A REMOTE NOBODY HAS WRITTEN TO IS A HOPE, the same way an unrestored
  # backup is. This does the whole round trip on a throwaway file:
  # write, read back, compare, delete. It is the difference between
  # "configured" and "works".
  [[ -n "${QB_BACKUP_REMOTE:-}" ]] || {
    echo "QB_BACKUP_REMOTE is not set — nothing to test."; exit 1; }
  kind="$(remote_kind "$QB_BACKUP_REMOTE")"
  probe="$(mktemp -d)"; token="qellys-probe-$(date -u +%s)-$$"
  echo "$token" > "$probe/.qellys-probe"
  echo "testing $QB_BACKUP_REMOTE ($kind)"
  back="$(mktemp -d)"; rc=0
  if [[ "$kind" == "rclone" ]]; then
    command -v rclone >/dev/null 2>&1 || {
      echo "  rclone is not installed. apt install rclone"; exit 1; }
    CFG="${QB_RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}"
    rclone copy --config "$CFG" "$probe/.qellys-probe" "$QB_BACKUP_REMOTE/" \
      && rclone copy --config "$CFG" "$QB_BACKUP_REMOTE/.qellys-probe" "$back/" \
      || rc=1
    rclone delete --config "$CFG" "$QB_BACKUP_REMOTE/.qellys-probe" >/dev/null 2>&1 || true
  else
    rsync -az "$probe/.qellys-probe" "$QB_BACKUP_REMOTE/" \
      && rsync -az "$QB_BACKUP_REMOTE/.qellys-probe" "$back/" \
      || rc=1
    # CLEAN UP AFTER THE PROBE. The rclone branch deletes its own; this
    # one did not, so a test left a stray .qellys-probe sitting at the
    # destination. The next real backup would remove it — `rsync
    # --delete` drops anything not in the source — but "it gets tidied
    # eventually by a job that might not be running" is exactly the
    # assumption this whole command exists to stop making.
    if [[ "$QB_BACKUP_REMOTE" == *"@"*":"* ]]; then
      ssh "${QB_BACKUP_REMOTE%%:*}" \
        "rm -f '${QB_BACKUP_REMOTE#*:}/.qellys-probe'" >/dev/null 2>&1 || true
    else
      rm -f "$QB_BACKUP_REMOTE/.qellys-probe" 2>/dev/null || true
    fi
  fi
  if [[ "$rc" -eq 0 && "$(cat "$back/.qellys-probe" 2>/dev/null)" == "$token" ]]; then
    echo "  ok — wrote a file, read it back, and it matched."
    echo "  The offsite leg works. Nightly backups will land there."
  else
    echo "  FAILED — could not write and read back a file."
    echo "  Backups are LOCAL ONLY, which does not survive losing the box."
    rc=1
  fi
  rm -rf "$probe" "$back"
  exit "$rc"
fi

if [[ "${1:-}" == "--check" ]]; then
  # A BACKUP NOBODY HAS RESTORED IS A HOPE. This restores the newest copy
  # of each database into a scratch file and asks SQLite whether it is
  # intact — which is the difference between having backups and being
  # able to recover.
  fail=0
  for db in "${DBS[@]}"; do
    name="$(basename "$db" .db)"
    newest="$(ls -1t "$DEST/${name}-"*.db.gz 2>/dev/null | head -1 || true)"
    if [[ -z "$newest" ]]; then
      echo "MISSING: no backup of $name"; fail=1; continue
    fi
    tmp="$(mktemp)"
    gunzip -c "$newest" > "$tmp"
    if python3 - "$tmp" <<'PY'
import sqlite3, sys
# A corrupt backup is an EXPECTED outcome of this check, not a crash —
# reporting it as a stack trace buries the one line that matters.
try:
    c = sqlite3.connect(sys.argv[1])
    ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    n = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    c.close()
except sqlite3.DatabaseError as exc:
    print(f"  unreadable: {exc}")
    sys.exit(1)
print(f"  {n} table(s)")
sys.exit(0 if ok and n else 1)
PY
    then
      age="$(( ($(date +%s) - $(stat -c %Y "$newest" 2>/dev/null || stat -f %m "$newest")) / 3600 ))"
      echo "ok: $name  (${age}h old, $(basename "$newest"))"
      [[ "$age" -gt 48 ]] && { echo "  STALE — the nightly job is not running"; fail=1; }
    else
      echo "CORRUPT OR EMPTY: $newest"; fail=1
    fi
    rm -f "$tmp"
  done
  # AND THE OFFSITE LEG. A remote that quietly stopped accepting writes
  # looks exactly like one that is working, from here, until the day the
  # box dies — which is the only day it is asked for.
  if [[ -n "${QB_BACKUP_REMOTE:-}" ]]; then
    kind="$(remote_kind "$QB_BACKUP_REMOTE")"
    if [[ "$kind" == "rclone" ]] && command -v rclone >/dev/null 2>&1; then
      n="$(rclone lsf --config "${QB_RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}" \
            "$QB_BACKUP_REMOTE/" 2>/dev/null | grep -c '\.db\.gz$' || true)"
      if [[ "${n:-0}" -gt 0 ]]; then echo "ok: offsite  ($n file(s) at $QB_BACKUP_REMOTE)"
      else echo "OFFSITE EMPTY OR UNREACHABLE: $QB_BACKUP_REMOTE"; fail=1; fi
    else
      echo "offsite: $QB_BACKUP_REMOTE ($kind) — run --test-remote to prove it"
    fi
  else
    echo "OFFSITE: none. Backups are on the same disk as the databases."
    fail=1
  fi
  exit "$fail"
fi

for db in "${DBS[@]}"; do
  [[ -f "$ROOT/$db" ]] || { echo "skip (absent): $db"; continue; }
  name="$(basename "$db" .db)"
  out="$DEST/${name}-${STAMP}.db"
  python3 - "$ROOT/$db" "$out" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
d = sqlite3.connect(dst)
with d:
    s.backup(d)          # consistent even while the app is writing
d.close(); s.close()
PY
  gzip -f "$out"
  echo "backed up: $db -> ${out}.gz ($(du -h "${out}.gz" | cut -f1))"
done

# Keep the last N of each, drop the rest.
for db in "${DBS[@]}"; do
  name="$(basename "$db" .db)"
  # `|| true` BECAUSE OF `pipefail`. When a database has no backups yet —
  # a fresh install, or the first run after adding one — the glob matches
  # nothing, `ls` exits non-zero, pipefail propagates it and `set -e`
  # ends the script HERE. Everything below, including the offsite push,
  # was then silently skipped. The local backup had already been written,
  # so the run looked successful and exited 0.
  #
  # Found while testing the remote leg on a tree with only one of the two
  # databases present.
  ls -1t "$DEST/${name}-"*.db.gz 2>/dev/null | tail -n "+$((KEEP + 1))" \
    | xargs -r rm -f || true
done

# `|| true` BECAUSE push_remote IS THE LAST COMMAND. Its return code was
# becoming the script's exit status, so a down offsite remote failed the
# whole script — and deploy.sh runs this under `set -e` as step 2, BEFORE
# the pull. A transient rclone outage was enough to make every deploy die
# at "backing up" having shipped nothing. The local snapshot is already
# written and verified by this point; the offsite leg says FAILED loudly
# above and --verify reports an empty remote, which is the alarm path.
# (2026-08-24 six-day review.)
push_remote || true
