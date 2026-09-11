"""The parlay journal: §11 logging, settling, and §13's Record bucket.

The Parlay Zone shipped publishing tickets that nothing could check. These
tests are about the properties that make the record trustworthy rather than
about the code that produces it:

  * a ticket journals ONCE per slate no matter how often the board rebuilds;
  * legs are graded by the singles journal, never a second time here;
  * the bankroll never moves — §13 puts parlays on probation;
  * the record is never blended with singles (§13's display rules);
  * no price is invented where none exists.
"""

import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger, parlayledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))


def _leg(player, market="total_bases", side="OVER", line=1.5, odds=-110,
         p=0.60, book="DK"):
    return {"player": player, "team": "NYM", "market": market, "side": side,
            "line": line, "odds": odds, "book": book, "p_final": p,
            "market_label": "Total Bases", "grade": "A"}


def _ticket(**over):
    t = {
        "sport": "mlb", "rank": 1, "parlay_type": "A", "qualified": True,
        "grade": "play", "slate_play": False,
        "legs": [_leg("Alpha Guy"), _leg("Beta Guy")],
        "pairs": [{"a": "Alpha Guy", "b": "Beta Guy", "rho": 0.30,
                   "rho_priced": 0.135, "rho_measured": False,
                   "mechanism": "same lineup, shared run environment",
                   "clash": 0}],
        "clash_screen": "Types 1-7 checked · cleared",
        "naive_product_dec": 3.63, "modeled_joint": 0.31,
        "independent_joint": 0.28, "edge_at_ceiling_points": 2.4,
        "threshold_points": 2.0,
        "correlation_tax_best_case": 0.04, "correlation_tax_worst_case": 0.15,
        "singles_alternative_same_stake": 0.02,
        "ev_parlay_at_required": 0.05,
        "stake_units": 0.0,
    }
    t.update(over)
    return t


def _board(**over):
    b = {"sport": "mlb", "date": D, "tickets": [_ticket()]}
    b.update(over)
    return b


def _single(conn, player, market="total_bases", side="OVER", line=1.5,
            odds=-110, status="open", actual=None, closing=None):
    """A leg's life as a single — every parlay leg is one of these first."""
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, book,"
        " odds, stake_units, stake_dollars, status, category, actual,"
        " closing_line) VALUES ('x','mlb',?,?,?,?,?,'DK',?,0.5,5.0,?,'main',"
        "?,?)", (D, player, market, side, line, odds, status, actual, closing))
    conn.commit()


# --- logging ----------------------------------------------------------------
def test_a_published_ticket_is_journaled_with_its_legs():
    conn = _conn()
    assert parlayledger.log_board(conn, _board()) == 1
    p = conn.execute("SELECT * FROM parlays").fetchone()
    assert p["sport"] == "mlb" and p["n_legs"] == 2 and p["status"] == "open"
    legs = conn.execute("SELECT * FROM parlay_legs ORDER BY leg_no").fetchall()
    assert [l["player"] for l in legs] == ["Alpha Guy", "Beta Guy"]


def test_the_same_ticket_does_not_journal_twice_on_a_rebuild():
    """The board rebuilds every 60 seconds. Without an identity keyed on the
    legs, one night's single observation would count several hundred times
    and the probation bar would be cleared by a refresh loop."""
    conn = _conn()
    assert parlayledger.log_board(conn, _board()) == 1
    for _ in range(5):
        assert parlayledger.log_board(conn, _board()) == 0
    assert conn.execute("SELECT COUNT(*) FROM parlays").fetchone()[0] == 1


def test_leg_order_does_not_create_a_second_ticket():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    flipped = _ticket(legs=[_leg("Beta Guy"), _leg("Alpha Guy")])
    assert parlayledger.log_board(conn, _board(tickets=[flipped])) == 0


def test_only_rank_one_is_journaled():
    """The shortlist exists so the page can show its work. Four constructions
    off one slate share legs, so they share their outcome — counting them as
    four observations quadruples the sample without the evidence."""
    conn = _conn()
    second = _ticket(rank=2, legs=[_leg("Gamma Guy"), _leg("Delta Guy")])
    parlayledger.log_board(conn, _board(tickets=[_ticket(), second]))
    assert conn.execute("SELECT COUNT(*) FROM parlays").fetchone()[0] == 1


def test_a_declined_ticket_is_journaled_too():
    """§12 says "no qualifying parlay" should be the most common output by a
    wide margin. Journaling only the tickets that cleared would measure the
    gates on the handful of nights they said yes — and never test the no."""
    conn = _conn()
    parlayledger.log_board(conn, _board(
        tickets=[_ticket(grade="short", qualified=False)]))
    p = conn.execute("SELECT grade, qualified FROM parlays").fetchone()
    assert p["grade"] == "short" and p["qualified"] == 0


def test_a_board_with_no_tickets_journals_nothing():
    conn = _conn()
    assert parlayledger.log_board(conn, _board(tickets=[])) == 0


