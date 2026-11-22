"""A game's parlays post late, when the news is in, then never change (step ABD, 21 November 2026).

Ethan, the evening of 21 November: "Clearly the parlays posted the latest are doing the best by what I'm
seeing so we need too figure that out. I just want whatever parlays are on the record page doing good. We
are reporting we are doing good on all the game reports yet I'm not doing good when I put the pick in."

Measured on the public record of every finished game since 16 November: the set each report carried at the
start (its latest) against the versions it posted earlier and replaced, three-leg 41 of 113 (36%) against 89
of 343 (26%), pairs 14 of 79 (18%) against 4 of 55 (7%), legs about ten points apart. The Record counted the
latest; a member who bet in the morning bet an earlier one. Now a game's parlays post once, POST_LEAD before
its start (75 minutes for the NFL, just after its inactives; 90 elsewhere), built then from the newest
numbers, and step ABB's lock holds them as posted; so what a member bets is what the Record counts.

    python3 tests/test_parlays_post_late_then_never_change.py
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
TP = __import__("test_the_parlays_are_made_of_the_reports_picks")
GAME = EG.GAME                                                       # WAS at NYG, 2099-11-12, "20:15" Eastern
KEY = f"{GAME['away']}@{GAME['home']}|{GAME['date']}"
START = dt.datetime(2099, 11, 13, 1, 15, tzinfo=dt.timezone.utc)    # 8:15 PM Eastern, standard time
SRC = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
UTC = dt.timezone.utc


def test_a_games_start_is_read_in_every_boards_shape():
    assert GP.game_start({"date": "2099-11-12", "kickoff": "20:15"}) == START, "the NFL's Eastern clock and day"
    assert GP.game_start({"date": "2026-07-04", "kickoff": "13:05"}) == dt.datetime(2026, 7, 4, 17, 5, tzinfo=UTC), \
        "summer time: four hours behind"
    assert GP.game_start({"kickoff": "2026-11-22T00:30Z"}) == dt.datetime(2026, 11, 22, 0, 30, tzinfo=UTC)
    for bad in ({}, {"kickoff": ""}, {"kickoff": "TBD", "date": "2026-11-22"}, {"kickoff": "13:00"}):
        assert GP.game_start(bad) is None, bad
    assert GP.post_lead("nfl") == 75 and GP.post_lead("nba") == 90 and GP.post_lead("nhl") == 90


def test_a_game_further_out_than_its_lead_posts_nothing_yet_and_says_when():
    x = {"date": "2099-11-12", "kickoff": "20:15", "threes": [{"legs": [1, 2, 3]}], "twos": [{"legs": [1, 2]}],
         "scorers": [{"legs": [1, 2]}], "twos_note": "x", "posted_kept": 3}
    at = GP.hold_until_post(x, "nfl", START - dt.timedelta(minutes=76))
    assert at == (START - dt.timedelta(minutes=75)).strftime("%Y-%m-%dT%H:%M:%SZ") == "2099-11-13T00:00:00Z"
    assert x["threes"] == [] and x["twos"] == [] and x["scorers"] == [], x
    assert "post at Thu 7:00 PM ET, about 75 minutes before the start" in x["post_note"], x["post_note"]
    assert x["threes_note"] == x["post_note"] and "twos_note" not in x and "posted_kept" not in x
    # Inside its lead it posts, and the note goes.
    y = dict(x, threes=[{"legs": [1, 2, 3]}])
    assert GP.hold_until_post(y, "nfl", START - dt.timedelta(minutes=74)) is None and y["threes"] and "post_at" not in y
    # A start it cannot read, a started game's kept entry and the switch: as built.
    for z in ({"kickoff": "", "threes": [1]}, {"date": "2099-11-12", "kickoff": "20:15", "kept": "x", "threes": [1]}):
        assert GP.hold_until_post(z, "nfl", START - dt.timedelta(days=3)) is None and z["threes"] == [1]
    os.environ["QB_PARLAY_POST_LATE"] = "off"
    try:
        z = {"date": "2099-11-12", "kickoff": "20:15", "threes": [1]}
        assert GP.hold_until_post(z, "nfl", START - dt.timedelta(days=3)) is None and z["threes"] == [1]
    finally:
        os.environ.pop("QB_PARLAY_POST_LATE", None)


def _build(posted=None, board=None):
    b = board or EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    if posted is not None:
        b[GP.POSTED_KEY] = posted
    GP.from_report(b, "nfl", GAME, TP.PICKS)
    GP.report_only(b)
    return b


def _posted(x):
    path = Path(tempfile.mkdtemp()) / "reportkeep_nfl.json"
    path.write_text(json.dumps({"games": {KEY: {"at": "2099-11-12T12:00:00", "report": {}, "parlays": x}}}),
                    encoding="utf-8")
    return GP.posted_from(path)


def _legs(ts):
    return [[(l["player"], l["market"], l["side"], l["line"], l.get("odds")) for l in t["legs"]] for t in ts]


def test_early_builds_post_nothing_the_first_inside_its_lead_posts_and_then_it_holds():
    # The morning: built, held. Nothing posted, so nothing journaled and nothing to hold later.
    b1 = _build()
    assert GP.post_late(b1, START - dt.timedelta(hours=8)) == 1
    x1 = GP.for_game(b1, "NYG", "WAS")
    assert not (x1["threes"] or x1["twos"] or x1["scorers"]) and x1["post_at"], x1.get("post_at")
    r = b1["game_parlays"]["ranked"]
    assert r["left_off"]["waiting"] == 1 and r["next_post"] == x1["post_at"] and r["post_lead"] == 75
    assert all(not r[k] for k in GP.RANK_KINDS), "nothing ranked before it posts"
    assert b1["game_parlays"]["counts"]["waiting"] == 1 and b1["game_parlays"]["counts"]["threes"] == 0
    # An hour before: posted, from this build's numbers.
    b2 = _build(posted=_posted(x1))
    assert GP.post_late(b2, START - dt.timedelta(minutes=60)) == 0
    x2 = GP.for_game(b2, "NYG", "WAS")
    assert x2["threes"] and x2["twos"] and x2["scorers"] and "post_at" not in x2
    assert "waiting" not in b2["game_parlays"]["ranked"]["left_off"]
    # The books move two legs' numbers before the start: what was posted stays as it was posted.
    board = EG.board()
    for row in board["most_likely"]:
        if row["player"] in ("Malik Nabers", "Isaiah Likely"):
            row["line"] = float(row["line"]) + 1.0
            row["odds"] = -110
    b3 = _build(posted=_posted(x2), board=board)
    GP.post_late(b3, START - dt.timedelta(minutes=30))
    x3 = GP.for_game(b3, "NYG", "WAS")
    assert {k: _legs(x3[k]) for k in ("threes", "twos", "scorers")} == {k: _legs(x2[k]) for k in ("threes", "twos", "scorers")}


def test_a_game_that_posted_is_never_taken_down():
    # This step's first day took the NFL tickets posted days ahead under the old rule down until their post time
    # (every one of them has posted again since). From step ACF (22 November) a game that posted stays posted
    # however far off its start now reads: a kickoff ESPN's scoreboard moves later (the Jaguars at the Giants,
    # posted for 1 PM, kicking off at 4:25) takes nothing it posted off the board.
    b = _build()
    x = GP.for_game(b, "NYG", "WAS")
    b2 = _build(posted=_posted(x))
    GP.post_late(b2, START - dt.timedelta(hours=20))
    x2 = GP.for_game(b2, "NYG", "WAS")
    assert x2["threes"] and x2.get("posted_before") is True and "post_at" not in x2
    assert {k: _legs(x2[k]) for k in ("threes", "twos", "scorers")} == {k: _legs(x[k]) for k in ("threes", "twos", "scorers")}
    held = dict(x, posted_before=True)
    assert GP.hold_until_post(held, "nfl", START - dt.timedelta(hours=20)) is None and held["threes"]
    fresh = _build()
    GP.post_late(fresh, START - dt.timedelta(hours=20))
    assert not GP.for_game(fresh, "NYG", "WAS")["threes"], "a game that never posted still waits for its time"


def test_every_leagues_report_stage_runs_it_after_the_reports_and_before_the_keep():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    fn = src[src.index("def _report_only(result: dict) -> None:"):src.index("def _parlays_from_picks(")]
    assert fn.index("gameparlays.report_only(result)") < fn.index("gameparlays.post_late(result)")
    league = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert "from .gamereport import _report_only" in league and "_report_only(result)" in league
    for words in ("three-leg   latest 41 of 113 (36%)   earlier 89 of 343 (26%)",
                  "Off without a deploy: ``sudo ./deploy/setenv.sh QB_PARLAY_POST_LATE off``"):
        assert words in SRC, words
    rp = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    assert "(rpParlays(x) || (x.scorers || []).length || x.post_note)" in rp, "a held game says when, under its picks"
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert 'out["parlay_waiting"] = len(waiting)' in launch, "the heartbeat counts the games waiting, not short"
    bp = (ROOT / "web" / "js" / "bestparlays.js").read_text(encoding="utf-8")
    assert "parlays post later, about ${" in bp and "(the next at ${" in bp



def test_best_parlays_says_the_next_posts_day_when_it_is_not_today():
    """Step ABF: a Saturday evening's "the next at 11:45 AM" is Sunday's, and says so."""
    import json
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    kick = __import__("test_football_kickoffs_read_in_the_readers_zone")
    bp = (ROOT / "web" / "js" / "bestparlays.js").read_text(encoding="utf-8")
    i = bp.index("function bpNextWhen(")
    fn = bp[i:bp.index("\n}\n", i) + 3]
    helpers = "\n".join(kick._fn(n) for n in ("tzOpts", "tzTime", "formatGameDate", "formatKickoff", "etInstant",
                                               "whenLabel"))
    out = {}
    for tz in ("America/New_York", "Europe/London"):
        prog = f"""
          const settings = () => ({{ tz: {json.dumps(tz)} }});
          const escapeHtml = (s) => String(s);
          {helpers}
          {fn}
          Date.now = () => Date.UTC(2026, 10, 21, 23, 30);            // Sat 6:30 PM in New York
          console.log(JSON.stringify([bpNextWhen(Date.UTC(2026, 10, 22, 0, 0)),     // Sat 7:00 PM New York
                                      bpNextWhen(Date.UTC(2026, 10, 22, 16, 45)),   // Sun 11:45 AM New York
                                      bpNextWhen(NaN)]));
        """
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(prog); path = fh.name
        try:
            run = subprocess.run([node, path], capture_output=True, text=True, timeout=30,
                                 env=dict(os.environ, TZ="Asia/Tokyo", LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8"))
        finally:
            os.unlink(path)
        assert run.returncode == 0, run.stderr
        out[tz] = json.loads(run.stdout.strip())
    assert out["America/New_York"] == ["7:00 PM", "Sun, Nov 22 · 11:45 AM", ""], out
    assert out["Europe/London"] == ["Sun, Nov 22 · 12:00 AM", "Sun, Nov 22 · 4:45 PM", ""], \
        "past midnight in London the next post is tomorrow there"
    assert "bpNextWhen(nextAt) ? ` (the next at ${bpNextWhen(nextAt)})` : \"\"" in bp



def test_a_held_games_post_time_reads_in_the_readers_zone():
    """Step ABF (decision 13): the engine's "post at Sun 11:45 AM ET" is said in the reader's own zone."""
    import json
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    kick = __import__("test_football_kickoffs_read_in_the_readers_zone")
    rep = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    i = rep.index("  function postNote(")
    fn = rep[i:rep.index("\n  }\n", i) + 5]
    at = dt.datetime(2026, 11, 22, 16, 45, tzinfo=dt.timezone.utc)
    note = GP._et_clock(at)
    assert note == "Sun 11:45 AM ET", note
    x = {"away": "NYG", "home": "WAS", "date": "2026-11-22", "kickoff": "13:00"}
    GP.hold_until_post(x, "nfl", at - dt.timedelta(hours=18))
    assert x["post_at"] == "2026-11-22T16:45:00Z" and "post at Sun 11:45 AM ET, about 75 minutes" in x["threes_note"]
    out = {}
    for tz, helpers in (("America/Los_Angeles", True), ("Europe/London", True), ("America/New_York", True),
                        ("America/Los_Angeles", False)):
        src = "\n".join(kick._fn(n) for n in ("tzOpts", "tzTime")) if helpers else ""
        prog = f"""
          const settings = () => ({{ tz: {json.dumps(tz)} }});
          {src}
          {fn}
          const g = {json.dumps(x)};
          console.log(JSON.stringify([postNote(g), postNote({{ ...g, post_at: "" }}),
                                      postNote({{ threes_note: "No three-leg ticket", post_at: g.post_at }}),
                                      postNote({{}})]));
        """
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(prog); path = fh.name
        try:
            run = subprocess.run([node, path], capture_output=True, text=True, timeout=30,
                                 env=dict(os.environ, TZ="Asia/Tokyo", LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8"))
        finally:
            os.unlink(path)
        assert run.returncode == 0, run.stderr
        out[(tz, helpers)] = json.loads(run.stdout.strip())
    la = out[("America/Los_Angeles", True)]
    assert "post at Sun 8:45 AM, about 75 minutes" in la[0], la[0]
    assert la[1] == x["threes_note"] and la[2] == "No three-leg ticket" and la[3] == "", la
    assert "post at Sun 4:45 PM, about" in out[("Europe/London", True)][0]
    assert "post at Sun 11:45 AM, about" in out[("America/New_York", True)][0]
    assert out[("America/Los_Angeles", False)][0] == x["threes_note"], "without the page's helpers, as the engine said"
    assert "escapeHtml(postNote(g) || \"No three-leg ticket without a conflict in this game.\")" in rep


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
