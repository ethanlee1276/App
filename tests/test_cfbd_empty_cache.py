"""An empty answer was cached for thirty days, so it never got asked again.

Ethan: "why has this been saying zero teams for like 3 weeks."

`SEASON_TTL` is 30 * 24 * 3600. `/talent?year=2026` answered 200 with an
empty array — CFBD had not published the season's composites yet, which
is the ordinary state of that endpoint before a season — and `_get`
wrote `[]` to disk like any other success, then served it for a MONTH
without asking again.

A temporary absence became a permanent one. Three weeks is what a
thirty-day TTL looks like from inside.

AN EMPTY PAYLOAD IS THE ONE THAT MUST NOT BE CACHED LONG. A full answer
is a fact that will not change this season. An empty one is almost
always "not published yet", and the entire value of asking again is that
the answer changes.

TWO PATHS SERVED IT AND BOTH NEEDED FIXING. The read path had the TTL;
the network-failure fallback then returned the same empty cache anyway,
on the reasoning that "a stale cache beats an exception". True of a
cache that HOLDS something — but falling back to `[]` returns nothing
while reporting success, so the caller cannot tell "the feed is down"
from "the feed says there is nothing" and picks one silently.

Both now apply on READ, so a cache already poisoned by a month-long
empty entry heals itself on the next cycle rather than needing someone
to know to delete the file.

AND IT WAS MASKING A SECOND FAULT: the droplet's CFBD key is missing or
invalid (a live curl returns Unauthorized). The app never noticed
because the cache answered every time. Once an empty entry expires in
minutes, that key failure surfaces as the honest "refused the key" note
instead of a silent zero.

Run directly: `python3 tests/test_cfbd_empty_cache.py`
"""

import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.sources import cfbd as C


def _dir():
    d = pathlib.Path(tempfile.mkdtemp())
    C.CACHE_DIR = d
    return d


def _stamp(d, name, payload, age_seconds):
    p = d / name
    p.write_text(json.dumps(payload))
    t = time.time() - age_seconds
    os.utime(p, (t, t))
    return name


def _get(name):
    """Read through `_get` with the network SIMULATED as unreachable, so
    each test takes the branch it is named for.

    IT USED TO RELY ON THE HOST HAVING NO ROUTE TO CFBD, and that is the
    difference between a sandbox and a CI runner. `cfbd._get` has two
    failure branches and the environment picks which one runs:

      * no network  -> `urlopen` raises a connection error -> `except
        Exception` -> falls back to a cache that holds content. This is
        the branch `test_the_network_failure_fallback_keeps_a_cache_with
        _content` asserts.
      * network up  -> CFBD answers 401 to `Bearer test-key` -> `except
        urllib.error.HTTPError` -> raises `CFBDUnavailable` and never
        reaches the stale-cache fallback below it.

    So the file was green in the sandbox it was written in and red on
    every GitHub runner, which is why `tests.yml` failed on this repo's
    working branch for eight consecutive commits while every session's
    log reported a green suite. The nightly health Routine cannot catch
    it either: it runs in the same blocked sandbox, and its own charter
    names this class — "check whether the TEST is: a test that reads a
    real store, a real database, or the network... If a test's verdict
    depends on machine state, isolate it."

    Simulating the failure isolates it: the branch under test is now the
    branch that runs, on any host.
    """
    import urllib.request

    def _down(req, timeout=None):
        raise OSError("network unavailable (simulated)")

    saved = urllib.request.urlopen
    urllib.request.urlopen = _down
    try:
        return C._get("/talent", {}, name, api_key="test-key")
    finally:
        urllib.request.urlopen = saved


# --- the two lifetimes ----------------------------------------------------
def test_an_empty_answer_expires_in_minutes_not_a_month():
    assert C.EMPTY_TTL <= 3600
    assert C.SEASON_TTL >= 7 * 24 * 3600


def test_a_full_answer_still_keeps_the_season():
    """The caching is not the bug and must not be thrown out with it —
    a composite is a fact that does not change mid-season."""
    d = _dir()
    name = _stamp(d, "full.json", [{"school": "Alabama", "talent": 900.0}],
                  10 * 24 * 3600)
    assert _get(name) == [{"school": "Alabama", "talent": 900.0}]


