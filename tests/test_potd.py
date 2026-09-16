"""The Lock of the Day picks one row, and can say whose opinion picked it.

Ethan, 2026-09-15: "I want it to be a 50-50 money flip, basically, either
from 80% to 100% flip of your money. And we need to look at other pro
sports bettors' logic and models ... So we need to figure out the models
they're using and implement that."

What this file guards is the part that would rot quietly. The band is a
product decision and is allowed to move; what is not allowed is for the
selector to publish a row it cannot defend — an invented price, a sharp
book's own quote dressed up as a ticket, a market measured at a coin
flip, a game already under way, or an "edge" that is nothing but our own
model shouting at a price. Each of those is one test.

Two of them execute arithmetic rather than asserting prose, because the
arithmetic is the whole argument and nothing else in the module restates
it: that no efficient favourite inside this band can be a heavy
favourite, and that the EV floor therefore asks for about one point of
disagreement rather than ten.

The band itself is a FLOOR on the winnings — "I’m putting 100 bucks on
it. I wanna make at least $70" — so the test that pins it checks the
cheap end to the cent. -143 pays $69.93 and is out.

Run directly: `python3 tests/test_potd.py`
"""

import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(minutes):
    """(date, "HH:MM") in Eastern, `minutes` from now. Relative on
    purpose: a fixture pinned to a date is a test that expires."""
    t = dt.datetime.now(ET) + dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _row(**kw):
    """A board row that clears every bar, for a game three hours out.

    Sharp-anchored by default because that is the tier the module is
    built to select: a sharp book quoted this market two ways, the
    de-vig says 60%, and DraftKings is paying a price that implies 52.4%.

    A GAME TOTAL RATHER THAN A PROP since 2026-09-15, because the day's
    pick is game markets only (`potd.disqualify`, and `ledger
    .is_game_row` for the test it makes). A total was chosen over a
    moneyline or a spread so that `side` and `line` keep the exact shape
    the prop fixture had — every number below this line is unchanged, and
    the tests that rest on them still rest on the same arithmetic.
    """
    d, k = _et(180)
    r = {"kind": "game", "player": "Over 3.5", "team": "AAA",
         "opponent": "BBB", "market": "total", "market_label": "Total",
         "side": "OVER", "line": 3.5, "book": "DraftKings", "odds": -110,
         "sharp_anchored": True, "sharp_fair": 0.60,
         "model_prob": 0.58, "implied_prob": 0.5238, "rank_auc": 0.71,
         "bettable": True, "injury_status": "", "game_date": d, "kickoff": k}
    r.update(kw)
    return r


def _consensus(**kw):
    """A row whose only witness is the de-vigged market consensus."""
    return _row(sharp_anchored=False, sharp_fair=None,
                prob_source="market", **kw)


