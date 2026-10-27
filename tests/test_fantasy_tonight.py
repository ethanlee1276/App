"""Tonight's NBA, WNBA and NHL in fantasy points (engine/fantasy_daily).

Ethan, 2026-10-27: after the football Fantasy room, the next on the list was
"NBA and NHL fantasy from the props we already project". Each night's
basketball and hockey build adds up every priced player's projections in
daily-fantasy points, beside its board; the Fantasy room draws them in a
tab of their own while a slate is tonight's.

What these hold: the scoring is the common daily-fantasy scoring, sum for
sum; a part the board did not price is his season average and is named; a
hockey points line splits by his own goals to assists; goalies and players
ruled out are left out; early in a season the few games are steadied by
last season's; basketball's starter flag is not a position; the stat line
is the members' and the points are not; the builds call it and it never
stops one; the room draws tonight's slates only, with the file's own
scoring, and its tab is named for them.

Run directly: `python3 tests/test_fantasy_tonight.py`
"""
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import fantasy_daily as FD                          # noqa: E402
from engine import gate                                          # noqa: E402

WEEK_JS = (ROOT / "web" / "js" / "fantasyweek.js").read_text(encoding="utf-8")
FANTASY_JS = (ROOT / "web" / "js" / "fantasy.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "fantasy.css").read_text(encoding="utf-8")


def _rows(player, team, opp, **markets):
    return [{"player": player, "team": team, "opponent": opp, "market": m, "projection": v}
            for m, v in markets.items()]


GAMES = [{"home": "NYK", "away": "BOS", "date": "2026-10-27", "kickoff": "2026-10-27T23:30:00Z"}]


# --- the sum --------------------------------------------------------------------------------------

def test_basketball_is_the_daily_fantasy_sum():
    rows = _rows("Jay Star", "BOS", "NYK", pts=20, reb=10, ast=5, fg3m=2, stl=1, blk=1, tov=3)
    got = FD.project("nba", rows, {}, GAMES)
    assert len(got) == 1
    r = got[0]
    assert r["points"] == 20 + 12.5 + 7.5 + 1 + 2 + 2 - 1.5 == 43.5
    assert r["filled"] == [] and r["board"] == sorted(["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"])
    assert r["game"]["home"] == "NYK" and r["opponent"] == "NYK"
    assert FD.SCORING["wnba"] == FD.SCORING["nba"]


def test_a_part_the_board_did_not_price_is_his_season_average_and_named():
    rows = _rows("Jay Star", "BOS", "NYK", pts=20)
    means = {"Jay Star": {"reb": 8.0, "ast": 4.0, "stl": 1.0, "_games": 30, "position": ""}}
    r = FD.project("nba", rows, means, GAMES)[0]
    assert r["filled"] == ["reb", "ast", "stl"], "in the scoring's order"
    assert r["proj"]["reb"] == 8.0 and r["points"] == 20 + 10 + 6 + 2
    assert r["board"] == ["pts"]
    # Nothing priced at all: not drawn on season averages alone.
    assert FD.project("nba", [], means, GAMES) == []


def test_combination_markets_are_not_added_twice():
    rows = _rows("Jay Star", "BOS", "NYK", pts=20, pra=33)
    r = FD.project("nba", rows, {}, GAMES)[0]
    assert r["points"] == 20.0 and "pra" not in r["proj"]


def test_a_hockey_points_line_splits_by_his_own_goals_to_assists():
    rows = _rows("Sniper", "TOR", "MTL", points=1.0, sog=4.0)
    means = {"Sniper": {"goals": 0.6, "assists": 0.2, "_games": 40, "position": "R"}}
    r = FD.project("nhl", rows, means, [])[0]
    assert abs(r["proj"]["goals"] - 0.75) < 1e-9 and abs(r["proj"]["assists"] - 0.25) < 1e-9
    assert "points" not in r["proj"]
    assert abs(r["points"] - (8.5 * 0.75 + 5 * 0.25 + 1.5 * 4.0)) < 0.01
    # Too few games to say: the league's mix.
    few = FD.project("nhl", rows, {"Sniper": {"goals": 1.0, "assists": 0.0, "_games": 3}}, [])[0]
    assert abs(few["proj"]["goals"] - FD.GOAL_SHARE) < 1e-9
    # A board that prices goals itself keeps its own goals.
    own = FD.project("nhl", _rows("Sniper", "TOR", "MTL", points=1.0, goals=0.5), means, [])[0]
    assert own["proj"]["goals"] == 0.5


def test_goalies_and_players_ruled_out_are_left_out():
    rows = (_rows("Keeper", "TOR", "MTL", saves=28.0)
            + _rows("Skater", "TOR", "MTL", sog=3.0)
            + [{"player": "Hurt", "team": "TOR", "opponent": "MTL", "market": "sog", "projection": 3.0,
                "injury_status": "Out"},
               {"player": "Maybe", "team": "TOR", "opponent": "MTL", "market": "sog", "projection": 2.0,
                "injury_status": "Questionable"},
               {"player": "Netminder", "team": "TOR", "opponent": "MTL", "market": "sog", "projection": 0.1,
                "position": "G"}])
    got = {r["player"]: r for r in FD.project("nhl", rows, {}, [])}
    assert set(got) == {"Skater", "Maybe"}
    assert got["Maybe"]["status"] == "Questionable" and got["Maybe"]["points"] == 3.0, "at full value, said"


def test_hockey_positions_read_as_a_fantasy_game_lists_them_and_basketball_has_none():
    assert FD._pos("nhl", "L") == "W" and FD._pos("nhl", "rw") == "W" and FD._pos("nhl", "D") == "D"
    assert FD._pos("nba", "S") == "" and FD._pos("nba", "B") == "", "the starter flag is not a position"
    r = FD.project("nhl", _rows("Winger", "TOR", "MTL", sog=3.0), {"Winger": {"position": "W"}}, [])[0]
    assert r["position"] == "W"


def test_best_first():
    rows = _rows("Low", "BOS", "NYK", pts=10) + _rows("High", "NYK", "BOS", pts=30)
    assert [r["player"] for r in FD.project("nba", rows, {}, GAMES)] == ["High", "Low"]


# --- the season's averages ------------------------------------------------------------------------

def _logs(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, player TEXT, position TEXT,"
                 " market TEXT, value REAL)")
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?)", rows)
    return conn


