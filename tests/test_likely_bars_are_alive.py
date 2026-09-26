"""Every bar the Most Likely board relies on can actually fire.

#165, Ethan 2026-09-06: "make that work better and higher roi and higher
PnL". The task's own list of levers opens with *"verify each is doing
work: HEAVIEST_PRICE -250, MIN_PROB, rankable()/MIN_RANK_AUC"* — and
the warning behind it is `stakecheck --select`: ranking by probability
and ignoring price measured WORST on the edge book (-9.3%, 56.2% hit,
average winner -163, 94% the same bets as the book's own price
ordering). What keeps this board from being that naked arm is exactly
these bars. If one of them is dead, the board IS that arm and the
scoreboard is measuring something nobody designed.

A DEAD BAR IS INVISIBLE IN A CENSUS, which is why this is a file rather
than a droplet check. `likely_census` counts refusals by reason — so an
unreachable branch reports **zero**, and zero is exactly what a bar that
is simply not binding tonight reports. The two readings are opposite
("this rule is protecting nothing" vs "this rule is not needed tonight")
and the number cannot tell them apart.

That is not hypothetical. 2026-09-16 alone turned up three guards that
could not fire: `gamerank.market_lines`'s thin-sample branch (under a
floor where the AUC is already None), the Pick of the Day card's error
branch (behind a bail that returns first), and `MIN_RANK_AUC` asked of
rows whose tier had already been refused. Each read as protection.

SO EACH REFUSAL IS PROVEN REACHABLE, by producing a row that earns it.
This file asserts nothing about whether a bar is at the RIGHT level —
that is a measurement and it needs the droplet's settled rows (#165's
scoreboard). It asserts only that the bar is alive, so that when the
census says zero, zero means "not binding".

Run through the gate's env.
"""

import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely                                     # noqa: E402


def _row(**kw):
    """A row that clears every bar, so whatever `kw` breaks is the one
    under test and the refusal that comes back names it."""
    r = {"model_prob": 0.70, "odds": -120, "book": "DraftKings",
         "implied_prob": 0.66, "market": "hits", "player": "X"}
    r.update(kw)
    return r


def test_the_clean_row_really_does_clear_everything():
    """The fixture is the control. If it stops clearing, every test
    below starts passing for the wrong reason."""
    assert likely.admissible(_row()) == "", likely.admissible(_row())


# --- one row per refusal, and the refusal has to be the named one -------------
def test_the_likelihood_floor_fires():
    why = likely.admissible(_row(model_prob=likely.MIN_PROB - 0.01))
    assert why == "under the likelihood floor", why


def test_the_price_cap_fires():
    """HEAVIEST_PRICE, the bar #165 names first. At -250 a bet needs
    71.4% to break even; past it "most likely" stops being a pick."""
    why = likely.admissible(_row(odds=likely.HEAVIEST_PRICE - 1,
                                 model_prob=0.80, implied_prob=0.72))
    assert "chalk, not a pick" in why, why
    # …and it is not off by one at the cap itself.
    assert likely.admissible(_row(odds=likely.HEAVIEST_PRICE,
                                  model_prob=0.80, implied_prob=0.72)) == ""


def test_a_fabricated_price_is_refused():
    why = likely.admissible(_row(book="proxy"))
    assert why == "no real market price", why


def test_a_price_no_book_could_post_is_refused():
    why = likely.admissible(_row(odds=-97))
    assert why == "price a book could not have posted", why


def test_the_missing_probability_branch_fires():
    why = likely.admissible(_row(model_prob=None))
    assert why == "no probability", why


def test_the_injury_hold_fires():
    why = likely.admissible(_row(injury_status="Questionable"))
    assert "held until inactives confirm" in why, why


