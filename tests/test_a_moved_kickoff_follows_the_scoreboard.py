"""A game the NFL moved takes ESPN's scoreboard's time, before anything is timed off it (step ACF, 22 November 2026).

The Sunday's board had the Steelers at the Eagles at 4:25 PM and the Jaguars at the Giants at 1 PM; ESPN's
scoreboard had them the other way round. The Steelers' game was in its first quarter while the board held its
picks to post at 3:10 PM and read the two clubs' inactives as a list for a later game. What these hold:

  * a game the scoreboard lists 10 minutes or more from the schedule's time, on the same Eastern day, takes the
    scoreboard's time (its old one kept), in the schedule's own form;
  * a time to be decided (midnight Eastern) and a move to another day are left alone, and said;
  * the NFL build reads the scoreboard's times as it reads the schedule, with the live layer, before the forecast,
    the inactives' window and the picks' post time read the kickoff; the live overlay corrects it too.

    python3 tests/test_a_moved_kickoff_follows_the_scoreboard.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.sources import livescores as L                     # noqa: E402


def _game(away, home, kickoff, date="2026-11-22"):
    return types.SimpleNamespace(away=away, home=home, kickoff=kickoff, date=date, live=None)


def _live(start):
    return types.SimpleNamespace(start_time=start, state="live")


def test_a_moved_game_takes_the_scoreboards_time():
    pit = _game("PIT", "PHI", "16:25")
    assert L.kickoff_from_scoreboard(pit, _live("2026-11-22T18:00Z")) == "PIT@PHI 16:25 -> 13:00"
    assert (pit.kickoff, pit.date, pit.kickoff_moved) == ("13:00", "2026-11-22", "16:25")
    jax = _game("JAX", "NYG", "13:00")
    assert L.kickoff_from_scoreboard(jax, _live("2026-11-22T21:25Z")) == "JAX@NYG 13:00 -> 16:25"
    assert jax.kickoff == "16:25"
    # A Sunday night game: 20:20 Eastern is the next day in UTC, and it is the same game at the same time.
    snf = _game("MIN", "SF", "20:20")
    assert L.kickoff_from_scoreboard(snf, _live("2026-11-23T01:20Z")) == "" and snf.kickoff == "20:20"
    near = _game("NYJ", "LAC", "16:05")
    assert L.kickoff_from_scoreboard(near, _live("2026-11-22T21:10Z")) == "", "five minutes is the same kickoff"
    iso = _game("A", "B", "2026-11-22T21:25:00Z")
    assert L.kickoff_from_scoreboard(iso, _live("2026-11-22T18:00Z")) == "A@B 16:25 -> 13:00"
    assert iso.kickoff == "2026-11-22T18:00:00Z", "the schedule's own form"


def test_a_time_to_be_decided_or_another_day_is_left_alone():
    tbd = _game("LV", "DEN", "16:25")
    said = L.kickoff_from_scoreboard(tbd, _live("2026-11-22T05:00Z"))
    assert "to be decided" in said and tbd.kickoff == "16:25"
    moved_day = _game("LV", "DEN", "16:25")
    said = L.kickoff_from_scoreboard(moved_day, _live("2026-11-23T18:00Z"))
    assert "2026-11-23" in said and moved_day.kickoff == "16:25" and moved_day.date == "2026-11-22"
    assert L.kickoff_from_scoreboard(_game("A", "B", ""), _live("2026-11-22T18:00Z")) == "", "no schedule time"
    assert L.kickoff_from_scoreboard(_game("A", "B", "13:00"), _live("")) == "", "no scoreboard time"


def test_the_scoreboards_games_are_matched_as_the_overlay_matches_them():
    was = L.fetch_live
    board = {frozenset(("PIT", "PHI")): _live("2026-11-22T18:00Z"),
             frozenset(("JAX", "NYG")): _live("2026-11-22T21:25Z"),
             frozenset(("DAL", "NYG")): _live("2026-12-20T18:00Z")}
    L.fetch_live = lambda: board
    try:
        games = [_game("PIT", "PHI", "16:25"), _game("JAX", "NYG", "13:00"), _game("KC", "ARI", "13:00")]
        assert L.kickoffs_from_scoreboard(games) == ["PIT@PHI 16:25 -> 13:00", "JAX@NYG 13:00 -> 16:25"]
        assert L.kickoffs_from_scoreboard(games) == [], "said once: moved, the times agree"
        late = _game("PIT", "PHI", "16:25")
        assert L.attach_live(types.SimpleNamespace(games=[late])) == 1 and late.kickoff == "13:00", \
            "the live overlay corrects it too"
        far = _game("NYG", "DAL", "13:00", date="2026-09-13")
        assert L.kickoffs_from_scoreboard([far]) == [] and far.kickoff == "13:00", "another week's meeting"

        def down():
            raise L.DataUnavailable("refused")
        L.fetch_live = down
        assert L.kickoffs_from_scoreboard(games) == []
    finally:
        L.fetch_live = was


def test_the_build_reads_them_before_anything_is_timed_off_the_kickoff():
    src = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    body = src[src.index("def show_games("):src.index("\ndef ", src.index("def show_games(") + 10)]
    assert "for said in kickoffs_from_scoreboard(games):" in body
    assert body.index("kickoffs_from_scoreboard(games)") < body.index("nflwx.attach(games)"), "before the forecast"
    assert "games = show_games(args.season, args.week, scoreboard=bool(args.live))" in src
    assert src.index("scoreboard=bool(args.live)") < src.index("_inactives = injuries_feed.inactives_posted(")
    lv = (ROOT / "engine" / "sources" / "livescores.py").read_text(encoding="utf-8")
    assert "            g.live = live\n            # …and its kickoff, where the schedule's is wrong (step ACF).\n" \
           "            kickoff_from_scoreboard(g, live)\n" in lv


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
