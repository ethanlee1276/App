"""Do the matchup scan's reasons predict anything the model does not
already know? Measured walk-forward, before any of them moves a number.

engine/gamescan reads a game the way the Falcons @ Packers breakdown
Ethan sent does (2026-09-24) — pressure against protection, a starting
corner out, a receiver who eats zone against a zone defence, a defence
that misses tackles — and the page says none of it moves our numbers
yet. This is the test each reason has to pass first.

For every regular-season player-game from week 4 on, with three earlier
games that season:

    e = the model's expectation BEFORE the scan: his average in those
        games times the defence-versus-position step the board already
        applies (engine/defensevs.effect, at its measured transfer)
    x = the signal, from games before this one only
    y = what he did

and the signal's strength b is the least-squares answer to
``y ≈ e · (1 + a + b·x)`` — ``a`` the level (see the fit below). So a
signal is credited only with what it adds on top of the matchup the
model already reads: a pass defence that allows a lot of EPA is mostly
a defence that allows a lot of yards, which the board has priced since
2026-09-23.

Each season is held out in turn: fitted on the others, scored on it.
THE RULE (the one college's matchups were chosen by, engine/defensevs.
MODEL_STAT_CFB): a signal joins the model only where its held-out gain
is positive on average AND in all but one of the held-out seasons —
and, here, where b is at least MIN_T standard errors from zero.

MEASURED 2026-09-24, 2022-2025, 40,312 player-games (MEASURED below):
NOTHING PASSES. Not one of the six signals predicted a player's line
beyond his form and the defence-versus-position step. The page and Ask
say so; the scan is the story of a game, and none of it moves a number.

MEASURED AGAIN 2026-10-13, with six more (Ethan, after the carry and
route charts: "use this data to make better pics"): where his targets
go by depth, yards after contact allowed, the pocket split, and three
the charts made — his run direction against where the defence gives
ground, the side of the field he is thrown to against the side they
give up, and his yards after the catch against theirs. NOTHING PASSES,
and the first six re-ran within noise of their old numbers.

    python3 -m engine.scanfit --points /tmp/pts.pkl   # 2022-2025, the report
    python3 -m engine.scanfit --json out.json
"""
from __future__ import annotations

import math

from engine import defensevs as D
from engine import gamescan as G

#: (market, position group) -> (stat column, form floor)
MARKETS = {
    ("pass_yds", "QB"): ("passing_yards", 150.0),
    ("rec_yds", "WR"): ("receiving_yards", 15.0),
    ("rec_yds", "TE"): ("receiving_yards", 15.0),
    ("receptions", "WR"): ("receptions", 1.5),
    ("receptions", "TE"): ("receptions", 1.5),
    ("rush_yds", "RB"): ("rushing_yards", 15.0),
}

#: Each signal and the markets it claims to move, in the scan's words.
SIGNALS = {
    "pressure": {"markets": [("pass_yds", "QB")],
                 "says": "his line against their pass rush (sacks and hits per dropback, both sides)"},
    "pass_defense": {"markets": [("pass_yds", "QB"), ("rec_yds", "WR"), ("rec_yds", "TE"),
                                 ("receptions", "WR"), ("receptions", "TE")],
                     "says": "their pass defence's opponent-adjusted EPA per dropback"},
    "run_defense": {"markets": [("rush_yds", "RB")],
                    "says": "their run defence's opponent-adjusted EPA per carry"},
    "missed_tackles": {"markets": [("rush_yds", "RB")],
                       "says": "their missed-tackle rate (PFR), against the league's"},
    "cb_out": {"markets": [("rec_yds", "WR"), ("receptions", "WR")],
               "says": "starting corners missing from their side (≥70% of snaps before)"},
    "zone_fit": {"markets": [("rec_yds", "WR"), ("receptions", "WR")],
                 "says": "his yards per target vs zone over vs man (last season) × their zone rate over the league's"},
    # MEASURED 2026-10-13 (below): the three that waited on the box's run,
    # and the three the carry and route charts made the same day.
    # 2026-10-08 (the Bucs @ Cowboys research): the defence's yards a
    # target in HIS biggest air-yard zone (short / intermediate / deep),
    # against the league's.
    "depth": {"markets": [("rec_yds", "WR"), ("rec_yds", "TE"), ("receptions", "WR"), ("receptions", "TE")],
              "says": "their yards a target allowed in his biggest air-yard zone (short / intermediate / deep), "
                      "over the league's"},
    # 2026-10-08, Ethan: "seems like it should be free data". Two more off
    # the free tables: what the defence allows after contact (PFR's rows,
    # summed by opponent), and the passer's own clean-vs-hit gap against
    # how often this defence hits him (the play-by-play).
    "yac_allowed": {"markets": [("rush_yds", "RB")],
                    "says": "their yards after contact allowed a carry (PFR, by opponent), over the league's"},
    "pocket_fit": {"markets": [("pass_yds", "QB")],
                   "says": "his completion rate not hit minus hit (play-by-play) × their hits-and-sacks rate "
                           "over the league's"},
    # 2026-10-13, Ethan, after the carry and route charts: "is there more
    # features or tools … to get more accurate data and able to use this
    # data to make better pics". Three matchups the charts' own columns
    # make. Each is the INTERACTION alone — where HE goes against where
    # THEY give ground, over their overall: a defence that is bad
    # everywhere is the defence-versus-position step the board already
    # takes, and x is zero for it, as it is for a player whose mix is the
    # league's.
    "run_direction": {"markets": [("rush_yds", "RB")],
                      "says": "his inside/outside run mix (the play-by-play's run gap) × their yards a carry "
                              "by direction, over their overall"},
    "side_fit": {"markets": [("rec_yds", "WR"), ("rec_yds", "TE"), ("receptions", "WR"), ("receptions", "TE")],
                 "says": "his left/middle/right target mix × their yards a target by side of the field, "
                         "over their overall"},
    "yac_fit": {"markets": [("rec_yds", "WR"), ("rec_yds", "TE")],
                "says": "his share of yards after the catch over the league's × their yards after the "
                        "catch a catch over the league's"},
}

