"""A game report's picks post once, with its parlays, and never change (step ABQ, 22 November 2026).

Ethan, the Sunday morning: "let's also work on not throwing a million different picks into one game report and
keep switching picks and stuff like that, like the issue we had last night for NBA, because that's a big issue.
So we need to figure out the timeline for that". Every build chose a report's picks afresh and the report book
journals a pick the first time any version shows it, so a game piled up picks through the day (Saturday night's
seven NBA reports: 50 graded singles) and a reader saw different ones on each visit. What these hold:

  * before its post time (its parlays': 75 minutes before an NFL kickoff, 90 elsewhere) a report shows its
    analysis and says when its picks post; no card, no pick on any read, nothing for the record to journal;
  * at the post time its card and the picks its reads carry post, marked with the time;
  * on every build after, until the start, the report shows the picks it posted, as posted, whatever the
    board's numbers did; every other section still updates;
  * the posted picks are read back from the file the report stage keeps (engine/reportkeep);
  * QB_REPORT_PICKS_POST=off goes back to a report's picks as each build makes them.

    python3 tests/test_a_reports_picks_post_once_and_never_change.py
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

from engine import gameparlays as GP, gamereport as GR, reportbets  # noqa: E402

TP = __import__("test_the_parlays_are_made_of_the_reports_picks")   # an NFL report's board (a sibling test file)
GAME = TP.NFL_GAME
NAMES = {"GB": "Packers", "DET": "Lions"}
START = GP.game_start(GAME)


class _Env:
    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.was = {k: os.environ.get(k) for k in self.kw}
        for k, v in self.kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *exc):
        for k, v in self.was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _report(now, result=None):
    if result is None:
        result, _ = TP._nfl_result()
        result["game_parlays"] = GP.build(result, "nfl")
    # The report's clock, set (finish reads `picks_timeline` by name when it runs).
    real_tl = GR.picks_timeline
    GR.picks_timeline = lambda c, sections, now=None, _at=now: real_tl(c, sections, now=_at)
    try:
        with _Env(QB_PARLAY_POST_LATE="off"):
            rep = GR.build(GAME, result, sport="nfl", names=NAMES)
    finally:
        GR.picks_timeline = real_tl
    return result, rep


def _sec(rep, key):
    return next((s for s in rep["sections"] if s.get("key") == key), None)


def _items_with_picks(rep):
    return [(s.get("key"), it.get("player")) for s in rep["sections"] for b in s.get("blocks") or []
            for it in b.get("items") or [] if isinstance(it, dict) and (it.get("bet") or it.get("pick"))]


def test_before_the_post_time_a_report_has_no_pick_and_says_when():
    _result, rep = _report(START - dt.timedelta(hours=5))
    card = _sec(rep, "card")
    assert card and len(card["blocks"]) == 1 and card["blocks"][0]["type"] == "p", card
    assert card["blocks"][0]["post_at"] == (START - dt.timedelta(minutes=75)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert card["blocks"][0]["text"].startswith("Our picks for this game post at ") and \
        "75 minutes before the start" in card["blocks"][0]["text"]
    assert not _items_with_picks(rep), _items_with_picks(rep)
    assert not rep.get("_bets"), "nothing for the record to journal"


def test_at_the_post_time_its_picks_post_and_say_when():
    now = START - dt.timedelta(minutes=70)
    _result, rep = _report(now)
    card = _sec(rep, "card")
    assert any(b.get("type") == "picks" for b in card["blocks"]), card
    assert card["posted_at"] == now.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert rep.get("_bets"), "the posted picks are the record's"
    for key, _who in _items_with_picks(rep):
        assert _sec(rep, key).get("posted_at"), key


def test_after_it_the_posted_picks_stand_as_posted():
    from engine.reportlog import game_key
    result, rep = _report(START - dt.timedelta(minutes=70))
    posted = {"card": _sec(rep, "card"), "at": _sec(rep, "card")["posted_at"],
              "sections": {s["key"]: s for s in rep["sections"] if s.get("key") != "card" and s.get("posted_at")}}
    was = [it["pick"] for b in posted["card"]["blocks"] if b.get("type") == "picks" for it in b["items"]]
    # The board moves: every line half a point up, the likeliest pick gone.
    result2, _ = TP._nfl_result()
    rows = result2["likely_board"]["rows"]
    for r in rows:
        r["line"] = float(r["line"]) + 0.5
    result2["likely_board"]["rows"] = rows[1:]
    result2["game_parlays"] = GP.build(result2, "nfl")
    result2[GR.PICKS_POSTED_KEY] = {game_key(GAME): copy.deepcopy(posted)}
    _r, rep2 = _report(START - dt.timedelta(minutes=40), result2)
    now = [it["pick"] for b in _sec(rep2, "card")["blocks"] if b.get("type") == "picks" for it in b["items"]]
    assert now == was, (now, was)
    assert _sec(rep2, "card") == posted["card"]
    assert {(b["player"], b["line"]) for b in rep2.get("_bets") or []} >= \
        {(b["player"], b["line"]) for b in rep.get("_bets") or [] if "card" in b.get("sources", [])}
    # And without the posted file, the moved board would have changed them.
    _r, fresh = _report(START - dt.timedelta(minutes=40), result2 | {GR.PICKS_POSTED_KEY: {}})
    assert [it["pick"] for b in _sec(fresh, "card")["blocks"] if b.get("type") == "picks" for it in b["items"]] != was


def test_the_posted_picks_are_read_back_from_the_kept_file():
    from engine import reportkeep
    from engine.reportlog import game_key
    _result, rep = _report(START - dt.timedelta(minutes=70))
    d = Path(tempfile.mkdtemp())
    path = reportkeep.path_for("nfl", d)
    key = game_key(GAME)
    waiting = copy.deepcopy(rep)
    waiting["sections"] = [s for s in waiting["sections"] if s.get("key") != "card"] + [
        {"key": "card", "title": "Our picks for this game", "blocks": [{"type": "p", "text": "Our picks post at"}]}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"games": {key: {"at": "x", "report": rep}, "GB@DET|2099-10-26": {"at": "x",
                                                                                                "report": waiting}}}))
    got = GR.posted_picks_from(path)
    assert list(got) == [key], "a game still waiting posted nothing"
    assert got[key]["card"]["posted_at"] and got[key]["at"] == got[key]["card"]["posted_at"]
    assert GR.posted_picks_from(d / "nothing.json") == {}


def test_the_switch_goes_back_to_each_builds_picks():
    with _Env(QB_REPORT_PICKS_POST="off"):
        _result, rep = _report(START - dt.timedelta(hours=5))
    assert any(b.get("type") == "picks" for b in _sec(rep, "card")["blocks"])
    assert rep.get("_bets") and not _sec(rep, "card").get("posted_at")
    assert GR.picks_wait("nfl", {"kickoff": "", "date": ""}) is None, "a start it cannot read posts as built"


def test_every_leagues_report_runs_it_and_the_page_says_the_readers_time():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    fin = src[src.index("def finish("):src.index("def section_hint(") if "def section_hint(" in src[src.index("def finish("):] else None]
    assert fin.index("sections = picks_timeline(c, sections)") < fin.index("bets = reportbets.bets_of(sections")
    assert "return finish(c, fns, short)" in (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "b.post_at ? postNote({ threes_note: b.text, post_at: b.post_at }) : b.text" in js
    assert GR.PICKS_NOT_IN == ("parlays",) and reportbets.SOURCES == ("card", "read", "breakout", "fade")


def test_report_picks_says_when_a_waiting_games_picks_post():
    import shutil
    import subprocess
    js = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    i = js.index("function rpWaitWords(")
    fn = js[i:js.index("\n}\n", i) + 3]
    assert "rpWaitWords(tix)\n        || \"No single pick on this game clears our bars.\"" in js
    node = shutil.which("node")
    if not node:
        return
    code = fn + """
      const tzTime = (d) => "1:45 PM";
      const soon = new Date(Date.now() + 3600e3).toISOString(), gone = new Date(Date.now() - 60e3).toISOString();
      console.log(JSON.stringify([rpWaitWords({ post_at: soon }), rpWaitWords({ post_at: gone }), rpWaitWords(null)]));"""
    out = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got == ["This game's picks post at 1:45 PM, with its parlays, and never change after.", "", ""], got


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
