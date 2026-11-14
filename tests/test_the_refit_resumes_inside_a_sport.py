"""The weekly refit resumes inside a sport (engine/deepfit._refit_sport,
run_round).

The live heartbeat, 2026-11-05 10:20: "deep refit: round of 2026-11-04:
nothing done this run; left for the next: nfl, cfb, ...", after 68
minutes, with the NFL's fits still dated late August. A sport's three
fitters (recency dial, player memory, temperatures) were one piece: a run
cut off in the second threw the first one's work away, and the next
attempt began at the first again, so a sport whose three fitters outgrow
one run could never finish. What these hold:

  * each fitter is written down the moment it ends, and the next run of
    the same round starts at the first one not done;
  * the fitter a run's time ran out in is named, with how long it ran, in
    the run's last line (the line the heartbeat keeps) and in the state;
  * a finished sport clears its part-way record and keeps each fitter's
    running time;
  * a new round starts every fitter again;
  * a fitter that failed earlier in the round still keeps the NBA's
    spread switch from being thrown.

Run directly: `python3 tests/test_the_refit_resumes_inside_a_sport.py`
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import deepfit as D                                  # noqa: E402

WED = dt.date(2026, 11, 4)
THU, FRI = WED + dt.timedelta(days=1), WED + dt.timedelta(days=2)
NEXT_WED = WED + dt.timedelta(days=7)


class _Fitters:
    """subprocess.run for the three fitters: ``cut`` scripts time out,
    ``fail`` scripts exit 1, the rest adopt something."""
    def __init__(self, cut=(), fail=()):
        self.cut, self.fail, self.ran = set(cut), set(fail), []

    def __call__(self, cmd, **kw):
        script = Path(cmd[1]).name
        self.ran.append(script)
        if script in self.cut:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        if script in self.fail:
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        return subprocess.CompletedProcess(cmd, 0, "  receptions: adopted 0.9\n", "")


def _round(tmp, today, fitters, left=("nfl",), round_of=WED, pieces=None, rows=None):
    path = tmp / "deepfit_state.json"
    if not path.exists():
        path.write_text(json.dumps({"round": round_of.isoformat(), "left": list(left),
                                    "pieces": pieces or {}}))
    keep_rows, keep_run = D._row_counts, subprocess.run
    D._row_counts = lambda db="data/history.db": dict(rows or {"nfl": 330_000, "nba": 250_000})
    subprocess.run = fitters
    try:
        lines = D.run_round(db="unused", state_path=path, today=today, budget_s=3600)
    finally:
        D._row_counts, subprocess.run = keep_rows, keep_run
    return lines, json.loads(path.read_text())


def test_a_run_cut_off_in_a_fitter_keeps_the_ones_it_finished_and_names_the_one_it_did_not():
    tmp = Path(tempfile.mkdtemp())
    f = _Fitters(cut={"playerfit.py"})
    lines, st = _round(tmp, THU, f)
    assert f.ran == ["formfit.py", "playerfit.py", "calibrate.py"], f.ran
    nfl = st["pieces"]["nfl"]
    assert nfl["fitters_done"] == {"round": "2026-11-04", "done": ["recency dial", "temperatures"]}, nfl
    assert nfl["cut_off"]["fitter"] == "player memory" and nfl["cut_off"]["on"] == THU.isoformat()
    assert set(nfl["fitter_seconds"]) == {"recency dial", "player memory", "temperatures"}
    assert st["left"] == ["nfl"] and "done" not in nfl
    last = lines[-1]
    assert last.startswith("deep refit: round of 2026-11-04: nothing done this run; left for the next: nfl")
    assert "part-way: nfl (recency dial, temperatures done; player memory cut off after" in last, last


def test_the_next_run_starts_at_the_first_fitter_not_done_and_finishes_the_sport():
    tmp = Path(tempfile.mkdtemp())
    _round(tmp, THU, _Fitters(cut={"playerfit.py"}))
    f = _Fitters()
    lines, st = _round(tmp, FRI, f)
    assert f.ran == ["playerfit.py"], f.ran
    assert any("nfl recency dial — done earlier this round" in ln for ln in lines), lines
    nfl = st["pieces"]["nfl"]
    assert nfl["done"] == FRI.isoformat() and "fitters_done" not in nfl and "cut_off" not in nfl, nfl
    assert set(nfl["fitter_seconds"]) == {"recency dial", "player memory", "temperatures"}
    assert st["left"] == [] and lines[-1].startswith("deep refit: round of 2026-11-04 complete")


def test_a_fitter_that_outgrew_a_run_goes_last_so_the_others_get_theirs():
    """The dial is cut by its own 45 minutes, the memory five minutes later
    only because the run's time was nearly gone: the dial is the one that
    outgrew the run, and the next run takes the memory first."""
    import time as _t
    now = [10_000.0]
    cost = {"formfit.py": 2700.0, "playerfit.py": 300.0, "calibrate.py": 0.0}

    class _Timed(_Fitters):
        def __call__(self, cmd, **kw):
            now[0] += cost[Path(cmd[1]).name]
            return super().__call__(cmd, **kw)
    real = _t.monotonic
    _t.monotonic = lambda: now[0]
    try:
        tmp = Path(tempfile.mkdtemp())
        _, st = _round(tmp, THU, _Timed(cut={"formfit.py", "playerfit.py"}))
        nfl = st["pieces"]["nfl"]
        assert nfl["cut_off"]["fitter"] == "recency dial" and nfl["cut_off"]["after_s"] == 2700, nfl
        assert nfl["fitters_done"]["done"] == ["temperatures"], nfl
        g = _Timed()
        lines, st = _round(tmp, FRI, g)
    finally:
        _t.monotonic = real
    assert g.ran == ["playerfit.py", "formfit.py"], g.ran
    assert st["pieces"]["nfl"]["done"] == FRI.isoformat()


def test_the_cut_off_fitter_is_taken_last_the_next_time():
    tmp = Path(tempfile.mkdtemp())
    cut = {"nfl": {"cut_off": {"fitter": "recency dial", "after_s": 2700, "on": "2026-11-05",
                               "round": "2026-11-04"}}}
    f = _Fitters()
    _round(tmp, FRI, f, pieces=cut)
    assert f.ran == ["playerfit.py", "calibrate.py", "formfit.py"], f.ran
    tmp2 = Path(tempfile.mkdtemp())
    old = {"nfl": {"cut_off": {"fitter": "recency dial", "after_s": 2700, "on": "2026-10-29",
                               "round": "2026-10-28"}}}
    g = _Fitters()
    _round(tmp2, FRI, g, pieces=old)
    assert g.ran == ["formfit.py", "playerfit.py", "calibrate.py"], "another round's cut-off is not this round's"


def test_a_new_round_starts_every_fitter_again():
    tmp = Path(tempfile.mkdtemp())
    stale = {"nfl": {"fitters_done": {"round": "2026-10-28", "done": ["recency dial", "player memory"]}}}
    f = _Fitters()
    _round(tmp, NEXT_WED, f, round_of=NEXT_WED, pieces=stale)
    assert f.ran == ["formfit.py", "playerfit.py", "calibrate.py"], f.ran


def test_a_failed_fitter_earlier_in_the_round_still_holds_the_nba_switch():
    from engine.nba import switches
    thrown = []
    keep = (switches.target, switches.apply_target)
    switches.target = lambda name: True
    switches.apply_target = lambda name: thrown.append(name) or "spread switch thrown"
    try:
        tmp = Path(tempfile.mkdtemp())
        earlier = {"nba": {"fitters_done": {"round": "2026-11-04", "done": ["recency dial"],
                                            "failed": ["recency dial"]}}}
        f = _Fitters()
        lines, st = _round(tmp, THU, f, left=("nba",), pieces=earlier)
        fitters = [x for x in f.ran if x in ("formfit.py", "playerfit.py", "calibrate.py")]
        assert fitters == ["playerfit.py", "calibrate.py"], f.ran     # the NBA's checks join first
        assert thrown == [], "a failure earlier in the round keeps the switch where it is"
        tmp2 = Path(tempfile.mkdtemp())
        f2 = _Fitters()
        _round(tmp2, THU, f2, left=("nba",))
        assert thrown == ["spread"], "a clean refit throws it"
    finally:
        switches.target, switches.apply_target = keep


def test_the_part_way_note_reads_only_this_round_and_today():
    pieces = {"nfl": {"fitters_done": {"round": "2026-11-04", "done": ["recency dial"]},
                      "cut_off": {"fitter": "player memory", "after_s": 2700, "on": "2026-11-05"}},
              "cfb": {"fitters_done": {"round": "2026-10-28", "done": ["recency dial"]}},
              "nba": {"cut_off": {"fitter": "temperatures", "after_s": 600, "on": "2026-11-01"}}}
    got = D._part_way(pieces, ["nfl", "cfb", "nba"], "2026-11-04", "2026-11-05")
    assert got == ["nfl (recency dial done; player memory cut off after 45 min)"], got


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
