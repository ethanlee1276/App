"""The smart paywall, the richer morning brief and the season bridge
(engine/smartwall + GET /api/billing/caught + js/account.js pwCaught;
engine/kickoffs.brief_extras; engine/lifecycle.season_bridge).

Ethan's second research paper (2026-10-29): "Smart paywall — shows a free
user what paid alerts caught on their teams last week", "Morning brief —
each user's games, model edges, injuries and line moves, every morning" and
"Season bridge — when a user's sport ends, suggests players to follow in the
next one". What these hold:

  * the paywall counts last week's staked picks on a free account's own
    teams from the journal the Record reads, how the graded ones went and how
    many are still open, never naming one; nothing under two picks, nothing
    for a member or a stranger;
  * the brief adds who on their teams is out, doubtful or questionable, a
    spread that moved a point or more since it opened, and a count of the
    picks on those games;
  * the bridge tells a member whose teams' leagues have all just finished,
    once, which leagues are on — and nobody whose league still plays; a
    break inside a season (the All-Star weeks, the Super Bowl's bye) is not
    an end;
  * a league back after its break tells its fans who have been away a
    week, once a season, when their team plays first.

Run directly: `python3 tests/test_the_paywall_brief_and_bridge.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger as L                                    # noqa: E402
from engine import smartwall as SW                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731
ET = ZoneInfo("America/New_York")
NOW = dt.datetime(2026, 10, 29, 14, 0, tzinfo=ET).timestamp()
DAY = 86400.0


def _pick(c, sport, team, date, status, category="main", stake=1.0, player="X"):
    c.execute("INSERT INTO bets (sport, date, player, market, side, status, category, stake_units, team) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (sport, date, f"{player}{team}{date}{status}{stake}", "pts", "OVER", status,
                                             category, stake, team))


def test_the_paywall_counts_last_week_on_their_teams_and_names_none():
    d = tempfile.mkdtemp()
    c = L.connect(Path(d) / "l.db")
    _pick(c, "nfl", "KC", "2026-10-26", "won")
    _pick(c, "nfl", "KC", "2026-10-26", "lost")
    _pick(c, "nfl", "KC", "2026-10-27", "won")
    _pick(c, "nfl", "KC", "2026-10-29", "open")
    _pick(c, "nba", "LAL", "2026-10-28", "push")
    _pick(c, "nfl", "KC", "2026-10-10", "won")                      # two weeks ago
    _pick(c, "nfl", "DAL", "2026-10-27", "won")                     # not their team
    _pick(c, "nfl", "KC", "2026-10-27", "won", stake=0.0)           # never staked
    _pick(c, "nfl", "KC", "2026-10-27", "won", category="shadow")   # not a published book
    c.commit()
    teams = SW._teams({"teams": ["nfl:KC", "nba:LAL", "nhl:", "junk"]})
    assert teams == [("nfl", "KC"), ("nba", "LAL")]
    got = SW.caught(c, teams, NOW)
    assert got == {"n": 5, "w": 2, "l": 1, "p": 1, "open": 1, "teams": ["KC", "LAL"]}, got
    assert SW.caught(c, [("nhl", "BOS")], NOW) is None and SW.caught(c, [], NOW) is None
    srv = READ("server.py")
    at = srv.index('if path == "caught":')
    body = srv[at:at + 1600]
    assert 'return self._send(401, b\'{"error":"sign in first"}\', ".json")' in body
    assert "if self._entitled(conn, who):" in body
    acct = READ("web", "js", "account.js")
    fn = acct[acct.index("async function pwCaught(host)"):acct.index("/* Tonight's picks on the plans")]
    assert "_pwStatus.signed_in && !_pwStatus.entitled" in fn and "settings().teams.length" in fn
    assert "losses and all" in fn and "Members saw each one when it posted" in fn
    assert "pwCaught(host);" in acct and '<div class="pw-caught" hidden></div>' in acct


def test_the_brief_says_injuries_the_line_and_how_many_picks():
    from engine import gate
    from engine import kickoffs as KO
    d = Path(tempfile.mkdtemp())
    games = [{"home": "KC", "away": "DEN", "date": "2026-10-29", "kickoff": "2026-10-30T00:20:00Z",
              "line_open": {"spread_home": -3.0, "spread_move": -1.5}},
             {"home": "DAL", "away": "NYG", "date": "2026-10-29", "kickoff": "2026-10-30T00:20:00Z",
              "line_open": {"spread_home": -6.0, "spread_move": -0.5}}]
    (d / "recommendations.json").write_text(json.dumps({"games": games}))
    (d / "injuries.json").write_text(json.dumps({"sports": {"nfl": [
        {"player": "Travis Kelce", "team": "KC", "status": "Questionable", "injury": "ankle"},
        {"player": "Rashee Rice", "team": "KC", "status": "Out", "injury": "knee"},
        {"player": "Somebody Else", "team": "DAL", "status": "Out", "injury": "hip"},
        {"player": "Healthy Guy", "team": "KC", "status": "Active", "injury": ""}]}}))
    keep = gate.board_source
    full = d / "full.json"
    full.write_text(json.dumps({"games": games, "recommendations": [
        {"team": "KC", "opponent": "DEN", "player": "A"}, {"team": "DEN", "opponent": "KC", "player": "B"},
        {"team": "DAL", "opponent": "NYG", "player": "C"}]}))
    gate.board_source = lambda p: full if Path(p).name == "recommendations.json" else p
    try:
        lines = KO.brief_extras([("nfl", "1", "DEN", "KC", NOW)], {("nfl", "KC")}, d)
    finally:
        gate.board_source = keep
    assert lines[0] == "Out: Rashee Rice (KC). Questionable: Travis Kelce (KC).", lines
    assert "KC opened −3, now −4.5." in lines, lines
    assert lines[-1] == "2 picks on this game — members see them.", lines
    assert not any("Somebody Else" in x or "DAL" in x for x in lines), "only their teams and their games"
    src = READ("engine", "kickoffs.py")
    assert 'body or "Your teams’ games — the slate, the chats and Call it."' in src
    assert "len(body) + 1 + len(x) <= BRIEF_CHARS" in src, "whole sentences, never one cut off on a lock screen"


def test_the_server_answers_a_free_reader_and_nobody_else():
    import server
    from engine import accounts as A
    tmp = Path(tempfile.mkdtemp())
    conn = A.connect(tmp / "a.db")
    uid = int(conn.execute("INSERT INTO users (email, verifier, created_at) VALUES ('free@example.com', 'x', ?)",
                           (NOW,)).lastrowid)
    A.save_sections(conn, uid, {"settings": {"ts": 1, "data": {"teams": ["nfl:KC"]}}})
    conn.commit()
    conn.close()
    lc = L.connect(tmp / "l.db")
    today = dt.date.today().isoformat()
    _pick(lc, "nfl", "KC", today, "won")
    _pick(lc, "nfl", "KC", today, "lost")
    lc.commit()
    lc.close()
    saved = (A.DB_PATH, L.DEFAULT_DB)
    A.DB_PATH, L.DEFAULT_DB = tmp / "a.db", tmp / "l.db"
    try:
        h = object.__new__(server.Handler)
        sent = []
        h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
        h._entitled = lambda conn, who: False
        h._account = lambda conn: None
        h._billing_get("caught")
        assert sent[-1][0] == 401, sent[-1]
        h._account = lambda conn: {"id": uid, "email": "free@example.com"}
        h._billing_get("caught")
        assert sent[-1] == (200, {"caught": {"n": 2, "w": 1, "l": 1, "p": 0, "open": 0, "teams": ["KC"]}}), sent[-1]
        h._entitled = lambda conn, who: True
        h._billing_get("caught")
        assert sent[-1] == (200, {"caught": None}), "a member is sold nothing"
    finally:
        A.DB_PATH, L.DEFAULT_DB = saved


def _boards(d, lg_games):
    from engine import socialfeed as SF
    for lg, games in lg_games.items():
        (d / SF.SPORT_FILE[lg]).write_text(json.dumps({"games": games}))


def _iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _accounts(tmp):
    from engine import accounts as A
    from engine import lifecycle as LC
    from engine import pushalerts as PA
    from engine import pushmine as PM
    conn = A.connect(Path(tmp) / "a.db")
    LC.ensure_tables(conn)
    PA.ensure_tables(conn)
    PM.ensure_tables(conn)
    web = Path(tmp) / "web"
    (web / "data").mkdir(parents=True)
    return conn, web


def _fan(conn, i, teams, seen_days_ago=0.0, now=NOW):
    from engine import accounts as A
    from engine import pushalerts as PA
    cur = conn.execute("INSERT INTO users (email, verifier, created_at, last_seen) VALUES (?, 'x', ?, ?)",
                       (f"f{i}@example.com", now - 200 * DAY, now - seen_days_ago * DAY))
    uid = int(cur.lastrowid)
    A.save_sections(conn, uid, {"settings": {"ts": 1, "data": {"teams": teams}}})
    PA.subscribe(conn, f"{i:02d}" * 16, kind="apns", user_id=uid, topics=["away"])
    return uid


def test_the_bridge_tells_a_finished_league_s_fans_once_which_are_on():
    from engine import lifecycle as LC
    with tempfile.TemporaryDirectory() as tmp:
        conn, web = _accounts(tmp)
        at = lambda days: _iso(NOW + days * DAY)                            # noqa: E731
        _boards(web / "data", {
            "mlb": [{"home": "LAD", "away": "NYY", "kickoff": at(-12)}],    # the World Series, over
            "nba": [{"home": "LAL", "away": "BOS", "kickoff": at(1)}, {"home": "BOS", "away": "LAL", "kickoff": at(5)}],
            "nhl": [{"home": "NYR", "away": "BOS", "kickoff": at(2)}, {"home": "BOS", "away": "NYR", "kickoff": at(6)}],
            "nfl": [{"home": "KC", "away": "DEN", "kickoff": at(3)}, {"home": "DEN", "away": "KC", "kickoff": at(9)}]})
        on, done, back = LC.seasons(web / "data", NOW)
        assert done == {"mlb"} and {"nba", "nhl", "nfl"} <= on and not back, (on, done, back)
        uids = [_fan(conn, i, teams) for i, teams in enumerate((["mlb:NYY"], ["mlb:NYY", "nfl:KC"], ["nba:LAL"]))]
        assert LC.season_bridge(conn, now=NOW, web=web) == 1
        (title, body), = conn.execute("SELECT title, body FROM push_mine WHERE user_id = ?", (uids[0],)).fetchall()
        assert title == "MLB is done for the season", title
        assert body.startswith("NFL, NBA and NHL are on: follow a team there"), body
        assert not conn.execute("SELECT 1 FROM push_mine WHERE user_id IN (?, ?)", (uids[1], uids[2])).fetchone(), \
            "a fan whose other league still plays, or whose league is on, hears nothing"
        assert LC.season_bridge(conn, now=NOW + 3 * DAY, web=web) == 0, "the away alert's one a week"
        conn.execute("DELETE FROM engagement_away")
        assert LC.season_bridge(conn, now=NOW + 3 * DAY, web=web) == 0, "and the bridge itself once"
        # THE BOARD EMPTIED after the final: the marks still know when it was.
        _boards(web / "data", {"mlb": []})
        assert "mlb" in LC.seasons(web / "data", NOW + 4 * DAY, conn)[1]
        assert "mlb" not in LC.seasons(web / "data", NOW + 20 * DAY, conn)[1], "a month on, no news"


def test_a_break_is_not_the_end_of_a_season():
    from engine import lifecycle as LC
    feb = dt.datetime(2027, 2, 16, 14, 0, tzinfo=ET).timestamp()        # the NBA's All-Star break
    may = dt.datetime(2027, 5, 26, 14, 0, tzinfo=ET).timestamp()        # between two playoff rounds
    bye = dt.datetime(2027, 2, 2, 14, 0, tzinfo=ET).timestamp()         # the Super Bowl's bye week
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _boards(d, {"nba": [{"home": "LAL", "away": "BOS", "kickoff": _iso(feb - 12 * DAY)}]})
        assert "nba" not in LC.seasons(d, feb)[1], "the Olympics and the All-Star weeks are not in May to July"
        _boards(d, {"nba": [{"home": "LAL", "away": "BOS", "kickoff": _iso(may - 3 * DAY)}]})
        assert "nba" not in LC.seasons(d, may)[1], "three quiet days is a gap between rounds"
        _boards(d, {"nfl": [{"home": "KC", "away": "DEN", "kickoff": _iso(bye - 9 * DAY)},
                            {"home": "KC", "away": "SF", "kickoff": _iso(bye + 5 * DAY)}]})
        on, done, _back = LC.seasons(d, bye)
        assert "nfl" in on and "nfl" not in done, (on, done)


def test_a_league_back_tells_its_away_fans_once_when_their_team_plays():
    from engine import lifecycle as LC
    with tempfile.TemporaryDirectory() as tmp:
        conn, web = _accounts(tmp)
        tip = NOW + 2 * DAY
        _boards(web / "data", {"nba": [{"home": "LAL", "away": "BOS", "kickoff": _iso(tip)},
                                       {"home": "BOS", "away": "NYK", "kickoff": _iso(NOW + 9 * DAY)}],
                               "nfl": [{"home": "KC", "away": "DEN", "kickoff": _iso(NOW + 3 * DAY)}]})
        LC.seasons(web / "data", NOW, conn)
        assert not LC.seasons(web / "data", NOW, conn)[2], "first sight, in season: already playing, not back"
        conn.execute("UPDATE season_marks SET last_on = ? WHERE league = 'nba'", (NOW - 40 * DAY,))
        away = _fan(conn, 1, ["nba:BOS"], seen_days_ago=60)
        here = _fan(conn, 2, ["nba:LAL"], seen_days_ago=1)
        nfl = _fan(conn, 3, ["nfl:KC"], seen_days_ago=60)
        assert LC.season_bridge(conn, now=NOW, web=web) == 1
        (title, body), = conn.execute("SELECT title, body FROM push_mine WHERE user_id = ?", (away,)).fetchall()
        assert title == "The NBA is back", title
        assert body.startswith(f"BOS play LAL {LC._day(tip)}, ") and "Live tab" in body, body
        assert not conn.execute("SELECT 1 FROM push_mine WHERE user_id IN (?, ?)", (here, nfl)).fetchone(), \
            "somebody here this week, or whose league never stopped, hears nothing"
        conn.execute("DELETE FROM engagement_away")
        assert LC.season_bridge(conn, now=NOW + DAY, web=web) == 0, "once a season"
        late = _fan(conn, 4, ["nba:LAL"], seen_days_ago=60, now=NOW)
        assert LC.season_bridge(conn, now=NOW + 8 * DAY, web=web) == 0, "a week after it is back, no news"
        assert not conn.execute("SELECT 1 FROM push_mine WHERE user_id = ?", (late,)).fetchone()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
