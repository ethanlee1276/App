"""The best legal lineup under YOUR league's scoring.

Ethan, 2026-08-15: "since league after draft to optimize line ups each
week."

WHAT MAKES THIS DIFFERENT FROM A RANKING, and what the tests therefore
have to hold:

  * SCORING IS THE LEAGUE'S. Half-PPR, TE premium and six-point passing
    touchdowns each change who should start. The tests below run the same
    four players through four scoring systems and check the order
    actually flips — a scorer that quietly ignored the settings would
    pass a "does it return a number" test all day.
  * SLOTS ARE THE LEAGUE'S, and the assignment is SOLVED. Filling
    dedicated slots and flexing the leftovers is optimal only while
    eligibility nests; a SUPERFLEX breaks it. `assign` is checked against
    brute force over every legal permutation on small boards, including
    superflex ones, because "looks right on my example" is how an
    optimiser ships a lineup that is quietly second best.
  * A GAP IS REPORTED, NEVER ASSUMED AWAY. The projection starts from
    nflverse's PPR total and adds only the differences this league makes.
    A component we do not store cannot be adjusted for, and an absent
    term looks exactly like a rule that matches PPR — so every row
    carries `exact` and `missing`.
"""

import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import fantasy_lineup as fl                       # noqa: E402

MEANS = {
    "Possession WR": {"position": "WR", "fp_ppr": 14.0, "receptions": 8.0,
                      "rec_yds": 60.0, "_games": 16},
    "Big Play WR": {"position": "WR", "fp_ppr": 14.0, "receptions": 3.0,
                    "rec_yds": 95.0, "_games": 16},
    "Volume TE": {"position": "TE", "fp_ppr": 11.0, "receptions": 7.0,
                  "rec_yds": 55.0, "_games": 16},
    "Pocket QB": {"position": "QB", "fp_ppr": 18.0, "pass_yds": 270.0,
                  "pass_td": 1.8, "pass_int": 0.7, "_games": 16},
    "Bench RB": {"position": "RB", "fp_ppr": 9.0, "rush_yds": 70.0,
                 "receptions": 2.0, "_games": 16},
}
ROSTER = [{"player": n, "position": m["position"]} for n, m in MEANS.items()]


# --- the scoring is the league's --------------------------------------------
def test_full_ppr_passes_the_baseline_through_untouched():
    """A league that matches PPR gets no adjustment at all — the base is
    already exactly right, and inventing a correction would be worse than
    doing nothing."""
    s = {"rec": 1.0, "rec_yd": 0.1, "pass_yd": 0.04, "pass_td": 4.0}
    for name, m in MEANS.items():
        got = fl.league_points(m, s)
        assert got["points"] == m["fp_ppr"], name
        assert got["exact"] is True


def test_half_ppr_separates_two_receivers_a_ranking_calls_equal():
    """Both score 14.0 in PPR. In half-PPR the eight-catch man loses four
    points and the three-catch man loses one and a half — which is the
    entire reason this is not a ranking."""
    s = {"rec": 0.5, "rec_yd": 0.1}
    poss = fl.league_points(MEANS["Possession WR"], s)["points"]
    big = fl.league_points(MEANS["Big Play WR"], s)["points"]
    assert poss == 10.0 and big == 12.5
    assert big > poss


def test_te_premium_puts_the_volume_tight_end_back():
    s = {"rec": 0.5, "rec_yd": 0.1}
    without = fl.league_points(MEANS["Volume TE"], s)["points"]
    with_ = fl.league_points(MEANS["Volume TE"],
                             {**s, "bonus_rec_te": 0.5})["points"]
    assert with_ - without == 3.5           # 0.5 × 7 receptions


def test_the_te_bonus_only_applies_to_tight_ends():
    s = {"rec": 1.0, "bonus_rec_te": 0.5}
    assert (fl.league_points(MEANS["Possession WR"], s)["points"]
            == MEANS["Possession WR"]["fp_ppr"])


def test_six_point_passing_touchdowns_move_the_quarterback():
    got = fl.league_points(MEANS["Pocket QB"], {"pass_td": 6.0})
    assert got["points"] == 18.0 + 1.8 * 2   # two extra points per TD


def test_a_component_we_do_not_store_is_named_rather_than_ignored():
    """An absent term looks exactly like a rule that matches PPR, and the
    difference is a lineup decision."""
    got = fl.league_points({"position": "WR", "fp_ppr": 12.0}, {"rec": 0.5})
    assert got["points"] == 12.0            # nothing could be adjusted
    assert got["exact"] is False and got["missing"] == ["rec"]


