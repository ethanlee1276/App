"""The NBA and NHL builds put their stage times on the heartbeat.

The 8 November heartbeat had the NBA build at 78 seconds of every cycle and
the NHL's at 61, beside the NFL's and college's stage tables, with nothing
to say where either one's time went. Each now prints one line per stage as
it goes (engine/stageclock.mark), which the loop reads back into
boards.<sport>.stages, and the NHL's board stage, where nearly all of its
work happens, names its parts (stageclock.lap) as the NFL's pricing does.

Checks: each build marks its stages in the order it runs them, starts its
clock first, and prints its last mark before the closing summary (the line
the loop reports for a build); the NHL board's parts print only inside a
build, so the tests and the Lab that call it directly print nothing, and the
board is the same either way.

Run directly: `python3 tests/test_the_nba_and_nhl_builds_say_where_their_time_goes.py`
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import stageclock                                   # noqa: E402

NBA_STAGES = ("tuning fit", "schedule", "history + rosters + injuries", "game report facts",
              "slate + odds + line ledger", "context reads", "prop inputs", "menu audit + pricing",
              "shared recommendations + ladders", "scan + team profiles", "most likely board",
              "journal + settle", "comps + parlays",
              "live lines + tracker + exchange fair + crowd + openers + report", "write the board",
              "pick of the day journal + NBA Cup")
NHL_STAGES = ("schedule", "board", "prop tape + game lines + shift lines", "most likely board",
              "live lines + tracker + exchange fair + crowd + openers + report + pick of the day",
              "journal", "write the board")
NHL_BOARD_PARTS = ("player games", "injuries", "team profiles + league rates", "rosters + slate", "odds",
                   "shot quality", "starting goalies", "context + assets", "price slate",
                   "line combinations", "scan", "game bets + market scan")


def _main_of(name):
    src = (ROOT / name).read_text()
    return src[src.index("def main("):]


def _in_order(body, needles):
    at = [body.index(n) for n in needles]
    return at == sorted(at), at


def test_the_nba_build_marks_its_stages_in_order_and_keeps_its_summary_last():
    body = _main_of("nba_build.py")
    assert body.index("diagnose(args.league, args.date)") < body.index("_clock.start()"), \
        "a --diagnose run prints no stage clock"
    marks = [f'_clock.mark("{st}")' for st in NBA_STAGES]
    for m in marks:
        assert body.count(m) == 1, f"{m} once, or the loop adds two stages into one"
    ok, at = _in_order(body, ["_clock.start()"] + marks)
    assert ok, f"started first, then in the order the build runs them: {at}"
    assert body.count("_clock.mark(") == len(NBA_STAGES), "every mark is a named stage here"
    last = body.index(marks[-1])
    assert last < body.index('print(f"NBA {args.date}: {c[\'props_analyzed\']} props → "') \
        and last < body.index('print(f"NBA {args.date}: {out[\'status\']}. Wrote {args.out}")'), \
        "the summary stays the build's last line, the one the loop reports"


def test_the_nhl_build_marks_its_stages_in_order_and_keeps_its_summary_last():
    body = _main_of("nhl_build.py")
    marks = [f'_clock.mark("{st}")' for st in NHL_STAGES]
    for m in marks:
        assert body.count(m) == 1, m
    ok, at = _in_order(body, ["_clock.start()", "nhldata.schedule_day(args.date)"] + marks)
    assert ok, f"started before the schedule read, then in the order the build runs them: {at}"
    assert body.index('_clock.mark("board")') > body.index("out, slate = build(args.date, games, conn")
    assert body.index(marks[-1]) < body.index('print(f"NHL {args.date}: {len(games)} game(s)'), \
        "the summary stays the build's last line, the one the loop reports"


def test_the_nhl_boards_parts_are_named_in_the_order_it_reads_them():
    src = (ROOT / "nhl_build.py").read_text()
    body = src[src.index("def build("):src.index("def main(")]
    laps = [f'_clock.lap("board", "{p}", _pt)' for p in NHL_BOARD_PARTS]
    for lp in laps:
        assert body.count(lp) == 1, lp
    ok, at = _in_order(body, laps)
    assert ok, at
    assert "_clock.mark(" not in body, "a mark always prints; inside build only silent laps"


NBA_PARTS = {
    # 8 seconds at 10:13 on 9 November, nothing named.
    "history + rosters + injuries": ("_ht", ("week's schedule", "schedule spots", "rosters", "injuries",
                                             "player history", "history context",
                                             "total norm + minutes window")),
    # 5 seconds at 10:13 on 9 November, nothing named.
    "slate + odds + line ledger": ("_ot", ("props", "prop odds", "game lines", "stale-line scan",
                                           "prop tape", "line ledger")),
    "context reads": ("_ct", ("defense", "matchup ratings", "shooting", "rates",
                              "rotation + starting five")),
    "scan + team profiles": ("_st", ("team profiles", "vacancy", "faces", "scan")),
    "most likely board": ("_mt", ("pick of the day lines", "likely board",
                                  "scan stamps + matchup picks", "first basket", "one board")),
}


def test_the_nba_builds_eight_second_stages_name_their_parts_in_order():
    """At 09:05 on 9 November the NBA build's context reads ran 8 seconds,
    its Most Likely board 8 and its matchup scan 6, with nothing to say
    where: each now names its parts, between its stage's two marks."""
    body = _main_of("nba_build.py")
    order = list(NBA_STAGES)
    for stage, (var, parts) in NBA_PARTS.items():
        before = f'_clock.mark("{order[order.index(stage) - 1]}")'
        seg = body[body.index(before):body.index(f'_clock.mark("{stage}")')]
        laps = [f'_clock.lap("{stage}", "{p}", {var})' for p in parts]
        for lp in laps:
            assert seg.count(lp) == 1, (stage, lp)
        ok, at = _in_order(seg, laps)
        assert ok, (stage, at)
        assert body.count(f'_clock.lap("{stage}", ') == len(parts), f"{stage}: no other part"
        for p in parts:
            assert "›" not in p and ":" not in p, p


