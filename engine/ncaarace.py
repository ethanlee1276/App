"""The NCAA tournament race: college basketball's NBA Cup page.

Ethan, 2026-11-13: "make it like nba cup and shit I want all the features
like this is a complete sport. We want college basketball to feel complete
and done."

THE TOURNAMENT, 2026-27. Sixty-eight teams. Every Division I conference's
champion goes automatically (its conference tournament's winner), and the
selection committee picks the rest at large. It ranks all sixty-eight (the
S-curve) and seeds them 1 to 16 in four regions; the last four at-large teams
and the four lowest automatic qualifiers play the First Four in Dayton, and
then sixty-four play six rounds: the first round, the second, the Sweet 16,
the Elite Eight, the Final Four in Detroit (April 3, 2027) and the title
game (April 5).

WHAT IS OURS AND WHAT IS NOT.
  * THE RATINGS are ours (`engine.cbbratings`): points better than an average
    Division I team on a neutral floor, adjusted for every opponent played,
    measured on three seasons (docs/CBB_LAB.md, "The tournament model").
  * EVERY GAME LEFT is one draw at our win chance.
  * THE CONFERENCE TOURNAMENTS are stood in for until they are played: each
    conference's top `CONF_TOURNEY` by conference record (ties to the rating)
    in single elimination on a neutral floor. Formats differ (most invite
    every team; byes and home sites vary); the top seeds win most of them,
    and that is what this keeps. A conference tournament under way plays on
    from the teams it has not knocked out, and a final played crowns the
    real champion.
  * THE COMMITTEE is stood in for by a selection score: our rating plus
    `RESUME_POINTS` for every win above what the `BUBBLE_RANK`-th best team
    would expect against the same Division I schedule. On 2023-24 to 2025-26
    it named 104 of the 110 teams the committee took at large, and seeded
    the field within 0.69 of a line on average (docs/CBB_LAB.md). Conference
    separation in the bracket and the committee's quadrants are not
    modelled — said, not hidden.

THE FIELD IF THE SEASON ENDED TODAY is that score on the games played so far,
with today's conference leaders (by conference record; before conference play,
the best-rated school) as the automatic bids: seeded on the S-curve, with
the bubble either side of the cut. It is free, as every race's "if it ended
today" is. The chances — the field, a top-four seed, each round, the title —
are the rest of the season, the conference tournaments, the selection and
the bracket played out `SIMS` times, and paid (gate.PAID_KEYS_BY_FILE), as
are each contender's games at our price and the games that swing the field.

AFTER SELECTION SUNDAY the page is the bracket itself, off the scoreboard:
ESPN bills each tournament game "NCAA Men's Basketball Championship - East
Region - 1st Round" and carries each team's seed as its rank (seen on all
sixty-seven of 2026's). Every result is kept as it lands, and the chances
are the rest of the bracket played out from there.

PURE BELOW `publish`: compact games and ratings in, a payload out — tested
without a network (tests/test_the_ncaa_tournament_race.py).
"""
from __future__ import annotations

import datetime as _dt
import json
import random
from collections import defaultdict

from . import cbbratings as CR

FIELD = 68
#: The four regions as ESPN bills them.
REGIONS = ("East", "South", "West", "Midwest")
#: A region's first round by seed, in bracket order: the winners of the
#: first two meet, of the next two, and so on.
FIRST_ROUND = ((1, 16), (8, 9), (5, 12), (4, 13), (6, 11), (3, 14), (7, 10), (2, 15))
#: The rounds a team can reach, in order.
ROUNDS = ("field", "r64", "r32", "s16", "e8", "f4", "final", "title")
ROUND_NAMES = {"first_four": "First Four", "r64": "First round", "r32": "Second round", "s16": "Sweet 16",
               "e8": "Elite Eight", "f4": "Final Four", "final": "National championship"}

#: THE COMMITTEE, STOOD IN FOR (module note; docs/CBB_LAB.md, "The
#: tournament model"): the best of a grid of bubble ranks {30, 45, 60} and
#: weights {0 to 6} on 2023-24 to 2025-26, at naming the at-large teams and
#: at seeding the field together (1.0 to 2.0 at the 45th all named 104 of
#: 110; 1.5 seeded closest of the first pass's grid).
RESUME_POINTS = 1.5
BUBBLE_RANK = 45
#: The conference tournament stand-in: this many teams, single elimination.
CONF_TOURNEY = 8
#: A conference with fewer Division I members than this sends no automatic
#: bid (the independents; the NCAA's own floor is seven).
MIN_CONFERENCE = 6
#: An at-large team has won at least as many as it has lost: the committee
#: has never taken a losing record at large.
AT_LARGE_MIN_PCT = 0.5
#: Seasons played out per build. A field chance near one half is good to
#: about a point either way at this many.
SIMS = 2000
#: The contenders listed with their chances: the most likely, at most this
#: many, each with at least `MIN_SHOWN` to make the field.
SHOWN = 100
MIN_SHOWN = 0.01
#: Each contender's next games at our price, at most this many.
NEXT_GAMES = 6
#: THE GAMES THAT SWING IT: the coming `SWING_DAYS` days' games between
#: Division I schools nearest the cut, at most `SWING_WATCH` watched per
#: build; a move is shown when it is at least `SWING_FLOOR` and, for a team
#: not playing in the game, `SWING_Z` standard errors of the run (a finite
#: run moves every bubble team a little in every game, by chance alone).
SWING_DAYS = 3
SWING_WATCH = 40
SWING_FLOOR = 0.04
SWING_Z = 3.5
SWING_MIN_SIMS = 60
SWING_SHOWN = 8
SWING_MOVES = 4

#: THE 2026-27 CALENDAR (the NCAA's announced dates and sites).
NIGHTS = {2026: {"selection": "2027-03-14",
                 "first_four": ("2027-03-16", "2027-03-17"),
                 "r64": ("2027-03-18", "2027-03-19"), "r32": ("2027-03-20", "2027-03-21"),
                 "s16": ("2027-03-25", "2027-03-26"), "e8": ("2027-03-27", "2027-03-28"),
                 "f4": ("2027-04-03",), "final": ("2027-04-05",)}}
FINAL_FOUR_SITE = {2026: "Detroit, Ford Field"}
#: The race runs from the season's first day to two days after the title.
SEASON_START = (11, 1)
AFTER_TITLE_DAYS = 2
NCAA_NOTE = "Men's Basketball Championship"
#: A conference tournament's rounds as ESPN bills them (the last part of the
#: billing, 2023-24 to 2025-26): "SEC Tournament - Final", "America East
#: Playoffs - Quarterfinal", "Ivy League Tournament pres. by TIAA - Semifinal".
CONF_ROUNDS = frozenset({"1st Round", "2nd Round", "3rd Round", "4th Round", "First Round", "Second Round",
                         "Opening Round", "Quarterfinal", "Quarterfinals", "Semifinal", "Semifinals",
                         "Final", "Championship"})
CONF_FINALS = frozenset({"Final", "Championship"})


def season_of(day: _dt.date) -> int:
    """College basketball's season, named by the year it starts
    (`engine.seasons`)."""
    from .seasons import season_of as _s
    return _s("cbb", day.isoformat())


def nights(season: int) -> dict:
    """The tournament's dates for a season; one this table does not hold
    gets 2026-27's weeks a year on per year (a fallback, said so in the
    payload's ``calendar``)."""
    if season in NIGHTS:
        return NIGHTS[season]
    base = NIGHTS[2026]

    def shift(iso):
        return (_dt.date.fromisoformat(iso) + _dt.timedelta(weeks=52 * (season - 2026))).isoformat()
    return {k: (shift(v) if isinstance(v, str) else tuple(shift(x) for x in v)) for k, v in base.items()}


