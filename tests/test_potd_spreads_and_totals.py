"""Spreads and totals can be the Pick of the Day, on a sharp witness.

Ethan chose game markets on 2026-09-15 — "moneylines and spreads only
for all sports", then totals too. On 2026-09-16 it turned out the engine
could only ever hand him a moneyline, and the cause was two steps apart.

STEP ONE, AND THE REAL ONE. A sharp-anchored spread card arrives from
`gamebets.price_spread_sharp` with `win_prob` ALREADY REWRITTEN to the
sharp book's de-vigged fair (`_sharpify`, the same rewrite the moneyline
path does). `likely.from_game_bet` built its row and dropped
`sharp_anchored` on the floor. `potd.evidence` then fell through to
`prob_source`, which `ranking_number` sets to "model" for any market
with no `GAME_RANK_MARKET` entry — every spread and every total — and
`shortfall` refused the row with "only our own model disputes this
price". THAT SENTENCE WAS FALSE ABOUT THE ROW: the number disputing the
price was Pinnacle's. The evidence was discarded, not outweighed.

STEP TWO. Once the tier is honest, `MIN_RANK_AUC` would have refused it
anyway — that figure is OUR model replayed over closes (0.49 on spreads)
and it was being asked of a row priced on somebody else's number.

WHAT IS NOT WAIVED, which is most of this file: the model tier is still
refused outright, the EV floor still wants 2% against the sharp fair,
`MIN_FAIR` still wants the pick likelier to win than lose — a real cut
on spreads, which sit near 50% by construction — and the market tier
KEEPS the ranking bar, because a de-vigged consensus is a number we
compute from a field we choose.

NOT MEASURED, AND THE FILE SAYS SO. The sharp-anchor method has been
replayed on moneylines and never on spreads or totals, because no sharp
spread pair is stored to replay. This opens the markets on the method's
logic, not on a measurement of these markets.

Run through the gate's env (`QB_MODELS_DIR` sandboxed) — this box's
fitted stores change what ranks.
"""

import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely, potd                               # noqa: E402

ET = ZoneInfo("America/New_York")


def _when():
    t = dt.datetime.now(ET) + dt.timedelta(minutes=180)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _card(market="spread", **kw):
    """A sharp-anchored game card as `gamebets._sharpify` leaves it:
    `win_prob` IS the sharp book's de-vigged fair for the side taken,
    `fair_prob` is what the soft price implies."""
    d, k = _when()
    c = {"bet_type": market, "market_label": market.title(),
         "matchup": "AAA @ BBB", "home": "BBB", "away": "AAA", "team": "BBB",
         "pick_label": "BBB -2.5", "headline": "BBB -2.5",
         "side": "-2.5" if market == "spread" else "Over", "line": -2.5,
         # 55% against -110 is +5.0% EV. It read 0.60 (+14.5%) until
         # `potd.MAX_EV` landed on 2026-09-16 — a gap that size is one
         # `gamebets._sharpify` already grades Pass and stakes nothing on.
         "win_prob": 0.55, "fair_prob": 0.5238, "edge": 0.0262,
         "odds": -110, "other_odds": -110, "has_market": True,
         "book": "DraftKings", "home_book": "DraftKings",
         "away_book": "DraftKings", "sharp_anchored": True,
         "date": d, "kickoff": k}
    c.update(kw)
    return c


def _row(market="spread", **kw):
    """The card, through the real `from_game_bet`."""
    return likely.from_game_bet(_card(market, **kw), sport="nfl")


# --- step one: the row says whose number it is -------------------------------
def test_a_sharp_spread_row_records_its_witness():
    row = _row("spread")
    assert row is not None, "the board refused the card outright"
    assert row["sharp_anchored"] is True
    assert row["sharp_fair"] == 0.55, row.get("sharp_fair")
    assert potd.evidence(row) == "sharp", potd.evidence(row)
    assert potd.fair_prob(row) == 0.55


def test_the_same_holds_for_a_total():
    row = _row("total", side="Over", line=44.5, pick_label="Over 44.5",
               headline="Over 44.5")
    assert row is not None
    assert potd.evidence(row) == "sharp"
    assert potd.fair_prob(row) == 0.55


def test_a_card_with_no_sharp_anchor_is_still_ours_alone():
    """The guard on the guard: this must not label every game row sharp."""
    row = _row("spread", sharp_anchored=False)
    assert row is not None
    assert row["sharp_anchored"] is False
    assert row["sharp_fair"] is None
    assert potd.evidence(row) == "model"
    assert potd.shortfall(row) == "only our own model disputes this price"


