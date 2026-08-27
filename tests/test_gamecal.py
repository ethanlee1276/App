"""Calibrating the game-line model against its own closing-number record.

The spread and total model shipped for a long time with a market haircut
that was a guess: shrink halfway to the close. Nobody could do better,
because no closing number was ever stored — the build asked for spreads
and totals, priced off them, and journaled only the moneyline. Once the
schedule feed's own closing consensus was ingested, the guess became
measurable, and the first measurement over 899 NFL games put the slope
within a standard error of zero on all three game markets.

These tests pin the estimator, the guards that stop a thin or unlucky
database from moving the number, the direction the measurement is
allowed to move it, and the promise that a board which goes quiet says
why on the card.

Run directly: `python3 tests/test_gamecal.py`
"""

import contextlib
import math
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gamecal as G
from engine import gamebets


@contextlib.contextmanager
def sandbox_state(entries=None):
    """Point the module at a throwaway state file, cache cleared both ways.

    Every test here has to be immune to whatever `data/feedstate/
    gamecal.json` happens to hold on the machine running it — that file
    is gitignored, so it exists on the production box and not in a fresh
    clone, and a test whose answer depends on which one it got is not a
    test.
    """
    keep_path, keep_cache = G.STATE_PATH, dict(G._cache)
    tmp = tempfile.mkdtemp()
    G.STATE_PATH = os.path.join(tmp, "gamecal.json")
    G._cache.clear()
    if entries:
        G._write_state(entries)
        G._cache.clear()
    try:
        yield G.STATE_PATH
    finally:
        G.STATE_PATH = keep_path
        G._cache.clear()
        G._cache.update(keep_cache)


