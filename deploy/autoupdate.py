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
service only when code the site runs actually moved (a push of only docs
or tests is pulled with no restart: NO_RESTART below). The app keeps every
line of its hardening.

Every run writes data/autoupdate.json — timestamp, ok, commit, note —
because the last updater's failures were invisible by design ("offline
is the common case and not worth shouting about"; a permanently broken
pull looks exactly like offline). `launch.py --boards` reads that file,
so "is auto-update working, and if not why" is on the one screen that
answers everything else. The state lives in data/ (not web/data/) so
git error text is never served to the public.

Same guards as the in-process version, same reasons:
  * --ff-only — never merges, never rebases. Divergence stops it.
  * MODIFIED TRACKED FILES are someone's work in progress; skip, and
    name the files, because "dirty" without a path costs a round trip
    over SSH to learn what one porcelain line would have said.
  * untracked files do NOT block the pull. They cannot be harmed by a
    fast-forward — git itself refuses any pull that would overwrite an
    untracked file — and treating them as dirt is how this updater
    jammed itself on the droplet on 2026-08-31: one stray unignored
    file, and every five-minute run for a day skipped a clean pull it
    could have taken safely. They are still worth a word (each one is a
    .gitignore hole, one `git add -A` from a public leak), so the note
    lists them without stopping for them.
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
import time


def _git(repo, *args):
    try:
        p = subprocess.run(("git", "-C", repo) + args, capture_output=True,
                           text=True, timeout=120)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception as exc:                    # noqa: BLE001 — git missing/hung
        return False, str(exc)


def _named(paths, cap=5):
    """The first few paths, and an honest count of the rest."""
    shown = ", ".join(paths[:cap])
    more = len(paths) - cap
    return shown + (f" (+{more} more)" if more > 0 else "")


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


#: Who runs code from the pulled checkout (audit 2026-09-30, P1-7). This
#: script is root — it needs the deploy key and systemctl — and it ran the
#: trim straight from what it had just pulled, so any commit on the branch
#: executed as root within five minutes.
APP_USER = os.environ.get("QB_APP_USER", "qellys")


def _user_exists(name) -> bool:
    try:
        import pwd
        pwd.getpwnam(name)
        return True
    except (ImportError, KeyError):
        return False


def _as_app_user(args, euid=None, user_exists=_user_exists, have=None):
    """``args`` wrapped in `runuser -u <app user> --` when this is root and
    the user exists; unchanged otherwise (a laptop, a scratch box)."""
    import shutil
    euid = os.geteuid() if euid is None and hasattr(os, "geteuid") else euid
    have = have or (lambda b: shutil.which(b) is not None)
    if euid == 0 and user_exists(APP_USER) and have("runuser"):
        return ["runuser", "-u", APP_USER, "--"] + list(args)
    return list(args)


def _hand_to_app_user(repo) -> None:
    """The trim's output directory, owned by the app user, so the trim can
    write it without root. Best effort: a failure leaves the originals
    served, which is where the site was before the trim existed."""
    if not (hasattr(os, "geteuid") and os.geteuid() == 0 and _user_exists(APP_USER)):
        return
    try:
        import pwd
        pw = pwd.getpwnam(APP_USER)
        top = os.path.join(repo, "web", "min")
        for sub in ("", "js", "css"):
            d = os.path.join(top, sub)
            os.makedirs(d, exist_ok=True)
            os.chown(d, pw.pw_uid, pw.pw_gid)
            for name in os.listdir(d):
                f = os.path.join(d, name)
                if os.path.isfile(f):
                    os.chown(f, pw.pw_uid, pw.pw_gid)
    except OSError:
        pass


