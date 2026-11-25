"""A player's own page, in every league (2026-11-16).

Ethan, with ESPN's page for Josh Allen: "The page should look just like this
and have each menu for all players in all sports." Overview, News, Stats,
Bio, Splits and Game Log, for anyone the history file or a roster knows.

`page` gathers what those menus show, from what is already kept:

  * bio      the published roster's facts (number, height, weight, age, the
             day he was born, where, his college, his years in the league),
             and the seasons and games the history file holds on him;
  * notes    his roster's latest injury note and any move between clubs;
  * headline his season's four numbers, the ones a sports site leads with
             for what he does (a passer's yards, touchdowns, interceptions
             and rating; a scorer's points, rebounds, assists and shooting),
             each with where it ranks in the league this season;
  * last     the newest game: the score, the result, both clubs' records
             through it, and four of his numbers from it;
  * splits   the season a game's average at a time (a baseball season's
             totals, as its box scores are read): all of it, the last
             five, home and away, wins and losses, a hitter's against
             left- and right-handed starters, month by month and
             opponent by opponent;
  * career   season by season, totals (a game's average in basketball, as
             the box score is read there) and the career line.

The game log itself is engine/gamelog's, drawn in its own tab. Facts, not
picks: served free (server.py /api/players/page), drawn by js/playerpage.js.

A RANK is among the players who qualify: a count among everyone with one; a
basketball average among those who have played half a regular's games (the
90th percentile of games played); a rate (a rating, a percentage, yards a carry) and a count
where fewer is better (interceptions) among those with at least
RATE_SHARE of the leader's volume behind it. Ties share a place.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time

from . import db as _db
from . import gamelog as GL
from . import rosters

SPORTS = tuple(GL.LAYOUTS)
HOOPS = ("nba", "wnba", "cbb")
ROSTER_DIR = "web/data"
#: A rate is ranked among players with this share of the leader's volume.
RATE_SHARE = 0.4
#: A basketball average is ranked among players with this share of a regular's games
#: (the 90th percentile of games played, so one name shared by several players cannot lift it).
GAMES_SHARE = 0.5
#: A rank table is rebuilt in the background once this old (a season's totals
#: move once a night); a stale one answers meanwhile. Built cold, a table is
#: seconds of reading a large file (measured live 2026-11-16: MLB 5.7 s,
#: college basketball 7.5 s), so the server builds every league's at start
#: (`warm`) and no page waits on one.
RANK_TTL = 6 * 3600
#: The kinds of player each league's pages rank.
KINDS = {"nfl": ("passing", "rushing", "receiving", "kicking", "defense"),
         # no defense: college's play file names no tackler (NO_FEED)
         "cfb": ("passing", "rushing", "receiving", "kicking"),
         "nba": ("box",), "wnba": ("box",), "cbb": ("box",), "nhl": ("skater", "goalie"),
         "mlb": ("batting", "pitching")}
_REFRESHING: set = set()
_RANK_FAIL_SAID = False
#: Leagues whose games table does not hold every game, so a club's record
#: counted off it is wrong: MLB's is filled game by game as slates are read
#: (seen live 2026-11-16, the Dodgers "29-19-1" in mid-October). No record is
#: printed there rather than a wrong one.
NO_RECORDS = ("mlb",)
#: Leagues whose splits are read as totals, as a box score's are (2026-11-17):
#: a baseball split is its at-bats, hits and homers with the rates beside
#: them (ESPN's MLB splits), not 0.3 homers a game.
SPLIT_TOTALS = ("mlb",)
#: A hitter's platoon split, by the hand of the starter they faced
#: (`game_starters`, the starters the nightly stores with their hand).
HANDS = (("L", "vs left-handed starters"), ("R", "vs right-handed starters"))

# A headline number: (key, label, title, how, per_game, low_is_better, volume, ranked).
#   how      gamelog's rule (sum/pct/avg/rating/ip), or "gaa" / "k9" / "gp" below;
#   volume   the market a rate (or a fewer-is-better count) qualifies on.
HEAD = {
    "passing": (("yds", "YDS", "Passing yards", ("sum", "pass_yds"), False, False, None, True),
                ("td", "TD", "Passing touchdowns", ("sum", "pass_td"), False, False, None, True),
                ("int", "INT", "Interceptions thrown", ("sum", "pass_int"), False, True, "pass_att", True),
                ("rtg", "RTG", "Passer rating", ("rating",), False, False, "pass_att", True)),
    "rushing": (("car", "CAR", "Rushing attempts", ("sum", "carries", "rush_att"), False, False, None, True),
                ("yds", "YDS", "Rushing yards", ("sum", "rush_yds"), False, False, None, True),
                ("td", "TD", "Rushing touchdowns", ("sum", "rush_td"), False, False, None, True),
                ("avg", "AVG", "Yards a carry", ("avg", "rush_yds", "carries"), False, False, "carries", True)),
    "receiving": (("rec", "REC", "Receptions", ("sum", "receptions"), False, False, None, True),
                  ("yds", "YDS", "Receiving yards", ("sum", "rec_yds"), False, False, None, True),
                  ("td", "TD", "Receiving touchdowns", ("sum", "rec_td"), False, False, None, True),
                  ("avg", "AVG", "Yards a catch", ("avg", "rec_yds", "receptions"), False, False, "receptions",
                   True)),
    # A kicker's and a defender's (2026-11-17): the numbers a sports site
    # leads those pages with. A long is one kick, the season's best, so it
    # is shown and not ranked.
    "kicking": (("fgm", "FGM", "Field goals made", ("sum", "fg_made"), False, False, None, True),
                ("pct", "FG%", "Field goal percentage", ("pct", "fg_made", "fg_att"), False, False, "fg_att", True),
                ("lng", "LNG", "Longest field goal made", ("max", "fg_long"), False, False, None, False),
                ("pts", "PTS", "Kicking points", ("sum", "kick_pts"), False, False, None, True)),
    "defense": (("tot", "TOT", "Total tackles", ("sum", "tackles_ast"), False, False, None, True),
                ("sack", "SACK", "Sacks", ("sum", "def_sacks"), False, False, None, True),
                ("int", "INT", "Interceptions", ("sum", "def_int"), False, False, None, True),
                ("pd", "PD", "Passes defended", ("sum", "def_pd"), False, False, None, True)),
    "box": (("pts", "PTS", "Points a game", ("sum", "pts"), True, False, None, True),
            ("reb", "REB", "Rebounds a game", ("sum", "reb"), True, False, None, True),
            ("ast", "AST", "Assists a game", ("sum", "ast"), True, False, None, True),
            ("fgp", "FG%", "Field goal percentage", ("pct", "fgm", "fga"), False, False, "fga", True)),
    "skater": (("g", "G", "Goals", ("sum", "goals"), False, False, None, True),
               ("a", "A", "Assists", ("sum", "assists"), False, False, None, True),
               ("pts", "PTS", "Points", ("sum", "points"), False, False, None, True),
               ("sog", "SOG", "Shots on goal", ("sum", "sog"), False, False, None, True)),
    "goalie": (("svp", "SV%", "Save percentage", ("pct", "saves", "shots_against"), False, False, "shots_against",
                True),
               ("gaa", "GAA", "Goals against a 60 minutes", ("gaa",), False, True, "toi", True),
               ("sv", "SV", "Saves", ("sum", "saves"), False, False, None, True),
               ("gs", "GS", "Games started", ("sum", "started"), False, False, None, False)),
    # The numbers a sports site leads a hitter's and a pitcher's page with
    # (2026-11-17), now the box scores' whole lines are kept (engine/mlb/
    # fulllines). A rate is ranked among those with RATE_SHARE of the most
    # plate appearances (or outs) behind it.
    "batting": (("avg", "AVG", "Batting average", ("bavg", "hits", "at_bats"), False, False, "pa", True),
                ("hr", "HR", "Home runs", ("sum", "home_runs"), False, False, None, True),
                ("rbi", "RBI", "Runs batted in", ("sum", "rbis"), False, False, None, True),
                ("ops", "OPS", "On-base plus slugging",
                 ("ops", "hits", "walks", "hbp", "at_bats", "sac_flies", "total_bases"), False, False, "pa", True)),
    "pitching": (("era", "ERA", "Earned run average", ("era", "earned_runs", "outs"), False, True, "outs", True),
                 ("k", "K", "Strikeouts", ("sum", "strikeouts"), False, False, None, True),
                 ("whip", "WHIP", "Walks and hits an inning", ("whip", "hits_allowed", "walks_allowed", "outs"),
                  False, True, "outs", True),
                 ("ip", "IP", "Innings pitched", ("ip", "outs"), False, False, None, True)),
}
#: A kind's spare numbers, in order, for headline ones whose season has none (PLAYERDATA4, 2026-11-17): the
#: WNBA's box scores carry minutes, points, rebounds and assists and no shots, so every WNBA page read "FG% —"
#: in its headline. A number with nothing behind it gives way to the next spare, ranked the same way. A
#: baseball season read before its box scores were filled (engine/mlb/fulllines) holds the props' numbers
#: alone, so a hitter's page leads with those and a pitcher's with strikeouts a nine and games.
SPARE = {"box": (("min", "MIN", "Minutes a game", ("sum", "min"), True, False, None, True),),
         "batting": (("h", "H", "Hits", ("sum", "hits"), False, False, None, True),
                     ("tb", "TB", "Total bases", ("sum", "total_bases"), False, False, None, True),
                     ("pa", "PA", "Plate appearances", ("sum", "pa"), False, False, None, False)),
         "pitching": (("k9", "K/9", "Strikeouts a nine innings", ("k9",), False, False, "outs", True),
                      ("gp", "GP", "Games pitched", ("gp",), False, False, None, False))}


def headline_specs(sport: str, kind: str, summed: dict, gp: int) -> list:
    """[(spec, value)] for the headline: the kind's four, each with no value
    given way to the next spare that has one (SPARE)."""
    specs = [(sp, head_value(sport, sp, summed, gp)) for sp in HEAD.get(kind, ())]
    spares = ((sp, v) for sp in SPARE.get(kind, ()) for v in (head_value(sport, sp, summed, gp),) if v is not None)
    for i, (_, v) in enumerate(specs):
        if v is None:
            nxt = next(spares, None)
            if nxt is None:
                break
            specs[i] = nxt
    return specs


#: Who a kind's places are among: a player with one of these in the season.
#: (A hitter's strikeouts are no pitcher's, a skater's minutes no goalie's.)
ROLE_NEED = {"passing": ("pass_att",), "rushing": ("carries", "rush_att"), "receiving": ("receptions", "targets"),
             "kicking": ("fg_att", "xp_att"), "defense": ("tackles_ast", "tackles_solo"),
             "box": ("min",), "skater": ("goals", "assists", "points", "sog"), "goalie": ("shots_against",),
             "batting": ("pa",), "pitching": ("outs",)}
#: The four numbers from the newest game, by the column ids of the game log (the first four it has).
TILES = {
    "passing": ("passing.rtg", "passing.pct", "passing.yds", "passing.td"),
    "rushing": ("rushing.car", "rushing.yds", "rushing.avg", "rushing.td"),
    "receiving": ("receiving.rec", "receiving.tgt", "receiving.yds", "receiving.td"),
    "kicking": ("kicking.fg", "kicking.lng", "kicking.xp", "kicking.pts"),
    "defense": ("defense.tot", "defense.sack", "defense.int", "defense.pd"),
    "box": ("box.pts", "box.reb", "box.ast", "box.fg"),
    "skater": ("skater.g", "skater.a", "skater.sog", "skater.toi"),
    "goalie": ("goalie.sv", "goalie.sa", "goalie.svp", "goalie.ga"),
    # A baseball game's whole line where the box score is kept, else the props' numbers: the first four kept.
    "batting": ("batting.ab", "batting.h", "batting.hr", "batting.rbi", "batting.tb", "batting.pa"),
    "pitching": ("pitching.ip", "pitching.h", "pitching.er", "pitching.k"),
}


def tile_kind(sport: str, kind: str, stats: dict) -> str:
    """Whose tiles a game's card shows: the player's own kind, unless they
    did nothing there that game and did in another (2026-11-17, Jalon
    Daniels' page: a quarterback who threw no pass and ran twice read
    "YDS 0 · TD 0" for the passing; the runs were the game they had)."""
    def busy(k):
        return any((stats.get(m) or 0) > 0 for m in ROLE_NEED.get(k, ()))
    if not kind or busy(kind):
        return kind
    return next((k for k in KINDS.get(sport, ()) if k != kind and busy(k)), kind)


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")
_RANKS: dict = {}
_ROSTERS: dict = {}


#: The positions a football page reads as a kicker's or a defender's: the
#: board's own K and DEF (engine/sources/nflverse.board_position), and the
#: positions a roster prints.
KICKERS = frozenset({"K", "PK"})
DEFENDERS = frozenset({"DEF", "LB", "ILB", "OLB", "MLB", "DE", "DT", "NT", "DL", "EDGE", "CB", "S", "SS", "FS",
                       "DB", "SAF"})


#: WHY A FOOTBALL PAGE HAS NO NUMBERS, where that is the whole story: it
#: says so instead of "No seasons on file yet", which reads as a gap.
#: A box score keeps no line for an offensive lineman or a long snapper.
LINEMEN = frozenset({"OL", "OT", "OG", "T", "G", "C", "IOL"})
NO_BOX = {**{p: "offensive linemen" for p in LINEMEN}, "LS": "long snappers"}
#: The positions a box score has numbers for and the stats we read do not,
#: by league: no punting in either, and no tackler in college's play file
#: (engine/sources/cfbstats KICK_MARKETS).
NO_FEED = {"nfl": {"P": "punting"}, "cfb": {"P": "punting", **{p: "defense" for p in DEFENDERS}}}
#: How each league's feed is named in that note.
FEED_NAME = {"nfl": "NFL", "cfb": "college"}


#: What a page with games on file and not one number in them says.
NO_NUMBERS = "No stats are recorded in this player's games on file yet."
#: The NFL roster's 32 fantasy team defenses ("New England Patriots", DEF):
#: a fantasy pick, not a player.
TEAM_DEFENSE = "This is the team's defense as a fantasy pick, not a player. Its numbers are on the team's page."
#: A college roster's school with no game on file: the play file covers games
#: between FBS schools (engine/ingest.cfb_games_for).
NOT_FBS = "Our college stats cover games between FBS schools, and this school has none on file."


def no_stats_note(sport: str, position: str) -> str:
    """Why a football page has no numbers, where the position is the reason."""
    if sport not in FEED_NAME:
        return ""
    pos = str(position or "").upper()
    if sport == "nfl" and pos == "DEF":
        return TEAM_DEFENSE
    if pos in NO_BOX:
        return f"Box scores keep no numbers for {NO_BOX[pos]}, so there are none to show here."
    what = NO_FEED[sport].get(pos)
    return (f"Our {FEED_NAME[sport]} stats feed doesn't include {what}, so there are no numbers to show here."
            if what else "")


def _school_without_games(conn, sport: str, team: str) -> bool:
    """A college school with no game on file in the newest season."""
    if sport != "cfb" or not team or conn is None:
        return False
    row = conn.execute("SELECT MAX(season) FROM games WHERE sport='cfb'").fetchone()
    if not row or row[0] is None:
        return False
    return conn.execute("SELECT 1 FROM games WHERE sport='cfb' AND season=? AND (home=? OR away=?) LIMIT 1",
                        (int(row[0]), team, team)).fetchone() is None


def role(sport: str, position: str, s: dict) -> str:
    """What he does, for the headline: a passer, a runner or a receiver in
    football (his position first, else where his volume is), a goalie or a
    skater, a pitcher or a hitter; every basketball player is the box."""
    pos = str(position or "").upper()
    if sport in ("nfl", "cfb"):
        if pos == "QB":
            return "passing"
        if pos in ("RB", "FB", "HB"):
            return "rushing"
        if pos in ("WR", "TE"):
            return "receiving"
        if pos in KICKERS:
            return "kicking"
        if pos in DEFENDERS:
            return "defense"
        vol = {"passing": s.get("pass_att") or 0, "rushing": s.get("carries") or s.get("rush_att") or 0,
               "receiving": s.get("targets") or s.get("receptions") or 0,
               "kicking": (s.get("fg_att") or 0) + (s.get("xp_att") or 0),
               "defense": s.get("tackles_ast") or 0}
        best = max(vol, key=vol.get)
        return best if vol[best] > 0 else ""
    if sport in HOOPS:
        return "box"
    if sport == "nhl":
        return "goalie" if pos == "G" or s.get("shots_against") else "skater"
    if sport == "mlb":
        return "pitching" if pos in ("P", "SP", "RP") or (s.get("outs") and not s.get("pa")) else "batting"
    return ""


def _markets(how) -> tuple:
    kind = how[0]
    if kind == "rating":
        return ("pass_att", "pass_cmp", "pass_yds", "pass_td", "pass_int")
    if kind == "gaa":
        return ("goals_against", "toi")
    if kind == "k9":
        return ("strikeouts", "outs")
    if kind == "gp":
        return ()
    return tuple(how[1:])


def head_value(sport: str, spec: tuple, s: dict, gp: int):
    """One headline number off a season's summed stats (``gp`` games played)."""
    how, per_game = spec[3], spec[4]
    kind = how[0]
    if kind == "gaa":
        toi, ga = s.get("toi"), s.get("goals_against")
        return round(ga * 60.0 / toi, 2) if toi and ga is not None else None
    if kind == "k9":
        outs, k = s.get("outs"), s.get("strikeouts")
        return round(k * 27.0 / outs, 1) if outs and k is not None else None
    if kind == "gp":
        return gp or None
    if kind == "sum" and per_game:
        # Over the games that carry it (gamelog.add_up, step ACV), as the season's lines are.
        key = GL._first_key(s, how[1:])
        return round(float(s[key]) / GL.games_with(s, key, gp), 1) if key is not None and gp else None
    return GL.value(sport, how, s, gp)


