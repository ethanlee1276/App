"""What happens when the site gets busy.

Ethan, 2026-08-21, having just posted the live site to Instagram: *"we
need to make sure everything is perfect … make sure we are also ready for
alot of traffic."*

THE FAILURE THIS PREVENTS. `ThreadingHTTPServer` starts a thread per
connection and has no ceiling. On a 1GB droplet a burst walks the box into
swap and then into the OOM killer — and what dies is not "some requests",
it is the whole process, taking every signed-in session with it. Often it
takes sshd's headroom too, so the fix has to start with a console.

A bounded pool turns that into the failure anybody would choose: a few
callers get a 503 and a Retry-After, everyone already being served
finishes normally, and the box stays up.

WHY THE SEMAPHORE IS TAKEN IN `process_request` AND NOT IN THE HANDLER.
By the time a handler runs, the thread exists and the memory is spent.
The only place a ceiling means anything is before the thread is created.

    python3 tests/test_load_shedding.py
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server as S                                          # noqa: E402


def test_there_is_a_ceiling_and_it_is_not_absurd():
    assert S.MAX_INFLIGHT >= 4
    assert S.MAX_INFLIGHT <= 512, (
        "a ceiling this high is not a ceiling on a 1GB box")


def test_the_ceiling_can_be_moved_without_a_code_change():
    """The right number depends on the box, and the box is not in the
    repository."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert "QB_MAX_INFLIGHT" in src


def test_a_nonsense_ceiling_does_not_take_the_site_down():
    """An env var is typed by a human at 1am."""
    for junk in ("", "   ", "lots", "-5", "0"):
        os.environ["QB_MAX_INFLIGHT"] = junk
        try:
            import importlib
            got = max(4, int(os.environ.get("QB_MAX_INFLIGHT", "") or 64)) \
                if junk.lstrip("-").isdigit() else 64
            assert got >= 4
        finally:
            os.environ.pop("QB_MAX_INFLIGHT", None)


def test_the_slot_is_taken_before_the_thread_exists():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("class BoundedHTTPServer")
    body = src[i:src.index("\ndef seal_on_boot", i)]
    assert "def process_request(self" in body, (
        "the ceiling is not enforced where threads are created")
    j = body.index("def process_request(self")
    k = body.index("super().process_request(", j)
    assert body.index("_slots.acquire", j) < k, (
        "the thread is started before the slot is taken, which is no "
        "ceiling at all")


def test_every_path_out_of_the_thread_releases_the_slot():
    """A slot leaked once per failed request is a server that throttles
    itself to zero over an afternoon — and the requests that leak are the
    ones that raised, which is exactly when there are many."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def process_request_thread(self")
    body = src[i:i + 400]
    assert "finally:" in body and "_slots.release()" in body, (
        "the slot is released on the happy path only")
    # And the guard on the start path too.
    i2 = src.index("def process_request(self")
    body2 = src[i2:src.index("def process_request_thread", i2)]
    assert "except" in body2 and "_slots.release()" in body2, (
        "a thread that fails to start holds its slot for ever")


def test_both_entrypoints_have_the_ceiling():
    """launch.py is what systemd runs. A ceiling only in server.main()
    would be a ceiling on the one path production never takes — which is
    exactly how seal_on_boot was wrong for a day."""
    for name in ("server.py", "launch.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert "BoundedHTTPServer(" in src, "%s serves unbounded" % name
        # Anything still building the unbounded one has to be a LOCAL
        # tool, not the site. `--check`'s render sweep is the one: bound
        # to 127.0.0.1 on an ephemeral port, one headless browser as its
        # only client, torn down when the sweep ends. A ceiling there
        # would make the sweep flaky and protect nothing.
        for line in src.splitlines():
            if "ThreadingHTTPServer((" not in line:
                continue
            assert '("127.0.0.1"' in line, (
                "%s builds an unbounded server on a public bind: %s"
                % (name, line.strip()))


def test_the_ceiling_and_keep_alive_are_not_changed_apart():
    """A slot is a CONNECTION. That equals one request only because the
    handler speaks HTTP/1.0 and closes after each response.

    Turn keep-alive on — `protocol_version = "HTTP/1.1"` — and Caddy's
    idle upstream connections start sitting in these slots doing nothing.
    Enough of them and the site refuses everybody while completely idle.
    That is a failure that looks like nothing in the logs and takes a
    long evening to understand, so the two settings are pinned together.
    """
    assert getattr(S.Handler, "protocol_version", "HTTP/1.0") == "HTTP/1.0", (
        "keep-alive is on and the request ceiling is now a ceiling on IDLE "
        "connections too — either raise MAX_INFLIGHT well above Caddy's "
        "upstream pool, or count requests rather than connections")


# --- against a real socket --------------------------------------------------
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_a_full_server_sheds_instead_of_growing():
    """The behaviour, measured. Slots are filled with connections that are
    opened and left hanging; the next caller must get a 503 rather than a
    thread, and the server must recover the moment they let go."""
    port = _free_port()
    env = dict(os.environ)
    env.update({"QB_MAX_INFLIGHT": "4", "QB_PAYWALL": "",
                "QB_ACCOUNTS_DB": "/tmp/qb-shed-%d.db" % port})
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:%d" % port

    def get(timeout=8):
        try:
            with urllib.request.urlopen(base + "/api/billing/status",
                                        timeout=timeout) as r:
                return r.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:                                    # noqa: BLE001
            return 0

    try:
        end = time.time() + 40
        while time.time() < end and get(2) != 200:
            if proc.poll() is not None:
                raise AssertionError("server died:\n"
                                     + (proc.stdout.read() or "")[:1200])
            time.sleep(0.25)
        assert get() == 200, "server never came up"

        # Occupy every slot with a connection that sends a partial request
        # and then sits there, which is what a slow phone on a train looks
        # like to a server.
        held = []
        for _ in range(4):
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
            s.sendall(b"GET /api/billing/status HTTP/1.1\r\n")
            held.append(s)
        time.sleep(0.6)

        code = get(6)
        assert code == 503, (
            "expected a 503 when every slot is held, got %r — the ceiling "
            "is not doing anything" % code)

        # And the refusal is a retryable one that says so.
        for s in held:
            try:
                s.close()
            except Exception:                                # noqa: BLE001
                pass
        time.sleep(0.8)
        assert get() == 200, (
            "the server did not recover once the slow callers let go, so "
            "slots are leaking")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            os.unlink("/tmp/qb-shed-%d.db" % port)
        except OSError:
            pass


def test_the_refusal_is_a_retryable_one():
    """A 503 with Retry-After is a browser and a crawler both being told
    to come back. A bare connection reset is neither."""
    assert b"503" in S._BUSY
    assert b"Retry-After" in S._BUSY
    assert b"Content-Length" in S._BUSY, (
        "no length and no chunking means the client waits for the socket "
        "to close before it can read the reason"
    )
    head, _, body = S._BUSY.partition(b"\r\n\r\n")
    stated = int([l.split(b":")[1] for l in head.split(b"\r\n")
                  if l.lower().startswith(b"content-length")][0])
    assert stated == len(body), (
        "Content-Length says %d, body is %d — the client hangs waiting for "
        "bytes that never come" % (stated, len(body)))
    json.loads(body.decode())


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
