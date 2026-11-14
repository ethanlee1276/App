#!/usr/bin/env python3
"""Who scores a game's first touchdown, and what predicts it — every number in
docs/FIRST_TD_RESEARCH.md, from the nflverse play-by-play.

    python3 tools/first_td_study.py              # 2021 through the current season
    python3 tools/first_td_study.py 2021 2026    # another first and last season

Ethan, 2026-10-31: "use all of our data and tools to figure out how we can
figure out who would be the best, most likely, first touchdown scorer for
each game ... not just off of book lines."

Reads the app's own cached play-by-play reader (engine/sources/nflpbp), the
same rows the NFL model reads. Regular season only. Fits on every season but
the last two and scores on those two, so each number below is a held-out
one. Standard library only; reads nothing else and writes nothing.
"""
from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COLS = ["game_id", "season", "season_type", "week", "home_team", "away_team", "posteam", "qtr",
        "fixed_drive", "play_type", "touchdown", "td_team", "td_player_name", "td_player_id",
        "pass_touchdown", "rush_touchdown", "kickoff_attempt", "receiver_player_id",
        "receiver_player_name", "rusher_player_id", "rusher_player_name", "spread_line", "total_line"]

ONE = ("1", "1.0")
#: The share floor (engine/firsttd.EPS), chosen on the training seasons.
EPS = 0.04


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def games_from(plays) -> list:
    """Per game: teams, lines, who received the opening kickoff, every
    touchdown in order, and each player's carries + targets."""
    games: dict = {}
    for r in plays:
        if r.get("season_type") != "REG":
            continue
        g = games.get(r["game_id"])
        if g is None:
            g = games[r["game_id"]] = {"season": int(float(r["season"])), "week": int(float(r["week"])),
                                       "home": r["home_team"], "away": r["away_team"],
                                       "spread": _f(r.get("spread_line")), "receiver": None, "tds": [],
                                       "usage": defaultdict(lambda: {"touch": 0, "team": None, "name": None})}
        if g["receiver"] is None and str(r.get("kickoff_attempt")) in ONE and str(r.get("qtr")) in ONE:
            g["receiver"] = r.get("posteam") or None
        if r.get("play_type") in ("run", "pass"):
            for idk, namek in (("rusher_player_id", "rusher_player_name"), ("receiver_player_id", "receiver_player_name")):
                pid = r.get(idk)
                if pid and pid != "NA":
                    u = g["usage"][pid]
                    u["touch"] += 1
                    u["team"], u["name"] = r.get("posteam"), r.get(namek)
        if str(r.get("touchdown")) in ONE and r.get("td_team") not in (None, "", "NA"):
            off = r["td_team"] == r.get("posteam") and (str(r.get("pass_touchdown")) in ONE
                                                       or str(r.get("rush_touchdown")) in ONE)
            g["tds"].append({"team": r["td_team"], "pid": r.get("td_player_id"), "offense": off,
                             "qtr": int(float(r.get("qtr") or 0))})
    out = list(games.values())
    out.sort(key=lambda g: (g["season"], g["week"]))
    return out


def ll(p, y) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -math.log(p if y else 1 - p)


def fit_logistic(rows, feats, y, iters=2500, lr=0.05):
    w = [0.0] * (len(feats) + 1)
    for _ in range(iters):
        g = [0.0] * len(w)
        for r in rows:
            x = [1.0] + [f(r) for f in feats]
            p = 1 / (1 + math.exp(-sum(a * b for a, b in zip(w, x))))
            for i, xi in enumerate(x):
                g[i] += (p - y(r)) * xi
        w = [a - lr * b / len(rows) for a, b in zip(w, g)]
    return w


def predict(w, feats, r) -> float:
    x = [1.0] + [f(r) for f in feats]
    return 1 / (1 + math.exp(-sum(a * b for a, b in zip(w, x))))


