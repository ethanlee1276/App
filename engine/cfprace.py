"""The College Football Playoff race, played out from our game model.

Ethan, 2026-10-29, to "a College Football Playoff race: each contender's
chances from our game model and remaining schedule, the bracket if it
started today, and which Saturday games swing it": "do all 3".

THE 2026-27 FORMAT, as the CFP Management Committee kept it for this season
(twelve teams; expansion is still being argued over for 2027):

  * the four Power Four champions — ACC, Big Ten, Big 12, SEC — automatic,
    wherever they are ranked;
  * the highest-ranked team from the Group of Six — the American,
    Conference USA, the MAC, the Mountain West, the Pac-12 and the Sun Belt
    — automatic, champion or not (the 2024-25 rule gave five bids to the
    highest-ranked champions; this one does not ask for a title);
  * Notre Dame, when it finishes in the top twelve;
  * the rest at large, the highest-ranked left;
  * seeded 1-12 straight off the final ranking. Seeds 1-4 sit out the first
    round, which is played on the campuses of seeds 5-8 (5 v 12, 6 v 11,
    7 v 10, 8 v 9), Dec 18-19; the quarterfinals and on are neutral.

WHAT IS OURS AND WHAT IS NOT. Every game left is one draw at the win chance
the college board prices with — the same opponent-adjusted ratings, talent
prior, home field and margin spread (`cfb_build`, `engine.cfb.ratings`).
The conference title games are played between the two best conference
records in each draw (ties to the better rating: the conferences' own
tiebreakers are not modelled, and a two-team head-to-head is the commonest
one they would apply — stated, not hidden). What is NOT ours is the
committee, and nobody's model has it: the final ranking in each draw is a
STAND-IN — a team's rating plus `WIN_POINTS` for every win above what an
elite team would expect against the same schedule, plus `CHAMP_POINTS` for a
title. Those two weights are assumptions, written down here, not a fit to
past committees; the page says so.

THE BRACKET IF IT STARTED TODAY IS NOT OURS AT ALL: it is the current poll —
the committee's own ranking from its first release (Nov 3, 2026), the AP
Top 25 before it — with today's conference leaders standing in for the
champions. Free, like the poll it is read from. The chances, the schedules
priced game by game and the swing games are the model's, and paid
(gate.PAID_KEYS_BY_FILE).

PURE BELOW `publish`: games, ratings and a clock in, a payload out — tested
without a network (tests/test_the_playoff_race.py).
"""

from __future__ import annotations

import datetime as _dt
import math
import random
from collections import Counter, defaultdict

P4 = ("ACC", "Big Ten", "Big 12", "SEC")
G6 = ("American", "Conference USA", "MAC", "Mountain West", "Pac-12", "Sun Belt")
INDEPENDENTS = "FBS Independents"
NOTRE_DAME = "ND"
FIELD = 12
BYES = 4
#: The first round, by seed: the higher seed hosts.
FIRST_ROUND = ((5, 12), (6, 11), (7, 10), (8, 9))
#: Each bye seed meets this first-round game's winner in the quarterfinals.
QUARTERS = ((1, 3), (2, 2), (3, 1), (4, 0))       # (seed, index into FIRST_ROUND)
#: The semifinals, by quarterfinal: 1 with 4's side, 2 with 3's side.
SEMIS = ((0, 3), (1, 2))

#: THE COMMITTEE, STOOD IN FOR (see the module note). Rating points a win
#: above an elite team's expected record is worth, and a conference title.
WIN_POINTS = 8.0
CHAMP_POINTS = 4.0
#: "Elite" is the rating of the team this many places from the top of FBS —
#: a playoff-calibre side, the yardstick strength of record is measured by.
ELITE_RANK = 12
#: An opponent the ratings have never seen: an FCS visitor, nearly always.
UNRATED = -20.0
SIMS = 6000
#: A team is listed as a contender at this chance or better, or when ranked.
MIN_SHOWN = 0.005
SHOWN = 30
SWING_SHOWN = 8
#: A move smaller than this, or a game with fewer draws than this on its
#: short side, is a finite run's noise (see the swing note in `build`).
SWING_FLOOR = 0.03
SWING_MIN_SIMS = 150