def test_the_reasoning_records_the_priced_rho_not_the_raw_one():
    """The joint was built from the priced rho — estimates get shrunk,
    measurements do not. Logging the raw number would leave a post-mortem
    arguing with an input the model never used."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    txt = conn.execute("SELECT conditional_reasoning FROM parlays").fetchone()[0]
    assert "+0.14" in txt or "+0.13" in txt      # 0.135 priced, not 0.30
    assert "shared run environment" in txt


def test_a_measured_correlation_is_marked_as_measured():
    conn = _conn()
    t = _ticket()
    t["pairs"][0].update(rho_measured=True, rho_priced=0.637)
    parlayledger.log_board(conn, _board(tickets=[t]))
    txt = conn.execute("SELECT conditional_reasoning FROM parlays").fetchone()[0]
    assert "(measured)" in txt


def test_the_dominance_ratio_is_logged():
    """§11 wants EV_parlay / EV_singles. Publishing only the singles side
    left the journal recording what we gave up but not what we got."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    assert conn.execute(
        "SELECT dominance_ratio FROM parlays").fetchone()[0] == 2.5


# --- no invented price ------------------------------------------------------
def test_no_quoted_price_is_invented():
    """No feed we ingest carries SGP prices and an SGP price is not derivable
    from the leg prices. A number in quoted_dec would be a fabrication, and
    §11's by-book tax table would then be measuring our own assumption."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    p = conn.execute("SELECT quoted_dec, assumed_dec, price_basis "
                     "FROM parlays").fetchone()
    assert p["quoted_dec"] is None
    assert p["assumed_dec"] is not None
    assert p["price_basis"] == "assumed_likely_case"


def test_the_grading_price_sits_between_the_two_taxes():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    p = conn.execute("SELECT naive_product_dec, assumed_dec, correlation_tax "
                     "FROM parlays").fetchone()
    assert 0.04 < p["correlation_tax"] < 0.15
    assert p["assumed_dec"] < p["naive_product_dec"]


def test_the_by_book_tax_table_is_empty_and_says_why():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    tax = parlayledger.report(conn)["tax_by_book"]
    assert tax["books"] == []
    assert "not derivable" in tax["note"]


# --- settling ---------------------------------------------------------------
def test_a_ticket_waits_while_any_leg_is_open():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="open")
    r = parlayledger.settle(conn)
    assert r["settled"] == 0 and r["waiting"] == 1
    assert conn.execute("SELECT status FROM parlays").fetchone()[0] == "open"


def test_a_ticket_waits_when_a_leg_has_no_single_at_all():
    """§14: a leg only exists because it earned the board as a single. If
    the single is missing, something is wrong upstream — grading around the
    gap would invent a verdict."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    assert parlayledger.settle(conn)["settled"] == 0


def test_every_leg_winning_wins_the_ticket():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    assert parlayledger.settle(conn)["settled"] == 1
    p = conn.execute("SELECT status, pnl_units FROM parlays").fetchone()
    assert p["status"] == "won" and p["pnl_units"] > 0


def test_one_leg_losing_loses_the_ticket():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    p = conn.execute("SELECT status, pnl_units FROM parlays").fetchone()
    assert p["status"] == "lost" and p["pnl_units"] == -1.0


def test_legs_are_not_graded_a_second_time_here():
    """The verdict is READ from the singles journal, never recomputed. One
    grading path means the parlay record can never disagree with the record
    its own legs are in — and it inherits the premature-settle guard."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    # A single graded WON on an actual that plainly lost. Absurd on purpose:
    # if this module grades, it will say lost and disagree with the journal.
    _single(conn, "Alpha Guy", status="won", actual=0.0)
    _single(conn, "Beta Guy", status="won", actual=0.0)
    parlayledger.settle(conn)
    assert conn.execute("SELECT status FROM parlays").fetchone()[0] == "won"


def test_a_voided_leg_drops_out_and_the_ticket_reprices():
    """What a book does. The remaining legs still ran and still won."""
    conn = _conn()
    t = _ticket(legs=[_leg("Alpha Guy"), _leg("Beta Guy"), _leg("Gamma Guy")])
    parlayledger.log_board(conn, _board(tickets=[t]))
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=3.0)
    _single(conn, "Gamma Guy", status="void")
    parlayledger.settle(conn)
    p = conn.execute("SELECT status, legs_void, pnl_units FROM parlays").fetchone()
    assert p["status"] == "won" and p["legs_void"] == 1
    # Repriced on two legs, so it pays less than three would have.
    assert 0 < p["pnl_units"] < 2.7


def test_a_ticket_with_fewer_than_two_legs_left_voids():
    """Below two legs there is no parlay to grade, and quietly turning one
    into a single would put a bet in the parlay record that was never one."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="void")
    parlayledger.settle(conn)
    p = conn.execute("SELECT status, pnl_units FROM parlays").fetchone()
    assert p["status"] == "void" and p["pnl_units"] == 0


def test_settling_twice_is_a_no_op():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    parlayledger.settle(conn)
    assert parlayledger.settle(conn)["settled"] == 0


