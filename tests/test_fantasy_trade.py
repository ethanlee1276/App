"""Trades worth proposing — and the honest answer about acceptance.

Ethan, 2026-08-15: "Have a trade generator to generate trades and know if
they will m be accepted or not."

THE FIRST HALF IS BUILT. THE SECOND HALF IS REFUSED, ON PURPOSE, and that
refusal is what most of this file tests.

A player's value is not his ranking — it is what he adds to a particular
team's best legal STARTING lineup. A third good tight end is worth almost
nothing to a roster that starts one and ten points a week to the roster
with a hole there, and that asymmetry is the only reason a mutually
beneficial trade can exist at all. So both lineups are re-optimised after
the swap and the difference is the score. The tests below build exactly
that shape — one side four deep at running back, the other two deep at
tight end — and check a real deal falls out of it.

"WILL THEY ACCEPT" IS NOT FITTABLE and any percentage would be invented.
This repo has never stored a proposed trade, let alone an accepted one.
So `acceptance_odds` must not exist, the note must say why, and the log
must be there so that the question becomes answerable from evidence
rather than from a plausible-sounding number. Those three are tested.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import fantasy_trade as ft                        # noqa: E402

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"]
SCORING = {"rec": 1.0, "rec_yd": 0.1}


def _p(name, pos, pts):
    return (name, {"position": pos, "fp_ppr": pts, "_games": 16})


#: I am four deep at running back with three slots and starting a scrub at
#: tight end. They are two deep at tight end with one slot and starting
#: scrubs at running back. This is the shape a real trade lives in.
MINE_ROWS = [_p("My QB", "QB", 18), _p("RB A", "RB", 17), _p("RB B", "RB", 16),
             _p("RB C", "RB", 15), _p("RB D", "RB", 14),
             _p("WR A", "WR", 14), _p("WR B", "WR", 13),
             _p("Scrub TE", "TE", 4)]
THEIRS_ROWS = [_p("Th QB", "QB", 17), _p("Th RB", "RB", 6),
               _p("Th RB2", "RB", 5), _p("Th WR", "WR", 13),
               _p("Th WR2", "WR", 12), _p("TE A", "TE", 15),
               _p("TE B", "TE", 13)]
MEANS = dict(MINE_ROWS + THEIRS_ROWS)
MINE = [{"player": n, "position": m["position"]} for n, m in MINE_ROWS]
THEIRS = [{"player": n, "position": m["position"]} for n, m in THEIRS_ROWS]


# --- value is what a player adds to THIS lineup -----------------------------
def test_a_surplus_player_is_worth_less_than_his_ranking():
    """THE WHOLE PREMISE. My fourth running back outscores their starting
    tight end and is still worth less to me, because he never reaches the
    field. A generator working off rankings cannot see that and therefore
    cannot find a trade both sides want."""
    give = tuple(r for r in MINE if r["player"] == "RB D")
    get = tuple(r for r in THEIRS if r["player"] == "TE B")
    ev = ft.evaluate(MINE, THEIRS, give, get, SLOTS, SCORING, MEANS)
    assert MEANS["RB D"]["fp_ppr"] > MEANS["TE B"]["fp_ppr"]
    assert ev["my_gain"] > 0, "the swap should still improve my lineup"


def test_both_sides_are_scored_by_re_optimising_not_by_a_price():
    """A trade is scored by rebuilding both starting lineups, which is why
    the same player can be worth different amounts to each side."""
    give = tuple(r for r in MINE if r["player"] in ("My QB", "RB A"))
    get = tuple(r for r in THEIRS if r["player"] in ("Th QB", "TE B"))
    ev = ft.evaluate(MINE, THEIRS, give, get, SLOTS, SCORING, MEANS)
    assert ev["my_gain"] == 5.0 and ev["their_gain"] == 5.0


def test_a_trade_that_helps_only_one_side_is_not_returned():
    """That is a request, not a trade, and sending them is how a league
    stops reading your messages."""
    trades = ft.generate(MINE, {"Rival": THEIRS}, SLOTS, SCORING, MEANS)
    assert trades
    for t in trades:
        assert t["my_gain"] >= ft.MIN_GAIN and t["their_gain"] >= ft.MIN_GAIN


def test_noise_sized_gains_are_not_worth_proposing():
    assert ft.MIN_GAIN > 0
    ev = ft.evaluate(MINE, THEIRS,
                     (MINE[1],), (THEIRS[1],), SLOTS, SCORING, MEANS)
    if abs(ev["my_gain"]) < ft.MIN_GAIN or abs(ev["their_gain"]) < ft.MIN_GAIN:
        assert ev["both_gain"] is False


def test_a_lopsided_deal_is_labelled_rather_than_hidden():
    """Not a rule against proposing it — a label, so it is sent knowing
    how it will read."""
    ev = {"my_gain": 12.0, "their_gain": 1.0}
    got = ft.evaluate(MINE, THEIRS,
                      (MINE[1],), (THEIRS[5],), SLOTS, SCORING, MEANS)
    assert "lopsided" in got and "gap" in got and "favours" in got
    assert ft.LOPSIDED > 0
    del ev


def test_the_search_covers_bundles_not_just_one_for_ones():
    trades = ft.generate(MINE, {"Rival": THEIRS}, SLOTS, SCORING, MEANS)
    assert any(len(t["give"]) > 1 or len(t["get"]) > 1 for t in trades)


def test_combos_are_general_rather_than_unrolled():
    """The first cut hand-wrote k of 1 and 2 and returned an empty list for
    3 — which would have made MAX_PER_SIDE = 3 look like "no trades
    exist" instead of failing."""
    roster = [{"player": f"p{i}"} for i in range(4)]
    assert len(ft._combos(roster, 1)) == 4
    assert len(ft._combos(roster, 2)) == 6
    assert len(ft._combos(roster, 3)) == 4


