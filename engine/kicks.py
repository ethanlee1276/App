"""Every kick a kicker tried, for the kicker chart (kind "kicks").

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list he
said yes to had an NFL kicker chart on it.

WHAT THE RECORD HAS. The NFL play-by-play (the nflverse file the carry,
route and passing charts already read every night) carries, on every
field goal and extra point: the kicker, the distance, made, missed or
blocked, the quarter and the clock, the score, and the game's roof,
surface, temperature and wind. It does NOT record which hash a kick came
from or where between the uprights it went, so the chart places each
kick by its distance only and says so.

A field goal's distance is the play-by-play's kick distance (the line of
scrimmage plus the snap and the end zone, 17 or 18 yards). An extra
point is listed with its result and counted in his points; it is not
drawn among the field goals. Two-point tries are not kicks, and a fake
(a run or a pass) is not one either. An extra point that never got off
(a bad snap) is listed as aborted and counted as an attempt not made,
the box score's way.

The fold (`NflKicks`) rides the nightly play-by-play read the other
football charts share; `chart` is what the page draws.
"""

from __future__ import annotations

from .carries import _clean, _clock, _flag, _fold, _int, _num
from .targets import _pid

#: Play-by-play columns the fold reads on top of `nflpbp.NEEDED` (which
#: carries week, posteam, defteam, play_type, yardline_100, game_id, qtr).
PBP_COLS = ("play_id", "season", "season_type", "game_date", "home_team", "away_team",
            "field_goal_attempt", "field_goal_result", "extra_point_attempt", "extra_point_result",
            "kick_distance", "kicker_player_id", "kicker_player_name", "score_differential",
            "quarter_seconds_remaining", "roof", "surface", "temp", "wind", "two_point_attempt")
#: The bands every kicking split is read in.
BANDS = ((0, 29, "u30", "Under 30"), (30, 39, "30s", "30–39"), (40, 49, "40s", "40–49"),
         (50, 99, "50", "50+"))
#: Wind a kicker feels, in miles an hour (the play-by-play's own unit).
WINDY = 10
#: Cold, in degrees Fahrenheit.
COLD = 40
#: A one-score game for a kicker: within three points either way.
CLOSE = 3
RESULTS = {"made": "made", "good": "made", "missed": "missed", "failed": "missed",
           "blocked": "blocked", "aborted": "aborted"}


def band(dist) -> str:
    if dist is None:
        return ""
    return next((k for lo, hi, k, _n in BANDS if lo <= dist <= hi), "50")


class NflKicks:
    """A fold over one season's NFL play-by-play rows: every field goal and
    extra point tried, regular season and playoffs."""

    def __init__(self, season: int):
        self.season = int(season)
        self._rows: list[dict] = []

    def add(self, r: dict) -> None:
        ptype = r.get("play_type") or ""
        fg = ptype == "field_goal" or _flag(r.get("field_goal_attempt"))
        xp = not fg and (ptype == "extra_point" or _flag(r.get("extra_point_attempt")))
        if not (fg or xp) or _flag(r.get("two_point_attempt")):
            return
        if (_clean(r.get("season_type")) or "REG").upper() not in ("REG", "POST"):
            return
        pid = _clean(r.get("kicker_player_id"))
        week = _int(r.get("week"))
        home_t, away_t = _clean(r.get("home_team")), _clean(r.get("away_team"))
        team = _clean(r.get("posteam"))
        result = RESULTS.get(_clean(r.get("field_goal_result" if fg else "extra_point_result")).lower())
        if not pid or not week or not home_t or not away_t or not team or not result:
            return
        dist = _int(r.get("kick_distance"))
        if dist is None and fg:
            yl = _int(r.get("yardline_100"))
            dist = yl + 17 if yl is not None else None
        self._rows.append({
            "sport": "nfl", "season": _int(r.get("season"), self.season) or self.season,
            "period": f"{week:03d}", "game_id": f"{away_t}@{home_t}", "play_id": _pid(r.get("play_id")),
            "date": _clean(r.get("game_date")), "player_id": pid,
            "pbp_name": _clean(r.get("kicker_player_name")),
            "team": team, "opponent": _clean(r.get("defteam")) or (away_t if team == home_t else home_t),
            "home": 1 if team == home_t else 0,
            "qtr": _int(r.get("qtr")), "clock": _clock(r.get("quarter_seconds_remaining")),
            "kind": "fg" if fg else "xp", "distance": dist, "result": result,
            "score_diff": _int(r.get("score_differential")),
            "roof": _clean(r.get("roof")).lower(), "surface": _clean(r.get("surface")).lower(),
            "temp": _num(r.get("temp")), "wind": _num(r.get("wind")),
        })

    def rows(self, names: dict | None = None) -> list[dict]:
        """The `kicks` table's rows, named as the site's own game logs name
        him (`carries.nfl_names`); without one the play-by-play's short
        name ("J.Tucker") stands."""
        names = names or {}
        out = []
        for k in self._rows:
            who = names.get(k["player_id"]) or {}
            row = {c: v for c, v in k.items() if c != "pbp_name"}
            row.update(player=who.get("name") or k["pbp_name"] or k["player_id"],
                       position=who.get("position") or "", jersey=who.get("jersey") or "")
            out.append(row)
        return out


