"""Gift a month: a member buys a month for a friend, delivered as a code
(docs/IDEAS.md, the way in and the way up's ninth; built 2026-10-28, off
until runbook FZ names a gift price).

What these hold:

  * a code is minted only on Stripe's word that a gift was paid: its signed
    webhook, or the buyer's return trip read back from Stripe; one session
    is one code, however often either says so; an unpaid or someone else's
    session mints nothing;
  * a gift's paid Checkout never becomes a plan: the webhook answers it
    before the subscription code reads it, and the subscription's own
    return-trip check refuses a one-time or gift session outright;
  * a code is redeemed in the Redeem a code box: a month from that day,
    once, entitling exactly as a code does; a spent code reads as no code,
    and a wrong guess counts against the same hourly allowance;
  * Checkout is a one-time payment marked as a gift, with its own
    idempotency key; the buyer sees their codes and whether each is spent;
  * deleting an account takes it off both sides of a gift, and the gift
    stays spent; the privacy policy names the table.

Run directly: `python3 tests/test_gift_a_month.py`
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote_plus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import accounts as A    # noqa: E402
from engine import billing as BI    # noqa: E402
from engine import gifts as GF      # noqa: E402
from engine import redeem as RD     # noqa: E402

NOW = 1_800_000_000.0
SID = "cs_test_giftAAAA1111"


def _db():
    conn = A.connect(os.path.join(tempfile.mkdtemp(), "acc.db"))
    ids = []
    for who in ("buyer", "friend", "other"):
        _, out = A.create_user(conn, f"{who}@example.com", "correct-horse-battery", confirmed=True)
        ids.append(out["id"])
    BI.init(conn)
    return conn, ids


def _session(buyer, paid=True, kind="gift", mode="payment", sid=SID):
    return {"id": sid, "mode": mode, "payment_status": "paid" if paid else "unpaid",
            "client_reference_id": str(buyer), "metadata": {"kind": kind} if kind else {}}


def _hook(sess):
    return {"id": "evt_1", "type": "checkout.session.completed", "created": NOW, "data": {"object": sess}}


def test_only_stripe_s_word_mints_a_code_and_once_a_session():
    conn, (buyer, friend, other) = _db()
    assert GF.is_gift(_hook(_session(buyer))) and not GF.is_gift(_hook(_session(buyer, kind="")))
    assert GF.from_webhook(conn, _hook(_session(buyer, paid=False)), NOW) is None, "unpaid mints nothing"
    code = GF.from_webhook(conn, _hook(_session(buyer)), NOW)
    assert GF.CODE_RE.match(code) and not re.search(r"[IO01]", code[5:]), code
    assert GF.from_webhook(conn, _hook(_session(buyer)), NOW + 5) == code, "a retried webhook is the same code"
    assert GF.confirm(conn, buyer, SID, fetch=lambda s: _session(buyer), now=NOW + 9) == code, "and the return trip"
    assert GF.confirm(conn, other, "cs_test_otherBBBB2222", fetch=lambda s: _session(buyer, sid=s)) is None, \
        "someone else's session mints nothing for the one holding it"
    assert GF.confirm(conn, buyer, "cs_x/../v1/customers", fetch=lambda s: _session(buyer)) is None
    assert GF.confirm(conn, buyer, "cs_test_unpaidCCCC3333", fetch=lambda s: _session(buyer, paid=False, sid=s)) is None
    assert [g["code"] for g in GF.mine(conn, buyer)] == [code] and GF.mine(conn, friend) == []


def test_a_gift_never_becomes_a_plan():
    conn, (buyer, friend, other) = _db()
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    hook = src[src.index("    def _billing_webhook("):]
    assert hook.index("if GF.is_gift(payload):") < hook.index("event = BI.read_event(payload)"), \
        "the gift is answered before the subscription code reads it"
    real = BI._get, BI.keys
    BI._get = lambda url, secret, **kw: _session(buyer)
    BI.keys = lambda: ("sk_test_gift_fake", "whsec_gift_fake", "price_month_fake")
    try:
        out = BI.reconcile_session(conn, buyer, SID)
    finally:
        BI._get, BI.keys = real
    assert not out.get("entitled") and out.get("status") in (None, "none"), out
    assert not conn.execute("SELECT 1 FROM subscriptions WHERE user_id=?", (buyer,)).fetchone()


def test_a_code_is_a_month_once():
    conn, (buyer, friend, other) = _db()
    code = GF.mint(conn, buyer, SID, NOW)
    got = GF.redeem(conn, friend, code.lower(), now=NOW)
    assert got["months"] == 1 and abs(got["granted_to"] - (NOW + RD.MONTH_S)) < 1
    assert RD.active(conn, friend, now=NOW + 86400) and not RD.active(conn, friend, now=NOW + 32 * 86400)
    for who, said in ((friend, "You have already used this code."), (other, "That code is not valid.")):
        try:
            GF.redeem(conn, who, code, now=NOW + 60)
            raise AssertionError("a spent code worked twice")
        except RD.RedeemError as exc:
            assert str(exc) == said, exc
    assert GF.mine(conn, buyer)[0]["redeemed"] is True
    for i in range(RD.MAX_ATTEMPTS - 1):
        try:
            GF.redeem(conn, other, f"GIFT-AAAA-AAA{i + 2}", now=NOW + 100)
        except RD.RedeemError:
            pass
    try:
        GF.redeem(conn, other, "GIFT-ZZZZ-ZZZZ", now=NOW + 101)
    except RD.RedeemError as exc:
        assert "Too many attempts" in str(exc), exc
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "got = (GF.redeem(conn, who[\"id\"], code) if GF.looks_like(code) else" in src, "the code box takes one"


def test_checkout_is_a_one_time_gift():
    url, headers, body = GF.checkout_request("sk_test_gift_fake", "price_gift_fake", 7, "buyer@example.com",
                                             "https://site/?gift=1&s={CHECKOUT_SESSION_ID}#account",
                                             "https://site/#account", now=NOW)
    form = {unquote_plus(k): unquote_plus(v) for k, v in (x.split("=", 1) for x in body.decode().split("&"))}
    assert url.endswith("/checkout/sessions") and headers.get("Idempotency-Key")
    assert form["mode"] == "payment" and form["line_items[0][price]"] == "price_gift_fake"
    assert form["metadata[kind]"] == "gift" and form["payment_intent_data[metadata][kind]"] == "gift"
    assert form["client_reference_id"] == "7" and form["success_url"].startswith("https://site/?gift=1&s=")
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if path not in ("checkout", "portal", "yearly", "gift", "gift_confirm"):' in src
    assert 'out["gifts"] = _GF.enabled()' in src and 'if path == "gifts":' in src
    os.environ.pop(GF.ENV_GIFT_PRICE, None)
    assert GF.enabled() is False, "off until a gift price is named"


def test_an_account_leaves_a_gift_and_the_policy_names_it():
    conn, (buyer, friend, other) = _db()
    code = GF.mint(conn, buyer, SID, NOW)
    GF.redeem(conn, friend, code, now=NOW)
    A.delete_user(conn, buyer)
    A.delete_user(conn, friend)
    row = conn.execute("SELECT user_id, redeemed_by FROM gift_codes WHERE code=?", (code,)).fetchone()
    assert tuple(row) == (0, 0), "both off it"
    try:
        GF.redeem(conn, other, code, now=NOW + 5)
        raise AssertionError("a gift whose user left came back to life")
    except RD.RedeemError:
        pass
    assert "<code>gift_codes</code>" in (ROOT / "web" / "privacy.html").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\nif (")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_settings_screen():
    acct = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
    assert "if (s.gifts) rows.push(setItem({ ico: \"ticket\", tone: \"gold\", title: \"Gift a month\"" in acct
    assert 'if (b.dataset.gift === "buy") { _billGo(b, "gift"); return; }' in acct
    assert "/^cs_[A-Za-z0-9_]{8,200}$/.test(sid)" in _fn(acct, "giftFill"), "only a session id's shape is sent on"
    node = shutil.which("node")
    if not node:
        return
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    prog = f"""
      const escapeHtml = (s) => String(s).replace(/</g, "&lt;"); const escapeAttr = escapeHtml;
      const icon = () => ""; const setIco = () => "";
      {_fn(app, "setHref")}
      {_fn(app, "setItem")}
      {_fn(app, "setGroup")}
      {_fn(acct, "giftHTML")}
      const strip = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      console.log(JSON.stringify([
        strip(giftHTML({{ on: true, gifts: [{{ code: "GIFT-ABCD-EFGH", redeemed: false }}, {{ code: "GIFT-JKLM-NPQR", redeemed: true }}] }})),
        strip(giftHTML({{ on: false, gifts: [] }})),
        strip(giftHTML({{ on: true, gifts: [] }}, true)),
        giftHTML({{ on: true, gifts: [{{ code: "GIFT-ABCD-EFGH", redeemed: false }}] }}),
      ]));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    on, off, back, raw = json.loads(out.stdout)
    assert "Your gifts GIFT-ABCD-EFGH Not used yet" in on and "GIFT-JKLM-NPQR Used" in on and "Buy a month for a friend" in on
    assert "Gifts aren’t on yet." in off and "Buy a month" not in off
    assert back.startswith("Stripe is confirming the payment"), back
    assert 'data-gift-share="GIFT-ABCD-EFGH"' in raw


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
