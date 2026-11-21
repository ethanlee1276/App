"""Next Gen Stats: pulled from nflverse, read per player-week, measured first.

Ethan, 2026-09-28: "do all the free shit first." engine/sources/ngs.py reads
the three NGS files; ngsfit.py is the information test a tracking number
has to pass before it reaches a projection. Offline: the parser and the
prior on fixture rows, and the harness's shape.

Run directly: `python3 tests/test_next_gen_stats_are_read_and_measured.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import ngs as N                            # noqa: E402


def _r(season, week, name, **vals):
    row = {"season": str(season), "season_type": "REG", "week": str(week), "player_display_name": name,
           "player_position": "WR", "team_abbr": "PHI"}
    row.update({k: str(v) for k, v in vals.items()})
    return row


def test_rows_are_read_per_player_week_oldest_first_and_thin_weeks_are_absent():
    rows = [_r(2025, 2, "DeVonta Smith", avg_separation=3.1, avg_cushion=6.0),
            _r(2025, 1, "DeVonta Smith", avg_separation=2.4),
            _r(2024, 17, "DeVonta Smith", avg_separation=2.9),
            _r(2025, 1, "Nobody", avg_separation="")]                 # no metric present: no week
    by = N.by_player(rows, "receiving")
    assert [(s, w) for s, w, _v in by["DeVonta Smith"]] == [(2024, 17), (2025, 1), (2025, 2)]
    assert by["DeVonta Smith"][-1][2] == {"avg_separation": 3.1, "avg_cushion": 6.0}
    assert "Nobody" not in by


def test_the_prior_is_the_last_charted_weeks_before_the_game_across_seasons():
    hist = [(2024, 16, {"avg_separation": 2.0}), (2024, 17, {"avg_separation": 3.0}),
            (2025, 1, {"avg_separation": 4.0}), (2025, 2, {"avg_separation": 9.0})]
    assert N.prior(hist, 2025, 2, "avg_separation") == 3.0, "weeks before 2025-2 only: 2, 3, 4"
    assert N.prior(hist, 2025, 2, "avg_separation", n=2) is None, "fewer than three charted weeks"
    assert N.prior(hist, 2025, 3, "avg_separation", n=3) == (3.0 + 4.0 + 9.0) / 3
    assert N.prior(hist, 2025, 3, "avg_cushion") is None


def test_the_files_and_metrics_are_the_three_nflverse_publishes():
    assert N.KINDS == ("receiving", "rushing", "passing")
    assert N.BASE.endswith("/nextgen_stats")
    assert "avg_separation" in N.METRICS["receiving"] and "rush_yards_over_expected_per_att" in N.METRICS["rushing"]
    assert "completion_percentage_above_expectation" in N.METRICS["passing"]
    src = (ROOT / "engine" / "sources" / "ngs.py").read_text(encoding="utf-8")
    assert 'fetch_csv(f"{BASE}/ngs_{kind}.csv.gz", f"ngs_{kind}.csv"' in src, "the gz asset, cached ungzipped"


def test_the_harness_ships_nothing_on_its_own():
    """ngsfit prints; a metric reaches a projection only by a later, separate
    change that cites its held-out figure — the rule every input here obeys."""
    fit = (ROOT / "ngsfit.py").read_text(encoding="utf-8")
    assert "ships = best_k > 0 and delta >= 2 * se and up >= min(3, len(per))" in fit
    assert "import marketfit as M" in fit
    for f in ("engine/likely.py", "engine/pipeline.py", "engine/yardagefit.py", "engine/nfl/pipeline.py"):
        p = ROOT / f
        if p.exists():
            assert "sources.ngs" not in p.read_text(encoding="utf-8") and "import ngs" not in p.read_text(encoding="utf-8"), f


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
