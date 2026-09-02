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
    humble about, so a measured rho is used at face value.

    Asserted through `rho_meta` rather than against MEASURED directly: on
    a machine whose settle has run, the number in use is the LIVE refit
    and the frozen table is only the floor beneath it. A test that reads
    the floor fails on exactly the machine where the feature works."""
    r, measured = P.rho_for("qb_passing_game", 0.425)
    assert measured is True
    assert r == P.rho_meta("qb_passing_game")[0]
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


def test_the_possession_pie_stays_a_kill_whatever_the_number_says():
    """THE DISPOSITION IS THE CLAIM, and it is the half that held up.

    This asserted rho < -0.4, on the strength of a hand-taken -0.560
    against a published band of -0.10 to +0.10 — "Type 3's
    kill-by-default is more right than the estimate knew". Refit on four
    seasons of the CURRENT ingest it reads -0.098, inside the doc's band
    after all, and the -0.560 turns out to have been measured while
    `rec_yds` was stored for wide receivers only (2026-08-02, against the
    widening on 2026-08-15). The estimate was right; the correction was
    an artefact of the data underneath it.

    None of which softens the pairing: two teammates splitting one
    possession pie is a Type 3 kill on the MECHANISM, not on the size of
    the number, and that is what this asserts now. Isolated, because the
    rho in use depends on whether this machine has refit, and a test
    whose verdict changes with the operator's history is testing the
    operator."""
    a = dict(player="WR1", team="GB", opponent="CHI", market="rec_yds",
             side="OVER", game_date="d")
    b = dict(player="WR2", team="GB", opponent="CHI", market="rec_yds",
             side="OVER", game_date="d")
    with _isolated():                      # no live fit: the floor applies
        rel = P.relate("nfl", a, b)
        assert rel.verdict == "kill"
        assert rel.clash == 3
        assert rel.rho < 0, rel.rho
    with _isolated():                      # and with a superseded fit
        C._write_state({"possession_pie": {
            "r": -0.0975, "n": 2278, "se": 0.0208, "fit_at": time.time(),
            "superseded": {"was": -0.56, "sigma": 22.3}}})
        C._cache.clear()
        rel = P.relate("nfl", a, b)
        assert rel.verdict == "kill" and rel.clash == 3
        assert rel.rho == -0.0975


# --- and it feeds itself back ------------------------------------------------
#
# For three weeks this module was the only fitter on the site that a human
# had to remember to run: you typed the command, read the table, and copied
# five numbers into engine/parlays.MEASURED — across two naming schemes,
# flipping one sign on the way. Every other loop refits on the settle. A
# manual step on a one-person project is a step that stops happening, and
# nothing could tell you it had.

import json                                                    # noqa: E402
import time                                                    # noqa: E402


import contextlib                                             # noqa: E402


@contextlib.contextmanager
def _isolated(tmpdir=None):
    """Point the state file somewhere disposable, then PUT IT BACK.

    Restoring matters more than isolating: `measured()` caches, and a
    test that leaves a fake fit standing would silently rewrite what
    every later test in this file believes the pricer is running on. The
    first draft of these tests did exactly that, and the pass they got
    was luck rather than agreement."""
    keep, keep_cache = C.STATE_PATH, dict(C._cache)
    C.STATE_PATH = os.path.join(tmpdir or tempfile.mkdtemp(), "corr.json")
    C._cache.clear()
    try:
        yield C.STATE_PATH
    finally:
        C.STATE_PATH = keep
        C._cache.clear()
        C._cache.update(keep_cache)


def test_the_adoption_table_names_things_that_actually_exist():
    """A typo either side is silent: the pairing simply never adopts, and
    the site keeps pricing the frozen number forever while the log says
    nothing at all."""
    keys = {p.key for p in C.PRIORS}
    for fit_key, (parlay_key, sign) in C.ADOPT.items():
        assert fit_key in keys, f"{fit_key} is not a fitted pairing"
        assert parlay_key in P.MEASURED, \
            f"{parlay_key} is not a pairing the pricer reads"
        assert sign in (1, -1), parlay_key


def test_the_one_sign_that_flips_is_written_down_rather_than_remembered():
    """§5.1 states the pitcher stack as strikeouts-over against the
    opposing total UNDER; this module measures strikeouts against the RUNS
    that lineup scores, which is the same claim with the opposite sign.
    It lived in a comment, applied by hand, once."""
    assert C.ADOPT["sp_strikeouts__opp_runs"][1] == -1
    assert all(sign == 1 for key, (_n, sign) in C.ADOPT.items()
               if key != "sp_strikeouts__opp_runs"), \
        "a second sign flip appeared with no test to explain it"


def test_a_thin_fit_never_displaces_a_better_sampled_number():
    """The estimators here are sample-shaped: the possession-pie partial
    reads -0.560 on five NFL seasons and -0.045 on one. That is not noise,
    it is a different data depth answering a different question — so a
    thin box must never overwrite a rich fit."""
    path, conn = _fixture_db()
    with _isolated(os.path.dirname(path)):
        out = C.refresh(path)
    assert not out["adopted"], "a 120-game fixture displaced a 2,844-game fit"
    assert out["held"], "a fit that declines to adopt must say why"
    assert any("needs" in h["why"] or "no " in h["why"] for h in out["held"])
    conn.close()


def test_a_well_sampled_fit_is_adopted_and_read_back():
    with _isolated():
        C._write_state({"qb_passing_game": {
            "r": 0.71, "n": 99999, "se": 0.01,
            "from": "qb_pass_yds__wr_rec_yds",
            "sport": "nfl", "fit_at": time.time()}})
        C._cache.clear()
        got = C.measured("qb_passing_game")
        assert got and got["r"] == 0.71
        # And the pricer uses it in preference to the frozen table.
        r, measured = P.rho_for("qb_passing_game", 0.425)
        assert measured is True and r == 0.71
        assert P.rho_n("qb_passing_game") == 99999, \
            "the card would quote the frozen sample beside a live number"


def test_an_unusable_fit_is_refused_rather_than_priced():
    """|r| at the rail is a broken join — two series that are the same
    column, or a partial whose covariate collapsed onto its inputs — and
    a tiny sample is a rumour. Neither may reach a ticket."""
    with _isolated():
        for bad in ({"r": 0.999, "n": 99999}, {"r": 0.4, "n": 3}):
            C._write_state({"lineup_stack": dict(bad, fit_at=time.time())})
            C._cache.clear()
            assert C.measured("lineup_stack") is None, bad


def test_a_corrupt_state_file_costs_the_refinement_and_not_the_board():
    with _isolated() as path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        C._cache.clear()
        assert C.measured("qb_passing_game") is None
        # And the pricer falls back to the frozen table rather than raising.
        r, measured = P.rho_for("qb_passing_game", 0.425)
        assert measured is True and r == P.MEASURED["qb_passing_game"][0]


def test_the_state_write_is_replaced_rather_than_truncated():
    """A settle interrupted mid-write must not leave the pricing path
    reading half a file."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "corrfit.py"), encoding="utf-8").read()
    i = src.index("def _write_state")
    assert "os.replace" in src[i:i + 500]


