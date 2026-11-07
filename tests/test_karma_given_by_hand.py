"""Karma and badges given by hand, to the owner's accounts.

Ethan, 2026-10-30: "we need to give both of my accounts high karma and alot
of badges" — "the founders account and the actual qellysbook account". The
site's own account earns nothing and stands on no ladder; given karma, it
wears its level in the chats like anybody. `python3 -m engine.karma grant
--to EMAIL …` gives an account
karma up to a mark (100,000 unless told: level 62, Legend) and every badge
at its top tier. Given karma is its own kind ("From Qellys"): it counts in
the account's level and badges and on no ladder and in no week's trophies,
so nobody who earned a place is moved down. Run again it tops up rather
than adding twice; `--undo` takes it all back. The emails are typed on the
box and never kept in the code (the fixtures use example.com).

Run directly: `python3 tests/test_karma_given_by_hand.py`
"""
import datetime as _dt
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts as A                             # noqa: E402
from engine import karma as K                                # noqa: E402
from engine import socialfeed as SF                          # noqa: E402

GOOD = "correct-horse-battery"
ET = ZoneInfo("America/New_York")
T0 = _dt.datetime(2026, 10, 28, 20, 0, tzinfo=ET).timestamp()       # a Wednesday evening


def _db():
    """The founder's account (``owner``), the site's own (``other``,
    verified, a qellys name) and a fan."""
    K._cache.clear()
    K._ready.clear()
    path = os.path.join(tempfile.mkdtemp(), "acc.db")
    conn = A.connect(path)
    SF.ensure_tables(conn)
    K.ensure_tables(conn)
    ids = []
    for who, handle in (("owner", "founder_e"), ("other", "site_acct"), ("fan", "fan")):
        _, out = A.create_user(conn, f"{who}@example.com", GOOD, confirmed=True)
        ids.append(out["id"])
        assert SF.profile_set(conn, out["id"], handle, "")[0] == 200, handle
    conn.execute("UPDATE feed_profiles SET founder=1, handle='owner' WHERE user_id=?", (ids[0],))
    conn.execute("UPDATE feed_profiles SET verified=1, handle='qellys_book' WHERE user_id=?", (ids[1],))
    conn.commit()
    assert K._house(conn) == ids[1]
    return conn, ids, path


def test_an_account_is_given_karma_and_every_badge():
    conn, (owner, other, fan), _ = _db()
    K.award(conn, owner, "chat_day", "d1", now=T0)
    got = K.grant(conn, owner, now=T0)
    assert got["before"] == 10 and got["after"] == K.GRANT_KARMA == 100_000, got
    assert got["level"] == K.level_of(100_000) == 62 and got["tier"] == "Legend", got
    assert got["badges"] == got["of"] == len(K.FAMILIES) + len(K.ONE_OFF), got
    rows = {b["key"]: b for b in K.badges(conn, owner)}
    for key, _n, _w, marks in K.FAMILIES:
        assert rows[key]["tier"] == len(marks) and rows[key]["next"] is None, key
        assert rows[key]["n"] >= marks[-1], key
    assert rows["nightowl"]["tier"] == 1 and rows["founding"]["tier"] == 1
    kinds = dict(conn.execute("SELECT kind, SUM(pts) FROM karma_events WHERE user_id=? GROUP BY kind", (owner,)))
    assert kinds == {"chat_day": 10, "grant": 99_990}, kinds
    assert K.RULES["grant"][2] == "From Qellys"
    # Nobody else is touched.
    assert K.total(conn, fan) == 0 and not any(b["tier"] for b in K.badges(conn, fan) if not b.get("one"))


