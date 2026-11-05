"""A push to the site's own phones when the site needs its owner.

Ethan, 2026-11-02: "deep dive and add more features and tools the Qellys book
owners account should have". The desk (engine/ownerdesk) shows the box's
health to whoever opens it; this says so without opening it, on every phone
signed in to the verified Qellys_Book account with alerts on, and the desk
puts the same list at its top under "Needs you":

  board     a league's board is STALE_H hours old or more on a day its league
            has a game (a league with none today is resting, not late)
  grading   the settle pass has not run for GRADE_H hours — it stamps itself
            every five minutes whether or not there is anything to grade
            (engine/maintenance), so this is a stuck loop, not a quiet night
  disk      the disk is DISK_PCT% full or more (1 November's outage)
  update    the last automatic update failed (deploy/autoupdate)
  odds      fewer than ODDS_LEFT odds credits with two or more days of the
            month to go: the boards price less until the first
  crashes   CRASHES_24H or more script errors on readers' screens in a day
  server    SERVER_ERRORS_24H or more errors inside the site in a day, from its
            own record (engine/bugscan.record_server)
  backup    the newest nightly copy of the accounts or the journal is
            ownerdesk.NIGHTLY_LATE_H hours old (deploy/backup.sh, 4am)
  offsite   last night's run made its copy but not the offsite one
  weekly-zip  no weekly zip of the small files in ownerdesk.WEEKLY_LATE_D days
  signins   ownerdesk.SPRAY_HOUR failed sign-ins in the last hour
  webhook   ownerdesk.WEBHOOK_BAD Stripe messages failing their signature in
            a day: the webhook secret may have changed, and payments with it
  mail      ownerdesk.MAIL_FAILS emails failing to send in a day, more than went
  lab       a sport's numbers on the Lab page ownerdesk.LAB_LATE_D days old (its
            weekly replay missed twice; the page stood five weeks in October)
  deepfit   a sport the weekly refit owes this round, last fitted
            ownerdesk.DEEP_LATE_D days ago or never (the NFL, August to November)

And, from `morning_pass` (its own pass, not a problem): yesterday in a line
after 8am Eastern, while the desk's "Morning summary" switch is on.

Each at most once an Eastern day (its id carries the problem and the day),
queued as an `account` notice (engine/pushalerts.ACCOUNT): it reaches every
phone signed in to the account, the day's cap never cuts it, and it waits
out the owner's own quiet hours (engine/pushmine.HELD) like a renewal does.
A failed service unit already emails the owner (engine/alert); these are the
softer failures, the ones a running site can see in itself. The box's own
state and counts — never a member.

Run from engine/pushmine.run_once every OWNER_EVERY_S. Costs one query when
the account has no phone with alerts on — and, phones or no, writes the
day's totals the desk's trend reads (engine/ownerdesk.snapshot).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
STALE_H = 6
GRADE_H = 2
DISK_PCT = 90
ODDS_LEFT = 2000
CRASHES_24H = 50
SERVER_ERRORS_24H = 25
OWNER_EVERY_S = 15 * 60
LABELS = {"nfl": "NFL", "cfb": "college football", "nba": "NBA", "wnba": "WNBA", "nhl": "NHL", "mlb": "MLB",
          "ufc": "UFC"}


def site_account(conn) -> int | None:
    """The verified Qellys_Book account's id (engine/whoson.SITE_HANDLE), or None."""
    from . import whoson as W
    try:
        r = conn.execute("SELECT user_id FROM feed_profiles WHERE handle = ? COLLATE NOCASE AND verified = 1",
                         (W.SITE_HANDLE,)).fetchone()
    except Exception:                                        # noqa: BLE001 — no feed tables yet: no account
        return None
    return int(r[0]) if r else None


def _eastern_day(t: float) -> str:
    from . import activity as ACT
    return ACT.eastern(t).date().isoformat()


