"""The home-run long-shot model, measured for the first time.

The per-market sweep has a "Home Runs" row and it is not this model. That
row runs the GENERIC prop model over home runs — a market it never bets,
which is why it reports 0 bets. The board's picks come from
``engine.mlb.homeruns.hr_probability``, and nothing scored it against a
real outcome until this file.

That gap mattered more than gaps usually do. On a summer night the Long
Shots board is often the only board holding open bets, so the single model
taking money was the single model nobody had measured.

Two things this had to get right, and both are counter-intuitive:

RANKING, NOT CALIBRATION. The board takes three names off the top of a
list; it never bets the population. On a ~10% event, predicting 10% for
everyone scores Brier ~0.09, and perfect knowledge of each hitter's true
rate only reaches ~0.091 — so a model with no discrimination and a model
with all of it are separated by about two points of skill score. On the
synthetic population below, Brier skill reported +0.1% while the model's
top fifth homered 2.0x as often as its bottom fifth. Brier could not see
the only thing the board uses the model for.

HONEST INPUTS. Statcast profiles are not stored historically, so this
measures the model's fallback path. Reporting a clean number without
saying that would describe a model nobody runs.
"""

import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEAMS = ["CHC", "PHI", "NYY", "LAD", "BOS", "COL", "SD", "ATL"]


def _seed(rates, players=120, games=60, seed=3):
    """A synthetic population where each hitter's TRUE home-run rate is
    drawn from ``rates`` — so we know the right answer in advance."""
    from engine import db
    path = os.path.join(tempfile.mkdtemp(), "hr.db")
    conn = db.connect(path)
    rng = random.Random(seed)
    for p in range(players):
        rate = rng.choice(rates)
        team = rng.choice(TEAMS)
        for g in range(games):
            opp = rng.choice([t for t in TEAMS if t != team])
            home = g % 2 == 0
            d = f"2026-0{4 + g // 30}-{(g % 30) + 1:02d}"
            conn.execute(
                "INSERT INTO player_game_logs (sport,season,period,game_id,"
                "player,team,opponent,position,home,market,value) VALUES "
                "('mlb',2026,?,?,?,?,?,'OF',?,'home_runs',?)",
                (d, f"g{p}-{g}", f"Hitter {p}", team, opp, int(home),
                 1.0 if rng.random() < rate else 0.0))
            H, A = (team, opp) if home else (opp, team)
            conn.execute(
                "INSERT OR IGNORE INTO games (sport,season,period,game_id,"
                "home,away,home_score,away_score,roof,temp,wind) VALUES "
                "('mlb',2026,?,?,?,?,4,3,'open',74,8)",
                (d, f"gm{p}-{g}", H, A))
    conn.commit()
    return path, conn


SPREAD = [0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18]
FLAT = [0.10]


# --- the measurement that matters: ranking ----------------------------------
def test_it_finds_ranking_ability_when_ranking_ability_exists():
    from engine.mlb.hrbacktest import backtest_hr, lift
    _, conn = _seed(SPREAD)
    _report, _cov, settled = backtest_hr(conn, use_real_lines=False)
    bands = lift(settled)
    assert len(bands) == 5
    lo, hi = bands[0]["actual"], bands[-1]["actual"]
    assert hi > lo * 1.4, \
        f"real 4%-to-18% spread, but top fifth {hi:.1%} vs bottom {lo:.1%}"


def test_it_reports_no_ranking_ability_when_every_hitter_is_identical():
    """The negative control, and the one that makes the test above mean
    something. Every hitter has the same true rate here, so any ordering
    the model produces is noise and must not read as skill."""
    from engine.mlb.hrbacktest import backtest_hr, lift
    _, conn = _seed(FLAT, seed=9)
    _report, _cov, settled = backtest_hr(conn, use_real_lines=False)
    bands = lift(settled)
    lo, hi = bands[0]["actual"], bands[-1]["actual"]
    assert hi < lo * 1.4, \
        f"identical hitters, but the model 'ranked' them {hi:.1%} vs {lo:.1%}"


