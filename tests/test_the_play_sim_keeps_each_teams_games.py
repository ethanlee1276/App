"""The play simulator keeps each team's games until what they are drawn
from changes (engine/playsim.team_rng, entry_key, draw_team, KeptSims,
ideas_section).

The NFL build's readings spent 11.7 to 13.2 seconds in the simulator on
every build on 9 November and ran out its ten-second budget, so the teams
after the cutoff had no reading at all. A team's thousand games come only
from its profile (its last eight games), the fitted shocks and the trials,
which move when it plays or the box refits, never when a line does. What
these hold:

  * a team draws from its own seed: its games are the same whichever
    teams the board lists before it, or beside it;
  * a kept team reads exactly as one drawn fresh, and a moved line is
    counted again without drawing anything;
  * a team that played, a new leg, a refit, a code change or an old file
    draws again, and only that team; a leg drawn once stays drawn while
    the team's games hold, so its numbers never move;
  * the budget bounds only the teams it has to draw: kept teams are read
    after it is spent, and the one left waiting is drawn by the next build;
  * the store opens only on the production history file, lives beside the
    kept game-log reads (pruned and forgotten with them), drops a team no
    build has read in KEEP_DAYS, is never written past the reads' size
    limits, and says on the heartbeat what each build kept and drew;
  * the section's own read of two seasons of logs (`board_games`) is kept
    until those logs change or the board's teams do, and gives the games a
    fresh read gives (4.2 to 8.3 seconds a build at 22:49-23:23 on 9
    November, with every team's draw kept).

Run directly: `python3 tests/test_the_play_sim_keeps_each_teams_games.py`
"""
import math
import os
import pickle
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import logcache                                        # noqa: E402
from engine import playsim as P                                    # noqa: E402

OPP = {"AAA": "BBB", "BBB": "AAA", "CCC": "DDD", "DDD": "CCC"}
DAY = 20_400


def _logs(teams=("AAA", "BBB"), weeks=7, seed=2):
    rnd = random.Random(seed)
    rows = []
    for team in teams:
        for wk in range(1, weeks + 1):
            rows.append((2026, wk, team, f"{team} QB", "pass_att", 30 + rnd.randint(0, 10)))
            for r in range(3):
                t = rnd.randint(2, 10)
                c = min(t, rnd.randint(1, 8))
                rows += [(2026, wk, team, f"{team} WR{r}", "targets", t),
                         (2026, wk, team, f"{team} WR{r}", "receptions", c),
                         (2026, wk, team, f"{team} WR{r}", "rec_yds", c * 11.0 + rnd.random())]
            rows += [(2026, wk, team, f"{team} RB", "rush_att", rnd.randint(8, 20)),
                     (2026, wk, team, f"{team} RB", "rush_yds", rnd.randint(30, 110))]
    return rows


def _six(rows):
    return [r for r in rows if r[1] <= 6]


def _board(teams=("AAA", "BBB"), lines=None, extra=()):
    recs = []
    for team in teams:
        legs = [(f"{team} QB", "pass_yds", 230.5), (f"{team} WR0", "rec_yds", 55.5),
                (f"{team} WR1", "receptions", 3.5), (f"{team} RB", "rush_yds", 62.5)]
        legs += [x for x in extra if x[0].startswith(team)]
        for p, m, ln in legs:
            recs.append({"team": team, "opponent": OPP[team], "player": p, "market": m,
                         "line": (lines or {}).get((p, m), ln)})
    return {"recommendations": recs}


class _Conn:
    def execute(self, *a, **k):
        class R:
            def fetchone(self):
                return (2026,)
        return R()


def _section(board, rows, keep=None, budget=10_000.0, shocks=None):
    saved = (P.load_rows, P.load, P.BUILD_SECONDS)
    try:
        P.load_rows = lambda conn, sport, seasons=None, teams=None: [r for r in rows if not teams or r[2] in teams]
        P.load = lambda: {"shocks": shocks} if shocks else {}
        P.BUILD_SECONDS = budget
        return P.ideas_section(None, None, board, "nfl", conn=_Conn(), keep=keep)
    finally:
        P.load_rows, P.load, P.BUILD_SECONDS = saved


