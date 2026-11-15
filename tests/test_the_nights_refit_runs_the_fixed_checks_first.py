"""The night's refit runs a fixed check first and spends the time it has left (2026-11-15).

Step PM, 14 November, told Ethan that the night after the NBA's rotation and
rates checks were fixed to judge only finished seasons (engine/deepfit
NBA_CHECK_VERSION 2), the refit would run them first and the rotation rules
would come back on. The heartbeat on 15 November said otherwise:

    deep refit: round of 2026-11-11: nba_vacancy done this run; left for the
    next: nfl, cfb, nba_spread, nba_rules, nba_rates, nba, nfl_props, ladder

The run took 7 of its 50 minutes, and `nba_switches.rotation.verdict` still
read `not yet`. There were two causes, both in engine/deepfit:

  * stalest first read the checks' 14 November done date, which was the OLD
    code's run, as the freshest in the round, so they sorted last behind
    pieces of 45 minutes each. A check not yet tried on its current code
    (`attempted_v`) now goes to the front. Once tried on that code, its dates
    place it like any piece.
  * a run stopped at the first piece that needed more than the time left.
    Now the first piece in line that fits runs. The one that did not fit is
    never started, so it keeps its place for the next run.

    python3 tests/test_the_nights_refit_runs_the_fixed_checks_first.py
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import deepfit as D                                  # noqa: E402

ROWS = {"nfl": 330_000, "cfb": 400_000, "nba": 250_000}
MIN = 60


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _box_on_the_15th():
    """The round as the heartbeat showed it after the 15 November run."""
    return {"round": "2026-11-11",
            "left": ["nfl", "cfb", "nba_spread", "nba_rules", "nba_rates", "nba", "nfl_props", "ladder"],
            "pieces": {"nfl": {"done": "2026-11-11", "seconds": 44 * MIN, "rows": 1},
                       "cfb": {"done": "2026-11-13", "seconds": 40 * MIN, "rows": 1},
                       "nba_spread": {"done": "2026-11-05", "seconds": 45 * MIN},
                       # The old code's run: no version written beside it.
                       "nba_rules": {"done": "2026-11-14", "seconds": 1823},
                       "nba_rates": {"done": "2026-11-14", "seconds": 660},
                       "nba_vacancy": {"done": "2026-11-15", "seconds": 7 * MIN},
                       "nba": {"done": "2026-11-10", "seconds": 20 * MIN, "rows": 1},
                       "nfl_props": {"done": "2026-11-11", "seconds": 15 * MIN},
                       "ladder": {"done": "2026-11-12", "seconds": 10 * MIN}}}


def _run(state, today, cost, unfinished=()):
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "deepfit_state.json"
    path.write_text(json.dumps(state))
    clock, ran = _Clock(), []

    def run_piece(p, db, deadline, say):
        ran.append(p)
        clock.t += cost.get(p, MIN)
        return [f"{p} ran"], p not in unfinished
    keep_rows, keep_rest = D._row_counts, D.resting_pieces
    D._row_counts = lambda db="data/history.db": dict(ROWS)
    D.resting_pieces = lambda pieces, today: []
    try:
        lines = D.run_round(db="unused", state_path=path, today=today, clock=clock, run_piece=run_piece)
    finally:
        D._row_counts, D.resting_pieces = keep_rows, keep_rest
    return ran, json.loads(path.read_text()), lines


def test_the_fixed_checks_run_first_the_night_after():
    cost = {"nba_rules": 1823, "nba_rates": 660}
    ran, st, lines = _run(_box_on_the_15th(), dt.date(2026, 11, 16), cost)
    assert ran[:2] == ["nba_rules", "nba_rates"], ran
    for c in ("nba_rules", "nba_rates"):
        assert st["pieces"][c]["v"] == 2 and st["pieces"][c]["attempted_v"] == 2, st["pieces"][c]
        assert c not in st["left"]
    # The NBA's fitters still wait for the spread's check, as before.
    assert "nba" in st["left"] and "nba_spread" in st["left"]
    assert lines[-1].startswith("deep refit: round of 2026-11-11: nba_rules, nba_rates"), lines[-1]


def test_a_check_tried_on_its_new_code_takes_its_place_by_its_dates():
    st = _box_on_the_15th()
    # Tried last night on the new code and did not finish: no new done date.
    st["pieces"]["nba_rules"].update(attempted="2026-11-16", attempted_v=2)
    order = D._stalest_first(st["left"], st)
    assert order[0] == "nba_rates", ("the one not yet tried on its code goes first", order)
    assert order[-1] == "nba_rules", ("then by its dates: tried last night, so last in line, "
                                      "not first every night", order)
    assert not D._first_on_new_code("nba_rules", st["pieces"])
    assert not D._first_on_new_code("nba_spread", st["pieces"]), "a check with no version is never stale"
    ran, after, _ = _run(st, dt.date(2026, 11, 17), {"nba_rates": 660, "nba_rules": 1823})
    assert ran[0] == "nba_rates" and ran[-1] == "nba_rules", ran
    # Run on its current code, a check is not owed again at all.
    assert not D._first_on_new_code("nba_rates", after["pieces"])
    assert not D._first_on_new_code("nba_rules", after["pieces"])


def test_the_time_left_goes_to_a_piece_that_fits_it():
    st = {"round": "2026-11-11", "left": ["nfl", "cfb", "ladder"],
          "pieces": {"nfl": {"done": "2026-11-05", "seconds": 30 * MIN, "rows": 1},
                     "cfb": {"done": "2026-11-06", "seconds": 40 * MIN, "rows": 1},
                     "ladder": {"done": "2026-11-07", "seconds": 8 * MIN}}}
    cost = {"nfl": 30 * MIN, "cfb": 40 * MIN, "ladder": 8 * MIN}
    ran, after, lines = _run(st, dt.date(2026, 11, 16), cost)
    # 20 minutes left after the NFL: college needs 45, the ladder 9.6.
    assert ran == ["nfl", "ladder"], ran
    assert after["left"] == ["cfb"] and after["pieces"]["cfb"].get("attempted") is None, \
        "never started, so it keeps its place"
    # The next run starts with it, whatever it needs.
    ran, after, _ = _run(after, dt.date(2026, 11, 17), cost)
    assert ran == ["cfb"] and after["left"] == [], ran


def test_the_first_piece_still_starts_whatever_it_needs_and_nothing_starts_short():
    st = {"round": "2026-11-11", "left": ["nfl", "cfb"],
          "pieces": {"nfl": {"done": "2026-11-05", "seconds": 99 * MIN, "rows": 1},
                     "cfb": {"done": "2026-11-06", "seconds": 4 * MIN, "rows": 1}}}
    ran, after, _ = _run(st, dt.date(2026, 11, 16), {"nfl": 47 * MIN, "cfb": 4 * MIN})
    # Three minutes left: under the five any piece is given (MIN_PIECE_LEFT_S).
    assert ran == ["nfl"] and after["left"] == ["cfb"], ran


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
