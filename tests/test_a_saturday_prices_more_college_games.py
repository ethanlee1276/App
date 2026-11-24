"""A college football Saturday prices more games for the same credits (step AEN, 24 November 2026).

Ethan's decisions that day: A, "yes more" college games with priced props, and B, "we always want every sport posting
props and bets and game reports at all times for every games so we learn and dial in and calibrate". A pull buys at
most twelve games, the ranked and power-conference ones first, and it bought the same twelve at every pull of the day
until they kicked off. Now (cfb_build.pull_plan):

  * a game priced in the last two and a half hours, with its kickoff further off than that, gives its place in the
    pull to the next game waiting, and is read from the cache for nothing;
  * inside its last two and a half hours a game is bought every pull, as before;
  * every game not bought is read from the cache, so a cached build shows every game's last paid price;
  * a pull still buys at most its cap; a game after tonight's slate is never bought; a cached build buys nothing;
  * a live failure ends the spend, never the build: the rest are read from the cache.

Offline. Run directly: `python3 tests/test_a_saturday_prices_more_college_games.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import cfb_build as CB                                               # noqa: E402
from engine import pricedplayers                                     # noqa: E402
from engine.sources import oddsapi as oa                             # noqa: E402

UTC = dt.timezone.utc
H = 3600


def _at(h, m=0, day=28):
    return dt.datetime(2026, 11, day, h, m, tzinfo=UTC)


def test_a_fresh_game_gives_its_place_and_one_near_kickoff_is_bought_again():
    now = _at(14)                                            # 9 AM Eastern
    cands = [(0, 0, _at(16), 0, "near"),                     # kicks off in 2h, priced 2h ago: bought again
             (0, 0, _at(20, 30), 1, "fresh"),                # 6.5h off, priced 2h ago: gives its place
             (1, 0, _at(20, 30), 2, "never"),                # nothing on disk: bought
             (1, 0, _at(0, 30, 29), 3, "old"),               # priced 3h ago: bought
             (2, 0, _at(17), 4, "low")]
    ages = {"near": 2 * H, "fresh": 2 * H, "never": None, "old": 3 * H, "low": None}
    buy, held, wanting = CB.pull_plan(cands, ages, 2, now)
    assert buy == {"near", "never"} and held == 1 and wanting == 4, (buy, held, wanting)
    assert CB.pull_plan(cands, ages, 12, now)[0] == {"near", "never", "old", "low"}
    assert CB.pull_plan(cands, ages, 12, now, cache_only=True)[0] == set(), "a cached build buys nothing"
    tonight = _at(23).timestamp()
    assert "old" not in CB.pull_plan(cands, ages, 12, now, until=tonight)[0], "after tonight's slate: never bought"
    assert CB.pull_plan(cands, ages, 0, now)[0] == set()
    assert CB.REPRICE_AFTER_S == 2.5 * H
    assert CB.REPRICE_AFTER_S * 2 <= oa.MAX_PROP_PRICE_AGE, \
        "a price waits at most this plus one pull's gap: inside the six hours it stays bettable"


class _Book:
    """The odds feed and its cache on disk: what each event was last bought at, and every call made."""

    def __init__(self):
        self.written, self.live, self.cached = {}, [], []
        self.now = None
        self.fail = set()

    def fetch(self, eid, key=None, markets=None, books=None, ttl=300, sport="cfb", cache_only=False):
        if cache_only:
            self.cached.append(eid)
            if eid not in self.written:
                raise oa.OddsAPIError("no cached copy")
            return {"id": eid, "bookmakers": []}, oa.Quota()
        if eid in self.fail:
            raise oa.OddsAPIError("down")
        self.live.append(eid)
        self.written[eid] = self.now
        return {"id": eid, "bookmakers": []}, oa.Quota("1", "1")

    def age(self, eid, markets=None, books=None, sport="cfb", now=None):
        return None if eid not in self.written else self.now - self.written[eid]


class _Tracker:
    def see(self, *a, **k):
        return []

    def save(self):
        pass


class _Swap:
    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.was = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.was)


def _saturday(n=36):
    """Thirty-six games in three waves (noon, 3:30 and 7:30 PM Eastern); the first twelve ranked SEC games."""
    games, priced = [], {}
    waves = (_at(17), _at(20, 30), _at(0, 30, 29))
    for i in range(n):
        g = {"game_id": f"g{i}", "home": f"H{i}", "away": f"A{i}", "weekday": "saturday",
             "kickoff": waves[i % 3].strftime("%Y-%m-%dT%H:%MZ")}
        if i < 12:
            g.update(home_rank=i + 1, home_conference="SEC", away_conference="SEC")
        games.append(g)
        priced[g["game_id"]] = {"event_id": f"e{i}", "spread": (-3.0, -110, -110), "total": (50.5, -110, -110)}
    return games, priced


def _day(reprice_after):
    """Saturday's first three pulls (7 AM, 9 AM and noon Eastern) at twelve games each, and the games each bought."""
    book = _Book()
    games, priced = _saturday()
    bought = []
    with _Swap(oa, "fetch_event_odds", book.fetch), _Swap(oa, "event_cache_age", book.age), \
            _Swap(pricedplayers, "Tracker", _Tracker), _Swap(CB, "REPRICE_AFTER_S", reprice_after):
        for when in (_at(12), _at(14), _at(16, 30)):
            book.now = when.timestamp()
            book.live.clear()
            *_, note, _age = CB.attach_player_quotes(games, priced, cache_only=False, now=when, cap=12)
            assert len(book.live) <= 12, ("the pull spends what it did", book.live)
            bought.append(list(book.live))
    return bought, note, book


