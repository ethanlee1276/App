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
import sqlite3
import threading
import time

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
            ("anytime_td", "Anytime TD"),
            # THE QUARTERBACK'S OWN TOUCHDOWNS, missing from this tuple
            # since it was written. Ethan, 2026-09-10: "when we search a
            # QB, we are not showing passing touchdown stats at all."
            # The rows have been on disk the whole time —
            # `ingest.NFL_USAGE_MARKETS` has stored `pass_td` per
            # player-week since August — and this list, which is what
            # the search page draws its chips from, simply did not name
            # the market. Anytime TD is the man who SCORES; this is the
            # man who throws it, and a quarterback's page showed neither
            # his own number nor any hint one existed.
            #
            # Label matched to `models.MARKET_LABELS[PASS_TD]` for the
            # dedupe-by-label reason the anytime_td note gives above:
            # `pass_td` is now a priced market too, so a second spelling
            # here would draw one stat on two chips.
            ("pass_td", "Passing TDs"),
            # The volume markets priced since 2026-09-27 (engine/models):
            # carries already has its chip above, under the same label.
            ("pass_att", "Pass Attempts"), ("pass_cmp", "Completions"),
            # Interceptions thrown (2026-10-05): the label the priced
            # market wears (models.MARKET_LABELS[PASS_INT]).
            ("pass_int", "Interceptions")),
    "mlb": (("total_bases", "Total Bases"), ("hits", "Hits"),
            ("home_runs", "Home Runs"), ("strikeouts", "Strikeouts"),
            ("outs", "Outs Recorded")),
    # Hoops joined for the league-wide search (2026-08-18). Labels match
    # engine/nba/pipeline.MARKET_LABELS for the same dedupe-by-label
    # reason the anytime_td comment gives.
    "nba": (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
            ("fg3m", "3-Pointers Made"),
            # Stored since 2026-10-13 and priced since 2026-10-14
            # (`hoops.COUNTS`); a game ingested before then has no row and
            # shows none, never a zero.
            ("stl", "Steals"), ("blk", "Blocks"), ("tov", "Turnovers")),
    "wnba": (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
             ("fg3m", "3-Pointers Made")),
    # Men's college basketball (2026-11-13): the five its board prices, and
    # the three the box score stores beside them.
    "cbb": (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
            ("fg3m", "3-Pointers Made"), ("stl", "Steals"), ("blk", "Blocks"),
            ("tov", "Turnovers")),
    # College football joined 2026-08-24, off ESPN's own box scores —
    # the "no free player-level feed covers 134 programs" line in the
    # front end was stale, and this is the layer that retires it. Same
    # labels as the NFL's for the same dedupe-by-label reason above.
    # College keeps the same shape, and `sources.cfbstats.MARKETS`
    # writes `pass_td` for it too — a college quarterback's page was
    # missing the column for the same reason the NFL's was.
    "cfb": (("pass_yds", "Passing Yards"), ("rush_yds", "Rushing Yards"),
            ("rec_yds", "Receiving Yards"), ("receptions", "Receptions"),
            ("carries", "Carries"), ("targets", "Targets"),
            ("pass_td", "Passing TDs"), ("pass_att", "Pass Attempts"),
            ("pass_cmp", "Completions"), ("pass_int", "Interceptions")),
    # Hockey joined 2026-10-03, off the NHL's own box scores
    # (engine/sources/nhldata). Labels match engine/nhl/model.MARKET_LABELS.
    "nhl": (("sog", "Shots on Goal"), ("points", "Points"), ("goals", "Goals"),
            ("assists", "Assists"), ("blocks", "Blocked Shots"), ("saves", "Saves")),
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
        # KEPT BETWEEN BUILDS (engine/logcache, 2026-11-09) while the sport's
        # logs and the board's names hold: one index seek per player and
        # market, thousands a board, inside the NFL pricing stage's 6-second
        # "census + player stats + shelves + market scan" at 09:24 on 9
        # November, the same games on every build of the same slate.
        import hashlib
        from . import logcache
        return logcache.memo(conn, "player_stats", sport, None,
                             lambda: _query(conn, sport, markets, players), code=__file__,
                             extra={"players": hashlib.sha1("\n".join(players).encode()).hexdigest()})
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


