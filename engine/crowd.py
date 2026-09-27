"""Every venue's price on a game, side by side, and a record of it.

Ethan, 2026-09-26: "we should also look into where we can use pollymarket
and kalshi odds for money lines and other bets since crowd betting is
more accurate when it comes to what's right and wrong ... we can study
market swings ... because usually a market has swung a certain way when
a large group of people already know the answer."

WHAT WAS THERE. Kalshi's price reached exactly one place: the Pick of the
Day's evidence ladder (`engine/exchangefair`), and only on Most Likely
moneyline rows. The game page, the game bets and the Edge board never
saw it, Polymarket's game markets were never read at all, and nothing
anywhere recorded the prices side by side — so "is the crowd more
accurate than the books?" has never had a single row to answer it with.

WHAT THIS DOES. For every game on a board it hangs one block, ``crowd``:
the win chance for the HOME club from each source that priced the game —

    kalshi       the exchange's mid (a real, tight, liquid book only)
    polymarket   the venue's moneyline (same guards)
    books        the sportsbooks' price, de-vigged
— and writes them to ``crowd_snaps`` on every build while the game has
not started, beside our own two numbers: the card's (after its measured
shrink) and the engine's before it. OURS ARE RECORDED, NEVER HUNG ON THE
GAME: `game_bets` is a paid key and `games` is public, so a model number
on the game would hand every visitor the paid moneyline for free. That table is the whole experiment: a game's
prices over its last pregame hours, joined later to the final score by
`engine/crowdfit`, which measures which source is most accurate, whether
a gap between the crowd and the books predicts the result, and whether a
late swing keeps going.

NOTHING HERE MOVES A PICK. The page shows the numbers; `crowdfit` says
whether they earn a say, and nothing is wired into pricing until it does.
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import time
from pathlib import Path

from . import exchangefair as _xf

#: Polymarket's guards, the same three `exchangefair` holds Kalshi to: a
#: two-sided book, tight, and liquid. Polymarket reports liquidity in
#: dollars resting on the book, a bigger number than Kalshi's contract
#: counts, so its floor is higher.
POLY_MAX_SPREAD_CENTS = 4.0
POLY_MIN_LIQUIDITY = 1000.0

#: One stored row per game per bucket, so a board built every few
#: minutes does not write the same prices forty times an hour.
SNAP_BUCKET_S = 900

#: ITS OWN FILE, not the history database. The box, 2026-09-26: college
#: recorded 0 of 13 priced games while `live_build` logged "database is
#: locked" on history.db — every builder and the live loop write there. A
#: few rows a build need nothing else, and waiting on nobody is the point.
DB_PATH = Path(os.environ.get("QB_CROWD_DB", "").strip()
               or (Path(__file__).resolve().parents[1] / "data" / "crowd.db"))


def connect(path=None):
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30)
    ensure_tables(conn)
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS crowd_snaps (
    sport TEXT, date TEXT, away TEXT, home TEXT, bucket_ts INTEGER,
    kickoff TEXT, kalshi REAL, polymarket REAL, books REAL,
    model REAL, model_raw REAL,
    kalshi_spread REAL, poly_spread REAL,
    PRIMARY KEY (sport, date, away, home, bucket_ts)
);
CREATE TABLE IF NOT EXISTS crowd_lines (
    sport TEXT, date TEXT, away TEXT, home TEXT, bucket_ts INTEGER,
    kind TEXT, line REAL, venue TEXT, p REAL, spread_cents REAL,
    PRIMARY KEY (sport, date, away, home, bucket_ts, kind, venue)
);
"""


def poly_quality(row: dict) -> str:
    """"" if this Polymarket moneyline is worth using, else why not."""
    if str(row.get("price_basis") or "") != "book":
        return "no two-sided book — only a last trade"
    sp = row.get("spread_cents")
    if sp is None or float(sp) > POLY_MAX_SPREAD_CENTS:
        return "book too wide" if sp is not None else "no quoted spread"
    if max(float(row.get("liquidity") or 0), float(row.get("volume_24h") or 0)) < POLY_MIN_LIQUIDITY:
        return "thin"
    return ""


