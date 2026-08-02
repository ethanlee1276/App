"""--why-empty was explaining the wrong board with the wrong bar.

Ethan ran it on a 15-game card and it reported:

    Binding gate: "engine graded it (grade ≠ Pass)" — 9 prop(s) clear
    everything else and die there.

    In the recommendable window (15 total):
      Ty France OVER 0.5 home_runs  575  net +3.42pt  need 0.30pt
                                    conf 6.9  edge 4.12%  Pass

That row clears every gate the report lists and is still Pass, which reads
as a grader bug. It is not one. Two faults in the REPORT combined to
manufacture it.

First, home runs are quarantined on the Long Shots board by design —
engine/mlb/pipeline.py skips Tier 3 for the main board and counts it under
census["longshot_board"]. Walking them through the main board's funnel put
15 props that can never be main-board picks "in the recommendable window",
and then required a gate to explain why they were not picked.

Second, the report's graded bar was hardcoded at 0.003 while _grade's
lowest threshold ("Play") needs 0.010. The funnel therefore passed props at
a bar a third of the engine's, and blamed "engine graded it" for killing
what its own bar should have stopped.

A diagnostic that disagrees with the code it explains is worse than no
diagnostic: it sends you hunting for a bug that is not there. Both of us
spent a round on this one.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()


def _block():
    i = SRC.index("def why_empty(")
    return SRC[i:SRC.index("def _settleable_days(")]


# --- the bar has to be the engine's bar -------------------------------------
def test_the_reports_bar_is_read_from_the_grader_not_invented():
    b = _block()
    assert "_GRADE_FLOOR = min(net_min for _, _, net_min in BASE_THRESHOLDS)" in b
    assert "0.003 + favourite_surcharge" not in b, \
        "the report still uses its own looser floor"


def test_that_floor_is_the_number_the_engine_would_actually_use():
    from engine.betting import BASE_THRESHOLDS, _grade
    floor = min(net_min for _, _, net_min in BASE_THRESHOLDS)
    best_conf = max(conf for _, conf, _ in BASE_THRESHOLDS)
    # Just under the floor grades Pass; at the floor it does not.
    assert _grade(best_conf, floor - 0.0001, odds=100) == "Pass"
    assert _grade(best_conf, floor, odds=100) != "Pass"


def test_the_printed_bar_matches_the_bar_being_applied():
    """The heading said "net ≥ 0.3pt" while the check used a different
    number — so the line you read and the line that ran disagreed."""
    b = _block()
    assert 'f"clears the graded bar (net ≥ {_GRADE_FLOOR*100:.1f}pt "' in b
    assert "net ≥ 0.3pt" not in b


# --- the funnel has to describe the board it claims to --------------------
def test_long_shots_are_excluded_from_the_main_boards_funnel():
    b = _block()
    assert "def _is_longshot(r):" in b
    assert 'r.get("tier") == 3' in b
    assert '"home_runs"' in b


def test_the_exclusion_matches_the_pipelines_own_rule():
    """If these two ever disagree, the report is describing a board the
    build does not produce."""
    pipe = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
                encoding="utf-8").read()
    assert 'r.get("tier", 2) == 3 or r.get("market") == "home_runs"' in pipe, \
        "the pipeline's quarantine rule moved; --why-empty still uses the old one"


def test_the_long_shots_are_counted_out_loud_rather_than_vanishing():
    """Silently dropping 15 of 591 props would make the totals stop adding
    up, which is its own kind of wrong."""
    b = _block()
    assert "the Long Shots board" in b
    assert "len(real) + len(shots)" in b, \
        "the headline count no longer includes the props it set aside"


def test_a_card_that_is_all_long_shots_says_so_and_stops():
    b = _block()
    assert "if not real:" in b
    assert "nothing to explain" in b


# --- end to end -------------------------------------------------------------
def test_the_report_runs_and_keeps_home_runs_out_of_the_window():
    import subprocess
    p = subprocess.run([sys.executable, "launch.py", "--why-empty", "mlb"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-500:]
    out = p.stdout
    assert "Long Shots board owns those by design" in out
    window = out[out.index("In the recommendable window"):]
    window = window[:window.index("Biggest net edges")]
    assert "home_runs" not in window, \
        "a long shot is still being offered as a main-board candidate"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
