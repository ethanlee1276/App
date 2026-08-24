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
    # College football joined 2026-08-24, off ESPN's own box scores —
    # the "no free player-level feed covers 134 programs" line in the
    # front end was stale, and this is the layer that retires it. Same
    # labels as the NFL's for the same dedupe-by-label reason above.
    "cfb": (("pass_yds", "Passing Yards"), ("rush_yds", "Rushing Yards"),
            ("rec_yds", "Receiving Yards"), ("receptions", "Receptions"),
            ("carries", "Carries"), ("targets", "Targets")),
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


#: How long a league's name list stays good. Built only when a search
#: MISSES, so on a healthy query it is never built at all; a name that
#: first appears within the next quarter of an hour is one keystroke late,
#: which is a trade any search box makes.
NAME_INDEX_TTL = 900
_NAME_INDEX: dict = {}


def _name_index(conn, sport: str) -> list[str]:
    """Every name this league has ever logged.

    Only reached on a miss. The `LIKE` in `_ranked_names` is what the
    database can answer with an index and it answers the ordinary case;
    this is for the ones it cannot see at all — an accent in the stored
    spelling, the words typed in the other order, a letter wrong — where
    the reader is already looking at an empty page and a slower answer
    beats no answer.
    """
    import time
    hit = _NAME_INDEX.get(sport)
    now = time.time()
    if hit and now - hit[0] < NAME_INDEX_TTL:
        return hit[1]
    names = [r[0] for r in conn.execute(
        "SELECT DISTINCT player FROM player_game_logs WHERE sport=?",
        (sport,)) if r[0]]
    _NAME_INDEX[sport] = (now, names)
    return names


def _ranked_names(conn, sport: str, q: str, limit: int) -> dict:
    """{name: rank} — the substring the index can find, then the rest.

    Ethan, 2026-08-23: "if you dont type the players name in exactly, they
    dont come up at all which makes it feel broken." It was: the query was
    one `LIKE '%q%'`, so a circumflex in the stored name, a hyphen, the
    first and last name typed the other way round, or a single wrong
    letter each returned nothing whatsoever — and nothing on the page
    could tell that apart from "we have never heard of him".
    """
    from .playersearch import rank
    out: dict = {}
    for r in conn.execute(
            "SELECT DISTINCT player FROM player_game_logs "
            "WHERE sport=? AND player LIKE ? LIMIT ?",
            (sport, f"%{q}%", int(limit) * 4)):
        got = rank(r[0], q)
        if got is not None:
            out[r[0]] = got
    # ANY hit at all ends it, not `limit` of them. Most real searches
    # return one or two names, so a "did we fill the page" test would
    # have built the full-scan index on almost every successful query —
    # the expensive path running constantly to serve the case it was not
    # for. Ethan's complaint is the empty result, and that is exactly
    # when this falls through.
    if out:
        return out
    for name in _name_index(conn, sport):
        if name in out:
            continue
        got = rank(name, q)
        if got is not None:
            out[name] = got
    return out


def _search_conn(conn, sport: str, q: str, limit: int) -> list[dict]:
    """One league's hits on an already-open connection.

    Split out so the all-league search opens the database once instead of
    once per sport — five connections to answer one keystroke, on a box
    with one core, is a cost the page pays on every letter typed.
    """
    ranked = _ranked_names(conn, sport, q, limit)
    if not ranked:
        return []
    # HOW WELL IT MATCHES FIRST, how recently he played second. Recency is
    # the right tiebreak between two men who match equally well — a
    # current starter over a 2021 namesake — and the wrong first key
    # entirely: it would put a guessed spelling from last night above the
    # exact name from last week.
    names = sorted(ranked, key=lambda n: (ranked[n], n))[:int(limit) * 3]
    marks = ", ".join("?" for _ in names)
    rows = conn.execute(
        f"SELECT player, COUNT(DISTINCT game_id) AS games, "
        f"MAX(season || '-' || period) AS last "
        f"FROM player_game_logs WHERE sport=? AND player IN ({marks}) "
        f"GROUP BY player ORDER BY last DESC, games DESC",
        (sport, *names)).fetchall()
    rows = sorted(rows, key=lambda r: ranked[r["player"]])[:int(limit)]
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
                    "sport": sport, "rank": ranked[r["player"]],
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


def search_by_sport(q: str, limit: int = 12, sports=None,
                    db_path=None) -> dict:
    """{sport: ranked hits} for every log-backed league, ONE connection.

    The per-source lists rather than a merged one, because the merge is
    not this module's job: fighters come from a different store entirely
    (engine/ufc/fighters.py) and the two are interleaved in
    engine/playersearch.py, which is the only place that knows about both.

    One connection because the page re-runs this on every keystroke, and
    a connection per league on a one-core droplet is four times the cost
    for the same answer.
    """
    q = (q or "").strip()
    want = [s for s in (sports or SPORT_MARKETS) if s in SPORT_MARKETS]
    if not q or not want:
        return {}
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        return {s: _search_conn(conn, s, q, limit) for s in want}
    finally:
        conn.close()


def search_all(q: str, limit: int = 12, prefer: str = "",
               db_path=None) -> list[dict]:
    """Every player in every LOG-BACKED league whose name contains ``q``.

    Ethan, 2026-08-23: "searching for a player should search through ALL
    players for ALL sports. so even if im selected on nfl, i shoudl still
    be able to look up mlb or ufc or wnba players." A search box that
    silently scopes itself to whichever tab you happen to be on is a
    search box you cannot trust — you type a name, get nothing, and have
    no way to tell "he isn't in our data" from "you're on the wrong tab".

    THE LEAGUES IN THIS DATABASE ONLY. Fighters are not here and never
    were: nothing writes a UFC row to ``player_game_logs``. The box the
    visitor actually types into is served by engine/playersearch.py,
    which adds them. This is the history-DB half of that answer.
    """
    from .playersearch import merge, source_order
    q = (q or "").strip()
    if not q:
        return []
    order = [s for s in source_order(prefer) if s in SPORT_MARKETS]
    return merge(search_by_sport(q, limit, order, db_path), q, limit, order)


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
