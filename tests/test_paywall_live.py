"""Curl the running site with no cookie and see what comes back.

Ethan, 2026-08-21: *"make sure … no one can bypass the stripe paywall to
get on the site."*

THIS TEST EXISTS BECAUSE THE OTHER ONES PASSED. `tests/test_paywall_bypass.py`
walks the design and proves the rule is right: the file on the public path
IS the redacted one, so there is nothing in the served tree to leak. Every
assertion in it was true on the day a `curl` of the live site returned 293
picks to nobody at all.

The rule was never wrong. The TIMING was. Redaction happens inside
`publish()`, so turning `QB_PAYWALL` on changes what the next build writes
and touches nothing already on disk — and in production Caddy answers
/data/*.json off disk, so the app never sees the request and has no later
chance to catch it. Every board written before the flag went on stayed
whole and stayed public, indefinitely.

`launch.py --seal` always fixed it, and a paywall that depends on an
operator remembering a command is not a paywall. `server.py` now seals at
startup, because a restart is the one thing that reliably happens on every
deploy and on the config change that turns the flag on.

So this file starts a REAL server against a REAL data directory that has
NOT been sealed, and fetches like a stranger. Everything else is a proxy
for this. Real means a real server, a real directory on disk and a real
fetch over the wire — but the boards in that directory are PLANTED, not
the working copy's. web/data is gitignored, so reading it would make the
answer depend on which machine asked.

    python3 tests/test_paywall_live.py
"""

import json
import os
import re
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

from engine import gate                                       # noqa: E402

BOOT_TIMEOUT = 45

#: Not Ethan's real invite. This is a fixture, and the point is that a
#: stranger never receives whatever string is configured.
DISCORD_PROBE = "https://discord.gg/PROBEcode"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _not_the_real_boards(directory, names):
    """copytree filter: take all of web/ except its data directory.

    Only the top-level web/data is skipped — a `data` folder nested
    deeper is a real asset and gets copied."""
    web = os.path.abspath(os.path.join(ROOT, "web"))
    if os.path.abspath(directory) == web:
        return {"data"} & set(names)
    return set()


def _get(url, cookie=None):
    req = urllib.request.Request(url)
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