def ccg_start(season: int) -> _dt.date:
    """The Thursday the conference title weekend begins: the first in
    December (Dec 3, 2026; the games are the Friday and Saturday)."""
    d = _dt.date(int(season), 12, 1)
    return d + _dt.timedelta(days=(3 - d.weekday()) % 7)


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def win_prob(net_home: float, net_away: float, hfa: float, sd: float,
             neutral: bool = False) -> float:
    """P(home wins) — `cfb_build`'s own: a normal CDF over the projected
    margin, college football's fitted spread, clamped as the board clamps."""
    margin = (net_home - net_away) + (0.0 if neutral else hfa)
    return min(0.98, max(0.02, _phi(margin / max(sd, 1e-6))))


def _net(ratings: dict, team: str) -> float:
    r = ratings.get(team)
    if r is None:
        return UNRATED
    v = getattr(r, "net", r)
    try:
        return float(v)
    except (TypeError, ValueError):
        return UNRATED


def team_conferences(games: list) -> dict:
    """{team: conference}, the commonest label each team's own side carries."""
    seen: dict = defaultdict(Counter)
    for g in games:
        for side in ("home", "away"):
            t, c = g.get(side), str(g.get(f"{side}_conference") or "").strip()
            if t and c:
                seen[t][c] += 1
    return {t: c.most_common(1)[0][0] for t, c in seen.items()}


def _fbs(conf: str) -> bool:
    return conf in P4 or conf in G6 or conf == INDEPENDENTS


def _record(w: int, l: int) -> str:
    return f"{w}-{l}"


def current_ranks(games: list, today: str) -> dict:
    """{team: rank} off the scoreboard, when the poll feed could not be
    read: each team's rank on its next game (the current poll), or on its
    latest one when it has none left."""
    nxt: dict = {}
    last: dict = {}
    for g in sorted(games, key=lambda x: str(x.get("date") or "")):
        for side in ("home", "away"):
            t, r = g.get(side), g.get(f"{side}_rank")
            if not t or not isinstance(r, int) or not 1 <= r <= 25:
                continue
            if str(g.get("date") or "") >= today and t not in nxt:
                nxt[t] = r
            last[t] = r
    out = dict(last)
    out.update(nxt)
    return out


def _split(games: list, season: int) -> tuple:
    """(played, remaining, title games) for one season's regular slate."""
    cut = ccg_start(season).isoformat()
    played, left, titles = [], [], []
    for g in games:
        if g.get("season_type") not in (None, 2):
            continue
        if not g.get("home") or not g.get("away"):
            continue
        day = str(g.get("date") or "")
        done = g.get("completed") and g.get("home_score") is not None \
            and g.get("away_score") is not None
        if day >= cut:
            titles.append(g)
        elif done:
            played.append(g)
        elif g.get("state") != "final":
            left.append(g)
    return played, left, titles


