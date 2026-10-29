"""The research's bet-linked and follow alerts, and each bet's closing line
value (engine/betclv, engine/slipwatch.moments, engine/pushmine,
engine/kickoffs closegame_pass/today_pass, engine/newsalerts).

Ethan's research (2026-10-29), the notification plan: "Your game starts
(T-10) ... Prop close to hitting (within 1 unit, or 85%+) ... Bet settled +
CLV ... Lineup/injury news ... Line moved vs. your bet (opt-in) ... Close
game (opt-in) ... Weekly CLV report", and "Live CLV ... you can make it
free". What these hold:

  * a leg's CLV is its entry decimal × the closing no-vig chance − 1 (the
    best closing price's own chance where there was no fair), kept from the
    sweep's own prices until the game starts and frozen after; a ticket's
    needs every leg's close;
  * the minute's moments: a game of the ticket within ten minutes of its
    start, a live over within a unit of its number or any leg 85% likely, a
    line 2% (implied) or a point from the price taken, a game late and
    within one score — each told once, the opt-in ones only to their switch;
  * the result says whether the price beat the close; Monday's week says the
    average and the best-priced bet;
  * a followed team's close finish, the morning slate from ten where the
    member is, and a player's status CHANGE (never the first sight) reach
    the phones that asked; the Alerts page has the four switches; the
    account's deletion takes the new tables and its export carries the
    closes.

Run directly: `python3 tests/test_bets_that_tell_you_when_it_matters.py`
"""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import betclv as BC                                   # noqa: E402
from engine import kickoffs as KO                                 # noqa: E402
from engine import newsalerts as NA                               # noqa: E402
from engine import pushalerts as PA                               # noqa: E402
from engine import pushmine as PM                                 # noqa: E402
from engine import slipwatch as SW                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
NOW = 1_793_304_000.0                                             # 2026-10-29 16:00 Eastern


