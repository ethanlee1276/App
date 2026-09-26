"""Touchdown scenarios: a scorer built from our matchup data, not his price.

Ethan, 2026-09-26: "i dont give a shit about edge, i want to use our data
for offense and defense and where offense players do good and what
defense players do bad to create a senario where a specific player can get
a touchdown, mixed with redsone usage and redzone trips and all that shit."

engine/tdscenarios reads four things off what the site already carries
for every read with a touchdown stamp — his team's implied points, the
opponent's unit rank against his position (55/45 blend), his share of the
targets or carries, his expected red-zone chances — scores each 0–2,
keeps a player at SCENARIO_MIN with defence and usage both counting, and
ranks by OUR chance. The shelf sits under the touchdown shelf; the rows
journal on paper under td_scenario; the paywall strips them.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdscenarios as T                              # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _read(player, pos, team, opp, share, td, snap=0.8):
    u = {"tgt_share": share, "snap_pct": snap} if pos != "RB" else {"carry_share": share, "snap_pct": snap}
    return {"player": player, "team": team, "opp": opp, "pos": pos, "read": "good", "label": "Good matchup",
            "usage": u, "td": td}


def _units(pass_rank, rush_rank):
    return {"blend": 0.55, "def": {"passing": {"rank": pass_rank}, "rushing": {"rank": rush_rank}}}


def test_olave_against_the_lions_is_a_scenario_and_a_thin_role_is_not():
    olave = _read("Chris Olave", "WR", "NO", "DET", 0.27,
                  {"model_prob": 0.38, "odds": 165, "book": "DraftKings", "implied_total": 25.5, "rz_chances": 1.6})
    s = T.score(olave, _units(30, 12))
    assert s and s["points"] == {"offense": 2, "defense": 2, "usage": 2, "red_zone": 2, "trips": 0}
    rz = T.score(olave, _units(30, 12), rz_own={"off": 9.1, "off_rel": 0.18}, rz_opp={"def": 8.6, "def_rel": 0.12})
    assert rz["points"]["trips"] == 2 and rz["score"] == 10
    assert "NO runs 9.1 red-zone plays a game (+18% vs the league) · DET allows 8.6 (+12%) — for the teams each has played" in rz["lines"]
    assert s["lines"][1] == "DET’s pass defence ranks 30th of 32 (55% this season, the rest last)"
    assert s["lines"][0] == "NO expected to score 25.5 by the lines" and "27% of the targets" in s["lines"][2]
    # Same game, a fourth receiver: the defence is soft but nobody throws to him.
    thin = _read("Fourth WR", "WR", "NO", "DET", 0.08,
                 {"model_prob": 0.12, "odds": 600, "book": "DraftKings", "implied_total": 25.5, "rz_chances": 0.2})
    assert T.score(thin, _units(30, 12)) is None
    # A great matchup on paper against a top defence is not a scenario.
    assert T.score(olave, _units(3, 12)) is None
    # A back reads the run defence, not the pass defence.
    back = _read("Alvin Kamara", "RB", "NO", "DET", 0.62,
                 {"model_prob": 0.45, "odds": -120, "book": "FanDuel", "implied_total": 25.5, "rz_chances": 2.2})
    assert T.score(back, _units(30, 4)) is None and T.score(back, _units(4, 27))["points"]["defense"] == 2


def test_the_shelf_ranks_by_our_chance_and_leaves_seated_scorers_off():
    reads = {"NO@DET": {"players": [
        _read("Chris Olave", "WR", "NO", "DET", 0.27,
              {"model_prob": 0.38, "odds": 165, "book": "DK", "implied_total": 25.5, "rz_chances": 1.6}),
        _read("Alvin Kamara", "RB", "NO", "DET", 0.62,
              {"model_prob": 0.52, "odds": -130, "book": "FD", "implied_total": 25.5, "rz_chances": 2.4}),
        _read("Juwan Johnson", "TE", "NO", "DET", 0.19,
              {"model_prob": 0.29, "odds": 230, "book": "DK", "implied_total": 25.5, "rz_chances": 1.0})]}}
    result = {"games": [{"away": "NO", "home": "DET", "scan": {"units": {"DET": _units(30, 28), "NO": _units(10, 10)}}}],
              "scan_reads": reads,
              "most_likely": [{"kind": "td", "player": "Alvin Kamara"}]}
    rows = T.build(result)
    assert [r["player"] for r in rows] == ["Chris Olave", "Juwan Johnson"], "Kamara is seated already"
    o = rows[0]
    assert (o["market"], o["side"], o["line"], o["odds"], o["model_prob"]) == ("anytime_td", "YES", 0.5, 165, 0.38)
    assert o["scenario"] is True and o["game"] == "NO@DET" and len(o["scenario_lines"]) == 4
    assert T.build({"games": [], "scan_reads": {}, "most_likely": []}) == []


def test_the_board_carries_journals_and_paywalls_it():
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert '"td_scenarios": _scenarios,' in pipe and "from .tdscenarios import build as _td_scenarios" in pipe
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert 'category="td_scenario", grade_label="Scenario"' in build
    from engine import gate
    assert "td_scenarios" in gate.PAID_KEYS
    # The watch rows and the read stamp carry the two numbers the scenario reads.
    td = open(os.path.join(ROOT, "engine", "touchdowns.py"), encoding="utf-8").read()
    assert '"implied_total": info.get("implied_total"),' in td and '"rz_chances": info.get("rz_expected"),' in td
    scan = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    assert '"implied_total": r.get("implied_total"), "rz_chances": r.get("rz_chances"),' in scan


def test_the_journal_keeps_the_bucket_apart():
    from engine import ledger
    conn = ledger.connect(":memory:")
    rows = [{"kind": "td", "player": "Chris Olave", "team": "NO", "opponent": "DET", "market": "anytime_td",
             "side": "YES", "line": 0.5, "odds": 165, "book": "DraftKings", "model_prob": 0.38,
             "game_date": "2026-09-28", "kickoff": "2026-09-28T17:00:00Z"}]
    n = ledger.log_most_likely(conn, {"sport": "nfl", "date": "2026-09-28", "most_likely": rows},
                               category="td_scenario", grade_label="Scenario")
    assert n == 1
    got = conn.execute("SELECT category, grade, stake_dollars FROM bets").fetchall()
    assert [tuple(r) for r in got] == [("td_scenario", "Scenario", 0.0)], [tuple(r) for r in got]
    assert ledger.log_most_likely(conn, {"sport": "nfl", "date": "2026-09-28", "most_likely": rows},
                                  category="td_scenario", grade_label="Scenario") == 0, "journaled once"


def test_the_page_draws_it_under_the_touchdown_shelf_on_both_boards():
    fn = APP[APP.index("function tdScenariosHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "Touchdown scenarios" in fn and "built from the matchup" in fn and 'data-team-game="${escapeAttr(gameId(g))}"' in fn
    assert '.replace(/ data-open="[^"]*"/g, "")' in fn, "the game door wins the tap, not the row's own"
    assert "</section>`).join(\"\")}${tdScenariosHTML()}</div>" in APP, "Home, under the shelves"
    assert '+ tdScenariosHTML() + likelyScriptsHTML(rows)' in APP, "the full board"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
