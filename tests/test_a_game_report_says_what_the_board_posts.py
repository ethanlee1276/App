"""A game's report says exactly what the board posts: nothing before its post time, the locked set after
(step ABH, 22 November 2026).

Ethan, the Sunday morning: "I see parlays posted now on the game reports for nfl but those shouldn't be
there by what u said." Each report writes its parlays section, its card's parlay line and its short version
(gamereport.finish) right after its picks rebuild the game's tickets (gameparlays.from_report), and the post
time (step ABD) and the lock (step ABB) ran only after every report was written: the board held Sunday's NFL
tickets until 75 minutes before each kickoff while every NFL report printed a fresh set, and a game that had
posted printed each build's fresh set, not the locked one Report Picks and Best Parlays showed. Now the
report's rebuild applies both to its game before it writes a word (gameparlays.as_posted). What these hold:

  * before its post time a report writes no ticket, its card no parlay line, and its parlays section says
    when they post (with the time, so the page says it in the reader's zone);
  * after it, the report writes the tickets the game posted, as posted, not this build's fresh ones;
  * the board's own pass after the reports (report_only, post_late) finds nothing more to change;
  * every league's report goes through the same rebuild.

    python3 tests/test_a_game_report_says_what_the_board_posts.py
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, gamereport as GR  # noqa: E402

TP = __import__("test_the_parlays_are_made_of_the_reports_picks")   # an NFL report's board (a sibling test file)
GAME = TP.NFL_GAME
KEY = f"{GAME['away']}@{GAME['home']}|{GAME['date']}"
NAMES = {"GB": "Packers", "DET": "Lions"}


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


def _report(posted=None):
    result, _priced = TP._nfl_result()
    result["game_parlays"] = GP.build(result, "nfl")
    if posted is not None:
        result[GP.POSTED_KEY] = posted
    rep = GR.build(GAME, result, sport="nfl", names=NAMES)
    return result, rep


def _section(rep):
    return next(s for s in rep["sections"] if s["key"] == "parlays")


def _shown(rep, kind="three"):
    return [b for b in _section(rep)["blocks"] if b.get("type") == "parlays" and b.get("kind") == kind]


def test_before_its_post_time_a_report_writes_no_ticket_and_says_when():
    with _Env(QB_PARLAY_POST_LATE=None):
        result, rep = _report()
    x = GP.for_game(result, "DET", "GB")
    assert not (x.get("threes") or x.get("twos") or x.get("scorers")) and x.get("post_at"), x.get("threes_note")
    blocks = _section(rep)["blocks"]
    assert len(blocks) == 1 and blocks[0]["type"] == "p", blocks
    assert blocks[0]["post_at"] == x["post_at"]
    assert "This game's parlays post at " in blocks[0]["text"] and "75 minutes before the start" in blocks[0]["text"]
    card = str(next(s for s in rep["sections"] if s["key"] == "card"))
    assert "The parlay:" not in card and "The touchdown pair:" not in card, "the card names no ticket yet"
    assert "The parlay" not in str(rep.get("short") or ""), "nor the short version"


def test_after_it_the_report_writes_the_tickets_the_game_posted_as_posted():
    with _Env(QB_PARLAY_POST_LATE="off"):
        result, rep = _report()
        fresh = copy.deepcopy(GP.for_game(result, "DET", "GB"))
        assert fresh["threes"], fresh.get("threes_note")
        # The game posted these an earlier build: the same tickets, one leg at the number it was posted at.
        posted = copy.deepcopy(fresh["threes"])
        posted[0]["legs"][0]["line"] = 99.5
        mine = {"threes": [[list(k) for k in GP.ident(t)] for t in posted], GP.POSTED_TICKETS: {"threes": posted}}
        result2, rep2 = _report(posted={KEY: mine})
    x = GP.for_game(result2, "DET", "GB")
    assert x["threes"][0]["legs"][0]["line"] == 99.5, "the board holds the posted number"
    shown = _shown(rep2)
    assert shown and "99.5" in shown[0]["items"][0]["legs"][0]["pick"], shown[0]["items"][0]["legs"][0]
    assert [[l["player"] for l in i["legs"]] for i in shown[0]["items"]] == \
        [[l["player"] for l in t["legs"]] for t in x["threes"]], "the report writes the board's tickets, in order"
    # The board's own pass after the reports changes nothing more.
    before = copy.deepcopy(x["threes"])
    result2[GP.POSTED_KEY] = {KEY: mine}
    with _Env(QB_PARLAY_POST_LATE="off"):
        GP.report_only(result2)
        GP.post_late(result2)
    assert [[(l["player"], l["line"]) for l in t["legs"]] for t in GP.for_game(result2, "DET", "GB")["threes"]] == \
        [[(l["player"], l["line"]) for l in t["legs"]] for t in before]


def test_inside_its_post_window_the_fresh_tickets_post():
    # The first build inside the window: nothing posted yet, so the report writes this build's tickets.
    start = GP.game_start({"date": GAME["date"], "kickoff": GAME["kickoff"]})
    result, _ = TP._nfl_result()
    result["game_parlays"] = GP.build(result, "nfl")
    x = GP.for_game(result, "DET", "GB")
    GP.from_report(result, "nfl", GAME, [{"player": l["player"], "market": l["market"], "side": l["side"],
                                         "line": l["line"]} for t in x.get("threes") or [] for l in t["legs"]])
    GP.as_posted(result, "nfl", x, now=start - dt.timedelta(minutes=60))
    assert x["threes"] and not x.get("post_at")
    GP.as_posted(result, "nfl", x, now=start - dt.timedelta(hours=5))
    assert not x["threes"] and x.get("post_at"), "and further out, none"


def test_a_started_games_kept_entry_and_a_bad_board_are_left_alone():
    x = {"away": "GB", "home": "DET", "date": GAME["date"], "kickoff": GAME["kickoff"], "kept": "Sun 1:00 PM ET",
         "threes": [{"legs": [{"player": "A"}, {"player": "B"}, {"player": "C"}]}]}
    GP.as_posted({}, "nfl", x)
    assert x["threes"] and not x.get("post_at")
    GP.as_posted(None, "nfl", {"threes": []})                # never raises


def test_every_leagues_report_rebuild_runs_it_and_the_page_says_the_readers_time():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    fn = src[src.index("def _parlays_from_picks("):src.index("def finish(")]
    assert fn.index("x = gameparlays.from_report(c.result, c.sport, c.g, picks)") < \
        fn.index("gameparlays.as_posted(c.result, c.sport, x)")
    assert "return finish(c, fns, short)" in (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "b.post_at ? postNote({ threes_note: b.text, post_at: b.post_at }) : b.text" in js
    gp = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert "I see parlays posted now on the game reports for nfl but those shouldn't be\n#: there by what u\n#: said." \
        in gp or "I see parlays posted now on the game reports for nfl" in gp


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
