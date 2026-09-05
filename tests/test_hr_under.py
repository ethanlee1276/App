"""'Under 0.5 Home Runs' reached the best-bets board. Never again.

Ethan, 2026-09-01: "we are showing 'under 0.5 homeruns' which is not a
real bet and you need to dive into why we did that and fix it."

THE DIVE. Odds feeds record placeholder unders against real one-sided
overs — engine/odds.py has documented the classic for weeks: "Caesars
showing 'over +850 / under -110' on a home run", a pair implying 63%
and reading as a 37% arbitrage against itself. The backtests and the
longshot board both filter these through `pair_is_sane`; the LIVE
recommendation path (`pick_side` → `devig_two_way`) never did. Devig a
63% pair and both fairs inflate at once — the under's to 83% against a
model that says "no homer" ~90% of the time, and there is the fat fake
edge that put a fake bet on the board.

Two fixes, both pinned here:
  * `devig_two_way` treats an insane pair as one-sided on the over,
    exactly as `longshots._price` always has — every caller healed at
    the root;
  * home runs are a yes-market. "To hit a home run" is the product;
    the board never sells the "won't happen" side even where some book
    genuinely quotes one (`allow_under=False` on the HR path).

Run directly: `python3 tests/test_hr_under.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.betting import pick_side
from engine.models import SportsbookLine
from engine.odds import ONE_SIDED_HOLD, american_to_prob, devig_two_way


def test_an_insane_pair_devigs_as_one_sided_not_as_a_gift():
    """The documented classic: +850 over, -110 placeholder under."""
    fair_over, fair_under = devig_two_way(850, -110)
    raw = american_to_prob(850)
    assert abs(fair_over - raw / ONE_SIDED_HOLD) < 1e-9, \
        "the real over devigs against the one-sided hold"
    assert fair_under == 1.0 - fair_over
    # The OLD arithmetic normalised the 63% pair: fair_under = .524/.629
    # ≈ 0.83 — a DISCOUNT against the model's ~0.90 no-homer number, and
    # that seven-point gap was the fake edge. The one-sided treatment
    # prices the under at its true complement (~0.90), and the edge is
    # gone.
    old_fair_under = american_to_prob(-110) / (raw + american_to_prob(-110))
    assert old_fair_under < 0.85, "the fake discount the old path granted"
    assert fair_under > old_fair_under + 0.05, (fair_under, old_fair_under)


def test_a_sane_pair_still_devigs_exactly():
    fair_over, fair_under = devig_two_way(-110, -110)
    assert abs(fair_over - 0.5) < 1e-9 and abs(fair_under - 0.5) < 1e-9
    fair_over, _ = devig_two_way(320, -450)
    assert 0.20 < fair_over < american_to_prob(320)


def test_pick_side_never_bets_the_fabricated_under():
    """The exact board scenario: model says no-homer ~90%, the feed
    carries the placeholder pair. The old path returned UNDER on a 7-pt
    fake edge; now the corrupt pair prices as over-only."""
    lines = [SportsbookLine("caesars", 0.5, 850, -110)]
    side, best, win, fair, edge = pick_side(lines, lambda ln: 0.10)
    assert side == "OVER", (side, edge)


def test_allow_under_false_refuses_even_a_sane_under():
    """A real book genuinely quoting 'no homer' at -450 is still not a
    product this board sells. The yes-market only bets yes."""
    lines = [SportsbookLine("dk", 0.5, 320, -450)]
    # The model thinks no-homer is near-certain: the under would win
    # the edge comparison if it were allowed to run.
    side, *_ = pick_side(lines, lambda ln: 0.02, allow_under=False)
    assert side == "OVER"
    side_free, *_ = pick_side(lines, lambda ln: 0.02)
    assert side_free == "UNDER", "other markets still shop both sides"


def test_the_mlb_path_pins_home_runs_to_the_over():
    with open(os.path.join(ROOT, "engine", "mlb", "betting.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "allow_under=prop.market != HOME_RUNS" in src


def test_two_sided_shopping_skips_insane_pairs_only():
    """One book posts the corrupt pair, another a real one — the real
    under is still shoppable; the corrupt one no longer competes."""
    lines = [SportsbookLine("caesars", 0.5, 850, -110),
             SportsbookLine("dk", 0.5, -105, -115)]
    side, best, *_ = pick_side(lines, lambda ln: 0.10)
    assert side == "UNDER" and best.book == "dk", (side, best.book)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
