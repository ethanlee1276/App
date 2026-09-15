"""Pick-by-pick advice: who will NOT be there at your next pick.

Ethan, 2026-08-15: "We need to show pick by pick advice."

THE BOARD ALREADY ANSWERS "WHO IS BEST" and that is the easy half. Taking
the best available when he would have lasted another round, and passing
on the man who will not, is how a good board produces a bad team. So the
unit under test is the SURVIVAL estimate, and these tests pin the three
ways it could quietly stop meaning anything:

  * the snake maths — slot 12 picks back-to-back and slot 1 waits
    twenty-two, and a seat error does not produce slightly wrong advice,
    it produces advice for somebody else's team;
  * the reach window — measured from THIS room's picks, not assumed, and
    falling back to a stated prior while the sample is too small to fit;
  * the monotonicity of survival in every argument, which is what stops
    the number being a plausible-looking function of nothing.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import fantasy_pick as fp                         # noqa: E402

RANKS = {f"p{i}": i for i in range(1, 61)}
BOARD = [{"key": f"p{i}", "player": f"P{i}", "position": "RB", "vorp": 60 - i}
         for i in range(1, 61)]
DRAFT = {"type": "snake", "settings": {"teams": 12, "rounds": 15},
         "draft_order": {"me": 3, "you": 7}}


def _chalk(n=14):
    """A room that always takes the consensus best available."""
    return [{"key": f"p{i}", "picked_by": "them"} for i in range(1, n + 1)]


def _reachy(n=14, seed=3):
    pool = [f"p{i}" for i in range(1, 61)]
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        out.append({"key": pool.pop(min(len(pool) - 1, rng.randrange(8, 20))),
                    "picked_by": "them"})
    return out


# --- which seat is yours, and when you pick ---------------------------------
def test_the_snake_turns_round_on_even_rounds():
    """Slot 12 picks twice in a row at the turn and slot 1 waits
    twenty-two picks. A model that assumed even waits would tell the turn
    to hoard and the ends to relax — exactly backwards."""
    assert fp.pick_numbers(1, 12, 4) == [1, 24, 25, 48]
    assert fp.pick_numbers(12, 12, 4) == [12, 13, 36, 37]
    assert fp.pick_numbers(3, 12, 3) == [3, 22, 27]


def test_a_linear_draft_does_not_turn_round():
    assert fp.pick_numbers(3, 12, 3, "linear") == [3, 15, 27]


def test_an_impossible_seat_yields_no_picks_rather_than_wrong_ones():
    assert fp.pick_numbers(0, 12, 4) == []
    assert fp.pick_numbers(13, 12, 4) == []
    assert fp.pick_numbers(3, 0, 4) == []


def test_a_draft_you_are_only_watching_has_no_seat_for_you():
    """Inventing a slot would produce confident advice for a team that is
    not yours."""
    assert fp.my_slot(DRAFT, "stranger") is None
    assert fp.my_slot({}, "me") is None
    assert fp.my_slot(DRAFT, "me") == 3


def test_the_wait_is_counted_from_the_picks_already_made():
    mine = fp.pick_numbers(3, 12, 4)               # 3, 22, 27, 46
    assert fp.next_pick(3, mine) == 22
    assert fp.picks_until(3, mine) == 18
    assert fp.next_pick(22, mine) == 27
    assert fp.picks_until(26, mine) == 0           # on the clock
    assert fp.next_pick(999, mine) is None


# --- how this room drafts, measured rather than assumed ---------------------
def test_a_chalk_room_measures_as_chalk():
    w = fp.reach_window(_chalk(), RANKS)
    assert w <= 2.0, w


def test_a_reaching_room_measures_as_one():
    w = fp.reach_window(_reachy(), RANKS)
    assert w > 8.0, w


def test_a_room_that_has_barely_started_uses_the_stated_prior():
    """A window fitted on three picks is one loud homer away from
    nonsense, and the board says which of the two it is using."""
    assert fp.reach_window(_chalk(3), RANKS) == fp.DEFAULT_WINDOW
    out = fp.advice(DRAFT, _chalk(3), RANKS, BOARD, "me")
    assert out["window_fitted"] is False
    assert fp.advice(DRAFT, _chalk(14), RANKS, BOARD, "me")["window_fitted"]


def test_the_window_is_clamped_at_both_ends():
    """Under 1 the arithmetic stops meaning anything; over 40 it is not a
    draft, it is a raffle, and the numbers stop being worth printing."""
    assert fp.reach_window(_chalk(30), RANKS) >= fp.WINDOW_FLOOR
    wild = [{"key": f"p{i}", "picked_by": "x"} for i in range(60, 10, -1)]
    assert fp.reach_window(wild, RANKS) <= fp.WINDOW_CEILING


def test_a_pick_of_someone_we_do_not_rank_is_skipped_not_counted():
    """A kicker taken in round nine is not evidence the room reaches."""
    picks = _chalk(10) + [{"key": "some kicker", "picked_by": "x"}]
    assert fp.reach_window(picks, RANKS) == fp.reach_window(_chalk(10), RANKS)


# --- survival ---------------------------------------------------------------
def test_nobody_picking_before_you_is_certainty_not_a_model():
    assert fp.survival(1, 0, 6.0) == 1.0
    assert fp.survival(50, None, 6.0) == 1.0


def test_survival_falls_as_the_wait_grows():
    ps = [fp.survival(5, k, 6.0) for k in (1, 5, 11, 22)]
    assert ps == sorted(ps, reverse=True)
    assert ps[-1] < ps[0]


def test_survival_rises_with_depth():
    ps = [fp.survival(d, 10, 6.0) for d in (1, 5, 15, 40)]
    assert ps == sorted(ps)


def test_a_player_far_beyond_the_reach_is_safe_until_the_queue_arrives():
    """Depth 40 with a window of 6 needs 34 picks before he is even a
    candidate — telling you to rush him would be the model inventing
    urgency."""
    assert fp.survival(40, 10, 6.0) == 1.0
    assert fp.survival(40, 40, 6.0) < 1.0


def test_a_room_that_reaches_leaves_the_top_of_the_board_alone():
    """The direction is worth pinning because it is counter-intuitive.
    A room that reaches is SAFER for the best available, not riskier —
    every pick spent forty spots down is a pick not spent on him."""
    assert fp.survival(1, 6, 15.0) > fp.survival(1, 6, 2.0)
    # And it is more dangerous for the man deep down the board, who a
    # chalk room would never have reached at all. Needs a real wait — over
    # six picks nobody gets 25 deep under either window, and both are
    # correctly 1.0.
    assert fp.survival(25, 6, 15.0) == fp.survival(25, 6, 2.0) == 1.0
    assert fp.survival(25, 22, 15.0) < fp.survival(25, 22, 2.0)


def test_probabilities_stay_inside_zero_and_one():
    for d in (1, 10, 100):
        for k in (0, 1, 50, 500):
            for w in (1.5, 6.0, 40.0):
                p = fp.survival(d, k, w)
                assert 0.0 <= p <= 1.0


def test_three_verdicts_because_two_would_lie():
    """One threshold forces every 50/50 into a confident word."""
    assert fp.verdict(0.95) == "safe"
    assert fp.verdict(0.50) == "toss-up"
    assert fp.verdict(0.05) == "gone"


# --- what you already have --------------------------------------------------
def test_only_your_own_picks_count_as_your_roster():
    picks = [{"key": "p1", "picked_by": "me"}, {"key": "p2", "picked_by": "them"}]
    got = fp.roster_counts(picks, "me", {"p1": "RB", "p2": "RB"})
    assert got == {"RB": 1}


def test_need_is_starters_only():
    """A bench body is not a need, and treating it as one is how a board
    tells you to take a fourth tight end in the eighth round."""
    assert fp.needs({"RB": 2}, {"RB": 2, "WR": 2}) == {"WR": 2}
    assert fp.needs({"TE": 3}, {"TE": 1}) == {}


# --- the advice -------------------------------------------------------------
def test_the_recommendation_is_the_best_man_who_cannot_wait():
    """The pick a later round cannot give back. In a chalk room with a
    long wait, that is simply the best available — everyone near the top
    is gone by the turn."""
    out = fp.advice(DRAFT, _chalk(14), RANKS, BOARD, "me", {"RB": 2})
    assert out["take"]["player"] == "P15"
    assert out["take"]["verdict"] == "gone"


def test_when_everyone_is_safe_it_says_take_the_best_available():
    """On the clock, nobody picks before you, so no urgency exists and
    manufacturing some would be the model talking."""
    out = fp.advice(DRAFT, _chalk(2), RANKS, BOARD, "me", {"RB": 2})
    assert out["picks_until"] == 0 and out["on_the_clock"]
    assert out["take"]["survives"] == 1.0
    assert out["take"]["player"] == "P3"


def test_players_already_taken_are_not_recommended():
    out = fp.advice(DRAFT, _chalk(14), RANKS, BOARD, "me", {"RB": 2})
    names = {r["player"] for r in out["board"]}
    assert not (names & {f"P{i}" for i in range(1, 15)})


def test_the_can_wait_list_is_the_other_half_of_the_advice():
    """"Take X now and Y next" is the actual decision, and it needs both
    halves — a board that only shouts about urgency gives you no plan."""
    out = fp.advice(DRAFT, _chalk(14), RANKS, BOARD, "me", {"RB": 2})
    assert out["can_wait"]
    assert all(r["verdict"] == "safe" for r in out["can_wait"])


def test_the_advice_survives_a_draft_it_knows_nothing_about():
    out = fp.advice({}, [], {}, [], "nobody")
    assert out["slot"] is None and out["take"] is None
    assert out["board"] == []


def test_the_note_says_what_the_model_cannot_see():
    out = fp.advice(DRAFT, _chalk(14), RANKS, BOARD, "me")
    assert "ruled out" in out["note"] and "consensus" in out["note"]


def test_it_reads_the_room_rather_than_a_national_average():
    """The whole construction. Two rooms, the same board, different
    advice — because the sample is the twelve people you are drafting
    against, not strangers."""
    a = fp.advice(DRAFT, _chalk(14), RANKS, BOARD, "me")
    b = fp.advice(DRAFT, _reachy(14), RANKS, BOARD, "me")
    assert a["window"] < b["window"]
    assert a["board"][0]["survives"] < b["board"][0]["survives"]


# --- the boundary -----------------------------------------------------------
def test_this_module_fetches_nothing():
    """Same discipline as the rankings board: every input is handed in, so
    there is no request here to grow a credential onto."""
    src = open(os.path.join(ROOT, "engine", "fantasy_pick.py"),
               encoding="utf-8").read()
    assert "import" in src
    for word in ("urllib", "requests", "fetch_text", "http"):
        assert word not in src, f"fantasy_pick reached for {word!r}"


# --- the wiring -------------------------------------------------------------
def test_the_endpoint_exists_and_validates_its_draft_id():
    """A path parameter forwarded to a fetch is how a proxy becomes an
    open relay on the user's own network."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert '"/api/draftadvice"' in src
    i = src.index("def _draft_advice(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert 'fullmatch(r"\\d{1,25}", draft_id)' in body
    # And every Sleeper read still goes through the allowlist.
    assert "sleeper_path_ok" in body


def test_the_endpoint_reuses_the_cached_pick_feed():
    """The browser is already polling these picks. A second uncached
    fetch on the same 12-second loop would double the traffic for no new
    information."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _draft_advice(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert "ttl=10" in body                 # same ttl the proxy uses for picks


def test_the_starter_slots_come_from_the_draft_not_a_default():
    """A superflex or a 3-WR league has different needs, and a hard-coded
    12-team default would tell a superflex room to take one quarterback."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _draft_advice(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert '"slots_" + pos.lower()' in body


def test_a_spectator_is_told_so_rather_than_advised():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("async function dkAdvice(")
    body = app[i:app.index("\n}", i)]
    assert "a.slot == null" in body
    assert "spectator" in body.lower()


def test_the_advice_panel_is_polled_with_the_picks():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function dkStart(")
    body = app[i:app.index("\nfunction ", i + 1)]
    assert "dkAdvice(draftId)" in body


def test_the_panel_shows_the_survival_number_not_just_a_name():
    """"Take him now" without "12% to last" is an instruction with no
    reason attached, and the reason is the whole feature."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("async function dkAdvice(")
    body = app[i:app.index("\n}", i)]
    assert "take.survives" in body and "can_wait" in body
    assert "window_fitted" in body, "the page never says when it is on a prior"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
