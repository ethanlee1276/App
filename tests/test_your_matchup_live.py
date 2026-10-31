"""Your matchup, live, and fantasy points on the game pages.

Ethan, 2026-10-27, after round one of the Fantasy room: the next on the list
was "your matchup live (points as games happen)" and "fantasy points on the
live game pages". engine/fantasy_live reads Sleeper's own points for the
lineup actually set, projects what is left from each starter's game clock,
and gives the win chance from there; the game page adds up each player's
fantasy points off the box score it already draws.

What these hold: the share of a game left from the quarter and the clock;
a starter yet to play counts at his projection, one in a game at his points
plus his projection for the time left, one whose game is over at what he
scored; the spread shrinks the same way; nothing is drawn before a kickoff;
the scoreboard's word beats the kickoff time's; the desk reads the board a
minute fresh while a game is on; the card refreshes itself and nothing
else; the game page's points are the site's own PPR, word for word.

Run directly: `python3 tests/test_your_matchup_live.py`
"""
import datetime as _dt
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import fantasy_live as FL                            # noqa: E402
from engine import fantasyweek as FW                             # noqa: E402

WEEK_JS = (ROOT / "web" / "js" / "fantasyweek.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "fantasy.css").read_text(encoding="utf-8")
DCSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")

PLAYERS = {"1": {"first_name": "QB", "last_name": "Mine", "position": "QB", "team": "PHI"},
           "2": {"first_name": "RB", "last_name": "Mine", "position": "RB", "team": "MIA"},
           "3": {"first_name": "WR", "last_name": "Mine", "position": "WR", "team": "LAR"},
           "11": {"first_name": "QB", "last_name": "Theirs", "position": "QB", "team": "BAL"},
           "12": {"first_name": "RB", "last_name": "Theirs", "position": "RB", "team": "CIN"},
           "13": {"first_name": "WR", "last_name": "Theirs", "position": "WR", "team": "KC"}}
SLOTS = ["QB", "RB", "WR"]
PROJ = {"QB Mine": 20.0, "RB Mine": 12.0, "WR Mine": 15.0, "QB Theirs": 22.0, "RB Theirs": 14.0, "WR Theirs": 10.0}
SDS = {k: 6.0 for k in PROJ}


def _board(mine=None, theirs=None):
    return [{"roster_id": 1, "matchup_id": 4, "starters": ["1", "2", "3"], "players_points": mine or {}},
            {"roster_id": 2, "matchup_id": 4, "starters": ["11", "12", "13"], "players_points": theirs or {}},
            {"roster_id": 3, "matchup_id": 5, "starters": [], "players_points": {}}]


# --- the clock ---------------------------------------------------------------------------------

def test_the_share_of_the_game_left():
    assert FL.frac_left("Q1", "15:00") == 1.0
    assert abs(FL.frac_left("Q3", "5:41") - (15 * 60 + 341) / 3600) < 1e-9
    assert FL.frac_left("Q4", "0:00") == 0.0 and FL.frac_left("Q5", "4:00") == 0.01
    assert FL.frac_left("Half", "") == 0.5 and FL.frac_left("", "") == 0.0
    assert FL.frac_left("Q2", "") == 0.5, "a break at the end of the quarter"


def test_the_scoreboard_beats_the_kickoff_time():
    d = Path(tempfile.mkdtemp())
    try:
        (d / "live_nfl.json").write_text(json.dumps({"games": [
            {"home": "LAR", "away": "SF", "live": {"state": "live", "period": "Q2", "clock": "7:30"}},
            {"home": "KC", "away": "BUF", "live": {"state": "final"}},
            {"home": "DAL", "away": "NYG", "live": {"state": "pre"}}]}))
        board = FL.scoreboard(d / "live_nfl.json")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert board["LAR"]["state"] == "live" and board["LAR"]["clock"] == "Q2 7:30"
    assert abs(board["SF"]["frac_left"] - (2 * 900 + 450) / 3600) < 1e-9
    assert board["KC"] == {"state": "final", "frac_left": 0.0, "clock": "Final"}
    assert board["DAL"]["state"] == "pre" and board["DAL"]["frac_left"] == 1.0
    week = {"teams": {"LA": {"date": "2026-11-01", "kickoff": "16:25"}, "CIN": {"date": "2026-11-01", "kickoff": "13:00"},
                      "MIA": {"date": "2026-10-29", "kickoff": "20:15"}, "NYJ": {"date": "2026-11-02", "kickoff": "20:15"}}}
    now = _dt.datetime(2026, 11, 1, 14, 0)
    got = FL.states(week, board, now=now)
    assert got["LA"]["state"] == "live", "the scoreboard's LAR is the week's LA"
    assert got["CIN"]["state"] == "live" and abs(got["CIN"]["frac_left"] - (1 - 60 / FL.WALL_MIN)) < 1e-9
    assert got["MIA"]["state"] == "final" and got["NYJ"]["state"] == "pre"


# --- the matchup -------------------------------------------------------------------------------

def test_nothing_before_a_kickoff():
    game = {"PHI": {"state": "pre", "frac_left": 1.0, "clock": "Sun 1:00 PM ET"}}
    assert FL.matchup(_board(), 1, PLAYERS, SLOTS, PROJ, SDS, game) is None


def test_points_so_far_the_rest_projected_and_the_chance():
    game = {"PHI": {"state": "final", "frac_left": 0.0, "clock": "Final"},
            "MIA": {"state": "live", "frac_left": 0.5, "clock": "Q3 15:00"},
            "BAL": {"state": "final", "frac_left": 0.0, "clock": "Final"},
            "CIN": {"state": "live", "frac_left": 0.25, "clock": "Q4 15:00"}}
    got = FL.matchup(_board({"1": 24.0, "2": 7.0}, {"11": 18.0, "12": 9.0}), 1, PLAYERS, SLOTS, PROJ, SDS, game)
    me, them = got["me"], got["them"]
    assert me["points"] == 31.0 and them["points"] == 27.0
    assert me["projected"] == round(24.0 + (7.0 + 12.0 * 0.5) + 15.0, 1), "final, live, not started"
    assert them["projected"] == round(18.0 + (9.0 + 14.0 * 0.25) + 10.0, 1)
    var = (36 * 0.5 + 36) + (36 * 0.25 + 36)
    assert abs(got["win_prob"] - round(0.5 * (1 + math.erf((me["projected"] - them["projected"]) / math.sqrt(var) / math.sqrt(2))), 4)) < 1e-4
    assert got["in_progress"] and not got["done"] and got["opponent_roster_id"] == 2
    rows = {p["player"]: p for p in me["players"]}
    assert rows["RB Mine"]["state"] == "live" and rows["RB Mine"]["clock"] == "Q3 15:00" and rows["RB Mine"]["slot"] == "RB"
    assert rows["WR Mine"]["state"] == "pre", "a team the clock does not know has not kicked off"


def test_all_final_is_decided():
    game = {t: {"state": "final", "frac_left": 0.0, "clock": "Final"} for t in ("PHI", "MIA", "LA", "BAL", "CIN", "KC")}
    got = FL.matchup(_board({"1": 20, "2": 10, "3": 9}, {"11": 15, "12": 8, "13": 5}), 1, PLAYERS, SLOTS, PROJ, SDS, game)
    assert got["done"] and not got["in_progress"] and got["win_prob"] == 1.0
    assert got["me"]["projected"] == got["me"]["points"] == 39.0


def test_an_empty_slot_and_no_opponent():
    rows = [{"roster_id": 1, "matchup_id": 9, "starters": ["1", "0", "3"], "players_points": {"1": 5.0}}]
    game = {"PHI": {"state": "live", "frac_left": 0.5, "clock": "Q3 15:00"}}
    got = FL.matchup(rows, 1, PLAYERS, SLOTS, PROJ, SDS, game)
    assert got["them"] is None and got["win_prob"] is None
    assert got["me"]["players"][1]["state"] == "empty" and got["me"]["players"][1]["player"] is None
    assert FL.matchup([{"roster_id": 1, "matchup_id": None, "starters": ["1"]}], 1, PLAYERS, SLOTS, PROJ, SDS, game) is None


def test_projections_are_the_league_s_scoring_with_the_spread_scaled():
    means = {"WR One": {"position": "WR", "fp_ppr": 15.0, "receptions": 6.0, "rec_yds": 70.0, "_sd": 6.0}}
    proj, sds = FL.projections(["WR One", "Nobody"], means, {"rec": 0.5})
    assert proj == {"WR One": 12.0} and abs(sds["WR One"] - 6.0 * 12.0 / 15.0) < 1e-9


# --- the desk and the card ---------------------------------------------------------------------

def test_the_desk_reads_the_board_a_minute_fresh_while_a_game_is_on():
    desk = SERVER[SERVER.index("    def _league_desk(self, query: dict):"):SERVER.index("    def _league_desk_espn(")]
    assert 'ttl=60 if any(g["state"] == "live" for g in live_board.values()) else 300' in desk
    assert "fantasy_live.matchup(board, my_roster_id, players, slots, proj, sds," in desk
    assert 'out["live"] = live' in desk and "desk live:" in desk, "the desk never fails for it"


def test_the_card_leads_the_desk_and_refreshes_only_itself():
    assert 'host.innerHTML = (W ? W.live(d) + W.todo(d) : "") + ffH2HHTML(d)' in APP_JS
    i = WEEK_JS.index("function liveWatch(")
    body = WEEK_JS[i:WEEK_JS.index("\n  }\n", i)]
    assert 'host.querySelector(".ffl[data-ffl-on]")' in body and "now.outerHTML = liveHTML(d)" in body
    assert "document.hidden" in body, "a hidden tab does not ask"
    s = WEEK_JS.index("async function season(")
    assert "liveWatch(host, leagueId, userId, platform);" in WEEK_JS[s:s + 200]
    drawn = set(re.findall(r"\b(ffl-[a-z-]+)", WEEK_JS)) - {"ffl-on"}       # data-ffl-on is the refresh flag
    styled = set(re.findall(r"\.(ffl-[a-z-]+)", CSS))
    assert drawn and drawn <= styled, sorted(drawn - styled)


def _fn(src, name):
    i = src.index(f"function {name}(")
    i = src.rindex("\n", 0, i) + 1
    needle = "\n}\n" if src[i] in "fa" else "\n  }\n"
    return src[i:src.index(needle, i) + len(needle)]


def test_the_card_in_node():
    if not shutil.which("node"):
        return
    game = {"PHI": {"state": "final", "frac_left": 0.0, "clock": "Final"},
            "MIA": {"state": "live", "frac_left": 0.5, "clock": "Q3 15:00"}}
    live = FL.matchup(_board({"1": 24.0, "2": 7.0}, {"11": 18.0}), 1, PLAYERS, SLOTS, PROJ, SDS, game)
    live["opponent"] = "Danny"
    harness = ("const escapeHtml=(x)=>String(x==null?'':x);\n" + _fn(WEEK_JS, "liveHTML")
               + f"\nprocess.stdout.write(liveHTML({json.dumps({'week': 9, 'live': live})}));")
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    html = out.stdout
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert 'data-ffl-on="1"' in html and "Live Week 9 · vs Danny" in text
    assert "You 31.0 projected" in text and "Danny 18.0 projected" in text
    assert "QB Mine 24.0 Final QB QB Theirs" in text and "RB Mine 7.0 Q3 15:00" in text
    assert "% to win" in text


# --- fantasy points on the game page -----------------------------------------------------------

def test_the_game_page_adds_up_the_site_s_own_ppr_in_node():
    if not shutil.which("node"):
        return
    rows = [{"player": "Joe Burrow", "team": "CIN", "position": "QB",
             "stats": {"pass_yds": 268, "pass_td": 2, "pass_int": 1, "rush_yds": 21}},
            {"player": "Ja'Marr Chase", "team": "CIN", "position": "WR",
             "stats": {"receptions": 6, "rec_yds": 94, "rec_td": 1, "targets": 9}},
            {"player": "Blocker", "team": "CIN", "stats": {"carries": 1, "rush_yds": 0}}]
    harness = ("const escapeHtml=(x)=>String(x==null?'':x);const PBP_FOOTBALL=new Set(['nfl','cfb']);"
               "const teamMarkIn=()=>'';const pbpStat=(r,k)=>Number(((r||{}).stats||{})[k]);\n"
               + _fn(DETAIL, "pbpFantasyPts") + _fn(DETAIL, "pbpFantasyHTML")
               + f"\nconst rows={json.dumps(rows)};"
               "process.stdout.write(JSON.stringify([rows.map((r)=>pbpFantasyPts(r)),rows.map((r)=>pbpFantasyPts(r,0.5)),"
               "pbpFantasyHTML({players:rows,live:{state:'live'}},'nfl'),pbpFantasyHTML({players:rows},'nba')]));")
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    ppr, half, html, nba = json.loads(out.stdout)
    want = [FW.points({k: v for k, v in r["stats"].items() if k in FW.PPR}) for r in rows]
    assert [round(x, 2) for x in ppr] == want, (ppr, want)
    assert [round(x, 2) for x in half] == [FW.points({k: v for k, v in r["stats"].items() if k in FW.HALF}, FW.HALF)
                                           for r in rows]
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert text.startswith("Fantasy points so far PPR · half 1 Ja'Marr Chase WR 6-94, 1 TD 21.4 18.4 2 Joe Burrow QB")
    assert "Blocker" not in text, "no points, no row"
    assert nba == "", "football only"
    drawn = set(re.findall(r"\b(pbp-ff-[a-z-]+)", DETAIL))
    styled = set(re.findall(r"\.(pbp-ff-[a-z-]+)", DCSS))
    assert drawn and drawn <= styled, sorted(drawn - styled)
    assert "${pbpFantasyHTML(d, league)}${block(d.away)}${block(d.home)}" in DETAIL


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
