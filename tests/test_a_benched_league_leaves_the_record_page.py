"""WNBA off the record until the model earns its way back.

Ethan, 2026-09-21: *"Stop recording WNBA on the record and make it paper
till we make the model better and remove wnba from the record so it's
not hurting us. Make it all paper."*

PAPER WOULD NOT HAVE DONE IT, which is why this is not paper mode.
`ledger.BOOK` is ("main", "paper") and `performance` counts both —
because on 2026-08-13 he asked for exactly that: "Combine our paper
record and normal money record." So filing WNBA as paper stops the
DOLLARS and leaves every unit, win, loss and ROI point of it in the
headline, which is the number he asked to stop it hurting. `paper_mode`
is also one global switch, not a per-league one.

A benched league goes to a category OUTSIDE `BOOK`. That is what takes
it out of `performance`, and it is the whole mechanism.

WHAT THE BENCH IS NOT. It is not a deletion and not a silence. The
picks are still made, still journaled, still graded, and still shown —
under their own heading in `SHADOW_SECTIONS`, because a league whose
rows simply stopped appearing is the misleading quiet this project
keeps being fixed for. The bench is a claim we should be held to: we
said the model was not good enough, and this is where that gets
checked.

THE SEALED FORECAST LOG IS UNTOUCHED AND DOES NOT BREAK — and the first
version of this warning, given to Ethan before the schema was read,
said it would. It does not: `verify_forecast_log` recomputes from the
log's OWN copy of `category`, and `seal_forecasts` joins on `bet_id` and
will not re-seal a row already in the chain. The log records what was
CLAIMED at the time; this table records what was decided afterwards.
They are supposed to be able to differ.

MONEY MOVES IN TWO PLACES, NOT ONE. The Edge book is the headline, but
`LIKELY_LIVE_SPORTS` had WNBA staking 0.25u of real dollars on the
likelihood board since 2026-09-19. "Make it all paper" means no WNBA
money anywhere.

OFF THE PAGE ENTIRELY, NOT JUST OUT OF THE TOTAL. The first cut of this
showed the bench under its own Record-page heading, on the argument that
a league whose rows stop appearing is misleading quiet. Ethan,
2026-09-21, after seeing it: *"I don't want wnba Past bet or new bet on
the record page. I only want it as paper bets."* So the heading is gone
and the league is absent from that page — past rows and new ones.

IT IS NOT DELETED AND NOT UNGRADED. Every row stays in the journal, is
still settled, still carries its CLV, and is still readable at the
terminal — `homecheck.py record` scopes to it — which is how we find
out whether the model got better. What stopped is publishing it.

`test_the_record_page_cannot_tell_wnba_exists` is the whole rule in one
assertion, and the only one that can catch a POOLED figure quietly
carrying these rows: a number has no league name in it, so nothing that
reads the payload for the word can see the leak. It exports twice and
requires the two payloads to be identical.

Run directly:
`python3 tests/test_a_benched_league_leaves_the_record_page.py`
"""

import datetime as dt
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                    # noqa: E402

SRC = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
SOON = (dt.datetime.utcnow() + dt.timedelta(days=1)).date().isoformat()
# Yesterday, not a written-down day: a settled fixture pinned to a
# literal date ages out of `RECORD_EPOCH`'s window and starts failing on
# a morning nobody touched this file — the way the day's-pick tests went
# red at midnight on 2026-09-20.
PAST = (dt.datetime.utcnow() - dt.timedelta(days=1)).date().isoformat()

_INS = ("INSERT INTO bets (ts,sport,date,player,market,side,line,odds,"
        "stake_units,stake_dollars,status,category,actual,pnl_units) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)")


