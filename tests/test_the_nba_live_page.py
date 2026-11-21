"""The NBA live page: what ESPN's game file gives it, and how it is drawn.

Ethan, 2026-10-15, with two renders (the Qellys arena, and the page laid out
like ESPN's app: the scoreboard, the arena with Live / Shot Chart / Player
Tracker / Game Flow, then the plays, the stats and the odds): "the live play
by play screen for nba looks like shit ... figure out what live data we can
get too make it look like an actual play by play screen like ball tracking
or possessions".

THE DATA (engine/sources/espnplays, livescore_build.pbp_doc): every play
keeps its spot on the floor (ESPN's feet, the shooting team's basket at
(25, 0); a play with no spot gets none) and every name it carries, in
ESPN's order; the game file gains the quarter-by-quarter line, the building,
and ESPN's scorer's-table block — timeouts, team fouls, the bonus, the ball —
only where ESPN carries one. The box score marks its starters. Nothing is
written that ESPN wrote as a sentence. hoopsprobe.py prints, on the box,
what a real game carries.

THE PAGE. Until 21 November 2026 web/js/hoopscast.js drew a whole page of its
own: its scoreboard, the arena, then the plays, the stats and the odds. Every
sport's page is the one page now (detail.js gpPageHTML; Ethan: "all sports in
all aspects should be trying to match nfl and that should be automatic when we
do any visual changes"), and the file hands it basketball's parts (`parts`):
Ethan's arena with Live / Shot Chart / Player Tracker / Game Flow where
football's field is, the newest play in words for the shared card, each play's
line for the period cards, the scorer's table under the score, and the shot
chart and the trends for the Stats room. What it works out from the plays is
pinned here — whose ball it is (only where a play settles it), runs, leads,
droughts, the five on the floor (only when one order of ESPN's two names holds
for every substitution), the league's shot zones, a name's role (only when the
box puts that player on that role's side) — and the court on the picture: the
four corners land where they were read off the render, each side's shots on
its own half. A redraw keeps the decoded picture and a scrolled view's place
(the page's own rule now: gpHoldTake, gpHoldGive).

Offline throughout; the browser half is opt-in (QB_BROWSER_TESTS=1) and
aborts every request that leaves the page's own server.

Run directly: `python3 tests/test_the_nba_live_page.py`
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

import hoopsprobe as P                                       # noqa: E402
import livescore_build as B                                  # noqa: E402
from engine.sources import espnplays as E                    # noqa: E402
from _app import app_js, page_builders  # noqa: E402  (app.js and its rooms; the game page's own card builders)

TEXT = "ESPN's own sentence about the play"
SHORT = "ESPN's shorter sentence"
BOS, CHA = "2", "30"                                          # ESPN team ids
TATUM, BROWN, WHITE, HORFORD, PRITCH = "4065648", "3917376", "3078576", "3213", "4066354"
BALL, MILLER = "4432816", "4433287"
OFF = -214748340                                              # ESPN's no-spot sentinel


def _play(pid, *, ptype, team=BOS, parts=(TATUM,), period=3, clock="5:24", shot=False, scoring=False,
          value=0, attempted=0, away=44, home=54, x=OFF, y=OFF):
    return {"id": pid, "sequenceNumber": pid, "period": {"number": period}, "clock": {"displayValue": clock},
            "team": {"id": team}, "participants": [{"athlete": {"id": a}} for a in parts],
            "type": {"id": "1", "text": ptype}, "shootingPlay": shot, "scoringPlay": scoring,
            "scoreValue": value, "pointsAttempted": attempted, "awayScore": away, "homeScore": home,
            "coordinate": {"x": x, "y": y}, "text": TEXT, "shortDescription": SHORT}


def _box(tid, abbr, people):
    return {"team": {"id": tid, "abbreviation": abbr, "displayName": abbr},
            "statistics": [{"name": "", "labels": ["MIN", "PTS", "REB", "AST", "PF"],
                            "athletes": [{"athlete": {"id": aid, "displayName": nm,
                                                      "position": {"abbreviation": "F"}},
                                          "starter": st, "stats": ["20", "12", "4", "3", "2"]}
                                         for aid, nm, st in people]}]}


def _summary(situation=True):
    plays = [
        _play("1", ptype="Pullup Jump Shot", shot=True, scoring=True, value=3, attempted=3,
              parts=(TATUM, BROWN), x=3.0, y=4.0, home=57),
        _play("2", ptype="Substitution", parts=(PRITCH, WHITE)),
        _play("3", ptype="Driving Layup Shot", team=CHA, parts=(BALL,), shot=True, attempted=2,
              x=25.5, y=1.0),
        _play("4", ptype="Defensive Rebound", parts=(HORFORD,), x=26.0, y=3.0),
        _play("5", ptype="Free Throw - 1 of 2", team=CHA, parts=(MILLER,), shot=True, scoring=True,
              value=1, attempted=1, away=45, x=OFF, y=OFF),
    ]
    head = {"id": "401810010", "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"id": BOS, "abbreviation": "BOS"},
         "linescores": [{"displayValue": "30"}, {"displayValue": "24"}, {"displayValue": "3"}]},
        {"homeAway": "away", "team": {"id": CHA, "abbreviation": "CHA"},
         "linescores": [{"displayValue": "22"}, {"displayValue": "22"}, {"displayValue": "1"}]}]}]}
    if situation:
        head["competitions"][0]["situation"] = {
            "homeTimeouts": 4, "awayTimeouts": 3, "possession": CHA,
            "homeFouls": {"teamFouls": 2, "foulsToGive": 2, "bonusState": "NONE"},
            "awayFouls": {"teamFouls": 5, "foulsToGive": 0, "bonusState": "BONUS"}}
    return {"plays": plays, "header": head,
            "gameInfo": {"venue": {"fullName": "TD Garden", "address": {"city": "Boston", "state": "MA"}}},
            "boxscore": {"players": [
                _box(BOS, "BOS", [(TATUM, "Jayson Tatum", True), (BROWN, "Jaylen Brown", True),
                                  (WHITE, "Derrick White", True), (HORFORD, "Al Horford", True),
                                  (PRITCH, "Payton Pritchard", False)]),
                _box(CHA, "CHA", [(BALL, "LaMelo Ball", True), (MILLER, "Brandon Miller", True)])],
                "teams": []}}


SIDES = {BOS: "BOS", CHA: "CHA"}
GAME = {"event_id": "401810010", "home": "BOS", "away": "CHA", "live": {"state": "live"}}


# --- the data --------------------------------------------------------------------
def test_a_play_keeps_its_spot_on_the_floor_and_a_play_without_one_gets_none():
    rows = E.hoops_plays(_summary(), "nba", 0, sides=SIDES)
    assert (rows[0]["x"], rows[0]["y"]) == (3.0, 4.0), "a corner three, ESPN's feet"
    assert (rows[2]["x"], rows[2]["y"]) == (25.5, 1.0), "a layup at the rim"
    assert "x" not in rows[4] and "y" not in rows[4], "a free throw carries ESPN's sentinel: no spot"
    assert E._floor_spot({"x": "12.04", "y": 7}) == (12.0, 7.0)
    for bad in (None, {}, {"x": None, "y": 3}, {"x": "a", "y": 1}, {"x": 101, "y": 1}):
        assert E._floor_spot(bad) is None, bad
    hockey = E.hoops_plays(_summary(), "nhl", 0, sides=SIDES)
    assert not any("x" in r for r in hockey), "the court is basketball's"
    from engine.nba import shots
    assert E.OFF_FLOOR == shots.ESPN_FLOOR, "one bound for ESPN's off-floor sentinel"


def test_every_name_rides_in_espns_order_and_one_name_stays_player():
    rows = E.hoops_plays(_summary(), "nba", 0, sides=SIDES)
    assert rows[0]["player"] == "Jayson Tatum" and rows[0]["players"] == ["Jayson Tatum", "Jaylen Brown"]
    assert rows[1]["players"] == ["Payton Pritchard", "Derrick White"], "both men in the substitution"
    assert "players" not in rows[2], "one name is `player` alone"


def test_the_game_file_carries_the_quarters_the_building_and_the_scorers_table():
    doc = B.pbp_doc("nba", GAME, _summary(), sides=SIDES)
    assert doc["linescores"] == {"BOS": [30, 24, 3], "CHA": [22, 22, 1]}
    assert doc["venue"] == {"name": "TD Garden", "city": "Boston", "state": "MA"}
    assert doc["situation"] == {"timeouts": {"home": 4, "away": 3}, "fouls": {"home": 2, "away": 5},
                                "bonus": {"home": False, "away": True}, "possession": "away"}
    starters = [r["name"] for b in doc["box"] for g in b["groups"] for r in g["rows"] if r.get("starter")]
    assert starters == ["Jayson Tatum", "Jaylen Brown", "Derrick White", "Al Horford",
                        "LaMelo Ball", "Brandon Miller"], starters
    flat = json.dumps(doc)
    for prose in (TEXT, SHORT, '"text"', '"shortDescription"'):
        assert prose not in flat, prose


def test_what_espn_does_not_carry_is_absent_never_guessed():
    bare = _summary(situation=False)
    bare.pop("gameInfo")
    for c in bare["header"]["competitions"][0]["competitors"]:
        c.pop("linescores")
    doc = B.pbp_doc("nba", GAME, bare, sides=SIDES)
    for key in ("situation", "venue", "linescores"):
        assert key not in doc, key
    assert E.hoops_situation({"header": {"competitions": [{"situation": {"homeTimeouts": 99}}]}}) == {}, \
        "a number no scorer's table holds is not read"
    assert E.hoops_venue({"gameInfo": {"venue": {"fullName": "x" * 61}}}) == {}, "a name, never a sentence"
    nfl = B.pbp_doc("nfl", {**GAME, "home": "DAL", "away": "TB"}, {"drives": {"previous": [], "current": None}})
    for key in ("situation", "venue", "linescores"):
        assert key not in nfl, f"{key}: a summary without it gives a file without it"


def test_a_header_block_that_breaks_costs_that_key_alone():
    real = E.hoops_venue
    E.hoops_venue = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("shape"))
    try:
        doc = B.pbp_doc("nba", GAME, _summary(), sides=SIDES)
    finally:
        E.hoops_venue = real
    assert "venue" not in doc and doc["linescores"] and doc["situation"] and doc["plays"]


# --- the box probe ---------------------------------------------------------------
def test_the_probe_finds_the_substitution_order_from_the_starters():
    starters = {"BOS": {"T", "B", "W", "H", "J"}}
    # Pritchard in for White, then White back for him. Read the wrong way
    # round, the first step is impossible (White is on, Pritchard is not);
    # one impossible step counts once.
    in_first = [("BOS", "P", "W"), ("BOS", "W", "P")]
    assert P.on_floor_order(starters, in_first) == {"in_first": 0, "out_first": 1}
    out_first = [("BOS", "W", "P"), ("BOS", "P", "W")]
    assert P.on_floor_order(starters, out_first) == {"in_first": 1, "out_first": 0}


def test_the_probe_reports_the_four_answers_and_never_a_sentence():
    board = {"events": [{"id": "401810010", "competitions": [_summary()["header"]["competitions"][0]]}]}
    lines = P.report(board, _summary(), "401810010")
    text = "\n".join(lines)
    for head in ("1. the scorer's table", "2. the court", "3. who is on the floor", "4. what the deep file will carry"):
        assert head in text, head
    assert "homeTimeouts = 4" in text and "bonusState = BONUS" in text
    assert "ESPN lists the man coming IN first" in text
    assert "with a spot on the floor 2" in text
    assert TEXT not in text and SHORT not in text
    assert "venue: {'name': 'TD Garden'" in text
    src = (ROOT / "hoopsprobe.py").read_text(encoding="utf-8")
    assert "cdn.nba.com" not in src and "sudo -u qellys python3 hoopsprobe.py" in src


# --- the page: the readers --------------------------------------------------------
HC = (ROOT / "web" / "js" / "hoopscast.js").read_text(encoding="utf-8")
HC_CSS = (ROOT / "web" / "css" / "hoopscast.css").read_text(encoding="utf-8")
APP = app_js()
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")

LAL5 = ["LeBron James", "Anthony Davis", "Austin Reaves", "D'Angelo Russell", "Rui Hachimura"]
BOS5 = ["Jayson Tatum", "Jaylen Brown", "Derrick White", "Jrue Holiday", "Al Horford"]


def _deep(state="live", situation=True, sub=("Payton Pritchard", "Derrick White")):
    """A deep file as pbp_doc writes it: LAL at BOS, five minutes into the second."""
    rows, sc = [], {"LAL": 0, "BOS": 0}

    def play(team, player, event, period, clock, *, shot=False, made=False, tried=0, x=None, y=None, names=None):
        if made:
            sc[team] += tried
        r = {"kind": "hoops", "id": str(len(rows) + 1), "period": period, "clock": clock, "team": team,
             "player": player, "event": event, "scoring": made, "shot": shot, "points": tried if made else 0,
             "points_attempted": tried if shot else 0, "away_score": sc["LAL"], "home_score": sc["BOS"]}
        if names:
            r["players"] = list(names)
        if x is not None:
            r["x"], r["y"] = x, y
        rows.append(r)

    play("LAL", "LeBron James", "Driving Layup Shot", 1, "11:30", shot=True, made=True, tried=2, x=25.5, y=1.5,
         names=("LeBron James", "Austin Reaves"))
    play("BOS", "Jayson Tatum", "Jump Shot", 1, "10:58", shot=True, made=True, tried=3, x=3.0, y=4.0,
         names=("Jayson Tatum", "Derrick White"))
    play("BOS", sub[0], "Substitution", 1, "10:40", names=sub)
    play("LAL", "Anthony Davis", "Jump Shot", 1, "10:21", shot=True, tried=2, x=37.0, y=12.0,
         names=("Anthony Davis", "Al Horford"))
    play("BOS", "Al Horford", "Defensive Rebound", 1, "10:19")
    play("BOS", "Jaylen Brown", "Dunk", 1, "9:50", shot=True, made=True, tried=2, x=25.0, y=1.0)
    play("LAL", "Austin Reaves", "Lost Ball Turnover", 1, "9:31", names=("Austin Reaves", "Jrue Holiday"))
    play("BOS", "Jrue Holiday", "Pullup Jump Shot", 1, "2:00", shot=True, made=True, tried=3, x=25.0, y=26.0)
    play("", "", "End Period", 1, "0.0")
    play("LAL", "LeBron James", "Step Back Jump Shot", 2, "9:00", shot=True, made=True, tried=3, x=10.0, y=22.0)
    play("LAL", "LeBron James", "Cutting Layup Shot", 2, "8:10", shot=True, made=True, tried=2, x=24.0, y=2.0)
    play("LAL", "Anthony Davis", "Dunk", 2, "6:30", shot=True, made=True, tried=2, x=25.0, y=0.5)
    play("BOS", "Jayson Tatum", "Shooting Foul", 2, "5:40", names=("Jayson Tatum", "Anthony Davis"))
    play("LAL", "Anthony Davis", "Free Throw - 1 of 2", 2, "5:40", shot=True, made=True, tried=1)
    play("LAL", "Anthony Davis", "Free Throw - 2 of 2", 2, "5:40", shot=True, tried=1)
    play("BOS", "Al Horford", "Defensive Rebound", 2, "5:38")
    play("BOS", "", "Timeout", 2, "5:10")
    rows[0]["text"] = TEXT                                   # were a sentence ever in the file, it is not drawn

    def box(team, five, bench):
        return {"team": team, "groups": [{"name": "", "labels": ["MIN", "FG", "3PT", "FT", "REB", "AST", "STL", "BLK", "TO", "PF", "PTS"],
                "rows": [{"name": n, "id": f"{team}{i}", "pos": "F", "stats": ["12", "2-4", "1-2", "0-0", "3", "2", "1", "0", "1", str(i % 3), str(4 + i)],
                          **({"starter": True} if n in five else {})} for i, n in enumerate(five + bench)]}]}
    doc = {"league": "nba", "event_id": "401810010", "generated_at": "2026-10-15T01:20:00Z", "home": "BOS", "away": "LAL",
           "live": {"state": state, "period": "Q2", "clock": "5:10", "home_score": sc["BOS"], "away_score": sc["LAL"],
                    "win_prob": {"home_win_prob": 0.58, "away_win_prob": 0.42}},
           "plays": rows, "box": [box("LAL", LAL5, ["Gabe Vincent"]), box("BOS", BOS5, ["Payton Pritchard", "Kristaps Porzingis"])],
           "team_stats": {}, "records": {"LAL": "3-2", "BOS": "4-1"},
           "linescores": {"LAL": [2, 8], "BOS": [8, 0]}, "venue": {"name": "TD Garden", "city": "Boston", "state": "MA"}}
    if situation:
        doc["situation"] = {"timeouts": {"home": 4, "away": 3}, "fouls": {"home": 5, "away": 2},
                            "bonus": {"home": False, "away": True}, "possession": "away"}
    return doc


STUBS = """
  globalThis.window = globalThis;
  globalThis.escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.escapeAttr = escapeHtml;
  globalThis.icon = (n) => `<i class="ico-${n}"></i>`;
  globalThis.teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
  globalThis.teamNameIn = (lg, a) => ({ LAL: "Lakers", BOS: "Celtics" })[a] || a;
  globalThis.teamsIn = () => ({ LAL: { loc: "Los Angeles", nick: "Lakers", primary: "#552583", secondary: "#fdb927", tertiary: "#000000" },
                                BOS: { loc: "Boston", nick: "Celtics", primary: "#007a33", secondary: "#ba9653", tertiary: "#963821" } });
  globalThis.LEAGUE_LABEL = { nba: "NBA", wnba: "WNBA" };
  globalThis.pbpAgo = () => "updated just now";
  globalThis.oddsTxt = (v) => (Number(v) > 0 ? `+${v}` : String(v));
  globalThis.gameId = (g) => `${g.away}@${g.home}`;
  globalThis.pbpPropsHTML = () => "<div>our picks on the game</div>";
