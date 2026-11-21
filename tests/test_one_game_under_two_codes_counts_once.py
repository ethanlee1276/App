"""One college game filed under two codes for one side counts once (18 November 2026).

Western Michigan's page said 9-3 and listed its 3 October game at Buffalo
twice: the games table held it as "WMU@BUF" and as "WMU@BUFF", the same
20-17. The two writers spell some schools differently (Air Force "AF" and
"AFA", Albany "ALB" and "UALB"), so the copies never shared a pair and
`standings.once` kept both. And the college standings page counted our own
games all season because ESPN's bare table answered with no teams. What
these hold:

  * two finals with the same team on the same side, a day or less apart
    and the same score, are one game (a football team plays once in two
    days); a different score, a week apart, or the other side is not;
  * the team page's schedule and record count the game once;
  * college football's standings ask for Division I-FBS (group 80) when the
    bare table answers with no teams; every other league asks once.

    python3 tests/test_one_game_under_two_codes_counts_once.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, standings, teamdex                      # noqa: E402
from engine.sources import leaguestandings                     # noqa: E402


def _row(day, away, home, a, h, gid=None):
    return {"sport": "cfb", "season": 2026, "period": day, "game_id": gid or f"{away}@{home}", "date": None,
            "home": home, "away": away, "home_score": h, "away_score": a}


def test_the_same_side_and_score_on_one_day_is_one_game():
    rows = [_row("2026-10-03", "WMU", "BUF", 20, 17), _row("2026-10-03", "WMU", "BUFF", 20, 17),
            _row("2026-10-10", "KENT", "WMU", 7, 38)]
    kept = standings.once("cfb", rows)
    assert len(kept) == 2 and {r["game_id"] for r in kept} & {"WMU@BUF", "WMU@BUFF"}, kept
    # A day apart (an Eastern and a UTC day) is the same game too.
    assert len(standings.once("cfb", [_row("2026-10-03", "WMU", "BUF", 20, 17),
                                      _row("2026-10-04", "WMU", "BUFF", 20, 17)])) == 1


def test_a_different_score_a_week_apart_or_the_other_side_is_not():
    week = [_row("2026-10-03", "WMU", "BUF", 20, 17), _row("2026-10-10", "WMU", "TOL", 20, 17)]
    assert len(standings.once("cfb", week)) == 2, "a week apart: two games"
    score = [_row("2026-10-03", "WMU", "BUF", 20, 17), _row("2026-10-03", "WMU", "BUFF", 21, 17)]
    assert len(standings.once("cfb", score)) == 2, "the copies disagree: neither is dropped on a guess"
    sides = [_row("2026-10-03", "WMU", "BUF", 20, 17), _row("2026-10-03", "BUFF", "WMU", 17, 20)]
    assert len(standings.once("cfb", sides)) == 2, "the other side is another reading, not this rule's"
    nfl = [dict(r, sport="nfl") for r in week[:1] * 2]
    assert len(standings.once("nfl", nfl)) == 2, "only the leagues that file copies"
    unscored = [{"period": "2026-10-03", "home": "BUF", "away": "WMU"}, {"period": "2026-10-03", "home": "BUFF", "away": "WMU"}]
    assert len(standings.once("cfb", unscored)) == 2, "a row with no score is left as it is"


def test_the_team_page_counts_the_game_once():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [_row("2026-10-03", "WMU", "BUF", 20, 17), _row("2026-10-03", "WMU", "BUFF", 20, 17),
                           _row("2026-10-10", "KENT", "WMU", 7, 38), _row("2026-10-24", "WMU", "TOL", 38, 45)])
    conn.commit()
    sched = teamdex.season_schedule(conn, "cfb", "WMU")
    assert len(sched["games"]) == 3, [g["game_id"] for g in sched["games"]]
    season = teamdex.profile(conn, "cfb", "WMU")["seasons"][0]
    assert (season["wins"], season["losses"]) == (2, 1), season


def test_college_football_asks_for_fbs_when_the_bare_table_is_empty():
    asked = []

    def fake(url, name, **kw):
        asked.append((url, name))
        if "group=80" not in url:
            return {"children": []}
        return {"children": [{"abbreviation": "MAC", "standings": {"entries": [
            {"team": {"abbreviation": "WMU"}, "stats": [{"name": "wins", "value": 8}, {"name": "losses", "value": 3}]}]}}]}

    real = leaguestandings.fetch_json
    leaguestandings.fetch_json = fake
    try:
        rows = leaguestandings.fetch("cfb", 2026)
        assert [r["team"] for r in rows] == ["WMU"] and rows[0]["wins"] == 8, rows
        assert asked[0][0].endswith("seasontype=2") and "group=80" in asked[1][0], asked
        assert asked[0][1] != asked[1][1], "each try is cached under its own name"
        asked.clear()
        leaguestandings.fetch("nfl", 2026)
        assert len(asked) == 1 and "group" not in asked[0][0], asked
    finally:
        leaguestandings.fetch_json = real


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
