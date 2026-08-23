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
import re

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
    # Hoops joined for the league-wide search (2026-08-18). Labels match
    # engine/nba/pipeline.MARKET_LABELS for the same dedupe-by-label
    # reason the anytime_td comment gives.
    "nba": (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
            ("fg3m", "3-Pointers Made")),
    "wnba": (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
             ("fg3m", "3-Pointers Made")),
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


def _face_of(conn, sport: str, player: str) -> str:
    """The sport's own headshot for a name, or "". Never raises.

    A search result with no photo is a page that looks unfinished; a
    search endpoint that throws because a roster feed is down is a page
    that does not load at all. This is the first of those on purpose.
    """
    try:
        from . import rosters
        return rosters.face_of(rosters.face_map(conn, sport), player)
    except Exception:                                        # noqa: BLE001
        return ""


def search(sport: str, q: str, limit: int = 12, db_path=None) -> list[dict]:
    """Every player in the league whose name contains ``q``, newest first.

    Ethan, 2026-08-18: "You should be able too look up any player in the
    league too that specific sport." The board only knows tonight's
    priced players; THIS knows everyone who has ever appeared in an
    ingested game for the sport — which is the league, as a bettor means
    it. Ranked by most recent appearance, then games played, so a current
    starter outranks a 2021 namesake.

    Same honest degradation as ``for_board``: no DB, empty list.
    """
    q = (q or "").strip()
    if not q or sport not in SPORT_MARKETS:
        return []
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return []
    conn = _db.connect(path)
    try:
        return _search_conn(conn, sport, q, limit)
    finally:
        conn.close()


def _search_conn(conn, sport: str, q: str, limit: int) -> list[dict]:
    """One league's hits on an already-open connection.

    Split out so the all-league search opens the database once instead of
    once per sport — five connections to answer one keystroke, on a box
    with one core, is a cost the page pays on every letter typed.
    """
    rows = conn.execute(
        "SELECT player, COUNT(DISTINCT game_id) AS games, "
        "MAX(season || '-' || period) AS last "
        "FROM player_game_logs WHERE sport=? AND player LIKE ? "
        "GROUP BY player ORDER BY last DESC, games DESC LIMIT ?",
        (sport, f"%{q}%", int(limit))).fetchall()
    out = []
    for r in rows:
        # The team he was LAST seen with — the GROUP BY above would
        # hand back an arbitrary row's team, and a deadline trade is
        # exactly when someone gets looked up.
        t = conn.execute(
            "SELECT team, position FROM player_game_logs "
            "WHERE sport=? AND player=? "
            "ORDER BY season DESC, period DESC LIMIT 1",
            (sport, r["player"])).fetchone()
        # The face rides along when the ingest has stored one —
        # player_assets is in the same DB, and a search result
        # without the photo is the page Ethan keeps noticing.
        #
        # AND WHEN IT HAS NOT, WHICH IS MOST SPORTS. Only the hoops
        # ingest writes `player_assets`: ESPN's box score hands over a
        # photo href, so NBA and WNBA faces are taken. The MLB Stats
        # API publishes no photo URL — MLB's face is CONSTRUCTED from
        # the person id — and nothing writes NFL's here either. So
        # this table answered for basketball and returned nothing for
        # everyone else, and every MLB search result drew initials.
        # Ethan, 2026-08-22: "headshots are not loading on the search
        # page for players."
        #
        # `rosters.face_map` already knew all of this per sport. It
        # is memoised there, so this is one lookup per request rather
        # than a roster fetch per row.
        face = ""
        try:
            a = conn.execute(
                "SELECT headshot FROM player_assets "
                "WHERE sport=? AND player=?",
                (sport, r["player"])).fetchone()
            face = (a["headshot"] if a else "") or ""
        except Exception:                                # noqa: BLE001
            face = ""                # a DB predating the assets table
        if not face:
            face = _face_of(conn, sport, r["player"])
        # The LEAGUE rides on every hit. Search spans all of them
        # now, so "which sport is this?" is a question the row has to
        # answer for itself — the page reads it to pick the right
        # team colours, the right logo host and the right injury
        # board, all of which are keyed by abbreviations that collide
        # across leagues (CIN, ATL, SF, TB).
        out.append({"player": r["player"], "games": int(r["games"]),
                    "sport": sport,
                    "team": (t["team"] if t else "") or "",
                    "position": (t["position"] if t else "") or "",
                    "headshot": face})
    return out


def _leads_with(name: str, q: str) -> bool:
    """Does ``q`` start the name, or start any word in it?

    "mahomes" leading Patrick Mahomes has to outrank "mahomes" merely
    appearing inside somebody else's name, or the league that happens to
    sort first eats the whole result list.
    """
    n = (name or "").lower()
    ql = (q or "").lower()
    if not ql:
        return False
    return n.startswith(ql) or any(
        w.startswith(ql) for w in re.split(r"[^a-z0-9]+", n) if w)


def search_all(q: str, limit: int = 12, prefer: str = "",
               db_path=None) -> list[dict]:
    """Every player in EVERY league whose name contains ``q``.

    Ethan, 2026-08-23: "searching for a player should search through ALL
    players for ALL sports. so even if im selected on nfl, i shoudl still
    be able to look up mlb or ufc or wnba players." A search box that
    silently scopes itself to whichever tab you happen to be on is a
    search box you cannot trust — you type a name, get nothing, and have
    no way to tell "he isn't in our data" from "you're on the wrong tab".

    ROUND-ROBIN, NOT ONE BIG SORT. The per-league ranking key is
    ``season || '-' || period``, and period means different things in
    different leagues — a zero-padded NFL week ('005') against an ISO
    baseball date ('2026-08-14'). Those sort against each other as
    nonsense, so one merged ORDER BY would hand the list to whichever
    league's format sorts highest and call it relevance. Taking one hit
    from each league in turn needs no cross-league comparison at all, and
    guarantees every league a place in a short list.

    Names that START with the query go round first, so an exact lookup
    still leads even when another league has a longer substring match.
    ``prefer`` (the league the visitor is on) only chooses who goes first
    within a tier — it never excludes anyone, which is the whole point.
    """
    q = (q or "").strip()
    if not q:
        return []
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return []
    order = ([prefer] if prefer in SPORT_MARKETS else []) + \
        [s for s in SPORT_MARKETS if s != prefer]
    conn = _db.connect(path)
    try:
        # Each league fetches a full page: four empty leagues must not
        # cost the fifth its results.
        per = {s: _search_conn(conn, s, q, limit) for s in order}
    finally:
        conn.close()
    strong = {s: [h for h in per[s] if _leads_with(h["player"], q)]
              for s in order}
    weak = {s: [h for h in per[s] if not _leads_with(h["player"], q)]
            for s in order}
    out: list[dict] = []
    for tier in (strong, weak):
        depth = 0
        while len(out) < limit:
            took = False
            for s in order:
                lst = tier[s]
                if depth < len(lst):
                    out.append(lst[depth])
                    took = True
                    if len(out) >= limit:
                        break
            if not took:
                break
            depth += 1
    return out[:limit]


def for_player(sport: str, player: str, db_path=None) -> dict:
    """One player's multi-market logs, whether or not he is on a board.

    The same shape ``for_board`` attaches — {market_label: [games…]} —
    so the Players page renders a searched-up bench bat with the exact
    card a priced star gets."""
    markets = SPORT_MARKETS.get(sport)
    if not markets or not player:
        return {}
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        return _query(conn, sport, markets, [player]).get(player, {})
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
