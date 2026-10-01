"""The basketball prop boards are replayed over stored history, and the
replay sits beside the journal's Brier on the Record page.

Audit 2026-09-30, B1-1 (roadmap #34). The NBA and WNBA boards priced props
every night and nothing replayed them — the Lab said "projections ship
unreplayed", and the only calibration evidence for those leagues was the
forward journal the headline is built from. engine.hoopsreplay walks the
board's own evaluate_prop over stored logs, game i priced from games [:i];
the Lab publishes it weekly; record.json carries a calibration-only summary
of every league's replay for the Record page.
"""

import datetime as dt
import json
import random
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import hoopsreplay as hr, lab  # noqa: E402


def _db(players=12, games=30, seed=7):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE player_game_logs (sport, season, player, team, "
              "position, period, market, value, game_id, opponent, home)")
    rnd = random.Random(seed)
    d0 = dt.date(2025, 11, 1)
    for p in range(players):
        rate, mins = rnd.uniform(0.3, 0.8), rnd.uniform(18, 36)
        for g in range(games):
            day = (d0 + dt.timedelta(days=2 * g)).isoformat()
            m = max(0.0, rnd.gauss(mins, 4))
            for mk, v in (("min", m), ("pts", rnd.gauss(rate * m, 4)),
                          ("reb", rnd.gauss(0.2 * m, 2)),
                          ("ast", rnd.gauss(0.12 * m, 1.5)),
                          ("fg3m", rnd.gauss(0.06 * m, 1))):
                c.execute("INSERT INTO player_game_logs VALUES "
                          "('nba', 2026, ?, 'BOS', ?, ?, ?, ?, ?, 'NYK', 1)",
                          (f"P{p}", "S" if mins > 28 else "B", day, mk,
                           max(0.0, round(v, 1)), f"g{g}"))
    return c


def test_every_market_is_priced_and_graded():
    res = hr.replay(_db(), "nba")
    got = {m: rep.n for m, rep, _ in res}
    assert set(got) == set(hr.MARKETS), got
    assert all(n > 50 for n in got.values()), got


def test_the_replay_never_sees_the_game_it_prices():
    """Change game i (and everything after it) and the price for game i
    must not move — the definition of walk-forward."""
    hist = hr.histories(_db(players=1, games=20), "nba")
    before, _ = hr.settled_props(hist, "pts", "nba", cap=0)
    first = before[0]
    rows = hist["P0"]
    k = next(i for i in range(hr.MIN_HISTORY, len(rows)) if rows[i][2].get("min", 0) > 0)
    for _, _, g in rows[k:]:
        g["pts"] = g["pts"] + 50
    after, _ = hr.settled_props(hist, "pts", "nba", cap=0)
    assert after[0].hit_prob == first.hit_prob and after[0].line == first.line
    assert after[0].projection == first.projection
    assert after[0].actual == first.actual + 50


def test_it_prices_through_the_boards_own_evaluate_prop():
    from engine.nba import pipeline
    calls = []
    real = pipeline.evaluate_prop

    def spy(prop, tune=None):
        calls.append(prop)
        return real(prop, tune) if tune is not None else real(prop)
    pipeline.evaluate_prop = spy
    try:
        hr.replay(_db(players=2, games=14), "nba", markets=("pts",))
    finally:
        pipeline.evaluate_prop = real
    assert calls, "the replay priced nothing through the production pricer"
    p = calls[0]
    assert len(p["minutes"]) == len(p["values"]) <= hr.WINDOW
    assert p["over_odds"] == -110 and p["under_odds"] == -110   # naive basis


def test_a_game_he_did_not_play_is_not_graded():
    c = _db(players=1, games=12)
    c.execute("UPDATE player_game_logs SET value = 0 WHERE market='min' "
              "AND period = (SELECT MAX(period) FROM player_game_logs)")
    hist = hr.histories(c, "nba")
    settled, _ = hr.settled_props(hist, "pts", "nba", cap=0)
    last = hist["P0"][-1][0]
    assert len(settled) <= len(hist["P0"]) - hr.MIN_HISTORY - 1, last


def test_a_harvested_close_prices_on_the_book_basis():
    hist = hr.histories(_db(players=3, games=16), "nba")
    quotes = {(hr._norm(p), day): {"line": 14.5, "over_odds": -125,
                                   "under_odds": +105, "book": "fanduel"}
              for p, rows in hist.items() for day, _, _ in rows}
    settled, counts = hr.settled_props(hist, "pts", "nba", quotes, cap=0)
    assert counts["priced"] and counts["book"] == counts["priced"], counts
    assert all(s.basis == "book" and s.line == 14.5 for s in settled)
    assert {s.odds for s in settled} <= {-125, 105}


def test_the_lab_publishes_nba_props_instead_of_a_reason():
    assert "nba" not in lab.NO_PROP_HARNESS and "wnba" not in lab.NO_PROP_HARNESS
    markets = lab.hoops_props(_db(), "nba", log=lambda *_: None)
    assert {m["market"] for m in markets} == set(hr.MARKETS)
    assert all(m["basis"] == "naive" for m in markets)


def test_the_public_summary_carries_calibration_numbers_only():
    doc = {"generated_at": "2026-09-30T04:00:00", "sports": {
        "nba": {"props": {"markets": [
            {"market": "pts", "label": "Points", "n": 300, "brier": 0.24,
             "ece": 0.02, "skill": {"skill": 0.04}, "basis": "naive",
             "roi": 0.12, "n_bets": 40, "bins": [{"n": 1}]},
            {"market": "reb", "label": "Rebounds", "n": 100, "brier": 0.20,
             "ece": 0.04, "skill": {"skill": 0.08}, "basis": "naive"}]}},
        "ufc": {"props": {"unavailable": "graded forward"}}}}
    s = lab.replay_summary(doc)
    assert set(s) == {"nba", "generated_at"}
    n = s["nba"]
    assert n["n"] == 400 and n["brier"] == 0.23 and n["skill"] == 0.05
    assert n["basis"] == "naive"
    leaked = {"roi", "n_bets", "bins", "net_units", "wins", "segments"} & set(n)
    assert not leaked, f"paid replay detail on a public file: {leaked}"
    from engine import gate
    assert "replay" not in getattr(gate, "PAID_KEYS", ()), \
        "the gate would strip the summary the Record page reads"


def test_record_json_carries_the_replay_and_the_page_renders_it():
    src = (ROOT / "engine" / "ledger.py").read_text()
    assert '"replay": _replay_summary(),' in src
    app = (ROOT / "web" / "js" / "app.js").read_text()
    assert "+ recReplaySection(d.replay, scoped ? scope : null)" in app
    i = app.index("const REPLAY_SPORT = ")
    j = app.index("\n}\n", app.index("function recReplaySection(", i)) + 3
    code = app[i:j]
    js = ("const escapeHtml = (s) => String(s).replace(/[<>&\"]/g, '');\n" + code +
          "\nconsole.log(JSON.stringify([recReplaySection(" + json.dumps({
              "nba": {"n": 1234, "brier": 0.241, "skill": 0.031, "basis": "naive"},
              "generated_at": "2026-09-30"}) + ", null),"
          " recReplaySection({}, null),"
          " recReplaySection({nba: {n: 5, brier: .2}}, 'mlb')]));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    html, empty, scoped = json.loads(out.stdout)
    assert "NBA" in html and "1,234 priced" in html and "Brier 0.241" in html
    assert "skill +3.1%" in html and "trailing-average" in html
    assert "Replayed 2026-09-30" in html
    assert empty == "" and scoped == ""


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
