"""Our own expected average and slugging, measured before they touch a pick.

Ethan, 2026-10-13, on the list he said yes to ("Yes do all of them"):
"MLB expected stats: once batted balls are stored, we could build our own
expected batting average and slugging from exit velocity and launch angle,
as we did for NHL expected goals. I'd test it before it touches a pick."

What is pinned, offline, on balls and worlds built here:

  * THE TABLE (engine/mlb/xstats): a ball's cell by exit velocity, then
    launch angle; each cell's hit rate and bases shrunk toward its band's,
    the band's toward the league's; the deepest cell answers; a hitter's
    line counts a strikeout as nothing, a walk as no at bat, and a ball
    with no reading as what it was; it is saved and read back whole;
  * THE TEST (engine/mlb/xstatsfit): the table is fitted on the first
    TRAIN_SHARE of the dates and nothing later; the shrink is picked on
    TUNE alone; each hitter-game is predicted from his earlier plate
    appearances that season only; the bar and its constants are the ones
    written before any run; a world where contact quality carries the
    signal passes, a world where it carries none does not, and too few
    hitter-games pass nothing;
  * THE PAGE: the hit tracker's balls carry their expected hit and bases,
    the season line its xBA and xSLG beside AVG and SLG, the note says
    what the test found or that it has not run; nothing that prices a
    bet reads any of it.

Run directly: `python3 tests/test_mlb_expected_stats_measured_before_use.py`
"""
import inspect
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D, maintenance as M  # noqa: E402
from engine.mlb import charts as MC, xstats as X, xstatsfit as XF  # noqa: E402

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
MLB_JS = (ROOT / "web" / "js" / "chart-mlb.js").read_text(encoding="utf-8")


class _models:
    """A models directory of the test's own, so a fit here never meets the box's."""

    def __enter__(self):
        self.old = os.environ.get("QB_MODELS_DIR")
        self.dir = tempfile.mkdtemp()
        os.environ["QB_MODELS_DIR"] = self.dir
        return Path(self.dir)

    def __exit__(self, *a):
        if self.old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = self.old
        shutil.rmtree(self.dir, ignore_errors=True)


def _balls():
    """Hard line drives fall in, soft grounders do not, with a little of each."""
    rows = []
    for i in range(400):
        rows.append((104.0, 18.0, "double" if i % 4 == 0 else "single" if i % 4 != 3 else "field_out"))
        rows.append((72.0, -12.0, "single" if i % 10 == 0 else "field_out"))
    return rows


# --- the table ---------------------------------------------------------------------

def test_a_ball_falls_in_a_cell_and_the_cell_borrows_from_its_band():
    assert X.keys(104.0, 18.0) == ["e11", "e11l6"] and X.keys(59.0, -40.0) == ["e0", "e0l0"]
    m = X.fit(_balls() + [(None, 10.0, "single"), (95.0, None, "single")])
    assert m["n"] == 800, "a ball with no speed or angle is not fitted"
    hard, soft = X.xvals(m, 104.0, 18.0), X.xvals(m, 72.0, -12.0)
    assert hard[0] > 0.6 and soft[0] < 0.2 and hard[1] > soft[1]
    # 400 balls in the hard band, 300 of them hits, all in one cell: the
    # band is shrunk by PRIOR toward the league, the cell toward the band.
    band = m["cells"]["e11"][0]
    assert abs(band - (300 + X.PRIOR * m["league"][0]) / (400 + X.PRIOR)) < 1e-4
    assert abs(m["cells"]["e11l6"][0] - (300 + X.PRIOR * band) / (400 + X.PRIOR)) < 1e-4
    # A cell the table never saw answers with its band; a band it never saw
    # with the league.
    assert X.xvals(m, 104.0, 60.0) == tuple(m["cells"]["e11"])
    assert X.xvals(m, 115.0, 20.0) == tuple(m["league"])
    assert X.xvals(m, None, 20.0) is None and X.xvals({}, 100.0, 20.0) is None


def test_a_hitter_s_line_counts_at_bats_the_box_score_s_way():
    m = X.fit(_balls())
    hard = X.xvals(m, 104.0, 18.0)
    got = X.line(m, [("strikeout", None, None), ("walk", None, None), ("single", 104.0, 18.0),
                     ("home_run", None, None), ("sac_fly", 99.0, 30.0)])
    assert got["ab"] == 3, "a walk and a sacrifice are no at bat"
    assert abs(got["xh"] - (hard[0] + 1)) < 0.01 and abs(got["xtb"] - (hard[1] + 4)) < 0.01
    assert got["xba"] == round((hard[0] + 1) / 3, 3) and got["xslg"] == round((hard[1] + 4) / 3, 3)
    assert X.line(m, [("walk", None, None)]) == {"ab": 0, "xh": 0, "xtb": 0, "xba": None, "xslg": None}


