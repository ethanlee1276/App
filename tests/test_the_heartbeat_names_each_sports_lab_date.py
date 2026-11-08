"""The heartbeat says which sports the Lab has replayed, and when
(launch._lab_dates_public, _weekly_jobs_public; engine/lab.status_line,
LAST_RUN).

The 8 November check-in read "lab: ok" as the weekly Lab's last line and
could not tell from it, or from anything public, whether the NFL had been
replayed since 29 September: the line the heartbeat keeps was the bare
status word, and the page with the dates on it is paid. What these hold:

  * the heartbeat's Lab entry carries the day each sport's numbers are
    from, read as the owner desk reads them (the subscriber's copy, each
    sport's ``replayed_at``, else the page's own date), and nothing else
    from the page;
  * with no page there is no such field, and a page that will not parse
    costs the heartbeat nothing;
  * the Lab's automatic lane ends on one line naming what it replayed,
    failed and left for the next run.

Run directly: `python3 tests/test_the_heartbeat_names_each_sports_lab_date.py`
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import launch                                                       # noqa: E402
from engine import gate, lab as LB, maintenance as M               # noqa: E402

PAGE = {"generated_at": "2026-11-08T02:07:30", "sports": {
    "nfl": {"replayed_at": "2026-11-08T02:05:00", "props": {"markets": [{"market": "rec_yds", "hit_rate": 0.571}]}},
    "cfb": {"props": {"markets": [{"market": "rush_yds", "hit_rate": 0.533}]}},
    "ufc": {"replayed_at": "2026-11-07T03:00:00"},
    "nhl": "not a sport the Lab replays"}}


class _Tree:
    """A Lab page in a scratch `<tmp>/web/data/` tree (its subscriber's copy
    beside it, in `<tmp>/data/built/`), and the chores' records in scratch."""

    def __init__(self, page=None, private=True):
        self.page, self.private = page, private

    def __enter__(self):
        td = Path(tempfile.mkdtemp())
        self.keep = (LB.LAB_PATH, M._child_dir)
        public = td / "web" / "data" / "backtest.json"
        public.parent.mkdir(parents=True)
        public.write_text(json.dumps({"generated_at": PAGE["generated_at"], "locked": {"whole_board": 5}}))
        if self.page is not None:
            built = td / "data" / "built" / "backtest.json"
            built.parent.mkdir(parents=True)
            built.write_text(self.page if isinstance(self.page, str) else json.dumps(self.page))
        LB.LAB_PATH = public
        M._child_dir = lambda: td / "cache"
        (td / "cache").mkdir()
        return td

    def __exit__(self, *exc):
        LB.LAB_PATH, M._child_dir = self.keep


def test_the_heartbeat_names_the_day_each_sports_numbers_are_from():
    with _Tree(PAGE):
        assert Path(gate.board_source(LB.LAB_PATH)).parent.name == "built", "the subscriber's copy"
        M._record_job("engine.lab", started="2026-11-08T01:57:57", ended="2026-11-08T02:07:30", minutes=10,
                      exit=0, cut_off=False, running=False, last="lab: ok (replayed nfl, cfb)")
        got = launch._weekly_jobs_public()
    assert got["lab"]["sports"] == {"nfl": "2026-11-08", "cfb": "2026-11-08", "ufc": "2026-11-07"}, got["lab"]
    assert got["lab"]["last"] == "lab: ok (replayed nfl, cfb)"
    out = json.dumps(got)
    assert "hit_rate" not in out and "0.571" not in out and "rec_yds" not in out, "dates only: the page is paid"


def test_no_page_no_dates_and_a_broken_page_costs_nothing():
    with _Tree(None):
        M._record_job("engine.lab", last="lab: ok")
        got = launch._weekly_jobs_public()
    assert got["lab"] == {"last": "lab: ok"}, got
    with _Tree("{ not json"):
        M._record_job("engine.lab", last="lab: ok")
        assert launch._weekly_jobs_public()["lab"] == {"last": "lab: ok"}
    with _Tree(PAGE):
        assert launch._lab_dates_public()["nfl"] == "2026-11-08"
        # No Lab job recorded yet: nothing to hang the dates on.
        assert "lab" not in launch._weekly_jobs_public()


def test_the_automatic_lane_ends_on_a_line_naming_what_it_replayed():
    td = Path(tempfile.mkdtemp())
    p = td / "web" / "data" / "backtest.json"
    p.parent.mkdir(parents=True)
    calls = []

    def build(sport, hconn, log=None, nfl=True):
        calls.append(sport)
        if sport == "cfb":
            raise RuntimeError("no college closes")
        return {"props": {"markets": [{"market": "x", "n": 40}]}, "game_lines": {}}
    status = LB.run_if_due(hconn=object(), log=lambda *a: None, path=p, force=True, build_one=build,
                           attempts_path=td / "attempts.json", budget_s=None)
    assert status == "partial" and calls == list(LB.SPORT_ORDER)
    done = [s for s in LB.SPORT_ORDER if s != "cfb"]
    assert LB.status_line(status) == f"lab: partial (replayed {', '.join(done)}; failed cfb)"
    # The next run owes only the sport that failed, and it fails again.
    again = LB.run_if_due(hconn=object(), log=lambda *a: None, path=p, build_one=build,
                          attempts_path=td / "attempts.json", budget_s=None)
    assert (again, LB.status_line(again)) == ("failed", "lab: failed (failed cfb)"), LB.LAST_RUN
    LB.LAST_RUN.clear()
    assert LB.status_line("already") == "lab: already"
    import inspect
    assert "print(status_line(status))" in inspect.getsource(LB.main)


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
