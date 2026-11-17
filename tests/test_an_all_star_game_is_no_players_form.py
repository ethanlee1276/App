"""An All-Star Game or an exhibition is no player's form (2026-11-17).

Checking the live player pages, Caitlin Clark's 2026 WNBA game log held 47
games and two clubs: the All-Star Game (25 July, "SPO" against "COOP",
129-122) and an exhibition against Nigeria's national team (2 May, 105-57)
were stored as games of the season, so every number read off her games
counted them. What these hold:

  - the nightly's ingest (engine/sources/espnhoops.ingest_day) stores an NBA
    or WNBA game only when both sides are the league's own clubs (by
    engine/divisions, any spelling the feeds use), reads no box score for
    one that is not, and says what it left out;
  - engine/hoopsexhibitions lists every stored game of the two leagues with
    a side that is no club of theirs, and removes their stat lines and
    games rows only with --apply;
  - and the runbook gives the command, the dry run first.

    python3 tests/test_an_all_star_game_is_no_players_form.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D, hoopsexhibitions as HX                            # noqa: E402
from engine.sources import espnhoops as EH                                    # noqa: E402


def _game(gid, home, away, hs, as_):
    return {"game_id": gid, "home": home, "away": away, "home_score": hs, "away_score": as_, "completed": True}


def test_the_ingest_keeps_a_leagues_own_games_and_says_what_it_left_out():
    conn = D.connect(":memory:")
    games = [_game("w1", "IND", "LV", 88, 81), _game("w2", "SPO", "COOP", 129, 122), _game("w3", "IND", "NIGER", 105, 57)]
    asked = []
    keep = (EH.load_day, EH.fetch_summary)
    EH.load_day = lambda date, ttl=None, league="wnba": [dict(g) for g in games]

    def summary(gid, ttl=30 * 24 * 3600, league="wnba"):
        asked.append(gid)
        return {}
    EH.fetch_summary = summary
    try:
        res = EH.ingest_day(conn, "2026-07-25", league="wnba")
    finally:
        EH.load_day, EH.fetch_summary = keep
    assert asked == ["w1"], ("no box score is read for a game that is not the league's", asked)
    stored = [r[0] for r in conn.execute("SELECT game_id FROM games WHERE sport='wnba'")]
    assert stored == ["w1"], stored
    said = " ".join(res["skipped"])
    assert "w2 2026-07-25: COOP at SPO is not two WNBA clubs (an All-Star or exhibition game); not stored" in said
    assert "NIGER at IND is not two WNBA clubs" in said


def test_every_spelling_of_a_club_is_the_club():
    for league, home, away in (("wnba", "CONN", "WSH"), ("wnba", "LV", "NY"), ("wnba", "GS", "POR"), ("wnba", "TOR", "LA"),
                               ("nba", "GS", "NY"), ("nba", "GSW", "LAL"), ("nba", "UTAH", "SA"), ("nba", "PHO", "BRK")):
        assert HX.league_game(league, home, away), (league, home, away)
    for league, home, away in (("wnba", "SPO", "COOP"), ("wnba", "IND", "NIGER"), ("nba", "LEB", "GIA"),
                               ("nba", "BOS", "RMD")):
        assert not HX.league_game(league, home, away), (league, home, away)


def test_the_cleanup_lists_what_was_stored_and_removes_it_only_when_asked():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = D.connect(path)
    logs = [("w1", "2026-07-20", "IND", "LV"), ("w2", "2026-07-25", "SPO", "COOP"), ("w3", "2026-05-02", "IND", "NIGER"),
            ("n1", "2026-11-12", "GS", "NY")]
    for gid, day, team, opp in logs:
        league = "nba" if gid.startswith("n") else "wnba"
        for who in ("Caitlin Clark", "Aliyah Boston"):
            for market, val in (("pts", 17.0), ("min", 21.0)):
                conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                             "position, home, market, value) VALUES (?, 2026, ?, ?, ?, ?, ?, 'G', 1, ?, ?)",
                             (league, day, gid, who, team, opp, market, val))
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES (?, 2026, ?, ?, ?, ?, 100, 90, ?)", (league, day, gid, team, opp, day))
    conn.commit()
    rep = HX.found(conn, "wnba")
    assert [(g["day"], g["sides"], g["players"]) for g in rep["games"]] == [
        ("2026-07-25", ["COOP", "SPO"], 2), ("2026-05-02", ["IND", "NIGER"], 2)], rep["games"]
    assert rep["rows"] == 8 and rep["game_rows"] == 2
    assert HX.found(conn, "nba")["games"] == [], "the NBA's GS against NY is a league game"
    # The dry run writes nothing.
    real = HX._db.connect                      # the same module as D: hold the real one before standing in
    HX._db.connect = lambda *a, **k: real(path)
    try:
        assert HX.main([]) == 0
        assert real(path).execute("SELECT COUNT(*) FROM player_game_logs WHERE sport='wnba'").fetchone()[0] == 12
        assert HX.main(["--league", "wnba", "--apply"]) == 0
    finally:
        HX._db.connect = real
    after = D.connect(path)
    assert [r[0] for r in after.execute("SELECT DISTINCT game_id FROM player_game_logs WHERE sport='wnba'")] == ["w1"]
    assert [r[0] for r in after.execute("SELECT game_id FROM games WHERE sport='wnba'")] == ["w1"]
    assert after.execute("SELECT COUNT(*) FROM player_game_logs WHERE sport='nba'").fetchone()[0] == 4


def test_the_runbook_gives_the_dry_run_first():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    at = doc.index("python3 -m engine.hoopsexhibitions\n")
    assert doc.index("python3 -m engine.hoopsexhibitions --apply") > at, "the list before the removal"


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
