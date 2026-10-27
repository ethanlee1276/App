"""Team defenses (D/ST) this week, in fantasy points.

Ethan, 2026-10-27: "make sure we're using all our tools and data … in our
fantasy room … and that the fantasy room is actually a useful tool". Almost
every league starts a team defense, and every league desk here valued one at
zero: there was no projection for a defense at all, so the lineup could not
pick one and no pickup list ever named one (docs/FANTASY.md, gap 1).

WHAT A DEFENSE SCORES, in the common (Sleeper's default) scoring: 1 a sack,
2 an interception or a fumble recovery, 2 a safety or a blocked kick, 6 a
defensive or return touchdown, and a bonus for points allowed that shrinks
the more it allows (10 for a shutout, 7 for 1-6, 4 for 7-13, 1 for 14-20, 0
for 21-27, −1 for 28-34, −4 for 35 or more). A league's own values and tiers
apply on top (`points`, `scoring_from_sleeper`).

WHAT THIS PROJECTS, from what the site already holds:

  * POINTS ALLOWED: the opponent's implied total off this week's line (the
    total and the spread, the same `touchdowns.team_implied_total` the
    touchdown board reads), and a normal spread around it (`PA_SD`), scored
    tier by tier on the league's own tiers;
  * SACKS: the opponent's dropbacks a game times the sack rate the two sides
    imply together — the defense's sacks per dropback faced against the
    offense's sacks taken per dropback, each over the league's (log5), both
    shrunk toward the league while a season is young (`engine/sources
    /nflunits`, the play-by-play's own count);
  * TAKEAWAYS: interceptions and fumble recoveries the same way, the
    defense's takeaways a game against the offense's giveaways
    (`team_weeks`, every play, special teams too), split at the league's own
    share of interceptions;
  * TOUCHDOWNS: a share of the takeaways (a pick-six, a scoop-and-score) and
    the league's return-touchdown rate; safeties and blocked kicks at the
    league's rates.

Each count is Poisson around its rate and points allowed is normal, so the
range on the card (where eight weeks in ten land) is simulated from them,
seeded per team so the same inputs always draw the same range.

WHAT IT DOES NOT CLAIM. Yards-allowed tiers (some ESPN leagues score them)
are not projected: the row names them in `missing` rather than guessing. A
team the tables know nothing about this season is projected at the league's
rates and says so. The numbers here are the league averages a season of
play-by-play gives; `dstfit.py` walks past seasons forward on the box and
saves what it measures (`saved_fit`), which this then reads.

Standard library only. Pure apart from `team_rates`, which reads the DB.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

#: The league's own rates, from a season of play-by-play (2023-2025 NFL:
#: about 6.6% of dropbacks end in a sack; 1.3 takeaways a team-game, 58% of
#: them interceptions; a tenth of takeaways come back for a touchdown, and a
#: return touchdown, a safety and a blocked kick each come about once in
#: thirty, fifty and thirty team-games). `dstfit.py --save` replaces them
#: with the box's own measurement.
LEAGUE = {
    "sack_rate": 0.066,          # sacks per dropback, league
    "dropbacks": 37.0,           # dropbacks per team-game, league
    "takeaways": 1.3,            # takeaways per team-game, league
    "int_share": 0.58,           # share of takeaways that are interceptions
    "td_per_takeaway": 0.10,     # defensive touchdowns per takeaway
    "st_td": 0.035,              # return touchdowns per team-game
    "safe": 0.02,                # safeties per team-game
    "blk_kick": 0.03,            # blocked kicks per team-game
    "implied": 22.0,             # points per team-game, when a line is missing
    "pa_sd": 9.8,                # points scored around the implied total
    "script_dropbacks": 0.010,   # an underdog throws more: per point of spread
}
#: Shrinkage toward the league: a rate counts this many league dropbacks
#: (and takeaways this many league games) before the team's own.
PRIOR_DROPBACKS = 250.0
PRIOR_GAMES = 4.0

#: The common scoring (Sleeper's default for a team defense).
DEFAULT = {
    "sack": 1.0, "int": 2.0, "fum_rec": 2.0, "safe": 2.0, "def_td": 6.0, "st_td": 6.0,
    "blk_kick": 2.0,
    "pts_allow": [(0, 0, 10.0), (1, 6, 7.0), (7, 13, 4.0), (14, 20, 1.0),
                  (21, 27, 0.0), (28, 34, -1.0), (35, 999, -4.0)],
}
#: Sleeper's scoring keys for the points-allowed tiers.
SLEEPER_PA = {"pts_allow_0": (0, 0), "pts_allow_1_6": (1, 6), "pts_allow_7_13": (7, 13),
              "pts_allow_14_20": (14, 20), "pts_allow_21_27": (21, 27),
              "pts_allow_28_34": (28, 34), "pts_allow_35p": (35, 999)}
#: …and its yards-allowed ones, which are not projected (see the docstring).
SLEEPER_YDS_PREFIX = "yds_allow_"

#: A matchup worth naming: the opponent's implied total at or under / over.
SOFT_IMPLIED, TOUGH_IMPLIED = 19.5, 25.5
#: Draws for the range (seeded per team).
SIMS = 2000

FIT_PATH = Path(__file__).resolve().parents[1] / "data" / "models" / "dst_fit.json"

#: Every club's full name, and the aliases platforms use for its code.
NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LV": "Las Vegas Raiders", "LAC": "Los Angeles Chargers",
    "LA": "Los Angeles Rams", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SF": "San Francisco 49ers", "SEA": "Seattle Seahawks", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}
ALIASES = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "OAK": "LV", "SD": "LAC", "STL": "LA"}
DEF_POSITIONS = ("DEF", "DST", "D/ST")


def code(team) -> str:
    t = str(team or "").strip().upper()
    return ALIASES.get(t, t)


def team_of(name, team=None) -> str | None:
    """The club a defense row is, by its code where the platform gives one
    (Sleeper's DEF ids are codes) and by its name otherwise: ESPN's "Eagles
    D/ST", Yahoo's "Philadelphia", Sleeper's "Philadelphia Eagles". A name
    two clubs could share ("New York", "Los Angeles") is no club."""
    t = code(team)
    if t in NAMES:
        return t
    raw = " ".join(str(name or "").replace("D/ST", " ").replace("DST", " ")
                   .replace("Defense", " ").split()).lower()
    if not raw:
        return None
    for c, full in NAMES.items():
        if raw == full.lower():
            return c
    # Every club's nickname is one word ("Eagles", "49ers").
    nick = [c for c, full in NAMES.items() if raw == full.lower().split()[-1]]
    if len(nick) == 1:
        return nick[0]
    city = [c for c, full in NAMES.items() if full.lower().startswith(raw + " ")]
    return city[0] if len(city) == 1 else None


def saved_fit() -> dict:
    try:
        return json.loads(FIT_PATH.read_text())
    except (OSError, ValueError):
        return {}


def league_rates() -> dict:
    """LEAGUE, with the box's measured values where `dstfit.py --save` kept them."""
    fit = (saved_fit().get("league") or {})
    return {**LEAGUE, **{k: float(v) for k, v in fit.items() if k in LEAGUE and isinstance(v, (int, float))}}


def implied(game: dict, team: str, league: dict | None = None) -> float:
    """A side's implied points off a board game dict (`spread` is the home
    spread, negative when the home side is favoured)."""
    lg = league or LEAGUE
    try:
        total, spread = float(game.get("total") or 0), float(game.get("spread") or 0)
    except (TypeError, ValueError):
        total, spread = 0.0, 0.0
    if total <= 0:
        return float(lg["implied"])
    half = total / 2.0
    return half - spread / 2.0 if team == game.get("home") else half + spread / 2.0


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def tier_probs(mu: float, sd: float, tiers) -> list:
    """The chance points allowed lands in each tier: normal around ``mu``,
    read at half-points (scores are whole), everything under zero counted as
    a shutout."""
    out = []
    for lo, hi, _pts in tiers:
        top = 1.0 if hi >= 999 else _phi((hi + 0.5 - mu) / sd)
        bot = 0.0 if lo <= 0 else _phi((lo - 0.5 - mu) / sd)
        out.append(max(0.0, top - bot))
    return out


def scoring_from_sleeper(settings: dict | None) -> dict:
    """A Sleeper league's defense scoring, over the default for anything it
    does not set. Returns DEFAULT's shape plus `yds_allow` (True when the
    league scores yards allowed, which is not projected)."""
    s = settings or {}
    out = {k: (float(s[k]) if isinstance(s.get(k), (int, float)) else v)
           for k, v in DEFAULT.items() if k != "pts_allow"}
    tiers = []
    for key, (lo, hi) in SLEEPER_PA.items():
        default = next(p for a, _b, p in DEFAULT["pts_allow"] if a == lo)
        val = s.get(key)
        tiers.append((lo, hi, float(val) if isinstance(val, (int, float)) else default))
    out["pts_allow"] = tiers
    out["ff"] = float(s["ff"]) if isinstance(s.get("ff"), (int, float)) else 0.0
    out["yds_allow"] = any(k.startswith(SLEEPER_YDS_PREFIX) and s.get(k) for k in s)
    return out


def points(dst: dict, scoring: dict | None = None) -> float:
    """Expected points from a row's `dst` part under ``scoring`` (DEFAULT
    when None)."""
    sc = scoring or DEFAULT
    d = dst or {}
    tiers = sc.get("pts_allow") or DEFAULT["pts_allow"]
    probs = tier_probs(float(d.get("pa_mu") or 0), float(d.get("pa_sd") or LEAGUE["pa_sd"]), tiers)
    pa = sum(p * t[2] for p, t in zip(probs, tiers))
    return round(pa + sum(float(sc.get(k) or 0) * float(d.get(k) or 0)
                          for k in ("sack", "int", "fum_rec", "safe", "def_td", "st_td", "blk_kick", "ff")), 2)


def _shrunk(num: float, den: float, prior: float, weight: float) -> float:
    return (num + prior * weight) / (den + weight) if den + weight > 0 else prior


def team_rates(conn, season: int, before_week: int | None = None) -> dict:
    """{team: rates} for one season's weeks before ``before_week`` (all of
    them when None): the defense's sacks and the dropbacks it faced, the
    offense's sacks taken and its dropbacks, takeaways and giveaways, games.
    Raw sums; `project` shrinks them. Missing tables read as nothing."""
    out: dict = {}
    cut = f"{int(before_week):03d}" if before_week else "999"

    def slot(t):
        return out.setdefault(code(t), {"def_sacks": 0.0, "def_db": 0.0, "off_sacks": 0.0, "off_db": 0.0,
                                        "off_games": 0, "takeaways": 0.0, "giveaways": 0.0, "games": 0})
    try:
        for r in conn.execute("SELECT team, side, dropbacks, sacks FROM team_units WHERE sport='nfl' "
                              "AND season=? AND period < ?", (int(season), cut)):
            s = slot(r[0])
            if r[1] == "def":
                s["def_sacks"] += float(r[3] or 0)
                s["def_db"] += float(r[2] or 0)
            elif r[1] == "off":
                s["off_sacks"] += float(r[3] or 0)
                s["off_db"] += float(r[2] or 0)
                s["off_games"] += 1
    except Exception:                                      # noqa: BLE001 — a box without the table
        pass
    try:
        for r in conn.execute("SELECT team, takeaways, giveaways FROM team_weeks WHERE sport='nfl' "
                              "AND season=? AND period < ?", (int(season), cut)):
            s = slot(r[0])
            s["takeaways"] += float(r[1] or 0)
            s["giveaways"] += float(r[2] or 0)
            s["games"] += 1
    except Exception:                                      # noqa: BLE001
        pass
    return out


#: Last season counts as this many of its games, early on: a defense's
#: identity carries over (most of its starters do), and four games of it
#: settle a September rate without drowning this season's.
LAST_SEASON_WEIGHT = 0.25


def season_rates(conn, season: int, week: int | None = None) -> dict:
    """This season's sums before ``week``, with last season's added at
    LAST_SEASON_WEIGHT: the rates `project` reads."""
    now = team_rates(conn, season, week)
    before = team_rates(conn, int(season) - 1)
    out = {}
    for t in set(now) | set(before):
        a, b = now.get(t) or {}, before.get(t) or {}
        out[t] = {k: float(a.get(k) or 0) + LAST_SEASON_WEIGHT * float(b.get(k) or 0)
                  for k in set(a) | set(b)}
    return out


def _side(rates: dict, team: str) -> dict:
    return rates.get(code(team)) or {}


def project(game: dict, defense: str, rates: dict | None = None, league: dict | None = None) -> dict | None:
    """One defense's week against the other side of ``game``: its expected
    counts (`dst`), its points under DEFAULT, the range, the matchup and the
    reasons. None when the defense is not in this game."""
    lg = league or LEAGUE
    home, away = code(game.get("home")), code(game.get("away"))
    d = code(defense)
    if d not in (home, away):
        return None
    opp = away if d == home else home
    rates = rates or {}
    D, O = _side(rates, d), _side(rates, opp)
    mu = implied({**game, "home": home}, opp, lg)
    # The opponent's dropbacks a game, more of them as the underdog.
    db_pg = _shrunk(float(O.get("off_db") or 0), float(O.get("off_games") or 0), lg["dropbacks"], PRIOR_GAMES)
    try:
        spread = float(game.get("spread") or 0)
    except (TypeError, ValueError):
        spread = 0.0
    opp_dog = spread if opp == home else -spread          # points the opponent is getting
    db_pg *= max(0.8, min(1.2, 1.0 + lg["script_dropbacks"] * opp_dog))
    r_def = _shrunk(float(D.get("def_sacks") or 0), float(D.get("def_db") or 0), lg["sack_rate"], PRIOR_DROPBACKS)
    r_off = _shrunk(float(O.get("off_sacks") or 0), float(O.get("off_db") or 0), lg["sack_rate"], PRIOR_DROPBACKS)
    sacks = db_pg * r_def * r_off / lg["sack_rate"]
    ta = _shrunk(float(D.get("takeaways") or 0), float(D.get("games") or 0), lg["takeaways"], PRIOR_GAMES)
    ga = _shrunk(float(O.get("giveaways") or 0), float(O.get("games") or 0), lg["takeaways"], PRIOR_GAMES)
    takeaways = ta * ga / lg["takeaways"]
    dst = {"pa_mu": round(mu, 2), "pa_sd": lg["pa_sd"], "sack": round(sacks, 3),
           "int": round(takeaways * lg["int_share"], 3), "fum_rec": round(takeaways * (1 - lg["int_share"]), 3),
           "def_td": round(takeaways * lg["td_per_takeaway"], 3), "st_td": lg["st_td"],
           "safe": lg["safe"], "blk_kick": lg["blk_kick"], "ff": 0.0}
    known = bool(D.get("games") or D.get("def_db")) and bool(O.get("games") or O.get("off_db"))
    grade = "soft" if mu <= SOFT_IMPLIED else "tough" if mu >= TOUGH_IMPLIED else None
    oname, dname = NAMES.get(opp, opp), NAMES.get(d, d)
    lo, hi = range_for(dst, d)
    # The same shape as a player's reasons (fantasyweek._reasons): a step
    # and the sentence the card shows.
    reasons = [
        {"step": "line", "why": f"{oname} are implied for {mu:.1f} points this week."},
        {"step": "pressure", "why": (f"The {dname.split()[-1]} sack {r_def * 100:.1f}% of dropbacks faced; "
                                     f"the {oname.split()[-1]} give one up on {r_off * 100:.1f}% "
                                     f"(league {lg['sack_rate'] * 100:.1f}%).")},
        {"step": "turnovers", "why": (f"{ta:.1f} takeaways a game against {ga:.1f} giveaways a game "
                                      f"(league {lg['takeaways']:.1f}).")},
    ]
    pts = points(dst)
    return {
        "player": dname, "team": d, "position": "DEF", "opponent": opp,
        "game": {"home": home, "away": away, "date": game.get("date"), "kickoff": game.get("kickoff")},
        "ppr": pts, "expected": pts, "play": 1.0,
        "range": [lo, hi],
        # THE SPREAD THE HEAD-TO-HEAD ADDS UP (fantasyweek.week_entry): the
        # simulated range read as a normal one (the 10th to the 90th
        # percentile is 2.56 spreads), so a defense swings a matchup by its
        # own week instead of counting as a certainty.
        "sd": round((hi - lo) / 2.563, 2),
        "matchup": {"grade": grade, "text": f"{oname} implied for {mu:.1f} points"},
        "dst": dst, "reasons": reasons,
        "sources": [] if known else ["league rates (no games of theirs on file this season)"],
    }


def range_for(dst: dict, team: str = "", scoring: dict | None = None, sims: int = SIMS) -> tuple[float, float]:
    """Where eight weeks in ten land: the 10th and 90th percentiles of
    simulated weeks (normal points allowed, Poisson counts), seeded by team
    so the same inputs draw the same range."""
    sc = scoring or DEFAULT
    tiers = sc.get("pts_allow") or DEFAULT["pts_allow"]
    rnd = random.Random(f"dst:{team}:{dst.get('pa_mu')}:{dst.get('sack')}:{dst.get('int')}")

    def pois(lam):
        if lam <= 0:
            return 0
        k, p, cut = 0, 1.0, math.exp(-lam)
        while True:
            p *= rnd.random()
            if p <= cut:
                return k
            k += 1

    weeks = []
    for _ in range(sims):
        pa = max(0, int(round(rnd.gauss(float(dst.get("pa_mu") or 0), float(dst.get("pa_sd") or LEAGUE["pa_sd"])))))
        tier = next((t[2] for t in tiers if t[0] <= pa <= t[1]), 0.0)
        pts = tier + sum(float(sc.get(k) or 0) * pois(float(dst.get(k) or 0))
                         for k in ("sack", "int", "fum_rec", "def_td", "st_td", "safe", "blk_kick"))
        weeks.append(pts)
    weeks.sort()
    return round(weeks[int(0.1 * sims)], 1), round(weeks[int(0.9 * sims) - 1], 1)


def week_rows(games: list, rates: dict | None = None, league: dict | None = None) -> list:
    """Every defense playing this week, best first: the rows the week's file
    carries beside the players (position DEF)."""
    lg = league or league_rates()
    out = []
    for g in games or []:
        for side in (g.get("home"), g.get("away")):
            if side:
                row = project(g, side, rates, lg)
                if row:
                    out.append(row)
    out.sort(key=lambda r: -r["expected"])
    return out


def with_scoring(row: dict, scoring: dict | None) -> dict:
    """A defense row re-scored under a league's own defense scoring: its
    points and its range. A league that scores yards allowed is told that
    part is not projected (`missing`)."""
    # A free reader's copy carries no workings (gate: `dst` is paid), so
    # there is nothing to re-score: the common scoring's points stand.
    if not scoring or not row.get("dst"):
        return row
    dst = row.get("dst") or {}
    pts = points(dst, scoring)
    lo, hi = range_for(dst, row.get("team") or "", scoring, sims=800)
    out = {**row, "ppr": pts, "expected": pts, "range": [lo, hi], "sd": round((hi - lo) / 2.563, 2)}
    if scoring.get("yds_allow"):
        out["missing"] = list(row.get("missing") or []) + ["yards-allowed tiers"]
    return out
