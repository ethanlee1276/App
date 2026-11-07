"""`injury_events` was read by nothing; now it is measured.

Ethan, 2026-09-19: *"figure out what data we need to source and what we
can use to make all of our edge bets and all of our most likely bets
better. I know it's out there."*

The cheapest source is the one already on disk, and `engine.datause`'s
new table audit found exactly one store nobody reads: `injury_events`.
`engine.newstape` INSERTs into it every night — player, status,
`posted_at` from the feed, `first_seen` from us — and no model, no gate
and no page has ever selected a row back out.

It is worth the trouble because injury news is a MECHANICAL edge rather
than a predictive one: when a starter is ruled out the number moves, and
the money is in the gap between the filing and the move. We do not have
to out-forecast anyone, only be early — and early is measurable.

`odds_history` is timestamped and carries `player`, so a player's own
prop quotes line up against the moment his status changed. This file
pins the arithmetic that turns those two stores into an answer, in both
directions: a NEGATIVE lead (the market moved first) has to be
reportable, or the measurement can only ever flatter us.

Run directly: `python3 tests/test_are_we_ahead_on_injury_news.py`
"""

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import injurylag as il                             # noqa: E402

SEEN = "2026-09-14T12:00:00"


def _q(*pairs):
    return list(pairs)


# --- the good case: we saw it first ------------------------------------
def test_a_line_that_moves_after_we_see_the_news_is_a_positive_lead():
    """THE SIGNAL. Baseline holds until our filing, then the market
    reprices — the gap is the window we could have bet in."""
    got = il.classify(SEEN, _q(
        ("2026-09-14T09:00:00", 62.5),
        ("2026-09-14T11:00:00", 62.5),
        ("2026-09-14T12:45:00", 55.5)))
    assert got["moved"] is True, got
    assert got["move"] == -7.0, got
    assert got["lead_minutes"] == 45.0, got


def test_the_lead_is_to_the_first_quote_that_moved():
    """A line that drifts back before the close still moved, and the
    window we care about is the FIRST chance to bet it."""
    got = il.classify(SEEN, _q(
        ("2026-09-14T11:00:00", 62.5),
        ("2026-09-14T12:30:00", 55.5),
        ("2026-09-14T18:00:00", 61.0)))
    assert got["lead_minutes"] == 30.0, got


# --- the bad case, which has to be reportable --------------------------
def test_a_market_that_moved_first_reads_as_a_negative_lead():
    """THE ANSWER THAT MATTERS MOST. If the line had already moved
    before our filing, the news was priced before we saw it — our feed
    is a newspaper. A measurement that cannot say this can only ever
    flatter us."""
    got = il.classify(SEEN, _q(
        ("2026-09-14T08:00:00", 62.5),
        ("2026-09-14T10:00:00", 55.5),      # market moved two hours early
        ("2026-09-14T11:30:00", 55.5),
        ("2026-09-14T13:00:00", 54.0)))
    assert got["moved"] is True, got
    assert got["lead_minutes"] is not None and got["lead_minutes"] < 0, got


def test_a_line_that_never_moves_is_not_counted_as_being_early():
    got = il.classify(SEEN, _q(
        ("2026-09-14T11:00:00", 62.5),
        ("2026-09-14T13:00:00", 62.5)))
    assert got["moved"] is False, got
    assert got["lead_minutes"] is None, got


# --- and the honest refusals -------------------------------------------
def test_quotes_on_only_one_side_say_nothing():
    """Counting these as "no move" would quietly claim we were early on
    a filing we have no before-price for."""
    assert il.classify(SEEN, _q(("2026-09-14T13:00:00", 55.5))) is None
    assert il.classify(SEEN, _q(("2026-09-14T09:00:00", 62.5))) is None


def test_a_move_smaller_than_a_tick_is_not_a_move():
    """Half a point is the tick books quote in; under it is the same
    number wearing a rounding error, and counting those would report a
    move on every quote and make the lead meaningless."""
    got = il.classify(SEEN, _q(
        ("2026-09-14T11:00:00", 62.5),
        ("2026-09-14T13:00:00", 62.5 + il.MOVE_EPS / 2)))
    assert got["moved"] is False, got


