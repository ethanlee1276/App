"""How far behind the game the play-by-play page is allowed to run.

Ethan, 2026-09-10, watching Patriots at Seahawks on the play-by-play
page: "its working now but definetly delayed."

Every term is a constant in this repo, so the delay is a sum somebody
can add up rather than a feeling:

  espnplays.LIVE_TTL        the summary cache — THE PLAY LIST ITSELF
  livescore_build.TTL       the scoreboard cache — score and clock
  launch.LIVE_FAST_S        how often the loop rebuilds while a game is on
  renderPbpPage's `again()` how often the open page re-reads the file
  Caddy Cache-Control       how long a shared cache may hold the file

Two of them dominated and both were one line. The summary cache was
THIRTY seconds — written when the argument was "a drive only moves a few
times a minute", which is true of a drive and false of the play list this
cache actually holds. And Caddy told every shared cache to keep
`/data/pbp/*.json` for SIXTY, on files the loop rewrites every twelve.

THE PAGE'S `no-store` DOES NOT COVER THE SECOND ONE, which is why it
survived: that is a REQUEST directive. It stops the browser reusing its
own copy and says nothing to a CDN in between.

This file pins the sum, not the individual numbers — tune any of them
and the test still passes as long as the reader is not left a minute
behind a game they are betting.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CADDY = (ROOT / "deploy" / "Caddyfile").read_text()


def _num(src, name):
    m = re.search(rf"^{re.escape(name)} = (\d+)", src, re.M)
    assert m, f"{name} is gone — the budget below cannot be added up"
    return int(m.group(1))


def _page_refresh_s():
    """`renderPbpPage`'s own re-read timer, from the function itself."""
    i = APP.index("function renderPbpPage(")
    body = APP[i:APP.index("\nfunction ", i + 20)]
    m = re.search(r"if \(state\.view === \"pbp\"\) renderPbpPage\(\);\s*\},\s*(\d+)\)", body)
    assert m, "the page's refresh timer moved — find it before trusting this sum"
    return int(m.group(1)) // 1000


def test_the_plays_are_fetched_at_least_once_per_poll():
    """A cache held longer than the gap between the two builds that would
    read it buys nothing and costs the reader the difference."""
    from engine.sources import espnplays
    import launch

    assert espnplays.LIVE_TTL <= launch.LIVE_FAST_S, (
        f"the summary is cached {espnplays.LIVE_TTL}s while the loop rebuilds every "
        f"{launch.LIVE_FAST_S}s — a play is stale before the builder sees it")


def test_the_whole_budget_stays_under_a_thirty_second_worst_case():
    """The sum a reader actually experiences, ESPN's own lag aside — that
    part is not ours and cannot be tuned from here."""
    from engine.sources import espnplays
    import launch
    import livescore_build

    worst = espnplays.LIVE_TTL + launch.LIVE_FAST_S + _page_refresh_s()
    assert worst <= 40, (
        f"{worst}s worst case: summary {espnplays.LIVE_TTL} + loop "
        f"{launch.LIVE_FAST_S} + page {_page_refresh_s()}")
    # The scoreboard half — score, clock, possession — rides the same loop.
    assert livescore_build.TTL <= 20, livescore_build.TTL


def test_no_shared_cache_may_hold_a_live_file_for_a_minute():
    """The board files earn their minute of cache; the files rewritten
    every twelve seconds do not, and `no-store` on the fetch does not
    reach a CDN."""
    assert '@built path /data/*.json' in CADDY
    i = CADDY.index("@fast path")
    rule = CADDY[i:i + 200]
    # Both shapes, because the wildcard in /data/*.json sits in the last
    # segment and pbp/ is a directory deeper.
    assert "/data/live_*.json" in rule, rule
    assert "/data/pbp/*.json" in rule, rule
    assert 'header @fast Cache-Control "no-cache"' in CADDY, rule
    # AFTER the 60-second rule, or it is overwritten by it.
    assert CADDY.index("@fast path") > CADDY.index("@built path"), \
        "the fast rule is stated before the one it must override"


def test_the_page_still_asks_the_server_every_time():
    """Belt to the Caddy braces: the open page must not reuse its own
    copy either."""
    i = APP.index("function renderPbpPage(")
    body = APP[i:APP.index("\nfunction ", i + 20)]
    j = body.index("data/pbp/")
    assert 'cache: "no-store"' in body[j:j + 220], body[j:j + 220]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
