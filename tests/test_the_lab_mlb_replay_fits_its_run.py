"""The Lab's MLB replay fits inside its run (engine/lab.mlb_section,
carry_forward, the Lab page).

Wednesday 4 November the Lab was 85 minutes into MLB, its first sport,
when a push restarted the site: every stored season walked for three
markets, against a run's ceiling of an hour with MLB's own game lines and
five more sports still to come. What these hold:

  * the replay walks the latest two seasons the history file holds, and
    the page says which;
  * with a time limit a market starts only while the time left covers its
    games at the pace the market before it walked; the first always
    starts; the ones not reached are named, in the log and on the page;
  * a market the run did not reach keeps the last run's numbers beside
    the ones this run made, dated; a market this run measured is never
    displaced by an older one;
  * without a limit nothing changes for the other callers;
  * the run's line for each sport says how long it took;
  * the page names the seasons and says which card is last week's.

Run directly: `python3 tests/test_the_lab_mlb_replay_fits_its_run.py`
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import db, lab                                       # noqa: E402
from engine import selectionfit as _sf                           # noqa: E402
import engine.mlb.backtest as MB                                 # noqa: E402
from _app import app_js                                          # noqa: E402

_sf.set_enabled(False)          # as tests/test_lab.py: the live haircut is not what this tests

MARKETS = ("total_bases", "hits", "strikeouts")


def _history(seasons=(2024, 2025, 2026), n_players=6, n_games=30):
    conn = db.connect(":memory:")
    rng = random.Random(5)
    rows = []
    for season in seasons:
        for market in MARKETS:
            for p in range(n_players):
                for g in range(n_games):
                    rows.append({"sport": "mlb", "season": season,
                                 "period": f"{season}-{5 + g // 28:02d}-{1 + g % 28:02d}",
                                 "game_id": f"{season}g{g}", "player": f"Player {p}",
                                 "team": "BOS", "opponent": "NYY", "position": "OF", "home": 1,
                                 "market": market, "value": max(0, int(rng.gauss(1.5, 1.2)))})
    rows.append({"sport": "nba", "season": 2027, "period": "2026-11-01", "game_id": "n1",
                 "player": "Not Baseball", "team": "BOS", "opponent": "NYK", "position": "G",
                 "home": 1, "market": "pts", "value": 20})
    db.upsert_player_logs(conn, rows)
    return conn


def _quiet(*a, **k):
    pass


class _Clock:
    """A clock that moves only when a market's walk runs: ``cost`` seconds
    per game walked."""
    def __init__(self, cost):
        self.t, self.cost = 1000.0, cost

    def __call__(self):
        return self.t


def _timed(clock):
    import time
    real_mono, real_walk = time.monotonic, MB.backtest_from_logs

    def walk(entries, market, **kw):
        clock.t += clock.cost * sum(len(e["values"]) for e in entries)
        return real_walk(entries, market, **kw)
    time.monotonic = clock
    MB.backtest_from_logs = walk
    return lambda: (setattr(time, "monotonic", real_mono), setattr(MB, "backtest_from_logs", real_walk))


def test_the_replay_walks_the_latest_two_seasons_and_says_which():
    conn = _history()
    assert lab.latest_seasons(conn, "mlb", 2) == [2025, 2026]
    assert lab.latest_seasons(conn, "nfl", 2) == []
    sec = lab.mlb_section(conn, log=_quiet)
    assert sec["seasons"] == [2025, 2026] and "not_reached" not in sec
    two = lab.mlb_props(conn, markets=MARKETS, log=_quiet, seasons=[2025, 2026])
    every = lab.mlb_props(conn, markets=MARKETS, log=_quiet)
    assert [m["n"] for m in sec["markets"]] == [m["n"] for m in two]
    assert all(a["n"] < b["n"] for a, b in zip(two, every)), "three seasons walk more games than two"


def test_a_market_starts_only_while_the_time_left_covers_it():
    conn = _history()
    clock = _Clock(cost=4.0)                        # 360 games a market, 24 minutes each
    undo = _timed(clock)
    logs = []
    try:
        sec = lab.mlb_section(conn, log=logs.append, budget_s=30 * 60)
    finally:
        undo()
    assert [m["market"] for m in sec["markets"]] == ["total_bases"], sec
    assert sec["not_reached"] == ["hits", "strikeouts"], sec
    assert any("total_bases replayed: 360 games in 24 min" in ln for ln in logs), logs
    assert any("stopped at the run's time limit: hits, strikeouts not replayed" in ln for ln in logs), logs


def test_with_time_enough_every_market_is_replayed():
    conn = _history()
    clock = _Clock(cost=1.0)                        # six minutes a market
    undo = _timed(clock)
    try:
        sec = lab.mlb_section(conn, log=_quiet, budget_s=30 * 60)
    finally:
        undo()
    assert [m["market"] for m in sec["markets"]] == list(MARKETS) and "not_reached" not in sec


def test_the_first_market_always_starts():
    conn = _history()
    clock = _Clock(cost=10.0)                       # an hour for the first alone
    undo = _timed(clock)
    try:
        sec = lab.mlb_section(conn, log=_quiet, budget_s=30 * 60)
    finally:
        undo()
    assert [m["market"] for m in sec["markets"]] == ["total_bases"]
    assert sec["not_reached"] == ["hits", "strikeouts"]


def _page(markets, stamp="2026-10-28T03:10:00"):
    return {"generated_at": stamp,
            "sports": {"mlb": {"props": {"markets": markets, "seasons": [2025, 2026]},
                               "game_lines": {"markets": [{"market": "total"}]},
                               "replayed_at": stamp}}}


def test_a_market_not_reached_keeps_last_weeks_numbers_dated():
    old = _page([{"market": "total_bases", "n": 900}, {"market": "hits", "n": 800},
                 {"market": "strikeouts", "n": 300}])
    blob = {"props": {"markets": [{"market": "total_bases", "n": 950}], "seasons": [2025, 2026],
                      "not_reached": ["hits", "strikeouts"]},
            "game_lines": {"markets": [{"market": "total"}]}, "replayed_at": "2026-11-05T01:00:00"}
    page, kept = lab.merge_sport(old, "mlb", blob)
    got = {m["market"]: m for m in page["sports"]["mlb"]["props"]["markets"]}
    assert got["total_bases"]["n"] == 950 and "carried_from" not in got["total_bases"], \
        "this run's measurement is never displaced"
    assert got["hits"]["n"] == 800 and got["hits"]["carried_from"] == "2026-10-28"
    assert got["strikeouts"]["carried_from"] == "2026-10-28"
    assert kept == ["mlb/props/hits", "mlb/props/strikeouts"], kept


def test_a_carried_market_keeps_its_first_date():
    old = _page([{"market": "total_bases", "n": 900},
                 {"market": "hits", "n": 800, "carried_from": "2026-10-21"}])
    blob = {"props": {"markets": [{"market": "total_bases", "n": 950}], "not_reached": ["hits"]},
            "replayed_at": "2026-11-05T01:00:00"}
    page, _ = lab.merge_sport(old, "mlb", blob)
    hits = [m for m in page["sports"]["mlb"]["props"]["markets"] if m["market"] == "hits"][0]
    assert hits["carried_from"] == "2026-10-21", "the measurement's date, not the last carry's"


def test_without_a_limit_nothing_changes_for_the_other_callers():
    conn = _history(seasons=(2026,))
    logs = []
    out = lab.mlb_props(conn, markets=("total_bases",), log=logs.append)
    assert out and out[0]["market"] == "total_bases" and not logs, logs


def test_the_lab_builds_mlb_with_its_budget_and_each_sport_says_how_long():
    import inspect
    assert "mlb_section(hconn, log=log, budget_s=cap(LAB_MLB_PROPS_BUDGET_S))" in inspect.getsource(lab.build_sport)
    assert 15 * 60 <= lab.LAB_MLB_PROPS_BUDGET_S <= 40 * 60 and lab.LAB_MLB_SEASONS == 2
    tmp = Path(tempfile.mkdtemp())
    logs = []
    lab.run_if_due(hconn=object(), log=logs.append, path=tmp / "backtest.json", force=True,
                   attempts_path=tmp / "attempts.json",
                   build_one=lambda sport, hconn, log, nfl: {"props": {"markets": [{"market": "m", "n": 1}]}})
    assert any(re.match(r"  lab: mlb replayed in \d+ min → ", ln) for ln in logs), logs[:4]


def _fn(src, name):
    i = src.index(f"function {name}(")
    ends = [src.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(src)]
    return src[i:min(ends)]


def test_the_page_names_the_seasons_and_says_which_card_is_last_weeks():
    node = shutil.which("node")
    if not node:
        return
    src = app_js()
    prog = "\n".join([_fn(src, "escapeHtml"), _fn(src, "labReachNote"), _fn(src, "labSeasonWord"), """
      console.log(JSON.stringify([
        labSeasonWord({seasons: [2025, 2026]}), labSeasonWord({season: 2025}), labSeasonWord({}),
        labReachNote({carried_from: "2026-10-28"}), labReachNote({stopped_early: true, weeks: [7, 9]}),
        labReachNote({weeks: [6, 17]})]));"""])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    seasons, one, none, carried, partial, whole = json.loads(out.stdout)
    assert seasons == "2025–2026 seasons" and one == "2025 season" and none == ""
    assert "Replayed 2026-10-28" in carried and "kept from that run" in carried
    assert "Weeks 7–9" in partial and "time ran out" in partial
    assert whole == ""
    assert "labReachNote(m)" in src and "escapeHtml(labSeasonWord(props))" in src


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
