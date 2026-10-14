"""Every fight a fighter has had: the UFC fight history.

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list
had UFC fight history and finish times on it.

What is pinned, offline, on fights shaped like ESPN's MMA records:

  * THE RECORD'S ROWS (engine/ufc/history.rows): won, lost or neither; how
    it ended; the round and the time in it for a stoppage, the scheduled
    rounds and 5:00 for a decision; how long it lasted; both men's
    numbers where ESPN tracked the bout; a bout with no id is no row;
  * ESPN'S FIGHT LOG (engine/sources/espnmma.fight_log): the opponent's
    name read when the history asks for it and not otherwise, an upcoming
    bout never in the history, newest first;
  * THE LINES AND SPLITS: his record, finishes won and lost, how often he
    goes the distance, first-round finishes, the average fight, by method,
    three rounds and five, and when his fights end, decisions last;
  * THE FILL: a few fighters a tick, a fighter read again only when stale,
    one ESPN cannot find remembered (not retried every tick), a re-read
    replacing what was there, and the scheduler's UFC tick calling it for
    the upcoming card without touching a dossier;
  * THE DOOR AND THE PAGE: /api/players/chart answers kind=fights for UFC
    only, with his photo off his ESPN id; every fighter block has the
    door; the drawing is its own module, CSP-clean, tokens only.

Run directly: `python3 tests/test_a_fight_history_for_every_fighter.py`
"""
import datetime as dt
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import charts as CH, db as D  # noqa: E402
from engine.sources import espnmma as E  # noqa: E402
from engine.ufc import history as H  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
UF_JS = (ROOT / "web" / "js" / "chart-ufc.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _fight(cid, date, winner, method, period, clock, secs, rounds=3, opp="Opponent", own=None, opp_row=None):
    return {"event_id": f"6{cid}", "comp_id": cid, "date": dt.date.fromisoformat(date), "winner": winner,
            "method": method, "duration_s": secs, "rounds": rounds, "division_text": "Lightweight",
            "period": period, "clock": clock, "opp_id": f"9{cid}", "opp_name": opp,
            "own_row": own, "opp_row": opp_row}


#: Six bouts, newest first as fight_log hands them: a second-round
#: knockout win (3:12 in), a five-round decision win, a first-round
#: submission loss, a split draw, a first-round knockout win, and one
#: whose ending ESPN does not have; and a bout with no id (no row).
FIGHTS = [
    _fight("401", "2026-08-02", True, "KO/TKO", 2, 192, 492.0, opp="Dan Hooker",
           own={"ssl": 41, "ssa": 77, "tdl": 1, "tda": 3, "kd": 1, "sm": 0},
           opp_row={"ssl": 22, "ssa": 60, "tdl": 0, "tda": 1, "kd": 0, "sm": 0}),
    _fight("402", "2026-03-08", True, "DEC", 5, 300, 1500.0, rounds=5, opp="Mateusz Gamrot",
           own={"ssl": 120, "ssa": 260}, opp_row={"ssl": 98, "ssa": 240}),
    _fight("403", "2025-10-18", False, "SUB", 1, 151, 151.0, opp="Charles Oliveira"),
    _fight("404", "2025-05-03", None, "DEC", 3, 300, 900.0, opp="Beneil Dariush"),
    _fight("405", "2024-12-14", True, "KO/TKO", 1, 45, 45.0, opp="Renato Moicano"),
    _fight("406", "2024-06-01", True, None, None, None, 900.0, opp=""),
    _fight("", "2024-01-01", True, "DEC", 3, 300, 900.0),
]


def _conn(path=":memory:"):
    conn = D.connect(path)
    D.upsert_ufc_fights(conn, H.rows("Arman Tsarukyan", "3949584", FIGHTS))
    return conn


def test_the_record_s_rows():
    rows = H.rows("Arman Tsarukyan", "3949584", FIGHTS)
    assert [r["comp_id"] for r in rows] == ["401", "402", "403", "404", "405", "406"], "a bout with no id is no row"
    by = {r["comp_id"]: r for r in rows}
    ko = by["401"]
    assert (ko["result"], ko["method"], ko["rnd"], ko["clock"], ko["secs"], ko["rounds"]) == ("W", "KO/TKO", 2, "3:12", 492.0, 3)
    assert ko["opp"] == "Dan Hooker" and ko["opp_id"] == "9401" and ko["date"] == "2026-08-02" and ko["division"] == "Lightweight"
    assert (ko["ssl"], ko["ssa"], ko["kd"], ko["o_ssl"], ko["o_tda"]) == (41, 77, 1, 22, 1)
    dec = by["402"]
    assert (dec["result"], dec["rnd"], dec["clock"], dec["rounds"], dec["secs"]) == ("W", 5, "5:00", 5, 1500.0), \
        "a decision ends at the last scheduled round's 5:00"
    assert (by["403"]["result"], by["403"]["clock"]) == ("L", "2:31")
    assert by["404"]["result"] == "D", "a draw or a no contest is neither a win nor a loss"
    unknown = by["406"]
    assert unknown["method"] == "" and unknown["rnd"] is None and unknown["clock"] == "", "no ending invented"
    assert by["403"]["ssl"] is None and by["403"]["o_ssl"] is None, "an untracked bout has no numbers"


def test_espn_s_fight_log_names_the_opponent_only_when_asked():
    ME, OPP = "100", "200"
    comps = {
        "c1": {"id": "c1", "date": "2026-08-02T22:00Z", "type": {"text": "Lightweight"},
               "format": {"regulation": {"periods": 3}},
               "competitors": [{"id": ME, "winner": True}, {"id": OPP, "winner": False}]},
        "c2": {"id": "c2", "date": "2030-01-01T22:00Z", "type": {"text": "Lightweight"},
               "competitors": [{"id": ME}, {"id": OPP}]},
    }
    calls = []

    def fake(url, cache):
        calls.append(cache)
        if "eventlog" in url:
            return {"events": {"pageCount": 1, "items": [
                {"competition": {"$ref": f"http://core/events/77/competitions/{c}"}} for c in ("c2", "c1")]}}
        if url.endswith("/status"):
            return {"period": 2, "displayClock": "3:12", "result": {"displayName": "KO/TKO"}}
        if "competitions/" in url:
            return comps[url.rstrip("/").split("/")[-1]]
        if "statistics" in url or "stats" in url:
            who = ME if f"/{ME}/" in url or url.endswith(ME) or ME in cache else OPP
            n = 41 if who == ME else 22
            return {"categories": [{"labels": ["SSL", "SSA"], "statistics": [{"eventId": "77", "stats": [n, n * 2]}]}]}
        return {"displayName": "Dan Hooker"}

    keep = E._get_json
    E._get_json = fake
    try:
        _own, fights, total = E.fight_log(ME, dt.date(2026, 10, 14), names=True)
        named = [c for c in calls if c.startswith("espn_mma_ath_")]
        calls.clear()
        _own2, plain, _t = E.fight_log(ME, dt.date(2026, 10, 14))
        unnamed = [c for c in calls if c.startswith("espn_mma_ath_")]
    finally:
        E._get_json = keep
    assert total == 1 and len(fights) == 1, "an upcoming bout is not history"
    f = fights[0]
    assert f["comp_id"] == "c1" and f["winner"] is True and f["method"] == "KO/TKO"
    assert (f["period"], f["clock"], f["duration_s"]) == (2, 192, 492)
    assert f["opp_name"] == "Dan Hooker" and named == [f"espn_mma_ath_{OPP}.json"]
    assert plain[0]["opp_name"] == "" and unnamed == [], "the dossier's read costs no extra request"
    assert f["own_row"] == {"ssl": 41, "ssa": 82} and f["opp_row"] == {"ssl": 22, "ssa": 44}


def test_the_lines_and_the_splits():
    d = H.chart(_conn(), "arman tsarukyan")
    assert d["player"] == "Arman Tsarukyan" and d["sport"] == "ufc" and d["seasons"] == [0]
    assert d["position"] == "Lightweight" and d["face"].endswith("/mma/players/full/3949584.png")
    assert [g["opp"] for g in d["games"]][:2] == ["Dan Hooker", "Mateusz Gamrot"], "newest first"
    assert d["games"][-1]["opp"] == "his opponent", "an unnamed opponent is not a blank"
    L = d["season_line"]
    assert (L["n"], L["w"], L["l"], L["d"]) == (6, 4, 1, 1)
    assert (L["ko_w"], L["sub_w"], L["dec_w"], L["sub_l"]) == (2, 0, 1, 1)
    assert L["finish_w"] == 0.5 and L["distance"] == round(2 / 6, 3)
    assert L["r1"] == 2, "a first-round finish either way"
    assert L["avg_secs"] == round((492 + 1500 + 151 + 900 + 45 + 900) / 6, 1)
    by = {m["key"]: m for m in d["by_method"]}
    assert (by["KO/TKO"]["w"], by["SUB"]["l"], by["DEC"]["w"]) == (2, 1, 1)
    rounds = {r["rounds"]: r for r in d["by_rounds"]}
    assert rounds[5]["n"] == 1 and rounds[3]["n"] == 5 and rounds[3]["l"] == 1
    assert [f["name"] for f in d["by_finish"]] == ["Round 1", "Round 2", "Unknown", "Decision"]
    stats = {s["key"]: s for s in d["games"][0]["stats"]}
    assert stats["ssl"]["me"] == 41 and stats["ssl"]["me_att"] == 77 and stats["ssl"]["opp"] == 22
    assert set(stats) == {"ssl", "tdl", "kd", "sm"}
    assert {s["key"] for s in d["games"][1]["stats"]} == {"ssl"}, "only what ESPN tracked"
    assert d["games"][2]["stats"] == []
    assert H.chart(_conn(), "Nobody") == {}
    assert H.chart(D.connect(":memory:"), "Arman Tsarukyan") == {}


def test_a_few_fighters_a_tick_and_none_twice():
    conn = D.connect(":memory:")
    day = dt.date(2026, 10, 14)
    asked = []

    def fetch(n):
        asked.append(n)
        if n == "Ghost":
            return None
        if n == "Broken":
            raise RuntimeError("ESPN down")
        return "3949584", FIGHTS[:2]

    names = ["Arman Tsarukyan", "Ghost", "Broken"]
    r1 = H.fill(conn, names, day, limit=2, fetch_fn=fetch)
    assert r1 == {"read": 2, "fights": 2, "missing": 1, "left": 1}
    r2 = H.fill(conn, names, day, limit=2, fetch_fn=fetch)
    assert r2 == {"read": 1, "fights": 0, "missing": 1, "left": 0}
    r3 = H.fill(conn, names, day, limit=2, fetch_fn=fetch)
    assert r3["read"] == 0 and asked == names, "one ESPN cannot find is remembered, not asked every tick"
    assert H.owed(conn, names, day + dt.timedelta(days=H.STALE_DAYS)) == names, "stale again"
    # A re-read is his record as ESPN has it now: a bout it dropped goes.
    D.upsert_ufc_fights(conn, H.rows("Arman Tsarukyan", "3949584", FIGHTS))
    assert conn.execute("SELECT COUNT(*) FROM ufc_fights").fetchone()[0] == 6
    H.fill(conn, ["Arman Tsarukyan"], day + dt.timedelta(days=H.STALE_DAYS), fetch_fn=fetch)
    assert conn.execute("SELECT COUNT(*) FROM ufc_fights").fetchone()[0] == 2


def test_the_ufc_tick_reads_the_card_and_leaves_the_dossiers():
    import launch
    src = inspect.getsource(launch.refresh_ufc)
    assert src.index("_auto_weighins(quiet)") < src.index("_auto_fight_history(quiet)") < src.index("ufc_build.py")
    fill = inspect.getsource(launch._auto_fight_history)
    assert "UD.card_fighters()" in fill and "_hist.fill(conn, names)" in fill
    assert "dossier" not in inspect.getsource(H.fill).lower(), "the history never touches a dossier"


def test_the_door_answers_the_fight_history():
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
        h._players_chart({"kind": ["fights"], "sport": ["ufc"], "player": ["Arman Tsarukyan"]})
        _conn(path).close()
        h._players_chart({"kind": ["fights"], "sport": ["ufc"], "player": ["Arman Tsarukyan"]})
        h._players_chart({"kind": ["fights"], "sport": ["nfl"], "player": ["Arman Tsarukyan"]})
    finally:
        D.DEFAULT_DB = keep
        shutil.rmtree(tmp, ignore_errors=True)
    assert sent[0] == (200, {"filling": True})
    got = sent[1][1]
    assert sent[1][0] == 200 and got["kind"] == "fights" and got["season_line"]["n"] == 6
    assert got["face"].endswith("3949584.png"), "his ESPN photo where the site has none"
    assert sent[2][0] == 400
    assert CH.known("fights", "ufc") and not CH.known("fights", "nfl")


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n{UF_JS}\n"
            f"console.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink()
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_every_fight():
    d = H.chart(_conn(), "Arman Tsarukyan")
    got = _node(f"""
      const d = {json.dumps(d)}, P = T.DRAW.fights, g = d.games[0];
      const game = P.game(g, d), season = P.season(d);
      return {{
        game, rows: (season.match(/class="uf-res /g) || []).length, bars: (game.match(/uf-bar me/g) || []).length,
        none: P.game(d.games[2], d), side: P.seasonSide(d), tiles: P.gameSide(g, d), list: P.list(g, d),
        tables: P.splits(d), chip: [P.chip(g), P.chip(d.games[1]), P.chip(d.games[5])],
        titles: [P.seasonTitle(d), P.gameTitle(g, d)], count: P.count(d.season_line), note: P.note(d),
        tip: P.tip(g.stats[0], g, d), items: P.items(g).length, listTitle: P.listTitle(g, d),
        dec: P.season(Object.assign({{}}, d, {{ games: [d.games[1]] }})),
        kinds: [T.kindsFor("ufc", "moneyline", ""), T.kindsFor("ufc", "", "")],
        kind: [T.KIND.fights.title, T.KIND.fights.chip],
      }};
    """)
    if got is None:
        return
    assert "Won · KO/TKO · R2 3:12" in got["game"] and got["game"].count('class="uf-r"') == 3, "three rounds drawn"
    assert got["bars"] == 4 and got["items"] == 4 and got["rows"] == 6
    assert "ESPN tracked no numbers for this fight" in got["none"]
    assert ">4-1-1<" in got["side"] and ">Won by finish<" in got["side"] and ">Round 1<" in got["side"]
    assert ">Fight lasted<" in got["tiles"] and ">8:12<" in got["tiles"] and "3 rounds" in got["tiles"]
    assert "41 of 77" in got["list"] and '<span class="uf-o">22 of 60</span>' in got["list"]
    assert got["listTitle"] == "That fight’s numbers · his, then Dan Hooker’s"
    assert "How he wins and loses" in got["tables"] and "Three rounds and five" in got["tables"] and "When it ended" in got["tables"]
    assert got["chip"] == ["W KO R2", "W DEC", "W"]
    assert got["titles"][0] == "His last 6 fights · 4-1-1" and got["titles"][1].startswith("vs Dan Hooker · Aug 2, 2026")
    assert got["count"] == "6 fights" and "Nothing here moves a price" in got["note"]
    assert "Significant strikes 41 of 77" in got["tip"]
    assert re.search(r'<text class="uf-m" x="408" y="31" text-anchor="end">DEC</text>', got["dec"]), \
        "a fight the clock's width has its ending on the line above, not over its bar"
    assert got["kinds"] == [["fights"], ["fights"]] and got["kind"] == ["Fight history", "Fights"]


def test_every_fighter_block_has_the_door_and_the_module_is_clean():
    i = APP_JS.index("function fighterColHTML(")
    assert 'ccDoor(f.name, "ufc", "fights", "Fight history")' in APP_JS[i:i + 2400]
    assert "${fighterColHTML(f)}" in APP_JS, "the searched fighter's card draws the same block"
    assert 'fights: "ufc"' in CC_JS and 'Q.draw("fights"' in UF_JS
    assert "onclick" not in UF_JS and "onerror" not in UF_JS and not re.search(r"on(error|load)\s*=", UF_JS)
    for cls in (".uf-svg", ".uf-track", ".uf-fill.gain", ".uf-fill.loss", ".uf-end", ".uf-bar.me", ".uf-bar.opp", ".dt.uf-d"):
        assert cls in CC_CSS, cls
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
