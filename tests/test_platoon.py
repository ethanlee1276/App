"""Tests for measured platoon splits (in-memory SQLite)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.mlb.platoon import platoon_splits, attach_platoon


def _seed(conn):
    """Lefty Masher: 1.0 TB/game overall, but 1.8 vs LHP and 0.6 vs RHP."""
    logs, starters = [], []
    for i in range(1, 31):
        date = f"2026-{4 + i // 28:02d}-{(i % 28) + 1:02d}"
        hand = "L" if i % 2 else "R"
        val = 1.8 if hand == "L" else 0.6
        logs.append({"sport": "mlb", "season": 2026, "period": date,
                     "game_id": f"LM-{date}", "player": "Lefty Masher",
                     "team": "NYY", "opponent": "BOS", "position": "RF",
                     "home": 1, "market": "total_bases", "value": val})
        starters.append({"sport": "mlb", "season": 2026, "period": date,
                         "game_id": "NYY@BOS", "team": "BOS",
                         "pitcher": f"P{hand}", "throws": hand})
    db.upsert_player_logs(conn, logs)
    db.upsert_game_starters(conn, starters)


def test_splits_measure_shrink_and_clamp():
    conn = db.connect(":memory:")
    _seed(conn)
    s = platoon_splits(conn, "total_bases")
    m = s["lefty masher"]
    # Crushes lefties, struggles vs righties — shrunk and clamped, so the
    # raw 1.5x becomes a bounded nudge, never a lever.
    assert m["L"] > 1.05 and m["R"] < 0.95
    assert 0.85 <= m["R"] and m["L"] <= 1.18
    assert m["nL"] == 15 and m["nR"] == 15
    # Thin histories never produce a split.
    assert "someone else" not in s


def test_attach_uses_tonights_starter_hand():
    from engine.mlb.models import (MLBGame, MLBProp, MLBGameLog, Pitcher,
                                   TOTAL_BASES)
    from engine.models import SportsbookLine
    from engine.mlb.data_loader import MLBSlate

    game = MLBGame(home="NYY", away="BOS", park="yankee",
                   pitchers={"BOS": Pitcher(name="Southpaw", throws="L")})
    prop = MLBProp("Lefty Masher", "NYY", "BOS", "RF", TOTAL_BASES,
                   [MLBGameLog(i, "BOS", 1) for i in range(1, 6)], 1.0, None,
                   [SportsbookLine("proxy", 1.5)], bats="R", lineup_spot=2)
    slate = MLBSlate(date="2026-07-26", games=[game], props=[prop])
    splits = {TOTAL_BASES: {"lefty masher": {"L": 1.12, "R": 0.92,
                                             "nL": 15, "nR": 15}}}
    assert attach_platoon(slate, splits) == 1
    # Re-anchored 2026-08-31 (the MLB handicapping script, §11): the
    # stored 1.12 was shrunk toward 1.0 with weight nL/(nL+SHRINK)=0.5;
    # the unearned half now regresses toward the LEAGUE advantage norm
    # (1.04) instead of toward "no effect": 1.12 + 0.5×0.04 = 1.14.
    assert prop.platoon_factor == 1.14, prop.platoon_factor
    assert "vs lefties" in prop.platoon_note

    # The matchup layer uses the measured split INSTEAD of the generic bump.
    from engine.mlb.matchup import evaluate_matchup
    eff = evaluate_matchup(prop, game)
    assert any("Measured split" in r for r in eff.reasons)
    assert not any("Platoon edge —" in r for r in eff.reasons)


def test_parse_official_splits():
    from engine.mlb.sources.mlbstats import parse_batting_splits
    payload = {"people": [{"id": 545361, "stats": [{"splits": [
        {"split": {"code": "vl"},
         "stat": {"plateAppearances": "150", "slg": ".620", "homeRuns": "12"}},
        {"split": {"code": "vr"},
         "stat": {"plateAppearances": "310", "slg": ".540", "homeRuns": "18"}},
        {"split": {"code": "h"}, "stat": {"slg": ".700"}},   # home split — ignored
    ]}]}, {"id": 0}]}
    sp = parse_batting_splits(payload)
    assert sp == {545361: {"vl": {"pa": 150, "slg": 0.62, "hr": 12},
                           "vr": {"pa": 310, "slg": 0.54, "hr": 18}}}


class _G:
    def __init__(self, throws):
        class _P:  # noqa: N801 — tiny stand-in
            pass
        p = _P(); p.throws = throws; p.name = "Starter"
        self.pitchers = {"BOS": p}


class _Slate:
    def __init__(self, props, throws="L"):
        self.props = props
        self._g = _G(throws)

    def game_for(self, prop):
        return self._g


def _official_prop(person_id=545361, factor=1.0):
    from engine.mlb.models import MLBProp
    p = MLBProp(player="Lefty Masher", team="NYY", opponent="BOS",
                position="RF", market="total_bases", logs=[], career_avg=1.0,
                vs_pitcher_avg=None, lines=[], person_id=person_id)
    p.platoon_factor = factor
    return p


def test_official_split_fills_only_unmeasured_players():
    from engine.mlb.platoon import attach_official_splits
    splits = {545361: {"vl": {"pa": 150, "slg": 0.620, "hr": 12},
                       "vr": {"pa": 310, "slg": 0.440, "hr": 10}}}
    fresh = _official_prop()                      # our logs: unmeasured
    already = _official_prop(factor=1.12)         # our logs: measured
    slate = _Slate([fresh, already], throws="L")
    n = attach_official_splits(slate, splits)
    assert n == 2                                 # both carry the raw split
    assert fresh.platoon_official and already.platoon_official
    # The unmeasured player gains an official SLG-split factor (>1: he
    # slugs .620 vs LHP against a .497 blend), shrunk and clamped.
    assert 1.0 < fresh.platoon_factor <= 1.18
    assert "Official season split" in fresh.platoon_note
    # The measured player keeps his our-log factor untouched.
    assert already.platoon_factor == 1.12


def test_official_split_needs_a_real_sample():
    from engine.mlb.platoon import attach_official_splits
    thin = {545361: {"vl": {"pa": 20, "slg": 0.900, "hr": 4},
                     "vr": {"pa": 300, "slg": 0.450, "hr": 12}}}
    p = _official_prop()
    attach_official_splits(_Slate([p], throws="L"), thin)
    assert p.platoon_factor == 1.0               # 20 PA is an anecdote


def test_hr_model_uses_measured_power_split_both_directions():
    """A reverse-split hitter gets SUPPRESSED against the hand a flat bump
    would have boosted — the exact failure the flat model can't see."""
    from engine.mlb.models import MLBProp, MLBGame, Pitcher
    from engine.mlb.homeruns import pitcher_multiplier

    def prop(official):
        p = MLBProp(player="X", team="NYY", opponent="BOS", position="RF",
                    market="home_runs", logs=[], career_avg=0.2,
                    vs_pitcher_avg=None, lines=[], bats="R")
        p.platoon_official = official
        return p

    game = MLBGame(home="NYY", away="BOS", park="yankee",
                   pitchers={"BOS": Pitcher(name="Lefty", throws="L")})
    # Righty who CRUSHES lefties: 12 HR in 160 PA vs L, 6 in 340 vs R.
    masher = prop({"vl": {"pa": 160, "slg": 0.62, "hr": 12},
                   "vr": {"pa": 340, "slg": 0.45, "hr": 6}})
    # Righty with a REVERSE split: 1 HR in 160 PA vs L, 17 in 340 vs R.
    reverse = prop({"vl": {"pa": 160, "slg": 0.40, "hr": 1},
                    "vr": {"pa": 340, "slg": 0.52, "hr": 17}})
    flat = prop(None)                            # no data → flat bump

    m_mash, r_mash = pitcher_multiplier(masher, game)
    m_rev, r_rev = pitcher_multiplier(reverse, game)
    m_flat, r_flat = pitcher_multiplier(flat, game)

    assert m_mash > m_flat > m_rev
    assert any("Measured power split" in r for r in r_mash + r_rev)
    assert any("Platoon edge" in r for r in r_flat)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
