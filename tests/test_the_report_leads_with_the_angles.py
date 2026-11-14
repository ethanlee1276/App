"""The report leads with the angles: where each defence leaks to the players
this offence has (engine/angles, 2026-11-14).

Ethan, 2026-11-14: "it looks at the player's defense and offense and tries
to find good matchups ... the Giants are blitz-heavy defense and forces
Daniels to run ... the Commanders are not good with tight end coverage ...
it goes through teams' red zone usage for players ... it's very hard to
find that information if we are giving it". His Commanders–Giants report
won on four of them: Washington against WR1s, Washington against tight
ends, the Giants' blitz against Daniels' legs, and the Giants' red zone.

The fixture is a small league built in the game-log table: three
defences, the Giants' and Washington's players, four weeks.

    python3 tests/test_the_report_leads_with_the_angles.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import angles as A                       # noqa: E402


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, game_id TEXT, "
                 "player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER, market TEXT, value REAL)")

    def put(player, team, opp, pos, week, **m):
        for k, v in m.items():
            conn.execute("INSERT INTO player_game_logs VALUES ('nfl',2099,?,?,?,?,?,?,1,?,?)",
                         (f"{week:03d}", f"{team}-{week:03d}", player, team, opp, pos, k, v))
    # Washington's defence: the top receivers it faced went big; tight ends too.
    for w, (team, wr, te, qb) in enumerate((("DAL", "Dal WR", "Dal TE", "Dal QB"),
                                            ("PHI", "Phi WR", "Phi TE", "Phi QB"),
                                            ("LA", "La WR", "La TE", "La QB"),
                                            ("NYG", "Malik Nabers", "Isaiah Likely", "J.J. McCarthy")), 1):
        put(wr, team, "WAS", "WR", w, targets=11, receptions=8, rec_yds=110 - w, rec_td=1)
        put(f"{team} WR2", team, "WAS", "WR", w, targets=4, receptions=3, rec_yds=30, rec_td=0)
        put(te, team, "WAS", "TE", w, targets=8, receptions=6, rec_yds=72, rec_td=1)
        put(qb, team, "WAS", "QB", w, rush_yds=10, rush_att=3)
    # The Giants' defence: quarterbacks ran on it.
    for w, (team, qb, yds) in enumerate((("NO", "Tyler Shough", 32), ("ARI", "Joe Milton", 64),
                                         ("PHI", "Phi QB", 12), ("WAS", "Jayden Daniels", 103)), 1):
        put(qb, team, "NYG", "QB", w, rush_yds=yds, rush_att=7)
        put(f"{team} WR", team, "NYG", "WR", w, targets=9, receptions=4, rec_yds=40, rec_td=0)
        put(f"{team} TE", team, "NYG", "TE", w, targets=4, receptions=2, rec_yds=15, rec_td=0)
    # A stingy third defence, so the ranks mean something.
    for w in range(1, 5):
        put("Kc WR", "KC", "DEN", "WR", w, targets=12, receptions=3, rec_yds=25, rec_td=0)
        put("Kc TE", "KC", "DEN", "TE", w, targets=3, receptions=1, rec_yds=8, rec_td=0)
        put("Kc QB", "KC", "DEN", "QB", w, rush_yds=2, rush_att=1)
    # The Giants' red zone: Skattebo's carries, in their other games.
    for w in range(5, 9):
        put("Cam Skattebo", "NYG", "XXX", "RB", w, rz_car=3, rz_tgt=0, i5_car=1)
        put("Malik Nabers", "NYG", "XXX", "WR", w, rz_car=0, rz_tgt=1)
        put("Isaiah Likely", "NYG", "XXX", "TE", w, rz_car=0, rz_tgt=1)
    conn.commit()
    return conn


class _Ctx:
    def __init__(self, tables):
        self.teams = ("WAS", "NYG")
        self.opp = {"WAS": "NYG", "NYG": "WAS"}
        self.angle_tables = tables
        self.reads = [
            {"player": "Malik Nabers", "team": "NYG", "pos": "WR", "usage": {"tgt_share": 0.30}},
            {"player": "Isaiah Likely", "team": "NYG", "pos": "TE", "usage": {"tgt_share": 0.26}},
            {"player": "Cam Skattebo", "team": "NYG", "pos": "RB", "usage": {"carry_share": 0.4}},
            {"player": "Jayden Daniels", "team": "WAS", "pos": "QB", "usage": {"rush_yds_pg": 28.0}}]
        self.scan = {"charting": {
            "defense": {"NYG": {"blitz_rate": 0.403}},
            "defense_weeks": {"NYG": [{"week": 5, "opp": "WAS", "dropbacks": 37, "blitz": 23},
                                      {"week": 9, "opp": "PHI", "dropbacks": 30, "blitz": 12}]},
            "scrambles": {"WAS": [{"name": "J.Daniels", "team": "WAS", "scrambles": 34, "yds": 297, "weeks": 8}]}}}

    def name(self, t):
        return {"WAS": "Washington", "NYG": "New York"}.get(t, t)


def test_the_tables_rank_each_defences_leak():
    t = A.nfl_tables(_db(), 2099, before_week=10)
    assert t["wr1"]["WAS"]["rank"] == 1 and t["wr1"]["WAS"]["big"] == 4, t["wr1"]["WAS"]
    assert t["wr1"]["WAS"]["log"][-1]["player"] == "Malik Nabers", "the team's own top-targeted receiver"
    assert t["te"]["WAS"]["rank"] == 1 and t["te"]["WAS"]["td"] == 4
    assert t["qb_rush"]["NYG"]["rank"] == 1
    assert [x["player"] for x in t["qb_rush"]["NYG"]["log"]] == ["Joe Milton", "Phi QB", "Jayden Daniels"]
    rz = t["rz"]["NYG"]
    assert rz["top"][0]["player"] == "Cam Skattebo" and rz["run_share"] == 0.6
    assert A.nfl_tables(sqlite3.connect(":memory:"), 2099) == {}, "no table, nothing said"


def test_the_game_reads_his_four_angles():
    rows = A.for_game(_Ctx(A.nfl_tables(_db(), 2099, before_week=10)), None)
    by = {(r["player"], r["points_to"]): r for r in rows}
    nab = by[("Malik Nabers", "catches and yards")]["text"]
    assert "the most in the league" in nab and "4 of 4 topped 90" in nab, nab
    lik = by[("Isaiah Likely", "catches, yards and a touchdown")]["text"]
    assert "4 touchdowns to them in 4 games" in lik, lik
    dan = by[("Jayden Daniels", "rushing yards")]["text"]
    assert "New York blitzes on 40% of dropbacks" in dan and "62% of Washington's dropbacks when they met in week 5" in dan, dan
    assert "4.2 times a game" in dan and "103 (Jayden Daniels)" in dan, dan
    sk = by[("Cam Skattebo", "a touchdown")]["text"]
    assert "runs on 60% of its red-zone plays" in sk and "(4 inside the 5)" in sk, sk


def test_the_report_puts_them_first():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "SECTIONS = (sec_angles, sec_facts," in src
    assert "angle_tables = _angles.nfl_tables(conn, season, before_week=_week_of(result))" in src
    ftn = (ROOT / "engine" / "sources" / "ftn.py").read_text(encoding="utf-8")
    assert '"yards_gained")' in ftn and 'out["scrambles"]' in ftn and 'out["defense_weeks"]' in ftn


def test_ftn_counts_scrambles_and_each_weeks_blitz():
    from engine.sources import ftn as F
    rows = []
    for i in range(50):
        rows.append({"week": "5", "defteam": "NYG", "posteam": "WAS", "qb_dropback": "1",
                     "n_pass_rushers": "5" if i < 31 else "4", "pass_attempt": "1"})
    for i in range(5):
        rows.append({"week": "5", "defteam": "NYG", "posteam": "WAS", "qb_dropback": "1", "qb_scramble": "1",
                     "rusher_player_id": "00-1", "rusher_player_name": "J.Daniels", "yards_gained": "9"})
    t = F.season_tables(2099, rows=rows)
    wk = t["defense_weeks"]["NYG"][0]
    assert wk["opp"] == "WAS" and wk["dropbacks"] == 55 and wk["blitz"] == 31
    s = t["scrambles"][("WAS", "J.Daniels")]
    assert s["scrambles"] == 5 and s["yds"] == 45 and s["weeks"] == 1


def test_a_card_shows_his_game_log_and_how_often_he_clears_the_boards_number():
    from engine import gamereport as GR

    class C:
        result = {"most_likely": [{"player": "Isaiah Likely", "market": "rec_yds", "side": "Over", "line": 46.5},
                                  {"player": "Isaiah Likely", "market": "anytime_td", "side": "Yes", "line": 0.5}],
                  "recommendations": [{"player": "Isaiah Likely", "market": "receptions", "side": "Over",
                                       "line": 3.5, "recommended": True},
                                      {"player": "Isaiah Likely", "market": "receptions", "side": "Under",
                                       "line": 6.5, "recommended": False}]}
        form = {"Isaiah Likely": {"log": [
            {"wk": 9, "opp": "PHI", "s": {"receptions": 5, "rec_yds": 53, "targets": 6, "rec_td": 1}},
            {"wk": 7, "opp": "HOU", "s": {"receptions": 3, "rec_yds": 31, "targets": 4}},
            {"wk": 6, "opp": "NO", "s": {"receptions": 7, "rec_yds": 99, "targets": 9}},
            {"wk": 5, "opp": "WAS", "s": {"receptions": 11, "rec_yds": 94, "targets": 13, "rec_td": 2}},
            {"wk": 4, "opp": "ARI", "s": {"receptions": 5, "rec_yds": 66, "targets": 7}},
            {"wk": 3, "opp": "TEN", "s": {"receptions": 2, "rec_yds": 12, "targets": 3}}]}}
    hits = GR.hit_lines(C, {"player": "Isaiah Likely"})
    assert hits == ["Over 46.5 receiving yards: 4 of 6 games this season, 4 of his last 5",
                    "Scored: 2 of 6 games this season, 2 of his last 5",
                    "Over 3.5 catches: 4 of 6 games this season, 4 of his last 5"], hits
    log = GR.season_log("rec", C.form["Isaiah Likely"]["log"])
    assert log.startswith("Wk 9 PHI 5-53 (6), 1 TD · Wk 7 HOU 3-31 (4)"), log
    assert GR.hit_lines(C, {"player": "Nobody"}) == []


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
