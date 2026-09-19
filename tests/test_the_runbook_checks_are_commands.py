"""The droplet checks run as commands, not as pasted heredocs.

Ethan, 2026-09-16, after running five blocks from WHEN_YOU_ARE_HOME
cleanly: "i couldnt get that last command to work". The five that worked
were one line each. The one that did not was a thirty-line
`python3 - <<'PY'` heredoc, and a heredoc pasted into an interactive
shell fails in a dozen ways that have nothing to do with the question:
a stray ^C, a client that reflows long lines, a paste landing while the
previous command is still printing.

`homecheck.py` is those checks as subcommands. What this file defends is
the three properties that make it worth having: it never throws at the
caller, one check's failure does not take the run down with it, and the
runbook actually points at it.

Run directly: `python3 tests/test_the_runbook_checks_are_commands.py`
"""

import io
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import homecheck                                              # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")


def _capture(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = homecheck.main(argv)
    return code, buf.getvalue()


def _board(rows):
    return {"game_bets": rows}


def _swap(rows_by_sport):
    """Stand in for the board reader. THE TESTS DO NOT READ THIS BOX —
    a check that passes because the dev box happens to have a board is a
    check that says nothing on the box it was written for."""
    real = homecheck._board

    def fake(sport):
        if sport not in rows_by_sport:
            raise FileNotFoundError(f"no board for {sport}")
        return _board(rows_by_sport[sport])
    homecheck._board = fake
    return real


# --- it answers the question -------------------------------------------------
def test_a_filler_row_is_counted_and_named_by_market():
    real = _swap({"mlb": [
        {"odds": -110, "book": "", "bet_type": "team_total"},
        {"odds": -110, "book": "", "bet_type": "total"},
        {"odds": -110, "book": "DraftKings", "bet_type": "total"},
        {"odds": -135, "book": "", "bet_type": "moneyline"},
    ]})
    try:
        out = "\n".join(homecheck.filler())
    finally:
        homecheck._board = real
    line = [x for x in out.splitlines() if x.strip().startswith("mlb")][0]
    assert "4 game rows" in line, line
    # Three rows name no book; only the two at -110 are FILLER prices.
    assert "3 name no book" in line, line
    assert "2 at a filler price" in line, line
    assert "team_total" in line and "total" in line, line


def test_a_clean_board_reports_zero_rather_than_nothing():
    """A check that prints nothing when the answer is good is a check
    nobody can tell apart from a check that did not run."""
    real = _swap({"mlb": [{"odds": -135, "book": "FanDuel",
                           "bet_type": "moneyline"}]})
    try:
        out = "\n".join(homecheck.filler())
    finally:
        homecheck._board = real
    assert "0 at a filler price" in out, out


def test_a_league_with_no_board_names_itself_and_the_others_still_print():
    real = _swap({"nfl": [{"odds": -110, "book": "", "bet_type": "total"}]})
    try:
        out = "\n".join(homecheck.filler())
    finally:
        homecheck._board = real
    assert "mlb" in out and "cannot read board" in out, out
    assert "1 at a filler price" in out, "the league that HAS a board was lost"


def test_an_unbooked_row_that_is_still_recommended_is_shouted_about():
    """#207 sets `recommended = False` on a row whose price names no
    book. Ethan's board carries 32 unbooked NFL rows; this is the line
    that says whether any of them is being pushed at a reader."""
    real = _swap({"mlb": [
        {"odds": -135, "book": "", "bet_type": "moneyline",
         "recommended": True},
        {"odds": -135, "book": "", "bet_type": "spread"},
    ]})
    try:
        out = "\n".join(homecheck.filler())
    finally:
        homecheck._board = real
    assert "1 of those unbooked rows are still RECOMMENDED" in out, out
    assert "#207" in out, out


def test_unbooked_rows_that_are_not_recommended_say_nothing_extra():
    """The ordinary case. A warning that fires every run is not read."""
    real = _swap({"mlb": [{"odds": -135, "book": "", "bet_type": "spread"}]})
    try:
        out = "\n".join(homecheck.filler())
    finally:
        homecheck._board = real
    assert "RECOMMENDED" not in out, out


# --- it never throws at the caller -------------------------------------------
def test_one_check_blowing_up_does_not_take_the_run_with_it():
    """`all` exists so one paste returns everything. A traceback in the
    middle would truncate the rest of the output, which is the half the
    reader was going to send back."""
    real = homecheck.CHECKS["filler"]

    def boom():
        raise ValueError("pretend the board moved")
    homecheck.CHECKS["filler"] = (boom, real[1], True)
    try:
        code, out = _capture(["all"])
    finally:
        homecheck.CHECKS["filler"] = real
    assert code == 0, code
    assert "filler: FAILED" in out and "pretend the board moved" in out, out
    assert "HEAD:" in out, "the checks after the failure did not run"


def test_an_unknown_check_lists_the_real_ones_instead_of_failing_silently():
    code, out = _capture(["nonsense"])
    assert code == 2
    for name in homecheck.CHECKS:
        assert name in out, out
    assert "all" in out


def test_help_exits_clean_and_names_every_check():
    """Run as a SUBPROCESS, because `--help` crashing the parser is a
    failure this project has already shipped once (potd_backtest, a bare
    % in argparse help text)."""
    got = subprocess.run([sys.executable, str(ROOT / "homecheck.py"), "--help"],
                         capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
    for name in homecheck.CHECKS:
        assert name in got.stdout, got.stdout


def test_no_argument_is_help_rather_than_a_crash():
    code, out = _capture([])
    assert code == 0 and "checks:" in out


# --- the fetching one says so ------------------------------------------------
def test_the_only_check_that_fetches_is_kept_out_of_all():
    """`all` is what a person pastes without reading. It must not reach
    the network or write a cache file, because doing that as root is
    what left 6,098 root-owned entries on the droplet."""
    assert homecheck.CHECKS["exchange"][2] is False
    for name, (_fn, _desc, auto) in homecheck.CHECKS.items():
        if auto:
            assert name != "exchange"


def test_the_fetching_check_warns_when_it_is_run_as_root():
    """OFFLINE. `exchange` takes its fetcher as an argument for exactly
    this reason — an earlier version of this test called the real one and
    put twenty refused CONNECTs through the proxy on every gate run."""
    real = os.geteuid
    os.geteuid = lambda: 0
    try:
        out = "\n".join(homecheck.exchange(fetch=lambda: ([], {})))
    finally:
        os.geteuid = real
    assert "root" in out.lower(), out
    assert "sudo -u qellys" in out, out


def test_a_feed_that_does_not_answer_is_reported_not_raised():
    def boom():
        raise OSError("connection refused")
    out = "\n".join(homecheck.exchange(fetch=boom))
    assert "the feed did not answer" in out and "connection refused" in out, out


def test_the_ticker_shapes_are_what_gets_printed():
    """The whole reason KX-2 exists: the four fields that say whether the
    club pair is in the ticker."""
    market = {"ticker": "KXMLBGAME-26AUG111840CLEDET-CLE",
              "event_ticker": "KXMLBGAME-26AUG111840CLEDET",
              "title": "Cleveland wins", "subtitle": "Cleveland",
              "price_basis": "book", "spread_cents": 2.0, "prob": 0.58,
              "volume_24h": 5000.0, "open_interest": 5000.0}
    out = "\n".join(homecheck.exchange(fetch=lambda: ([market], {"x": 1})))
    assert "26AUG111840CLEDET" in out, out
    assert "series report" in out, out


# --- the runbook points at it ------------------------------------------------
def test_the_runbook_names_the_command_rather_than_a_heredoc():
    """The whole point. A check that exists and is not in the file Ethan
    pastes from is a check that does not exist."""
    assert "homecheck.py filler" in DOC, \
        "the FILLER block still asks for a heredoc"


def test_every_check_this_script_offers_is_reachable_from_the_runbook():
    missing = [name for name in CHECK_NAMES if f"homecheck.py {name}" not in DOC]
    assert not missing, (
        f"these checks are not named anywhere in WHEN_YOU_ARE_HOME.md, so "
        f"nobody will run them: {missing}")


# --- LIVE: the tab that could not tell an empty tracker from a quiet night ---
def _swap_boards(boards):
    """Whole boards, not just game rows. Same rule as `_swap`: THE TESTS
    DO NOT READ THIS BOX."""
    real = homecheck._board

    def fake(sport):
        if sport not in boards:
            raise FileNotFoundError(f"no board for {sport}")
        return boards[sport]
    homecheck._board = fake
    return real


def _swap_journal(rows):
    """An in-memory journal holding ``(sport, date, category)`` rows.

    A real sqlite, so the check's own SQL is what is being exercised —
    a hand-built stub returning the shape the check wants would test the
    stub. In memory, so nothing on this box is opened or locked.
    """
    import sqlite3
    real = homecheck._journal_ro
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, date TEXT, category TEXT, "
                 "status TEXT)")
    conn.executemany("INSERT INTO bets VALUES (?,?,?, 'open')", rows)
    homecheck._journal_ro = lambda: (conn, "")
    return real


def _live(boards, rows):
    real_b = _swap_boards(boards)
    real_j = _swap_journal(rows)
    try:
        return "\n".join(homecheck.live())
    finally:
        homecheck._board = real_b
        homecheck._journal_ro = real_j


def test_the_two_numbers_that_have_to_agree_are_printed_together():
    """The board's tracked count and the journal's open count, on
    adjacent lines. Either alone answers nothing."""
    out = _live({"nfl": {"date": "2026-W03",
                         "live_picks": [{"phase": "live", "category": "main"},
                                        {"phase": "upcoming", "category": "likely"}],
                         "live_potd": [{}]}},
                [("nfl", "2026-W03", "main"), ("nfl", "2026-W03", "likely")])
    assert "board date 2026-W03" in out, out
    assert "2 tracked (1 live, 1 likely)" in out, out
    assert "1 pick of the day" in out, out
    assert "journal: 2 open nfl bet(s)" in out, out


def test_the_journal_line_the_tracker_can_actually_see_is_marked():
    """`open_bets_for` matches `date` EXACTLY. Which of the journal's
    dates is the board's is the whole diagnosis, so it is marked rather
    than left to be eyeballed against a label three lines up."""
    out = _live({"nfl": {"date": "2026-W03", "live_picks": [{"phase": "live"}]}},
                [("nfl", "2026-W03", "main"), ("nfl", "2026-W02", "main")])
    hit = [x for x in out.splitlines() if "2026-W03" in x and "main" in x][0]
    miss = [x for x in out.splitlines() if "2026-W02" in x][0]
    assert "<- the board's date" in hit, hit
    assert "<- the board's date" not in miss, (
        "a date the tracker cannot see is marked as one it can: " + miss)


def test_bets_filed_under_a_date_the_tracker_cannot_match_are_shouted_about():
    """The failure this check exists for, and the one that is invisible
    from the page: a tracker whose exact match finds nothing draws the
    same thing as a night with no bets.

    NOTE THE SHAPE. These rows are under 2026-W02 and the board is on
    W03, so the count of rows the tracker CAN reach is zero — which is
    why a single `reachable and not drawn` condition is a dead guard
    here and the two failures are reported separately."""
    out = _live({"nfl": {"date": "2026-W03", "live_picks": [], "live_potd": []}},
                [("nfl", "2026-W02", "main"), ("nfl", "2026-W02", "likely")])
    assert "invisible on the Live tab" in out, out
    assert "2 row(s) in books the tab draws" in out, out
    assert "0 tracked" in out and "journal: 2 open nfl bet(s)" in out, out
    # AND NOT ALSO AS A SETTLING NOTE. These are main and likely rows —
    # bets the tab is supposed to draw — so calling them measurement rows
    # under a past slate reports one fault as two and buries the loud one.
    assert "measurement row(s) still open" not in out, out


def test_a_tracker_that_misses_rows_on_its_own_date_is_a_louder_problem():
    """The other failure: the rows are right there, under the board's own
    date, in a book the tab draws, and nothing was tracked."""
    out = _live({"nfl": {"date": "2026-W03", "live_picks": [], "live_potd": []}},
                [("nfl", "2026-W03", "main"), ("nfl", "2026-W03", "likely")])
    assert "the tracker itself is not working" in out, out
    assert "invisible on the Live tab" not in out, (
        "the rows ARE on the board's date; calling them mis-filed sends "
        "the reader after the wrong thing:\n" + out)


def test_a_measurement_book_is_never_counted_as_a_missing_bet():
    """Ethan's 2026-09-18 run: `nfl 39 tracked` over `journal: 101 open`
    — a 62-row gap with not one row missing. 59 were `stale`, the
    line-staleness shadow book, which the Live tab has never drawn and
    should not. Counting those made a healthy league read as a hole."""
    out = _live({"nfl": {"date": "2026-W02",
                         "live_picks": [{"phase": "live", "category": "main"}],
                         "live_potd": []}},
                [("nfl", "2026-W02", "main")]
                + [("nfl", "2026-W02", "stale")] * 59)
    assert "60 open nfl bet(s) — 1 in the books the Live tab draws" in out, out
    assert "measurement book, never on the tab" in out, out
    assert "1 drawn (1 tracked + 0 pick of the day) vs 1 reachable" in out, out
    assert "!!" not in out, "a healthy league is being shouted about:\n" + out


def test_the_books_the_tab_draws_come_from_the_engine_not_a_copy():
    """A second list here would drift the first time a book is added,
    and this check would go on calling the new one invisible."""
    import inspect
    body = inspect.getsource(homecheck.live).split('"""')[-1]
    assert "TRACKER_CATEGORIES" in body and "POTD_TRACKER_CATEGORIES" in body, \
        "the shown-book list is hand-written rather than imported"


def test_a_stranded_measurement_row_gets_a_note_not_an_alarm():
    """An NFL `stale` flag still open under 2026-W01 a week later is a
    settling gap. Real, and not the thing the reader came here for."""
    out = _live({"nfl": {"date": "2026-W02",
                         "live_picks": [{"phase": "live", "category": "main"}]}},
                [("nfl", "2026-W02", "main"), ("nfl", "2026-W01", "stale")])
    assert "1 measurement row(s) still open under a past slate" in out, out
    assert "invisible on the Live tab" not in out, (
        "a measurement row is being reported as a tracking failure:\n" + out)


def test_a_genuinely_quiet_league_is_not_shouted_about():
    """Nothing journaled and nothing tracked is the tab being right. A
    warning that fires on a quiet Tuesday is a warning nobody reads."""
    out = _live({"nfl": {"date": "2026-W03", "live_picks": [], "live_potd": []}},
                [])
    assert "tracks NONE" not in out, out
    assert "0 tracked" in out, "a zero still has to be printed"


def test_a_tracker_that_threw_says_so_instead_of_reading_as_empty():
    """`attach_tracker` writes its own failure into the board precisely
    so it is not read as a zero."""
    out = _live({"nfl": {"date": "2026-W03", "live_picks": [],
                         "live_picks_error": "no such column: leg"}},
                [])
    assert "live_picks_error: no such column: leg" in out, out


def test_a_board_that_cannot_be_read_does_not_take_the_other_leagues():
    out = _live({"nfl": {"date": "2026-W03", "live_picks": [{"phase": "live"}]}},
                [("nfl", "2026-W03", "main")])
    assert "mlb" in out and "cannot read board" in out, out
    assert "1 tracked" in out, "the league that HAS a board was lost"


def test_the_journal_is_opened_read_only_and_from_the_right_file():
    """Two mistakes this repo has already made, in one function.

    `ledger.connect()` runs the migrations and the schema script on the
    first connection in a process — writes, on the file the refresher
    and the settler are using — and every subcommand here is advertised
    as safe to run mid-cycle. `db.connect()` opens history.db, which has
    no `bets` table; that swap cost Ethan a runbook command on
    2026-09-16 and came back as a bare sqlite error.
    """
    import inspect
    # THE CODE, NOT THE DOCSTRING. The first draft of this searched the
    # whole source and failed on the function's own explanation of why
    # `ledger.connect()` is wrong — an assertion matching the prose that
    # documents the fix rather than the fix.
    body = inspect.getsource(homecheck._journal_ro).split('"""')[-1]
    assert "mode=ro" in body, \
        "the journal is opened writable — it can take the exclusive lock"
    assert "ledger.DEFAULT_DB" in body, \
        "the journal is not read from the ledger's own path"
    assert "ledger.connect(" not in body, \
        "ledger.connect() migrates and writes on first use in a process"
    assert "db.connect(" not in body, \
        "that is history.db, which has no `bets` table"


def test_the_live_check_runs_inside_the_daily_paste():
    """A check outside `all` is a check nobody runs twice."""
    assert homecheck.CHECKS["live"][2] is True, \
        "`live` is excluded from `all`, so the daily paste will not carry it"


# --- GRADING: a book that can never close a bet ------------------------------
def _grading(counts, stuck=(), category="main"):
    """`counts` is (sport, status, n); `stuck` is (sport, reason) rows as
    `ledger.why_open` would return them. `category` names the book the
    rows land in — the Record page keeps three and ignores the rest."""
    import sqlite3
    from engine import ledger
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # A `date` column, because the check reports which slates were
    # journaled and a fixture without one exercises its error path
    # instead of its answer.
    conn.execute("CREATE TABLE bets (sport TEXT, status TEXT, date TEXT, "
                 "category TEXT)")
    for sport, status, n in counts:
        conn.executemany("INSERT INTO bets VALUES (?,?,'2026-09-17',?)",
                         [(sport, status, category)] * n)
    real_j, real_h = homecheck._journal_ro, homecheck._history_ro
    real_w = ledger.why_open
    homecheck._journal_ro = lambda: (conn, "")
    homecheck._history_ro = lambda: (sqlite3.connect(":memory:"), "")
    ledger.why_open = lambda *a, **k: [{"sport": sp, "reason": why}
                                       for sp, why in stuck]
    try:
        return "\n".join(homecheck.grading())
    finally:
        homecheck._journal_ro, homecheck._history_ro = real_j, real_h
        ledger.why_open = real_w


def test_settled_and_open_are_printed_side_by_side():
    """"0 open past the window" means nothing alone: a league that has
    graded four hundred bets and one that has never graded any can both
    be quiet today."""
    out = _grading([("mlb", "won", 21), ("mlb", "lost", 11),
                    ("mlb", "open", 1)])
    assert "32 settled" in out and "1 open" in out, out
    assert "won 21" in out and "lost 11" in out, out


def test_a_book_that_has_never_closed_a_bet_is_shouted_about():
    """Ethan, 2026-09-18: "CFB still hasn't graded any edge bets or most
    likely bets." A league with open rows and nothing settled is not a
    quiet week."""
    out = _grading([("cfb", "open", 34)])
    assert "HAS NEVER GRADED A BET" in out, out
    assert "34 open, 0 settled" in out, out


def test_a_league_that_has_graded_is_not_shouted_about():
    """The warning has to stay rare or it stops being read."""
    out = _grading([("mlb", "won", 5), ("mlb", "open", 2)])
    assert "HAS NEVER GRADED" not in out, out


def test_results_that_were_never_stored_are_named_as_the_ingest_s_problem():
    """The distinction the whole check exists for: a bet waiting on
    Saturday's kickoff and a bet waiting on a feed that stopped landing
    in August look identical from the journal."""
    out = _grading([("cfb", "open", 3)],
                   stuck=[("cfb", "no results ingested")] * 3)
    assert "waiting on results that were never stored" in out, out
    assert "the ingest is the fix, not the settler" in out, out
    assert "3 stuck past the settle window — no results ingested" in out, out


def test_a_stuck_reason_that_is_not_the_ingest_is_reported_without_the_alarm():
    """"player has no log" is a scratch or a spelling, and a person
    fixes it. It gets a line, not a shout."""
    out = _grading([("nfl", "won", 4), ("nfl", "open", 2)],
                   stuck=[("nfl", "player has no log")] * 2)
    assert "player has no log" in out, out
    assert "the ingest is the fix" not in out, out


def test_the_reasons_come_from_the_ledger_not_a_second_opinion():
    """`ledger.why_open` already classifies every stuck bet and is what
    `doctor.py` reads. A second classifier here would drift from it, and
    then two commands would disagree about the same bet."""
    import inspect
    body = inspect.getsource(homecheck.grading).split('"""')[-1]
    assert "ledger.why_open" in body, \
        "the stuck reasons are being derived here instead of read"
    assert "no results ingested" in body, \
        "the loud case is not keyed to a reason the ledger actually emits"


def test_the_history_db_is_opened_read_only():
    """Same promise as the journal: every check here is safe mid-cycle,
    and `db.connect()` runs the schema on first use in a process."""
    import inspect
    body = inspect.getsource(homecheck._history_ro).split('"""')[-1]
    assert "mode=ro" in body, "the results DB is opened writable"
    assert "db.DEFAULT_DB" in body, "not the history database's own path"
    assert "db.connect(" not in body, \
        "db.connect() creates the schema on first use in a process"


def test_each_book_says_whether_it_reaches_the_record_page():
    """Ethan, 2026-09-18: "CFB still hasn't graded any edge bets or most
    likely bets." The 2026-09-19 run: `cfb 446 settled`. Both true — the
    Record page keeps three books and `stale` is not one of them."""
    out = _grading([("cfb", "won", 156), ("cfb", "lost", 171),
                    ("cfb", "void", 119)], category="stale")
    assert "shadow book, never on the Record page" in out, out
    assert "stale" in out and "446 settled" in out, out


def test_a_league_whose_whole_record_is_a_shadow_book_is_shouted_about():
    """446 settled and a blank Record page is the exact complaint, and a
    per-sport total cannot tell it from a healthy league."""
    out = _grading([("cfb", "won", 156), ("cfb", "lost", 171)],
                   category="stale")
    assert "NOTHING CFB HAS SETTLED REACHES THE RECORD PAGE" in out, out


def test_a_book_that_is_on_the_page_is_not_shouted_about():
    out = _grading([("mlb", "won", 21), ("mlb", "lost", 11)],
                   category="main")
    assert "Record page \u2192 edge" in out, out
    assert "REACHES THE RECORD PAGE" not in out, out


def test_a_league_that_has_graded_nothing_is_not_told_its_rows_are_misfiled():
    """The NFL case: 0 settled in any book. Saying its graded rows are
    in the wrong place describes rows that do not exist — the
    never-graded shout is the true one."""
    out = _grading([("nfl", "open", 13)], category="main")
    assert "NOTHING NFL HAS SETTLED REACHES" not in out, out
    assert "HAS NEVER GRADED A BET" in out, out


def test_the_sections_come_from_the_ledger_not_a_copy():
    """`BOOK_SECTIONS` is what the Record page itself renders from. A
    second list here would say a book is on the page after the page
    stopped showing it."""
    import inspect
    body = inspect.getsource(homecheck.grading).split('"""')[-1]
    assert "BOOK_SECTIONS" in body, \
        "the section map is hand-written rather than read from the ledger"


def test_how_many_slates_were_journaled_is_printed():
    """Ethan, 2026-09-19: "can we still fill the record page with all the
    bets that we have made since week zero". The answer is the set of
    rows in the journal and nothing else, so the check has to say how
    many days of the season were actually written down."""
    out = _grading([("cfb", "open", 34)])
    assert "slate(s) journaled" in out, out


def test_a_single_slate_season_is_visible_as_one_line():
    """The shape that answers the question: a league that has been
    publishing boards for a month and journaled one day of them."""
    import sqlite3
    from engine import ledger
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, status TEXT, date TEXT)")
    conn.executemany("INSERT INTO bets VALUES ('cfb','open',?)",
                     [("2026-09-17",)] * 34)
    real_j, real_h = homecheck._journal_ro, homecheck._history_ro
    real_w = ledger.why_open
    homecheck._journal_ro = lambda: (conn, "")
    homecheck._history_ro = lambda: (sqlite3.connect(":memory:"), "")
    ledger.why_open = lambda *a, **k: []
    try:
        out = "\n".join(homecheck.grading())
    finally:
        homecheck._journal_ro, homecheck._history_ro = real_j, real_h
        ledger.why_open = real_w
    assert "1 slate(s) journaled, 2026-09-17 \u2192 2026-09-17" in out, out
    assert "2026-09-17      34 bet(s)" in out, out


