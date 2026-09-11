"""Rung two of the self-tuning loop: the model's own recipe learns.

The temperature refit corrects confidence after a projection exists; the
recency dial refits the blend the projection is BUILT from. What these
tests pin is the discipline that makes that safe: one dial (not seven
free weights), a walk-forward score on raw probabilities, adoption only
past a margin and a sample floor, the spec curve as the undefeated
default, and a fitter that can never read the store it is refitting.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import formfit as ff                              # noqa: E402
from engine import ledger                                     # noqa: E402
from engine.form import MLB_WINDOW_WEIGHTS                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = MLB_WINDOW_WEIGHTS


def _rounded(d):
    return {k: round(v, 6) for k, v in d.items()}


# --- the family --------------------------------------------------------------
def test_dial_zero_is_exactly_the_spec_curve():
    assert ff.family(BASE, 0.0) == _rounded(BASE)


def test_the_dial_ends_at_the_anchors_and_every_stop_is_a_real_blend():
    assert ff.family(BASE, 1.0) == _rounded(ff.ANCHOR_HOT)
    assert ff.family(BASE, -1.0) == _rounded(ff.ANCHOR_STEADY)
    for r in ff.GRID:
        total = sum(ff.family(BASE, r).values())
        assert 0.999 < total < 1.001, r
    # Beyond the family there is nothing — clamped, not extrapolated.
    assert ff.family(BASE, 5.0) == ff.family(BASE, 1.0)


# --- the fit -----------------------------------------------------------------
def _player(name, vals):
    return {"name": name, "values": vals,
            "dates": [f"2026-06-{d+1:02d}" for d in range(len(vals))]}


def _ramp_entries(n_players=18):
    """Players whose tonight tracks their recent games, not their season —
    a world where recent form is genuinely worth more. Deterministic."""
    out = []
    for i in range(n_players):
        vals = [round(0.5 + g * 0.15 + 0.4 * ((g + i) % 3), 1)
                for g in range(22)]
        out.append(_player(f"Ramp{i}", vals))
    return out


def test_when_recent_form_truly_predicts_the_dial_moves_toward_it():
    f = ff.fit(_ramp_entries(), "hits", BASE)
    assert f.r > 0 and f.adopted
    assert f.brier_fitted < f.brier_default - ff.MIN_GAIN
    assert f.samples >= ff.MIN_SAMPLES
    assert "recent form" in f.verdict


def test_identical_curves_tie_and_the_tie_goes_to_the_spec():
    """Constant game logs make every candidate curve produce the same
    projection — 21 equal Briers. The argmin must land on 0, and a dial
    that didn't move must not be adopted."""
    entries = [_player(f"C{i}", [2.0] * 22) for i in range(18)]
    f = ff.fit(entries, "hits", BASE)
    assert f.r == 0.0 and f.adopted is False
    assert f.brier_fitted == f.brier_default
    assert "default kept" in f.verdict


def test_a_real_gain_on_a_thin_sample_is_not_adopted():
    """Three players of ramp data show the same Brier improvement — and
    stay unadopted, because 42 walk-forward samples is a story, not
    evidence. The floor is the same one the temperature fit uses."""
    f = ff.fit(_ramp_entries(3), "hits", BASE)
    assert f.samples < ff.MIN_SAMPLES
    assert f.adopted is False


def test_the_fit_scores_raw_probabilities_with_calibration_disabled():
    src = open(os.path.join(ROOT, "engine", "formfit.py"),
               encoding="utf-8").read()
    fn = src[src.index("def fit("):src.index("\ndef save(")]
    assert "with cal.disabled():" in fn
    # And every candidate is passed explicitly — the fitter never reads
    # the store it is refitting, so runs cannot compound.
    assert "form_weights=family(base, r)" in fn


# --- the store and the projection-time lookup --------------------------------
def _store_with(entry, path):
    json.dump({"mlb:hits": entry}, open(path, "w"))
    return path


GOOD = {"sport": "mlb", "market": "hits", "r": 0.8, "samples": 5000,
        "brier_default": 0.25, "brier_fitted": 0.245, "adopted": True,
        "weights": ff.family(MLB_WINDOW_WEIGHTS, 0.8)}