#: Signals written but NOT YET MEASURED: collected and reported by the
#: same run, kept out of SIGNALS (every signal there has its MEASURED
#: line, and the page's sentence rests on that) until a run puts theirs
#: in MEASURED. Until then the card shows the fact as "shown, not in the
#: number", which is exactly what it is. Empty since 2026-10-13: the six
#: that were here were measured and moved into SIGNALS.
PENDING: dict = {}

#: The run behind the page's sentence, 2026-09-24: (b, SE, held-out gain
#: per season 2022 / 2023 / 2024 / 2025, mean). Re-run before changing
#: what the page says; a signal moves a number only when it passes.
MEASURED = {
    ("pressure", "pass_yds", "QB"): (-0.050, 0.039, (+0.01, +0.24, -0.09, +0.09), +0.062),
    ("pass_defense", "pass_yds", "QB"): (-0.002, 0.119, (-0.03, -0.29, -0.21, -0.66), -0.296),
    ("pass_defense", "rec_yds", "WR"): (-0.098, 0.122, (+0.02, -0.02, +0.02, -0.07), -0.014),
    ("pass_defense", "rec_yds", "TE"): (+0.437, 0.205, (+0.53, -2.69, +0.36, +0.44), -0.339),
    ("pass_defense", "receptions", "WR"): (-0.096, 0.103, (+0.01, +0.01, +0.00, -0.21), -0.047),
    ("pass_defense", "receptions", "TE"): (+0.156, 0.170, (+0.09, -1.54, +0.06, -0.03), -0.354),
    ("run_defense", "rush_yds", "RB"): (+0.298, 0.206, (-0.18, +0.16, +0.16, -0.20), -0.016),
    ("missed_tackles", "rush_yds", "RB"): (+0.007, 0.070, (-0.04, -0.06, -0.64, -0.16), -0.224),
    # Receivers did a shade BETTER with a starting corner out (actual over
    # expected 0.965 against 0.954, n 1,116) — inside the noise either way.
    ("cb_out", "rec_yds", "WR"): (-0.020, 0.020, (-0.04, -0.35, -0.14, -0.15), -0.170),
    ("cb_out", "receptions", "WR"): (-0.014, 0.017, (+0.00, +0.01, -0.05, +0.01), -0.008),
    # The Falcons @ Packers breakdown's centrepiece ("9.1 yards a target
    # against zone, 6.2 against man"): flat, t 0.1.
    ("zone_fit", "rec_yds", "WR"): (-0.018, 0.376, (-0.01, -0.03, +0.00, -0.06), -0.026),
    ("zone_fit", "receptions", "WR"): (+0.032, 0.301, (-0.07, -0.01, -0.00, -0.18), -0.065),
    # 2026-10-13, run in the sandbox off the same nflverse files the box
    # reads (`python3 -m engine.scanfit`, 81,905 samples, 2022-2025). The
    # six above re-ran within noise of their 2026-09-24 numbers — cb_out
    # to the digit — so this run is the box's run. Nothing passes again:
    # where a receiver's targets go by depth (Bucs @ Cowboys research),
    # yards after contact allowed, the pocket split, and the carry and
    # route charts' three — run direction, side of the field, yards after
    # the catch. Each t is under 2 and every mean held-out gain is below 0.
    ("depth", "rec_yds", "TE"): (+0.070, 0.045, (+0.28, -1.48, +0.17, +0.26), -0.191),
    ("depth", "rec_yds", "WR"): (+0.006, 0.019, (-0.03, -0.05, -0.01, -0.01), -0.025),
    ("depth", "receptions", "TE"): (+0.011, 0.038, (+0.00, -0.39, -0.04, +0.01), -0.105),
    ("depth", "receptions", "WR"): (-0.006, 0.019, (-0.00, -0.00, -0.03, -0.07), -0.026),
    ("yac_allowed", "rush_yds", "RB"): (-0.001, 0.035, (-0.08, -0.11, -0.11, -0.13), -0.107),
    ("pocket_fit", "pass_yds", "QB"): (-0.238, 0.251, (-0.12, -0.20, -0.24, -0.07), -0.161),
    ("run_direction", "rush_yds", "RB"): (+0.158, 0.768, (+0.00, -0.01, -0.12, -0.12), -0.060),
    ("side_fit", "rec_yds", "WR"): (+0.057, 0.786, (-0.03, -0.18, -0.12, -0.09), -0.104),
    ("side_fit", "rec_yds", "TE"): (+0.074, 1.191, (+0.00, -0.03, -0.09, -0.02), -0.037),
    ("side_fit", "receptions", "WR"): (-0.131, 0.651, (-0.09, -0.06, -0.05, -0.03), -0.059),
    ("side_fit", "receptions", "TE"): (+0.895, 0.964, (+0.09, -0.20, +0.05, -0.09), -0.038),
    ("yac_fit", "rec_yds", "WR"): (+0.470, 0.529, (+0.03, -0.01, +0.02, -0.43), -0.096),
    ("yac_fit", "rec_yds", "TE"): (-0.077, 1.404, (-0.21, -0.01, -0.02, -0.15), -0.096),
}

