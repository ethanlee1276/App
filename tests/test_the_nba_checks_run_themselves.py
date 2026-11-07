"""The NBA's waiting checks run themselves, and their verdicts throw the switches.

Ethan, 2026-11-04: "I don't want to have to specifically ask you for certain
tools or us grabbing certain pieces of data or using certain sources or
inventing certain things. I want you to just do it." Three NBA changes the lab
measured waited on a command typed on the box (runbook JY, JZ). Checks, one
rule each: a setting on the box still decides first, then the box's own
verdict, then the old default; a new round owes the three checks right before
the NBA's fitters, and a round already under way takes them late; a check runs
as a child bounded by what is left of the run, and a check that has not
answered stays owed; the NBA's refit fits on the spread its verdict asks for
and throws the switch only after a clean refit, never against a setting on
the box; each check files its verdict.

Run directly: `python3 tests/test_the_nba_checks_run_themselves.py`
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
for _k in ("QB_NBA_SPREAD", "QB_NBA_ROTATION"):
    os.environ.pop(_k, None)

from engine import deepfit as D                                        # noqa: E402
from engine.nba import switches as W                                    # noqa: E402
# The round's mechanics, pinned on any date: whether a league at rest sits the
# round out is tests/test_a_league_at_rest_sits_out_the_heavy_nights.py.
D.resting_pieces = lambda pieces, today: []

CHECKS = list(D.NBA_CHECKS)
ROWS = {"cfb": 400_000, "mlb": 900_000, "nba": 250_000, "nfl": 330_000, "wnba": 60_000}


def _fresh():
    os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
    for k in ("QB_NBA_SPREAD", "QB_NBA_ROTATION"):
        os.environ.pop(k, None)


def test_the_box_setting_decides_first_then_its_own_verdict_then_the_old_default():
    _fresh()
    from engine.nba.minutes import rotation_on
    from engine.nba.prob import spread_on
    assert not W.is_on("spread") and W.is_on("rotation"), "no verdict: the board as it was"
    W.record_check("spread", True, "lower Brier in 7 of 7")
    assert not spread_on(), "a ready verdict waits for the NBA refit"
    assert W.target("spread") is True
    assert "switched ON" in W.apply_target("spread") and spread_on() and W.apply_target("spread") == ""
    os.environ["QB_NBA_SPREAD"] = "0"
    try:
        assert not spread_on() and W.target("spread") is None, "the box's setting wins, and nothing fits against it"
    finally:
        os.environ.pop("QB_NBA_SPREAD")
    W.record_check("rotation", False, "role jump in 2025: minutes -0.4%", follow=True)
    assert not rotation_on(), "the rules follow the box's own seasons at once"
    os.environ["QB_NBA_ROTATION"] = "1"
    try:
        assert rotation_on()
    finally:
        os.environ.pop("QB_NBA_ROTATION")
    W.record_check("rotation", True, "holds", follow=True)
    assert rotation_on() and W.entry("rotation")["verdict"] == "ready"


def test_a_new_round_owes_the_nba_checks_right_before_its_fitters():
    owed = D.round_pieces({}, ROWS)
    i = owed.index("nba")
    assert owed[i - len(CHECKS):i] == CHECKS, owed
    assert D.PREREQS["nba"] == tuple(CHECKS), "the fitters fit on what the checks decided"
    quiet = D.round_pieces({"pieces": {"nba": {"done": "2026-10-28", "rows": ROWS["nba"]}}}, ROWS)
    assert "nba" not in quiet and not set(CHECKS) & set(quiet), "no new NBA games, nothing to check"


def _clock():
    t = {"now": 0.0}

    def clock():
        return t["now"]
    return clock, t


def test_a_round_under_way_takes_the_checks_late():
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "deepfit_state.json"
    path.write_text(json.dumps({"round": "2026-11-04", "left": ["nfl", "cfb", "nba", "mlb"],
                                "pieces": {"yardage_mixture": {"attempted": "2026-11-04"}}}))
    keep = D._row_counts
    D._row_counts = lambda db="data/history.db": dict(ROWS)
    clock, t = _clock()
    ran = []

    def run_piece(p, db, deadline, say):
        ran.append(p)
        t["now"] += 60
        return [f"{p} ran"], True
    try:
        lines = D.run_round(db="unused", state_path=path, today=dt.date(2026, 11, 5), clock=clock,
                            run_piece=run_piece)
    finally:
        D._row_counts = keep
    assert ran == ["nfl", "cfb", *CHECKS, "nba", "mlb"], ran
    assert any("join this round before its fitters" in ln for ln in lines), lines
    st = {"round": "2026-11-04", "left": ["mlb"], "pieces": {}}
    assert not D._late_checks(st, "2026-11-04") and st["left"] == ["mlb"], "no NBA fitters owed, no checks"
    st = {"round": "2026-11-04", "left": ["nba"], "pieces": {c: {"done": "2026-11-04"} for c in CHECKS}}
    assert not D._late_checks(st, "2026-11-04"), "a check done this round is not owed twice"


class _Done:
    def __init__(self, code=0, out=""):
        self.returncode, self.stdout, self.stderr = code, out, ""


def _patched(fake):
    keep = subprocess.run
    subprocess.run = fake
    return keep


def test_a_check_runs_as_a_child_bounded_by_what_is_left_of_the_run():
    import time
    seen = []

    def fake(cmd, **kw):
        seen.append((cmd, kw.get("timeout")))
        return _Done(0, "a table\nspread: ready for the refit — lower in 7 of 7\nspread verdict filed: /x\n")
    keep = _patched(fake)
    try:
        lines, finished = D._run_check("nba_spread", deadline=time.monotonic() + 600)
    finally:
        subprocess.run = keep
    assert finished and seen[0][0][1:] == ["nbalabcheck.py", "--part", "spread", "--save-verdict"]
    assert seen[0][1] <= 600, "bounded by the run"
    assert lines == ["nba_spread: spread: ready for the refit — lower in 7 of 7",
                     "nba_spread: spread verdict filed: /x"], lines

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    keep = _patched(slow)
    try:
        lines, finished = D._run_check("nba_vacancy", deadline=time.monotonic() + 60)
    finally:
        subprocess.run = keep
    assert not finished and "left for the next run" in lines[0], "unanswered, still owed"
    assert D._run_check("nba_rules", deadline=time.monotonic() - 5)[1] is False
    assert D.NBA_CHECKS["nba_vacancy"] == ("nbavacancy.py", ("nba", "--heldout", "--save"))
    assert D.NBA_CHECKS["nba_rules"] == ("nbarules.py", ("--save",))


def test_the_nba_refit_fits_on_the_verdict_and_then_throws_the_switch():
    import time
    _fresh()
    W.record_check("spread", True, "lower Brier in 7 of 7")
    envs = []

    def fake(cmd, **kw):
        envs.append((cmd[1], (kw.get("env") or {}).get("QB_NBA_SPREAD")))
        return _Done(0, "")
    keep = _patched(fake)
    try:
        lines, finished = D._refit_sport("nba", deadline=time.monotonic() + 3000)
    finally:
        subprocess.run = keep
    assert finished and [e for _s, e in envs] == ["1", "1", "1"], envs
    assert W.is_on("spread") and any("switched ON" in ln for ln in lines), lines

    _fresh()
    W.record_check("spread", True, "lower Brier in 7 of 7")

    def broken(cmd, **kw):
        return _Done(1 if cmd[1] == "calibrate.py" else 0, "")
    keep = _patched(broken)
    try:
        D._refit_sport("nba", deadline=time.monotonic() + 3000)
    finally:
        subprocess.run = keep
    assert not W.is_on("spread"), "a refit that did not run clean throws nothing"

    os.environ["QB_NBA_SPREAD"] = "0"
    envs.clear()
    keep = _patched(fake)
    try:
        D._refit_sport("nba", deadline=time.monotonic() + 3000)
    finally:
        subprocess.run = keep
        os.environ.pop("QB_NBA_SPREAD")
    assert all(e is None for _s, e in envs) and not W.entry("spread").get("on"), \
        "the box's setting: the fitters read it, nothing is thrown"
    envs.clear()
    keep = _patched(fake)
    try:
        D._refit_sport("nfl", deadline=time.monotonic() + 3000)
    finally:
        subprocess.run = keep
    assert all(e is None for _s, e in envs), "another league's refit is untouched"


def test_each_check_files_its_verdict():
    lab = (ROOT / "nbalabcheck.py").read_text(encoding="utf-8")
    assert "--save-verdict" in lab and "switches.record_check('spread', ready, why)" in lab, \
        "the spread's verdict is filed, its switch waits for the refit"
    rules = (ROOT / "nbarules.py").read_text(encoding="utf-8")
    assert '"--save" in argv' in rules and "switches.record_check(name, ok," in rules and "follow=True" in rules
    assert 'for name, rules in (("rotation", RULES), ("starters", (FIVE,))):' in rules, \
        "the rotation's verdict and the starting five's, each filed apart"
    vac = (ROOT / "nbavacancy.py").read_text(encoding="utf-8")
    assert '"--save" in flags' in vac and "vacancy.save(sport, res)" in vac


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
