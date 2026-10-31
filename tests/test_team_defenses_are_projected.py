"""Team defenses (D/ST) are projected, and every league desk scores them.

Ethan, 2026-10-27, on the Fantasy room: "make sure we're using all our tools
and data … and that the fantasy room is actually a useful tool". Almost every
league starts a team defense; every desk here valued one at zero, so the
lineup could not choose one and no pickup list named one (docs/FANTASY.md).
What these hold (engine/dstproj, engine/fantasyweek, dstfit.py):

  - a defense's week is its points-allowed bonus off the opponent's implied
    total, its expected sacks (both sides' rates, log5), its takeaways and
    touchdowns, on the common scoring or the league's own;
  - a better defense against a worse offense projects higher, and an
    underdog offense drops back more;
  - a defense is found under every platform's name for it (Sleeper's
    "Philadelphia Eagles", ESPN's "Eagles D/ST", Yahoo's "Philadelphia"),
    never under a name two clubs share;
  - the week's file carries them beside the players; the lineup scores
    them, the pickups list one nobody rosters, the free copy keeps the
    points and drops the workings;
  - dstfit.py walks seasons forward against each defense's own average.

    python3 tests/test_team_defenses_are_projected.py
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import dstproj as D            # noqa: E402
from engine import fantasy_lineup as FL    # noqa: E402
from engine import fantasyweek as FW       # noqa: E402
from engine import gate                    # noqa: E402

WEEK_JS = (ROOT / "web" / "js" / "fantasyweek.js").read_text(encoding="utf-8")
BUILD = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")

GAME = {"home": "PHI", "away": "DAL", "spread": -7.0, "total": 44.0, "date": "2026-11-01", "kickoff": "13:00"}


def _rates():
    # The Eagles sack 9% and take it away 1.8 a game; the Cowboys give up a
    # sack on 9% and give it away 1.6 a game; the reverse pairing is meek.
    return {"PHI": {"def_sacks": 36, "def_db": 400, "off_sacks": 20, "off_db": 380, "off_games": 10,
                    "takeaways": 18, "giveaways": 9, "games": 10},
            "DAL": {"def_sacks": 18, "def_db": 400, "off_sacks": 36, "off_db": 400, "off_games": 10,
                    "takeaways": 8, "giveaways": 16, "games": 10}}


# --- the scoring -----------------------------------------------------------------------
def test_the_tiers_cover_every_score_and_a_shutout_is_rare():
    probs = D.tier_probs(22.0, 9.8, D.DEFAULT["pts_allow"])
    assert abs(sum(probs) - 1.0) < 1e-9
    assert 0.005 < probs[0] < 0.03, "a shutout against 22 implied points is a 1-in-70 week"
    assert D.tier_probs(13.0, 9.8, D.DEFAULT["pts_allow"])[2] > D.tier_probs(28.0, 9.8, D.DEFAULT["pts_allow"])[2]


def test_a_week_is_its_parts_on_the_scoring():
    dst = {"pa_mu": 17.5, "pa_sd": 9.8, "sack": 3.0, "int": 1.0, "fum_rec": 0.5, "def_td": 0.15,
           "st_td": 0.035, "safe": 0.02, "blk_kick": 0.03}
    base = D.points(dst)
    no_pa = sum(D.DEFAULT[k] * dst[k] for k in ("sack", "int", "fum_rec", "def_td", "st_td", "safe", "blk_kick"))
    assert 1.5 < base - no_pa < 3.0, "17.5 implied points is worth about two points of bonus"
    doubled = D.scoring_from_sleeper({"sack": 2.0, "pts_allow_0": 12})
    assert D.points(dst, doubled) > base + 2.9, "a league's own sack value applies"
    assert doubled["pts_allow"][0] == (0, 0, 12.0) and doubled["pts_allow"][3] == (14, 20, 1.0)
    assert D.scoring_from_sleeper({"yds_allow_0_100": 5})["yds_allow"] is True


# --- the projection ----------------------------------------------------------------------
def test_a_better_defense_against_a_worse_offense_projects_higher():
    phi = D.project(GAME, "PHI", _rates())
    dal = D.project(GAME, "DAL", _rates())
    assert phi["opponent"] == "DAL" and dal["opponent"] == "PHI"
    assert phi["dst"]["pa_mu"] == 18.5 and dal["dst"]["pa_mu"] == 25.5, "the spread splits the total"
    assert phi["dst"]["sack"] > 2 * dal["dst"]["sack"]
    assert phi["dst"]["int"] + phi["dst"]["fum_rec"] > dal["dst"]["int"] + dal["dst"]["fum_rec"]
    assert phi["expected"] > dal["expected"] + 3
    assert phi["matchup"]["grade"] == "soft" and dal["matchup"]["grade"] == "tough"
    lo, hi = phi["range"]
    assert lo < phi["expected"] < hi and D.project(GAME, "PHI", _rates())["range"] == [lo, hi], "seeded"
    assert phi["sd"] == round((hi - lo) / 2.563, 2), "the head-to-head's spread is the range's"
    assert D.project(GAME, "NYJ", _rates()) is None


def test_an_underdog_throws_more_and_a_new_team_reads_the_league():
    dog = D.project({**GAME, "spread": -10.0}, "PHI", _rates())["dst"]["sack"]
    even = D.project({**GAME, "spread": 0.0}, "PHI", _rates())["dst"]["sack"]
    assert dog > even
    new = D.project({"home": "SEA", "away": "ARI", "spread": 0, "total": 0}, "SEA", {})
    assert new["dst"]["pa_mu"] == D.LEAGUE["implied"], "no line: the league's average points"
    assert new["sources"], "and it says it is the league's rates"


# --- names on every platform ---------------------------------------------------------------
def test_a_defense_is_found_under_every_platforms_name():
    assert D.team_of("Philadelphia Eagles") == "PHI"            # Sleeper
    assert D.team_of("Eagles D/ST") == "PHI"                    # ESPN
    assert D.team_of("Philadelphia") == "PHI"                   # Yahoo
    assert D.team_of("49ers D/ST") == "SF" and D.team_of("Kansas City") == "KC"
    assert D.team_of("Whatever", "LAR") == "LA" and D.team_of("x", "JAC") == "JAX"
    assert D.team_of("New York") is None and D.team_of("Los Angeles") is None, "two clubs share it"
    assert D.team_of("Jalen Hurts") is None and D.team_of("") is None


# --- the week's file and the desks -----------------------------------------------------------
def _doc():
    rows = D.week_rows([GAME], _rates())
    wr = {"player": "CeeDee Lamb", "team": "DAL", "position": "WR", "expected": 15.0, "ppr": 15.0, "play": 1.0}
    return FW.from_board({"games": [GAME]}, defenses=rows) | {"players": sorted(
        [wr] + rows, key=lambda r: -r["expected"])}


def test_the_week_carries_them_and_every_desk_finds_them():
    doc = _doc()
    defs = [r for r in doc["players"] if r["position"] == "DEF"]
    assert [r["team"] for r in defs] == ["PHI", "DAL"]
    for name in ("Philadelphia Eagles", "Eagles D/ST", "Philadelphia"):
        m = FW.with_week({}, doc, [name])
        assert m[name]["fp_ppr"] == defs[0]["expected"] and m[name]["position"] == "DEF", name
    sleeper = FW.with_week({}, doc, ["Philadelphia Eagles"], teams={"Philadelphia Eagles": "PHI"},
                           dst_scoring=D.scoring_from_sleeper({"sack": 2.0}))
    assert sleeper["Philadelphia Eagles"]["fp_ppr"] > defs[0]["expected"] + 2, "the league's own scoring"
    roster = [{"player": "Eagles D/ST", "position": "DEF"}, {"player": "Cowboys D/ST", "position": "DEF"}]
    lineup = FL.lineup(roster, ["DEF"], {}, FW.with_week({}, doc, [r["player"] for r in roster]))
    assert lineup["starters"][0]["player"] == "Eagles D/ST", "the lineup can choose a defense now"


def test_the_pickups_name_a_defense_nobody_rosters():
    doc = _doc()
    fa = FW.free_agents(doc, ["CeeDee Lamb"])
    assert [r["team"] for r in fa["DEF"]] == ["PHI", "DAL"]
    assert [r["team"] for r in FW.free_agents(doc, ["Eagles D/ST"])["DEF"]] == ["DAL"], "rostered under ESPN's name"


def test_a_kicker_and_a_defense_are_not_missing_catches():
    for pos in ("K", "DEF"):
        out = FL.league_points({"fp_ppr": 9.0, "position": pos}, {"rec": 0.5})
        assert out["points"] == 9.0 and out["exact"] and not out["missing"], pos


def test_the_points_are_free_and_the_workings_are_paid():
    assert "dst" in gate.ROW_PAID_KEYS_BY_FILE["fantasy_week.json"][1]
    free = FW.free_view(_doc())
    d = next(r for r in free["players"] if r["position"] == "DEF")
    assert "dst" not in d and "reasons" not in d and d["expected"] > 0 and d["range"]


def test_the_build_and_the_desk_read_them():
    assert "_dst.week_rows(result.get(\"games\") or []," in BUILD and "defenses=_fw_defs)" in BUILD
    assert "dst_scoring=dstproj.scoring_from_sleeper(" in SERVER


def test_the_room_draws_them():
    assert '["ALL", "QB", "RB", "WR", "TE", "K", "DEF"]' in WEEK_JS
    assert "if (r.position === \"DEF\") return defRowHTML(r, top);" in WEEK_JS
    assert '["QB", "RB", "WR", "TE", "K", "DEF"].filter((p) => (fa[p] || []).length)' in WEEK_JS


# --- dstfit.py -------------------------------------------------------------------------------
def _history(path):
    c = sqlite3.connect(path)
    c.executescript("""
      CREATE TABLE games (sport TEXT, season INTEGER, period TEXT, game_id TEXT, home TEXT, away TEXT,
        home_score REAL, away_score REAL, spread REAL, total REAL);
      CREATE TABLE team_units (sport TEXT, season INTEGER, period TEXT, team TEXT, side TEXT, opp TEXT,
        dropbacks INTEGER, sacks INTEGER);
      CREATE TABLE team_weeks (sport TEXT, season INTEGER, period TEXT, team TEXT, takeaways INTEGER, giveaways INTEGER);
    """)
    good, bad = ("PHI", "BAL", "DEN", "MIN"), ("NYJ", "CAR", "TEN", "LV")
    for wk in range(1, 9):
        p = f"{wk:03d}"
        for i in range(4):
            h, a = (good[i], bad[(i + wk) % 4]) if wk % 2 else (bad[(i + wk) % 4], good[i])
            g_home = h in good
            hs, as_ = (24, 13) if g_home else (13, 24)
            c.execute("INSERT INTO games VALUES ('nfl', 2025, ?, ?, ?, ?, ?, ?, ?, 41)",
                      (p, f"g{wk}{i}", h, a, hs, as_, -6.0 if g_home else 6.0))
            for team, opp, good_side in ((h, a, g_home), (a, h, not g_home)):
                c.execute("INSERT INTO team_units VALUES ('nfl', 2025, ?, ?, 'def', ?, 38, ?)",
                          (p, team, opp, 4 if good_side else 1))
                c.execute("INSERT INTO team_units VALUES ('nfl', 2025, ?, ?, 'off', ?, 38, ?)",
                          (p, team, opp, 1 if good_side else 4))
                c.execute("INSERT INTO team_weeks VALUES ('nfl', 2025, ?, ?, ?, ?)",
                          (p, team, 2 if good_side else 0, 0 if good_side else 2))
    c.commit()
    c.close()


def test_the_fit_walks_seasons_forward_and_saves_what_it_measured():
    import dstfit
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "h.db")
        _history(db)
        conn = sqlite3.connect(db)
        try:
            res = dstfit.run(conn, [2025], list(range(3, 9)))
        finally:
            conn.close()
        doc = dstfit.summary(res, [2025], list(range(3, 9)))
        s = doc["score"]
        assert s["n"] == 6 * 8 and s["weeks"] == 6
        assert s["pairs_proj"] >= 0.95, s
        assert doc["league"]["sack_rate"] == round((8 * 4 * (4 + 1)) / (8 * 8 * 38), 4)
        assert dstfit.actual_points(0, 2, 1) == 10 + 2 + 2 and dstfit.actual_points(30, 0, 0) == -1
        fit = Path(d) / "dst_fit.json"
        old = D.FIT_PATH
        D.FIT_PATH = fit
        try:
            fit.write_text(json.dumps(doc))
            assert D.league_rates()["sack_rate"] == doc["league"]["sack_rate"], "the box's own rates win"
        finally:
            D.FIT_PATH = old


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
    sys.exit(0)
