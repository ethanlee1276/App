"""How much of the slate gets priced, and which prices survive the join.

Two findings from `--odds-doctor` on 2026-08-22, both of which showed up
as the same symptom Ethan reported — "Today's books prices are not being
pulled enough":

* Background cycles passed `--active-odds`, pricing only games inside a
  six-hour window. At 11am ET on a 15-game Saturday that reaches the 1:35
  games and nothing else: 153 prices across 3 of 15 games, and a board
  with 710 props and no book price on any of them. The window saved 96
  credits out of a 3,408 daily allowance — 2.8% — and the pacer had
  already RESERVED the full-slate cost anyway.
* Three prices were bought and thrown away because the book said "James
  Jarvis" and the slate said "Jim Jarvis". The near-miss detector already
  knew; it only printed a warning.

Run directly: `python3 tests/test_odds_coverage.py`
"""

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.oddsbudget import (BudgetState, CREDITS_PER_EVENT, WIDE_PULL_MARGIN,
                               daily_allowance, wide_pull_affordable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = _dt.date(2026, 8, 22)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


# --- how much of the slate ----------------------------------------------------
def test_a_funded_plan_prices_the_whole_slate():
    """The measured case: 68,663 credits in hand, 15 games on the board."""
    st = BudgetState(remaining=68663)
    assert wide_pull_affordable(16, st, DAY) is True


def test_a_free_plan_still_narrows():
    """The window was written for a 500-credit month and still earns its
    keep there. This is a poverty measure, not a deleted feature."""
    for bal in (500, 5000, 20000):
        assert wide_pull_affordable(16, BudgetState(remaining=bal), DAY) is False, bal


def test_the_margin_is_what_decides_it():
    """Right at the boundary, so the rule is the arithmetic and not a
    number that happens to work for one balance."""
    per_pull = 16 * CREDITS_PER_EVENT
    st = BudgetState(remaining=68663)
    allow = daily_allowance(st, DAY)
    assert (allow >= per_pull * WIDE_PULL_MARGIN) is wide_pull_affordable(16, st, DAY)


def test_the_window_was_saving_almost_nothing():
    """The number that made this a bug rather than a trade-off: the
    six-hour window covered ~4 of 15 games, so it saved under 3% of the
    day's allowance and cost the entire evening board."""
    st = BudgetState(remaining=68663)
    allow = daily_allowance(st, DAY)
    saved = (16 - 4) * CREDITS_PER_EVENT
    assert saved / allow < 0.05, f"{saved}/{allow}"


def test_the_launcher_narrows_only_when_it_cannot_afford_not_to():
    raw = _read("launch.py")
    src = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))
    assert "--active-odds" in src
    # Every append of the flag must sit behind _narrow_pull.
    i = 0
    while True:
        i = src.find('args.append("--active-odds")', i)
        if i < 0:
            break
        window = src[max(0, i - 200):i]
        assert "_narrow_pull(" in window, (
            "an --active-odds append no longer checks the budget first")
        i += 10


def test_narrowing_is_the_safe_direction_when_the_budget_is_unreadable():
    """A broken import must not become a way to overspend."""
    src = _read("launch.py")
    block = src[src.index("def _narrow_pull("):]
    block = block[:block.index("\ndef ", 1)]
    assert "except" in block and "return True" in block.split("except")[1]


# --- which prices survive the join --------------------------------------------
def test_the_loose_fallback_only_fires_when_it_is_unambiguous():
    """A first initial and a surname is a weak key. Two "J Rodriguez" on
    one slate is an ordinary Tuesday, and attaching the wrong player's
    price is worse than attaching none — a missing price shows as no bet,
    a wrong one shows as a bet at a number nobody offered."""
    src = _read("engine", "sources", "oddsapi.py")
    block = src[src.index("    loose: dict[str, list] = {}"):]
    block = block[:block.index("result.unmatched.append")]
    assert "len(cands) == 1" in block, \
        "the loose fallback no longer requires a unique candidate"


def test_a_recovered_price_is_counted_separately():
    """So a rise in these is visible. The fallback is a safety net, not a
    licence to stop maintaining the exact name map."""
    from engine.sources.oddsapi import OddsAttachResult
    assert OddsAttachResult().loose_matched == 0


