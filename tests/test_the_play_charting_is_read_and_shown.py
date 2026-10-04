"""FTN's play charting: read off nflverse, joined to the play-by-play, measured
first, and shown on the scan as what was noticed — never counted.

Ethan, 2026-09-28: "what else can we add that's free". engine/sources/ftn
reads the charting the site had called paid; chartfit.py is the
information test (nothing cleared); the scan's coverage card carries this
season's blitz and box, and the reads carry the charted and tracked
lines as notes. Offline, on fixture plays.

Run directly: `python3 tests/test_the_play_charting_is_read_and_shown.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import ftn as F                            # noqa: E402
from engine.sources import ngs as NGS                          # noqa: E402
from engine import gamescan as G                               # noqa: E402


def _chart(game, play, week, **flags):
    row = {"nflverse_game_id": game, "nflverse_play_id": str(play), "week": str(week),
           "n_blitzers": "0", "n_pass_rushers": "4", "n_defense_box": "7"}
    for k in ("is_play_action", "is_screen_pass", "is_rpo", "is_motion", "is_no_huddle",
              "is_qb_out_of_pocket", "is_interception_worthy", "is_throw_away", "is_catchable_ball",
              "is_contested_ball", "is_created_reception", "is_drop", "is_qb_fault_sack"):
        row[k] = "FALSE"
    row.update({k: (str(v).upper() if isinstance(v, bool) else str(v)) for k, v in flags.items()})
    return row


def _play(game, play, week, posteam, defteam, kind, **who):
    row = {"game_id": game, "play_id": f"{play}.0", "week": str(week), "posteam": posteam, "defteam": defteam,
           "play_type": kind, "pass_attempt": "1" if kind == "pass" else "0",
           "rush_attempt": "1" if kind == "run" else "0", "qb_dropback": "1" if kind == "pass" else "0",
           "qb_scramble": "0", "sack": "0", "interception": "0", "complete_pass": "0",
           "passer_player_id": "", "passer_player_name": "", "receiver_player_id": "",
           "receiver_player_name": "", "rusher_player_id": "", "rusher_player_name": ""}
    row.update(who)
    return row


def _fixture():
    g = "2026_01_CHI_PHI"
    charted, plays = [], []
    # Ten PHI dropbacks against CHI: four blitzed, one interception-worthy,
    # eight catchable of which Smith dropped one; three PHI runs into a
    # stacked box, one into a light one.
    for i in range(10):
        charted.append(_chart(g, i + 1, 1, n_pass_rushers=5 if i < 4 else 4, n_blitzers=1 if i < 4 else 0,
                              is_interception_worthy=(i == 0), is_catchable_ball=(i < 8),
                              is_drop=(i == 1), is_contested_ball=(i == 2), is_play_action=(i < 3)))
        plays.append(_play(g, i + 1, 1, "PHI", "CHI", "pass", passer_player_id="00-H", passer_player_name="J.Hurts",
                           receiver_player_id="00-S", receiver_player_name="D.Smith"))
    for i in range(4):
        charted.append(_chart(g, 20 + i, 1, n_defense_box=8 if i < 3 else 5))
        plays.append(_play(g, 20 + i, 1, "PHI", "CHI", "run", rusher_player_id="00-B", rusher_player_name="S.Barkley"))
    # A kickoff neither side's tables count, and a charted play the
    # play-by-play does not carry.
    charted.append(_chart(g, 99, 1))
    plays.append(_play(g, 99, 1, "CHI", "PHI", "kickoff"))
    charted.append(_chart(g, 500, 1))
    return charted, plays


def test_the_join_is_by_game_and_play_and_the_tables_count_what_the_charting_says():
    charted, plays = _fixture()
    rows = F.joined(2026, charted=charted, plays=plays)
    assert len(rows) == 15, "every charted play the play-by-play carries, once"
    d = F.defense_weeks(rows, 2026)["CHI"]
    assert d == [(2026, 1, {"dropbacks": 10, "blitz": 4, "blitzers": 4, "runs": 4, "heavy_box": 3, "light_box": 1})]
    o = F.offense_weeks(rows, 2026)["PHI"][0][2]
    assert o["dropbacks"] == 10 and o["play_action"] == 3 and o["attempts"] == 10 and o["catchable"] == 8 and o["iw"] == 1
    q = F.qb_weeks(rows, 2026)["00-H"][0][2]
    assert q["attempts"] == 10 and q["iw"] == 1 and q["catchable"] == 8 and q["name"] == "J.Hurts" and q["team"] == "PHI"
    r = F.receiver_weeks(rows, 2026)["00-S"][0][2]
    assert r == {"targets": 10, "catchable": 8, "drops": 1, "contested": 1, "created": 0, "name": "D.Smith", "team": "PHI"}


def test_a_pooled_prior_weighs_a_week_by_its_volume_and_needs_the_minimum():
    hist = [(2025, 17, {"drops": 0, "catchable": 2}), (2026, 1, {"drops": 3, "catchable": 10}),
            (2026, 2, {"drops": 0, "catchable": 8})]
    assert F.rate_prior(hist, 2026, 2, "drops", "catchable") == 3 / 12, "the weeks before week 2, pooled"
    assert F.rate_prior(hist, 2026, 2, "drops", "catchable", min_den=15) is None
    assert F.rate_prior(hist, 2026, 3, "drops", "catchable", n=1) == 0.0, "the last one week only"


def test_the_season_tables_carry_counts_by_name_and_shares_as_rates():
    charted, plays = _fixture()
    rows = F.joined(2026, charted=charted, plays=plays)
    F_MIN = (F.MIN_DROPBACKS, F.MIN_RUNS, F.MIN_ATTEMPTS, F.MIN_TARGETS)
    try:
        F.MIN_DROPBACKS, F.MIN_RUNS, F.MIN_ATTEMPTS, F.MIN_TARGETS = 1, 1, 1, 1
        t = F.season_tables(2026, rows=rows)
    finally:
        F.MIN_DROPBACKS, F.MIN_RUNS, F.MIN_ATTEMPTS, F.MIN_TARGETS = F_MIN
    chi = t["defense"]["CHI"]
    assert chi["blitz"] == 4 and chi["blitz_rate"] == 0.4 and chi["heavy_box_rate"] == 0.75 and chi["light_box_rate"] == 0.25
    assert t["offense"]["PHI"]["play_action_rate"] == 0.3
    assert t["qbs"][("PHI", "J.Hurts")]["iw"] == 1 and t["qbs"][("PHI", "J.Hurts")]["iw_rate"] == 0.1
    smith = t["receivers"][("PHI", "D.Smith")]
    assert smith["catchable"] == 8 and smith["drops"] == 1 and smith["drops_rate"] == 0.125
    assert t["weeks"] == 0 and t["partial"] == 1, "fifteen plays is a week still being charted"


def test_the_reads_quote_the_charting_and_the_tracking_as_notes():
    smith = {"catchable": 13, "drops": 0, "drops_rate": 0.0, "contested_rate": 0.105}
    chi = {"blitz_rate": 0.388, "heavy_box_rate": 0.217, "light_box_rate": 0.348}
    track = {"avg_separation": 2.67, "avg_separation_rank": 44, "n_ranked": 67, "avg_cushion": 4.98,
             "avg_yac_above_expectation": 0.02}
    lines = G.charting_notes("wr", "CHI", smith, chi, track)
    assert lines[0] == "Charted: 0 drops on 13 catchable balls this season (0%), 10% of his targets contested"
    assert lines[1].startswith("Tracking: 2.7 yd of separation at the throw (44th of 67 WRs), 5.0 yd of cushion")
    assert lines[2] == "CHI blitzes on 39% of dropbacks this season"
    rb = G.charting_notes("rb", "CHI", None, chi, {"rush_yards_over_expected_per_att": 0.41,
                                                    "rush_yards_over_expected_per_att_rank": 3, "n_ranked": 30,
                                                    "percent_attempts_gte_eight_defenders": 21.4})
    assert rb[0].startswith("Tracking: +0.41 rushing yards over expected a carry (3rd of 30 RBs), sees 8+ in the box on 21%")
    assert rb[1] == "CHI stacks the box (8+) on 22% of runs this season, light boxes (6 or fewer) on 35%"
    qb = G.charting_notes("qb", "CHI", {"attempts": 62, "iw": 1, "iw_rate": 0.016, "catchable_rate": 0.694,
                                        "play_action_rate": 0.191}, chi, None)
    assert qb[0] == "Charted: 1 interception-worthy throw on 62 attempts (2%), 69% catchable, play action on 19% of dropbacks"
    assert G.charting_notes("wr", "CHI", None, None, None) == [], "nothing charted, nothing said"
    # A read's notes carry them: the read function threads all three.
    src = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert "notes += charting_notes(group, opp, charting, charting_def, tracking)" in src
    assert "charting=charting, tracking=tracking," in src, "scan_game gets both tables from attach"


def test_the_scan_carries_this_seasons_charting_and_the_page_draws_it():
    src = (ROOT / "engine" / "gamescan.py").read_text(encoding="utf-8")
    assert '"charting": {"season": (charting or {}).get("season")' in src
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    card = js[js.index("function scanCoverageHTML"):js.index("function scanWhyList")]
    assert "const cd = (ch.defense || {})[team];" in card and "const co = (ch.offense || {})[team];" in card
    assert "<b>This season</b> ${nowLine}${when}" in card and "<b>On offense</b> ${offLine}" in card
    assert "pct(cd.blitz_rate)" in card and "pct(co.play_action_rate)" in card
    assert "+ part of week ${ch.partial}" in card, "the week FTN is still charting is named as partial"


def test_next_gen_stats_defence_side_and_season_ranks():
    sched = [{"season": "2026", "week": "1", "home_team": "PHI", "away_team": "CHI"},
             {"season": "2026", "week": "2", "home_team": "LA", "away_team": "PHI"}]
    rows = [{"season": "2026", "week": "1", "team_abbr": "PHI", "player_display_name": "DeVonta Smith",
             "player_position": "WR", "targets": "10", "avg_separation": "3.0", "avg_cushion": "6.0",
             "avg_intended_air_yards": "12", "percent_share_of_intended_air_yards": "40", "avg_yac_above_expectation": "0.5"},
            {"season": "2026", "week": "2", "team_abbr": "PHI", "player_display_name": "DeVonta Smith",
             "player_position": "WR", "targets": "5", "avg_separation": "1.5", "avg_cushion": "3.0",
             "avg_intended_air_yards": "9", "percent_share_of_intended_air_yards": "30", "avg_yac_above_expectation": "-0.5"},
            {"season": "2026", "week": "2", "team_abbr": "LAR", "player_display_name": "Puka Nacua",
             "player_position": "WR", "targets": "12", "avg_separation": "2.0", "avg_cushion": "5.0",
             "avg_intended_air_yards": "8", "percent_share_of_intended_air_yards": "35", "avg_yac_above_expectation": "1.0"}]
    d = NGS.defense_weeks(rows, schedules=sched)
    assert d["CHI"] == [(2026, 1, {"targets": 10.0, "avg_separation_x": 30.0, "avg_cushion_x": 60.0})]
    assert d["LA"] == [(2026, 2, {"targets": 5.0, "avg_separation_x": 7.5, "avg_cushion_x": 15.0})], "the Rams are LA in the schedule"
    assert d["PHI"][0][2]["targets"] == 12.0, "Nacua's week against PHI, LAR read as LA"
    t = NGS.season_tables(2026, rows_by_kind={"receiving": rows, "rushing": [], "passing": []})
    smith = t["receivers"][("PHI", "DeVonta Smith")]
    assert smith["avg_separation"] == 2.5 and smith["targets"] == 15, "target-weighted: (3.0·10 + 1.5·5) / 15"
    assert smith["avg_separation_rank"] == 1 and t["receivers"][("LA", "Puka Nacua")]["avg_separation_rank"] == 2
    assert smith["n_ranked"] == 2


def test_the_harness_ships_nothing_on_its_own_and_the_cache_is_kept():
    fit = (ROOT / "chartfit.py").read_text(encoding="utf-8")
    assert "ships = best_k > 0 and delta >= 2 * se and up >= min(3, len(per))" in fit
    assert '"ngs_def": ngs_def' in fit, "the defence's side of Next Gen Stats is on the same harness"
    for f in ("engine/likely.py", "engine/pipeline.py", "engine/yardagefit.py", "engine/nfl/pipeline.py"):
        p = ROOT / f
        if p.exists():
            assert "sources.ftn" not in p.read_text(encoding="utf-8"), f
    from engine.maintenance import KEEP_CACHE_PREFIXES
    assert "ftn_charting_" in KEEP_CACHE_PREFIXES
    from engine.sources import nflscheme as N
    assert callable(N.load_pfr_pass) and callable(N.load_pfr_rec), "all four PFR files are read now"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
