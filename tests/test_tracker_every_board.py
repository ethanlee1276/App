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
from engine.livepicks import (attach_tracker, espn_progress,  # noqa: E402
                              open_bets_for, shift_day,
                              PROGRESS_MAX_GAMES, TRACKER_CATEGORIES)


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
    note = attach_tracker(result, "nfl", conn=conn, progress={})
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
    attach_tracker(result, "nfl", conn=conn, progress={})
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
    attach_tracker(result, "wnba", conn=conn, progress={})
    got = {r["player"]: r["status"] for r in result["live_picks"]}
    assert got == {"A'ja Wilson": "tracking", "Caitlin Clark": "tracking"}, got


def test_todays_unmapped_bet_is_kept_so_the_count_reconciles():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "Nobody On The Board", "rec_yds", line=1.5)
    result = _board()
    attach_tracker(result, "nfl", conn=conn, progress={})
    assert [r["status"] for r in result["live_picks"]] == ["unmapped"]


def test_a_scheduled_game_is_upcoming_and_a_final_grades_on_the_spot():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "DET@KC", "total", side="OVER", line=20.5)
    up = _board(state="scheduled")
    attach_tracker(up, "nfl", conn=conn, progress={})
    assert up["live_picks"][0]["phase"] == "upcoming"
    done = _board(state="final")
    attach_tracker(done, "nfl", conn=conn, progress={})
    assert done["live_picks"][0]["phase"] == "final"


def test_a_dead_journal_is_written_into_the_board_not_only_printed():
    class Dead:
        def execute(self, *a, **k):
            raise RuntimeError("database is locked")

        def close(self):
            pass
    result = _board()
    note = attach_tracker(result, "nfl", conn=Dead(), progress={})
    assert "database is locked" in result["live_picks_error"]
    assert "tracker error" in note
    assert "live_picks" not in result


def test_no_open_bets_says_nothing_and_writes_an_empty_tracker():
    result = _board()
    assert attach_tracker(result, "nfl", conn=_journal(), progress={}) == ""
    assert result["live_picks"] == [] and result["open_elsewhere"] == 0


# --- the live stat line --------------------------------------------------------
def _nfl_summary(rec_yds="61", receptions="5"):
    """ESPN's `boxscore.players` as `nflpreseason.parse_boxscore` reads
    it: a block per stat group, LABELS naming the columns."""
    return {"boxscore": {"players": [
        {"team": {"abbreviation": "KC"}, "statistics": [
            {"name": "receiving",
             "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [{"athlete": {"displayName": "Travis Kelce",
                                       "position": {"abbreviation": "TE"}},
                           "stats": [receptions, rec_yds, "12.2", "0", "23", "7"]}]}]},
        {"team": {"abbreviation": "DET"}, "statistics": [
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [{"athlete": {"displayName": "Jahmyr Gibbs",
                                       "position": {"abbreviation": "RB"}},
                           "stats": ["9", "44", "4.9", "1", "18"]}]}]},
    ]}}


def _wnba_summary():
    """As `espnhoops.parse_summary` reads it: NAMES, not labels."""
    return {"boxscore": {"players": [
        {"team": {"abbreviation": "LV"}, "statistics": [
            {"names": ["MIN", "PTS", "REB", "AST", "3PT"],
             "athletes": [{"athlete": {"id": "1", "displayName": "A'ja Wilson"},
                           "stats": ["30", "22", "9", "3", "1-4"]}]}]}]}}


def _stubbed(rows, summaries):
    """Point the fetcher at fixtures: the scoreboard rows and a summary
    per event id. Returns the live event ids that were asked for."""
    from engine.sources import livescores, espnplays
    asked = []

    def rows_fn(league, ttl=30):
        return rows

    def summary_fn(league, eid, ttl=30):
        asked.append((league, eid))
        if eid not in summaries:
            raise RuntimeError("ESPN refused")
        return summaries[eid]
    return livescores, espnplays, rows_fn, summary_fn, asked


def _with_stubs(rows, summaries, fn):
    livescores, espnplays, rows_fn, summary_fn, asked = _stubbed(rows, summaries)
    real = livescores.fetch_rows, espnplays.fetch_summary
    livescores.fetch_rows, espnplays.fetch_summary = rows_fn, summary_fn
    try:
        return fn(), asked
    finally:
        livescores.fetch_rows, espnplays.fetch_summary = real


SB = [{"event_id": "401", "home": "KC", "away": "DET", "live": None},
      {"event_id": "402", "home": "LVA", "away": "IND", "live": None}]


def test_football_progress_is_keyed_and_named_like_the_mlb_trackers():
    games = _board()["games"]
    (prog, note), asked = _with_stubs(SB, {"401": _nfl_summary()},
                                      lambda: espn_progress("nfl", games))
    assert asked == [("nfl", "401")], asked
    k = prog["travis kelce"]
    assert (k["receptions"], k["rec_yds"]) == (5.0, 61.0), k
    assert prog["jahmyr gibbs"]["rush_yds"] == 44.0
    # The parser derives `anytime_td` from the TD columns, so a TD long
    # shot on the tracker clears the moment the back scores.
    assert prog["jahmyr gibbs"]["anytime_td"] == 1.0, prog["jahmyr gibbs"]
    assert "live stats: 1 of 1 live game(s)" in note, note


