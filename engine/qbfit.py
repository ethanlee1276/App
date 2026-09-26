"""What a missing starting quarterback does to his team's other players: measured.

Ethan, 2026-09-23: "there is a lot of starting qbs out in the nfl right now
so I wanna make sure the models notice that and we show that".

engine/nflinfo.py already asked the GAME question and the answer was that
the closing line prices a QB change fully. This asks the PLAYER question
the close does not answer for us: when a team's established starter does
not play, what happens to its receivers, tight ends and backs?

The established starter going into week w: the team's leading passer in
attempts over weeks before w, with at least two starts. He is OUT when he
has no passing attempt that week. The REPLACEMENT is whoever led the
team's attempts. His TIER is read the way the board can read it before
kickoff — from passes he threw BEFORE that week (this season and last):

    similar    50+ earlier attempts, yards per attempt at least
               SIMILAR_RATIO of the starter's
    downgrade  below that, or under 50 earlier attempts (the rookie, the
               career backup): measured, and these two behave alike

For every top-three WR, TE and RB by volume with three earlier games, the
multiplier is the ratio of actual to own-average in starter-out games of
that tier over the same ratio in every other game. Standard library only.
"""
from __future__ import annotations

import math
from collections import defaultdict

SIMILAR_RATIO = 0.90
MIN_ATTEMPTS = 50
FIRST_WEEK = 4
#: market -> (the player's column, form floor)
MARKETS = {"rec_yds": ("receiving_yards", 15.0), "receptions": ("receptions", 1.5),
           "rush_yds": ("rushing_yards", 15.0), "anytime_td": (("receiving_tds", "rushing_tds"), 0.0)}
GROUPS = ("WR", "TE", "RB")