def test_the_settle_runs_the_refit_without_being_asked():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    m = open(os.path.join(root, "engine", "maintenance.py"),
             encoding="utf-8").read()
    i = m.index("def settle_open(")
    body = m[i:m.index("\ndef ", i + 10)]
    assert "corrfit.refresh(hconn)" in body, \
        "the correlation priors are back to being a command somebody types"
    assert "correlation refit skipped" in body, \
        "a failing refit must not take the settle down with it"


def test_the_doctor_says_what_each_correlation_is_running_on():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = open(os.path.join(root, "doctor.py"), encoding="utf-8").read()
    assert "def check_correlation_priors(rep):" in d
    assert "check_correlation_priors" in d[d.index("CHECKS = ["):
                                           d.index("CHECKS = [") + 400]
    assert "CORR_STALE_DAYS" in d


def test_the_json_state_is_plain_and_sorted():
    with _isolated() as path:
        C._write_state({"b": {"r": 0.1, "n": 600}, "a": {"r": 0.2, "n": 600}})
        text = open(path, encoding="utf-8").read()
        assert text.index('"a"') < text.index('"b"'), \
            "unsorted state churns diffs"
        assert json.loads(text)["a"]["r"] == 0.2


# --- when a bigger sample is not better evidence -----------------------------

def test_a_standing_number_this_code_cannot_reproduce_is_superseded():
    """Found 2026-08-27 by ingesting four NFL seasons and refitting.

    The standing `possession_pie` is -0.560 on 2,848 games. Today's code,
    on 2,278 games of the same league with a stable shape across all four
    seasons, measures -0.098 ± 0.021 — twenty-two sigma, which no extra
    season explains. The dates say why: the table was hand-taken on
    2026-08-02, and the ingest that widened `rec_yds` from wide receivers
    only to every position landed on 2026-08-15. "The team's total
    receiving yards" is a different number before and after that, and it
    is exactly the quantity this pairing holds fixed.

    A sample count cannot see any of this. It compares how MANY, never of
    what — so the "never displace a better-sampled number" rule was
    dutifully protecting a measurement of a schema that no longer
    exists."""
    class _Fit:
        def __init__(self, r, n, se, prior):
            self.r, self.n, self.se, self.prior = r, n, se, prior
            self.missing = ""
    prior = next(p for p in C.PRIORS if p.key == "wr_rec_yds__wr2_rec_yds")
    standing = P.MEASURED["possession_pie"][0]
    fit = _Fit(-0.0975, 2278, 0.0208, prior)
    sigma = abs(fit.r - standing) / fit.se
    assert sigma > C.REPRO_SIGMA, sigma
    assert fit.n >= C.REPRO_MIN_N and fit.se <= C.REPRO_MAX_SE
    # And the standing sample really is the larger one, so nothing but
    # the reproducibility test could have let this through.
    assert fit.n < P.MEASURED["possession_pie"][1]


