"""Each team's own game count on the game page's scan (18 November 2026).

IND@HOU's matchup scan said "This season (9 games)" at the top, "This
season, as played (10 games)" over the raw numbers and "After 9 games" in
the note under them. The Colts had played 10 and the Texans 9 (a bye), and
each line took a different one: the smaller, the larger, the home side's.
Under it, the play-by-play's sums went over the final scores' games:
Monday night's LAC@BAL score is filed that night and its plays a night or
two later, so both teams' rushing yards and sacks allowed a game were 9
games of plays over 10 games (8 over 9 for the Chargers). What these hold:

  * one count when the two match, each team's when they do not, the same
    way on the top line and over the raw numbers, in football and hockey;
  * the split is said once, at the top, as a range when the teams differ;
  * a play-by-play sum is divided by the play-by-play's own games.

    python3 tests/test_each_team_says_its_own_games.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, gamescan                                # noqa: E402
from _app import app_js                                         # noqa: E402

STUBS = """
const NICK = {IND: "Colts", HOU: "Texans", LAK: "Kings", BOS: "Bruins"};
const teamName = (a) => NICK[a] || a;
const escapeHtml = (s) => String(s == null ? "" : s);
const ordinal = (n) => n + "th";
const SEASON_NUMBER_ROWS = [["pts_for", "Points scored a game", "n"], ["sacks", "Sacks a game", "n"]];
const state = {data: {}};
const scanReadHTML = () => "";
"""


def _fn(src, name):
    i = src.index(f"\nfunction {name}(") + 1
    j = src.find("\nfunction ", i + 10)
    k = src.find("\nconst ", i + 10)
    return src[i:min(x for x in (j, k) if x != -1)]


def _run(names, body):
    node = shutil.which("node")
    if not node:
        return None
    src = app_js()
    prog = STUBS + "\n".join(_fn(src, n) for n in names) + "\n" + body
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _units(ga, gh, ba, bh):
    return {"units": {"IND": {"games": ga, "blend": ba}, "HOU": {"games": gh, "blend": bh}}}


def test_the_top_line_says_each_teams_games_and_the_split_once():
    got = _run(["gamesEach", "pctRange", "tapeBasis"], "console.log(JSON.stringify([" + ", ".join(
        f"tapeBasis({json.dumps(_units(*a))}, 'IND', 'HOU')" for a in (
            (10, 9, 0.62, 0.6), (9, 9, 0.6, 0.6), (0, 0, None, None), (12, 12, 1.0, 1.0), (13, 12, 1.0, 1.0))
    ) + "]));")
    if got is None:
        return
    differ, same, none, only, only_differ = got
    assert differ == ("This season (Colts 10 games, Texans 9) with last season filling in — "
                      "38–40% of each rank is last season"), differ
    assert same == "This season (9 games) with last season filling in — 40% of each rank is last season", same
    assert none == "Last season’s numbers — no games yet this season", none
    assert only == "This season only · 12 games each", only
    assert only_differ == "This season only (Colts 13 games, Texans 12)", only_differ


def test_college_says_the_split_not_a_count_made_of_plays():
    # cfb_ratings' games are plays over 70: "8 games" for teams with 11.
    ratings = gamescan.cfb_ratings({"OHIO": {"plays": 560.0, "off": {"overall": 0.2}, "def": {"overall": 0.1}},
                                    "BALL": {"plays": 575.0, "off": {"overall": 0.1}, "def": {"overall": 0.2}}},
                                   {"OHIO": {"plays": 800.0, "off": {"overall": 0.1}, "def": {"overall": 0.1}},
                                    "BALL": {"plays": 800.0, "off": {"overall": 0.1}, "def": {"overall": 0.1}}})
    assert ratings["OHIO"]["basis"] == "plays" and ratings["OHIO"]["games"] == 8
    scan = {"units": {t: {k: ratings[t][k] for k in ("games", "blend", "basis")} for t in ("BALL", "OHIO")}}
    got = _run(["gamesEach", "pctRange", "tapeBasis"],
               f"console.log(JSON.stringify(tapeBasis({json.dumps(scan)}, 'BALL', 'OHIO')));")
    if got is None:
        return
    assert "game" not in got and got.startswith("This season with last season filling in — "), got


def test_the_team_shapes_line_counts_in_words():
    body = _fn(app_js(), "renderGamePage")
    assert "const plural =" not in body, "app.js's plural forms the word; a local copy printed '9 undefined'"
    got = _run(["pluralWord", "plural"], "console.log(JSON.stringify([plural(9, 'game'), plural(1, 'game')]));")
    if got is not None:
        assert got == ["9 games", "1 game"], got


def test_the_raw_numbers_say_each_teams_games_the_same_way():
    scan = {"numbers": {"IND": {"games": 10, "pts_for": {"value": 20.8, "rank": 23}},
                        "HOU": {"games": 9, "pts_for": {"value": 25.9, "rank": 9}}}}
    same = {"numbers": {"IND": {"games": 9, "pts_for": {"value": 20.8, "rank": 23}},
                        "HOU": {"games": 9, "pts_for": {"value": 25.9, "rank": 9}}}}
    got = _run(["gamesEach", "seasonNumbersHTML"],
               f"console.log(JSON.stringify([seasonNumbersHTML({json.dumps(scan)}, 'IND', 'HOU'), "
               f"seasonNumbersHTML({json.dumps(same)}, 'IND', 'HOU')]));")
    if got is None:
        return
    assert "This season, as played (Colts 10 games, Texans 9) — raw numbers, league rank" in got[0], got[0]
    assert "This season, as played (9 games) — raw numbers, league rank" in got[1], got[1]


def test_the_note_under_the_ranks_does_not_say_the_split_again():
    src = _fn(app_js(), "matchupScanHTML")
    assert "u0.games} game" not in src and "the big number is" not in src
    assert "The big number mixes in last season by the share above" in src


def test_hockey_says_each_teams_games_and_the_split():
    def game(ga, gh, wa, wh):
        return {"away": "LAK", "home": "BOS", "nhl_tape": {"teams": 32, "sides": {
            "LAK": {"gp_season": ga, "season_weight": wa}, "BOS": {"gp_season": gh, "season_weight": wh}}}}
    got = _run(["gamesEach", "pctRange", "nhlScanHTML"],
               "console.log(JSON.stringify([" + ", ".join(
                   f"nhlScanHTML({json.dumps(game(*a))})" for a in ((18, 19, 0.5, 0.5), (19, 19, 0.5, 0.5),
                                                                   (18, 19, 0.48, 0.5))) + "]));")
    if got is None:
        return
    differ, same, split = got
    assert ("After 18 games for the Kings and 19 for the Bruins this season, team strength is 50% this season "
            "and 50% last season") in differ, differ
    assert "After 19 games this season, team strength is 50% this season and 50% last season" in same, same
    assert "team strength is 48–50% this season and 50–52% last season" in split, split


def test_a_play_by_play_sum_goes_over_the_play_by_plays_games():
    conn = db.connect(":memory:")
    # Two finals for BAL, and the play-by-play of only the first: Monday
    # night's plays are not in yet.
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES ('nfl', 2026, ?, ?, ?, ?, ?, ?)",
                     [("009", "JAX@BAL", "BAL", "JAX", 10, 33), ("010", "LAC@BAL", "BAL", "LAC", 20, 23)])
    db.upsert_team_units(conn, [dict(sport="nfl", season=2026, period="009", team="BAL", side="def", opp="JAX",
                                     plays=62, rushes=30, rush_yds=150, sacks=4, third_att=12, third_conv=5,
                                     rz_drives=4, rz_tds=3),
                                dict(sport="nfl", season=2026, period="009", team="BAL", side="off", opp="JAX",
                                     plays=58, rushes=22, third_att=13, third_conv=4, rz_drives=2, rz_tds=1)])
    bal = gamescan.season_numbers(conn, 2026)["BAL"]
    assert bal["games"] == 2, "the games count is the final scores'"
    assert bal["pts_against"]["value"] == 28.0, "points go over the finals"
    assert bal["rush_allowed"]["value"] == 150.0, bal["rush_allowed"]
    assert bal["sacks"]["value"] == 4.0, bal["sacks"]


def test_a_league_ranks_only_its_own_clubs():
    # "Rank of 31" in a 30-team NBA: a side outside the league with three
    # nights on file was rated and ranked. WNBA rows keep ESPN's own codes.
    from engine.nba import teams as T

    def nights(pairs, days=3):
        rows = []
        for d in range(days):
            day = f"2026-10-{10 + d:02d}"
            for a, b in pairs:
                for team, opp in ((a, b), (b, a)):
                    for k in T.BOX:
                        rows.append((day, team, opp, k, 240.0 if k == "min" else 10.0 + d))
        return rows

    nba = T.build(nights([("BOS", "RMD"), ("NYK", "TOR")]), [], "nba")
    assert set(nba["teams"]) == {"BOS", "NYK", "TOR"} and nba["n"] == 3, sorted(nba["teams"])
    wnba = T.build(nights([("LV", "NY")]), [], "wnba")
    assert set(wnba["teams"]) == {"LV", "NY"}, sorted(wnba["teams"])
    # College ranks Division I's own: "Rank of 407" in a 365-school division
    # (2026-11-18). A small school (ESPN's id for a code) keeps its numbers, unranked.
    cbb = T.build(nights([("DUKE", "UNC"), ("BAY", "espn:2918")]), [], "cbb")
    assert set(cbb["teams"]) == {"DUKE", "UNC", "BAY", "espn:2918"}, sorted(cbb["teams"])
    assert cbb["n"] == 3, "ranked among Division I's schools only"
    assert cbb["teams"]["espn:2918"]["ranks"] == {} and cbb["teams"]["espn:2918"].get("pts") is not None
    assert max(r for t in ("DUKE", "UNC", "BAY") for r in cbb["teams"][t]["ranks"].values()) <= 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
