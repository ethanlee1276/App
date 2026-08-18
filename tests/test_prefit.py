"""Does preseason starter usage move a preseason result? The measurement.

Ethan, 2026-08-14, to the offer to fit August before pricing it: "yes do
this now too".

THE POINT OF THIS FILE IS THAT THE BAR CANNOT MOVE. `MIN_ROWS`, `MAX_P`
and `MIN_SIGNAL_POINTS` are constants declared above the answer in
`engine/nfl/prefit`, and the tests below pin both the numbers and the two
things that would quietly defeat them:

  * the FORECAST inputs may only see earlier seasons. A tendency computed
    over the season it predicts is not a forecast, it is a lookup, and it
    would convict every time;
  * the walk-forward may never fit on the season it scores.

Both are tested against a database where a team's habit deliberately
CHANGES year to year, so a leak has a different value than the honest
answer and cannot hide behind a coincidence.

AND CONVICTION IS NOT PERMISSION. `prices_allowed` is False in every
state, including the one where the effect is real, because "the effect
exists" and "the book missed it" are different claims and only the first
is measurable from what we hold.
"""

import json
import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.nfl import prefit as pf                           # noqa: E402

TEAMS = [f"T{i:02d}" for i in range(32)]
SEASONS = (2021, 2022, 2023, 2024, 2025)


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE player_game_logs (sport TEXT, season INT,
        week TEXT, player TEXT, team TEXT, position TEXT, market TEXT,
        value REAL)""")
    c.execute("""CREATE TABLE preseason_player_logs (sport TEXT, season INT,
        week INT, game_id TEXT, player TEXT, team TEXT, opponent TEXT,
        position TEXT, home INT, market TEXT, value REAL)""")
    c.execute("""CREATE TABLE preseason_games (sport TEXT, season INT,
        week INT, game_id TEXT, date TEXT, home TEXT, away TEXT,
        home_score REAL, away_score REAL, completed INT, venue TEXT)""")
    return c


def _roles(c, season):
    """Regular-season snaps and attempts, so every team has a named QB."""
    for t in TEAMS:
        for g in range(8):
            c.execute("INSERT INTO player_game_logs VALUES "
                      "('nfl',?,?,?,?,?,?,?)",
                      (season - 1, str(g), f"QB_{t}", t, "QB", "snap_pct", .95))
        c.execute("INSERT INTO player_game_logs VALUES ('nfl',?,?,?,?,?,?,?)",
                  (season - 1, "1", f"QB_{t}", t, "QB", "pass_att", 400))


def _game(c, gid, season, week, home, away, ha, aa, total):
    for team, att in ((home, ha), (away, aa)):
        c.execute("INSERT INTO preseason_player_logs VALUES "
                  "('nfl',?,?,?,?,?,'X','QB',1,'pass_att',?)",
                  (season, week, str(gid), f"QB_{team}", team, att))
    hs = round(total / 2)
    c.execute("INSERT INTO preseason_games VALUES ('nfl',?,?,?,?,?,?,?,?,1,'V')",
              (season, week, str(gid), f"{season}-08-{10 + week:02d}",
               home, away, hs, round(total) - hs))


def _seasons_db(beta: float, seed: int = 11):
    """Five Augusts where the total is ``20 + beta*(attempts) + noise``.

    Each team has a STABLE habit plus per-game jitter, which is what makes
    a tendency forecastable at all — and each habit is redrawn per season
    in `_drifting_db` below, which is what makes a leak visible.
    """
    c = _db()
    rng = random.Random(seed)
    habit = {t: max(0.0, rng.gauss(10, 5)) for t in TEAMS}
    gid = 0
    for season in SEASONS:
        _roles(c, season)
        for week in (1, 2, 3):
            order = TEAMS[:]
            rng.shuffle(order)
            for i in range(0, 32, 2):
                home, away = order[i], order[i + 1]
                gid += 1
                ha = max(0, round(rng.gauss(habit[home], 3)))
                aa = max(0, round(rng.gauss(habit[away], 3)))
                _game(c, gid, season, week, home, away, ha, aa,
                      20 + beta * (ha + aa) + rng.gauss(0, 9))
    c.commit()
    return c


REAL = _seasons_db(0.5)          # a planted, bettable-sized effect
NULL = _seasons_db(0.0)          # attempts tell you nothing

#: Four thousand permutations across four pairs is a second and a half a
#: run, and half a dozen tests want the same two reports. Computed once.
_CACHE: dict = {}


def _fit(conn):
    key = id(conn)
    if key not in _CACHE:
        _CACHE[key] = pf.fit(conn)
    return _CACHE[key]


# --- the bar, and that it is above the answer -------------------------------
def test_the_bar_is_three_named_constants():
    assert pf.MIN_ROWS >= 60 and 0 < pf.MAX_P <= 0.01
    assert pf.MIN_SIGNAL_POINTS >= 1.0


def test_the_bar_is_declared_before_any_result_can_exist():
    """A threshold defined after the measurement is a threshold that got
    to see the answer. These sit at module scope, above every function."""
    src = open(os.path.join(ROOT, "engine", "nfl", "prefit.py"),
               encoding="utf-8").read()
    first_def = src.index("\ndef ")
    for name in ("MIN_ROWS", "MAX_P", "MIN_SIGNAL_POINTS"):
        assert src.index(f"\n{name} = ") < first_def, name


def test_the_tested_pairs_are_fixed_not_chosen():
    """Two predictors against two outcomes, named in the source. Picking
    the pair that came back best is how a null becomes a discovery."""
    assert pf.PAIRS == (("att_sum", "total"), ("att_gap", "margin"))


def test_p_is_stricter_than_the_usual_five_percent():
    """Four (predictor, outcome) tests run across the two questions. One
    of them landing under 0.05 is the null behaving exactly as expected."""
    assert pf.MAX_P <= 0.01


# --- the sample -------------------------------------------------------------
def test_only_played_games_join():
    c = _db()
    _roles(c, 2025)
    c.execute("INSERT INTO preseason_games VALUES "
              "('nfl',2025,2,'g1','2025-08-12','T00','T01',NULL,NULL,0,'V')")
    assert pf.finals(c) == []


def test_a_missing_table_is_survivable():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    assert pf.finals(c) == [] and pf.sample(c) == []
    rep = pf.fit(c)
    assert rep["n"] == 0 and rep["verdict"] == "insufficient"


def test_a_game_with_no_box_score_is_dropped_not_zeroed():
    """Zero attempts is a coach resting his starter. An absent box score is
    a game we did not ingest. Averaging the second into the first
    manufactures rests that never happened."""
    c = _db()
    _roles(c, 2025)
    c.execute("INSERT INTO preseason_games VALUES "
              "('nfl',2025,2,'g1','2025-08-12','T00','T01',20,17,1,'V')")
    assert pf.sample(c) == []


def test_the_sample_carries_both_the_outcome_and_the_usage():
    rows = pf.sample(REAL)
    assert len(rows) == 240
    r = rows[0]
    for k in ("total", "margin", "att_sum", "att_gap", "exp_sum", "exp_gap"):
        assert k in r


# --- leakage, which is the failure that would convict every time ------------
def _drifting_db():
    """A league whose habits are redrawn EVERY season.

    That is the point: an honest forecast for 2024 knows only 2021-2023, so
    it cannot land on 2024's own number. A leak can, and the two answers
    are far apart rather than coincidentally close.
    """
    c = _db()
    rng = random.Random(5)
    gid = 0
    per_season = {}
    for season in SEASONS:
        _roles(c, season)
        per_season[season] = {t: float(rng.randrange(0, 30)) for t in TEAMS}
        for week in (1, 2, 3):
            order = TEAMS[:]
            rng.shuffle(order)
            for i in range(0, 32, 2):
                home, away = order[i], order[i + 1]
                gid += 1
                _game(c, gid, season, week, home, away,
                      per_season[season][home], per_season[season][away], 40)
    c.commit()
    return c, per_season


def test_the_forecast_input_never_sees_its_own_season():
    c, per = _drifting_db()
    rows = pf.sample(c)
    for r in rows:
        if r["exp_home"] is None:
            continue
        prior = [per[s][r["home"]] for s in SEASONS if s < r["season"]]
        assert abs(r["exp_home"] - round(sum(prior) / len(prior), 1)) < 0.05, r
        # And it is NOT this season's own number, which is what a leak
        # would produce.
        if len(set(prior)) > 1 or prior[0] != per[r["season"]][r["home"]]:
            assert abs(r["exp_home"] - per[r["season"]][r["home"]]) > 1e-9


def test_the_earliest_season_has_no_forecast_at_all():
    """Nothing came before it. None, not a zero and not this year's own
    attempts."""
    rows = [r for r in pf.sample(REAL) if r["season"] == min(SEASONS)]
    assert rows and all(r["exp_sum"] is None for r in rows)


def test_the_walk_forward_never_fits_on_what_it_scores():
    wf = pf.walk_forward(pf.sample(REAL), "exp_sum", "total")
    # 2021 has no exp_*; 2022 is the first with one and has nothing prior
    # to fit on, so scoring starts in 2023.
    assert min(wf["seasons_scored"]) >= 2023
    assert max(wf["seasons_scored"]) == max(SEASONS)


# --- the arithmetic ---------------------------------------------------------
def test_pearson_and_ols_on_a_line():
    xs = [1, 2, 3, 4, 5]
    ys = [3, 5, 7, 9, 11]
    assert abs(pf.pearson(xs, ys) - 1.0) < 1e-9
    b, a = pf.ols(xs, ys)
    assert abs(b - 2) < 1e-9 and abs(a - 1) < 1e-9


def test_a_column_with_no_spread_has_no_correlation():
    assert pf.pearson([4, 4, 4, 4], [1, 2, 3, 4]) is None
    assert pf.ols([4, 4], [1, 2]) is None


def test_the_permutation_p_is_the_same_twice():
    """A p-value that wobbles between runs is one somebody re-rolls until
    it passes."""
    xs = [i for i in range(60)]
    ys = [i * 0.5 + (i % 7) for i in range(60)]
    assert pf.permutation_p(xs, ys, 400) == pf.permutation_p(xs, ys, 400)


def test_the_permutation_p_can_never_be_zero():
    xs = list(range(60))
    assert pf.permutation_p(xs, xs, 200) > 0


def test_signal_points_reads_negative_when_the_model_hurts():
    """A model worse than the league mean should look worse, not clamp to
    nothing and read as harmless."""
    assert pf.signal_points(10.0, 11.0) < 0
    assert abs(pf.signal_points(10.0, 6.0) - 8.0) < 1e-9


# --- a dead column is not a finding -----------------------------------------
def _flat_db():
    """Every starting quarterback threw exactly zero attempts.

    Which is what the table actually held on 2026-08-14: `pass_att` was
    missing from the preseason box parser's market list, so `qb_att` was
    0.0 for all 203 joined games.
    """
    c = _db()
    rng = random.Random(3)
    gid = 0
    for season in SEASONS:
        _roles(c, season)
        for week in (1, 2, 3):
            order = TEAMS[:]
            rng.shuffle(order)
            for i in range(0, 32, 2):
                gid += 1
                _game(c, gid, season, week, order[i], order[i + 1], 0, 0,
                      38 + rng.gauss(0, 9))
    c.commit()
    return c


FLAT = _flat_db()


def test_a_predictor_that_never_moved_is_named_as_such():
    rep = _fit(FLAT)
    assert rep["n"] >= pf.MIN_ROWS
    assert "att_sum~total" in rep["dead"]
    assert rep["mechanism"]["pairs"]["att_sum~total"]["distinct_x"] == 1


def test_a_dead_column_can_never_read_as_a_negative_result():
    """THE ONE THIS FILE EXISTS FOR AFTER 2026-08-14. The first real run
    returned 203 joined games and said "starter usage does not predict an
    August result". The truth was that starter usage had never been
    measured — the column was all zeros. A finding and a data fault must
    never produce the same output."""
    assert pf.verdict(_fit(FLAT)) == "unmeasurable"
    assert pf.verdict(_fit(FLAT)) != "no"


def test_the_explanation_sends_you_at_the_data_not_at_the_league():
    text = pf.explain(_fit(FLAT))
    assert "NOTHING was measured" in text
    assert "ingest.py nflpre" in text
    assert "does not predict" not in text


def test_a_small_sample_is_insufficient_rather_than_dead():
    """A constant is only diagnosable at scale. Four games where both
    staffs happened to throw five times is a coincidence, and calling it a
    broken feed would print "your data is empty" at a page whose real
    problem is that August has barely started."""
    c = _db()
    _roles(c, 2025)
    for gid in range(4):
        _game(c, gid, 2025, 2, TEAMS[gid * 2], TEAMS[gid * 2 + 1], 5, 5, 40)
    c.commit()
    rep = pf.fit(c)
    assert rep["dead"] == [] and rep["verdict"] == "insufficient"


def test_a_real_null_is_still_allowed_to_say_no():
    """The guard must not swallow honest negatives — that would make the
    whole measurement unable to return its most likely answer."""
    assert pf.dead_predictors(_fit(NULL)) == []
    assert pf.verdict(_fit(NULL)) == "no"


def test_the_probe_leads_with_the_fault_rather_than_the_table():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def show_prefit(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert 'rep.get("dead")' in body
    assert body.index('rep.get("dead")') < body.index("A. MECHANISM")


def test_the_verdict_reaches_disk_on_every_branch_that_reached_one():
    """An "unmeasurable" that never got written would leave the card
    saying "not measured yet" — the wrong half of the truth. It WAS run,
    and it could not answer."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def show_prefit(")
    body = src[i:src.index("\ndef ", i + 1)]
    # The write is atomic since 2026-08-18 (tmp + replace — the page
    # polls this file), so the pin is the replace landing on `out`.
    assert body.index("os.replace(_ptmp, out)") < body.index('rep.get("dead")')