def test_brier_alone_would_have_missed_the_difference():
    """The reason lift() exists. On a rare event both populations score
    almost the same Brier skill, so a report built on Brier would call a
    model with real discrimination and one with none the same thing."""
    from engine.mlb.hrbacktest import backtest_hr
    _, spread_conn = _seed(SPREAD)
    _, flat_conn = _seed(FLAT, seed=9)
    a, _, _ = backtest_hr(spread_conn, use_real_lines=False)
    b, _, _ = backtest_hr(flat_conn, use_real_lines=False)
    ska, skb = a.skill()["skill"], b.skill()["skill"]
    assert abs(ska - skb) < 0.05, (
        f"Brier skill separated them by {abs(ska - skb):.1%} — if it really "
        "can tell these apart, lift() is redundant")


def test_lift_refuses_a_sample_too_thin_to_bucket():
    from engine.mlb.hrbacktest import lift
    from engine.backtest import SettledProp
    few = [SettledProp("p", "home_runs", 0.5, 0, 0.1, 0.1, 0.0)
           for _ in range(60)]
    assert lift(few) == []


# --- it must score the model the board actually runs ------------------------
def test_it_calls_the_production_probability_function():
    src = open(os.path.join(ROOT, "engine", "mlb", "hrbacktest.py"),
               encoding="utf-8").read()
    assert "from .homeruns import hr_probability" in src
    assert "hr_probability(prop, game)" in src
    # A reimplementation would measure a copy of the model.
    assert "def hr_probability" not in src


def test_it_walks_forward_and_never_sees_the_game_it_is_scoring():
    src = open(os.path.join(ROOT, "engine", "mlb", "hrbacktest.py"),
               encoding="utf-8").read()
    assert "prior = vals[:i][::-1][:limit]" in src
    assert "actual=float(vals[i])" in src


def test_the_side_is_always_the_over_so_bins_cannot_invert():
    """Home runs are the pathological one-sided market: hit_prob is the
    probability of the side backed, so grading a board that always takes
    the over against "did the under hit" reverses every bin."""
    from engine.mlb.hrbacktest import backtest_hr
    _, conn = _seed(SPREAD)
    _r, _c, settled = backtest_hr(conn, use_real_lines=False)
    assert {s.side for s in settled} == {"OVER"}
    assert {s.line for s in settled} == {0.5}


# --- honesty about what was reconstructed -----------------------------------
def test_it_reports_that_statcast_was_not_available():
    from engine.mlb.hrbacktest import backtest_hr
    _, conn = _seed(SPREAD)
    _r, cov, _s = backtest_hr(conn, use_real_lines=False)
    assert cov.with_statcast == 0
    assert any("Statcast" in ln for ln in cov.lines())


def test_the_park_is_resolved_from_the_real_home_team():
    """Without the park the environment multiplier is a constant, and the
    model's whole weather story stops being tested."""
    from engine.mlb.hrbacktest import backtest_hr
    _, conn = _seed(SPREAD)
    _r, cov, _s = backtest_hr(conn, use_real_lines=False)
    assert cov.with_park == cov.props


def test_coverage_counts_cannot_exceed_the_population():
    from engine.mlb.hrbacktest import backtest_hr
    _, conn = _seed(SPREAD)
    _r, cov, settled = backtest_hr(conn, use_real_lines=False)
    assert cov.props == len(settled)
    for n in (cov.with_park, cov.with_weather, cov.with_statcast,
              cov.with_book_line):
        assert 0 <= n <= cov.props


# --- the CLI ----------------------------------------------------------------
def test_an_empty_db_says_ingest_rather_than_printing_an_empty_table():
    from engine import db
    path = os.path.join(tempfile.mkdtemp(), "empty.db")
    db.connect(path)
    p = subprocess.run([sys.executable, "hr_backtest.py", "--db", path],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0
    assert "No MLB home-run game logs" in p.stdout
    assert "ingest.py mlb" in p.stdout


def test_the_cli_prints_the_ranking_table_and_a_verdict():
    path, _ = _seed(SPREAD)
    p = subprocess.run([sys.executable, "hr_backtest.py", "--db", path,
                        "--naive"], cwd=ROOT, capture_output=True,
                       text=True, timeout=600)
    assert p.returncode == 0, p.stderr[-400:]
    assert "TOP fifth (it bets here)" in p.stdout
    assert "as often as its bottom fifth" in p.stdout
    assert "Statcast 0%" in p.stdout


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
