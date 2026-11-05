"""The starting five's news moves the NBA's minutes before the tip (2026-11-04).

engine/nba/starters, measured on the lab's two seasons (docs/NBA_LAB.md,
"Who starts tonight"): about one game in eleven a man does the other thing
from his newest game — the bench man starts, the starter comes off the
bench — and those games carry a sixth of the board's squared minutes
error. Knowing tonight's five outright would take 5.5-6.0% off the minutes
error; what the board knows before the tip took 1.3-1.7% (points 0.3%),
each season held out. Pinned here:

  * the six terms read his starts over his last ten, his club's last
    starting five ruled out tonight, and the returning regulars who started
    before they sat — for a bench man and for a starter;
  * the NBA's values move the minutes through the vacancy's slot, caps
    included, and the card says why; the WNBA has none, the switch
    (engine/nba/switches ``starters``, QB_NBA_STARTERS) turns it off;
  * the build records who started each game (`player_history`), reads each
    club's news from the injury report and the returning regulars
    (`club_news`), and hands every prop its starts and both counts;
  * the fitters' walk hands the projection his own starts;
  * nbarules.py replays it beside the rotation's rules and files its own
    verdict, apart from theirs; the heartbeat shows the switch.

Run directly: `python3 tests/test_nba_starting_five_news.py`
"""
import contextlib
import io
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
for _k in ("QB_NBA_STARTERS", "QB_NBA_ROTATION", "QB_NBA_RATES", "QB_NBA_SPREAD", "QB_NBA_SHOOTING"):
    os.environ.pop(_k, None)

# The fitted models must not decide this file (see tests/test_nba.py).
from engine import calibrate as cal, losspatterns as _lp, playerfit as pf   # noqa: E402
_void = Path(tempfile.gettempdir()) / "qb-no-such-fit.json"
for _m in (cal, pf, _lp):
    _m.DEFAULT_PATH = _void
    _m._cache = {}

from engine import db, hoops, hoopsreplay                      # noqa: E402
from engine.nba import pipeline, starters as S, switches as W  # noqa: E402
import nba_build as B                                          # noqa: E402
import nbarules                                                # noqa: E402

NBA, WNBA = hoops.NBA, hoops.WNBA


def _fresh():
    """No verdict on file and no switch set: the defaults decide."""
    p = Path(W._path())
    if p.exists():
        p.unlink()
    os.environ.pop("QB_NBA_STARTERS", None)


def test_the_six_terms_for_a_bench_man_and_a_starter():
    bench = [False, False, True, True, True, False, False, False, True, False] + [False] * 10
    t = S.read(bench, five_out=1, five_back=1)
    assert t == {"bench_after_starts": 0.4, "bench_one_out": 1.0, "bench_two_out": 0.0,
                 "start_after_bench": 0.0, "start_one_back": 0.0, "fill_in_one_back": 0.0}, t
    assert S.read(bench, five_out=3)["bench_two_out"] == 1.0
    starter = [True, True, True, False, False, False, False, False, False, False, True]
    t = S.read(starter, five_out=2, five_back=1)
    assert t["start_after_bench"] == 0.7 and t["start_one_back"] == 1.0 and t["fill_in_one_back"] == 0.7
    assert t["bench_one_out"] == 0.0, "a starter is not the bench man a sitting starter makes room for"
    assert S.read(starter)["start_one_back"] == 0.0
    assert S.read([]) == dict.fromkeys(S.TERMS, 0.0) and S.read(None, 2, 2) == dict.fromkeys(S.TERMS, 0.0)
    assert S.share([True, False] * 10) == 0.5 and S.share(None) is None
    assert S.share([True] * 3) == 1.0, "a short window reads what it has"


