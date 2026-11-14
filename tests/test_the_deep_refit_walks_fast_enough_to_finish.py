"""The deep refit's walks are fast enough to finish, and the dial keeps
each market it fits (engine/storecache, engine/calibrate.one_sided,
formfit.py --resume-after, engine/deepfit._refit_sport).

The NFL's recency dial ran past the deep refit's 45 minutes on the box on
4 November and was cut off, all four markets' walks lost with it, so the
NFL's dial and everything after it stayed dated late August. Profiled on
four NFL seasons here, one market's walk asked the disk for six stores'
file times on every game (125,000 asks, a fifth of the walk) and asked
the temperature store whether it was one-sided four times a game, 51
probes each (83,388 asks, over half). What these hold:

  * inside a walk a store's file time is asked once, and a store written
    inside one is read again; outside a walk it is asked every time, as
    before, so the board sees a store the moment a fitter rewrites it;
  * a walk inside one read prices every game exactly as before, and hands
    every fit the model's raw chance, as MLB's and basketball's walks do
    (fitted on the chance already shrunk toward the walk's -110 proxy, the
    NFL's temperatures lost to the raw fit on all four markets held out,
    and to no correction at all on three);
  * the one-sided answer is kept per market until the stores reload,
    never kept from a store swapped in place, never when the yes-only
    registry could not be read, and never while calibration is off;
  * the dial writes each market the moment it is fitted, whole or not at
    all, keeps the ones fitted since the round began when asked
    (--resume-after), and says so; a run by hand still fits every market;
  * the weekly refit hands the dial its round's first day, and its line
    says which markets were kept rather than "nothing adopted".

Run directly: `python3 tests/test_the_deep_refit_walks_fast_enough_to_finish.py`
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import types
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import calibrate as C                                # noqa: E402
from engine import deepfit as D                                  # noqa: E402
from engine import formfit as ff                                 # noqa: E402
from engine import losspatterns as LP                            # noqa: E402
from engine import storecache as SC                              # noqa: E402


class _Stats:
    """Count the disk's answers to os.stat while it is in place."""
    def __enter__(self):
        self.real, self.n = os.stat, 0

        def counted(*a, **k):
            self.n += 1
            return self.real(*a, **k)
        os.stat = counted
        return self

    def __exit__(self, *exc):
        os.stat = self.real


def test_inside_a_walk_a_stores_time_is_asked_once_and_outside_every_time():
    p = Path(tempfile.mkdtemp()) / "store.json"
    p.write_text("{}")
    with _Stats() as st:
        for _ in range(5):
            SC.mtime(p)
    assert st.n == 5, "outside a walk the disk is asked every time"
    with _Stats() as st, SC.frozen():
        for _ in range(5):
            SC.mtime(p)
        with SC.frozen():
            SC.mtime(str(p))
    assert st.n == 1, st.n
    assert SC.mtime(Path(p.parent) / "missing.json") is None
    with SC.frozen():
        assert SC.mtime(p) is not None
    assert not SC._MEMO, "nothing is remembered once the walk ends"


def test_a_store_written_inside_a_walk_is_read_again():
    d = Path(tempfile.mkdtemp())
    path = d / "losspatterns.json"
    with SC.frozen():
        assert LP.load(path) == {}, "no file yet"
        LP.save({"v": 1}, path)
        assert LP.load(path) == {"v": 1}, "the writer's forget makes the next read ask the disk"
        LP.save({"v": 2}, path)
        assert LP.load(path) == {"v": 2}
    assert LP.load(path) == {"v": 2}


def _entries(n_players=6, n_games=60):
    import random
    rng = random.Random(7)
    return [{"name": f"Player {i}", "values": [max(0, int(rng.gauss(55, 25))) for _ in range(n_games)]}
            for i in range(n_players)]


def _rows(settled):
    return [(s.player, s.line, s.odds, s.hit_prob, s.projection, s.actual, s.recommended,
             s.stake_units, s.side, s.grade) for s in settled]


