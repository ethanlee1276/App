"""Every run a player made, for the carry chart.

Ethan, 2026-10-13, with the NFL Next Gen Stats carry chart for Josh Allen
at the Rams on the screen: "one feature too add for nfl and CFB is a carry
chart exactly in the screenshot for every player ... Users should be able
too look at a Carry chart for past games and also just a kinda 'average'
carry chart showing where they run."

WHAT IS PUBLIC AND WHAT IS NOT. The lines on that chart are the ball
carrier's TRACKED path, from the league's player-tracking chips, and the
league does not publish the tracking. What the public play-by-play does
carry, on every NFL run, is the hole (nflfastR's ``run_location`` and
``run_gap``: left end, left tackle, left guard, middle, right guard, right
tackle, right end), the yards, where the play started, the down, whether
it was a scramble, whether it scored and whether the ball was lost.
Checked against the screenshot before a line of this was written: Allen's
2026 week 5 at the Rams reads 10 carries, 121 yards and 1 touchdown in
that file — the chart's own numbers — four off left end, three up the
middle, two through right guard and one off right end. So the page draws
each carry from the backfield, through the hole it hit, to where it
ended. The bend between is drawn, not tracked, and the page says so.

COLLEGE HAS NO HOLE. The college plays come from the file the college
player logs are already built from (cfbfastR-data ``player_stats``,
`engine.sources.cfbstats`): the runner, the yards, the field position,
the down and the quarter, and nothing about direction — no public
college feed records it. A college chart spreads the carries across the
field in the order they happened and says that is what it is doing.

RUSHING YARDS OVER EXPECTED is the league's own tracking number, and it
IS published — per player-week, in nflverse's ``ngs_rushing`` file — for
running backs with ten or more carries in a game (measured 2026-10-13:
every 2026 row is an RB, the smallest weekly row is 10 attempts). Stored
as the file has it (`ngs_rows`), shown where a row exists, absent where
the league did not publish one. Never estimated.

The parsers (`NflCarries`, `CfbCarries`) are folds over the rows the
nightly already streams — the NFL play-by-play read in
`engine.maintenance` and the college play file read in
`engine.ingest.ingest_cfb_player_history` — so the chart costs no new
download. `chart` turns the stored rows into what the page draws.
"""

from __future__ import annotations

import math
import re
import unicodedata

#: The seven holes, left to right as the offence sees the field.
HOLES = ("LE", "LT", "LG", "M", "RG", "RT", "RE")
HOLE_NAMES = {"LE": "Left end", "LT": "Left tackle", "LG": "Left guard", "M": "Middle",
              "RG": "Right guard", "RT": "Right tackle", "RE": "Right end"}

#: Play-by-play columns the NFL fold reads on top of `nflpbp.NEEDED`
#: (which already carries week, posteam, defteam, play_type, yardline_100,
#: yards_gained, rush_touchdown, rusher_player_name, game_id, qtr).
PBP_COLS = ("play_id", "season", "season_type", "game_date", "home_team", "away_team",
            "run_location", "run_gap", "rusher_player_id", "rushing_yards", "qb_scramble",
            "two_point_attempt", "fumble_lost", "fumbled_1_player_id", "first_down_rush",
            "down", "ydstogo", "quarter_seconds_remaining")

#: The chart's three colours, by gain: tackled for a loss, 0-4 yards, 5 or
#: more (a touchdown is a gain whatever its length) — the NGS legend's
#: "tackled for loss / 0-5 yds gained / 5+ yds gained/TD".
GAIN_AT = 5
#: A carry of this many yards or more is a big play.
EXPLOSIVE = 10
#: Field zones by yards to the end zone, nearest last.
ZONES = (("own", "Own half", 51, 100), ("mid", "Their 50 to the 21", 21, 50),
         ("rz", "Red zone (20 to 6)", 6, 20), ("gl", "Goal line (5 and in)", 1, 5))

_BLANK = ("", "NA", "NULL", "None", "nan")


def _clean(v) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s in _BLANK else s