def _ledger(path=None):
    conn = ledger.connect(path or (Path(tempfile.mkdtemp()) / "l.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn


def _settled(conn, sport, category="main"):
    conn.execute(_INS, (PAST + "T00:00:00", sport, PAST, "X",
                        "pts", "OVER", 20.5, -110, 1.0, 10.0, "lost",
                        category, 12, -1.0))
    conn.commit()


def _prop(**kw):
    row = {"player": "A Wilson", "team": "LV", "opponent": "IND",
           "market": "pts", "market_label": "Points", "side": "OVER",
           "line": 20.5, "book": "fanduel", "odds": -115, "hit_prob": 0.62,
           "raw_prob": 0.62, "implied_prob": 0.56, "model_prob": 0.62,
           "projection": 24.0, "game_date": SOON, "date": SOON,
           "has_market": True, "recommended": True, "edge": 0.06,
           "confidence": 0.7, "grade": "A", "stake_units": 1.0,
           "logs": [], "recent_values": []}
    row.update(kw)
    return row


# --- the bench is outside the headline book ----------------------------
def test_the_bench_is_not_in_the_book_the_headline_counts():
    """THE ONE THING THAT MAKES ANY OF THIS WORK. If the bench category
    were inside `BOOK`, every assertion below would pass while the
    number Ethan asked to protect kept moving."""
    assert ledger.BENCH_CATEGORY not in ledger.BOOK
    assert ledger.BENCH_CATEGORY not in ledger.RECOMMENDED_CATEGORIES


def test_paper_would_not_have_worked_and_the_reason_is_written_down():
    """`BOOK` is ("main", "paper") on Ethan's own 2026-08-13 instruction,
    so "make it paper" would have left WNBA in the headline. The next
    person to reach for paper mode has to meet that."""
    assert "paper" in ledger.BOOK, "the premise of this whole file moved"
    i = SRC.index("BENCH_CATEGORY = ")
    why = SRC[max(0, i - 2000):i]
    assert "2026-08-13" in why, "nothing records why paper was not used"
    assert "paper_mode" in why, "nothing says the paper switch is global"


def test_wnba_is_benched_and_the_list_is_the_only_switch():
    assert ledger.is_benched("wnba") and ledger.is_benched("WNBA")
    for sp in ("nfl", "cfb", "mlb", "nba"):
        assert not ledger.is_benched(sp), sp


def test_one_answer_for_which_book_a_fresh_row_belongs_to():
    """`log_recommendations` files props and game bets through two
    separate inserts. A bench honoured by one of them is not a bench —
    the shape `game_day` took when eight inserts of eleven forgot it."""
    assert ledger.book_for("wnba", False) == ledger.BENCH_CATEGORY
    assert ledger.book_for("wnba", True) == ledger.BENCH_CATEGORY
    assert ledger.book_for("nfl", False) == "main"
    assert ledger.book_for("nfl", True) == "paper"


# --- new rows ----------------------------------------------------------
def test_a_new_wnba_pick_is_journaled_to_the_bench_with_no_dollars():
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "wnba", "date": SOON, "recommendations": [_prop()]})
    got = conn.execute(
        "SELECT category, stake_units, stake_dollars FROM bets").fetchone()
    assert got["category"] == ledger.BENCH_CATEGORY, dict(got)
    assert got["stake_dollars"] == 0.0, dict(got)
    # THE UNITS STAY AS SIZED. That is what keeps the bench measurable —
    # `performance` drops any row staked at zero, so zeroing the units
    # would make the benched record ungradeable and the bench pointless.
    assert got["stake_units"] > 0, dict(got)


def test_a_new_wnba_GAME_bet_is_benched_too():
    """That insert named no category at all and leaned on the schema's
    `DEFAULT 'main'`, so a bench applied only at the props loop would
    have sent every WNBA game bet straight to the headline."""
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "wnba", "date": SOON, "recommendations": [],
        "game_bets": [{"recommended": True, "bet_type": "moneyline",
                       "market": "moneyline", "pick": "LV", "team": "LV",
                       "home": "LV", "away": "IND", "book": "fanduel",
                       "odds": -122, "win_prob": 0.58, "edge": 0.03,
                       "confidence": 0.7, "grade": "B+", "stake_units": 1.0,
                       "date": SOON, "game_date": SOON}]})
    rows = conn.execute(
        "SELECT category, stake_dollars FROM bets").fetchall()
    assert rows, "the game bet was not journaled at all"
    for r in rows:
        assert r["category"] == ledger.BENCH_CATEGORY, dict(r)
        assert r["stake_dollars"] == 0.0, dict(r)