def test_quotes_from_another_day_are_not_this_filings_reaction():
    got = il.classify(SEEN, _q(
        ("2026-09-11T11:00:00", 62.5),
        ("2026-09-18T13:00:00", 40.0)))
    assert got is None, got


def test_an_unreadable_timestamp_costs_its_own_row_not_the_pass():
    got = il.classify(SEEN, _q(
        ("not a date", 99.0),
        ("2026-09-14T11:00:00", 62.5),
        ("2026-09-14T13:00:00", 55.5)))
    assert got["moved"] is True, got
    assert il.classify("nonsense", _q(("2026-09-14T11:00:00", 62.5))) is None


def test_a_missing_line_is_skipped_rather_than_read_as_zero():
    got = il.classify(SEEN, _q(
        ("2026-09-14T11:00:00", 62.5),
        ("2026-09-14T12:10:00", None),
        ("2026-09-14T13:00:00", 55.5)))
    assert got["moved"] is True and got["move"] == -7.0, got


# --- the verdict over many filings -------------------------------------
def test_the_rate_is_over_moves_not_over_every_filing():
    """A filing whose line never moved says nothing about our speed.
    Folding those in would flatter whichever answer had more quiet news
    in it."""
    rows = [
        {"moved": True, "move": -7.0, "lead_minutes": 45.0},
        {"moved": True, "move": -3.0, "lead_minutes": -20.0},
        {"moved": False, "move": 0.0, "lead_minutes": None},
        {"moved": False, "move": 0.0, "lead_minutes": None},
        None,
    ]
    s = il.summarise(rows)
    assert s["filings"] == 5 and s["usable"] == 4, s
    assert s["moved"] == 2 and s["ahead"] == 1, s
    assert s["ahead_rate"] == 0.5, s


def test_a_book_with_no_moves_reports_no_rate_rather_than_zero():
    """"0% ahead" and "nothing measurable yet" are different facts and
    the second one must not print as the first."""
    s = il.summarise([{"moved": False, "move": 0.0, "lead_minutes": None}])
    assert s["ahead_rate"] is None, s
    assert s["median_lead_minutes"] is None, s


def test_the_summary_survives_having_nothing_at_all():
    s = il.summarise([])
    assert s["filings"] == 0 and s["ahead_rate"] is None, s


# --- it reads only the statuses that move a market ---------------------
def test_only_statuses_the_market_has_to_reprice_are_measured():
    """"Probable" moves nothing, and including it would bury the signal
    in filings that were never going to matter."""
    assert "out" in il.MOVING_STATUSES and "doubtful" in il.MOVING_STATUSES
    assert "probable" not in il.MOVING_STATUSES


def test_nothing_in_here_writes():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "injurylag.py"),
        encoding="utf-8").read()
    for write in ("INSERT", "UPDATE ", "DELETE", "commit("):
        assert write not in src, f"{write} in a measurement"


# --- and it has to FINISH on a real box --------------------------------
class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Spy:
    """A connection that answers nothing and remembers everything asked.

    The bug this catches is a PERFORMANCE one, and performance is not
    visible in a return value — the old code gave the right answer and
    took thirteen minutes to give it. What a query touches is only
    checkable by looking at the query.
    """

    def __init__(self, filings, quotes=(), ever=False):
        self.filings = list(filings)
        self.quotes = quotes if isinstance(quotes, dict) else list(quotes)
        self.ever = ever          # does the name probe find him at all?
        self.asked = []

    def execute(self, sql, args=()):
        flat = " ".join(sql.split())
        self.asked.append((flat, list(args)))
        if "FROM injury_events" in flat:
            return _Rows(self.filings)
        if "BETWEEN" in flat:
            q = self.quotes
            # A dict lets one pass carry filings of DIFFERENT shapes,
            # which is what the reconciliation test needs.
            return _Rows(list(q.get(args[3], ())) if isinstance(q, dict)
                         else q)
        return _Rows([{"1": 1}] if self.ever else [])

    def quote_reads(self):
        """The bounded window reads — one per filing that can be dated."""
        return [q for q in self.asked
                if "FROM odds_history" in q[0] and "BETWEEN" in q[0]]

    def name_probes(self):
        """The "do we ever quote this man" fallback, asked only when the
        window came back empty."""
        return [q for q in self.asked
                if "FROM odds_history" in q[0] and "BETWEEN" not in q[0]]


