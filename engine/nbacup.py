"""The NBA Cup, group by group, played out from our numbers.

Ethan, 2026-10-29, to "an NBA Cup tracker: group standings, the
point-differential tiebreaker, our odds for each team to advance": "do all 3".

THE 2026 CUP, as the league published it:

  * six groups of five, three a conference, drawn from 2025-26 records;
    each team plays the other four once — two at home, two away — on the
    group nights from October 30 to November 27;
  * eight go through: each group's winner and one wild card a conference
    (the best record of the rest);
  * ties inside a group go to head-to-head, then POINT DIFFERENTIAL in the
    group games, then total points scored in them, then the 2025-26 record,
    then a draw; and a group game that goes to overtime counts ZERO in the
    differential, and its overtime points count nowhere. The wild card is
    the same order without the head-to-head (the teams have not met);
  * the quarterfinals (Dec 4-5) and semifinals (Dec 8-9) are at the higher
    seed's arena — group winners seeded 1-3 by the same order, the wild card
    4th — and the final is at Hinkle Fieldhouse, Indianapolis, on Dec 11.

WHAT IS OURS. Every group game left is a draw of the MARGIN — the futures
board's own rating gap and home court (`engine.futures`), spread so that
the chance it puts on a win is the chance that board puts on it — because
the differential is the second tiebreaker and a coin with no margin cannot
break a tie on it. A margin under half a point is a game to overtime: the
winner drawn at our price, the differential zero. Our stand-in for the
2025-26 record (the fourth tiebreaker) is the rating itself; stated.

The standings and the field if group play ended now are facts, and free.
The chances and every game left at our price are the model's, and paid
(gate.PAID_KEYS_BY_FILE["nba_cup.json"]).
"""

from __future__ import annotations

import datetime as _dt
import math
import random
from collections import defaultdict

#: The 2026 draw, in the league's own codes (engine.divisions).
GROUPS = {
    "East A": ("BKN", "DET", "MIL", "ORL", "TOR"),
    "East B": ("CLE", "IND", "MIA", "NYK", "PHI"),
    "East C": ("ATL", "BOS", "CHA", "CHI", "WAS"),
    "West A": ("DAL", "DEN", "HOU", "PHX", "UTA"),
    "West B": ("LAC", "MEM", "MIN", "NOP", "OKC"),
    "West C": ("GSW", "LAL", "POR", "SAC", "SAS"),
}
SEASON = 2026
GROUP_PLAY = ("2026-10-30", "2026-11-27")
KNOCKOUTS = {"quarterfinals": "2026-12-04", "semifinals": "2026-12-08",
             "final": "2026-12-11"}
#: An NBA game's margin around the rating gap. The futures board turns the
#: gap into a chance with a logistic of scale `futures.MARGIN_SCALE["nba"]`;
#: a normal whose CDF matches it has a spread of about 1.7 of that scale.
LOGISTIC_TO_NORMAL = 1.7
#: Points in an NBA game, for the third tiebreaker (total points scored).
TOTAL_MEAN = 228.0
TOTAL_SD = 18.0
SIMS = 10000


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def group_of(team: str) -> str:
    for g, ts in GROUPS.items():
        if team in ts:
            return g
    return ""


def conference(group: str) -> str:
    return group.split()[0] if group else ""


def cup_games(games: list) -> list:
    """The group games among a season's: both sides in one group, inside the
    group-play window, regular season. When the feed marks its Cup games
    (a note naming a group or the Cup) only marked games count; otherwise
    each pair's first meeting in the window is its group game."""
    from .divisions import canonical
    lo, hi = GROUP_PLAY
    rows = []
    for g in games:
        day = str(g.get("date") or g.get("kickoff") or "")[:10]
        if not (lo <= day <= hi) or g.get("season_type") not in (None, 2):
            continue
        h, a = canonical("nba", g.get("home", "")), canonical("nba", g.get("away", ""))
        grp = group_of(h)
        if not grp or group_of(a) != grp:
            continue
        rows.append((day, h, a, grp, g))
    marked = [r for r in rows if any(w in str(r[4].get("notes") or "").lower()
                                     for w in ("group", "cup"))]
    rows = marked or rows
    seen, out = set(), []
    for day, h, a, grp, g in sorted(rows, key=lambda r: (r[0], str(r[4].get("kickoff") or ""))):
        pair = frozenset((h, a))
        if pair in seen:
            continue
        seen.add(pair)
        out.append({"date": day, "home": h, "away": a, "group": grp,
                    "home_name": g.get("home_name") or h, "away_name": g.get("away_name") or a,
                    "done": bool(g.get("completed")) and g.get("home_score") is not None,
                    "home_score": g.get("home_score"), "away_score": g.get("away_score"),
                    "ot": _went_to_ot(g),
                    "reg": ((g["home_reg"], g["away_reg"]) if g.get("home_reg") is not None
                            and g.get("away_reg") is not None else None)})
    return out


