"""An exchange's touchdown price is shown only when a sportsbook is close.

Ethan, 2026-09-26, on Novig pricing four of the eight touchdown scenarios:
"if the Novig prices are almost the same as the sports book prices, then
it does not matter." So `odds.prefer_sportsbook` keeps the exchange's
price when the best sportsbook is within EXCHANGE_NEAR_PROB (1.5 points of
implied chance) and otherwise shows the sportsbook — on the touchdown
board the scenarios, the Most Likely shelf and the value picks all read.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import odds as O                                      # noqa: E402
from engine.models import SportsbookLine                          # noqa: E402


def _ln(book, over, under=None):
    return SportsbookLine(book=book, line=0.5, over_odds=over, under_odds=under)


def test_close_keeps_the_exchange_far_shows_the_sportsbook():
    assert O.EXCHANGE_NEAR_PROB == 0.015
    close = O.prefer_sportsbook([_ln("Novig", -108), _ln("DraftKings", -110)])
    assert close.book == "Novig", "51.9% against 52.4% is almost the same"
    far = O.prefer_sportsbook([_ln("Novig", -108), _ln("DraftKings", -125), _ln("FanDuel", -120)])
    assert far.book == "FanDuel" and far.over_odds == -120, "54.5% against 51.9% is not"
    long_far = O.prefer_sportsbook([_ln("Novig", 400), _ln("BetMGM", 350)])
    assert long_far.book == "BetMGM"
    assert O.prefer_sportsbook([_ln("Novig", 113)]).book == "Novig", "an exchange alone still prices"
    assert O.prefer_sportsbook([_ln("BetMGM", 105), _ln("Novig", 100)]).book == "BetMGM"
    assert O.prefer_sportsbook([]) is None


def test_the_touchdown_board_uses_it():
    from engine.models import ANYTIME_TD, Team, DefenseProfile, Prop, Game, GameLog, Weather
    from engine.data_loader import Slate
    from engine.pipeline import _long_shots
    teams = {"CIN": Team("CIN", "CIN", DefenseProfile("CIN")),
             "PIT": Team("PIT", "PIT", DefenseProfile("PIT"))}
    game = Game(home="CIN", away="PIT", weather=Weather(), date="2026-09-27",
                kickoff="2026-09-27T17:00:00Z", total=44.0, spread=-3.0)

    def prop(name, lines):
        return Prop(player=name, team="CIN", opponent="PIT", position="RB", market=ANYTIME_TD,
                    logs=[GameLog(week=w, opponent="X", value=1) for w in range(1, 6)],
                    career_avg=0.6, vs_opponent_avg=None, lines=lines)
    slate = Slate(date="2026-09-27", teams=teams, games=[game], props=[
        prop("Far Back", [_ln("Novig", -102), _ln("DraftKings", -125), _ln("FanDuel", -120)]),
        prop("Close Back", [_ln("Novig", -102), _ln("DraftKings", -105)])])
    picks, watch = _long_shots(slate)
    got = {r["player"]: (r["book"], int(r["odds"])) for r in list(picks) + list(watch)}
    assert got.get("Far Back") == ("FanDuel", -120), got
    assert got.get("Close Back") == ("Novig", -102), got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