def _filing(first_seen=SEEN, sport="nfl", player="A Back"):
    return {"sport": sport, "player": player, "status": "out",
            "posted_at": first_seen, "first_seen": first_seen}


def test_each_quote_lookup_is_bounded_by_the_time_column():
    """THE THIRTEEN MINUTES. Ethan, 2026-09-19: the first run of
    `homecheck.py data` on the droplet was still going after thirteen
    minutes and had to be killed.

    `odds_history`'s primary key is (sport, taken_at, event_id, player,
    market, book), so `sport=? AND player=?` cannot use it — `taken_at`
    sits between them and SQLite scans the whole table instead. One scan
    per filing, a few thousand filings, months of quotes. Bounding
    `taken_at` makes the leading two columns usable and each lookup a
    range scan over one day."""
    spy = _Spy([_filing()])
    il.measure(spy)
    reads = spy.quote_reads()
    assert len(reads) == 1, spy.asked
    sql, args = reads[0]
    assert "taken_at BETWEEN ? AND ?" in sql, sql
    lo, hi = il._parse(args[1]), il._parse(args[2])
    assert lo < il._parse(SEEN) < hi, args
    # The exact width is the two tests below this one; what matters here
    # is that a width exists at all, which is what the index needs.


def test_the_sql_window_is_a_superset_of_the_one_that_is_kept():
    """The SQL bound is deliberately WIDER than WINDOW_HOURS, and only
    ever wider.

    `BETWEEN` on a TEXT column is a string comparison, and both stores
    stamp "…T15:00:00Z" while an isoformat bound reads "… 15:00:00" —
    "T" sorts after " ", so an exact bound sharing a quote's calendar
    date decided the comparison on that one character and dropped quotes
    from the after-side of the filing. Date-only bounds cannot have that
    argument with a timestamp whatever separator it carries.

    `classify` re-parses every row and applies the real window, so a
    superset costs a few extra rows off one player's index range and
    nothing else. A SUBSET would cost measurements, silently."""
    spy = _Spy([_filing()])
    il.measure(spy)
    sql, args = spy.quote_reads()[0]
    assert "BETWEEN" in sql and len(args) >= 3, (sql, args)
    lo, hi = il._parse(args[1]), il._parse(args[2])
    seen = il._parse(SEEN)
    assert lo <= seen - _dt.timedelta(hours=il.WINDOW_HOURS), (lo, seen)
    assert hi >= seen + _dt.timedelta(hours=il.WINDOW_HOURS), (hi, seen)


def test_the_sql_window_is_not_wider_than_it_needs_to_be():
    """A superset is safe; an unbounded one is the table scan this whole
    thread started with."""
    spy = _Spy([_filing()])
    il.measure(spy)
    args = spy.quote_reads()[0][1]
    span = (il._parse(args[2]) - il._parse(args[1])).total_seconds() / 3600.0
    assert span <= il.WINDOW_HOURS * 2 + 48, span


def test_a_filing_with_no_readable_stamp_never_buys_a_lookup():
    """A filing that can never be classified must not be paid for. The
    stamp is parsed BEFORE the quotes are fetched, not after."""
    spy = _Spy([_filing(first_seen="not a date")])
    il.measure(spy)
    assert spy.quote_reads() == [], spy.asked


def test_one_filing_costs_one_read():
    """Not one per quote, and not one per book."""
    spy = _Spy([_filing(player="A"), _filing(player="B"),
                _filing(player="C")])
    il.measure(spy)
    assert len(spy.quote_reads()) == 3, spy.asked


def test_a_pathological_key_still_costs_a_bounded_read():
    """A name that matches half the board, or a feed that stamped every
    row at midnight, buys one capped read rather than the table."""
    spy = _Spy([_filing()])
    il.measure(spy)
    sql, args = spy.quote_reads()[0]
    assert "LIMIT ?" in sql, sql
    assert args[-1] == il.MAX_QUOTES, args


