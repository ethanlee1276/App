"""Measuring college football instead of guessing at it.

`engine.cfb.ratings` has always been honest about the difference: with a
real sample it returns measured constants and ``fitted=True``; without
one the prior stands, ``fitted=False``, and the whole CFB board sits on
probation — journaled and graded, never staked.

On 2026-08-27 the database held ONE completed CFB game, so the prior had
been in force for the sport's entire life on this site. The blocker was
the feed: ESPN's scoreboard answers "what is on today" one day at a time
and a standard egress policy refuses it outright.
`engine.sources.cfbfastr` reads whole finished seasons off the same
raw.githubusercontent.com path the NFL schedules already use — 3,132
FBS-vs-FBS games across 2022–2025.

And measuring found a bug in the measurement. Home field was estimated
as the plain mean home margin, which in this sport is not the home-field
advantage: good teams host bad ones far more often than the reverse, so
that number came out +4.73 against the +2.7 two strength-controlled
estimators agree on. It would have replaced a decent invented prior
(2.4) with a confident wrong measurement, and pushed every projected
margin two points toward the home side on every college game.

Run directly: `python3 tests/test_cfb_history.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, teamrates
from engine.cfb import ratings as R
from engine.sources import cfbfastr as C


def _row(**kw):
    base = {"game_id": "401000001", "season": "2024", "week": "3",
            "season_type": "regular", "start_date": "2024-09-14T23:30:00.000Z",
            "completed": "TRUE", "neutral_site": "FALSE",
            "home_id": "61", "home_team": "Georgia", "home_division": "fbs",
            "home_points": "30",
            "away_id": "194", "away_team": "Ohio State", "away_division": "fbs",
            "away_points": "24"}
    base.update(kw)
    return base


# --- the parse ---------------------------------------------------------------
def test_a_finished_fbs_game_becomes_a_games_row():
    out = C.parse_schedule([_row()], 2024)
    g = out["games"][0]
    assert g["sport"] == "cfb" and g["season"] == 2024
    assert g["period"] == "2024-09-14"
    assert g["home"] == "espn:61" and g["away"] == "espn:194"
    assert g["home_score"] == 30.0 and g["away_score"] == 24.0


def test_the_cupcake_games_are_left_out():
    """An FBS side hosting an FCS opponent is 121 games a season nobody
    can bet, and including them drags the scoring baseline up and the
    margin spread wide — the two constants the stake depends on."""
    out = C.parse_schedule([_row(away_division="fcs"),
                            _row(home_division="ii", away_division="ii")], 2024)
    assert out["games"] == []
    assert out["skipped"]["not FBS vs FBS"] == 2


def test_an_unplayed_game_is_not_evidence():
    for missing in ({"home_points": ""}, {"away_points": "NA"},
                    {"home_points": "NA", "away_points": "NA"}):
        out = C.parse_schedule([_row(**missing)], 2024)
        assert out["games"] == [], missing
        assert out["skipped"]["no final score"] == 1


def test_no_spread_or_total_is_invented():
    """This feed carries scores and Elo, not betting lines. A 0.0 spread
    would read as a pick'em on 3,132 games and would hand the game-line
    calibration a market it never quoted."""
    g = C.parse_schedule([_row()], 2024)["games"][0]
    assert g["spread"] is None and g["total"] is None


def test_a_neutral_site_is_recorded_so_home_field_can_skip_it():
    g = C.parse_schedule([_row(neutral_site="TRUE")], 2024)["games"][0]
    assert json.loads(g["extra"])["neutral"] is True
    ordinary = C.parse_schedule([_row()], 2024)["games"][0]
    assert "neutral" not in json.loads(ordinary["extra"] or "{}")


def test_the_school_names_ride_along_for_a_later_resolution():
    g = C.parse_schedule([_row()], 2024)["games"][0]
    extra = json.loads(g["extra"])
    assert extra["home_name"] == "Georgia" and extra["away_name"] == "Ohio State"


def test_a_supplied_map_keys_rows_the_way_the_board_does():
    out = C.parse_schedule([_row()], 2024,
                           id_to_abbr={"61": "UGA", "194": "OSU"})
    assert out["games"][0]["home"] == "UGA"
    assert out["games"][0]["away"] == "OSU"


def test_a_team_the_map_does_not_know_is_skipped_not_guessed():
    out = C.parse_schedule([_row()], 2024, id_to_abbr={"61": "UGA"})
    assert out["games"] == []
    assert out["skipped"]["team id not in the map"] == 1


def test_the_two_namings_can_never_collide():
    """``espn:61`` is not a shape any real abbreviation takes, so a
    backfill run without a map and one run with it stay visibly distinct
    instead of silently splitting a team in half."""
    assert C.team_key("61", None) == "espn:61"
    assert ":" not in (C.team_key("61", {"61": "UGA"}) or "")


def test_a_row_with_no_team_id_is_skipped():
    out = C.parse_schedule([_row(home_id=""), _row(away_id="NA")], 2024)
    assert out["games"] == []
    assert out["skipped"]["team id not in the map"] == 2


# --- the home-field estimator ------------------------------------------------
def _balanced(hfa, n=40):
    """A schedule where every pair plays home-and-home, so the true
    home-field advantage is exactly ``hfa`` and nothing else."""
    teams = [f"T{i}" for i in range(n)]
    games = []
    for i, x in enumerate(teams):
        for y in teams[i + 1:]:
            sx, sy = i * 0.5, teams.index(y) * 0.5
            games.append((x, y, (sx - sy) + hfa, True))
            games.append((y, x, (sy - sx) + hfa, True))
    return games


def test_the_estimator_recovers_a_known_home_field():
    for hfa in (0.0, 2.7, 6.0, -1.5):
        got = R.home_field(_balanced(hfa, n=12))
        assert abs(got - hfa) < 1e-6, (hfa, got)


def test_the_biased_estimator_is_the_one_that_was_replaced():
    """The whole finding, constructed. Strong teams host weak ones; the
    true home-field edge is 2.0; the plain mean home margin says far
    more, and the joint fit says 2.0.
    """
    games = []
    # The buy game: a strong side (+14) hosting a weak one, never the
    # reverse. Three per weak team, so its strength is identified by
    # more than a single result.
    for w in range(12):
        for k in range(3):
            games.append((f"S{(w + k) % 12}", f"W{w}", 14.0 + 2.0, True))
    # …and a balanced home-and-home round-robin among the strong teams,
    # who are all of equal strength here.
    for i in range(12):
        for j in range(i + 1, 12):
            games.append((f"S{i}", f"S{j}", 2.0, True))
            games.append((f"S{j}", f"S{i}", 2.0, True))
    raw = sum(g[2] for g in games) / len(games)
    fitted = R.home_field(games)
    assert raw > 4.0, raw                     # what shipped
    assert abs(fitted - 2.0) < 1e-6, fitted   # what is true


def test_neutral_sites_do_not_contribute_a_home_edge():
    games = _balanced(3.0, n=8)
    games += [("T0", "T1", 25.0, False), ("T2", "T3", -25.0, False)]
    assert abs(R.home_field(games) - 3.0) < 1e-6


def test_the_estimator_refuses_rather_than_returning_zero():
    assert R.home_field([]) is None
    assert R.home_field([("A", "B", 3.0, False)]) is None      # no sited game
    assert R.home_field([("A", "A", 3.0, True)]) is None       # one team


def test_the_paired_cross_check_needs_real_pairs():
    assert R.paired_home_field(_balanced(2.5, n=4)) is None    # too few
    got = R.paired_home_field(_balanced(2.5, n=12))
    assert got and abs(got[0] - 2.5) < 1e-9
    assert got[1] >= R.HFA_MIN_PAIRS


def test_the_two_estimators_agree_on_a_balanced_schedule():
    games = _balanced(2.7, n=14)
    assert abs(R.home_field(games) - R.paired_home_field(games)[0]) < 1e-6


# --- the fit, end to end -----------------------------------------------------
def _seeded_db(hfa=2.7, seasons=(2023, 2024)):
    conn = db.connect(":memory:")
    teams = [f"espn:{100 + i}" for i in range(24)]
    rows, gid = [], 0
    for season in seasons:
        day = 1
        for i, x in enumerate(teams):
            for y in teams[i + 1:]:
                for home, away in ((x, y), (y, x)):
                    gid += 1
                    day = day % 28 + 1
                    hs = 27 + (teams.index(home) - teams.index(away)) * 0.5 \
                        + hfa + (gid % 7) - 3
                    as_ = 27 + (gid % 5) - 2
                    rows.append({
                        "sport": "cfb", "season": season,
                        "period": f"{season}-10-{day:02d}",
                        "game_id": str(gid), "home": home, "away": away,
                        "home_score": round(hs), "away_score": round(as_),
                        "spread": None, "total": None, "roof": None,
                        "surface": None, "temp": None, "wind": None,
                        "extra": None})
    db.upsert_games(conn, rows)
    return conn


def test_enough_real_games_lift_the_board_off_probation():
    conn = _seeded_db()
    tr = teamrates.compute_team_ratings(conn, "cfb")
    fit = R.fit_from_history(conn, tr)
    assert fit.games >= R.MIN_GAMES
    assert fit.fitted is True
    assert fit.probation is False


def test_a_thin_database_keeps_the_prior_and_says_so():
    conn = db.connect(":memory:")
    fit = R.fit_from_history(conn, {})
    assert fit.fitted is False and fit.probation is True
    assert str(R.MIN_GAMES) in fit.note


def test_the_note_quotes_the_independent_cross_check():
    """A joint fit that has drifted away from the pairs is visible on the
    board, not only in a test."""
    conn = _seeded_db()
    tr = teamrates.compute_team_ratings(conn, "cfb")
    note = R.fit_from_history(conn, tr).note
    assert "cross-checks at" in note
    assert "home-and-home pairs" in note


def test_the_prior_is_no_longer_an_invention():
    """Three of the five guesses were fine and two were not: the scoring
    baseline was 1.8 points per team high, which put every college total
    3.6 points over. The numbers below are measured on 3,132 real games,
    and `fitted` stays False because they were not measured on the games
    this board is pricing."""
    assert R.PRIOR.fitted is False
    assert abs(R.PRIOR.scoring_baseline - 26.70) < 1e-9
    assert abs(R.PRIOR.home_field - 2.71) < 1e-9
    assert "3,132" in R.PRIOR.note or "3132" in R.PRIOR.note
    # …and the prior must never claim the sport is off probation.
    assert R.PRIOR.probation is True


def test_the_installed_constants_follow_the_prior():
    from engine import gamebets
    R.install(R.PRIOR)
    assert gamebets.SCORING_BASELINE["cfb"] == R.PRIOR.scoring_baseline
    assert gamebets.HOME_FIELD["cfb"] == R.PRIOR.home_field
    assert gamebets.MARGIN_SD["cfb"] == R.PRIOR.margin_sd


# --- the re-key, and the four seasons the board could not see ----------
#
# The backfill keys a team ``espn:61`` when the teams feed is refused,
# and the live board keys the same school ``UGA``. Nothing joins:
# `engine.cfb.tds` looks a quoted player's usage up under the board's key
# and finds none, so it prices nobody — with 232,913 measured player rows
# in the table. The first build that DOES have the teams feed repairs it.

def _keyed_db(tmp):
    conn = db.connect(tmp)
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, "
                 "away, home_score, away_score) VALUES "
                 "('cfb', 2024, '2024-09-14', '401', 'espn:61', 'espn:194', "
                 "30, 24)")
    conn.execute("INSERT INTO player_game_logs (sport, season, period, "
                 "game_id, player, team, opponent, position, home, market, "
                 "value) VALUES ('cfb', 2024, '2024-09-14', '401', 'Back', "
                 "'espn:61', 'espn:194', 'RB', 1, 'anytime_td', 1)")
    conn.commit()
    return conn


def test_the_rekey_rewrites_both_tables_and_both_sides(tmp_path=None):
    import tempfile
    from engine.ingest import remap_cfb_team_keys
    with tempfile.TemporaryDirectory() as tmp:
        conn = _keyed_db(os.path.join(tmp, "h.db"))
        out = remap_cfb_team_keys(conn, {"61": "UGA", "194": "OSU"})
        assert out["teams"] == 2
        assert out["games"] == 2 and out["player_logs"] == 2
        game = conn.execute("SELECT home, away FROM games").fetchone()
        assert (game["home"], game["away"]) == ("UGA", "OSU")
        log = conn.execute("SELECT team, opponent FROM "
                           "player_game_logs").fetchone()
        assert (log["team"], log["opponent"]) == ("UGA", "OSU")


def test_a_team_the_feed_does_not_carry_stays_keyed_and_is_reported():
    import tempfile
    from engine.ingest import remap_cfb_team_keys
    with tempfile.TemporaryDirectory() as tmp:
        conn = _keyed_db(os.path.join(tmp, "h.db"))
        out = remap_cfb_team_keys(conn, {"61": "UGA"})
        assert out["unmapped"] == ["espn:194"]
        game = conn.execute("SELECT home, away FROM games").fetchone()
        assert (game["home"], game["away"]) == ("UGA", "espn:194")


def test_no_map_at_all_changes_nothing():
    import tempfile
    from engine.ingest import remap_cfb_team_keys
    with tempfile.TemporaryDirectory() as tmp:
        conn = _keyed_db(os.path.join(tmp, "h.db"))
        out = remap_cfb_team_keys(conn, {})
        assert out == {"games": 0, "player_logs": 0, "teams": 0,
                       "unmapped": []}
        assert conn.execute("SELECT home FROM games").fetchone()[0] == "espn:61"


def test_the_id_map_accumulates_across_builds():
    import tempfile
    from engine import cfbteams
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ids.json")
        assert cfbteams.remember_ids({"61": "UGA"}, path) == 1
        assert cfbteams.remember_ids({"194": "OSU"}, path) == 1
        assert cfbteams.load_ids(path) == {"61": "UGA", "194": "OSU"}
        # A build that saw only what was playing must not shrink it.
        assert cfbteams.remember_ids({"61": "UGA"}, path) == 0
        assert len(cfbteams.load_ids(path)) == 2


def test_an_unreadable_id_map_reads_as_empty_never_raises():
    import tempfile
    from engine import cfbteams
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ids.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        assert cfbteams.load_ids(path) == {}


def test_a_backfill_with_no_explicit_map_reads_the_persisted_one():
    """Otherwise a box that already learned the real abbreviations
    re-introduces ``espn:`` keys the next time it backfills."""
    import inspect
    from engine import ingest
    source = inspect.getsource(ingest.ingest_cfb_history)
    assert "cfbteams.load_ids()" in source


def test_the_variance_fit_needs_ratings_for_both_sides_of_a_game():
    """The reason the build hands it a map of EVERY season. Residuals
    are only computed where both teams are rated, so a current-season
    map in week 1 produces none, borrows all three spreads from the
    prior and reports fitted=False — which `engine.probation` reads as
    "do not stake this sport", with 3,132 measured games in the table."""
    import tempfile
    from engine import teamrates as _tr
    with tempfile.TemporaryDirectory() as tmp:
        conn = db.connect(os.path.join(tmp, "h.db"))
        rows = []
        teams = [f"T{i}" for i in range(20)]
        for season in (2023, 2024):
            for i, home in enumerate(teams):
                for j, away in enumerate(teams):
                    if i >= j:
                        continue
                    rows.append({
                        "sport": "cfb", "season": season,
                        "period": f"{season}-09-{(i % 28) + 1:02d}",
                        "game_id": f"{season}-{i}-{j}", "home": home,
                        "away": away, "home_score": 24 + (i % 7) * 3,
                        "away_score": 17 + (j % 5) * 3,
                        "spread": None, "total": None, "roof": None,
                        "surface": None, "temp": None, "wind": None,
                        "extra": None})
        db.upsert_games(conn, rows)
        thin = _tr.compute_team_ratings(conn, "cfb", shrink=8.0,
                                        seasons=[2099])
        assert not thin
        full = _tr.compute_team_ratings(conn, "cfb", shrink=8.0)
        assert len(full) == len(teams)
        assert R.fit_from_history(conn, thin, min_games=10).fitted is False
        assert R.fit_from_history(conn, full, min_games=10).fitted is True


def test_the_build_hands_the_variance_fit_every_season():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "cfb_build.py"), encoding="utf-8") as fh:
        source = fh.read()
    block = source[source.index("teamrates.ratings_for_season("):]
    block = block[:block.index("cfbratings.install(fit)")]
    # every season, with the same FCS exclusion the board's own map gets
    assert 'compute_team_ratings(conn, "cfb", shrink=8.0,' in block, \
        "the variance fit must get a map that is not current-season only"
    assert "seasons=" not in block[block.index("all_seasons = "):block.index("fit = ")]
    assert "fit_from_history(conn, all_seasons or ratings)" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
