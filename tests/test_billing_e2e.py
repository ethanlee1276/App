"""The whole purchase, over real HTTP, against a real server process.

THE ONE THING UNIT TESTS CANNOT TELL YOU. Every piece of this is already
tested in isolation — the signature verifier, the event reader, the
storage layer, the entitlement rule — and all of them passed on the day
the site was wired to the wrong processor's header name. A verifier that
works and is never called looks identical to one that works.

So this starts `server.py` on an ephemeral port, signs an account up
through the API, fires a webhook signed the way Stripe signs one, and
checks that the account's entitlement moved. Nothing is mocked on this
side of the wire; the only thing standing in for Stripe is the HMAC,
which is the part Stripe's own docs specify byte for byte.

WHAT IT STILL CANNOT PROVE is that Stripe agrees with the Checkout
request we build — this container cannot reach api.stripe.com, and step 4
below asserts only that the failure is a clean 502 rather than a
traceback. The live-fire check with card 4242 4242 4242 4242 has no
substitute and docs/BILLING.md says so where it matters.

RUNS AGAINST A TEMPORARY DATABASE, via QB_ACCOUNTS_DB. Signing a test
account up into the file real accounts live in is how a test deletes
somebody.

AND AGAINST A TEMPORARY web/, via QB_WEB_DIR, for the same reason one step
over. This fixture boots with QB_PAYWALL=1, and `server.py` seals the
public path at startup: every paid board in the web directory it is given
is rewritten in place with its picks removed. Pointed at the working copy
— which it was until 2026-08-31 — that meant running this file emptied
whatever boards the machine had built, and in a parallel suite run it
raced whichever test was writing one (test_side_bias, intermittently
red). A test that redacts your real boards as a side effect is a worse
bug than the one it is checking for.

    python3 tests/test_billing_e2e.py
"""

import hashlib
import hmac
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
sys.path.insert(0, ROOT)

WEBHOOK_SECRET = "whsec_e2e_not_a_real_secret"
BOOT_TIMEOUT = 45