def _setting(name, default=""):
    """One value: the environment first, then /etc/qellys/env — read for
    that one key, never sourced (it holds the payment keys; the update
    unit deliberately does not load it). Same rule as deploy/backup.sh."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(os.environ.get("QB_ENV_FILE", "/etc/qellys/env"), encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.strip().partition("=")
                if k.strip() == name:
                    return v.strip().strip("'\"") or default
    except OSError:
        pass
    return default


def _allowed(repo, mode) -> str:
    """Why FETCH_HEAD may not be deployed, or "" when it may.

    QB_UPDATE_REQUIRE (audit P1-7): ``off`` (default) takes any head on the
    branch — the ship-on-green pipeline; ``tag`` takes only a head that a
    ``deploy-*`` tag points at; ``signed`` only a head `git verify-commit`
    accepts against the keys in root's keyring."""
    mode = (mode or "off").strip().lower()
    if mode in ("", "off"):
        return ""
    if mode == "tag":
        _git(repo, "fetch", "--tags", "origin")
        ok, tags = _git(repo, "tag", "--points-at", "FETCH_HEAD", "--list", "deploy-*")
        return "" if ok and tags.strip() else "no deploy-* tag on the pushed head"
    if mode == "signed":
        ok, out = _git(repo, "verify-commit", "FETCH_HEAD")
        return "" if ok else "the pushed head is not signed by an allowed key"
    return f"unknown QB_UPDATE_REQUIRE={mode!r} — refusing to guess"


def _trim(repo, clear=False) -> str:
    """The comment-stripped shell (engine/shrink.py): clear it, or build it.

    Empty when there is nothing to say — a checkout without the module (an
    old commit, the tests' scratch repos) or a build that changed nothing.
    Never fatal: a failed trim leaves the originals served, which is where
    the site was before the trim existed.
    """
    if not os.path.isfile(os.path.join(repo, "engine", "shrink.py")):
        return ""
    args = [sys.executable, "-m", "engine.shrink", "--web", os.path.join(repo, "web")]
    if clear:
        args.append("--clear")
    _hand_to_app_user(repo)
    try:
        p = subprocess.run(_as_app_user(args), cwd=repo, capture_output=True, text=True,
                           timeout=120)
    except Exception as exc:                                  # noqa: BLE001
        return f" · trim failed: {exc}"
    if p.returncode != 0:
        return f" · trim failed: {(p.stderr or p.stdout).strip()[-200:]}"
    if clear:
        return ""
    said = [ln for ln in p.stdout.splitlines()
            if ln.strip() and not ln.endswith(": current")]
    # A count, and the files it could not trim in full: the note keeps its
    # last 400 characters, and fourteen files' sizes pushed the run's own
    # word ("restarted") out of it (2026-10-24, the rooms split).
    left = [ln for ln in said if "served as written" in ln]
    done = len(said) - len(left)
    return ((f" · trimmed {done} file(s)" if done else "")
            + (f" · {'; '.join(left)}" if left else ""))


#: THE RESTART WAITS FOR THE BOARD SWEEP IN PROGRESS (2026-10-14). This
#: restarted the unit the moment a push landed, and a restart kills the
#: sweep and every build in it. Thirty pushes between one evening and the
#: next noon, most under an hour apart, meant the boards late in the
#: sweep's order were never rebuilt; past an hour old the page takes a
#: board's picks off (web/js/app.js `picksWithheld`), and Ethan found every
#: board empty. Now the app says whether a sweep is running
#: (data/cache/sweep.json, written by launch.py `_note_sweep`); while one
#: is, the new code is pulled and served as files (the page, the trimmed
#: shell) but the restart waits, and data/cache/restart_wanted.json tells
#: the app to start no new sweep, so the wait ends at the sweep's end. An
#: app too old to say restarts at once, as before.
SWEEP_STATE = ("data", "cache", "sweep.json")
RESTART_WANT = ("data", "cache", "restart_wanted.json")
#: The longest new code waits for a restart, counted from the first run
#: that pulled it. Past it the unit restarts mid-sweep, as it always did.
RESTART_WAIT_MAX_S = 45 * 60
#: A sweep said to be running for longer than this is stuck, or its writer
#: died without saying so: not waited on.
SWEEP_STALE_S = 50 * 60