def face(conn, sport: str, player: str) -> str:
    """His photo: the row stored under this exact spelling first, then the
    sport's normalised map. Never raises.

    The stored row first because `face_map` is memoised for six hours, and
    the daily face pass (facesfill.chart_rows) writes a chart player's
    photo under the chart's own spelling — read only through the memo, a
    face filled this morning would wait until the afternoon to appear."""
    try:
        row = conn.execute("SELECT headshot FROM player_assets WHERE sport=? AND player=?",
                           (sport, player)).fetchone()
        if row and row[0]:
            return row[0]
    except Exception:                                        # noqa: BLE001
        pass                         # a database predating the assets table
    return _face_of(conn, sport, player)


def search(sport: str, q: str, limit: int = 12, db_path=None,
           data_dir=None) -> list[dict]:
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
        # No history store at all — the roster is still a true answer,
        # and a league whose logs have not landed yet should not read as
        # a league with no players in it.
        return _roster_hits(sport, q, limit, set(), data_dir)
    conn = _db.connect(path)
    try:
        return _search_conn(conn, sport, q, limit, data_dir)
    finally:
        conn.close()


#: How long a league's name list stays good where the file keeps no counts
#: of its changes (`logcache.generations`); where it does, the list is good
#: until the league's logs change, and that is what is checked.
NAME_INDEX_TTL = 900
#: A league with fewer names than this is rebuilt in line when its logs
#: change (a blink); a bigger one keeps answering from the list it has
#: while the new one is built behind it, at most once a minute.
NAME_INDEX_INLINE = 20000
NAME_INDEX_GAP = 60
_NAME_INDEX: dict = {}
_NAMES_BUSY: set = set()
_NAMES_LOCK = threading.Lock()
_NAMES_FAIL_SAID = [False]

#: Every name a league has logged, with the latest season it played: ONE
#: INDEX SEEK A NAME. `idx_logs_player` is ordered (sport, player, season),
#: so the next name after the last one and a name's latest season are each
#: a seek, where `SELECT DISTINCT player` reads every row the league has
#: (millions for college football). Measured on a million-row table of
#: twenty thousand names: 0.044 s against 0.12 s for the GROUP BY, and the
#: gap grows with the rows a name has.
_NAMES_SQL = """
WITH RECURSIVE names(p) AS (
  SELECT (SELECT MIN(player) FROM player_game_logs INDEXED BY idx_logs_player WHERE sport = ?1)
  UNION ALL
  SELECT (SELECT MIN(player) FROM player_game_logs INDEXED BY idx_logs_player
          WHERE sport = ?1 AND player > names.p)
  FROM names WHERE names.p IS NOT NULL)
SELECT p, (SELECT MAX(season) FROM player_game_logs INDEXED BY idx_logs_player
           WHERE sport = ?1 AND player = names.p)
FROM names WHERE p IS NOT NULL"""


def _read_names(conn, sport: str) -> list:
    """``(name, latest season)`` for every name the league has logged."""
    try:
        return conn.execute(_NAMES_SQL, (sport,)).fetchall()
    except sqlite3.OperationalError:
        # A file older than idx_logs_player: the same answer, row by row.
        return conn.execute("SELECT player, MAX(season) FROM player_game_logs "
                            "WHERE sport=? GROUP BY player", (sport,)).fetchall()


def _log_sig(conn, sport: str):
    """The league's change counts, or None where the file keeps none."""
    from . import logcache
    return logcache.generations(conn, sport, None)


def _build_names(conn, sport: str, sig):
    from .playersearch import NameIndex
    return NameIndex(((r[0], r[1]) for r in _read_names(conn, sport) if r[0]),
                     at=time.time(), sig=sig)


def _name_index(conn, sport: str):
    """Every name this league has ever logged (`playersearch.NameIndex`).

    EVERY SEARCH READS IT, where it once served only a search that missed.
    Ethan, 2026-11-16: "players are not showing up on the search page for
    players." The ordinary query was a `LIKE '%q%'` over the league's logs,
    which no index can serve (the wildcard leads), so every keystroke read
    the whole league: millions of rows for college football, where a
    search took 8 to 16 seconds on the box. The list is built once, with a
    seek a name (`_NAMES_SQL`), and kept until the league's logs change;
    `warm_search` builds every league's before anyone types.
    """
    from . import logcache
    path = logcache.db_file(conn)
    key = (sport, path)
    sig = _log_sig(conn, sport)
    hit = _NAME_INDEX.get(key)
    if hit is not None:
        if (hit.sig == sig) if sig is not None else (time.time() - hit.at < NAME_INDEX_TTL):
            return hit
        if path and len(hit) >= NAME_INDEX_INLINE:
            _rebuild_names_later(sport, path)
            return hit
    built = _build_names(conn, sport, sig)
    _NAME_INDEX[key] = built
    return built