MIN_PRIOR_GAMES = 3
FIRST_WEEK = 4
QB_MIN_ATTEMPTS = 20.0
#: A corner "starts" at this share of the defensive snaps…
CB_START_PCT = 0.70
#: …in this many of the team's last three games before this one.
CB_START_OF_LAST3 = 2
#: Last-season targets a receiver needs against each look for his split.
ZONE_MIN_TGTS, MAN_MIN_TGTS = 20, 10
#: Games of this season that count as much as last season's rate.
PRIOR_GAMES = 4.0


def _f(v, default=0.0):
    try:
        if v in (None, "", "NA"):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _reg(r) -> bool:
    return (r.get("season_type") or r.get("game_type") or "REG") == "REG"


# ── the signals, each from games before the week only ─────────────────────


def unit_signals(units_now: list[dict], units_prior: list[dict] | None, wk: int) -> dict:
    """{team: {"pass_defense", "run_defense", "def_pressure", "off_pressure"}}
    — the scan's own ratings (gamescan.ratings_from_rows) as of week ``wk``,
    each centred on the league so 0 is an average unit."""
    now = [u for u in units_now if int(u["period"]) < wk]
    if not now:
        return {}
    r = G.ratings_from_rows(now, units_prior)
    val = lambda t, side, u: ((r[t].get(side) or {}).get(u) or {}).get("value")   # noqa: E731
    def mean(side, u):
        xs = [val(t, side, u) for t in r if val(t, side, u) is not None]
        return sum(xs) / len(xs) if xs else None
    m = {k: mean(*k) for k in (("def", "passing"), ("def", "rushing"),
                               ("def", "pressure"), ("off", "pressure"),
                               ("def", "short"), ("def", "mid"), ("def", "deep"))}
    out = {}
    for t in r:
        row = {}
        for (side, u), name in ((("def", "passing"), "pass_defense"),
                                (("def", "rushing"), "run_defense"),
                                (("def", "short"), "def_short"),
                                (("def", "mid"), "def_mid"),
                                (("def", "deep"), "def_deep")):
            v = val(t, side, u)
            if v is not None and m[(side, u)] is not None:
                row[name] = v - m[(side, u)]
        for (side, u), name in ((("def", "pressure"), "def_pressure"),
                                (("off", "pressure"), "off_pressure")):
            v = val(t, side, u)
            if v is not None and m[(side, u)]:
                row[name] = v / m[(side, u)] - 1.0
        out[t] = row
    return out


def tackle_rates(pfr_rows: list[dict]) -> dict:
    """{team: {week: [missed, attempts]}} from PFR's weekly defender rows."""
    out: dict = {}
    for r in pfr_rows:
        if not _reg(r):
            continue
        c = out.setdefault(r.get("team") or "", {}).setdefault(int(_f(r.get("week"))), [0.0, 0.0])
        m = _f(r.get("def_missed_tackles"))
        c[0] += m
        c[1] += _f(r.get("def_tackles_combined")) + m
    return out


def missed_signal(now: dict, prior: dict | None, wk: int) -> dict:
    """{team: missed-tackle rate over the league's, minus 1} before ``wk``,
    blended with last season's by games."""
    def season(t, table, upto=None):
        wks = {w: v for w, v in (table.get(t) or {}).items() if upto is None or w < upto}
        m, a = sum(v[0] for v in wks.values()), sum(v[1] for v in wks.values())
        return (m / a if a else None), len(wks)
    rates, league_m, league_a = {}, 0.0, 0.0
    for t, wks in now.items():
        for w, (m, a) in wks.items():
            if w < wk:
                league_m += m
                league_a += a
    if not league_a:
        return {}
    league = league_m / league_a
    for t in now:
        cur, g = season(t, now, wk)
        if cur is None or g < MIN_PRIOR_GAMES:
            continue
        p = season(t, prior)[0] if prior else None
        rate = cur if p is None else (g * cur + PRIOR_GAMES * p) / (g + PRIOR_GAMES)
        rates[t] = rate / league - 1.0
    return rates


def corner_snaps(snap_rows: list[dict]) -> dict:
    """{team: {week: {player: defense share}}} for corners."""
    out: dict = {}
    for r in snap_rows:
        if not _reg(r) or (r.get("position") or "") != "CB":
            continue
        out.setdefault(r.get("team") or "", {}).setdefault(int(_f(r.get("week"))), {})[
            r.get("player") or ""] = _f(r.get("defense_pct"))
    return out


