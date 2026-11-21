"""Kick physics: the air's density and the wind's angle to the field, not just the wind speed.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 7: drag on a kicked
ball scales with the air's density, which heat and height both thin; and a
wind's effect depends on its angle to the uprights.

What these hold: density is the ideal gas law on the standard atmosphere's
pressure at the stadium's altitude (or a given pressure), with vapour when
the humidity is known — 1.225 at sea level and 59°F, about a fifth thinner
in Denver on a mild day; a wind's parts are along and across a recorded
bearing, from where it blows; a bearing is recorded only with a source
link; every stored field goal reads its home stadium's altitude and, under
a roof, the building's 70°F; the logistic fit recovers a known effect; the
held-out test needs the physics' sign as well as the gain, and 2,000
kicks; "plays like" comes only from a fit that held; the game and kicker
pages show the air, labelled.

Run directly: `python3 tests/test_the_air_a_kick_flies_through.py`
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
from engine import kickphysics as K                              # noqa: E402

LAB = ROOT / "web" / "js" / "lab.js"


def test_density_is_the_gas_law_at_the_stadiums_height():
    assert round(K.air_density(59, 0), 3) == 1.225
    den = K.air_density(70, 5280)
    assert 0.97 < den < 1.0 and K.density_dev(den) < -0.18, "Denver on a mild day: about a fifth thinner"
    assert K.air_density(20, 600) > K.air_density(90, 600), "cold air is thicker"
    assert K.air_density(80, 0, humidity=90) < K.air_density(80, 0), "moist air is lighter"
    assert K.air_density(59, 0, humidity=0.9) == K.air_density(59, 0, humidity=90), "0-1 or 0-100"
    assert abs(K.air_density(59, 5280, pressure_hpa=1013.25) - 1.225) < 1e-3, "a measured pressure wins"
    assert K.air_density(None, 0) is None


def test_the_wind_is_split_along_and_across_a_recorded_bearing():
    assert K.wind_parts(10, "N", 0) == {"along": -10.0, "across": 0.0}, "from the north, toward the south end"
    assert K.wind_parts(10, "W", 0) == {"along": 0.0, "across": 10.0}
    assert K.wind_parts(10, 225, 45) == {"along": 10.0, "across": 0.0}, "from the south-west, toward the end at 45°"
    assert K.wind_parts(10, "", 0) is None and K.wind_parts(None, "N", 0) is None
    d = tempfile.mkdtemp()
    old = os.environ.get("QB_MODELS_DIR")
    os.environ["QB_MODELS_DIR"] = d
    try:
        try:
            K.set_bearing("CHI", 5, "")
            raise AssertionError("a bearing without a source must be refused")
        except ValueError:
            pass
        K.set_bearing("CHI", 185, "https://example.com/soldier-field")
        assert K.bearings() == {"CHI": {"deg": 5.0, "source": "https://example.com/soldier-field"}}
    finally:
        if old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = old
        shutil.rmtree(d)


def test_every_stored_kick_reads_its_stadium_and_a_roof_reads_the_building():
    conn = D.connect(":memory:")
    rows = [("1", "KC@DEN", 50, "made", "outdoors", 70.0, 5.0), ("2", "BUF@DET", 45, "missed", "dome", None, None),
            ("3", "BUF@DET", 33, "blocked", "dome", None, None), ("4", "BUF@DET", 0, "made", "dome", None, None)]
    for pid, gid, dist, res, roof, temp, wind in rows:
        conn.execute("INSERT INTO kicks (sport, season, period, game_id, play_id, kind, distance, result, roof, temp, wind) "
                     "VALUES ('nfl', 2025, '005', ?, ?, 'fg', ?, ?, ?, ?, ?)", (gid, pid, dist, res, roof, temp, wind))
    conn.execute("INSERT INTO kicks (sport, season, period, game_id, play_id, kind, distance, result, roof) "
                 "VALUES ('nfl', 2025, '005', 'BUF@DET', '9', 'xp', 33, 'made', 'dome')")
    ks = K.load_kicks(conn)
    den = [k for k in ks if k["distance"] == 50][0]
    assert den["outdoors"] and den["dens_dev"] < -0.18 and den["wind"] == 5.0
    dome = [k for k in ks if k["distance"] == 45][0]
    assert not dome["outdoors"] and dome["wind"] == 0.0
    assert abs(dome["dens_dev"] - K.density_dev(K.air_density(70, 600))) < 1e-9, "Ford Field: 70°F at its altitude"
    assert len([k for k in ks if k["distance"] == 33]) == 1, "an extra point is not a field goal"


def _sim(n=6000, seed=3, effect=-1.2):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        d = rnd.randint(20, 58)
        dev = rnd.uniform(-0.2, 0.1)
        z = 6.0 - 1.3 * (d / 10) + effect * dev * (d / 10)
        out.append({"season": 2021 + i % 5, "distance": d, "made": int(rnd.random() < 1 / (1 + math.exp(-z))),
                    "outdoors": False, "wind": 0.0, "dens_dev": dev})
    return out


def test_the_fit_finds_a_real_effect_and_the_bar_wants_the_physics_sign():
    res = K.held_out(_sim())
    assert res["test"] == [2024, 2025] and res["n"] == 2400
    assert res["density_coef"] < 0 and res["sign_ok"]
    held = {"holds": True, "distance_coef": -1.3, "density_coef": -1.2}
    assert K.plays_like(held, 50, -0.2) < 50 < K.plays_like(held, 50, 0.1), "thin air: shorter; thick: longer"
    assert K.plays_like({"holds": False, "distance_coef": -1.3, "density_coef": -1.2}, 50, -0.2) is None
    wrong = K.held_out(_sim(effect=+1.2))
    assert not wrong["sign_ok"] and not wrong["holds"], "an effect against the physics never holds"
    few = K.held_out(_sim(n=1500))
    assert few["test"] == [2023, 2024, 2025] and few["n"] == 900, "newest seasons until 2,000, two left to fit"
    assert not few["holds"], "900 kicks is not 2,000"
    mid = K.held_out(_sim(n=4500))
    assert mid["test"] == [2023, 2024, 2025] and mid["n"] == 2700, "two seasons short of 2,000: a third is held out"


def test_the_game_and_kicker_pages_show_the_air():
    g = {"home": "DEN", "away": "KC", "weather": {"temp_f": 70, "wind_mph": 10, "wind_dir": "N", "measured": True}}
    c = K.conditions(g, {}, {"DEN": {"deg": 0.0, "source": "x"}})
    assert c["altitude_ft"] == 5280 and c["density_dev"] < -0.18 and c["wind_parts"]["along"] == -10.0
    assert "plays_like_50" not in c, "no fit that held, no yards"
    dome = K.conditions({"home": "DET", "away": "BUF", "weather": {"dome": True, "temp_f": 20, "wind_mph": 30}}, {}, {})
    assert dome["temp_f"] == K.DOME_F and dome["wind_mph"] is None
    sec = K.ideas_section([], [g], {"recommendations": [{"player": "Wil Lutz", "team": "DEN", "market": "fg_made"},
                                                       {"player": "Bo Nix", "team": "DEN", "market": "pass_yds"}]}, "nfl")
    assert list(sec["kickers"]) == ["Wil Lutz"]
    pv, gv = K.pick_view(sec, "Wil Lutz", "fg_made"), K.game_view(sec, "DEN", "KC")
    assert pv["home"] == "DEN" and gv["density"] == pv["density"] and K.pick_view(sec, "Bo Nix", "pass_yds") is None
    assert K.ideas_section([], [g], {}, "nba") is None
    assert ID.SECTIONS["kicks"] == "kickphysics"
    node = shutil.which("node")
    if not node:
        print("      (skipped the drawing: no Node)")
        return
    script = ("const vm = require('vm'); const fs = require('fs'); const ctx = { window: {} }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(LAB))}, 'utf8'), ctx); const L = ctx.window.QBLab;"
              f"process.stdout.write(JSON.stringify({{h: L.gameHTML({json.dumps({'home': 'DEN', 'sections': {'kicks': {**c, 'fit': {}}}})})}}));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1200:]
    h = json.loads(out.stdout)["h"]
    assert "The air a kick flies through" in h and "thinner than sea-level air" in h
    assert "10 mph down the field, 0 across it" in h and "Reading · not measured yet" in h


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
