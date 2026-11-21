"""The odds plan says where the month's credits went (engine/oddsplan).

Ethan, 2026-11-04: "it's now November 4th, so it's a new month, and we've
already ran through almost 10,000 credits, so we need to work on our
budgeting and stuff, because maybe something's not working. That seems
like a lot. Seems like we'll run out pretty soon."

Measured against the plan, nothing had run away: 100,000 credits over a
thirty-day month is 3,333 a day, the plan is built to spend nearly all of
it (credits left at the renewal expire), and the month's first days held
an NFL Sunday and a Monday night — the dearest days of the week. What was
missing was the sum. What these hold:

  * the report opens with the month so far: used against the quota, the
    share of the month gone, and the share of the month's spending the
    plan's own table puts in those days — on its pace, or ahead of it;
  * `--month` prints every day since the renewal (what it spent, the
    table's most for it, each lane), what the calls bought, and the API's
    own count beside the ledger's — a gap is spend the ledger never saw;
  * the renewal is SEEN when the ledger shows the API's own count falling
    back to zero (every live call books it since 2026-10-30), before it is
    measured or assumed — with one key on the ring only;
  * the command writes nothing.

Run directly: `python3 tests/test_the_month_says_where_the_credits_went.py`
"""
import contextlib
import datetime as dt
import inspect
import io
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path
from zoneinfo import ZoneInfo

# THE BOX'S CLOCK. The service runs in Eastern and books the ledger's dates
# in it; the API turns its month over at midnight UTC. Each test file runs in
# its own process, so this zone is this file's alone.
os.environ["TZ"] = "America/New_York"
time.tzset()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import oddsbudget as ob                          # noqa: E402
from engine import oddsplan as P                             # noqa: E402

ET = ZoneInfo("America/New_York")
OCT31 = dt.date(2026, 10, 31)
NOV1 = dt.date(2026, 11, 1)
NOV4 = dt.date(2026, 11, 4)
DEC1 = dt.date(2026, 12, 1)


def _row(utc, kind, sport, credits, used=None):
    """A ledger row as the box writes it: its clock, and its date in Eastern."""
    t = dt.datetime.fromisoformat(utc).replace(tzinfo=dt.timezone.utc)
    r = {"ts": t.timestamp(), "iso": t.astimezone(ET).replace(tzinfo=None).isoformat(timespec="seconds"),
         "kind": kind, "sport": sport, "credits": credits}
    if used is not None:
        r["used"] = used
    return r


def _month():
    """The ledger of a month like this one: the old month's last calls on
    the morning of the 31st, the API's meter back to zero at midnight UTC
    (8:05pm Eastern on the 31st, a college Saturday night), an NFL Sunday
    and Monday night, an Election Day with no basketball."""
    rows = [_row("2026-10-31T13:00:00", "live_event", "cfb", 50, used=99_350),
            _row("2026-10-31T15:00:00", "live_event", "cfb", 60, used=99_410)]
    used = 0
    for utc, kind, sport, c in (
            ("2026-11-01T00:05:00", "live_event", "cfb", 700),       # Sat Oct 31, 8:05pm ET
            ("2026-11-01T01:00:00", "hist_event", "nfl", 400),
            ("2026-11-01T02:00:00", "live_event", "nba", 104),
            ("2026-11-01T17:00:00", "live_event", "nfl", 4_800),     # Sunday
            ("2026-11-01T18:00:00", "live_board", "nfl_lines", 462),
            ("2026-11-01T23:00:00", "live_event", "nba", 690),
            ("2026-11-02T03:00:00", "hist_event", "nfl", 400),       # Sun 10pm ET
            ("2026-11-02T17:00:00", "live_event", "nfl", 780),       # Monday
            ("2026-11-02T23:00:00", "live_event", "nba", 800),
            ("2026-11-03T04:00:00", "hist_event", "nba", 400),       # Mon 11pm ET
            ("2026-11-03T17:00:00", "live_board", "nfl_lines", 12),  # Tuesday
            ("2026-11-03T20:00:00", "live_event", "nhl", 300),
            ("2026-11-03T21:00:00", "slip_event", "nfl", 25),
            ("2026-11-04T04:00:00", "hist_event", "nba", 400),       # Tue 11pm ET
            ("2026-11-04T13:00:00", "live_event", "nba", 50)):       # Wednesday 8am ET
        used += c
        rows.append(_row(utc, kind, sport, c, used=used))
    return rows, used


def _plan(pool=88_000, reset="seen"):
    return P.build(NOV4, pool, {"nba": 14, "nhl": 10, "cfb": 2}, end=DEC1, reset=reset,
                   start=NOV1, over=("mlb",))