def corners_out(table: dict, team: str, wk: int) -> int | None:
    """Starting corners (CB_START_PCT of the snaps in CB_START_OF_LAST3 of
    the team's last three games) who did not play in week ``wk``; None
    when the team has no game that week or too few before it."""
    weeks = table.get(team) or {}
    if wk not in weeks:
        return None
    last3 = sorted(w for w in weeks if w < wk)[-3:]
    if len(last3) < 3:
        return None
    starters = {p for p in {q for w in last3 for q in weeks[w]}
                if sum(weeks[w].get(p, 0.0) >= CB_START_PCT for w in last3) >= CB_START_OF_LAST3}
    return sum(1 for p in starters if weeks[wk].get(p, 0.0) <= 0.0)


def _week_of(game_id: str) -> int:
    parts = (game_id or "").split("_")
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0


def zone_rates(part_rows: list[dict], wk: int) -> dict:
    """{defence: zone share} from this season's charting before ``wk``, and the league's."""
    from engine.sources import nflscheme as N
    got = N.scheme([r for r in part_rows if _week_of(r.get("nflverse_game_id") or "") < wk])
    return {t: v["zone"] for t, v in got.items()}


#: Targets with air yards before his zone counts (engine/gamescan.DEPTH_MIN_TGTS).
DEPTH_MIN_TGTS = 10


def depth_zones(plays: list[dict]) -> dict:
    """{receiver (pbp name): [(week, zone)]} from a season's targeted plays,
    for `main_zone` to read strictly before a week."""
    from engine.sources.nflpbp import depth_zone
    out: dict = {}
    for p in plays:
        name, araw = p.get("receiver_player_name"), p.get("air_yards")
        if not name or araw in (None, "", "NA"):
            continue
        try:
            wk = int(_f(p.get("week")))
        except ValueError:
            continue
        out.setdefault(str(name), []).append((wk, depth_zone(_f(araw))))
    return out


def main_zone(zones: dict, name: str, wk: int):
    """His biggest air-yard zone over the targets before ``wk``, or None
    under DEPTH_MIN_TGTS of them."""
    counts = {"short": 0, "mid": 0, "deep": 0}
    for w, z in zones.get(name) or ():
        if w < wk:
            counts[z] += 1
    if sum(counts.values()) < DEPTH_MIN_TGTS:
        return None
    return max(("short", "mid", "deep"), key=lambda z: (counts[z], z == "short"))


#: Carries a defence must have faced before its contact number is a
#: signal, and the passer's throws (not hit / hit) before his gap is.
CONTACT_MIN_CARRIES = 60
POCKET_MIN = (50, 10)


def contact_signal(pfr_rush: list[dict], wk: int) -> dict:
    """{defence: yards after contact allowed a carry − the league's} from
    PFR rushing rows strictly before ``wk``."""
    from engine.sources.nflscheme import run_contact
    rows = [r for r in pfr_rush if _f(r.get("week")) < wk]
    got = run_contact(rows, CONTACT_MIN_CARRIES)
    if not got:
        return {}
    league = sum(v["yac_pc"] for v in got.values()) / len(got)
    return {t: v["yac_pc"] - league for t, v in got.items()}


def pocket_gap(passes: list[dict], name: str, wk: int):
    """His completion rate not hit minus hit over the throws before
    ``wk``, or None under POCKET_MIN of either."""
    ac = cc = ah = ch = 0
    for p in passes:
        if p.get("passer_player_name") != name or _f(p.get("week")) >= wk:
            continue
        if _f(p.get("qb_hit")) == 1:
            ah += 1
            ch += _f(p.get("complete_pass")) == 1
        else:
            ac += 1
            cc += _f(p.get("complete_pass")) == 1
    if ac < POCKET_MIN[0] or ah < POCKET_MIN[1]:
        return None
    return cc / ac - ch / ah


def zone_splits(part_prev: list[dict], plays_prev: list[dict]) -> dict:
    """{receiver: relative split} from last season: (yards per target vs
    zone − vs man) over his yards per target, where both samples clear."""
    from engine.sources import nflscheme as N
    merged: dict = {}
    for (_team, name), c in N.receiver_splits(part_prev, plays_prev).items():
        m = merged.setdefault(name, {"zone": [0, 0.0], "man": [0, 0.0]})
        for k in ("zone", "man"):
            m[k][0] += c[k][0]
            m[k][1] += c[k][1]
    out = {}
    for name, c in merged.items():
        tz, yz = c["zone"]
        tm, ym = c["man"]
        if tz < ZONE_MIN_TGTS or tm < MAN_MIN_TGTS:
            continue
        allt = (yz + ym) / (tz + tm)
        if allt > 0:
            out[name] = (yz / tz - ym / tm) / allt
    return out


# ── the charts' matchups (2026-10-13) ─────────────────────────────────────
#
# Carries a defence must have faced in a direction (targets to a side,
# catches for yards after the catch) before its own rate counts at full
# weight: under that it is pulled toward the league's, by count.
DIR_SHRINK, SIDE_SHRINK, YAC_SHRINK = 40.0, 30.0, 40.0
#: His carries / targets / catches before his mix is a signal at all,
#: and how hard a short history leans on the league's mix.
DIR_MIN, SIDE_MIN, YAC_MIN = 12, 12, 8
MIX_SHRINK = 8.0