def _rank_on(spec: tuple, s: dict, gp: int, sport: str):
    """The number a headline is ranked on (innings are ranked on outs; a rate
    printed as baseball prints it, ".312", on its number)."""
    if spec[3][0] == "ip":
        return s.get("outs")
    v = head_value(sport, spec, s, gp)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return v


def _league(conn, sport: str, season: int, markets) -> dict:
    """{player: ({market: season sum}, games played)} for the league's season."""
    marks = ",".join("?" * len(markets))
    args: list = [sport, season, *markets]
    bound = ""
    if sport not in GL.WEEKLY:
        # A day is a season's own, so its days bound the read to it (the
        # period index), rather than every season the league has kept.
        lo, hi = conn.execute("SELECT MIN(period), MAX(period) FROM games WHERE sport=? AND season=?",
                              (sport, season)).fetchone() or (None, None)
        if lo and hi:
            bound = " AND period BETWEEN ? AND ?"
            args += [str(lo), str(hi) + "~"]
    if sport in GL.ONE_A_WEEK:
        return _league_once_a_week(conn, sport, season, markets)
    out: dict = {}
    # With the days bound, the plain read walks the table's own key over every
    # market of the season (measured live 2026-11-16: 6.2 s for MLB's first
    # page); the market-and-day index reads the four markets wanted.
    sql = ("SELECT player, market, SUM(value), COUNT(*), SUM(CASE WHEN value > 0 THEN 1 ELSE 0 END) "
           f"FROM player_game_logs{' INDEXED BY idx_logs_period' if bound else ''} WHERE sport=? AND season=? "
           f"AND market IN ({marks}){bound} GROUP BY player, market")
    try:
        found = conn.execute(sql, args).fetchall()
    except Exception:                                     # noqa: BLE001 — a file without that index
        found = conn.execute(sql.replace(" INDEXED BY idx_logs_period", ""), args).fetchall()
    for player, market, total, n, pos in found:
        s, gp = out.get(player, ({}, 0))
        if total is not None:
            s[market] = float(total)
        # A basketball game counts where he played minutes; elsewhere a row is a game.
        played = int(pos or 0) if (sport in HOOPS and market == "min") else (0 if sport in HOOPS else int(n or 0))
        out[player] = (s, max(gp, played))
    return out


