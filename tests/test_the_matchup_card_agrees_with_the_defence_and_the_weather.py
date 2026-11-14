"""A player's matchup card says what the matchup says: the defence, the
points the lines expect, a teammate out and the forecast, never his own
share of the work (engine/gamescan._label, weather_line).

Ethan, 12 November 2026, the Commanders at the Giants, rain 74% likely:
the short version said the Giants' run defense ranks 30th, "so there is
room to run for the Commanders", and the card under it read "Rachaad
White vs NYG's run defense — UNFAVORABLE". "That doesn't make any sense
... it's supposed to rain this game as well. So we're marking running
backs as unfavorable, but it's going to be raining." The one reason
against him was his own share, "only 28% of the carries so far", which
the card hides because its role line already says it, and the read
counted none of the weather the board had priced him with. What these
hold:

  * a small share is said (``role``, first among the notes) and never a
    reason against him; a big one never a reason for him, though it still
    decides a breakout;
  * the measured weather step on his headline market counts: in rain a
    back's carries go up and a receiver's yards come down, as the board
    prices them;
  * a lean that rests on the weather alone points only at what the weather
    moves: rain backs a back's carries, never his rushing yards;
  * a forecast the board carries as a dict reads the same as the slate's
    own, and a dome or an unpulled forecast counts nothing.

Run directly: `python3 tests/test_the_matchup_card_agrees_with_the_defence_and_the_weather.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamescan as G                                     # noqa: E402
from engine.models import Weather                                    # noqa: E402

#: The night Ethan sent: kickoff 8:15pm at MetLife, 52°F, wind 12 mph,
#: rain 74% likely (the board's own forecast for WAS @ NYG).
RAIN = Weather(dome=False, temp_f=52.0, wind_mph=12.0, wind_dir="NE", rain=True,
               precip_chance=0.74, measured=True, forecast=True)
DRY = Weather(dome=False, temp_f=58.0, wind_mph=3.0, measured=True, forecast=True)

#: No rank the model counts either way: the Giants sit mid-table in what
#: they give up to backs, so nothing measured leans the matchup.
ALLOWED = {"rb_rush_yds": {"rank": 14, "of": 32, "pg": 88.0},
           "rb_rush_td": {"rank": 15, "of": 32, "pg": 0.7}}
NYG = {"WAS": {"off": {"rushing": {"rank": 19}}}, "NYG": {"def": {"rushing": {"rank": 30}}}}


def _white(weather, allowed=ALLOWED, share=0.28):
    return G.player_read("Rachaad White", "WAS", "NYG", "RB",
                         usage={"carry_share": share, "carries_pg": 7.7, "targets_pg": 2.6, "games": 7},
                         ratings=NYG, room={}, scheme={}, split={}, tackling={}, line_out=[],
                         mates_out=[], allowed=allowed, points=20.0, weather=weather)


def test_a_small_share_is_said_and_never_a_reason_against_him():
    dry = _white(DRY)
    assert dry["read"] == "neutral", dry
    assert dry["con"] == [] and dry["pro"] == []
    assert dry["role"] == ["Only 28% of the carries so far"]
    assert dry["notes"][0] == "Only 28% of the carries so far", "said first, with the uncounted"
    # A big share is said the same way, never a reason for him: he is what
    # he is, and the line is set on it.
    lead = _white(DRY, share=0.62)
    assert lead["read"] == "neutral" and lead["pro"] == [], lead
    assert lead["role"] == ["Takes 62% of the carries (7.7 a game)"]


def test_rain_counts_for_a_back_the_way_the_board_priced_him():
    wet = _white(RAIN)
    assert wet["read"] == "good", wet
    assert len(wet["pro"]) == 1 and wet["con"] == []
    line = wet["pro"][0]
    assert line == ("Rain is 74% likely at kickoff: teams run more in rain and a back keeps his "
                    "share, about 5% more carries (measured, 2016-2025)"), line
    # The card's verdict is the read's: FAVORABLE, not UNFAVORABLE.
    from engine.gamereport import VERDICT
    assert VERDICT[wet["read"]][0] == "favorable"


def test_a_lean_on_the_weather_alone_backs_his_carries_not_his_yards():
    wet = _white(RAIN)
    assert wet["lean"] == ["rush_att"], wet["lean"]
    leans = G.leans_from_reads({"WAS@NYG": {"players": [wet]}})
    assert set(leans) == {("Rachaad White", "WAS", "rush_att")}, leans
    assert leans[("Rachaad White", "WAS", "rush_att")]["side"] == "over"
    # With the defence leaning too, the read points at what both back.
    soft = dict(ALLOWED, rb_rush_yds={"rank": 3, "of": 32, "pg": 128.0})
    both = _white(RAIN, allowed=soft)
    assert both["read"] == "good" and len(both["pro"]) == 2, both
    assert "rush_yds" in both["lean"] and "rush_att" in both["lean"]


def test_rain_counts_against_a_receiver():
    diggs = G.player_read("Stefon Diggs", "WAS", "NYG", "WR",
                          usage={"tgt_share": 0.22, "targets_pg": 6.6, "games": 7},
                          ratings=NYG, room={}, scheme={}, split={}, tackling={}, line_out=[],
                          mates_out=[], allowed={"wr_rec_yds": {"rank": 16, "of": 32, "pg": 140.0}},
                          points=20.0, weather=RAIN)
    assert diggs["read"] == "tough", diggs
    (line,) = diggs["con"]
    assert line == ("Rain is 74% likely at kickoff and the wind is forecast at 12 mph: about 15% "
                    "off a receiver's yards (measured, 2016-2025)"), line
    assert set(diggs["lean"]) <= {"rec_yds", "receptions", "anytime_td"}


def test_the_board_s_dict_reads_like_the_slate_s_own_and_a_roof_counts_nothing():
    as_dict = {"dome": False, "temp_f": 52.0, "wind_mph": 12.0, "wind_dir": "NE", "rain": True,
               "snow": False, "measured": True, "precip_chance": 0.74, "forecast": True}
    assert _white(as_dict)["pro"] == _white(RAIN)["pro"]
    for w in (Weather(dome=True, measured=True), Weather(rain=True, precip_chance=0.9),
              None, {"dome": False}):
        assert G.weather_line("rb", "RB", w) == (0, ""), w
    # A light chance moves too little to count either way.
    drizzle = Weather(rain=True, precip_chance=0.35, wind_mph=3.0, measured=True, forecast=True)
    assert G.weather_line("rb", "RB", drizzle) == (0, "")


def test_every_scan_hands_its_reads_the_forecast():
    src = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert 'weather=getattr(g, "weather", None) or gd.get("weather"))' in src, "the NFL's slate game"
    assert 'weather=gd.get("weather"))' in src, "college's built game"
    assert "contact=(contact or {}).get(opp[team]), weather=weather)" in src, "every read"


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
