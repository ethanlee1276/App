"""The prices we already hold at the moment the news breaks get written down.

Ethan, 2026-09-19, after `homecheck.py data` finally ran clean:

    nfl  1554 filings · 737 never quoted · 817 quoted, but never within 24h

Eight hundred of those are men the books price every week. We hold no
number from the hours the news lands in — not because the measurement is
impossible, but because nobody wrote the price down. Only the PAID
historical harvest stores a prop row, and it snapshots near kickoff while
injury news breaks midweek.

This is `engine/lineledger.py`'s bug one table over: *"the prices are
already in memory when this runs; the only thing that was missing was
writing them down."* Props never got that treatment.

THE TWO BOUNDS ARE THE POINT, and both are tested here. An NFL slate is
tens of thousands of quotes a build and hundreds of thousands a day,
which this box does not have the disk for. So the tape stores only men
carrying a designation — it exists to measure injury news, so a man
nobody filed anything about is not its business — and only when the
number actually moved. A quiet market has to be free, or the second bound
is decoration.

Run directly: `python3 tests/test_the_prop_prices_around_the_news_are_kept.py`
"""

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db as hist_db                               # noqa: E402
from engine import proptape as pt                              # noqa: E402

NOW = _dt.datetime(2026, 9, 19, 15, 0, tzinfo=_dt.timezone.utc)


class _Line:
    def __init__(self, book, line, over=-110, under=-110):
        self.book, self.line = book, line
        self.over_odds, self.under_odds = over, under


class _Prop:
    def __init__(self, player, market="rec_yds", team="PHI", lines=()):
        self.player, self.market, self.team = player, market, team
        self.lines = list(lines)


class _Slate:
    def __init__(self, props=(), games=()):
        self.props, self.games = list(props), list(games)


def _game(home="PHI", away="DAL", date="2026-09-21"):
    return {"home": home, "away": away, "date": date}


def _conn():
    return hist_db.connect(":memory:")


def _file(conn, player, sport="nfl", status="Questionable", seen=None):
    conn.execute(
        "INSERT OR REPLACE INTO injury_events (sport, player, team, status, "
        "posted_at, first_seen, injury, pos) VALUES (?,?,'PHI',?,'',?,'','')",
        (sport, player, status,
         seen or NOW.strftime("%Y-%m-%dT%H:%M:00Z")))
    conn.commit()


def _slate(player="A.J. Brown", **kw):
    return _Slate([_Prop(player, lines=[_Line("DK", 62.5)], **kw)],
                  [_game()])


# --- the bound that makes this affordable ------------------------------
def test_a_man_nobody_has_filed_anything_about_is_not_stored():
    """THE VOLUME BOUND. An NFL slate is tens of thousands of quotes a
    build. This tape measures injury news, so a healthy man is not its
    business — and storing him would cost the disk this box does not
    have."""
    conn = _conn()
    _file(conn, "Someone Else")
    assert pt.record(conn, "nfl", _slate("A.J. Brown"), NOW) == 0


def test_a_man_on_the_injury_report_is_stored():
    conn = _conn()
    _file(conn, "A.J. Brown")
    assert pt.record(conn, "nfl", _slate("A.J. Brown"), NOW) == 1


def test_an_unchanged_number_is_not_stored_twice():
    """THE OTHER BOUND. A line that has not moved is a row we already
    hold; storing it again costs a row per build forever. A quiet market
    has to be FREE or the bound is decoration."""
    conn = _conn()
    _file(conn, "A.J. Brown")
    assert pt.record(conn, "nfl", _slate(), NOW) == 1
    later = NOW + _dt.timedelta(minutes=45)
    assert pt.record(conn, "nfl", _slate(), later) == 0


def test_a_moved_line_is_stored():
    """And the move — the event we are trying to catch — is what we pay
    for."""
    conn = _conn()
    _file(conn, "A.J. Brown")
    pt.record(conn, "nfl", _slate(), NOW)
    moved = _Slate([_Prop("A.J. Brown", lines=[_Line("DK", 55.5)])], [_game()])
    assert pt.record(conn, "nfl", moved, NOW + _dt.timedelta(minutes=45)) == 1