def home_spread(g: dict) -> float | None:
    """The board's line as the HOME club's number (−3.5 = home gives 3.5).
    `spread` is stored as a size and `favorite` names who gives it."""
    try:
        size = abs(float(g.get("spread")))
    except (TypeError, ValueError):
        return None
    fav = str(g.get("favorite") or g.get("home") or "")
    return -size if fav == str(g.get("home") or "") else size


def crowd_lines(row: dict, g: dict, first_is_home: bool) -> dict:
    """The venue's price on THE BOARD'S OWN spread and total — the same bet
    the books are quoting, and only that. A venue line half a point away is
    a different bet and is left out rather than stretched to fit.

        spread_home_line   the board's line, home club's number
        poly_home_cover    P(home covers it), Polymarket
        total_line         the board's total
        poly_over          P(over it), Polymarket
    """
    from .sources import polysports
    out: dict = {}
    hl, tot = home_spread(g), g.get("total")
    for ln in row.get("lines") or []:
        if poly_quality(ln):
            continue
        if ln.get("kind") == "spread" and hl is not None and "poly_home_cover" not in out:
            is_home = polysports._club(str(ln.get("team") or ""), g, "home")
            is_away = polysports._club(str(ln.get("team") or ""), g, "away")
            if is_home == is_away:
                continue                      # names both or neither: not ours to guess
            venue_home_line = float(ln["line"]) if is_home else -float(ln["line"])
            if abs(venue_home_line - hl) < 0.01:
                p = float(ln["p"])
                out.update(spread_home_line=hl, poly_home_cover=round(p if is_home else 1.0 - p, 4))
        elif ln.get("kind") == "total" and tot is not None and "poly_over" not in out:
            try:
                same = abs(float(ln["line"]) - float(tot)) < 0.01
            except (TypeError, ValueError):
                same = False
            if same:
                out.update(total_line=float(tot), poly_over=round(float(ln["p"]), 4))
    return out


_MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG",
                                        "SEP", "OCT", "NOV", "DEC"), start=1)}


def _kalshi_event_game(event_ticker: str) -> tuple[str, str] | None:
    """``(date, clubs)`` out of a line event ticker —
    "KXNFLSPREAD-26SEP27CARCLE" → ("2026-09-27", "CARCLE"); baseball's
    carries a start time too ("26SEP271505HOUATH"). None if unreadable."""
    import re
    parts = str(event_ticker or "").upper().split("-")
    if len(parts) < 2:
        return None
    m = re.match(r"^(\d{2})([A-Z]{3})(\d{2})\d*([A-Z]+)$", parts[1])
    if not m or m.group(2) not in _MONTHS:
        return None
    return f"20{m.group(1)}-{_MONTHS[m.group(2)]:02d}-{m.group(3)}", m.group(4)


