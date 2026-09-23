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
        # what each defence gave up to tight ends: DET a lot, GB little
        add(f"TE {opp}", "XX", opp, "TE", wk, rec_yds={"DET": 90.0, "CHI": 50.0, "GB": 20.0}[opp],
            receptions=5.0, rec_td=1.0 if opp == "DET" else 0.0,
            fp_ppr={"DET": 20.0, "CHI": 10.0, "GB": 4.0}[opp])
    return rows


conn = _db.connect(str(_TMP / "history.db"))
_db.upsert_player_logs(conn, _logs())
conn.close()
AB.HISTORY_DB = str(_TMP / "history.db")


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
    app = (ROOT / "web" / "js" / "app.js").read_text()
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