def _store(tmp, code="c1", day=DAY, name="playsim_sims-nfl-kept.pkl"):
    return P.KeptSims(os.path.join(tmp, name), "nfl", code, clock=lambda: day * 86400.0 + 5.0)


def _team_view(sec, team):
    return {k: v for k, v in sec["players"].items() if v["team"] == team}


def test_a_team_draws_from_its_own_seed_whatever_is_listed_before_it():
    rows = _six(_logs(("AAA", "BBB", "CCC")))
    both = _section(_board(("AAA", "BBB")), rows)
    # CCC comes first now (more board rows), and BBB is gone.
    alone = _section(_board(("AAA", "CCC"), extra=[("CCC WR2", "rec_yds", 30.5)]), rows)
    assert _team_view(both, "AAA") == _team_view(alone, "AAA") and _team_view(both, "AAA")
    a, b = P.team_rng("nfl", "AAA"), P.team_rng("nfl", "AAA")
    assert [a.random() for _ in range(5)] == [b.random() for _ in range(5)]
    assert P.team_rng("nfl", "AAA").random() != P.team_rng("nfl", "BBB").random()
    assert P.team_rng("nfl", "AAA").random() != P.team_rng("cfb", "AAA").random()


def test_a_kept_team_reads_as_one_drawn_fresh_and_a_moved_line_draws_nothing():
    rows, board = _six(_logs()), _board()
    with tempfile.TemporaryDirectory() as tmp:
        fresh = _section(board, rows)
        s1 = _store(tmp)
        first = _section(board, rows, keep=s1)
        assert (s1.note["drawn"], s1.note["kept"], s1.note["why"]) == (2, 0, "no copy"), s1.note
        s2 = _store(tmp)
        second = _section(board, rows, keep=s2)
        assert (s2.note["drawn"], s2.note["kept"], s2.note["why"]) == (0, 2, ""), s2.note
        assert first == fresh == second and len(fresh["players"]) == 8
        moved = _board(lines={("AAA WR0", "rec_yds"): 70.5})
        s3 = _store(tmp)
        got = _section(moved, rows, keep=s3)
        assert (s3.note["drawn"], s3.note["kept"]) == (0, 2), "a line is counted, never drawn"
        assert got == _section(moved, rows)
        assert got["players"]["AAA WR0|rec_yds"]["sim_over"] < fresh["players"]["AAA WR0|rec_yds"]["sim_over"]
        assert not s3.dirty, "nothing new, the same day: the file is left alone"


def test_a_team_that_played_is_drawn_again_and_the_other_is_kept():
    every = _logs()
    base, played = _six(every), [r for r in every if r[1] <= 6 or r[2] == "AAA"]
    board = _board()
    with tempfile.TemporaryDirectory() as tmp:
        _section(board, base, keep=_store(tmp))
        s = _store(tmp)
        got = _section(board, played, keep=s)
        assert (s.note["drawn"], s.note["kept"]) == (1, 1), s.note
        assert got == _section(board, played)
        assert _team_view(got, "BBB") == _team_view(_section(board, base), "BBB")
        # A refit moves every team's games.
        s = _store(tmp)
        _section(board, played, keep=s, shocks={"vol_sd": 0.2})
        assert (s.note["drawn"], s.note["kept"]) == (2, 0), s.note


def test_a_new_leg_draws_its_team_again_with_the_old_ones_and_their_numbers_hold():
    rows = _six(_logs())
    new = [("AAA WR2", "rec_yds", 40.5)]
    with tempfile.TemporaryDirectory() as tmp:
        before = _section(_board(), rows, keep=_store(tmp))
        s = _store(tmp)
        after = _section(_board(extra=new), rows, keep=s)
        assert (s.note["drawn"], s.note["kept"]) == (1, 1), s.note
        assert after == _section(_board(extra=new), rows)
        for k, v in before["players"].items():
            assert after["players"][k]["sim_over"] == v["sim_over"], k
        assert ("AAA WR2", "rec_yds") in s.teams["AAA"]["asked"]
        # The leg leaves the board and comes back: still drawn, nothing redrawn.
        _section(_board(), rows, keep=_store(tmp))
        s = _store(tmp)
        back = _section(_board(extra=new), rows, keep=s)
        assert (s.note["drawn"], s.note["kept"]) == (0, 2) and back == after
        # A man the simulation never plays is asked once, not on every build.
        ghost = [("AAA K", "rush_yds", 0.5)]
        _section(_board(extra=ghost), rows, keep=_store(tmp))
        s = _store(tmp)
        _section(_board(extra=ghost), rows, keep=s)
        assert (s.note["drawn"], s.note["kept"]) == (0, 2), s.note