def run_class(location, gap) -> str:
    """"in" (a guard or the middle) or "out" (a tackle or an end), from
    the play-by-play's run_location and run_gap; "" when it has neither."""
    loc = str(location or "").strip().lower()
    gp = str(gap or "").strip().lower()
    if loc == "middle" or gp == "guard":
        return "in"
    if gp in ("tackle", "end"):
        return "out"
    return ""


def direction_table(runs: list[dict]) -> dict:
    """{"def": {defence: [(week, class, yards)]}, "mine": {rusher id: [(week, class)]}}."""
    out: dict = {"def": {}, "mine": {}}
    for p in runs:
        c = run_class(p.get("run_location"), p.get("run_gap"))
        wk = int(_f(p.get("week")))
        if not c or not wk:
            continue
        y = _f(p.get("rushing_yards"), _f(p.get("yards_gained")))
        out["def"].setdefault(str(p.get("defteam") or ""), []).append((wk, c, y))
        out["mine"].setdefault(str(p.get("rusher_player_id") or ""), []).append((wk, c))
    return out


SIDES = {"left": "L", "middle": "M", "right": "R"}


def side_table(plays: list[dict]) -> dict:
    """{"def": {defence: [(week, side, yards)]}, "mine": {receiver id: [(week, side)]}} —
    a target's yards are the catch's, nothing on a miss."""
    out: dict = {"def": {}, "mine": {}}
    for p in plays:
        sd = SIDES.get(str(p.get("pass_location") or "").strip().lower(), "")
        wk = int(_f(p.get("week")))
        if not sd or not wk:
            continue
        y = _f(p.get("yards_gained")) if _f(p.get("complete_pass")) == 1 else 0.0
        out["def"].setdefault(str(p.get("defteam") or ""), []).append((wk, sd, y))
        out["mine"].setdefault(str(p.get("receiver_player_id") or ""), []).append((wk, sd))
    return out


def yac_table(plays: list[dict]) -> dict:
    """{"def": {defence: [(week, yac)]}, "mine": {receiver id: [(week, yac, yards)]}}, per catch."""
    out: dict = {"def": {}, "mine": {}}
    for p in plays:
        if _f(p.get("complete_pass")) != 1 or p.get("yards_after_catch") in (None, "", "NA"):
            continue
        wk = int(_f(p.get("week")))
        if not wk:
            continue
        yac, y = _f(p.get("yards_after_catch")), _f(p.get("yards_gained"))
        out["def"].setdefault(str(p.get("defteam") or ""), []).append((wk, yac))
        out["mine"].setdefault(str(p.get("receiver_player_id") or ""), []).append((wk, yac, y))
    return out


def class_rel(table: dict, wk: int, shrink: float) -> tuple[dict, dict]:
    """({defence: {class: its rate over the league's}}, {class: the league's share})
    from the rows strictly before ``wk`` — a defence's rate pulled toward
    the league's by ``shrink`` rows."""
    tot: dict = {}
    per: dict = {}
    for team, rows in table.items():
        for w, c, v in rows:
            if w >= wk:
                continue
            t, m = tot.setdefault(c, [0, 0.0]), per.setdefault(team, {}).setdefault(c, [0, 0.0])
            t[0] += 1
            t[1] += v
            m[0] += 1
            m[1] += v
    n_all = sum(n for n, _s in tot.values())
    if not n_all:
        return {}, {}
    league = {c: s / n for c, (n, s) in tot.items() if n and s > 0}
    weights = {c: n / n_all for c, (n, _s) in tot.items() if c in league}
    rel = {team: {c: ((cs.get(c, [0, 0.0])[1] + shrink * lg) / (cs.get(c, [0, 0.0])[0] + shrink)) / lg
                  for c, lg in league.items()}
           for team, cs in per.items()}
    return rel, weights


def mix_fit(mine: list, wk: int, rel: dict | None, weights: dict, min_n: int):
    """Where he goes against where they give ground: Σ his share of a
    class × their rate there, over their rate at the league's mix, minus
    one. Zero when his mix is the league's, or when they are the same in
    every class. None under ``min_n`` of his rows before ``wk``."""
    if not rel or not weights:
        return None
    counts: dict = {}
    for w, c in mine or ():
        if w < wk and c in weights:
            counts[c] = counts.get(c, 0) + 1
    n = sum(counts.values())
    if n < min_n:
        return None
    share = {c: (counts.get(c, 0) + MIX_SHRINK * weights[c]) / (n + MIX_SHRINK) for c in weights}
    overall = sum(weights[c] * rel.get(c, 1.0) for c in weights)
    his = sum(share[c] * rel.get(c, 1.0) for c in weights)
    return his / overall - 1.0 if overall > 0 else None


def yac_rel(table: dict, wk: int) -> tuple[dict, float | None, float | None]:
    """({defence: its yards after the catch a catch over the league's,
    minus one}, the league's per catch, the league's share of receiving
    yards that came after the catch) before ``wk``."""
    n = s = 0.0
    per: dict = {}
    for team, rows in table["def"].items():
        for w, yac in rows:
            if w < wk:
                c = per.setdefault(team, [0, 0.0])
                c[0] += 1
                c[1] += yac
                n += 1
                s += yac
    yds = sum(y for rows in table["mine"].values() for w, _yac, y in rows if w < wk)
    if not n or s <= 0 or yds <= 0:
        return {}, None, None
    lg = s / n
    rel = {t: (c[1] + YAC_SHRINK * lg) / (c[0] + YAC_SHRINK) / lg - 1.0 for t, c in per.items()}
    return rel, lg, s / yds


