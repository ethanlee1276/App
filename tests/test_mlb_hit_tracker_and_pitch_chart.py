"""Every ball a hitter put in play, every pitch a pitcher threw: baseball's charts.

Ethan, 2026-10-13: "Can we do a hit tracker for mlb?", then "Yes do all of
them ... make sure they are all routed correctly like nfl."

What is pinned, offline, on a fixture play-by-play and databases built here:

  * THE FOLD (engine/mlb/charts.fold): one row per completed plate
    appearance with the ball in play where there was one, on the batting
    side's team key (the away team bats in the top); one row per pitch; a
    play that is not a plate appearance (an inning ending on a caught
    stealing) keeps its pitches and writes no plate appearance;
  * THE GAMES: only finals of the regular season and the postseason;
    a game already stored is never read again; a season's backlog is read
    newest first, a night's budget at a time;
  * THE HIT TRACKER: his line the box score's way (an at-bat excludes a
    walk, a hit by pitch and a sacrifice), hard hit at 95 mph, pulled or
    opposite field by where it landed and his side, against right- and
    left-handers;
  * THE PITCH CHART: called strikes, whiffs and swings by the CSW
    measure's own codes (a foul tip is contact), his mix, the zone's boxes,
    his fastball's speed start by start, and every batter he faced;
  * THE DOOR AND THE PAGE: /api/players/chart serves both; the drawings
    load as their own module the first time one is drawn; a pitcher's bet
    draws his pitches, a hitter's his balls in play; every baseball bet
    has a chart slot and a parlay door.

Run directly: `python3 tests/test_mlb_hit_tracker_and_pitch_chart.py`
"""
import inspect
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

