"""The settle pass's hourly learners, and the record export's two-leg
section, say where their time went (engine/maintenance._learn_sampled,
engine/stacksample.Sampler(qualify=True), engine/ledger.TWO_LEG_LAST).

The first settle pass after the 04:35 restart on 10 November learned for
528.6 seconds and exported for 144.9, 63.7 of them in the two-leg parlay
section, on a one-CPU box beside the board builds, with nothing to say
which learner or which half. What these hold:

  * a qualified sample names each section with its module, so six modules'
    ``refresh`` are six sections, not one;
  * the learners run through the sampler and their seconds land on the
    pass's phases as ``learn_parts``, at both places the pass learns;
  * the two-leg section times its two halves (the pools' record and the
    backtest, kept or worked out) and the settle pass puts them on its
    phases as ``export_two_leg``, cleared before each export;
  * every pass carries the last learning pass's breakdown and the last
    export's (``last_learned``, ``last_exported``) through the settle state,
    since the heartbeat shows only the latest pass (07:41 on 11 November: a
    quiet pass, every overnight one that learned replaced);
  * the biggest learner says where its own time went: the game-line
    calibration (128.8 of 249.1 seconds at 04:03 on 12 November) times each
    league's fit and each read (``engine.gamecal.LAST``), the settle pass
    puts it on ``learn_gamecal``, cleared before each pass, and keeps the
    last one under ``last_learned``.

Run directly: `python3 tests/test_the_learners_say_which_took_their_time.py`
"""
import importlib
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.stacksample import Sampler                             # noqa: E402

LEARNER = '''
import time


def refresh(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass
'''


def _two_learners(folder):
    """Two modules, ``learner_a`` and ``learner_b``, each with a ``refresh``."""
    for name in ("learner_a", "learner_b"):
        (Path(folder) / f"{name}.py").write_text(LEARNER, encoding="utf-8")
    sys.path.insert(0, folder)
    try:
        return importlib.import_module("learner_a"), importlib.import_module("learner_b")
    finally:
        sys.path.remove(folder)


def test_a_qualified_sample_tells_two_refreshes_apart():
    with tempfile.TemporaryDirectory() as td:
        a, b = _two_learners(td)

        def learn():
            a.refresh(0.5)
            b.refresh(0.25)
        with Sampler(learn.__code__, interval=0.01, qualify=True) as s:
            learn()
        parts = s.seconds()
        assert parts.get("learner_a.refresh", 0) > 0.3 and parts.get("learner_b.refresh", 0) > 0.1, parts
        assert parts["learner_a.refresh"] > parts["learner_b.refresh"], parts
        with Sampler(learn.__code__, interval=0.01) as plain:
            learn()
        assert set(plain.seconds()) <= {"refresh", "(self)"}, "unqualified, the two are one"
        sys.modules.pop("learner_a", None)
        sys.modules.pop("learner_b", None)


def test_the_learners_seconds_land_on_the_phases():
    from engine import maintenance as M
    with tempfile.TemporaryDirectory() as td:
        a, b = _two_learners(td)

        def learn():
            a.refresh(0.4)
            b.refresh(0.2)
        phases: dict = {}
        M._learn_sampled(learn, phases)
        parts = phases.get("learn_parts") or {}
        assert parts.get("learner_a.refresh", 0) > 0.25 and parts.get("learner_b.refresh", 0) > 0.08, parts
        sys.modules.pop("learner_a", None)
        sys.modules.pop("learner_b", None)
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert src.count("_learn_sampled(learn, phases)") == 2, "both places the pass learns"
    i = src.index("def settle_open(")
    assert "                learn()\n" not in src[i:] and "            learn()\n" not in src[i:], \
        "the pass learns only through the sampler"


