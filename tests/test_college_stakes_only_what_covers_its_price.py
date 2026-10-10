"""A college Most Likely pick is staked only when our chance covers its price.

Ethan, 2026-10-09, choosing "stake only when we cover the price" after the
college loss audit: the staked college picks claimed 63% and hit 63% — an
honest number — at prices that needed 65%, so the book lost by construction
(127-76, -4.1%). The board ranks on how likely a pick is, never on price.

These check, one rule each: a college pick whose chance is below its
price's break-even goes to the paper book (still journaled, still graded,
no money) and is marked for the card; one that covers is staked as before;
the NFL is untouched; the card says why.

Run directly: `python3 tests/test_college_stakes_only_what_covers_its_price.py`
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger                                          # noqa: E402

_SEQ = [0]


def _conn():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    return conn


def _row(prob, odds, sport_tag):
    _SEQ[0] += 1
    return {"player": f"{sport_tag} Back {_SEQ[0]}", "market": "rush_yds", "side": "OVER", "line": 60.5,
            "odds": odds, "book": "fanduel", "model_prob": prob, "implied_prob": None,
            "game_date": "2026-10-10"}


def _journal(conn, sport, rows):
    ledger.log_most_likely(conn, {"sport": sport, "date": "2026-10-10", "most_likely": rows})
    return {r["player"]: (r["category"], r["stake_units"], r["stake_dollars"]) for r in conn.execute(
        "SELECT player, category, stake_units, stake_dollars FROM bets").fetchall()}


def test_college_stakes_a_pick_that_covers_its_price_and_papers_one_that_does_not():
    assert ledger.likely_is_staked("cfb"), "this rule is about college's STAKED book"
    c = _conn()
    covers = _row(0.72, -200, "CFB")        # -200 needs 66.7%: 72% covers it
    short = _row(0.63, -200, "CFB")         # 63% does not
    got = _journal(c, "cfb", [covers, short])
    assert got[covers["player"]][0] == ledger.LIKELY_LIVE_CATEGORY and got[covers["player"]][2] > 0
    cat, units, dollars = got[short["player"]]
    assert cat == "likely" and dollars == 0.0 and units > 0, \
        "a pick below its price is journaled on paper — graded, no money on it"
    assert short["price_short"] is True and covers["price_short"] is False, "the card must be told"


def test_exactly_break_even_counts_as_covering():
    assert ledger.covers_price(0.5, 100) is True
    assert ledger.covers_price(0.6667, -200) is True
    assert ledger.covers_price(0.66, -200) is False
    assert ledger.covers_price(None, -200) is None and ledger.covers_price(0.6, None) is None


def test_the_nfl_is_untouched():
    assert "nfl" not in ledger.PRICE_COVER_SPORTS
    c = _conn()
    short = _row(0.63, -200, "NFL")
    got = _journal(c, "nfl", [short])
    assert got[short["player"]][0] == ledger.LIKELY_LIVE_CATEGORY, "the NFL stakes as it always has"
    assert "price_short" not in short


def test_the_card_says_why():
    src = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = src.index("function likelyTagsHTML(r)")
    body = src[i:src.index("\nfunction ", i + 10)]
    assert "r.price_short" in body and "Price too high to stake" in body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
