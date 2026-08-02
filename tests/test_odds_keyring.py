"""Two API keys, and a switch when the first one runs dry.

A plan is a fixed monthly allowance. Ethan hit zero on a 20,000-credit plan
mid-season with a second plan sitting unused, so the key stopped being a
value and became a RING: try the first, and when the API refuses it for want
of credits, spend the next one instead.

The failure mode worth guarding is subtle. A key we have never called has an
UNKNOWN balance, not a zero one — and a ring that treats unknown as empty
would skip straight past a full plan. Every test here is really about that
distinction.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as B
from engine.sources import oddsapi as O


def _env(**kw):
    for k in ("ODDS_API_KEY", "ODDS_API_KEY_2", "ODDS_API_KEY_3",
              "ODDS_API_KEYS"):
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in kw.items() if v})


def _budget():
    return os.path.join(tempfile.mkdtemp(), "budget.json")


# --- the ring ---------------------------------------------------------------
def test_the_ring_reads_every_documented_form():
    _env(ODDS_API_KEY="aaa", ODDS_API_KEY_2="bbb", ODDS_API_KEY_3="ccc")
    assert O.api_keys() == ["aaa", "bbb", "ccc"]
    _env(ODDS_API_KEY="aaa", ODDS_API_KEYS="bbb,ccc")
    assert O.api_keys() == ["aaa", "bbb", "ccc"]
    _env(ODDS_API_KEY="aaa")
    assert O.api_keys() == ["aaa"]


def test_the_primary_stays_first_and_duplicates_collapse():
    """Order is the order given — the primary is the plan you want spent
    first. A key listed twice must not be tried twice, or a spent key gets a
    second turn ahead of a full one."""
    _env(ODDS_API_KEY="aaa", ODDS_API_KEYS="aaa,bbb", ODDS_API_KEY_2="bbb")
    assert O.api_keys() == ["aaa", "bbb"]


def test_an_explicit_key_wins_outright():
    _env(ODDS_API_KEY="aaa", ODDS_API_KEY_2="bbb")
    assert O.api_keys("zzz") == ["zzz"]


def test_no_key_at_all_says_how_to_add_one():
    _env()
    try:
        O.get_api_key()
    except O.OddsAPIError as exc:
        assert "ODDS_API_KEY_2" in str(exc), "the error never mentions spares"
    else:
        raise AssertionError("a missing key did not raise")


# --- what "spent" means -----------------------------------------------------
def test_a_key_we_have_never_called_is_not_spent():
    """The whole trap. Unknown is not zero, and a ring that confuses them
    walks past a full plan to report that everything is empty."""
    p = _budget()
    assert B.key_is_spent("never-used", p) is False


def test_a_key_the_api_refused_is_spent_and_stays_spent():
    p = _budget()
    B.mark_key_spent("aaa", p)
    assert B.key_is_spent("aaa", p) is True
    # ...and a later report of real credits clears it, because a plan resets
    B.record_quota(19000, 1000, p, key="aaa")
    assert B.key_is_spent("aaa", p) is False


def test_the_state_file_never_stores_the_key_itself():
    """It lives in a gitignored cache directory, which is not the same as
    being a safe place to write a secret."""
    p = _budget()
    B.record_quota(500, 10, p, key="super-secret-key")
    body = open(p, encoding="utf-8").read()
    assert "super-secret-key" not in body
    assert B.fingerprint("super-secret-key") in body


# --- the pool ---------------------------------------------------------------
def test_the_headline_balance_is_the_whole_ring():
    """The pacer only ever looks at `remaining`. One key reporting zero while
    a second sits untouched must not read as "the operation is out of
    credits" — that is the entire point of attaching a second key."""
    p = _budget()
    B.record_quota(0, 20000, p, key="aaa")
    B.record_quota(20000, 0, p, key="bbb")
    assert B.load(p).remaining == 20000


def test_the_pool_holds_whichever_order_the_keys_were_measured_in():
    """The real sequence is: key one is measured full, key one runs dry, key
    two gets measured. Asserting only the order that happens to leave the
    full key last lets a pool that never adds anything pass."""
    for order in (("aaa", 0, "bbb", 20000), ("bbb", 20000, "aaa", 0)):
        p = _budget()
        k1, v1, k2, v2 = order
        B.record_quota(v1, 0, p, key=k1)
        B.record_quota(v2, 0, p, key=k2)
        assert B.load(p).remaining == 20000, order