def test_the_budget_bounds_only_the_draws_and_the_next_build_draws_the_rest():
    every = _logs()
    base, played = _six(every), [r for r in every if r[1] <= 6 or r[2] == "BBB"]
    board = _board()
    with tempfile.TemporaryDirectory() as tmp:
        _section(board, base, keep=_store(tmp))
        s = _store(tmp)
        got = _section(board, played, keep=s, budget=-1.0)
        assert (s.note["drawn"], s.note["kept"], s.note["left"]) == (0, 1, 1), s.note
        assert _team_view(got, "AAA") and not _team_view(got, "BBB"), "the kept team is read after the budget"
        s = _store(tmp)
        got = _section(board, played, keep=s)
        assert (s.note["drawn"], s.note["kept"], s.note["left"]) == (1, 1, 0), s.note
        assert got == _section(board, played)
        # Without a store the budget stops the draws just the same.
        assert len(_section(board, base, budget=-1.0)["players"]) == 0


def test_a_code_change_an_old_file_or_an_unreadable_one_draws_afresh():
    rows, board = _six(_logs()), _board()
    with tempfile.TemporaryDirectory() as tmp:
        _section(board, rows, keep=_store(tmp))
        s = _store(tmp, code="c2")
        _section(board, rows, keep=s)
        assert (s.note["drawn"], s.note["why"]) == (2, "code changed"), s.note
        path = os.path.join(tmp, "playsim_sims-nfl-kept.pkl")
        with open(path, "wb") as fh:
            pickle.dump({"v": P.KEEP_VERSION - 1, "code": "c2", "teams": {}}, fh)
        s = _store(tmp, code="c2")
        _section(board, rows, keep=s)
        assert (s.note["drawn"], s.note["why"]) == (2, "old shape"), s.note
        with open(path, "wb") as fh:
            fh.write(b"not a pickle")
        s = _store(tmp, code="c2")
        assert _section(board, rows, keep=s) == _section(board, rows)
        assert (s.note["drawn"], s.note["why"]) == (2, "unreadable"), s.note
        s = _store(tmp, code="c2")
        _section(board, rows, keep=s)
        assert (s.note["kept"], s.note["why"]) == (2, ""), "written over, and read again"


def test_the_store_opens_only_on_the_production_history_file():
    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(os.path.join(tmp, "h.db"))
        try:
            assert P.KeptSims.for_board(conn, "nfl") is None
            assert P.KeptSims.for_board(_Conn(), "nfl") is None
            keep = logcache.enabled_for
            logcache.enabled_for = lambda c: True
            try:
                s = P.KeptSims.for_board(conn, "nfl")
            finally:
                logcache.enabled_for = keep
            assert s is not None and s.code == logcache.code_hash(P.__file__)
            assert os.path.dirname(s.path) == logcache.folder()
            assert os.path.basename(s.path) == "playsim_sims-nfl-kept.pkl"
        finally:
            conn.close()


def test_a_team_no_build_reads_for_keep_days_is_dropped():
    rows = _six(_logs())
    with tempfile.TemporaryDirectory() as tmp:
        _section(_board(), rows, keep=_store(tmp, day=DAY))
        s = _store(tmp, day=DAY + P.KEEP_DAYS)
        _section(_board(("AAA",)), rows, keep=s)
        assert set(s.teams) == {"AAA", "BBB"}, "ten days: still kept"
        s = _store(tmp, day=DAY + P.KEEP_DAYS + 1)
        _section(_board(("AAA",)), rows, keep=s)
        assert set(s.teams) == {"AAA"}, "eleven: BBB goes; AAA was read today"
        assert set(_store(tmp, day=DAY + P.KEEP_DAYS + 1).teams) == {"AAA"}, "and the file says so"