class Site:
    """A server on a temp copy of web/, with the paywall ON and the
    boards deliberately UNSEALED — the exact state the site was in when
    the leak was found."""

    def __init__(self, paywall=True):
        self.dir = tempfile.mkdtemp(prefix="qb-wall-")
        self.web = os.path.join(self.dir, "web")
        # web/data IS DELIBERATELY NOT COPIED. It is gitignored, so what
        # it holds is whatever the machine happened to build: Ethan's real
        # slate on the laptop, nothing at all in a fresh clone, and on a
        # box that has run this suite once, the leftovers of whichever
        # test last wrote a board into the tree. Copying it made this
        # file's verdict a reading of the disk rather than of the gate —
        # see FREE_PLANTED for the run where that went red on checkout.
        # The fixtures below are the whole data directory now.
        shutil.copytree(os.path.join(ROOT, "web"), self.web,
                        ignore=_not_the_real_boards)
        self.planted = _plant(os.path.join(self.web, "data"))
        self.port = _free_port()
        env = dict(os.environ)
        env.update({
            "QB_ACCOUNTS_DB": os.path.join(self.dir, "accounts.db"),
            "QB_WEB_DIR": self.web,
            "QB_PAYWALL": "1" if paywall else "",
            "QB_COMP_EMAILS": "",
            # A real-looking invite, so the checks below are testing the
            # gate rather than an unset variable.
            "QB_DISCORD_INVITE": DISCORD_PROBE,
            "STRIPE_SECRET_KEY": "sk_test_wall",
            "STRIPE_WEBHOOK_SECRET": "whsec_wall",
            "STRIPE_PRICE_MONTHLY": "price_m",
        })
        self.proc = subprocess.Popen(
            [sys.executable, "server.py", "--port", str(self.port)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        self.base = f"http://127.0.0.1:{self.port}"
        end = time.time() + BOOT_TIMEOUT
        while time.time() < end:
            if self.proc.poll() is not None:
                raise AssertionError("server died:\n"
                                     + (self.proc.stdout.read() or "")[:1500])
            try:
                _get(self.base + "/api/billing/status")
                return
            except Exception:                                # noqa: BLE001
                time.sleep(0.25)
        raise AssertionError("server never answered")

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


#: A board with paid rows in it, written into the temp tree so the test
#: does not depend on the state of anybody's working copy.
#:
#: IT USED TO READ `web/data` DIRECTLY and assert it was unsealed. That
#: made the result depend on whether anything had previously started a
#: server with QB_PAYWALL set — which seals the tree, correctly — so the
#: test passed or failed on the order it was run in. A test that is right
#: only when nothing else ran first is not measuring the thing it claims.
PLANTED = {
    "recommendations.json": {
        "generated_at": "2026-08-21T00:00:00Z",
        "games": [{"home": "DET", "away": "GB", "kickoff": "2026-09-07"}],
        "recommendations": [
            {"player": "Test Player", "market": "receptions",
             "side": "over", "line": 4.5, "price": -115, "edge_pts": 6.2,
             "confidence": 7.1, "book": "TestBook"},
            {"player": "Other Player", "market": "rush_yds",
             "side": "under", "line": 58.5, "price": -110, "edge_pts": 4.4,
             "confidence": 6.3, "book": "TestBook"},
        ],
        "game_bets": [
            {"game": "DET@GB", "market": "spread", "side": "DET",
             "line": -3.0, "price": -110, "edge_pts": 3.1},
        ],
    },
}


#: The FREE half, planted for the same reason the paid half is.
#:
#: `record.json` is free by design — it is the evidence the subscription
#: is sold on — and the check below fetches it to prove the seal did not
#: take the free half down with the paid one. It used to arrive via the
#: copytree, out of the working copy's gitignored web/data, and that made
#: this file answer a question about the machine instead of the code:
#:
#:   fresh clone      no web/data at all, so /data/record.json was a 404
#:                    and the suite was RED on checkout
#:   after one run    some other test had written a board into the repo's
#:                    web/data, record.json now existed, and the identical
#:                    commit went GREEN
#:
#: Same code, opposite verdicts, decided by what happened to be on disk —
#: and the green one is the dangerous direction, because it is the one
#: that looks like a passing gate. Planted, the check reads the gate.
FREE_PLANTED = {
    "record.json": {
        "generated_at": "2026-08-21T00:00:00Z",
        "overall": {"settled": 41, "wins": 23, "losses": 17, "pushes": 1,
                    "win_rate": 0.575},
        "recent": [{"player": "Test Player", "market": "receptions",
                    "side": "over", "line": 4.5, "result": "win",
                    "graded_at": "2026-08-20"}],
    },
}


def _plant(data_dir):
    """Write the fixture boards, paid and free. Returns the PAID names.

    The return value feeds the leak checks, which are only meaningful
    against boards that carry paid rows, so the free fixtures are written
    but not returned."""
    os.makedirs(data_dir, exist_ok=True)
    for name, payload in PLANTED.items():
        assert not gate.is_free(name), \
            f"{name} is free by design, so planting it proves nothing"
        with open(os.path.join(data_dir, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    for name, payload in FREE_PLANTED.items():
        assert gate.is_free(name), \
            f"{name} is paid, so fetching it below tests the lock rather " \
            "than the free half it is supposed to prove still works"
        with open(os.path.join(data_dir, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    return sorted(PLANTED)


def _paid_boards(web_dir):
    """Boards that carry paid rows right now, straight off disk."""
    out = {}
    data = os.path.join(web_dir, "data")
    for name in sorted(os.listdir(data)) if os.path.isdir(data) else []:
        if not name.endswith(".json") or gate.is_free(name):
            continue
        try:
            with open(os.path.join(data, name), encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            n = gate._paid_rows(payload, name)
            if n:
                out[name] = n
    return out


def test_every_entrypoint_seals(steps):
    """BOTH ways the site can be started, not just the one under test.

    The seal was written into `server.main()` and it worked — in dev.
    Production runs `launch.py`, which builds its own ThreadingHTTPServer
    around the same Handler and never calls `server.main()`, so on the
    one machine the seal existed for, it never ran. The systemd unit is
    what gave it away, not the code.

    So this checks the SOURCE of both entrypoints rather than the
    behaviour of one, because the live server below can only ever
    exercise whichever of them the test happens to launch.
    """
    root = ROOT
    for name in ("server.py", "launch.py"):
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            src = fh.read()
        # Comments stripped: both files EXPLAIN the seal at length, and a
        # mention is not a call.
        code = re.sub(r"(?m)#.*$", "", src)
        code = re.sub(r'(?s)"""(?:.|\n)*?"""', "", code)
        assert "seal_on_boot()" in code, (
            f"{name} starts a server without sealing the public path — "
            "the boards written before QB_PAYWALL went on stay readable")
    unit = os.path.join(root, "deploy", "qellys.service")
    if os.path.isfile(unit):
        with open(unit, encoding="utf-8") as fh:
            text = fh.read()
        started = [n for n in ("launch.py", "server.py") if n in text]
        assert started, "the unit starts neither entrypoint — check this test"
        steps.append(f"the unit runs {started[0]}, which seals")


def main():
    steps = []

    def ok(name):
        steps.append(name)
        print(f"  ok  {name}")

    test_every_entrypoint_seals(steps)
    ok("both entrypoints seal before they bind")

    # The filter is the thing being trusted, so make it answer directly.
    # The guard inside the run below catches a filter that has stopped
    # filtering, but only once a server is up; this says it in one line,
    # and it says it even if the fixture never boots.
    web = os.path.join(ROOT, "web")
    assert _not_the_real_boards(web, ["data", "js", "css"]) == {"data"}, \
        "the copytree filter stopped skipping the working copy's boards"
    nested = os.path.join(web, "fonts")
    assert _not_the_real_boards(nested, ["data"]) == set(), \
        "the filter is skipping a nested data/ that is a real asset"
    ok("the copytree filter skips web/data and nothing else")

    site = Site(paywall=True)
    try:
        # The fixture has to be genuinely leaky before the server starts,
        # or a pass below means nothing. Checked against the copy, since
        # the server has already sealed it — so this reads the payload we
        # wrote rather than the file.
        before = {n: gate._paid_rows(PLANTED[n], n) for n in site.planted}
        assert all(before.values()), \
            f"the planted fixture carries no paid rows: {before}"
        ok(f"the fixture is genuinely unsealed ({sum(before.values())} paid rows)")

        # THE GUARD ON EVERYTHING BELOW. Every assertion in this file
        # reads the served tree, so the tree has to be the fixture and
        # only the fixture. When the copytree still brought the working
        # copy's web/data along, an untracked board left there by another
        # test — or by a real build — silently joined the run, and the
        # checks graded whatever it contained. If the ignore filter ever
        # stops filtering, this is the line that says so, instead of the
        # verdict quietly starting to depend on the box.
        served = sorted(n for n in os.listdir(os.path.join(site.web, "data"))
                        if n.endswith(".json"))
        assert served == sorted(list(PLANTED) + list(FREE_PLANTED)), (
            f"the served tree holds boards nobody planted: {served} — "
            "web/data is gitignored, so anything extra in here is the "
            "machine leaking into the verdict")
        ok(f"the served tree is the fixture and nothing else "
           f"({len(served)} boards)")

        # --- THE ONE THAT FAILED --------------------------------------
        leaked = _paid_boards(site.web)
        assert not leaked, (
            "the server booted with the paywall on and left "
            f"{leaked} on the public path")
        ok("starting the server with the paywall on seals the public path")

        for name in sorted(before):
            code, body = _get(f"{site.base}/data/{name}")
            assert code == 200, f"/data/{name} returned {code}"
            payload = json.loads(body)
            rows = gate._paid_rows(payload, name)
            assert rows == 0, (
                f"curl of /data/{name} with no cookie returned {rows} paid "
                "row(s) — that is the whole product, free")
        ok(f"no paid row is served to an anonymous caller ({len(before)} boards)")

        # --- the free half must still work ----------------------------
        code, body = _get(f"{site.base}/data/record.json")
        assert code == 200
        rec = json.loads(body)
        assert rec.get("overall") or rec.get("recent"), \
            "the Record page went dark — it is free by design and is the " \
            "evidence the subscription is sold on"
        ok("the Record page is still readable without an account")

        code, _ = _get(f"{site.base}/")
        assert code == 200, "the site itself stopped serving"
        ok("the shop still loads")

        # --- and the API half -----------------------------------------
        # `.json` INCLUDED. `full_board` refuses anything that is not a
        # bare filename ending in .json — a path from a URL that can climb
        # out of the directory turns an entitlement check into an
        # arbitrary file read — so the endpoint is /api/board/<file>.json.
        code, body = _get(f"{site.base}/api/board/recommendations.json")
        assert code in (401, 402), \
            f"the entitled board endpoint answered {code} to nobody"
        assert json.loads(body).get("locked") is True
        ok("the subscriber board endpoint refuses an anonymous caller")

        # --- path tricks ----------------------------------------------
        for trick in ("/data/../data/recommendations.json",
                      "/data//recommendations.json",
                      "/data/recommendations.json?x=1",
                      "/DATA/recommendations.json"):
            code, body = _get(site.base + trick)
            if code != 200:
                continue
            try:
                payload = json.loads(body)
            except ValueError:
                continue
            if isinstance(payload, dict):
                assert gate._paid_rows(payload, "recommendations.json") == 0, \
                    f"{trick} walked around the gate"
        ok("path tricks do not reach an unredacted copy")

        # --- the members' invite ---------------------------------------
        # STATIC ASSETS ARE THE TRAP. The first version of this feature
        # put the invite in app.js and gated the render, which ships the
        # string to every anonymous visitor and hides it with CSS-grade
        # security. Checked over the wire, where it can be seen.
        for path in ("/js/app.js", "/", "/terms.html", "/privacy.html",
                     "/api/billing/status"):
            code, body = _get(site.base + path)
            assert DISCORD_PROBE not in body, \
                f"{path} hands the Discord invite to an anonymous caller"
        ok("the Discord invite is in nothing a stranger can fetch")
    finally:
        site.stop()

    # --- and with the flag OFF, nothing is gated ----------------------
    site = Site(paywall=False)
    try:
        code, body = _get(f"{site.base}/data/recommendations.json")
        assert code == 200
        assert gate._paid_rows(json.loads(body), "recommendations.json") > 0, (
            "the paywall is OFF and the board is still redacted — the flag "
            "is meant to be a true no-op when unset")
        ok("with the flag off the boards publish whole, as they always did")
    finally:
        site.stop()

    return steps


if __name__ == "__main__":
    print(f"\n{len(main())} tests passed.")
