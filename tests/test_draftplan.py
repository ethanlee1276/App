"""The draft plan: who to take in which round, from your seat.

Ethan, 2026-09-02: "a list for best draft orders of players ... who they
should draft in what round ... a tool to help users in their draft while
they are doing it." The plan is greedy and says so; these pins hold the
arithmetic it is greedy WITH: the seat's pick numbers, the count of other
picks before each, survival from the same function the live advice uses,
starting slots before bench, position caps, and the value/reach tags
against the market's round.

Run directly: `python3 tests/test_draftplan.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import draftplan as D
from engine.fantasy_pick import pick_numbers


def _board():
    """Twelve rows, VORP order, with the market roughly agreeing."""
    rows = [("cmc", "RB", 12.5, 24.5), ("bijan", "RB", 8.8, 20.8),
            ("puka", "WR", 8.6, 20.9), ("mcbride", "TE", 7.7, 17.7),
            ("gibbs", "RB", 7.6, 19.6), ("chase", "WR", 7.1, 19.4),
            ("achane", "RB", 6.5, 18.5), ("arsb", "WR", 6.0, 18.3),
            ("allen", "QB", 5.7, 23.2), ("jsn", "WR", 5.6, 17.9),
            ("brown", "RB", 5.1, 17.1), ("olave", "WR", 4.3, 16.6),
            ("bowers", "TE", 3.3, 13.3), ("lamar", "QB", 3.0, 21.0),
            ("cook", "RB", 4.3, 16.3), ("london", "WR", 4.2, 16.5)]
    board = [{"key": k, "player": k.title(), "position": pos, "vorp": v,
              "proj": pj, "tier": 1 + i // 4, "team": "T"} for i, (k, pos, v, pj) in enumerate(rows)]
    ranks = {r["key"]: i + 1 for i, r in enumerate(board)}
    return board, ranks


def test_others_before_counts_only_other_seats():
    mine = pick_numbers(7, 12, 15)              # 7, 18, 31, 42, ...
    assert mine[:3] == [7, 18, 31]
    assert D.others_before(7, 0, mine) == 6     # six seats pick before you
    assert D.others_before(18, 0, mine) == 16   # 17 picks, one of them yours
    assert D.others_before(18, 7, mine) == 10   # after your first, ten more
    assert D.others_before(7, 7, mine) == 0     # already happened


def test_the_first_pick_from_seat_one_is_certain_and_takes_the_top_of_the_board():
    board, ranks = _board()
    out = D.build(board, ranks, teams=2, slot=1, rounds=3)
    r1 = out["rounds"][0]
    assert r1["pick"] == 1 and r1["others_before"] == 0
    assert r1["plan"]["key"] == "cmc" and r1["plan"]["survives"] == 1.0
    # and the plan never repeats a player in a later round
    keys = [r["plan"]["key"] for r in out["rounds"] if r["plan"]]
    assert len(keys) == len(set(keys)) == 3


def test_a_late_seat_is_told_the_top_of_the_board_will_be_gone():
    board, ranks = _board()
    out = D.build(board, ranks, teams=12, slot=12, rounds=2)
    r1 = out["rounds"][0]
    assert r1["pick"] == 12 and r1["others_before"] == 11
    # cmc cannot survive eleven picks at depth 1 with a six-deep window
    # cmc at depth 1 survives eleven picks about one time in seven: not
    # a target, a reach — named as one, never as the plan
    assert "cmc" not in {c["key"] for c in r1["targets"]}
    assert r1["plan"]["key"] != "cmc"
    assert r1["plan"]["survives"] >= D.MIN_TARGET_P
    # by the second round he is simply gone and is named nowhere
    out2 = D.build(board, ranks, teams=12, slot=12, rounds=2)
    r2 = out2["rounds"][1]
    assert "cmc" not in {c["key"] for c in r2["reach"]}


def test_the_plan_weighs_value_by_survival_not_value_alone():
    """Value alone chose the earliest 40% shot every round. Expected value
    prefers the near-certain player unless the gamble is worth a lot."""
    board, ranks = _board()
    out = D.build(board, ranks, teams=12, slot=12, rounds=1)
    pick = out["rounds"][0]["plan"]
    assert pick["survives"] >= 0.5
    sure = {"key": "a", "position": "RB", "vorp": 5.0, "survives": 1.0}
    gamble = {"key": "b", "position": "RB", "vorp": 6.0, "survives": 0.4}
    assert D.score(sure, {}) > D.score(gamble, {})
    assert D.score({**gamble, "vorp": 20.0}, {}) > D.score(sure, {})


def test_starting_slots_are_filled_before_bench_and_caps_hold():
    board, ranks = _board()
    # a two-team room so the sixteen-man fixture lasts eight rounds, and
    # a sixty-deep window so everyone survives: the choice is pure
    out = D.build(board, ranks, teams=2, slot=1, rounds=8, window=60.0)
    picks = [r["plan"]["position"] for r in out["rounds"] if r["plan"]]
    assert picks.count("QB") <= D.MAX_AT_POSITION["QB"]
    assert picks.count("TE") <= D.MAX_AT_POSITION["TE"]
    # with everyone available the plan fills every starting slot (QB,
    # RB, RB, WR, WR, TE, FLEX) inside its first eight picks, and the
    # quarterback — worth two points of need against a back's or a
    # receiver's value — waits until the backs and receivers are in
    first8 = picks[:8]
    assert first8.count("QB") == 1 and first8.count("TE") == 1
    assert first8.count("RB") >= 2 and first8.count("WR") >= 2
    assert picks.index("QB") > 3


def test_starter_needs_reads_the_flex_as_the_thinnest_position():
    assert D.starter_needs({}, None) == {"QB": 1, "RB": 3, "WR": 2, "TE": 1}
    assert D.starter_needs({"RB": 2, "WR": 1, "QB": 1, "TE": 1}, None) == {"WR": 2}
    assert D.starter_needs({"RB": 3, "WR": 2, "QB": 1, "TE": 1}, None) == {}


def test_a_hand_marked_draft_advances_the_plan():
    board, ranks = _board()
    out = D.build(board, ranks, teams=12, slot=1, rounds=3,
                  taken=["bijan", "puka"], mine=["cmc"])
    assert out["picks_made"] == 3 and out["have"] == {"RB": 1}
    assert out["rounds"][0]["pick"] == 24          # your second pick
    planned = {r["plan"]["key"] for r in out["rounds"] if r["plan"]}
    assert not planned & {"bijan", "puka", "cmc"}


def test_the_summary_adds_up_a_starting_lineup():
    board, ranks = _board()
    out = D.build(board, ranks, teams=2, slot=1, rounds=8, window=60.0)
    s = out["summary"]
    assert s["planned"] == 8 and s["empty_rounds"] == 0
    assert len(s["starters"]) == 7
    assert s["starters_proj"] == round(sum(p["proj"] for p in s["starters"]), 1)
    assert s["shape"].startswith("R1 ")


def test_rounds_past_the_board_are_empty_not_invented():
    board, ranks = _board()
    out = D.build(board, ranks, teams=2, slot=1, rounds=20, window=60.0)
    assert out["summary"]["empty_rounds"] > 0
    assert all(r["plan"] is None for r in out["rounds"] if r["empty"])


def test_value_and_reach_tags_compare_rounds_not_ranks():
    board, ranks = _board()
    ranks = dict(ranks)
    ranks["olave"] = 40          # the market takes him three rounds later
    ranks["bowers"] = 1          # the market takes him first overall
    rows = {r["key"]: r for r in D.annotate_rounds(board, ranks, 12)}
    assert rows["olave"]["tag"] == "value" and rows["olave"]["market_round"] == 4
    assert rows["bowers"]["tag"] == "reach"
    assert rows["cmc"]["tag"] == "fair" and rows["cmc"]["our_round"] == 1


def test_the_draft_state_shape_feeds_the_live_advice_unchanged():
    from engine.fantasy_pick import my_slot
    d = D.draft_state(teams=10, slot=4, rounds=16)
    assert my_slot(d, "me") == 4
    assert d["settings"]["teams"] == 10 and d["type"] == "snake"


def test_the_window_comes_from_the_room_when_it_can():
    board, ranks = _board()
    picks = [{"key": k} for k in list(ranks)[:9]]      # a chalk room
    out = D.build(board, ranks, teams=12, slot=1, rounds=2, picks=picks,
                  taken=list(ranks)[:9])
    assert out["window_fitted"] is True
    assert out["window"] == D.DEFAULT_WINDOW or out["window"] <= 6.0


def test_the_round_list_and_the_round_count_do_not_share_a_name():
    board, ranks = _board()
    out = D.build(board, ranks, teams=2, slot=1, rounds=3)
    assert out["n_rounds"] == 3 and isinstance(out["rounds"], list)
    assert len(out["rounds"]) == 3


def test_it_fetches_nothing():
    import inspect
    src = inspect.getsource(D)
    for word in ("urlopen", "requests.", "fetch_text", "sqlite3"):
        assert word not in src, word


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
