#!/usr/bin/env python3
"""Grade the drive sim against seasons of real NFL finals — today.

The Weeks 1-4 forward journal is the seat decision, but five finished
seasons already sit in the cached schedule with closing spreads, totals
and final scores. This is the HISTORY ARM, simrecon.py's design ported
to the clock sports:

  * For every settled game, the sim replays the matchup off its closing
    line and states the four cover×over cell probabilities. The
    INCUMBENT states the same four cells from the sim's own marginals
    multiplied — so the two models differ ONLY in correlation, and a
    paired log-loss on the cell the real game landed in isolates
    exactly the joint structure the sim claims to add.
  * The verdict language is simrecon's: the sim EARNS consideration
    only if it beats independence by at least two standard errors of
    the paired difference. Anything less and independence keeps the
    seat — a tie is a loss for the challenger, because the challenger
    costs compute and complexity.
  * Alongside the verdict, the honesty numbers: realized margin sd vs
    the sim's, win-probability calibration by bucket, and how often
    finals land on the key numbers the {0,3,7} grain over-serves.

Pushes on either leg drop the game from the joint score (neither model
prices a push differently), but they are counted and reported.

    python3 drivesimrecon.py                    # last three seasons
    python3 drivesimrecon.py --seasons 2021 2022 2023 2024 2025
    python3 drivesimrecon.py --forward          # grade the build journal

The forward arm reads data/drivesim_log.jsonl (written by nfl_build
before kickoff) and grades every journaled claim whose final now
exists in the schedule — the same arithmetic, on claims that were
provably made in advance.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import drivesim

FLOOR = 1e-4          # a zero-probability cell is a log-loss singularity


class Tally:
    """Paired differences with their standard error — simrecon's shape."""

    def __init__(self):
        self.diffs = []

    def add(self, loss_sim: float, loss_indep: float) -> None:
        self.diffs.append(loss_sim - loss_indep)

    @property
    def n(self) -> int:
        return len(self.diffs)

    @property
    def mean(self) -> float:
        return sum(self.diffs) / self.n if self.n else 0.0

    @property
    def se(self) -> float:
        if self.n < 2:
            return float("inf")
        mu = self.mean
        var = sum((d - mu) ** 2 for d in self.diffs) / (self.n - 1)
        return math.sqrt(var / self.n)


def settled_games(seasons: list[int]) -> list[dict]:
    """Real finals with closing lines, in the sim's own conventions.
    nflverse's spread_line is positive when the HOME side is favored;
    the sim speaks home-negative, so the sign flips here and nowhere
    else."""
    from engine.sources import nflverse
    want = {str(s) for s in seasons}
    out = []
    for r in nflverse.load_schedules():
        if r.get("season") not in want:
            continue
        try:
            h = int(r.get("home_score"))
            a = int(r.get("away_score"))
            spread = -float(r.get("spread_line"))
            total = float(r.get("total_line"))
        except (TypeError, ValueError):
            continue
        out.append({"season": r.get("season"), "week": r.get("week"),
                    "home": r.get("home_team"), "away": r.get("away_team"),
                    "spread": spread, "total": total,
                    "margin": h - a, "points": h + a})
    return out


def outcome_cell(g: dict) -> tuple | None:
    """(covered, went_over) for the home side, or None on any push."""
    m, s, t = g["margin"], g["spread"], g["total"]
    if m + s == 0 or g["points"] == t:
        return None
    return (m + s > 0, g["points"] > t)


