"""Team ratings must survive the start of a season.

Found on the real machine 2026-08-08. `python3 ingest.py nfl` reported
**1,696 games, 1,424 with final scores** — and the board still said:

    Team ratings: none in the DB yet — run `python3 ingest.py nfl` so the
    moneyline model has team strength to find an edge.

Every build script asked for `seasons=[current]`, and `compute_team_ratings`
requires a final score. All 272 unscored games WERE the 2026 season, because
it had not been played. The query returned nothing and the message sent the
reader to run the one command that could not possibly help.

Same fault as the prop board's (see engine/carry.py): scoping to a season
that by definition has no results at the start of a season. Same repair:
carry the previous one until this one can stand up.

Run directly: `python3 tests/test_season_ratings.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, teamrates                                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEAMS = ("AAA", "BBB", "CCC", "DDD")


def _conn(rows):
    """rows: (season, home, away, home_score, away_score)."""
    c = db.connect(":memory:")
    for i, (season, h, a, hs, as_) in enumerate(rows):
        c.execute(
            "INSERT INTO games (sport, season, period, game_id, home, away,"
            " home_score, away_score) VALUES ('nfl',?,?,?,?,?,?,?)",
            (season, f"{i % 18 + 1:03d}", f"g{season}{i}", h, a, hs, as_))
    c.commit()
    return c


def _played(season, n=8):
    out = []
    for i in range(n):
        h, a = TEAMS[i % 4], TEAMS[(i + 1) % 4]
        out.append((season, h, a, 24, 17))
    return out


def _scheduled(season, n=8):
    """The shape that broke it: rows exist, scores are NULL."""
    return [(season, TEAMS[i % 4], TEAMS[(i + 1) % 4], None, None)
            for i in range(n)]


# --- the bug -----------------------------------------------------------------
def test_a_season_with_no_scores_yet_still_produces_ratings():
    """The exact situation on the machine: last season played, this season
    scheduled but unplayed."""
    conn = _conn(_played(2025, 40) + _scheduled(2026, 16))
    ratings, seasons = teamrates.ratings_for_season(conn, "nfl", 2026)
    assert ratings, "no ratings at the start of a season"
    assert 2025 in seasons, seasons


def test_the_old_call_really_did_return_nothing():
    """Pinning the fault itself, so nobody 'simplifies' the helper back to
    the single-season call it replaced."""
    conn = _conn(_played(2025, 40) + _scheduled(2026, 16))
    single = teamrates.compute_team_ratings(conn, "nfl", seasons=[2026])
    assert single == {}, single


# --- and does not overreach --------------------------------------------------
def test_a_season_with_enough_games_stands_on_its_own():
    """Once this season can speak, last season stops being pooled in — a
    rating still carrying last year's roster in December is worse than the
    gap it was covering."""
    conn = _conn(_played(2025, 40) + _played(2026, 40))
    _r, seasons = teamrates.ratings_for_season(conn, "nfl", 2026)
    assert seasons == [2026], seasons


def test_the_floor_is_games_per_team_not_games_total():
    """A 32-team league playing 16 games has one game per team, which is
    nothing. Counting fixtures rather than per-team samples would call that
    enough."""
    conn = _conn(_played(2025, 40) + _played(2026, 4))
    _r, seasons = teamrates.ratings_for_season(conn, "nfl", 2026)
    assert len(seasons) == 2, seasons


def test_an_empty_database_does_not_invent_a_wider_window():
    """With nothing anywhere, reporting a two-season span would claim a
    search that also found nothing."""
    conn = _conn([])
    ratings, seasons = teamrates.ratings_for_season(conn, "nfl", 2026)
    assert ratings == {}
    assert seasons == [2026], seasons


def test_pooling_actually_changes_the_numbers():
    """If the pooled call returned the same ratings as the thin one, the
    fallback would be decoration."""
    conn = _conn(_played(2025, 40) + _scheduled(2026, 16))
    pooled, _ = teamrates.ratings_for_season(conn, "nfl", 2026)
    thin = teamrates.compute_team_ratings(conn, "nfl", seasons=[2026])
    assert pooled != thin
    assert all(r.games > 0 for r in pooled.values())


# --- the message ------------------------------------------------------------
def test_no_build_script_still_scopes_ratings_to_one_season():
    """nfl_build and mlb_build both had it; cfb_build fits a distribution
    rather than attaching ratings to a board, and coverage.py already had
    its own fallback."""
    for f in ("nfl_build.py", "mlb_build.py"):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        assert "ratings_for_season(" in src, f
        assert "compute_team_ratings(conn" not in src, f


def test_the_message_no_longer_sends_you_to_run_the_useless_command():
    """The original told the reader to run an ingest that could not help,
    which is worse than saying nothing. It has to name the real
    condition: no PLAYED games yet."""
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    i = src.index("Team ratings: no ")
    msg = src[i:i + 400]
    assert "SCORED" in msg or "played" in msg
    assert "nothing to fill" in msg


def test_the_span_is_reported_so_a_pooled_rating_says_so():
    """A number built partly from last season must not look like this
    season's."""
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "last season pooled in" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
