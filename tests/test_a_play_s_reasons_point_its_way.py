"""Every reason under a play points the play's way, or says it does not.

Ethan, 2026-10-06, on the game page's Plays that fit: "make sure
everything here is adding up and everything we say and are doing make
sense." Kendre Miller's UNDER 29.5 rushing yards listed "Script: favored
in a shootout — everyone eats" — a reason for the over — and every under
carried the over's yardage line ("a bet on his role AND a big play").

Run directly: `python3 tests/test_a_play_s_reasons_point_its_way.py`
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gameplan import _fit_reason, script_sign            # noqa: E402

SHOOTOUT = {"lean": "favored in a shootout — everyone eats"}
CLOCK = {"lean": "leads late and runs the clock — run volume up, pass volume a little down"}
TRAIL = {"lean": "expected to trail and throw — pass volume up, the run shelved"}
CLOSE = {"lean": "close game, both offenses stay in it"}


def test_the_script_knows_which_way_it_pushes_each_market():
    assert script_sign(SHOOTOUT["lean"], "rush_yds") == script_sign(SHOOTOUT["lean"], "rec_yds") == 1
    assert script_sign(CLOCK["lean"], "rush_yds") == 1 and script_sign(CLOCK["lean"], "rec_yds") == -1
    assert script_sign(TRAIL["lean"], "pass_yds") == 1 and script_sign(TRAIL["lean"], "rush_att") == -1
    assert script_sign(CLOSE["lean"], "rec_yds") == 0


def test_an_under_never_lists_a_script_for_the_over_as_its_reason():
    why = _fit_reason({"side": "UNDER", "market": "rush_yds", "game_script": SHOOTOUT})
    assert not any(w.startswith("Script:") for w in why), why
    assert "Against it — the script: favored in a shootout — everyone eats." in why
    # A script that backs the under is a reason for it.
    why = _fit_reason({"side": "UNDER", "market": "rec_yds", "game_script": CLOCK})
    assert any(w.startswith("Script: leads late") for w in why), why
    # A close game says nothing about an under, so it is left off.
    why = _fit_reason({"side": "UNDER", "market": "rec_yds", "game_script": CLOSE})
    assert not any("Script" in w or "script" in w for w in why), why


def test_an_over_keeps_its_script_and_says_when_it_is_against():
    assert "Script: favored in a shootout — everyone eats." in _fit_reason(
        {"side": "OVER", "market": "receptions", "game_script": SHOOTOUT})
    assert "Against it — the script: expected to trail and throw — pass volume up, the run shelved." in \
        _fit_reason({"side": "OVER", "market": "rush_yds", "game_script": TRAIL})


def test_the_yardage_line_is_worded_for_the_side_and_the_market():
    over = _fit_reason({"side": "OVER", "market": "rec_yds"})
    under = _fit_reason({"side": "UNDER", "market": "rush_yds"})
    assert over[-1].startswith("Yardage — a bet on his role AND a big play; the catches")
    assert under[-1] == "Yardage under — one long play can beat it; the carries under is the steadier way in."


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