def test_three_saturday_pulls_price_more_games_for_the_same_credits():
    before, _note, _b = _day(0)                         # every game bought again each pull, as before step AEN
    after, note, book = _day(CB.REPRICE_AFTER_S)
    assert [len(x) for x in before] == [12, 12, 12] and [len(x) for x in after] == [12, 12, 12], (before, after)
    assert len({e for x in before for e in x}) == 12, "the same twelve, three times"
    # At 9 AM every ranked game was priced two hours before and kicks off three hours or more away: all twelve give
    # their places to games never priced, twenty-four games by 11:30.
    assert not set(after[1]) & set(after[0]) and all(int(e[1:]) >= 12 for e in after[1]), after[1]
    assert len({e for x in after for e in x}) == 24, after
    # At 11:30 the ranked games, priced four and a half hours before (the noon ones half an hour from kickoff), are
    # bought again before they pass the six hours a price stays bettable; the ranked games come first, as before.
    assert set(after[2]) == set(after[0]), after[2]
    assert "priced, 12 bought at 14 credit(s) each" in note, note


def _sixty(marquee=18):
    """A sixty-game Saturday in four waves (noon, 3:30, 7:30 and 10:30 PM Eastern: 21, 18, 15 and 6 games), every
    third or fourth game a ranked SEC game."""
    waves = ((_at(17), 21), (_at(20, 30), 18), (_at(0, 30, 29), 15), (_at(3, 30, 29), 6))
    games, priced, k = [], {}, 0
    for when, n in waves:
        for _j in range(n):
            g = {"game_id": f"g{k}", "home": f"H{k}", "away": f"A{k}", "weekday": "saturday",
                 "kickoff": when.strftime("%Y-%m-%dT%H:%MZ")}
            if k % round(60 / marquee) == 0:
                g.update(home_rank=1, home_conference="SEC", away_conference="SEC")
            games.append(g)
            priced[g["game_id"]] = {"event_id": f"e{k}", "spread": (-3.0, -110, -110), "total": (50.5, -110, -110)}
            k += 1
    return games, priced


#: The pacer's own Saturday: 7 AM, a readiness pull three hours before the noon wave, noon, the 3:30 wave's readiness
#: pull, 3 PM, the 7:30 wave's, 6 PM and the 10:30 wave's (oddsbudget.TOUCHPOINTS, READY_BEFORE_S).
PACER_SATURDAY = (_at(12), _at(14), _at(17), _at(17, 30), _at(20), _at(21, 30), _at(23), _at(0, 30, 29))


def _whole_day(reprice_after, pulls=PACER_SATURDAY, marquee=18):
    book = _Book()
    games, priced = _sixty(marquee)
    kick = {priced[g["game_id"]]["event_id"]: dt.datetime.fromisoformat(g["kickoff"].replace("Z", "+00:00"))
            .timestamp() for g in games}
    buys = 0
    with _Swap(oa, "fetch_event_odds", book.fetch), _Swap(oa, "event_cache_age", book.age), \
            _Swap(pricedplayers, "Tracker", _Tracker), _Swap(CB, "REPRICE_AFTER_S", reprice_after):
        for when in pulls:
            book.now = when.timestamp()
            book.live.clear()
            CB.attach_player_quotes(games, priced, cache_only=False, now=when, cap=12)
            assert len(book.live) <= 12
            buys += len(book.live)
    at_kick = [(kick[e] - book.written[e]) / H for e in book.written]
    return {"priced": len(book.written), "buys": buys, "fresh": sum(a < 2 for a in at_kick),
            "over_six": sum(a > 6 for a in at_kick)}