def test_a_walk_inside_one_read_prices_every_game_as_before_and_asks_the_disk_little():
    from engine import logwalk as LW
    entries = _entries()
    plain = LW._settled_props(entries, "rec_yds", "nfl", 4, 30, None, None, None, None)
    with _Stats() as st:
        once = LW.settled_props_from_logs(entries, "rec_yds", sport="nfl")
    assert _rows(plain) == _rows(once) and len(once) >= 300, len(once)
    assert st.n < 40, f"{st.n} file checks for {len(once)} games: a store is being asked per game"
    import inspect
    assert "with frozen():" in inspect.getsource(LW.walk), "every harness walks inside one read"


def test_the_walk_hands_every_fit_the_raw_chance_as_the_other_walks_do():
    """The board corrects the model's raw chance and shrinks toward the
    market after; the fits must learn on the raw one. MLB's walk and the
    basketball one carried it; this one handed over the shrunk chance."""
    from engine import calibrate as cal, logwalk as LW
    from engine.backtest import evaluate
    entries = _entries()
    raws = []
    real = LW.evaluate_prop

    def seen(*a, **k):
        r = real(*a, **k)
        raws.append(r.raw_prob)
        return r
    LW.evaluate_prop = seen
    try:
        with cal.disabled():
            settled = LW.settled_props_from_logs(entries, "rec_yds", sport="nfl")
    finally:
        LW.evaluate_prop = real
    assert len(raws) == len(settled) >= 300
    assert all(s.raw_prob == r for s, r in zip(settled, raws)), "each game keeps the board's raw chance"
    pairs = evaluate(settled).pairs
    want = [((s.raw_prob if (s.side or "OVER").upper() == "OVER" else 1 - s.raw_prob), s.over_hit)
            for s in settled if s.over_hit is not None]
    assert pairs == want
    wide = max(p for p, _ in pairs) - min(p for p, _ in pairs)
    shrunk = [(s.hit_prob if (s.side or "OVER").upper() == "OVER" else 1 - s.hit_prob) for s in settled]
    assert wide > max(shrunk) - min(shrunk), "the raw chance spreads wider than the shrunk one"
    import inspect
    assert "raw_prob=rec.raw_prob" in inspect.getsource(LW._settled_props)


def _curve_store(knots):
    tmp = os.path.join(tempfile.mkdtemp(), "cal.json")
    json.dump({"nfl:rush_yds": {"temperature": 1.0, "intercept": 0.0, "samples": 5000,
                                "curve": {"knots": knots}, "sport": "nfl", "market": "rush_yds"}},
              open(tmp, "w"))
    C.reset_cache()
    return tmp


SATURATING = [[0.0, 0.05], [0.4, 0.210], [0.5, 0.305], [0.6, 0.401], [1.0, 0.402]]
HEALTHY = [[0.0, 0.02], [0.5, 0.48], [1.0, 0.97]]


def _counting_probe():
    real, seen = C._apply_raw, [0]

    def probe(*a, **k):
        seen[0] += 1
        return real(*a, **k)
    C._apply_raw = probe
    return seen, lambda: setattr(C, "_apply_raw", real)


def test_the_one_sided_answer_is_asked_once_a_market_until_the_stores_reload():
    tmp = _curve_store(SATURATING)
    seen, undo = _counting_probe()
    try:
        for _ in range(200):
            assert C.one_sided("nfl", "rush_yds", tmp)
            C.calibrated("nfl", "rush_yds", 0.6, tmp)
        assert seen[0] <= 2 * C.SIDE_PROBE, seen[0]
        json.dump({"nfl:rush_yds": {"temperature": 1.0, "intercept": 0.0, "samples": 5000,
                                    "curve": {"knots": HEALTHY}}}, open(tmp, "w"))
        C.reset_cache()
        assert not C.one_sided("nfl", "rush_yds", tmp), "a reload is asked afresh"
        C._curves = dict(C._curves or {})
        before = seen[0]
        C.one_sided("nfl", "rush_yds", tmp)
        assert seen[0] > before, "a store swapped in place is asked afresh, not served stale"
        with C.disabled():
            assert not C.one_sided("nfl", "rush_yds", tmp)
    finally:
        undo()
        C.reset_cache()


