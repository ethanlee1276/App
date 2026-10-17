"""Tonight's opponent beside his chart: the matchup view (kind "matchup").

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done". The seventh thing on the list he said yes to: "Matchup view.
Tonight's defense next to his chart: where they allow catches, which run
gaps, which shot zones, or the pitcher's zone against the hitter's hot
spots. This is context only."

ONE PICTURE IN EVERY LEAGUE (the same message: "All sports screens should
basically be identical"). His own chart's zones, a row each. On the left,
how much of the volume goes there; on the right, a rate there beside the
league's. Then one number, the FIT: the right-hand difference weighted by
the left-hand share, in the rate's own units.

  family   league  left: the volume           right: the rate, against the league's
  routes   nfl     his targets, depth x side  yards a target tonight's defence allows
                                              his position group there
  passes   nfl     his throws, depth x side   yards an attempt the defence allows
  carries  nfl     his carries by hole        yards a carry the defence allows
  runs     cfb     his carries by field zone  yards a carry the defence allows (the
  catches  cfb     his targets by field zone  college play file has no hole and no
                                              depth or side: field position is what
                                              it has)
  shots    nba     his shots by zone          the field-goal % the defence allows
  skater   nhl     his shots by distance      goals a shot on goal the opponent allows
  goalie   nhl     the opponent's shots on    the opponent's goals a shot on goal there
                   goal by distance
  hitter   mlb     tonight's starter's        his own slugging there, on the pitch that
                   pitches by zone (the       ended the plate appearance
                   staff's when none is named)
  pitcher  mlb     his pitches by zone        the opposing lineup's slugging there

Every opponent rate (and a hitter's own) is shrunk toward the league's by
a few dozen pseudo-plays, so a zone seen five times reads near the league
rather than at 0 or 20, and the raw count is shown beside it.

CONTEXT ONLY. Measured on the 2022-2025 NFL seasons (engine/scanfit,
MEASURED): where a defence allows yards by side, depth or run gap did not
improve the picks on their own. The other leagues' versions are not
measured. Nothing here moves a price, and the page says so.

`chart` answers one player against one opponent; league-wide sums are
kept in the process for a few hours (they change once a night).
"""

from __future__ import annotations

import threading
import time

#: Pseudo-plays an opponent's rate in a zone is shrunk toward the league's by.
SHRINK = {"routes": 25, "passes": 30, "carries": 25, "runs": 30, "catches": 25, "shots": 40,
          "skater": 30, "goalie": 30, "hitter": 30, "pitcher": 40}
#: About three games of the right-hand side; an opponent with less in the
#: newest season is read on the season before. A route chart's is three
#: games of one position group (a defence sees a tight end about seven
#: times a game).
MIN_N = {"routes": 20, "passes": 90, "carries": 60, "runs": 90, "catches": 60, "shots": 240,
         "skater": 75, "goalie": 75, "hitter": 100, "pitcher": 100}
#: League-wide sums are kept this long in one process.
TTL = 3 * 3600
_MEMO: dict = {}
_BUILDS: dict = {}
_BUILD_LOCK = threading.Lock()

#: What each family's two sides say, for the page.
SPEC = {
    "routes": {"left": "His targets", "right": "Yards a target allowed", "unit": "yds/target", "fmt": "yds",
               "good": 1, "tested": True},
    "passes": {"left": "His throws", "right": "Yards an attempt allowed", "unit": "yds/attempt", "fmt": "yds",
               "good": 1, "tested": True},
    "carries": {"left": "His carries", "right": "Yards a carry allowed", "unit": "yds/carry", "fmt": "yds",
                "good": 1, "tested": True},
    "runs": {"left": "His carries", "right": "Yards a carry allowed", "unit": "yds/carry", "fmt": "yds",
             "good": 1, "tested": False},
    "catches": {"left": "His targets", "right": "Yards a target allowed", "unit": "yds/target", "fmt": "yds",
                "good": 1, "tested": False},
    "shots": {"left": "His shots", "right": "FG% allowed", "unit": "FG%", "fmt": "pct", "good": 1,
              "tested": False},
    "skater": {"left": "His shots", "right": "Shooting % allowed", "unit": "shooting %", "fmt": "pct",
               "good": 1, "tested": False},
    "goalie": {"left": "Their shots", "right": "Their shooting %", "unit": "shooting %", "fmt": "pct",
               "good": -1, "tested": False},
    "hitter": {"left": "The pitches he will see", "right": "His slugging", "unit": "slugging", "fmt": "slg",
               "good": 1, "tested": False},
    "pitcher": {"left": "His pitches", "right": "Their slugging", "unit": "slugging", "fmt": "slg",
                "good": -1, "tested": False},
}