WRITE_PARTS = ("relock pick of the day", "freshness", "publish", "light board", "fantasy tonight")


def test_each_builds_write_stage_names_its_parts_in_order():
    """36 seconds of the NHL build at 00:56 on 9 November and 35 of the
    NFL's went to writing the board, 9 of the NBA's, for the same few jobs:
    each now says which."""
    for name, before in (("nhl_build.py", '_clock.mark("journal")'),
                         ("nba_build.py", '_clock.mark("live lines + tracker + exchange fair + crowd + openers + report")')):
        body = _main_of(name)
        seg = body[body.index(before):body.index('_clock.mark("write the board")')]
        laps = [f'_clock.lap("write the board", "{p}", _wt)' for p in WRITE_PARTS]
        for lp in laps:
            assert seg.count(lp) == 1, (name, lp)
        ok, at = _in_order(seg, laps)
        assert ok, (name, at)
        assert "_wt = _wtime.monotonic()" in seg, name


def test_no_stage_name_can_be_read_as_a_part_or_cut_short():
    for st in NBA_STAGES + NHL_STAGES + NHL_BOARD_PARTS:
        assert "›" not in st and ":" not in st, st
    said = []
    stageclock._STATE.update(t0=None, last=None)
    try:
        stageclock.start(clock=lambda: 0.0)
        for i, st in enumerate(NBA_STAGES):
            stageclock.mark(st, out=said.append, clock=lambda i=i: float(i + 1) * 2)
    finally:
        stageclock._STATE.update(t0=None, last=None)
    assert stageclock.parse(said) == {st: 2 for st in NBA_STAGES}, stageclock.parse(said)


def _quiet_board():
    import test_nhl_board_builds as T
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out, _slate = T._board()
    return out, buf.getvalue().splitlines()


def _picks(out):
    return ([(r["player"], r["market"], r["side"], r["line"], round(r["hit_prob"], 9))
             for r in out["recommendations"]],
            [(b["bet_type"], round(b["win_prob"], 9)) for b in out["game_bets"]])


def test_the_nhl_board_names_its_parts_only_inside_a_build_and_builds_the_same():
    keep = dict(stageclock._STATE)
    try:
        stageclock._STATE.update(t0=None, last=None)
        plain, said = _quiet_board()
        assert not [ln for ln in said if "⏱" in ln], "the tests and the Lab print no clock"
        stageclock.start()
        timed, said = _quiet_board()
        parts = stageclock.parse_parts(said)
        assert list(parts) == ["board"], parts
        assert tuple(parts["board"]) == NHL_BOARD_PARTS, tuple(parts["board"])
        assert all(v >= 0 for v in parts["board"].values())
        assert stageclock.parse(said) == {}, "a part is never counted as a stage"
        assert _picks(timed) == _picks(plain), "the clock never changes the board"
    finally:
        stageclock._STATE.clear()
        stageclock._STATE.update(keep)


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
