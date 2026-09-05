"""The open-bet tracker on every league board, not only baseball's.

`renderLivePicks` reads `live_picks` off the VIEWED sport's board. Only
`mlb_build.py` ever wrote that key, so the Live tab on the NFL, CFB, NBA
and WNBA tabs said "No open bets on today's card" whatever the journal
held — and Ethan's 2026-09-05 request that the tab carry both the edge
bets and the Most Likely bets was delivered for one sport in five.

`engine.livepicks.attach_tracker` is the MLB block's assembly and
arithmetic behind one call: the same `assemble_live_picks`, the same
today-plus-neighbours window, the same "all open edge bets minus the
edge rows shown" count. This file drives it against a temporary journal
and a board shaped like the NFL's, then pins that each build calls it
before it writes its file.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                    # noqa: E402
from engine.livepicks import (attach_tracker, open_bets_for,  # noqa: E402
                              shift_day, TRACKER_CATEGORIES)


def _journal():
    """A fresh journal in a temp dir, with the real schema."""
    d = tempfile.mkdtemp()
    conn = ledger.connect(os.path.join(d, "ledger.db"))
    return conn


def _bet(conn, sport, date, player, market, side="OVER", line=0.5,
         odds=-110, stake=0.5, category="main", status="open"):
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, "
        "odds, stake_units, status, category, hit_prob) "
        "VALUES ('2026-09-05T00:00:00', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.55)",
        (sport, date, player, market, side, line, odds, stake, status,
         category))
    conn.commit()


def _board(state="live"):
    """An NFL-shaped board: one game in progress, two players on it."""
    return {
        "date": "2026-W01", "sport": "nfl",
        "games": [{"home": "KC", "away": "DET", "date": "2026-09-10",
                   "kickoff": "2026-09-11T00:20:00Z",
                   "live": {"state": state, "home_score": 14,
                            "away_score": 10, "period": "Q2"}}],
        "recommendations": [
            {"player": "Travis Kelce", "market": "rec_yds", "team": "KC",
             "opponent": "DET", "headshot": "kelce.png", "projection": 61.0},
            {"player": "Jahmyr Gibbs", "market": "rush_yds", "team": "DET",
             "opponent": "KC", "headshot": "", "projection": 74.0},
        ],
        "long_shots": [
            {"player": "Amon-Ra St. Brown", "market": "anytime_td",
             "team": "DET", "opponent": "KC", "headshot": "", "projection": 0.4},
        ],
    }


# --- the window ----------------------------------------------------------------
def test_a_week_label_has_no_neighbouring_days():
    assert shift_day("2026-W01", -1) == "2026-W01"
    assert shift_day("2026-W01", 1) == "2026-W01"
    assert shift_day("2026-08-31", 1) == "2026-09-01"       # month boundary
    assert shift_day("2026-12-31", 1) == "2027-01-01"       # year boundary
    assert shift_day("", 1) == ""


def test_open_bets_are_this_sports_open_rows_in_the_tracked_categories():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "Travis Kelce", "rec_yds", line=60.5)
    _bet(conn, "nfl", "2026-W01", "Jahmyr Gibbs", "rush_yds", line=70.5,
         category="likely", stake=0.1)
    _bet(conn, "nfl", "2026-W01", "Amon-Ra St. Brown", "anytime_td",
         category="longshot", odds=180)
    _bet(conn, "nfl", "2026-W01", "Sam LaPorta", "receptions",
         category="longshot_watch")               # the calibration sample
    _bet(conn, "nfl", "2026-W01", "Patrick Mahomes", "pass_yds",
         status="won")                            # settled
    _bet(conn, "mlb", "2026-W01", "Aaron Judge", "home_runs")   # other sport
    today, near = open_bets_for(conn, "nfl", "2026-W01")
    assert sorted(r["player"] for r in today) == \
        ["Amon-Ra St. Brown", "Jahmyr Gibbs", "Travis Kelce"], today
    assert {r["category"] for r in today} == set(TRACKER_CATEGORIES)
    assert near == [], "a week label has no neighbours to ask for"


def test_an_iso_card_also_asks_the_neighbouring_days():
    conn = _journal()
    _bet(conn, "wnba", "2026-09-05", "A'ja Wilson", "pts", line=22.5)
    _bet(conn, "wnba", "2026-09-06", "Caitlin Clark", "ast", line=7.5)
    _bet(conn, "wnba", "2026-09-04", "Napheesa Collier", "reb", line=9.5)
    _bet(conn, "wnba", "2026-09-07", "Kelsey Plum", "pts", line=19.5)
    today, near = open_bets_for(conn, "wnba", "2026-09-05")
    assert [r["player"] for r in today] == ["A'ja Wilson"]
    assert sorted(r["player"] for r in near) == \
        ["Caitlin Clark", "Napheesa Collier"], near


# --- the assembly --------------------------------------------------------------
def test_every_open_bet_on_the_card_lands_on_the_board_with_its_category():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "Travis Kelce", "rec_yds", line=60.5)
    _bet(conn, "nfl", "2026-W01", "Jahmyr Gibbs", "rush_yds", line=70.5,
         category="likely", stake=0.1)
    _bet(conn, "nfl", "2026-W01", "Amon-Ra St. Brown", "anytime_td",
         category="longshot", odds=180)
    _bet(conn, "nfl", "2026-W01", "KC", "moneyline", odds=-150)
    _bet(conn, "nfl", "2026-W01", "DET@KC", "total", side="OVER", line=47.5)
    result = _board()
    note = attach_tracker(result, "nfl", conn=conn)
    rows = {r["player"]: r for r in result["live_picks"]}
    assert set(rows) == {"Travis Kelce", "Jahmyr Gibbs", "Amon-Ra St. Brown",
                         "KC", "DET@KC"}, set(rows)
    assert all(r["phase"] == "live" for r in rows.values()), rows
    assert all(r["status"] != "unmapped" for r in rows.values()), rows
    assert rows["Jahmyr Gibbs"]["category"] == "likely"
    assert rows["Amon-Ra St. Brown"]["category"] == "longshot", \
        "the TD long shot mapped through the long-shot board"
    assert rows["Travis Kelce"]["headshot"] == "kelce.png"
    # Team markets track from the live score the board already carries.
    assert rows["DET@KC"]["current"] == 24.0
    assert rows["KC"]["game"]["home"] == "KC"
    assert "5 on this card (5 live, 1 likely)" in note, note
    assert "live_picks_error" not in result


def test_the_elsewhere_count_is_every_open_edge_bet_minus_the_edge_rows_shown():
    """Likely rows are on the tracker and NOT in the masthead's count, so
    they are neither counted nor subtracted."""
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "Travis Kelce", "rec_yds", line=60.5)
    _bet(conn, "nfl", "2026-W01", "Jahmyr Gibbs", "rush_yds", line=70.5,
         category="likely", stake=0.1)
    _bet(conn, "mlb", "2026-09-05", "Aaron Judge", "home_runs", odds=300,
         category="longshot")
    _bet(conn, "cfb", "2026-09-06", "UGA", "moneyline", odds=-200)
    result = _board()
    attach_tracker(result, "nfl", conn=conn)
    assert len(result["live_picks"]) == 2
    assert result["open_elsewhere"] == 2, result["open_elsewhere"]


def test_a_neighbour_days_bet_shows_only_if_it_lands_on_this_card():
    conn = _journal()
    _bet(conn, "wnba", "2026-09-05", "A'ja Wilson", "pts", line=22.5)
    _bet(conn, "wnba", "2026-09-06", "Caitlin Clark", "ast", line=7.5)
    _bet(conn, "wnba", "2026-09-06", "Someone Else", "pts", line=9.5)
    result = {
        "date": "2026-09-05", "sport": "wnba",
        "games": [{"home": "LVA", "away": "IND", "date": "2026-09-05",
                   "live": {"state": "live", "home_score": 40,
                            "away_score": 38}}],
        "recommendations": [
            {"player": "A'ja Wilson", "market": "pts", "team": "LVA",
             "opponent": "IND", "projection": 24.0},
            {"player": "Caitlin Clark", "market": "ast", "team": "IND",
             "opponent": "LVA", "projection": 8.0},
        ],
    }
    attach_tracker(result, "wnba", conn=conn)
    got = {r["player"]: r["status"] for r in result["live_picks"]}
    assert got == {"A'ja Wilson": "tracking", "Caitlin Clark": "tracking"}, got


def test_todays_unmapped_bet_is_kept_so_the_count_reconciles():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "Nobody On The Board", "rec_yds", line=1.5)
    result = _board()
    attach_tracker(result, "nfl", conn=conn)
    assert [r["status"] for r in result["live_picks"]] == ["unmapped"]


def test_a_scheduled_game_is_upcoming_and_a_final_grades_on_the_spot():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "DET@KC", "total", side="OVER", line=20.5)
    up = _board(state="scheduled")
    attach_tracker(up, "nfl", conn=conn)
    assert up["live_picks"][0]["phase"] == "upcoming"
    done = _board(state="final")
    attach_tracker(done, "nfl", conn=conn)
    assert done["live_picks"][0]["phase"] == "final"


def test_a_dead_journal_is_written_into_the_board_not_only_printed():
    class Dead:
        def execute(self, *a, **k):
            raise RuntimeError("database is locked")

        def close(self):
            pass
    result = _board()
    note = attach_tracker(result, "nfl", conn=Dead())
    assert "database is locked" in result["live_picks_error"]
    assert "tracker error" in note
    assert "live_picks" not in result


def test_no_open_bets_says_nothing_and_writes_an_empty_tracker():
    result = _board()
    assert attach_tracker(result, "nfl", conn=_journal()) == ""
    assert result["live_picks"] == [] and result["open_elsewhere"] == 0


# --- the builds ----------------------------------------------------------------
def _src(name):
    return (ROOT / name).read_text()


def test_each_board_attaches_the_tracker_before_it_writes_its_file():
    for build, sport, write in (
            ("nfl_build.py", '"nfl"', "gate.publish(result, args.out)"),
            ("cfb_build.py", '"cfb"', "_write(out, args.out)"),
            ("nba_build.py", "args.league", "gate.publish(out, p)")):
        s = _src(build)
        call = f"attach_tracker("
        assert s.count(call) == 1, (build, s.count(call))
        i = s.index(call)
        assert sport in s[i:i + 120], (build, s[i:i + 120])
        # The LAST write is the main path's; cfb_build publishes an empty
        # board early on an unreachable schedule, and that exit carries
        # no picks to track.
        assert i < s.rindex(write), f"{build}: the tracker is attached after the file is written"


def test_the_mlb_block_is_left_as_it_was():
    """MLB carries the boxscore fetch, the pitcher set and the identity
    map inline; the helper takes those as arguments and does not replace
    the block."""
    s = _src("mlb_build.py")
    assert "assemble_live_picks(open_today" in s
    assert "attach_tracker(" not in s


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
