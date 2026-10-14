"""Every throw a quarterback made, for the passing chart.

Ethan, 2026-10-13, on the list of charts the data could carry next ("Yes
do all of them and don't stop till they are all done"): the quarterback's
chart is the route chart turned round — not every pass thrown TO a
player, but every pass a passer threw: how far past the line it went, to
which third of the field, complete or not, the yards after the catch,
touchdowns and interceptions, and the sacks he took.

WHAT THE RECORD HAS. The NFL play-by-play (the nflverse file the carry
and route charts already read every night) carries, on every dropback:
the passer, the air yards and the third of the field, whether it was
caught and by whom, the yards, the yards after the catch, touchdowns,
interceptions, sacks and the yards lost, whether he was hit, and
nflfastR's completion probability for the throw (so completion % over
expected per throw, the CPOE a box score cannot give). Checked before a
line of this was written: Josh Allen's 2026 week 5 at the Rams reads 19
attempts, 12 completions, 210 yards, a touchdown, an interception and one
sack for 8 in the play-by-play — nflverse's weekly stats, to the yard.

* FTN's charting (engine/sources/ftn, 2022 on, this season included)
  adds per play: play action, a screen, out of the pocket, a throwaway,
  a ball that should have been intercepted, a blitz (five or more
  rushers) and a drop by the receiver.
* nflverse's Next Gen Stats passing file (the league's own tracking)
  adds per game: time to throw, completion % above expectation and
  aggressiveness (throws into a tight window), for passers past the
  league's minimum. Stored as published (`ngs_rows`), never estimated.

A SPIKE IS AN ATTEMPT. The box score counts a spiked ball as an
incomplete pass, so the chart does too — listed, never drawn as a throw.
A sack is no attempt; it is listed and counted on its own. Two-point
tries, plays wiped out by a penalty and scrambles (which are runs, on the
carry chart) are not here.

The fold (`NflPasses`) rides the nightly play-by-play read the carry and
route charts share; `charting_for` reads the FTN file the route chart
already caches. `chart` is what the page draws.
"""

from __future__ import annotations

from .carries import _clean, _clock, _flag, _fold, _int, _num
from .targets import DEPTHS, SIDES, _pid, _stream, _true, depth_of

#: Play-by-play columns the fold reads on top of `nflpbp.NEEDED` (which
#: carries week, posteam, defteam, play_type, yardline_100, air_yards,
#: complete_pass, yards_gained, pass_touchdown, receiver_player_name,
#: passer_player_name, qb_hit, sack, game_id and qtr).
PBP_COLS = ("play_id", "season", "season_type", "game_date", "home_team", "away_team",
            "passer_player_id", "receiver_player_id", "pass_location", "yards_after_catch",
            "passing_yards", "interception", "first_down_pass", "two_point_attempt", "down",
            "ydstogo", "quarter_seconds_remaining", "cp", "cpoe", "fumble_lost")
#: FTN's charting, kept on a throw as words.
FTN_WORDS = (("is_play_action", "play action"), ("is_screen_pass", "screen"),
             ("is_qb_out_of_pocket", "out of pocket"), ("is_throw_away", "throwaway"),
             ("is_interception_worthy", "should have been picked"), ("is_drop", "drop"))
#: Five or more rushers is the blitz every charting service counts (as
#: engine/sources/ftn.BLITZ_RUSHERS).
BLITZ_RUSHERS = 5
FTN_FIRST = 2022


