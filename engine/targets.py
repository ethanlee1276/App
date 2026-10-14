"""Every pass thrown to a player, for the route chart.

Ethan, 2026-10-13, with the NFL's Next Gen Stats route chart for Sam
LaPorta against the Cardinals on the screen: "We can add route charts for
wr and shit too. And if we don't have access too this info then we should
be able too make it. There should be enough data and tools we have access
too too make this for nfl".

WHAT THE PUBLIC RECORD HAS. The league's chart draws the path each route
took, from player tracking it does not publish. The play-by-play has, for
every target: how far past the line the ball was thrown (air yards) and to
which third of the field (left, middle, right), whether it was caught, the
yards after the catch, touchdowns and interceptions. Checked against the
screenshot before this was written: LaPorta's 2026 week 5 reads 5
targets, 5 catches, 88 yards, 44 after the catch and a touchdown — the
chart's own numbers. Two more free files add to it:

* nflverse's participation file names the ROUTE the league charted for
  the targeted receiver (13 kinds: go, slant, quick out, hitch/curl,
  in/dig, deep out, post, corner, shallow cross, screen, swing, wheel,
  angle), whether the defence was in man or zone and its shell (Cover 1,
  Cover 3 …), for 2016 through 2025. There is no 2026 file — nflverse
  answers 404 — so this season's targets carry no route.
* FTN's charting (engine/sources/ftn), this season included, says per
  play whether it was a screen or play action, whether the ball was
  contested, catchable or dropped, and whether the catch was one the
  receiver made on his own.

WE DO NOT GUESS THE ROUTE. Measured 2026-10-13 on 2025 (weeks 1-12 fit,
13-18 held out, 6,357 targets): the route most common for a target's
side, depth and the receiver's position is the route the league charted
43% of the time — 65% even where one route dominates its cell. Drawn as
his route it would be wrong more often than right. So a target with no
charted route is drawn as the THROW, from the pocket to where the ball
arrived, which the record does say; a charted one is drawn in its route's
shape, ending at the real catch point.

The fold (`NflTargets`) rides the nightly play-by-play read the carry
chart and the unit ratings already share; `routes_for` and `charting_for`
read the participation and FTN files the scan already caches. `chart` is
what the page draws.

COLLEGE (2026-10-13, Ethan: "Yes do all of them"). The college play file
(engine/sources/cfbstats) names who was thrown at on a catch, and since
2025 on most incompletions and interceptions too: 78% of 2025's
incompletions, 92% of 2026's, against 21-45% before. So `CfbTargets`
keeps every pass the file names for 2025 on — caught or not, the yards,
a touchdown, the down, the distance and the yards to the goal — and
nothing before 2025, where most misses are unnamed and a target chart
would be mostly catches. It records no air yards, no side of the field
and (its clock being often the drive's) no time, so a college target has
none of them, and the page draws college targets straight upfield in the
order they were thrown, as it draws college carries.
"""

from __future__ import annotations

import csv
import io

from .carries import _clean, _clock, _flag, _fold, _int, _num

#: Play-by-play columns the fold reads on top of `nflpbp.NEEDED` (which
#: carries week, posteam, defteam, play_type, yardline_100, air_yards,
#: complete_pass, pass_touchdown, receiver_player_name, game_id, qtr and
#: sack) and the carry fold's `carries.PBP_COLS`, which the nightly reads
#: beside these.
PBP_COLS = ("play_id", "season", "season_type", "game_date", "home_team", "away_team",
            "receiver_player_id", "pass_location", "yards_after_catch", "receiving_yards",
            "td_player_id", "interception", "first_down_pass", "two_point_attempt", "down",
            "ydstogo", "quarter_seconds_remaining")
SIDES = {"left": "L", "middle": "M", "right": "R"}
SIDE_NAMES = {"L": "Left", "M": "Middle", "R": "Right"}
#: Depth bands for the season view, by air yards.
DEPTHS = (("behind", "Behind the line", None, 0), ("short", "0-9 yards", 0, 10),
          ("mid", "10-19 yards", 10, 20), ("deep", "20+ yards", 20, None))