def test_the_loose_key_joins_the_names_that_actually_missed():
    from engine.sources.oddsapi import _name_key_loose
    assert _name_key_loose("Jim Jarvis") == _name_key_loose("James Jarvis")
    assert _name_key_loose("Mike Trout") == _name_key_loose("Michael Trout")
    assert _name_key_loose("J. Chourio") == _name_key_loose("Jackson Chourio")
    # Different surnames stay apart.
    assert _name_key_loose("Jim Jarvis") != _name_key_loose("Jim Jarvin")
    # But two players CAN share a loose key — "A Judge" is both of these —
    # which is the whole reason the fallback refuses to fire unless
    # exactly one book entry carries it.
    assert _name_key_loose("Aaron Judge") == _name_key_loose("Austin Judge")


# --- the doctor must not read a redacted board -------------------------------
def test_the_doctor_reads_the_full_board_not_the_public_one():
    """web/data/ is what the paywall redacts. With QB_PAYWALL on,
    `recommendations` is emptied there — so --odds-doctor reported
    "0 prop(s): 0 with a real book price" on a board that was working,
    and that number was used to diagnose a bug in the odds pull."""
    src = _read("launch.py")
    block = src[src.index("def _odds_doctor") if "def _odds_doctor" in src
                else src.index("THE FULL COPY, NOT THE PUBLIC ONE"):]
    block = block[:block.index("gate_census")]
    assert '"data" / "built"' in block or "'data' / 'built'" in block, \
        "the doctor is back to reading the redacted public board"
    assert "read_from" in block, "it no longer says which copy it read"


def test_recommendations_really_is_a_redacted_key():
    """The premise. If `recommendations` stopped being redacted this test
    should fail loudly rather than the doctor quietly going back to a
    number that happens to be right."""
    from engine.gate import PAID_KEYS
    assert "recommendations" in PAID_KEYS


# --- the near-miss report must not advise a wrong join ------------------------
def test_two_different_players_are_not_reported_as_the_same_one():
    """Measured 2026-08-22: the report told Ethan that "Enrique Hernández"
    and "Elieser Hernández" were "almost certainly the same player" and
    that the fix was the name map. They are two different major leaguers.
    Doing what it said would attach one man's prices to the other's
    projections."""
    from engine.sources.oddsapi import _name_near_misses

    class P:
        def __init__(self, player, market):
            self.player, self.market = player, market

    class Slate:
        props = [P("Enrique Hernandez", "hits")]

    menu = {
        ("elieserhernandez", "hits"): {"player": "Elieser Hernandez"},
        ("emmanuelhernandez", "hits"): {"player": "Emmanuel Hernandez"},
    }
    assert _name_near_misses(Slate(), menu, set()) == [], \
        "an ambiguous loose key is still being reported as a near miss"


def test_a_genuine_unique_near_miss_is_still_reported():
    """The guard must not silence the real thing it was built for."""
    from engine.sources.oddsapi import _name_near_misses

    class P:
        def __init__(self, player, market):
            self.player, self.market = player, market

    class Slate:
        props = [P("Jim Jarvis", "hits")]

    menu = {("jamesjarvis", "hits"): {"player": "James Jarvis"}}
    got = _name_near_misses(Slate(), menu, set())
    assert len(got) == 1 and got[0]["book"] == "James Jarvis", got


def test_a_price_the_fallback_recovered_is_not_reported_as_lost():
    """Otherwise it reports a bug that has been fixed, every cycle, for
    as long as the two names disagree."""
    from engine.sources.oddsapi import _name_near_misses

    class P:
        def __init__(self, player, market):
            self.player, self.market = player, market

    class Slate:
        props = [P("Jim Jarvis", "hits")]

    menu = {("jamesjarvis", "hits"): {"player": "James Jarvis"}}
    from engine.sources.oddsapi import normalize_name
    key = (normalize_name("Jim Jarvis"), "hits")
    assert _name_near_misses(Slate(), menu, set(), recovered={key}) == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
