"""A prop a book prices better than the sharp book's fair is said and listed
(engine/sharpvalue; 2026-10-29, after Ethan's "think like a pro sports
better ... use the data and resources we have" and "Ok keep going").

From today the NBA and NHL boards read the sharp book's two-way price as
their market. The same pair answers a pro's first question of a screen:
is any book I can bet paying more than the sharp book's fair? No model is
in that number. What these hold:

  * both sides are read, at the same number only, at books a reader can
    bet (never the sharp book itself, never a placeholder), the best price
    each side; the game cards' bands decide (2% to 15%, a warning past 7%);
  * a basketball or hockey row that read the sharp book at its own number
    carries `sharp_value` and says it in a line; one read across from
    another number, or priced off the other books, carries nothing;
  * the Market Scanner's Sharp money section lists those props, and the
    Scanner, now in js/more.js, is fetched when its page opens, not on
    every first visit.

Run directly: `python3 tests/test_a_book_beating_the_sharp_price_is_listed.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import hoops                                                    # noqa: E402
from engine.models import SportsbookLine as L                               # noqa: E402
from engine.nba import pipeline as P                                        # noqa: E402
from engine.odds import american_to_decimal, devig_two_way                  # noqa: E402
from engine.sharpvalue import note, sharp_value                             # noqa: E402

STEADY = [30, 31, 29, 32, 30, 31, 30, 29, 31, 30]


def _q(book, line, over, under):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def test_the_better_side_at_a_bettable_book_inside_the_bands():
    fair_over = 0.50
    quotes = [_q("DraftKings", 22.5, -110, -110), _q("FanDuel", 22.5, 105, -125),
              _q("Pinnacle", 22.5, 130, -150), _q("proxy", 22.5, 150, -110),
              _q("BetMGM", 23.5, 140, -170)]
    v = sharp_value(fair_over, quotes, 22.5)
    assert v["side"] == "OVER" and v["book"] == "FanDuel" and v["odds"] == 105, v
    assert abs(v["ev"] - round(0.5 * american_to_decimal(105) - 1, 4)) < 1e-9 and not v["suspect"], v
    # The under side, when it is the one past the fair; past 7% it carries
    # its warning.
    v = sharp_value(0.45, [_q("DraftKings", 22.5, -110, 105)], 22.5)
    assert v["side"] == "UNDER" and abs(v["ev"] - round(0.55 * 2.05 - 1, 4)) < 1e-9 and v["suspect"], v


def test_nothing_under_two_points_or_past_fifteen():
    assert sharp_value(0.50, [_q("DraftKings", 22.5, -105, -115)], 22.5) is None, "-2.4% and -6.5%: no value"
    assert sharp_value(0.50, [_q("DraftKings", 22.5, 101, -125)], 22.5) is None, "+0.5%: noise"
    assert sharp_value(0.50, [_q("DraftKings", 22.5, 140, -170)], 22.5) is None, "+20%: a broken price"
    assert sharp_value(0.50, [], 22.5) is None and sharp_value(None, [], 22.5) is None
    assert sharp_value(1.0, [_q("DraftKings", 22.5, 105, -125)], 22.5) is None


def test_the_line_on_the_card():
    v = {"side": "OVER", "odds": 105, "book": "FanDuel", "fair": 0.512, "ev": 0.0496, "suspect": False}
    assert note(v, "Pinnacle") == ("Beats Pinnacle: FanDuel +105 on the over pays more than Pinnacle's fair "
                                   "(51%), +5.0% EV on the price alone")
    assert "check the number still stands" in note(dict(v, suspect=True), "Pinnacle")


def _nba(sharp_lines, lines):
    prop = {"player": "A Guard", "team": "BOS", "opponent": "NYK", "market": "pts", "line": 19.5,
            "over_odds": -110, "under_odds": -110, "book": "DraftKings", "spread": -3.0, "is_starter": True,
            "minutes": list(STEADY), "values": [round(m * 0.65, 1) for m in STEADY], "sharp_lines": sharp_lines}
    return P.shared_recommendations([prop], {("A Guard", "pts"): lines}, {}, tune=hoops.NBA)[0]


def test_an_nba_row_that_read_the_sharp_book_at_its_number_carries_it():
    lines = [_q("DraftKings", 19.5, -110, -110), _q("FanDuel", 19.5, 108, -130)]
    row = _nba([_q("Pinnacle", 19.5, -115, -105)], lines)
    fo = devig_two_way(-115, -105)[0]
    v = row["sharp_value"]
    assert v and v["side"] == "OVER" and v["book"] == "FanDuel" and v["odds"] == 108, v
    assert abs(v["fair"] - round(fo, 4)) < 1e-3, (v, fo)
    assert any(r.startswith("Beats Pinnacle: FanDuel +108 on the over") for r in row["reasons"]), row["reasons"]
    across = _nba([_q("Pinnacle", 20.5, -115, -105)], lines)
    assert across["market_source"] == "sharp" and across["sharp_value"] is None, "read across: no market-only claim"
    plain = _nba([], lines)
    assert plain["sharp_value"] is None and not any(r.startswith("Beats ") for r in plain["reasons"])


def test_an_nhl_row_carries_it_too():
    sys.path.insert(0, str(ROOT / "tests"))
    import nhl_build as B
    import test_nhl_board_builds as T

    def odds(slate):
        note_ = T._odds(slate)
        for pr in slate.props:
            if pr.player == "Connor McDavid" and pr.market == "sog":
                pr.lines = [L("DraftKings", 3.5, -120, -105), L("FanDuel", 3.5, 115, -140)]
                pr.sharp_lines = [L("Pinnacle", 3.5, -105, -115)]
        return note_
    out, _ = B.build("2025-10-30", T.TONIGHT, T._history(), attach_odds=odds, injuries={}, starters={}, lines={})
    row = next(r for r in out["recommendations"] if r["player"] == "Connor McDavid" and r["market"] == "sog")
    v = row["sharp_value"]
    assert v and v["book"] == "FanDuel" and v["side"] == "OVER" and v["odds"] == 115, v
    assert any(r.startswith("Beats Pinnacle: FanDuel +115") for r in row["reasons"]), row["reasons"]


def test_the_scanner_lists_them_and_waits_for_its_page():
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    more = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
    assert 'function renderScanner(...a) { return roomCall(renderScanner, "renderScanner", "js/more.js"' in app
    assert '["scanner-body", () => renderScanner(), true],' in app, "drawn when opened, never in the background"
    assert 'if (name === "scanner") renderScanner();' in app
    body = more[more.index("function renderScanner("):]
    body = body[:body.index("\n}\n")]
    assert "if (r.sharp_value) return { r, v: r.sharp_value };" in body
    assert "pays more than the sharp book’s fair" in body and "!sharpProps.length" in body


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
