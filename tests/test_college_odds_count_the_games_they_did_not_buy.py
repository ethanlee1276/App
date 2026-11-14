"""Tonight's games off college's props board are counted, never "dropped"
(2026-11-14).

College prices players for the few games a pull buys (nba_build.
college_board_games: five a pull), while the odds event list holds the
whole night. Saturday's noon board read "matched 2 props across 5 events
(cached); 54 event(s) DROPPED — see the odds diagnosis": every other game
on the night's slate landed in "mapped, but that pair is not on our slate",
the bucket kept for a wiring fault between our abbreviations and the
book's. The note sent the next check looking for a broken name join that
was not there. Those games are now counted apart (`off_board_events`); a
pair on no slate at all is still a drop, as before.

    python3 tests/test_college_odds_count_the_games_they_did_not_buy.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.models import (DefenseProfile, Game, GameLog, Prop,          # noqa: E402
                           SportsbookLine, Team, Weather, PASS_YDS)
from engine.data_loader import Slate                                     # noqa: E402
from engine.sources import oddsapi as oa                                 # noqa: E402


def _slate():
    teams = {t: Team(t, t, DefenseProfile(t)) for t in ("KC", "BUF")}
    game = Game(home="KC", away="BUF", weather=Weather(dome=False), spread=-2.5, total=47.0)
    logs = [GameLog(week=w, opponent="X", value=260) for w in range(1, 6)]
    prop = Prop(player="Josh Allen", team="BUF", opponent="KC", position="QB", market=PASS_YDS,
                logs=logs, career_avg=255, vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=250.0)], usage_role="starter")
    return Slate(date="2024-W05", teams=teams, games=[game], props=[prop])


EVENTS = [{"id": "e1", "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills"},
          {"id": "e2", "home_team": "Philadelphia Eagles", "away_team": "Dallas Cowboys"}]


def _run(night=None):
    was = oa.list_events, oa.fetch_event_odds
    oa.list_events = lambda key, ttl=300, sport="nfl", cache_only=False: list(EVENTS)
    oa.fetch_event_odds = (lambda eid, key, markets=None, books=None, ttl=300, sport="nfl",
                           cache_only=False: ({"bookmakers": []}, oa.Quota()))
    try:
        slate = _slate()
        if night is not None:
            slate.night_pairs = night
        return oa.apply_odds_to_slate(slate, api_key="k")
    finally:
        oa.list_events, oa.fetch_event_odds = was


def test_a_game_on_tonights_slate_but_off_the_props_board_is_counted_not_dropped():
    res = _run(night=[("KC", "BUF"), ("PHI", "DAL")])
    assert res.off_board_events == 1, res.off_board_events
    assert res.dropped_events == [], res.dropped_events


def test_without_the_nights_pairs_it_is_still_a_drop():
    res = _run()
    assert res.off_board_events == 0
    assert [d["reason"] for d in res.dropped_events] == ["mapped, but that pair is not on our slate"]


def test_college_hands_the_whole_night_and_the_note_says_it_plainly():
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert 'slate.night_pairs = [(g["home"], g["away"]) for g in all_games' in src
    i = src.index('odds_note = (f"matched {res.matched} props')
    block = src[i:i + 2600]
    assert "more game(s) tonight " in block and "not on the props board" in block
    assert block.index("res.dropped_events") < block.index("off_board_events"), "the drop note keeps its place"


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
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
