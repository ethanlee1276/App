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
  4. the game page says when inactives post (web/js/app.js).

Run directly: `python3 tests/test_research_parity.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import defensevs as D                                       # noqa: E402
from engine import defensefit as DF                                     # noqa: E402
from engine import gamescan as G                                        # noqa: E402
from engine import likelyctx as C                                       # noqa: E402
from engine import qbchange as Q                                        # noqa: E402
from engine import scout as SC                                          # noqa: E402

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
    # No weekly rows under him yet: the sentence stays as it was.
    assert Q.detail({"team": "TB", "starter": "A", "replacement": "B", "replacement_attempts": 0}) \
        == "B has 0 pass attempts in our data — too few to rate"
    # A row without the air-yards column reads as unknown, never as 0.0.
    qb2 = Q.quarterbacks([], [_weekly("X", "TB", 1, attempts=30, passing_yards=200, carries=3, rushing_yards=12)],
                         [], 2, lambda p: "TB")
    assert qb2["profile"]["X"]["air_per_att"] is None


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