# --- keeping it current -------------------------------------------------------
def nfl_behind(conn, season: int, today) -> bool:
    """Is a finished NFL game newer than the newest kick on file? The
    carry chart's check (`carries.nfl_behind`), on this table."""
    from .carries import nfl_behind as _behind
    return _behind(conn, season, today, table="kicks")


def missing_seasons(conn, seasons) -> list[int]:
    """The NFL seasons with no kicks stored yet — the one-time backfill."""
    return [int(s) for s in seasons
            if not conn.execute("SELECT 1 FROM kicks WHERE sport='nfl' AND season=? LIMIT 1",
                                (int(s),)).fetchone()]


def backfill_nfl(conn, season: int) -> int:
    """One past NFL season's kicks, read once. Returns rows written."""
    from . import db
    from .carries import nfl_names
    from .sources.nflpbp import load_pbp_rows
    fold = NflKicks(season)
    for r in load_pbp_rows(int(season), columns=PBP_COLS):
        fold.add(r)
    return db.upsert_kicks(conn, fold.rows(nfl_names(int(season))))


# --- what the page draws ------------------------------------------------------
def resolve(conn, player: str) -> str:
    """The stored spelling of a kicker's name in `kicks`, or ""."""
    q = (player or "").strip()
    if not q:
        return ""
    row = conn.execute("SELECT player FROM kicks WHERE sport='nfl' AND player=? LIMIT 1", (q,)).fetchone()
    if row:
        return row[0]
    want = _fold(q).replace(" ", "")
    hits = [p for (p,) in conn.execute("SELECT DISTINCT player FROM kicks WHERE sport='nfl'")
            if _fold(p).replace(" ", "") == want] if want else []
    return hits[0] if len(hits) == 1 else ""


def _rate(made: int, att: int):
    return round(made / att, 3) if att else None


def _line(ks: list[dict]) -> dict:
    """A game's or a split's numbers, the box score's way: a blocked or an
    aborted kick is an attempt not made."""
    fg = [k for k in ks if k["k"] == "fg"]
    xp = [k for k in ks if k["k"] == "xp"]
    fgm = [k for k in fg if k["r"] == "made"]
    xpm = sum(1 for k in xp if k["r"] == "made")
    long_ = max((k["d"] for k in fgm if k["d"] is not None), default=None)
    # `n` is what the page weighs his charts by (js/carrychart.js `vol`):
    # every kick he tried.
    return {"n": len(ks), "fga": len(fg), "fgm": len(fgm), "fg_pct": _rate(len(fgm), len(fg)),
            "xpa": len(xp), "xpm": xpm, "xp_pct": _rate(xpm, len(xp)),
            "pts": 3 * len(fgm) + xpm, "long": long_, "blocked": sum(1 for k in ks if k["r"] == "blocked"),
            "fg50": sum(1 for k in fgm if (k["d"] or 0) >= 50), "fga50": sum(1 for k in fg if (k["d"] or 0) >= 50)}


def _split(ks: list[dict], key, order) -> list:
    out = []
    for k, name in order:
        xs = [x for x in ks if x["k"] == "fg" and key(x) == k]
        if xs:
            made = sum(1 for x in xs if x["r"] == "made")
            out.append({"key": k, "name": name, "fga": len(xs), "fgm": made, "pct": _rate(made, len(xs))})
    return out


