"""Matchup picks: every game, offence against defence, into its touchdowns
and its yards-and-catches bets.

Ethan, 2026-09-26, after listing the other AI's winners (Gibbs, St. Brown
and Olave against New Orleans; LaPorta, Knox, Kincaid, Allen and Cook in
Lions–Bills; Adams 5 catches; Kyren Williams 60 and 60; the Stevenson
under) — none of them in our journal, on any board: "build a matchup
touchdown pick section for every game ... and I also like the idea of
doing the yardage and reception picks the same way." engine/matchpicks:
quarterbacks count, no edge bar, no 55% floor, no slate cap; the chance
shown is the model's; journaled on paper.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import matchpicks as M                                   # noqa: E402

GAME = {"home": "DET", "away": "BUF", "kickoff": "2026-09-27T17:00:00Z", "date": "2026-09-27",
        "scan": {"units": {"DET": {"def": {"passing": {"rank": 28}, "rushing": {"rank": 24}}},
                           "BUF": {"def": {"passing": {"rank": 12}, "rushing": {"rank": 30}}}},
                 "redzone": {"BUF": {"off": 11.0, "off_rel": 0.25, "def": 8.0, "def_rel": -0.1},
                             "DET": {"off": 12.0, "off_rel": 0.35, "def": 10.5, "def_rel": 0.18}}}}


def _td(player, team, pos, prob, rz=1.6, implied=26.0, **kw):
    opp = "DET" if team == "BUF" else "BUF"
    return {"player": player, "team": team, "opponent": opp, "position": pos, "model_prob": prob,
            "odds": 120, "book": "DraftKings", "implied_total": implied, "rz_chances": rz, **kw}


WATCH = [
    _td("Josh Allen", "BUF", "QB", 0.47),
    _td("James Cook", "BUF", "RB", 0.52),
    _td("Dalton Kincaid", "BUF", "TE", 0.33),
    _td("Dawson Knox", "BUF", "TE", 0.29),
    _td("Khalil Shakir", "BUF", "WR", 0.31, injury_status="Questionable"),
    _td("Jahmyr Gibbs", "DET", "RB", 0.55),
    _td("Sam LaPorta", "DET", "TE", 0.36),
    _td("Deep Backup", "DET", "WR", 0.12),
    _td("Other Game", "KC", "WR", 0.60),
]


def test_touchdowns_game_by_game_with_quarterbacks():
    got = M.td_picks(GAME, WATCH, reads=[])
    names = [r["player"] for r in got]
    assert names == ["Jahmyr Gibbs", "James Cook", "Josh Allen", "Sam LaPorta"], names
    assert len(got) == M.TD_PER_GAME == 4
    allen = got[2]
    assert allen["position"] == "QB" and "run defence" in " ".join(allen["matchup_lines"])
    assert all(r["market"] == "anytime_td" and r["side"] == "YES" and r["line"] == 0.5 for r in got)
    assert "Khalil Shakir" not in names, "anyone on the injury report is left off"
    assert "Deep Backup" not in names and "Other Game" not in names


def test_a_strong_chance_needs_no_matchup_and_a_weak_one_needs_the_case():
    soft = dict(GAME, scan={"units": {}, "redzone": {}})
    weak = [_td("Plain Receiver", "BUF", "WR", 0.34, rz=0.2, implied=17.0),
            _td("Goal Line Back", "BUF", "RB", 0.50, rz=0.2, implied=17.0)]
    got = [r["player"] for r in M.td_picks(soft, weak, reads=[])]
    assert got == ["Goal Line Back"], got


def test_the_team_cap_and_pulled_players():
    watch = [_td(f"P{i}", "BUF", "WR", 0.5 - i * 0.02) for i in range(5)]
    got = M.td_picks(GAME, watch, reads=[], pulled=["P0"])
    assert [r["player"] for r in got] == ["P1", "P2", "P3"], "three a side, and a pulled player is out"


def _prop(player, market, side, line, hp, odds=-110, **kw):
    lines = kw.pop("all_lines", [{"book": "FanDuel", "line": line, "over_odds": odds, "under_odds": odds}])
    return {"player": player, "team": kw.pop("team", "BUF"), "opponent": kw.pop("opponent", "DET"),
            "market": market, "market_label": market, "side": side, "line": line, "hit_prob": hp,
            "odds": odds, "book": "FanDuel", "all_lines": lines, **kw}


def test_yards_and_catches_follow_the_read_where_our_number_agrees():
    reads = [
        {"player": "Davante Adams", "team": "BUF", "opp": "DET", "read": "good", "label": "Good matchup",
         "lean": ["receptions", "rec_yds"], "pro": ["DET allows the 4th-most catches to receivers"],
         "usage": {"targets_pg": 8.0}},
        {"player": "Rhamondre Stevenson", "team": "DET", "opp": "BUF", "read": "tough",
         "label": "Tough matchup", "lean": ["rush_yds"], "con": ["BUF's run defence ranks 3rd"],
         "usage": {"carries_pg": 13.0}},
        {"player": "Coin Flip", "team": "BUF", "opp": "DET", "read": "good", "lean": ["rec_yds"],
         "usage": {"targets_pg": 5.0}},
    ]
    props = [
        _prop("Davante Adams", "receptions", "OVER", 4.5, 0.62),
        _prop("Davante Adams", "rec_yds", "OVER", 60.5, 0.57),
        # The model's chosen side is the over at 40%, so the under is 60% —
        # priced from the books at that line, the exchange only when close.
        _prop("Rhamondre Stevenson", "rush_yds", "OVER", 47.5, 0.40, team="DET", opponent="BUF",
              all_lines=[{"book": "Novig", "line": 47.5, "over_odds": -105, "under_odds": 105},
                         {"book": "DraftKings", "line": 47.5, "over_odds": -115, "under_odds": -115}]),
        _prop("Coin Flip", "rec_yds", "OVER", 30.5, 0.52),
    ]
    got = M.prop_picks(GAME, reads, props)
    by = {(r["player"], r["market"]): r for r in got}
    assert set(by) == {("Davante Adams", "receptions"), ("Davante Adams", "rec_yds"),
                       ("Rhamondre Stevenson", "rush_yds")}, by
    st = by[("Rhamondre Stevenson", "rush_yds")]
    assert st["side"] == "UNDER" and abs(st["model_prob"] - 0.60) < 1e-9
    assert (st["odds"], st["book"]) == (-115, "DraftKings"), "Novig +105 against -115 is not close"
    assert by[("Davante Adams", "receptions")]["matchup_lines"] == ["DET allows the 4th-most catches to receivers"]


def test_no_proxy_line_no_exchange_rung_no_heavy_juice_no_fringe_role():
    """The box's first run, 2026-09-26: eight of eighteen picks priced at the
    model's own "proxy" line, Terrance Ferguson under 49.5 at -380 on
    ProphetX alone, Brady Russell under 5 rushing yards."""
    def read(name, mk, **u):
        return {"player": name, "team": "BUF", "opp": "DET", "read": "tough", "lean": [mk], "usage": u}
    reads = [read("Proxy Guy", "rec_yds", targets_pg=5.0), read("Rung Guy", "rec_yds", targets_pg=5.0),
             read("Juice Guy", "receptions", targets_pg=5.0), read("Brady Russell", "rush_yds", carries_pg=1.5),
             read("No Usage", "rec_yds"), read("Real Guy", "rec_yds", targets_pg=6.0)]
    props = [
        _prop("Proxy Guy", "rec_yds", "UNDER", 14.0, 0.62,
              all_lines=[{"book": "proxy", "line": 14.0, "over_odds": -110, "under_odds": -110}]),
        _prop("Rung Guy", "rec_yds", "OVER", 49.5, 0.32,
              all_lines=[{"book": "ProphetX", "line": 49.5, "over_odds": 290, "under_odds": -380}]),
        _prop("Juice Guy", "receptions", "UNDER", 2.5, 0.75,
              all_lines=[{"book": "DraftKings", "line": 2.5, "over_odds": 230, "under_odds": -300}]),
        _prop("Brady Russell", "rush_yds", "UNDER", 5.5, 0.70),
        _prop("No Usage", "rec_yds", "UNDER", 20.5, 0.70),
        _prop("Real Guy", "rec_yds", "UNDER", 38.5, 0.60),
    ]
    got = [r["player"] for r in M.prop_picks(GAME, reads, props)]
    assert got == ["Real Guy"], got


def test_build_and_the_journal_rows():
    reads = {"BUF@DET": {"players": []}}
    # The live scorer rows carry no position: build takes it from the prop
    # rows, so Josh Allen still reads as a quarterback.
    bare = [{k: v for k, v in r.items() if k != "position"} for r in WATCH]
    board = M.build([GAME, {"home": "KC", "away": "LV"}], reads, bare,
                    [{"player": "Josh Allen", "position": "QB", "market": "pass_yds"}])
    assert [b["game"] for b in board] == ["BUF@DET"]
    allen = [r for r in board[0]["td"] if r["player"] == "Josh Allen"][0]
    assert allen["position"] == "QB" and "(he scores on the ground)" in " ".join(allen["matchup_lines"])
    assert all(r["game"] == "BUF@DET" for r in board[0]["td"])
    assert len(M.journal_rows(board, "td")) == 4 and M.journal_rows(board, "prop") == []


def test_it_is_published_paywalled_journaled_and_drawn():
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert '"matchup_picks": _matchups,' in pipe
    assert "_match_picks(_games, _partial.get(\"scan_reads\") or {}, ls_watch, results)" in pipe
    from engine import gate
    assert "matchup_picks" in gate.PAID_KEYS
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert '("td", "matchup_td", "Matchup"), ("prop", "matchup_prop", "Matchup")' in build
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "${matchupPicksHTML()}${tdScenariosHTML()}" in js
    assert '["gp-sec-matchup", `Matchup picks · ${matchupPickCount(g)}`]' in js
    assert "${gpMatchupHTML(g)}" in js


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