def test_an_empty_answer_inside_its_window_is_still_served():
    """Minutes of caching still spares the API a request per loop tick."""
    d = _dir()
    assert _get(_stamp(d, "fresh.json", [], 60)) == []


def test_an_empty_answer_past_its_window_is_not_served():
    """THE THREE-WEEK BUG. With no network the refusal surfaces as a
    raise, which is the honest answer — the caller learns nothing is
    known rather than being told the feed is empty."""
    d = _dir()
    name = _stamp(d, "stale_empty.json", [], 3600)
    try:
        got = _get(name)
    except C.CFBDUnavailable:
        return
    raise AssertionError(f"served a stale empty cache: {got!r}")


def test_an_empty_dict_counts_as_empty_too():
    """Some endpoints answer `{}` rather than `[]`."""
    d = _dir()
    name = _stamp(d, "stale_obj.json", {}, 3600)
    try:
        _get(name)
    except C.CFBDUnavailable:
        return
    raise AssertionError("served a stale empty object")


# --- the fallback path, which served it too -------------------------------
def test_the_network_failure_fallback_keeps_a_cache_with_content():
    """Unchanged behaviour where it was right: last season's composite
    beats an exception."""
    d = _dir()
    name = _stamp(d, "old_full.json", [{"school": "Georgia"}],
                  400 * 24 * 3600)          # long past any TTL
    assert _get(name) == [{"school": "Georgia"}]


def test_the_fallback_refuses_an_empty_cache():
    """Falling back to `[]` returns nothing while reporting success."""
    d = _dir()
    name = _stamp(d, "old_empty.json", [], 400 * 24 * 3600)
    try:
        _get(name)
    except C.CFBDUnavailable:
        return
    raise AssertionError("fell back to an empty cache")


def test_the_fallback_reasoning_is_written_down():
    import inspect
    src = inspect.getsource(C._get)
    assert "only if it HOLDS" in src


# --- it heals a cache that is already poisoned ----------------------------
def test_a_month_old_empty_entry_needs_no_manual_deletion():
    """Applied on READ, so the droplet's existing poisoned entry expires
    by itself on the next cycle. A fix that needs someone to know to
    delete a file is a fix that does not ship."""
    d = _dir()
    name = _stamp(d, "poisoned.json", [], 25 * 24 * 3600)
    try:
        _get(name)
    except C.CFBDUnavailable:
        return
    raise AssertionError("still serving the poisoned entry")


def test_a_corrupt_cache_file_is_ignored_rather_than_fatal():
    d = _dir()
    (d / "bad.json").write_text("{not json")
    try:
        _get("bad.json")
    except C.CFBDUnavailable:
        return
    raise AssertionError("a corrupt cache should not be served")


def test_the_helper_simulates_the_outage_rather_than_relying_on_one():
    """The pin that would have caught this in the sandbox.

    Every other test here passes whether the helper stubs the network or
    merely assumes it is down — that is exactly why the bug survived
    eight CI runs while every local suite reported green. Reverting the
    helper has to fail SOMEWHERE a session actually looks, so it fails
    here.
    """
    import inspect

    src = inspect.getsource(_get)
    assert "urllib.request.urlopen = _down" in src, \
        "the helper is relying on the host having no network again"
    assert "finally" in src and "urlopen = saved" in src, \
        "a stub left installed would leak into every later test"


def test_the_two_failure_branches_are_still_distinct():
    """`cfbd._get` treats a refused key and a dead network differently —
    401 raises immediately, a connection error consults the cache first.
    The bug was a test that could only ever reach the second; this pins
    that they remain two branches, so simulating one is meaningful."""
    import inspect

    src = inspect.getsource(C._get)
    assert "except urllib.error.HTTPError" in src
    assert "except Exception" in src
    http_at = src.index("except urllib.error.HTTPError")
    generic_at = src.index("except Exception")
    assert http_at < generic_at, "the HTTPError branch must come first"
    # …and only the generic branch reaches the stale-cache fallback.
    assert "path_c.exists()" in src[generic_at:]
    assert "path_c.exists()" not in src[http_at:generic_at]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