from engine import charts as CH, db as D, maintenance as M  # noqa: E402
from engine.mlb import charts as MC  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
MLB_JS = (ROOT / "web" / "js" / "chart-mlb.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
SLIP_JS = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")

JUDGE, SOTO, COLE, SKUBAL = 592450, 665742, 543037, 669373
GAME = {"game_pk": 776001, "date": "2026-10-11", "home": "NYY", "away": "DET", "type": "D"}


def _pitch(n, code, t="FF", v=97.1, px=0.1, pz=2.5, zone=5, balls=0, strikes=1, hit=None):
    ev = {"isPitch": True, "pitchNumber": n, "details": {"call": {"code": code}, "type": {"code": t}},
          "count": {"balls": balls, "strikes": strikes},
          "pitchData": {"startSpeed": v, "strikeZoneTop": 3.4, "strikeZoneBottom": 1.6, "zone": zone,
                        "coordinates": {"pX": px, "pZ": pz}, "breaks": {"spinRate": 2350}}}
    if hit:
        ev["hitData"] = hit
    return ev


def _play(ab, half, batter, pitcher, event, etype, events, side="R", hand="R", rbi=0, inning=1):
    return {"result": {"event": event, "eventType": etype, "rbi": rbi},
            "about": {"atBatIndex": ab, "halfInning": half, "inning": inning},
            "matchup": {"batter": {"id": batter[0], "fullName": batter[1]}, "batSide": {"code": side},
                        "pitcher": {"id": pitcher[0], "fullName": pitcher[1]}, "pitchHand": {"code": hand}},
            "playEvents": [{"isPitch": False, "details": {"description": "Mound visit"}}] + events}


J, S_, C_, K_ = (JUDGE, "Aaron Judge"), (SOTO, "Juan Soto"), (COLE, "Gerrit Cole"), (SKUBAL, "Tarik Skubal")
PAYLOAD = {"allPlays": [
    # Top 1: Detroit bats, Cole pitches.
    _play(0, "top", (111, "Riley Greene"), C_, "Strikeout", "strikeout",
          [_pitch(1, "C"), _pitch(2, "S", t="SL", v=88.0, px=0.9, pz=1.2, zone=14),
           _pitch(3, "T", t="SL", v=87.5)], side="L"),
    # Bottom 1: New York bats, Skubal pitches (left-handed).
    _play(1, "bottom", J, K_, "Home Run", "home_run",
          [_pitch(1, "B", t="CH", v=86.0, px=-1.2, pz=1.0, zone=13, strikes=0, balls=1),
           _pitch(2, "X", v=97.8, hit={"launchSpeed": 110.4, "launchAngle": 28, "totalDistance": 431,
                                        "trajectory": "fly_ball", "hardness": "hard", "location": "7",
                                        "coordinates": {"coordX": 60.0, "coordY": 60.0}})],
          hand="L", rbi=1),
    _play(2, "bottom", S_, K_, "Walk", "walk",
          [_pitch(i + 1, "B", px=1.5, zone=12, balls=i + 1, strikes=0) for i in range(4)], side="L", hand="L"),
    _play(3, "bottom", J, K_, "Single", "single",
          [_pitch(1, "D", v=96.0, hit={"launchSpeed": 92.0, "launchAngle": 9, "totalDistance": 180,
                                        "trajectory": "line_drive", "hardness": "medium", "location": "9",
                                        "coordinates": {"coordX": 190.0, "coordY": 120.0}})], hand="L",
          inning=3),
    # An inning that ends on the bases: the pitches count, the plate
    # appearance does not.
    _play(4, "bottom", S_, K_, "Caught Stealing 2B", "caught_stealing_2b", [_pitch(1, "F")], side="L", hand="L",
          inning=3),
    {"result": {}, "about": {"atBatIndex": 5, "halfInning": "top"}, "matchup": {}, "playEvents": []},  # in progress
]}


def _conn(path=":memory:"):
    conn = D.connect(path)
    pas, pitches = MC.fold(PAYLOAD, GAME)
    D.upsert_mlb_pa(conn, pas)
    D.upsert_mlb_pitches(conn, pitches)
    # Judge's earlier game, a 0-for with a groundout pulled to the left side.
    g2 = dict(GAME, game_pk=775900, date="2026-10-05", home="NYY", away="KC", type="R")
    pas2, pitches2 = MC.fold({"allPlays": [
        _play(0, "bottom", J, (600, "Seth Lugo"), "Groundout", "field_out",
              [_pitch(1, "X", v=95.0, hit={"launchSpeed": 101.0, "launchAngle": -5, "totalDistance": 20,
                                            "trajectory": "ground_ball", "hardness": "hard", "location": "6",
                                            "coordinates": {"coordX": 100.0, "coordY": 160.0}})], hand="R"),
    ]}, g2)
    D.upsert_mlb_pa(conn, pas2)
    D.upsert_mlb_pitches(conn, pitches2)
    return conn


# --- the fold ------------------------------------------------------------------------
def test_one_row_per_plate_appearance_and_per_pitch():
    pas, pitches = MC.fold(PAYLOAD, GAME)
    assert [p["at_bat"] for p in pas] == [0, 1, 2, 3], "a caught stealing and an at-bat in progress are no PA"
    assert len(pitches) == 3 + 2 + 4 + 1 + 1, "every pitch, the caught-stealing at-bat's included; no mound visit"
    hr = pas[1]
    assert (hr["batter"], hr["team"], hr["opponent"], hr["home"], hr["half"]) == ("Aaron Judge", "NYY", "DET", 1, "B")
    assert (hr["pitcher"], hr["pitch_hand"], hr["bat_side"]) == ("Tarik Skubal", "L", "R")
    assert hr["launch_speed"] == 110.4 and hr["distance"] == 431 and hr["trajectory"] == "fly_ball"
    assert (hr["coord_x"], hr["coord_y"], hr["location"], hr["rbi"], hr["pitches"]) == (60.0, 60.0, "7", 1, 2)
    k = pas[0]
    assert (k["team"], k["opponent"], k["home"], k["launch_speed"]) == ("DET", "NYY", 0, None)
    p = pitches[1]
    assert (p["pitcher_id"], p["pitch_type"], p["speed"], p["zone"], p["code"]) == (COLE, "SL", 88.0, 14, "S")
    assert (p["px"], p["pz"], p["sz_top"], p["spin"], p["season"], p["date"]) == (0.9, 1.2, 3.4, 2350.0, 2026, "2026-10-11")


def test_only_finals_of_the_season_and_the_postseason():
    def g(pk, kind="R", state="Final", coded="F", home=147, away=116):
        return {"gamePk": pk, "gameType": kind, "officialDate": "2026-10-11",
                "status": {"abstractGameState": state, "codedGameState": coded},
                "teams": {"home": {"team": {"id": home}}, "away": {"team": {"id": away}}}}
    sched = {"dates": [{"games": [g(1), g(2, kind="D"), g(3, kind="S"), g(4, state="Live"), g(5, coded="D"),
                                  g(6, kind="A")]}]}
    got = MC.finals(sched)
    assert [x["game_pk"] for x in got] == [1, 2], "spring, the All-Star Game, live and postponed games are out"
    assert got[0]["home"] == "NYY" and got[0]["away"] == "DET"


def test_a_game_is_read_once_and_the_backlog_newest_first():
    conn = D.connect(":memory:")
    asked = []

    def fetch(pk):
        asked.append(pk)
        return PAYLOAD if pk != 3 else None
    games = [dict(GAME, game_pk=pk, date=f"2026-09-{pk:02d}") for pk in (1, 2, 3)]
    out = MC.ingest_games(conn, games, fetch=fetch, workers=1)
    assert out["games"] == 2 and out["failed"] == 1 and out["pas"] == 8 and out["pitches"] == 22
    assert MC.ingest_games(conn, games, fetch=fetch, workers=1)["games"] == 0
    assert sorted(asked) == [1, 2, 3, 3], "a stored game is never fetched again; an unread one is tried again"
    from engine.mlb.sources import mlbstats

    def sched(start, end):
        return {"dates": [{"games": [{"gamePk": pk, "gameType": "R", "officialDate": f"2026-09-{pk:02d}",
                                      "status": {"abstractGameState": "Final", "codedGameState": "F"},
                                      "teams": {"home": {"team": {"id": 147}}, "away": {"team": {"id": 116}}}}
                                     for pk in range(1, 8)]}]}
    keep = mlbstats.fetch_schedule
    mlbstats.fetch_schedule = sched
    try:
        asked.clear()
        got = MC.backfill(conn, 2026, "2026-10-12", budget=2, fetch=fetch)
    finally:
        mlbstats.fetch_schedule = keep
    assert asked == [7, 6] and got["games"] == 2 and got["left"] == 3, "newest first, a night's budget at a time"


def test_the_backfill_reads_an_old_game_without_keeping_its_file():
    """A season of ~640 KB payloads is ~1.5 GB the cache would keep for a
    month after their rows are stored: the backfill lets each one go. A
    copy that was already there (a starter's recent game the nightly
    reads) is left alone."""
    from engine.mlb.sources import mlbstats, pbp
    tmp = Path(tempfile.mkdtemp())
    keep = (mlbstats.CACHE_DIR, pbp.fetch_playbyplay)

    def fetch(pk):                                # the cached read: writes its file
        (tmp / f"mlb_pbp_{pk}.json").write_text(json.dumps(PAYLOAD))
        return PAYLOAD
    try:
        mlbstats.CACHE_DIR, pbp.fetch_playbyplay = tmp, fetch
        (tmp / "mlb_pbp_2.json").write_text("{}")
        assert MC.read_once(1) == PAYLOAD and not (tmp / "mlb_pbp_1.json").exists(), "its own file goes"
        assert MC.read_once(2) == PAYLOAD and (tmp / "mlb_pbp_2.json").exists(), "a file it found stays"
        assert "fetch or read_once" in inspect.getsource(MC.backfill)
        assert "read_once" not in inspect.getsource(MC.ingest_range), \
            "yesterday's finals keep their files: the nightly's own readers want them"
    finally:
        mlbstats.CACHE_DIR, pbp.fetch_playbyplay = keep
        shutil.rmtree(tmp, ignore_errors=True)


# --- the hit tracker ---------------------------------------------------------------------
def test_the_hit_tracker_reads_his_line_the_box_scores_way():
    d = MC.hits_chart(_conn(), "Aaron Judge")
    assert d["player"] == "Aaron Judge" and d["season"] == 2026 and d["side"] == "R"
    assert [g["id"] for g in d["games"]] == [776001, 775900], "newest first"
    L = d["games"][0]["line"]
    assert (L["pa"], L["ab"], L["h"], L["tb"], L["hr"], L["rbi"], L["bb"], L["k"]) == (2, 2, 2, 5, 1, 1, 0, 0)
    assert L["hard"] == 1 and L["bip"] == 2 and L["avg"] == 1.0
    S = d["season_line"]
    assert (S["pa"], S["ab"], S["h"], S["hard"]) == (3, 3, 2, 2), "the groundout at 101 is hard hit too"
    hr, single = d["games"][0]["pas"]
    assert hr["dir"] == "pull" and single["dir"] == "oppo", "a right-hander pulls to left field"
    assert {x["key"]: x["n"] for x in d["by_type"]} == {"ground_ball": 1, "line_drive": 1, "fly_ball": 1}
    assert {x["key"]: x["h"] for x in d["by_hand"]} == {"R": 0, "L": 2}
    soto = MC.hits_chart(_conn(), "juan soto")
    assert soto["season_line"]["bb"] == 1 and soto["season_line"]["ab"] == 0, "a walk is no at-bat"
    assert MC.hits_chart(_conn(), "Nobody Here") == {}
    assert MC.direction(125.42, 100, "L") == "center" and MC.direction(60, 60, "L") == "oppo"


# --- the pitch chart ---------------------------------------------------------------------
def test_the_pitch_chart_reads_his_mix_his_zones_and_who_he_faced():
    d = MC.pitches_chart(_conn(), "Tarik Skubal")
    assert d["hand"] == "L" and d["team"] == "DET" and d["games"][0]["opp"] == "NYY"
    assert d["games"][0]["home"] is False, "he pitched in the bottom half: the road side"
    L = d["season_line"]
    assert (L["pitches"], L["bf"], L["k"], L["bb"], L["h"], L["hr"]) == (8, 3, 0, 1, 2, 1)
    assert L["whiffs"] == 0 and L["called"] == 0 and L["swings"] == 3, "two balls in play and a foul"
    assert [x["b"] for x in d["games"][0]["faced"]] == ["Aaron Judge", "Juan Soto", "Aaron Judge"]
    mix = {m["type"]: m for m in d["mix"]}
    assert mix["FF"]["n"] == 7 and mix["CH"]["n"] == 1 and d["mix"][0]["type"] == "FF"
    zones = {z["zone"]: z["n"] for z in d["zones"]}
    assert zones[12] == 4 and zones[13] == 1 and zones[5] == 3 and len(d["zones"]) == 13
    assert d["velo_type"] == "FF" and d["velo"][0]["n"] == 7
    cole = MC.pitches_chart(_conn(), "Gerrit Cole")
    C = cole["season_line"]
    assert (C["k"], C["whiffs"], C["called"], C["swings"]) == (1, 1, 1, 2), "a foul tip is contact, not a whiff"
    assert C["csw"] == round(2 / 3, 3)
    assert MC.pitches_chart(_conn(), "Aaron Judge") == {}, "a hitter has no pitch chart"


# --- the door, the nightly, the page -----------------------------------------------------------
def test_the_door_serves_both():
    import server
    tmp = tempfile.mkdtemp()
    keep = D.DEFAULT_DB
    sent = []
    try:
        path = Path(tmp) / "history.db"
        D.connect(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._players_chart({"kind": ["spray"], "sport": ["mlb"], "player": ["Aaron Judge"]})
        _conn(path).close()
        h._players_chart({"kind": ["spray"], "sport": ["mlb"], "player": ["Aaron Judge"]})
        h._players_chart({"kind": ["pitches"], "sport": ["mlb"], "player": ["Gerrit Cole"]})
        h._players_chart({"kind": ["spray"], "sport": ["nfl"], "player": ["Aaron Judge"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True})
    assert sent[1][0] == 200 and sent[1][1]["kind"] == "spray" and sent[1][1]["season_line"]["hr"] == 1
    assert sent[2][0] == 200 and sent[2][1]["kind"] == "pitches" and "face" in sent[2][1]
    assert sent[3][0] == 400
    assert CH.known("spray", "mlb") and CH.known("pitches", "mlb") and not CH.known("spray", "nba")


def test_the_nightly_reads_the_finals_and_the_backlog():
    src = inspect.getsource(M._run_chores)
    assert "_mlbc.ingest_range(_mc, start.isoformat(), yesterday.isoformat())" in src
    assert "_mlbc.backfill(_mc, today.year, yesterday.isoformat())" in src
    assert 200 <= MC.BACKFILL_PER_NIGHT <= 600


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{MLB_JS}\n"
            f"console.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_both():
    hit, pit = MC.hits_chart(_conn(), "Aaron Judge"), MC.pitches_chart(_conn(), "Tarik Skubal")
    got = _node(f"""
      const h = {json.dumps(hit)}, p = {json.dumps(pit)}, SP = T.DRAW.spray, PI = T.DRAW.pitches;
      const g = h.games[0], pg = p.games[0];
      const sg = SP.game(g, h), ss = SP.season(h), pgm = PI.game(pg, p), ps = PI.season(p);
      return {{
        balls: (sg.match(/class="mb-ball cx-mark/g) || []).length, hr: (sg.match(/mb-ball cx-mark hr/g) || []).length,
        seasonBalls: (ss.match(/class="mb-ball /g) || []).length, pulled: ss.includes("Pulled"),
        list: SP.list(g, h), tiles: SP.gameSide(g, h), side: SP.seasonSide(h), tables: SP.splits(h),
        chip: SP.chip(g), count: SP.count(h.season_line), tip: SP.tip(g.pas[0], g, h),
        dots: (pgm.match(/class="mp cx-mark/g) || []).length, cells: (ps.match(/class="mp-cell"/g) || []).length,
        plist: PI.list(pg, p), pside: PI.gameSide(pg, p), pchip: PI.chip(pg), pmix: PI.splits(p),
        kinds: [T.kindsFor("mlb", "strikeouts", "P"), T.kindsFor("mlb", "outs", ""), T.kindsFor("mlb", "hits", "OF"),
                T.kindsFor("mlb", "total_bases", ""), T.kindsFor("mlb", "home_runs", "DH")],
        titles: [T.KIND.spray.title, T.KIND.pitches.title],
      }};
    """)
    if got is None:
        return
    assert got["balls"] == 2 and got["hr"] == 1 and got["seasonBalls"] == 3 and got["pulled"]
    assert ">HR<" in got["list"] and ">1B<" in got["list"] and "vs Tarik Skubal (L)" in got["list"]
    assert "110 mph · 28° · 431 ft · fly ball" in got["list"] and ">Hard hit<" in got["list"]
    assert ">2-2<" in got["tiles"] and "Total bases" in got["tiles"] and ">5<" in got["tiles"]
    assert "Exit velocity" in got["side"] and "Sweet spot" in got["side"]
    assert "Against right- and left-handers" in got["tables"] and "By where he hit it" in got["tables"]
    assert got["chip"] == "2-2, 1 HR" and got["count"] == "3 plate appearances" and "431 ft" in got["tip"]
    assert got["dots"] == 8 and got["cells"] == 13
    assert "Aaron Judge (R)" in got["plist"] and "4 pitches" in got["plist"] and ">BB<" in got["plist"]
    assert "This game’s mix" in got["pside"] and "Four-seam" in got["pside"]
    assert got["pchip"] == "0 K · 8p" and "His pitch mix" in got["pmix"]
    assert got["kinds"] == [["pitches"], ["pitches"], ["spray"], ["spray"], ["spray"]]
    assert got["titles"] == ["Hit tracker", "Pitch chart"]


def test_every_door_and_the_module():
    i = APP_JS.index("function chartSlot(")
    assert ': lg === "mlb";' in APP_JS[i:i + 500], "every baseball bet leaves a slot"
    i = SLIP_JS.index("function chartsHTML(")
    assert '["pitches", "Pitch chart"] : ["spray", "Hit tracker"]' in SLIP_JS[i:i + 700]
    assert 'const PLUG = { spray: "mlb", pitches: "mlb" };' in CC_JS
    assert "el.src = `js/chart-${f}.js`;" in CC_JS and 'el.addEventListener("load"' in CC_JS
    assert "window.QBCarry.plug" in MLB_JS and 'Q.draw("spray"' in MLB_JS and 'Q.draw("pitches"' in MLB_JS
    for js in (CC_JS, MLB_JS):
        assert "onclick" not in js and "onerror" not in js and not re.search(r"on(error|load)\s*=", js)
    for cls in (".mb-grass", ".mb-ball.hr", ".mb-arc.sel", ".mp-zone", ".mp.w", ".mp-cell", ".mp-line"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