def test_the_table_is_saved_whole_and_read_back():
    with _models() as d:
        assert X.load() is None
        m = X.fit(_balls())
        p = X.save(m)
        assert p == d / X.MODEL_FILE and X.load() == json.loads(json.dumps(m))
        (d / X.MODEL_FILE).write_text("{broken")
        assert X.load() is None


def test_the_box_fits_on_every_stored_ball_or_those_before_a_date():
    conn = D.connect(":memory:")
    rows = [{"game_pk": 1, "at_bat": i, "season": 2026, "date": "2026-05-01" if i < 5 else "2026-06-01",
             "batter_id": 7, "batter": "A Hitter", "event_type": "single" if i % 2 else "field_out",
             "launch_speed": 95.0 + i, "launch_angle": 12.0} for i in range(10)]
    rows.append(dict(rows[0], at_bat=99, event_type="strikeout", launch_speed=None, launch_angle=None))
    D.upsert_mlb_pa(conn, rows)
    assert X.fit_from_db(conn)["n"] == 10 and X.fit_from_db(conn, before="2026-06-01")["n"] == 5


# --- the test ----------------------------------------------------------------------

def _world(seed=7, players=90, days=120, signal=True):
    """A season of hitters. With ``signal`` a hitter's skill is how hard he
    hits it, and a ball's fate follows its speed and angle with luck on
    top; without, his skill is in the outcome alone and the speed and
    angle are noise."""
    rnd = random.Random(seed)
    ev_skill = {p: rnd.gauss(0, 6) for p in range(players)}
    hit_skill = {p: rnd.gauss(0, 0.08) for p in range(players)}
    rows, gpk = [], 0
    for d in range(days):
        date = f"2026-{4 + d // 28:02d}-{1 + d % 28:02d}"
        for p in range(players):
            gpk += 1
            for _ in range(4):
                if rnd.random() < 0.2:
                    rows.append((date, 2026, gpk, p, "strikeout", None, None))
                    continue
                if signal:
                    ev, la = rnd.gauss(88 + ev_skill[p], 10), rnd.gauss(12, 22)
                    ph = 1 / (1 + math.exp(-((ev - 94) / 5))) * (0.95 if 5 < la < 30 else 0.3)
                else:
                    ev, la = rnd.gauss(88, 10), rnd.gauss(12, 22)
                    ph = min(max(0.3 + hit_skill[p], 0.02), 0.9)
                if rnd.random() < ph:
                    et = ("home_run" if signal and ev > 100 and 20 < la < 38 and rnd.random() < 0.5
                          else rnd.choice(["single", "single", "single", "double"]))
                else:
                    et = "field_out"
                rows.append((date, 2026, gpk, p, et, round(ev, 1), round(la, 1)))
    return rows


def test_the_bar_is_the_one_written_before_any_run():
    """Changing any of these after a run is choosing the answer: tell Ethan."""
    assert (XF.TRAIN_SHARE, XF.TUNE_SHARE) == (0.60, 0.15)
    assert XF.GRID == (25, 50, 100, 200, 400, 800) and XF.MIN_PRIOR_AB == 20
    assert (XF.BAR_LOGLOSS, XF.BAR_MSE, XF.MIN_GAMES) == (0.001, 0.005, 2000)
    assert set(XF.TARGETS) == {"hits", "bases"}


def test_the_table_sees_train_only_and_each_game_sees_his_earlier_at_bats_only():
    rows = _world(players=20, days=40)
    ss, league, model, (tune_from, test_from) = XF.samples(rows)
    dates = sorted({r[0] for r in rows})
    assert tune_from == dates[int(len(dates) * 0.60)] and test_from == dates[int(len(dates) * 0.75)]
    train = [r for r in rows if r[0] < tune_from]
    assert model == X.fit((r[5], r[6], r[4]) for r in train)
    # Scramble every ball after TRAIN: the table cannot move.
    later = [(d, s, g, b, "home_run", 120.0, 25.0) if d >= tune_from else (d, s, g, b, e, v, a)
             for d, s, g, b, e, v, a in rows]
    assert XF.samples(later)[2] == model
    # Only TUNE and TEST games are predicted, each with enough earlier at bats.
    assert ss and all(s["date"] >= tune_from and s["ab"] >= XF.MIN_PRIOR_AB and s["g_ab"] >= 1 for s in ss)
    assert all(s["part"] == ("test" if s["date"] >= test_from else "tune") for s in ss)
    ab = [r for r in train if r[4] not in MC.NOT_AB]
    assert abs(league[0] - sum(1 for r in ab if r[4] in MC.HIT_BASES) / len(ab)) < 1e-12


