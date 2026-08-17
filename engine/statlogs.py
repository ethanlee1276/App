"""Multi-market game logs for the players on tonight's board.

Ethan, 2026-08-17: "when i search an nfl player it will only display yard
props with that chart, but i also wanna be able to maybe see reception
props with the chart … and same for mlb, i wanna see more then just bases
prop chart when i look them up."

The site had the answer all along: data/history.db stores one row per
(player, market, game) for every ingested market — receptions, targets,
carries and the yardage families for the NFL; bases, hits, homers and the
pitcher markets for MLB. The board simply never shipped them: each
recommendation carries logs for ITS market only, and the Players page
drew the first recommendation it found and discarded the rest.

This module reads the other markets for exactly the players already on
tonight's board and the pipelines attach the result as
``payload["player_stats"]``:

    {player: {market_label: [{"week"|"date", "opponent", "home", "value"},
                             ...newest first]}}

Game logs are FACTS, not picks — the section rides through gate.redact()
untouched on free copies, the same footing as rosters and injuries.

Honest degradation: a machine without the history DB (fresh clone, CI)
builds a board whose section is empty, and the Players page offers the
priced markets it always offered. A machine WITH the DB — the droplet,
the laptop — fills the chips in. The asymmetry is deliberate and matches
every other DB-backed extra (player faces, team form, venue weather).
"""

from __future__ import annotations

import os

from . import db as _db

#: market id -> chip label, in DISPLAY ORDER. Deliberately wider than the
#: markets any board prices (targets, carries): the Players page answers
#: "how has he been doing", not "what is priced tonight".
SPORT_MARKETS = {
    "nfl": (("pass_yds", "Passing Yards"), ("rush_yds", "Rushing Yards"),
            ("rec_yds", "Receiving Yards"), ("receptions", "Receptions"),
            ("targets", "Targets"), ("carries", "Carries"),
            # Same label the priced market wears (engine/models.py
            # MARKET_LABELS) — the page dedupes chips BY LABEL, so a
            # different spelling here would put the same stat on two
            # chips whenever the market is also priced.
            ("anytime_td", "Anytime TD")),
    "mlb": (("total_bases", "Total Bases"), ("hits", "Hits"),
            ("home_runs", "Home Runs"), ("strikeouts", "Strikeouts"),
            ("outs", "Outs Recorded")),
}

N_GAMES = 10       # what a profile chart can legibly hold
MIN_GAMES = 3      # below this a chart is an anecdote, so it is not drawn


def for_board(recommendations, sport: str, db_path=None) -> dict:
    """``player_stats`` for every player named in ``recommendations``.

    Missing DB file -> ``{}`` on purpose (see the module header). A DB
    that exists but cannot be queried RAISES: half a database is a broken
    machine, and the silent-failure tax was already paid once this month
    (launch.py's three-day quiet build guillotine).
    """
    markets = SPORT_MARKETS.get(sport)
    players = sorted({r.get("player") for r in recommendations or []
                      if isinstance(r, dict) and r.get("player")})
    if not markets or not players:
        return {}
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        return _query(conn, sport, markets, players)
    finally:
        conn.close()


def _query(conn, sport, markets, players) -> dict:
    ids = [m for m, _ in markets]
    labels = dict(markets)
    rows = conn.execute(
        "SELECT player, market, period, opponent, home, value "
        "FROM player_game_logs "
        f"WHERE sport=? AND market IN ({','.join('?' * len(ids))}) "
        f"AND player IN ({','.join('?' * len(players))}) "
        # Zero-padded NFL weeks ('018') and ISO MLB dates both sort
        # correctly as text; season first so a January game cannot
        # outrank a September one on week number alone.
        "ORDER BY season DESC, period DESC",
        [sport, *ids, *players]).fetchall()
    grouped: dict[str, dict[str, list]] = {}
    for r in rows:
        per = grouped.setdefault(r["player"], {})
        lst = per.setdefault(r["market"], [])
        if len(lst) >= N_GAMES:
            continue
        g = {"opponent": r["opponent"], "home": bool(r["home"]),
             "value": float(r["value"])}
        # Same field names the existing per-market logs use, so the page
        # formats both with one code path: NFL logs are weeks, MLB games.
        if sport == "nfl":
            g["week"] = int(r["period"])
        else:
            g["date"] = str(r["period"])
        lst.append(g)
    # Rebuild in SPORT_MARKETS order — JSON keeps insertion order and the
    # page renders chips in payload order, so display order is decided
    # HERE, once, not per surface.
    out: dict[str, dict[str, list]] = {}
    for player, per in grouped.items():
        keep = {labels[m]: per[m] for m, _ in markets
                if len(per.get(m, [])) >= MIN_GAMES}
        if keep:
            out[player] = keep
    return out
