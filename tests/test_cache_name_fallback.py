"""A change to the odds request never blanks a board on a cached rebuild.

Ethan, 2026-09-14 (Monday): "we are now only showing a money line for
the Chiefs game tonight for the most likely bets ... there's no rushing
props or passing props receiving props or anything like that."

The cause was that morning's deploy. The event cache file is named by
the market list, and `player_pass_tds` joined the NFL request, so a
cached rebuild found nothing under the new name — and nothing under the
09-07 fallback name either, because that one is the same list minus the
ladders. Every NFL event missed its cache, every prop fell to a proxy
price, and only the moneyline (bought by the separate board-level pull)
survived. A payload bought with a different list is still real prices
for the markets it carries; a cached rebuild now serves the newest one
on disk for the event, dated by that file's own age.

Run directly: `python3 tests/test_cache_name_fallback.py`
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as oa                     # noqa: E402
from engine.models import (Team, DefenseProfile, Weather, Game, Prop, GameLog,  # noqa: E402
                           SportsbookLine, RUSH_YDS)
from engine.data_loader import Slate                         # noqa: E402


def _book(key, title, main):
    return {"key": key, "title": title, "markets": [
        {"key": "player_rush_yds", "outcomes": [
            {"name": "Over", "description": "Josh Jacobs", "price": main[1], "point": main[0]},
            {"name": "Under", "description": "Josh Jacobs", "price": main[2], "point": main[0]}]},
        {"key": "h2h", "outcomes": [{"name": "Green Bay Packers", "price": -150},
                                    {"name": "Chicago Bears", "price": 130}]}]}


EVENT = {"id": "e1", "home_team": "Green Bay Packers", "away_team": "Chicago Bears",
         "bookmakers": [_book("draftkings", "DraftKings", (62.5, -110, -110)),
                        _book("fanduel", "FanDuel", (63.5, -105, -115))]}

#: The request as it was BEFORE 2026-09-14: four player markets, the
#: scorer market, the three game markets — no passing TDs, no ladders.
OLD_REQUEST = ["player_pass_yds", "player_rush_yds", "player_reception_yds",
               "player_receptions", "player_anytime_td", "h2h", "totals", "spreads"]


def _slate():
    teams = {"GB": Team("GB", "GB", DefenseProfile("GB")),
             "CHI": Team("CHI", "CHI", DefenseProfile("CHI"))}
    game = Game(home="GB", away="CHI", weather=Weather(dome=False), spread=-2.5, total=47.0)
    logs = [GameLog(week=w, opponent="X", value=70) for w in range(1, 6)]
    prop = Prop(player="Josh Jacobs", team="GB", opponent="CHI", position="RB",
                market=RUSH_YDS, logs=logs, career_avg=68, vs_opponent_avg=None,
                lines=[SportsbookLine(book="proxy", line=65.0)], usage_role="rb1")
    return Slate(date="2026-W02", teams=teams, games=[game], props=[prop])


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val
    def __enter__(self):
        self.old = getattr(self.obj, self.name); setattr(self.obj, self.name, self.val)
    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


def _events(key, ttl=300, sport="nfl", cache_only=False):
    return [EVENT]


def _rebuild(tmp: Path):
    slate = _slate()
    with _Swap(oa, "CACHE_DIR", tmp), _Swap(oa, "list_events", _events):
        res = oa.apply_odds_to_slate(slate, api_key="k", sport="nfl", cache_only=True)
    return res, slate


def test_the_old_name_is_not_todays_name_and_not_the_base_name():
    today = oa.event_cache_name("e1", sport="nfl")
    cfg = oa.SPORT_CONFIG["nfl"]
    base = [m for m in (list(cfg["markets"]) + list(cfg["scorers"]) + list(cfg["alternates"])
                        + ["h2h", "totals", "spreads"]) if m not in cfg["alternates"]]
    old = oa.event_cache_name("e1", OLD_REQUEST, sport="nfl")
    assert old != today and old != oa.event_cache_name("e1", base, sport="nfl"), \
        "the fixture no longer reproduces the miss"


def test_a_cached_rebuild_serves_the_newest_payload_whatever_it_asked_for():
    tmp = Path(tempfile.mkdtemp())
    (tmp / oa.event_cache_name("e1", OLD_REQUEST, sport="nfl")).write_text(json.dumps(EVENT))
    res, slate = _rebuild(tmp)
    assert res.matched == 1 and res.cache_misses == 0, res
    assert res.name_fallback == 1 and res.alt_fallback == 0, res
    assert sorted(ln.line for ln in slate.props[0].lines) == [62.5, 63.5]
    assert all(ln.book != "proxy" for ln in slate.props[0].lines)
    assert slate.games[0].home_ml == -150, "the game price rode in with the props"


def test_the_newest_file_wins_and_a_broken_one_is_a_miss():
    tmp = Path(tempfile.mkdtemp())
    older = tmp / oa.event_cache_name("e1", OLD_REQUEST, sport="nfl")
    older.write_text(json.dumps(EVENT))
    newer = tmp / oa.event_cache_name("e1", OLD_REQUEST + ["player_pass_tds"], sport="nfl")
    newer.write_text(json.dumps({**EVENT, "bookmakers": [_book("fanduel", "FanDuel", (70.5, -120, 100))]}))
    then = time.time() - 3600
    os.utime(older, (then, then))
    with _Swap(oa, "CACHE_DIR", tmp):
        path, payload = oa.newest_event_cache("e1", "nfl")
    assert path == newer and payload["bookmakers"][0]["markets"][0]["outcomes"][0]["point"] == 70.5
    # A corrupt newest file is a miss, not a crash — and not the older file.
    newer.write_text("{not json")
    with _Swap(oa, "CACHE_DIR", tmp):
        assert oa.newest_event_cache("e1", "nfl") == (None, None)
    # Another event's file is never this event's.
    with _Swap(oa, "CACHE_DIR", tmp):
        assert oa.newest_event_cache("e2", "nfl") == (None, None)


def test_nothing_on_disk_is_still_a_counted_miss():
    res, slate = _rebuild(Path(tempfile.mkdtemp()))
    assert res.cache_misses == 1 and res.name_fallback == 0 and res.matched == 0, res
    assert slate.props[0].lines[0].book == "proxy"


def test_the_served_file_is_dated_by_its_own_age():
    """The payload found under another name is as old as THAT file. Dated
    under today's name it would answer None — nothing cached, current by
    construction — and a days-old payload would walk under the ceiling."""
    tmp = Path(tempfile.mkdtemp())
    path = tmp / oa.event_cache_name("e1", OLD_REQUEST, sport="nfl")
    path.write_text(json.dumps(EVENT))
    then = time.time() - 3 * 86400
    os.utime(path, (then, then))
    res, slate = _rebuild(tmp)
    assert res.name_fallback == 1, res
    assert res.stale_prop_events == 1 and res.matched == 0, res
    assert slate.props[0].lines[0].book == "proxy"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
