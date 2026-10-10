"""A pick tells its case: what backs it, what works against it, and what
our number is actually built on.

Ethan, 2026-10-04, on Ja'Marr Chase: "We're labeling him as a good
matchup, but then suggesting his under and giving him a low yard
projection", and on Jacksonville: "gives up seven most receiving yards to
wide receivers … pass defense ranks fifth … fourth fewest touchdowns to
wide receivers. But yet we're recommending a touchdown … it all feels like
it's fighting itself." And on the script: "these are two really good teams
… this could be more of a back and forth game and not a Bengals ahead
game."

Checks, one rule each: the scan's facts name the stat our number reads (a
receiver's yards read the defence's PASSING yards allowed) as in the
number and the receiver-only stats as shown, at any rank; the pick page
sorts the facts for THIS side, so an under lists a soft-to-receivers
defence under "works against it", marked shown-not-counted, and says why
the pick still stands; a close spread with a high total reads as a
back-and-forth game that backs a catch over and works against its under;
the corners he will see come with the yards each has allowed.

Run directly: `python3 tests/test_a_pick_tells_its_case.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                     # noqa: E402

#: Jacksonville as Ethan read it: soft to receivers' yards (7th-most), stingy
#: through the air overall (5th-fewest passing yards), few TDs to WRs.
JAX = {"qb_pass_yds": {"rank": 28, "of": 32, "pg": 196.0},
       "wr_rec_yds": {"rank": 7, "of": 32, "pg": 158.0},
       "wr_rec": {"rank": 15, "of": 32, "pg": 13.1},
       "wr_td": {"rank": 29, "of": 32, "pg": 0.6}}
CHASE_USAGE = {"games": 4, "tgt_share": 0.28, "targets_pg": 10.5, "snap_pct": 0.94}


def _facts():
    return G.read_facts("wr", "WR", "CIN", "JAX", usage=CHASE_USAGE, allowed=JAX,
                        ratings_def={"def": {"passing": {"rank": 5}}}, points=26.0,
                        line_words="CIN −2.5, total 49.5", n_teams=32, room=None)


def test_the_facts_say_which_stat_our_number_reads():
    by = {f.get("stat"): f for f in _facts() if f["kind"] == "defense"}
    assert by["qb_pass_yds"]["in_number"] and by["qb_pass_yds"]["sign"] == -1, by
    assert set(by["qb_pass_yds"]["markets"]) >= {"rec_yds", "receptions"}
    assert "5th-fewest" in by["qb_pass_yds"]["text"]
    assert not by["wr_rec_yds"]["in_number"] and by["wr_rec_yds"]["sign"] == 1
    assert "7th-most" in by["wr_rec_yds"]["text"]
    assert not by["wr_td"]["in_number"] and by["wr_td"]["markets"] == ["anytime_td"]
    role = next(f for f in _facts() if f["kind"] == "role")
    assert role["in_number"] and role["sign"] == 1 and "28%" in role["text"]


def test_the_corners_carry_the_yards_they_allowed():
    chart = [{"position": "LCB", "players": ["Tyson Campbell"]}, {"position": "RCB", "players": ["Jourdan Lewis"]},
             {"position": "NB", "players": ["Jarrian Jones"]}]
    from engine.sources.nflscheme import name_key
    defenders = {("JAX", name_key("Tyson Campbell")): {"name": "Tyson Campbell", "games": 4, "targets": 22,
                                                        "cmp": 13, "yds": 171, "td": 1, "yds_per_tgt": 7.8,
                                                        "rating": 98.1}}
    room = G.coverage_room("JAX", chart, defenders)
    tc = next(c for c in room["corners"] if c["name"] == "Tyson Campbell")
    assert (tc["targets"], tc["cmp"], tc["yds"], tc["games"]) == (22, 13, 171, 4)


def _js(names, consts):
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    out = []
    for c in consts:
        m = re.search(rf"^const {c} = .*?;$", app, re.M)
        assert m, c
        out.append(m.group(0))
    for n in names:
        i = app.index(f"\nfunction {n}(") + 1
        j = app.find("\nfunction ", i + 10)
        k = app.find("\nconst ", i + 10)
        end = min(x for x in (j, k) if x != -1)
        out.append(app[i:end])
    return "\n".join(out)


def test_the_page_sorts_the_case_for_the_under_and_says_why_it_stands():
    node = shutil.which("node")
    if not node:
        return
    src = _js(["caseHighTotal", "caseLowTotal", "scriptExpected", "caseScriptFact", "pickCase", "pickCaseHTML"],
              ["MINUS", "WHY_SCORER", "GS_HIGH_TOTAL", "GS_CATCH", "GS_PASS", "GS_RUSH"])
    src = src.replace("const CASE_CLOSE_SPREAD", "var CASE_CLOSE_SPREAD")
    facts = _facts()
    game = {"home": "JAX", "away": "CIN", "spread": 2.5, "favorite": "CIN", "total": 49.5,
            "scan": {"coverage": {"JAX": {"corners": [
                {"name": "Tyson Campbell", "spot": "LCB", "targets": 22, "cmp": 13, "yds": 171,
                 "yds_per_tgt": 7.8, "rating": 98.1, "td": 1}]}}}}
    under = {"player": "Ja'Marr Chase", "team": "CIN", "opponent": "JAX", "market": "rec_yds",
             "market_label": "Receiving yards", "side": "UNDER", "line": 84.5, "projection": 74.2,
             "position": "WR", "logs": [{"value": v} for v in (61, 92, 70, 55, 101, 66)]}
    read = {"pos": "WR", "facts": facts, "usage": CHASE_USAGE}
    prog = (src + "\nvar CASE_CLOSE_SPREAD = 3.5, CASE_WIDE_SPREAD = 6.5;"
            "\nconst state = {sport: 'nfl'};"
            "\nconst escapeHtml = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');"
            "\nconst teamName = (t) => ({CIN: 'Bengals', JAX: 'Jaguars'})[t] || t;"
            "\nconst wholePct = (p) => Math.round(p * 100) + '%';"
            f"\nconst g = {json.dumps(game)}, r = {json.dumps(under)}, x = {json.dumps(read)};"
            "\nconst c = pickCase(r, null, x, g);"
            "\nconsole.log(JSON.stringify({for: c.forBet.map(f => f.text), against: c.against.map(f => [f.text, f.in_number])}));"
            "\nconsole.log(pickCaseHTML(r, null, x, g, 0.6));"
            "\nconst o = Object.assign({}, r, {side: 'OVER'});"
            "\nconsole.log(JSON.stringify(pickCase(o, null, x, g).forBet.map(f => f.text)));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    first, html, over_for = out.stdout.split("\n", 2)[0], out.stdout, out.stdout.strip().splitlines()[-1]
    sorted_ = json.loads(first)
    assert any("passing yards" in t for t in sorted_["for"]), "the stingy pass defence backs the under"
    shown = [t for t, inn in sorted_["against"] if not inn]
    assert any("receiving yards to wide receivers" in t for t in shown), sorted_
    assert any("back-and-forth" in t for t, _ in sorted_["against"]), "a close, high total works against a catch under"
    assert "The case for the under 84.5" in html and "Works against it" in html
    assert "shown — not in our number" in html and "in our number" in html
    assert "pull the other way" in html or "pulls the other way" in html, "the verdict says why it still stands"
    assert "Who covers him" in html and "Tyson Campbell" in html and "171" in html
    assert "this is worth" in html and "take it past" in html, "the fair price and the worst one to take"
    assert "back-and-forth" in over_for, "the same script backs the over"


def test_the_game_script_names_a_back_and_forth_game():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "Close · back-and-forth, high-scoring" in app
    assert "a close, back-and-forth game" in app
    fn = app[app.index("function whyLikelyHTML("):]
    fn = fn[:fn.index("\nfunction ", 10)]
    assert "pickCaseHTML(rr, lk, x," in fn and "whySectionHTML(items, p, board, caseHTML)" in fn, \
        "the pick page leads with the case"


def test_red_zone_and_third_downs_are_counted_from_the_play_by_play():
    # Both breakdowns led with "Jacksonville allows a touchdown on 20% of
    # red-zone trips"; the site had no red-zone touchdown rate at all.
    from engine.sources.nflunits import Units
    base = dict(week="4", season_type="REG", posteam="CIN", defteam="JAX", epa="0.1", success="1",
                yards_gained="4", sack="0", qb_hit="0", two_point_attempt="0", game_id="2026_04_JAX_CIN")
    plays = [dict(base, qb_dropback="1", rush="0", drive="2", yardline_100="12", fixed_drive_result="Touchdown",
                  third_down_converted="1", third_down_failed="0"),
             dict(base, qb_dropback="0", rush="1", drive="6", yardline_100="9", fixed_drive_result="Field goal",
                  third_down_converted="0", third_down_failed="1"),
             dict(base, qb_dropback="0", rush="1", drive="8", yardline_100="60", fixed_drive_result="Punt",
                  third_down_converted="0", third_down_failed="0")]
    u = Units()
    for p in plays:
        u.add(p)
    rows = {(r["team"], r["side"]): r for r in u.rows(2026)}
    off, dfn = rows[("CIN", "off")], rows[("JAX", "def")]
    assert (off["rz_drives"], off["rz_tds"], off["third_att"], off["third_conv"]) == (2, 1, 2, 1)
    assert (dfn["rz_drives"], dfn["rz_tds"]) == (2, 1), "the defence allowed what the offence got"
    assert "redzone" in G.UNITS and "third_down" in G.UNITS


def test_a_scorer_reads_the_red_zone_and_a_receiver_reads_the_secondary():
    ratings_def = {"def": {"passing": {"rank": 5}, "redzone": {"rank": 2, "value": 0.2}}}
    ratings_off = {"off": {"redzone": {"rank": 20, "value": 0.5}}}
    room = {"corners": [{"name": "Dax Hill", "spot": "NB", "next_man_up": True}],
            "missing": [{"name": "Jalen Davis", "spot": "NB", "status": "IR"}]}
    facts = G.read_facts("wr", "WR", "JAX", "CIN", usage={"games": 3, "tgt_share": 0.299, "targets_pg": 7.7},
                         allowed={}, ratings_def=ratings_def, ratings_off=ratings_off, points=24.5,
                         line_words="", n_teams=32, room=room)
    rz = [f for f in facts if f["kind"] == "redzone"]
    assert any("20%" in f["text"] and f["sign"] == -1 and f["markets"] == ["anytime_td"] for f in rz), rz
    sec = next(f for f in facts if f["kind"] == "secondary")
    assert "Jalen Davis" in sec["text"] and "Dax Hill fills in" in sec["text"] and sec["sign"] == 1
    assert not sec["in_number"] and "rec_yds" in sec["markets"]


def test_the_season_numbers_table_is_the_plain_record():
    # Every breakdown's table: points for and against a game, run defence,
    # third downs, red-zone TD rate both ways, run rate — raw, ranked.
    from engine import db
    conn = db.connect(":memory:")
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                     "VALUES ('nfl', 2026, ?, ?, ?, ?, ?, ?)",
                     [("001", "A@B", "JAX", "CLE", 26, 10), ("002", "C@D", "DEN", "JAX", 20, 13),
                      ("003", "E@F", "JAX", "NE", 35, 6), ("001", "G@H", "CIN", "TB", 28, 21)])
    rows = [dict(sport="nfl", season=2026, period="001", team="JAX", side="def", opp="CLE", plays=60, rushes=20,
                 rush_yds=70, sacks=3, third_att=12, third_conv=3, rz_drives=4, rz_tds=1),
            dict(sport="nfl", season=2026, period="001", team="JAX", side="off", opp="CLE", plays=64, rushes=33,
                 third_att=11, third_conv=6, rz_drives=3, rz_tds=2)]
    db.upsert_team_units(conn, rows)
    nums = G.season_numbers(conn, 2026, before_week=4)
    jax = nums["JAX"]
    assert jax["games"] == 3 and round(jax["pts_against"]["value"], 1) == 12.0
    assert jax["pts_against"]["rank"] == 1, "fewest allowed ranks first"
    assert jax["rz_def"]["value"] == 0.25 and round(jax["third_off"]["value"], 3) == 0.545
    assert jax["run_rate"]["rank"] is None, "a run rate is a style, not a ranking"


def test_a_teammate_out_and_a_questionable_corner_reach_the_case():
    room = {"corners": [{"name": "Montaric Brown", "spot": "RCB", "status": "QUESTIONABLE", "next_man_up": False}],
            "missing": []}
    read = G.player_read("Tee Higgins", "CIN", "JAX", "WR", usage={"games": 3, "tgt_share": 0.225, "targets_pg": 7.7},
                         ratings={}, room=room, scheme=None, split=None, tackling=None, line_out=None,
                         mates_out=[{"name": "Colbie Young", "pos": "WR", "share": 0.08, "same_pos": True}],
                         allowed={}, points=27.0)
    kinds = {f["kind"]: f for f in read["facts"]}
    assert "Colbie Young" in kinds["teammate"]["text"] and kinds["teammate"]["sign"] == 1
    assert "Montaric Brown" in kinds["watch"]["text"] and kinds["watch"]["sign"] == 0


def test_each_game_script_carries_how_likely_it_is():
    # The breakdowns' "Cincinnati controls the game ~45%, close game ~25%":
    # from the posted spread and total, 13.5 points of spread on each.
    node = shutil.which("node")
    if not node:
        return
    src = _js(["scriptExpected", "gsPhi", "scriptOdds", "scriptScenarioOdds"],
              ["GS_HIGH_TOTAL", "GS_SD"]).replace("const CASE_CLOSE_SPREAD", "var CASE_CLOSE_SPREAD")
    prog = (src + "\nvar CASE_CLOSE_SPREAD = 3.5;\nconst state = {sport: 'nfl'};"
            "\nconst g = {home: 'CIN', away: 'JAX', spread: -2.5, favorite: 'CIN', total: 51.5};"
            "\nconst o = scriptOdds(g);"
            "\nconsole.log(JSON.stringify([o.home, o.close, o.high, scriptScenarioOdds(g, 1, 1), scriptScenarioOdds(g, 0, 1)]));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    home, close, high, cin_high, shoot = json.loads(out.stdout)
    assert abs(home - 0.573) < 0.01 and abs(close - 0.389) < 0.01 and abs(high - 0.630) < 0.01
    assert abs(cin_high - home * high) < 1e-9 and abs(shoot - close * high) < 1e-9

def test_a_scorer_case_opens_with_his_red_zone_role():
    """Every touchdown scan starts a scorer at "6 red-zone carries, 3 inside
    the 5": the case shows it, in our number, backing a back with real
    goal-line work and working against a receiver with none."""
    node = shutil.which("node")
    if not node:
        return
    src = _js(["caseHighTotal", "caseLowTotal", "scriptExpected", "caseScriptFact", "pickCase"],
              ["MINUS", "WHY_SCORER", "GS_HIGH_TOTAL", "GS_CATCH", "GS_PASS", "GS_RUSH"])
    src = src.replace("const CASE_CLOSE_SPREAD", "var CASE_CLOSE_SPREAD")
    brown = {"player": "Chase Brown", "team": "CIN", "opponent": "JAX", "market": "anytime_td",
             "side": "YES", "position": "RB", "rz_chances": 2.1,
             "goal_line": {"games": 3, "rz_car": 6, "i5_car": 3, "rz_tgt": 1, "i10_tgt": 0},
             "goal_line_text": "6 red-zone carries (3 inside the 5), 1 red-zone target in his last 3 games"}
    quiet = {**brown, "player": "Depth Receiver", "position": "WR",
             "goal_line": {"games": 3, "rz_car": 0, "i5_car": 0, "rz_tgt": 0, "i10_tgt": 0},
             "goal_line_text": "No red-zone touches in his last 3 games", "rz_chances": 0}
    prog = (src + "\nvar CASE_CLOSE_SPREAD = 3.5, CASE_WIDE_SPREAD = 6.5;"
            "\nconst state = {sport: 'nfl'};"
            "\nconst teamName = (t) => t;"
            f"\nconst a = pickCase({json.dumps(brown)}, null, null, null);"
            f"\nconst b = pickCase({json.dumps(quiet)}, null, null, null);"
            "\nconsole.log(JSON.stringify({brown: a.forBet.map(f => [f.text, f.in_number]),"
            " quiet: b.against.map(f => f.text)}));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
    out = subprocess.run([node, fh.name], capture_output=True, text=True, timeout=30)
    os.unlink(fh.name)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    role = [t for t, inn in got["brown"] if "inside the 5" in t]
    assert role and all(inn for t, inn in got["brown"] if "inside the 5" in t), got
    assert "2.1 red-zone chances expected this week" in role[0]
    assert any("No red-zone touches" in t for t in got["quiet"]), got


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
