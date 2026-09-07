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


def test_the_side_split_survives_into_the_lab_json_per_basis():
    """A blended segment number can hide a board winning on one side and
    losing on the other. Measured on 2025 NFL props, "256 bets, 57.1%,
    +8.7%" is 129 overs at 44.2% (-8.5%) and 127 unders at 66.1%
    (+26.1%) — one number that describes neither half."""
    from engine.lab import report_to_dict
    recs = [
        {"player": "O", "market": "rec_yds", "line": 50.5, "odds": 100,
         "hit_prob": 0.6, "projection": 60.0, "recommended": True,
         "book": "DraftKings", "grade": "A", "side": "OVER"},
        {"player": "U", "market": "rec_yds", "line": 50.5, "odds": 100,
         "hit_prob": 0.6, "projection": 40.0, "recommended": True,
         "book": "DraftKings", "grade": "A", "side": "UNDER"},
    ]
    actuals = {(B._norm("O"), "rec_yds"): 20.0,      # the over lost
               (B._norm("U"), "rec_yds"): 20.0}      # the under won
    d = report_to_dict(B.evaluate(B.settle_recommendations(recs, actuals)))
    sides = d["segments"]["book"]["sides"]
    assert sides["OVER"]["wins"] == 0 and sides["OVER"]["n_bets"] == 1
    assert sides["UNDER"]["wins"] == 1 and sides["UNDER"]["n_bets"] == 1


def test_the_printer_shows_both_sides_when_there_are_two():
    import io, contextlib
    from engine import lab
    m = {"market": "all", "label": "All", "n": 10, "basis": "naive",
         "n_bets": 2, "win_rate": 0.5, "roi": 0.0, "segments": {"naive": {
             "n_bets": 2, "win_rate": 0.5, "roi": 0.0, "grades": {},
             "sides": {"OVER": {"n_bets": 1, "wins": 0, "win_rate": 0.0,
                                "roi": -1.0},
                       "UNDER": {"n_bets": 1, "wins": 1, "win_rate": 1.0,
                                 "roi": 1.0}}}}}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lab._print_market(m)
    out = buf.getvalue()
    assert "OVER" in out and "UNDER" in out


def test_a_one_sided_board_does_not_get_a_pointless_split():
    """Anytime touchdown is OVER-only. Printing "OVER 40, UNDER 0" on it
    is furniture."""
    import io, contextlib
    from engine import lab
    m = {"market": "anytime_td", "label": "Anytime touchdown", "n": 40,
         "basis": "book", "n_bets": 40, "win_rate": 0.175, "roi": -0.489,
         "segments": {"book": {"n_bets": 40, "win_rate": 0.175,
                               "roi": -0.489, "grades": {},
                               "sides": {"OVER": {"n_bets": 40, "wins": 7,
                                                  "win_rate": 0.175,
                                                  "roi": -0.489}}}}}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lab._print_market(m)
    assert "OVER" not in buf.getvalue()


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


# --- the touchdown board, which had never been graded for money -------------
def _td_prop(player="Jaylen Waddle", team="CIN"):
    """A scorer prop as `build_slate` makes one: NO line, on purpose."""
    return Prop(player=player, team=team, opponent="BAL", position="WR",
                market="anytime_td", logs=[], career_avg=0.0,
                vs_opponent_avg=None, lines=[])


def test_a_scorer_prop_starts_with_no_line_and_gains_the_harvested_one():
    """`build_slate` refuses to invent a -110 for a scorer market, so the
    touchdown board is the ONE market that cannot be replayed at all
    without a purchased price. Every other market has a baseline to fall
    back on; this one has silence."""
    slate = _slate([_td_prop()])
    assert slate.props[0].lines == []
    n = B.apply_real_lines(
        slate, {(B._norm("Jaylen Waddle"), "anytime_td", "2025-09-07"):
                {"line": 0.5, "over_odds": 550, "under_odds": -800,
                 "book": "FanDuel"}})
    assert n == 1
    got = slate.props[0].lines[0]
    assert got.line == 0.5 and got.over_odds == 550 and got.under_odds == -800