#: A PULL THAT CHANGES NOTHING THE SITE RUNS IS NOT RESTARTED INTO
#: (2026-10-14). Every pull restarted the unit, the runbook's included, and
#: a restart costs the boards their sweep: the restart waits for the one in
#: progress, then the new process rebuilds from the NFL down. Ethan's Status
#: page that afternoon, after four pushes in ninety minutes, two of them
#: docs: every board but the NFL's red. Nothing under these paths is loaded
#: by the running site at start (what docs/ holds that it reads at all, it
#: reads when asked), so the pull alone delivers them. launch.py NO_RESTART
#: is the same rule, for `--boards`.
NO_RESTART = ("docs/", "tests/", "audit/")


def _runs_nothing(path) -> bool:
    path = str(path or "").strip()
    return bool(path) and (path.startswith(NO_RESTART)
                           or ("/" not in path and path.lower().endswith(".md")))


def _needs_restart(repo, before, after) -> bool:
    """Do the commits from ``before`` to ``after`` touch anything the site
    runs? True whenever git cannot say, or names no path at all."""
    ok, out = _git(repo, "diff", "--name-only", before, after)
    paths = [p for p in out.splitlines() if p.strip()] if ok else None
    return not paths or not all(_runs_nothing(p) for p in paths)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _same_commit(a, b) -> bool:
    """Two short hashes of one commit: the app's and git's abbreviations
    may differ in length, never in their common prefix."""
    a, b = str(a or "").strip(), str(b or "").strip()
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def _sweep_running(repo, now):
    """``(seconds the board sweep in progress has run, the commit the app
    is serving)``; the seconds are None when a restart need not wait —
    no sweep running, an app too old to say, a writer that is gone, or a
    sweep past SWEEP_STALE_S."""
    st = _read_json(os.path.join(repo, *SWEEP_STATE))
    if not st or st.get("handshake") != 1:
        return None, ""
    serving = str(st.get("commit") or "")
    if not st.get("running") or not _pid_alive(st.get("pid")):
        return None, serving
    try:
        ran = now - float(st.get("started"))
    except (TypeError, ValueError):
        return None, serving
    if ran < 0 or ran > SWEEP_STALE_S:
        return None, serving
    return ran, serving


