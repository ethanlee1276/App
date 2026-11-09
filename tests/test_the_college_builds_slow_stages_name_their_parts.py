"""The college build's slow stages name their parts on the heartbeat
(engine/stageclock.lap; cfb_build.main and _write; engine/cfb/props.build_slate).

The heartbeat at 07:51 on 9 November had the college build at 110 seconds,
and four of its stages, 92 of those seconds, with no parts: "injuries +
lineup + prop pricing" 40, "pick of the day + crowd + parlays" 22, "long
shots + Most Likely board" 18 and "opponent-adjusted ratings + game lines"
12. A stage's one number cannot say which of its steps took the time.
What these hold:

  * each of the four stages laps its steps under its own name, in the
    order the build runs them, and no lap names a stage it is not inside
    (the pricing stage's last two steps live in ``_write``, the door every
    exit of the build goes out through, before its mark);
  * the college slate (the pricing stage's first step) says each of its
    reads under its own name, so its parts are never added into the
    stage's, prints nothing outside a build, and builds the same props
    with the clock running or not.

Run directly: `python3 tests/test_the_college_builds_slow_stages_name_their_parts.py`
"""
import contextlib
import io
import os
import random
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import stageclock                                       # noqa: E402

CFB_STAGE_PARTS = {
    "opponent-adjusted ratings + game lines": [
        "this season adjusted", "every season adjusted", "rating fit", "talent", "status + QB read",
        "weather", "games + lines"],
    "injuries + lineup + prop pricing": [
        "injuries", "slate", "book lines", "prop tape", "lineup", "pricing"],
    "long shots + Most Likely board": [
        "touchdown board", "QB changes", "first touchdown", "matchup scan", "most likely",
        "scenarios + matchup picks", "board + game plan", "quote journal"],
    "pick of the day + crowd + parlays": [
        "tracker", "exchange fair", "crowd", "openers", "game reports", "pick of the day", "comps",
        "parlays"],
}
FIRST_STAGE = "history + team ratings"
SLATE_PARTS = ["defense ratings", "usage", "log rows", "rosters", "faces", "props"]


class _Stopped:
    """The stage clock as a process that never started it (the backtest)."""

    def __enter__(self):
        self.keep = dict(stageclock._STATE)
        stageclock._STATE.update(t0=None, last=None)

    def __exit__(self, *exc):
        stageclock._STATE.clear()
        stageclock._STATE.update(self.keep)


def test_each_slow_stage_names_its_parts_under_its_own_mark():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    marks = [(m.start(), m.group(1)) for m in re.finditer(r'_clock\.mark\("([^"]+)"\)', src)]
    for stage, want in CFB_STAGE_PARTS.items():
        at = [k for k, (_pos, name) in enumerate(marks) if name == stage]
        assert len(at) == 1 and at[0] > 0, stage
        seg = src[marks[at[0] - 1][0]:marks[at[0]][0]]
        laps = re.findall(r'_clock\.lap\("([^"]+)", "([^"]+)"', seg)
        assert {st for st, _p in laps} == {stage}, ("each lap under the stage that holds it", stage, laps)
        assert [p for _st, p in laps] == want, (stage, laps)
    every = re.findall(r'_clock\.lap\("([^"]+)", "([^"]+)"', src)
    others = [(st, p) for st, p in every if st != FIRST_STAGE]
    assert sorted(others) == sorted((st, p) for st, ps in CFB_STAGE_PARTS.items() for p in ps), \
        "no lap outside the stages listed"


def test_the_write_door_laps_its_two_steps_before_its_mark():
    """Every exit of the build goes out through `_write`, so its two steps
    are timed there, after the clock it reads is imported."""
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    body = src[src.index("def _write("):]
    body = body[:body.index("\ndef ", 1)] if "\ndef " in body[1:] else body
    imp = body.index("from engine import stageclock as _clock")
    comps = body.index('"pick of the day + crowd + parlays", "comps"')
    parlays = body.index('"pick of the day + crowd + parlays", "parlays"')
    mark = body.index('_clock.mark("pick of the day + crowd + parlays")')
    assert imp < comps < parlays < mark


#: (name, filed team, position, markets), as tests/test_cfb_props.py files them.
ROSTER = [
    ("Carson Beck", "UGA", "QB", ("pass_yds", "pass_att", "pass_cmp", "pass_int")),
    ("Nate Frazier", "UGA", "RB", ("rush_yds", "carries", "rush_att")),
    ("Arian Smith", "UGA", "WR", ("rec_yds", "receptions")),
    ("Will Howard", "OSU", "QB", ("pass_yds", "pass_att", "pass_cmp", "pass_int")),
    ("Quinshon Judkins", "OSU", "RB", ("rush_yds", "carries", "rush_att")),
    ("Emeka Egbuka", "OSU", "WR", ("rec_yds", "receptions")),
]
MEANS = {"pass_yds": 250.0, "rush_yds": 70.0, "rec_yds": 60.0, "receptions": 4.0, "carries": 12.0,
         "pass_att": 32.0, "pass_cmp": 21.0, "rush_att": 12.0, "pass_int": 0.8}
GAMES = [{"game_id": "401", "home": "UGA", "away": "OSU", "home_name": "Georgia",
          "away_name": "Ohio State", "date": "2026-09-05", "kickoff": "2026-09-05T23:30Z",
          "spread": -3.5, "total": 52.5,
          "weather": {"dome": False, "temp_f": 78.0, "wind_mph": 7.0, "wind_dir": "NW"},
          "weather_checked": True}]


def _conn():
    from engine import db
    d = tempfile.mkdtemp(prefix="cfb-slate-parts-")
    conn = db.connect(os.path.join(d, "history.db"))
    rnd = random.Random(3)
    rows = []
    for name, team, pos, markets in ROSTER:
        for g in range(10):
            for m in markets:
                rows.append({"sport": "cfb", "season": 2025, "period": f"2025-09-{g + 1:02d}",
                             "game_id": f"{team}-{g}", "player": name, "team": team, "opponent": "XXX",
                             "position": pos, "home": g % 2, "market": m,
                             "value": max(0.0, rnd.gauss(MEANS[m], MEANS[m] * 0.3))})
    db.upsert_player_logs(conn, rows)
    return conn


def _slate_once(conn):
    from engine.cfb import props as P
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        slate = P.build_slate(conn, GAMES, "2026-09-05", 2025, census={}, current={})
    return slate, buf.getvalue().splitlines()


def _shape(slate):
    return [(p.player, p.team, p.opponent, p.market, p.position, round(p.lines[0].line, 3),
             [round(g.value, 3) for g in p.logs]) for p in slate.props]


def test_the_college_slate_names_its_reads_only_inside_a_build_and_builds_the_same():
    conn = _conn()
    with _Stopped():
        quiet, quiet_lines = _slate_once(conn)
        stageclock.start()
        timed, timed_lines = _slate_once(conn)
    assert quiet.props, "the fixture builds props"
    assert not stageclock.parse_parts(quiet_lines), "a slate outside a build prints no part"
    parts = stageclock.parse_parts(timed_lines)
    assert list(parts) == ["college slate"], "its own group: never added into the stage's parts"
    assert list(parts["college slate"]) == SLATE_PARTS, list(parts["college slate"])
    assert not stageclock.parse(timed_lines), "a part is never a stage"
    assert _shape(quiet) == _shape(timed), "the clock changes no prop"


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
