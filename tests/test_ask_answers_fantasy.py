"""Ask answers fantasy football: start/sit, projected points, matchups vs position.

Ethan, 2026-09-23: "users should be able too ask the Qellys chat about
fantasy questions too, like best usage starters or anything else someone
would ask, idk fantasy that much so idk".

The fantasy desk (usage, waivers, streamers, trending, ranks) was already a
tool. What a manager asks most was not: "who do I start, X or Y?" and
"who gives up the most to tight ends?". Two tools answer them from our own
data (engine/askbot.fantasy_points, defense_vs_position), and the prompt
says start/sit advice is welcome and is not a bet.
"""
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as AB                                  # noqa: E402
from engine import db as _db                                     # noqa: E402

_TMP = Path(tempfile.mkdtemp())
os.environ["QB_ASK_WEB_DAILY"] = "0"
# The roster the fantasy lookup reads is the box's own published file;
# a test reads an empty folder instead (and one test writes its own).
from engine import statlogs as _SL                               # noqa: E402
_SL.ROSTER_DIR = str(_TMP)
_SL._ROSTER.clear()


def _logs():
    rows = []

    def add(player, team, opp, pos, wk, **m):
        for market, v in m.items():
            rows.append({"sport": "nfl", "season": 2026, "period": f"{wk:03d}", "game_id": f"{team}-{wk:03d}",
                         "player": player, "team": team, "opponent": opp, "position": pos, "home": 1,
                         "market": market, "value": v})
    for wk, opp in ((1, "DET"), (2, "CHI"), (3, "DET"), (4, "GB")):
        add("Chris Olave", "NO", opp, "WR", wk, rec_yds=80.0, receptions=6.0, rec_td=0.5, rush_yds=0.0,
            fp_ppr=6 + 8 + 3 + (6 if wk % 2 else 0))
        add("Juwan Johnson", "NO", opp, "TE", wk, rec_yds=40.0, receptions=4.0, rec_td=0.25, fp_ppr=9.5)
        add("Josh Allen", "BUF", "MIA", "QB", wk, pass_yds=250.0, pass_td=2.0, rush_yds=30.0, rush_td=0.5,
            fp_ppr=24.0)
        add("Keenan Allen", "CHI", "MIN", "WR", wk, rec_yds=50.0, receptions=5.0, rec_td=0.0, fp_ppr=10.0)
        add("Malachi Fields", "NYG", "DAL", "WR", wk, rec_yds=28.0, receptions=3.0, rec_td=0.0, fp_ppr=5.8)
        # what each defence gave up to tight ends: DET a lot, GB little
        add(f"TE {opp}", "XX", opp, "TE", wk, rec_yds={"DET": 90.0, "CHI": 50.0, "GB": 20.0}[opp],
            receptions=5.0, rec_td=1.0 if opp == "DET" else 0.0,
            fp_ppr={"DET": 20.0, "CHI": 10.0, "GB": 4.0}[opp])
    return rows


conn = _db.connect(str(_TMP / "history.db"))
_db.upsert_player_logs(conn, _logs())
conn.close()
AB.HISTORY_DB = str(_TMP / "history.db")
# THE WEEK'S FILE (engine/fantasyweek) is read from the paid folder: an
# empty one here, so every test reads the board-and-logs path whatever the
# machine running it holds, unless it writes a week of its own.
AB.PAID_DIR = str(_TMP)


def _row(player, market, projection, **kw):
    return {"player": player, "team": "NO", "opponent": "DET", "position": "WR", "market": market,
            "projection": projection, **kw}


BOARDS = {"nfl": {
    "recommendations": [
        _row("Chris Olave", "rec_yds", 90.0, matchup_card={"text": "DET allow 190 receiving yards to WRs a game"}),
        _row("Chris Olave", "receptions", 7.0),
        _row("Juwan Johnson", "receptions", 5.0, position="TE"),
    ],
    "longshot_watch": [_row("Chris Olave", "anytime_td", None, model_prob=0.40)],
}}