def _num(v, default=None):
    s = _clean(v)
    if not s:
        return default
    try:
        f = float(s)
    except ValueError:
        return default
    return f if math.isfinite(f) else default


def _int(v, default=None):
    f = _num(v)
    return default if f is None else int(f)


def _flag(v) -> bool:
    return _num(v, 0.0) == 1.0


def hole_of(location, gap) -> str:
    """The hole a run hit, from the play-by-play's two columns, or "".

    ``middle`` carries no gap; a left or right run with no gap recorded is
    left blank rather than guessed into a lane it may not have used."""
    loc = _clean(location).lower()
    gp = _clean(gap).lower()
    if loc == "middle":
        return "M"
    if loc in ("left", "right") and gp in ("end", "tackle", "guard"):
        return loc[0].upper() + gp[0].upper()
    return ""


def _clock(seconds) -> str:
    s = _int(seconds)
    if s is None or s < 0:
        return ""
    return f"{s // 60}:{s % 60:02d}"


class NflCarries:
    """A fold over one season's NFL play-by-play rows: every run, kept.

    Two-point tries are not carries (no rushing attempt is credited), and
    a kneel-down is its own play type in nflfastR, so neither reaches the
    chart. Regular season and playoffs both do."""

    def __init__(self, season: int):
        self.season = int(season)
        self._rows: list[dict] = []

    def add(self, r: dict) -> None:
        if (r.get("play_type") or "") != "run" or _flag(r.get("two_point_attempt")):
            return
        if (_clean(r.get("season_type")) or "REG").upper() not in ("REG", "POST"):
            return
        pid = _clean(r.get("rusher_player_id"))
        week = _int(r.get("week"))
        home_t, away_t = _clean(r.get("home_team")), _clean(r.get("away_team"))
        team = _clean(r.get("posteam"))
        if not pid or not week or not home_t or not away_t or not team:
            return
        yards = _num(r.get("rushing_yards"))
        if yards is None:
            yards = _num(r.get("yards_gained"), 0.0)
        fumbler = _clean(r.get("fumbled_1_player_id"))
        lost = _flag(r.get("fumble_lost")) and (not fumbler or fumbler == pid)
        self._rows.append({
            "sport": "nfl", "season": _int(r.get("season"), self.season) or self.season,
            "period": f"{week:03d}", "game_id": f"{away_t}@{home_t}",
            "play_id": _clean(r.get("play_id")),
            "date": _clean(r.get("game_date")), "player_id": pid,
            "pbp_name": _clean(r.get("rusher_player_name")),
            "team": team, "opponent": _clean(r.get("defteam")) or (away_t if team == home_t else home_t),
            "home": 1 if team == home_t else 0,
            "qtr": _int(r.get("qtr")), "clock": _clock(r.get("quarter_seconds_remaining")),
            "down": _int(r.get("down")), "distance": _int(r.get("ydstogo")),
            "yardline_100": _int(r.get("yardline_100")),
            "yards": float(yards), "hole": hole_of(r.get("run_location"), r.get("run_gap")),
            "scramble": 1 if _flag(r.get("qb_scramble")) else 0,
            "td": 1 if _flag(r.get("rush_touchdown")) else 0,
            "fumble": 1 if lost else 0, "fumble_lost": 1 if lost else 0,
            "first_down": 1 if _flag(r.get("first_down_rush")) else 0,
        })

    def rows(self, names: dict | None = None) -> list[dict]:
        """The `carries` table's rows. ``names`` maps the league's player id
        to ``{"name", "position", "jersey"}`` (`nfl_names`): the name the
        site's own game logs use, so the page's player finds his carries.
        Without one the play-by-play's short name ("J.Allen") stands."""
        names = names or {}
        out = []
        for c in self._rows:
            who = names.get(c["player_id"]) or {}
            row = {k: v for k, v in c.items() if k != "pbp_name"}
            row.update(player=who.get("name") or c["pbp_name"] or c["player_id"],
                       position=who.get("position") or "", jersey=who.get("jersey") or "")
            out.append(row)
        return out


