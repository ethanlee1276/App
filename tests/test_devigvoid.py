"""A bet on a man who never took the field is not a loss. It is void.

WHAT THIS WAS WRITTEN AFTER. `engine.devigfit` reported that in the
0.10-0.18 raw-price band — roughly +455 to +800, which is where the
touchdown longshot board lives — the market charged a 35.0% haircut
against 12.8% across the rest of the board, z = +2.9 on 888 player-weeks.
That cleared the error bar added the day before, so the spike is real in
the data. The question this file asks is whether it is real in the world.

A haircut is `1 - actual / raw`. Anything that lowers the realised rate
without lowering the price is arithmetically indistinguishable from the
book charging a bigger toll — and an anytime-touchdown prop on a player
who does not dress is VOID at every book, refunded, not lost. Graded here
as a loss it manufactures exactly that shape.

AND IT IS NOT SPREAD EVENLY. Over 30,750 NFL player-weeks, the share
with no snaps, no carries and no targets runs:

    career TD rate under 5%     9.6%
    5-12%                       5.0%
    12-22%                      1.8%
    22-35%                      0.9%
    over 35%                    0.1%

A hundred-fold gradient pointing straight at the longshot band. None of
those 1,265 rows scored, because a man who never took a snap cannot.

The logs CAN separate the cases: 1,030 NFL player-weeks record an
explicit zero snap count, 2,314 record positive snaps with no usage at
all — a real loss — and 240 carry no snap record either way. So the
correction is not applied silently. Both tables are printed and the gap
between them is labelled as the width of what the logs cannot settle.

Run directly: `python3 tests/test_devigvoid.py`
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import devigfit as D                        # noqa: E402


def _board(seed=1, n=3000, void_longshots=0.10, void_rest=0.0,
           hold=0.86):
    """A board charging a FLAT hold at every price, with non-participants
    concentrated among the longshots exactly as the logs say they are."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        p = rng.choice([0.05, 0.14, 0.22, 0.35, 0.55])
        rate = void_longshots if p < 0.18 else void_rest
        played = rng.random() >= rate
        rows.append({"season": 2024, "week": "1", "market": p,
                     "played": played,
                     "scored": 0 if not played else
                               int(rng.random() < p * hold)})
    return rows


def _cut(lines, band="0.10-0.18"):
    """The haircut column of one band, as a float."""
    for ln in lines:
        if ln.strip().startswith(band):
            return float(ln.split()[4].rstrip("%")) / 100.0
    raise AssertionError(f"{band} not in\n" + "\n".join(lines))


# --- the artifact, reproduced ---------------------------------------------
def test_void_rows_manufacture_a_haircut_that_nobody_charged():
    """THE WHOLE POINT, on a board charging the SAME hold everywhere. Ten
    per cent of the longshot rows never played; nothing about the price
    changed; and the longshot band's measured toll jumps anyway."""
    rows = _board()
    with_void = _cut(D.haircut_lines(rows))
    without = _cut(D.haircut_lines(D.played_rows(rows)))
    assert with_void - without > 0.05, (with_void, without)


def test_the_rest_of_the_board_barely_moves():
    """The distortion has to be where the voids are, or the fixture is
    measuring something else."""
    rows = _board()
    for band in ("0.18-0.28", "0.45-1.01"):
        a = _cut(D.haircut_lines(rows), band)
        b = _cut(D.haircut_lines(D.played_rows(rows)), band)
        assert abs(a - b) < 0.02, (band, a, b)


# --- what gets dropped, and what does not ---------------------------------
def test_only_an_explicit_zero_is_dropped_never_an_unknown():
    """"Unknown" is not "absent". 240 NFL player-weeks and every college
    row carry no snap record at all, and guessing either way would invent
    the fact the whole check is about."""
    rows = [{"market": 0.14, "scored": 0, "played": True},
            {"market": 0.14, "scored": 0, "played": None},
            {"market": 0.14, "scored": 0, "played": False}]
    kept = D.played_rows(rows)
    assert len(kept) == 2
    assert [r["played"] for r in kept] == [True, None]


def test_a_player_who_dressed_and_did_nothing_stays_in():
    """He took the field, so the bet was live and the loss was real. Over
    twice as many rows are this case as are true non-participants —
    dropping them would be the opposite error, and a larger one."""
    rows = [{"market": 0.14, "scored": 0, "played": True} for _ in range(50)]
    assert len(D.played_rows(rows)) == 50


# --- the report says what it did ------------------------------------------
def test_the_report_prints_both_tables_and_calls_the_gap_a_width():
    """NOT A CORRECTION TO APPLY. The logs cannot tell an inactive from a
    healthy scratch of usage, so the honest answer is the interval, and
    saying so is the difference between a measurement and a claim."""
    got = D.void_lines(_board())
    body = "\n".join(got)
    assert "VOID at the book, not losses" in body
    assert "the truth is between the two tables" in body
    assert "cannot tell an inactive from a healthy scratch" in body
    assert "what the market actually charged" not in body, \
        "the second table reuses the first one's heading row"


def test_the_count_and_the_scorers_are_both_reported():
    """"How many were dropped" without "how many of them scored" invites
    the reader to wonder whether the filter ate winners. It cannot — a
    man with no snaps cannot score — and the line proves it rather than
    asking to be trusted."""
    got = "\n".join(D.void_lines(_board()))
    assert "never took a snap" in got
    assert "0 of them scored" in got


def test_a_board_with_no_snap_records_refuses_instead_of_agreeing():
    """College has no `snap_pct` market at all. Printing an identical
    table twice would read as the two answers agreeing, which is the
    strongest possible statement from the weakest possible evidence."""
    rows = [dict(r, played=None) for r in _board()]
    got = "\n".join(D.void_lines(rows))
    assert "participation unknown for every row" in got
    assert "what the market actually charged" not in got


def test_a_board_where_everyone_played_says_so_plainly():
    rows = [dict(r, played=True) for r in _board()]
    got = "\n".join(D.void_lines(rows))
    assert "took the field" in got
    assert "no part of the hold above is a void bet" in got


def test_the_harvest_carries_participation_on_every_row():
    """It has to come off the same query the outcome does, or the two are
    joined by a key that can silently miss."""
    import inspect
    src = inspect.getsource(D.collected)
    assert "market='snap_pct'" in src
    assert '"played": None if snap is None else float(snap) > 0' in src


def test_the_full_report_includes_the_sensitivity():
    """A finding this load-bearing must not depend on someone knowing to
    call a second function."""
    import inspect
    assert "void_lines(rows)" in inspect.getsource(D.report_lines)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
