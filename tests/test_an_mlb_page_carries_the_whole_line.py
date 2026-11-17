"""An MLB player's page carries the whole batting and pitching line (2026-11-17).

Ethan, asked whether the MLB player pages should carry the full batting and
pitching lines now or before spring: "yes build it all". What these hold:

  * the box score (engine/mlb/fulllines): every player who played, a hitter's
    AB, R, H, 2B, 3B, HR, RBI, BB, SO, SB, HBP, SF, PA and total bases, a
    pitcher's innings (as outs), hits, runs, earned runs, walks, strikeouts,
    homers, batters faced, pitches and decision; a pinch hitter names no
    position; a bench player who never came in has no line;
  * one game, one key: a game is keyed as the nightly keys it from the
    player's own game log, so a player who sat out a doubleheader's first
    game keys the second as their first, and the whole line lands on the
    graded rows' own game; a number the record graded is never changed;
  * the season's fill reads the schedule once and a box score a game, a day
    whole or not at all, without caching them; the nightly adds each final
    game's lines;
  * the game log prints the whole line, with AVG, OBP, SLG, OPS, ERA and
    WHIP as the season's through each game, read only over the games that
    carry their whole line (a game with the props' numbers alone adds to
    the counts, never to a rate);
  * the page leads a hitter with AVG, HR, RBI and OPS and a pitcher with ERA,
    K, WHIP and IP, ranked (ERA and WHIP, fewer is better); a season read
    before its box scores were filled leads with the props' numbers instead.

Run directly: `python3 tests/test_an_mlb_page_carries_the_whole_line.py`
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db, gamelog as GL, playerpage as PP              # noqa: E402
from engine.mlb import fulllines as F                                       # noqa: E402


def _bat(ab, r, h, d2, t3, hr, rbi, bb, so, sb=0, hbp=0, sf=0):
    return {"atBats": ab, "runs": r, "hits": h, "doubles": d2, "triples": t3, "homeRuns": hr, "rbi": rbi,
            "baseOnBalls": bb, "strikeOuts": so, "stolenBases": sb, "hitByPitch": hbp, "sacFlies": sf,
            "plateAppearances": ab + bb + hbp + sf}


def _pit(ip, h, r, er, bb, k, hr=0, bf=0, pc=0, w=0, lo=0, sv=0):
    return {"inningsPitched": ip, "hits": h, "runs": r, "earnedRuns": er, "baseOnBalls": bb, "strikeOuts": k,
            "homeRuns": hr, "battersFaced": bf, "numberOfPitches": pc, "wins": w, "losses": lo, "saves": sv}


def _player(name, pos, batting=None, pitching=None):
    return {"person": {"fullName": name}, "position": {"abbreviation": pos},
            "stats": {"batting": batting or {}, "pitching": pitching or {}, "fielding": {}}}


def _box(home: dict, away: dict) -> dict:
    return {"teams": {"home": {"players": {f"ID{i}": p for i, p in enumerate(home)}},
                      "away": {"players": {f"ID{i + 50}": p for i, p in enumerate(away)}}}}


JUDGE_1 = _bat(4, 1, 2, 1, 0, 1, 3, 1, 1)
BOX_1 = _box([_player("Aaron Judge", "RF", JUDGE_1),
              _player("Gerrit Cole", "P", pitching=_pit("6.1", 5, 3, 2, 2, 7, 1, 26, 98, w=1)),
              _player("Ben Rice", "PH", _bat(1, 0, 0, 0, 0, 0, 0, 0, 1)),
              _player("Bench Guy", "C"),
              _player("Opener Arm", "P", pitching=_pit("0.0", 2, 1, 1, 0, 0, bf=2, pc=11))],
             [_player("Rafael Devers", "3B", _bat(4, 0, 1, 0, 0, 0, 0, 0, 2))])


def test_a_box_score_gives_every_player_who_played_their_whole_line():
    lines = {name: (pos, line) for side in F.player_lines(BOX_1).values() for name, pos, line in side}
    assert set(lines) == {"Aaron Judge", "Gerrit Cole", "Ben Rice", "Opener Arm", "Rafael Devers"}, set(lines)
    pos, judge = lines["Aaron Judge"]
    assert pos == "RF"
    assert {m: judge[m] for m in ("at_bats", "runs", "hits", "doubles", "triples", "home_runs", "rbis", "walks",
                                  "batter_strikeouts", "stolen_bases", "hbp", "sac_flies", "pa")} == {
        "at_bats": 4, "runs": 1, "hits": 2, "doubles": 1, "triples": 0, "home_runs": 1, "rbis": 3, "walks": 1,
        "batter_strikeouts": 1, "stolen_bases": 0, "hbp": 0, "sac_flies": 0, "pa": 5}, judge
    assert judge["total_bases"] == 6, "a double and a homer and a single's worth of nothing: 2 + 4"
    assert "strikeouts" not in judge, "a batter's strikeouts are not a pitcher's"
    _, cole = lines["Gerrit Cole"]
    assert (cole["outs"], cole["strikeouts"], cole["earned_runs"], cole["hits_allowed"], cole["wins"]) == (19, 7, 2, 5, 1)
    assert lines["Ben Rice"][0] == "", "a pinch hitter's box-score position says nothing of where they play"
    assert lines["Opener Arm"][1]["outs"] == 0, "a pitcher who faced batters without an out has a line"


def _slate(*games):
    return SimpleNamespace(games=[SimpleNamespace(game_pk=pk, home=h, away=a, game_number=n, sched_state=st, live=None)
                                  for pk, h, a, n, st in games])


def test_a_doubleheader_is_keyed_as_the_game_log_keys_it():
    g1 = _box([_player("Aaron Judge", "RF", JUDGE_1)], [])
    g2 = _box([_player("Aaron Judge", "RF", _bat(3, 0, 1, 0, 0, 0, 0, 0, 0)),
               _player("Ben Rice", "1B", _bat(4, 1, 2, 0, 0, 1, 2, 0, 1))], [])
    boxes = {2: g2, 1: g1, 3: _box([_player("Not Final", "SS", JUDGE_1)], [])}
    rows = F.slate_rows(_slate((2, "NYY", "BOS", 2, "Final"), (1, "NYY", "BOS", 1, "Final"),
                               (3, "LAD", "SD", 1, "Live")), "2026-07-04", fetch=boxes.__getitem__)
    keys = {(r["player"], r["game_id"]) for r in rows}
    assert keys == {("Aaron Judge", "Aaron Judge-2026-07-04"), ("Aaron Judge", "Aaron Judge-2026-07-04-G2"),
                    ("Ben Rice", "Ben Rice-2026-07-04")}, keys
    judge_g2 = {r["market"]: r["value"] for r in rows if r["game_id"] == "Aaron Judge-2026-07-04-G2"}
    assert judge_g2["at_bats"] == 3, "the day's games in the order played, whatever order the slate lists them"
    r = next(r for r in rows if r["player"] == "Ben Rice")
    assert (r["sport"], r["season"], r["period"], r["team"], r["opponent"], r["home"]) == (
        "mlb", 2026, "2026-07-04", "NYY", "BOS", 1)


def test_a_game_whose_lines_are_kept_is_not_read_again():
    box = _box([_player("Aaron Judge", "RF", JUDGE_1)], [_player("Rafael Devers", "3B", JUDGE_1)])
    asked = []

    def fetch(pk):
        asked.append(pk)
        return box
    slate = _slate((1, "NYY", "BOS", 1, "Final"), (2, "LAD", "SD", 1, "Final"), (3, "SF", "ARI", 1, "Final"),
                   (4, "SF", "ARI", 2, "Final"))
    F.slate_rows(slate, "2026-07-04", fetch=fetch, done={"NYY", "BOS", "SF", "ARI"})
    assert asked == [2, 3, 4], "a doubleheader's clubs are read whole; a kept game is not read again"
    path, conn = _history()
    F.write(conn, F.rows(box, "NYY", "BOS", "2026-06-01"))
    assert F.done_teams(conn, "2026-06-01") == {"NYY", "BOS"} and F.done_teams(conn, "2026-06-02") == set()
    conn.close()


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = _db.connect(path)
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     [("mlb", 2026, d, f"BOS@NYY-{d}", "NYY", "BOS", hs, as_, d)
                      for d, hs, as_ in (("2026-06-01", 5, 3), ("2026-06-02", 2, 4), ("2026-06-03", 7, 1))])
    conn.commit()
    return path, conn


def test_the_whole_line_never_changes_a_number_the_record_graded():
    path, conn = _history()
    # The nightly's graded row, from the player's game log: two hits.
    conn.execute("INSERT INTO player_game_logs VALUES ('mlb', 2026, '2026-06-01', 'Aaron Judge-2026-06-01', "
                 "'Aaron Judge', 'NYY', 'BOS', 'RF', 1, 'hits', 2)")
    conn.commit()
    box = _box([_player("Aaron Judge", "RF", _bat(4, 1, 3, 1, 0, 1, 3, 1, 1))], [])
    added = F.write(conn, F.rows(box, "NYY", "BOS", "2026-06-01"))
    got = dict(conn.execute("SELECT market, value FROM player_game_logs WHERE player='Aaron Judge'").fetchall())
    assert got["hits"] == 2, "the graded number stays"
    assert got["at_bats"] == 4 and got["rbis"] == 3 and added == len(got) - 1, (added, got)
    assert F.write(conn, F.rows(box, "NYY", "BOS", "2026-06-01")) == 0, "a second read adds nothing"
    ids = {r[0] for r in conn.execute("SELECT DISTINCT game_id FROM player_game_logs")}
    assert ids == {"Aaron Judge-2026-06-01"}, "one game, one key"
    conn.close()


def _schedule():
    def game(pk, d, home, away, gtype="R", state="Final", n=1):
        return {"gamePk": pk, "officialDate": d, "gameType": gtype, "gameNumber": n,
                "status": {"abstractGameState": state},
                "teams": {"home": {"team": {"id": home}}, "away": {"team": {"id": away}}}}
    return {"dates": [
        {"date": "2026-03-01", "games": [game(1, "2026-03-01", 147, 111, gtype="S")]},
        {"date": "2026-06-01", "games": [game(10, "2026-06-01", 147, 111), game(11, "2026-06-01", 147, 111, n=2),
                                         game(12, "2026-06-01", 119, 135, state="Live")]},
        {"date": "2026-06-02", "games": [game(20, "2026-06-02", 119, 135), game(21, "2026-06-02", 147, 111)]},
        {"date": "2026-07-14", "games": [game(30, "2026-07-14", 147, 111, gtype="A")]},
        {"date": "2026-10-20", "games": [game(40, "2026-10-20", 119, 147, gtype="W"),
                                         game(40, "2026-10-20", 119, 147, gtype="W")]}]}


def test_the_seasons_fill_reads_a_day_whole_or_leaves_it_for_the_next_run():
    games = F.games_of(_schedule())
    assert [(g["pk"], g["home"], g["away"], g["game_number"]) for g in games] == [
        (10, "NYY", "BOS", 1), (11, "NYY", "BOS", 2), (20, "LAD", "SD", 1), (21, "NYY", "BOS", 1),
        (40, "LAD", "NYY", 1)], "finals of the season and postseason only, each game once"
    box = _box([_player("Aaron Judge", "RF", JUDGE_1)], [_player("Rafael Devers", "3B", JUDGE_1)])

    def fetch(pk):
        if pk == 21:
            raise OSError("timed out")
        return box
    said = []
    path, conn = _history()
    out = F.backfill(conn, 2026, fetch_box=fetch, fetch_schedule=lambda a, b: _schedule(), log=said.append, pause=0)
    assert out["games"] == 5 and out["failed"] == 2, out
    days = {r[0] for r in conn.execute("SELECT DISTINCT period FROM player_game_logs")}
    assert days == {"2026-06-01", "2026-10-20"}, "the day with a box score that could not be read waits whole"
    ids = sorted(r[0] for r in conn.execute("SELECT DISTINCT game_id FROM player_game_logs WHERE player='Aaron Judge'"))
    assert ids == ["Aaron Judge-2026-06-01", "Aaron Judge-2026-06-01-G2", "Aaron Judge-2026-10-20"], ids
    assert any("2026-06-02 left for the next run" in s for s in said), said
    src = (ROOT / "engine" / "mlb" / "fulllines.py").read_text(encoding="utf-8")
    assert "        fetch_box = box_uncached\n" in src, "a season's box scores are read, not cached"
    conn.close()


def _season(conn):
    """Three games for Judge (the middle one the props' numbers alone) and Cole, two for Devers."""
    F.write(conn, F.rows(_box([_player("Aaron Judge", "RF", JUDGE_1),
                                _player("Gerrit Cole", "P", pitching=_pit("6.1", 5, 3, 2, 2, 7, 1, 26, 98, w=1))],
                               [_player("Rafael Devers", "3B", _bat(4, 1, 1, 0, 0, 0, 1, 0, 2))]),
                         "NYY", "BOS", "2026-06-01"))
    conn.executemany("INSERT INTO player_game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     [("mlb", 2026, "2026-06-02", "Aaron Judge-2026-06-02", "Aaron Judge", "NYY", "BOS", "RF", 1,
                       m, v) for m, v in (("pa", 4), ("hits", 3), ("total_bases", 6), ("home_runs", 1))])
    conn.commit()
    F.write(conn, F.rows(_box([_player("Aaron Judge", "RF", _bat(4, 0, 1, 0, 0, 0, 0, 0, 2)),
                                _player("Gerrit Cole", "P", pitching=_pit("5.0", 6, 4, 4, 1, 5, 0, 24, 90, lo=1))],
                               [_player("Rafael Devers", "3B", _bat(4, 0, 0, 0, 0, 0, 0, 0, 3))]),
                         "NYY", "BOS", "2026-06-03"))


