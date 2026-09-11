"""A finished backfill and a broken one printed the same thing.

From a real run. Two seasons of NBA, two hours of walking:

    546/546 days · 0 games · 0 log rows
      games: 0   player-log rows: 0   (459 day(s) already stored, skipped)

    History DB contents:
      NFL: 1,696 games ...
      MLB: 16,525 games ...

Nothing was wrong. 459 days were already stored, and the other 87 are days
the NBA does not play — a season WINDOW is Oct 1 to Jun 30, but the league
sits out three weeks of that October, the All-Star break, the gaps between
playoff rounds and the fortnight after the finals. The backfill was done.

You could not tell from the output. The headline number was 0, and the
summary underneath listed two sports because it had been written as the
literal tuple ("nfl", "mlb") — so the basketball you just spent two hours
fetching was not mentioned at all.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ingest
from engine import db
from engine.seasons import dates_for


def _db_with(sport, dates, logs=True):
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    grows, prows = [], []
    for i, d in enumerate(dates):
        grows.append({"sport": sport, "season": 2024, "period": d,
                      "game_id": f"g{i}", "home": "BOS", "away": "LAL",
                      "home_score": 110, "away_score": 104, "spread": 0.0,
                      "total": None, "roof": "indoor", "surface": "hardwood",
                      "temp": None, "wind": None, "extra": None})
        if logs:
            prows.append({"sport": sport, "season": 2024, "period": d,
                          "game_id": f"g{i}", "player": "P", "team": "BOS",
                          "opponent": "LAL", "position": "G", "home": 1,
                          "market": "points", "value": 20.0})
    db.upsert_games(conn, grows)
    db.upsert_player_logs(conn, prows)
    return conn


def _quiet_day(_conn, _date):
    """A date the league did not play: a clean answer holding no games."""
    return {"games": 0, "player_logs": 0, "skipped": []}


def _broken_day(_conn, _date):
    """A date the feed could not answer at all — the real failure."""
    return {"games": 0, "player_logs": 0, "skipped": ["nba scoreboard: 403"]}


# --- the summary that forgot basketball -------------------------------------
def test_the_summary_reports_every_sport_that_has_rows():
    conn = _db_with("nba", dates_for("nba", [2024])[:20])
    s = db.summary(conn)
    assert s["games"]["nba"] == 20, "the sport just ingested is missing"
    assert "nfl" in s["games"] and "mlb" in s["games"]


def test_a_board_with_nothing_stored_is_still_listed():
    """Silence and "no data" look identical, and only one of them is worth
    acting on."""
    conn = _db_with("nba", dates_for("nba", [2024])[:5])
    assert set(db.CORE_SPORTS) <= set(db.summary(conn)["games"])
    assert db.summary(conn)["games"]["wnba"] == 0


def test_an_unexpected_sport_still_shows_up():
    conn = _db_with("ufc", ["2026-07-04"])
    assert "ufc" in db.sports_present(conn)
    # ...and the core boards keep their place at the front.
    assert db.sports_present(conn)[:len(db.CORE_SPORTS)] == list(db.CORE_SPORTS)


# --- telling a finished walk from a failed one ------------------------------
def test_days_the_league_did_not_play_are_counted_separately():
    dates = dates_for("nba", [2024, 2025])
    conn = _db_with("nba", dates[:459])
    g, p, skipped, empty = ingest._walk_days(
        conn, "nba", dates, _quiet_day, False, False)
    assert (g, p) == (0, 0)
    assert skipped == 459
    assert empty == len(dates) - 459
    # Which is the whole point: every date is accounted for, so "0 new" is
    # provably "nothing left" rather than "nothing worked".
    assert skipped + empty == len(dates)


def test_a_dead_feed_is_not_counted_as_a_quiet_day():
    """The distinction only earns its keep if a real outage still reads as
    one. A day the feed refused has a skip reason; a day with no games does
    not."""
    dates = dates_for("nba", [2024])[:10]
    conn = _db_with("nba", [])
    g, p, skipped, empty = ingest._walk_days(
        conn, "nba", dates, _broken_day, False, False)
    assert (g, p, skipped, empty) == (0, 0, 0, 0), \
        "a 403 from every endpoint was filed as an off day"


def test_the_standing_total_is_available_to_report():
    """What this RUN added and what the DB HOLDS are different numbers, and
    after a resumed backfill only the second one answers "did it work"."""
    conn = _db_with("nba", dates_for("nba", [2024])[:30])
    assert ingest._held(conn, "nba") == (30, 30)
    assert ingest._held(conn, "wnba") == (0, 0)


def test_a_scores_only_day_is_rewalked_for_its_logs():
    """Resumability must not mark a day finished that is missing the half
    you came back for."""
    dates = dates_for("nba", [2024])[:6]
    conn = _db_with("nba", dates, logs=False)
    assert ingest._already_have(conn, "nba", dates[0], need_logs=False) is True
    assert ingest._already_have(conn, "nba", dates[0], need_logs=True) is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