def test_hoops_progress_reads_the_box_score_by_column_name():
    games = [{"home": "LVA", "away": "IND", "live": {"state": "live"}}]
    (prog, _), asked = _with_stubs(SB, {"402": _wnba_summary()},
                                   lambda: espn_progress("wnba", games))
    assert asked == [("wnba", "402")]
    # Keyed by the SAME function the tracker looks a bet up with — it
    # strips the apostrophe, and a literal key here would test the test.
    from engine.sources.oddsapi import normalize_name
    assert prog[normalize_name("A'ja Wilson")] == {
        "min": 30.0, "pts": 22.0, "reb": 9.0, "ast": 3.0, "fg3m": 1.0}, prog


def test_only_live_games_are_fetched_and_a_missing_id_is_counted():
    games = [{"home": "KC", "away": "DET", "live": {"state": "live"}},
             {"home": "BUF", "away": "NYJ", "live": {"state": "live"}},
             {"home": "LAR", "away": "SF", "live": {"state": "scheduled"}}]
    (prog, note), asked = _with_stubs(SB, {"401": _nfl_summary()},
                                      lambda: espn_progress("nfl", games))
    assert asked == [("nfl", "401")], asked
    assert "1 of 2 live game(s)" in note and "1 not on the scoreboard" in note, note


def test_one_dead_feed_costs_that_games_numbers_and_nothing_else():
    games = [{"home": "KC", "away": "DET", "live": {"state": "live"}},
             {"home": "LVA", "away": "IND", "live": {"state": "live"}}]
    (prog, note), _ = _with_stubs(SB, {"401": _nfl_summary()},
                                  lambda: espn_progress("nfl", games))
    assert "travis kelce" in prog
    assert "1 feed(s) unreachable" in note, note


def test_an_unreachable_scoreboard_is_no_numbers_and_says_so():
    from engine.sources import livescores
    real = livescores.fetch_rows

    def dead(league, ttl=30):
        raise RuntimeError("Tunnel connection failed")
    livescores.fetch_rows = dead
    try:
        prog, note = espn_progress("nfl", _board()["games"])
    finally:
        livescores.fetch_rows = real
    assert prog == {} and "scoreboard unreachable" in note, note


def test_the_cap_holds_and_the_note_says_so():
    games = [{"home": f"H{i}", "away": f"A{i}", "live": {"state": "live"}}
             for i in range(PROGRESS_MAX_GAMES + 3)]
    rows = [{"event_id": str(i), "home": f"H{i}", "away": f"A{i}", "live": None}
            for i in range(PROGRESS_MAX_GAMES + 3)]
    (_, note), asked = _with_stubs(rows, {str(i): _wnba_summary()
                                          for i in range(PROGRESS_MAX_GAMES + 3)},
                                   lambda: espn_progress("wnba", games))
    assert len(asked) == PROGRESS_MAX_GAMES, len(asked)
    assert f"3 past the {PROGRESS_MAX_GAMES}-game cap" in note, note


def test_a_league_without_an_espn_scoreboard_fetches_nothing():
    assert espn_progress("mlb", _board()["games"]) == ({}, "")
    assert espn_progress("nfl", []) == ({}, "")


def test_the_tracker_fetches_progress_itself_and_the_bet_clears_on_it():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "Travis Kelce", "rec_yds", line=60.5)
    _bet(conn, "nfl", "2026-W01", "Jahmyr Gibbs", "rush_yds", side="UNDER",
         line=40.5, category="likely", stake=0.1)
    result = _board()
    note, _ = _with_stubs(SB, {"401": _nfl_summary()},
                          lambda: attach_tracker(result, "nfl", conn=conn))
    rows = {r["player"]: r for r in result["live_picks"]}
    assert rows["Travis Kelce"]["current"] == 61.0
    assert rows["Travis Kelce"]["status"] == "cleared", rows["Travis Kelce"]
    assert rows["Jahmyr Gibbs"]["status"] == "busted", rows["Jahmyr Gibbs"]
    assert "; live stats: 1 of 1 live game(s)" in note, note


def test_a_failing_progress_fetch_costs_the_numbers_not_the_tracker():
    conn = _journal()
    _bet(conn, "nfl", "2026-W01", "Travis Kelce", "rec_yds", line=60.5)
    result = _board()

    def boom(league, games):
        raise RuntimeError("no box score")
    note = attach_tracker(result, "nfl", conn=conn, fetcher=boom)
    assert result["live_picks"][0]["status"] == "tracking"
    assert result["live_picks"][0]["current"] is None
    assert "live stats unavailable: no box score" in note, note
    assert "live_picks_error" not in result


def test_the_live_payload_never_lands_under_a_settlement_cache_name():
    """The ingests cache a final for a month under `espn_nfl_box_`,
    `cfb_summary_` and `espn_{league}_box_`. A third-quarter snapshot
    under one of those names is the final the settler would read."""
    import inspect
    from engine import livepicks
    src = inspect.getsource(livepicks.espn_progress)
    assert "espnplays.fetch_summary(" in src
    for banned in ("fetch_boxscore(", "cfbdata.fetch_summary(",
                   "espnhoops.fetch_summary("):
        assert banned not in src, banned
    src2 = inspect.getsource(livepicks._box_rows)
    assert "fetch" not in src2.replace("fetched", ""), "the parser helper must not fetch"


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
