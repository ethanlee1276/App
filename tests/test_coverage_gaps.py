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
    _logs(c, day, db.THIN_DAY_PLAYERS + 50)


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
    """A full MLB day stores several hundred. Nine is a run that stopped
    part-way, and from the outside it looks exactly like a quiet day."""
    c = _conn()
    _game(c, "2026-07-31")
    _logs(c, "2026-07-31", 9)
    c.commit()
    assert _kinds(c) == {"2026-07-31": "thin_logs"}


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
    assert "python3 ingest.py {sport} --from {lo} --to {hi}" in block
    # And the follow-up, because re-ingesting alone leaves the bets open.
    assert "--settle all" in block


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