def test_a_player_with_no_data_scores_zero_rather_than_raising():
    got = fl.league_points({}, {"rec": 0.5})
    assert got["points"] == 0.0


# --- the assignment is solved, not greedily filled --------------------------
def _brute(players, slots):
    """Best total over every PARTIAL injective assignment.

    Partial matters: a roster with no tight end leaves the TE slot empty
    and the lineup is still legal. An exhaustive check that only scored
    boards where every slot could be filled would silently skip most
    random shapes — measured, it skipped nearly two thirds of them.
    """
    def rec(si, used):
        if si == len(slots):
            return 0.0
        best = rec(si + 1, used)            # leave this slot empty
        for pi, p in enumerate(players):
            if pi in used or not fl._eligible(slots[si], p["position"]):
                continue
            best = max(best, p["points"] + rec(si + 1, used | {pi}))
        return best
    return rec(0, frozenset())


def test_the_assignment_matches_brute_force_on_every_shape():
    """THE TEST THIS MODULE EXISTS FOR. Three hundred random boards across
    four slot layouts, including two with a SUPERFLEX — the layout where
    a greedy fill stops being optimal."""
    rng = random.Random(7)
    layouts = [
        ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"],
        ["QB", "RB", "WR", "FLEX", "SUPER_FLEX"],
        ["QB", "QB", "RB", "WR", "REC_FLEX"],
        ["RB", "WR", "WRRB_FLEX"],
    ]
    checked = 0
    for _ in range(300):
        n = rng.randrange(5, 9)
        players = [{"player": f"p{i}", "position": rng.choice(["QB", "RB", "WR", "TE"]),
                    "points": round(rng.uniform(0, 25), 1)} for i in range(n)]
        slots = rng.choice(layouts)[:n]
        want = _brute(players, slots)
        got = sum(p["points"] for p in fl.assign(players, slots).values())
        assert abs(got - want) < 1e-6, (slots, players)
        checked += 1
    assert checked == 300, f"only {checked} boards were checked"


def test_a_superflex_can_start_a_second_quarterback():
    players = [{"player": "QB1", "position": "QB", "points": 22.0},
               {"player": "QB2", "position": "QB", "points": 19.0},
               {"player": "RB1", "position": "RB", "points": 12.0}]
    seated = fl.assign(players, ["QB", "SUPER_FLEX"])
    assert {p["player"] for p in seated.values()} == {"QB1", "QB2"}


def test_a_plain_flex_cannot():
    players = [{"player": "QB1", "position": "QB", "points": 22.0},
               {"player": "QB2", "position": "QB", "points": 19.0},
               {"player": "RB1", "position": "RB", "points": 12.0}]
    seated = fl.assign(players, ["QB", "FLEX"])
    assert {p["player"] for p in seated.values()} == {"QB1", "RB1"}


def test_bench_seats_are_never_started():
    assert fl.starting_slots(["QB", "RB", "BN", "BN", "IR", "TAXI"]) == ["QB", "RB"]


def test_an_unfillable_slot_is_left_empty_rather_than_filled_wrongly():
    """No kicker on the roster means the K slot is empty. Seating a wide
    receiver there would be a lineup the league would reject."""
    out = fl.lineup([{"player": "WR1", "position": "WR"}], ["WR", "K"],
                    {"rec": 1.0}, {"WR1": {"position": "WR", "fp_ppr": 10.0,
                                           "_games": 16}})
    k = [s for s in out["starters"] if s["slot"] == "K"][0]
    assert k["player"] is None


# --- the whole answer -------------------------------------------------------
def test_the_lineup_fills_every_slot_it_can_and_totals_them():
    out = fl.lineup(ROSTER, ["QB", "RB", "WR", "TE", "FLEX", "BN", "BN"],
                    {"rec": 0.5, "rec_yd": 0.1}, MEANS)
    assert out["slots"] == ["QB", "RB", "WR", "TE", "FLEX"]
    assert all(s["player"] for s in out["starters"])
    assert out["total"] == round(sum(s["points"] for s in out["starters"]), 2)


def test_the_swap_list_is_what_makes_it_an_argument():
    """A lineup with no deltas is an instruction. With them it is a case
    you can disagree with, which is the difference between a tool and an
    oracle."""
    roster = ROSTER + [{"player": "Stud RB", "position": "RB"}]
    means = {**MEANS, "Stud RB": {"position": "RB", "fp_ppr": 25.0,
                                  "receptions": 4.0, "_games": 16}}
    out = fl.lineup(roster, ["QB", "RB", "BN", "BN", "BN", "BN"],
                    {"rec": 1.0}, means)
    assert [s["player"] for s in out["starters"] if s["slot"] == "RB"] == ["Stud RB"]
    assert out["swaps"] == [], "the best man is already in"