# --- the bankroll must not move ---------------------------------------------
def test_settling_a_ticket_never_moves_the_bankroll():
    """§13: graded, never staked. A parlay bucket that moved the account
    would be staking them by the back door, and the probation architecture
    exists precisely to stop that."""
    conn = _conn()
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    before = ledger.bankroll(conn)
    parlayledger.settle(conn)
    assert ledger.bankroll(conn) == before


def test_a_ticket_stakes_zero_but_carries_a_notional():
    """Zero stake keeps the account still; the notional is what makes
    "positive flat-stake ROI" a measurable condition rather than 0/0."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    p = conn.execute("SELECT stake_units, notional_units FROM parlays").fetchone()
    assert p["stake_units"] == 0.0 and p["notional_units"] == 1.0


def test_parlays_never_enter_the_singles_record():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    parlayledger.settle(conn)
    perf = ledger.performance(conn)
    assert perf["settled"] == 2         # the two legs as singles, not the ticket


# --- loss codes -------------------------------------------------------------
def test_one_miss_out_of_three_is_leg_one_killed_it():
    conn = _conn()
    t = _ticket(legs=[_leg("Alpha Guy"), _leg("Beta Guy"), _leg("Gamma Guy")])
    parlayledger.log_board(conn, _board(tickets=[t]))
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=3.0)
    _single(conn, "Gamma Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    codes = json.loads(conn.execute(
        "SELECT loss_codes FROM parlays").fetchone()[0])
    assert "LEG_ONE_KILLED_IT" in codes


def test_one_ticket_splitting_is_not_stamped_as_a_correlation_error():
    """REVERSED 2026-08-23, on the first real record. This used to assert
    the opposite, and the assertion was wrong.

    The rule was "some legs won, some lost, and the ticket priced rho +".
    On a two-leg ticket that is the definition of "exactly one leg
    missed" — so the record came back LEG_ONE_KILLED_IT 10,
    CORRELATION_ERROR 10: the same ten tickets counted twice, one of them
    under a name that reads as a diagnosis of the model.

    And a split is the most likely single outcome even when a positive
    correlation is priced perfectly. rho +0.38 does not mean the legs
    land together; it means they land together slightly more often than
    chance. Stamping every split as the correlation being wrong is a
    conclusion the outcome cannot support — the same argument
    CLASH_MISSED already carries, applied to the neighbouring code.

    Whether the correlation is wrong is an aggregate question, and
    `calibration()` answers it: observed ticket wins against the modeled
    joint and against the independent joint."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    codes = json.loads(conn.execute(
        "SELECT loss_codes FROM parlays").fetchone()[0])
    assert "CORRELATION_ERROR" not in codes, (
        "one split ticket is being read as proof the correlation is wrong")
    assert "LEG_ONE_KILLED_IT" in codes, (
        "the thing that DID happen must still be recorded")


def test_both_legs_missing_is_not_a_correlation_error():
    """Two correlated legs both failing is the correlation WORKING. Stamping
    it as a correlation error would teach the opposite lesson."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="lost", actual=0.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    codes = json.loads(conn.execute(
        "SELECT loss_codes FROM parlays").fetchone()[0] or "[]")
    assert "CORRELATION_ERROR" not in codes


def test_singles_profiting_on_a_losing_ticket_is_tax_too_high():
    conn = _conn()
    t = _ticket(legs=[_leg("Alpha Guy"), _leg("Beta Guy"), _leg("Gamma Guy")])
    parlayledger.log_board(conn, _board(tickets=[t]))
    _single(conn, "Alpha Guy", status="won", actual=3.0, odds=200)
    _single(conn, "Beta Guy", status="won", actual=3.0, odds=200)
    _single(conn, "Gamma Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    row = conn.execute("SELECT loss_codes, singles_pnl_units "
                       "FROM parlays").fetchone()
    assert "TAX_TOO_HIGH" in json.loads(row["loss_codes"])
    assert row["singles_pnl_units"] > 0


def test_clash_missed_is_never_assigned_automatically():
    """Deciding a Type 2/3/4 clash slipped through is a judgement about the
    mechanism, not something an outcome can tell you — a ticket can lose
    with no clash and win with one. Auto-stamping it would fill the column
    with a conclusion nobody reached."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="lost", actual=0.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    assert "CLASH_MISSED" not in (conn.execute(
        "SELECT loss_codes FROM parlays").fetchone()[0] or "")


def test_a_won_ticket_carries_no_loss_code():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    parlayledger.settle(conn)
    assert conn.execute("SELECT loss_code FROM parlays").fetchone()[0] is None


# --- the report -------------------------------------------------------------
def test_an_empty_report_does_not_divide_by_zero():
    assert parlayledger.report(_conn())["graded"] == 0


def test_the_report_carries_the_three_promotion_conditions():
    """§13 gives three conditions. A module that fails promotion should say
    WHICH one it failed, not just that it did."""
    conn = _conn()
    p = parlayledger.report(conn)["promotion"]
    for k in ("tickets_required", "tickets_have", "roi_positive",
              "clv_non_negative", "z_clears", "z_required"):
        assert k in p
    assert p["tickets_required"] == 100 and p["z_required"] == 2.0


