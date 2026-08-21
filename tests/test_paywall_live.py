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
for this.

    python3 tests/test_paywall_live.py
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
sys.path.insert(0, ROOT)

from engine import gate                                       # noqa: E402

BOOT_TIMEOUT = 45


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


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
        shutil.copytree(os.path.join(ROOT, "web"), self.web)
        self.planted = _plant_unsealed(os.path.join(self.web, "data"))
        self.port = _free_port()
        env = dict(os.environ)
        env.update({
            "QB_ACCOUNTS_DB": os.path.join(self.dir, "accounts.db"),
            "QB_WEB_DIR": self.web,
            "QB_PAYWALL": "1" if paywall else "",
            "QB_COMP_EMAILS": "",
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


def _plant_unsealed(data_dir):
    """Write the fixture boards. Returns the names planted."""
    os.makedirs(data_dir, exist_ok=True)
    for name, payload in PLANTED.items():
        assert not gate.is_free(name), \
            f"{name} is free by design, so planting it proves nothing"
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


def main():
    steps = []

    def ok(name):
        steps.append(name)
        print(f"  ok  {name}")

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
