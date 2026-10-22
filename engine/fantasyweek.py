"""This week's fantasy projection: the NFL board's numbers, in fantasy points.

Ethan, 2026-10-22: "with all this new data added for nfl with how we do
the offense and defense and game scripts and all the data from our game
reports. We need to make sure we are using that data correctly for
fantasy ... make sure we wrap that into it how it should be".

WHAT THE FANTASY TOOLS USED. Every league desk (the lineup, the
head-to-head, the trade finder, on Sleeper, ESPN and Yahoo alike) valued a
player at his SEASON AVERAGE (`fantasy_lineup.per_game`). It ignored the
matchup, the game script and injuries. A receiver facing the stingiest pass
defence in the league, in a 25 mph wind, with his quarterback out, was
worth exactly what he averaged against everyone else. A player on a bye
was worth his average too.

WHAT THEY READ NOW. Each stat comes from the prop board's own projection,
the chain every pick on the site is built on (engine/projection):
  * form, over measured windows;
  * his measured usage role (engine/nflusage);
  * the defence against his position, at its measured strength
    (engine/defensevs);
  * the game script's tilt (engine/gamescript);
  * the weather (engine/wxfit);
  * his quarterback or a teammate at his position out (engine/qbchange,
    engine/teammates);
  * his team's pace and pass rate (engine/teamcontext);
  * the record's own correction for players the chain misreads.
His touchdowns come from the measured touchdown model (engine/touchdowns):
his team's implied total, his red-zone work, his share of the offence's
expected points, the defence and the weather, calibrated exactly as the
touchdown board is. The stats are added up under PPR, and each component is
kept so a league's own scoring applies on top (`fantasy_lineup
.league_points`), the same way it does to a season average.

WHAT IT DOES NOT INVENT:
  * A stat the board does not project for him comes from his own season
    average in it (`fill_missing`, measured: a receiver with a yards line
    and no catches line was four points short), and `sources` names every
    part that did. A part with no average either is left out and NAMED in
    `missing`, not guessed; fumbles and two-point tries are never counted.
  * The scan's read (could shine, could struggle), the game report's form
    and the role-change watch ride along as REASONS. They move no number:
    each was measured as a reading, and the projection already holds the
    defence and the usage they are built from.

AVAILABILITY. A player ruled out, on injured reserve or suspended is worth
zero this week. A questionable or doubtful player is worth the chance he
plays (the practice reports, engine/practice, measured on every stored
listing) times what the projection gives him if he does. Both numbers are
on the row, so a manager who can wait on a late game sees what he is
waiting on.

Standard library only. Pure: every input is handed in.
"""

from __future__ import annotations

import math

#: The board's markets that ARE fantasy components, by the component name
#: the league desks score (`fantasy_lineup.SCORING_MARKET`'s values).
COMPONENTS = {
    "pass_yds": "pass_yds", "pass_td": "pass_td", "pass_int": "pass_int",
    "rush_yds": "rush_yds", "rec_yds": "rec_yds", "receptions": "receptions",
    "kick_pts": "kick_pts",
}
#: Volume the card shows beside the points. Scored by no standard league.
VOLUME = {"rush_att": "carries", "pass_att": "pass_att", "pass_cmp": "pass_cmp"}

#: PPR: nflverse's own `fantasy_points_ppr`, the unit of every season
#: average the desks hold, so a league's rules are applied to both the
#: same way (`fantasy_lineup.PPR_BASELINE`; tested equal).
PPR = {"pass_yds": 0.04, "pass_td": 4.0, "pass_int": -2.0,
       "rush_yds": 0.1, "rec_yds": 0.1, "receptions": 1.0,
       "rush_td": 6.0, "rec_td": 6.0, "kick_pts": 1.0}
HALF = {**PPR, "receptions": 0.5}
STANDARD = {**PPR, "receptions": 0.0}

#: What each position's line is expected to carry. A component missing
#: from this list is a gap worth naming; one not on it is not his game.
EXPECTED = {
    "QB": ("pass_yds", "pass_td", "pass_int", "rush_yds"),
    "RB": ("rush_yds", "receptions", "rec_yds"),
    "WR": ("rec_yds", "receptions"),
    "TE": ("rec_yds", "receptions"),
    "K": ("kick_pts",),
}
#: The positions the touchdown model prices. A kicker scores through his
#: kicking points and a defender is not on a fantasy roster here.
TD_POSITIONS = ("QB", "RB", "WR", "TE")

#: Never a fantasy starter this week, whatever the projection says.
#: "SUS" is Sleeper's spelling of suspended.
OUT_STATUSES = {"OUT", "IR", "SUSPENDED", "SUS", "PUP", "NFI", "INACTIVE", "RESERVE"}

#: Each position's MAIN market: whose chain the card's reasons come from.
MAIN_MARKET = {"QB": "pass_yds", "RB": "rush_yds", "WR": "rec_yds",
               "TE": "rec_yds", "K": "kick_pts"}

#: The chain steps a fantasy card names when they moved his number, in
#: the order a manager weighs them: who plays around him and who is hurt
#: around him first, then the defence, the team's tendency, the weather,
#: his role, the record's correction for him, the air a kick flies
#: through, and the learned model where it stands in for the dials.
REASON_STEPS = ("lineup", "injury", "matchup", "context", "weather", "usage", "player",
                "air", "learned")
