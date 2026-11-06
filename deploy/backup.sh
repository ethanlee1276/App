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
#   zeno.db      — the owner's own tickets. IRREPLACEABLE.
#   history.db   — BACKED UP since 2026-09-30 (audit P1-12). Most of it
#                  rebuilds from `ingest.py`, but not `odds_history`: the
#                  harvested and taped prices CLV is measured against were
#                  bought or caught once and are gone with the disk. Fewer
#                  copies kept (QB_BACKUP_KEEP_HISTORY, default 3), and
#                  QB_BACKUP_HISTORY=0 turns it off on a disk too small.
#   the evidence files — the free line history (every close the site has
#                  graded CLV against), the odds budget, the feed state and
#                  the daily chain heads (engine/ledger.record_heads), as
#                  dated tarballs beside the databases.
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
DBS=("data/accounts.db" "data/ledger.db" "data/zeno.db")
if [[ "${QB_BACKUP_HISTORY:-1}" != "0" ]]; then DBS+=("data/history.db"); fi
FILES=("data/cache/line_history.jsonl" "data/cache/odds_budget.json"
       "data/forecast_heads.jsonl" "data/feedstate")
KEEP_BIG="${QB_BACKUP_KEEP_HISTORY:-3}"

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

# ONE BACKUP AT A TIME, BOX-WIDE (2026-10-04). The droplet had TWO nightly
# jobs at 04:00 UTC — root's crontab (this file's own example line) and
# the qellys user's (deploy/README) — and each took a raw 5 GB copy of
# history.db at the same moment. The disk filled at 04:26 UTC and every
# board on the site stopped. A second run now waits its turn by skipping:
# a lock both users can take (flock on a read-only descriptor).
LOCK="${QB_BACKUP_LOCK:-/tmp/qellys-backup.lock}"
[[ -e "$LOCK" ]] || ( umask 000; : > "$LOCK" ) 2>/dev/null || true
if [[ -r "$LOCK" ]] && command -v flock >/dev/null 2>&1; then
  exec 9<"$LOCK"
  if ! flock -n 9; then
    echo "SKIPPED: another backup is running right now — one at a time"
    exit 0
  fi
fi

# A RAW COPY NEVER OUTLIVES THE RUN. The database is copied raw, then
# gzipped; a gzip that dies on a full disk leaves the raw copy (5 GB of
# history) behind, and the retention sweep only knew `.db.gz` — so the
# copies that filled the disk were never pruned. Whatever this run is
# holding raw is deleted on any exit.
RAW=""
CHECK_TMP=""
trap '[[ -n "$RAW" ]] && rm -f "$RAW" "$RAW.gz" "$RAW.gz.partial" 2>/dev/null; [[ -n "$CHECK_TMP" ]] && rm -f "$CHECK_TMP" 2>/dev/null; true' EXIT
#: The share of the disk a backup must leave free after itself.
FLOOR_PCT="${QB_BACKUP_FLOOR_PCT:-15}"
# A database this big or bigger is measured against the disk before it is
# copied or restored; the small ones are a few MB and never the risk.
MEASURE_MB="${QB_BACKUP_MEASURE_MB:-200}"

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

# THE OWNER'S DESK READS THIS (engine/ownerdesk.backups): when the last run
# finished and whether its offsite leg landed — ok, failed, or none when no
# remote is set — so a backup that stops reaching offsite says so on the
# desk and on the owner's phone instead of in a log nobody opens. Written
# beside the copies, atomically; it can never fail the run.
#
# AND WHY A FAILED ONE FAILED (2026-11-05). The desk said "the offsite leg
# failed" and sent the owner to the box for the reason, which was in this
# log and nowhere the desk reads. The tool's own last error line now rides
# along as `why` (the second argument): printable ASCII only, quotes and
# backslashes out, so it cannot break the JSON; any run of 20 or more
# letters and digits (a key, a token) blanked; 240 characters at most.
note_run() {
  { printf '{"at": %s, "offsite": "%s", "why": "%s"}\n' "$(date +%s)" "$1" "$(clean_why "${2:-}")" \
      > "$DEST/last_run.json.tmp" && mv -f "$DEST/last_run.json.tmp" "$DEST/last_run.json"; } 2>/dev/null || true
}