def _league_once_a_week(conn, sport: str, season: int, markets) -> dict:
    """`_league` where a game can sit in the file more than once (gamelog.ONE_A_WEEK):
    each player's rows a day or less apart are one game, its number the
    largest of the copies (a copy read short, or a play file's zero beside the
    box score's count, never adds to the season)."""
    marks = ",".join("?" * len(markets))
    seen: dict = {}
    for player, market, period, val in conn.execute(
            f"SELECT player, market, period, value FROM player_game_logs WHERE sport=? AND season=? "
            f"AND market IN ({marks})", [sport, season, *markets]):
        if val is not None:
            seen.setdefault(player, {}).setdefault(market, []).append((str(period), float(val)))
    out: dict = {}
    for player, by_market in seen.items():
        s, gp = {}, 0
        for market, rows in by_market.items():
            total, games, last = 0.0, 0, None
            best = None
            for period, val in sorted(rows):
                d = GL._day(period)
                if last is not None and d and (d - last).days <= 1:
                    best = max(best, val)
                    continue
                if best is not None:
                    total += best
                    games += 1
                best, last = val, d
            if best is not None:
                total += best
                games += 1
            s[market] = total
            gp = max(gp, games)
        out[player] = (s, gp)
    return out


def rank_table(conn, sport: str, season: int, kind: str, db_path=None, wait: bool = True) -> dict | None:
    """{headline key: {player: place}} for one season and one kind of player.
    Kept, and rebuilt in the background once RANK_TTL old while the old one
    answers; built here only the first time (`warm` builds them at start).
    A table missing from memory is read from disk first (`_ranks_load`).

    NEVER BUILT WHILE A READER WAITS (step AFU, 25 November 2026; Ethan: "data
    on the player page takes a long time to load"). `warm` builds each league's
    newest season, so a page for an older one built its table on the reader's
    ask: Cameron Boozer's college page (his newest season is 2025-26) took
    29.3 s on the live site, 28.7 s of it the college table (7.1 s of the
    server's own time, the rest the disk and its turn). With ``wait`` False
    (the site's pages) a table neither kept nor on disk is built behind the
    page and None comes back: the page answers without its places this once."""
    key = (sport, int(season), kind)
    hit = _RANKS.get(key)
    if not hit:
        hit = _ranks_load(_ranks_file(conn, key, db_path))
        if hit:
            _RANKS[key] = hit
    if hit:
        if time.time() - hit[0] >= RANK_TTL:
            _refresh_later(key, db_path)
        return hit[1]
    if not wait:
        _refresh_later(key, db_path)
        return None
    table = _build_table(conn, sport, int(season), kind)
    _RANKS[key] = (time.time(), table)
    _ranks_save(_ranks_file(conn, key, db_path), _RANKS[key][0], table)
    return table


