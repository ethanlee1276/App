"""The calendar day, kept apart from the settle key.

`bets.date` is a JOIN KEY, not a date. Every daily sport files its
results under the calendar day, so for them the two are the same string.
The NFL does not: nflverse files results under season + week, the board
journals "2026-W01", and `_hist_where` resolves that onto period "001".
ledger.py says twice what happens if you "fix" that by writing an ISO
day instead — "a TD bet dated with the game's ISO Sunday would query a
period nothing is filed under and sit open forever".

So the key stays and the calendar gets a column. Before it existed,
everything that asked a DATE question was reading a join key:

  * the profit calendar collapsed every Week 1 bet into ONE bucket;
  * "W" sorts above every digit, so that bucket landed at the far right
    of the equity curve regardless of when the games were played;
  * `date >= '2026-08-01'` is TRUE of every week label ever written, so
    a one-month window silently contained every NFL bet in the journal.

Found 2026-09-08 asking whether the site was ready for the Wednesday
opener. It was the only thing on the readiness list that was broken
rather than merely unmeasured.
"""

import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger                                    # noqa: E402


def _db():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "ledger.db"))
    return conn


def _settled(conn, sport, date, player, pnl, game_day=None, market="moneyline"):
    conn.execute(
        "INSERT INTO bets (sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, pnl_units, pnl_dollars, "
        "category) VALUES (?,?,?,?,?,'OVER',0.5,-110,1.0,10.0,?,?,?, 'main')",
        (sport, date, game_day, player, market,
         "won" if pnl > 0 else "lost", pnl, pnl * 10))
    conn.commit()


# ------------------------------------------------------ the column exists

def test_the_column_survives_a_database_that_predates_it():
    """Ethan's ledger is 2.2 MB of real history. The migration has to add
    the column to it in place, not on a rebuild nobody will run."""
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    old = sqlite3.connect(path)
    old.executescript(ledger._BETS_TABLE)          # the table as it was
    old.execute("INSERT INTO bets (sport, date, player) "
                "VALUES ('nfl','2026-W01','Puka Nacua')")
    old.commit()
    old.execute("ALTER TABLE bets DROP COLUMN game_day")
    old.commit()
    old.close()
    conn = ledger.connect(path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bets)")]
    assert "game_day" in cols, cols
    # and the row that predates it is still there, carrying NULL
    row = conn.execute("SELECT date, game_day FROM bets").fetchone()
    assert row["date"] == "2026-W01"
    assert row["game_day"] is None


# ------------------------------------------------------ what counts as a day

def test_a_week_label_is_never_mistaken_for_a_day():
    """`date.fromisoformat("2026-W01")` returns 2025-12-29 on 3.11+ — a
    real date, in the wrong year, with no error. A parse-only guard here
    would have made the calendar confidently wrong instead of empty."""
    assert ledger.game_day_for({"date": "2026-W01"}) == ""
    assert ledger.game_day_for({}, "2026-W01") == ""


def test_the_games_own_date_beats_the_slates():
    assert ledger.game_day_for({"game_date": "2026-09-13"},
                               "2026-W01") == "2026-09-13"


def test_a_daily_sport_falls_through_to_the_slate():
    assert ledger.game_day_for({}, "2026-07-04") == "2026-07-04"


def test_a_utc_kickoff_instant_is_not_treated_as_a_day():
    """Every odds row carries `commence_time`, and a Sunday-night kickoff
    is 00:20Z on MONDAY. Slicing ten characters off it files half the NFL
    week a day late — the same UTC drift that cost thirty home-run bets
    their settle in July."""
    assert ledger.game_day_for({"commence_time": "2026-09-14T00:20:00Z"},
                               "2026-W01") == ""


# --------------------------------------------------- the calendar and curve

def test_a_weeks_bets_land_on_the_days_they_were_played():
    """The whole point. Two NFL bets in one week label, played Thursday
    and Sunday, are two days on the calendar."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day="2026-09-10")
    _settled(conn, "nfl", "2026-W01", "PHI", -1.0, game_day="2026-09-13")
    days = [r["date"] for r in ledger.pnl_curve(conn)]
    assert days == ["2026-09-10", "2026-09-13"], days


def test_a_week_label_no_longer_sorts_to_the_end_of_the_curve():
    """"W" outranks every digit, so an NFL week used to land after every
    ISO day in its own year — the equity curve drew September's football
    to the right of October's baseball."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day="2026-09-13")
    _settled(conn, "mlb", "2026-10-02", "NYY", 1.0, game_day="2026-10-02")
    days = [r["date"] for r in ledger.pnl_curve(conn)]
    assert days == ["2026-09-13", "2026-10-02"], days


