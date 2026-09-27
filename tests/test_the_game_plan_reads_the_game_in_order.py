"""The game plan: one game read in a bettor's order (engine/gameplan).

Ethan, 2026-09-27, with the other AI's Jets @ Lions and Chargers @ Bills
reports: "focus on the way the ai thinks and finds its bets and its
thought process and the steps it goes through … this is the way we need
to be thinking on the site." Its steps, every game: the line and the
script; who is out and where the work goes; the matchup; the plays that
fit (volume first); the plays to avoid; what changes the read; and — the
step where it and the site part ways — where the number disagrees with
the market. The site refuses anything past ten points as its own error;
the other AI's strongest calls are exactly those (Sadiq 2.5+ catches,
Hampton 2+ catches). Those rows are named, never staked, and journaled
on paper so the record says who was right.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gameplan as P                                   # noqa: E402
from engine import gate                                             # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

GAME = {
    "home": "BUF", "away": "LAC", "date": "2026-09-27", "kickoff": "13:00", "spread": -7.0, "total": 50.0,
    "roof": "outdoors", "weather": {"dome": False, "forecast": False, "wind_mph": 6.0},
    "scan": {
        "units": {"BUF": {"off": {"passing": {"rank": 3}}}, "LAC": {"def": {"passing": {"rank": 26}}}},
        "edges": [{"off": "BUF", "def": "LAC", "unit": "passing", "off_rank": 3, "def_rank": 26, "gap": 23}],
        "coverage": {"BUF": {"corners": [{"name": "Christian Benford", "spot": "LCB", "rating": 119.2, "targets": 17}],
                             "missing": [], "weakest": "Christian Benford"},
                     "LAC": {"corners": [], "missing": [{"name": "Elijah Molden", "spot": "S", "status": "OUT"}],
                             "weakest": None}},
        "scheme": {"LAC": {"zone": 0.76, "man": 0.24, "blitz": 0.21}},
        "rush": {"BUF": [{"name": "Gregory Rousseau", "pressures": 9, "sacks": 4.0}]},
        "method": {"teams": 32, "opponent_adjusted": True},
        "injuries": [
            {"team": "BUF", "player": "Keon Coleman", "position": "WR", "status": "QUESTIONABLE",
             "opens": "If he sits — 14% of BUF's targets to share out"},
            {"team": "LAC", "player": "Charlie Kolar", "position": "TE", "status": "OUT",
             "opens": "5% of LAC's targets to share out"},
        ],
    },
}

READS = {"players": [
    {"player": "Khalil Shakir", "team": "BUF", "opp": "LAC", "pos": "WR", "read": "good", "label": "Good matchup",
     "lean": ["receptions", "rec_yds", "anytime_td"], "pro": ["LAC gives up the 7th-most passing yards"],
     "con": [], "usage": {"targets_pg": 6.0}},
    {"player": "Quentin Johnston", "team": "LAC", "opp": "BUF", "pos": "WR", "read": "tough", "label": "Tough matchup",
     "lean": ["receptions", "rec_yds"], "pro": [], "con": ["BUF gives up the 3rd-fewest catches to receivers"],
     "usage": {"targets_pg": 6.0}},
]}


def _rec(player, team, opp, market, side, line, hp, raw, fair, odds=-110, **kw):
    return {"player": player, "team": team, "opponent": opp, "position": kw.pop("position", "WR"),
            "market": market, "market_label": market, "side": side, "line": line, "hit_prob": hp,
            "raw_prob": raw, "fair_prob": fair, "odds": odds, "book": "FanDuel",
            "all_lines": [{"book": "FanDuel", "line": line, "over_odds": -120, "under_odds": 100}],
            "reasons": [], "projection": line, **kw}


RECS = [
    _rec("Khalil Shakir", "BUF", "LAC", "receptions", "OVER", 3.5, 0.59, 0.61, 0.60, odds=-159,
         game_script={"lean": "leads late and runs the clock"}),
    _rec("Dalton Kincaid", "BUF", "LAC", "receptions", "UNDER", 4.5, 0.55, 0.56, 0.51, trend_delta=1.7,
         position="TE"),
    _rec("Quentin Johnston", "LAC", "BUF", "receptions", "UNDER", 3.5, 0.58, 0.59, 0.55),
    _rec("Ladd McConkey", "LAC", "BUF", "receptions", "UNDER", 4.5, 0.61, 0.79, 0.44, odds=116,
         reasons=["Model disagrees with the market by more than 10 points — treated as a modelling or "
                  "data error, not an edge, so this is not staked"]),
    _rec("Omarion Hampton", "LAC", "BUF", "receptions", "OVER", 1.5, 0.64, 0.71, 0.57, odds=-148, position="RB"),
    _rec("Josh Allen", "BUF", "LAC", "pass_yds", "UNDER", 238.5, 0.51, 0.52, 0.49, position="QB"),
    _rec("Khalil Shakir", "BUF", "LAC", "rec_yds", "OVER", 48.5, 0.56, 0.57, 0.52,
         mate_card={"applied": 1.0, "if_sits": {"who": ["Keon Coleman"], "mult": 1.18, "case": "above_new"}}),
    # Another game entirely: never in this plan.
    _rec("Garrett Wilson", "NYJ", "DET", "rec_yds", "UNDER", 70.5, 0.56, 0.64, 0.50),
]

MATCHUP = {"game": "LAC@BUF", "home": "BUF", "away": "LAC", "td": [
    {"kind": "td", "player": "James Cook", "team": "BUF", "opponent": "LAC", "position": "RB",
     "market": "anytime_td", "market_label": "Anytime TD", "side": "YES", "line": 0.5, "odds": -130,
     "book": "DraftKings", "model_prob": 0.58, "label": "Strong case", "matchup_lines": ["Red zone: 3.1 chances a game"]},
], "props": [
    {"kind": "prop", "player": "Khalil Shakir", "team": "BUF", "opponent": "LAC", "position": "WR",
     "market": "receptions", "market_label": "Receptions", "side": "OVER", "line": 3.5, "odds": -159,
     "book": "DraftKings", "model_prob": 0.5911, "read": "good", "label": "Good matchup",
     "matchup_lines": ["LAC gives up the 7th-most passing yards (265 a game)"]},
    {"kind": "prop", "player": "Khalil Shakir", "team": "BUF", "opponent": "LAC", "position": "WR",
     "market": "rec_yds", "market_label": "Receiving Yards", "side": "OVER", "line": 48.5, "odds": -114,
     "book": "FanDuel", "model_prob": 0.56, "read": "good", "label": "Good matchup", "matchup_lines": []},
    {"kind": "prop", "player": "Weak Case", "team": "BUF", "opponent": "LAC", "position": "WR",
     "market": "receptions", "market_label": "Receptions", "side": "OVER", "line": 2.5, "odds": -110,
     "book": "FanDuel", "model_prob": 0.50, "read": "good", "label": "Good matchup", "matchup_lines": []},
]}

BOARD = {"rows": [{"player": "Khalil Shakir", "market": "receptions", "side": "OVER", "line": 3.5,
                   "game": "LAC@BUF", "tier": "top", "tier_label": "Top pick", "model_prob": 0.5911}]}

RESULT = {"games": [GAME, {"home": "DET", "away": "NYJ", "spread": -6.5, "total": 48.5}],
          "scan_reads": {"LAC@BUF": READS}, "recommendations": RECS,
          "matchup_picks": [MATCHUP], "likely_board": BOARD}


def _plan():
    plans = P.build(RESULT, "nfl")
    assert [p["game"] for p in plans] == ["LAC@BUF"], "a game without a scan has no plan"
    return plans[0]


def _step(p, key):
    return next(s for s in p["steps"] if s["key"] == key)


def test_the_steps_come_in_a_bettors_order():
    p = _plan()
    assert [s["key"] for s in p["steps"]] == ["line", "out", "matchup", "fits", "avoid", "watch", "gap"]
    assert p["script"]["archetype"] == "Favorite runs, dog throws"
    line = _step(p, "line")["lines"]
    assert line[0].startswith("BUF by 7 at 50: the lines expect BUF to score about 28.5, LAC about 21.5")
    assert "BUF leads late and runs the clock" in line[1] and "LAC expected to trail and throw" in line[1]
    out = [r["player"] for r in _step(p, "out")["rows"]]
    assert out == ["Charlie Kolar", "Keon Coleman"], "the ruled-out first, the questionable after"
    m = " ".join(_step(p, "matchup")["lines"])
    assert "BUF's passing offence (3rd of 32) against LAC's passing defence (26th) — edge BUF." in m
    assert "Christian Benford (LCB) has allowed a 119 passer rating" in m
    assert "LAC's starting S Elijah Molden is out" in m and "LAC plays zone 76% of the time, blitzes 21%." in m
    assert "Gregory Rousseau (9 pressures, 4 sacks)" in m


def test_plays_that_fit_are_the_reads_plays_volume_first_and_say_their_seat():
    fits = _step(_plan(), "fits")["rows"]
    assert [(r["player"], r["market"]) for r in fits] == [
        ("Khalil Shakir", "receptions"), ("James Cook", "anytime_td"), ("Khalil Shakir", "rec_yds")], \
        "catches and touchdowns (by our chance) before yardage; a 50% case is not a fit"
    shakir = fits[0]
    assert shakir["on_board"] and shakir["tier"] == "top" and shakir["tier_label"] == "Top pick"
    assert shakir["volume"] and "A volume market — a bet on his role, not on a big play." in shakir["why"]
    assert "Script: leads late and runs the clock." in shakir["why"]
    assert not fits[2]["on_board"] and not fits[2]["volume"]
    assert "Yardage — a bet on his role AND a big play" in fits[2]["why"][-1]
    note = _step(_plan(), "fits")["note"]
    assert note.startswith("Receiving yards and rushing yards are read-only on this site"), note


def test_plays_to_avoid_are_the_over_that_fights_the_matchup_or_chases_last_week():
    avoid = _step(_plan(), "avoid")["rows"]
    by = {r["player"]: r for r in avoid}
    assert set(by) == {"Quentin Johnston", "Dalton Kincaid"}, by
    qj = by["Quentin Johnston"]
    assert qj["side"] == "OVER" and qj["odds"] == -120, "the over's own price, not the row's under"
    assert qj["why"] == "The over fights the matchup — BUF gives up the 3rd-fewest catches to receivers."
    assert abs(qj["model_prob"] - 0.42) < 1e-9, "our chance on the over"
    k = by["Dalton Kincaid"]
    assert k["why"].startswith("Chasing last week — his last three sit +1.7 catches above his form")
    assert "Khalil Shakir" not in by and "Josh Allen" not in by


def test_where_we_disagree_is_named_never_staked_and_journaled_at_the_raw_chance():
    gap = _step(_plan(), "gap")["rows"]
    assert [r["player"] for r in gap] == ["Ladd McConkey", "Omarion Hampton"], gap
    mc = gap[0]
    assert (mc["raw_prob"], mc["fair_prob"], mc["gap"]) == (0.79, 0.44, 0.35)
    assert mc["why"].startswith("Our raw number says 79% on the under; the market says 44%.")
    assert "stakes nothing" in mc["why"] and "on paper" in mc["why"]
    rows = P.journal_rows([_plan()])
    assert [(r["player"], r["model_prob"]) for r in rows] == [("Ladd McConkey", 0.79), ("Omarion Hampton", 0.71)]
    assert "Garrett Wilson" not in {r["player"] for r in gap}, "another game's row"
    assert P.GAP_MIN == 0.10


def test_what_changes_the_read_is_a_call_that_moves_a_number_and_the_weather():
    watch = _step(_plan(), "watch")["rows"]
    assert watch[0]["player"] == "Keon Coleman" and watch[0]["text"] == "If he sits: Khalil Shakir +18% receiving yards."
    assert watch[1]["status"] == "weather" and "no game-time forecast" in watch[1]["text"]
    assert len(watch) == 2, "a questionable player who moves nothing sits under 'who is out', not here"


def test_a_pickem_reads_as_no_script():
    g = dict(GAME, spread=0.0, total=44.0)
    d, lines = P.script_lines(g)
    assert d["favorite"] == "" and lines[0].startswith("Pick'em at 44")
    assert P.script_lines({"home": "A", "away": "B"})[1][0].startswith("No posted line yet")


def test_attach_never_raises_and_the_builds_journal_and_pay_for_it():
    r = {"games": [{"home": "A", "away": "B", "scan": {"units": {}}}], "recommendations": [{"bad": object()}]}
    line = P.attach(r, "nfl")
    assert line.startswith("Game plans: 1 game(s)") and r["game_plans"][0]["game"] == "B@A"
    assert P.attach({"games": None}, "nfl").startswith("Game plans: 0 game(s)")
    assert "game_plans" in gate.PAID_KEYS
    nfl = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    cfb = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    for src in (nfl, cfb):
        assert "_gplan.attach(" in src and 'category="plan_gap"' in src and "_gap_rows(" in src
    assert nfl.index("_lb.build(result, record=_rec)") < nfl.index("_gplan.attach(result, 'nfl')"), \
        "built after the board, so a fit can say its tier"


def test_the_page_and_ask_carry_the_plan():
    assert "function gamePlanHTML(g)" in APP and 'id="gp-sec-plan"' in APP
    assert '["gp-sec-plan", "Game plan"]' in APP and "${gamePlanHTML(g)}" in APP
    assert "d.locked.game_plans" in APP, "locked, the section says what it is"
    assert ".gplan-step" in CSS and ".gplan .sc-lines" in CSS
    from engine import askbot as A
    board = dict(RESULT, game_plans=P.build(RESULT, "nfl"))
    facts = A.game_facts(board, GAME, scan=True)
    plan = facts["game_plan"]
    assert list(plan)[:1] == ["script"] and plan["fits"][0]["player"] == "Khalil Shakir"
    assert plan["gap"][0]["raw_prob"] == 0.79 and plan["out"][0].startswith("Charlie Kolar (LAC TE, out)")
    assert "game_plan" not in A.game_facts(board, GAME, scan=False), "the plan rides with the scan: paid"
    assert "game_plan is that game read in a bettor's order" in A.SYSTEM_PROMPT if hasattr(A, "SYSTEM_PROMPT") \
        else "game_plan is that game read in a bettor's order" in open(os.path.join(ROOT, "engine", "askbot.py"), encoding="utf-8").read()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
