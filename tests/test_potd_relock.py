"""The Pick of the Day lock was a veto, not a memory.

Ethan, 2026-09-15, looking at the MLB page in the evening: "the mlb is
still showing the angles +1.5 as the pick of the day. idk if thats right
or it should have been replaced."

It was not right. That morning `log_pick_of_the_day` had locked Spencer
Jones OVER 0.5 total bases — the first qualifying pick of the day, which
is by design the day's pick and cannot be replaced. By the evening his
price had run from inside the even-money band out to -180, `potd.choose`
refused him on price like any other row, and `potd.build` fell through
to its best-available lean, LAA +1.5. So the page showed one pick, the
record held another, and nothing anywhere connected the two.

WHAT THE LOCK COULD AND COULD NOT DO. `locked_potd_keys` returns the
tuple a pick is journaled under, which is enough to REFUSE the board's
new favourite — `day_top_pick` did exactly that, correctly — and not
enough to SHOW the old one. A key is not a card. So the refusal had
nowhere to land and the day fell through to a below-bar lean, which is
exempt from locking precisely because nothing journals it. An unrecorded
lean displacing a recorded claim is the churn the lock exists to stop,
arriving through the one door the lock did not cover.

TWO SOURCES, IN ORDER. The board row is preferred: it carries TODAY's
price and it carries which witness stood behind the fair, and the
journal stores neither (it stores what a bet needs to settle). The
journal is the fallback for the day the row really does leave the board.

Run directly: `python3 tests/test_potd_relock.py`
"""

import datetime
import io
import contextlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger, potd                               # noqa: E402


