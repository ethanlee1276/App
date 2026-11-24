"""The NBA's, the WNBA's and hockey's game pages draw the Team shapes radar, as the NFL's does.

Ethan, 2026-11-23: "We want all the live pages to match each other ... NFL is kind of like the one we want to go off
of." The NFL's game page shows each side's shape — points scored and allowed, the last five margins, home edge and
steadiness as league percentiles off the scores table, this season blended with last (engine/teamshape) — and no other
league's did, though nothing in the radar is football's. The basketball and hockey builders now attach it too. College
basketball's scores mix in schools outside Division I, whose few games would bend every percentile, so it waits. The
note under the radar says goals for hockey and leaves a new starting QB to football.

Offline. Run directly: `python3 tests/test_every_leagues_game_page_draws_team_shapes.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as DB                                        # noqa: E402
from engine import teamshape as TS                                 # noqa: E402

TEAMS = ["BOS", "NYK", "LAL", "GSW", "DEN", "PHX"]


def _league(sport="nba"):
    conn = DB.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    strength = {t: i for i, t in enumerate(TEAMS)}
    rows = []
    for season in (2025, 2026):
        day = dt.date(season, 10, 25)
        n = 0
        for _round in range(6):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1:]:
                    n += 1
                    date = (day + dt.timedelta(days=n)).isoformat()
                    rows.append({"sport": sport, "season": season, "period": date, "date": date,
                                 "game_id": f"{away}@{home}-{n}", "home": home, "away": away,
                                 "home_score": 100 + 3 * strength[home] + (n % 7),
                                 "away_score": 100 + 3 * strength[away] - (n % 5)})
    DB.upsert_games(conn, rows)
    conn.commit()
    return conn


def test_the_radar_is_any_leagues():
    conn = _league("nba")
    shapes = TS.blended_shapes(conn, "nba", 2026)
    assert set(shapes) == set(TEAMS)
    best, worst = shapes["PHX"], shapes["BOS"]
    assert best["pct"]["offense"] > worst["pct"]["offense"]
    assert set(best["pct"]) == {"offense", "defense", "form", "home_edge", "steadiness"}
    assert best["games"] > 0 and "blend" in best


def test_the_basketball_and_hockey_builders_attach_it():
    nba = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    block = nba[nba.index("# TEAM SHAPES, AS THE NFL'S GAME PAGE DRAWS THEM"):nba.index('_clock.mark("scan + team profiles")')]
    assert 'if args.league in ("nba", "wnba"):' in block, "college basketball waits for a Division I filter"
    assert "_tshape.blended_shapes(conn, args.league, _shape_season)" in block
    assert 'out["team_shapes"] = _shapes' in block and 'out["team_shapes_season"] = _shape_season' in block
    nhl = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    block = nhl[nhl.index("# TEAM SHAPES, AS THE NFL'S GAME PAGE DRAWS THEM"):]
    block = block[:block.index("except Exception as _shx:")]
    assert '_tshape.blended_shapes(conn, "nhl", _shape_season)' in block and 'out["team_shapes"] = _shapes' in block


def test_the_note_speaks_each_sport():
    det = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    card = det[det.index("const shapeCard = _sh && _sa ? (() => {"):]
    card = card[:card.index("})() : \"\";")]
    assert 'state.sport === "nfl" || state.sport === "cfb" ? ", faster for a new starting QB" : ""' in card
    assert 'offense is ${state.sport === "nhl" ? "goals" : "points"} scored' in card


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