def test_a_long_season_is_summarised_rather_than_listed():
    """Thirty MLB slates must not print thirty lines into a paste that
    has four other leagues to get through."""
    import sqlite3
    from engine import ledger
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, status TEXT, date TEXT)")
    days = [f"2026-07-{d:02d}" for d in range(1, 31)]
    conn.executemany("INSERT INTO bets VALUES ('mlb','won',?)",
                     [(d,) for d in days])
    real_j, real_h = homecheck._journal_ro, homecheck._history_ro
    real_w = ledger.why_open
    homecheck._journal_ro = lambda: (conn, "")
    homecheck._history_ro = lambda: (sqlite3.connect(":memory:"), "")
    ledger.why_open = lambda *a, **k: []
    try:
        out = "\n".join(homecheck.grading())
    finally:
        homecheck._journal_ro, homecheck._history_ro = real_j, real_h
        ledger.why_open = real_w
    assert "30 slate(s) journaled, 2026-07-01 \u2192 2026-07-30" in out, out
    assert "2026-07-15" not in out, "thirty lines were printed:\n" + out


def test_the_grading_check_runs_inside_the_daily_paste():
    assert homecheck.CHECKS["grading"][2] is True, \
        "`grading` is excluded from `all`, so nobody will run it twice"


# --- RECORD: the artifact the page renders, against the journal -------------
def _record(doc, graded=()):
    """`doc` stands in for record.json; `graded` is (sport, n) rows the
    journal has settled into books the Record page renders."""
    import json as _json
    import sqlite3
    import tempfile
    from pathlib import Path as _P
    from engine import gate, ledger
    tmp = _P(tempfile.mkdtemp()) / "record.json"
    tmp.write_text(_json.dumps(doc), encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bets (sport TEXT, date TEXT, status TEXT, "
                 "category TEXT)")
    for sport, n in graded:
        conn.executemany(
            "INSERT INTO bets VALUES (?, '2026-09-10', 'won', 'likely')",
            [(sport,)] * n)
    real_src, real_j = gate.board_source, homecheck._journal_ro
    gate.board_source = lambda _p: tmp
    homecheck._journal_ro = lambda: (conn, "")
    try:
        return "\n".join(homecheck.record())
    finally:
        gate.board_source, homecheck._journal_ro = real_src, real_j


def _doc(**kw):
    base = {"generated_at": "2026-09-19T00:00:00", "record_epoch": "2026-08-06",
            "tracked_sports": ["cfb", "mlb"], "by_sport": {}, "book_records": {}}
    base.update(kw)
    return base


def test_a_league_the_journal_graded_and_the_file_lost_is_shouted_about():
    """Ethan, 2026-09-19: `grading` showed cfb with 285 likely, 8 main
    and 1 longshot settled — all three rendered books — and the page
    showed him nothing. Every layer between is generic, so the artifact
    is where the two can disagree."""
    out = _record(_doc(), graded=[("cfb", 294)])
    assert "the journal has graded 294 cfb bet(s)" in out, out
    assert "the export is the gap, not the journal" in out, out


def test_a_league_the_file_carries_is_not_shouted_about():
    out = _record(_doc(book_records={"cfb": {"likely": {"w": 200, "l": 94}}}),
                  graded=[("cfb", 294)])
    assert "the export is the gap" not in out, out
    assert "likely 294" in out, out


def test_a_partial_export_says_how_many_rows_were_lost():
    out = _record(_doc(book_records={"cfb": {"likely": {"w": 100, "l": 94}}}),
                  graded=[("cfb", 294)])
    # Re-worded 2026-09-19. Both numbers are W-L now, not settled: the
    # journal side used to count pushes against a file count that never
    # could, and reported nine phantom missing MLB rows for it.
    assert "journal 294 W-L, file 194" in out, out
    assert "100 graded row(s) did not reach the page" in out, out


def test_a_stale_export_is_named_as_stale():
    """A page rendering a twelve-hour-old file looks exactly like a page
    rendering a broken one."""
    out = _record(_doc(generated_at="2020-01-01T00:00:00"))
    assert "STALE — the page is rendering an old export" in out, out


def test_a_fresh_export_is_not_called_stale():
    import datetime as dt
    now = dt.datetime.now().replace(microsecond=0).isoformat()
    out = _record(_doc(generated_at=now))
    assert "STALE" not in out, out


def test_the_epoch_is_printed_because_it_legitimately_hides_rows():
    """`RECORD_EPOCH` is a real reason for a league to be absent, and a
    reader chasing a missing section needs to rule it out first."""
    out = _record(_doc())
    assert "record_epoch 2026-08-06" in out, out
    assert "NOT in the public record" in out, out


def test_a_missing_file_is_reported_not_raised():
    import json as _json
    import tempfile
    from pathlib import Path as _P
    from engine import gate
    real = gate.board_source
    gate.board_source = lambda _p: _P(tempfile.mkdtemp()) / "nope.json"
    try:
        out = "\n".join(homecheck.record())
    finally:
        gate.board_source = real
    assert "cannot read record.json" in out, out


def test_the_record_check_runs_inside_the_daily_paste():
    assert homecheck.CHECKS["record"][2] is True


CHECK_NAMES = tuple(homecheck.CHECKS)


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
