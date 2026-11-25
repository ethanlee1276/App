"""Basketball's team ratings are measured against the closing line (step AEU, 25 November 2026).

Every game report shows our team ratings' own chance beside the price's, "unproven"; football's and baseball's
game-line models are graded against their closes (engine/gamecal), basketball's never were. engine/hoopscal
measures the ratings each report reads, as they stood before each game, against the tape's last price before the
tip, in gamecal's own shapes. What this holds:

  * a close is the last price taken before the game started: one taken in play, or with no start on its row, is
    not read; the sharp book's stands where it quoted, the shopped field's otherwise; a moneyline needs both sides;
  * college's ratings for a day are fitted on the days before it alone, each game on its own floor (the race's
    kept day carries the neutral site), last season's ratings as the prior, and a fit started from the day
    before's lands where a fresh one does;
  * the NBA's are futuresdata.blended_ratings' numbers on the games before the day;
  * gamecal fits them as any league's, refuses a basketball total by name, and keeps every fit's numbers for the
    heartbeat, held or adopted;
  * a report reads a measurement only for the ratings it measured.

Offline. Run directly: `python3 tests/test_basketball_ratings_meet_the_closing_line.py`
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import cbbratings as CR, db, gamecal as GC, hoopscal as H   # noqa: E402

DAYS = ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
#: (day, home, away, home score, away score)
CBB = [("2026-11-10", "DUKE", "UNC", 80, 70), ("2026-11-10", "KU", "espn:9", 95, 50),
       ("2026-11-11", "UNC", "KU", 75, 72), ("2026-11-11", "DUKE", "KU", 66, 70),
       ("2026-11-12", "KU", "DUKE", 81, 77), ("2026-11-12", "UNC", "espn:9", 90, 60),
       ("2026-11-13", "DUKE", "UNC", 71, 74)]
PRIOR = [("2026-01-10", "DUKE", "UNC", 85, 70), ("2026-02-01", "KU", "DUKE", 70, 72),
         ("2026-02-10", "UNC", "KU", 60, 64)]


class _Box:
    def __init__(self, sport="cbb", games=CBB, prior=PRIOR, season=2026):
        self.sport, self.games, self.prior, self.season = sport, games, prior, season

    def __enter__(self):
        from engine.sources import fetch as F
        self.dir = Path(tempfile.mkdtemp())
        self.F, self.keep_cache = F, F.CACHE_DIR
        F.CACHE_DIR = self.dir / "cache"
        F.CACHE_DIR.mkdir()
        self.conn = db.connect(self.dir / "h.db")
        rows = []
        for i, (d, h, a, hs, as_) in enumerate(self.games):
            rows.append({"sport": self.sport, "season": self.season, "period": d, "game_id": f"g{i}", "home": h,
                         "away": a, "home_score": hs, "away_score": as_})
        for i, (d, h, a, hs, as_) in enumerate(self.prior):
            rows.append({"sport": self.sport, "season": self.season - 1, "period": d, "game_id": f"p{i}",
                         "home": h, "away": a, "home_score": hs, "away_score": as_})
        db.upsert_games(self.conn, rows)
        self.conn.commit()
        return self

    def tape(self, day, home, away, *, spread=None, ml=None, book="best", taken="T20:00:00Z",
             start="T23:00:00Z"):
        ev, rows = f"{day}-{away}@{home}", []
        base = {"sport": self.sport, "taken_at": day + taken, "event_id": ev, "home": home, "away": away,
                "book": book, "commence_time": (day + start) if start else None}
        if spread is not None:
            rows.append({**base, "player": home, "market": "spread", "line": spread, "over_odds": -110,
                         "under_odds": -110})
        for team, odds in zip((home, away), ml or ()):
            if odds:
                rows.append({**base, "player": team, "market": "moneyline", "line": 0.0, "over_odds": odds,
                             "under_odds": None})
        db.upsert_odds_history(self.conn, rows)
        self.conn.commit()

    def kept_day(self, day, neutral=()):
        rows = [{"id": "x", "date": d, "home": h, "away": a, "home_score": float(hs), "away_score": float(as_),
                 "neutral": (h, a) in neutral} for d, h, a, hs, as_ in self.games if d == day]
        (self.F.CACHE_DIR / f"cbb_slate_{day.replace('-', '')}.json").write_text(json.dumps({"rows": rows}))

    def __exit__(self, *exc):
        self.conn.close()
        self.F.CACHE_DIR = self.keep_cache
        shutil.rmtree(self.dir, ignore_errors=True)


def test_a_close_is_the_last_price_before_the_tip():
    with _Box() as b:
        b.tape("2026-11-13", "DUKE", "UNC", spread=-3.5, ml=(-160, 140), taken="T18:00:00Z")
        b.tape("2026-11-13", "DUKE", "UNC", spread=-4.0, ml=(-170, 150), taken="T22:59:00Z")
        b.tape("2026-11-13", "DUKE", "UNC", spread=+9.5, ml=(400, -600), taken="T23:30:00Z")   # in play
        b.tape("2026-11-12", "KU", "DUKE", spread=-2.0, ml=(-130, 110))
        b.tape("2026-11-12", "KU", "DUKE", spread=-1.0, ml=(-115, -105), book="Pinnacle", taken="T19:00:00Z")
        b.tape("2026-11-12", "UNC", "espn:9", spread=-30.0, start=None)                   # no start: not read
        b.tape("2026-11-11", "UNC", "KU", ml=(-120, None))                                # one side only
        closes = H.pregame_closes(b.conn, "cbb")
        assert closes[("2026-11-13", "DUKE", "UNC")] == {"spread": -4.0, "ml": (-170, 150)}, "the last before the tip"
        assert closes[("2026-11-12", "KU", "DUKE")] == {"spread": -1.0, "ml": (-115, -105)}, "the sharp book's"
        assert ("2026-11-12", "UNC", "espn:9") not in closes
        assert ("2026-11-11", "UNC", "KU") not in closes, "a moneyline needs both sides"


def test_college_ratings_for_a_day_come_from_the_days_before_on_their_own_floors():
    with _Box() as b:
        b.tape("2026-11-12", "KU", "DUKE", spread=-2.0, ml=(-130, 110))
        b.tape("2026-11-13", "DUKE", "UNC", spread=-4.0, ml=(-170, 150))
        b.kept_day("2026-11-11", neutral={("DUKE", "KU")})
        for d in ("2026-11-10", "2026-11-12", "2026-11-13"):
            b.kept_day(d)
        got = {(g["date"], g["home"]): (margin, p) for g, _q, margin, p in H.walk(b.conn, "cbb")}
        assert set(got) == {("2026-11-12", "KU"), ("2026-11-13", "DUKE")}
        from engine.ncaarace import prior_ratings
        prior = prior_ratings(b.conn, 2026)
        games = H.college_games(b.conn, 2026)
        assert {(g["home"], g["neutral"]) for g in games if g["date"] == "2026-11-11"} == {("UNC", False),
                                                                                         ("DUKE", True)}
        before = [g for g in games if g["date"] < "2026-11-12"]
        r = CR.adjusted(before, prior=prior)
        assert abs(got[("2026-11-12", "KU")][0] - (r["KU"] - r["DUKE"] + CR.HCA)) < 1e-3, "two days before it"
        floors = CR.adjusted([dict(g, neutral=False) for g in before], prior=prior)
        assert abs((floors["KU"] - floors["DUKE"]) - (r["KU"] - r["DUKE"])) > 0.1, "the neutral floor counts"
        r2 = CR.adjusted([g for g in games if g["date"] < "2026-11-13"], prior=prior)
        assert abs(got[("2026-11-13", "DUKE")][0] - (r2["DUKE"] - r2["UNC"] + CR.HCA)) < 1e-3
        assert abs(got[("2026-11-13", "DUKE")][1] - CR.win_prob(r2["DUKE"], r2["UNC"], False)) < 1e-3


def test_a_fit_started_from_the_day_before_lands_where_a_fresh_one_does():
    games = [{"home": h, "away": a, "home_score": hs, "away_score": as_, "neutral": False}
             for _d, h, a, hs, as_ in CBB]
    prior = {"DUKE": 10.0, "UNC": 6.0, "KU": 12.0}
    fresh = CR.adjusted(games, prior=prior)
    warm = CR.adjusted(games, prior=prior, init=CR.adjusted(games[:4], prior=prior))
    assert set(fresh) == set(warm) and all(abs(fresh[t] - warm[t]) < 5e-3 for t in fresh), (fresh, warm)


def test_the_nba_reads_futuresdatas_blend_on_the_games_before():
    from engine import futuresdata as FD
    games = [("2026-11-01", "BOS", "NYK", 110, 100), ("2026-11-02", "NYK", "MIA", 99, 101),
             ("2026-11-03", "MIA", "BOS", 90, 112), ("2026-11-05", "BOS", "MIA", 120, 118)]
    prior = [("2026-03-01", "BOS", "NYK", 100, 90), ("2026-03-02", "MIA", "NYK", 95, 101)]
    with _Box(sport="nba", games=games, prior=prior) as b:
        ours = H._blend(H._table_games(b.conn, "nba", 2026), {t: r.net for t, r in
                        __import__("engine.teamrates", fromlist=["x"]).compute_team_ratings(
                            b.conn, "nba", seasons=[2025]).items()}, "nba")
        theirs, _share, _played = FD.blended_ratings(b.conn, "nba", 2026)
        assert set(ours) == set(theirs) and all(abs(ours[t] - theirs[t]) < 2e-3 for t in ours), (ours, theirs)
        b.tape("2026-11-05", "BOS", "MIA", spread=-6.5, ml=(-250, 205))
        rows = H.walk(b.conn, "nba")
        assert len(rows) == 1 and rows[0][0]["date"] == "2026-11-05"
        before = H._blend([g for g in H._table_games(b.conn, "nba", 2026) if g["date"] < "2026-11-05"],
                          {t: r.net for t, r in __import__("engine.teamrates", fromlist=["x"]).compute_team_ratings(
                              b.conn, "nba", seasons=[2025]).items()}, "nba")
        from engine import futures as F
        assert abs(rows[0][2] - (before["BOS"] - before["MIA"] + F.HOME_EDGE["nba"])) < 1e-9


def test_gamecal_fits_basketball_and_refuses_a_total_by_name():
    with _Box() as b:
        b.tape("2026-11-12", "KU", "DUKE", spread=-2.0, ml=(-130, 110))
        b.tape("2026-11-12", "UNC", "espn:9", spread=-25.0, ml=(-5000, 2000))
        b.tape("2026-11-13", "DUKE", "UNC", spread=-4.0, ml=(-170, 150))
        spread = H.observations(b.conn, "cbb", "spread")
        assert len(spread) == 3
        ml = H.observations(b.conn, "cbb", "moneyline")
        assert len(ml) == 3 and all(len(o) == 3 and o[2] in (0.0, 1.0) for o in ml)
        f = GC.fit_one(b.conn, "cbb", "spread")
        assert f.n == 3 and not f.missing and f.slope == f.slope
        t = GC.fit_one(b.conn, "cbb", "total")
        assert t.missing == H.NO_TOTAL and t.missing.startswith("no ")
        state = GC.STATE_PATH
        try:
            GC.STATE_PATH = str(b.dir / "gamecal.json")
            out = GC.refresh(b.conn, sport="cbb")
        finally:
            GC.STATE_PATH = state
        keys = {m["key"]: m for m in out["measured"]}
        assert keys["cbb:spread"]["n"] == 3 and "hit_rate" in keys["cbb:spread"]
        assert "hit_rate" not in keys["cbb:moneyline"], "a moneyline's hit rate means nothing"
        assert any(h["key"] == "cbb:total" for h in out["held"])
        from engine import maintenance as M
        v = M.verdict_gamecal_measured(out)
        assert v["measured"]["cbb:spread"][0] == 3 and len(v["measured"]["cbb:spread"]) == 4
        assert len(v["measured"]["cbb:moneyline"]) == 3
        assert M.verdict_gamecal_measured({}) == {}


def test_a_report_reads_a_measurement_only_for_the_ratings_it_measured():
    from engine import gamereport as R
    keep = GC.measured
    try:
        GC.measured = lambda sport, market: {"shrink": 0.0, "n": 1310}
        assert R.ratings_why("cbb", "adjusted") == ("over 1,310 graded games, their disagreements with the "
                                                    "closing line carried nothing")
        assert R.ratings_why("cbb") == "they haven't been measured against the price yet", "the average margins"
        assert R.ratings_why("nba") == ("over 1,310 graded games, their disagreements with the closing line "
                                        "carried nothing")
    finally:
        GC.measured = keep
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert 'verdicts["game lines"].update(verdict_gamecal_measured(gc))' in src


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
