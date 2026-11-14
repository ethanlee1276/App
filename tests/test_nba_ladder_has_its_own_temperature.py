"""The NBA's alternate rungs carry their own temperature (2026-11-04).

The fitters' walk prices each game at ONE line, a half point under his
recent average — near the projection — and the temperature fitted there
was applied to every rung of the alternate ladder, where Most Likely
prices. On the lab's two seasons that near-line temperature came out above
one for most markets and tempered the ladder's confident claims below what
they landed. Pinned here:

  * the walk also prices every game, raw, at half-point rungs one and one
    and a half curve-widths either side of the projection (the board's own
    `sd_for`), oldest first, as ``ladder_pairs`` — when the temperature
    fit asks (``ladder=True``), so the other fits' walks cost what they did;
  * calibrate.py fits those under ``<market>@ladder`` beside the market's
    own key, stamped as the history fitter's, and stores none below its
    sample floor;
  * a rung is priced through the ladder key when one is stored and through
    its market's own correction when not (never the sport-wide fallback in
    its place), while the main line keeps the market's key;
  * the record page names the key in words.

Run directly: `python3 tests/test_nba_ladder_has_its_own_temperature.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

# The fitted models must not decide this file (see tests/test_nba.py).
from engine import calibrate as cal, losspatterns as _lp, playerfit as pf   # noqa: E402
_void = Path(tempfile.gettempdir()) / "qb-no-such-fit.json"
for _m in (cal, pf, _lp):
    _m.DEFAULT_PATH = _void
    _m._cache = {}

import calibrate as calibrate_cli                              # noqa: E402
from engine import db, hoops, hoopsreplay, logwalk             # noqa: E402
from engine.nba import pipeline, prob                          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _games(player, k=0, n=30):
    rows = []
    for i in range(n):
        day = f"2026-01-{i + 1:02d}"
        mins = float(22 + (i * 5 + k) % 15)
        g = {"min": mins, "pts": 8 + (i * 7 + k) % 19, "reb": 2 + (i * 3 + k) % 9,
             "ast": 1 + (i + 2 * k) % 7, "fg3m": (i + k) % 4}
        for market, v in g.items():
            rows.append({"sport": "nba", "season": 2025, "period": day, "game_id": f"{player}-{day}",
                         "player": player, "team": "BOS", "opponent": "NYK", "position": "S",
                         "home": i % 2, "market": market, "value": float(v)})
    return rows


def _league_file(players=6):
    path = Path(tempfile.mkdtemp()) / "history.db"
    conn = db.connect(str(path))
    for k in range(players):
        db.upsert_player_logs(conn, _games(f"Player {k}", k=k))
    conn.commit()
    conn.close()
    return path


class _Store:
    """A calibration store holding exactly ``entries`` for the block."""

    def __init__(self, entries):
        self.path = Path(tempfile.mkdtemp()) / "calibration.json"
        if entries is not None:
            self.path.write_text(json.dumps(entries))

    def __enter__(self):
        self.keep = cal.DEFAULT_PATH
        cal.DEFAULT_PATH = self.path
        cal.reset_cache()
        return self.path

    def __exit__(self, *exc):
        cal.DEFAULT_PATH = self.keep
        cal.reset_cache()
        return False


def test_the_rungs_are_a_curve_width_and_one_and_a_half_either_side():
    tune = hoops.NBA
    sd = prob.sd_for("pts", 20.0, tune)
    got = hoopsreplay.ladder_lines("pts", 20.0, tune)
    want = []
    for k in (-1.5, -1.0, 1.0, 1.5):
        v = 20.0 + k * sd
        ln = int(v) + 0.5 if v > 0.5 else 0.5
        if ln not in want:
            want.append(ln)
    assert got == want and len(got) == 4, (got, want)
    assert all(x % 1 == 0.5 for x in got), "half points: no push in a fit that never priced one"
    low = hoopsreplay.ladder_lines("blk", 0.4, tune)
    assert low == sorted(set(low)) and low[0] == 0.5, "a low count's rungs coincide and are kept once"


def test_the_walk_prices_the_ladder_too_raw_and_oldest_first():
    path = _league_file()
    conn = db.connect(str(path))
    entries = logwalk.load_entries(conn, "nba", "pts", min_games=6)
    with cal.disabled():
        raw = logwalk.walk("nba", entries, "pts", ladder=True)
        plain = logwalk.walk("nba", entries, "pts")
    assert plain.ladder_pairs == [] and plain.pairs == raw.pairs, \
        "only the temperature fit asks for the rungs: the other fits' walks are unchanged"
    games = len(raw.settled)
    assert games and games <= len(raw.ladder_pairs) <= 4 * games, (games, len(raw.ladder_pairs))
    assert all(0.0 <= p <= 1.0 and y in (0, 1) for p, y in raw.ladder_pairs)
    # Rebuilt game by game from what the walk settled, in the walk's order.
    want = []
    for s in raw.settled:
        for rung in hoopsreplay.ladder_lines("pts", s.projection, entries.aux["tune"]):
            want.append((prob.p_over("pts", s.projection, rung, entries.aux["tune"]),
                         1 if s.actual > rung else 0))
    assert raw.ladder_pairs == want
    assert {y for _p, y in raw.ladder_pairs} == {0, 1}
    # Raw whatever is stored: the fit must learn on the uncorrected number.
    with _Store({"nba:pts@ladder": {"temperature": 0.5, "intercept": 0.0},
                 "nba:pts": {"temperature": 2.0, "intercept": 0.0}}):
        stored = logwalk.walk("nba", entries, "pts", ladder=True)
    assert stored.ladder_pairs == raw.ladder_pairs
    # Only the walk carries them; the Lab's replay at real lines does not.
    assert hoopsreplay.evaluate([]).ladder_pairs == []


def _fit(path, floor):
    """What calibrate.py's main hands the store, as the store writes it."""
    got: dict = {}

    def save(fitted, *_a, **_k):
        got.update({k: c.to_dict() for k, c in fitted.items()})
        return "the store"

    argv, keep = sys.argv, calibrate_cli.cal.save
    sys.argv = ["calibrate.py", "--from-db", str(path), "--sport", "nba", "--market", "pts",
                "--min-samples", str(floor)]
    calibrate_cli.cal.save = save
    try:
        calibrate_cli.main()
    finally:
        sys.argv, calibrate_cli.cal.save = argv, keep
    return got


