"""TWO PLACES ANSWER "is this reader entitled", and they must agree.

`Handler._entitled` decides whether a full board goes out. It checks, in
order: is the gate even on, is anybody signed in, is the address on the
comp list, is there a redeemed code, is there a live subscription.

`/api/billing/status` is what the BROWSER asks, and it is what decides
whether the wall is drawn. It knew about codes and subscriptions. It did
not know about the comp list.

So a comped address was served unredacted boards by `_entitled` and told
`entitled: false` by the status endpoint. The browser believed the
endpoint, put the wall up, and drew a plans page on top of data the
reader was already entitled to — asking somebody for money for something
they had been given. The comp list is how Ethan gets into his own site
and how anyone is let in without a card, so this was live the whole time
the wall has been up.

The two answers are one question. This file asks it both ways.

    python3 tests/test_entitlement_agreement.py
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOT_TIMEOUT = 40
COMP = "comped@example.com"
PLAIN = "paying-nothing@example.com"
PASSWORD = "a-long-enough-password"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _call(url, payload=None, cookie=None):
    """Returns (status, body, set-cookie)."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode(), r.headers.get("Set-Cookie")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), exc.headers.get("Set-Cookie")


def _not_the_real_boards(directory, names):
    """copytree filter: take all of web/ except its data directory.

    Only the top-level web/data is skipped — a `data` folder nested
    deeper is a real asset and gets copied. The same filter
    tests/test_paywall_live.py uses, and for a narrower reason here.

    NOTHING IN THIS FILE READS A BOARD: every assertion below is about
    what `/api/billing/status` says. So unlike that file, the verdict was
    never a reading of the disk. What the copy did do was hand the server
    a duplicate of whatever boards this machine had built, which it then
    SEALS at startup — four times, once per `Site`, inside a 40-second
    boot timeout, on a directory whose size is a property of the laptop
    rather than of the code. A test that gets slower as its author builds
    more boards eventually goes red for a reason nobody can read off the
    failure.

    It also stopped the server writing full copies of Ethan's real boards
    into a temp tree at all, which no test needs to do."""
    web = os.path.abspath(os.path.join(ROOT, "web"))
    if os.path.abspath(directory) == web:
        return {"data"} & set(names)
    return set()


class Site:
    def __init__(self, comp=COMP):
        self.dir = tempfile.mkdtemp(prefix="qb-ent-")
        self.web = os.path.join(self.dir, "web")
        shutil.copytree(os.path.join(ROOT, "web"), self.web,
                        ignore=_not_the_real_boards)
        self.port = _free_port()
        env = dict(os.environ)
        env.update({
            "QB_ACCOUNTS_DB": os.path.join(self.dir, "accounts.db"),
            "QB_WEB_DIR": self.web,
            "QB_PAYWALL": "1",
            "QB_COMP_EMAILS": comp,
            "STRIPE_SECRET_KEY": "sk_test_ent",
            "STRIPE_WEBHOOK_SECRET": "whsec_ent",
            "STRIPE_PRICE_MONTHLY": "price_m",
        })
        self.proc = subprocess.Popen(
            [sys.executable, "server.py", "--port", str(self.port)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        self.base = "http://127.0.0.1:%d" % self.port
        end = time.time() + BOOT_TIMEOUT
        while time.time() < end:
            if self.proc.poll() is not None:
                raise AssertionError("server died:\n"
                                     + (self.proc.stdout.read() or "")[:1500])
            try:
                _call(self.base + "/api/billing/status")
                return
            except Exception:                                # noqa: BLE001
                time.sleep(0.25)
        raise AssertionError("server never answered")

    def signup(self, email):
        code, body, cookie = _call(
            self.base + "/api/account/signup",
            {"email": email, "password": PASSWORD, "confirmed": True})
        assert code == 200, "signup failed (%s): %s" % (code, body[:300])
        assert cookie, "signup returned no session cookie"
        return cookie.split(";")[0]

    def status(self, cookie=None):
        code, body, _ = _call(self.base + "/api/billing/status",
                              cookie=cookie)
        assert code == 200, body[:300]
        return json.loads(body)

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


def test_a_comped_address_is_told_it_is_entitled():
    site = Site()
    try:
        st = site.status(site.signup(COMP))
        assert st["entitled"] is True, (
            "the comp list lets this address read full boards, and the "
            "status endpoint says it has nothing: %r" % st)
        assert st.get("comped") is True, (
            "entitled, but the page cannot tell a comp from a purchase — "
            "the account page would offer to manage a subscription that "
            "does not exist")
    finally:
        site.stop()


def test_a_comped_account_is_not_told_it_has_no_subscription():
    """`status_for` reads the subscriptions table, which has no row for a
    comped address, so its sentence is "No subscription." — printed in the
    entitled style beside a site that works."""
    site = Site()
    try:
        st = site.status(site.signup(COMP))
        assert "no subscription" not in (st.get("note") or "").lower(), (
            "entitled, and told it has nothing: %r" % st.get("note"))
        assert st.get("note"), "entitled and told nothing at all"
        assert not st.get("customer_id"), (
            "a comp with a Stripe customer id is a real subscription and "
            "this test is measuring the wrong thing")
    finally:
        site.stop()


def test_an_address_that_is_not_comped_is_not():
    site = Site()
    try:
        st = site.status(site.signup(PLAIN))
        assert st["entitled"] is False, (
            "everybody is entitled, which is not a paywall: %r" % st)
        assert not st.get("comped")
    finally:
        site.stop()


def test_the_comp_list_is_matched_the_way_the_gate_matches_it():
    """`gate.comped` lowercases and strips both sides, because the list is
    typed by hand into a config file. The status endpoint has to inherit
    that rather than doing its own comparison."""
    site = Site(comp="  Comped@Example.COM , someone-else@example.com ")
    try:
        st = site.status(site.signup(COMP))
        assert st["entitled"] is True, (
            "a case difference in a hand-typed config file locked out a "
            "comped account: %r" % st)
    finally:
        site.stop()


def test_signed_out_is_never_entitled():
    site = Site()
    try:
        st = site.status()
        assert st["signed_in"] is False
        assert st.get("entitled") is not True
        assert "discord" not in st, (
            "the invite is in an anonymous response")
    finally:
        site.stop()


def test_the_status_says_who_it_is_talking_to():
    """The plans page shows the address so that a signed-in reader who has
    not subscribed is told they are signed in. Landing them on a page
    headed "Log in" is how this looked when Ethan reported that signing in
    never says it worked."""
    site = Site()
    try:
        st = site.status(site.signup(PLAIN))
        assert st.get("email") == PLAIN, (
            "the page has no way to say who is signed in: %r" % st)
    finally:
        site.stop()


def test_the_email_is_not_handed_to_strangers():
    site = Site()
    try:
        site.signup(PLAIN)
        assert "email" not in site.status(), (
            "an address in a response to somebody with no cookie")
    finally:
        site.stop()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
