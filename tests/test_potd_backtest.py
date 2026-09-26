"""The Pick of the Day, replayed: does the product itself make money?

Ethan, 2026-09-16: "you should not stop until you confirm that the Pick
of the Day we show every day is elite and worth betting on."

Nothing in this repository graded the product. `backtest_sharp_anchor`
grades the METHOD — every price disagreement it can find. The Pick of
the Day takes ONE of those a day, ranked on the witness before the edge,
which is a different sample of the same pool and can land anywhere in
the method's spread. On this box's own MLB data that spread runs
backwards in EV (under 4% returned +29.3%, over 8% returned -16.8%), so
assuming the product inherits the method's number is assuming the
answer.

WHAT THESE TESTS DEFEND, since the measurement itself lives on the
droplet and this box's harvest is nearly empty:

  * THE SELECTOR IS IMPORTED, NEVER RESTATED. A backtest that
    reimplements the thing it grades measures the reimplementation.
  * ONE PICK A DAY, and a below-bar lean is not one of them — the
    product does not bet a lean and neither does the replay's headline.
  * THE LEAN COUNTERFACTUAL IS SETTLED SEPARATELY, because "always have
    a pick" is a live product question and the only way to answer it is
    to price it.
  * A REPLAY THAT PRICED NOTHING SAYS WHICH RUNG EMPTIED. A zero that
    cannot explain itself costs an evening, which is the lesson
    `SharpAnchorReport.diagnosis` was dragged out of.

The fixture is a small database built in a temp directory, so these
tests read no box they run on.

Run directly: `python3 tests/test_potd_backtest.py`
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd, potdbacktest                         # noqa: E402

#: The ranking figure every fixture here is replayed under. Supplied
#: rather than read off the box, because `likely.measured_auc` answers
#: from this machine's own rankfit store when it has one — so a test that
#: let it look the number up would pass or fail on what the box last
#: measured, which is exactly the house rule against tests that read the
#: box they run on. 0.71 clears `potd.MIN_RANK_AUC`; the test that the
#: bar bites at all is `tests/test_potd.py`'s.
AUC = 0.71

SCHEMA = """
CREATE TABLE games (
    sport TEXT, season INTEGER, period TEXT, game_id TEXT,
    home TEXT, away TEXT, home_score REAL, away_score REAL,
    spread REAL, total REAL, roof TEXT, surface TEXT, temp REAL, wind REAL,
    extra TEXT, date TEXT,
    PRIMARY KEY (sport, season, period, game_id));
CREATE TABLE odds_history (
    sport TEXT, taken_at TEXT, event_id TEXT, home TEXT, away TEXT,
    player TEXT, market TEXT, book TEXT,
    line REAL, over_odds INTEGER, under_odds INTEGER,
    PRIMARY KEY (sport, taken_at, event_id, player, market, book));
