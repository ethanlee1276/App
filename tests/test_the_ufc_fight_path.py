"""UFC's fight path: how each man wins by our read, beside how his own fights ended.

Ethan, 2026-10-15, one of the sixteen ideas he asked to have built ("do
every one for every sport"): a UFC fight path. Context only; nothing moves
a price.

What these hold: each corner's record is his stored fights, counted — wins
and losses by knockout, submission and decision, a finish's round, a
decision with none, a draw counted apart — newest first, by his stored name
or a folded spelling of it; a man with nothing on file carries no path; the
build hangs it on every corner of every fight it shows; the paths ride
inside the paid rows, so a reader without a membership gets none of them;
and the card under the UFC page reads corner a first, the round it ends in from the
round prices, and says what it is.

Run directly: `python3 tests/test_the_ufc_fight_path.py`
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D                                       # noqa: E402
from engine.ufc import fightpath as FP                           # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

EXTRAS = ROOT / "web" / "js" / "extras.js"


def _conn():
    conn = D.connect(":memory:")
    fights = [("2026-09-01", "W", "KO/TKO", 1, "Opp A"), ("2026-06-01", "W", "KO/TKO", 2, "Opp B"),
              ("2026-03-01", "W", "DEC", 3, "Opp C"), ("2025-12-01", "L", "SUB", 2, "Opp D"),
              ("2025-09-01", "D", "DEC", 3, "Opp E"), ("2025-06-01", "L", "DEC", 3, "Opp F"),
              ("2025-03-01", "W", "SUB", 1, "Opp G")]
    for i, (date, res, how, rnd, opp) in enumerate(fights):
        conn.execute("INSERT INTO ufc_fights (fighter, comp_id, date, opp, result, method, rnd, rounds) "
                     "VALUES (?,?,?,?,?,?,?,?)", ("Alex Pereira", f"c{i}", date, opp, res, how, rnd, 3))
    conn.commit()
    return conn


def test_his_fights_are_counted_by_how_they_ended():
    p = FP.record(_conn(), "Alex Pereira")
    assert p["n"] == 7 and p["draws"] == 1
    assert p["wins"] == {"ko": 2, "sub": 1, "dec": 1} and p["losses"] == {"ko": 0, "sub": 1, "dec": 1}
    assert p["won_in"] == {"1": 2, "2": 1} and p["lost_in"] == {"2": 1}, "a decision has no finishing round"
    assert len(p["last"]) == FP.LAST and p["last"][0] == ["W", "KO/TKO", 1, "Opp A", "2026-09-01"], "newest first"
    assert p["last"][2] == ["W", "DEC", None, "Opp C", "2026-03-01"]


def test_a_folded_spelling_finds_him_and_nobody_has_no_path():
    conn = _conn()
    assert FP.record(conn, "alex  PEREIRA")["n"] == 7
    assert FP.record(conn, "Nobody Here") is None and FP.record(conn, "") is None


def test_the_build_hangs_a_path_on_every_corner_it_shows():
    board = {"picks": [{"fight": "Alex Pereira vs Nobody Here", "fighters": [{"name": "Alex Pereira"}, {"name": "Nobody Here"}]}],
             "pass_list": [{"fight": "Alex Pereira vs X", "fighters": [{"name": "Alex Pereira"}, {}]}, "junk"]}
    assert FP.attach(board, _conn()) == 2
    a, nobody = board["picks"][0]["fighters"]
    assert a["path"]["n"] == 7 and "path" not in nobody, "a man with nothing on file carries none, not an empty one"
    assert board["pass_list"][0]["fighters"][0]["path"] == a["path"]
    src = (ROOT / "ufc_build.py").read_text(encoding="utf-8")
    assert "n_paths = _fp.attach(out, _pc)" in src and "fight paths skipped" in src


def test_the_paths_ride_inside_the_paid_rows():
    from engine import gate
    board = {"sport": "ufc", "picks": [{"fight": "A vs B", "fighters": [{"name": "A", "path": {"n": 3}}]}],
             "pass_list": [{"fight": "C vs D", "fighters": [{"name": "C", "path": {"n": 2}}]}]}
    out = gate.redact(board, "ufc.json")
    assert "path" not in json.dumps(out) and out.get("locked"), "a reader without a membership gets no fight reads"


def _node(body: str):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    script = ("const vm = require('vm'); const fs = require('fs');"
              "const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(EXTRAS))}, 'utf8'), ctx);"
              "const X = ctx.window.QBExtras;" + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_toolbox_card_reads_corner_a_first_and_says_what_it_is():
    path = FP.record(_conn(), "Alex Pereira")
    board = {"picks": [{"kind": "pick", "pick": "Alex Pereira", "fight": "Alex Pereira vs Jamahal Hill",
                        "division": "light_heavyweight", "scheduled_rounds": 5,
                        "fighters": [{"name": "Alex Pereira", "record": "12-3", "path": path}, {"name": "Jamahal Hill"}],
                        "method": {"a_ko": 0.4, "a_sub": 0.05, "a_dec": 0.2, "b_ko": 0.2, "b_sub": 0.05, "b_dec": 0.1,
                                   "distance": 0.3},
                        "market_board": [{"market": "exact_round", "selection": "Ends in round 1", "p_model": 0.22},
                                         {"market": "exact_round", "selection": "Ends in round 2", "p_model": 0.18},
                                         {"market": "moneyline", "selection": "Alex Pereira", "p_model": 0.65}]}],
             "pass_list": [{"kind": "pass", "fight": "No vs Read", "fighters": [{"name": "No"}, {"name": "Read"}]}]}
    got = _node(f"const b = {json.dumps(board)};"
                "process.stdout.write(JSON.stringify({rows: X.fightPaths(b), html: X.pathsHTML(b),"
                "locked: X.pathsHTML({locked: {picks: 3}}), none: X.pathsHTML({})}));")
    if got is None:
        return
    r = got["rows"]
    assert len(r) == 1, "a fight the model did not read has no path"
    assert r[0]["a"]["name"] == "Alex Pereira" and abs(r[0]["a"]["win"] - 0.65) < 1e-9 and abs(r[0]["b"]["win"] - 0.35) < 1e-9
    assert r[0]["ends"] == {"1": 0.22, "2": 0.18} and r[0]["rounds"] == 5 and r[0]["division"] == "light heavyweight"
    html = got["html"]
    assert "Fight path" in html and "Pick: Alex Pereira" in html and "5 rounds" in html
    assert "KO/TKO 40%" in html and "Won: 2 KO/TKO · 1 Sub · 1 Dec" in html and "Lost: 0 KO/TKO · 1 Sub · 1 Dec" in html
    assert "R1 2 · R2 1" in html and "R1 22% · R2 18% · Distance 30%" in html
    assert "His fights are not on file yet." in html, "Hill has no path"
    assert html.count('class="xt-fp-l t-good"') == 3 and "1 drawn or no contest" in html
    assert "Context, not a pick." in html
    assert "membership" in got["locked"] and "No fights read on the card yet" in got["none"]
    # UFC is its own page, not a sport the Toolbox switches to: the paths
    # draw under the card that page has already read (members' copy or sealed).
    app = app_js()
    assert '<div id="ufc-paths"></div>' in app
    assert 'el = document.getElementById("ufc-paths"); if (X && el) el.innerHTML = X.pathsHTML(d);' in app


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
