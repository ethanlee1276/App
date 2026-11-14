"""College football on the NFL's level: the matchup work, for college.

Ethan, 2026-09-26: "all this work we've done for NFL with the offense and
defense and the good matchup and bad matchup and who will struggle and who
won't ... we need to make sure all of that work ... has also been done for
college football because we want college football and NFL to be on the
same level."

What the NFL had and college did not, and what college now has:
  * reads with the player's usage (college logs catches, not targets, so
    the receiving share is said as catches — never passed off as targets);
  * every read's touchdown chance and price (stamp_touchdowns);
  * red-zone trips, as college's scoring chances (drives to the 40) had and
    allowed, from CFBD's advanced table (gamescan.cfb_chances);
  * the touchdown matchup of 8 and the scenarios, with a college defence's
    rank read as it would sit among 32 (tdscenarios.rank32);
  * the per-game matchup picks and the touchdown scenarios, built, pooled
    into the one Most Likely board and journaled on paper.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                               # noqa: E402
from engine import tdscenarios as TS                           # noqa: E402
from engine import matchpicks as MP                            # noqa: E402
from engine import likelyboard as LB                           # noqa: E402
from engine.sources import cfbd                                 # noqa: E402

BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()


def _row(team, plays, ppa, opps_off, opps_def, havoc=0.15):
    side = lambda p, opps: {                                    # noqa: E731
        "plays": plays, "ppa": p, "successRate": 0.42, "explosiveness": 1.2,
        "lineYards": 3.0, "stuffRate": 0.18, "havoc": {"total": havoc},
        "passingPlays": {"ppa": p}, "rushingPlays": {"ppa": p},
        "totalOpportunies": opps, "pointsPerOpportunity": 4.1}
    return {"team": team, "offense": side(ppa, opps_off), "defense": side(-ppa, opps_def)}


def test_the_scoring_chances_parse_and_rate_against_the_league():
    got = cfbd.parse_advanced([_row("Georgia", 700, 0.3, 60, 30)])
    ch = got["Georgia"]["chances"]
    assert ch["off"] == {"opps": 60.0, "ppo": 4.1, "plays": 700.0} and ch["def"]["opps"] == 30.0
    assert set(got["Georgia"]["off"]) == set(G.CFB_UNITS), "the units are untouched"
    # The other spelling is read too, should CFBD ever fix it.
    alt = _row("X", 700, 0.1, 0, 0)
    alt["offense"].pop("totalOpportunies"); alt["offense"]["totalOpportunities"] = 50
    assert cfbd.parse_advanced([alt])["X"]["chances"]["off"]["opps"] == 50.0
    cur = cfbd.parse_advanced([_row("A", 700, 0.3, 60, 30), _row("B", 700, 0.0, 40, 50)])
    rz = G.cfb_chances(cur)
    assert rz["A"]["off"] == 6.0 and rz["B"]["off"] == 4.0, "per game: 700 plays is ten games"
    assert rz["A"]["off_rel"] == 0.2 and rz["B"]["off_rel"] == -0.2
    assert rz["A"]["def_rel"] == -0.25 and rz["B"]["def_rel"] == 0.25
    assert rz["A"]["what"] == "scoring chances"


def test_college_usage_says_catches_not_targets(monkeypatch=None):
    import engine.cfb.tds as T
    real = T.merged_usage
    T.merged_usage = lambda conn, season: (2026, {"UGA": {
        "a": {"player": "Ace Back", "carries": 18.0, "receptions": 1.0, "rush_yds": 90.0, "rec_yds": 8.0,
              "games": 4, "position": "RB"},
        "b": {"player": "Wide Out", "carries": 0.0, "receptions": 6.0, "rush_yds": 0.0, "rec_yds": 80.0,
              "games": 4, "position": "WR"},
        "c": {"player": "Other Back", "carries": 6.0, "receptions": 1.0, "rush_yds": 20.0, "rec_yds": 5.0,
              "games": 4, "position": "RB"}}}, {})
    try:
        u = G.cfb_usage(None, 2026)
    finally:
        T.merged_usage = real
    wr = u[("UGA", G._key("Wide Out"))]
    assert wr["share_of"] == "catches" and wr["tgt_share"] == 0.75 and wr["rec_pg"] == 6.0
    assert "targets_pg" not in wr, "no targets are invented"
    rb = u[("UGA", G._key("Ace Back"))]
    assert rb["carry_share"] == 0.75 and rb["carries_pg"] == 18.0 and rb["position"] == "RB"


def _cfb_board(n_other=60):
    teams = [_row("Georgia", 700, 0.35, 70, 25), _row("Tennessee", 700, -0.2, 35, 65)]
    teams += [_row(f"T{i}", 700, 0.2 - i * 0.006, 50, 50) for i in range(n_other)]
    keys = {"Georgia": "UGA", "Tennessee": "TENN", **{f"T{i}": f"T{i}" for i in range(n_other)}}
    out = {"games": [{"home": "TENN", "away": "UGA"}],
           "recommendations": [{"player": "Wide Out", "team": "UGA", "opponent": "TENN", "position": "WR",
                                "market": "rec_yds", "line": 60.5, "hit_prob": 0.6}]}
    usage = {("UGA", G._key("Wide Out")): {"name": "Wide Out", "position": "WR", "games": 4, "tgt_share": 0.3,
                                          "share_of": "catches", "rec_pg": 6.0, "rec_yds_pg": 80.0}}
    watch = [{"player": "Wide Out", "team": "UGA", "opponent": "TENN", "model_prob": 0.41, "odds": 150,
              "book": "DraftKings", "implied_total": 34.5, "rz_chances": 1.6, "position": "WR"}]
    n = G.attach_cfb(out, 2026, lambda s: keys.get(s), fetch=lambda year: cfbd.parse_advanced(teams) if year == 2026 else {},
                     usage=usage, watch=watch)
    return n, out


def test_the_college_scan_carries_what_the_nfl_scan_carries():
    n, out = _cfb_board()
    assert n == 1
    scan = out["games"][0]["scan"]
    assert scan["n_teams"] == 62
    assert scan["redzone"]["UGA"]["off_rel"] > 0 and scan["redzone"]["TENN"]["def_rel"] > 0
    read = next(x for x in out["scan_reads"]["UGA@TENN"]["players"] if x["player"] == "Wide Out")
    assert read["td"]["model_prob"] == 0.41 and read["td"]["rz_chances"] == 1.6, "every read's TD chance"
    assert read["usage"]["share_of"] == "catches"
    assert any("of the catches" in t for t in read["pro"] + read["con"] + read["notes"]), read
    assert not any("targets" in t for t in read["pro"] + read["con"]), "never targets college doesn't log"


def test_a_college_defence_rank_reads_as_among_32():
    assert TS.rank32(100, 128) == 25.0 and TS.rank32(26, 32) == 26.0 and TS.rank32(None, 128) is None
    m = MP.td_matchup({"position": "WR", "implied_total": 34.5, "rz_chances": 1.6, "team": "UGA",
                       "opponent": "TENN"},
                      {"def": {"passing": {"rank": 120}}}, {"off": 7.0, "off_rel": 0.2, "what": "scoring chances"},
                      {"def": 6.5, "def_rel": 0.18, "what": "scoring chances"}, n_teams=128,
                      usage={"tgt_share": 0.3, "share_of": "catches"})
    assert m["points"]["defense"] == 2, "120th of 128 is a soft defence, not 120th of 32"
    assert m["points"]["trips"] == 2 and m["score"] >= 6
    assert any("scoring chances (drives to the 40)" in t for t in m["lines"])
    assert any("of the catches" in t for t in m["lines"])


def test_college_scenarios_and_matchup_picks_are_built_pooled_and_journaled():
    n, out = _cfb_board()
    sc = TS.build({"games": out["games"], "scan_reads": out["scan_reads"], "most_likely": []})
    assert [r["player"] for r in sc] == ["Wide Out"], sc
    assert any("of 62" in t for t in sc[0]["scenario_lines"]), "the rank is out of the college league's size"
    for bit in ('out["td_scenarios"] = _td_scen(', 'out["matchup_picks"] = _mp_build(',
                'category="td_scenario", grade_label="Scenario")',
                'for _kind, _cat in (("td", "matchup_td"), ("prop", "matchup_prop")):',
                "usage=_cfb_use, watch=watch, injuries=_cfb_inj)", "_scan.cfb_usage(conn, "):
        assert bit in BUILD, bit
    # The one board reads a college scorer's touchdown matchup off the scan.
    out["most_likely"] = [{"player": "Wide Out", "team": "UGA", "opponent": "TENN", "kind": "td",
                           "market": "anytime_td", "side": "YES", "line": 0.5, "model_prob": 0.46,
                           "odds": 120, "position": "WR", "implied_total": 34.5, "rz_chances": 1.6}]
    board = LB.build(out, record={}, sport="cfb")
    row = board["rows"][0]
    assert row["checks"]["matchup"] is True, row["check_notes"]
    assert row["matchup_score"] >= LB.TD_CASE


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