"""


def _db(games, quotes):
    """A throwaway database. ``games`` are (day, home, away, hs, as).
    ``quotes`` are (day, home, away, book, team, odds)."""
    tmp = tempfile.mkdtemp()
    conn = sqlite3.connect(os.path.join(tmp, "h.db"))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for i, (day, home, away, hs, as_) in enumerate(games):
        conn.execute("INSERT INTO games (sport, season, period, game_id, home,"
                     " away, home_score, away_score, date) VALUES"
                     " ('mlb', 2026, ?, ?, ?, ?, ?, ?, ?)",
                     (day, f"g{i}", home, away, hs, as_, day))
    for day, home, away, book, team, odds in quotes:
        conn.execute("INSERT INTO odds_history (sport, taken_at, event_id,"
                     " home, away, player, market, book, over_odds) VALUES"
                     " ('mlb', ?, ?, ?, ?, ?, 'moneyline', ?, ?)",
                     (f"{day}T23:00:00Z", f"{day}:{home}", home, away,
                      team, book, odds))
    conn.commit()
    return conn


def _one_day(day="2026-05-01", hs=5.0, as_=3.0,
             sharp=(-160, 140), soft=(-131, 150)):
    """One game with a Pinnacle pair and a shopped soft price on each
    side. -160/+140 de-vigs to about 60/40 and -131 on the home side is
    +5.0% EV — inside `potd.MAX_EV`, which since 2026-09-16 refuses a
    gap past 7% as one the sharp side has probably already repriced.

    THE DEFAULT WAS -120 (+9.3%) UNTIL THEN, so every fixture in this
    file was a bet the selector now declines and the edge board already
    staked nothing on."""
    games = [(day, "AAA", "BBB", hs, as_)]
    quotes = [(day, "AAA", "BBB", "Pinnacle", "AAA", sharp[0]),
              (day, "AAA", "BBB", "Pinnacle", "BBB", sharp[1]),
              (day, "AAA", "BBB", "best", "AAA", soft[0]),
              (day, "AAA", "BBB", "best", "BBB", soft[1])]
    return _db(games, quotes)


# --- the replay selects on the shipped bars ----------------------------------
def test_the_replay_calls_the_shipped_selector():
    """THE ONE THAT MATTERS MOST. If this module ever grows its own copy
    of the band, the EV floor or the ranking bar, it stops grading what
    the site publishes and starts grading a fork of it."""
    import inspect
    src = inspect.getsource(potdbacktest)
    for name in ("potd.choose", "potd.shortfall", "potd.evidence",
                 "potd.fair_prob", "potd.edge"):
        assert name in src, f"the replay does not use {name}"
    for restated in ("MIN_EV =", "MAX_ODDS =", "MIN_FAIR =", "MIN_RANK_AUC ="):
        assert restated not in src, \
            f"the replay restates {restated!r} instead of importing it"


def test_a_winning_pick_is_settled_as_a_win():
    conn = _one_day(hs=5.0, as_=3.0)
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.games_priced == 1
    assert r.days_with_pick == 1
    assert r.n_bets == 1 and r.wins == 1
    assert r.net > 0 and r.roi is not None and r.roi > 0
    assert r.staked == 1.0


def test_a_losing_pick_costs_exactly_one_unit():
    conn = _one_day(hs=3.0, as_=5.0)
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.n_bets == 1 and r.wins == 0
    assert r.net == -1.0 and r.roi == -1.0


def test_only_one_pick_a_day_however_many_games():
    """The lock. `ledger.log_pick_of_the_day` records the first
    qualifying pick of the day and nothing else; a replay that bet every
    qualifying row would grade a product nobody ships."""
    day = "2026-05-01"
    games, quotes = [], []
    for i, (h, a) in enumerate((("AAA", "BBB"), ("CCC", "DDD"),
                                ("EEE", "FFF"))):
        games.append((day, h, a, 5.0, 3.0))
        quotes += [(day, h, a, "Pinnacle", h, -160),
                   (day, h, a, "Pinnacle", a, 140),
                   (day, h, a, "best", h, -131),
                   (day, h, a, "best", a, 150)]
    r = potdbacktest.replay_potd(_db(games, quotes), "mlb", rank_auc=AUC)
    assert r.games_priced == 3
    assert r.days_seen == 1
    assert r.n_bets == 1, f"{r.n_bets} bets on one day"


def test_two_days_are_two_picks():
    games, quotes = [], []
    for day in ("2026-05-01", "2026-05-02"):
        games.append((day, "AAA", "BBB", 5.0, 3.0))
        quotes += [(day, "AAA", "BBB", "Pinnacle", "AAA", -160),
                   (day, "AAA", "BBB", "Pinnacle", "BBB", 140),
                   (day, "AAA", "BBB", "best", "AAA", -131),
                   (day, "AAA", "BBB", "best", "BBB", 150)]
    r = potdbacktest.replay_potd(_db(games, quotes), "mlb", rank_auc=AUC)
    assert r.days_seen == 2 and r.n_bets == 2


# --- what it refuses to bet --------------------------------------------------
def test_a_game_with_no_sharp_pair_is_never_priced():
    """Both sides of the sharp book, or there is no fair to de-vig and
    the evidence tier the replay claims would be a fiction."""
    day = "2026-05-01"
    conn = _db([(day, "AAA", "BBB", 5.0, 3.0)],
               [(day, "AAA", "BBB", "Pinnacle", "AAA", -160),
                (day, "AAA", "BBB", "best", "AAA", -120)])
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.games_seen == 1
    assert r.games_priced == 0 and r.n_bets == 0


def test_a_price_outside_the_band_is_not_bet():
    """-400 pays 0.25u on 1u and is nowhere near the even-money band the
    feature is built on. The bar is `potd.in_band` and it is the
    shipped one."""
    conn = _one_day(sharp=(-600, 450), soft=(-400, 300))
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.games_priced == 1
    assert r.n_bets == 0
    assert any("band" in why for why in r.census), r.census


def test_a_lean_is_counted_but_never_in_the_headline():
    """A row that clears the hard refusals and misses a quality bar is
    what `build` shows on a quiet day and what
    `log_pick_of_the_day` refuses to journal. The product does not bet
    it, so neither does the headline — it is settled into its own books
    so the "always have a pick" question can be priced."""
    # A ROW THE PRODUCTION GATE PASSES AND THE SELECTOR WILL NOT NAME.
    #
    # The first fixture here priced a NEGATIVE edge, which
    # `sharp_anchor_two_way` refuses outright — so after the replay
    # started calling that gate (2026-09-16) there was no card at all,
    # let alone a lean, and this test was asserting a state production
    # cannot produce.
    #
    # +120/-140 de-vigs the home side to ~43.8%, and +140 on it is +5.1%
    # EV — inside [2%, 15%] so the gate builds the card, and inside
    # `potd.MAX_EV` so the selector reaches the bar this test is about.
    # `potd.MIN_FAIR` then refuses it: not confident enough to be the
    # one bet the day is named after. That is the exact reason seven of
    # the droplet's MLB leans carried — the bar is the same one, and on
    # 2026-09-16 its sentence changed with its meaning, from "at least a
    # coin flip" to the floor the pick is now chosen on.
    #
    # +150 UNTIL 2026-09-16, which is +9.5% — past the new ceiling, so
    # the lean came back carrying "the gap is too big to trust" and this
    # test was no longer about `MIN_FAIR` at all.
    conn = _one_day(sharp=(120, -140), soft=(140, -140), hs=5.0, as_=3.0)
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.days_with_pick == 0
    assert r.n_bets == 0 and r.net == 0.0
    assert r.days_with_only_a_lean == 1
    assert r.lean_bets == 1 and r.lean_wins == 1
    assert r.lean_net > 0
    # The bar it missed travels with it, so the counterfactual can be
    # read by reason rather than as one number — and the reason is the
    # shipped `shortfall`'s own words, not a label this module invented.
    assert sum(b["n"] for b in r.lean_why.values()) == 1
    assert len(r.lean_why) == 1, r.lean_why
    why = next(iter(r.lean_why))
    assert "not confident enough" in why, why
    assert f"{potd.MIN_FAIR:.0%}" in why, why


def test_a_blank_day_is_told_apart_from_a_lean_day():
    """Two different facts: the board had nothing placeable at all, and
    the board had something it would not stand behind."""
    conn = _one_day(sharp=(-600, 450), soft=(-400, 300))
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.days_blank == 1 and r.days_with_only_a_lean == 0


# --- the gate production applies, applied here too ---------------------------
def test_a_gap_too_big_to_trust_is_never_bet():
    """THE ONE THIS FILE WAS WRITTEN TO CATCH AND DID NOT.

    `gamebets.sharp_anchor_two_way` refuses any side whose EV lands
    outside [SHARP_MIN_EV, SHARP_MAX_EV] — 2% to 15% — because "a
    disagreement this big between books usually means the sharp side
    repriced on news and this quote is stale, not free money". Production
    never builds the card at all.

    The first version of this replay computed the EV itself and skipped
    that ceiling. On the droplet, 2026-09-16, it reported an average edge
    at selection of 29.5% and an ROI of +25.6% — a book made almost
    entirely of bets the live site refuses by construction.
    """
    from engine.gamebets import SHARP_MAX_EV
    conn = _one_day(sharp=(-160, 140), soft=(300, -140))
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.games_priced == 1
    assert r.gate_refused == 1
    assert r.n_bets == 0 and r.lean_bets == 0
    assert r.days_with_pick == 0
    # …and the ordinary fixture still gets through, so this is a ceiling
    # and not a wall.
    ok = potdbacktest.replay_potd(_one_day(), "mlb", rank_auc=AUC)
    assert ok.n_bets == 1 and ok.gate_refused == 0
    assert ok.ev_sum <= SHARP_MAX_EV + 1e-9, ok.ev_sum


def test_the_replay_calls_the_gate_rather_than_restating_it():
    """Same rule as the selector: a backtest that reimplements the thing
    it grades measures the reimplementation. That was checked for
    `potd.choose` and not for the row handed to it, which is the more
    expensive half."""
    import inspect
    src = inspect.getsource(potdbacktest)
    assert "sharp_anchor_two_way(" in src
    for restated in ("SHARP_MIN_EV =", "SHARP_MAX_EV =",
                     "devig_two_way("):
        assert restated not in src, f"the replay restates {restated!r}"


def test_a_one_sided_soft_quote_is_counted_not_guessed():
    """The real gate compares both sides, so a game quoted on one side
    only cannot be run through it — and inventing the other price is the
    restatement the test above forbids."""
    day = "2026-05-01"
    conn = _db([(day, "AAA", "BBB", 5.0, 3.0)],
               [(day, "AAA", "BBB", "Pinnacle", "AAA", -160),
                (day, "AAA", "BBB", "Pinnacle", "BBB", 140),
                (day, "AAA", "BBB", "best", "AAA", -120)])
    r = potdbacktest.replay_potd(conn, "mlb", rank_auc=AUC)
    assert r.games_priced == 1
    assert r.one_sided == 1
    assert r.n_bets == 0


def test_a_gap_the_pricer_distrusts_is_counted_and_never_bet():
    """A suspect gap still becomes a card in production — graded Pass at
    a stake of zero — and since `potd.MAX_EV` (2026-09-16) the selector
    will not name one either. So the count is a fact about the POOL, and
    the bet count under it has to be zero or the ceiling is not holding.

    This is the assertion that `MAX_EV` is wired to the same number the
    pricer stops believing at. If the two ever drift, the replay will
    bet a gap the live site grades Pass and the ROI will be about a
    product nobody ships — which is the failure this whole file exists
    to catch, one level down."""
    # -160/+140 de-vigs the home side to ~59.6%. At -115 that is +11.5%
    # EV — inside the 15% cap so the card exists, past the 7% line so
    # production grades it Pass. At -131 it is +5.2% and ordinary.
    hot = potdbacktest.replay_potd(
        _one_day(sharp=(-160, 140), soft=(-115, -140)), "mlb", rank_auc=AUC)
    assert hot.suspect == 1, hot.suspect
    assert hot.n_bets == 0, "a gap production grades Pass was bet"
    assert hot.lean_bets == 1 and list(hot.lean_why) == [
        "the gap is too big to trust — the sharp side has probably moved"
    ], hot.lean_why

    calm = potdbacktest.replay_potd(
        _one_day(sharp=(-160, 140), soft=(-131, -140)), "mlb", rank_auc=AUC)
    assert calm.n_bets == 1 and calm.suspect == 0, calm.suspect

    out = potdbacktest.summarize(hot)
    assert "gate refused" in out
    assert "suspect gaps      1" in out, out


def test_the_picks_are_split_by_the_edge_they_were_chosen_for():
    """`potd.rank_key` sorts by the BIGGEST edge within a tier, and on
    the droplet the average selected edge came out at 8.6% — above the
    line where the pricer itself grades a gap Pass, and inside the band
    `backtest_sharp_anchor` measured at -16.8%. This is the cut that
    says whether the edge-first sort is choosing against the evidence.

    Split at `SHARP_SUSPECT_EV` rather than a round number: the question
    is not "is the edge big" but "is it past the point production stops
    believing it"."""
    games, quotes = [], []
    # -160/+140 de-vigs the home side to ~59.6%, so: -138 is +2.8%,
    # -131 is +5.2%, -115 is +11.5% and past the ceiling.
    for soft_home, day in ((-138, "2026-05-01"),
                           (-131, "2026-05-02"),
                           (-115, "2026-05-03")):
        games.append((day, "AAA", "BBB", 5.0, 3.0))
        quotes += [(day, "AAA", "BBB", "Pinnacle", "AAA", -160),
                   (day, "AAA", "BBB", "Pinnacle", "BBB", 140),
                   (day, "AAA", "BBB", "best", "AAA", soft_home),
                   (day, "AAA", "BBB", "best", "BBB", -140)]
    r = potdbacktest.replay_potd(_db(games, quotes), "mlb", rank_auc=AUC)
    assert r.n_bets == 2, (r.n_bets, r.gate_refused)
    assert sum(b["n"] for b in r.ev_buckets.values()) == 2, r.ev_buckets
    assert set(r.ev_buckets) == {"under 4%", "4-7%"}, r.ev_buckets
    out = potdbacktest.summarize(r)
    assert "by the edge it was chosen for:" in out


