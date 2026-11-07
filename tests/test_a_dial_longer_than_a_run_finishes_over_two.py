"""A recency-dial market longer than a run finishes over two.

The box's deep refit gives a fitter 45 minutes. The NFL's three big dial
markets (receiving yards, receptions, rushing yards; about 26,000 settled
predictions each) are 21 walk-forwards apiece, and one of them alone
outgrew a run: on 6 November the dial was cut off having kept nothing, and
those markets still carried their 25 August fit. What these hold:

  * each setting's score is kept as its walk ends, and a run that was cut
    off resumes at the next setting, fitting exactly the dial an
    uninterrupted run fits;
  * a saved grid is used only when the spec curve (r = 0) scores exactly as
    it did when it was saved, so a grid is never two different walks (new
    games, or a store the walk reads refitted in between);
  * the refit counts settings kept, not only whole markets, so a run that
    scored settings without finishing a market has moved, and one that had
    to start a market afresh with fewer has not;
  * only the deep refit's round (``--resume-after``) keeps a grid; a fit
    run by hand is the one long fit it always was.

Run directly: `python3 tests/test_a_dial_longer_than_a_run_finishes_over_two.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import deepfit as D                                       # noqa: E402
from engine import formfit as ff                                      # noqa: E402
from engine import logwalk                                            # noqa: E402
from engine.form import MLB_WINDOW_WEIGHTS                            # noqa: E402

BASE = MLB_WINDOW_WEIGHTS


def _player(name, vals):
    return {"name": name, "values": vals,
            "dates": [f"2026-06-{d + 1:02d}" for d in range(len(vals))]}


def _entries(n_players=12, games=22):
    """Players whose tonight tracks their recent games: a dial with a real
    answer, deterministic."""
    return [_player(f"Ramp{i}", [round(0.5 + g * 0.15 + 0.4 * ((g + i) % 3), 1) for g in range(games)])
            for i in range(n_players)]


class _Cut(Exception):
    """The run's time ran out (the refit kills the fitter's process)."""


def _counting(stop_after=None):
    """`logwalk.walk`, counting its calls and cut off after ``stop_after``."""
    real = logwalk.walk
    calls = []

    def walk(*a, **k):
        if stop_after is not None and len(calls) >= stop_after:
            raise _Cut()
        calls.append(k.get("form_weights"))
        return real(*a, **k)
    return walk, calls


def _fit(entries, ck, stop_after=None):
    walk, calls = _counting(stop_after)
    real = logwalk.walk
    logwalk.walk = walk
    try:
        try:
            got = ff.fit(entries, "hits", BASE, checkpoint=ck)
        except _Cut:
            got = None
    finally:
        logwalk.walk = real
    return got, calls


def _same(a, b):
    assert (a.r, a.samples, a.adopted) == (b.r, b.samples, b.adopted), (a, b)
    assert abs(a.brier_default - b.brier_default) < 1e-15 and abs(a.brier_fitted - b.brier_fitted) < 1e-15
    assert a.curve == b.curve


def test_a_cut_off_grid_resumes_at_the_next_setting_and_fits_the_same_dial():
    entries = _entries()
    whole = ff.fit(entries, "hits", BASE)
    ck = ff.GridCheckpoint("mlb", "hits", path=Path(tempfile.mkdtemp()) / "partial.json")
    got, calls = _fit(entries, ck, stop_after=8)
    assert got is None and len(calls) == 8, "cut off after eight walks"
    kept = ck.load()
    assert len(kept) == 8 and 0.0 in kept, "each setting kept as its walk ended, the spec curve first"
    assert calls[0] == ff.family(BASE, 0.0)
    got, calls = _fit(entries, ck)
    assert len(calls) == 1 + (len(ff.GRID) - 8), "the spec curve again, then only the settings owed"
    _same(got, whole)


def test_a_grid_scored_on_another_walk_is_scored_afresh():
    entries = _entries()
    ck = ff.GridCheckpoint("mlb", "hits", path=Path(tempfile.mkdtemp()) / "partial.json")
    _fit(entries, ck, stop_after=10)
    assert len(ck.load()) == 10
    # A night's games came in between: the spec curve no longer scores as
    # it did, so none of the ten is used.
    more = [dict(p, values=p["values"] + [p["values"][-1] + 0.3],
                 dates=p["dates"] + ["2026-06-30"]) for p in entries]
    got, calls = _fit(more, ck)
    assert len(calls) == len(ff.GRID), "the whole grid, scored on the new games"
    _same(got, ff.fit(more, "hits", BASE))
    # The same when a saved score does not match (a store refitted between).
    ck2 = ff.GridCheckpoint("mlb", "hits", path=Path(tempfile.mkdtemp()) / "partial.json")
    _fit(entries, ck2, stop_after=5)
    raw = json.loads(ck2.path.read_text(encoding="utf-8"))
    raw["mlb:hits"]["scores"]["0.0"][0] += 1e-9
    ck2.path.write_text(json.dumps(raw), encoding="utf-8")
    got, calls = _fit(entries, ck2)
    assert len(calls) == len(ff.GRID)
    _same(got, ff.fit(entries, "hits", BASE))


def test_the_checkpoint_keeps_markets_apart_and_survives_a_bad_file():
    path = Path(tempfile.mkdtemp()) / "partial.json"
    a, b = ff.GridCheckpoint("nfl", "rec_yds", path=path), ff.GridCheckpoint("nfl", "receptions", path=path)
    a.put(0.0, 0.2411, 26000)
    a.put(-0.3, 0.2409, 26000)
    b.put(0.0, 0.2370, 25000)
    assert a.load() == {0.0: (0.2411, 26000), -0.3: (0.2409, 26000)} and len(b.load()) == 1
    assert ff.partial_counts("nfl", path) == {"rec_yds": 2, "receptions": 1}
    assert ff.partial_counts("cfb", path) == {}
    a.clear()
    assert a.load() == {} and len(b.load()) == 1, "clearing one market leaves the other"
    path.write_text("{not json", encoding="utf-8")
    assert b.load() == {} and ff.partial_counts("nfl", path) == {}, "a torn file is nothing kept, never an error"


def test_the_refit_counts_settings_kept_not_only_markets():
    models = Path(os.environ["QB_MODELS_DIR"])
    saved = ff.DEFAULT_PATH, ff.PARTIAL_PATH
    ff.DEFAULT_PATH, ff.PARTIAL_PATH = models / "formfit_t.json", models / "formfit_partial_t.json"
    try:
        for p in (ff.DEFAULT_PATH, ff.PARTIAL_PATH):
            p.unlink(missing_ok=True)
        assert D._dial_kept("nfl", "2026-11-04") == 0
        ff.DEFAULT_PATH.write_text(json.dumps({
            "nfl:pass_yds": {"fitted": "2026-11-06T00:59:44", "r": -0.2},
            "nfl:rec_yds": {"fitted": "2026-08-25T14:49:55", "r": 1.0}}), encoding="utf-8")
        assert D._dial_kept("nfl", "2026-11-04") == len(ff.GRID), "one market fitted this round: its whole grid"
        ck = ff.GridCheckpoint("nfl", "rec_yds")
        for r in ff.GRID[:9]:
            ck.put(r, 0.24, 26000)
        assert D._dial_kept("nfl", "2026-11-04") == len(ff.GRID) + 9, "and nine settings of the next"
        assert D._dial_kept("cfb", "2026-11-04") == 0
    finally:
        for p in (ff.DEFAULT_PATH, ff.PARTIAL_PATH):
            p.unlink(missing_ok=True)
        ff.DEFAULT_PATH, ff.PARTIAL_PATH = saved


def test_a_cut_off_dial_leaves_how_far_it_got_in_the_refit_log():
    import subprocess
    import time as _t
    out = (b"Fitting the nfl recency dial from data/history.db\n"
           b"  Receiving yards  setting +0.0 scored \xe2\x80\x94 1 of 21 kept, 02:19:03\n"
           b"  Receiving yards  setting -1.0 scored \xe2\x80\x94 2 of 21 kept, 02:21:40\n")
    now = [10_000.0]

    def fake_run(cmd, **kw):
        if Path(cmd[1]).name == "formfit.py":
            now[0] += kw["timeout"]
            raise subprocess.TimeoutExpired(cmd, kw["timeout"], output=out)
        now[0] += 60
        return subprocess.CompletedProcess(cmd, 0, "", "")
    counts = iter([0, 2])
    keep = subprocess.run, _t.monotonic, D._dial_kept
    subprocess.run, _t.monotonic = fake_run, (lambda: now[0])
    D._dial_kept = lambda sport, round_of, path=None: next(counts)
    try:
        lines, _finished = D._refit_sport("nfl", deadline=now[0] + 2 * D.TIMEOUT_S, round_of="2026-11-04",
                                          on_done=lambda *a: None)
    finally:
        subprocess.run, _t.monotonic, D._dial_kept = keep
    said = [ln for ln in lines if "scored before the cut" in ln]
    assert said and "2 setting(s)" in said[0] and "2 of 21 kept, 02:21:40" in said[0], lines
    assert not any("stalled" in ln for ln in lines), "two settings kept is a move"


def test_only_the_round_keeps_a_grid():
    src = (ROOT / "formfit.py").read_text(encoding="utf-8")
    assert "ck = _ShownGrid(sport, market, label) if args.resume_after else None" in src
    assert "class _ShownGrid(ff.GridCheckpoint):" in src and "flush=True" in src
    assert "checkpoint=ck" in src
    i = src.index("path = ff.save({f\"{sport}:{market}\": f}, ff.DEFAULT_PATH)")
    assert "ck.clear()" in src[i:i + 200], "a fitted market's grid is let go once it is saved"
    deep = (ROOT / "engine" / "deepfit.py").read_text(encoding="utf-8")
    assert "kept_after <= kept_before" in deep, "fewer settings than before (a grid started afresh) is no move"


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
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} of {len(tests)} failed.")
    sys.exit(1 if fails else 0)
