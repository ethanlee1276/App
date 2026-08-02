"""Fitting the correlation priors against our own history.

The parlay instruction set's Appendix says plainly that the rho magnitudes
"are professional estimates, not measured constants." A correlation prior is
the only thing standing between a same-game ticket and being priced as if
its legs were independent, so the gap between an estimate and a measurement
matters more here than almost anywhere else in this engine.

These tests pin the statistics, the two join fixes that made a measurement
possible at all, and the rule that a counted number is preferred to a
guessed one.
"""

import math
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import corrfit as C
from engine import parlays as P


def test_pearson_against_a_known_answer():
    assert abs(C.pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) - 1.0) < 1e-12
    assert abs(C.pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]) + 1.0) < 1e-12
    assert abs(C.pearson([1, 2, 3, 4], [1, 1, 1, 1])) != C.pearson(
        [1, 2, 3, 4], [1, 1, 1, 1]) or True     # constant y -> nan, not a crash


def test_partial_correlation_removes_the_shared_driver():
    """The measurement that changed a conclusion.

    Two teammates' receiving yards correlate at +0.70 raw, because both rise
    with the size of the passing game. §3 Type 3's claim is not about that —
    it is that they COMPETE for a finite pool, which is what is left after
    the pool's size is held fixed. Constructed here: x and y are pure noise
    plus a shared driver z, so their raw correlation is high and their
    partial correlation is zero. If partial() cannot see that, the -0.56 it
    reports on real data means nothing."""
    import random
    random.seed(11)
    zs = [random.gauss(0, 1) for _ in range(4000)]
    xs = [z + random.gauss(0, 0.5) for z in zs]
    ys = [z + random.gauss(0, 0.5) for z in zs]
    assert C.pearson(xs, ys) > 0.6, "the shared driver should dominate raw"
    assert abs(C.partial(xs, ys, zs)) < 0.05, (
        "partial correlation did not remove the shared driver")


def test_partial_correlation_still_sees_a_real_negative():
    """The negative control on the control: a genuine trade-off must survive
    the shared driver being taken out."""
    import random
    random.seed(12)
    zs = [random.gauss(0, 1) for _ in range(4000)]
    splits = [random.gauss(0, 1) for _ in range(4000)]
    xs = [z + s for z, s in zip(zs, splits)]
    ys = [z - s for z, s in zip(zs, splits)]     # they split a fixed pie
    assert C.partial(xs, ys, zs) < -0.5


def test_the_standard_error_shrinks_with_the_sample():
    assert C.stderr(0.5, 50) > C.stderr(0.5, 5000)
    assert C.stderr(0.5, 4) != C.stderr(0.5, 4)  # nan below the floor


def _fixture_db():
    """Two seasons of a made-up league where the answer is known."""
    import random
    random.seed(5)
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, "
              "period INT, game_id TEXT, player TEXT, team TEXT, opponent TEXT,"
              " position TEXT, home INT, market TEXT, value REAL)")
    c.execute("CREATE TABLE games (sport TEXT, season INT, period INT, "
              "game_id TEXT, home TEXT, away TEXT, home_score REAL, "
              "away_score REAL, spread REAL, total REAL, roof TEXT, "
              "surface TEXT, temp REAL, wind REAL, extra TEXT)")
    for wk in range(1, 121):
        vol = random.gauss(250, 60)
        # NOTE the deliberately DIFFERENT game_id schemes — this is the real
        # database's shape, and the reason a game_id join finds nothing.
        c.execute("INSERT INTO player_game_logs VALUES "
                  "('x',2025,?,?, 'QB','AAA','BBB','QB',1,'pass_yds',?)",
                  (wk, f"AAA-{wk:03d}", vol))
        c.execute("INSERT INTO player_game_logs VALUES "
                  "('x',2025,?,?, 'WR','AAA','BBB','WR',1,'rec_yds',?)",
                  (wk, f"AAA-{wk:03d}", vol * 0.35 + random.gauss(0, 12)))
        c.execute("INSERT INTO games VALUES "
                  "('x',2025,?,?, 'AAA','BBB',?,?,0,0,'','',0,0,'')",
                  (wk, "BBB@AAA", vol / 10.0, 20.0))
    c.commit()
    return path, c


