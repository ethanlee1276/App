"""The board that ranks by likelihood, not by edge.

Ethan, 2026-08-30: "we need to focus more on using the data to figure out
who will score each game, not who has the best edge... a separate page
which will be the main page for bets, that will show who we genuinely
think will score or hit the over."

The measurements agree and are not close. The model ranks outcomes and
prices them badly, and those are separate abilities:

    who scores a touchdown    AUC 0.721 (22,099 graded player-weeks)
    who clears their line     0.76 rushing, 0.77 receptions,
                              0.73 receiving, 0.69 passing
    where the market is wrong AUC 0.468 — noise

Long Shots is built on the last one. This board is built on the first
two, which is why it is the main page and that one is the specialist.

Run directly: `python3 tests/test_likely.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely as K                               # noqa: E402


def _prop(market="rec_yds", prob=0.62, odds=-115, player="A Wideout",
          has_market=True, **kw):
    got = {"player": player, "team": "CIN", "opponent": "CLE",
           "market": market, "market_label": market, "side": "over",
           "line": 45.5, "book": "DK", "odds": odds, "hit_prob": prob,
           "fair_prob": 0.55, "projection": 52.0, "ev_per_unit": 0.03,
           "has_market": has_market, "reasons": ["because"],
           "recent_values": [40, 60, 55], "date": "2026-09-14"}
    got.update(kw)
    return got


def _watch(player="A Back", prob=0.58, odds=-140):
    return {"player": player, "team": "DET", "opponent": "CHI",
            "book": "DK", "odds": odds, "model_prob": prob,
            "implied_prob": 0.55, "ev_per_unit": 0.01,
            "reasons": ["Team implied total 27.5"], "recent_values": [1, 0, 1],
            "game_date": "2026-09-14"}


def _always(_market):
    return True


#: THE MIXTURE, INJECTED. `run_tests` points QB_MODELS_DIR at an empty
#: sandbox, where `display_prob` finds no store and every row falls back
#: to its raw claim — so fixtures tuned to mixture output pass standalone
#: and fail in the suite. These are the real fitted values from 2026-08-30.
FITS = {
    "rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54},
    "rec_yds": {"zero": [-0.39, 0.61], "sigma": 0.60},
    "receptions": {"zero": [-0.82, 0.48], "sigma": 0.46},
}


# --- what may be ranked --------------------------------------------------
def test_only_markets_shown_to_rank_appear_at_all():
    """"We think he will hit" is a claim, and an unmeasured claim on the
    main board is exactly what this product is trying to stop being."""
    for market in ("anytime_td", "receptions", "rush_yds", "rec_yds",
                   "pass_yds"):
        assert K.rankable(market), market
    for market in ("first_td", "longest_reception", "made_up"):
        assert not K.rankable(market), market
    assert K.from_prop(_prop(market="made_up"), _always, fits=FITS) is None


def test_the_rank_floor_is_above_a_coin_flip_by_a_margin():
    """0.5 is a coin flip; a board that cannot sort itself has no
    business claiming who will hit."""
    assert K.MIN_RANK_AUC > 0.5
    assert min(K.RANK_AUC.values()) >= K.MIN_RANK_AUC


# --- the distinction the whole page rests on -----------------------------
def test_a_market_can_rank_without_being_bettable():
    """THE POINT, AND IT LOOKS WRONG UNTIL YOU SEE THE TWO TESTS APART.
    `calibrate.is_reliable` shuts rushing yards for BETTING because its
    probability is wrong in ABSOLUTE terms — it cannot be compared to a
    price. Ranking needs it right only in RELATIVE terms. Rushing yards
    rank at 0.7605 while being unbettable, and ordering barely moves when
    the calibration is stripped out entirely (0.7605 against 0.7627 for
    the raw projection), because a monotone error does not reorder a
    list."""
    shut = K.from_prop(_prop(market="rush_yds"),
                       lambda m: m != "rush_yds")
    assert shut is not None, "a shut market must still be rankable"
    assert shut["bettable"] is False
    open_ = K.from_prop(_prop(market="receptions"), _always, fits=FITS)
    assert open_["bettable"] is True


def test_the_row_carries_the_measurement_that_justifies_it():
    """A reader should be able to ask "how good is this ordering" and get
    a number rather than a tone of voice."""
    row = K.from_prop(_prop(market="rush_yds"), _always, fits=FITS)
    assert row["rank_auc"] == K.RANK_AUC["rush_yds"]


# --- the ordering --------------------------------------------------------
def test_ranked_by_probability_and_by_nothing_else():
    """Sorting by EV, or breaking ties on it, would quietly rebuild the
    edge board under a different name — the exact failure this page
    exists to correct."""
    # PROJECTIONS DIFFER, not just the claimed probability. The
    # displayed number is recomputed from the projection against the
    # line, so three players with identical projections SHOULD land on
    # identical probabilities — an earlier version of this fixture varied
    # only `hit_prob` and read that correct behaviour as a sorting bug.
    # EACH ROW'S BOOK NUMBER SITS NEAR ITS OWN PROJECTION. The
    # credibility bar refuses a displayed probability more than
    # MAX_CREDIBLE_EDGE from the book's, so a fixture that gave three
    # different projections one shared `fair_prob` had two of them
    # correctly thrown out — for a reason that has nothing to do with
    # ordering.
    rows = [_prop(player="Low", prob=0.42, projection=44.0,
                  fair_prob=0.38, ev_per_unit=0.40),
            _prop(player="High", prob=0.71, projection=72.0,
                  fair_prob=0.67, ev_per_unit=-0.10),
            _prop(player="Mid", prob=0.55, projection=55.0,
                  fair_prob=0.51, ev_per_unit=0.20)]
    board = K.build(rows, [], [], sport="nfl", fits=FITS)
    assert [r["player"] for r in board] == ["High", "Mid", "Low"], board
    # The juiciest EV on the slate is LAST, which is the whole point.
    assert board[-1]["player"] == "Low"


def test_a_long_shot_pick_and_its_watch_row_are_not_shown_twice():
    board = K.build([], [_watch()], [_watch()], sport="nfl", fits=FITS)
    assert len(board) == 1, board


def test_touchdowns_and_yardage_rank_against_each_other():
    """One list, not two stacked. A 71% receiving over outranks a 58%
    scorer and has to say so."""
    # Projected well clear of his line, so he leads on the CALIBRATED
    # number rather than on a raw claim the mixture then pulls down.
    board = K.build([_prop(player="Wideout", prob=0.71, projection=88.0,
                           fair_prob=0.77)],
                    [], [_watch(player="Back", prob=0.58)], sport="nfl", fits=FITS)
    assert [r["player"] for r in board] == ["Wideout", "Back"], board
    assert board[0]["model_prob"] > board[1]["model_prob"]


# --- what never reaches it ----------------------------------------------
def test_a_proxy_price_is_not_a_likelihood():
    assert K.from_prop(_prop(has_market=False), _always, fits=FITS) is None


def test_a_stale_or_absurd_price_is_refused():
    assert K.from_prop(_prop(odds=9000), _always, fits=FITS) is None
    assert K.from_prop(_prop(odds=None), _always, fits=FITS) is None


def test_a_coin_flip_is_not_likely_however_it_ranks():
    """The page is called Most Likely. A 31% shot at the top of a thin
    slate is still not something to tell somebody is likely."""
    assert K.from_prop(_prop(prob=0.12), _always, fits=FITS) is None
    assert K.MIN_PROB >= 0.30


def test_a_missing_probability_never_becomes_a_zero():
    assert K.from_prop(_prop(prob=None), _always, fits=FITS) is None
    board = K.build([], [], [dict(_watch(), model_prob=None)], sport="nfl", fits=FITS)
    assert board == []


# --- what the page says about itself -------------------------------------
def test_the_summary_counts_rather_than_asserts():
    board = K.build([_prop(market="rush_yds")], [], [_watch()], sport="nfl", fits=FITS)
    got = K.summary(board)
    assert got["rows"] == len(board)
    assert got["bettable"] + got["rank_only"] == got["rows"]
    assert sum(got["by_market"].values()) == got["rows"]


def test_the_board_is_capped_so_it_stays_a_ranking():
    rows = [_prop(player=f"P{i}", prob=0.9 - i / 1000.0) for i in range(200)]
    assert len(K.build(rows, [], [], sport="nfl", fits=FITS)) == K.LIMIT


def test_the_page_is_paid_because_it_is_the_product():
    from engine.gate import PAID_KEYS
    assert "most_likely" in PAID_KEYS, \
        "the main board is the thing somebody is paying for"


def test_both_football_boards_publish_it():
    """A sport that published an empty one would read as broken rather
    than as narrow, and college prices touchdowns and nothing else."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "cfb_build.py")).read()
    assert '"most_likely"' in src
    pipe = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "pipeline.py")).read()
    assert '"most_likely"' in pipe


