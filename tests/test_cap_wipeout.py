"""An emptied board says the bankroll rule emptied it.

The exposure caps scale every stake by one factor and drop whatever
lands under `staking.MIN_STAKE_UNITS`. The 15u slate cap and that 0.1u
minimum are together an arithmetic ceiling on the COUNT — 150 — and past
it every stake falls through the floor at once and the board goes to
zero. Not smaller: empty.

That much is a bankroll rule doing its job. The defect was that nobody
was told. `cap_notes` has ridden in the board payload since the caps were
wired into both football builds and NO page has ever drawn it, so the one
slate where it matters most rendered through the last branch of the
empty-board chain — "No props clear your filters. Loosen the sliders" —
which is advice that cannot work, because no slider funds a bet the cap
will not pay for.

THE PREFIX IS THE JOINT and it is why this file is not two files. The
engine writes "NO BETS FUNDED:" and the page matches on it. Either side
can be reworded by someone who never sees the other, and the failure is
silent in exactly the way the original one was — the note is written, the
page draws nothing, and the board looks like an ordinary quiet night.

Run directly: `python3 tests/test_cap_wipeout.py`
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.correlation import apply_exposure_caps, max_fundable

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _emptied_note():
    """The real note, from the real function, on a slate past the cliff."""
    recs = [{"player": f"P{i}", "market": "pass_yds", "team": f"T{i}",
             "opponent": f"O{i}", "game_date": "2026-W01", "recommended": True,
             "stake_units": 1.0, "grade": "A"}
            for i in range(max_fundable() + 50)]
    notes = apply_exposure_caps(recs, [])
    assert not [r for r in recs if r.get("recommended")], "this slate should empty"
    return notes[0]


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ",
                                          "\nconst ", "\nlet ")]
    return APP[i:min([e for e in ends if e != -1] or [len(APP)])]


def test_the_page_matches_the_prefix_the_engine_actually_writes():
    """The joint. Both sides are read here, from source, so a reword on
    either one fails rather than going quiet."""
    body = _fn("capWipeoutNote")
    start = body.index('startsWith("') + len('startsWith("')
    prefix = body[start:body.index('"', start)]
    assert prefix, "the page matches on nothing"
    assert _emptied_note().startswith(prefix), (prefix, _emptied_note()[:60])


def test_the_page_reads_the_field_the_build_actually_publishes():
    body = _fn("capWipeoutNote")
    assert "cap_notes" in body, body
    for build in ("nfl_build.py", "cfb_build.py"):
        src = (ROOT / build).read_text()
        assert '"cap_notes"' in src, build


def test_the_wipeout_branch_is_read_before_every_other_empty_reason():
    """On a wipeout the picks DID clear the gate and DO carry real
    prices — they were zeroed one step later — so every downstream branch
    reads the slate correctly and answers the wrong question. The sliders
    branch is the one that used to catch it."""
    body = _fn("renderRecommended")
    at = body.index("const capped = capWipeoutNote();")
    assert at < body.index("if (recs.length && !real.length)"), body[at:at + 80]
    assert at < body.index("No props clear your filters")
    # And it is a branch, not a note appended beside the wrong advice.
    assert "if (capped) {" in body, body[at:at + 200]
    first = body.index("if (capped) {")
    assert "Loosen the sliders" not in body[first:body.index("} else if", first)]


def test_the_note_is_escaped_before_it_reaches_the_page():
    """It carries a team name from `_uniform_factor`'s `why`, which comes
    from board data rather than from this repo."""
    body = _fn("renderRecommended")
    first = body.index("if (capped) {")
    assert "escapeHtml(capped)" in body[first:body.index("} else if", first)]


def test_a_board_that_still_funds_something_draws_no_wipeout_note():
    recs = [{"player": f"P{i}", "market": "pass_yds", "team": f"T{i}",
             "opponent": f"O{i}", "game_date": "2026-W01", "recommended": True,
             "stake_units": 1.0, "grade": "A"} for i in range(max_fundable())]
    notes = apply_exposure_caps(recs, [])
    assert [r for r in recs if r.get("recommended")], "this slate should fund"
    body = _fn("capWipeoutNote")
    start = body.index('startsWith("') + len('startsWith("')
    prefix = body[start:body.index('"', start)]
    assert not any(n.startswith(prefix) for n in notes), notes


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
