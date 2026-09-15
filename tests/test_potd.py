"""The Pick of the Day picks one row, and can say why it picked it.

Ethan, 2026-09-15: "I want too to a 'Pick of the day' for each sport
where we find 1 pick ... We want the price of the prop too fall in
between -190 and +190 so we can basically have a 'one props doubles
money' type of hit."

What this file guards is the part that would rot quietly. The band and
the floor are product decisions and they are allowed to move; what is
not allowed is for the selector to publish a row it cannot defend — an
invented price, a market measured at a coin flip, a game already under
way, or a probability the board itself refused. Each of those is one
test, and the arithmetic that ties the floor to the reachable half of
the band is another, because that arithmetic is the whole argument for
the default and nothing else in the module restates it.

Run directly: `python3 tests/test_potd.py`
"""

import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402
from engine.betting import MAX_CREDIBLE_EDGE                  # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(minutes):
    """(date, "HH:MM") in Eastern, `minutes` from now. Relative on
    purpose: a fixture pinned to a date is a test that expires."""
    t = dt.datetime.now(ET) + dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _row(**kw):
    """A board row that clears every bar, for a game three hours out."""
    d, k = _et(180)
    r = {"kind": "prop", "player": "A Player", "team": "AAA",
         "opponent": "BBB", "market": "receptions", "market_label": "Receptions",
         "side": "OVER", "line": 3.5, "book": "DraftKings", "odds": -140,
         "model_prob": 0.64, "implied_prob": 0.583, "rank_auc": 0.71,
         "bettable": True, "injury_status": "", "game_date": d, "kickoff": k}
    r.update(kw)
    return r


# --- the arithmetic the band rests on ----------------------------------------
def test_the_price_table_is_the_one_quoted():
    """These six prices are the table the feature was specified against.
    If any of them moves, the argument for MIN_PROB moves with it."""
    want = {-190: (0.6552, 0.526), -150: (0.6000, 0.667), -110: (0.5238, 0.909),
            100: (0.5000, 1.000), 150: (0.4000, 1.500), 190: (0.3448, 1.900)}
    for odds, (imp, pay) in want.items():
        assert round(potd.implied(odds), 4) == imp, (odds, potd.implied(odds))
        assert round(potd.payout(odds), 3) == pay, (odds, potd.payout(odds))


def test_plus_money_is_the_underdog_and_not_the_favourite():
    """The first draft inverted this and +190 came back 65.5%, which
    would have made every underdog look like the safest bet on the
    board. It is its own test because the bug was silent."""
    assert potd.implied(190) < 0.5 < potd.implied(-190)
    assert potd.payout(190) > 1.0 > potd.payout(-190)


def test_the_band_is_the_one_he_asked_for():
    assert potd.in_band(-190) and potd.in_band(190)
    assert not potd.in_band(-191) and not potd.in_band(191)
    assert not potd.in_band(-250), "chalk is outside the band"
    # No American price lives between -100 and +100; a quote claiming to
    # is broken, not a coin flip.
    assert not potd.in_band(-95) and not potd.in_band(99)
    for junk in (None, "", "x", 0):
        assert not potd.in_band(junk), junk


def test_the_floor_and_the_credible_cap_decide_which_prices_can_qualify():
    """THE ARGUMENT FOR THE DEFAULT, executed rather than asserted in
    prose. A pick must clear MIN_PROB and sit within MAX_CREDIBLE_EDGE
    of the book's own number, so the market's implied probability has to
    be at least MIN_PROB - MAX_CREDIBLE_EDGE. At the shipped values that
    is 0.50, which is exactly +100 — the even-money end of the band, and
    the "doubles money" Ethan asked for, still reachable."""
    need = potd.MIN_PROB - MAX_CREDIBLE_EDGE
    assert round(need, 4) == 0.50, need
    # A row at +100 claiming exactly the floor qualifies.
    assert potd.refuse(_row(odds=100, implied_prob=0.50,
                            model_prob=potd.MIN_PROB)) == ""
    # One point of price worse than that, and the same claim cannot be
    # credited any more.
    assert potd.shortfall(_row(odds=110, implied_prob=0.4762,
                               model_prob=potd.MIN_PROB)) != ""


# --- what is never shown -----------------------------------------------------
def test_a_row_outside_the_band_is_disqualified_not_shown_as_a_near_miss():
    """The band is the product definition, not a quality bar. "The most
    likely thing today is a -400 favourite" is not this feature having a
    quiet day; it is a different feature."""
    chalk = _row(odds=-400, implied_prob=0.80, model_prob=0.82)
    assert potd.disqualify(chalk) == "priced outside the even-money band"
    got = potd.build([chalk], "nfl", "2026-W02")
    assert got["pick"] is None, got
    assert got["census"]["priced outside the even-money band"] == 1


def test_a_reserve_row_can_never_be_the_pick():
    """The Most Likely board ships rows from below its own floor so the
    page is never blank. A row its own maker refused cannot be the pick
    of the day on any reading."""
    r = _row(reserve=True)
    assert potd.disqualify(r) == "the board itself says this did not clear its bar"
    assert potd.build([r], "nfl", "2026-W02")["pick"] is None


def test_an_invented_price_is_never_the_pick():
    for book in ("proxy", "", "   "):
        assert potd.disqualify(_row(book=book)) == "no real market price"


