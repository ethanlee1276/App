"""What changed: every game report keeps what moved since it was first written (engine/reportlog).

Ethan, 2026-10-20: "I want you too do all of it besides D" — the "what
changed" log among it. A report read on Sunday was written on Tuesday;
the report is rebuilt every build, so this keeps what moved in between:

  * one snapshot a game — the spread and total, kickoff, the simulator,
    the injury report, pulled props, the forecast, the key players'
    reads, how the listed players practised, a quarterback change — kept
    beside the build's PRIVATE board, never in the public tree;
  * a change only when a reader would call it one (half a point on a
    line, five points on the simulator, 5°F / 5 mph / 20 points of rain
    on the forecast), and slow drift adds up rather than vanishing;
  * a fact a build could not read is not a change, so a feed that blinks
    writes nothing;
  * the report's "What changed" section under the short version, newest
    first and stamped Eastern; nothing on a report's first build;
  * Ask reads it, each change with its time.

Run directly: `python3 tests/test_what_changed_on_the_report.py`
"""
import copy
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import askbot                                           # noqa: E402
from engine import db                                               # noqa: E402
from engine import gamereport as R                                  # noqa: E402
from engine import gate                                             # noqa: E402
from engine import reportlog as L                                   # noqa: E402

NFL = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
CFB = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()


def _board(**over):
    g = {"away": "GB", "home": "DET", "date": "2026-10-25", "kickoff": "13:00",
         "spread": -2.5, "total": 48.5, "sim": {"p_home_win": 0.58},
         "weather": {"forecast": True, "dome": False, "temp_f": 51.0, "wind_mph": 6.0,
                     "precip_chance": 0.1, "rain": False, "snow": False},
         "scan": {"injuries": [{"team": "DET", "player": "Amon-Ra St. Brown", "position": "WR",
                                "status": "QUESTIONABLE"}], "pulled": []}}
    g.update(over)
    return {"date": "2026-W8", "built_at": "2026-10-20T09:05:00", "games": [g],
            "qb_changes": [],
            "scan_reads": {"GB@DET": {"players": [
                {"player": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "read": "neutral",
                 "usage": {"carry_share": 0.55}},
                {"player": "Bo Melton", "team": "GB", "pos": "WR", "read": "neutral",
                 "usage": {"tgt_share": 0.03}}]}}}


def _tree():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "web", "data"))
    return d, os.path.join(d, "web", "data", "recommendations.json")


def _attach(board, out, at):
    return R.attach(board, conn=db.connect(":memory:"), ideas={}, out=out, at=at)


def _changes(board):
    rep = board["game_reports"][0]
    keys = [s["key"] for s in rep["sections"]]
    sec = next((s for s in rep["sections"] if s["key"] == "changes"), None)
    return keys, sec


def test_the_first_build_keeps_a_snapshot_beside_the_private_board_and_writes_no_section():
    d, out = _tree()
    board = _board()
    line = _attach(board, out, "2026-10-20T09:05:00")
    keys, sec = _changes(board)
    assert sec is None and "changes" not in keys
    log = L.path_for("nfl", gate._full_dir_for(out))
    assert str(log).startswith(os.path.join(d, "data", "built")), log
    assert not str(log).startswith(os.path.join(d, "web")), "the log of paid reads stays private"
    kept = json.load(open(log))["games"]["GB@DET|2026-10-25"]
    assert kept["first"] == "2026-10-20T09:05:00" and kept["entries"] == []
    assert kept["last"]["spread"] == -2.5 and kept["last"]["injuries"] == {"Amon-Ra St. Brown": "questionable"}
    assert "what changed: 0 game(s) moved since the last build, 1 tracked" in line, line