def test_the_second_board_never_costs_the_first_one():
    """It is an additional view of rows that are already published. If it
    cannot be assembled the page renders empty rather than the slate
    failing to build."""
    import inspect
    from engine import pipeline
    src = inspect.getsource(pipeline._likely_board)
    assert "except Exception" in src and "return []" in src


# --- calibrated, because the page claims a probability -------------------
def test_a_boundary_fit_market_reaches_this_page_uncorrected_without_the_mixture():
    """THE DEFECT ETHAN CAUGHT, 2026-08-30: "we have the calibration off
    for the most likely page."

    `calibrate.correction_for` DISCARDS a boundary fit rather than
    applying it — correct for betting, since a capped temperature is the
    search failing rather than a correction. But rush_yds and rec_yds
    both fitted to T=6.0, exactly GRID_MAX, so the two markets measured
    MOST overconfident were the two reaching this page with no correction
    at all."""
    from engine.calibrate import correction_for, GRID_MAX
    import engine.calibrate as C
    store = dict(C.load(C.DEFAULT_PATH))
    # Whatever this box holds, a capped fit must resolve to no correction
    # — that is the behaviour that left the page uncalibrated.
    C._cache = {"nfl:rush_yds": (GRID_MAX, -0.16)}
    try:
        assert correction_for("nfl", "rush_yds") == (1.0, 0.0)
    finally:
        C._cache = None
    assert store is not None


