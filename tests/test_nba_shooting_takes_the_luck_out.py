"""Points and threes rebuilt from shot volume, luck taken out
(engine/nba/shooting).

The NBA lab (docs/NBA_LAB.md): on two full seasons of the league's own
play-by-play, fit on 2024-25 and judged on 2025-26, threes read as his
attempts times a 3P% shrunk toward the league's landed 1.68% closer than
threes a minute, points 0.99%, the points combos 0.6-0.9%. These hold:

  * the arithmetic (attempts a minute × make rates shrunk by K attempts);
  * a hot shooter's threes come DOWN, a cold one's go UP, his volume stays;
  * a combo moves only its points part;
  * the read is off for the WNBA, off for markets without points or
    threes, off when shot columns are thin, and off with QB_NBA_SHOOTING=0;
  * the projection carries it as a "shooting" step and its chain still
    multiplies out to the number that shipped;
  * the build, the box's replay and the calibration fitters' walk all hand
    the same read to the projection.

Run directly: `python3 tests/test_nba_shooting_takes_the_luck_out.py`
"""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.nba import shooting as SH                        # noqa: E402

LG = {"p3": 0.36, "p2": 0.55, "pf": 0.78}


def _game(mins=34.0, fga=16, fg3a=7, fta=5, fgm=8, fg3m=3, ftm=4):
    pts = 2 * (fgm - fg3m) + 3 * fg3m + ftm
    return {"min": mins, "fga": fga, "fg3a": fg3a, "fta": fta, "fgm": fgm,
            "fg3m": fg3m, "ftm": ftm, "pts": pts}


def test_the_arithmetic_is_volume_times_a_shrunk_make_rate():
    assert abs(SH.shrunk(40, 100, 250, 0.36) - (40 + 90) / 350) < 1e-12
    recent = [_game() for _ in range(10)]
    read = SH.bundle(recent, recent, LG)
    s = SH.structural(read)
    m = 340.0
    a2, a3, af = (160 - 70) / m, 70 / m, 50 / m
    p3 = (30 + SH.K3 * 0.36) / (70 + SH.K3)
    p2 = (50 + SH.K2 * 0.55) / (90 + SH.K2)
    pf = (40 + SH.KF * 0.78) / (50 + SH.KF)
    assert abs(s["fg3m"] - a3 * p3) < 1e-12
    assert abs(s["pts"] - (2 * a2 * p2 + 3 * a3 * p3 + af * pf)) < 1e-12


def test_a_hot_shooter_comes_down_and_a_cold_one_comes_up():
    hot = [_game(fg3a=8, fg3m=4) for _ in range(20)]          # 50% lately
    long_hot = hot + [_game(fg3a=8, fg3m=2) for _ in range(40)]   # 25% before
    rate = sum(g["fg3m"] for g in hot) / sum(g["min"] for g in hot)
    m, note = SH.projection_mult("fg3m", rate, SH.bundle(hot, long_hot, LG))
    assert m < 0.85 and "50.0% lately" in note and "attempts" in note
    cold = [_game(fg3a=8, fg3m=1) for _ in range(20)]
    long_cold = cold + [_game(fg3a=8, fg3m=3) for _ in range(40)]
    rate = sum(g["fg3m"] for g in cold) / sum(g["min"] for g in cold)
    m, _ = SH.projection_mult("fg3m", rate, SH.bundle(cold, long_cold, LG))
    assert m > 1.15


def test_a_combo_moves_only_its_points_part():
    games = [dict(_game(fg3m=4, fg3a=7), reb=8.0, ast=5.0) for _ in range(20)]
    read = SH.bundle(games, games, LG)
    s = SH.structural(read)
    mins = sum(g["min"] for g in games)
    pts_rate = sum(g["pts"] for g in games) / mins
    pra_rate = sum(g["pts"] + g["reb"] + g["ast"] for g in games) / mins
    m_pts, _ = SH.projection_mult("pts", pts_rate, read)
    m_pra, _ = SH.projection_mult("pra", pra_rate, read)
    assert abs(m_pts - s["pts"] / s["pts_raw"]) < 1e-3
    assert abs(m_pra - (pra_rate - s["pts_raw"] + s["pts"]) / pra_rate) < 1e-3
    assert abs(m_pra - 1) < abs(m_pts - 1), "the combo moves less: only points moved"


