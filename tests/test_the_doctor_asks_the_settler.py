"""`why_open` says "gradeable now" only when the settler would grade it.

Ethan, 2026-09-19, from the droplet's grading check: one NFL bet filed
under "gradeable now" beside 143 filed under "day barely ingested". The
settler runs every five minutes, so a bet that is genuinely gradeable
cannot still be open — and the doctor's own advice for that heading is
"run `--settle all`; if they survive it, tell me." He told me.

It survived because the two functions were answering the same question
differently. `settle_from_history` does not grade a game bet on "some
row is final"; it calls `_pick_dh_game`, which WAITS when the bet names
a leg that has not finished, and waits again when only part of a
multi-game day is in. Both of those states have a final row in them, and
`why_open` re-derived its verdict from exactly that — `if finals:
reason = "gradeable now"` — so the settler's two deliberate waits were
reported as the settler failing.

That is worse than an unhelpful label. It sends the reader looking for a
defect in the settler, which is where I would have gone.

The doctor now asks `_pick_dh_game` itself, so there is ONE answer to
"will this grade?" — the same reason `_hist_where` and `close_dates` are
each written once and read twice. Every test below runs the real settler
next to the report and asserts they agree.

Run directly: `python3 tests/test_the_doctor_asks_the_settler.py`
"""

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db as hist_db                                # noqa: E402
from engine import ledger                                       # noqa: E402

TODAY = _dt.date.today().isoformat()
OLD = "2026-07-24"          # firmly past, so the strict window is off


def _conn():
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    return conn


def _moneyline(conn, pick="NYY", date=OLD):
    ledger.log_recommendations(conn, {
        "sport": "mlb", "date": date, "recommendations": [],
        "game_bets": [{"bet_type": "moneyline", "recommended": True,
                       "pick": pick, "odds": -125, "win_prob": 0.6,
                       "edge": 0.04, "confidence": 6.0, "grade": "Play",
                       "stake_units": 1.0}]})


def _game(gid, home_score, away_score, date=OLD, home="NYY", away="BOS"):
    return {"sport": "mlb", "season": 2026, "period": date, "game_id": gid,
            "home": home, "away": away, "home_score": home_score,
            "away_score": away_score, "spread": 0.0, "total": None,
            "roof": "open", "surface": "grass", "temp": None, "wind": None,
            "extra": ""}


def _reasons(conn, hist):
    return [r["reason"] for r in ledger.why_open(conn, hist, TODAY)]


def _settles(conn, hist):
    """How many rows a real settle pass closes. THE ARBITER — every
    claim below is checked against this, not against my reading."""
    return ledger.settle_from_history(conn, hist, sport="mlb")


# --- the case ----------------------------------------------------------
def test_a_half_final_doubleheader_is_not_called_gradeable():
    """THE BUG. One leg final, one not. `_pick_dh_game` waits on
    purpose; the doctor said the settler should have graded it."""
    conn = _conn()
    _moneyline(conn)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [_game("g1", 5, 3), _game("g2", None, None)])
    reasons = _reasons(conn, hist)
    assert reasons == ["waiting on the rest of the day"], reasons
    assert _settles(conn, hist) == 0, \
        "the settler did not grade it — so the doctor must not say it did"


def test_the_same_bet_becomes_gradeable_when_the_day_finishes():
    """And the wait has to END, or the new label is just a nicer way of
    losing the bet."""
    conn = _conn()
    _moneyline(conn)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [_game("g1", 5, 3), _game("g2", None, None)])
    hist.execute("UPDATE games SET home_score=7, away_score=1 "
                 "WHERE game_id='g2'")
    assert _reasons(conn, hist) == ["gradeable now"]
    assert _settles(conn, hist) == 1


