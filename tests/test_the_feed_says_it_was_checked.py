"""The feed is republished on every sweep, so its age means "last checked",
not "last news".

2026-10-01: Status showed "The feed — 5 hours ago" in red while every board
was current. The feed is event-driven; `scan_all` published only when a
sweep found a new event, so a quiet morning (and a frozen NFL board) read
exactly like a stopped loop. Every sweep now republishes: the merge with no
new events keeps the wire as it was, prunes anything past its window, and
stamps the time.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import feed  # noqa: E402


def test_a_quiet_sweep_still_publishes():
    calls = []
    real_scan, real_pub = feed.scan, feed.publish
    feed.scan = lambda sport, path, now=None: []
    feed.publish = lambda events, now=None: calls.append(list(events)) or 0
    try:
        assert feed.scan_all({"nfl": "x.json", "mlb": "y.json"}) == 0
    finally:
        feed.scan, feed.publish = real_scan, real_pub
    assert calls == [[]], calls


def test_a_sweep_with_news_publishes_it():
    calls = []
    real_scan, real_pub = feed.scan, feed.publish
    feed.scan = lambda sport, path, now=None: [{"id": sport}]
    feed.publish = lambda events, now=None: calls.append(list(events)) or len(events)
    try:
        assert feed.scan_all({"nfl": "x.json"}) == 1
    finally:
        feed.scan, feed.publish = real_scan, real_pub
    assert calls == [[{"id": "nfl"}]]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