def test_a_status_the_market_ignores_is_filtered_before_the_read():
    """"Probable" is not measured, so it must not cost a query either."""
    spy = _Spy([dict(_filing(), status="probable")])
    il.measure(spy)
    assert spy.quote_reads() == [], spy.asked



# --- and it refuses to run where it cannot run fast --------------------
def test_a_store_without_the_index_is_refused_not_crawled():
    """Ethan, 2026-09-19, the second report: five more minutes after the
    first fix. `homecheck` opens the history READ-ONLY — correct, a check
    must be safe mid-cycle — so it cannot build the index it needs, and
    a fresh deploy read exactly like the bug it fixed: a command that
    sits there. A measurement that cannot be fast should say so in a
    second."""
    import sqlite3
    bare = sqlite3.connect(":memory:")
    bare.row_factory = sqlite3.Row
    assert il.index_ready(bare) is False
    out = il.report(bare)
    assert "not measured" in out, out
    assert il.REQUIRED_INDEX in out, out


def test_the_refusal_says_how_to_fix_it():
    """A refusal that does not hand over the next command is a slower
    way of saying nothing."""
    import sqlite3
    bare = sqlite3.connect(":memory:")
    bare.row_factory = sqlite3.Row
    out = il.report(bare)
    assert "db.connect()" in out, out
    assert "nightly" in out, out


def test_a_store_that_has_the_index_is_measured():
    """The refusal has to END, or it is just the check being off."""
    from engine.db import connect
    out = il.report(connect(":memory:"))
    assert "not measured" not in out, out
    assert "Nothing here bets" in out, out


def test_an_unreadable_store_reads_as_not_ready():
    """FAILS CLOSED, the same way `stale_promoted` does: refusing costs
    a report, crawling costs the box."""
    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("no such table: sqlite_master")
    assert il.index_ready(Broken()) is False