#: The chart a pick page asked for, onto the family that reads it.
HINT = {"routes": "routes", "passes": "passes", "carries": "carries", "shots": "shots",
        "shotmap": "skater", "saves": "goalie", "spray": "hitter", "pitches": "pitcher"}

# --- zones --------------------------------------------------------------------
SIDE_WORD = {"L": "left", "M": "middle", "R": "right"}
DEPTH_WORD = {"deep": "Deep (20+)", "mid": "10-19 yds", "short": "0-9 yds"}
PASS_ZONES = tuple((f"{d}{s}", f"{DEPTH_WORD[d]}, {SIDE_WORD[s]}") for d in ("deep", "mid", "short")
                   for s in "LMR") + (("behind", "Behind the line"),)
#: A route chart's position groups: a defence is read against his.
GROUP = {"WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB", "HB": "RB"}
#: The strike zone's nine boxes and the four outside it (catcher's view),
#: in six readable parts.
MLB_ZONES = (("heart", "Heart of the zone"), ("up", "Up in the zone"), ("edge", "Edges, in and away"),
             ("down", "Down in the zone"), ("chase_up", "Chase, up"), ("chase_down", "Chase, down"))
MLB_OF = {5: "heart", 1: "up", 2: "up", 3: "up", 4: "edge", 6: "edge", 7: "down", 8: "down", 9: "down",
          11: "chase_up", 12: "chase_up", 13: "chase_down", 14: "chase_down"}


def pass_zone(air, side) -> str:
    """A target's or a throw's zone: depth by air yards, and the side."""
    from .targets import depth_of
    d = depth_of(air)
    if d == "behind":
        return "behind"
    if not d or side not in SIDE_WORD:
        return ""
    return f"{d}{side}"


def field_zone(yl) -> str:
    from .carries import ZONES
    if yl is None:
        return ""
    return next((k for k, _n, lo, hi in ZONES if lo <= yl <= hi), "")


def _field_zones():
    from .carries import ZONES
    return tuple((k, n) for k, n, _lo, _hi in ZONES)


def _hole_zones():
    from .carries import HOLES, HOLE_NAMES
    return tuple((h, HOLE_NAMES[h]) for h in HOLES)


def _nba_zones():
    from .nba.shots import ZONES
    return ZONES


#: The shot map's distance bands, named short enough for a row.
NHL_NAMES = {"crease": "The crease", "slot": "The slot", "high": "High slot", "point": "The point"}


def _nhl_zones():
    from .nhl.charts import BANDS
    return tuple((k, NHL_NAMES.get(k, label)) for _lo, _hi, k, label in BANDS)


# --- reading -----------------------------------------------------------------
def _path(conn) -> str:
    try:
        return str(conn.execute("PRAGMA database_list").fetchone()[2] or "")
    except Exception:                                              # noqa: BLE001
        return ""


def _memo(conn, key, build):
    """A league-wide table, kept a few hours per database file (never for
    an in-memory one, which a test opens fresh each time).

    BUILT ONCE HOWEVER MANY ASK (2026-10-14). A cold baseball table is two
    joins over a season of pitches — two seconds on a full season here,
    more on the box — and every pick page opened in that window asked for
    its own copy. One request builds; the others wait for it and read the
    table it kept."""
    path = _path(conn)
    if not path:
        return build()
    k = (path,) + tuple(key)
    hit = _MEMO.get(k)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    with _BUILD_LOCK:
        lock = _BUILDS.setdefault(k, threading.Lock())
    with lock:
        hit = _MEMO.get(k)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
        val = build()
        _MEMO[k] = (time.time(), val)
        return val


def _add(table: dict, team, zone, n=1, tot=0.0):
    if not team or not zone:
        return
    a = table.setdefault(team, {}).setdefault(zone, [0, 0.0])
    a[0] += n
    a[1] += tot