def test_the_two_leg_halves_are_timed_and_reach_the_phases():
    from engine import ledger
    from engine import maintenance as M
    conn = ledger.connect(":memory:")
    ledger._two_leg_record(conn)
    last = dict(ledger.TWO_LEG_LAST)
    assert {"report_s", "backtest_s", "backtest"} <= set(last), last
    assert last["backtest"] in ("kept", "worked out"), last
    if last["backtest"] == "worked out":
        assert {"schedule_s", "groups", "paired"} <= set(last), last
    real = ledger.export_json
    ledger.TWO_LEG_LAST.update(report_s=9.9)                 # a stale copy from an earlier export

    def export(c, p):
        ledger.TWO_LEG_LAST.update(report_s=0.1, backtest_s=0.2, backtest="kept")
    ledger.export_json = export
    try:
        phases: dict = {}
        M._export_record(conn, phases)
        assert phases["export_two_leg"] == {"report_s": 0.1, "backtest_s": 0.2, "backtest": "kept"}, phases

        def export_none(c, p):
            pass
        ledger.export_json = export_none
        phases = {}
        M._export_record(conn, phases)
        assert "export_two_leg" not in phases, "cleared before each export: never an earlier one's"
    finally:
        ledger.export_json = real


def test_every_pass_carries_the_last_learning_and_the_last_export():
    from engine import maintenance as M
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "maintenance.json"
        state = M._load_state(path)
        learned = {"learned": True, "learn": 12.3, "learn_parts": {"selectionfit.refresh": 9.1},
                   "exported": True, "export": 4.0, "export_parts": {"_two_leg_record": 2.5},
                   "export_two_leg": {"report_s": 0.4, "backtest_s": 2.1, "backtest": "kept"}}
        M._keep_last_parts(state, learned, 1000.0)
        M._save_state(path, state)
        assert learned["last_learned"]["parts"] == {"selectionfit.refresh": 9.1}
        assert learned["last_learned"]["learn"] == 12.3
        assert learned["last_exported"]["two_leg"]["backtest"] == "kept"
        # The next pass, in its own process, does neither: both come back from the file.
        quiet: dict = {"learned": False, "learn": 0.0, "export": 0.0}
        again = M._load_state(path)
        M._keep_last_parts(again, quiet, 2000.0)
        assert quiet["last_learned"] == learned["last_learned"], quiet
        assert quiet["last_exported"] == learned["last_exported"], quiet
        assert quiet["last_learned"]["at"] < M._dt.datetime.fromtimestamp(2000.0).isoformat(timespec="seconds")
        # A later learning replaces it; an export without a two-leg half carries none.
        later = {"learn": 3.0, "learn_parts": {"journalfit.refresh": 2.0}, "export_parts": {"performance": 1.0}}
        M._keep_last_parts(again, later, 3000.0)
        assert later["last_learned"]["parts"] == {"journalfit.refresh": 2.0}
        assert "two_leg" not in later["last_exported"]
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("def settle_open(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert body.count("_keep_last_parts(state, phases, now)\n") == 2, "both places a pass ends"
    assert body.count('_keep_last_parts(state, phases, now)\n            state["last_settle_ts"] = now') == 1
    assert body.count('_keep_last_parts(state, phases, now)\n    state["last_settle_ts"] = now') == 1


def _calibration_history():
    """A scratch history: four NFL teams through two seasons, every game
    with its score and a schedule close, and a harvested total for some."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE games (sport TEXT, season INT, period TEXT, home TEXT, away TEXT, "
                 "home_score INT, away_score INT, spread REAL, total REAL, extra TEXT, date TEXT)")
    conn.execute("CREATE TABLE odds_history (sport TEXT, market TEXT, book TEXT, taken_at TEXT, "
                 "home TEXT, away TEXT, player TEXT, line REAL, over_odds INT, under_odds INT)")
    teams = ("A", "B", "C", "D")
    rows, harvest = [], []
    for season in (2024, 2025):
        for wk in range(1, 18):
            for i in range(0, 4, 2):
                home, away = teams[(wk + i) % 4], teams[(wk + i + 1) % 4]
                hs, as_ = 17 + (wk * 3 + i) % 15, 14 + (wk * 5 + i) % 13
                date = f"{season}-09-{wk:02d}" if wk < 30 else None
                rows.append((season, f"{wk:03d}", home, away, hs, as_, -2.5 - i, 43.5 + wk % 5,
                             '{"ml": [-140, 120], "spread_odds": [-110, -110], "total_odds": [-110, -110]}',
                             date))
                if wk % 3 == 0:
                    harvest.append(("nfl", "total", "best", f"{date}T18:00:00Z", home, away, "",
                                    44.0 + wk % 4, -110, -110))
    conn.executemany("INSERT INTO games (sport, season, period, home, away, home_score, away_score, "
                     "spread, total, extra, date) VALUES ('nfl',?,?,?,?,?,?,?,?,?,?)", rows)
    conn.executemany("INSERT INTO odds_history VALUES (?,?,?,?,?,?,?,?,?,?)", harvest)
    conn.commit()
    return conn


class _ScratchCalibration:
    """engine.gamecal pointed at a throwaway state file (the box's own
    data/feedstate/gamecal.json is never read or written here)."""

    def __enter__(self):
        from engine import gamecal as G
        self.G, self.tmp = G, tempfile.TemporaryDirectory()
        self.saved = G.STATE_PATH, dict(G._cache)
        G.STATE_PATH = str(Path(self.tmp.name) / "gamecal.json")
        G._cache.clear()
        return G

    def __exit__(self, *exc):
        self.G.STATE_PATH = self.saved[0]
        self.G._cache.clear()
        self.G._cache.update(self.saved[1])
        self.G.LAST.clear()
        self.tmp.cleanup()


def test_the_game_line_calibration_names_each_fit_and_each_read():
    with _ScratchCalibration() as G:
        conn = _calibration_history()
        out = G.refresh(conn, sport="nfl")
        last = dict(G.LAST)
        assert set(last["fits"]) == {"nfl:total", "nfl:spread", "nfl:moneyline"}, last
        assert {"sports", "schedule closes", "harvested closes", "games", "walk"} <= set(last["parts"]), last
        assert last["seconds"] >= max(last["fits"].values()) >= 0, last
        assert list(last["fits"].values()) == sorted(last["fits"].values(), reverse=True)
        # Timing only: what it adopts and holds is what each fit says on its own.
        fits = {m: G.fit_one(conn, "nfl", m) for m in ("total", "spread", "moneyline")}
        held = {h["key"]: h["why"] for h in out["held"]}
        for m, f in fits.items():
            key = f"nfl:{m}"
            assert key in held or any(a["key"] == key for a in out["adopted"]), key
            if f.missing:
                assert held[key] == f.missing, (key, held, f.missing)
        # Each refresh's numbers are its own, never added to the last one's.
        G.refresh(conn, sport="nfl", markets=("total",))
        assert set(G.LAST["fits"]) == {"nfl:total"}, G.LAST


def test_the_settle_pass_puts_the_calibrations_parts_on_its_phases_and_keeps_them():
    from engine import maintenance as M
    with _ScratchCalibration() as G:
        conn = _calibration_history()
        phases: dict = {}
        M._learn_sampled(lambda: G.refresh(conn, sport="nfl"), phases)
        assert set(phases["learn_gamecal"]["fits"]) == {"nfl:total", "nfl:spread", "nfl:moneyline"}, phases
        # A pass whose learning never reached the calibration carries none,
        # never the pass before's.
        quiet: dict = {}
        M._learn_sampled(lambda: None, quiet)
        assert "learn_gamecal" not in quiet, quiet
        with tempfile.TemporaryDirectory() as td:
            state = M._load_state(Path(td) / "maintenance.json")
            # A scratch refresh is too quick for the sampler to see; the
            # box's 128.8 seconds are not.
            phases["learn_parts"] = phases.get("learn_parts") or {"gamecal.refresh": 1.0}
            M._keep_last_parts(state, phases, 1000.0)
            assert state["last_learned"]["gamecal"] == phases["learn_gamecal"], state
            later = {"learn": 2.0, "learn_parts": {"corrfit.refresh": 2.0}}
            M._keep_last_parts(state, later, 2000.0)
            assert "gamecal" not in state["last_learned"], "a later learning without it replaces it whole"


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
