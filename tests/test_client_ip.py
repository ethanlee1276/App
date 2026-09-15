"""Who the app thinks is calling, once Cloudflare is in front of Caddy.

Ethan put the live site behind Cloudflare on 2026-08-21 and turned on Bot
Fight Mode the same evening, hours after posting the site to Instagram.
That added a hop the address logic had never seen:

    browser → Cloudflare → Caddy → this app

`deploy/Caddyfile` REPLACES X-Forwarded-For with the peer Caddy saw, which
was the whole point before — the last hop is the one our own proxy wrote,
and a client cannot forge it. After Cloudflare, that peer is a Cloudflare
edge server, and the visitor's real address (which Cloudflare had sent)
was overwritten.

WHAT BREAKS, AND ONLY UNDER LOAD. `server.rate_ok` buckets by caller.
Every visitor through one Cloudflare point of presence became one caller:
300 API calls a minute and 20 sign-ins a minute shared by all of them.
A quiet site never notices. A site that just got posted to Instagram
starts handing 429s to paying customers, and the 429 says "slow down",
which is the opposite of what happened.

THE FIX IS NOT "TRUST CF-CONNECTING-IP". Any client can send that header.
Believing it on sight lets anybody pick their own rate-limit bucket, or
somebody else's. It is believed only when the machine that spoke to our
proxy was really Cloudflare, checked against their published ranges.

    python3 tests/test_client_ip.py
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import cfips                                    # noqa: E402

#: Two real Cloudflare ranges and one that is emphatically not.
CF_V4 = "173.245.48.0/20"
CF_V6 = "2400:cb00::/32"
EDGE = "173.245.48.9"
#: NOT the 203.0.113.0/24 documentation range these would normally use.
#: `cfips.visitor` refuses anything that is not a PUBLIC address, and the
#: documentation ranges are reserved, so a visitor addressed out of them
#: is correctly rejected — which made this file's first draft pass for the
#: wrong reason. Two arbitrary routable addresses instead.
VISITOR = "24.51.99.7"
VISITOR_2 = "77.13.201.4"
IMPOSTOR = "45.62.190.11"


def _list(tmp, body=None):
    p = os.path.join(tmp, "cf.txt")
    with open(p, "w") as fh:
        fh.write("# a comment\n\n%s\n" % (body if body is not None
                                          else "%s\n%s" % (CF_V4, CF_V6)))
    os.environ[cfips.ENV_PATH] = p
    cfips._CACHE["key"] = None
    return p


# --- the range list ---------------------------------------------------------
def test_with_no_list_installed_nothing_is_cloudflare():
    """Fail closed. A missing file costs accuracy; a file believed
    without being checked would cost the guarantee."""
    os.environ[cfips.ENV_PATH] = "/nonexistent/cf.txt"
    cfips._CACHE["key"] = None
    assert cfips.is_cloudflare(EDGE) is False
    assert cfips.ranges() == ()


def test_a_file_of_nonsense_is_not_a_list_of_ranges():
    with tempfile.TemporaryDirectory() as tmp:
        _list(tmp, "<html>404 Not Found</html>\nnot-an-ip\n")
        assert cfips.ranges() == ()
        assert cfips.is_cloudflare(EDGE) is False


def test_one_bad_line_does_not_cost_the_good_ones():
    with tempfile.TemporaryDirectory() as tmp:
        _list(tmp, "%s\n999.999.999.0/24\n%s\n" % (CF_V4, CF_V6))
        assert len(cfips.ranges()) == 2
        assert cfips.is_cloudflare(EDGE)


def test_membership_is_by_range_and_not_by_prefix_string():
    with tempfile.TemporaryDirectory() as tmp:
        _list(tmp)
        assert cfips.is_cloudflare("173.245.48.0")
        assert cfips.is_cloudflare("173.245.63.255")
        assert not cfips.is_cloudflare("173.245.64.0")
        assert cfips.is_cloudflare("2400:cb00::1")
        assert not cfips.is_cloudflare("2400:cb01::1")


def test_rubbish_addresses_are_answered_rather_than_raised():
    """This runs inside request handling. A header is arbitrary bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        _list(tmp)
        for junk in ("", "   ", "not-an-ip", "1.2.3", "::::", "٣.٤.٥.٦"):
            assert cfips.is_cloudflare(junk) is False


def test_the_list_is_reread_when_it_changes_without_a_restart():
    with tempfile.TemporaryDirectory() as tmp:
        p = _list(tmp, CF_V4)
        assert cfips.is_cloudflare(EDGE)
        time.sleep(0.01)
        with open(p, "w") as fh:
            fh.write("192.0.2.0/24\n")
        assert not cfips.is_cloudflare(EDGE), (
            "a refreshed list needs a restart to take effect")


