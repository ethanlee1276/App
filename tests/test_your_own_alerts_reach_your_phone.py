"""Your own alerts reach your phone: a watch that fired, your parlay on, one
leg left, settled.

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 9 and 10 (engine/pushmine). What these hold:

  - a member's own alerts need the member: a phone subscribed signed out
    gets the shared two only, and subscribing signed out detaches it from
    any account (a shared phone stops showing the last person's bets);
  - a watch alert is the member's own words and a count, never the pick;
    it goes only to a member the gate lets read the feed, starts from now
    on a first look, waits out quiet hours, and fires once;
  - the slip watch's own pass queues the ticket's three moments, once each,
    and only for a member whose phone asked; they go at any hour;
  - a knocked phone reads its member's queue with the shared one, newest
    first; another phone never reads it;
  - the box runs it on the slip watcher's minute, the page carries the
    switches and re-links on sign-in and sign-out.

Every test runs on a throwaway accounts database; nothing is sent.

    python3 tests/test_your_own_alerts_reach_your_phone.py
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_DIR = tempfile.mkdtemp()
os.environ["QB_ACCOUNTS_DB"] = os.path.join(_DIR, "accounts.db")
os.environ["QB_MODELS_DIR"] = os.path.join(_DIR, "models")
os.environ["QB_LIKELY_CAL"] = os.path.join(_DIR, "likely_calibration.json")
os.environ["QB_SITE_URL"] = "https://qellysbook.example"

from engine import accounts as A                                  # noqa: E402
from engine import alerts as AL                                   # noqa: E402
from engine import gate                                           # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402
from engine import slipwatch as SW                                # noqa: E402

READ = lambda *p: (ROOT.joinpath(*p)).read_text(encoding="utf-8")  # noqa: E731
GOOD = "correct horse battery"
NOW = 1_760_000_000.0
KEY = {"d": 1, "pub": "x"}


def _ep(n):
    return f"https://fcm.googleapis.com/fcm/send/member{n}:APA91bHxyz"


_n = [0]


def _member(slips=None):
    _n[0] += 1
    conn = A.connect()
    try:
        code, out = A.create_user(conn, f"m{_n[0]}@example.com", GOOD, confirmed=True)
        assert code == 200, out
        if slips:
            A.save_sections(conn, out["id"], {"mybets": {"ts": 1, "data": {"rows": slips, "deleted": []}}})
        return out["id"]
    finally:
        conn.close()


def _conn():
    conn = A.connect()
    PM.ensure_tables(conn)
    return conn


def test_your_own_alerts_need_you_and_signing_out_lets_go():
    uid = _member()
    conn = _conn()
    try:
        code, out = PA.subscribe(conn, _ep(1), topics=["posted", "watches", "bets"])
        assert code == 200 and out["topics"] == ["posted"], "signed out: the shared alerts only"
        code, out = PA.subscribe(conn, _ep(1), topics=["posted", "watches", "bets"], user_id=uid)
        assert out["topics"] == ["posted", "watches", "bets"] and PA.subscription(conn, _ep(1))["user_id"] == uid
        code, out = PA.subscribe(conn, _ep(1), topics=["posted", "watches", "bets"])
        assert out["topics"] == ["posted"] and PA.subscription(conn, _ep(1))["user_id"] is None, \
            "subscribing signed out detaches the phone"
        PA.subscribe(conn, _ep(2), topics=["bets"], user_id=uid)
        code, out = PA.subscribe(conn, _ep(2), topics=["bets"])
        assert code == 200 and out.get("detached") and PA.subscription(conn, _ep(2)) is None, \
            "nothing left for it: the phone is dropped, not left holding the member's"
        assert PA.subscribe(conn, _ep(3), topics=["bogus"])[0] == 400
    finally:
        conn.close()


def _events(*items):
    return [dict({"kind": "line_move", "edge": 0.07, "market": "receiving yards", "line": 71.5}, **e) for e in items]


def test_a_watch_alert_is_a_members_words_and_a_count_for_anybody_else():
    uid = _member()
    conn = _conn()
    try:
        PA.subscribe(conn, _ep(10), topics=["watches"], user_id=uid)
        AL.add_watch(conn, uid, "player", "Ja'Marr Chase")
        AL.add_watch(conn, uid, "edge", "6")
        first = _events({"id": "a", "ts": "2026-10-24T18:00:00Z", "player": "Ja'Marr Chase"})
        assert PM.watch_pass(conn, first, entitled=lambda c, w: True, now=NOW) == 0, \
            "a first look starts from now, not the whole window"
        more = first + _events({"id": "b", "ts": "2026-10-24T18:05:00Z", "player": "Ja'Marr Chase"},
                               {"id": "c", "ts": "2026-10-24T18:06:00Z", "player": "Tee Higgins"})
        # BEHIND THE WALL, AN ACCOUNT WITHOUT A PLAN IS TOLD HOW MANY (the
        # free tier, 2026-10-25) — not who, not what: the picks are paid.
        # Run with the wall up whatever this box's own switch says.
        keep = gate.enabled
        gate.enabled = lambda: True
        try:
            assert PM.watch_pass(conn, more, entitled=lambda c, w: False, now=NOW) == 1
            t = PM.mine(conn, uid, now=NOW)[0]
            assert t["url"] == "/#paywall" and "2 new picks" in t["body"] and "Members see them" in t["body"], t
            words = (t["title"] + t["body"]).lower()
            for leak in ("chase", "higgins", "edge", "receiving", "over", "under"):
                assert leak not in words, f"a free account's alert names {leak}"
        finally:
            gate.enabled = keep
        conn.execute("DELETE FROM push_mine WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM push_watch_seen WHERE user_id = ?", (uid,))
        conn.execute("INSERT INTO push_watch_seen (user_id, ts) VALUES (?, ?)", (uid, "2026-10-24T18:00:00Z"))
        assert PM.watch_pass(conn, more, entitled=lambda c, w: True, now=NOW) == 1
        msgs = PM.mine(conn, uid, now=NOW)
        assert len(msgs) == 1 and msgs[0]["kind"] == "watches" and msgs[0]["url"] == "/#alerts", msgs
        m = msgs[0]
        assert m["title"] == "2 new on your watches", m
        assert "Ja'Marr Chase" in m["body"] and "any edge at or above 6" in m["body"], m
        words = (m["title"] + m["body"]).lower()
        for pick in ("receiving", "71.5", "7%", "0.07", "higgins", "over", "under"):
            assert pick not in words, f"a pick on a lock screen: {pick}"
        assert PM.watch_pass(conn, more, entitled=lambda c, w: True, now=NOW) == 0, "once"
        nobody = _member()
        AL.add_watch(conn, nobody, "player", "Tee Higgins")
        assert PM.watch_pass(conn, more, entitled=lambda c, w: True, now=NOW) == 0, "no phone asked, none told"
        assert PM.mine(conn, nobody, now=NOW) == []
    finally:
        conn.close()


def test_the_three_moments_of_a_ticket_once_each_and_only_if_asked():
    uid = _member()
    conn = _conn()
    try:
        assert not PM.bet_on(conn, uid, "s1", "BUF 7 – 10 LA, 2nd 4:12", now=NOW), "nobody of theirs asked"
        PA.subscribe(conn, _ep(20), topics=["bets"], user_id=uid)
        assert PM.bet_on(conn, uid, "s1", "BUF 7 – 10 LA, 2nd 4:12", now=NOW)
        assert not PM.bet_on(conn, uid, "s1", "BUF 14 – 10 LA", now=NOW + 60), "once"
        assert PM.bet_last(conn, uid, "s1", "Chiefs ML", now=NOW + 120)
        bet = {"id": "s1", "stake": 20, "odds": 170}
        assert PM.bet_settled(conn, uid, bet, {"result": "win"}, now=NOW + 180)
        msgs = {m["id"]: m for m in PM.mine(conn, uid, now=NOW + 200)}
        assert msgs["bets:on:s1"]["body"].startswith("BUF 7 – 10 LA") and msgs["bets:on:s1"]["url"] == "/#live"
        assert msgs["bets:last:s1"]["body"].startswith("Chiefs ML decides your parlay")
        assert msgs["bets:settled:s1"]["title"] == "Your parlay won"
        assert msgs["bets:settled:s1"]["body"].startswith("$54.00 back on $20.00"), msgs["bets:settled:s1"]
        assert PM.mine(conn, uid, now=NOW + PM.TTL_S["on"] + 1).__len__() == 2, "a game-on alert goes stale"
        PM.bet_settled(conn, uid, {"id": "s2", "stake": 10, "odds": 300}, {"result": "loss"}, now=NOW)
        PM.bet_settled(conn, uid, {"id": "s3", "stake": 10, "odds": 300}, {"result": "push"}, now=NOW)
        titles = {m["id"]: m["title"] for m in PM.mine(conn, uid, now=NOW + 1)}
        assert titles["bets:settled:s2"] == "Your parlay lost" and titles["bets:settled:s3"] == "Your parlay pushed"
        # A ticket of one leg is a bet (a straight bet tracked from Ask).
        assert PM.bet_on(conn, uid, "s4", "BUF 0 – 0 LA, 1st 15:00", now=NOW, legs=1)
        PM.bet_settled(conn, uid, {"id": "s4", "stake": 10, "odds": -110, "legs": [{"player": "Josh Allen"}]},
                       {"result": "win"}, now=NOW)
        titles = {m["id"]: m["title"] for m in PM.mine(conn, uid, now=NOW + 1)}
        assert titles["bets:on:s4"] == "Your bet is on" and titles["bets:settled:s4"] == "Your bet won", titles
    finally:
        conn.close()


def test_sending_holds_watches_in_the_night_and_never_your_tickets():
    uid = _member()
    conn = _conn()
    try:
        PM.flush(conn, knock=lambda *a, **k: 201, apns=lambda *a: 200, vapid=KEY, apns_cfg={"k": 1}, now=NOW,
                 quiet=False)                                       # the earlier tests' queue, sent
        PA.subscribe(conn, _ep(30), topics=["watches", "bets"], user_id=uid)
        PA.subscribe(conn, "ab" * 32, kind="apns", topics=["bets"], user_id=uid)
        PM.tell(conn, uid, "watches:x", "watches", "1 new", "On Chase.", "/#alerts", now=NOW)
        PM.tell(conn, uid, "bets:last:s9", "bets", "Down to the last leg", "KC decides it", "/#live", now=NOW)
        knocks, apns = [], []
        knock = lambda ep, k, topic="": knocks.append((ep, topic)) or 201        # noqa: E731
        sent = lambda tok, m, cfg: apns.append((tok, m["title"])) or 200         # noqa: E731
        out = PM.flush(conn, knock=knock, apns=sent, vapid=KEY, apns_cfg={"k": 1}, now=NOW, quiet=True)
        assert out["messages"] == 1 and knocks == [(_ep(30), "bets-last-s9")] and apns == [("ab" * 32, "Down to the last leg")]
        knocks.clear()
        out = PM.flush(conn, knock=knock, apns=sent, vapid=KEY, apns_cfg={"k": 1}, now=NOW + 60, quiet=False)
        assert out["messages"] == 1 and knocks == [(_ep(30), "watches-x")], "the watch goes at nine"
        assert PM.flush(conn, knock=knock, apns=sent, vapid=KEY, apns_cfg={"k": 1}, now=NOW + 90, quiet=False)["messages"] == 0
        PM.tell(conn, uid, "bets:on:s10", "bets", "Your parlay is on", "x", "/#live", ttl="on", now=NOW)
        knocks.clear()
        PM.flush(conn, knock=knock, apns=sent, vapid=KEY, apns_cfg={"k": 1}, now=NOW + PM.TTL_S["on"] + 5, quiet=False)
        assert knocks == [], "a stale game-on is dropped, not sent late"
        PM.tell(conn, uid, "bets:settled:s11", "bets", "Your parlay lost", "x", "/#mybets", now=NOW)
        out = PM.flush(conn, knock=lambda *a, **k: 410, apns=sent, vapid=KEY, apns_cfg={"k": 1}, now=NOW + 1, quiet=False)
        assert out["gone"] == 1 and PA.subscription(conn, _ep(30)) is None, "a refused address goes"
        PM.flush(conn, knock=lambda *a, **k: 201, apns=lambda *a: 200, vapid=KEY, apns_cfg={"k": 1},
                 now=NOW + PM.KEEP_S + 1, quiet=False)
        assert not conn.execute("SELECT 1 FROM push_mine WHERE user_id = ?", (uid,)).fetchone(), \
            "kept a day at most (privacy policy 2.7)"
    finally:
        conn.close()
    assert "We keep\n      those for at most a day" in READ("web", "privacy.html")
    conn = _conn()
    try:
        pass
    finally:
        conn.close()


def test_a_knocked_phone_reads_its_own_queue_and_no_other_phone_does():
    uid, other = _member(), _member()
    conn = _conn()
    try:
        PA.subscribe(conn, _ep(40), topics=["posted", "bets"], user_id=uid)
        PA.subscribe(conn, _ep(41), topics=["posted", "settled"], user_id=other)
        PA.subscribe(conn, _ep(42), topics=["posted", "settled"])
        shared = Path(_DIR) / "latest.json"
        shared.write_text(json.dumps({"messages": [{"id": "posted:nfl:2026-10-24", "kind": "posted", "league": "nfl",
                                                    "title": "This week’s NFL picks are up", "body": "6 picks",
                                                    "url": "/", "at": NOW - 600}]}))
        PM.tell(conn, uid, "bets:last:s1", "bets", "Down to the last leg", "KC decides it", "/#live", now=NOW)
        sub = PA.subscription(conn, _ep(40))
        got = PA.latest_for(sub, path=shared, now=NOW + 5, mine=PM.mine(conn, sub["user_id"], now=NOW + 5))
        assert got["title"] == "Down to the last leg" and got["tag"] == "bets:last:s1", got
        for ep in (_ep(41), _ep(42)):
            s = PA.subscription(conn, ep)
            got = PA.latest_for(s, path=shared, now=NOW + 5, mine=PM.mine(conn, (s or {}).get("user_id"), now=NOW + 5))
            assert got["title"] == "This week’s NFL picks are up", (ep, got)
        assert PM.mine(conn, None) == []
    finally:
        conn.close()


def _tracker():
    spec = importlib.util.spec_from_file_location(
        "_tracktests", ROOT / "tests" / "test_a_graded_slip_says_what_to_do_next.py")
    T = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(T)
    return T


def test_the_slip_watch_queues_the_result_for_a_member_who_asked():
    from engine import sliplive as SL
    T = _tracker()
    leg = lambda team, odds, game: dict(T._ml(team, odds), game=game)  # noqa: E731
    slip = {"id": "1760000000501", "book": "DraftKings", "sport": "NFL", "date": "2026-10-18", "desc": "two-leg",
            "stake": 20, "odds": 170, "result": "pending", "src": "slip", "slip_key": "k501",
            "legs": [leg("LA", -140, "BUF @ LA"), leg("KC", -180, "DEN @ KC")]}
    uid = _member([slip])
    conn = _conn()
    try:
        PA.subscribe(conn, _ep(50), topics=["bets"], user_id=uid)
    finally:
        conn.close()
    final = SL.Live({"nfl": {}}, fast_dir=T._fast({"live_nfl.json": {"games": [
        {"event_id": "1", "home": "LA", "away": "BUF",
         "live": {"state": "final", "home_score": 24, "away_score": 20, "period": 4, "clock": "0:00"}},
        {"event_id": "2", "home": "KC", "away": "DEN",
         "live": {"state": "final", "home_score": 27, "away_score": 20, "period": 4, "clock": "0:00"}}]}}))
    conn = A.connect()
    try:
        rows = [r for r in SW.pending_slips(conn) if r["user_id"] == uid]
        out = SW.sweep(conn, T.GAMES, final, rows=rows, send=lambda *a: None, now=NOW,
                       site="https://qellysbook.example", log=lambda *_: None)
        assert out["settled"] == 1, out
        msgs = PM.mine(conn, uid, now=NOW + 1)
        assert [m["id"] for m in msgs] == ["bets:settled:1760000000501"] and msgs[0]["title"] == "Your parlay won", msgs
    finally:
        conn.close()


def test_the_box_the_server_and_the_page_carry_it():
    launch = READ("launch.py")
    at = launch.index("def _slip_watcher() -> None:")
    body = launch[at:launch.index("\ndef ", at + 10)]
    assert body.index("_sw.run_once(entitled=_srv.account_entitled)") < body.index("_pm.run_once(entitled=_srv.account_entitled)")
    srv = READ("server.py")
    at = srv.index("def _push_post(self, path: str):")
    assert "out = PA.latest_for(sub, mine=PM.mine(conn, uid)," in srv[at:at + 3000] and \
        'uid = (sub or {}).get("user_id")' in srv[at:at + 3000], "the member's own queue, with the shared one"
    from _app import app_js                    # the Alerts page loads on first use (js/more.js)
    app = app_js()
    assert 'box("watches", "My teams and players make the board (members see which)", !signedIn)' in app
    assert 'box("bets", "My parlay: on, last leg, settled", !signedIn)' in app
    assert app.count("    _acctUser = { signed_in: true, email: body.email };\n    pushRelink();\n") == 2
    at = app.index("window.acctSignOut = async function () {")
    assert "pushRelink();" in app[at:at + 1400], "signing out detaches this phone"
    sw = READ("engine", "slipwatch.py")
    for what in ('_tell("bet_on"', '_tell("bet_last"', '_tell("bet_settled"'):
        assert what in sw, what


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
