"""Who steps up, for college football's reports (step AEK, 24 November 2026; rivalry week).

The NFL's reports say where an absent receiver's or back's work goes (engine/stepup, step AEC). College's props
already take a measured teammate-out step (engine/cfb/lineup, since 10 October), and the report never said it.
College box scores log catches, not targets, and no positions, so the block says what the logs hold and claims no
graded read:

  * who is out and his share of the team's catches (a receiver or tight end) or carries (a back), counted while he
    played in one of the team's last three games;
  * in this season's games where he has no catch or carry on record, who took them: each man's per game then,
    beside his per game with him, the positions the report's own reads say before the logs' guess;
  * a quarterback is never named for a back's carries;
  * which picks our numbers raise for it (their `mate_card`), "the lift measured on college games";
  * the season's games are the lineup step's own read, left on the board's working key, which is never published.

Offline. Run directly: `python3 tests/test_who_steps_up_in_college.py`
"""
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import stepup as S                                       # noqa: E402

DAYS = ["2026-09-06", "2026-09-13", "2026-09-20", "2026-09-27", "2026-10-04", "2026-10-11", "2026-10-18",
        "2026-10-25", "2026-11-01", "2026-11-08", "2026-11-15"]
MISSED = {"2026-10-18", "2026-11-08"}


def _indiana():
    """Eleven games; the top receiver missed two; the tight end's log guess is a receiver."""
    def games(per_day):
        return {d: v for d, v in ((d, per_day(d)) for d in DAYS) if v is not None}
    top = games(lambda d: None if d in MISSED else {"receptions": 6.0, "rec_yds": 80.0})
    two = games(lambda d: {"receptions": 7.0 if d in MISSED else 4.0, "rec_yds": 90.0 if d in MISSED else 50.0})
    te = games(lambda d: {"receptions": 5.0 if d in MISSED else 3.0, "rec_yds": 40.0 if d in MISSED else 25.0})
    back = games(lambda d: {"rush_att": 15.0, "rush_yds": 70.0, "receptions": 1.0, "rec_yds": 6.0})
    qb = games(lambda d: {"pass_att": 30.0, "rush_att": 8.0, "rush_yds": 35.0})
    return {"Elijah Sarratt": {"role": "WR", "games": top},
            "Omar Cooper Jr.": {"role": "WR", "games": two},
            "Riley Nowakowski": {"role": "WR", "games": te},
            "Roman Hemby": {"role": "RB", "games": back},
            "Fernando Mendoza": {"role": "QB", "games": qb}}


def _rows():
    return [{"player": "Omar Cooper Jr.", "team": "IND", "market": "receptions",
             "mate_card": {"applied": 1.12, "out": ["Elijah Sarratt"], "case": "above|new"}},
            {"player": "Omar Cooper Jr.", "team": "IND", "market": "rec_yds",
             "mate_card": {"applied": 1.09, "out": ["Elijah Sarratt"], "case": "above|new"}},
            {"player": "Roman Hemby", "team": "IND", "market": "rush_yds", "mate_card": {"applied": 1.0}}]


OUT = [("Elijah Sarratt", "WR", "Out")]


def test_the_report_says_who_took_the_catches_in_the_games_without_him():
    got = S.for_cfb_team(_indiana(), DAYS, "IND", "Indiana", OUT, _rows(), before="2026-11-22",
                         positions={S._key("Riley Nowakowski"): "TE"}, season=2026)
    lines = [t for t, _cl in got["lines"]]
    # His 6 catches a game of the team's 14 in the nine games he played.
    assert lines[0] == "Indiana without Elijah Sarratt (WR, 43% of the catches): 43% of the catches this season to fill", lines
    assert lines[1] == ("In the 2 games this season that player had no catch or carry on record (Oct. 18 and Nov. 8), "
                        "the catches went to: Omar Cooper Jr. (WR) 7 catches a game (4 a game with that player), 90 "
                        "yards a game; Riley Nowakowski (TE) 5 catches a game (3 a game with that player), 40 yards a "
                        "game"), lines[1]
    assert lines[2] == ("Our numbers raise Omar Cooper Jr.'s receiving yards by 9% and catches by 12%, the lift we "
                        "measured on college games when a teammate ranked higher at the same position is out"), lines[2]
    assert all(cl is None for _t, cl in got["lines"]), "no graded read is claimed for college"
    assert got["outs"] == ["Elijah Sarratt"] and got["vacated"] == {"catches": 0.429}


