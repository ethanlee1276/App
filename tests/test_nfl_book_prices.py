"""The NFL walk-forward could not read a closing price it had been sold.

`build_slate` invents a proxy line — the player's recent-form baseline at
a synthetic -110 — and its docstring has said "swap in an odds feed to
price against real books" since it was written. Nobody ever could:
`backtest_from_stats` had no parameter to pass one through, and
`lab.nfl_props` called it with none.

So on 2026-08-27, after 11,772 `receptions` closes were purchased and
stored, the thing that needed them still priced every prop against its
own trailing average. The harvest guard added the same week checks that
the PARSER can read a market back; it cannot see that the BACKTEST
cannot. This is that hole, one layer up.

What these pin: a harvested close reaches the prop, the basis follows
the book that priced it, a partial harvest segments rather than blends,
and none of the ways a quote can be unusable turns into a fake edge.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest as B
from engine.models import Prop, SportsbookLine


class _Game:
    def __init__(self, home, away, date):
        self.home, self.away, self.date = home, away, date


class _Slate:
    def __init__(self, games, props):
        self.games, self.props = games, props


def _prop(player="Ja'Marr Chase", team="CIN", market="receptions",
          line=5.5):
    return Prop(player=player, team=team, opponent="BAL", position="WR",
                market=market, logs=[], career_avg=5.0, vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=line,
                                      over_odds=-110, under_odds=-110)])


def _slate(props=None, date="2025-09-07"):
    return _Slate([_Game("CIN", "BAL", date)], list(props or [_prop()]))


def _quote(line=6.5, over=-135, under=105, book="DraftKings"):
    return {"line": line, "over_odds": over, "under_odds": under,
            "book": book, "taken_at": "2025-09-07T17:00:00Z"}


# --- the swap ----------------------------------------------------------------
def test_a_harvested_close_replaces_the_proxy_line():
    slate = _slate()
    n = B.apply_real_lines(
        slate, {(B._norm("Ja'Marr Chase"), "receptions", "2025-09-07"):
                _quote()})
    assert n == 1
    got = slate.props[0].lines[0]
    assert got.book == "DraftKings"
    assert got.line == 6.5 and got.over_odds == -135 and got.under_odds == 105


def test_the_market_is_part_of_the_key():
    """A player has a receptions close and a receiving-yards close on the
    same day and they are different bets. `closing_odds_by_date` drops the
    market from its key, so the caller has to put it back."""
    slate = _slate([_prop(market="rec_yds", line=60.5)])
    n = B.apply_real_lines(
        slate, {(B._norm("Ja'Marr Chase"), "receptions", "2025-09-07"):
                _quote()})
    assert n == 0
    assert slate.props[0].lines[0].book == "proxy"


def test_the_date_comes_from_the_schedule_not_the_week():
    """A week holds a Thursday, a Sunday and a Monday game. They are three
    different closes, and only the days actually harvested may join."""
    slate = _Slate([_Game("CIN", "BAL", "2025-09-08")],   # Monday night
                   [_prop()])
    n = B.apply_real_lines(
        slate, {(B._norm("Ja'Marr Chase"), "receptions", "2025-09-07"):
                _quote()})
    assert n == 0, "a Sunday close must not price a Monday game"


def test_a_prop_with_no_close_keeps_its_proxy():
    slate = _slate([_prop(), _prop(player="Tee Higgins")])
    n = B.apply_real_lines(
        slate, {(B._norm("Tee Higgins"), "receptions", "2025-09-07"):
                _quote(line=4.5)})
    assert n == 1
    kept = [p for p in slate.props if p.player == "Ja'Marr Chase"][0]
    assert kept.lines[0].book == "proxy"


def test_no_harvest_at_all_changes_nothing():
    slate = _slate()
    assert B.apply_real_lines(slate, {}) == 0
    assert B.apply_real_lines(slate, None) == 0
    assert slate.props[0].lines[0].book == "proxy"


def test_a_game_with_no_date_is_skipped_rather_than_crashing():
    slate = _Slate([_Game("CIN", "BAL", "")], [_prop()])
    assert B.apply_real_lines(
        slate, {(B._norm("Ja'Marr Chase"), "receptions", ""): _quote()}) == 0


# --- the ways a quote can be unusable ---------------------------------------
def test_an_over_only_quote_is_refused_rather_than_half_invented():
    """0 is the parser's word for 'not quoted'. Filling the missing side at
    -110 is what put phantom edges on markets nobody could bet."""
    slate = _slate()
    assert B.apply_real_lines(
        slate, {(B._norm("Ja'Marr Chase"), "receptions", "2025-09-07"):
                _quote(over=0, under=-110)}) == 0
    assert slate.props[0].lines[0].book == "proxy"


def test_an_arithmetically_impossible_pair_drops_the_under():
    """Two sides implying less than 100% between them is corrupt data, not
    a free arbitrage. The over is kept and the under discarded, the same
    call `engine.mlb.backtest` makes."""
    from engine.odds import pair_is_sane
    assert not pair_is_sane(200, 200), "premise: this pair must be insane"
    slate = _slate()
    assert B.apply_real_lines(
        slate, {(B._norm("Ja'Marr Chase"), "receptions", "2025-09-07"):
                _quote(over=200, under=200)}) == 1
    got = slate.props[0].lines[0]
    assert got.over_odds == 200 and got.under_odds == 0


def test_junk_in_the_line_is_skipped_rather_than_raising():
    slate = _slate()
    for bad in ({"over_odds": -110}, {"line": None, "over_odds": -110},
                {"line": "n/a", "over_odds": -110}):
        assert B.apply_real_lines(
            slate, {(B._norm("Ja'Marr Chase"), "receptions",
                     "2025-09-07"): bad}) == 0


# --- the basis ---------------------------------------------------------------
def test_the_basis_is_read_off_the_book_that_priced_it():
    assert B._basis_of("proxy") == "naive"
    assert B._basis_of("") == "naive"
    assert B._basis_of(None) == "naive"
    assert B._basis_of("DraftKings") == "book"


def test_settling_tags_each_bet_with_the_basis_it_was_priced_on():
    recs = [
        {"player": "A", "market": "receptions", "line": 5.5, "odds": -135,
         "hit_prob": 0.6, "projection": 6.4, "recommended": True,
         "book": "DraftKings", "grade": "A"},
        {"player": "B", "market": "receptions", "line": 4.5, "odds": -110,
         "hit_prob": 0.58, "projection": 5.1, "recommended": True,
         "book": "proxy", "grade": "B+"},
    ]
    actuals = {(B._norm("A"), "receptions"): 7.0,
               (B._norm("B"), "receptions"): 3.0}
    got = {s.player: s.basis for s in B.settle_recommendations(recs, actuals)}
    assert got == {"A": "book", "B": "naive"}


def test_a_partial_harvest_segments_rather_than_blends():
    """Twelve of eighteen Sundays bought means a smaller honest
    book-priced sample BESIDE the baseline, not one number that is
    neither."""
    recs = [
        {"player": "A", "market": "receptions", "line": 5.5, "odds": 100,
         "hit_prob": 0.6, "projection": 6.4, "recommended": True,
         "book": "DraftKings", "grade": "A"},
        {"player": "B", "market": "receptions", "line": 4.5, "odds": 100,
         "hit_prob": 0.58, "projection": 5.1, "recommended": True,
         "book": "proxy", "grade": "A"},
    ]
    actuals = {(B._norm("A"), "receptions"): 7.0,      # book bet wins
               (B._norm("B"), "receptions"): 3.0}      # proxy bet loses
    rep = B.evaluate(B.settle_recommendations(recs, actuals))
    assert rep.segments["book"]["n_bets"] == 1
    assert rep.segments["book"]["wins"] == 1
    assert rep.segments["naive"]["n_bets"] == 1
    assert rep.segments["naive"]["wins"] == 0


def test_the_grade_ladder_survives_into_the_lab_json_per_basis():
    """The whole question — does the top band earn its billing against a
    REAL book — is a per-grade record inside the "book" segment, and it
    was the one number `report_to_dict` dropped."""
    from engine.lab import report_to_dict
    recs = [
        {"player": "A", "market": "receptions", "line": 5.5, "odds": 100,
         "hit_prob": 0.6, "projection": 6.4, "recommended": True,
         "book": "DraftKings", "grade": "A"},
        {"player": "B", "market": "receptions", "line": 4.5, "odds": 100,
         "hit_prob": 0.55, "projection": 5.1, "recommended": True,
         "book": "DraftKings", "grade": "B+"},
    ]
    actuals = {(B._norm("A"), "receptions"): 3.0,      # the A band loses
               (B._norm("B"), "receptions"): 7.0}      # the B+ band wins
    d = report_to_dict(B.evaluate(B.settle_recommendations(recs, actuals)))
    grades = d["segments"]["book"]["grades"]
    assert grades["A"]["wins"] == 0 and grades["A"]["n_bets"] == 1
    assert grades["B+"]["wins"] == 1 and grades["B+"]["n_bets"] == 1


def test_a_slate_missing_its_props_is_counted_as_zero_not_a_crash():
    """The prop count is bookkeeping. A slate that really lost its props
    reports n=0 and says so loudly; a crash in the counter would only
    obscure that — and it broke an existing offline stub the first time
    the counter was added."""
    assert B.apply_real_lines(object(), {"k": {}}) == 0
    assert B.apply_real_lines(_Slate([], []), {"k": {}}) == 0


# --- the wiring --------------------------------------------------------------
def test_the_lab_actually_passes_the_closes_it_loads():
    """`nfl_props` grew a `conn`; `build` has to hand it one, or the whole
    chain is inert on the only command anybody runs."""
    import inspect
    from engine import lab
    assert "real_lines" in inspect.signature(
        B.backtest_from_stats).parameters
    assert "conn" in inspect.signature(lab.nfl_props).parameters
    src = inspect.getsource(lab.build)
    assert "nfl_props(log=log, conn=hconn)" in src


def test_the_close_loader_keeps_the_market_in_the_key():
    from engine import db
    from engine.lab import nfl_real_lines
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [
        {"sport": "nfl", "taken_at": "2025-09-07T17:00:00Z", "event_id": "e",
         "home": "CIN", "away": "BAL", "player": "ja marr chase",
         "market": m, "book": "DK", "line": ln,
         "over_odds": -115, "under_odds": -105}
        for m, ln in (("receptions", 5.5), ("rec_yds", 70.5))])
    got = nfl_real_lines(conn)
    assert set(got) == {("ja marr chase", "receptions", "2025-09-07"),
                        ("ja marr chase", "rec_yds", "2025-09-07")}
    assert got[("ja marr chase", "receptions", "2025-09-07")]["line"] == 5.5


def test_an_empty_history_yields_no_closes_and_no_error():
    from engine import db
    from engine.lab import nfl_real_lines
    assert nfl_real_lines(db.connect(":memory:")) == {}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
