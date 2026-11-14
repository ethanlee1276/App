"""The owner finds any account, sees where it stands, and acts on it — each step written down.

Ethan, 2026-11-02: "I know you added features and data for me to see, but I
also want more access and stuff to be able to do to people's accounts".
engine/owneraccounts, server `/api/owner/accounts` and `/api/owner/account`,
js/owner.js ACCOUNTS. What these hold:

  * an account is found by any part of its email, the start of its username,
    or its number; a one-letter search finds nothing;
  * its card says how it signs in, its devices and phones, its membership as
    the account page says it, whether it has had its trial, and its Stripe
    customer;
  * free access from the desk lets the account past the paywall until its
    date (the same gate a board, an email and the account page ask), and
    ending it walls it again;
  * sign out everywhere ends every session;
  * a suspension ends every session, unlinks its phones' alerts and refuses
    every way back in, saying why to the right password only; lifting it lets
    them in;
  * a username is reset to member<number>;
  * delete takes the typed email (or a phone account's number);
  * suspend and delete are refused while Stripe can still charge the
    account, and for the site's own account;
  * every action is a line in the record, kept by number after a delete, in
    Download my data while the account lives;
  * the endpoints answer the site's own account alone, a POST only as JSON;
  * the desk draws the card and the Privacy Policy says what it does.

Run directly: `python3 tests/test_the_owner_acts_on_an_account.py`
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp())

from engine import accounts as A                                  # noqa: E402
from engine import billing as BI                                  # noqa: E402
from engine import owneraccounts as OA                            # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import socialfeed as SF                               # noqa: E402

A.DB_PATH = _TMP / "accounts.db"
READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
PASS = "correct horse battery"
DAY = 86400


def _db():
    d = Path(tempfile.mkdtemp())
    conn = A.connect(str(d / "acc.db"))
    BI.init(conn)
    OA.init(conn)
    return conn


def _user(conn, email, handle=None):
    uid = int(A.create_user(conn, email, PASS, confirmed=True)[1]["id"])
    if handle:
        code, out = SF.profile_set(conn, uid, handle, "my bio", name=handle.title())
        assert code == 200, out
    return uid


def _sub(conn, uid, status, cancel=False, ends_in=20 * DAY, cus=None):
    conn.execute("INSERT INTO subscriptions (user_id, customer_id, subscription_id, status, period_end, plan, "
                 "cancel_at_end, updated_at, started_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                 "status = excluded.status, cancel_at_end = excluded.cancel_at_end, period_end = excluded.period_end",
                 (uid, cus or f"cus_{uid}", f"sub_{uid}", status, time.time() + ends_in, "monthly", int(cancel),
                  time.time(), time.time() - 10 * DAY))
    conn.commit()


def _entitled(conn, uid):
    import server
    row = conn.execute("SELECT email FROM users WHERE id = ?", (uid,)).fetchone()
    return server.account_entitled(conn, {"id": uid, "email": row[0]})


def test_an_account_is_found_by_its_email_its_username_or_its_number():
    conn = _db()
    a = _user(conn, "jordan.smith@example.com", "Jordan_S")
    b = _user(conn, "pat@example.com", "Hoops_Pat")
    _user(conn, "under_score@example.com")
    assert [r["id"] for r in OA.find(conn, "smith@exa")] == [a], "any part of the email"
    assert [r["id"] for r in OA.find(conn, "hoops")] == [b], "the start of a username"
    assert [r["id"] for r in OA.find(conn, "@Hoops_P")] == [b], "with its @ too"
    assert [r["id"] for r in OA.find(conn, str(a))] == [a], "its number"
    assert OA.find(conn, "o") == [] and OA.find(conn, "") == [], "one letter is not a search"
    assert [r["id"] for r in OA.find(conn, "under_")] != [] and OA.find(conn, "%") == [], "LIKE's wildcards are literal"
    row = OA.find(conn, "pat@")[0]
    assert set(row) == {"id", "who", "handle", "joined", "seen", "suspended", "status", "entitled"}
    assert row["status"] == "none" and row["who"] == "pat@example.com" and row["handle"] == "Hoops_Pat"


def test_the_card_says_where_the_account_stands():
    conn = _db()
    uid = _user(conn, "card@example.com", "Card_Holder")
    c = OA.card(conn, uid)
    assert c["who"] == "card@example.com" and c["handle"] == "Card_Holder" and c["ways"] == ["password"]
    assert c["membership"]["status"] == "none" and c["membership"]["trial_used"] is False and c["stripe"] == ""
    assert c["sessions"] == 0 and c["grant"] is None and not c["suspended"] and c["log"] == []
    A.start_session(conn, uid)
    _sub(conn, uid, "trialing", cancel=True, ends_in=2 * DAY, cus="cus_ABC123")
    c = OA.card(conn, uid)
    assert c["sessions"] == 1 and c["membership"]["trial_used"] is True
    assert c["stripe"].endswith("/customers/cus_ABC123") and c["stripe"].startswith("https://dashboard.stripe.com/")
    assert c["membership"]["charges"] is False, "a trial set to cancel will not be charged"
    assert OA.card(conn, 99999) is None
    # A phone account shows its number, never the placeholder address.
    pcode, pout = A.create_phone_user(conn, "+15555550123", confirmed=True)
    assert pcode == 200, pout
    pc = OA.card(conn, pout["id"])
    assert pc["phone_account"] and "phone.invalid" not in pc["who"] and "555" in pc["who"] and pc["ways"] == ["phone"]


def test_free_access_opens_the_paywall_until_its_date_and_ending_it_walls_again():
    conn = _db()
    uid = _user(conn, "comp@example.com")
    os.environ["QB_PAYWALL"] = "1"
    try:
        assert not _entitled(conn, uid)
        assert OA.act(conn, uid, "grant", {"days": 0})[0] == 400 and OA.act(conn, uid, "grant", {"days": 400})[0] == 400
        code, out = OA.act(conn, uid, "grant", {"days": 30})
        assert code == 200 and out["card"]["grant"] and abs(out["card"]["grant"] - (time.time() + 30 * DAY)) < 60
        assert _entitled(conn, uid), "the same gate a board asks"
        assert OA.granted(conn, uid, now=time.time() + 31 * DAY) is None, "and no further than its date"
        code, out = OA.act(conn, uid, "ungrant")
        assert code == 200 and out["card"]["grant"] is None and not _entitled(conn, uid)
        assert OA.act(conn, uid, "ungrant")[0] == 409, "nothing to end"
    finally:
        os.environ.pop("QB_PAYWALL", None)
    assert [r["action"] for r in OA.recent(conn)] == ["ungrant", "grant"]
    assert OA.recent(conn)[1]["detail"].startswith("30 days, to ")


def test_sign_out_everywhere_and_suspend_and_lift_it():
    conn = _db()
    uid = _user(conn, "rowdy@example.com", "Rowdy_One")
    tokens = [A.start_session(conn, uid) for _ in range(3)]
    code, out = OA.act(conn, uid, "signout")
    assert code == 200 and all(A.session_user(conn, t) is None for t in tokens)
    assert OA.recent(conn)[0]["detail"] == "3 devices"
    token = A.start_session(conn, uid)
    PA.ensure_tables(conn)
    assert PA.subscribe(conn, "ab" * 16, kind="apns", user_id=uid, topics=["posted"])[0] == 200
    code, out = OA.act(conn, uid, "suspend")
    assert code == 200 and out["card"]["suspended"]
    assert A.session_user(conn, token) is None, "signed out"
    assert conn.execute("SELECT user_id FROM push_subs").fetchone()[0] is None, "its phones keep only the public alerts"
    assert A.session_user(conn, A.start_session(conn, uid)) is None, "a session made anyway answers to nobody"
    code, said = A.authenticate(conn, "rowdy@example.com", PASS)
    assert code == 403 and said.get("suspended") and said["error"] == A.SUSPENDED_MSG
    assert A.authenticate(conn, "rowdy@example.com", "wrong password here")[1]["error"] == "Wrong email or password.", \
        "a wrong password learns nothing"
    assert OA.act(conn, uid, "suspend")[0] == 409
    assert OA.act(conn, uid, "unsuspend")[0] == 200
    assert A.authenticate(conn, "rowdy@example.com", PASS)[0] == 200 and not A.suspended(conn, uid)
    assert OA.act(conn, uid, "unsuspend")[0] == 409


def test_every_way_in_refuses_a_suspended_account():
    src = READ("server.py")
    # Password sign-in is refused by accounts.authenticate; the reset link,
    # the texted code and the passkey are refused before a session is made.
    for at in ("token = A.start_session(conn, out[\"id\"])\n                return self._send(200, json.dumps(\n"
               "                    {\"signed_in\": True, \"email\": out[\"email\"]}).encode(),",):
        i = src.index(at)
        assert "A.suspended(conn, out[\"id\"])" in src[i - 400:i], "the reset link"
    for marker in ('_seclog("phone_verify", "ok"', '_seclog("passkey_login", "ok"'):
        i = src.index(marker)
        assert "A.suspended(conn" in src[i:i + 400] and src.index("A.suspended(conn", i) < src.index("start_session", i), marker
    assert src.count("A.SUSPENDED_MSG") >= 3


def test_a_username_is_reset():
    conn = _db()
    uid = _user(conn, "rude@example.com", "Rude_Name")
    code, out = OA.act(conn, uid, "rename")
    assert code == 200 and out["card"]["handle"] == f"member{uid}" and out["card"]["name"] == ""
    assert (SF.profile_of(conn, uid) or {}).get("bio") == ""
    assert OA.recent(conn)[0]["detail"] == f"@Rude_Name to @member{uid}"
    assert OA.act(conn, uid, "rename")[0] == 409, "already the plain one"
    plain = _user(conn, "nohandle@example.com")
    assert OA.act(conn, plain, "rename")[0] == 409


def test_suspend_and_delete_wait_while_stripe_can_charge_and_never_touch_the_site_account():
    conn = _db()
    payer = _user(conn, "payer@example.com")
    _sub(conn, payer, "active")
    for action, args in (("suspend", {}), ("delete", {"confirm": "payer@example.com"})):
        code, out = OA.act(conn, payer, action, args)
        assert code == 409 and "Cancel its subscription on Stripe first" in out["error"], (action, out)
        assert out["stripe"].endswith(f"/customers/cus_{payer}")
    _sub(conn, payer, "past_due")
    assert OA.act(conn, payer, "suspend")[0] == 409, "Stripe is still retrying a failed card"
    _sub(conn, payer, "active", cancel=True)
    assert OA.act(conn, payer, "suspend")[0] == 200, "set to cancel: Stripe will not charge it again"
    site = _user(conn, "site@example.com")
    assert SF.claim(conn, "site@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
    for action, args in (("suspend", {}), ("delete", {"confirm": "site@example.com"})):
        assert OA.act(conn, site, action, args)[0] == 409, action
    assert OA.act(conn, 424242, "signout")[0] == 404 and OA.act(conn, payer, "explode")[0] == 400


def test_delete_takes_the_typed_email_and_the_record_keeps_the_number():
    conn = _db()
    uid = _user(conn, "Gone.Soon@example.com", "Gone_Soon")
    OA.act(conn, uid, "grant", {"days": 7})
    assert OA.act(conn, uid, "delete", {"confirm": "gone.soon@example"})[0] == 400
    assert OA.act(conn, uid, "delete", {})[0] == 400
    code, out = OA.act(conn, uid, "delete", {"confirm": "  gone.soon@EXAMPLE.com "})
    assert code == 200 and out == {"deleted": True, "id": uid}
    assert conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM owner_grants WHERE user_id = ?", (uid,)).fetchone()[0] == 0
    log = OA.recent(conn)
    assert [r["action"] for r in log] == ["delete", "grant"] and all(r["gone"] and r["id"] == uid for r in log)
    assert all("example.com" not in json.dumps(r) for r in log), "a deleted account's record carries no address"
    # A phone account is confirmed by its number.
    pcode, pout = A.create_phone_user(conn, "+15555550188", confirmed=True)
    assert OA.act(conn, pout["id"], "delete", {"confirm": "(555) 555-0199"})[0] == 400
    assert OA.act(conn, pout["id"], "delete", {"confirm": "+1 (555) 555-0188"})[0] == 200


def test_the_record_is_kept_a_year_and_goes_in_download_my_data():
    conn = _db()
    uid = _user(conn, "mine@example.com")
    OA.act(conn, uid, "grant", {"days": 30}, now=time.time() - OA.LOG_KEEP_S - DAY)
    OA.act(conn, uid, "signout")
    assert [r["action"] for r in OA.recent(conn)] == ["signout"], "a line older than a year is dropped"
    OA.act(conn, uid, "grant", {"days": 30})
    out = A.export_user(conn, uid)
    assert out["free_access_from_the_site"]["until"] > time.time()
    assert [r["action"] for r in out["actions_the_site_took_on_your_account"]] == ["signout", "grant"]
    assert "suspended_at" not in out
    conn.execute("UPDATE users SET suspended_at = ? WHERE id = ?", (time.time(), uid))
    assert A.export_user(conn, uid)["suspended_at"]


# --- the server -------------------------------------------------------------------
def _serve():
    import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _call(base, path, body=None, cookie="", ctype="application/json"):
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(base + path, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": ctype, **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except ValueError:
            return e.code, None


def test_the_endpoints_answer_the_site_account_alone_and_a_post_only_as_json():
    conn = A.connect()
    BI.init(conn)
    site = _user(conn, "site3@example.com")
    assert SF.claim(conn, "site3@example.com", "Qellys_Book", name="Qellys Book")[0] == 200
    fan = _user(conn, "fan3@example.com", "Fan_Three")
    site_c = f"qb_session={A.start_session(conn, site)}"
    fan_c = f"qb_session={A.start_session(conn, fan)}"
    conn.close()
    httpd, base = _serve()
    os.environ["QB_PAYWALL"] = "1"
    try:
        for cookie in ("", fan_c):
            assert _call(base, "/api/owner/accounts?q=fan", cookie=cookie)[0] == 404, "no such page"
            assert _call(base, "/api/owner/account", {"id": fan, "action": "signout"}, cookie)[0] == 404
        code, got = _call(base, "/api/owner/accounts?q=fan3", cookie=site_c)
        assert code == 200 and [a["id"] for a in got["accounts"]] == [fan] and got["recent"] == []
        code, got = _call(base, f"/api/owner/accounts?id={fan}", cookie=site_c)
        assert code == 200 and got["card"]["handle"] == "Fan_Three"
        assert _call(base, "/api/owner/accounts?id=987654", cookie=site_c)[0] == 404
        # A form another site could post: refused, whatever it carries.
        code, _ = _call(base, "/api/owner/account", f"id={fan}&action=signout".encode(), site_c,
                        ctype="application/x-www-form-urlencoded")
        assert code == 415
        code, got = _call(base, "/api/owner/account", {"id": fan, "action": "grant", "days": 30}, site_c)
        assert code == 200 and got["card"]["grant"]
        # The fan's own page now says so, and lets them in.
        code, st = _call(base, "/api/billing/status", cookie=fan_c)
        assert code == 200 and st["entitled"] is True and st["note"].startswith("Free access from Qellys Book until ")
        code, got = _call(base, "/api/owner/account", {"id": fan, "action": "suspend"}, site_c)
        assert code == 200
        assert _call(base, "/api/account/me", cookie=fan_c)[1].get("signed_in") is not True, "signed out at once"
        code, said = _call(base, "/api/account/login", {"email": "fan3@example.com", "password": PASS})
        assert code == 403 and said["error"] == A.SUSPENDED_MSG
        code, got = _call(base, "/api/owner/accounts", cookie=site_c)
        assert [r["action"] for r in got["recent"]] == ["suspend", "grant"]
    finally:
        os.environ.pop("QB_PAYWALL", None)
        httpd.shutdown()


def test_the_desk_draws_it_and_the_policy_says_it():
    js = READ("web", "js", "owner.js")
    for want in ("function oaInner(", "function oaCardHTML(", '"/api/owner/account"', "data-oa-arm", "Delete for good",
                 'id="od-acct"', "Suspend and Delete wait until Stripe can no longer charge this account"):
        assert want in js, want
    assert 'headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, action' in js
    assert "#od-acct form" in js, "the minute's redraw never wipes a search or a delete being typed"
    css = READ("web", "css", "owner.css")
    assert ".oa-hit {" in css and ".oa-del {" in css
    priv = re.sub(r"\s+", " ", READ("web", "privacy.html"))
    assert 'id="owner-tools"' in READ("web", "privacy.html")
    for want in ("2.14 When the site’s owner looks at your account", "<code>owner_grants</code>",
                 "<code>owner_actions</code>", "An account Stripe can still charge is never suspended or deleted",
                 "The record of what the owner did to an account</b> — one year"):
        assert want in priv, want
    assert "owner_grants" in READ("engine", "accounts.py"), "it dies with the account"


if __name__ == "__main__":
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn(); print(f"  ok  {name}")
        print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
