"""The four-rung learning ladder, extended to every sport.

MLB got the ladder first; these tests pin the extension: the generic
engine (NFL and any log-based sport that adopts it) threads ``sport``
through every store lookup, the hoops and college gates consult the same
three verdicts (temperature, boundary closure, loss-pattern veto), the
deep fitters walk any sport through one door (logwalk.walk), and the
journal fitter covers the sports that have no deep harness at all —
first fits only, because refitting on post-correction claims would
compound. Also pinned: the sixth appearance of the frozen-default trap
(correction_for/is_reliable bound DEFAULT_PATH at import), and the store
saves that used to replace the whole file one sport at a time.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate as cal                           # noqa: E402
from engine import formfit as ff                              # noqa: E402
from engine import journalfit as jf                           # noqa: E402
from engine import ledger                                     # noqa: E402
from engine import losspatterns as lp                         # noqa: E402
from engine import playerfit as pf                            # noqa: E402

# These tests price synthetic slates and assert on what comes out. The
# selection haircut reads a store fitted from the REAL journal at settle
# time, so on a live laptop a −0.35 shift empties the board and this file
# fails for a reason that has nothing to do with what it tests. Switched
# off here, deliberately and visibly — see engine/selectionfit.set_enabled.
from engine import selectionfit as _sf                          # noqa: E402
_sf.set_enabled(False)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOPS_PROP = {"player": "A Test", "market": "pts", "line": 18.5,
              "over_odds": -110, "under_odds": -110,
              "minutes": [30, 31, 29, 32, 30, 31, 30, 29, 31, 30, 32, 29],
              "values": [18, 20, 17, 21, 19, 18, 20, 17, 19, 21, 18, 20],
              "is_starter": True, "spread": -3.0, "book": "dk"}


def _player(name, vals):
    return {"name": name, "values": vals}


# --- the generic engine, de-hardcoded ----------------------------------------
def test_the_generic_gate_carries_every_rung_and_no_hardcoded_sport():
    src = open(os.path.join(ROOT, "engine", "betting.py"),
               encoding="utf-8").read()
    assert 'correction_for("nfl"' not in src     # the old silent leak
    assert "correction_for(sport, prop.market)" in src
    assert "is_reliable(sport, prop.market)" in src
    assert "lp_veto(sport, prop.market" in src
    i = src.index("gate_ok = ")
    seg = src[i:i + 260]
    assert "calibration_ok" in seg and "pattern_block is None" in seg


def test_the_generic_projection_consults_the_stores_by_sport():
    src = open(os.path.join(ROOT, "engine", "projection.py"),
               encoding="utf-8").read()
    assert "weights_for(sport, prop.market)" in src
    assert "mult_for(sport, prop.market, prop.player)" in src
    # The fitters' explicit values always beat the stores.
    assert "if form_weights is None:" in src
    assert "if player_mult is None:" in src


# --- the deep fitters, through one door --------------------------------------
def test_nfl_dial_fits_through_the_generic_harness():
    ramp = [_player(f"R{i}", [round(30 + g * 4 + 6 * ((g + i) % 3), 1)
                              for g in range(16)]) for i in range(20)]
    f = ff.fit(ramp, "rec_yds", sport="nfl")
    assert f.r > 0 and f.adopted
    assert f.brier_fitted < f.brier_default - ff.MIN_GAIN
    assert f.samples >= ff.MIN_SAMPLES


def test_nfl_memory_fits_through_the_generic_harness():
    world = []
    for i in range(10):
        world.append(_player(f"Fade{i}",
                             [round(90 - g * 3 + 5 * ((g + i) % 2), 1)
                              for g in range(24)]))
        world.append(_player(f"Rise{i}",
                             [round(30 + g * 3 + 5 * ((g + i) % 2), 1)
                              for g in range(24)]))
    p = pf.fit(world, "rec_yds", sport="nfl")
    assert p.adopted and p.players
    fades = {n: r for n, r in p.players.items() if n.startswith("fade")}
    rises = {n: r for n, r in p.players.items() if n.startswith("rise")}
    assert fades and all(r["mult"] < 1.0 for r in fades.values())
    assert rises and all(r["mult"] > 1.0 for r in rises.values())


def test_every_cli_takes_a_sport():
    for name in ("formfit.py", "playerfit.py", "calibrate.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert '"--sport"' in src, name
        assert "SPORT_MARKETS" in src, name


# --- the hoops gate (NBA and WNBA through tune.key) --------------------------
def test_the_hoops_gate_consults_all_three_verdicts():
    from engine.hoops import WNBA
    from engine.nba.pipeline import evaluate_prop as hoops_eval
    keep_lp, keep_cal = lp.DEFAULT_PATH, cal.DEFAULT_PATH
    try:
        lp.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        cal.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        cal.reset_cache()
        base = hoops_eval(dict(HOOPS_PROP), WNBA)
        assert base["kind"] in ("near_miss", "pick")

        # Rung 1: a closed slice vetoes, with the pattern spelled out.
        lp.save({"closed": [{"sport": "wnba", "market": "pts", "dim": "side",
                             "value": "OVER", "reading": "test closure"}]})
        vetoed = hoops_eval(dict(HOOPS_PROP), WNBA)
        assert any("blind spot" in f for f in vetoed.get("fails", []))
        # ...and it is keyed by league: the NBA is not the WNBA.
        from engine.hoops import NBA
        nba_r = hoops_eval(dict(HOOPS_PROP), NBA)
        assert not any("blind spot" in f for f in nba_r.get("fails", []))

        # Rung 4: a stored temperature moves the claim toward 50%...
        json.dump({"wnba:pts": {"temperature": 2.0, "intercept": 0.0}},
                  open(cal.DEFAULT_PATH, "w"))
        cal.reset_cache()
        tempered = hoops_eval(dict(HOOPS_PROP), WNBA)
        # Margin rather than a bare comparison (see test_sidebias.py).
        # Measured: 0.019 against 0.038 — tempering halves the distance
        # from the coin flip, so 10% is nowhere near the real effect.
        assert (abs(tempered["p_model"] - 0.5)
                < abs(base["p_model"] - 0.5) * 0.9)
        # ...and a boundary fit closes the market outright.
        json.dump({"wnba:pts": {"temperature": cal.GRID_MAX, "intercept": 0.0}},
                  open(cal.DEFAULT_PATH, "w"))
        cal.reset_cache()
        closed = hoops_eval(dict(HOOPS_PROP), WNBA)
        assert any("search range" in f for f in closed.get("fails", []))
    finally:
        lp.DEFAULT_PATH, cal.DEFAULT_PATH = keep_lp, keep_cal
        cal.reset_cache()


def test_the_hoops_projection_carries_player_memory():
    src = open(os.path.join(ROOT, "engine", "nba", "pipeline.py"),
               encoding="utf-8").read()
    assert 'pf_mult(tune.key, stat, prop["player"])' in src
    assert "rate * proj_min * pmult" in src


# --- the college gate --------------------------------------------------------
def test_the_cfb_gate_consults_all_three_verdicts():
    """UNDER THE NAME THE STORES USE, which is "spread", not "side".

    This test used to write its own fixtures at `cfb:side` and
    `market: "side"` — the name `evaluate_play` asked for — and passed.
    It could not have failed: it was checking the gate against a key only
    it and the gate believed in. Nothing that WRITES those stores spells
    it that way. `ledger.log_recommendations` journals a CFB spread bet
    as market "spread", so `journalfit` fits `cfb:spread` and
    `losspatterns` mines its closures keyed "spread", and both of those
    were invisible to the gate. See `pipeline.STORE_MARKET`.
    """
    from engine.cfb.pipeline import evaluate_play
    keep_lp, keep_cal = lp.DEFAULT_PATH, cal.DEFAULT_PATH
    play = {"market": "side", "odds": -160, "opposing_odds": 140,
            "p_model": 0.68, "selection": "HOME", "book": "dk",
            "game": {"home": "A", "away": "B"}}
    try:
        lp.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        cal.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        cal.reset_cache()
        lp.save({"closed": [{"sport": "cfb", "market": "spread", "dim": "odds",
                             "value": lp.odds_band(-160),
                             "reading": "test closure"}]})
        r = evaluate_play(dict(play))
        assert r["kind"] == "pass" and "blind spot" in r["why"]

        lp.save({"closed": []})
        json.dump({"cfb:spread": {"temperature": cal.GRID_MAX,
                                  "intercept": 0.0}},
                  open(cal.DEFAULT_PATH, "w"))
        cal.reset_cache()
        r2 = evaluate_play(dict(play))
        assert r2["kind"] == "pass" and "search range" in r2["why"]

        # …and the key nothing writes is not consulted any more, or the
        # gate is still reading a store of its own invention.
        lp.save({"closed": [{"sport": "cfb", "market": "side", "dim": "odds",
                             "value": lp.odds_band(-160),
                             "reading": "test closure"}]})
        json.dump({"cfb:side": {"temperature": cal.GRID_MAX,
                                "intercept": 0.0}},
                  open(cal.DEFAULT_PATH, "w"))
        cal.reset_cache()
        r3 = evaluate_play(dict(play))
        assert "blind spot" not in (r3.get("why") or "")
        assert "search range" not in (r3.get("why") or "")
    finally:
        lp.DEFAULT_PATH, cal.DEFAULT_PATH = keep_lp, keep_cal
        cal.reset_cache()


# --- the journal fitter ------------------------------------------------------
def _journal(rows):
    conn = ledger.connect(":memory:")
    for r in rows:
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " book, odds, hit_prob, projection, actual, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.commit()
    return conn


def _hot_wnba_rows(n=260):
    # (sport, date, player, market, category) is the journal's unique key,
    # so each of the ten players gets his own run of dates.
    return [("2026-07-%02dT10:00:00" % (i // 10 % 28 + 1), "wnba",
             "2026-07-%02d" % (i // 10 % 28 + 1), f"P{i % 10}", "pts", "OVER",
             14.5, "dk", -120, 0.65, 20.0, 26.0 if (i // 10) % 2 else 14.0,
             "won" if i % 2 == 0 else "lost", "main") for i in range(n)]


def test_journal_temperatures_fit_merge_and_never_compound():
    conn = _journal(_hot_wnba_rows())
    path = tempfile.mktemp(suffix=".json")
    json.dump({"mlb:hits": {"temperature": 1.1, "intercept": 0.0}},
              open(path, "w"))
    t = jf.fit_temperatures(conn, path=path)
    assert [x["key"] for x in t["fitted"]] == ["wnba:pts"]
    assert t["fitted"][0]["temperature"] > 1.5      # said 65%, hit 50%
    stored = json.load(open(path))
    assert stored["mlb:hits"]["temperature"] == 1.1  # merge, not replace
    first = t["fitted"][0]["temperature"]

    # Second run: the key exists now, so it REFITS rather than being skipped.
    # Every row here was logged before the correction was fitted, so every
    # row is already the model's own claim and nothing is un-corrected — the
    # refit therefore has to land on the same answer. That is the
    # non-compounding property, tested where it actually bites: a fitter
    # that double-counted would climb on the second pass.
    t2 = jf.fit_temperatures(conn, path=path)
    assert t2["fitted"] == [], t2["fitted"]
    assert [x["key"] for x in t2["refitted"]] == ["wnba:pts"]
    again = t2["refitted"][0]
    assert again["temperature"] == first, (again["temperature"], first)
    assert again["provenance"]["raw"] == again["n"], again["provenance"]

    # And a third pass does not drift either.
    t3 = jf.fit_temperatures(conn, path=path)
    assert t3["refitted"][0]["temperature"] == first


def test_journal_temperatures_respect_the_floor():
    conn = _journal(_hot_wnba_rows(150))
    path = tempfile.mktemp(suffix=".json")
    t = jf.fit_temperatures(conn, path=path)
    assert t["fitted"] == []
    assert t["collecting"] == [{"key": "wnba:pts", "n": 150, "need": 200}]
    assert not os.path.exists(path)                 # nothing earned a write


def test_journal_memory_adopts_only_a_real_per_player_bias():
    # Ten players, each with a PERSONAL bias the projection misses.
    biased = []
    for i in range(250):
        player = f"P{i % 10}"
        actual = 14.0 if (i % 10) < 5 else 26.0     # per-player, persistent
        biased.append(("2026-07-%02dT10:00:00" % (i // 10 % 28 + 1), "wnba",
                       "2026-07-%02d" % (i // 10 % 28 + 1), player, "pts",
                       "OVER", 14.5, "dk", -120, 0.6, 20.0, actual, "won",
                       "main"))
    m = jf.fit_memory(_journal(biased), path=tempfile.mktemp(suffix=".json"))
    f = m["fitted"][0]
    assert f["adopted"] and f["players"] > 0
    # The same volume with no per-player structure adopts nothing.
    m2 = jf.fit_memory(_journal(_hot_wnba_rows()),
                       path=tempfile.mktemp(suffix=".json"))
    assert m2["fitted"][0]["adopted"] is False


def test_journal_memory_never_touches_a_deep_fitted_key():
    path = tempfile.mktemp(suffix=".json")
    json.dump({"wnba:pts": {"sport": "wnba", "market": "pts",
                            "adopted": True, "samples": 5000,
                            "players": {}}}, open(path, "w"))
    m = jf.fit_memory(_journal(_hot_wnba_rows()), path=path)
    assert [x["key"] for x in m["owned"]] == ["wnba:pts"]
    assert m["fitted"] == []


def test_the_settle_pass_runs_the_journal_fitter():
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"),
                 encoding="utf-8").read()
    assert "journalfit" in maint[maint.index("def settle_open("):]
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "journalfit.refresh(lconn)" in launch


# --- shared-store hygiene ----------------------------------------------------
def test_every_store_save_merges_across_sports():
    p = tempfile.mktemp(suffix=".json")
    c = cal.fit([(0.6, 1)] * 300, sport="wnba", market="pts",
                min_samples=200)
    cal.save({"wnba:pts": c}, p)
    cal.save({"mlb:hits": c}, p)
    assert set(json.load(open(p))) == {"wnba:pts", "mlb:hits"}


def test_repointed_calibration_store_is_seen_at_call_time():
    """correction_for/is_reliable bound DEFAULT_PATH at import — the
    sixth appearance of the frozen-default trap. Behavioral pin."""
    keep = cal.DEFAULT_PATH
    try:
        cal.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        json.dump({"wnba:pts": {"temperature": 1.5, "intercept": 0.0}},
                  open(cal.DEFAULT_PATH, "w"))
        cal.reset_cache()
        assert cal.correction_for("wnba", "pts") == (1.5, 0.0)
    finally:
        cal.DEFAULT_PATH = keep
        cal.reset_cache()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