class NflPasses:
    """A fold over one season's NFL play-by-play rows: every dropback that
    ended in a throw, a spike or a sack, kept.

    Regular season and playoffs both. A throw with no receiver named (a
    throwaway, a ball batted down) is an attempt all the same."""

    def __init__(self, season: int):
        self.season = int(season)
        self._rows: list[dict] = []

    def add(self, r: dict) -> None:
        ptype = r.get("play_type") or ""
        if ptype not in ("pass", "qb_spike") or _flag(r.get("two_point_attempt")):
            return
        if (_clean(r.get("season_type")) or "REG").upper() not in ("REG", "POST"):
            return
        pid = _clean(r.get("passer_player_id"))
        week = _int(r.get("week"))
        home_t, away_t = _clean(r.get("home_team")), _clean(r.get("away_team"))
        team = _clean(r.get("posteam"))
        if not pid or not week or not home_t or not away_t or not team:
            return
        sack = _flag(r.get("sack"))
        kind = "spike" if ptype == "qb_spike" else "sack" if sack else "pass"
        caught = kind == "pass" and _flag(r.get("complete_pass"))
        air = _num(r.get("air_yards")) if kind == "pass" else None
        if kind == "sack":
            yards = _num(r.get("yards_gained"), 0.0)
        else:
            yards = (_num(r.get("passing_yards")) if caught else 0.0)
            if yards is None:
                yards = _num(r.get("yards_gained"), 0.0)
        yac = _num(r.get("yards_after_catch")) if caught else None
        if caught and yac is None and air is not None:
            yac = yards - air
        cp = _num(r.get("cp")) if kind == "pass" else None
        self._rows.append({
            "sport": "nfl", "season": _int(r.get("season"), self.season) or self.season,
            "period": f"{week:03d}", "game_id": f"{away_t}@{home_t}", "play_id": _pid(r.get("play_id")),
            "nflverse_game": _clean(r.get("game_id")),
            "date": _clean(r.get("game_date")), "player_id": pid,
            "pbp_name": _clean(r.get("passer_player_name")),
            "team": team, "opponent": _clean(r.get("defteam")) or (away_t if team == home_t else home_t),
            "home": 1 if team == home_t else 0,
            "qtr": _int(r.get("qtr")), "clock": _clock(r.get("quarter_seconds_remaining")),
            "down": _int(r.get("down")), "distance": _int(r.get("ydstogo")),
            "yardline_100": _int(r.get("yardline_100")), "kind": kind,
            "air_yards": air, "side": SIDES.get(_clean(r.get("pass_location")).lower(), "") if kind == "pass" else "",
            "complete": 1 if caught else 0, "yards": float(yards), "yac": yac,
            "td": 1 if caught and _flag(r.get("pass_touchdown")) else 0,
            "interception": 1 if kind == "pass" and _flag(r.get("interception")) else 0,
            "first_down": 1 if caught and _flag(r.get("first_down_pass")) else 0,
            "receiver_id": _clean(r.get("receiver_player_id")) if kind == "pass" else "",
            "receiver_pbp": _clean(r.get("receiver_player_name")) if kind == "pass" else "",
            "hit": 1 if _flag(r.get("qb_hit")) or sack else 0,
            "fumble_lost": 1 if sack and _flag(r.get("fumble_lost")) else 0,
            "cp": round(cp, 4) if cp is not None else None,
        })

    def rows(self, names: dict | None = None, charting: dict | None = None) -> list[dict]:
        """The `passes` table's rows. ``names`` as `carries.nfl_names`
        (the passer and his receiver both); ``charting`` as `ftn_map`."""
        names, charting = names or {}, charting or {}
        out = []
        for t in self._rows:
            who = names.get(t["player_id"]) or {}
            to = names.get(t["receiver_id"]) or {}
            words = list(charting.get((t["nflverse_game"], t["play_id"])) or ())
            if t["kind"] != "pass":
                words = [w for w in words if w == "blitz"]
            elif t["complete"]:
                words = [w for w in words if w not in ("drop", "throwaway")]
            row = {k: v for k, v in t.items() if k not in ("pbp_name", "nflverse_game", "receiver_pbp")}
            row.update(player=who.get("name") or t["pbp_name"] or t["player_id"],
                       position=who.get("position") or "", jersey=who.get("jersey") or "",
                       receiver=(to.get("name") or t["receiver_pbp"]) if t["receiver_id"] or t["receiver_pbp"] else "",
                       charting=",".join(words))
            out.append(row)
        return out


# --- FTN's charting -----------------------------------------------------------
def ftn_map(rows) -> dict:
    """``{(nflverse game id, play id): (words …)}`` for the passing chart:
    `FTN_WORDS`, and "blitz" where five or more rushed."""
    out = {}
    for r in rows or []:
        words = [w for col, w in FTN_WORDS if _true(r.get(col))]
        rushers = _num(r.get("n_pass_rushers"))
        if rushers is not None and rushers >= BLITZ_RUSHERS:
            words.append("blitz")
        if words:
            out[(_clean(r.get("nflverse_game_id")), _pid(r.get("nflverse_play_id")))] = tuple(words)
    return out


