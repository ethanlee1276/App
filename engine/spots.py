"""Spots: the situations around a player's game, for the scout to flag.

Ethan, 2026-10-11, after the hometown flag: "what other things are there
like this we can track for players" — and, of the list (revenge game,
primetime, rest, travel and body clock, divisional rematch, contract year,
coach change, altitude and surface, late season, milestone chase): "all of
it".

Every spot here is a two-sided scout flag (engine/scout.SPOTS): the card
names it, the five-season replay (engine/scouthist) scores its overs and
its unders against the same side in every other game, and a side only moves
a pick once it clears the bar fixed there before any run (3% worse in both
halves, on 100+ games in each). Until then a spot is a line on the card —
"Spot: primetime" — never a caution and never a number.

WHAT EACH SPOT IS, written 2026-10-11 before anything was measured (the
repo's rule: never choose a setting because a backtest liked it):

  primetime       kickoff at PRIMETIME_ET (7pm Eastern) or later
  extra_rest      EXTRA_REST_DAYS+ days since his team's last game — a bye,
                  or the long week after a Thursday game (engine/fatigue's
                  "extra days" and "off a bye")
  long_trip       a road game TRIP_ZONES+ time zones from his team's home,
                  or a neutral site (in the NFL's regular season, abroad)
  body_clock      kickoff at BODY_CLOCK_EARLY (10am) or earlier by his
                  team's home clock — a West Coast team at 1pm Eastern
  div_rematch     the second meeting this season with a division rival
  new_coach       one of his team's first NEW_COACH_GAMES games under a head
                  coach — a new hire in the opener, or an interim mid-season
  altitude        a road game ALTITUDE_FT+ above sea level (Denver; Mexico
                  City)
  surface_switch  a road game on grass when his home field is turf, or turf
                  when it is grass (never at a neutral site, whose surface
                  the schedule does not reliably give)
  late_season     week LATE_FROM_WEEK on, for a team that has clinched its
                  division or is eliminated — engine/restwatch's
                  tiebreaker-free rules, from the finals before the game
  revenge         his first game against a team he played REVENGE_GAMES+
                  games for, since he left it
  contract_year   the last season of his deal (engine/contracts)
  milestone       the last MILESTONE_GAMES_LEFT games of the season, chasing
                  a round number (MILESTONES) he needs about his own pace to
                  reach: between MILESTONE_BAND of his per-game average times
                  the games left. Only in the milestone's own market.

WHERE IT COMES FROM: nflverse's schedule (games.csv, already cached for the
whole board) for the game spots — kickoff, rest, division, surface, venue,
coaches, finals; the player logs for revenge and milestones; the contracts
table for contract years; and data/nfl_staff_changes.json for a head coach
nflverse has not caught up with yet (it kept Arizona's 2025 coach on 2026's
rows).

Standard library only. No network: the schedule is read from the cache.
"""
from __future__ import annotations

import csv
import functools
from pathlib import Path

from .divisions import NFL as DIVISIONS

#: The thresholds, fixed 2026-10-11 before any measurement.
PRIMETIME_ET = 19.0
EXTRA_REST_DAYS = 9
TRIP_ZONES = 2
BODY_CLOCK_EARLY = 10.0
ALTITUDE_FT = 4000
NEW_COACH_GAMES = 4
REVENGE_GAMES = 8
LATE_FROM_WEEK = 15                  # engine/restwatch.RISK_FROM_WEEK
REGULAR_SEASON_GAMES = 17
MILESTONES = {"rec_yds": 1000, "rush_yds": 1000, "receptions": 100, "pass_yds": 4000,
              "pass_td": 30, "anytime_td": 10}
MILESTONE_GAMES_LEFT = 4
MILESTONE_BAND = (0.6, 1.4)
MILESTONE_MIN_PLAYED = 6
#: The card names a chase a little more widely than the flag fires: the
#: last six games, and anything he can reach at up to 1.5 times his pace.
MILESTONE_SHOW_LEFT = 6
MILESTONE_SHOW_REACH = 1.5
#: Neutral sites at altitude, by nflverse stadium id (Estadio Azteca).
VENUE_ALTITUDE = {"MEX00": 7350}
LABELS = {"rec_yds": "receiving yards", "rush_yds": "rushing yards", "receptions": "catches",
          "pass_yds": "passing yards", "pass_td": "touchdown passes", "anytime_td": "touchdowns"}


