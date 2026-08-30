"""No second name for a paid board may hand its rows back.

THE FOURTH TIME. `engine.gate` strips paid keys by name, and its own
header already says the failure out loud — "key-stripping only protects
boards whose keys were anticipated". It has been taught that three
times: `predmarkets` needed PAID_FILES because its whole payload was the
product; UFC slipped through from the other side because it ships its
picks under `picks` and `pass_list`; and on 2026-08-30 `board_shelves`
was added — the likelihood board grouped by market for the page's layout,
carrying a COPY of every row `most_likely` holds — and was not added
here. `most_likely` came back empty and the identical players, prices
and probabilities came back in the next key down.

EVERY EXISTING TEST OF THIS FILE IS AN ENUMERATION, which is why none of
them caught it: they check that the keys someone thought of are stripped,
and a new key is by definition one nobody thought of.

So this file does not enumerate. It plants a sentinel inside every paid
board, redacts, and asserts the sentinel survives NOWHERE in the output —
whatever key it might have been copied into, however deeply nested. A new
view of a paid board fails this the day it is added, without anyone
remembering to update a list.

Run directly: `python3 tests/test_gate_leak.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import gate

#: Not a name anything could produce, so a hit is a leak and never a
#: coincidence.
SENTINEL = "ZZQPAIDROWSENTINEL"


def _row():
    return {"player": SENTINEL, "market": "anytime_td", "odds": -120,
            "model_prob": 0.61, "book": "DK"}


def _payload():
    """A board carrying the sentinel in every paid shape there is."""
    return {
        "generated_at": "2026-08-30T12:00:00", "sport": "nfl",
        "date": "2026-09-07",
        # Free context a reader without a subscription is meant to keep.
        "games": [{"home": "KC", "away": "BAL"}],
        "most_likely": [_row()],
        "board_shelves": [{"key": "touchdowns", "title": "Touchdown scorers",
                           "markets": ["anytime_td"], "rows": [_row()]}],
        "recommendations": [_row()],
        "long_shots": [_row()],
        "longshot_watch": [_row()],
        "edge_board": [_row()],
        "parlays": [{"legs": [_row()]}],
        "market_scan": {"arbs": [_row()], "stale": [_row()]},
    }


def _leaks(out) -> bool:
    return SENTINEL in json.dumps(out)


# --- the structural guard -------------------------------------------------
def test_no_paid_row_survives_redaction_under_any_key():
    """THE TEST THAT WOULD HAVE CAUGHT IT. Not "is board_shelves in the
    list" — "did any row escape", which is the thing actually promised."""
    assert not _leaks(gate.redact(_payload(), "recommendations.json"))


def test_the_same_holds_with_no_filename_hint():
    """`redact` is called without a name in some paths; the default set
    has to be at least as strict."""
    assert not _leaks(gate.redact(_payload()))


def test_the_sentinel_really_is_present_before_redaction():
    """Guards the guard. A typo in the fixture would make every
    assertion above pass by testing nothing."""
    assert _leaks(_payload())


def test_free_context_still_survives():
    """Stripping everything would pass the test above and break the
    site. The games a reader can see must still be there."""
    out = gate.redact(_payload(), "recommendations.json")
    assert out.get("games"), out


def test_the_reader_is_told_what_was_taken():
    out = gate.redact(_payload(), "recommendations.json")
    assert out.get("locked_reason") == "subscription"
    assert "most_likely" in (out.get("locked") or {})
    assert "board_shelves" in (out.get("locked") or {})


# --- the specific regression ----------------------------------------------
def test_the_layout_view_of_the_likelihood_board_is_paid():
    """`board_shelves` is the same board under a second name. Named
    explicitly as well, so a reader of this file learns the case."""
    assert "board_shelves" in gate.PAID_KEYS
    assert "most_likely" in gate.PAID_KEYS


def test_stripping_one_and_not_the_other_is_what_broke():
    """The exact shape of the bug, kept executable: empty the board and
    leave its copy, and the sentinel is still in the output."""
    d = _payload()
    d["most_likely"] = []
    assert _leaks(d), "fixture no longer reproduces the leak"
    assert not _leaks(gate.redact(d, "recommendations.json"))


# --- and the college board carries the same furniture ---------------------
def test_college_serves_the_guide_and_the_shelves():
    """CFB published `most_likely` with neither, so its board drew with
    no trust line at all — no "picked on how likely it is", no
    "recorded, not staked" — which is the confusion engine/boards
    exists to end."""
    with open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'out["board_guide"] = _boards.guide()' in src
    assert 'out["board_shelves"] = _boards.shelves("cfb"' in src


def test_a_sport_with_no_likelihood_board_gets_no_shelves():
    """Nothing in engine/mlb produces `most_likely`, so a shelf spec for
    baseball described a board that does not exist."""
    from engine import boards
    assert boards.shelves("mlb") == []
    assert boards.shelves("mlb", [{"market": "hits"}]) == []
    assert not hasattr(boards, "BASEBALL_SHELVES")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
