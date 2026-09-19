"""A book that is losing stops staking, without anyone noticing first.

Ethan, 2026-09-19, having been shown +2.1% at z 0.75 and asked whether
it was enough: *"yeah id rather stake regardless"* — then, for the rest
of the leagues: *"after that do this for all the other sports with most
likely paper bets."*

Five boards are now playing for money and four of them had no settled
record at all on the day they were switched on. What shipped with them
was a promotion and nothing else: if the NFL book ran -20% over its
first fifty bets, NOTHING would have said so. He would have found out
by reading the Record page and noticing.

A promotion bar with no demotion bar is not a policy. It is an opinion
about the first day.

THE BAR, AND WHY THESE NUMBERS. At this board's prices a settled bet's
return has a standard deviation near 0.68, so at 100 settled the
standard error on the ROI is about 6.8 points. z <= -2.0 is therefore
roughly -13.5%, which at a flat 0.25u is about 3.4 units — a real but
survivable loss in exchange for being near-certain the book is losing
rather than unlucky. Stopping sooner stops good books on noise;
stopping later is paying tuition for a lesson already learned.

AND IT CUTS A BAND BEFORE IT CUTS A BOARD. The MLB paper record ran
-3.9% / +6.4% / -12.0% across its claimed-probability bands: every
dollar of the headline in one of them, and the MOST confident band the
worst. Pulling the whole board for that would throw away the part that
was working.

Run directly: `python3 tests/test_a_losing_staked_book_stops_itself.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                      # noqa: E402

_SEQ = [0]
ODDS = -210                       # the board's measured average price
PAYOUT = 100 / abs(ODDS)


def _conn():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    return conn


def _settled(conn, n, wins, prob=0.68, sport="mlb",
             category=None, stake=0.25):
    """`n` graded rows in the staked book, `wins` of them won."""
    category = category or ledger.LIKELY_LIVE_CATEGORY
    for i in range(n):
        _SEQ[0] += 1
        won = i < wins
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
            "hit_prob,edge,stake_units,stake_dollars,ts,status,category,"
            "pnl_units) VALUES (?,'2026-09-01',?,'total_bases','OVER',1.5,?,"
            "'DK',?,0,?,?,'now',?,?,?)",
            (sport, f"P{_SEQ[0]}", ODDS, prob, stake, stake * 10,
             "won" if won else "lost", category,
             (stake * PAYOUT) if won else -stake))
    conn.commit()


def _board(sport="mlb", prob=0.68, n=1):
    return {"sport": sport, "date": "2026-09-20", "most_likely": [
        {"player": f"New{_SEQ[0]}_{i}", "market": "total_bases",
         "side": "OVER", "line": 1.5, "odds": ODDS, "book": "DK",
         "model_prob": prob, "implied_prob": 0.677,
         "game_date": "2026-09-20"} for i in range(n)]}


def _journaled(conn):
    return conn.execute(
        "SELECT category, stake_units, stake_dollars FROM bets "
        "WHERE player LIKE 'New%'").fetchall()


# --- the breaker's verdict ---------------------------------------------
def test_a_book_with_no_record_yet_keeps_running():
    """Every league but MLB started here. A breaker that stopped an
    unmeasured book would have cancelled the thing Ethan just asked
    for."""
    c = _conn()
    v = ledger.live_verdict(c, "mlb")
    assert v["verdict"] == "run", v
    assert str(ledger.LIVE_STOP_MIN_N) in v["why"], v["why"]


def test_a_thin_losing_record_is_not_enough_to_stop():
    """Half the stop sample, losing badly. Acting here would stop good
    books on noise, which is the failure mode that costs the most."""
    c = _conn()
    _settled(c, ledger.LIVE_STOP_MIN_N // 2, 10)
    assert ledger.live_verdict(c, "mlb")["verdict"] == "run"


def test_a_book_losing_clear_of_the_noise_band_stops():
    """THE POINT, on the BOOK's own z. Two bands, each too thin to be
    judged on its own, together past the stop line — so the verdict can
    only come from the book."""
    c = _conn()
    half = ledger.LIVE_BAND_MIN_N - 5
    _settled(c, half, int(half * 0.55), prob=0.55)
    _settled(c, half, int(half * 0.55), prob=0.68)
    v = ledger.live_verdict(c, "mlb")
    assert v["verdict"] == "stop", v
    assert v["z"] is not None and v["z"] <= ledger.LIVE_STOP_Z, v
    assert "losing side" in v["why"], v["why"]
    assert all(b["verdict"] != "stop" for b in v["bands"]), v["bands"]


def test_a_book_whose_every_band_is_cut_is_itself_stopped():
    """Judging the remainder would report "0 settled, 100 needed" about
    a book that has just had all of its evidence thrown out for losing —
    a sentence that reads like patience and means the opposite."""
    c = _conn()
    _settled(c, 150, 82, prob=0.68)
    v = ledger.live_verdict(c, "mlb")
    assert v["verdict"] == "stop", v
    assert "every band with a record has been cut" in v["why"], v["why"]
    assert ledger.likely_stake_for(c, "mlb", 0.68) == 0.0


def test_a_book_losing_but_not_past_doubt_is_flagged_not_stopped():
    """The gap between review and stop is where a human should be
    looking. Saying so before it becomes a decision is the whole
    point of having two thresholds."""
    c = _conn()
    # 80/130 = 61.5%; -210 needs 67.7%, so about -9% — inside the stop
    # band's reach but not past it.
    _settled(c, 130, 80)
    v = ledger.live_verdict(c, "mlb")
    assert v["verdict"] == "review", v
    assert ledger.LIVE_STOP_Z < v["z"] <= ledger.LIVE_REVIEW_Z, v
    assert ledger.likely_stake_for(c, "mlb", 0.68) == ledger.LIKELY_LIVE_STAKE


def test_a_winning_book_is_left_alone():
    """The breaker has to be capable of saying nothing."""
    c = _conn()
    _settled(c, 150, 115)
    assert ledger.live_verdict(c, "mlb")["verdict"] == "run"


def test_the_paper_history_does_not_vote_on_the_stake():
    """586 paper rows licensed the stake; they must not then outvote the
    evidence about whether the stake is working. Different sample,
    different question."""
    c = _conn()
    _settled(c, 400, 300, category="likely", stake=0.1)   # glowing paper
    _settled(c, 150, 82)                                  # losing money
    assert ledger.live_verdict(c, "mlb")["verdict"] == "stop"


def test_one_league_stopping_does_not_stop_another():
    c = _conn()
    _settled(c, 150, 82, sport="mlb")
    assert ledger.live_verdict(c, "mlb")["verdict"] == "stop"
    assert ledger.live_verdict(c, "nfl")["verdict"] == "run"


# --- and it cuts a band before it cuts a board -------------------------
def test_a_losing_band_is_cut_while_the_rest_keeps_running():
    """The MLB shape: the top band bleeding while the middle carries the
    book. Pulling everything would throw away the part that works."""
    c = _conn()
    _settled(c, 90, 30, prob=0.80)        # the 75-101% band, losing hard
    _settled(c, 150, 115, prob=0.68)      # the 60-75% band, fine
    v = ledger.live_verdict(c, "mlb")
    assert v["verdict"] != "stop", v      # the BOOK is not stopped
    top = [b for b in v["bands"] if b["lo"] == 0.75][0]
    mid = [b for b in v["bands"] if b["lo"] == 0.60][0]
    assert top["verdict"] == "stop", top
    assert mid["verdict"] != "stop", mid
    assert ledger.likely_stake_for(c, "mlb", 0.80) == 0.0
    assert ledger.likely_stake_for(c, "mlb", 0.68) == ledger.LIKELY_LIVE_STAKE


def test_a_thin_band_is_not_cut_on_its_own_thinness():
    c = _conn()
    _settled(c, 20, 2, prob=0.80)
    assert ledger.likely_stake_for(c, "mlb", 0.80) == ledger.LIKELY_LIVE_STAKE


# --- what a stopped row actually becomes -------------------------------
def test_a_stopped_book_still_publishes_and_grades_the_pick():
    """DEMOTED, NOT DELETED. The board goes on making the call at no
    risk, so the record keeps answering whether stopping was right —
    the same shape as the promotion it reverses."""
    c = _conn()
    _settled(c, 150, 82)
    assert ledger.log_most_likely(c, _board()) == 1
    row = _journaled(c)[0]
    assert row["category"] == "likely", dict(row)
    assert row["stake_dollars"] == 0.0, dict(row)
    assert row["stake_units"] > 0, "a zero stake cannot be graded as a bet"


def test_a_cut_band_is_the_only_thing_that_loses_its_money():
    c = _conn()
    _settled(c, 90, 30, prob=0.80)
    _settled(c, 150, 115, prob=0.68)
    ledger.log_most_likely(c, _board(prob=0.80))
    ledger.log_most_likely(c, _board(prob=0.68))
    got = {r["category"] for r in _journaled(c)}
    assert got == {"likely", ledger.LIKELY_LIVE_CATEGORY}, got


def test_a_running_book_is_still_staked_end_to_end():
    c = _conn()
    _settled(c, 150, 115)
    ledger.log_most_likely(c, _board())
    row = _journaled(c)[0]
    assert row["category"] == ledger.LIKELY_LIVE_CATEGORY, dict(row)
    assert row["stake_dollars"] > 0, dict(row)


def test_the_journal_asks_the_breaker_once_not_once_per_row():
    """`live_verdict` queries the journal, and a slate can carry a
    hundred rows. Asking per row would put a hundred round trips in a
    build that already runs on one core."""
    c = _conn()
    seen = [0]
    real = ledger.live_verdict

    def counting(conn, sport, since=None):
        seen[0] += 1
        return real(conn, sport, since)
    ledger.live_verdict = counting
    try:
        ledger.log_most_likely(c, _board(n=25))
    finally:
        ledger.live_verdict = real
    assert seen[0] == 1, seen[0]


# --- the failure mode it chooses, said out loud ------------------------
def test_an_unreadable_journal_keeps_staking_and_says_so():
    """THE ONE PLACE THIS FILE DOES NOT FAIL CLOSED, deliberately.

    Stopping when the breaker cannot see would be the safe-by-default
    reading. It is not what happens, because Ethan asked for these
    boards to be staked and a database hiccup silently cancelling his
    bets is a surprise he did not agree to. The verdict says the check
    could not run, which is the honest version of carrying on."""
    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("no such table: bets")
    v = ledger.live_verdict(Broken(), "mlb")
    assert v["verdict"] == "run", v
    assert v["readable"] is False, v
    assert "could not read" in v["why"], v["why"]


def test_the_bar_is_named_on_the_constants_not_buried_in_a_branch():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "ledger.py"),
        encoding="utf-8").read()
    assert ledger.LIVE_STOP_Z < ledger.LIVE_REVIEW_Z < 0
    assert ledger.LIVE_BAND_MIN_N < ledger.LIVE_STOP_MIN_N, \
        "a band needs a smaller sample than the board, or it is never cut"
    i = src.index("LIVE_STOP_MIN_N =")
    assert "standard deviation" in src[i - 1400:i], \
        "the stop bar does not say where its numbers came from"


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
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
