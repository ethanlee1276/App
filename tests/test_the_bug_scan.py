"""The bug scan: a crash on anyone's screen reaches the box, and one report says everything that broke.

Ethan, 2026-10-24: "we need a debugging thing to scan for bugs ... anything a
normal app and a consistent running app and website would have." A script
error drew an apology on the one screen that hit it (app.js crashNote) and
told nobody who could fix it. Now app.js reportCrash sends it to
POST /api/clienterror, engine/bugscan keeps it, and `python3 -m
engine.bugscan` rolls it up with the builds' warnings, stale boards, the
self-update and the site's errors — mailed to the owner once a day when
anything needs a person.

What these hold: a report keeps the message, the place, the page, the
screen and the browser's family and nothing that identifies anyone; the
browser talking (a ResizeObserver notice, a cross-origin "Script error.",
an extension) is not kept; the file sheds its older half past its cap;
crashes are grouped and counted with the screens and browsers they hit; a
build's warnings and a traceback's last line are read off its log; a stale
board, a failed update and a journal that cannot be read are all said; the
scan exits 1 and mails only when something is broken; and the page, the
server, the privacy policy and the daily pass carry it.

Run directly: `python3 tests/test_the_bug_scan.py`
"""
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import alert, bugscan as B                            # noqa: E402

UA = {
    "Samsung Internet Android": "Mozilla/5.0 (Linux; Android 14; SM-F946B) AppleWebKit/537.36 (KHTML, like Gecko) "
                                "SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
    "Safari iOS": "Mozilla/5.0 (iPhone; CPU iPhone OS 27_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/27.1 Mobile/15E148 Safari/604.1",
    "Chrome Android": "Mozilla/5.0 (Linux; Android 15; Pixel 9 Pro Fold) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/138.0.0.0 Mobile Safari/537.36",
    "Edge Windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
    "Firefox Mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:131.0) Gecko/20100101 Firefox/131.0",
}


def test_a_browser_is_named_by_its_family_only():
    for want, ua in UA.items():
        assert B.browser_family(ua) == want, (want, B.browser_family(ua))
    assert B.browser_family("") == "other"


def test_a_report_keeps_what_fixes_a_bug_and_nothing_that_identifies_anyone():
    path = os.path.join(tempfile.mkdtemp(), "c.jsonl")
    ok = B.record_client({"m": "TypeError: x is undefined\x00\x07", "src": "app.js:45601:12", "view": "Likely<b>",
                          "w": 280, "h": 99999, "email": "someone@example.com", "token": "secret"},
                         ua=UA["Samsung Internet Android"], path=path, now=1_800_000_000, commit="2c39a058")
    assert ok
    (row,) = [json.loads(x) for x in open(path, encoding="utf-8")]
    assert row == {"at": 1_800_000_000, "m": "TypeError: x is undefined", "src": "app.js:45601:12",
                   "view": "likelyb", "w": 280, "h": 10000, "browser": "Samsung Internet Android",
                   "commit": "2c39a058"}, row
    assert B.record_client({"m": "y" * 500}, path=path) and len(json.loads(open(path).readlines()[-1])["m"]) == 200


def test_the_browser_talking_is_not_kept():
    path = os.path.join(tempfile.mkdtemp(), "c.jsonl")
    for m, src in (("ResizeObserver loop completed with undelivered notifications.", ""), ("Script error.", ""),
                   ("boom", "chrome-extension://abc/content.js:1:1"), ("", "app.js:1:1")):
        assert not B.record_client({"m": m, "src": src}, path=path), m
    assert not B.record_client("not a dict", path=path)
    assert not os.path.exists(path)


def test_the_file_sheds_its_older_half_past_its_cap():
    path = os.path.join(tempfile.mkdtemp(), "c.jsonl")
    was, B.CLIENT_LOG_MAX = B.CLIENT_LOG_MAX, 2000
    try:
        for i in range(40):
            B.record_client({"m": f"error number {i:02d}", "src": "app.js:1:1"}, path=path, now=1_800_000_000 + i)
    finally:
        B.CLIENT_LOG_MAX = was
    rows = [json.loads(x) for x in open(path, encoding="utf-8")]
    assert os.path.getsize(path) <= 2000 + 200 and rows[-1]["m"] == "error number 39" and rows[0]["m"] != "error number 00"


def test_crashes_are_grouped_with_the_screens_and_browsers_they_hit():
    path = os.path.join(tempfile.mkdtemp(), "c.jsonl")
    now = 1_800_000_000
    for i, (w, h, ua, view) in enumerate([(280, 653, "Samsung Internet Android", "likely"),
                                          (280, 653, "Samsung Internet Android", "likely"),
                                          (951, 543, "Safari iOS", "prop")]):
        B.record_client({"m": "TypeError: card is null", "src": "app.js:100:5", "view": view, "w": w, "h": h},
                        ua=UA[ua], path=path, now=now - 60 * i)
    B.record_client({"m": "old one", "src": "app.js:1:1"}, path=path, now=now - 3 * 86400)
    (g,) = B.crashes(24, path=path, now=now)
    assert g["n"] == 3 and dict(g["screens"]) == {"280x653": 2, "951x543": 1}
    assert dict(g["browsers"]) == {"Samsung Internet Android": 2, "Safari iOS": 1} and dict(g["views"]) == {"likely": 2, "prop": 1}
    assert len(B.crashes(24 * 7, path=path, now=now)) == 2


