"""A league whose results have moved is not a day behind them (launch._run_futures,
FUTURES_AFTER_FINALS_MIN), FRESH1.

Ethan, 2026-11-17: "make sure we're getting the most up-to-date information
that's updating consistently on the website". Every public feed was read on
the live site that day: the boards, the injuries, the news, the rosters and
the standings were minutes old, the scoreboards seconds. The season
projections were the one feed that was not: rebuilt once a day, whenever
the last rebuild happened to fall, so the NBA's and the NHL's playoff
brackets read up to a day behind the standings page beside them. What these
hold:

  * between the daily rebuilds, a league whose count of finals has changed
    since its own last build is built again, and only that league;
  * one league a pass, and no league more often than
    FUTURES_AFTER_FINALS_MIN, so a night of finals is a handful of builds;
  * a league whose results have not moved is left to the daily rebuild, and
    the daily rebuild still builds every league and still throttles to a day;
  * a build that fails is tried again; an unreadable count never loops.

    python3 tests/test_a_league_whose_results_moved_is_rebuilt.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import futures_build                                                # noqa: E402
import launch                                                       # noqa: E402
from engine import db                                               # noqa: E402


class _World:
    """launch._run_futures on a box of its own: two leagues, a history whose finals the test moves."""

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "web" / "data").mkdir(parents=True)
        self.built, self.finals, self.fail = [], {"nba": 200, "nhl": 300}, set()
        self.real = (launch.ROOT, futures_build.build, futures_build.SPORTS, futures_build.publish,
                     launch._futures_finals, db.connect)
        launch.ROOT = self.dir

        def build(sport, conn, **kw):
            assert kw.get("live_odds") is False, "a rebuild never reaches the meter"
            if sport in self.fail:
                raise RuntimeError("no schedule")
            self.built.append(sport)
            return {"sport": sport, "teams": []}
        futures_build.build = build
        futures_build.SPORTS = ("nba", "nhl")
        futures_build.publish = lambda sport, data, conn: ""
        launch._futures_finals = lambda conn, sport: self.finals[sport]
        db.connect = lambda *a, **k: self.real[5](":memory:")
        return self

    def __exit__(self, *exc):
        (launch.ROOT, futures_build.build, futures_build.SPORTS, futures_build.publish,
         launch._futures_finals, db.connect) = self.real

    def run(self):
        del self.built[:]
        launch._run_futures(quiet=True)
        return list(self.built)

    def age(self, sport, minutes):
        """As if the league's last build were this long ago."""
        path = self.dir / "data" / "futures_finals.json"
        seen = json.loads(path.read_text(encoding="utf-8"))
        seen[sport]["at"] = time.time() - minutes * 60
        path.write_text(json.dumps(seen), encoding="utf-8")


def test_a_league_whose_finals_moved_is_rebuilt_and_only_that_league():
    with _World() as w:
        assert w.run() == ["nba", "nhl"], "the daily rebuild: every league"
        stamp = w.dir / "web" / "data" / ".futures_built"
        first = stamp.read_text(encoding="utf-8")
        assert first.endswith(launch.FUTURES_VERSION)
        assert w.run() == [], "nothing has moved"
        w.finals["nba"] += 3                                  # the night's finals
        assert w.run() == [], "built minutes ago: not again yet"
        w.age("nba", launch.FUTURES_AFTER_FINALS_MIN + 1)
        assert w.run() == ["nba"], "its results moved: its projection and bracket follow"
        assert w.run() == [], "and once"
        assert stamp.read_text(encoding="utf-8") == first, "the daily rebuild's own clock is not reset"


def test_one_league_a_pass_and_no_league_more_often_than_the_gap():
    with _World() as w:
        w.run()
        w.finals["nba"] += 1
        w.finals["nhl"] += 2
        w.age("nba", 60)
        w.age("nhl", 60)
        assert w.run() == ["nba"] and w.run() == ["nhl"] and w.run() == [], "one a pass"
        # More finals within the gap wait for it: a night is a handful of builds, never one a final.
        for _ in range(4):
            w.finals["nba"] += 1
            assert w.run() == []
        w.age("nba", launch.FUTURES_AFTER_FINALS_MIN)
        assert w.run() == ["nba"]
        assert 20 <= launch.FUTURES_AFTER_FINALS_MIN <= 120


def test_a_failed_build_is_tried_again_and_an_unreadable_count_never_loops():
    with _World() as w:
        w.run()
        w.finals["nhl"] += 1
        w.age("nhl", 60)
        w.fail.add("nhl")
        assert w.run() == [] and w.run() == [], "nothing built"
        w.fail.clear()
        assert w.run() == ["nhl"], "tried again once it can be built"
        # A history that cannot be counted says -1 every time: one build, not one a pass.
        w.finals["nba"] = -1
        w.age("nba", 60)
        assert w.run() == ["nba"] and w.run() == []
    conn = db.connect(":memory:")
    assert launch._futures_finals(conn, "nba") == 0
    assert launch._futures_finals(None, "nba") == -1


def test_the_daily_rebuild_still_builds_every_league_and_throttles_to_a_day():
    with _World() as w:
        w.run()
        stamp = w.dir / "web" / "data" / ".futures_built"
        old = time.time() - (launch.FUTURES_EVERY_HOURS * 3600 + 60)
        os.utime(stamp, (old, old))
        assert w.run() == ["nba", "nhl"] and w.run() == []
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    block = src[src.index("def _run_futures("):src.index("\ndef ", src.index("def _run_futures(") + 1)]
    assert "live_odds=False" in block and "futures_build.publish(sport, data, conn)" in block
    assert "][:1]" in block, "one league a pass"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
