"""The NFL slate reads last season once, and works out every market's
positional means in one walk of it (engine/carry.positional_means_all,
engine/sources/nflverse.build_slate).

The NFL build's slate stage took 14 to 19 seconds a build on 9 November. On
a copy of the same files here, 2.2 of its 5.1 seconds were the carry's
positional means: last season's whole regular season filtered, each row's
position and name read, once for every one of fourteen markets, for a
season that does not change. And last season's file was parsed twice, once
for the defences' prior and again for the carry. What these hold:

  * every market's means from the one walk are the floats each market's
    own walk gives, in the same order, whatever the rows hold (the
    postseason, a man short of the floor, a row with no name or position);
  * build_slate asks for last season once, and builds the slate it built
    when it asked twice;
  * the defences' prior reads last season's rows and writes none, which is
    what lets the carry take the same parse.

Run directly: `python3 tests/test_the_nfl_slate_reads_last_season_once.py`
"""
import copy
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import carry                                            # noqa: E402
from engine.sources import nflverse as nv                           # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE")


def _season(seed=4, season=2025):
    rnd = random.Random(seed)
    rows = []
    for k in range(60):
        pos = POSITIONS[k % 4]
        name = f"Player {k}"
        weeks = range(1, 18) if k % 7 else range(1, 4)        # some fall short of the floor
        for wk in weeks:
            rows.append({"season": str(season), "week": str(wk),
                         "season_type": "REG" if wk < 17 or k % 2 else "POST",
                         "player_display_name": name, "position": pos, "position_group": pos,
                         "recent_team": "MIA" if k % 2 else "BUF", "opponent_team": "NYJ",
                         "passing_yards": str(rnd.uniform(150, 330)) if pos == "QB" else "0",
                         "attempts": str(rnd.randint(20, 45)) if pos == "QB" else "0",
                         "completions": str(rnd.randint(12, 30)) if pos == "QB" else "0",
                         "rushing_yards": str(rnd.uniform(0, 120)),
                         "carries": str(rnd.randint(0, 22)),
                         "receiving_yards": str(rnd.uniform(0, 140)) if pos != "QB" else "0",
                         "receptions": str(rnd.randint(0, 11)) if pos != "QB" else "0",
                         "targets": str(rnd.randint(0, 14)) if pos != "QB" else "0",
                         "passing_tds": str(rnd.randint(0, 4)) if pos == "QB" else "0",
                         "interceptions": str(rnd.randint(0, 2)) if pos == "QB" else "0"})
    rows.append({"season": str(season), "week": "3", "season_type": "REG", "player_display_name": "",
                 "position": "WR", "receiving_yards": "999"})          # no name: counted nowhere
    rows.append({"season": str(season), "week": "3", "season_type": "REG",
                 "player_display_name": "Nobody", "position": "", "receiving_yards": "999"})
    return rows


def test_every_markets_means_in_one_walk_are_each_markets_own():
    for seed in (4, 9):
        rows = _season(seed)
        one = carry.positional_means_all(rows, nv.STAT_MARKETS)
        for market in nv.STAT_MARKETS:
            own = carry.positional_means(rows, market)
            assert list(one[market].items()) == list(own.items()), market
        assert set(one) == set(nv.STAT_MARKETS)
    assert carry.positional_means_all([], nv.STAT_MARKETS) == {m: {} for m in nv.STAT_MARKETS}


def _stubbed(current, prior, week=5, season=2026, copies=False):
    """build_slate with every feed replaced; ``copies`` hands each read of
    last season its own parse, as the build did before."""
    from engine.models import Game, Weather
    games = [Game(home="MIA", away="BUF", weather=Weather(dome=True), injuries=[],
                  date="2026-10-04", kickoff="13:00", spread=-3.0, total=44.5)]
    saved = {n: getattr(nv, n) for n in ("build_games", "load_weekly_stats", "roster_index",
                                        "roster_teams", "load_schedules")}
    asked = []

    def _stats(s):
        asked.append(s)
        rows = current if s == season else prior
        return copy.deepcopy(rows) if copies else rows

    nv.build_games = lambda s, w: games
    nv.load_weekly_stats = _stats
    named = [r for r in prior if r.get("player_display_name") and r.get("recent_team")]
    nv.roster_index = lambda s: {r["player_display_name"]: {"team": r["recent_team"], "position": r["position"]}
                                 for r in named}
    nv.roster_teams = lambda s: {r["player_display_name"]: r["recent_team"] for r in named}
    nv.load_schedules = lambda: []
    try:
        report = {}
        slate = nv.build_slate(season, week, carry=True, report=report)
        return slate, report, asked
    finally:
        for n, fn in saved.items():
            setattr(nv, n, fn)


def _props(slate):
    return [sorted((k, repr(v)) for k, v in vars(p).items()) for p in slate.props]


def test_last_season_is_asked_for_once_and_the_slate_is_the_one_two_reads_built():
    prior = _season(4)
    current = [dict(r, season="2026") for r in _season(11, 2026) if int(r["week"]) < 5]
    slate, report, asked = _stubbed(current, prior)
    assert asked.count(2025) == 1 and asked.count(2026) == 1, asked
    again, report_again, asked_again = _stubbed(current, prior, copies=True)
    assert slate.props and _props(slate) == _props(again)
    assert report == report_again


def test_the_defences_prior_writes_no_row():
    prior, current = _season(4), [dict(r, season="2026") for r in _season(11, 2026)]
    before = copy.deepcopy(prior)
    for week in (1, 5, 12):
        nv.build_defense_profiles(current, week, prior)
    assert prior == before


def test_the_build_reads_last_season_from_the_defences_parse():
    import inspect
    src = inspect.getsource(nv.build_slate)
    assert "prior_stats = last_season if last_season is not None else load_weekly_stats(season - 1)" in src
    assert "positional_means_all(prior_stats, STAT_MARKETS)" in src
    assert "_carry.positional_means(prior_stats" not in src


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
