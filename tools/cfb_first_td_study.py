#!/usr/bin/env python3
"""Who scores a college game's first touchdown, and what predicts it — the
college half of docs/FIRST_TD_RESEARCH.md, from cfbfastR's play-by-play.

    python3 tools/cfb_first_td_study.py               # 2021 through 2026
    python3 tools/cfb_first_td_study.py 2021 2026     # another first and last season

Ethan, 2026-10-31: "I only want our long shot picks to be stuff like first
basket score for NBA or first touchdown score for NFL ... I guess only
college football, NFL, and NBA would have that right now. But I also want
to start implementing that too."

WHAT IT READS. sportsdataverse's cfbfastR play-by-play, one CSV a season on
GitHub's release server (the same host the schedules come from), streamed
once and boiled down to what this needs — each game's teams and line, every
player's carries and targets, every touchdown in order — and kept in
data/cache/cfb_first_td_<season>.csv so a rerun reads a few megabytes
instead of half a gigabyte. FBS against FBS only, the games books price.

WHAT IT ANSWERS, the NFL study's questions on college games, each fitted on
every season but the last two and scored on those two:

  1. how often an offence scores the first touchdown, and the favourite;
  2. which team: the home edge in points from the line (the spread is the
     home side's, negative when home is favoured), as a logistic fit;
  3. which player on that team: his share of its carries and targets, of
     its touchdowns, and the NFL's blend of the two;
  4. the whole model's calibration on the held-out games.

Standard library only. Writes nothing but its own cache.
"""
from __future__ import annotations

import csv
import io
import math
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
URL = ("https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
       "cfbfastR_cfb_pbp/play_by_play_{season}.csv")
YES = ("1", "TRUE", "True", "true", "1.0")
#: The share floor, the NFL study's (engine/firsttd.EPS) until the training
#: seasons say otherwise — the run prints the floors it tried.
EPS_GRID = (0.02, 0.04, 0.06, 0.08)
BANDS = ((0.0, 0.02), (0.02, 0.05), (0.05, 0.08), (0.08, 0.12), (0.12, 0.18), (0.18, 1.0))


#: Words of play text, never of a name: the parser's leftovers.
NOT_A_NAME = ("intended", "incomplete", "pass", "thrown", "caught", "broken up", "team", "penalty")


def real_name(who: str) -> bool:
    """A player's name, not the play-by-play's leftovers — "intended" and
    "pass. Pass incomplete intended" in every season (an incompletion the
    parser could not name), and from 2025 ESPN's new play text: "#21
    J.Theodore caught at 09", "#10 D.Scudero thrown to 13"."""
    w = (who or "").strip()
    if not w or not w[0].isupper() or any(c.isdigit() or c == "#" for c in w):
        return False
    low = w.lower()
    return not low.endswith(" to") and not any(x in low for x in NOT_A_NAME)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def slim(reader) -> dict:
    """One pass over a season's plays → {game id: game}, each game its
    teams, line, every player's carries + targets, and its touchdowns in
    play order."""
    games: dict = {}
    for r in reader:
        gid = r.get("game_id")
        if not gid:
            continue
        g = games.get(gid)
        if g is None:
            g = games[gid] = {
                "season": int(float(r.get("year") or r.get("season") or 0)),
                "week": int(float(r.get("week") or 0)), "type": r.get("season_type") or "",
                "home": r.get("home") or "", "away": r.get("away") or "",
                "fbs": (r.get("home_team_division") == "fbs" and r.get("away_team_division") == "fbs"),
                "spread": _f(r.get("spread")), "usage": Counter(), "tds": []}
        if g["spread"] is None:
            g["spread"] = _f(r.get("spread"))
        team = r.get("pos_team") or ""
        if r.get("rush") in YES and real_name(r.get("rusher_player_name")):
            g["usage"][(team, r["rusher_player_name"])] += 1
        if r.get("target") in YES and real_name(r.get("receiver_player_name")):
            g["usage"][(team, r["receiver_player_name"])] += 1
        if r.get("touchdown") in YES:
            n = int(float(r.get("game_play_number") or 0))
            if r.get("rush_td") in YES:
                g["tds"].append((n, team, r.get("rusher_player_name") or "", True))
            elif r.get("pass_td") in YES:
                g["tds"].append((n, team, r.get("receiver_player_name") or "", True))
            elif r.get("defense_score_play") in YES:
                g["tds"].append((n, r.get("def_pos_team") or "", "", False))
            elif r.get("offense_score_play") in YES:
                g["tds"].append((n, team, "", False))       # a return the offence ran back
    for g in games.values():
        g["tds"].sort()
    return games


