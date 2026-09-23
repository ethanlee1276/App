"""A rookie, or a player who lost last season, is on the board from week 2.

Ethan, 2026-09-23, with a screenshot of Ask: "Who do i start in fantasy
malachi fields or malik nabers" → "no NFL player by that name", and
"some players are not showing up for nfl like we are missing players".

Weeks 1-3 build a player from last season when this one has fewer than
three games (engine/carry.py), and a player with fewer than six games last
season got no carry — so a rookie, or Malik Nabers (four 2025 games, then
the knee), was dropped until his third game. On the 2026 week 3 board that
was 23 of the teams' top three by volume, among them Nabers, Malachi
Fields, Carnell Tate and Jeremiyah Love. Now (carry.thin_for, measured on
2023-2025 weeks 2-3): built from his one or two games, pulled a third of
the way to the positional mean, the card says so, and he is shown, not
staked. Week 4 on stands as it was — there it was measured worse.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import carry                                         # noqa: E402
from engine.models import GameLog, ANYTIME_TD, REC_YDS, RECEPTIONS  # noqa: E402


def _row(player, wk, value, season, pos="WR", team="NYG"):
    return {"season": str(season), "week": str(wk), "season_type": "REG",
            "player_display_name": player, "position": pos, "recent_team": team,
            "opponent_team": "OPP", "receiving_yards": str(value), "receptions": "4",
            "targets": "7"}


def test_the_rule_is_the_measured_one():
    logs = [GameLog(2, "x", 30.0), GameLog(1, "x", 60.0)]
    got = carry.thin_for(logs, [], "Rookie", REC_YDS, "WR", {"WR": 36.0}, 3)
    assert abs(got["weight"] - 2 / 3) < 1e-9 and got["own_mean"] == 45.0
    assert abs(got["baseline"] - (2 / 3 * 45.0 + 1 / 3 * 36.0)) < 1e-9
    assert carry.THIN_PRIOR_GAMES == 1.0 and carry.THIN_UPTO_WEEK == 3 and carry.STAKE_ON_THIN is False
    assert carry.thin_for(logs, [], "Rookie", REC_YDS, "WR", {"WR": 36.0}, 4) is None, "week 4 on: measured worse"
    assert carry.thin_for([], [], "Rookie", REC_YDS, "WR", {"WR": 36.0}, 2) is None, "nothing to build from"
    one = carry.thin_for(logs[:1], [], "Rookie", REC_YDS, "WR", {}, 2)
    assert one["weight"] == 1.0 and one["baseline"] == 30.0, "no anchor: his own games"


def _slate(week):
    from engine.sources import nflverse as nv
    from engine.models import Game, Weather
    prior = [_row("Vet", w, 70.0, 2025) for w in range(1, 18)]
    prior += [_row("Hurt Star", w, 90.0, 2025) for w in range(1, 5)]          # four games, then the knee
    prior += [_row("Other WR", w, 20.0, 2025, team="DAL") for w in range(1, 18)]
    current = []
    for w in range(1, min(week, 3)):
        current += [_row("Vet", w, 60.0, 2026), _row("Rookie", w, 40.0, 2026), _row("Hurt Star", w, 50.0, 2026)]
    games = [Game(home="NYG", away="DAL", weather=Weather(dome=True), injuries=[], date="2026-09-24",
                  kickoff="20:20", spread=-3.0, total=44.5)]
    saved = {n: getattr(nv, n) for n in ("build_games", "load_weekly_stats", "roster_index", "roster_teams",
                                         "load_schedules")}
    nv.build_games = lambda s, w: games
    nv.load_weekly_stats = lambda s: current if s == 2026 else prior
    roster = {n: {"team": "NYG", "position": "WR"} for n in ("Vet", "Rookie", "Hurt Star")}
    nv.roster_index = lambda s: roster
    nv.roster_teams = lambda s: {n: "NYG" for n in roster}
    nv.load_schedules = lambda: []
    try:
        report = {}
        return nv.build_slate(2026, week, carry=True, report=report), report
    finally:
        for n, fn in saved.items():
            setattr(nv, n, fn)


def test_week_three_builds_the_rookie_and_the_man_who_lost_last_season():
    slate, report = _slate(3)
    yds = {p.player: p for p in slate.props if p.market == REC_YDS}
    assert {"Vet", "Rookie", "Hurt Star"} <= set(yds), sorted(yds)
    assert set(report["thin"]) == {"Rookie", "Hurt Star"} and "Vet" in report["carried"]
    assert report["thin"]["Hurt Star"]["prior_games"] == 4 and report["thin"]["Rookie"]["prior_games"] == 0
    r = yds["Rookie"]
    assert [g.value for g in r.logs] == [40.0, 40.0] and not any(getattr(g, "prior", False) for g in r.logs)
    assert r.form_prior_games == 1.0 and r.form_prior is not None and r.form_prior_n == carry.THIN_ANCHOR_GAMES
    assert yds["Vet"].form_prior is None, "a carried player is untouched"
    assert any(p.player == "Rookie" and p.market == ANYTIME_TD for p in slate.props), "and his touchdown prop"
    assert any(p.player == "Rookie" and p.market == RECEPTIONS for p in slate.props)


def test_the_projection_is_pulled_the_measured_third():
    from engine.form import compute_form
    slate, report = _slate(3)
    r = next(p for p in slate.props if p.player == "Rookie" and p.market == REC_YDS)
    anchor = r.form_prior
    plain = compute_form(r.logs, r.career_avg, None).mean
    pulled = compute_form(r.logs, r.career_avg, None, prior=anchor, prior_n=r.form_prior_n,
                          prior_games=r.form_prior_games).mean
    assert abs(pulled - (2 / 3 * plain + 1 / 3 * anchor)) < 1e-9


def test_week_four_on_stands_as_it_was():
    slate, report = _slate(5)
    assert "Rookie" not in {p.player for p in slate.props} and not report["thin"]


def test_the_card_says_what_it_stands_on_and_it_is_shown_not_staked():
    recs = [{"player": "Rookie", "recommended": True}, {"player": "Hurt Star", "recommended": False},
            {"player": "Vet", "recommended": True}]
    n = carry.decorate(recs, {"thin": {
        "Rookie": {"games": 2, "prior_games": 0, "weight": 2 / 3, "position": "WR"},
        "Hurt Star": {"games": 1, "prior_games": 4, "weight": 0.5, "position": "WR"}}})
    assert n == 2
    assert recs[0]["warnings"][0] == ("Only 2 games this season (none last season): projected from them, "
                                      "pulled 33% toward the typical WR")
    assert recs[0]["recommended"] is False and recs[0]["thin"]["held_back"] is True
    assert recs[1]["warnings"] == ["Only 1 game this season (4 last season, too few to carry): projected "
                                   "from it, pulled 50% toward the typical WR"]
    assert "held_back" not in recs[1]["thin"], "never recommended, so not relabelled"
    assert recs[2] == {"player": "Vet", "recommended": True}


def test_the_build_prints_and_publishes_it():
    src = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert 'if carry_report.get("carried") or carry_report.get("thin"):' in src
    assert 'result["thin"] = ' in src and "Built {len(thin)} player(s) on one or two games" in src


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
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
