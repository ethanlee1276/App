"""What a stranger sees of the paid side before making an account.

    python3 -m engine.firstlook         # the JSON, as the box would serve it

Ethan, 2026-10-25: "we need to go deeper on the free paid wall for when u
sign into the site or first get onto the site. look at other apps ... we
can show our paid features on the sign up site". The sign-up screen and
the plans show the members' side the way a store app's paywall does — the
picks waiting tonight, how last night went, and one real graded pick as
the sample (the Financial Times' "view a sample" before you register) —
and every number comes from here.

PUBLIC BY DESIGN, and nothing in it is new to the public: the record, last
night and tonight's per-league counts are the iPhone widget's own feed
(engine/widgetfeed, GET /api/widget — a count, as the "picks are up" alert
says it, never a pick), and the sample is the newest row of the Record's
settled list (/api/record/bets serves the same row to anyone). Whatever
that row did — won or lost — is what shows: a first screen that picked
its own best result would be the one claim on the page nobody could check.

AND TODAY'S FREE PICK (`free_pick`, 2026-11-03; Ethan, on the audit's "the
free Pick of the Day travels": "on sign-up and plans"): the day's top pick as
the public copy of day_top_pick.json carries it — free since 2026-10-30 —
on a day it is a bet and dated today, with the Pick of the Day's own record.
Nothing the free page does not already show anyone.

AND HOW MANY ARE HERE (`proof`, 2026-10-26, the ideas list's "true social
proof"): accounts made in the last seven days, from the accounts table,
and pages in a game's chat room right now, from the room's own "here"
count (engine/gamechat). Counts only, never a name. Real or not shown: a
number under its floor is left out rather than dressed up, and nothing is
ever rounded up, padded or invented.
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

#: What the screen keeps of the newest graded pick.
LAST_FIELDS = ("date", "sport", "player", "market", "side", "line", "odds", "book",
               "status", "pnl_units", "hit_prob")


#: What the screen keeps of today's free pick: the words, the price and whose fair it is.
FREE_PICK_FIELDS = ("sport", "player", "team", "opponent", "market", "market_label", "side", "line", "odds",
                    "book", "fair_prob", "evidence", "price_implied", "payout_units", "headshot")


#: The floors under which a count is not shown: "3 accounts made this
#: week" tells a stranger nothing they should act on.
WEEK_MIN = 25
ROOMS_MIN = 10
WEEK_S = 7 * 86400


def proof(now: float | None = None, conn=None) -> dict | None:
    """``{"week": accounts made in seven days, "rooms": pages in game rooms
    now}``, each only when it clears its floor; None when neither does."""
    now = time.time() if now is None else float(now)
    out: dict = {}
    own = conn is None
    try:
        if own:
            # A read never makes the accounts file: no file, no count.
            from engine import accounts as A
            conn = A.connect() if Path(A.DB_PATH).exists() else None
        if conn is not None:
            week = int(conn.execute("SELECT COUNT(*) FROM users WHERE created_at > ?",
                                    (now - WEEK_S,)).fetchone()[0])
            if week >= WEEK_MIN:
                out["week"] = week
    except Exception:                    # noqa: BLE001 — the first screen draws without it
        pass
    finally:
        if own and conn is not None:
            conn.close()
    from engine import gamechat as GC
    rooms = GC.here_total(now)
    if rooms >= ROOMS_MIN:
        out["rooms"] = rooms
    return out or None


def last_graded(conn) -> dict | None:
    """The newest settled pick of the headline record, or None."""
    from engine import ledger as L
    try:
        rows = L.settled_page(conn)["rows"]
    except sqlite3.Error:
        return None
    return {k: rows[0].get(k) for k in LAST_FIELDS} if rows else None


def free_pick(web: Path = WEB, today: _dt.date | None = None) -> dict | None:
    """Today's free Pick of the Day, or None: the public file's top pick on a
    day it is a bet and dated today (the box's day, Eastern), with the Pick
    of the Day's record. Through gate.free_top_pick again, so a box with the
    paywall off — whose public path holds the full file — never shows a lean."""
    from engine import gate
    today = today or _dt.date.today()
    try:
        top = json.loads((Path(web) / "data" / "day_top_pick.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    top = gate.free_top_pick(top if isinstance(top, dict) else {})
    pick = top.get("pick")
    if not (isinstance(pick, dict) and pick) or str(top.get("date") or "") != today.isoformat():
        return None
    out = {k: pick[k] for k in FREE_PICK_FIELDS if pick.get(k) not in (None, "")}
    out["sport"] = str(top.get("sport") or pick.get("sport") or "")
    try:
        rec = json.loads((Path(web) / "data" / "record.json").read_text(encoding="utf-8")).get("potd") or {}
    except (OSError, ValueError, AttributeError):
        rec = {}
    if isinstance(rec, dict) and rec.get("settled"):
        out["record"] = {"w": int(rec.get("wins") or 0), "l": int(rec.get("losses") or 0),
                         "p": int(rec.get("pushes") or 0), "units": round(float(rec.get("net_units") or 0), 1)}
    return out


#: What the welcome page keeps of the newest fact-checked game.
SAMPLE_FIELDS = ("date", "away", "home", "names", "final", "call", "reads", "injuries")


def reports(web: Path = WEB, where=None) -> dict | None:
    """THE GAME REPORTS' OWN RECORD, for the welcome page's report card (Ethan,
    2026-11-17: "for the welcome page, we need to show more features, like we
    need to show the game report feature on the welcome page").

    Public figures only, each the free page's own: the report picks graded (the
    `report` book of record_head.json, which the Record page draws), and over
    every league's fact checks (engine/reportrecord, the free "How our reports
    did") the games checked, the winners called and the injury listings that
    held. And the newest fact-checked game as the sample, whatever it did, as
    `last_graded` shows the newest pick: a welcome page that picked its own best
    game would be the one claim on it nobody could check. A figure with nothing
    graded is left out; None with none at all."""
    from engine import widgetfeed
    out: dict = {}
    head = widgetfeed._load(Path(web) / "data" / "record_head.json") \
        or widgetfeed._load(Path(web) / "data" / "record.json")
    rep = head.get("report") if isinstance(head.get("report"), dict) else {}
    w, l = int(rep.get("wins") or 0), int(rep.get("losses") or 0)
    if w + l:
        out["picks"] = {"w": w, "l": l, "units": round(float(rep.get("net_units") or 0), 1)}
    try:
        from engine import gate, reportrecord
        # The archive beside the web folder it was handed, as gate.FULL_DIR sits
        # beside the site's own: a test's folder never reads the box's.
        if where is None:
            where = gate.FULL_DIR if Path(web).resolve() == WEB.resolve() else Path(web).parent / "data" / "built"
        games = calls = called = held = listed = 0
        newest = None
        for lg in reportrecord.LEAGUE_WORDS:
            rec = reportrecord.record(where, lg)
            t = rec.get("totals") or {}
            games += int(t.get("games") or 0)
            c, i = t.get("call") or (0, 0), t.get("injuries") or (0, 0)
            called, calls = called + int(c[0] or 0), calls + int(c[1] or 0)
            held, listed = held + int(i[0] or 0), listed + int(i[1] or 0)
            for g in rec.get("games") or []:
                if isinstance(g, dict) and g.get("final") and (newest is None or str(g.get("date") or "")
                                                                > str(newest[1].get("date") or "")):
                    newest = (lg, g)
        if games:
            out["games"] = games
        if calls:
            out["calls"] = {"right": called, "n": calls}
        if listed:
            out["injuries"] = {"right": held, "n": listed}
        if newest:
            lg, g = newest
            out["sample"] = {"league": lg, **{k: g[k] for k in SAMPLE_FIELDS if g.get(k) not in (None, "")}}
    except Exception:                                        # noqa: BLE001
        pass                    # the reports' figures are a nicety; the page stands without them
    return out or None


def build(web: Path = WEB, today: _dt.date | None = None, conn=None, took=None) -> dict:
    """The first screen's members' side. ``took``, a list, gets each part's milliseconds as ``(part, ms)``, in order
    (step AGH: the build was 1.8 s of the server's own time, and nothing said which part's)."""
    t0 = [time.perf_counter()]

    def mark(part):
        if took is not None:
            now = time.perf_counter()
            took.append((part, (now - t0[0]) * 1000.0))
            t0[0] = now
    from engine import widgetfeed
    out = widgetfeed.build(web, today)
    out.pop("url", None)
    mark("counts")
    out["free_pick"] = free_pick(web, today)
    mark("free")
    own = conn is None
    if own:
        from engine import ledger as L
        try:
            conn = L.connect()
        except sqlite3.Error:
            conn = None
    try:
        out["last"] = last_graded(conn) if conn is not None else None
    finally:
        if own and conn is not None:
            conn.close()
    mark("last")
    out["proof"] = proof()
    mark("proof")
    out["reports"] = reports(web)
    mark("reports")
    return out


if __name__ == "__main__":
    json.dump(build(), sys.stdout, indent=2)
    print()
