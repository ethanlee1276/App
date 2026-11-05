"""MLB travel and rest are measured before anything is built (mlbtravelcheck.py,
docs/MLB_MODEL.md §7).

The MLB spec's Travel / Fatigue Engine (a day game after a night game,
time zones, cross-country trips, getaway days, long stretches without a
day off, doubleheaders) lived in the spec and never in the code. The box
check measures each situation against a runs model of every club's
offence and defence, every park and home field. A situation is worth
building only past the NFL's bar: two standard errors on the seasons
pooled, and the same side in three or more seasons. What holds:

  * each situation is read from the club's own schedule: the day after a
    night game, two or more time zones east or west with no day off, the
    miles between parks, the days in a row, a getaway day, a doubleheader's
    second game, the first game home after a long road trip;
  * the runs model gives each club-game its expected runs, scored and
    allowed, and its expected chance from both;
  * a situation that really moves runs clears the bar; noise does not, and
    one season alone is never enough;
  * the market part reads the box's stored closing totals read-only, and
    the check writes nothing anywhere;
  * a game scheduled short of nine innings (2021's seven-inning
    doubleheaders) is not read: it made the second game of a doubleheader
    look like it held; the box reads 2018 on, 2020's sixty games left out;
  * the runbook, the catch-up and RUN_NEXT carry the command.

Run directly: `python3 tests/test_mlb_travel_is_measured_before_it_is_built.py`
"""
import contextlib
import datetime as dt
import io
import json
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mlbtravelcheck as T                                    # noqa: E402

IDS = {"NYY": 147, "BOS": 111, "LAD": 119, "SF": 137, "CHC": 112, "SD": 135}
VENUE = {"NYY": "Yankee Stadium", "BOS": "Fenway Park", "LAD": "Dodger Stadium", "SF": "Oracle Park",
         "CHC": "Wrigley Field", "SD": "Petco Park"}
LINE = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 mlbtravelcheck.py"


def _game(pk, day, home, away, hs, as_, night=True, game_number=1):
    hour = 23 if night else 17
    return {"gamePk": pk, "officialDate": day, "gameDate": f"{day}T{hour:02d}:05:00Z",
            "dayNight": "night" if night else "day", "gameNumber": game_number,
            "doubleHeader": "S" if game_number == 2 else "N",
            "status": {"abstractGameState": "Final", "codedGameState": "F"},
            "teams": {"home": {"team": {"id": IDS[home]}, "score": hs},
                      "away": {"team": {"id": IDS[away]}, "score": as_}},
            "venue": {"name": VENUE[home]}}


def _payload(games):
    by_day = {}
    for g in games:
        by_day.setdefault(g["officialDate"], []).append(g)
    return {"dates": [{"date": d, "games": gs} for d, gs in sorted(by_day.items())]}


def _rows(games):
    return T.team_rows(T.games_from(_payload(games)))


def _flags(rows, team, day):
    return [r["flags"] for r in rows if r["team"] == team and r["date"] == day]


def test_each_situation_is_read_from_the_clubs_own_schedule():
    d = lambda n: (dt.date(2025, 6, 1) + dt.timedelta(days=n)).isoformat()   # noqa: E731
    games = [
        _game(1, d(0), "NYY", "BOS", 5, 3, night=True),          # NYY home, night
        _game(2, d(1), "NYY", "BOS", 4, 2, night=False),         # day after night
        _game(3, d(2), "LAD", "NYY", 3, 1, night=True),          # NYY flies west, no day off
        _game(4, d(3), "LAD", "NYY", 2, 6, night=True),
        _game(5, d(4), "NYY", "SF", 7, 1, night=True),           # NYY back east, no day off
        _game(6, d(6), "NYY", "SF", 1, 0, night=True),           # after a day off
        _game(7, d(6), "NYY", "SF", 2, 2 + 1, night=True, game_number=2),
    ]
    rows = _rows(games)
    assert len(rows) == 14
    assert _flags(rows, "NYY", d(1))[0]["day_after_night"] and _flags(rows, "BOS", d(1))[0]["day_after_night"]
    assert not _flags(rows, "NYY", d(0))[0]["day_after_night"]
    west = _flags(rows, "NYY", d(2))[0]
    assert west["west2"] and west["long_trip"] and not west["east2"]
    assert _flags(rows, "NYY", d(1))[0]["getaway"], "tomorrow in another park"
    assert _flags(rows, "NYY", d(1))[0]["getaway_day"], "and a day game"
    east = _flags(rows, "NYY", d(4))[0]
    assert east["east2"] and east["long_trip"]
    first, second = _flags(rows, "NYY", d(6))
    assert first["after_off"] and not first["dh2"] and second["dh2"]
    sf_first = _flags(rows, "SF", d(4))[0]
    assert not sf_first["east2"] and not sf_first["long_trip"] and not sf_first["after_off"], \
        "a club's first game has nothing before it"
    assert not any(f["streak13"] for r in rows for f in [r["flags"]])


