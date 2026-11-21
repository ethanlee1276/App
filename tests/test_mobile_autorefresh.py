"""The board went stale on the phone until the tab was closed and reopened.

"the auto update doesn't work. The mlb data says it 10 mins stale so I have
to close the website and re load it for the data to update."

Three separate faults, each sufficient on its own.

THE CACHE. The poll URL was byte-identical on every refresh — same sport,
same three slider values, no cache-buster, no no-store. iOS Safari answered
from its own cache, so the timer could fire every 30 seconds for ten
minutes and the page never changed. Closing the tab and reopening it is
close to the only thing that misses that cache, which is exactly the
reported workaround.

THE TIMER. Polling only ran while a game was LIVE; otherwise the interval
was cleared outright. Between builds the board still moves — new picks,
settled bets, a paid odds pull — so outside live windows the page only ever
aged, never updated.

THE PHONE. iOS throttles setInterval hard when a tab is backgrounded and
suspends it when the phone locks. After a back-forward-cache restore the
page resumes with its timers dead and no `load` event to restart them. A
timer alone cannot fix this; something has to fire when the page comes
back.

Verified in a mobile browser before shipping: after eleven seconds idle a
visibilitychange produced exactly one fetch, an immediate second switch
produced none, and every URL was unique.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("//"))


BODY = _strip_comments(APP)


# --- the cache ---------------------------------------------------------------
def test_the_slate_fetch_is_cache_busted():
    """Identical URL every poll = Safari serves its own copy forever."""
    assert "`${meta.api}?${params}&_=${Date.now()}`" in BODY


def test_the_slate_fetch_also_asks_the_browser_not_to_store_it():
    i = BODY.index("${meta.api}?${params}")
    assert 'cache: "no-store"' in BODY[i:i + 200]


def test_the_fallback_fetch_is_cache_busted_too():
    """It is the path a phone hits most — the static file, no API."""
    assert "`${meta.fallback}?_=${Date.now()}`" in BODY
    i = BODY.index("${meta.fallback}?_=")
    assert 'cache: "no-store"' in BODY[i:i + 200]


# --- the timer ---------------------------------------------------------------
def test_polling_continues_when_no_game_is_live():
    """It used to clearInterval entirely, so the page only aged."""
    i = BODY.index("function manageAutoRefresh()")
    block = BODY[i:i + 1200]
    assert "state.livePolling ? 30000 : 120000" in block
    assert "clearInterval(state.refreshTimer); state.refreshTimer = null;\n  } else {" \
        not in block, "the idle branch still kills the timer outright"


def test_a_static_page_still_stops_polling():
    """Nothing behind it to refresh from — polling would be pure noise."""
    i = BODY.index("function manageAutoRefresh()")
    block = BODY[i:i + 1200]
    assert "if (state.static)" in block


def test_changing_cadence_replaces_the_timer_rather_than_stacking_one():
    """A game going live flips 120s to 30s. Without clearing first, both
    intervals run and every poll doubles for the rest of the session."""
    i = BODY.index("function manageAutoRefresh()")
    block = BODY[i:i + 1200]
    j = block.index("state.refreshEvery !== every")
    assert "clearInterval(state.refreshTimer);" in block[j:j + 250]


# --- the phone ---------------------------------------------------------------
def test_the_page_refreshes_when_it_becomes_visible_again():
    assert 'document.addEventListener("visibilitychange"' in BODY
    i = BODY.index('addEventListener("visibilitychange"')
    assert 'document.visibilityState === "visible"' in BODY[i:i + 200]


def test_a_bfcache_restore_is_handled_separately():
    """Swiping back or reopening the tab restores a frozen page and fires
    NO visibilitychange. visibilitychange and pageshow each catch a case
    the other misses; both are required."""
    assert 'window.addEventListener("pageshow"' in BODY
    i = BODY.index('addEventListener("pageshow"')
    assert "e.persisted" in BODY[i:i + 200]


def test_returning_twice_in_a_row_does_not_refetch():
    """Tab-switching should not become a request storm."""
    i = BODY.index("function refreshOnReturn()")
    block = BODY[i:i + 500]
    assert "state.lastLoad" in block
    assert "RETURN_REFRESH_AFTER_MS" in block


def test_the_return_guard_is_short_enough_to_be_useful():
    """Ten minutes away must refresh. The guard exists to stop a storm,
    not to make returning feel broken."""
    m = re.search(r"RETURN_REFRESH_AFTER_MS = (\d+)", APP)
    assert m and int(m.group(1)) <= 30000


def test_a_static_page_does_not_refetch_on_return_either():
    i = BODY.index("function refreshOnReturn()")
    assert "if (state.static) return;" in BODY[i:i + 300]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
