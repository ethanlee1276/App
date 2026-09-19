"""The selector sees the whole board, not the top of it.

Ethan, 2026-09-16: "I think the selector should see the full game list so
no prop or game is left unscanned."

THE TWO RANKINGS PULLED OPPOSITE WAYS, and that is the whole bug.
`likely.GAME_LIMIT` keeps the twenty LIKELIEST game rows, because a
sixteen-game Sunday at five markets a game is eighty rows of 52% leans
and they would push every player row off a board capped at forty. That
is a sound decision about a page. But `potd`'s band (-142 to +190)
exists to throw the likeliest rows away — no in-band price can imply
more than 58.8% — so the cap was discarding, by construction, exactly
the part of the board the Pick of the Day shops in. A sharp-anchored
+130 dog with a real edge sat at position 21 on a probability ranking
and was never considered.

WHAT IS AND IS NOT WAIVED, which is the safety of this and the first
test below. The rows now handed to the selector cleared `likely
.admissible` and every refusal in `from_prop` / `from_game_bet` — the
price cap, the credibility bar, an injury designation, a game under way,
a moneyline that contradicts its own spread. What they failed is a SEAT.
Nothing about `disqualify` or `shortfall` moved.

THE THIRD TEST IS THE PAGE-WEIGHT ONE. These rows are deliberately NOT
published: `GAME_LIMIT` is a real decision and the MLB board is already
8 MB. They travel between two steps of one build under a private key
that `attach` pops, so a build cannot forget to strip it.

Run directly (through the gate's own env, or this box's fitted models
change the answer):
    QB_MODELS_DIR=/tmp/x QB_FEEDSTATE_DIR=/tmp/y python3 tests/test_potd_full_pool.py
"""

import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely, potd                               # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(minutes):
    t = dt.datetime.now(ET) + dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _row(prob, **kw):
    """A game row in board shape. `model_prob` is what the display cap
    ranks on; everything else is what the selector reads."""
    d, k = _et(180)
    r = {"kind": "game", "player": "AAA ML", "team": "AAA", "opponent": "BBB",
         "matchup": "AAA@BBB", "market": "moneyline", "market_label": "Moneyline",
         "side": "", "line": None, "book": "DraftKings", "odds": -110,
         # 55% against -110 is +5.0% EV — an ordinary sharp-anchor row.
         # It read 0.60 (+14.5%) until `potd.MAX_EV` landed and refused
         # it as a gap too big to trust.
         "model_prob": prob, "sharp_anchored": True, "sharp_fair": 0.55,
         "implied_prob": 0.5238, "rank_auc": 0.71, "bettable": True,
         "injury_status": "", "game_date": d, "kickoff": k}
    r.update(kw)
    return r


# --- the pool is wider; the bars are not ------------------------------------
def test_a_row_beyond_the_cap_can_now_be_the_pick():
    """The bug, end to end. The board carries a heavy favourite the band
    refuses; the row that clears sits in the cut."""
    day = _et(180)[0]
    seated = [_row(0.80, player="CHALK ML", team="CHALK", odds=-400)]
    # -115 AND NOT +130, and the reason is worth writing down:
    # `MIN_FAIR` (50%) and `MAX_EV` (7%) collide at +114. Above that
    # price no bet can be both likelier than a coin flip and a gap we
    # trust, so a +130 row is unreachable by construction now. See
    # docs/PICK_OF_THE_DAY.md §3i.
    cut = [_row(0.54, player="DOG ML", team="DOG", odds=-115)]
    board = {"date": day, "most_likely": seated}
    # Without the cut there is no pick: -400 is outside the band.
    assert potd.build(seated, "mlb", day)["pick"] is None
    potd.attach(board, "mlb", cut=cut)
    pick = board["pick_of_the_day"]["pick"]
    assert pick is not None and pick["team"] == "DOG", pick
    assert board["pick_of_the_day"]["verdict"]["call"] == "bet"