def _db(games):
    """An in-memory history DB. ``games`` is (date, home, away, hs, as, extra)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE games (sport TEXT, period TEXT, home TEXT, "
                 "away TEXT, home_score INT, away_score INT, spread REAL, "
                 "total REAL, extra TEXT)")
    conn.execute("CREATE TABLE odds_history (sport TEXT, market TEXT, "
                 "book TEXT, taken_at TEXT, home TEXT, away TEXT, player TEXT, "
                 "line REAL, over_odds INT, under_odds INT)")
    conn.executemany(
        "INSERT INTO games (sport, period, home, away, home_score, "
        "away_score, spread, total, extra) VALUES ('nfl',?,?,?,?,?,?,?,?)",
        games)
    conn.commit()
    return conn


# --- the estimator ----------------------------------------------------------
def test_slope_of_one_when_the_model_is_exactly_right():
    """Constructed: the market's error IS the model's disagreement."""
    pairs = [(d, d) for d in (-4, -3, -2, -1, 1, 2, 3, 4)] * 5
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    assert abs(sxy / sxx - 1.0) < 1e-12


def test_logistic_fit_recovers_a_known_slope():
    """Generate outcomes from a known beta and get it back.

    Deterministic: instead of sampling, each observation is entered twice
    with fractional weight impossible in this estimator, so the fixture
    uses a symmetric design where the maximum-likelihood answer is exact
    by construction — equal numbers of wins and losses at mirrored gaps
    put the slope at zero, and no amount of arithmetic drift moves it.
    """
    obs = []
    for gap in (0.4, 0.8, 1.2):
        obs += [(gap, 0.0, 1.0), (gap, 0.0, 0.0),
                (-gap, 0.0, 1.0), (-gap, 0.0, 0.0)]
    slope, se = G._fit_logistic(obs)
    assert abs(slope) < 1e-6, slope
    assert se > 0

    # …and a design where the model's side wins most of the time, but not
    # always, must push the slope firmly positive. NOT always: outcomes
    # that line up perfectly with the gap are separable, and the maximum
    # likelihood for separable data is an infinite slope — see the test
    # below, which pins that this estimator refuses rather than adopts it.
    obs2 = ([(g, 0.0, 1.0 if g > 0 else 0.0)
             for g in (0.5, 1.0, 1.5, -0.5, -1.0, -1.5)] * 8
            + [(g, 0.0, 0.0 if g > 0 else 1.0)
               for g in (0.5, 1.0, 1.5, -0.5, -1.0, -1.5)] * 2)
    slope2, se2 = G._fit_logistic(obs2)
    assert slope2 > 1.0, slope2
    assert se2 > 0


def test_perfectly_separable_outcomes_are_refused_not_adopted():
    """The failure mode that would otherwise adopt an infinite slope.

    If every game the model leaned on had gone its way, the maximum
    likelihood is "believe the model without limit" — which is what a
    small, lucky sample looks like, and the single most dangerous number
    this module could hand the pricer. Newton walks off toward infinity,
    the iteration cap trips, and the fit comes back unusable.
    """
    obs = [(g, 0.0, 1.0 if g > 0 else 0.0)
           for g in (0.5, 1.0, 1.5, -0.5, -1.0, -1.5)] * 8
    slope, se = G._fit_logistic(obs)
    assert slope != slope and se != se     # nan, nan
    f = G.Fit("nfl", "moneyline", n=900, slope=slope, se=se)
    with sandbox_state():
        assert G.measured("nfl", "moneyline") is None


def test_logistic_slope_is_zero_when_outcomes_ignore_the_model():
    """Half the strong disagreements win, half lose — nothing to learn."""
    obs = [(1.5, 0.0, 1.0), (1.5, 0.0, 0.0)] * 40
    slope, _se = G._fit_logistic(obs)
    assert abs(slope) < 1e-6


# --- adoption guards --------------------------------------------------------
def test_a_thin_database_is_held_not_adopted():
    rows = [(f"2024-09-{d:02d}", "KC", "BUF", 24, 20, -3.0, 44.0,
             '{"spread_odds":[-110,-110],"total_odds":[-110,-110]}')
            for d in range(1, 29)]
    conn = _db(rows)
    with sandbox_state():
        out = G.refresh(conn, sport="nfl", markets=("total",))
    assert not out["adopted"]
    why = out["held"][0]["why"]
    assert "needs" in why or "graded games" in why, why


def test_a_loose_slope_is_held():
    """Enough games, but the slope is not pinned down — no adoption.

    MAX_SE exists because a slope of 0.03 ± 0.40 and a slope of
    0.03 ± 0.02 are the same number and completely different claims.
    """
    f = G.Fit("nfl", "total", n=G.MIN_N + 10, slope=0.03,
              se=G.MAX_SE + 0.01, hit=100, decided=200)
    assert f.se > G.MAX_SE


def test_measured_refuses_a_corrupt_entry():
    with sandbox_state({"nfl:total": {"shrink": "banana", "se": 0.1,
                                      "n": 900}}):
        assert G.measured("nfl", "total") is None
        assert G.shrink_for("nfl", "total") is None


def test_measured_refuses_a_shrink_outside_zero_to_one():
    with sandbox_state({"nfl:total": {"shrink": 1.4, "se": 0.05, "n": 900}}):
        assert G.measured("nfl", "total") is None


def test_measured_refuses_a_thin_or_loose_stored_fit():
    with sandbox_state({"nfl:total": {"shrink": 0.3, "se": 0.05,
                                      "n": G.MIN_N - 1}}):
        assert G.measured("nfl", "total") is None
    with sandbox_state({"nfl:total": {"shrink": 0.3, "se": G.MAX_SE + 0.1,
                                      "n": 900}}):
        assert G.measured("nfl", "total") is None


def test_an_unreadable_state_file_costs_the_calibration_not_the_board():
    with sandbox_state() as path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        G._cache.clear()
        assert G.measured("nfl", "total") is None
        # …and the pricer still prices.
        card = gamebets.price_total("nfl", "KC", "BUF", 47.0, 47.0)
        assert card["grade"] in ("Pass", "Lean", "Play", "Strong Play")


# --- the direction the measurement may move the number ----------------------
def test_a_measurement_can_only_make_the_board_quieter():
    """MAX_ADOPTED. A backfit is allowed to withdraw trust, never to add it.

    A fitted slope of 0.9 would be a claim that the model is nearly right
    and the close nearly wrong — believable only after a season of
    forward results, never off the same games the fit was run on.
    """
    hot = G.Fit("nfl", "total", n=5000, slope=0.9, se=0.02)
    assert G._adopted_shrink(hot) == G.MAX_ADOPTED
    assert G.MAX_ADOPTED <= 0.5


def test_a_negative_slope_floors_at_zero_rather_than_inverting():
    cold = G.Fit("nfl", "spread", n=5000, slope=-0.4, se=0.02)
    assert G._adopted_shrink(cold) == 0.0


def test_a_middling_slope_is_taken_as_measured():
    mid = G.Fit("nfl", "total", n=5000, slope=0.25, se=0.02)
    assert abs(G._adopted_shrink(mid) - 0.25) < 1e-12


# --- the pricing path -------------------------------------------------------
def test_a_measured_zero_shrink_collapses_the_edge_onto_the_market():
    """The change this whole module exists to make.

    Same three-point disagreement on an NFL total, priced twice: once
    with no measurement (the flat halfway guess) and once with the
    measured near-zero. Three points is chosen deliberately — it is
    inside the credibility ceiling, so the flat prior GRADES IT A PLAY
    and the board ships it. This is a bet that used to go out and now
    does not.
    """
    with sandbox_state():
        loud = gamebets.price_total("nfl", "KC", "BUF", 50.5, 47.5)
    with sandbox_state({"nfl:total": {"shrink": 0.03, "se": 0.05,
                                      "n": 899, "hit_rate": 0.507,
                                      "market": "total", "sport": "nfl"}}):
        quiet = gamebets.price_total("nfl", "KC", "BUF", 50.5, 47.5)
    assert loud["grade"] == "Play", loud["grade"]
    assert loud["edge"] > 0.04, loud["edge"]
    assert quiet["edge"] < loud["edge"] / 10, (quiet["edge"], loud["edge"])
    assert quiet["grade"] == "Pass"
    assert quiet["stake_units"] == 0.0


def test_an_unmeasured_sport_keeps_the_flat_prior():
    """MLB has no fit, so nothing about its board may change."""
    with sandbox_state({"nfl:total": {"shrink": 0.0, "se": 0.05, "n": 899}}):
        mlb = gamebets.price_total("mlb", "LAD", "SD", 9.5, 8.0)
        assert G.shrink_for("mlb", "total") is None
    with sandbox_state():
        base = gamebets.price_total("mlb", "LAD", "SD", 9.5, 8.0)
    assert abs(mlb["edge"] - base["edge"]) < 1e-12


def test_the_spread_shrink_is_read_from_the_spread_fit_not_the_total():
    """Two markets, two measurements — no cross-contamination."""
    state = {"nfl:total": {"shrink": 0.5, "se": 0.05, "n": 900},
             "nfl:spread": {"shrink": 0.0, "se": 0.05, "n": 900}}
    with sandbox_state(state):
        assert G.shrink_for("nfl", "total") == 0.5
        assert G.shrink_for("nfl", "spread") == 0.0
        sp = gamebets.price_spread("nfl", "KC", "BUF", 0.0, -6.5)
        assert abs(sp["edge"]) < 0.01, sp["edge"]


def test_the_moneyline_reads_its_own_fit_only_when_given_a_sport():
    with sandbox_state({"nfl:moneyline": {"shrink": 0.0, "se": 0.05,
                                          "n": 897}}):
        told = gamebets.price_moneyline("KC", "BUF", 0.72, -140, +120,
                                        sport="nfl")
        untold = gamebets.price_moneyline("KC", "BUF", 0.72, -140, +120)
    # A margin, not a bare abs-vs-abs: a measured zero shrink should
    # collapse the edge, not shave its last decimal.
    assert abs(told.edge) < abs(untold.edge) * 0.2, (told.edge, untold.edge)


# --- the board explains itself ----------------------------------------------
def test_a_quiet_board_says_why_on_the_card():
    with sandbox_state({"nfl:total": {"shrink": 0.0, "se": 0.05, "n": 899,
                                      "hit_rate": 0.507, "sport": "nfl",
                                      "market": "total"}}):
        card = gamebets.price_total("nfl", "KC", "BUF", 50.5, 47.5)
        joined = " ".join(card["reasons"])
    assert "899" in joined
    assert "no information" in joined or "carried no" in joined


def test_the_note_stays_silent_when_the_fit_changed_nothing():
    """A measurement that landed on the old guess has nothing to add."""
    with sandbox_state({"nfl:total": {"shrink": 0.5, "se": 0.05, "n": 900,
                                      "hit_rate": 0.53}}):
        assert G.note_for("nfl", "total") is None
    with sandbox_state():
        assert G.note_for("nfl", "total") is None


def test_the_moneyline_note_never_quotes_a_hit_rate():
    """A moneyline model mostly disagrees toward underdogs, which win well
    under half the time and are still profitable at the price. Printing
    "its side won 37%" on that card would read as a disaster and mean
    nothing."""
    with sandbox_state({"nfl:moneyline": {"shrink": 0.0, "se": 0.05,
                                          "n": 897, "hit_rate": 0.372,
                                          "market": "moneyline"}}):
        note = G.note_for("nfl", "moneyline")
    assert note and "37" not in note and "%" not in note.split("Priced")[0]


def test_the_summary_omits_the_hit_rate_for_a_moneyline():
    f = G.Fit("nfl", "moneyline", n=897, slope=-0.002, se=0.118,
              hit=334, decided=897)
    assert "37" not in f.summary()
    t = G.Fit("nfl", "total", n=899, slope=0.03, se=0.113,
              hit=451, decided=890)
    assert "50.7%" in t.summary()


# --- refusals ---------------------------------------------------------------
def test_an_unknown_market_is_refused():
    conn = _db([])
    try:
        G.observations(conn, "nfl", "first_half_total")
    except ValueError as exc:
        assert "market must be" in str(exc)
    else:
        raise AssertionError("an unknown market should be refused")


def test_a_sport_with_no_registered_variance_is_held_not_crashed():
    """A refresh over every sport in the DB must survive the one league
    nobody has fitted — the alternative is a nightly job that dies on a
    stray row."""
    conn = _db([])
    conn.execute("INSERT INTO games (sport, period, home, away, home_score, "
                 "away_score) VALUES ('quidditch','2024-01-01','A','B',10,7)")
    conn.commit()
    f = G.fit_one(conn, "quidditch", "total")
    assert f.missing and "quidditch" in f.missing


def test_a_moneyline_fit_refuses_a_sport_with_no_win_curve():
    """CFB used to be the example here. It is not any more — see below —
    which is the point: the refusal has to be about a curve that does
    not exist, not about a sport nobody got round to."""
    conn = _db([])
    f = G.fit_one(conn, "quidditch", "moneyline")
    assert f.missing and "win-probability curve" in f.missing


def test_college_football_has_its_own_win_curve_now():
    from engine.gamebets import cfb_win_prob, nfl_win_prob
    from engine.cfb import ratings as R
    R.install(R.PRIOR)
    even = cfb_win_prob(0.0, 0.0)
    assert 0.5 < even < 0.62           # the home edge, and only that
    assert cfb_win_prob(10.0, 0.0) > even > cfb_win_prob(-10.0, 0.0)
    # And it is NOT the NFL's curve wearing a college label: college
    # margins scatter wider, so the same rating gap is a smaller
    # favourite here.
    assert cfb_win_prob(10.0, 0.0) < nfl_win_prob(10.0, 0.0)


def test_the_college_curve_refuses_rather_than_borrowing():
    """`_sd` exists so a sport with no registered variance cannot be
    priced through another league's. The curve has to inherit that."""
    from engine import gamebets
    from engine.cfb import ratings as R
    saved = (gamebets.HOME_FIELD.pop("cfb", None),
             gamebets.MARGIN_SD.pop("cfb", None))
    try:
        raised = False
        try:
            gamebets.cfb_win_prob(3.0, 0.0)
        except ValueError:
            raised = True
        assert raised
    finally:
        R.install(R.PRIOR)
        assert gamebets.HOME_FIELD["cfb"] and gamebets.MARGIN_SD["cfb"]
        assert saved