# --- the tables, kept on disk -------------------------------------------------------------
#: THE LEAGUE PLACES SURVIVE A RESTART (step AFO, 25 November 2026; Ethan: "data on the player page takes a long
#: time to load"). The tables lived only in the server's memory, so every restart (each deploy) emptied them, and
#: the first reader of each kind's page waited for its build until `warm` ran, which on the box is after the boards
#: are rebuilt: Kerby Joseph's page took 3.7 s, 3.5 s of it the defenders' table, and Jahmyr Gibbs's 2.8 s. Each
#: table built is written beside the history file (cache/ranks/), with when it was built and the code that built
#: it; a table missing from memory is read from there, and past RANK_TTL it answers while a new one is built, as a
#: kept one does. A file the code since changed is not read.
def _code_stamp(*files) -> str:
    h = hashlib.sha1()
    for f in files:
        with open(f, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:12]


_RANKS_CODE = _code_stamp(__file__, GL.__file__)
_RANKS_SAVE_SAID = [False]


def _ranks_file(conn, key: tuple, db_path=None) -> str:
    """Where a table is kept: cache/ranks/ beside the history file the table is read from; "" for none."""
    path = str(db_path or "")
    if not path and conn is not None:
        try:
            row = conn.execute("PRAGMA database_list").fetchone()
            path = str(row[2] or "") if row else ""
        except sqlite3.Error:
            path = ""
    if not path:
        return ""                                # a database in memory keeps nothing on disk
    sport, season, kind = key
    return os.path.join(os.path.dirname(os.path.abspath(path)), "cache", "ranks", f"{sport}_{int(season)}_{kind}.json")


def _ranks_save(path: str, built: float, table: dict) -> None:
    if not path:
        return
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"built": built, "code": _RANKS_CODE, "table": table}, fh, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError as exc:
        # The table still answers from memory; only the next restart waits for it again, so say so once.
        if not _RANKS_SAVE_SAID[0]:
            _RANKS_SAVE_SAID[0] = True
            print(f"⚠️  player page ranks not kept on disk ({type(exc).__name__}: {exc}): a restart builds them again",
                  file=sys.stderr)


def _ranks_load(path: str):
    """``(built, table)`` kept on disk by this code, or None."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("code") != _RANKS_CODE or not isinstance(doc.get("table"), dict):
        return None
    return float(doc.get("built") or 0.0), doc["table"]


def _refresh_later(key: tuple, db_path=None) -> threading.Thread | None:
    if key in _REFRESHING:
        return None
    _REFRESHING.add(key)
    t = threading.Thread(target=_rebuild_ranks, args=(key, db_path), name="playerpage-rank", daemon=True)
    t.start()
    return t


def _rebuild_ranks(key: tuple, db_path=None) -> None:
    """One table rebuilt in the background. A failure leaves the old table
    answering, which looks like a quiet night's ranks; so the first failure in
    a process says so, once, in the service's log."""
    global _RANK_FAIL_SAID
    try:
        conn = _db.connect(str(db_path or _db.DEFAULT_DB))
        try:
            _RANKS[key] = (time.time(), _build_table(conn, *key))
            _ranks_save(_ranks_file(conn, key, db_path or _db.DEFAULT_DB), *_RANKS[key])
        finally:
            conn.close()
    except Exception as exc:                              # noqa: BLE001 — the old table keeps answering
        if not _RANK_FAIL_SAID:
            _RANK_FAIL_SAID = True
            print(f"⚠️  player page ranks not rebuilt for {key} ({type(exc).__name__}: {exc}): "
                  "the pages show the table built before", file=sys.stderr)
    finally:
        _REFRESHING.discard(key)


def forget_ranks(sport: str, db_path=None) -> int:
    """Drop a league's kept rank tables, so the next ask (or `warm`, which
    builds only the ones missing) reads the rows as they now stand. For a
    fill that writes a column the tables were built without
    (launch._fill_missing_lines): live on 17 Nov a page asked for during the
    first fill built the kickers' table off a few nights' tries, and kept it
    six hours (RANK_TTL), Cameron Dicker first in everything and Brandon
    Aubrey in nothing. Returns how many it dropped."""
    gone = [k for k in list(_RANKS) if k[0] == sport]
    for k in gone:
        _RANKS.pop(k, None)
    # ...and the copies kept on disk (step AFO), or the next restart would read them back.
    import glob
    for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(str(db_path or _db.DEFAULT_DB))), "cache",
                                    "ranks", f"{sport}_*.json")):
        try:
            os.remove(f)
        except OSError:
            pass
    return len(gone)


