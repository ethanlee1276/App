"""The box's own checks judge only seasons that have ended (2026-11-14).

Ethan, 2026-11-14: "make sure ... all of the learning is working ... for
every single sport ... everything is learning and getting better". The
audit found the NBA's rotation rules (his first games back, a role that
jumped, a regular's return) switched OFF that morning by the box's own
weekly check (nbarules.py --save): its bar judged every season with 100+
games a rule touches, and three and a half weeks of the season in progress
had just crossed that floor. Rules measured on two full seasons, held out
both ways, were switched off on a few weeks of noise: thrashing, not
learning. The rates read past the last twenty (nbarates.py) used the same
bar the same way.

Now a season still being played is shown in the check's table and never
judged (engine/seasons.finished); a check whose measuring code changed is
owed again in a round whose NBA fitters are still to run
(engine/deepfit.NBA_CHECK_VERSION), so the fixed check runs tonight,
before the NBA's calibration is fitted on the board it leaves.

    python3 tests/test_the_box_checks_judge_finished_seasons.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import nbarates as NRT                              # noqa: E402
import nbarules as NR                               # noqa: E402
from engine import deepfit as D                     # noqa: E402
from engine.seasons import finished                 # noqa: E402


def test_a_season_is_finished_only_once_its_window_has_ended():
    assert finished("nba", 2025, "2026-11-14") and not finished("nba", 2026, "2026-11-14")
    assert not finished("nba", 2026, "2027-06-30") and finished("nba", 2026, "2027-07-01")
    assert not finished("cbb", 2026, "2027-04-15") and finished("cbb", 2026, "2027-04-16")
    assert finished("ufc", 2026, "2026-01-01"), "a sport without a window has nothing to wait for"


def _rules_season(gain):
    return {"n": 900, **{r: {"n": NR.MIN_TOUCHED + 50, "minutes": gain, "points": gain}
                        for r in (*NR.RULES, NR.FIVE)}}


def test_the_season_in_progress_never_switches_the_rules_off():
    res = {2024: _rules_season(0.02), 2025: _rules_season(0.03), 2026: _rules_season(-0.01)}
    in_play = lambda s: s != 2026                                          # noqa: E731
    assert NR.verdict(res, judge=in_play) == (True, []), "the finished seasons hold"
    assert NR.verdict(res, (NR.FIVE,), judge=in_play) == (True, [])
    assert NR.verdict(res)[0] is False, "a caller that judges every season still can"
    only_now = {2026: _rules_season(-0.01)}
    assert NR.verdict(only_now, judge=in_play) == (False, [NR.NOT_JUDGED]), \
        "only the season in progress has the games: nothing filed, the switch stays as it was"
    real = {2025: _rules_season(-0.01), 2026: _rules_season(0.02)}
    ok, why = NR.verdict(real, judge=in_play)
    assert not ok and all("in 2025:" in w for w in why), "a finished season that fails still decides"


def test_the_table_shows_the_season_in_progress_and_says_it_is_not_judged():
    res = {2025: _rules_season(0.02), 2026: _rules_season(-0.01)}
    lines = NR.report(res, 0.3, judge=lambda s: s != 2026)
    row = next(ln for ln in lines if ln.startswith("2026"))
    assert row.endswith("(in progress: shown, not judged)") and "HOLDS" in "\n".join(lines)
    assert not next(ln for ln in lines if ln.startswith("2025")).endswith("not judged)")
    src = (ROOT / "nbarules.py").read_text(encoding="utf-8")
    assert "ok, why = verdict(res, rules, judge=_finished)" in src, "the --save run judges finished seasons"
    assert NR._finished(2025) and not NR._finished(9999)


def test_the_rates_read_follows_the_same_rule():
    res = {2025: {s: {"n": NRT.MIN_ROWS, "gain": 0.02} for s in NRT.STATS},
           2026: {s: {"n": NRT.MIN_ROWS, "gain": -0.05} for s in NRT.STATS}}
    assert NRT.verdict(res, judge=lambda s: s != 2026) == (True, [])
    assert NRT.verdict({2026: res[2026]}, judge=lambda s: s != 2026)[1] == ["no season has enough games to judge"]
    src = (ROOT / "nbarates.py").read_text(encoding="utf-8")
    assert "ok, why = verdict(res, judge=_finished)" in src and "report(res, judge=_finished)" in src


def test_a_changed_check_runs_again_before_the_nbas_fitters():
    assert D.NBA_CHECK_VERSION == {"nba_rules": 2, "nba_rates": 2}
    # The box this morning: the rules and the rates done this round on the
    # old code (no version written), the NBA's fitters still owed.
    st = {"round": "2026-11-11", "left": ["nfl", "cfb", "nba_vacancy", "nba_spread", "nba", "nfl_props"],
          "pieces": {"nba_rules": {"done": "2026-11-14"}, "nba_rates": {"done": "2026-11-14"}}}
    assert D._late_checks(st, "2026-11-11")
    assert st["left"] == ["nfl", "cfb", "nba_vacancy", "nba_spread", "nba_rules", "nba_rates", "nba", "nfl_props"]
    assert set(D.PREREQS["nba"]) >= {"nba_rules", "nba_rates"}, "the fitters wait for them"
    # Once run on this code, never again this round.
    st = {"round": "2026-11-11", "left": ["nba"],
          "pieces": {c: {"done": "2026-11-14", "v": D.NBA_CHECK_VERSION.get(c, 1)} for c in D.NBA_CHECKS}}
    assert not D._late_checks(st, "2026-11-11")
    # With no NBA fitters left there is nothing to fit on the board: not owed.
    st = {"round": "2026-11-11", "left": ["nfl"], "pieces": {"nba_rules": {"done": "2026-11-14"}}}
    assert not D._late_checks(st, "2026-11-11")


def test_a_round_writes_the_version_each_check_ran():
    path = Path(tempfile.mkdtemp()) / "deepfit_state.json"
    path.write_text(json.dumps({"round": "2026-11-11", "left": ["nba"],
                                "pieces": {"nba_rules": {"done": "2026-11-14"}, "nba_rates": {"done": "2026-11-14"},
                                           "nba_vacancy": {"done": "2026-11-12", "v": 1},
                                           "nba_spread": {"done": "2026-11-12", "v": 1}}}))
    keep = D._row_counts
    D._row_counts = lambda db="data/history.db": {"nba": 1000}
    t = {"now": 0.0}
    ran = []

    def run_piece(p, db, deadline, say):
        ran.append(p)
        t["now"] += 60
        return [f"{p} ran"], True
    try:
        D.run_round(db="unused", state_path=path, today=dt.date(2026, 11, 14), clock=lambda: t["now"],
                    run_piece=run_piece)
    finally:
        D._row_counts = keep
    assert ran == ["nba_rules", "nba_rates", "nba"], ran
    pieces = json.loads(path.read_text())["pieces"]
    assert pieces["nba_rules"]["v"] == 2 and pieces["nba_rates"]["v"] == 2


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=3)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
