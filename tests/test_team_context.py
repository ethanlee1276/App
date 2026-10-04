"""NFL Phase 2 — pricing with measured pace, PROE and offensive EPA.

The data has been collected since Phase 1 and displayed on game pages, but
never priced a prop; the model doc's own line was "Model pricing hookup is
Phase 2".

Three variants were built and measured against the same 2,626 settled
props from 2025 weeks 6-17. The baseline is the shipped model:

                     MAE     Brier    skill    ROI
    baseline        23.09   0.2425   +2.7%   +13.5%
    level           23.38   0.2434   +2.4%    +2.5%
    level, replacing
      the proxies   23.28   0.2433   +2.4%    +1.0%
    drift           23.01   0.2424   +2.8%   +10.0%

LEVEL made the model worse on every axis that matters, and the reason
turned out to be upstream of the layer entirely: the projection starts from
``form.mean``, the player's own recent games ON THIS TEAM. A receiver in a
fast, pass-heavy offence already carries that pace and pass rate in his own
numbers. Multiplying by the team's level counts it twice.

DRIFT prices only what form has not absorbed — this team over its last few
weeks against this team over the season so far — and edges the baseline on
MAE, Brier and skill, which are measured over all 2,626 props. Its ROI is
nominally lower on 284 bets vs 257, but at n≈270 the standard error on win
rate is about 3 points and the gap is 2.3, so those two ROI figures are not
distinguishable.

None of it ships enabled. One season is one season, and the gains that
survive are small enough to be noise. What ships is the machinery, the
switch, and these numbers — so the next season of data settles it instead
of re-running the argument.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.teamcontext import (context_multiplier, drift_multiplier,
                                league_means, profiles_through)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seeded():
    """Two teams, six weeks, with a deliberate late change of pace.

    Six because MIN_WEEKS is 4: a shorter fixture yields no profile at all
    and every assertion below becomes a KeyError rather than a result."""
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    for wk in range(1, 7):
        # FAST speeds up sharply in the last two weeks; SLOW never changes.
        fast_pace = 32.0 if wk <= 4 else 28.0
        conn.execute(
            "INSERT INTO team_weeks (sport,season,period,team,plays,proe,"
            "off_epa,pass_epa,rush_epa,def_epa,pace) VALUES "
            "('nfl',2025,?,'FAST',65,?,0.10,0.12,0.02,0.0,?)",
            (f"{wk:03d}", 0.06 if wk > 3 else 0.0, fast_pace))
        conn.execute(
            "INSERT INTO team_weeks (sport,season,period,team,plays,proe,"
            "off_epa,pass_epa,rush_epa,def_epa,pace) VALUES "
            "('nfl',2025,?,'SLOW',60,-0.04,-0.08,-0.06,-0.03,0.0,34.0)",
            (f"{wk:03d}",))
    conn.commit()
    return conn


# --- the thing that would invalidate everything -----------------------------
def test_a_week_never_sees_itself_or_anything_after_it():
    """A backtest of week 8 reading season averages has seen week 15. It
    would score beautifully and none of it would survive a live Sunday."""
    conn = _seeded()
    p = profiles_through(conn, 2025, "005", last_n=None)
    assert p["FAST"]["weeks"] == 4, "week 5 priced itself with weeks 5 and 6"
    assert abs(p["FAST"]["pace"] - 32.0) < 1e-9, \
        "the pre-change weeks are contaminated by the post-change ones"


def test_the_full_window_sees_everything_before_it():
    """The control — otherwise 'sees nothing' passes the test above."""
    conn = _seeded()
    p = profiles_through(conn, 2025, "007", last_n=None)
    assert p["FAST"]["weeks"] == 6


def test_a_team_with_too_few_weeks_gets_no_profile_at_all():
    """Early season is exactly when the sample is thinnest and the
    temptation to nudge anyway is greatest."""
    conn = _seeded()
    assert profiles_through(conn, 2025, "004", last_n=None) == {}


# --- the sign, which would be silent if wrong -------------------------------
def test_a_faster_team_gets_more_volume_not_less():
    """`pace` is SECONDS BETWEEN SNAPS, so lower is faster. Inverting this
    would flip every volume adjustment in the model and nothing would
    visibly break."""
    conn = _seeded()
    p = profiles_through(conn, 2025, "007", last_n=None)
    lg = league_means(p)
    fast, _ = context_multiplier(p["FAST"], lg, "rec_yds")
    slow, _ = context_multiplier(p["SLOW"], lg, "rec_yds")
    assert fast > 1.0 > slow, f"fast={fast:.3f} slow={slow:.3f}"


def test_a_pass_heavy_team_lifts_receiving_and_cuts_rushing():
    conn = _seeded()
    p = profiles_through(conn, 2025, "007", last_n=None)
    lg = league_means(p)
    rec, _ = context_multiplier(p["FAST"], lg, "rec_yds")
    rush, _ = context_multiplier(p["FAST"], lg, "rush_yds")
    assert rec > rush


def test_nothing_here_prices_the_opponent():
    """matchup.py owns defence. Reading def_epa too would price the same
    fact twice, which is the mistake the LEVEL variant made with pace and
    PROE and paid for in ROI."""
    src = open(os.path.join(ROOT, "engine", "teamcontext.py"),
               encoding="utf-8").read()
    i = src.index("def context_multiplier(")
    j = src.index("def drift_multiplier(")
    assert 'get("def_epa")' not in src[i:j]


def test_a_missing_profile_is_silent_rather_than_invented():
    assert context_multiplier(None, {"pace": 31.0}, "rec_yds") == (1.0, [])
    assert drift_multiplier(None, {"pace": 31.0}, "rec_yds") == (1.0, [])


# --- drift measures change, which is the whole distinction ------------------
def test_drift_sees_a_team_that_just_sped_up():
    conn = _seeded()
    recent = profiles_through(conn, 2025, "007", last_n=2)      # the fast weeks
    baseline = profiles_through(conn, 2025, "007", last_n=None)  # the season
    f, why = drift_multiplier(recent["FAST"], baseline["FAST"], "rec_yds")
    assert f > 1.02, f"a 32s→28s change produced only {f:.3f}"
    assert any("faster" in r for r in why)


def test_drift_says_nothing_about_a_team_that_has_not_changed():
    """SLOW is identical every week. Level would still shade it; drift must
    not, because form has already absorbed a constant."""
    conn = _seeded()
    recent = profiles_through(conn, 2025, "007", last_n=2)
    baseline = profiles_through(conn, 2025, "007", last_n=None)
    f, why = drift_multiplier(recent["SLOW"], baseline["SLOW"], "rec_yds")
    assert abs(f - 1.0) < 1e-9 and why == []


def test_level_and_drift_disagree_about_an_unchanged_team():
    """The two modes are genuinely different measurements, not a rename."""
    conn = _seeded()
    recent = profiles_through(conn, 2025, "007", last_n=2)
    baseline = profiles_through(conn, 2025, "007", last_n=None)
    lg = league_means(baseline)
    lvl, _ = context_multiplier(recent["SLOW"], lg, "rec_yds")
    drf, _ = drift_multiplier(recent["SLOW"], baseline["SLOW"], "rec_yds")
    assert abs(lvl - 1.0) > 0.01 and abs(drf - 1.0) < 1e-9


# --- it must stay off, and stay switchable ----------------------------------
def test_the_projection_prices_exactly_as_before_with_no_context():
    """The A/B only means something if 'off' is byte-for-byte the old
    model."""
    src = open(os.path.join(ROOT, "engine", "projection.py"),
               encoding="utf-8").read()
    assert "ctx_mult, ctx_reasons = 1.0, []" in src
    assert "if context:" in src


def test_the_backtest_rebuilds_context_per_week_not_once():
    src = open(os.path.join(ROOT, "engine", "backtest.py"),
               encoding="utf-8").read()
    assert 'profiles_through(_hc, season, f"{int(w):03d}")' in src
    assert "ctx_by_week" in src


def test_the_proxies_stand_down_only_when_the_measured_layer_is_on():
    src = open(os.path.join(ROOT, "engine", "matchup.py"),
               encoding="utf-8").read()
    assert "measured_context: bool = False" in src
    i = src.index("if measured_context:")
    # The DEFENSIVE factor is applied above this line and must survive.
    assert src.index("_defense_factor(defense, prop)") < i


def test_both_modes_are_reachable_from_the_cli():
    src = open(os.path.join(ROOT, "backtest.py"), encoding="utf-8").read()
    assert '"--team-context"' in src
    assert 'choices=("level", "drift")' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