def _rebuild_names_later(sport: str, path: str) -> None:
    key = (sport, path)
    with _NAMES_LOCK:
        hit = _NAME_INDEX.get(key)
        if key in _NAMES_BUSY or (hit is not None and time.time() - hit.at < NAME_INDEX_GAP):
            return
        _NAMES_BUSY.add(key)
    threading.Thread(target=_rebuild_names, args=(sport, path), daemon=True,
                     name=f"names-{sport}").start()


def _rebuild_names(sport: str, path: str) -> None:
    """The league's new name list, built on its own connection while the
    search answers from the old one. A failure keeps the old list, which
    reads like a quiet day's, so the first one in a process says so in the
    service's log; the next try waits a minute."""
    key = (sport, path)
    try:
        conn = _db.connect(path)
        try:
            _NAME_INDEX[key] = _build_names(conn, sport, _log_sig(conn, sport))
        finally:
            conn.close()
    except Exception as exc:                                 # noqa: BLE001
        hit = _NAME_INDEX.get(key)
        if hit is not None:
            hit.at = time.time()
        if not _NAMES_FAIL_SAID[0]:
            _NAMES_FAIL_SAID[0] = True
            print(f"[search] the {sport} name list was not rebuilt "
                  f"({type(exc).__name__}: {exc}); the search keeps the one it has", flush=True)
    finally:
        with _NAMES_LOCK:
            _NAMES_BUSY.discard(key)


def warm_search(db_path=None, data_dir=None, delay: float = 0.0):
    """Every league's name list and roster list, built before anyone types.

    The first search after a restart would otherwise build its league's
    (about a second for college football on the box). A thread, so the
    server answers while it runs; the thread is returned for the tests."""
    t = threading.Thread(target=_warm_all, args=(db_path, data_dir, delay),
                         daemon=True, name="search-warm")
    t.start()
    return t


def _warm_all(db_path, data_dir, delay: float) -> None:
    if delay:
        time.sleep(delay)
    path = str(db_path or _db.DEFAULT_DB)
    for sport in SPORT_MARKETS:
        try:
            _roster_index(sport, data_dir)
            if os.path.exists(path):
                conn = _db.connect(path)
                try:
                    _name_index(conn, sport)
                finally:
                    conn.close()
        except Exception as exc:                             # noqa: BLE001
            print(f"[search] the {sport} search lists were not built ahead "
                  f"({type(exc).__name__}: {exc}); the first search builds them", flush=True)


def _ranked_names(conn, sport: str, q: str, limit: int, fuzzy: bool = True) -> dict:
    """{name: rank}, best first: the tier, then (for a guessed spelling) the
    closest whole name, then the latest season, then the name.

    Ethan, 2026-08-23: "if you dont type the players name in exactly, they
    dont come up at all which makes it feel broken." The tiers forgive an
    accent, punctuation, the words in either order and (when nobody has the
    name as typed) a wrong letter. Read off the kept list (`_name_index`),
    never the logs: a keystroke costs a search of a megabyte of names.
    """
    from .playersearch import closeness, norm
    ql = norm(q)
    if not ql:
        return {}
    ix = _name_index(conn, sport)
    got = ix.ranked(ql, fuzzy=fuzzy)

    def order(k):
        t = got[k]
        return (t, -closeness(ql, ix.norm_of(k)) if t == 3 else 0.0, -ix.last[k], ix.names[k])
    return {ix.names[k]: got[k] for k in sorted(got, key=order)}


