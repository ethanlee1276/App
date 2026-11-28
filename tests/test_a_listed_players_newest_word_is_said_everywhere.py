"""A listed player's newest word is said everywhere the site lists him (step ABY, 22 November 2026).

Ethan, the Sunday afternoon: "Baker Mayfield's foot/right thumb is slated to play in Sunday's game against Detroit
Lions, Ian Rapoport of NFL Network reports. But he's still labeled as questionable on ESPN ... clearly that
information is being conveyed and we're not reporting it. So we need to be having that information on hand and
using that data to our advantage, and also reporting it in our game reports and every other spot where we report
injuries or data like that." The Injuries page showed the blurb only on a hover, and a report's injury lines said
"questionable" and nothing more. What these hold:

  * a blurb is read for the game it names, counted from when it was posted: a day already past is when it was
    said ("McVay said Saturday ... expected to play Wednesday" is Wednesday's game), a Sunday blurb naming
    Saturday is about a game played, and one naming no day counts for a day;
  * its word is which way it leans, else under ESPN's bare "Day-To-Day" the league's own word, with the reporter;
  * the Injuries page says it under the status, coloured by its lean;
  * every league's report says it on the player's injury line, read off the board's cache (no network);
  * the report watch reads blurbs the same way (one reader, engine/sources/espninjuries).

    python3 tests/test_a_listed_players_newest_word_is_said_everywhere.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as GR, reportwatch as RW                # noqa: E402
from engine.sources import espninjuries as E                         # noqa: E402

NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=dt.timezone.utc)         # Sunday, 10 AM ET
MAYFIELD = ("Mayfield (foot/right thumb) is slated to play in Sunday's game against the Lions, Ian Rapoport of NFL "
            "Network reports.")


def test_a_blurb_is_read_for_the_game_it_names():
    def row(comment, date, status="Questionable"):
        return {"status": status, "comment": comment, "date": date}
    for r, day, word in (
            (row(MAYFIELD, "2026-11-22T12:24Z"), "Sunday", {"word": "in", "day": "Sunday", "by": "Ian Rapoport of NFL Network"}),
            (row("Head coach Sean McVay said Saturday that Williams is tending to a sore toe but is expected to play "
                 "Wednesday against the Packers, Sarah Barshop of ESPN reports.", "2026-11-21T21:55Z"),
             "Wednesday", {"word": "in", "day": "Wednesday", "by": "Sarah Barshop of ESPN"}),
            (row("Tate (shoulder) is expected to play in Sunday's game against the Cowboys.", "2026-11-20T18:00Z"),
             "Sunday", {"word": "in", "day": "Sunday", "by": ""}),
            (row("Tatum (rest) has been ruled out for Saturday's game against the Kings.", "2026-11-22T15:02Z",
                 "Day-To-Day"), False, None),
            (row("Towns (illness) won't play in Saturday's game versus the Trail Blazers.", "2026-11-22T03:05Z",
                 "Day-To-Day"), False, None),
            (row("Melton (thigh) has been ruled out for the rest of Sunday's game against the Vikings.",
                 "2026-11-22T19:56Z"), "Sunday", None),
            (row("Rice (knee) is not expected to play.", "2026-11-22T13:00Z"), None, {"word": "out", "day": None, "by": ""}),
            (row("Rice (knee) is not expected to play.", "2026-11-18T13:00Z"), False, None),
            (row("Beck (back) has been ruled out for Sunday's game at Kansas City.", "2026-11-21T19:25Z", "Out"),
             "Sunday", None)):
        assert E.blurb_day(r, NOW) == day, (r["comment"][:40], E.blurb_day(r, NOW))
        assert E.newest_word(r, NOW) == word, (r["comment"][:40], E.newest_word(r, NOW))
    assert RW.lean is E.lean and RW.reported_by is E.reported_by, "the watch reads blurbs the same way"


def test_the_injuries_page_says_it_under_the_status():
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'const INJ_LEAN = { in: "expected to play", out: "expected to miss the game" };' in app
    assert 'inj-word${r.word === "in" ? " up" : r.word === "out" ? " down" : ""}' in app
    css = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    assert ".inj-word.up { color: var(--good); }" in css and ".inj-word { white-space: normal; max-width: 15em; }" in css
    ib = (ROOT / "injuries_build.py").read_text(encoding="utf-8")
    assert "w = newest_word(r)" in ib


def _board_cache(tmp: Path) -> Path:
    payload = {"injuries": [{"displayName": "Tampa Bay Buccaneers", "injuries": [
        {"athlete": {"displayName": "Baker Mayfield", "position": {"abbreviation": "QB"}}, "status": "Questionable",
         "date": "2026-11-22T12:24Z", "shortComment": MAYFIELD, "details": {"type": "Foot", "detail": "Strain"}}]},
        {"displayName": "Detroit Lions", "injuries": [
            {"athlete": {"displayName": "Sione Vaki", "position": {"abbreviation": "RB"}}, "status": "Questionable",
             "date": "2026-11-20T21:00Z", "shortComment": "Vaki (ankle) is listed as questionable."}]}]}
    path = tmp / "espn_injuries_nfl.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_every_report_says_it_on_the_players_injury_line():
    tmp = Path(tempfile.mkdtemp())
    path = _board_cache(tmp)
    real, real_now = E._cache_file, E.newest_word
    E._cache_file = lambda league: path if league == "nfl" else tmp / f"none_{league}.json"
    GR._WORDS.clear()
    try:
        g = {"home": "DET", "away": "TB", "date": "2026-11-22", "kickoff": "13:00",
             "scan": {"injuries": [{"player": "Baker Mayfield", "team": "TB", "position": "QB", "status": "QUESTIONABLE"},
                                   {"player": "Sione Vaki", "team": "DET", "position": "RB", "status": "QUESTIONABLE"}]}}
        c = GR.Ctx(g, {"date": "2026-W12", "games": [g]}, sport="nfl", names={"TB": "Buccaneers", "DET": "Lions"})
        E.newest_word = lambda row, now=None: real_now(row, NOW)
        assert GR.newest_word(c, "TB", "Baker Mayfield") == \
            "the newest word: expected to play, per Ian Rapoport of NFL Network"
        assert GR.newest_word(c, "DET", "Sione Vaki") == "", "a blurb that leans neither way says nothing"
        sec = GR.sec_injuries(c)
        text = json.dumps(sec)
        assert "Baker Mayfield (QB) \\u2014 questionable; the newest word: expected to play, per Ian Rapoport of NFL Network" \
            in text, text[:600]
        # A game on another day: the Sunday blurb is about Sunday's game, not this one.
        c2 = GR.Ctx(dict(g, date="2026-11-24", kickoff="20:15"), {"games": []}, sport="nfl",
                    names={"TB": "Buccaneers"})
        assert GR.newest_word(c2, "TB", "Baker Mayfield") == ""
        # No cache, no word, and no request.
        GR._WORDS.clear()
        c3 = GR.Ctx({"home": "BOS", "away": "NYK", "kickoff": "2026-11-23T00:30:00Z"}, {}, sport="nba", names={})
        assert GR.newest_word(c3, "BOS", "Jayson Tatum") == ""
    finally:
        E._cache_file, E.newest_word = real, real_now
        GR._WORDS.clear()
    lr = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert lr.count("newest_word(c, ") >= 3, "the NBA's and the NHL's injury lines too"
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "a report asks nothing of the network" in src


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