def test_all_three_credibility_bars_fire_and_say_which_number():
    """THREE QUESTIONS OF THREE DIFFERENT PROBABILITIES, and until
    2026-09-08 two of them answered in sentences a reader could not tell
    apart. They also read DIFFERENT FIELDS, which is the trap this test
    fell into first: `_credible` compares against `implied_prob`,
    `engine_credible` against `fair_prob`. A fixture carrying the wrong
    one makes a live branch look dead."""
    shown = likely.admissible(_row(model_prob=0.95, implied_prob=0.40))
    assert shown == ("the shown probability disagrees with the market by "
                     "more than we credit"), shown

    # The model's OWN read, on a row that ranks on the market's number.
    # `model_prob` has to stay credible or the bar above answers first.
    own = likely.admissible(_row(prob_source="market", win_prob=0.99))
    assert own == ("the model's own read disagrees with the market by more "
                   "than we credit"), own

    # The RAW claim, before the shrink — the Gelof bar. Against
    # `fair_prob`, and NOT on a market-ranked row (it returns True there
    # by design, measured 2026-09-08).
    raw = likely.admissible(_row(engine_raw_prob=0.99, fair_prob=0.66))
    assert raw.startswith("the raw model claim"), raw


def test_the_reserve_floor_moves_and_only_it_moves():
    """`floor` overrides MIN_PROB for the reserve pass and NOTHING else
    — the price cap in particular must not relax, because the reserve
    exists to fill a thin page and a -400 row is chalk on any page."""
    # `implied_prob` tracks the lowered probability, or the credibility
    # bar answers before the floor does and the test measures that
    # instead.
    low = _row(model_prob=likely.RESERVE_MIN_PROB + 0.01, implied_prob=0.44)
    assert likely.admissible(low) == "under the likelihood floor"
    assert likely.admissible(low, floor=likely.RESERVE_MIN_PROB) == ""
    chalk = _row(model_prob=0.80, implied_prob=0.72,
                 odds=likely.HEAVIEST_PRICE - 1)
    assert "chalk" in likely.admissible(chalk, floor=likely.RESERVE_MIN_PROB), \
        "the reserve pass relaxed the price cap — it may only move the floor"


# --- the structural claim ------------------------------------------------------
def test_every_refusal_this_function_can_return_is_reachable():
    """THE ONE THAT CATCHES THE NEXT DEAD BAR. Reads the refusal strings
    out of the source and requires each to be produced by some row
    above. A branch nobody can reach reads as protection in review and
    as a zero in the census, and those are the two places anybody
    would look.

    A new refusal added to `admissible` fails this test until a row
    earning it is added here, which is the point.
    """
    src = inspect.getsource(likely.admissible)
    # Every literal this function can hand back, f-strings included.
    literals = set(re.findall(r'return (?:f?)"([^"]+)"', src))
    literals.discard("")
    produced = set()
    for r in (_row(model_prob=None),
              _row(model_prob=likely.MIN_PROB - 0.01),
              _row(book="proxy"),
              _row(odds=-97),
              _row(odds=likely.HEAVIEST_PRICE - 1, model_prob=0.80,
                   implied_prob=0.72),
              _row(model_prob=0.95, implied_prob=0.40),
              _row(injury_status="Questionable"),
              _row(prob_source="market", win_prob=0.99),
              _row(engine_raw_prob=0.99, fair_prob=0.66)):
        why = likely.admissible(r)
        if why:
            produced.add(why)

    def _matches(lit):
        # f-string literals carry {…} placeholders; compare on the fixed
        # part so `heavier than {HEAVIEST_PRICE} — chalk` matches its
        # rendered form.
        stem = lit.split("{")[0].strip()
        tail = lit.rsplit("}", 1)[-1].strip()
        return any((stem and stem in p) or (tail and tail in p)
                   for p in produced)

    dead = sorted(lit for lit in literals if not _matches(lit))
    assert not dead, (
        f"these refusals cannot be produced by any row — each is either "
        f"unreachable or untested, and both read as a zero in the census: "
        f"{dead}")


def test_the_price_cap_and_the_floor_are_the_numbers_written_down():
    """#165 quotes MIN_PROB as 0.30; the constant reads 0.55 — Ethan
    raised it on 2026-09-06, after that note was written. Pinned so the
    next reader compares against the code rather than the note."""
    assert likely.HEAVIEST_PRICE == -250
    assert likely.MIN_PROB == 0.55
    assert likely.RESERVE_MIN_PROB < likely.MIN_PROB


def test_the_ranking_bar_is_a_real_gate_on_a_real_market():
    """`rankable` / MIN_RANK_AUC, the third bar #165 names. Asked of a
    market with no measurement at all, which is the state every new
    market starts in."""
    assert likely.MIN_RANK_AUC == 0.60
    assert likely.rankable("a_market_nobody_measured", "nfl") is False


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
