"""A closing line is the last price BEFORE the game — for every sport.

Audit 2026-09-30, P0-2 and P1-4 (`audit/01-integrity.md`). The NFL's free
snapshots were fixed forward on 2026-09-29, but four other paths still
let an in-game price become a "close":

  * the PAID harvest snapshots one hour a day (23:00 UTC by default) and
    stored every event on the list — including games already under way,
    whose event-odds endpoint returns in-play prices;
  * the builds' own game-line tape (`lineledger`) and injury prop tape
    (`proptape`) write every cycle, in-play games included, with no start
    time on the row, into the same `odds_history` table the closes are
    read from;
  * the settle path took whatever harvested row the date held, with no
    check against the bet's own kickoff (`bets.ts + lead_min`);
  * college football never recorded a line snapshot at all, and the free
    snapshot index keyed its day by the machine's clock (UTC on the box),
    so a 9 p.m. Eastern game's close was filed under the next day, and a
    doubleheader's second game lost every pre-game price after the first
    pitch of game one.

Each is closed here, and legacy rows without a start keep reading exactly
as before — the cut applies where the start is known, never on a guess.
"""

import datetime as _dt
import inspect
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, ledger, linemoves                            # noqa: E402
from engine.sources import oddshistory as oh                         # noqa: E402


def _epoch(iso):
    return _dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _row(taken, commence=None, over=-110, under=-110, line=1.5,
         player="aaron judge", market="hits", book="dk", date=None):
    return {"sport": "mlb", "taken_at": taken, "event_id": "e1",
            "home": "NYY", "away": "BOS", "player": player,
            "market": market, "book": book, "line": line,
            "over_odds": over, "under_odds": under,
            "commence_time": commence}


# --- the harvested table -----------------------------------------------------
def test_the_price_table_keeps_each_games_start():
    conn = db.connect(":memory:")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(odds_history)")}
    assert "commence_time" in cols
    assert "commence_time" in db.ODDS_HIST_COLS


def test_a_harvested_price_taken_after_the_start_is_never_a_close():
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [
        _row("2026-07-24T22:00:00Z", "2026-07-24T23:05:00Z", over=-120),
        _row("2026-07-24T23:30:00Z", "2026-07-24T23:05:00Z", over=-400),
    ])
    got = db.closing_odds_by_date(conn, "mlb", "hits")
    assert got[("aaron judge", "2026-07-24")]["over_odds"] == -120, \
        "the 23:30 price is in play — the 22:00 one is the close"
    books = db.closing_odds_all_books(conn, "mlb", "hits")
    assert [q["over_odds"] for q in books[("aaron judge", "2026-07-24")]] == [-120]


def test_a_game_with_nothing_before_its_start_has_no_close():
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [
        _row("2026-07-24T23:30:00Z", "2026-07-24T23:05:00Z")])
    assert db.closing_odds_by_date(conn, "mlb", "hits") == {}
    assert db.closing_odds_all_books(conn, "mlb", "hits") == {}


def test_a_row_with_no_start_keeps_reading_as_it_always_has():
    conn = db.connect(":memory:")
    db.upsert_odds_history(conn, [_row("2026-07-24T23:30:00Z", None, over=-130)])
    assert db.closing_odds_by_date(conn, "mlb", "hits")[
        ("aaron judge", "2026-07-24")]["over_odds"] == -130


