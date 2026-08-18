"""Possession-level Monte Carlo for the clock sports — NFL first.

Ethan, 2026-08-18: "for every bet we analyze for every sport, are we
running simulations and running the games and bets 1000s of times
over?" MLB already was — engine/mlb/gamesim.py bats every lineup
20,000 times. This module is the same idea for the sports that run on
a clock: each game is re-played TRIALS times, drive by drive (NFL,
CFB) or possession by possession (NBA, WNBA), and every probability
the card reports is a count over those runs.

WHAT THE SIM IS FOR — AND WHAT IT IS NOT. The marginals are anchored
to the market's own line: each team's expected points are the implied
points from the spread and total, so on any single market the sim
REPRODUCES the line rather than arguing with it (the analytic models
own the arguing, and they are calibrated). What the replay adds is
everything JOINT — the shape of the margin, the correlation between
covering and the over, the probability of a blowout — structure a
closed-form single-market price cannot carry. That is exactly the
division of labor the MLB sim settled.

THE SEAT MUST BE EARNED. ``ENABLED`` ships False: nothing here touches
a published price until a live-slate reconciliation — the simrecon.py
discipline, run over real NFL weeks — shows the sim's joints beating
the correlation priors by the same paired log-loss bar the MLB sim
faces. Until then the build journals the sim's claims next to each
priced game so September can grade them.

Honest crudeness, v1, written down rather than hidden:
  * Football drives score {0, 3, 7}: extra points are folded into the
    7, two-point tries and safeties are ignored. Real margins also land
    on 6 and 8; ours cluster slightly harder on 3 and 7.
  * Ties resolve by a strength-weighted coin flip plus a field goal
    (an overtime in miniature). The NFL's rare real tie is ignored.
  * Basketball possessions are independent, so the simulated margin
    runs wider than the empirical one (garbage time pulls real games
    in). The reconciliation decides whether that shape needs a shrink
    before it may price anything.

Run one game by hand:

    python3 -m engine.drivesim --sport nfl --spread -3.5 --total 47
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field

#: Nothing prices off this module until the live reconciliation says the
#: joints beat the priors. The journal below records regardless — the
#: evidence has to exist before the verdict can.
ENABLED = False

LOG_PATH = os.path.join("data", "drivesim_log.jsonl")

TRIALS = 20000

#: Per-sport shape. `units` is possessions per team per game; `score_mix`
#: is what a SCORING possession is worth: (points, share-of-scores).
#: Football's 60/40 TD/FG split and basketball's 12/66/22 one/two/three
#: mix are league constants measured from recent seasons — they set the
#: grain of the score, while the LINE sets the level.
SPORTS = {
    "nfl":  {"units": 11.0, "units_sd": 1.0,
             "score_mix": ((7, 0.60), (3, 0.40))},
    "cfb":  {"units": 12.0, "units_sd": 1.2,
             "score_mix": ((7, 0.62), (3, 0.38))},
    "nba":  {"units": 99.0, "units_sd": 3.0,
             "score_mix": ((1, 0.12), (2, 0.66), (3, 0.22))},
    "wnba": {"units": 81.0, "units_sd": 3.0,
             "score_mix": ((1, 0.12), (2, 0.66), (3, 0.22))},
}


def implied_points(spread: float, total: float) -> tuple[float, float]:
    """(home, away) expected points from the market's two numbers.
    Spread is the home line: negative means home favored."""
    home = total / 2.0 - spread / 2.0
    away = total / 2.0 + spread / 2.0
    return home, away


def _score_value(mix) -> float:
    return sum(p * w for p, w in mix)


def _team_game(rng, units: int, p_score: float, mix) -> int:
    pts = 0
    for _ in range(units):
        if rng.random() < p_score:
            roll = rng.random()
            for p, w in mix:
                roll -= w
                if roll <= 0:
                    pts += p
                    break
            else:
                pts += mix[-1][0]
    return pts


@dataclass
class SimCard:
    """One game, TRIALS times over. Everything here is a tally."""
    sport: str
    spread: float
    total: float
    trials: int
    margins: list = field(repr=False, default_factory=list)   # home − away
    totals: list = field(repr=False, default_factory=list)

    def _mean(self, xs):
        return sum(xs) / len(xs) if xs else 0.0

    @property
    def p_home_win(self) -> float:
        return sum(1 for m in self.margins if m > 0) / self.trials

    @property
    def margin_mean(self) -> float:
        return self._mean(self.margins)

    @property
    def margin_sd(self) -> float:
        mu = self.margin_mean
        return (self._mean([(m - mu) ** 2 for m in self.margins])) ** 0.5

    @property
    def total_mean(self) -> float:
        return self._mean(self.totals)

    @property
    def total_sd(self) -> float:
        mu = self.total_mean
        return (self._mean([(t - mu) ** 2 for t in self.totals])) ** 0.5

    def p_cover(self, line: float | None = None) -> dict:
        """Home side against the spread line: cover / no / push shares."""
        line = self.spread if line is None else line
        c = sum(1 for m in self.margins if m + line > 0)
        p = sum(1 for m in self.margins if m + line == 0)
        return {"cover": c / self.trials, "push": p / self.trials,
                "no": (self.trials - c - p) / self.trials}

    def p_over(self, line: float | None = None) -> dict:
        line = self.total if line is None else line
        o = sum(1 for t in self.totals if t > line)
        p = sum(1 for t in self.totals if t == line)
        return {"over": o / self.trials, "push": p / self.trials,
                "under": (self.trials - o - p) / self.trials}

    def joint_cells(self, spread_line: float | None = None,
                    total_line: float | None = None) -> dict:
        """All four cover×over cells over the same runs, pushes dropped
        from both legs — what a reconciliation needs to score the sim's
        joint against a real game's outcome. Keys are (covered, went_over);
        "n" is the effective run count. `indep` is the same four cells
        rebuilt from the marginals alone, so the two models differ ONLY
        in correlation and a paired score isolates exactly that."""
        sl = self.spread if spread_line is None else spread_line
        tl = self.total if total_line is None else total_line
        counts = {(True, True): 0, (True, False): 0,
                  (False, True): 0, (False, False): 0}
        n = 0
        for m, t in zip(self.margins, self.totals):
            if m + sl == 0 or t == tl:
                continue
            n += 1
            counts[(m + sl > 0, t > tl)] += 1
        if not n:
            return {"cells": {}, "indep": {}, "n": 0}
        cells = {k: v / n for k, v in counts.items()}
        pc = cells[(True, True)] + cells[(True, False)]
        po = cells[(True, True)] + cells[(False, True)]
        indep = {(True, True): pc * po, (True, False): pc * (1 - po),
                 (False, True): (1 - pc) * po,
                 (False, False): (1 - pc) * (1 - po)}
        return {"cells": cells, "indep": indep, "n": n}

    def joint(self, spread_line: float | None = None,
              total_line: float | None = None) -> dict:
        """The 2×2 the parlay math needs: cover × over, counted over the
        SAME runs, pushes dropped from both legs. `independent` is what
        multiplying the marginals would claim — the gap is the sim's
        whole contribution."""
        sl = self.spread if spread_line is None else spread_line
        tl = self.total if total_line is None else total_line
        n = cc = 0
        c1 = o1 = 0
        for m, t in zip(self.margins, self.totals):
            if m + sl == 0 or t == tl:
                continue
            n += 1
            cov = m + sl > 0
            ovr = t > tl
            c1 += cov
            o1 += ovr
            cc += cov and ovr
        if not n:
            return {"cover_and_over": 0.0, "independent": 0.0, "lift": 0.0}
        both = cc / n
        indep = (c1 / n) * (o1 / n)
        return {"cover_and_over": both, "independent": indep,
                "lift": both - indep}


def simulate(sport: str, spread: float, total: float,
             trials: int = TRIALS, seed: int | None = 7) -> SimCard:
    """Re-play one game `trials` times. Deterministic by default, same
    convention as the MLB sim: a seeded run is a number someone else can
    reproduce, and an unseeded one is a number nobody can check."""
    cfg = SPORTS[sport]
    rng = random.Random(seed)
    mix = cfg["score_mix"]
    value = _score_value(mix)
    home_mu, away_mu = implied_points(spread, total)
    base_units = cfg["units"]
    card = SimCard(sport=sport, spread=spread, total=total, trials=trials)
    hoops = len(mix) == 3
    for _ in range(trials):
        units = max(3, round(rng.gauss(base_units, cfg["units_sd"])))
        # The pace draw is SHARED: both teams play the same game. Scoring
        # rates are solved per trial so expected points stay the implied
        # points whatever pace was drawn.
        ph = min(0.9, home_mu / units / value)
        pa = min(0.9, away_mu / units / value)
        h = _team_game(rng, units, ph, mix)
        a = _team_game(rng, units, pa, mix)
        if h == a:
            if hoops:
                # Overtime: five extra possessions each until broken.
                while h == a:
                    h += _team_game(rng, 5, ph, mix)
                    a += _team_game(rng, 5, pa, mix)
            else:
                # A miniature overtime: the stronger side wins a field
                # goal at its share of expected points.
                if rng.random() < home_mu / (home_mu + away_mu):
                    h += 3
                else:
                    a += 3
        card.margins.append(h - a)
        card.totals.append(h + a)
    return card


def journal_records(games: list[dict], sport: str,
                    trials: int = 4000) -> list[dict]:
    """The sim's claims for tonight's priced games, one record each, for
    the reconciliation to grade against finals. Fewer trials than a hand
    run — this rides a build with a timeout guillotine, and 4,000 puts
    ±0.8% on a probability, plenty to grade a forward journal."""
    out = []
    for g in games or []:
        spread, total = g.get("spread"), g.get("total")
        if spread is None or total is None:
            continue
        try:
            card = simulate(sport, float(spread), float(total),
                            trials=trials)
        except (KeyError, ValueError):
            continue
        j = card.joint()
        out.append({
            "sport": sport, "date": g.get("date") or "",
            "home": g.get("home") or "", "away": g.get("away") or "",
            "spread": float(spread), "total": float(total),
            "trials": trials,
            "p_home_win": round(card.p_home_win, 4),
            "p_home_cover": round(card.p_cover()["cover"], 4),
            "p_over": round(card.p_over()["over"], 4),
            "p_cover_and_over": round(j["cover_and_over"], 4),
            "joint_lift": round(j["lift"], 4),
            "margin_sd": round(card.margin_sd, 2),
        })
    return out


def journal(records: list[dict]) -> None:
    """Append tonight's claims for the reconciliation to grade later.
    Never fatal, never chatty — same contract as simjoint's journal: a
    box where data/ is missing builds exactly as it would have."""
    if not records:
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
    except OSError:
        pass


def _card_text(card: SimCard) -> str:
    cov = card.p_cover()
    ovr = card.p_over()
    j = card.joint()
    home_mu, away_mu = implied_points(card.spread, card.total)
    return "\n".join([
        f"{card.sport.upper()} · spread {card.spread:+.1f} · "
        f"total {card.total:.1f} · {card.trials:,} runs",
        f"  implied points   home {home_mu:.1f} · away {away_mu:.1f}",
        f"  simulated points home {(card.total_mean + card.margin_mean) / 2:.1f} · "
        f"away {(card.total_mean - card.margin_mean) / 2:.1f}",
        f"  home win {100 * card.p_home_win:.1f}%",
        f"  home covers {100 * cov['cover']:.1f}%  "
        f"(push {100 * cov['push']:.1f}%)",
        f"  over {100 * ovr['over']:.1f}%  (push {100 * ovr['push']:.1f}%)",
        f"  cover AND over {100 * j['cover_and_over']:.1f}%  vs "
        f"{100 * j['independent']:.1f}% if independent  "
        f"(lift {100 * j['lift']:+.1f}pt)",
        f"  margin sd {card.margin_sd:.1f} · total sd {card.total_sd:.1f}",
    ])


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=sorted(SPORTS), default="nfl")
    ap.add_argument("--spread", type=float, required=True,
                    help="home line; negative = home favored")
    ap.add_argument("--total", type=float, required=True)
    ap.add_argument("--trials", type=int, default=TRIALS)
    args = ap.parse_args(argv)
    print(_card_text(simulate(args.sport, args.spread, args.total,
                              trials=args.trials)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
