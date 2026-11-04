"""The NBA's spread that follows the projection, and the box check that
measures it and the shooting read (`hoops.NBA.sd_power`, `prob.spread_on`,
nbalabcheck.py).

The NBA lab (docs/NBA_LAB.md): one CV per stat — and the box fits it the
way that makes it widest, the median of every player's game-to-game spread,
garbage-time nights and all — made a star's line too wide and a bench line
too narrow. Variance = a × projection^c, fit on 2024-25 and judged on
2025-26, was 0.8-2.1% better on Brier in every market below and said the
Most Likely kind of over within a point of how often it hit. It waits
behind QB_NBA_SPREAD=1 because the stored calibration curves were fit on
the CV spread. These hold:

  * off by default: the board prices exactly as before;
  * on: SD = sqrt(a × μ^c) for the seven markets, threes and the WNBA untouched;
  * a bench line's relative spread is wider than a star's;
  * the counts still go through the negative binomial at that spread;
  * nbalabcheck.py replays both changes off and on, writes nothing, and
    leaves the switches as it found them.

Run directly: `python3 tests/test_nba_spread_follows_the_projection.py`
"""
import contextlib
import io
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.hoops import NBA, WNBA                           # noqa: E402
from engine.nba import prob as P                             # noqa: E402

SEVEN = ("pts", "reb", "ast", "pra", "pts_reb", "pts_ast", "reb_ast")


@contextlib.contextmanager
def _env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    os.environ.update({k: v for k, v in kw.items()})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_off_by_default_the_board_prices_as_before():
    os.environ.pop("QB_NBA_SPREAD", None)
    assert not P.spread_on()
    assert P.sd_for("pts", 20, NBA) == max(0.1, NBA.sd_cv["pts"] * 20)
    assert P.p_over("pts", 20, 14.5, NBA) == round(P.p_over_normal(20, 14.5, NBA.sd_cv["pts"] * 20), 4)


def test_on_the_seven_markets_follow_the_projection_and_nothing_else_moves():
    assert set(NBA.sd_power) == set(SEVEN) and WNBA.sd_power == {}
    with _env(QB_NBA_SPREAD="1"):
        for stat in SEVEN:
            a, c = NBA.sd_power[stat]
            assert abs(P.sd_for(stat, 12.0, NBA) - math.sqrt(a * 12.0 ** c)) < 1e-9, stat
        assert P.sd_for("fg3m", 2.5, NBA) == max(0.1, NBA.sd_cv["fg3m"] * 2.5), "threes keep their CV"
        assert P.sd_for("pts", 20, WNBA) == max(0.1, WNBA.sd_cv["pts"] * 20), "the WNBA keeps its CVs"


def test_a_bench_line_is_wider_than_a_stars_for_its_size():
    with _env(QB_NBA_SPREAD="1"):
        assert P.sd_for("pts", 5, NBA) / 5 > P.sd_for("pts", 25, NBA) / 25 * 1.5
        assert P.sd_for("ast", 1.5, NBA) / 1.5 > P.sd_for("ast", 9, NBA) / 9


def test_the_counts_still_go_through_the_negative_binomial():
    with _env(QB_NBA_SPREAD="1"):
        a, c = NBA.sd_power["reb"]
        cv = math.sqrt(a * 8.0 ** c) / 8.0
        assert P.p_over("reb", 8.0, 5.5, NBA) == round(P.p_over_negbin(8.0, 5.5, cv), 4)
        assert P.p_over("reb", 0.0, 0.5, NBA) == 0.0, "a zero mean still cannot cross"


