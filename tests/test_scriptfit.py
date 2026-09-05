"""The two measurements the within-game tests could not make.

`engine/scriptfit` exists because every earlier check on game script, the
total and opponent defence was run WITHIN a game, where the spread and
the total are constant and therefore cannot separate two players on the
same team. Those factors do two jobs — scale a team between games, split
the equity within one — and this module measures each where it lives.

Three bugs are pinned here by name, because each one produced a clean,
confident, wrong table before it was caught:

  * joining the logs to `games` on game_id (NFL spells one "ARI-001",
    `games` spells it "DAL@TB": zero rows, reads as missing data)
  * keying the lead receiver on `targets` (college has ONE such row in
    the whole table: a 0.000 share and three identical zero scores that
    look like a tie)
  * running the college curve backwards through `script_multiplier`
    (which takes the HOME line and derives the lead itself)

Run directly: `python3 tests/test_scriptfit.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import scriptfit as S                              # noqa: E402
from engine.cfb import tds as C                                # noqa: E402


def _db(sport="nfl", game_id_style="team"):
    """A synthetic season. NOTHING is read off this box — the suite runs
    the same everywhere or it is measuring a machine, not a model."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (sport TEXT, season INT, period TEXT, "
                 "game_id TEXT, home TEXT, away TEXT, home_score REAL, "
                 "away_score REAL, spread REAL, total REAL)")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, "
                 "period TEXT, game_id TEXT, player TEXT, team TEXT, "
                 "opponent TEXT, position TEXT, home INT, market TEXT, "
                 "value REAL)")
    rows, logs = [], []
    # SPREADS ACROSS THE WHOLE RANGE AND A SHARE THAT VARIES WEEK TO
    # WEEK. Both matter: the bands need populating, and a fixture where
    # every game in a band is identical has zero within-band variance, so
    # the chi-square divides by nothing and scores every model 0.0 — a
    # tie that looks like agreement and is actually an empty measurement.
    spreads = (-21.0, -14.0, -7.0, -3.0, 0.0, 3.0, 7.0, 14.0, 21.0)
    for season in (2022, 2023, 2024):
        for week in range(1, 21):
            period = f"{week:03d}"
            for i, spread in enumerate(spreads):
                home = f"H{i}"
                away = f"A{i}"
                rows.append((sport, season, period, f"{away}@{home}", home,
                             away, 24, 20, spread, 47.0))
                for team, opp in ((home, away), (away, home)):
                    # The FAVOURED side's back takes more of its team's
                    # touchdowns — the effect the curve is for — plus a
                    # week-to-week wobble so the bands have variance.
                    lead = -spread if team == home else spread
                    wobble = 1.0 if (week + i) % 3 == 0 else 0.0
                    rb = max(0.0, round(1.0 + lead / 14.0) + wobble)
                    gid = (f"{team}-{period}" if game_id_style == "team"
                           else f"{away}@{home}")
                    for player, pos, td, vol in (
                            (f"{team}-RB1", "RB", rb, 20.0),
                            (f"{team}-RB2", "RB", 0.0, 4.0),
                            (f"{team}-WR1", "WR", 1.0, 9.0),
                            (f"{team}-WR2", "WR", 1.0 - wobble, 3.0)):
                        logs.append((sport, season, period, gid, player, team,
                                     opp, pos, 1, "anytime_td", td))
                        market = "carries" if pos == "RB" else "receptions"
                        logs.append((sport, season, period, gid, player, team,
                                     opp, pos, 1, market, vol))
    conn.executemany("INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.executemany("INSERT INTO player_game_logs VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?)", logs)
    conn.commit()
    return conn


# --- the joins that silently returned nothing -----------------------------
def test_the_logs_join_on_the_team_not_the_game_id():
    """THE BUG THAT READ AS MISSING DATA. The NFL logs key a game as
    "ARI-001" and `games` keys the same game "DAL@TB". Joining on game_id
    matched nothing, printed "0 team-games", and looked exactly like a
    feed that had never been harvested — on a table holding 30,750 rows.

    A team plays once per period in both sports, so (season, period,
    team) identifies a team-game whatever either side calls the file."""
    for style in ("team", "matchup"):
        conn = _db(game_id_style=style)
        rows = S.between_games(conn, "nfl")
        assert len(rows) == 3 * 20 * 9 * 2, (style, len(rows))
        assert all(r["tds"] > 0 for r in rows), style


def test_the_lead_receiver_is_keyed_on_receptions_not_targets():
    """College carries ONE `targets` row in the entire table. Keying the
    lead receiver on it found nobody, gave every team-game a 0.000 share,
    and scored three identical zeroes — which reads as a clean tie
    between three models rather than as a broken population."""
    conn = _db("cfb")
    lead = S.lead_players(conn, "cfb", "WR")
    assert lead, "no lead receiver found at all"
    assert all(p.endswith("-WR1") for p in lead.values()), lead
    rows = S.within_team(conn, "cfb", "WR")
    assert rows and S.wmean(rows, "share") > 0.0, \
        "a zero share is the symptom this test exists for"


def test_the_lead_player_is_the_seasons_volume_leader_not_todays_scorer():
    """Picking the leader by touchdowns would score the model on its own
    answer. RB2 outscores nobody but RB1 has the carries, every week."""
    conn = _db()
    assert S.lead_players(conn, "nfl", "RB")[(2023, "H0")] == "H0-RB1"


