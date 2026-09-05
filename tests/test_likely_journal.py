"""The likelihood board gets a record, because it never had one.

Ethan, 2026-08-30: "which bets do we trust more as now its confusing.
also which ones are we recording?"

The answer was worse than confusing. `log_recommendations` walks
`result["recommendations"]` and `log_longshots` walks `long_shots`;
NOTHING anywhere read `most_likely`. On a sample slate, seven of eight
likelihood rows left no trace — no ledger row, no Record entry, no CLV.

So we were recording the board built on the signal that measures as
NOISE and recording nothing from the board built on the two that measure
well:

    who scores a touchdown     AUC 0.721
    who clears their line      0.76 rush · 0.77 rec'ns · 0.73 rec · 0.69 pass
    where the market is wrong  AUC 0.468

`category='likely'`, a flat 0.1u and ZERO dollars — the same shape as the
long-shot bucket, and for the same reason: this is a measurement, not a
position. Nothing here touches the headline record. In a few weeks the
ledger rather than an AUC says which board to trust.

Run directly: `python3 tests/test_likely_journal.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger                               # noqa: E402
from engine.ledger import _grade_side_aware             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(player="A Back", market="rush_yds", side="OVER", line=45.5,
         odds=-110, prob=0.55, implied=0.50, book="DraftKings"):
    return {"player": player, "market": market, "side": side, "line": line,
            "odds": odds, "model_prob": prob, "implied_prob": implied,
            "book": book, "projection": 60.0}


def _book(rows, sport="nfl", date="2026-W01", **kw):
    conn = ledger.connect(":memory:")
    n = ledger.log_most_likely(conn, {"sport": sport, "date": date,
                                      "most_likely": rows}, **kw)
    return conn, n


# --- it is a measurement bucket, not a position ---------------------------
def test_rows_land_in_their_own_category_with_no_dollars_on_them():
    conn, n = _book([_row()])
    assert n == 1
    got = dict(conn.execute("SELECT * FROM bets").fetchone())
    assert got["category"] == "likely"
    assert got["stake_dollars"] == 0.0
    assert got["stake_units"] > 0, "a zero stake cannot answer what it returned"
    assert got["status"] == "open"


def test_the_headline_record_is_untouched():
    """`main` is the record the Record page scores. A new bucket that
    leaked into it would be a product change wearing a measurement's
    clothes."""
    conn, _n = _book([_row()])
    cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM bets")]
    assert cats == ["likely"], cats


def test_it_journals_the_probability_the_page_showed():
    """`model_prob`, not the raw model number and not the
    recommendation's `hit_prob`. The question this bucket answers is
    whether the figure a reader ACTED ON was true."""
    conn, _n = _book([_row(prob=0.62)])
    assert dict(conn.execute("SELECT * FROM bets").fetchone())["hit_prob"] \
        == 0.62


def test_the_edge_column_is_evidence_not_a_claim():
    """This board is ranked on probability and never on price. The gap
    against the book rides along so it can be analysed later; it is not
    what is being scored."""
    conn, _n = _book([_row(prob=0.55, implied=0.50)])
    got = dict(conn.execute("SELECT * FROM bets").fetchone())
    assert abs(got["edge"] - 0.05) < 1e-9
    conn2, _ = _book([dict(_row(), implied_prob=None)])
    assert dict(conn2.execute("SELECT * FROM bets").fetchone())["edge"] is None


# --- every row it writes has to be able to settle -------------------------
def test_a_touchdown_row_is_normalised_so_it_can_grade():
    """THE BUG THE FIRST CUT SHIPPED WITH. `_grade_side_aware` computes
    `actual > b["line"]` and compares the side against "OVER", so a
    touchdown row journaled as the BOARD renders it — side "yes", line
    None — raises a TypeError on the settle pass and, surviving that,
    would invert its own result. `_journal_longshot_rows` writes OVER/0.5
    for exactly this reason."""
    conn, _n = _book([_row(market="anytime_td", side="yes", line=None,
                           odds=250, prob=0.30)])
    got = dict(conn.execute("SELECT * FROM bets").fetchone())
    assert got["side"] == "OVER" and got["line"] == 0.5
    assert _grade_side_aware(got, 1.0)[0] == "won"
    assert _grade_side_aware(got, 0.0)[0] == "lost"


def test_a_row_with_no_line_at_all_is_refused_rather_than_stranded():
    """A row that can never settle sits open forever and turns every
    audit into a wall of names — the failure `log_longshots` retired the
    watchlist over."""
    _conn, n = _book([_row(market="rush_yds", line=None)])
    assert n == 0


def test_every_market_this_board_carries_grades_both_ways():
    rows = [_row(market="anytime_td", side="yes", line=None, odds=250),
            _row(market="rush_yds", line=45.5),
            _row(market="rec_yds", line=54.5),
            _row(market="receptions", line=4.5),
            _row(market="pass_yds", side="UNDER", line=259.5)]
    for i, r in enumerate(rows):
        r["player"] = f"Player {i}"
    conn, n = _book(rows)
    assert n == 5
    for b in conn.execute("SELECT * FROM bets"):
        over = (b["side"] or "").upper() == "OVER"
        assert _grade_side_aware(b, b["line"] + 1.0)[0] == \
            ("won" if over else "lost"), b["market"]
        assert _grade_side_aware(b, b["line"] - 1.0)[0] == \
            ("lost" if over else "won"), b["market"]
        assert _grade_side_aware(b, b["line"])[0] == "push", b["market"]


def test_the_settle_pass_needs_no_new_code_to_reach_them():
    """`settle_from_history` selects open bets with NO category filter,
    and every market here is a `player_game_logs` market — so these grade
    on the same pass as everything else."""
    import inspect
    src = inspect.getsource(ledger.settle_from_history)
    assert "SELECT * FROM bets WHERE status='open'" in src
    # The only categories the sweep treats specially are the two graded
    # by someone else entirely — an exchange and a fight card. "likely"
    # is not one of them, so it takes the ordinary player-stat path.
    assert ledger.GRADED_ELSEWHERE == ("predmarket", "ufc")
    assert "likely" not in ledger.GRADED_ELSEWHERE


def test_a_player_who_never_took_the_field_voids_rather_than_loses():
    """The same rule the vig work landed on this morning: a prop on a man
    who did not play is VOID, not a loss. The no-show sweep already does
    that for every category outside GRADED_ELSEWHERE, so this bucket
    inherits it — worth pinning, because grading scratches as losses is
    exactly what made the longshot band read as a 35% market toll."""
    import inspect
    src = inspect.getsource(ledger.settle_from_history)
    assert 'if b["category"] in NEVER_NOSHOW:' in src
    assert "NEVER_NOSHOW = GRADED_ELSEWHERE" in src


# --- volume discipline ----------------------------------------------------
def test_only_the_top_of_the_board_is_journaled():
    """TEN, NOT FORTY, and the number is a lesson rather than a taste.
    The old watchlist wrote two hundred rows a night into a bucket nobody
    read. `tdbacktest.board_report` grades this board at depths 5, 10, 20
    and 40, and the signal is at the top: the first five rows land 6.8
    points above what they claim, the first forty are inside the noise."""
    rows = [_row(player=f"Player {i}") for i in range(40)]
    _conn, n = _book(rows)
    assert n == ledger.LIKELY_JOURNAL_DEPTH == 10, n


def test_the_depth_is_the_top_of_the_list_not_a_sample():
    rows = [_row(player=f"Player {i}", prob=0.9 - i * 0.01) for i in range(20)]
    conn, _n = _book(rows)
    kept = {r[0] for r in conn.execute("SELECT player FROM bets")}
    assert kept == {f"Player {i}" for i in range(10)}, sorted(kept)


# --- the same refusals the other journals make ----------------------------
def test_a_proxy_price_is_refused():
    _conn, n = _book([_row(book="proxy")])
    assert n == 0


def test_an_impossible_american_price_is_refused():
    for odds in (0, 50, -95):
        _conn, n = _book([_row(odds=odds)])
        assert n == 0, odds


def test_running_twice_does_not_double_count():
    rows = [_row()]
    conn, first = _book(rows)
    again = ledger.log_most_likely(
        conn, {"sport": "nfl", "date": "2026-W01", "most_likely": rows})
    assert (first, again) == (1, 0)


def test_the_nfl_dates_on_its_week_and_other_sports_on_the_game():
    """Same fork, and the same reason, as the long-shot journal: the NFL
    settles on its WEEK label while everything else settles on the game's
    own date, and a bet dated one day off its result cannot settle."""
    nfl, _ = _book([dict(_row(), game_date="2026-09-13")], sport="nfl",
                   date="2026-W02")
    assert dict(nfl.execute("SELECT * FROM bets").fetchone())["date"] == \
        "2026-W02"
    cfb, _ = _book([dict(_row(), game_date="2026-09-12")], sport="cfb",
                   date="2026-09-13")
    assert dict(cfb.execute("SELECT * FROM bets").fetchone())["date"] == \
        "2026-09-12"


# --- it is actually called ------------------------------------------------
def test_both_football_builds_journal_the_board():
    """Defined and never called is the failure two other tests in this
    suite already guard against by name."""
    for path, sport in (("nfl_build.py", "nfl"), ("cfb_build.py", "cfb")):
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            src = fh.read()
        assert "ledger.log_most_likely(" in src, path
        assert '"most_likely"' in src, path


def test_the_real_board_survives_the_round_trip():
    """End to end on the sample slate rather than on fixtures — the
    shape `pipeline` actually emits, not the shape this file imagines."""
    from engine.pipeline import run_slate
    board = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    rows = board.get("most_likely") or []
    assert rows, "the sample slate stopped producing a likelihood board"
    conn, n = _book(rows)
    # NOT AN EQUALITY, and the difference is the point. The journal keeps
    # its own refusals — a proxy book, an impossible American price — so
    # the count is a ceiling rather than a promise. Asserting equality
    # passed here and failed inside `run_tests`, whose sandbox points
    # QB_MODELS_DIR at an empty directory: the board comes out ordered
    # differently without a fitted store, and Amon-Ra St. Brown's
    # anytime-TD row rises into the top ten carrying `over_odds: -97`
    # from the fixture. There is no such American price — the dead zone
    # runs -99 to +99 and a book quoting better than even money writes
    # +103 — so the journal is right to drop it, and a test that
    # demanded otherwise was asserting about this box's model store.
    assert 0 < n <= min(len(rows), ledger.LIKELY_JOURNAL_DEPTH), n
    for b in conn.execute("SELECT * FROM bets"):
        assert b["line"] is not None, b["player"]
        assert (b["side"] or "").upper() in ("OVER", "UNDER"), b["side"]
        _grade_side_aware(b, float(b["line"]) + 1.0)   # must not raise


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