def yac_lean(rows: list, wk: int, league_share: float | None):
    """His share of receiving yards after the catch over the league's, from
    his catches before ``wk``; None under YAC_MIN of them."""
    if league_share is None:
        return None
    mine = [(yac, y) for w, yac, y in rows or () if w < wk]
    yds = sum(y for _yac, y in mine)
    if len(mine) < YAC_MIN or yds <= 0:
        return None
    return sum(yac for yac, _y in mine) / yds - league_share


# ── the samples ────────────────────────────────────────────────────────────


def samples(season: dict, prior: dict | None) -> dict:
    """{(signal, market, group): [(e, x, y, season)]} for one season.

    ``season`` and ``prior`` are `load_season` dicts (prior may be None)."""
    yr = season["season"]
    reg = [r for r in season["weekly"] if D._regular(r)]
    dvp_prior = D.ratings([r for r in prior["weekly"] if D._regular(r)], 99) if prior else None
    tackles = tackle_rates(season["pfr"])
    tackles_prior = tackle_rates(prior["pfr"]) if prior else None
    cbs = corner_snaps(season["snaps"])
    splits = zone_splits(prior["part"], prior["plays"]) if prior else {}
    depth = depth_zones(season["plays"])
    passes = season.get("passes") or []
    pfr_rush = season.get("pfr_rush") or []
    mats = {"dir": direction_table(season.get("runs") or []), "side": side_table(season["plays"]),
            "yac": yac_table(season["plays"])}
    by_player: dict = {}
    for r in reg:
        g = D.GROUP_OF.get(str(r.get("position") or "").upper())
        if g:
            by_player.setdefault(str(r.get("player_id") or r.get("player_display_name")), []).append((D._week(r), g, r))
    cache: dict = {}

    def week(wk):
        if wk not in cache:
            zr = zone_rates(season["part"], wk)
            cache[wk] = {
                "dvp": D.ratings(reg, wk, D.SHRINK_GAMES, dvp_prior),
                "units": unit_signals(season["units"], prior["units"] if prior else None, wk),
                "missed": missed_signal(tackles, tackles_prior, wk),
                "zone": zr, "zone_league": (sum(zr.values()) / len(zr)) if zr else None,
                "contact": contact_signal(pfr_rush, wk),
                "dir": class_rel(mats["dir"]["def"], wk, DIR_SHRINK),
                "side": class_rel(mats["side"]["def"], wk, SIDE_SHRINK),
                "yac": yac_rel(mats["yac"], wk),
            }
        return cache[wk]

    out: dict = {}
    for logs in by_player.values():
        logs.sort(key=lambda x: x[0])
        for i, (wk, g, r) in enumerate(logs):
            if wk < FIRST_WEEK or i < MIN_PRIOR_GAMES:
                continue
            team, opp = str(r.get("team") or r.get("recent_team") or ""), str(r.get("opponent_team") or "")
            prev = [x[2] for x in logs[:i]]
            if g == "QB" and sum(_f(p.get("attempts")) for p in prev) / len(prev) < QB_MIN_ATTEMPTS:
                continue
            W = week(wk)
            for name, sig in {**SIGNALS, **PENDING}.items():
                for market, grp in sig["markets"]:
                    if grp != g:
                        continue
                    col, floor = MARKETS[(market, grp)]
                    e0 = sum(_f(p.get(col)) for p in prev) / len(prev)
                    if e0 < floor:
                        continue
                    mult, _why, _card = D.effect(opp, (W["dvp"] or {}).get(opp) or {}, g, market)
                    x = signal(name, W, team, opp, r, cbs, splits, wk, depth, passes, mats)
                    if x is None:
                        continue
                    out.setdefault((name, market, g), []).append((e0 * mult, x, _f(r.get(col)), yr))
    return out


def signal(name, W, team, opp, r, cbs, splits, wk, depth=None, passes=None, mats=None):
    u = W.get("units") or {}
    pid = str(r.get("player_id") or "")
    if name in ("run_direction", "side_fit"):
        key, floor = ("dir", DIR_MIN) if name == "run_direction" else ("side", SIDE_MIN)
        rel, weights = W.get(key) or ({}, {})
        return mix_fit(((mats or {}).get(key) or {}).get("mine", {}).get(pid), wk, rel.get(opp), weights, floor)
    if name == "yac_fit":
        rel, _per_catch, share = W.get("yac") or ({}, None, None)
        lean = yac_lean(((mats or {}).get("yac") or {}).get("mine", {}).get(pid), wk, share)
        d = rel.get(opp)
        return None if lean is None or d is None else lean * d
    if name == "depth":
        zone = main_zone(depth or {}, str(r.get("player_name") or ""), wk)
        return None if zone is None else (u.get(opp) or {}).get(f"def_{zone}")
    if name == "yac_allowed":
        return (W.get("contact") or {}).get(opp)
    if name == "pocket_fit":
        gap = pocket_gap(passes or [], str(r.get("player_name") or ""), wk)
        pr = (u.get(opp) or {}).get("def_pressure")
        return None if gap is None or pr is None else gap * pr
    if name == "pressure":
        a, b = (u.get(opp) or {}).get("def_pressure"), (u.get(team) or {}).get("off_pressure")
        return None if a is None or b is None else a + b
    if name == "pass_defense":
        return (u.get(opp) or {}).get("pass_defense")
    if name == "run_defense":
        return (u.get(opp) or {}).get("run_defense")
    if name == "missed_tackles":
        return W["missed"].get(opp)
    if name == "cb_out":
        return corners_out(cbs, opp, wk)
    if name == "zone_fit":
        rel = splits.get(str(r.get("player_name") or ""))
        z = W["zone"].get(opp)
        if rel is None or z is None or W["zone_league"] is None:
            return None
        return rel * (z - W["zone_league"])
    return None


