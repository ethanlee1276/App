"""The MLB matchup scan: who could shine, who could struggle, breakouts.

Ethan, 2026-09-26: "move on to MLB. We need to get the who's going to
struggle and who's going to do good and best candidates ... breakout
candidates and good matchups for all the players and pitchers ... which
batters do good against what pitchers and left hand and right hand ... all
the work we did for NFL and college football ... move that to MLB."

engine/mlb/scan reads what the MLB model already priced — each hitter's own
platoon split, the starter's slugging allowed to his side, the expected-
stats gap and barrels, lineup slot, park by hand, wind, pens; for a starter
the lineup's strikeout rate, his own, his CSW, the umpire, the park — into a
tale of the tape per game and a read per player in the football reads' own
shape. The reads feed Most Likely's leans, the one board's matchup check
and every game's matchup picks, as the NFL's do. They never move a number.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.mlb import scan as SC                              # noqa: E402
from engine.mlb.models import (MLBGame, MLBProp, MLBWeather,  # noqa: E402
                               Pitcher, StatcastProfile)
from engine.mlb.data_loader import MLBSlate                    # noqa: E402
from engine import likelyboard as LB                          # noqa: E402
from engine import matchpicks as MP                           # noqa: E402

BUILD = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()


def _game():
    g = MLBGame(home="NYY", away="BOS", park="yankee",
                weather=MLBWeather(wind_mph=12, wind_dir_rel="out"))
    g.pitchers = {"NYY": Pitcher(name="Gerrit Cole", throws="R", slg_allowed_vs_l=0.480,
                                 slg_allowed_vs_r=0.330, k_rate=0.29, xera=3.10),
                  "BOS": Pitcher(name="Soft Tosser", throws="L", slg_allowed_vs_l=0.380,
                                 slg_allowed_vs_r=0.500, k_rate=0.18, xera=5.10)}
    g.team_k_rate = {"BOS": 0.26, "NYY": 0.20}
    g.bullpen_fatigue = {"BOS": 7.0}
    return g


def _prop(player, team, opp, pos, market, **kw):
    return MLBProp(player=player, team=team, opponent=opp, position=pos, market=market,
                   logs=[], career_avg=1.0, vs_pitcher_avg=kw.pop("bvp", None), lines=[], **kw)


def _slate():
    g = _game()
    props = [
        _prop("Lefty Masher", "BOS", "NYY", "RF", "total_bases", bats="L", lineup_spot=2,
              platoon_factor=1.08, platoon_note="Hits righties 18% better than his average",
              statcast=StatcastProfile(xslg=0.520, slg=0.450, barrel_pct=0.14), bvp=1.4),
        _prop("Righty Victim", "BOS", "NYY", "C", "hits", bats="R", lineup_spot=9,
              platoon_factor=0.93, statcast=StatcastProfile(xslg=0.330, slg=0.410)),
        _prop("Gerrit Cole", "NYY", "BOS", "SP", "strikeouts", throws="R",
              statcast=StatcastProfile(csw_pct=0.315)),
    ]
    return MLBSlate(date="2026-09-26", games=[g], props=props)


def test_every_hitter_and_starter_gets_a_read_in_the_football_shape():
    got = SC.scan(_slate())
    reads = {x["player"]: x for x in got["reads"]["BOS@NYY"]["players"]}
    m = reads["Lefty Masher"]
    assert m["read"] == "breakout" and m["label"] == "Breakout candidate", m
    assert "Hits righties 18% better than his average" in m["pro"]
    assert "Gerrit Cole allows a .480 SLG to lefties" in m["pro"], "the starter's split by hand"
    assert any("xSLG .520 vs SLG .450" in t for t in m["pro"]), "the expected-stats gap"
    assert "home_runs" in m["lean"], "barrels and a boost park lean to power"
    assert any("Career against Gerrit Cole" in t for t in m["notes"]), "batter vs pitcher: shown, never counted"
    v = reads["Righty Victim"]
    assert v["read"] in ("tough", "avoid"), v
    assert "Gerrit Cole holds righties to a .330 SLG" in v["con"]
    c = reads["Gerrit Cole"]
    assert c["pos"] == "SP" and c["read"] in ("good", "breakout") and c["lean"] == ["strikeouts", "outs"]
    assert any("BOS strikes out 26.0%" in t for t in c["pro"])
    tape = got["tapes"]["BOS@NYY"]
    assert tape["sides"]["NYY"]["starter"]["name"] == "Gerrit Cole" and tape["sides"]["BOS"]["k_rate"] == 0.26


def test_the_reads_reach_most_likely_the_board_and_the_matchup_picks():
    for bit in ("_ms = _mscan.scan(slate, _ars)", 'result["scan_reads"] = _ms["reads"]',
                "leans=_mlb_leans, lean_report=_mlb_lean_report)",
                '_stamp_mlb(result["scan_reads"], _mlb_lean_report, board=result["most_likely"])',
                'sport="mlb")', 'category="matchup_prop", grade_label="Matchup")'):
        assert bit in BUILD, bit
    assert LB.MATCHUP_SOURCE["mlb"] == "scan+model"
    reads = SC.scan(_slate())["reads"]
    ml = [{"player": "Lefty Masher", "team": "BOS", "market": "total_bases", "side": "over", "line": 1.5,
           "model_prob": 0.62, "odds": -150, "kind": "prop"},
          {"player": "Nobody", "team": "BOS", "market": "hits", "side": "over", "line": 0.5,
           "model_prob": 0.66, "odds": -190, "kind": "prop"}]
    board = LB.build({"games": [], "scan_reads": reads, "most_likely": ml, "recommendations": []},
                     record={}, sport="mlb")
    by = {r["player"]: r for r in board["rows"]}
    assert by["Lefty Masher"]["checks"]["matchup"] is True, by["Lefty Masher"]["check_notes"]
    assert by["Nobody"]["checks"]["matchup"] is None, "no read, no model step: can't say"
    recs = [{"player": "Lefty Masher", "team": "BOS", "opponent": "NYY", "market": "total_bases", "side": "over",
             "line": 1.5, "hit_prob": 0.61, "all_lines": [{"book": "DraftKings", "line": 1.5, "over_odds": -140}]},
            {"player": "Gerrit Cole", "team": "NYY", "opponent": "BOS", "market": "strikeouts", "side": "over",
             "line": 6.5, "hit_prob": 0.58, "all_lines": [{"book": "FanDuel", "line": 6.5, "over_odds": -120}]}]
    picks = MP.build([{"home": "NYY", "away": "BOS"}], reads, [], recs, sport="mlb")
    got = {(p["player"], p["market"]) for m in picks for p in m["props"]}
    assert ("Lefty Masher", "total_bases") in got and ("Gerrit Cole", "strikeouts") in got
    assert all(not m["td"] for m in picks)


def test_the_game_page_draws_the_tape_and_the_reads():
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    fn = js[js.index("function mlbScanHTML(g) {"):]
    fn = fn[:fn.index("\nfunction ", 10)]
    for bit in ("Slugging allowed: lefties ${slg(sp.slg_vs_l)} · righties ${slg(sp.slg_vs_r)}",
                "Facing a lineup that strikes out ${pct(lineK)}", "${players.map(scanReadHTML).join(\"\")}",
                'id="gp-sec-scan"'):
        assert bit in fn, bit
    assert "${matchupScanHTML(g) || mlbScanHTML(g)}" in js
    assert '(g.scan && g.scan.units) || g.mlb_tape ? ["gp-sec-scan", "Matchup scan"] : null,' in js
    assert 'Also noticed — not counted${state.sport === "mlb" ? "" : ", no lift when tested"}' in js, \
        "baseball's noticed items were never tested; the page must not say they were"
    assert ".mlb-tape { display: grid;" in css
    src = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()
    assert '_gd["mlb_tape"] = _t' in src


def test_pitch_type_matchups_and_the_lineup_against_his_hand():
    """Ethan, 2026-09-26: "which batters do good against what pitchers and left
    hand and right hand ... what tools and data we need". The hitter half is
    Savant's pitch-arsenal board (whiff rate by pitch type); the pitcher half
    is his mix over his last starts, off the playByPlay the build already
    caches for velocity. arsenal.matchup re-weights the hitter by tonight's
    mix; the difference from his usual is the read."""
    sl = _slate()
    ars = {"season": 2026, "mix": {"NYY": {"pitcher": "Gerrit Cole", "shares": {"FF": 0.45, "SL": 0.35, "CH": 0.20}}},
           "batters": {"lefty masher": {"FF": {"pa": 120, "whiff_pct": 0.15, "usage": 0.5, "est_woba": 0.40},
                                        "SL": {"pa": 60, "whiff_pct": 0.18, "usage": 0.2, "est_woba": 0.36},
                                        "CH": {"pa": 50, "whiff_pct": 0.20, "usage": 0.1, "est_woba": 0.33},
                                        "CU": {"pa": 40, "whiff_pct": 0.45, "usage": 0.2, "est_woba": 0.25}}}}
    got = SC.scan(sl, ars)
    m = {x["player"]: x for x in got["reads"]["BOS@NYY"]["players"]}["Lefty Masher"]
    line = next(t for t in m["pro"] if t.startswith("Sees the ball well"))
    assert "four-seamers 45%, sliders 35%, changeups 20%" in line and "his usual" in line, line
    assert got["tapes"]["BOS@NYY"]["sides"]["NYY"]["mix"] == "four-seamers 45%, sliders 35%, changeups 20%"
    # The lineup against a hand needs four measured bats.
    props = [_prop(f"H{i}", "BOS", "NYY", "LF", "hits", bats="L", platoon_factor=1.06) for i in range(4)]
    assert SC.lineup_vs_hand(props, "BOS", "R") == {"hand": "R", "factor": 1.06, "hitters": 4}
    assert SC.lineup_vs_hand(props[:3], "BOS", "R") is None
    for bit in ("_ars = _mscan.arsenal_context(slate, int(args.date[:4]))", "_ms = _mscan.scan(slate, _ars)"):
        assert bit in BUILD, bit
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "Throws ${escapeHtml(s.mix)}" in js and "hitters measured)" in js


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