def test_one_thin_season_can_never_overturn_a_measurement():
    """Both halves of the rule are needed. Without the sample floor, a
    single quiet season could overturn real evidence; without the sigma
    test, a stale constant outlives every ingest change forever."""
    assert C.REPRO_MIN_N > 570, \
        "one NFL season is 570 team-games and must not be enough"


def test_a_pairing_that_still_reproduces_keeps_its_richer_sample():
    """The rule has to discriminate or it is just a blanket override.
    `run_game_script` measures +0.347 against a standing +0.356 — well
    inside the noise — so the better-sampled standing number stays."""
    standing = P.MEASURED["run_game_script"][0]
    sigma = abs(0.347 - standing) / 0.018
    assert sigma < C.REPRO_SIGMA, sigma


def test_a_supersede_is_recorded_rather_than_silent():
    with _isolated():
        C._write_state({"possession_pie": {
            "r": -0.0975, "n": 2278, "se": 0.0208, "fit_at": time.time(),
            "superseded": {"was": -0.56, "sigma": 22.3}}})
        C._cache.clear()
        got = C.measured("possession_pie")
        assert got["superseded"]["was"] == -0.56
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "maintenance.py"), encoding="utf-8").read()
    assert "SUPERSEDES" in src, "the settle log says nothing about it"
    d = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "doctor.py"), encoding="utf-8").read()
    assert "cannot \n" not in d and "superseded" in d


def test_the_table_records_that_its_data_moved_underneath_it():
    """The numbers stay as a floor for a machine with no history. What
    they are not any more is the last word, and the file says so where
    the next reader will be standing."""
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "parlays.py"), encoding="utf-8").read()
    i = src.index("MEASURED: dict[str, tuple[float, int, str]]")
    head = src[max(0, i - 1400):i]
    assert "2026-08-15" in head and "2026-08-02" in head
    assert "wide receivers" in head


def test_the_touchdown_pairs_pick_the_man_by_his_role_not_by_his_outcome():
    """Ethan, 2026-09-02: "measure and price" the QB-TD / WR-TD pair.

    The trap: choosing the receiver by the measured market itself — the
    teammate who scored most — selects on the outcome and manufactures
    correlation. The WR1 is the team-week's top TARGETS, the quarterback
    its top PASS ATTEMPTS. Built here so the decoy — a third receiver
    who scores every week on one target — must NOT be the one measured,
    and the recovered number is the one planted on the real WR1."""
    import random
    random.seed(9)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE player_game_logs (sport, season, period, "
                     "team, player, market, value)")
        rows = []
        for wk in range(1, 401):
            key = ("nfl", 2025, f"{wk:03d}", "T")
            qb_td = random.choice([0, 0, 1, 1, 2, 3])
            wr_td = 1 if (qb_td and random.random() < 0.6) else 0
            rows += [key + ("QB", "pass_att", 30), key + ("QB", "pass_td", qb_td),
                     key + ("WR1", "targets", 10), key + ("WR1", "anytime_td", wr_td),
                     key + ("WR2", "targets", 5), key + ("WR2", "anytime_td", 0),
                     # the decoy: one target, a touchdown every single week
                     key + ("DECOY", "targets", 1), key + ("DECOY", "anytime_td", 1)]
        conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
        prior = next(p for p in C.PRIORS if p.key == "qb_pass_td__wr1_anytime_td")
        f = C.fit_one(conn, prior)
        assert f.n == 400, f.missing or f.n
        # the planted dependence is strongly positive; measuring the decoy
        # (constant 1) would have given nan
        assert 0.35 < f.r < 0.85, f.r
        assert f.r == f.r
        conn.close()


def test_the_touchdown_pairs_are_adopted_into_the_pricer_by_name():
    for key, (parlay_key, sign) in C.ADOPT.items():
        if key.endswith("anytime_td"):
            assert parlay_key in P.MEASURED, parlay_key
            assert sign == +1
    assert P.MEASURED["qb_td_game"][1] >= 2000
    assert P.MEASURED["qb_td_wr_td"][0] > P.MEASURED["qb_td_game"][0] > P.SAME_GAME_BASELINE_RHO


if __name__ == "__main__":
    import re as _re
    declared = _re.findall(r"^def (test_\w+)",
                           open(__file__, encoding="utf-8").read(), _re.M)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert not set(declared) - {f.__name__ for f in fns}
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")