def build(games: list, ratings: dict, hfa: float, sd: float, today: str,
          ranks: dict | None = None, poll: dict | None = None,
          teams: dict | None = None, sims: int = SIMS, seed=None) -> dict:
    """The race: the bracket if it started today, every contender's chances,
    their games left at our price, and the coming games that move it most."""
    rng = random.Random(seed)
    seasons = [g.get("season") for g in games if isinstance(g.get("season"), int)]
    season = Counter(seasons).most_common(1)[0][0] if seasons else int(today[:4])
    confs = team_conferences(games)
    played, left, titles = _split(games, season)
    fbs = sorted(t for t, c in confs.items() if _fbs(c))
    idx = {t: i for i, t in enumerate(fbs)}
    n = len(fbs)
    net = [_net(ratings, t) for t in fbs]
    conf_of = [confs[t] for t in fbs]

    # The season so far.
    w0, l0, cw0, cl0 = [0] * n, [0] * n, [0] * n, [0] * n
    for g in played:
        hw = float(g["home_score"]) > float(g["away_score"])
        same = g.get("conference_game") and confs.get(g["home"]) == confs.get(g["away"])
        for side, won in (("home", hw), ("away", not hw)):
            i = idx.get(g[side])
            if i is None:
                continue
            (w0 if won else l0)[i] += 1
            if same:
                (cw0 if won else cl0)[i] += 1

    # What an elite team would win against each schedule — the yardstick.
    elite = sorted(net, reverse=True)[ELITE_RANK - 1] if n >= ELITE_RANK else 0.0
    elite_w = [0.0] * n

    def opp_net(t):
        i = idx.get(t)
        return net[i] if i is not None else _net(ratings, t)
    for g in played + left:
        neutral = bool(g.get("neutral_site"))
        for side, other, sign in (("home", "away", 1), ("away", "home", -1)):
            i = idx.get(g[side])
            if i is None:
                continue
            m = (elite - opp_net(g[other])) + (0.0 if neutral else sign * hfa)
            elite_w[i] += min(0.98, max(0.02, _phi(m / max(sd, 1e-6))))

    # The games left, at our price.
    rem = []
    for g in left:
        h, a = g["home"], g["away"]
        p = win_prob(opp_net(h), opp_net(a), hfa, sd, bool(g.get("neutral_site")))
        same = bool(g.get("conference_game")) and confs.get(h) == confs.get(a) \
            and confs.get(h) in P4 + G6
        rem.append((idx.get(h), idx.get(a), p, same, g))

    # A title game ESPN has already set (both sides real, same conference).
    set_titles = {}
    for g in titles:
        h, a = g["home"], g["away"]
        c = confs.get(h)
        if c in P4 + G6 and confs.get(a) == c and h in idx and a in idx \
                and g.get("conference_game"):
            set_titles[c] = (idx[h], idx[a], g)
    members = defaultdict(list)
    for i, c in enumerate(conf_of):
        if c in P4 + G6:
            members[c].append(i)

    # Which coming games are watched for swing: today through the Saturday.
    d0 = _dt.date.fromisoformat(today[:10])
    sat = d0 + _dt.timedelta(days=(5 - d0.weekday()) % 7)
    swing_ix = [k for k, r in enumerate(rem)
                if today <= str(r[4].get("date") or "") <= sat.isoformat()
                and r[0] is not None and r[1] is not None]

    inn = [0] * n
    bye = [0] * n
    champ = [0] * n
    title = [0] * n
    won_out = [0] * n
    in_if_out = [0] * n
    seed_sum = [0] * n
    sw_n = {k: [0, 0] for k in swing_ix}
    sw_in = {k: (defaultdict(int), defaultdict(int)) for k in swing_ix}
    nd = idx.get(NOTRE_DAME)
    cands = [i for i in range(n) if conf_of[i] in P4 + G6 or conf_of[i] == INDEPENDENTS]

    for _ in range(sims):
        w, l = w0[:], l0[:]
        cw, cl = cw0[:], cl0[:]
        lost_left = [0] * n
        outcome = {}
        for k, (hi, ai, p, same, _g) in enumerate(rem):
            hw = rng.random() < p
            outcome[k] = hw
            for i, won in ((hi, hw), (ai, not hw)):
                if i is None:
                    continue
                if won:
                    w[i] += 1
                    if same:
                        cw[i] += 1
                else:
                    l[i] += 1
                    lost_left[i] += 1
                    if same:
                        cl[i] += 1
        bonus = [0.0] * n
        extra = [0.0] * n
        champs = {}
        for c, ms in members.items():
            if c in set_titles:
                a, b, _g = set_titles[c]
            else:
                top = sorted(ms, key=lambda i: (cl[i], -cw[i], -net[i], rng.random()))
                if len(top) < 2:
                    continue
                a, b = top[0], top[1]
            pa = win_prob(net[a], net[b], hfa, sd, neutral=True)
            win = a if rng.random() < pa else b
            lose = b if win == a else a
            w[win] += 1
            l[lose] += 1
            for i, o in ((a, b), (b, a)):
                extra[i] += min(0.98, max(0.02, _phi((elite - net[o]) / max(sd, 1e-6))))
            champs[c] = win
            bonus[win] = CHAMP_POINTS
            champ[win] += 1
        score = {i: WIN_POINTS * (w[i] - elite_w[i] - extra[i]) + net[i] + bonus[i]
                 for i in cands}
        order = sorted(cands, key=lambda i: -score[i])
        place = {i: r for r, i in enumerate(order)}
        field = {champs[c] for c in P4 if c in champs}
        g6 = next((i for i in order if conf_of[i] in G6), None)
        if g6 is not None:
            field.add(g6)
        if nd is not None and nd in place and place[nd] < FIELD:
            field.add(nd)
        for i in order:
            if len(field) >= FIELD:
                break
            field.add(i)
        seeds = sorted(field, key=lambda i: place[i])
        for s, i in enumerate(seeds, 1):
            inn[i] += 1
            seed_sum[i] += s
            if s <= BYES:
                bye[i] += 1
        for i in range(n):
            if lost_left[i] == 0:
                won_out[i] += 1
                if i in field:
                    in_if_out[i] += 1
        # The bracket, played: the first round at the higher seed, then neutral.
        if len(seeds) == FIELD:
            fr = []
            for hs, as_ in FIRST_ROUND:
                h, a = seeds[hs - 1], seeds[as_ - 1]
                fr.append(h if rng.random() < win_prob(net[h], net[a], hfa, sd) else a)
            qf = []
            for s, j in QUARTERS:
                h, a = seeds[s - 1], fr[j]
                qf.append(h if rng.random() < win_prob(net[h], net[a], hfa, sd, True) else a)
            sf = []
            for x, y in SEMIS:
                h, a = qf[x], qf[y]
                sf.append(h if rng.random() < win_prob(net[h], net[a], hfa, sd, True) else a)
            h, a = sf
            title[h if rng.random() < win_prob(net[h], net[a], hfa, sd, True) else a] += 1
        for k in swing_ix:
            r = 0 if outcome[k] else 1
            sw_n[k][r] += 1
            bucket = sw_in[k][r]
            for i in field:
                bucket[i] += 1

    def name(t):
        info = (teams or {}).get(t) or {}
        return info.get("nick") or info.get("name") or t

    ranks = ranks or {}
    chances, remaining, rows = {}, {}, []
    for i, t in enumerate(fbs):
        p_in = inn[i] / sims
        if p_in < MIN_SHOWN and t not in ranks:
            continue
        sched = []
        for hi, ai, p, _same, g in rem:
            if i not in (hi, ai):
                continue
            home = i == hi
            sched.append({"date": str(g.get("date") or ""), "opp": g["away"] if home else g["home"],
                          "home": home, "neutral": bool(g.get("neutral_site")),
                          "p": round(p if home else 1.0 - p, 3)})
        win_out = 1.0
        for s in sched:
            win_out *= s["p"]
        exp_w = w0[i] + sum(s["p"] for s in sched)
        chances[t] = {
            "playoff": round(p_in, 3), "bye": round(bye[i] / sims, 3),
            "conf": round(champ[i] / sims, 3), "title": round(title[i] / sims, 3),
            "win_out": round(win_out, 3),
            "in_if_win_out": (round(in_if_out[i] / won_out[i], 3) if won_out[i] else None),
            "seed": round(seed_sum[i] / inn[i], 1) if inn[i] else None,
            "proj": [round(exp_w, 1), round(w0[i] + l0[i] + len(sched) - exp_w, 1)],
        }
        remaining[t] = sched
        rows.append({"team": t, "name": name(t), "conference": conf_of[i],
                     "record": _record(w0[i], l0[i]), "conf_record": _record(cw0[i], cl0[i]),
                     "rank": ranks.get(t), "_p": p_in})
    rows.sort(key=lambda r: (-r["_p"], r["rank"] or 99))
    rows = rows[:SHOWN]
    shown = {r["team"] for r in rows}
    for r in rows:
        r.pop("_p")
    chances = {t: v for t, v in chances.items() if t in shown}
    remaining = {t: v for t, v in remaining.items() if t in shown}

    # HOW MUCH A GAME MOVES THE FIELD, as the expected change it makes:
    # each team's odds if the home side wins against if it loses, weighted
    # by how likely the game is to go either way (2·p·(1−p)) — a 97% lock
    # whose upset would wreck a contender is a big "if" and a small swing.
    # Moves under SWING_FLOOR and games too lopsided to have SWING_MIN_SIMS
    # draws on the short side are noise from a finite run, not a finding.
    swing = []
    for k in swing_ix:
        hi, ai, p, _same, g = rem[k]
        nh, na = sw_n[k]
        if min(nh, na) < SWING_MIN_SIMS:
            continue
        moves = []
        total = 0.0
        for i in set(sw_in[k][0]) | set(sw_in[k][1]):
            a, b = sw_in[k][0].get(i, 0) / nh, sw_in[k][1].get(i, 0) / na
            if abs(a - b) < SWING_FLOOR:
                continue
            total += 2.0 * p * (1.0 - p) * abs(a - b)
            moves.append({"team": fbs[i], "if_home": round(a, 3), "if_away": round(b, 3)})
        if not moves:
            continue                     # it moves nobody: not a swing game
        moves.sort(key=lambda m: -abs(m["if_home"] - m["if_away"]))
        swing.append({"date": str(g.get("date") or ""), "home": fbs[hi], "away": fbs[ai],
                      "home_name": name(fbs[hi]), "away_name": name(fbs[ai]),
                      "neutral": bool(g.get("neutral_site")), "p_home": round(p, 3),
                      "swing": round(total, 3), "moves": moves[:4]})
    swing.sort(key=lambda s: -s["swing"])

    return {
        "sport": "cfb", "season": season, "date": today, "sims": sims,
        "poll": poll or {"name": "the poll on the scoreboard", "kind": "scoreboard"},
        "format": {"field": FIELD, "byes": BYES, "auto": list(P4) + ["Group of Six"],
                   "first_round": [list(x) for x in FIRST_ROUND]},
        "today": bracket_today(fbs, conf_of, w0, l0, cw0, cl0, net, ranks, name),
        "teams": rows,
        "standings": standings(fbs, conf_of, w0, l0, cw0, cl0, ranks, name),
        "games_left": len(rem),
        "assumptions": {"win_points": WIN_POINTS, "champ_points": CHAMP_POINTS,
                        "elite_rank": ELITE_RANK, "home_field": round(hfa, 2),
                        "margin_sd": round(sd, 2)},
        # THE MODEL'S HALF — paid (gate.PAID_KEYS_BY_FILE["cfp_race.json"]).
        "chances": chances,
        "remaining": remaining,
        "swing": swing[:SWING_SHOWN],
    }