def _history_db():
    from engine import db
    conn = db.connect(":memory:")
    rows = []
    for p, (pts, fg3m, fg3a) in {"Hot Hand": (22, 4, 9), "Steady": (14, 2, 6)}.items():
        for d in range(40):
            day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
            made3 = fg3m + (2 if d % 5 == 0 else 0) - (1 if d % 7 == 0 else 0)
            g = {"min": 32.0 + (d % 4), "pts": float(pts + (d % 6) - 2), "reb": 6.0 + d % 3,
                 "ast": 4.0 + d % 2, "fg3m": float(max(0, made3)), "fg3a": float(fg3a),
                 "fga": 16.0, "fgm": 7.0 + d % 2, "fta": 5.0, "ftm": 4.0}
            for k, v in g.items():
                rows.append(("nba", 2026, day, f"g{d}", p, "BOS", "NYK", "S", 1, k, v))
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return conn


def test_the_box_check_replays_both_changes_and_writes_nothing():
    import nbalabcheck
    from engine import db as DB
    conn = _history_db()
    before = conn.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0]

    class _Keep:
        """The check closes its connection; the test keeps reading it."""
        def __init__(self, c):
            self.c = c

        def __getattr__(self, k):
            return getattr(self.c, k)

        def close(self):
            pass

    real = DB.connect
    DB.connect = lambda *a, **k: _Keep(conn)
    os.environ.pop("QB_NBA_SPREAD", None)
    os.environ["QB_NBA_SHOOTING"] = "1"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = nbalabcheck.main([])
    finally:
        DB.connect = real
    out = buf.getvalue()
    assert rc == 0, out
    assert "SHOOTING, LUCK TAKEN OUT" in out and "THE SPREAD THAT FOLLOWS THE PROJECTION" in out
    assert "raw, before any calibration" in out and "shooting: projections closer in" in out
    assert "RMSE" in out and "Brier" in out and "half-point lines" in out
    assert "The board's spreads (one CV per stat, as the build fits them)" in out
    assert "MOST LIKELY'S KIND OF OVER" in out and "spread on Most Likely's kind of over" in out
    assert "spread: ready for the refit" in out or "spread: not yet" in out
    assert conn.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0] == before
    assert os.environ.get("QB_NBA_SHOOTING") == "1" and "QB_NBA_SPREAD" not in os.environ, \
        "the switches are left as they were"
    os.environ.pop("QB_NBA_SHOOTING", None)


def _sp(key, line, actual, p, basis="naive", side="OVER", proj=10.0):
    from engine.backtest import SettledProp
    return SettledProp(player="A", market="reb", line=line, odds=-110, hit_prob=p,
                       projection=proj, actual=actual, recommended=False, stake_units=0.0,
                       side=side, basis=basis, key=key)


def test_a_whole_number_line_is_left_out_of_the_brier_and_a_close_is_scored_alone():
    """A count lands on a whole-number line about one time in five; the push
    is dropped and the board's chance never counted it, so those lines say
    nothing fair about a spread. The replay's own line is whole half the time."""
    import nbalabcheck as L

    class Rep:
        def __init__(self, settled):
            self.settled = settled
    off = [_sp("d1|A", 7.5, 9, 0.60), _sp("d2|A", 7.0, 7, 0.50), _sp("d3|A", 6.5, 5, 0.55, basis="book"),
           _sp("d4|A", 8.0, 10, 0.70)]
    on = [_sp("d1|A", 7.5, 9, 0.70), _sp("d2|A", 7.0, 7, 0.90), _sp("d3|A", 6.5, 5, 0.50, basis="book")]
    p = L._paired(Rep(off), Rep(on))
    assert p["n"] == 3 and p["n_half"] == 2 and p["n_whole"] == 1, p
    assert abs(p["brier"][0] - ((0.6 - 1) ** 2 + (0.55 - 0) ** 2) / 2) < 1e-12
    assert abs(p["brier"][1] - ((0.7 - 1) ** 2 + (0.5 - 0) ** 2) / 2) < 1e-12
    assert p["n_book"] == 1 and abs(p["book"][1] - 0.25) < 1e-12
    assert abs(p["rmse"][0] - (((10 - 9) ** 2 + (10 - 7) ** 2 + (10 - 5) ** 2) / 3) ** 0.5) < 1e-12


