"""College's rain, asked of college's own games (engine/wxfit college_*,
wxfit.py --college).

Ethan, 6 November: "dive into the weather factor for NFL and college
football games". College reads the NFL's rain table; this asks college's
own games the NFL's question, the NFL's way. The kickoffs and venues come
from the cfbfastR mirror, the venues' coordinates from CFBD, the weather
from Open-Meteo's archive (free, keyless) and the carries from the box's
own college logs. What these hold:

  * a game is kept only when it is a finished regular-season FBS game with
    a known kickoff hour at a venue CFBD places, keyed as the box's logs key
    it (the mirror's game number, the box's team keys);
  * the weather is the archive's reading at kickoff: rain once a millimetre
    fell over the game's first three hours, snow when it fell as snow or
    below freezing, nothing when no reading sits near kickoff;
  * one archive request per venue per season;
  * the carries are measured exactly as the NFL's (team_samples,
    measure_all, the house rule), and the verdict says whether college
    agrees with, differs from or contradicts the NFL's step, or cannot say.

Run directly: `python3 tests/test_college_rain_is_asked_of_its_own_games.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import wxfit as CLI                                              # noqa: E402
from engine import wxfit as F                                    # noqa: E402


def _row(**kw):
    base = {"game_id": "401000001", "season": "2024", "season_type": "regular",
            "start_date": "2024-09-07T19:30:00.000Z", "start_time_tbd": "FALSE",
            "completed": "TRUE", "venue": "Sanford Stadium", "home_id": "61", "away_id": "333",
            "home_division": "fbs", "away_division": "fbs"}
    base.update(kw)
    return base


VENUES = {"sanford stadium": {"lat": 33.95, "lon": -83.37, "dome": False},
          "caesars superdome": {"lat": 29.95, "lon": -90.08, "dome": True}}


def _venues():
    from engine.sources.cfbdata import name_key
    return {name_key(k): v for k, v in VENUES.items()}


def test_a_placed_fbs_game_is_keyed_as_the_box_keys_it():
    ids = {"61": "UGA", "333": "BAMA"}
    rows = [_row(),
            _row(game_id="401000002", start_time_tbd="TRUE"),
            _row(game_id="401000003", away_division="fcs"),
            _row(game_id="401000004", venue="Nowhere Field"),
            _row(game_id="401000005", season_type="postseason"),
            _row(game_id="401000006", completed="FALSE"),
            _row(game_id="401000007", venue="Caesars Superdome")]
    got = F.college_games(rows, 2024, ids, _venues())
    assert [g["game_id"] for g in got] == ["401000001", "401000007"], got
    g = got[0]
    assert (g["home"], g["away"], g["roofed"]) == ("UGA", "BAMA", False)
    assert got[1]["roofed"], "a dome is the base, as the NFL's"
    # With no id map the box keys a school espn:<id>, and so does this.
    assert F.college_games(rows[:1], 2024, None, _venues())[0]["home"] == "espn:61"


def _payload(start="2024-09-07T17:00", hours=8, precip=(), snow=(), temp=70.0, wind=5.0):
    import datetime as dt
    t0 = dt.datetime.fromisoformat(start)
    times = [(t0 + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    p = list(precip) + [0.0] * (hours - len(precip))
    s = list(snow) + [0.0] * (hours - len(snow))
    return {"hourly": {"time": times, "temperature_2m": [temp] * hours,
                       "wind_speed_10m": [wind] * hours, "precipitation": p, "snowfall": s}}


def test_the_weather_at_kickoff_reads_rain_snow_and_dry():
    # Kickoff 19:30 sits between the 19:00 and 20:00 readings; the board's
    # own picker (engine/cfb/wx.nearest_hour) takes the earlier, so the
    # game's three hours are 19:00-22:00 (indexes 2 to 4).
    ko = "2024-09-07T19:30:00.000Z"
    wet = F.game_weather(_payload(precip=(0, 0, 0.4, 0.4, 0.4)), ko)
    assert wet == {"temp": 70.0, "wind": 5.0, "precip": "rain"}, wet
    dry = F.game_weather(_payload(precip=(3.0, 3.0, 0, 0, 0.2)), ko)
    assert dry["precip"] is None, "rain that stopped before kickoff is not a wet game"
    assert F.game_weather(_payload(precip=(0, 0, 0, 1, 1, 1), temp=30.0), ko)["precip"] == "snow"
    assert F.game_weather(_payload(precip=(0, 0, 0, 1, 1, 1), snow=(0, 0, 0, 0.5)), ko)["precip"] == "snow"
    assert F.game_weather(_payload(start="2024-09-08T17:00"), ko) is None, "no reading near kickoff"


def test_one_archive_request_per_venue_per_season():
    calls = []

    def fetch(lat, lon, start, end):
        calls.append((lat, lon, start, end))
        return _payload(start=f"{start}T00:00", hours=24 * 30)
    games = [{"game_id": str(i), "season": 2024, "kickoff": f"2024-09-{7 + 7 * i:02d}T19:30:00.000Z",
              "home": "UGA", "away": f"T{i}", "lat": 33.95, "lon": -83.37, "roofed": False}
             for i in range(3)]
    games.append({"game_id": "9", "season": 2024, "kickoff": "2024-09-14T19:30:00.000Z",
                  "home": "LSU", "away": "X", "lat": 29.95, "lon": -90.08, "roofed": True})
    got = CLI.college_weather(games, fetch=fetch, pause=0)
    assert calls == [(33.95, -83.37, "2024-09-07", "2024-09-22")], \
        ("one request for the outdoor venue's season, a day past its last game; none for the dome", calls)
    assert set(got) == {(2024, "0"), (2024, "1"), (2024, "2")}


def _season_of_games(step: float, seasons=(2022, 2023, 2024, 2025), teams=20, weeks=10):
    """A league whose teams carry 35 a game, ``step`` times that in rain."""
    games, weather, carries = [], {}, {}
    for s in seasons:
        for w in range(1, weeks + 1):
            for k in range(teams // 2):
                a, b = (k + w) % teams, (teams - 1 - k + w) % teams
                if a == b:
                    continue
                gid = f"{s}{w:02d}{k:02d}"
                games.append({"game_id": gid, "season": s, "kickoff": f"{s}-09-01T{w:02d}:00:00Z",
                              "home": f"T{a}", "away": f"T{b}", "lat": 30.0 + k, "lon": -90.0,
                              "roofed": False})
                rain = (hash((s, w, k)) % 5 == 0) and w >= 4
                weather[(s, gid)] = {"temp": 65.0, "wind": 4.0, "precip": "rain" if rain else None}
                for t, jig in ((f"T{a}", 1.0 + ((w * 7 + k) % 5 - 2) / 50.0),
                               (f"T{b}", 1.0 + ((w * 3 + k) % 5 - 2) / 50.0)):
                    carries[(s, gid, t)] = 35.0 * jig * (step if rain else 1.0)
    return games, weather, carries


def test_college_carries_are_measured_the_nfls_way():
    games, weather, carries = _season_of_games(1.15)
    got = F.college_measure(games, weather, carries)
    v = got["rain"]
    assert abs(v["mult"] - 1.15) < 0.02 and F.clears(v), v
    assert set(v["per"]) == {2022, 2023, 2024, 2025}
    assert CLI.college_verdict(v, 1.069).startswith("DIFFERS"), "×1.15 clears and is not the NFL's"
    games, weather, carries = _season_of_games(1.07)
    v = F.college_measure(games, weather, carries)["rain"]
    assert CLI.college_verdict(v, 1.069).startswith("AGREES"), v


def test_the_verdict_says_what_college_can_and_cannot_say():
    weak = {"mult": 1.05, "se": 0.04, "n": 60, "per": {2022: 1.1, 2023: 0.98, 2024: 1.07}}
    assert CLI.college_verdict(weak, 1.069).startswith("NOT ENOUGH")
    against = {"mult": 0.90, "se": 0.03, "n": 80, "per": {2022: 0.9, 2023: 0.88, 2024: 0.93}}
    assert CLI.college_verdict(against, 1.069).startswith("DIFFERS"), "a clear fall is its own finding"
    soft = {"mult": 0.97, "se": 0.04, "n": 80, "per": {2022: 0.99, 2023: 0.95, 2024: 1.02}}
    assert CLI.college_verdict(soft, 1.069).startswith("CONTRADICTS")
    assert CLI.college_verdict(None, 1.069).startswith("TOO FEW")


def test_the_report_names_what_it_read_and_ends_on_the_verdict():
    games, weather, carries = _season_of_games(1.07)
    lines = CLI.college_report(games=games, weather=weather, carries=carries)
    assert lines[0].startswith("college 2022-2025: ") and "wet" in lines[0], lines[0]
    assert any(ln.strip().startswith("rain ") and "×" in ln for ln in lines), lines
    assert lines[-1].split(":")[0] in ("AGREES", "DIFFERS", "NOT ENOUGH", "CONTRADICTS", "TOO FEW"), lines[-1]


def test_the_box_logs_are_read_by_game_and_team():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, "
                 "player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        ("cfb", 2024, "2024-09-07", "401000001", "A", "UGA", "BAMA", "RB", 1, "rush_att", 18),
        ("cfb", 2024, "2024-09-07", "401000001", "B", "UGA", "BAMA", "QB", 1, "rush_att", 9),
        ("cfb", 2024, "2024-09-07", "401000001", "A", "UGA", "BAMA", "RB", 1, "rush_yds", 120),
        ("nfl", 2024, "001", "x", "C", "BAL", "JAX", "RB", 1, "rush_att", 25)])
    assert CLI.college_carries(conn, [2024]) == {(2024, "401000001", "UGA"): 27.0}


def test_the_command_is_in_the_runbook_and_the_catchup():
    cmd = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 wxfit.py --college"
    assert cmd in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert cmd in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8")
    assert "--college" in (ROOT / "wxfit.py").read_text(encoding="utf-8").split('"""')[1]


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - fails} tests passed." if not fails else f"\n{fails} of {len(fns)} failed.")
    sys.exit(1 if fails else 0)
