"""Four Bucs-Cowboys write-ups (2026-10-07) against the site: the marks
they hit that it did not.

Ethan: "look at where it is looking and the site isnt and make sure we are
hitting all the marks." docs/RESEARCH_PARITY_2026-10-08.md is the whole
audit; these pin the four gaps it closed:

  1. a defence's rushing yards allowed TO QUARTERBACKS, rated, shown on a
     QB rushing pick and in the scan — the number untouched until the box
     measures it (engine/defensevs, gamescan, defensefit);
  2. the research post-mortem's rule as a scout flag: a receiving over
     outside the team's top-two targets with under 15% of its targets
     (engine/scout, likelyctx) — a note until the record proves it;
  3. how the offence changes shape under a new quarterback: pass rate in
     his starts, his carries and rushing yards a game, air yards an attempt
     (engine/qbchange);
  4. the game page says when inactives post (web/js/app.js);
  5. (Ethan, later that night: "add the target-depth buckets on the cards
     too") where a receiver's targets come from by air yards — short /
     intermediate / deep — and how the defence does in that zone: counted
     per player-week and per defence-week off the play-by-play
     (engine/sources/nflpbp, nflunits), rated like every unit
     (engine/gamescan.UNITS), joined onto his usage (engine/nflusage), said
     on his card (gamescan.depth_facts) and registered for measurement
     (engine/scanfit) — shown, not in the number, until that run.

Run directly: `python3 tests/test_research_parity.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db as DB                                             # noqa: E402
from engine import defensevs as D                                       # noqa: E402
from engine import defensefit as DF                                     # noqa: E402
from engine import gamescan as G                                        # noqa: E402
from engine import likelyctx as C                                       # noqa: E402
from engine import qbchange as Q                                        # noqa: E402
from engine import scout as SC                                          # noqa: E402
from engine import scanfit as SF                                        # noqa: E402
from engine import nflusage as NU                                       # noqa: E402
from engine.sources import nflpbp as P                                  # noqa: E402
from engine.sources import nflunits as U                                # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _qb_rows():
    """Three weeks of two quarterbacks: one runs on Dallas, one does not."""
    rows = []
    for wk in (1, 2, 3):
        rows.append({"week": wk, "season_type": "REG", "position": "QB", "opponent_team": "DAL",
                     "player_display_name": "Runner", "rushing_yards": 60, "passing_yards": 220})
        rows.append({"week": wk, "season_type": "REG", "position": "QB", "opponent_team": "TB",
                     "player_display_name": "Pocket", "rushing_yards": 5, "passing_yards": 260})
        rows.append({"week": wk, "season_type": "REG", "position": "RB", "opponent_team": "DAL",
                     "player_display_name": "Back", "rushing_yards": 70})
    return rows


def test_a_defences_rushing_yards_to_quarterbacks_is_rated_shown_and_not_yet_in_the_number():
    assert D.STATS["qb_rush_yds"] == ("QB", ("rushing_yards",), "rushing yards to QBs")
    assert D.stat_for("QB", "rush_yds") == "qb_rush_yds" and D.stat_for("RB", "rush_yds") == "rb_rush_yds"
    assert D.model_stat("QB", "rush_yds") is None and D.transfer("QB", "rush_yds") == 0.0, \
        "shown, not in the number, until the box measures it"
    r = D.ratings(_qb_rows(), 4)
    assert r["DAL"]["qb_rush_yds"]["pg"] == 60.0 and r["DAL"]["qb_rush_yds"]["rank"] == 1
    assert r["TB"]["qb_rush_yds"]["pg"] == 5.0 and r["TB"]["qb_rush_yds"]["rank"] == 2
    assert r["DAL"]["rb_rush_yds"]["pg"] == 70.0, "the running backs' own stat is untouched"
    mult, why, card = D.effect("DAL", r["DAL"], "QB", "rush_yds")
    assert mult == 1.0 and why == "" and card
    assert card["model"]["applied"] == 1.0 and "has not predicted" in card["model"]["note"]
    text = str(card)
    assert "rushing yards to QBs" in text and "rushing yards to RBs" in text, \
        "his legs against what the defence gives up to quarterbacks, the run defence beside it"
    # The scan says it in words, and measures it on the box.
    assert G.D_STAT_WORDS["qb_rush_yds"] == "rushing yards to quarterbacks"
    assert ("rush_yds", "qb_rush_yds") in G._FACT_STATS["qb"]
    sign, line = G.rank_fact({"qb_rush_yds": {"rank": 1, "of": 32, "pg": 47.0}}, "qb_rush_yds", "DAL")
    assert sign == 1 and line == "DAL gives up 47 rushing yards to quarterbacks a game — the 1st-most of 32", line
    assert "QB" in DF.MARKETS["rush_yds"][0] and "RB" in DF.MARKETS["rush_yds"][0]


def test_a_receiving_over_outside_the_top_two_targets_on_thin_volume_is_flagged():
    assert "thin_target_over" in SC.FLAGS and SC.THIN_TARGET_SHARE == 0.15
    thin = SC.situation("receptions", "OVER", line=3.5, position="TE", values=[3, 4, 3, 3],
                        tgt_share=0.12, tgt_rank=3)
    assert "thin_target_over" in SC.flags(thin)
    for kw in ({"tgt_share": 0.12, "tgt_rank": 2}, {"tgt_share": 0.18, "tgt_rank": 4},
               {"tgt_share": None, "tgt_rank": 4}, {"tgt_share": 0.12, "tgt_rank": None}):
        s = SC.situation("receptions", "OVER", line=3.5, position="TE", values=[3, 4, 3, 3], **kw)
        assert "thin_target_over" not in SC.flags(s), kw
    under = SC.situation("rec_yds", "UNDER", line=40.5, position="WR", values=[30, 35], tgt_share=0.1, tgt_rank=5)
    assert "thin_target_over" not in SC.flags(under)
    rush = SC.situation("rush_yds", "OVER", line=40.5, position="RB", values=[50, 55], tgt_share=0.05, tgt_rank=6)
    assert "thin_target_over" not in SC.flags(rush), "a rushing over is not a receiving over"
    # The board reads his share and his place among his team's targets from
    # the scan's usage read.
    result = {"games": [{"home": "DAL", "away": "TB", "spread": -8.5, "total": 48.5}], "recommendations": [],
              "scan_reads": {"TB@DAL": {"players": [
                  {"player": "CeeDee Lamb", "team": "DAL", "usage": {"targets_pg": 11.0, "tgt_share": 0.33}},
                  {"player": "George Pickens", "team": "DAL", "usage": {"targets_pg": 6.5, "tgt_share": 0.20}},
                  {"player": "Jake Ferguson", "team": "DAL", "usage": {"targets_pg": 3.8, "tgt_share": 0.11}},
                  {"player": "Cade Otton", "team": "TB", "usage": {"targets_pg": 4.5, "tgt_share": 0.14}},
                  {"player": "Emeka Egbuka", "team": "TB", "usage": {"targets_pg": 7.0, "tgt_share": 0.22}},
                  {"player": "Chris Godwin", "team": "TB", "usage": {"targets_pg": 4.3, "tgt_share": 0.13}}]}}}
    rows = [{"player": "Jake Ferguson", "team": "DAL", "opponent": "TB", "market": "receptions", "side": "OVER",
             "line": 3.5, "odds": -110, "model_prob": 0.6, "recent_values": [4, 3, 2, 5]},
            {"player": "Cade Otton", "team": "TB", "opponent": "DAL", "market": "receptions", "side": "OVER",
             "line": 3.5, "odds": 105, "model_prob": 0.58, "recent_values": [4, 3, 5, 3]},
            {"player": "Chris Godwin", "team": "TB", "opponent": "DAL", "market": "receptions", "side": "OVER",
             "line": 3.5, "odds": -120, "model_prob": 0.6, "recent_values": [6, 3, 4, 3]},
            {"player": "George Pickens", "team": "DAL", "opponent": "TB", "market": "rec_yds", "side": "OVER",
             "line": 60.5, "odds": -115, "model_prob": 0.56, "recent_values": [75, 40, 60, 50]}]
    C.annotate(rows, result)
    by = {r["player"]: r["scout_flags"] for r in rows}
    assert "thin_target_over" in by["Jake Ferguson"], "third target, 11%: the post-mortem's cut"
    assert "thin_target_over" not in by["Cade Otton"], "second target on his team: not thin"
    assert "thin_target_over" in by["Chris Godwin"], "third target at 13%"
    assert "thin_target_over" not in by["George Pickens"], "second target at 20%"
    assert any("top-two targets" in t for t in rows[0]["scout_notes"])


def _weekly(name, team, wk, pos="QB", **kw):
    r = {"player_display_name": name, "recent_team": team, "week": wk, "position": pos, "season_type": "REG"}
    r.update(kw)
    return r


def test_the_new_quarterbacks_offence_is_described_by_its_shape():
    """Tampa under Daniels: a run-first, short-passing offence with a
    quarterback who runs. The card says so from the weekly rows."""
    stats = []
    for wk in (1, 2, 3):                      # Mayfield's starts: a throwing offence
        stats += [_weekly("Baker Mayfield", "TB", wk, attempts=36, passing_yards=260, passing_air_yards=290,
                          carries=2, rushing_yards=8),
                  _weekly("Bucky Irving", "TB", wk, pos="RB", carries=14, rushing_yards=60)]
    stats += [_weekly("Jalon Daniels", "TB", 4, attempts=27, passing_yards=148, passing_air_yards=113,
                      carries=8, rushing_yards=55),
              _weekly("Bucky Irving", "TB", 4, pos="RB", carries=16, rushing_yards=61),
              _weekly("Sean Tucker", "TB", 4, pos="RB", carries=7, rushing_yards=30)]
    qb = Q.quarterbacks([], stats, [], 5, lambda p: "TB")
    pr = qb["profile"]
    assert pr["Jalon Daniels"]["starts"] == 1 and pr["Jalon Daniels"]["games"] == 1
    assert pr["Jalon Daniels"]["pass_rate"] == round(27 / (27 + 8 + 16 + 7), 3)
    assert pr["Jalon Daniels"]["carries_pg"] == 8.0 and pr["Jalon Daniels"]["rush_yds_pg"] == 55.0
    assert pr["Jalon Daniels"]["air_per_att"] == 4.2
    assert pr["Baker Mayfield"]["starts"] == 3 and pr["Baker Mayfield"]["pass_rate"] == round(36 / (36 + 2 + 14), 3)
    assert pr["Baker Mayfield"]["air_per_att"] == round(290 / 36, 1)
    ch = {"team": "TB", "starter": "Baker Mayfield", "status": "OUT", "replacement": "Jalon Daniels",
          "replacement_ypa": 5.5, "starter_ypa": 7.2, "replacement_attempts": 27,
          "replacement_profile": pr["Jalon Daniels"], "starter_profile": pr["Baker Mayfield"]}
    words = Q.shape_words(ch)
    assert "in his 1 start this season the team threw on 47% of its plays (Baker Mayfield’s starts: 69%)" in words
    assert "he has run 8.0 times a game for 55 yards" in words
    assert "4.2 air yards an attempt against Baker Mayfield’s 8.1" in words
    d = Q.detail(ch)
    assert d.startswith("Jalon Daniels has thrown for 5.5 yards an attempt (27 attempts) against Baker Mayfield’s 7.2 — ")
    assert "47% of its plays" in d
    # WHERE THE BALL GOES UNDER HIM (the research's "4.2 air yards per
    # target"): the team's short and deep shares of its targets in his
    # starts, off the units table's offence rows.
    conn = DB.connect(":memory:")
    DB.upsert_team_units(conn, [
        {"sport": "nfl", "season": 2026, "period": f"{wk:03d}", "team": "TB", "side": "off", "opp": "X",
         "plays": 60, "short_tgt": st, "short_yds": 100.0, "mid_tgt": mi, "mid_yds": 80.0, "deep_tgt": dp, "deep_yds": 60.0}
        for wk, st, mi, dp in ((1, 14, 10, 6), (2, 15, 10, 5), (3, 16, 9, 5), (4, 22, 6, 2))]
        + [{"sport": "nfl", "season": 2026, "period": "005", "team": "TB", "side": "off", "opp": "X", "plays": 60}])
    td = Q.team_depth(conn, 2026)
    assert td[("TB", 4)] == {"short": 22.0, "mid": 6.0, "deep": 2.0} and ("TB", 5) not in td, \
        "a week from before the columns is no mix, not a zero one"
    qb3 = Q.quarterbacks([], stats, [], 5, lambda p: "TB", team_depth=td)
    pr3 = qb3["profile"]
    assert pr3["Jalon Daniels"]["short_share"] == round(22 / 30, 3) and pr3["Jalon Daniels"]["deep_share"] == round(2 / 30, 3)
    assert pr3["Baker Mayfield"]["short_share"] == 0.5 and pr3["Baker Mayfield"]["deep_share"] == round(16 / 90, 3)
    assert pr["Jalon Daniels"]["short_share"] is None, "without the table, nothing is said"
    ch3 = {**ch, "replacement_profile": pr3["Jalon Daniels"], "starter_profile": pr3["Baker Mayfield"]}
    w3 = Q.shape_words(ch3)
    assert ("in his starts 73% of the team’s targets were short throws (under 10 air yards) and 7% deep (20+) — "
            "Baker Mayfield’s starts: 50% short, 18% deep") in w3, w3
    assert "short throws" not in words, "no table: the old sentence"
    # The build puts the rows in the report; the slate builder hands them on.
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert 'carry_report["team_depth"] = _team_depth(_tdb.connect(), args.season)' in build
    assert build.index('carry_report["team_depth"]') < build.index("report=carry_report, qb_backups=True")
    nv = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()
    assert 'team_depth=report.get("team_depth") or None' in nv
    # No weekly rows under him yet: the sentence stays as it was.
    assert Q.detail({"team": "TB", "starter": "A", "replacement": "B", "replacement_attempts": 0}) \
        == "B has 0 pass attempts in our data — too few to rate"
    # A row without the air-yards column reads as unknown, never as 0.0.
    qb2 = Q.quarterbacks([], [_weekly("X", "TB", 1, attempts=30, passing_yards=200, carries=3, rushing_yards=12)],
                         [], 2, lambda p: "TB")
    assert qb2["profile"]["X"]["air_per_att"] is None


def _play(wk, off, dfn, receiver, air, yds, **kw):
    r = {"week": wk, "season_type": "REG", "posteam": off, "defteam": dfn, "play_type": "pass",
         "qb_dropback": 1, "rush": 0, "epa": 0.1, "success": 1, "yards_gained": yds,
         "sack": 0, "qb_hit": 0, "two_point_attempt": 0, "game_id": f"g{wk}", "drive": 1,
         "yardline_100": 60, "fixed_drive_result": "Punt", "receiver_player_name": receiver,
         "air_yards": air, "complete_pass": 1 if yds else 0, "pass_touchdown": 0}
    r.update(kw)
    return r


def test_targets_are_counted_by_depth_for_the_receiver_and_the_defence():
    assert (P.MID_AIR, P.DEEP_AIR) == (10.0, 20.0)
    assert [P.depth_zone(a) for a in (-3, 0, 9.9, 10, 19.9, 20, 45)] == \
        ["short", "short", "short", "mid", "mid", "deep", "deep"]
    plays = [_play(1, "DAL", "TB", "C.Lamb", 4, 7), _play(1, "DAL", "TB", "C.Lamb", 6, 0),
             _play(1, "DAL", "TB", "C.Lamb", 14, 18), _play(1, "DAL", "TB", "G.Pickens", 28, 0),
             _play(1, "DAL", "TB", "G.Pickens", 31, 44),
             # No air yards charted: not called short, not counted.
             _play(1, "DAL", "TB", "C.Lamb", "NA", 0)]
    # Per defence-week (the units): targets and yards in each zone.
    u = U.Units()
    for r in plays:
        u.add(r)
    rows = {(r["team"], r["side"]): r for r in u.rows(2026)}
    tb = rows[("TB", "def")]
    assert (tb["short_tgt"], tb["short_yds"]) == (2, 7.0)
    assert (tb["mid_tgt"], tb["mid_yds"]) == (1, 18.0)
    assert (tb["deep_tgt"], tb["deep_yds"]) == (2, 44.0)
    assert rows[("DAL", "off")]["deep_tgt"] == 2, "the offence's own mix sits on its side of the row"
    assert all(c in U.UNIT_COLS for c in ("air_yards", "receiver_player_name"))
    assert U.DEPTH_COLS == ("short_tgt", "short_yds", "mid_tgt", "mid_yds", "deep_tgt", "deep_yds")
    assert all(c in DB.TEAM_UNIT_COLS for c in U.DEPTH_COLS), "the table carries them"
    for z in ("short", "mid", "deep"):
        assert G.UNITS[z] == ((f"{z}_yds",), f"{z}_tgt", True) and z in G.UNIT_LABELS
    # Per player-week (the play-by-play fold): counts, never an xFP bucket.
    agg = P.aggregate_pbp(plays)
    assert agg["players"][("C.Lamb", "DAL", 1)]["_dep_short"] == 2
    assert agg["players"][("C.Lamb", "DAL", 1)]["_dep_mid"] == 1
    assert agg["players"][("G.Pickens", "DAL", 1)]["_dep_deep"] == 2
    assert "_dep_short" not in agg["values"], "the xFP value table prices only the situation buckets"
    logs = {(r["player"], r["market"]): r["value"] for r in P.xfp_player_rows(agg, 2026)}
    assert logs[("C.Lamb", "tgt_short")] == 2.0 and logs[("C.Lamb", "tgt_mid")] == 1.0 \
        and logs[("C.Lamb", "tgt_deep")] == 0.0
    assert logs[("G.Pickens", "tgt_deep")] == 2.0
    # A fresh database takes the rows, and the mix comes back per player.
    conn = DB.connect(":memory:")
    DB.upsert_team_units(conn, u.rows(2026))
    got = conn.execute("SELECT short_tgt, deep_yds FROM team_units WHERE team='TB' AND side='def'").fetchone()
    assert tuple(got) == (2, 44.0)
    rows_in = []
    for wk in (1, 2, 3, 4):
        for z, n in (("short", 3), ("mid", 1), ("deep", 1)):
            rows_in.append({"sport": "nfl", "season": 2026, "period": f"{wk:03d}", "game_id": f"DAL-{wk:03d}",
                            "player": "C.Lamb", "team": "DAL", "opponent": "", "position": "", "home": 1,
                            "market": f"tgt_{z}", "value": float(n)})
    rows_in.append({"sport": "nfl", "season": 2026, "period": "001", "game_id": "DAL-001", "player": "J.Ferguson",
                    "team": "DAL", "opponent": "", "position": "", "home": 1, "market": "tgt_short", "value": 4.0})
    DB.upsert_player_logs(conn, rows_in)
    mix = NU.depth_mix(conn, 2026)
    assert mix[("c", "lamb", "DAL")] == {"short": 0.6, "mid": 0.2, "deep": 0.2, "targets": 20}
    assert ("j", "ferguson", "DAL") not in mix, "four targets is no mix"
    assert ("c", "lamb", "DAL") not in NU.depth_mix(conn, 2026, upto_week=2), "five before week 2: thin"
    assert NU.depth_mix(conn, 2026, upto_week=3)[("c", "lamb", "DAL")]["targets"] == 10, "ten is the floor"
    assert "depth" in NU.build_usage_maps(conn, 2026)
    # The scan hangs it on his usage row by (initial, surname, team).
    usage = {("DAL", "ceedee lamb"): {"name": "CeeDee Lamb", "targets_pg": 11.0},
             ("DAL", "jake ferguson"): {"name": "Jake Ferguson", "targets_pg": 4.0}}
    assert G.attach_depth(usage, mix) == 1
    assert usage[("DAL", "ceedee lamb")]["depth"]["short"] == 0.6 and "depth" not in usage[("DAL", "jake ferguson")]


def test_the_card_says_where_his_targets_come_from_and_how_the_defence_does_there():
    ratings_def = {"def": {"short": {"rank": 24, "value": 6.9, "of": 32},
                           "mid": {"rank": 3, "value": 9.1, "of": 32},
                           "deep": {"rank": 15, "value": 14.0, "of": 32}}}
    lean = ["rec_yds", "receptions", "anytime_td"]
    f = G.depth_facts({"short": 0.58, "mid": 0.3, "deep": 0.12, "targets": 40}, "TB", ratings_def, 32, lean)
    assert len(f) == 1 and f[0]["text"] == \
        "58% of his targets are short throws (under 10 air yards); TB ranks 24th of 32 against them, " \
        "allowing 6.9 yards a target"
    assert f[0]["sign"] == 1 and f[0]["in_number"] is False and f[0]["kind"] == "depth"
    assert f[0]["markets"] == lean and f[0]["zone"] == "short"
    g = G.depth_facts({"short": 0.3, "mid": 0.5, "deep": 0.2, "targets": 40}, "TB", ratings_def, 32, lean)
    assert g[0]["sign"] == -1 and "intermediate throws (10–19 air yards); TB ranks 3rd of 32" in g[0]["text"]
    assert G.depth_facts({"short": 0.9, "mid": 0.1, "deep": 0.0, "targets": 9}, "TB", ratings_def, 32, lean) == []
    assert G.depth_facts({"short": 0.9, "mid": 0.1, "deep": 0.0, "targets": 40}, "TB", {"def": {}}, 32, lean) == [], \
        "a table from before the columns: no rank, no fact"
    assert G.depth_facts(None, "TB", ratings_def, 32, lean) == []
    # The tale of the tape carries the three zones, each row only where a
    # rank exists (a table from before the backfill shows nothing new).
    tape = APP[APP.index("const SCAN_UNITS = "):APP.index("const SCAN_READ_TONE")]
    for z, label in (("short", "Short throws"), ("mid", "Intermediate throws"), ("deep", "Deep throws")):
        assert f'["{z}", "{label}", ' in tape, z
    labels = APP[APP.index("const TAPE_LABELS = {"):APP.index("function tapeTier(")]
    assert 'short: ["Short throws (yds a target)", "Short throws allowed"]' in labels
    assert "deep: [" in labels and "mid: [" in labels
    assert "if (ra == null && rh == null) return \"\";" in APP[APP.index("function scanTapeHTML("):]
    # read_facts carries it for a receiver, after his role; never for a passer.
    facts = G.read_facts("wr", "WR", "DAL", "TB", usage={"games": 4, "tgt_share": 0.33, "targets_pg": 11.0,
                                                         "depth": {"short": 0.58, "mid": 0.3, "deep": 0.12,
                                                                   "targets": 40}},
                         allowed=None, ratings_def=ratings_def, points=None, line_words="", n_teams=32, room=None)
    kinds = [x["kind"] for x in facts]
    assert kinds[:2] == ["role", "depth"], kinds
    qb = G.read_facts("qb", "QB", "DAL", "TB", usage={"games": 4, "depth": {"short": 0.6, "mid": 0.3, "deep": 0.1,
                                                                            "targets": 40}},
                      allowed=None, ratings_def=ratings_def, points=None, line_words="", n_teams=32, room=None)
    assert "depth" not in [x["kind"] for x in qb]
    # Registered for measurement — PENDING, not SIGNALS: every signal in
    # SIGNALS has its MEASURED line and the page's sentence rests on that;
    # the run collects both, and the box's paste moves it over.
    assert "depth" in SF.PENDING and "depth" not in SF.SIGNALS
    assert not any(k[0] == "depth" for k in SF.MEASURED)
    assert ("rec_yds", "TE") in SF.PENDING["depth"]["markets"]
    assert all(m in SF.MARKETS for m in SF.PENDING["depth"]["markets"])
    assert "air_yards" in SF.RECV_COLS and "week" in SF.RECV_COLS
    zones = SF.depth_zones([{"receiver_player_name": "C.Lamb", "air_yards": a, "week": w}
                            for w, a in [(1, 3), (1, 5), (1, 12), (2, 2), (2, 4), (2, 6), (2, 7), (2, 25),
                                         (3, 1), (3, 2), (3, 3), (4, 30)]])
    assert SF.main_zone(zones, "C.Lamb", 3) is None, "eight targets before week 3: too few"
    assert SF.main_zone(zones, "C.Lamb", 4) == "short" and SF.main_zone(zones, "Nobody", 9) is None
    units = [{"period": "001", "team": t, "side": "def", "opp": "X", "dropbacks": 30, "pass_epa": 0.0,
              "plays": 60, "epa": 0.0, "rushes": 30, "rush_epa": 0.0, "short_tgt": 20, "short_yds": y}
             for t, y in (("TB", 160.0), ("DAL", 120.0), ("PHI", 140.0))]
    sig = SF.unit_signals(units, None, 2)
    assert round(sig["TB"]["def_short"], 3) == round(8.0 - 7.0, 3) and round(sig["DAL"]["def_short"], 3) == -1.0
    W = {"units": sig}
    assert SF.signal("depth", W, "DAL", "TB", {"player_name": "C.Lamb"}, {}, {}, 4, zones) == sig["TB"]["def_short"]
    assert SF.signal("depth", W, "DAL", "TB", {"player_name": "C.Lamb"}, {}, {}, 3, zones) is None


def test_the_game_page_says_when_inactives_post():
    fn = APP[APP.index("function inactivesNote("):APP.index("function whenLabel(")]
    assert 'state.sport !== "nfl"' in fn and "- 90" in fn and "inactives " in fn
    assert '["scheduled", "pre", "upcoming"].includes(st)' in fn, "while the game is still ahead"
    assert "${inactivesNote(g)}" in APP[APP.index('<div class="gp-sub">'):APP.index('<div class="gp-sub">') + 200]
    css = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
    assert ".gp-inactives {" in css
    assert os.path.exists(os.path.join(ROOT, "docs", "RESEARCH_PARITY_2026-10-08.md"))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