def charting_for(season: int) -> dict:
    """FTN's words for one season's dropbacks, or {} before 2022 and when
    the file is not there — the same cached copy the route chart reads."""
    from .sources.fetch import DataUnavailable
    from .sources.ftn import BASE
    if int(season) < FTN_FIRST:
        return {}
    cols = ("nflverse_game_id", "nflverse_play_id", "n_pass_rushers") + tuple(c for c, _ in FTN_WORDS)
    try:
        return ftn_map(_stream(f"{BASE}/ftn_charting_{int(season)}.csv",
                               f"ftn_charting_{int(season)}.csv", 6 * 3600, cols))
    except DataUnavailable:
        return {}


# --- the league's passing tracking file ---------------------------------------
def ngs_rows(rows) -> list[dict]:
    """The `ngs_passing` table's rows, from nflverse's ``ngs_passing`` file
    as published: one per player-week (week 0 the season line), passers
    past the league's minimum."""
    out = []
    for r in rows or []:
        pid, season, week = _clean(r.get("player_gsis_id")), _int(r.get("season")), _int(r.get("week"))
        if not pid or season is None or week is None:
            continue
        out.append({
            "season": season, "week": week, "season_type": (_clean(r.get("season_type")) or "REG").upper(),
            "player_id": pid, "player": _clean(r.get("player_display_name")), "team": _clean(r.get("team_abbr")),
            "attempts": _int(r.get("attempts")), "completions": _int(r.get("completions")),
            "yards": _num(r.get("pass_yards")), "tds": _int(r.get("pass_touchdowns")),
            "ints": _int(r.get("interceptions")), "time_to_throw": _num(r.get("avg_time_to_throw")),
            "cpoe": _num(r.get("completion_percentage_above_expectation")),
            "aggressiveness": _num(r.get("aggressiveness")),
            "intended_air": _num(r.get("avg_intended_air_yards")),
            "completed_air": _num(r.get("avg_completed_air_yards")),
            "air_to_sticks": _num(r.get("avg_air_yards_to_sticks")),
            "max_air": _num(r.get("max_air_distance")),
        })
    return out


def fetch_ngs_passing(ttl: int = 6 * 3600) -> list[dict]:
    """Every season of the NGS passing file — the cached copy
    `engine.sources.ngs.fetch` already keeps, read with week 0 left in."""
    from .sources.fetch import fetch_csv
    from .sources.ngs import BASE
    return fetch_csv(f"{BASE}/ngs_passing.csv.gz", "ngs_passing.csv", ttl=ttl)


# --- keeping it current -------------------------------------------------------
def nfl_behind(conn, season: int, today) -> bool:
    """Is a finished NFL game newer than the newest throw on file? The
    carry chart's check (`carries.nfl_behind`), on this table."""
    from .carries import nfl_behind as _behind
    return _behind(conn, season, today, table="passes")


def missing_seasons(conn, seasons) -> list[int]:
    """The NFL seasons with no throws stored yet — the one-time backfill."""
    out = []
    for s in seasons:
        n = conn.execute("SELECT COUNT(*) FROM passes WHERE sport='nfl' AND season=?",
                         (int(s),)).fetchone()[0]
        if not n:
            out.append(int(s))
    return out


def backfill_nfl(conn, season: int) -> int:
    """One past NFL season's throws, with FTN's charting, read once.
    Returns rows written."""
    from . import db
    from .carries import nfl_names
    from .sources.nflpbp import load_pbp_rows
    fold = NflPasses(season)
    for r in load_pbp_rows(int(season), columns=PBP_COLS):
        fold.add(r)
    return db.upsert_passes(conn, fold.rows(nfl_names(int(season)), charting_for(int(season))))


# --- what the page draws ------------------------------------------------------
def resolve(conn, player: str) -> str:
    """The stored spelling of a passer's name in `passes`, or "" — exact
    first, then the carry chart's loose form when one stored name matches."""
    q = (player or "").strip()
    if not q:
        return ""
    row = conn.execute("SELECT player FROM passes WHERE sport='nfl' AND player=? LIMIT 1", (q,)).fetchone()
    if row:
        return row[0]
    want = _fold(q)
    hits = [p for (p,) in conn.execute("SELECT DISTINCT player FROM passes WHERE sport='nfl'")
            if _fold(p) == want] if want else []
    return hits[0] if len(hits) == 1 else ""


