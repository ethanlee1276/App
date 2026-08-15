#!/usr/bin/env bash
# Back up the two databases that cannot be rebuilt.
#
#   ./deploy/backup.sh          # local snapshot
#   ./deploy/backup.sh --check  # restore the newest one and verify it
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

mkdir -p "$DEST"

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
  ls -1t "$DEST/${name}-"*.db.gz 2>/dev/null | tail -n "+$((KEEP + 1))" \
    | xargs -r rm -f
done

# OFFSITE IS THE PART THAT MATTERS. A backup on the same disk as the
# database survives a mistake and not a dead server, and the dead server
# is the case you are actually buying insurance against.
if [[ -n "${QB_BACKUP_REMOTE:-}" ]]; then
  echo "syncing to $QB_BACKUP_REMOTE"
  rsync -az --delete "$DEST/" "$QB_BACKUP_REMOTE/"
else
  echo "NOTE: QB_BACKUP_REMOTE is not set — these backups are on the same"
  echo "      disk as the databases, which does not survive losing the box."
fi
