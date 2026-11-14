"""The Kalshi player-props probe finds NFL player series and nothing else.

Ethan's Bills @ Rams report 2 (2026-10-12) priced Stafford 250+ passing yards
at "Kalshi 68.5¢"; the site reads no Kalshi player series because none was
known, and Kalshi is unreachable from the build sandbox. `kalshiprops.py` is
the discovery run for the box (runbook step 33). Offline: the fetchers are
handed in.

Run directly: `python3 tests/test_kalshi_player_props_probe.py`
"""
import contextlib
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import kalshiprops as K                                            # noqa: E402

SERIES = [
    {"ticker": "KXNFLPASSYDS", "title": "Pro football passing yards", "tags": ["Football"]},
    {"ticker": "KXNFLRECYDS", "title": "NFL receiving yards", "tags": []},
    {"ticker": "KXNFLSPREAD", "title": "Pro football spread", "tags": ["Football"]},
    {"ticker": "KXNFLGAME", "title": "Pro football game", "tags": ["Football"]},
    {"ticker": "KXNBAPTS", "title": "NBA points", "tags": ["Basketball"]},
    {"ticker": "KXMLBHITS", "title": "MLB hits", "tags": ["Baseball"]},
]


def test_it_keeps_nfl_player_series_and_skips_what_the_site_already_reads():
    keep = [s["ticker"] for s in SERIES if K.is_nfl_player_series(s)]
    assert keep == ["KXNFLPASSYDS", "KXNFLRECYDS"], keep


def test_a_run_prints_counts_and_samples_and_never_touches_the_network():
    calls = []

    def get(url, cache):
        calls.append(url)
        return {"series": SERIES}

    def events(series):
        calls.append(series)
        if series == "KXNFLPASSYDS":
            return [{"markets": [{"ticker": "KXNFLPASSYDS-26OCT12-STAFF-250", "floor_strike": 249.5,
                                  "title": "Matthew Stafford 250+ passing yards", "yes_bid_dollars": "0.6700",
                                  "yes_ask_dollars": "0.7000", "volume": 1200}]}]
        return []

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert K.main([], get=get, events=events) == 0
    text = out.getvalue()
    assert "NFL player-stat series: 2" in text
    assert "KXNFLPASSYDS: 1 open events · 1 markets" in text and "Stafford 250+" in text
    assert "1 series with open events" in text
    assert "KXNFLSPREAD" not in [c for c in calls if not c.startswith("http")], "already read by the site"
    assert set(K.CANDIDATES) <= set(calls), "the candidate tickers are tried even when unlisted"


def test_a_dead_listing_still_tries_the_candidates():
    def get(url, cache):
        raise OSError("refused")

    tried = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        K.main([], get=get, events=lambda s: tried.append(s) or [])
    assert "unavailable" in out.getvalue() and tried == list(K.CANDIDATES)


def test_the_runbook_says_to_run_it():
    run = open(os.path.join(ROOT, "docs", "WHEN_YOU_ARE_HOME.md"), encoding="utf-8").read()
    assert "python3 kalshiprops.py" in run


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