def test_a_split_doubleheader_is_named_as_voiding_not_as_gradeable():
    """Both legs final, opposite outcomes: there is no honest grade, so
    the settler VOIDS. "gradeable now" invited a settle pass that would
    never produce a win or a loss."""
    conn = _conn()
    _moneyline(conn)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [_game("g1", 5, 3), _game("g2", 1, 9)])
    assert _reasons(conn, hist) == ["voids on the next pass"]
    # The settler counts a void as handled, and the row leaves the book.
    assert _settles(conn, hist) == 1
    assert conn.execute(
        "SELECT status FROM bets").fetchone()[0] == "void"


def test_a_doubleheader_that_agrees_with_itself_is_gradeable():
    """Both legs final, same outcome either way — the settler grades it,
    so the doctor must say so."""
    conn = _conn()
    _moneyline(conn)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [_game("g1", 5, 3), _game("g2", 7, 1)])
    assert _reasons(conn, hist) == ["gradeable now"]
    assert _settles(conn, hist) == 1


# --- the ordinary cases still read the same ----------------------------
def test_a_single_final_game_is_still_gradeable():
    conn = _conn()
    _moneyline(conn)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [_game("g1", 5, 3)])
    assert _reasons(conn, hist) == ["gradeable now"]
    assert _settles(conn, hist) == 1


def test_a_day_with_no_final_at_all_is_not_gradeable():
    conn = _conn()
    _moneyline(conn)
    hist = hist_db.connect(":memory:")
    hist_db.upsert_games(hist, [_game("g1", None, None)])
    assert "gradeable now" not in _reasons(conn, hist)
    assert _settles(conn, hist) == 0


def test_a_day_with_nothing_ingested_is_not_gradeable():
    conn = _conn()
    _moneyline(conn)
    hist = hist_db.connect(":memory:")
    assert _reasons(conn, hist) == ["no results ingested"]
    assert _settles(conn, hist) == 0


# --- nothing may be called gradeable that the settler refuses ----------
def test_no_reported_gradeable_bet_ever_survives_a_settle_pass():
    """The invariant, over every shape above at once: whatever the
    doctor files under "gradeable now" must be gone after one pass."""
    conn = _conn()
    hist = hist_db.connect(":memory:")
    for i, games in enumerate((
            [_game("a1", 5, 3)],                      # single final
            [_game("b1", 5, 3), _game("b2", None, None)],   # half done
            [_game("c1", 5, 3), _game("c2", 7, 1)],   # agree
            [_game("d1", 5, 3), _game("d2", 1, 9)],   # disagree
            [_game("e1", None, None)])):              # nothing final
        date = f"2026-07-0{i + 1}"
        _moneyline(conn, date=date)
        hist_db.upsert_games(hist, [dict(g, period=date) for g in games])
    before = {r["id"]: r["reason"] for r in ledger.why_open(conn, hist, TODAY)}
    said_ready = {i for i, why in before.items() if why == "gradeable now"}
    assert said_ready, "nothing was called gradeable — the test proves nothing"
    ledger.settle_from_history(conn, hist, sport="mlb")
    still = {r["id"] for r in conn.execute(
        "SELECT id FROM bets WHERE status='open'")}
    assert not (said_ready & still), \
        f"called gradeable and still open: {sorted(said_ready & still)}"


def test_the_doctor_calls_the_settlers_own_decider():
    src = (os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "ledger.py"))
    with open(src, encoding="utf-8") as fh:
        led = fh.read()
    body = led[led.index("def why_open("):]
    body = body[:body.index("\ndef ", 10)]
    assert "_pick_dh_game(rows_g, b, actual_fn)" in body, \
        "why_open is re-deriving the settler's answer again"


def test_every_reason_the_doctor_can_print_has_advice():
    """A reason with no entry in the tips table prints 'unknown', which
    is how a reader learns nothing from a report built to explain."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "launch.py"), encoding="utf-8") as fh:
        lp = fh.read()
    for reason in ("gradeable now", "waiting on the rest of the day",
                   "voids on the next pass", "no results ingested",
                   "day barely ingested", "game not found"):
        assert f'"{reason}":' in lp, f"{reason} has no advice line"


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