def test_thirteen_days_in_a_row_and_the_first_game_home_after_a_road_trip():
    games, pk = [], 100
    start = dt.date(2025, 7, 1)
    for i in range(14):                       # CHC on the road six games, then home eight
        day = (start + dt.timedelta(days=i)).isoformat()
        home, away = ("SD", "CHC") if i < 6 else ("CHC", "SD")
        games.append(_game(pk, day, home, away, 4, 4 + (i % 2)))
        pk += 1
    rows = _rows(games)
    chc = sorted((r for r in rows if r["team"] == "CHC"), key=lambda r: r["date"])
    assert chc[6]["flags"]["home_after_trip"] and not chc[7]["flags"]["home_after_trip"]
    assert [r["flags"]["streak13"] for r in chc].count(True) == 2, "the 13th and 14th days"
    assert not chc[5]["flags"]["home_after_trip"]


def _season(seed, effect=1.0, n_days=150):
    """Six clubs, a season of series; a day game after a night game scores
    ``effect`` times its usual runs."""
    rnd = random.Random(seed)
    clubs = list(IDS)
    power = {c: 0.8 + 0.4 * rnd.random() for c in clubs}
    games, pk = [], seed * 100000
    start = dt.date(2000 + seed, 4, 1)
    for k in range(n_days):
        day = (start + dt.timedelta(days=k)).isoformat()
        week = (k // 3) % 5
        pairs = [(clubs[(i + week) % 6], clubs[(i + week + 3) % 6]) for i in range(3)]
        night = (k % 3) != 2
        for h, a in pairs:
            lam_h = 4.4 * power[h] / power[a] * 1.04
            lam_a = 4.4 * power[a] / power[h]
            if not night and (k % 3) == 2:
                lam_h *= effect
                lam_a *= effect
            hs = sum(1 for _ in range(60) if rnd.random() < lam_h / 60)
            as_ = sum(1 for _ in range(60) if rnd.random() < lam_a / 60)
            games.append(_game(pk, day, h, a, hs, as_ if as_ != hs else as_ + 1, night=night))
            pk += 1
    return _payload(games)


def _run(payloads, db=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = T.run(payloads, db)
    return out, buf.getvalue()


def test_the_runs_model_expects_what_each_club_scores():
    rows = T.team_rows(T.games_from(_season(1)))
    T.fit(rows)
    tot_r = sum(r["runs"] for r in rows)
    tot_e = sum(r["e"] for r in rows)
    assert abs(tot_r / tot_e - 1) < 1e-6, "the level is the season's"
    by = {}
    for r in rows:
        by.setdefault(r["team"], [0, 0])
        by[r["team"]][0] += r["runs"]
        by[r["team"]][1] += r["e"]
    assert all(abs(a / b - 1) < 0.02 for a, b in by.values()), by
    assert all(0 < r["p"] < 1 and "e_opp" in r for r in rows)
    assert 0.5 < T.overdispersion(rows) < 3.0


def test_a_real_effect_clears_the_bar_and_noise_does_not():
    real = {s: _season(s, effect=0.80) for s in (1, 2, 3, 4)}
    out, text = _run(real)
    ok, why = out["day_after_night"]
    assert ok and ("runs scored" in why or "runs allowed" in why), why
    assert "holds — worth building" in text
    flat = {s: _season(s + 10, effect=1.0) for s in (1, 2, 3, 4)}
    out, text = _run(flat)
    assert not out["day_after_night"][0], out["day_after_night"]
    one = {1: _season(1, effect=0.80)}
    out, _ = _run(one)
    assert not out["day_after_night"][0], "one season alone never clears the bar"
    assert "Verdicts (the NFL's bar" in text


def test_the_market_part_reads_the_stored_closes_and_writes_nothing():
    payload = _season(5)
    games = T.games_from(payload)
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, game_id TEXT, home TEXT, away TEXT, "
                 "home_score REAL, away_score REAL, spread REAL, total REAL, date TEXT)")
    for g in games[:400]:
        conn.execute("INSERT INTO games VALUES ('mlb', 2005, ?, ?, ?, ?, ?, ?, 0, 8.5, NULL)",
                     (g["date"], f"{g['away']}@{g['home']}", g["home"], g["away"], g["hr"], g["ar"]))
    conn.commit()
    conn.close()
    before = Path(path).read_bytes()
    try:
        out, text = _run({2005: payload}, path)
        assert "The market: 400 games with a stored closing total" in text, text[-1500:]
        assert "runs from the close" in text
        assert Path(path).read_bytes() == before, "the history file is opened read-only"
        out, text = _run({2005: payload}, None)
        assert "The market" not in text
    finally:
        os.unlink(path)


def test_saved_payloads_run_offline_and_an_empty_read_says_so():
    d = tempfile.mkdtemp()
    p = Path(d) / "s.json"
    p.write_text(json.dumps(_season(6)), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = T.main(["--files", str(p), "--db", str(Path(d) / "none.db")])
    assert rc == 0 and "MLB travel and rest, 2006-2006" in buf.getvalue(), buf.getvalue()[:400]
    assert sorted(os.listdir(d)) == ["s.json"], "nothing written beside it"
    e = Path(d) / "e.json"
    e.write_text(json.dumps({"dates": []}), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = T.main(["--files", str(e), "--db", ""])
    assert rc == 1 and "nothing to measure" in buf.getvalue()


def test_a_seven_inning_game_is_not_read_and_the_box_reads_2018_on_without_2020():
    d = lambda n: (dt.date(2021, 6, 1) + dt.timedelta(days=n)).isoformat()   # noqa: E731
    g1 = _game(1, d(0), "NYY", "BOS", 3, 2, game_number=1)
    g2 = _game(2, d(0), "NYY", "BOS", 1, 0, game_number=2)
    nine = _game(3, d(1), "NYY", "BOS", 5, 4)
    g1["scheduledInnings"] = g2["scheduledInnings"] = 7
    nine["scheduledInnings"] = 9
    games = T.games_from(_payload([g1, g2, nine]))
    assert [g["pk"] for g in games] == [3], games
    assert [g["pk"] for g in T.games_from(_payload([_game(4, d(2), "NYY", "BOS", 2, 1)]))] == [4], \
        "a payload without the field is a nine-inning game"
    assert T.default_seasons(2025) == [2018, 2019, 2021, 2022, 2023, 2024, 2025]


def test_the_check_is_read_only_and_names_no_one():
    src = (ROOT / "mlbtravelcheck.py").read_text(encoding="utf-8")
    assert "mode=ro" in src and "INSERT" not in src and "UPDATE" not in src and ".commit(" not in src
    assert "_get_json" not in src, "the cached fetch would write a file"
    assert "@" not in T.SCHEDULE


def test_the_runbook_the_catch_up_and_run_next_carry_it():
    book = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert LINE in book.split("\n")
    assert LINE in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8").split("\n")
    assert LINE in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8").split("\n")


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
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