def share_events(games, blend):
    """For every team that scored an offensive touchdown: its first scorer and
    each of its players' prior-only share (season to date, last season at
    half weight), under ``blend`` {"touch": w, "td": w}."""
    tot = defaultdict(lambda: defaultdict(float))     # (pid, season) -> {touch, td, touch_t, td_t}
    events = []
    for g in games:
        for team in (g["home"], g["away"]):
            players = {pid: u for pid, u in g["usage"].items() if u["team"] == team}
            if not players:
                continue
            tds = [t["pid"] for t in g["tds"] if t["offense"] and t["team"] == team and t["pid"] not in (None, "NA")]
            if tds and tds[0] in players:
                sc = {}
                for pid in players:
                    s = EPS
                    for m, w in blend.items():
                        own = tot[(pid, g["season"])][m] + 0.5 * tot[(pid, g["season"] - 1)][m]
                        tm = tot[(pid, g["season"])][m + "_t"] + 0.5 * tot[(pid, g["season"] - 1)][m + "_t"]
                        s += w * (own / tm if tm else 0.0)
                    sc[pid] = s
                z = sum(sc.values())
                events.append({"season": g["season"], "p": sc[tds[0]] / z})
            team_touch = sum(u["touch"] for u in players.values())
            for pid, u in players.items():
                d = tot[(pid, g["season"])]
                d["touch"] += u["touch"]
                d["touch_t"] += team_touch
                d["td"] += tds.count(pid)
                d["td_t"] += len(tds)
    return events


def main(argv=None) -> int:
    from engine.sources import nflpbp
    args = [int(a) for a in (argv if argv is not None else sys.argv[1:])[:2]]
    first, last = (args + [2021, 2026])[:2] if args else (2021, 2026)
    plays = (r for s in range(first, last + 1) for r in nflpbp.load_pbp_rows(s, columns=COLS))
    games = games_from(plays)
    scored = [g for g in games if g["tds"]]
    test_from = last - 1
    print(f"{len(games)} regular-season games, {first}-{last}; held out: {test_from}-{last}\n")

    # 1. The base rates.
    off = [g for g in scored if g["tds"][0]["offense"]]
    print(f"a touchdown in {len(scored) / len(games):.1%} of games; the first one an offence's {len(off) / len(scored):.1%}")
    print("first touchdown by quarter:", dict(sorted(Counter(g["tds"][0]["qtr"] for g in scored).items())))
    rec = [g for g in scored if g["receiver"]]
    print(f"the team receiving the opening kickoff scores it {sum(g['tds'][0]['team'] == g['receiver'] for g in rec) / len(rec):.1%}")
    fav = [g for g in scored if g["spread"]]
    print(f"the favourite scores it {sum(g['tds'][0]['team'] == (g['home'] if g['spread'] > 0 else g['away']) for g in fav) / len(fav):.1%}")

    # 2. Which team: the lines, and the actual receiver (known only at the toss).
    rows = [{"dimp": g["spread"] / 7, "recv": 1.0 if g["receiver"] == g["home"] else -1.0,
             "y": g["tds"][0]["team"] == g["home"], "season": g["season"]}
            for g in scored if g["spread"] is not None and g["receiver"]]
    tr = [r for r in rows if r["season"] < test_from]
    te = [r for r in rows if r["season"] >= test_from]
    f1 = [lambda r: r["dimp"]]
    f2 = [lambda r: r["dimp"], lambda r: r["recv"]]
    w1, w2 = fit_logistic(tr, f1, lambda r: r["y"]), fit_logistic(tr, f2, lambda r: r["y"])
    coin = sum(ll(0.5, r["y"]) for r in te) / len(te)
    l1 = sum(ll(predict(w1, f1, r), r["y"]) for r in te) / len(te)
    l2 = sum(ll(predict(w2, f2, r), r["y"]) for r in te) / len(te)
    print(f"\nwhich team (held out, {len(te)} games): coin {coin:.4f} · the lines {l1:.4f}"
          f" (logit {w1[0]:+.3f} {w1[1]:+.3f} x home edge / 7) · after the toss {l2:.4f}")

    # 3. Which player: shares of his team's first touchdowns.
    print("\nwhich player (held out, log loss of the scorer among his team's players):")
    for name, blend in (("touchdown share", {"td": 1.0}), ("carries + targets share", {"touch": 1.0}),
                        ("2/3 volume + 1/3 touchdowns", {"touch": 2 / 3, "td": 1 / 3})):
        ev = [e for e in share_events(games, blend) if e["season"] >= test_from]
        print(f"  {name:28s} {sum(-math.log(e['p']) for e in ev) / len(ev):.4f}  ({len(ev)} team first touchdowns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
