"""The owner's reports say what the running site is doing (engine/sitesays,
engine.analytics report, engine.engagement report).

Ethan's catch-up, 2026-10-29: the analytics report said "Switched OFF:
nothing is being counted" and the engagement report "activity OFF" while
the site was counting and keeping. The reports run as the qellys user, and
only root reads the service's settings, so their own environment had no
switches. What these hold:

  * a shell that was told a switch goes by it;
  * a shell that was not asks the site on the box's loopback (the public
    status endpoint, which carries the switches) and says it did;
  * no answer from the site is said as that, never as OFF.

Run directly: `python3 tests/test_the_reports_ask_the_running_site.py`
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _k in ("QB_ANALYTICS", "QB_ACTIVITY"):
    os.environ.pop(_k, None)

from engine import activity as ACT                                # noqa: E402
from engine import analytics as AN                                # noqa: E402
from engine import engagement as E                                # noqa: E402
from engine import sitesays as SS                                 # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731


class _Site:
    """A stand-in for the service's status endpoint on a free port."""

    def __init__(self, body, status=200):
        site = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):                                     # noqa: N802
                site.paths.append(self.path)
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_a):
                pass

        self.paths = []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/api/billing/status"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class _Says:
    """The site's answer, without a network."""

    def __init__(self, answer):
        self.answer, self.keys = answer, []

    def __enter__(self):
        self.keep = SS.ask
        SS.ask = lambda key, **kw: (self.keys.append(key), self.answer)[1]
        return self

    def __exit__(self, *exc):
        SS.ask = self.keep


def test_the_site_is_asked_on_its_status_endpoint_and_only_a_yes_or_no_counts():
    site = _Site({"analytics": True, "activity_switch": False, "plans": "x", "signed_in": False})
    try:
        assert SS.ask("analytics", site.url) is True
        assert SS.ask("activity_switch", site.url) is False
        assert SS.ask("plans", site.url) is None, "not a yes or a no"
        assert SS.ask("closeboard_switch", site.url) is None, "not there"
        assert site.paths == ["/api/billing/status"] * 4
    finally:
        site.close()
    broken = _Site({"analytics": True}, status=500)
    try:
        assert SS.ask("analytics", broken.url) is None, "an error page is no answer"
    finally:
        broken.close()
    assert SS.ask("analytics", site.url, timeout=1.0) is None, "nothing listening: no answer"
    # The address is the service's own (deploy/qellys.service binds it there).
    assert SS.URL == "http://127.0.0.1:8000/api/billing/status"
    assert "--bind 127.0.0.1 8000" in READ("deploy", "qellys.service")
    srv = READ("server.py")
    assert 'out["analytics"] = AN.enabled()' in srv and 'out["activity_switch"] = ACT.enabled()' in srv


def test_a_shell_that_was_told_goes_by_itself():
    os.environ["QB_ANALYTICS"] = "1"
    try:
        with _Says(False) as says:
            assert AN.switch_line() == "Switched ON (QB_ANALYTICS)."
            assert says.keys == [], "the site is not asked"
        os.environ["QB_ANALYTICS"] = "0"
        with _Says(True):
            assert AN.switch_line() == "Switched OFF: nothing is being counted (QB_ANALYTICS)."
    finally:
        os.environ.pop("QB_ANALYTICS", None)


def test_a_shell_that_was_not_told_asks_the_site_and_says_so():
    with _Says(True) as says:
        assert AN.switch_line() == "Switched ON (the running site says so; QB_ANALYTICS)."
        assert E.switch_line() == "Activity: ON (the running site says so)."
        assert says.keys == ["analytics", "activity_switch"]
    with _Says(False):
        assert AN.switch_line() == "Switched OFF: nothing is being counted (the running site says so; QB_ANALYTICS)."
        line = E.switch_line()
        assert line.startswith("Activity: OFF (the running site says so) — "), line
        assert (f"its {ACT.ENV} is not 1" in line) == ACT.policy_ready(), line
    with _Says(None):
        for line in (AN.switch_line(), E.switch_line()):
            assert "can't tell from here" in line and "OFF" not in line, line
            assert "the running site did not answer" in line, line


def test_the_reports_lead_with_it():
    import tempfile
    none = Path(tempfile.mkdtemp())
    with _Says(True):
        text = AN.report(7, path=none / "a.db", accounts_path=none / "u.db")
        assert "(UTC days). Switched ON (the running site says so; QB_ANALYTICS)." in text, text
    eng = READ("engine", "engagement.py")
    assert 'head = [f"Qellys engagement, the last {days} days (Eastern days). {switch_line()}"]' in eng
    assert 'print(f"Qellys engagement. {switch_line()} Nothing has been kept yet.")' in eng
    # The catch-up runs them as the qellys user, the shell that cannot see.
    catch = READ("tools", "catchup.sh")
    assert "sudo -u qellys python3 -m engine.analytics report 7" in catch
    assert "sudo -u qellys python3 -m engine.engagement report 28" in catch


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