def _latest(conn, sql, args=()) -> int | None:
    row = conn.execute(sql, args).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _routes(conn, season: int) -> dict:
    """``{group: {defence: {zone: [targets, yards]}}}``, all groups under ""."""
    def build():
        out: dict = {}
        for opp, pos, air, side, yards in conn.execute(
                "SELECT opponent, position, air_yards, side, yards FROM targets WHERE sport='nfl' AND season=?",
                (season,)):
            z = pass_zone(air, side)
            g = GROUP.get(str(pos or "").upper(), "")
            for key in ("", g) if g else ("",):
                _add(out.setdefault(key, {}), opp, z, 1, float(yards or 0.0))
        return out
    return _memo(conn, ("routes", season), build)


def _passes(conn, season: int) -> dict:
    def build():
        out: dict = {}
        for opp, air, side, yards in conn.execute(
                "SELECT opponent, air_yards, side, yards FROM passes WHERE sport='nfl' AND season=? AND kind='pass'",
                (season,)):
            _add(out, opp, pass_zone(air, side), 1, float(yards or 0.0))
        return out
    return _memo(conn, ("passes", season), build)


def _carries(conn, season: int) -> dict:
    def build():
        out: dict = {}
        for opp, hole, yards in conn.execute(
                "SELECT opponent, hole, yards FROM carries WHERE sport='nfl' AND season=? AND scramble=0 "
                "AND hole != ''", (season,)):
            _add(out, opp, hole, 1, float(yards or 0.0))
        return out
    return _memo(conn, ("carries", season), build)


def _field(conn, season: int, table: str) -> dict:
    def build():
        out: dict = {}
        for opp, yl, yards in conn.execute(
                f"SELECT opponent, yardline_100, yards FROM {table} WHERE sport='cfb' AND season=?", (season,)):
            _add(out, opp, field_zone(yl), 1, float(yards or 0.0))
        return out
    return _memo(conn, ("field", table, season), build)


def _nba(conn, season: int) -> dict:
    def build():
        out: dict = {}
        for opp, zone, n, made in conn.execute(
                "SELECT opponent, zone, COUNT(*), SUM(made) FROM nba_shots WHERE season=? "
                "AND kind IN ('2pt', '3pt') GROUP BY opponent, zone", (season,)):
            _add(out, opp, zone, n, float(made or 0))
        return out
    return _memo(conn, ("nba", season), build)


def _band_sql() -> str:
    from .nhl.charts import BANDS
    parts = " ".join(f"WHEN dist < {hi} THEN '{k}'" for _lo, hi, k, _n in BANDS[:-1])
    return f"CASE WHEN dist IS NULL THEN '' {parts} ELSE '{BANDS[-1][2]}' END"


def _nhl(conn, season: int, side: str) -> dict:
    """Shots on goal by the defending side (``opponent``: what a team
    allows) or the shooting side (``team``: what a team does)."""
    col = "opponent" if side == "against" else "team"

    def build():
        out: dict = {}
        for who, band, n, goals in conn.execute(
                f"SELECT {col}, {_band_sql()} AS band, COUNT(*), SUM(is_goal) FROM nhl_shots WHERE season=? "
                f"AND kind IN ('sog', 'goal') AND COALESCE(empty_net, 0)=0 GROUP BY {col}, band", (season,)):
            _add(out, who, band, n, float(goals or 0))
        return out
    return _memo(conn, ("nhl", side, season), build)


def _tb(event_type) -> tuple[int, int]:
    """(at bats, total bases) a plate appearance's result counts for."""
    from .mlb.charts import HIT_BASES, NOT_AB
    if event_type in NOT_AB:
        return 0, 0
    return 1, HIT_BASES.get(event_type, 0)


def _mlb(conn, season: int) -> dict:
    """``{"staff": {fielding team: {zone: [ab, tb]}}, "bats": {batting
    team: ...}, "pitches": {fielding team: {zone: [pitches, 0]}}}`` — the
    zone of the pitch that ended the plate appearance, and every pitch."""
    def build():
        staff: dict = {}
        bats: dict = {}
        for team, opp, zone, et in conn.execute(
                "SELECT a.team, a.opponent, p.zone, a.event_type FROM mlb_pa a JOIN mlb_pitches p "
                "ON p.game_pk = a.game_pk AND p.at_bat = a.at_bat AND p.n = a.pitches WHERE a.season=?",
                (season,)):
            z = MLB_OF.get(zone)
            ab, tb = _tb(et)
            if z and ab:
                _add(staff, opp, z, ab, float(tb))
                _add(bats, team, z, ab, float(tb))
        pitches: dict = {}
        for opp, zone, n in conn.execute(
                "SELECT a.opponent, p.zone, COUNT(*) FROM mlb_pitches p JOIN mlb_pa a "
                "ON a.game_pk = p.game_pk AND a.at_bat = p.at_bat WHERE a.season=? GROUP BY a.opponent, p.zone",
                (season,)):
            _add(pitches, opp, MLB_OF.get(zone), n, 0.0)
        return {"staff": staff, "bats": bats, "pitches": pitches}
    return _memo(conn, ("mlb", season), build)


