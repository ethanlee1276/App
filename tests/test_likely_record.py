"""The paper book was write-only until this: journaled, graded, unread.

Ethan, 2026-08-30: "we should also record the bets on the most likley
page and if it does good then we will attack money and roi and shit to
it. maybe we do papr bets with it."

Half of that already existed. `ledger.log_most_likely` writes the top of
the board to `category='likely'` every night at zero dollar exposure, and
`settle_from_history` grades it on the same pass as everything else.

THE OTHER HALF DID NOT, and its absence is the interesting part. Nothing
read the bucket back. Rows went in nightly, graded themselves, and were
seen by no report, no page and no command — a measurement nobody can read
is not a measurement, and "if it does good" had no way to be answered.
The same shape as every other bug in this file's neighbourhood: a claim
the code makes and never checks.

TWO TESTS, KEPT APART, and this file pins that they stay apart:

    is the number true    we said 68%, did 68% land? The claim the board
                          actually makes, and the only one it was built
                          to make.
    would it have paid    ROI at the price shown. A perfectly calibrated
                          board still loses to the vig — the 22,168-row
                          replay put it at -5% to -7.4% claimed at every
                          depth — so passing the first is not passing
                          this one.

Money is gated on the second. And below LIKELY_VERDICT_N settled rows the
report refuses to offer a verdict at all, because every wrong turn this
bucket has produced was a small sample read as a result.

Run directly: `python3 tests/test_likely_record.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import ledger


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))


#: The ledger's unique key is (sport, date, player, market, category), so
#: every fixture row needs its own player — the same constraint that
#: makes the real journal idempotent across a night's rebuilds.
_SEQ = [0]


def _bet(conn, claimed, status, market="anytime_td", odds=-120,
         category="likely", pnl=None):
    if pnl is None:
        mult = (100.0 / abs(odds)) if odds < 0 else (odds / 100.0)
        pnl = 0.1 * mult if status == "won" else -0.1
    _SEQ[0] += 1
    conn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
        "hit_prob,edge,stake_units,stake_dollars,ts,status,category,pnl_units)"
        " VALUES ('nfl','2026-W1',?,?,'OVER',0.5,?,'DK',?,0,0.1,0,'now',"
        "?,?,?)", (f"P{_SEQ[0]}", market, odds, claimed, status, category,
                   pnl))
    conn.commit()


# --- the side the journal writes ------------------------------------------
def _likely_row(market, side, prob, line=0.5, odds=-500, player="P"):
    return {"kind": "prop", "player": player, "market": market, "side": side,
            "line": line, "book": "dk", "odds": odds, "model_prob": prob,
            "implied_prob": None, "game_date": "2026-08-20"}


def _journal(conn, row, sport="mlb"):
    ledger.log_most_likely(conn, {"sport": sport, "date": "2026-08-20",
                                  "most_likely": [row]})
    return conn.execute("SELECT market, side, line, hit_prob FROM bets "
                        "WHERE category='likely'").fetchall()


def test_a_home_run_row_is_journaled_on_the_side_the_board_showed():
    """THE BUG, AND IT COST 42.8% OF THE BOOK'S LOSSES. `log_most_likely`
    normalised LONGSHOT_MARKETS rows to `side, line = "OVER", 0.5`. The
    line half is why the branch exists — a yes/no row carries none. The
    side half was written when this board showed only overs and survived
    the day it began admitting them (2026-09-02).

    A home-run OVER cannot reach this board: P(a hitter homers) is
    0.05-0.15 and `likely.MIN_PROB` is 0.30. So every home-run row here
    is an UNDER carrying P(no home run) — and every one was graded as
    the over. `likely_report` on 2026-09-06: claimed 94.0%, hit 10.0%
    over ten rows."""
    conn = _conn()
    got = _journal(conn, _likely_row("home_runs", "under", 0.94))
    assert len(got) == 1, got
    assert got[0]["side"] == "UNDER", tuple(got[0])
    assert got[0]["hit_prob"] == 0.94
    # The line half of the normalisation still happens.
    assert got[0]["line"] == 0.5


def test_a_touchdown_yes_row_still_normalises_to_the_over():
    """The other half must not regress. `likely.from_watch` renders a
    scorer row as side "yes" with no line, and `_grade_side_aware`
    compares against "OVER" and needs a number — which is the whole
    reason this branch exists."""
    conn = _conn()
    got = _journal(conn, _likely_row("anytime_td", "yes", 0.55, line=None,
                                     odds=-120), sport="nfl")
    assert len(got) == 1, got
    assert got[0]["side"] == "OVER" and got[0]["line"] == 0.5, tuple(got[0])


def test_a_no_row_is_journaled_as_an_under_not_as_a_yes():
    conn = _conn()
    got = _journal(conn, _likely_row("anytime_td", "no", 0.68, line=None,
                                     odds=-180), sport="nfl")
    assert got[0]["side"] == "UNDER" and got[0]["line"] == 0.5, tuple(got[0])


# --- and the rows already written on the wrong side -----------------------
def _hr(conn, side, prob, category="likely", market="home_runs"):
    _SEQ[0] += 1
    conn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
        "hit_prob,edge,stake_units,stake_dollars,ts,status,category,pnl_units)"
        " VALUES ('mlb','2026-08-20',?,?,?,0.5,-500,'DK',?,0,0.1,0,'now',"
        "'lost',?,-0.1)", (f"P{_SEQ[0]}", market, side, prob, category))
    conn.commit()
    return f"P{_SEQ[0]}"


def test_the_repair_flips_only_the_rows_that_could_not_be_real():
    """A repair that guesses turns one data error into two. The test is
    home_runs + likely + side OVER + a probability above a coin flip,
    and nothing else — anytime_td is excluded on purpose because an OVER
    above 0.5 is a real bet there."""
    conn = _conn()
    bad = _hr(conn, "OVER", 0.94)
    ok_under = _hr(conn, "UNDER", 0.94)
    real_over = _hr(conn, "OVER", 0.12)             # a genuine long shot
    other_book = _hr(conn, "OVER", 0.94, category="main")
    td = _hr(conn, "OVER", 0.55, market="anytime_td")
    got = ledger.repair_inverted_likely_sides(conn)
    assert got["flipped"] == 1, got
    sides = {r["player"]: (r["side"], r["status"]) for r in
             conn.execute("SELECT player, side, status FROM bets")}
    assert sides[bad] == ("UNDER", "open"), sides
    for p in (ok_under,):
        assert sides[p][0] == "UNDER" and sides[p][1] == "lost", sides[p]
    for p in (real_over, other_book, td):
        assert sides[p] == ("OVER", "lost"), (p, sides[p])


def test_the_repair_reopens_rather_than_rescoring_by_hand():
    """A second copy of the settle arithmetic living in a repair function
    is one nobody looks at, and the one nobody looks at is the one that
    drifts. The side is corrected and the row goes back through the same
    settle pass as everything else."""
    conn = _conn()
    _hr(conn, "OVER", 0.94)
    ledger.repair_inverted_likely_sides(conn)
    r = conn.execute("SELECT status, pnl_units FROM bets").fetchone()
    assert r["status"] == "open" and r["pnl_units"] is None, tuple(r)


def test_the_repair_is_idempotent():
    conn = _conn()
    _hr(conn, "OVER", 0.94)
    assert ledger.repair_inverted_likely_sides(conn)["flipped"] == 1
    assert ledger.repair_inverted_likely_sides(conn)["flipped"] == 0


# --- the threshold is derived, not picked ---------------------------------
def test_the_verdict_threshold_comes_from_the_standard_error():
    """n = (2 * 0.5 / 0.10)^2 — two standard errors at the worst-case
    variance, resolving a ten-point calibration gap. A round number
    chosen by feel is how a bucket like this gets read too early."""
    assert ledger.LIKELY_VERDICT_N == int((2 * 0.5 / 0.10) ** 2) == 100


# --- it reads the right bucket --------------------------------------------
def test_the_report_reads_the_bucket_the_journal_writes():
    conn = _conn()
    _bet(conn, 0.60, "won")
    assert ledger.likely_report(conn)["calibration"]["n"] == 1


def test_other_buckets_do_not_leak_in():
    """`longshot` and `main` carry the same markets. A category filter
    missing from one query is how a paper book quietly becomes a mixture
    of three."""
    conn = _conn()
    _bet(conn, 0.60, "won")
    _bet(conn, 0.10, "won", category="longshot")
    _bet(conn, 0.55, "lost", category="main")
    p = ledger.likely_report(conn)
    assert p["calibration"]["n"] == 1
    assert sum(d["n"] for d in p["by_market"].values()) == 1
    assert sum(b["n"] for b in p["bands"]) == 1


def test_open_rows_are_counted_and_not_graded():
    conn = _conn()
    _bet(conn, 0.60, "open", pnl=0)
    p = ledger.likely_report(conn)
    assert p["open"] == 1
    assert p["calibration"]["n"] == 0


# --- the two tests stay apart ---------------------------------------------
def test_calibration_and_roi_are_separate_fields():
    """Folding them together is the mistake the whole bucket exists to
    avoid: a board can print true numbers and still lose to the vig."""
    conn = _conn()
    _bet(conn, 0.60, "won")
    p = ledger.likely_report(conn)
    assert "calibration" in p and "roi" in p
    assert "roi" not in p["calibration"]


def test_a_calibrated_board_that_loses_money_says_both_things():
    """The expected outcome of the replay, in one report: hit rate lands
    where claimed, ROI is negative. Neither number may hide the other."""
    conn = _conn()
    # 60% claimed, 60% actual, at -200 — true and unprofitable.
    for _ in range(6):
        _bet(conn, 0.60, "won", odds=-200)
    for _ in range(4):
        _bet(conn, 0.60, "lost", odds=-200)
    p = ledger.likely_report(conn)
    assert p["calibration"]["actual"] == 0.6
    assert p["calibration"]["gap"] == 0.0
    assert p["roi"] < 0, p["roi"]


# --- the refusal ----------------------------------------------------------
def test_no_verdict_is_offered_on_a_thin_sample():
    conn = _conn()
    for _ in range(5):
        _bet(conn, 0.60, "won")
    p = ledger.likely_report(conn)
    assert p["enough"] is False
    assert "needed" in p["verdict"] and str(p["needed"]) in p["verdict"]


def test_the_thin_verdict_does_not_hedge_its_way_to_a_claim():
    """A hedged verdict still gets acted on. At this sample the honest
    output is the row count and nothing else."""
    conn = _conn()
    for _ in range(5):
        _bet(conn, 0.90, "won")      # 5-0, and it means nothing
    v = ledger.likely_report(conn)["verdict"].lower()
    assert "no verdict" in v
    for word in ("promising", "encouraging", "trending", "on track"):
        assert word not in v, word


def test_an_empty_bucket_says_so_rather_than_dividing_by_zero():
    p = ledger.likely_report(_conn())
    assert p["calibration"]["n"] == 0
    assert p["calibration"]["actual"] is None
    assert p["bands"] == [] and p["by_market"] == {}
    assert "settled yet" in p["verdict"]


# --- the noise band -------------------------------------------------------
def test_a_gap_inside_the_noise_band_is_not_called_real():
    conn = _conn()
    for _ in range(5):
        _bet(conn, 0.60, "won")
    for _ in range(5):
        _bet(conn, 0.60, "lost")
    cal = ledger.likely_report(conn)["calibration"]
    assert cal["gap"] == -0.10
    assert cal["noise_band"] > 0.10          # ten rows resolve nothing
    assert cal["real"] is False


def test_the_same_gap_becomes_real_with_enough_rows():
    """The band is the whole point: identical gap, different verdict,
    decided by sample size rather than by how the number looks."""
    conn = _conn()
    for _ in range(300):
        _bet(conn, 0.60, "won")
    for _ in range(300):
        _bet(conn, 0.60, "lost")
    cal = ledger.likely_report(conn)["calibration"]
    assert cal["gap"] == -0.10
    assert cal["real"] is True


def test_a_verdict_at_size_names_the_direction_of_the_miss():
    conn = _conn()
    for _ in range(300):
        _bet(conn, 0.60, "won")
    for _ in range(300):
        _bet(conn, 0.60, "lost")
    v = ledger.likely_report(conn)["verdict"]
    assert "real miss" in v
    assert "money stays off" in v


# --- the breakdowns -------------------------------------------------------
def test_bands_split_the_board_by_what_it_claimed():
    """An average hides the shape, and the top of the board is what a
    reader actually bets."""
    conn = _conn()
    _bet(conn, 0.35, "lost")
    _bet(conn, 0.80, "won")
    bands = {(b["lo"], b["hi"]): b for b in ledger.likely_report(conn)["bands"]}
    assert bands[(0.30, 0.45)]["actual"] == 0.0
    assert bands[(0.75, 1.01)]["actual"] == 1.0


def test_an_empty_band_is_dropped_rather_than_reported_as_zero():
    conn = _conn()
    _bet(conn, 0.80, "won")
    assert [(b["lo"], b["hi"])
            for b in ledger.likely_report(conn)["bands"]] == [(0.75, 1.01)]


def test_markets_are_broken_out_because_they_are_the_shelves():
    conn = _conn()
    _bet(conn, 0.70, "won", market="receptions")
    _bet(conn, 0.40, "lost", market="pass_yds")
    got = ledger.likely_report(conn)["by_market"]
    assert got["receptions"]["actual"] == 1.0
    assert got["pass_yds"]["actual"] == 0.0


# --- and it is actually reachable -----------------------------------------
def test_the_record_payload_carries_it():
    """The failure this whole file is about: a report that exists and is
    served nowhere is the same as no report."""
    assert '"likely": likely_report(conn, since=since)' in _src("engine", "ledger.py")


def test_the_record_page_draws_it():
    src = _src("web", "js", "app.js")
    assert "function recLikelySection(lk)" in src
    assert "recLikelySection(d.likely)" in src


def test_the_page_shows_the_verdict_rather_than_burying_it():
    src = _src("web", "js", "app.js")
    at = src.index("function recLikelySection(lk)")
    body = src[at:src.index("function recLongshotSection(ls)", at)]
    assert "lk.verdict" in body
    # Above the tiles, not under them — a number that looks like a result
    # is read before any caveat beside it.
    assert body.index("lk.verdict") < body.index('class="stats rec-kpis"')


def test_the_page_says_calibration_is_not_profit():
    src = _src("web", "js", "app.js")
    at = src.index("function recLikelySection(lk)")
    body = src[at:src.index("function recLongshotSection(ls)", at)]
    assert "still lose" in body and "money stays off" in body


def test_there_is_a_command_for_the_box_that_holds_the_ledger():
    """Ethan reads this over ssh, not in a browser."""
    src = _src("launch.py")
    assert "def show_likely()" in src
    assert 'if "--likely" in argv:' in src


def test_the_command_prints_the_refusal_last():
    """A reader who stops early still has to hit the sentence that
    decides what happens next."""
    src = _src("launch.py")
    at = src.index("def show_likely()")
    body = src[at:src.index("def show_gates()", at)]
    assert body.index("Not enough to act on") > body.index("by market")



def test_each_sport_carries_its_own_two_tests():
    """Ethan, 2026-09-01: "make sure you dont stop testing each sport
    until the most likley for eavh sport is making money and positive
    roi." A standing order is an instrument, not a task: every sport in
    the likely book reports its own calibration gap and ROI, and a
    sport under the settle floor says how far it has to go instead of
    passing its early number off as a verdict."""
    conn = _conn()
    for _ in range(6):
        _bet(conn, 0.65, "won")
    for _ in range(4):
        _bet(conn, 0.65, "lost")
    got = ledger.likely_report(conn)
    sp = got["by_sport"]["nfl"]
    assert sp["n"] == 10 and sp["w"] == 6
    assert sp["actual"] == 0.6 and sp["claimed"] == 0.65
    assert isinstance(sp["roi"], float)
    assert not sp["enough"]
    assert "of 100 settles" in sp["note"] and "no verdict" in sp["note"]


def test_the_weekly_pass_prints_the_per_sport_scoreboard():
    with open(os.path.join(ROOT, "engine", "maintenance.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "likely book {_sp}:" in src
    assert 'by_sport' in src

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