def test_weights_for_serves_only_earned_curves():
    p = tempfile.mktemp(suffix=".json")
    assert ff.weights_for("mlb", "hits",
                          _store_with(GOOD, p)) == GOOD["weights"]
    assert ff.weights_for("mlb", "total_bases", p) is None
    for bad in (
        {**GOOD, "adopted": False},                    # examined, kept default
        {**GOOD, "samples": 50},                       # under the floor
        {**GOOD, "weights": {}},                       # nothing to apply
        {**GOOD, "weights": {"last1": 9.0}},           # not a blend
    ):
        q = tempfile.mktemp(suffix=".json")
        assert ff.weights_for("mlb", "hits", _store_with(bad, q)) is None, bad


def test_default_path_is_read_at_call_time_not_frozen_at_import():
    keep = ff.DEFAULT_PATH
    try:
        ff.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        _store_with(GOOD, ff.DEFAULT_PATH)
        assert ff.weights_for("mlb", "hits") == GOOD["weights"]
    finally:
        ff.DEFAULT_PATH = keep


def test_the_projection_applies_an_adopted_curve_and_an_override_beats_it():
    """A hitter whose recent games run far above his early season projects
    higher under an adopted recent-leaning curve than under the spec —
    the learned recipe reaches the live number. An explicit form_weights
    (the fitter trying candidates) wins over the store."""
    from engine.mlb.models import MLBProp, MLBGame, MLBGameLog, HITS
    from engine.mlb.projection import build_mlb_projection
    logs = [MLBGameLog(game=20 - j, opponent="", value=(3.0 if j < 5 else 0.5))
            for j in range(20)]      # most-recent-first: hot 5, cold 15
    prop = MLBProp(player="X", team="HOME", opponent="AWAY", position="",
                   market=HITS, logs=logs, career_avg=1.0,
                   vs_pitcher_avg=None, lines=[], lineup_spot=3)
    game = MLBGame(home="HOME", away="AWAY", park="generic")
    keep = ff.DEFAULT_PATH
    try:
        ff.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        spec_mean = build_mlb_projection(prop, game).mean
        _store_with(GOOD, ff.DEFAULT_PATH)
        adopted_mean = build_mlb_projection(prop, game).mean
        assert adopted_mean > spec_mean
        override = build_mlb_projection(
            prop, game, form_weights=MLB_WINDOW_WEIGHTS).mean
        assert override == spec_mean
    finally:
        ff.DEFAULT_PATH = keep


# --- the CLI and the page ----------------------------------------------------
def test_the_cli_excludes_home_runs_and_orders_the_refits():
    src = open(os.path.join(ROOT, "formfit.py"), encoding="utf-8").read()
    mlb_list = src.split('"mlb": [')[1].split("]")[0]
    assert '"home_runs"' not in mlb_list
    # Adopting weights changes the model; the temperature must be refit
    # on the model that will actually run.
    assert "calibrate.py" in src and "refit its temperature" in src


def test_the_dial_ships_with_the_self_tuning_story():
    from engine import calibrate as cal
    keep_ff, keep_cal = ff.DEFAULT_PATH, cal.DEFAULT_PATH
    try:
        ff.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        cal.DEFAULT_PATH = tempfile.mktemp(suffix=".json")
        json.dump({"mlb:hits": GOOD,
                   "mlb:total_bases": {**GOOD, "market": "total_bases",
                                       "r": 0.0, "adopted": False}},
                  open(ff.DEFAULT_PATH, "w"))
        st = ledger.self_tuning_report(None)
        by = {w["market"]: w for w in st["weights"]}
        assert by["hits"]["adopted"] and by["hits"]["r"] == 0.8
        assert by["hits"]["reading"] == "leans on recent form"
        assert by["total_bases"]["reading"] == "default kept"
    finally:
        ff.DEFAULT_PATH, cal.DEFAULT_PATH = keep_ff, keep_cal


