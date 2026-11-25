"""College basketball's game reports read the college ratings (step AET, 25 November 2026).

A college game report's "Our team ratings alone" and the slip checker's college model read each team's
average margin with last season's beside it (engine/futuresdata.blended_ratings): not adjusted for who a team
played, the fault engine/cbbratings was built to fix, and never measured. The Race page fits cbbratings
(measured on four seasons: 15,945 games) on every run. What this holds:

  * each fit the race makes is kept, whole, beside the race (engine/ncaarace.keep_ratings), and read back
    only while it is fresh (kept_ratings: 36 hours);
  * the slip checker's college model reads the kept ratings: the rating gap, the measured home court off a
    neutral floor and none on one, a school below Division I at its fixed level, the measured spread; where
    none is kept, or a Division I side has no rating yet, the average margins stand as before;
  * the report's ratings line says which ratings it read and that they were fitted on results, not yet
    measured against the price;
  * the race keeps every fit it makes.

Offline. Run directly: `python3 tests/test_college_reports_read_the_college_ratings.py`
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import cbbratings as CR, gamereport as R, ncaarace as NR, slipgame as SG   # noqa: E402

DAY = dt.date(2026, 11, 25)
RATED = {"DUKE": 18.4, "UNC": 12.1, "MILW": -3.0}


class _Kept:
    """A kept fit in a folder of its own, the slip checker pointed at it."""

    def __init__(self, ratings=RATED, age_s=0.0, prior=True):
        self.ratings, self.age_s, self.prior = ratings, age_s, prior

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / NR.RATINGS_FILE
        NR.keep_ratings(DAY, self.ratings, {"DUKE": 15.0} if self.prior else {}, 1789, path=self.path,
                        now=time.time() - self.age_s)
        self._was = SG._college_kept
        SG._college_kept = lambda: NR.kept_ratings(path=self.path)
        return self

    def __exit__(self, *exc):
        SG._college_kept = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


def test_a_fit_is_kept_whole_and_read_back_while_fresh():
    with _Kept() as k:
        doc = NR.kept_ratings(path=k.path)
        assert doc["ratings"] == RATED and doc["played"] == 1789 and doc["date"] == "2026-11-25"
        assert doc["season"] == 2026 and doc["prior_schools"] == 1
        assert (doc["hca"], doc["sd"]) == (CR.HCA, CR.SD)
        assert not list(k.dir.glob("*.tmp")), "written whole"
        assert NR.kept_ratings(path=k.path, now=time.time() + NR.RATINGS_MAX_AGE_S + 60) is None, "too old"
        k.path.write_text("{not json", encoding="utf-8")
        assert NR.kept_ratings(path=k.path) is None
        k.path.write_text(json.dumps({"at": time.time(), "ratings": {}}), encoding="utf-8")
        assert NR.kept_ratings(path=k.path) is None, "no ratings in it"
        assert NR.kept_ratings(path=k.dir / "none.json") is None


def test_the_slip_model_reads_the_kept_ratings_with_the_home_court():
    with _Kept():
        m = SG.model(None, "cbb", "DUKE", "UNC", {}, today="2026-11-25")
        assert m["ratings"] == "adjusted" and m["kind"] == "normal" and m["margin_sd"] == CR.SD
        assert abs(m["margin"] - (18.4 - 12.1 + CR.HCA)) < 1e-9
        assert abs(m["p_home"] - CR.win_prob(18.4, 12.1, False)) < 1e-12 and m["no_total"] is True
        assert m["inputs"][0].startswith("DUKE +18.4 and UNC +12.1 points better than an average Division I "
                                         "team on a neutral floor, adjusted for every opponent played (1,789 "
                                         "games this season, last season's rating counting as a few games of "
                                         "this one)"), m["inputs"]
        assert m["inputs"][1] == f"the home court {CR.HCA:g} points"
        n = SG.model(None, "cbb", "DUKE", "UNC", {"neutral": True}, today="2026-11-25")
        assert abs(n["margin"] - (18.4 - 12.1)) < 1e-9 and n["inputs"][1] == "a neutral floor — no home court"
        assert abs(n["p_home"] - CR.win_prob(18.4, 12.1, True)) < 1e-12


def test_a_school_below_division_one_plays_at_its_level():
    with _Kept():
        m = SG.model(None, "cbb", "MILW", "espn:2771", {}, today="2026-11-25")
        assert abs(m["margin"] - (-3.0 - CR.NON_DI + CR.HCA)) < 1e-9
        assert "a school below Division I (-23.5)" in m["inputs"][0], m["inputs"]


def test_without_a_kept_fit_or_a_rating_the_average_margins_stand():
    calls = []
    keep = SG._hoops
    SG._hoops = lambda conn, league, season: calls.append(league) or ({"DUKE": 9.0, "OSU": 2.0}, 0.2, 400)
    try:
        with _Kept():
            m = SG.model(None, "cbb", "DUKE", "OSU", {}, today="2026-11-25")
            assert "ratings" not in m and m["kind"] == "logistic" and calls == ["cbb"], "OSU has no rating yet"
        was = SG._college_kept
        SG._college_kept = lambda: None
        try:
            m = SG.model(None, "cbb", "DUKE", "OSU", {}, today="2026-11-25")
            assert "ratings" not in m and calls == ["cbb", "cbb"]
        finally:
            SG._college_kept = was
        with _Kept():
            m = SG.model(None, "nba", "DUKE", "OSU", {}, today="2026-11-25")
            assert "ratings" not in m, "the NBA keeps its own"
    finally:
        SG._hoops = keep


def _ctx(conn):
    g = {"home": "DUKE", "away": "UNC", "date": "2026-11-25", "home_ml": -240, "away_ml": 196}
    return R.Ctx(g, {}, sport="cbb", names={"DUKE": "Duke", "UNC": "North Carolina"}, conn=conn)


def test_the_report_says_which_ratings_and_what_they_were_fitted_on():
    with _Kept():
        c = _ctx(conn=object())
        sec = R.sec_verdict(c)
        assert c.ratings_kind == "adjusted"
        items = next(b for b in sec["blocks"] if b["type"] == "list")["items"]
        line = next(i for i in items if i.startswith("Our team ratings alone"))
        p = round(CR.win_prob(18.4, 12.1, False) * 100)
        assert line == (f"Our team ratings alone: Duke {p}%. Unproven: they were fitted on four seasons of "
                        "college results (15,945 games) and haven't been measured against the price yet."), line
    assert R.ratings_why("cbb") == "they haven't been measured against the price yet", "the average margins"
    import engine.gamecal as GC
    keep = GC.measured
    try:
        GC.measured = lambda sport, market: {"shrink": 0.0, "n": 1204}
        assert R.ratings_why("cbb", "adjusted") == ("over 1,204 graded games, their disagreements with the "
                                                    "closing line carried nothing"), "a measurement wins"
    finally:
        GC.measured = keep


def test_the_race_keeps_every_fit_it_makes():
    src = (ROOT / "engine" / "ncaarace.py").read_text(encoding="utf-8")
    assert ("    ratings = CR.adjusted(done, prior=prior)\n    try:\n        keep_ratings(day, ratings, prior, "
            "len(done))\n") in src
    assert "the college ratings were not kept for the game reports" in src


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