def test_a_date_window_no_longer_admits_every_week_label():
    """`'2026-W01' >= '2026-10-01'` is TRUE in SQLite, so a one-month
    window contained every NFL bet ever journalled — the count under the
    chart disagreed with the chart and nothing said why."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day="2026-09-13")
    _settled(conn, "mlb", "2026-10-02", "NYY", 1.0, game_day="2026-10-02")
    rows = ledger.pnl_curve(conn, since="2026-10-01")
    assert [r["date"] for r in rows] == ["2026-10-02"], rows


def test_a_row_with_no_day_still_appears_rather_than_vanishing():
    """Every row journalled before this column exists carries NULL. It
    keeps its old, wrong bucket — which is not good, and is not made
    worse by this change. Dropping it from the record to tidy the
    calendar would be losing real money from the ledger to fix a
    display."""
    conn = _db()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day=None)
    rows = ledger.pnl_curve(conn)
    assert [r["date"] for r in rows] == ["2026-W01"], rows
    assert rows[0]["day_u"] == 0.9


def test_a_daily_sport_reads_exactly_as_it_did_before():
    """The negative control. MLB's date IS its day, and this change must
    be invisible there."""
    conn = _db()
    _settled(conn, "mlb", "2026-07-04", "NYY", 1.0, game_day="2026-07-04")
    _settled(conn, "mlb", "2026-07-05", "BOS", -1.0, game_day="2026-07-05")
    rows = ledger.pnl_curve(conn)
    assert [r["date"] for r in rows] == ["2026-07-04", "2026-07-05"]
    assert [r["day_u"] for r in rows] == [1.0, -1.0]


# ------------------------------------------------- the settle key is intact

def test_the_settle_key_is_untouched():
    """The reason `date` cannot simply be corrected: NFL results are
    filed under season + period, and `_hist_where` resolves the week
    label onto them. A bet whose `date` became an ISO Sunday would query
    a period nothing is filed under and sit open forever."""
    where, args = ledger._hist_where(
        {"sport": "nfl", "date": "2026-W01"})
    assert "season=?" in where and "period=?" in where
    assert args == ["nfl", 2026, "001"]


def test_the_journal_writes_both_and_they_disagree_only_for_football():
    """One row through the real writer, so the column list and the value
    tuple cannot drift apart — the failure mode of adding a column to a
    positional INSERT."""
    conn = _db()
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": "2026-W01",
        "recommendations": [{
            "player": "Puka Nacua", "market": "receptions", "side": "OVER",
            "line": 4.5, "odds": -115, "hit_prob": 0.62, "edge": 0.04,
            "confidence": 7.5, "grade": "Play", "stake_units": 0.3,
            "recommended": True, "has_market": True,
            "game_date": "2026-09-13", "book": "FanDuel"}]})
    row = conn.execute("SELECT date, game_day FROM bets").fetchone()
    assert row["date"] == "2026-W01", dict(row)
    assert row["game_day"] == "2026-09-13", dict(row)


# ---------------------------------------------------------- the backfill

def _hist():
    """A history DB holding one NFL week: Thursday, and two Sundays."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, "
        "game_id TEXT, home TEXT, away TEXT, date TEXT);"
        "CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
        "period TEXT, game_id TEXT, player TEXT, team TEXT, market TEXT);")
    for gid, home, away, day in (("NE@SEA", "SEA", "NE", "2026-09-10"),
                                 ("DAL@NYG", "NYG", "DAL", "2026-09-13"),
                                 ("GB@MIN", "MIN", "GB", "2026-09-13")):
        conn.execute("INSERT INTO games VALUES ('nfl',2026,'001',?,?,?,?)",
                     (gid, home, away, day))
    conn.execute("INSERT INTO player_game_logs VALUES "
                 "('nfl',2026,'001','GB@MIN','Jordan Love','GB','pass_yds')")
    # LOGGED LAST SEASON ONLY — no row for the week being placed, which
    # is every prop on a game that has not been played yet.
    conn.execute("INSERT INTO player_game_logs VALUES "
                 "('nfl',2025,'014','DAL@NYG','Malik Nabers','NYG','rec_yds')")
    conn.execute("INSERT INTO player_game_logs VALUES "
                 "('nfl',2025,'009','NE@SEA','Rhamondre Stevenson','NE','rush_yds')")
    # TWO MEN, ONE NAME, one week — the ambiguity the len()==1 guards
    # exist for. Shared names are ordinary in football rosters, and a
    # double-ingest produces the same shape.
    for gid in ("NE@SEA", "DAL@NYG"):
        conn.execute("INSERT INTO player_game_logs VALUES "
                     "('nfl',2026,'001',?,'Mike Williams','?','rec_yds')",
                     (gid,))
    # A DOUBLE-INGESTED GAME. `games` has no unique constraint, so one
    # fixture can appear twice — and then a team lookup answers twice
    # with what may be two different dates. Same guard, same reason.
    conn.execute("INSERT INTO games VALUES "
                 "('nfl',2026,'001','CHI@CAR','CAR','CHI','2026-09-13')")
    conn.execute("INSERT INTO games VALUES "
                 "('nfl',2026,'001','CHI@CAR','CAR','CHI','2026-09-14')")
    conn.commit()
    return conn