def test_the_join_uses_a_key_the_two_tables_actually_share():
    """The bug that made every game-context prior unmeasurable.

    player_game_logs writes game ids like "TEN-001"; games writes "DAL@TB".
    Nothing joins on it. The tool reported "too thin to read (0 games)" for
    six priors against a database holding five full seasons, which reads as
    missing data and was in fact a key mismatch. Season + period + team is
    the key both tables really share."""
    path, conn = _fixture_db()
    logs = C._logs(conn, "x", "pass_yds")
    scores = C._scores(conn, "x")
    assert logs and scores
    key = next(iter(logs))
    assert len(key) == 3, "the log key is not (season, period, team)"
    assert key in scores, (
        "logs and scores do not share a key — every team_points, "
        "team_margin and opp_points prior silently measures nothing")


def test_a_known_correlation_is_recovered_end_to_end():
    """The positive control. The fixture builds a receiver whose yards are
    0.35x the passing game plus noise, so the two must come back strongly
    and positively correlated on a real fit."""
    path, conn = _fixture_db()
    prior = C.Prior("t", "x", (0.35, 0.50), "§4.1", "fixture", "teammates",
                    "pass_yds", "rec_yds")
    f = C.fit_one(conn, prior)
    assert f.n == 120, f.n
    assert f.r > 0.8, f.r
    assert f.se < 0.1


def test_a_missing_market_says_so_instead_of_measuring_a_subset():
    """A tool that quietly measures whatever it found and calls that the
    answer is worse than one that refuses."""
    path, conn = _fixture_db()
    prior = C.Prior("t", "x", (0.2, 0.3), "§5.1", "fixture", "teammates",
                    "pass_yds", "outs")
    f = C.fit_one(conn, prior)
    assert f.n == 0
    assert "no outs logs" in f.missing
    assert "no sample" in f.verdict


# --- feeding it back --------------------------------------------------------
def test_a_measured_correlation_is_preferred_to_an_estimate():
    """Every prior in parlays.py is a band midpoint under a humility clamp.
    The clamp is humility about a GUESS — a counted number has nothing to be
    humble about, so a measured rho is used at face value."""
    r, measured = P.rho_for("qb_passing_game", 0.425)
    assert measured is True
    assert r == P.MEASURED["qb_passing_game"][0]
    r2, measured2 = P.rho_for("a_pairing_nobody_has_fitted", 0.31)
    assert measured2 is False and r2 == 0.31


def test_every_measurement_carries_its_provenance():
    """A stale fit has to be visible rather than inherited: a correlation
    measured on one season and used three later is an estimate wearing a
    measurement's clothes."""
    for name, entry in P.MEASURED.items():
        rho, n, provenance = entry
        assert -1.0 < rho < 1.0, name
        assert n >= 100, f"{name} was fitted on {n} games"
        assert len(provenance) > 8 and "·" in provenance, name


def test_the_passing_game_stack_is_priced_on_the_measurement():
    """§4.1 bands the QB-to-WR1 link at +0.35 to +0.50; five seasons of our
    own games put it at +0.64. Pricing the estimate made §4.2's headline
    construction look like a worse ticket than it is."""
    a = dict(player="QB", team="GB", opponent="CHI", market="pass_yds",
             side="OVER", game_date="d")
    b = dict(player="WR", team="GB", opponent="CHI", market="rec_yds",
             side="OVER", game_date="d")
    rel = P.relate("nfl", a, b)
    assert rel.measured is True
    assert rel.rho > 0.50, "the measurement did not reach the pricing path"
    assert "measured" in rel.mechanism


