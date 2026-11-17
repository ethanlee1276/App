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
  * splits   the season a game's average at a time: all of it, the last
             five, home and away, wins and losses, month by month and
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
import json
import os
import sys
import threading
import time

from . import db as _db
from . import gamelog as GL

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
    "batting": (("h", "H", "Hits", ("sum", "hits"), False, False, None, True),
                ("hr", "HR", "Home runs", ("sum", "home_runs"), False, False, None, True),
                ("tb", "TB", "Total bases", ("sum", "total_bases"), False, False, None, True),
                ("pa", "PA", "Plate appearances", ("sum", "pa"), False, False, None, False)),
    "pitching": (("k", "K", "Strikeouts", ("sum", "strikeouts"), False, False, None, True),
                 ("ip", "IP", "Innings pitched", ("ip", "outs"), False, False, None, True),
                 ("k9", "K/9", "Strikeouts a nine innings", ("k9",), False, False, "outs", True),
                 ("gp", "GP", "Games pitched", ("gp",), False, False, None, False)),
}
#: Who a kind's places are among: a player with one of these in the season.
#: (A hitter's strikeouts are no pitcher's, a skater's minutes no goalie's.)
ROLE_NEED = {"passing": ("pass_att",), "rushing": ("carries", "rush_att"), "receiving": ("receptions", "targets"),
             "kicking": ("fg_att", "xp_att"), "defense": ("tackles_ast", "tackles_solo"),
             "box": ("min",), "skater": ("goals", "assists", "points", "sog"), "goalie": ("shots_against",),
             "batting": ("pa",), "pitching": ("outs",)}
#: The four numbers from his newest game, by the column ids of the game log.
TILES = {
    "passing": ("passing.rtg", "passing.pct", "passing.yds", "passing.td"),
    "rushing": ("rushing.car", "rushing.yds", "rushing.avg", "rushing.td"),
    "receiving": ("receiving.rec", "receiving.tgt", "receiving.yds", "receiving.td"),
    "kicking": ("kicking.fg", "kicking.lng", "kicking.xp", "kicking.pts"),
    "defense": ("defense.tot", "defense.sack", "defense.int", "defense.pd"),
    "box": ("box.pts", "box.reb", "box.ast", "box.fg"),
    "skater": ("skater.g", "skater.a", "skater.sog", "skater.toi"),
    "goalie": ("goalie.sv", "goalie.sa", "goalie.svp", "goalie.ga"),
    "batting": ("batting.h", "batting.tb", "batting.hr", "batting.pa"),
    "pitching": ("pitching.ip", "pitching.k"),
}
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


def no_stats_note(sport: str, position: str) -> str:
    """Why a football page has no numbers, where the position is the reason."""
    if sport not in FEED_NAME:
        return ""
    pos = str(position or "").upper()
    if pos in NO_BOX:
        return f"Box scores keep no numbers for {NO_BOX[pos]}, so there are none to show here."
    what = NO_FEED[sport].get(pos)
    return (f"Our {FEED_NAME[sport]} stats feed doesn't include {what}, so there are no numbers to show here."
            if what else "")


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
        v = GL._first(s, how[1:])
        return round(v / gp, 1) if v is not None and gp else None
    return GL.value(sport, how, s, gp)


def _rank_on(spec: tuple, s: dict, gp: int, sport: str):
    """The number a headline is ranked on (innings are ranked on outs)."""
    if spec[3][0] == "ip":
        return s.get("outs")
    return head_value(sport, spec, s, gp)


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


def rank_table(conn, sport: str, season: int, kind: str, db_path=None) -> dict:
    """{headline key: {player: place}} for one season and one kind of player.
    Kept, and rebuilt in the background once RANK_TTL old while the old one
    answers; built here only the first time (`warm` builds them at start)."""
    key = (sport, int(season), kind)
    hit = _RANKS.get(key)
    if hit:
        if time.time() - hit[0] >= RANK_TTL:
            _refresh_later(key, db_path)
        return hit[1]
    table = _build_table(conn, sport, int(season), kind)
    _RANKS[key] = (time.time(), table)
    return table


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
        finally:
            conn.close()
    except Exception as exc:                              # noqa: BLE001 — the old table keeps answering
        if not _RANK_FAIL_SAID:
            _RANK_FAIL_SAID = True
            print(f"⚠️  player page ranks not rebuilt for {key} ({type(exc).__name__}: {exc}): "
                  "the pages show the table built before", file=sys.stderr)
    finally:
        _REFRESHING.discard(key)


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
                    if key in _RANKS:
                        continue
                    try:
                        _RANKS[key] = (time.time(), _build_table(conn, *key))
                    except Exception:                     # noqa: BLE001 — that table is built on first ask
                        continue
        finally:
            conn.close()
    t = threading.Thread(target=run, name="playerpage-warm", daemon=True)
    t.start()
    return t