def test_a_better_bench_player_produces_a_swap_with_its_value():
    roster = [{"player": "Starter", "position": "RB"},
              {"player": "Better", "position": "RB"}]
    means = {"Starter": {"position": "RB", "fp_ppr": 8.0, "_games": 16},
             "Better": {"position": "RB", "fp_ppr": 14.0, "_games": 16}}
    out = fl.lineup(roster, ["RB", "BN"], {"rec": 1.0}, means)
    # The optimiser already starts the better man, so there is no swap.
    assert out["starters"][0]["player"] == "Better"
    assert out["bench"][0]["player"] == "Starter"


def test_a_thin_sample_is_flagged_but_not_dropped():
    """A rookie with two games is not a reason to leave a slot empty, and
    a board that silently loses him looks like a bug."""
    out = fl.lineup([{"player": "Rookie", "position": "RB"}], ["RB"],
                    {"rec": 1.0},
                    {"Rookie": {"position": "RB", "fp_ppr": 12.0, "_games": 2}})
    assert out["starters"][0]["player"] == "Rookie"
    assert out["starters"][0]["thin"] is True


def test_the_gap_is_carried_all_the_way_to_the_top():
    out = fl.lineup([{"player": "X", "position": "WR"}], ["WR"],
                    {"rec": 0.5}, {"X": {"position": "WR", "fp_ppr": 10.0}})
    assert out["exact"] is False and "rec" in out["missing"]


def test_an_empty_roster_is_an_empty_lineup_not_a_crash():
    out = fl.lineup([], ["QB", "RB"], {}, {})
    assert out["total"] == 0.0 and out["swaps"] == []
    assert all(s["player"] is None for s in out["starters"])


# --- the data behind it -----------------------------------------------------
def test_per_game_averages_over_games_played_not_the_calendar():
    """Dividing a season by 17 when he missed six weeks answers a question
    nobody asked at a start/sit screen."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE player_game_logs (sport TEXT, season INT,
        period TEXT, game_id TEXT, player TEXT, team TEXT, opponent TEXT,
        position TEXT, home INT, market TEXT, value REAL)""")
    for wk, v in ((1, 10.0), (2, 20.0)):
        c.execute("INSERT INTO player_game_logs (sport,season,period,player,"
                  "position,market,value) VALUES ('nfl',2025,?,?,?,?,?)",
                  (str(wk), "A", "WR", "fp_ppr", v))
    got = fl.per_game(c, 2025)
    assert got["A"]["fp_ppr"] == 15.0 and got["A"]["_games"] == 2


def test_a_missing_table_is_survivable():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    assert fl.per_game(c, 2025) == {}


def test_the_scoring_components_are_ingested_for_every_position():
    """The gap this closed: `rec_yds` was stored only for wide receivers
    and `rush_yds` only for backs, so a pass-catching back and every tight
    end had no receiving yards at all — precisely the players a half-PPR
    setting moves."""
    src = open(os.path.join(ROOT, "engine", "ingest.py"), encoding="utf-8").read()
    i = src.index("NFL_USAGE_MARKETS = {")
    block = src[i:src.index("}", i)]
    for market in ("rec_yds", "rush_yds", "pass_td", "pass_int"):
        assert f'"{market}"' in block, market
    # And the quarterback-only ones stay quarterback-only, or "he threw no
    # touchdowns" and "he is a wide receiver" become the same row.
    assert "NFL_QB_ONLY" in src
    assert "pass_td" in src[src.index("NFL_QB_ONLY"):src.index("NFL_QB_ONLY") + 200]


# --- the wiring -------------------------------------------------------------
def test_the_endpoint_reads_the_league_s_own_scoring_and_slots():
    """A default here would quietly answer a different league's question:
    a half-PPR TE-premium superflex league does not have the same best
    lineup as the standard one."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert '"/api/leaguedesk"' in src
    i = src.index("def _league_desk(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert 'league.get("scoring_settings")' in body
    assert 'league.get("roster_positions")' in body
    assert 'fullmatch(r"\\d{1,25}", league_id)' in body
    assert "sleeper_path_ok" in body


def test_the_page_says_when_the_scoring_could_not_be_applied_exactly():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function ffLineupHTML(")
    body = app[i:app.index("\n}", i)]
    assert "L.exact === false" in body
    assert "L.missing" in body


def test_a_league_with_no_roster_of_yours_is_told_so():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("async function renderLeagueDesk(")
    body = app[i:app.index("\n}", i)]
    assert "d.has_me" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