def _search_conn(conn, sport: str, q: str, limit: int,
                 data_dir=None) -> list[dict]:
    """One league's hits on an already-open connection.

    Split out so the all-league search opens the database once instead of
    once per sport — five connections to answer one keystroke, on a box
    with one core, is a cost the page pays on every letter typed.
    """
    ranked = _ranked_names(conn, sport, q, limit, fuzzy=False)
    if not ranked:
        # NOTHING HAS PLAYED UNDER THAT NAME — which is not the same as
        # nobody having it. The roster answers for the men the logs
        # cannot; see `_roster_players`. Its names as typed come before
        # anyone's closest spellings: a freshman typed exactly is found
        # without the spelling pass over every name the league has logged.
        named = _roster_hits(sport, q, limit, set(), data_dir, fuzzy=False)
        if named:
            return named
        ranked = _ranked_names(conn, sport, q, limit)
        if not ranked:
            return _roster_hits(sport, q, limit, set(), data_dir)
    # HOW WELL IT MATCHES FIRST, how recently he played second. Recency is
    # the right tiebreak between two men who match equally well — a
    # current starter over a 2021 namesake — and the wrong first key
    # entirely: it would put a guessed spelling from last night above the
    # exact name from last week. `_ranked_names` comes best first already
    # (and a guess, closest spelling first), so the page's worth is its head.
    names = list(ranked)[:int(limit) * 3]
    marks = ", ".join("?" for _ in names)
    rows = conn.execute(
        f"SELECT player, COUNT(DISTINCT game_id) AS games, "
        f"MAX(season || '-' || period) AS last "
        f"FROM player_game_logs WHERE sport=? AND player IN ({marks}) "
        f"GROUP BY player ORDER BY last DESC, games DESC",
        (sport, *names)).fetchall()
    place = {n: i for i, n in enumerate(names)}
    rows = sorted(rows, key=lambda r: (ranked[r["player"]],
                                       place[r["player"]] if ranked[r["player"]] == 3 else 0))[:int(limit)]
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
    # TOPPED UP, NOT REPLACED. A man with a stat line outranks one
    # without, always — so the roster only ever fills the space the
    # logs left empty, and a thin log store degrades into a roster
    # search instead of into a blank page.
    found = any(r < 3 for r in ranked.values())
    if len(out) < int(limit):
        out += _roster_hits(sport, q, int(limit) - len(out),
                            {r["player"] for r in out}, data_dir, fuzzy=not found)
    from .playersearch import no_guess_beside_an_answer
    return no_guess_beside_an_answer(out)


#: Where the published roster payloads live, and how long one stays
#: good in memory. Same quarter-hour as the name index above, for the
#: same reason: a roster changes on a nightly, not on a keystroke.
ROSTER_DIR = "web/data"
ROSTER_TTL = 900
_ROSTER: dict = {}


def _roster_players(sport: str, data_dir=None) -> list[dict]:
    """Everyone on a published roster, whether or not he has played.

    Ethan, 2026-09-19: *"a lot of CFB players dont show up in the player
    search."*

    They could not. This module searches `player_game_logs`, which is
    everyone who has APPEARED IN AN INGESTED GAME — and in September a
    college roster is a hundred men of whom a couple of dozen have a
    stat line. Backups, freshmen, specialists and anyone whose week has
    not been ingested were not merely ranked low; they were absent, and
    the page could not tell that apart from "no such player".

    The rosters were already on disk and already published. Nothing
    here fetches.
    """
    import json
    import os
    import time
    key = (sport, str(data_dir or ROSTER_DIR))
    hit = _ROSTER.get(key)
    now = time.time()
    if hit and now - hit[0] < ROSTER_TTL:
        return hit[1]
    out: list[dict] = []
    path = os.path.join(str(data_dir or ROSTER_DIR), f"rosters_{sport}.json")
    # THE SAME FILE IS THE SAME ROSTER. Rereading 5.6 MB of college rosters
    # every quarter hour on a search, to find what the nightly build wrote
    # last night, was a second's wait for nothing; the file's stamp says
    # whether there is anything new to read.
    try:
        stamp = os.stat(path).st_mtime_ns
    except OSError:
        stamp = None
    if hit and stamp is not None and len(hit) > 2 and hit[2] == stamp:
        _ROSTER[key] = (now, hit[1], stamp)
        return hit[1]
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for team, entry in (doc.get("teams") or {}).items():
            # `{team: {"players": [...]}}`, which is what `rosters.build`
            # publishes — the roster page reads the same shape. A bare
            # list is accepted too so an older payload on disk does not
            # silently read as an empty league.
            players = (entry.get("players") if isinstance(entry, dict)
                       else entry) or []
            for pl in players:
                name = str((pl or {}).get("player") or "").strip()
                if name:
                    # A jersey is a string to print: 0 is a number a man
                    # wears, not a missing one.
                    num = pl.get("number")
                    num = pl.get("jersey") if num in (None, "") else num
                    out.append({"player": name, "team": team,
                                "position": str(pl.get("position") or ""),
                                "headshot": str(pl.get("headshot") or ""),
                                "number": "" if num in (None, "") else str(num)})
    except Exception:                                    # noqa: BLE001
        out = []      # no roster published for this league: logs only
    _ROSTER[key] = (now, out, stamp)
    return out