def test_the_read_stays_out_where_it_was_not_measured_or_cannot_be_read():
    games = [_game(fg3m=5, fg3a=8) for _ in range(20)]
    read = SH.bundle(games, games, LG)
    rate = 0.12
    assert SH.projection_mult("reb", rate, read) == (1.0, "")
    assert SH.projection_mult("fg3m", rate, read, league_key="wnba") == (1.0, "")
    assert SH.projection_mult("fg3m", rate, None) == (1.0, "")
    thin = [{"min": 30, "pts": 10}] * 15 + games[:5]          # shot columns on a quarter of his minutes
    assert SH.bundle(thin, games, LG) is None
    old = os.environ.get("QB_NBA_SHOOTING")
    os.environ["QB_NBA_SHOOTING"] = "0"
    try:
        assert SH.projection_mult("fg3m", rate, read) == (1.0, "")
    finally:
        if old is None:
            os.environ.pop("QB_NBA_SHOOTING", None)
        else:
            os.environ["QB_NBA_SHOOTING"] = old
    assert SH.game_shots({"fga": 3}) is None and SH.game_shots(None) is None


def test_the_projection_carries_it_as_a_step_and_the_chain_closes():
    from engine import chain
    from engine.nba.pipeline import project
    hot = [_game(fg3a=8, fg3m=4) for _ in range(20)]
    long_hot = hot + [_game(fg3a=8, fg3m=2) for _ in range(40)]
    prop = {"player": "A Shooter", "market": "fg3m", "minutes": [g["min"] for g in hot],
            "values": [float(g["fg3m"]) for g in hot], "is_starter": True, "spread": 0.0,
            "rest": "1day", "player_mult": 1.0}
    plain = project(dict(prop))
    read = project(dict(prop, shooting=SH.bundle(hot, long_hot, LG)))
    assert read["projection"] < plain["projection"]
    keys = [s["key"] for s in read["chain"]["steps"]]
    assert "shooting" in keys and "shooting" not in [s["key"] for s in plain["chain"]["steps"]]
    assert chain.closes(read["chain"]) and chain.closes(plain["chain"])
    assert any("attempts" in c for c in read["context"])
    assert chain.STEP_LABELS["shooting"]


def test_the_logs_give_the_long_run_and_the_league():
    from engine import db
    conn = db.connect(":memory:")
    rows = []
    for d in range(70):
        day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
        g = _game(fg3m=2 if d < 50 else 4)
        for k, v in g.items():
            mk = "min" if k == "min" else k
            rows.append(("nba", 2026, day, f"g{d}", "A Shooter", "BOS", "NYK", "S", 1, mk, float(v)))
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    out = SH.longrun(conn, "nba", ["A Shooter", "Nobody"])
    assert list(out) == ["A Shooter"] and len(out["A Shooter"]) == SH.LONG_GAMES
    assert out["A Shooter"][0]["fg3m"] == 4.0, "newest first"
    before = SH.longrun(conn, "nba", ["A Shooter"], before="2026-02-01")
    assert all(g["fg3m"] == 2.0 for g in before["A Shooter"])
    assert SH.league_pcts(conn, "nba") == {}, "too few shots to say"
    many = [(r[0], r[1], r[2], r[3], f"P{i}", *r[5:]) for i in range(40) for r in rows]
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", many)
    lg = SH.league_pcts(conn, "nba")
    assert 0.25 < lg["p3"] < 0.6 and 0.5 < lg["p2"] < 0.7 and abs(lg["pf"] - 0.8) < 1e-9


def test_the_build_the_replay_and_the_fitters_hand_it_the_same_read():
    build = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert 'p["games"] = [p["by_week"][w] for w in weeks]' in build
    assert "_shooting.longrun(conn, args.league," in build and "_shooting.league_pcts(conn, args.league" in build
    assert '"shooting": (_shooting.bundle(h.get("games") or [], _shoot_long.get(prop.player),' in build
    from engine import hoopsreplay as HR
    games = [dict(_game(), reb=5.0, ast=3.0) for _ in range(30)]
    e = {"name": "A", "games": games}
    assert HR._shooting(e, 25, "nba", "pts") is not None
    assert HR._shooting(e, 25, "wnba", "pts") is None and HR._shooting(e, 25, "nba", "reb") is None
    src = (ROOT / "engine" / "hoopsreplay.py").read_text(encoding="utf-8")
    assert src.count('"shooting": _shooting(entries[n], i, sport, market)') == 2, "the replay and the walk"
    from engine import db
    conn = db.connect(":memory:")
    rows = [("nba", 2026, f"2026-01-{d:02d}", f"g{d}", "A", "BOS", "NYK", "S", 1, k, float(v))
            for d in range(1, 13) for k, v in dict(_game(), reb=5, ast=3).items()]
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    pts = db.hoops_entries(conn, "nba", "pts")
    reb = db.hoops_entries(conn, "nba", "reb")
    assert pts and "games" in pts[0] and pts[0]["games"][0].get("fg3a") == 7.0
    assert reb and "games" not in reb[0], "only where the read moves a market"


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