# --- the opponent --------------------------------------------------------------
def _merge(table: dict, sport: str) -> dict:
    """One row per club, its old and other spellings folded in."""
    from .divisions import canonical
    if sport == "cfb":
        return table
    out: dict = {}
    for team, zones in table.items():
        t = out.setdefault(canonical(sport, team), {})
        for z, (n, tot) in zones.items():
            a = t.setdefault(z, [0, 0.0])
            a[0] += n
            a[1] += tot
    return out


def find(sport: str, teams, opp: str) -> str:
    """The key ``teams`` holds tonight's opponent under, or ""."""
    from .divisions import canonical
    if not opp:
        return ""
    if sport == "cfb":
        from .sources.cfbdata import name_key, resolve_team
        lookup = {name_key(t): t for t in teams}
        return resolve_team(opp, lookup) or ""
    want = canonical(sport, opp)
    return want if want in teams else ""


# --- the rows ------------------------------------------------------------------
def _rate(a):
    return a[1] / a[0] if a and a[0] else None


def _league(table: dict) -> dict:
    out: dict = {}
    for zones in table.values():
        for z, (n, tot) in zones.items():
            a = out.setdefault(z, [0, 0.0])
            a[0] += n
            a[1] += tot
    return out


def rows(order, left: dict, right: dict, league: dict, k: float) -> tuple[list, float | None, int]:
    """Each zone's row, the fit and the left-hand total. ``left`` counts
    by zone; ``right`` and ``league`` ``[n, total]`` by zone."""
    # Only the zones the league has a rate in: a share of a zone that is
    # never drawn would leave the drawn ones short of the whole.
    order = [(z, name) for z, name in order if _rate(league.get(z)) is not None]
    total = sum(left.get(z, 0) for z, _n in order)
    out, fit = [], 0.0
    for z, name in order:
        lg = _rate(league.get(z))
        r = right.get(z) or [0, 0.0]
        rate = (r[1] + k * lg) / (r[0] + k)
        share = left.get(z, 0) / total if total else 0.0
        diff = rate - lg
        fit += share * diff
        out.append({"key": z, "name": name, "n": int(left.get(z, 0)), "share": round(share, 3),
                    "rn": int(r[0]), "raw": round(_rate(r), 3) if r[0] else None,
                    "rate": round(rate, 3), "league": round(lg, 3), "diff": round(diff, 3)})
    return out, (round(fit, 3) if total else None), int(total)


def overall(table: dict, key: str, k: float, good: int) -> dict:
    """The opponent's rate over every zone beside the league's, and where
    it ranks: 1 is the best side of it for the player (the most a defence
    allows, or for a pitcher's or goalie's opponent the least it does)."""
    lg = _league(table)
    n = sum(a[0] for a in lg.values())
    if not n or key not in table:
        return {}
    base = sum(a[1] for a in lg.values()) / n
    rates = {}
    for team, zones in table.items():
        tn = sum(a[0] for a in zones.values())
        rates[team] = ((sum(a[1] for a in zones.values()) + k * base) / (tn + k), tn)
    order = sorted(rates, key=lambda t: -rates[t][0] * good)
    return {"rate": round(rates[key][0], 3), "league": round(base, 3), "n": int(rates[key][1]),
            "rank": order.index(key) + 1, "of": len(order)}


# --- each family ---------------------------------------------------------------
def _counts(pairs) -> dict:
    out: dict = {}
    for z, n in pairs:
        if z:
            out[z] = out.get(z, 0) + n
    return out