# --- the renewal, seen ------------------------------------------------------------
def test_the_renewal_is_seen_where_the_apis_count_falls_to_zero():
    rows, _ = _month()
    # Booked on October 31 in Eastern; the API's day, in UTC, is the 1st.
    fell = next(r for r in rows if r.get("used") == 700)
    assert fell["iso"].startswith("2026-10-31T20:05")
    assert P.seen_start(rows, NOV4) == NOV1
    assert P.measured_start(sum(r["credits"] for r in rows[2:]), rows, NOV4) == OCT31, \
        "the ledger walk, by Eastern dates, reads the 31st: why the plan said 'renews Nov 30'"
    # No count on the rows (a ledger from before 2026-10-30): not seen.
    assert P.seen_start([{k: v for k, v in r.items() if k != "used"} for r in rows], NOV4) is None
    # A fall from a count too small to trust is noise, not a month.
    tiny = [_row("2026-11-02T14:00:00", "live_event", "nba", 5, used=60),
            _row("2026-11-02T15:00:00", "live_event", "nba", 5, used=4)]
    assert P.seen_start(tiny, NOV4) is None
    # A fall more than a month back is last month's.
    assert P.seen_start(rows, dt.date(2026, 12, 15)) is None
    # The latest fall is the one that counts.
    later = rows + [_row("2026-11-04T20:00:00", "live_event", "nba", 9, used=3)]
    assert P.seen_start(later, NOV4) == NOV4


def test_seen_comes_before_measured_and_after_set_with_one_key_only():
    rows, used = _month()
    st = ob.BudgetState(remaining=100_000 - used, used=used, last_seen_iso="2026-11-04T07:00:00")
    assert P.reset_day(st, rows, NOV4) == (1, "seen")
    assert P.period(NOV4, 1) == (NOV1, DEC1), "renews December 1, not November 30"
    two = ob.BudgetState(remaining=100_000 - used, used=used, last_seen_iso="2026-11-04T07:00:00",
                         keys={"aaaa1111": {"remaining": 60_000, "used": 40_000},
                               "bbbb2222": {"remaining": 30_000, "used": 9_000}})
    assert P.reset_day(two, rows, NOV4)[1] != "seen", "two keys: a switch between them is no renewal"
    os.environ[P.RESET_DAY_ENV] = "1"
    try:
        assert P.reset_day(st, rows, NOV4) == (1, "set"), "the setting still wins"
    finally:
        os.environ.pop(P.RESET_DAY_ENV, None)
    assert "seen: the API's own count of used credits fell back to zero" in P.report(_plan())
    assert _plan().headroom, "a seen renewal is a known one: the headroom is planned"


# --- the month so far -------------------------------------------------------------
def test_the_month_line_reads_used_beside_the_month_gone_and_the_plans_table():
    plan = _plan()
    rows, _ = _month()
    now = dt.datetime(2026, 11, 4, 7, 15).timestamp()           # 7:15am Eastern
    began = P.since(plan, rows)
    assert began == next(r for r in rows if r.get("used") == 700)["ts"], "the instant the meter reset"
    on = P.month_line(plan, 10_000, 90_000, now=now, over=("mlb",), since_ts=began)
    assert on.startswith("  this month so far: 10,000 of 100,000 used (10%) with 3.5 of 30 days gone (12%)"), on
    assert "the plan's table puts" in on and on.endswith("on its pace ✓"), on
    hot = P.month_line(plan, 30_000, 70_000, now=now, over=("mlb",), since_ts=began)
    assert "AHEAD of its table ⚠️" in hot and "--month" in hot, hot
    assert P.month_line(plan, 0, 100_000, now=now) == "" and P.month_line(plan, None, None, now=now) == ""
    text = P.report(plan, {}, {}, pool_now=88_000, month=on)
    lines = text.splitlines()
    assert lines[3] == on, "under the pool's line"


def test_the_table_is_each_league_at_its_headroom_and_the_harvest():
    sun = dt.date(2026, 11, 8)
    want = P.HARVEST_DAY + sum(P.day_need(lg, sun) * (1 + (P.NFL_HEADROOM if lg == "nfl" else P.HEADROOM))
                               for lg in P.PRIORITY if lg != "mlb")
    assert P.table_day(sun, over=("mlb",)) == round(want)
    assert P.table_day(sun, over=("mlb",)) > 2 * P.table_day(dt.date(2026, 11, 10), over=("mlb",)), \
        "an NFL Sunday is the dearest day of the week"
    month = sum(P.table_day(NOV1 + dt.timedelta(days=i), over=("mlb",)) for i in range(30))
    # Every league at its headroom: about the whole 100k, and since college
    # basketball joined (2026-11-13) a little past it — the plan cuts the
    # headroom, never a target, when the pool cannot hold all of it.
    assert 85_000 <= month <= 120_000, f"the table spends about the whole 100k: {month}"


