"""A posted Most Likely pick is locked until kickoff.

Ethan, 2026-09-25: "it still seems like picks on the most likley board and
page are dissapearing and new props are replacing them. we cant let that be
a plroblem ever ever ever." And: "I'm starting to think that the pics
probably disappeared from the board ... For St. Brown and Laporta and Gibbs."

The seat hold (HELD_SEATS) stopped newcomers pushing a posted pick off,
but a posted pick still left the moment it failed any bar on a later
build — the commonest being its price ticking past -250, which is the book
agreeing with it. Now only its game starting or its player being ruled out
takes it down (`likely.hard_exit`); anything else keeps it up exactly as it
went up, "Locked in", with what changed. The main page orders a shelf by
when each pick went up, so a newcomer cannot push one off the dashboard.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as K                                     # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
LEDGER = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_only_the_game_and_the_players_status_take_a_pick_down():
    for why in ("the game is already under way", "the game has already been played",
                "its game started", "listed Out — held until inactives confirm",
                "listed Doubtful — held until inactives confirm", "listed IR — held until inactives confirm"):
        assert K.hard_exit(why), why
    for why in ("heavier than -250 — chalk, not a pick", "under the likelihood floor",
                "no longer offered", "no real market price", "a likelier pick took its seat",
                "the shown probability disagrees with the market by more than we credit",
                "listed Questionable — held until inactives confirm", "number moved"):
        assert not K.hard_exit(why), why


def test_every_soft_exit_says_what_changed():
    assert "moved past −250" in K.lock_note("heavier than -250 — chalk, not a pick")
    assert "under 55%" in K.lock_note("under the likelihood floor")
    assert "No book is quoting" in K.lock_note("no longer offered")
    assert K.lock_note("listed Questionable — held until inactives confirm") \
        == "Now listed questionable — check his status before kickoff."
    assert K.lock_note("a likelier pick took its seat") == "", "outranked is not news to a reader"


def test_a_crowd_of_likelier_picks_cannot_push_a_posted_one_off():
    old = {"kind": "prop", "player": "Posted", "team": "GB", "market": "rec_yds", "side": "OVER",
           "line": 40.5, "model_prob": 0.60, "odds": -140, "since": "2026-09-27T10:00:00Z",
           "kickoff": "2026-09-27T20:00:00Z"}
    new = [{"kind": "prop", "player": f"N{i}", "team": "T", "market": "rec_yds", "model_prob": 0.9 - i * 0.01,
            "odds": -150, "side": "OVER", "line": 30.5} for i in range(K.PER_MARKET * K.HELD_SEATS)]
    held = {K.hold_key(old): old}
    seated = {r["player"] for r in K._cut_players(new, K.PER_MARKET, held=held)}
    assert "Posted" not in seated, "the seat ceiling alone would drop it — which is why the lock exists"
    assert not K.hard_exit("a likelier pick took its seat")


def test_the_page_never_hides_a_locked_pick():
    assert "if ((r || {}).locked) return true;" in _fn("showableLikelyRow")
    assert '["Locked in", "", r.lock_note' in _fn("likelyTagsHTML")
    assert "r.locked && r.lock_note" in _fn("likelyCard")


def test_the_dashboard_keeps_what_it_showed():
    top = _fn("renderLikelyTop")
    assert "shelfByPosted((sh.rows || []).filter(showableLikelyRow))" in top
    order = _fn("shelfByPosted")
    assert "a.since" in order and "b.model_prob" in order
    assert "const LIKELY_TOP_N = 5;" in APP


def test_a_locked_pick_is_journaled_once():
    """Journaled when it went up, the lock never adds a second bet; posted
    under the old ten-row journal and never journaled, it journals now, at
    the number it went up at."""
    from engine import ledger
    posted = {"player": "Emanuel Wilson", "team": "GB", "market": "rush_yds", "side": "over",
              "line": 9.5, "odds": -240, "book": "DraftKings", "model_prob": 0.74,
              # A kickoff still ahead, whenever this runs: the journal
              # refuses a game under way by the clock.
              "game_date": "2099-09-24", "kickoff": "20:15"}
    lock = K._locked(posted, "number moved", "2099-09-24T20:00:00Z")
    conn = ledger.connect(":memory:")
    board = {"sport": "nfl", "date": "2026-W03", "most_likely": [lock]}
    assert ledger.log_most_likely(conn, board) == 1, "never journaled: it journals now"
    assert ledger.log_most_likely(conn, board) == 0, "already in the book: never a second bet"
    got = dict(conn.execute("SELECT odds, line, side FROM bets").fetchone())
    assert got == {"odds": -240, "line": 9.5, "side": "OVER"}, got


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