def test_the_suspect_band_is_read_off_the_leans_now_that_none_are_bet():
    """`MAX_EV` empties the suspect band among the PICKS by
    construction, so the split above can no longer say whether refusing
    those gaps was right. The refused rows are settled as leans and
    split the same way, which is the only place that question can still
    be asked — a negative line there is the ceiling earning its keep."""
    games, quotes = [], []
    for soft_home, day in ((-131, "2026-05-01"), (-115, "2026-05-02")):
        games.append((day, "AAA", "BBB", 5.0, 3.0))
        quotes += [(day, "AAA", "BBB", "Pinnacle", "AAA", -160),
                   (day, "AAA", "BBB", "Pinnacle", "BBB", 140),
                   (day, "AAA", "BBB", "best", "AAA", soft_home),
                   (day, "AAA", "BBB", "best", "BBB", -140)]
    r = potdbacktest.replay_potd(_db(games, quotes), "mlb", rank_auc=AUC)
    assert r.n_bets == 1 and r.lean_bets == 1
    assert "7-15% (suspect)" not in r.ev_buckets, r.ev_buckets
    assert "7-15% (suspect)" in r.lean_ev_buckets, r.lean_ev_buckets
    assert r.lean_ev_buckets["7-15% (suspect)"]["n"] == 1
    out = potdbacktest.summarize(r)
    assert "the leans, by the edge they were refused at:" in out
    assert "7-15% (suspect)" in out