def selection_day(season: int) -> _dt.date:
    return _dt.date.fromisoformat(nights(season)["selection"])


def window(season: int) -> tuple:
    return (_dt.date(season, *SEASON_START),
            _dt.date.fromisoformat(nights(season)["final"][-1]) + _dt.timedelta(days=AFTER_TITLE_DAYS))


# --- the season's games, compact ---------------------------------------------------
def compact(game: dict, date: str) -> dict | None:
    """One scoreboard game (`espnhoops.parse_scoreboard`, league cbb) as the
    race reads it."""
    h, a = game.get("home"), game.get("away")
    if not h or not a or game.get("preseason"):
        return None
    done = bool(game.get("completed")) and game.get("home_score") is not None \
        and game.get("away_score") is not None
    return {"id": str(game.get("game_id") or ""), "date": date, "home": h, "away": a,
            "hc": str(game.get("home_conf") or ""), "ac": str(game.get("away_conf") or ""),
            "home_score": float(game["home_score"]) if done else None,
            "away_score": float(game["away_score"]) if done else None,
            "neutral": bool(game.get("neutral")), "st": game.get("season_type") or 2,
            "notes": str(game.get("notes") or "").split(" · ")[0],
            "hseed": game.get("home_rank"), "aseed": game.get("away_rank")}


def _played(g: dict) -> bool:
    return g.get("home_score") is not None and g.get("away_score") is not None


def members(games: list) -> dict:
    """{team: conference id}: the commonest each Division I school carries."""
    seen: dict = defaultdict(lambda: defaultdict(int))
    for g in games:
        for side, conf in (("home", "hc"), ("away", "ac")):
            t, c = g.get(side), g.get(conf)
            if t and c and CR.is_division_one(t):
                seen[t][c] += 1
    return {t: max(cs.items(), key=lambda kv: (kv[1], kv[0]))[0] for t, cs in seen.items()}


def _round_of(g: dict) -> str:
    return (g.get("notes") or "").split(" - ")[-1].strip()


def conf_tourney(g: dict) -> bool:
    """A conference tournament's game: two schools of one conference, in
    February or March, billed by a round ("... Tournament - Semifinal")."""
    n = g.get("notes") or ""
    if not n or NCAA_NOTE in n or g.get("st") == 3:
        return False
    if not g.get("hc") or g.get("hc") != g.get("ac"):
        return False
    return str(g.get("date", ""))[5:7] in ("02", "03") and _round_of(g) in CONF_ROUNDS


def conf_state(played: list) -> dict:
    """{conference: {"champion": a school or "", "out": {schools knocked
    out}}} off the conference tournaments' games played so far."""
    out: dict = defaultdict(lambda: {"champion": "", "out": set(), "_final": ""})
    for g in sorted(played, key=lambda x: x.get("date", "")):
        if not conf_tourney(g) or not _played(g):
            continue
        c = g["hc"]
        hw = g["home_score"] > g["away_score"]
        win, lose = (g["home"], g["away"]) if hw else (g["away"], g["home"])
        st = out[c]
        st["out"].add(lose)
        if _round_of(g) in CONF_FINALS and g["date"] >= st["_final"]:
            st["champion"], st["_final"] = win, g["date"]
    return {c: {"champion": v["champion"], "out": v["out"]} for c, v in out.items()}


def split(games: list, season: int, today: str) -> tuple:
    """(played, left): the regular season's games played through selection
    Sunday (its conference finals included), and those still to play from
    today on — less the conference tournaments', which the race plays as
    its own stand-in. A game whose day has passed with no score was
    postponed; a rescheduled one comes back on its new day."""
    sel = selection_day(season).isoformat()
    played, left = [], []
    for g in games:
        if g.get("st") not in (None, 2) or g.get("date", "") > sel:
            continue
        if _played(g):
            played.append(g)
        elif g.get("date", "") >= today and not conf_tourney(g):
            left.append(g)
    return played, left


# --- records and the résumé ---------------------------------------------------------
def records(played: list, conf: dict) -> dict:
    """{team: {"w", "l", "cw", "cl"}}: the overall record over every game, the
    conference record over the regular season's games between two schools
    of the same conference."""
    out: dict = defaultdict(lambda: {"w": 0, "l": 0, "cw": 0, "cl": 0})
    for g in played:
        h, a = g["home"], g["away"]
        hw = g["home_score"] > g["away_score"]
        same = conf.get(h) and conf.get(h) == conf.get(a) and not conf_tourney(g)
        for t, won in ((h, hw), (a, not hw)):
            if not CR.is_division_one(t):
                continue
            r = out[t]
            r["w" if won else "l"] += 1
            if same:
                r["cw" if won else "cl"] += 1
    return out


def _pct(w: int, l: int) -> float:
    return w / (w + l) if (w + l) else 0.5


def bubble_rating(ratings: dict, rank: int = BUBBLE_RANK) -> float:
    di = sorted((r for t, r in ratings.items() if CR.is_division_one(t)), reverse=True)
    return di[min(len(di), rank) - 1] if di else 0.0


def bubble_chance(game: dict, team: str, ratings: dict, bubble: float) -> float | None:
    """A bubble team's chance to win this game in this team's place, or None
    against a school below Division I (the committee's sheets leave those
    games out of the résumé)."""
    home = game["home"] == team
    opp = game["away"] if home else game["home"]
    if not CR.is_division_one(opp):
        return None
    ro = CR.rating_of(ratings, opp)
    if home:
        return CR.win_prob(bubble, ro, game.get("neutral"))
    return 1.0 - CR.win_prob(ro, bubble, game.get("neutral"))


def resume(played: list, ratings: dict, bubble: float) -> dict:
    """{team: wins above a bubble team's expectation} over Division I games."""
    out: dict = defaultdict(float)
    for g in played:
        hw = g["home_score"] > g["away_score"]
        for t, won in ((g["home"], hw), (g["away"], not hw)):
            if not CR.is_division_one(t):
                continue
            e = bubble_chance(g, t, ratings, bubble)
            if e is not None:
                out[t] += (1.0 if won else 0.0) - e
    return out


# --- the selection -------------------------------------------------------------------
def leaders(recs: dict, conf: dict, ratings: dict, crowned: dict | None = None) -> dict:
    """{conference: its automatic bid today}: a crowned champion, else the
    best conference record (ties, and a conference yet to start, to the
    rating). A conference too small to send one is left out."""
    size: dict = defaultdict(int)
    for c in conf.values():
        size[c] += 1
    best: dict = {}
    for t, c in conf.items():
        if size[c] < MIN_CONFERENCE:
            continue
        r = recs.get(t) or {"cw": 0, "cl": 0}
        key = (_pct(r["cw"], r["cl"]), r["cw"], ratings.get(t, 0.0), t)
        if c not in best or key > best[c][0]:
            best[c] = (key, t)
    out = {c: t for c, (_k, t) in best.items()}
    for c, st in (crowned or {}).items():
        if st.get("champion") and c in out:
            out[c] = st["champion"]
    return out


def first_four(at_large: list, autos: list, score) -> list:
    """The First Four's pairs: the four lowest at-large by score, best against
    worst and the middle two, and the four lowest automatic bids the same."""
    pairs = []
    for grp in (sorted(at_large, key=score)[:4], sorted(autos, key=score)[:4]):
        if len(grp) == 4:
            grp = sorted(grp, key=score, reverse=True)
            pairs += [(grp[0], grp[3]), (grp[1], grp[2])]
    return pairs


