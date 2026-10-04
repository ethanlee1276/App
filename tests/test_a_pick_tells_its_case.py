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
    assert "back-and-forth" in over_for, "the same script backs the over"


def test_the_game_script_names_a_back_and_forth_game():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "Close · back-and-forth, high-scoring" in app
    assert "a close, back-and-forth game" in app
    fn = app[app.index("function whyLikelyHTML("):]
    fn = fn[:fn.index("\nfunction ", 10)]
    assert "pickCaseHTML(rr, lk, x," in fn and "whySectionHTML(items, p, board, caseHTML)" in fn, \
        "the pick page leads with the case"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
