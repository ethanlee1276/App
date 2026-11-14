"""Each NBA rate read past his last twenty games (engine/nba/rates).

The NBA lab (docs/NBA_LAB.md, "Twenty games is not enough for a rate"): on
two full seasons of the league's own box scores, each held out, his older
games (his last sixty, any club) at a weight a minute and some minutes of
his role's league rate, joined to the twenty's, came out closer: steals
4.5%, turnovers 3.3%, blocks 2.7-4.0%, rebounds 2.0-3.2%, assists 1.6-2.4%,
as numbers, and 0.5-1.5% better as chances through the fitters' own walk.
Points and threes stay the shooting read's (closer as a number, no better
as a chance). These hold:

  * the arithmetic, and a missing row is not a zero;
  * a hot fortnight comes down toward his older games, a thin twenty
    toward his role's league rate;
  * a combo is the sum of its parts, its points the shooting read's;
  * a twenty that never recorded the stat takes the longer read as its
    rate (no multiplier lifts a zero);
  * it is off for the WNBA, for points and threes, for a prop with no read, and with
    QB_NBA_RATES=0 or a box verdict that did not hold;
  * the projection carries it as a "rates" step and its chain multiplies
    out to the number that shipped;
  * the build, the box's replay and the fitters' walk hand the same read;
  * the box's own check (nbarates.py) judges every stat in every season big
    enough, files its verdict and the switch follows; the weekly refit runs
    it before the NBA's fitters and the heartbeat shows it.

Run directly: `python3 tests/test_nba_rates_read_past_the_twenty.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
for _k in ("QB_NBA_RATES", "QB_NBA_SHOOTING", "QB_NBA_SPREAD", "QB_NBA_ROTATION"):
    os.environ.pop(_k, None)

from engine.nba import rates as RT                           # noqa: E402
from engine.nba import shooting as SH                        # noqa: E402

LG = {"p3": 0.36, "p2": 0.55, "pf": 0.78}


def _fresh():
    os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
    os.environ.pop("QB_NBA_RATES", None)


def _game(mins=30.0, reb=6.0, ast=4.0, stl=1.0, blk=0.5, tov=2.0,
          fga=15.0, fg3a=6.0, fta=4.0, fgm=7.0, fg3m=2.0, ftm=3.0):
    pts = 2 * (fgm - fg3m) + 3 * fg3m + ftm
    return {"min": mins, "pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk, "tov": tov,
            "fga": fga, "fg3a": fg3a, "fta": fta, "fgm": fgm, "fg3m": fg3m, "ftm": ftm}


def _days(n, start=1):
    return [f"2026-{1 + (start + i) // 28:02d}-{1 + (start + i) % 28:02d}" for i in range(n)][::-1]


def _read(recent, older, starter=True):
    rd = _days(len(recent), start=len(older) + 1)
    od = _days(len(older))
    return RT.bundle(recent, rd, list(zip(rd, recent)) + list(zip(od, older)), starter)


def test_the_arithmetic_and_a_missing_row_is_not_a_zero():
    _fresh()
    recent = [_game(mins=25.0, reb=2.5) for _ in range(4)]          # 10 boards in 100 minutes
    older = [_game(mins=30.0, reb=6.0) for _ in range(10)]          # 60 boards in 300 minutes
    read = _read(recent, older)
    raw, new = RT.blended("reb", read)
    w, kappa = RT.PARAMS["reb"]
    want = (10 + w * 60 + kappa * RT.LEAGUE[True]["reb"]) / (100 + w * 300 + kappa)
    assert abs(raw - 0.1) < 1e-12 and abs(new - want) < 1e-12, (raw, new, want)
    gappy = recent + [{"min": 40.0, "reb": 9.0}] + [{"min": 40.0}]   # one game never stored blocks
    s = RT.sums(gappy)
    assert s["reb"] == (19.0, 140.0) and s["blk"] == (2.0, 100.0), s
    assert RT.blended("reb", RT.bundle([{"min": 30.0}], ["2026-01-02"], [], True)) is None, \
        "a twenty that never stored the stat is no read"


def test_a_hot_fortnight_comes_down_and_a_thin_twenty_leans_on_his_role():
    _fresh()
    hot = [_game(stl=3.0) for _ in range(20)]
    usual = [_game(stl=1.0) for _ in range(40)]
    m, note = RT.projection_mult("stl", 3.0 / 30.0, _read(hot, usual))
    assert m < 0.75, m
    assert "steals read past his last 20 games" in note and "measured" in note, note
    cold = [_game(stl=0.0) for _ in range(20)]
    assert RT.projection_mult("stl", 0.0, _read(cold, usual)) == (1.0, ""), "a zero rate has nothing to scale"
    lifted, why = RT.lift_zero("stl", _read(cold, usual))
    assert 0 < lifted < 1.0 / 30.0 and "No steals in his last 20 games" in why, (lifted, why)
    assert RT.lift_zero("stl", _read(hot, usual)) == (None, ""), "only a twenty with none of it"
    assert RT.lift_zero("reb_ast", _read(cold, usual)) == (None, "") and RT.lift_zero("stl", None) == (None, "")
    rookie = [_game(mins=12.0, blk=1.0) for _ in range(5)]          # 5 blocks in 60 minutes, no older games
    raw, new = RT.blended("blk", _read(rookie, []))
    assert raw > new > RT.LEAGUE[True]["blk"], "pulled toward his role's league rate, not all the way"


def test_a_combo_is_the_sum_of_its_parts():
    _fresh()
    from engine.nba.pipeline import project
    recent = [_game(reb=9.0, ast=6.0, fga=20.0, fg3a=8.0, fta=7.0, fgm=10.0, fg3m=3.0, ftm=6.0)
              for _ in range(20)]
    older = [_game() for _ in range(40)]
    rd = _days(20, start=41)
    read = RT.bundle(recent, rd, list(zip(rd, recent)) + list(zip(_days(40), older)), True)
    shoot = SH.bundle(recent, recent + older, LG)
    base = {"player": "A Wing", "minutes": [g["min"] for g in recent], "is_starter": True,
            "spread": 0.0, "rest": "1day", "player_mult": 1.0, "shooting": shoot, "rates": read}
    got = {}
    for market in ("pts", "reb", "ast", "pra", "reb_ast", "pts_reb", "pts_ast"):
        parts = {"pra": ("pts", "reb", "ast"), "reb_ast": ("reb", "ast"), "pts_reb": ("pts", "reb"),
                 "pts_ast": ("pts", "ast")}.get(market, (market,))
        vals = [sum(g[p] for p in parts) for g in recent]
        got[market] = project(dict(base, market=market, values=vals))["projection"]
    assert abs(got["pra"] - (got["pts"] + got["reb"] + got["ast"])) < 0.03, got
    assert abs(got["reb_ast"] - (got["reb"] + got["ast"])) < 0.03, got
    assert abs(got["pts_reb"] - (got["pts"] + got["reb"])) < 0.03, got
    assert abs(got["pts_ast"] - (got["pts"] + got["ast"])) < 0.03, got
    plain = project(dict(base, market="reb", values=[g["reb"] for g in recent], rates=None))["projection"]
    assert got["reb"] < plain, "nine boards a night over the twenty, six before: the read comes down"
    pts_plain = project(dict(base, market="pts", values=[g["pts"] for g in recent], rates=None))["projection"]
    assert got["pts"] == pts_plain, "points stay the shooting read's"


def test_the_read_stays_out_where_it_was_not_measured_or_is_switched_off():
    _fresh()
    hot = [_game(reb=12.0) for _ in range(20)]
    read = _read(hot, [_game() for _ in range(40)])
    assert RT.projection_mult("reb", 0.4, read)[0] < 1.0
    assert RT.projection_mult("reb", 0.4, read, "wnba") == (1.0, ""), "the WNBA was not measured"
    assert RT.projection_mult("fg3m", 0.1, read) == (1.0, ""), "threes stay the shooting read's"
    assert RT.projection_mult("pts", 0.7, read) == (1.0, ""), "points move through the shooting read"
    assert RT.projection_mult("reb", 0.4, None) == (1.0, "")
    os.environ["QB_NBA_RATES"] = "0"
    try:
        assert RT.projection_mult("reb", 0.4, read) == (1.0, "")
    finally:
        os.environ.pop("QB_NBA_RATES")
    from engine.nba import switches as W
    W.record_check("rates", False, "blk in 2026: -0.20%", follow=True)
    assert not RT.enabled() and RT.projection_mult("reb", 0.4, read) == (1.0, ""), \
        "a box verdict that did not hold turns it off"
    os.environ["QB_NBA_RATES"] = "1"
    try:
        assert RT.enabled(), "the box's setting still decides first"
    finally:
        os.environ.pop("QB_NBA_RATES")


def test_the_projection_carries_it_as_a_step_and_the_chain_closes():
    _fresh()
    from engine import chain
    from engine.nba.pipeline import project
    hot = [_game(blk=3.0) for _ in range(20)]
    prop = {"player": "A Big", "market": "blk", "minutes": [g["min"] for g in hot],
            "values": [g["blk"] for g in hot], "is_starter": True, "spread": 0.0,
            "rest": "1day", "player_mult": 1.0}
    plain = project(dict(prop))
    read = project(dict(prop, rates=_read(hot, [_game(blk=1.0) for _ in range(40)])))
    assert read["projection"] < plain["projection"]
    keys = [s["key"] for s in read["chain"]["steps"]]
    assert "rates" in keys and "rates" not in [s["key"] for s in plain["chain"]["steps"]]
    assert chain.closes(read["chain"]) and chain.closes(plain["chain"])
    assert any("blocks read past his last 20 games" in c for c in read["context"])
    assert chain.STEP_LABELS["rates"]


def test_a_twenty_with_none_of_it_is_no_longer_a_certain_under():
    _fresh()
    from engine import chain
    from engine.nba.pipeline import project
    from engine.nba.prob import p_over
    guard = [_game(blk=0.0) for _ in range(20)]
    prop = {"player": "A Guard", "market": "blk", "minutes": [g["min"] for g in guard],
            "values": [0.0] * 20, "is_starter": True, "spread": 0.0, "rest": "1day", "player_mult": 1.0}
    plain = project(dict(prop))
    read = project(dict(prop, rates=_read(guard, [_game(blk=0.0)] * 30 + [_game(blk=1.0)] * 10)))
    assert plain["projection"] == 0.0 and 0.05 < read["projection"] < 0.5, (plain["projection"], read["projection"])
    assert p_over("blk", read["projection"], 0.5) > 0.03, "over 0.5 blocks is unlikely, not impossible"
    # A tenth of a block is rounded to the hundredth, so the chain is held to
    # that rounding here rather than to its 1% (`chain.closes`).
    assert abs(chain.product(read["chain"]) - read["projection"]) <= 0.005, read["chain"]
    assert read["chain"]["base"]["rate_per_min"] > 0, "the read is the rate the chain starts from"
    assert any("No blocks in his last 20 games" in c for c in read["context"])


def test_the_logs_give_his_last_sixty_any_club():
    _fresh()
    from engine import db
    conn = db.connect(":memory:")
    rows = []
    for d in range(70):
        day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
        team = "BOS" if d < 40 else "NYK"
        for k, v in _game(reb=4.0 if d < 50 else 8.0).items():
            rows.append(("nba", 2026, day, f"g{d}", "A Big", team, "MIA", "S", 1, k, float(v)))
    rows.append(("nba", 2026, "2026-03-20", "dnp", "A Big", "NYK", "MIA", "B", 1, "min", 0.0))
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    out = RT.longrun(conn, "nba", ["A Big", "Nobody"])
    assert list(out) == ["A Big"] and len(out["A Big"]) == RT.LONG_GAMES
    assert out["A Big"][0][1]["reb"] == 8.0 and out["A Big"][0][0] > out["A Big"][-1][0], "newest first"
    assert all(float(g["min"]) > 0 for _d, g in out["A Big"]), "a night he sat is not a game"
    before = RT.longrun(conn, "nba", ["A Big"], before="2026-02-01")
    assert all(d < "2026-02-01" for d, _g in before["A Big"])


def test_the_build_the_replay_and_the_fitters_hand_it_the_same_read():
    _fresh()
    build = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert "_rates.longrun(conn, args.league," in build
    assert ('"rates": (_rates.bundle(h.get("games") or [], h.get("dates") or [],\n'
            '                                        _rate_long.get(prop.player), bool(h["starter"]), args.league)') in build
    from engine import hoopsreplay as HR
    games = [_game(reb=5.0 + (i % 3)) for i in range(70)]
    dates = sorted(_days(70))
    e = {"name": "A", "games": games, "dates": dates, "starters": [True] * 70}
    read = HR._rates(e, 65, "nba")
    assert read and read["starter"] is True
    want_recent = RT.sums(games[45:65])
    want_older = RT.sums(games[5:45])
    assert read["recent"] == want_recent and read["older"] == want_older, \
        "the twenty before it, then the forty past them that make his last sixty"
    assert HR._rates(e, 65, "wnba") is None
    src = (ROOT / "engine" / "hoopsreplay.py").read_text(encoding="utf-8")
    assert src.count('"rates": _rates(entries[n], i, sport)') == 2, "the replay and the walk"
    from engine import db
    conn = db.connect(":memory:")
    rows = [("nba", 2026, f"2026-01-{d:02d}", f"g{d}", "A", "BOS", "NYK", "S", 1, k, float(v))
            for d in range(1, 13) for k, v in _game().items()]
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    for market in ("reb", "stl", "reb_ast", "pra"):
        ent = db.hoops_entries(conn, "nba", market)
        assert ent and all(k in ent[0]["games"][0] for k in ("min",) + RT.KEYS), market
    assert "stl" not in db.hoops_entries(conn, "nba", "fg3m")[0]["games"][0], "threes carry the shooting read's"


def _box(tmp: Path, players: int):
    """A history of steady players whose nights scatter around their rates:
    a twenty-game rate carries the scatter, the longer read less of it."""
    from engine import db
    conn = db.connect(str(tmp / "history.db"))
    rows, seed = [], [12345]

    def noise(scale):
        seed[0] = (seed[0] * 1103515245 + 12345) % (2 ** 31)
        return round(scale * (2.0 * seed[0] / 2 ** 31 - 1.0))

    for p in range(players):
        for d in range(80):
            day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
            g = _game(reb=6.0 + noise(5), ast=4.0 + noise(3), stl=1.0 + noise(1), blk=1.0 + noise(1),
                      tov=2.0 + noise(2))
            for k, v in g.items():
                rows.append(("nba", 2026, day, f"g{p}-{d}", f"P{p}", "BOS", "NYK", "S", 1, k, float(v)))
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_the_box_check_judges_every_stat_and_the_switch_follows():
    _fresh()
    import nbarates as NR
    res = {2025: {s: {"n": NR.MIN_ROWS, "gain": 0.02} for s in NR.STATS},
           2026: {s: {"n": NR.MIN_ROWS, "gain": 0.01} for s in NR.STATS}}
    assert NR.verdict(res) == (True, [])
    res[2026]["blk"]["gain"] = -0.002
    assert NR.verdict(res) == (False, ["blk in 2026: -0.20%"])
    res[2026]["blk"]["n"] = NR.MIN_ROWS - 1
    assert NR.verdict(res)[0], "a season too thin in a stat is shown, not judged"
    thin = {2026: {s: {"n": 10, "gain": -0.5} for s in NR.STATS}}
    assert NR.verdict(thin) == (False, ["no season has enough games to judge"])
    tmp = Path(tempfile.mkdtemp())
    _box(tmp, 6)
    from engine import db
    import sqlite3
    conn = sqlite3.connect(str(tmp / "history.db"))
    try:
        rows = NR.cases(NR.load(conn))
    finally:
        conn.close()
    got = NR.measure(rows)[2026]
    assert all(got[k]["n"] > 0 and got[k]["gain"] > 0 for k in ("reb", "ast", "stl", "blk", "tov")), got
    keep_db, keep_min = db.DEFAULT_DB, NR.MIN_ROWS
    db.DEFAULT_DB = str(tmp / "history.db")
    NR.MIN_ROWS = 50
    try:
        import contextlib
        import io
        from engine.nba import switches as W
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            NR.main(["--save"])
        text = out.getvalue()
        assert "rates verdict filed" in text and "Read-only" not in text, text
        assert W.entry("rates")["verdict"] == "ready" and W.entry("rates")["on"] is True, W.entry("rates")
    finally:
        db.DEFAULT_DB, NR.MIN_ROWS = keep_db, keep_min
        os.environ.pop("QB_NBA_RATES", None)


def test_the_weekly_refit_runs_it_and_the_heartbeat_shows_it():
    _fresh()
    from engine import deepfit as D
    assert D.NBA_CHECKS["nba_rates"] == ("nbarates.py", ("--save",))
    assert "nba_rates" in D.PREREQS["nba"] and D.PIECE_ORDER.index("nba_rates") < D.PIECE_ORDER.index("nba")
    assert D.NBA_CHECK_GUESS_S["nba_rates"] > 0
    import launch
    pub = launch._nba_switches_public()
    assert pub["rates"]["on"] is True and pub["rates"]["set_on_box"] is False, pub


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
