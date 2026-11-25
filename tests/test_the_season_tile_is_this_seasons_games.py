"""The Season tile is this season's games, in every league (step AFI, 25 November 2026).

The tiles over a priced market card read L1, L3, L5, L10 and Season, and Season was the mean of every game the build
read, whatever season it was from: basketball reads a player's last twenty games across two seasons, so in late
November most cards' Season held last April's games; the NFL's and college football's held the games carried in from
last season early in the year; baseball's and hockey's every game on the log. A history card's Season tile has said
only this season's games since step AFD. Now every build's does:

  * NFL and college football: the games not carried in from last season (`prior`);
  * NBA, WNBA and college basketball: the games whose dates fall in the season being played
    (engine/nba/pipeline.this_season);
  * hockey: the same, by each game's date; baseball: the games of this year;
  * and hockey's L3, L5 and L10 are each the average of the games it has, as every other league's are, where they
    were blank under three, five or ten games.

Offline. Run directly: `python3 tests/test_the_season_tile_is_this_seasons_games.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_basketball_reads_the_season_being_played():
    from engine.nba.pipeline import this_season
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    dates = ["2026-11-20", "2026-11-18", "2026-10-25", "2026-04-12", "2026-04-10", ""]
    assert this_season("nba", vals, dates, today="2026-11-25") == [1.0, 2.0, 3.0]
    assert this_season("cbb", vals, dates, today="2026-11-25") == [1.0, 2.0], "college's season opens in November"
    assert this_season("nba", vals, dates[:2], today="2026-11-25") == [1.0, 2.0], "a value with no date is no season's"
    assert this_season("nba", [], [], today="2026-11-25") == []
    src = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    assert "this_season(tune.key, vals, dates)" in src


def test_basketballs_tile_reads_the_whole_season_not_the_twenty():
    import nba_build as B
    by_week = {}
    for i in range(25):                      # this season: 25 games, more than the twenty the model reads
        by_week[f"2026-{10 + i // 20:02d}-{1 + i % 20:02d}"] = {"pts": 20.0 + (i % 5), "reb": 5.0, "ast": 4.0,
                                                               **({"stl": 1.0} if i < 10 else {})}
    for i in range(5):                       # last season's spring
        by_week[f"2026-04-{1 + i:02d}"] = {"pts": 40.0, "reb": 10.0, "ast": 10.0, "stl": 3.0}
    got = B.season_means("nba", by_week, 2026)
    assert got["pts"] == 22.0 and got["reb"] == 5.0 and got["pra"] == 31.0 and got["pts_reb"] == 27.0
    assert got["stl"] == 1.0, "a count over the games whose box stored it, never a missing row as a zero"
    assert B.season_means("nba", by_week, None) == {} and B.season_means("nba", {}, 2026) == {}
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert '"season_mean": (h.get("season_means") or {}).get(prop.market),' in src
    assert 'p["season_means"] = season_means(sport, p["by_week"], max(seasons) if seasons else None)' in src
    pipe = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    assert ('"season": (prop["season_mean"] if prop.get("season_mean") is not None\n'
            '                                else _avg(this_season(tune.key, vals, dates))),') in pipe


def test_football_leaves_the_carried_games_out():
    src = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
    assert '"season": _avg([g.value for g in prop.logs if not getattr(g, "prior", False)]),' in src
    assert '"last10": _avg(vals[:10]),' in src, "the windows still read every game, carried ones too"


def test_hockey_reads_its_dates_and_its_windows_read_what_they_have():
    import nhl_build as N
    assert N._in_season("2026-10-15", "2026-11-25") and not N._in_season("2026-04-10", "2026-11-25")
    assert not N._in_season("", "2026-11-25") and not N._in_season(None, "2026-11-25")
    assert N._mean([]) is None and N._mean([1.0, 2.0]) == 1.5
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    assert '"last3": _mean(vals[:3]), "last5": _mean(vals[:5]), "last10": _mean(vals[:10]),' in src
    assert "for g in games if _in_season(g.get(\"date\"), date)]" in src
    assert "if len(vals) >= 5 else None" not in src, "a window blank under five games, as no other league's is"


def test_baseball_reads_this_year():
    src = (ROOT / "engine" / "mlb" / "pipeline.py").read_text(encoding="utf-8")
    assert 'if str(getattr(g, "date", "") or "")[:4] == _this_year()]),' in src
    from engine.mlb import pipeline as P
    import datetime
    assert P._this_year() == str(datetime.date.today().year)


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