def warm(db_path=None, delay: float = 60.0) -> threading.Thread:
    """Every league's rank tables for its newest season, built in the
    background (after ``delay`` seconds, so the server's own start comes
    first), so no player's page waits on one. Returns the thread."""
    def run():
        time.sleep(delay)
        path = str(db_path or _db.DEFAULT_DB)
        if not os.path.exists(path):
            return
        conn = _db.connect(path)
        try:
            for sport, kinds in KINDS.items():
                row = conn.execute("SELECT MAX(season) FROM games WHERE sport=?", (sport,)).fetchone()
                if not row or row[0] is None:
                    continue
                for kind in kinds:
                    key = (sport, int(row[0]), kind)
                    # One build of a table at a time: one a page started behind it (step AFU) is left to finish.
                    if key in _RANKS or key in _REFRESHING:
                        continue
                    kept = _ranks_load(_ranks_file(conn, key, path))       # kept on disk (step AFO)
                    if kept and time.time() - kept[0] < RANK_TTL:
                        _RANKS[key] = kept
                        continue
                    _REFRESHING.add(key)
                    try:
                        _RANKS[key] = (time.time(), _build_table(conn, *key))
                        _ranks_save(_ranks_file(conn, key, path), *_RANKS[key])
                    except Exception:                     # noqa: BLE001 — that table is built on first ask
                        continue
                    finally:
                        _REFRESHING.discard(key)
        finally:
            conn.close()
    t = threading.Thread(target=run, name="playerpage-warm", daemon=True)
    t.start()
    return t


def _build_table(conn, sport: str, season: int, kind: str) -> dict:
    specs = tuple(HEAD.get(kind) or ()) + tuple(SPARE.get(kind, ()))
    need = ROLE_NEED.get(kind, ())
    markets = {m for sp in specs for m in _markets(sp[3])} | {sp[6] for sp in specs if sp[6]} | set(need)
    if sport in HOOPS:
        markets.add("min")
    league = _league(conn, sport, int(season), sorted(markets)) if markets else {}
    if need:
        league = {p: x for p, x in league.items() if any((x[0].get(m) or 0) > 0 for m in need)}
    # The bar for a basketball average: half the games of a regular, read at the
    # 90th percentile, not the single most. The table is keyed by name, and a
    # name several college players share counts all their games as one man's
    # (seen live 2026-11-16: no college player with 6 games could be placed).
    gps = sorted(gp for _, gp in league.values())
    most_games = gps[int(0.9 * (len(gps) - 1))] if gps else 0
    table: dict = {}
    for sp in specs:
        if not sp[7]:
            continue
        vol_key, low, per_game = sp[6], sp[5], sp[4]
        vals = {}
        for player, (s, gp) in league.items():
            v = _rank_on(sp, s, gp, sport)
            if v is None:
                continue
            if vol_key is None and not per_game and not v:
                continue                       # a count of nothing is not a place
            vals[player] = (float(v), float(s.get(vol_key) or 0) if vol_key else 0.0, gp)
        if vol_key:
            lead = max((x[1] for x in vals.values()), default=0.0)
            vals = {p: x for p, x in vals.items() if x[1] > 0 and x[1] >= RATE_SHARE * lead}
        if per_game:
            vals = {p: x for p, x in vals.items() if x[2] >= max(1.0, GAMES_SHARE * most_games)}
        # A place is one more than the players strictly ahead of him (ties share it).
        asc = sorted(x[0] for x in vals.values())
        table[sp[0]] = {p: 1 + (bisect.bisect_left(asc, x[0]) if low else len(asc) - bisect.bisect_right(asc, x[0]))
                        for p, x in vals.items()}
    return table


# --- the roster's facts --------------------------------------------------------------------
def _roster_doc(sport: str, data_dir=None) -> dict:
    path = os.path.join(str(data_dir or ROSTER_DIR), f"rosters_{sport}.json")
    try:
        stamp = os.stat(path).st_mtime
    except OSError:
        return {}
    hit = _ROSTERS.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    _ROSTERS[path] = (stamp, doc)
    return doc


#: THE ROSTER BY NAME (step AFP, 25 November 2026; Ethan: "data on the player page takes a long time to load"). A
#: page found its player by putting every row of the league's roster through `core_name`: on the live college
#: roster (9.2 MB) that was about half a second of every college player's page (Jeremiah Smith's 506 ms of 557).
#: Each roster file, as read, is indexed once by its names' cores, in its own order.
_ROSTER_BY_NAME: dict = {}


def _roster_names(sport: str, data_dir=None) -> dict:
    """{core name: [(club, row)]} over the league's published roster, rebuilt when the file is read again."""
    doc = _roster_doc(sport, data_dir)
    key = os.path.join(str(data_dir or ROSTER_DIR), f"rosters_{sport}.json")
    hit = _ROSTER_BY_NAME.get(key)
    if hit and hit[0] is doc:
        return hit[1]
    index: dict = {}
    for club, entry in ((doc.get("teams") or {}).items()):
        rows = (entry.get("players") if isinstance(entry, dict) else entry) or []
        for r in rows:
            if isinstance(r, dict):
                index.setdefault(core_name(r.get("player") or ""), []).append((club, r))
    _ROSTER_BY_NAME[key] = (doc, index)
    return index


def roster_row(sport: str, player: str, team: str = "", data_dir=None, position: str = "") -> dict:
    """His row on the published roster: on his club's where the club is known;
    else the one row of that name (two men of one name are neither).

    THE ONE ROW ON ANOTHER CLUB IS HIM ONLY IN HIS POSITION (2026-11-16). The
    live college roster lost 268 schools' pages one night, Ohio State's among
    them, and Jeremiah Smith's page (the Buckeyes' receiver, every game in his
    log) took the one "Jeremiah Smith" left, Louisiana Tech's linebacker, for
    its header: "LT · LB". A trade or a transfer moves a man to another club
    in his position; a namesake on another club in another one is not him.
    `position` is what his logs say he plays."""
    # By the name's core (core_name), so the box scores' "Nolan Smith" finds
    # the roster's "Nolan Smith Jr.": his number, size and face, not the
    # stored rows' "DEF" (live, 17 Nov).
    want = core_name(player)
    if not want:
        return {}
    hits = [dict(r, team=r.get("team") or club) for club, r in _roster_names(sport, data_dir).get(want, ())]
    if team:
        mine = [r for r in hits if r.get("team") == team]
        if mine:
            return mine[0]
    if len(hits) != 1:
        return {}
    one = hits[0]
    theirs = str(one.get("position") or "").strip().upper()
    if team and position and theirs and theirs != str(position).strip().upper():
        return {}
    return one


#: The generational marks a roster and a box score disagree on: "Nolan Smith
#: Jr." on the Eagles' roster is "Nolan Smith" in every box score.
SUFFIXES = ("Jr.", "Jr", "Sr.", "Sr", "II", "III", "IV", "V")
_SUFFIX_WORDS = frozenset(w.rstrip(".").lower() for w in SUFFIXES)


def core_name(name: str) -> str:
    """A name as two spellings of one person share it: accents, punctuation
    and case dropped (playersearch.norm), initials run together ("D.J." and
    "DJ" are both "dj"), and a generational suffix dropped too."""
    from .playersearch import norm
    words, run = [], ""
    for w in norm(name).split():
        if len(w) == 1:
            run += w
            continue
        if run:
            words.append(run)
            run = ""
        words.append(w)
    if run:
        words.append(run)
    while len(words) > 2 and words[-1] in _SUFFIX_WORDS:
        words.pop()
    return " ".join(words)