def _league(conn, season: int) -> dict:
    """Every kicker's field goals that season, by distance band: the
    league's rate beside his."""
    tally: dict = {}
    for dist, result in conn.execute(
            "SELECT distance, result FROM kicks WHERE sport='nfl' AND season=? AND kind='fg'", (int(season),)):
        t = tally.setdefault(band(dist), [0, 0])
        t[0] += result == "made"
        t[1] += 1
    return {k: _rate(m, a) for k, (m, a) in tally.items()}


def _outdoors(k) -> bool:
    return k["roof"] in ("outdoors", "open")


def chart(conn, player: str, season: int | None = None) -> dict:
    """Everything the kicker chart draws for one kicker-season:
    ``{player, sport, seasons, season, team, position, jersey, games:
    [{id, period, week, date, opp, home, team, line, kicks}], season_line,
    by_band, by_place, by_weather, by_moment, league}``, games newest
    first, each kick ``{k, d, r, q, clk, sd, roof, temp, wind}`` in the
    order he tried them. ``{}`` when he has no kicks."""
    name = resolve(conn, player)
    if not name:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        "SELECT DISTINCT season FROM kicks WHERE sport='nfl' AND player=? ORDER BY season DESC", (name,))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    cur = conn.execute("SELECT * FROM kicks WHERE sport='nfl' AND player=? AND season=?", (name, pick))
    cols = [d[0] for d in cur.description]
    games: dict = {}
    for r in (dict(zip(cols, x)) for x in cur.fetchall()):
        g = games.setdefault((r["period"], r["game_id"]), {
            "id": r["game_id"], "period": r["period"], "date": r["date"] or "", "opp": r["opponent"] or "",
            "home": bool(r["home"]), "team": r["team"] or "", "kicks": []})
        g["kicks"].append({
            "_order": int(r["play_id"]) if str(r["play_id"] or "").isdigit() else 0,
            "k": r["kind"], "d": r["distance"], "r": r["result"], "q": r["qtr"], "clk": r["clock"] or "",
            "sd": r["score_diff"], "roof": r["roof"] or "", "temp": r["temp"], "wind": r["wind"]})
    out_games, every = [], []
    for (period, _gid), g in sorted(games.items(), key=lambda kv: (kv[0][0], kv[1]["date"]), reverse=True):
        ks = sorted(g["kicks"], key=lambda k: k["_order"])
        for k in ks:
            del k["_order"]
        every.extend(ks)
        out_games.append({"id": g["id"], "period": period, "week": _int(period), "date": g["date"],
                          "opp": g["opp"], "home": g["home"], "team": g["team"], "line": _line(ks), "kicks": ks})
    league = _league(conn, pick)
    by_band = [dict(x, league=league.get(x["key"])) for x in
               _split(every, lambda k: band(k["d"]), [(k, n) for _lo, _hi, k, n in BANDS])]
    by_place = _split(every, lambda k: "out" if _outdoors(k) else "in" if k["roof"] else "",
                      [("in", "Indoors (a dome or a closed roof)"), ("out", "Outdoors")])
    by_weather = _split([k for k in every if _outdoors(k)],
                        lambda k: ("windy" if (k["wind"] or 0) >= WINDY else "calm") if k["wind"] is not None else "",
                        [("calm", f"Outdoors, under {WINDY} mph"), ("windy", f"Outdoors, {WINDY}+ mph wind")])
    by_weather += _split([k for k in every if _outdoors(k)],
                         lambda k: "cold" if k["temp"] is not None and k["temp"] < COLD else "",
                         [("cold", f"Outdoors, under {COLD}°F")])
    by_moment = _split(every, lambda k: "late" if (k["q"] or 0) >= 4 else "early",
                       [("early", "First three quarters"), ("late", "Fourth quarter and overtime")])
    by_moment += _split(every, lambda k: "close" if k["sd"] is not None and abs(k["sd"]) <= CLOSE else "",
                        [("close", f"Within {CLOSE} points either way")])
    latest = out_games[0] if out_games else {}
    meta = conn.execute("SELECT position, jersey FROM kicks WHERE sport='nfl' AND player=? AND season=? "
                        "AND position != '' ORDER BY period DESC LIMIT 1", (name, pick)).fetchone()
    return {"player": name, "sport": "nfl", "seasons": seasons, "season": pick,
            "team": latest.get("team", ""), "position": (meta[0] if meta else "") or "K",
            "jersey": (meta[1] if meta else "") or "", "games": out_games, "season_line": _line(every),
            "by_band": by_band, "by_place": by_place, "by_weather": by_weather, "by_moment": by_moment,
            "league": league}