def nfl_names(season: int, roster_rows=None, weekly_rows=None) -> dict:
    """``{gsis_id: {"name", "position", "jersey"}}`` for one season.

    The weekly stats' ``player_display_name`` wins: it is the spelling
    `player_game_logs` stores, which is the name the page asks for. The
    roster adds the jersey number and anybody the weekly file missed."""
    from .sources import nflverse as NV
    from .sources.fetch import DataUnavailable
    out: dict = {}
    if roster_rows is None:
        try:
            roster_rows = NV.load_rosters(season)
        except DataUnavailable:
            roster_rows = []
    for r in roster_rows or []:
        gid = _clean(r.get("gsis_id"))
        if gid:
            out[gid] = {"name": _clean(r.get("full_name")) or _clean(r.get("football_name")),
                        "position": _clean(r.get("position")),
                        "jersey": (_clean(r.get("jersey_number")) or "").split(".")[0]}
    if weekly_rows is None:
        try:
            weekly_rows = NV.load_weekly_stats(season)
        except DataUnavailable:
            weekly_rows = []
    for r in weekly_rows or []:
        pid = _clean(r.get("player_id"))
        name = _clean(r.get("player_display_name")) or _clean(r.get("player_name"))
        if pid and name:
            e = out.setdefault(pid, {})
            e["name"] = name
            if not e.get("position"):
                e["position"] = _clean(r.get("position"))
    return out


class CfbCarries:
    """A fold over the college play file's rows: every run, kept.

    ``games`` and ``roster`` are what `ingest_cfb_player_history` already
    hands `cfbstats.parse_player_stats`, so a carry lands on the same team
    key and under the same name as the player's game logs. A touchdown is
    the feed's own ``touchdown_player`` or the geometry (a gain of exactly
    the distance to the goal line), the same either-signal rule the
    college logs credit scores by. A fumble is the runner's, but the file
    does not say who recovered it, so a college carry says FUMBLED and
    never "lost"."""

    def __init__(self, season: int, games: dict, roster: dict | None = None):
        self.season = int(season)
        self.games = games or {}
        self.roster = roster or {}
        self._rows: list[dict] = []

    def add(self, r: dict) -> None:
        from .sources import cfbstats as CS
        rush = _clean(r.get("rush_player"))
        if not rush:
            return
        gid = _clean(r.get("game_id"))
        game = self.games.get(gid)
        if not game:
            return
        side = CS._side_of(game, _clean(r.get("team")))
        if not side:
            return
        team, opponent, home = side
        ytg = CS._ytg(r.get("yards_to_goal"))
        gain = CS._num(r.get("rush_yds"))
        scorer = _clean(r.get("touchdown_player"))
        td = (bool(scorer) and scorer == rush) or CS.scored_geometrically(ytg, gain)
        down, dist = _int(r.get("down")), _int(r.get("distance"))
        rid = _clean(r.get("rush_player_id"))
        self._rows.append({
            "sport": "cfb", "season": self.season, "period": game.get("period") or "",
            "game_id": gid, "play_id": _clean(r.get("play_id")),
            "date": str(game.get("period") or "")[:10], "player_id": rid, "feed_name": rush,
            "team": team, "opponent": opponent, "home": 1 if home else 0,
            # THE QUARTER, NOT THE CLOCK. The file's clock is often the
            # drive's, not the play's: of 8,006 drives in 2026 with three
            # or more runs, 1,648 carry one time on every run. A wrong time
            # beside a carry is worse than none.
            "qtr": _int(r.get("period")), "clock": "",
            "down": down, "distance": dist,
            "yardline_100": None if ytg is None else int(round(ytg)),
            "yards": float(gain), "hole": "", "scramble": 0, "td": 1 if td else 0,
            "fumble": 1 if _clean(r.get("fumble_player")) == rush else 0, "fumble_lost": None,
            "first_down": 1 if (td or (dist and gain >= dist)) else 0,
        })

    def rows(self) -> list[dict]:
        out = []
        for c in self._rows:
            who = self.roster.get(c["player_id"]) or {}
            row = {k: v for k, v in c.items() if k != "feed_name"}
            row.update(player=who.get("name") or c["feed_name"],
                       position=who.get("position") or "", jersey="")
            out.append(row)
        return out


