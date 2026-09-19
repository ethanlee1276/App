"""Tail or fade: the argument with the model, scored by the journal.

Roadmap #5 (Ethan): "Every recommendation gets two buttons: tail /
fade. Track each user's record against the model's."

The properties that carry it, pinned rather than trusted:

  * THE BOARD IS THE AUTHORITY. The browser names a player and a
    market; the served board decides the side, the line, whether it is
    recommended and whether the game started. A client-supplied side
    would let a caller invent a pick the model never made and beat it.
  * ONE JOURNAL SCORES BOTH SIDES. Calls settle from the same graded
    bet row the Results page shows, and the model's monthly record is
    read from the same table — the strip can never tell a story the
    Results page contradicts.
  * ACCOUNT PROMISES HOLD. Calls are deleted with the account and ride
    in its export, like every other thing we hold about a person.

Run directly: `python3 tests/test_tailfade.py`
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import ledger as L                               # noqa: E402
from engine import tailfade as TF                            # noqa: E402

GOOD = "correct-horse-battery"


def _accounts_db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    _, out = A.create_user(conn, "caller@example.com", GOOD, confirmed=True)
    TF.ensure_tables(conn)
    return conn, out["id"]


def _board(started=False):
    return {"date": "2026-09-13", "recommendations": [
        {"player": "Jahmyr Gibbs", "market": "rush_yds", "side": "OVER",
         "line": 88.5, "recommended": True, "live": started,
         "warnings": (["Game already started — x"] if started else [])},
        {"player": "Fringe Guy", "market": "rec_yds", "side": "UNDER",
         "line": 30.5, "recommended": False},
    ]}


def _ledger(status="won"):
    conn = L.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, "
        "book, odds, stake_units, stake_dollars, status, category) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-09-13T09:00:00", "nfl", "2026-09-13", "Jahmyr Gibbs",
         "rush_yds", "OVER", 88.5, "DraftKings", -110, 1.0, 0.0, status,
         "main"))
    conn.commit()
    return conn


# --- the board is the authority ---------------------------------------------

def test_only_recommended_picks_take_calls():
    conn, uid = _accounts_db()
    code, _ = TF.record_call(conn, uid, _board(), "nfl",
                             "Fringe Guy", "rec_yds", "tail")
    assert code == 404
    code, out = TF.record_call(conn, uid, _board(), "nfl",
                               "Jahmyr Gibbs", "rush_yds", "tail")
    assert code == 200
    # The SIDE comes from the board, never the caller.
    assert out["side"] == "OVER" and out["line"] == 88.5


def test_a_started_game_locks_its_calls():
    conn, uid = _accounts_db()
    code, out = TF.record_call(conn, uid, _board(started=True), "nfl",
                               "Jahmyr Gibbs", "rush_yds", "fade")
    assert code == 409 and "started" in out["error"]


def test_changing_and_clearing_before_start_is_free():
    conn, uid = _accounts_db()
    TF.record_call(conn, uid, _board(), "nfl", "Jahmyr Gibbs",
                   "rush_yds", "tail")
    code, out = TF.record_call(conn, uid, _board(), "nfl", "Jahmyr Gibbs",
                               "rush_yds", "fade")
    assert code == 200 and out["stance"] == "fade"
    n = conn.execute("SELECT COUNT(*) FROM tf_calls WHERE user_id=?",
                     (uid,)).fetchone()[0]
    assert n == 1, "a stance change duplicated the call"
    code, out = TF.record_call(conn, uid, _board(), "nfl", "Jahmyr Gibbs",
                               "rush_yds", "clear")
    assert code == 200 and out["cleared"]
    assert conn.execute("SELECT COUNT(*) FROM tf_calls WHERE user_id=?",
                        (uid,)).fetchone()[0] == 0


def test_junk_stances_are_refused():
    conn, uid = _accounts_db()
    code, _ = TF.record_call(conn, uid, _board(), "nfl", "Jahmyr Gibbs",
                             "rush_yds", "hedge")
    assert code == 400


# --- one journal scores both sides ------------------------------------------

def _called(stance):
    conn, uid = _accounts_db()
    TF.record_call(conn, uid, _board(), "nfl", "Jahmyr Gibbs",
                   "rush_yds", stance)
    return conn, uid


def test_a_tail_wins_when_the_pick_wins_and_a_fade_when_it_loses():
    for stance, pick, want in (("tail", "won", "won"),
                               ("tail", "lost", "lost"),
                               ("fade", "won", "lost"),
                               ("fade", "lost", "won"),
                               ("tail", "void", "void"),
                               ("fade", "void", "void")):
        conn, uid = _called(stance)
        assert TF.settle(conn, uid, _ledger(pick)) == 1
        row = conn.execute("SELECT status, result FROM tf_calls "
                           "WHERE user_id=?", (uid,)).fetchone()
        assert (row["status"], row["result"]) == ("settled", want), \
            f"{stance} vs pick {pick}: got {row['result']}, want {want}"


def test_an_open_pick_leaves_the_call_open():
    conn, uid = _called("tail")
    assert TF.settle(conn, uid, _ledger("open")) == 0
    assert conn.execute("SELECT status FROM tf_calls WHERE user_id=?",
                        (uid,)).fetchone()["status"] == "open"


def test_a_moved_line_is_still_the_same_pick():
    """The journal row's line and the call's can differ by a build — the
    join is (sport, date, player, market, side), and the settle stands."""
    conn, uid = _called("fade")
    led = _ledger("won")
    led.execute("UPDATE bets SET line=90.5")
    led.commit()
    assert TF.settle(conn, uid, led) == 1


def test_me_reports_both_records_from_one_source():
    conn, uid = _called("tail")
    led = _ledger("won")
    out = TF.me(conn, uid, led)
    assert out["month"]["tail"] == {"w": 1, "l": 0}
    assert out["month"]["fade"] == {"w": 0, "l": 0}
    # The model's month is read from the same bets table.
    assert out["model_month"] == {"w": 1, "l": 0}
    assert out["calls"] and out["calls"][0]["result"] == "won"


# --- the account promises hold here too -------------------------------------

def test_calls_die_with_the_account_and_ride_in_its_export():
    conn, uid = _called("tail")
    export = A.export_user(conn, uid)
    assert export["tail_fade_calls"][0]["player"] == "Jahmyr Gibbs"
    A.delete_user(conn, uid)
    assert conn.execute("SELECT COUNT(*) FROM tf_calls").fetchone()[0] == 0


# --- the wiring is real ------------------------------------------------------

def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_the_server_routes_exist_and_gate_entitlement():
    src = _read("server.py")
    for needle in ('"/api/tailfade/"', "_tailfade_get", "_tailfade_post"):
        assert needle in src, f"server.py lost {needle}"
    # With the paywall on, the call validator's own answers would map the
    # board one probe at a time for anyone signed in — entitlement first.
    seg = src[src.index("def _tailfade_post"):]
    seg = seg[:seg.index("def _streak_get")]
    assert "gate.enabled() and not self._entitled" in seg


def test_the_buttons_ride_on_recommended_cards_only():
    app = _read("web", "js", "app.js")
    assert "${tfRow(r)}" in app, "the card lost its tail/fade row"
    i = app.index("function tfRow(r)")
    body = app[i:app.index("\n}", i)]
    assert 'if (!r.recommended || r.live) return ""' in body
    assert 'id="tailfade-strip"' in _read("web", "index.html")


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
