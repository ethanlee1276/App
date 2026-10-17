#!/usr/bin/env python3
"""Which bets are still open on games that are over, and why. Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 settlecheck.py

Ethan, 2026-10-13: "bets are taking way too long too setttle … It should
not take a day for all bets to settle." The settle now runs on its own
clock and a final on a live board starts a pass at once, so a bet on a
finished game should be graded within minutes. This prints, per league:

* OPEN — every open bet, split by its game day: today, yesterday, older.
* OWED — open bets on a day whose games the history database has as
  final. Each one is listed with what it is waiting on: no stat line for
  that player on file (the box score or the league's file has not landed,
  or he did not play and the official file has to say so), or a stat line
  that IS on file (then the settle itself has not run since — see SETTLE).
* NOT FINAL — open bets on a day the database does not yet have final: the
  results feed has not delivered that game.

and the SETTLE line: when the last pass ran and what the settle lane is
doing now. Writes nothing; the databases are opened read-only.
"""

import datetime as _dt
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: Leagues in the order the page lists them. Fights and desk tickets grade
#: elsewhere (the fight's result, the exchange) and are counted, not traced.
LEAGUES = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl")
GAME_MARKETS = ("moneyline", "total", "spread", "team_total")
#: How many owed rows to name per league.
SHOW = 8
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ro(path):
    """Read-only, never created: a missing file is an error, not an empty
    database the check made."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _day(row) -> str:
    return str(row["game_day"] or row["date"] or "")[:10]


def _ago(ts, now) -> str:
    if not isinstance(ts, (int, float)):
        return "never"
    m = int((now - ts) // 60)
    return f"{m} min ago" if m < 120 else f"{m // 60} h ago"


def settle_line(state_path, lane_path, now=None) -> str:
    """The last pass and what the lane is doing now."""
    now = time.time() if now is None else now
    try:
        st = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    try:
        lane = json.loads(Path(lane_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        lane = {}
    doing = lane.get("step") or "idle"
    if lane.get("step") and lane.get("since"):
        doing += f" for {int((now - lane['since']) // 60)} min"
    return (f"SETTLE  last pass {_ago(st.get('last_settle_ts'), now)}  ·  desk asked "
            f"{_ago(st.get('last_desk_ts'), now)}  ·  settle lane: {doing}")


def _games(hist, sport, b, day):
    """(games on file that day, how many final) for this bet's league-day."""
    if sport == "nfl":
        q, a = "SELECT COUNT(*), COALESCE(SUM(home_score IS NOT NULL), 0) FROM games " \
               "WHERE sport='nfl' AND date=?", (day,)
    else:
        q, a = "SELECT COUNT(*), COALESCE(SUM(home_score IS NOT NULL), 0) FROM games " \
               "WHERE sport=? AND (period=? OR date=?)", (sport, b["date"], day)
    r = hist.execute(q, a).fetchone()
    return int(r[0] or 0), int(r[1] or 0)


def _has_line(hist, sport, b) -> str:
    """'official', 'box' (provisional, same night) or '' for the player's
    stat line in this market on the bet's slate."""
    from engine.ledger import _hist_where, DERIVED_MARKETS
    where, args = _hist_where(b)
    market = b["market"]
    parts = DERIVED_MARKETS.get((sport, market), (market,))
    marks = ",".join("?" * len(parts))
    rows = hist.execute(f"SELECT game_id FROM player_game_logs WHERE {where} AND player=? "
                        f"AND market IN ({marks})", (*args, b["player"], *parts)).fetchall()
    if not rows:
        return ""
    return "box" if all(str(r[0]).endswith("-box") for r in rows) else "official"


def _absent_why(hist, b) -> str:
    """A prop with no stat line. College says which link of the settler's
    absent-player rule holds it (engine.ledger.absent_blocker) — 61 college
    rows read only "no stat line" on 2026-10-17 and nobody could tell a
    missing box from a man with no team."""
    plain = "no stat line for him yet (box or league file not in, or he did not play)"
    if b["sport"] != "cfb":
        return plain
    try:
        from engine import ledger
        why = ledger.absent_blocker(hist, b)
    except Exception:                                    # noqa: BLE001
        return plain
    return f"no stat line for him — {why}" if why else plain


def report(ledger_path, history_path, today=None) -> list:
    today = today or _dt.date.today()
    yday = (today - _dt.timedelta(days=1)).isoformat()
    led, hist = _ro(ledger_path), _ro(history_path)
    led.row_factory = hist.row_factory = sqlite3.Row
    out = []
    rows = led.execute("SELECT * FROM bets WHERE status='open' ORDER BY sport, game_day, date").fetchall()
    for sport in LEAGUES:
        mine = [b for b in rows if b["sport"] == sport
                and (b["category"] or "") not in ("predmarket", "ufc")]
        if not mine:
            out.append(f"{sport.upper():5} open 0")
            continue
        when = {"today": 0, "yesterday": 0, "older": 0, "ahead": 0, "undated": 0}
        owed, not_final = [], 0
        for b in mine:
            d = _day(b)
            if not _ISO.match(d):
                when["undated"] += 1      # a week label with no game day: --backfill-days
                continue
            key = ("ahead" if d > today.isoformat() else "today" if d == today.isoformat()
                   else "yesterday" if d == yday else "older")
            when[key] += 1
            if key == "ahead":
                continue
            n, fin = _games(hist, sport, b, d)
            if not n or fin < n:
                not_final += 1
                continue
            line = "" if b["market"] in GAME_MARKETS else _has_line(hist, sport, b)
            why = ("game bet on a final score — the settle has not run since" if b["market"] in GAME_MARKETS
                   else "stat line on file (box score) — the settle has not run since" if line == "box"
                   else "stat line on file — the settle has not run since" if line == "official"
                   else _absent_why(hist, b))
            owed.append((d, b["player"], b["market"], b["category"], why))
        out.append(f"{sport.upper():5} open {len(mine)}  ·  today {when['today']}  yesterday {when['yesterday']}  "
                   f"older {when['older']}  ahead {when['ahead']}"
                   + (f"  undated {when['undated']}" if when["undated"] else "")
                   + f"  ·  OWED {len(owed)}  NOT FINAL {not_final}")
        for d, p, m, c, why in sorted(owed)[:SHOW]:
            out.append(f"      {d}  {p} {m} [{c}] — {why}")
        if len(owed) > SHOW:
            out.append(f"      … and {len(owed) - SHOW} more")
            # The whole list by reason, so the rows past SHOW are not a mystery.
            tally: dict = {}
            for *_, why in owed:
                tally[why] = tally.get(why, 0) + 1
            for why, n in sorted(tally.items(), key=lambda kv: -kv[1]):
                out.append(f"      {n:4} × {why}")
    fights = [b for b in rows if b["sport"] == "ufc" or (b["category"] or "") == "ufc"]
    desk = [b for b in rows if (b["category"] or "") == "predmarket"]
    out.append(f"UFC   open {len(fights)}" + (f"  ·  oldest card {min(_day(b) for b in fights)}" if fights else ""))
    past = [b for b in desk if _day(b) and _day(b) <= today.isoformat()]
    out.append(f"DESK  open {len(desk)}  ·  on events today or earlier {len(past)}")
    return out


def main() -> int:
    print(settle_line(ROOT / "data" / "cache" / "maintenance.json",
                      ROOT / "data" / "cache" / "chores_settle.json"))
    try:
        for line in report(ROOT / "data" / "ledger.db", ROOT / "data" / "history.db"):
            print(line)
    except sqlite3.Error as exc:
        print(f"unreadable: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