# --- the schedule ---------------------------------------------------------------------
def _int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def surface_kind(s) -> str | None:
    """"grass", "dessograss" and "grass " are grass; every turf brand is turf."""
    s = str(s or "").strip().lower()
    if not s:
        return None
    return "grass" if "grass" in s else "turf"


def parse_row(r: dict) -> dict | None:
    """One regular-season schedule row, cut to what the spots read."""
    if str(r.get("game_type") or "REG").upper() != "REG":
        return None
    season, week = _int(r.get("season")), _int(r.get("week"))
    home, away = str(r.get("home_team") or "").upper(), str(r.get("away_team") or "").upper()
    if not season or not week or not home or not away:
        return None
    return {"season": season, "week": week, "home": home, "away": away,
            "day": str(r.get("gameday") or "")[:10], "kickoff": str(r.get("gametime") or ""),
            "neutral": str(r.get("location") or "").lower() == "neutral",
            "rest": {home: _int(r.get("home_rest")), away: _int(r.get("away_rest"))},
            "coach": {home: str(r.get("home_coach") or "").strip(), away: str(r.get("away_coach") or "").strip()},
            "score": {home: _float(r.get("home_score")), away: _float(r.get("away_score"))},
            "div": str(r.get("div_game") or "") in ("1", "1.0", "TRUE", "true"),
            "surface": surface_kind(r.get("surface")), "stadium_id": str(r.get("stadium_id") or "")}


class Schedule:
    """The regular season, indexed the ways the spots look a game up."""

    def __init__(self, rows):
        self.rows = sorted((x for x in rows if x), key=lambda x: (x["season"], x["week"]))
        self.by_key = {(x["season"], x["week"], x["home"]): x for x in self.rows}
        self.by_team: dict = {}
        for x in self.rows:
            for t in (x["home"], x["away"]):
                self.by_team.setdefault(t, []).append(x)
        self._memo: dict = {}

    def game(self, season=None, week=None, home=None, away=None, day=None) -> dict | None:
        """By season, week and home team where they are known; else by the
        two teams and the date (the board's games carry a date, no week)."""
        home, away = str(home or "").upper(), str(away or "").upper()
        if season is not None and week is not None:
            g = self.by_key.get((_int(season), _int(week), home))
            # The away team must agree too: a fixture's id is not the game.
            if g and (not away or g["away"] == away):
                return g
        if not day:
            return None
        for x in self.by_team.get(home, []):
            if x["day"] == str(day)[:10] and (not away or away in (x["home"], x["away"])):
                return x
        return None

    def before(self, team: str, g: dict, season_only: bool = True) -> list:
        """His team's games before this one (this season only, by default)."""
        return [x for x in self.by_team.get(team, [])
                if (x["season"], x["week"]) < (g["season"], g["week"])
                and (not season_only or x["season"] == g["season"])]


_SCHED: dict = {}


def load_schedule(path=None) -> Schedule:
    """nflverse's games.csv from the cache, read once per change of the file
    (an empty schedule when there is none — the spots then say nothing)."""
    from .sources.fetch import CACHE_DIR
    p = Path(path) if path else Path(CACHE_DIR) / "games.csv"
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        return Schedule([])
    if _SCHED.get("stamp") != stamp:
        try:
            with open(p, newline="", encoding="utf-8") as fh:
                rows = [parse_row(r) for r in csv.DictReader(fh)]
        except (OSError, ValueError):
            rows = []
        _SCHED["stamp"], _SCHED["sched"] = stamp, Schedule(rows)
    return _SCHED["sched"]


# --- the game's spots, for one team -----------------------------------------------------
def _clock(hour: float) -> str:
    from .fatigue import clock_str
    h = int(hour)
    suffix = "pm" if 12 <= h % 24 < 24 else "am"
    return f"{clock_str((h % 12 or 12) + (hour - h))}{suffix}"


