"""Multi-season history: the thing that was actually limiting every model.

The database had five seasons of NFL and at most one of anything else, and
almost every weakness downstream traced back to that. Team ratings firm up
with games. A prop backtest can only replay games it has. Calibration
needs hundreds of graded results. The college football variance fit
refuses to run under 400 games.

The obstacle was never the model — it was the shape of the command, and
two facts nobody should have to hold in their head:

**The NBA CDN only serves the CURRENT season.** It cannot answer a
question about 2021 at all, which is precisely why basketball had one
season and football had five. ESPN's scoreboard is per-date and goes back
as far as the sport does.

**A season is labelled by the year it STARTS.** An NBA game in March 2022
belongs to the 2021 season; keying it to 2022 would split every season in
half in the games table and quietly halve every team's sample.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import seasons as S
from engine.sources import espnhoops as E


# --- the windows ------------------------------------------------------------
def test_every_sport_with_a_board_has_a_season_window():
    for sport in ("mlb", "nba", "wnba", "cfb"):
        lo, hi = S.window(sport, 2023)
        assert lo < hi, f"{sport}'s window runs backwards"


def test_the_seasons_that_cross_new_year_actually_cross_it():
    """Getting this wrong drops a playoff round or a bowl season."""
    assert S.window("nba", 2023)[1].startswith("2024")
    assert S.window("cfb", 2023)[1].startswith("2024")
    # …and the ones that don't, don't.
    assert S.window("mlb", 2023)[1].startswith("2023")
    assert S.window("wnba", 2023)[1].startswith("2023")


def test_an_unknown_sport_raises_rather_than_guessing_a_window():
    try:
        S.window("hockey", 2023)
        assert False, "invented a season for a sport we don't cover"
    except ValueError:
        pass


def test_season_specs_accept_what_people_actually_type():
    assert S.parse_seasons("2021-2026") == [2021, 2022, 2023, 2024, 2025, 2026]
    assert S.parse_seasons("2024") == [2024]
    assert S.parse_seasons("2021,2023,2025") == [2021, 2023, 2025]
    assert S.parse_seasons("2026-2021") == S.parse_seasons("2021-2026")
    assert S.parse_seasons("") == []


def test_the_walk_stops_at_today():
    """A season in progress has no results past today, and walking into
    next June would spend a thousand requests confirming that."""
    import datetime as _dt
    days = S.dates_for("nba", [2025])
    assert days, "the current season should still produce dates"
    assert days[-1] <= _dt.date.today().isoformat()


def test_a_heavy_backfill_warns_before_it_starts():
    text = S.describe("nba", [2021, 2022], 700)
    assert "slow" in text and "skipped" in text
    assert "700" in text or "700," in text


# --- season labelling -------------------------------------------------------
def test_a_march_game_belongs_to_the_season_that_started_in_october():
    assert E._season_of("2022-03-05", "nba") == 2021
    assert E._season_of("2021-11-20", "nba") == 2021
    assert E._season_of("2022-06-15", "nba") == 2021


def test_a_single_calendar_year_sport_keeps_its_own_year():
    assert E._season_of("2026-07-15", "wnba") == 2026
    assert E._season_of("2026-05-02", "wnba") == 2026


# --- the NBA history source -------------------------------------------------
def test_both_basketball_leagues_share_one_parser():
    """Two copies of a box-score parser drift, and the first symptom would
    be one league quietly missing a stat the other has."""
    from engine.sources import wnbaespn
    assert wnbaespn.parse_summary is E.parse_summary
    assert wnbaespn.parse_scoreboard is E.parse_scoreboard
    assert set(E.LEAGUES) == {"nba", "wnba"}
    assert "basketball/nba" in E._base("nba")
    assert "basketball/wnba" in E._base("wnba")


def test_the_nba_history_does_not_come_from_the_current_season_cdn():
    """The CDN's scheduleLeagueV2.json is this season only — it cannot
    answer a question about 2021, which is why this database had one
    season of basketball and five of football."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ingest.py"), encoding="utf-8").read()
    assert "from engine.sources import espnhoops" in src
    assert "ingest_nba_date" not in src, "history still routed via the CDN"


def test_scores_only_never_requests_a_box_score():
    """The difference between a six-season backfill taking an afternoon
    and taking a week. Final scores alone unlock ratings, the variance
    fits and settlement."""
    from unittest import mock
    from engine import db
    sb = {"events": [{"id": "g1", "date": "2022-03-05T23:00Z", "competitions": [{
        "status": {"type": {"completed": True}},
        "competitors": [
            {"homeAway": "home", "score": 110, "team": {"abbreviation": "BOS"}},
            {"homeAway": "away", "score": 104, "team": {"abbreviation": "MIA"}}]}]}]}

    def _boom(*a, **k):
        raise AssertionError("a box score was fetched in scores-only mode")

    conn = db.connect(":memory:")
    with mock.patch.object(E, "fetch_scoreboard", lambda d, ttl=0, league="": sb), \
         mock.patch.object(E, "fetch_summary", _boom):
        res = E.ingest_day(conn, "2022-03-05", league="nba", scores_only=True)
    assert res["games"] == 1 and res["player_logs"] == 0


# --- the CLI ----------------------------------------------------------------
def test_a_bare_command_prints_usage_instead_of_starting_an_afternoon():
    """`--seasons` used to default to the NFL's last five, so
    `python3 ingest.py nba` silently launched a 1,366-day backfill instead
    of printing the options."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for sport in ("nba", "wnba", "cfb"):
        out = subprocess.run(["python3", os.path.join(root, "ingest.py"), sport],
                             capture_output=True, text=True, timeout=90)
        assert "Provide" in out.stdout, f"{sport} started work with no args"
        assert "Ingesting" not in out.stdout


def test_a_backfill_is_resumable():
    """Thousands of requests; one dropped connection must not cost the run."""
    from engine import db
    import ingest as I
    conn = db.connect(":memory:")
    assert I._already_have(conn, "nba", "2022-03-05", True) is False
    db.upsert_games(conn, [{"sport": "nba", "season": 2021,
                            "period": "2022-03-05", "game_id": "g1",
                            "home": "BOS", "away": "MIA",
                            "home_score": 110.0, "away_score": 104.0}])
    # Scores are there but logs aren't — a logs run must NOT skip the day.
    assert I._already_have(conn, "nba", "2022-03-05", True) is False
    assert I._already_have(conn, "nba", "2022-03-05", False) is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
