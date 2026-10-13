"""A saved slip down to its last leg says so — on the Live tab, with a
buzz, and by email from the box to a member who asked (engine/slipwatch,
2026-10-13).

Ethan, 2026-10-13: "add all of them", the fifth being an alert when a slip
saved to My Bets from the parlay checker is down to the one leg that
decides it.

Every test runs on a throwaway accounts database and the tracker test's
own synthetic board; nothing reads the box's files or the network, and
nothing is ever sent — `send` is a list.

    python3 tests/test_a_saved_slip_on_its_last_leg_says_so.py
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
from engine import digest as DG                                   # noqa: E402
from engine import mailer                                         # noqa: E402
from engine import slipgrade as SG                                # noqa: E402
from engine import sliplive as SL                                 # noqa: E402
from engine import slipwatch as SW                                # noqa: E402

_spec = importlib.util.spec_from_file_location("_tracktests", ROOT / "tests" / "test_a_graded_slip_says_what_to_do_next.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

GOOD = "correct horse battery"
NOW = 1_760_000_000.0
SITE = "https://qellysbook.example"

ONE_LEFT = {"id": "1760000000001", "book": "DraftKings", "sport": "NFL", "date": "2026-10-18",
            "desc": "2-leg parlay: LA moneyline + KC moneyline", "stake": 20, "odds": 170, "result": "pending",
            "src": "slip", "slip_key": "sx1",
            "legs": [dict(T._ml("LA", -140), game="BUF @ LA"), dict(T._ml("KC", -180), game="DEN @ KC")]}
NOT_STARTED = {"id": "1760000000002", "book": "FanDuel", "sport": "NFL", "date": "2026-10-18",
               "desc": "2-leg parlay: KC moneyline + DEN moneyline", "stake": 10, "odds": 400, "result": "pending",
               "src": "slip", "slip_key": "sx2",
               "legs": [dict(T._ml("KC", -180), game="DEN @ KC"), dict(T._ml("DEN", 155), game="DEN @ KC")]}
BY_HAND = {"id": "1760000000003", "book": "Caesars", "desc": "Rams -3", "stake": 10, "odds": -110, "result": "pending"}
SETTLED = dict(ONE_LEFT, id="1760000000004", result="win")


def _member(email, slips, on=None):
    conn = A.connect()
    try:
        code, out = A.create_user(conn, email, GOOD, confirmed=True)
        assert code == 200, out
        A.save_sections(conn, out["id"], {"mybets": {"ts": 1, "data": {"rows": slips, "deleted": []}}})
        if on is not None:
            SW.optin_set(conn, out["id"], on)
        return out["id"]
    finally:
        conn.close()


def _live(first_state="final"):
    return SL.Live({"nfl": {}}, fast_dir=T._scores(first_state=first_state))


def test_the_box_notices_a_slip_down_to_its_last_leg_once_and_mails_who_asked():
    uid = _member("a@example.com", [ONE_LEFT, NOT_STARTED, BY_HAND, SETTLED], on=True)
    uid2 = _member("b@example.com", [ONE_LEFT])                        # never asked for the email
    sent = []
    conn = A.connect()
    try:
        rows = SW.pending_slips(conn)
        assert [(r["email"], r["bet"]["id"]) for r in rows] == [
            ("a@example.com", "1760000000002"), ("a@example.com", "1760000000001"),
            ("b@example.com", "1760000000001")], "open saved slips only, newest first, by hand and settled left out"
        out = SW.sweep(conn, T.GAMES, _live(), send=lambda *a: sent.append(a), entitled=lambda c, w: True,
                       mail_on=True, now=NOW, site=SITE)
        assert out == {"slips": 3, "noted": 2, "mailed": 1, "failed": 0}, out
        assert [s[0] for s in sent] == ["a@example.com"]
        assert [tuple(r) for r in conn.execute(
            "SELECT user_id, bet_id, mailed FROM slip_alerts ORDER BY user_id")] == \
            [(uid, "1760000000001", 1), (uid2, "1760000000001", 0)]
        again = SW.sweep(conn, T.GAMES, _live(), send=lambda *a: sent.append(a), entitled=lambda c, w: True,
                         mail_on=True, now=NOW + 60, site=SITE)
        assert again["noted"] == 0 and again["mailed"] == 0 and len(sent) == 1, "once per slip, ever"
        # The message: the ticket, the leg, when it kicks off, our chance, the hedge's own numbers.
        to, subject, text, html = sent[0]
        assert subject == "One leg left on your DraftKings slip: KC moneyline"
        assert "2-leg parlay: LA moneyline + KC moneyline ($20.00 at +170) is down to its last leg." in text
        assert "KC moneyline: kicks off Sun 4:25 PM ET. Our chance for the rest: 66%." in text
        assert "The hedge: DEN moneyline at +155 (Caesars)." in text
        W, d = 20 * SG.to_decimal(170), SG.to_decimal(155)
        assert f"Lock it: bet ${W / d:,.2f} and you're up ${W - 20 - W / d:,.2f} whichever way it goes." in text
        assert f"Stake back: bet ${20 / (d - 1):,.2f}" in text
        assert f"{SITE}/#live" in text and "No bets are taken here." in text
        assert f"Stop these emails: {SITE}/unsubscribe/slip-{uid}." in text
        assert f'href="{SITE}/#live"' in html and "Stop these emails</a>" in html and "KC moneyline" in html
        msg = mailer.message(to, subject, text, html)
        link = text.split("Stop these emails: ")[1].split()[0]
        assert msg["List-Unsubscribe"] == f"<{link}>" and msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert msg.get_body(("plain",)) is not None and msg.get_body(("html",)) is not None, "both parts"
        # The link turns off this mail and nothing else; a wrong token does nothing.
        token = link.rsplit("/", 1)[1]
        assert token == SW.link_token(conn, uid) and token.startswith("slip-")
        assert SW.unsubscribe(conn, token[:-1] + ("A" if token[-1] != "A" else "B")) is False
        assert SW.unsubscribe(conn, token[5:]) is False and DG.unsubscribe(conn, token) is False
        assert SW.optin_get(conn, uid)["on"] is True
        assert SW.unsubscribe(conn, token) is True and SW.optin_get(conn, uid)["on"] is False
        assert SW.link_token(conn, uid) == token, "the salt is kept across the toggle: old links keep working"
        assert SW.link_token(conn, uid2) == "", "no token for somebody who never opted in"
    finally:
        conn.close()


def test_the_gate_the_switch_and_the_days_allowance_each_hold_the_email():
    sent = []
    send = lambda *a: sent.append(a)                                  # noqa: E731
    conn = A.connect()
    try:
        def run(uid, **kw):
            sent.clear()
            out = SW.sweep(conn, T.GAMES, _live(), send=send, now=NOW, site=SITE, **kw)
            row = conn.execute("SELECT mailed FROM slip_alerts WHERE user_id=?", (uid,)).fetchone()
            return out["noted"], out["mailed"], out["failed"], row and int(row["mailed"]), len(sent)
        c = _member("c@example.com", [ONE_LEFT], on=True)
        assert run(c, entitled=lambda cn, w: False, mail_on=True) == (1, 0, 0, 0, 0), "not entitled: noted, not mailed"
        d = _member("d@example.com", [ONE_LEFT], on=True)
        assert run(d, entitled=lambda cn, w: True, mail_on=False) == (1, 0, 0, 0, 0), "no relay: noted, not mailed"
        e = _member("e@example.com", [ONE_LEFT], on=True)
        assert run(e, mail_on=True) == (1, 0, 0, 0, 0), "no gate handed in: nobody is mailed"
        f = _member("f@example.com", [ONE_LEFT], on=True)
        saved = list(SW._SENT)
        SW._SENT[:] = [NOW - 1] * SW.MAIL_PER_DAY
        try:
            assert run(f, entitled=lambda cn, w: True, mail_on=True) == (1, 0, 0, 0, 0), "the day's allowance is spent"
        finally:
            SW._SENT[:] = saved
        g = _member("g@example.com", [ONE_LEFT], on=True)

        def broken(*a):
            raise RuntimeError("relay down")
        out = SW.sweep(conn, T.GAMES, _live(), send=broken, entitled=lambda cn, w: True, mail_on=True, now=NOW, site=SITE)
        assert out["noted"] == 1 and out["failed"] == 1 and out["mailed"] == 0
        assert run(g, entitled=lambda cn, w: True, mail_on=True) == (0, 0, 0, 0, 0), "a failed send is not retried"
        # Who the gate is asked about: the member, by id and address.
        asked = []
        h = _member("h@example.com", [ONE_LEFT], on=True)
        SW.sweep(conn, T.GAMES, _live(), send=send, entitled=lambda cn, w: asked.append(w) or True, mail_on=True,
                 now=NOW, site=SITE)
        assert asked == [{"id": h, "email": "h@example.com"}] and [s[0] for s in sent] == ["h@example.com"]
        # Old notes go; a slip two legs from done or already decided is never noted.
        assert conn.execute("SELECT COUNT(*) FROM slip_alerts").fetchone()[0] >= 6
        SW.sweep(conn, T.GAMES, _live(), send=send, entitled=None, now=NOW + (SW.KEEP_DAYS + 1) * 86400, site=SITE)
        assert conn.execute("SELECT COUNT(*) FROM slip_alerts WHERE fired_at < ?", (NOW + 1,)).fetchone()[0] == 0
        assert not conn.execute("SELECT 1 FROM slip_alerts WHERE bet_id='1760000000002'").fetchone()
    finally:
        conn.close()


def test_the_leg_is_described_from_the_scoreboard_and_a_push_is_not_a_leg_left():
    card = dict(T.TRACK_ONE_LEFT, hedge=dict(T.TRACK_ONE_LEFT["hedge"], lock={"hedge": 21.18, "either": 12.82},
                                             back={"hedge": 12.9, "if_hits": 21.1}))
    subject, text, html = SW.message(dict(ONE_LEFT, book="Other"), card, link=f"{SITE}/unsubscribe/slip-1.x", site=SITE)
    assert subject == "One leg left on your slip: KC moneyline", "no book named when My Bets has none"
    multi = SW.message(dict(ONE_LEFT, book="Draft\nKings", desc="x \r\n y " * 100), card, link="x", site=SITE)
    assert multi[0] == "One leg left on your Draft Kings slip: KC moneyline" and "\n" not in multi[0]
    assert multi[1].startswith("x y x y") and len(multi[1].split(" is down to its last leg")[0]) < 200, "one line, bounded"
    assert "KC moneyline: DEN 13 – 17 KC, 5:41 - 3rd, 62% to win now. Our chance for the rest: 62%." in text
    assert "The hedge: DEN moneyline at +155 (Caesars) — the price we last saw." in text
    assert "Lock it: bet $21.18 and you're up $12.82 whichever way it goes." in text
    assert SW.where({"market": "receptions", "live": {"state": "live", "home": "LA", "away": "BUF", "home_score": 17,
                                                      "away_score": 10, "clock": "8:12 - 3rd", "current": 4}}) \
        == "BUF 10 – 17 LA, 8:12 - 3rd, has 4 so far"
    assert SW.where({"market": "spread", "live": {"state": "live", "home": "LA", "away": "BUF", "home_score": 17,
                                                  "away_score": 10, "clock": "Half", "cover_by": -2.5}}) \
        == "BUF 10 – 17 LA, Half, short by 2.5"
    assert SW.where({"market": "moneyline", "kickoff": "2026-10-19 20:15"}) == "kicks off Mon 8:15 PM ET"
    assert SW.where({"market": "moneyline"}) == "not started yet"
    # No hedge price known: the message still says where it stands.
    bare = dict(card, hedge=None)
    _, text2, _ = SW.message(ONE_LEFT, bare, link="x", site=SITE)
    assert "The hedge:" not in text2 and "KC moneyline: DEN 13 – 17 KC" in text2
    # At the price no hedge locks a profit: said, not invented.
    nolock = dict(card, hedge=dict(card["hedge"], lock={"hedge": 50.0, "either": -3.0}, back=None))
    assert "no hedge locks a profit" in SW.message(ONE_LEFT, nolock, link="x", site=SITE)[1]
    # One leg left means one leg to decide it — the standing's own count.
    assert SW.last_leg({"now": {"status": "open", "left": 1}}) is True
    assert SW.last_leg({"now": {"status": "open", "left": 2}}) is False
    assert SW.last_leg({"now": {"status": "won", "left": 0}}) is False and SW.last_leg({"now": None}) is False
    # A live last leg off the real reader, not the fixture: LA final, KC in play.
    fast = T._fast({"live_nfl.json": {"games": [
        {"event_id": "1", "home": "LA", "away": "BUF",
         "live": {"state": "final", "home_score": 24, "away_score": 20, "period": 4, "clock": "0:00"}},
        {"event_id": "2", "home": "KC", "away": "DEN",
         "live": {"state": "live", "home_score": 17, "away_score": 13, "period": 3, "clock": "5:41 - 3rd"}}]}})
    graded = SG.grade(SG.clean_slip(dict(ONE_LEFT, total_odds=170, is_bet_slip=True)), T.GAMES,
                      live=SL.Live({"nfl": {}}, fast_dir=fast), brief=True)
    assert SW.last_leg(graded), graded["now"]
    stand = SW.where(SW.open_leg(graded))
    assert stand.startswith("DEN 13 – 17 KC, ") and "5:41 - 3rd" in stand, stand   # the reader's own clock, quarter first


class _Sent(Exception):
    pass


def _handler(token):
    import server
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json", headers=None: sent.append((code, body, ext))
    h._cookie = lambda name: token
    h._account = lambda conn: A.session_user(conn, token)
    return h, sent


def test_the_account_endpoints_switch_it_and_it_dies_with_the_account():
    import server
    uid = _member("i@example.com", [ONE_LEFT])
    conn = A.connect()
    saved = server._mail_on
    server._mail_on = lambda: True
    try:
        token = A.start_session(conn, uid)
        h, sent = _handler(token)
        h._account_get("lastleg")
        assert sent[-1][0] == 200 and json.loads(sent[-1][1]) == {"on": False, "available": True, "email": "i@example.com"}
        h._account_post("lastleg", {"on": True})
        assert sent[-1][0] == 200 and json.loads(sent[-1][1]) == {"on": True, "available": True, "email": "i@example.com"}
        h._account_get("lastleg")
        assert json.loads(sent[-1][1])["on"] is True and SW.optin_get(conn, uid)["on"] is True
        h._account_post("lastleg", {"on": "no"})
        assert json.loads(sent[-1][1])["on"] is True, "a string is not off: only a boolean switches it"
        h._account_post("lastleg", {"on": False})
        assert json.loads(sent[-1][1])["on"] is False and SW.optin_get(conn, uid)["on"] is False
        assert "token" not in sent[-1][1].decode() and "slip-" not in sent[-1][1].decode()
        out, sent2 = _handler("")
        out._account_get("lastleg")
        assert sent2[-1][0] == 401
        out._account_post("lastleg", {"on": True})
        assert sent2[-1][0] == 401
        # The unsubscribe page knows which list a token is for, and needs no one signed in.
        SW.optin_set(conn, uid, True)
        tok = SW.link_token(conn, uid)
        page, pages = _handler("")
        page._unsubscribe({"t": [tok]})
        assert pages[-1][0] == 200 and pages[-1][2] == ".html"
        assert b"saved slip is down to its last leg" in pages[-1][1] and b"Live tab" in pages[-1][1]
        assert SW.optin_get(conn, uid)["on"] is False
        page._unsubscribe({"t": ["nobody"]})
        assert pages[-1][0] == 200 and b"morning card or the nightly recap" in pages[-1][1]
        # The export carries the switch and nothing of the link; deleting the account takes both tables' rows.
        SW.optin_set(conn, uid, True)
        conn.execute("INSERT INTO slip_alerts (user_id, bet_id, fired_at, mailed) VALUES (?,?,?,1)", (uid, "x", NOW))
        conn.commit()
        ex = A.export_user(conn, uid)
        assert ex["last_leg_email"] is True and "slip-" not in json.dumps(ex)
        A.delete_user(conn, uid)
        for table in ("slip_alerts", "slip_alert_optin"):
            assert not conn.execute(f"SELECT 1 FROM {table} WHERE user_id=?", (uid,)).fetchone(), table
    finally:
        server._mail_on = saved
        conn.close()


def test_the_launcher_runs_it_on_its_own_clock_through_the_servers_gate():
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    i = launch.index("def _slip_watcher(")
    body = launch[i:launch.index("\ndef ", i + 10)]
    assert "time.sleep(SLIP_WATCH_S)" in body and "_sw.run_once(entitled=_srv.account_entitled)" in body
    assert "except Exception as exc" in body and "print(" in body, "a failure is said on the log, never swallowed"
    assert "SLIP_WATCH_S = 60" in launch
    main = launch[launch.index("def main() -> None:"):]
    assert "threading.Thread(target=_slip_watcher, daemon=True" in main
    assert main.index("_live_scores_refresher, daemon=True") < main.index("target=_slip_watcher")
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    i = srv.index("def account_entitled(")
    assert "return Handler._entitled(None, conn, who)" in srv[i:srv.index("\ndef ", i + 10)]
    i = srv.index("def _unsubscribe(self, query")
    body = srv[i:srv.index("def do_POST_unsubscribe", i)]
    assert "SW.unsubscribe(conn, token) if slip else DG.unsubscribe(conn, token)" in body
    assert '"lastleg"' in srv[srv.index("def _account_post("):srv.index("def _account_post(") + 400]
    # No board is read on a minute with nothing open — the common minute.
    fresh = Path(tempfile.mkdtemp()) / "accounts.db"
    saved_db, saved_bl = A.DB_PATH, SW.boards_and_live

    def never():
        raise AssertionError("a board was read with no slip open")
    A.DB_PATH, SW.boards_and_live = fresh, never
    try:
        assert SW.run_once(entitled=lambda c, w: True) == {"slips": 0, "noted": 0, "mailed": 0, "failed": 0}
    finally:
        A.DB_PATH, SW.boards_and_live = saved_db, saved_bl
    # And a sweep with a slip open goes through the real boards (stubbed here) and the gate handed in.
    j = _member("j@example.com", [ONE_LEFT], on=True)
    calls = []
    saved_bl, saved_send = SW.boards_and_live, mailer.send
    SW.boards_and_live = lambda: (T.GAMES, _live())
    mailer.send = lambda *a: calls.append(a)
    saved_env = os.environ.get("QB_RESEND_KEY", ""), os.environ.get("QB_MAIL_FROM", "")
    os.environ["QB_RESEND_KEY"], os.environ["QB_MAIL_FROM"] = "re_test_only", "Qellys Book <hello@qellysbook.example>"
    try:
        out = SW.run_once(entitled=lambda c, w: w["id"] == j)
        assert out["noted"] >= 1 and out["mailed"] == 1 and calls[0][0] == "j@example.com", out
    finally:
        SW.boards_and_live, mailer.send = saved_bl, saved_send
        os.environ["QB_RESEND_KEY"], os.environ["QB_MAIL_FROM"] = saved_env
    # Runbook and the email doc say what it is.
    run = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "44. **A saved slip down to its last leg" in run and "slip watch" in run
    assert "## The last-leg email" in (ROOT / "docs" / "EMAIL.md").read_text(encoding="utf-8")


def test_the_live_tab_leads_with_the_last_leg_and_buzzes_once():
    out = T._node(T._vm("""
        let BETS = [
          { id: "1", result: "pending", src: "slip", legs: [{}], odds: 170, stake: 20 },
          { id: "2", result: "pending", src: "slip", legs: [{}], odds: 170, stake: 20 },
          { id: "3", result: "loss", src: "slip", legs: [{}], odds: 170, stake: 20 } ];
        const buzzed = [];
        const bk = { load: () => JSON.parse(JSON.stringify(BETS)), save: (b) => { BETS = b; }, buzz: (k) => buzzed.push(k) };
        const one = { now: { status: "open", left: 1, won: 1, live: 1 }, legs: [
          { sport: "nfl", team: "LA", market: "moneyline", side: "team", live: { result: "won" } },
          { sport: "nfl", team: "KC", market: "moneyline", side: "team", live: { state: "live" } }], hedge: { leg: "KC moneyline" } };
        const cards = [ { id: "1", slip: one }, { id: "2", slip: { now: { status: "open", left: 2 } } },
                        { id: "3", slip: one }, { id: "9", slip: one }, { id: "2", error: "x" } ];
        const first = S.lastLeg(cards, bk);
        const second = S.lastLeg(cards, bk);
        process.stdout.write(JSON.stringify({ first, second, buzzed, marks: BETS.map((b) => !!b.last_leg),
          strip: S.lastHTML(one), named: S.lastHTML(Object.assign({}, one, { hedge: null })),
          none: S.lastHTML({ now: { status: "won", left: 0 } }) + S.lastHTML({ now: { status: "open", left: 2 } }) + S.lastHTML(null) }));
    """))
    if out is None:
        return
    got = json.loads(out)
    assert got["first"] == ["1"] and got["second"] == [] and got["buzzed"] == ["win"], got
    assert got["marks"] == [True, False, False], "the mark rides on the entry; a settled bet is never marked"
    assert got["strip"].startswith('<div class="pgr-now s-last"><b>Last leg.</b> KC moneyline decides it') and "cash-out" in got["strip"]
    assert "KC moneyline decides it" in got["named"], "no hedge price: the open leg is named from the legs"
    assert got["none"] == ""
    js = (ROOT / "web" / "js" / "slip.js").read_text(encoding="utf-8")
    i = js.index("async function refresh()")
    body = js[i:js.index("\n  }\n", i)]
    assert body.index("settle(body.slips);") < body.index("lastLeg(body.slips);"), "settled first, then the last leg"
    assert 'fetch("/api/account/lastleg"' in js and 'document.addEventListener("change"' in js
    assert "data-lastleg-mail" in js and "onchange" not in js
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = app.index("function liveSlips(")
    assert 'live: () => state.view === "live", buzz }' in app[i:app.index("\n}\n", i)], "the page's own buzz, guarded"
    css = (ROOT / "web" / "css" / "slip.css").read_text(encoding="utf-8")
    assert ".pgr-now.s-last" in css and ".pgr-mail " in css


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
