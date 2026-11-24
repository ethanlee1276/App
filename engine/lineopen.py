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

THE "NOW" COLUMNS ARE THE CLOSE (2026-10-15). They stop at kickoff, so
the row left standing is the last line the board read before the game —
and the ledger banks it as a settled moneyline's or total's close
(`ledger._game_close`): the game lines' only close, since the stores the
props close from carry none. So a price the board marks as dated
(``price_stale``: past oddsapi.MAX_GAME_PRICE_AGE, shown for up to two
days) never moves them: a day-old number would pass for the close.

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


#: THE ROAD FAVOURITE'S SIGN, MENDED ONCE (step ADT, 2026-11-24). Until then
#: crowd.home_spread took the home club for the favourite on every board that
#: names none — every league but the NFL — so each game a road side was
#: favoured in was stored with its line on the other side of zero, open and
#: close alike. The row's own moneylines, taken in the same read, say who was
#: favoured: where they name the road side and the stored line has the home
#: club giving points, the line is flipped. Once, recorded in
#: `line_open_fixes`: a row written since is the board's own number, and a
#: book's spread and moneyline that disagree on a pick'em are left as read.
SIGN_FIX = "road_favourite_sign_2026_11_24"


def repair_signs(conn) -> int:
    """Flip the spreads stored the wrong way round before step ADT, once.
    Returns the columns flipped (an open and a close count apart); 0 when
    the repair has already run. Never touches the NFL's rows, whose board
    always named its favourite."""
    ensure_tables(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS line_open_fixes (name TEXT PRIMARY KEY, at INTEGER, rows INTEGER)")
    if conn.execute("SELECT 1 FROM line_open_fixes WHERE name=?", (SIGN_FIX,)).fetchone():
        return 0
    n = 0
    for col, hm, am in (("open_spread", "open_home_ml", "open_away_ml"),
                        ("now_spread", "now_home_ml", "now_away_ml")):
        # The old rule only ever stored a home favourite's number (zero or
        # less); the road side's shorter price says it was the road's.
        n += conn.execute(
            f"UPDATE line_opens SET {col} = -{col} WHERE sport != 'nfl' AND {col} < 0 "
            f"AND {hm} IS NOT NULL AND {am} IS NOT NULL AND {am} < {hm}").rowcount
    conn.execute("INSERT OR IGNORE INTO line_open_fixes VALUES (?,?,?)", (SIGN_FIX, int(time.time()), n))
    conn.commit()
    return n


def record(conn, sport: str, games, now: float | None = None) -> dict:
    """First-seen numbers written once; ``now`` columns every build on a
    current price (a dated one opens a row but never moves them). Started
    games are left alone (engine/crowd.started). Returns a census."""
    from .crowd import home_spread, started
    ensure_tables(conn)
    repair_signs(conn)
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
        dated = bool(g.get("price_stale"))
        if row is None:
            now_cols = (None,) * 5 if dated else (ts, sp, tot, hm, am)
            conn.execute("INSERT INTO line_opens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (sport, date, away, home, ts, sp, tot, hm, am, *now_cols))
            census["opened"] += 1
        elif not dated:
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


def total_against_money(g: dict, open_total, now_total) -> dict | None:
    """The total moved toward the side holding the minority of the money
    (2026-11-14). Ethan's Commanders–Giants research: "the total dropped from
    43.5 to 40.5 even though about 70% of bets and money backed the over,
    which usually means sharp money is on the under". The split's total
    market (`money.total.over`, engine/moneysplit), the same bars as the
    spread's (MIN_MOVE, MONEY_SIDE). Returns the note's parts, or None."""
    t = ((g or {}).get("money") or {}).get("total") or {}
    if not t or t.get("over") is None or open_total is None or now_total is None:
        return None
    delta = float(now_total) - float(open_total)
    if abs(delta) < MIN_MOVE:
        return None
    toward = "under" if delta < 0 else "over"
    over = float(t.get("over") or 0)
    money_on = "over" if over >= MONEY_SIDE else "under" if over <= 1 - MONEY_SIDE else None
    if money_on is None or money_on == toward:
        return None
    return {"toward": toward, "money_on": money_on, "money_share": round(max(over, 1 - over), 3),
            "delta": round(delta, 1)}


def attach(conn, sport: str, games, now: float | None = None) -> int:
    """``line_open`` on every game with a stored opener. Returns games stamped.

    A STARTED GAME CARRIES ITS CLOSE (step ADT, 2026-11-24): ``close``, the
    `now_*` columns the board stopped writing at the start — the line the
    Record grades a game bet against. The board's own fields do not keep it:
    hockey's finished games lost theirs on the first build after midnight,
    college basketball's as each game ended, and the NFL's moneylines went to
    the not-offered zero, so a finished game's page read "—" in one league
    and its closing numbers in the NBA's. ESPN's page for a finished game
    still names the line; every league's now does, from here."""
    from .crowd import home_spread, started
    ensure_tables(conn)
    n = 0
    for g in games or []:
        if not isinstance(g, dict):
            continue
        date, away, home = key(g)
        row = conn.execute("SELECT open_ts, open_spread, open_total, open_home_ml, open_away_ml, "
                           "now_ts, now_spread, now_total, now_home_ml, now_away_ml "
                           "FROM line_opens WHERE sport=? AND date=? AND away=? AND home=?",
                           (sport, date, away, home)).fetchone()
        if row is None:
            g.pop("line_open", None)
            continue
        open_ts, o_sp, o_tot, o_hm, o_am, c_ts, c_sp, c_tot, c_hm, c_am = row
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
        trlm = total_against_money(g, o_tot, n_tot)
        if trlm:
            out["total_against_money"] = trlm
        if c_ts is not None and started(g, now):
            out["close"] = {"spread_home": c_sp, "total": c_tot, "home_ml": _ml(c_hm), "away_ml": _ml(c_am)}
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
    dated = sum(1 for g in games if isinstance(g, dict) and priced(g) and g.get("price_stale"))
    return (f"  {sport.upper()} opening lines: {c['opened']} opened, {c['updated']} updated, "
            f"{stamped} on the board · {moved} spread(s) moved · {rlm} against the money"
            + (f" · {dated} dated price(s) kept out of the close" if dated else ""))