def test_a_moved_PRICE_at_the_same_line_is_stored():
    """The number that moves first on injury news is often the juice,
    not the line. Comparing lines alone would miss the early half of
    every repricing."""
    conn = _conn()
    _file(conn, "A.J. Brown")
    pt.record(conn, "nfl", _slate(), NOW)
    rejuiced = _Slate(
        [_Prop("A.J. Brown", lines=[_Line("DK", 62.5, over=-155)])], [_game()])
    assert pt.record(conn, "nfl", rejuiced,
                     NOW + _dt.timedelta(minutes=45)) == 1


def test_one_build_cannot_write_more_than_the_ceiling():
    """A bad watchlist or a feed that reprices everything at once costs a
    bounded write, not the disk."""
    conn = _conn()
    props = []
    for i in range(pt.MAX_ROWS + 50):
        _file(conn, f"Player {i}")
        props.append(_Prop(f"Player {i}", lines=[_Line("DK", 10.5 + i)]))
    n = pt.record(conn, "nfl", _Slate(props, [_game()]), NOW)
    assert n == pt.MAX_ROWS, n


# --- it has to be readable by the thing that asked for it --------------
def test_the_stored_name_is_the_books_spelling():
    """`odds_history` holds `normalize_name(player)`, and `injurylag`
    looks him up that way. A fourth spelling of a man here recreates the
    join that cost 2026-09-19."""
    from engine.sources.oddsapi import normalize_name
    conn = _conn()
    _file(conn, "A.J. Terrell Jr.")
    pt.record(conn, "nfl", _slate("A.J. Terrell Jr."), NOW)
    got = conn.execute("SELECT player FROM odds_history").fetchone()[0]
    assert got == normalize_name("A.J. Terrell Jr."), got
    assert got == "a j terrell", got


def test_the_stamp_matches_the_store_it_will_be_joined_against():
    """`newstape` and `lineledger` both write minute-resolution UTC.
    Three tables meant to be read against each other cannot each pick
    their own time format."""
    from engine import lineledger, newstape
    assert pt._stamp(NOW) == lineledger._stamp(NOW) == newstape._stamp(NOW)


def test_a_stored_price_becomes_a_measurable_filing():
    """THE WHOLE POINT, end to end and through the real code path: two
    prices stored by this tape either side of a filing have to turn that
    filing from "never quoted" into one `injurylag` can measure.

    Written by hand at first against bounds the test built itself, which
    proved only that the test could build bounds. Going through
    `measure` is what caught the window skew below."""
    from engine import injurylag as il
    conn = _conn()
    _file(conn, "A.J. Brown")
    before = NOW - _dt.timedelta(hours=2)
    after = NOW + _dt.timedelta(hours=2)
    pt.record(conn, "nfl", _slate(), before)
    pt.record(conn, "nfl",
              _Slate([_Prop("A.J. Brown", lines=[_Line("DK", 55.5)])],
                     [_game()]), after)
    got = il.measure(conn, sport="nfl")["nfl"]
    assert got["never_quoted"] == 0, got
    assert got["usable"] == 1, got
    assert got["moved"] == 1, got


def test_the_window_is_not_skewed_by_the_stored_time_format():
    """THE SKEW, 2026-09-19. `BETWEEN` on a TEXT column is a STRING
    comparison. Both stores stamp "…T15:00:00Z" while an isoformat bound
    reads "… 15:00:00", and "T" sorts after " " — so a bound sharing a
    quote's calendar date decided the comparison on that one character.

    Measured: a quote thirteen hours AFTER the filing was excluded and
    one six hours BEFORE the window opened was let in. The skew ran
    against the after-side, which is the only side that can show a move,
    so the measurement would have been quietly biased toward "we saw
    nothing" even once the names matched."""
    from engine import injurylag as il
    conn = _conn()
    _file(conn, "A.J. Brown")
    # Both quotes on calendar days that a naive bound gets wrong.
    pt.record(conn, "nfl", _slate(), NOW - _dt.timedelta(hours=20))
    pt.record(conn, "nfl",
              _Slate([_Prop("A.J. Brown", lines=[_Line("DK", 55.5)])],
                     [_game()]), NOW + _dt.timedelta(hours=20))
    got = il.measure(conn, sport="nfl")["nfl"]
    assert got["usable"] == 1, got
    assert got["moved"] == 1, got