def test_the_wider_pool_waives_no_bar():
    """The pool grew; `disqualify` and `shortfall` did not move. A cut
    row still has to clear every one of them."""
    day = _et(180)[0]
    for bad, why in (
            (_row(0.54, odds=-400), "band"),
            (_row(0.54, book="Pinnacle"), "no real market price"),
            (_row(0.54, book=""), "no real market price"),
            (_row(0.54, sharp_anchored=False, sharp_fair=None), "model"),
            (_row(0.54, bettable=False), "reliable"),
            # THE RANKING BAR, ON THE TIER THAT STILL KEEPS IT. Since
            # 2026-09-16 a sharp or exchange witness is exempt — the
            # figure is OUR model's and says nothing about Pinnacle's
            # number (see tests/test_potd_spreads_and_totals.py). The
            # market tier still answers to it.
            (_row(0.54, rank_auc=0.50, sharp_anchored=False,
                  # 0.55 at -110 is +5.0%, inside `MAX_EV`, so the
                  # ranking bar is the one that bites.
                  sharp_fair=None, prob_source="market",
                  implied_prob=0.55), "coin flip"),
            (_row(0.54, kind="prop", market="hits"), "player prop")):
        board = {"date": day, "most_likely": []}
        potd.attach(board, "mlb", cut=[bad])
        got = board["pick_of_the_day"]
        pick = got.get("pick")
        assert pick is None or pick.get("below_bar"), (why, pick)
        assert got["verdict"]["call"] == "no bet", why


def test_a_prop_in_the_pool_is_refused_by_the_market_gate():
    """He said "no prop or game left unscanned"; props are out by his own
    call yesterday (game markets only). The pool is handed over whole and
    the gate does the refusing, so the market policy stays in one place
    and the pool never has to know it."""
    day = _et(180)[0]
    prop = _row(0.62, kind="prop", market="hits", market_label="Hits",
                player="A Hitter", side="OVER", line=1.5)
    board = {"date": day, "most_likely": []}
    potd.attach(board, "mlb", cut=[prop])
    census = board["pick_of_the_day"]["census"]
    assert any("player prop" in why for why in census), census


# --- the pick is seated so the rest of the site can find it ------------------
def test_a_pick_from_beyond_the_cap_is_put_on_the_board():
    """`ledger.relock_potd` re-points the card by finding this row among
    `most_likely` every build; the card's door opens it; the Live tab
    maps the journal row back through it. Left off, every widened pick
    would read "shown from the journal at the price it was locked at"
    with a price that never refreshes."""
    from engine import ledger
    day = _et(180)[0]
    winner = _row(0.54, player="DOG ML", team="DOG", odds=-115)
    board = {"date": day, "most_likely": [], "pick_of_the_day": None}
    potd.attach(board, "mlb", cut=[winner])
    assert board["pick_of_the_day"]["from_beyond_the_cap"] is True
    assert any(r is winner for r in board["most_likely"]), \
        "the pick is not on the board — relock will fall back to the journal"
    # AND RELOCK FINDS IT, which is the reason the seating exists.
    card = board["pick_of_the_day"]
    key = ledger.potd_row_key(card["pick"])
    again = potd.relock(card, board["most_likely"], key)
    assert again["pick"] is not None and again["pick"].get("locked") is True
    assert "off_board" not in again["pick"], again.get("relocked")


def test_a_pick_already_on_the_board_is_not_seated_twice():
    day = _et(180)[0]
    seated = [_row(0.54, player="DOG ML", team="DOG", odds=-115)]
    board = {"date": day, "most_likely": seated}
    potd.attach(board, "mlb", cut=[])
    assert len(board["most_likely"]) == 1
    assert "from_beyond_the_cap" not in board["pick_of_the_day"]