def tap(rows, also):
    """Hand every row to ``also`` on its way through — one read, two folds."""
    for r in rows:
        also(r)
        yield r


def ngs_rows(rows) -> list[dict]:
    """The `ngs_rushing` table's rows, from nflverse's ``ngs_rushing`` file
    as it is published: one per player-week (week 0 is the season line),
    regular season and playoffs. Nothing here is computed but a rename."""
    out = []
    for r in rows or []:
        pid, season, week = _clean(r.get("player_gsis_id")), _int(r.get("season")), _int(r.get("week"))
        if not pid or season is None or week is None:
            continue
        out.append({
            "season": season, "week": week,
            "season_type": (_clean(r.get("season_type")) or "REG").upper(),
            "player_id": pid, "player": _clean(r.get("player_display_name")),
            "team": _clean(r.get("team_abbr")),
            "attempts": _int(r.get("rush_attempts")), "yards": _num(r.get("rush_yards")),
            "tds": _int(r.get("rush_touchdowns")), "expected_yards": _num(r.get("expected_rush_yards")),
            "ryoe": _num(r.get("rush_yards_over_expected")),
            "ryoe_per_att": _num(r.get("rush_yards_over_expected_per_att")),
            "eight_box": _num(r.get("percent_attempts_gte_eight_defenders")),
            "time_to_los": _num(r.get("avg_time_to_los")), "efficiency": _num(r.get("efficiency")),
        })
    return out


def fetch_ngs_rushing(ttl: int = 6 * 3600) -> list[dict]:
    """Every season of the NGS rushing file — the cached copy
    `engine.sources.ngs.fetch` already keeps, read with week 0 left in."""
    from .sources.fetch import fetch_csv
    from .sources.ngs import BASE
    return fetch_csv(f"{BASE}/ngs_rushing.csv.gz", "ngs_rushing.csv", ttl=ttl)


# --- keeping it current -------------------------------------------------------
def nfl_behind(conn, season: int, today) -> bool:
    """Is a finished NFL game newer than the newest carry on file?

    The nightly reads the play-by-play on Tuesdays for the unit ratings;
    a Thursday or Monday game's chart should not wait a week for that, so
    the read also runs while this is true. nflverse refreshes the file
    overnight and the fetch layer caches it for a day, so this costs one
    download a night at most and stops the night the file has the game."""
    try:
        last = conn.execute(
            "SELECT MAX(date) FROM games WHERE sport='nfl' AND season=? AND home_score IS NOT NULL "
            "AND date < ?", (int(season), today.isoformat())).fetchone()[0]
        have = conn.execute("SELECT MAX(date) FROM carries WHERE sport='nfl' AND season=?",
                            (int(season),)).fetchone()[0]
    except Exception:                                              # noqa: BLE001
        return False
    return bool(last) and (not have or str(have) < str(last))


def missing_seasons(conn, sport: str, seasons) -> list[int]:
    """The seasons with no carries stored yet — the one-time backfill."""
    out = []
    for s in seasons:
        n = conn.execute("SELECT COUNT(*) FROM carries WHERE sport=? AND season=?",
                         (sport, int(s))).fetchone()[0]
        if not n:
            out.append(int(s))
    return out


def backfill_nfl(conn, season: int) -> int:
    """One past NFL season's carries, read once. Returns rows written."""
    from . import db
    from .sources.nflpbp import load_pbp_rows
    fold = NflCarries(season)
    for r in load_pbp_rows(int(season), columns=PBP_COLS):
        fold.add(r)
    return db.upsert_carries(conn, fold.rows(nfl_names(int(season))))