def _season_for(conn, sport: str, family: str, table_of, opp: str) -> tuple:
    """``(season, merged table, opponent key)``: the newest season, or the
    one before when tonight's opponent has too little in it yet."""
    newest = _newest(conn, sport, family)
    if newest is None:
        return None, {}, ""
    pick = None
    for s in (newest, newest - 1):
        t = _merge(table_of(s), sport)
        key = find(sport, t, opp)
        if key and sum(a[0] for a in t[key].values()) >= MIN_N[family]:
            return s, t, key
        if pick is None and key:
            pick = (s, t, key)
    return pick or (newest, _merge(table_of(newest), sport), "")


def _newest(conn, sport: str, family: str) -> int | None:
    sql = {"routes": "SELECT MAX(season) FROM targets WHERE sport='nfl'",
           "passes": "SELECT MAX(season) FROM passes WHERE sport='nfl'",
           "carries": "SELECT MAX(season) FROM carries WHERE sport='nfl'",
           "runs": "SELECT MAX(season) FROM carries WHERE sport='cfb'",
           "catches": "SELECT MAX(season) FROM targets WHERE sport='cfb'",
           "shots": "SELECT MAX(season) FROM nba_shots",
           "skater": "SELECT MAX(season) FROM nhl_shots", "goalie": "SELECT MAX(season) FROM nhl_shots",
           "hitter": "SELECT MAX(season) FROM mlb_pa", "pitcher": "SELECT MAX(season) FROM mlb_pa"}[family]
    try:
        return _latest(conn, sql)
    except Exception:                                              # noqa: BLE001 — a table not made yet
        return None


def _his(conn, sql: str, args, zone_of) -> tuple:
    """``(season, {zone: count})`` for his newest season in a table."""
    rows_ = conn.execute(sql, args).fetchall()
    if not rows_:
        return None, {}
    season = max(r[0] for r in rows_)
    return season, _counts((zone_of(*r[1:]), 1) for r in rows_ if r[0] == season)


def family_of(conn, sport: str, player: str, hint: str = "") -> tuple[str, str]:
    """``(family, his stored name)`` for this player, or ("", "")."""
    fam = HINT.get(hint, "")
    if sport == "nfl":
        from . import carries as C, passes as P, targets as T
        names = {"passes": P.resolve(conn, player), "routes": T.resolve(conn, player, "nfl"),
                 "carries": C.resolve(conn, "nfl", player)}
        vol = {}
        for f, (tbl, extra) in {"passes": ("passes", " AND kind='pass'"), "routes": ("targets", ""),
                                "carries": ("carries", " AND scramble=0")}.items():
            vol[f] = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE sport='nfl' AND player=?{extra}",
                                  (names[f],)).fetchone()[0] if names[f] else 0
        # His own chart leads, whatever the bet (a back's carries, a
        # receiver's targets), as on the pick page; a passer's throws count
        # three to one, so a quarterback who runs is still a passer.
        best = max(vol, key=lambda f: (vol[f] * (3 if f == "passes" else 1)))
        return (best, names[best]) if vol[best] else ("", "")
    if sport == "cfb":
        from . import carries as C, targets as T
        runs, catches = C.resolve(conn, "cfb", player), T.resolve(conn, player, "cfb")
        nr = conn.execute("SELECT COUNT(*) FROM carries WHERE sport='cfb' AND player=?", (runs,)).fetchone()[0] \
            if runs else 0
        nc = conn.execute("SELECT COUNT(*) FROM targets WHERE sport='cfb' AND player=?", (catches,)).fetchone()[0] \
            if catches else 0
        if not nr and not nc:
            return "", ""
        return ("runs", runs) if nr >= nc else ("catches", catches)
    if sport == "nba":
        from .nba.shots import resolve
        _pid, name = resolve(conn, player)
        return ("shots", name) if name else ("", "")
    if sport == "nhl":
        from .nhl.charts import _resolve
        if fam == "goalie" or not fam:
            g = _resolve(conn, player, "goalie")
            if g:
                return "goalie", g
        s = _resolve(conn, player, "shooter")
        return ("skater", s) if s else ("", "")
    if sport == "mlb":
        from .mlb.charts import _resolve
        role = "pitcher" if fam == "pitcher" else "batter"
        _pid, name = _resolve(conn, player, role)
        if not name and not fam:
            _pid, name = _resolve(conn, player, "pitcher")
            role = "pitcher"
        return (("pitcher" if role == "pitcher" else "hitter"), name) if name else ("", "")
    return "", ""


