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
        # hit_prob and a close ride along: the calibration block and the
        # CLV coverage block are two of the surfaces this file checks, and
        # both are empty without them — a reconciliation test where every
        # number is 0 reconciles perfectly and proves nothing.
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,odds,"
            "hit_prob,stake_units,stake_dollars,status,category,pnl_units,"
            "closing_line) VALUES "
            "('x',?,?,?,'hits','OVER',1.5,'DK',?,0.58,1.0,10.0,?,'main',?,1.6)",
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
    # `\ndef ` too: this helper reads BOTH app.js and ledger.py, and
    # without a Python boundary a slice of one function ran on to the end
    # of the file — which is how a test asserting "_edge_series takes no
    # window" read the word out of export_json below it.
    for end in ("\nfunction ", "\nasync function ", "\nconst ", "\n/* ",
                "\ndef ", "\n#: "):
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


def test_every_count_on_the_page_reconciles():
    """Ethan, looking at the deployed page: "you didnt push the mlb
    reccord back to the 6th. every single reccord and all of that needs
    to be pushed back. EVERYTHING."

    ALL BETS read 431 while the MLB tab beside it read 625 and the
    verdict under it read "across 564 graded picks". Three numbers about
    the same book, on one screen, none of them agreeing.

    So this is not a list of blocks to remember to scope — it is the
    arithmetic. The tabs must sum to the headline, and every block that
    counts our settled picks must land on the same total. A block added
    later that forgets the window fails here without anybody having to
    think of it.
    """
    conn = _journal()
    conn.execute(
        "INSERT INTO bets (ts,sport,date,player,market,side,line,book,odds,"
        "stake_units,stake_dollars,status,category,pnl_units,closing_line) "
        "VALUES ('t','nfl','2026-08-14','QB','hits','OVER',1.5,'DK',-110,"
        "1.0,10.0,'won','main',0.91,1.6)")
    conn.execute("UPDATE bets SET hit_prob=0.58 WHERE player='QB'")
    conn.commit()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    d = json.load(open(path))

    head = d["overall"]["settled"]
    assert head == 6, head
    tabs = sum(d["by_sport"][sp]["overall"]["settled"]
               for sp in d["tracked_sports"])
    assert tabs == head, f"tabs sum to {tabs}, headline says {head}"
    for block, n in (("calibration", d["calibration"]["n"]),
                     ("clv_coverage", d["clv_coverage"]["settled"]),
                     ("restated", d["restated"]["overall"]["settled"])):
        assert n <= head, f"{block} counts {n} against a {head}-pick record"
    assert d["calibration"]["n"] == head


def test_the_verdicts_own_numbers_come_from_the_windowed_calibration():
    """THE VERDICT's settled tile, its claimed/landed rates and its
    "across N graded picks" line all read the calibration block. That one
    slipped through the first pass and was the most visible miss on the
    page — a 431-pick record explained by a 564-pick calibration."""
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    body = _fn(src, "def export_json(")
    i = body.index('"calibration":')
    assert "since=since" in body[i:i + 90]


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


def test_the_learning_surfaces_still_read_every_row():
    """THIS TEST ALSO USED TO ASSERT THE OPPOSITE, for calibration, and
    that was the most visible miss of the lot: THE VERDICT's settled tile
    reads the record while its claimed/landed rates and its "across N
    graded picks" line read calibration, so the page explained a 431-pick
    record with a 564-pick calibration.

    What stays unscoped is what exists to look BACK across the whole
    history. The era split's entire purpose is comparing the model before
    and after each re-tune. The miner is the learning Ethan explicitly
    asked to keep — "we keep the data and shit for everything from our
    record so we can still learn" — and it reads the database, which is
    whole.
    """
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    body = _fn(src, "def export_json(")
    # THE LINE, not a character window. A 90-character slice here spilled
    # into the NEXT export key — which is scoped — and failed on its own
    # first run. Seventh time this suite has made that mistake today.
    for key in ('"model_eras"', '"loss_patterns"'):
        i = body.index(key)
        line = body[i:body.index("\n", i)]
        assert "since" not in line, f"{key} got scoped: {line}"


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


# --- the command that makes the date a decision --------------------------