def test_another_league_is_untouched():
    conn = _ledger()
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": SOON,
        "recommendations": [_prop(player="J Allen", market="pass_yds",
                                  line=240.5)]})
    got = conn.execute(
        "SELECT category, stake_dollars FROM bets").fetchone()
    assert got["category"] == "main", dict(got)
    assert got["stake_dollars"] > 0, dict(got)


def test_the_likelihood_board_stops_paying_for_wnba_too():
    """It staked 0.25u of REAL dollars on that board from 2026-09-19.
    Asked through `likely_is_staked` rather than by reading the list, so
    the two cannot be edited apart."""
    assert not ledger.likely_is_staked("wnba")
    assert "wnba" not in ledger.LIKELY_LIVE_SPORTS
    assert ledger.likely_is_staked("nfl"), "the other leagues came off too"


def test_re_adding_wnba_to_the_live_list_alone_still_pays_it_nothing():
    """The bench is asked FIRST, so the two lists cannot be edited apart.
    Somebody widening the likelihood board back out — a routine edit,
    made for a reason that has nothing to do with this — would otherwise
    quietly put real money back on a benched league."""
    real = ledger.LIKELY_LIVE_SPORTS
    try:
        ledger.LIKELY_LIVE_SPORTS = real + ("wnba",)
        assert not ledger.likely_is_staked("wnba")
    finally:
        ledger.LIKELY_LIVE_SPORTS = real


# --- the rows already on the record ------------------------------------
def test_settled_wnba_rows_leave_the_headline_and_keep_their_result():
    conn = _ledger()
    _settled(conn, "wnba")
    _settled(conn, "nfl")
    assert ledger.performance(conn, sport="wnba")["settled"] == 1
    assert ledger.bench_existing(conn) == {"wnba": 1}
    assert ledger.performance(conn, sport="wnba")["settled"] == 0
    assert ledger.performance(conn, sport="nfl")["settled"] == 1
    # Still there, still graded, still readable — moved, not deleted.
    got = conn.execute(
        "SELECT category, status, pnl_units, stake_dollars FROM bets "
        "WHERE sport='wnba'").fetchone()
    assert got["category"] == ledger.BENCH_CATEGORY, dict(got)
    assert got["status"] == "lost" and got["pnl_units"] == -1.0, dict(got)
    assert got["stake_dollars"] == 0.0, "benched dollars were left standing"


def test_open_wnba_rows_move_too():
    """A bet still running would otherwise settle into the headline days
    after the league left it."""
    conn = _ledger()
    conn.execute(_INS, (PAST + "T00:00:00", "wnba", SOON, "X", "pts",
                        "OVER", 20.5, -110, 1.0, 10.0, "open", "main",
                        None, None))
    conn.commit()
    assert ledger.bench_existing(conn) == {"wnba": 1}
    assert conn.execute("SELECT category FROM bets").fetchone()[0] \
        == ledger.BENCH_CATEGORY


def test_the_paper_half_of_the_book_moves_as_well():
    """`BOOK` is both categories, so a WNBA row filed as paper is in the
    headline too and has to come out with the rest."""
    conn = _ledger()
    _settled(conn, "wnba", category="paper")
    assert ledger.performance(conn, sport="wnba")["settled"] == 1
    ledger.bench_existing(conn)
    assert ledger.performance(conn, sport="wnba")["settled"] == 0


def test_the_sweep_is_idempotent():
    conn = _ledger()
    _settled(conn, "wnba")
    assert ledger.bench_existing(conn) == {"wnba": 1}
    assert ledger.bench_existing(conn) == {}