def s_curve(order: list, pairs: list) -> tuple:
    """The sixty-four places dealt four to a seed line, the regions snaking
    (line 1: regions 0 1 2 3, line 2: 3 2 1 0, ...) so region 0 holds the
    overall first seed and region 3 the fourth; a First Four pair takes the
    place of its better team. Returns ([4 x {seed: team or (a, b)}],
    {team: (seed, region)})."""
    partner = {a: b for a, b in pairs}
    skip = {b for _a, b in pairs}
    slots = [t for t in order if t not in skip][:64]
    regions: list = [dict() for _ in range(4)]
    where = {}
    for i, t in enumerate(slots):
        line, pos = divmod(i, 4)
        reg = pos if line % 2 == 0 else 3 - pos
        regions[reg][line + 1] = (t, partner[t]) if t in partner else t
        where[t] = (line + 1, reg)
        if t in partner:
            where[partner[t]] = (line + 1, reg)
    return regions, where


def select(auto: dict, score: dict, recs: dict, field: int = FIELD) -> dict:
    """The sixty-eight by the selection score: ``{"auto", "at_large",
    "order" (the S-curve), "pairs" (the First Four), "regions", "seeds",
    "out" (the next eight by score)}``."""
    autos = list(dict.fromkeys(auto.values()))
    aset = set(autos)
    room = max(0, field - len(autos))

    def eligible(t):
        r = recs.get(t) or {"w": 0, "l": 0}
        return _pct(r["w"], r["l"]) >= AT_LARGE_MIN_PCT

    pool = sorted((t for t in score if t not in aset and eligible(t)), key=lambda t: (-score[t], t))
    at_large = pool[:room]
    out = pool[room:room + 8]

    def sc(t):
        return score.get(t, -99.0)
    order = sorted(autos + at_large, key=lambda t: (-sc(t), t))
    pairs = first_four(at_large, autos, sc)
    regions, seeds = s_curve(order, pairs)
    return {"auto": dict(auto), "at_large": at_large, "order": order, "pairs": pairs,
            "regions": regions, "seeds": seeds, "out": out}


# --- the bracket, played once ----------------------------------------------------------
def _bracket_order(n: int) -> list:
    """Seeds in bracket order for a single-elimination draw of ``n`` (a power
    of two): 1 8 4 5 2 7 3 6 for eight."""
    order = [1]
    while len(order) < n:
        m = len(order) * 2
        order = [x for s in order for x in (s, m + 1 - s)]
    return order


def play_bracket(regions: list, semis: tuple, beats, rng, results: dict | None = None,
                 tally: dict | None = None):
    """The tournament from the First Four on. ``regions`` are four ``{seed:
    team or (a, b)}`` (a pair is a First Four game); ``semis`` pairs the
    regions for the Final Four; ``beats(a, b)`` is a's chance against b on a
    neutral floor; ``results`` ``{frozenset((a, b)): winner}`` holds the games
    already played. ``tally[round][team]`` counts each team's furthest round.
    Returns the champion."""
    results = results or {}

    def play(a, b):
        if a is None or b is None:
            return b if a is None else a
        won = results.get(frozenset((a, b)))
        if won is None:
            won = a if rng.random() < beats(a, b) else b
        return won

    champs = []
    for reg in regions:
        line = []
        for pair in FIRST_ROUND:
            for s in pair:
                t = reg.get(s)
                if isinstance(t, tuple):
                    t = play(t[0], t[1])
                line.append(t)
        if tally is not None:
            for t in line:
                if t is not None:
                    tally["r64"][t] += 1
        for rnd in ("r32", "s16", "e8", "f4"):
            line = [play(a, b) for a, b in zip(line[::2], line[1::2])]
            if tally is not None:
                for t in line:
                    if t is not None:
                        tally[rnd][t] += 1
        champs.append(line[0])
    finalists = [play(champs[i], champs[j]) for i, j in semis]
    if tally is not None:
        for t in finalists:
            if t is not None:
                tally["final"][t] += 1
    champ = play(finalists[0], finalists[1])
    if tally is not None and champ is not None:
        tally["title"][champ] += 1
    return champ


#: The Final Four as the S-curve pairs it: the overall first seed's region
#: against the fourth's, the second's against the third's.
SEMIS = ((0, 3), (1, 2))