def test_the_epoch_can_be_compared_against_the_eras_it_is_not():
    """Ethan asked what he needs to decide. The date the public record
    starts from is his call, and it should be made against the real
    numbers rather than against a feeling about them.

    The dates offered are MODEL_ERAS — the re-tunes this journal has
    actually had — because an era boundary is a date something CHANGED
    and any other date is just a date. Only the first kind answers "why
    does your record start there?" if a subscriber ever asks.
    """
    import launch
    assert hasattr(launch, "show_epoch")
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--epoch" in argv' in src, "the flag is not wired"
    body = _fn(src, "def show_epoch(")
    assert "MODEL_ERAS" in body, "it offers dates nothing happened on"
    assert "RECORD_EPOCH" in body
    # Read-only: a reporting command that writes is a command nobody runs
    # on a live journal.
    for w in ("INSERT", "UPDATE", "DELETE", "export_json", "commit("):
        assert w not in body, w


def test_the_comparison_says_the_journal_is_untouched():
    """The whole point of the epoch is that it is a display window. A
    command that prints a smaller record without saying the rest is still
    there is the command that makes someone think data was deleted."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = _fn(src, "def show_epoch(")
    assert "stay there" in body or "still" in body
    assert "only what the SITE shows" in body


# --- the information test ------------------------------------------------

def test_the_edge_panel_counts_the_same_bets_as_the_record():
    """Ethan, pointing at the panel header: "fix where it says 500 bets."
    It read "558 settled bets" beside a 431-pick record, because it
    returned the last BANKED run and every banked run was measured over
    the whole journal."""
    # FORTY-FIVE IN THE WINDOW, because edgehistory.measure refuses a
    # sample under 40 — a test built on six rows would have proved only
    # that the panel draws nothing, which it already does.
    conn = _journal()
    for i in range(45):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,hit_prob,stake_units,stake_dollars,status,category,"
            "pnl_units,closing_odds) VALUES ('t','mlb',?,?,'hits','OVER',1.5,"
            "'DK',-110,?,1.0,10.0,?,'main',?,-105)",
            (f"2026-08-{6 + i % 18:02d}", f"Edge{i}",
             round(0.50 + (i % 9) * 0.02, 3),
             "won" if i % 2 else "lost", 0.91 if i % 2 else -1.0))
    conn.commit()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    d = json.load(open(path))
    assert d["edge_now"] is not None
    assert d["edge_now"]["n"] == d["overall"]["settled"], (
        f"panel says {d['edge_now']['n']}, record says "
        f"{d['overall']['settled']}")


def test_the_snapshot_is_measured_fresh_when_a_window_is_given():
    """Banking stays right for the TREND — each stored run is what the
    test said on the night it ran, and rewriting those would be inventing
    a history. The headline number is a statement about the record on
    screen, so it is computed over the same bets."""
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    body = _fn(src, "def _edge_snapshot(")
    assert "edgehistory.measure(" in body, "still reading the banked run"
    assert "if not since:" in body and "edgehistory.latest(" in body, \
        "the unwindowed caller lost its banked answer"


def test_the_nightly_run_is_banked_over_the_same_window():
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = launch.index("ledger.record_edge_run(")
    assert "since=ledger.RECORD_EPOCH" in launch[i:i + 90]


def test_the_stored_runs_are_left_alone():
    """A trend whose old points get rewritten is not a trend."""
    src = open(os.path.join(ROOT, "engine", "ledger.py"),
               encoding="utf-8").read()
    body = _fn(src, "def _edge_series(")
    assert "since" not in body


def test_the_edge_panel_is_the_last_thing_in_the_room():
    """It led the page from 2026-08-09 on the argument that it is the
    frame the ROI should be read through. Right about its importance,
    wrong about a reader's first ten seconds — four rows of AUCs, three
    paragraphs of statistics and a sixty-run trend, standing between a
    visitor and the record they came for."""
    js = _js()
    body = _fn(js, "async function renderRecord(")
    i = body.index("const receipts = verdict")
    tail = body[i:]
    assert "verdict + edgePanel" not in tail, "the panel leads again"
    assert tail.index("recRecentSection") < tail.index("${edgePanel}")


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