def test_the_nbas_values_move_his_minutes_and_the_wnba_has_none():
    _fresh()
    assert tuple(NBA.starter_news) == S.TERMS and WNBA.starter_news == {}
    assert hoops.LeagueTuning(key="x", name="x").starter_news == {}, "off by default"
    c = NBA.starter_news
    assert c["bench_after_starts"] < 0 < c["bench_one_out"] < c["bench_two_out"] and c["fill_in_one_back"] < 0
    back = [False] + [True] * 9
    assert S.minutes(back, tune=NBA) == round(c["bench_after_starts"] * 0.9, 2)
    assert S.minutes(back, 2, 0, NBA) == round(c["bench_after_starts"] * 0.9 + c["bench_one_out"]
                                               + c["bench_two_out"], 2)
    fill = [True] * 3 + [False] * 7
    assert S.minutes(fill, 0, 1, NBA) == round(0.7 * c["start_after_bench"] + c["start_one_back"]
                                               + 0.7 * c["fill_in_one_back"], 2)
    assert S.minutes([True] * 10, 0, 0, NBA) == 0.0, "a settled starter with no news moves nothing"
    assert S.minutes(back, 2, 0, WNBA) == 0.0 and S.minutes(None, 2, 1, NBA) == 0.0


def test_the_switch_turns_it_off_and_a_verdict_decides_unset():
    _fresh()
    assert S.on() is True, "on from the day it was measured"
    os.environ["QB_NBA_STARTERS"] = "0"
    try:
        assert S.on() is False and S.minutes([False] + [True] * 9, 1, 0, NBA) == 0.0
    finally:
        os.environ.pop("QB_NBA_STARTERS")
    W.record_check("starters", False, "a season it stopped paying", follow=True)
    try:
        assert S.on() is False and W.entry("starters")["verdict"] == "not yet"
        os.environ["QB_NBA_STARTERS"] = "1"
        assert S.on() is True, "the box's own setting still wins"
    finally:
        os.environ.pop("QB_NBA_STARTERS", None)
        _fresh()
    assert W.ENV["starters"] == "QB_NBA_STARTERS" and W.DEFAULT["starters"] is True


def _prop(**kw):
    p = {"player": "X", "market": "pts", "minutes": [24.0] * 20, "values": [12.0] * 20,
         "is_starter": False, "spread": 0.0, "is_favorite": False, "rest": "1day", "player_mult": 1.0}
    p.update(kw)
    return p


def test_the_projection_carries_it_and_the_card_says_so():
    _fresh()
    plain = pipeline.project(_prop(), NBA)
    starts = [False] + [True] * 6 + [False] * 13
    moved = pipeline.project(_prop(starts=starts), NBA)
    shift = S.minutes(starts, 0, 0, NBA)
    assert shift < 0 and abs(moved["proj_min"] - round(plain["proj_min"] + shift * 1.0, 1)) <= 0.11, \
        (plain["proj_min"], moved["proj_min"], shift)
    assert moved["projection"] < plain["projection"]
    assert any("Back on the bench after starting 6 of his last 10" in c for c in moved["context"]), moved["context"]
    out = pipeline.project(_prop(starts=[False] * 20, five_out=2), NBA)
    assert out["proj_min"] > plain["proj_min"]
    assert any("2 of his club's last starting five are ruled out tonight" in c for c in out["context"])
    fill = pipeline.project(_prop(is_starter=True, starts=[True] * 2 + [False] * 18, five_back=1), NBA)
    assert any("A starter is back tonight and he started 2 of his last 10" in c for c in fill["context"])
    # The vacancy's caps hold it: never past his recent high plus the cap.
    big = pipeline.project(_prop(starts=[False] * 20, five_out=4, vacancy_minutes=30.0), NBA)
    assert big["proj_min"] <= 24.0 + NBA.vacancy_cap_over_high + 1e-9
    # Unknown starts, the WNBA, or the switch off: exactly as before.
    assert pipeline.project(_prop(five_out=3, five_back=2), NBA)["proj_min"] == plain["proj_min"]
    assert pipeline.project(_prop(starts=starts), WNBA)["proj_min"] == pipeline.project(_prop(), WNBA)["proj_min"]
    os.environ["QB_NBA_STARTERS"] = "0"
    try:
        assert pipeline.project(_prop(starts=starts), NBA)["proj_min"] == plain["proj_min"]
    finally:
        os.environ.pop("QB_NBA_STARTERS")
    small = S.note([True] * 10, 0, 0, 0.3)
    assert small == "", "a shift under NOTE_MIN says nothing"