def test_the_note_reaches_the_heartbeat_and_forget_drops_the_store():
    rows, board = _six(_logs()), _board()
    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = tmp
        try:
            path = P.KeptSims.path_for("nfl")
            _section(board, rows, keep=P.KeptSims(path, "nfl", "c1"))
            _section(board, rows, keep=P.KeptSims(path, "nfl", "c1"))
            note = logcache.status()["playsim_sims.nfl"]
            assert (note["teams"], note["kept"], note["drawn"], note["left"], note["why"]) == (2, 2, 0, 0, ""), note
            assert note["mb"] > 0 and "load_s" in note and "not_stored" not in note
            assert os.path.exists(path)
            assert logcache.forget("nfl") >= 1 and not os.path.exists(path)
        finally:
            if old is None:
                os.environ.pop("QB_FEEDSTATE_DIR", None)
            else:
                os.environ["QB_FEEDSTATE_DIR"] = old


def test_a_store_past_the_size_limit_is_not_written():
    rows, board = _six(_logs()), _board()
    with tempfile.TemporaryDirectory() as tmp:
        keep = logcache.MAX_MB
        logcache.MAX_MB = 0.0001
        try:
            s = _store(tmp)
            got = _section(board, rows, keep=s)
        finally:
            logcache.MAX_MB = keep
        assert s.note["not_stored"].startswith("too big"), s.note
        assert not os.path.exists(os.path.join(tmp, "playsim_sims-nfl-kept.pkl"))
        assert got == _section(board, rows), "the reading itself is whole"
        s = _store(tmp)
        _section(board, rows, keep=s)
        assert s.note["drawn"] == 2


def test_a_kept_pairs_correlation_is_the_float_its_scores_give():
    rows = _six(_logs(("AAA",)))
    prof = P.profile(P.team_games(rows)["AAA"])
    legs = [("AAA QB", "pass_yds"), ("AAA WR0", "rec_yds"), ("AAA WR1", "receptions"),
            ("AAA RB", "rush_yds"), ("AAA QB", "pass_att")]
    e = P.draw_team("nfl", "AAA", prof, {}, legs)
    sim = P.simulate(prof, P.TRIALS_BUILD, P.team_rng("nfl", "AAA"), {})
    assert sorted(e["values"]) == sorted(legs)
    for (p, m), v in e["values"].items():
        assert list(v) == sim[p][m], (p, m)
    ns = {k: P.normal_scores(sim[k[0]][k[1]]) for k in legs}
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            if a[0] == b[0]:
                assert (a, b) not in e["rho"] and (b, a) not in e["rho"], "one man's own legs are not a pair"
                continue
            assert e["rho"][P._pair(a, b)] == P.scores_corr(ns[a], ns[b]) == P.scores_corr(ns[b], ns[a]), (a, b)
    assert all(not math.isnan(r) for r in e["rho"].values())
    k1 = P.entry_key("nfl", "AAA", prof, {})
    assert k1 == P.entry_key("nfl", "AAA", dict(reversed(list(prof.items()))), {}), "the key reads no dict order"
    assert k1 != P.entry_key("nfl", "AAA", prof, {"k_rec": 1.7})
    assert k1 != P.entry_key("nfl", "AAA", prof, {}, trials=400)
    assert k1 != P.entry_key("nfl", "BBB", prof, {})



def test_the_pair_counts_are_every_trial_counted():
    """Each leg's overs are one number, a byte a trial, and a pair's trials
    both over are counted in one AND (45% of a kept build was the walk over
    every trial of every pair). Every count is the one the walk gives."""
    rows, board = _six(_logs()), _board(extra=[("AAA WR2", "rec_yds", 40.5), ("BBB WR2", "receptions", 2.5)])
    sec = _section(board, rows)
    tg = P.team_games(rows)
    checked = 0
    for team in ("AAA", "BBB"):
        legs = {(r["player"], r["market"]): r for r in board["recommendations"] if r["team"] == team}
        e = P.draw_team("nfl", team, P.profile(tg[team]), {}, set(legs))
        for (p, m), r in legs.items():
            got = sec["players"][f"{p}|{m}"]
            a = list(e["values"][(p, m)])
            n_a = sum(1 for x in a if x > r["line"])
            for link in got["links"]:
                b = list(e["values"][(link["player"], link["market"])])
                both = sum(1 for x, y in zip(a, b) if x > r["line"] and y > link["line"])
                assert link["their_over"] == round(sum(1 for y in b if y > link["line"]) / len(b), 3), link
                assert link["their_over_given_his"] == (round(both / n_a, 3) if n_a else None), link
                checked += 1
    assert checked >= 20, checked
    for v in (0, 1, 2 ** 70 + 5, (1 << 8000) - 1):
        assert P.popcount(v) == bin(v).count("1")
    assert P.over_bytes([1.0, 3.0, 2.5, 2.0], 2.0) == int.from_bytes(bytes([0, 1, 1, 0]), "little")