COVERAGE = {"MAN_COVERAGE": "man", "ZONE_COVERAGE": "zone"}
SHELLS = {"COVER_0": "Cover 0", "COVER_1": "Cover 1", "COVER_2": "Cover 2", "2_MAN": "2-Man",
          "COVER_3": "Cover 3", "COVER_4": "Cover 4", "COVER_6": "Cover 6", "COVER_9": "Cover 9"}
#: FTN's charting, kept on a target as words. "not catchable" only on a
#: miss: of 2026's charted completions, 15 of 2,753 read uncatchable.
FTN_WORDS = (("is_screen_pass", "screen"), ("is_play_action", "play action"),
             ("is_contested_ball", "contested"), ("is_drop", "drop"),
             ("is_created_reception", "created"))
PART_BASE = "https://github.com/nflverse/nflverse-data/releases/download/pbp_participation"
FTN_FIRST = 2022


def _pid(v) -> str:
    """A play id as all three files can agree on: "141", never "141.0"."""
    f = _num(v)
    return str(int(f)) if f is not None else ""


def _true(v) -> bool:
    return _clean(v).upper() == "TRUE"


class NflTargets:
    """A fold over one season's NFL play-by-play rows: every target, kept.

    A target is a pass with a receiver named — a completion, an
    incompletion or an interception. Sacks, two-point tries and throws with
    nobody named (a throwaway, a spike) are not targets. Regular season and
    playoffs both are."""

    def __init__(self, season: int):
        self.season = int(season)
        self._rows: list[dict] = []

    def add(self, r: dict) -> None:
        if (r.get("play_type") or "") != "pass" or _flag(r.get("two_point_attempt")) or _flag(r.get("sack")):
            return
        if (_clean(r.get("season_type")) or "REG").upper() not in ("REG", "POST"):
            return
        rid = _clean(r.get("receiver_player_id"))
        week = _int(r.get("week"))
        home_t, away_t = _clean(r.get("home_team")), _clean(r.get("away_team"))
        team = _clean(r.get("posteam"))
        if not rid or not week or not home_t or not away_t or not team:
            return
        caught = _flag(r.get("complete_pass"))
        scorer = _clean(r.get("td_player_id"))
        air = _num(r.get("air_yards"))
        yards = _num(r.get("receiving_yards"), 0.0) if caught else 0.0
        yac = _num(r.get("yards_after_catch")) if caught else None
        if caught and yac is None and air is not None:
            yac = yards - air
        self._rows.append({
            "sport": "nfl", "season": _int(r.get("season"), self.season) or self.season,
            "period": f"{week:03d}", "game_id": f"{away_t}@{home_t}", "play_id": _pid(r.get("play_id")),
            "nflverse_game": _clean(r.get("game_id")),
            "date": _clean(r.get("game_date")), "player_id": rid,
            "pbp_name": _clean(r.get("receiver_player_name")),
            "team": team, "opponent": _clean(r.get("defteam")) or (away_t if team == home_t else home_t),
            "home": 1 if team == home_t else 0,
            "qtr": _int(r.get("qtr")), "clock": _clock(r.get("quarter_seconds_remaining")),
            "down": _int(r.get("down")), "distance": _int(r.get("ydstogo")),
            "yardline_100": _int(r.get("yardline_100")),
            "air_yards": air, "side": SIDES.get(_clean(r.get("pass_location")).lower(), ""),
            "complete": 1 if caught else 0, "yac": yac, "yards": float(yards),
            "td": 1 if caught and _flag(r.get("pass_touchdown")) and (not scorer or scorer == rid) else 0,
            "interception": 1 if _flag(r.get("interception")) else 0,
            "first_down": 1 if caught and _flag(r.get("first_down_pass")) else 0,
        })

    def rows(self, names: dict | None = None, routes: dict | None = None,
             charting: dict | None = None) -> list[dict]:
        """The `targets` table's rows. ``names`` as `carries.nfl_names`;
        ``routes`` as `route_map` — the league's charted route, coverage
        and shell for the plays it charted, nothing for the rest;
        ``charting`` as `ftn_map`."""
        names, routes, charting = names or {}, routes or {}, charting or {}
        out = []
        for t in self._rows:
            who = names.get(t["player_id"]) or {}
            key = (t["nflverse_game"], t["play_id"])
            rt, cov, shell = routes.get(key) or ("", "", "")
            words = list(charting.get(key) or ())
            if "not catchable" in words and t["complete"]:
                words.remove("not catchable")
            if "drop" in words and t["complete"]:
                words.remove("drop")
            row = {k: v for k, v in t.items() if k not in ("pbp_name", "nflverse_game")}
            row.update(player=who.get("name") or t["pbp_name"] or t["player_id"],
                       position=who.get("position") or "", jersey=who.get("jersey") or "",
                       route=rt, coverage=cov, shell=shell, charting=",".join(words))
            out.append(row)
        return out


