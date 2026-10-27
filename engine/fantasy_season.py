"""Your league's season: playoff odds, power rankings, last week in review.

Ethan, 2026-10-27: "look at other apps … add more features and what our
fantasy room should actually be doing". FantasyPros, ESPN and Yahoo show a
linked league's playoff odds and power rankings, and Yahoo and the recap
apps send a weekly review (docs/FANTASY.md, items 5 and 8). The desk knew
the standings and this week's game, and nothing about the rest of the
season or the week just played.

THE ODDS ARE SIMULATED, NOT GUESSED: the rest of the regular season played
SIMS times on the league's own schedule (Sleeper's matchups for each week
left), each team's week drawn around its best lineup's points under the
league's own scoring (fantasy_h2h.team_total on this season's averages; a
player whose team is on a bye that week scores nothing), with the spread
its starters' own week-to-week swings give it. This week is scored on this
week's projections when the desk has them. Then the league's own table:
wins (a tie is half), then points for. A median league (Sleeper's
league_average_match) also plays the league's median every week.

THE ASSUMPTIONS, said: each roster as it stands today plays out the season
(no trades, no pickups, no injury beyond this week's report), and team
weeks are independent normals (fantasy_h2h says why that is the standard
approximation and where it is worst).

POWER RANKINGS put the teams in order of how good they are now: each
roster's best lineup a week on this season's averages. Beside it the
ALL-PLAY record, every team's score each week against every other team's
(its record without the schedule's luck), and LUCK, the wins it has above
what its all-play rate says.

THE WEEK IN REVIEW reads last week's box from Sleeper: each team's score
against the best lineup it could have set from its own players' points
(points left on the bench), your best and worst calls, and the league's
awards.

Standard library only. Pure: every input is handed in.
"""
from __future__ import annotations

import math
import random

from .fantasy_h2h import team_total
from .fantasy_lineup import _eligible, assign

#: Seasons simulated.
SIMS = 2000
#: A team whose starters carry no measured spread still swings this much a
#: week, about the smallest a nine-man lineup's week-to-week spread runs.
MIN_TEAM_SD = 15.0
#: The parts of a player's line a bye zeroes.
PARTS = ("fp_ppr", "receptions", "rec_yds", "rush_yds", "pass_yds", "pass_td", "pass_int",
         "rush_td", "rec_td")


def _zero(m: dict) -> dict:
    out = dict(m or {})
    for k in PARTS:
        if k in out:
            out[k] = 0.0
    out["_sd"], out["_sd_basis"] = 0.0, "zero"
    return out


def strengths(rosters: dict, slots: list, scoring: dict, means: dict, *,
              off: set | None = None, team_of: dict | None = None) -> dict:
    """{roster id: (points, spread)}: each roster's best lineup a week and its
    spread. A player whose NFL team is in ``off`` (on a bye that week) is
    zeroed first, so his team plays the week without him."""
    out = {}
    for rid, rows in (rosters or {}).items():
        m = means
        if off:
            m = dict(means or {})
            for r in rows or []:
                name = r.get("player")
                if (team_of or {}).get(name) in off and name in m:
                    m[name] = _zero(m[name])
        t = team_total(rows, slots, scoring, m)
        out[rid] = (float(t["points"]), max(MIN_TEAM_SD, math.sqrt(float(t["variance"] or 0.0))))
    return out


def schedule_from(matchups: list) -> list:
    """[(roster a, roster b)] from one week of Sleeper's matchups: the rows
    sharing a matchup_id play each other; a row with none has no game."""
    by: dict = {}
    for m in matchups or []:
        mid = m.get("matchup_id")
        if mid is not None and m.get("roster_id") is not None:
            by.setdefault(mid, []).append(int(m["roster_id"]))
    return [tuple(sorted(v)) for _k, v in sorted(by.items()) if len(v) == 2]


def _table(wins: dict, pf: dict) -> list:
    return sorted(wins, key=lambda r: (-wins[r], -pf[r], r))


