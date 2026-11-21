"""The test suite cannot reach the internet, on any machine.

2026-10-11: run once with every outbound connection refused and logged,
about seventy test files (and the build scripts and server they launch)
reached GitHub, ESPN, MLB, Kalshi, Polymarket, the NHL, the Odds API and
Stripe, and five passed only because a download happened to be cached.
run_tests.py now loads tests/netguard/sitecustomize.py into every test
process. These check, one rule each: a non-local host is refused before
anything leaves (by name, by address, through urllib), and the refusal is
logged under the script's name; this machine's own servers still answer;
the interpreter's own sitecustomize still runs; the runner wires the guard
in and tallies what it refused.

Run directly: `python3 tests/test_the_suite_has_no_network.py`
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
GUARD = os.path.join(ROOT, "tests", "netguard")


def _child(code: str, extra_path: str = "") -> tuple[str, str]:
    """Run ``code`` as a script under the guard; (its output, the log)."""
    d = tempfile.mkdtemp()
    script, log = os.path.join(d, "probe_script.py"), os.path.join(d, "net.log")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(code)
    env = dict(os.environ, PYTHONPATH=GUARD + (os.pathsep + extra_path if extra_path else ""),
               QB_NETGUARD_LOG=log)
    out = subprocess.run([sys.executable, script], capture_output=True, text=True, env=env, timeout=60)
    try:
        logged = open(log, encoding="utf-8").read()
    except OSError:
        logged = ""
    return out.stdout + out.stderr, logged


def test_a_host_on_the_internet_is_refused_and_logged():
    out, log = _child(
        "import socket, urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('https://github.com/nflverse', timeout=5)\n"
        "    print('REACHED')\n"
        "except OSError as e:\n"
        "    print('refused:', e)\n"
        "for addr in (('192.0.2.1', 80), ('example.com', 443)):\n"
        "    try:\n"
        "        socket.create_connection(addr, timeout=2)\n"
        "        print('REACHED', addr)\n"
        "    except ConnectionRefusedError as e:\n"
        "        print('refused:', e)\n")
    assert "REACHED" not in out, out
    assert out.count("the test suite has no network") == 3, out
    assert "probe_script.py\tgithub.com" in log and "probe_script.py\t192.0.2.1" in log, log


def test_this_machines_own_servers_still_answer():
    out, log = _child(
        "import http.server, threading, urllib.request\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.end_headers(); self.wfile.write(b'local ok')\n"
        "    def log_message(self, *a): pass\n"
        "s = http.server.HTTPServer(('127.0.0.1', 0), H)\n"
        "threading.Thread(target=s.serve_forever, daemon=True).start()\n"
        "for host in ('127.0.0.1', 'localhost'):\n"
        "    print(urllib.request.urlopen(f'http://{host}:{s.server_port}/', timeout=5).read().decode())\n")
    assert out.count("local ok") == 2, out
    assert log == "", "nothing local is logged"


def test_the_interpreters_own_sitecustomize_still_runs():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "sitecustomize.py"), "w", encoding="utf-8") as fh:
        fh.write("import builtins\nbuiltins.QB_SYSTEM_SITE_RAN = True\n")
    out, _log = _child("import builtins\nprint('chained:', getattr(builtins, 'QB_SYSTEM_SITE_RAN', False))\n",
                       extra_path=d)
    assert "chained: True" in out, out


def test_the_guard_reads_loopback_the_way_the_suite_uses_it():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_netguard_probe", os.path.join(GUARD, "sitecustomize.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)           # installs the guard here too — this file needs no network
    for h in ("127.0.0.1", "127.0.1.1", "localhost", "::1", "[::1]", b"127.0.0.1", ""):
        assert g.local(h), h
    for h in ("github.com", "192.0.2.1", "10.0.0.5", "api.stripe.com", "1.2.3.4"):
        assert not g.local(h), h


def test_the_runner_wires_the_guard_in_and_tallies_it():
    src = open(os.path.join(ROOT, "run_tests.py"), encoding="utf-8").read()
    assert 'os.path.join(ROOT, "tests", "netguard")' in src and 'env["PYTHONPATH"] = guard' in src
    assert 'env["QB_NETGUARD_LOG"]' in src
    # Set after the QB_ sweep, or the sweep would eat it.
    assert src.index('env["QB_NETGUARD_LOG"]') > src.index('if name.startswith(("STRIPE_", "ODDS_API_KEY", "QB_"))')
    import run_tests
    d = tempfile.mkdtemp()
    log = os.path.join(d, "n.log")
    assert run_tests.netguard_tally(log) == "", "no file, nothing to say"
    with open(log, "w", encoding="utf-8") as fh:
        fh.write("test_a.py\tgithub.com\n" * 3 + "test_b.py\tapi.stripe.com\ncfb_build.py\tsite.api.espn.com\n")
    line = run_tests.netguard_tally(log, top=2)
    assert "refused 5 time(s) in 3 file(s)" in line and line.index("test_a.py") < line.index("test_b.py"), line
    assert "and 1 more" in line


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
