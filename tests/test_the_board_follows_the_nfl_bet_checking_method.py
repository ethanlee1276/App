"""The Most Likely board and the game reports follow Ethan's NFL Bet checking method (2026-11-15).

Ethan, after their project's export was read again end to end: "Most
importantly is scanning the zip files ... and implementing that too the game
reports and the website and how the most likely bets are selected like how
we talked about". His master instructions and slate log name the props to
stay off; their own words in the chats add "I care more about what genuinely
will hit not my rules". So (engine/likelyboard.METHOD_AVOID):

  * the scout raises his two post-mortem rules it lacked — quarterback
    rushing unders, a back's receiving over with no route role — and his
    secondary-receiver rule takes its own alternative, 5 targets a game;
  * a pick breaking one of his rules stays on the board, tracked, but tops
    out at Worth a look and says which rule — the record keeps measuring it;
  * his touchdown rule (45%, or 40% with 30% of the red-zone work) on
    every touchdown pick and pair;
  * the reports carry his four scripts with the picks that hold in the most
    of them, each team's touchdown chances ranked beside what the defense
    allows the position, and a take-it-at price on every pick.

    python3 tests/test_the_board_follows_the_nfl_bet_checking_method.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R, likelyboard as B, scout as SC        # noqa: E402
from engine.gameparlays import card                                   # noqa: E402


def _flags(**kw):
    base = dict(market="receptions", side="OVER", position="WR", game_spread=-3.0, home=True, total=44.0)
    base.update(kw)
    return SC.flags(SC.situation(**base))


def test_the_scout_raises_his_post_mortem_rules():
    assert "qb_rush_under" in _flags(market="rush_att", side="UNDER", position="QB")
    assert "qb_rush_under" in _flags(market="rush_yds", side="UNDER", position="QB")
    assert "qb_rush_under" not in _flags(market="rush_att", side="UNDER", position="RB")
    assert "rb_route_over" in _flags(position="RB", tgt_share=0.06, tgt_rank=5)
    assert "rb_route_over" not in _flags(position="RB", tgt_share=0.14, tgt_rank=4)
    # The secondary-receiver rule: under 15% and outside the top two — unless
    # he sees 5 targets a game, the rule's own alternative.
    assert "thin_target_over" in _flags(tgt_share=0.11, tgt_rank=3, targets_pg=3.9)
    assert "thin_target_over" not in _flags(tgt_share=0.11, tgt_rank=3, targets_pg=5.2)
    assert "thin_target_over" not in _flags(tgt_share=0.16, tgt_rank=3, targets_pg=4.0)


def test_a_pick_breaking_a_rule_says_which_and_only_where_the_rule_speaks():
    row = {"market": "receptions", "side": "OVER", "scout_flags": ["thin_target_over", "boom_bust"]}
    assert B.method_fails(row, "nfl") == [B.METHOD_AVOID["thin_target_over"]], "needs-a-bomb is a yardage rule"
    assert B.method_fails(dict(row, market="rec_yds"), "nfl") == [B.METHOD_AVOID["thin_target_over"],
                                                                 B.METHOD_AVOID["boom_bust"]]
    assert B.method_fails({"market": "rush_yds", "side": "OVER", "scout_flags": ["blowout_over"]}, "nfl") == [], \
        "a favourite's back gets the clock-killing carries"
    assert B.method_fails({"market": "rec_yds", "side": "UNDER", "scout_flags": ["boom_bust"]}, "nfl") == []
    assert B.method_fails(row, "nba") == [], "football's method"
    assert B.method_fails(dict(row, market="anytime_td"), "nfl") == [], "a touchdown answers to its own rule"
    assert all(w.startswith("our rule:") for w in B.METHOD_AVOID.values()), "the card is every member's"


def test_the_touchdown_rule():
    assert B.td_rule({"model_prob": 0.47})["meets"] is True
    assert B.td_rule({"model_prob": 0.42, "rz_share": 0.35})["meets"] is True
    got = B.td_rule({"model_prob": 0.42, "rz_share": 0.2})
    assert got["meets"] is False and "45%, or 40% with 30% of the red-zone work" in got["why"]
    assert B.td_rule({"model_prob": 0.38, "rz_share": 0.6})["meets"] is False


def test_the_board_caps_a_rule_breaker_and_keeps_it():
    import test_the_nfl_board_is_tightened as T
    rows = [T._prop("A Back", 0.72, market="rush_yds", position="RB"),
            T._prop("B Catches", 0.70, market="receptions", position="WR")]
    b = B.build(T._result([dict(r) for r in rows]), record={}, sport="nfl", tiers_seen={})
    by = {r["player"]: r for r in b["rows"]}
    assert set(by) == {"A Back", "B Catches"}, "a rule breaker stays on the board"
    back = by["A Back"]
    assert "dog_run_over" in back["scout_flags"], "the Jets are 9.5-point underdogs"
    assert back["tier"] == "look" and back["method_note"] == (
        "Worth a look, not higher — our rule: no rushing over on a team likely to trail")
    assert by["B Catches"]["tier"] == "strong" and "method_note" not in by["B Catches"]


def test_a_pair_says_whether_its_scorers_meet_the_touchdown_rule():
    leg = {"player": "A", "market": "anytime_td", "side": "YES", "odds": 120, "p": 0.46}
    t = {"joint": 0.2, "independent": 0.19, "fair_words": "+400", "take_words": "+400",
         "legs": [leg, dict(leg, player="B", p=0.41)]}
    got = card(t, 1, "td", "nfl")
    assert got["td_rule"] is True and got["rule_note"] == "Both scorers are 40% or better — our touchdown rule"
    low = card(dict(t, legs=[leg, dict(leg, player="B", p=0.31)]), 2, "td", "nfl")
    assert low["td_rule"] is False and low["rule_note"] == "Below our touchdown rule (40% a scorer): B 31%"
    assert "rule_note" not in card(t, 1, "three", "nfl") and "rule_note" not in card(t, 1, "td", "nba")


def test_the_tickets_a_game_posts_are_built_to_win_together():
    """Ethan's chats, 2026-10-25 and 11-08: "I don't want to build them to
    where if one parlay wins, the other parlay can't win"."""
    from engine import gameparlays as GP

    def t(name, joint, margin, points=0):
        return {"legs": [{"player": name, "market": "receptions", "side": "OVER", "line": 4.5}],
                "joint": joint, "need_margin": margin, "need_points": points}
    a, b, c = t("A", 0.5, 1), t("B", 0.45, -1), t("C", 0.4, 1)
    got = GP.choose([a, b, c], 2)
    assert [x["legs"][0]["player"] for x in got] == ["A", "C"], "B needs the other side ahead"
    assert GP.choose([a, t("D", 0.45, 0, -1), t("E", 0.4, 0, 1)], 2)[1]["legs"][0]["player"] == "D", \
        "no lean against a lean is fine"
    # A game that cannot fill its tickets otherwise keeps the count, and the
    # ticket that pulls apart says so.
    got = GP.choose([a, b], 2)
    assert len(got) == 2 and GP.APART_NOTE in got[1]["caveats"] and GP.APART_NOTE not in (a.get("caveats") or [])


