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


def attach(result: dict, sport: str, kalshi_markets=None, poly_rows=None) -> dict:
    """Hang ``crowd`` on every game a venue priced. Returns a census."""
    from .sources import kalshi, polysports
    games = [g for g in result.get("games") or [] if isinstance(g, dict)]
    census = {"games": len(games), "kalshi": 0, "polymarket": 0}
    if not games:
        return census
    named = _xf.with_names(games, sport)
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
    for r in poly_rows or []:
        if r.get("sport") not in (None, sport) or poly_quality(r):
            continue
        g, first_home = polysports.match_game(r, named)
        if g is not None and key(g) not in px:
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
        if not c:
            g.pop("crowd", None)
            continue
        b = book_p_home(g)
        if b is not None:
            c["books"] = b
        venues = [c[v] for v in ("kalshi", "polymarket") if c.get(v) is not None]
        c["crowd"] = round(sum(venues) / len(venues), 4)
        if b is not None:
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
    conn.commit()
    return n


def attach_to_board(result: dict, sport: str, kalshi_fetch=None, poly_fetch=None,
                    conn=None, record: bool = True) -> str:
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
    try:
        prow, report = (poly_fetch or (lambda: polysports.fetch_sports([sport])))()
        result["polymarket_tags"] = report
    except Exception as exc:                                   # noqa: BLE001
        prow = []
        notes.append(f"Polymarket unavailable ({type(exc).__name__})")
    try:
        census = attach(result, sport, kmk, prow)
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
            f"{census['polymarket']} of {census['games']} games · {stored} recorded"
            + (f" · {'; '.join(notes)}" if notes else ""))