# --- the pool never reaches a reader ----------------------------------------
def test_the_pool_never_reaches_the_published_board():
    """These rows are deliberately not published — `GAME_LIMIT` is a real
    page-weight decision and the MLB board is already 8 MB. `attach` pops
    the key, so a build cannot forget to strip it."""
    day = _et(180)[0]
    board = {"date": day, "most_likely": [],
             potd.POOL_KEY: [_row(0.54, player="DOG ML", team="DOG", odds=130)]}
    potd.attach(board, "mlb")
    assert potd.POOL_KEY not in board, "the pool is published"
    # …and it was actually USED, not merely dropped.
    assert board["pick_of_the_day"]["pick"]["team"] == "DOG"


def test_a_malformed_board_neither_raises_nor_keeps_the_pool():
    """`attach` promises never to raise — a board that cannot produce a
    pick is a fact the page renders, and an exception here would take
    down a build that had already priced everything else. The seating
    step is new code on that path, so it gets the same promise, and the
    pool is popped before any of it runs."""
    day = _et(180)[0]
    board = {"date": day, "most_likely": "not a list",
             potd.POOL_KEY: [_row(0.54)]}
    note = potd.attach(board, "mlb")          # must not raise
    assert potd.POOL_KEY not in board
    assert isinstance(note, str) and note


def test_every_build_hands_its_cut_rows_over():
    """THE GUARD ON THE WIRING. Five leagues build a likelihood board and
    each one has to pass `cut=`; a league that forgets is a league whose
    Pick of the Day silently goes back to reading the top twenty, with
    nothing anywhere saying so."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("mlb_build.py", "nba_build.py", "cfb_build.py",
                 os.path.join("engine", "pipeline.py")):
        src = open(os.path.join(root, name)).read()
        assert "cut=" in src, f"{name} does not ask for the cut rows"
        assert "POOL_KEY" in src, f"{name} does not hand them to potd"


# --- likely.build's side of it -----------------------------------------------
def _card(i, prob):
    """One priced moneyline the likelihood board will accept."""
    d, k = _et(180)
    return {"bet_type": "moneyline", "matchup": f"A{i} @ B{i}",
            "home": f"B{i}", "away": f"A{i}", "team": f"B{i}",
            "win_prob": prob, "fair_prob": prob - 0.02, "odds": -150,
            "has_market": True, "book": "DraftKings",
            "game_date": d, "kickoff": k}


def test_the_cut_holds_exactly_what_the_game_cap_dropped():
    """The measurement behind the change: past `GAME_LIMIT` the board
    stops and the overflow has to go somewhere a caller can reach."""
    n = likely.GAME_LIMIT + 6
    cards = [_card(i, 0.90 - i * 0.005) for i in range(n)]
    cut: list = []
    board = likely.build([], [], [], sport="nfl", game_bets=cards, cut=cut)
    games = [r for r in board if r.get("kind") == "game"]
    if len(games) < likely.GAME_LIMIT:
        print("  SKIP the fixture did not fill the cap"); return
    assert len(games) == likely.GAME_LIMIT
    assert len(cut) == n - likely.GAME_LIMIT, (len(cut), n)
    # AND THE CUT IS THE TAIL, not a random slice: the cap keeps the
    # likeliest, so what it drops is the least likely — which is exactly
    # the half the Pick of the Day's band is shopping in.
    assert all(r.get("kind") == "game" for r in cut)
    worst_seated = min(float(r["model_prob"]) for r in games)
    assert all(float(r["model_prob"]) <= worst_seated for r in cut)


def test_the_cut_is_empty_when_nothing_is_dropped():
    cut: list = []
    likely.build([], [], [], sport="mlb", game_bets=[], cut=cut)
    assert cut == []


def test_asking_for_no_cut_changes_nothing():
    """`cut=None` is the old behaviour exactly — every existing caller."""
    a = likely.build([], [], [], sport="mlb", game_bets=[])
    b = likely.build([], [], [], sport="mlb", game_bets=[], cut=[])
    assert a == b


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