def _leaders(fbs, conf_of, cw0, cl0, net, ranks, conf):
    ms = [i for i, c in enumerate(conf_of) if c == conf]
    return sorted(ms, key=lambda i: (cl0[i], -cw0[i], ranks.get(fbs[i], 99), -net[i]))


def bracket_today(fbs, conf_of, w0, l0, cw0, cl0, net, ranks, name) -> dict:
    """The field if the season ended now: the poll as the ranking, today's
    conference leaders as the champions, the 2026 rules as the selection."""
    def rk(i):
        return ranks.get(fbs[i]) or 99
    pool = sorted(range(len(fbs)), key=lambda i: (rk(i), -net[i]))
    field, why = [], {}
    for c in P4:
        top = _leaders(fbs, conf_of, cw0, cl0, net, ranks, c)
        if top:
            field.append(top[0])
            why[top[0]] = f"{c} leader"
    g6 = next((i for i in pool if conf_of[i] in G6), None)
    if g6 is not None and g6 not in field:
        field.append(g6)
        why[g6] = "Group of Six's best"
    nd = fbs.index(NOTRE_DAME) if NOTRE_DAME in fbs else None
    if nd is not None and rk(nd) <= FIELD and nd not in field:
        field.append(nd)
        why[nd] = "Notre Dame, top 12"
    for i in pool:
        if len(field) >= FIELD:
            break
        if i not in field:
            field.append(i)
            why.setdefault(i, "at large")
    seeds = sorted(field, key=lambda i: (rk(i), -net[i]))
    out = [{"seed": s, "team": fbs[i], "name": name(fbs[i]), "rank": ranks.get(fbs[i]),
            "record": _record(w0[i], l0[i]), "conference": conf_of[i], "bid": why.get(i, "at large")}
           for s, i in enumerate(seeds, 1)]
    out_next = [i for i in pool if i not in field and ranks.get(fbs[i])][:4]
    return {"seeds": out,
            "first_four_out": [{"team": fbs[i], "name": name(fbs[i]), "rank": ranks.get(fbs[i]),
                                "record": _record(w0[i], l0[i])} for i in out_next]}


