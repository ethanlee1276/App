"""A report's card backs one side of a game: one club across the moneyline and the spread, one side of the total
(step AEB).

24 November 2026: on How our reports did, five finished games' reports carried both sides of one spread, the
Vikings at the 49ers both "49ers −3" (won) and "Vikings +3.5" (lost), Eastern Michigan at Western Michigan both
sides of 14.5, and three more college games. Those came before a report's picks posted once (step ABQ, 22
November), when every version of a card was journaled; but nothing kept one card from holding both sides. Now it
cannot (engine/gamereport._card_rows, `game_side`): the first in the card's order, which is best first, stands.

Offline. Run directly: `python3 tests/test_a_report_card_backs_one_side_of_a_game.py`
"""
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as R                                   # noqa: E402


def _game(label, market, team, side="", line=None, p=0.6):
    return {"kind": "game", "player": label, "team": team, "market": market, "bet_type": market, "side": side,
            "line": line, "model_prob": p, "tier": "strong", "game": "MIN@SF", "home": "SF", "away": "MIN"}


def _prop(player, p=0.62):
    return {"player": player, "team": "SF", "market": "rush_yds", "side": "over", "line": 70.5, "model_prob": p,
            "tier": "strong", "game": "MIN@SF", "home": "SF", "away": "MIN"}


def _card(rows, monkey=True):
    c = types.SimpleNamespace(featured=False, sport="nfl", home="SF", away="MIN", result={})
    was = R._card_pool
    R._card_pool = lambda _c, key="rows": list(rows)
    try:
        return [r["player"] for r in R._card_rows(c)]
    finally:
        R._card_pool = was


def test_the_card_backs_one_club_across_the_moneyline_and_the_spread():
    rows = [_game("SF ML", "moneyline", "SF", "over", 0.5, 0.66), _game("SF -3", "spread", "SF", "home", -3.0, 0.58),
            _game("MIN +3.5", "spread", "MIN", "away", 3.5, 0.55), _prop("Christian McCaffrey")]
    assert _card(rows) == ["SF ML", "SF -3", "Christian McCaffrey"], "the 49ers twice, the Vikings never"
    # Best first decides: a card whose first game pick backs the Vikings takes no 49ers line.
    assert _card([rows[2], rows[0], rows[1], rows[3]]) == ["MIN +3.5", "Christian McCaffrey"]


def test_one_side_of_the_total_and_of_each_team_total():
    rows = [_game("Over 44.5", "total", "SF", "Over", 44.5), _game("Under 45.5", "total", "SF", "Under", 45.5),
            _game("SF Over 24.5", "team_total", "SF", "Over", 24.5),
            _game("MIN Under 20.5", "team_total", "MIN", "Under", 20.5),
            _game("SF Under 25.5", "team_total", "SF", "Under", 25.5)]
    assert _card(rows) == ["Over 44.5", "SF Over 24.5", "MIN Under 20.5"], \
        "a club's own number one way, the other club's free to go its own"


def test_what_a_game_row_bets_on():
    assert R.game_side(_game("SF ML", "moneyline", "SF")) == ("club", "SF")
    assert R.game_side(_game("SF -3", "spread", "SF", "home", -3.0)) == ("club", "SF")
    assert R.game_side(_game("Over 44.5", "total", "SF", "Over", 44.5)) == ("total", "over")
    assert R.game_side(_game("SF o24.5", "team_total", "SF", "o", 24.5)) == ("team_total|SF", "over")
    assert R.game_side(_prop("Brock Purdy")) is None, "a player's pick is no side of the game"
    assert R.game_side(_game("?", "spread", "")) is None and R.game_side(None) is None


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