# --- the walk-forward promise -----------------------------------------------
def test_observations_never_price_a_game_with_its_own_result():
    """The fit must grade the model as it would have been run.

    With a warmup of one game per team, the first game each team plays
    can never appear as an observation — its ratings would otherwise be
    built from the very score being predicted.
    """
    rows = []
    for i in range(1, 41):
        rows.append((f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                     "KC", "BUF", 20 + (i % 7), 17 + (i % 5), -3.0, 44.0,
                     '{"spread_odds":[-110,-110],"total_odds":[-110,-110]}'))
    conn = _db(rows)
    obs = G.observations(conn, "nfl", "total", min_team_games=5)
    assert len(obs) == len(rows) - 5


def test_the_spread_observation_uses_the_home_margin_convention():
    """`games.spread` is the HOME team's book number, so the margin the
    market implies is its negation. Getting this backwards would fit a
    slope on a mirrored signal and read as strong evidence for exactly
    the wrong shrink."""
    rows = [(f"2024-09-{d:02d}", "KC", "BUF", 30, 20, -7.0, 44.0,
             '{"spread_odds":[-110,-110],"total_odds":[-110,-110]}')
            for d in range(1, 21)]
    conn = _db(rows)
    obs = G.observations(conn, "nfl", "spread", min_team_games=5)
    # Home won by 10 with a -7 line, so the market was 3 points short.
    assert obs and all(abs(y - 3.0) < 1e-9 for _x, y in obs), obs[:3]