def test_the_answer_is_not_kept_when_the_yes_only_registry_cannot_be_read():
    tmp = _curve_store(SATURATING)
    keep = sys.modules.get("engine.maintenance")
    sys.modules["engine.maintenance"] = types.ModuleType("engine.maintenance")
    try:
        assert C.one_sided("nfl", "rush_yds", tmp)
        assert not C._sided, "an answer read without the registry is given, not kept"
    finally:
        if keep is not None:
            sys.modules["engine.maintenance"] = keep
        else:
            sys.modules.pop("engine.maintenance", None)
        C.reset_cache()
    assert C.one_sided("nfl", "rush_yds", tmp) and C._sided
    C.reset_cache()
    assert not C._sided, "reset_cache forgets every answer"


# --- the dial keeps each market ---------------------------------------------
def _fit(market, r=0.3, adopted=True):
    return ff.FormFit(sport="nfl", market=market, r=r, samples=5000, brier_default=0.2400,
                      brier_fitted=0.2390, adopted=adopted, weights=ff.family(ff.base_for("nfl"), r),
                      curve={0.0: 0.24, r: 0.239})


def _run_dial(store, argv, die_on=None):
    """formfit.py's main on a stand-in history: each market's fit is
    recorded; ``die_on`` stops the run inside that market, as the refit's
    time limit does."""
    import formfit as CLI
    import engine.logwalk as LW
    asked = []

    def fit(entries, market, sport="nfl", min_history=None, base=None, checkpoint=None):
        asked.append(market)
        if market == die_on:
            raise KeyboardInterrupt("time limit")
        return _fit(market)
    keep = (ff.DEFAULT_PATH, ff.fit, CLI._db.connect, LW.load_entries, sys.argv)
    ff.DEFAULT_PATH, ff.fit = store, fit
    CLI._db.connect = lambda path: object()
    LW.load_entries = lambda conn, sport, market, min_games=8, seasons=None: [{"name": "x", "values": [1] * 9}]
    sys.argv = ["formfit.py", "--sport", "nfl", "--from-db", "unused.db", *argv]
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            try:
                CLI.main()
            except KeyboardInterrupt:
                pass
    finally:
        ff.DEFAULT_PATH, ff.fit, CLI._db.connect, LW.load_entries, sys.argv = keep
    return asked, out.getvalue()


def test_each_market_is_written_the_moment_it_is_fitted():
    store = Path(tempfile.mkdtemp()) / "formfit.json"
    asked, _ = _run_dial(store, [], die_on="rec_yds")
    assert asked == ["pass_yds", "rush_yds", "rec_yds"], asked
    kept = json.loads(store.read_text())
    assert set(kept) == {"nfl:pass_yds", "nfl:rush_yds"}, "the two finished before the cut are kept"
    assert all(v.get("fitted") for v in kept.values())


def test_a_run_of_the_same_round_fits_only_what_is_left_and_says_what_it_kept():
    store = Path(tempfile.mkdtemp()) / "formfit.json"
    store.write_text(json.dumps({
        "nfl:pass_yds": dict(_fit("pass_yds").to_dict(), fitted="2026-11-05T01:10:00"),
        "nfl:rush_yds": dict(_fit("rush_yds").to_dict(), fitted="2026-10-29T02:00:00"),
        "mlb:hits": dict(_fit("hits").to_dict(), fitted="2026-11-05T01:00:00")}))
    asked, text = _run_dial(store, ["--resume-after", "2026-11-04"])
    assert asked == ["rush_yds", "rec_yds", "receptions"], "last round's rushing fit is refitted"
    assert "Passing Yards    kept — fitted 2026-11-05 01:10, earlier this round" in text, text
    got = json.loads(store.read_text())
    assert got["nfl:pass_yds"]["fitted"] == "2026-11-05T01:10:00", "a kept market is not rewritten"
    assert "mlb:hits" in got, "another sport's dial is never touched"