def _mlb_starter(team: str, opp: str) -> str:
    """Tonight's starter for the opponent, off the MLB board's games (its
    probable pitchers), or "" when the board names none."""
    from . import routes
    from .divisions import canonical
    want = canonical("mlb", opp)
    for g in (routes._board("mlb").get("games") or []):
        for side in ("home", "away"):
            if canonical("mlb", str(g.get(side) or "")) == want:
                return str(((g.get("pitchers") or {}).get(side) or {}).get("name") or "")
    return ""


#: How a hitter's matchup finds tonight's starter; a test hands its own.
STARTER = _mlb_starter


def chart(conn, sport: str, player: str, opp: str, season=None, hint: str = "") -> dict:
    """Everything the matchup view draws for one player against tonight's
    opponent: ``{player, sport, family, season, his_season, opp, left,
    right, unit, fmt, good, tested, zones: [{key, name, n, share, rn, raw,
    rate, league, diff, mine?}], fit, overall, season_line, games: []}``.
    ``{}`` without an opponent, or with nothing on file for either side."""
    try:
        fam, name = family_of(conn, sport, player, hint)
    except Exception:                                              # noqa: BLE001 — a table not made yet
        return {}
    if not fam or not opp:
        return {}
    k = SHRINK[fam]
    spec = dict(SPEC[fam])
    extra: dict = {}
    if fam in ("routes", "passes", "carries", "runs", "catches"):
        tbl, zones_, zone_of, cols = {
            "routes": ("targets", PASS_ZONES, pass_zone, "air_yards, side"),
            "passes": ("passes", PASS_ZONES, pass_zone, "air_yards, side"),
            "carries": ("carries", _hole_zones(), lambda h: h, "hole"),
            "runs": ("carries", _field_zones(), field_zone, "yardline_100"),
            "catches": ("targets", _field_zones(), field_zone, "yardline_100")}[fam]
        lg = "cfb" if fam in ("runs", "catches") else "nfl"
        cond = " AND kind='pass'" if fam == "passes" else " AND scramble=0" if fam == "carries" else ""
        his_season, left = _his(conn, f"SELECT season, {cols} FROM {tbl} WHERE sport=? AND player=?{cond}",
                                (lg, name), zone_of)
        if fam == "routes":
            pos = conn.execute("SELECT position FROM targets WHERE sport='nfl' AND player=? AND position != '' "
                               "ORDER BY season DESC, period DESC LIMIT 1", (name,)).fetchone()
            group = GROUP.get(str(pos[0] if pos else "").upper(), "")
            table_of = lambda s: (_routes(conn, s).get(group) or _routes(conn, s).get("") or {})  # noqa: E731
            extra["group"] = group
            if group:
                spec["right"] = f"Yards a target allowed to {group}s"
        else:
            table_of = {"passes": lambda s: _passes(conn, s), "carries": lambda s: _carries(conn, s),
                        "runs": lambda s: _field(conn, s, "carries"),
                        "catches": lambda s: _field(conn, s, "targets")}[fam]
        season_, table, key = _season_for(conn, lg, fam, table_of, opp)
        if not key or not left:
            return {}
        right = table[key]
        order = zones_
    elif fam == "shots":
        from .nba.shots import resolve, season_label
        pid, _n = resolve(conn, name)
        his_season, left = _his(conn, "SELECT season, zone FROM nba_shots WHERE person_id=? "
                                      "AND kind IN ('2pt', '3pt')", (pid,), lambda z: z)
        season_, table, key = _season_for(conn, "nba", fam, lambda s: _nba(conn, s), opp)
        if not key or not left:
            return {}
        right, order = table[key], _nba_zones()
        extra["season_label"] = season_label(season_)
    elif fam in ("skater", "goalie"):
        from .nhl.charts import band, season_label
        side = "against" if fam == "skater" else "for"
        season_, table, key = _season_for(conn, "nhl", fam, lambda s: _nhl(conn, s, side), opp)
        if not key:
            return {}
        right, order = table[key], _nhl_zones()
        extra["season_label"] = season_label(season_)
        if fam == "skater":
            his_season, left = _his(conn, "SELECT season, dist FROM nhl_shots WHERE shooter=? "
                                          "AND kind IN ('sog', 'goal', 'miss')", (name,), band)
            if not left:
                return {}
        else:
            # The left side is where tonight's opponent shoots from; his
            # own save percentage there rides along on each row.
            left = {z: a[0] for z, a in right.items()}
            mine: dict = {}
            his_season = None
            for s, dist, g in conn.execute(
                    "SELECT season, dist, is_goal FROM nhl_shots WHERE goalie=? AND kind IN ('sog', 'goal') "
                    "AND COALESCE(empty_net, 0)=0", (name,)):
                his_season = max(his_season or s, s)
                mine.setdefault(s, {}).setdefault(band(dist), [0, 0])
                mine[s][band(dist)][0] += 1
                mine[s][band(dist)][1] += int(g or 0)
            extra["mine"] = {z: round(1 - a[1] / a[0], 3) for z, a in (mine.get(his_season) or {}).items()
                             if a[0]}
    else:                                                          # mlb
        from .mlb.charts import _resolve
        role = "batter" if fam == "hitter" else "pitcher"
        pid, _n = _resolve(conn, name, role)
        season_, mtab, key = None, {}, ""
        newest = _newest(conn, "mlb", fam)
        part = "staff" if fam == "hitter" else "bats"
        for s in (newest, newest - 1) if newest is not None else ():
            t = {p: _merge(v, "mlb") for p, v in _mlb(conn, s).items()}
            kk = find("mlb", t[part], opp)
            if kk and sum(a[0] for a in t[part][kk].values()) >= MIN_N[fam]:
                season_, mtab, key = s, t, kk
                break
            if kk and not key:
                season_, mtab, key = s, t, kk
        if not key:
            return {}
        table, order = mtab[part], MLB_ZONES
        if fam == "pitcher":
            his_season, left = _his(conn, "SELECT season, zone FROM mlb_pitches WHERE pitcher_id=?", (pid,),
                                    lambda z: MLB_OF.get(z, ""))
            right = table[key]
        else:
            # His own slugging, zone by zone, on the pitch that ended each
            # plate appearance; the left side is where tonight's starter
            # (or, with none named, the staff) throws.
            his: dict = {}
            his_season = None
            for s, zone, et in conn.execute(
                    "SELECT a.season, p.zone, a.event_type FROM mlb_pa a JOIN mlb_pitches p "
                    "ON p.game_pk = a.game_pk AND p.at_bat = a.at_bat AND p.n = a.pitches WHERE a.batter_id=?",
                    (pid,)):
                his_season = max(his_season or s, s)
                ab, tb = _tb(et)
                if ab and MLB_OF.get(zone):
                    _add(his, s, MLB_OF[zone], ab, float(tb))
            right = his.get(his_season) or {}
            team = conn.execute("SELECT team FROM mlb_pa WHERE batter_id=? ORDER BY date DESC LIMIT 1",
                                (pid,)).fetchone()
            who = ""
            try:
                who = STARTER(team[0] if team else "", opp) or ""
            except Exception:                                      # noqa: BLE001 — no board on disk
                who = ""
            spid, sname = _resolve(conn, who, "pitcher") if who else (None, "")
            left = {}
            if spid is not None:
                left = _counts((MLB_OF.get(z, ""), n) for (z, n) in conn.execute(
                    "SELECT zone, COUNT(*) FROM mlb_pitches WHERE pitcher_id=? AND season=? GROUP BY zone",
                    (spid, season_)))
            if left:
                extra["starter"] = sname
                spec["left"] = f"Where {sname} pitches"
            else:
                left = {z: a[0] for z, a in (mtab["pitches"].get(key) or {}).items()}
                spec["left"] = "Where their staff pitches"
            if not right:
                return {}
    zones, fit, total = rows(order, left, right, _league(table), k)
    if not zones or not total:
        return {}
    if "mine" in extra:
        for z in zones:
            z["mine"] = extra["mine"].get(z["key"])
        extra.pop("mine")
    ov = overall(table, key, k, spec["good"]) if fam != "hitter" else overall(table, key, k, 1)
    return dict({"player": name, "sport": sport, "family": fam, "season": season_, "seasons": [season_],
                 "newest": _newest(conn, sport, fam), "his_season": his_season, "opp": key, "asked": opp,
                 "k": k, "zones": zones, "fit": fit,
                 "overall": ov, "season_line": {"n": total}, "games": []}, **spec, **extra)