# --- the rest of the season, played out ---------------------------------------------------
def simulate(played: list, left: list, ratings: dict, sims: int | None = None, seed: int | None = None,
             watch: tuple = ()) -> dict:
    """Play the rest of the season out ``sims`` times: every game left, each
    conference's tournament (or what is left of it), the selection and the
    bracket. ``watch`` are game ids whose result is kept beside who made
    the field. Returns ``{"teams", "tally": {round: [count per team]},
    "auto", "top4", "seed_sum", "sims", "watch": [[game, [made it when home
    won], [when it lost], [n home won, n lost]]]}``."""
    sims = SIMS if sims is None else sims
    rng = random.Random(seed)
    conf = members(played + left)
    teams = sorted(conf)
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    rating = [float(ratings.get(t, 0.0)) for t in teams]
    full = {t: rating[i] for i, t in enumerate(teams)}
    bubble = bubble_rating(full)
    recs = records(played, conf)
    w0 = [recs[t]["w"] if t in recs else 0 for t in teams]
    l0 = [recs[t]["l"] if t in recs else 0 for t in teams]
    cw0 = [recs[t]["cw"] if t in recs else 0 for t in teams]
    cl0 = [recs[t]["cl"] if t in recs else 0 for t in teams]
    res_d = resume(played, full, bubble)
    res0 = [res_d.get(t, 0.0) for t in teams]
    # A bubble team's chance against each school on a neutral floor: what a
    # conference tournament's win is worth to the résumé.
    eb = [CR.win_prob(bubble, rating[i], True) for i in range(n)]
    crowned = conf_state(played)
    size: dict = defaultdict(int)
    for c in conf.values():
        size[c] += 1
    by_conf: dict = defaultdict(list)
    for t in teams:
        if size[conf[t]] >= MIN_CONFERENCE:
            by_conf[conf[t]].append(idx[t])
    fixed = {c: idx[st["champion"]] for c, st in crowned.items() if st["champion"] in idx}
    knocked = {c: {idx[x] for x in st["out"] if x in idx} for c, st in crowned.items()}
    # Each game left, once: its home chance and what each side's result is
    # worth to its résumé.
    watch_ids = set(watch)
    plan, seen = [], []
    for g in left:
        hi, ai = idx.get(g["home"], -1), idx.get(g["away"], -1)
        if hi < 0 and ai < 0:
            continue
        p = CR.win_prob(CR.rating_of(full, g["home"]), CR.rating_of(full, g["away"]), g.get("neutral"))
        same = hi >= 0 and ai >= 0 and conf[teams[hi]] == conf[teams[ai]]
        eh = bubble_chance(g, g["home"], full, bubble) if hi >= 0 else None
        ea = bubble_chance(g, g["away"], full, bubble) if ai >= 0 else None
        row = (hi, ai, p, same, (1.0 - eh) if eh is not None else 0.0, -eh if eh is not None else 0.0,
               (1.0 - ea) if ea is not None else 0.0, -ea if ea is not None else 0.0)
        if g.get("id") in watch_ids and hi >= 0 and ai >= 0:
            seen.append((g, row))
        else:
            plan.append(row)
    nw = len(seen)
    sw_in = [([0] * n, [0] * n) for _ in range(nw)]
    sw_n = [[0, 0] for _ in range(nw)]
    tally = {r: [0] * n for r in ROUNDS}
    auto_n, top4, seed_sum = [0] * n, [0] * n, [0] * n

    def beats(a, b):
        return CR.win_prob(rating[a], rating[b], True)

    for _ in range(sims):
        w, l, cw, cl, res = w0[:], l0[:], cw0[:], cl0[:], res0[:]
        rnd = rng.random
        outs = []
        for _g, (hi, ai, p, same, hw_, hl_, aw_, al_) in seen:
            home_won = rnd() < p
            outs.append(home_won)
            if home_won:
                w[hi] += 1
                l[ai] += 1
                res[hi] += hw_
                res[ai] += al_
                if same:
                    cw[hi] += 1
                    cl[ai] += 1
            else:
                l[hi] += 1
                w[ai] += 1
                res[hi] += hl_
                res[ai] += aw_
                if same:
                    cl[hi] += 1
                    cw[ai] += 1
        for hi, ai, p, same, hw_, hl_, aw_, al_ in plan:
            if rnd() < p:
                if hi >= 0:
                    w[hi] += 1
                    res[hi] += hw_
                    if same:
                        cw[hi] += 1
                if ai >= 0:
                    l[ai] += 1
                    res[ai] += al_
                    if same:
                        cl[ai] += 1
            else:
                if hi >= 0:
                    l[hi] += 1
                    res[hi] += hl_
                    if same:
                        cl[hi] += 1
                if ai >= 0:
                    w[ai] += 1
                    res[ai] += aw_
                    if same:
                        cw[ai] += 1
        # The conference tournaments: a champion crowned stands; the rest
        # play on from the schools not yet knocked out.
        auto = {}
        for c, mem in by_conf.items():
            if c in fixed:
                auto[c] = fixed[c]
                continue
            out_c = knocked.get(c) or ()
            alive = [i for i in mem if i not in out_c]
            alive.sort(key=lambda i: (-_pct(cw[i], cl[i]), -cw[i], -rating[i]))
            k = 1
            while k * 2 <= min(CONF_TOURNEY, len(alive)):
                k *= 2
            draw = [alive[s - 1] for s in _bracket_order(k)] if alive else []
            while len(draw) > 1:
                nxt = []
                for a, b in zip(draw[::2], draw[1::2]):
                    win, lose = (a, b) if rnd() < beats(a, b) else (b, a)
                    w[win] += 1
                    l[lose] += 1
                    res[win] += 1.0 - eb[lose]
                    res[lose] -= eb[win]
                    nxt.append(win)
                draw = nxt
            if draw:
                auto[c] = draw[0]
        score = {i: rating[i] + RESUME_POINTS * res[i] for i in range(n)}
        rec_now = {i: {"w": w[i], "l": l[i]} for i in range(n)}
        picked = select(auto, score, rec_now)
        inside = picked["seeds"]
        for i, (line, _reg) in inside.items():
            tally["field"][i] += 1
            seed_sum[i] += line
            if line <= 4:
                top4[i] += 1
        for i in auto.values():
            auto_n[i] += 1
        counts = {r: defaultdict(int) for r in ("r64", "r32", "s16", "e8", "f4", "final", "title")}
        play_bracket(picked["regions"], SEMIS, beats, rng, tally=counts)
        for r, got in counts.items():
            arr = tally[r]
            for i, c in got.items():
                arr[i] += c
        for k, home_won in enumerate(outs):
            r = 0 if home_won else 1
            sw_n[k][r] += 1
            bucket = sw_in[k][r]
            for i in inside:
                bucket[i] += 1
    return {"teams": teams, "conf": conf, "tally": tally, "auto": auto_n, "top4": top4, "seed_sum": seed_sum,
            "sims": sims, "watch": [[g, sw_in[k][0], sw_in[k][1], sw_n[k]] for k, (g, _r) in enumerate(seen)],
            "plan_p": {g.get("id"): r[2] for g, r in seen}}


def chances(sim: dict) -> dict:
    """{team: {round: share of the runs, "auto", "top4", "seed" (its average
    seed when in)}} for every team a run put in the field."""
    n = max(1, sim["sims"])
    out = {}
    for i, t in enumerate(sim["teams"]):
        f = sim["tally"]["field"][i]
        if not f:
            continue
        row = {r: round(sim["tally"][r][i] / n, 4) for r in ROUNDS}
        row["auto"] = round(sim["auto"][i] / n, 4)
        row["top4"] = round(sim["top4"][i] / n, 4)
        row["seed"] = round(sim["seed_sum"][i] / f, 1)
        out[t] = row
    return out


def swings(sim: dict, names: dict) -> list:
    """The watched games that move the field most. Each team's chance to make
    it when the home side wins against when it loses, weighted by how likely
    the game is to go either way (2·p·(1−p)): a lock whose upset would wreck
    a contender is a big "if" and a small swing. A team not in the game is
    shown only on a move the run could not make by chance (`SWING_Z`)."""
    teams = sim["teams"]
    rows = []
    for g, in_h, in_a, (nh, na) in sim.get("watch") or []:
        if min(nh, na) < SWING_MIN_SIMS:
            continue
        p = sim["plan_p"].get(g.get("id"), 0.5)
        moves, total = [], 0.0
        for i, t in enumerate(teams):
            a, b = in_h[i] / nh, in_a[i] / na
            d = abs(a - b)
            if d < SWING_FLOOR:
                continue
            if t not in (g["home"], g["away"]):
                se = ((a * (1 - a)) / nh + (b * (1 - b)) / na) ** 0.5
                if d < SWING_Z * max(se, 1e-9):
                    continue
            total += 2.0 * p * (1.0 - p) * d
            moves.append({"team": t, "if_home": round(a, 3), "if_away": round(b, 3)})
        if not moves:
            continue
        moves.sort(key=lambda m: -abs(m["if_home"] - m["if_away"]))
        rows.append({"id": g.get("id"), "date": g["date"], "home": g["home"], "away": g["away"],
                     "home_name": names.get(g["home"]) or g["home"], "away_name": names.get(g["away"]) or g["away"],
                     "neutral": bool(g.get("neutral")), "p_home": round(p, 3), "swing": round(total, 3),
                     "moves": moves[:SWING_MOVES]})
    rows.sort(key=lambda r: -r["swing"])
    return rows[:SWING_SHOWN]


def watched(left: list, score: dict, cut: int, today: str, limit: int = SWING_WATCH) -> list:
    """The coming days' games worth watching for the swing: between two
    Division I schools, nearest the at-large cut by the selection score
    first."""
    hi = (_dt.date.fromisoformat(today) + _dt.timedelta(days=SWING_DAYS)).isoformat()
    rank = {t: i + 1 for i, t in enumerate(sorted(score, key=lambda t: -score[t]))}
    cands = []
    for g in left:
        if not (today <= g.get("date", "") < hi) or not g.get("id"):
            continue
        h, a = g["home"], g["away"]
        if not (CR.is_division_one(h) and CR.is_division_one(a)):
            continue
        near = min(abs(rank.get(h, 999) - cut), abs(rank.get(a, 999) - cut))
        cands.append((near, g["date"], g["id"]))
    cands.sort()
    return [gid for _n, _d, gid in cands[:limit]]


# --- after selection Sunday: the bracket itself ---------------------------------------------
_ROUND_OF = {"First Four": "first_four", "1st Round": "r64", "First Round": "r64", "2nd Round": "r32",
             "Second Round": "r32", "Sweet 16": "s16", "Elite 8": "e8", "Elite Eight": "e8",
             "Final Four": "f4", "National Championship": "final", "Championship": "final"}


