"""legcheck.py prices another analyst's legs with our own derivation.

Ethan, 2026-09-28, two Eagles-Bears research reports: "see how it aligns
with the site." The script reads the built board and, for each leg, gives
our chance at that exact number (likely._prob_at — the rung derivation),
our best price there, the board's own seat for the player and the read.
Read-only; offline here on a fake board.

Run directly: `python3 tests/test_legcheck_prices_their_legs.py`
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import legcheck                                                 # noqa: E402

BOARD = {
    "built_at": "2026-09-28T12:00:00",
    "qb_changes": [{"team": "CHI", "headline": "Caleb Williams (OUT) — Case Keenum starts", "note": "shown"}],
    "recommendations": [
        {"player": "Jalen Hurts", "team": "PHI", "market": "pass_yds", "side": "OVER", "line": 224.5, "odds": -110,
         "projection": 236.0, "proj_std": 55.0, "position": "QB",
         "alt_lines": [{"book": "DraftKings", "line": 199.5, "over_odds": -167, "under_odds": 130},
                       {"book": "FanDuel", "line": 199.5, "over_odds": -160, "under_odds": 125}]},
        {"player": "DeVonta Smith", "team": "PHI", "market": "receptions", "side": "OVER", "line": 5.5, "odds": -109,
         "projection": 5.9, "proj_std": 2.2, "position": "WR", "recent_values": [3, 10, 6, 5, 7, 4],
         "alt_lines": [{"book": "DraftKings", "line": 5.5, "over_odds": -109, "under_odds": -112}]},
    ],
    "longshot_watch": [{"player": "D'Andre Swift", "team": "CHI", "model_prob": 0.41, "odds": 110, "book": "FanDuel"}],
    "likely_board": {"rows": [{"player": "Jalen Hurts", "game": "PHI@CHI", "market": "pass_yds", "side": "OVER",
                               "line": 199.5, "odds": -160, "model_prob": 0.68, "tier": "strong"}]},
    "scan_reads": {"PHI@CHI": {"players": [
        {"player": "DeVonta Smith", "team": "PHI", "pos": "WR", "read": "good", "label": "Good matchup",
         "no_pick": {"refused": "under the 55% floor"}}]}},
}


def test_each_leg_gets_our_number_our_price_and_the_seat():
    lines = []
    got = legcheck.check(BOARD, [("Jalen Hurts", "pass_yds", "over", 199.5),
                                 ("DeVonta Smith", "receptions", "over", 5.5),
                                 ("Kalif Raymond", "receptions", "over", 2.5),
                                 ("D'Andre Swift", "anytime_td", "yes", 0.5)], out=lines.append)
    text = "\n".join(lines)
    h = got[0]
    assert h["prob"] is not None and 0.55 < h["prob"] < 0.85, h        # 236 ± 55 over 199.5
    assert h["best"] == (-160, "FanDuel"), "best bettable price at the rung, whatever the bars say"
    assert 0.55 < h["fair"] < 0.65 and "from the book's" in h["verdict"], "the credibility bar, named"
    assert "on Most Likely: OVER 199.5 pass_yds -160 · 68% · strong" in text
    assert got[1]["prob"] is not None and "read: Good matchup (good) · no pick: under the 55% floor" in text
    assert "Kalif Raymond" in text and "not on our board" in text
    assert got[3]["prob"] == 0.41 and "ours 41% at 110 FanDuel" in text


def test_the_default_legs_are_tonights_six_and_the_script_writes_nothing():
    assert len(legcheck.TONIGHT) == 6
    src = (ROOT / "legcheck.py").read_text(encoding="utf-8")
    assert "open(board_source(" in src, "the board is read through the gate's own source, not a path"
    assert '"w"' not in src and "write(" not in src


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