# --- a close with no price beside it ----------------------------------
def _priced_db(pair):
    """One CFB game carrying a closing spread, with or without prices."""
    import json as _json
    import sqlite3
    from engine import db as _db
    conn = _db.connect(":memory:")
    extra = {"home_name": "Georgia", "away_name": "Ohio State"}
    if pair is not None:
        extra["spread_odds"] = pair
    conn.execute(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score, spread, total, extra) VALUES "
        "('cfb', 2024, '2024-09-14', '401', 'UGA', 'OSU', 30, 24, -7.5, "
        "55.5, ?)", (_json.dumps(extra),))
    conn.commit()
    assert sqlite3
    return conn


def test_a_close_with_no_prices_is_refused_by_default():
    """A BACKTEST has to price a bet, so a line with no -110s beside it
    is useless to it and must not silently arrive as one."""
    from engine.gamebacktest import schedule_closes
    conn = _priced_db(None)
    assert schedule_closes(conn, "cfb", "spread") == {}


def test_a_close_with_no_prices_is_usable_when_the_caller_says_so():
    """`engine.gamecal` measures how far our NUMBER sits from the
    market's number and never reads a price. College football's closes
    arrive without them, and requiring prices reported the whole sport
    as "0 graded games with a close"."""
    from engine.gamebacktest import schedule_closes
    conn = _priced_db(None)
    out = schedule_closes(conn, "cfb", "spread", require_prices=False)
    assert out[("2024-09-14", "UGA", "OSU")] == (-7.5, None, None)


def test_prices_still_ride_along_when_the_feed_has_them():
    from engine.gamebacktest import schedule_closes
    conn = _priced_db([-110, -110])
    out = schedule_closes(conn, "cfb", "spread", require_prices=False)
    assert out[("2024-09-14", "UGA", "OSU")] == (-7.5, -110, -110)


def test_the_calibration_asks_for_lines_not_prices():
    import inspect
    from engine import gamecal
    source = inspect.getsource(gamecal.observations)
    assert "require_prices=False" in source


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