def bracket_games(games: list) -> list:
    """The tournament's games off the scoreboard: each one's region and round
    from ESPN's billing, each side's seed from its rank."""
    out = []
    for g in games:
        n = g.get("notes") or ""
        if NCAA_NOTE not in n:
            continue
        parts = [p.strip() for p in n.split(" - ")]
        region = next((p[:-len(" Region")] for p in parts if p.endswith(" Region")), "")
        rnd = next((_ROUND_OF[p] for p in parts[1:] if p in _ROUND_OF), "")
        done = _played(g)
        out.append({"id": g.get("id"), "date": g.get("date"), "region": region, "round": rnd,
                    "home": g["home"], "away": g["away"], "home_seed": g.get("hseed"), "away_seed": g.get("aseed"),
                    "home_score": g.get("home_score"), "away_score": g.get("away_score"), "done": done,
                    "winner": (g["home"] if g["home_score"] > g["away_score"] else g["away"]) if done else ""})
    return out


def real_field(bgames: list) -> dict:
    """{team: (seed, region name)} off the tournament's own games."""
    seeds = {}
    for g in bgames:
        if g["region"] not in REGIONS:
            continue
        for side in ("home", "away"):
            s = g[f"{side}_seed"]
            if s and g[side]:
                seeds.setdefault(g[side], (int(s), g["region"]))
    return seeds


def real_regions(seeds: dict) -> list:
    """The four regions as `play_bracket` reads them, in REGIONS order; two
    teams on one line of a region are a First Four pair."""
    regions: list = [dict() for _ in REGIONS]
    lines: dict = defaultdict(list)
    for t, (s, reg) in seeds.items():
        lines[(REGIONS.index(reg), s)].append(t)
    for (r, s), ts in lines.items():
        ts = sorted(ts)
        regions[r][s] = ts[0] if len(ts) == 1 else (ts[0], ts[1])
    return regions


def real_semis(bgames: list, seeds: dict, regions: list, ratings: dict) -> tuple:
    """The Final Four's region pairs: read off a Final Four game once the
    scoreboard lists one, else the S-curve's rule with the regions ordered
    by their 1 seeds' ratings (our stand-in for the committee's overall
    order). Returns (pairs, "named" or "ours")."""
    for g in bgames:
        if g["round"] == "f4" and g["home"] in seeds and g["away"] in seeds:
            a, b = REGIONS.index(seeds[g["home"]][1]), REGIONS.index(seeds[g["away"]][1])
            rest = [r for r in range(4) if r not in (a, b)]
            if a != b and len(rest) == 2:
                return ((a, b), tuple(rest)), "named"

    def top(r):
        t = regions[r].get(1)
        t = t[0] if isinstance(t, tuple) else t
        return CR.rating_of(ratings, t) if t else -99.0
    order = sorted(range(4), key=lambda r: -top(r))
    return ((order[0], order[3]), (order[1], order[2])), "ours"


def tree(regions: list, semis: tuple, results: dict, games_by_pair: dict) -> dict:
    """The bracket as the page draws it: each region's four rounds, the
    Final Four and the title game, every slot with its two teams (None for
    one not yet decided), seeds, the game when the scoreboard has it, and
    its winner once played."""
    def seed_of(reg, t):
        for s, x in reg.items():
            if x == t or (isinstance(x, tuple) and t in x):
                return s
        return None

    def slot(a, b, sa=None, sb=None, rnd=""):
        g = games_by_pair.get(frozenset((a, b))) if a and b else None
        won = results.get(frozenset((a, b))) if a and b else None
        row = {"a": a, "b": b, "sa": sa, "sb": sb, "round": rnd, "w": won}
        if g:
            home_is_a = g["home"] == a
            row.update({"id": g["id"], "date": g["date"],
                        "as": g["home_score"] if home_is_a else g["away_score"],
                        "bs": g["away_score"] if home_is_a else g["home_score"]})
        return row

    out = {"regions": [], "first_four": []}
    champs = []
    for r, reg in enumerate(regions):
        rounds = []
        line = []
        for pair in FIRST_ROUND:
            for s in pair:
                t = reg.get(s)
                if isinstance(t, tuple):
                    ff = slot(t[0], t[1], s, s, "first_four")
                    ff["region"] = REGIONS[r] if r < len(REGIONS) else ""
                    out["first_four"].append(ff)
                    t = ff["w"]
                line.append((t, s))
        first = [slot(a, b, sa, sb, "r64") for (a, sa), (b, sb) in zip(line[::2], line[1::2])]
        rounds.append(first)
        cur = first
        for rnd in ("r32", "s16", "e8"):
            nxt = []
            for x, y in zip(cur[::2], cur[1::2]):
                a, b = x["w"], y["w"]
                nxt.append(slot(a, b, seed_of(reg, a) if a else None, seed_of(reg, b) if b else None, rnd))
            rounds.append(nxt)
            cur = nxt
        champs.append((cur[0]["w"], seed_of(reg, cur[0]["w"]) if cur[0]["w"] else None))
        out["regions"].append({"name": REGIONS[r] if r < len(REGIONS) else f"Region {r + 1}", "rounds": rounds})
    semis_rows = [slot(champs[i][0], champs[j][0], champs[i][1], champs[j][1], "f4") for i, j in semis]
    out["final_four"] = semis_rows
    out["final"] = slot(semis_rows[0]["w"], semis_rows[1]["w"], None, None, "final")
    out["semis"] = [[REGIONS[i], REGIONS[j]] for i, j in semis]
    return out


def bracket_odds(regions: list, semis: tuple, ratings: dict, results: dict, sims: int, seed=None) -> dict:
    """Each team's chance to reach each round, the bracket played out from
    the results in."""
    rng = random.Random(seed)
    tally = {r: defaultdict(int) for r in ("r64", "r32", "s16", "e8", "f4", "final", "title")}

    def beats(a, b):
        return CR.win_prob(CR.rating_of(ratings, a), CR.rating_of(ratings, b), True)
    for _ in range(sims):
        play_bracket(regions, semis, beats, rng, results, tally)
    teams = set()
    for reg in regions:
        for x in reg.values():
            teams |= set(x) if isinstance(x, tuple) else {x}
    return {t: {r: round(tally[r].get(t, 0) / max(1, sims), 4) for r in tally} for t in teams if t}


# --- the payload -----------------------------------------------------------------------------
def poll_ranks(games: list, today: str) -> dict:
    """Each school's poll rank on its latest game to date (the scoreboard
    carries the AP top 25 as each side's rank before the tournament)."""
    latest: dict = {}
    for g in games:
        d = g.get("date", "")
        if d > today or g.get("st") == 3:
            continue
        for side, key in (("home", "hseed"), ("away", "aseed")):
            t = g[side]
            if t not in latest or d >= latest[t][0]:
                latest[t] = (d, g.get(key))
    # The poll is a top 25; a feed that marks the rest unranked with a 99
    # (hoopR's files do) is read as unranked.
    return {t: r for t, (_d, r) in latest.items() if r and 1 <= int(r) <= 25}


def _top_seed(region: dict) -> str:
    t = region.get(1) or ""
    return t[0] if isinstance(t, tuple) else t