def _home_surface(sched: Schedule, team: str, season: int) -> str | None:
    """His home field's surface that season: what its own home games were
    played on, else the stadium table's."""
    kinds = [x["surface"] for x in sched.by_team.get(team, [])
             if x["season"] == season and x["home"] == team and not x["neutral"] and x["surface"]]
    if kinds:
        return max(set(kinds), key=kinds.count)
    from .stadiums import STADIUMS
    st = STADIUMS.get(team)
    return st.surface if st else None


def _coach(sched: Schedule, x: dict, team: str, staff: dict | None) -> str:
    """The head coach on a schedule row — the staff file's new hire where
    nflverse still carries last season's man."""
    c = x["coach"].get(team) or ""
    hire = ((staff or {}).get(x["season"]) or {}).get(team, {}).get("hc")
    if hire and c != hire:
        last = [y for y in sched.by_team.get(team, []) if y["season"] == x["season"] - 1]
        if not c or (last and last[-1]["coach"].get(team) == c):
            return hire
    return c


def coach_games(sched: Schedule, g: dict, team: str, staff: dict | None = None) -> tuple[str, int] | None:
    """(his team's head coach, which game under him this is) when his tenure
    started inside the schedule — None for a coach whose start is unknown."""
    seq = [x for x in sched.by_team.get(team, []) if (x["season"], x["week"]) <= (g["season"], g["week"])]
    if not seq or seq[-1] is not g:
        return None
    now = _coach(sched, g, team, staff)
    if not now:
        return None
    n = 0
    for x in reversed(seq):
        c = _coach(sched, x, team, staff)
        if c != now:
            return (now, n) if c else None
        n += 1
    return None


def statuses(sched: Schedule, season: int, week: int) -> dict:
    """{team: "clinched" | "eliminated"} from the finals before this week,
    under engine/restwatch's tiebreaker-free rules (a clinch it cannot
    prove is not claimed)."""
    key = ("status", season, week)
    if key in sched._memo:
        return sched._memo[key]
    rec = {t: [0, 0] for t in DIVISIONS}                      # points (2W + T), games played
    for x in sched.rows:
        if x["season"] != season or x["week"] >= week:
            continue
        h, a = x["home"], x["away"]
        hs, as_ = x["score"].get(h), x["score"].get(a)
        if h not in rec or a not in rec or hs is None or as_ is None:
            continue
        rec[h][1] += 1
        rec[a][1] += 1
        if hs == as_:
            rec[h][0] += 1
            rec[a][0] += 1
        else:
            rec[h if hs > as_ else a][0] += 2
    best = {t: p + 2 * max(0, REGULAR_SEASON_GAMES - n) for t, (p, n) in rec.items()}
    out = {}
    for t, (pts, played) in rec.items():
        if not played:
            continue
        conf, div = DIVISIONS[t]
        rivals = [r for r in rec if r != t and DIVISIONS[r] == (conf, div)]
        if all(best[r] < pts for r in rivals):
            out[t] = "clinched"
        elif sum(1 for r in rec if r != t and DIVISIONS[r][0] == conf and rec[r][0] > best[t]) >= 7:
            out[t] = "eliminated"
    sched._memo[key] = out
    return out