#: A step this close to 1.0 changed nothing worth a sentence.
FLAT = 0.02


def td_lambda(p) -> float:
    """Expected touchdowns from the chance he scores at least one.

    The touchdown model works the other way round: an expected count, then
    ``1 - e^-x`` (engine/touchdowns). Inverting it hands back the count, and
    the calibrated chance is the one the board publishes."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return 0.0
    if p <= 0.0:
        return 0.0
    return -math.log(1.0 - min(p, 0.999))


def split_tds(lam: float, position: str, rush_yds: float = 0.0,
              rec_yds: float = 0.0) -> tuple[float, float]:
    """(rushing, receiving) touchdowns from his expected total.

    A quarterback's are his own carries; a back's split the way his yards
    do; a receiver or tight end catches his unless he is projected to run
    for some. Only a league that scores the two differently notices."""
    pos = (position or "").upper()
    if lam <= 0:
        return 0.0, 0.0
    if pos == "QB":
        return lam, 0.0
    ry, cy = max(0.0, float(rush_yds or 0.0)), max(0.0, float(rec_yds or 0.0))
    if ry + cy <= 0:
        return (lam, 0.0) if pos == "RB" else (0.0, lam)
    return lam * ry / (ry + cy), lam * cy / (ry + cy)


def points(comp: dict, scoring: dict | None = None) -> float:
    """Fantasy points from components. PPR when no scoring is given."""
    rules = scoring or PPR
    return round(sum(float(rules.get(k, 0.0)) * float(v or 0.0)
                     for k, v in (comp or {}).items() if k in rules), 2)


def play_chance(status: str, practice: dict | None = None,
                fallback: dict | None = None) -> tuple[float, str]:
    """(chance he plays, where that came from).

    ``practice`` is his row in the practice reports' section
    (engine/practice.ideas_section): his designation, how he practised,
    and the measured share of players listed that way who played. The
    club-folded number is used only when its held-out bar holds, the rule
    engine/practice states for itself. ``fallback`` is the by-designation
    table measured on nflverse's reports (`FALLBACK_PLAY`) for a box that
    has not saved the practice fit."""
    st = str(status or (practice or {}).get("designation") or "").strip().upper()
    if st in OUT_STATUSES:
        return 0.0, "ruled out"
    if practice:
        club = practice.get("club")
        held = (practice.get("held_out") or {}).get("holds")
        if club is not None and held:
            return float(club), "practice report and his club's record"
        if practice.get("league") is not None:
            return float(practice["league"]), "practice report"
    table = fallback if fallback is not None else fallback_play()
    how = str((practice or {}).get("practice") or "")
    for key in ("Doubtful", "Questionable"):
        if st != key.upper():
            continue
        for cell in ((f"{key}|{how}", "designation and how he practised"),
                     (f"{key}|*", "designation")):
            p = table.get(cell[0]) if cell[0] != f"{key}|" else None
            if p is not None:
                return float(p), cell[1]
    return 1.0, ""


#: THE CHANCE A LISTED PLAYER PLAYS, by designation and how he practised
#: ("Questionable|Limited"; "Questionable|*" for any), for a box whose
#: practice fit is not saved. Measured by `fantasyweekfit.py` on
#: nflverse's injury reports against its snap counts, 2023-2025 regular
#: seasons (2026-10-22): 4,230 questionable listings, 450 doubtful. A
#: questionable player took a snap 64.6% of the time — 51.8% after a week
#: of no practice, 70.2% after a full one. A doubtful one, 1.1%. Cells
#: with fewer than PLAY_MIN_N listings are left out ("Doubtful|None", 4).
#: A box's own `--save` wins; the practice fit (engine/practice) wins
#: over both, with his club's record folded in when its bar holds.
FALLBACK_PLAY: dict = {
    "Questionable|*": 0.6456, "Questionable|DNP": 0.5183,
    "Questionable|Limited": 0.6556, "Questionable|Full": 0.7024,
    "Questionable|None": 0.6538,
    "Doubtful|*": 0.0111, "Doubtful|DNP": 0.0159,
    "Doubtful|Limited": 0.0068, "Doubtful|Full": 0.0,
}
#: Listings a cell needs before its share is kept.
PLAY_MIN_N = 40

#: HOW WIDE A WEEK LANDS AROUND ITS PROJECTION, per position: the
#: standard deviation of actual PPR points minus the projection, as
#: ``(intercept, slope)`` on the projection — what the head-to-head's win
#: chance adds up (engine/fantasy_h2h). Measured by `fantasyweekfit.py`
#: walk-forward, 2023-2025 weeks 4-17, 10,445 player-weeks, with the
#: season-average fill (2026-10-22). A receiver projected for 12: a spread
#: of 7.6 points; a tight end projected for 7: 5.6.
RESIDUAL: dict = {
    "QB": (7.072, 0.0532), "RB": (3.685, 0.3024),
    "WR": (3.433, 0.3439), "TE": (2.611, 0.4254),
}

#: WHERE EIGHT WEEKS IN TEN LAND, per position: the 10th and 90th
#: percentile of what players scored, by projection band, as
#: ``(low intercept, low slope, high intercept, high slope)`` on the
#: projection. Same run as RESIDUAL.
#:
#: MEASURED, NOT A NORMAL BAND. Fantasy points lean high — a touchdown is
#: six at once — and the projection ± 1.28 standard deviations missed HIGH
#: 11-12% of the time for backs, receivers and tight ends and LOW only
#: 1-4%. The percentile lines, each season held out of its own fit, held
#: 77-84% inside with the misses split either side (2025 quarterbacks the
#: loosest: 15% below, 7% above). A receiver projected for 12: 3.3 to 22.3.
RANGE: dict = {
    "QB": (-6.301, 0.716, 14.928, 0.687), "RB": (-1.618, 0.515, 6.171, 1.38),
    "WR": (-1.77, 0.42, 6.236, 1.335), "TE": (-1.215, 0.415, 4.4, 1.56),
}

#: Where `fantasyweekfit.py --save` keeps a box's own re-measurement
#: (engine/modelstate); it wins over the numbers above when present.
STORE = "fantasyweek_fit.json"
_SAVED: dict = {}


def saved_fit() -> dict:
    """The box's own saved measurement, read once a process; {} if none."""
    if "fit" not in _SAVED:
        try:
            from . import modelstate
            import json
            with open(modelstate.path(STORE)) as fh:
                _SAVED["fit"] = json.load(fh) or {}
        except (OSError, ValueError, ImportError):
            _SAVED["fit"] = {}
    return _SAVED["fit"]


