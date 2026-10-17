"""The minutes a regular's absence opens — held out before the board gives them to anyone.

Box run, 2026-10-17 (nbavacancy.py, section O): when a regular sits, his
teammates ran +1.8 minutes and +1.1 points above the board's number in both
seasons stored — the bar set before that run, MET, which earned a held-out
test. What these hold: the rule shares k × the absent minutes over the
rotation by each man's base minutes; the slot stays empty (k 0) until a
saved verdict holds; the projection takes the vacancy through the minutes
model, caps and all, and is unchanged without one; the held-out test fits k
on the other seasons and holds only where minutes AND points improve in
every held-out season — it finds the share a synthetic league was built
with, and refuses a league where absences open nothing; and the build gives
the vacancy to the rotation, never to the man who is out or ruled out, and
the teammate card says what moved. No test touches the network.

Run directly: `python3 tests/test_nba_vacancy_held_out.py`
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nba_build                                                  # noqa: E402
import nbavacancy as NV                                           # noqa: E402
from engine.nba import pipeline as P                              # noqa: E402
from engine.nba import vacancy as V                               # noqa: E402


class _Models:
    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.environ.get("QB_MODELS_DIR")
        os.environ["QB_MODELS_DIR"] = self.dir
        return self

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = self.old
        shutil.rmtree(self.dir)


def test_the_vacated_minutes_are_shared_by_each_mans_own_minutes():
    got = V.shares(30.0, {"Wing": 30.0, "Big": 20.0, "Bench": 0.0}, 0.5)
    assert got == {"Wing": 9.0, "Big": 6.0}, got
    assert V.shares(30.0, {"Wing": 30.0}, 0.0) == {} and V.shares(0.0, {"Wing": 30.0}, 0.5) == {}


def test_the_slot_stays_empty_until_a_saved_verdict_holds():
    with _Models() as m:
        assert V.k_for("nba") == 0.0, "no verdict: the empty slot, as before"
        V.save("nba", {"holds": False, "k": 0.6})
        assert V.k_for("nba") == 0.0
        V.save("nba", {"holds": True, "k": 0.6})
        assert V.k_for("nba") == 0.6
        assert json.load(open(os.path.join(m.dir, V.STORE)))["nba"]["k"] == 0.6
        assert V.k_for("wnba") == 0.0, "each league earns its own"


def test_the_projection_takes_the_vacancy_through_the_minutes_model():
    prop = {"player": "Wing", "market": "pts", "minutes": [30.0] * 10, "values": [18.0] * 10,
            "spread": 0.0, "is_starter": True, "is_favorite": False, "rest": "1day", "player_mult": 1.0}
    flat = P.project(prop)
    more = P.project(dict(prop, vacancy_minutes=4.0))
    assert more["proj_min"] > flat["proj_min"]
    assert abs(more["projection"] / flat["projection"] - more["proj_min"] / flat["proj_min"]) < 0.01
    assert P.project(dict(prop, vacancy_minutes=0.0))["projection"] == flat["projection"]
    capped = P.project(dict(prop, vacancy_minutes=40.0))
    assert capped["proj_min"] <= 30.0 + 8.0 + 0.05, "never past his recent high plus the cap"


def _league(share: float) -> dict:
    """Two seasons of one club: the star sits every fifth game (fresh — he
    played the game before), and his teammates take ``share`` of his 34
    minutes by their own minutes, at 0.6 points a minute."""
    clubs = {}
    base = {"Wing": 30.0, "Big": 26.0, "Guard": 24.0, "Sixth": 20.0}
    tot = sum(base.values())
    for season in (2024, 2025):
        games = {}
        for i in range(60):
            d = f"{season}-{1 + i // 28:02d}-{1 + i % 28:02d}"
            sits = i >= 10 and i % 5 == 4
            g = {} if sits else {"Star": {"min": 34.0, "pts": 24.0, "starter": True}}
            for name, mins in base.items():
                m = mins + (share * 34.0 * mins / tot if sits else 0.0) + ((i * 7 + len(name)) % 3 - 1) * 0.5
                g[name] = {"min": m, "pts": 0.6 * m, "starter": name != "Sixth"}
            games[d] = g
        clubs[(season, "BOS")] = games
    return clubs


def test_the_held_out_test_finds_the_share_and_holds_only_when_it_helps():
    rows = NV.cases(_league(0.6), "nba")
    games: dict = {}
    for r in rows:
        games.setdefault((r["team"], r["date"]), []).append(r)
    assert len(games) >= 16, "ten fresh absences a season, after the first ten games"
    assert all(abs(sum(r["share"] for r in g) - 1.0) < 1e-9 for g in games.values()), \
        "each absence's minutes are shared over the men who played, all of them"
    assert all(abs(g[0]["absent"] - 34.0) < 1e-6 for g in games.values())
    res = NV.heldout(rows, "nba")
    assert res["holds"], res
    assert 0.35 <= res["k"] <= 0.85, res["k"]
    assert set(res["by_season"]) == {"2024", "2025"}, "each season held out in turn"
    assert all(v["minutes_gain"] > 0 and v["points_gain"] > 0 for v in res["by_season"].values())
    none = NV.heldout(NV.cases(_league(0.0), "nba"), "nba")
    assert not none["holds"], "absences that open nothing must not move a number"
    lines = NV.heldout_report(res, "nba")
    assert any("HOLDS" in x for x in lines) and any("2024 held out" in x for x in lines)


def _team_hist():
    dates = [f"2026-02-{d:02d}" for d in range(10, 20)]
    hist = {}

    def add(name, mins, team="BOS"):
        by = {d: {"min": mins} for d in dates}
        hist[name] = {"team": team, "starter": True, "by_week": by, "minutes": [mins] * 10}
    add("Star", 34.0)
    add("Wing", 30.0)
    add("Big", 20.0)
    add("Hurt", 25.0)
    add("Other", 30.0, team="MIA")
    return hist


def test_the_build_gives_the_vacancy_to_the_rotation_and_no_one_else():
    hist = _team_hist()
    injuries = {"star": {"player": "Star", "status": "Out"}, "hurt": {"player": "Hurt", "status": "Out"}}
    gone = nba_build.absences(hist, injuries)
    listed = {"Star": injuries["star"], "Hurt": injuries["hurt"]}
    cache = {}
    wing = nba_build.vacancy_for("Wing", "BOS", gone, hist, listed, 0.6, cache=cache)
    big = nba_build.vacancy_for("Big", "BOS", gone, hist, listed, 0.6, cache=cache)
    assert wing > big > 0 and abs(wing / big - 1.5) < 0.05, (wing, big)
    assert abs(wing + big - 0.6 * (34.0 + 25.0)) < 0.05, "all of k × the vacated minutes, no more"
    assert nba_build.vacancy_for("Star", "BOS", gone, hist, listed, 0.6, cache=cache) == 0.0
    assert nba_build.vacancy_for("Hurt", "BOS", gone, hist, listed, 0.6, cache=cache) == 0.0
    assert nba_build.vacancy_for("Other", "MIA", gone, hist, listed, 0.6) == 0.0, "nobody out in Miami"
    assert nba_build.vacancy_for("Wing", "BOS", gone, hist, listed, 0.0) == 0.0, "no verdict, no vacancy"
    src = (ROOT / "nba_build.py").read_text()
    assert '"vacancy_minutes": _vac_min' in src and "_vac.k_for(args.league)" in src
    assert "our minutes model gives him" in src, "the teammate card says what moved"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