def test_the_mixture_pulls_an_overconfident_number_down():
    """A back with two blanks in six games, projected 58 against a 45.5
    line: the raw model says 62%, the mixture says the mid-fifties. The
    difference is the chance he simply does not touch it, which a normal
    spreads below zero instead of piling at zero."""
    row = _prop(market="rush_yds", prob=0.62, projection=58.0,
                recent_values=[70, 0, 52, 61, 0, 44])
    got = K.from_prop(row, _always, fits=FITS)
    if got["prob_source"] == "model":
        return          # no fitted store on this box; nothing to assert
    assert got["model_prob"] < got["raw_prob"], got
    assert got["raw_prob"] == 0.62


def test_the_reader_is_told_which_number_they_are_seeing():
    """A page that silently swapped its probability source would be the
    opposite of the point."""
    got = K.from_prop(_prop(), _always, fits=FITS)
    assert got["prob_source"] in ("model", "mixture")
    assert "raw_prob" in got
    app = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "web", "js", "app.js")).read()
    assert 'r.prob_source !== "mixture"' in app
    assert "raw read was" in app


def test_a_row_the_mixture_cannot_price_keeps_the_number_it_had():
    """None rather than a guess whenever anything is missing. A
    likelihood page that swapped in a WORSE number would be the opposite
    of the point twice over."""
    from engine.yardagefit import display_prob
    assert display_prob("rush_yds", None, 45.5, [1, 2, 3]) is None
    assert display_prob("rush_yds", 58.0, None, [1, 2, 3]) is None
    assert display_prob("rush_yds", 58.0, 45.5, [1]) is None
    assert display_prob("made_up_market", 58.0, 45.5, [1, 2, 3]) is None


def test_passing_yards_is_left_on_the_normal_on_its_own_evidence():
    """Adopted where measured better, refused where measured worse.
    pass_yds is 2.3% zeroes, the normal fits it nearly perfectly, and the
    mixture came out WORSE there (0.0389 against 0.0324)."""
    from engine.yardagefit import MIXTURE_MARKETS
    assert "pass_yds" not in MIXTURE_MARKETS
    for m in ("rush_yds", "rec_yds", "receptions"):
        assert m in MIXTURE_MARKETS


def test_the_nightly_refits_it():
    """A fitted number nobody refits goes stale, and this one is fitted
    from the box's own logs."""
    import inspect
    from engine import deepfit
    assert "refit_yardage_mixture(db)" in inspect.getsource(deepfit.refit_all)
    src = inspect.getsource(deepfit.refit_yardage_mixture)
    assert "save_fits" in src and "likelihood" in src.lower()


