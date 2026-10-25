"""Referral codes (engine/referrals): who gets one, what it refuses, and a
credit that is paid once.

Ethan, 2026-10-25: the new member gets 25% off one month, the member who
shared the code 25% off their next. Both as $6.25 — see the module's
docstring for why never a percentage.

    python3 tests/test_referrals.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import referrals as R                              # noqa: E402


def _db(n=4):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    for i in range(1, n + 1):
        conn.execute("INSERT INTO users (id, email) VALUES (?, ?)", (i, f"u{i}@example.com"))
    conn.commit()
    return conn


def test_a_member_gets_a_code_and_a_free_account_does_not():
    conn = _db()
    assert R.code_for(conn, 2, member=False) is None
    code = R.code_for(conn, 1, member=True)
    assert code and len(code) == R.CODE_LEN and R.CODE_RE.match(code)
    assert not set(code) & set("01OIL"), "a code is read off one phone and typed on another"
    assert R.code_for(conn, 1, member=True) == code, "the same code every time"
    assert R.code_for(conn, 1, member=False) == code, "a lapse keeps the code links already carry"


def test_a_code_is_typed_by_hand():
    conn = _db()
    code = R.code_for(conn, 1, member=True)
    assert R.owner_of(conn, f" {code[:3].lower()}-{code[3:].lower()} ") == 1
    assert R.owner_of(conn, "") is None and R.owner_of(conn, "NOPE!!") is None


def test_what_attach_refuses():
    conn = _db()
    code = R.code_for(conn, 1, member=True)
    assert R.attach(conn, 1, code)[0] is False, "its own code"
    assert R.attach(conn, 2, "ZZZZZZZ")[0] is False, "an unknown code"
    assert R.attach(conn, 3, code, subscribed_before=True)[0] is False, "after a first membership"
    ok, why = R.attach(conn, 2, code)
    assert ok and "$6.25" in why
    other = R.code_for(conn, 4, member=True)
    assert R.attach(conn, 2, other)[0] is False, "a second code on one account"


def test_the_discount_is_for_a_first_membership_and_once():
    conn = _db()
    code = R.code_for(conn, 1, member=True)
    R.attach(conn, 2, code)
    assert R.discount_for(conn, 2, subscribed_before=False) == R.COUPON_ID
    assert R.discount_for(conn, 2, subscribed_before=True) == ""
    assert R.discount_for(conn, 3, subscribed_before=False) == "", "no code, no coupon"
    R.discount_taken(conn, 2)
    assert R.discount_for(conn, 2, subscribed_before=False) == ""


def test_the_referrer_is_credited_once_however_often_it_is_told():
    conn = _db()
    code = R.code_for(conn, 1, member=True)
    R.attach(conn, 2, code)
    assert R.first_payment(conn, 3) is None, "not referred"
    assert R.first_payment(conn, 2) == 1
    assert R.first_payment(conn, 2) is None, "a retried webhook owes nothing new"
    calls = []

    def credit(cus, cents, key, note):
        calls.append((cus, cents, key))
        return "cbtxn_1"
    assert R.settle(conn, lambda uid: "cus_A" if uid == 1 else None, credit) == 1
    assert R.settle(conn, lambda uid: "cus_A", credit) == 0, "paid already"
    assert calls == [("cus_A", 625, "qb-referral-credit-2")]


def test_a_referrer_not_paying_right_now_is_owed_and_paid_later():
    conn = _db()
    code = R.code_for(conn, 1, member=True)
    R.attach(conn, 2, code)
    R.first_payment(conn, 2)
    assert R.settle(conn, lambda uid: None, lambda *a: "x") == 0
    assert R.owed(conn) == [(2, 1)]
    assert R.summary(conn, 1, member=False)["waiting_cents"] == 625
    assert R.settle(conn, lambda uid: "cus_A", lambda *a: "x") == 1
    s = R.summary(conn, 1, member=True)
    assert s["credited_cents"] == 625 and s["waiting_cents"] == 0 and s["joined"] == 1 and s["paid"] == 1


def test_a_failed_credit_stays_owed():
    conn = _db()
    code = R.code_for(conn, 1, member=True)
    for friend in (2, 3):
        R.attach(conn, friend, code)
        R.first_payment(conn, friend)

    def credit(cus, cents, key, note):
        if key.endswith("-2"):
            raise RuntimeError("Stripe said no")
        return "ok"
    assert R.settle(conn, lambda uid: "cus_A", credit) == 1
    assert R.owed(conn) == [(2, 1)]


def test_the_money_is_a_quarter_of_the_month_on_every_plan():
    from engine import billing
    month = billing.PLANS["monthly"]["cents"]
    assert R.NEW_MEMBER_OFF_CENTS == R.REFERRER_CREDIT_CENTS == month // 4


# --- the money, through Stripe ---------------------------------------------
def test_a_referred_checkout_carries_the_coupon_and_no_promo_box():
    from engine import billing as BI
    from urllib.parse import parse_qs
    _u, _h, body = BI.checkout_request("sk_x", "price_1", 7, "you@example.com", "s", "c", "monthly",
                                       trial_days=3, allow_promo=True, coupon=R.COUPON_ID)
    q = parse_qs(body.decode())
    assert q["discounts[0][coupon]"] == [R.COUPON_ID]
    assert "allow_promotion_codes" not in q, "Stripe takes a coupon or the box, never both"
    _u, _h, plain = BI.checkout_request("sk_x", "price_1", 7, "you@example.com", "s", "c", "monthly")
    assert "discounts" not in plain.decode()


def test_the_coupon_is_an_amount_for_one_month_never_a_percentage():
    from engine import billing as BI
    from urllib.parse import parse_qs
    url, head, body = BI.referral_coupon_request("sk_x")
    q = parse_qs(body.decode())
    assert url.endswith("/coupons") and q["id"] == [R.COUPON_ID]
    assert q["amount_off"] == ["625"] and q["currency"] == ["usd"] and "percent_off" not in q
    assert q["duration"] == ["repeating"] and q["duration_in_months"] == ["1"]


def test_the_referrers_credit_is_a_negative_balance_with_its_own_key():
    from engine import billing as BI
    from urllib.parse import parse_qs
    url, head, body = BI.credit_request("sk_x", "cus_A", 625, "qb-referral-credit-2", "Referral credit")
    assert url.endswith("/customers/cus_A/balance_transactions")
    assert parse_qs(body.decode())["amount"] == ["-625"]
    assert head["Idempotency-Key"] == "qb-referral-credit-2"


def test_a_membership_going_active_owes_the_referrer():
    from engine import billing as BI
    conn = _db()
    conn.row_factory = sqlite3.Row
    BI.init(conn)
    code = R.code_for(conn, 1, member=True)
    R.attach(conn, 2, code)
    paid = []
    keep = (BI.settle_referrals, BI.configured)
    BI.settle_referrals = lambda c: paid.append(1) or 1
    BI.configured = lambda: True
    try:
        BI.apply_event(conn, {"user_id": 2, "customer_id": "cus_B", "subscription_id": "sub_1",
                              "status": "trialing", "at": 1.0})
        assert not paid and R.owed(conn) == [], "a trial is not a payment"
        BI.apply_event(conn, {"user_id": 2, "customer_id": "cus_B", "subscription_id": "sub_1",
                              "status": "active", "at": 2.0})
        assert paid == [1] and R.owed(conn) == [(2, 1)]
        BI.apply_event(conn, {"user_id": 2, "customer_id": "cus_B", "subscription_id": "sub_1",
                              "status": "active", "at": 3.0})
        assert paid == [1], "a renewal owes nothing new"
    finally:
        BI.settle_referrals, BI.configured = keep
    launch = (ROOT / "launch.py").read_text()
    assert "_bi.settle_referrals(conn)" in launch, "the sweep pays what the webhook could not"


def test_the_server_attaches_at_sign_up_and_discounts_at_checkout():
    srv = (ROOT / "server.py").read_text()
    sign = srv[srv.index('            if path in ("signup", "login"):'):srv.index("            token = self._cookie(SESSION_COOKIE)")]
    assert "RF.attach(conn, out[\"id\"], body.get(\"ref\"))" in sign
    assert sign.index("A.create_user(") < sign.index("RF.attach("), "the account exists first"
    buy = srv[srv.index("fresh = not BI.has_subscribed_before(conn, who[\"id\"])"):]
    buy = buy[:buy.index("else:")]
    assert "RF.discount_for(conn, who[\"id\"], not fresh)" in buy and "BI.ensure_referral_coupon()" in buy
    assert "allow_promo=fresh and not coupon, coupon=coupon" in buy
    assert '"lastleg", "referral"):' in srv
    get = srv[srv.index('            if path == "referral":'):]
    assert "member=self._entitled(conn, who)" in get[:600] and '/?ref={out[' in get[:600]


def test_the_page_offers_it_both_ways():
    acct = (ROOT / "web" / "js" / "account.js").read_text()
    app = (ROOT / "web" / "js" / "app.js").read_text()
    assert 'data-set-open="invite"' in acct and "async function invFill(" in acct
    assert 'class="acct-ref"' in acct and "value=\"${escapeAttr(referralTyped())}\"" in acct
    assert 'ref: ((card.querySelector(".acct-ref") || {}).value || referralTyped()).trim()' in app
    assert "/^[A-Za-z0-9]{4,16}$/.test(ref)" in app, "a ?ref= link is kept only when it looks like a code"


def test_deleting_an_account_takes_its_chat_alerts_and_referrals_with_it():
    """The Privacy Policy says the account's rows go with it (§7); the game
    chat, the per-account alert rows and both sides of a referral were the
    tables delete_user had never heard of."""
    import tempfile
    from engine import accounts as A, gamechat as GC
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(Path(d) / "a.db")
        uids = []
        for i in range(3):
            code, out = A.create_user(conn, f"p{i}@example.com", "a long enough password", confirmed=True)
            uids.append(out["id"])
        me, friend, other = uids
        GC.ensure_tables(conn)
        conn.execute("INSERT INTO chat_msgs (room, user_id, body, created_at) VALUES ('nfl_1', ?, 'hi', 1)", (me,))
        mid = conn.execute("SELECT id FROM chat_msgs").fetchone()[0]
        conn.execute("INSERT INTO chat_reacts (msg_id, user_id, room, kind, changed_at) VALUES (?, ?, 'nfl_1', 'fire', 1)", (mid, other))
        conn.execute("INSERT INTO chat_votes (room, user_id, side, changed_at) VALUES ('nfl_1', ?, 'home', 1)", (me,))
        conn.commit()
        R.attach(conn, friend, R.code_for(conn, me, member=True))
        mine = A.export_user(conn, me)
        assert mine["game_chat_messages"][0]["body"] == "hi" and mine["referral_code"]
        assert A.export_user(conn, friend)["joined_with_referral_code"]["code"] == mine["referral_code"]
        A.delete_user(conn, me)
        for table, where in (("chat_msgs", ""), ("chat_reacts", ""), ("chat_votes", ""), ("referral_codes", ""),
                             ("referrals", "")):
            n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            assert n == 0, f"{table} kept {n} row(s) after the account went"


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
