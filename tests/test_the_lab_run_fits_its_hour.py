"""The Lab's whole run fits its hour (engine/lab.run_if_due, build_sport,
hoops_props; engine/hoopsreplay.replay).

The owner's desk, 5 November: "The Lab's WNBA numbers are 37 days old",
six sports late. The chores stop a weekly child at its hour, and a sport
cut off mid-replay publishes nothing: on 4 and 5 November the run spent
85 and 99 minutes inside its first sport. MLB and the NFL got limits of
their own; the rest had none, and nothing kept the run as a whole inside
the hour. What these hold:

  * the first sport always starts; after it, a sport starts only with
    `LAB_SPORT_MIN_S` left of `LAB_RUN_BUDGET_S`, and the ones not started
    are named, never marked tried, and first in the next run;
  * each sport is handed what is left less `LAB_SPORT_RESERVE_S`, capped by
    its own limit; a builder that takes no budget is called as before;
  * the NBA's and the WNBA's markets stop between markets at the pace the
    one before them walked, the first always starting; the ones not
    reached are named on the section and keep last week's numbers, dated.

Run directly: `python3 tests/test_the_lab_run_fits_its_hour.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import lab                                           # noqa: E402
from engine import selectionfit as _sf                           # noqa: E402

_sf.set_enabled(False)          # as tests/test_lab.py: the live haircut is not what this tests

TODAY = dt.date(2026, 11, 6)
COST_MIN = {"cfb": 20, "nba": 22, "wnba": 9, "ufc": 0, "mlb": 30, "nfl": 25}


class _Clock:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t


def _tree():
    tmp = Path(tempfile.mkdtemp())
    public = tmp / "web" / "data" / "backtest.json"
    public.parent.mkdir(parents=True)
    private = tmp / "data" / "built" / "backtest.json"
    private.parent.mkdir(parents=True)
    private.write_text(json.dumps({"generated_at": "2026-09-29T04:40:09", "sports": {
        sp: {"props": {"markets": [{"market": "m", "n": 9}]}} for sp in lab.SPORT_ORDER}}))
    return tmp, public


def _builder(clock, seen, with_budget=True):
    def blob(sport):
        return {"props": {"markets": [{"market": f"{sport}-fresh", "n": 7}]},
                "replayed_at": "2026-11-06T01:00:00"}
    if with_budget:
        def build_one(sport, hconn, log=print, nfl=True, budget_s=None):
            seen.append((sport, budget_s))
            clock.t += COST_MIN[sport] * 60
            return blob(sport)
    else:
        def build_one(sport, hconn, log=print, nfl=True):
            seen.append((sport, None))
            clock.t += COST_MIN[sport] * 60
            return blob(sport)
    return build_one


def _quiet(*_a, **_k):
    pass


def test_a_sport_starts_only_with_time_enough_left_and_the_rest_go_first_next_time():
    tmp, public = _tree()
    clock, seen, logs = _Clock(), [], []
    status = lab.run_if_due(hconn=object(), log=logs.append, path=public, today=TODAY,
                            build_one=_builder(clock, seen), clock=clock)
    order = [s for s, _ in seen]
    spent = sum(COST_MIN[s] for s in order)
    assert spent <= 50 + COST_MIN[order[-1]], "no sport starts past the run's budget"
    tried = json.loads((tmp / "data" / "cache" / "lab_attempts.json").read_text())
    skipped = [s for s in lab.SPORT_ORDER if s not in order]
    assert skipped, order
    assert not set(skipped) & set(tried), "a sport never started is not marked tried"
    assert status == "partial"
    assert any("stopped at the run's time limit" in ln and skipped[0] in ln for ln in logs), logs[-3:]
    assert any(ln.endswith("wait for the next run") for ln in logs), logs[-1]
    nxt = lab.due_sports(json.loads((tmp / "data" / "built" / "backtest.json").read_text()), TODAY,
                         tried)
    assert nxt[:len(skipped)] == [s for s in lab.SPORT_ORDER if s in skipped], "first in the next run"


def test_the_first_sport_always_starts_and_each_is_handed_what_is_left():
    tmp, public = _tree()
    clock, seen = _Clock(), []
    lab.run_if_due(hconn=object(), log=_quiet, path=public, today=TODAY,
                   build_one=_builder(clock, seen), clock=clock, budget_s=60)
    assert len(seen) == 1 and seen[0][1] == 60.0, "the first starts, with a minute at least"
    tmp, public = _tree()
    clock, seen = _Clock(), []
    lab.run_if_due(hconn=object(), log=_quiet, path=public, today=TODAY,
                   build_one=_builder(clock, seen), clock=clock)
    first, second = seen[0], seen[1]
    assert first[1] == lab.LAB_RUN_BUDGET_S - lab.LAB_SPORT_RESERVE_S
    assert second[1] == lab.LAB_RUN_BUDGET_S - COST_MIN[first[0]] * 60 - lab.LAB_SPORT_RESERVE_S


def test_a_builder_without_a_budget_is_called_as_before():
    tmp, public = _tree()
    clock, seen = _Clock(), []
    lab.run_if_due(hconn=object(), log=_quiet, path=public, today=TODAY,
                   build_one=_builder(clock, seen, with_budget=False), clock=clock)
    assert seen and all(b is None for _, b in seen)


def test_each_sports_own_limit_caps_what_the_run_hands_it():
    import inspect
    src = inspect.getsource(lab.build_sport)
    for name in ("LAB_MLB_PROPS_BUDGET_S", "LAB_NFL_PROPS_BUDGET_S", "LAB_HOOPS_PROPS_BUDGET_S"):
        assert f"budget_s=cap({name})" in src, name
    assert lab.LAB_RUN_BUDGET_S <= 50 * 60 and lab.LAB_SPORT_MIN_S >= 5 * 60
    assert "run_if_due(hconn=hconn, log=print)" in inspect.getsource(lab.main), \
        "the chores' run takes the default budget"


def test_basketball_stops_between_markets_and_keeps_last_weeks_numbers():
    import time
    from test_basketball_props_are_replayed import _db
    from engine import hoopsreplay as hr
    clock = _Clock()
    real_settled, real_mono = hr.settled_props, time.monotonic

    def slow(*a, **k):
        clock.t += 400                      # each market walks for 400 s
        return real_settled(*a, **k)
    hr.settled_props, time.monotonic = slow, clock
    try:
        missed = []
        got = lab.hoops_props(_db(), "nba", log=_quiet, budget_s=1000, missed=missed)
        blob = None
        logs = []
        hr.settled_props = slow
        blob = lab.build_sport("nba", _db(), log=logs.append, budget_s=1000)
    finally:
        hr.settled_props, time.monotonic = real_settled, real_mono
    # Two 400 s markets leave 200 s, under the pace the last one walked:
    # the third would end past the limit, so it does not start.
    assert [m["market"] for m in got] == list(hr.MARKETS[:2]), [m["market"] for m in got]
    assert missed == list(hr.MARKETS[2:])
    assert blob["props"]["not_reached"] == list(hr.MARKETS[2:])
    assert any("nba stopped at its time limit" in ln for ln in logs), logs
    old = {"generated_at": "2026-10-28T03:00:00", "sports": {"nba": {
        "props": {"markets": [{"market": m, "n": 50} for m in hr.MARKETS]},
        "replayed_at": "2026-10-28T03:00:00"}}}
    page, kept = lab.merge_sport(old, "nba", blob)
    by = {m["market"]: m for m in page["sports"]["nba"]["props"]["markets"]}
    assert set(by) == set(hr.MARKETS)
    assert all(by[m].get("carried_from") == "2026-10-28" for m in hr.MARKETS[2:])
    assert all("carried_from" not in by[m] for m in hr.MARKETS[:2]), "this run's numbers stand"
    assert kept == [f"nba/props/{m}" for m in hr.MARKETS[2:]]


def test_without_a_deadline_every_market_is_replayed():
    from test_basketball_props_are_replayed import _db
    from engine import hoopsreplay as hr
    missed = []
    got = hr.replay(_db(), "nba", missed=missed)
    assert [m for m, _r, _c in got] == list(hr.MARKETS) and missed == []


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
