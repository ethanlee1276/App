"""The faces backfill existed for three weeks and never once ran itself.

Ethan, 2026-09-04: "can we make sure all headshot are up to date for all
sports. I see some players on nfl don't have any."

`facesfill.py` was written on 2026-08-18 and had NO caller. Not in
launch.py, not in a deploy script, not in a timer — only a human typing
it. Measured in this checkout, `player_assets` held 5,766 college rows
and NOT ONE for nfl, mlb, nba or wnba, which is exactly what that
module's own header predicts: "the fantasy player profile reads
`player_assets` for its face and NOTHING has ever written NFL rows to
that table."

AND NOTHING ELSE CAN DO THE JOB. Its docstring says why: the photo URL
is captured DURING ingest, and ingest skips days it has already stored —
that is what makes a six-season backfill affordable. So a player whose
days were all stored before faces existed can never pick one up. Ethan
re-ran every ingest on 2026-08-18 and the WNBA count sat at 171/183
before and after, because not one already-stored day was re-read. It is
a one-way ratchet and this is the only thing that releases it.

IN `run_if_due`, NOT IN THE NIGHTLY. That function is the once-a-day
hook BOTH paths call — `nightly_run`'s first step, and the server's own
startup and background refresher. Wiring it to the nightly alone would
leave it unrun on exactly the box where the nightly is the thing that
broke, which is the failure this module's docstring was written about.

Run directly: `python3 tests/test_faces_scheduled.py`
"""

import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import maintenance                               # noqa: E402

SRC = inspect.getsource(maintenance.run_if_due)


def _block():
    """Just the faces backfill, so a check cannot pass on a word that
    happens to appear somewhere else in a 600-line function.

    `test_every_sport_it_covers_is_asked_for` was written against the
    whole of `run_if_due` and passed with the entire caller DELETED,
    because "nfl" and "mlb" appear all over the daily chores. A test that
    survives the removal of the thing it tests is furniture."""
    assert "import facesfill" in SRC, \
        "facesfill has no scheduled caller — the whole block is gone"
    i = SRC.index("import facesfill")
    return SRC[i:SRC.index("if harvest:", i)]


# --- it is called at all ------------------------------------------------------
def test_the_daily_chores_run_the_backfill():
    assert "import facesfill" in SRC, \
        "facesfill is back to having no scheduled caller"
    assert "facesfill.fill(" in SRC


def test_every_sport_it_covers_is_asked_for():
    """NFL is the one Ethan named and the one with no rows at all, but
    the same ratchet applies to all four — the WNBA gap is what found
    this in the first place."""
    block = _block()
    for sport in ("nfl", "mlb", "nba", "wnba"):
        assert f'"{sport}"' in block, f"{sport} is not filled on the schedule"


def test_it_runs_where_both_paths_reach_it():
    """`run_if_due` is called by the nightly AND by the server. Putting
    the fill in `nightly_run` alone would skip it on a box whose nightly
    is broken, and a broken nightly is the documented failure mode."""
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "_run_maintenance()" in launch
    assert launch.count("facesfill") == 0, \
        "a second caller in launch.py — one scheduled home, not two"


# --- and it cannot take the chores down ---------------------------------------
def test_one_sport_failing_does_not_stop_the_others():
    """Per-sport try/except, because the four read four different feeds
    and a dead nflverse must not cost the MLB faces."""
    block = _block()
    inner = block[block.index("for _sport in"):]
    assert "except Exception as exc:" in inner, \
        "a single feed failure aborts every sport's fill"
    assert "continue" in inner


def test_the_whole_block_is_best_effort():
    """Faces are polish. A backfill that raises must never cost the
    results ingest, the settle, or the day's mark."""
    block = _block()
    i = SRC.index("import facesfill")
    assert SRC[:i].rstrip().endswith("try:"), \
        "the backfill is not inside a try"
    assert "faces backfill skipped" in block


def test_it_runs_before_the_day_is_marked_done():
    """`last_done` gates the whole function for the rest of the day. A
    fill placed after it would run once and then be skipped until
    tomorrow — which is the shape of the bug it is fixing."""
    _block()          # raises with a real message if the caller is gone
    assert SRC.index("import facesfill") < SRC.index('state["last_done"]'), \
        ("the fill runs after the day is marked done, so it runs once and "
         "then is skipped until tomorrow")


def test_the_log_says_what_changed_rather_than_that_it_ran():
    """"faces: ok" is not a fact. A count that moved is."""
    block = _block()
    assert "_after > _before" in block, "it logs without checking anything"
    assert "nothing new to fill" in block, \
        "a quiet day is indistinguishable from a broken one"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:              # noqa: BLE001
                # A source anchor that VANISHES raises ValueError from
                # str.index, not AssertionError. Reported as a failure
                # rather than killing the run, or one missing anchor hides
                # every test after it — which is exactly what happened
                # while mutation-testing this file.
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
