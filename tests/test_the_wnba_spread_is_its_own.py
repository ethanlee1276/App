"""The WNBA's spread that follows the projection, measured on its own six
seasons (`hoops.WNBA.sd_power`, docs/WNBA_LAB.md), and the box check that
reads it on the box's WNBA games (`nbalabcheck.py --league wnba`).

The WNBA kept one CV per stat after the NBA lab, because nothing had been
measured on WNBA games. Six regular seasons of wehoop box scores
(2021-2026) through the board's own projection, fitted on one season and
judged on the next, against the CV the box's own fit sets: the Brier lower
in every judged season in the seven markets below, threes left on their CV
(three seasons better, two worse). What holds:

  * the WNBA reads its own seven values, not the NBA's, threes left out;
  * off by default (the spread's switch is the NBA's: engine/nba/switches),
    the WNBA prices with its CVs exactly as before;
  * on, SD = sqrt(a × μ^c), a bench line wider for its size than a star's;
  * the weekly refit fits the WNBA after the NBA, so the WNBA's calibration
    is refitted on the spread in the same round the NBA's switch turns on;
  * `nbalabcheck.py --league wnba` replays the box's WNBA logs, reads the
    spread only (shooting is the NBA's alone), writes nothing, files no
    verdict (it refuses --save-verdict), and leaves the switches as it
    found them;
  * the runbook's step, the catch-up's line and RUN_NEXT carry it.

Run directly: `python3 tests/test_the_wnba_spread_is_its_own.py`
"""
import contextlib
import io
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.hoops import NBA, WNBA                           # noqa: E402
from engine.nba import prob as P                             # noqa: E402

SEVEN = ("pts", "reb", "ast", "pra", "pts_reb", "pts_ast", "reb_ast")
LINE = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbalabcheck.py --league wnba"


@contextlib.contextmanager
def _env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_the_wnba_reads_its_own_seven_values_and_threes_keep_their_cv():
    assert set(WNBA.sd_power) == set(SEVEN), sorted(WNBA.sd_power)
    assert "fg3m" not in WNBA.sd_power
    assert all(WNBA.sd_power[m] != NBA.sd_power[m] for m in SEVEN), "its own, not the NBA's"
    for m, (a, c) in WNBA.sd_power.items():
        assert 0.5 < a < 15 and 0.4 < c < 1.2, (m, a, c)
    assert WNBA.sd_power["pts"] == (5.927, 0.735) and WNBA.sd_power["pra"] == (8.429, 0.650)


def test_off_by_default_the_wnba_prices_with_its_cvs_as_before():
    with _env(QB_NBA_SPREAD=None):
        if P.spread_on():                 # a verdict on file in this environment: nothing to say
            return
        for m in SEVEN:
            assert P.sd_for(m, 12.0, WNBA) == max(0.1, WNBA.sd_cv[m] * 12.0), m
    with _env(QB_NBA_SPREAD="0"):
        assert P.p_over("pts", 18.0, 14.5, WNBA) == round(P.p_over_normal(18.0, 14.5, WNBA.sd_cv["pts"] * 18.0), 4)


def test_on_the_spread_follows_the_projection_and_a_bench_line_is_wider():
    with _env(QB_NBA_SPREAD="1"):
        for m in SEVEN:
            a, c = WNBA.sd_power[m]
            assert abs(P.sd_for(m, 10.0, WNBA) - math.sqrt(a * 10.0 ** c)) < 1e-9, m
        assert P.sd_for("pts", 5, WNBA) / 5 > P.sd_for("pts", 22, WNBA) / 22 * 1.4
        assert P.sd_for("fg3m", 2.0, WNBA) == max(0.1, WNBA.sd_cv["fg3m"] * 2.0)
        a, c = WNBA.sd_power["reb"]
        cv = math.sqrt(a * 7.0 ** c) / 7.0
        assert P.p_over("reb", 7.0, 4.5, WNBA) == round(P.p_over_negbin(7.0, 4.5, cv), 4), "counts stay discrete"


