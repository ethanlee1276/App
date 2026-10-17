"""Every shot a skater took and every shot a goalie faced: hockey's charts.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl."

What is pinned, offline, on shots stored the way engine/sources/nhlpbp
stores them for the xG model:

  * ONE END OF THE RINK: an attempt at the other net is turned a half
    turn to face the net at +89 (his left stays his left), read off the
    distance the row was measured with;
  * THE SHOT MAP: attempts, on goal (goals included), missed and blocked
    the way the box score counts them, the goals with their assists, the
    goalie each one went at, expected goals from our model on unblocked
    attempts only, the distance bands, kind of shot and strength splits;
  * THE SAVE MAP: only shots on goal he faced, no empty net; save
    percentage and saved-above-expected the way the board counts them
    (xg.summaries);
  * THE DOOR AND THE PAGE: /api/players/chart serves both; a goalie's
    saves or goals against draw his save map and a skater's bet his shot
    map; the drawing loads as its own module; every hockey leg in the
    parlay checker has its door.

Run directly: `python3 tests/test_a_shot_map_and_save_map_for_hockey.py`
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

from engine import charts as CH, db as D  # noqa: E402
from engine.nhl import charts as HC  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
NHL_JS = (ROOT / "web" / "js" / "chart-nhl.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
SLIP_JS = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")


def _shot(gid, ev, kind, x, y, dist, shooter="Auston Matthews", goalie="Igor Shesterkin", team="TOR",
          opp="NYR", date="2025-11-01", per=1, st="EV", en=0, reb=0, rush=0, a1="", a2="", stype="wrist"):
    return {"game_id": gid, "event_id": ev, "date": date, "season": 2025, "team": team, "opponent": opp,
            "shooter_id": "8479318", "shooter": shooter, "goalie_id": "8478048", "goalie": goalie,
            "kind": kind, "x": x, "y": y, "dist": dist, "angle": 10.0, "shot_type": stype, "strength": st,
            "empty_net": en, "rebound": reb, "rush": rush, "is_goal": int(kind == "goal"), "period": per,
            "assist1": a1, "assist2": a2}


def _conn():
    conn = D.connect(":memory:")
    D.upsert_nhl_shots(conn, [
        _shot(2025020101, 10, "goal", 80.0, -4.0, 9.8, a1="Mitch Marner", a2="William Nylander", rush=1),
        _shot(2025020101, 11, "sog", 70.0, 10.0, 21.5, st="PP"),
        _shot(2025020101, 12, "miss", -75.0, 8.0, 16.1, per=2),          # at the other net
        _shot(2025020101, 13, "block", 55.0, -20.0, 39.4, per=2),
        _shot(2025020101, 14, "goal", 50.0, 0.0, 39.0, per=3, en=1),    # into an empty net
        _shot(2025020090, 3, "sog", 84.0, 2.0, 5.4, date="2025-10-28", opp="BOS", goalie="Jeremy Swayman",
              reb=1),
    ])
    D.upsert_games(conn, [{"sport": "nhl", "season": 2025, "period": "2025-11-01", "game_id": "NYR@TOR",
                           "home": "TOR", "away": "NYR", "home_score": 4.0, "away_score": 2.0, "date": "2025-11-01"}])
    return conn


def test_every_attempt_faces_the_same_net():
    assert HC.facing(80.0, 5.0, 10.3) == (80.0, 5.0)
    assert HC.facing(-80.0, 5.0, 10.3) == (80.0, -5.0), "a half turn, never a mirror"
    assert HC.facing(-75.0, 8.0, 16.1) == (75.0, -8.0)
    assert HC.facing(None, 1.0, 5.0) == (None, None)
    assert [HC.band(d) for d in (4, 12, 30, 55, None)] == ["crease", "slot", "high", "point", ""]


def test_the_shot_map_counts_his_attempts_the_box_scores_way():
    conn = _conn()
    keep = HC._model
    HC._model = lambda: {"league": 0.07, "cells": {"d0": 0.25, "d1": 0.12, "d2": 0.06, "d3": 0.04}}
    try:
        d = HC.shot_map(conn, "auston matthews")
    finally:
        HC._model = keep
    assert d["player"] == "Auston Matthews" and d["role"] == "skater" and d["season_label"] == "2025-26"
    g = d["games"][0]
    assert g["date"] == "2025-11-01" and g["opp"] == "NYR" and g["home"] is True
    L = g["line"]
    assert (L["att"], L["sog"], L["goals"], L["miss"], L["blocked"], L["pp"]) == (5, 3, 2, 1, 1, 1)
    shots = {s["i"]: s for s in g["shots"]}
    assert shots[10]["a"] == ["Mitch Marner", "William Nylander"] and shots[10]["vs"] == "Igor Shesterkin"
    assert (shots[12]["x"], shots[12]["y"]) == (75.0, -8.0), "turned to face the net at the top"
    assert "xg" not in shots[13], "a blocked attempt has no expected goals"
    assert shots[14]["xg"] == 0.6 and shots[14]["en"] == 1, "an open net is the model's own empty-net rate"
    assert d["games"][1]["home"] is None, "a game the games table lacks says neither"
    S = d["season_line"]
    assert S["games"] == 2 and S["sog"] == 4 and S["goals"] == 2 and S["sog_pg"] == 2.0
    zones = {z["key"]: z for z in d["zones"]}
    assert zones["crease"]["n"] == 2 and zones["crease"]["goals"] == 1 and zones["point"]["n"] == 2
    assert {s["key"] for s in d["by_strength"]} == {"EV", "PP"} and d["xg_model"] is True


def test_the_save_map_counts_shots_on_goal_he_faced():
    conn = _conn()
    keep = HC._model
    HC._model = lambda: {"league": 0.07, "cells": {"d0": 0.25, "d1": 0.12, "d2": 0.06, "d3": 0.04}}
    try:
        d = HC.save_map(conn, "Igor Shesterkin")
    finally:
        HC._model = keep
    assert d["role"] == "goalie" and d["team"] == "NYR" and d["games"][0]["opp"] == "TOR"
    L = d["season_line"]
    # The goal (9.8 ft), the power-play shot on goal (21.5 ft); never the
    # miss, the block or the empty net.
    assert (L["shots"], L["saves"], L["ga"]) == (2, 1, 1) and L["sv_pct"] == 0.5
    assert L["xga"] == round(0.25 + 0.06, 2) and L["gsax"] == round(0.31 - 1, 2)
    assert {s["by"] for s in d["games"][0]["shots"]} == {"Auston Matthews"}
    assert HC.save_map(conn, "Auston Matthews") == {}, "a skater has no save map"
    assert HC.shot_map(conn, "Nobody") == {}


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
        h._players_chart({"kind": ["shotmap"], "sport": ["nhl"], "player": ["Auston Matthews"]})
        c = D.connect(path)
        src = _conn()
        D.upsert_nhl_shots(c, [dict(r) for r in src.execute("SELECT * FROM nhl_shots")])
        c.close()
        h._players_chart({"kind": ["shotmap"], "sport": ["nhl"], "player": ["Auston Matthews"]})
        h._players_chart({"kind": ["saves"], "sport": ["nhl"], "player": ["Igor Shesterkin"]})
        h._players_chart({"kind": ["saves"], "sport": ["nba"], "player": ["Igor Shesterkin"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True})
    assert sent[1][0] == 200 and sent[1][1]["kind"] == "shotmap" and sent[1][1]["season_line"]["goals"] == 2
    assert sent[2][0] == 200 and sent[2][1]["kind"] == "saves" and "face" in sent[2][1]
    assert sent[3][0] == 400
    assert CH.known("shotmap", "nhl") and CH.known("saves", "nhl") and not CH.known("shotmap", "nba")


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{NHL_JS}\n"
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


def test_the_page_draws_the_rink():
    conn = _conn()
    sk, gk = HC.shot_map(conn, "Auston Matthews"), HC.save_map(conn, "Igor Shesterkin")
    got = _node(f"""
      const s = {json.dumps(sk)}, k = {json.dumps(gk)}, A = T.DRAW.shotmap, B = T.DRAW.saves;
      const g = s.games[0], kg = k.games[0];
      const game = A.game(g, s), season = A.season(s), save = B.game(kg, k);
      return {{
        marks: (game.match(/class="nh-mark cx-mark/g) || []).length, goals: (game.match(/cx-mark goal/g) || []).length,
        blocks: (game.match(/cx-mark block/g) || []).length, faint: (season.match(/nh-mark faint/g) || []).length,
        pills: (season.match(/class="nh-pill"/g) || []).length, saved: (save.match(/cx-mark sv/g) || []).length,
        allowed: (save.match(/cx-mark ga/g) || []).length,
        list: A.list(g, s), tiles: A.gameSide(g, s), side: A.seasonSide(s), tables: A.splits(s), chip: A.chip(g),
        count: A.count(s.season_line), glist: B.list(kg, k), gtiles: B.gameSide(kg, k), gchip: B.chip(kg),
        gcount: B.count(k.season_line), note: B.note(),
        kinds: [T.kindsFor("nhl", "sog", "C"), T.kindsFor("nhl", "saves", "G"), T.kindsFor("nhl", "goals_against", ""),
                T.kindsFor("nhl", "anytime_goal", ""), T.kindsFor("nhl", "", "")],
        titles: [T.KIND.shotmap.title, T.KIND.saves.title], label: T.gameTitle(g, "nhl", "2025-26"),
      }};
    """)
    if got is None:
        return
    assert got["marks"] == 5 and got["goals"] == 2 and got["blocks"] == 1
    assert got["faint"] == 6 and got["pills"] >= 2 and got["saved"] == 1 and got["allowed"] == 1
    assert "Assists Mitch Marner, William Nylander" in got["list"] and "on Igor Shesterkin" in got["list"]
    assert "Power play" in got["list"] and ">Blocked<" in got["list"] and "Off the rush" in got["list"]
    assert "our model" in got["tiles"] and ">3<" in got["tiles"] and "Shooting" in got["side"]
    assert "By distance from the net" in got["tables"] and "By strength" in got["tables"]
    assert got["chip"] == "3 SOG, 2 G" and got["count"] == "6 attempts", "the season: both games"
    assert "by Auston Matthews" in got["glist"] and "Save %" in got["gtiles"] and ">GSAx<" in got["gtiles"]
    assert got["gchip"] == "1/2 saved"
    assert got["gcount"] == "2 shots faced" and "an empty net is not his" in got["note"]
    assert got["kinds"] == [["shotmap", "role"], ["saves", "role"], ["saves", "role"], ["shotmap", "role"], []]
    assert got["titles"] == ["Shot map", "Save map"] and got["label"].startswith("2025-26 vs NYR")


def test_every_door_and_the_module():
    # Every leg's door asks for his charts with its bet (2026-10-14): a
    # goalie's saves draw his save map, a skater's leg his shot map
    # (kindsFor, pinned above).
    i = SLIP_JS.index("function chartsHTML(")
    assert '/^(nfl|cfb|nba|wnba|nhl|mlb)$/.test(lg)' in SLIP_JS[i:i + 400]
    assert 'data-kind="auto" data-mkt="${esc(l.market || "")}"' in SLIP_JS[i:i + 600]
    assert 'shotmap: "nhl", saves: "nhl"' in CC_JS and 'Q.draw("shotmap"' in NHL_JS and 'Q.draw("saves"' in NHL_JS
    assert "onclick" not in NHL_JS and "onerror" not in NHL_JS and not re.search(r"on(error|load)\s*=", NHL_JS)
    for cls in (".nh-svg", ".nh-ice", ".nh-crease", ".nh-mark.goal", ".nh-mark.ga", ".nh-pill rect", ".dt.nh-sv"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