#: The first college season a target chart is drawn for: the play file
#: names the intended receiver on 78% of 2025's incompletions and 92% of
#: 2026's, against 21-45% before (cfbstats' module note).
CFB_FROM = 2025


class CfbTargets:
    """A fold over the college play file's rows: every pass thrown to a
    player the file names — a catch, or an incompletion or interception
    whose intended receiver it records — from `CFB_FROM` on.

    ``games`` and ``roster`` are what `ingest_cfb_player_history` hands
    `cfbstats.parse_player_stats`, so a target lands on the same team and
    under the same name as the player's game logs. Who caught a completion
    is resolved the way the logs resolve it (`cfbstats.split_pass`: the
    passer is whichever of the two names has more quarterback evidence in
    his team's season), so his catches here are his receptions there. A
    touchdown is the feed's `touchdown_player` naming either man on the
    play, or the geometry (a gain of exactly the distance to the goal) —
    the college carries' either-signal rule."""

    def __init__(self, season: int, games: dict, roster: dict | None = None):
        self.season = int(season)
        self.games = games or {}
        self.roster = roster or {}
        self._scores: dict = {}
        self._rows: list[dict] = []
        self._pending: list = []

    def add(self, r: dict) -> None:
        if self.season < CFB_FROM:
            return
        from .sources import cfbstats as CS
        gid = _clean(r.get("game_id"))
        game = self.games.get(gid)
        if not game:
            return
        side = CS._side_of(game, _clean(r.get("team")))
        if not side:
            return
        team, opponent, home = side
        by_team = self._scores.setdefault(team, {})
        for column in CS.QB_COLUMNS:
            qb = CS._name(r.get(column))
            if qb:
                by_team[qb] = by_team.get(qb, 0) + 1
        ytg = CS._ytg(r.get("yards_to_goal"))
        dist = _int(r.get("distance"))
        base = {"sport": "cfb", "season": self.season, "period": game.get("period") or "",
                "game_id": gid, "play_id": _clean(r.get("play_id")),
                "date": str(game.get("period") or "")[:10], "team": team, "opponent": opponent,
                "home": 1 if home else 0, "qtr": _int(r.get("period")), "clock": "",
                "down": _int(r.get("down")), "distance": dist,
                "yardline_100": None if ytg is None else int(round(ytg))}
        thrown = next((CS._name(r.get(c)) for c in CS.ATTEMPT_COLUMNS if CS._name(r.get(c))), "")
        if thrown:
            aimed = CS._name(r.get("target_player"))
            if aimed and aimed != thrown:
                self._rows.append(dict(base, feed_name=aimed, player_id=_clean(r.get("target_player_id")),
                                       complete=0, yards=0.0, td=0, first_down=0,
                                       interception=1 if CS._name(r.get("interception_thrown_player")) else 0))
            return
        comp, recv = CS._name(r.get("completion_player")), CS._name(r.get("reception_player"))
        if comp and recv:
            yards = CS._num(r.get("reception_yds")) or CS._num(r.get("completion_yds"))
            scorer = CS._name(r.get("touchdown_player"))
            td = (bool(scorer) and scorer in (comp, recv)) or CS.scored_geometrically(ytg, yards)
            ids = {comp: _clean(r.get("completion_player_id")), recv: _clean(r.get("reception_player_id"))}
            self._pending.append((team, comp, recv, ids, dict(
                base, complete=1, interception=0, yards=float(yards), td=1 if td else 0,
                first_down=1 if (td or (dist and yards >= dist)) else 0)))

    def rows(self, kept=None) -> list[dict]:
        """The `targets` table's rows, every college one resolved.

        ``kept`` is the games the college logs kept from the same read
        (`cfbstats.parse_player_stats` drops a week whose scoring plays
        the file lost, and a game it credited more touchdowns than its
        score holds): a game missing its plays draws a chart missing its
        catches, so only those games are kept here too."""
        from .sources import cfbstats as CS
        found = list(self._rows)
        for team, comp, recv, ids, row in self._pending:
            _passer, receiver = CS.split_pass(self._scores.get(team, {}), comp, recv)
            found.append(dict(row, feed_name=receiver, player_id=ids.get(receiver, "")))
        if kept is not None:
            found = [t for t in found if t["game_id"] in kept]
        out = []
        for t in found:
            who = self.roster.get(t["player_id"]) or {}
            row = {k: v for k, v in t.items() if k != "feed_name"}
            row.update(player=who.get("name") or t["feed_name"], position=who.get("position") or "",
                       jersey="", air_yards=None, side="", yac=None, route="", coverage="",
                       shell="", charting="")
            out.append(row)
        return out