def test_probation_never_reports_clear_on_a_thin_sample():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    parlayledger.settle(conn)
    r = parlayledger.report(conn)
    assert r["probation"] is True
    assert r["promotion"]["tickets_have"] < r["promotion"]["tickets_required"]


def test_the_report_says_whether_singles_would_have_been_better():
    """§13 wants this on every card. Across the record it is the single most
    useful number: if flat singles beat the tickets, the structure is
    costing money and that should not need reconstructing."""
    conn = _conn()
    t = _ticket(legs=[_leg("Alpha Guy"), _leg("Beta Guy"), _leg("Gamma Guy")])
    parlayledger.log_board(conn, _board(tickets=[t]))
    _single(conn, "Alpha Guy", status="won", actual=3.0, odds=200)
    _single(conn, "Beta Guy", status="won", actual=3.0, odds=200)
    _single(conn, "Gamma Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    c = parlayledger.report(conn)["singles_comparison"]
    assert c["singles_better"] is True and c["singles_units"] > c["parlay_units"]


def test_leg_level_clv_is_aggregated_from_the_legs():
    """§11: leg-level CLV is the only honest parlay CLV. Summing line moves
    across different markets into one ticket number would add yards to
    strikeouts."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0, closing=2.5)
    _single(conn, "Beta Guy", status="won", actual=2.0, closing=2.5)
    parlayledger.settle(conn)
    r = parlayledger.report(conn)
    assert r["leg_clv_n"] == 2
    assert r["avg_leg_clv"] == 1.0            # both OVER 1.5, closed 2.5


def test_clv_is_side_aware_for_legs_too():
    conn = _conn()
    t = _ticket(legs=[_leg("Alpha Guy", side="UNDER"),
                      _leg("Beta Guy", side="UNDER")])
    parlayledger.log_board(conn, _board(tickets=[t]))
    _single(conn, "Alpha Guy", side="UNDER", status="won", actual=0.0, closing=0.5)
    _single(conn, "Beta Guy", side="UNDER", status="won", actual=0.0, closing=0.5)
    parlayledger.settle(conn)
    # An under wants the line to FALL; 1.5 → 0.5 is +1.0 our way.
    assert parlayledger.report(conn)["avg_leg_clv"] == 1.0


def test_the_z_score_needs_more_than_one_ticket():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    parlayledger.settle(conn)
    assert parlayledger.report(conn)["z"] is None


def test_the_record_splits_by_grade_so_the_bar_can_be_tested():
    """The whole point of journaling declines: it lets us ask later whether
    the tickets we called short actually lost."""
    conn = _conn()
    parlayledger.log_board(conn, _board(
        tickets=[_ticket(grade="short", qualified=False)]))
    _single(conn, "Alpha Guy", status="lost", actual=0.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    grades = {g["key"] for g in parlayledger.report(conn)["by_grade"]}
    assert grades == {"short"}


def test_recent_tickets_carry_their_legs():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    r = parlayledger.report(conn)["recent"][0]
    assert len(r["legs"]) == 2
    assert {l["status"] for l in r["legs"]} == {"won", "lost"}
    assert r["price_basis"] == "assumed_likely_case"


# --- wiring -----------------------------------------------------------------
def test_the_record_export_carries_the_parlay_bucket_separately():
    """§13: reported separately, never blended. Its own key."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    data = json.load(open(path))
    assert "parlays" in data
    assert data["parlays"]["open"] == 1
    # And nothing leaked into the singles numbers.
    assert data["overall"]["settled"] == 0


def test_journaling_reads_the_boards_that_actually_shipped():
    """Journal what the reader was shown, not a recomputation that can drift
    from it."""
    conn = _conn()
    root = tempfile.mkdtemp()
    d = os.path.join(root, "web", "data")
    os.makedirs(d)
    with open(os.path.join(d, "mlb_recommendations.json"), "w") as f:
        json.dump({"date": D, "parlays": _board()}, f)
    r = parlayledger.journal_built_boards(conn, root)
    assert r["journaled"] == 1


def test_a_board_with_no_parlay_zone_is_skipped_quietly():
    conn = _conn()
    root = tempfile.mkdtemp()
    d = os.path.join(root, "web", "data")
    os.makedirs(d)
    with open(os.path.join(d, "nba.json"), "w") as f:
        json.dump({"date": D}, f)
    assert parlayledger.journal_built_boards(conn, root)["journaled"] == 0


def test_the_refresh_journals_after_the_arbitration_not_before():
    """The arbitration decides which ONE ticket §10.2 would have allowed and
    can only run once every board exists. Journaling first would record
    every night's play as "not the play"."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert src.index("_arbitrate_parlays(quiet=quiet)") < \
        src.index("_journal_parlays(quiet=quiet)")


def test_the_settle_grades_parlays_after_the_singles():
    """Tickets grade off their legs' verdicts, so running first would leave
    every ticket waiting on legs that were about to settle."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("n = ledger.settle_from_history(lconn, hconn)")
    assert "parlayledger.settle(lconn)" in src[i:i + 900]


# --- the Record page --------------------------------------------------------
def _app_js():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def test_the_record_page_renders_the_parlay_bucket():
    assert "recParlaySection(d.parlays)" in _app_js()


def test_the_parlay_bucket_is_whole_journal_like_the_other_samplers():
    """The 100-ticket bar is cross-sport, so a per-sport slice of it would
    be a different (and much weaker) claim than the one §13 makes."""
    src = _app_js()
    i = src.index("recParlaySection(d.parlays)")
    assert 'scoped ? "" : recParlaySection' in src[i - 40:i + 40]


def test_the_legs_line_spans_the_whole_row():
    """.rl-row is a six-column GRID. A legs element added as a sixth child
    lands in the 72px P&L column and renders each leg as a vertical stack of
    one-word lines — which is exactly what it did before this rule."""
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = css.index(".pl-legs")
    assert "grid-column: 1 / -1" in css[i:i + 200]


def test_every_class_the_parlay_section_uses_is_styled():
    """A class named in the JS and missing from the CSS renders as unstyled
    text, which on this page reads as a layout bug rather than a missing
    rule."""
    src = _app_js()
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = src.index("function recParlaySection")
    block = src[i:src.index("function recLongshotSection")]
    import re
    used = set(re.findall(r'class="(pl-[a-z-]+)', block))
    assert len(used) >= 6, used          # the regex must actually be finding them
    for cls in used:
        assert f".{cls}" in css, cls


def test_a_real_screened_ticket_journals_every_field():
    """The fixtures above are hand-written, so they would keep passing if the
    screen renamed a key tomorrow and the journal quietly started storing
    NULLs. This runs the actual screen and asserts the §11 fields arrive
    populated — the only test here that can catch that drift.
    """
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import test_parlays as TP
    out = TP.run("mlb", TP.clearing_fixture(),
                 games=[TP.game(home="PHI", away="CHC", date="2026-08-02")])
    assert out["tickets"], "the clearing fixture must still clear"
    conn = _conn()
    assert parlayledger.log_board(conn, out, sport="mlb",
                                  date=out.get("date")) == 1
    r = conn.execute("SELECT * FROM parlays").fetchone()
    # Every §11 field the doc names, and none of them silently NULL.
    for col in ("parlay_type", "n_legs", "grade", "naive_product_dec",
                "assumed_dec", "correlation_tax", "modeled_joint",
                "implied_joint", "edge_points", "dominance_ratio",
                "singles_alternative_ev", "conditional_reasoning",
                "clash_screen_result"):
        assert r[col] is not None, col
    assert r["conditional_reasoning"].startswith("Ace x Ace rho ")
    assert r["quoted_dec"] is None          # still no real SGP quote
    assert conn.execute("SELECT COUNT(*) FROM parlay_legs").fetchone()[0] == 2


def test_the_slate_play_flag_survives_into_the_journal():
    conn = _conn()
    parlayledger.log_board(conn, _board(tickets=[_ticket(slate_play=True)]))
    assert conn.execute("SELECT was_play FROM parlays").fetchone()[0] == 1



# --- the repair pass ---------------------------------------------------------
def test_a_ticket_killed_by_a_leg_that_heals_heals_with_it():
    """The settle docstring promises the parlay record can never disagree
    with the singles journal its legs live in — and then only ever reads
    OPEN tickets, so the promise held exactly until a settled single moved.
    A leg graded lost off a partial NBA score killed the ticket; when
    resettle_mismatches healed the leg to won, the ticket stayed lost
    forever, wearing a LEG_ONE_KILLED_IT code about a loss that no longer
    exists."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    p = conn.execute("SELECT * FROM parlays").fetchone()
    assert p["status"] == "lost" and p["loss_code"] == "LEG_ONE_KILLED_IT"

    # The singles repair pass flips the leg: the "0 total bases" was a
    # partial line, the real final cleared it.
    conn.execute("UPDATE bets SET status='won', actual=2.0 "
                 "WHERE player='Beta Guy'")
    conn.commit()
    r = parlayledger.resettle(conn)
    assert len(r["fixed"]) == 1 and r["fixed"][0]["was"] == "lost"
    p = conn.execute("SELECT * FROM parlays").fetchone()
    assert p["status"] == "won" and p["pnl_units"] > 0
    assert p["loss_code"] is None
    leg = conn.execute("SELECT status FROM parlay_legs WHERE player="
                       "'Beta Guy'").fetchone()
    assert leg["status"] == "won"
    # Idempotent: nothing moves twice.
    r2 = parlayledger.resettle(conn)
    assert r2["fixed"] == [] and r2["reopened"] == 0


def test_a_reopened_leg_reopens_the_ticket():
    """repair-premature can reopen a single outright. A ticket whose
    verdict rests on a bet that no longer has one goes back to open and
    waits for the ordinary settle, exactly like the leg does."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    conn.execute("UPDATE bets SET status='open', actual=NULL "
                 "WHERE player='Beta Guy'")
    conn.commit()
    r = parlayledger.resettle(conn)
    assert r["reopened"] == 1
    p = conn.execute("SELECT * FROM parlays").fetchone()
    assert p["status"] == "open" and p["pnl_units"] is None
    assert p["loss_code"] is None and p["settled_ts"] is None
    # And once the leg really lands, the ordinary settle takes it again.
    conn.execute("UPDATE bets SET status='won', actual=2.0 "
                 "WHERE player='Beta Guy'")
    conn.commit()
    assert parlayledger.settle(conn)["settled"] == 1
    assert conn.execute("SELECT status FROM parlays").fetchone()[0] == "won"