_ROSTER_INDEX: dict = {}


def _roster_index(sport: str, data_dir=None):
    """``(players, NameIndex of their names)``: the roster `_roster_players`
    keeps, its names normed once, rebuilt when the roster is."""
    from .playersearch import NameIndex
    players = _roster_players(sport, data_dir)
    key = (sport, str(data_dir or ROSTER_DIR))
    hit = _ROSTER_INDEX.get(key)
    if hit is not None and hit[0] is players:
        return players, hit[1]
    ix = NameIndex(((p["player"], 0) for p in players), at=time.time())
    _ROSTER_INDEX[key] = (players, ix)
    return players, ix


def roster_meta(sport: str, player: str, team: str = "", data_dir=None) -> dict:
    """``{"position", "number"}`` off the published roster, or ``{}``.

    For the head of his chart, beside his name (2026-10-14, Ethan's renders
    of the MLB hit page: "RF #22"). Where the chart knows his team only
    that club's roster answers, so a namesake on another club, or the
    man a traded player was last season, is never printed as him; with
    no team, only a name the league carries once. Never raises: no
    roster on disk is ``{}``."""
    from .playersearch import norm
    want = norm(player)
    if not want:
        return {}
    hits = [r for r in _roster_players(sport, data_dir) if norm(r["player"]) == want
            and (not team or r["team"] == team)]
    if len(hits) != 1:
        return {}
    return {"position": hits[0]["position"], "number": hits[0].get("number") or ""}


def _roster_hits(sport: str, q: str, want: int, seen: set,
                 data_dir=None, fuzzy: bool = True) -> list[dict]:
    """Roster names matching `q` that the logs did not already answer.

    ``games: 0`` is the honest part — the page must not promise a chart
    for a man with no logged game, and "we know who he is, he has not
    played" is a different fact from "we have never heard of him".
    """
    from .playersearch import closeness, norm
    ql = norm(q)
    if not ql:
        return []
    players, ix = _roster_index(sport, data_dir)
    out = []
    # ``fuzzy`` is False once the logs have found someone by the name typed:
    # a roster's closest spellings are then noise (`no_guess_beside_an_answer`),
    # and the costly part of a roster of forty thousand.
    for k, got in ix.ranked(ql, fuzzy=fuzzy).items():
        pl = players[ix.src[k]]
        if pl["player"] in seen:
            continue
        out.append({"player": pl["player"], "games": 0, "sport": sport,
                    "rank": got, "team": pl["team"],
                    "position": pl["position"],
                    "headshot": pl["headshot"],
                    "_near": -closeness(ql, ix.norm_of(k)) if got == 3 else 0.0})
    out.sort(key=lambda r: (r["rank"], r["_near"], r["player"]))
    for r in out:
        del r["_near"]
    return out[:max(0, want)]


def search_by_sport(q: str, limit: int = 12, sports=None,
                    db_path=None, data_dir=None) -> dict:
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
        # Still the rosters — see `search`. A league whose logs have not
        # landed is not a league with no players in it.
        return {s: _roster_hits(s, q, limit, set(), data_dir) for s in want}
    conn = _db.connect(path)
    try:
        return {s: _search_conn(conn, s, q, limit, data_dir) for s in want}
    finally:
        conn.close()


def search_all(q: str, limit: int = 12, prefer: str = "",
               db_path=None, data_dir=None) -> list[dict]:
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
    return merge(search_by_sport(q, limit, order, db_path, data_dir),
                 q, limit, order,
                 prefer=prefer)


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


# --- head-to-head: every game against ONE opponent --------------------------
# Ethan, 2026-09-01: "Add an option too be able too look up past game data
# for player for nfl and CFB. For example, the rams take on the 49ers week
# one and I wanna see how Devonte Adam's did the last time the 49ers
# played the rams. Also make sure we don't have any issues with the names
# like we did before."
#
# Two answers in one contract. The DATA one: player_game_logs already
# stores the opponent on every ingested row, across every stored season —
# so "how did he do against them" is a filter, not a new feed. The NAMES
# one: the typed name goes through the SAME ranked resolution the search
# box uses (playersearch.rank — his own example, "Devonte Adam's", lands
# on Davante Adams as a closest-spelling hit), and the OPPONENT is never
# free-typed at all: `opponents_of` hands the page the exact stored
# values, the page offers them as a picker, and `versus` receives one
# back verbatim. A join that never leaves the database cannot misspell.

