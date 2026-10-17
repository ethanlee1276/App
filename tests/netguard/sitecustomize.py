"""The test suite's network guard: no test reaches the internet, on any machine.

run_tests.py puts this directory first on every test process's PYTHONPATH,
so Python imports this file at start-up — in each test file, and in every
script a test launches (cfb_build.py, server.py …), because the
environment is inherited.

WHY (2026-10-11). The rule was always "tests never touch the network",
and nothing enforced it. Run once with every outbound connection refused
and logged, the suite showed about seventy files reaching GitHub
(nflverse), ESPN, MLB's stats API, Kalshi, Polymarket, the NHL, the Odds
API, CollegeFootballData and Stripe. In the cloud sandbox an egress proxy
refused most of them, so the suite looked hermetic there; on the droplet
every one went out for real. And five files only passed because a GitHub
download (or a file an earlier test had downloaded into data/cache) was
there to read — a verdict that depended on the machine and on test order.

WHAT IT DOES: a connection to anything but this machine (localhost,
127.x, ::1) raises ConnectionRefusedError before a byte leaves — the same
failure the code already meets on a box with no egress, which every feed
is written to survive. Each refusal is written, with the script's name
and the host, to the file named by QB_NETGUARD_LOG (the runner prints the
tally at the end of the run).

The interpreter's own sitecustomize, if it has one, still runs first.
Standard library only.
"""
import os
import sys


def _chain_the_real_one() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    for d in list(sys.path):
        try:
            base = os.path.abspath(d or os.getcwd())
        except OSError:
            continue
        if base == here:
            continue
        cand = os.path.join(base, "sitecustomize.py")
        if os.path.isfile(cand):
            import importlib.util
            spec = importlib.util.spec_from_file_location("_qb_system_sitecustomize", cand)
            try:
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
            except Exception:                                 # noqa: BLE001
                pass
            return


_chain_the_real_one()

import http.client                                             # noqa: E402
import socket                                                  # noqa: E402

LOG = os.environ.get("QB_NETGUARD_LOG", "")


def local(host) -> bool:
    """This machine: a loopback name or address (the suite's own servers)."""
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    h = str(host or "").strip().lower().strip("[]")
    return (h in ("", "localhost", "::1", "0.0.0.0", "::") or h.endswith(".localhost")
            or h.startswith(("127.", "::ffff:127.")))


def _refuse(host, port=None):
    if LOG:
        try:
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(f"{os.path.basename(sys.argv[0] or '?')}\t{host}\n")
        except OSError:
            pass
    raise ConnectionRefusedError(f"the test suite has no network ({host}:{port})")


_connect = http.client.HTTPConnection.connect


def _http_connect(self):
    host = getattr(self, "_tunnel_host", None) or self.host
    if not local(host):
        _refuse(host, getattr(self, "_tunnel_port", None) or self.port)
    return _connect(self)


_create_connection = socket.create_connection


def _create(address, *a, **k):
    if not local(address[0]):
        _refuse(address[0], address[1])
    return _create_connection(address, *a, **k)


_getaddrinfo = socket.getaddrinfo


def _resolve(host, *a, **k):
    if host is not None and not local(host):
        _refuse(host, a[0] if a else None)
    return _getaddrinfo(host, *a, **k)


_sock_connect, _sock_connect_ex = socket.socket.connect, socket.socket.connect_ex


def _guarded(fn):
    def inner(self, address):
        if isinstance(address, tuple) and self.family in (socket.AF_INET, socket.AF_INET6) \
                and not local(address[0]):
            _refuse(address[0], address[1])
        return fn(self, address)
    return inner


http.client.HTTPConnection.connect = _http_connect
socket.create_connection = _create
socket.getaddrinfo = _resolve
socket.socket.connect = _guarded(_sock_connect)
socket.socket.connect_ex = _guarded(_sock_connect_ex)
