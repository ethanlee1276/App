"""The NHL board meets the market on every line, and reads the sharp book
first (nhl_build.rung_probs, nhl_build._sharp_pair; 2026-10-29, the NBA
board's two fixes the same day, after Ethan's "think like a pro sports
better ... use the data and resources we have").

The same two gaps the NBA board had. A ladder rung quoted one way only
carried our raw number, while a two-way rung beside it was shrunk toward
its price, on a board that ranks by chance. And the build pulled the sharp
book's quotes in the same odds call and never read them, so the haircut
leaned on the other books' best two prices. What these hold:

  * a one-way rung is shrunk toward the main line's market read at the rung
    through our own curve (`_implied_mean`), the way a two-way rung is
    shrunk toward its own price; with no main price, the raw number;
  * a number some book quotes both ways reads that quote; the sharp book's
    two-way quote at a number comes before every other book's there;
  * on the main line, the sharp book's two-way quote at the same number is
    the market the side, the haircut and the edge are read against, while
    the price taken stays the shop's, and the card says so; a sharp quote
    at another number is not read across.

Run directly: `python3 tests/test_the_nhl_board_meets_the_market_on_every_line.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nhl_build as B                                          # noqa: E402
from engine.betting import temper_edge                         # noqa: E402
from engine.models import SportsbookLine as L                  # noqa: E402
from engine.odds import devig_two_way                          # noqa: E402

SOG = {"mean": 3.0, "disp": 1.3}
SAVES = {"mean": 26.0, "sd": 5.0}


def test_the_main_price_reads_back_as_a_mean_on_our_own_curve():
    for proj, market, line, q in ((SOG, "sog", 2.5, 0.55), (SOG, "sog", 3.5, 0.40),
                                  (SAVES, "saves", 25.5, 0.52), ({"mean": 0.6, "disp": 1.1}, "points", 0.5, 0.45)):
        m = B._implied_mean(proj, market, line, q)
        assert m is not None, (market, line, q)
        assert abs(B._p_over(dict(proj, mean=m), market, line) - q) < 1e-4, (market, line, q, m)
    assert B._implied_mean(SOG, "sog", 2.5, 0.995) is None


def test_a_one_way_rung_is_shrunk_toward_the_main_lines_market():
    mean = B._implied_mean(SOG, "sog", 2.5, 0.60)
    got = B.rung_probs(SOG, "sog", [L("DraftKings", 1.5, -400, 0)], main_line=2.5, main_over=0.60)
    raw = B._p_over(SOG, "sog", 1.5)
    mkt = B._p_over(dict(SOG, mean=mean), "sog", 1.5)
    want = temper_edge(raw, mkt, "DraftKings")[0]
    assert abs(got["1.5"] - round(want, 4)) < 1e-9, (got, want)
    assert min(raw, mkt) < got["1.5"] < max(raw, mkt), "between our number and the market's"
    assert B.rung_probs(SOG, "sog", [L("DraftKings", 1.5, -400, 0)])["1.5"] == round(raw, 4), \
        "with no main price, the raw number, as before"


def test_a_two_way_quote_anywhere_and_the_sharp_book_first():
    two = [L("DraftKings", 1.5, -400, 0), L("FanDuel", 1.5, -380, 290)]
    got = B.rung_probs(SOG, "sog", two, main_line=2.5, main_over=0.60)
    want = temper_edge(B._p_over(SOG, "sog", 1.5), devig_two_way(-380, 290)[0], "FanDuel")[0]
    assert abs(got["1.5"] - round(want, 4)) < 1e-9, (got, want)
    sharp = B.rung_probs(SOG, "sog", two[1:], sharp_alts=[L("Pinnacle", 1.5, -330, 260)])
    want = temper_edge(B._p_over(SOG, "sog", 1.5), devig_two_way(-330, 260)[0], "FanDuel")[0]
    assert abs(sharp["1.5"] - round(want, 4)) < 1e-9, (sharp, want)
    assert B.rung_probs(SOG, "sog", two[1:], sharp_alts=[L("Pinnacle", 2.5, -330, 260)]) == \
        B.rung_probs(SOG, "sog", two[1:]), "a sharp quote at another number prices nothing here"


def test_the_sharp_pair_is_the_same_number_and_a_real_market():
    assert B._sharp_pair([L("Pinnacle", 3.5, -118, -102)], 3.5) == (-118, -102, "Pinnacle")
    for bad in ([L("Pinnacle", 2.5, -118, -102)],              # another number
                [L("Pinnacle", 3.5, -118, 0)],                 # one side
                [L("Pinnacle", 3.5, -160, -160)],              # holding past the bar
                [L("Pinnacle", 3.5, 120, 110)], [], None):     # holding less than nothing
        assert B._sharp_pair(bad, 3.5) is None, bad


def _board(sharp=None):
    import test_nhl_board_builds as T

    def odds(slate):
        note = T._odds(slate)
        for pr in slate.props:
            if pr.player == "Connor McDavid" and pr.market == "sog":
                pr.sharp_lines = list(sharp or [])
        return note
    conn = T._history()
    out, _slate = B.build("2025-10-30", T.TONIGHT, conn, attach_odds=odds, injuries={}, starters={}, lines={})
    return {(r["player"], r["market"]): r for r in out["recommendations"]}


def test_the_card_reads_the_sharp_book_and_shops_the_others():
    sys.path.insert(0, str(ROOT / "tests"))
    plain = _board()[("Connor McDavid", "sog")]
    assert plain["market_source"] == "books" and not any("vig out" in x for x in plain["reasons"])
    sharp = _board([L("Pinnacle", 3.5, -140, 118)])[("Connor McDavid", "sog")]
    fo, fu = devig_two_way(-140, 118)
    assert sharp["market_source"] == "sharp", sharp
    assert abs(sharp["fair_prob"] - round(fo if sharp["side"] == "OVER" else fu, 4)) < 1e-9, sharp["fair_prob"]
    assert sharp["book"] in ("DraftKings", "FanDuel"), "the price taken is still the shop's"
    assert any("Pinnacle's price, vig out" in x for x in sharp["reasons"]), sharp["reasons"]
    bo, bu = devig_two_way(-120, 100)              # the shop: DraftKings' over, FanDuel's under
    assert abs(sharp["books_fair"] - round(bo if sharp["side"] == "OVER" else bu, 4)) < 1e-9, sharp["books_fair"]
    away = _board([L("Pinnacle", 2.5, -300, 240)])[("Connor McDavid", "sog")]
    assert away["market_source"] == "books", "a sharp quote at another number is not read across"


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tests"))
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
