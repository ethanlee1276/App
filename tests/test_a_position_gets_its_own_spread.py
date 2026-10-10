"""How wide a player's outcomes really are, by position (engine/posspread).

The 2026-10-04 NFL record: tight ends over-claimed on BOTH sides (overs 47%
where we said 64%, unders 41% where we said 65%) — too sure, not leaning
the wrong way. Checks, one rule each: a width that predicts held-out
seasons better is adopted and one that does not is left at 1.0; the
projection widens the spread by it for that position only, in the NFL
only, and says so; the weekly deep-fit job runs it.

Run directly: `python3 tests/test_a_position_gets_its_own_spread.py`
"""
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()

from engine import posspread as P                                   # noqa: E402


def _data(true_mult: float, seasons=(2021, 2022, 2023, 2024, 2025), per=900, seed=3):
    """Rows priced at sd=10 whose outcomes really spread true_mult × 10."""
    rng = random.Random(seed)
    out = []
    for s in seasons:
        for _ in range(per):
            mu = rng.uniform(30, 60)
            actual = rng.gauss(mu, 10 * true_mult)
            for line in (25.5, 40.5, 60.5):
                if P.NEAR_LO * mu <= line <= P.NEAR_HI * mu:
                    out.append((s, 10.0, mu, line, actual > line))
    return out


def test_a_width_that_predicts_held_out_seasons_is_adopted_and_noise_is_not():
    too_sure = P.judge(_data(1.35))
    assert too_sure["passed"] and 1.25 <= too_sure["m"] <= 1.45, too_sure
    assert too_sure["better"] >= P.MIN_SEASONS_BETTER
    honest = P.judge(_data(1.0))
    assert not honest["passed"], "an honest width stays at 1.0"
    small = P.judge(_data(1.35, per=40))
    assert not small["passed"], "too few rows prove nothing"


def test_the_projection_widens_that_position_only_and_says_so():
    path = Path(os.environ["QB_MODELS_DIR"]) / "position_spread.json"
    P.save({"TE|receptions": {"m": 1.3, "n": 9000, "gain": 0.01, "passed": True},
            "WR|receptions": {"m": 0.9, "n": 9000, "gain": -0.01, "passed": False}}, path)
    assert P.width_mult("TE", "receptions") == 1.3
    assert P.width_mult("WR", "receptions") == 1.0, "a width that did not pass is not used"
    assert P.width_mult("te", "rec_yds") == 1.0
    # The first (far-tail) version's store carries no version: never read.
    path.write_text('{"widths": {"TE|receptions": {"m": 1.35}}}', encoding="utf-8")
    import time
    time.sleep(0.01)
    os.utime(path, None)
    assert P.width_mult("TE", "receptions") == 1.0, "a store from the far-tail version is ignored"
    src = open(os.path.join(ROOT, "engine", "projection.py"), encoding="utf-8").read()
    i = src.index("from .posspread import width_mult")
    # Each league reads only widths measured on its own games (college
    # joined 2026-10-09 with its own store; was NFL-only).
    assert 'if sport in ("nfl", "cfb"):' in src[i - 200:i]
    assert "width_mult(prop.position, prop.market, sport)" in src[i:i + 120], \
        "a league must read its own store, never another league's"
    assert "adj_std *= _w" in src[i:i + 300] and "Spread:" in src[i:i + 500]