def _today() -> str:
    """From the clock, never a literal. `relock_potd` keys on the journal
    day, so a frozen date here would pass or fail by the calendar."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def _journal():
    """A throwaway journal. The suite must not read the box it runs on."""
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "ledger.db"))


def _locked_row(odds=-140):
    """The pick as it was when it qualified this morning — inside the
    band, with a sharp book behind the fair."""
    return {"player": "Spencer Jones", "market": "total_bases",
            "side": "OVER", "line": 0.5, "odds": odds, "book": "FanDuel",
            "sharp_anchored": True, "sharp_fair": 0.64, "fair_prob": 0.64,
            "implied_prob": 0.62, "model_prob": 0.66,
            "game_date": _today()}


def _lean():
    """The below-bar row `build` falls through to. Shown, never recorded."""
    return {"player": "LAA", "market": "spread", "side": "OVER",
            "line": 1.5, "odds": -113, "book": "DraftKings",
            "model_prob": 0.593, "fair_prob": 0.593,
            "below_bar": "only our own model disputes this price"}


def _with_lock(odds=-140):
    """A journal holding this morning's lock, and the payload the evening
    board published: the lean, because the locked row priced out."""
    conn = _journal()
    n = ledger.log_pick_of_the_day(
        conn, {"sport": "mlb", "date": _today(), "pick": _locked_row(odds)})
    assert n == 1, "the fixture failed to lock anything"
    return conn, {"sport": "mlb", "date": _today(), "pick": _lean()}


# ── the case Ethan was looking at ───────────────────────────────────

def test_the_locked_pick_comes_back_when_the_board_moves_on():
    conn, payload = _with_lock()
    out = ledger.relock_potd(payload, [_locked_row(-180), _lean()], conn=conn)
    assert out["pick"]["player"] == "Spencer Jones", out["pick"]
    assert out["pick"]["locked"] is True
    assert not out["pick"].get("below_bar"), "a lock is not a lean"
    assert "locked earlier today" in out.get("relocked", "")


def test_it_comes_back_at_TONIGHT_s_price_not_this_morning_s():
    """The claim was made at -140 and the market has moved to -180. The
    card is what a reader can act on now, so it shows the live number;
    the price it was taken at is the journal's job, and the record page
    reads that. Showing -140 here would be quoting a price nobody can
    get."""
    conn, payload = _with_lock(odds=-140)
    out = ledger.relock_potd(payload, [_locked_row(-180), _lean()], conn=conn)
    assert out["pick"]["odds"] == -180, out["pick"]["odds"]


def test_the_witness_survives_the_round_trip():
    """The whole reason the board row is preferred over the journaled
    one. `bets` has no column for which witness stood behind the fair,
    so a card rebuilt from the journal would have to say "model" about a
    pick that qualified on a sharp book — understating it in the one
    field the selector is built on."""
    conn, payload = _with_lock()
    out = ledger.relock_potd(payload, [_locked_row(-180), _lean()], conn=conn)
    assert out["pick"]["evidence"] == "sharp", out["pick"]["evidence"]
    assert out["pick"]["fair_prob"] == 0.64


def test_the_lean_does_not_survive_as_the_pick():
    """The negative half, stated on its own so it cannot be satisfied by
    a card that carries both."""
    conn, payload = _with_lock()
    out = ledger.relock_potd(payload, [_locked_row(-180), _lean()], conn=conn)
    assert out["pick"]["player"] != "LAA", out["pick"]


# ── the other three states ──────────────────────────────────────────

def test_a_card_already_showing_the_lock_is_only_labelled():
    """The ordinary case all day: the board still likes what it locked.
    Nothing is swapped, but the card says it is the day's lock, so the
    page does not have to infer that from the record page."""
    conn, _ = _with_lock()
    row = _locked_row(-135)
    payload = {"sport": "mlb", "date": _today(), "pick": row}
    out = ledger.relock_potd(payload, [row], conn=conn)
    assert out["pick"]["player"] == "Spencer Jones"
    assert out["pick"]["locked"] is True
    assert "relocked" not in out, "nothing moved; there is nothing to explain"


def test_nothing_locked_yet_leaves_the_card_exactly_as_it_was():
    """The first cycle of every day, and every day a sport has no pick.
    A lock that changed the card before one existed would be inventing
    one."""
    conn = _journal()
    payload = {"sport": "mlb", "date": _today(), "pick": _lean()}
    out = ledger.relock_potd(payload, [_lean()], conn=conn)
    assert out["pick"]["player"] == "LAA"
    assert out["pick"].get("below_bar")
    assert "relocked" not in out


def test_a_locked_row_that_has_left_the_board_is_read_from_the_journal():
    """A row can genuinely go — the game starts, the book pulls the
    market. The claim still stands, so the card shows it at the price it
    was locked at and says where the number came from."""
    conn, payload = _with_lock(odds=-140)
    out = ledger.relock_potd(payload, [_lean()], conn=conn)
    assert out["pick"]["player"] == "Spencer Jones"
    assert out["pick"]["off_board"] is True
    assert out["pick"]["odds"] == -140, "the journaled price, there being no other"
    assert "from the journal" in out.get("relocked", "")


def test_a_lock_with_no_row_anywhere_blanks_the_card_rather_than_lying():
    """The last state, and the one worth being deliberate about: if the
    locked pick can be found neither on the board nor in the journal,
    the answer is not the lean underneath it. The sport has a claim on
    today's record; a card showing something else would put the page and
    the record into silent disagreement, which is the whole bug."""
    out = potd.relock({"sport": "mlb", "pick": _lean()}, [_lean()],
                      ("Ghost", "total_bases", "OVER", 0.5))
    assert out["pick"] is None, out["pick"]
    assert "no longer on the board" in out.get("relocked", "")


# ── the contract around it ──────────────────────────────────────────

def test_the_two_lock_readers_cannot_disagree():
    """`locked_potd_keys` answers "is the board still showing what it
    claimed" and `locked_potd_picks` answers "what did it claim". Two
    derivations of one tuple is how one book ends up right and another
    wrong, so the keys reader is now built FROM the picks reader."""
    conn, _ = _with_lock()
    keys = ledger.locked_potd_keys(conn, _today())
    picks = ledger.locked_potd_picks(conn, _today())
    assert set(keys) == set(picks)
    for sport, key in keys.items():
        assert tuple(key) == tuple(picks[sport]["_key"]), sport


def test_a_dead_journal_returns_the_card_unchanged_and_says_so():
    """It runs inside a build. A build must not die because the journal
    was busy — and a card that silently vanished on a locked database
    would look exactly like a day with no pick, which is the failure
    shape this repository keeps finding."""
    class _Dead:
        def execute(self, *a, **k):
            raise RuntimeError("database is locked")
    payload = {"sport": "mlb", "date": _today(), "pick": _lean()}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = ledger.relock_potd(payload, [_lean()], conn=_Dead())
    assert out["pick"]["player"] == "LAA", "the card was blanked"
    assert "lock not applied" in buf.getvalue(), buf.getvalue()


def test_the_read_only_opener_does_not_create_the_tables():
    """`connect` runs the schema and a column migration on every call.
    That is right for a writer and pure cost for a reader — and on a box
    already failing on "database is locked", a sixth process taking DDL
    locks is the opposite of help. A reader that silently created an
    empty `bets` would also turn "the journal is not where you think it
    is" into "there are no picks today"."""
    path = os.path.join(tempfile.mkdtemp(), "empty.db")
    conn = ledger.read_only(path)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "bets" not in names, names
    # And a caller reading that database gets "no answer", not a crash.
    conn = ledger.read_only(path)
    try:
        assert ledger.locked_potd_picks(conn, _today()) == {}
    finally:
        conn.close()


def test_every_build_relocks_BEFORE_it_publishes():
    """Pinned on the source, because the ordering is the fix. The journal
    is opened much further down each of these files, long after the board
    has been written — a swap made there would never reach the page, and
    that is precisely the shape of the bug."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Keyed on the PUBLISH OF THE BOARD THAT CARRIES THE PICK, by the
    # variable it is built in. nfl_build has an earlier `gate.publish`
    # for the pre-season shell — schedule, lines and weather, no props,
    # no pick of the day, and it returns immediately after — so the
    # first publish in the file is the wrong one to measure against.
    for name, pub in (("mlb_build.py", "gate.publish(result,"),
                      ("nfl_build.py", "gate.publish(result,"),
                      ("cfb_build.py", "gate.publish(out,"),
                      ("nba_build.py", "gate.publish(out,")):
        src = open(os.path.join(here, name), encoding="utf-8").read()
        assert "relock_potd(" in src, name
        assert pub in src, f"{name}: {pub} — the publish call moved"
        assert src.index("relock_potd(") < src.index(pub), \
            f"{name} publishes its board before honouring the day's lock"


if __name__ == "__main__":
    fails = ran = 0
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            try:
                _f(); ran += 1; print(f"  ok  {_n}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {_n}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {_n}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