# --- the league's route charting and FTN's ------------------------------------
def route_map(rows) -> dict:
    """``{(nflverse game id, play id): (route, "man"|"zone"|"", shell)}``
    from a season's participation rows — the route the league charted for
    the targeted receiver, as it wrote it ("QUICK OUT", "HITCH/CURL" …)."""
    out = {}
    for r in rows or []:
        rt = _clean(r.get("route")).upper()
        if not rt:
            continue
        key = (_clean(r.get("nflverse_game_id")), _pid(r.get("play_id")))
        out[key] = (rt, COVERAGE.get(_clean(r.get("defense_man_zone_type")).upper(), ""),
                    SHELLS.get(_clean(r.get("defense_coverage_type")).upper(), ""))
    return out


def ftn_map(rows) -> dict:
    """``{(nflverse game id, play id): (words …)}`` from FTN's charting
    rows (`FTN_WORDS`, plus "not catchable" where FTN charted the ball
    uncatchable)."""
    out = {}
    for r in rows or []:
        words = [w for col, w in FTN_WORDS if _true(r.get(col))]
        if _clean(r.get("is_catchable_ball")).upper() == "FALSE":
            words.append("not catchable")
        if words:
            out[(_clean(r.get("nflverse_game_id")), _pid(r.get("nflverse_play_id")))] = tuple(words)
    return out


def _stream(url: str, cache: str, ttl: int, cols: tuple):
    """A cached CSV's rows, only ``cols`` kept — the participation file is
    ~49 MB, and a list of every row as a full dict is what that costs."""
    from .sources.fetch import fetch_text
    text = fetch_text(url, cache, ttl=ttl, timeout=300)
    rdr = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(rdr, [])
    idx = {c: header.index(c) for c in cols if c in header}
    for row in rdr:
        try:
            yield {c: row[i] for c, i in idx.items()}
        except IndexError:
            continue


def routes_for(season: int) -> dict:
    """The league's charted routes for one season, or {} where nflverse has
    not published the participation file (2026, as of this writing). The
    same cached file `engine.sources.nflpart` reads, under its name."""
    from .sources.fetch import DataUnavailable
    cols = ("nflverse_game_id", "play_id", "route", "defense_man_zone_type", "defense_coverage_type")
    for url in (f"{PART_BASE}/pbp_participation_{int(season)}.csv",
                f"{PART_BASE}/pbp_participation_{int(season)}.csv.gz"):
        try:
            return route_map(_stream(url, f"pbp_participation_{int(season)}.csv", 6 * 24 * 3600, cols))
        except DataUnavailable:
            continue
    return {}