def _log_row(team, wk, player, market, value, season=2026):
    return {"sport": "nfl", "season": season, "period": str(wk), "game_id": f"{team}-{season}-{wk}",
            "player": player, "team": team, "opponent": OPP[team], "position": "WR", "home": 1,
            "market": market, "value": value}


def test_the_boards_log_read_is_kept_until_the_logs_or_the_teams_change():
    from engine import db
    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(tmp, "feedstate")
        enabled, reads = logcache.enabled_for, []
        load = P.load_rows
        conn = db.connect(os.path.join(tmp, "history.db"))
        try:
            logcache.enabled_for = lambda c: True
            P.load_rows = lambda *a, **k: (reads.append(1), load(*a, **k))[1]
            db.upsert_player_logs(conn, [_log_row(t, wk, f"{t} {p}", m, v) for t in ("AAA", "BBB", "CCC")
                                         for wk in range(1, 6) for p, m, v in (("WR0", "targets", 7),
                                                                               ("WR0", "rec_yds", 61.0),
                                                                               ("QB", "pass_att", 33))])
            conn.commit()
            seasons = (2025, 2026)
            first = P.board_games(conn, "nfl", seasons, {"BBB", "AAA"})
            again = P.board_games(conn, "nfl", seasons, ["AAA", "BBB"])
            note = logcache.status()["playsim_games.nfl"]
            assert reads == [1] and note["kept"] is True, (reads, note)
            assert again == first == P.team_games(load(conn, "nfl", seasons, ["AAA", "BBB"]))
            assert sorted(first) == ["AAA", "BBB"] and len(first["AAA"]) == 5
            P.board_games(conn, "nfl", seasons, ["AAA", "CCC"])
            assert len(reads) == 2, "another team list reads again"
            db.upsert_player_logs(conn, [_log_row("AAA", 6, "AAA WR0", "targets", 9)])
            conn.commit()
            moved = P.board_games(conn, "nfl", seasons, ["AAA", "BBB"])
            note = logcache.status()["playsim_games.nfl"]
            assert len(reads) == 3 and note["kept"] is False and note["why"] == "rows changed", note
            assert len(moved["AAA"]) == 6 and moved == P.team_games(load(conn, "nfl", seasons, ["AAA", "BBB"]))
        finally:
            P.load_rows, logcache.enabled_for = load, enabled
            conn.close()
            if old is None:
                os.environ.pop("QB_FEEDSTATE_DIR", None)
            else:
                os.environ["QB_FEEDSTATE_DIR"] = old


def test_the_section_reads_its_logs_through_the_kept_read():
    import inspect
    src = inspect.getsource(P.ideas_section)
    assert "board_games(conn, sport, (int(latest) - 1, int(latest)), by_team)" in src
    assert "team_games(load_rows(" not in src


def test_college_is_not_played_and_reads_nothing():
    """College's logs file each game under its date and keep no targets, so
    the college section drew no team from the day it was built and read two
    seasons of logs on every build to draw none (2 to 6 seconds, 9
    November). It now says nothing and reads nothing."""
    keep = P.load_rows
    read = []
    try:
        P.load_rows = lambda *a, **k: read.append(a) or []
        board = {"recommendations": [{"team": "espn:2483", "opponent": "espn:333", "player": "QB One",
                                      "market": "pass_yds", "line": 240.5}]}
        assert P.ideas_section(None, None, board, "cfb", conn=_Conn()) is None
        assert P.ideas_section(None, None, board, "nba", conn=_Conn()) is None
    finally:
        P.load_rows = keep
    assert read == [], "nothing read for a sport the simulator does not play"

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
