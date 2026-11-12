"""Rain and wind reach a quarterback's completions and a kicker's points, and
a pick's weather sentence is signed by what the weather did to ITS market
(engine/weather WIND, RAIN, WIND_FORECAST, by_kind, sign_for; engine/wxfit
MARKETS, FORECAST_SHARES, forecast_row; engine/betting.evaluate_prop).

Ethan, 12 November 2026, the afternoon of the Commanders at the Giants (a 74%
chance of rain at kickoff, 12 mph forecast): "I feel like we are not putting
weather as a factor for the picks." For passing and receiving yards,
touchdowns, catches and a back's carries it was. But completions and a
kicker's points, bought and priced since October, were never measured, so
the rain and the wind left them alone. Measured the way the rest were, ten
seasons, the same rule: completions ×0.917 in rain, ×0.949 at 12-18 mph and
×0.935 at 18+; a kicker's points ×0.930 from 12 mph. Pass attempts, field
goals made, and a kicker in rain or cold measured nothing clear and stay
untouched. And the sentence under a pick was signed by a minus sign anywhere
in it: a back's carries OVER in rain — carries +7% — read "against this side"
for his catches' −16%. What these hold:

  * the two markets ship in the fit's own shape, and the fit measures them;
  * their forecast rows come from what each forecast range turned into,
    shares that give every row the droplet measured back to within 0.001;
  * a quarterback's completions and a kicker's points move with the
    forecast; attempts and field goals made do not;
  * the game's weather read names them, and lights the mark when priced;
  * a pick's weather sentence is with or against its side by its own
    market, and says so when the weather left its market alone.

Run directly: `python3 tests/test_the_weather_reaches_completions_and_kickers.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import weather as W                                     # noqa: E402
from engine import wxfit as F                                       # noqa: E402
from engine.models import (Game, Weather, Team, DefenseProfile, Prop, GameLog,  # noqa: E402
                           SportsbookLine, PASS_CMP, PASS_ATT, KICK_PTS, FG_MADE, RUSH_ATT,
                           RUSH_YDS)

#: The Giants game as the board read it that afternoon.
WET = dict(dome=False, temp_f=52.0, wind_mph=12.0, precip_chance=0.74, rain=True,
           measured=True, forecast=True)


def test_the_two_markets_ship_in_the_fits_shape():
    assert W.WIND[("pass_cmp", "QB")] == {"12-18": 0.949, "18+": 0.935}
    assert W.WIND[("kick_pts", "K")] == {"12-18": 0.93, "18+": 0.93}, "18+ carried from 12-18"
    assert W.RAIN[("pass_cmp", "QB")] == 0.917
    assert ("kick_pts", "K") not in W.RAIN and not W.FREEZE, "a kicker in rain or cold: nothing clear"
    for key in (("pass_cmp", "QB"), ("kick_pts", "K")):
        assert key in F.PROP_KEYS, key
        assert key in W.WIND_FORECAST, key
    assert not any(k[0] in (PASS_ATT, FG_MADE) for k in list(W.WIND) + list(W.RAIN) + list(W.SNOW)), \
        "attempts and field goals made measured nothing"
    assert ("kick_pts", ("fg_made", "fg_made", "fg_made", "pat_made"), 4.0) in F.MARKETS["K"]
    assert F.GROUP["K"] == "K"


def test_the_fit_measures_a_kickers_points_three_a_field_goal():
    cond = {(2024, wk, "BUF"): {"roofed": True, "wind": None, "temp": None, "precip": None,
                                "implied": None} for wk in range(1, 9)}
    rows = [{"season_type": "REG", "position": "K", "player_display_name": "Kicker", "week": wk,
             "team": "BUF", "fg_made": fg, "pat_made": pat}
            for wk, fg, pat in ((1, 2, 3), (2, 1, 4), (3, 3, 2), (4, 2, 2), (5, 0, 5))]
    got = [p for p in F.samples(2024, rows, cond) if p["m"] == "kick_pts"]
    assert [p["y"] for p in got] == [8.0, 5.0], "week 4: 3×2 + 2; week 5: 0 + 5"
    assert all(p["g"] == "K" for p in got)


def test_the_forecast_rows_come_from_what_the_forecasts_turned_into():
    for name, shares in F.FORECAST_SHARES.items():
        assert 0.0 <= sum(shares) <= 1.0, name
    # The shares give every row the droplet measured back to within 0.001 …
    for key, row in W.WIND_FORECAST.items():
        derived = F.forecast_row(W.WIND[key])
        assert max(abs(derived[r] - row[r]) for r in row) <= 0.001 + 1e-9, (key, derived, row)
    td = F.forecast_row(W.TD_WIND["pass"])
    assert max(abs(td[r] - W.TD_WIND_FORECAST["pass"][r]) for r in td) <= 0.001 + 1e-9
    # … and the two new rows are exactly theirs.
    assert W.WIND_FORECAST[("pass_cmp", "QB")] == F.forecast_row(W.WIND[("pass_cmp", "QB")])
    assert W.WIND_FORECAST[("kick_pts", "K")] == F.forecast_row(W.WIND[("kick_pts", "K")])
    assert W.WIND_FORECAST[("kick_pts", "K")] == {"0-4": 1.0, "4-7": 0.995, "7-10": 0.991,
                                                   "10-13": 0.97, "13+": 0.943}


def test_completions_and_kicking_points_move_and_attempts_do_not():
    qb = W.evaluate_weather(Weather(**WET), "QB")
    want = W.WIND_FORECAST[("pass_cmp", "QB")]["10-13"] * W.at_chance(0.917, 0.74)
    assert abs(qb.multipliers[PASS_CMP] - want) < 1e-9, qb.multipliers
    assert qb.multipliers.get(PASS_ATT, 1.0) == 1.0
    assert "completions −2.3%" in qb.reasons[0] and "completions −8%" in qb.reasons[1], qb.reasons
    k = W.evaluate_weather(Weather(**dict(WET, wind_mph=15.0)), "K")
    assert k.multipliers[KICK_PTS] == 0.943 and k.multipliers.get(FG_MADE, 1.0) == 1.0
    assert k.reasons[0].startswith("Wind 15 mph forecast — games forecast at 13+ mph averaged "
                                   "kicking points −5.7%"), k.reasons
    assert "no clear effect measured on these markets in rain; left alone" in k.reasons[1]
    # A played game's reported wind keeps its band; under 12 mph a kicker is left alone.
    read = dict(WET, forecast=False, precip_chance=0.0, rain=False)
    assert W.evaluate_weather(Weather(**dict(read, wind_mph=15.0)), "K").multipliers[KICK_PTS] == 0.93
    calm = W.evaluate_weather(Weather(**dict(read, wind_mph=10.0)), "K")
    assert calm.multipliers[KICK_PTS] == 1.0
    assert calm.reasons == ["Wind 10 mph — no clear effect measured on a kicker's markets at 8–12 mph; "
                            "left alone"]


def test_the_games_read_names_them_and_lights_the_mark():
    from engine.pipeline import _conditions
    eff = W.evaluate_weather(Weather(**dict(WET, wind_mph=15.0)))
    assert "completions −4.6%" in eff.reasons[0] and "kicking points −5.7%" in eff.reasons[0]
    game = Game(home="NYG", away="WAS", weather=Weather(**dict(WET, wind_mph=15.0, precip_chance=0.0,
                                                               rain=False)))
    kicks = [{"market": "kick_pts", "team": "NYG", "opponent": "WAS"},
             {"market": "pass_cmp", "team": "WAS", "opponent": "NYG"}]
    got = _conditions(game, kicks)
    assert got["material"] is True and got["markets_moved"] == ["kick_pts", "pass_cmp"], got


def _card(pos, market, vals, line, side_lines):
    from engine.betting import evaluate_prop
    from engine.projection import build_projection
    game = Game(home="NYG", away="WAS", weather=Weather(**WET))
    logs = [GameLog(week=w, opponent="x", value=v) for w, v in enumerate(vals, 1)]
    p = Prop(player="P", team="WAS", opponent="NYG", position=pos, market=market, logs=logs,
             career_avg=sum(vals) / len(vals), vs_opponent_avg=None,
             lines=[SportsbookLine("DK", line, -110, -110)])
    pr = build_projection(p, game, Team(abbr="NYG", name="NYG", defense=DefenseProfile(team="NYG")))
    out = {}
    for ln in side_lines:
        p.lines = [SportsbookLine("DK", ln, -110, -110)]
        rec = evaluate_prop(p, pr, game=game)
        out[rec.side] = [r for r in rec.reasons if r.startswith(("Wind ", "Rain "))]
    return out


def test_a_picks_weather_sentence_is_signed_by_its_own_market():
    # A back's carries go UP in rain: the OVER has the rain with it.
    carries = _card("RB", RUSH_ATT, (16, 18, 15, 17, 19, 16), 16.5, (12.5, 21.5))
    assert carries["OVER"][0].endswith("— with this side"), carries
    assert carries["UNDER"][0].endswith("— against this side"), carries
    # His rushing yards are left alone, and the sentence says so rather than taking a side.
    yards = _card("RB", RUSH_YDS, (70, 64, 75, 68, 72, 66), 68.5, (40.5, 95.5))
    for side in ("OVER", "UNDER"):
        assert yards[side] and all(r.endswith("— his rushing yards left alone") for r in yards[side]), yards
    # A quarterback's legs: the passing cut is not his rushing yards'.
    legs = _card("QB", RUSH_YDS, (40, 35, 50, 45, 38, 42), 40.5, (20.5, 60.5))
    assert len(legs["OVER"]) == 2 and all(r.endswith("left alone") for r in legs["OVER"]), legs
    # Completions and a kicker's points: cut, so with the UNDER.
    cmp_ = _card("QB", PASS_CMP, (22, 24, 21, 25, 23, 22), 22.5, (17.5, 27.5))
    assert all(r.endswith("— with this side") for r in cmp_["UNDER"]) and len(cmp_["UNDER"]) == 2, cmp_
    assert all(r.endswith("— against this side") for r in cmp_["OVER"]), cmp_
    kick = _card("K", KICK_PTS, (8, 7, 9, 6, 8, 10), 7.5, (4.5, 11.5))
    assert kick["UNDER"][0].endswith("— with this side") and kick["OVER"][0].endswith("— against this side")
    assert kick["UNDER"][1].endswith("left alone"), "the rain line already says it measured nothing"


def test_an_effect_built_without_the_split_keeps_the_old_rule():
    from engine.weather import WeatherEffect, sign_for
    assert sign_for(WeatherEffect({}), "rush_att", "Rain 70% likely … −9%") is None
    eff = W.evaluate_weather(Weather(**WET), "RB")
    assert sign_for(eff, "rush_att", eff.reasons[0]) == 1
    assert sign_for(eff, "receptions", eff.reasons[0]) == -1
    assert sign_for(eff, "rush_yds", eff.reasons[0]) == 0
    assert W.label("rush_rec_yds") == "rush + rec yards" and W.label("pass_cmp") == "completions"


def test_the_input_check_knows_they_are_measured_now():
    from engine import inputcheck as C
    assert C.flat_by_construction("nfl", "pass_cmp", "weather") is None
    assert C.flat_by_construction("nfl", "kick_pts", "weather") is None
    assert C.flat_by_construction("nfl", "pass_att", "weather"), "attempts: no coefficient, known flat"
    assert C.flat_by_construction("nfl", "fg_made", "weather")


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
