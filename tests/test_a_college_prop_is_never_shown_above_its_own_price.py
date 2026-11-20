"""A college prop is never shown above its own price (step ZX, 2026-11-20).

Ethan: "I really want the best picks and best game report picks and best most
likely picks ... for NBA and for college football." The NFL board already
shows the books' number where ours runs above it, read off three books at the
pick's line; college props rarely have three (pricetrust found a market chance
on 8 of 2,087 college picks), so college never joined. Every prop has its own
price, though, and a bet at it needs a known chance to break even. On the
public receipts, 26 September to 19 November (1,525 graded board props):

    shown above its own price    617   said 66.9%   hit 55.1%   the price said 57.1%
    shown at or under it         908   said 57.7%   hit 58.5%

Held to the price the board's log loss fell from 0.6992 to 0.6781, better in
eight of nine weeks, and each day's five likeliest props hit 66.9% against
61.1% ranked by our own number. engine/likelyboard.hold_to_own_price, behind
QB_PRICE_CEILING; the NBA's and the NHL's boards hit at or above their claims
and keep theirs.

    python3 tests/test_a_college_prop_is_never_shown_above_its_own_price.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likelyboard as LB                                  # noqa: E402
from engine.odds import american_to_prob                              # noqa: E402


class _Env:
    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _row(prob=0.70, odds=-140, **kw):
    return {"kind": "prop", "player": "Jeremiah Smith", "team": "OSU", "opponent": "MICH",
            "market": "receptions", "side": "OVER", "line": 5.5, "odds": odds, "book": "FanDuel",
            "has_market": True, "model_prob": prob, "implied_prob": round(american_to_prob(odds) / 1.045, 4),
            "sources": ["likely"], **kw}


def _result(rows):
    return {"games": [], "most_likely": rows, "matchup_picks": [], "td_scenarios": [], "recommendations": []}


def test_a_prop_above_its_price_shows_the_prices_number():
    r = _row(prob=0.70, odds=-140)
    with _Env(QB_PRICE_CEILING=None):
        assert LB.hold_to_own_price([r], "cfb") == 1
    price = american_to_prob(-140)
    assert abs(r["model_prob"] - round(price, 4)) < 1e-9, "the chance a bet at -140 needs, the books' cut left in"
    assert r["ceiling_from"] == r["trust_from"] == 0.70 and r["board_raw_prob"] == 0.70
    assert "we said 70%" in r["trust_note"] and "58%" in r["trust_note"], r["trust_note"]
    assert "break even" in r["trust_note"]


def test_a_prop_at_or_under_its_price_keeps_its_number():
    r = _row(prob=0.56, odds=-140)
    with _Env(QB_PRICE_CEILING=None):
        assert LB.hold_to_own_price([r], "cfb") == 0
    assert r["model_prob"] == 0.56 and "trust_note" not in r and "ceiling_from" not in r
    assert abs(r["price_ceiling"] - round(american_to_prob(-140), 4)) < 1e-9, "its ceiling is still on the row"


def test_only_college_football_and_only_while_switched_on():
    with _Env(QB_PRICE_CEILING=None):
        assert LB.price_ceiling_on("cfb") and not LB.price_ceiling_on("nba") and not LB.price_ceiling_on("nhl")
        assert not LB.price_ceiling_on("nfl"), "the NFL reads three books' fair price instead"
        for lg in ("nba", "nhl", "nfl", "mlb", "wnba", "cbb"):
            r = _row(prob=0.70)
            assert LB.hold_to_own_price([r], lg) == 0 and r["model_prob"] == 0.70, lg
    with _Env(QB_PRICE_CEILING="off"):
        r = _row(prob=0.70)
        assert LB.hold_to_own_price([r], "cfb", stats=(st := {})) == 0 and r["model_prob"] == 0.70
        assert st["on"] is False


def test_props_only_and_only_at_a_real_price():
    td = _row(prob=0.60, odds=120, market="anytime_td", side="YES", line=None)
    game = {"kind": "game", "market": "moneyline", "side": "OVER", "odds": -150, "model_prob": 0.75,
            "home": "OSU", "away": "MICH"}
    proxy = _row(prob=0.70, book="proxy")
    bare = _row(prob=0.70, has_market=False)
    none = dict(_row(prob=0.70), odds=None)
    with _Env(QB_PRICE_CEILING=None):
        assert LB.hold_to_own_price([td, game, proxy, bare, none], "cfb", stats=(st := {})) == 0
    assert td["model_prob"] == 0.60 and game["model_prob"] == 0.75
    assert proxy["model_prob"] == bare["model_prob"] == none["model_prob"] == 0.70
    assert st == {"on": True, "rows": 3, "priced": 0, "above": 0, "moved": 0, "posted": 0}, st


def test_a_pick_on_paper_keeps_our_own_claim():
    r = _row(prob=0.80, odds=-120, paper_hold="on paper, not posted: ...")
    with _Env(QB_PRICE_CEILING=None):
        assert LB.hold_to_own_price([r], "cfb") == 0
    assert r["model_prob"] == 0.80, "the paper record goes on measuring what we claimed"


def test_the_counts_say_what_the_ceiling_did():
    rows = [_row(prob=0.70, odds=-140), _row(prob=0.56, odds=-140, player="B"),
            _row(prob=0.66, odds=-110, player="C", locked=True, lock_note=None)]
    with _Env(QB_PRICE_CEILING=None):
        LB.hold_to_own_price(rows, "cfb", stats=(st := {}))
    assert st == {"on": True, "rows": 3, "priced": 3, "above": 2, "moved": 2, "posted": 1}, st


def test_the_board_ranks_checks_and_tiers_on_the_prices_number():
    # (15 points or more above the price is every league's standing paper hold; this is under it.)
    hot = _row(prob=0.70, odds=-150, player="A")         # the price says 60%
    cool = _row(prob=0.64, odds=-200, player="B")        # under its price (66.7%): keeps 64%
    with _Env(QB_PRICE_CEILING=None, QB_CFB_TIGHT=None):
        board = LB.build(_result([hot, cool]), sport="cfb", calibration={}, band_verdict=None)
    by = {r["player"]: r for r in board["rows"]}
    assert abs(by["A"]["model_prob"] - 0.60) < 1e-9 and by["B"]["model_prob"] == 0.64
    assert [r["player"] for r in board["rows"] if r["tier"] == by["A"]["tier"]][0] != "A" or by["B"]["tier"] != by["A"]["tier"], \
        "the pick we rated 70% no longer leads the one the price backs"
    assert board["price_ceiling"]["moved"] == 1 and board["price_ceiling"]["above"] == 1
    assert "we said 70%" in by["A"]["check_notes"]["model"], by["A"]["check_notes"]["model"]
    # Agreeing with the price it was set to is no second opinion: never a Top pick on it.
    assert by["A"]["checks"]["market"] is None and "second opinion" in by["A"]["check_notes"]["market"]
    assert by["A"]["tier"] != "top"
    assert by["B"]["checks"]["market"] is True, "a pick under its price is judged against it as before"


def test_other_leagues_boards_carry_no_ceiling_count():
    with _Env(QB_PRICE_CEILING=None):
        board = LB.build(_result([_row(prob=0.80, odds=-150)]), sport="nba", calibration={}, band_verdict=None)
    assert "price_ceiling" not in board
    assert board["rows"][0]["model_prob"] == 0.80 if board["rows"] else True


def test_under_even_at_its_price_a_prop_is_held_unless_the_matchup_backs_it():
    r = _row(prob=0.55, odds=120)                        # the price says 45.5%
    with _Env(QB_PRICE_CEILING=None, QB_CFB_TIGHT=None):
        board = LB.build(_result([r]), sport="cfb", calibration={}, band_verdict=None)
    assert not board["rows"] and len(board["held"]) == 1, "under 50% with no matchup read: held back, as the NFL's are"
    assert "under 50%" in board["held"][0]["held_note"], board["held"][0]["held_note"]


def test_a_posted_pick_takes_the_ceiling_when_the_list_hands_its_number_back():
    posted = _row(prob=0.72, odds=-140, locked=True, lock_note=None, first_prob=0.72)
    res = _result([posted])
    with _Env(QB_PRICE_CEILING=None, QB_CFB_TIGHT=None):
        res["likely_board"] = LB.build(res, sport="cfb", calibration={}, band_verdict=None)
        LB.harmonize(res)
    price = round(american_to_prob(-140), 4)
    row = (res["likely_board"]["rows"] or res["likely_board"]["held"])[0]
    assert abs(row["model_prob"] - price) < 1e-9
    assert abs(res["most_likely"][0]["model_prob"] - price) < 1e-9, "one bet, one chance: the list shows the board's"


def _quoted(rows, quotes):
    res = _result(rows)
    res["recommendations"] = [{"player": "Jeremiah Smith", "market": "receptions", "all_lines": quotes}]
    return res


OVER_ONLY = [{"book": "draftkings", "line": 5.5, "over_odds": -220, "under_odds": 0}]
BOTH = OVER_ONLY + [{"book": "fanduel", "line": 5.5, "over_odds": -215, "under_odds": 165}]


def test_a_price_with_one_side_quoted_is_no_second_opinion():
    # Step ZY: 136 college props whose best price was one book's heavy over hit 54.4%
    # where the price said 67.6%. At or under its price (-220 needs 68.8%), within the
    # market check's agreement — and no book quotes the under at 5.5.
    row = lambda: _row(prob=0.66, odds=-220, book="DraftKings")  # noqa: E731
    with _Env(QB_PRICE_CEILING=None, QB_CFB_TIGHT=None):
        lone = LB.build(_quoted([row()], OVER_ONLY), sport="cfb", calibration={}, band_verdict=None)
        both = LB.build(_quoted([row()], BOTH), sport="cfb", calibration={}, band_verdict=None)
        bare = LB.build(_result([row()]), sport="cfb", calibration={}, band_verdict=None)
        nba = LB.build(_quoted([row()], OVER_ONLY), sport="nba", calibration={}, band_verdict=None)
    r = lone["rows"][0]
    assert r["price_one_sided"] is True and r["checks"]["market"] is None, r["checks"]
    assert "no book quotes both sides" in r["check_notes"]["market"], r["check_notes"]["market"]
    assert r["model_prob"] == 0.66, "the pick stays, on our own number"
    assert lone["price_ceiling"]["one_sided"] == 1
    assert both["rows"][0]["checks"]["market"] is True and "price_one_sided" not in both["rows"][0], \
        "one book quoting both sides at the number is a market"
    assert both["price_ceiling"]["one_sided"] == 0
    assert bare["rows"][0]["checks"]["market"] is True, "no quote kept at the number: nothing to tell, as before"
    assert nba["rows"][0]["checks"]["market"] is True and "price_one_sided" not in nba["rows"][0], \
        "only the leagues the price ceiling holds"


def test_one_sided_reads_the_picks_own_number():
    q = LB.book_quotes(_quoted([], OVER_ONLY + [{"book": "fanduel", "line": 6.5, "over_odds": -110,
                                                 "under_odds": -110}]))
    assert LB.one_sided_price(_row(), q) is True, "the two-sided quote is at another number"
    assert LB.one_sided_price(dict(_row(), line=6.5), q) is False
    assert LB.one_sided_price(dict(_row(), line=7.5), q) is None
    assert LB.one_sided_price(dict(_row(), line=None), q) is None
    proxy = LB.book_quotes(_quoted([], [{"book": "proxy", "line": 5.5, "over_odds": -110, "under_odds": -110}]))
    assert LB.one_sided_price(_row(), proxy) is None, "the proxy is no book"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
