"""A playoff race is played out again only when something it is built from
has moved (engine/racecache; nflrace.publish, cfprace.publish,
nbacup.publish).

The NFL playoff race plays the rest of the season out 10,000 times, the
college race 6,000, the NBA Cup 10,000, and each ran on every board build
though between two builds nothing it reads had usually changed. The NFL
build ran 577 of its 600-second limit on 8 November with its race inside
it. What these hold:

  * a race writes the fingerprint of its inputs beside its numbers, and the
    next build off the same inputs keeps it — no seasons played, the file
    and its "Built" time untouched, a line in the log saying so;
  * a new score, a game moved, a rating, the next day, or a file that will
    not read, and the race is played out again;
  * the fingerprint does not care about the order a dict was built in,
    does care about every value, and carries the race module's own code;
  * the college race and the NBA Cup ask the same question of their own
    inputs (the poll and the selection too, for college).

Run directly: `python3 tests/test_a_race_is_played_again_only_when_its_inputs_move.py`
"""
import datetime as dt
import inspect
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import cfprace, futuresdata, nbacup, nflrace, racecache   # noqa: E402
from engine import db as _db                                         # noqa: E402
from engine.sources import nflverse                                  # noqa: E402

TEAMS = [t for t, _c, _d in nflrace.league()]
DAY = dt.date(2026, 11, 8)


def _season(extra_score=False):
    rows = []
    for week in range(1, 9):
        order = TEAMS[week % 32:] + TEAMS[:week % 32]
        for k in range(16):
            h, a = order[k], order[31 - k]
            played = week <= 6 or (extra_score and week == 7 and k == 0)
            rows.append({"season": "2026", "game_type": "REG", "week": str(week),
                         "gameday": f"2026-09-{week + 6:02d}", "home_team": h, "away_team": a,
                         "location": "Home", "home_score": "24" if played else "",
                         "away_score": "17" if played else ""})
    return rows


class _Conn:
    def close(self):
        pass


class _NFL:
    """nflrace.publish with its schedule, ratings and database stubbed, and
    its seasons counted (300 a race, so the test is quick)."""

    def __init__(self, rows=None, ratings=None):
        self.rows = rows if rows is not None else _season()
        self.ratings = ratings if ratings is not None else {t: (i % 7) - 3.0 for i, t in enumerate(TEAMS)}
        self.out = Path(tempfile.mkdtemp()) / "web" / "data" / "nfl_race.json"
        self.calls = 0

    def publish(self, day=DAY):
        keep = (nflverse.load_schedules, futuresdata.blended_ratings, _db.connect, nflrace.build)
        real_build = nflrace.build

        def counted(rows, ratings, today, season=None, **kw):
            self.calls += 1
            return real_build(rows, ratings, today, season=season, sims=300, seed_=7)
        nflverse.load_schedules = lambda *a, **k: self.rows
        futuresdata.blended_ratings = lambda conn, sport, season: (self.ratings, 0.25, 8)
        _db.connect = lambda *a, **k: _Conn()
        nflrace.build = counted
        try:
            return nflrace.publish(day, out_path=str(self.out))
        finally:
            nflverse.load_schedules, futuresdata.blended_ratings, _db.connect, nflrace.build = keep

    def saved(self):
        from engine import gate
        return json.loads(Path(gate.board_source(self.out)).read_text(encoding="utf-8"))


def test_the_same_inputs_keep_the_race_and_its_built_time():
    race = _NFL()
    first = race.publish()
    assert race.calls == 1 and "seasons played out" in first, first
    saved = race.saved()
    assert len(saved["inputs"]) == 40 and saved["generated_at"]
    line = race.publish()
    assert race.calls == 1, "no seasons played: nothing it reads has moved"
    assert "kept" in line and saved["generated_at"][:16].replace("T", " ") in line, line
    assert race.saved() == saved, "the file and its Built time untouched"


def test_a_score_a_rating_or_the_next_day_plays_it_again():
    race = _NFL()
    race.publish()
    race.rows = _season(extra_score=True)
    race.publish()
    assert race.calls == 2, "a game finished"
    race.ratings = dict(race.ratings, BUF=race.ratings["BUF"] + 0.5)
    race.publish()
    assert race.calls == 3, "a rating moved"
    race.publish(DAY + dt.timedelta(days=1))
    assert race.calls == 4, "the next day"
    race.publish(DAY + dt.timedelta(days=1))
    assert race.calls == 4, "and then holds again"
    from engine import gate
    Path(gate.board_source(race.out)).write_text("{ torn", encoding="utf-8")
    race.publish(DAY + dt.timedelta(days=1))
    assert race.calls == 5, "a file that will not read is built again"


def test_the_fingerprint_reads_values_not_order_and_carries_the_code():
    a = racecache.key("nfl", {"BUF": 1.0, "MIA": -1.0}, [{"home": "BUF", "away": "MIA"}])
    b = racecache.key("nfl", {"MIA": -1.0, "BUF": 1.0}, [{"away": "MIA", "home": "BUF"}])
    assert a == b, "a dict's order is not an input"
    assert racecache.key("nfl", {"BUF": 1.0000001, "MIA": -1.0}, [{"home": "BUF", "away": "MIA"}]) != a
    assert racecache.key("cfb", {"BUF": 1.0, "MIA": -1.0}, [{"home": "BUF", "away": "MIA"}]) != a
    src = racecache.source_of(nflrace.__file__)
    assert len(src) == 40 and src != racecache.source_of(cfprace.__file__)
    assert racecache.source_of("/no/such/file.py") == ""
    assert racecache.kept("/no/such/race.json", a) is None


def test_the_cup_keeps_its_race_too_and_college_asks_of_its_own_inputs():
    out = Path(tempfile.mkdtemp()) / "web" / "data" / "nba_cup.json"
    ratings = {"BOS": 4.0, "NYK": 2.0}
    games = []
    calls = []
    keep = (futuresdata.blended_ratings, nbacup.load_window, nbacup.load_knockouts, nbacup.build)
    futuresdata.blended_ratings = lambda conn, sport, season: (ratings, 0.3, 10)
    nbacup.load_window = lambda day: list(games)
    nbacup.load_knockouts = lambda day: []
    nbacup.build = lambda g, r, today, edge, scale: calls.append(today) or {
        "chances": {"BOS": {"cup": 0.3}}, "played": len(g), "games_left": 5, "bracket": {}}
    try:
        day = dt.date(2026, 11, 12)
        nbacup.publish(None, day, out_path=str(out))
        line = nbacup.publish(None, day, out_path=str(out))
        assert len(calls) == 1 and "kept" in line, line
        games.append({"home": "BOS", "away": "NYK", "home_score": 110, "away_score": 99})
        nbacup.publish(None, day, out_path=str(out))
        assert len(calls) == 2, "a Cup game finished"
    finally:
        futuresdata.blended_ratings, nbacup.load_window, nbacup.load_knockouts, nbacup.build = keep
    # The college race: the same question, of the games, the ratings, the
    # poll and the twelve it would select.
    src = inspect.getsource(cfprace.publish)
    assert "racecache.kept(p, inputs)" in src and 'out["inputs"] = inputs' in src
    for part in ("games, ratings", "ranks, poll, teams, twelve", "racecache.source_of(__file__)"):
        assert part in src, part
    assert "gate.publish(out, p, p.name)" in src


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