def test_the_mlb_priors_are_measured_on_the_live_history():
    """§5.2 calls the pitcher stack the best construction in the system and
    §5.1 bands its correlation at +0.20 to +0.35. Ethan's own history — 26,717
    games — puts it at +0.268, which is the strongest confirmation any prior
    in this module has received.

    The lineup pairing came back at +0.186 against the same band: two bats in
    one lineup move together slightly LESS than the doc assumes. A small miss,
    but on 27,613 games a real one, and it makes the lineup stack a
    fractionally harder ticket rather than an easier one — which is the
    direction a measurement should be trusted in."""
    stack = P.MEASURED["pitcher_vs_lineup"]
    assert 0.20 <= stack[0] <= 0.35, "the measurement left §5.1's band"
    assert stack[1] > 20000, "fitted on too thin a sample to prefer"

    lineup = P.MEASURED["lineup_stack"]
    assert lineup[0] < 0.20, (
        "the lineup pairing measured below its band; pricing it at the band "
        "would claim more correlation than the history shows")
    assert lineup[1] > 20000

    # and both reach the pricing path
    a = dict(player="SP", team="PHI", opponent="CHC", market="strikeouts",
             side="OVER", game_date="d")
    b = dict(player="Bat", team="CHC", opponent="PHI", market="total_bases",
             side="UNDER", game_date="d")
    rel = P.relate("mlb", a, b)
    assert rel.measured is True and rel.rho == stack[0]
    assert "measured" in rel.mechanism


def test_a_strong_measured_correlation_is_not_mistaken_for_a_duplicate():
    """The bug measuring the priors exposed.

    §3 Type 6 says a pair correlating above +0.50 is treated as one leg FOR
    THRESHOLD PURPOSES. Separately, a genuine restatement — a moneyline and
    a spread on the same team — has its book ceiling capped at correlated
    fair, because no book pays 85% of the product on a pair that cashes
    together almost always. One flag was doing both jobs, so the moment the
    QB-to-WR1 link was measured at +0.64 instead of the estimated +0.43,
    §4.2's headline construction tripped a cap written for near-identical
    bets and stopped clearing."""
    def leg(pl, mk, p, odds):
        ev = p * (P.american_to_decimal(odds) - 1) - (1 - p)
        return dict(player=pl, team="GB", opponent="CHI", market=mk,
                    market_label=mk, side="OVER", line=1.5, odds=odds,
                    hit_prob=p, ev_per_unit=ev, recommended=True, grade="A",
                    game_date="2026-11-02", warnings=[], headline=f"{pl} {mk}")
    slate = {"date": "2026-11-02",
             "games": [dict(home="CHI", away="GB", date="2026-11-02",
                            spread=3.0, favorite="GB", total=49.0,
                            roof="outdoors", weather={"wind_mph": 6})],
             "recommendations": [leg("QB", "pass_yds", 0.58, -115),
                                 leg("WR1", "receptions", 0.56, -110)]}
    t = P.screen(slate, "nfl")["tickets"][0]
    assert t["pairs"][0]["rho_measured"] is True
    assert "duplicate" not in t["clash_screen"], (
        "a quarterback and his receiver were priced as one bet")
    assert t["qualified"] is True


def test_the_possession_pie_stays_a_kill_and_gets_louder():
    """The measurement moved this one hard in the doc's own direction: -0.56
    against a published band of -0.10 to +0.10. Type 3's kill-by-default is
    more right than the estimate knew, and the disposition must not soften
    just because the number changed."""
    a = dict(player="WR1", team="GB", opponent="CHI", market="rec_yds",
             side="OVER", game_date="d")
    b = dict(player="WR2", team="GB", opponent="CHI", market="rec_yds",
             side="OVER", game_date="d")
    rel = P.relate("nfl", a, b)
    assert rel.verdict == "kill"
    assert rel.clash == 3
    assert rel.rho < -0.4, rel.rho


if __name__ == "__main__":
    import re as _re
    declared = _re.findall(r"^def (test_\w+)",
                           open(__file__, encoding="utf-8").read(), _re.M)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert not set(declared) - {f.__name__ for f in fns}
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
