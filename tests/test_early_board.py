"""The on-deck hitters — player props visible all day, journaled only
when real.

Ethan, 2026-08-26: "We should be showing player props all day every
day." The lineup hold is correct and untouched — a bet on a hitter who
might not play is a bet on a guess, and nothing journals before the
card posts. What changed is VISIBILITY: a prop that cleared every other
gate now says "waiting on the lineup card" on the board instead of
disappearing into held_by_rules. Real book prices ONLY: a strip of
model-baseline lines shipped beside it and Ethan killed it the same
day — "We should never ever display fake numbers on the site" — so a
test below pins the refusal, not just the feature.

What this file pins:

  * EARLY IS EXACTLY ONE MISSING THING. The flag fires only when the
    lineup check is the sole failure — a row also dead on juice, grade
    or Kelly is a held prop, not an early lean.
  * THE IL OUTRANKS THE CARD. An IL'd hitter also fails only the lineup
    check, and calling him "waiting on the card" would be waiting for a
    card that is not coming.
  * NOTHING EARLY EVER JOURNALS. The ledger's gate is recommended=True,
    and early rows are by definition not recommended.

Run directly: `python3 tests/test_early_board.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.mlb.pipeline import early_lean, run_mlb_slate      # noqa: E402
from engine.rules import condition                             # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _row(recommended=False, checks=()):
    return {"recommended": recommended, "checks": list(checks)}


def _c(key, passed):
    return condition(key, key, passed, "", "")


ALL_PASS = [_c(k, True) for k in
            ("grade", "kelly", "pregame", "confidence", "edge", "juice")]


def test_early_fires_only_when_the_card_is_the_sole_failure():
    row = _row(checks=ALL_PASS + [_c("lineup", False)])
    assert early_lean(row), "a prop one card away from a pick went invisible"


def test_a_second_failure_means_held_not_early():
    for other in ("juice", "grade", "kelly", "edge"):
        checks = [_c(k, k != other) for k in
                  ("grade", "kelly", "pregame", "confidence", "edge", "juice")]
        row = _row(checks=checks + [_c("lineup", False)])
        assert not early_lean(row), \
            f"a prop also dead on {other} was called an early lean"


def test_a_recommended_row_is_never_early():
    assert not early_lean(_row(recommended=True,
                               checks=ALL_PASS + [_c("lineup", True)]))


def test_a_home_run_row_never_uses_the_side_door():
    """The Long Shots board owns home runs outright — early must not put
    the quarantined market back on the main board."""
    row = _row(checks=ALL_PASS + [_c("lineup", False)])
    row["market"] = "home_runs"
    assert not early_lean(row)


def test_a_pitcher_prop_has_no_card_to_wait_on():
    # No lineup check at all — pitcher props never carry one.
    assert not early_lean(_row(checks=ALL_PASS))


def test_the_slate_stamps_every_row_and_the_census_counts_the_bucket():
    result = run_mlb_slate(os.path.join(ROOT, "data", "mlb_sample_slate.json"))
    rows = result["recommendations"]
    assert rows and all("early" in r for r in rows), \
        "a row left the pipeline without saying whether it is on deck"
    for r in rows:
        if r["early"]:
            assert not r["recommended"]
            assert early_lean(r), "the stored flag disagrees with the predicate"
    assert "awaiting_lineup" in result["gate_census"], \
        "the census lumps waiting rows back into held_by_rules"


def test_the_il_outranks_the_lineup_card():
    src = _read("engine", "mlb", "pipeline.py")
    i = src.index('d["early"] =')
    assert 'False if (il and il.get("on_il")) else early_lean(d)' in src[i:i + 120], \
        "an IL'd hitter reads as waiting for a card that is not coming"


def test_nothing_early_can_reach_the_journal():
    src = _read("engine", "ledger.py")
    assert 'not r.get("recommended")' in src, \
        "the journal's recommended gate moved — early rows depend on it"
    # And the pipeline never sets recommended on an early row: the flag is
    # defined as NOT recommended, pinned above; this is belt to that brace.
    p = _read("engine", "mlb", "pipeline.py")
    j = p.index("def early_lean")
    assert 'if row.get("recommended"):\n        return False' in p[j:j + 1600]


# --- the board ---------------------------------------------------------------

APP = _read("web", "js", "app.js")


def test_the_on_deck_block_wears_honest_words():
    assert "LINEUP PENDING" in APP
    assert "waiting only\n        on the lineup card" in APP
    assert "Not picks yet,\n        and not journaled." in APP


def test_no_fake_numbers_the_model_line_strip_stays_dead():
    """Ethan, 2026-08-26: "We should never ever display fake numbers on
    the site. If the props price are not fully available then we don't
    make the pick till then." The strip that showed model-baseline lines
    for unpriced hitters lived a few hours; this is its headstone."""
    assert "model line — no book price yet" not in APP
    assert "pendingRows" not in APP, "the unpriced-hitter strip came back"
    assert "No real price, no row" in APP, \
        "the refusal note left the code — the next reader will re-add it"


def test_the_empty_guard_counts_the_on_deck_rows():
    i = APP.index("if (!picks.length && !signals.length && !ridden.length")
    guard = APP[i:i + 200]
    assert "!earlyRows.length" in guard, \
        "a day with only on-deck rows renders an empty board"


def test_the_census_panel_names_the_new_bucket():
    assert 'awaiting_lineup: "cleared every gate' in APP


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