def charting_for(season: int) -> dict:
    """FTN's charting words for one season's plays, or {} before 2022 and
    when the file is not there — the cached copy `engine.sources.ftn`
    keeps, under its name."""
    from .sources.ftn import BASE
    from .sources.fetch import DataUnavailable
    if int(season) < FTN_FIRST:
        return {}
    cols = ("nflverse_game_id", "nflverse_play_id", "is_catchable_ball") + tuple(c for c, _ in FTN_WORDS)
    try:
        return ftn_map(_stream(f"{BASE}/ftn_charting_{int(season)}.csv",
                               f"ftn_charting_{int(season)}.csv", 6 * 3600, cols))
    except DataUnavailable:
        return {}


# --- the league's receiving tracking file -------------------------------------
def ngs_rows(rows) -> list[dict]:
    """The `ngs_receiving` table's rows, from nflverse's ``ngs_receiving``
    file as published: one per player-week (week 0 the season line),
    receivers and tight ends past the league's five-target minimum."""
    out = []
    for r in rows or []:
        pid, season, week = _clean(r.get("player_gsis_id")), _int(r.get("season")), _int(r.get("week"))
        if not pid or season is None or week is None:
            continue
        out.append({
            "season": season, "week": week, "season_type": (_clean(r.get("season_type")) or "REG").upper(),
            "player_id": pid, "player": _clean(r.get("player_display_name")), "team": _clean(r.get("team_abbr")),
            "targets": _int(r.get("targets")), "receptions": _int(r.get("receptions")),
            "yards": _num(r.get("yards")), "tds": _int(r.get("rec_touchdowns")),
            "separation": _num(r.get("avg_separation")), "cushion": _num(r.get("avg_cushion")),
            "intended_air": _num(r.get("avg_intended_air_yards")),
            "air_share": _num(r.get("percent_share_of_intended_air_yards")),
            "yac": _num(r.get("avg_yac")), "expected_yac": _num(r.get("avg_expected_yac")),
            "yac_over": _num(r.get("avg_yac_above_expectation")), "catch_pct": _num(r.get("catch_percentage")),
        })
    return out


def fetch_ngs_receiving(ttl: int = 6 * 3600) -> list[dict]:
    """Every season of the NGS receiving file — the cached copy
    `engine.sources.ngs.fetch` already keeps, read with week 0 left in."""
    from .sources.fetch import fetch_csv
    from .sources.ngs import BASE
    return fetch_csv(f"{BASE}/ngs_receiving.csv.gz", "ngs_receiving.csv", ttl=ttl)


# --- keeping it current -------------------------------------------------------
def nfl_behind(conn, season: int, today) -> bool:
    """Is a finished NFL game newer than the newest target on file? The
    carry chart's check (`carries.nfl_behind`), on this table."""
    from .carries import nfl_behind as _behind
    return _behind(conn, season, today, table="targets")


def missing_seasons(conn, seasons) -> list[int]:
    """The NFL seasons with no targets stored yet — the one-time backfill."""
    out = []
    for s in seasons:
        n = conn.execute("SELECT COUNT(*) FROM targets WHERE sport='nfl' AND season=?",
                         (int(s),)).fetchone()[0]
        if not n:
            out.append(int(s))
    return out


def backfill_nfl(conn, season: int) -> int:
    """One past NFL season's targets, with its charted routes and FTN's
    charting, read once. Returns rows written."""
    from . import db
    from .carries import nfl_names
    from .sources.nflpbp import load_pbp_rows
    fold = NflTargets(season)
    for r in load_pbp_rows(int(season), columns=PBP_COLS):
        fold.add(r)
    return db.upsert_targets(conn, fold.rows(nfl_names(int(season)), routes_for(int(season)),
                                             charting_for(int(season))))


