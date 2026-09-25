"""A bet on the Live tab opens as the bet placed — never another line of it.

Ethan, 2026-09-25, a screen recording from the Live tab: Bijan Robinson
OVER 3.5 receptions, placed −243, and his tap opened "UNDER 10.5
Receptions · Novig −19900" — "very unrealistic", and a different bet.

Two faults, one on each side of the tap:

* THE DOOR matched the board by player and market alone and opened the
  first row it found, whatever its side and line (`ridingDoorProp`). It
  now prefers the row at the bet's own number, and the page is drawn at
  the bet's side, line, price and book either way (`data-bet`,
  `betPickFor`).
* THE ROW EXISTED because the line shop takes the highest line for an
  under, and Novig — an exchange, which posts several numbers where a
  sportsbook posts one — hung 10.5, seven receptions above everybody's
  3.5. The shop now compares only lines near the market's own number
  (`odds.SHOP_WINDOW_ABS`).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import odds as O                                     # noqa: E402
from engine.livepicks import TRACKER_COLS                        # noqa: E402
from engine.models import SportsbookLine as L                    # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
LIVE = open(os.path.join(ROOT, "engine", "livepicks.py"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


# ── the shop ──────────────────────────────────────────────────────────────


def _bijan():
    return [L(book="DraftKings", line=3.5, over_odds=-130, under_odds=100),
            L(book="FanDuel", line=3.5, over_odds=-125, under_odds=-105),
            L(book="Novig", line=10.5, over_odds=5000, under_odds=-19900)]


def test_an_exchange_rung_far_from_the_market_is_not_shopped():
    under, over = O.best_under_line(_bijan()), O.best_over_line(_bijan())
    assert (under.line, under.book) == (3.5, "DraftKings"), under
    assert over.line == 3.5, over
    assert O.market_centre(_bijan()) == 3.5, "the centre is the line priced nearest even"


def test_a_ladder_cannot_drag_the_centre():
    ladder = [L(book="Novig", line=x, over_odds=o, under_odds=u) for x, o, u in
              [(2.5, -400, 300), (5.5, 350, -500), (7.5, 900, -1800), (10.5, 5000, -19900)]]
    got = O.best_under_line(_bijan() + ladder)
    assert got.line <= 4.5, got


def test_ordinary_shopping_is_untouched():
    field = [L(book="DraftKings", line=3.5, over_odds=-110, under_odds=-110),
             L(book="FanDuel", line=4.5, over_odds=120, under_odds=-150)]
    assert O.best_under_line(field).line == 4.5, "a whole reception is still a shop"
    assert O.best_over_line(field).line == 3.5
    yards = [L(book="DraftKings", line=60.5, over_odds=-110, under_odds=-110),
             L(book="FanDuel", line=66.5, over_odds=105, under_odds=-135)]
    assert O.best_under_line(yards).line == 66.5, "six yards on sixty is a shop"


def test_a_lone_quote_still_returns_a_line():
    one = [L(book="Novig", line=10.5, over_odds=5000, under_odds=-19900)]
    assert O.best_under_line(one).line == 10.5, "the fallback keeps the field, as every refusal here does"


# ── the Live row carries the bet ──────────────────────────────────────────


def test_the_live_row_carries_its_book_and_its_chance():
    assert "book" in [c.strip() for c in TRACKER_COLS.split(",")]
    assert LIVE.count('"book": b.get("book") or ""') == 2, "both row shapes, mapped and not"
    assert '"pregame_prob": b.get("hit_prob")' in LIVE


def test_the_door_carries_the_bet_and_every_path_passes_it_on():
    assert 'data-bet="${escapeAttr(ridingBet(b))}"' in _fn("ridingAttrs")
    assert APP.count('bet: card.dataset.bet }') == 2, "the click and the keyboard"
    # Tonight, every league: the bet and — for a Most Likely card — which
    # board it came from (2026-09-25 review).
    assert 'openProp(door.dataset.prop, { likely: door.dataset.likely === "1", bet: door.dataset.bet })' in APP
    assert "state.propBet = JSON.parse(opts.bet)" in _fn("openProp")
    page = _fn("renderPropPage")
    assert "const lk = state.propLikely ? (lkRow || likelyFor(r)) : betPickFor(r);" in page
    assert "!(lk && lk.bet)" in page, "no parlay button on a bet already placed"
    assert 'lk && lk.bet ? "" : shoppedLineNote(v)' in page


def test_the_door_prefers_the_bets_own_number():
    if not shutil.which("node"):
        return
    harness = ("const propOpenable=(r)=>true;\n"
               "let BOARD=[];const allProps=()=>BOARD;\n" + _fn("ridingDoorProp") + "\n}\n"
               "const a=JSON.parse(process.argv[2]);BOARD=a.board;"
               "process.stdout.write(JSON.stringify(ridingDoorProp(a.bet)));")
    path = os.path.join(tempfile.mkdtemp(), "d.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    under = {"player": "Bijan Robinson", "market": "receptions", "side": "UNDER", "line": 10.5}
    mine = {"player": "Bijan Robinson", "market": "receptions", "side": "OVER", "line": 3.5}
    bet = dict(mine, odds=-243)

    def door(board):
        out = subprocess.run(["node", path, json.dumps({"board": board, "bet": bet})],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr[-400:]
        return json.loads(out.stdout)
    assert door([under, mine]) == mine, "the row at his own number, not the first one"
    assert door([under]) == under, "any row of the stat for the chart — the page draws the bet"
    assert door([]) is None


if __name__ == "__main__":
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
