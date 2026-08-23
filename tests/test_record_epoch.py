"""The public record starts on a date. The journal does not.

Ethan, 2026-08-23: "can we reset our record ON THE SITE to display for
8/6/2026 and onwards but we keep the data and shit for everything from
our record so we can still learn and shit. i just dont want our data to
be in the red since when we first started in july the model wasnt tuned
yet and its not whats pulling bets now."

That is a fair reading of what the number MEANS — a −22% ROI earned by
gates that no longer exist says nothing about the model running tonight,
which is the argument `era_report` was already written to make.

IT IS ONLY FAIR WHILE THE PAGE SAYS SO, and that is what most of this
file pins. A record scoped to a start date with no line admitting it is a
curated record, and this site's whole claim is that it grades in public.
So: nothing is deleted, every learning surface still reads everything,
the page states the date and the count it is leaving out, and the
all-time figures sit one click inside that same note.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPOCH = ledger.RECORD_EPOCH


def _journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))

    def bet(date, status, pnl, odds=-110, sport="mlb", player="P"):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,odds,"
            "stake_units,stake_dollars,status,category,pnl_units) VALUES "
            "('x',?,?,?,'hits','OVER',1.5,'DK',?,1.0,10.0,?,'main',?)",
            (sport, date, player, odds, status, pnl))

    # Before the epoch: a losing July.
    for i in range(6):
        bet("2026-07-2%d" % i, "lost", -1.0, player=f"Jul{i}")
    # On and after it: a winning August.
    for i in range(4):
        bet("2026-08-1%d" % i, "won", 0.91, player=f"Aug{i}")
    bet(EPOCH, "won", 0.91, player="OnTheDay")
    conn.commit()
    return conn


def _js():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def _fn(src, decl):
    i = src.index(decl)
    j = len(src)
    for end in ("\nfunction ", "\nasync function ", "\nconst ", "\n/* "):
        k = src.find(end, i + len(decl))
        if k != -1:
            j = min(j, k)
    return src[i:j]


# --- the scoping ----------------------------------------------------------

def test_the_epoch_scopes_the_headline():
    conn = _journal()
    assert ledger.performance(conn)["settled"] == 11
    scoped = ledger.performance(conn, since=EPOCH)
    assert scoped["settled"] == 5
    assert scoped["wins"] == 5 and scoped["losses"] == 0


def test_the_epoch_day_itself_is_included():
    """"from 8/6 onwards" includes the 6th. An off-by-one here silently
    drops a day of picks and nothing on the page would show it."""
    conn = _journal()
    rows = [r["player"] for r in conn.execute(
        "SELECT player FROM bets WHERE date >= ?", (EPOCH,))]
    assert "OnTheDay" in rows


def test_the_curve_starts_where_the_headline_starts():
    """A running total that disagrees with the number above it reads as
    the headline lying — and the curve is the more convincing of the
    two."""
    conn = _journal()
    dates = [p["date"] for p in ledger.pnl_curve(conn, since=EPOCH)]
    assert dates and min(dates) >= EPOCH


def test_a_football_week_label_sorts_by_its_season_not_by_luck():
    """NFL journals week labels and everything else journals ISO days, so
    the epoch filter compares two formats against each other.

    THE OBVIOUS SUMMARY OF THIS IS WRONG and a 2024 fixture in
    test_ledger caught it: week labels do NOT always sort above an ISO
    date. They sort by their YEAR prefix first, which is the behaviour
    that is actually wanted — a 2024 week is correctly outside a 2026
    epoch — and only inside the epoch's own year does "W" outrank every
    digit and pull the label in. That is the safe direction there: a week
    of the current season is included rather than silently dropped."""
    conn = _journal()
    conn.execute(
        "INSERT INTO bets (ts,sport,date,player,market,side,line,book,odds,"
        "stake_units,stake_dollars,status,category,pnl_units) VALUES "
        "('x','nfl','2026-W1','QB','pass_yds','OVER',250,'DK',-110,1.0,10.0,"
        "'won','main',0.91)")
    conn.commit()
    got = [b["player"] for b in conn.execute(
        "SELECT player FROM bets WHERE date >= ?", (EPOCH,))]
    assert "QB" in got, "the current season's weeks were dropped"
    # And a week from an EARLIER season is correctly outside the window.
    assert "2024-W05" < EPOCH
    assert "2026-W1" > EPOCH


# --- nothing is deleted, and learning still sees everything ---------------

def test_the_export_keeps_the_all_time_numbers_beside_the_scoped_ones():
    conn = _journal()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    d = json.load(open(path))
    assert d["record_epoch"] == EPOCH
    assert d["overall"]["settled"] == 5
    assert d["all_time"]["overall"]["settled"] == 11
    assert d["all_time"]["hidden_settled"] == 6


def test_the_export_writes_nothing_back_to_the_journal():
    """"we keep the data and shit" is the load-bearing half of the ask."""
    conn = _journal()
    before = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    ledger.export_json(conn, os.path.join(tempfile.mkdtemp(), "r.json"))
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == before


def test_every_record_block_on_the_page_uses_the_same_window():
    """THIS TEST USED TO ASSERT THE OPPOSITE, and it was wrong.

    It pinned `by_sport` as deliberately UNSCOPED, on the reasoning that
    it was the tuning view and tuning wants every row. Ethan found the
    hole immediately: "the record page still shows us down 20 units …
    and thats for every spot on the page." The per-sport tabs read that
    block, so the headline said one thing and every tab beside it said
    another.

    The reasoning was wrong on its own terms. record.json is the
    WEBSITE's payload and nothing else reads it; the tuning that needs
    every row — the miner, the calibration fits, the era split — runs in
    Python against the database. "we will keep all the other data that we
    dont display for ourselves" is exactly right, and the database is
    where that data lives.

    So: every block on that page that states a RECORD is windowed, or
    two numbers on one screen disagree.
    """
    conn = _journal()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    d = json.load(open(path))
    assert d["overall"]["settled"] == 5
    assert d["by_sport"]["mlb"]["overall"]["settled"] == 5
    assert d["by_sport"]["mlb"]["curve"] == d["curve"]
    assert d["restated"]["overall"]["settled"] <= 5
    for k in ("longshots", "stale_flags", "form_sampler", "loose_sampler",
              "predmarket", "ufc_record", "paper"):
        assert d[k]["settled"] == 0, k


def test_the_era_split_still_shows_every_era():
    """The one block that MUST reach back past the epoch. Its entire
    purpose is to show the model's record split at each re-tune — an era
    report that starts after the eras it is comparing is nothing."""
    conn = _journal()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    eras = json.load(open(path))["model_eras"]["eras"]
    assert sum(e["settled"] for e in eras) == 11


def test_the_database_still_holds_every_row():
    """The half of the ask that is not about display at all."""
    conn = _journal()
    ledger.export_json(conn, os.path.join(tempfile.mkdtemp(), "r.json"))
    assert conn.execute(
        "SELECT COUNT(*) FROM bets WHERE date < ?", (EPOCH,)).fetchone()[0] == 6


def test_the_calibration_chart_is_not_scoped_either():
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    body = _fn(src, "def export_json(")
    i = body.index('"calibration":')
    assert "since=since" not in body[i:i + 120]


# --- the disclosure -------------------------------------------------------

def test_the_page_says_the_date_and_the_count_it_leaves_out():
    """"Some earlier picks" is not a disclosure. A reader can weigh a
    number."""
    body = _fn(_js(), "function recEpochHTML(")
    assert "Record shown from" in body
    assert "not in these numbers" in body
    assert "hidden" in body


def test_the_note_carries_the_all_time_figures_itself():
    """One click, in the same note — not a link to somewhere else, and
    not nowhere."""
    body = _fn(_js(), "function recEpochHTML(")
    assert "All-time" in body
    assert "o.wins" in body and "o.losses" in body and "roi" in body


def test_the_note_is_drawn_under_the_numbers_it_qualifies():
    body = _fn(_js(), "async function renderRecord(")
    assert "recEpochHTML(d)" in body
    # ORDER, NOT DISTANCE. The first draft of this asserted the note sat
    # within 3000 characters of the strip and went red on its own first
    # run — the same fixed-window mistake this suite has made six times
    # now. What matters is that it comes AFTER the numbers and BEFORE the
    # next thing on the page, so a reader meets it while looking at them.
    kpis = body.index("rec-kpis")
    note = body.index("recEpochHTML(d)")
    nxt = body.index('recDisclosure("What counts as a tracked bet"')
    assert kpis < note < nxt


def test_nothing_hidden_draws_nothing():
    """A permanent notice about zero bets is noise pretending to be
    candour."""
    body = _fn(_js(), "function recEpochHTML(")
    assert "if (!ep || !hidden || !o.settled) return \"\";" in body


def test_the_note_is_not_hidden_behind_the_why_collapse():
    """`enhanceSectionSubs` folds long .section-title subs behind "why?".
    The one line that says what the record leaves out must not be one of
    the things a reader has to go looking for."""
    body = _fn(_js(), "function recEpochHTML(")
    assert 'class="section-title"' not in body
    assert 'class="rec-epoch"' in body
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".rec-epoch" in css, "the note has no styling at all"


def test_every_surface_quoting_the_record_uses_the_same_window():
    """The paywall's proof block reads the same file. If it kept quoting
    the all-time numbers the site would state two different records, and
    the one on the sales page would be the wrong one either way."""
    js = _js()
    body = _fn(js, "function pwResultsHTML(")
    assert "rec.overall" in body
    assert "all_time" not in body


# --- the tiles that were overlapping -------------------------------------

def test_a_full_season_record_does_not_fill_its_own_tile():
    """Ethan, 2026-08-23, with RECORD and WIN RATE circled: "this text
    cant fit and is over lapping."

    MEASURED AT 900px in Chromium: the value box was 133px inside a 134px
    content box, so "300-320-0" ran edge to edge and read as one number
    with 48.4% across the 1px divider. Nothing OVERFLOWED, which is why an
    overflow check found nothing and a person found it instantly.

    The earlier fix for the same nine characters went on `.tile.lead`
    only, and RECORD is not a lead tile — and its other half, the
    non-breaking hyphens that stop the score wrapping, is what guarantees
    the overrun once the tile is narrow enough.
    """
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = css.index(".rec-kpis {")
    block = css[i:css.index("}", i)]
    assert "minmax(min(196px" in block, "the track floor is back at 168px"
    j = css.index(".rec-kpis .tile .v {")
    rule = css[j:css.index("}", j)]
    assert "clamp(" in rule, "the plain tiles size their value unclamped again"
    # And the lead tiles keep their own, larger clamp — higher specificity.
    assert ".rec-kpis .tile.lead .v {" in css


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