def spread_for(position: str, proj: float) -> float | None:
    """The measured spread of a week around this projection, or None."""
    pos = (position or "").upper()
    fit = (saved_fit().get("residual") or {}).get(pos) or RESIDUAL.get(pos)
    if not fit or proj is None:
        return None
    a, b = fit
    return round(max(0.5, float(a) + float(b) * float(proj)), 2)


#: EXPECTED TOUCHDOWNS, SCALED PER POSITION — only from a box's own
#: `fantasyweekfit.py --save`, and only where it held. The touchdown
#: model's chance is calibrated for the touchdown board (engine/calibrate)
#: on the scorers books quote; a fantasy roster holds every skill player.
#: Walked forward without the usage maps (2026-10-22, 10,445 player-weeks),
#: backs scored 1.51 times the touchdowns the chance implied, tight ends
#: 1.44, receivers 1.08 and quarterbacks 0.75 (rushing); the back and
#: quarterback scales held on every held-out season, and they fixed the
#: level (a back +0.74 a week to +0.06) without ordering anyone better.
#: But the live model takes 70% of a player's share from his
#: expected-points share (touchdowns.XFP_SHARE_WEIGHT), which that run
#: could not see, so no scale is set here. The box's run replays the maps
#: (nflusage.build_usage_maps as of each week) and saves a position's
#: scale only when it beat no scale on every season held out of its fit.
TD_SCALE: dict = {}


def td_scale_for(position: str) -> float:
    """The measured multiplier on his expected touchdowns, else 1.0."""
    pos = (position or "").upper()
    got = (saved_fit().get("td_scale") or {}).get(pos) or TD_SCALE.get(pos)
    try:
        return float(got) if got else 1.0
    except (TypeError, ValueError):
        return 1.0


def range_for(position: str, proj, fit=None) -> tuple[float, float] | None:
    """(low, high): where eight weeks in ten land around this projection,
    PPR, if he plays. None when his position's range is not measured."""
    pos = (position or "").upper()
    f = fit or (saved_fit().get("range") or {}).get(pos) or RANGE.get(pos)
    if not f or proj is None:
        return None
    la, lb, ha, hb = (float(x) for x in f)
    lo = max(0.0, la + lb * float(proj))
    hi = max(lo + 1.0, ha + hb * float(proj))
    return round(lo, 1), round(hi, 1)


def fallback_play() -> dict:
    """By-designation play chances: the box's saved fit, else the run above."""
    return {**FALLBACK_PLAY, **(saved_fit().get("play") or {})}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _grade(card: dict | None) -> str | None:
    """"soft", "tough" or "neutral" from a matchup card's rank: the
    first-most allowed is the softest. A third of the league each way."""
    if not card:
        return None
    rank, of = card.get("rank"), card.get("of") or 32
    try:
        rank, of = int(rank), int(of)
    except (TypeError, ValueError):
        return None
    if rank <= of // 3:
        return "soft"
    if rank > of - of // 3:
        return "tough"
    return "neutral"


def _reasons(row: dict) -> list[dict]:
    """The steps of his main market's chain that moved the number, as
    {key, label, mult, why}, biggest move first."""
    out = []
    for s in ((row or {}).get("chain") or {}).get("steps") or []:
        if s.get("key") not in REASON_STEPS:
            continue
        m = _f(s.get("mult"))
        if m is None or abs(m - 1.0) < FLAT or not s.get("why"):
            continue
        out.append({"key": s["key"], "label": s.get("label") or s["key"],
                    "mult": round(m, 3), "why": s["why"]})
    order = {k: i for i, k in enumerate(REASON_STEPS)}
    out.sort(key=lambda s: (-abs(s["mult"] - 1.0), order.get(s["key"], 99)))
    return out


def _script(row: dict) -> dict | None:
    gs = (row or {}).get("game_script") or {}
    if not gs:
        return None
    return {k: gs.get(k) for k in ("role", "team_implied", "opp_implied", "lean",
                                   "archetype", "summary", "line") if gs.get(k) is not None}