def test_a_yes_only_scorer_quote_still_prices_the_yes():
    """Books often quote the Yes alone. Unlike a two-sided market, that is
    normal here and must not cost the pick."""
    slate = _slate([_td_prop()])
    assert B.apply_real_lines(
        slate, {(B._norm("Jaylen Waddle"), "anytime_td", "2025-09-07"):
                {"line": 0.5, "over_odds": 700, "under_odds": None,
                 "book": "FanDuel"}}) == 1
    got = slate.props[0].lines[0]
    assert got.over_odds == 700 and got.under_odds == 0


def test_a_longshot_pick_becomes_something_the_settler_understands():
    recs = B.longshot_recs([{"player": "Jaylen Waddle",
                             "market": "anytime_td", "odds": 550,
                             "model_prob": 0.18, "grade": "A",
                             "book": "FanDuel", "stake_units": 0.5}])
    assert len(recs) == 1
    r = recs[0]
    assert r["line"] == 0.5 and r["side"] == "OVER" and r["recommended"]
    assert r["hit_prob"] == 0.18 and r["projection"] == 0.18
    assert r["book"] == "FanDuel" and r["stake_units"] == 0.5


def test_a_pick_with_no_price_or_no_probability_is_dropped():
    assert B.longshot_recs([{"player": "X", "market": "anytime_td",
                             "odds": None, "model_prob": 0.2}]) == []
    assert B.longshot_recs([{"player": "X", "market": "anytime_td",
                             "odds": 550, "model_prob": None}]) == []
    assert B.longshot_recs(None) == []
    assert B.longshot_recs([]) == []


def test_a_scored_touchdown_wins_the_yes_and_a_blank_loses_it():
    recs = B.longshot_recs([
        {"player": "Scored", "market": "anytime_td", "odds": 550,
         "model_prob": 0.18, "grade": "A", "book": "FanDuel"},
        {"player": "Blanked", "market": "anytime_td", "odds": 400,
         "model_prob": 0.22, "grade": "A", "book": "FanDuel"},
    ])
    actuals = {(B._norm("Scored"), "anytime_td"): 1.0,
               (B._norm("Blanked"), "anytime_td"): 0.0}
    got = {s.player: s.outcome for s in B.settle_recommendations(recs, actuals)}
    assert got == {"Scored": 1, "Blanked": 0}


def test_the_touchdown_actual_is_binary_and_not_a_count():
    """The market is 'scored at least one' and the model's number is a
    PROBABILITY. Settling a probability against a count of 2 would make
    MAE, Brier and every calibration bin describe nothing."""
    import inspect
    src = inspect.getsource(B.backtest_from_stats)
    assert 'actuals[(_norm(name), ANYTIME_TD)] = float(' in src
    assert '"rushing_tds"' in src and '"receiving_tds"' in src
    assert "> 0)" in src


def test_the_scorer_board_is_reported_apart_from_the_yardage_markets():
    """A +450 scorer market and a -110 yardage market do not share a
    meaningful win rate. One blended row would describe neither."""
    assert "longshots" in {f.name for f in
                           __import__("dataclasses").fields(B.BacktestReport)}
    import inspect
    from engine import lab
    src = inspect.getsource(lab.nfl_props)
    assert "rep.longshots" in src
    assert '"anytime_td", "Anytime touchdown"' in src


def test_the_scorer_market_is_one_the_lab_asks_the_database_for():
    from engine.lab import NFL_MARKETS
    assert "anytime_td" in NFL_MARKETS


def test_a_harvested_scorer_price_survives_the_whole_load():
    from engine import db
    from engine.lab import nfl_real_lines
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [
        {"sport": "nfl", "taken_at": "2025-09-07T17:00:00Z", "event_id": "e",
         "home": "CIN", "away": "BAL", "player": "jaylen waddle",
         "market": "anytime_td", "book": "FanDuel", "line": 0.5,
         "over_odds": 550, "under_odds": -800}])
    quote = nfl_real_lines(conn)[("jaylen waddle", "anytime_td", "2025-09-07")]
    slate = _slate([_td_prop()])
    assert B.apply_real_lines(
        slate, {(B._norm("Jaylen Waddle"), "anytime_td", "2025-09-07"):
                quote}) == 1
    assert slate.props[0].lines[0].over_odds == 550