def _logs(conn, player, team, games):
    rows = []
    for day, mins, started in games:
        for market, v in (("min", mins), ("pts", mins / 2)):
            rows.append({"sport": "nba", "season": 2026, "period": day, "game_id": f"{team}-{day}",
                         "player": player, "team": team, "opponent": "NYK", "position": "S" if started else "B",
                         "home": 1, "market": market, "value": float(v)})
    db.upsert_player_logs(conn, rows)


def test_the_build_records_who_started_and_reads_each_clubs_news():
    path = Path(tempfile.mkdtemp()) / "history.db"
    conn = db.connect(str(path))
    days = [f"2026-11-{d:02d}" for d in range(1, 7)]
    _logs(conn, "Star", "BOS", [(d, 34.0, True) for d in days])
    _logs(conn, "Fill", "BOS", [(d, 26.0, i >= 3) for i, d in enumerate(days)])
    _logs(conn, "Six", "BOS", [(d, 22.0, False) for d in days])
    _logs(conn, "Hurt", "BOS", [(d, 30.0, True) for d in days[:3]])          # sat the last three
    conn.commit()
    conn.row_factory = __import__("sqlite3").Row
    hist = B.player_history(conn, {"BOS"})
    assert hist["Fill"]["starts"] == [True, True, True, False, False, False], hist["Fill"]["starts"]
    assert len(hist["Fill"]["starts"]) == len(hist["Fill"]["minutes"])
    assert hist["Six"]["starts"] == [False] * 6 and hist["Star"]["starts"][0] is True
    club = B.club_days(hist, "2026-11-07")
    gone = {"BOS": [("Star", 34.0)]}
    back = {"BOS": [("Hurt", 30.0)]}
    out, ret = S.club_news("BOS", hist, club["BOS"], gone, back)
    assert out == ["Star"], "only a man in the club's last five who is ruled out"
    assert ret == ["Hurt"], "a returning regular who started before he sat"
    assert S.club_news("BOS", hist, club["BOS"], {"BOS": [("Six", 22.0)]}, {}) == ([], []), \
        "a bench man ruled out opens no starter's spot"
    assert S.club_news("BOS", hist, [], gone, back) == ([], [])
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    for want in ('"starts": list(h.get("starts") or [])',
                 '"five_out": len([n for n in _five.get(h["team"], ([], []))[0] if n != prop.player])',
                 '"five_back": len([n for n in _five.get(h["team"], ([], []))[1] if n != prop.player])',
                 "_starters.club_news(t, hist, _days.get(t) or [], gone, _back)"):
        assert want in src, want


def test_the_fitters_walk_hands_the_projection_his_starts():
    e = {"starters": [True, True, False, False, True], "minutes": [30, 31, 20, 21, 32]}
    assert hoopsreplay._starts(e, 4) == [False, False, True, True]
    assert hoopsreplay._starts(e, 0) == [] and hoopsreplay._starts({}, 3) == []
    src = (ROOT / "engine" / "hoopsreplay.py").read_text(encoding="utf-8")
    assert src.count('"starts": _starts(entries[n], i)') == 2, "the walk and the Lab's replay both"


def _club():
    """One club, 30 games: A and B start every game; C fills in for B while
    B sits (games 12-14) and goes back to the bench when B returns; D comes
    off the bench throughout."""
    games = {}
    for i in range(30):
        d = f"2026-{11 + i // 28:02d}-{1 + i % 28:02d}"
        g = {"A": {"min": 34.0, "pts": 18.0, "starter": True}}
        if not 12 <= i <= 14:
            g["B"] = {"min": 32.0, "pts": 16.0, "starter": True}
        g["C"] = {"min": 30.0 if 12 <= i <= 14 else 18.0, "pts": 9.0, "starter": 12 <= i <= 14}
        g["D"] = {"min": 21.0 if 12 <= i <= 14 else 17.0, "pts": 8.0, "starter": False}
        games[d] = g
    return {(2027, "BOS"): games}


