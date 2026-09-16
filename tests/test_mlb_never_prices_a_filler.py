"""A baseball total nobody posted is not priced, and not published.

FOUND FROM THE LIVE BOARD, 2026-09-16. Ethan, reading the MLB Pick of the
Day census: *"Eleven of the twelve game rows carry an empty book field …
Those eleven all show odds of exactly -110, which is a filler number
rather than a posted quote … The price passes a band check and still is
not a price anyone posted."*

THE MECHANISM. `MLBGame` defaulted its four game-line prices to -110 and
its total to 8.5. Both are truthy and -110 is a real American price
sitting comfortably inside `potd`'s -142..+190 band, so:

  * a baseball game with no odds pull still had a total and a price;
  * `_game_bets` priced it, because the totals branch was guarded only
    on `has_rating`;
  * the card published at a number no book had quoted.

The moneyline was never exposed — `home_ml` defaults to 0 and its branch
checks it. The run line was not either — `spread` defaults to 0.0.
TOTALS WERE THE HOLE, and only because 8.5 and -110 are both truthy.

WHAT WAS STANDING BETWEEN THAT AND THE PICK OF THE DAY: one check on the
BOOK NAME (`potd.disqualify` → "no real market price"). A band check over
the same rows passes all eleven. That is the whole reason this is worth a
file: the number looks fine and is not a number.

`engine.models.Game` (NFL) has defaulted these to 0 and carried
`total_measured` / `spread_measured` since the football boards were
hardened (#198, #205). `oddsapi.apply_odds_to_slate` is sport-agnostic
and has been STAMPING those flags onto MLB games ever since — `MLBGame`
never declared them, so they landed as stray instance attributes and
nothing read them back. This is that fix reaching baseball.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.models import MLBGame                          # noqa: E402
from engine.mlb.pipeline import _game_bets                     # noqa: E402
from engine.rules import RuleConfig                            # noqa: E402


def _rated(**kw):
    """A game the model can price — ratings present, no odds unless given."""
    g = MLBGame(home="BBB", away="AAA", park="generic",
                home_rating=0.2, away_rating=-0.1,
                home_off=0.3, home_def=-0.2, away_off=0.1, away_def=0.2)
    for k, v in kw.items():
        setattr(g, k, v)
    return g


def _markets(cards):
    return {c.get("bet_type") for c in cards}


# --- the defaults are zero ----------------------------------------------------
def test_the_book_fields_are_declared_not_stray_attributes():
    """`attach_books` reads these with `getattr(g, ..., "")`, so an
    undeclared field is not an error — it is a silent empty string on
    every card, which is exactly what the live board showed."""
    g = MLBGame(home="BBB", away="AAA", park="generic")
    for field in ("home_ml_book", "away_ml_book", "home_spread_book",
                  "away_spread_book", "total_over_book", "total_under_book"):
        assert field in type(g).__dataclass_fields__, \
            f"{field} is not a declared field — it can only arrive by accident"


def test_an_unpriced_game_carries_no_price_at_all():
    """-110 is a real price. Zero is the absence of one, and only the
    second can be told apart from a quote by anything downstream."""
    g = MLBGame(home="BBB", away="AAA", park="generic")
    assert g.total_over_odds == 0 and g.total_under_odds == 0
    assert g.spread_home_odds == 0 and g.spread_away_odds == 0
    assert g.home_ml == 0 and g.away_ml == 0


def test_the_loader_does_not_mint_the_filler_either():
    """It was the SECOND place -110 came from, so changing the dataclass
    default alone would have left it in."""
    from engine.mlb.data_loader import _game
    g = _game({"home": "BBB", "away": "AAA", "park": "generic"})
    assert g.total_over_odds == 0 and g.spread_home_odds == 0


def test_the_posted_question_is_asked_the_way_the_nfl_asks_it():
    """Same names, same logic as `engine.models.Game`, so the two sports
    cannot drift to different definitions of "a book posted this"."""
    g = _rated()
    assert g.total_is_posted is False and g.spread_is_posted is False
    assert _rated(total_over_odds=-105, total_under_odds=-115).total_is_posted
    # …and the flag alone is enough, for the paths that build a priced
    # game directly.
    assert _rated(total_measured=True).total_is_posted
    assert _rated(spread_measured=True).spread_is_posted


# --- the pricer refuses -------------------------------------------------------
def test_a_total_nobody_posted_is_never_priced():
    cards = _game_bets([_rated()], RuleConfig())
    assert "total" not in _markets(cards), \
        "a total was priced for a game with no quoted total"


def test_a_posted_total_still_is():
    """The guard must not empty the board — a real quote still prices."""
    cards = _game_bets([_rated(total=8.5, total_over_odds=-105,
                               total_under_odds=-115)], RuleConfig())
    assert "total" in _markets(cards), _markets(cards)


def test_the_guard_is_on_the_total_alone_not_the_whole_rated_block():
    """A game can have a posted RUN LINE and no posted total. The first
    draft of this guarded the whole `has_rating` block, which put the
    team totals and the spread behind a posted total as well."""
    cards = _game_bets([_rated(spread=-1.5, spread_home_odds=-105,
                               spread_away_odds=-115)], RuleConfig())
    assert "spread" in _markets(cards), _markets(cards)
    assert "total" not in _markets(cards), _markets(cards)


def test_a_run_line_nobody_posted_is_never_priced():
    cards = _game_bets([_rated(spread=-1.5)], RuleConfig())
    assert "spread" not in _markets(cards), _markets(cards)


def test_a_team_total_is_behind_the_same_gate_as_the_total_it_is_split_from():
    """The LINE is `_half(g.total / 2)`. Over an unposted total that is
    half of `MLBGame.total`'s 8.5 default — a number split off a number
    nobody quoted. Football guards its team totals for exactly this
    reason; baseball priced two of them per rated game regardless, which
    is most of the eleven rows Ethan counted."""
    assert "team_total" not in _markets(_game_bets([_rated()], RuleConfig()))
    assert "team_total" not in _markets(_game_bets(
        [_rated(spread=-1.5, spread_home_odds=-105, spread_away_odds=-115)],
        RuleConfig())), "a posted run line is not a posted total"
    assert "team_total" in _markets(_game_bets(
        [_rated(total=8.5, total_over_odds=-105, total_under_odds=-115)],
        RuleConfig())), "the guard emptied a market that has a real line"


def test_nothing_published_on_a_game_market_carries_a_price_with_no_book():
    """THE PROPERTY ETHAN READ OFF THE BOARD, asked directly of the three
    markets baseball actually ingests odds for.

    Team totals are deliberately outside this loop and get their own
    assertion below. The books arrive from the same parse as the prices —
    `oddsapi` sets both on the Game together — so a fixture carrying one
    and not the other is not a shape production can produce."""
    g = _rated(total=8.5, total_over_odds=-105, total_under_odds=-115,
               spread=-1.5, spread_home_odds=-105, spread_away_odds=-115,
               home_ml=-130, away_ml=110,
               home_ml_book="DraftKings", away_ml_book="FanDuel",
               home_spread_book="DraftKings", away_spread_book="FanDuel",
               total_over_book="DraftKings", total_under_book="FanDuel")
    seen = set()
    for c in _game_bets([g], RuleConfig()):
        if c.get("bet_type") not in ("moneyline", "spread", "total"):
            continue
        odds = c.get("odds")
        if not odds:
            continue
        seen.add(c.get("bet_type"))
        book = (c.get("book") or c.get("home_book") or c.get("away_book") or "")
        assert str(book).strip(), (
            f"{c.get('bet_type')} published at {odds} with no book — the "
            f"exact shape of the eleven MLB rows")
    assert seen, "the fixture priced nothing, so this asserted nothing"


def test_the_team_total_price_is_still_a_filler_and_this_says_so_out_loud():
    """KNOWN AND UNFIXED, asserted so it cannot be fixed quietly or
    forgotten quietly.

    `gamebets.price_team_total` defaults `over_odds`/`under_odds` to -110
    and all three sports call it without odds, so every team-total card
    on every board publishes at a price no book posted. That is shared
    code on the football and college boards too, so it is not a baseball
    change and is not made here. When it IS made, this test fails and
    that is the signal to delete it."""
    g = _rated(total=8.5, total_over_odds=-105, total_under_odds=-115,
               total_over_book="DraftKings", total_under_book="FanDuel")
    tt = [c for c in _game_bets([g], RuleConfig())
          if c.get("bet_type") == "team_total"]
    assert tt, "no team total to check"
    assert all(c.get("odds") in (-110, 110) for c in tt), \
        f"the team-total filler moved: {[c.get('odds') for c in tt]}"
    assert all(not str(c.get("book") or "").strip() for c in tt), \
        "a team total named a book — the shared default may have been fixed"


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