"""


def _node(js, gc=False):
    """`gc` loads js/gamecast.js first, as the page has it: the shared run
    (QBGamecast.track) that moves the ball and the card the newest play is
    drawn on. Without it every mark is drawn where it is, which is what a
    reader who asked for less motion sees. The page's own boxes (detail.js)
    are the real ones (_app.page_builders)."""
    node = shutil.which("node")
    if not node:
        return None
    prog = (f"{STUBS}\n{page_builders()}\n{GC if gc else ''}\n{HC}\n"
            f"console.log(JSON.stringify((() => {{ const Q = window.QBHoops; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


#: What the sport hands the one page, as text: each part, and its words for every play.
PARTS = """
  const partsOf = (ctx) => {
    const P = Q.parts(ctx), out = {};
    for (const [key, v] of Object.entries(P)) if (typeof v !== "function") out[key] = v;
    out.says = (ctx.d.plays || []).map((p) => P.say(p));
    out.wire = typeof P.wire;
    return out;
  };
"""


def _parts(doc, board=None, gc=True, league="nba"):
    """Basketball's parts of the page (QBHoops.parts), as detail.js gpKit asks for them."""
    return _node(f"""{PARTS}
      return partsOf({{ d: {json.dumps(doc)}, league: "{league}", lv: {json.dumps(doc.get("live") or {})},
                       boardGame: {json.dumps(board)}, faces: {{}} }});""", gc=gc)