def test_the_card_separates_the_two_negatives_too():
    """The same distinction the explanation makes has to survive the trip
    to the page, or the terminal and the board disagree about what was
    found."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function preseasonFitHTML(")
    body = app[i:app.index("\n}", i)]
    assert "f.noisy" in body and "cannot resolve it" in body
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    j = src.index("def refresh_preseason(")
    ref = src[j:src.index("\ndef ", j + 1)]
    assert 'limited_by") == ["significance"]' in ref


def test_the_card_says_it_could_not_run_rather_than_going_quiet():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function preseasonFitHTML(")
    body = app[i:app.index("\n}", i)]
    assert '"unmeasurable"' in body
    assert "could not run" in body


# --- one line, one sample ---------------------------------------------------
def test_the_p_and_the_rmse_describe_the_same_rows():
    """THE REPORTING DEFECT FOUND ON THE FIRST REAL RESULT. The p was
    computed over every row carrying a forecast input; the RMSE beside it
    over the smaller subset a walk-forward could actually score — 154
    against 105 on Ethan's data — and the two were printed on one line as
    though they were one measurement. Neither number was wrong; the line
    was."""
    rows = pf.sample(REAL)
    wf = pf.walk_forward(rows, "exp_sum", "total")
    scored = [r for r in rows
              if r["season"] in wf["seasons_scored"] and r["exp_sum"] is not None]
    assert wf["n"] == len(scored)
    # And the correlation reported is that same set's, not the wider one.
    wide = [r for r in rows if r.get("exp_sum") is not None]
    assert len(wide) > wf["n"], "fixture no longer exercises the difference"
    exact = pf.pearson([r["exp_sum"] for r in scored],
                       [r["total"] for r in scored])
    assert abs(wf["r"] - exact) < 1e-4         # the report rounds to 4dp
    # The wider set gives a DIFFERENT number, which is what makes this a
    # real check rather than an arithmetic identity.
    assert abs(pf.pearson([r["exp_sum"] for r in wide],
                          [r["total"] for r in wide]) - exact) > 1e-4


# --- what kind of "no" -------------------------------------------------------
def test_the_two_bars_are_reported_separately():
    assert pf.limited_by({"signal_points": 5.0, "p": 0.5}) == ["significance"]
    assert pf.limited_by({"signal_points": 0.1, "p": 0.001}) == ["effect"]
    assert pf.limited_by({"signal_points": 0.1, "p": 0.5}) == ["effect",
                                                               "significance"]
    assert pf.limited_by({"signal_points": 5.0, "p": 0.001}) == []


def test_the_sample_size_needed_grows_as_the_effect_shrinks():
    big, small = pf.n_for_p(0.40), pf.n_for_p(0.10)
    assert big < small
    # r = 0.10 at p <= 0.01 is a few hundred games; the exact figure is a
    # normal approximation and is not quoted to three digits anywhere.
    assert 500 < small < 800
    assert pf.n_for_p(0.0) is None and pf.n_for_p(None) is None


def test_a_noisy_but_real_effect_is_not_called_absent():
    """"Starter usage does not move an August result" is a claim about
    football. "We cannot tell at 105 games whether it does" is a claim
    about our sample, and only the second is what a p of 0.14 supports.

    This is the exact shape of the real 2026 result: `exp_gap~margin`
    cleared the effect bar and missed only significance."""
    rep = {"n": 200, "seasons": [2022, 2023, 2024, 2025], "verdict": "no",
           "mechanism": {"pairs": {"att_gap~margin": {"p": 0.0047}}},
           "forecast": {"pairs": {"exp_gap~margin": {
               "signal_points": 1.13, "p": 0.138, "n": 105, "r": 0.12,
               "n_for_p": 460, "limited_by": ["significance"]}}}}
    text = pf.explain(rep)
    assert "NOT a demonstration there is none" in text
    assert "460" in text
    assert "does not predict" not in text


def test_a_pair_that_failed_both_bars_gets_the_plain_negative():
    """The guard must not turn every negative into "come back later" — a
    pair that missed the effect AND the significance bar found nothing,
    and the flat sentence is the honest one for it."""
    rep = {"n": 200, "seasons": [2022], "verdict": "no",
           "mechanism": {"pairs": {"att_gap~margin": {"p": 0.001}}},
           "forecast": {"pairs": {"exp_gap~margin": {
               "signal_points": 0.05, "p": 0.62, "n": 105,
               "limited_by": ["effect", "significance"]}}}}
    text = pf.explain(rep)
    assert "does not predict" in text
    assert "NOT a demonstration" not in text
    assert "SETTLED" not in text


def test_a_real_effect_too_small_to_bet_is_reported_as_settled():
    """THE THIRD KIND OF NO, and the one the real 2026 run produced. When
    a pair CLEARS the p bar and its out-of-sample model still cannot beat
    the league mean, nothing failed to be found — the thing was found and
    shown to be too small. That closes the question rather than deferring
    it, and printing the generic "does not predict" line for it understates
    what was established."""
    rep = {"n": 251, "seasons": [2021, 2022, 2023, 2024, 2025, 2026],
           "verdict": "no",
           "mechanism": {"pairs": {"att_gap~margin": {
               "p": 0.0005, "swing": 1.7, "sd_y": 14.1}}},
           "forecast": {"pairs": {"exp_gap~margin": {
               "signal_points": -0.86, "p": 0.0085, "n": 154,
               "limited_by": ["effect"]}}}}
    text = pf.explain(rep)
    assert "SETTLED rather than open" in text
    assert "real and too small" in text
    assert "More Augusts will not change that" in text
    # And it must NOT offer the come-back-later line.
    assert "NOT a demonstration there is none" not in text


def test_the_effect_is_reported_in_the_units_of_the_thing_bet_on():
    """A correlation settles no argument a bettor has. "One SD of the
    predictor moves the answer 1.7 points, against results that scatter
    14" does, and both halves are needed — a swing means nothing without
    the scatter it competes with."""
    m = pf.mechanism(pf.sample(REAL))["pairs"]["att_sum~total"]
    assert m["swing"] > 0 and m["sd_y"] > 0
    xs = [r["att_sum"] for r in pf.sample(REAL)]
    assert abs(m["swing"] - abs(m["slope"]) * pf.stdev(xs)) < 1e-2


def test_a_flat_predictor_has_no_swing_to_report():
    m = pf.mechanism(pf.sample(FLAT))["pairs"]["att_sum~total"]
    assert m["swing"] is None


def test_the_probe_prints_what_it_would_take():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def show_prefit(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert 'lim == ["significance"]' in body and "n_for_p" in body


# --- the verdict ------------------------------------------------------------
def test_too_few_games_is_insufficient_not_no():
    """"We looked and there is nothing" and "we could not look" are
    different sentences and the board prints different things for them."""
    c = _db()
    _roles(c, 2025)
    for gid in range(4):
        _game(c, gid, 2025, 2, TEAMS[gid * 2], TEAMS[gid * 2 + 1], 5, 5, 40)
    c.commit()
    assert pf.fit(c)["verdict"] == "insufficient"


def test_a_null_league_does_not_convict():
    rep = _fit(NULL)
    assert rep["n"] >= pf.MIN_ROWS
    assert rep["verdict"] == "no"


def test_a_planted_effect_does_convict():
    """The machinery has to be able to say yes, or "no" means nothing."""
    rep = _fit(REAL)
    assert rep["verdict"] == "measured"
    fc = rep["forecast"]["pairs"]["exp_sum~total"]
    assert fc["signal_points"] >= pf.MIN_SIGNAL_POINTS
    assert fc["p"] <= pf.MAX_P


def test_a_mechanism_that_fails_kills_the_forecast():
    """Question A uses information no bettor has, so it is the generous
    one. If it cannot find the effect, a verdict built on the weaker
    question is noise that got lucky."""
    rep = {"n": 500,
           "mechanism": {"pairs": {"att_sum~total": {"p": 0.9}}},
           "forecast": {"pairs": {"exp_sum~total":
                                  {"signal_points": 9.0, "p": 0.0001}}}}
    assert pf.verdict(rep) == "no"


# --- conviction is still not permission -------------------------------------
def test_nothing_is_ever_priced_from_here():
    for rep in (_fit(REAL), _fit(NULL), {}, None):
        assert pf.prices_allowed(rep) is False


def test_the_report_contains_no_edge_no_stake_and_no_pick():
    blob = json.dumps(_fit(REAL)).lower()
    for word in ("edge", "stake", "units", "recommend", "hit_prob",
                 "fair_prob", "ev_per_unit"):
        assert word not in blob, f"the fit emitted {word!r}"


def test_the_explanation_matches_the_verdict():
    assert "not enough" not in pf.explain(_fit(REAL))
    assert "does not predict" in pf.explain(_fit(NULL))
    assert "ingest.py nflpre" in pf.explain({"verdict": "insufficient", "n": 3})


def test_a_measured_effect_still_says_it_is_not_priced():
    """The one sentence that has to survive a good result."""
    assert "NOT priced" in pf.explain(_fit(REAL))


# --- the wiring -------------------------------------------------------------
def test_the_probe_exists_and_is_dispatched():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--prefit" in argv' in src and "def show_prefit(" in src


def test_the_probe_says_what_to_run_when_nothing_is_joined():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def show_prefit(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "ingest.py nflpre" in body
    assert "nfl_prefit.json" in body


def test_the_finals_have_somewhere_to_live():
    schema = open(os.path.join(ROOT, "engine", "db.py"),
                  encoding="utf-8").read()
    assert "CREATE TABLE IF NOT EXISTS preseason_games" in schema
    assert "def upsert_preseason_games(" in schema


def test_a_scheduled_row_never_erases_a_stored_final():
    """The scoreboard is re-read every six hours all August and lists games
    that have already finished. ESPN sends no score for anything unplayed;
    letting that write back would erase each final the morning after."""
    from engine import db
    c = _db()
    base = {"sport": "nfl", "season": 2026, "week": 2, "game_id": "g1",
            "date": "2026-08-14", "home": "DET", "away": "MIA",
            "completed": 1, "venue": "V"}
    db.upsert_preseason_games(c, [dict(base, home_score=20, away_score=17)])
    db.upsert_preseason_games(c, [dict(base, home_score=None,
                                       away_score=None, completed=0)])
    row = c.execute("SELECT home_score FROM preseason_games").fetchone()
    assert row[0] == 20


def test_the_ingest_stores_the_finals():
    src = open(os.path.join(ROOT, "engine", "ingest.py"),
               encoding="utf-8").read()
    i = src.index("def ingest_nfl_preseason(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "upsert_preseason_games" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
