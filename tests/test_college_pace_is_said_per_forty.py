"""College and WNBA pace is said per 40 minutes, the NBA's per 48 (PACE40,
18 November 2026).

Walking a college game's page found its pace said as "81.6 possessions per 48
minutes", a number for a game college does not play: its games, and the
WNBA's, are 40 minutes. The model reads pace per 48 in every league
(engine/nba/teams.season_profiles: 48 x possessions / game minutes) and keeps
doing so, so no read, rank or threshold moves; what changes is what the page
says. What these hold:

  * the league's game length is 40 for college and the WNBA and 48 for the
    NBA, and the build carries it beside the profiles;
  * the tale of the tape's pace row and the scan's fast/slow reasons say the
    league's own minutes, with the numbers converted, the NBA's unchanged;
  * the report's pace line says the same minutes as the tape beside it (the
    research test holds its words), and its claim keeps the per-48 numbers
    it is graded on plus the minutes it was said in;
  * the fact check says the claim's own minutes (a college check says
    "Division I's"), and an older claim with no minutes still says per 48,
    as its report did.

    python3 tests/test_college_pace_is_said_per_forty.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import reportfacts as F                                          # noqa: E402
from engine.nba import scan as S, teams as T                                  # noqa: E402


def _prof(minutes=None):
    side = {"pts": 75.0, "opp_pts": 70.0, "ortg": 110.0, "drtg": 103.0, "efg": 0.52, "ranks": {"pace": 1}}
    prof = {"teams": {"DUKE": dict(side, pace=81.6), "UNC": dict(side, pace=78.0, ranks={"pace": 9})},
            "league": {"pace": 76.8, "pts": 72.0}, "n": 2}
    if minutes:
        prof["minutes"] = minutes
    return prof


def test_each_league_has_its_game_length_and_the_build_carries_it():
    assert (T.game_minutes("nba"), T.game_minutes("cbb"), T.game_minutes("WNBA"), T.game_minutes(None)) == \
        (48, 40, 40, 48)
    assert T.pace_said(81.6, 40) == 68.0 and T.pace_said(99.0, 48) == 99.0 and T.pace_said(None, 40) is None
    assert T.build([], [], "cbb")["minutes"] == 40 and T.build([], [], "nba")["minutes"] == 48


def test_the_tape_says_the_leagues_own_minutes():
    g = {"home": "DUKE", "away": "UNC"}
    college = S.tape("DUKE", "UNC", _prof(40), env=S.environment(g, _prof(40)))
    pace = next(r for r in college["rows"] if r["key"] == "pace")
    assert pace["label"] == "Pace: possessions per 40 minutes", pace
    assert (pace["a"], pace["h"]) == ("65.0", "68.0"), pace
    assert (pace["ar"], pace["hr"]) == (9, 1), "the ranks are the model's, unchanged"
    assert college["sides"]["DUKE"]["pace"] == 81.6, "what the board stores stays per 48"
    nba = S.tape("DUKE", "UNC", _prof(), env=S.environment(g, _prof()))
    pace = next(r for r in nba["rows"] if r["key"] == "pace")
    assert pace["label"] == "Pace: possessions per 48 minutes" and (pace["a"], pace["h"]) == ("78.0", "81.6")


def test_the_scans_fast_game_reason_says_the_same_minutes():
    n = 15
    h = {"team": "DUKE", "starter": True, "minutes": [32] * n, "pts": [18] * n, "reb": [5] * n, "ast": [3] * n,
         "fg3m": [2] * n, "dates": [f"2026-11-{30 - i:02d}" for i in range(n)], "opps": ["UNC"] * n,
         "by_week": {}}
    g = {"home": "DUKE", "away": "UNC"}
    env = S.environment(g, _prof(40))
    assert env["DUKE"]["minutes"] == 40 and env["DUKE"]["pace"] == (81.6 + 78.0) / 2
    r = S.read_player("A Guard", h, "DUKE", "UNC", env=env)
    # (81.6 + 78.0) / 2 = 79.8 per 48 is 66.5 per 40; 79.8 - 76.8 = 3.0 per 48 is 2.5 per 40.
    assert "A fast game: DUKE and UNC average 66.5 possessions per 40 between them (+2.5 on the league)" in r["pro"], \
        r["pro"]
    r = S.read_player("A Guard", h, "DUKE", "UNC", env=S.environment(g, _prof()))
    assert "A fast game: DUKE and UNC average 79.8 possessions per 48 between them (+3.0 on the league)" in r["pro"], \
        r["pro"]


class _Box:
    def __init__(self, teams):
        self.teams = teams

    def has(self, t):
        return t in self.teams


def test_the_fact_check_says_the_minutes_its_claim_was_said_in():
    # One college night: 70 possessions a side in a 40-minute game (200 team minutes):
    # 84.0 per 48, which is 70.0 per 40.
    line = {"fga": 60, "oreb": 8, "tov": 12, "fta": 13.636363636363637, "min": 200, "pts": 75, "fgm": 27,
            "fg3m": 7, "fg3a": 22, "ftm": 14, "reb": 35, "ast": 14}
    bx = _Box({"DUKE": dict(line), "UNC": dict(line)})
    g = {"home": "DUKE", "away": "UNC", "date": "2026-11-20",
         "live": {"state": "final", "home_score": 75, "away_score": 75}}
    claim = {"kind": "pace", "read": "fast", "league": 76.8, "pace": [["UNC", 78.0], ["DUKE", 81.6]], "minutes": 40}
    got = F.claim_grade("cbb", claim, bx, g, {})
    assert got["status"] == "right" and got["actual"] == 84.0, got
    assert got["words"] == "Right: 70.0 possessions per 40 minutes, over Division I’s 64.0.", got
    tug = F.claim_grade("cbb", dict(claim, read="split", fast="DUKE", slow="UNC"), bx, g, {})
    assert tug["words"] == "DUKE won the tug of war: 70.0 possessions per 40 minutes, nearer its 68.0 than UNC’s 65.0.", tug
    # A claim from before 18 November carries no minutes: it is checked as its report said it.
    old = {k: v for k, v in claim.items() if k != "minutes"}
    assert F.claim_grade("cbb", old, bx, g, {})["words"] == \
        "Right: 84.0 possessions per 48 minutes, over Division I’s 76.8.", old


def test_the_report_keeps_the_numbers_it_is_graded_on():
    src = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert 'claim = {"kind": "pace", "league": lp, "pace": [[a, pa], [h, ph]]}' in src
    assert 'claim["minutes"] = gm' in src
    nba = (ROOT / "tests" / "test_the_basketball_report_does_the_research.py").read_text(encoding="utf-8")
    assert "101.2 possessions per 48 minutes" in nba and "84.3 possessions per 40 minutes" in nba


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