def test_it_runs_wherever_the_ledger_OPENS_not_by_hand():
    """A manual step gets run on one machine and forgotten on the next —
    the reason `seal_forecasts` is a sweep. Checked across two PROCESSES,
    because `_SCHEMA_DONE` is per-process and a second `connect()` in one
    process deliberately skips the migration path."""
    db = Path(tempfile.mkdtemp()) / "l.db"
    conn = _ledger(db)
    _settled(conn, "wnba")
    conn.close()
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; from engine import ledger as L;"
         "c = L.connect(sys.argv[1]);"
         "print(c.execute('SELECT category FROM bets').fetchone()[0])",
         str(db)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == ledger.BENCH_CATEGORY, out.stdout


# --- the books the bench cannot re-categorise --------------------------
def test_the_pick_of_the_day_pool_drops_the_bench_and_a_scope_still_reads_it():
    """`potd` is the key the day-lock, the relock and the live tracker
    all query by, so those rows cannot be moved without breaking "the
    first qualifying pick is the day's pick". They come out of the
    POOLED figure instead — and the per-sport cut still answers in
    full, because a scoped read is somebody asking for the bench."""
    conn = _ledger()
    _settled(conn, "wnba", category=ledger.POTD_CATEGORY)
    _settled(conn, "nfl", category=ledger.POTD_CATEGORY)
    pooled = ledger.performance(conn, category=ledger.POTD_CATEGORY,
                                exclude_sports=ledger.BENCHED_SPORTS)
    assert pooled["settled"] == 1, pooled["settled"]
    scoped = ledger.performance(conn, sport="wnba",
                                category=ledger.POTD_CATEGORY,
                                exclude_sports=ledger.BENCHED_SPORTS)
    assert scoped["settled"] == 1, "the scoped cut went quiet instead"


def test_the_receipts_under_that_pool_match_it():
    """A list still showing a benched league's losses under a total that
    no longer counts them reads as a bug in the arithmetic."""
    conn = _ledger()
    _settled(conn, "wnba", category=ledger.POTD_CATEGORY)
    _settled(conn, "nfl", category=ledger.POTD_CATEGORY)
    got = ledger.recent_settled(conn, 40, category=ledger.POTD_CATEGORY,
                                exclude_sports=ledger.BENCHED_SPORTS)
    assert [r["sport"] for r in got] == ["nfl"], got
    # And the same rule as `performance`: asking FOR the bench answers.
    scoped = ledger.recent_settled(conn, 40, category=ledger.POTD_CATEGORY,
                                   sport="wnba",
                                   exclude_sports=ledger.BENCHED_SPORTS)
    assert [r["sport"] for r in scoped] == ["wnba"], scoped


def test_the_pooled_most_likely_report_drops_the_bench_too():
    """That board journals under `likely`/`likely_live`, which the live
    tracker reads by category as well. Same treatment, same reason —
    and `likely_report(sport="wnba")` still answers."""
    conn = _ledger()
    _settled(conn, "wnba", category="likely")
    _settled(conn, "nfl", category="likely")
    assert ledger.likely_report(conn)["settled"] == 1
    assert ledger.likely_report(conn)["calibration"]["n"] == 1
    # THE WHOLE SCOPED REPORT, not just its headline count: the bands,
    # the calibration and the receipts are the part anyone would read to
    # judge whether the model got better, and they come from this
    # function's own queries rather than from `performance`.
    mine = ledger.likely_report(conn, sport="wnba")
    assert mine["settled"] == 1, mine["settled"]
    assert mine["calibration"]["n"] == 1, mine["calibration"]
    assert [r["sport"] for r in mine["recent"]] == ["wnba"], mine["recent"]


def test_the_page_is_SERVED_a_pooled_pick_of_the_day_without_the_bench():
    """The assertions above hold `performance` to it; this holds the
    thing that actually reaches the browser. Two arguments at two call
    sites in `export_json` are exactly the kind that get added to the
    total and forgotten on the receipts."""
    import json
    conn = _ledger()
    _settled(conn, "wnba", category=ledger.POTD_CATEGORY)
    _settled(conn, "nfl", category=ledger.POTD_CATEGORY)
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, out)
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got["potd"]["settled"] == 1, got["potd"]["settled"]
    assert [r["sport"] for r in got["potd_recent"]] == ["nfl"], \
        got["potd_recent"]
    # AND NOT UNDER ITS OWN LABEL EITHER. The first cut shipped the
    # per-sport cut on the argument that a labelled row is honest rather
    # than hidden; Ethan wanted the league off the page, so the pooled
    # figure and the per-sport cut both drop it.
    assert "wnba" not in got["potd_by_sport"], got["potd_by_sport"]
    assert "nfl" in got["potd_by_sport"]


