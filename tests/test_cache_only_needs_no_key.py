"""A missing key must not throw away the odds we already paid for.

2026-09-09, two hours before the season opener. A build run by hand could
not see the box's API key, and every fetch in `oddsapi` resolved the key
BEFORE it honoured `cache_only`. So the cache-only pass — which touches
no network, spends no credit, and only reads files already on disk —
refused to read them. The build fell back to proxy lines and republished
a good NFL board (173 matched props, 21 priced games) as 286 props, none
priced, no game prices at all.

It printed a warning, not an error: "Odds API unavailable — keeping proxy
lines". The board it had just wiped was the thing it claimed to be
keeping.

A missing key means "you cannot BUY more odds". It has never meant "you
may not read the odds you already bought". Any path where those two are
the same sentence turns a lost environment variable — a hand-run build, a
cron that drops its env, a container that starts before its secrets mount
— into a wiped board, and reports it as weather.

So the demand for a key moves to the moment of spending.
"""

import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.models import Game, Weather                      # noqa: E402
from engine.sources import oddsapi as O                      # noqa: E402

_KEY_VARS = ("ODDS_API_KEY", "ODDS_API_KEYS",
             *(f"ODDS_API_KEY_{i}" for i in range(2, 8)))


class _NoKey:
    """No key anywhere on the ring, as a hand-run build sees it."""

    def __enter__(self):
        self._saved = {k: os.environ.pop(k, None) for k in _KEY_VARS}
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
        return False


class _Slate:
    def __init__(self, games):
        self.games, self.date, self.props = games, "2026-09-13", []


def _game():
    return Game(home="MIN", away="GB", weather=Weather(),
                date="2026-09-13", kickoff="20:25")


def _event():
    return {"home_team": "Minnesota Vikings", "away_team": "Green Bay Packers",
            "commence_time": "2026-09-13T20:25:00Z",
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": "Minnesota Vikings", "price": -118},
                                {"name": "Green Bay Packers", "price": 102}]}]}]}


def _seeded_cache():
    tmp = pathlib.Path(tempfile.mkdtemp())
    path = tmp / "odds_board_nfl_lines.json"
    path.write_text(json.dumps([_event()]))
    old = time.time() - 600
    os.utime(path, (old, old))
    return tmp


def test_a_key_is_still_required_to_spend():
    """The bar has not been lowered, only moved. A path that may reach the
    wire still refuses without a key, and says how to set one."""
    with _NoKey():
        try:
            O._key_for(None, cache_only=False)
        except O.OddsAPIError as exc:
            assert "ODDS_API_KEY" in str(exc)
        else:                                                # pragma: no cover
            raise AssertionError("a spending path accepted no key")


def test_a_cache_only_read_does_not_need_one():
    """It reads a file. There is nothing to authorise."""
    with _NoKey():
        assert O._key_for(None, cache_only=True) == ""


def test_an_explicit_key_still_wins():
    with _NoKey():
        assert O._key_for("abc123", cache_only=True) == "abc123"
        assert O._key_for("abc123", cache_only=False) == "abc123"


def test_the_cached_prices_survive_a_build_that_cannot_see_the_key():
    """THE ACCIDENT, end to end. The payload is on disk and was paid for.
    With no key in the environment the board must still be priced from
    it — not fall back to proxies and republish the slate blank."""
    slate = _Slate([_game()])
    real = O.CACHE_DIR
    O.CACHE_DIR = _seeded_cache()
    try:
        with _NoKey():
            res = O.apply_board_lines_to_slate(slate, cache_only=True)
    finally:
        O.CACHE_DIR = real
    g = slate.games[0]
    assert (g.home_ml, g.away_ml) == (-118, 102), (g.home_ml, g.away_ml)
    assert res.moneylines == 1, res


def test_with_no_cache_and_no_key_it_reports_nothing_rather_than_raising():
    """The other half: an empty cache is still an empty answer, not a
    crash — the caller keeps whatever it already had."""
    slate = _Slate([_game()])
    real = O.CACHE_DIR
    O.CACHE_DIR = pathlib.Path(tempfile.mkdtemp())
    try:
        with _NoKey():
            res = O.apply_board_lines_to_slate(slate, cache_only=True)
    finally:
        O.CACHE_DIR = real
    assert res.moneylines == 0
    assert slate.games[0].home_ml == 0


def test_every_fetch_in_this_module_asks_the_same_way():
    """Six call sites resolved the key, and one of them being right is
    worth nothing — a build takes several of these paths in a row. The
    rule holds module-wide or it does not hold."""
    import inspect
    src = inspect.getsource(O)
    assert "key = get_api_key(api_key)" not in src, (
        "a fetch still demands a key before honouring cache_only")
    assert src.count("key = _key_for(api_key, cache_only)") == 6


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