# --- the arithmetic the band rests on ----------------------------------------
def test_the_price_table_is_the_one_quoted():
    """These prices are the table the feature was specified against. If
    any of them moves, the argument for the band moves with it."""
    want = {-190: (0.6552, 0.526), -125: (0.5556, 0.800), -110: (0.5238, 0.909),
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


def test_the_band_is_the_seventy_dollars_he_asked_for():
    """Ethan, 2026-09-15, rewording his own first spec: "I’m putting 100
    bucks on it. I wanna make at least $70." That is a FLOOR on the
    winnings, and the floor is the end that has to be exact — a price
    paying $69.93 is not the product."""
    assert potd.payout(-142) >= 0.70 and potd.in_band(-142)
    assert potd.payout(-143) < 0.70 and not potd.in_band(-143), \
        "−143 pays 0.6993 — seven cents short of the promise"
    assert potd.in_band(-110) and potd.in_band(100) and potd.in_band(190)
    assert not potd.in_band(-200), "pays 0.50 — half the promise"
    assert not potd.in_band(-400), "chalk is outside the band"
    assert not potd.in_band(191), "past the sanity cap"
    # No American price lives between -100 and +100; a quote claiming to
    # is broken, not a coin flip.
    assert not potd.in_band(-95) and not potd.in_band(99)
    for junk in (None, "", "x", 0):
        assert not potd.in_band(junk), junk


def test_the_band_is_decided_by_the_payout_not_by_the_odds():
    """`MIN_ODDS`/`MAX_ODDS` are for printing; the payout is the test.
    A drift between the two spellings would be invisible on the page and
    is the exact thing the derivation above exists to prevent."""
    for odds in range(-300, 301):
        if -100 < odds < 100:
            continue
        by_payout = potd.MIN_PAYOUT - 1e-9 <= potd.payout(odds) <= potd.MAX_PAYOUT + 1e-9
        by_odds = potd.MIN_ODDS <= odds <= potd.MAX_ODDS
        assert by_payout == by_odds == potd.in_band(odds), odds


def test_no_efficient_favourite_in_this_band_can_be_a_heavy_favourite():
    """THE MEASUREMENT THE MODULE IS BUILT ON, executed rather than
    asserted in prose. The most any in-band price can imply is what
    MIN_ODDS implies — 58.7%. So a straight favourite here is close to a
    coin flip by construction, which is why the selector needs a
    disagreement between two books rather than a confidence ranking.
    Replayed on the stored closes this came out at 51.4% NFL / 50.4%
    CFB; the ceiling below is why that was never going to be 68%."""
    ceiling = potd.implied(potd.MIN_ODDS)
    assert round(ceiling, 3) == 0.587, ceiling
    for odds in range(-300, 301):
        if -100 < odds < 100 or not potd.in_band(odds):
            continue
        assert potd.implied(odds) <= ceiling + 1e-9, odds


def test_the_ev_floor_asks_for_one_point_not_ten():
    """What MIN_EV actually demands, at both ends of the band. The
    answer is about a point of disagreement with the price — the size of
    gap a real sharp-versus-soft difference produces. A floor that
    needed ten would only ever be cleared by our own model being wrong,
    which is the failure this module was rebuilt to stop."""
    for odds in (potd.MIN_ODDS, -110, potd.MAX_ODDS):
        imp = potd.implied(odds)
        # The smallest fair that clears the floor at this price.
        need = next(f / 10000 for f in range(1, 10000)
                    if potd.edge({"sharp_anchored": True, "sharp_fair": f / 10000,
                                  "odds": odds}) >= potd.MIN_EV)
        assert 0.005 < need - imp < 0.02, (odds, need, imp)


# --- whose opinion it is -----------------------------------------------------
def test_the_witness_is_named_and_the_fair_comes_from_that_witness():
    """`evidence` and `fair_prob` are a pair. A row whose tier says
    "sharp" while its number came from somewhere else is the bug this
    pairing exists to make impossible."""
    sharp = _row()
    assert potd.evidence(sharp) == "sharp"
    assert potd.fair_prob(sharp) == 0.60, "the sharp book's de-vig, not ours"

    market = _consensus(implied_prob=0.56)
    assert potd.evidence(market) == "market"
    assert potd.fair_prob(market) == 0.56, "the consensus de-vig"

    ours = _row(sharp_anchored=False, sharp_fair=None, model_prob=0.62)
    assert potd.evidence(ours) == "model"
    assert potd.fair_prob(ours) == 0.62


def test_our_own_model_can_never_be_the_evidence():
    """Ethan, 2026-09-15: "we shouldn't use that 70%." Measured, not
    stylistic — likely.GAME_RANK_MEASURED has our moneyline model at
    0.677 against the market's 0.722. A price only we dispute is a price
    disputed by the weaker witness in the room."""
    ours = _row(sharp_anchored=False, sharp_fair=None, model_prob=0.70,
                implied_prob=0.5238)
    assert potd.disqualify(ours) == "", "it is a real, placeable, in-band bet"
    assert potd.shortfall(ours) == "only our own model disputes this price"
    assert potd.build([ours], "nfl", "2026-W02")["pick"]["below_bar"] != ""


def test_a_sharp_anchor_outranks_a_bigger_consensus_edge():
    """THE INVERSION THAT IS THE POINT OF THE MODULE. Sorting on edge
    size hands every day to the loudest disagreement, and the loudest
    disagreements come from the weakest witness."""
    quiet = _row(player="Pinnacle says", odds=-110, sharp_fair=0.57)
    loud = _consensus(player="Consensus says", odds=-110, implied_prob=0.62)
    assert potd.refuse(quiet) == "" and potd.refuse(loud) == ""
    assert potd.edge(loud) > potd.edge(quiet), "the loud one has the bigger edge"
    pick, _, _ = potd.choose([loud, quiet])
    assert pick["player"] == "Pinnacle says", pick["player"]


def test_the_edge_is_the_fair_against_the_price():
    """EV of one unit, off the shared converter. Checked at a price that
    pays less than the stake and at one that pays more, because that is
    where a sign error hides."""
    assert round(potd.edge(_row(odds=-125, sharp_fair=0.60)), 4) == 0.0800
    assert round(potd.edge(_row(odds=100, sharp_fair=0.60)), 4) == 0.2000
    assert potd.edge(_row(odds=-110, sharp_fair=0.40)) < 0
    assert potd.edge(_row(odds="x")) is None


# --- what is never shown -----------------------------------------------------
def test_a_row_outside_the_band_is_disqualified_not_shown_as_a_near_miss():
    """The band is the product definition, not a quality bar. "The
    strongest thing today is a -400 favourite" is not this feature
    having a quiet day; it is a different feature."""
    chalk = _row(odds=-400, implied_prob=0.80)
    assert potd.disqualify(chalk) == "the payout is outside the even-money band"
    got = potd.build([chalk], "nfl", "2026-W02")
    assert got["pick"] is None, got
    assert got["census"]["the payout is outside the even-money band"] == 1


def test_a_reserve_row_needs_a_sharper_witness_than_us():
    """CHANGED 2026-09-15, and the change is the pool this feature picks
    from. `likely` ships rows below its own 55% floor, labelled, and this
    module used to refuse every one. That answered the wrong question:
    `likely.MIN_PROB` asks "is this MOST LIKELY?" and a 53% sharp-anchored
    price at +100 is not, and is +6% EV, which IS this product. Since no
    in-band price can imply more than 58.8%, the rows nearest the band
    are exactly the ones `likely` is likeliest to have cut.

    What is not waived: the reserve band is measured at a loss on the
    MODEL's ranking (45-60% went -7.68% over 184 rows), so a reserve row
    reaches the pick only on a sharp or market witness."""
    ours = _row(reserve=True, sharp_anchored=False, sharp_fair=None,
                model_prob=0.70)
    assert potd.refuse(ours) == "the board itself says this did not clear its bar"

    anchored = _row(reserve=True)                 # sharp by default
    assert potd.refuse(anchored) == "", potd.refuse(anchored)
    got = potd.build([anchored], "nfl", "2026-W02")
    assert got["pick"]["below_bar"] == "", "a sharp-anchored reserve qualifies"
    assert got["pick"]["from_reserve"] is True, \
        "the card must say the row came from below the board’s own floor"


def test_the_card_keeps_the_de_vigged_fair_and_the_price_apart():
    """A `likely` row’s `implied_prob` is the DE-VIGGED fair
    (`likely._row_from`) and is what the market tier is selected on.
    `_card` used to overwrite it with the price’s raw break-even — a
    different quantity that looks like it — so the card stomped the very
    number the selection had just been made on."""
    row = _consensus(implied_prob=0.56, odds=-110)
    card = potd.build([row], "nfl", "2026-W02")["pick"]
    assert card["implied_prob"] == 0.56, "the de-vigged fair survives"
    assert card["price_implied"] == round(potd.implied(-110), 4)
    assert card["fair_prob"] == 0.56, "and it is what was priced against"


def test_an_invented_price_is_never_the_pick():
    for book in ("proxy", "", "   "):
        assert potd.disqualify(_row(book=book)) == "no real market price"


def test_the_sharp_book_prices_the_pick_and_is_never_the_ticket():
    """Pinnacle sets the fair and does not take the action. Quoting its
    own price as the bet would be a ticket nobody in the US can buy —
    the rule `odds.is_sharp_book` exists for, enforced here too because
    a rule enforced in one place is not a rule."""
    assert potd.disqualify(_row(book="Pinnacle")) == "no real market price"


def test_a_game_already_under_way_is_never_the_pick():
    d, k = _et(-30)
    assert potd.disqualify(_row(game_date=d, kickoff=k)) == "the game has already started"
    assert potd.disqualify(_row(live=True)) == "the game has already started"
    assert potd.disqualify(_row(started=True)) == "the game has already started"


def test_an_injury_designation_is_never_the_pick():
    assert potd.disqualify(_row(injury_status="questionable")) == \
        "the player is carrying an injury designation"


def test_a_price_that_is_still_more_likely_to_lose_is_refused():
    """A +EV underdog is a fine bet and a bad Lock of the Day. At +100 a
    fair of 48% clears the EV floor comfortably and still loses more
    often than it wins."""
    dog = _row(odds=100, sharp_fair=0.48, implied_prob=0.50)
    assert potd.edge(dog) is not None and potd.edge(dog) < potd.MIN_EV
    dog = _row(odds=100, sharp_fair=0.545, implied_prob=0.50)
    assert potd.edge(dog) > potd.MIN_EV, "clears the EV bar"
    assert potd.shortfall(_row(odds=100, sharp_fair=0.499, implied_prob=0.50)) != ""


def test_a_price_barely_off_the_fair_is_not_worth_the_day():
    thin = _row(odds=-110, sharp_fair=0.53)
    assert potd.disqualify(thin) == ""
    assert potd.shortfall(thin) == \
        "the price is not far enough off the fair to be worth it"


def test_an_unmeasured_or_coin_flip_market_is_refused():
    assert potd.shortfall(_row(rank_auc=None)) == "this market has never been measured"
    assert potd.shortfall(_row(rank_auc=0.49)) == "this market ranks no better than a coin flip"
    assert potd.shortfall(_row(bettable=False)) == \
        "this market's probabilities are not reliable enough to bet"


# --- how it ranks ------------------------------------------------------------
def test_equal_edges_go_to_the_better_price():
    """Two rows making the same claim to the nearest point are the same
    claim; the tie goes to the one that pays more. Ethan's "flip of your
    money", served wherever it costs nothing."""
    cheap = _row(player="Cheap", odds=-125, sharp_fair=0.6389)
    rich = _row(player="Rich", odds=100, sharp_fair=0.5750)
    assert round(potd.edge(cheap), 2) == round(potd.edge(rich), 2) == 0.15
    assert potd.refuse(cheap) == "" and potd.refuse(rich) == ""
    assert potd.payout(100) > potd.payout(-125)
    pick, _, _ = potd.choose([cheap, rich])
    assert pick["player"] == "Rich", pick["player"]
    # A genuinely bigger edge still wins outright.
    better = _row(player="Better", odds=-125, sharp_fair=0.70)
    pick, _, _ = potd.choose([cheap, rich, better])
    assert pick["player"] == "Better", pick["player"]


# --- what the page gets ------------------------------------------------------
def test_a_qualifying_pick_carries_the_numbers_the_card_shows():
    got = potd.build([_row()], "nfl", "2026-W02")
    pick = got["pick"]
    assert pick["below_bar"] == "", "a qualifying pick is not flagged"
    assert pick["evidence"] == "sharp"
    assert pick["fair_prob"] == 0.60
    assert pick["model_prob"] == 0.58, "ours travels as context, labelled"
    assert pick["payout_units"] == round(potd.payout(-110), 3)
    assert pick["ev_units"] == round(potd.edge(_row()), 4)
    assert pick["edge_points"] == round((0.60 - potd.implied(-110)) * 100, 1)
    assert got["band"] == [potd.MIN_ODDS, potd.MAX_ODDS]
    assert got["payout_band"] == [potd.MIN_PAYOUT, potd.MAX_PAYOUT]
    assert got["min_ev"] == potd.MIN_EV
    assert got["considered"] == 1


def test_a_quiet_day_shows_the_best_available_and_says_it_missed():
    """The pattern the boards already use so a page is never blank. The
    difference that matters is `below_bar`: the page reads it, and the
    journal refuses the row because of it."""
    thin = _row(sharp_fair=0.53)
    got = potd.build([thin], "nfl", "2026-W02")
    assert got["pick"] is not None
    assert got["pick"]["below_bar"] == \
        "the price is not far enough off the fair to be worth it"
    assert got["census"][got["pick"]["below_bar"]] == 1


def test_a_qualifying_pick_always_beats_a_near_miss():
    got = potd.build([_row(sharp_fair=0.53), _row(player="Good")],
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
    rows = [_row(odds=-400),
            _row(reserve=True, sharp_anchored=False, sharp_fair=None,
                 model_prob=0.70),
            _row(sharp_fair=0.53), _row(rank_auc=0.49),
            _row(sharp_anchored=False, sharp_fair=None, model_prob=0.70)]
    got = potd.build(rows, "nfl", "2026-W02")
    assert got["census"] == {
        "the payout is outside the even-money band": 1,
        # The reserve row and the model-only row BOTH have only our
        # number behind them; each is named by the more specific of the
        # two true reasons, which is what makes the census worth reading.
        "the board itself says this did not clear its bar": 1,
        "the price is not far enough off the fair to be worth it": 1,
        "this market ranks no better than a coin flip": 1,
        "only our own model disputes this price": 1}, got["census"]
    # The reserve refusal now lives in `shortfall`, not `disqualify`, so
    # it is a quality bar the page may fall back to rather than a row the
    # page may never show.
    assert "the board itself says this did not clear its bar" \
        not in potd.HARD_REASONS


def test_every_hard_reason_is_one_the_module_can_actually_give():
    """The tuple is documentation the page may read; a name in it that
    no branch produces is a lie that survives a refactor."""
    produced = set()
    for r in (_row(sharp_anchored=False, sharp_fair=None, model_prob=None,
                   implied_prob=None, prob_source=None),
              _row(book="proxy"), _row(book="Pinnacle"),
              _row(odds="x"), _row(odds=-400),
              _row(injury_status="out"), _row(live=True)):
        produced.add(potd.disqualify(r))
    assert produced == set(potd.HARD_REASONS), produced ^ set(potd.HARD_REASONS)


# ── game markets only ───────────────────────────────────────────────

def _prop(**kw):
    """A player prop that would otherwise clear every bar — same price,
    same sharp fair, same everything as `_row`. The only difference is
    that it is one player's line."""
    d, k = _et(180)
    r = {"kind": "prop", "player": "A Player", "team": "AAA",
         "opponent": "BBB", "market": "receptions",
         "market_label": "Receptions", "side": "OVER", "line": 3.5,
         "book": "DraftKings", "odds": -110, "sharp_anchored": True,
         "sharp_fair": 0.60, "model_prob": 0.58, "implied_prob": 0.5238,
         "rank_auc": 0.71, "bettable": True, "injury_status": "",
         "game_date": d, "kickoff": k}
    r.update(kw)
    return r


def test_a_player_prop_can_never_be_the_day_s_pick():
    """Ethan, 2026-09-15: "i do want the pick of the day to be moneylines
    and spreads only for all sports."

    THE REASON IS THE EVIDENCE LADDER, not volatility — a single bet's
    variance is p(1-p) whatever it is about. `exchangefair.MARKETS` is
    moneyline and nothing else, and a sharp book's prop coverage is thin
    to absent, so a prop is structurally stuck near the bottom of
    `EVIDENCE` while `shortfall` refuses a model-only row outright."""
    assert potd.disqualify(_prop()) != ""
    assert "game markets only" in potd.disqualify(_prop())
    # And the identical row as a game total is fine, so the refusal is
    # about the MARKET and not about the numbers.
    assert potd.disqualify(_row()) == ""


def test_it_is_refused_before_every_other_bar():
    """A prop with something else wrong with it is still counted as a
    prop. Ordering is what makes the census readable: "44 player props"
    is an answer, and "44 outside the band" over a board of props sends
    the reader to move a bar that would change nothing."""
    out_of_band = _prop(odds=-400)
    assert "game markets only" in potd.disqualify(out_of_band)
    started = _prop(**dict(zip(("game_date", "kickoff"), _et(-30))))
    assert "game markets only" in potd.disqualify(started)


def test_a_prop_is_not_the_fallback_lean_either():
    """`build` shows the best available when nothing clears. If a prop
    could be that, the card would name a player on a day the day's own
    universe had nothing — shown, labelled, and still from a pool the
    selector had just been told to ignore."""
    got = potd.build([_prop()], "nfl", "2026-09-16")
    assert got.get("pick") is None, got.get("pick")
    assert any("game markets only" in why for why in got["census"]), got["census"]


def test_all_four_game_markets_are_in():
    """Moneyline, spread and total are Ethan's list. Team total is in
    because it is a whole team's scoring and meets the reason he gave —
    and because `ledger.GAME_MARKETS` is the one definition of a game
    row, so a second list here would be a second thing to keep in sync.
    Cutting team totals is a one-line change if he wants it."""
    from engine.ledger import GAME_MARKETS
    assert set(GAME_MARKETS) == {"moneyline", "spread", "total", "team_total"}
    for market in sorted(GAME_MARKETS):
        row = _row(kind="game", market=market)
        assert potd.disqualify(row) == "", (market, potd.disqualify(row))


def test_a_row_with_no_kind_is_read_off_its_market():
    """An older board, a hand-built payload, a journal row read back —
    `kind` is not always there, and the market alone has to answer."""
    from engine import ledger
    assert ledger.is_game_row({"market": "moneyline"}) is True
    assert ledger.is_game_row({"market": "receptions"}) is False
    assert ledger.is_game_row({"kind": "game"}) is True
    assert ledger.is_game_row(None) is False


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
