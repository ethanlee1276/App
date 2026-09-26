"""A 404 is not a blocked network, and telling them apart is the message.

Three nflverse loaders — weekly stats, depth charts, injuries — each carried
the same hardcoded sentence for every possible failure:

    "... are unavailable here (GitHub release access is blocked by this
    environment's egress policy). Export them once and save to <path> —
    e.g. in Python: nfl.import_weekly_data([2026])..."

That states one of two possible causes as though it were known. Printed on
Ethan's own Mac on 2026-08-08, on a working connection, directly above its
own last-error line:

    (last error: Could not fetch
     https://github.com/nflverse/.../player_stats_2026.csv.gz:
     HTTP Error 404: Not Found)

The file was not blocked. It does not exist: nflverse publishes a season's
player stats once games have been played, and the 2026 regular season had
not started. And the advice was worse than silence — `import_weekly_data`
reads that same release, so following it fails identically. The reader is
sent to prove a working network is working.

The pipeline itself was already right: `build_slate` catches this exact
case and falls back to the prior-season carry, with a comment saying the
file "404s because the games have not been played". Only the message
disagreed with the code.

Run directly: `python3 tests/test_release_errors.py`
"""

import io
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import fetch                                   # noqa: E402
from engine.sources.fetch import (DataUnavailable,                 # noqa: E402
                                  release_unavailable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Every loader that reaches an nflverse release and has to explain a miss.
LOADERS = ("engine/sources/nflverse.py", "engine/sources/depthcharts.py",
           "engine/sources/injuries.py")


def _http(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))


# --- the status has to survive the raise -------------------------------------
def test_an_http_status_is_carried_on_the_exception():
    """Without this the caller can only regex the message, which is how the
    status ended up ignored in the first place — it WAS in the text."""
    assert fetch._status_of(_http(404)) == 404
    assert fetch._status_of(_http(403)) == 403


def test_a_failure_with_no_response_has_no_status():
    """A refused CONNECT, a DNS failure or a timeout never got an answer.
    None is the honest value, and it must not read as 0 or as 404."""
    for exc in (TimeoutError("timed out"), OSError("unreachable"),
                urllib.error.URLError("tunnel failed")):
        assert fetch._status_of(exc) is None, exc


def test_data_unavailable_defaults_to_no_status():
    assert DataUnavailable("x").status is None


def test_both_fetchers_attach_the_status():
    import inspect
    for fn in (fetch.fetch_text, fetch.fetch_json):
        src = inspect.getsource(fn)
        assert "status=_status_of(exc)" in src, fn.__name__


# --- the two branches --------------------------------------------------------
def _mk(status):
    return DataUnavailable("Could not fetch u: whatever", status=status)


def test_a_404_does_not_tell_you_to_export_the_file():
    """THE BUG. The export reads the same release that just 404'd, so this
    advice cannot work — and it costs the reader a trip to another machine
    to find that out."""
    msg = str(release_unavailable("weekly player stats", 2026, "/tmp/p.csv",
                                  "nfl.import_weekly_data([2026])",
                                  ["u1", "u2"], _mk(404)))
    assert "nfl_data_py" not in msg
    assert "import_weekly_data" not in msg
    assert "egress" not in msg.lower()


def test_a_404_says_what_it_actually_means():
    msg = str(release_unavailable("weekly player stats", 2026, "/tmp/p.csv",
                                  "nfl.import_weekly_data([2026])",
                                  ["u1", "u2"], _mk(404)))
    assert "404" in msg
    assert "not published" in msg.lower()
    # And that before Week 1 it is the expected answer, not a fault to chase.
    assert "expected" in msg.lower()


def test_an_unreachable_host_still_gets_the_export_recipe():
    """The original advice is RIGHT for this case — that is the whole reason
    the text existed — so the fix must not throw it away."""
    for status in (None, 403, 407, 502):
        msg = str(release_unavailable("weekly player stats", 2026, "/tmp/p.csv",
                                      "nfl.import_weekly_data([2026])",
                                      ["u1"], _mk(status)))
        assert "nfl_data_py" in msg, status
        assert "import_weekly_data" in msg, status
        assert "reachability" in msg.lower(), status


def test_the_status_is_preserved_on_the_rethrown_error():
    """So a caller further up can branch too, rather than re-parsing prose."""
    assert release_unavailable("x", 2026, "p", "e", ["u"], _mk(404)).status == 404
    assert release_unavailable("x", 2026, "p", "e", ["u"], _mk(403)).status == 403


def test_the_404_message_names_what_was_tried():
    """nflverse has renamed these releases before — the loader carries four
    candidate URLs for exactly that reason. When all of them 404 the reader
    needs to see which ones, or "not published" is unfalsifiable."""
    msg = str(release_unavailable("weekly player stats", 2026, "/tmp/p.csv", "e",
                                  ["https://a/x.csv", "https://b/y.csv"],
                                  _mk(404)))
    assert "https://a/x.csv" in msg and "https://b/y.csv" in msg


# --- no loader keeps the old blanket sentence --------------------------------
def test_no_loader_asserts_the_egress_cause_any_more():
    for f in LOADERS:
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        # The docstring may still describe egress as one possibility; what
        # must not survive is asserting it as the reason for a given failure.
        assert "is blocked by this environment's egress policy)" not in src, f


def test_every_release_loader_routes_through_the_shared_branch():
    """Three copies drifted into the same wrong sentence once. One function
    is what stops a fourth."""
    for f in LOADERS:
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        assert "release_unavailable(" in src, f


def test_the_measurement_is_recorded_where_it_will_be_read():
    src = open(os.path.join(ROOT, "engine/sources/fetch.py"),
               encoding="utf-8").read()
    assert "404" in src and "not there" in src.lower()


def test_the_carry_still_survives_a_missing_current_season():
    """The behaviour this message describes. `build_slate` must keep
    treating an absent current-season stats file as survivable — that is
    the case the prior-season carry was built for, and a message change
    must not have quietly made it fatal."""
    import inspect
    from engine.sources import nflverse
    src = inspect.getsource(nflverse.build_slate)
    i = src.index("load_weekly_stats(season)")
    block = src[max(0, i - 400):i + 200]
    assert "except DataUnavailable" in block
    assert "if not carry" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