def test_start_sit_puts_the_higher_projection_first_and_says_where_each_number_came_from():
    got = AB.run_tool("fantasy_points", {"players": ["Juwan Johnson", "Chris Olave"]}, BOARDS)
    assert got["scoring"] == "PPR" and [p["player"] for p in got["players"]] == ["Chris Olave", "Juwan Johnson"]
    olave = got["players"][0]
    lam = -math.log(1 - 0.40)
    assert olave["projected_points"] == round(90 * 0.1 + 7 * 1 + lam * 6, 1), "board stats plus expected TDs"
    assert olave["parts"]["rec_yds"] == {"value": 90.0, "from": "this week"}
    assert olave["touchdowns"]["from"] == "our touchdown model, 40% to score"
    assert olave["matchup"].startswith("DET allow") and olave["opponent"] == "DET"
    assert olave["season"]["games"] == 4 and olave["season"]["weekly_swing_ppr"] == 3.0, "boom-or-bust, measured"
    tj = got["players"][1]
    assert tj["parts"]["rec_yds"] == {"value": 40.0, "from": "season average"}, "not on the board in that market"
    assert tj["touchdowns"] == {"expected": 0.25, "from": "his season rate"}
    assert "interceptions" in got["how"]


def test_scoring_changes_the_catch_value_and_a_qb_scores_his_passing():
    half = AB.fantasy_points(BOARDS, ["Chris Olave"], "half")["players"][0]["projected_points"]
    ppr = AB.fantasy_points(BOARDS, ["Chris Olave"], "ppr")["players"][0]["projected_points"]
    std = AB.fantasy_points(BOARDS, ["Chris Olave"], "standard")["players"][0]["projected_points"]
    assert round(ppr - half, 1) == 3.5 and round(ppr - std, 1) == 7.0
    qb = AB.fantasy_points(BOARDS, ["Josh Allen"])["players"][0]
    assert qb["position"] == "QB" and set(qb["parts"]) == {"pass_yds", "pass_td", "rush_yds"}
    assert qb["projected_points"] == round(250 * 0.04 + 2 * 4 + 30 * 0.1 + 0.5 * 6, 1)
    assert qb["note"] == "not on this week's board: season averages only"
    assert AB.fantasy_points(BOARDS, ["Chris Olave"], "dynasty")["error"].startswith("scoring is one of")


def test_a_shared_surname_is_asked_about_not_guessed():
    got = AB.fantasy_points(BOARDS, ["Allen", "Olave"])
    assert [p["player"] for p in got["players"]] == ["Chris Olave"]
    assert got["unsure"]["Allen"] == ["Josh Allen", "Keenan Allen"]
    assert AB.fantasy_points(BOARDS, ["Nobody Atall"])["found"] is False


def test_a_misspelt_name_is_the_player_it_nearly_spells():
    """Ethan, 2026-09-23: "Who do i start in fantasy malachi fields or malik
    nabers" → "I can't find a 'Malachi Field'". The Players page's own
    forgiving match, best tier only."""
    got = AB.fantasy_points(BOARDS, ["Malachi Field", "chris olav"])
    assert [p["player"] for p in got["players"]] == ["Chris Olave", "Malachi Fields"], got
    assert "unsure" not in got


def test_a_rostered_player_with_no_game_is_known_not_unheard_of():
    import json as _json
    from engine import statlogs as SL
    d = Path(tempfile.mkdtemp())
    (d / "rosters_nfl.json").write_text(_json.dumps({"teams": {"TEN": {"players": [
        {"player": "Carnell Tate", "position": "WR"}]}}}))
    was, SL.ROSTER_DIR = SL.ROSTER_DIR, str(d)
    SL._ROSTER.clear()
    try:
        got = AB.fantasy_points(BOARDS, ["carnell tate"])
    finally:
        SL.ROSTER_DIR = was
        SL._ROSTER.clear()
    assert got["found"] is False
    assert got["unsure"]["carnell tate"] == \
        "Carnell Tate (TEN WR) is on the roster with no NFL game logged yet: nothing to project from"


