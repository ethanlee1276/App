"""The one-sided hold, measured instead of assumed.

Ethan circled the anytime-TD card's third confession (2026-08-26):
*"Books don't offer the NO side of this market, so the vig is assumed at
6% rather than measured off both prices."* A two-sided market hands you
its hold — sum the two implied probabilities and read the overround. A
Yes-only market hands you nothing, and summing the Yes prices across
players measures the game's expected touchdowns, not the juice, because
the outcomes are not mutually exclusive. That is why the 6% was assumed:
no feed we have can say the number.

But the number is measurable, just not from prices alone. If you keep
EVERY quote on the board — not our picks, the whole quoted field, which
is what makes the estimate unbiased where the graded journal cannot be —
and settle each one against what actually happened, then over enough
quotes:

    hold  ≈  (sum of raw implied probabilities) / (number who scored)

because a book's raw Yes prices systematically overstate the truth by
exactly its juice. So this module journals the full quoted board at
build time (a handful of rows per player, identities and prices only),
settles it a day later from the same weekly TD rows that grade the
journal, and fits a per-market hold once the sample is real. Until then
`load_hold` answers None and the pricing keeps its conservative
assumption — a measured number arrives with the season, never before it.

The names on the quotes are the SLATE's names (the odds layer already
matched book spellings to nflverse spellings before anything lands
here), so settlement joins cleanly against ``player_game_logs``. A
quoted player with no stat row in a played week is treated as a
scratch — books void those tickets, so the fit must too, or every
healthy scratch would count as juice.

Standard library only; rows live in the history DB beside the logs that
settle them.
"""

from __future__ import annotations

import json
import os
import time

from .odds import american_to_prob

#: Below this many settled quotes the ratio is noise wearing a decimal
#: point — a single NFL week quotes roughly a thousand player-books, so
#: the gate clears within the season's first fortnight.
MIN_SETTLED = 800

#: Sanity rails on the fitted hold. Outside these the data is broken
#: (a settlement bug, a half-ingested week), not the market: real
#: one-sided holds live in single digits either side of the assumption.
HOLD_RAILS = (1.02, 1.20)

#: Where the fitted numbers land — small JSON beside the other feed
#: state (the relative path every feedstate file uses; builds run from
#: the repo root), read lazily by the pricing path with the assumption
#: as its fallback.
STATE_PATH = os.path.join("data", "feedstate", "hold.json")


def ensure_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS quote_board (
        sport       TEXT NOT NULL,
        season      INTEGER NOT NULL,
        week        INTEGER NOT NULL,
        player      TEXT NOT NULL,
        market      TEXT NOT NULL,
        book        TEXT NOT NULL,
        odds        INTEGER NOT NULL,
        implied     REAL NOT NULL,
        outcome     REAL,
        settled     INTEGER NOT NULL DEFAULT 0,
        recorded_at REAL NOT NULL,
        PRIMARY KEY (sport, season, week, player, market, book)
    )""")
    conn.commit()


def record_slate(conn, slate, sport: str, season: int, week: int,
                 market: str = "anytime_td") -> int:
    """Journal every real quote the slate carries for ``market``.

    REPLACE on the primary key, deliberately: each rebuild before
    kickoff overwrites with the fresher price, so what settles is the
    last quote we saw — the nearest thing to a closing number this
    journal can hold. Identities and prices only; no model output rides
    along, so the table can never leak a projection.
    """
    ensure_table(conn)
    n = 0
    now = time.time()
    for prop in getattr(slate, "props", []):
        if prop.market != market or not prop.lines:
            continue
        for ln in prop.lines:
            odds = int(ln.over_odds)
            conn.execute(
                "INSERT OR REPLACE INTO quote_board (sport, season, week, "
                "player, market, book, odds, implied, outcome, settled, "
                "recorded_at) VALUES (?,?,?,?,?,?,?,?,NULL,0,?)",
                (sport, int(season), int(week), prop.player, market,
                 str(ln.book or "book"), odds, american_to_prob(odds), now))
            n += 1
    conn.commit()
    return n


def settle(conn, sport: str = "nfl", market: str = "anytime_td") -> int:
    """Grade unsettled quotes against the ingested weekly TD rows.

    A week settles only when it has stat rows at all — before then the
    games have not been played (or the file has not updated) and the
    quotes simply wait. Within a settleable week, a quoted player with
    no row is a scratch: ``settled=1, outcome NULL``, excluded from the
    fit exactly as a book's void excludes the ticket from its handle.
    """
    ensure_table(conn)
    n = 0
    weeks = conn.execute(
        "SELECT DISTINCT season, week FROM quote_board "
        "WHERE sport=? AND market=? AND settled=0", (sport, market))
    for sw in weeks.fetchall():
        season, week = int(sw["season"]), int(sw["week"])
        rows = conn.execute(
            "SELECT player, SUM(value) AS v FROM player_game_logs "
            "WHERE sport=? AND season=? AND period=? AND market=? "
            "GROUP BY player",
            (sport, season, f"{week:03d}", market)).fetchall()
        if not rows:
            continue
        scored = {r["player"]: 1.0 if float(r["v"] or 0) > 0 else 0.0
                  for r in rows}
        for r in conn.execute(
                "SELECT DISTINCT player FROM quote_board WHERE sport=? "
                "AND market=? AND season=? AND week=? AND settled=0",
                (sport, market, season, week)).fetchall():
            out = scored.get(r["player"])
            conn.execute(
                "UPDATE quote_board SET outcome=?, settled=1 WHERE sport=? "
                "AND market=? AND season=? AND week=? AND player=?",
                (out, sport, market, season, week, r["player"]))
            n += 1
    conn.commit()
    return n


def fit(conn, sport: str = "nfl", market: str = "anytime_td") -> dict | None:
    """Fit the hold off every settled, non-void quote and write it out.

    Returns the entry written, or None when the gate or the rails said
    the number is not ready to be believed. Writing happens through the
    whole-file replace the other feed states use.
    """
    ensure_table(conn)
    row = conn.execute(
        "SELECT COUNT(*) AS n, SUM(implied) AS imp, SUM(outcome) AS hit "
        "FROM quote_board WHERE sport=? AND market=? AND settled=1 "
        "AND outcome IS NOT NULL", (sport, market)).fetchone()
    n = int(row["n"] or 0)
    if n < MIN_SETTLED or not row["hit"]:
        return None
    hold = float(row["imp"]) / float(row["hit"])
    if not (HOLD_RAILS[0] <= hold <= HOLD_RAILS[1]):
        return None
    entry = {"hold": round(hold, 4), "n": n, "fit_at": time.time()}
    state = {}
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    state[f"{sport}:{market}"] = entry
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    _cache.clear()
    return entry


_cache: dict = {}


def load_hold(sport: str, market: str) -> dict | None:
    """``{"hold": 1.08, "n": 1234}`` when measured, else None.

    Never raises: the pricing path calls this on every one-sided quote
    and a broken state file must cost the measurement, not the board.
    """
    key = f"{sport}:{market}"
    if key in _cache:
        return _cache[key]
    entry = None
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            entry = (json.load(fh) or {}).get(key)
        if entry is not None and not (
                isinstance(entry, dict) and entry.get("hold")
                and HOLD_RAILS[0] <= float(entry["hold"]) <= HOLD_RAILS[1]):
            entry = None
    except (OSError, ValueError):
        entry = None
    _cache[key] = entry
    return entry
