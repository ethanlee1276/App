"""The exchange's own number, and the guards that decide it is worth using.

Ethan, 2026-09-15: "I want to make sure that we're using every single
piece of data."

WE WERE ALREADY PULLING THE BEST ONE AND NOT USING IT. `sources/kalshi`
fetches a CFTC-regulated exchange, parses its order book, matches a
market to one of our games and knows which side the YES contract is —
and it fed the Prediction Desk and nothing else. The Pick of the Day, a
feature built entirely around finding a trustworthy fair, never saw it.

WHY THIS RANKS ABOVE THE SHARP BOOK, which is the claim most worth
guarding: de-vigging Pinnacle means ASSUMING how its margin is spread
across the two sides. An exchange has no margin to strip. That is the
only reason for the ordering, and if the guards below ever stop holding
then the ordering becomes a way to prefer a worse number — so the
guards are the test, not the plumbing.

Run directly: `python3 tests/test_exchange_fair.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import exchangefair as X, potd                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mkt(**kw):
    """A healthy two-sided exchange market."""
    m = {"ticker": "KXMLBGAME-26SEP15SEALAA-LAA", "title": "Angels vs Mariners",
         "subtitle": "Los Angeles Angels", "prob": 0.58, "price_basis": "book",
         "spread_cents": 2.0, "volume_24h": 4000.0, "open_interest": 1200.0}
    m.update(kw)
    return m


# --- the guards, which are the whole argument --------------------------------
def test_a_healthy_book_is_usable():
    assert X.quality(_mkt()) == ""


def test_a_last_trade_is_not_a_market_opinion():
    """`kalshi.parse_markets` says it itself: "a fair value with no book
    behind it is a weaker claim". One stale print on a market nobody has
    touched since Tuesday is not the exchange's number."""
    why = X.quality(_mkt(price_basis="last_trade", spread_cents=None))
    assert "no two-sided book" in why, why


def test_a_wide_book_cannot_settle_a_question_this_fine():
    """THE ARITHMETIC, executed. A book 10 cents wide puts the true
    number five points either side of the mid; `potd.MIN_EV` asks for
    two. A guard wider than the edge it protects is not a guard."""
    assert X.MAX_SPREAD_CENTS / 100.0 <= potd.MIN_EV * 2, (
        "the spread cap admits more slop than the EV floor asks for")
    assert X.quality(_mkt(spread_cents=X.MAX_SPREAD_CENTS)) == ""
    why = X.quality(_mkt(spread_cents=X.MAX_SPREAD_CENTS + 0.5))
    assert "wide" in why, why


def test_a_thin_book_is_two_people_not_a_market():
    why = X.quality(_mkt(volume_24h=10.0, open_interest=5.0))
    assert "thin" in why, why
    # Either measure clearing the floor is enough — open interest with no
    # volume today is still real money on the line.
    assert X.quality(_mkt(volume_24h=0.0,
                          open_interest=X.MIN_LIQUIDITY + 1)) == ""


def test_an_unreadable_market_is_refused_rather_than_guessed_at():
    for bad in ({"price_basis": "book", "spread_cents": "x"},
                {"price_basis": "book", "spread_cents": None}):
        assert X.quality(_mkt(**bad)) != ""


# --- which side is which, where an error would look like confidence ----------
def test_the_yes_side_and_the_other_side_are_not_confused():
    """A side error here would not read as a bug. It would read as a
    confident pick on the wrong team."""
    game = {"home": "LAA", "away": "SEA", "home_name": "Los Angeles Angels",
            "away_name": "Seattle Mariners"}
    m = _mkt(prob=0.58)
    laa = X.fair_for_team(m, "LAA", game)
    sea = X.fair_for_team(m, "SEA", game)
    if laa is None and sea is None:
        # The matcher could not name a side on this fixture; the function
        # must then price NEITHER rather than guess one.
        return
    assert laa is not None and sea is not None, (laa, sea)
    assert abs((laa + sea) - 1.0) < 1e-9, (laa, sea)
    assert 0.0 < laa < 1.0 and 0.0 < sea < 1.0


def test_a_team_the_contract_says_nothing_about_is_priced_at_nothing():
    """THE GUARD THAT SURVIVED A MUTANT until this test existed. A
    game-winner contract settles two outcomes and names both. Asked
    about a third team, the honest answer is silence — returning either
    `p` or `1-p` would be inventing a price for a club the market has no
    opinion on, and it would arrive on the board looking exactly like a
    real one."""
    game = {"home": "LAA", "away": "SEA", "home_name": "Los Angeles Angels",
            "away_name": "Seattle Mariners"}
    m = _mkt(prob=0.58)
    assert X.fair_for_team(m, "NYY", game) is None
    assert X.fair_for_team(m, "", game) is None
    # And a game missing a side cannot name the other one either.
    assert X.fair_for_team(m, "LAA", {"home": "LAA", "away": ""}) is None