def test_the_spread_is_ready_only_when_most_likelys_overs_get_better_and_honest():
    """Ready means, raw: the ladder's Brier lower in five of seven markets,
    the overs it calls 80% or more hitting within three points of that in
    five of seven, and no market worse near the line. Not the average said
    against the average hit: one wide CV can match an average while both
    of its ends are wrong."""
    import nbalabcheck as L

    def lad(lower, honest):
        return {m: (i < lower, i < honest) for i, m in enumerate(SEVEN)}
    near = {m: {"brier": (0.2500, 0.2490)} for m in SEVEN}
    assert L._ready(near, lad(5, 5))[0]
    ok, why = L._ready(near, lad(4, 7))
    assert not ok and "Brier" in why, "four of seven is not enough"
    ok, why = L._ready(near, lad(7, 4))
    assert not ok and "80%" in why, "a better Brier with dishonest top overs is not ready"
    near["reb"] = {"brier": (0.2480, 0.2480 * (1 + L.NEAR_SLACK) + 1e-6)}
    ok, why = L._ready(near, lad(7, 7))
    assert not ok and "reb" in why
    near["reb"] = {"brier": (0.2480, 0.2480 * (1 + L.NEAR_SLACK) - 1e-6)}
    assert L._ready(near, lad(7, 7))[0], "inside the slack is no worse"
    assert L._honest((150, 0.85, 0.83)) and not L._honest((150, 0.85, 0.80))
    assert not L._honest((99, 0.85, 0.85)), "too few to call honest"
    assert not L._honest((0, None, None))


def test_the_check_compares_against_the_spread_the_board_really_uses():
    """The replay's default is the inherited CVs; the board prices with the
    ones `hoops_fit` fits from the box's logs. The check hands the replay
    and the ladder the fitted tuning, and falls back as the build does."""
    import dataclasses
    import nbalabcheck as L
    from engine import hoopsreplay as HR
    conn = _history_db()
    hist = HR.histories(conn, "nba")
    wide = dataclasses.replace(NBA, sd_cv={**NBA.sd_cv, "pts": 0.9})
    os.environ.pop("QB_NBA_SPREAD", None)
    a, _ = HR.settled_props(hist, "pts", "nba", {})
    b, _ = HR.settled_props(hist, "pts", "nba", {}, tune=wide)
    pa, pb = {s.key: s.hit_prob for s in a}, {s.key: s.hit_prob for s in b}
    assert any(pa[k] != pb[k] for k in pa if k in pb), "the tune reached the pricer"
    import engine.hoops_fit as HF
    real = HF.fitted_tuning
    HF.fitted_tuning = lambda conn, league: (wide, {})
    try:
        assert L.board_tune(conn).sd_cv["pts"] == 0.9
        HF.fitted_tuning = lambda conn, league: (_ for _ in ()).throw(RuntimeError("no fit"))
        assert L.board_tune(conn) is NBA, "a failed fit falls back as the build does"
    finally:
        HF.fitted_tuning = real
    src = (ROOT / "nbalabcheck.py").read_text(encoding="utf-8")
    assert src.count("tune=tune") >= 8, "every replay and both ladders get the board's tuning"


def test_the_runbook_runs_the_check_and_refits_before_it_switches():
    """The check is the runbook's line and the catch-up's (JY), RUN_NEXT
    points at it, and the switch comes AFTER an NBA refit run with the new
    spread: the stored calibration was fitted on the old one."""
    line = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 nbalabcheck.py"
    book = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert line in book.split("\n")
    assert line in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8").split("\n")
    assert "catchup.sh JY" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")
    step = book[book.index("**JY. "):book.index("**JX. ")]
    refit = step.index("sudo -u qellys env QB_NBA_SPREAD=1 nohup nice -n 19 python3 -u -m engine.deepfit nba")
    switch = step.index("sudo ./deploy/setenv.sh QB_NBA_SPREAD 1 && sudo systemctl restart qellys")
    assert refit < switch, "the refit on the new spread comes first"


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