def _line(ts: list[dict]) -> dict:
    """A game's or a split's numbers, the box score's way: a spike is an
    attempt, a sack is not; CPOE over the throws nflfastR priced."""
    att = [t for t in ts if t["k"] in ("pass", "spike")]
    thrown = [t for t in ts if t["k"] == "pass"]
    cmp_ = [t for t in thrown if t["c"]]
    sacks = [t for t in ts if t["k"] == "sack"]
    air = [t["ay"] for t in thrown if t["ay"] is not None]
    priced = [t for t in thrown if t.get("cp") is not None and t["ay"] is not None]
    yards = sum(t["y"] for t in cmp_)
    deep = [t for t in thrown if (t["ay"] or 0) >= 20]
    n = len(att)
    # `n` is what the page weighs his charts by (js/carrychart.js `vol`):
    # a passer's attempts, as a back's carries.
    return {"n": n, "att": n, "cmp": len(cmp_), "yds": round(yards, 1),
            "td": sum(1 for t in thrown if t["td"]), "int": sum(1 for t in thrown if t["int"]),
            "sk": len(sacks), "sk_yds": round(sum(t["y"] for t in sacks), 1),
            "adot": round(sum(air) / len(air), 1) if air else None,
            "ypa": round(yards / n, 2) if n else None,
            "pct": round(len(cmp_) / n, 3) if n else None,
            "cpoe": round(sum((1.0 if t["c"] else 0.0) - t["cp"] for t in priced) / len(priced), 3)
            if priced else None,
            "first": sum(1 for t in thrown if t["fd"]),
            "long": max((t["y"] for t in cmp_), default=None),
            "yac": round(sum(t["yac"] or 0.0 for t in cmp_), 1),
            "deep": len(deep), "deep_cmp": sum(1 for t in deep if t["c"]),
            "hit": sum(1 for t in ts if t["hit"]),
            "pa": sum(1 for t in thrown if "play action" in t["fl"]),
            "blitz": sum(1 for t in ts if "blitz" in t["fl"]),
            "away": sum(1 for t in thrown if "throwaway" in t["fl"]),
            "risky": sum(1 for t in thrown if "should have been picked" in t["fl"])}


