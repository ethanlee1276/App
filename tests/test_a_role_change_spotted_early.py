"""A role change spotted early — Bayesian changepoint detection on each man's share of the work.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 10: a role jumps,
and the board's four-week average takes four weeks to believe it.

What these hold: the detector finds a planted jump within a game or two
and does not cry change on a flat series; its forecast is made from the
games before, never the game itself; a share is his targets (carries)
over his team's that week, a snap share as stored; the walk-forward
errors start after four games and the four-week average is the baseline;
the settings come from the grid on the training seasons alone; the verdict
is clustered by player-season and wants every test season above zero; and
the pick and game pages show the shares and the change, labelled. No test
touches the network.

Run directly: `python3 tests/test_a_role_change_spotted_early.py`
"""
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D                                       # noqa: E402
from engine import ideas as ID                                   # noqa: E402
from engine import rolechange as R                               # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def _jump(seed=1, before=8, after=3, lo=0.12, hi=0.28, sd=0.02):
    rnd = random.Random(seed)
    return [lo + rnd.gauss(0, sd) for _ in range(before)] + [hi + rnd.gauss(0, sd) for _ in range(after)]


def test_it_finds_a_planted_jump_and_stays_quiet_on_a_flat_role():
    s = R.summary(_jump())
    assert s["flag"] and s["changed"] > 0.8 and s["games_ago"] == 3, s
    assert abs(s["before"] - 0.12) < 0.02 and abs(s["after"] - 0.28) < 0.03
    assert s["forecast"] > s["four_week"], "the detector believes the new role sooner than four weeks do"
    rnd = random.Random(5)
    flat = R.summary([0.18 + rnd.gauss(0, 0.02) for _ in range(12)])
    assert not flat["flag"] and flat["changed"] < 0.3, flat
    assert R.summary([0.2, 0.2, 0.2]) is None, "three games is too few"


def test_the_forecast_is_made_before_the_game():
    xs = _jump()
    d = R.detect(xs)
    assert d["forecasts"][0] is None and len(d["forecasts"]) == len(xs)
    again = R.detect(xs[:5] + [0.9] + xs[6:])
    assert again["forecasts"][:6] == d["forecasts"][:6], "game 6's own value never reaches its forecast"
    assert abs(sum(d["run"]) - 1) < 1e-9 and len(d["run"]) <= R.MAX_RUN


def test_a_share_is_of_his_own_team_that_week():
    rows = [(2025, 1, "BUF", "Khalil Shakir", "targets", 8), (2025, 1, "BUF", "Dalton Kincaid", "targets", 2),
            (2025, 2, "BUF", "Khalil Shakir", "targets", 5), (2025, 2, "BUF", "Dalton Kincaid", "targets", 5),
            (2025, 1, "BUF", "James Cook", "carries", 15), (2025, 1, "BUF", "Khalil Shakir", "snap_pct", 0.81),
            (2025, 1, "MIA", "Tyreek Hill", "targets", 9)]
    s = R.series_from(rows)
    assert s[("tgt", 2025, "Khalil Shakir")] == [(1, 0.8), (2, 0.5)]
    assert s[("car", 2025, "James Cook")] == [(1, 1.0)] and s[("snap", 2025, "Khalil Shakir")] == [(1, 0.81)]
    assert s[("tgt", 2025, "Tyreek Hill")] == [(1, 1.0)], "his denominator is his own team's"


def test_the_walk_forward_errors_and_the_grid():
    series = {("tgt", 2025, "A"): [(w, v) for w, v in enumerate(_jump(), 1)],
              ("tgt", 2023, "B"): [(w, v) for w, v in enumerate(_jump(seed=2), 1)],
              ("car", 2025, "A"): [(1, 0.5)] * 3}
    e = R.errors(series, "tgt", {2025}, R.DEFAULT)
    assert len(e) == 11 - R.MIN_PRIOR and all(x[0] == 2025 and x[1] == "A|2025" for x in e)
    xs = [v for _w, v in series[("tgt", 2025, "A")]]
    assert abs(e[0][3] - abs(sum(xs[0:4]) / 4 - xs[4])) < 1e-12, "the baseline is the four weeks before"
    assert R.errors(series, "car", {2025}, R.DEFAULT) == [], "three games forecasts nothing"
    pick = R.choose(series, "tgt", {2023})
    assert pick["hazard"] in R.HAZARDS and pick["spread"] in R.SPREADS


def test_the_verdict_is_clustered_and_wants_every_test_season():
    rnd = random.Random(3)
    rows = []
    for season in (2024, 2025):
        for p in range(200):
            for _ in range(8):
                base = abs(rnd.gauss(0, 0.05))
                rows.append((season, f"{p}|{season}", base - 0.01 + rnd.gauss(0, 0.004), base))
    v = R.verdict(rows)
    assert v["series"] == 400 and v["forecasts"] == 3200 and v["holds"] and set(v["by_season"]) == {"2024", "2025"}
    worse = [(s, k, d + (0.03 if s == 2025 else 0), b) for s, k, d, b in rows]
    assert not R.verdict(worse)["holds"]
    assert not R.verdict(rows[:1000])["holds"], "125 player-seasons is not 300"


def test_the_pick_and_game_pages_show_the_change():
    conn = D.connect(":memory:")
    shares = _jump(before=6, after=3)
    for w, sh in enumerate(shares, 1):
        for player, team, m, v in (("Khalil Shakir", "BUF", "targets", round(sh * 40)), ("Others", "BUF", "targets", 40 - round(sh * 40)),
                                   ("Khalil Shakir", "BUF", "snap_pct", 0.8)):
            conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, market, value) "
                         "VALUES ('nfl', 2026, ?, ?, ?, ?, ?, ?)", (f"{w:03d}", f"g{w}", player, team, m, v))
    board = {"recommendations": [{"player": "Khalil Shakir", "team": "BUF", "opponent": "MIA", "market": "receptions"}]}
    sec = R.ideas_section([], [], board, "nfl", conn=conn)
    p = R.pick_view(sec, "Khalil Shakir", "receptions")
    assert p["lead"] == "tgt" and list(p["reads"]) == ["tgt", "snap"]
    t = p["reads"]["tgt"]
    assert t["flag"] and t["games_ago"] == 3 and len(t["values"]) == 9
    g = R.game_view(sec, "MIA", "BUF")
    assert g["rows"][0]["player"] == "Khalil Shakir" and g["rows"][0]["label"] == "Target share"
    assert R.game_view(sec, "NYJ", "NE") is None and R.ideas_section([], [], board, "cfb", conn=conn) is None
    assert ID.SECTIONS["role"] == "rolechange"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{p: L.pickHTML({json.dumps({'sections': {'role': p}})}),"
              f" g: L.gameHTML({json.dumps({'sections': {'role': g}})})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)
    assert "His role, watched for a change" in h["p"] and "over his last 3 games" in h["p"]
    assert 'class="new"' in h["p"] and "Snap share" in h["p"] and "Reading · not measured yet" in h["p"]
    assert "Roles that just changed" in h["g"] and "Khalil Shakir" in h["g"]


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
