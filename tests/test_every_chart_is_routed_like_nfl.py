"""Every league's charts open the way the NFL's do, from every door.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl."

What is pinned, offline:

  * HIS CHART LEADS, IN EVERY LEAGUE: the chart module's kindsFor names
    the player's own chart first and his role after it (the matchup is
    added last where the opponent is named);
  * THE PICK PAGE: every player's bet leaves a slot, whatever the league;
  * THE PLAYER PAGE: one door to his charts in every league with one,
    handing over the face it shows, the bet, his position and tonight's
    opponent; a fighter keeps his own fight-history door;
  * THE PARLAY CHECKER: every player's leg, in every league with a chart,
    carries the same door, with its bet and its opponent; a game leg has
    none;
  * THE DOOR'S CHARTS: the ones the bet and position point to, or every
    chart the league has when they point nowhere; the matchup last when
    the opponent is named and a chart has zones to read it on.

Run directly: `python3 tests/test_every_chart_is_routed_like_nfl.py`
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

APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
SLIP_JS = ROOT / "web" / "js" / "slip.js"
LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl", "mlb")


def _node(prog):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip())


STUBS = """
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const escapeAttr = escapeHtml, teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
  const window = {};
"""


def _chart(js):
    return _node(f"{STUBS}\n{CC_JS}\nconsole.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")


def test_his_own_chart_leads_in_every_league_and_his_role_follows():
    got = _chart("""return {
      nfl: [T.kindsFor("nfl", "rush_yds", "RB"), T.kindsFor("nfl", "receptions", "WR"), T.kindsFor("nfl", "pass_yds", "QB"),
            T.kindsFor("nfl", "kick_pts", "K")],
      cfb: [T.kindsFor("cfb", "rush_yds", "RB"), T.kindsFor("cfb", "receptions", "WR")],
      nba: [T.kindsFor("nba", "pts", "G")], wnba: [T.kindsFor("wnba", "pts", "G")],
      nhl: [T.kindsFor("nhl", "shots_on_goal", "C"), T.kindsFor("nhl", "saves", "G")],
      mlb: [T.kindsFor("mlb", "hits", "OF"), T.kindsFor("mlb", "strikeouts", "P")],
      ufc: [T.kindsFor("ufc", "moneyline", "")] };""")
    if got is None:
        return
    assert got["nfl"] == [["carries", "routes", "role"], ["routes", "carries", "role"], ["passes", "carries", "role"],
                          ["kicks"]]
    assert got["cfb"] == [["carries", "routes", "role"], ["routes", "carries", "role"]]
    assert got["nba"] == [["shots", "role"]] and got["wnba"] == [["role"]]
    assert got["nhl"] == [["shotmap", "role"], ["saves", "role"]]
    assert got["mlb"] == [["spray", "role"], ["pitches", "role"]] and got["ufc"] == [["fights"]]


def test_a_door_asks_for_the_bets_charts_or_the_leagues_every_one_and_the_matchup_last():
    got = _chart("""const D = (...a) => T.doorKinds(...a);
      return [D("nba", "reb", "", ""), D("nba", "reb", "", "BOS"), D("mlb", "strikeouts", "", "NYY"),
              D("mlb", "", "", ""), D("wnba", "pts", "", "LV"), D("nfl", "receptions", "", ""),
              D("nfl", "", "", "KC"), D("nhl", "saves", "", "TOR"), D("cfb", "", "", ""), D("ufc", "", "", "")];""")
    if got is None:
        return
    assert got[0] == {"cand": ["shots", "role"], "fam": "shots"}
    assert got[1] == {"cand": ["shots", "role", "matchup"], "fam": "shots"}
    assert got[2] == {"cand": ["pitches", "role", "matchup"], "fam": "pitches"}
    assert got[3] == {"cand": ["spray", "pitches", "role"], "fam": ""}, "no bet: every chart, the server picks"
    assert got[4] == {"cand": ["role"], "fam": "role"}, "no zones to read a matchup on"
    assert got[5] == {"cand": ["routes", "carries", "role"], "fam": "routes"}
    assert got[6] == {"cand": ["carries", "routes", "passes", "kicks", "role", "matchup"], "fam": ""}
    assert got[7] == {"cand": ["saves", "role", "matchup"], "fam": "saves"}
    assert got[8]["cand"] == ["carries", "routes", "role"] and got[9]["cand"] == ["fights"]
    assert "const D = auto ? doorKinds(lg, mkt, pos, opp)" in CC_JS and "fam: D.fam" in CC_JS


def test_every_pick_page_leaves_a_slot_in_every_league():
    i = APP_JS.index("function chartSlot(")
    fn = APP_JS[i:APP_JS.index("\n}\n", i) + 2]
    got = _node(f"""{STUBS}\nconst state = {{ sport: "nfl" }};\n{fn}
      console.log(JSON.stringify({json.dumps(list(LEAGUES))}.map((lg) => chartSlot({{ sport: lg, player: "A Player",
        market: "m", position: "P", opponent: "OPP" }})).concat([chartSlot({{ sport: "nba", player: "" }})])));""")
    if got is None:
        return
    for lg, html in zip(LEAGUES, got):
        assert f'data-lg="{lg}"' in html and 'data-cc="A Player"' in html and 'data-opp="OPP"' in html, lg
    assert got[-1] == "", "a bet with no player has no chart"


def test_the_player_page_has_one_door_to_his_charts_in_every_league():
    i = APP_JS.index("function chartDoor(")
    door = APP_JS[i:APP_JS.index("\n}\n", i) + 2]
    j = APP_JS.index("const ccDoor = ")
    cc = APP_JS[j:APP_JS.index("\n", j)]
    row = {"market": "pts", "position": "G", "opponent": "BOS", "headshot": "https://img.example/x.png"}
    got = _node(f"""{STUBS}\n{door}\n{cc}
      const r = {json.dumps(row)};
      console.log(JSON.stringify([...{json.dumps(list(LEAGUES))}.map((lg) => chartDoor("A <Player>", lg, r)),
                                  chartDoor("A Fighter", "ufc", r), chartDoor("No Row", "nba", {{}})]));""")
    if got is None:
        return
    for lg, html in zip(LEAGUES, got):
        assert html.count('class="btn cc-open"') == 1 and ">His charts</button>" in html, lg
        for attr in (f'data-lg="{lg}"', 'data-kind="auto"', 'data-carry="A &lt;Player&gt;"', 'data-mkt="pts"',
                     'data-pos="G"', 'data-opp="BOS"', 'data-face="https://img.example/x.png"'):
            assert attr in html, (lg, attr)
    assert got[len(LEAGUES)] == "", "a fighter's door is his fight history, on the card"
    assert 'data-mkt=""' in got[-1] and "data-face" not in got[-1]
    assert "+ chartDoor(player, lg, priced.get(mkt) || r0)" in APP_JS
    i = APP_JS.index('e.target.closest(".cc-open")')
    assert "m.open(d.carry, d.lg, d.kind, d.face, d.mkt, d.pos, d.opp)" in APP_JS[i:i + 300]
    assert 'ccDoor(f.name, "ufc", "fights", "Fight history")' in APP_JS


def test_every_players_leg_in_the_parlay_checker_carries_the_same_door():
    leg = lambda sport, market, player: {  # noqa: E731
        "sport": sport, "player": player, "team": "AAA", "opponent": "BBB", "market": market, "side": "over",
        "line": 1.5, "verdict": "fair", "prob": 0.6, "needs": 0.55}
    legs = [leg("nfl", "rush_yds", "Back"), leg("cfb", "receptions", "Wideout"), leg("nba", "pts", "Guard"),
            leg("wnba", "reb", "Forward"), leg("nhl", "saves", "Goalie"), leg("mlb", "strikeouts", "Starter"),
            {"sport": "nfl", "team": "AAA", "game": "AAA @ BBB", "market": "moneyline", "side": "AAA",
             "line": None, "verdict": "fair", "prob": 0.6, "needs": 0.55}]
    node = shutil.which("node")
    if not node:
        return
    prog = ("const vm = require('vm'); const fs = require('fs');"
            "const ctx = { window: {} }; vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(SLIP_JS))}, 'utf8'), ctx);"
            f"process.stdout.write(ctx.window.QBSlip.card({json.dumps({'n_legs': len(legs), 'grade': 'C', 'legs': legs})}));")
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    doors = re.findall(r'class="pgr-chart cc-open" data-carry="([^"]*)" data-lg="(\w+)" data-kind="(\w+)" '
                       r'data-mkt="([^"]*)" data-opp="([^"]*)">His charts<', out.stdout)
    assert doors == [("Back", "nfl", "auto", "rush_yds", "BBB"), ("Wideout", "cfb", "auto", "receptions", "BBB"),
                     ("Guard", "nba", "auto", "pts", "BBB"), ("Forward", "wnba", "auto", "reb", "BBB"),
                     ("Goalie", "nhl", "auto", "saves", "BBB"), ("Starter", "mlb", "auto", "strikeouts", "BBB")], doors
    assert out.stdout.count("pgr-chart cc-open") == 6, "the moneyline leg has no player and no chart"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
