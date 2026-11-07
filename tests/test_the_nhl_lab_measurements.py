"""What the NHL lab measured (docs/NHL_LAB.md), pinned where the board reads it.

Three seasons of every NHL box score, each skater-game priced walk-forward
through engine/nhl/model and judged on the season the fit never saw:

  * the memories: a rate reads 30 games (half-life), ice time 3, from up to
    60 games; a team's strength 40, shrunk by 100 games of average;
  * back-to-backs: the tired side's goals 0.93 of the model's, its rested
    opponent's 1.04; a skater's number moves by the measured factor, at
    three-quarters strength (fewer shots and goals for the tired side, more
    against it, more blocks for it); ice time does not move;
  * the goalie: a probable starter who started last night starts again 9%
    of the time; his team's other goalie starts 78%, and the card names him.

Run directly: `python3 tests/test_the_nhl_lab_measurements.py`
"""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import nhl_build as B                                          # noqa: E402
from engine.models import SportsbookLine as L                  # noqa: E402
from engine.nhl import model as M                              # noqa: E402
T = importlib.import_module("test_nhl_board_builds")   # the board fixture, shared

LEAGUE = {"F": {"sog": 8.0, "goals": 0.9, "points": 2.0, "assists": 1.1, "blocks": 1.0, "sh": 0.10},
          "D": {"sog": 5.0, "goals": 0.3, "points": 1.0, "assists": 0.7, "blocks": 4.0, "sh": 0.05}, "sv": 0.900}
SKATER = {"position": "C", "games": [{"date": f"2025-10-{i:02d}", "toi": 18.0, "sog": 3.0, "goals": 0.3,
                                      "points": 0.8, "assists": 0.5, "blocks": 1.0} for i in range(20, 0, -1)]}


def test_the_measured_memories():
    assert (M.RATE_HALF_LIFE, M.TOI_HALF_LIFE, M.RECENT_GAMES) == (30.0, 3.0, 60)
    assert (M.TEAM_HALF_LIFE, M.TEAM_PRIOR_GAMES) == (40.0, 100.0)
    assert M.HOME_EDGE == 1.04, "left alone: the two seasons pulled it opposite ways"
    assert M.XG_WINDOW == 40, "the shot-quality window stays where it was built; the lab had no xG"


def test_rest_labels_and_factors():
    assert M.rest_of(True, False) == "tired" and M.rest_of(False, True) == "opp_tired"
    assert M.rest_of(True, True) is None and M.rest_of(False, False) is None
    for stat in ("sog", "points", "goals", "assists"):
        assert M.rest_factor(stat, "tired") < 1.0 < M.rest_factor(stat, "opp_tired")
    assert M.rest_factor("blocks", "tired") > 1.0 > M.rest_factor("blocks", "opp_tired"), \
        "a tired side spends the night defending"
    assert M.rest_factor("anytime_goal", "tired") == M.B2B_SKATER["goals"], "the scorer rides goals"
    assert M.rest_factor("sog", None) == 1.0 and M.rest_factor("saves", "tired") == 1.0
    # Three-quarters of what two seasons measured: never the full fitted size.
    assert 0.97 < M.B2B_SKATER["sog"] < 0.98 and 1.04 < M.B2B_SKATER_OPP["goals"] < 1.05


def test_a_back_to_back_moves_a_skaters_number_and_says_so():
    teams = {"CGY": {"gf": 3.0, "ga": 3.0, "sog_for": 30, "sog_against": 30, "n": 82}}
    rested = M.skater_projection(SKATER, "sog", LEAGUE, teams, "CGY")
    tired = M.skater_projection(SKATER, "sog", LEAGUE, teams, "CGY", rest="tired")
    fresh_v_tired = M.skater_projection(SKATER, "sog", LEAGUE, teams, "CGY", rest="opp_tired")
    assert rested["rest"] is None and rested["rest_factor"] == 1.0
    assert abs(tired["mean"] / rested["mean"] - M.B2B_SKATER["sog"]) < 1e-3
    assert abs(fresh_v_tired["mean"] / rested["mean"] - M.B2B_SKATER_OPP["sog"]) < 1e-3
    assert tired["rest"] == "tired" and tired["toi"] == rested["toi"], "the legs move, not the minutes"
    goal = M.skater_projection(SKATER, "anytime_goal", LEAGUE, teams, "CGY", rest="tired")
    base = M.skater_projection(SKATER, "anytime_goal", LEAGUE, teams, "CGY")
    assert goal["mean"] < base["mean"]


