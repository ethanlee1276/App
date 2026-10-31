#!/usr/bin/env python3
"""Who makes an NBA game's first basket, and what predicts it — run on the box.

    cd /srv/qellys && sudo -u qellys python3 tools/first_basket_study.py
    sudo -u qellys python3 tools/first_basket_study.py --db data/history.db

Ethan, 2026-10-31: "I only want our long shot picks to be stuff like first
basket score for NBA or first touchdown score for NFL ... use all of our
data and tools to figure out ... who would be the best, most likely" — and
not by the book's shortest price. The football half is
docs/FIRST_TD_RESEARCH.md; this is the basketball half's measurement.

WHAT IT READS, read-only: the box's every NBA shot (`nba_shots`: game,
action order, period, player, team, made). The first basket is the game's
first MADE field goal by action order; the team of the game's first shot
stands in for who had the first possession (the opening tip). No price is
read: this asks what our data can say, before any price.

WHAT IT ANSWERS, each fitted on every season but the last and scored on the
last, so every figure is a held-out one:

  1. how often the team with the first shot makes the first basket — the
     tip's whole value;
  2. whether a team's history of getting the first shot predicts it (a
     centre who wins tips is a real, lasting skill — or not);
  3. which player share picks the scorer among his team's players: his
     share of its shots, of its made shots, of its first-quarter shots, of
     its shots in the first three minutes, and blends;
  4. the whole model's calibration.

Standard library only. Writes nothing.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "history.db"


def _clock_s(clock) -> float:
    """Seconds left in the period from "PT11M45.00S" or "11:45"; -1 unknown."""
    c = str(clock or "")
    try:
        if c.startswith("PT"):
            m, s = c[2:].rstrip("S").split("M")
            return int(m) * 60 + float(s)
        if ":" in c:
            m, s = c.split(":")
            return int(m) * 60 + float(s)
    except ValueError:
        pass
    return -1.0


def games_from(rows) -> list:
    """rows: (game_id, action, season, date, player, team, home, period, clock, made) in any
    order → one dict a game: its shots in action order, home/away, the first shot's team and
    the first basket's (player, team)."""
    by: dict = defaultdict(list)
    for r in rows:
        by[r[0]].append(r)
    out = []
    for gid, shots in by.items():
        shots.sort(key=lambda r: int(r[1]))
        home = next((r[5] for r in shots if r[6] in (1, "1", True)), None)
        away = next((r[5] for r in shots if r[6] in (0, "0", False)), None)
        if not home or not away:
            continue
        made = next((r for r in shots if r[9] in (1, "1", True)), None)
        out.append({"gid": gid, "season": int(shots[0][2]), "date": shots[0][3], "home": home, "away": away,
                    "first_shot": shots[0][5], "first": (made[4], made[5]) if made else None,
                    "shots": [(r[4], r[5], int(r[7] or 0), _clock_s(r[8]), r[9] in (1, "1", True)) for r in shots]})
    out.sort(key=lambda g: (g["date"] or "", g["gid"]))
    return out


SHARES = {
    "shots": lambda s: True,
    "q1 shots": lambda s: s[2] == 1,
    "first 3 minutes": lambda s: s[2] == 1 and s[3] >= 540,
}


def share_events(games, blend: dict, eps: float = 0.02) -> list:
    """For each team that made the first basket of its own: the scorer and
    every one of its shooters' prior-only blended share (this season; last
    season at half weight). ``blend`` maps a SHARES key (or "made") to its
    weight."""
    tot = defaultdict(lambda: defaultdict(float))
    out = []
    for g in games:
        for team in (g["home"], g["away"]):
            mine = [s for s in g["shots"] if s[1] == team]
            players = {s[0] for s in mine}
            first_made = next((s[0] for s in mine if s[4]), None)
            if first_made and players:
                sc = {}
                for p in players:
                    v = eps
                    for m, w in blend.items():
                        own = tot[(p, g["season"])][m] + 0.5 * tot[(p, g["season"] - 1)][m]
                        tm = tot[(p, g["season"])][m + "_t"] + 0.5 * tot[(p, g["season"] - 1)][m + "_t"]
                        v += w * (own / tm if tm else 0.0)
                    sc[p] = v
                z = sum(sc.values())
                out.append({"season": g["season"], "p": sc[first_made] / z})
            counts = {m: defaultdict(int) for m in list(SHARES) + ["made"]}
            for s in mine:
                for m, keep in SHARES.items():
                    if keep(s):
                        counts[m][s[0]] += 1
                if s[4]:
                    counts["made"][s[0]] += 1
            for m, c in counts.items():
                team_total = sum(c.values())
                for p in players:
                    tot[(p, g["season"])][m] += c.get(p, 0)
                    tot[(p, g["season"])][m + "_t"] += team_total
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    a = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rows = conn.execute("SELECT game_id, action, season, date, player, team, home, period, clock, made "
                        "FROM nba_shots").fetchall()
    games = [g for g in games_from(rows) if g["first"]]
    if not games:
        print("no NBA shots on file")
        return 0
    seasons = sorted({g["season"] for g in games})
    test = seasons[-1]
    print(f"{len(games)} games with a basket, seasons {seasons[0]}-{test}; held out: {test}\n")

    # 1. The tip's value.
    fs = sum(g["first"][1] == g["first_shot"] for g in games) / len(games)
    home = sum(g["first"][1] == g["home"] for g in games) / len(games)
    print(f"the team with the game's first shot makes the first basket {fs:.1%}; the home team {home:.1%}")

    # 2. Does a team's history of the first shot predict the next one?
    hist = defaultdict(lambda: [0, 0])
    pairs = []
    for g in games:
        h, aw = hist[(g["season"], g["home"])], hist[(g["season"], g["away"])]
        rh = (h[0] + 2) / (h[1] + 4)
        ra = (aw[0] + 2) / (aw[1] + 4)
        p = rh / (rh + ra)                      # the home side's chance of the first shot
        pairs.append((g["season"], p, g["first_shot"] == g["home"]))
        h[1] += 1
        aw[1] += 1
        h[0] += g["first_shot"] == g["home"]
        aw[0] += g["first_shot"] == g["away"]
    te = [(p, y) for s, p, y in pairs if s == test]
    ll = lambda p, y: -math.log(max(1e-9, p if y else 1 - p))  # noqa: E731
    print(f"who shoots first (held out, {len(te)} games): coin {sum(ll(.5, y) for _, y in te) / len(te):.4f}"
          f" · each team's history {sum(ll(p, y) for p, y in te) / len(te):.4f}")

    # 3. Which player.
    print("\nwhich player (held out, log loss of the scorer among his team's shooters):")
    for name, blend in (("share of shots", {"shots": 1.0}), ("share of made shots", {"made": 1.0}),
                        ("share of first-quarter shots", {"q1 shots": 1.0}),
                        ("share of first-3-minute shots", {"first 3 minutes": 1.0}),
                        ("1/2 shots + 1/2 first-quarter shots", {"shots": .5, "q1 shots": .5}),
                        ("1/3 shots, 1/3 made, 1/3 first 3 minutes", {"shots": 1 / 3, "made": 1 / 3, "first 3 minutes": 1 / 3})):
        ev = [e for e in share_events(games, blend) if e["season"] == test]
        if ev:
            print(f"  {name:42s} {sum(-math.log(e['p']) for e in ev) / len(ev):.4f}  ({len(ev)} team first baskets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
