"""The NBA's own word under ESPN's "Day-To-Day" (step ABU, 22 November 2026).

Ethan, the Sunday morning: "we need to do better on reporting on injuries, figuring out which players are in or
out for all sports, for all game reports". ESPN files an NBA player who is probable, questionable or doubtful
all as "Day-To-Day", and the blurb under it keeps the league's own word: that morning, "Siakam (hip) is listed
as questionable for Sunday's game against New York", "Cunningham (knee) is probable to play Sunday in Atlanta",
"Antetokounmpo (groin) is listed as questionable for Sunday's game against Oklahoma City". The NBA's report said
"day-to-day" for all of them. What these hold:

  * the blurb's word is read for the game it names: probable, questionable, doubtful or game-time decision;
    a blurb about another day's game ("ruled out for Saturday's game", read on the Sunday), about the rest of
    a game under way, giving two words, or none, gives none;
  * the NBA report's Injuries list and its "Still to be decided" line say the league's word, and ESPN's
    status where the blurb gives none;
  * the report watch says a new word as an update ("day-to-day, now listed questionable for the game");
  * nothing moves a number: the board's hold reads ESPN's status, as before.

    python3 tests/test_the_nbas_own_word_under_day_to_day.py
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

from engine import gamereport as GR, leaguereport as L, reportwatch as RW   # noqa: E402
from engine.sources import espninjuries as E                                # noqa: E402

SIAKAM = "Siakam (hip) is listed as questionable for Sunday's game against New York."
CADE = "Cunningham (knee) is probable to play Sunday in Atlanta."


def test_the_blurb_gives_the_leagues_word_for_the_game_it_names():
    for text, day, want in (
            (SIAKAM, "Sunday", "questionable"),
            (CADE, "Sunday", "probable"),
            ("Williams is probable for Sunday's game against the Nuggets due to a left thumb sprain.", "Sunday",
             "probable"),
            ("Antetokounmpo (groin) is listed as questionable for Sunday's game against Oklahoma City, Ira "
             "Winderman of the South Florida Sun Sentinel reports.", "Sunday", "questionable"),
            ("X (ankle) has been downgraded to doubtful for Monday's game.", "Monday", "doubtful"),
            ("X (ankle) will be a game-time decision Monday.", "Monday", "game-time decision"),
            # Another day's game, the rest of one under way, two words, none.
            ("Tatum (rest) has been ruled out for Saturday's game against the Kings.", "Sunday", None),
            (SIAKAM, "Monday", None),
            ("Pospisil (upper body) left Saturday's game against Chicago and won't return.", "Saturday", None),
            ("X is questionable but expected to play; Y is doubtful.", "Monday", None),
            ("Brown (hamstring) went through individual work during Friday's practice.", "Sunday", None),
            ("day-to-day", "Sunday", None), ("", "Sunday", None), (None, None, None)):
        assert E.designation(text, day) == want, (text, E.designation(text, day))
    assert E.about_game(CADE, "Sunday") and not E.about_game(CADE, "Monday") and E.about_game("Out.", None)


def _nba(listed):
    games = [{"home": "NYK", "away": "IND", "date": "2026-11-22", "kickoff": "2026-11-23T00:30:00Z"}]  # Sun 7:30 PM ET
    hist = {"Pascal Siakam": {"team": "IND", "starter": True, "minutes": [34, 35, 33], "pts": [20, 22, 19]},
            "Andrew Nembhard": {"team": "IND", "starter": True, "minutes": [30, 31, 29], "pts": [12, 10, 14]},
            "Jalen Brunson": {"team": "NYK", "starter": True, "minutes": [35, 36, 34], "pts": [28, 26, 30]},
            "OG Anunoby": {"team": "NYK", "starter": True, "minutes": [34, 33, 35], "pts": [16, 15, 18]}}
    meta = L.nba_meta(games, hist, listed, {}, False)
    m = meta["IND@NYK"]
    return GR.Ctx(games[0], {"date": "2026-11-22", "games": games}, sport="nba",
                  names={"IND": "Pacers", "NYK": "Knicks"}, meta=m)


def _text(sec):
    out = []
    for b in (sec or {}).get("blocks") or []:
        out.append(str(b.get("text") or ""))
        out += [str(i.get("text") if isinstance(i, dict) else i) for i in b.get("items") or []]
    return " ".join(out)


def test_the_nba_report_says_the_leagues_word():
    listed = {"Pascal Siakam": {"player": "Pascal Siakam", "status": "Day-To-Day", "injury": "Hip", "comment": SIAKAM},
              "Andrew Nembhard": {"player": "Andrew Nembhard", "status": "Day-To-Day", "injury": "Ankle",
                                  "comment": "Nembhard (ankle) has been ruled out for Saturday's game."},
              "OG Anunoby": {"player": "OG Anunoby", "status": "Day-To-Day", "injury": "Calf"}}
    c = _nba(listed)
    assert L._game_day(c) == "Sunday"
    inj = _text(L.nba_injuries(c))
    assert "Pascal Siakam (IND) — questionable, hip" in inj, inj
    assert "Andrew Nembhard (IND) — day-to-day, ankle" in inj, "a blurb about another game: ESPN's status"
    assert "OG Anunoby (NYK) — day-to-day, calf" in inj, "no blurb: ESPN's status"
    before = _text(L.nba_before(c))
    assert "Pascal Siakam (IND, questionable)" in before and "OG Anunoby (NYK, day-to-day)" in before, before
    nb = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert '**({"comment": r["comment"]} if r.get("comment") else {})}' in nb, "the build keeps the blurb"


def test_the_watch_says_a_new_word_as_an_update():
    now = dt.datetime(2026, 11, 22, 15, 0, tzinfo=dt.timezone.utc).timestamp()

    def iso(h):
        return dt.datetime.fromtimestamp(now + h * 3600, dt.timezone.utc).isoformat().replace("+00:00", "Z")
    board = {"games": [{"away": "IND", "home": "NYK", "kickoff": iso(9.5), "away_name": "Indiana Pacers",
                        "home_name": "New York Knicks"}]}

    def row(comment, h=-1):
        return [{"team": "Indiana Pacers", "player": "Pascal Siakam", "pos": "F", "status": "Day-To-Day",
                 "injury": "Hip", "date": iso(h), "comment": comment}]

    def run(rows, at):
        return RW.run(now=now + at, leagues=("nba",), boards={"nba": board}, state_path=state, publish=False,
                      fetch_injuries=lambda _l: rows, fetch_news=lambda _l: [], fetch_rss=lambda _l: [])
    state = Path(tempfile.mkdtemp()) / "state.json"
    run(row("Siakam (hip) has been ruled out for Saturday's game.", -20), 0)
    ups = run(row(SIAKAM), 60)["leagues"]["nba"]["games"]["IND@NYK"]["updates"]
    assert [(u["from"], u["to"], u["word"]) for u in ups] == [("Day-To-Day", "Day-To-Day", "questionable")], ups
    c = GR.Ctx({"away": "IND", "home": "NYK"}, {}, sport="nba", names={"IND": "Pacers", "NYK": "Knicks"})
    words = GR.update_words(c, dict(ups[0], at="2026-11-22T15:01:00Z"))
    assert "day-to-day (hip), now listed questionable for the game" in words, words
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert 'const RW_DESIGNATIONS = ["probable", "questionable", "doubtful", "game-time decision"];' in js
    assert '`${now}${u.injury ? ` (${String(u.injury).toLowerCase()})` : ""}, now listed ${u.word} for the game${' in js


def test_nothing_moves_a_number():
    for f in ("nba_build.py", "engine/nba/pipeline.py", "engine/injurymerge.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert "import designation" not in src and ".designation(" not in src, \
            f"{f}: the board's hold reads ESPN's status"


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