def build(games: list, ratings: dict, today: str, names: dict | None = None, sims: int | None = None,
          seed: int | None = None) -> dict:
    """The page: the field if the season ended today, the bubble, each
    conference's race, our chances, the games that swing the field — and
    from selection Sunday, the bracket."""
    from . import cbbteams
    sims = SIMS if sims is None else sims
    names = dict(names or {})
    day = _dt.date.fromisoformat(today)
    season = season_of(day)
    sel = selection_day(season)
    played, left = split(games, season, today)
    conf = members(played + left)
    recs = records(played, conf)
    di = sorted(conf)
    full = {t: float(ratings.get(t, 0.0)) for t in di}
    bubble = bubble_rating(full)
    res = resume(played, full, bubble)
    score = {t: full[t] + RESUME_POINTS * res.get(t, 0.0) for t in di}
    crowned = conf_state(played)
    lead = leaders(recs, conf, full, crowned)
    picked = select(lead, score, recs)
    ranks = poll_ranks(games, today)

    def nm(t):
        return names.get(t) or t

    def row(t, **extra):
        r = recs.get(t) or {"w": 0, "l": 0, "cw": 0, "cl": 0}
        return {"team": t, "name": nm(t), "conf": cbbteams.conference(conf.get(t)),
                "record": f"{r['w']}-{r['l']}", "conf_record": f"{r['cw']}-{r['cl']}",
                "rank": ranks.get(t), **extra}

    bgames = bracket_games([g for g in games if g.get("date", "") >= sel.isoformat()])
    real = real_field(bgames) if day >= sel else {}
    bracket, lines, sim = None, {}, None
    if len(real) >= 64:
        regions = real_regions(real)
        semis, how = real_semis(bgames, real, regions, full)
        results = {frozenset((g["home"], g["away"])): g["winner"] for g in bgames if g["done"]}
        by_pair = {frozenset((g["home"], g["away"])): g for g in bgames}
        bracket = tree(regions, semis, results, by_pair)
        bracket.update({"set": True, "semis_from": how,
                        "seeds": {t: [s, r] for t, (s, r) in sorted(real.items())},
                        "champion": bracket["final"].get("w") or ""})
        for g in bgames:
            if not g["done"] and g["home"] and g["away"]:
                lines[g["id"]] = {"home": g["home"], "p_home": round(CR.win_prob(
                    CR.rating_of(full, g["home"]), CR.rating_of(full, g["away"]), True), 3)}
        ch = bracket_odds(regions, semis, full, results, sims, seed)
        field_rows = [row(t, seed=s, region=r)
                      for t, (s, r) in sorted(real.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[0]))]
        today_block = {"date": today, "set": True, "field": field_rows}
    else:
        # The cut by the selection score: where today's last at-large team
        # stands among every school (the small conferences' leaders sit
        # below it, so it is not the number of at-large places).
        by_all = sorted(score, key=lambda t: (-score[t], t))
        last_in = min(picked["at_large"], key=lambda t: score[t]) if picked["at_large"] else ""
        cut = by_all.index(last_in) + 1 if last_in else FIELD
        sim = simulate(played, left, full, sims=sims, seed=seed, watch=watched(left, score, cut, today))
        ch = chances(sim)
        aset = set(picked["auto"].values())
        ff = {t for p in picked["pairs"] for t in p}
        field_rows = []
        for t in picked["order"]:
            s, r = picked["seeds"].get(t, (None, None))
            field_rows.append(row(t, seed=s, region=r, bid="auto" if t in aset else "at-large",
                                  first_four=t in ff))
        by_score = sorted(picked["at_large"], key=lambda t: score[t])
        today_block = {"date": today, "set": False, "field": field_rows,
                       "first_four": [list(p) for p in picked["pairs"]],
                       "last_four_in": [row(t) for t in by_score[:4]],
                       "first_four_out": [row(t) for t in picked["out"][:4]],
                       "next_four_out": [row(t) for t in picked["out"][4:8]],
                       "auto_bids": {cbbteams.conference(c) or c: t for c, t in sorted(lead.items())},
                       "region_tops": [_top_seed(picked["regions"][r]) for r in range(4)]}
    # The contenders: everyone in the field today and the likeliest of the
    # rest, the likeliest champion first.
    in_field = {r["team"] for r in field_rows}
    pool = [t for t in set(ch) | in_field if t in in_field or ch.get(t, {}).get("field", 0.0) >= MIN_SHOWN]
    shown = sorted(pool, key=lambda t: (-(ch.get(t, {}).get("title", 0.0)), -(ch.get(t, {}).get("field", 0.0)),
                                        -score.get(t, -99.0), t))[:SHOWN]
    remaining = {}
    if not bracket:
        by_team: dict = defaultdict(list)
        for g in sorted(left, key=lambda x: (x["date"], x.get("id") or "")):
            p = CR.win_prob(CR.rating_of(full, g["home"]), CR.rating_of(full, g["away"]), g.get("neutral"))
            for t, home in ((g["home"], True), (g["away"], False)):
                by_team[t].append({"date": g["date"], "opp": g["away"] if home else g["home"], "home": home,
                                   "neutral": bool(g.get("neutral")), "p": round(p if home else 1 - p, 3)})
        for t in shown:
            mine = by_team.get(t, [])
            r = recs.get(t) or {"w": 0, "l": 0, "cw": 0, "cl": 0}
            ew = sum(x["p"] for x in mine)
            same = [x for x in mine if conf.get(x["opp"]) == conf.get(t)]
            ecw = sum(x["p"] for x in same)
            if t in ch:
                ch[t]["proj"] = [round(r["w"] + ew, 1), round(r["l"] + len(mine) - ew, 1)]
                ch[t]["conf_proj"] = [round(r["cw"] + ecw, 1), round(r["cl"] + len(same) - ecw, 1)]
                # Its wins' 10th to 90th, each game left one draw (the
                # futures page's band).
                sd = sum(x["p"] * (1 - x["p"]) for x in mine) ** 0.5
                ch[t]["proj_band"] = [max(r["w"], int(round(r["w"] + ew - 1.2816 * sd))),
                                      min(r["w"] + len(mine), int(round(r["w"] + ew + 1.2816 * sd)))]
            remaining[t] = mine[:NEXT_GAMES]
    conferences = {}
    for c in sorted({conf[t] for t in di}, key=lambda c: (cbbteams.conference(c) or c)):
        ts = [t for t in di if conf[t] == c]
        ts.sort(key=lambda t: (-_pct(recs.get(t, {}).get("cw", 0), recs.get(t, {}).get("cl", 0)),
                               -recs.get(t, {}).get("cw", 0),
                               -_pct(recs.get(t, {}).get("w", 0), recs.get(t, {}).get("l", 0)), t))
        st = crowned.get(c) or {}
        conferences[cbbteams.conference(c) or c] = {
            "name": cbbteams.conference_name(c) or c, "leader": lead.get(c, ""),
            "champion": st.get("champion", ""), "auto_bid": len(ts) >= MIN_CONFERENCE,
            "teams": [{"team": t, "name": nm(t), "record": row(t)["record"], "conf_record": row(t)["conf_record"],
                       "rank": ranks.get(t), "out": t in (st.get("out") or ())} for t in ts]}
    return {
        "sport": "cbb", "season": season, "date": today, "sims": sims,
        "today": today_block,
        "format": {"field": FIELD, "auto": len(lead), "at_large": FIELD - len(lead), "regions": list(REGIONS),
                   "first_round": [list(p) for p in FIRST_ROUND], "conf_tourney": CONF_TOURNEY},
        "assumptions": {"resume_points": RESUME_POINTS, "bubble_rank": BUBBLE_RANK, "home_court": CR.HCA,
                        "margin_sd": CR.SD},
        "nights": nights(season), "calendar": "announced" if season in NIGHTS else "estimated",
        "site": FINAL_FOUR_SITE.get(season, ""),
        "played": len(played), "games_left": len(left),
        "teams": [row(t) for t in shown],
        "conferences": conferences,
        "names": {t: names[t] for t in sorted(names) if names.get(t) and names[t] != t
                  and (t in conf or any(t == x["opp"] for v in remaining.values() for x in v))},
        # THE MODEL'S HALF — paid (gate.PAID_KEYS_BY_FILE["ncaa_race.json"]).
        "chances": {t: ch[t] for t in shown if t in ch},
        # Every school's chance at its conference's automatic bid, for the
        # conference tables (the contenders' rows carry theirs too).
        "bids": {t: c["auto"] for t, c in sorted(ch.items()) if c.get("auto", 0) >= 0.005},
        "remaining": remaining,
        "swing": swings(sim, names) if sim else [],
        "bracket": bracket,
        "bracket_lines": lines,
    }


