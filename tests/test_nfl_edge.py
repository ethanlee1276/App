"""NFL edges 1–4: usage bridge, injury gate, game-script tilt, QB watch.

The four approved NFL upgrades, three built here and one verified:

* **Usage bridge** — recent measured volume × season per-opportunity
  efficiency becomes a second baseline, blended against observed form by
  sample size (``USAGE_PRIOR_GAMES``). Thin outcome logs lean on the
  measured role; a full season of outcomes speaks for itself. Live
  boards only: the backtest stays usage-free so its fitted temperatures
  keep meaning what they meant, and journalfit audits the live drift.
* **Injury gate** — already existed (engine/injuries.py CONCERN_STATUSES
  + rules.apply_rules ``block_injury_concern``, fed by nfl_build's
  ``--injuries``). Pinned below so it can never silently rot.
* **Game-script tilt** — the spread (a measured market number) leans
  volume: underdogs project to trail and throw, favorites lean on the
  run. It lives in engine.matchup, which already owned the spread as a
  step function — nothing until 4 points, then a cliff — and now prices
  it per point, bounded tight. The module's stand-down contract carries
  over: teamcontext measuring pass rate for real silences the guess, and
  the learned branch replaces the matchup multiplier wholesale (its
  feature vector already carries the spread), so the signal is never
  counted twice.
* **QB dependency** — a new QB1 on the depth chart, or a concern status
  on the incumbent, stamps a warning on every pass-catcher prop for
  that team. A warning the human weighs, never a gate.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.models import (
    DefenseProfile, Game, GameLog, Injury, Prop, Team, Weather,
    PASS_YDS, REC_YDS, RECEPTIONS, RUSH_YDS,
)
from engine.nflusage import build_usage_maps, volume_roles
from engine.projection import build_projection

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- fixtures ----------------------------------------------------------------
def _prop(market=REC_YDS, team="KC", opp="BUF", vals=(60,), career=60.0,
          position="WR"):
    return Prop(player="Test Bridge", team=team, opponent=opp,
                position=position, market=market,
                logs=[GameLog(week=i + 1, opponent=opp, value=v)
                      for i, v in enumerate(vals)],
                career_avg=career, vs_opponent_avg=None, lines=[])


def _game(spread=0.0, home="KC", away="BUF"):
    # A dome mutes the weather module so these tests isolate one factor.
    return Game(home=home, away=away, weather=Weather(dome=True),
                spread=spread)


def _opp(abbr="BUF"):
    return Team(abbr=abbr, name=abbr, defense=DefenseProfile(team=abbr))


def _log(player, team, wk, market, value):
    return {"sport": "nfl", "season": 2025, "period": f"{wk:03d}",
            "game_id": f"{team}-{wk:03d}", "player": player, "team": team,
            "opponent": "OPP", "position": "", "home": 1,
            "market": market, "value": value}


# --- item 1: the volume roles off the ingested logs --------------------------
def test_volume_roles_measure_recent_volume_and_season_efficiency():
    conn = db.connect(":memory:")
    rows = []
    for wk in range(1, 7):
        rows += [_log("T.Hill", "MIA", wk, "targets", 8),
                 _log("T.Hill", "MIA", wk, "rec_yds", 90),
                 _log("T.Hill", "MIA", wk, "receptions", 6)]
    # Two quiet weeks of 2 targets: 4 season opportunities is below the
    # efficiency floor — no role at all, not a junk one.
    for wk in (1, 2):
        rows += [_log("B.Bench", "MIA", wk, "targets", 2),
                 _log("B.Bench", "MIA", wk, "rec_yds", 15)]
    db.upsert_player_logs(conn, rows)

    vol = volume_roles(conn)
    hill = vol[("t", "hill", "MIA")]
    assert hill["rec_yds"]["opp_per_game"] == 8.0
    assert abs(hill["rec_yds"]["eff"] - 11.25) < 0.01      # 540 yds / 48 tgt
    assert hill["rec_yds"]["opp_market"] == "targets"
    assert abs(hill["receptions"]["eff"] - 0.75) < 0.01    # catch rate
    assert ("b", "bench", "MIA") not in vol


def test_build_usage_maps_now_carries_the_volume_map():
    conn = db.connect(":memory:")
    maps = build_usage_maps(conn)
    assert set(maps) == {"red_zone", "snap", "volume", "xfp",
                         "team_of"}


# --- item 1: the blend inside the projection ---------------------------------
USAGE = {"opp_per_game": 8.0, "eff": 11.0, "opp_market": "targets",
         "n_weeks": 5}                                     # est = 88.0


def test_a_cold_start_leans_on_the_measured_role():
    """One outcome log: the measured role carries 80% of the baseline."""
    prop = _prop(vals=(60,))
    base = build_projection(prop, _game(), _opp())
    bridged = build_projection(prop, _game(), _opp(), usage=USAGE)
    want = (0.2 * 60 + 0.8 * 88) / 60          # every other factor cancels
    assert abs(bridged.mean / base.mean - want) < 0.01
    assert any("Usage bridge" in r for r in bridged.reasons)


def test_a_deep_sample_trusts_the_observed_form():
    prop = _prop(vals=(60,) * 12)
    base = build_projection(prop, _game(), _opp())
    bridged = build_projection(prop, _game(), _opp(), usage=USAGE)
    want = (0.75 * 60 + 0.25 * 88) / 60        # w = 12 / (12 + 4)
    assert abs(bridged.mean / base.mean - want) < 0.01
    # The same measured role moves a thin sample much further than a deep one.
    thin = build_projection(_prop(vals=(60,)), _game(), _opp(), usage=USAGE)
    assert thin.mean > bridged.mean


def test_no_usage_means_the_old_projection_exactly():
    prop = _prop(vals=(60, 55, 70))
    a = build_projection(prop, _game(), _opp())
    b = build_projection(prop, _game(), _opp(), usage=None)
    c = build_projection(prop, _game(), _opp(), usage={})
    assert a.mean == b.mean == c.mean


# --- item 3: the game-script tilt --------------------------------------------
def test_the_spread_leans_pass_volume_up_for_underdogs():
    prop = _prop(market=REC_YDS)
    dog = build_projection(prop, _game(spread=7.0), _opp())      # KC +7
    fav = build_projection(prop, _game(spread=-7.0), _opp())     # KC -7
    assert dog.mean > fav.mean
    assert abs(dog.mean / fav.mean - 1.028 / 0.972) < 0.005
    assert any("Game script" in r and "underdog" in r for r in dog.reasons)
    assert any("Game script" in r and "favorite" in r for r in fav.reasons)


def test_the_spread_no_longer_leans_run_volume_at_all():
    """THIS TEST USED TO ASSERT THE OPPOSITE. The idea is sound football
    — a favourite leads late and runs the clock — and five seasons do not
    show it. Production against the player's own prior form, bucketed by
    his team's spread, reads 1.103, 1.219, 1.184, 1.104, 1.167, 1.340
    from big favourite to big underdog: the ends differ by 21%, nothing
    in between agrees, the ends are the thinnest buckets, and what
    difference there is points the OTHER way — the big underdogs ran for
    most. An end-to-end number on a series that doubles back is not an
    effect size."""
    prop = _prop(market=RUSH_YDS, position="RB")
    dog = build_projection(prop, _game(spread=7.0), _opp())
    fav = build_projection(prop, _game(spread=-7.0), _opp())
    assert abs(dog.mean - fav.mean) < 1e-9, \
        "the spread is moving a rushing projection again"
    assert not any("run volume" in r for r in fav.reasons)
    # The constant stays so the measurement has something to name and
    # re-enabling is one line.
    from engine.matchup import SCRIPT_COEF_RUSH
    assert SCRIPT_COEF_RUSH > 0


def test_the_tilt_is_clamped_however_lopsided_the_spread():
    prop = _prop(market=PASS_YDS, position="QB")
    dog = build_projection(prop, _game(spread=20.0), _opp())
    fav = build_projection(prop, _game(spread=-20.0), _opp())
    assert dog.mean / fav.mean <= 1.05 / 0.95 + 1e-6


def test_a_pick_em_or_missing_spread_moves_nothing():
    prop = _prop(market=REC_YDS)
    flat = build_projection(prop, _game(spread=0.0), _opp())
    assert not any("Game script" in r for r in flat.reasons)


def test_the_learned_branch_never_stacks_the_tilt():
    """The feature vector already carries the spread; the learned magnitude
    owns that signal, so the same flat model must price both sides alike.
    (Reason chips still narrate the script — the rule modules supply
    reasons under the learned model by design — but the arithmetic is the
    learned multiplier's alone.)"""
    class _FlatModel:
        def has(self, market):
            return True

        def predict_multiplier(self, feat, market):
            return 1.0

    prop = _prop(market=REC_YDS)
    dog = build_projection(prop, _game(spread=7.0), _opp(), model=_FlatModel())
    fav = build_projection(prop, _game(spread=-7.0), _opp(), model=_FlatModel())
    assert abs(dog.mean - fav.mean) < 1e-9


def test_the_tilt_stands_down_when_team_context_is_measured():
    """engine.matchup's own contract, inherited by the smooth tilt: when
    teamcontext prices PROE and pace from measurement, the spread-derived
    guess at the same effect must go silent, not stack."""
    prop = _prop(market=REC_YDS)
    ctx = {"profiles": {}, "league": {}}
    dog = build_projection(prop, _game(spread=7.0), _opp(), context=ctx)
    fav = build_projection(prop, _game(spread=-7.0), _opp(), context=ctx)
    assert abs(dog.mean - fav.mean) < 1e-9
    assert not any("Game script" in r for r in dog.reasons)


# --- item 4: the QB-dependency watch -----------------------------------------
def _row(week, team, name, pos="QB", rank=1):
    return {"week": str(week), "club_code": team, "full_name": name,
            "depth_position": pos, "depth_team": str(rank)}


def test_qb1_map_reads_the_top_of_the_chart():
    from engine.sources.depthcharts import qb1_map
    rows = [_row(5, "KC", "Patrick Mahomes", rank=1),
            _row(5, "KC", "Carson Wentz", rank=2),
            _row(5, "BUF", "Josh Allen", rank=1),
            _row(5, "KC", "Travis Kelce", pos="TE", rank=1),
            _row(4, "KC", "Someone Else", rank=1)]        # wrong week
    assert qb1_map(rows, 5) == {"KC": "Patrick Mahomes", "BUF": "Josh Allen"}


def test_the_watch_flags_a_new_starter_and_a_dinged_incumbent():
    from engine.sources.depthcharts import qb_dependency
    rows = [_row(4, "BUF", "Josh Allen"), _row(5, "BUF", "Mitch Trubisky"),
            _row(4, "KC", "Patrick Mahomes"), _row(5, "KC", "Patrick Mahomes"),
            _row(4, "DET", "Jared Goff"), _row(5, "DET", "Jared Goff")]
    inj = [Injury(player="Patrick Mahomes", team="KC", position="QB",
                  role="qb", status="QUESTIONABLE")]
    notes = qb_dependency(rows, 5, inj)
    assert "takes over at QB1" in notes["BUF"] and "Josh Allen" in notes["BUF"]
    assert "QUESTIONABLE" in notes["KC"]
    assert "DET" not in notes                  # stable and healthy: silence


def test_week_one_has_no_baseline_to_compare_against():
    from engine.sources.depthcharts import qb_dependency
    notes = qb_dependency([_row(1, "KC", "Patrick Mahomes")], 1, [])
    assert notes == {}


def test_run_slate_stamps_the_note_on_pass_catchers_only():
    from engine.pipeline import run_slate
    note = "QB dependency: QB1 Test Case is QUESTIONABLE — every pass-catcher..."
    out = run_slate(os.path.join(ROOT, "data", "sample_slate.json"),
                    team_notes={"GB": note})
    gb_pass = [r for r in out["recommendations"]
               if r["team"] == "GB" and r["market"] in (REC_YDS, RECEPTIONS,
                                                        PASS_YDS)]
    gb_rush = [r for r in out["recommendations"]
               if r["team"] == "GB" and r["market"] == RUSH_YDS]
    assert gb_pass and all(note in r["warnings"] for r in gb_pass)
    assert gb_rush and all(note not in r["warnings"] for r in gb_rush)


def test_the_bridge_reaches_the_board_through_run_slate():
    from engine.fantasy import _short_key
    from engine.pipeline import run_slate
    slate = json.load(open(os.path.join(ROOT, "data", "sample_slate.json")))
    target = next(p for p in slate["props"] if p["market"] == RECEPTIONS)
    key = _short_key(target["player"], target["team"])
    usage = {"volume": {key: {RECEPTIONS: {
        "opp_per_game": 12.0, "eff": 0.9, "opp_market": "targets",
        "n_weeks": 5}}}}
    out = run_slate(os.path.join(ROOT, "data", "sample_slate.json"),
                    nfl_usage=usage)
    row = next(r for r in out["recommendations"]
               if r["player"] == target["player"]
               and r["market"] == RECEPTIONS)
    assert any("Usage bridge" in r for r in row["reasons"])


# --- item 2: the injury gate stands (verified, pinned) -----------------------
def test_the_injury_gate_already_stands():
    from engine.injuries import CONCERN_STATUSES, player_injury_status
    from engine.rules import RuleConfig
    assert {"QUESTIONABLE", "DOUBTFUL", "GTD"} <= CONCERN_STATUSES
    assert RuleConfig().block_injury_concern is True
    prop = _prop()
    dinged = [Injury(player=prop.player, team=prop.team, position="WR",
                     role="wr1", status="QUESTIONABLE")]
    assert player_injury_status(prop, dinged) == "QUESTIONABLE"


# --- the seams that keep the lanes honest ------------------------------------
def test_the_backtest_only_takes_the_bridge_when_asked():
    """THIS TEST USED TO REQUIRE THE OPPOSITE, and its reason was
    inverted. It read: "fitted temperatures were earned without the
    bridge; feeding it into the harness would quietly refit them against
    a different model." True — but it kept the harness consistent with
    the STORED TEMPERATURES rather than with the live board, and the
    board is what takes bets. `nfl_build` passes the bridge and
    `build_projection` blends it against form by sample size, so at
    USAGE_PRIOR_GAMES games of log it supplies half the base. Every
    calibration fitted through the usage-free walk was therefore earned
    against a model nobody runs, and `propcal`'s AUC numbers described
    that model too.

    What the old test was really protecting is that nothing changes
    silently, and that survives: the parameter defaults to None, so a
    caller passing no connection replays exactly as before. `propcal`
    opts in deliberately, and it refits from scratch every time — the
    refit against a different model is the entire point of it."""
    src = open(os.path.join(ROOT, "engine", "backtest.py"),
               encoding="utf-8").read()
    assert "usage = None" in src, "the bridge must be off by default"
    assert "if usage_conn is not None:" in src
    assert "upto_week=w" in src, \
        "a replay reading the finished season hands week 7 its own answers"
    assert "team_notes" not in src


def test_the_launcher_ships_the_depth_flag():
    """The QB watch and role refinement must ride the automated refresh —
    a feature that only fires on a hand-typed flag is a demo, not a
    feature (the --injuries lesson, learned once already)."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def refresh_nfl(")
    block = src[i:src.index("def refresh_predmarkets(")]
    assert '"--injuries"' in block and '"--depth"' in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