def test_the_dial_grid_cannot_be_widened_past_its_anchor():
    """±1.0 is the end of the FAMILY, not the end of a search range.

    A dial resting at the edge looks like a search that ran out of room,
    and the reflex is to widen the grid. It cannot be widened: r=+1.0 IS
    ANCHOR_HOT, so anything beyond it is an affine combination with a
    negative coefficient on the spec curve, and the very first step out
    puts a negative weight on vs_opp — "subtract this player's record
    against this opponent from his projection", which is not a stronger
    lean on recent form. This pins the wall so nobody widens it later.
    """
    def unclamped(r):
        t = abs(r)
        return {k: (1 - t) * BASE.get(k, 0.0) + t * ff.ANCHOR_HOT.get(k, 0.0)
                for k in set(BASE) | set(ff.ANCHOR_HOT)}

    assert all(v >= 0 for v in unclamped(1.0).values())
    bad = {k: v for k, v in unclamped(1.1).items() if v < 0}
    assert bad, "extrapolation past the anchor no longer breaks — recheck the wall"
    assert "vs_opp" in bad
    # The sum still comes to 1, which is exactly the trap: a curve can look
    # like a valid blend and still be subtracting a window.
    assert abs(sum(unclamped(1.1).values()) - 1.0) < 1e-9


def test_the_fit_keeps_the_whole_curve_not_just_its_winner():
    """The argmin alone cannot say whether the dial meant it.

    A 21-point search always returns a winner; on a flat surface that
    winner is wherever noise dipped, and edges are as likely as anywhere.
    The fit already evaluates every grid point, so keeping them is free —
    and it is the difference between a readable verdict and a mystery.
    """
    fit = ff.fit(_ramp_entries(), "hits", BASE)
    assert fit is not None
    assert len(fit.curve) == len(ff.GRID)
    assert set(fit.curve) == set(ff.GRID)
    # The winner in the curve must BE the reported winner.
    assert min(fit.curve, key=lambda r: (fit.curve[r], abs(r))) == fit.r
    assert abs(fit.curve[fit.r] - fit.brier_fitted) < 1e-12
    assert abs(fit.curve[0.0] - fit.brier_default) < 1e-12
    # …and it survives the round trip through the store.
    assert fit.to_dict()["curve"]["1.0"] == round(fit.curve[1.0], 6)


def test_a_flat_surface_reports_how_many_settings_tied():
    """plateau is the counterweight to the argmin."""
    flat = ff.FormFit(sport="mlb", market="hits", r=1.0, samples=5000,
                      brier_default=0.2000, brier_fitted=0.19999,
                      adopted=False, weights=dict(BASE),
                      curve={r: 0.2 for r in ff.GRID})
    assert flat.plateau == len(ff.GRID)
    assert "flat search landed" in flat.verdict
    # A real slope: only the winner is inside the margin.
    sloped = ff.FormFit(sport="mlb", market="hits", r=1.0, samples=5000,
                        brier_default=0.2000, brier_fitted=0.1900,
                        adopted=True, weights=dict(BASE),
                        curve={r: 0.20 - 0.01 * (r == 1.0) for r in ff.GRID})
    assert sloped.plateau == 1
    # An adopted boundary keeps the upstream warning; it is a real signal.
    assert "AT THE GRID EDGE" in sloped.verdict
    # An old store with no curve must not fake a verdict.
    bare = ff.FormFit(sport="mlb", market="hits", r=1.0, samples=5000,
                      brier_default=0.2, brier_fitted=0.2, adopted=False,
                      weights=dict(BASE))
    assert bare.plateau == 0
    assert "flat search landed" not in bare.verdict


def test_an_unadopted_dial_shows_the_margin_that_rejected_it():
    """Same defect as the player-memory rows: the verdict was shown and
    the evidence behind it was gated on adoption, so the only row anyone
    questions — "default kept" — was the one with no number on it."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("const weightRows")
    body = app[i:app.index("const weightsBlock")]
    assert "w.adopted &&" not in body, "the Brier pair is gated again"
    assert "w.brier_default != null" in body
    # A boundary that was never applied must not be painted as a fault.
    assert "dialTone" in body and "dialNote" in body


def test_the_page_renders_the_recipe_rows_with_guards():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function recSelfTuningSection(")
    fn = app[i:app.find("\nfunction ", i + 1)]
    for needle in ("The recipe itself, refit", "st.weights",
                   "${weightsBlock}"):
        assert needle in fn, needle
    # Method calls on possibly-absent fields blank the page — guarded.
    assert "(w.r ?? 0).toFixed" in fn
    assert "(w.samples ?? 0).toLocaleString" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
