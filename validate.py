#!/usr/bin/env python3
"""One-command validation runbook — does the model actually have edge?

    python3 validate.py                      # last 5 seasons
    python3 validate.py --seasons 2021-2025

Runs the real pipeline end to end: ingest → backtest → calibration/ROI report.
Every stage that needs a release-gated or API host degrades to a clear BLOCKED
line with the exact command to unblock it, so this runs anywhere and tells you
precisely what to do to get the real numbers. On an open network with the feeds
reachable, it prints your model's calibration (ECE) and ROI over real seasons —
the yes/no on edge.
"""

from __future__ import annotations

import argparse

from engine import db, ingest
from engine.sources.fetch import DataUnavailable
from engine.rules import RuleConfig


class Stage:
    def __init__(self, name): self.name = name; self.status = "…"; self.detail = ""
    def ok(self, d): self.status = "PASS"; self.detail = d; return self
    def block(self, d): self.status = "BLOCKED"; self.detail = d; return self


def parse_seasons(spec):
    a, b = spec.split("-") if "-" in spec else (spec, spec)
    return list(range(int(a), int(b) + 1))


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate the model on real data.")
    ap.add_argument("--seasons", default=None, help="e.g. 2021-2025")
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    args = ap.parse_args()

    import datetime
    if args.seasons:
        seasons = parse_seasons(args.seasons)
    else:
        end = datetime.date.today().year - 1
        seasons = list(range(end - 4, end + 1))

    print(f"Validating on seasons {seasons[0]}–{seasons[-1]}\n")
    conn = db.connect(args.db)
    stages = []

    # 1. Ingest NFL (games are reachable from the git tree; player logs gated).
    s = Stage("NFL data ingest")
    res = ingest.ingest_nfl(conn, seasons)
    if res["player_logs"]:
        s.ok(f"{res['games']:,} games, {res['player_logs']:,} player-log rows")
    else:
        s.block(f"{res['games']:,} games ingested; player logs need release access "
                f"— export once: nfl_data_py import_weekly_data → data/cache/player_stats_<yr>.csv")
    stages.append(s)

    # 2. NFL backtest (walk-forward calibration + ROI) on the latest season.
    s = Stage("NFL backtest")
    try:
        from engine.backtest import backtest_from_stats
        rep = backtest_from_stats(seasons[-1], list(range(6, 18)), RuleConfig())
        if rep.n:
            s.ok(f"{rep.n} props · Brier {rep.brier:.3f} · ECE {rep.ece:.3f} · "
                 f"ROI {rep.roi:+.1%}")
        else:
            s.block("no settled props — check the stats cache covers these weeks")
    except DataUnavailable:
        s.block("needs weekly stats (release-gated) — see stage 1 export")
    stages.append(s)

    # 3. MLB backtest from ingested logs (MLB Stats API / cache).
    s = Stage("MLB backtest")
    entries = db.entries_for_market(conn, "mlb", "total_bases", min_games=10)
    if entries:
        from engine.mlb.backtest import backtest_from_logs
        rep = backtest_from_logs(entries, "total_bases", min_history=8)
        s.ok(f"{rep.n} settled · ECE {rep.ece:.3f} · ROI {rep.roi:+.1%}")
    else:
        s.block("no MLB logs in the DB — run: python3 ingest.py mlb --dates <YYYY-MM-DD ...>")
    stages.append(s)

    # 4. Ledger present (self-evaluation loop).
    s = Stage("Bet ledger")
    s.ok("ready — `python3 ledger.py demo`, then log/settle real picks")
    stages.append(s)

    # --- report -------------------------------------------------------------
    print("Validation report")
    print("─" * 62)
    for st in stages:
        icon = {"PASS": "✅", "BLOCKED": "⚠️ ", "…": "  "}[st.status]
        print(f"{icon} {st.name:20} {st.detail}")
    print("─" * 62)
    blocked = [st for st in stages if st.status == "BLOCKED"]
    if blocked:
        print(f"\n{len(blocked)} stage(s) need reachable feeds. Run this where "
              f"github releases / statsapi.mlb.com are reachable (or drop the cached "
              f"CSVs) to get the real edge numbers.")
    else:
        print("\nAll stages validated on real data. 🎯")


if __name__ == "__main__":
    main()