def test_the_walk_forward_settles_the_touchdown_board_end_to_end():
    """The whole chain in one pass: a scorer pick reaches the settler, its
    actual comes out of the two touchdown columns, and it lands in its own
    report rather than in the yardage numbers."""
    import engine.sources.nflverse as nv
    import engine.pipeline as pl

    stats = [
        {"week": "5", "player_display_name": "RB One", "rushing_yards": "80",
         "passing_yards": "0", "receiving_yards": "0", "receptions": "0",
         "rushing_tds": "1", "receiving_tds": "0"},
        {"week": "5", "player_display_name": "WR Two", "rushing_yards": "0",
         "passing_yards": "0", "receiving_yards": "40", "receptions": "3",
         "rushing_tds": "0", "receiving_tds": "0"},
    ]
    saved = (nv.load_weekly_stats, nv.build_slate, pl.run_slate)
    nv.load_weekly_stats = lambda season: stats
    nv.build_slate = lambda season, w, upto_week=None: _slate()
    pl.run_slate = lambda slate, config=None, **kw: {
        "recommendations": [{
            "player": "RB One", "market": "rush_yds", "line": 70.0,
            "odds": -110, "hit_prob": 0.6, "projection": 82.0,
            "recommended": True, "stake_units": 1.0, "book": "proxy"}],
        "long_shots": [
            {"player": "RB One", "market": "anytime_td", "odds": 250,
             "model_prob": 0.34, "grade": "A", "book": "FanDuel"},
            {"player": "WR Two", "market": "anytime_td", "odds": 600,
             "model_prob": 0.15, "grade": "B+", "book": "FanDuel"}],
    }
    try:
        r = B.backtest_from_stats(2024, [5])
    finally:
        nv.load_weekly_stats, nv.build_slate, pl.run_slate = saved

    # The yardage board is untouched by any of this.
    assert r.n == 1 and r.n_bets == 1 and r.wins == 1
    assert r.segments["naive"]["n_bets"] == 1
    assert "book" not in r.segments, "a proxy-priced bet is not book-priced"

    # The touchdown board settled on its own, on real prices.
    td = r.longshots
    assert td is not None
    assert td.n == 2 and td.n_bets == 2
    assert td.wins == 1, "RB One scored; WR Two did not"
    assert td.segments["book"]["n_bets"] == 2
    assert td.used_real_lines == 2 and td.total_priced == 2
    # And it is NOT mixed into the yardage win rate.
    assert r.wins == 1 and r.n_bets == 1


def test_no_scorer_picks_leaves_the_longshot_report_absent_not_empty():
    """An absent report says "this was not measured". A zeroed one says
    "measured, found nothing", and they are different claims."""
    import engine.sources.nflverse as nv
    import engine.pipeline as pl
    stats = [{"week": "5", "player_display_name": "RB One",
              "rushing_yards": "80", "passing_yards": "0",
              "receiving_yards": "0", "receptions": "0",
              "rushing_tds": "0", "receiving_tds": "0"}]
    saved = (nv.load_weekly_stats, nv.build_slate, pl.run_slate)
    nv.load_weekly_stats = lambda season: stats
    nv.build_slate = lambda season, w, upto_week=None: _slate()
    pl.run_slate = lambda slate, config=None, **kw: {
        "recommendations": [{
            "player": "RB One", "market": "rush_yds", "line": 70.0,
            "odds": -110, "hit_prob": 0.6, "projection": 82.0,
            "recommended": True, "stake_units": 1.0, "book": "proxy"}],
        "long_shots": []}
    try:
        r = B.backtest_from_stats(2024, [5])
    finally:
        nv.load_weekly_stats, nv.build_slate, pl.run_slate = saved
    assert r.longshots is None


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