# --- where it went ------------------------------------------------------------------
def test_where_it_went_day_by_day_lane_by_lane():
    rows, used = _month()
    by_day = P.daily_spend(rows, OCT31)
    assert by_day["2026-11-01"] == {"nfl": 5_262, "nba": 690, "harvest": 400}, by_day["2026-11-01"]
    assert by_day["2026-11-03"] == {"nfl": 12, "nhl": 300, "slips": 25, "harvest": 400}, by_day["2026-11-03"]
    assert "2026-10-30" not in by_day
    kinds = P.kind_spend(rows, OCT31)
    assert kinds["closing lines"] == 1_600 and kinds["game lines"] == 474 and kinds["slip checks"] == 25
    text = P.month_report(_plan(), rows, used=used, over=("mlb",))
    lines = text.splitlines()
    assert lines[0] == "WHERE THIS MONTH'S CREDITS WENT · Sat Oct 31 from 20:05 to today · renews Dec 1", lines[0]
    assert lines[1] == f"  the API counts {used:,} used this month; the ledger books {used:,}", \
        "the month runs from the instant the meter reset: that evening's calls, not that morning's"
    sat = next(ln for ln in lines if ln.startswith("  Sat Oct 31: "))
    assert sat.startswith("  Sat Oct 31: 1,204 (") and "CFB 700 · closing lines 400 · NBA 104" in sat, sat
    sat_tab = int(sat.split("(")[1].split(")")[0].replace(",", ""))
    assert sat_tab < P.table_day(OCT31, ("mlb",)) * 0.25, "the month had four hours of that Saturday"
    sun = next(ln for ln in lines if ln.startswith("  Sun Nov  1: "))
    assert sun.startswith(f"  Sun Nov  1: 6,352 ({P.table_day(NOV1, ('mlb',)):,})"), sun
    assert "NFL 5,262 · NBA 690 · closing lines 400" in sun, sun
    assert lines[-3].startswith("  Wed Nov  4 (so far): 50 ("), lines[-3]
    assert lines[-2].startswith("  by what the calls bought: player props 8,224 · closing lines 1,600"), lines[-2]
    assert lines[-1].startswith(f"  so far: {used:,} against the table's "), lines[-1]


def test_spend_the_ledger_never_saw_is_said():
    rows, used = _month()
    text = P.month_report(_plan(), rows, used=used + 3_000, over=("mlb",))
    assert "3,000 the ledger never saw ⚠️" in text.splitlines()[1]


def test_two_keys_have_no_one_month():
    st = ob.BudgetState(remaining=90_000, used=10_000, keys={})
    assert P.meter(st) == (10_000, 90_000)


# --- the command ------------------------------------------------------------------------
def test_the_command_prints_it_and_writes_nothing():
    rows, used = _month()
    d = tempfile.mkdtemp(prefix="oddsplan-")
    state = Path(d) / "odds_budget.json"
    ledger = Path(d) / "odds_spend.jsonl"
    ob.save(ob.BudgetState(remaining=100_000 - used, used=used,
                           last_seen_iso=dt.datetime.now().isoformat(timespec="seconds")), state)
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in (state, ledger)}
    saved = (ob.STATE_PATH, ob.SPEND_LOG, sys.modules.get("launch"))
    fake = types.ModuleType("launch")
    fake._games_today = lambda: {"nba": 14, "nhl": 10}
    fake._seasons_over = lambda: ("mlb",)
    ob.STATE_PATH, ob.SPEND_LOG = state, ledger
    sys.modules["launch"] = fake
    P._CACHE.clear()
    P._RESET.clear()
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = P.main(["--month"])
    finally:
        ob.STATE_PATH, ob.SPEND_LOG = saved[0], saved[1]
        if saved[2] is None:
            sys.modules.pop("launch", None)
        else:
            sys.modules["launch"] = saved[2]
        P._CACHE.clear()
        P._RESET.clear()
    text = out.getvalue()
    assert code == 0, text
    assert "ODDS PLAN" in text and "this month so far:" in text, text[:600]
    assert "WHERE THIS MONTH'S CREDITS WENT" in text, text[-800:]
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in (state, ledger)}
    assert before == after, "the command wrote to the budget's files"
    src = inspect.getsource(P.month_report) + inspect.getsource(P.month_line)
    for verb in ("write_text", "open(", "save(", "log_spend", "record_quota"):
        assert verb not in src, verb


def test_the_runbook_and_the_catchup_run_it():
    line = "cd /srv/qellys && sudo -u qellys python3 -m engine.oddsplan --month"
    assert line in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert line in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8")
    assert "catchup.sh JW" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")


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