def _free_port() -> int:
    """Ask the OS for one instead of picking a number.

    A hardcoded port fails as "Address already in use" the second time
    the suite runs on a machine where the first run left something
    behind, and that failure reads like a code fault.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _not_the_real_boards(directory, names):
    """copytree filter: take all of web/ except its data directory.

    Only the top-level web/data is skipped — a `data` folder nested
    deeper is a real asset and gets copied. Same filter, same reason, as
    tests/test_paywall_live.py."""
    web = os.path.abspath(os.path.join(ROOT, "web"))
    if os.path.abspath(directory) == web:
        return {"data"} & set(names)
    return set()


class Server:
    def __init__(self):
        self.port = _free_port()
        self.dir = tempfile.mkdtemp(prefix="qb-e2e-")
        self.db = os.path.join(self.dir, "accounts.db")
        # A web/ of our own, minus the boards. Nothing below reads a
        # board, so an empty data directory is the whole requirement —
        # and an empty one cannot be sealed, which is the point.
        self.web = os.path.join(self.dir, "web")
        shutil.copytree(os.path.join(ROOT, "web"), self.web,
                        ignore=_not_the_real_boards)
        os.makedirs(os.path.join(self.web, "data"), exist_ok=True)
        env = dict(os.environ)
        env.update({
            "QB_ACCOUNTS_DB": self.db,
            "QB_WEB_DIR": self.web,
            "STRIPE_SECRET_KEY": "sk_test_e2e",
            "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
            "STRIPE_PRICE_MONTHLY": "price_m",
            "STRIPE_PRICE_SIXMONTH": "price_s",
            "STRIPE_PRICE_YEARLY": "price_y",
            "QB_PAYWALL": "1",
            # DELIBERATELY EMPTY. A comp list with anybody on it would
            # grant entitlement before the webhook does and every
            # assertion below would pass for the wrong reason.
            "QB_COMP_EMAILS": "",
        })
        self.env = env
        self.proc = subprocess.Popen(
            [sys.executable, "server.py", "--port", str(self.port)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        self.base = f"http://127.0.0.1:{self.port}"
        self._wait()

    def _wait(self):
        end = time.time() + BOOT_TIMEOUT
        while time.time() < end:
            if self.proc.poll() is not None:
                raise AssertionError(
                    "the server exited during boot:\n"
                    + (self.proc.stdout.read() or "")[:2000])
            try:
                self.get("/api/billing/status")
                return
            except Exception:                            # noqa: BLE001
                time.sleep(0.25)
        raise AssertionError("the server never answered")

    def _call(self, path, data=None, cookie=None, headers=None):
        h = dict(headers or {})
        if cookie:
            h["Cookie"] = cookie
        body = None
        if data is not None:
            body = data if isinstance(data, bytes) else json.dumps(data).encode()
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(
            self.base + path, data=body, headers=h,
            method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read().decode(), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(), exc.headers.get("Set-Cookie")

    def get(self, path, cookie=None):
        return self._call(path, None, cookie)

    def post(self, path, data, cookie=None, headers=None):
        return self._call(path, data, cookie, headers)

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


def _signed(payload: bytes, secret=WEBHOOK_SECRET, ts=None):
    ts = int(time.time()) if ts is None else int(ts)
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload,
                   hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={mac}",
            "Content-Type": "application/json"}


def _user_id(db_path, email):
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT id FROM users WHERE email=?",
                           (email,)).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def main():
    srv = Server()
    steps = []

    def step(name):
        steps.append(name)
        print(f"  ok  {name}")

    try:
        # --- the fixture is not the machine ------------------------------
        # ASSERTED ON THE FIXTURE, NOT ON THE DISK. The tempting check is
        # to fingerprint the working copy's web/data before and after the
        # boot and demand it be unchanged — but the suite runs eight files
        # at a time and test_side_bias legitimately writes a board into
        # that directory, so that check would fail for a reason that has
        # nothing to do with this file. This asserts the structure that
        # makes the damage impossible instead, which is true whatever else
        # is running.
        served = os.path.realpath(srv.env["QB_WEB_DIR"])
        real = os.path.realpath(os.path.join(ROOT, "web"))
        assert served != real and not served.startswith(real + os.sep), \
            f"the paywalled fixture is serving the working copy: {served}"
        assert not [n for n in os.listdir(os.path.join(srv.web, "data"))
                    if n.endswith(".json")], \
            "the fixture copied the machine's boards in, so the startup " \
            "seal has something of Ethan's to strip"
        step("a paywalled server is pointed away from the real boards")

        # --- what an anonymous visitor is told ---------------------------
        code, body, _ = srv.get("/api/billing/status")
        assert code == 200, body
        st = json.loads(body)
        assert st["configured"] is True, "the server does not see the keys"
        assert st["live"] is False, \
            "a test key reported as live mode — nobody would know if it were"
        assert st["paywall"] is True
        got = {p["id"]: p for p in st["plans"]}
        assert set(got) == {"monthly", "sixmonth", "yearly"}
        assert [got[k]["price"] for k in ("monthly", "sixmonth", "yearly")] \
            == [25.0, 125.0, 225.0]
        assert all(p["ready"] for p in got.values())
        step("the plans and their prices reach the page")

        # --- checkout needs an account -----------------------------------
        code, body, _ = srv.post("/api/billing/checkout", {"plan": "yearly"})
        assert code == 401, f"anonymous checkout returned {code}: {body}"
        step("checkout refuses an anonymous caller")

        code, body, cookie = srv.post("/api/account/signup", {
            "email": "e2e@example.com", "password": "correct-horse-battery",
            "confirmed": True})
        assert code == 200, body
        ck = (cookie or "").split(";")[0]
        uid = _user_id(srv.db, "e2e@example.com")
        assert uid, "the account was not written"
        step("an account can be created")

        # --- the Stripe call itself --------------------------------------
        code, body, _ = srv.post("/api/billing/checkout", {"plan": "yearly"}, ck)
        assert code == 502, f"expected a clean 502, got {code}: {body}"
        assert "error" in json.loads(body), "no message for the page to show"
        step("an unreachable Stripe is a 502 with a sentence, not a crash")

        # THE EXPENSIVE FAILURE. Substituting a known price for an unknown
        # plan charges $25 to somebody who believes they bought a year.
        code, body, _ = srv.post("/api/billing/checkout", {"plan": "lifetime"}, ck)
        assert code == 502 and "plan" in body.lower(), \
            f"an unknown plan was not refused: {code} {body}"
        step("an unknown plan is refused rather than priced as something else")

        # --- the webhook, which is the only thing that grants -------------
        assert json.loads(srv.get("/api/billing/status", ck)[1])["entitled"] \
            is not True
        step("the account starts unentitled")

        code, body, _ = srv.post("/api/billing/webhook", {"id": "evt_forged"})
        assert code == 400, f"an unsigned webhook returned {code}"
        step("an unsigned webhook is refused")

        payload = json.dumps({
            "id": "evt_e2e_1", "type": "checkout.session.completed",
            "data": {"object": {
                "client_reference_id": str(uid), "customer": "cus_e2e",
                "subscription": "sub_e2e", "payment_status": "paid",
                "metadata": {"plan": "yearly"}}}}).encode()
        forged = dict(_signed(payload))
        forged["Stripe-Signature"] = forged["Stripe-Signature"][:-1] + (
            "0" if forged["Stripe-Signature"][-1] != "0" else "1")
        code, body, _ = srv.post("/api/billing/webhook", payload, headers=forged)
        assert code == 400, f"a tampered signature was accepted: {code}"
        assert json.loads(srv.get("/api/billing/status", ck)[1])["entitled"] \
            is not True
        step("a tampered signature grants nothing")

        code, body, _ = srv.post("/api/billing/webhook", payload,
                                 headers=_signed(payload))
        assert code == 200, f"{code}: {body}"
        assert json.loads(body).get("applied") is True, body
        st = json.loads(srv.get("/api/billing/status", ck)[1])
        assert st["entitled"] is True, "the signed webhook did not grant access"
        assert st["plan"] == "yearly", f"the plan did not survive: {st}"
        assert st["plan_name"] == "Yearly"
        step("a signed webhook grants access and records the plan")

        # Stripe delivers at least once, not exactly once.
        code, body, _ = srv.post("/api/billing/webhook", payload,
                                 headers=_signed(payload))
        assert code == 200 and json.loads(body).get("duplicate") is True, body
        step("a replayed event is a no-op, not a second grant")

        # --- and it can be taken away ------------------------------------
        gone = json.dumps({
            "id": "evt_e2e_2", "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_e2e", "customer": "cus_e2e",
                                "status": "canceled"}}}).encode()
        code, body, _ = srv.post("/api/billing/webhook", gone,
                                 headers=_signed(gone))
        assert code == 200, body
        st = json.loads(srv.get("/api/billing/status", ck)[1])
        assert st["entitled"] is False, "a cancelled subscription still reads in"
        step("a cancellation closes the account's access again")

        # --- ?paid=1 is a claim, not a grant ------------------------------
        # The whole return-trip design rests on this: anybody can type it.
        code, body, _ = srv.get("/?paid=1")
        st = json.loads(srv.get("/api/billing/status", ck)[1])
        assert st["entitled"] is False, \
            "loading the success URL granted entitlement by itself"
        step("the success URL grants nothing on its own")

    finally:
        srv.stop()

    return steps


if __name__ == "__main__":
    # The footer is printed HERE, not inside main(), because
    # `run_tests.py` counts "N tests passed." and tests/test_runner.py
    # only looks below this line for it — a file that prints the footer
    # from a helper is scored zero and nothing about the output looks
    # wrong. Found by that test, which is the whole reason it exists.
    print(f"\n{len(main())} tests passed.")
