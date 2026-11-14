"""The settle pass finds each open bet's rows without rereading the day
(engine/ledger._derived_rows, name_index; engine/db idx_games_period;
engine/ledger.settle_from_history's stat_rows, absent, too_early and
game_rows parts).

The heartbeat's settle pass at 16:20 on Saturday 7 November graded nothing
and still spent 124 seconds grading: every open bet, every pass, looks for
its stat row and asks whether its game is over. Two of those reads were
bigger than their answers. A summed market's prop (points + rebounds +
assists) read the whole day's rows of its parts and normalized every name,
once per prop; and the games table had no index on a day without its
season, so every daily sport's "is his team's game final" walked that
sport's every stored season. What these hold:

  * inside a name index a summed market's parts are read once per day and
    answer every name exactly as outside one; outside, nothing is kept; so
    is a teamless college prop's six-week team window, and the roster
    file read when that window cannot place him; and the college absent
    rule's box-score, play-file and first-TD checks read each day's files
    once, through the season, and rule exactly as per bet;
  * the games table has an index on (sport, period), and the day lookups
    use it;
  * the grade's parts name the stat-row search, the absent-player rule and
    the game-finished guard (and the game markets' own evidence).

Run directly: `python3 tests/test_the_settle_finds_each_bets_rows_without_rereading.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, ledger                                      # noqa: E402

DAY = "2026-11-06"


class _Counting:
    """A history connection that counts the summed-market reads."""
    def __init__(self, conn):
        self.conn, self.reads = conn, 0

    def execute(self, sql, args=()):
        if "SELECT player, market, value, team, game_id FROM player_game_logs" in sql:
            self.reads += 1
        return self.conn.execute(sql, args)


def _hist():
    h = db.connect(":memory:")
    rows = []
    for name, team, (p, r, a) in (("Jalen Brunson", "NYK", (31, 4, 7)),
                                  ("Josh Hart", "NYK", (9, 12, 5)),
                                  ("Luka Dončić", "LAL", (35, 9, 11)),
                                  ("Jayson Tatum", "BOS", (28, 8, None))):   # no assists row
        for market, v in (("pts", p), ("reb", r), ("ast", a)):
            if v is not None:
                rows.append({"sport": "nba", "season": 2026, "period": DAY,
                             "game_id": f"g-{team}", "player": name, "team": team,
                             "opponent": "X", "position": "G", "home": 1,
                             "market": market, "value": float(v)})
    db.upsert_player_logs(h, rows)
    return h


def _bet(player, market="pra"):
    return {"sport": "nba", "market": market, "player": player, "date": DAY}


def test_inside_an_index_a_summed_markets_parts_are_read_once_and_answer_the_same():
    h = _Counting(_hist())
    where, wargs = ledger._hist_where(_bet("x"))
    asks = ["Jalen Brunson", "Josh Hart", "Luka Doncic", "Jayson Tatum", "Nobody"]
    plain = [ledger._derived_rows(h, _bet(n), where, wargs) for n in asks]
    assert h.reads == len(asks)
    h.reads = 0
    with ledger.name_index():
        kept = [ledger._derived_rows(h, _bet(n), where, wargs) for n in asks]
        assert h.reads == 1, h.reads
        ledger._derived_rows(h, _bet("Josh Hart", "pts_reb"), where, wargs)
        assert h.reads == 2, "another set of parts is its own read"
    assert kept == plain
    assert [r[0]["value"] if r else None for r in plain] == [42.0, 26.0, 55.0, None, None], \
        "a game missing a part is left out, as before"
    assert ledger._name_index_now() is None


class _CountingTeams:
    """A history connection that counts the college team-window reads."""
    def __init__(self, conn):
        self.conn, self.reads = conn, 0

    def execute(self, sql, args=()):
        if sql == ledger._CFB_TEAM_SQL or sql.startswith(
                ledger._CFB_TEAM_SPAN_SQL.split("{marks}")[0]):
            self.reads += 1
        return self.conn.execute(sql, args)


def test_a_teamless_college_prop_finds_his_team_from_one_read_a_pass():
    h = db.connect(":memory:")
    rows = []
    for day, name, team in (("2026-10-31", "José Núñez", "UNM"), ("2026-10-24", "José Núñez", "BOIS"),
                            ("2026-10-31", "Chris Olave", "OSU"), ("2026-09-01", "Old Timer", "ARMY")):
        rows.append({"sport": "cfb", "season": 2026, "period": day, "game_id": f"g{day}{team}",
                     "player": name, "team": team, "opponent": "X", "position": "WR", "home": 1,
                     "market": "rec_yds", "value": 10.0})
    db.upsert_player_logs(h, rows)
    c = _CountingTeams(h)
    since, until = "2026-09-23", "2026-11-07"
    asks = ["jose nunez", "chris olave", "old timer", "nobody"]
    plain = [ledger._recent_cfb_team(c, since, until, t) for t in asks]
    assert plain == ["UNM", "OSU", None, None], "his newest row's team; outside the window, none"
    assert c.reads == len(asks)
    c.reads = 0
    with ledger.name_index():
        kept = [ledger._recent_cfb_team(c, since, until, t) for t in asks]
        assert c.reads == 1
    assert kept == plain


def test_the_roster_file_is_parsed_once_a_pass_and_names_the_same_team():
    import json
    import tempfile
    from engine import cfbroster
    season = 2026
    d = Path(tempfile.mkdtemp())
    with open(d / f"cfb_rosters_{season}.csv", "w", encoding="utf-8") as fh:
        fh.write("athlete_id,first_name,last_name,team,position\n")
        for row in (("1", "DJ", "Miller", "Central Michigan", "WR"),
                    ("2", "Derek", "Meadows", "Notre Dame", "WR"),
                    ("3", "Kaleb", "Edwards", "Central Michigan", "RB")):
            fh.write(",".join(row) + "\n")
    h = db.connect(":memory:")
    h.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
              "away_score, extra) VALUES ('cfb', ?, '2026-11-05', 'COLG@CMU', NULL, 'CMU', 'COLG', "
              "24, 20, ?)", (season, json.dumps({"home_name": "Central Michigan",
                                                  "away_name": "Colgate"})))
    h.commit()
    saved_dir, saved_parse = cfbroster.CACHE_DIR, cfbroster.roster_schools
    parses = []

    def counting(season_, cache_dir=None):
        parses.append(season_)
        return saved_parse(season_, cache_dir)
    cfbroster.CACHE_DIR, cfbroster.roster_schools = d, counting
    try:
        asks = ["DJ Miller", "Derek Meadows", "Kaleb Edwards", "Nobody Here"]
        plain = [ledger._cfb_roster_team(h, n, season) for n in asks]
        assert plain == [cfbroster.team_of(h, n, season) for n in asks] == ["CMU", None, "CMU", None]
        parses.clear()
        with ledger.name_index():
            kept = [ledger._cfb_roster_team(h, n, season) for n in asks]
            assert parses == [season], "one parse a season a pass"
        assert kept == plain
    finally:
        cfbroster.CACHE_DIR, cfbroster.roster_schools = saved_dir, saved_parse


class _CountingFiles:
    """A history connection that counts the college file checks."""
    def __init__(self, conn):
        self.conn, self.per_team, self.per_day = conn, 0, 0

    def execute(self, sql, args=()):
        if sql.startswith("SELECT 1 FROM player_game_logs WHERE sport='cfb' AND period IN"):
            self.per_team += 1
        if sql.startswith("SELECT DISTINCT team, game_id NOT LIKE"):
            self.per_day += 1
        return self.conn.execute(sql, args)


def test_the_college_absent_rule_reads_each_days_files_once_and_rules_the_same():
    import datetime as dt
    today = dt.date.today()
    day = (today - dt.timedelta(days=1)).isoformat()
    season = (today - dt.timedelta(days=1)).year if (today - dt.timedelta(days=1)).month >= 8 \
        else (today - dt.timedelta(days=1)).year - 1
    h = db.connect(":memory:")
    for gid, home, away in (("g1", "IOWA", "ISU"), ("g2", "OSU", "MICH"), ("g3", "TEX", "OU")):
        h.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, "
                  "away_score) VALUES ('cfb', ?, ?, ?, ?, ?, ?, 24, 20)", (season, day, gid, day, home, away))
    h.commit()
    rows = []
    # IOWA: box and play file in, first TD marked. OSU: box only. TEX: nothing filed.
    for gid, team, market in (("g1-box", "IOWA", "rec_yds"), ("g1", "IOWA", "rec_yds"),
                              ("g1", "IOWA", "first_td"), ("g2-box", "OSU", "rec_yds"),
                              ("g9-box", "TEX", "rec_yds")):
        rows.append({"sport": "cfb", "season": season - 3 if team == "TEX" else season,
                     "period": day if team != "TEX" else "2023-11-04", "game_id": gid,
                     "player": f"Somebody {team}", "team": team, "opponent": "X",
                     "position": "WR", "home": 1, "market": market, "value": 1.0})
    db.upsert_player_logs(h, rows)
    bets = [{"sport": "cfb", "date": day, "player": "Absent Man", "market": m, "team": t,
             "category": "main"}
            for t in ("IOWA", "OSU", "TEX") for m in ("rec_yds", "rush_yds", "first_td")]
    c = _CountingFiles(h)
    plain = [ledger._college_absent(c, b, "absent man") for b in bets]
    assert c.per_team > 0 and c.per_day == 0
    c.per_team = c.per_day = 0
    with ledger.name_index():
        kept = [ledger._college_absent(c, b, "absent man") for b in bets]
        assert c.per_team == 0 and c.per_day == 1, (c.per_team, c.per_day)
    assert kept == plain
    verdicts = {(b["team"], b["market"]): v for b, (v, _why) in zip(bets, plain)}
    assert verdicts[("IOWA", "rec_yds")] == "void" and verdicts[("IOWA", "first_td")] == "void"
    assert verdicts[("OSU", "rec_yds")] == "wait", "box in, play file not: a receiver waits"
    assert verdicts[("OSU", "rush_yds")] == "void" and verdicts[("OSU", "first_td")] is None
    assert verdicts[("TEX", "rush_yds")] is None, "nothing filed that day: open"


def test_the_games_table_finds_a_day_without_its_season():
    h = db.connect(":memory:")
    names = {r[1] for r in h.execute("PRAGMA index_list(games)")}
    assert "idx_games_period" in names
    cols = [r[2] for r in h.execute("PRAGMA index_info(idx_games_period)")]
    assert cols == ["sport", "period"]
    for q, a in (("SELECT COUNT(*) FROM games WHERE sport=? AND period=? AND (home=? OR away=?) "
                  "AND home_score IS NOT NULL", ("cfb", DAY, "A", "A")),
                 ("SELECT period, home, away FROM games WHERE sport='cfb' AND period BETWEEN ? "
                  "AND ? AND (home=? OR away=?)", (DAY, DAY, "A", "A"))):
        plan = " ".join(str(tuple(r)) for r in h.execute("EXPLAIN QUERY PLAN " + q, a))
        assert "idx_games_period" in plan, plan


def test_the_grade_names_where_finding_the_rows_went():
    h = _hist()
    db.upsert_games(h, [
        {"sport": "nba", "season": 2026, "period": DAY, "game_id": "g-NYK", "home": "NYK",
         "away": "BOS", "home_score": 110, "away_score": 104, "spread": 0.0, "total": 220.5,
         "roof": "", "surface": "", "temp": None, "wind": None, "extra": None}])
    led = ledger.connect(":memory:")
    ledger.configure_bankroll(led, starting=1000, unit_pct=1.0)
    for player, market, line in (("Josh Hart", "pra", 24.5), ("Nobody Atall", "pts", 10.5)):
        led.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
            "stake_units, stake_dollars, status, category) VALUES "
            "('t','nba',?,?,?,'OVER',?,'FanDuel',-110,0.1,1.0,'open','main')",
            (DAY, player, market, line))
    led.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, book, odds, "
                "stake_units, stake_dollars, status, category) VALUES "
                "('t','nba',?,'NYK','moneyline','OVER',0.5,'FanDuel',-150,0.1,1.0,'open','main')",
                (DAY,))
    led.commit()
    ledger.take_grade_parts()
    with ledger.name_index():
        ledger.settle_from_history(led, h)
    parts = ledger.take_grade_parts()
    for k in ("stat_rows", "absent", "too_early", "game_rows"):
        assert k in parts and parts[k] >= 0.0, (k, parts)
    got = {r["player"]: r["status"] for r in led.execute("SELECT player, status FROM bets")}
    assert got["Josh Hart"] == "won" and got["NYK"] == "won", got


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