# ── the fit ────────────────────────────────────────────────────────────────
#
# WITH A LEVEL TERM. A player's recent average overstates his next game on
# the whole (he was measured because he cleared a floor; regression to the
# mean does the rest — about 4½% in these samples), and a signal that is
# never negative, like a corner being out, would soak that bias up and
# look like an effect. So every fit carries ``a``, the level, and the
# signal is judged against a model that has it too:
#
#     base:  y ≈ e · (1 + a0)
#     full:  y ≈ e · (1 + a + b·x)


def _level(pts) -> float:
    den = sum(e * e for e, *_ in pts)
    return sum(e * (y - e) for e, _x, y, *_ in pts) / den if den else 0.0


def fit(pts: list[tuple]) -> dict:
    """a, b and b's standard error from ``y − e = a·e + b·e·x``."""
    if len(pts) < 30:
        return {"a": 0.0, "b": 0.0, "se": None, "n": len(pts)}
    suu = sum(e * e for e, *_ in pts)
    svv = sum((e * x) ** 2 for e, x, *_ in pts)
    suv = sum(e * e * x for e, x, *_ in pts)
    sur = sum(e * (y - e) for e, _x, y, *_ in pts)
    svr = sum(e * x * (y - e) for e, x, y, *_ in pts)
    det = suu * svv - suv * suv
    if det <= 0:
        return {"a": round(_level(pts), 4), "b": 0.0, "se": None, "n": len(pts)}
    a = (svv * sur - suv * svr) / det
    b = (suu * svr - suv * sur) / det
    resid = sum((y - e * (1 + a + b * x)) ** 2 for e, x, y, *_ in pts) / max(1, len(pts) - 2)
    return {"a": round(a, 4), "b": round(b, 4), "se": round(math.sqrt(resid * suu / det), 4),
            "n": len(pts)}


def gain(pts: list[tuple], full: dict, a0: float) -> float:
    """Share of the base model's squared error the signal removes."""
    base = sum((y - e * (1 + a0)) ** 2 for e, _x, y, *_ in pts)
    got = sum((y - e * (1 + full["a"] + full["b"] * x)) ** 2 for e, x, y, *_ in pts)
    return (base - got) / base if base > 0 else 0.0


#: THE RULE, and the bar beside it: held-out gain positive on average and
#: in all but one season, and b at least this many standard errors from
#: zero on every season together — a b inside its own error bar is noise
#: the model would be carrying.
MIN_T = 2.0


def study(points: dict) -> dict:
    """Per (signal, market, group): the fit on every season, then each
    season held out in turn, and whether it passes."""
    res = {}
    for key, pts in sorted(points.items()):
        seasons = sorted({p[3] for p in pts})
        held = {}
        for s in seasons:
            train = [p for p in pts if p[3] != s]
            test = [p for p in pts if p[3] == s]
            held[s] = round(gain(test, fit(train), _level(train)), 5) if test and train else None
        vals = [v for v in held.values() if v is not None]
        mean = sum(vals) / len(vals) if vals else 0.0
        positive = sum(v > 0 for v in vals)
        whole = fit(pts)
        t = abs(whole["b"]) / whole["se"] if whole.get("se") else 0.0
        xs = [p[1] for p in pts]
        mx = sum(xs) / len(xs) if xs else 0.0
        sd = math.sqrt(sum((x - mx) ** 2 for x in xs) / len(xs)) if xs else 0.0
        row = {**whole, "t": round(t, 2), "x_sd": round(sd, 4),
               "per_sd": round(whole["b"] * sd, 4),
               "held_out": held, "mean_gain": round(mean, 5),
               "passes": (len(vals) >= 3 and mean > 0 and positive >= len(vals) - 1 and t >= MIN_T),
               "exposed": sum(1 for p in pts if p[1])}
        if key[0] == "cb_out":
            on = [p for p in pts if p[1] > 0]
            off = [p for p in pts if p[1] == 0]
            ratio = lambda ps: (sum(p[2] for p in ps) / sum(p[0] for p in ps)) if ps and sum(p[0] for p in ps) else None  # noqa: E731
            row["actual_over_expected"] = {"corner_out": ratio(on), "none_out": ratio(off), "n_out": len(on)}
        res[key] = row
    return res