def test_the_edge_book_MOVES_its_rows_rather_than_only_hiding_them():
    """THE PAGE FILTER IS NOT THE WHOLE BENCH, and this is what the
    difference test cannot see.

    Hiding a row at read time leaves its category and its stake standing
    in the table, so it stays on the money book for the settle pass, the
    bankroll curve and every `sqlite3` query anyone runs on the droplet.
    The Edge book therefore MOVES its rows, which is also the only thing
    that zeroes the dollars. Asked with `exclude_sports=()` — the true
    unfiltered total — because with the page filter on, a row that was
    merely hidden and a row that was properly moved look identical."""
    conn = _ledger()
    _settled(conn, "wnba")
    raw = dict(exclude_sports=())
    assert ledger.performance(conn, **raw)["settled"] == 1
    ledger.bench_existing(conn)
    assert ledger.performance(conn, **raw)["settled"] == 0, \
        "the row was hidden from the page but left on the money book"
    got = conn.execute(
        "SELECT category, stake_dollars FROM bets").fetchone()
    assert got["category"] == ledger.BENCH_CATEGORY, dict(got)
    assert got["stake_dollars"] == 0.0, dict(got)


# --- the whole rule, in one assertion ----------------------------------
#: Every book a benched league can have rows in, with the category the
#: production writer really files it under. Hand-listed rather than read
#: off a constant on purpose: the point of the test below is to fail
#: when a NEW book appears and nobody taught it about the bench, and a
#: list derived from the code would quietly grow to match the code.
#: `main` and `paper` are in here deliberately, even though a benched
#: league's fresh Edge rows never reach them and `bench_existing` sweeps
#: the old ones at every open. That sweep runs inside a try/except that
#: warns and carries on rather than refusing to open the ledger, so
#: "the sweep did not run" is a state this page has to survive — and it
#: is the state the droplet is in for the seconds before the first open.
_ALL_BOOKS = ("benched", "main", "paper", "potd", "likely", "likely_live",
              "longshot", "longshot_watch", "stale", "form", "loose",
              "predmarket")


def _seed(conn, sport):
    """One settled row and one open row in every book, for one league."""
    for cat in _ALL_BOOKS:
        conn.execute(_INS, (PAST + "T00:00:00", sport, PAST, f"{sport} X",
                            "pts", "OVER", 20.5, -110, 1.0, 10.0, "lost",
                            cat, 12, -1.0))
        conn.execute(_INS, (PAST + "T00:00:00", sport, SOON, f"{sport} Y",
                            "pts", "OVER", 20.5, -110, 1.0, 10.0, "open",
                            cat, None, None))
    conn.commit()


def _exported(conn):
    import json
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, out)
    got = json.loads(out.read_text(encoding="utf-8"))
    got.pop("generated_at", None)      # the one field that always differs
    # AND THE SECOND CLOCK, ONE LEVEL DOWN, which the pop above never
    # reached because it is nested rather than top-level: the
    # `loss_patterns` block carries the miner's own `generated` stamp at
    # second resolution.
    #
    # The difference test below exports twice in a row, so whenever those
    # two calls straddled a second boundary the payloads differed on the
    # clock alone and the failure was reported as
    # "the record page changed when WNBA rows were added: ['loss_patterns']"
    # — a benched-league leak that was not there. Exporting an UNCHANGED
    # journal twice, 1.2s apart, reproduces it with no WNBA row involved
    # at all, which is how it was pinned.
    #
    # That is also why it was invisible when run by hand: standalone the
    # two exports land inside the same second, and the file passes 31/31.
    # Under `run_tests.py` — several files at a time, one vCPU — they do
    # not, so this went red only in the suite, only sometimes, and blamed
    # the code under test. A wall clock has no league, player or price in
    # it, so dropping it costs the assertion nothing.
    if isinstance(got.get("loss_patterns"), dict):
        got["loss_patterns"].pop("generated", None)
    return got