def test_an_empty_league_produces_no_trades_rather_than_raising():
    assert ft.generate([], {}, SLOTS, SCORING, {}) == []
    assert ft.generate(MINE, {"Rival": []}, SLOTS, SCORING, MEANS) == []


def test_every_trade_names_the_team_it_is_with():
    trades = ft.generate(MINE, {"Rival": THEIRS}, SLOTS, SCORING, MEANS)
    assert all(t["with"] == "Rival" for t in trades)


# --- the half that is refused -----------------------------------------------
def test_there_is_no_acceptance_probability_anywhere():
    """THE POINT. Whether a manager says yes is a fact about a person —
    whether they read their messages, whether they like the player,
    whether they are tanking. Nothing here has ever been stored, so a
    percentage would be invented, and inventing one is exactly what this
    project does not do."""
    src = open(os.path.join(ROOT, "engine", "fantasy_trade.py"),
               encoding="utf-8").read()
    assert not hasattr(ft, "acceptance_odds")
    assert not hasattr(ft, "accept_probability")
    for row in ft.generate(MINE, {"Rival": THEIRS}, SLOTS, SCORING, MEANS):
        for key in row:
            assert "prob" not in key and "odds" not in key, key
    assert "will not be one" in src


def test_the_note_says_what_is_measured_instead():
    note = ft.summary(ft.generate(MINE, {"Rival": THEIRS}, SLOTS, SCORING,
                                  MEANS))["acceptance_note"]
    assert "invented" in note
    assert "starting lineup improves" in note or "starting lineup" in note


def test_a_proposal_can_be_written_down():
    """This is the step that makes the refused half answerable later."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.jsonl")
        trade = {"with": "Rival", "give": ["RB D"], "get": ["TE B"],
                 "my_gain": 3.0, "their_gain": 2.0}
        assert ft.log_proposal(trade, sent=True, outcome="", path=p)
        rows = ft.load_proposals(p)
        assert len(rows) == 1 and rows[0]["give"] == ["RB D"]
        assert rows[0]["sent"] is True


def test_a_corrupt_log_line_does_not_lose_the_file():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.jsonl")
        ft.log_proposal({"with": "a", "give": [], "get": []}, path=p)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        assert len(ft.load_proposals(p)) == 1


def test_the_evidence_refuses_to_quote_a_rate_too_early():
    """A rate from four proposals is a number about four people's moods."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.jsonl")
        for i in range(4):
            ft.log_proposal({"with": "r", "give": [], "get": []},
                            sent=True, outcome="accepted", path=p)
        ev = ft.acceptance_evidence(p)
        assert ev["graded"] == 4 and ev["enough"] is False
        assert ev["rate"] is None
        assert "moods" in ev["note"]


def test_the_evidence_reports_a_rate_once_there_is_enough():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.jsonl")
        for i in range(20):
            ft.log_proposal({"with": "r", "give": [], "get": []}, sent=True,
                            outcome="accepted" if i < 5 else "rejected",
                            path=p)
        ev = ft.acceptance_evidence(p)
        assert ev["enough"] is True and ev["rate"] == 0.25
        assert "logged" in ev["note"]


def test_an_ungraded_proposal_is_not_counted_as_a_rejection():
    """Silence is not a no — it is a row waiting for its outcome, and
    scoring it as a rejection would bias the first real measurement."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.jsonl")
        ft.log_proposal({"with": "r", "give": [], "get": []}, sent=True, path=p)
        ev = ft.acceptance_evidence(p)
        assert ev["sent"] == 1 and ev["graded"] == 0


# --- the wiring -------------------------------------------------------------
def test_the_page_shows_their_gain_beside_ours():
    """A trade panel that only shows what YOU gain is a wishlist. The
    other side's number is the one that decides whether it gets sent."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function ffTradesHTML(")
    body = app[i:app.index("\n}", i)]
    assert "t.their_gain" in body and "t.my_gain" in body
    assert "lopsided" in body


def test_the_page_prints_no_acceptance_percentage():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function ffTradesHTML(")
    body = app[i:app.index("\n}", i)]
    for word in ("accept_prob", "acceptance_odds", "% likely", "chance"):
        assert word not in body, f"the trade panel emits {word!r}"
    assert "acceptance_note" in body, "the note explaining why is missing"


def test_the_page_can_log_a_proposal():
    """The step that makes the refused half answerable later."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    assert "ff_trade_log" in app
    i = app.index("function ffLogTrade(")
    body = app[i:app.index("\n}", i)]
    assert "outcome" in body


def test_the_endpoint_only_offers_trades_when_it_knows_your_roster():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _league_desk(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert "if mine and rivals else []" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
