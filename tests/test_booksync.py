"""Syncing a sportsbook into a book somebody keeps by hand.

Ethan, 2026-08-23: *"you only have to log onto your sports book once then
every time you log onto the app after that it automatically syncs the
bets from those accounts."*

Every test here is about the SECOND sync, because the first one into an
empty book is trivial and no bug has ever lived there. The failures that
matter are a bet counted twice, a graded bet pushed back to pending, and
a correction somebody typed being overwritten by the next pull.

    python3 tests/test_booksync.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import booksync as bs                              # noqa: E402


def slip(sid, desc="Aaron Judge Over 1.5 Total Bases", risk=25.0,
         odds=-110, status="pending", placed="2026-08-20T23:14:02Z", **kw):
    """A SharpSports BetSlip, using their documented field names."""
    out = {"id": sid, "bookDescription": desc, "atRisk": risk,
           "oddsAmerican": odds, "status": status, "placedAt": placed}
    out.update(kw)
    return out


def typed(desc="Judge o1.5 TB", stake=25.0, odds=-110, book="FanDuel",
          date="2026-08-20", result="pending"):
    """A row the user entered by hand on the My Bets page."""
    return {"id": "local-1", "book": book, "sport": "mlb", "date": date,
            "desc": desc, "stake": stake, "odds": odds, "result": result}


# --- the shape ---------------------------------------------------------------
def test_a_slip_becomes_a_row_the_page_already_understands():
    r = bs.normalize(slip("bs_1"), book="FanDuel")
    assert r["book"] == "FanDuel" and r["date"] == "2026-08-20"
    assert r["stake"] == 25.0 and r["odds"] == -110
    assert r["result"] == "pending" and r["ext_id"] == "bs_1"
    assert r["src"].startswith(bs.SRC_PREFIX)


def test_the_book_s_own_words_are_used_when_it_gives_them():
    """SharpSports' guidance is that bookDescription is always present
    while the structured breakdown may not be. A mapper that insists on
    event/market/selection drops exactly the bets hardest to rebuild by
    hand."""
    r = bs.normalize(slip("bs_2", desc="Judge 1+ HR"), book="DK")
    assert r["desc"] == "Judge 1+ HR"


def test_a_slip_with_no_words_is_described_from_its_legs():
    r = bs.normalize(slip("bs_3", desc="", bets=[
        {"proposition": "Judge", "position": "Over", "line": "1.5"},
        {"proposition": "Soto", "position": "Over", "line": "0.5"}]), book="DK")
    assert "Judge" in r["desc"] and "Soto" in r["desc"] and "+" in r["desc"]


def test_a_slip_with_no_money_or_no_price_is_dropped_not_defaulted():
    """A zero-stake row would sit in somebody's book looking like a real
    wager they had forgotten about."""
    assert bs.normalize(slip("x", risk=0)) is None
    assert bs.normalize(slip("x", risk=None)) is None
    assert bs.normalize(slip("x", odds=None)) is None
    assert bs.normalize({"id": "x"}) is None
    assert bs.normalize("not a slip") is None


def test_an_unknown_status_stays_pending_rather_than_being_guessed():
    """It is a bet whose result we do not know, which is what pending
    means. Guessing it into a win or a loss puts a number in somebody's
    P&L that nothing measured."""
    assert bs.normalize(slip("x", status="settled_somehow"))["result"] == "pending"
    assert bs.normalize(slip("x", status="WON"))["result"] == "won"
    assert bs.normalize(slip("x", status="voided"))["result"] == "push"


def test_the_day_is_kept_and_the_instant_is_not():
    """My Bets is a daily book and the user's own rows carry a date.
    Keeping the time would make every imported row fail an accounting
    match against the row they typed for the same bet."""
    assert bs.normalize(slip("x", placed="2026-08-20T23:14:02Z"))["date"] \
        == "2026-08-20"


# --- the second sync ---------------------------------------------------------
def test_syncing_twice_does_not_double_the_book():
    """The whole feature, in one assertion. This runs on every app open."""
    slips = [slip("a"), slip("b", desc="Soto o0.5 HR", risk=10.0, odds=250)]
    once = bs.merge([], slips, book="FanDuel")
    twice = bs.merge(once["rows"], slips, book="FanDuel")
    assert once["added"] == 2
    assert twice["added"] == 0 and len(twice["rows"]) == 2
    assert bs.merge(twice["rows"], slips, book="FanDuel")["added"] == 0


def test_a_bet_the_user_already_typed_is_claimed_rather_than_duplicated():
    """THE ONE THAT MATTERS. They logged it on their phone before the
    sync ran. `bet_sig` keys on the description, and a person writes
    "Judge o1.5 TB" where the book writes "Aaron Judge Over 1.5 Total
    Bases" — so a description-keyed merge puts a second copy of every
    bet in the book, silently doubling their staked total and halving
    their apparent ROI."""
    book = [typed()]
    out = bs.merge(book, [slip("bs_9")], book="FanDuel")
    assert out["matched"] == 1 and out["added"] == 0
    assert len(out["rows"]) == 1
    row = out["rows"][0]
    assert row["ext_id"] == "bs_9", "the row was not claimed by the import"
    assert row["desc"] == "Judge o1.5 TB", "the user's own words were replaced"


def test_a_claimed_bet_is_not_claimed_a_second_time_by_another_slip():
    """Two different wagers can share a date, book, stake and price — a
    parlay and a straight at −110 for $25 on the same night. The second
    slip must land as its own row rather than overwriting the first."""
    out = bs.merge([typed()], [slip("bs_1"), slip("bs_2", desc="Soto o0.5")],
                   book="FanDuel")
    assert out["matched"] == 1 and out["added"] == 1
    assert len(out["rows"]) == 2
    assert {r["ext_id"] for r in out["rows"]} == {"bs_1", "bs_2"}


def test_a_bet_that_grades_between_syncs_is_updated_in_place():
    first = bs.merge([], [slip("a")], book="FanDuel")
    second = bs.merge(first["rows"], [slip("a", status="won", payout=47.73)],
                      book="FanDuel")
    assert second["added"] == 0 and second["updated"] == 1
    assert second["rows"][0]["result"] == "won"
    assert second["rows"][0]["payout"] == 47.73


def test_a_settled_bet_is_never_pushed_back_to_pending():
    """A sync running while the book is mid-grading would otherwise
    un-settle a bet the user has already watched resolve, which reads as
    the site losing their money."""
    won = bs.merge([], [slip("a", status="won")], book="FanDuel")["rows"]
    out = bs.merge(won, [slip("a", status="pending")], book="FanDuel")
    assert out["rows"][0]["result"] == "won"


def test_a_correction_the_user_typed_survives_the_next_sync():
    """A sync that overwrites a human edit teaches people not to correct
    anything, and then the book is wrong AND nobody is fixing it."""
    rows = bs.merge([], [slip("a")], book="FanDuel")["rows"]
    rows[0]["desc"] = "Judge TB over — my note"
    rows[0]["sport"] = "mlb"
    out = bs.merge(rows, [slip("a", status="lost")], book="FanDuel")
    assert out["rows"][0]["desc"] == "Judge TB over — my note"
    assert out["rows"][0]["sport"] == "mlb"
    assert out["rows"][0]["result"] == "lost", "the book still decides results"


def test_the_book_decides_the_money_and_the_user_decides_the_words():
    rows = bs.merge([], [slip("a", risk=25.0)], book="FanDuel")["rows"]
    rows[0]["desc"] = "mine"
    out = bs.merge(rows, [slip("a", risk=30.0, odds=-120)], book="FanDuel")
    assert out["rows"][0]["stake"] == 30.0 and out["rows"][0]["odds"] == -120
    assert out["rows"][0]["desc"] == "mine"


def test_an_unusable_slip_is_counted_rather_than_silently_dropped():
    out = bs.merge([], [slip("a"), slip("b", risk=0), {}], book="FanDuel")
    assert out["added"] == 1 and out["skipped"] == 2


def test_rows_that_are_not_rows_cannot_break_a_sync():
    """The book comes off a user profile, which is data from a client."""
    out = bs.merge(["nonsense", None, {"desc": "x"}], [slip("a")],
                   book="FanDuel")
    assert out["added"] == 1
    assert all(isinstance(r, dict) for r in out["rows"])


def test_nothing_here_reaches_the_network_or_sees_a_credential():
    """The fetch lives in its own module. This one is pure so it can be
    tested exhaustively, and so a sync bug can never be a leak."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "booksync.py"),
        encoding="utf-8").read()
    for bad in ("import requests", "urlopen", "http", "socket", "API_KEY",
                "password", "token"):
        assert bad not in src.lower().replace("sportsbook", ""), bad


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
