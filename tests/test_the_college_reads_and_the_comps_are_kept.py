"""College's game-log reads and every sport's comps are kept until their rows
change (engine/logcache; engine/comps; engine/cfb/tds, props, defense, lineup).

The heartbeat at 08:35 on 9 November had the college build reading the same
logs again and again on every build: the comps' spot index 11.5 seconds
(each market's whole history), the props' log rows 6.4, the defense ratings
5.6, the usage table 3.8 three times (props, touchdown board, matchup scan)
and the lineup's season 3.5. What these hold:

  * a read keyed on the whole sport is served while no row of that sport
    changes, and read again when any season's does, an old one or one
    filed with no season; another sport's rows never touch it;
  * a read's other inputs (``extra``) and every source file it names
    (``code``) must match too, and say why when they do not;
  * a kept read nothing has asked for in PRUNE_DAYS goes, once a process;
  * a comps index kept between builds counts exactly what a fresh one does,
    spot tuples and a replay's cutoff included, and a replay builds its own;
  * each college read comes back the same through the cache as off the
    table, is served while its rows hold, and is read again when they move,
    when the day it stops before moves, or when the slate's teams do.

Run directly: `python3 tests/test_the_college_reads_and_the_comps_are_kept.py`
"""
import os
import pickle
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, logcache                                  # noqa: E402