def test_the_required_index_is_actually_in_the_schema():
    """The guard names an index; the schema has to build it, or the
    refusal is permanent and nothing ever measures."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = open(os.path.join(root, "engine", "db.py"), encoding="utf-8").read()
    assert il.REQUIRED_INDEX in db, "the guard names an index nothing creates"
    i = db.index(il.REQUIRED_INDEX)
    decl = " ".join(db[i:i + 200].split())
    assert "odds_history (sport, player, taken_at)" in decl, decl



# --- the two stores spell the same man differently ---------------------
def test_the_lookup_asks_for_the_books_spelling_of_the_name():
    """THE ZERO. Ethan, 2026-09-19, on the droplet: 2,015 filings and not
    one with quotes on both sides, in every sport at once.

    `injury_events` keeps the feed's display name; `odds_history` keeps
    the books' menu, which `parse_event_lines` runs through
    `normalize_name` before storing. So the join was "A.J. Terrell Jr."
    against "a j terrell" and matched 0 of 708 NFL players. Nothing was
    broken about the arithmetic — it was never handed a row."""
    spy = _Spy([_filing(player="A.J. Terrell Jr.")])
    il.measure(spy)
    args = spy.quote_reads()[0][1]
    assert args[3] == "a j terrell", args


def test_the_normaliser_is_the_books_own_one():
    """Not a third spelling convention invented here. `odds_history` is
    written with `oddsapi.normalize_name`, so the lookup has to use that
    function and not a lookalike."""
    from engine.sources.oddsapi import normalize_name
    for raw in ("A.J. Terrell Jr.", "Amon-Ra St. Brown", "Ja'Marr Chase",
                "Ronald Acuña Jr."):
        assert il._norm(raw) == normalize_name(raw), raw


def test_an_unspellable_name_does_not_cost_the_pass():
    assert il._norm(None) == ""
    assert il._norm("") == ""


# --- and an empty answer says WHICH empty ------------------------------
def test_a_man_no_book_prices_is_counted_apart():
    """"0 with quotes either side" was true of a name mismatch, a
    coverage gap and a timing gap alike, and the report printed the same
    sentence for all three. That is what sent me looking in the wrong
    place twice."""
    spy = _Spy([_filing()], quotes=[], ever=False)
    got = il.measure(spy)["nfl"]
    assert got["never_quoted"] == 1, got
    assert got["quoted_elsewhen"] == 0, got


def test_a_man_we_price_but_not_near_the_news_is_counted_apart():
    """The more interesting failure: the names are fine and we simply
    hold no quote when the news breaks. That is a recording gap, and
    recording is free — the prices are already in memory."""
    spy = _Spy([_filing()], quotes=[], ever=True)
    got = il.measure(spy)["nfl"]
    assert got["quoted_elsewhen"] == 1, got
    assert got["never_quoted"] == 0, got


def test_the_probe_is_only_paid_for_when_the_window_is_empty():
    """It exists to explain a zero, so a filing that measured fine must
    not buy one."""
    spy = _Spy([_filing()], quotes=[
        {"taken_at": "2026-09-14T11:00:00Z", "line": 62.5},
        {"taken_at": "2026-09-14T13:00:00Z", "line": 55.5}])
    il.measure(spy)
    assert spy.name_probes() == [], spy.asked


def test_the_report_says_which_kind_of_nothing_it_found():
    spy = _Spy([_filing()], quotes=[], ever=False)
    out = il.report(_Ready(spy))
    assert "never quoted by any book" in out, out
    assert "naming gap" in out, out


def test_the_report_says_the_other_kind_too():
    spy = _Spy([_filing()], quotes=[], ever=True)
    out = il.report(_Ready(spy))
    assert "no quote when the news breaks" in out, out


class _Ready(_Spy):
    """A spy that also answers the index-readiness check, so `report`
    gets past its guard and renders."""

    def __init__(self, spy):
        super().__init__(spy.filings, spy.quotes, spy.ever)

    def execute(self, sql, args=()):
        if "sqlite_master" in sql:
            return _Rows([{"1": 1}])
        return super().execute(sql, args)



def test_every_filing_lands_in_exactly_one_bucket():
    """THE COLUMNS HAVE TO ADD UP. Ethan, 2026-09-19: mlb printed 18
    filings over buckets summing to 16. The missing two were quoted
    inside the window but on ONE SIDE of the filing, so `classify`
    refused them — correctly — and the report dropped them silently.

    A report whose own numbers do not reconcile teaches the reader to
    distrust all of it, which is the opposite of what a measurement is
    for."""
    def q(*pairs):
        return [{"taken_at": t, "line": v} for t, v in pairs]
    spy = _Spy(
        [_filing(player="Measured"), _filing(player="OneSided"),
         _filing(player="NeverQuoted")],
        quotes={
            "measured": q(("2026-09-14T11:00:00Z", 62.5),
                          ("2026-09-14T13:00:00Z", 55.5)),
            "onesided": q(("2026-09-14T13:00:00Z", 55.5)),
            "neverquoted": (),
        })
    got = il.measure(spy)["nfl"]
    assert got["filings"] == 3, got
    assert got["usable"] == 1, got
    assert got["one_sided"] == 1, got
    assert got["never_quoted"] == 1, got
    total = (got["usable"] + got["one_sided"]
             + got["never_quoted"] + got["quoted_elsewhen"])
    assert total == got["filings"], got


def test_the_report_prints_the_one_sided_count():
    """MUTATION, 2026-09-19: counting the third bucket and not showing it
    left the printed columns still failing to add up, which is the whole
    complaint."""
    spy = _Spy([_filing()], quotes=[{"taken_at": "2026-09-14T13:00:00Z",
                                     "line": 55.5}])
    out = il.report(_Ready(spy))
    assert "1 quoted on one side only" in out, out


def test_the_report_leaves_the_third_bucket_out_when_it_is_empty():
    """A column of zeros is noise on a line already carrying two
    numbers."""
    out = il.report(_Ready(_Spy([_filing()], quotes=[], ever=True)))
    assert "one side only" not in out, out


def test_a_one_sided_filing_never_buys_a_name_probe():
    """We already know we quote him — the probe answers a question this
    filing has just answered."""
    spy = _Spy([_filing()], quotes=[{"taken_at": "2026-09-14T13:00:00Z",
                                     "line": 55.5}])
    il.measure(spy)
    assert spy.name_probes() == [], spy.asked



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