def test_the_ball_is_somebodys_only_where_a_play_settles_it():
    one = lambda team, event, **kw: {"team": team, "event": event, **kw}
    cases = {
        "rebound": ([one("BOS", "Defensive Rebound")], "home"),
        "turnover": ([one("BOS", "Bad Pass Turnover")], "away"),
        "traveling": ([one("LAL", "Traveling")], "home"),
        "first of two": ([one("LAL", "Free Throw - 1 of 2", shot=True, scoring=True)], "away"),
        "last made": ([one("LAL", "Free Throw - 2 of 2", shot=True, scoring=True)], "home"),
        "last missed": ([one("LAL", "Free Throw - 2 of 2", shot=True, scoring=False)], ""),
        "make": ([one("BOS", "Dunk", shot=True, scoring=True, points_attempted=2)], "away"),
        "miss": ([one("BOS", "Jump Shot", shot=True, scoring=False, points_attempted=2)], ""),
        "foul": ([one("BOS", "Personal Foul")], "away"),
        "over a timeout and a change": ([one("BOS", "Offensive Rebound"), one("BOS", "Timeout"),
                                         one("LAL", "Substitution")], "home"),
        "the period ended": ([one("BOS", "Defensive Rebound"), one("", "End Period")], ""),
        "nobody's team": ([one("espn:99", "Defensive Rebound")], ""),
    }
    got = _node(f"""
      const cases = {json.dumps({k: v[0] for k, v in cases.items()})};
      const out = {{}};
      for (const [k, plays] of Object.entries(cases)) out[k] = Q.ballAfter({{ home: "BOS", away: "LAL", plays }});
      return out;""")
    if got is None:
        print("      (skipped: no node)")
        return
    for k, (_, want) in cases.items():
        assert got[k] == want, (k, got[k], want)


