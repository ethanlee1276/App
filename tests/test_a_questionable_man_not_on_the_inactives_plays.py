"""A questionable man not on his club's inactives list plays, and his own props are priced (step ACA, 22 November 2026).

Ethan, the Sunday: "clearly that information is being conveyed and we're not reporting it. So we need to be having
that information on hand and using that data to our advantage." ESPN's board filed the Ravens' seven inactives as
"Out" with the note "inactive" at 11:32 AM ET, two minutes after the lists came out, and kept every questionable
man who was active at "Questionable" until kickoff; the hold on a questionable man's own props kept them off the
board through his game. What these hold:

  * a club's list is posted for its game when at least three rows are filed as inactive since 100 minutes before
    its kickoff; a list from an earlier game, or a club with one row so far, is not;
  * then every man it still lists questionable, doubtful or a game-time decision who is not on it is ACTIVE (his
    old status kept): no hold on his own props, and no teammate priced as if he sat;
  * the NFL build reads the lists off the board's cache and says who it cleared; the report says he is active;
  * QB_ACTIVE_AFTER_INACTIVES=off goes back to before.

    python3 tests/test_a_questionable_man_not_on_the_inactives_plays.py
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

from engine import gamereport as GR                             # noqa: E402
from engine.injuries import player_injury_status               # noqa: E402
from engine.models import Injury                                # noqa: E402
from engine.sources import injuries as I                        # noqa: E402

NOW = dt.datetime(2026, 11, 22, 16, 50, tzinfo=dt.timezone.utc).timestamp()       # 11:50 AM ET


class _G:
    def __init__(self, home, away, date="2026-11-22", kickoff="13:00"):
        self.home, self.away, self.date, self.kickoff = home, away, date, kickoff


GAMES = [_G("DET", "TB"), _G("BAL", "NYJ"), _G("KC", "ARI", kickoff="16:25")]


def _inactive(team, player, date="2026-11-22T16:32Z", comment="inactive"):
    return {"team": team, "player": player, "status": "Out", "comment": comment, "date": date}


ROWS = ([_inactive("Baltimore Ravens", p) for p in ("Marlon Humphrey", "Nnamdi Madubuike", "Elijah Sarratt")]
        + [_inactive("Houston Texans", p, "2026-11-19T23:50Z") for p in ("A", "B", "C", "D")]      # Thursday's game
        + [_inactive("Tampa Bay Buccaneers", "Y", "2026-11-22T16:40Z")]                             # one row so far
        + [_inactive("Kansas City Chiefs", p, "2026-11-22T16:40Z") for p in ("E", "F", "G")])       # its 4:25 game


def test_a_clubs_list_is_posted_for_its_game():
    posted = I.inactives_posted(ROWS, GAMES, now=NOW)
    assert set(posted) == {"BAL"}, posted
    assert posted["BAL"] == {"marlon humphrey", "nnamdi madubuike", "elijah sarratt"}
    # The 4:25 game's window opens 100 minutes before it: at 2:50 PM ET its list counts.
    later = dt.datetime(2026, 11, 22, 19, 50, tzinfo=dt.timezone.utc).timestamp()
    rows = ROWS + [_inactive("Kansas City Chiefs", p, "2026-11-22T19:47Z") for p in ("H", "I", "J")]
    assert set(I.inactives_posted(rows, GAMES, now=later)) >= {"KC"}
    sentences = [_inactive("Baltimore Ravens", p, comment=f"{p} was declared inactive Sunday.") for p in ("X", "Y", "Z")]
    assert I.inactives_posted(sentences, GAMES, now=NOW) == {"BAL": {"x", "y", "z"}}, "the note in a sentence counts"
    assert I.inactives_posted(sentences[:2], GAMES, now=NOW) == {}, "two names are no list yet"


def test_a_man_still_listed_and_not_on_it_is_active():
    inj = [Injury("Lamar Jackson", "BAL", "QB", "qb", "QUESTIONABLE"),
           Injury("Zay Flowers", "BAL", "WR", "wr1", "DOUBTFUL"),
           Injury("Marlon Humphrey", "BAL", "CB", "cb1", "OUT"),
           Injury("Baker Mayfield", "TB", "QB", "qb", "QUESTIONABLE")]
    cleared = I.clear_the_active(inj, I.inactives_posted(ROWS, GAMES, now=NOW))
    assert [(i.player, i.status, i.cleared) for i in cleared] == [
        ("Lamar Jackson", "ACTIVE", "QUESTIONABLE"), ("Zay Flowers", "ACTIVE", "DOUBTFUL")]
    assert inj[2].status == "OUT" and inj[3].status == "QUESTIONABLE", "on the list, or no list yet: as it was"

    class _P:
        player = "Lamar Jackson"
    assert player_injury_status(_P(), inj) == "", "no hold on his own props"
    was = os.environ.get(I.INACTIVES_ENV)
    os.environ[I.INACTIVES_ENV] = "off"
    try:
        assert I.inactives_posted(ROWS, GAMES, now=NOW) == {}
    finally:
        os.environ.pop(I.INACTIVES_ENV, None) if was is None else os.environ.__setitem__(I.INACTIVES_ENV, was)


def test_an_active_filing_in_his_window_clears_a_man_by_himself():
    # The board, 22 November: Mayfield filed "Active" at 11:36 AM ET, with no Buccaneers inactives on the board.
    rows = ROWS + [{"team": "Tampa Bay Buccaneers", "player": "Baker Mayfield", "status": "Active",
                    "comment": "Mayfield (foot/thumb) is listed as active Sunday at Detroit, Scott Smith of the "
                               "Buccaneers' official site reports.", "date": "2026-11-22T16:36Z"},
                   {"team": "Tampa Bay Buccaneers", "player": "Old Return", "status": "Active",
                    "comment": "returned", "date": "2026-11-20T16:36Z"}]
    active = I.active_filings(rows, GAMES, now=NOW)
    assert active == {"TB": {"baker mayfield"}}, active
    inj = [Injury("Baker Mayfield", "TB", "QB", "qb", "QUESTIONABLE"), Injury("Old Return", "TB", "WR", "wr", "QUESTIONABLE")]
    cleared = I.clear_the_active(inj, I.inactives_posted(rows, GAMES, now=NOW), active)
    assert [(i.player, i.cleared) for i in cleared] == [("Baker Mayfield", "QUESTIONABLE")], cleared
    assert inj[1].status == "QUESTIONABLE", "an Active filing from before the window clears nobody"


def test_the_build_reads_it_and_the_report_says_he_plays():
    nb = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert "_inactives = injuries_feed.inactives_posted(_board_rows, slate.games)" in nb
    assert "_active = injuries_feed.active_filings(_board_rows, slate.games)" in nb
    assert "live=live, inactives=_inactives, active=_active)" in nb and "Active after the inactives: " in nb
    src = (ROOT / "engine" / "sources" / "injuries.py").read_text(encoding="utf-8")
    assert "cleared = clear_the_active(week_injuries, inactives or {}, active or {})" in src
    g = {"home": "BAL", "away": "NYJ", "date": "2026-11-22", "kickoff": "13:00",
         "scan": {"injuries": [{"player": "Lamar Jackson", "team": "BAL", "position": "QB", "status": "ACTIVE",
                                "cleared": "QUESTIONABLE", "opens": ""}]}}
    c = GR.Ctx(g, {"games": [g]}, sport="nfl", names={"BAL": "Ravens", "NYJ": "Jets"})
    import json
    text = json.dumps(GR.sec_injuries(c))
    assert "Lamar Jackson (QB) \\u2014 active: not on the Ravens' inactives list (was questionable)" in text, text[:400]
    scan = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert '**({"cleared": str(i.cleared)} if getattr(i, "cleared", None) else {})' in scan


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