def test_college_reads_its_own_widths_and_never_the_nfls():
    nfl = Path(os.environ["QB_MODELS_DIR"]) / "position_spread.json"
    cfb = Path(os.environ["QB_MODELS_DIR"]) / "cfb_position_spread.json"
    assert P._store("cfb").name == cfb.name and P._store("nfl").name == nfl.name
    P.save({"TE|receptions": {"m": 1.3, "n": 9000, "gain": 0.01, "passed": True}}, nfl)
    P.save({"RB|rush_yds": {"m": 1.2, "n": 9000, "gain": 0.01, "passed": True}}, cfb)
    assert P.width_mult("TE", "receptions", "cfb") == 1.0, "an NFL width never reaches a college prop"
    assert P.width_mult("RB", "rush_yds", "cfb") == 1.2
    assert P.width_mult("RB", "rush_yds", "nfl") == 1.0, "a college width never reaches an NFL prop"
    assert P.width_mult("TE", "receptions", "nba") == 1.0, "a league with no fit reads 1.0"
    rep = {"cfb": {"slices": {"position": [{"key": "RB · over", "n": 40, "hit": 0.70, "said": 0.64}]}}}
    assert P.record_veto("RB", rep, "cfb") and not P.record_veto("RB", rep, "nfl"), \
        "college's own record vetoes college's widths"


def test_the_record_vetoes_widening_a_position_it_shows_is_not_over_sure():
    rep = {"nfl": {"slices": {"position": [
        {"key": "WR · over", "n": 94, "hit": 0.67, "said": 0.63},
        {"key": "WR · under", "n": 28, "hit": 0.43, "said": 0.68},
        {"key": "TE · over", "n": 53, "hit": 0.47, "said": 0.64},
        {"key": "RB · under", "n": 15, "hit": 0.70, "said": 0.63}]}}}
    res = {"WR|rec_yds": {"m": 1.5, "passed": True}, "TE|rec_yds": {"m": 1.4, "passed": True},
           "RB|rush_yds": {"m": 1.45, "passed": True}, "RB|rec_yds": {"m": 1.0, "passed": False}}
    P.apply_vetoes(res, rep)
    assert res["WR|rec_yds"]["passed"] is False and "67%" in res["WR|rec_yds"]["veto"]
    assert res["TE|rec_yds"]["passed"] is True, "tight ends over-claim: history's width stands"
    assert res["RB|rush_yds"]["passed"] is True, "fifteen picks are too few to veto"
    assert "veto" not in res["RB|rec_yds"]


def test_only_lines_near_his_projection_are_scored():
    rows = [{"season": 2025, "mu": 40.0, "form_sd": 12.0, "actual": 50.0}]
    lines = sorted(line for _s, _sd, _mu, line, _h in P.samples(rows, "rec_yds"))
    assert lines == [40.5], "15.5, 25.5 and 60.5 are far tails a book would not hang for a 40-yard man"


def test_it_reads_the_history_database_by_position():
    from engine import db
    hist = db.connect(Path(tempfile.mkdtemp()) / "history.db")
    logs = [{"sport": "nfl", "season": 2025, "period": f"{w:03d}", "game_id": f"LV-{w:03d}", "player": "Tight End",
             "team": "LV", "opponent": "KC", "position": "TE", "home": 0, "market": "receptions",
             "value": float(2 + w % 4)} for w in range(1, 12)]
    db.upsert_player_logs(hist, logs)
    hist.commit()
    res = P.measure(hist)
    assert set(res) == {"TE|receptions"} and res["TE|receptions"]["passed"] is False, res


def test_the_current_season_counts_from_its_second_week():
    from engine import db
    hist = db.connect(Path(tempfile.mkdtemp()) / "history.db")
    logs = [{"sport": "nfl", "season": season, "period": f"{w:03d}", "game_id": f"LV-{w:03d}",
             "player": "Tight End", "team": "LV", "opponent": "KC", "position": "TE", "home": 0,
             "market": "receptions", "value": float(2 + w % 4)}
            for season, weeks in ((2025, range(12, 18)), (2026, range(1, 5))) for w in weeks]
    db.upsert_player_logs(hist, logs)
    hist.commit()
    rows = P.carried_rows(hist, "receptions")
    assert sorted({r["season"] for r in rows}) == [2025, 2026]
    assert sum(1 for r in rows if r["season"] == 2026) == 4, "every 2026 week, carried from 2025"


def test_the_weekly_job_runs_it():
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    body = src[src.index("def _run_deep_refit("):src.index("def _run_lab(")]
    assert '_spawn_module("engine.posspread", log)' in body


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