def test_two_exports_of_one_unchanged_journal_are_identical():
    """THE GUARD ON THE TEST BELOW, not on the ledger.

    The difference test only means something if the payload is a
    function of the JOURNAL. Every clock in it is a false positive
    waiting for a slow box, and it reads as the leak this file exists to
    catch, which is the worst way to fail: it accuses the code under
    test. `loss_patterns.generated` did exactly that — red in the suite,
    green by hand, because a parallel run is slow enough to cross a
    second between the two exports.

    So: export, cross a second deliberately, export again, and require
    the two to match with nothing added to the journal in between. This
    fails on the next nested timestamp instead of leaving it to a loaded
    machine to find.
    """
    import time
    conn = _ledger()
    _seed(conn, "nfl")
    first = _exported(conn)
    time.sleep(1.1)                    # deliberately straddle a second
    second = _exported(conn)
    if first != second:
        moved = sorted(k for k in set(first) | set(second)
                       if first.get(k) != second.get(k))
        raise AssertionError(
            "the export moved while the journal stood still — a clock, "
            f"not a bet: {moved}")


def test_the_record_page_cannot_tell_wnba_exists():
    """THE WHOLE RULE, AND THE ONLY SHAPE THAT CAN PROVE IT.

    Ethan: "I don't want wnba Past bet or new bet on the record page."

    Scanning the payload for the word would pass while a POOLED total
    silently carried these rows — a number has no league name in it, and
    a pooled total quietly counting a league nobody can see is exactly
    the kind of quiet this repo keeps being fixed for. So the test is a
    difference instead: export a journal, add a full set of WNBA rows to
    every book, export again, and require the two payloads to be
    IDENTICAL. Any figure that moves, any key that appears, any receipt
    that shows up, fails this.

    It fails for a book that does not exist yet, too: `_ALL_BOOKS` is
    hand-listed, so a new one has to be added here deliberately.
    """
    conn = _ledger()
    _seed(conn, "nfl")
    before = _exported(conn)
    _seed(conn, "wnba")
    after = _exported(conn)
    # ONE EXEMPTION, AND IT IS NOT A BET. `forecast_log` is the sealed
    # chain's integrity readout — {ok, n, head, broken_at} — and `n`
    # counts what the chain has SEALED, with no league, player or price
    # in it. A benched league's picks are still published on its own
    # board and still sealed, which is the point of sealing: the chain
    # says nobody rewrote a claim afterwards, and a chain that quietly
    # skipped a league would be worth less, not more.
    before.pop("forecast_log", None)
    after.pop("forecast_log", None)
    # AND ONE MORE, WHICH IS THE RULE RATHER THAN A HOLE IN IT.
    # `all_time.benched_settled` is a COUNT of the rows this page is not
    # counting — no league, no bet, nothing to scope to. It has to move
    # when benched rows are added, because a disclosure that stayed at
    # zero while rows piled up behind it would be the quiet this whole
    # file is written against. Everything else in `all_time` must not
    # move, and that is asserted rather than exempted.
    assert (before["all_time"]["benched_settled"]
            < after["all_time"]["benched_settled"]), "the count did not move"
    for blob in (before, after):
        blob["all_time"] = {k: v for k, v in blob["all_time"].items()
                            if k != "benched_settled"}
    if before != after:
        moved = sorted(k for k in set(before) | set(after)
                       if before.get(k) != after.get(k))
        raise AssertionError(
            f"the record page changed when WNBA rows were added: {moved}")


def test_the_same_journal_still_knows_every_one_of_those_rows():
    """THE OTHER HALF, and the reason the test above is not just a
    deletion passing as a feature. The bench is not published; it is
    still kept, still graded and still readable at the terminal, which
    is how anyone finds out whether the model got better."""
    conn = _ledger()
    _seed(conn, "wnba")
    n = conn.execute(
        "SELECT COUNT(*) FROM bets WHERE sport='wnba'").fetchone()[0]
    assert n == len(_ALL_BOOKS) * 2, n
    graded = conn.execute(
        "SELECT COUNT(*) FROM bets WHERE sport='wnba' AND status='lost'"
    ).fetchone()[0]
    assert graded == len(_ALL_BOOKS), graded