def standings(fbs, conf_of, w0, l0, cw0, cl0, ranks, name) -> dict:
    """Each Power Four and Group of Six conference, by conference record."""
    out = {}
    for c in P4 + G6:
        ms = [i for i, x in enumerate(conf_of) if x == c]
        ms.sort(key=lambda i: (cl0[i], -cw0[i], l0[i], -w0[i], ranks.get(fbs[i], 99)))
        if ms:
            out[c] = [{"team": fbs[i], "name": name(fbs[i]), "rank": ranks.get(fbs[i]),
                       "conf": _record(cw0[i], cl0[i]), "all": _record(w0[i], l0[i])} for i in ms]
    return out


def load_season(season: int, today: _dt.date) -> list:
    """The season's FBS slate off the scoreboard cache: settled days on the
    long TTL the futures board already keeps them under, the days around
    today short enough that last night's results are in."""
    from .sources import cfbdata
    lo = _dt.date(int(season), 8, 20)
    hi = ccg_start(season) + _dt.timedelta(days=3)
    near = today - _dt.timedelta(days=3)
    games = []
    if near > lo:
        games += cfbdata.load_range(lo.isoformat(), (near - _dt.timedelta(days=1)).isoformat(),
                                    ttl=24 * 3600)
    games += cfbdata.load_range(max(lo, near).isoformat(), hi.isoformat(), ttl=3 * 3600)
    return games