# --- the server -------------------------------------------------------------
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Site:
    """A real server, asked real questions over a real socket. The whole
    point is the header handling, and a unit test of `_client_ip` in
    isolation would not exercise it."""

    def __init__(self, cf_list):
        self.dir = tempfile.mkdtemp(prefix="qb-ip-")
        self.port = _free_port()
        env = dict(os.environ)
        env.update({
            "QB_ACCOUNTS_DB": os.path.join(self.dir, "a.db"),
            "QB_CF_IPS": cf_list,
            "QB_PAYWALL": "",
            "QB_COMP_EMAILS": "",
        })
        self.proc = subprocess.Popen(
            [sys.executable, "server.py", "--port", str(self.port)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        self.base = "http://127.0.0.1:%d" % self.port
        end = time.time() + 40
        while time.time() < end:
            if self.proc.poll() is not None:
                raise AssertionError("server died:\n"
                                     + (self.proc.stdout.read() or "")[:1200])
            try:
                self.get("/api/billing/status")
                return
            except Exception:                                # noqa: BLE001
                time.sleep(0.25)
        raise AssertionError("server never answered")

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def burst(self, n, headers=None):
        """How many of n requests came back 429."""
        return sum(self.get("/api/billing/status", headers)[0] == 429
                   for _ in range(n))

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


def _cf_file():
    fd, p = tempfile.mkstemp(prefix="cf-", suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        fh.write("%s\n%s\n" % (CF_V4, CF_V6))
    return p


def test_two_visitors_behind_one_cloudflare_edge_are_two_callers():
    """The bug, stated as a measurement. Both requests arrive from the
    same edge address; only the CF-Connecting-IP tells them apart, and
    before this fix nothing read it."""
    from server import RATE_READ_PER_MIN as LIMIT
    cf = _cf_file()
    site = Site(cf)
    try:
        # One visitor spends the whole budget.
        hot = {"X-Forwarded-For": EDGE, "CF-Connecting-IP": VISITOR}
        site.burst(LIMIT + 5, hot)
        assert site.get("/api/billing/status", hot)[0] == 429, (
            "the limiter did not engage at all, so this proves nothing")
        # A different visitor, same edge, arriving in the same minute.
        cold = {"X-Forwarded-For": EDGE, "CF-Connecting-IP": VISITOR_2}
        code, _ = site.get("/api/billing/status", cold)
        assert code == 200, (
            "a second visitor through the same Cloudflare edge was refused "
            "because the first one was busy — this is the launch-day "
            "failure the fix exists to prevent")
    finally:
        site.stop()
        os.unlink(cf)


def test_a_forged_cf_header_from_a_hop_that_is_not_cloudflare_is_ignored():
    """Otherwise anyone can choose their own bucket, or fill somebody
    else's. The header is only as good as the hop that sent it."""
    from server import RATE_READ_PER_MIN as LIMIT
    cf = _cf_file()
    site = Site(cf)
    try:
        forged = {"X-Forwarded-For": IMPOSTOR, "CF-Connecting-IP": VISITOR}
        site.burst(LIMIT + 5, forged)
        assert site.get("/api/billing/status", forged)[0] == 429
        # Same forged CF header, different claimed identity. If the header
        # were believed, changing it would hand out a fresh budget.
        again = {"X-Forwarded-For": IMPOSTOR,
                 "CF-Connecting-IP": VISITOR_2}
        assert site.get("/api/billing/status", again)[0] == 429, (
            "changing a header nobody verified bought a new rate-limit "
            "bucket")
    finally:
        site.stop()
        os.unlink(cf)


def test_with_no_list_the_behaviour_is_exactly_what_it_was_before():
    """The safety property of failing closed: installing this change on a
    box that has not run cfips.sh must change nothing."""
    from server import RATE_READ_PER_MIN as LIMIT
    site = Site("/nonexistent/cf.txt")
    try:
        a = {"X-Forwarded-For": EDGE, "CF-Connecting-IP": VISITOR}
        b = {"X-Forwarded-For": EDGE, "CF-Connecting-IP": VISITOR_2}
        site.burst(LIMIT + 5, a)
        assert site.get("/api/billing/status", b)[0] == 429, (
            "without the list these must share a bucket, as they did "
            "before the change — anything else is a surprise")
    finally:
        site.stop()


def test_a_direct_caller_cannot_claim_to_be_local():
    """The guarantee that was already here, still holding. `_local_only`
    gates granting and revoking Yahoo access."""
    cf = _cf_file()
    site = Site(cf)
    try:
        code, body = site.get("/api/yahoo/start", {
            "X-Forwarded-For": EDGE, "CF-Connecting-IP": "127.0.0.1"})
        assert code == 403, (
            "a caller claiming 127.0.0.1 through Cloudflare was treated as "
            "local: %s" % body[:200])
    finally:
        site.stop()
        os.unlink(cf)


def test_an_address_a_visitor_cannot_have_is_refused():
    """Found by this file on the first run after the header was wired up:
    `CF-Connecting-IP: 127.0.0.1` made `_local_only` true, which is the
    guard on granting and revoking Yahoo access. Cloudflare never reports
    a visitor as loopback, or as a LAN address, or out of a reserved
    range — so none of those are accepted as one."""
    for bad in ("127.0.0.1", "::1", "10.0.0.4", "192.168.1.9", "172.16.3.3",
                "169.254.1.1", "203.0.113.5", "2001:db8::1", "100.64.0.1",
                "", "   ", "not-an-ip"):
        assert cfips.visitor(bad) == "", "accepted %r as a visitor" % bad
    for good in (VISITOR, VISITOR_2, IMPOSTOR, "2606:4700::1111"):
        assert cfips.visitor(good) == good


def test_the_local_only_guard_still_needs_a_real_local_request():
    cfips._CACHE["key"] = None
    assert cfips.visitor("127.0.0.1") == ""


# --- the installer ----------------------------------------------------------
def test_the_installer_refuses_a_short_list():
    """A stub page served as 200, or a truncated download. Installing it
    would quietly turn the fix off."""
    src = open(os.path.join(ROOT, "deploy", "cfips.sh")).read()
    assert "refusing to install" in src
    assert "len(v4) < 10" in src, "no floor on how short a list may be"
    assert "not CIDRs" in src, "unparseable lines are installed anyway"


def test_the_installer_validates_before_it_overwrites():
    src = open(os.path.join(ROOT, "deploy", "cfips.sh")).read()
    i = src.index("install -m 644")
    assert "refusing to install" in src[:i], (
        "the destination is overwritten before the download is checked")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