def test_the_page_is_TOLD_which_leagues_are_benched():
    """Absence alone is ambiguous, and the page was about to resolve it
    the wrong way: the Pick-of-the-Day line falls back to "No settled
    Picks of the Day yet in this league" when a record is missing, and
    on a benched league that is false — there are settled picks, they
    are on paper. So the export names the benched leagues and the board
    says the true thing."""
    conn = _ledger()
    got = _exported(conn)
    assert got["benched_sports"] == ["wnba"], got["benched_sports"]
    assert "wnba" not in got["tracked_sports"], got["tracked_sports"]
    src = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "benched_sports" in src, \
        "the page cannot tell 'none yet' from 'not published'"
    # The claim the page makes has to be the one the journal keeps.
    i = src.index("benched_sports")
    said = src[i:i + 500]
    assert "paper" in said and "graded" in said, said[:200]


# --- and it can be checked, which is the point of benching -------------
def _boxed(rows):
    """A journal at `ledger.DEFAULT_DB`, so `homecheck` reads THIS one.

    Repointed rather than passed, because `homecheck._journal_ro` takes
    the path from the module — and the whole reason it does is that it
    opens `mode=ro`, so a check can never take the write lock off the
    settler. A test that handed it a connection would not be testing the
    thing that matters.
    """
    import homecheck
    real = ledger.DEFAULT_DB
    db = Path(tempfile.mkdtemp()) / "l.db"
    conn = _ledger(db)
    # The journal's unique key is (sport, date, player, market, category),
    # so each row needs its own player — two losses for one league are
    # two bets, not one written twice.
    for i, (sport, status, pnl, cat) in enumerate(rows):
        conn.execute(_INS, (PAST + "T00:00:00", sport, PAST, f"P{i}",
                            "pts", "OVER", 20.5,
                            -110, 1.0, 10.0, status, cat, 1, pnl))
    conn.commit()
    conn.close()
    ledger.DEFAULT_DB = db
    try:
        return "\n".join(homecheck.bench())
    finally:
        ledger.DEFAULT_DB = real


def test_the_check_says_plainly_that_benching_HELPED_when_it_did():
    got = _boxed([("nfl", "won", 0.9, "main"), ("nfl", "lost", -1.0, "main"),
                  ("wnba", "lost", -1.0, ledger.BENCH_CATEGORY),
                  ("wnba", "lost", -1.0, ledger.BENCH_CATEGORY)])
    assert "better" in got, got
    assert "worse" not in got, got
    # AND THE PRICE OF IT, as loudly as the improvement. A book that
    # improved by shedding a third of its sample has a prettier number
    # and a weaker claim, and a check that printed only the ROI would be
    # selling the first while hiding the second.
    assert "2 fewer settled bets" in got, got


def test_the_check_can_tell_us_we_were_WRONG():
    """THE ONE THAT MATTERS. WNBA was benched because Ethan asked, not
    because it was shown to be losing — nobody had measured it. If it
    was winning, the bench cost the record, and a check that could only
    confirm the decision would be worth nothing."""
    got = _boxed([("nfl", "lost", -1.0, "main"), ("nfl", "lost", -1.0, "main"),
                  ("wnba", "won", 0.9, ledger.BENCH_CATEGORY),
                  ("wnba", "won", 0.9, ledger.BENCH_CATEGORY)])
    assert "worse" in got, got
    assert "IT IS WINNING" in got, got
    assert "BENCHED_SPORTS" in got, "it does not say how to undo it"


def test_an_empty_book_is_not_reported_as_an_unchanged_one():
    """"ROI unchanged by 0.00 points" over nothing reads as a measured
    finding, and this check exists precisely because an unmeasured claim
    was being taken for one."""
    got = _boxed([])
    assert "unchanged" not in got, got
    assert "nothing has settled" in got, got