def test_the_season_to_date_line_is_his_alone_and_before_the_game():
    # Two hitters, three days, the second day a doubleheader.
    rows = [("2026-04-01", 2026, 1, 1, "single", 100.0, 15.0), ("2026-04-01", 2026, 1, 1, "strikeout", None, None),
            ("2026-04-01", 2026, 1, 2, "home_run", 108.0, 28.0),
            ("2026-04-02", 2026, 2, 1, "field_out", 80.0, -5.0), ("2026-04-02", 2026, 3, 1, "walk", None, None),
            ("2026-04-02", 2026, 3, 1, "double", 102.0, 20.0),
            ("2026-04-03", 2026, 4, 1, "single", 95.0, 10.0)]
    ss, *_ = XF.samples(rows, model=X.fit(_balls()), tune_from="2026-04-02", test_from="2026-04-03", min_prior_ab=0)
    got = [(s["date"], s["ab"], s["h"], s["tb"], s["g_ab"], s["g_hit"], s["g_tb"]) for s in ss]
    assert got == [("2026-04-02", 2, 1, 1, 1, 0, 0),       # game 2: his day-one line only
                   ("2026-04-02", 3, 1, 1, 1, 1, 2),       # game 3: day one and game 2, the walk no at bat
                   ("2026-04-03", 4, 2, 3, 1, 1, 1)]
    assert [s["part"] for s in ss] == ["tune", "tune", "test"]


def test_contact_quality_that_carries_the_signal_passes_and_noise_does_not():
    signal = XF.measure(_world(signal=True), min_games=500)
    noise = XF.measure(_world(signal=False), min_games=500)
    assert signal["passed"]["hits"] is True
    h = signal["targets"]["hits"]
    assert all(p["gain"] >= XF.BAR_LOGLOSS for p in h["halves"]) and h["test"]["expected"] < h["test"]["league"]
    assert noise["passed"] == {"hits": False, "bases": False}
    assert all(p["gain"] < 0 for t in noise["targets"].values() for p in t["halves"])
    # Too few hitter-games pass nothing, however good the gain.
    assert XF.measure(_world(signal=True))["passed"]["hits"] is False


def test_the_shrink_is_picked_on_tune_alone():
    rows = _world(players=40, days=80)
    base = XF.measure(rows, min_games=1)
    test_from = base["test_from"]
    flipped = [(d, s, g, b, ("field_out" if e in MC.HIT_BASES else "single") if d >= test_from and e != "strikeout" else e, v, a)
               for d, s, g, b, e, v, a in rows]
    again = XF.measure(flipped, min_games=1)
    for t in ("hits", "bases"):
        assert again["targets"][t]["k_actual"] == base["targets"][t]["k_actual"]
        assert again["targets"][t]["k_expected"] == base["targets"][t]["k_expected"]
        assert again["targets"][t]["test"] != base["targets"][t]["test"]


def test_the_verdict_is_saved_and_read_back():
    with _models() as d:
        assert XF.measured() is None
        res = XF.measure(_world(players=20, days=40), min_games=1)
        p = XF.save(res)
        assert p == d / XF.MEASURED_FILE
        back = XF.measured()
        assert back["passed"] == res["passed"] and back["version"] == 1 and back["at"]


# --- the page ------------------------------------------------------------------------

def _hitter_conn():
    conn = D.connect(":memory:")
    rows = [{"game_pk": 10, "at_bat": i, "season": 2026, "date": "2026-09-01", "batter_id": 5,
             "batter": "Pat Batter", "bat_side": "R", "pitch_hand": "R", "pitcher": "Some Arm",
             "team": "NYY", "opponent": "BOS", "home": 1, "inning": i + 1, "half": "B",
             "event": e, "event_type": e, "rbi": 0, "pitches": 3, "launch_speed": ls, "launch_angle": la,
             "coord_x": 120.0 if ls else None, "coord_y": 100.0 if ls else None,
             "trajectory": "line_drive" if ls else None}
            for i, (e, ls, la) in enumerate([("single", 104.0, 18.0), ("field_out", 72.0, -12.0),
                                             ("strikeout", None, None), ("walk", None, None)])]
    D.upsert_mlb_pa(conn, rows)
    return conn