#: Games a head-to-head answer carries. Deeper than the profile chart's
#: N_GAMES on purpose — two clubs meet twice a year, so ten games of
#: history IS five seasons, and the reader asked for the history.
VS_GAMES = 20


def resolve_player(conn, sport: str, q: str) -> str:
    """The stored spelling for a typed name, or "".

    Exact hit first (free, and almost always the case — the page sends
    the name it already displays). Then the ranked search the box uses,
    best tier only; a tie inside the tier goes to the man seen most
    recently, the same "current starter over 2021 namesake" rule search
    results follow.
    """
    q = (q or "").strip()
    if not q:
        return ""
    row = conn.execute(
        "SELECT player FROM player_game_logs WHERE sport=? AND player=? "
        "LIMIT 1", (sport, q)).fetchone()
    if row:
        return row["player"]
    ranked = _ranked_names(conn, sport, q, 12)
    if not ranked:
        return ""
    best = min(ranked.values())
    names = sorted(n for n in ranked if ranked[n] == best)
    if len(names) == 1:
        return names[0]
    marks = ", ".join("?" for _ in names)
    row = conn.execute(
        f"SELECT player FROM player_game_logs WHERE sport=? "
        f"AND player IN ({marks}) ORDER BY season DESC, period DESC "
        f"LIMIT 1", (sport, *names)).fetchone()
    return row["player"] if row else names[0]


def _resolve_opponent(conn, sport: str, player: str, opp: str) -> str:
    """The stored opponent key ``opp`` means, or "".

    Matched against the opponents THIS player has actually logged —
    exact, then case-insensitive, then normalised containment (a CFB
    school typed as "ohio state" against a stored "Ohio State"). NFL
    keys are abbreviations the picker supplies verbatim, so the fallbacks
    exist for hand-built URLs, not for the page.
    """
    opp = (opp or "").strip()
    if not opp:
        return ""
    stored = [r[0] for r in conn.execute(
        "SELECT DISTINCT opponent FROM player_game_logs "
        "WHERE sport=? AND player=? AND opponent != ''",
        (sport, player))]
    if opp in stored:
        return opp
    low = opp.lower()
    for cand in stored:
        if cand.lower() == low:
            return cand
    from .playersearch import norm
    n = norm(opp)
    for cand in stored:
        cn = norm(cand)
        if n and cn and (n in cn or cn in n):
            return cand
    return ""


def opponents_of(sport: str, player: str, db_path=None) -> dict:
    """Who this player has logged games against — the picker's options.

    ``{"player": stored spelling, "opponents": [{"opponent", "games"},
    …most recently met first]}``, or ``{}`` when the name resolves to
    nobody. Same honest degradation as everything here: no DB, ``{}``.
    """
    if sport not in SPORT_MARKETS or not (player or "").strip():
        return {}
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        name = resolve_player(conn, sport, player)
        if not name:
            return {}
        rows = conn.execute(
            "SELECT opponent, COUNT(DISTINCT game_id) AS games, "
            "MAX(season || '-' || period) AS last "
            "FROM player_game_logs "
            "WHERE sport=? AND player=? AND opponent != '' "
            "GROUP BY opponent ORDER BY last DESC, games DESC",
            (sport, name)).fetchall()
        return {"player": name,
                "opponents": [{"opponent": r["opponent"],
                               "games": int(r["games"])} for r in rows]}
    finally:
        conn.close()