def _one_game_week():
    """A week with a single fixture — the opener, before the Sunday
    slate is ingested. Route 4 needs no evidence about the row at all."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, "
        "game_id TEXT, home TEXT, away TEXT, date TEXT);"
        "CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
        "period TEXT, game_id TEXT, player TEXT, team TEXT, market TEXT);")
    conn.execute("INSERT INTO games VALUES "
                 "('nfl',2026,'001','NE@SEA','SEA','NE','2026-09-10')")
    conn.commit()
    return conn


def _unstamped(conn, sport, date, player, market="moneyline"):
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "stake_units, status, category) "
        "VALUES (?,?,?,?, 'OVER', 0.5, -110, 1.0, 'won', 'main')",
        (sport, date, player, market))
    conn.commit()


def _day(conn, player):
    return conn.execute("SELECT game_day FROM bets WHERE player=?",
                        (player,)).fetchone()["game_day"]


def test_a_prop_lands_on_the_day_its_player_actually_played():
    """The strongest evidence available: the log row says which game he
    was on the field for, and that game has a kickoff date."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "Jordan Love", "pass_yds")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "Jordan Love") == "2026-09-13"
    assert res["filled"] == 1 and res["unresolved"] == 0, res


def test_a_prop_lands_when_every_club_the_player_could_be_on_plays_that_day():
    """The 206 rows of 2026-09-09: Week 1 props with no log row yet,
    because the games had not been played. His club from last season is
    not evidence about this week — players move — but the SCHEDULE is:
    NYG play Sunday, so a bet on a man who might be a Giant is on a
    Sunday game whether or not he still is one."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "Malik Nabers", "rec_yds")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "Malik Nabers") == "2026-09-13"
    assert res["by_route"].get("player's clubs all play that day") == 1, res


def test_a_prop_is_refused_when_his_clubs_play_on_different_days():
    """NE open on the Thursday. A player who could be a Patriot or a
    Giant has two possible days and the schedule does not settle it, so
    it stands down — which is the case where guessing costs most."""
    conn, hist = _db(), _hist()
    hist.execute("INSERT INTO player_game_logs VALUES "
                 "('nfl',2024,'003','DAL@NYG','Rhamondre Stevenson','NYG','rush_yds')")
    hist.commit()
    _unstamped(conn, "nfl", "2026-W01", "Rhamondre Stevenson", "rush_yds")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "Rhamondre Stevenson") is None
    assert res["unresolved"] == 1, res


def test_a_played_game_still_beats_the_schedule_inference():
    """Route 2 is exact — the log says which game he was ON THE FIELD
    for. It must be consulted first, or a man who moved mid-season gets
    placed by a club he no longer plays for."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "Jordan Love", "pass_yds")
    res = ledger.backfill_game_days(conn, hist)
    assert res["by_route"].get("player log") == 1, res


def test_a_game_bet_lands_via_the_team_it_names():
    """Moneyline, spread and team_total all store the team in `player`."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "SEA")
    ledger.backfill_game_days(conn, hist)
    assert _day(conn, "SEA") == "2026-09-10"


def test_a_game_total_lands_via_its_matchup_key():
    """A total stores AWAY@HOME with the spaces taken out, not a team."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "DAL@NYG", "total")
    ledger.backfill_game_days(conn, hist)
    assert _day(conn, "DAL@NYG") == "2026-09-13"


