"""The light copy of a board, and the first paint that reads it.

Ethan, 2026-09-05: "faster first paint on mlb board". A phone parses the
whole board before it draws anything. Each build publishes a light copy
beside the board — the same picks, games and open bets, without the
player-stats table and without the halves of each row only the prop page
draws — through the same paywall publish, and the page draws it while
the full board is still on the wire, only when it holds nothing for that
league, with the same identity guards, and never keeps it past the full
board's arrival.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import lightboard, gate                                  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _board(n_recs=40, n_logs=15):
    rec = lambda i: {                                                 # noqa: E731
        "player": f"P{i}", "team": "NYY", "opponent": "BOS", "market": "hits", "side": "OVER",
        "line": 1.5, "odds": -110, "book": "FanDuel", "grade": "A", "hit_prob": 0.61, "edge": 0.04,
        "stake_units": 1.0, "reasons": ["a", "b"], "warnings": [], "headshot": "h",
        "recent_values": [1, 2, 0, 1], "game_script": {"archetype": "x", "line": "y"},
        "logs": [{"date": "2026-08-01", "value": 1, "opponent": "TB"} for _ in range(n_logs)],
        "all_lines": [{"book": f"B{k}", "line": 1.5, "over_odds": -110, "under_odds": -110} for k in range(4)],
        "line_tape": [{"at": "x", "over_odds": -110}] * 6,
        "chain": {"steps": list(range(40))}, "checks": list(range(20)), "comps": list(range(30)),
        "line_series": [{"ts": 1}] * 48,
    }
    return {
        "date": "2026-09-05", "status": "ok", "generated_at": "t", "odds_status": {"at": "9:00"},
        "counts": {"props_built": 300}, "games": [{"home": "NYY", "away": "BOS"}] * 15,
        "recommendations": [rec(i) for i in range(n_recs)],
        "game_bets": [{"pick": "NYY", "market": "moneyline", "odds": -140, "line_tape": [1] * 6, "chain": [1] * 40}],
        "long_shots": [dict(rec(99), market="home_runs")],
        "most_likely": [dict(rec(98))],
        "live_picks": [{"player": "P1", "status": "upcoming"}],
        "team_recent": {"NYY": [1] * 40}, "team_form": {"hot": [1]}, "market_scan": {"arbs": [1]},
        "parlays": [1] * 10, "longshot_watch": [1] * 30, "board_guide": [{"key": "a"}],
        "player_stats": {f"P{i}": [1] * 400 for i in range(n_recs)},
    }


def test_the_light_copy_drops_the_player_stats_table_and_the_prop_page_halves_only():
    full = _board()
    lite = lightboard.light(full, "mlb")
    assert lite["light"] is True and lite["sport"] == "mlb"
    assert "player_stats" not in lite, "the one heavy table the first paint never reads"
    for k in full:
        if k != "player_stats":
            assert k in lite, k                      # everything else the page reads stays
    for lst in ("recommendations", "game_bets", "long_shots", "most_likely"):
        for r in lite[lst]:
            for k in ("chain", "checks", "comps", "line_series"):   # by name: the prop page's four
                assert k not in r, (lst, k)
    r = lite["recommendations"][0]
    for k in ("player", "line", "odds", "reasons", "warnings", "recent_values", "logs",
              "all_lines", "line_tape", "game_script"):
        assert k in r, f"{k}: the card draws it, so the first paint needs it"
    assert len(r["logs"]) == 15, "logs stay whole — the edge board's bars read them"
    assert len(lite["games"]) == 15 and len(lite["recommendations"]) == 40
    assert "chain" in full["recommendations"][0] and "player_stats" in full, "the payload is untouched"
    assert lite["live_picks"] == full["live_picks"] and lite["team_recent"] == full["team_recent"]


def test_the_light_copy_is_a_fraction_of_the_board():
    full = _board()
    a, b = len(json.dumps(full)), len(json.dumps(lightboard.light(full)))
    assert b < a * 0.45, (a, b)


def test_the_light_copy_is_named_beside_its_board_and_gated_like_it():
    assert lightboard.light_path("web/data/recommendations.json") == "web/data/recommendations_picks.json"
    assert lightboard.light_path("web/data/mlb_recommendations.json") == "web/data/mlb_recommendations_picks.json"
    assert lightboard.light_path("web/data/cfb.json") == "web/data/cfb_picks.json"
    assert lightboard.light_path(Path("web/data/nba.json")) == "web/data/nba_picks.json"
    lite = lightboard.light(_board(3), "mlb")
    red = gate.redact(lite, "mlb_recommendations_picks.json")
    assert red["recommendations"] == [] and red["games"], "the paywall strips the same keys from the light copy"
    assert not gate.is_free("mlb_recommendations_picks.json")
    assert gate.full_board_file("mlb_recommendations_picks.json") is not None, "the entitled route serves it by name"


def test_the_size_line_reads_the_two_files():
    with tempfile.TemporaryDirectory() as d:
        b, l = Path(d) / "x.json", Path(d) / "x_picks.json"
        b.write_text("x" * 2_000_000); l.write_text("x" * 700_000)
        line = lightboard.report(b, l)
        assert "0.7 MB of 2.0 MB (35%)" in line and "x_picks.json" in line, line
        assert "sizes unavailable" in lightboard.report(b, Path(d) / "missing.json")


def test_every_build_publishes_it_beside_the_board_and_logs_its_size():
    for name in ("nfl_build.py", "mlb_build.py", "nba_build.py", "cfb_build.py"):
        src = (ROOT / name).read_text()
        assert "from engine import lightboard" in src, name
        assert "gate.publish(lightboard.light(" in src and "lightboard.light_path(" in src, name
        assert "print(lightboard.report(gate.board_source(" in src, name


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    i = APP.index("function lightNameFor(")
    fn = APP[i:APP.index("\n}", i) + 2]
    prog = f"{fn}\nconsole.log(JSON.stringify((() => {{ {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_names_the_light_copy_from_the_boards_own_file():
    got = _node("""return [lightNameFor({fallback: "data/recommendations.json"}), lightNameFor({fallback: "data/mlb_recommendations.json"}),
                          lightNameFor({fallback: "data/cfb.json"}), lightNameFor({}), lightNameFor(null), lightNameFor({fallback: "data/x.txt"})];""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["recommendations_picks.json", "mlb_recommendations_picks.json", "cfb_picks.json", "", "", ""], got