def test_the_two_splits_are_the_same_bands_computed_once():
    """The picks and the leans have to be cut at the same places or the
    comparison between them is meaningless. Both read `BANDS`."""
    import inspect
    src = inspect.getsource(potdbacktest.summarize)
    assert '"under 4%"' not in src and "'under 4%'" not in src, \
        "summarize writes a band name out instead of reading BANDS"
    assert src.count("in BANDS") == 2, "one of the two splits is not on BANDS"
    assert potdbacktest.BANDS[2].endswith("(suspect)")
    assert potdbacktest._band(0.039) == potdbacktest.BANDS[0]
    assert potdbacktest._band(0.04) == potdbacktest.BANDS[1]
    assert potdbacktest._band(0.0699) == potdbacktest.BANDS[1]
    assert potdbacktest._band(0.071) == potdbacktest.BANDS[2]


# --- the report ---------------------------------------------------------------
def test_an_empty_replay_says_which_rung_emptied():
    """A zero that cannot explain itself costs an evening."""
    out = potdbacktest.summarize(potdbacktest.replay_potd(_db([], []), "mlb"))
    assert "NO PICK WAS EVER MADE" in out
    assert "nothing priced" in out
    assert out.strip()


def test_the_report_quotes_a_standard_error_beside_every_roi():
    """An ROI quoted alone invites a reader to treat +9% over 90 bets as
    a fact about the world. It is about 1.3 standard errors from zero."""
    games, quotes = [], []
    for i in range(12):
        day = f"2026-05-{i + 1:02d}"
        games.append((day, "AAA", "BBB", 5.0 if i % 3 else 3.0, 3.0 if i % 3 else 5.0))
        quotes += [(day, "AAA", "BBB", "Pinnacle", "AAA", -160),
                   (day, "AAA", "BBB", "Pinnacle", "BBB", 140),
                   (day, "AAA", "BBB", "best", "AAA", -131),
                   (day, "AAA", "BBB", "best", "BBB", 150)]
    r = potdbacktest.replay_potd(_db(games, quotes), "mlb", rank_auc=AUC)
    assert r.n_bets == 12
    assert r.roi_stderr is not None and r.roi_stderr > 0
    out = potdbacktest.summarize(r)
    assert "s.e." in out
    assert "READ THIS BEFORE THE ROI" in out


def test_the_report_says_what_the_fairs_predicted():
    """The one number that is not about money. If the picks were priced
    at fairs averaging 57% and won 44%, the ROI is an accident either
    way."""
    r = potdbacktest.replay_potd(_one_day(), "mlb", rank_auc=AUC)
    fair, got = r.calibration
    assert 0.0 < fair <= r.n_bets
    assert got == float(r.wins)
    assert "the fairs said" in potdbacktest.summarize(r)


def test_the_caveats_are_in_the_module_that_computes_the_number():
    """Not in a doc a reader has to go and find. Every one of these is a
    reason the figure is a floor rather than a copy of production."""
    head = (potdbacktest.__doc__ or "").lower()
    for caveat in ("moneylines only", "no exchange tier",
                   "close against close", "bettable"):
        assert caveat in head, f"the header does not state: {caveat}"


def test_the_replay_takes_no_schema_locks_on_the_box_it_reads():
    """`potd_backtest.py` runs on the droplet beside four builds that
    have spent nights failing on "database is locked". A reader that
    takes DDL locks to answer a SELECT is the sixth process in that
    pile-up."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "potd_backtest.py")).read()
    assert "db.read_only(" in src
    assert "db.connect(" not in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