def test_the_hit_tracker_carries_the_expected_line_once_there_is_a_table():
    with _models():
        bare = MC.hits_chart(_hitter_conn(), "Pat Batter")
        assert bare["season_line"]["xba"] is None and bare["x_measured"] is None
        assert not any("xh" in p for g in bare["games"] for p in g["pas"])
        assert bare["season_line"]["slg"] == round(1 / 3, 3)
        m = X.fit(_balls())
        X.save(m)
        got = MC.hits_chart(_hitter_conn(), "Pat Batter")
        pas = got["games"][0]["pas"]
        hard, soft = X.xvals(m, 104.0, 18.0), X.xvals(m, 72.0, -12.0)
        assert pas[0]["xh"] == round(hard[0], 3) and pas[1]["xtb"] == round(soft[1], 3)
        assert "xh" not in pas[2] and "xh" not in pas[3]
        L = got["season_line"]
        assert L["ab"] == 3 and L["xba"] == round((hard[0] + soft[0]) / 3, 3)
        assert L["xslg"] == round((hard[1] + soft[1]) / 3, 3)
        assert got["by_type"][0]["xba"] is not None
        assert got["x_measured"] is None, "no verdict until the test has run"
        XF.save(XF.measure(_world(signal=False, players=20, days=40), min_games=1))
        got = MC.hits_chart(_hitter_conn(), "Pat Batter")
        assert got["x_measured"]["hits"] is False and len(got["x_measured"]["at"]) == 10


def test_the_nightly_refits_the_table_after_the_balls_come_in():
    src = inspect.getsource(M._run_chores)
    i = src.index("_mlbc.backfill(_mc, today.year, yesterday.isoformat())")
    j = src.index("_xs.fit_from_db(_mc)")
    assert i < j < src.index("mlb charts failed", i)
    assert '_xm["n"] >= _xs.MIN_BALLS' in src and "_xs.save(_xm)" in src


def test_nothing_that_prices_a_bet_reads_it():
    allowed = {"engine/mlb/xstats.py", "engine/mlb/xstatsfit.py", "engine/mlb/charts.py", "engine/maintenance.py"}
    found = set()
    for p in list((ROOT / "engine").rglob("*.py")) + [ROOT / "server.py", ROOT / "launch.py"]:
        if "xstats" in p.read_text(encoding="utf-8"):
            found.add(p.relative_to(ROOT).as_posix())
    assert found <= allowed, found - allowed


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


def test_the_page_shows_xba_and_xslg_and_what_the_test_found():
    with _models():
        X.save(X.fit(_balls()))
        d = MC.hits_chart(_hitter_conn(), "Pat Batter")
    passed = dict(d, x_measured={"hits": True, "bases": False, "at": "2026-10-14"})
    failed = dict(d, x_measured={"hits": False, "bases": False, "at": "2026-10-14"})
    got = _node(f"""
      const d = {json.dumps(d)}, P = {json.dumps(passed)}, F = {json.dumps(failed)}, SP = T.DRAW.spray;
      const g = d.games[0];
      return {{ side: SP.seasonSide(d), tip: SP.tip(g.pas[0], g, d), tipK: SP.tip(g.pas[2], g, d),
               none: SP.note(d), yes: SP.note(P), no: SP.note(F), tables: SP.splits(d) }};
    """)
    if got is None:
        return
    assert ">AVG<" in got["side"] and "xBA ." in got["side"] and ">SLG<" in got["side"] and "xSLG ." in got["side"]
    assert "Launch angle" in got["side"]
    assert "xBA ." in got["tip"] and "xBA" not in got["tipK"]
    assert "not yet been measured as a pick signal" in got["none"]
    assert "read a hitter’s next game better than his own average did" in got["yes"]
    assert "did not read a hitter’s next game better" in got["no"]
    for k in ("none", "yes", "no"):
        assert "nothing here moves a price" in got[k]
    assert ">xBA<" in got["tables"]
    assert "onclick" not in MLB_JS and "onerror" not in MLB_JS and not re.search(r"on(error|load)\s*=", MLB_JS)


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