clean_why() {
  printf '%s' "$1" | LC_ALL=C tr -cd '\040-\176' | tr -d '"\\' \
    | sed -E 's#[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9:]{8} ##; s/[A-Za-z0-9]{20,}/[...]/g' | cut -c1-240
}

# The line in the tool's own output that says what went wrong: the last
# one naming an error, else its last line at all.
offsite_why() {
  local line=""
  [[ -n "${1:-}" && -r "$1" ]] || return 0
  line="$(grep -iE 'error|fail|denied|refused|forbidden|unauthori|no such|not found|quota|cap|timed? ?out' "$1" | tail -1 || true)"
  [[ -n "$line" ]] || line="$(grep -v '^[[:space:]]*$' "$1" | tail -1 || true)"
  printf '%s' "$line"
}

# A FULL BUCKET, MEASURED (2026-11-06). What the bucket holds after this
# run's deletes, and what this box keeps, so the cap can be set above the
# second (Backblaze: Caps & Alerts). One listing, only when the cap refused.
_gb() {
  [[ -n "${1:-}" ]] && python3 -c 'import sys; print("%.1f GB" % (int(sys.argv[1]) / 1e9))' "$1" 2>/dev/null \
    || echo "an unknown amount"
}
# OLD VERSIONS COUNT (B2). A file the sync deletes is HIDDEN in a B2 bucket,
# not removed, and it counts against the cap until the bucket's lifecycle
# rule removes it, so the size is read with --b2-versions (a backend flag
# every rclone accepts; it changes nothing on another kind of remote).
cap_sizes() {
  local cfg="$1" remote_b="" local_b=""
  remote_b="$(rclone size --json --b2-versions --config "$cfg" "$QB_BACKUP_REMOTE/" 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("bytes", ""))' 2>/dev/null || true)"
  local_b="$(du -sb "$DEST" 2>/dev/null | cut -f1 || true)"
  echo "  the bucket's storage cap is full: it holds $(_gb "$remote_b"), old versions included; this box keeps $(_gb "$local_b")."
  echo "  Raise the cap above what this box keeps, with a night's room (Backblaze: Caps & Alerts),"
  echo "  and let the bucket keep only the last version of a file (Backblaze: Lifecycle Settings)."
}

