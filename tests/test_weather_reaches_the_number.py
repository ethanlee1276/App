"""The kickoff forecast reaches the projection, and what it does is measured.

Ethan, 2026-09-23: "if it was a wind game it would should make passing
props lower so it doesn't seem like the model is tracking the weather and
shit correctly either idk, it seems weird so figure all that out."

He was right twice. nfl_build.show_games stamped the Open-Meteo forecast
on its own list of games and build_slate read the schedule again, so every
outdoor game the projections AND the published cards saw was the 60°F /
6 mph prior. And the bands it would have read were hand-set: ten seasons
(engine/wxfit.py, `python3 wxfit.py`) say wind cuts passing harder at
12-18 mph than they had it, does not lift rushing, cold alone does nothing
clear, and rain is the biggest weather effect of all.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import weather as W                                         # noqa: E402
from engine import wxfit as F                                           # noqa: E402
from engine.models import (Game, Weather, Team, DefenseProfile, Prop, GameLog,  # noqa: E402
                           SportsbookLine, PASS_YDS, REC_YDS, RECEPTIONS, RUSH_YDS)


def _wind(mph, **kw):
    return Weather(dome=False, temp_f=kw.pop("temp_f", 50.0), wind_mph=mph, measured=True, **kw)


# ---- the forecast reaches the slate ---------------------------------------
def test_the_slate_takes_the_games_the_forecast_was_stamped_on():
    from engine.sources import nflverse as nv
    row = {"season": "2026", "week": "1", "season_type": "REG", "player_display_name": "Vet",
           "position": "WR", "recent_team": "CHI", "opponent_team": "GB",
           "receiving_yards": "70", "receptions": "5", "targets": "8"}
    prior = [dict(row, season="2025", week=str(w)) for w in range(1, 18)]
    stamped = [Game(home="CHI", away="GB", weather=_wind(19.0), injuries=[], date="2026-09-27",
                    kickoff="13:00", spread=-3.0, total=41.5)]
    saved = {n: getattr(nv, n) for n in ("build_games", "load_weekly_stats", "roster_index",
                                         "roster_teams", "load_schedules")}
    nv.build_games = lambda s, w: [Game(home="CHI", away="GB", weather=Weather(temp_f=60.0, wind_mph=6.0),
                                        injuries=[], date="2026-09-27", kickoff="13:00")]
    nv.load_weekly_stats = lambda s: [] if s == 2026 else prior
    nv.roster_index = lambda s: {"Vet": {"team": "CHI", "position": "WR"}}
    nv.roster_teams = lambda s: {"Vet": "CHI"}
    nv.load_schedules = lambda: []
    try:
        slate = nv.build_slate(2026, 3, carry=True, report={}, games=stamped)
        unstamped = nv.build_slate(2026, 3, carry=True, report={})
    finally:
        for n, fn in saved.items():
            setattr(nv, n, fn)
    assert slate.games[0] is stamped[0] and slate.games[0].weather.wind_mph == 19.0
    assert unstamped.games[0].weather.measured is False, "without it, the schedule's prior"
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "report=carry_report, qb_backups=True, games=games)" in src
    assert src.index("games = show_games(args.season, args.week)") < src.index("games=games)")


# ---- wind reaches the number, by position, as measured ---------------------
def _proj(position, market, weather, matchup=None):
    from engine.projection import build_projection
    logs = [GameLog(week=w, opponent="x", value=v) for w, v in enumerate((70, 64, 75, 68, 72, 66), 1)]
    p = Prop(player="P", team="CHI", opponent="GB", position=position, market=market, logs=logs,
             career_avg=69.0, vs_opponent_avg=None, lines=[SportsbookLine("proxy", 68.5, -110, -110)],
             usage_role={"QB": "starter", "RB": "rb1"}.get(position, "wr1"))
    d = DefenseProfile(team="GB", **(matchup or {}))
    return build_projection(p, Game(home="CHI", away="GB", weather=weather), Team(abbr="GB", name="GB", defense=d))


def _step(pr, key):
    return next(s for s in pr.chain["steps"] if s["key"] == key)


def test_a_windy_game_lowers_passing_and_receiving_and_leaves_the_backs_alone():
    calm, windy = _wind(3.0), _wind(15.0)
    for pos, market, want in (("WR", REC_YDS, 0.92), ("WR", RECEPTIONS, 0.953), ("QB", PASS_YDS, 0.926)):
        a, b = _proj(pos, market, calm), _proj(pos, market, windy)
        assert abs(b.mean / a.mean - want) < 1e-6, (pos, market, b.mean / a.mean)
        assert _step(b, "weather")["mult"] == want and "12–18 mph" in _step(b, "weather")["why"]
    rb = _proj("RB", RUSH_YDS, windy)
    assert _step(rb, "weather")["mult"] == 1.0, "the rushing lift measured nothing"
    assert "no clear effect measured on a back's markets" in _step(rb, "weather")["why"]


def test_the_prior_moves_nothing_and_says_so():
    pr = _proj("WR", REC_YDS, Weather(temp_f=60.0, wind_mph=19.0))
    assert _step(pr, "weather")["mult"] == 1.0
    assert _step(pr, "weather")["why"].startswith("Outdoors, no forecast pulled")


def test_rain_applies_at_the_forecasts_own_chance():
    e = W.evaluate_weather(_wind(3.0, precip_chance=0.7, rain=True), "WR")
    assert abs(e.multipliers[REC_YDS] - (1 - 0.7 * (1 - W.RAIN[("rec_yds", "WRTE")]))) < 1e-9
    assert "at a 70% chance that is −9% and −7%" in e.reasons[0]
    assert W.evaluate_weather(_wind(3.0, precip_chance=0.2), "WR").multipliers[REC_YDS] == 1.0
    snow = W.evaluate_weather(_wind(3.0, temp_f=28.0, precip_chance=0.8, snow=True), "WR")
    assert snow.multipliers[RECEPTIONS] < 1.0 and snow.reasons[0].startswith("Snow 80% likely")


def test_cold_alone_moves_nothing_and_the_deep_block_stands():
    e = W.evaluate_weather(_wind(4.0, temp_f=12.0), "WR")
    assert all(v == 1.0 for v in e.multipliers.values()) and "no clear effect" in e.reasons[0]
    assert W.evaluate_weather(_wind(26.0), "WR").avoid_deep is True


def test_the_measured_weather_is_not_clipped_by_the_hand_tuned_cap():
    tough = {"vs_wr1": 0.70}
    pr = _proj("WR", REC_YDS, _wind(20.0), matchup=tough)
    cal = _proj("WR", REC_YDS, _wind(3.0), matchup=tough)
    assert abs(pr.mean / cal.mean - W.WIND[("rec_yds", "WRTE")]["18+"]) < 1e-6
    prod = pr.chain["base"]["value"]
    for s in pr.chain["steps"]:
        prod *= s["mult"]
    assert abs(prod - pr.mean) < 0.05, "base × steps is still the projection"


def test_the_card_says_which_way_the_weather_cuts():
    from engine.betting import evaluate_prop
    from engine.projection import build_projection
    windy = Game(home="CHI", away="GB", weather=_wind(16.0))
    logs = [GameLog(week=w, opponent="x", value=v) for w, v in enumerate((70, 64, 75, 68, 72, 66), 1)]
    signed = {}
    for line in (40.5, 95.5):                       # far under, far over the projection
        p = Prop(player="P", team="CHI", opponent="GB", position="WR", market=REC_YDS, logs=logs,
                 career_avg=69.0, vs_opponent_avg=None, lines=[SportsbookLine("DK", line, -110, -110)],
                 usage_role="wr1")
        pr = build_projection(p, windy, Team(abbr="GB", name="GB", defense=DefenseProfile(team="GB")))
        rec = evaluate_prop(p, pr, game=windy)
        signed[rec.side] = [r for r in rec.reasons if r.startswith("Wind ")]
    assert signed["OVER"] and signed["OVER"][0].endswith("— against this side"), signed
    assert signed["UNDER"] and signed["UNDER"][0].endswith("— with this side"), signed


# ---- the forecast is read on the scale the effect was measured on ----------
def test_a_forecast_takes_its_ranges_measured_cut_and_a_reading_its_band():
    """Ethan's droplet, 2026-09-23, `python3 wxfit.py --scale`, three runs.
    The median forecast/reported ratio (0.714) was a calm-day artifact; a
    single best scale (×1.18) traded one miss for another. What each
    forecast range has been worth — the measured effects averaged over the
    winds those forecasts became — is the table itself. Re-measured
    2026-09-25 at the kickoff hour (it had been read four hours early):
    a calm forecast is worth no cut at all, a 13+ one more than before."""
    wr = {mph: W.evaluate_weather(Weather(wind_mph=mph, measured=True, forecast=True), "WR")
          for mph in (3.0, 9.0, 11.0, 15.0)}
    assert [wr[m].multipliers[REC_YDS] for m in (3.0, 9.0, 11.0, 15.0)] == [0.997, 0.967, 0.945, 0.926]
    assert wr[9.0].multipliers[RECEPTIONS] == 0.994
    assert wr[9.0].reasons[0].startswith(
        "Wind 9 mph forecast — games forecast at 7–10 mph averaged receiving yards −3.3%, catches −0.6%")
    qb = W.evaluate_weather(Weather(wind_mph=15.0, measured=True, forecast=True), "QB")
    assert qb.multipliers[PASS_YDS] == 0.938 and qb.multipliers["pass_td"] == 0.870
    rb = W.evaluate_weather(Weather(wind_mph=15.0, measured=True, forecast=True), "RB")
    assert all(v == 1.0 for v in rb.multipliers.values()) and rb.reasons == []
    assert W.evaluate_weather(_wind(9.0), "WR").multipliers[REC_YDS] == W.WIND[("rec_yds", "WRTE")]["8-12"], \
        "a played game's reported wind keeps the band it was measured in"
    from engine.touchdowns import weather_td_multiplier
    g = Game(home="CHI", away="GB", weather=Weather(wind_mph=9.0, measured=True, forecast=True))
    assert weather_td_multiplier(g, "WR")[0] == W.TD_WIND_FORECAST["pass"]["7-10"]
    assert weather_td_multiplier(g, "QB")[0] == 1.0
    for key, rows in W.WIND_FORECAST.items():
        vals = [rows[r] for r in ("0-4", "4-7", "7-10", "10-13", "13+")]
        assert vals == sorted(vals, reverse=True) and all(v <= 1.0 for v in vals), key
        assert vals[-1] < 1.0, "a 13+ forecast always cuts"


def test_the_deep_ball_block_reads_the_forecast_as_it_is():
    from engine.betting import evaluate_prop
    from engine.projection import build_projection
    from engine.rules import apply_rules
    logs = [GameLog(week=w, opponent="x", value=v) for w, v in enumerate((70, 64, 75, 68, 72, 66), 1)]
    p = Prop(player="P", team="CHI", opponent="GB", position="WR", market=REC_YDS, logs=logs,
             career_avg=69.0, vs_opponent_avg=None, lines=[SportsbookLine("DK", 55.5, -110, -110)], usage_role="wr1")

    def warns(weather):
        g = Game(home="CHI", away="GB", weather=weather)
        pr = build_projection(p, g, Team(abbr="GB", name="GB", defense=DefenseProfile(team="GB")))
        return apply_rules(evaluate_prop(p, pr, game=g), p, g).warnings
    assert any(x.startswith("Wind 26 mph — deep-passing") for x in warns(
        Weather(wind_mph=26.0, measured=True, forecast=True)))
    assert not any("deep-passing" in x for x in warns(Weather(wind_mph=19.0, measured=True, forecast=True)))


def test_the_scale_check_compares_the_cut_not_the_winds():
    # Reported wind = the forecast with a calm-day floor: the ratio of winds
    # reads low, and the check still compares cuts.
    pairs = [(max(6.0, f), f) for f in (1, 2, 3, 2, 4, 1, 3, 2, 9, 10, 11, 14, 15, 19, 20)]
    assert F.scale(pairs)["median_ratio"] < 0.9
    rows = F.effect_by_forecast(pairs, W.WIND)
    assert [r["forecast"] for r in rows] == ["0-4", "4-7", "7-10", "10-13", "13+"]
    assert all(t == b for r in rows for (t, b) in r["markets"].values()), "reading == forecast here"
    shipped = F.effect_by_forecast(pairs, {("rec_yds", "WRTE"): W.WIND[("rec_yds", "WRTE")]}, W.forecast_cut)
    assert shipped[2]["markets"][("rec_yds", "WRTE")] == (0.955, 0.967)
    assert F.forecast_range(3.9) == "0-4" and F.forecast_range(13.0) == "13+" and F.FORECAST_TOLERANCE == 0.01
    src = open(os.path.join(ROOT, "wxfit.py"), encoding="utf-8").read()
    assert "F.effect_by_forecast(pairs, table, W.forecast_cut)" in src and "CHANGE — a range is off by" in src


def test_an_ordinary_outdoor_day_does_not_light_the_weather_mark():
    from engine.pipeline import _conditions, MATERIAL_WEATHER
    priced = [{"market": "rec_yds", "team": "CHI", "opponent": "GB"}]
    calm = Game(home="CHI", away="GB", weather=Weather(wind_mph=5.0, measured=True, forecast=True))
    windy = Game(home="CHI", away="GB", weather=Weather(wind_mph=11.0, measured=True, forecast=True))
    assert MATERIAL_WEATHER == 0.03
    assert _conditions(calm, priced)["material"] is False
    assert _conditions(windy, priced)["material"] is True


def test_forecasts_are_flagged_where_they_are_stamped_and_neutral_sites_find_their_venue():
    from engine import nflwx
    from engine.cfb.props import weather_of_dict
    got = {}
    def fc(lat, lon, date, kickoff):
        got["at"] = (round(lat, 1), round(lon, 1))
        return {"temp_f": 75, "wind_mph": 6, "wind_dir": "E", "precip_chance": 0.1}
    rio = Game(home="DAL", away="BAL", weather=Weather(), date="2026-09-27", kickoff="20:30",
               neutral_site=True, venue="Maracana Stadium")
    assert nflwx.attach([rio], forecast=fc) == 1 and got["at"] == (-22.9, -43.2), "Rio, not Dallas"
    assert rio.weather.forecast is True and rio.weather.measured is True
    nowhere = Game(home="DAL", away="BAL", weather=Weather(), date="2026-09-27", kickoff="20:30",
                   neutral_site=True, venue="Somewhere Unmapped")
    assert nflwx.attach([nowhere], forecast=fc) == 0 and nowhere.weather.measured is False
    assert weather_of_dict({"temp_f": 60, "wind_mph": 9}, True).forecast is True
    from engine.sources import nflverse as nv
    assert 'venue=_s(r, "stadium")' in open(nv.__file__, encoding="utf-8").read()


def test_the_board_and_the_check_carry_the_forecast_flag():
    from engine.pipeline import _game_to_dict
    g = Game(home="CHI", away="GB", weather=Weather(wind_mph=10.0, measured=True, forecast=True, precip_chance=0.4))
    w = _game_to_dict(g)["weather"]
    assert w["forecast"] is True and w["precip_chance"] == 0.4
    from engine import inputcheck
    lines = inputcheck.weather({"nfl": {"games": [{"home": "CHI", "away": "GB", "weather": w}], "recommendations": []}})
    assert "GB @ CHI: 10 mph forecast, 65°F, 40% precipitation" in lines[3], lines


# ---- touchdowns: on top of the book total ---------------------------------
def test_touchdowns_cut_the_pass_catchers_and_not_a_quarterbacks_own_score():
    from engine.touchdowns import weather_td_multiplier
    g = Game(home="CHI", away="GB", weather=_wind(15.0))
    wr, why = weather_td_multiplier(g, "WR")
    assert wr == W.TD_WIND["pass"]["12-18"] and "beyond what the total already prices" in why[0]
    assert weather_td_multiplier(g, "QB")[0] == 1.0 and weather_td_multiplier(g, "RB")[0] == 1.0
    from engine.cfb import tds as T
    rain = T.weather_multiplier({"dome": False, "wind_mph": 4, "temp_f": 60, "precip_chance": 0.9}, "WR")
    assert abs(rain[0] - W.TD_WIND_FORECAST["pass"]["4-7"] * (1 - 0.9 * (1 - W.TD_RAIN["pass"]))) < 1e-9
    assert T.weather_multiplier({}, "WR")[0] == 1.0, "an unanswered college game moves nothing"


def test_college_props_see_the_chance_of_rain():
    from engine.cfb.props import _weather_of
    w = _weather_of({"weather": {"temp_f": 58, "wind_mph": 9, "precip_chance": 0.8}, "weather_checked": True})
    assert w.precip_chance == 0.8 and w.rain and w.measured


# ---- the fit and its rule --------------------------------------------------
def test_the_sky_line_is_read_as_the_sky_not_the_forecast():
    assert F.precip_of("Rain Temp: 58° F, Humidity: 84%, Wind: East 11 mph") == "rain"
    assert F.precip_of("Light Snow Temp: 33° F") == "snow"
    assert F.precip_of("Cloudy, Humid, Chance of Rain Temp: 79° F") is None
    assert F.precip_of("Sunny Temp: 84° F, Wind: NE 8 mph") is None
    sched = [{"game_id": "g1", "season": "2022", "week": "5", "game_type": "REG", "home_team": "CHI",
              "away_team": "GB", "roof": "outdoors", "temp": "", "wind": "", "total_line": "44",
              "spread_line": "3"}]
    c = F.conditions(sched, {"g1": "Rain Temp: 45° F, Humidity: 90%, Wind: NNW 16 mph"})
    assert c[(2022, 5, "CHI")] == {"roofed": False, "wind": 16.0, "temp": 45.0, "precip": "rain", "implied": 23.5}
    assert c[(2022, 5, "GB")]["implied"] == 20.5


def test_each_condition_is_measured_where_the_others_are_absent():
    cold_windy = {"roofed": False, "wind": 20.0, "temp": 25.0, "precip": None}
    assert F.tier_wind(cold_windy) is None and F.tier_freeze(cold_windy) is None
    wet = {"roofed": False, "wind": 5.0, "temp": 50.0, "precip": "rain"}
    assert F.tier_rain(wet) == "rain" and F.tier_wind(wet) is None and F.tier_freeze(wet) is None
    assert F.tier_wind({"roofed": True, "wind": None, "temp": None, "precip": None}) == "base"


def test_the_rule_and_the_carry_up():
    ok = {"mult": 0.90, "se": 0.02, "n": 400, "per": {s: 0.9 for s in range(2016, 2026)}}
    assert F.clears(ok)
    assert not F.clears(dict(ok, n=22)), "a handful of games does not ship"
    assert not F.clears(dict(ok, se=0.06)), "inside two standard errors"
    split = dict(ok, per={s: (0.8 if s % 2 else 1.1) for s in range(2016, 2026)})
    assert not F.clears(split), "half the seasons the other way"
    res = {("rec_yds", "WRTE", "12-18"): ok, ("rec_yds", "WRTE", "18+"): dict(ok, mult=0.97, se=0.05)}
    assert F.wind_table(res, [("rec_yds", "WRTE")]) == {("rec_yds", "WRTE"): {"12-18": 0.9, "18+": 0.9}}


def test_what_ships_is_the_fits_shape_and_nothing_hand_set_is_left():
    got = W.shipped()
    assert set(got) == {"wind", "freeze", "rain", "snow", "td_wind", "td_freeze", "td_rain", "td_snow"}
    for key, bands in got["wind"].items():
        assert key in F.PROP_KEYS and set(bands) <= set(F.BANDS)
        assert all(v < 1.0 for v in bands.values())
    assert not any(k[0] == "rush_yds" for k in got["wind"]), "the rushing lift is gone"
    assert got["freeze"] == {} and got["td_snow"] == {}
    got = F.scale([(10, 11), (20, 18), (5, 5)])
    assert {k: got[k] for k in ("n", "median_ratio", "mean_gap", "same_band")} == \
        {"n": 3, "median_ratio": 1.0, "mean_gap": -0.33, "same_band": 1.0}
    assert got["same_band_converted"] == 1.0 and [r["forecast"] for r in got["by_forecast"]] == ["4-7", "10-13", "13-"]


def test_the_droplet_check_reads_the_board():
    from engine import inputcheck
    board = {"games": [{"home": "CHI", "away": "GB", "weather": {"dome": False, "measured": True,
                                                                  "wind_mph": 17, "temp_f": 48}},
                       {"home": "DET", "away": "NYJ", "weather": {"dome": True, "measured": True}},
                       {"home": "BUF", "away": "MIA", "weather": {"dome": False, "measured": False}}],
             "recommendations": [{"market": "rec_yds", "chain": {"steps": [{"key": "weather", "mult": 0.92}]}}]}
    lines = inputcheck.weather({"nfl": board})
    assert "nfl: 3 games — 1 indoors, 2 outdoors, 1 of them forecast  (1 on the prior)" in lines[2]
    assert "GB @ CHI: 17 mph, 48°F" in lines[3] and "rec_yds 1 (×0.92–×0.92)" in lines[4]
    hc = open(os.path.join(ROOT, "homecheck.py"), encoding="utf-8").read()
    assert '"weather": (weather,' in hc


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