def game_spots(sched: Schedule, g: dict | None, team, staff: dict | None = None) -> dict:
    """{spot: what the card says} for one team's game — only the spots
    that hold."""
    team = str(team or "").upper()
    if not g or team not in (g["home"], g["away"]):
        return {}
    key = ("game", g["season"], g["week"], g["home"], team)
    if key in sched._memo:
        return sched._memo[key]
    from .fatigue import TEAM_UTC_OFFSET_FROM_ET, _kickoff_hour, body_clock
    out: dict = {}
    road = g["neutral"] or team != g["home"]
    opp = g["away"] if team == g["home"] else g["home"]
    hour = _kickoff_hour(g["kickoff"])
    if hour is not None and hour >= PRIMETIME_ET:
        out["primetime"] = f"kicks off {_clock(hour)} Eastern"
    rest = g["rest"].get(team)
    if rest and rest >= EXTRA_REST_DAYS and sched.before(team, g):
        out["extra_rest"] = f"{rest} days since his team's last game"
    if g["neutral"]:
        out["long_trip"] = "a neutral site abroad"
    elif road:
        mine, theirs = TEAM_UTC_OFFSET_FROM_ET.get(team), TEAM_UTC_OFFSET_FROM_ET.get(g["home"])
        if mine is not None and theirs is not None and abs(mine - theirs) >= TRIP_ZONES:
            out["long_trip"] = f"{abs(mine - theirs)} time zones from home"
    clock = body_clock(team, g["kickoff"])
    if clock is not None and clock <= BODY_CLOCK_EARLY:
        out["body_clock"] = f"kicks off at {_clock(clock)} by his team's home clock"
    if g["div"] or DIVISIONS.get(team) == DIVISIONS.get(opp):
        if any(opp in (x["home"], x["away"]) for x in sched.before(team, g)):
            out["div_rematch"] = f"second meeting with {opp} this season"
    cg = coach_games(sched, g, team, staff)
    if cg and cg[1] <= NEW_COACH_GAMES:
        out["new_coach"] = f"game {cg[1]} under {cg[0]}"
    if road:
        from .stadiums import STADIUMS
        ft = VENUE_ALTITUDE.get(g["stadium_id"]) if g["neutral"] else getattr(STADIUMS.get(g["home"]), "altitude_ft", 0)
        if ft and ft >= ALTITUDE_FT:
            out["altitude"] = f"{ft:,} feet up"
    if road and not g["neutral"]:
        here = g["surface"] or _home_surface(sched, g["home"], g["season"])
        mine = _home_surface(sched, team, g["season"])
        if here and mine and here != mine:
            out["surface_switch"] = f"{here} here, {mine} at home"
    if g["week"] >= LATE_FROM_WEEK:
        st = statuses(sched, g["season"], g["week"]).get(team)
        if st:
            out["late_season"] = (f"{team} has clinched its division" if st == "clinched"
                                  else f"{team} is eliminated")
    sched._memo[key] = out
    return out


# --- the player's spots ---------------------------------------------------------------
def revenge(games: list, i: int) -> str | None:
    """His old team, when game ``i`` of ``games`` — [(team, opponent), …]
    in date order — is his first against a team he played REVENGE_GAMES+
    games for, since he left it."""
    if i < 0 or i >= len(games):
        return None
    team, opp = games[i]
    if not opp or opp == team:
        return None
    with_them = [k for k in range(i) if games[k][0] == opp]
    if len(with_them) < REVENGE_GAMES:
        return None
    if any(games[k][1] == opp for k in range(with_them[-1] + 1, i)):
        return None
    return opp


def milestone(market: str, values, games_left) -> dict | None:
    """His chase of this market's round number, from his values THIS
    season before the game and his team's games left (this one counted):
    {"target", "total", "need", "games_left", "pace", "flag", "note"} —
    None when there is no chase to name."""
    target = MILESTONES.get(market)
    vals = [float(v) for v in (values or []) if v is not None]
    if not target or not games_left or games_left <= 0 or len(vals) < MILESTONE_MIN_PLAYED:
        return None
    total = sum(vals)
    need = target - total
    pace = total / len(vals)
    if need <= 0 or pace <= 0:
        return None
    ratio = need / (pace * games_left)
    flag = games_left <= MILESTONE_GAMES_LEFT and MILESTONE_BAND[0] <= ratio <= MILESTONE_BAND[1]
    if not flag and not (games_left <= MILESTONE_SHOW_LEFT and ratio <= MILESTONE_SHOW_REACH):
        return None
    label = LABELS.get(market, market)
    games = "game" if games_left == 1 else f"{games_left} games"
    note = (f"{total:,.0f} {label} — needs {need:,.0f} more in his last {games} for {target:,} "
            f"(he averages {pace:,.1f} a game)" if pace < 10 else
            f"{total:,.0f} {label} — needs {need:,.0f} more in his last {games} for {target:,} "
            f"(he averages {pace:,.0f} a game)")
    return {"target": target, "total": round(total, 1), "need": round(need, 1), "games_left": games_left,
            "pace": round(pace, 2), "flag": flag, "note": note}