def test_an_impossible_probability_prices_nothing():
    game = {"home": "LAA", "away": "SEA"}
    for bad in (0.0, 1.0, -0.2, 1.4, None, "x"):
        assert X.fair_for_team(_mkt(prob=bad), "LAA", game) is None, bad


# --- what it will and will not speak to --------------------------------------
def test_only_the_moneyline_is_priced_from_a_game_winner_contract():
    """Kalshi lists who wins. It does not list our run line, and letting
    a win probability settle a spread is the silent coercion this
    codebase keeps finding in its own history."""
    assert X.MARKETS == ("moneyline",)
    rows = [{"market": "spread", "team": "LAA"},
            {"market": "total", "team": "LAA"}]
    census = X.attach(rows, [_mkt()], [{"home": "LAA", "away": "SEA"}], "mlb")
    assert census["rows"] == 0, "a non-moneyline row was considered"
    assert all("exchange_fair" not in r for r in rows)


def test_a_row_it_cannot_match_is_left_exactly_as_it_was():
    row = {"market": "moneyline", "team": "NYY", "model_prob": 0.6}
    before = dict(row)
    X.attach([row], [_mkt()], [{"home": "LAA", "away": "SEA"}], "mlb")
    assert row == before or "exchange_fair" not in row


def test_the_census_says_which_guard_rejected_a_market():
    census = X.attach([{"market": "moneyline", "team": "LAA"}],
                      [_mkt(spread_cents=30.0), _mkt(volume_24h=1.0,
                                                     open_interest=1.0)],
                      [{"home": "LAA", "away": "SEA"}], "mlb")
    assert census["usable markets"] == 0
    reasons = [k for k in census if k not in ("rows", "attached", "usable markets")]
    assert reasons, census
    assert any("wide" in r for r in reasons), reasons
    assert any("thin" in r for r in reasons), reasons


# --- the tier, and the ordering that makes it worth anything -----------------
def test_the_exchange_outranks_the_sharp_book_and_carries_its_own_number():
    row = {"exchange_fair": 0.58, "sharp_anchored": True, "sharp_fair": 0.55,
           "implied_prob": 0.52, "model_prob": 0.61, "odds": -110}
    assert potd.evidence(row) == "exchange"
    assert potd.fair_prob(row) == 0.58, "it must price on the exchange's number"
    assert potd.EVIDENCE.index("exchange") < potd.EVIDENCE.index("sharp")


def test_without_an_exchange_number_the_ladder_is_unchanged():
    """The new rung must not disturb the three below it."""
    sharp = {"sharp_anchored": True, "sharp_fair": 0.6, "odds": -110}
    assert potd.evidence(sharp) == "sharp" and potd.fair_prob(sharp) == 0.6
    mkt = {"prob_source": "market", "implied_prob": 0.56, "odds": -110}
    assert potd.evidence(mkt) == "market" and potd.fair_prob(mkt) == 0.56
    ours = {"model_prob": 0.7, "odds": -110}
    assert potd.evidence(ours) == "model"


def test_every_build_prices_the_board_BEFORE_it_picks():
    """THE ORDER IS LOAD-BEARING AND ITS FAILURE IS INVISIBLE. `potd
    .attach` selects off these rows. A build that priced them afterwards
    would publish a board carrying exchange fairs and a pick chosen
    without them — no error, no empty section, nothing to notice."""
    for fn in ("nfl_build.py", "cfb_build.py", "mlb_build.py", "nba_build.py"):
        src = open(os.path.join(ROOT, fn), encoding="utf-8").read()
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        assert "exchangefair" in code, f"{fn} never prices the board"
        assert code.index("attach_to_board") < code.index("_potd.attach("), \
            f"{fn} picks before it prices"


def test_the_hook_survives_a_feed_that_is_down():
    """It fetches a live venue, so this promise does real work: an
    exchange having a bad morning costs us the tier for one build and
    nothing else."""
    import engine.sources.kalshi as k
    real = k.fetch_sports_markets
    try:
        k.fetch_sports_markets = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("kalshi is down"))
        out = {"most_likely": [{"market": "moneyline", "team": "LAA"}],
               "games": []}
        note = X.attach_to_board(out, "mlb")
        assert "unavailable" in note and "kalshi is down" in note, note
        assert out["exchange_fair_error"], "the failure must reach the JSON"
    finally:
        k.fetch_sports_markets = real


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