def test_both_sides_of_a_back_to_back_move_the_game():
    teams = {"EDM": {"gf": 3.0, "ga": 3.0, "n": 82}, "CGY": {"gf": 3.0, "ga": 3.0, "n": 82}}
    lh, la = M.team_lambdas(teams, "EDM", "CGY")
    th, ta = M.team_lambdas(teams, "EDM", "CGY", rested={"EDM": False, "CGY": True})
    assert abs(th / lh - M.B2B_FACTOR) < 1e-9 and abs(ta / la - M.B2B_OPP_FACTOR) < 1e-9
    ah, aa = M.team_lambdas(teams, "EDM", "CGY", rested={"EDM": True, "CGY": False})
    assert abs(aa / la - M.B2B_FACTOR) < 1e-9 and abs(ah / lh - M.B2B_OPP_FACTOR) < 1e-9
    bh, ba = M.team_lambdas(teams, "EDM", "CGY", rested={"EDM": False, "CGY": False})
    assert (bh, ba) == (lh, la), "both tired: the seasons disagreed, so no factor"
    assert M.B2B_FACTOR == 0.93 and M.B2B_OPP_FACTOR == 1.04


def _goalie(team, dates):
    return {"team": team, "position": "G", "games": [{"date": d, "started": True} for d in dates]}


def test_the_backup_is_whoever_holds_the_other_starts():
    nights = [f"2025-10-{i:02d}" for i in range(1, 21)]
    players = {"Starter": _goalie("EDM", nights[2:]), "Backup": _goalie("EDM", nights[:2] + ["2025-10-21"]),
               "Third": _goalie("EDM", ["2025-09-30"]), "Other club": _goalie("CGY", nights)}
    assert M.backup_goalie(players, "EDM", "Starter") == "Backup"
    # Nobody else in the newest ten: the most recent other starter before them.
    alone = {"Starter": _goalie("EDM", nights), "Third": _goalie("EDM", ["2025-09-30"])}
    assert M.backup_goalie(alone, "EDM", "Starter") == "Third"
    assert M.backup_goalie({"Starter": _goalie("EDM", nights)}, "EDM", "Starter") is None
    assert M.BACKUP_B2B_STARTS == 0.78


def test_the_card_names_the_likely_backup_and_still_bets_no_saves_on_him():
    nights = [f"2025-10-{i:02d}" for i in range(1, 27)]
    players = {"Stuart Skinner": _goalie("EDM", [d for i, d in enumerate(nights) if i % 4]),
               "Calvin Pickard": _goalie("EDM", [d for i, d in enumerate(nights) if not i % 4]),
               "Dan Vladar": _goalie("CGY", nights)}
    players["Stuart Skinner"]["games"].append({"date": "2025-10-26", "started": True})
    for p in players.values():
        p["games"] = sorted({g["date"]: g for g in p["games"]}.values(), key=lambda g: g["date"], reverse=True)
    games = [{"home": "EDM", "away": "CGY", "start": ""}]
    ctx = B.scalpy_context(games, players, {"sv": 0.9}, {}, "2025-10-27", starters={})
    edm = ctx["EDM"]
    assert edm["b2b"] and edm["starter"] == "Stuart Skinner" and not edm["starter_sure"]
    assert edm["likely_backup"] == "Calvin Pickard" and edm["likely_backup_rate"] == 0.78
    confirmed = B.scalpy_context(games, players, {"sv": 0.9}, {}, "2025-10-27",
                                 starters={"EDM": {"name": "Stuart Skinner", "status": "confirmed"}})
    assert confirmed["EDM"]["starter_sure"] and confirmed["EDM"]["likely_backup"] is None
    rested = B.scalpy_context(games, players, {"sv": 0.9}, {}, "2025-10-29", starters={})
    assert not rested["EDM"]["b2b"] and rested["EDM"]["likely_backup"] is None


def test_the_rest_line_on_a_card():
    conn = T._history()
    players = M.player_games(conn)
    league = M.league_rates(players)
    teams = M.team_profiles(conn)
    p = players["Connor McDavid"]
    prop = B._Prop("Connor McDavid", "sog", "EDM")
    prop.lines = [L("DraftKings", 3.5, -120, -105), L("FanDuel", 3.5, -125, 100)]
    ctx = {"EDM": {"b2b": True, "last10": set()}, "CGY": {"b2b": False, "last10": set()}}
    proj = M.skater_projection(p, "sog", league, teams, "CGY", rest=M.rest_of(True, False))
    r = B.price_prop(prop, proj, p, "CGY", {}, "2025-10-30", ctx=ctx, teams=teams, league=league)
    assert r is not None
    rest = [x for x in r["reasons"] if x.startswith("Rest:")]
    assert rest and "EDM on the second night" in rest[0] and "-2.5%" in rest[0], rest
    # Rested on both sides: no line.
    plain = M.skater_projection(p, "sog", league, teams, "CGY")
    ctx2 = {"EDM": {"b2b": False, "last10": set()}, "CGY": {"b2b": False, "last10": set()}}
    r2 = B.price_prop(prop, plain, p, "CGY", {}, "2025-10-30", ctx=ctx2, teams=teams, league=league)
    assert not [x for x in r2["reasons"] if x.startswith("Rest:")]