def chart(conn, player: str, season: int | None = None) -> dict:
    """Everything the passing chart draws for one quarterback-season.

    ``{player, sport, seasons, season, team, position, jersey,
    games: [{id, period, week, date, opp, home, team, line, ngs, throws}],
    season_line, by_zone, by_down, by_pressure, by_target, ngs}`` — games
    newest first, each throw ``{k, q, clk, dn, ds, yl, ay, s, c, y, yac,
    td, int, fd, to, hit, fum, fl, cp}`` in the order it happened. The
    season line's ``n`` (his attempts) is what a page weighs against his
    carries to know which chart is his. ``{}`` when he has no throws."""
    name = resolve(conn, player)
    if not name:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        "SELECT DISTINCT season FROM passes WHERE sport='nfl' AND player=? ORDER BY season DESC", (name,))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    cur = conn.execute("SELECT * FROM passes WHERE sport='nfl' AND player=? AND season=?", (name, pick))
    cols = [d[0] for d in cur.description]
    games: dict = {}
    for r in (dict(zip(cols, x)) for x in cur.fetchall()):
        g = games.setdefault((r["period"], r["game_id"]), {
            "id": r["game_id"], "period": r["period"], "date": r["date"] or "", "opp": r["opponent"] or "",
            "home": bool(r["home"]), "team": r["team"] or "", "pid": r["player_id"] or "", "throws": []})
        g["throws"].append({
            "_order": int(r["play_id"]) if str(r["play_id"] or "").isdigit() else 0,
            "k": r["kind"] or "pass", "q": r["qtr"], "clk": r["clock"] or "", "dn": r["down"],
            "ds": r["distance"], "yl": r["yardline_100"], "ay": r["air_yards"], "s": r["side"] or "",
            "c": bool(r["complete"]), "y": float(r["yards"] or 0.0), "yac": r["yac"],
            "td": bool(r["td"]), "int": bool(r["interception"]), "fd": bool(r["first_down"]),
            "to": r["receiver"] or "", "hit": bool(r["hit"]), "fum": bool(r["fumble_lost"]),
            "cp": r["cp"], "fl": [w for w in (r["charting"] or "").split(",") if w]})
    ngs = _ngs_passing(conn, pick, {g["pid"] for g in games.values() if g["pid"]})
    out_games, every = [], []
    for (period, _gid), g in sorted(games.items(), key=lambda kv: (kv[0][0], kv[1]["date"]), reverse=True):
        ts = sorted(g["throws"], key=lambda t: t["_order"])
        for t in ts:
            del t["_order"]
        every.extend(ts)
        week = _int(period)
        out_games.append({"id": g["id"], "period": period, "week": week, "date": g["date"], "opp": g["opp"],
                          "home": g["home"], "team": g["team"], "line": _line(ts), "ngs": ngs.get(week),
                          "throws": ts})
    from .carries import scoreboard
    scoreboard(conn, "nfl", pick, out_games)
    thrown = [t for t in every if t["k"] == "pass"]
    by_zone = []
    for key, label, _lo, _hi in DEPTHS:
        for side in ("L", "M", "R"):
            line = _line([t for t in thrown if t["s"] == side and depth_of(t["ay"]) == key])
            line.update(depth=key, depth_name=label, side=side)
            by_zone.append(line)
    by_down = [dict(_line([t for t in every if t["dn"] == d]), down=d)
               for d in (1, 2, 3, 4) if any(t["dn"] == d for t in every)]
    by_pressure = [dict(_line([t for t in every if not t["hit"]]), when="Kept clean"),
                   dict(_line([t for t in every if t["hit"]]), when="Hit or sacked")]
    if any("blitz" in t["fl"] for t in every):
        by_pressure += [dict(_line([t for t in every if "blitz" in t["fl"]]), when="Blitzed (5+ rushers)")]
    if any("play action" in t["fl"] for t in thrown):
        by_pressure += [dict(_line([t for t in every if "play action" in t["fl"]]), when="Play action")]
    to: dict = {}
    for t in thrown:
        if t["to"]:
            to.setdefault(t["to"], []).append(t)
    by_target = sorted(({"to": k, "tgt": len(v), "rec": sum(1 for t in v if t["c"]),
                         "yds": round(sum(t["y"] for t in v if t["c"]), 1),
                         "td": sum(1 for t in v if t["td"]), "int": sum(1 for t in v if t["int"])}
                        for k, v in to.items()), key=lambda x: (-x["tgt"], -x["yds"], x["to"]))[:8]
    latest = out_games[0] if out_games else {}
    meta = conn.execute("SELECT position, jersey FROM passes WHERE sport='nfl' AND player=? AND season=? "
                        "AND position != '' ORDER BY period DESC LIMIT 1", (name, pick)).fetchone()
    line = _line(every)
    return {"player": name, "sport": "nfl", "seasons": seasons, "season": pick,
            "team": latest.get("team", ""), "position": (meta[0] if meta else "") or "",
            "jersey": (meta[1] if meta else "") or "",
            "games": out_games, "season_line": line, "by_zone": by_zone, "by_down": by_down,
            "by_pressure": by_pressure, "by_target": by_target, "ngs": ngs.get(0) or {}}


def _ngs_passing(conn, season: int, ids: set) -> dict:
    """``{week: tracking numbers}`` for the passer's ids, regular season
    only, as the route chart reads its file."""
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    try:
        cur = conn.execute(f"SELECT * FROM ngs_passing WHERE season=? AND player_id IN ({marks}) "
                           f"AND season_type='REG'", (int(season), *sorted(ids)))
    except Exception:                                              # noqa: BLE001
        return {}
    cols = [d[0] for d in cur.description]
    out = {}
    for r in cur.fetchall():
        row = dict(zip(cols, r))
        out[int(row["week"])] = {k: row[k] for k in ("attempts", "time_to_throw", "cpoe", "aggressiveness",
                                                      "intended_air", "completed_air", "air_to_sticks")}
    return out