push_remote() {
  if [[ -z "${QB_BACKUP_REMOTE:-}" ]]; then
    echo "NOTE: QB_BACKUP_REMOTE is not set — these backups are on the same"
    echo "      disk as the databases, which does not survive losing the box."
    echo "      ./deploy/backup.sh --test-remote once you have set one."
    note_run none
    return 0
  fi
  local kind; kind="$(remote_kind "$QB_BACKUP_REMOTE")"
  echo "syncing to $QB_BACKUP_REMOTE ($kind)"
  # NOT `set -e`'s problem: a failed upload must be LOUD and must not
  # take the local backup with it. The snapshot on this disk is already
  # written and valid by the time we get here, and exiting non-zero from
  # the middle of a nightly cron is how you find out months later that
  # the whole job stopped.
  # The tool's complaints go to a file first, then into this log as before,
  # so the reason can travel to the desk (note_run). No file to be had, a
  # full disk say, and they come straight here the way they always did.
  local errf=""
  errf="$(mktemp 2>/dev/null)" || errf=""
  if [[ "$kind" == "rclone" ]]; then
    if ! command -v rclone >/dev/null 2>&1; then
      echo "  FAILED: rclone is not installed. apt install rclone"
      note_run failed "rclone is not installed on the box"
      [[ -n "$errf" ]] && rm -f "$errf"
      return 1
    fi
    local cfg="${QB_RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}"
    # DELETE BEFORE UPLOADING (2026-11-06). rclone's default deletes AFTER
    # the transfers, and not at all when one of them failed. So the first
    # night the bucket reached its storage cap, the copies this box had
    # already dropped stayed in it, the next night's upload met the same
    # cap, and the offsite copy stopped for good: "403
    # storage_cap_exceeded", every night from late October. Deleting first
    # frees what this box no longer keeps before anything is sent.
    # --max-delete guards the one case that would hurt: a local folder
    # emptied by accident would otherwise empty the bucket too. A normal
    # night deletes about seven files; the first night after this, the
    # backlog of a few weeks.
    if ! rclone sync --config "$cfg" --delete-before --max-delete "${QB_BACKUP_MAX_DELETE:-250}" \
        "$DEST/" "$QB_BACKUP_REMOTE/" 2>"${errf:-/dev/stderr}"; then
      [[ -n "$errf" ]] && cat "$errf"
      echo "  FAILED: rclone could not sync. Backups are LOCAL ONLY."
      if [[ -n "$errf" ]] && grep -qiE 'cap_exceeded|cap exceeded' "$errf"; then
        cap_sizes "$cfg"
      fi
      note_run failed "rclone: $(offsite_why "$errf")"
      [[ -n "$errf" ]] && rm -f "$errf"
      return 1
    fi
  else
    if ! rsync -az --delete "$DEST/" "$QB_BACKUP_REMOTE/" 2>"${errf:-/dev/stderr}"; then
      [[ -n "$errf" ]] && cat "$errf"
      echo "  FAILED: rsync could not reach it. Backups are LOCAL ONLY."
      note_run failed "rsync: $(offsite_why "$errf")"
      [[ -n "$errf" ]] && rm -f "$errf"
      return 1
    fi
  fi
  [[ -n "$errf" ]] && { cat "$errf"; rm -f "$errf"; }
  echo "  offsite copy updated"
  note_run ok
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
  #
  # AND IT MUST NEVER BE WHAT FILLS THE DISK (2026-11-01). The weekly run
  # at 04:30 UTC on a Sunday restored history.db (6.5 GB) into /tmp with
  # 4.5 GB free, filled the disk, died in gunzip, and left the half-written
  # copy where it was: seven hours of "No space left on device", the API
  # answering 502, nobody able to sign in. A second leftover from an
  # earlier Sunday was found beside it. So the restore measures first and
  # skips a database the disk cannot hold with FLOOR_PCT still free; the
  # scratch copy sits beside the backups, not in /tmp; a killed run's
  # leftovers are swept here; and the trap above removes it however the
  # run ends.
  fail=0
  rm -f "$DEST"/.check-* 2>/dev/null || true
  for db in "${DBS[@]}"; do
    name="$(basename "$db" .db)"
    newest="$(ls -1t "$DEST/${name}-"*.db.gz 2>/dev/null | head -1 || true)"
    # A database this box has never had (zeno.db before the first import)
    # and no backup of it either: nothing was lost, so nothing is missing.
    if [[ -z "$newest" && ! -f "$ROOT/$db" ]]; then
      echo "skip (never here): $db"; continue
    fi
    if [[ -z "$newest" ]]; then
      echo "MISSING: no backup of $name"; fail=1; continue
    fi
    # The restore is the database's full size: the live file says how big,
    # or six times the archive when there is no live file to ask.
    size_mb=$(( $(stat -c %s "$ROOT/$db" 2>/dev/null || stat -f %z "$ROOT/$db" 2>/dev/null || echo 0) / 1048576 ))
    if [[ "$size_mb" -le 0 ]]; then
      size_mb=$(( $(stat -c %s "$newest" 2>/dev/null || stat -f %z "$newest") * 6 / 1048576 ))
    fi
    if [[ "$size_mb" -ge "$MEASURE_MB" ]]; then
      free_mb=$(df -Pm "$DEST" | awk 'NR==2 {print $4}')
      total_mb=$(df -Pm "$DEST" | awk 'NR==2 {print $2}')
      if [[ $(( ${free_mb:-0} - size_mb )) -lt $(( ${total_mb:-0} * FLOOR_PCT / 100 )) ]]; then
        echo "NOT CHECKED: $name — restoring it needs about ${size_mb} MB and only ${free_mb} MB is free (the disk keeps ${FLOOR_PCT}% free); free some space and run --check again"
        continue
      fi
    fi
    CHECK_TMP="$(mktemp "$DEST/.check-${name}-XXXXXX")"
    gunzip -c "$newest" > "$CHECK_TMP"
    # THE LIVE FILE IS PASSED IN TOO, so the backup can be checked against
    # what it is supposed to be a copy OF. Absent when restoring on a
    # different box, which is fine and says so rather than failing.
    if KEEP_HINT="$KEEP" python3 - "$CHECK_TMP" "$ROOT/$db" <<'PYCHECK'
import os
import sqlite3
import sys

# A corrupt backup is an EXPECTED outcome of this check, not a crash —
# reporting it as a stack trace buries the one line that matters.
def counts(path):
    """``{table: rows}`` for a database, or None if it cannot be read."""
    try:
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = {}
        for t in names:
            out[t] = c.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        c.close()
        return out
    except sqlite3.DatabaseError:
        return None

try:
    c = sqlite3.connect(sys.argv[1])
    ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    c.close()
except sqlite3.DatabaseError as exc:
    print("  unreadable: %s" % exc)
    sys.exit(1)

back = counts(sys.argv[1])
if back is None:
    print("  unreadable")
    sys.exit(1)
if not ok:
    print("  integrity_check failed")
    sys.exit(1)
if not back:
    print("  no tables at all")
    sys.exit(1)

# WHAT IS ACTUALLY IN IT, not how many tables it has. The line here used
# to print "3 table(s)" and pass, which is the whole reason this section
# was rewritten: a backup of a ZEROED database has a perfect schema and a
# clean integrity_check. Demonstrated 2026-09-09 — five users in the live
# file, none in the backup, and this printed "ok: accounts".
big = sorted(back.items(), key=lambda kv: -kv[1])[:4]
print("  " + ", ".join("%d %s" % (n, t) for t, n in big)
      + (" (+%d more)" % (len(back) - len(big)) if len(back) > len(big) else ""))

live = counts(sys.argv[2]) if os.path.exists(sys.argv[2]) else None
if live is None:
    print("  (no live copy here to compare against — structure only)")
    sys.exit(0)

# THE ONE COMPARISON THAT CANNOT CRY WOLF. A backup is always older than
# the live file, so holding FEWER rows is normal, and alarming on that
# would fire every single night until nobody read this output any more. A
# table with rows in the live database and NONE in the backup is not lag;
# it is a faithful copy of something that was already gone.
lost = sorted(t for t, n in live.items() if n and not back.get(t, 0))
if lost:
    print("  EMPTY IN THE BACKUP but not live: " + ", ".join(lost))
    print("  That is what a zeroed database looks like once it has been")
    print("  backed up. The last good copy is %s nightlies from being"
          % os.environ.get("KEEP_HINT", "?"))
    print("  dropped by the retention sweep — go and find it now.")
    sys.exit(1)
sys.exit(0)
PYCHECK
    then
      age="$(( ($(date +%s) - $(stat -c %Y "$newest" 2>/dev/null || stat -f %m "$newest")) / 3600 ))"
      echo "ok: $name  (${age}h old, $(basename "$newest"))"
      [[ "$age" -gt 48 ]] && { echo "  STALE — the nightly job is not running"; fail=1; }
    else
      echo "CORRUPT OR EMPTY: $newest"; fail=1
    fi
    rm -f "$CHECK_TMP"; CHECK_TMP=""
  done
  # THE EVIDENCE FILES: each present file has a tarball that lists.
  for f in "${FILES[@]}"; do
    [[ -e "$ROOT/$f" ]] || continue
    tag="$(basename "$f" | tr '.' '_')"
    newest="$(ls -1t "$DEST/${tag}-"*.tar.gz 2>/dev/null | head -1 || true)"
    if [[ -z "$newest" ]]; then echo "MISSING: no backup of $f"; fail=1
    elif tar -tzf "$newest" >/dev/null 2>&1; then echo "ok: $f  ($(basename "$newest"))"
    else echo "CORRUPT: $newest"; fail=1; fi
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
  # A BIG FILE SAYS IT IS STARTING, AND CHECKS THE DISK FIRST. history.db
  # runs to gigabytes; on the droplet its copy and gzip take minutes with
  # nothing printed, which read as a frozen deploy (2026-10-03), and the
  # raw copy needs its own size free on a disk that has filled before
  # (2026-10-01). Skipped, loudly, when it would not fit.
  size_mb=$(( $(stat -c %s "$ROOT/$db" 2>/dev/null || stat -f %z "$ROOT/$db") / 1048576 ))
  if [[ "$size_mb" -ge "$MEASURE_MB" ]]; then
    free_mb=$(df -Pm "$DEST" | awk 'NR==2 {print $4}')
    total_mb=$(df -Pm "$DEST" | awk 'NR==2 {print $2}')
    # Room for the raw copy and its gzip, AND the disk still FLOOR_PCT
    # free afterwards — a backup that leaves the site no room to build
    # its boards is the outage it was meant to insure against.
    if [[ "${free_mb:-0}" -lt $(( size_mb * 3 / 2 )) ]] || \
       [[ $(( ${free_mb:-0} - size_mb * 3 / 2 )) -lt $(( ${total_mb:-0} * FLOOR_PCT / 100 )) ]]; then
      echo "SKIPPED: $db is ${size_mb} MB and only ${free_mb} MB is free — the disk must keep ${FLOOR_PCT}% free after a backup; free some space first"
      continue
    fi
    echo "backing up $db (${size_mb} MB — this takes a few minutes, nothing prints until it is done)"
  fi
  RAW="$out"
  python3 - "$ROOT/$db" "$out" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
d = sqlite3.connect(dst)
with d:
    s.backup(d)          # consistent even while the app is writing
d.close(); s.close()
PY
  # The fastest gzip for the big one: its size is the cost that matters
  # on one core, and level 1 still shrinks a database by most of the way.
  if [[ "$size_mb" -ge "$MEASURE_MB" ]]; then gzip -1 -f "$out"; else gzip -f "$out"; fi
  rm -f "$out"; RAW=""
  echo "backed up: $db -> ${out}.gz ($(du -h "${out}.gz" | cut -f1))"
done

for f in "${FILES[@]}"; do
  [[ -e "$ROOT/$f" ]] || continue
  tag="$(basename "$f" | tr '.' '_')"
  out="$DEST/${tag}-${STAMP}.tar.gz"
  tar -czf "$out" -C "$ROOT" "$f"
  echo "backed up: $f -> $out ($(du -h "$out" | cut -f1))"
done
for f in "${FILES[@]}"; do
  tag="$(basename "$f" | tr '.' '_')"
  ls -1t "$DEST/${tag}-"*.tar.gz 2>/dev/null | tail -n "+$((KEEP_BIG + 1))" \
    | xargs -r rm -f || true
done

# Keep the last N of each, drop the rest.
for db in "${DBS[@]}"; do
  name="$(basename "$db" .db)"
  keep="$KEEP"; [[ "$name" == "history" ]] && keep="$KEEP_BIG"
  # `|| true` BECAUSE OF `pipefail`. When a database has no backups yet —
  # a fresh install, or the first run after adding one — the glob matches
  # nothing, `ls` exits non-zero, pipefail propagates it and `set -e`
  # ends the script HERE. Everything below, including the offsite push,
  # was then silently skipped. The local backup had already been written,
  # so the run looked successful and exited 0.
  #
  # Found while testing the remote leg on a tree with only one of the two
  # databases present.
  ls -1t "$DEST/${name}-"*.db.gz 2>/dev/null | tail -n "+$((keep + 1))" \
    | xargs -r rm -f || true
done
# Raw copies an older run left when its gzip died — every database this
# script has ever backed up, whether or not this run covers it, and
# stamped names only: a hand-made `ledger-before-void-….db` is someone's,
# and stays.
for name in accounts ledger zeno history; do
  rm -f "$DEST/${name}-"20[0-9][0-9][01][0-9][0-3][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.db 2>/dev/null || true
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