def grade(games: list[dict], trials: int = 4000,
          seed: int = 7) -> dict:
    """Score sim-joint vs independence on every gradable game.

    Cards are cached by half-point line pair — a season of games shares
    a handful of numbers, and the sim's answer depends on nothing else."""
    cards: dict[tuple, drivesim.SimCard] = {}
    tally = Tally()
    pushes = skipped = 0
    margins = []
    win_bins: dict[int, list[int]] = {}
    key_mass = 0
    for g in games:
        key = (round(g["spread"] * 2) / 2, round(g["total"] * 2) / 2)
        card = cards.get(key)
        if card is None:
            card = drivesim.simulate("nfl", key[0], key[1],
                                     trials=trials, seed=seed)
            cards[key] = card
        cell = outcome_cell(g)
        margins.append(g["margin"])
        if abs(g["margin"]) in (3, 7):
            key_mass += 1
        b = min(4, max(0, int(card.p_home_win * 5)))
        win_bins.setdefault(b, []).append(1 if g["margin"] > 0 else 0)
        if cell is None:
            pushes += 1
            continue
        jc = card.joint_cells(g["spread"], g["total"])
        if not jc["n"]:
            skipped += 1
            continue
        p_sim = max(FLOOR, jc["cells"].get(cell, 0.0))
        p_ind = max(FLOOR, jc["indep"].get(cell, 0.0))
        tally.add(-math.log(p_sim), -math.log(p_ind))
    mu = sum(margins) / len(margins) if margins else 0.0
    sd = (sum((m - mu) ** 2 for m in margins)
          / (len(margins) - 1)) ** 0.5 if len(margins) > 1 else 0.0
    sim_sd = (sum(c.margin_sd for c in cards.values())
              / len(cards)) if cards else 0.0
    return {"tally": tally, "pushes": pushes, "skipped": skipped,
            "cards": len(cards), "realized_margin_sd": sd,
            "sim_margin_sd": sim_sd,
            "key_number_share": key_mass / len(margins) if margins else 0.0,
            "win_bins": win_bins}


def verdict(tally: Tally) -> str:
    if tally.n < 200:
        return (f"NO CALL — only {tally.n} gradable games; the bar "
                f"needs a real sample.")
    d, se = tally.mean, tally.se
    if d < 0 and abs(d) >= 2 * se:
        return (f"THE JOINT EARNS CONSIDERATION — sim beats independence "
                f"by {abs(d):.4f} paired log-loss (≥2 SE, se {se:.4f}). "
                f"The forward journal still decides the seat.")
    if d > 0 and d >= 2 * se:
        return (f"INDEPENDENCE KEEPS THE SEAT — the sim's joint is WORSE "
                f"by {d:.4f} paired log-loss (≥2 SE, se {se:.4f}).")
    return (f"NO EDGE EITHER WAY — paired diff {d:+.4f} (se {se:.4f}); "
            f"a tie is a loss for the challenger, independence keeps "
            f"the seat.")


def forward_games() -> list[dict]:
    """The build journal's pre-kickoff claims, joined to finals that now
    exist. Last write per (date, home, away) wins, simjoint-style."""
    try:
        lines = open(drivesim.LOG_PATH, encoding="utf-8").read().splitlines()
    except OSError:
        return []
    claims: dict[tuple, dict] = {}
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        claims[(r.get("date"), r.get("home"), r.get("away"))] = r
    if not claims:
        return []
    seasons = {int(str(k[0])[:4]) for k in claims if k[0]}
    finals = {(g["home"], g["away"], g["season"]): g
              for g in settled_games(sorted(seasons | {s + 1 for s in seasons}))}
    out = []
    for (date, home, away), r in claims.items():
        f = finals.get((home, away, str(date)[:4]))
        if not f:
            continue
        out.append({**f, "spread": r["spread"], "total": r["total"]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="*",
                    default=[2023, 2024, 2025])
    ap.add_argument("--trials", type=int, default=4000)
    ap.add_argument("--forward", action="store_true",
                    help="grade the build journal instead of history")
    args = ap.parse_args(argv)
    games = forward_games() if args.forward else settled_games(args.seasons)
    label = "forward journal" if args.forward else \
        f"seasons {', '.join(map(str, args.seasons))}"
    if not games:
        print(f"Nothing to grade for {label} — "
              + ("the journal is empty or nothing has settled."
                 if args.forward else "is the schedule cache present?"))
        return 1
    r = grade(games, trials=args.trials)
    t = r["tally"]
    print(f"Drive-sim reconciliation · {label} · {len(games)} finals · "
          f"{r['cards']} distinct lines · {args.trials:,} trials each")
    print(f"  gradable {t.n} · pushes dropped {r['pushes']} · "
          f"degenerate {r['skipped']}")
    print(f"  margin sd — real {r['realized_margin_sd']:.1f} · "
          f"sim {r['sim_margin_sd']:.1f}")
    print(f"  finals on 3 or 7 — {100 * r['key_number_share']:.1f}% of games")
    print("  win-prob calibration (sim bucket → real home win rate):")
    for b in sorted(r["win_bins"]):
        xs = r["win_bins"][b]
        print(f"    {b * 20:>3}–{b * 20 + 20}%  n={len(xs):<4} "
              f"real {100 * sum(xs) / len(xs):.0f}%")
    print(f"\n  {verdict(t)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
