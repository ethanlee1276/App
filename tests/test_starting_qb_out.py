"""A starting quarterback out: the model notices, prices what was measured, shows it.

Ethan, 2026-09-23: "there is a lot of starting qbs out in the nfl right now
so I wanna make sure the models notice that and we show that in the
responses and shit under the card like the other shit."

Before: a depth-chart watch put one warning line on pass-catcher props and
moved nothing; the injured starter's props were built and held; the man
actually starting had none. Now (engine/qbchange.py, engine/qbfit.py):
the change is detected from the injury report, the live board and the
depth chart; the replacement's props are built and the starter's dropped;
behind a downgrade the team's receivers take the measured drop (yards
×0.897, catches ×0.912, every season 2022-2025); every row of that team,
every game card and Ask carry it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import qbchange as Q                                      # noqa: E402
from engine import qbfit as F                                         # noqa: E402
from engine.models import (Injury, Prop, SportsbookLine, GameLog, Game, Weather, Team,  # noqa: E402
                           DefenseProfile, REC_YDS, RECEPTIONS, PASS_YDS)
from engine.sources import nflverse as N                              # noqa: E402

QB = {"teams": {"HOU": {"starter": "C.J. Stroud", "backup": "Davis Mills"},
                "WAS": {"starter": "Jayden Daniels", "backup": "Marcus Mariota"},
                "KC": {"starter": "Patrick Mahomes", "backup": "Gardner Minshew"}},
      "passing": {"C.J. Stroud": (600.0, 4200.0), "Davis Mills": (70.0, 371.0),
                  "Jayden Daniels": (500.0, 3700.0), "Marcus Mariota": (120.0, 870.0),
                  "Patrick Mahomes": (600.0, 4000.0)}}


def _inj(player, team, status):
    return Injury(player=player, team=team, position="QB", role="qb", status=status)


def test_the_change_is_noticed_from_the_report_and_from_the_depth_chart():
    chs = Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT"), _inj("Patrick Mahomes", "KC", "QUESTIONABLE")])
    assert set(chs) == {"HOU"}, "questionable is not out: the old watch line covers him"
    h = chs["HOU"]
    assert (h["replacement"], h["tier"], h["status"]) == ("Davis Mills", "downgrade", "OUT")
    assert Q.headline(h) == "C.J. Stroud (OUT) — Davis Mills starts"
    assert Q.detail(h) == "Davis Mills has thrown for 5.3 yards an attempt (70 attempts) against C.J. Stroud’s 7.0"
    w = Q.changes(QB, [_inj("Jayden Daniels", "WAS", "IR")])["WAS"]
    assert w["tier"] == "similar", "7.25 a throw against 7.4 is not a downgrade"
    d = Q.changes(QB, [], {"KC": "Gardner Minshew"})["KC"]
    assert d["status"] == "BENCHED" and d["replacement"] == "Gardner Minshew"
    assert Q.headline(d) == "Gardner Minshew starts over Patrick Mahomes (this week’s depth chart)"
    both = Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT"), _inj("Davis Mills", "HOU", "OUT")])["HOU"]
    assert both["replacement"] is None and "not named yet" in Q.headline(both), "a ruled-out backup is not the answer"
    assert Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT")], {"HOU": "C.J. Stroud"})["HOU"]["replacement"] == \
        "Davis Mills", "a depth chart that has not caught up does not un-injure him"


def _prop(player, team, pos, market, role):
    return Prop(player=player, team=team, opponent="TEN", position=pos, market=market,
                logs=[GameLog(w, "x", 60.0) for w in range(1, 6)], career_avg=60.0, vs_opponent_avg=None,
                lines=[SportsbookLine("book", 59.5, -110, -110)], usage_role=role)


class _Slate:
    def __init__(self, props, games):
        self.props, self.games = props, games


def test_the_man_who_starts_gets_the_props_and_the_starter_and_idle_backups_do_not():
    props = [_prop("C.J. Stroud", "HOU", "QB", PASS_YDS, "starter"), _prop("Davis Mills", "HOU", "QB", PASS_YDS, "backup"),
             _prop("Patrick Mahomes", "KC", "QB", PASS_YDS, "starter"),
             _prop("Gardner Minshew", "KC", "QB", PASS_YDS, "backup"), _prop("Nico Collins", "HOU", "WR", REC_YDS, "wr1")]
    games = [Game(home="HOU", away="TEN", weather=Weather()), Game(home="KC", away="DEN", weather=Weather())]
    sl = _Slate(props, games)
    chs = Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT")])
    got = Q.apply_to_slate(sl, chs)
    assert [p.player for p in sl.props] == ["Davis Mills", "Patrick Mahomes", "Nico Collins"]
    assert sl.props[0].usage_role == "starter" and got["kept"] == ["Davis Mills"]
    assert set(games[0].qb_changes) == {"HOU"} and games[1].qb_changes == {}


def test_the_measured_drop_moves_a_receiver_and_the_card_goes_on_every_row():
    g = Game(home="HOU", away="TEN", weather=Weather())
    g.qb_changes = Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT")])
    m, why, card = Q.effect(_prop("Nico Collins", "HOU", "WR", REC_YDS, "wr1"), g)
    assert m == 0.897 and why.startswith("QB change: C.J. Stroud (OUT) — Davis Mills starts")
    assert card["applied"] == 0.897 and "receivers lost 10%" in card["note"]
    assert Q.effect(_prop("Nico Collins", "HOU", "WR", RECEPTIONS, "wr1"), g)[0] == 0.912
    m, why, card = Q.effect(_prop("Dalton Schultz", "HOU", "TE", REC_YDS, "te"), g)
    assert (m, why) == (1.0, "") and card["note"].startswith("Shown for you"), "not measured for a tight end"
    assert Q.effect(_prop("Davis Mills", "HOU", "QB", PASS_YDS, "starter"), g)[2]["note"] == \
        "Starting in place of C.J. Stroud"
    assert Q.effect(_prop("Calvin Ridley", "TEN", "WR", REC_YDS, "wr1"), g) == (1.0, "", None), "the other team"
    assert Q.EFFECT == {("rec_yds", "WR", "downgrade"): 0.897, ("receptions", "WR", "downgrade"): 0.912}


def test_the_projection_prices_it_in_the_lineup_step():
    from engine.projection import build_projection
    g = Game(home="HOU", away="TEN", weather=Weather())
    g.qb_changes = Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT")])
    opp = Team(abbr="TEN", name="TEN", defense=DefenseProfile(team="TEN"))
    base = build_projection(_prop("Nico Collins", "HOU", "WR", REC_YDS, "wr1"),
                            Game(home="HOU", away="TEN", weather=Weather()), opp)
    now = build_projection(_prop("Nico Collins", "HOU", "WR", REC_YDS, "wr1"), g, opp)
    assert abs(now.mean / base.mean - 0.897) < 1e-6
    steps = {s["key"]: s for s in now.chain["steps"]}
    assert steps["lineup"]["mult"] == 0.897 and "QB change" in steps["lineup"]["why"]
    assert steps["injury"]["mult"] == 1.0, "measured, so outside the hand-tuned cap"
    assert now.injury.qb_card["headline"] == "C.J. Stroud (OUT) — Davis Mills starts"


def test_one_starting_quarterback_per_team_from_the_merged_specs():
    S = N.PlayerSpec
    specs = [S("Jaxson Dart", "pass_yds", "starter", "QB"), S("Russell Wilson", "pass_yds", "backup", "QB"),
             S("Jameis Winston", "pass_yds", "starter", "QB"), S("Jaxson Dart", "pass_yds", "backup", "QB"),
             S("Malik Nabers", "rec_yds", "wr1", "WR")]
    got = N.one_quarterback_each(specs, lambda p: "NYG")
    assert [(s.player, s.usage_role) for s in got] == [("Jaxson Dart", "starter"), ("Russell Wilson", "backup"),
                                                        ("Malik Nabers", "wr1")], \
        "last season's leader filed under this team is not a second starter"
    rows = []
    for name, att in (("Starter", 35), ("Backup", 4)):
        for wk in (1, 2, 3):
            rows.append({"season_type": "REG", "week": str(wk), "recent_team": "BUF", "position": "QB",
                         "player_display_name": name, "attempts": str(att)})
    roles = {(s.player, s.usage_role) for s in N.top_players_for_week(rows, {"BUF"}, 4, qb_backups=True)}
    assert ("Starter", "starter") in roles and ("Backup", "backup") in roles
    assert not [s for s in N.top_players_for_week(rows, {"BUF"}, 4) if s.player == "Backup"], "off unless asked"


def test_the_fitter_recovers_a_known_drop_and_the_rule_wants_three_seasons():
    seasons = {}
    for season in (2022, 2023, 2024, 2025):
        rows = []
        for wk in range(1, 11):
            starter_out = wk in (6, 8)
            rows.append({"season_type": "REG", "week": str(wk), "team": "HOU", "position": "QB",
                         "player_display_name": "Backup" if starter_out else "Starter", "attempts": "30",
                         "passing_yards": "150" if starter_out else "240"})
            rows.append({"season_type": "REG", "week": str(wk), "team": "HOU", "position": "WR",
                         "player_display_name": "Receiver", "targets": "8",
                         "receiving_yards": str(60.0 * (0.8 if starter_out else 1.0)), "receptions": "5"})
        seasons[season] = rows
    res = F.measure(F.samples(seasons))
    k = ("rec_yds", "WR", "downgrade")
    assert abs(res[k]["mult"] - 0.8) < 0.01 and res[k]["n"] == 8
    fake = {("a", "WR", "similar"): {"mult": 1.10, "se": 0.03, "n": 300, "per": {1: 1.47, 2: 0.99, 3: 1.06, 4: 0.99}},
            ("b", "WR", "downgrade"): {"mult": 0.90, "se": 0.03, "n": 300, "per": {1: 0.89, 2: 0.90, 3: 0.92, 4: 0.90}}}
    assert F.shipped(fake) == {("b", "WR", "downgrade"): 0.90}, "one season carrying it is not an effect"


def test_game_cards_and_ask_say_it():
    src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    body = src[src.index("def _game_bets("):src.index("def price_props(")]
    assert 'd["qb_cards"] = [_qb_card(ch) for ch in chs.values()]' in body
    from engine import askbot as A
    card = Q.card(Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT")])["HOU"])
    row = A.compact({"player": "Nico Collins", "team": "HOU", "qb_card": card})
    assert row["qb_change"].startswith("C.J. Stroud (OUT) — Davis Mills starts. Davis Mills has thrown for 5.3")
    board = {"qb_changes": [card], "games": [{"home": "HOU", "away": "TEN"}]}
    assert A.game_facts(board, {"home": "HOU", "away": "TEN"})["starting_qb_out"][0].startswith("C.J. Stroud (OUT)")
    assert "starting_qb_out" not in A.game_facts(board, {"home": "KC", "away": "DEN"})
    assert A.board_summary(board)["starting_qb_out"][0].startswith("C.J. Stroud")
    assert "say who is out and who starts" in " ".join(A.SYSTEM.split())
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "report=carry_report, qb_backups=True, games=games)" in build and 'result["qb_changes"] = ' in build


def test_the_card_draws_under_the_pick():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    esc = app[app.index("function escapeHtml("):]
    esc = esc[:esc.index("\n}\n") + 2]
    fn = app[app.index("function qbCardHTML("):]
    fn = fn[:fn.index("\n}\n") + 2]
    card = Q.card(Q.changes(QB, [_inj("C.J. Stroud", "HOU", "OUT")])["HOU"], 0.897)
    prog = esc + fn + f"\nconsole.log(JSON.stringify([qbCardHTML({json.dumps(card)}), qbCardHTML(null)]));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    html, none = json.loads(out.stdout)
    assert none == "" and "QB change" in html and "C.J. Stroud (OUT) — Davis Mills starts" in html
    assert "receivers lost 10%" in html
    for place in ("${qbCardHTML(r.qb_card)}${mateCardHTML(r.mate_card)}${matchupCardHTML(r)}", "(r.qb_cards || []).map(qbCardHTML)",
                  "const mu = qbCardHTML(r.qb_card) + mateCardHTML(r.mate_card) + matchupCardHTML("):
        assert place in app, place


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