def test_given_karma_moves_nobody_on_a_ladder():
    conn, (owner, other, fan), _ = _db()
    for i in range(6):
        K.award(conn, fan, "chat_day", f"d{i}", now=T0 + i)
    K.award(conn, owner, "chat_day", "d1", now=T0)
    K.grant(conn, owner, now=T0)
    for scope in ("week", "all"):
        K._cache.clear()
        lad = K.ladder(conn, scope, viewer=owner, now=T0 + 60)
        board = [(r["handle"], r["points"]) for r in lad["rows"]]
        assert board == [("fan", 60), ("owner", 10)], (scope, board)
        assert lad["mine"]["points"] == 10, (scope, "the owner's own place counts what was earned")
        assert lad["rows"][1]["level"] == 62, "the level the chats show is the given one"
    SF_friends = K.friends_ladder(conn, owner, now=T0 + 60)
    assert SF_friends["mine"]["points"] == 10
    # The finished week's trophies are worked out from earned karma only.
    week = K.week_of(T0)
    top = dict(K._week_results(conn, week))
    assert top[fan] == 1 and top[owner] == 2, top
    report = "\n".join(K.report(conn))
    assert "most karma earned: @fan 60" in report and "given by hand: 99,990 karma to 1 account(s)" in report


def test_the_sites_own_account_wears_its_given_level_and_stays_off_the_ladders():
    conn, (owner, house, fan), _ = _db()
    K.award(conn, house, "chat_day", "d1", now=T0)
    assert house not in K.cards(conn, {owner, house, fan}, now=T0), "no level until one is given"
    K.grant(conn, house, now=T0)
    K.grant(conn, owner, now=T0)
    K._cache.clear()
    cards = K.cards(conn, {owner, house, fan}, now=T0 + 1)
    assert cards[house]["lv"] == cards[owner]["lv"] == 62 and cards[house]["cls"] == "t7", cards
    assert cards[fan]["lv"] == 1
    assert K.public(conn, house)["level"] == 62 and len(K.public(conn, house)["badges"]) == 6
    for scope in ("week", "all"):
        K._cache.clear()
        handles = [r["handle"] for r in K.ladder(conn, scope, now=T0 + 60)["rows"]]
        assert "qellys_book" not in handles and "owner" not in handles, (scope, handles)


def test_again_tops_up_and_undo_takes_it_back():
    conn, (owner, *_), _ = _db()
    K.award(conn, owner, "chat_day", "d1", now=T0)
    K.grant(conn, owner, now=T0)
    K.award(conn, owner, "chat_day", "d2", now=T0 + 86400)
    again = K.grant(conn, owner, now=T0 + 86400)
    assert again["after"] == 100_000, ("topped up to the mark, not added twice", again)
    assert conn.execute("SELECT COUNT(*) FROM karma_events WHERE user_id=? AND kind='grant'",
                        (owner,)).fetchone()[0] == 1
    more = K.grant(conn, owner, karma=250_000, now=T0 + 86400)
    assert more["after"] == 250_000 and more["level"] == K.level_of(250_000)
    back = K.grant(conn, owner, undo=True, now=T0 + 86400)
    assert back["after"] == 20 and back["badges"] == 1, ("earned karma and the founding badge stay", back)
    assert K._given(conn, owner) == {}


def test_the_command_finds_each_account_by_its_email():
    conn, (owner, other, fan), path = _db()
    conn.close()
    saved = A.DB_PATH
    A.DB_PATH = path
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            rc = K.main(["grant", "--to", "Owner@Example.com", "--to", " other@example.com ",
                         "--to", "nobody@example.com"])
    finally:
        A.DB_PATH = saved
    text = out.getvalue()
    assert rc == 1, ("one email matched no account", text)
    assert "Owner@Example.com: karma 0 -> 100,000 (level 62, Legend), 19 of 19 badges — given" in text, text
    assert " other@example.com : karma 0 -> 100,000" in text, text
    assert "nobody@example.com: no account signs in with that email — nothing given" in text
    conn = A.connect(path)
    try:
        assert K.total(conn, owner) == K.total(conn, other) == 100_000 and K.total(conn, fan) == 0
    finally:
        conn.close()


def test_no_email_is_kept_in_the_code():
    src = open(os.path.join(ROOT, "engine", "karma.py"), encoding="utf-8").read()
    grant = src[src.index("# ─── given by hand"):src.index("def main(")]
    assert "@" not in grant.replace("@example.com", ""), "an address in the code"
    assert 'ap.add_argument("--to", action="append", required=True, metavar="EMAIL"' in grant


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