def test_runs_leads_and_droughts_come_off_the_running_score():
    got = _node(f"""
      const d = {json.dumps(_deep())};
      return {{ leads: Q.leads(d, "nba"), dry: Q.droughts(d, "nba"), flow: Q.flow(d, "nba").length,
               t: [Q.elapsed("nba", {{ period: 2, clock: "5:10" }}), Q.elapsed("wnba", {{ period: 2, clock: "5:10" }}),
                   Q.elapsed("nba", {{ period: 5, clock: "1:00" }})], c: [Q.clockSecs("4:07"), Q.clockSecs("31.4"), Q.clockSecs("")] }};""")
    if got is None:
        return
    L = got["leads"]
    assert (L["changes"], L["ties"]) == (2, 0), L
    assert L["big"] == {"home": 6, "away": 2}, L["big"]
    assert L["run"] == {"side": "away", "pts": 8}, "LAL's 8-0 since BOS last scored"
    assert L["best"] == {"side": "home", "pts": 8}, "the first 8-0 of the game holds the mark"
    assert got["dry"]["home"] == (720 + 410) - 600, "BOS's last field goal at 2:00 of the first"
    assert got["dry"]["away"] == 80
    assert got["flow"] == 9, "the tip and every change of score"
    assert got["t"] == [1130, 600 + 290, 2880 + 240], "twelve-minute quarters, ten in the WNBA, five in overtime"
    assert got["c"] == [247, 31.4, None]


def test_the_five_on_the_floor_hold_for_one_order_of_espns_names_or_none():
    got = _node(f"""
      return {{ inFirst: Q.onFloor({json.dumps(_deep())}),
               outFirst: Q.onFloor({json.dumps(_deep(sub=("Derrick White", "Payton Pritchard")))}),
               neither: Q.onFloor({json.dumps(_deep(sub=("Payton Pritchard", "Kristaps Porzingis")))}) }};""")
    if got is None:
        return
    assert got["inFirst"]["inFirst"] is True
    assert sorted(got["inFirst"]["home"]) == sorted(["Jayson Tatum", "Jaylen Brown", "Jrue Holiday", "Al Horford", "Payton Pritchard"])
    assert sorted(got["inFirst"]["away"]) == sorted(LAL5)
    assert got["outFirst"]["inFirst"] is False and "Payton Pritchard" in got["outFirst"]["home"]
    assert got["neither"] is None, "two men off the floor swapping is impossible both ways: no five drawn"
    no_starters = _deep()
    for b in no_starters["box"]:
        for r in b["groups"][0]["rows"]:
            r.pop("starter", None)
    assert _node(f"return Q.onFloor({json.dumps(no_starters)});") is None, "a box with no starters marked draws no five"