# --- what the page draws ------------------------------------------------------
def resolve(conn, player: str, sport: str = "nfl") -> str:
    """The stored spelling of a player's name in `targets`, or "" — exact
    first, then the carry chart's loose form (accents, suffixes, case)
    when exactly one stored name matches it."""
    q = (player or "").strip()
    if not q:
        return ""
    row = conn.execute("SELECT player FROM targets WHERE sport=? AND player=? LIMIT 1", (sport, q)).fetchone()
    if row:
        return row[0]
    want = _fold(q)
    hits = [p for (p,) in conn.execute("SELECT DISTINCT player FROM targets WHERE sport=?", (sport,))
            if _fold(p) == want] if want else []
    return hits[0] if len(hits) == 1 else ""


def depth_of(air) -> str:
    """The `DEPTHS` band a throw's air yards fall in, or "" with none."""
    if air is None:
        return ""
    for key, _label, lo, hi in DEPTHS:
        if (lo is None or air >= lo) and (hi is None or air < hi):
            return key
    return ""


def _line(ts: list[dict]) -> dict:
    n = len(ts)
    rec = [t for t in ts if t["c"]]
    air = [t["ay"] for t in ts if t["ay"] is not None]
    yards = sum(t["y"] for t in rec)
    contested = [t for t in ts if "contested" in t["fl"]]
    return {"tgt": n, "rec": len(rec), "yds": round(yards, 1), "td": sum(1 for t in ts if t["td"]),
            "yac": round(sum(t["yac"] or 0.0 for t in rec), 1),
            "adot": round(sum(air) / len(air), 1) if air else None,
            "int": sum(1 for t in ts if t["int"]), "first": sum(1 for t in ts if t["fd"]),
            "long": max((t["y"] for t in rec), default=None),
            "catch": round(len(rec) / n, 3) if n else None,
            "ypt": round(yards / n, 2) if n else None,
            "drops": sum(1 for t in ts if "drop" in t["fl"]),
            "contested": len(contested), "contested_won": sum(1 for t in contested if t["c"])}


