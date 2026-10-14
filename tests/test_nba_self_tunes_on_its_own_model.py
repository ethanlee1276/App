"""The basketball boards' self-tuning fits learn on the board's own model.

Ethan, 2026-10-14: "Ya do the self tuneung" — yes to the note that the
self-tuning fits had never been able to see PRA. Looking at why found a
larger gap: `logwalk.walk` handed the NBA and the WNBA to the FOOTBALL
chain (`projection.build_projection` + `betting.evaluate_prop`), so every
basketball temperature, player memory and rank AUC was measured on a
model no basketball board runs, then applied to the board's minutes ×
rate projection. Pinned here:

  * the walk door hands both leagues to the board's own `project` and
    `p_over` (`hoopsreplay.walk`) and never to the football chain;
  * each game is priced off the twenty before it exactly as the live
    build hands them to the board — minutes, starter, sums, counts — and
    with the league's fitted tuning, as the build fits it;
  * the temperature learns on the raw number, oldest game first, and the
    walk prices every game the model projects (no gate in the way);
  * the memory's hooks reach the projection: ``player_mult`` on a prop
    stands in for the store, and the record gets the number before it;
  * PRA, the combos and the counts are fitted for the NBA, and the
    recency dial declines basketball — there is no dial on its
    projection — and retires the dials it stored off the football chain;
  * a count with nothing in his window no longer stops the whole slate.

Run directly: `python3 tests/test_nba_self_tunes_on_its_own_model.py`
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

# The fitted models must not decide this file (see tests/test_nba.py).
from engine import calibrate as cal, losspatterns as _lp, playerfit as pf   # noqa: E402
_void = Path(tempfile.gettempdir()) / "qb-no-such-fit.json"
for _m in (cal, pf, _lp):
    _m.DEFAULT_PATH = _void
    _m._cache = {}

import calibrate as calibrate_cli                              # noqa: E402
import formfit as formfit_cli                                  # noqa: E402
import nba_build                                               # noqa: E402
import playerfit as playerfit_cli                              # noqa: E402
from engine import db, deepfit, hoops, hoops_fit, hoopsreplay, logwalk, rankfit   # noqa: E402
from engine import formfit as ff                               # noqa: E402
from engine.nba import pipeline, prob                          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NBA_MARKETS = ("pts", "reb", "ast", "fg3m", "pra", "pts_reb", "pts_ast", "reb_ast", "stl", "blk", "tov")


def _games(player, k=0, n=30, stl_from=24, bench_newest=False, sport="nba"):
    """``n`` games oldest first, every stat varying game to game; game 25
    a night he sat (zero minutes, his box row all zeros); steals stored
    from game ``stl_from`` on (older boxes have no row); with
    ``bench_newest`` he came off the bench in his newest game but one."""
    rows = []
    for i in range(n):
        day = f"2026-01-{i + 1:02d}"
        mins = 0.0 if i == 25 else float(22 + (i * 5 + k) % 15)
        on = 1.0 if mins else 0.0
        g = {"min": mins, "pts": on * (8 + (i * 7 + k) % 19), "reb": on * (2 + (i * 3 + k) % 9),
             "ast": on * (1 + (i + 2 * k) % 7), "fg3m": on * ((i + k) % 4), "blk": on * ((i * 2 + k) % 3),
             "tov": on * (1 + (i + k) % 3)}
        if i >= stl_from:
            g["stl"] = on * ((i + k) % 3)
        pos = "B" if bench_newest and i == n - 2 else "S"
        for market, v in g.items():
            rows.append({"sport": sport, "season": 2025, "period": day, "game_id": f"{player}-{day}",
                         "player": player, "team": "BOS", "opponent": "NYK", "position": pos,
                         "home": i % 2, "market": market, "value": float(v)})
    return rows


def _league(players=6, sport="nba", **kw):
    conn = db.connect(":memory:")
    for k in range(players):
        db.upsert_player_logs(conn, _games(f"Player {k}", k=k, sport=sport, **kw))
    conn.commit()
    return conn


def test_the_walk_door_hands_basketball_to_its_own_model():
    conn = _league()
    keep = logwalk.build_projection

    def football(*_a, **_k):
        raise AssertionError("the football chain priced a basketball game")

    logwalk.build_projection = football
    try:
        for sport in ("nba", "wnba"):
            c = conn if sport == "nba" else _league(sport="wnba")
            entries = logwalk.load_entries(c, sport, "pts", min_games=6)
            with cal.disabled():
                rep = logwalk.walk(sport, entries, "pts")
            assert rep.pairs and rep.total_priced == len(rep.pairs) == len(rep.settled), sport
            assert entries.aux["tune"].key == sport
    finally:
        logwalk.build_projection = keep
    src = (ROOT / "engine" / "logwalk.py").read_text(encoding="utf-8")
    assert 'HOOPS = ("nba", "wnba")' in src and "hoops_walk(entries, market" in src


def test_each_game_is_priced_off_the_twenty_before_it_as_the_build_hands_them():
    """The walk's number for his newest game is the live build's: the same
    window read by `nba_build.player_history` off only the games before
    it, through `pipeline.project` — a night he sat in the window, a
    starter flag off his newest game, a count read only where the box
    stored it, a sum added from its parts."""
    rows = _games("Guard One", bench_newest=True)
    full, before = db.connect(":memory:"), db.connect(":memory:")
    db.upsert_player_logs(full, rows)
    db.upsert_player_logs(before, [r for r in rows if r["period"] < "2026-01-30"])
    full.commit()
    before.commit()
    h = nba_build.player_history(before, {"BOS"})["Guard One"]
    assert h["starter"] is False and 0.0 in h["minutes"] and len(h["minutes"]) == 20
    assert len(h["stl"]) == 5, "games 24-28 carried steals"
    for market in ("pts", "pts_reb", "pra", "stl", "blk"):
        entries = logwalk.load_entries(full, "nba", market, min_games=6)
        rep = hoopsreplay.walk(entries, market, tune=hoops.NBA, cap=1, player_adjust=lambda _n: 1.0)
        want = pipeline.project({"player": "Guard One", "market": market, "minutes": h["minutes"],
                                 "values": h[market], "is_starter": bool(h["starter"]),
                                 "spread": 0.0, "rest": "1day", "player_mult": 1.0}, hoops.NBA)
        assert len(rep.settled) == 1, market
        assert rep.settled[0].projection == want["projection"], (market, rep.settled[0].projection, want)
        assert rep.settled[0].actual == entries[0]["values"][-1]
    # The Lab's replay hands the board the same window: every minute, and a
    # count only where it was stored.
    seen = []
    keep = pipeline.evaluate_prop
    pipeline.evaluate_prop = lambda prop, tune: seen.append(prop) or {"kind": "skip"}
    try:
        hoopsreplay.settled_props(hoopsreplay.histories(full, "nba"), "stl", min_history=8)
    finally:
        pipeline.evaluate_prop = keep
    last = seen[-1]
    assert len(last["minutes"]) == 20 and len(last["values"]) == 5, (len(last["minutes"]), len(last["values"]))


def test_the_entries_carry_minutes_starts_sums_and_the_fitted_tuning():
    conn = _league(players=2)
    e = logwalk.load_entries(conn, "nba", "pra", min_games=6)
    g = {x["name"]: x for x in e}["Player 0"]
    assert len(g["values"]) == len(g["minutes"]) == len(g["starters"]) == len(g["dates"]) == 30
    assert g["minutes"][25] == 0.0 and g["values"][25] == 0.0, "a night he sat is in his window"
    assert g["values"][3] == (8 + 21 % 19) + (2 + 9 % 9) + (1 + 3 % 7), "points, rebounds and assists added up"
    s = {x["name"]: x for x in logwalk.load_entries(conn, "nba", "stl", min_games=6)}["Player 0"]
    assert s["values"][:24] == [None] * 24, "a box with no steals row is not a zero"
    assert e.aux["tune"] == hoops_fit.fitted_tuning(conn, "nba")[0]
    assert logwalk.load_entries(conn, "nba", "pts").aux["tune"] is e.aux["tune"], "fitted once, not per market"
    assert logwalk.load_entries(conn, "nba", "pts", min_games=99) == [], "too few games, no entry"
    src = (ROOT / "engine" / "db.py").read_text(encoding="utf-8")
    assert "def entries_for_sum(" not in src, "one reader for basketball's entries"


def test_the_temperature_learns_on_the_raw_number_oldest_game_first():
    conn = _league()
    entries = logwalk.load_entries(conn, "nba", "pts", min_games=6)
    with cal.disabled():
        raw = logwalk.walk("nba", entries, "pts")
    store = Path(tempfile.mkdtemp()) / "calibration.json"
    store.write_text(json.dumps({"nba:pts": {"temperature": 2.0, "intercept": 0.3}}))
    keep = cal.DEFAULT_PATH
    cal.DEFAULT_PATH = store
    cal.reset_cache()
    try:
        tempered = logwalk.walk("nba", entries, "pts")
    finally:
        cal.DEFAULT_PATH = keep
        cal.reset_cache()
    # The same raw P(over) whichever side the tempered number backs (a side
    # restated twice differs in the last float digit, never more).
    assert len(tempered.pairs) == len(raw.pairs) and all(
        abs(a - b) < 1e-9 and x == y for (a, x), (b, y) in zip(tempered.pairs, raw.pairs)), \
        "the fit learns on the raw number"
    assert any(a.side != b.side for a, b in zip(tempered.settled, raw.settled)), "the tempered number picks the side"
    assert any(abs(a.hit_prob - b.hit_prob) > 1e-6 for a, b in zip(tempered.settled, raw.settled))
    for s in raw.settled:
        assert (s.hit_prob >= 0.5) and s.odds == -110 and s.basis == "naive" and s.raw_prob is not None
    # Oldest first, so `calibrate.bake_off`'s held-out slice is the latest
    # games; a cap keeps the most recent.
    todo = hoopsreplay._todo(entries, 8, 0)
    assert [t[0] for t in todo] == sorted(t[0] for t in todo)
    assert hoopsreplay._todo(entries, 8, 7) == todo[-7:]
    # No gate in the way: every gradeable game he could be projected for is
    # walked — the nights he sat are not graded, a book voids them.
    played = sum(1 for x in entries for i in range(8, 30) if x["minutes"][i] > 0)
    assert len(raw.pairs) == played


def test_the_memory_hooks_reach_the_projection():
    conn = _league()
    entries = logwalk.load_entries(conn, "nba", "reb", min_games=6)
    got: list = []
    with cal.disabled():
        one = logwalk.walk("nba", entries, "reb", player_adjust=lambda _n: 1.0)
        up = logwalk.walk("nba", entries, "reb", player_adjust=lambda _n: 1.1,
                          player_record=lambda name, p, a: got.append(p))
    assert all(abs(b.projection - round(a.projection * 1.1, 2)) <= 0.02 for a, b in zip(one.settled, up.settled))
    assert all(abs(p - s.projection) <= 0.02 for p, s in zip(got, one.settled)), \
        "the record gets the projection before the multiplier"
    # The fitter itself runs on it, and the board reads the store the same
    # way the walk's stand-in does.
    fit = pf.fit(entries, "reb", sport="nba")
    assert fit is not None and fit.samples == len(one.pairs)
    store = Path(tempfile.mkdtemp()) / "playerfit.json"
    store.write_text(json.dumps({"nba:reb": {"adopted": True, "players": {
        "player 0": {"mult": 1.1, "games": 60}}}}))
    prop = {"player": "Player 0", "market": "reb", "minutes": [30.0] * 12, "values": [6.0] * 12,
            "is_starter": True, "spread": 0.0, "rest": "1day"}
    keep = pf.DEFAULT_PATH
    pf.DEFAULT_PATH = store
    pf._cache = {}
    try:
        stored = pipeline.project(dict(prop), hoops.NBA)["projection"]
        off = pipeline.project(dict(prop, player_mult=1.0), hoops.NBA)["projection"]
    finally:
        pf.DEFAULT_PATH = keep
        pf._cache = {}
    assert stored > off and abs(stored - off * 1.1) < 0.02, (stored, off)


def test_pra_the_combos_and_the_counts_are_fitted_and_the_dial_declines_basketball():
    for mod in (calibrate_cli, playerfit_cli):
        assert tuple(mod.SPORT_MARKETS["nba"]) == NBA_MARKETS == rankfit.MARKETS["nba"], mod.__name__
        assert mod.SPORT_MARKETS["wnba"] == ["pts", "reb", "ast", "fg3m", "pra"], "the WNBA board prices five"
    assert {"nba", "wnba"} <= set(formfit_cli.SPORT_MARKETS), "deepfit counts sports from this table"
    assert set(formfit_cli.NO_DIAL) == {"nba", "wnba"}
    # The temperature fit sees PRA now.
    conn = _league()
    got, err = calibrate_cli.fit_market(conn, "pra", None, 200, sport="nba")
    assert err is None and got[1].pairs and all(0.0 <= p <= 1.0 for p, _ in got[1].pairs)
    # The dial: declined, and the dials stored off the football chain go.
    d = Path(tempfile.mkdtemp())
    (d / "formfit.json").write_text(json.dumps({"nba:pts": {"adopted": True, "r": 0.4},
                                               "mlb:hits": {"adopted": False, "r": 0.0}}))
    out = subprocess.run([sys.executable, "formfit.py", "--sport", "nba", "--from-db", str(d / "none.db")],
                         cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "QB_MODELS_DIR": str(d)})
    assert out.returncode == 0, out.stderr
    assert "nba: not fitted — " in out.stdout and "Retired 1 stored nba dial" in out.stdout
    assert set(json.loads((d / "formfit.json").read_text())) == {"mlb:hits"}
    assert ff.retire("nba", d / "formfit.json") == [] and ff.retire("mlb", d / "formfit.json") == ["mlb:hits"]
    # The weekly refit says why, not "nothing adopted".

    class _Done:
        returncode, stdout, stderr = 0, "nba: not fitted — no dial on this board\n", ""

    keep = deepfit.subprocess.run
    deepfit.subprocess.run = lambda *_a, **_k: _Done
    try:
        lines = deepfit.refit_sport("nba")
    finally:
        deepfit.subprocess.run = keep
    assert lines[0] == "deep refit: nba recency dial — not fitted: no dial on this board", lines


def test_the_rank_walk_measures_the_board_s_model():
    src = (ROOT / "engine" / "rankfit.py").read_text(encoding="utf-8")
    assert "load_entries(conn, sport, market)" in src and "sums=True" not in src
    conn = _league(players=10, n=30)
    store = Path(tempfile.mkdtemp()) / "rank_auc.json"
    lines = rankfit.measure(conn, "nba", markets=["pra"], path=store, log=lambda *_: None)
    assert lines and "walk failed" not in lines[0] and "pairs" in lines[0], lines


def test_a_count_with_nothing_in_his_window_no_longer_stops_the_slate():
    assert prob.p_over_negbin(0.0, 0.5, 0.9) == 0.0 and prob.p_over("blk", 0.0, 0.5) == 0.0
    assert prob.p_over_negbin(0.4, 0.5, 0.9) > 0.0
    prop = {"player": "Guard One", "market": "blk", "minutes": [34.0] * 12, "values": [0.0] * 5,
            "line": 0.5, "over_odds": 300, "under_odds": -450, "is_starter": True, "spread": -3.0,
            "rest": "1day", "book": "fanduel", "team": "BOS", "opponent": "NYK"}
    r = pipeline.evaluate_prop(dict(prop), hoops.NBA)
    assert r["kind"] == "skip" and "disagree" in r["why"], r
    out = pipeline.run_nba_slate([dict(prop)], tune=hoops.NBA)
    assert out is not None


def test_the_call_is_in_the_runbook():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "engine/hoopsreplay.walk" in doc
    assert re.search(r"refit_sport\('nba'\)", doc)


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