def test_the_leagues_zones_and_each_sides_half_of_the_court():
    got = _node("""
      const z = (x, y, pts) => Q.zoneOf({ x, y, pts });
      const at = (side, x, y) => { const c = Q.courtSpot({ side, x, y }); return Q.artSpot(c, side).map((v) => Math.round(v * 10) / 10); };
      return {
        zones: [z(25.5, 1.5, 2), z(30, 10, 2), z(37, 12, 2), z(3, 4, 3), z(25, 26, 3), z(null, 4, 2)],
        corners: [[0, 0], [94, 0], [0, 50], [94, 50]].map(([u, v]) => Q.toArt(u, v).map((n) => Math.round(n * 10) / 10)),
        centre: Q.toArt(47, 25).map((n) => Math.round(n * 10) / 10),
        rims: [at("away", 25, 0), at("home", 25, 0)],
        threes: [at("away", 25, 23.75), at("home", 25, 23.75)],
        corner3: [at("away", 3, 4), at("away", 47, 4), at("home", 3, 4)],
        nowhere: [Q.courtSpot({ side: "", x: 25, y: 1 }), Q.courtSpot({ side: "home", x: null, y: 1 })],
      };""")
    if got is None:
        return
    assert got["zones"] == ["ra", "paint", "mid", "corner3", "above3", ""], got["zones"]
    assert got["corners"] == [[440, 594], [1233, 594], [189, 830], [1482, 830]], "the four corners read off the render"
    cx = got["centre"][0]
    assert abs(cx - 836) < 1 and abs(got["centre"][1] - 683.7) < 1
    (ax, ay), (hx, hy) = got["rims"]
    assert ax < cx < hx and ay == hy, "the away side shoots at the left basket, the home side at the right"
    assert abs((ax + hx) / 2 - cx) < 1, "the two baskets mirror each other about centre court"
    assert abs(ax - 372) < 40 and abs(hx - 1300) < 40, "under the rims the render draws (its camera leans the uprights out)"
    assert got["threes"][0][0] - ax > 250 and hx - got["threes"][1][0] > 250, "a three from the top of the key, well out"
    far, near, other = got["corner3"]
    assert abs(far[1] - 594) < 10 and abs(near[1] - 830) < 10, "a corner three sits on a sideline"
    assert far[0] < cx and near[0] < cx and other[0] > cx
    assert got["nowhere"] == [None, None]


def test_a_play_reads_as_a_line_and_a_role_only_the_box_backs():
    """Who did what, in our own words (21 November 2026): the label and its facts were a row of pieces ("Jump Shot
    · missed 2 · blocked by Al Horford"); the same facts are a line now, the names in bold on a row."""
    doc = _deep()
    stray = dict(doc["plays"][0], id="x1", players=["LeBron James", "Jayson Tatum"])        # an "assist" from the other side
    ghost = dict(doc["plays"][0], id="x2", players=["LeBron James", "Somebody Else"])        # a name the box does not list
    got = _node(f"""
      const d = {json.dumps(doc)};
      const k = {{ sideOfName: (n) => ({{ "LeBron James": "away", "Austin Reaves": "away", "Anthony Davis": "away",
                                         "Jayson Tatum": "home", "Al Horford": "home", "Jrue Holiday": "home" }})[n] || "",
                  floor: Q.onFloor(d) }};
      const P = d.plays;
      const line = (p) => {{ const s = Q.sayPlay(p, d, k); return !s ? null : s.moment ? `[${{s.moment}}]` : s.html; }};
      return [P[0], P[3], P[6], P[12], P[2], P[13], P[14], {json.dumps(stray)}, {json.dumps(ghost)}, P[8], P[16]].map(line)
        .concat([Q.playKind(P[0]), Q.playKind(P[3]), Q.playKind(P[13]), Q.playKind(P[14]), Q.playKind(P[16])]);""")
    if got is None:
        return
    assert got[0] == "<b>LeBron James</b> makes a driving layup, assist <b>Austin Reaves</b>"
    assert got[1] == "<b>Anthony Davis</b> misses a jump shot, blocked by <b>Al Horford</b>"
    assert got[2] == "<b>Austin Reaves</b> turns it over: lost ball, stolen by <b>Jrue Holiday</b>"
    assert got[3] == "Shooting foul on <b>Jayson Tatum</b>, drawn by <b>Anthony Davis</b>"
    assert got[4] == "<b>Payton Pritchard</b> in for <b>Derrick White</b>"
    assert got[5] == "<b>Anthony Davis</b> makes free throw 1 of 2" and got[6] == "<b>Anthony Davis</b> misses free throw 2 of 2"
    assert got[7] == "<b>LeBron James</b> makes a driving layup", "a teammate's assist, never the other side's"
    assert got[8] == "<b>LeBron James</b> makes a driving layup", "no role for a name the box does not list"
    assert got[9:11] == ["[End of the 1st quarter]", "[Timeout, Celtics]"], "a moment in the game is named, not a play"
    assert got[11:] == ["made", "miss", "ft", "ftmiss", "time"]
    assert TEXT not in json.dumps(got), "ESPN's sentence is never the line"


def test_each_side_wears_a_colour_that_reads_on_the_dark_floor():
    got = _node("""
      return [Q.colours("nba", { home: "BOS", away: "LAL" }), Q.colours("nba", { home: "LAL", away: "BOS" }),
              Q.colours("nba", { home: "XXX", away: "YYY" })];""")
    if got is None:
        return
    assert got[0] == {"home": "#007a33", "away": "#fdb927"}, "the Lakers in their gold, as Ethan's render draws them"
    assert got[1] == {"home": "#fdb927", "away": "#007a33"}
    assert got[2] == {"home": "var(--text-mute)", "away": "var(--brand)"}, "a club off the table takes the site's own"