def versus(sport: str, player: str, opponent: str, db_path=None) -> dict:
    """Every stored game this player has against that opponent.

    ``{"player", "opponent", "games": [{"season", "week"|"date", "home",
    "team", "stats": {label: value}}, …newest first]}`` — one row PER
    GAME with every ingested market on it, because "how did he do last
    time they played" is a question about the game, not about one stat.

    ``team`` is HIS club in that game, kept per row on purpose: the
    history follows the man, not the laundry — Adams's games against the
    49ers include the ones he played as a Raider, and the row says so.
    """
    markets = SPORT_MARKETS.get(sport)
    if not markets or not (player or "").strip():
        return {}
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        name = resolve_player(conn, sport, player)
        if not name:
            return {}
        opp = _resolve_opponent(conn, sport, name, opponent)
        if not opp:
            return {"player": name, "opponent": "", "games": []}
        ids = [m for m, _ in markets]
        labels = dict(markets)
        rows = conn.execute(
            "SELECT season, period, game_id, team, home, market, value "
            "FROM player_game_logs "
            "WHERE sport=? AND player=? AND opponent=? "
            f"AND market IN ({','.join('?' * len(ids))}) "
            "ORDER BY season DESC, period DESC",
            (sport, name, opp, *ids)).fetchall()
        games: list[dict] = []
        seen: dict = {}
        for r in rows:
            key = (r["season"], r["period"], r["game_id"])
            g = seen.get(key)
            if g is None:
                if len(games) >= VS_GAMES:
                    continue
                g = {"season": int(r["season"]),
                     "home": bool(r["home"]), "team": r["team"],
                     "stats": {}}
                if sport == "nfl":
                    g["week"] = int(r["period"])
                else:
                    g["date"] = str(r["period"])
                seen[key] = g
                games.append(g)
            g["stats"][labels[r["market"]]] = float(r["value"])
        # Stats in SPORT_MARKETS display order, decided here once — the
        # same argument _query's rebuild carries.
        for g in games:
            g["stats"] = {labels[m]: g["stats"][labels[m]]
                          for m, _ in markets if labels[m] in g["stats"]}
        return {"player": name, "opponent": opp, "games": games}
    finally:
        conn.close()


def _query(conn, sport, markets, players) -> dict:
    """``player_stats`` for ``players``: each one's last ``N_GAMES`` in each
    market, newest first, players listed newest first.

    ONE SEEK PER PLAYER AND MARKET (2026-11-08). The single read below
    (`_query_scan`) asks for every season of every priced player, sorted
    newest first, and SQLite answers the sort by walking the table's own
    key backwards: every row the sport has, of every market and player,
    to keep ten a pair. On a two-million-row copy of the table's shape:
    1.68 seconds; on the NFL build at 09:16 on 8 November it sat inside an
    11-second part of the pricing stage. Each pair's ten are now one seek
    of the (sport, market, player) index, named outright because the
    planner, left to itself, walks the key backwards for each of them too:
    0.16 seconds, the same games. The order is the one that backwards walk
    gave — newest season, week or date, then game, then player, then
    market, as the box's file (never ANALYZEd, so planned the same way)
    gave it — written down: a pair's games newest first, game id breaking
    a tie (a doubleheader), and the players by their newest game, the name
    breaking a tie the same way. A file without that index (one made
    before it existed) is read the old way."""
    import sqlite3
    ids = [m for m, _ in markets]
    labels = dict(markets)
    q = ("SELECT season, period, game_id, opponent, home, value "
         "FROM player_game_logs INDEXED BY idx_logs_lookup "
         "WHERE sport=? AND market=? AND player=? "
         "ORDER BY season DESC, period DESC, game_id DESC LIMIT ?")
    grouped: dict[str, dict[str, list]] = {}
    newest: dict = {}
    try:
        for player in players:
            per: dict[str, list] = {}
            for m in ids:
                rows = conn.execute(q, (sport, m, player, N_GAMES)).fetchall()
                if not rows:
                    continue
                top = (rows[0][0], str(rows[0][1]), str(rows[0][2]))
                if player not in newest or top > newest[player]:
                    newest[player] = top
                lst = per.setdefault(m, [])
                for r in rows:
                    g = {"opponent": r[3], "home": bool(r[4]), "value": float(r[5])}
                    if sport == "nfl":
                        g["week"] = int(r[1])
                    else:
                        g["date"] = str(r[1])
                    lst.append(g)
            if per:
                grouped[player] = per
    except sqlite3.OperationalError as exc:
        if "no such index" not in str(exc):
            raise
        return _query_scan(conn, sport, markets, players)
    out: dict[str, dict[str, list]] = {}
    for player in sorted(grouped, key=lambda p: (newest[p], p), reverse=True):
        per = grouped[player]
        keep = {labels[m]: per[m] for m, _ in markets
                if len(per.get(m, [])) >= MIN_GAMES}
        if keep:
            out[player] = keep
    return out


def _query_scan(conn, sport, markets, players) -> dict:
    """The single read `_query` replaced: every season of every player,
    sorted newest first, ten kept a pair. Kept for a file without the
    (sport, market, player) index."""
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
