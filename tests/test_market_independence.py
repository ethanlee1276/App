"""One market never costs another — the standing rule, enforced.

Ethan, 2026-09-14: "Anytime we're working on the most likely bets or
edge bets for NFL or any sport, I need you to make sure that issue we
just ran into is not happening anymore. If I'm having an issue seeing a
certain category of props, to make those props show you should not be
affecting another category of props."

The issue: putting passing touchdowns on the NFL request renamed every
event's odds cache file, so a cached rebuild found no payload, every
prop fell to a proxy, and the Monday board showed one moneyline. Three
places let one market's work reach another's rows; each is pinned here
so the rule survives the next change. docs/ONE_MARKET_NEVER_COSTS_ANOTHER.md
is the prose.

Run directly: `python3 tests/test_market_independence.py`
"""

import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely as K                                # noqa: E402
from engine.sources import oddsapi as oa                     # noqa: E402


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val
    def __enter__(self):
        self.old = getattr(self.obj, self.name); setattr(self.obj, self.name, self.val)
    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


def _request_for(sport):
    cfg = oa.SPORT_CONFIG[sport]
    return (list(cfg["markets"]) + list(cfg.get("scorers") or {})
            + list(cfg.get("alternates") or {}) + ["h2h", "totals", "spreads"])


# --- 1. the request: a market joining or leaving never hides a cached payload ----
def test_a_market_joining_or_leaving_the_request_never_hides_the_last_payload():
    """For every sport that buys player markets: file a payload under
    yesterday's request — one market fewer, then one more — and the
    newest-file lookup must find it under today's."""
    for sport, cfg in oa.SPORT_CONFIG.items():
        if not cfg.get("markets"):
            continue
        today = _request_for(sport)
        alts = set(cfg.get("alternates") or {})
        base = [m for m in today if m not in alts]
        fewer = [m for m in today if m != sorted(cfg["markets"])[0]]
        more = today + ["some_market_that_joins_tomorrow"]
        for yesterday in (fewer, more):
            tmp = Path(tempfile.mkdtemp())
            name = oa.event_cache_name("ev1", yesterday, sport=sport)
            # The miss is real: neither today's name nor the base name.
            assert name != oa.event_cache_name("ev1", today, sport=sport), sport
            assert name != oa.event_cache_name("ev1", base, sport=sport), sport
            (tmp / name).write_text(json.dumps({"id": "ev1", "bookmakers": []}))
            with _Swap(oa, "CACHE_DIR", tmp):
                path, payload = oa.newest_event_cache("ev1", sport)
            assert path == tmp / name and payload == {"id": "ev1", "bookmakers": []}, (sport, yesterday)


def test_the_attach_step_reaches_for_the_newest_payload_after_both_names_miss():
    src = inspect.getsource(oa.apply_odds_to_slate)
    at = src.index("result.alt_fallback += 1")
    after = src[at:src.index("result.cache_misses += 1", at)]
    assert '_age_path, payload = newest_event_cache(ev["id"], sport)' in after
    assert "result.name_fallback += 1" in after


# --- 2. a refused key costs one call, never the event ------------------------------
def test_a_refused_key_is_dropped_and_the_event_retried_without_it():
    src = inspect.getsource(oa.fetch_event_odds)
    assert "REJECTED_MARKETS.update(bad)" in src
    assert "return fetch_event_odds(event_id, api_key, markets=kept" in src
    # Every key bought on the strength of documentation is marked, so a
    # refusal that names nothing drops those and keeps the proven rest.
    for key in (oa.PASS_TD_ODDS_KEY, *oa.MLB_ALT_ODDS_TO_MARKET, *oa.HOOPS_ALT_ODDS_TO_MARKET):
        assert key in oa.UNPROVEN_MARKETS, key


# --- 3. the board: a market's seats are its own -----------------------------------
def _row(i, market, prob):
    return {"kind": "prop", "player": f"P{market}{i}", "team": "T", "market": market,
            "model_prob": prob, "implied_prob": prob - 0.03, "odds": -110,
            "book": "DraftKings", "bettable": True}


def test_a_sixth_market_does_not_take_the_lowest_markets_seats():
    """Six NFL markets, ten rows each, passing yards priced lowest of all.
    The old cut kept forty across markets in probability order, which
    gave passing yards zero seats the day passing touchdowns joined."""
    markets = ["anytime_td", "receptions", "rush_yds", "rec_yds", "pass_td", "pass_yds"]
    rows = []
    for k, m in enumerate(markets):
        top = 0.75 - 0.03 * k                   # pass_yds lowest, at 0.60
        rows += [_row(i, m, top - i * 0.001) for i in range(10)]
    assert len(markets) * K.PER_MARKET > K.LIMIT, "the premise: more seats than LIMIT"
    got = K._cut_players(rows, K.LIMIT)
    by = {}
    for r in got:
        by[r["market"]] = by.get(r["market"], 0) + 1
    assert by == {m: K.PER_MARKET for m in markets}, by
    assert len(got) == len(markets) * K.PER_MARKET
    probs = [r["model_prob"] for r in got]
    assert probs == sorted(probs, reverse=True)
    # And with room to spare, the back-fill still tops up to LIMIT.
    few = [_row(i, "receptions", 0.70 - i * 0.001) for i in range(50)] \
        + [_row(i, "pass_yds", 0.56) for i in range(3)]
    got = K._cut_players(few, K.LIMIT)
    assert len(got) == K.LIMIT and sum(1 for r in got if r["market"] == "pass_yds") == 3


def test_every_market_the_nfl_board_ranks_has_a_seat_and_a_shelf():
    from engine import boards
    shelved = set()
    for shelf in boards.FOOTBALL_SHELVES:
        shelved |= set(shelf[2])
    for m in K.RANK_AUC:
        assert m in shelved, f"{m} ranks but has no shelf"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