def test_a_whole_saturday_prices_forty_nine_games_where_it_priced_twenty_nine():
    """The simulation REPRICE_AFTER_S was chosen on (cfb_build): the same buys, twenty more games priced at least
    once, as many priced within two hours of their kickoff, and none over six hours old at kickoff."""
    before, after = _whole_day(0), _whole_day(CB.REPRICE_AFTER_S)
    assert before == {"priced": 29, "buys": 90, "fresh": 16, "over_six": 0}, before
    assert after == {"priced": 49, "buys": 89, "fresh": 17, "over_six": 0}, after
    every_two = tuple(_at(12 + 2 * k) if 12 + 2 * k < 24 else _at(12 + 2 * k - 24, 0, 29) for k in range(8))
    b2, a2 = _whole_day(0, every_two), _whole_day(CB.REPRICE_AFTER_S, every_two)
    assert a2["priced"] > b2["priced"] and a2["fresh"] >= b2["fresh"] and a2["over_six"] == 0, (b2, a2)


def test_a_held_game_keeps_its_price_on_the_board():
    book = _Book()
    games, priced = _saturday(6)
    with _Swap(oa, "fetch_event_odds", book.fetch), _Swap(oa, "event_cache_age", book.age), \
            _Swap(pricedplayers, "Tracker", _Tracker):
        book.now = _at(12).timestamp()
        CB.attach_player_quotes(games, priced, cache_only=False, now=_at(12), cap=6)
        book.now = _at(13).timestamp()
        book.live.clear()
        book.cached.clear()
        *_, note, _age = CB.attach_player_quotes(games, priced, cache_only=False, now=_at(13), cap=6)
    # An hour later the noon games (four hours off) hold; nothing kicks off inside two and a half hours.
    assert book.live == [] and sorted(book.cached) == sorted(f"e{i}" for i in range(6)), (book.live, book.cached)
    assert note.startswith("player quotes: 6 of 6 eligible game(s) priced, 0 bought at 14 credit(s) each"), note
    assert "6 priced in the last 2.5h read from the cache, their places given to games waiting" in note, note
    assert "left unpriced" not in note


def test_a_live_failure_ends_the_spend_and_the_rest_are_read_from_the_cache():
    book = _Book()
    games, priced = _saturday(6)
    for e in ("e4", "e5"):
        book.written[e] = _at(6).timestamp()             # bought earlier that morning
    book.fail = {"e1"}
    with _Swap(oa, "fetch_event_odds", book.fetch), _Swap(oa, "event_cache_age", book.age), \
            _Swap(pricedplayers, "Tracker", _Tracker):
        book.now = _at(12).timestamp()
        *_, note, _age = CB.attach_player_quotes(games, priced, cache_only=False, now=_at(12), cap=6)
    # The build's order: the ranked noon games, then 3:30, then 7:30 (e0, e3, e1, e4, e2, e5).
    assert book.live == ["e0", "e3"], ("two bought, then the feed failed on e1: no call after it", book.live)
    assert {"e1", "e4", "e2", "e5"} <= set(book.cached), ("the failed game and the rest read from the cache",
                                                          book.cached)
    assert "player quotes: 4 of 6 eligible game(s) priced, 2 bought" in note, note
    assert "2 left unpriced" in note, note


def test_a_cached_build_shows_every_games_last_paid_price():
    book = _Book()
    games, priced = _saturday(6)
    for i in range(6):
        book.written[f"e{i}"] = _at(11).timestamp()
    with _Swap(oa, "fetch_event_odds", book.fetch), _Swap(oa, "event_cache_age", book.age), \
            _Swap(pricedplayers, "Tracker", _Tracker):
        book.now = _at(12).timestamp()
        *_, note, _age = CB.attach_player_quotes(games, priced, cache_only=True, now=_at(12), cap=2)
    assert book.live == [] and len(set(book.cached)) == 6, (book.live, book.cached)
    assert note.startswith("player quotes: 6 of 6 eligible game(s) priced, 0 bought at 14 credit(s) each (cached)"), note


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