def kalshi_lines(markets, g: dict) -> dict:
    """Kalshi's price on THE BOARD'S OWN spread and total, by the rule
    `crowd_lines` holds Polymarket to: the same bet the books quote, never
    a neighbouring one. Ethan's box, 2026-09-27 (crowdprobe.py) confirmed
    the series; see kalshi.LINE_SERIES for their shape.

    "HOME wins by over F" prices the home club covering −F; "AWAY wins by
    over F" is the home club covering +F, from the other side. So a board
    line matches only a half-point strike of the same size — a −7 has no
    Kalshi twin (its markets are 6.5 and 7.5, each a different bet) and is
    left out rather than stretched. The game is matched by the ticker's
    date and its two clubs, exactly; a club code Kalshi spells differently
    matches nothing, which is the safe way to be wrong.

        kalshi_home_cover   P(home covers the board's line)
        kalshi_over         P(over the board's total)
    """
    out: dict = {}
    hl, tot = home_spread(g), g.get("total")
    home, away = str(g.get("home") or "").upper(), str(g.get("away") or "").upper()
    date = str(g.get("date") or "")[:10]
    for m in markets or []:
        got = _kalshi_event_game(m.get("event_ticker"))
        if not got or got[1] not in (away + home, home + away) or (date and got[0] != date):
            continue
        if _xf.quality(m) or m.get("floor_strike") is None or m.get("strike_type") != "greater":
            continue
        f, p = float(m["floor_strike"]), float(m["prob"])
        series = str(m.get("series") or m.get("event_ticker") or "").upper()
        if "SPREAD" in series and hl is not None and "kalshi_home_cover" not in out:
            club = str(m.get("ticker") or "").upper().rsplit("-", 1)[-1].rstrip("0123456789")
            if club == home and abs(f + hl) < 0.01:
                out.update(spread_home_line=hl, kalshi_home_cover=round(p, 4))
            elif club == away and abs(f - hl) < 0.01:
                out.update(spread_home_line=hl, kalshi_home_cover=round(1.0 - p, 4))
        elif "TOTAL" in series and tot is not None and "kalshi_over" not in out:
            try:
                same = abs(f - float(tot)) < 0.01
            except (TypeError, ValueError):
                same = False
            if same:
                out.update(total_line=float(tot), kalshi_over=round(p, 4))
    return out


def book_p_home(g: dict) -> float | None:
    """The sportsbooks' home win chance, de-vigged, or None."""
    hm, am = g.get("home_ml"), g.get("away_ml")
    try:
        if not hm or not am:
            return None
        from .odds import devig_two_way
        ph, _pa = devig_two_way(int(hm), int(am))
        return round(float(ph), 4)
    except (TypeError, ValueError):
        return None


def model_p_home(game_bets, g: dict) -> tuple[float | None, float | None]:
    """``(card, raw)``: our moneyline card's home win chance, and the
    engine's before the shrink. The card states the PICK's chance, which
    flips team every game, so it is turned to the home side here."""
    for b in game_bets or []:
        if not isinstance(b, dict):
            continue
        if str(b.get("bet_type") or b.get("market") or "") != "moneyline":
            continue
        if b.get("home") != g.get("home") or b.get("away") != g.get("away"):
            continue
        home = bool(b.get("pick_is_home")) if b.get("pick_is_home") is not None \
            else str(b.get("team") or b.get("pick") or "") == str(g.get("home") or "")

        def _h(p):
            if p is None:
                return None
            p = float(p)
            return round(p if home else 1.0 - p, 4)
        return _h(b.get("win_prob")), _h(b.get("engine_raw_prob"))
    return None, None


def _board_names(games, teams) -> list:
    """Games with their clubs' names filled from the board's own ``teams``.

    COLLEGE HAS NO NAME LIST ANYWHERE ELSE. The box, 2026-09-26: 65 of
    Polymarket's college games were on the slate and one matched, because
    every college game carried its codes alone (``FSU``, ``WYO``) and
    `exchangefair.names_for` has no college map. The board ships ESPN's
    identity for every school (`cfbdata.parse_teams`: the full name and
    the short one), so both are joined in — "Florida State Seminoles
    Florida St" — and a venue's "Florida State" finds every word."""
    if not isinstance(teams, dict) or not teams:
        return games
    out = []
    for g in games:
        row = dict(g)
        for side in ("home", "away"):
            key = f"{side}_name"
            t = teams.get(str(row.get(side) or ""))
            if not str(row.get(key) or "").strip() and isinstance(t, dict):
                row[key] = " ".join(str(t.get(k) or "") for k in ("name", "nick")).strip()
        out.append(row)
    return out