def test_early_in_a_season_his_few_games_are_steadied_by_last_season():
    rows = [("nba", 2026, "Jay Star", "S", "stl", 0.0)] * 2 + [("nba", 2025, "Jay Star", "B", "stl", 2.0)] * 50
    rows += [("nba", 2026, "Rookie", "B", "stl", 1.0)] * 3
    rows += [("nba", 2025, "Gone", "S", "stl", 1.5)] * 20
    m = FD.season_means(_logs(rows), "nba")
    assert abs(m["Jay Star"]["stl"] - (2 * 0.0 + FD.PRIOR_GAMES * 2.0) / (2 + FD.PRIOR_GAMES)) < 1e-9
    assert m["Rookie"]["stl"] == 1.0, "no last season: this season's alone"
    assert m["Gone"]["stl"] == 1.5, "no games yet this season: last season's"
    assert m["Jay Star"]["position"] == "", "S and B are whether he started"
    assert m["Jay Star"]["_games"] == 52


def test_a_player_who_started_some_games_is_one_average_not_two():
    rows = [("nba", 2026, "Swing", "S", "pts", 20.0)] * 5 + [("nba", 2026, "Swing", "B", "pts", 10.0)] * 5
    m = FD.season_means(_logs(rows), "nba")
    assert m["Swing"]["pts"] == 15.0