# --- the curve, pointed the right way -------------------------------------
def test_the_college_curve_is_not_run_backwards():
    """`script_multiplier` takes the HOME line and derives the lead
    itself, so handing it a negated spread runs the whole curve
    backwards — which showed up as the shipped form scoring twice as
    badly as having no curve at all, a result that would have got a
    working term deleted."""
    # A 20-point home favourite: spread_home is NEGATIVE, and its back
    # gains while its receiver loses.
    assert S.shipped_multiplier("cfb", -20.0, "RB") > 1.0
    assert S.shipped_multiplier("cfb", -20.0, "WR") < 1.0
    # Which is exactly what the live board would apply to that player.
    assert S.shipped_multiplier("cfb", -20.0, "RB") == \
        C.script_multiplier(-20.0, True, "RB")[0]
    # And the underdog end mirrors it.
    assert S.shipped_multiplier("cfb", 20.0, "RB") < 1.0
    assert S.shipped_multiplier("nfl", -10.0, "RB") > 1.0
    assert S.shipped_multiplier("nfl", 10.0, "RB") < 1.0


# --- the scores themselves ------------------------------------------------
def test_chi_square_sees_a_bias_that_squared_error_calls_a_tie():
    """WHY THIS IS NOT SCORED BY SQUARED ERROR. One player's share of one
    game is noisy enough to hide a systematic shift, so per-game squared
    error rates a badly biased multiplier as barely worse than an
    unbiased one. Chi-square of band means measures the thing a
    multiplier is for.

    Compared here: a model that is right in every band, against the same
    model shifted 20% low everywhere."""
    rows = S.within_team(_db(), "nfl", "RB")
    by_spread = {}
    for r in rows:
        by_spread.setdefault(r["spread"], []).append(r)
    truth = {k: S.wmean(v, "share") for k, v in by_spread.items()}

    honest = S.chi_square(rows, "share", lambda r: truth[r["spread"]])
    biased = S.chi_square(rows, "share", lambda r: truth[r["spread"]] * 0.8)
    assert biased > honest * 20 + 50, (honest, biased)
    # The same pair by RMSE is nearly indistinguishable, which is the
    # point — the difference is a fraction of the per-game noise.
    r_honest = S.rmse(rows, "share", lambda r: truth[r["spread"]])
    r_biased = S.rmse(rows, "share", lambda r: truth[r["spread"]] * 0.8)
    assert r_biased < r_honest * 1.35, (r_honest, r_biased)


def test_a_real_script_effect_beats_no_script_on_this_slate():
    """The fixture's favoured backs really do score more of their teams'
    touchdowns, so a form that knows about the spread must beat one that
    does not. If it did not, the scorer would be broken rather than
    strict."""
    rows = S.within_team(_db(), "nfl", "RB")
    flat = S.chi_square(rows, "share", lambda r: S.wmean(rows, "share"))
    coef = S.wls(rows, "share", lambda r: [1.0, min(r["spread"], 0.0),
                                           max(r["spread"], 0.0)])
    fitted = S.chi_square(rows, "share", lambda r: (
        coef[0] + coef[1] * min(r["spread"], 0.0)
        + coef[2] * max(r["spread"], 0.0)))
    assert fitted < flat, (fitted, flat)


def test_the_between_game_report_keeps_real_zeroes_and_drops_dead_feeds():
    """A team-game with no logged touchdown on EITHER side is a feed that
    never landed, not a shutout, and counting it as a zero drags every
    expectation down. A genuine zero — the other side scored — stays."""
    conn = _db()
    conn.execute("DELETE FROM player_game_logs WHERE season=2024 AND "
                 "period='005' AND market='anytime_td'")
    conn.execute("UPDATE player_game_logs SET value=0 WHERE season=2024 "
                 "AND period='006' AND team='H0' AND market='anytime_td'")
    conn.commit()
    rows = S.between_games(conn, "nfl")
    mine = [r for r in rows if r["season"] == 2024 and r["team"] == "H0"]
    assert len(mine) == 19, "the dead week should be dropped entirely"
    assert [r["tds"] for r in mine].count(0.0) == 1, \
        "a real zero is data and must survive — the other side scored"


def test_the_report_runs_end_to_end_and_names_what_it_scored():
    """The whole point is a table somebody reads. It has to render even
    when a population is too thin to score."""
    conn = _db()
    lines = S.report_between(S.between_games(conn, "nfl"), "nfl")
    assert any("between games" in x for x in lines)
    assert any("implied total" in x for x in lines)
    lines = S.report_within(S.within_team(conn, "nfl", "RB"), "nfl", "RB")
    assert any("lead back" in x for x in lines)
    assert any("SHIPPED curve" in x for x in lines)
    # A thin population says so rather than printing a confident number.
    assert any("too few" in x for x in S.report_within([], "nfl", "WR"))
    assert any("too few" in x for x in S.report_between([], "nfl"))


def test_held_out_never_scores_a_season_it_trained_on():
    """Leave-one-season-out is the whole design: every form here contains
    the constant, so in-sample each can only improve on it and the winner
    would be whichever had the luckier fit."""
    seen = []
    rows = S.within_team(_db(), "nfl", "RB")

    def make(train, key):
        seen.append({r["season"] for r in train})
        return lambda r: S.wmean(train, key)

    S.held_out(rows, "share", make, S.chi_square)
    assert seen, "no season was held out at all"
    for i, trained in enumerate(seen):
        assert len(trained) == 2, trained
    assert len(seen) == 3, seen


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
