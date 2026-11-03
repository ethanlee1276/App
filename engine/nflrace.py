"""The NFL playoff race, played out from our ratings.

Ethan, 2026-11-03, on the 30 October audit's list — "an NFL playoff race:
the same engine (play out the rest of the season with our game model) gives
each team's chance at the playoffs, the seeds if it ended today, and the
Sunday games that swing it" — "do all of them".

THE FORMAT. Fourteen teams, seven a conference: the four division winners
seeded 1-4 by record, then the three best records left as wild cards, 5-7.
Seed 1 alone sits out the Wild Card round, where 2 meets 7, 3 meets 6 and 4
meets 5 at the higher seed; the divisional round reseeds (1 meets the lowest
seed left); the conference title games are at the higher seed and the Super
Bowl is neutral.

TIEBREAKERS, AS FAR AS THE SCHEDULE TELLS THEM. A tie in win percentage
(a tie game counts half a win) is broken by the NFL's own first steps, in
order, and then by our rating, which stands in for the steps a schedule
cannot answer cheaply (common games, strength of victory and of schedule,
points). Stated, not hidden:

  * two clubs in a division: head-to-head, division record, conference
    record;
  * three or more in a division: head-to-head among them, division record,
    conference record;
  * any other two (a wild card, or seeding division winners): head-to-head
    when they met, conference record;
  * any other three or more: a head-to-head sweep (one beat all the others,
    or lost to all of them), conference record; and before any of it, only
    the highest-ranked club of each division can be chosen, as the league
    eliminates the rest first.

When one club of a multi-club tie is chosen, the others start the steps
again, two-club or multi-club — the league's own restart.

OURS AND NOT OURS. The standings and the seeds if it ended today are facts
off the schedule's results, and free. The chances, each game left at our
price and the games that swing the race are the model's, and paid
(gate.PAID_KEYS_BY_FILE). Every game left is one draw at `futures.win_prob`
on the ratings the futures board plays the season with
(`futuresdata.blended_ratings`), so the race and the Futures page agree about
every game; ratings stay where they are for the rest of the season (no
injuries, no trades), and no game is drawn as a tie.

PURE BELOW `publish`: schedule rows, ratings and a date in, a payload out —
tested without a network (tests/test_the_nfl_playoff_race.py).
"""

from __future__ import annotations

import datetime as _dt
import math
import random
from collections import defaultdict

from . import futures as FU
from .divisions import MAPS, canonical

CONFERENCES = ("AFC", "NFC")
DIVISIONS = ("East", "North", "South", "West")
BERTHS = 7
#: The Wild Card round, by seed: the higher seed hosts. Seed 1 rests.
WILD_CARD = ((2, 7), (3, 6), (4, 5))
SIMS = 10000
SWING_SHOWN = 8
#: A move smaller than this, or a game with fewer draws than this on its
#: short side, is a finite run's noise, not a finding (as in cfprace).
SWING_FLOOR = 0.03
SWING_MIN_SIMS = 150
#: The teams just outside the seven, listed under "If it ended today".
HUNT_SHOWN = 4
EPS = 1e-9


