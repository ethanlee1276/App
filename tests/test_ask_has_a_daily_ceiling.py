"""Ask has a daily ceiling: per account, and on the site's spend.

The site audit, 2026-09-24. Every Ask question is a paid model call, and
the only limit was eight a minute per address — eleven thousand a day for
one subscriber or one stolen session. The usage log priced every call and
nothing read the total. Now an account has QB_ASK_PER_ACCOUNT_DAILY
uncached questions a UTC day and the site stops at QB_ASK_DAILY_USD of
estimated spend; both are environment variables, 0 turns either off.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as AB                                  # noqa: E402

DAY = "2026-09-24"


def _fresh():
    d = Path(tempfile.mkdtemp())
    AB.USAGE_PATH = d / "ask_usage.json"
    return d


def test_an_account_stops_at_its_daily_questions():
    _fresh()
    os.environ["QB_ASK_PER_ACCOUNT_DAILY"] = "3"
    try:
        for _ in range(3):
            assert AB.over_limit(42, today=DAY) == ""
            AB.count_question(42, today=DAY)
        assert AB.over_limit(42, today=DAY) == "account"
        assert AB.over_limit(7, today=DAY) == "", "another account is untouched"
        assert AB.over_limit(42, today="2026-09-25") == "", "a new UTC day starts clean"
        os.environ["QB_ASK_PER_ACCOUNT_DAILY"] = "0"
        assert AB.over_limit(42, today=DAY) == "", "0 turns it off"
    finally:
        os.environ.pop("QB_ASK_PER_ACCOUNT_DAILY", None)


def test_the_site_pauses_past_its_daily_spend():
    _fresh()
    AB.USAGE_PATH.write_text(json.dumps({"days": {DAY: {"calls": 900, "usd": 25.0}}}))
    assert AB.over_limit(1, today=DAY) == "spend", "the default ceiling is $25"
    os.environ["QB_ASK_DAILY_USD"] = "40"
    try:
        assert AB.over_limit(1, today=DAY) == ""
        os.environ["QB_ASK_DAILY_USD"] = "0"
        AB.USAGE_PATH.write_text(json.dumps({"days": {DAY: {"usd": 9999.0}}}))
        assert AB.over_limit(1, today=DAY) == ""
    finally:
        os.environ.pop("QB_ASK_DAILY_USD", None)


def test_the_log_never_holds_who_asked():
    _fresh()
    AB.count_question("someone@example.com", today=DAY)
    raw = AB.USAGE_PATH.read_text()
    assert "someone@example.com" not in raw
    tags = json.loads(raw)["days"][DAY]["accounts"]
    assert list(tags.values()) == [1] and len(next(iter(tags))) == 16


def test_the_server_checks_before_it_reads_and_counts_only_what_it_paid_for():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    body = src.split("    def _ask(self, body):")[1].split("\n    def ")[0]
    assert body.index("AB.over_limit(me)") < body.index("AB.board_at(")
    assert '"ask daily limit"' in body and "self._send(429," in body
    assert 'if not out.get("cached"):' in body and "AB.count_question(me)" in body
    assert 'f"ip:{self._client_ip()}"' in body, "a reader with the paywall off is counted by address"
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    fn = app[app.index("function askErrorText("):]
    fn = fn[:fn.index("\n}\n")]
    assert 'body.limit === "account"' in fn and 'body.limit === "spend"' in fn


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
