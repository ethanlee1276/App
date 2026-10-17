"""ESPN's live injury board reaches the NFL model, merged over the weekly report.

Ethan, 2026-09-07: "Confirm all of our models and game scripts and all of
that are updating to live injuries. An example is RB2 Isiah Pacheco is
now out till October 11th ... make sure we are adjusting if needed and
reading this data and adjusting everything live and everything is up to
date."

They were not. The NFL slate's injuries came from ONE source, nflverse's
weekly report — the club's filed designation, re-downloaded twice a day
— which never lists a man on injured reserve (he is off the active
roster and files nothing) and cannot list a Saturday move. ESPN's
current-status board, which the injuries page and the news tape have
read since August, knew about the reserve move and the return date;
nothing carried it to the model. Now `injuries.live_injuries` turns that
board into the engine's `Injury` objects, `merge_injuries` lays it over
the weekly report, and the build passes the merged list to the slate.

Everything here is fixture-driven; nothing reaches the network.

Run directly: `python3 tests/test_live_injuries.py`
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.sources import injuries as inj                       # noqa: E402
from engine.sources.fetch import DataUnavailable                 # noqa: E402
from engine.models import (Team, DefenseProfile, Weather, Game, Prop, GameLog,  # noqa: E402
                           SportsbookLine, RUSH_YDS, PASS_YDS, Injury)
from engine.data_loader import Slate                             # noqa: E402

NOW = dt.datetime(2026, 9, 7, 20, 0, tzinfo=dt.timezone.utc).timestamp()


def _iso(days_ago: float) -> str:
    return (dt.datetime.fromtimestamp(NOW, dt.timezone.utc)
            - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _espn(player, team, status, days_ago=1.0, pos="RB", date=True, injury="Knee"):
    """One row the way `espninjuries.parse_injuries` writes it."""
    return {"team": team, "player": player, "pos": pos, "status": status,
            "date": _iso(days_ago) if date else None, "injury": injury,
            "side": None, "return_date": None, "comment": None, "face": None}


LIVE = [
    # The example: a back on reserve, filed three days ago. The weekly
    # report will never carry this row.
    _espn("Isiah Pacheco", "Kansas City Chiefs", "Injured Reserve", 3),
    # A game-week designation, current.
    _espn("Josh Allen", "Buffalo Bills", "Questionable", 1, pos="QB"),
    # A game-week designation from last week: dropped.
    _espn("Old News", "Buffalo Bills", "Questionable", 9, pos="WR"),
    # An undated Questionable can never age out: dropped.
    _espn("No Date", "Buffalo Bills", "Doubtful", date=False, pos="TE"),
    # A cleared-to-play notice is not a designation.
    _espn("Back Again", "Kansas City Chiefs", "Active", 1, injury=None),
    # A practice note, not a game designation: unmapped, dropped.
    _espn("Practice Note", "Kansas City Chiefs", "Day-To-Day", 1),
    # A suspension keeps a man off the field the same as an injury.
    _espn("Sat Down", "Kansas City Chiefs", "Suspension", 2, pos="CB"),
    # The reserve lists ESPN spells several ways.
    _espn("On Pup", "Buffalo Bills", "Physically Unable to Perform", 40, pos="OT"),
    # A team the slate cannot key is dropped rather than guessed.
    _espn("Nobody", "Rhein Fire", "Out", 1),
    # OUT is a standing status: an old filing still stands.
    _espn("Long Out", "Kansas City Chiefs", "Out", 30, pos="WR"),
]


def test_the_live_board_becomes_engine_injuries_keyed_like_the_slate():
    got = {i.player: i for i in inj.live_injuries(LIVE, now=NOW)}
    assert set(got) == {"Isiah Pacheco", "Josh Allen", "Sat Down", "On Pup",
                        "Long Out"}, sorted(got)
    assert (got["Isiah Pacheco"].team, got["Isiah Pacheco"].status,
            got["Isiah Pacheco"].position) == ("KC", "IR", "RB")
    assert (got["Josh Allen"].team, got["Josh Allen"].status) == ("BUF", "QUESTIONABLE")
    assert got["Sat Down"].status == "OUT" and got["Sat Down"].role == "cb1"
    assert got["On Pup"].status == "IR" and got["On Pup"].role == "OT"
    assert got["Long Out"].status == "OUT"


def test_the_newest_filing_per_player_wins():
    """A man hurt, cleared and hurt again appears three times on ESPN's
    board; the model reads the newest, the same way the page does."""
    rows = [_espn("Twice", "Buffalo Bills", "Out", 10, pos="WR"),
            _espn("Twice", "Buffalo Bills", "Active", 5, injury=None),
            _espn("Twice", "Buffalo Bills", "Questionable", 1, pos="WR")]
    got = inj.live_injuries(rows, now=NOW)
    assert [(i.player, i.status) for i in got] == [("Twice", "QUESTIONABLE")]
    # …and cleared last means not listed at all.
    got = inj.live_injuries(rows[:2], now=NOW)
    assert got == []


def test_the_merge_keeps_the_more_severe_designation_and_counts_additions():
    weekly = [Injury("Josh Allen", "BUF", "QB", "qb", "QUESTIONABLE"),
              Injury("Ed Oliver", "BUF", "DT", "dt", "OUT")]
    live = [Injury("Josh Allen", "BUF", "QB", "qb", "OUT"),        # worsened
            Injury("Ed Oliver", "BUF", "DT", "dt", "QUESTIONABLE"),  # cheerier: ignored
            Injury("Isiah Pacheco", "KC", "RB", "rb", "IR")]        # only live
    merged, added = inj.merge_injuries(weekly, live)
    by = {i.player: i for i in merged}
    assert added == 1 and set(by) == {"Josh Allen", "Ed Oliver", "Isiah Pacheco"}
    assert by["Josh Allen"].status == "OUT"
    assert by["Ed Oliver"].status == "OUT"
    assert by["Isiah Pacheco"].status == "IR"
    # The weekly row object is kept (its role may have been refined).
    assert by["Josh Allen"] is weekly[0]
    # Names join loosely: a suffix on one side is the same man.
    merged, added = inj.merge_injuries(
        [Injury("Marvin Harrison", "ARI", "WR", "wr", "QUESTIONABLE")],
        [Injury("Marvin Harrison Jr.", "ARI", "WR", "wr", "DOUBTFUL")])
    assert added == 0 and len(merged) == 1 and merged[0].status == "DOUBTFUL"


def _row(name, team, pos, status, week=5):
    return {"season": "2026", "week": str(week), "team": team, "position": pos,
            "full_name": name, "report_status": status}


WEEKLY = [_row("Josh Allen", "BUF", "QB", "Questionable"),
          _row("Ed Oliver", "BUF", "DT", "Out")]


def _slate():
    teams = {"KC": Team("KC", "KC", DefenseProfile("KC")),
             "BUF": Team("BUF", "BUF", DefenseProfile("BUF"))}
    game = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-2.5, total=47.0)
    allen = Prop("Josh Allen", "BUF", "KC", "QB", PASS_YDS,
                 [GameLog(w, "X", 260) for w in range(1, 6)], 255, None,
                 [SportsbookLine("proxy", 250.0)], "starter")
    pacheco = Prop("Isiah Pacheco", "KC", "BUF", "RB", RUSH_YDS,
                   [GameLog(w, "X", 70) for w in range(1, 6)], 68, None,
                   [SportsbookLine("proxy", 65.0)], "rb1")
    return Slate("2026-W05", teams, [game], [allen, pacheco])


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val
    def __enter__(self):
        self.old = getattr(self.obj, self.name); setattr(self.obj, self.name, self.val)
    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


def test_the_reserve_move_reaches_the_slate_and_holds_the_prop():
    """The weekly report says nothing about Pacheco; the live board
    does; the slate holds him and the game carries the row."""
    slate = _slate()
    live = inj.live_injuries(LIVE, now=NOW)
    with _Swap(inj, "load_injuries", lambda season: WEEKLY):
        res = inj.attach_injuries_to_slate(slate, 2026, 5, live=live)
    assert res.weekly == 2 and res.live == 5 and res.live_added == 4, res
    assert res.total == 6 and res.weekly_error is None
    assert set(res.holds) == {"Josh Allen", "Isiah Pacheco"}
    names = {i.player: i.status for i in slate.games[0].injuries}
    assert names["Isiah Pacheco"] == "IR" and names["Ed Oliver"] == "OUT"
    assert res.by_status.get("IR") == 2 and res.by_status.get("OUT") == 3
    # …and the rules engine holds the prop on the merged status.
    from engine.pipeline import run_slate
    out = run_slate(slate)
    pacheco = next(r for r in out["recommendations"] if r["player"] == "Isiah Pacheco")
    assert pacheco["recommended"] is False
    assert pacheco["injury_status"] == "IR", pacheco["injury_status"]


def test_a_live_row_takes_the_slates_spelling_so_the_hold_can_see_it():
    slate = _slate()
    live = inj.live_injuries([_espn("Isiah Pacheco Jr.", "Kansas City Chiefs",
                                    "Injured Reserve", 2)], now=NOW)
    with _Swap(inj, "load_injuries", lambda season: WEEKLY):
        res = inj.attach_injuries_to_slate(slate, 2026, 5, live=live)
    assert "Isiah Pacheco" in res.holds, res.holds
    assert any(i.player == "Isiah Pacheco" and i.status == "IR"
               for i in slate.games[0].injuries)


def test_without_a_live_board_nothing_changes():
    slate = _slate()
    with _Swap(inj, "load_injuries", lambda season: WEEKLY):
        res = inj.attach_injuries_to_slate(slate, 2026, 5)
    assert (res.total, res.weekly, res.live, res.live_added) == (2, 2, 0, 0)
    assert res.holds == ["Josh Allen"]


def test_the_live_board_carries_the_slate_when_the_weekly_report_is_missing():
    """nflverse's file is a 404 until it publishes a season's first
    week. With a live board in hand that is a note, not an empty slate;
    with none it raises as it always did."""
    def missing(season):
        raise DataUnavailable("injuries_2026.csv: HTTP 404")
    slate = _slate()
    live = inj.live_injuries(LIVE, now=NOW)
    with _Swap(inj, "load_injuries", missing):
        res = inj.attach_injuries_to_slate(slate, 2026, 5, live=live)
    assert res.weekly == 0 and res.live_added == 5 and res.total == 5
    assert "404" in (res.weekly_error or "")
    assert "Isiah Pacheco" in res.holds
    with _Swap(inj, "load_injuries", missing):
        try:
            inj.attach_injuries_to_slate(_slate(), 2026, 5)
        except DataUnavailable:
            pass
        else:
            raise AssertionError("no live board and no weekly report must still raise")


def test_a_questionable_for_a_game_already_played_is_dropped_by_the_slates_week():
    """The first live-board build (Monday 2026-09-07) held 66 props, 56
    on Questionable: Friday's designations for Sunday's games, three
    days old, on men who had played. The slate's own week is the clock —
    a Questionable filed before this team's week began is last week's."""
    slate = _slate()                      # KC at home to BUF
    slate.games[0].date = "2026-09-10"    # Thursday night, Week 2
    since = inj.week_starts(slate)
    assert set(since) == {"KC", "BUF"}
    start = dt.datetime(2026, 9, 5, tzinfo=dt.timezone.utc).timestamp()
    assert since["KC"] == start and since["BUF"] == start
    rows = [_espn("Josh Allen", "Buffalo Bills", "Questionable", 3, pos="QB"),   # Fri 09-04
            _espn("New Doubt", "Buffalo Bills", "Doubtful", 0.2, pos="WR"),      # this week
            _espn("Long Out", "Kansas City Chiefs", "Out", 30, pos="WR"),        # stands
            _espn("Isiah Pacheco", "Kansas City Chiefs", "Injured Reserve", 3)]  # stands
    got = {i.player: i.status for i in inj.live_injuries(rows, now=NOW, since=since)}
    assert got == {"New Doubt": "DOUBTFUL", "Long Out": "OUT", "Isiah Pacheco": "IR"}, got
    # Without the slate's week the flat window keeps Friday's row — the
    # fallback, and the behaviour this test exists to retire from the build.
    assert "Josh Allen" in {i.player for i in inj.live_injuries(rows, now=NOW)}
    # A team not on the slate keeps the flat window.
    rows.append(_espn("Elsewhere", "Detroit Lions", "Questionable", 3, pos="TE"))
    got = {i.player for i in inj.live_injuries(rows, now=NOW, since=since)}
    assert "Elsewhere" in got and "Josh Allen" not in got
    # A game with no date contributes nothing rather than crashing.
    slate.games[0].date = ""
    assert inj.week_starts(slate) == {}


def test_the_build_fetches_the_live_board_and_passes_it_through():
    """The wiring, read from the build script: the live board is loaded
    under its own guard (a blip costs a note, never the board), handed to
    the attach step, and the payload says what each source carried."""
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "live = injuries_feed.load_live_injuries(slate)" in src
    assert "attach_injuries_to_slate(slate, args.season, args.week,\n" \
           "                                                        live=live)" in src
    assert 'injury_status["live_error"] = str(exc)' in src
    assert "live_added=ir.live_added" in src
    assert '"nflverse+espn" if live is not None else "nflverse"' in src
    # The load function reads the cached board inside the page's TTL.
    import inspect
    body = inspect.getsource(inj.load_live_injuries)
    assert 'fetch_injuries("nfl")' in body and "parse_injuries(" in body
    assert "since=week_starts(slate)" in body


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