def _load_body():
    i = APP.index("async function load(quiet = false)")
    return APP[i:APP.index("\n}", i)]


def test_the_first_paint_reads_it_only_when_nothing_is_held_and_never_after_a_switch():
    body = _load_body()
    j = body.index("if (lightName && !(state.data && _boardFor === meta.api)) {")
    seg = body[j:body.index("captureFreshBaseline(meta.api);", j)]
    assert "const lr = await paidFetch(lightName);" in seg
    assert seg.count("if (overtaken()) return;") == 2, "abandoned after each await, like the full load"
    assert "if (lite.light === true) {" in seg, "a full board answering under the light name is not drawn twice"
    assert "stampFrom(lr);" in seg, "the freshness chip ages the light copy's build, not the previous league's"
    assert "state.lightBoard = true;\n            renderAll();" in seg
    assert "_boardFor = meta.api;" in seg, "the identity every other reader checks"
    assert body.index("const stampFrom = ") < j, "stampFrom exists before the light block uses it"


def test_a_light_board_is_never_revalidated_and_the_flag_clears_by_either_route():
    body = _load_body()
    assert "const holding = state.data && _boardFor === meta.api && !state.lightBoard;" in body, \
        "a tag from an earlier full load would 304 and pin the light board on screen"
    assert body.count("state.lightBoard = false;") == 2, "cleared when the full board lands, by either route"
    assert body.index("state.lightBoard = true;") < body.index("state.lightBoard = false;")
    assert "lightBoard: false," in APP[:APP.index("async function load(")], "declared on state, not conjured"


# --- the load itself, on the open-bets harness ------------------------------
def _run_light(setup, plan, light):
    """tests/test_open_bets_vanish's scripted wire, with the light copy on it."""
    import test_open_bets_vanish as H
    src = (H._STUBS
           + H._fn("normalizeSlate") + "\n" + H._fn("locksAwayWhatWeHold") + "\n"
           + H._fn("lightNameFor") + "\n" + H._fn("load", kind="async function") + "\n"
           + "state.lightBoard = false; const PAINTS = [];\n"
           + "renderAll = () => PAINTS.push({ n: (state.data.live_picks || []).length, light: !!state.lightBoard });\n"
           + (f"paidFetch = async (name) => ({{ ok: true, status: 200, headers: {{ get: () => null }}, "
              f"json: async () => ({json.dumps(light)}) }});\n" if light is not None else "")
           + setup + "\n" + f"PLAN = {json.dumps(plan)};\n"
           + """
load(true).then(() => {
  console.log(JSON.stringify({ live: (state.data || {}).live_picks || [], locked: !!(state.data || {}).locked_reason,
    light: !!state.lightBoard, boardFor: _boardFor, paints: PAINTS, planLeft: PLAN.length }));
}).catch((e) => { console.error(e); process.exit(3); });
""")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src); path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True, text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def test_on_a_cold_open_the_light_copy_paints_first_and_the_full_board_replaces_it():
    if not shutil.which("node"):
        print("  SKIP node not installed"); return
    import test_open_bets_vanish as H
    lite = dict(H.FULL, light=True, recommendations=[])
    got = _run_light("", [{"body": H.FULL}], lite)
    assert got["paints"] and got["paints"][0] == {"n": 2, "light": True}, f"the light copy was not painted first: {got}"
    assert not got["light"] and len(got["live"]) == 2 and got["boardFor"] == "/api/recommendations", got
    assert got["planLeft"] == 0, "the full board was still fetched"


def test_a_light_copy_answering_without_its_mark_is_not_painted():
    if not shutil.which("node"):
        print("  SKIP node not installed"); return
    import test_open_bets_vanish as H
    got = _run_light("", [{"body": H.FULL}], dict(H.FULL))       # a full board under the light name
    # The load's own final render is always a paint; none may be the light one.
    assert got["paints"] == [{"n": 2, "light": False}], \
        f"a board without light:true was drawn as the first paint: {got}"
    assert len(got["live"]) == 2


def test_a_held_full_board_never_asks_for_the_light_copy():
    if not shutil.which("node"):
        print("  SKIP node not installed"); return
    import test_open_bets_vanish as H
    lite = dict(H.FULL, light=True)
    got = _run_light(H.HOLDING, [{"body": H.FULL}], lite)
    assert got["paints"] == [{"n": 2, "light": False}], \
        f"a 30-second refresh painted the light copy over a held board: {got}"
    assert not got["light"]


def test_a_dropped_poll_after_the_light_paint_keeps_the_light_copy_not_the_redacted_file():
    if not shutil.which("node"):
        print("  SKIP node not installed"); return
    import test_open_bets_vanish as H
    lite = dict(H.FULL, light=True)
    got = _run_light("", [{"throw": True}, {"body": H.REDACTED}], lite)
    assert len(got["live"]) == 2 and not got["locked"], f"the redacted file replaced the entitled light copy: {got}"
    assert got["light"], "what is on screen is still the light copy, honestly flagged"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