def test_a_clean_table_is_a_no_op():
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="won", actual=2.0)
    parlayledger.settle(conn)
    r = parlayledger.resettle(conn)
    assert r["fixed"] == [] and r["reopened"] == 0


def test_the_autosettle_grades_tickets_not_just_singles():
    """Tickets journal nightly; settling them lived only in the manual
    --settle handler, so they sat 'waiting' until someone happened to run
    it. The every-refresh auto-settle is what actually keeps the journal
    current — the tickets belong to it. Pinned at the source so the wiring
    cannot quietly fall out."""
    import os as _os
    root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    src = open(_os.path.join(root, "engine", "maintenance.py"),
               encoding="utf-8").read()
    block = src[src.index("def settle_open("):]
    block = block[:block.index("\ndef ", 1)]
    assert "parlayledger" in block, "auto-settle no longer grades tickets"
    assert "parlayledger.settle(" in block.replace(" ", "")\
        .replace("pr=", "") or "pr = parlayledger.settle" in block
    assert "resettle" in block


# --- the report nobody could read -------------------------------------------

def test_the_parlay_record_has_a_way_to_be_read():
    """Ethan, 2026-08-23: "we suck at parlays and they are loosing us alot
    of money so we need a way to fix that and work on the model or
    something bc its not working".

    Every number needed to answer that was already computed by report()
    and printed nowhere — no CLI, and the Record page shows the bucket
    without the loss codes or the singles comparison. You cannot fix a
    model you cannot see."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "def _parlay_report_cli(" in src
    assert '"--parlay-report" in argv' in src, "defined but not reachable"


def test_the_report_says_the_three_things_that_decide_what_to_fix():
    """The singles comparison, the loss codes and the promotion state
    point at three DIFFERENT repairs, and a report that shows only ROI
    lets somebody conclude "the model is bad" when the record says the
    legs were fine and wrapping them was the mistake."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = src[src.index("def _parlay_report_cli("):]
    body = body[:body.index("\ndef ")]
    for key in ("singles_comparison", "loss_codes", "promotion"):
        assert key in body, "the report never reads %s" % key
    assert "CORRELATION_ERROR" in body, (
        "nothing distinguishes the one loss code that IS a model fault")
    assert "never staked" in body or "0.0 units" in body, (
        "the report does not say that the model stakes nothing, which is "
        "the fact that decides whether 'fix the model' is even the job")


def _seed(conn, rows):
    import json as _j
    parlayledger.ensure_schema(conn)
    for d, sp, ty, gr, st, pnl, sing, codes in rows:
        conn.execute(
            "INSERT INTO parlays (date, sport, parlay_type, grade, status, "
            "pnl_units, notional_units, singles_pnl_units, loss_codes, "
            "was_play) VALUES (?,?,?,?,?,?,?,?,?,1)",
            (d, sp, ty, gr, st, pnl, 1.0, sing, _j.dumps(codes)))
    conn.commit()


def test_the_report_prints_on_an_empty_ledger_and_on_a_full_one():
    """Both paths, because the empty one is the one it will meet first
    and a crash there reads as "the parlay system is broken"."""
    import contextlib
    import io
    from pathlib import Path

    import launch
    from engine import ledger as _lg

    for rows in ([], [("2026-08-10", "nfl", "A", "marginal", "lost",
                       -1.0, 0.4, ["TAX_TOO_HIGH"]),
                      ("2026-08-11", "mlb", "A", "strong", "won",
                       2.6, 0.9, [])]):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "l.db"
            conn = _lg.connect(path)
            _seed(conn, rows)
            conn.close()
            real = _lg.connect
            _lg.connect = lambda *a, **k: real(path)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    launch._parlay_report_cli()
            finally:
                _lg.connect = real
            out = buf.getvalue()
            assert "Parlay record" in out
            if rows:
                assert "2 graded" in out and "singles" in out.lower()
            else:
                assert "Nothing graded yet" in out


def test_an_empty_report_explains_the_blind_window_rather_than_reading_as_zero():
    """`journal_built_boards` read the public board, where `parlays` is
    stripped, so it recorded nothing from the day the paywall went on
    until 2026-08-23. An empty record that does not say so reads as
    "we never published any", which is the opposite of true."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = src[src.index("def _parlay_report_cli("):]
    body = body[:body.index("\ndef ")]
    i = body.index("Nothing graded yet")
    assert "paid key" in body[i:], (
        "an empty ledger is reported without saying why it might be empty")


# --- which half is broken ---------------------------------------------------

def _graded(conn, rows):
    """rows: (won, modeled, independent, leg_ps, leg_wins, qualified)."""
    import json as _j
    parlayledger.ensure_schema(conn)
    for i, (won, mod, ind, ps, lw, qual) in enumerate(rows):
        conn.execute(
            "INSERT INTO parlays (date, sport, parlay_type, grade, qualified,"
            " was_play, status, pnl_units, notional_units, "
            "singles_pnl_units, loss_codes, modeled_joint, "
            "independent_joint, n_legs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"2026-08-{i + 1:02d}", "mlb", "A",
             "marginal" if qual else "short", 1 if qual else 0, 0,
             "won" if won else "lost", 1.6 if won else -1.0, 1.0,
             0.2, _j.dumps([]), mod, ind, len(ps)))
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for k, pf in enumerate(ps, start=1):
            conn.execute(
                "INSERT INTO parlay_legs (parlay_id, leg_no, player, market,"
                " p_final, status) VALUES (?,?,?,?,?,?)",
                (pid, k, f"P{i}-{k}", "strikeouts", pf,
                 "won" if k <= lw else "lost"))
    conn.commit()


def test_calibration_separates_the_legs_from_the_joint():
    """The one diagnostic that says which half of a parlay model is
    wrong, and nothing computed it until 2026-08-23 — so a record could
    say "we lost" and never which half lost it.

    Legs short of their own p_final is a miscalibrated MARGINAL: the prop
    model is wrong and the singles board is making the same mistake.
    Legs on target while the TICKETS come in short is the correlation.
    """
    conn = _conn()
    # Legs hit exactly as priced (8 of 16 at p=0.5); tickets do not.
    _graded(conn, [(False, 0.30, 0.25, [0.5, 0.5], 1, 0) for _ in range(8)])
    c = parlayledger.calibration(conn)
    assert c["legs"]["n"] == 16 and c["legs"]["won"] == 8
    assert abs(c["legs"]["expected"] - 8.0) < 0.01
    assert abs(c["legs"]["z"]) < 1.0, "on-target legs must not look broken"
    assert c["tickets"]["won"] == 0
    assert c["tickets"]["z"] < -1.0, "0 of 8 against a 0.30 joint is a miss"


def test_calibration_catches_a_marginal_that_is_simply_wrong():
    conn = _conn()
    # Every leg priced at 0.7 and every one loses.
    _graded(conn, [(False, 0.49, 0.49, [0.7, 0.7], 0, 0) for _ in range(10)])
    c = parlayledger.calibration(conn)
    assert c["legs"]["expected"] > c["legs"]["won"]
    assert c["legs"]["z"] < -2, "legs far under their own number read as fine"


def test_a_positive_prior_can_be_shown_to_have_the_wrong_sign():
    """The third case, which the numbers can tell apart and a person
    cannot: coming in below even the as-if-unrelated joint means the legs
    we said move together do not."""
    conn = _conn()
    _graded(conn, [(False, 0.40, 0.30, [0.6, 0.6], 1, 0) for _ in range(12)])
    pos = parlayledger.calibration(conn)["positive_rho"]
    assert pos["n"] == 12
    assert pos["expected"] > pos["expected_independent"]
    assert pos["won"] < pos["expected_independent"]
    assert pos["z_independent"] is not None


def test_the_record_says_what_it_is_a_record_of():
    """log_board journals rank 1 from every slate whether the screen
    qualified it or not — the Zone ranks even when nothing clears. Read
    whole, the first real record was 18 rejects and one recommendation,
    and the total was being read as the model's performance."""
    conn = _conn()
    _graded(conn, [(False, 0.3, 0.25, [0.5, 0.5], 1, 0) for _ in range(6)]
                  + [(True, 0.3, 0.25, [0.5, 0.5], 2, 1)])
    q = parlayledger.report(conn)["by_qualified"]
    assert q["not_qualified"]["graded"] == 6
    assert q["qualified"]["graded"] == 1 and q["qualified"]["wins"] == 1


def test_the_singles_comparison_weighs_the_two_costs_rather_than_ranking():
    """`singles_better` is a bare sign test, and on the first real record
    it was true while singles LOST 15.32u against the tickets' 15.98u —
    so a report reading only the flag announced "the legs were fine and
    wrapping them was the mistake" about legs that had lost fifteen
    units. The structure cost 0.66u; the legs cost the rest."""
    conn = _conn()
    _graded(conn, [(False, 0.3, 0.25, [0.5, 0.5], 1, 0)])
    conn.execute("UPDATE parlays SET pnl_units=-15.98, singles_pnl_units=-15.32")
    conn.commit()
    sc = parlayledger.report(conn)["singles_comparison"]
    assert sc["singles_better"] is True, "the old flag still says what it said"
    assert abs(sc["structure_cost"] - 0.66) < 0.01, sc
    assert abs(sc["legs_cost"] - 15.32) < 0.01, sc


# --- the record read as a record of the right thing ---------------------------
def test_promotion_counts_only_the_tickets_the_screen_recommended():
    """§13's bar is about tickets this module would STAKE, and it was
    measured over every graded row — which includes rank 1 off every
    slate the screen refused. That let refusals count toward the hundred
    and set the ROI condition, so the module could be held back by the
    losses of bets it declined to make, or promoted on the strength of
    grading its own rejects."""
    conn = _conn()
    # Eighteen refusals, all losers; two recommendations, both winners.
    _graded(conn, [(False, 0.3, 0.25, [0.5, 0.5], 1, 0) for _ in range(18)]
                  + [(True, 0.3, 0.25, [0.5, 0.5], 2, 1) for _ in range(2)])
    r = parlayledger.report(conn)
    pr = r["promotion"]
    assert pr["tickets_have"] == 2, "refusals still count toward the hundred"
    assert pr["tickets_graded_all"] == 20, "the blended count is not reported"
    assert pr["roi_positive"] is True, (
        "the ROI condition is being set by tickets the screen declined")
    # And the blended numbers are still there — hiding them would be the
    # opposite mistake.
    assert r["graded"] == 20 and r["roi"] < 0


def test_the_recommended_bucket_is_summed_where_the_notional_is():
    """ROIs do not add. `recommended` is computed in SQL over both yes
    buckets rather than by averaging two percentages on the page, which
    is how a weighted average becomes a mean."""
    conn = _conn()
    _graded(conn, [(True, 0.3, 0.25, [0.5, 0.5], 2, 1) for _ in range(3)]
                  + [(False, 0.3, 0.25, [0.5, 0.5], 1, 0)])
    q = parlayledger.report(conn)["by_qualified"]
    rec, play, alsoq = q["recommended"], q["play"], q["qualified"]
    assert rec["graded"] == play["graded"] + alsoq["graded"] == 3
    assert rec["staked_units"] == 3.0, "no notional to re-divide by"
    assert abs(rec["net_units"] - (play["net_units"] + alsoq["net_units"])) < 1e-9
    assert rec["losses"] == rec["graded"] - rec["wins"]


def test_the_singles_verdict_is_asked_of_the_screens_own_tickets():
    """"Singles were better, the structure is costing money" is a verdict
    on the SCREEN. Answering it over rows the screen declined convicts it
    of somebody else's tickets."""
    conn = _conn()
    _graded(conn, [(False, 0.3, 0.25, [0.5, 0.5], 1, 0) for _ in range(4)]
                  + [(True, 0.3, 0.25, [0.5, 0.5], 2, 1)])
    r = parlayledger.report(conn)
    assert r["singles_comparison"]["n"] == 5
    assert r["singles_comparison_recommended"]["n"] == 1, (
        "the recommendation is being judged on the refusals' results")


def test_the_page_headline_reads_the_recommended_bucket_not_the_blend():
    """Ethan, 2026-08-23: "we suck at parlays and they are loosing us alot
    of money". The number he was reading was -84.1% over 19 tickets, and
    EIGHTEEN of the nineteen were tickets the screen refused."""
    src = _app_js()
    i = src.index("function recParlaySection")
    block = src[i:src.index("function recLongshotSection")]
    lead = block[block.index("rec-kpis"):block.index("pl-conds")]
    assert "pz.roi" not in lead, "the blended ROI is back in the KPI row"
    assert "rec.roi" in lead and "rec.net_units" in lead
    # and the blend is still reported, below, rather than hidden
    assert "Everything graded, blended" in block


def test_no_rate_is_printed_on_a_sample_that_cannot_carry_one():
    """THE FIRST CUT OF THE FIX SHIPPED A WORSE LIE. Splitting the record
    made the headline "+160.0% ROI" in green off ONE winning ticket. A
    rate quoted on a sample that cannot carry one is the same fault as
    the blend, pointing the other way."""
    src = _app_js()
    assert "const PARLAY_RATE_FLOOR = 10;" in src, "the floor was removed"
    i = src.index("function recParlaySection")
    block = src[i:src.index("function recLongshotSection")]
    assert "readable" in block, "the floor is defined and never consulted"
    # the split rows honour it too — a row reading +160% beside a note
    # saying one ticket is not a record is the page arguing with itself
    split = src[src.index("function parlaySplitHTML"):
                src.index("function recLongshotSection")]
    assert "b.graded >= PARLAY_RATE_FLOOR" in split
    # …and the verdict line does not conclude from it either
    assert "a difference, not a finding" in block


def test_the_refusals_are_labelled_as_the_gates_working():
    """A heavy loss on the refused bucket is the screen being RIGHT.
    Printing it without that sentence is how the split becomes a second
    way to read the same wrong conclusion."""
    src = _app_js()
    split = src[src.index("function parlaySplitHTML"):
                src.index("function recLongshotSection")]
    assert "the gates working" in split
    assert "never recommended" in split


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
