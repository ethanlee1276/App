"""Every ESPN feed was 403ing on a User-Agent, and failing quietly.

Found 2026-08-08. `nflpre.py` could not fetch a preseason schedule while a
bare `urllib.request.urlopen` on the identical URL, from the same machine
in the same minute, returned it. The difference was one header:

    User-Agent: qellys-book/0.1 (+nflverse loader)  ->  HTTP 403
    urllib's own default                            ->  200, 1 game

ESPN rejects the unfamiliar string. The custom agent is not a disguise
being removed — sending none is MORE honest, since urllib then identifies
the client as exactly what it is.

**The reason this needed a test file rather than a one-line fix.** Four
modules reach site.api.espn.com through the shared fetcher: NFL live
scores, college football, hoops, and the new preseason source. All four
were 403ing, and none of them said so — `fetch_text` and `fetch_json` fall
back to a stale cache on any network failure, which is right for a flaky
connection and indistinguishable from a working feed when the failure is
permanent. The live scores on the board had been coming from cache.

Run directly: `python3 tests/test_espn_agent.py`
"""

import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import cfbdata, espnhoops, fetch                # noqa: E402
from engine.sources import livescores, nflpreseason                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Every module that talks to ESPN. A new one added without the opt-out
#: will 403 in production and read as a quiet day.
ESPN_MODULES = (livescores, cfbdata, espnhoops, nflpreseason)


def test_the_fetchers_can_send_no_user_agent_at_all():
    """`DEFAULT_AGENT` has to mean "omit the header", not "send something
    else" — the point is to let urllib supply its own."""
    for fn in (fetch.fetch_text, fetch.fetch_json):
        assert "user_agent" in inspect.signature(fn).parameters, fn.__name__
    src = inspect.getsource(fetch.fetch_text)
    assert "if user_agent is DEFAULT_AGENT" in src
    assert "{}" in src, "no branch that sends an empty header dict"


def test_the_default_is_still_the_projects_own_agent():
    """Only ESPN needs the opt-out. Everything else should keep announcing
    itself, and a blanket change would remove that from feeds that are
    perfectly happy."""
    for fn in (fetch.fetch_text, fetch.fetch_json):
        assert (inspect.signature(fn).parameters["user_agent"].default
                is fetch.USER_AGENT), fn.__name__


def test_every_espn_call_opts_out():
    """The whole point. One module left on the default 403s, and because
    both fetchers fall back to a stale cache it looks like a slow news day
    rather than a broken feed.

    Walked as an AST rather than matched with a regex: the first cut tried
    to balance parentheses by hand, stopped at the first character, and
    reported every call as broken including the fixed ones. A keyword
    argument is a thing the parser already knows about.
    """
    import ast
    missed = []
    for mod in ESPN_MODULES:
        src = open(mod.__file__, encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fn not in ("fetch_text", "fetch_json"):
                continue
            kw = {k.arg for k in node.keywords}
            if "user_agent" not in kw:
                missed.append(f"{os.path.basename(mod.__file__)}"
                              f":{node.lineno} {fn}")
    assert not missed, missed


def test_each_espn_module_imports_the_sentinel():
    for mod in ESPN_MODULES:
        src = open(mod.__file__, encoding="utf-8").read()
        assert "DEFAULT_AGENT" in src, mod.__name__


def test_the_measured_403_is_recorded_where_it_will_be_read():
    """A future reader will see a fetcher opting out of its own User-Agent
    and assume it is cargo cult unless the measurement is next to it."""
    src = inspect.getsource(fetch)
    assert "403" in src
    assert "not a disguise" in src.lower() or "honest" in src.lower()


def test_a_stale_cache_is_still_the_fallback_and_that_is_the_hazard():
    """Not a bug to fix here, but the reason this went unnoticed, and worth
    pinning so nobody 'improves' the fallback away without knowing it is
    load-bearing for offline runs — or leaves it silent forever."""
    src = inspect.getsource(fetch.fetch_text)
    assert "path.exists()" in src and "read_text" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
