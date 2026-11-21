"""The members' closing-line leaderboards (engine/closeboard, engine/betclv,
GET /api/feed/closeboard, js/account.js mbBoardHTML, Settings' switch).

Ethan, 2026-10-29: "approve all. and build leaderboards". A board ranks each
member's average price against the close over their saved parlays' legs:
the honest measure of a bet before its result, never profit. What these
hold, because a public table invites gaming and a private one did not:

  * a leg's price is the member's own synced log, so it counts only up to
    the best price the books showed when the box first saw it, and only
    once the box saw its game start with the parlay still saved (a parlay
    deleted mid-move would freeze a flattering "close");
  * only members who put themselves on it, with a username; a block hides
    both ways; Friends is the viewer and their friends; a minimum of legs
    to be ranked, and the viewer told how many more they need;
  * nothing at all until both locks open: QB_CLOSEBOARD=1 and the Privacy
    Policy's section (id="close-board");
  * on and off goes in the consent log, and the page draws the board and
    the switch only while the site keeps one.

Run directly: `python3 tests/test_the_closing_line_leaderboards.py`
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("QB_CLOSEBOARD", None)

from engine import betclv as BC                                   # noqa: E402
from engine import closeboard as CB                               # noqa: E402
from engine import social as SC                                   # noqa: E402
from engine import socialfeed as SF                               # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOW = 1_793_304_000.0                                             # Thursday 2026-10-29, 16:00 Eastern


class _Locks:
    def __init__(self, switch=True, section=True):
        self.switch, self.section = switch, section

    def __enter__(self):
        self.old = (os.environ.get(CB.ENV), CB.POLICY)
        if self.switch:
            os.environ[CB.ENV] = "1"
        else:
            os.environ.pop(CB.ENV, None)
        p = Path(tempfile.mkdtemp()) / "privacy.html"
        p.write_text(f'<h3 id="{CB.POLICY_ID}">The board</h3>' if self.section else "<h3>No</h3>")
        CB.POLICY = p
        return self

    def __exit__(self, *exc):
        env, CB.POLICY = self.old
        if env is None:
            os.environ.pop(CB.ENV, None)
        else:
            os.environ[CB.ENV] = env


def _db(*handles):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE user_data (user_id INTEGER, section TEXT, ts INTEGER, payload TEXT, "
              "PRIMARY KEY (user_id, section))")
    SF.ensure_tables(c)
    SC.ensure_tables(c)
    BC.ensure_tables(c)
    for i, h in enumerate(handles, 1):
        if h:
            assert SF.profile_set(c, i, h, "")[0] == 200
    return c


def _on(c, uid, on=True):
    c.execute("INSERT OR REPLACE INTO user_data VALUES (?, 'settings', 1, ?)",
              (uid, json.dumps({CB.KEY: "on" if on else "off", "odds": "american"})))


def _legs(c, uid, n, entry=-110, first=-110, fair=0.55, closed=NOW - 3600, start=0):
    """n closed legs: priced at ``entry``, first seen at ``first``, closing
    at ``fair`` (a -110 that closes at 55% is worth +5%)."""
    c.executemany("INSERT INTO bet_clv (user_id, bet_id, leg, entry, best, fair, at, first_best, first_at, closed) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  [(uid, f"b{uid}-{start + i}", 0, entry, -125, fair, closed - 60, first, closed - 86400, closed)
                   for i in range(n)])


def test_a_leg_keeps_the_first_price_it_was_seen_at_and_its_start():
    c = _db()
    leg = {"odds": "+150", "price": {"best": "+140", "fair": 0.40}, "live": {"state": "pre"}}
    assert BC.note(c, 1, "s1", {"legs": [leg]}, NOW - 7200) == 1
    leg["price"] = {"best": "+120", "fair": 0.45}
    BC.note(c, 1, "s1", {"legs": [leg]}, NOW - 3600)
    r = c.execute("SELECT entry, best, fair, first_best, first_at, closed FROM bet_clv").fetchone()
    assert tuple(r) == (150.0, 120.0, 0.45, 140.0, NOW - 7200, None), tuple(r)
    leg["live"] = {"state": "live"}
    assert BC.note(c, 1, "s1", {"legs": [leg]}, NOW) == 1, "the start, marked once"
    assert BC.note(c, 1, "s1", {"legs": [leg]}, NOW + 60) == 0
    assert c.execute("SELECT closed, best FROM bet_clv").fetchone()[:] == (NOW, 120.0), "the close stays the last pre-game"
    # The price a board counts: the price taken, never better than the first one seen.
    assert BC.verified_entry(150, 140) == 140 and BC.verified_entry(130, 140) == 130
    assert BC.verified_entry(-105, -110) == -110 and BC.verified_entry(None, -110) == -110
    assert BC.verified_entry(150, None) is None, "nothing to check it against: not counted"


def test_the_board_ranks_members_who_put_themselves_on_it():
    c = _db("amy", "bob", "cal", None, "eve")
    for uid in (1, 2, 3, 4, 5):
        _on(c, uid)
    _on(c, 3, on=False)                                  # cal took himself off
    _legs(c, 1, 6, fair=0.56)                            # amy: -110 closing at 56%: +6.9%
    _legs(c, 2, 6, entry=+200, first=-110, fair=0.55)    # bob claims +200; the books showed -110
    _legs(c, 3, 9, fair=0.60)                            # off the board
    _legs(c, 4, 9, fair=0.60)                            # no username
    _legs(c, 5, 4, fair=0.70)                            # under the week's minimum
    _legs(c, 5, 30, fair=0.70, closed=NOW - 20 * 86400, start=10)    # last month: the 90 days only
    with _Locks():
        week = CB.board(c, "week", viewer=5, now=NOW)
        assert [(r["handle"], r["n"]) for r in week["rows"]] == [("amy", 6), ("bob", 6)], week["rows"]
        assert week["rows"][0]["clv"] == round((1.9090909 * 0.56 - 1) * 100, 1)
        assert week["rows"][1]["clv"] == round((1.9090909 * 0.55 - 1) * 100, 1), "capped at the price on offer"
        assert week["me"] == {"n": 4, "beat": 4, "clv": week["me"]["clv"], "need": 1} and week["on"]
        ninety = CB.board(c, "90d", viewer=5, now=NOW)
        assert [r["handle"] for r in ninety["rows"]] == ["eve"] and ninety["rows"][0]["me"]
        assert ninety["min"] == CB.MIN["90d"] and ninety["rows"][0]["n"] == 34
        assert not CB.board(c, "week", viewer=3, now=NOW)["on"], "off is off"
        assert "LeBron" not in json.dumps(week) and "stake" not in json.dumps(week)


def test_friends_and_blocks():
    c = _db("amy", "bob", "cal")
    for uid in (1, 2, 3):
        _on(c, uid)
        _legs(c, uid, 6, fair=0.50 + uid / 100)
    c.executemany("INSERT INTO friendships VALUES (?, ?, ?)", [(1, 2, NOW), (2, 1, NOW)])
    with _Locks():
        mine = CB.board(c, "week", viewer=1, scope="friends", now=NOW)
        assert sorted(r["handle"] for r in mine["rows"]) == ["amy", "bob"] and mine["scope"] == "friends"
        c.execute("INSERT INTO feed_blocks (user_id, blocked_id, created_at) VALUES (3, 1, ?)", (NOW,))
        assert [r["handle"] for r in CB.board(c, "week", viewer=1, now=NOW)["rows"]] == ["bob", "amy"], \
            "a block hides both ways"


def test_nothing_until_both_locks_open_and_choices_are_written_down():
    c = _db("amy")
    _on(c, 1)
    _legs(c, 1, 9)
    assert CB.board(c, "week", viewer=1, now=NOW) == {"enabled": False}
    with _Locks(switch=True, section=False):
        assert CB.board(c, "week", viewer=1, now=NOW) == {"enabled": False}, "the switch alone does nothing"
    with _Locks(switch=False, section=True):
        assert not CB.enabled()
    with _Locks():
        assert CB.board(c, "week", viewer=1, now=NOW)["enabled"]
    assert CB.changed({}, {CB.KEY: "on"}) == "on the closing-line leaderboard"
    assert CB.changed({CB.KEY: "on"}, {CB.KEY: "off"}) == "off the closing-line leaderboard"
    assert CB.changed(None, {"odds": "decimal"}) is None
    from engine import consent as CS
    assert "closeboard" in CS.KINDS


def test_the_server_the_page_and_the_policy():
    srv = READ("server.py")
    assert 'if path == "closeboard":' in srv and 'CB.board(conn, one("window", "week")[:4], uid,' in srv
    assert 'if said and CS.record(conn, who["id"], "closeboard", said):' in srv
    assert 'out["closeboard_switch"] = CB.enabled()' in srv
    acct = READ("web", "js", "account.js")
    for want in ("function mbBoardHTML(v)", "async function mbBoardFill()", 'data-cb="join"', 'data-cb="leave"',
                 "/api/feed/closeboard?window=", "_pwStatus.closeboard_switch", 'data-set-switch="closeboard"',
                 "never a reason to bet more", '  mbEdgeFill();\n  mbBoardFill();\n}'):
        assert want in acct, want
    # A switch flips from what it shows: the split's first tap used to set "on" again.
    assert 'setSetting(k, flip.getAttribute("aria-checked") === "true" ? "off" : "on");' in acct
    policy = " ".join(READ("web", "privacy.html").split())
    assert f'id="{CB.POLICY_ID}"' in policy and CB.policy_ready(ROOT / "web" / "privacy.html")
    assert "Never a bet, a team, a player, a stake or a result" in policy
    assert "the best price the books showed when we first saw it" in policy
    terms = " ".join(READ("web", "terms.html").split())
    assert "standings and the closing-line leaderboard" in terms
    assert 'CREATE TABLE' not in READ("engine", "closeboard.py"), "nothing new is kept for it"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