def _suffix_spellings(player: str) -> list:
    """The same name with its suffix dropped, or with each suffix added."""
    words = str(player or "").split()
    if len(words) > 2 and words[-1].rstrip(".").lower() in _SUFFIX_WORDS:
        return [" ".join(words[:-1])]
    return [f"{player} {suf}" for suf in SUFFIXES]


def stored_name(conn, sport: str, player: str, team: str = "", data_dir=None) -> str:
    """The name the history file keeps this player's games under, or "".

    The exact name when it has games. Else the same person's other spelling:
    with or without a generational suffix ("Nolan Smith Jr." is "Nolan Smith"
    in the box scores), or the nearest stored name (statlogs.resolve_player)
    when it is the same name written another way ("D.J. Moore", "DJ Moore").
    A typed name no roster carries takes the nearest stored name, typo and
    all. A NAME A ROSTER CARRIES IS NEVER SOMEONE ELSE'S (2026-11-17): JK
    Scott, the Chargers' punter, has no games on file, and his page drew Nick
    Scott's, the Panthers' safety; and on one club, Anthony Richardson Sr.'s
    drew Anthony Gould's, Caleb Tiernan's Caleb Banks', Jakob Robinson's
    Wan'Dale Robinson's. And a closest spelling stands in only for a misspelling
    of the whole name (statlogs.resolve_player, 2026-11-17: college's page for
    Cooper Flagg drew TJ Cope's, "Cope" being near "Cooper")."""
    if GL.seasons_of(conn, sport, player):
        return player
    other = _suffix_spellings(player)
    marks = ",".join("?" * len(other))
    found = [r[0] for r in conn.execute(
        f"SELECT DISTINCT player FROM player_game_logs WHERE sport=? AND player IN ({marks})", (sport, *other))]
    if found:
        return found[0]
    from .statlogs import resolve_player
    near = resolve_player(conn, sport, player)
    if not near or core_name(near) == core_name(player):
        return near or ""
    return "" if roster_row(sport, player, team, data_dir) else near


def _birthplace(sport: str, row: dict, player: str, position: str) -> str:
    if row.get("birthplace"):
        return str(row["birthplace"])
    if sport != "nfl":
        return ""
    try:                         # the hometown table keeps NFL birthplaces
        from . import hometown
        hit = hometown.lookup(hometown.load(), player, position)
    except Exception:                                     # noqa: BLE001
        hit = None
    return f"{hit['city']}, {hit['state']}" if hit and hit.get("city") else ""


#: ONE HEIGHT AND ONE WEIGHT, AS THE NFL'S PAGE SAYS THEM (22 November 2026; Ethan: "every single sports player
#: pages to match each other ... NFL is kind of like the one we want to go off of"). Each league's roster comes
#: from its own feed and each feed spells them its own way: the NFL's and the NHL's 6'5" and 237 lb, ESPN's
#: (basketball's, college's) 6' 2" and 190 lbs, and some feeds a bare 74 inches or 190. Every page says 6'2"
#: and 190 lb now; anything it cannot read is said as the feed said it.
_FEET = re.compile(r"^\s*(\d)\s*(?:'|’|ft\.?|-)\s*(\d{1,2})\s*(?:\"|”|''|in\.?)?\s*$")
_INCHES = re.compile(r"^\s*(\d{2})(?:\.\d+)?\s*$")
_POUNDS = re.compile(r"^\s*(\d{2,3})(?:\.\d+)?\s*(?:lbs?\.?|pounds)?\s*$", re.I)


def nfl_height(v) -> str:
    """A height as 6'2" (feet and inches, no space), from any feed's spelling; blank stays blank."""
    s = "" if v is None else str(v).strip()
    m = _FEET.match(s)
    if m and 0 <= int(m.group(2)) < 12:
        return f"{int(m.group(1))}'{int(m.group(2))}\""
    m = _INCHES.match(s)
    if m and 48 <= int(m.group(1)) <= 95:
        n = int(m.group(1))
        return f"{n // 12}'{n % 12}\""
    return s


def nfl_weight(v) -> str:
    """A weight as 190 lb, from any feed's spelling; blank stays blank."""
    s = "" if v is None else str(v).strip()
    m = _POUNDS.match(s)
    return f"{int(m.group(1))} lb" if m and 80 <= int(m.group(1)) <= 450 else s


def bio(sport: str, player: str, row: dict, position: str = "") -> dict:
    """The facts a roster publishes, as it publishes them (blank is unknown), the height and weight said one
    way in every league (`nfl_height`, `nfl_weight`)."""
    pick = lambda k: row.get(k) if row.get(k) not in (None, "") else ""        # noqa: E731
    return {"team": pick("team"), "number": "" if pick("number") == "" else str(row["number"]),
            "position": pick("position") or position, "height": nfl_height(pick("height")),
            "weight": nfl_weight(pick("weight")),
            "age": pick("age"), "born": pick("born"),
            "birthplace": _birthplace(sport, row, player, pick("position") or position),
            "college": pick("college"), "years_exp": pick("years_exp"), "rookie": bool(row.get("rookie")),
            # A college player's class ("Junior"): what ESPN's header says of him where it has no age.
            "class": pick("class"),
            "shoots": pick("shoots"), "status": pick("status"), "headshot": pick("headshot")}


def notes(sport: str, player: str, row: dict, data_dir=None) -> dict:
    """His roster's latest note (the injury and its words, where it has them)
    and his moves between clubs in the roster file's window."""
    hurt = None
    if row.get("injury_status") or row.get("injury") or row.get("injury_note"):
        hurt = {"status": row.get("injury_status") or "", "what": row.get("injury") or "",
                "note": row.get("injury_note") or "", "back": row.get("return_date") or "",
                "source": row.get("injury_source") or ""}
    from .playersearch import norm
    want = norm(player)
    moves = [{"from": m.get("from") or "", "to": m.get("to") or "", "date": m.get("date") or ""}
             for m in (((_roster_doc(sport, data_dir).get("transactions") or {}).get("moves")) or [])
             if isinstance(m, dict) and norm(m.get("player") or "") == want]
    return {"injury": hurt, "moves": moves}


# --- the history file ----------------------------------------------------------------------
def _groups(sport: str, games) -> list:
    """The layout's groups he has a number in, and the columns the file keeps."""
    out = []
    for key, title, marks, cols in GL.LAYOUTS[sport]:
        if not GL.shows(games, marks):
            continue
        kept = [c for c in cols if any(GL.value(sport, c[3], g["stats"]) is not None for g in games)]
        if kept:
            out.append((key, title, kept))
    return out


def _shape(groups) -> list:
    return [{"key": k, "title": t, "cols": [{"key": c[0], "label": c[1], "title": c[2]} for c in cols]}
            for k, t, cols in groups]


def _sum(games) -> dict:
    s: dict = {}
    for g in games:
        GL.add_up(s, g["stats"])
    return s