def backfill_cfb(conn, season: int) -> int:
    """One past college season's carries, read once. Returns rows written."""
    from . import db
    from .ingest import cfb_games_for
    from .sources import cfbstats
    from .sources.fetch import DataUnavailable
    games = cfb_games_for(conn, int(season))
    if not games:
        return 0
    try:
        roster = cfbstats.fetch_rosters(int(season))
    except DataUnavailable:
        roster = {}
    fold = CfbCarries(int(season), games, roster)
    for r in cfbstats._stream(cfbstats.STATS_URL.format(season=int(season)),
                              f"cfb_player_stats_{int(season)}.csv", 86400 * 7):
        fold.add(r)
    return db.upsert_carries(conn, fold.rows())


# --- what the page draws ------------------------------------------------------
def _fold(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", s)
    return " ".join(s.split())


def resolve(conn, sport: str, player: str) -> str:
    """The stored spelling of a player's name in `carries`, or ""."""
    q = (player or "").strip()
    if not q:
        return ""
    row = conn.execute("SELECT player FROM carries WHERE sport=? AND player=? LIMIT 1",
                       (sport, q)).fetchone()
    if row:
        return row[0]
    want = _fold(q)
    if not want:
        return ""
    hits = [p for (p,) in conn.execute("SELECT DISTINCT player FROM carries WHERE sport=?", (sport,))
            if _fold(p) == want]
    return hits[0] if len(hits) == 1 else ""


def success(down, distance, yards, td) -> bool | None:
    """The standard success rule: 40% of the distance on first down, 60%
    on second, all of it on third and fourth; a touchdown always is.
    None when the down or the distance is not on the row."""
    if td:
        return True
    if not down or not distance or distance <= 0:
        return None
    return yards >= {1: 0.4, 2: 0.6}.get(int(down), 1.0) * distance


def _line(carries: list[dict]) -> dict:
    n = len(carries)
    yds = sum(c["y"] for c in carries)
    ok = [success(c.get("dn"), c.get("ds"), c["y"], c.get("td")) for c in carries]
    graded = [s for s in ok if s is not None]
    return {"n": n, "yds": round(yds, 1), "ypc": round(yds / n, 2) if n else None,
            "td": sum(1 for c in carries if c.get("td")),
            "long": max((c["y"] for c in carries), default=None),
            "first": sum(1 for c in carries if c.get("fd")),
            "success": round(sum(graded) / len(graded), 3) if graded else None,
            "stuffed": round(sum(1 for c in carries if c["y"] <= 0) / n, 3) if n else None,
            "explosive": sum(1 for c in carries if c["y"] >= EXPLOSIVE),
            "fum": sum(1 for c in carries if c.get("fl"))}


def _band(y: float, td) -> str:
    return "gain" if td or y >= GAIN_AT else "loss" if y < 0 else "short"


def chart(conn, sport: str, player: str, season: int | None = None) -> dict:
    """Everything the carry chart draws for one player-season.

    ``{player, sport, holes, seasons, season, team, position, jersey,
    games: [{id, period, date, opp, home, line, ryoe, carries: [...]}],
    season_line, by_hole, by_zone, by_down, kinds, bands, ngs}`` — games
    newest first, each carry ``{q, clk, dn, ds, yl, y, h, sc, td, fl, fd,
    band}``. ``{}`` when the player has no carries on file."""
    sport = (sport or "").lower()
    name = resolve(conn, sport, player)
    if not name:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        "SELECT DISTINCT season FROM carries WHERE sport=? AND player=? ORDER BY season DESC",
        (sport, name))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    cur = conn.execute(
        "SELECT * FROM carries WHERE sport=? AND player=? AND season=? ORDER BY period, game_id",
        (sport, name, pick))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    games: dict = {}
    for r in rows:
        g = games.setdefault((r["period"], r["game_id"]), {
            "id": r["game_id"], "period": r["period"], "date": r["date"] or "",
            "opp": r["opponent"] or "", "home": bool(r["home"]), "team": r["team"] or "",
            "pid": r["player_id"] or "", "carries": []})
        g["carries"].append({
            # The league's play id runs in game order. A college one is
            # eighteen digits, past what a float holds exactly.
            "_order": int(r["play_id"]) if str(r["play_id"] or "").isdigit() else 0,
            "q": r["qtr"], "clk": r["clock"] or "", "dn": r["down"], "ds": r["distance"],
            "yl": r["yardline_100"], "y": float(r["yards"] or 0.0), "h": r["hole"] or "",
            "sc": bool(r["scramble"]), "td": bool(r["td"]),
            "fl": bool(r["fumble"]), "fd": bool(r["first_down"])})
    ngs = _ngs_for(conn, sport, pick, {g["pid"] for g in games.values() if g["pid"]})
    out_games = []
    every: list[dict] = []
    for (period, _gid), g in sorted(games.items(), key=lambda kv: (kv[0][0], kv[1]["date"]), reverse=True):
        cs = sorted(g["carries"], key=lambda c: c.pop("_order"))
        for c in cs:
            c["band"] = _band(c["y"], c["td"])
        every.extend(cs)
        week = _int(period) if sport == "nfl" else None
        row = ngs.get(week) if week is not None else None
        out_games.append({"id": g["id"], "period": period, "week": week, "date": g["date"],
                          "opp": g["opp"], "home": g["home"], "team": g["team"],
                          "line": _line(cs), "ryoe": row and row.get("ryoe"),
                          "xyds": row and row.get("expected_yards"), "carries": cs})
    holes = sport == "nfl"
    by_hole = []
    if holes:
        known = [c for c in every if c["h"]]
        for h in HOLES:
            mine = [c for c in known if c["h"] == h]
            line = _line(mine)
            line.update(hole=h, name=HOLE_NAMES[h],
                        share=round(len(mine) / len(known), 3) if known else 0.0)
            by_hole.append(line)
    by_zone = []
    for key, label, lo, hi in ZONES:
        mine = [c for c in every if c["yl"] is not None and lo <= c["yl"] <= hi]
        line = _line(mine)
        line.update(zone=key, name=label)
        by_zone.append(line)
    by_down = []
    for d in (1, 2, 3, 4):
        mine = [c for c in every if c["dn"] == d]
        if mine:
            line = _line(mine)
            line.update(down=d)
            by_down.append(line)
    kinds = {}
    if holes and any(c["sc"] for c in every):
        kinds = {"designed": _line([c for c in every if not c["sc"]]),
                 "scramble": _line([c for c in every if c["sc"]])}
    latest = out_games[0] if out_games else {}
    meta = conn.execute(
        "SELECT position, jersey FROM carries WHERE sport=? AND player=? AND season=? "
        "AND position != '' ORDER BY period DESC LIMIT 1", (sport, name, pick)).fetchone()
    return {
        "player": name, "sport": sport, "holes": holes, "seasons": seasons, "season": pick,
        "team": latest.get("team", ""), "position": (meta[0] if meta else "") or "",
        "jersey": (meta[1] if meta else "") or "",
        "games": out_games, "season_line": _line(every),
        "bands": {b: sum(1 for c in every if c["band"] == b) for b in ("loss", "short", "gain")},
        "by_hole": by_hole, "by_zone": by_zone, "by_down": by_down, "kinds": kinds,
        "ngs": ngs.get(0) or {},
    }


def _ngs_for(conn, sport: str, season: int, ids: set) -> dict:
    """``{week: ngs row}`` for this player-season, week 0 the season line —
    regular season only, which is the season line's own scope. One id in
    practice; the league's own ids, never a name match."""
    if sport != "nfl" or not ids:
        return {}
    marks = ",".join("?" * len(ids))
    try:
        cur = conn.execute(
            f"SELECT * FROM ngs_rushing WHERE season=? AND player_id IN ({marks}) "
            f"AND season_type='REG'", (int(season), *sorted(ids)))
    except Exception:                                              # noqa: BLE001
        return {}
    cols = [d[0] for d in cur.description]
    out: dict = {}
    for r in cur.fetchall():
        row = dict(zip(cols, r))
        out[int(row["week"])] = {k: row[k] for k in ("attempts", "yards", "expected_yards", "ryoe",
                                                      "ryoe_per_att", "eight_box", "time_to_los")}
    return out