def chart(conn, player: str, season: int | None = None, sport: str = "nfl") -> dict:
    """Everything the route chart draws for one player-season.

    ``{player, sport, air, seasons, season, routes, team, position, jersey,
    games: [{id, period, week, date, opp, home, team, line, ngs, targets}],
    season_line, by_zone, by_route, by_cov, by_shell, by_down, by_field,
    ngs}`` — games newest first, each target ``{q, clk, dn, ds, yl, ay, s,
    c, yac, y, td, int, fd, rt, cov, sh, fl}``; ``routes`` says whether the
    league charted this season's routes; ``air`` whether the league's file
    records air yards and the side of the field (the NFL's does, the
    college one does not). ``{}`` when the player has no targets."""
    sport = (sport or "nfl").lower()
    name = resolve(conn, player, sport)
    if not name:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        "SELECT DISTINCT season FROM targets WHERE sport=? AND player=? ORDER BY season DESC", (sport, name))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    cur = conn.execute("SELECT * FROM targets WHERE sport=? AND player=? AND season=?", (sport, name, pick))
    cols = [d[0] for d in cur.description]
    games: dict = {}
    for r in (dict(zip(cols, x)) for x in cur.fetchall()):
        g = games.setdefault((r["period"], r["game_id"]), {
            "id": r["game_id"], "period": r["period"], "date": r["date"] or "", "opp": r["opponent"] or "",
            "home": bool(r["home"]), "team": r["team"] or "", "pid": r["player_id"] or "", "targets": []})
        g["targets"].append({
            "_order": int(r["play_id"]) if str(r["play_id"] or "").isdigit() else 0,
            "q": r["qtr"], "clk": r["clock"] or "", "dn": r["down"], "ds": r["distance"],
            "yl": r["yardline_100"], "ay": r["air_yards"], "s": r["side"] or "",
            "c": bool(r["complete"]), "yac": r["yac"], "y": float(r["yards"] or 0.0),
            "td": bool(r["td"]), "int": bool(r["interception"]), "fd": bool(r["first_down"]),
            "rt": r["route"] or "", "cov": r["coverage"] or "", "sh": r["shell"] or "",
            "fl": [w for w in (r["charting"] or "").split(",") if w]})
    ngs = (_ngs_receiving(conn, pick, {g["pid"] for g in games.values() if g["pid"]})
           if sport == "nfl" else {})
    out_games, every = [], []
    for (period, _gid), g in sorted(games.items(), key=lambda kv: (kv[0][0], kv[1]["date"]), reverse=True):
        ts = sorted(g["targets"], key=lambda t: t["_order"])
        for t in ts:
            del t["_order"]
        every.extend(ts)
        week = _int(period)
        out_games.append({"id": g["id"], "period": period, "week": week, "date": g["date"], "opp": g["opp"],
                          "home": g["home"], "team": g["team"], "line": _line(ts), "ngs": ngs.get(week),
                          "targets": ts})
    from .carries import scoreboard
    scoreboard(conn, sport, pick, out_games)
    by_zone = []
    for key, label, _lo, _hi in DEPTHS:
        for side in ("L", "M", "R"):
            line = _line([t for t in every if t["s"] == side and depth_of(t["ay"]) == key])
            line.update(depth=key, depth_name=label, side=side)
            by_zone.append(line)
    charted = [t for t in every if t["rt"]]
    by_route = []
    for rt in sorted({t["rt"] for t in charted}):
        line = _line([t for t in charted if t["rt"] == rt])
        line.update(route=rt, share=round(line["tgt"] / len(charted), 3))
        by_route.append(line)
    by_route.sort(key=lambda x: (-x["tgt"], x["route"]))
    by_cov = [dict(_line([t for t in charted if t["cov"] == cov]), coverage=cov)
              for cov in ("man", "zone") if any(t["cov"] == cov for t in charted)]
    by_shell = [dict(_line([t for t in charted if t["sh"] == sh]), shell=sh)
                for sh in SHELLS.values() if any(t["sh"] == sh for t in charted)]
    by_down = [dict(_line([t for t in every if t["dn"] == d]), down=d)
               for d in (1, 2, 3, 4) if any(t["dn"] == d for t in every)]
    # Where on the field he was thrown at — the carry chart's zones, by
    # yards to the goal: what the college file has when it has no depth.
    from .carries import ZONES
    by_field = [dict(_line([t for t in every if t["yl"] is not None and lo <= t["yl"] <= hi]),
                     zone=key, name=label)
                for key, label, lo, hi in ZONES
                if any(t["yl"] is not None and lo <= t["yl"] <= hi for t in every)]
    latest = out_games[0] if out_games else {}
    meta = conn.execute("SELECT position, jersey FROM targets WHERE sport=? AND player=? AND season=? "
                        "AND position != '' ORDER BY period DESC LIMIT 1", (sport, name, pick)).fetchone()
    return {"player": name, "sport": sport, "air": sport == "nfl", "seasons": seasons, "season": pick,
            "routes": bool(charted), "team": latest.get("team", ""),
            "position": (meta[0] if meta else "") or "", "jersey": (meta[1] if meta else "") or "",
            "games": out_games, "season_line": _line(every), "by_zone": by_zone, "by_route": by_route,
            "by_cov": by_cov, "by_shell": by_shell, "by_down": by_down, "by_field": by_field,
            "ngs": ngs.get(0) or {}}


def _ngs_receiving(conn, season: int, ids: set) -> dict:
    """``{week: tracking numbers}`` for the player's ids, regular season
    only — the season line's own scope, and the file numbers the Super
    Bowl week 23 where the play-by-play says 22."""
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    try:
        cur = conn.execute(f"SELECT * FROM ngs_receiving WHERE season=? AND player_id IN ({marks}) "
                           f"AND season_type='REG'", (int(season), *sorted(ids)))
    except Exception:                                              # noqa: BLE001
        return {}
    cols = [d[0] for d in cur.description]
    out = {}
    for r in cur.fetchall():
        row = dict(zip(cols, r))
        out[int(row["week"])] = {k: row[k] for k in ("targets", "receptions", "separation", "cushion",
                                                      "intended_air", "air_share", "yac_over", "catch_pct")}
    return out