def publish(ratings: dict, fit, day: _dt.date, teams: dict | None = None,
            out_path: str = "web/data/cfp_race.json") -> str:
    """Build the race off the board's own ratings and write it through the
    gate. Returns the build-log line. In season only: before the first
    Saturday of September or after the title weekend there is no race."""
    from pathlib import Path
    from . import gate
    from .sources import cfbdata
    season = day.year
    if not (_dt.date(season, 9, 1) <= day <= ccg_start(season) + _dt.timedelta(days=3)):
        return "playoff race: out of season, not built"
    games = load_season(season, day)
    if not games:
        return "playoff race: no games read off the scoreboard, not built"
    poll = None
    ranks = None
    try:
        poll = cfbdata.parse_rankings(cfbdata.fetch_rankings())
        ranks = poll.pop("ranks", None) or None
    except Exception:                                         # noqa: BLE001
        poll = None
    if not ranks:
        ranks = current_ranks(games, day.isoformat())
        poll = {"name": "the poll on the scoreboard", "kind": "scoreboard"}
    out = build(games, ratings, float(fit.home_field), float(fit.margin_sd),
                day.isoformat(), ranks=ranks, poll=poll, teams=teams)
    out["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(out, p, p.name)
    top = ", ".join(f"{r['team']} {out['chances'][r['team']]['playoff']:.0%}"
                    for r in out["teams"][:4] if r["team"] in out["chances"])
    return (f"playoff race: {len(out['teams'])} contenders over {out['games_left']} "
            f"games left ({out['poll'].get('name')}) — {top}")