def project_players(rows: list, tds: dict | None = None, *,
                    practice: dict | None = None, reads: dict | None = None,
                    roles: dict | None = None, games: list | None = None) -> list:
    """Every player on the board, in fantasy terms. Pure.

    ``rows``: the board's evaluated prop rows (`pipeline.price_props`),
    every market of every player. ``tds``: {(team, player): {"prob",
    "reasons", "quoted"}} from `pipeline.td_chances`. ``practice``: the
    practice reports' `listed` map (normalised name → row). ``reads``:
    {(team, player): scan read row}. ``roles``: the role-change section's
    `players` map. ``games``: the board's game dicts, for the kickoff."""
    from .backtest import _norm
    tds = tds or {}
    practice = practice or {}
    reads = reads or {}
    roles = roles or {}
    kick = {}
    for g in games or []:
        for side in ("home", "away"):
            if g.get(side):
                kick[g[side]] = {"date": g.get("date"), "kickoff": g.get("kickoff"),
                                 "home": g.get("home"), "away": g.get("away")}
    people: dict = {}
    for r in rows or []:
        name, team = r.get("player"), r.get("team")
        if not name or not team:
            continue
        p = people.setdefault((team, name), {
            "player": name, "team": team, "opponent": r.get("opponent"),
            "position": (r.get("position") or "").upper(),
            "headshot": r.get("headshot") or "", "rows": {}})
        p["rows"][r.get("market")] = r
    out = []
    for (team, name), p in people.items():
        pos = p["position"]
        comp: dict = {}
        sources: dict = {}
        for market, key in COMPONENTS.items():
            row = p["rows"].get(market)
            v = _f((row or {}).get("projection"))
            if v is None:
                continue
            comp[key] = max(0.0, v)
            sources[key] = "board"
        volume = {VOLUME[m]: round(max(0.0, _f(p["rows"][m].get("projection")) or 0.0), 1)
                  for m in VOLUME if m in p["rows"] and _f(p["rows"][m].get("projection")) is not None}
        td = tds.get((team, name))
        if pos in TD_POSITIONS and td and td.get("prob") is not None:
            scale = td_scale_for(pos)
            lam = td_lambda(td["prob"]) * scale
            rush_td, rec_td = split_tds(lam, pos, comp.get("rush_yds", 0.0), comp.get("rec_yds", 0.0))
            comp["rush_td"], comp["rec_td"] = rush_td, rec_td
            sources["rush_td"] = sources["rec_td"] = ("touchdown model" if scale == 1.0 else
                                                      "touchdown model, scaled as measured")
        missing = [k for k in EXPECTED.get(pos, ()) if k not in comp]
        if pos in TD_POSITIONS and "rush_td" not in comp:
            # A quarterback's passing touchdowns are in his passing line;
            # what the touchdown model would have given him is a rushing one.
            missing.append("rush_td" if pos == "QB" else "touchdowns")
        if not comp:
            continue
        ppr = points(comp)
        main = p["rows"].get(MAIN_MARKET.get(pos, "")) or next(iter(p["rows"].values()))
        listed = practice.get(_norm(name)) or {}
        if listed and listed.get("team") and listed.get("team") != team:
            listed = {}
        # The board's status, else the week's practice report's.
        status = (main.get("injury_status") or listed.get("designation") or "").strip()
        play, play_src = play_chance(status, listed or None)
        card = main.get("matchup_card")
        row = {
            "player": name, "team": team, "opponent": p["opponent"], "position": pos,
            "headshot": p["headshot"],
            "proj": {k: round(v, 2) for k, v in comp.items()},
            "volume": volume,
            "ppr": ppr, "half": points(comp, HALF), "standard": points(comp, STANDARD),
            # What he is worth to a lineup this week: the points if he
            # plays, times the chance he does.
            "expected": round(ppr * play, 2),
            "play": round(play, 4),
            "play_source": play_src,
            "status": status,
            "practice": listed.get("practice") or "",
            "injury": listed.get("injury") or "",
            "td_prob": round(float(td["prob"]), 3) if td and td.get("prob") is not None else None,
            "td_quoted": bool(td and td.get("quoted")),
            "matchup": ({"grade": _grade(card), "text": card.get("text"), "rank": card.get("rank"),
                         "of": card.get("of"), "stat": card.get("stat"),
                         "applied": (card.get("model") or {}).get("applied")} if card else None),
            "script": _script(main),
            "reasons": _reasons(main),
            "missing": missing,
            "sources": sources,
        }
        sd = spread_for(pos, ppr)
        if sd is not None:
            row["sd"] = sd
        # Where eight of his weeks in ten land if he plays: the measured
        # percentiles, not a normal band (RANGE says why).
        rg = range_for(pos, ppr)
        if rg is not None:
            row["range"] = list(rg)
        if td and td.get("reasons"):
            row["td_reasons"] = list(td["reasons"])[:3]
        rd = reads.get((team, name))
        if rd:
            row["read"] = {k: rd.get(k) for k in ("read", "label", "headline", "why") if rd.get(k)}
        rl = (roles.get(name) or {}).get("reads") or {}
        flagged = {k: v for k, v in rl.items() if v.get("flag") and v.get("games_ago")}
        if flagged:
            k, v = max(flagged.items(), key=lambda kv: kv[1].get("changed") or 0)
            row["role_change"] = {"share": k, "before": v.get("before"), "after": v.get("after"),
                                  "games_ago": v.get("games_ago"), "changed": v.get("changed")}
        if team in kick:
            row["game"] = kick[team]
        out.append(row)
    out.sort(key=lambda r: (-r["expected"], r["player"]))
    return out