# --- and it refuses rather than guesses --------------------------------
def test_a_stale_designation_stops_buying_rows():
    """Last month's healed hamstring is not still on the tape."""
    conn = _conn()
    old = (NOW - _dt.timedelta(days=pt.WATCH_DAYS + 5)).strftime(
        "%Y-%m-%dT%H:%M:00Z")
    _file(conn, "A.J. Brown", seen=old)
    assert pt.record(conn, "nfl", _slate(), NOW) == 0


def test_a_prop_with_no_game_on_the_slate_is_not_invented():
    """`event_id` is built from the game. A prop whose team is not
    playing today would get a fabricated key, and a made-up id in a
    shared table is worse than a missing row."""
    conn = _conn()
    _file(conn, "A.J. Brown")
    orphan = _Slate([_Prop("A.J. Brown", team="SEA",
                           lines=[_Line("DK", 62.5)])], [_game()])
    assert pt.record(conn, "nfl", orphan, NOW) == 0


def test_an_unreadable_injury_store_writes_nothing():
    """FAILS CLOSED. A tape that cannot read the watchlist must write
    NOTHING rather than everything — the failure that would fill the
    disk."""
    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("no such table: injury_events")
    assert pt.record(Broken(), "nfl", _slate(), NOW) == 0
    # AND IT SAYS SO. Failing closed quietly was the first thing I
    # wrote, and it made an unreadable store and a healthy roster print
    # the same sentence — `lineledger.record_note`'s double silence,
    # recreated in the module that cites it.
    assert "skipped" in pt.record_note(Broken(), "nfl", _slate(), NOW)


def test_the_leagues_do_not_share_a_watchlist():
    conn = _conn()
    _file(conn, "A.J. Brown", sport="cfb")
    assert pt.record(conn, "nfl", _slate(), NOW) == 0


def test_nothing_here_buys_a_price():
    """The argument for this whole file is that it costs no API credit.
    A fetch in here would make that untrue."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "proptape.py"),
        encoding="utf-8").read()
    for buy in ("requests", "urlopen", "fetch_", "oddsapi.get", "http"):
        assert buy not in src, f"{buy} — this tape is supposed to be free"


# --- the build says what it did ----------------------------------------
def test_the_build_line_separates_nothing_to_do_from_a_failure():
    """`lineledger`'s own lesson, in its docstring: returning 0 for both
    "nothing to write" and "the write threw" made a harvest broken on
    the day it shipped look like a quiet Tuesday."""
    conn = _conn()
    assert "nothing to watch" in pt.record_note(conn, "nfl", _slate(), NOW)
    _file(conn, "A.J. Brown")
    assert "stored free" in pt.record_note(conn, "nfl", _slate(), NOW)
    assert "no number moved" in pt.record_note(conn, "nfl", _slate(), NOW)

    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("disk is full")
    assert "skipped" in pt.record_note(Broken(), "nfl", _slate(), NOW)


def test_the_build_actually_calls_the_tape():
    """THE RECURRING BUG OF THIS CODEBASE: a thing computed correctly and
    never placed. A tape nothing calls collects nothing, and the only
    symptom is the zero we already spent a day chasing.

    Comments are stripped first — deleting the one line that read
    `clv_coverage` left that guard green because the comment above it
    still said the word (2026-09-19)."""
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "nfl_build.py"), encoding="utf-8").read()
    src = re.sub(r"(?s)([\"']{3}).*?\1", " ", src)
    src = re.sub(r"(?m)#.*$", " ", src)
    assert "proptape.record_note" in src, \
        "the prop tape is written and never called by the build"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