def test_every_pick_line_carries_the_price_it_is_worth():
    assert R.take_at(0.62) == "−163 or better"
    assert R.take_at(0.85) == "−250 or better", "never past the −250 limit"
    assert R.take_at(0.45) == "+122 or better"
    assert R.take_at(None) == "" and R.take_at(1.0) == ""


def test_the_report_carries_the_four_scripts_and_who_can_score():
    import test_the_game_report_reads_like_the_research as T
    text = R.to_text(T._report())
    for want in ("— Four scripts —",
                 "Script A, DET controls it (17% of the simulated games): Jahmyr Gibbs's carries",
                 "Script B, GB leads (42% of the simulated games)",
                 "Script C, a close game (21% of the simulated games)",
                 "Script D, a blowout (20% of the simulated games): DET's starters can sit in the fourth",
                 "— Who can score for Lions —",
                 # 2026-11-15: his share of the red-zone work is said as counts
                 # above these lines (rz_usage_lines), not as our estimate here.
                 "Jahmyr Gibbs (RB): 43% to score, at +333; GB allows the "
                 "second-most touchdowns to running backs; the touchdown matchup backs it"):
        assert want in text, want
    # Which scripts a pick holds in (rule 6: "Prefer props that can hit under
    # multiple scripts").
    assert R.script_fit("rush_yds", "OVER", "DET", "DET") == "ACD"
    assert R.script_fit("rush_yds", "OVER", "GB", "DET") == "BC"
    assert R.script_fit("receptions", "OVER", "GB", "DET") == "ACD"
    assert R.script_fit("receptions", "UNDER", "GB", "DET") == "B"
    assert R.script_fit("anytime_td", "YES", "GB", "DET") == ""


def test_a_game_with_no_qualifying_play_says_so_and_names_the_closest():
    """Rule 26: "The model should never force a bet. If nothing clears the
    thresholds: No qualifying plays at current lines. Then list: closest
    candidates…"."""
    class C:
        reads = [{"player": "A", "no_pick": {"best": {"market": "receptions", "side": "over", "line": 4.5,
                                                      "odds": -150, "model_prob": 0.58}}},
                 {"player": "B", "no_pick": {"best": {"market": "rush_yds", "side": "under", "line": 44.5,
                                                      "odds": -110, "model_prob": 0.46}}}]
    got = R.no_play_blocks(C())
    assert got[0] == {"type": "h", "text": "No qualifying plays at current lines"}
    assert got[1]["text"].endswith("Below are the closest, with the price each would need.")
    assert got[2]["items"] == ["A: Over 4.5 receptions (−150, 58%) — worth it at −138 or better.",
                               "B: Under 44.5 rush yds (−110, 46%) — our number is under even."]
    C.reads[0]["matchup_pick"] = {"market": "receptions", "side": "OVER"}
    assert R.no_play_blocks(C()) == [], "a game with a pick says nothing of the kind"


def test_the_heartbeat_counts_the_rules_at_work():
    import json
    import os
    import tempfile
    sys.path.insert(0, str(ROOT))
    import launch as L
    rows = [{"player": "A", "method_note": "Worth a look, not higher — our rule: …"},
            {"player": "B", "lane": "td", "td_rule": {"meets": True}},
            {"player": "C", "lane": "td", "td_rule": {"meets": False}}, {"player": "D"}]
    board = {"most_likely": [], "recommendations": [], "game_bets": [], "likely_board": {"rows": rows}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
            with open(path, "w") as fh:
                json.dump(dict(board, likely_board={"rows": [{"player": "D"}]}), fh)
            none = L._board_counts(path)
        finally:
            L._full_copy = was
    assert (got["method_capped"], got["td_rule_met"]) == (1, 1), got
    assert "method_capped" not in none, "a board the rules never touched says nothing"


def test_the_card_shows_the_rule():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = js.index("function obCardHTML(")
    body = js[i:js.index("\n}\n", i)]
    assert "r.method_note" in body and "r.td_rule && r.td_rule.meets" in body and "${method}" in body
    rep = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "t.rule_note" in rep and "gr-parlay-rule" in rep


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
                traceback.print_exc(limit=5)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
