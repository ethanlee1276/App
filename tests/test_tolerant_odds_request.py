"""One market the API refuses costs one call, never the event.

The 2026-09-10 incident: `player_pass_tds` went onto the NFL request and
both NFL boards emptied inside a rebuild, because every market for an
event rides one `markets=` parameter and a key the API would not serve
failed the whole event. The note left behind said: put it back only
behind a request that tolerates one bad key. This is that request.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as oa  # noqa: E402

BAD = oa.PASS_TD_ODDS_KEY


def _wire(refuse_when=lambda url: BAD in url, message=None):
    """A fake API: refuses a request naming the bad key, serves the rest."""
    calls = []
    def fake(url, cache_name, ttl=300, timeout=30, cache_only=False):
        calls.append(url)
        if refuse_when(url):
            raise oa.OddsAPIError(message or (
                'Odds API HTTP 422: {"message":"Invalid market(s): '
                f'{BAD}","error_code":"INVALID_MARKET"}}'))
        return {"id": "ev", "url": url}, oa.Quota()
    return calls, fake


def _patched(fake):
    keep = (oa._request, oa._key_for)
    oa._request = fake
    oa._key_for = lambda api_key, cache_only: "k"
    oa.REJECTED_MARKETS.clear()
    def restore():
        oa._request, oa._key_for = keep
        oa.REJECTED_MARKETS.clear()
    return restore


def test_a_refused_key_is_dropped_and_the_event_retried_without_it():
    calls, fake = _wire()
    restore = _patched(fake)
    try:
        payload, _ = oa.fetch_event_odds("ev1", "key", sport="nfl")
        assert len(calls) == 2, calls
        assert BAD in calls[0] and BAD not in calls[1]
        assert "player_pass_yds" in calls[1] and "player_receptions" in calls[1]
        assert payload["id"] == "ev"
        assert BAD in oa.REJECTED_MARKETS
    finally:
        restore()


def test_the_next_event_never_asks_for_the_refused_key_again():
    """Once is one refused call. Twice is paying for the same lesson
    every game of the week."""
    calls, fake = _wire()
    restore = _patched(fake)
    try:
        oa.fetch_event_odds("ev1", "key", sport="nfl")
        n = len(calls)
        oa.fetch_event_odds("ev2", "key", sport="nfl")
        assert len(calls) == n + 1, calls[n:]
        assert BAD not in calls[-1]
    finally:
        restore()


def test_an_error_naming_no_key_drops_only_the_unproven_one():
    calls, fake = _wire(message="Odds API HTTP 422: unknown market in request")
    restore = _patched(fake)
    try:
        oa.fetch_event_odds("ev1", "key", sport="nfl")
        assert len(calls) == 2 and BAD not in calls[1]
        assert "player_rush_yds" in calls[1]
    finally:
        restore()


def test_an_error_about_anything_else_still_raises():
    """Quota, auth, the network: not a bad key, not this guard's to swallow."""
    calls, fake = _wire(refuse_when=lambda url: True,
                        message="Odds API auth/quota error 401: bad key")
    restore = _patched(fake)
    try:
        try:
            oa.fetch_event_odds("ev1", "key", sport="nfl")
        except oa.OddsAPIError:
            pass
        else:
            raise AssertionError("an auth error was swallowed")
        assert len(calls) == 1
        assert not oa.REJECTED_MARKETS
    finally:
        restore()


def test_college_never_asks_for_the_key_and_is_untouched():
    calls, fake = _wire()
    restore = _patched(fake)
    try:
        oa.fetch_event_odds("ev1", "key", sport="cfb")
        assert len(calls) == 1 and BAD not in calls[0]
    finally:
        restore()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