# --- the parts it hands the page -----------------------------------------------------
def test_the_parts_are_the_arena_the_newest_play_the_scorers_table_and_two_stats_cards():
    """One page for every sport (detail.js gpPageHTML, 21 November 2026). This file drew a page of its own: a
    scoreboard, an arena and three cards with tabs. It hands the page its parts now, and nothing else."""
    P = _parts(_deep(), {"home": "BOS", "away": "LAL", "spread": -4.5, "total": 227.5})
    if P is None:
        return
    assert set(P) == {"stage", "now", "statsExtra", "ball", "ballIcon", "ballTitle", "marks", "says", "wire"}, sorted(P)
    stage = P["stage"]
    # The arena, in the page's own box (gpStageHTML), in the clubs' colours.
    assert stage.startswith('<div class="card gp-stage hc-stage v-live" style="--ca:#fdb927;--ch:#007a33">'), stage[:120]
    for key, label in (("live", "Live"), ("shots", "Shot Chart"), ("tracker", "Player Tracker"), ("flow", "Game Flow")):
        assert f'data-hc-view="{key}"' in stage and f'aria-label="{label}"' in stage, key
    assert 'data-hc-full aria-label="Full screen"' in stage
    assert "img/arena/nba-arena.webp 1280w" in stage and "img/arena/nba-arena@640.webp 640w" in stage
    assert '<div class="hc-venue"><b>TD Garden</b><span>Boston, MA</span></div>' in stage
    # The last shot flies to the rim and the arrow points the ball's way.
    # The ball runs the last shots on the shared timeline (QBGamecast.track,
    # 2026-10-15): a translate along the points, not a flight of its own.
    assert 'class="hc-flight' in stage and '<animateTransform attributeName="transform" type="translate"' in stage and 'class="hc-arrow"' in stage
    assert "LAL on an 8–0 run" in stage, "said once, on the arena"
    # The scorer's table, ESPN's block, under each side's record on the page's score: LAL in the bonus.
    assert P["marks"] == {
        "away": '<span class="hc-marks-row"><span class="hc-bonus">Bonus</span><span class="hc-k">Fouls <b>2</b></span>'
                '<span class="hc-k">Timeouts <b>3</b></span></span>',
        "home": '<span class="hc-marks-row"><span class="hc-k">Fouls <b>5</b></span><span class="hc-k">Timeouts <b>4</b></span></span>'}
    assert (P["ball"], P["ballIcon"], P["ballTitle"]) == ("away", "basketball", "Ball"), "ESPN's possession wins over the plays' guess"
    # The newest play, on the card every sport's is drawn on (gamecast.js playNowHTML): the last real play,
    # who was in it with their game so far, and what has happened since.
    now = P["now"]
    assert now.startswith('<div class="card gc-dv" data-gc-dv>')
    assert '<div class="gc-k">Last play · Q2 5:38</div><b>Rebound</b>' in now
    assert '<p class="gc-dv-said">Al Horford grabs a defensive rebound.</p>' in now
    assert now.count('class="gc-chip"') == 1 and "<b>Al Horford</b>" in now and "8 PTS, 3 REB, 2 AST" in now
    assert '<div class="gc-dv-before"><span>Timeout, Celtics</span></div>' in now, "a timeout is said under the play, not as it"
    assert "run" not in now, "the run is the arena's to say"
    # Every play in words, for the period cards and the list beside the page (app.js playsHTML `say`).
    assert len(P["says"]) == 17 and P["says"][-1] == {"moment": "Timeout, Celtics"}
    assert P["says"][1] == {"html": "<b>Jayson Tatum</b> makes a 3-point jump shot, assist <b>Derrick White</b>"}
    # What only basketball has, for the Stats room: two of the page's own cards (gpCardHTML).
    extra = P["statsExtra"]
    assert extra.count('<div class="card gp-card hc-card" style="--ca:#fdb927;--ch:#007a33">') == 2
    assert "<b>Shot chart</b><span>every shot, from above</span>" in extra and "<b>Trends</b>" in extra
    assert 'class="hc-fcourt"' in extra and "At the rim" in extra and "Corner 3" in extra
    assert "On pace for" in extra and "BOS: no field goal in <b>8:50</b>" in extra
    # And none of the page it used to draw: the score, the play list, the team stats, the odds, the chat's slot.
    whole = json.dumps(P)
    for gone in ("hc-score", "hc-plays", "hc-stats", "hc-odds", "hc-ts-k", "hc-line-k", "gch-entry-slot", "pbp-game-door",
                 "Win chance (our model)", "<nav>", "pbp-foot"):
        assert gone not in whole, gone
    assert TEXT not in whole, "ESPN's sentences are never drawn"
    assert "onclick" not in whole and "onerror" not in whole
    assert P["wire"] == "function"


def test_what_espn_does_not_carry_draws_nothing_and_a_final_holds_no_ball():
    bare = _deep(situation=False)
    for key in ("venue", "linescores"):
        bare.pop(key)
    P = _parts(bare)
    if P is None:
        return
    assert P["marks"] == {"away": "", "home": ""}, "no scorer's table, no line of it under the score"
    assert "hc-venue" not in P["stage"]
    assert (P["ball"], P["ballTitle"]) == ("home", "Ball — from the last play"), "the plays' own read, said as such"
    final = _parts(_deep(state="final"))
    assert final["ball"] == "" and final["marks"] is None and final["now"] == "", "nobody's ball, bonus or last play after the final"
    assert "hc-arrow" not in final["stage"] and "hc-run" not in final["stage"]
    # A final opens on its shot chart, with no Live view to choose (tests/test_a_finished_game_is_its_record.py).
    assert 'class="card gp-stage hc-stage v-shots"' in final["stage"] and 'data-hc-view="live"' not in final["stage"]
    assert "<b>Trends</b>" in final["statsExtra"] and "On pace for" not in final["statsExtra"]
    pre = _deep(state="scheduled")
    pre["plays"], pre["box"] = [], []
    pre["live"] = {"state": "scheduled", "start_time": "2026-10-15T23:30Z"}
    P = _parts(pre)
    assert (P["stage"], P["now"], P["statsExtra"], P["ball"], P["marks"]) == ("", "", "", "", None), \
        "before the tip there is no arena to draw: the page's own score says Tip-off"
    assert 'mlb: "First pitch", nba: "Tip-off", wnba: "Tip-off", cbb: "Tip-off", nhl: "Puck drop"' in APP