def test_a_builds_warnings_and_its_traceback_are_read_off_its_log():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "nba_build.log"), "w", encoding="utf-8") as fh:
        fh.write("Building\n⚠️  5 priced event(s) could not be placed on the slate:\nok\n"
                 "Traceback (most recent call last):\n  File \"x.py\", line 1\nKeyError: 'games'\n")
    with open(os.path.join(d, "nfl_build.log"), "w", encoding="utf-8") as fh:
        fh.write("⚠️  an old warning\n")
    old = time.time() - 3 * 86400
    os.utime(os.path.join(d, "nfl_build.log"), (old, old))
    got = B.build_warnings(24, log_dir=d)
    assert list(got) == ["nba_build"], got
    assert got["nba_build"][0].startswith("⚠️  5 priced event(s)") and "  -> KeyError: 'games'" in got["nba_build"]


def test_the_scan_says_every_section_and_counts_what_needs_a_person():
    d = tempfile.mkdtemp()
    real = (B.CLIENT_LOG, B.LOG_DIR, B.ROOT)
    B.CLIENT_LOG, B.LOG_DIR, B.ROOT = os.path.join(d, "c.jsonl"), d, d
    try:
        os.makedirs(os.path.join(d, "web", "data"))
        os.makedirs(os.path.join(d, "data"))
        board = os.path.join(d, "web", "data", "nba.json")
        open(board, "w").write("{}")
        os.utime(board, (time.time() - 5 * 3600,) * 2)
        json.dump({"ok": False, "at": "2026-10-24T16:00:00", "note": "pull failed"}, open(os.path.join(d, "data", "autoupdate.json"), "w"))
        B.record_client({"m": "TypeError: a", "src": "app.js:1:1"}, path=B.CLIENT_LOG)
        got = B.scan(24, journal=lambda h: None)
        assert got["broken"] == 2 and got["stale"] == {"nba": 5.0}
        text = "\n".join(B.report(got))
        for bit in ("CRASHES ON PEOPLE'S SCREENS: 1 report(s), 1 distinct", "BOARDS OLDER THAN 3h: nba 5.0h",
                    "SELF-UPDATE: FAILED", "SITE ERRORS IN THE JOURNAL: not readable here"):
            assert bit in text, bit
        sent = []
        real_send, real_scan = alert.send_text, B.scan
        alert.send_text = lambda subject, text: sent.append(subject) or "sent"
        B.scan = lambda hours, **kw: got
        try:
            assert B.main(["--mail"]) == 1 and sent == ["Qellys bug scan: 2 thing(s) need a person"]
            clean = dict(got, crashes=[], update={"ok": True}, broken=0)
            B.scan = lambda hours, **kw: clean
            sent.clear()
            assert B.main(["--mail"]) == 0 and sent == [], "a clean day sends nothing"
        finally:
            B.scan, alert.send_text = real_scan, real_send
    finally:
        B.CLIENT_LOG, B.LOG_DIR, B.ROOT = real


def test_the_owner_mail_goes_by_the_alert_address():
    got = []
    assert alert.send_text("s", "t", send=lambda to, s, t: got.append(to), env={"QB_ALERT_EMAIL": "you@example.com"}) == "sent"
    assert got == ["you@example.com"]
    assert alert.send_text("s", "t", send=lambda *a: None, env={"QB_ALERT_EMAIL": "off"}) == "no-address"

    def boom(*a):
        raise OSError("relay down")
    assert alert.send_text("s", "t", send=boom, env={}) == "failed"


def test_the_page_the_server_the_policy_and_the_day_carry_it():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    at = app.index("function reportCrash(")
    body = app[at:app.index("\n}\n", at)]
    assert "_crashSent.size >= 5" in body and "_crashSent.has(m)" in body, "each distinct error once, five a page"
    assert 'credentials: "omit"' in body and '"/api/clienterror"' in body, "no cookie rides along"
    assert app.count("reportCrash(") == 3, "the error and the rejection both report"
    srv = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert 'if parsed.path in ("/api/clienterror", "/api/clienterror/"):' in srv
    at = srv.index("def _client_error(self):")
    body = srv[at:srv.index("def _event(self):")]
    assert "RATE_CLIENTERR_PER_MIN" in body and "0 < length <= 2000" in body and "_client_ip" not in body
    policy = open(os.path.join(ROOT, "web", "privacy.html"), encoding="utf-8").read()
    assert "<h3>2.6 Crash reports</h3>" in policy and "no IP address, no account, no identifier" in policy
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    assert 'state.get("bugscan_attempted") != today.isoformat()' in maint
    assert '_spawn_module("engine.bugscan", log, args=("--mail",))' in maint


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
