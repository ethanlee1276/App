"""The Live tab keeps a night's games until 5 AM, and a finished bet leaves the list.

Ethan, 2026-09-24, 12:13 AM, from the MLB Live tab — Padres 4-1 Dodgers in
the top of the 6th on two open bets, and above them "No MLB games in
progress right now": "mlbs bets will show they are live but the games
won't show up on the live tab. Also bets will still be on the live page
even when the game is over."

Two causes. The board, the tracker and the journal have rolled at 5 AM
Eastern since 2026-09-01 (launch._slate_date), but the live scoreboard
(live_build.py) and the per-bet sweat (engine/sweat.py) read
`date.today()` — Eastern midnight on the droplet — so from 12 to 5 they
fetched the next day's schedule: nothing live, and no final ever reaching
a bet on a game that had ended. One rule now (engine/slateday). And a bet
whose game has finished drops out of the Live list into one closed line
under it, waiting on the official result.
"""
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.slateday import baseball_day, ROLL_HOUR                 # noqa: E402


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def test_the_night_runs_until_five():
    assert ROLL_HOUR == 5
    assert baseball_day(dt.datetime(2026, 9, 23, 22, 10)) == "2026-09-23"
    assert baseball_day(dt.datetime(2026, 9, 24, 0, 13)) == "2026-09-23", "Padres-Dodgers, top of the 6th"
    assert baseball_day(dt.datetime(2026, 9, 24, 4, 59)) == "2026-09-23"
    assert baseball_day(dt.datetime(2026, 9, 24, 5, 0)) == "2026-09-24"


def test_the_scoreboard_the_sweat_and_the_board_read_the_same_day():
    assert "date = args.date or baseball_day()" in _src("live_build.py")
    assert "_dt.date.today()" not in _src("live_build.py")
    sweat = _src("engine", "sweat.py")
    assert "day = today or baseball_day()" in sweat and "_dt.date.today()" not in sweat
    launch = _src("launch.py")
    body = launch[launch.index("def _slate_date()"):launch.index("def refresh_mlb(")]
    assert 'return baseball_day(_dt.datetime.now(ZoneInfo("America/New_York")))' in body


def test_the_scoreboard_asks_for_the_night_being_played():
    import live_build
    seen = {}
    saved = (live_build.build, sys.argv)
    live_build.build = lambda date, pbp_dir=None: seen.setdefault("date", date) and {
        "generated_at": "x", "date": date, "games": []}
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "live_mlb.json")
    sys.argv = ["live_build.py", "--out", out]
    import engine.slateday as SD
    real = SD.baseball_day
    SD.baseball_day = lambda now=None: "2026-09-23"
    import engine.sweat as SW
    real_sweat = SW.build
    SW.build = lambda **k: None
    try:
        try:
            live_build.main()
        except Exception:                                   # noqa: BLE001
            pass                                            # the write after build is not the point
    finally:
        live_build.build, sys.argv = saved
        SD.baseball_day = real
        SW.build = real_sweat
    assert seen.get("date") == "2026-09-23", seen


def test_a_finished_bet_leaves_the_live_list():
    app = _src("web", "js", "app.js")
    body = app[app.index("function renderLivePicks()"):app.index("function renderTeamForm()")]
    assert 'const active = list.filter((r) => r.phase !== "final");' in body
    assert 'const done = list.filter((r) => r.phase === "final");' in body
    assert "active.map(rowHTML)" in body and "list.map(rowHTML)" not in body
    assert '<details class="lv-done"><summary>${done.length} finished — waiting on' in body
    assert 'const n = active.filter((r) => r.phase === "live").length;' in body, "the live dot counts live bets only"
    css = _src("web", "css", "styles.css")
    assert ".lv-done > summary" in css and ".lv-done-note" in css


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