def test_by_hand_every_market_is_fitted_and_a_round_already_done_says_so():
    store = Path(tempfile.mkdtemp()) / "formfit.json"
    store.write_text(json.dumps({f"nfl:{m}": dict(_fit(m).to_dict(), fitted="2026-11-05T01:00:00")
                                 for m in ("pass_yds", "rush_yds", "rec_yds", "receptions")}))
    asked, _ = _run_dial(store, [])
    assert asked == ["pass_yds", "rush_yds", "rec_yds", "receptions"], "no --resume-after: all of them"
    asked, text = _run_dial(store, ["--resume-after", "2026-11-04"])
    assert asked == [] and "Every market was fitted earlier this round" in text, text
    assert "Nothing fitted. Ingest history first" not in text


def test_a_dial_store_is_written_whole_or_not_at_all():
    store = Path(tempfile.mkdtemp()) / "formfit.json"
    ff.save({"mlb:hits": _fit("hits")}, store)
    before = store.read_text()
    real = os.replace

    def killed(*a, **k):
        raise KeyboardInterrupt("killed between the write and the swap")
    os.replace = killed
    try:
        try:
            ff.save({"nfl:rec_yds": _fit("rec_yds")}, store)
        except KeyboardInterrupt:
            pass
    finally:
        os.replace = real
    assert store.read_text() == before, "the store is the old one whole, never half of the new"
    ff.save({"nfl:rec_yds": _fit("rec_yds")}, store)
    assert set(json.loads(store.read_text())) == {"mlb:hits", "nfl:rec_yds"}


class _Fitters:
    def __init__(self, out=None):
        self.cmds, self.out = [], out or {}

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, self.out.get(Path(cmd[1]).name, ""), "")


def test_the_weekly_refit_hands_the_dial_its_rounds_first_day():
    import datetime as dt
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "deepfit_state.json"
    path.write_text(json.dumps({"round": "2026-11-04", "left": ["nfl"], "pieces": {}}))
    f = _Fitters()
    keep_rows, keep_run = D._row_counts, subprocess.run
    D._row_counts = lambda db="data/history.db": {"nfl": 330_000}
    subprocess.run = f
    try:
        D.run_round(db="unused", state_path=path, today=dt.date(2026, 11, 5), budget_s=3600)
    finally:
        D._row_counts, subprocess.run = keep_rows, keep_run
    by = {Path(c[1]).name: c for c in f.cmds}
    assert by["formfit.py"][-2:] == ["--resume-after", "2026-11-04"], by["formfit.py"]
    assert "--resume-after" not in by["playerfit.py"] and "--resume-after" not in by["calibrate.py"]
    g = _Fitters()
    keep_run = subprocess.run
    subprocess.run = g
    try:
        D.refit_sport("nfl", db="unused")
    finally:
        subprocess.run = keep_run
    assert "--resume-after" not in g.cmds[0], "a refit by hand fits every market"


def test_the_refits_line_says_which_markets_were_kept():
    allkept = ("  Passing Yards    kept — fitted 2026-11-05 01:10, earlier this round\n"
               "  Rushing Yards    kept — fitted 2026-11-05 01:30, earlier this round\n"
               "\nEvery market was fitted earlier this round; nothing left to fit.\n")
    f = _Fitters({"formfit.py": allkept})
    keep_run = subprocess.run
    subprocess.run = f
    try:
        lines, finished = D._refit_sport("nfl", db="unused", round_of="2026-11-04")
    finally:
        subprocess.run = keep_run
    dial = [ln for ln in lines if " recency dial " in ln]
    assert dial == ["deep refit: nfl recency dial — 2 market(s) fitted earlier this round, kept"], dial
    some = allkept.replace("\nEvery market", "  Receptions        5,000 settled   Brier 0.2400 → 0.2400   r = +0.0\n"
                                            "\nEvery market")
    g = _Fitters({"formfit.py": some})
    subprocess.run = g
    try:
        lines, _ = D._refit_sport("nfl", db="unused", round_of="2026-11-04")
    finally:
        subprocess.run = keep_run
    dial = [ln for ln in lines if " recency dial " in ln]
    assert dial[0].endswith("2 market(s) fitted earlier this round, kept")
    assert dial[1] == "deep refit: nfl recency dial — nothing adopted (the record did not beat the default)"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