def test_a_move_is_written_under_its_time_right_under_the_short_version():
    _d, out = _tree()
    _attach(_board(), out, "2026-10-20T09:05:00")
    later = _board(spread=-3.5, total=47.0, sim={"p_home_win": 0.64},
                   weather={"forecast": True, "dome": False, "temp_f": 44.0, "wind_mph": 18.0,
                            "precip_chance": 0.6, "rain": True, "snow": False},
                   scan={"injuries": [{"team": "DET", "player": "Amon-Ra St. Brown", "position": "WR",
                                       "status": "OUT"}], "pulled": ["Amon-Ra St. Brown"]})
    line = _attach(later, out, "2026-10-23T18:40:00")
    keys, sec = _changes(later)
    assert keys[:2] == ["short", "changes"], keys
    assert sec["title"] == "What changed"
    assert sec["blocks"][0] == {"type": "p", "text": "What has moved since we first wrote this report "
                                                     "(Tue 9:05 AM ET), newest first."}
    assert sec["blocks"][1] == {"type": "h", "text": "Fri 6:40 PM ET"}
    items = sec["blocks"][2]["items"]
    for want in ("The spread moved from DET −2.5 to DET −3.5.",
                 "The total moved from 48.5 to 47.",
                 "Our simulator moved DET from 58% to 64% to win.",
                 "Amon-Ra St. Brown (DET WR) is now out; he was questionable.",
                 "Every book took Amon-Ra St. Brown (DET WR)'s props down.",
                 "The forecast moved from 51°F, wind 6 mph, a 10% chance of rain to 44°F, wind 18 mph, "
                 "a 60% chance of rain, rain."):
        assert want in items, (want, items)
    assert "what changed: 1 game(s) moved since the last build" in line, line


def test_newest_first_and_a_quiet_rebuild_adds_nothing():
    _d, out = _tree()
    _attach(_board(), out, "2026-10-20T09:05:00")
    _attach(_board(spread=-3.5), out, "2026-10-21T10:00:00")
    _attach(_board(spread=-3.5), out, "2026-10-21T16:00:00")            # nothing moved
    b = _board(spread=-3.5, total=50.0)
    _attach(b, out, "2026-10-22T12:30:00")
    _keys, sec = _changes(b)
    heads = [x["text"] for x in sec["blocks"] if x["type"] == "h"]
    assert heads == ["Thu 12:30 PM ET", "Wed 10:00 AM ET"], heads


def test_nothing_moved_says_so_in_one_line():
    _d, out = _tree()
    _attach(_board(), out, "2026-10-20T09:05:00")
    b = _board(spread=-2.5, sim={"p_home_win": 0.6})                     # 2 points on the sim: noise
    _attach(b, out, "2026-10-20T15:00:00")
    _keys, sec = _changes(b)
    assert [x["type"] for x in sec["blocks"]] == ["p"]
    assert sec["blocks"][0]["text"].startswith("Nothing has moved since we first wrote this report (Tue 9:05 AM ET)")


def test_slow_drift_adds_up_instead_of_vanishing_a_quarter_point_at_a_time():
    snap = lambda sp, sim: ({"spread": sp, "sim_home": sim}, "DET", "GB")  # noqa: E731
    _d, out = _tree()
    path = os.path.join(_d, "log.json")
    key = "GB@DET|2026-10-25"
    L.update(path, {key: snap(-3.0, 0.55)}, "2026-10-20T09:00:00", today=dt.date(2026, 10, 20))
    r = L.update(path, {key: snap(-3.25, 0.58)}, "2026-10-20T12:00:00", today=dt.date(2026, 10, 20))
    assert r[key]["entries"] == []
    r = L.update(path, {key: snap(-3.5, 0.61)}, "2026-10-20T15:00:00", today=dt.date(2026, 10, 20))
    assert r[key]["entries"] == [{"at": "2026-10-20T15:00:00",
                                  "changes": ["The spread moved from DET −3 to DET −3.5",
                                              "Our simulator moved DET from 55% to 61% to win"]}]


def test_a_fact_the_build_could_not_read_is_not_a_change():
    _d, out = _tree()
    _attach(_board(), out, "2026-10-20T09:05:00")
    blind = _board()
    blind["games"][0].pop("scan")                                       # the scan failed this build
    blind["games"][0]["weather"] = {"forecast": False}                  # and the forecast
    blind.pop("scan_reads")
    _attach(blind, out, "2026-10-20T12:00:00")
    _keys, sec = _changes(blind)
    assert not any(x["type"] == "h" for x in sec["blocks"]), sec        # nothing written
    back = _board()
    _attach(back, out, "2026-10-20T15:00:00")
    _keys, sec = _changes(back)
    assert not any(x["type"] == "h" for x in sec["blocks"]), sec        # and nothing on its return