def test_this_week_s_file_answers_first_and_says_so():
    """Ethan, 2026-10-22: the board's offence, defence and game-script data
    "wrapped into" fantasy. Ask answers a player on this week's file exactly
    as the Fantasy page and the league desks score him: at the chance he
    plays, with the range, the matchup and why; a bye is zero."""
    import datetime as _dt
    import json as _json
    from engine import fantasyweek as FW
    soon = (_dt.date.today() + _dt.timedelta(days=3)).isoformat()
    rows = [_row("Chris Olave", "rec_yds", 90.0, injury_status="Questionable",
                 matchup_card={"rank": 2, "of": 32, "text": "DET allow 190 receiving yards to WRs a game"}),
            _row("Chris Olave", "receptions", 7.0)]
    doc = {"week": 8, "players": FW.project_players(rows, {("NO", "Chris Olave"): {"prob": 0.40}}),
           "byes": ["BUF"], "listed": {}, "teams": {"NO": {"date": soon}}, "measured": FW.MEASURED}
    d = Path(tempfile.mkdtemp())
    (d / FW.FILE).write_text(_json.dumps(doc))
    was, AB.PAID_DIR = AB.PAID_DIR, str(d)
    try:
        got = AB.fantasy_points(BOARDS, ["Chris Olave", "Josh Allen", "Juwan Johnson"])
        stale = dict(doc, teams={"NO": {"date": "2020-01-01"}})
        (d / FW.FILE).write_text(_json.dumps(stale))
        old = AB.fantasy_points(BOARDS, ["Chris Olave"])
    finally:
        AB.PAID_DIR = was
    by = {p["player"]: p for p in got["players"]}
    olave = by["Chris Olave"]
    q = FW.FALLBACK_PLAY["Questionable|*"]
    ppr = 90 * 0.1 + 7 + -math.log(1 - 0.40) * 6
    assert olave["if_he_plays"] == round(ppr, 1) and olave["chance_to_play"] == round(q, 2)
    assert olave["projected_points"] == round(ppr * q, 1), "counted at the chance he plays"
    assert olave["injury"] == "Questionable" and olave["matchup_grade"] == "soft"
    assert olave["eight_in_ten_weeks_ppr"] == list(FW.range_for("WR", round(ppr, 2)))
    assert olave["parts"]["rec_yds"] == {"value": 90.0, "from": "this week's board"}
    assert olave["touchdowns"]["from"] == "our touchdown model, 40% to score a touchdown"
    assert olave["season"]["games"] == 4, "his season rides along"
    allen = by["Josh Allen"]
    assert allen["projected_points"] == 0.0 and allen["note"] == "BUF are on a bye this week"
    assert by["Juwan Johnson"]["parts"]["rec_yds"]["from"] == "season average", "not on the week: the old path"
    assert "this week's file" in got["how"] and got["measured"].startswith("walked forward on 2023-2025")
    assert old["players"][0]["parts"]["rec_yds"]["from"] == "this week", "a finished week is not read"


def test_defences_against_a_position_are_ranked_from_the_logs():
    got = AB.run_tool("defense_vs_position", {"position": "te", "team": "Packers"}, BOARDS)
    assert got["position"] == "TE" and got["ranked"] == "1 = gives up the most"
    top = got["most_generous"][0]
    assert top["defense"] == "DET" and top["rank"] == 1 and top["games"] == 2
    assert top["ppr_allowed"] == round((20 + 9.5 + 20 + 9.5) / 2, 1), "every tight end who played them, per game"
    assert got["stingiest"][0]["defense"] == "GB" and got["team"]["defense"] == "GB"
    assert AB.defense_vs_position("K")["error"].startswith("position is one of")


def test_the_prompt_welcomes_fantasy_and_the_chips_name_the_lookup():
    system = " ".join(AB.SYSTEM.split())
    assert "Fantasy football questions are welcome" in system
    assert "For a start/sit you may say who you would start" in system and "That is fantasy advice, not a bet" in system
    assert "Never tell the reader to bet or how much" in system, "betting advice is still refused"
    got = AB.fantasy_points(BOARDS, ["Chris Olave", "Juwan Johnson"])
    assert AB.tool_source("fantasy_points", {}, got)["label"] == "Fantasy projections, Chris Olave, Juwan Johnson"
    assert AB.tool_source("defense_vs_position", {}, AB.defense_vs_position("TE"))["label"] == \
        "Defences vs TEs, 2025-2026", "a young season reads last season with it, and says so"


def test_the_room_says_it_does_fantasy():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _app import app_js
    app = app_js()                       # app.js and the rooms it loads (Ask: js/ask.js)
    assert "<p>Fantasy too: who to start, projected points, waiver pickups and the matchups to target.</p>" in app


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
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