def _num(v):
    try:
        if str(v).strip() in ("", "NA", "None"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def league() -> list:
    """Every club, as the site codes them, with its conference and division."""
    return sorted((t, c, d) for t, (c, d) in MAPS.get("nfl", {}).items()
                  if c in CONFERENCES and d in DIVISIONS)


def schedule(rows: list, season: int) -> tuple:
    """(played, left) regular-season games of one season off nflverse's
    schedule, each as a dict: week, date, home, away, neutral, and the two
    scores when played."""
    played, left = [], []
    for r in rows:
        if str(r.get("season", "")).strip() != str(season):
            continue
        if str(r.get("game_type", "REG")).strip().upper() != "REG":
            continue
        h, a = canonical("nfl", str(r.get("home_team", ""))), canonical("nfl", str(r.get("away_team", "")))
        if not h or not a:
            continue
        try:
            week = int(float(r.get("week") or 0))
        except (TypeError, ValueError):
            week = 0
        g = {"week": week, "date": str(r.get("gameday") or "")[:10], "home": h, "away": a,
             "neutral": str(r.get("location", "")).strip().lower() == "neutral"}
        hs, as_ = _num(r.get("home_score")), _num(r.get("away_score"))
        if hs is not None and as_ is not None:
            g["home_score"], g["away_score"] = hs, as_
            played.append(g)
        else:
            left.append(g)
    return played, left


class _Table:
    """One season's records — played so far, or one run of the rest of it —
    and the head-to-head the tiebreakers read."""

    def __init__(self, n, conf, div, net):
        self.n, self.conf, self.div, self.net = n, conf, div, net
        self.w, self.l, self.t = [0] * n, [0] * n, [0] * n
        self.dw, self.dl, self.dt = [0] * n, [0] * n, [0] * n
        self.cw, self.cl, self.ct = [0] * n, [0] * n, [0] * n
        self.pf, self.pa = [0.0] * n, [0.0] * n
        self.h2h = defaultdict(float)          # (i, j): i's points against j (a win 1, a tie ½)
        self.met = defaultdict(int)            # (i, j): games they played

    def copy(self):
        c = _Table.__new__(_Table)
        c.n, c.conf, c.div, c.net = self.n, self.conf, self.div, self.net
        for k in ("w", "l", "t", "dw", "dl", "dt", "cw", "cl", "ct", "pf", "pa"):
            setattr(c, k, list(getattr(self, k)))
        c.h2h, c.met = defaultdict(float, self.h2h), defaultdict(int, self.met)
        return c

    def add(self, h, a, hs, as_):
        """A result: home index, away index, the two scores."""
        same_div = self.div[h] == self.div[a]
        same_conf = self.conf[h] == self.conf[a]
        if hs > as_:
            res = ((h, "w"), (a, "l"))
        elif as_ > hs:
            res = ((h, "l"), (a, "w"))
        else:
            res = ((h, "t"), (a, "t"))
        for i, r in res:
            getattr(self, r)[i] += 1
            if same_div:
                getattr(self, "d" + r)[i] += 1
            if same_conf:
                getattr(self, "c" + r)[i] += 1
        self.pf[h] += hs
        self.pa[h] += as_
        self.pf[a] += as_
        self.pa[a] += hs
        pts_h = 1.0 if hs > as_ else 0.5 if hs == as_ else 0.0
        self.h2h[(h, a)] += pts_h
        self.h2h[(a, h)] += 1.0 - pts_h
        self.met[(h, a)] += 1
        self.met[(a, h)] += 1

    def win(self, wi, li):
        """A drawn result: no scores, no ties."""
        same_div = self.div[wi] == self.div[li]
        same_conf = self.conf[wi] == self.conf[li]
        self.w[wi] += 1
        self.l[li] += 1
        if same_div:
            self.dw[wi] += 1
            self.dl[li] += 1
        if same_conf:
            self.cw[wi] += 1
            self.cl[li] += 1
        self.h2h[(wi, li)] += 1.0
        self.met[(wi, li)] += 1
        self.met[(li, wi)] += 1

    @staticmethod
    def _pct(w, l, t):
        g = w + l + t
        return (w + 0.5 * t) / g if g else 0.0

    def pct(self, i):
        return self._pct(self.w[i], self.l[i], self.t[i])

    def dpct(self, i):
        return self._pct(self.dw[i], self.dl[i], self.dt[i])

    def cpct(self, i):
        return self._pct(self.cw[i], self.cl[i], self.ct[i])

    def record(self, i, kind=""):
        w, l, t = (getattr(self, kind + "w")[i], getattr(self, kind + "l")[i], getattr(self, kind + "t")[i])
        return f"{w}-{l}" + (f"-{t}" if t else "")


# --- the tiebreakers ------------------------------------------------------------------
def _two(a, b, tb, same_div):
    """Two clubs: head-to-head, (in a division) division record, conference
    record, then our rating."""
    n = tb.met[(a, b)]
    pa, pb = tb.h2h[(a, b)], tb.h2h[(b, a)]
    if n and abs(pa - pb) > EPS:
        return (a, b) if pa > pb else (b, a)
    if same_div:
        da, db = tb.dpct(a), tb.dpct(b)
        if abs(da - db) > EPS:
            return (a, b) if da > db else (b, a)
    ca, cb = tb.cpct(a), tb.cpct(b)
    if abs(ca - cb) > EPS:
        return (a, b) if ca > cb else (b, a)
    return (a, b) if tb.net[a] >= tb.net[b] else (b, a)


def _many_key(i, pool, tb, same_div):
    """Three or more: in a division, head-to-head among them; otherwise a
    sweep only (1 beat every other, −1 lost to every other); then division
    record (in a division), conference record, our rating."""
    others = [j for j in pool if j != i]
    if same_div:
        pts = sum(tb.h2h[(i, j)] for j in others)
        n = sum(tb.met[(i, j)] for j in others)
        h = pts / n if n else 0.5
    else:
        beat = all(tb.met[(i, j)] and tb.h2h[(i, j)] > tb.h2h[(j, i)] for j in others)
        lost = all(tb.met[(i, j)] and tb.h2h[(i, j)] < tb.h2h[(j, i)] for j in others)
        h = 1.0 if beat else -1.0 if lost else 0.0
    return (-h, -(tb.dpct(i) if same_div else 0.0), -tb.cpct(i), -tb.net[i])


def _break(tied, tb, same_div, div_rank=None):
    """Clubs level on win percentage, best first. With `div_rank` (a wild
    card), only each division's highest-ranked club may be chosen next."""
    if len(tied) <= 1:
        return list(tied)
    pool = list(tied)
    if div_rank is not None:
        best = {}
        for i in tied:
            d = tb.div[i]
            if d not in best or div_rank[i] < div_rank[best[d]]:
                best[d] = i
        pool = list(best.values())
    if len(pool) == 1:
        first = pool[0]
    elif len(pool) == 2:
        first = _two(pool[0], pool[1], tb, same_div)[0]
    else:
        first = min(pool, key=lambda i: _many_key(i, pool, tb, same_div))
    rest = [i for i in tied if i != first]
    return [first] + _break(rest, tb, same_div, div_rank)


def order(group, tb, same_div, div_rank=None) -> list:
    """Clubs best first: win percentage, then the tiebreakers above."""
    group = sorted(group, key=lambda i: -tb.pct(i))
    out, k = [], 0
    while k < len(group):
        j = k + 1
        while j < len(group) and abs(tb.pct(group[j]) - tb.pct(group[k])) < EPS:
            j += 1
        out += _break(group[k:j], tb, same_div, div_rank)
        k = j
    return out


def seed(tb, members) -> dict:
    """{conference: (seven seeds in order, every division's order, the
    clubs left out in order)} for one table."""
    out = {}
    for conf in CONFERENCES:
        div_rank, champs, divs = {}, [], {}
        for d in DIVISIONS:
            ranked = order(members[(conf, d)], tb, True)
            divs[d] = ranked
            for r, i in enumerate(ranked):
                div_rank[i] = r
            if ranked:
                champs.append(ranked[0])
        champs = order(champs, tb, False)
        rest = [i for d in DIVISIONS for i in divs[d][1:]]
        wild = order(rest, tb, False, div_rank)
        seeds = champs + wild[:BERTHS - len(champs)]
        out[conf] = (seeds, divs, wild[BERTHS - len(champs):])
    return out


def _bracket(seeds, net, rng):
    """One conference's playoffs: its champion."""
    s = {k + 1: t for k, t in enumerate(seeds)}

    def game(home, away, neutral=False):
        p = FU.win_prob("nfl", net[home], net[away], neutral=neutral)
        return home if rng.random() < p else away
    alive = [1] + [h if game(s[h], s[a]) == s[h] else a for h, a in WILD_CARD]
    alive.sort()
    top, a, b, c = alive
    d1 = top if game(s[top], s[c]) == s[top] else c
    d2 = a if game(s[a], s[b]) == s[a] else b
    hi, lo = sorted((d1, d2))
    return s[hi] if game(s[hi], s[lo]) == s[hi] else s[lo]


def build(rows: list, ratings: dict, today: str, season: int | None = None,
          sims: int = SIMS, seed_=None) -> dict:
    """The race: the seeds if it ended today, the standings, every club's
    chances, its games left at our price, and the coming week's games that
    move the field most."""
    rng = random.Random(seed_)
    season = int(season if season is not None else today[:4])
    clubs = league()
    teams = [t for t, _c, _d in clubs]
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    conf = [c for _t, c, _d in clubs]
    div = [f"{c} {d}" for _t, c, d in clubs]
    net = [float(ratings.get(t, 0.0) or 0.0) for t in teams]
    members = defaultdict(list)
    for i, (_t, c, d) in enumerate(clubs):
        members[(c, d)].append(i)

    played, left = schedule(rows, season)
    base = _Table(n, conf, div, net)
    for g in played:
        h, a = idx.get(g["home"]), idx.get(g["away"])
        if h is not None and a is not None:
            base.add(h, a, g["home_score"], g["away_score"])

    # The games left, at our price.
    rem = []
    for g in left:
        h, a = idx.get(g["home"]), idx.get(g["away"])
        if h is None or a is None:
            continue
        p = FU.win_prob("nfl", net[h], net[a], neutral=g["neutral"])
        rem.append((h, a, p, g))
    weeks = sorted({r[3]["week"] for r in rem if r[3]["week"]})
    week = weeks[0] if weeks else None
    swing_ix = [k for k, r in enumerate(rem) if r[3]["week"] == week]

    inn, divw, bye, conf_c, title = [0] * n, [0] * n, [0] * n, [0] * n, [0] * n
    seed_sum = [0] * n
    sw_n = {k: [0, 0] for k in swing_ix}
    sw_in = {k: (defaultdict(int), defaultdict(int)) for k in swing_ix}
    for _ in range(sims):
        tb = base.copy()
        outcome = {}
        for k, (h, a, p, _g) in enumerate(rem):
            hw = rng.random() < p
            outcome[k] = hw
            if hw:
                tb.win(h, a)
            else:
                tb.win(a, h)
        field = seed(tb, members)
        champs = []
        in_field = set()
        for c in CONFERENCES:
            seeds, divs, _out = field[c]
            for s, i in enumerate(seeds, 1):
                inn[i] += 1
                seed_sum[i] += s
                in_field.add(i)
                if s == 1:
                    bye[i] += 1
            for d in DIVISIONS:
                if divs[d]:
                    divw[divs[d][0]] += 1
            if len(seeds) == BERTHS:
                ch = _bracket(seeds, net, rng)
                conf_c[ch] += 1
                champs.append(ch)
        if len(champs) == 2:
            a, b = champs
            title[a if rng.random() < FU.win_prob("nfl", net[a], net[b], neutral=True) else b] += 1
        for k in swing_ix:
            r = 0 if outcome[k] else 1
            sw_n[k][r] += 1
            bucket = sw_in[k][r]
            for i in in_field:
                bucket[i] += 1

    chances, remaining = {}, {}
    for i, t in enumerate(teams):
        sched = []
        for h, a, p, g in rem:
            if i not in (h, a):
                continue
            home = i == h
            sched.append({"week": g["week"], "date": g["date"], "opp": teams[a] if home else teams[h],
                          "home": home, "neutral": g["neutral"], "p": round(p if home else 1.0 - p, 3)})
        exp_w = base.w[i] + 0.5 * base.t[i] + sum(s["p"] for s in sched)
        games = base.w[i] + base.l[i] + base.t[i] + len(sched)
        chances[t] = {
            "playoffs": round(inn[i] / sims, 3), "division": round(divw[i] / sims, 3),
            "bye": round(bye[i] / sims, 3), "conference": round(conf_c[i] / sims, 3),
            "title": round(title[i] / sims, 3),
            "seed": round(seed_sum[i] / inn[i], 1) if inn[i] else None,
            "proj": [round(exp_w, 1), round(games - exp_w, 1)],
        }
        remaining[t] = sched

    # HOW MUCH A GAME MOVES THE FIELD (cfprace's measure): each club's chance
    # of the playoffs if the home side wins against if it loses, weighted by
    # how likely the game is to go either way, 2·p·(1−p).
    #
    # ONLY WHERE A RESULT CAN REACH, AND ONLY PAST THE SAMPLER'S NOISE. Two
    # AFC clubs' game cannot move an NFC club's chances, and on a finite run
    # thirty-two clubs times a week of games turned up "moves" like that
    # anyway (a 6-point one for the Falcons in Chiefs-Broncos, 2026-11-03,
    # gone at 12,000 runs): a club is weighed only in the two clubs'
    # conferences, and a move counts only past three standard errors.
    swing = []
    for k in swing_ix:
        h, a, p, g = rem[k]
        nh, na = sw_n[k]
        if min(nh, na) < SWING_MIN_SIMS:
            continue
        reach = {conf[h], conf[a]}
        moves, total = [], 0.0
        for i in set(sw_in[k][0]) | set(sw_in[k][1]):
            if conf[i] not in reach:
                continue
            x, y = sw_in[k][0].get(i, 0) / nh, sw_in[k][1].get(i, 0) / na
            noise = 3.0 * math.sqrt(x * (1.0 - x) / nh + y * (1.0 - y) / na)
            if abs(x - y) < max(SWING_FLOOR, noise):
                continue
            total += 2.0 * p * (1.0 - p) * abs(x - y)
            moves.append({"team": teams[i], "if_home": round(x, 3), "if_away": round(y, 3)})
        if not moves:
            continue
        moves.sort(key=lambda m: -abs(m["if_home"] - m["if_away"]))
        swing.append({"week": g["week"], "date": g["date"], "home": teams[h], "away": teams[a],
                      "neutral": g["neutral"], "p_home": round(p, 3), "swing": round(total, 3),
                      "moves": moves[:4]})
    swing.sort(key=lambda s: -s["swing"])

    now = seed(base, members)
    today_out, standings = {}, {}
    for c in CONFERENCES:
        seeds, divs, out = now[c]
        champs = set(seeds[:4])
        last = seeds[-1] if len(seeds) == BERTHS else None

        def back(i):
            if last is None:
                return None
            return round(((base.w[last] - base.w[i]) + (base.l[i] - base.l[last])) / 2.0, 1)
        today_out[c] = {
            "seeds": [{"seed": s, "team": teams[i], "record": base.record(i),
                       "why": f"{div[i]} leader" if i in champs else "Wild card"}
                      for s, i in enumerate(seeds, 1)],
            "hunt": [{"team": teams[i], "record": base.record(i), "back": back(i)} for i in out[:HUNT_SHOWN]],
        }
        for d in DIVISIONS:
            standings[f"{c} {d}"] = [{
                "team": teams[i], "record": base.record(i), "div": base.record(i, "d"),
                "conf": base.record(i, "c"), "pf": int(base.pf[i]), "pa": int(base.pa[i]),
            } for i in divs[d]]

    rows_out = sorted(({"team": t, "conference": conf[i], "division": div[i], "record": base.record(i)}
                       for i, t in enumerate(teams)),
                      key=lambda r: (-chances[r["team"]]["playoffs"], r["team"]))
    return {
        "sport": "nfl", "season": season, "date": today, "week": week, "sims": sims,
        "format": {"berths": BERTHS, "byes": 1, "wild_card": [list(x) for x in WILD_CARD]},
        "today": today_out,
        "standings": standings,
        "teams": rows_out,
        "games_played": len(played),
        "games_left": len(rem),
        "tiebreakers": ("win percentage, then head-to-head, division record (in a division) and "
                        "conference record; a wild-card tie takes each division's best club first; "
                        "then our rating"),
        # THE MODEL'S HALF — paid (gate.PAID_KEYS_BY_FILE["nfl_race.json"]).
        "chances": chances,
        "remaining": remaining,
        "swing": swing[:SWING_SHOWN],
    }


def publish(day: _dt.date, out_path: str = "web/data/nfl_race.json") -> str:
    """Build the race off the futures board's ratings and the schedule, and
    write it through the gate. Returns the build-log line. From the first
    week of the season to the last regular-season game; nothing else."""
    from pathlib import Path
    from . import gate
    from .db import connect
    from .futuresdata import blended_ratings
    from .seasons import season_of
    from .sources.nflverse import load_schedules
    season = season_of("nfl", day.isoformat())
    rows = load_schedules()
    played, left = schedule(rows, season)
    if not left:
        return "NFL playoff race: no regular-season games left, not built"
    if not played:
        return "NFL playoff race: no games played yet, not built"
    conn = connect()
    try:
        ratings, prior_share, _n = blended_ratings(conn, "nfl", season)
    finally:
        conn.close()
    out = build(rows, ratings, day.isoformat(), season=season)
    out["prior_share"] = prior_share
    out["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p, p.name)
    top = ", ".join(f"{c} 1: {out['today'][c]['seeds'][0]['team']}" for c in CONFERENCES
                    if out["today"][c]["seeds"])
    return (f"NFL playoff race: week {out['week']}, {out['games_left']} games left, "
            f"{out['sims']:,} seasons played out — today {top}")
