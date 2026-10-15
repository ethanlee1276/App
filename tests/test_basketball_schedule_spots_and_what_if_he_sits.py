"""Basketball's two Toolbox cards: tonight's schedule spots, and what if he sits.

Ethan, 2026-10-15, two of the sixteen ideas he asked to have built ("do
every one for every sport"): NBA schedule flags — the back-to-back, three
in four, the trip, the altitude, the blowout risk — context until
measured; and a "what if he sits" toggle that moves no number unless a
measured rule says so, and otherwise shows the on/off evidence.

What these hold: the spots carry the build's own rest bucket and add the
trip, the clock and the altitude from a table of the arenas (every NBA
and WNBA club in it), with the blowout watch once the lines are in; the
what-if reads only box scores, counts his games for this club only, and
says when the missed games are too few; the build, the server and the
page reach both, and nothing on the board moves.

Run directly: `python3 tests/test_basketball_schedule_spots_and_what_if_he_sits.py`
"""
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.nba import schedspots as S                            # noqa: E402
from engine.nba import whatif as W                                # noqa: E402

EXTRAS = ROOT / "web" / "js" / "extras.js"

SCHED = {"2026-10-21": [{"home": "DEN", "away": "LAL"}, {"home": "MIA", "away": "ORL"}],
         "2026-10-19": [{"home": "BOS", "away": "NYK"}]}
DENS = {"LAL": {"rest": "b2b_home", "games_in_4": 2, "games_in_6": 2}, "DEN": {"rest": "b2b_home"},
        "NYK": {"rest": "2plus"}, "BOS": {"rest": "1day"}, "ORL": {"rest": "3in4"}, "MIA": {"rest": "b2b_home"}}


def test_the_trip_the_clock_and_the_altitude():
    rows = S.spots([{"home": "DEN", "away": "NYK"}, {"home": "BOS", "away": "LAL"}, {"home": "ORL", "away": "MIA"}],
                   SCHED, "2026-10-22", "nba", DENS)
    den = rows[0]
    assert den["arena"] == "Ball Arena" and den["feet"] == 5280
    nyk = den["teams"]["away"]
    assert nyk["from"] == "BOS" and nyk["days_since"] == 3
    assert 1700 < nyk["miles"] < 1800 and nyk["tz_shift"] == -2
    assert set(nyk["flags"]) == {"long_trip", "clock", "altitude"}, nyk["flags"]
    home = den["teams"]["home"]
    assert home["rest_word"] == "Second night of a back-to-back" and "altitude" not in home["flags"]
    assert home["miles"] == 0 and home["flags"] == ["b2b_home"], "a home stand is no trip"
    lal = rows[1]["teams"]["away"]
    assert lal["tz_shift"] == 2 and "b2b_home" in lal["flags"] and lal["games_in_4"] == 2
    assert "altitude" not in lal["flags"], "Boston is not up a mountain"
    orl = rows[2]["teams"]["home"]
    assert orl["miles"] < 300 and "long_trip" not in orl["flags"] and orl["flags"] == ["3in4"]


def test_the_blowout_watch_waits_for_the_lines():
    rows = S.spots([{"home": "DEN", "away": "NYK"}, {"home": "BOS", "away": "LAL"}], SCHED, "2026-10-22", "nba", DENS)
    assert rows[0]["spread"] is None and "blowout" not in rows[0]["teams"]["home"]["flags"]
    S.add_spreads(rows, {"DEN": (-11.5, True), "BOS": (-3.0, True)})
    assert rows[0]["spread"] == -11.5
    assert "blowout" in rows[0]["teams"]["home"]["flags"] and "blowout" in rows[0]["teams"]["away"]["flags"]
    assert "blowout" not in rows[1]["teams"]["home"]["flags"]
    S.add_spreads(rows, {"DEN": (-11.5, True)})
    assert rows[0]["teams"]["home"]["flags"].count("blowout") == 1, "twice is still once"


def test_a_club_the_table_does_not_know_gets_no_guess():
    rows = S.spots([{"home": "XXX", "away": "NYK"}], SCHED, "2026-10-22", "nba", {})
    t = rows[0]["teams"]["away"]
    assert "miles" not in t and "altitude" not in t["flags"] and rows[0]["feet"] is None
    assert t["rest"] == "" and t["flags"] == []
    assert S.last_venue({}, "NYK", "not a date") is None


def test_every_club_has_an_arena():
    def codes(js):
        return set(re.findall(r'^  "([A-Z]{2,4})"', (ROOT / "web" / "js" / js).read_text(), re.M))
    assert codes("teams_nba.js") == set(S.ARENAS["nba"]), codes("teams_nba.js") ^ set(S.ARENAS["nba"])
    assert codes("teams_wnba.js") <= set(S.ARENAS["wnba"]), codes("teams_wnba.js") - set(S.ARENAS["wnba"])
    high = {t for t, a in S.ARENAS["nba"].items() if a[3] >= S.HIGH_FT}
    assert high == {"DEN", "UTA"}
    assert abs(S.miles((40.0, -75.0), (40.0, -75.0))) < 1e-9