def playing_today(league: str, data_dir: Path | None = None, now: float | None = None) -> bool:
    """A game today (Eastern) on the league's fast scoreboard, begun or not.
    A scoreboard that cannot be read says nothing either way: not today."""
    from .gamechat import _when
    t = time.time() if now is None else float(now)
    try:
        doc = json.loads((Path(data_dir or DATA) / f"live_{league}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    today = _eastern_day(t)
    for g in (doc.get("games") if isinstance(doc, dict) else None) or []:
        live = (g or {}).get("live") or {}
        if str(live.get("state") or "").lower() in ("live", "in"):
            return True
        start = _when(live.get("start_time"))
        if start is not None and _eastern_day(start) == today:
            return True
    return False


def _hours(s: float) -> str:
    h = s / 3600
    return f"{h:.0f}" if h >= 10 else f"{h:.1f}".rstrip("0").rstrip(".")


def problems(h: dict, data_dir: Path | None = None, now: float | None = None) -> list[dict]:
    """What needs the owner, read off the desk's health section: a list of
    {key, title, body}, the worst first. Empty when all is well."""
    t = time.time() if now is None else float(now)
    if not isinstance(h, dict) or h.get("error"):
        return []
    out = []
    d = h.get("disk") or {}
    if d.get("used_pct") is not None and float(d["used_pct"]) >= DISK_PCT:
        out.append({"key": "disk", "title": f"The disk is {float(d['used_pct']):g}% full",
                    "body": f"{d.get('free_gb', '?')} GB left. A full disk took the site down on 1 November; "
                            "the desk has the details."})
    s = h.get("settled_ago_s")
    if s is not None and float(s) >= GRADE_H * 3600:
        out.append({"key": "grading", "title": f"Bets have not been graded in {_hours(float(s))} hours",
                    "body": "The settle pass checks every five minutes and has stopped. The service may need a restart."})
    for league, hours in sorted((h.get("stale") or {}).items()):
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            continue
        if hours >= STALE_H and playing_today(league, data_dir, t):
            out.append({"key": f"board-{league}",
                        "title": f"The {LABELS.get(league, league.upper())} board is {_hours(hours * 3600)} hours old",
                        "body": "Its league plays today and the board has not rebuilt. The desk has the details."})
    u = h.get("update") or {}
    if u and u.get("ok") is False:
        out.append({"key": "update", "title": "The last site update failed",
                    "body": (str(u.get("note") or "").strip()[:140]
                             or "The site is still running the version before it.")})
    o = h.get("odds") or {}
    try:
        low = o and o.get("remaining") is not None and int(o["remaining"]) < ODDS_LEFT and int(o.get("days_left") or 0) >= 2
    except (TypeError, ValueError):
        low = False
    if low:
        out.append({"key": "odds", "title": f"{int(o['remaining']):,} odds credits left",
                    "body": f"With {int(o['days_left'])} days of the month to go, the boards price less until the 1st."})
    # The backups (engine/ownerdesk.backups): the nightly copies of the two
    # databases that cannot be rebuilt, the offsite leg, the weekly zip.
    # A weekly zip went missing for four weeks in October with nothing to
    # say so (docs/RUN_NEXT.md, BU1).
    from . import ownerdesk as OD
    b = h.get("backups") if isinstance(h.get("backups"), dict) else {}
    late = [float(v.get("age_h") or 0) for k, v in (b.get("dbs") or {}).items()
            if k in ("accounts", "ledger") and float(v.get("age_h") or 0) >= OD.NIGHTLY_LATE_H]
    if late:
        out.append({"key": "backup", "title": f"The nightly backup is {_hours(max(late) * 3600)} hours old",
                    "body": "The newest copy of the accounts or the bet journal. deploy/backup.sh runs at 4am "
                            "from root's cron; the desk has each database's age."})
    run = b.get("run") or {}
    try:
        recent = float(run.get("age_h")) < 30
    except (TypeError, ValueError):
        recent = False
    if run.get("offsite") == "failed" and recent:
        why = str(run.get("why") or "").strip().rstrip(".")
        out.append({"key": "offsite", "title": "Last night's backup did not reach the offsite copy",
                    "body": (f"The copy on this disk was made; the offsite leg failed: {why[:160]}. "
                             "./deploy/backup.sh --test-remote on the box tries it again."
                             if why else
                             "The copy on this disk was made; the offsite leg failed. "
                             "./deploy/backup.sh --test-remote on the box says why.")})
    w = b.get("weekly") or {}
    if w and float(w.get("age_d") or 0) >= OD.WEEKLY_LATE_D:
        out.append({"key": "weekly-zip", "title": f"No weekly backup zip in {int(float(w['age_d']))} days",
                    "body": "The Sunday zip of the small files (the UFC dossiers, the device profiles) has stopped. "
                            "The chores' log says why."})
    # The security log (engine/ownerdesk.security).
    sec = h.get("security") if isinstance(h.get("security"), dict) else {}
    if int(sec.get("fails_hour") or 0) >= OD.SPRAY_HOUR:
        out.append({"key": "signins", "title": f"{int(sec['fails_hour']):,} failed sign-ins in the last hour",
                    "body": (f"Up to {int(sec.get('fails_one_network') or 0):,} from one network and "
                             f"{int(sec.get('fails_one_account') or 0):,} on one account. Somebody may be trying "
                             "passwords; the rate limit slows each network.")})
    if int(sec.get("stripe_bad_day") or 0) >= OD.WEBHOOK_BAD:
        out.append({"key": "webhook", "title": "Stripe's messages are failing their signature check",
                    "body": (f"{int(sec['stripe_bad_day']):,} in a day. If the webhook's signing secret changed "
                             "in Stripe, payments stop reaching the site until STRIPE_WEBHOOK_SECRET matches it.")})
    # The weekly jobs (engine/ownerdesk.weekly): the Lab's numbers and the
    # deep refit, each of which stood still for weeks with nothing to say so.
    wk = h.get("weekly") if isinstance(h.get("weekly"), dict) else {}
    today = _eastern_day(t)

    def _days(iso):
        try:
            import datetime as _dt
            return (_dt.date.fromisoformat(today) - _dt.date.fromisoformat(str(iso)[:10])).days
        except (TypeError, ValueError):
            return None
    lab_late = sorted(((_days(x.get("replayed")), str(x.get("sport") or ""))
                       for x in ((wk.get("lab") or {}).get("sports") or []) if x.get("replayed")),
                      reverse=True)
    lab_late = [(d, sp) for d, sp in lab_late if d is not None and d >= OD.LAB_LATE_D]
    if lab_late:
        d, sp = lab_late[0]
        out.append({"key": "lab", "title": f"The Lab's {LABELS.get(sp, sp.upper())} numbers are {d} days old",
                    "body": ("Late: " + ", ".join(f"{LABELS.get(s, s.upper())} ({n} days)" for n, s in lab_late)
                             + ". Each sport replays every seven days; the desk's Weekly jobs card has the "
                               "Lab's last run.")})
    deep = wk.get("deep") if isinstance(wk.get("deep"), dict) else {}
    owed = []
    for sp, last in sorted((deep.get("last_done") or {}).items()):
        d = _days(last) if last else None
        if d is None or d >= OD.DEEP_LATE_D:
            owed.append((sp, d))
    if owed:
        # The oldest first; a sport with no finished fit on record before all.
        owed.sort(key=lambda x: (x[1] is None, x[1] or 0), reverse=True)
        sp, d = owed[0]
        out.append({"key": "deepfit", "title": (f"The deep refit has not fitted the {LABELS.get(sp, sp.upper())} in "
                                                f"{d} days" if d is not None else
                                                f"The deep refit has no finished {LABELS.get(sp, sp.upper())} fit on record"),
                    "body": ("Owed this round: " + ", ".join(
                        f"{LABELS.get(s, s.upper())} ({f'{n} days' if n is not None else 'none on record'})"
                        for s, n in owed)
                             + (". Part-way: " + "; ".join(deep.get("part_way") or []) if deep.get("part_way") else "")
                             + ". The desk's Weekly jobs card has the refit's round.")})
    # The emails (engine/ownerdesk.mail): sends failing, and more than went.
    ml = h.get("mail") if isinstance(h.get("mail"), dict) else {}
    bad = int(ml.get("failed_day") or 0)
    if bad >= OD.MAIL_FAILS and bad > int(ml.get("sent_day") or 0):
        last = ml.get("last_fail") or {}
        out.append({"key": "mail", "title": f"{bad:,} emails failed to send in a day",
                    "body": (f"The last: {last.get('kind') or 'an email'} — {str(last.get('why') or '')[:110]}"
                             if last else "The desk's Emails card has the reasons.")})
    n = int(h.get("crashes") or 0)
    if n >= CRASHES_24H:
        top = ((h.get("crash_top") or [{}])[0] or {}).get("m") or ""
        out.append({"key": "crashes", "title": f"{n:,} script errors on readers' screens in a day",
                    "body": (f"Most often: {top[:120]}" if top else "The desk lists the most common.")})
    n = int(h.get("server_errors") or 0)
    if n >= SERVER_ERRORS_24H:
        top = (h.get("server_top") or [{}])[0] or {}
        out.append({"key": "server", "title": f"{n:,} errors inside the site in a day",
                    "body": (f"Most often: {str(top.get('m') or '')[:110]}"
                             + (f" at {top['src']}" if top.get("src") else "") if top.get("m")
                             else "The desk lists the most common.")})
    return out


#: The days this process has already queued its morning summary (a restart
#: asks again; pushmine.tell never queues one id twice).
_MORNING_DONE: set = set()


def morning_pass(conn, now: float | None = None) -> int:
    """The owner's morning summary (engine/ownerdesk.morning): yesterday in a
    line, once an Eastern day from ownerdesk.MORNING_HOUR, to the site's
    owners' phones, while the desk's switch for it is on. Queued as an
    `account` notice like the problems, so it waits out the owner's quiet
    hours."""
    from . import ownerdesk as OD
    from . import pushalerts as PA
    from . import pushmine as PM
    from . import siteowners as SO
    from . import activity as ACT
    t = time.time() if now is None else float(now)
    day = _eastern_day(t)
    if day in _MORNING_DONE or ACT.eastern(t).hour < OD.MORNING_HOUR or not OD.prefs()["morning"]:
        return 0
    uids = [u for u in SO.desk_accounts(conn) if PM.asked(conn, u, PA.ACCOUNT)]
    if not uids:
        return 0
    mo = OD.morning(conn, None, t)
    told = sum(bool(PM.tell(conn, uid, f"owner:morning:{day}", PA.ACCOUNT, mo["title"], mo["body"], "/#owner", now=t))
               for uid in uids)
    _MORNING_DONE.add(day)
    return told


def alerts_pass(conn, now: float | None = None, health: dict | None = None, data_dir: Path | None = None) -> int:
    """Queue today's alert for each problem not yet told today; how many."""
    from . import ownerdesk as OD
    from . import pushalerts as PA
    from . import pushmine as PM
    from . import siteowners as SO
    t = time.time() if now is None else float(now)
    # The business day by day (engine/ownerdesk.snapshot): the day's totals,
    # written every pass so the day's last write is its close, phones or no.
    try:
        OD.snapshot(conn, t)
    except Exception:                                        # noqa: BLE001 — the alerts still go
        pass
    # The site's owners' phones (engine/siteowners: the listed accounts; until
    # there are any, the verified Qellys_Book account's).
    uids = [u for u in SO.desk_accounts(conn) if PM.asked(conn, u, PA.ACCOUNT)]
    if not uids:
        return 0
    h = health if health is not None else OD.health(t)
    day = _eastern_day(t)
    told = 0
    for p in problems(h, data_dir, t):
        for uid in uids:
            told += bool(PM.tell(conn, uid, f"owner:{p['key']}:{day}", PA.ACCOUNT, p["title"], p["body"],
                                 "/#owner", now=t))
    return told
