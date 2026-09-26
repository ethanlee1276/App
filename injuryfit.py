#!/usr/bin/env python3
"""Re-measure the injury knock-on rules (engine/injuryfit.py).

    python3 injuryfit.py                       # 2022-2024
    python3 injuryfit.py --seasons 2021-2024

Reads data/cache/player_stats_<season>.csv (the NFL build's box scores) and
the weekly injury reports and depth charts through the build's own loaders,
and prints, per rule in engine/injuries.KNOCK_ONS (plus the ones measured
and dropped), the multiplier in use against the one the games show.

Seasons whose depth charts are dated snapshots rather than weekly (2025 on)
cannot say who started in a past week, so they are left out by default.
Change KNOCK_ONS only when a re-run says to, and say so in the commit.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from engine import injuryfit as F
from engine.injuries import KNOCK_ONS, KnockOn

ROOT = Path(__file__).resolve().parent

#: Measured and taken out of KNOCK_ONS, kept so a re-run can say whether
#: the games have changed their mind.
DROPPED = (
    KnockOn("ol_out_qb", "own", frozenset({"LT", "OT"}), frozenset({"QB"}), frozenset({"pass_yds"}),
            0.95, "", measured=False),
)


def main() -> None:
    from engine.sources import depthcharts as D
    from engine.sources import injuries as I
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2022-2024")
    a, _, b = ap.parse_args().seasons.partition("-")
    rules = tuple(KNOCK_ONS) + DROPPED
    pts: dict = {r.key: [] for r in rules}
    for season in range(int(a), int(b or a) + 1):
        with open(ROOT / "data" / "cache" / f"player_stats_{season}.csv", newline="") as fh:
            rows = list(csv.DictReader(fh))
        weeks = sorted({int(F._f(r, "week")) for r in rows})
        out = F.out_roles_by_week(I.load_injuries(season), D.load_depth_charts(season, keep_days=None), weeks)
        for k, v in F.samples(rows, out, rules).items():
            pts[k].extend(v)
        print(f"  {season}: read")
    for rule in rules:
        m = F.measure(pts[rule.key])
        got = "—" if m["mult"] is None else f"×{m['mult']:.3f} ± {m['se'] or 0:.3f}"
        state = "in use" if rule in KNOCK_ONS else "dropped"
        print(f"  {rule.key:<14} {state:<8} ×{rule.mult:.2f}{'' if rule.measured else ' (hand-set)'}   "
              f"measured {got}   flagged {m['n']}, others {m['others']}")


if __name__ == "__main__":
    main()