def _iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn(uid=7, topics=("bets", "lines", "closegame", "news", "today"), teams=("nba:LAL",), tz=None):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, verifier TEXT, created_at REAL);
                       CREATE TABLE user_data (user_id INTEGER, section TEXT, ts INTEGER, payload TEXT,
                         PRIMARY KEY (user_id, section));""")
    c.execute("INSERT INTO users VALUES (?, 'm@example.com', 'x', 1)", (uid,))
    settings = {"teams": list(teams)}
    if tz:
        settings["tz"] = tz
    c.execute("INSERT INTO user_data VALUES (?, 'settings', 1, ?)", (uid, json.dumps(settings)))
    PM.ensure_tables(c)
    PA.subscribe(c, "ab" * 32, kind="apns", user_id=uid, topics=list(topics))
    return c


def _told(c, uid=7):
    return [dict(r) for r in c.execute("SELECT id, kind, title, body, url FROM push_mine WHERE user_id = ? ORDER BY at",
                                       (uid,))]


def test_a_legs_clv_is_its_price_against_the_close():
    assert abs(BC.leg_clv(110, 0.545) - (2.10 * 0.545 - 1)) < 1e-9
    assert abs(BC.leg_clv(-110, None, -130) - (1.9091 * (130 / 230) - 1)) < 1e-3, "the price's own chance, margin in"
    assert BC.leg_clv(None, 0.5) is None and BC.leg_clv(110, None, None) is None
    assert BC.words(0.042) == "beat the close by 4.2%" and BC.words(-0.031) == "3.1% worse than the close"
    c = sqlite3.connect(":memory:")
    leg = {"odds": 110, "price": {"best": -120, "fair": 0.52}, "live": {"state": "pre"}}
    assert BC.note(c, 1, "b1", {"legs": [leg, dict(leg, odds=-105)]}, NOW) == 2
    BC.note(c, 1, "b1", {"legs": [dict(leg, price={"best": -150, "fair": 0.58})]}, NOW + 60)
    BC.note(c, 1, "b1", {"legs": [dict(leg, price={"best": -300, "fair": 0.74}, live={"state": "live"})]}, NOW + 120)
    t = BC.ticket(c, 1, "b1", legs=2, payout=264)
    assert t["legs"][0]["close"] == -150 and abs(t["legs"][0]["clv"] - (2.10 * 0.58 - 1)) < 1e-9, \
        "the last price before the start, never one after"
    assert abs(t["clv"] - (3.64 * 0.58 * 0.52 - 1)) < 1e-9
    assert BC.ticket(c, 1, "b1", legs=3)["clv"] is None, "a ticket's number needs every leg's close"
    c.execute("UPDATE bet_clv SET at = ?", (NOW - (BC.KEEP_DAYS + 1) * 86400,))
    assert BC.prune(c, NOW) == 2


def _leg(**kw):
    base = {"league": "nba", "player": "LeBron James", "market": "points", "side": "over", "line": 24.5,
            "odds": 110, "live": {"state": "pre", "home": "LAL", "away": "BOS", "start": _iso(NOW + 8 * 60)}}
    base.update(kw)
    return base


def test_the_minute_finds_the_moments():
    got = SW.moments({"legs": [_leg()]}, NOW)
    assert got == [("bet_soon", ("nba:BOS@LAL", "BOS @ LAL", 8))], got
    assert not SW.moments({"legs": [_leg(live={"state": "pre", "start": _iso(NOW + 3600)})]}, NOW)
    way = SW.moments({"legs": [_leg(live={"state": "pre"}, price={"best": -130, "book": "FanDuel"})]}, NOW)
    assert way[0][0] == "bet_line" and way[0][1][4] > 0.02, way
    pts = SW.moments({"legs": [_leg(live={"state": "pre"}, price={"best": 105, "main_line": 26.5})]}, NOW)
    assert pts == [("bet_line_points", ("LeBron James", 24.5, 26.5))] or pts[0][0] == "bet_line_points", pts
    live = {"state": "live", "home": "LAL", "away": "BOS", "home_score": 101, "away_score": 99, "clock": "2:10 4th",
            "current": 24, "share_left": 0.05}
    close = SW.moments({"legs": [_leg(live=live)]}, NOW)
    assert [k for k, _ in close] == ["bet_close", "bet_close_game"], close
    far = dict(live, current=18, home_score=120, away_score=99, chance=0.2)
    assert not SW.moments({"legs": [_leg(live=far)]}, NOW)
    sure = dict(far, chance=0.9)
    assert [k for k, _ in SW.moments({"legs": [_leg(live=sure, side="under")]}, NOW)] == ["bet_close"]


def test_each_is_told_once_and_the_opt_ins_only_to_their_switch():
    c = _conn(topics=("bets",))
    assert PM.bet_soon(c, 7, "b1", "nba:BOS@LAL", "BOS @ LAL", 8, now=NOW)
    assert not PM.bet_soon(c, 7, "b1", "nba:BOS@LAL", "BOS @ LAL", 7, now=NOW + 60), "once a ticket and game"
    assert PM.bet_close(c, 7, "b1", "LeBron James o24.5 points", "has 24 so far", now=NOW)
    assert not PM.bet_close(c, 7, "b1", "LeBron James o24.5 points", "has 24 so far", now=NOW + 60)
    assert not PM.bet_line(c, 7, "b1", "LeBron", 110, -130, "FanDuel", 0.09, now=NOW), "lines is its own switch"
    assert not PM.bet_close_game(c, 7, "b1", "nba:BOS@LAL", "BOS 99 – 101 LAL", now=NOW)
    d = _conn()
    assert PM.bet_line(d, 7, "b1", "LeBron James o24.5", 110, -130, "FanDuel", 0.09, now=NOW)
    told = _told(d)[-1]
    assert told["title"] == "The line moved your way: LeBron James o24.5" and "you beat the market" in told["body"]
    assert PM.bet_close_game(d, 7, "b1", "nba:BOS@LAL", "BOS 99 – 101 LAL", now=NOW)
    for t in _told(c) + _told(d):
        assert "bet now" not in (t["title"] + t["body"]).lower()


def test_the_result_and_the_week_say_the_close():
    c = _conn()
    BC.note(c, 7, "b9", {"legs": [{"odds": 110, "price": {"best": -120, "fair": 0.53}, "live": {"state": "pre"}}]}, NOW)
    bet = {"id": "b9", "odds": 110, "stake": 10, "legs": [{"player": "x"}], "src": "slip", "date": "2026-10-27",
           "desc": "LeBron o24.5"}
    assert PM.bet_settled(c, 7, bet, {"result": "loss"}, now=NOW)
    assert "Your price beat the close by 11.3%." in _told(c)[-1]["body"], _told(c)[-1]
    line = PM.week_clv(c, 7, [bet, dict(bet, id="b10")], "2026-10-26", "2026-11-01")
    assert line == "Your prices beat the close by 11.3% on average (1 bet).", line


def _board(tmp, games, league="nba"):
    (Path(tmp) / f"live_{league}.json").write_text(json.dumps({"games": games}))
    return Path(tmp)


def test_a_followed_team_s_close_finish_and_the_morning_slate():
    c = _conn(teams=("nba:LAL",))
    tmp = tempfile.mkdtemp()
    late = {"event_id": "401", "away": "BOS", "home": "LAL",
            "live": {"state": "live", "period": 4, "clock": "2:10", "home_score": 101, "away_score": 99}}
    _board(tmp, [late])
    assert KO.closegame_pass(c, Path(tmp), now=NOW) == 1
    assert KO.closegame_pass(c, Path(tmp), now=NOW + 60) == 0, "once a game"
    assert _told(c)[-1]["url"] == "/#pbp/nba/401" and _told(c)[-1]["title"].startswith("Close game: BOS 99 – 101 LAL")
    blowout = dict(late, event_id="402", live=dict(late["live"], home_score=130))
    _board(tmp, [blowout])
    assert KO.closegame_pass(c, Path(tmp), now=NOW) == 0
    # The morning slate: from ten where the member is, once a day.
    from zoneinfo import ZoneInfo
    nine = dt.datetime(2026, 10, 29, 9, 30, tzinfo=ZoneInfo("America/New_York")).timestamp()
    ten = nine + 1800
    tonight = {"event_id": "403", "away": "BOS", "home": "LAL",
               "live": {"state": "pre", "start_time": _iso(ten + 10 * 3600)}}
    _board(tmp, [tonight])
    d = _conn(teams=("nba:LAL",))
    assert KO.today_pass(d, Path(tmp), now=nine) == 0
    assert KO.today_pass(d, Path(tmp), now=ten) == 1 and KO.today_pass(d, Path(tmp), now=ten + 900) == 0
    assert _told(d)[-1]["title"] == "Today: BOS @ LAL 8:00 PM ET", _told(d)[-1]
    west = _conn(teams=("nba:LAL",), tz="America/Los_Angeles")
    assert KO.today_pass(west, Path(tmp), now=ten) == 0, "seven in the morning in Los Angeles"
    none = _conn(teams=("nfl:KC",))
    assert KO.today_pass(none, Path(tmp), now=ten) == 0, "no game of theirs, no line"


def test_injury_news_is_a_change_never_a_first_sight():
    c = _conn()
    from engine import alerts as AL
    AL.ensure_tables(c)
    c.execute("INSERT INTO alert_watches (user_id, kind, value, created_at) VALUES (7, 'player', 'Ja Morant', 1)")
    c.execute("INSERT INTO user_data VALUES (7, 'mybets', 1, ?)", (json.dumps({"rows": [
        {"id": "s1", "src": "slip", "result": "pending", "legs": [{"player": "LeBron James", "market": "points"}]}]}),))
    tmp = Path(tempfile.mkdtemp())

    def board(morant, lebron):
        (tmp / "injuries.json").write_text(json.dumps({"sports": {"nba": [
            {"player": "Ja Morant", "team": "MEM", "status": morant, "injury": "Ankle"},
            {"player": "LeBron James", "team": "LAL", "status": lebron, "injury": "Foot"}]}}))
    board("QUESTIONABLE", "PROBABLE")
    assert NA.news_pass(c, tmp, now=NOW) == 0, "first sight is remembered, not told"
    board("OUT", "PROBABLE")
    assert NA.news_pass(c, tmp, now=NOW + 300) == 1
    t = _told(c)[-1]
    assert t["title"] == "Ja Morant (MEM): Questionable → Out" and t["body"] == "Ankle. News: you follow him.", t
    board("OUT", "QUESTIONABLE")
    assert NA.news_pass(c, tmp, now=NOW + 600) == 1 and _told(c)[-1]["body"] == "Foot. News: he is in your open bet."
    assert NA.news_pass(c, tmp, now=NOW + 900) == 0, "no change, nothing"


def test_wired_switched_deleted_and_exported():
    for t in ("lines", "closegame", "news", "today"):
        assert t in PA.PERSONAL and t in PM.TTL_S
    assert {"lines", "closegame", "news"} <= set(PM.HELD) and "bets" not in PM.HELD
    run = READ("engine", "pushmine.py")
    assert "_ko.closegame_pass(conn" in run and "_ko.today_pass(conn" in run and "_na.news_pass(conn" in run
    sweep = READ("engine", "slipwatch.py")
    assert "BC.note(conn, r[\"user_id\"], bid, card, t)" in sweep and "for kind, args in moments(card, t):" in sweep
    app = READ("web", "js", "app.js")
    for t in ("closegame", "news", "today", "lines"):
        assert f'box("{t}",' in app
    assert '"bet_clv", "news_seen"' in READ("engine", "accounts.py")
    assert "closing_prices_of_your_bets" in READ("engine", "accounts.py")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