def _restart_or_wait(repo, service, before, after, wanted, stray, trim):
    """Restart into ``after`` now, or leave a request and wait for the
    sweep in progress. Records what it did. Never raises."""
    now = time.time()
    want_path = os.path.join(repo, *RESTART_WANT)
    try:
        since = float((wanted or {}).get("since") or now)
    except (TypeError, ValueError):
        since = now
    try:
        ran, _serving = _sweep_running(repo, now)
    except Exception:                                          # noqa: BLE001
        ran = None
    pulled = f"pulled {before}..{after}" if before != after else f"{after}, pulled earlier,"
    if ran is not None and now - since < RESTART_WAIT_MAX_S:
        try:
            os.makedirs(os.path.dirname(want_path), exist_ok=True)
            tmp = want_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"commit": after, "since": round(since), "at": round(now)}, fh)
            os.replace(tmp, want_path)
            os.chmod(want_path, 0o644)
            _record(repo, True, f"{pulled} — the restart waits for the board sweep in progress "
                                f"({ran / 60:.0f} min in; waited {(now - since) / 60:.0f} of "
                                f"{RESTART_WAIT_MAX_S // 60} min)" + stray + trim)
            return
        except OSError:
            pass                       # cannot leave the request: restart now
    waited = f" after waiting {(now - since) / 60:.0f} min for the board sweep" if now - since >= 60 else ""
    try:
        subprocess.run(("systemctl", "restart", service), check=True, timeout=120)
        try:
            os.remove(want_path)
        except OSError:
            pass
        _record(repo, True, f"{pulled} and restarted {service}{waited}" + stray + trim)
    except Exception as exc:                                  # noqa: BLE001
        _record(repo, False, f"{pulled} but the restart failed: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/srv/qellys")
    ap.add_argument("--service", default="qellys")
    args = ap.parse_args()
    repo = args.repo

    ok, porcelain = _git(repo, "status", "--porcelain")
    if not ok:
        _record(repo, False, f"git status failed: {porcelain}")
        return 0
    # `_git` strips the joint output, which eats the leading space off
    # the first porcelain line (" M f.txt" -> "M f.txt") — so no fixed-
    # width slicing: strip each line and split the status code off at
    # the first space run instead.
    lines = [ln.strip() for ln in porcelain.splitlines() if ln.strip()]
    modified = [ln.partition(" ")[2].lstrip()
                for ln in lines if not ln.startswith("??")]
    untracked = [ln.partition(" ")[2].lstrip()
                 for ln in lines if ln.startswith("??")]
    if modified:
        _record(repo, False, "working tree dirty — pull skipped "
                             f"(uncommitted changes to {_named(modified)}: "
                             "someone's work, not an obstacle)")
        return 0
    # Untracked files ride along in the note but never block: a
    # fast-forward cannot touch them (git refuses the pull if it would),
    # and each one is a .gitignore hole worth seeing on --boards.
    stray = (f" · {_named(untracked)} untracked and not ignored — "
             "a .gitignore hole" if untracked else "")
    ok, branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if not ok or not branch or branch == "HEAD":
        _record(repo, False, f"not on a branch: {branch}")
        return 0
    _, before = _git(repo, "rev-parse", "--short", "HEAD")
    # THE TRIMMED SHELL STEPS ASIDE BEFORE NEW CODE LANDS (engine/shrink).
    # Between the pull writing a new index.html and the rebuild, an old
    # trimmed app.js would be served under the new page — the stale-script
    # failure the Caddyfile's @shell rule exists to stop. So when the fetch
    # shows new commits the trimmed copies are cleared first and Caddy
    # serves the originals until they are rebuilt, a second later. A fetch
    # that fails changes nothing here: the pull below fails the same way
    # and says so.
    fetched, _ = _git(repo, "fetch", "origin", branch)
    if fetched:
        _, head = _git(repo, "rev-parse", "HEAD")
        _, incoming = _git(repo, "rev-parse", "FETCH_HEAD")
        if head and incoming and head != incoming:
            why = _allowed(repo, _setting("QB_UPDATE_REQUIRE", "off"))
            if why:
                _record(repo, False, f"refused {incoming[:8]}: {why} "
                                     "(QB_UPDATE_REQUIRE) — nothing pulled")
                return 0
            _trim(repo, clear=True)
    ok, out = _git(repo, "pull", "--ff-only", "origin", branch)
    if not ok:
        _record(repo, False, f"pull failed: {out}" + _trim(repo))
        return 0
    _, after = _git(repo, "rev-parse", "--short", "HEAD")
    trim = _trim(repo)
    # New code pulled by an earlier run may still be waiting for its
    # restart (`_restart_or_wait`): this run finishes that wait, unless the
    # app is already serving it (it restarted on its own meanwhile).
    want_path = os.path.join(repo, *RESTART_WANT)
    wanted = _read_json(want_path)
    if wanted and after == before:
        try:
            serving = _sweep_running(repo, time.time())[1]
        except Exception:                                      # noqa: BLE001
            serving = ""
        if _same_commit(serving, after):
            try:
                os.remove(want_path)
            except OSError:
                pass
            wanted = None
    if after == before and not wanted:
        _record(repo, True, "up to date" + stray + trim)
        return 0
    # Code pulled earlier and still waiting (`wanted`) restarts whatever
    # this pull carried; on its own, a docs-only pull does not.
    if not wanted and not _needs_restart(repo, before, after):
        _record(repo, True, f"pulled {before}..{after} — docs and tests only, nothing the "
                            "site runs: no restart" + stray + trim)
        return 0
    # Restart AFTER recording would report a restart that hasn't happened;
    # record what was done, with the restart's own result on the line.
    _restart_or_wait(repo, args.service, before, after, wanted, stray, trim)
    return 0


if __name__ == "__main__":
    sys.exit(main())