def test_an_unmeasured_key_is_not_counted_as_a_full_plan():
    """The ring is TRIED in full; only the arithmetic is conservative.
    Counting a key we have never called as 20,000 credits would let the pacer
    plan an evening against money that may not exist."""
    p = _budget()
    B.record_quota(6000, 14000, p, key="aaa")
    assert B.load(p).remaining == 6000


# --- the switch -------------------------------------------------------------
def test_the_next_key_is_the_next_one_with_credits():
    _env(ODDS_API_KEY="aaa", ODDS_API_KEY_2="bbb", ODDS_API_KEY_3="ccc")
    p = _budget()
    old = B.STATE_PATH
    B.STATE_PATH = p
    try:
        B.mark_key_spent("bbb", p)
        assert O._next_key("aaa") == "ccc", "a spent key was handed back"
        assert O._next_key("ccc") is None, "the ring did not end"
    finally:
        B.STATE_PATH = old


def test_the_retry_rebills_the_same_request_to_the_new_key():
    """The refused call cost nothing — it was rejected — so the identical
    request goes out again on the next key. Only the apiKey may change."""
    url = ("https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
           "?apiKey=aaa&regions=us&markets=h2h,totals&oddsFormat=american")
    assert O._url_key(url) == "aaa"
    swapped = O._with_key(url, "bbb")
    assert O._url_key(swapped) == "bbb"
    for part in ("regions=us", "oddsFormat=american", "baseball_mlb"):
        assert part.split("=")[0] in swapped
    assert "aaa" not in swapped


def test_an_exhausted_key_switches_mid_request_and_the_call_succeeds():
    """The behaviour the ring exists for, exercised through the real request
    path rather than around it.

    The API answers a spent key with a 401 carrying OUT_OF_USAGE_CREDITS. The
    refusal costs nothing, so the identical request goes straight back out on
    the next key. Everything above only tested the bookkeeping; this tests
    that a build which would have died at 13:53 keeps running."""
    import io
    import json
    import urllib.error
    import urllib.request

    _env(ODDS_API_KEY="spent-key", ODDS_API_KEY_2="fresh-key")
    p = _budget()
    old_state, old_open = B.STATE_PATH, urllib.request.urlopen
    tried = []

    class _Resp:
        headers = {"x-requests-remaining": "19999", "x-requests-used": "1"}
        def read(self): return json.dumps([{"id": "evt"}]).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        key = O._url_key(req.full_url)
        tried.append(key)
        if key == "spent-key":
            raise urllib.error.HTTPError(
                req.full_url, 401, "Unauthorized", {},
                io.BytesIO(b'{"message":"OUT_OF_USAGE_CREDITS"}'))
        return _Resp()

    B.STATE_PATH = p
    urllib.request.urlopen = fake_urlopen
    cache = tempfile.mkdtemp()
    old_cache = O.CACHE_DIR
    O.CACHE_DIR = __import__("pathlib").Path(cache)
    try:
        data, quota = O._request(
            "https://api.the-odds-api.com/v4/x?apiKey=spent-key&regions=us",
            "ring_test.json", ttl=0)
        assert tried == ["spent-key", "fresh-key"], tried
        assert data == [{"id": "evt"}], "the retry did not return the payload"
        assert B.key_is_spent("spent-key", p) is True
        assert B.key_is_spent("fresh-key", p) is False
    finally:
        urllib.request.urlopen = old_open
        B.STATE_PATH = old_state
        O.CACHE_DIR = old_cache
        _env()


def test_the_active_key_skips_the_spent_one():
    _env(ODDS_API_KEY="aaa", ODDS_API_KEY_2="bbb")
    p = _budget()
    old = B.STATE_PATH
    B.STATE_PATH = p
    try:
        assert O.get_api_key() == "aaa"
        B.mark_key_spent("aaa", p)
        assert O.get_api_key() == "bbb"
        # Every key empty: still hand back the first, so the caller gets the
        # API's own answer rather than a guess from a stale state file.
        B.mark_key_spent("bbb", p)
        assert O.get_api_key() == "aaa"
    finally:
        B.STATE_PATH = old
        _env()


if __name__ == "__main__":
    import re as _re
    declared = _re.findall(r"^def (test_\w+)",
                           open(__file__, encoding="utf-8").read(), _re.M)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert not set(declared) - {f.__name__ for f in fns}
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