# --- the box: the season off the scoreboard, kept compact ---------------------------------
#: How long a day's games are kept before the scoreboard is asked again: a
#: settled day for good, the last three days and today half an hour, the
#: coming week twelve hours, the weeks after three days (a schedule moves
#: rarely and the race rebuilds every few hours).
SETTLED_TTL = 365 * 24 * 3600
NEAR_TTL = 30 * 60
WEEK_TTL = 12 * 3600
AHEAD_TTL = 3 * 24 * 3600
#: The scoreboard is asked at most this many times a build: a fresh box
#: reads a season in a handful of builds rather than all at once, the days
#: to date first, the weeks ahead after. The race waits for all of them...
READS_PER_BUILD = 20
#: ...but for this many days ahead the scoreboard keeps refusing.
AHEAD_SLACK = 3


def _slate_path(date: str):
    from .sources import fetch as F
    return F._cache_path(f"cbb_slate_{date.replace('-', '')}.json")


def day_rows(date: str, fetch=None) -> list:
    """One day's Division I games, compact, read off the scoreboard and kept
    in a small file of their own (data/cache/cbb_slate_{date}.json). The
    scoreboard read is let go — a season of them is hundreds of megabytes —
    unless something else had already kept it. Every school the day names
    is remembered for the pages (`cbbteams.remember_cards`)."""
    import os
    from .sources import fetch as F
    path = _slate_path(date)
    if fetch is not None:
        games = fetch(date)
    else:
        from .sources import cbbespn
        raw = F._cache_path(f"espn_cbb_{date.replace('-', '')}.json")
        had = raw.exists()
        try:
            games = cbbespn.parse_scoreboard(cbbespn.fetch_scoreboard(date, ttl=60))
        finally:
            if not had:
                try:
                    raw.unlink()
                except OSError:
                    pass
        try:
            from . import cbbteams
            cbbteams.remember_cards(cbbespn.teams_from_games(games))
        except Exception:                                          # noqa: BLE001
            pass
    rows = [r for r in (compact(g, date) for g in games or []) if r]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"rows": rows}, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
    return rows