def test_hockey_positions_come_from_the_logs():
    rows = [("nhl", 2026, "Winger", "L", "goals", 0.5)] * 12
    m = FD.season_means(_logs(rows), "nhl")
    assert m["Winger"]["position"] == "W" and m["Winger"]["_games"] == 12
    assert FD.season_means(None, "nhl") == {} and FD.season_means(_logs([]), "nhl") == {}


# --- the file, the gate, the builds --------------------------------------------------------------

def test_the_file_and_its_gate():
    result = {"date": "2026-10-27", "games": GAMES,
              "recommendations": _rows("Jay Star", "BOS", "NYK", pts=20, reb=10)}
    doc = FD.from_board("nba", result, {}, "2026-10-27T12:00:00")
    assert doc["sport"] == "nba" and doc["date"] == "2026-10-27" and doc["scoring"] == FD.SCORING["nba"]
    assert doc["games"] == [{"home": "NYK", "away": "BOS", "date": "2026-10-27", "kickoff": "2026-10-27T23:30:00Z"}]
    for name in FD.FILES.values():
        assert name in gate.KNOWN_BOARDS and name in gate.MIXED_FILES
        assert gate.ROW_PAID_KEYS_BY_FILE[name] == ("players", ("proj",))
    pub = gate.redact(doc, "fantasy_nba.json")
    row = pub["players"][0]
    assert "proj" not in row and row["points"] == doc["players"][0]["points"], "the points free, the stat line paid"
    assert pub["locked"]["players[].fields"] == 1 and "proj" in doc["players"][0], "the full copy keeps it"
    assert FD.summary_line(doc) == "Fantasy tonight (NBA): 1 player(s), top Jay Star 32.5".replace(" player(s)", " players")


def test_publish_writes_both_copies_beside_the_board():
    import os
    was = os.environ.get(gate.ENV_ENABLED)
    os.environ[gate.ENV_ENABLED] = "1"
    try:
        _publish_both()
    finally:
        if was is None:
            os.environ.pop(gate.ENV_ENABLED, None)
        else:
            os.environ[gate.ENV_ENABLED] = was


def _publish_both():
    with tempfile.TemporaryDirectory() as td:
        board = Path(td) / "web" / "data" / "nba.json"
        board.parent.mkdir(parents=True)
        doc = FD.from_board("nba", {"date": "2026-10-27", "games": GAMES,
                                    "recommendations": _rows("Jay Star", "BOS", "NYK", pts=20)}, {})
        public, full = FD.publish(doc, board)
        assert Path(public) == board.parent / "fantasy_nba.json"
        assert "proj" not in json.loads(Path(public).read_text())["players"][0]
        assert "proj" in json.loads(Path(full).read_text())["players"][0]
        assert FD.publish(doc, None) is None