def test_a_table_built_before_the_column_still_reads():
    """Several fixtures (and any copy of an old history.db) hold an
    `odds_history` without the column; the reader must not break on one."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE odds_history (sport TEXT, taken_at TEXT, "
                 "event_id TEXT, home TEXT, away TEXT, player TEXT, market TEXT, "
                 "book TEXT, line REAL, over_odds INTEGER, under_odds INTEGER)")
    conn.execute("INSERT INTO odds_history VALUES ('mlb','2026-07-24T23:00:00Z',"
                 "'e','A','B','aaron judge','hits','dk',1.5,-110,-110)")
    assert ("aaron judge", "2026-07-24") in db.closing_odds_by_date(conn, "mlb", "hits")
    assert ("aaron judge", "2026-07-24") in db.closing_odds_all_books(conn, "mlb", "hits")


# --- where the start comes from ----------------------------------------------
def test_the_snapshot_parser_carries_the_events_start():
    snap = oh.Snapshot(requested="2026-07-24T23:00:00Z",
                       taken="2026-07-24T22:55:00Z",
                       data={"id": "e1", "home_team": "New York Yankees",
                             "away_team": "Boston Red Sox",
                             "commence_time": "2026-07-24T23:05:00Z",
                             "bookmakers": []})
    hist = oh.parse_snapshot(snap, "mlb")
    assert hist.commence == "2026-07-24T23:05:00Z"
    hist.moneylines = {"NYY": -150, "BOS": 130}
    rows = oh.to_rows(hist)
    assert rows and all(r["commence_time"] == "2026-07-24T23:05:00Z" for r in rows)


def test_the_harvest_skips_an_event_already_under_way():
    import harvest_odds as ho
    taken = "2026-07-24T23:00:00Z"
    assert ho._already_started({"commence_time": "2026-07-24T22:10:00Z"}, taken)
    assert ho._already_started({"commence_time": "2026-07-24T23:00:00Z"}, taken)
    assert not ho._already_started({"commence_time": "2026-07-24T23:10:00Z"}, taken)
    assert not ho._already_started({}, taken), "no start = no guess"
    src = inspect.getsource(ho)
    i = src.index("for ev in events:")
    loop = src[i:src.index("fetch_historical_event_odds(", i)]
    assert "_already_started(ev, events_snap.taken)" in loop, \
        "the check has to run before the credits are spent"


def test_the_builds_game_line_tape_stamps_each_games_start():
    from engine import lineledger
    games = [{"home": "NYY", "away": "BOS", "date": "2026-07-24",
              "kickoff": "2026-07-24T23:05:00Z", "total": 8.5,
              "total_over_odds": -110, "total_under_odds": -110}]
    rows = lineledger.rows_for_games("mlb", games)
    assert rows and rows[0]["commence_time"] == "2026-07-24T23:05:00Z"
    # The NFL's kickoff is nflverse's bare Eastern clock.
    nfl = [{"home": "BUF", "away": "NYJ", "date": "2026-09-27",
            "kickoff": "13:00", "total": 44.5,
            "total_over_odds": -110, "total_under_odds": -110}]
    rows = lineledger.rows_for_games("nfl", nfl)
    assert rows[0]["commence_time"] == "2026-09-27T17:00:00Z"


def test_the_injury_prop_tape_stamps_each_games_start():
    from engine import proptape

    class _L:
        book, line, over_odds, under_odds = "dk", 1.5, -110, -110

    class _P:
        player, market, team, lines = "Aaron Judge", "hits", "NYY", [_L()]

    class _S:
        games = [{"home": "NYY", "away": "BOS", "date": "2026-07-24",
                  "kickoff": "2026-07-24T23:05:00Z"}]
        props = [_P()]

    rows = proptape.rows_for("mlb", _S(), {proptape._norm("Aaron Judge")}, {})
    assert rows and rows[0]["commence_time"] == "2026-07-24T23:05:00Z"


# --- the settle path ---------------------------------------------------------
def test_a_close_after_the_bets_own_kickoff_is_refused():
    b = {"ts": "2026-07-24T20:00:00", "lead_min": 60.0}       # kickoff 21:00Z
    late = {"line": 1.5, "over_odds": -300, "taken_at": "2026-07-24T23:00:00Z"}
    early = {"line": 1.5, "over_odds": -120, "taken_at": "2026-07-24T20:45:00Z"}
    assert ledger._pregame_close(late, b) is None
    assert ledger._pregame_close(early, b) is early
    # No kickoff on the row (legacy journal): no cut, as before.
    assert ledger._pregame_close(late, {"ts": "2026-07-24T20:00:00",
                                        "lead_min": None}) is late
    assert ledger._pregame_close(None, b) is None


def _settle(lead_min, monkey_snaps=None):
    conn = ledger.connect(":memory:")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    ledger.log_recommendations(conn, {
        "sport": "mlb", "date": "2026-07-24",
        "recommendations": [
            {"player": "Aaron Judge", "market": "total_bases", "side": "OVER",
             "line": 1.5, "book": "FanDuel", "odds": -120,
             "projection": 1.9, "hit_prob": 0.6, "edge": 0.08,
             "confidence": 7.5, "grade": "Play", "stake_units": 1.0,
             "recommended": True}]})
    conn.execute("UPDATE bets SET ts='2026-07-24T17:00:00', lead_min=?",
                  (lead_min,))
    conn.commit()
    hist = db.connect(":memory:")
    db.upsert_player_logs(hist, [
        {"sport": "mlb", "season": 2026, "period": "2026-07-24",
         "game_id": "g", "player": "Aaron Judge", "team": "NYY",
         "opponent": "BOS", "position": "RF", "home": 1,
         "market": "total_bases", "value": 2.0}])
    # A LEGACY harvested row — no start on it — taken at 23:00 UTC.
    db.upsert_odds_history(hist, [
        {"sport": "mlb", "taken_at": "2026-07-24T23:00:00Z", "event_id": "e",
         "home": "NYY", "away": "BOS", "player": "aaron judge",
         "market": "total_bases", "book": "DK", "line": 1.5,
         "over_odds": -250, "under_odds": 190}])
    saved = (ledger._snapshot_closes, ledger._snapshot_close_odds)
    snaps = monkey_snaps or ({}, {})
    ledger._snapshot_closes = lambda *a, **k: snaps[0]
    ledger._snapshot_close_odds = lambda *a, **k: snaps[1]
    try:
        assert ledger.settle_from_history(conn, hist, sport="mlb") == 1
    finally:
        ledger._snapshot_closes, ledger._snapshot_close_odds = saved
    return conn.execute("SELECT * FROM bets").fetchone()


def test_settling_refuses_a_harvested_close_taken_after_first_pitch():
    b = _settle(lead_min=120.0)                              # first pitch 19:00Z
    assert b["status"] == "won"
    assert b["closing_line"] is None and b["closing_odds"] is None, \
        "a 23:00 UTC price on a 19:00 UTC game is an in-play number"


def test_settling_keeps_a_harvested_close_taken_before_first_pitch():
    b = _settle(lead_min=360.0)                              # first pitch 23:00Z…
    assert b["closing_odds"] is None, "…at the start is not before it"
    b = _settle(lead_min=365.0)                              # 23:05Z
    assert int(b["closing_odds"]) == -250 and b["closing_line"] == 1.5


def test_settling_falls_back_to_the_free_snapshots_when_the_harvest_is_late():
    idx = linemoves._CloseIndex({("aaron judge", "total_bases", "2026-07-24"): 1.5})
    idx.stamped.add(("aaron judge", "total_bases", "2026-07-24"))
    odds = {("aaron judge", "total_bases", "2026-07-24", 1.5):
            {"over": -135, "under": 110}}
    b = _settle(lead_min=120.0, monkey_snaps=(idx, odds))
    assert b["closing_line"] == 1.5 and int(b["closing_odds"]) == -135


def test_a_stamped_snapshot_close_beats_an_unverifiable_harvested_one():
    """No kickoff on the bet, no start on the harvested row: nothing proves
    the harvested price is pre-game. A snapshot close cut at a recorded
    start IS proven, so it wins."""
    idx = linemoves._CloseIndex({("aaron judge", "total_bases", "2026-07-24"): 1.5})
    idx.stamped.add(("aaron judge", "total_bases", "2026-07-24"))
    odds = {("aaron judge", "total_bases", "2026-07-24", 1.5):
            {"over": -135, "under": 110}}
    b = _settle(lead_min=None, monkey_snaps=(idx, odds))
    assert int(b["closing_odds"]) == -135


def test_the_backfill_applies_the_same_cut():
    src = inspect.getsource(ledger.repair_closing_odds)
    assert "_pregame_close(" in src
    assert "_pregame_close(" in inspect.getsource(ledger.settle_from_history)


# --- the free snapshots ------------------------------------------------------
def _snap(ts_iso, start_iso, line, over=-110, player="Aaron Judge"):
    r = {"ts": _epoch(ts_iso), "player": player, "market": "hits",
         "book": "dk", "line": line, "over_odds": over, "under_odds": -110}
    if start_iso:
        r["start_ts"] = _epoch(start_iso)
    return r


def test_a_late_eastern_game_is_filed_under_its_slate_day():
    """9:10 p.m. Eastern on the 26th is 01:10 UTC on the 27th. The bet is
    journaled under the 26th, and so must its close be."""
    rows = [_snap("2026-09-27T00:50:00Z", "2026-09-27T01:10:00Z", 1.5)]
    got = linemoves.closing_lines_by_date(rows)
    assert ("aaron judge", "hits", "2026-09-26") in got
    odds = linemoves.closing_odds_by_date(rows)
    assert ("aaron judge", "hits", "2026-09-26", 1.5) in odds


def test_a_doubleheaders_second_game_keeps_its_own_close():
    g1, g2 = "2026-07-24T17:05:00Z", "2026-07-24T23:05:00Z"
    rows = [_snap("2026-07-24T16:30:00Z", g1, 1.5, over=-120),
            _snap("2026-07-24T18:00:00Z", g1, 0.5, over=-900),   # in play
            _snap("2026-07-24T22:30:00Z", g2, 1.5, over=-140)]
    got = linemoves.closing_lines_by_date(rows)
    day = ("aaron judge", "hits", "2026-07-24")
    assert got[day] == 1.5
    assert got[day + (1,)] == 1.5 and got[day + (2,)] == 1.5
    odds = linemoves.closing_odds_by_date(rows)
    assert odds[day + (1.5,)]["over"] == -120, "game one's close by default"
    assert odds[day + (1.5, 2)]["over"] == -140, \
        "game two's pre-game price survives game one's first pitch"
    assert odds[day + (1.5, 1)]["over"] == -120


def test_a_single_game_day_carries_no_leg_keys():
    rows = [_snap("2026-07-24T22:30:00Z", "2026-07-24T23:05:00Z", 1.5)]
    got = linemoves.closing_lines_by_date(rows)
    assert set(got) == {("aaron judge", "hits", "2026-07-24")}
    assert got.stamped == {("aaron judge", "hits", "2026-07-24")}


def test_unstamped_history_is_not_reinterpreted():
    """Rows written before the start stamp existed keep the old day key and
    no cut — the page's past closes do not move under a code change."""
    ts = _dt.datetime(2026, 7, 24, 23, 30).timestamp()      # machine-local
    rows = [{"ts": ts, "player": "Aaron Judge", "market": "hits",
             "book": "dk", "line": 1.5, "over_odds": -110}]
    got = linemoves.closing_lines_by_date(rows)
    assert ("aaron judge", "hits", "2026-07-24") in got
    assert not got.stamped