#: The parts a season average may stand in for when the board has no line
#: for him in that stat. Touchdowns are filled separately (his season
#: rate) and only when the touchdown model has no chance for him.
FILL = ("pass_yds", "pass_td", "pass_int", "rush_yds", "rec_yds", "receptions")


def _rescore(r: dict) -> None:
    """His points, range and spread again, after a part was added."""
    comp = r["proj"]
    r["ppr"] = points(comp)
    r["half"], r["standard"] = points(comp, HALF), points(comp, STANDARD)
    r["expected"] = round(r["ppr"] * float(r.get("play", 1.0)), 2)
    sd = spread_for(r["position"], r["ppr"])
    if sd is not None:
        r["sd"] = sd
    rg = range_for(r["position"], r["ppr"])
    if rg is not None:
        r["range"] = list(rg)


def fill_missing(players: list, means: dict | None) -> list:
    """A part the board does not project, from his season average.

    MEASURED, NOT ASSUMED (fantasyweekfit.py, 2026-10-22). Walked forward
    over 2024-2025, the board had no catches line for about 430 receiver-
    weeks that had a yards line, no yards line for about 520 tight-end
    weeks that had a catches line, and no receiving line at all for over
    half the backs: each of those players was short several PPR points,
    and a man short four points is ordered behind men he outscores. His
    own per-game average in that stat this season (the desks' means,
    fantasy_lineup.per_game) is a fact about him, not a guess, and is what
    the desks scored everything on before; it stands in where the board is
    silent, and `sources` says so for each part it filled. A part with no
    average either stays in `missing`.

    ``means``: {name: {market: per-game mean}} — the desks' `per_game`.
    Returns the same list, re-sorted by expected points."""
    if not means:
        return players
    from .backtest import _norm
    by_norm = {_norm(k): v for k, v in means.items()}
    for r in players or []:
        base = means.get(r["player"]) or by_norm.get(_norm(r["player"])) or {}
        if not base:
            continue
        filled = []
        for k in list(r.get("missing") or []):
            if k in FILL and base.get(k) is not None:
                r["proj"][k] = round(max(0.0, float(base[k])), 2)
                r["sources"][k] = "season average"
                filled.append(k)
            elif k in ("touchdowns", "rush_td") and r["position"] in TD_POSITIONS:
                rush = float(base.get("rush_td") or 0.0)
                rec = float(base.get("rec_td") or 0.0) if r["position"] != "QB" else 0.0
                if base.get("rush_td") is None and base.get("rec_td") is None:
                    continue
                r["proj"]["rush_td"], r["proj"]["rec_td"] = round(rush, 3), round(rec, 3)
                r["sources"]["rush_td"] = r["sources"]["rec_td"] = "season average"
                filled.append(k)
        if filled:
            r["missing"] = [k for k in r["missing"] if k not in filled]
            r["filled"] = filled
            _rescore(r)
    players.sort(key=lambda x: (-x["expected"], x["player"]))
    return players


# --- the week's file ---------------------------------------------------------
#: The file the NFL build writes beside its board, paid in its entirety
#: (engine/gate.PAID_FILES): every number in it is the model's.
FILE = "fantasy_week.json"


def _teams(games: list) -> dict:
    """{team: {opponent, home, implied, role, lean, date, kickoff}} off the
    board's game dicts — the script each side of each game plays."""
    out = {}
    for g in games or []:
        home, away = g.get("home"), g.get("away")
        if not home or not away:
            continue
        for team, opp, is_home in ((home, away, True), (away, home, False)):
            out[team] = {"opponent": opp, "home": is_home,
                         "date": g.get("date"), "kickoff": g.get("kickoff")}
    return out


def from_board(result: dict, tds: dict | None = None, *, ideas: dict | None = None,
               season: int | None = None, week: int | None = None, slate=None,
               built_at: str | None = None, season_means: dict | None = None) -> dict:
    """The week's fantasy file, off a priced NFL board.

    ``result`` is the board `pipeline.run_slate` returned (its prop rows,
    games and scan reads). ``tds`` is `pipeline.td_chances` of the same
    slate. ``ideas`` is the build's readings (engine/ideas.LAST["nfl"]):
    the practice reports and the role-change watch. ``slate`` gives the
    week's full injury report, every listed player, board or no board.
    ``season_means`` are the desks' per-game means (fantasy_lineup
    .per_game), for the parts the board does not project."""
    from .divisions import NFL as _NFL, canonical
    secs = (ideas or {}).get("sections") or {}
    practice = ((secs.get("practice") or {}).get("listed") or {})
    held = (secs.get("practice") or {}).get("held_out") or {}
    if held:
        practice = {k: {**v, "held_out": held} for k, v in practice.items()}
    roles = (secs.get("role") or {}).get("players") or {}
    reads: dict = {}
    for game in ((result or {}).get("scan_reads") or {}).values():
        for x in (game or {}).get("players") or []:
            if x.get("player") and x.get("team"):
                reads[(x["team"], x["player"])] = x
    games = (result or {}).get("games") or []
    players = project_players((result or {}).get("recommendations") or [], tds,
                              practice=practice, reads=reads, roles=roles, games=games)
    # The parts the board is silent on, from his season average
    # (`season_means`: the desks' fantasy_lineup.per_game).
    players = fill_missing(players, season_means)
    teams = _teams(games)
    for r in players:
        t = teams.get(r["team"])
        if t and r.get("script"):
            t.setdefault("implied", r["script"].get("team_implied"))
            t.setdefault("role", r["script"].get("role"))
            t.setdefault("lean", r["script"].get("lean"))
    listed = {}
    for g in getattr(slate, "games", None) or []:
        for i in getattr(g, "injuries", None) or []:
            if getattr(i, "player", None) and getattr(i, "status", None):
                listed[i.player] = {"team": i.team, "status": str(i.status).title()}
    # In the league's own spellings (divisions.canonical): the Rams are
    # "LA" here and "LAR" on Sleeper, and a bye list that disagreed with
    # the board about one club would sit that whole team down.
    playing = {canonical("nfl", t) for t in teams}
    byes = sorted(t for t in _NFL if playing and t not in playing)
    import datetime as _dt
    return {
        "season": season, "week": week,
        "date": (result or {}).get("date"),
        "built_at": built_at or _dt.datetime.now().isoformat(timespec="seconds"),
        "players": players,
        "teams": teams,
        "byes": byes,
        "listed": listed,
        "measured": measured(),
        "scoring": "PPR, with each component kept so a league's own rules apply",
    }