def _logs():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport, season, player, team, position, period, market, value, "
                 "opponent, home)")
    dates = [f"2026-{m:02d}-{d:02d}" for m in (1, 2) for d in range(1, 29, 3)]
    for i, dt in enumerate(dates):
        star_out = i % 4 == 0
        rows = [("Star", 36, 30), ("Wing", 30, 14), ("Guard", 28, 12), ("Big", 26, 10)]
        # The new man arrives halfway: his first game for BOS is dates[10], 2026-02-01.
        if i >= 10:
            rows.append(("New Man", 12, 4))
        for p, mins, pts in rows:
            if p == "Star" and star_out:
                continue
            m = mins + (4 if star_out and p != "Star" else 0)
            pt = pts + (6 if star_out and p == "Wing" else 0)
            for mk, v in (("min", m), ("pts", pt), ("reb", 5), ("ast", 3)):
                conn.execute("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?)",
                             ("nba", 2026, p, "BOS", "S", dt, mk, v, "NYK", 1))
    # Another club's rows are never read.
    conn.execute("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?)",
                 ("nba", 2026, "Elsewhere", "NYK", "S", "2026-01-01", "min", 40, "BOS", 0))
    return conn


def test_what_if_reads_the_box_scores():
    conn = _logs()
    rot = W.whatif(conn, "nba", "BOS", "", [2026])["rotation"]
    assert [r["player"] for r in rot][:1] == ["Wing"] and "Elsewhere" not in {r["player"] for r in rot}
    out = W.whatif(conn, "nba", "BOS", "Star", [2026])
    pts = out["stats"]["pts"]
    # He sat the club's first night too, but that was before his first game
    # for it: four missed games count, not five.
    assert out["since"] == "2026-01-04"
    assert pts["n_out"] == 4 and pts["enough"] is True
    top = pts["rows"][0]
    assert top["player"] == "Wing" and top["without"] > top["with"] and top["n_without"] == 4
    assert set(out["stats"]) == {"min", "pts", "reb", "ast"}


def test_his_games_before_the_club_are_not_sat():
    conn = _logs()
    out = W.whatif(conn, "nba", "BOS", "New Man", [2026])
    assert out["since"] == "2026-02-01", out["since"]
    assert out["stats"]["min"]["n_out"] == 0 and out["stats"]["min"]["enough"] is False
    assert W.whatif(conn, "nba", "BOS", "Nobody", [2026])["error"] == "no games for this club"
    assert W.whatif(conn, "nfl", "BOS", "", [2026]) == {"error": "league and team"}


def test_the_build_the_server_and_the_page_reach_them():
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert 'out["schedule_spots"] = _ss.spots(games, sched_days, args.date, args.league,' in src
    assert '_ss.add_spreads(out.get("schedule_spots") or [], spread_by_team)' in src
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/hoops/whatif"' in srv and "W.whatif(conn, league, team, player)" in srv
    js = EXTRAS.read_text(encoding="utf-8")
    assert "nba: [spotsHTML, whatifHTML]" in js and "wnba: [spotsHTML, whatifHTML]" in js
    assert "/api/hoops/whatif?" in js and "Evidence only: the board’s numbers do not move for it." in js
    assert "Context, not a price." in js


def _node(body: str):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    script = ("const vm = require('vm'); const fs = require('fs');"
              "const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(EXTRAS))}, 'utf8'), ctx);"
              "const X = ctx.window.QBExtras;" + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_cards_say_what_they_show():
    rows = S.spots([{"home": "DEN", "away": "NYK"}], SCHED, "2026-10-22", "nba", DENS)
    S.add_spreads(rows, {"DEN": (-11.5, True)})
    thin = {"player": "A", "team": "BOS", "since": "2026-01-01", "floor": 3,
            "stats": {"min": {"n_played": 20, "n_out": 1, "enough": False,
                              "rows": [{"player": "B", "with": 0.2, "without": 0.3, "delta": 0.1,
                                        "n_with": 20, "n_without": 1}]}}}
    got = _node(f"process.stdout.write(JSON.stringify({{chips: X.spotChips({json.dumps(rows[0]['teams']['away'])}),"
                f"html: X.spotsHTML({{schedule_spots: {json.dumps(rows)}}}), none: X.spotsHTML({{}}),"
                f"thin: X.whatifOut({json.dumps(thin)}, 'min'), err: X.whatifOut({{error: 'no games for this club'}}, 'min')}}));")
    if got is None:
        return
    words = [w for _t, w in got["chips"]]
    assert words[0].endswith("mi from BOS") and "Clock −2 h" in words and "Up to altitude" in words
    assert "Blowout watch" in words
    assert "NYK @ DEN" in got["html"] and "5,280 ft" in got["html"] and "DEN −11.5" in got["html"]
    assert "No games on the board tonight" in got["none"]
    assert "the shape, not evidence" in got["thin"] and "+10.0" in got["thin"]
    assert "no games for this club" in got["err"]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
