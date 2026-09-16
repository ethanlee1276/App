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
             sharp=(-160, 140), soft=(-120, 150)):
    """One game with a Pinnacle pair and a shopped soft price on each
    side. -160/+140 de-vigs to about 60/40; +150 on the home side would
    be a huge edge, so the soft home price is the modest one and the
    picked row is whichever clears."""
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
                   (day, h, a, "best", h, -120),
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
                   (day, "AAA", "BBB", "best", "AAA", -120),
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
    # +120/-140 de-vigs the home side to ~44%, and +150 on it is +9.5%
    # EV — inside [2%, 15%], so the card exists. `potd.MIN_FAIR` then
    # refuses it: more likely to lose than to win, even at a good price.
    # That is the exact reason seven of the droplet's MLB leans carried.
    conn = _one_day(sharp=(120, -140), soft=(150, -140), hs=5.0, as_=3.0)
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
    assert list(r.lean_why) == [
        "more likely to lose than to win, even at a good price"], r.lean_why


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


def test_the_report_says_how_many_gaps_the_pricer_distrusts():
    """A suspect gap still becomes a card in production, graded Pass at
    a stake of zero. The reader is told how much of the book rides on
    quotes the pricer itself does not trust."""
    # -160/+140 de-vigs the home side to ~59.6%. At -115 that is +11.5%
    # EV — inside the 15% cap so the card exists, past the 7% line so
    # production grades it Pass. At -131 it is +5.2% and ordinary.
    hot = potdbacktest.replay_potd(
        _one_day(sharp=(-160, 140), soft=(-115, -140)), "mlb", rank_auc=AUC)
    assert hot.n_bets == 1, hot.gate_refused
    assert hot.suspect == 1, hot.suspect

    calm = potdbacktest.replay_potd(
        _one_day(sharp=(-160, 140), soft=(-131, -140)), "mlb", rank_auc=AUC)
    assert calm.n_bets == 1 and calm.suspect == 0, calm.suspect

    out = potdbacktest.summarize(hot)
    assert "gate refused" in out
    assert "suspect gaps      1" in out, out


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
                   (day, "AAA", "BBB", "best", "AAA", -120),
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