def averaged(sport: str, how: tuple, s: dict, gp: int):
    """A column as a game's average: a count over the games, made-tried as
    each a game's, innings as a game's outs; a rate is the rate."""
    if not gp:
        return None
    kind = how[0]
    # Each over the games that carry it (gamelog.add_up, step ACV): a column some of the season's box scores were
    # read without is averaged over the ones that have it, made-tried over the games with both.
    if kind == "sum":
        key = GL._first_key(s, how[1:])
        return None if key is None else round(float(s[key]) / GL.games_with(s, key, gp), 1)
    if kind == "made":
        made, tried, n = GL.paired(s, how[1], how[2])
        n = n or gp
        return None if made is None or tried is None else f"{made / n:.1f}-{tried / n:.1f}"
    if kind == "ip":
        outs = s.get(how[1])
        if outs is None:
            return None
        o = int(round(outs / GL.games_with(s, how[1], gp)))
        return f"{o // 3}.{o % 3}"
    return GL.value(sport, how, s, gp)


def _line(sport: str, groups, s: dict, gp: int, per_game: bool) -> dict:
    return {f"{k}.{c[0]}": (averaged(sport, c[3], s, gp) if per_game else GL.value(sport, c[3], s, gp))
            for k, _, cols in groups for c in cols}


def starter_hands(conn, season: int) -> dict:
    """``{(day, club): hand}``: the hand of each club's starter, a day at a
    time, for a season's MLB games. A club with two starters on a day (a
    doubleheader) is left out: which game a hitter's row is cannot be told
    from the day alone."""
    seen: dict = {}
    for period, team, throws in conn.execute(
            "SELECT period, team, throws FROM game_starters WHERE sport='mlb' AND season=?", (int(season),)):
        seen.setdefault((str(period)[:10], team), []).append(str(throws or "").upper()[:1])
    return {k: v[0] for k, v in seen.items() if len(v) == 1 and v[0] in ("L", "R")}


def _date_of(sport: str, g: dict, res: dict | None) -> str:
    if sport in GL.WEEKLY and not GL._ISO.match(g["period"]):
        return str((res or {}).get("date") or "")[:10]
    return g["period"][:10]


def _record(by_id: dict, team: str, through: str, sport: str = "") -> str:
    """A club's wins and losses (and ties) in the season through one period.

    EACH GAME ONCE (22 November 2026): college football's games table can hold one game more than once
    (engine/standings.once, which its standings and team pages already read), and this counted every copy:
    Ohio State "15-9" on Jeremiah Smith's page, 7-4 on the field."""
    from .standings import once
    rows = [r for r in by_id.values()
            if team in (r["home"], r["away"]) and r["hs"] is not None and r["as"] is not None
            and r["period"] <= through]
    w = l = t = 0
    for r in (once(sport, rows) if sport else rows):
        mine, theirs = (r["hs"], r["as"]) if r["home"] == team else (r["as"], r["hs"])
        if mine > theirs:
            w += 1
        elif mine < theirs:
            l += 1
        else:
            t += 1
    if not (w or l or t):
        return ""
    return f"{w}-{l}" + (f"-{t}" if t else "")