class _Sandbox:
    """A history file and a feedstate directory of the test's own, with the
    cache switched on for that file (it is not the production one)."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.keep = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.dir, "feedstate")
        self.conn = db.connect(os.path.join(self.dir, "history.db"))
        self.enabled = logcache.enabled_for
        logcache.enabled_for = lambda conn: True
        return self

    def __exit__(self, *exc):
        logcache.enabled_for = self.enabled
        self.conn.close()
        if self.keep is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)


def _row(sport, season, period, player, market, value, team="UGA", opp="OSU", game=None, pos="WR"):
    return {"sport": sport, "season": season, "period": period,
            "game_id": game or f"{team}-{period}", "player": player, "team": team, "opponent": opp,
            "position": pos, "home": 1, "market": market, "value": value}


def _note(name, sport):
    return logcache.status().get(f"{name}.{sport}") or {}


def _counted(conn, name, sport, seasons, extra=None, code=None):
    calls = []

    def compute():
        calls.append(1)
        return {"rows": conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                                     (sport,)).fetchone()[0]}
    got = logcache.memo(conn, name, sport, seasons, compute, extra=extra, code=code)
    return got, len(calls)


# --- the cache: the whole sport, other inputs, several files, the prune ----
def test_a_whole_sport_read_is_served_until_any_season_of_it_moves():
    with _Sandbox() as sb:
        db.upsert_player_logs(sb.conn, [_row("cfb", 2025, "2025-09-06", "A", "rec_yds", 50),
                                        _row("cfb", 2026, "2026-09-05", "A", "rec_yds", 60)])
        sb.conn.commit()
        assert _counted(sb.conn, "whole", "cfb", None)[1] == 1, "first read computes"
        assert _counted(sb.conn, "whole", "cfb", None)[1] == 0, "served while nothing moved"
        db.upsert_player_logs(sb.conn, [_row("nba", 2026, "2026-11-01", "B", "points", 30)])
        sb.conn.commit()
        assert _counted(sb.conn, "whole", "cfb", None)[1] == 0, "another sport's rows never touch it"
        db.upsert_player_logs(sb.conn, [_row("cfb", 2019, "2019-09-07", "C", "rec_yds", 10)])
        sb.conn.commit()
        assert _counted(sb.conn, "whole", "cfb", None)[1] == 1, "an old season's row reads again"
        assert _note("whole", "cfb")["why"] == "rows changed"
        db.upsert_player_logs(sb.conn, [_row("cfb", None, "2026-09-12", "D", "rec_yds", 12)])
        sb.conn.commit()
        assert _counted(sb.conn, "whole", "cfb", None)[1] == 1, "a row with no season counts too"
        assert _counted(sb.conn, "whole", "cfb", None)[1] == 0


def test_the_whole_sport_falls_back_to_the_row_count_without_the_triggers():
    with _Sandbox() as sb:
        db.upsert_player_logs(sb.conn, [_row("cfb", 2026, "2026-09-05", "A", "rec_yds", 60)])
        sb.conn.commit()
        sb.conn.execute("DROP TRIGGER log_generations_update")
        assert logcache.generations(sb.conn, "cfb", None) is None
        assert _counted(sb.conn, "bare", "cfb", None)[1] == 1
        assert _counted(sb.conn, "bare", "cfb", None)[1] == 0
        assert "rows" in _note("bare", "cfb") and "gens" not in _note("bare", "cfb")
        sb.conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, market, "
                        "value) VALUES ('cfb', 2018, '2018-09-01', 'g', 'E', 'rec_yds', 5)")
        assert _counted(sb.conn, "bare", "cfb", None)[1] == 1, "a new row in any season reads again"


def test_another_input_must_match_and_says_so_when_it_does_not():
    with _Sandbox() as sb:
        db.upsert_player_logs(sb.conn, [_row("cfb", 2026, "2026-09-05", "A", "rec_yds", 60)])
        sb.conn.commit()
        assert _counted(sb.conn, "x", "cfb", (2026,), extra={"before": "2026-11-09"})[1] == 1
        assert _counted(sb.conn, "x", "cfb", (2026,), extra={"before": "2026-11-09"})[1] == 0
        assert _counted(sb.conn, "x", "cfb", (2026,), extra={"before": "2026-11-10"})[1] == 1
        assert _note("x", "cfb")["why"] == "inputs changed"


def test_every_source_file_named_must_match():
    with _Sandbox() as sb:
        a, b = Path(sb.dir) / "a.py", Path(sb.dir) / "b.py"
        a.write_text("A = 1\n")
        b.write_text("B = 1\n")
        db.upsert_player_logs(sb.conn, [_row("cfb", 2026, "2026-09-05", "A", "rec_yds", 60)])
        sb.conn.commit()
        assert _counted(sb.conn, "c", "cfb", (2026,), code=(str(a), str(b)))[1] == 1
        assert _counted(sb.conn, "c", "cfb", (2026,), code=(str(a), str(b)))[1] == 0
        b.write_text("B = 2\n")
        assert _counted(sb.conn, "c", "cfb", (2026,), code=(str(a), str(b)))[1] == 1
        assert _note("c", "cfb")["why"] == "code changed"


def test_a_read_nothing_asks_for_goes_after_its_days_once_a_process():
    with _Sandbox() as sb:
        db.upsert_player_logs(sb.conn, [_row("cfb", 2026, "2026-09-05", "A", "rec_yds", 60)])
        sb.conn.commit()
        _counted(sb.conn, "old", "cfb", (2026,))
        _counted(sb.conn, "new", "cfb", (2026,))
        folder = logcache.folder()
        old = [f for f in os.listdir(folder) if f.startswith("old-")]
        assert sorted(f.rsplit(".", 1)[1] for f in old) == ["json", "pkl"]
        stale = time.time() - (logcache.PRUNE_DAYS + 1) * 86400
        for f in old:
            os.utime(os.path.join(folder, f), (stale, stale))
        keep = logcache._PRUNED[0]
        try:
            logcache._PRUNED[0] = False
            assert logcache.prune() == 2
            assert not [f for f in os.listdir(folder) if f.startswith("old-")]
            assert [f for f in os.listdir(folder) if f.startswith("new-")], "a fresh read stays"
            assert logcache.prune() == 0, "once a process"
        finally:
            logcache._PRUNED[0] = keep


def test_a_read_too_big_or_a_full_folder_is_made_but_not_kept():
    with _Sandbox() as sb:
        db.upsert_player_logs(sb.conn, [_row("cfb", 2026, "2026-09-05", "A", "rec_yds", 60)])
        sb.conn.commit()
        keep = (logcache.MAX_MB, logcache.FOLDER_MB)
        try:
            logcache.MAX_MB = 0
            got, n = _counted(sb.conn, "big", "cfb", (2026,))
            assert got == {"rows": 1} and n == 1, "the read is still made"
            assert _note("big", "cfb")["not_stored"].startswith("too big")
            assert _counted(sb.conn, "big", "cfb", (2026,))[1] == 1, "and made again: nothing was kept"
            logcache.MAX_MB = keep[0]
            _counted(sb.conn, "one", "cfb", (2026,))
            logcache.FOLDER_MB = logcache.folder_mb()
            _counted(sb.conn, "two", "cfb", (2026,))
            assert _note("two", "cfb")["not_stored"].startswith("folder full")
            assert _counted(sb.conn, "one", "cfb", (2026,))[1] == 0, "what is kept is still served"
        finally:
            logcache.MAX_MB, logcache.FOLDER_MB = keep


# --- the comps ------------------------------------------------------------
def _spots(n=4000, seed=5):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        season = rnd.choice((2023, 2024, 2025, None)) if i % 97 == 0 else rnd.choice((2023, 2024, 2025))
        out.append(((season, f"{season or 2025}-10-{1 + i % 28:02d}"), f"P{i % 60}",
                    rnd.uniform(0, 90), float(rnd.randint(0, 120))))
    return out


def test_a_kept_comps_index_counts_exactly_what_a_fresh_one_does():
    from engine import comps as C
    fresh = C._BandIndex([s for s in _spots() if s[0][0] is not None])
    kept = pickle.loads(pickle.dumps(fresh, protocol=pickle.HIGHEST_PROTOCOL))
    rnd = random.Random(9)
    for _ in range(1500):
        line = rnd.randint(0, 120) + rnd.choice((0, 0.5))
        form = rnd.uniform(-5, 95)
        player = rnd.choice(("P3", "P17", "nobody", None))
        assert fresh.record(line, form, player=player) == kept.record(line, form, player=player), \
            (line, form, player)
    cut = (2024, "2024-10-15")
    assert repr(fresh.record(40.5, 30.0, before=cut, player="P3")) == \
        repr(kept.record(40.5, 30.0, before=cut, player="P3")), "a replay's cutoff"
    assert repr(fresh.record(40.5, float("nan"))) == repr(kept.record(40.5, float("nan")))
    assert kept.spots == fresh.spots, "the spot tuples come back the same"
    plain = dict(vars(fresh))
    plain.pop("_cols", None)
    assert len(pickle.dumps(fresh)) < 0.8 * len(pickle.dumps(plain)), "columns, not tuples"


def test_the_board_keeps_its_comps_and_a_replay_builds_its_own():
    from engine import comps as C
    seen = []
    real = logcache.memo

    def spy(conn, name, sport, seasons, compute, **kw):
        seen.append((name, sport, seasons))
        return compute()
    recs = [{"market": "rec_yds", "line": 40.5, "recent_values": [30, 40, 50, 45, 35],
             "player": "A", "side": "OVER", "hit_prob": 0.5}]
    with _Sandbox() as sb:
        db.upsert_player_logs(sb.conn, [_row("cfb", 2025, f"2025-09-{d:02d}", f"P{p}", "rec_yds", 10 * d)
                                        for d in range(1, 28) for p in range(4)])
        sb.conn.commit()
        logcache.memo = spy
        try:
            C.decorate([dict(r) for r in recs], sb.conn, "cfb")
            assert seen == [("comps_rec_yds", "cfb", None)], seen
            seen.clear()
            C.decorate([dict(r) for r in recs], sb.conn, "cfb", before=(2025, "2025-09-20"))
            assert seen == [], "a replay's cutoff never reads a kept index"
        finally:
            logcache.memo = real
        a = C.decorate([dict(r) for r in recs], sb.conn, "cfb")
        b = C.decorate([dict(r) for r in recs], sb.conn, "cfb")
        assert a == b and _note("comps_rec_yds", "cfb").get("kept") is True


# --- the college reads ------------------------------------------------------
def _college(conn, seasons=(2025, 2026), schools=("UGA", "OSU", "BAMA", "LSU")):
    rows = []
    rnd = random.Random(3)
    for season in seasons:
        for wk in range(1, 9):
            day = f"{season}-09-{wk:02d}" if wk < 10 else f"{season}-10-{wk:02d}"
            for i, team in enumerate(schools):
                opp = schools[(i + 1) % len(schools)]
                for p, (pos, markets) in enumerate((("QB", ("pass_yds", "pass_att", "pass_cmp", "pass_int")),
                                                    ("RB", ("rush_yds", "carries", "rush_att")),
                                                    ("WR", ("rec_yds", "receptions")))):
                    for m in markets:
                        rows.append(_row("cfb", season, day, f"{team} {pos}", m,
                                         float(rnd.randint(0, 120)), team=team, opp=opp,
                                         game=f"{team}-{season}-{wk}", pos=pos))
                    rows.append(_row("cfb", season, day, f"{team} {pos}", "anytime_td",
                                     float(rnd.random() < 0.3), team=team, opp=opp,
                                     game=f"{team}-{season}-{wk}", pos=pos))
        for wk in range(1, 9):
            for i, team in enumerate(schools):
                conn.execute("INSERT OR REPLACE INTO games (sport, season, period, game_id, home, away) "
                             "VALUES ('cfb', ?, ?, ?, ?, ?)",
                             (season, f"{season}-09-{wk:02d}", f"{team}-{season}-{wk}", team,
                              schools[(i + 1) % len(schools)]))
    db.upsert_player_logs(conn, rows)
    conn.commit()


def _bump(conn):
    db.upsert_player_logs(conn, [_row("cfb", 2026, "2026-09-30", "UGA WR", "rec_yds", 77.0,
                                      opp="OSU", game="late")])
    conn.commit()


def test_the_usage_table_is_kept_and_reads_the_same():
    from engine.cfb import tds as T
    with _Sandbox() as sb:
        _college(sb.conn)
        table = T._merged_usage(sb.conn, 2026)
        assert T.merged_usage(sb.conn, 2026) == table, "the same through the cache"
        assert _note("cfb_usage2026", "cfb")["kept"] is False
        assert T.merged_usage(sb.conn, 2026) == table
        assert _note("cfb_usage2026", "cfb")["kept"] is True, "served the second time"
        _bump(sb.conn)
        assert T.merged_usage(sb.conn, 2026) == T._merged_usage(sb.conn, 2026)
        assert _note("cfb_usage2026", "cfb")["why"] == "rows changed"


def test_the_props_log_rows_are_kept_and_read_the_same():
    from engine.cfb import props as P
    with _Sandbox() as sb:
        _college(sb.conn)
        rows = P._read_log_rows(sb.conn, [2025, 2026])
        assert P._log_rows(sb.conn, [2025, 2026]) == rows
        assert P._log_rows(sb.conn, [2025, 2026]) == rows
        assert _note("cfb_log_rows", "cfb")["kept"] is True
        assert P._log_rows(sb.conn, []) == {}


def test_the_defense_ratings_are_kept_for_the_day_and_read_again_for_the_next():
    from engine.cfb import defense as DF
    with _Sandbox() as sb:
        _college(sb.conn)
        fbs = DF.fbs_teams(sb.conn, 2026)
        want = DF._ratings(sb.conn, 2026, "2026-09-07", fbs)
        assert DF.ratings(sb.conn, 2026, before="2026-09-07") == want
        assert DF.ratings(sb.conn, 2026, before="2026-09-07") == want
        assert _note("cfb_defense", "cfb")["kept"] is True
        assert DF.ratings(sb.conn, 2026, before="2026-09-08") == DF._ratings(sb.conn, 2026, "2026-09-08", fbs)
        assert _note("cfb_defense", "cfb")["why"] == "inputs changed", "a new day reads again"


def test_the_lineup_season_is_kept_for_the_slate_and_read_again_for_another():
    from engine.cfb import lineup as L
    with _Sandbox() as sb:
        _college(sb.conn)
        want = L._season_games(sb.conn, 2026, ["OSU", "UGA"])
        assert L.season_games(sb.conn, 2026, {"UGA", "OSU"}) == want
        assert L.season_games(sb.conn, 2026, ["OSU", "UGA"]) == want
        assert _note("cfb_season_games", "cfb")["kept"] is True, "the same slate, either order"
        assert L.season_games(sb.conn, 2026, ["LSU"]) == L._season_games(sb.conn, 2026, ["LSU"])
        assert _note("cfb_season_games", "cfb")["why"] == "inputs changed"
        assert L.season_games(sb.conn, 2026) == L._season_games(sb.conn, 2026), "every team"


def test_the_touchdown_boards_reads_are_kept_and_read_the_same():
    from engine.cfb import tds as T
    with _Sandbox() as sb:
        _college(sb.conn)
        logs = T._td_game_logs(sb.conn, T.TD_LOG_GAMES, T.TD_LOG_SEASONS)
        assert T.td_game_logs(sb.conn) == logs and T.td_game_logs(sb.conn) == logs
        assert _note(f"cfb_td_logs{T.TD_LOG_GAMES}x{T.TD_LOG_SEASONS}", "cfb")["kept"] is True
        names = T._teams_by_name(sb.conn, 2026)
        assert T.teams_by_name(sb.conn, 2026) == names and T.teams_by_name(sb.conn, 2026) == names
        assert _note("cfb_teams_by_name", "cfb")["kept"] is True
        _bump(sb.conn)
        assert T.td_game_logs(sb.conn) == T._td_game_logs(sb.conn, T.TD_LOG_GAMES, T.TD_LOG_SEASONS)
        assert _note(f"cfb_td_logs{T.TD_LOG_GAMES}x{T.TD_LOG_SEASONS}", "cfb")["why"] == "rows changed"


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