def test_the_money_question_is_recorded_with_its_error_bars():
    """The likelihood board is NOT journaled, and the reason is a
    measurement rather than caution. Both orderings bet the top quarter
    of the same qualifying pool; receptions favoured likelihood by +11.7%
    against +2.4% ROI, and rec_yds showed no difference at all. Every one
    of those numbers carries about ten points of standard error on 76-86
    bets, and the hit-rate gap is z = +1.5.

    Recorded with the intervals because a table without them is how a
    1.5-sigma result becomes a strategy."""
    import inspect
    src = inspect.getsource(K)
    for bit in ("+11.7%", "+2.4%", "65.8%", "z = +1.5", "not proof"):
        assert bit in src, f"the money measurement lost {bit}"
    assert "NOT JOURNALED" in src


def test_nothing_on_this_board_reaches_the_journal():
    """A likelihood row has no stake and no journal path. The guard is
    `ledger.journal_skip_reason`, which only takes rows carrying
    `recommended` and a positive stake — neither of which this board
    emits."""
    got = K.from_prop(_prop(), _always, fits=FITS)
    assert "stake_units" not in got and "recommended" not in got
    from engine.ledger import journal_skip_reason
    assert journal_skip_reason(dict(got)) is not None


# --- the guard this board never had --------------------------------------
def test_a_probability_that_runs_away_from_the_book_is_refused():
    """EVERY OTHER PICK PATH HAS THIS AND THIS ONE DID NOT.
    `betting.evaluate_prop`, `longshots` and `gamebets.temper` all refuse
    a probability disagreeing with the market past MAX_CREDIBLE_EDGE, on
    the argument that a 20-point gap in a heavily bet market is our error
    far more often than a discovery. The likelihood board carried no such
    check, because it does not grade or stake and nothing forced the
    question — while still making the claim that IS the product."""
    # LINE AND PROJECTION HAVE TO AGREE with the market being named: the
    # displayed number is recomputed from one against the other, so a
    # receptions projection against the fixture's default 45.5 yardage
    # line lands under MIN_PROB and is dropped for the wrong reason.
    rec = dict(market="receptions", line=3.5, projection=5.2,
               recent_values=[4, 5, 3, 6])
    near = K.from_prop(_prop(prob=0.62, fair_prob=0.68, **rec), _always, fits=FITS)
    far = K.from_prop(_prop(prob=0.62, fair_prob=0.25, **rec), _always, fits=FITS)
    assert near is not None
    assert far is None, "a 40-point disagreement is a modelling error"


def test_credibility_is_judged_on_the_number_actually_shown():
    """CHECKED AFTER THE MIXTURE, not before. The mixture recomputes from
    the projection and discards the market shrink `hit_prob` carried, so
    the rows most able to run away from the book are exactly the ones
    this page calibrated. Checking the input would pass what this exists
    to catch."""
    import inspect
    src = inspect.getsource(K.from_prop)
    i_mix = src.index("display_prob(")
    i_cred = src.index("_credible(shown")
    assert i_cred > i_mix, \
        "the bar is applied to the raw claim, not to what is displayed"


def test_the_bar_is_the_same_one_the_rest_of_the_engine_uses():
    from engine.betting import MAX_CREDIBLE_EDGE as BAR
    assert K.MAX_CREDIBLE_EDGE == BAR


def test_touchdown_rows_answer_to_the_same_bar():
    """One board, one rule. They arrive pre-shrunk so it almost never
    fires — and almost never is not a guarantee."""
    wild = dict(_watch(prob=0.90), implied_prob=0.30)
    assert K.build([], [], [wild], sport="nfl", fits=FITS) == []
    sane = dict(_watch(prob=0.58), implied_prob=0.55)
    assert len(K.build([], [], [sane], sport="nfl", fits=FITS)) == 1


def test_a_missing_book_number_is_not_treated_as_a_disagreement():
    """No fair price means nothing to disagree WITH. Refusing on absence
    would empty the board on exactly the markets that quote one side."""
    assert K._credible(0.80, None) is True
    assert K._credible(None, 0.20) is True
    assert K._credible(0.80, "not a number") is True


def test_an_emptied_board_can_say_why():
    """Census discipline: a board that came out short because the bar
    fired must not look like a quiet slate."""
    got = K.summary([], refused=7)
    assert got["refused_incredible"] == 7
    assert got["rows"] == 0



