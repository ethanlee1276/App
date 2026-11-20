"""Every game posts three three-leg player-prop parlays and three two-leg
scorer pairs (ZR, 2026-11-20).

Ethan, 20 November: "We should be making the 3 best parlays possible with the
data we have including the game report with the best possible props we have",
and asked what that meant a game: "i want 3 3 leg player prop parlays and 3 2
leg td prop parlays". What these hold:

  * three of each a game (THREE_MIN, THREE_PER_GAME, SCORER_PER_GAME) and no
    two-leg player-prop ticket (RETIRED): the journal keeps the ones posted
    before, and the record leaves them off;
  * a game short of three three-leg tickets fills: two of the report's picks
    and one other prop, then the Most Likely board's picks in the picks'
    places, then the game's best props, last; each wider level adds to what
    the one before it made, never in its place, and a set whose tickets all
    win together still comes first (`choose`);
  * a football game short of three scorer pairs takes its next scorers, a
    weaker research case first and then a longer price, never an avoid read
    or a scorer with no red-zone role, each named on its pair;
  * each filled ticket says how it was made up (``fill``), the journal keeps
    it, and the record says how each way has done apart;
  * the heartbeat counts the games still short and the tickets filled.

    python3 tests/test_every_game_posts_three_and_three.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, parlayledger as PL  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
TD = __import__("test_touchdown_pairs_come_from_our_research")
GAME = EG.GAME


def _leg(player, market, p, team="NYG", pos="WR"):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "home": "NYG",
            "away": "WAS", "position": pos, "market": market, "market_label": market, "side": "Over",
            "line": 2.5, "odds": -150, "book": "DraftKings", "p": p, "game_date": "2099-11-12"}


def test_three_and_three_and_no_two_leg_ticket():
    assert GP.THREE_MIN == GP.THREE_PER_GAME == GP.SCORER_PER_GAME == 3
    assert GP.RETIRED == ("two",) and GP.SOURCES["two"] == "game_two", "kept, so the journal's history reads"
    gp = GP.build(EG.board(), "nfl")
    g = gp["games"][0]
    assert len(g["threes"]) == 3 and len(g["scorers"]) == 3, (len(g["threes"]), len(g["scorers"]))
    assert not any(k in g for k in ("twos", "paper_twos", "twos_note")), sorted(g)
    assert "twos" not in gp["counts"] and gp["counts"]["threes"] == 3 and gp["counts"]["scorers"] == 3


def test_each_wider_level_adds_to_what_the_one_before_made():
    """Three picks ride on two tickets at most (a leg rides on MAX_USES): the
    report's own two stay, and the game's best props make the third."""
    picks = [_leg("A One", "receptions", 0.72), _leg("B Two", "rush_yds", 0.70, team="WAS", pos="RB"),
             _leg("C Three", "rec_yds", 0.68, pos="TE")]
    props = [_leg("E Five", "rush_att", 0.62, pos="RB"), _leg("F Six", "rec_yds", 0.60, team="WAS", pos="TE")]
    mine = {GP._leg_id(l) for l in picks}
    made = GP.tickets_of("nfl", GAME, picks, extra=props, picks=mine)
    own = [sum(GP._leg_id(l) in mine for l in t["legs"]) for t in made["threes"]]
    assert own == [3, 2, 1], own
    assert [t.get("fill") for t in made["threes"]] == [None, "one", "props"]
    assert (made["filled"], made["props_filled"], made["board_filled"]) == (2, 1, 0), made
    last = made["threes"][-1]
    assert any("E Five over 2.5 rush_att (62%) and F Six over 2.5 rec_yds (60%) are not this report's picks: "
               "props the board priced, added so the game has 3 three-leg parlays" in c for c in last["caveats"]), \
        last["caveats"]
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    body = src[src.index("def tickets_of("):src.index("def board_pick(")]
    assert body.count("keep=held(got)") == 2, "the Most Likely level and the last both add, never replace"


def _t(joint, *legs):
    return {"legs": [{"player": p, "team": team, "market": "receptions", "side": "OVER", "line": 2.5}
                     for p, team in legs], "joint": joint, "need_margin": 0, "need_points": 0}


def test_a_set_that_wins_together_comes_before_a_held_one_that_cannot():
    ab, cd, ef = _t(0.50, ("A", "X"), ("B", "Y")), _t(0.45, ("C", "X"), ("D", "Y")), _t(0.40, ("E", "X"), ("F", "Y"))
    was = GP.pulls_apart
    # E and F want the game the other way from every other ticket here.
    GP.pulls_apart = lambda t, out: bool(out) and (t is ef or any(o is ef for o in out))
    try:
        assert GP.choose([ab, cd, ef], 2) == [ab, cd]
        got = GP.choose([ab, cd, ef], 2, keep=[GP.ident(ef)])
    finally:
        GP.pulls_apart = was
    assert [GP.ident(t) for t in got] == [GP.ident(ab), GP.ident(cd)], "held, it would lose with the others"
    assert not any(GP.APART_NOTE in (t.get("caveats") or []) for t in got)


def test_a_football_game_fills_its_scorer_pairs_with_its_next_scorers_each_named():
    white = TD._read("Rachaad White", "WAS", "RB", "neutral", {"carry_share": 0.45}, 0.40, 1.2, implied=19.0)
    avoid = TD._read("Terry McLaurin", "WAS", "WR", "avoid", {"tgt_share": 0.25}, 0.38, 1.6, implied=19.0)
    no_rz = TD._read("Wan'Dale Robinson", "NYG", "WR", "breakout", {"tgt_share": 0.26}, 0.31, 0.4)
    reads = [TD.SKATTEBO, TD.LIKELY, white, avoid, no_rz]
    scorers = [TD._td(x["player"], x["team"], x["pos"], x["td"]["model_prob"]) for x in reads]
    gp = GP.build(TD._board(reads, scorers), "nfl")
    g = gp["games"][0]
    on = [{l["player"] for l in t["legs"]} for t in g["scorers"]]
    assert len(on) == 3 and set().union(*on) == {"Cam Skattebo", "Isaiah Likely", "Rachaad White"}, on
    filled = [t for t in g["scorers"] if t.get("stand_ins")]
    assert len(filled) == 2 and all(t["fill"] == "stand_in" for t in filled)
    for t in filled:
        assert ("Rachaad White has a weaker research case (3 of 13 points, under the 4 a pair is built from): "
                "added so the game has 3 touchdown pairs") in t["caveats"], t["caveats"]
    assert "scorers_note" not in g and gp["counts"]["filled_scorers"] == 2
    # The report's one line names the research's best pair, not one with a stand-in (TDSGP2).
    from engine import gamereport as GR
    b = TD._board(reads, scorers)
    b["game_parlays"] = gp
    g["scorers"] = list(reversed(g["scorers"]))                   # posted pairs keep their places (ZQ)
    line = GR.parlay_sentence(GR.Ctx(TD._game(), b, sport="nfl"))
    best = line[line.index("Best touchdown pair: "):]
    assert "Rachaad White" not in best and "Cam Skattebo" in best and "Isaiah Likely" in best, line
    # The fill floor reads lower than the pairs' own, and never an avoid read
    # or a scorer with no red-zone role, however likely.
    assert GP.SCORER_FILL_FLOOR["nfl"] < GP.SCORER_FLOOR["nfl"]
    # A longer price fills after a weaker case: a strong case at 22%.
    longer = TD._read("Chris Rodriguez", "WAS", "RB", "good", {"carry_share": 0.42}, 0.22, 1.6, implied=19.0)
    reads2 = [TD.SKATTEBO, longer, white]
    scorers2 = [TD._td(x["player"], x["team"], x["pos"], x["td"]["model_prob"]) for x in reads2]
    g2 = GP.build(TD._board(reads2, scorers2), "nfl")["games"][0]
    said = " ".join(c for t in g2["scorers"] for c in t.get("caveats") or [])
    assert "Chris Rodriguez is a longer shot (22%, under the 25% a pair is built from)" in said, said
    assert "Rachaad White has a weaker research case" in said, said


def test_a_filled_ticket_is_journaled_with_how_it_was_made_up():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    leg = lambda p, m: {"player": p, "team": "KC", "market": m, "side": "OVER", "line": 1.5, "odds": -150,   # noqa: E731
                        "book": "DraftKings", "p": 0.7}
    t = lambda fill, *ps: dict({"legs": [leg(p, "receptions") for p in ps], "joint": 0.3, "take_dec": 3.5,  # noqa: E731
                                "naive_dec": 3.4, "independent": 0.34}, **({"fill": fill} if fill else {}))
    gp = {"games": [{"away": "DEN", "home": "KC", "game": "DEN@KC",
                     "threes": [t(None, "A", "B", "C"), t("one", "A", "B", "D"), t("props", "E", "F", "G")],
                     "scorers": [t("stand_in", "H", "I"), t("nonsense", "J", "K")]}]}
    assert PL.log_game_parlays(c, gp, "nfl", "2026-W12") == 5
    got = [r["fill"] for r in c.execute("SELECT fill FROM parlays ORDER BY id")]
    assert got == [None, "one", "props", "stand_in", None], got
    assert set(GP.FILL_KINDS) == {"one", "board", "props", "stand_in"}


def test_the_heartbeat_counts_the_short_and_the_filled():
    import launch as L
    t3 = {"legs": [{"player": "A"}, {"player": "B"}, {"player": "C"}]}
    t2 = {"legs": [{"player": "A"}, {"player": "B"}]}
    games = [{"home": "A", "threes": [t3] * 3, "scorers": [t2] * 3, "threes_props_filled": 1},
             {"home": "B", "threes": [t3] * 3, "scorers": [t2], "threes_board_filled": 2},
             {"home": "C", "threes": [], "scorers": [], "kept": "Sun 1:00 PM ET"},          # started: not counted
             {"home": "D", "threes": [], "scorers": [], "no_props": "props_not_bought"}]   # nothing priced yet
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_parlays": {"sport": "nfl", "games": games,
                              "counts": {"games": 4, "threes": 6, "scorers": 4, "filled_scorers": 2}}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert (got["sgp_threes"], got["td_pairs"], got["threes_short"]) == (6, 4, 1), got
    assert (got["td_short"], got["td_filled"]) == (1, 2), got
    assert (got["threes_props_filled"], got["threes_board_filled"]) == (1, 2), got
    assert "sgp_twos" not in got


def test_ask_and_the_record_page_say_three_and_three():
    from engine import askbot
    desc = " ".join(str(t.get("description") or "") for t in askbot.TOOLS)
    assert "three three-leg player-prop parlays and three two-leg touchdown or goal-scorer pairs" in desc
    js = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert 'const GP_KINDS = ["three", "scorers"];' in js and "GP_FILL_WORDS" in js
    rj = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert '{ type: "parlays", items: g.scorers.map((t, i) => card(t, i + 1, "scorers", sport)) }) : ""}${' in rj, \
        "a short game's scorer note shows under the pairs it made"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
