"""Opening lines are kept, and a game says how far its market moved.

Ethan, 2026-09-28, on what the site was missing: the board could never say
"PHI opened -4.5, now -3.5" because every pull overwrote the numbers.
engine/lineopen writes a game's first real book price once, updates the
"now" columns every build, stamps `line_open` with the moves, and — with
the money split on the game — says when the spread moved against the
money. Offline, on a temporary database.

Run directly: `python3 tests/test_opening_lines_are_kept.py`
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import lineopen as L                               # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
NOW = 1_790_400_000.0                                            # 2026-09-25, a Friday
G = {"away": "PHI", "home": "CHI", "date": "2026-09-28", "kickoff": "20:15",
     "spread": 4.5, "favorite": "PHI", "total": 46.5, "home_ml": 180, "away_ml": -215}


def _conn():
    return sqlite3.connect(":memory:")


def test_the_first_price_is_written_once_and_now_moves():
    c = _conn()
    g = dict(G)
    assert L.record(c, "nfl", [g], NOW) == {"games": 1, "opened": 1, "updated": 0}
    g2 = dict(G, spread=3.5, total=41.5, home_ml=165, away_ml=-195)
    assert L.record(c, "nfl", [g2], NOW + 3600) == {"games": 1, "opened": 0, "updated": 1}
    row = c.execute("SELECT open_spread, open_total, open_home_ml, now_spread, now_total FROM line_opens").fetchone()
    assert row == (4.5, 46.5, 180, 3.5, 41.5), row          # the home club's number: CHI +4.5 → +3.5
    assert L.attach(c, "nfl", [g2], NOW + 3600) == 1
    lo = g2["line_open"]
    assert lo["spread_home"] == 4.5 and lo["total"] == 46.5 and lo["home_ml"] == 180
    assert lo["spread_move"] == -1.0 and lo["total_move"] == -5.0
    assert "against_money" not in lo, "no money split on the game: no note"


def test_a_proxy_line_or_a_started_game_never_opens_a_row():
    c = _conn()
    assert L.record(c, "nfl", [dict(G, home_ml=0, away_ml=0)], NOW)["games"] == 0, "no moneyline: a proxy"
    assert L.record(c, "nfl", [dict(G, live={"state": "live"})], NOW)["games"] == 0
    assert c.execute("SELECT COUNT(*) FROM line_opens").fetchone()[0] == 0


def test_the_spread_moving_against_the_money_is_said():
    # CHI +4.5 → +3.5 is a move TOWARD Chicago; 78% of the money on PHI.
    g = dict(G, spread=3.5, money={"spread": {"home": 0.22, "away": 0.78}})
    got = L.against_money(g, 4.5, 3.5)
    assert got == {"toward": "home", "money_on": "away", "money_share": 0.78, "delta": -1.0}, got
    # …and a move WITH the money, a small move, or a split market says nothing.
    assert L.against_money(dict(G, money={"spread": {"home": 0.78, "away": 0.22}}), 4.5, 3.5) is None
    assert L.against_money(g, 4.0, 3.6) is None
    assert L.against_money(dict(G, money={"ml": {"home": 0.5, "away": 0.5}}), 4.5, 3.5) is None
    # the moneyline split stands in when the spread market has none
    assert L.against_money(dict(G, money={"ml": {"home": 0.3, "away": 0.7}}), 4.5, 3.5)["money_on"] == "away"


def test_the_hook_never_raises_and_the_builds_call_it_after_the_crowd():
    c = _conn()
    line = L.attach_to_board({"games": [dict(G)]}, "nfl", conn=c, now=NOW)
    assert "1 opened" in line and "1 on the board" in line, line
    assert "opening lines" in L.attach_to_board({"games": "not a list"}, "nfl", conn=c, now=NOW)
    for f in ("nfl_build.py", "cfb_build.py", "mlb_build.py", "nba_build.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert src.index("_crowd.attach_to_board(") < src.index("_lo.attach_to_board("), f


def test_the_game_page_draws_it_and_the_home_card_does_not():
    assert "${o.open && !L ? lineOpenHTML(g, spTxt) : \"\"}" in APP
    assert "gameMarketsHTML(g, { mlb, isFinal, open: true })" in APP, "the game page asks for it"
    i = APP.index("function gameCard(g)")
    assert "open: true" not in APP[i:i + 600], "the Home card stays the three columns"
    fn = APP[APP.index("function lineOpenHTML("):]
    fn = fn[:fn.index("\nfunction ")]
    for bit in ("<b>Opened</b>", "since then", "unchanged", "the books moved against the money"):
        assert bit in fn, bit


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
