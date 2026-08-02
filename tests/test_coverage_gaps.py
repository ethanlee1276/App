"""Days inside the span that are half-ingested.

``date_ranges`` reports first and last, which is the wrong shape for the
failure that actually happens. A span of 2021 to 2026 prints with no
complaint while three days in the middle hold nothing — and the holes are
not cosmetic. A bet whose day was never fully ingested cannot settle, sits
open forever, and before the settle guards landed could be graded against
the wrong game entirely. Ethan's repair pass surfaced seventeen bets dated
2026-07-27 for exactly this reason.

Free to compute and free to repair: statsapi.mlb.com is keyless, so nothing
in this path spends an Odds API credit.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ing_repair(gaps):
    import ingest as ing
    return ing.repair_command("mlb", gaps)


def _conn():
    return db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))


def _game(c, day, gid="g1", scored=True):
    c.execute("INSERT INTO games (sport,season,period,game_id,home,away,"
              "home_score,away_score) VALUES ('mlb',2026,?,?,'NYM','ATL',?,?)",
              (day, gid, 4 if scored else None, 2 if scored else None))


def _logs(c, day, n, gid="g1"):
    for i in range(n):
        c.execute("INSERT INTO player_game_logs (sport,season,period,game_id,"
                  "player,team,opponent,position,home,market,value) VALUES "
                  "('mlb',2026,?,?,?,'NYM','ATL','C',1,'hits',1.0)",
                  (day, gid, f"P{i}"))


def _full_day(c, day):
    _game(c, day)
    _logs(c, day, db.THIN_PLAYERS_PER_GAME * 3)


def _kinds(c):
    return {g["date"]: g["kind"] for g in db.coverage_gaps(c)}


# --- the four holes ---------------------------------------------------------
def test_a_day_whose_games_have_no_scores_is_a_gap():
    """The scores layer ran and came back empty. Team ratings, the moneyline
    backtest and every team-market settle read finals — a day with none is
    invisible to all three."""
    c = _conn()
    _game(c, "2026-07-27", scored=False)
    c.commit()
    assert _kinds(c) == {"2026-07-27": "no_finals"}


def test_a_day_with_only_some_finals_is_named_differently():
    """Usually a genuinely suspended game, occasionally a partial run — and
    the two need different responses, so they get different labels."""
    c = _conn()
    _game(c, "2026-07-28", "g1")
    _game(c, "2026-07-28", "g2", scored=False)
    c.commit()
    assert _kinds(c) == {"2026-07-28": "some_finals"}


def test_finals_without_player_logs_is_the_expensive_one():
    """The scores layer worked and the log layer did not. Props have nothing
    to settle against, so every prop bet that day stays open forever."""
    c = _conn()
    _game(c, "2026-07-30")
    c.commit()
    assert _kinds(c) == {"2026-07-30": "no_logs"}


def test_a_handful_of_players_is_not_a_slate():
    """A real fixture logs 20-30 distinct players once the bullpen and the
    bench are counted. Two is a run that stopped part-way, and from the
    outside it looks exactly like a quiet day."""
    c = _conn()
    for i in range(13):
        _game(c, "2026-07-31", f"g{i}")
    _logs(c, "2026-07-31", 25)              # 1.9 a game
    c.commit()
    assert _kinds(c) == {"2026-07-31": "thin_logs"}


def test_a_small_but_COMPLETE_day_is_not_thin():
    """The absolute threshold's own bug. 77 players across 3 games is 26 a
    game — a complete ingest of a quiet Monday — and an absolute bar of 120
    called it a hole. Eleven of the eighteen days the first version reported
    as thin were this, and each one sent a repair walk after nothing."""
    c = _conn()
    for i in range(3):
        _game(c, "2026-06-07", f"g{i}")
    _logs(c, "2026-06-07", 77)
    _full_day(c, "2026-08-02")
    c.commit()
    assert db.coverage_gaps(c) == []


# --- and the things it must NOT flag ----------------------------------------
def test_a_complete_day_is_silent():
    c = _conn()
    _full_day(c, "2026-07-26")
    c.commit()
    assert db.coverage_gaps(c) == []


def test_an_empty_day_is_never_reported():
    """Off days, the All-Star break and the whole offseason all look like an
    empty day. A report that cries wolf on every Monday in November stops
    being read — and an unread diagnostic is the same as no diagnostic.
    """
    c = _conn()
    _full_day(c, "2026-07-26")
    _full_day(c, "2026-07-29")          # 27th and 28th simply absent
    c.commit()
    assert db.coverage_gaps(c) == []


def test_another_sport_is_not_scanned():
    c = _conn()
    c.execute("INSERT INTO games (sport,season,period,game_id,home,away) "
              "VALUES ('nfl',2026,'2026-07-27','g','GB','CHI')")
    c.commit()
    assert db.coverage_gaps(c, sport="mlb") == []


def test_it_reports_and_never_writes():
    """Safe against a live history DB mid-slate."""
    c = _conn()
    _game(c, "2026-07-27", scored=False)
    c.commit()
    before = c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    db.coverage_gaps(c)
    assert c.execute("SELECT COUNT(*) FROM games").fetchone()[0] == before


def test_the_window_can_be_narrowed():
    c = _conn()
    _game(c, "2026-07-27", scored=False)
    _game(c, "2026-08-15", scored=False)
    c.commit()
    got = db.coverage_gaps(c, start="2026-08-01")
    assert [g["date"] for g in got] == ["2026-08-15"]


def test_the_days_come_back_in_order():
    """The repair command is built from the first and last, so an unordered
    list would produce a backwards range."""
    c = _conn()
    for d in ("2026-07-30", "2026-07-27", "2026-07-28"):
        _game(c, d, scored=False)
    c.commit()
    days = [g["date"] for g in db.coverage_gaps(c)]
    assert days == sorted(days)


# --- the report -------------------------------------------------------------
def test_the_summary_prints_the_gaps():
    src = open(os.path.join(ROOT, "ingest.py"), encoding="utf-8").read()
    assert "print_gaps(conn)" in src
    assert "def print_gaps(" in src


def test_the_repair_command_is_named_as_free():
    """Ethan's constraint was explicit: do not eat the API credits. MLB
    results come from statsapi.mlb.com, which needs no key — the report has
    to say so, or the command looks like it costs money and never gets run.
    """
    src = open(os.path.join(ROOT, "ingest.py"), encoding="utf-8").read()
    i = src.index("def print_gaps(")
    block = src[i:i + 2600]
    assert "FREE" in block and "no key" in block
    assert "repair_command(sport, fixable)" in block
    # And the follow-up, because re-ingesting alone leaves the bets open.
    assert "--settle all" in block


def test_a_few_scattered_days_get_named_not_ranged():
    """22 holes spread over five seasons became "--from 2021-06-07 --to
    2026-07-16" — 1,867 days of requests to fix 22. Free of credits is not
    free of an afternoon."""
    cmd = ing_repair([{"date": "2021-06-07"}, {"date": "2024-03-20"},
                      {"date": "2026-07-16"}])
    assert "--dates 2021-06-07,2024-03-20,2026-07-16" in cmd
    assert "--from" not in cmd


def test_a_long_contiguous_outage_gets_a_range():
    """The other direction. Past the threshold a range genuinely is the
    smaller ask, and a comma list of 400 dates is not a command."""
    days = [{"date": f"2026-05-{d:02d}"} for d in range(1, 29)]
    days += [{"date": f"2026-06-{d:02d}"} for d in range(1, 29)]
    cmd = ing_repair(days)
    assert "--from 2026-05-01 --to 2026-06-28" in cmd
    assert "--dates" not in cmd


def test_a_clean_database_says_so_rather_than_going_quiet():
    """Silence reads as "the check did not run"."""
    src = open(os.path.join(ROOT, "ingest.py"), encoding="utf-8").read()
    i = src.index("def print_gaps(")
    assert "no half-ingested days" in src[i:i + 2600]


def test_a_long_list_collapses_rather_than_scrolling():
    c = _conn()
    for d in range(1, 25):
        _game(c, f"2026-06-{d:02d}", scored=False)
    c.commit()
    assert len(db.coverage_gaps(c)) == 24
    src = open(os.path.join(ROOT, "ingest.py"), encoding="utf-8").read()
    assert "GAP_LIST_MAX" in src
# --- what the first real run taught it --------------------------------------
#
# Against Ethan's live DB the first version returned 519 days and printed a
# five-year repair walk. Both failures are pinned below.


def test_spring_training_is_not_a_hole():
    """The 519 were mostly this. Spring training is in the schedule and its
    games have finals, but the ingest deliberately stores no player logs for
    them — so every day from March 1st was reported, 14 games at a time.

    The window comes from the DATA, not a calendar: a hardcoded "the season
    starts in April" would be wrong the year the league moves opening day,
    and would say nothing about a backfill that genuinely stopped in July.
    """
    c = _conn()
    for d in ("2026-03-01", "2026-03-02", "2026-03-05"):
        _game(c, d)                       # final, no logs — before the window
    _full_day(c, "2026-04-01")
    _full_day(c, "2026-08-02")
    c.commit()
    assert db.coverage_gaps(c) == []


def test_a_hole_inside_the_logged_window_still_reports():
    """The control for the test above. Restricting to the window must not
    silence real holes in the middle of the season."""
    c = _conn()
    _full_day(c, "2026-04-01")
    _game(c, "2026-07-30")                # final, no logs — inside the window
    _full_day(c, "2026-08-02")
    c.commit()
    assert _kinds(c) == {"2026-07-30": "no_logs"}


def test_a_season_with_no_logs_at_all_is_still_scanned():
    """No window to speak of means no basis to exclude anything — a season
    that was never ingested should not be silenced by its own absence."""
    c = _conn()
    _game(c, "2026-07-30")
    c.commit()
    assert _kinds(c) == {"2026-07-30": "no_logs"}


def test_a_scoreless_past_day_is_marked_unrepairable():
    """parse_results returns completed, SCORED games and nothing else, so a
    scoreless row on a past date is a postponed, cancelled or suspended
    fixture. Re-ingesting cannot fill it, and listing it beside a real hole
    is what produced a five-year repair range for a handful of days."""
    c = _conn()
    _full_day(c, "2026-04-01")
    _game(c, "2026-07-27", scored=False)
    _full_day(c, "2026-08-02")
    c.commit()
    got = db.coverage_gaps(c)
    assert [g["date"] for g in got] == ["2026-07-27"]
    assert got[0]["repairable"] is False


def test_missing_logs_are_marked_repairable():
    c = _conn()
    _full_day(c, "2026-04-01")
    _game(c, "2026-07-30")
    _full_day(c, "2026-08-02")
    c.commit()
    assert db.coverage_gaps(c)[0]["repairable"] is True


def test_the_repair_range_is_built_from_repairable_days_only():
    """The bug in one assertion: one real hole in July must not produce a
    range starting at the first postponed game of the season."""
    import io
    import contextlib
    import ingest as ing
    c = _conn()
    _full_day(c, "2026-04-01")
    _game(c, "2026-04-02", scored=False)          # postponed, unrepairable
    _game(c, "2026-07-30")                        # the actual hole
    _full_day(c, "2026-08-02")
    c.commit()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ing.print_gaps(c)
    out = buf.getvalue()
    assert "--dates 2026-07-30" in out
    assert "2026-04-02" not in out.split("NEVER resolve")[0]


def test_the_unrepairable_days_get_their_own_heading_and_remedy():
    """Different cause, different fix. Merged into one list they made the
    list unreadable and the repair command wrong."""
    import io
    import contextlib
    import ingest as ing
    c = _conn()
    _full_day(c, "2026-04-01")
    _game(c, "2026-07-27", scored=False)
    _full_day(c, "2026-08-02")
    c.commit()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ing.print_gaps(c)
    out = buf.getvalue()
    assert "NEVER resolve" in out
    assert "postponed" in out
    # And it must not pretend a re-ingest is the answer for them.
    assert "nothing a re-ingest would fill" in out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