def test_the_builds_call_it_and_it_never_stops_one():
    for f in ("nba_build.py", "nhl_build.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert "from engine import fantasy_daily as _fd" in src and "_fd.build(" in src, f
    assert FD.build("nba", None, None).startswith("Fantasy tonight (NBA)")
    assert FD.build("xfl", {}, None).startswith("Fantasy tonight (XFL) skipped: KeyError")


# --- the room -------------------------------------------------------------------------------------

def _night_js():
    i = WEEK_JS.index("  const NIGHT = {")
    return WEEK_JS[i:WEEK_JS.index("  /* What the desk's lineup was scored on", i)]


def _render(docs, then=""):
    stubs = ("const escapeHtml=(x)=>String(x==null?'':x);const escapeAttr=escapeHtml;"
             "const playerAvatar=(n)=>`<i class=face>${n}</i>`;const teamMark=()=>'';"
             "const icon=()=>'';const panelEmpty=(x)=>`<p>${x}</p>`;const SHOWN=30;"
             "const NBA_TEAMS={};const NHL_TEAMS={};const WNBA_TEAMS={};\n")
    harness = (stubs + _night_js() + f"\nconst docs={json.dumps(docs)};"
               + "process.stdout.write(JSON.stringify([daily(docs), dailyName(docs)" + then + "]));")
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def _doc(sport, date, rows, games=GAMES):
    return FD.from_board(sport, {"date": date, "games": games, "recommendations": rows}, {})


def test_the_room_in_node():
    if not shutil.which("node"):
        return
    nba = _doc("nba", "2099-01-01", _rows("Jay Star", "BOS", "NYK", pts=20, reb=10, stl=1)
               + _rows("Bench Guy", "NYK", "BOS", pts=8))
    nhl = _doc("nhl", "2099-01-01", _rows("Sniper", "TOR", "MTL", goals=0.5, sog=4.0)
               + _rows("Rearguard", "MTL", "TOR", blocks=2.0), [])
    nhl["players"][1]["position"] = "D"
    old = _doc("nba", "2000-01-01", _rows("Old", "BOS", "NYK", pts=20))
    html, name = _render([nba, nhl, old])
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert name == "NBA & NHL tonight"
    assert html.startswith('<div id="ff-tonight">')
    assert "Tonight’s NBA in fantasy points" in text and "2 players across 1 game" in text
    assert "Scoring: 1 a point, 0.5 a three, 1.25 a rebound, 1.5 an assist, 2 a steal, 2 a block and −0.5 a turnover." in text
    assert "1 Jay Star BOS · at NYK" in text and "34.5 FPTS" in text, "Boston is the away side"
    assert "2 Bench Guy NYK · vs BOS" in text
    assert "20.0 PTS 10.0 REB 1.0 STL" in text, "a member's stat line"
    assert "Old" not in text, "a past night's slate is not tonight's"
    assert 'data-ffnsport="nhl"' in html, "a switch for each sport with a slate"
    # Nothing tonight: no room, and no tab.
    assert _render([old]) == ["", " tonight"]
    # A reader without a plan: the points, the lock line, no stat line.
    pub = gate.redact(nba, "fantasy_nba.json")
    html, name = _render([pub])
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert name == "NBA tonight" and "34.5 FPTS" in text and "20.0 PTS" not in text
    assert "Members also see each player’s stat line" in text
    assert 'data-ffnsport' not in html, "one sport, no switch"


def test_hockey_draws_its_positions_and_says_what_it_does_not_count():
    if not shutil.which("node"):
        return
    rows = _rows("Sniper", "TOR", "MTL", goals=0.5, sog=4.0) + _rows("Rearguard", "MTL", "TOR", blocks=2.0)
    nhl = _doc("nhl", "2099-01-01", rows, [])
    nhl["players"][0]["position"], nhl["players"][1]["position"] = "C", "D"
    html, _ = _render([nhl])
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert 'data-ffnpos="C"' in html and 'data-ffnpos="D"' in html and 'data-ffnpos="W"' not in html
    assert "goalies are left out" in text and "8.5 a goal" in text
    assert "1 Sniper TOR · C · vs MTL" in text


def test_the_fantasy_page_draws_the_tab_and_styles_every_class():
    assert 'paidFetch(name)' in FANTASY_JS[FANTASY_JS.index("async function ffNightLoad("):]
    i = FANTASY_JS.index("async function ffNightLoad(")
    body = FANTASY_JS[i:FANTASY_JS.index("\n}\n", i)]
    assert all(f in body for f in FD.FILES.values())
    assert '["tonight", typeof QBWeek !== "undefined" ? QBWeek.dailyName(_ffNight) : "Tonight",' in FANTASY_JS
    assert "QBWeek.daily(_ffNight)" in FANTASY_JS and "QBWeek.dailyBind(host)" in FANTASY_JS
    assert "daily, dailyBind, dailyName" in WEEK_JS
    drawn = set(re.findall(r"\b(ffn-[a-z-]+)", WEEK_JS))
    styled = set(re.findall(r"\.(ffn-[a-z-]+)", CSS))
    assert drawn and drawn <= styled, sorted(drawn - styled)


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