def test_only_the_key_players_reads_are_logged():
    _d, out = _tree()
    _attach(_board(), out, "2026-10-20T09:05:00")
    b = _board()
    for r in b["scan_reads"]["GB@DET"]["players"]:
        r["read"] = "good"
    _attach(b, out, "2026-10-21T09:05:00")
    _keys, sec = _changes(b)
    items = sec["blocks"][2]["items"]
    assert items == ["The read on Jahmyr Gibbs (DET RB) went from neutral to favorable."], items


def test_practice_kickoff_and_a_quarterback_change():
    old = {"kickoff": "13:00", "practice": {"Amon-Ra St. Brown": "DNP"}, "qb": [],
           "who": {"Amon-Ra St. Brown": "DET"}}
    new = {"kickoff": "16:25", "practice": {"Amon-Ra St. Brown": "Limited"},
           "qb": ["Malik Willis starts for GB (Jordan Love out)"]}
    moved = L.diff(old, new, "DET", "GB")
    assert moved == ["Kickoff moved from 1:00 PM to 4:25 PM ET",
                     "Malik Willis starts for GB (Jordan Love out)",
                     "Amon-Ra St. Brown (DET) was limited in practice, after he did not practice"], moved
    # The practice report's rows (engine/practice.game_view) make the snapshot.
    f = L.facts({"away": "GB", "home": "DET"}, {}, {"practice": {"rows": [
        {"player": "Amon-Ra St. Brown", "team": "DET", "designation": "Questionable", "practice": "Full"},
        {"player": "Someone", "team": "GB", "designation": "Questionable", "practice": None}]}})
    assert f["practice"] == {"Amon-Ra St. Brown": "Full"}


def test_the_first_forecast_and_a_listing_and_a_return():
    old = {"injuries": {"A": "out", "B": "questionable"}, "pulled": ["A"], "who": {"A": "GB WR", "B": "DET TE"}}
    new = {"injuries": {"B": "questionable", "C": "doubtful"}, "pulled": [],
           "weather": {"temp_f": 38, "wind_mph": 12, "snow": True}}
    moved = L.diff(old, new, "DET", "GB")
    assert moved == ["A (GB WR) came off the injury report; he was out",
                     "C was listed doubtful",
                     "A (GB WR)'s props are back up",
                     "The first forecast is in: 38°F, wind 12 mph, snow"], moved


def test_old_games_fall_out_and_a_broken_file_never_raises():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "log.json")
    L.update(path, {"GB@DET|2026-10-01": ({"spread": -3}, "DET", "GB")}, "2026-10-01T09:00:00",
             today=dt.date(2026, 10, 2))
    L.update(path, {"GB@DET|2026-10-25": ({"spread": -3}, "DET", "GB")}, "2026-10-20T09:00:00",
             today=dt.date(2026, 10, 20))
    assert list(json.load(open(path))["games"]) == ["GB@DET|2026-10-25"]
    open(path, "w").write("{not json")
    assert L.update(path, {"GB@DET|2026-10-25": ({"spread": -3}, "DET", "GB")}, "2026-10-20T10:00:00",
                    today=dt.date(2026, 10, 20))["GB@DET|2026-10-25"]["entries"] == []
    assert L.update(d, {"x|2026-10-25": ({}, "DET", "GB")}, "2026-10-20T10:00:00") == {}   # a directory


def test_no_board_path_keeps_nothing_and_writes_no_section():
    board = _board()
    line = R.attach(board, conn=db.connect(":memory:"), ideas={})
    _keys, sec = _changes(board)
    assert sec is None and "what changed" not in line


def test_the_builds_pass_their_board_path_and_ask_reads_it():
    assert "_greport.attach(result, allowed=_allowed, season=args.season, out=args.out)" in NFL
    assert "meta=_gr_meta, out=args.out)" in CFB
    _d, out = _tree()
    _attach(_board(), out, "2026-10-20T09:05:00")
    b = _board(spread=-3.5)
    _attach(b, out, "2026-10-23T18:40:00")
    facts = askbot.report_facts(b, b["games"][0])
    assert facts["what_changed"][1] == "Fri 6:40 PM ET: The spread moved from DET −2.5 to DET −3.5.", facts
    assert "what_changed" in askbot.SYSTEM
    # The section rides the paid report: the paywall's strip takes it whole.
    sealed = gate.redact(copy.deepcopy(b), "recommendations.json")
    assert not sealed.get("game_reports")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