#: WHAT THE WALK-FORWARD FOUND, for the page's "how good is this" line
#: (`fantasyweekfit.py`, 2026-10-22; 2023-2025 weeks 4-17, the same
#: players scored both ways, every one who played and had an earlier game
#: that season; no usage maps in that container, which the live board
#: has). Of every two players at one position in one week, this week's
#: projection had the higher scorer ahead 72.3% of the time to the season
#: average's 71.3% (paired t 3.9 over 168 position-weeks), and missed by
#: 4.66 points a week to 4.83. Receivers (t 5.4), tight ends (t 4.3) and
#: backs (t 4.3) gained; quarterbacks were a wash (t 0.2), never behind.
#: Byes and players ruled out — which only the week reads, and which cost
#: a season-average lineup a whole starter — are not in these numbers: a
#: player who sat scored neither way.
#:
#: THE FILL (`fill_missing`) is in them: a part the board had no line for
#: him in, from his season average. Without it the pairs were 72.1%, and a
#: back was 1.45 points a week short of what he scored; with it 0.74.
#:
#: NO LEVEL CORRECTION. The projection still runs a little under what
#: players score (the board's numbers are medians and fantasy points lean
#: high: backs +0.74 a week, quarterbacks −0.82). Shifting or scaling each
#: position to fix it was tried with each season held out of its own fit:
#: it made the miss WORSE in all three (4.62 → 4.70 in 2023, 4.72 → 4.78
#: in 2024, 4.64 → 4.72 in 2025, shifted) and moved the cross-position
#: flex calls by under 0.3 points either way. Ordering is what a lineup
#: needs; RANGE carries the lean. (The touchdown count is a separate
#: question, measured on the box with the usage maps: TD_SCALE.)
MEASURED: dict = {
    "measured": "2026-10-22", "seasons": "2023-2025", "weeks": "4-17",
    "score": {
        "ALL": {"n": 10445, "weeks": 168, "pairs_week": 0.7225, "pairs_season": 0.7127,
                "pairs_gain_t": 3.93, "rank_week": 0.5435, "rank_season": 0.5225,
                "mae_week": 4.661, "mae_season": 4.828, "bias_week": 0.38, "bias_season": 0.136},
        "QB": {"n": 996, "weeks": 42, "pairs_week": 0.6113, "pairs_season": 0.6096,
               "pairs_gain_t": 0.19, "rank_week": 0.3112, "rank_season": 0.3056,
               "mae_week": 6.372, "mae_season": 6.401, "bias_week": -0.817, "bias_season": -0.052},
        "RB": {"n": 3091, "weeks": 42, "pairs_week": 0.7563, "pairs_season": 0.7483,
               "pairs_gain_t": 4.29, "rank_week": 0.6895, "rank_season": 0.6717,
               "mae_week": 4.486, "mae_season": 4.685, "bias_week": 0.739, "bias_season": 0.188},
        "WR": {"n": 3842, "weeks": 42, "pairs_week": 0.7099, "pairs_season": 0.6995,
               "pairs_gain_t": 5.39, "rank_week": 0.5801, "rank_season": 0.5523,
               "mae_week": 5.021, "mae_season": 5.199, "bias_week": 0.207, "bias_season": -0.086},
        "TE": {"n": 2516, "weeks": 42, "pairs_week": 0.7181, "pairs_season": 0.7054,
               "pairs_gain_t": 4.33, "rank_week": 0.5933, "rank_season": 0.5603,
               "mae_week": 3.65, "mae_season": 3.814, "bias_week": 0.678, "bias_season": 0.486},
    },
}


def measured() -> dict | None:
    """The measurement the page quotes: the box's saved run, else the one
    above. {measured, seasons, weeks, score}."""
    fit = saved_fit()
    if fit.get("score"):
        return {k: fit.get(k) for k in ("measured", "seasons", "weeks", "score")}
    return MEASURED or None


def publish(doc: dict, board_out) -> tuple[str, str] | None:
    """Write the week's file beside the board's public path, through the
    gate (the whole file is paid). None when there is no board path."""
    if not board_out:
        return None
    from pathlib import Path
    from . import gate
    return gate.publish(doc, Path(board_out).parent / FILE, FILE)


