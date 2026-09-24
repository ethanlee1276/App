"""The matchup scan ranks each side's units, opponent-adjusted and blended.

Ethan, 2026-09-24: "ranking the defenses and offenses and looking at
where exactly in the defense and offense is good and bad". engine/
sources/nflunits folds the play-by-play into per team-week sums (overall,
passing, rushing, success, explosive, pressure, yards per carry);
engine/gamescan divides them, moves each game by its opponent's season,
blends with last season by games played, and ranks 1 = best.
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, gamescan as G                          # noqa: E402
from engine.sources import nflunits as U                       # noqa: E402


def _play(off, dfn, wk=1, kind="pass", epa=0.1, succ=1, yds=5, sack=0, hit=0, season_type="REG"):
    return {"week": str(wk), "season_type": season_type, "posteam": off, "defteam": dfn,
            "qb_dropback": "1" if kind == "pass" else "0", "rush": "1" if kind == "run" else "0",
            "epa": str(epa), "success": str(succ), "yards_gained": str(yds),
            "sack": str(sack), "qb_hit": str(hit), "two_point_attempt": "0"}


def test_plays_fold_into_both_sides_of_the_ball():
    rows = U.unit_week_rows([
        _play("ATL", "GB", kind="pass", epa=0.5, yds=25),
        _play("ATL", "GB", kind="pass", epa=-1.2, succ=0, yds=-7, sack=1),
        _play("ATL", "GB", kind="run", epa=0.2, yds=12),
        _play("GB", "ATL", kind="run", epa=-0.3, succ=0, yds=1, hit=1),
        _play("ATL", "GB", kind="pass", season_type="PRE"),          # preseason: out
    ], 2026)
    by = {(r["team"], r["side"]): r for r in rows}
    atl = by[("ATL", "off")]
    assert (atl["plays"], atl["dropbacks"], atl["rushes"]) == (3, 2, 1)
    assert (atl["pass_expl"], atl["rush_expl"], atl["sacks"]) == (1, 1, 1)
    assert by[("GB", "def")]["plays"] == 3 and by[("GB", "def")]["sacks"] == 1, "the defence's mirror"
    assert atl["opp"] == "GB" and by[("GB", "off")]["opp"] == "ATL"
    assert by[("GB", "off")]["hits"] == 0, "a hit on a run is not a pass-rush hit"


def _week(team, opp, wk, off_epa, def_epa, plays=60):
    base = {"sport": "nfl", "season": 2026, "period": f"{wk:03d}", "dropbacks": plays // 2,
            "rushes": plays // 2, "pass_expl": 3, "rush_expl": 2, "sacks": 2, "hits": 4,
            "rush_yds": 4.3 * (plays // 2)}
    off = dict(base, team=team, side="off", opp=opp, plays=plays, epa=off_epa * plays,
               success=0.45 * plays, pass_epa=off_epa * plays / 2, pass_success=0.2 * plays,
               rush_epa=off_epa * plays / 2, rush_success=0.2 * plays)
    dfn = dict(base, team=team, side="def", opp=opp, plays=plays, epa=def_epa * plays,
               success=0.45 * plays, pass_epa=def_epa * plays / 2, pass_success=0.2 * plays,
               rush_epa=def_epa * plays / 2, rush_success=0.2 * plays)
    return [off, dfn]


def test_an_offence_that_faced_good_defences_is_credited_for_it():
    # A and B both gain 0.00 EPA per play; A did it against C (a defence
    # allowing -0.20), B against D (allowing +0.20). A is the better offence.
    rows = (_week("A", "C", 1, 0.0, 0.0) + _week("C", "A", 1, 0.0, -0.20)
            + _week("B", "D", 1, 0.0, 0.0) + _week("D", "B", 1, 0.0, 0.20))
    r = G.ratings_from_rows(rows)
    assert r["A"]["off"]["overall"]["value"] > r["B"]["off"]["overall"]["value"]
    assert r["A"]["off"]["overall"]["rank"] < r["B"]["off"]["overall"]["rank"]


def test_two_games_lean_on_last_season_and_a_full_one_does_not():
    cur = _week("A", "B", 1, 0.30, 0.0) + _week("B", "A", 1, 0.0, 0.0)
    prior = [dict(r, season=2025) for r in (_week("A", "B", 1, -0.30, 0.0) + _week("B", "A", 1, 0.0, 0.0))]
    one = G.ratings_from_rows(cur, prior)
    assert one["A"]["blend"] == round(1 / (1 + G.PRIOR_GAMES), 2)
    assert one["A"]["off"]["overall"]["value"] < 0.30 * 0.5, "one game is mostly last season"
    many = []
    for wk in range(1, 17):
        many += _week("A", "B", wk, 0.30, 0.0) + _week("B", "A", wk, 0.0, 0.0)
    full = G.ratings_from_rows(many, prior)
    assert full["A"]["blend"] >= 0.79


def test_ranks_run_one_best_on_each_side():
    rows = (_week("A", "B", 1, 0.25, -0.10, plays=60) + _week("B", "A", 1, -0.10, 0.25, plays=60))
    r = G.ratings_from_rows(rows)
    assert r["A"]["off"]["overall"]["rank"] == 1 and r["B"]["off"]["overall"]["rank"] == 2
    assert r["A"]["def"]["overall"]["rank"] == 1, "the defence allowing less is first"


def test_the_ingest_and_the_tuesday_refresh_store_the_units():
    ing = open(os.path.join(ROOT, "engine", "ingest.py"), encoding="utf-8").read()
    mnt = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    for src in (ing, mnt):
        assert "load_pbp_rows(season, columns=UNIT_COLS)" in src and "also=units.add" in src
        assert "upsert_team_units(" in src
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    db.upsert_team_units(conn, _week("A", "B", 1, 0.1, 0.0) + _week("B", "A", 1, 0.0, 0.1)
                         + _week("A", "B", 3, 0.9, 0.0) + _week("B", "A", 3, 0.0, 0.9))
    got = G.unit_ratings(conn, 2026, before_week=3)
    assert got["A"]["games"] == 1, "only the weeks before the game"


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