def _f(r: dict, k: str) -> float:
    try:
        return float(r.get(k) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _v(r: dict, col) -> float:
    return sum(_f(r, c) for c in col) if isinstance(col, tuple) else _f(r, col)


def _team(r: dict) -> str:
    return str(r.get("team") or r.get("recent_team") or "")


def _regular(r: dict) -> bool:
    return str(r.get("season_type") or "REG") in ("REG", "")


def passing_before(seasons: dict, season: int, week: int) -> dict:
    """{name: (attempts, yards)} for every QB, this season before ``week`` and all of last season."""
    out: dict = defaultdict(lambda: [0.0, 0.0])
    for s in (season - 1, season):
        for r in seasons.get(s) or []:
            if not _regular(r) or str(r.get("position") or "").upper() != "QB":
                continue
            if s == season and int(_f(r, "week")) >= week:
                continue
            a = out[r["player_display_name"]]
            a[0] += _f(r, "attempts")
            a[1] += _f(r, "passing_yards")
    return {k: tuple(v) for k, v in out.items()}


def tier_of(passing: dict, starter: str, replacement: str) -> tuple:
    """(tier, starter ypa, replacement ypa or None)."""
    sa, sy = passing.get(starter, (0.0, 0.0))
    ra, ry = passing.get(replacement, (0.0, 0.0))
    s_ypa = sy / sa if sa else None
    r_ypa = ry / ra if ra >= MIN_ATTEMPTS else None
    if s_ypa and r_ypa and r_ypa >= SIMILAR_RATIO * s_ypa:
        return "similar", s_ypa, r_ypa
    return "downgrade", s_ypa, r_ypa


def samples(seasons: dict) -> list[dict]:
    """[{"season", "m", "g", "e", "y", "tier"}] — tier None for a game with its usual starter."""
    out = []
    for season, rows in sorted(seasons.items()):
        rows = [r for r in rows if _regular(r)]
        by_tw: dict = defaultdict(list)
        games: dict = defaultdict(dict)
        for r in rows:
            wk = int(_f(r, "week"))
            by_tw[(_team(r), wk)].append(r)
            games[(_team(r), r["player_display_name"])][wk] = r
        weeks = sorted({w for _t, w in by_tw})
        for team in sorted({t for t, _w in by_tw}):
            for wk in weeks:
                if wk < FIRST_WEEK or (team, wk) not in by_tw:
                    continue
                att, starts = defaultdict(float), defaultdict(int)
                for w in range(1, wk):
                    qbs = [r for r in by_tw.get((team, w), []) if str(r.get("position")) == "QB"]
                    for r in qbs:
                        att[r["player_display_name"]] += _f(r, "attempts")
                    if qbs:
                        starts[max(qbs, key=lambda r: _f(r, "attempts"))["player_display_name"]] += 1
                if not att:
                    continue
                starter = max(att, key=att.get)
                if starts[starter] < 2:
                    continue
                now = {r["player_display_name"]: r for r in by_tw[(team, wk)] if str(r.get("position")) == "QB"}
                tier = None
                if now and (starter not in now or _f(now[starter], "attempts") == 0):
                    rep = max(now.values(), key=lambda r: _f(r, "attempts"))["player_display_name"]
                    tier = tier_of(passing_before(seasons, season, wk), starter, rep)[0]
                vol: dict = {}
                for (t, name), g in games.items():
                    if t != team:
                        continue
                    pos = str(next(iter(g.values())).get("position") or "").upper()
                    if pos in GROUPS:
                        vol[(pos, name)] = sum(_f(g[w], "targets") + (_f(g[w], "carries") if pos == "RB" else 0.0)
                                               for w in g if w < wk)
                ranked: dict = defaultdict(list)
                for (pos, name), _v0 in sorted(vol.items(), key=lambda kv: -kv[1]):
                    ranked[pos].append(name)
                for pos, names in ranked.items():
                    for name in names[:3]:
                        g = games[(team, name)]
                        prev = [g[w] for w in sorted(g) if w < wk]
                        if len(prev) < 3 or wk not in g:
                            continue
                        for m, (col, floor) in MARKETS.items():
                            if m == "rush_yds" and pos != "RB":
                                continue
                            e = sum(_v(p, col) for p in prev) / len(prev)
                            if e < floor or (m == "anytime_td" and e <= 0):
                                continue
                            out.append({"season": season, "m": m, "g": pos, "e": e, "y": _v(g[wk], col),
                                        "tier": tier})
    return out


def measure(pts: list[dict]) -> dict:
    """{(market, group, tier): {"mult", "se", "n", "per": {season: mult}}} against games with the usual starter."""
    base_by: dict = defaultdict(lambda: [0.0, 0.0])
    base_s: dict = defaultdict(lambda: [0.0, 0.0])
    for p in pts:
        if p["tier"] is None:
            base_by[(p["m"], p["g"])][0] += p["y"]
            base_by[(p["m"], p["g"])][1] += p["e"]
            base_s[(p["m"], p["g"], p["season"])][0] += p["y"]
            base_s[(p["m"], p["g"], p["season"])][1] += p["e"]
    out = {}
    for key in sorted({(p["m"], p["g"], p["tier"]) for p in pts if p["tier"]}):
        m, g, _tier = key
        on = [p for p in pts if (p["m"], p["g"], p["tier"]) == key]
        by, be = base_by[(m, g)]
        if not be or not by or len(on) < 2:
            continue
        base = by / be
        mult = (sum(p["y"] for p in on) / sum(p["e"] for p in on)) / base
        rr = [p["y"] / p["e"] for p in on if p["e"] > 0]
        mu = sum(rr) / len(rr)
        se = math.sqrt(sum((x - mu) ** 2 for x in rr) / (len(rr) - 1)) / math.sqrt(len(rr)) / base
        per = {}
        for s in sorted({p["season"] for p in on}):
            o = [p for p in on if p["season"] == s]
            sy, se_ = base_s[(m, g, s)]
            if o and se_ and sy and sum(p["e"] for p in o):
                per[s] = round((sum(p["y"] for p in o) / sum(p["e"] for p in o)) / (sy / se_), 3)
        out[key] = {"mult": round(mult, 3), "se": round(se, 3), "n": len(on), "per": per}
    return out


def shipped(result: dict) -> dict:
    """THE RULE: a multiplier is applied where it sits two standard errors
    from 1.0 AND at least three of the seasons point the same way (one
    season carrying a pooled number is not an effect — RB rushing behind
    a similar backup measured ×1.10 ± .05 on the back of 2022 alone);
    otherwise the card shows the change and the number is left alone.
    {(market, group, tier): multiplier}."""
    out = {}
    for k, v in result.items():
        side = [x for x in v["per"].values() if (x < 1.0) == (v["mult"] < 1.0) and x != 1.0]
        if abs(v["mult"] - 1.0) >= 2 * v["se"] and len(side) >= min(3, len(v["per"])):
            out[k] = v["mult"]
    return out
