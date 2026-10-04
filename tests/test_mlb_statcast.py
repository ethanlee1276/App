"""Tests for the MLB Statcast layer (evaluation + Savant CSV parser)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.statcast import evaluate_statcast
from engine.mlb.sources.savant import parse_expected_stats, _norm
from engine.mlb.models import (
    StatcastProfile, MLBProp, MLBGame, MLBGameLog,
    TOTAL_BASES, HOME_RUNS, STRIKEOUTS,
)


def test_positive_regression_boosts():
    eff = evaluate_statcast(StatcastProfile(xslg=0.560, slg=0.500), TOTAL_BASES)
    assert eff.multiplier > 1.0
    assert any("positive regression" in r for r in eff.reasons)


def test_negative_regression_fades():
    eff = evaluate_statcast(StatcastProfile(xslg=0.400, slg=0.480), TOTAL_BASES)
    assert eff.multiplier < 1.0
    assert any("regression risk" in r for r in eff.reasons)


def test_barrel_helps_hr_more_than_tb():
    hr = evaluate_statcast(StatcastProfile(barrel_pct=0.16), HOME_RUNS).multiplier
    tb = evaluate_statcast(StatcastProfile(barrel_pct=0.16), TOTAL_BASES).multiplier
    assert hr > tb > 1.0


def test_pitcher_csw():
    hi = evaluate_statcast(StatcastProfile(csw_pct=0.33), STRIKEOUTS)
    lo = evaluate_statcast(StatcastProfile(csw_pct=0.24), STRIKEOUTS)
    assert hi.multiplier > 1.0 and lo.multiplier < 1.0
    assert any("CSW" in r for r in hi.reasons)


def test_multiplier_is_clamped():
    eff = evaluate_statcast(
        StatcastProfile(xslg=0.9, slg=0.2, barrel_pct=0.30, hard_hit_pct=0.7),
        TOTAL_BASES)
    assert eff.multiplier <= 1.12


def test_empty_profile_neutral():
    assert evaluate_statcast(StatcastProfile(), TOTAL_BASES).multiplier == 1.0


# --- Savant CSV parser ------------------------------------------------------
def test_parse_expected_stats():
    rows = [
        {"last_name": "Harper", "first_name": "Bryce",
         "slg": "0.505", "est_slg": "0.560", "woba": "0.375", "est_woba": "0.400"},
    ]
    board = parse_expected_stats(rows)
    prof = board[_norm("Bryce Harper")]
    assert prof.xslg == 0.560 and prof.slg == 0.505
    assert prof.xwoba == 0.400 and prof.woba == 0.375


def test_parse_combined_name_column():
    rows = [{"last_name": "Judge, Aaron", "first_name": "",
             "slg": "0.610", "est_slg": "0.640"}]
    board = parse_expected_stats(rows)
    assert _norm("Aaron Judge") in board
    assert board[_norm("Aaron Judge")].xslg == 0.640


# --- projection integration -------------------------------------------------
def test_projection_uses_statcast():
    logs = [MLBGameLog(i, "X", 2) for i in range(1, 11)]
    game = MLBGame(home="HOME", away="AWAY", park="generic")

    def prop(sc):
        return MLBProp("H", "AWAY", "HOME", "1B", TOTAL_BASES, logs, 1.8, None,
                       [], bats="R", lineup_spot=3, statcast=sc)

    from engine.mlb.projection import build_mlb_projection
    base = build_mlb_projection(prop(None), game)
    hot = build_mlb_projection(
        prop(StatcastProfile(xslg=0.560, slg=0.490, barrel_pct=0.15)), game)
    assert hot.mean > base.mean
    assert any("regression" in r for r in hot.reasons)


def test_parse_barrels_scales_percents_and_folds_accents():
    """brl_percent/ev95percent arrive as 7.5-style percents; the HR model's
    thresholds expect 0..1 fractions. And Savant prints accents (Acuña) that
    other feeds drop — the join must fold them."""
    from engine.mlb.sources.savant import parse_barrels, _norm
    rows = [
        {"last_name": "Acuña Jr., Ronald", "brl_percent": "15.2",
         "ev95percent": "52.1"},
        {"first_name": "Soft", "last_name": "Contact", "brl_percent": "3.1",
         "ev95percent": "31.0"},
    ]
    out = parse_barrels(rows)
    acuna = out[_norm("Ronald Acuna Jr")]
    assert abs(acuna["barrel_pct"] - 0.152) < 1e-9
    assert abs(acuna["hard_hit_pct"] - 0.521) < 1e-9
    assert out[_norm("Soft Contact")]["barrel_pct"] < 0.05


def test_attach_merges_boards_and_skips_pitchers(monkeypatch):
    from engine.mlb.sources import savant
    from engine.mlb.models import MLBProp, MLBGameLog, TOTAL_BASES, STRIKEOUTS
    from engine.models import SportsbookLine
    from engine.mlb.sources.savant import _norm

    monkeypatch.setattr(savant, "load_expected_stats", lambda y, k="batter": {
        _norm("Big Bopper"): savant.StatcastProfile(xslg=0.520, slg=0.450)})
    monkeypatch.setattr(savant, "load_barrels", lambda y, k="batter": {
        _norm("Big Bopper"): {"barrel_pct": 0.14, "hard_hit_pct": 0.50}})

    def prop(name, pos):
        return MLBProp(name, "NYY", "BOS", pos,
                       STRIKEOUTS if pos == "SP" else TOTAL_BASES,
                       [MLBGameLog(i, "X", 1) for i in range(1, 6)], 1.5, None,
                       [SportsbookLine("proxy", 1.5)])

    hitter, pitcher = prop("Big Bopper", "RF"), prop("Big Bopper", "SP")
    n = savant.attach_statcast([hitter, pitcher], 2026)
    assert n == 1
    assert hitter.statcast.barrel_pct == 0.14      # merged from barrels board
    assert hitter.statcast.xslg == 0.520           # and expected stats
    assert pitcher.statcast is None                # wrong board for pitchers


def test_real_savant_shape_bom_and_quoted_joined_name_column():
    """Regression for the live-site 'no Statcast' bug: Savant's BOM sits
    BEFORE the first cell's opening quote, which used to break the quoting,
    split "last_name, first_name" into two columns, and shift every stat one
    column left — zero names parsed, wrong numbers everywhere."""
    from engine.mlb.sources.savant import (
        parse_expected_stats, parse_barrels, _read_csv_text, _norm,
    )
    text = ('\ufeff"last_name, first_name",player_id,year,pa,ba,est_ba,'
            'slg,est_slg,woba,est_woba\n'
            '"Judge, Aaron",592450,2026,412,.310,.298,.665,.641,.462,.448\n')
    out = parse_expected_stats(_read_csv_text(text))
    p = out[_norm("Aaron Judge")]
    assert abs(p.slg - 0.665) < 1e-9 and abs(p.xslg - 0.641) < 1e-9

    btext = ('\ufeff"last_name, first_name",player_id,attempts,'
             'avg_hit_speed,ev95percent,brl_percent\n'
             '"Acu\u00f1a Jr., Ronald",660670,300,95.9,52.1,15.2\n')
    b = parse_barrels(_read_csv_text(btext))
    acuna = b[_norm("Ronald Acuna Jr")]          # accents folded on the join
    assert abs(acuna["barrel_pct"] - 0.152) < 1e-9
    assert abs(acuna["hard_hit_pct"] - 0.521) < 1e-9


if __name__ == "__main__":
    class MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo): setattr(obj, name, val)

    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        needs_mp = fn.__code__.co_argcount == 1
        mp = MP() if needs_mp else None
        try:
            fn(mp) if needs_mp else fn()
            print(f"  ok  {name}")
        finally:
            if mp: mp.undo()
    print(f"\n{len(fns)} tests passed.")