GOALIE = {"position": "G", "games": [{"date": f"2025-10-{i:02d}", "toi": 60.0, "saves": 26.0, "shots_against": 29.0,
                                      "started": 1.0} for i in range(20, 0, -1)]}


def test_the_saves_model_is_scaled_to_what_a_starter_faces_with_its_measured_spread():
    """Every start of two seasons: the projection ran 5-6% high and its
    spread 22% narrow (squared z 1.55); fitted on one season and judged on
    the other, the saves ladder's log loss fell 0.011 and 0.021."""
    assert (M.SAVES_LEVEL, M.SAVES_SD_SCALE) == (0.943, 1.22)
    assert M.B2B_SAVES > 1.0 > M.B2B_SAVES_OPP, "a tired team lets more shots through; a tired opponent takes fewer"
    teams = {"EDM": {"sog_against": 29.0, "n": 82}, "CGY": {"sog_for": 29.0, "n": 82}}
    league = {"sv": 0.900}
    base = M.goalie_projection(GOALIE, league, teams, "EDM", "CGY")
    assert abs(base["mean"] - base["shots"] * base["sv"]) < 0.01, "the card's arithmetic holds: shots × save rate"
    raw_shots = 29.0 * M.opp_factor(teams, "CGY", "sog_for")
    assert abs(base["shots"] - raw_shots * M.SAVES_LEVEL) < 0.01
    tired = M.goalie_projection(GOALIE, league, teams, "EDM", "CGY", rest="tired")
    fresh_v_tired = M.goalie_projection(GOALIE, league, teams, "EDM", "CGY", rest="opp_tired")
    assert abs(tired["mean"] / base["mean"] - M.B2B_SAVES) < 1e-3 and tired["rest"] == "tired"
    assert abs(fresh_v_tired["mean"] / base["mean"] - M.B2B_SAVES_OPP) < 1e-3
    assert base["rest"] is None and base["rest_factor"] == 1.0
    # The spread: the old one times the measured scale.
    sv = base["sv"]
    old_sd = (raw_shots * M.SOG_DISPERSION * sv * sv + raw_shots * sv * (1 - sv)) ** 0.5
    assert abs(base["sd"] - old_sd * M.SAVES_SD_SCALE) < 0.01


def test_the_box_check_reads_what_the_board_reads_and_writes_nothing():
    """nhllabcheck.py's team replay is the board's team_profiles (as of the
    morning after the last stored game), its history file is opened
    read-only, and a box with too few games says so instead of guessing."""
    import io
    import contextlib
    import nhllabcheck as C
    conn = T._history()
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    board = M.team_profiles(conn)
    conn.close()
    ro = C._ro(path)
    games, played = C._schedule(ro)
    players = C._logs(ro)
    try:
        ro.execute("CREATE TABLE nope (x)")
        raise AssertionError("the box check's connection must be read-only")
    except Exception as e:                     # sqlite3.OperationalError: readonly
        assert "readonly" in str(e).lower() or "read-only" in str(e).lower(), e
    ro.close()
    replay = C._profiles(games, "2099-01-01")
    for team in ("EDM", "CGY"):
        for k in ("gf", "ga", "sog_for", "sog_against"):
            assert abs(replay[team][k] - board[team][k]) < 1e-9, (team, k)
    assert "Connor McDavid" in players and players["Connor McDavid"]["games"][0]["opponent"] == "CGY"
    assert all(len(d) == 10 for d in played.values()), "every fixture final, both sides"
    before = Path(path).stat().st_mtime
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = C.main(["--db", path])
    assert rc == 1 and "too few to read" in out.getvalue()
    assert Path(path).stat().st_mtime == before


def test_the_runbook_and_the_catchup_run_the_box_check():
    line = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 nhllabcheck.py"
    for doc in ("docs/WHEN_YOU_ARE_HOME.md", "tools/catchup.sh", "docs/RUN_NEXT.md"):
        assert line in (ROOT / doc).read_text(encoding="utf-8"), doc
    assert "step KK" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")
    assert (ROOT / "docs" / "NHL_LAB.md").is_file()


if __name__ == "__main__":
    import inspect
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
