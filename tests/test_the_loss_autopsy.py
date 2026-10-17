"""The loss autopsy — every graded pick's miss split into volume and efficiency, summed into the step that is wrong most.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 12: a loss on four
targets and a loss on eleven targets at three yards a catch are different
mistakes, and the record should say which step makes them.

What these hold: the split adds to the miss with nothing left over and a
market that is its own opportunity is all volume; the role going in is his
four games before, two at least; the tags run left early, script, volume,
efficiency, both; the journal counts a pick once and reads only NFL
season-week keys; a step is named only when it goes against the pick in
losses clearly more than in wins, over 100 losses; the daily chores refresh it at
most once a day; and the pick page shows the shares, the steps and his last
picks, labelled. No test touches the network.

Run directly: `python3 tests/test_the_loss_autopsy.py`
"""
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import autopsy as A                                  # noqa: E402
from engine import ideas as ID                                   # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def test_the_split_adds_to_the_miss():
    p = A.decompose(62.0, 30.0, 8.0, 4.0)
    assert p == {"volume": -31.0, "efficiency": -1.0} and p["volume"] + p["efficiency"] == 30.0 - 62.0
    q = A.decompose(62.0, 30.0, 8.0, 11.0)
    assert q["volume"] > 0 > q["efficiency"] and abs(q["volume"] + q["efficiency"] + 32.0) < 1e-9
    assert A.decompose(16.5, 12.0, None, 4.0, volume_only=True) == {"volume": -4.5, "efficiency": 0.0}
    assert A.decompose(62.0, 30.0, None, 4.0) is None and A.decompose(62.0, 30.0, 8.0, None) is None
    assert A.against({"volume": -31.0, "efficiency": -1.0}, "Under") == (-31.0, -1.0)


def test_the_role_going_in_and_the_tags():
    weeks = {1: {"targets": 6}, 2: {"targets": 8}, 3: {"targets": 10}, 4: {"targets": 12}, 5: {"targets": 2}, 6: {}}
    assert A.role_going_in(weeks, 6, "targets") == (8 + 10 + 12 + 2) / 4
    assert A.role_going_in(weeks, 2, "targets") is None, "one game is not a role"
    vol = {"volume": -31.0, "efficiency": -1.0}
    assert A.tag(vol, "over", 0.85, 0.30) == "left early"
    assert A.tag(vol, "over", 0.85, 0.80, blowout=True) == "script"
    assert A.tag(vol, "over", 0.85, 0.80) == "volume"
    assert A.tag({"volume": 3.0, "efficiency": -20.0}, "over") == "efficiency"
    assert A.tag({"volume": -10.0, "efficiency": -9.0}, "over") == "both"
    assert A.tag(vol, "over", 0.30, 0.10) == "volume", "a part-timer's low snaps are not an exit"


def test_the_journal_counts_a_pick_once_and_reads_nfl_weeks():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE bets (id INTEGER PRIMARY KEY, sport, date, player, market, side, line, projection, "
                 "actual, status, category)")
    rows = [("nfl", "2025-W03", "Puka Nacua", "rec_yds", "over", 70.5, 78.0, 50.0, "lost", "likely"),
            ("nfl", "2025-W03", "Puka Nacua", "rec_yds", "over", 70.5, 78.0, 50.0, "lost", "board"),
            ("nfl", "2025-W04", "Puka Nacua", "anytime_td", "yes", 0.5, 0.4, 1.0, "won", "likely"),
            ("cfb", "2025-10-04", "Some Back", "rush_yds", "over", 80.5, 90.0, 60.0, "lost", "likely"),
            ("nfl", "2025-W05", "Puka Nacua", "rec_yds", "over", 70.5, 78.0, None, "open", "likely")]
    conn.executemany("INSERT INTO bets (sport, date, player, market, side, line, projection, actual, status, category) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    got = A.graded_picks(conn)
    assert len(got) == 1 and got[0]["season"] == 2025 and got[0]["week"] == 3 and not got[0]["won"]


def _rows(n_loss=150, n_win=250, seed=2, vol_bias=0.75):
    rnd = random.Random(seed)
    out = []
    for i in range(n_loss + n_win):
        won = i >= n_loss
        hurt_vol = rnd.random() < (vol_bias if not won else 0.4)
        parts = {"volume": -10.0 if hurt_vol else 4.0, "efficiency": -6.0 if rnd.random() < 0.5 else 3.0}
        out.append({"sport": "nfl", "market": "rec_yds", "player": f"P{i % 7}", "date": f"2025-W{i % 17 + 1:02d}",
                    "side": "over", "line": 60.5, "projection": 66.0, "actual": 50.0 if not won else 70.0, "won": won,
                    "parts": parts, "against": {"volume": -parts["volume"], "efficiency": -parts["efficiency"]},
                    "flags": {"volume": hurt_vol, "efficiency": parts["efficiency"] < 0, "script": False, "left_early": False},
                    "tag": None if won else A.tag(parts, "over")})
    return out


def test_a_step_is_named_only_against_the_wins():
    s = A.summarize(_rows())
    assert s["losses"] == 150 and s["wins"] == 250 and s["wrong_most"] == "volume"
    assert s["steps"]["volume"]["excess"] > 0.25 and s["steps"]["volume"]["z"] >= 2
    assert abs(s["steps"]["efficiency"]["excess"]) < 0.15
    flat = A.summarize(_rows(vol_bias=0.4))
    assert flat["wrong_most"] is None, "a step as noisy in wins as in losses is not the one that is wrong"
    few = A.summarize(_rows(n_loss=60))
    assert few["wrong_most"] is None, "60 losses is not 100"


def test_autopsy_joins_the_logs_and_the_build_refreshes_daily():
    picks = [{"sport": "nfl", "date": "2025-W06", "season": 2025, "week": 6, "player": "Puka Nacua", "market": "rec_yds",
              "side": "over", "line": 70.5, "projection": 80.0, "actual": 41.0, "won": False}]
    usage = {("puka nacua", 2025): {w: {"targets": 10.0, "snap_pct": 0.9} for w in range(1, 6)}}
    usage[("puka nacua", 2025)][6] = {"targets": 5.0, "snap_pct": 0.35}
    out = A.autopsy(picks, usage)
    assert out[0]["parts"] == {"volume": -40.0, "efficiency": 1.0} and out[0]["tag"] == "left early"
    assert A.autopsy(picks, {}) == [], "no role going in, no split"
    d = tempfile.mkdtemp()
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = d
    try:
        A.save({"built_at": time.time(), "markets": {}, "players": {}})
        assert A.refresh() is False, "built within the day: left alone"
        res = A.build(_rows())
        A.save(res)
        sec = A.ideas_section([], [], {"recommendations": [{"player": "P3", "market": "rec_yds"},
                                                          {"player": "P3", "market": "anytime_td"}]}, "nfl")
        p = A.pick_view(sec, "P3", "rec_yds")
        assert p["summary"]["wrong_most"] == "volume" and len(p["his"]) == 3
        assert A.pick_view(sec, "P3", "anytime_td") is None and A.game_view(sec, "LAR", "SF") is None
    finally:
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
        shutil.rmtree(d)
    assert ID.SECTIONS["autopsy"] == "autopsy"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.pickHTML({json.dumps({'sections': {'autopsy': p}})})}}));")
    run = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-1200:]
    h = json.loads(run.stdout)["h"]
    assert "When picks like this lose" in h and "The step wrong most" in h and "lb-tags" in h
    assert "His last graded picks" in h and "Context" in h


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