def test_the_game_log_prints_the_whole_line_with_the_rates_through_each_game():
    path, conn = _history()
    _season(conn)
    conn.close()
    log = GL.season_log("mlb", "Aaron Judge", db_path=path)
    bat = next(g for g in log["groups"] if g["key"] == "batting")
    assert [c["label"] for c in bat["cols"]] == ["PA", "AB", "R", "H", "2B", "3B", "HR", "RBI", "BB", "SO", "SB", "TB",
                                                 "AVG", "OBP", "SLG", "OPS"], [c["label"] for c in bat["cols"]]
    avg = next(c for c in bat["cols"] if c["key"] == "avg")
    assert avg["title"] == "Batting average, the season's through each game", avg
    by_day = {g["date"]: g["values"] for g in log["games"]}
    assert [g["date"] for g in log["games"]] == ["2026-06-03", "2026-06-02", "2026-06-01"], "newest first"
    assert by_day["2026-06-01"]["batting.avg"] == ".500" and by_day["2026-06-01"]["batting.ab"] == 4
    # The props' game: its hits count, but no at-bat stands behind them, so the rate holds.
    assert by_day["2026-06-02"]["batting.h"] == 3 and by_day["2026-06-02"]["batting.avg"] == ".500"
    assert by_day["2026-06-03"]["batting.avg"] == ".375", "3 hits in 8 at bats over the games with the whole line"
    assert by_day["2026-06-03"]["batting.obp"] == ".444", "(3 + 1) / (8 + 1)"
    assert log["totals"]["batting.h"] == 6 and log["totals"]["batting.avg"] == ".375", log["totals"]
    assert log["totals"]["batting.slg"] == ".875", "7 total bases in 8 at bats, the props' game's 6 left out"
    assert log["totals"]["batting.ops"] == "1.319", log["totals"]["batting.ops"]
    arm = GL.season_log("mlb", "Gerrit Cole", db_path=path)
    pit = [c["label"] for c in arm["groups"][0]["cols"]]
    assert pit == ["IP", "H", "R", "ER", "BB", "K", "HR", "PC", "DEC", "ERA", "WHIP"], pit
    days = {g["date"]: g["values"] for g in arm["games"]}
    assert (days["2026-06-01"]["pitching.dec"], days["2026-06-01"]["pitching.era"]) == ("W", "2.84")
    assert (days["2026-06-03"]["pitching.dec"], days["2026-06-03"]["pitching.era"]) == ("L", "4.76"), "6 ER in 34 outs"
    assert (arm["totals"]["pitching.ip"], arm["totals"]["pitching.dec"], arm["totals"]["pitching.whip"]) == (
        "11.1", "1-1", "1.24"), arm["totals"]