def test_a_row_that_cannot_be_placed_is_left_alone_and_counted():
    """It must not guess. Two Sundays in the week and no evidence which
    one — a wrong Sunday is invisible, a week label is visibly a week."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "Some Unknown Player", "rec_yds")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "Some Unknown Player") is None
    assert res["unresolved"] == 1 and res["filled"] == 0, res


def test_two_players_of_one_name_produce_no_guess():
    """The log join answers with two different games, so there is no
    answer. Taking the first would be a coin flip written into the money
    ledger — and it would look exactly like a fact afterwards."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "Mike Williams", "rec_yds")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "Mike Williams") is None, _day(conn, "Mike Williams")
    assert res["unresolved"] == 1, res


def test_a_daily_sport_is_copied_across_exactly():
    """MLB's date IS its day, so this is a copy and not an inference —
    and it is what gives the whole back catalogue a calendar for free."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "mlb", "2026-07-04", "Aaron Judge", "total_bases")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "Aaron Judge") == "2026-07-04"
    assert res["by_route"].get("already a day") == 1, res


def test_it_never_overwrites_a_day_already_stamped():
    """The journal is the money record. Stamped with a day the backfill
    would NOT have chosen, so "left alone" and "recomputed to the same
    answer" cannot be confused — the case that matters is a row somebody
    corrected by hand, which a re-run must not undo."""
    conn, hist = _db(), _hist()
    _settled(conn, "nfl", "2026-W01", "SEA", 0.9, game_day="2026-09-13")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "SEA") == "2026-09-13", _day(conn, "SEA")
    assert res["filled"] == 0 and res["unresolved"] == 0, res


def test_a_team_appearing_twice_in_a_week_produces_no_guess():
    """`games` carries no unique constraint, so a double ingest gives one
    team two rows — and here two different dates. Ambiguity is not a
    lookup failure and must not be resolved by taking the first."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "CAR")
    res = ledger.backfill_game_days(conn, hist)
    assert _day(conn, "CAR") is None, _day(conn, "CAR")
    assert res["unresolved"] == 1, res


def test_a_week_with_one_fixture_needs_no_evidence_about_the_row():
    """Route 4, and the case tonight is: the opener is the only NFL game
    ingested for Week 1 until the Sunday slate lands. Whoever the bet is
    on, there is only one day it can be."""
    conn = _db()
    _unstamped(conn, "nfl", "2026-W01", "Somebody Unknown", "rec_yds")
    res = ledger.backfill_game_days(conn, _one_game_week())
    assert _day(conn, "Somebody Unknown") == "2026-09-10"
    assert res["by_route"].get("only one day that week") == 1, res


def test_it_never_touches_the_settle_key():
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "SEA")
    ledger.backfill_game_days(conn, hist)
    row = conn.execute("SELECT date FROM bets").fetchone()
    assert row["date"] == "2026-W01", dict(row)


def test_a_dry_run_writes_nothing_and_reports_the_same_number():
    """A preview whose figures move when you commit is not a preview."""
    conn, hist = _db(), _hist()
    _unstamped(conn, "nfl", "2026-W01", "SEA")
    dry = ledger.backfill_game_days(conn, hist, dry_run=True)
    assert _day(conn, "SEA") is None
    wet = ledger.backfill_game_days(conn, hist)
    assert dry["filled"] == wet["filled"] == 1, (dry, wet)
    assert _day(conn, "SEA") == "2026-09-10"


def test_an_unreadable_history_db_leaves_the_journal_alone():
    """No bridge is the state every one of these rows is already in. A
    backfill must never be the thing that breaks the ledger."""
    conn = _db()
    broken = sqlite3.connect(":memory:")          # no games table at all
    _unstamped(conn, "nfl", "2026-W01", "SEA")
    res = ledger.backfill_game_days(conn, broken)
    assert res["unresolved"] == 1
    assert _day(conn, "SEA") is None


def test_the_flag_is_wired_and_dry_by_default():
    """It edits the money ledger. A flag that rewrites 2.2 MB of history
    on a typo is the wrong default."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--backfill-days"' in src
    assert 'backfill_days(dry_run="--apply" not in argv)' in src
    fn = src.split("def backfill_days", 1)[1].split("\ndef ", 1)[0]
    assert "dry_run: bool = True" in src.split("def backfill_days", 1)[1][:60]
    assert "--apply" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