def _went_to_ot(g: dict) -> bool:
    try:
        return int(g.get("period") or 0) > 4
    except (TypeError, ValueError):
        return False


def _rank(teams, w, l, pd, pf, net, games_between, rng, h2h=True) -> list:
    """The league's order among `teams`: record, then (inside a group)
    head-to-head among the tied, then differential, then points, then the
    prior record (our rating stands in), then a draw."""
    def h2h_key(tied):
        if not h2h or len(tied) < 2:
            return {t: 0 for t in tied}
        rec = {t: 0 for t in tied}
        for (x, y), winner in games_between.items():
            if x in rec and y in rec:
                rec[winner] += 1
        return rec
    # RECORD AS GAMES OVER .500, THEN WINS: equal to the league's order
    # once every team has played its four, and an honest one before that —
    # a 2-1 and a 1-0 are level, and the side with more played leads.
    by_rec = defaultdict(list)
    for t in teams:
        by_rec[(w[t] - l[t], w[t])].append(t)
    out = []
    for key in sorted(by_rec, reverse=True):
        tied = by_rec[key]
        hh = h2h_key(tied)
        tied.sort(key=lambda t: (-hh[t], -pd[t], -pf[t], -net[t], rng.random()))
        out += tied
    return out


def build(games: list, ratings: dict, today: str, home_edge: float, scale: float,
          sims: int = SIMS, seed=None) -> dict:
    """The Cup: every group's table, the field if group play ended now, and
    each team's chances, from the group games played and those left."""
    rng = random.Random(seed)
    sd = LOGISTIC_TO_NORMAL * scale
    teams = [t for ts in GROUPS.values() for t in ts]
    from .divisions import spellings

    def rating(t):
        for k in spellings("nba", t):
            if k in ratings:
                r = ratings[k]
                return float(getattr(r, "net", r) or 0.0)
        return 0.0
    net = {t: rating(t) for t in teams}
    rows = cup_games(games)
    names = {}
    for r in rows:
        names.setdefault(r["home"], r["home_name"])
        names.setdefault(r["away"], r["away_name"])

    w0, l0, pd0, pf0 = ({t: 0 for t in teams} for _ in range(4))
    between0 = {}
    left = []
    for r in rows:
        h, a = r["home"], r["away"]
        if r["done"]:
            hs, as_ = float(r["home_score"]), float(r["away_score"])
            win = h if hs > as_ else a
            w0[win] += 1
            l0[a if win == h else h] += 1
            between0[(h, a)] = win
            if not r["ot"]:
                pd0[h] += hs - as_
                pd0[a] += as_ - hs
                pf0[h] += hs
                pf0[a] += as_
            else:
                # Overtime: no differential, and regulation's points only —
                # the feed's own periods when it has them, else the score
                # the fourth quarter must have ended level at, which the
                # loser's total bounds from above.
                reg = r.get("reg") or (min(hs, as_), min(hs, as_))
                pf0[h] += reg[0]
                pf0[a] += reg[1]
        else:
            mu = net[h] - net[a] + home_edge
            left.append((h, a, mu, r))

    def standings_now(w, l, pd, pf, between):
        tables = {}
        for g, ts in GROUPS.items():
            tables[g] = _rank(ts, w, l, pd, pf, net, between, rng)
        return tables

    def field_of(tables, w, l, pd, pf):
        winners = {g: order[0] for g, order in tables.items()}
        wild = {}
        for conf in ("East", "West"):
            rest = [t for g, order in tables.items() if conference(g) == conf for t in order[1:]]
            wild[conf] = _rank(rest, w, l, pd, pf, net, {}, rng, h2h=False)[0]
        return winners, wild

    adv = defaultdict(int)
    won_group = defaultdict(int)
    wildcard = defaultdict(int)
    semis = defaultdict(int)
    final = defaultdict(int)
    cup = defaultdict(int)

    def play(h, a, neutral=False):
        mu = net[h] - net[a] + (0.0 if neutral else home_edge)
        return h if rng.random() < _phi(mu / sd) else a

    for _ in range(sims):
        w, l, pd, pf = dict(w0), dict(l0), dict(pd0), dict(pf0)
        between = dict(between0)
        for h, a, mu, _r in left:
            m = rng.gauss(mu, sd)
            tot = rng.gauss(TOTAL_MEAN, TOTAL_SD)
            if abs(m) < 0.5:
                win = h if rng.random() < _phi(mu / sd) else a
                pf[h] += tot / 2
                pf[a] += tot / 2
            else:
                win = h if m > 0 else a
                pd[h] += m
                pd[a] -= m
                pf[h] += (tot + m) / 2
                pf[a] += (tot - m) / 2
            w[win] += 1
            l[a if win == h else h] += 1
            between[(h, a)] = win
        tables = standings_now(w, l, pd, pf, between)
        winners, wild = field_of(tables, w, l, pd, pf)
        for t in winners.values():
            won_group[t] += 1
            adv[t] += 1
        for t in wild.values():
            wildcard[t] += 1
            adv[t] += 1
        champs = []
        for conf in ("East", "West"):
            gw = [t for g, t in winners.items() if conference(g) == conf]
            seeds = _rank(gw, w, l, pd, pf, net, {}, rng, h2h=False) + [wild[conf]]
            s1 = play(seeds[0], seeds[3])
            s2 = play(seeds[1], seeds[2])
            semis[s1] += 1
            semis[s2] += 1
            # The semifinal at the better seed's arena.
            hi_, lo_ = (s1, s2) if seeds.index(s1) < seeds.index(s2) else (s2, s1)
            c = play(hi_, lo_)
            final[c] += 1
            champs.append(c)
        cup[play(champs[0], champs[1], neutral=True)] += 1

    tables = standings_now(w0, l0, pd0, pf0, between0)
    winners, wild = field_of(tables, w0, l0, pd0, pf0)
    groups = {}
    for g, order in tables.items():
        groups[g] = [{"team": t, "name": names.get(t, t), "w": w0[t], "l": l0[t],
                      "pd": round(pd0[t]), "pf": round(pf0[t]),
                      "left": sum(1 for h, a, _m, _r in left if t in (h, a))} for t in order]
    chances, remaining = {}, {}
    for t in teams:
        chances[t] = {"advance": round(adv[t] / sims, 3), "group": round(won_group[t] / sims, 3),
                      "wildcard": round(wildcard[t] / sims, 3), "semis": round(semis[t] / sims, 3),
                      "final": round(final[t] / sims, 3), "cup": round(cup[t] / sims, 3)}
        sched = []
        for h, a, mu, r in left:
            if t not in (h, a):
                continue
            p = _phi(mu / sd)
            sched.append({"date": r["date"], "opp": a if t == h else h, "home": t == h,
                          "p": round(p if t == h else 1.0 - p, 3),
                          # The margin we expect, for the differential.
                          "margin": round(mu if t == h else -mu, 1)})
        remaining[t] = sched
    played = sum(1 for r in rows if r["done"])
    return {
        "sport": "nba", "season": SEASON, "date": today, "sims": sims,
        "window": list(GROUP_PLAY), "knockouts": KNOCKOUTS,
        "tiebreakers": ["head-to-head", "point differential (overtime counts zero)",
                        "points scored (overtime points excluded)", "2025-26 record", "a draw"],
        "groups": groups,
        "today": {"winners": winners, "wildcards": wild},
        "games": [{k: r[k] for k in ("date", "home", "away", "group", "done", "home_score",
                                     "away_score", "ot")} for r in rows],
        "played": played, "games_left": len(left),
        "names": names,
        # THE MODEL'S HALF — paid (gate.PAID_KEYS_BY_FILE["nba_cup.json"]).
        "chances": chances,
        "remaining": remaining,
        "swing": [],
    }


