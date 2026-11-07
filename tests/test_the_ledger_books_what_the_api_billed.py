"""The spend ledger books what The Odds API billed, beside what we priced.

2026-10-30, the month's numbers: the API reported ~99,400 credits used since
the 1st; the ledger had booked ~55,000. Every row was priced by
`oddsapi._classify`'s formula (markets × regions read off the request), so
a call billed differently from the formula — seventeen bookmakers where the
API counts every ten as a region, the historical multiplier — went into the
books at the wrong price, and so did every ceiling metered off them. The API
states each call's cost in `x-requests-last`; the ledger now books that and
keeps the formula's figure beside it (`est`), and the plan's report says how
far apart the two are (`oddsbudget.bill_line`).

Run directly: `python3 tests/test_the_ledger_books_what_the_api_billed.py`
"""
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import oddsbudget as B                           # noqa: E402
from engine.sources import oddsapi as O                      # noqa: E402

BOOKS = ",".join(O.DEFAULT_BOOKS)
URL = ("https://api.the-odds-api.com/v4/sports/basketball_nba/events/e1/odds?apiKey=k"
       f"&regions=us&markets=player_points,player_rebounds,h2h&oddsFormat=american&bookmakers={BOOKS}")


def _call(headers: dict, url: str = URL, name: str = "odds_event_nba_e1.json") -> list:
    """One live call through the real `_request`, the network faked and the
    ledger, state and cache in a temporary place. Returns the ledger rows."""
    d = Path(tempfile.mkdtemp())

    class _Resp:
        def __init__(self):
            self.headers = headers

        def read(self):
            return json.dumps({"id": "e1", "bookmakers": []}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    saved = (B.SPEND_LOG, B.DECISIONS_LOG, B.STATE_PATH, O.CACHE_DIR, urllib.request.urlopen)
    B.SPEND_LOG, B.DECISIONS_LOG, B.STATE_PATH = d / "spend.jsonl", d / "decisions.jsonl", d / "budget.json"
    O.CACHE_DIR = d / "cache"
    urllib.request.urlopen = lambda req, timeout=None: _Resp()
    try:
        O._request(url, name, ttl=0)
        return B.read_spend(d / "spend.jsonl")
    finally:
        (B.SPEND_LOG, B.DECISIONS_LOG, B.STATE_PATH, O.CACHE_DIR, urllib.request.urlopen) = saved


def test_a_call_is_booked_at_what_the_api_billed():
    rows = _call({"x-requests-remaining": "90000", "x-requests-used": "10000", "x-requests-last": "6"})
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["credits"] == 6, ("the API's own bill", row)
    assert row["est"] == 3, ("the formula: three markets, one region", row)
    assert row["billed"] is True and row["used"] == 10000, row
    assert row["kind"] == "live_event" and row["sport"] == "nba"


def test_without_the_header_the_formula_stands_and_says_so():
    rows = _call({"x-requests-remaining": "90000", "x-requests-used": "10000"})
    row = rows[0]
    assert row["credits"] == row["est"] == 3 and row["billed"] is False, row
    assert O._count("?") is None and O._count("") is None and O._count("-4") is None
    assert O._count("12") == 12 and O._count(" 0 ") == 0 and O._count("7.0") == 7


def test_a_free_call_is_booked_free():
    rows = _call({"x-requests-remaining": "90000", "x-requests-used": "10000", "x-requests-last": "0"},
                 url="https://api.the-odds-api.com/v4/sports/basketball_nba/events?apiKey=k",
                 name="odds_events_nba.json")
    assert rows[0]["credits"] == 0 and rows[0]["est"] == 1 and rows[0]["kind"] == "live_events", rows


def test_the_check_reads_the_gap_and_the_plan_prints_it():
    now = time.time()
    rows = [
        {"ts": now - 600, "kind": "live_event", "credits": 50, "est": 25, "billed": True},
        {"ts": now - 300, "kind": "live_board", "credits": 6, "est": 3, "billed": True},
        {"ts": now - 200, "kind": "live_event", "credits": 25},              # before 2026-10-30: no est
        {"ts": now - 100, "kind": "live_event", "credits": 8, "est": 8, "billed": False},
        {"ts": now - 90_000, "kind": "live_event", "credits": 99, "est": 1, "billed": True},
    ]
    got = B.billing_check(rows, since=now - 86_400)
    assert got["calls"] == 2 and got["billed"] == 56 and got["est"] == 28, got
    assert got["by_kind"] == {"live_event": [1, 50, 25], "live_board": [1, 6, 3]}, got
    line = B.bill_line(got)
    assert line == "  the API's own bill, last 24h: 56 credits for 2 call(s) we priced at 28 (2.0×)", line
    assert B.bill_line(B.billing_check([], since=now)) == ""
    import inspect
    from engine import oddsplan as P
    src = inspect.getsource(P.main)
    assert "ob.bill_line(ob.billing_check(rows, since=time.time() - 86400))" in src


def test_the_request_path_books_the_bill():
    src = (ROOT / "engine" / "sources" / "oddsapi.py").read_text(encoding="utf-8")
    body = src[src.index("def _request("):src.index("# --- endpoints")]
    assert 'last=resp.headers.get("x-requests-last", "?")' in body
    assert "log_spend(kind, sport, est if billed is None else billed, detail," in body
    assert "est=est, billed=billed is not None, used=_count(quota.used))" in body
    assert O.Quota("1", "2").last == "?", "positional Quota callers keep working"


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