def simulate(teams: dict, schedule: dict, strength: dict, *, playoff_teams: int,
             median: bool = False, sims: int = SIMS, seed: int = 0, me=None) -> dict:
    """The rest of the regular season, ``sims`` times.

    ``teams`` {roster id: {wins, losses, ties, pf}} now; ``schedule`` {week:
    [(a, b)]} for the weeks left; ``strength`` {week: {roster id: (points,
    spread)}}. Returns {"teams": {rid: {playoff, first, wins, losses, seed}},
    "paths": [{wins, of, share, playoff}]} where ``paths`` is ``me``'s
    playoff chance by how many of his games left he wins."""
    rng = random.Random(seed)
    ids = sorted(teams)
    weeks = sorted(w for w in schedule if schedule[w])
    acc = {r: {"playoff": 0, "first": 0, "wins": 0.0, "losses": 0.0, "seed": 0} for r in ids}
    games_me = sum(1 for w in weeks for g in schedule[w] if me in g) + (len(weeks) if median and me in teams else 0)
    paths: dict = {}
    for _ in range(max(1, sims)):
        wins = {r: float(teams[r].get("wins") or 0) + 0.5 * float(teams[r].get("ties") or 0) for r in ids}
        losses = {r: float(teams[r].get("losses") or 0) + 0.5 * float(teams[r].get("ties") or 0) for r in ids}
        pf = {r: float(teams[r].get("pf") or 0) for r in ids}
        mine = 0.0
        for w in weeks:
            st = strength.get(w) or {}
            score = {r: rng.gauss(*st[r]) if r in st else 0.0 for r in ids}
            for r in ids:
                pf[r] += score[r]
            for a, b in schedule[w]:
                if a not in score or b not in score:
                    continue
                if score[a] == score[b]:
                    wins[a] += .5; wins[b] += .5; losses[a] += .5; losses[b] += .5
                    mine += .5 if me in (a, b) else 0
                    continue
                win, lose = (a, b) if score[a] > score[b] else (b, a)
                wins[win] += 1; losses[lose] += 1
                if win == me:
                    mine += 1
            if median and len(ids) > 1:
                cut = sorted(score.values())[len(ids) // 2 - (0 if len(ids) % 2 else 1)]
                for r in ids:
                    if score[r] > cut:
                        wins[r] += 1
                        mine += 1 if r == me else 0
                    else:
                        losses[r] += 1
        table = _table(wins, pf)
        for i, r in enumerate(table, 1):
            a = acc[r]
            a["seed"] += i
            a["wins"] += wins[r]
            a["losses"] += losses[r]
            if i <= playoff_teams:
                a["playoff"] += 1
            if i == 1:
                a["first"] += 1
        if me in acc:
            k = int(round(mine))
            got = paths.setdefault(k, [0, 0])
            got[0] += 1
            got[1] += 1 if table.index(me) < playoff_teams else 0
    n = float(max(1, sims))
    out = {r: {"playoff": round(a["playoff"] / n, 3), "first": round(a["first"] / n, 3),
               "wins": round(a["wins"] / n, 1), "losses": round(a["losses"] / n, 1),
               "seed": round(a["seed"] / n, 1)} for r, a in acc.items()}
    return {"teams": out, "games_left": games_me,
            "paths": [{"wins": k, "of": games_me, "share": round(v[0] / n, 3),
                       "playoff": round(v[1] / v[0], 3)} for k, v in sorted(paths.items(), reverse=True)]}


def all_play(weekly: dict) -> dict:
    """{roster id: {w, l, t}}: each week's score against every other team's
    score that week, over ``weekly`` {week: {roster id: points}}."""
    out: dict = {}
    for _w, pts in sorted((weekly or {}).items()):
        live = {r: float(p) for r, p in pts.items() if p is not None}
        if len(live) < 2 or not any(live.values()):
            continue
        for r, p in live.items():
            rec = out.setdefault(r, {"w": 0, "l": 0, "t": 0})
            for o, q in live.items():
                if o == r:
                    continue
                rec["w" if p > q else "l" if p < q else "t"] += 1
    return out


def power(teams: dict, strength_now: dict, ap: dict) -> list:
    """The teams in order of how good they are now (best lineup a week on
    this season's averages), with the all-play record and luck: wins above
    what the all-play rate gives over the games played."""
    rows = []
    for rid, t in (teams or {}).items():
        w, l, ti = int(t.get("wins") or 0), int(t.get("losses") or 0), int(t.get("ties") or 0)
        rec = ap.get(rid) or {}
        games = w + l + ti
        tot = sum(rec.values()) if rec else 0
        rate = (rec.get("w", 0) + 0.5 * rec.get("t", 0)) / tot if tot else None
        rows.append({"roster_id": rid, "strength": round(float((strength_now.get(rid) or (0.0, 0.0))[0]), 1),
                     "all_play": rec or None, "all_play_rate": None if rate is None else round(rate, 3),
                     "luck": None if rate is None or not games else round(w + 0.5 * ti - rate * games, 1)})
    rows.sort(key=lambda r: (-r["strength"], r["roster_id"]))
    for i, r in enumerate(rows, 1):
        r["power"] = i
    return rows


# --- the week in review --------------------------------------------------------------------

def _best(pids: list, pts: dict, who, slots: list) -> tuple[float, dict]:
    rows = []
    for pid in pids or []:
        name, pos = who(pid)
        if name:
            rows.append({"pid": pid, "player": name, "position": pos, "points": float(pts.get(pid) or 0.0)})
    seat = assign(rows, slots)
    return round(sum(p["points"] for p in seat.values()), 2), seat


def review(matchups: list, who, slots: list, names: dict, me=None) -> dict | None:
    """Last week, from Sleeper's box for it: every team's score against the
    best lineup it could have set from its own players' points, the
    league's awards, and ``me``'s best and worst calls.

    ``who(pid)`` is (name, position); ``names`` {roster id: team name}."""
    rows = [m for m in matchups or [] if m.get("roster_id") is not None]
    if not rows or not any(float(m.get("points") or 0) for m in rows):
        return None
    teams = {}
    for m in rows:
        rid = int(m["roster_id"])
        pts = {str(k): float(v or 0) for k, v in (m.get("players_points") or {}).items()}
        starters = [str(p) for p in m.get("starters") or []]
        score = round(float(m.get("points") or 0), 2)
        # A box with no player points (Sleeper leaves them off a roster
        # now and then) has no best lineup to measure against: no award
        # for it, and no "left on the bench".
        best = _best([str(p) for p in m.get("players") or []], pts, who, slots)[0] if pts else None
        teams[rid] = {"roster_id": rid, "team": names.get(rid) or f"Team {rid}", "points": score,
                      "best": None if best is None else max(best, score),
                      "left": None if best is None else round(max(0.0, best - score), 2),
                      "matchup_id": m.get("matchup_id"), "starters": starters, "pts": pts,
                      "bench": [str(p) for p in m.get("players") or [] if str(p) not in starters]}
    games = []
    for a, b in schedule_from(rows):
        ta, tb = teams[a], teams[b]
        win, lose = (ta, tb) if ta["points"] >= tb["points"] else (tb, ta)
        games.append({"winner": win["team"], "loser": lose["team"], "w_pts": win["points"], "l_pts": lose["points"],
                      "margin": round(win["points"] - lose["points"], 2), "tie": ta["points"] == tb["points"],
                      "w_id": win["roster_id"], "l_id": lose["roster_id"]})
    T = list(teams.values())
    awards = []

    def add(key, title, text):
        awards.append({"key": key, "title": title, "text": text})
    hi = max(T, key=lambda t: t["points"])
    add("top", "Top score", f"{hi['team']}, {hi['points']:.1f}")
    lo = min(T, key=lambda t: t["points"])
    add("low", "Lowest score", f"{lo['team']}, {lo['points']:.1f}")
    decided = [g for g in games if not g["tie"]]
    if decided:
        g = max(decided, key=lambda g: g["margin"])
        add("blowout", "Biggest blowout", f"{g['winner']} over {g['loser']} by {g['margin']:.1f}")
        g = min(decided, key=lambda g: g["margin"])
        add("close", "Closest game", f"{g['winner']} over {g['loser']} by {g['margin']:.1f}")
        g = max(decided, key=lambda g: g["l_pts"])
        add("unlucky", "Unluckiest loss", f"{g['loser']} scored {g['l_pts']:.1f} and lost")
        g = min(decided, key=lambda g: g["w_pts"])
        add("lucky", "Luckiest win", f"{g['winner']} won with {g['w_pts']:.1f}")
    measured = [t for t in T if t["left"] is not None]
    if measured:
        sharp = min(measured, key=lambda t: (t["left"], -t["points"]))
        perfect = [t for t in measured if t["left"] < 0.05]
        add("sharp", "Sharpest lineup",
            f"{sharp['team']} left {sharp['left']:.1f} on the bench" if not perfect else
            f"{sharp['team']} set the best lineup it could" if len(perfect) == 1 else
            f"{sharp['team']} and {len(perfect) - 1} other{'s' if len(perfect) > 2 else ''} set the best "
            f"lineup they could")
        lazy = max(measured, key=lambda t: t["left"])
        if lazy["left"] > 0:
            add("bench", "Most left on the bench", f"{lazy['team']}, {lazy['left']:.1f}")
    star = max(((t, p) for t in T for p in t["starters"] if who(p)[0]), key=lambda tp: tp[0]["pts"].get(tp[1], 0.0),
               default=None)
    if star:
        add("mvp", "Player of the week", f"{who(star[1])[0]}, {star[0]['pts'].get(star[1], 0.0):.1f} for {star[0]['team']}")
    pine = max(((t, p) for t in T for p in t["bench"] if who(p)[0]), key=lambda tp: tp[0]["pts"].get(tp[1], 0.0),
               default=None)
    if pine and pine[0]["pts"].get(pine[1], 0.0) > 0:
        add("pine", "Best on a bench", f"{who(pine[1])[0]}, {pine[0]['pts'].get(pine[1], 0.0):.1f} on {pine[0]['team']}'s bench")
    out = {"awards": awards, "teams": sorted(({k: t[k] for k in ("roster_id", "team", "points", "best", "left")}
                                               for t in T), key=lambda t: -t["points"])}
    if me is not None and me in teams:
        out["me"] = _mine(teams[me], teams, games, who, slots)
    return out


def _mine(t: dict, teams: dict, games: list, who, slots: list) -> dict:
    """Your week: the result, what you left on the bench, and the one call
    that cost the most and the one that paid the most."""
    g = next((g for g in games if t["roster_id"] in (g["w_id"], g["l_id"])), None)
    out = {"points": t["points"], "best": t["best"], "left": t["left"]}
    if g:
        won = g["w_id"] == t["roster_id"]
        opp = teams[g["l_id"] if won else g["w_id"]]
        out.update({"result": "T" if g["tie"] else "W" if won else "L", "opponent": opp["team"],
                    "opp_points": opp["points"]})
    slot_of = {p: slots[i] for i, p in enumerate(t["starters"]) if i < len(slots)}
    pts = t["pts"]
    worst = best = None
    for s, slot in slot_of.items():
        sname = who(s)[0]
        if not sname:
            continue
        alts = [b for b in t["bench"] if who(b)[0] and _eligible(slot, who(b)[1])]
        if not alts:
            continue
        top = max(alts, key=lambda b: pts.get(b, 0.0))
        diff = pts.get(s, 0.0) - pts.get(top, 0.0)
        call = {"started": sname, "started_pts": round(pts.get(s, 0.0), 1),
                "benched": who(top)[0], "benched_pts": round(pts.get(top, 0.0), 1), "diff": round(abs(diff), 1)}
        if diff < 0 and (worst is None or -diff > worst["diff"]):
            worst = call
        if diff > 0 and (best is None or diff > best["diff"]):
            best = call
    if worst:
        margin = (out.get("opp_points") or 0) - t["points"]
        worst["would_have_won"] = bool(out.get("result") == "L" and worst["diff"] > margin)
        out["worst_call"] = worst
    if best:
        out["best_call"] = best
    return out