# --- the board shows bets, not chalk (Ethan, 2026-09-01) --------------------
def test_an_under_is_a_pick_held_to_the_same_bar():
    """First settled night of the MLB likely book: 52/73 won, ROI -11.2%,
    and nearly every row an UNDER at -300 to -1800. Ethan: "the point of
    the most likley page is to push bets... not just grabbing random
    -1200 props." The first fix banned every under; the price cap beside
    it was what actually answered him, and a day later (2026-09-02): "all
    I see us is doing overs, but we have no unders ... there is more bets
    that we can salvage." So: an under at a bettable price is a pick, and
    an under past the cap is still chalk."""
    rows = K.build([_prop(side="under", prob=0.62, odds=-115)])
    assert len(rows) == 1 and rows[0]["side"] == "under", rows
    assert K.build([_prop(side="under", prob=0.85, odds=-400)]) == []
    row = {"model_prob": 0.66, "side": "under", "odds": -180,
           "book": "DK", "implied_prob": 0.64}
    assert K.admissible(row) == ""
    assert "chalk" in K.admissible({**row, "odds": -400})
    assert "not happening" not in K.admissible(row)


def test_an_under_shows_its_own_probability_through_the_mixture():
    """The mixture is P(over); an under row shows the complement rather
    than the over's number wearing an under label. The two sides of one
    line sum to one — which is also why the ranking measurement covers
    both: an AUC is symmetric under the complement."""
    over = K.from_prop(_prop(market="rec_yds", side="over", prob=0.58,
                             fair_prob=0.55), _always, fits=FITS)
    under = K.from_prop(_prop(market="rec_yds", side="under", prob=0.42,
                              fair_prob=0.45), _always, fits=FITS)
    assert over and under, (over, under)
    assert over["prob_source"] == "mixture" == under["prob_source"]
    assert abs(over["model_prob"] + under["model_prob"] - 1.0) < 1e-3, \
        (over["model_prob"], under["model_prob"])
    assert under["raw_prob"] == 0.42


def test_chalk_beyond_the_price_cap_is_refused_everywhere():
    """-250 is the line: past it a 'most likely' row is a fee, not a
    pick. The cap lives in admissible — the ONE bar — so every sport's
    board inherits it, watch rows included."""
    assert K.build([_prop(odds=K.HEAVIEST_PRICE)]),         "the cap itself is still a showable price"
    assert K.build([_prop(odds=K.HEAVIEST_PRICE - 1,
                               prob=0.85)]) == []
    row = {"model_prob": 0.9, "side": "over", "odds": -1200,
           "book": "DK", "implied_prob": 0.88}
    assert "chalk" in K.admissible(row)
    heavy_watch = _watch(prob=0.75, odds=-800)
    assert K.build([], [heavy_watch]) == [],         "the touchdown chain passes the same bar"


def test_a_row_the_engine_calls_a_data_error_is_off_this_board_too():
    """Ethan, 2026-09-02, from a phone: "How is a under 4.5 bases -200,
    we need to figure out how and why we showed that and fix it."

    Zack Gelof, UNDER 4.5 total bases at -200, the card reading MODEL
    73% against a book-implied 63%, projection 1.7, none of his last ten
    games clearing 4.5 — on the Most Likely board while its own card
    printed `betting.IMPLAUSIBLE_EDGE_REASON` in red.

    THE MODEL WAS RIGHT. P(under 4.5) on a 1.7 projection is about 96%.
    73% is what 96% becomes after `temper_edge` shrinks it toward a
    market number that cannot be a real price for that line, and the
    board was ranking the shrink artefact.

    And the old guard could not have caught it at any threshold: since
    `hit - fair` equals `shrink x (raw - fair)`, a shrunk gap can only
    exceed the 10-point cap when the RAW gap exceeds 20, so every row
    the engine refuses between 10 and 20 points passed a check made on
    the shrunk number. The bar now asks the engine's question of the
    engine's number."""
    row = {"model_prob": 0.73, "side": "under", "odds": -200,
           "book": "theScore Bet", "implied_prob": 0.63,
           "engine_raw_prob": 0.963, "fair_prob": 0.63}
    assert K.admissible(row) == \
        "the model and the market disagree by more than we credit"
    # The band that made the old check useless: 15 raw points, shrunk to
    # well under the cap.
    fifteen = {**row, "engine_raw_prob": 0.78, "model_prob": 0.675}
    assert K.admissible(fifteen), "the 10-to-20 point band is still invisible"
    # A real under, whose raw claim IS near the market, still ships.
    ok = {**row, "line": 1.5, "odds": -250, "engine_raw_prob": 0.75,
          "implied_prob": 0.67, "fair_prob": 0.67, "model_prob": 0.73}
    assert K.admissible(ok) == "", K.admissible(ok)