def test_the_views_draw_the_shots_the_five_and_the_flow():
    got = _node(f"""
      let redraws = 0, binds = 0;
      globalThis.renderPbpPage = () => {{ redraws++; }};
      const host = {{ dataset: {{}}, contains: () => true, querySelector: () => null,
                     addEventListener: (t, f) => {{ binds++; host["on" + t] = f; }} }};
      const ctx = {{ d: {json.dumps(_deep())}, league: "nba", boardGame: null, faces: {{}} }};
      const first = Q.parts(ctx);
      first.wire(host); Q.parts(ctx).wire(host);          // bound once, however often the page is drawn
      const click = (attr, v) => host.onclick({{ target: {{ closest: () => ({{ dataset: {{ [attr]: v }}, hasAttribute: () => false }}) }} }});
      const out = {{}};
      click("hcView", "shots"); out.shots = Q.parts(ctx).stage;
      click("hcShots", "away"); out.away = Q.parts(ctx).stage;
      click("hcView", "tracker"); out.tracker = Q.parts(ctx).stage;
      click("hcView", "flow"); out.flow = Q.parts(ctx).stage;
      out.redraws = redraws; out.binds = binds;
      return out;""", gc=True)
    if got is None:
        return
    spotted = [p for p in _deep()["plays"] if p.get("shot") and p["points_attempted"] >= 2]
    marks = lambda html: len(re.findall(r'class="hc-shot (?:made|miss)"', html))
    assert 'hc-stage v-shots' in got["shots"] and marks(got["shots"]) == len(spotted) == 8
    assert marks(got["away"]) == sum(1 for p in spotted if p["team"] == "LAL") == 5
    assert "LAL 4/5" in got["away"] and "BOS 3/3" in got["away"], "each side's makes over its tries"
    assert got["tracker"].count('class="hc-trk-row"') == 10 and "<b>On the floor</b>" in got["tracker"]
    assert "Payton Pritchard" in got["tracker"].split("hc-trk-col")[2] and "<b>Derrick White</b>" not in got["tracker"].split("hc-row")[0]
    assert 'class="hc-flow"' in got["flow"] and "lead changes" in got["flow"]
    # A reader's choice draws the page again (detail.js renderPbpPage), which keeps the picture already painted.
    assert (got["redraws"], got["binds"]) == (4, 1)
    # The view a reader scrolled inside keeps its place by name; another view starts at its top.
    assert 'class="hc-pane" data-gp-scroll="hc-tracker"' in got["tracker"] and 'data-gp-scroll="hc-flow"' in got["flow"]


# --- the page: the wiring ----------------------------------------------------------
def test_the_page_asks_for_the_parts_and_loads_the_file_the_way_the_others_are():
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    assert 'const GP_SPORT_FILE = { nba: "hoopscast", wnba: "hoopscast", cbb: "hoopscast", nhl: "rinkcast" };' in det
    mod = det[det.index("function gpSportMod(league, d) {"):det.index("function gpPlainKit(o) {")]
    assert "css.href = `css/${name}.css`;" in mod and "el.src = `js/${name}.js`;" in mod
    assert 'el.addEventListener("error", done("failed"));' in mod, "a file that will not load leaves the sport on the plain page"
    assert 'const done = (how) => () => { _gpSportFile[name] = how; if (state.view === "pbp") renderPbpPage(); };' in mod
    kit = det[det.index("function gpKit(o) {"):det.index("function gpStageHTML(")]
    assert "try { return { ...plain, ...mod.parts(o) }; } catch (e) {" in kit, "a part that throws leaves the page on the plain ones"
    assert "Loading the ${wait}…" in kit, "the page is drawn at once, and again when the file lands"
    # The old handover (js/gamecast.js `hoops`, a page of its own drawn into the host) is gone.
    assert "function hoops(" not in GC and "QBHoops" not in GC and "GC.hoops" not in det
    assert "function render(" not in HC and "host.innerHTML" not in HC, "the page is drawn by the page"
    assert not re.search(r'class="[^"]*\bgp-', HC), "the page's own class names are written by the page's builders"
    for inline in ("onclick", "onerror", "onload=", "onchange", "eval(", "new Function"):
        assert inline not in HC, f"{inline}: the page's CSP forbids it"
    for prose in ("p.text", ".shortDescription", ".description"):
        assert prose not in HC, prose
    assert "window.QBHoops = {\n    parts,\n" in HC
    nba = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert 'gd["home_ml"] = g.home_ml or None' in nba and 'gd["away_ml"] = g.away_ml or None' in nba, \
        "the board's NBA games carry their moneylines (the page's odds card, lineopen's closes)"


def test_the_redraw_keeps_the_picture_and_the_scroll():
    """The arenas' rule since 2026-10-15, the page's own now (detail.js gpHoldTake, gpHoldGive): the sport names
    what a redraw must leave as it is, and the page keeps it for every sport."""
    assert 'const PICTURE = `<picture data-gp-hold="arena">' in HC
    assert '`<div class="hc-pane" data-gp-scroll="hc-${view}">${pane}</div>`' in HC
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    page = det[det.index("async function renderPbpPage("):det.index("THE GAME PAGE IN THE CLUBS' COLOURS")]
    take, draw, give = (page.index("const held = one ? gpHoldTake(host, `${league}:${event}`) : null;"),
                        page.index("host.innerHTML = one ? gpPageHTML({"), page.index("gpHoldGive(host, held);"))
    assert take < draw < give
    give_fn = det[det.index("function gpHoldGive(host, held) {"):det.index("let _gpFor = ")]
    assert "if (fresh && fresh !== old) fresh.replaceWith(old);" in give_fn, "the picture on the screen is put back"
    assert "if (el) el.scrollTop = top;" in give_fn
    assert "if (!same) return null;" in det[det.index("function gpHoldTake(host, key) {"):det.index("function gpHoldGive(")], \
        "only for the game already on the screen"