def _kept_day(date: str) -> list | None:
    try:
        return json.loads(_slate_path(date).read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        return None


def load_season(season: int, today: _dt.date, fetch=None, reads: int = READS_PER_BUILD) -> tuple:
    """The season's games, its first day to the title game, each day on the
    lifetime it needs. Returns (games, days to date not yet read, days ahead
    not yet read): a day the build's reads did not reach is read by the next
    build, the days before today first."""
    import time
    lo = _dt.date(season, *SEASON_START)
    hi = _dt.date.fromisoformat(nights(season)["final"][-1])
    days = []
    d = lo
    while d <= hi:
        days.append(d)
        d += _dt.timedelta(days=1)

    def ttl(day):
        if day < today - _dt.timedelta(days=3):
            return SETTLED_TTL
        if day <= today:
            return NEAR_TTL
        return WEEK_TTL if day <= today + _dt.timedelta(days=7) else AHEAD_TTL

    def age(day):
        try:
            return time.time() - _slate_path(day.isoformat()).stat().st_mtime
        except OSError:
            return None
    # The stale days: those to date first, the nearest first.
    stale = []
    for x in days:
        a = age(x)
        if a is None or a >= ttl(x):
            stale.append(x)
    stale.sort(key=lambda x: (x > today, abs((x - today).days)))
    for x in stale[:max(0, reads)]:
        try:
            day_rows(x.isoformat(), fetch)
        except Exception:                                          # noqa: BLE001
            pass                                                   # the kept file stands
    games, missing, ahead = [], 0, 0
    for x in days:
        rows = _kept_day(x.isoformat())
        if rows is None:
            if x <= today:
                missing += 1
            else:
                ahead += 1
            continue
        games += rows
    return games, missing, ahead


def prior_ratings(conn, season: int) -> dict:
    """Last season's ratings off the box's own games (no neutral floor is
    stored for them, so each reads at the home team's floor)."""
    rows = conn.execute("SELECT home, away, home_score, away_score FROM games WHERE sport='cbb' AND season=? "
                        "AND home_score IS NOT NULL AND away_score IS NOT NULL", (season - 1,)).fetchall()
    games = [{"home": h, "away": a, "home_score": hs, "away_score": as_, "neutral": False}
             for h, a, hs, as_ in rows]
    return CR.adjusted(games, prior_games=0.0) if games else {}


#: The race is played out again at most this often, beside its fingerprint:
#: a college night finishes a game every few minutes, and two thousand
#: seasons on each would spend the box's one processor on noise.
REBUILD_S = 2 * 3600


def publish(conn, day: _dt.date, out_path: str = "web/data/ncaa_race.json", fetch=None) -> str:
    """Build the race and write it through the gate. Returns the build-log
    line. In season only."""
    import time
    from pathlib import Path
    from . import cbbteams, gate, racecache
    season = season_of(day)
    lo, hi = window(season)
    if not (lo <= day <= hi):
        return "NCAA race: out of season, not built"
    p = Path(out_path)
    try:
        held = json.loads(Path(gate.board_source(p)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        held = None
    # HELD ONLY IF BUILT ON THE WHOLE SEASON. The first race on the box
    # (2026-11-14, 00:55 UTC) was played out with six days of the schedule
    # ahead read, "437 games left", and the two-hour hold then kept every
    # later build from reading the rest. A race is built on the whole
    # season's schedule now, and one that was not is never held.
    if held and held.get("generated_at") and held.get("date") == day.isoformat() \
            and held.get("schedule") == "whole":
        try:
            age = time.time() - _dt.datetime.fromisoformat(held["generated_at"]).timestamp()
        except ValueError:
            age = REBUILD_S
        if 0 <= age < REBUILD_S:
            return f"NCAA race: built {int(age // 60)} min ago, played out again at {REBUILD_S // 3600} hours"
    games, missing, ahead = load_season(season, day, fetch)
    # A day ahead the scoreboard keeps refusing must not hold the race up for
    # good: a handful (`AHEAD_SLACK`) may still be unread.
    if missing or ahead > AHEAD_SLACK:
        return (f"NCAA race: still reading the season off the scoreboard ({missing + ahead} day(s) to go), "
                "not built yet")
    if not games:
        return "NCAA race: no games read off the scoreboard, not built"
    prior = prior_ratings(conn, season) if conn is not None else {}
    done = [g for g in games if _played(g) and g.get("date", "") <= day.isoformat()]
    ratings = CR.adjusted(done, prior=prior)
    inputs = racecache.key("ncaa_race", SIMS, day.isoformat(), games, ratings, racecache.source_of(__file__),
                           racecache.source_of(CR.__file__))
    if racecache.kept(p, inputs):
        return "NCAA race: no score or game has moved since its last build — kept"
    names = {c: (card.get("short") or card.get("name") or c) for c, card in cbbteams.cards().items()}
    out = build(games, ratings, day.isoformat(), names=names)
    out["inputs"] = inputs
    out["schedule"] = "whole"
    out["days_unread"] = ahead
    out["prior"] = {"season": season - 1, "schools": len(prior)}
    out["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p, p.name)
    # The futures page, off the same run: our title chances beside the
    # books' prices already kept (a build never spends; futures_build.py
    # cbb --odds pulls them, one credit). Never at the race's expense.
    fut = ""
    try:
        fut = write_futures(out, p.with_name("futures_cbb.json"), cache_only=True)
    except Exception as exc:                                       # noqa: BLE001
        fut = f"futures not written ({type(exc).__name__}: {exc})"
    b = out.get("bracket")
    if b:
        decided = sum(1 for reg in b["regions"] for rnd in reg["rounds"] for s in rnd if s.get("w"))
        return (f"NCAA tournament: {decided} bracket game(s) decided"
                + (f" — {b['champion']} the champion" if b.get("champion") else "") + f"; {fut}")
    top = sorted(out["chances"].items(), key=lambda kv: -kv[1]["title"])[:4]
    return (f"NCAA race: {out['played']} games played, {out['games_left']} left, {out['sims']} seasons — "
            + ", ".join(f"{t} {c['title']:.0%}" for t, c in top) + f"; {fut}")


# --- the futures page --------------------------------------------------------------------
#: How the futures page says where college's numbers come from (its
#: ``doctrine``; the other leagues' is futures_build.DOCTRINE).
FUTURES_DOCTRINE = (
    "Every number here comes from playing the rest of the college season out — every game left, each "
    "conference's tournament, the committee's selection and the NCAA tournament's bracket — two thousand "
    "times, the same run as the Race page, not from reading a price. Futures are the market a book posts "
    "earliest and revisits least, which is where the edge argument comes from — and the market least likely "
    "to hold a sure thing, because the horizon is months and the stake is tied up for all of it.")
FUTURES_HOW = (
    "Each game left is one draw at our win chance from ratings adjusted for every opponent, the home court "
    "off a neutral floor. Each conference's tournament is its top eight by conference record, single "
    "elimination; the at-large picks stand in for the committee by our rating and each school's wins above a "
    "bubble team's; the bracket is seeded on the S-curve and played out game by game. Assumed, and worth "
    "knowing: ratings hold for the rest of the season — no injuries, no transfers, no regression — and every "
    "game is independent.")
#: Rows the futures page lists for college (the other leagues' twenty).
FUTURES_ROWS = 30


def title_prices(cache_only: bool = True) -> tuple:
    """(``{team: {"odds", "book", "implied"}}``, why it is empty): the
    national title's best price per school. The books' runners are matched
    by the names college's game lines learned (`cbbteams.load`) and each
    school's ESPN name (`cbbteams.cards`), exactly once normalised; a runner
    matched to no school is dropped, never guessed (`oddsapi.parse_outrights`).
    ``cache_only`` by default: a build never spends."""
    try:
        from . import cbbteams
        from .sources import oddsapi
        names = {c.get("name"): code for code, c in cbbteams.cards().items() if c.get("name")}
        names.update(cbbteams.load() or {})
        payload, _ = oddsapi.fetch_outrights("cbb", cache_only=cache_only)
        got = oddsapi.parse_outrights(payload, names)
        if not got:
            return {}, ("no title prices kept yet — futures_build.py cbb --odds pulls them" if cache_only
                        else "the futures market answered with no prices for college")
        return got, ""
    except Exception as exc:                                       # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"


def futures_payload(race: dict, prices: dict | None = None, price_note: str = "") -> dict:
    """The futures page's shape (futuresdata.project's) off a race: each
    contender's record, projected wins with a band, its chance at its
    conference's automatic bid ("Bid") and the field ("Field"), and the
    title — beside the best book price and the gap, in points."""
    prices = prices or {}
    ch = race.get("chances") or {}
    bracket = bool((race.get("bracket") or {}).get("set"))
    rows = []
    for r in race.get("teams") or []:
        c = ch.get(r["team"])
        if not c:
            continue
        w, l = (int(x) for x in str(r.get("record") or "0-0").split("-")[:2])
        proj = c.get("proj") or [w, l]
        band = c.get("proj_band") or [w, w]
        row = {"team": r["team"], "name": r.get("name") or r["team"], "conference": r.get("conf") or "",
               "wins": w, "losses": l, "proj_wins": float(proj[0]),
               "proj_wins_lo": band[0], "proj_wins_hi": band[1],
               "p_division": None if bracket else c.get("auto"),
               "p_playoffs": 1.0 if bracket else c.get("field"), "p_title": c.get("title", 0.0)}
        p = prices.get(r["team"])
        if p:
            row.update(title_odds=p["odds"], title_book=p["book"], title_implied=p["implied"],
                       title_edge_pts=round((row["p_title"] - p["implied"]) * 100, 1))
        rows.append(row)
    rows.sort(key=lambda x: (-x["p_title"], -(x["p_playoffs"] or 0), x["team"]))
    played = int(race.get("played") or 0)
    # The share of a rating that is still last season's: three games of it
    # against the games each school has played (two a game, over every
    # school in a conference).
    schools = sum(len(c.get("teams") or []) for c in (race.get("conferences") or {}).values()) or 1
    per = 2.0 * played / schools
    prior = (race.get("prior") or {}).get("schools")
    share = round(CR.PRIOR_GAMES / (CR.PRIOR_GAMES + per), 2) if prior else 0.0
    out = {"sport": "cbb", "season": race.get("season"), "teams": rows, "trials": race.get("sims", 0),
           "fixtures_remaining": race.get("games_left", 0), "games_played": played, "prior_share": share,
           "note": ("Each school's rating counts last season's as three games of this one, so early in the "
                    "season it leans on last year" if share else ""),
           "priced": len([x for x in rows if x.get("title_odds") is not None]),
           "labels": {"group": "Conf", "div": "Bid", "po": "Field"}, "rows_shown": FUTURES_ROWS,
           "doctrine": FUTURES_DOCTRINE, "how": FUTURES_HOW, "season_totals": [],
           "race_built": race.get("generated_at"), "generated_at": _dt.datetime.now().isoformat(timespec="seconds")}
    if price_note and not out["priced"]:
        out["price_note"] = price_note
    return out


def write_futures(race: dict, path, cache_only: bool = True) -> str:
    """futures_cbb.json off ``race``, through the gate (paid whole). Returns
    the build-log part."""
    from pathlib import Path
    from . import gate
    prices, why = title_prices(cache_only=cache_only)
    out = futures_payload(race, prices, why)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, path, path.name)
    return f"futures: {len(out['teams'])} school(s), {out['priced']} priced" + (f" ({why})" if why else "")


def futures_from_race(race_path: str = "web/data/ncaa_race.json", live_odds: bool = False) -> dict:
    """The futures payload off the race last built (its full copy), for
    futures_build.py: with ``live_odds`` the one-credit title pull."""
    from pathlib import Path
    from . import gate
    race = json.loads(Path(gate.board_source(Path(race_path))).read_text(encoding="utf-8"))
    prices, why = title_prices(cache_only=not live_odds)
    return futures_payload(race, prices, why)