def test_a_maker_with_no_pre_shrink_claim_is_judged_on_what_it_has():
    """Watch rows and game cards carry no `engine_raw_prob`; they answer
    the credibility question on their own displayed number rather than
    being refused for a field they never had."""
    watch = {"model_prob": 0.66, "side": "over", "odds": -140,
             "book": "DK", "implied_prob": 0.60}
    assert K.engine_credible(watch) is True
    assert K.admissible(watch) == ""


def test_from_prop_carries_the_engine_numbers_the_bar_needs():
    row = _prop(prob=0.62)
    row["raw_prob"] = 0.71
    got = K.from_prop(row, _always, fits=FITS)
    assert got["engine_raw_prob"] == 0.71
    assert got["fair_prob"] == row["fair_prob"]


def test_a_short_board_says_how_many_it_turned_down():
    """`likely_census` was read only when the board came back EMPTY —
    the rarer case and the less confusing one. An empty board with a
    reason reads as a working system; a SHORT board with no reason
    reads as the model having nothing to say. The real censuses are
    large (18 NFL and 162 MLB refusals on 2026-09-02), so a reader
    looking at four cards could not know 162 rows were considered."""
    import os as _os
    with open(_os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))), "web", "js", "app.js"),
            encoding="utf-8") as f:
        js = f.read()
    assert "function likelyRefusedNote(census, shown)" in js
    body = js[js.index("function likelyRefusedNote(census, shown)"):]
    body = body[:body.index("\n}")]
    assert "turned down" in body
    assert "escapeHtml(k)" in body, "a census key reaches the page unescaped"
    # Drawn on the board that HAS rows, beside the trust line.
    at = js.index("function renderLikely()")
    full = js[at:js.index("\nfunction ", at + 10)]
    assert "likelyRefusedNote(state.data.likely_census, rows.length)" in full
    # …and the empty state keeps its own, different sentence.
    assert "function likelyEmptyWhy(census)" in js
    assert "likelyEmptyWhy(state.data.likely_census)" in full


def test_the_page_never_labels_a_shrink_artefact_as_the_model():
    """Ethan's Gelof card read MODEL 73% on a claim of about 96%. That
    73% is `fair + shrink x (raw - fair)` — a statement about how far we
    are from a price we do not credit, not a probability of anything, so
    printing it under "Model" tells a reader the model believes
    something it does not.

    Computed from the row's own `raw_prob` and `fair_prob`, which ride
    on every prop row, so no reason text has to be matched."""
    import os as _os
    with open(_os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))), "web", "js", "app.js"),
            encoding="utf-8") as f:
        js = f.read()
    import re as _re
    from engine.betting import MAX_CREDIBLE_EDGE as _cap
    # THE VALUE, NOT ITS SPELLING. Python renders the constant "0.1" and
    # the page reads better as "0.10"; a string compare would fail on
    # that and pass on a real drift to 0.15, which is backwards.
    _m = _re.search(r"const MAX_CREDIBLE_EDGE = ([0-9.]+);", js)
    assert _m, "the page lost its copy of the cap"
    assert abs(float(_m.group(1)) - _cap) < 1e-9, \
        f"the page's cap ({_m.group(1)}) drifted from the engine's ({_cap})"
    assert "function shrinkArtefact(r)" in js
    art = js[js.index("function shrinkArtefact(r)"):]
    art = art[:art.index("\n}")]
    assert "raw_prob" in art and "fair_prob" in art
    # Every surface that printed the shrunk number goes through the tile.
    assert "function modelMetric(r, shown, label)" in js
    assert "modelMetric(r, r.hit_prob)" in js
    assert 'modelMetric(r, r.hit_prob, "Hit prob")' in js
    assert '<div class="v">${pct(r.hit_prob)}</div></div>` : ""}' not in js, \
        "a Model tile still prints the shrunk number unconditionally"
    # …including the comps bar, which asks whether the model agrees with
    # history — a question about the player, not about the price.
    assert "shrinkArtefact(r) ? Number(r.raw_prob)" in js


