"""College football's games carry their moneylines, as the NFL's, the NBA's and hockey's do.

24 November 2026: every college football game page's market grid read "ML — / —". The build read each game's
moneylines and priced its game bets with them (`attach_odds`, `entry["moneyline"]`), and they went onto the line tape,
but never onto the board's game, so the page had none to show, and engine/lineopen, which keeps a game's opening and
closing lines only when both sides are priced, kept nothing for college football: no line moves, no "moved against the
money" note, no close for its game bets, and (since step ADT) no closing line on a finished game's page. The NBA's
board learned the same on 15 October ("THE MONEYLINES TOO").

Offline. Run directly: `python3 tests/test_college_football_games_carry_their_moneylines.py`
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import lineopen                                         # noqa: E402

NOW = 1_790_000_000


def test_the_board_writes_both_sides_price_on_the_game():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    loop = src[src.index('    for gd, g in zip(out["games"], games):\n        lines = priced.get(g["game_id"]) or {}'):]
    loop = loop[:loop.index("lines_at_kickoff(out[\"games\"])")]
    assert '_ml = lines.get("moneyline") or (None, None)' in loop
    assert 'gd["home_ml"], gd["away_ml"] = (_ml[0] or None), (_ml[1] or None)' in loop, \
        "the event's (home, away) pair, as attach_odds writes it; zero is no price"
    i = src.index("def attach_odds(")
    assert 'entry["moneyline"] = (mls[home], mls[away])' in src[i:i + 9000], "home first, away second"


def test_a_priced_college_game_keeps_its_open_and_its_close():
    c = sqlite3.connect(":memory:")
    g = {"home": "EMU", "away": "KENT", "date": "2026-11-24", "kickoff": "2099-11-25T00:00Z",
         "spread": -5.5, "total": 46.5, "home_ml": -205, "away_ml": 170}
    assert lineopen.priced(g)
    assert lineopen.record(c, "cfb", [g], NOW)["opened"] == 1
    assert c.execute("SELECT open_spread, open_home_ml, open_away_ml FROM line_opens").fetchone() == (-5.5, -205, 170)
    done = dict(g, home_ml=None, away_ml=None, live={"state": "final"})
    lineopen.attach(c, "cfb", [done], NOW + 86400)
    assert done["line_open"]["close"] == {"spread_home": -5.5, "total": 46.5, "home_ml": -205, "away_ml": 170}
    # Without the prices on the game, nothing was kept at all.
    bare = sqlite3.connect(":memory:")
    assert lineopen.record(bare, "cfb", [dict(g, home_ml=None, away_ml=None)], NOW)["opened"] == 0


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