def test_the_check_is_registered_and_runs_with_the_rest():
    import homecheck
    assert "bench" in homecheck.CHECKS, sorted(homecheck.CHECKS)
    fn, desc, auto = homecheck.CHECKS["bench"]
    assert fn is homecheck.bench
    assert auto is True, "it is read-only, so `all` should carry it"
    assert "bench" in desc.lower()


def test_the_check_never_takes_the_write_lock():
    """`homecheck`'s docstring promises every subcommand is safe to run
    mid-cycle. `ledger.connect()` runs migrations on a process's first
    connection — writes, on the file the refresher and settler are both
    holding — so this check has to go through the read-only opener."""
    import inspect
    import homecheck
    src = inspect.getsource(homecheck.bench)
    assert "_journal_ro()" in src, src[:300]
    assert "ledger.connect(" not in src, "it opens the journal writable"


# --- the record says what it leaves out --------------------------------
def test_the_record_discloses_how_many_bets_the_bench_keeps_out():
    """OFF THE PAGE IS NOT THE SAME AS UNSAID.

    Every other exclusion on this page is disclosed — `hidden_settled`
    exists so the record "can show what it is leaving out rather than
    quietly leaving it out", in its own comment. The bench had no such
    line, so a reader could not tell a record that leaves nothing out
    from one that leaves a losing league out. On a page selling picks,
    those are not the same claim.

    A COUNT, AND ONLY A COUNT. No league named, no bet shown, nothing
    scoped to — Ethan, 2026-09-21: "I don't want wnba Past bet or new
    bet on the record page."
    """
    conn = _ledger()
    _settled(conn, "nfl")
    _settled(conn, "wnba")
    _settled(conn, "wnba", category=ledger.BENCH_CATEGORY)
    got = _exported(conn)
    assert got["overall"]["settled"] == 1, got["overall"]["settled"]
    assert got["all_time"]["benched_settled"] == 2, got["all_time"]
    # Still no league, no row, nowhere to click.
    assert "wnba" not in got["by_sport"]
    assert "wnba" not in got["tracked_sports"]


def test_the_page_prints_that_number_rather_than_shipping_it_unread():
    """A disclosure nothing renders is not a disclosure."""
    src = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = src.index("function recEpochHTML")
    body = src[i:src.index("function recTile")]
    assert "benched_settled" in body, "the export ships it and nothing reads it"
    # It has to survive the early return, or a record with no pre-epoch
    # rows would print nothing at all about the bench.
    assert "!hidden && !benched" in body, body[:600]
    assert "still graded" in body, body[:600]


# --- and it is shown, not vanished -------------------------------------
def test_the_bench_has_NO_heading_on_the_record():
    """IT HAD ONE, FOR ABOUT AN HOUR. The first cut showed the bench
    under "Benched — no money, still graded", on the argument that a
    league whose rows stop appearing is misleading quiet. Ethan saw it
    and said what he actually wanted: "I don't want wnba Past bet or new
    bet on the record page. I only want it as paper bets."

    Kept as a test rather than deleted with the code, because the
    argument for showing it is a good one and the next person to have it
    should find the answer here instead of shipping it again."""
    keys = [k for k, _label, _cats in ledger.SHADOW_SECTIONS]
    assert ledger.BENCH_CATEGORY not in keys, keys
    assert ledger.BENCH_CATEGORY not in [
        c for _k, _l, cats in ledger.SHADOW_SECTIONS for c in cats]


def test_the_bench_is_reversible_by_emptying_one_tuple():
    """When the model earns it back, nothing else should have to move."""
    real = ledger.BENCHED_SPORTS
    try:
        ledger.BENCHED_SPORTS = ()
        assert not ledger.is_benched("wnba")
        assert ledger.book_for("wnba", False) == "main"
        assert ledger.likely_is_staked("wnba") is False, \
            "LIKELY_LIVE_SPORTS has to be restored separately — say so"
    finally:
        ledger.BENCHED_SPORTS = real


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