def summary_line(doc: dict) -> str:
    """One line for the build log."""
    ps = (doc or {}).get("players") or []
    if not ps:
        return "Fantasy week: no players projected."
    by: dict = {}
    for r in ps:
        by[r["position"]] = by.get(r["position"], 0) + 1
    held = sum(1 for r in ps if r.get("play", 1.0) < 1.0)
    top = ", ".join(f"{r['player']} {r['expected']:g}" for r in ps[:3])
    return (f"Fantasy week: {len(ps)} players projected ("
            + ", ".join(f"{n} {p}" for p, n in sorted(by.items()))
            + f"), {held} listed and weighted by their play chance, "
            + f"{len(doc.get('byes') or [])} team(s) on bye · top: {top}")


#: The NFL week turns at this hour Eastern, the morning after its last
#: game (launch.NFL_WEEK_TURNS_HOUR_ET): until then the week just played
#: is still this week.
WEEK_TURNS_HOUR_ET = 6
#: A file without game dates counts as this week's for this long.
UNDATED_DAYS = 7


def current(doc: dict, now=None) -> bool:
    """Is this file still THIS week's?

    A desk that read last week's file after its games were over would
    start players against last week's opponents and bench a man for a bye
    he already had. The board moves to the next week on its first build
    after the last game (launch._current_nfl_week); a build that has not
    happened yet must cost the desk its weekly numbers, not hand it stale
    ones. Current while its last game's date is today or later on the
    Eastern clock, turned at WEEK_TURNS_HOUR_ET; without game dates, for
    UNDATED_DAYS after it was built."""
    import datetime as _dt
    if not doc or not doc.get("players"):
        return False
    n = now or _dt.datetime.now(_dt.timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=_dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        n = n.astimezone(ZoneInfo("America/New_York"))
    except Exception:                                         # noqa: BLE001
        pass
    today = (n - _dt.timedelta(hours=WEEK_TURNS_HOUR_ET)).date()
    days = []
    for t in (doc.get("teams") or {}).values():
        try:
            days.append(_dt.date.fromisoformat(str((t or {}).get("date") or "")[:10]))
        except ValueError:
            continue
    if days:
        return max(days) >= today
    try:
        built = _dt.datetime.fromisoformat(str(doc.get("built_at") or ""))
    except ValueError:
        return False
    if built.tzinfo is None:
        built = built.replace(tzinfo=n.tzinfo)
    return _dt.timedelta(0) <= n - built <= _dt.timedelta(days=UNDATED_DAYS)


def load(path=None) -> dict:
    """The full copy of the week's file (paid), or {} when there is none."""
    import json
    from pathlib import Path
    from . import gate
    p = Path(path) if path else gate.full_board_file(FILE)
    if p is None:
        return {}
    try:
        with open(p) as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def index(doc: dict) -> dict:
    """{normalised name: row} over the week's players — the join the
    league desks make from Sleeper's, ESPN's and Yahoo's spellings."""
    from .backtest import _norm
    out: dict = {}
    for r in (doc or {}).get("players") or []:
        k = _norm(r.get("player") or "")
        if k and (k not in out or r.get("expected", 0) > out[k].get("expected", 0)):
            out[k] = r
    return out


def week_entry(row: dict, base: dict | None = None) -> dict:
    """A desk `means` entry for this week, from his week row: PPR points
    (expected, so a doubtful man counts at his chance) and every component
    scaled the same way, so a league's own scoring applies on top exactly
    as it does to a season average (fantasy_lineup.league_points)."""
    play = float(row.get("play", 1.0))
    comp = row.get("proj") or {}
    out = {"position": row.get("position") or (base or {}).get("position") or "",
           "fp_ppr": round(float(row.get("ppr") or 0.0) * play, 2),
           "_games": int((base or {}).get("_games") or 0),
           "_from_week": True, "_week": week_card(row)}
    for key in ("receptions", "rec_yds", "rush_yds", "pass_yds", "pass_td", "pass_int"):
        if key in comp:
            out[key] = round(float(comp[key]) * play, 3)
    if "rush_td" in comp:
        out["rush_td"] = round(float(comp["rush_td"]) * play, 3)
    if "rec_td" in comp:
        out["rec_td"] = round(float(comp["rec_td"]) * play, 3)
    # THE SPREAD AROUND THIS WEEK'S PROJECTION, measured on how weeks
    # land around the chain's projections (fantasyweekfit.py) — narrower
    # than his raw week-to-week spread, which also holds every matchup
    # the projection now reads. His own spread when it is not measured.
    sd = row.get("sd")
    if sd is not None:
        sd, basis = float(sd), "week"
    elif base and base.get("_sd") is not None:
        sd, basis = float(base["_sd"]), base.get("_sd_basis", "own")
    else:
        sd, basis = None, "none"
    # A MAN WHO MAY SIT is two outcomes: zero, or his week. Their mixture
    # is wider than the week alone — a questionable 15-point back with a
    # spread of 8 who plays 65% of the time swings by 9.6 — and the
    # head-to-head's win chance adds these up.
    if sd is not None and play < 1.0:
        ppr = float(row.get("ppr") or 0.0)
        sd = math.sqrt(play * sd * sd + play * (1.0 - play) * ppr * ppr)
    out["_sd"], out["_sd_basis"] = (round(sd, 3) if sd is not None else None), basis
    return out


def week_card(row: dict) -> dict:
    """What a lineup row shows about his week: opponent, the points and
    the chance he plays, the matchup grade, the script, and the reasons."""
    out = {k: row.get(k) for k in ("team", "opponent", "ppr", "expected", "play", "play_source",
                                    "status", "practice", "td_prob", "range", "missing")
           if row.get(k) not in (None, "", [])}
    g = row.get("game") or {}
    if g.get("home") and row.get("team"):
        out["home"] = g["home"] == row["team"]
    if row.get("matchup"):
        out["matchup"] = {k: row["matchup"].get(k) for k in ("grade", "text") if row["matchup"].get(k)}
    if row.get("script"):
        out["script"] = {k: row["script"].get(k) for k in ("role", "team_implied", "lean")
                         if row["script"].get(k) is not None}
    why = [s["why"] for s in (row.get("reasons") or [])[:3]]
    if row.get("read") and row["read"].get("label"):
        why.append(f"Matchup scan: {row['read']['label']}")
    rc = row.get("role_change")
    if rc and rc.get("before") is not None and rc.get("after") is not None:
        word = {"tgt": "target share", "car": "carry share", "snap": "snap share"}.get(rc.get("share"), "role")
        why.append(f"Role change: his {word} went from {rc['before']:.0%} to {rc['after']:.0%} "
                   f"{rc['games_ago']} game{'s' if rc['games_ago'] != 1 else ''} ago")
    if why:
        out["why"] = why
    return out


def _zeroed(base: dict, week: dict) -> dict:
    """His entry at zero this week, every component with it. A known zero
    has no spread: started, he adds nothing to a head-to-head's swing."""
    out = {**base, "fp_ppr": 0.0, "_from_week": True, "_week": week,
           "_sd": 0.0, "_sd_basis": "zero"}
    for key in ("receptions", "rec_yds", "rush_yds", "pass_yds", "pass_td", "pass_int",
                "rush_td", "rec_td"):
        if key in out:
            out[key] = 0.0
    return out


def with_week(means: dict, doc: dict, roster_names=None, teams: dict | None = None,
              statuses: dict | None = None) -> dict:
    """`means` with THIS WEEK in place of the season average, for every
    player the week knows something about. Returns a NEW dict.

      * ruled out by his league's own feed (Sleeper's injury status: IR,
        Out, PUP, suspended): zero, whatever else is known. The week's
        practice report never lists a man on injured reserve, so without
        this the optimiser could start one at his season average;
      * on the week's board: his projection for this week, at his chance
        to play (`week_entry`);
      * on a bye, or ruled out on the week's injury report, board or no
        board: zero this week, and the row says which;
      * anyone else keeps his season average, marked as such, so a lineup
        built partly on averages says so.

    ``roster_names`` are the names the desk will look players up by (a
    league's spellings); each is joined to the week by normalised name, so
    "DJ Moore" finds "D.J. Moore". ``teams`` maps a name to his NFL team
    where the desk knows it (Sleeper does); otherwise the season rows'
    team is used for the bye. ``statuses`` maps a name to his injury
    status on the league's platform, where it has one."""
    from .backtest import _norm
    from .divisions import canonical
    if not doc or not doc.get("players"):
        return dict(means or {})
    out = dict(means or {})
    idx = index(doc)
    byes = {canonical("nfl", t) for t in doc.get("byes") or []}
    listed = {_norm(k): v for k, v in (doc.get("listed") or {}).items()}
    names = list(roster_names) if roster_names is not None else list(out)
    for name in names:
        base = out.get(name) or {}
        k = _norm(name)
        own = str((statuses or {}).get(name) or "").strip()
        if own.upper() in OUT_STATUSES:
            out[name] = _zeroed(base, {"status": own, "expected": 0.0, "play": 0.0,
                                       "source": "league"})
            continue
        row = idx.get(k)
        if row is not None:
            out[name] = week_entry(row, base)
            continue
        team = canonical("nfl", (teams or {}).get(name) or base.get("team") or "")
        status = (listed.get(k) or {}).get("status", "")
        if team and team in byes:
            out[name] = _zeroed(base, {"bye": True, "expected": 0.0})
        elif status.upper() in OUT_STATUSES:
            out[name] = _zeroed(base, {"status": status, "expected": 0.0, "play": 0.0})
        elif base:
            out[name] = {**base, "_week": {"season_average": True}}
    return out


def free_agents(doc: dict, rostered, limit_per_pos: int = 5) -> dict:
    """The best of this week's projections nobody in the league has:
    {position: [rows]}, by expected points. ``rostered`` is every name on
    every roster in the league, in the league's spellings."""
    from .backtest import _norm
    taken = {_norm(n) for n in rostered or [] if n}
    out: dict = {}
    for r in (doc or {}).get("players") or []:
        if r.get("position") not in ("QB", "RB", "WR", "TE", "K"):
            continue
        if _norm(r.get("player") or "") in taken or r.get("play", 1.0) <= 0:
            continue
        lst = out.setdefault(r["position"], [])
        if len(lst) < limit_per_pos:
            lst.append({k: r.get(k) for k in ("player", "team", "opponent", "position", "headshot",
                                              "expected", "ppr", "play", "status", "td_prob", "range")}
                       | {"card": week_card(r)})
    return out
