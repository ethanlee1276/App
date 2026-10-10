"""Rung three: per-player memory that must out-predict forgetting.

The blend misreads specific players — the decliner it projects off last
month's bat, the improver it lags. Remembering them is dangerous exactly
in proportion to how satisfying it is, so everything pinned here is a
restraint: shrinkage toward "he's ordinary", a hard ±15% cap enforced at
read as well as fit, a store floor under which nobody is remembered, and
market-level adoption decided by a CAUSAL walk-forward test — each game's
correction computed strictly from earlier games, so the memory is scored
out-of-sample at every single row.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger                                     # noqa: E402
from engine import playerfit as pf                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the shrinkage -----------------------------------------------------------
def test_evidence_moves_the_correction_and_the_clamp_ends_it():
    # 30% raw bias: 10 games moves it a fifth of the way, 200 games most
    # of the way — straight into the cap.
    assert pf.shrunk_mult(13.0, 10.0, 10) == 1.0 + 0.3 * (10 / 50.0)
    assert pf.shrunk_mult(260.0, 200.0, 200) == 1.0 + pf.CLAMP_PCT
    assert pf.shrunk_mult(140.0, 200.0, 200) == 1.0 - pf.CLAMP_PCT


def test_no_or_degenerate_evidence_is_an_ordinary_player():
    assert pf.shrunk_mult(0.0, 0.0, 0) == 1.0
    assert pf.shrunk_mult(5.0, 0.0, 10) == 1.0


# --- the fit -----------------------------------------------------------------
def _player(name, vals):
    return {"name": name, "values": vals,
            "dates": [f"2026-05-{(d % 30) + 1:02d}" for d in range(len(vals))]}


def _biased_world(n_each=9, games=32):
    """Half the league declines, half improves — trajectories the window
    blend structurally lags in opposite directions. Deterministic."""
    out = []
    for i in range(n_each):
        out.append(_player(f"Fade{i}",
                           [round(4.5 - g * 0.12 + 0.3 * ((g + i) % 2), 1)
                            for g in range(games)]))
        out.append(_player(f"Rise{i}",
                           [round(0.5 + g * 0.12 + 0.3 * ((g + i) % 2), 1)
                            for g in range(games)]))
    return out


def test_a_world_of_misread_players_switches_the_memory_on():
    f = pf.fit(_biased_world(), "total_bases")
    assert f.adopted
    assert f.brier_corrected < f.brier_baseline - pf.MIN_GAIN
    assert f.players, "persistent misreads must be remembered"
    fades = {n: r for n, r in f.players.items() if n.startswith("fade")}
    rises = {n: r for n, r in f.players.items() if n.startswith("rise")}
    assert fades and all(r["mult"] < 1.0 for r in fades.values())
    assert rises and all(r["mult"] > 1.0 for r in rises.values())
    assert all(r["games"] >= pf.MIN_GAMES_STORE for r in f.players.values())
    assert "memory on" in f.verdict


def test_a_world_the_blend_already_reads_keeps_the_memory_off():
    """Constant players: nothing personal to learn. The corrected pass
    cannot beat the baseline by the margin, memory stays off, and nobody
    is stored — remembering ordinary players is how noise gets a name."""
    flat = [_player(f"C{i}", [2.0] * 22) for i in range(18)]
    f = pf.fit(flat, "total_bases")
    assert f.adopted is False
    assert f.players == {}
    assert "memory off" in f.verdict


def test_a_thin_sample_cannot_switch_the_memory_on():
    f = pf.fit(_biased_world(n_each=2, games=22), "total_bases")
    assert f.samples < pf.MIN_SAMPLES
    assert f.adopted is False


def test_the_fit_is_causal_raw_and_calibration_free():
    src = open(os.path.join(ROOT, "engine", "playerfit.py"),
               encoding="utf-8").read()
    fn = src[src.index("def fit("):src.index("\ndef save(")]
    assert "with cal.disabled():" in fn
    assert 'player_adjust=lambda name: 1.0' in fn      # baseline, store-free
    bt = open(os.path.join(ROOT, "engine", "mlb", "backtest.py"),
              encoding="utf-8").read()
    # The ledger accumulates the RAW blend's projection — divide the
    # correction back out — or the correction would learn to correct
    # itself and spiral.
    assert "proj.mean / (mult or 1.0)" in bt


# --- the store and the projection-time lookup --------------------------------
GOOD = {"sport": "mlb", "market": "hits", "samples": 4000,
        "brier_baseline": 0.25, "brier_corrected": 0.2455, "adopted": True,
        "players": {"aaron judge": {"mult": 1.09, "games": 112},
                    "jose altuve": {"mult": 0.93, "games": 98}}}


def _store_with(entry, path):
    json.dump({"mlb:hits": entry}, open(path, "w"))
    return path


def test_mult_for_serves_only_earned_memory():
    p = _store_with(GOOD, tempfile.mktemp(suffix=".json"))
    assert pf.mult_for("mlb", "hits", "Aaron  Judge", p) == 1.09   # normed
    assert pf.mult_for("mlb", "hits", "someone else", p) == 1.0
    assert pf.mult_for("mlb", "total_bases", "aaron judge", p) == 1.0
    for bad in (
        {**GOOD, "adopted": False},
        {**GOOD, "players": {"aaron judge": {"mult": 1.09, "games": 5}}},
        {**GOOD, "players": {"aaron judge": {"mult": 1.60, "games": 112}}},
        {**GOOD, "players": {"aaron judge": {"mult": "x", "games": 112}}},
    ):
        q = _store_with(bad, tempfile.mktemp(suffix=".json"))
        assert pf.mult_for("mlb", "hits", "aaron judge", q) == 1.0, bad


def test_default_path_is_read_at_call_time_not_frozen_at_import():
    keep = pf.DEFAULT_PATH
    try:
        pf.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        _store_with(GOOD, pf.DEFAULT_PATH)
        assert pf.mult_for("mlb", "hits", "aaron judge") == 1.09
    finally:
        pf.DEFAULT_PATH = keep


def test_the_projection_applies_the_memory_and_says_so():
    from engine.mlb.models import MLBProp, MLBGame, MLBGameLog, HITS
    from engine.mlb.projection import build_mlb_projection
    logs = [MLBGameLog(game=20 - j, opponent="", value=1.5) for j in range(20)]
    prop = MLBProp(player="Aaron Judge", team="HOME", opponent="AWAY",
                   position="", market=HITS, logs=logs, career_avg=1.5,
                   vs_pitcher_avg=None, lines=[], lineup_spot=3)
    game = MLBGame(home="HOME", away="AWAY", park="generic")
    keep = pf.DEFAULT_PATH
    try:
        pf.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        plain = build_mlb_projection(prop, game).mean
        _store_with(GOOD, pf.DEFAULT_PATH)
        proj = build_mlb_projection(prop, game)
        assert abs(proj.mean - plain * 1.09) < 1e-9
        assert any("Player memory" in r for r in proj.reasons)
        # The fitter's explicit value always beats the store.
        override = build_mlb_projection(prop, game, player_mult=1.0)
        assert override.mean == plain
        assert not any("Player memory" in r for r in override.reasons)
    finally:
        pf.DEFAULT_PATH = keep


# --- the CLI and the page ----------------------------------------------------
def test_the_cli_excludes_home_runs_and_orders_the_refits():
    src = open(os.path.join(ROOT, "playerfit.py"), encoding="utf-8").read()
    mlb_list = src.split('"mlb": [')[1].split("]")[0]
    assert '"home_runs"' not in mlb_list
    assert "calibrate.py" in src and "refit its temperature" in src


def test_the_memory_ships_with_the_self_tuning_story():
    from engine import calibrate as cal
    keep_pf, keep_cal = pf.DEFAULT_PATH, cal.DEFAULT_PATH
    try:
        pf.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        cal.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        json.dump({"mlb:hits": GOOD,
                   "mlb:strikeouts": {**GOOD, "market": "strikeouts",
                                      "adopted": False, "players": {}}},
                  open(pf.DEFAULT_PATH, "w"))
        st = ledger.self_tuning_report(None)
        by = {p["market"]: p for p in st["players"]}
        assert by["hits"]["adopted"] and by["hits"]["n_players"] == 2
        assert by["hits"]["top"][0]["player"] == "aaron judge"   # biggest miss
        assert by["strikeouts"]["reading"] == "memory off — didn't help"
    finally:
        pf.DEFAULT_PATH, cal.DEFAULT_PATH = keep_pf, keep_cal


def test_the_page_renders_player_memory_with_guards():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function recSelfTuningSection(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    for needle in ("Player memory", "st.players", "${playersBlock}",
                   '"memory off" is a result'):
        assert needle in fn, needle
    assert "(t.mult ?? 1).toFixed" in fn
    assert "(p.samples ?? 0).toLocaleString" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