def games_left(sched: Schedule, g: dict | None, team) -> int | None:
    """His team's regular-season games left, this one counted."""
    if not g:
        return None
    return max(0, REGULAR_SEASON_GAMES - len(sched.before(str(team or "").upper(), g)))


def player_spots(sched: Schedule, g: dict | None, team, *, player: str = "", position: str = "",
                 market: str = "", games=None, i=None, values=None, contracts=None,
                 staff: dict | None = None) -> tuple[dict, dict | None]:
    """({spot: what the card says}, the milestone chase or None) for one
    player's pick: the game's spots, then revenge (``games`` and ``i``, see
    ``revenge``), contract year (``contracts`` = engine/contracts' table)
    and the milestone in ``market`` (``values`` = this season's, before the
    game)."""
    out = dict(game_spots(sched, g, team, staff))
    if games is not None and i is not None:
        old = revenge(games, i)
        if old:
            out["revenge"] = f"first game against {old} since he left"
    if contracts and g:
        from .contracts import contract_year, lookup
        if contract_year(lookup(contracts, player, position), g["season"]):
            out["contract_year"] = "the last season of his deal"
    chase = milestone(market, values, games_left(sched, g, team)) if values is not None else None
    if chase and chase["flag"]:
        out["milestone"] = chase["note"]
    return out, chase


def staff_for(*seasons) -> dict:
    """{season: data/nfl_staff_changes.json's teams that season} — the
    shape ``game_spots`` reads (each season read once per process: the
    file only changes with a deploy, which restarts it)."""
    return {int(s): _staff(int(s)) for s in seasons if s}


@functools.lru_cache(maxsize=16)
def _staff(season: int) -> dict:
    from .teamchange import load_staff
    return load_staff(season)


def player_history(hist, players, since: int) -> dict:
    """{player: {"games": [(season, week, team, opponent)] in order,
    "values": {(season, market): [(week, value)] in week order}}} from the stored
    logs since ``since`` — what the live board needs for revenge games and
    milestone chases. Read-only; an unreadable history is an empty dict."""
    out: dict = {}
    names = sorted({p for p in players if p})
    try:
        for k in range(0, len(names), 400):
            chunk = names[k:k + 400]
            q = ("SELECT player, season, period, team, opponent, market, value FROM player_game_logs "
                 f"WHERE sport='nfl' AND season >= ? AND player IN ({','.join('?' * len(chunk))})")
            for r in hist.execute(q, [int(since), *chunk]):
                wk = _int(r[2])
                if wk is None:
                    continue
                d = out.setdefault(r[0], {"games": {}, "values": {}})
                d["games"][(int(r[1]), wk)] = (str(r[3] or "").upper(), str(r[4] or "").upper())
                if r[6] is not None:
                    d["values"].setdefault((int(r[1]), r[5]), []).append((wk, float(r[6])))
    except Exception:                                         # noqa: BLE001
        return {}
    for d in out.values():
        d["games"] = [(s, w, t, o) for (s, w), (t, o) in sorted(d["games"].items())]
        d["values"] = {k: sorted(vs) for k, vs in d["values"].items()}
    return out


def live_inputs(hist_row: dict | None, g: dict, team, market: str) -> tuple[list, int, list]:
    """(his games as (team, opponent) with this one last, its index, his
    values in ``market`` this season before it) from ``player_history``."""
    h = hist_row or {}
    past = [(t, o) for s, w, t, o in h.get("games") or [] if (s, w) < (g["season"], g["week"])]
    opp = g["away"] if str(team or "").upper() == g["home"] else g["home"]
    games = past + [(str(team or "").upper(), opp)]
    vals = [v for w, v in (h.get("values") or {}).get((g["season"], market), []) if w < g["week"]]
    return games, len(games) - 1, vals
