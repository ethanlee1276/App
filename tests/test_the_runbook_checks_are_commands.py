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