def test_the_fitter_stores_the_ladder_key_beside_the_market():
    path = _league_file()
    got = _fit(path, 50)
    assert "nba:pts" in got and "nba:pts@ladder" in got, sorted(got)
    lad = got["nba:pts@ladder"]
    assert lad["basis"] == cal.BASIS_HISTORY and lad["fitted_at"] == got["nba:pts"]["fitted_at"]
    assert lad["market"] == "pts@ladder" and lad["sport"] == "nba"
    conn = db.connect(str(path))
    entries = logwalk.load_entries(conn, "nba", "pts", min_games=10)
    with cal.disabled():
        rep = logwalk.walk("nba", entries, "pts", ladder=True)
    assert lad["samples"] == len(rep.ladder_pairs) > got["nba:pts"]["samples"]
    # Below its own floor no ladder key: the rungs keep the market's.
    few = _fit(path, len(rep.ladder_pairs) + 1)
    assert "nba:pts@ladder" not in few


def test_a_rung_takes_the_ladder_key_and_the_main_line_keeps_its_own():
    tune = hoops.NBA
    alts = [{"line": ln} for ln in (14.5, 17.5, 23.5, 26.5)]      # quoted nowhere: the model's number
    raw = {f"{a['line']:g}": prob.p_over("pts", 20.0, a["line"], tune) for a in alts}

    def rungs():
        return pipeline.rung_probs("pts", 20.0, alts, 0.5, tune)

    with _Store({"nba:pts": {"temperature": 2.0, "intercept": 0.0},
                 "nba:pts@ladder": {"temperature": 0.5, "intercept": 0.0}}):
        assert cal.ladder_key("nba", "pts") == "pts@ladder"
        got = rungs()
        main = cal.calibrated("nba", "pts", raw["23.5"])
        with cal.disabled():
            assert cal.ladder_key("nba", "pts") == "pts", "fitting sees the raw number"
    for key, p in raw.items():
        assert got[key] == round(cal.apply_temperature(p, 0.5), 4), (key, got[key], p)
    assert abs(main - cal.apply_temperature(raw["23.5"], 2.0)) < 1e-9, "the main line keeps its market's key"
    # No ladder key: the rung takes its market's own correction, as before.
    with _Store({"nba:pts": {"temperature": 2.0, "intercept": 0.0}}):
        assert cal.ladder_key("nba", "pts") == "pts"
        got = rungs()
    assert all(got[k] == round(cal.apply_temperature(p, 2.0), 4) for k, p in raw.items())
    # ...and with no market key either, the sport-wide fallback it always had —
    # a ladder key is looked up explicitly, never through that fallback.
    with _Store({"nba": {"temperature": 1.5, "intercept": 0.0},
                 "wnba:pts@ladder": {"temperature": 0.5, "intercept": 0.0}}):
        assert cal.ladder_key("nba", "pts") == "pts"
        got = rungs()
    assert all(got[k] == round(cal.apply_temperature(p, 1.5), 4) for k, p in raw.items())
    src = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    assert "calibrated(tune.key, rung_market, p_over(stat, proj, line, tune))" in src
    assert "p_model_over = calibrated(tune.key, stat, p_over(stat, proj, line, tune))" in src


def test_the_record_page_names_the_key_in_words():
    js = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert 'replace(/@ladder$/, " · alternate lines")' in js


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
            print(f"  FAIL {name}: {exc}")
            traceback.print_exc()
    if fails:
        print(f"\n{fails} of {len(tests)} tests failed.")
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
