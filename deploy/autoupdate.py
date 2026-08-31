#!/usr/bin/env python3
"""Pull pushed code and restart the site on change. Run by the timer.

WHY THIS IS A SEPARATE PROCESS AND NOT THE APP. launch.py grew an
in-process `--auto-update` on 2026-08-31, and on the droplet it failed
silently every five minutes for an hour while three fixes sat pushed:
the app runs as the unprivileged `qellys` user under
`ProtectSystem=strict`, so the checkout — `.git` and every source file —
is READ-ONLY to it, and the deploy key lives in root's home behind
`ProtectHome=true`. In-process auto-update could never have worked on
that box, and weakening the sandbox so a public web process can rewrite
its own code is the wrong trade. The thing that already safely rewrites
this checkout is the deploy, run by root — so the auto-update is the
same shape: a root oneshot on a timer, pull --ff-only, restart the
service only when the code actually moved. The app keeps every line of
its hardening.

Every run writes data/autoupdate.json — timestamp, ok, commit, note —
because the last updater's failures were invisible by design ("offline
is the common case and not worth shouting about"; a permanently broken
pull looks exactly like offline). `launch.py --boards` reads that file,
so "is auto-update working, and if not why" is on the one screen that
answers everything else. The state lives in data/ (not web/data/) so
git error text is never served to the public.

Same guards as the in-process version, same reasons:
  * --ff-only — never merges, never rebases. Divergence stops it.
  * a dirty tree is someone's work in progress; skip and say so.
  * stays on the branch already checked out.

Run by deploy/qellys-update.timer; by hand for a one-off:
    sudo python3 /srv/qellys/deploy/autoupdate.py
"""

import argparse
import datetime
import json
import os
import subprocess
import sys


def _git(repo, *args):
    try:
        p = subprocess.run(("git", "-C", repo) + args, capture_output=True,
                           text=True, timeout=120)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception as exc:                    # noqa: BLE001 — git missing/hung
        return False, str(exc)


def _record(repo, ok, note):
    """data/autoupdate.json — atomically, one small fact per run."""
    _, commit = _git(repo, "rev-parse", "--short", "HEAD")
    path = os.path.join(repo, "data", "autoupdate.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"at": datetime.datetime.now().isoformat(timespec="seconds"),
                   "at_epoch": round(datetime.datetime.now().timestamp()),
                   "ok": bool(ok), "commit": commit,
                   # The tail is enough to name the fault and short enough
                   # that a stack of them cannot grow the file.
                   "note": str(note)[-400:]}, f)
    os.replace(tmp, path)
    print(("ok: " if ok else "FAILED: ") + str(note))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/srv/qellys")
    ap.add_argument("--service", default="qellys")
    args = ap.parse_args()
    repo = args.repo

    ok, dirty = _git(repo, "status", "--porcelain")
    if not ok:
        _record(repo, False, f"git status failed: {dirty}")
        return 0
    if dirty:
        _record(repo, False, "working tree dirty — pull skipped (uncommitted "
                             "work is someone's, not an obstacle)")
        return 0
    ok, branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if not ok or not branch or branch == "HEAD":
        _record(repo, False, f"not on a branch: {branch}")
        return 0
    _, before = _git(repo, "rev-parse", "--short", "HEAD")
    ok, out = _git(repo, "pull", "--ff-only", "origin", branch)
    if not ok:
        _record(repo, False, f"pull failed: {out}")
        return 0
    _, after = _git(repo, "rev-parse", "--short", "HEAD")
    if after == before:
        _record(repo, True, "up to date")
        return 0
    # Restart AFTER recording would report a restart that hasn't happened;
    # record what was done, with the restart's own result on the line.
    try:
        subprocess.run(("systemctl", "restart", args.service),
                       check=True, timeout=120)
        _record(repo, True, f"pulled {before}..{after} and restarted "
                            f"{args.service}")
    except Exception as exc:                                  # noqa: BLE001
        _record(repo, False, f"pulled {before}..{after} but the restart "
                             f"failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
