"""An NFL game's picks and parlays wait for both teams' inactives (step ACB, 22 November 2026).

Ethan, the Sunday: "we need to be having that information on hand and using that data to our advantage". The
inactives come out 90 minutes before kickoff and ESPN's board files them a club at a time: on the Sunday, a club's
first inactive 1 to 14 minutes after 11:30 AM ET, its last up to 21 minutes after, Carolina's none by noon, and the
board the builds read is up to ten minutes old. The 1 PM games' picks posted at 11:45 AM, 75 minutes before, before
most clubs' lists were on the board. What these hold:

  * an NFL game posts at 75 minutes only once both clubs' lists are on the board (the NFL build's
    ``inactives_in``); until then it waits, and it posts the first build after they are, or 50 minutes before its
    start, whichever comes first;
  * waiting, its report and its parlays say so, with the latest time they post (in the reader's zone);
  * a board that does not say (another league, or a build that could not read ESPN's board) posts as before;
  * the NFL build writes whose lists are in only when it read the board.

    python3 tests/test_an_nfl_games_picks_wait_for_its_inactives.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, gamereport as GR          # noqa: E402

START = dt.datetime(2026, 11, 22, 18, 0, tzinfo=dt.timezone.utc)   # 1 PM ET
G = {"home": "DET", "away": "TB", "date": "2026-11-22", "kickoff": "13:00"}


def _at(minutes_before):
    return START - dt.timedelta(minutes=minutes_before)


def test_whose_lists_are_in():
    assert GP.inactives_ready({"inactives_in": ["DET", "TB", "BAL"]}, G, "nfl") is True
    assert GP.inactives_ready({"inactives_in": ["DET"]}, G, "nfl") is False
    assert GP.inactives_ready({}, G, "nfl") is None, "the board does not say: as before"
    assert GP.inactives_ready({"inactives_in": []}, G, "nba") is None, "another league: as before"


def test_it_posts_once_both_are_in_or_at_the_deadline():
    for minutes, ready, want in ((80, False, (False, _at(75), False)),       # not yet its time
                                 (70, False, (False, _at(50), True)),        # its time, the lists not in: waits
                                 (70, True, (True, _at(75), False)),         # both in: posts
                                 (70, None, (True, _at(75), False)),         # the board does not say: posts
                                 (49, False, (True, _at(75), False))):       # past the deadline: posts
        assert GP.post_due(START, "nfl", _at(minutes), ready) == want, (minutes, ready)
    assert GP.post_due(START, "nba", _at(80), False)[0] is True, "another league never waits"
    assert GP.POST_DEADLINE_MIN == 50 and GP.POST_WAIT_SPORTS == ("nfl",)


def test_waiting_the_report_and_its_parlays_say_so():
    w = GR.picks_wait("nfl", G, now=_at(70), ready=False)
    assert w["post_at"] == "2026-11-22T17:10:00Z"
    assert w["text"].startswith("Our picks for this game post once both teams' inactives are in, at Sun 12:10 PM ET "
                                "at the latest"), w["text"]
    assert GR.picks_wait("nfl", G, now=_at(70), ready=True) is None
    assert "about 75 minutes before the start" in GR.picks_wait("nfl", G, now=_at(80), ready=False)["text"]
    x = dict(G, threes=[{"legs": []}], twos=[{"legs": []}])
    assert GP.hold_until_post(x, "nfl", now=_at(70), ready=False) == "2026-11-22T17:10:00Z"
    assert x["threes"] == [] and x["post_note"].startswith("This game's parlays post once both teams' inactives are in")
    y = dict(G, threes=[{"legs": []}])
    assert GP.hold_until_post(y, "nfl", now=_at(70), ready=True) is None and y["threes"], "both in: it posts"


def test_the_callers_ask_and_the_build_says_whose_lists_are_in():
    gp = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert "hold_until_post(x, sp, now, ready=inactives_ready(board, x, sp))" in gp
    assert "and hold_until_post(x, sp, now, ready=inactives_ready(board, x, sp)))" in gp
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'ready=_ready(getattr(c, "result", None), c.g, getattr(c, "sport", "")))' in gr
    nb = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert 'if locals().get("_inactives_read"):' in nb and "result[_iik] = sorted(locals().get(\"_inactives\") or {})" in nb
    assert nb.index("_inactives_read = True") < nb.index('if locals().get("_inactives_read"):')


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
