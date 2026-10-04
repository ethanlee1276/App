"""Opening lines, kept — so a game can say how far its market has moved.

Ethan, 2026-09-28, asked what the site was missing. The first answer was
this: every pull overwrote the game lines, so the board could never say
"PHI opened -4.5, now -3.5", and the one read both of his Eagles-Bears
research reports made from the market — the line moving toward Chicago
while most of the money sat on Philadelphia — had nothing to stand on.
The numbers passed through our hands every cycle and were thrown away.

WHAT IS KEPT. The first time a game is seen with a real book price on it
(a moneyline on both sides — a proxy line carries none), its spread (the
home club's number), total and moneylines are written once and never
touched again; every later build updates the "now" columns. One row per
game, in the crowd database beside the prediction-market tape.

WHAT THE PAGE GETS. ``line_open`` on the game: the opening numbers, when
they were first seen, and the moves. With the money split on the game
(engine/moneysplit) it also says when the spread moved AGAINST the money
— toward the side holding the minority of it — which is the classic
footprint of a book respecting the sharper side. A note, never a pick:
crowdfit measures the crowd's record before anything here moves a number.

NEVER RAISES into a build — an opening line is never the reason a board
fails.
"""

from __future__ import annotations

import datetime as _dt
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS line_opens (
    sport TEXT, date TEXT, away TEXT, home TEXT,
    open_ts INTEGER, open_spread REAL, open_total REAL, open_home_ml INTEGER, open_away_ml INTEGER,
    now_ts INTEGER, now_spread REAL, now_total REAL, now_home_ml INTEGER, now_away_ml INTEGER,
    PRIMARY KEY (sport, date, away, home)
);
"""

#: A spread move smaller than this is noise, not a move.
MIN_MOVE = 0.5
#: "Most of the money": the side holding at least this share.
MONEY_SIDE = 0.60


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _ml(v):
    n = _num(v)
    return int(n) if n else None            # zero is the board's "not offered"


def key(g: dict) -> tuple:
    return (str(g.get("date") or "")[:10], str(g.get("away") or ""), str(g.get("home") or ""))


def priced(g: dict) -> bool:
    """A book priced this game: a moneyline on both sides."""
    return _ml(g.get("home_ml")) is not None and _ml(g.get("away_ml")) is not None


def record(conn, sport: str, games, now: float | None = None) -> dict:
    """First-seen numbers written once; ``now`` columns every build.
    Started games are left alone (engine/crowd.started). Returns a census."""
    from .crowd import home_spread, started
    ensure_tables(conn)
    ts = int(now if now is not None else time.time())
    census = {"games": 0, "opened": 0, "updated": 0}
    for g in games or []:
        if not isinstance(g, dict) or not priced(g) or started(g, now):
            continue
        date, away, home = key(g)
        if not (away and home):
            continue
        census["games"] += 1
        sp, tot = home_spread(g), _num(g.get("total"))
        hm, am = _ml(g.get("home_ml")), _ml(g.get("away_ml"))
        row = conn.execute("SELECT open_ts FROM line_opens WHERE sport=? AND date=? AND away=? AND home=?",
                           (sport, date, away, home)).fetchone()
        if row is None:
            conn.execute("INSERT INTO line_opens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (sport, date, away, home, ts, sp, tot, hm, am, ts, sp, tot, hm, am))
            census["opened"] += 1
        else:
            conn.execute("UPDATE line_opens SET now_ts=?, now_spread=?, now_total=?, now_home_ml=?, now_away_ml=? "
                         "WHERE sport=? AND date=? AND away=? AND home=?",
                         (ts, sp, tot, hm, am, sport, date, away, home))
            census["updated"] += 1
    conn.commit()
    return census


def against_money(g: dict, open_spread, now_spread) -> dict | None:
    """The spread moved toward the side holding the minority of the money.

    The home number falling (-4.5 → -3.5 for a favourite, +4.5 → +3.5 for a
    dog) is a move TOWARD the home club; rising is toward the away club.
    The money is the split's spread market when it has one, else its
    moneyline. Returns the note's parts, or None."""
    m = (g or {}).get("money") or {}
    s = m.get("spread") or m.get("ml")
    if not s or open_spread is None or now_spread is None:
        return None
    delta = float(now_spread) - float(open_spread)
    if abs(delta) < MIN_MOVE:
        return None
    toward = "home" if delta < 0 else "away"
    home_share = float(s.get("home") or 0)
    money_on = "home" if home_share >= MONEY_SIDE else "away" if home_share <= 1 - MONEY_SIDE else None
    if money_on is None or money_on == toward:
        return None
    return {"toward": toward, "money_on": money_on,
            "money_share": round(max(home_share, 1 - home_share), 3), "delta": round(delta, 1)}


def attach(conn, sport: str, games, now: float | None = None) -> int:
    """``line_open`` on every game with a stored opener. Returns games stamped."""
    from .crowd import home_spread
    ensure_tables(conn)
    n = 0
    for g in games or []:
        if not isinstance(g, dict):
            continue
        date, away, home = key(g)
        row = conn.execute("SELECT open_ts, open_spread, open_total, open_home_ml, open_away_ml "
                           "FROM line_opens WHERE sport=? AND date=? AND away=? AND home=?",
                           (sport, date, away, home)).fetchone()
        if row is None:
            g.pop("line_open", None)
            continue
        open_ts, o_sp, o_tot, o_hm, o_am = row
        # The current numbers are the game's own — this build's, not the
        # table's "now" columns, which a started game stops updating.
        n_sp = home_spread(g) if priced(g) else None
        n_tot = _num(g.get("total")) if priced(g) else None
        out = {"since": _dt.datetime.fromtimestamp(int(open_ts)).isoformat(timespec="minutes"),
               "spread_home": o_sp, "total": o_tot, "home_ml": o_hm, "away_ml": o_am,
               "spread_move": (round(n_sp - o_sp, 1) if n_sp is not None and o_sp is not None else None),
               "total_move": (round(n_tot - o_tot, 1) if n_tot is not None and o_tot is not None else None)}
        rlm = against_money(g, o_sp, n_sp)
        if rlm:
            out["against_money"] = rlm
        g["line_open"] = out
        n += 1
    return n


def attach_to_board(result: dict, sport: str, conn=None, now: float | None = None) -> str:
    """Record, then stamp. One line for the build log; never raises."""
    from . import crowd
    try:
        own = conn is None
        if own:
            conn = crowd.connect()
        try:
            games = result.get("games") or []
            c = record(conn, sport, games, now)
            stamped = attach(conn, sport, games, now)
        finally:
            if own:
                conn.close()
    except Exception as exc:                                   # noqa: BLE001
        return f"  ⚠️  {sport.upper()} opening lines: {type(exc).__name__}: {exc}"
    moved = sum(1 for g in games if isinstance(g, dict)
                and ((g.get("line_open") or {}).get("spread_move") or 0))
    rlm = sum(1 for g in games if isinstance(g, dict) and (g.get("line_open") or {}).get("against_money"))
    return (f"  {sport.upper()} opening lines: {c['opened']} opened, {c['updated']} updated, "
            f"{stamped} on the board · {moved} spread(s) moved · {rlm} against the money")