def _build_table(conn, sport: str, season: int, kind: str) -> dict:
    specs = HEAD.get(kind) or ()
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
    from .playersearch import norm
    want = norm(player)
    if not want:
        return {}
    hits = []
    for club, entry in ((_roster_doc(sport, data_dir).get("teams") or {}).items()):
        rows = (entry.get("players") if isinstance(entry, dict) else entry) or []
        for r in rows:
            if isinstance(r, dict) and norm(r.get("player") or "") == want:
                hits.append(dict(r, team=r.get("team") or club))
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


def bio(sport: str, player: str, row: dict, position: str = "") -> dict:
    """The facts a roster publishes, as it publishes them (blank is unknown)."""
    pick = lambda k: row.get(k) if row.get(k) not in (None, "") else ""        # noqa: E731
    return {"team": pick("team"), "number": "" if pick("number") == "" else str(row["number"]),
            "position": pick("position") or position, "height": pick("height"), "weight": pick("weight"),
            "age": pick("age"), "born": pick("born"),
            "birthplace": _birthplace(sport, row, player, pick("position") or position),
            "college": pick("college"), "years_exp": pick("years_exp"), "rookie": bool(row.get("rookie")),
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
    if kind == "sum":
        v = GL._first(s, how[1:])
        return None if v is None else round(v / gp, 1)
    if kind == "made":
        made, tried = s.get(how[1]), s.get(how[2])
        return None if made is None or tried is None else f"{made / gp:.1f}-{tried / gp:.1f}"
    if kind == "ip":
        outs = s.get(how[1])
        if outs is None:
            return None
        o = int(round(outs / gp))
        return f"{o // 3}.{o % 3}"
    return GL.value(sport, how, s, gp)


def _line(sport: str, groups, s: dict, gp: int, per_game: bool) -> dict:
    return {f"{k}.{c[0]}": (averaged(sport, c[3], s, gp) if per_game else GL.value(sport, c[3], s, gp))
            for k, _, cols in groups for c in cols}


def _date_of(sport: str, g: dict, res: dict | None) -> str:
    if sport in GL.WEEKLY and not GL._ISO.match(g["period"]):
        return str((res or {}).get("date") or "")[:10]
    return g["period"][:10]


def _record(by_id: dict, team: str, through: str) -> str:
    """A club's wins and losses (and ties) in the season through one period."""
    w = l = t = 0
    for r in by_id.values():
        if team not in (r["home"], r["away"]) or r["hs"] is None or r["as"] is None or r["period"] > through:
            continue
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


def page(sport: str, player: str, team: str = "", season=None, db_path=None, data_dir=None) -> dict:
    """Everything his page's menus show; ``{}`` for a league with no layout or
    a name neither the history file nor a roster knows."""
    if sport not in GL.LAYOUTS or not player:
        return {}
    path = str(db_path or _db.DEFAULT_DB)
    rows: list = []
    seasons: list = []
    conn = _db.connect(path) if os.path.exists(path) else None
    try:
        if conn is not None:
            seasons = GL.seasons_of(conn, sport, player)
            if not seasons:
                from .statlogs import resolve_player
                found = resolve_player(conn, sport, player)
                if found and found != player:
                    player = found
                    seasons = GL.seasons_of(conn, sport, player)
            if seasons:
                rows = conn.execute(
                    "SELECT season, period, game_id, team, opponent, position, home, market, value "
                    "FROM player_game_logs WHERE sport=? AND player=?", (sport, player)).fetchall()
        by_season: dict = {}
        for yr, period, gid, club, opp, pos, home, market, val in rows:
            gs = by_season.setdefault(int(yr), {})
            g = gs.setdefault((str(period), str(gid)), {"period": str(period), "game_id": str(gid), "team": club,
                                                        "opponent": opp, "position": pos, "home": home,
                                                        "stats": {}})
            if val is not None:
                g["stats"][market] = float(val)
        by_season = {yr: {(g["period"], g["game_id"]): g for g in GL.collapse(sport, list(gs.values()))}
                     for yr, gs in by_season.items()}
        newest = max((g for gs in by_season.values() for g in gs.values()), key=lambda g: g["period"], default=None)
        my_team = team or ((newest or {}).get("team") or "")
        row = roster_row(sport, player, my_team, data_dir, position=(newest or {}).get("position") or "")
        position = str(row.get("position") or (newest or {}).get("position") or "")
        out = {"sport": sport, "player": player, "team": row.get("team") or my_team, "position": position,
               "bio": bio(sport, player, row, position), "notes": notes(sport, player, row, data_dir),
               "seasons": seasons}
        if not seasons:
            note = no_stats_note(sport, position)
            if note:
                out["no_stats"] = note
            return out if row else {}
        season = int(season) if season and str(season).isdigit() and int(season) in seasons else seasons[0]
        out["season"] = season
        by_id, by_pair = GL._results(conn, sport, season)
        games = []
        for g in by_season.get(season, {}).values():
            res = by_id.get(g["game_id"]) or by_pair.get((g["period"], frozenset((g["team"], g["opponent"]))))
            sat = not GL._played(sport, g["stats"])
            g = dict(g, home=(res["home"] == g["team"]) if res else bool(g["home"]), res=res,
                     date=_date_of(sport, g, res), played=not sat and GL.has_line(sport, g["stats"]),
                     pending=not sat and not GL.has_line(sport, g["stats"]))
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
        per_game = sport in HOOPS

        # The headline, with the league's places.
        places = rank_table(conn, sport, season, kind, db_path=path) if kind and conn is not None else {}
        out["headline"] = [{"key": sp[0], "label": sp[1], "title": sp[2],
                            "value": head_value(sport, sp, summed, gp),
                            "rank": (places.get(sp[0]) or {}).get(player) if sp[7] else None,
                            "per_game": sp[4], "low": sp[5]}
                           for sp in HEAD.get(kind, ())]

        # The newest game.
        if games:
            g = games[0]
            vals = {f"{k}.{c[0]}": GL.value(sport, c[3], g["stats"]) for k, _, cols in groups for c in cols}
            labels = {f"{k}.{c[0]}": (c[1], c[2]) for k, _, cols in groups for c in cols}
            last = {"date": g["date"], "opponent": g["opponent"] or "", "home": g["home"], "team": g["team"] or "",
                    "values": vals, "dnp": not g["played"] and not g["pending"], "pending": g["pending"],
                    "tiles": [{"id": t, "label": labels[t][0], "title": labels[t][1], "value": vals.get(t)}
                              for t in TILES.get(kind, ()) if t in labels and vals.get(t) is not None]}
            if sport in GL.WEEKLY and not GL._ISO.match(g["period"]):
                try:
                    last["week"] = int(g["period"])
                except ValueError:
                    pass
            if g.get("result"):
                last["result"], last["score"] = g["result"], g["score"]
                if sport not in NO_RECORDS:
                    last["record"] = _record(by_id, g["team"], g["period"])
                    last["opp_record"] = _record(by_id, g["opponent"], g["period"])
            out["last"] = last

        # The season's splits, a game's average at a time.
        split_rows = []

        def add(key, label, chosen):
            if chosen:
                split_rows.append({"key": key, "label": label, "gp": len(chosen),
                                   "values": _line(sport, groups, _sum(chosen), len(chosen), True)})
        add("season", "Season", played)
        if len(played) > 5:
            add("last5", "Last 5 games", played[:5])
        add("home", "Home", [g for g in played if g["home"]])
        add("away", "Away", [g for g in played if not g["home"]])
        add("wins", "Wins", [g for g in played if g.get("result") == "W"])
        add("losses", "Losses", [g for g in played if g.get("result") == "L"])
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
        out["splits"] = {"season": season, "groups": _shape(groups), "rows": split_rows}

        # Season by season.
        counts = lambda g: GL._played(sport, g["stats"]) and GL.has_line(sport, g["stats"])   # noqa: E731
        every = [g for gs in by_season.values() for g in gs.values() if counts(g)]
        cgroups = _groups(sport, every)
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
        out["career"] = {"groups": _shape(cgroups), "per_game": per_game, "rows": career_rows,
                         "total": {"gp": len(every), "values": _line(sport, cgroups, _sum(every), len(every),
                                                                     per_game)}}
        out["bio"].update({"first_season": min(seasons), "last_season": max(seasons), "games": len(every)})
        return out
    finally:
        if conn is not None:
            conn.close()