def test_the_box_check_replays_it_and_files_its_own_verdict():
    _fresh()
    rows = nbarules.cases(_club(), NBA, 0.0)
    five = [r for r in rows if nbarules.FIVE in r["touched"]]
    assert {r["prop"]["player"] for r in five} >= {"C", "D"}, {r["prop"]["player"] for r in five}
    out_game = [r for r in rows if r["prop"]["player"] == "D" and r["prop"]["five_out"] == 1]
    assert out_game, "the night B first sat, his place in the last five is open"
    back_game = [r for r in rows if r["prop"]["player"] == "C" and r["prop"]["five_back"] == 1]
    assert back_game and back_game[0]["prop"]["starts"][0] is True, "B back: the fill-in started last"
    assert all(len(r["prop"]["starts"]) == len(r["prop"]["minutes"]) for r in rows)
    res = nbarules.measure(rows, NBA)
    assert nbarules.FIVE in res[2027] and "minutes" in res[2027][nbarules.FIVE]
    fine = {2025: {"n": 900, **{r: {"n": 150, "minutes": 0.02, "points": 0.01}
                               for r in (*nbarules.RULES, nbarules.FIVE)}}}
    assert nbarules.verdict(fine) == (True, []) and nbarules.verdict(fine, (nbarules.FIVE,)) == (True, [])
    sour = {2025: {k: dict(v) if isinstance(v, dict) else v for k, v in fine[2025].items()}}
    sour[2025][nbarules.FIVE] = {"n": 150, "minutes": 0.01, "points": -0.001}
    assert nbarules.verdict(sour) == (True, []), "the five failing never switches the rotation's rules"
    ok, why = nbarules.verdict(sour, (nbarules.FIVE,))
    assert not ok and "the starting five in 2025" in why[0]
    text = "\n".join(nbarules.report(sour, 0.0))
    assert "HOLDS — the board keeps all three." in text and "QB_NBA_STARTERS=0" in text
    assert "NOT JUDGED" in "\n".join(nbarules.report({2025: {"n": 900}}, 0.0))
    # Off, the rule moves nothing: `_without` hands the board no values.
    t, p = nbarules._without(nbarules.FIVE, NBA, rows[0]["prop"])
    assert t.starter_news == {} and p is rows[0]["prop"]
    src = (ROOT / "nbarules.py").read_text(encoding="utf-8")
    assert 'os.environ["QB_NBA_STARTERS"] = "1"' in src, "the run that decides the switch measures the rule"
    assert '("starters", (FIVE,))' in src


def test_the_weekly_run_files_both_verdicts_and_the_heartbeat_shows_it():
    _fresh()
    tmp = Path(tempfile.mkdtemp())
    conn = db.connect(str(tmp / "history.db"))
    rows = []
    for (season, team), games in _club().items():
        for d, g in games.items():
            for name, s in g.items():
                for market in ("min", "pts"):
                    rows.append({"sport": "nba", "season": season, "period": d, "game_id": f"{team}-{d}",
                                 "player": name, "team": team, "opponent": "NYK",
                                 "position": "S" if s["starter"] else "B", "home": 1,
                                 "market": market, "value": float(s[market])})
    db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    keep_db, keep_min = db.DEFAULT_DB, nbarules.MIN_TOUCHED
    db.DEFAULT_DB = str(tmp / "history.db")
    nbarules.MIN_TOUCHED = 1
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            nbarules.main(["--save"])
        text = out.getvalue()
        assert "the starting five" in text and "starters verdict" in text and "rotation verdict" in text, text
        assert W.entry("starters").get("verdict") in ("ready", "not yet"), W.entry("starters")
    finally:
        db.DEFAULT_DB, nbarules.MIN_TOUCHED = keep_db, keep_min
        os.environ.pop("QB_NBA_STARTERS", None)
        os.environ.pop("QB_NBA_ROTATION", None)
        _fresh()
    import launch
    pub = launch._nba_switches_public()
    assert pub["starters"]["on"] is True and pub["starters"]["set_on_box"] is False, pub


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"  FAIL {name}: {exc}")
            traceback.print_exc()
    if fails:
        print(f"\n{fails} of {len(tests)} tests failed.")
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