def test_a_back_out_leaves_his_carries_and_a_quarterback_is_never_named_for_them():
    players = _indiana()
    players["Roman Hemby"]["games"] = {d: g for d, g in players["Roman Hemby"]["games"].items() if d not in MISSED}
    players["Kaelon Black"] = {"role": "RB", "games": {d: {"rush_att": 14.0 if d in MISSED else 5.0,
                                                           "rush_yds": 66.0 if d in MISSED else 20.0} for d in DAYS}}
    got = S.for_cfb_team(players, DAYS, "IND", "Indiana", [("Roman Hemby", "RB", "Out")], [], before="2026-11-22")
    text = " ".join(t for t, _ in got["lines"])
    assert "Roman Hemby (RB" in text and "of the carries" in text and "Kaelon Black (RB) 14 carries a game" in text, text
    assert "Fernando Mendoza" not in text, "a quarterback's carries are his own, never a back's to fill"


def test_no_block_without_a_fresh_absence_and_a_never_missed_man_is_said_so():
    players = _indiana()
    # Gone since September: his work is in his teammates' own form already.
    players["Elijah Sarratt"]["games"] = {d: g for d, g in players["Elijah Sarratt"]["games"].items() if d < "2026-10-01"}
    assert S.for_cfb_team(players, DAYS, "IND", "Indiana", OUT, [], before="2026-11-22") is None
    full = _indiana()
    full["Elijah Sarratt"]["games"] = {d: {"receptions": 6.0} for d in DAYS}
    got = S.for_cfb_team(full, DAYS, "IND", "Indiana", OUT, [], before="2026-11-22")
    assert [t for t, _ in got["lines"]][1].startswith("That player has a catch or carry on record in every game"), got
    assert S.for_cfb_team({}, DAYS, "IND", "Indiana", OUT) is None and S.for_cfb_team(_indiana(), [], "IND", "x", OUT) is None
    small = _indiana()
    assert S.for_cfb_team(small, DAYS, "IND", "Indiana", [("Fernando Mendoza", "QB", "Out")], []) is None, \
        "a quarterback's absence is the QB-change step's, not this block's"


def _ctx(result, injuries):
    return types.SimpleNamespace(
        sport="cfb", conn=None, season=2026, teams=("OSU", "IND"), name=lambda t: {"OSU": "Ohio State", "IND": "Indiana"}[t],
        g={"date": "2026-11-28"}, reads=[{"player": "Riley Nowakowski", "pos": "TE", "team": "IND"}],
        scan={"injuries": injuries}, result=result)


def test_the_college_report_reads_the_lineup_steps_season_off_the_board():
    held = {"players": {"IND": _indiana()}, "team_days": {"IND": DAYS}}
    inj = [{"player": "Elijah Sarratt", "position": "WR", "status": "OUT", "team": "IND"},
           {"player": "Jeremiah Smith", "position": "WR", "status": "QUESTIONABLE", "team": "OSU"}]
    blocks = S.report_blocks(_ctx({S.CFB_GAMES_KEY: held, "recommendations": _rows()}, inj))
    assert blocks[0] == {"type": "h", "text": "Who steps up"} and len(blocks) == 2, blocks
    assert blocks[1]["items"][0].startswith("Indiana without Elijah Sarratt (WR, 43% of the catches)")
    assert "Riley Nowakowski (TE)" in blocks[1]["items"][1], "the reads' position over the logs' guess"
    assert "claims" not in blocks[1], "nothing graded for college"
    assert S.report_blocks(_ctx({"recommendations": _rows()}, inj)) == [], "without the season read, nothing"
    report = {"sections": [{"key": "injuries", "blocks": blocks}]}
    assert S.census([report], {"recommendations": _rows()}) == {"teams": 1, "reads": 0, "moved": 2}


def test_the_build_leaves_the_season_read_on_a_key_the_board_never_publishes():
    src = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    assert "out[_su_key] = {\"players\": _su_players, \"team_days\": _su_days}" in src
    assert S.CFB_GAMES_KEY.startswith("_"), "a working key: engine/gate drops it before any copy is written"
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'su = _stepup.census(reports, result) if sport in ("nfl", "cfb") else {}' in gr


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