def test_a_game_already_under_way_is_never_the_pick():
    d, k = _et(-30)
    assert potd.disqualify(_row(game_date=d, kickoff=k)) == "the game has already started"
    assert potd.disqualify(_row(live=True)) == "the game has already started"
    assert potd.disqualify(_row(started=True)) == "the game has already started"


def test_an_injury_designation_is_never_the_pick():
    assert potd.disqualify(_row(injury_status="questionable")) == \
        "the player is carrying an injury designation"


def test_a_model_that_disagrees_with_the_market_too_hard_is_refused():
    """The standing lesson: when our number disagrees with a real price
    by more than we credit, ours is the one that is wrong."""
    wild = _row(odds=150, implied_prob=0.40, model_prob=0.62)
    assert potd.disqualify(wild) == "", "it is a real, placeable, in-band bet"
    assert potd.shortfall(wild) == \
        "the model disagrees with the market by more than we credit"


def test_an_unmeasured_or_coin_flip_market_is_refused():
    assert potd.shortfall(_row(rank_auc=None)) == "this market has never been measured"
    assert potd.shortfall(_row(rank_auc=0.49)) == "this market ranks no better than a coin flip"
    assert potd.shortfall(_row(bettable=False)) == \
        "this market's probabilities are not reliable enough to bet"


# --- how it ranks ------------------------------------------------------------
def test_confidence_leads_and_the_better_price_breaks_the_tie():
    """Two rows making the same claim to the nearest point are the same
    claim; the tie goes to the one that pays more. Ethan's "doubles
    money", served wherever it costs nothing."""
    cheap = _row(player="Cheap", odds=-180, implied_prob=0.643, model_prob=0.661)
    rich = _row(player="Rich", odds=-130, implied_prob=0.565, model_prob=0.660)
    # Both round to 0.66, and both sit inside the credible cap, so the
    # only thing left to separate them is what they pay.
    assert round(cheap["model_prob"], 2) == round(rich["model_prob"], 2) == 0.66
    assert potd.refuse(cheap) == "" and potd.refuse(rich) == ""
    assert potd.payout(-130) > potd.payout(-180)
    pick, _, _ = potd.choose([cheap, rich])
    assert pick["player"] == "Rich", pick["player"]
    # A genuinely higher number still wins outright.
    better = _row(player="Better", odds=-185, implied_prob=0.649, model_prob=0.72)
    pick, _, _ = potd.choose([cheap, rich, better])
    assert pick["player"] == "Better", pick["player"]


# --- what the page gets ------------------------------------------------------
def test_a_qualifying_pick_carries_the_three_numbers_the_card_shows():
    got = potd.build([_row()], "nfl", "2026-W02")
    pick = got["pick"]
    assert pick["below_bar"] == "", "a qualifying pick is not flagged"
    assert pick["payout_units"] == round(potd.payout(-140), 3)
    assert pick["edge_points"] == round((0.64 - 0.583) * 100, 1)
    assert got["band"] == [potd.MIN_ODDS, potd.MAX_ODDS]
    assert got["min_prob"] == potd.MIN_PROB
    assert got["considered"] == 1


def test_a_quiet_day_shows_the_best_available_and_says_it_missed():
    """The pattern the boards already use so a page is never blank. The
    difference that matters is `below_bar`: the page reads it, and the
    journal refuses the row because of it."""
    thin = _row(model_prob=0.56, implied_prob=0.583)
    got = potd.build([thin], "nfl", "2026-W02")
    assert got["pick"] is not None
    assert got["pick"]["below_bar"] == "under the confidence floor"
    assert got["census"]["under the confidence floor"] == 1


def test_a_qualifying_pick_always_beats_a_near_miss():
    got = potd.build([_row(model_prob=0.56, implied_prob=0.583), _row(player="Good")],
                     "nfl", "2026-W02")
    assert got["pick"]["player"] == "Good" and got["pick"]["below_bar"] == ""


def test_an_empty_board_is_a_sentence_not_an_exception():
    for rows in ([], None):
        got = potd.build(rows, "nfl", "2026-W02")
        assert got["pick"] is None and "no rows" in got["note"], got
    # And a board of nothing but chalk says something different.
    got = potd.build([_row(odds=-400, implied_prob=0.8)], "nfl", "2026-W02")
    assert got["pick"] is None and "in the band" in got["note"], got


def test_the_census_names_the_gate_that_was_binding():
    rows = [_row(odds=-400, implied_prob=0.8), _row(reserve=True),
            _row(model_prob=0.56, implied_prob=0.583), _row(rank_auc=0.49)]
    got = potd.build(rows, "nfl", "2026-W02")
    assert got["census"] == {
        "priced outside the even-money band": 1,
        "the board itself says this did not clear its bar": 1,
        "under the confidence floor": 1,
        "this market ranks no better than a coin flip": 1}, got["census"]


def test_every_hard_reason_is_one_the_module_can_actually_give():
    """The tuple is documentation the page may read; a name in it that
    no branch produces is a lie that survives a refactor."""
    produced = set()
    for r in (_row(model_prob=None), _row(reserve=True), _row(book="proxy"),
              _row(odds="x"), _row(odds=-400), _row(implied_prob=None),
              _row(injury_status="out"), _row(live=True)):
        produced.add(potd.disqualify(r))
    assert produced == set(potd.HARD_REASONS), produced ^ set(potd.HARD_REASONS)


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