def test_the_stylesheet_is_the_sites_tokens():
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b", HC_CSS):
        raise AssertionError(f"a raw colour in css/hoopscast.css: {m.group(0)}")
    for m in re.finditer(r"transition:[^;]+;", HC_CSS):
        assert "var(--dur-" in m.group(0) and "var(--ease-" in m.group(0), m.group(0)
    assert re.search(r"@media \(prefers-reduced-motion: reduce\) \{ \.hc-spot-ring \{ animation: none; \} \}", HC_CSS)
    styles = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    defined = set(re.findall(r"(--[\w-]+)\s*:", styles + HC_CSS + HC))
    for name in set(re.findall(r"var\((--[\w-]+)", HC_CSS + HC)):
        assert name in defined, f"{name} is read and never defined"
    assert ".hc-vs { display: none; }" in HC_CSS and ".hc-vl { display: none; }" in HC_CSS, "a phone reads the short tab words"
    for f in ("nba-arena.webp", "nba-arena.jpg", "nba-arena@640.webp", "nba-arena@640.jpg"):
        assert (ROOT / "web" / "img" / "arena" / f).exists(), f
    big = (ROOT / "web" / "img" / "arena" / "nba-arena.webp").stat().st_size
    small = (ROOT / "web" / "img" / "arena" / "nba-arena@640.webp").stat().st_size
    assert small < big < 300_000, (small, big)


# --- the page in a browser (opt-in) ------------------------------------------------
def test_the_page_in_a_browser_at_390_and_1280():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    doc = json.dumps(_deep())
    strip = json.dumps({"games": [{"event_id": "401810010", "home": "BOS", "away": "LAL", "live": _deep()["live"]}]})
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    # Nothing leaves the machine: fonts and logos are refused.
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nba_401810010.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=doc))
                    page.route("**/data/live_nba.json*", lambda r: r.fulfill(status=200, content_type="application/json", body=strip))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nba/401810010", wait_until="load")
                    page.wait_for_selector(".gp .hc-stage .hc-photo", timeout=15000)
                    page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                    page.wait_for_function("() => document.querySelector('.hc-photo').naturalWidth > 0", timeout=8000)
                    assert page.query_selector(".hc-svg .hc-flight"), "the last shot's flight"
                    # THE ONE PAGE, in football's order: the bar that stays, the score, the arena where the field
                    # is, the line score, the play right now, the tabs and the room behind them.
                    order = page.evaluate("""(() => {
                      const main = document.querySelector('.pbp-layout.gp .pbp-main');
                      const want = ['.gp-stick', '.pbp-hero', '.gp-stage', '.gp-line', '.gc-dv', '.pbp-tabs', '.pbp-panel'];
                      return want.map((sel) => { const el = main.querySelector(':scope > ' + sel); return el ? [...main.children].indexOf(el) : -1; });
                    })()""")
                    assert all(i >= 0 for i in order) and order == sorted(order), order
                    assert page.evaluate("[...document.querySelectorAll('.pbp-tabs .pbp-tab')].map((b) => b.textContent.trim())")[:4] == \
                        ["Stats", "Play-By-Play", "Standings", "Our picks"]
                    assert not page.query_selector(".hc-score") and not page.query_selector(".hc-plays"), "no page of its own"
                    # A live game opens on its plays: the period being played is open, its rows in sentences.
                    assert page.evaluate("document.querySelector('.pbp-tab.active').dataset.pbpTab") == "plays"
                    assert page.evaluate("document.querySelectorAll('details.gp-dr').length") == 2, "the 1st and the 2nd"
                    rows = page.evaluate("[...document.querySelectorAll('details.gp-dr[open] .lb-play')].map((r) => r.textContent.replace(/\\s+/g, ' ').trim())")
                    assert len(rows) == 8 and "Timeout, Celtics" in rows[0], rows[:2]
                    assert any("LeBron James makes a 3-point step-back jump shot" in r for r in rows), rows
                    # The score wears the scorer's table and the ball; the newest play is on the shared card.
                    assert page.evaluate("document.querySelector('.pbp-sb-side.away .hc-bonus').textContent") == "Bonus"
                    assert "Al Horford grabs a defensive rebound." in page.evaluate("document.querySelector('.gc-dv .gc-dv-said').textContent")
                    # The four views fit across a phone; nothing scrolls sideways.
                    assert page.evaluate("(() => { const v = document.querySelector('.hc-views'); return v.scrollWidth <= v.clientWidth + 1; })()")
                    page.click("[data-hc-view='shots']")
                    page.wait_for_selector(".hc-stage.v-shots")
                    assert len(page.query_selector_all(".hc-stage.v-shots .hc-svg .hc-shot")) == 8
                    page.click("[data-hc-view='tracker']")
                    page.wait_for_selector(".hc-stage.v-tracker")
                    assert len(page.query_selector_all(".hc-trk-row")) == 10
                    page.click("[data-hc-view='flow']")
                    page.wait_for_selector(".hc-pane .hc-flow")
                    page.click("[data-hc-view='live']")
                    page.wait_for_selector(".hc-stage.v-live")
                    # A redraw keeps the picture already painted (detail.js gpHoldGive).
                    page.evaluate("document.querySelector('.hc-photo').__kept = 1")
                    assert page.evaluate("renderPbpPage().then(() => document.querySelector('.hc-photo').__kept === 1)"), \
                        "the redraw painted a new picture"
                    # The Stats room: the page's team stats and box scores, then basketball's own two cards.
                    page.click(".pbp-tabs [data-pbp-tab='stats']")
                    page.wait_for_selector(".pbp-panel[data-pbp-panel='stats'] .hc-card")
                    heads = page.evaluate("[...document.querySelectorAll('.pbp-panel .gp-card-head b')].map((b) => b.textContent)")
                    assert heads.index("Lakers") < heads.index("Celtics") < heads.index("Shot chart") < heads.index("Trends"), heads
                    assert page.evaluate("document.scrollingElement.scrollWidth") <= width
                    assert not errors, errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


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
