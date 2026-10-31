"""The bug scan: everything that broke, in one place — crashes on people's phones, the builds, the box.

    python3 -m engine.bugscan                 # the last 24 hours
    python3 -m engine.bugscan --hours 72
    python3 -m engine.bugscan --mail          # and mail the owner when anything is broken

Ethan, 2026-10-24: "we need a debugging thing to scan for bugs ... anything
a normal app and a consistent running app and website would have." The box
already had pieces of this — doctor.py's checks, engine/alert mailing the
owner when a service dies, every build's warnings in its own log — and one
large hole: a script error on someone's phone drew an apology on THEIR
screen (app.js crashNote) and told nobody else. A crash only one person
ever saw is a crash that ships again.

WHAT IT READS, all on the box, nothing fetched:

  crashes     data/logs/client_errors.jsonl, written by `record_client` from
              POST /api/clienterror (server.py): the message, where in the
              script, the page, the screen's size and the browser's family.
              No IP address, no account, no identifier (privacy policy 2.6).
              Grouped by message and place, counted, with the screens and
              browsers each was seen on — a crash only on 280px covers, or
              only in Samsung Internet, says so.
  builds      each board's last build log (data/logs/<build>.log): its
              warning lines and any traceback.
  boards      each published board's age: one not rewritten in BOARD_STALE_H
              during the season is a build that keeps failing quietly.
  updates     data/autoupdate.json: the box pulling and restarting itself.
  service     the site's error lines in the journal, where journalctl runs.

A section that cannot be read says so; it is never an empty "all clear".
Exit 1 when anything is broken, so a cron line or the daily pass can act.

Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "data", "logs")
#: The crash log, and the size past which its older half is dropped.
CLIENT_LOG = os.path.join(LOG_DIR, "client_errors.jsonl")
CLIENT_LOG_MAX = 2 * 1024 * 1024
#: The boards the site publishes, as launch.BOARD_FILES names them.
BOARDS = {"nfl": "web/data/recommendations.json", "cfb": "web/data/cfb.json",
          "mlb": "web/data/mlb_recommendations.json", "nba": "web/data/nba.json",
          "wnba": "web/data/wnba.json", "nhl": "web/data/nhl.json"}
BUILD_LOGS = ("nfl_build", "cfb_build", "mlb_build", "nba_build", "nhl_build", "ufc_build")
#: A board this many hours old, in its season, is stale.
BOARD_STALE_H = 3
#: Messages that are the browser talking, not the site failing.
NOISE = (re.compile(r"ResizeObserver loop"), re.compile(r"^Script error\.?$"),
         re.compile(r"(chrome|moz|safari)-extension://"), re.compile(r"^Load failed$"))


def _clean(v, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(v or "")).strip()[:n]


def browser_family(ua: str) -> str:
    """"Samsung Internet Android", "Safari iOS", "Chrome Android", … from a
    user agent; nothing finer, so a report identifies a browser, not a person."""
    ua = ua or ""
    os_ = ("iOS" if re.search(r"iPhone|iPad|iPod", ua) else "Android" if "Android" in ua
           else "Mac" if "Mac OS X" in ua else "Windows" if "Windows" in ua else "Linux" if "Linux" in ua else "")
    br = ("Samsung Internet" if "SamsungBrowser" in ua else "Edge" if re.search(r"Edg[A/]", ua)
          else "Firefox" if re.search(r"Firefox|FxiOS", ua) else "Chrome" if re.search(r"Chrome|CriOS", ua)
          else "Safari" if "Safari" in ua else "other")
    return f"{br} {os_}".strip()


def running_commit(root: str | None = None) -> str:
    """The commit the site is serving, off its heartbeat; "" when unknown."""
    try:
        with open(os.path.join(root or ROOT, "web", "data", "heartbeat.json"), encoding="utf-8") as fh:
            return _clean(json.load(fh).get("commit"), 12)
    except (OSError, ValueError, AttributeError):
        return ""


def record_client(body: dict, ua: str = "", path: str | None = None, now: float | None = None,
                  commit: str = "") -> bool:
    """Append one crash report; False when it was noise or malformed."""
    if not isinstance(body, dict):
        return False
    msg = _clean(body.get("m"), 200)
    if not msg or any(p.search(msg) for p in NOISE):
        return False
    src = _clean(body.get("src"), 160)
    if any(p.search(src) for p in NOISE):
        return False
    try:
        w, h = int(body.get("w") or 0), int(body.get("h") or 0)
    except (TypeError, ValueError):
        w = h = 0
    row = {"at": int(now or time.time()), "m": msg, "src": src,
           "view": re.sub(r"[^a-z0-9-]", "", str(body.get("view") or "").lower())[:24],
           "w": max(0, min(w, 10000)), "h": max(0, min(h, 10000)),
           "browser": browser_family(ua), "commit": _clean(commit, 12)}
    path = path or CLIENT_LOG
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    try:
        if os.path.getsize(path) > CLIENT_LOG_MAX:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()
            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                fh.writelines(lines[len(lines) // 2:])
            os.replace(path + ".tmp", path)
    except OSError:
        pass
    return True


def crashes(hours: float = 24, path: str | None = None, now: float | None = None) -> list:
    """[{m, src, n, views, screens, browsers, first, last}] busiest first."""
    since = (now or time.time()) - hours * 3600
    groups: dict = {}
    try:
        fh = open(path or CLIENT_LOG, encoding="utf-8")
    except OSError:
        return []
    with fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("at", 0) < since:
                continue
            g = groups.setdefault((r.get("m"), r.get("src")), {
                "m": r.get("m"), "src": r.get("src"), "n": 0, "first": r["at"], "last": r["at"],
                "views": defaultdict(int), "screens": defaultdict(int), "browsers": defaultdict(int)})
            g["n"] += 1
            g["first"], g["last"] = min(g["first"], r["at"]), max(g["last"], r["at"])
            g["views"][r.get("view") or "?"] += 1
            g["screens"][f"{r.get('w')}x{r.get('h')}"] += 1
            g["browsers"][r.get("browser") or "?"] += 1
    return sorted(groups.values(), key=lambda g: -g["n"])


def build_warnings(hours: float = 24, log_dir: str | None = None, now: float | None = None) -> dict:
    """{build: [lines]} — each build log written in the window, its warning
    lines and the last line of any traceback."""
    out = {}
    since = (now or time.time()) - hours * 3600
    for name in BUILD_LOGS:
        path = os.path.join(log_dir or LOG_DIR, f"{name}.log")
        try:
            if os.path.getmtime(path) < since:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        got = [ln.strip() for ln in lines if "⚠️" in ln or ln.startswith("Traceback")]
        tb = [i for i, ln in enumerate(lines) if ln.startswith("Traceback")]
        for i in tb:
            tail = next((ln for ln in lines[i + 1:] if ln and not ln.startswith(" ")), "")
            if tail:
                got.append("  -> " + tail.strip())
        if got:
            out[name] = got[:12]
    return out


def stale_boards(root: str | None = None, now: float | None = None, hours: float = BOARD_STALE_H) -> dict:
    """{league: hours old} for published boards older than ``hours``."""
    out = {}
    for league, rel in BOARDS.items():
        try:
            age = ((now or time.time()) - os.path.getmtime(os.path.join(root or ROOT, rel))) / 3600
        except OSError:
            continue
        if age > hours:
            out[league] = round(age, 1)
    return out


def update_state(root: str | None = None) -> dict:
    try:
        with open(os.path.join(root or ROOT, "data", "autoupdate.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def service_errors(hours: float = 24) -> list | None:
    """The site's error lines from the journal; None where it cannot be read."""
    try:
        got = subprocess.run(["journalctl", "-u", "qellys", "--since", f"-{int(hours)}h", "-p", "err",
                              "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if got.returncode != 0:
        return None
    return [ln for ln in got.stdout.splitlines() if ln.strip()][-20:]


def scan(hours: float = 24, now: float | None = None, journal=service_errors) -> dict:
    """Everything, with ``broken``: the count of things that need a person."""
    rows = crashes(hours, now=now)
    builds = build_warnings(hours, now=now)
    stale = stale_boards(now=now)
    upd = update_state()
    svc = journal(hours)
    broken = (len(rows) + sum(1 for v in builds.values() if any(ln.startswith("Traceback") for ln in v))
              + (1 if upd and upd.get("ok") is False else 0) + (len(svc) if svc else 0))
    return {"hours": hours, "crashes": rows, "builds": builds, "stale": stale, "update": upd,
            "service": svc, "broken": broken}


def report(got: dict) -> list:
    when = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(t))  # noqa: E731
    out = [f"BUG SCAN · the last {got['hours']:g} hours · {got['broken']} thing(s) need a person"]
    out.append(f"\nCRASHES ON PEOPLE'S SCREENS: {sum(g['n'] for g in got['crashes'])} report(s), "
               f"{len(got['crashes'])} distinct")
    for g in got["crashes"][:15]:
        top = lambda d: ", ".join(f"{k} ×{v}" for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:4])  # noqa: E731
        out.append(f"  ×{g['n']:<3} {g['m'][:110]}")
        out.append(f"        at {g['src'] or '?'} · pages {top(g['views'])} · screens {top(g['screens'])}")
        out.append(f"        browsers {top(g['browsers'])} · {when(g['first'])} to {when(g['last'])} UTC")
    out.append(f"\nBUILDS WITH WARNINGS: {len(got['builds'])}")
    for name, lines in got["builds"].items():
        out.append(f"  {name}:")
        out += [f"    {ln[:150]}" for ln in lines]
    out.append(f"\nBOARDS OLDER THAN {BOARD_STALE_H}h: " + (", ".join(f"{k} {v}h" for k, v in got["stale"].items())
                                                         or "none"))
    u = got["update"]
    out.append("\nSELF-UPDATE: " + (f"{'ok' if u.get('ok') else 'FAILED'} at {u.get('at')}: {u.get('note', '')}"
                                    if u else "no record (data/autoupdate.json)"))
    s = got["service"]
    out.append("\nSITE ERRORS IN THE JOURNAL: " + ("not readable here" if s is None else str(len(s))))
    out += [f"  {ln[:150]}" for ln in (s or [])[-10:]]
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--mail", action="store_true", help="mail the owner when anything is broken")
    a = ap.parse_args(argv)
    got = scan(a.hours)
    text = "\n".join(report(got))
    print(text)
    if a.mail and got["broken"]:
        from . import alert
        print("mail:", alert.send_text(f"Qellys bug scan: {got['broken']} thing(s) need a person", text))
    return 1 if got["broken"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