def test_settle_asks_for_the_bets_own_leg():
    src = inspect.getsource(ledger.settle_from_history)
    assert "_leg_key(" in src


# --- college football --------------------------------------------------------
def test_college_records_line_snapshots_on_a_paid_pull():
    from engine.cfb import props as cfbprops
    sig = inspect.signature(cfbprops.attach_lines)
    assert "record" in sig.parameters
    src = inspect.getsource(cfbprops.attach_lines)
    assert "record_snapshots(" in src
    build = (ROOT / "cfb_build.py").read_text()
    assert "record=bool(args.odds)" in build


def test_college_snapshots_carry_the_kickoff():
    from engine.cfb import props as cfbprops
    from engine.data_loader import Slate
    from engine.models import Game, Prop, SportsbookLine, Weather
    tmp = Path(tempfile.mkdtemp()) / "lh.jsonl"
    saved = linemoves.HISTORY_PATH
    linemoves.HISTORY_PATH = tmp
    try:
        g = Game(home="UGA", away="BAMA", weather=Weather(),
                 kickoff="2026-09-26T23:30Z", date="2026-09-26")
        p = Prop(player="Carson Beck", team="UGA", opponent="BAMA",
                 position="QB", market="pass_yds", logs=[], career_avg=250.0,
                 vs_opponent_avg=None, lines=[])
        slate = Slate(date="2026-09-26", teams={}, games=[g], props=[p])
        line = SportsbookLine(book="dk", line=250.5, over_odds=-110,
                              under_odds=-110)
        from engine.sources.oddsapi import normalize_name
        cfbprops.attach_lines(slate, {(normalize_name("Carson Beck"), "pass_yds"): [line]},
                              record=True)
        import json
        rows = [json.loads(x) for x in tmp.read_text().splitlines()]
        assert rows and rows[0]["start_ts"] == _epoch("2026-09-26T23:30:00Z")
    finally:
        linemoves.HISTORY_PATH = saved


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items())
           if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
