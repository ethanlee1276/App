"""Rookies and transfers, translated from the college logs the box already keeps.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 8: a rookie's first
NFL month is priced off almost nothing, but his last college season and
where he was drafted are a projection the thin-history shrink throws away.

What these hold: a college line is one school's season with enough games,
and a name two schools share is left out rather than guessed; the first
month is NFL weeks 1-4 with two games; the roster's rookies are the
receivers, tight ends and backs whose rookie year is the season, one row a
man, undrafted reading as pick 260; the fit recovers a known translation;
the bar is the two newest classes against draft slot alone AND the
position's rookie mean, 60 rookies, t ≥ 2; a transfer keeps the ratio of
his new first four games to his old season; the pick page shows the
college line and the translation, labelled. No test touches the network.

Run directly: `python3 tests/test_rookies_from_their_college_line.py`
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D                                       # noqa: E402
from engine import ideas as ID                                   # noqa: E402
from engine import rookies as R                                  # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _log(conn, sport, season, week, player, team, market, value):
    conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, market, value) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (sport, season, f"{week:03d}", f"{team}{week}", player, team, market, value))


def test_a_college_line_is_one_schools_season_with_enough_games():
    conn = D.connect(":memory:")
    for w in range(1, 9):
        _log(conn, "cfb", 2025, w, "Tet McMillan", "Arizona", "rec_yds", 100.0)
        _log(conn, "cfb", 2025, w, "Chris Smith", "Ohio State", "rec_yds", 50.0)
        _log(conn, "cfb", 2025, w, "Chris Smith", "Utah", "rec_yds", 70.0)
    for w in range(1, 4):
        _log(conn, "cfb", 2025, w, "Short Season", "Iowa", "rec_yds", 80.0)
    col = R.college_lines(conn, 2025, "rec_yds")
    assert col == {"tet mcmillan": ("Arizona", 100.0, 8)}, "two schools is a guess; three games is too few"
    for w in (1, 2, 5):
        _log(conn, "nfl", 2026, w, "Tet McMillan", "CAR", "rec_yds", 60.0 if w < 5 else 200.0)
    _log(conn, "nfl", 2026, 1, "One Game", "CAR", "rec_yds", 90.0)
    assert R.nfl_first_month(conn, 2026, "rec_yds") == {"tet mcmillan": (60.0, 2)}, "weeks 1-4 only, two games"


def test_the_rosters_rookies_are_skill_players_in_their_first_year():
    roster = [{"season": 2026, "rookie_year": 2026, "position": "WR", "full_name": "Tet McMillan", "draft_number": "8", "college": "Arizona"},
              {"season": 2026, "rookie_year": 2026, "position": "WR", "full_name": "Tet McMillan", "draft_number": "8", "college": "Arizona"},
              {"season": 2026, "rookie_year": 2026, "position": "RB", "full_name": "Walk On", "draft_number": "NA"},
              {"season": 2026, "rookie_year": 2026, "position": "QB", "full_name": "A Passer", "draft_number": "1"},
              {"season": 2026, "rookie_year": 2024, "position": "TE", "full_name": "Old Hand", "draft_number": "40"}]
    rows = R.rookie_rows(roster)
    assert [(r[0], r[2], r[3]) for r in rows] == [("tet mcmillan", "WR", 8), ("walk on", "RB", R.UNDRAFTED)]


def _classes(seed=5, n=40):
    rnd = random.Random(seed)
    out = []
    for season in range(2021, 2027):
        for _ in range(n):
            pick = rnd.choice([3, 10, 25, 50, 90, 150, 220, 260])
            col = rnd.uniform(20, 110)
            out.append((season, rnd.choice(R.POSITIONS), pick, col, max(0.0, 30 + 0.45 * col - 4.0 * math.log(pick) + rnd.gauss(0, 3))))
    return out


def test_the_fit_recovers_a_translation_and_the_bar_wants_both_baselines_beaten():
    rows = _classes()
    m = R.fit(rows)
    assert abs(m["w"][1] - 0.45) < 0.03 and abs(m["w"][2] + 4.0) < 0.6
    assert set(m["pos_mean"]) == set(R.POSITIONS)
    h = R.held_out(rows)
    assert h["test"] == [2025, 2026] and h["n"] == 80 and h["holds"]
    assert h["vs_slot"]["gain"] > 0 and h["vs_position"]["gain"] > 0
    few = R.held_out(_classes(n=20))
    assert few["n"] == 40 and not few["holds"], "40 rookies is not 60"
    noise = [(s, p, k, c, 25.0 + random.Random(i).gauss(0, 8)) for i, (s, p, k, c, _y) in enumerate(rows)]
    assert not R.held_out(noise)["holds"], "a college line that predicts nothing never holds"
    assert R.held_out(rows[:80])["holds"] is False, "two classes is not enough to hold one out"


def test_a_transfer_keeps_his_new_first_four_over_his_old_season():
    conn = D.connect(":memory:")
    for w in range(1, 9):
        _log(conn, "cfb", 2025, w, "Mover", "Toledo", "rush_yds", 100.0)
        _log(conn, "cfb", 2025, w, "Stayer", "Iowa", "rush_yds", 90.0)
    for w in range(1, 7):
        _log(conn, "cfb", 2026, w, "Mover", "Oregon", "rush_yds", 60.0 if w <= 4 else 300.0)
        _log(conn, "cfb", 2026, w, "Stayer", "Iowa", "rush_yds", 90.0)
    assert R.transfer_ratios(conn, 2026, "rush_yds") == [(100.0, 60.0)], "first four games, school changed"
    assert R.transfer_table([(100.0, 60.0)] * 12) == {"keep": 0.6, "n": 12}
    assert R.transfer_table([(100.0, 60.0)] * 5) is None
    idx = R.indexes(conn, 2026, [], 2026)
    assert idx["transfer_index"] == {"mover": {"old": {"rush_yds": {"school": "Toledo", "pg": 100.0, "games": 8}}}}


def test_the_pick_page_shows_his_college_line_translated():
    d = tempfile.mkdtemp()
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = d
    try:
        assert R.ideas_section([], [], {"recommendations": [{"player": "Tet McMillan", "market": "rec_yds"}]}, "nfl") == \
            {"rows": {}, "measured": False}
        m = R.fit(_classes())
        R.save({"rookies": {"rec_yds": {"fit": m, "held_out": {"n": 80, "holds": False}}}, "transfers": {},
                "rookie_index": {"tet mcmillan": {"name": "Tet McMillan", "pos": "WR", "pick": 8,
                                                 "college": {"rec_yds": {"school": "Arizona", "pg": 95.1, "games": 12}}}}})
        board = {"recommendations": [{"player": "Tet McMillan", "market": "rec_yds"}, {"player": "Tet McMillan", "market": "pass_yds"}]}
        sec = R.ideas_section([], [], board, "nfl")
        p = R.pick_view(sec, "Tet McMillan", "rec_yds")
        assert p["kind"] == "rookie" and p["pick"] == 8 and p["school"] == "Arizona"
        assert abs(p["translated"] - round(R.translate(m, 95.1, 8), 1)) < 1e-9
        assert R.pick_view(sec, "Tet McMillan", "pass_yds") is None and R.game_view(sec, "CAR", "NO") is None
    finally:
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
        shutil.rmtree(d)
    assert ID.SECTIONS["rookie"] == "rookies"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.pickHTML({json.dumps({'sections': {'rookie': p}})})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)["h"]
    assert "His college line, translated" in h and "Arizona" in h and "#8" in h
    assert "Measured · does not hold" in h


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