def load_window(today: _dt.date) -> list:
    """The group-play nights off the scoreboard cache: settled nights on the
    long lifetime `espnhoops` gives a finished day, the rest on its own."""
    from .sources import espnhoops
    from .sources.fetch import DataUnavailable
    lo, hi = (_dt.date.fromisoformat(d) for d in GROUP_PLAY)
    out, day = [], lo
    while day <= hi:
        try:
            got = espnhoops.load_day(day.isoformat(), league="nba")
        except (DataUnavailable, ValueError):
            got = []
        # The night it was billed for, not the UTC instant: a 10 PM Eastern
        # tip on November 27 is the 28th in UTC and still a group game.
        for g in got:
            g["date"] = day.isoformat()
        out += got
        day += _dt.timedelta(days=1)
    return out


def publish(conn, day: _dt.date, out_path: str = "web/data/nba_cup.json") -> str:
    """Build the Cup off the futures board's ratings and write it through the
    gate. Returns the build-log line. From a week before group play to the
    final; outside it there is nothing to track."""
    from pathlib import Path
    from . import futures, futuresdata, gate
    lo = _dt.date.fromisoformat(GROUP_PLAY[0]) - _dt.timedelta(days=7)
    if not (lo <= day <= _dt.date.fromisoformat(KNOCKOUTS["final"])):
        return "NBA Cup: not in the Cup window, not built"
    ratings, _prior, _n = futuresdata.blended_ratings(conn, "nba", SEASON)
    games = load_window(day)
    out = build(games, ratings, day.isoformat(), futures.HOME_EDGE["nba"],
                futures.MARGIN_SCALE["nba"])
    out["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p, p.name)
    best = sorted(out["chances"].items(), key=lambda kv: -kv[1]["cup"])[:3]
    return (f"NBA Cup: {out['played']} group game(s) played, {out['games_left']} left — "
            + ", ".join(f"{t} {c['cup']:.0%}" for t, c in best))
