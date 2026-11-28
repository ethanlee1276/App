"""Bad weather is said first, in red (step AIO, 27 November 2026).

Ethan, on Broncos at Steelers' game page (its chips read "41°F · 17mph SW · kickoff forecast"): "if the weather is
going to be bad for that game, like high wind or rain or both or snow or whatever, it needs to be in red and shown at
the top so people know instantly that this game is going to be a rainy game or a snowy game". What holds:

  * an outdoor game whose forecast has rain or snow likely (the board's own 60% bar, snow at or below freezing) or,
    in football, a 13 mph wind or more at kickoff gets a red line under its date and at the top of its report,
    naming the game ("Windy game", "Rainy game", "Windy and snowy game") and the forecast;
  * a football line says what that weather has done to the numbers, in the engine's own measured figures, which
    this test holds the page's to;
  * a dome, a roof read as closed, an indoor league, a game with no forecast, and a finished game get none.

The games below are this test's own.

    python3 tests/test_bad_weather_is_said_first.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
REPORT = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def _const(src, name):
    i = src.index(f"const {name} = ")
    return src[i:src.index("\n};\n", i) + 4]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    lib = "\n".join([_const(DETAIL, "WX_ALERT")] + [_fn(DETAIL, n) for n in ("wxNum", "wxCut", "wxAlert", "wxAlertHTML")])
    prog = f"""
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const icon = (n) => `<i data-icon="${{n}}"></i>`;
      {lib}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_bad_forecast_is_named_and_said_with_what_it_does():
    got = _node("""
      const g = (w, extra) => Object.assign({home: "PIT", away: "DEN", roof: "outdoors", weather: w}, extra || {});
      return {
        windy: wxAlert(g({temp_f: 41, wind_mph: 17, wind_dir: "SW", precip_chance: 0.1, measured: true}), "nfl"),
        rainy: wxAlert(g({temp_f: 48, wind_mph: 6, precip_chance: 0.7, rain: true, measured: true}), "nfl"),
        snowy: wxAlert(g({temp_f: 28, wind_mph: 8, precip_chance: 0.8, snow: true, measured: true}), "nfl"),
        both: wxAlert(g({temp_f: 44, wind_mph: 21.4, wind_dir: "NW", precip_chance: 0.65, rain: true}), "cfb"),
        windSnow: wxAlert(g({temp_f: 30, wind_mph: 15, precip_chance: 0.9}), "nfl"),
        mlbRain: wxAlert(g({temp_f: 62, wind_mph: 20, wind_dir: "out", rain: true, measured: true}), "mlb"),
        html: wxAlertHTML(g({temp_f: 41, wind_mph: 17, wind_dir: "SW", measured: true}), "nfl"),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    w = got["windy"]
    assert (w["head"], w["said"], w["kinds"]) == ("Windy game", "17 mph SW wind at kickoff, 41°F", ["wind"]), w
    assert w["does"] == ("Wind this strong has cut passing touchdowns about 13% and receiving yards about 7% (NFL games, "
                         "2016–2025). Our player numbers for this game already include it."), w
    r = got["rainy"]
    assert (r["head"], r["said"]) == ("Rainy game", "A 70% chance of rain at kickoff, 48°F"), r
    assert r["does"].startswith("Rain has cut receivers’ yards about 13% and passing yards about 11% (NFL games"), r
    s = got["snowy"]
    assert (s["head"], s["said"]) == ("Snowy game", "An 80% chance of snow at kickoff, 28°F"), s
    assert s["does"].startswith("Snow has cut receivers’ yards about 17% and their catches about 19% (NFL games"), s
    b = got["both"]
    assert (b["head"], b["said"], b["kinds"]) == ("Windy and rainy game", "21 mph NW wind and a 65% chance of rain at "
                                                  "kickoff, 44°F", ["wind", "rain"]), b
    assert b["does"].startswith("Wind this strong has cut passing touchdowns about 13% and receiving yards about 7%; "
                                "rain has cut receivers’ yards about 13%"), "college reads the NFL's measured table"
    ws = got["windSnow"]
    assert (ws["head"], ws["kinds"]) == ("Windy and snowy game", ["wind", "snow"]), "snow read off the chance and the cold"
    m = got["mlbRain"]
    assert (m["head"], m["said"], m["does"], m["kinds"]) == ("Rainy game", "Rain likely at first pitch, 62°F", "",
                                                             ["rain"]), "baseball: no football figures, no wind rule"
    assert 'class="wx-alert" role="alert"' in got["html"] and '<b class="wx-alert-head">Windy game</b>' in got["html"]


def test_no_forecast_or_no_bad_weather_says_nothing():
    got = _node("""
      const g = (w, extra) => Object.assign({home: "X", away: "Y", weather: w}, extra || {});
      const bad = {temp_f: 30, wind_mph: 25, precip_chance: 0.9, snow: true, measured: true};
      return [
        wxAlert(g({temp_f: 41, wind_mph: 12.9, precip_chance: 0.59, measured: true}), "nfl"),   // just under both bars
        wxAlert(g(bad, {roof: "dome"}), "nfl"),
        wxAlert(g(Object.assign({}, bad, {dome: true})), "nfl"),
        wxAlert(g(Object.assign({}, bad, {retractable: true})), "nfl"),
        wxAlert(g(bad, {roof: "closed"}), "nfl"),
        wxAlert(g(bad, {indoor: true}), "cfb"),
        wxAlert(g(Object.assign({}, bad, {measured: false})), "nfl"),                       // the mild-day prior
        wxAlert(g({wind_mph: 30}), "nfl"),                                                  // no temperature: not pulled
        wxAlert(g(bad), "nba"), wxAlert(g(bad), "nhl"), wxAlert(g(bad), "cbb"),
        wxAlert({home: "X", away: "Y"}, "nfl"),
        wxAlertHTML(g({temp_f: 70, wind_mph: 3, measured: true}), "nfl"),
      ];""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == [None] * 12 + [""], got


def test_the_figures_are_the_engines_own():
    from engine import nflwx, weather, wxfit
    src = _const(DETAIL, "WX_ALERT")
    num = lambda key: float(re.search(key + r":\s*([0-9.]+)", src).group(1))  # noqa: E731
    assert num("precipLikely") == nflwx.PRECIP_LIKELY and num("freezingF") == nflwx.FREEZING_F
    assert num("windMph") == wxfit.FORECAST_RANGES[0][0] and wxfit.FORECAST_RANGES[0][1] == "13+", \
        "the top of the forecast ranges the wind was measured in"
    wind = src[src.index("wind: {"):src.index("}", src.index("wind: {"))]
    rain = src[src.index("rain: {"):src.index("}", src.index("rain: {"))]
    snow = src[src.index("snow: {"):src.index("}", src.index("snow: {"))]
    assert f"pass_td: {weather.WIND_FORECAST[('pass_td', 'QB')]['13+']:.3f}" in wind
    assert f"rec_yds: {weather.WIND_FORECAST[('rec_yds', 'WRTE')]['13+']:.3f}" in wind
    assert f"rec_yds: {weather.RAIN[('rec_yds', 'WRTE')]:.3f}" in rain
    assert f"pass_yds: {weather.RAIN[('pass_yds', 'QB')]:.3f}" in rain
    assert f"rec_yds: {weather.SNOW[('rec_yds', 'WRTE')]:.3f}" in snow
    assert f"receptions: {weather.SNOW[('receptions', 'WRTE')]:.3f}" in snow
    assert not weather.FREEZE, "cold on its own measured nothing, so it raises no warning"


def test_it_sits_at_the_top_of_the_game_and_its_report():
    hero = DETAIL[DETAIL.index('<div class="gp-sub">${escapeHtml(whenLabel(g.date, g.kickoff))}'):]
    assert hero.index('${isFinal ? "" : wxAlertHTML(g, state.sport)}') < hero.index("gpLines}"), \
        "under the date, above the lines, and gone once the game is final"
    rep = _fn(DETAIL, "gameReportHTML")
    assert 'const wxa = results ? "" : wxAlertHTML(g, state.sport);' in rep
    assert "if (wxa) extras = Object.assign({}, extras, { wxAlert: wxa });" in rep
    assert "const wx = !solo && extras && extras.wxAlert ? extras.wxAlert : \"\";" in REPORT
    assert 'class="gr">${head}${wx}${featuredHTML(r.featured)}' in REPORT, "first thing under the report's heading"
    block = CSS[CSS.index(".wx-alert {"):CSS.index(".wx-alert-does")]
    assert "var(--bad)" in block and ".wx-alert-head { color: var(--bad);" in CSS, "red, in both themes"
    assert "border:" not in block, "a red tint, not an outline (tests/test_no_hard_lines.py)"


if __name__ == "__main__":
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