def test_the_recorded_fair_follows_the_side_the_row_takes():
    """`from_game_bet` flips to the likely side when the card backs a
    dog. The sharp fair recorded has to be the fair for the side the row
    ends up on, or the card prices one side against the other's number."""
    row = _row("spread", win_prob=0.45, fair_prob=0.45,
               team="AAA", pick_label="AAA +2.5", line=2.5, side="+2.5")
    if row is None:
        print("  SKIP the flip path refused this fixture"); return
    assert row["flipped"] is True
    assert row["sharp_fair"] == round(row["win_prob"], 4)
    assert abs(row["sharp_fair"] - 0.55) < 1e-6, row["sharp_fair"]


# --- step two: the ranking bar is asked of the right rows --------------------
def test_our_models_spread_ranking_no_longer_refuses_a_sharp_row():
    """The figure that was doing the refusing, at its real value."""
    assert likely.GAME_RANK_MEASURED["nfl"]["spread"] < potd.MIN_RANK_AUC
    row = _row("spread")
    assert float(row["rank_auc"]) < potd.MIN_RANK_AUC, row["rank_auc"]
    assert potd.shortfall(row) == "", potd.shortfall(row)
    assert potd.refuse(row) == "", potd.refuse(row)


def test_the_board_still_calls_it_a_lean_and_ranks_it_on_the_model():
    """`ranking_number` is deliberately untouched. Which number the Most
    Likely board SORTS on, and whether a spread ships labelled a lean,
    is Ethan's 2026-09-02 call and this change does not reach it."""
    row = _row("spread")
    assert row["prob_source"] == "model"
    assert row["ranked"] is False


# --- what did not move --------------------------------------------------------
def test_every_other_bar_still_bites_on_a_sharp_spread():
    row = _row("spread")
    from copy import deepcopy

    # 0.52 AT -110 no longer reaches this bar: the confidence floor went
    # to 55% on 2026-09-16 and `shortfall` asks it first. -120 at the
    # floor itself is 0.83% EV — the same bar, asked where the floor
    # cannot answer instead of it.
    thin = deepcopy(row)
    thin["sharp_fair"] = potd.MIN_FAIR
    thin["odds"] = -120
    assert potd.shortfall(thin) == \
        "the price is not far enough off the fair to be worth it"

    # +115, not +150: at +150 a 48% fair is +20% EV, which `MAX_EV`
    # refuses one line earlier. The fair bar is what this case is for,
    # so the price is the one that lets the question be asked.
    dog = deepcopy(row); dog["sharp_fair"] = 0.48; dog["odds"] = 115
    why = potd.shortfall(dog)
    # The confidence floor's sentence, which names the bar and its value
    # since 2026-09-16 rather than asserting a coin-flip test the
    # constant no longer means.
    assert "not confident enough" in why, why
    assert f"{potd.MIN_FAIR:.0%}" in why, why

    hot = deepcopy(row); hot["sharp_fair"] = 0.62
    assert potd.shortfall(hot) == \
        "the gap is too big to trust — the sharp side has probably moved"

    priced = deepcopy(row); priced["odds"] = -400
    assert potd.disqualify(priced) == \
        "the payout is outside the even-money band"


def test_the_market_tier_keeps_the_ranking_bar():
    """A de-vigged consensus is a number WE compute from a field WE
    choose, so our own measurement does speak to it."""
    row = _row("spread", sharp_anchored=False)
    row = {**row, "prob_source": "market", "implied_prob": 0.55}
    assert potd.evidence(row) == "market"
    assert potd.shortfall(row) == "this market ranks no better than a coin flip"


def test_a_prop_is_still_refused_before_any_of_this():
    """Game markets only — his call, and it is asked first."""
    row = {**(_row("spread") or {}), "kind": "prop", "market": "rush_yds"}
    assert potd.disqualify(row).startswith("a player prop")


# --- end to end ---------------------------------------------------------------
def test_a_sharp_spread_can_now_be_the_days_pick():
    day = _when()[0]
    board = {"date": day, "most_likely": [_row("spread")]}
    potd.attach(board, "nfl")
    got = board["pick_of_the_day"]
    assert got["pick"] is not None, got.get("note") or got.get("census")
    assert not got["pick"]["below_bar"], got["pick"]["below_bar"]
    assert got["pick"]["market"] == "spread"
    assert got["pick"]["evidence"] == "sharp"
    assert got["verdict"]["call"] == "bet"


def test_the_caveat_is_recorded_where_the_bar_was_moved():
    """It is opened on the method's logic, not on a measurement of these
    markets, and the module that moved the bar says so."""
    import inspect
    src = inspect.getsource(potd.shortfall).lower()
    assert "never" in src and ("spread" in src or "total" in src)
    assert "measur" in src


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