def report(res: dict) -> str:
    out = ["Matchup-scan signals, on top of the board's own matchup step (held out a season at a time)"]
    for (name, market, grp), r in res.items():
        se = f" ± {r['se']:.3f}" if r.get("se") is not None else ""
        held = "  ".join(f"{s} {100 * v:+.2f}%" for s, v in r["held_out"].items() if v is not None)
        out.append(f"  {name:<15} {market:<10} {grp:<3} b = {r['b']:+.3f}{se} (t {r['t']:.1f})  "
                   f"n {r['n']:>6}   1 SD moves {100 * r['per_sd']:+.1f}%   held out {held}   "
                   f"mean {100 * r['mean_gain']:+.3f}%   {'PASSES' if r['passes'] else 'fails'}")
        if r.get("actual_over_expected"):
            a = r["actual_over_expected"]
            f = lambda v: "—" if v is None else f"{v:.3f}"            # noqa: E731
            out.append(f"      actual / expected: a starter out {f(a['corner_out'])} (n {a['n_out']}), "
                       f"none out {f(a['none_out'])}")
    return "\n".join(out)


# ── loading ────────────────────────────────────────────────────────────────


RECV_COLS = ("game_id", "play_id", "receiver_player_name", "yards_gained", "complete_pass",
             "air_yards", "week", "receiver_player_id", "pass_location", "yards_after_catch")
#: The carry chart's columns (engine/carries), for run_direction.
RUN_COLS = ("rusher_player_id", "run_location", "run_gap", "rushing_yards", "qb_scramble")
PASS_COLS = ("passer_player_name", "week", "qb_hit", "complete_pass")


def load_season(yr: int) -> dict:
    """Everything one season's samples read, slimmed as it is read."""
    from engine.sources import nflpbp, nflscheme as N, nflverse as NV
    from engine.sources.nflunits import UNIT_COLS, Units
    units = Units()
    plays, passes, runs = [], [], []
    for r in nflpbp.load_pbp_rows(yr, columns=tuple(UNIT_COLS) + RECV_COLS + PASS_COLS + RUN_COLS):
        units.add(r)
        if r.get("season_type", "REG") != "REG":
            continue
        if r.get("receiver_player_name"):
            plays.append({k: r.get(k) for k in RECV_COLS + ("posteam", "defteam")})
        if r.get("play_type") == "run" and r.get("rusher_player_id") and _f(r.get("qb_scramble")) != 1:
            runs.append({k: r.get(k) for k in ("week", "defteam", "rusher_player_id", "run_location",
                                               "run_gap", "rushing_yards", "yards_gained")})
        if r.get("passer_player_name") and r.get("play_type") == "pass" and _f(r.get("sack")) != 1:
            passes.append({k: r.get(k) for k in PASS_COLS})
    keep_part = ("nflverse_game_id", "play_id", "possession_team", "defense_man_zone_type",
                 "defense_coverage_type", "number_of_pass_rushers", "was_pressure")
    part = [{k: r.get(k) for k in keep_part} for r in N.load_participation(yr, ttl=10 ** 9)
            if r.get("defense_man_zone_type")]
    pfr = [{k: r.get(k) for k in ("team", "week", "game_type", "def_missed_tackles", "def_tackles_combined")}
           for r in N.load_pfr_def(yr, ttl=10 ** 9)]
    pfr_rush = [{k: r.get(k) for k in ("team", "opponent", "week", "game_type", "carries",
                                       "rushing_yards_before_contact", "rushing_yards_after_contact",
                                       "rushing_broken_tackles")}
                for r in N.load_pfr_rush(yr, ttl=10 ** 9)]
    snaps = [{k: r.get(k) for k in ("team", "week", "game_type", "player", "position", "defense_pct")}
             for r in NV.load_snap_counts(yr)]
    return {"season": yr, "weekly": NV.load_weekly_stats(yr), "units": units.rows(yr),
            "plays": plays, "passes": passes, "runs": runs, "part": part, "pfr": pfr,
            "pfr_rush": pfr_rush, "snaps": snaps}


def run(seasons=(2022, 2023, 2024, 2025), first_prior: int | None = 2021) -> dict:
    return study(collect(seasons, first_prior))


def collect(seasons=(2022, 2023, 2024, 2025), first_prior: int | None = 2021) -> dict:
    points: dict = {}
    prev = None
    wanted = ([first_prior] if first_prior else []) + list(seasons)
    for yr in wanted:
        cur = load_season(yr)
        if yr in seasons:
            for k, v in samples(cur, prev).items():
                points.setdefault(k, []).extend(v)
            print(f"  {yr}: {sum(len(v) for v in points.values())} sample(s) so far", flush=True)
        prev = cur
    return points


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", nargs="*", type=int, default=[2022, 2023, 2024, 2025])
    ap.add_argument("--json")
    ap.add_argument("--points", help="keep the samples here (pickle), and reuse them if present")
    a = ap.parse_args()
    import os
    import pickle
    if a.points and os.path.exists(a.points):
        with open(a.points, "rb") as fh:
            pts = pickle.load(fh)
    else:
        pts = collect(tuple(a.seasons), first_prior=min(a.seasons) - 1)
        if a.points:
            with open(a.points, "wb") as fh:
                pickle.dump(pts, fh)
    res = study(pts)
    print(report(res))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"|".join(k): v for k, v in res.items()}, fh, indent=1, default=str)