def attach(result: dict, sport: str, kalshi_markets=None, poly_rows=None,
           kalshi_line_markets=None) -> dict:
    """Hang ``crowd`` on every game a venue priced. Returns a census."""
    from .sources import kalshi, polysports
    games = [g for g in result.get("games") or [] if isinstance(g, dict)]
    census = {"games": len(games), "kalshi": 0, "polymarket": 0, "poly_spread": 0, "poly_total": 0,
              "kalshi_spread": 0, "kalshi_total": 0}
    if not games:
        return census
    named = _xf.with_names(_board_names(games, result.get("teams")), sport)
    key = lambda g: (str(g.get("away") or ""), str(g.get("home") or ""))  # noqa: E731
    kx: dict = {}
    for m in kalshi_markets or []:
        if kalshi.sport_of(m) not in (None, sport) or _xf.quality(m):
            continue
        g, _why = kalshi.match_game_verbose(m, named)
        if g is None:
            continue
        p = _xf.fair_for_team(m, g.get("home"), g)
        if p is not None and key(g) not in kx:
            kx[key(g)] = (p, m.get("spread_cents"))
    px: dict = {}
    pl: dict = {}
    for r in poly_rows or []:
        if r.get("sport") not in (None, sport):
            continue
        g, first_home = polysports.match_game(r, named)
        if g is None:
            continue
        # The spread and the total ride on the event even when its
        # moneyline book is too thin to use.
        if key(g) not in pl:
            got = crowd_lines(r, g, first_home)
            if got:
                pl[key(g)] = got
        if not poly_quality(r) and key(g) not in px:
            px[key(g)] = (polysports.p_home(r, first_home), r.get("spread_cents"))
    for g in games:
        k = key(g)
        c = {}
        if k in kx:
            c["kalshi"], c["kalshi_spread"] = kx[k]
            census["kalshi"] += 1
        if k in px:
            c["polymarket"], c["poly_spread"] = px[k]
            census["polymarket"] += 1
        lines = dict(pl.get(k) or {})
        lines.update(kalshi_lines(kalshi_line_markets, g))
        census["poly_spread"] += "poly_home_cover" in lines
        census["poly_total"] += "poly_over" in lines
        census["kalshi_spread"] += "kalshi_home_cover" in lines
        census["kalshi_total"] += "kalshi_over" in lines
        if not c and not lines:
            g.pop("crowd", None)
            continue
        b = book_p_home(g)
        if b is not None:
            c["books"] = b
        c.update(lines)
        venues = [c[v] for v in ("kalshi", "polymarket") if c.get(v) is not None]
        if venues:
            c["crowd"] = round(sum(venues) / len(venues), 4)
        if b is not None and c.get("crowd") is not None:
            # + means the crowd rates the home club higher than the books.
            c["gap_pts"] = round((c["crowd"] - b) * 100.0, 1)
        g["crowd"] = c
    return census


# --- the record -------------------------------------------------------------
def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)


def started(g: dict, now: float | None = None) -> bool:
    """Has this game begun? The live state first; else the kickoff, which
    is ISO time on the daily boards and a bare Eastern clock beside
    ``date`` on football's (`oddsapi` notes the same split)."""
    state = str(((g.get("live") or {}).get("state")) or "").lower()
    if state in ("live", "in", "final", "post"):
        return True
    now = time.time() if now is None else now
    ko = str(g.get("kickoff") or "")
    try:
        if "T" in ko:
            t = _dt.datetime.fromisoformat(ko.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=_dt.timezone.utc)
            return t.timestamp() <= now
        if ko and g.get("date"):
            from zoneinfo import ZoneInfo
            t = _dt.datetime.fromisoformat(f"{str(g['date'])[:10]}T{ko[:5]}").replace(
                tzinfo=ZoneInfo("America/New_York"))
            return t.timestamp() <= now
    except (ValueError, KeyError):
        return False
    return False


