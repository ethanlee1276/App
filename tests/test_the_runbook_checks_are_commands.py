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
