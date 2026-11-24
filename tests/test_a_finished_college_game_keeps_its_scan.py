"""A finished college basketball game keeps its Matchup scan and the board keeps its Team shapes, as the NBA's do.

24 November 2026, 00:18 Eastern: the college basketball board still carried Monday's 46 games and not one Matchup scan
tape, player read or Team shapes radar. Its slate section, where all three are made, runs only while a game the board
prices is still to tip (`college_board_games`), so once the last game tipped every finished college game page lost its
scan and its radar, while the NBA's finished games, whose slate is never narrowed, kept theirs. All three are pregame
things: a build that made none keeps the last board's, from the private copy, for the same slate only, never over
anything the build made itself (nba_build.keep_pregame).

Offline. Run directly: `python3 tests/test_a_finished_college_game_keeps_its_scan.py`
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

import nba_build                                                    # noqa: E402

TAPE = {"rows": [{"label": "Points a game", "a": "80.1", "h": "77.4"}], "sides": {"VCU": {}, "PROV": {}}}
PREV = {"date": "2026-11-23",
        "games": [{"away": "VCU", "home": "PROV", "nba_tape": TAPE}, {"away": "WIN", "home": "ILL"},
                  {"away": "DEN", "home": "KU", "nba_tape": {"rows": ["old"]}}],
        "scan_reads": {"VCU@PROV": {"players": [{"player": "A"}]}},
        "team_shapes": {"VCU": {"pct": {"offense": 70.0}}}, "team_shapes_season": 2026}


def _prev(doc):
    path = Path(tempfile.mkdtemp()) / "a_board_of_our_own.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_the_last_boards_scan_and_shapes_stand_past_the_last_tip():
    path = _prev(PREV)
    out = {"games": [{"away": "VCU", "home": "PROV"}, {"away": "WIN", "home": "ILL"},
                     {"away": "DEN", "home": "KU", "nba_tape": {"rows": ["this build's"]}}]}
    said = nba_build.keep_pregame(out, path, "2026-11-23")
    assert out["games"][0]["nba_tape"] == TAPE
    assert "nba_tape" not in out["games"][1], "the last board had none for it"
    assert out["games"][2]["nba_tape"] == {"rows": ["this build's"]}, "never over this build's own"
    assert out["scan_reads"] == {"VCU@PROV": {"players": [{"player": "A"}]}}, "the paid reads ride with their tape"
    assert out["team_shapes"] == PREV["team_shapes"] and out["team_shapes_season"] == 2026
    assert said == "Kept from the last board: 1 started game(s)' pregame scan and the team shapes", said


def test_another_slate_or_a_build_that_made_its_own_keeps_nothing():
    path = _prev(PREV)
    out = {"games": [{"away": "VCU", "home": "PROV"}]}
    assert nba_build.keep_pregame(out, path, "2026-11-24") == "" and "nba_tape" not in out["games"][0]
    own = {"games": [], "team_shapes": {"KU": {}}, "team_shapes_season": 2026}
    nba_build.keep_pregame(own, path, "2026-11-23")
    assert own["team_shapes"] == {"KU": {}}, "this build's shapes stand"
    assert nba_build.keep_pregame({"games": []}, Path(tempfile.mkdtemp()) / "none.json", "2026-11-23") == ""


def test_the_build_keeps_them_for_every_slate_not_only_one_with_games_to_tip():
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    i = src.index("    _kept_pre = keep_pregame(out, args.out, args.date)\n")
    assert src.index("    print(_lo.attach_to_board(out, args.league))\n") < i < src.index(
        "    print(f\"  {_lgr.attach(out, args.league, meta=_gr_meta, out=args.out)}\")"), \
        "at the main level, after the opening lines and before the game report"


def test_the_nights_most_likely_board_stands_past_the_last_tip():
    """After the last tip the build makes no Most Likely board (no `likely_census`); the last one's stands, for the
    same slate, and the page then says the picks are under way or decided (app.js boardBegun, step ADY)."""
    prev = dict(PREV, most_likely=[{"player": "A"}], likely_board={"rows": [{"player": "A"}]},
                board_shelves=[{"key": "top", "rows": [{"player": "A"}]}], likely_census={"under the floor": 3})
    path = _prev(prev)
    out = {"games": [], "most_likely": [], "board_shelves": []}
    said = nba_build.keep_likely(out, path, "2026-11-23")
    assert out["most_likely"] == [{"player": "A"}] and out["likely_board"] == prev["likely_board"]
    assert out["board_shelves"] == prev["board_shelves"] and out["likely_census"] == {"under the floor": 3}
    assert said == "Kept from the last board: the night's Most Likely board (1 pick(s))", said
    made = {"most_likely": [{"player": "B"}], "likely_census": {}}
    assert nba_build.keep_likely(made, path, "2026-11-23") == "" and made["most_likely"] == [{"player": "B"}], \
        "a build that made its board keeps its own"
    assert nba_build.keep_likely({"most_likely": []}, path, "2026-11-24") == "", "another slate's never"
    src = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    i = src.index("    _kept_ml = keep_likely(out, args.out, args.date)\n")
    assert src.index("out[\"pick_of_the_day\"] = _led.relock_potd(") < i < src.index("    gate.publish(out, p)\n"), \
        "after the Pick of the Day and its relock, just before the publish"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
