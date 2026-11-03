"""The Lab finishes in pieces: one sport at a time, each published as it
lands, each dated by its own replay (engine/lab.run_if_due, due_sports).

The 30 October audit found the Lab's page stamped 2026-09-29, five weeks
old, on a box meant to replay it weekly. The run built every sport in
memory and published only at the end; the NBA and WNBA replays joined it on
2026-10-01 and the NFL gained five markets on 10-10, and a pass cut off at
the chores' one-hour ceiling (engine.maintenance.WEEKLY_JOB_TIMEOUT_S)
wrote nothing — and was due again the next night, from the start. What
these hold:

  * a run cut off part way keeps every sport it finished, published through
    the gate, and the sports it did not reach keep their own old dates —
    never the new page's stamp, which would hide them for a week;
  * each sport it STARTS is marked before its replay begins, and the next
    run takes the sport it was cut off in last, so one harness that cannot
    finish in the hour never starves the rest;
  * a sport whose replay raises is skipped and the run goes on;
  * a sport the page does not carry is owed, a full fresh page owes
    nothing, and a page that measured nothing owes everything;
  * the attempts file lives in the page's own tree, never this checkout's;
  * a section carried forward is dated by its sport's own replay;
  * the page shows each sport's replay date.

Run directly: `python3 tests/test_the_lab_finishes_in_pieces.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gate, lab                                     # noqa: E402

OLD = "2026-09-29T04:40:09"
TODAY = dt.date(2026, 11, 3)


class _Killed(BaseException):
    """What the chores' reaper does to a run past the hour: not an error
    the run can catch, the end of it."""


def _old_page():
    """The page on the box: stamped 29 September, before the hoops replay
    joined the Lab — so it carries no NBA or WNBA."""
    return {"generated_at": OLD, "sports": {
        "mlb": {"props": {"markets": [{"market": "total_bases", "n": 40}]},
                "game_lines": {"markets": [{"market": "total"}]}},
        "nfl": {"props": {"markets": [{"market": "rec_yds", "n": 900}]},
                "game_lines": {"unavailable": "no harvested closing lines"}},
        "cfb": {"props": {"markets": [{"market": "anytime_td", "n": 500}]},
                "game_lines": {"markets": [{"market": "spread"}]}},
        "ufc": {"props": {"unavailable": "graded forward"},
                "game_lines": {"unavailable": "moneyline only"}}}}


def _tree(page=None):
    """A scratch tree shaped like the box: <tmp>/web/data/backtest.json, the
    private copy at <tmp>/data/built."""
    tmp = Path(tempfile.mkdtemp())
    public = tmp / "web" / "data" / "backtest.json"
    public.parent.mkdir(parents=True)
    if page is not None:
        private = tmp / "data" / "built" / "backtest.json"
        private.parent.mkdir(parents=True)
        private.write_text(json.dumps(page))
    return tmp, public


def _private(tmp):
    return json.loads((tmp / "data" / "built" / "backtest.json").read_text())


def _blob(sport):
    return {"props": {"markets": [{"market": f"{sport}-fresh", "n": 7}]},
            "game_lines": {"unavailable": "nothing this week"},
            "replayed_at": dt.datetime(2026, 11, 3, 6, 0).isoformat()}


def _stub(kill_at=None, raise_on=()):
    calls = []

    def build_one(sport, hconn, log=print, nfl=True):
        calls.append(sport)
        if kill_at is not None and len(calls) == kill_at:
            raise _Killed()
        if sport in raise_on:
            raise RuntimeError("database is locked")
        return _blob(sport)
    return build_one, calls


def _quiet(*_a, **_k):
    pass


def test_a_run_cut_off_part_way_keeps_every_sport_it_finished():
    tmp, public = _tree(_old_page())
    build_one, calls = _stub(kill_at=3)
    try:
        lab.run_if_due(hconn=object(), log=_quiet, path=public, today=TODAY, build_one=build_one)
        raise AssertionError("the stub was meant to cut the run off")
    except _Killed:
        pass
    # The two sports the page lacked go first (owed, never tried), then the
    # oldest — and the run was cut off in the third.
    assert calls == ["nba", "wnba", "mlb"], calls
    page = _private(tmp)
    assert page["sports"]["nba"]["props"]["markets"][0]["market"] == "nba-fresh"
    assert page["sports"]["wnba"]["props"]["markets"][0]["market"] == "wnba-fresh"
    # The sport it was cut off in, and the ones it never reached, are as
    # they were — and dated as they were, not by the new page's stamp.
    assert page["sports"]["mlb"]["props"]["markets"][0]["market"] == "total_bases"
    for sp in ("mlb", "nfl", "cfb", "ufc"):
        assert page["sports"][sp]["replayed_at"] == OLD, sp
    assert page["generated_at"] > OLD
    # Published through the gate: both copies written (the private one read
    # above), and with the paywall on the public one is sealed whole.
    assert public.exists() and gate.is_wholly_paid("backtest.json")
    assert not gate.redact(page, "backtest.json").get("sports"), "the backtests stay off the open web"


def test_the_sport_a_run_was_cut_off_in_goes_to_the_back_of_the_next_line():
    tmp, public = _tree(_old_page())
    build_one, _calls = _stub(kill_at=3)
    try:
        lab.run_if_due(hconn=object(), log=_quiet, path=public, today=TODAY, build_one=build_one)
    except _Killed:
        pass
    attempts = json.loads((tmp / "data" / "cache" / "lab_attempts.json").read_text())
    assert attempts == {"nba": "2026-11-03", "wnba": "2026-11-03", "mlb": "2026-11-03"}, attempts
    tomorrow = TODAY + dt.timedelta(days=1)
    owed = lab.due_sports(_private(tmp), tomorrow, attempts)
    assert owed == ["nfl", "cfb", "ufc", "mlb"], owed
    # And the next run finishes the rest, the cut-off sport last.
    build_one, calls = _stub()
    assert lab.run_if_due(hconn=object(), log=_quiet, path=public, today=tomorrow, build_one=build_one) == "ok"
    assert calls == ["nfl", "cfb", "ufc", "mlb"], calls
    page = _private(tmp)
    assert all(page["sports"][sp]["replayed_at"].startswith("2026-11-03") for sp in lab.SPORT_ORDER)
    assert lab.due_sports(page, tomorrow, attempts) == [], "a fresh page owes nothing"
    assert lab.run_if_due(hconn=object(), log=_quiet, path=public, today=tomorrow, build_one=build_one) == "already"


def test_a_sport_that_raises_is_skipped_and_the_run_goes_on():
    tmp, public = _tree(_old_page())
    build_one, calls = _stub(raise_on=("nfl",))
    logs = []
    got = lab.run_if_due(hconn=object(), log=logs.append, path=public, today=TODAY, build_one=build_one)
    assert got == "partial" and len(calls) == 6, (got, calls)
    page = _private(tmp)
    assert page["sports"]["nfl"]["props"]["markets"][0]["market"] == "rec_yds", "last measurement kept"
    assert page["sports"]["cfb"]["props"]["markets"][0]["market"] == "cfb-fresh"
    assert any("nfl skipped — RuntimeError: database is locked" in ln for ln in logs), logs
    assert any(ln.strip().startswith("lab: replaying nfl (") for ln in logs), "the line the reaper keeps"


def test_what_a_page_owes():
    fresh = {"generated_at": "2026-11-03T06:00:00",
             "sports": {sp: _blob(sp) for sp in lab.SPORT_ORDER}}
    assert lab.due_sports(fresh, TODAY) == []
    missing = json.loads(json.dumps(fresh))
    del missing["sports"]["nba"]
    assert lab.due_sports(missing, TODAY) == ["nba"], "a sport the page does not carry is owed"
    week = TODAY + dt.timedelta(days=lab.LAB_EVERY_DAYS)
    assert lab.due_sports(fresh, week) == list(lab.SPORT_ORDER)
    empty = {"generated_at": "2026-11-03T06:00:00",
             "sports": {sp: {"props": {"unavailable": "x"}, "game_lines": {"unavailable": "y"}}
                        for sp in lab.SPORT_ORDER}}
    assert lab.due_sports(empty, TODAY) == list(lab.SPORT_ORDER), "a page that measured nothing owes everything"
    # Read where the subscriber reads it, through the gate's private copy.
    tmp, public = _tree(fresh)
    assert not lab._due(public, TODAY) and lab._due(public, week)


def test_the_attempts_file_lives_in_the_page_tree():
    tmp = Path(tempfile.mkdtemp())
    assert lab._attempts_path_for(tmp / "web" / "data" / "backtest.json") == tmp / "data" / "cache" / "lab_attempts.json"
    assert lab._attempts_path_for(tmp / "backtest.json") == tmp / "lab_attempts.json"
    assert lab._attempts_path_for(lab.LAB_PATH) == lab.ATTEMPTS_PATH
    assert lab.ATTEMPTS_PATH == ROOT / "data" / "cache" / "lab_attempts.json"


def test_a_carried_section_is_dated_by_its_own_sport():
    prev = {"generated_at": "2026-11-03T06:00:00", "sports": {
        "nfl": {"replayed_at": "2026-10-28T05:00:00",
                "props": {"markets": [{"market": "rec_yds", "n": 900}]}}}}
    out = {"sports": {"nfl": {"props": {"unavailable": "skipped"}}}}
    assert lab.carry_forward(out, prev) == ["nfl/props"]
    assert out["sports"]["nfl"]["props"]["carried_from"] == "2026-10-28"


def test_the_page_shows_each_sports_replay_date():
    src = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
    i = src.index("async function renderLab(")
    body = src[i:src.index("\n}\n", i)]
    assert "s.replayed_at ? `replayed ${escapeHtml(formatStamp(s.replayed_at))}`" in body
    assert gate.PAID_FILES and "backtest.json" in gate.PAID_FILES


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