def _write(path: Path, games: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for gid, g in games.items():
            w.writerow(["G", gid, g["season"], g["week"], g["type"], g["home"], g["away"], int(g["fbs"]),
                        "" if g["spread"] is None else g["spread"]])
            for (team, who), n in g["usage"].items():
                w.writerow(["U", gid, team, who, n])
            for n, team, who, off in g["tds"]:
                w.writerow(["T", gid, n, team, who, int(off)])


def _read(path: Path) -> dict:
    games: dict = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if row[0] == "G":
                games[row[1]] = {"season": int(row[2]), "week": int(row[3]), "type": row[4], "home": row[5],
                                 "away": row[6], "fbs": row[7] == "1", "spread": _f(row[8]),
                                 "usage": Counter(), "tds": []}
            elif row[0] == "U":
                if real_name(row[3]):
                    games[row[1]]["usage"][(row[2], row[3])] += int(row[4])
            elif row[0] == "T":
                games[row[1]]["tds"].append((int(row[2]), row[3], row[4], row[5] == "1"))
    return games


def season(year: int, cache: Path = CACHE) -> dict:
    """A season's games, from the cache or streamed once and cached."""
    path = cache / f"cfb_first_td_{year}.csv"
    if path.exists():
        return _read(path)
    with urllib.request.urlopen(URL.format(season=year), timeout=120) as resp:
        games = slim(csv.DictReader(io.TextIOWrapper(resp, encoding="utf-8", newline="")))
    cache.mkdir(parents=True, exist_ok=True)
    _write(path, games)
    return games


def ll(p, y) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -math.log(p if y else 1 - p)


def fit_logistic(rows, iters=3000, lr=0.05):
    """logit P(home scores the first TD) = a + b × home edge / 7."""
    a = b = 0.0
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in rows:
            p = 1 / (1 + math.exp(-(a + b * x)))
            ga += p - y
            gb += (p - y) * x
        a -= lr * ga / len(rows)
        b -= lr * gb / len(rows)
    return a, b


def share_events(games, blend: dict, eps: float, test_from: int) -> list:
    """For every team that scored an offensive touchdown: each of its
    players' prior-only share (season to date, last season at half weight)
    and whether he scored the team's first one."""
    tot = defaultdict(lambda: defaultdict(float))      # (team, player, season) -> counts
    out = []
    for g in games:
        for team in (g["home"], g["away"]):
            players = {who: n for (t, who), n in g["usage"].items() if t == team}
            if not players:
                continue
            tds = [who for _n, t, who, off in g["tds"] if off and t == team and who]
            if g["season"] >= test_from - 2:
                sc = {}
                for who in players:
                    s = eps
                    for m, w in blend.items():
                        own = tot[(team, who, g["season"])][m] + 0.5 * tot[(team, who, g["season"] - 1)][m]
                        tm = tot[(team, "", g["season"])][m] + 0.5 * tot[(team, "", g["season"] - 1)][m]
                        s += w * (own / tm if tm else 0.0)
                    sc[who] = s
                z = sum(sc.values())
                ok = bool(tds) and tds[0] in players
                out.append({"season": g["season"], "p": sc[tds[0]] / z if ok else None, "scored": ok,
                            "shares": {k: v / z for k, v in sc.items()}, "game": g, "team": team})
            team_touch = sum(players.values())
            for who, n in players.items():
                tot[(team, who, g["season"])]["touch"] += n
                tot[(team, who, g["season"])]["td"] += tds.count(who)
            tot[(team, "", g["season"])]["touch"] += team_touch
            tot[(team, "", g["season"])]["td"] += len(tds)
    return out


def main(argv=None) -> int:
    args = [int(a) for a in (argv if argv is not None else sys.argv[1:])[:2]]
    first, last = (args + [2021, 2026])[:2] if args else (2021, 2026)
    allg = []
    for y in range(first, last + 1):
        g = season(y)
        allg += [x for x in g.values() if x["fbs"] and x["type"] == "regular"]
        print(f"  {y}: {sum(1 for x in g.values() if x['fbs'] and x['type'] == 'regular')} FBS regular-season games")
    allg.sort(key=lambda g: (g["season"], g["week"]))
    scored = [g for g in allg if g["tds"]]
    test_from = last - 1
    print(f"\n{len(allg)} FBS games, {first}-{last}; held out: {test_from}-{last}\n")

    # 1. The base rates.
    off = [g for g in scored if g["tds"][0][3]]
    print(f"a touchdown in {len(scored) / len(allg):.1%} of games; the first one an offence's {len(off) / len(scored):.1%}")
    fav = [g for g in scored if g["spread"]]
    print(f"the favourite scores it {sum(g['tds'][0][1] == (g['home'] if g['spread'] < 0 else g['away']) for g in fav) / len(fav):.1%}")

    # 2. Which team: the line's home edge.
    rows = [(g, -g["spread"] / 7.0, g["tds"][0][1] == g["home"]) for g in scored if g["spread"] is not None]
    tr = [(x, y) for g, x, y in rows if g["season"] < test_from]
    te = [(x, y) for g, x, y in rows if g["season"] >= test_from]
    a, b = fit_logistic(tr)
    coin = sum(ll(0.5, y) for _, y in te) / len(te)
    lines = sum(ll(1 / (1 + math.exp(-(a + b * x))), y) for x, y in te) / len(te)
    print(f"\nwhich team (held out, {len(te)} games): coin {coin:.4f} · the lines {lines:.4f}"
          f" (logit {a:+.3f} {b:+.3f} x home edge / 7)")
    off_share = len([g for g in scored if g["season"] < test_from and g["tds"][0][3]]) / max(
        1, len([g for g in scored if g["season"] < test_from]))

    # 3. Which player.
    print("\nwhich player (held out, log loss of the scorer among his team's players):")
    best_eps, best = None, None
    for eps in EPS_GRID:
        ev = [e for e in share_events(allg, {"touch": 2 / 3, "td": 1 / 3}, eps, test_from)
              if e["season"] < test_from and e["scored"]]
        v = sum(-math.log(e["p"]) for e in ev) / len(ev) if ev else 9
        if best is None or v < best:
            best_eps, best = eps, v
    print(f"  share floor chosen on the training seasons: {best_eps}")
    for name, blend in (("touchdown share", {"td": 1.0}), ("carries + targets share", {"touch": 1.0}),
                        ("2/3 volume + 1/3 touchdowns", {"touch": 2 / 3, "td": 1 / 3})):
        ev = [e for e in share_events(allg, blend, best_eps, test_from) if e["season"] >= test_from and e["scored"]]
        print(f"  {name:28s} {sum(-math.log(e['p']) for e in ev) / len(ev):.4f}  ({len(ev)} team first touchdowns)")

    # 4. The whole model on the held-out games: every player who played, on
    # both sides of every game, scored or not.
    pick = min((("touchdown share", {"td": 1.0}), ("carries + targets share", {"touch": 1.0}),
                ("2/3 volume + 1/3 touchdowns", {"touch": 2 / 3, "td": 1 / 3})),
               key=lambda kv: sum(-math.log(e["p"]) for e in share_events(allg, kv[1], best_eps, test_from)
                                  if e["season"] < test_from and e["scored"]))
    print(f"  chosen on the training seasons: {pick[0]}")
    ev = share_events(allg, pick[1], best_eps, test_from)
    seen = defaultdict(list)                                 # band -> (p, scored)
    tops = []
    lls, lls_eq = [], []
    for e in [e for e in ev if e["season"] >= test_from and e["game"]["tds"]]:
        g = e["game"]
        x = -g["spread"] / 7.0 if g["spread"] is not None else 0.0
        ph = 1 / (1 + math.exp(-(a + b * x)))
        pt = ph if e["team"] == g["home"] else 1 - ph
        first = g["tds"][0]
        n = len(e["shares"])
        for who, s in e["shares"].items():
            p = off_share * pt * s
            hit = first[3] and first[1] == e["team"] and first[2] == who
            lls.append(ll(p, hit))
            lls_eq.append(ll(off_share * pt / n, hit))
            if p >= 0.18:
                tops.append((round(p, 3), who, e["team"], g["season"], g["week"], hit))
            for lo, hi in BANDS:
                if lo <= p < hi:
                    seen[(lo, hi)].append((p, hit))
    print(f"\nthe whole model (an offence's share {off_share:.3f} × the team's chance × his share), "
          "every held-out player who played:")
    for (lo, hi), xs in sorted(seen.items()):
        print(f"  we said {lo:.0%}-{hi:.0%}: {sum(p for p, _ in xs) / len(xs):5.1%} said, "
              f"{sum(h for _, h in xs) / len(xs):5.1%} scored first, {len(xs)} player-games")
    print(f"  log loss {sum(lls) / len(lls):.4f} against {sum(lls_eq) / len(lls_eq):.4f} for every player alike")
    late = defaultdict(list)
    for e in [e for e in ev if e["season"] >= test_from and e["game"]["tds"] and e["game"]["week"] >= 4]:
        g = e["game"]
        x = -g["spread"] / 7.0 if g["spread"] is not None else 0.0
        ph = 1 / (1 + math.exp(-(a + b * x)))
        pt = ph if e["team"] == g["home"] else 1 - ph
        first = g["tds"][0]
        for who, s in e["shares"].items():
            p = off_share * pt * s
            hit = first[3] and first[1] == e["team"] and first[2] == who
            for lo, hi in BANDS:
                if lo <= p < hi:
                    late[(lo, hi)].append((p, hit))
    print("  from week 4 on, when this season's games carry the shares:")
    for (lo, hi), xs in sorted(late.items()):
        print(f"    we said {lo:.0%}-{hi:.0%}: {sum(p for p, _ in xs) / len(xs):5.1%} said, "
              f"{sum(h for _, h in xs) / len(xs):5.1%} scored first, {len(xs)} player-games")
    print(f"  the players we put at 18%+ ({len(tops)}), first ten:")
    for t in sorted(tops, reverse=True)[:10]:
        print("   ", t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