def test_the_render_gate_catches_a_refused_row_from_a_stale_file():
    """The engine drops these at build time; this gate is for the board
    file that predates the rule — the way the -1200 unders outlived
    their own ban."""
    import os as _os
    with open(_os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))), "web", "js", "app.js"),
            encoding="utf-8") as f:
        js = f.read()
    body = js[js.index("function showableLikelyRow(r)"):]
    body = body[:body.index("\n}")]
    assert "engine_raw_prob" in body and "shrinkArtefact" in body
    assert "LIKELY_HEAVIEST_PRICE" in body, "the price cap must survive"


def test_the_page_enforces_the_same_rules_a_stale_file_could_dodge():
    """2026-09-02: the droplet served a PRE-FIX board file while its
    builds were starved, and the page happily drew the -1200 unders the
    engine had already banned — Ethan, from his phone: "your still doing
    these dumb ass bets." A rule the render does not also enforce is a
    rule any stale file overrides; the page is the last gate, and its
    price cap is pinned equal to the engine's so they cannot drift."""
    import os as _os
    with open(_os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))), "web", "js", "app.js"),
            encoding="utf-8") as f:
        js = f.read()
    assert "function showableLikelyRow(r)" in js
    assert f"const LIKELY_HEAVIEST_PRICE = {K.HEAVIEST_PRICE};" in js
    for anchor in (".filter(showableLikelyRow).slice(0, 10)",
                   "rows: (sh.rows || []).filter(showableLikelyRow)",
                   "(state.data.most_likely || []).filter(showableLikelyRow)"):
        assert anchor in js, anchor

# --- the injury hold, on this board too -----------------------------------
def test_a_listed_player_is_held_off_the_likelihood_board():
    """Ethan, 2026-09-02: "some of them seem weird ... especially the most
    likely bets." `rules.apply_rules` holds a Questionable / Doubtful /
    Out player off the edge board; this board took the same row, ignored
    `recommended`, and carried no field with the designation. A player
    ruled out on Friday could top "who is most likely to hit" on Sunday."""
    fine = _prop(player="Healthy", prob=0.66)
    out = _prop(player="Ruled Out", prob=0.80, injury_status="OUT",
                recommended=False,
                warnings=["Ruled Out listed OUT — hold until inactives confirm status"])
    census: dict = {}
    board = K.build([fine, out], sport="nfl", fits=FITS, census=census)
    assert [r["player"] for r in board] == ["Healthy"]
    assert census == {"listed OUT — held until inactives confirm": 1}


def test_questionable_is_held_the_same_way_the_edge_board_holds_it():
    q = _prop(player="Game Time", prob=0.70, injury_status="QUESTIONABLE")
    assert K.admissible(K.from_prop(q, _always, fits=FITS)).startswith(
        "listed QUESTIONABLE")


def test_a_watch_row_carries_the_designation_and_is_refused_on_it():
    w = _watch(player="Hurt Back", prob=0.61)
    w["injury_status"] = "DOUBTFUL"
    w["caveats"] = ["Hurt Back listed DOUBTFUL — hold until inactives confirm status"]
    got = K.from_watch(w)
    assert got["injury_status"] == "DOUBTFUL"
    assert got["warnings"] == w["caveats"]
    assert K.admissible(got).startswith("listed DOUBTFUL")
    assert K.build([], [w], sport="nfl", fits=FITS) == []


def test_the_designation_rides_on_every_prop_row_from_the_decision():
    """The pipeline stamps `injury_status` from the rules decision's own
    `health` check, so this board cannot disagree with the hold."""
    from engine import pipeline as P
    class D:
        checks = [{"key": "juice", "value": "-115"},
                  {"key": "health", "value": "OUT"}]
    assert P._injury_status(D()) == "OUT"
    class Clean:
        checks = [{"key": "health", "value": "not listed"}]
    assert P._injury_status(Clean()) == ""
    assert P._injury_status(object()) == ""
    import inspect
    assert '"injury_status": _injury_status(decision)' in inspect.getsource(P._rec_to_dict)


def test_a_row_with_no_designation_field_is_unaffected():
    """CFB and MLB rows never carried the field; absence is health."""
    assert K.admissible(K.from_prop(_prop(), _always, fits=FITS)) == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
