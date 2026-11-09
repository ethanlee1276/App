"""The UFC step says where its time goes (ufc_build.main's stage clock;
launch.refresh_ufc, _ufc_piece, _ufc_before_the_build).

The UFC step took 17 to 22 seconds of every cycle on 9 November, beside the
NFL's, college's, NBA's and NHL's stage tables, with nothing to say where:
the build printed no stage clock, and the loop's own work before it (the
dossier drafts, the weigh-ins, the fight history, the free card read and the
pacer) was nowhere at all. What these hold:

  * the build starts its clock first, marks each stage once in the order it
    runs them, and prints its last mark before the closing summary (the
    line the loop reports for a build);
  * the card's two biggest stages and the journal name their parts, in the
    order they run;
  * the loop's work before the build rides ahead of the build's stages as
    one stage, "before the build", each piece a part of it, and reaches the
    board's heartbeat entry once;
  * nothing before the build changes what the step does: the card read, the
    pacer and the build's flags are what they were.

Run directly: `python3 tests/test_the_ufc_step_says_where_its_time_goes.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

UFC_STAGES = ("dossiers", "card + odds", "weigh-ins", "the card", "pick of the day", "publish",
              "journal")
UFC_PARTS = {"card + odds": ["events list", "bout prices + dossier lookups", "venue", "fight snapshots"],
             "the card": ["model", "round prices", "fight paths", "line moves"],
             "journal": ["pick of the day", "log picks", "settle", "record export"]}
BEFORE = ["dossier drafts", "weigh-ins", "fight history", "the card (free events list)", "the pacer"]


def _main_of(name):
    src = (ROOT / name).read_text(encoding="utf-8")
    return src[src.index("def main("):]


def _in_order(body, needles):
    at = [body.index(n) for n in needles]
    return at == sorted(at), at


def test_the_ufc_build_marks_its_stages_in_order_and_keeps_its_summary_last():
    body = _main_of("ufc_build.py")
    marks = [f'_clock.mark("{st}")' for st in UFC_STAGES]
    for m in marks:
        assert body.count(m) == 1, f"{m} once, or the loop adds two stages into one"
    ok, at = _in_order(body, ["load_local_secrets()", "_clock.start()", "dossiers = load_dossiers()"] + marks)
    assert ok, f"started first, then in the order the build runs them: {at}"
    assert body.count("_clock.mark(") == len(UFC_STAGES), "every mark is a named stage here"
    assert body.index('_clock.mark("the card")') > body.index("result = run_card(fights)")
    assert body.index('_clock.mark("publish")') > body.index("gate.publish(out, p)")
    last = body.index(marks[-1])
    assert last > body.index("ledger.log_ufc_picks(lconn, out)")
    assert last < body.index('print(f"UFC {event_label}: {c[\'fights\']} bouts, {len(dossiers)} "') \
        and last < body.index('print(f"UFC: {out[\'status\']}. Wrote {args.out}")'), \
        "the summary stays the build's last line, the one the loop reports"


def test_the_cards_biggest_stages_and_the_journal_name_their_parts_in_order():
    body = _main_of("ufc_build.py")
    for stage, parts in UFC_PARTS.items():
        laps = [f'_clock.lap("{stage}", "{p}", ' for p in parts]
        for lap in laps:
            assert body.count(lap) == 1, lap
        ok, at = _in_order(body, laps + [f'_clock.mark("{stage}")'])
        assert ok, f"{stage}: its parts in the order they run, inside the stage: {at}"
    assert body.count("_clock.lap(") == sum(len(p) for p in UFC_PARTS.values()), \
        "every part is listed here"
    ok, _at = _in_order(body, ['"events list"', "for ev in card:", '"bout prices + dossier lookups"',
                               "_env.card_for(", '"venue"', "record_fight_snapshots(snaps)",
                               '"fight snapshots"'])
    assert ok
    ok, _at = _in_order(body, ["run_card(fights)", '"model"', "_rounds.attach(", '"round prices"',
                               "_fp.attach(", '"fight paths"', "_mv.attach(", '"line moves"'])
    assert ok


def test_the_stage_clock_reads_the_builds_lines_back():
    from engine import stageclock
    keep = dict(stageclock._STATE)
    said, t = [], iter([0.0, 0.4, 3.1, 3.3, 9.0])
    clock = lambda: next(t)                                         # noqa: E731
    try:
        stageclock.start(clock=clock)
        stageclock.mark("dossiers", out=said.append, clock=clock)
        since = clock()
        stageclock.lap("card + odds", "events list", since, out=said.append, clock=clock)
        stageclock.mark("card + odds", out=said.append, clock=clock)
    finally:
        stageclock._STATE.clear()
        stageclock._STATE.update(keep)
    assert list(stageclock.parse(said)) == ["dossiers", "card + odds"], said
    assert stageclock.parse_parts(said) == {"card + odds": {"events list": 0.2}}, said


def test_each_piece_before_the_build_is_timed_once_and_added_up():
    import launch
    pieces, t = {}, iter([3.0, 3.5, 4.75])
    clock = lambda: next(t)                                         # noqa: E731
    since = launch._ufc_piece(pieces, "dossier drafts", 1.0, clock=clock)
    assert since == 3.0 and pieces == {"dossier drafts": 2.0}
    since = launch._ufc_piece(pieces, "weigh-ins", since, clock=clock)
    launch._ufc_piece(pieces, "weigh-ins", since, clock=clock)
    assert pieces == {"dossier drafts": 2.0, "weigh-ins": 1.8}, "a piece timed twice adds up"
    assert launch._ufc_piece({}, "x", 10.0, clock=lambda: 9.0) == 9.0


def test_the_loops_work_rides_ahead_of_the_builds_stages_once():
    import launch
    try:
        launch._LAST_BUILD_STAGES[0] = {"dossiers": 0, "card + odds": 4, "journal": 1}
        launch._LAST_BUILD_PARTS[0] = {"card + odds": {"events list": 0.3}}
        launch._ufc_before_the_build({"dossier drafts": 2.4, "weigh-ins": 6.1, "the pacer": 0.1})
        launch._note_board("zz_test_ufc", True)
        run = launch._BOARD_RUNS["zz_test_ufc"]
        assert list(run["stages"]) == ["before the build", "dossiers", "card + odds", "journal"], run
        assert run["stages"]["before the build"] == 9
        assert run["parts"] == {"before the build": {"dossier drafts": 2.4, "weigh-ins": 6.1, "the pacer": 0.1},
                                "card + odds": {"events list": 0.3}}, run
        launch._note_board("zz_test_ufc", True)
        assert "stages" not in launch._BOARD_RUNS["zz_test_ufc"], "taken once"
        # A build that printed no stage clock still gets the loop's own.
        launch._LAST_BUILD_STAGES[0], launch._LAST_BUILD_PARTS[0] = {}, {}
        launch._ufc_before_the_build({"fight history": 1.0})
        assert launch._LAST_BUILD_STAGES[0] == {"before the build": 1}
        launch._ufc_before_the_build({})
        assert launch._LAST_BUILD_STAGES[0] == {"before the build": 1}, "nothing timed adds nothing"
    finally:
        launch._LAST_BUILD_STAGES[0], launch._LAST_BUILD_PARTS[0] = {}, {}
        launch._BOARD_RUNS.pop("zz_test_ufc", None)


def test_refresh_ufc_times_its_five_pieces_and_still_builds_the_same_way():
    import launch
    names = ("_auto_dossiers", "_auto_weighins", "_auto_fight_history", "_ufc_card", "_odds_affordable",
             "_paid_pull_baseline", "_with_odds", "_run_build", "_finish_paid_pull")
    keep = {n: getattr(launch, n) for n in names}
    called, built = [], []

    def run_build(args):
        built.append(list(args))
        launch._LAST_BUILD_STAGES[0] = {"dossiers": 0, "journal": 1}
        launch._LAST_BUILD_PARTS[0] = {}
        return True, "UFC: no_card. Wrote web/data/ufc.json"

    try:
        launch._auto_dossiers = lambda quiet=False: called.append("dossiers")
        launch._auto_weighins = lambda quiet=False: called.append("weigh-ins")
        launch._auto_fight_history = lambda quiet=False: called.append("history")
        launch._ufc_card = lambda cache_only=False: []
        launch._odds_affordable = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no card, no pacer"))
        launch._paid_pull_baseline = lambda: (_ for _ in ()).throw(AssertionError("nothing to buy"))
        launch._with_odds = lambda: True
        launch._run_build = run_build
        launch._finish_paid_pull = lambda *a, **k: None
        assert launch.refresh_ufc(quiet=True) is True
        assert called == ["dossiers", "weigh-ins", "history"]
        assert built == [["ufc_build.py", "--out", launch.UFC_OUT, "--cached-odds"]], built
        stages, parts = launch._LAST_BUILD_STAGES[0], launch._LAST_BUILD_PARTS[0]
        assert list(stages) == ["before the build", "dossiers", "journal"], stages
        assert list(parts["before the build"]) == BEFORE, parts
        assert all(v >= 0 for v in parts["before the build"].values())
    finally:
        for n, f in keep.items():
            setattr(launch, n, f)
        launch._LAST_BUILD_STAGES[0], launch._LAST_BUILD_PARTS[0] = {}, {}


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