def store(conn, sport: str, games, now: float | None = None, game_bets=None) -> int:
    """Write this build's prices for every game not yet started, with our
    model's two numbers read off ``game_bets`` (never off the game)."""
    ensure_tables(conn)
    now = time.time() if now is None else now
    bucket = int(now // SNAP_BUCKET_S * SNAP_BUCKET_S)
    n = 0
    for g in games or []:
        c = (g or {}).get("crowd") if isinstance(g, dict) else None
        if not c or started(g, now):
            continue
        model, raw = model_p_home(game_bets, g)
        conn.execute(
            "INSERT OR REPLACE INTO crowd_snaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sport, str(g.get("date") or "")[:10], g.get("away"), g.get("home"), bucket,
             str(g.get("kickoff") or ""), c.get("kalshi"), c.get("polymarket"), c.get("books"),
             model, raw, c.get("kalshi_spread"), c.get("poly_spread")))
        n += 1
        date, a, h = str(g.get("date") or "")[:10], g.get("away"), g.get("home")
        for kind, line_key, p_key, venue in (("spread_home", "spread_home_line", "poly_home_cover", "polymarket"),
                                             ("over", "total_line", "poly_over", "polymarket"),
                                             ("spread_home", "spread_home_line", "kalshi_home_cover", "kalshi"),
                                             ("over", "total_line", "kalshi_over", "kalshi")):
            if c.get(p_key) is not None:
                conn.execute("INSERT OR REPLACE INTO crowd_lines VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (sport, date, a, h, bucket, kind, c.get(line_key), venue,
                              c[p_key], None))
    conn.commit()
    return n


def attach_to_board(result: dict, sport: str, kalshi_fetch=None, poly_fetch=None,
                    conn=None, record: bool = True, kalshi_line_fetch=None) -> str:
    """One hook, every build: fetch both venues, hang ``crowd`` on the
    games, record the pregame prices. NEVER RAISES — each venue is its own
    failure domain, and a crowd price is never the reason a board fails.
    Returns a log line; the census lands in the JSON as ``crowd_census``."""
    from .sources import kalshi, polysports
    notes = []
    try:
        kmk, _series = (kalshi_fetch or (lambda: kalshi.fetch_sports_markets(kalshi.parse_markets)))()
    except Exception as exc:                                   # noqa: BLE001
        kmk = []
        notes.append(f"Kalshi unavailable ({type(exc).__name__})")
    # An injected moneyline feed means a test or a replay: the line series
    # are then read only when injected too, never fetched behind its back.
    if kalshi_line_fetch is None and kalshi_fetch is not None:
        kalshi_line_fetch = list
    try:
        kline = (kalshi_line_fetch or (lambda: kalshi.fetch_line_markets(sport)))()
    except Exception as exc:                                   # noqa: BLE001
        kline = []
        notes.append(f"Kalshi lines unavailable ({type(exc).__name__})")
    try:
        prow, report = (poly_fetch or (lambda: polysports.fetch_sports([sport])))()
        result["polymarket_tags"] = report
    except Exception as exc:                                   # noqa: BLE001
        prow = []
        notes.append(f"Polymarket unavailable ({type(exc).__name__})")
    try:
        census = attach(result, sport, kmk, prow, kline)
    except Exception as exc:                                   # noqa: BLE001
        result["crowd_error"] = f"{type(exc).__name__}: {exc}"
        return f"  ⚠️  {sport.upper()} crowd prices: {exc}"
    stored = 0
    if record:
        try:
            own = conn is None
            if own:
                conn = connect()
            try:
                stored = store(conn, sport, result.get("games") or [],
                               game_bets=result.get("game_bets") or [])
            finally:
                if own:
                    conn.close()
        except Exception as exc:                               # noqa: BLE001
            notes.append(f"not recorded ({type(exc).__name__}: {exc})")
    census["recorded"] = stored
    result["crowd_census"] = census
    return (f"  {sport.upper()} crowd prices: Kalshi on {census['kalshi']}, Polymarket on "
            f"{census['polymarket']} of {census['games']} games (spread {census['poly_spread']}, "
            f"total {census['poly_total']}; Kalshi spread {census['kalshi_spread']}, "
            f"total {census['kalshi_total']}) · {stored} recorded"
            + (f" · {'; '.join(notes)}" if notes else ""))
