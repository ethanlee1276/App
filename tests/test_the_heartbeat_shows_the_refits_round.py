"""The heartbeat shows the deep refit's round, and where each owed sport's
recency dial stands (launch._deep_round_public, _weekly_jobs_public;
engine/ownerdesk.deep_round; engine/deepfit.dial_progress).

On 8 November the round's one public line, cut at 200 characters, said the
NFL's dial had been "cut off after 8 min" and nothing about how much of it
was left: whether a night moved it could only be asked on the box. What
these hold:

  * the heartbeat's refit entry carries the round as the owner desk's
    Weekly jobs card reads it — what it owes, what it has done, where a
    run's time ran out — and the desk reads the same function;
  * each owed sport with a dial says, market by market, fitted this round
    (the store's date), part-way (the settings its checkpoint kept) or
    owed; basketball, with no dial, says nothing;
  * no round on record, or no refit job recorded, leaves it out, and a
    broken file costs the heartbeat nothing.

Run directly: `python3 tests/test_the_heartbeat_shows_the_refits_round.py`
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import launch                                                       # noqa: E402
from engine import deepfit as D, formfit as ff                      # noqa: E402
from engine import maintenance as M, ownerdesk as OD                # noqa: E402

ROUND = "2026-11-04"
STATE = {"round": ROUND, "left": ["nfl", "cfb", "nba", "nfl_props"],
         "pieces": {"ladder": {"done": "2026-11-08"},
                    "nfl": {"fitters_done": {"round": ROUND, "done": ["player memory", "temperatures"]},
                            "cut_off": {"fitter": "recency dial", "after_s": 480, "on": "2026-11-08",
                                        "round": ROUND}}}}
STORE = {"nfl:pass_yds": {"sport": "nfl", "market": "pass_yds", "fitted": "2026-11-07T01:20:00"},
         "nfl:rec_yds": {"sport": "nfl", "market": "rec_yds", "fitted": "2026-08-25T03:00:00"},
         "cfb:pass_yds": {"sport": "cfb", "market": "pass_yds", "fitted": "2026-11-05T02:00:00"}}
NOW = time.mktime((2026, 11, 8, 12, 0, 0, 0, 0, -1))


class _Box:
    """The refit's round file, the dial's store and its checkpoint, and the
    chores' records, all in scratch."""

    def __init__(self, state=STATE, store=STORE, partial=None, job=True):
        self.state, self.store, self.partial, self.job = state, store, partial, job

    def __enter__(self):
        td = Path(tempfile.mkdtemp())
        self.keep = (D.STATE_PATH, ff.DEFAULT_PATH, ff.PARTIAL_PATH, M._child_dir)
        D.STATE_PATH = str(td / "deepfit_state.json")
        ff.DEFAULT_PATH = td / "formfit.json"
        ff.PARTIAL_PATH = td / "formfit_partial.json"
        for path, obj in ((D.STATE_PATH, self.state), (ff.DEFAULT_PATH, self.store),
                          (ff.PARTIAL_PATH, self.partial)):
            if obj is not None:
                Path(path).write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        M._child_dir = lambda: td / "cache"
        (td / "cache").mkdir()
        if self.job:
            M._record_job("engine.deepfit", started="2026-11-08T00:56:27", ended="2026-11-08T01:46:37",
                          minutes=50, exit=0, cut_off=False, running=False,
                          last="deep refit: round of 2026-11-04: ladder done this run; left for the next: "
                               "nfl, cfb, nba, nfl_props")
        return td

    def __exit__(self, *exc):
        D.STATE_PATH, ff.DEFAULT_PATH, ff.PARTIAL_PATH, M._child_dir = self.keep


def test_the_heartbeat_carries_the_round_and_each_dial_market():
    partial = {"nfl:rec_yds": {"scores": {f"{r:.1f}": [0.24, 26000] for r in ff.GRID[:12]}}}
    with _Box(partial=partial):
        got = launch._weekly_jobs_public(NOW)["deepfit"]
    rnd = got["round"]
    assert rnd["round"] == ROUND and rnd["left"] == ["nfl", "cfb", "nba", "nfl_props"], rnd
    assert rnd["done"] == ["ladder"], rnd
    assert rnd["part_way"] == ["nfl (player memory, temperatures done; recency dial cut off after 8 min)"], rnd
    assert rnd["dial"]["nfl"] == {"pass_yds": "fitted 2026-11-07", "rush_yds": "owed",
                                  "rec_yds": "12 of 21 scored", "receptions": "owed"}, rnd["dial"]
    assert rnd["dial"]["cfb"]["pass_yds"] == "fitted 2026-11-05"
    assert set(rnd["dial"]["cfb"]) == {"pass_yds", "rush_yds", "rec_yds", "receptions",
                                      "pass_att", "pass_cmp", "rush_att", "pass_int"}
    assert "nba" not in rnd["dial"] and "nfl_props" not in rnd["dial"], "no dial, nothing said"
    assert got["last"].startswith("deep refit: round of 2026-11-04"), "the job's own fields stand"


def test_the_desk_and_the_heartbeat_read_the_same_round():
    with _Box():
        desk = OD.weekly(now=NOW, jobs={}, deep_path=D.STATE_PATH, lab_path=Path(tempfile.mkdtemp()) / "no.json",
                         attempts_path=Path(tempfile.mkdtemp()) / "no.json")["deep"]
        beat = launch._deep_round_public(NOW)
    assert {k: v for k, v in beat.items() if k != "dial"} == desk, (beat, desk)


def test_a_dial_market_stands_where_its_store_and_checkpoint_say():
    with _Box():
        assert D.dial_progress("nfl", None) == {}, "no round, nothing to say"
        assert D.dial_progress("nba", ROUND) == {} and D.dial_progress("wnba", ROUND) == {}
        assert D.dial_progress("nhl", ROUND) == {}, "not a sport the dial fits"
        # A market fitted before the round began is owed again; part-way
        # wins over an old fit.
        assert D.dial_progress("nfl", "2026-11-08")["pass_yds"] == "owed"
    with _Box(store="{ not json", partial="{ torn"):
        assert set(D.dial_progress("nfl", ROUND).values()) == {"owed"}, "an unreadable store keeps nothing"


def test_no_round_or_no_job_leaves_it_out_and_a_broken_file_costs_nothing():
    with _Box(state=None):
        assert launch._deep_round_public(NOW) == {}
        assert "round" not in launch._weekly_jobs_public(NOW)["deepfit"]
    with _Box(job=False):
        assert "deepfit" not in launch._weekly_jobs_public(NOW), "nothing to hang it on"
    with _Box(state="{ not json"):
        assert "round" not in launch._weekly_jobs_public(NOW)["deepfit"]


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