def page(sport: str, player: str, team: str = "", season=None, db_path=None, data_dir=None, took=None,
         wait_ranks: bool = True) -> dict:
    """Everything his page's menus show; ``{}`` for a league with no layout or
    a name neither the history file nor a roster knows.

    ``took``, a list, gets each part's milliseconds as ``(part, ms)``, in order:
    server.py sends them as a Server-Timing header (step AFK, 25 November 2026:
    Amon-Ra St. Brown's page took 4.4 s to answer once and 0.2 s a minute later,
    and the box's data cannot be timed from anywhere else)."""
    if sport not in GL.LAYOUTS or not player:
        return {}
    clock = [time.perf_counter()]

    def mark(part):
        if took is not None:
            now = time.perf_counter()
            took.append((part, (now - clock[0]) * 1000.0))
            clock[0] = now
    path = str(db_path or _db.DEFAULT_DB)
    rows: list = []
    seasons: list = []
    conn = _db.connect(path) if os.path.exists(path) else None
    mark("open")
    try:
        if conn is not None:
            player = stored_name(conn, sport, player, team, data_dir) or player
            mark("name")
            seasons = GL.seasons_of(conn, sport, player)
            if seasons:
                rows = conn.execute(
                    "SELECT season, period, game_id, team, opponent, position, home, market, value "
                    "FROM player_game_logs WHERE sport=? AND player=?", (sport, player)).fetchall()
            mark("rows")
        by_season: dict = {}
        for yr, period, gid, club, opp, pos, home, market, val in rows:
            gs = by_season.setdefault(int(yr), {})
            g = gs.setdefault((str(period), str(gid)), {"period": str(period), "game_id": str(gid), "team": club,
                                                        "opponent": opp, "position": pos, "home": home,
                                                        "stats": {}})
            if pos and not g["position"]:
                g["position"] = pos                # a box score's pinch hitter has none (engine/mlb/fulllines)
            if val is not None:
                g["stats"][market] = float(val)
        by_season = {yr: {(g["period"], g["game_id"]): g for g in GL.collapse(sport, list(gs.values()))}
                     for yr, gs in by_season.items()}
        mark("merge")
        newest = max((g for gs in by_season.values() for g in gs.values()), key=lambda g: g["period"], default=None)
        my_team = team or ((newest or {}).get("team") or "")
        # What the logs say the player plays, never a basketball box score's starter flag
        # (engine/rosters.shown_position): "Duke Blue Devils · S" was that flag.
        logged = rosters.shown_position(sport, (newest or {}).get("position"))
        row = roster_row(sport, player, my_team, data_dir, position=logged)
        mark("roster")
        position = rosters.shown_position(sport, row.get("position")) or logged
        out = {"sport": sport, "player": player, "team": row.get("team") or my_team, "position": position,
               "bio": bio(sport, player, row, position), "notes": notes(sport, player, row, data_dir),
               "seasons": seasons}
        mark("notes")
        if not seasons:
            note = no_stats_note(sport, position) or (
                NOT_FBS if _school_without_games(conn, sport, out["team"]) else "")
            if note:
                out["no_stats"] = note
            return out if row else {}
        season = int(season) if season and str(season).isdigit() and int(season) in seasons else seasons[0]
        out["season"] = season
        # THE LEAGUE'S OWN NEWEST SEASON (step AFV): a page whose player's newest season is older (Cameron Boozer's
        # college page shows 2025-26 in 2026-27) says where he ranked that season, not "this season".
        # Read off the box scores (their key leads with sport and season), as his own seasons are; a schedule
        # can carry next season's games before one is played.
        newest = conn.execute("SELECT MAX(season) FROM player_game_logs WHERE sport=?", (sport,)).fetchone()
        if newest and newest[0] is not None:
            out["league_season"] = int(newest[0])
        by_id, by_pair = GL._results(conn, sport, season)
        mark("results")
        games = []
        for g in by_season.get(season, {}).values():
            res = by_id.get(g["game_id"]) or by_pair.get((g["period"], frozenset((g["team"], g["opponent"]))))
            sat = not GL._played(sport, g["stats"])
            day = _date_of(sport, g, res)
            bare = not sat and not GL.has_line(sport, g["stats"])
            # A row with no line waits for its box score a few days (GL.awaiting_line); past
            # that it is a game the player recorded nothing in, not one still to come.
            waiting = bare and GL.awaiting_line(sport, day)
            g = dict(g, home=(res["home"] == g["team"]) if res else bool(g["home"]), res=res,
                     date=day, played=not sat and not bare, dnp=sat, pending=waiting, no_line=bare and not waiting)
            if res and res["hs"] is not None and res["as"] is not None:
                mine, theirs = (res["hs"], res["as"]) if g["home"] else (res["as"], res["hs"])
                g["result"] = "W" if mine > theirs else "L" if mine < theirs else "T"
                g["score"] = f"{int(mine)}-{int(theirs)}"
            games.append(g)
        games.sort(key=lambda g: (g["period"], g["date"]), reverse=True)
        played = [g for g in games if g["played"]]
        groups = _groups(sport, played or games)
        summed, gp = _sum(played), len(played)
        kind = role(sport, position, summed)
        out["role"] = kind
        groups = GL.role_first(groups, kind)             # his own group first, as ESPN's (step AFW)
        per_game = sport in HOOPS
        mark("games")

        # The headline, with the league's places.
        places = rank_table(conn, sport, season, kind, db_path=path, wait=wait_ranks) \
            if kind and conn is not None else {}
        if places is None:
            # Its table is being built behind this answer (step AFU): no places this once, and said so, so the
            # server keeps no copy of it and the page asks again for them (js/playerpage.js plrRanksLater).
            places, out["ranks_pending"] = {}, True
        out["headline"] = [{"key": sp[0], "label": sp[1], "title": sp[2], "value": v,
                            "rank": (places.get(sp[0]) or {}).get(player) if sp[7] else None,
                            "per_game": sp[4], "low": sp[5]}
                           for sp, v in headline_specs(sport, kind, summed, gp)]
        mark("ranks")
        # GAMES ON FILE THIS SEASON AND NONE PLAYED (hurt, inactive, nothing in
        # the box score), none still waiting for a line: the Overview shows the
        # newest season the player did play, said as such, where it showed
        # nothing (Jake Tonges, 2026: one game on file, no line).
        if games and not played and not any(g["pending"] for g in games):
            for yr in seasons:
                past = [g for g in by_season.get(yr, {}).values()
                        if yr < season and GL._played(sport, g["stats"]) and GL.has_line(sport, g["stats"])]
                if past:
                    was = _sum(past)
                    out["prior"] = {"season": yr, "headline": [
                        {"key": sp[0], "label": sp[1], "title": sp[2], "value": v, "rank": None,
                         "per_game": sp[4], "low": sp[5]}
                        for sp, v in headline_specs(sport, role(sport, position, was) or kind, was, len(past))]}
                    break

        # The newest game.
        if games:
            g = games[0]
            vals = {f"{k}.{c[0]}": GL.value(sport, c[3], g["stats"]) for k, _, cols in groups for c in cols}
            labels = {f"{k}.{c[0]}": (c[1], c[2]) for k, _, cols in groups for c in cols}
            last = {"date": g["date"], "opponent": g["opponent"] or "", "home": g["home"], "team": g["team"] or "",
                    "values": vals, "dnp": g["dnp"], "pending": g["pending"], "no_line": g["no_line"],
                    "tiles": [{"id": t, "label": labels[t][0], "title": labels[t][1], "value": vals.get(t)}
                              for t in TILES.get(tile_kind(sport, kind, g["stats"]), ())
                              if t in labels and vals.get(t) is not None][:4]}
            if sport in GL.WEEKLY and not GL._ISO.match(g["period"]):
                try:
                    last["week"] = int(g["period"])
                except ValueError:
                    pass
            if g.get("result"):
                last["result"], last["score"] = g["result"], g["score"]
                if sport not in NO_RECORDS:
                    last["record"] = _record(by_id, g["team"], g["period"], sport)
                    last["opp_record"] = _record(by_id, g["opponent"], g["period"], sport)
            out["last"] = last

        # The season's splits, a game's average at a time (a baseball split's totals: SPLIT_TOTALS).
        split_rows = []
        averages = sport not in SPLIT_TOTALS

        def add(key, label, chosen):
            if chosen:
                split_rows.append({"key": key, "label": label, "gp": len(chosen),
                                   "values": _line(sport, groups, _sum(chosen), len(chosen), averages)})
        add("season", "Season", played)
        if len(played) > 5:
            add("last5", "Last 5 games", played[:5])
        add("home", "Home", [g for g in played if g["home"]])
        add("away", "Away", [g for g in played if not g["home"]])
        add("wins", "Wins", [g for g in played if g.get("result") == "W"])
        add("losses", "Losses", [g for g in played if g.get("result") == "L"])
        if sport == "mlb" and kind == "batting" and conn is not None:
            hands = starter_hands(conn, season)
            for hand, label in HANDS:
                add(f"hand:{hand}", label, [g for g in played if hands.get((g["date"], g["opponent"])) == hand])
        months: dict = {}
        for g in played:
            if GL._ISO.match(g["date"] or ""):
                months.setdefault(g["date"][:7], []).append(g)
        for ym, chosen in months.items():
            add(f"m:{ym}", _MONTHS[int(ym[5:7]) - 1], chosen)
        opps: dict = {}
        for g in played:
            if g["opponent"]:
                opps.setdefault(g["opponent"], []).append(g)
        for opp, chosen in opps.items():
            add(f"vs:{opp}", f"vs {opp}", chosen)
        out["splits"] = {"season": season, "groups": _shape(groups), "rows": split_rows,
                         **({} if averages else {"totals": True})}
        mark("splits")

        # Season by season.
        counts = lambda g: GL._played(sport, g["stats"]) and GL.has_line(sport, g["stats"])   # noqa: E731
        every = [g for gs in by_season.values() for g in gs.values() if counts(g)]
        cgroups = GL.role_first(_groups(sport, every), kind)
        career_rows = []
        for yr in sorted(by_season, reverse=True):
            mine = [g for g in by_season[yr].values() if counts(g)]
            if not mine:
                continue
            clubs: dict = {}
            for g in sorted(mine, key=lambda g: g["period"]):
                if g["team"]:
                    clubs[g["team"]] = clubs.get(g["team"], 0) + 1
            career_rows.append({"season": yr, "team": "/".join(clubs), "gp": len(mine),
                                "values": _line(sport, cgroups, _sum(mine), len(mine), per_game)})
        if not cgroups:
            out["no_stats"] = no_stats_note(sport, position) or NO_NUMBERS
        out["career"] = {"groups": _shape(cgroups), "per_game": per_game, "rows": career_rows,
                         "total": {"gp": len(every), "values": _line(sport, cgroups, _sum(every), len(every),
                                                                     per_game)}}
        out["bio"].update({"first_season": min(seasons), "last_season": max(seasons), "games": len(every)})
        mark("career")
        return out
    finally:
        if conn is not None:
            conn.close()
