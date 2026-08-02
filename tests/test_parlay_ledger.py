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


def test_legs_disagreeing_on_a_positive_rho_is_a_correlation_error():
    """We priced these as moving together and they moved apart. That is the
    one input the whole structure rests on being wrong."""
    conn = _conn()
    parlayledger.log_board(conn, _board())
    _single(conn, "Alpha Guy", status="won", actual=3.0)
    _single(conn, "Beta Guy", status="lost", actual=0.0)
    parlayledger.settle(conn)
    codes = json.loads(conn.execute(
        "SELECT loss_codes FROM parlays").fetchone()[0])
    assert "CORRELATION_ERROR" in codes


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