def test_the_weekly_refit_fits_the_wnba_after_the_nba():
    from engine import deepfit
    order = list(deepfit.PIECE_ORDER)
    assert order.index("wnba") > order.index("nba"), order


def _wnba_db():
    from engine import db
    conn = db.connect(":memory:")
    rows = []
    for p, (pts, reb, ast) in {"Quick Guard": (17, 3, 6), "Big Post": (12, 9, 2)}.items():
        for d in range(40):
            day = f"2025-{5 + d // 28:02d}-{1 + d % 28:02d}"
            g = {"min": 30.0 + (d % 5), "pts": float(pts + (d % 7) - 3), "reb": float(reb + d % 3 - 1),
                 "ast": float(ast + d % 2), "fg3m": float(d % 3), "stl": 1.0, "blk": 0.0, "tov": 2.0}
            for k, v in g.items():
                rows.append(("wnba", 2025, day, f"w{d}", p, "LV", "PHX", "S", 1, k, v))
    rows.append(("nba", 2025, "2025-11-01", "n1", "Not Her League", "BOS", "NYK", "S", 1, "pts", 30.0))
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return conn


class _Keep:
    """The check closes its connection; the test keeps reading it."""
    def __init__(self, c):
        self.c = c

    def __getattr__(self, k):
        return getattr(self.c, k)

    def close(self):
        pass


def _main(conn, argv):
    import nbalabcheck
    from engine import db as DB
    real = DB.connect
    DB.connect = lambda *a, **k: _Keep(conn)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = nbalabcheck.main(argv)
    finally:
        DB.connect = real
    return rc, buf.getvalue()


def test_the_box_check_reads_the_wnba_spread_and_writes_nothing():
    conn = _wnba_db()
    before = conn.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0]
    with _env(QB_NBA_SPREAD=None, QB_NBA_SHOOTING="1"):
        rc, out = _main(conn, ["--league", "wnba"])
        assert os.environ.get("QB_NBA_SHOOTING") == "1" and "QB_NBA_SPREAD" not in os.environ, \
            "the switches are left as they were"
    assert rc == 0, out
    assert "WNBA logs: 40 game dates" in out, out[:300]
    assert "SHOOTING, LUCK TAKEN OUT" not in out, "shooting is the NBA's alone"
    assert "THE SPREAD THAT FOLLOWS THE PROJECTION" in out and "MOST LIKELY'S KIND OF OVER" in out
    assert "wnba spread: ready for the refit" in out or "wnba spread: not yet" in out
    assert "spread verdict filed" not in out
    assert conn.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0] == before


def test_the_wnba_check_files_no_verdict_of_its_own():
    from engine.nba import switches
    conn = _wnba_db()
    before = switches.load()
    rc, out = _main(conn, ["--league", "wnba", "--save-verdict"])
    assert rc == 2 and "files none of its own" in out, out
    assert switches.load() == before, "nothing filed"


def test_the_check_prices_with_the_wnba_s_own_fitted_tuning():
    import dataclasses
    import nbalabcheck as L
    import engine.hoops_fit as HF
    conn = _wnba_db()
    wide = dataclasses.replace(WNBA, sd_cv={**WNBA.sd_cv, "pts": 0.9})
    seen = []
    real = HF.fitted_tuning
    HF.fitted_tuning = lambda conn, league: (seen.append(league) or wide, {})
    try:
        assert L.board_tune(conn, "wnba").sd_cv["pts"] == 0.9 and seen == ["wnba"]
        HF.fitted_tuning = lambda conn, league: (_ for _ in ()).throw(RuntimeError("no fit"))
        assert L.board_tune(conn, "wnba") is WNBA, "a failed fit falls back to the WNBA's own numbers"
        assert L.board_tune(conn) is NBA
    finally:
        HF.fitted_tuning = real


def test_the_runbook_the_catch_up_and_run_next_carry_it():
    book = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert LINE in book.split("\n")
    assert LINE in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8").split("\n")
    assert "catchup.sh KM" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8") \
        or LINE in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")
    lab = (ROOT / "docs" / "WNBA_LAB.md").read_text(encoding="utf-8")
    assert "spread that follows the projection" in lab.lower()


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
