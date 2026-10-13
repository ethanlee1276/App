"""Every bet grades minutes after its game ends, not the next day.

Ethan, 2026-10-13: "bets are taking way too long too setttle, we should
be pulling after game data and checking if bets settled or not … It
should not take a day for all bets to settle."

What held a finished game's bets open, one rule each below:

  * seven NFL board markets had no same-night stat line (the box parser
    never wrote them), so they waited for the next morning's file;
  * the box pass opened only on six markets' props;
  * basketball's points + rebounds + assists was priced and journaled and
    never stored, so it never graded at all;
  * the NBA's "is it final" came off a six-hour cache and the NHL's off a
    thirty-minute one;
  * a fight's result came off a six-hour cache — and a stale "no winner"
    on a bout dated yesterday reads exactly like a draw, which voids;
  * fight picks graded only when the UFC board rebuilt; a desk ticket on
    tonight's game was first asked about tomorrow;
  * the settle ran once per board sweep, however long the sweep took.

Run directly: `python3 tests/test_bets_settle_minutes_after_the_final.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import boxsettle as B, db, ledger                       # noqa: E402

TODAY = dt.date.today()
YESTERDAY = (TODAY - dt.timedelta(days=1)).isoformat()
OLD = (TODAY - dt.timedelta(days=10)).isoformat()


def _world():
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    return L, H


def _bet(L, sport, date, player, market, line, side="OVER", game_day="", category="main"):
    L.execute(
        "INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, "
        "odds, stake_units, stake_dollars, status, category) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, -110, 1, 10, 'open', ?)",
        (f"{YESTERDAY}T12:00:00", sport, date, game_day, player, market, side, line, category))
    L.commit()


def _status(L, player, market):
    r = L.execute("SELECT status, actual FROM bets WHERE player=? AND market=?",
                  (player, market)).fetchone()
    return r["status"], r["actual"]


def _ath(name, pos, stats):
    return {"athlete": {"displayName": name, "position": {"abbreviation": pos}}, "stats": stats}


def _nfl_box():
    """One finished game: a quarterback who never ran, a back, a receiver,
    a tight end, both kickers (one feed without a PTS column) and a
    linebacker."""
    return {"boxscore": {"players": [
        {"team": {"abbreviation": "DET"}, "statistics": [
            {"name": "passing", "labels": ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS", "QBR", "RTG"],
             "athletes": [_ath("Jared Goff", "QB", ["24/33", "281", "8.5", "2", "1", "2-14", "70.1", "101.2"])]},
            {"name": "rushing", "labels": ["CAR", "YDS", "AVG", "TD", "LONG"],
             "athletes": [_ath("Jahmyr Gibbs", "RB", ["19", "94", "4.9", "1", "22"])]},
            {"name": "receiving", "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
             "athletes": [_ath("Jahmyr Gibbs", "RB", ["3", "21", "7.0", "0", "12", "4"]),
                          _ath("Amon-Ra St. Brown", "WR", ["7", "81", "11.6", "1", "24", "9"]),
                          _ath("Sam LaPorta", "TE", ["4", "38", "9.5", "0", "15", "6"])]},
            {"name": "kicking", "labels": ["FG", "PCT", "LONG", "XP", "PTS"],
             "athletes": [_ath("Jake Bates", "K", ["2/3", "66.7", "51", "3/3", "9"])]},
            {"name": "defensive", "labels": ["TOT", "SOLO", "SACKS", "TFL", "PD", "QB HTS", "TD"],
             "athletes": [_ath("Jack Campbell", "LB", ["11", "7", "1", "2", "0", "1", "0"])]}]},
        {"team": {"abbreviation": "KC"}, "statistics": [
            {"name": "kicking", "labels": ["FG", "PCT", "LONG", "XP"],
             "athletes": [_ath("Harrison Butker", "K", ["1/1", "100.0", "40", "2/2"])]},
            {"name": "defensive", "labels": [], "athletes": [_ath("No Labels", "LB", ["4"])]}]}]}}


GAME = {"season": 2026, "period": "006", "game_id": "KC@DET", "home": "DET", "away": "KC"}


def _rows_by_player(rows):
    out: dict = {}
    for r in rows:
        out.setdefault(r["player"], {})[r["market"]] = r["value"]
    return out


# --- football: every board market the night of the game ----------------------
def test_every_nfl_board_market_gets_a_same_night_line():
    from engine.sources.nflverse import POSITION_MARKETS
    wanted = {m for lst in POSITION_MARKETS.values() for m, _ in lst} | {"anytime_td"}
    rows = B.nfl_rows(_nfl_box(), GAME)
    have = {r["market"] for r in rows}
    assert wanted <= have, f"no same-night line for {sorted(wanted - have)}"
    assert {r["game_id"] for r in rows} == {"DET-006-box", "KC-006-box"}
    keys = [(r["player"], r["market"]) for r in rows]
    assert len(keys) == len(set(keys)), "a player got two rows for one market"


def test_the_sums_and_the_special_blocks_read_right():
    got = _rows_by_player(B.nfl_rows(_nfl_box(), GAME))
    gibbs = got["Jahmyr Gibbs"]
    assert gibbs["rush_att"] == 19 and gibbs["rush_rec_yds"] == 115
    assert gibbs["pass_rush_yds"] == 115, "a back who threw nothing: passing is zero"
    assert got["Jared Goff"]["pass_rush_yds"] == 281, "a passer who never ran: rushing is zero"
    assert got["Jared Goff"]["anytime_td"] == 0, "he played and did not score"
    assert got["Amon-Ra St. Brown"]["anytime_td"] == 1
    assert got["Jake Bates"] == {"fg_made": 2.0, "kick_pts": 9.0}
    assert got["Harrison Butker"] == {"fg_made": 1.0, "kick_pts": 5.0}, "3 a field goal, 1 a point after"
    assert got["Jack Campbell"] == {"tackles_ast": 11.0}
    assert "No Labels" not in got, "a block without labels gives nothing, never a guess"


def test_a_week_whose_only_open_props_are_new_markets_fetches_the_box_and_grades():
    L, H = _world()
    _bet(L, "nfl", "2026-W06", "Jake Bates", "kick_pts", 7.5, game_day=YESTERDAY)
    _bet(L, "nfl", "2026-W06", "Jack Campbell", "tackles_ast", 8.5, game_day=YESTERDAY)
    _bet(L, "nfl", "2026-W06", "Jared Goff", "anytime_td", 0.5, game_day=YESTERDAY)
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
              "away_score) VALUES ('nfl', 2026, '006', 'KC@DET', ?, 'DET', 'KC', 27, 20)", (YESTERDAY,))
    H.commit()
    asked = []
    res = B.ingest_for_open(L, H, "nfl", log=lambda *a: None,
                            fetch_rows=lambda lg: [{"away": "KC", "home": "DET", "event_id": "401900"}],
                            fetch_summary=lambda lg, eid: asked.append(eid) or _nfl_box())
    assert asked == ["401900"] and res["games"] == 1, (asked, res)
    assert ledger.settle_from_history(L, H) == 3
    assert _status(L, "Jake Bates", "kick_pts") == ("won", 9.0)
    assert _status(L, "Jack Campbell", "tackles_ast") == ("won", 11.0)
    assert _status(L, "Jared Goff", "anytime_td") == ("lost", 0.0)


def test_any_prop_opens_the_pass_and_no_game_bet_or_desk_ticket_does():
    L, H = _world()
    _bet(L, "nfl", "2026-W06", "Jared Goff", "pass_att", 33.5, game_day=YESTERDAY)
    assert B._open_periods(L, "nfl") == {(2026, "006"): 1}
    L.execute("DELETE FROM bets")
    _bet(L, "nfl", "2026-W06", "DET", "spread", -3.5, game_day=YESTERDAY)
    _bet(L, "nfl", "2026-W06", "KXNFLGAME-26OCT12DET-YES", "rec_yds", 41.0,
         game_day=YESTERDAY, category="predmarket")
    assert B._open_periods(L, "nfl") == {}
    src = Path(ROOT, "engine", "boxsettle.py").read_text(encoding="utf-8")
    assert "PROP_MARKETS" not in src, "a fixed list of six markets is how the new ones were left out"


# --- basketball: points + rebounds + assists ---------------------------------
def _hoops_day(H, sport, date, player, parts, minutes=34.0):
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
              "away_score) VALUES (?, 2026, ?, 'NYK@BOS', ?, 'BOS', 'NYK', 112, 104)",
              (sport, date, date))
    rows = [{"sport": sport, "season": 2026, "period": date, "game_id": f"{player}-{date}",
             "player": player, "team": "BOS", "opponent": "NYK", "position": "S", "home": 1,
             "market": m, "value": v} for m, v in dict(parts, min=minutes).items()]
    db.upsert_player_logs(H, rows)
    H.commit()


def test_points_rebounds_assists_grade_off_their_parts():
    for sport in ("nba", "wnba"):
        L, H = _world()
        _bet(L, sport, OLD, "Jay Star", "pra", 39.5)
        _hoops_day(H, sport, OLD, "Jay Star", {"pts": 30.0, "reb": 6.0, "ast": 5.0})
        assert ledger.settle_from_history(L, H) == 1, sport
        assert _status(L, "Jay Star", "pra") == ("won", 41.0), sport


def test_a_missing_part_never_grades_a_short_sum():
    L, H = _world()
    _bet(L, "nba", OLD, "Jay Star", "pra", 29.5)
    _hoops_day(H, "nba", OLD, "Jay Star", {"pts": 30.0, "reb": 6.0})       # no assists row
    ledger.settle_from_history(L, H)
    assert _status(L, "Jay Star", "pra")[0] == "open"


def test_a_scratch_still_voids_on_a_summed_market():
    L, H = _world()
    _bet(L, "nba", OLD, "Bench Guy", "pra", 9.5)
    _hoops_day(H, "nba", OLD, "Bench Guy", {"pts": 0.0, "reb": 0.0, "ast": 0.0}, minutes=0.0)
    ledger.settle_from_history(L, H)
    assert _status(L, "Bench Guy", "pra")[0] == "void"


# --- the NBA's and the NHL's "is it final" ------------------------------------
def _iso(hours_ago):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nba_sched(status, date, tip):
    return {"leagueSchedule": {"gameDates": [{"games": [
        {"gameId": "0022600001", "gameDateEst": f"{date}T00:00:00Z", "gameStatus": status,
         "gameDateTimeUTC": tip,
         "homeTeam": {"teamTricode": "BOS", "score": 112 if status == 3 else 80},
         "awayTeam": {"teamTricode": "NYK", "score": 104 if status == 3 else 77}}]}]}}


def _nba_box(status):
    return {"game": {"gameStatus": status,
                     "homeTeam": {"teamTricode": "BOS", "players": [
                         {"name": "Jay Star", "starter": "1", "personId": 1,
                          "statistics": {"minutes": "PT36M00.00S", "points": 30,
                                         "reboundsTotal": 6, "assists": 5}}]},
                     "awayTeam": {"teamTricode": "NYK", "players": []}}}


def test_a_tipped_nba_game_is_asked_about_fresh_not_off_a_six_hour_copy():
    from engine.sources import nbadata as N
    date, tip = TODAY.isoformat(), _iso(3)
    calls = []

    def sched(ttl=21600):
        calls.append(ttl)
        return _nba_sched(3 if ttl == N.RECENT_TTL else 2, date, tip)
    saved = N.fetch_schedule
    N.fetch_schedule = sched
    try:
        games = N.day_games(date)
    finally:
        N.fetch_schedule = saved
    assert calls == [21600, N.RECENT_TTL], calls
    assert games[0]["status"] == 3 and games[0]["home_score"] == 112
    # Nothing tipped, or already final: the cached copy stands.
    assert not N.owed_finals([{"status": 1, "kickoff": _iso(-2)}]), "not tipped yet"
    assert not N.owed_finals([{"status": 3, "kickoff": _iso(3)}])
    assert not N.owed_finals([{"status": 2, "kickoff": _iso(40)}]), "a day-old copy is the daily pass's"
    assert not N.owed_finals([{"status": 2, "kickoff": _iso(3), "preseason": True}])


def test_an_nba_box_cached_before_the_buzzer_is_read_again_and_never_stored_live():
    from engine.sources import nbadata as N
    date, tip = YESTERDAY, _iso(20)
    boxes = {"default": _nba_box(2), "fresh": _nba_box(2)}

    def box(gid, ttl=21600):
        return boxes["fresh" if ttl == 0 else "default"]
    saved = (N.fetch_schedule, N.fetch_boxscore)
    N.fetch_schedule = lambda ttl=21600: _nba_sched(3, date, tip)
    N.fetch_boxscore = box
    H = db.connect(":memory:")
    try:
        res = N.ingest_nba_date(H, date)
        assert res["player_logs"] == 0 and any("not final yet" in s for s in res["skipped"]), res
        boxes["fresh"] = _nba_box(3)
        res = N.ingest_nba_date(H, date)
        assert res["player_logs"] > 0, res
    finally:
        N.fetch_schedule, N.fetch_boxscore = saved


def test_an_nhl_day_read_in_the_third_period_is_read_again_after_the_horn():
    from engine.sources import nhldata as N
    date = TODAY.isoformat()
    calls = []

    def fake_json(url, name, ttl=0, **kw):
        calls.append(ttl)
        state = "OFF" if ttl == N.RECENT_TTL else "LIVE"
        return {"games": [{"id": 2026020001, "gameType": 2, "gameState": state,
                           "startTimeUTC": _iso(3),
                           "homeTeam": {"abbrev": "TOR", "score": 4, "name": {"default": "Leafs"}},
                           "awayTeam": {"abbrev": "MTL", "score": 2, "name": {"default": "Canadiens"}}}]}
    saved = N.fetch_json
    N.fetch_json = fake_json
    H = db.connect(":memory:")
    try:
        N.ingest_day(H, date, scores_only=True)
    finally:
        N.fetch_json = saved
    assert calls == [1800, N.RECENT_TTL], calls
    r = H.execute("SELECT home_score, away_score FROM games WHERE sport='nhl'").fetchone()
    assert (r["home_score"], r["away_score"]) == (4.0, 2.0)


# --- fights and desk tickets --------------------------------------------------
def test_a_fight_from_last_night_is_read_fresh_before_no_winner_means_a_draw():
    from engine.sources import espnmma as M
    when = (TODAY - dt.timedelta(days=1)).isoformat()
    calls = []

    def fake(url, name, ttl=0, **kw):
        calls.append((name, ttl))
        if "eventlog" in url:
            return {"events": {"items": [{"competition": {"$ref": "http://x/competitions/777"}}]}}
        winner = ttl == M.RESULT_TTL
        return {"id": "777", "date": f"{when}T03:00Z", "competitors": [
            {"id": "1", "winner": winner}, {"id": "2", "winner": False}]}
    saved = (M._get_json, M.find_athlete_id)
    M._get_json, M.find_athlete_id = fake, (lambda name: "1")
    try:
        got = M.latest_result("Fighter One", TODAY - dt.timedelta(days=2))
    finally:
        M._get_json, M.find_athlete_id = saved
    assert got == {"won": True, "date": when}, got
    assert ("espn_mma_res_777.json", M.RESULT_TTL) in calls


def test_fights_and_tonights_desk_tickets_are_on_the_settle_clock():
    src = Path(ROOT, "engine", "maintenance.py").read_text(encoding="utf-8")
    body = src[src.index("def settle_open("):]
    body = body[:body.index("\ndef ", 1)]
    assert "ledger.settle_ufc(lconn)" in body
    assert body.index("settle_from_history(lconn, hconn)") < body.index("ledger.settle_ufc(lconn)")
    led = Path(ROOT, "engine", "ledger.py").read_text(encoding="utf-8")
    fn = led[led.index("def settle_predmarket("):]
    assert "when > today_d.isoformat()" in fn[:fn.index("\ndef ")]


# --- the settle's own clock ---------------------------------------------------
def test_the_live_boards_name_their_finals():
    import launch
    root = Path(tempfile.mkdtemp())
    d = root / "web" / "data"
    d.mkdir(parents=True)
    (d / "live_nfl.json").write_text(json.dumps({"games": [
        {"event_id": "401", "live": {"state": "final"}},
        {"event_id": "402", "live": {"state": "live"}}]}))
    (d / "live_mlb.json").write_text(json.dumps({"games": [
        {"game_pk": 7788, "live": {"state": "final"}}]}))
    (d / "live_nhl.json").write_text("not json")
    assert launch._finals_on_live_boards(root) == {("nfl", "401"), ("mlb", "7788")}


def test_a_final_starts_a_pass_at_once_and_the_lane_keeps_its_own_clock():
    import launch
    from engine.maintenance import SETTLE_EVERY_S
    kicks, answer = [], ["started"]
    saved = (launch._kick_lane, dict(launch._SETTLE_CLOCK))
    launch._kick_lane = lambda lane, force_settle=False: kicks.append((lane, force_settle)) or answer[0]
    launch._SETTLE_CLOCK.update(seen=None, owed=False, last_forced=0.0, last_kick=0.0)
    try:
        t = 1_000_000.0
        real = launch._settle_clock_tick
        launch._settle_clock_tick = lambda now=None, finals=None, last_pass=0.0: real(now, finals, last_pass)
        assert launch._settle_clock_tick(now=t, finals={("nfl", "1")}) == "", "boot: seen, not kicked"
        assert kicks == []
        assert launch._settle_clock_tick(now=t + 30, finals={("nfl", "1"), ("nfl", "2")}) == "final"
        assert kicks == [("settle", True)]
        # A second final inside the gap waits, and is owed.
        assert launch._settle_clock_tick(now=t + 60, finals={("nfl", "1"), ("nfl", "2"), ("nhl", "9")}) == ""
        assert len(kicks) == 1 and launch._SETTLE_CLOCK["owed"]
        later = t + 30 + launch.FINAL_KICK_GAP_S
        answer[0] = "still running"
        assert launch._settle_clock_tick(now=later, finals=set()) == ""
        assert launch._SETTLE_CLOCK["owed"], "a pass still running keeps the final owed"
        answer[0] = "started"
        assert launch._settle_clock_tick(now=later + 30, finals=set()) == "owed"
        assert kicks[-1] == ("settle", True)
        # No final: the lane's own clock, whatever the boards are doing.
        n = len(kicks)
        assert launch._settle_clock_tick(now=later + 60, finals=set()) == ""
        assert len(kicks) == n
        assert launch._settle_clock_tick(now=later + 30 + SETTLE_EVERY_S, finals=set()) == "due"
        assert kicks[-1] == ("settle", False)
        # A pass the board loop started is the lane's own clock too.
        n = len(kicks)
        assert real(later + 40 + 2 * SETTLE_EVERY_S, set(), later + 30 + 2 * SETTLE_EVERY_S) == ""
        assert len(kicks) == n, "a kick inside the last pass's five minutes would be turned away"
    finally:
        launch._settle_clock_tick = real
        launch._kick_lane = saved[0]
        launch._SETTLE_CLOCK.clear()
        launch._SETTLE_CLOCK.update(saved[1])


def test_the_clock_is_started_beside_the_live_boards():
    src = Path(ROOT, "launch.py").read_text(encoding="utf-8")
    assert 'threading.Thread(target=_settle_clock, daemon=True, name="settle-clock").start()' in src
    kc = src[src.index("def _kick_chores("):]
    assert "_kick_lane(lane, force_settle)" in kc[:kc.index("\n\n\n")], "one door to a lane"
    kl = src[src.index("def _kick_lane("):]
    assert "with _LANE_LOCK:" in kl[:kl.index("\n\n\n")], "two callers, one look-and-start"



# --- the box check -------------------------------------------------------------
def test_the_box_check_names_what_each_owed_bet_waits_on():
    import time as _time
    import settlecheck as S
    t = Path(tempfile.mkdtemp())
    L = ledger.connect(t / "l.db")
    ledger.configure_bankroll(L, starting=1000, unit_pct=1)
    H = db.connect(t / "h.db")
    ahead = (TODAY + dt.timedelta(days=2)).isoformat()
    _bet(L, "nfl", "2026-W06", "Amon-Ra St. Brown", "rec_yds", 60.5, game_day=YESTERDAY)
    _bet(L, "nba", OLD, "Jay Star", "pts", 25.5)
    _bet(L, "mlb", YESTERDAY, "Aaron Judge", "hits", 0.5)
    _bet(L, "nhl", ahead, "Auston Matthews", "goals", 0.5)
    _bet(L, "mlb", YESTERDAY, "KXMLBGAME-X-YES", "kalshi_ml", 41.0, category="predmarket")
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
              "VALUES ('nfl', 2026, '006', 'KC@DET', ?, 'DET', 'KC', 27, 20)", (YESTERDAY,))
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
              "VALUES ('nba', 2026, ?, 'NYK@BOS', ?, 'BOS', 'NYK', 112, 104)", (OLD, OLD))
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score) "
              "VALUES ('mlb', 2026, ?, 'NYY@BOS', ?, 'BOS', 'NYY', NULL, NULL)", (YESTERDAY, YESTERDAY))
    db.upsert_player_logs(H, [{"sport": "nfl", "season": 2026, "period": "006",
                               "game_id": "DET-006-box", "player": "Amon-Ra St. Brown", "team": "DET",
                               "opponent": "KC", "position": "WR", "home": 1,
                               "market": "rec_yds", "value": 81.0}])
    H.commit()
    counts = (L.execute("SELECT COUNT(*) FROM bets").fetchone()[0],
              H.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0])
    lines = S.report(t / "l.db", t / "h.db", today=TODAY)
    text = "\n".join(lines)
    nfl = next(x for x in lines if x.startswith("NFL"))
    assert "open 1" in nfl and "OWED 1" in nfl and "NOT FINAL 0" in nfl, nfl
    assert "Amon-Ra St. Brown rec_yds [main] — stat line on file (box score)" in text, text
    assert "Jay Star pts [main] — no stat line for him yet" in text, text
    mlb = next(x for x in lines if x.startswith("MLB"))
    assert "OWED 0" in mlb and "NOT FINAL 1" in mlb, mlb
    nhl = next(x for x in lines if x.startswith("NHL"))
    assert "ahead 1" in nhl and "OWED 0" in nhl, nhl
    assert "DESK  open 1" in text and "UFC   open 0" in text
    assert counts == (L.execute("SELECT COUNT(*) FROM bets").fetchone()[0],
                      H.execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0]), "it wrote"
    state, lane = t / "m.json", t / "lane.json"
    now = _time.time()
    state.write_text(json.dumps({"last_settle_ts": now - 120, "last_desk_ts": now - 600}))
    lane.write_text(json.dumps({"step": "autosettle", "since": now - 61}))
    got = S.settle_line(state, lane, now=now)
    assert "last pass 2 min ago" in got and "desk asked 10 min ago" in got
    assert "settle lane: autosettle for 1 min" in got, got
    assert "settle lane: idle" in S.settle_line(t / "none.json", t / "none.json", now=now)

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