def test_the_page_leads_with_the_numbers_a_sports_site_leads_with():
    path, conn = _history()
    _season(conn)
    conn.close()
    PP._RANKS.clear()
    data = tempfile.mkdtemp()
    page = PP.page("mlb", "Aaron Judge", db_path=path, data_dir=data)
    head = {h["key"]: (h["value"], h["rank"]) for h in page["headline"]}
    assert list(head) == ["avg", "hr", "rbi", "ops"], head
    assert head["avg"] == (".375", 1) and head["rbi"] == (3, 1), head
    tiles = [t["label"] for t in page["last"]["tiles"]]
    assert tiles == ["AB", "H", "HR", "RBI"], tiles
    devers = PP.page("mlb", "Rafael Devers", db_path=path, data_dir=data)
    assert {h["key"]: h["rank"] for h in devers["headline"]}["avg"] == 2
    arm = PP.page("mlb", "Gerrit Cole", db_path=path, data_dir=data)
    assert [h["key"] for h in arm["headline"]] == ["era", "k", "whip", "ip"], arm["headline"]
    assert arm["headline"][0]["low"] is True and arm["headline"][0]["value"] == "4.76"
    assert [t["label"] for t in arm["last"]["tiles"]] == ["IP", "H", "ER", "K"]
    # A season read before its box scores were filled: the props' numbers lead.
    assert PP._rank_on(PP.HEAD["batting"][0], {"hits": 3, "at_bats": 8}, 2, "mlb") == 0.375
    props_only = {"pa": 9, "hits": 4, "total_bases": 8, "home_runs": 1}
    specs = [sp[0] for sp, _ in PP.headline_specs("mlb", "batting", props_only, 2)]
    assert specs == ["h", "hr", "tb", "pa"], specs
    specs = [sp[0] for sp, _ in PP.headline_specs("mlb", "pitching", {"outs": 37, "strikeouts": 13}, 2)]
    assert specs == ["k9", "k", "gp", "ip"], specs


def test_the_nightly_adds_each_final_games_lines():
    src = (ROOT / "engine" / "ingest.py").read_text(encoding="utf-8")
    body = src[src.index("def ingest_mlb_date("):]
    assert "        full = fulllines.slate_rows(slate, date, done=fulllines.done_teams(conn, date))\n" in body
    assert body.index('result["player_logs"] = db.upsert_player_logs(conn, prows)') < body.index(
        'result["full_lines"] = fulllines.write(conn, full) if full else 0'), "after the graded rows, never over them"
    assert 'result["skipped"].append(f"mlb {date} full lines: {exc}")' in body


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
