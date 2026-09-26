"""Auction values — the sheet has to add up, and it has to be sane.

IDEAS #1, shipped 2026-08-26: a dollar figure per player for the rooms
that bid instead of snake. Two failures would make it worse than nothing
and each has a test here:

  * **A sheet that does not balance.** If the values total more than the
    league can spend, every one of them is a lie by however much they
    overshoot — and you find out in the last three rounds, with a roster
    you cannot fill. Whole-dollar rounding is done by largest remainder
    precisely so the total lands on the money in the room exactly.
  * **A sheet whose top is impossible.** The first cut priced the top
    pick at $136 of a $200 budget because it borrowed the snake board's
    starter-level replacement. No auction has ever paid that. The
    baseline here is the last man DRAFTED, and a test pins that the top
    of the sheet stays inside a range a real room could pay.

Run directly: `python3 tests/test_auction.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import auction                                    # noqa: E402
from engine.fantasy_draft import REPLACEMENT_RANK             # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


#: A league-shaped pool: enough bodies at every position that the
#: replacement ranks land inside the list rather than on its last man,
#: and a decaying points curve so the top is genuinely scarce.
DEPTH = {"QB": 40, "RB": 90, "WR": 110, "TE": 40}
TOP = {"QB": 24.0, "RB": 22.0, "WR": 21.0, "TE": 16.0}
DECAY = {"QB": 0.22, "RB": 0.30, "WR": 0.24, "TE": 0.35}


def _pool():
    rows = []
    for pos, n in DEPTH.items():
        for i in range(n):
            rows.append({"player": f"{pos}{i + 1}", "position": pos,
                         "proj": round(max(0.5, TOP[pos] - DECAY[pos] * i), 1)})
    return rows


def test_the_sheet_spends_exactly_the_money_in_the_room():
    for teams in (8, 10, 12, 14, 16):
        for budget in (100, 200, 260, 400):
            rows = _pool()
            a = auction.attach(rows, teams=teams, budget=budget)
            assert a["allocated"] == a["total"] == teams * budget, \
                f"{teams} teams at ${budget} allocated {a['allocated']}"


def test_every_row_is_priced_even_the_worthless_ones():
    rows = _pool()
    auction.attach(rows, teams=12)
    assert all(isinstance(r.get("auction"), int) for r in rows), \
        "a row left the pass with no dollar figure — a missing key on the " \
        "page must mean the pass did not run, never that a player was skipped"
    assert all(r["auction"] >= 1 for r in rows), "a player priced below the minimum bid"


def test_replacement_level_and_below_is_the_minimum_bid():
    rows = _pool()
    a = auction.attach(rows, teams=12)
    base = a["replacement"]
    for r in rows:
        if r["proj"] <= base[r["position"]]:
            assert r["auction"] == 1, \
                f"{r['player']} is at or below replacement and is not $1"


def test_the_baseline_is_deeper_than_the_snake_board():
    """The one number in the module worth arguing about. A snake drafter
    streams the wire, so his alternative is the best free STARTER; an
    auction buys every bench spot in the room, so his alternative is the
    cheapest body who still gets drafted."""
    a = auction.attach(_pool(), teams=12)
    for pos, rank in a["ranks"].items():
        assert rank > REPLACEMENT_RANK[pos], \
            f"{pos} is priced against the same rank the snake board uses"


def test_the_top_of_the_sheet_is_a_price_a_room_could_pay():
    """The regression this whole baseline exists for: the starter-level
    replacement priced the top pick at 68% of one manager's budget."""
    for budget in (200, 300):
        a = auction.attach(_pool(), teams=12, budget=budget)
        share = a["max"] / budget
        assert 0.15 <= share <= 0.45, \
            f"top of the sheet is {share:.0%} of a ${budget} budget"


def test_the_pool_is_the_room_and_the_rest_are_dollars():
    a = auction.attach(_pool(), teams=12, budget=200)
    # 12 teams x 13 skill spots; kicker and defence keep their dollars.
    assert a["priced"] <= 12 * (a["slots"] - a["non_skill"])
    assert a["dollar_spots"] == 12 * a["slots"] - a["priced"]


def test_a_deeper_league_prices_more_players():
    small = auction.attach(_pool(), teams=8)
    big = auction.attach(_pool(), teams=14)
    assert big["priced"] > small["priced"]


def test_doubling_the_discretionary_money_doubles_the_value_above_a_dollar():
    """Value minus the minimum bid is linear in (budget - slots) — the
    property the page's budget input rescales on instead of asking the
    server to reprice."""
    rows_a, rows_b = _pool(), _pool()
    a = auction.attach(rows_a, teams=12, budget=115, slots=15)
    b = auction.attach(rows_b, teams=12, budget=215, slots=15)
    assert (b["budget"] - b["slots"]) == 2 * (a["budget"] - a["slots"])
    pairs = [(x["auction"], y["auction"]) for x, y in zip(rows_a, rows_b)
             if x["auction"] > 3]
    assert pairs
    for x, y in pairs:
        assert abs((y - 1) - 2 * (x - 1)) <= 2, \
            f"${x} did not rescale to ${y} when the purse doubled"


def test_the_position_split_adds_up_to_what_the_pool_was_given():
    rows = _pool()
    a = auction.attach(rows, teams=12)
    told = sum(b["dollars"] for b in a["by_position"].values())
    spent = sum(r["auction"] for r in rows if r["auction"] > 1)
    # Every priced player is in the split, and a $1 pool member is too —
    # so the split is the pool's dollars, not merely the expensive ones.
    assert told == a["allocated"] - a["dollar_spots"]
    assert told >= spent


def test_a_budget_that_cannot_fill_the_roster_prices_nobody():
    """Arithmetic, not a failure: below the roster size there is no
    discretionary money and every player is worth the minimum. The page
    cannot reach here (MIN_BUDGET is above a standard roster) but a
    caller can."""
    rows = _pool()
    a = auction.attach(rows, teams=12, budget=10, slots=15)
    assert a["per_vorp"] == 0.0
    assert a["max"] == 1
    assert all(r["auction"] == 1 for r in rows)


def test_an_empty_board_does_not_crash_the_sheet():
    a = auction.attach([], teams=12)
    assert a["priced"] == 0 and a["max"] == 1


def test_the_kit_prices_every_surface_and_leaves_the_snake_board_alone():
    from engine import db
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from test_fantasy_draft import _seed                       # noqa: E402
    from engine.fantasy_draft import build_draft_kit
    conn = db.connect(":memory:")
    _seed(conn)
    kit = build_draft_kit(conn, 2025)
    assert kit["auction"]["allocated"] == kit["auction"]["total"]
    assert all("auction" in r for r in kit["board"])
    for rows in kit["tiers"].values():
        assert all("auction" in r for r in rows)
    # The board is still ordered by VORP: pricing must not re-sort what
    # a snake drafter reads.
    vorps = [r["vorp"] for r in kit["board"]]
    assert vorps == sorted(vorps, reverse=True)


# --- the page ---------------------------------------------------------------

APP = _read("web", "js", "app.js")


def test_the_page_and_the_module_agree_on_the_budget_rails():
    assert f"DK_AUC_MIN = {auction.MIN_BUDGET}" in APP
    assert f"DK_AUC_MAX = {auction.MAX_BUDGET}" in APP


def test_the_board_is_re_sorted_when_the_currency_changes():
    """Snake order is VORP against a starter; auction order is dollars
    against the last man drafted. They disagree, and showing auction
    dollars in snake order would present the disagreement as a typo."""
    i = APP.index("const rows = auc")
    assert "dkDollars(kit, b, auc) - dkDollars(kit, a, auc)" in APP[i:i + 260]


def test_the_dollars_replace_the_vorp_column_rather_than_joining_it():
    """The phone drops every .dl-num that is not .strong, so a sixth
    column would wrap the board on the screen it is read on."""
    i = APP.index("const valueCell = (r) => auc")
    cell = APP[i:i + 700]
    assert "dl-num strong dk-money" in cell and "dl-num strong pos" in cell
    css = _read("web", "css", "styles.css")
    assert ".dk-money {" in css


def test_a_re_render_puts_the_draft_room_strikeouts_back():
    """Flipping the currency rebuilds every row. The taken set lives in
    the poll, twelve seconds apart — without this the board would show
    twenty drafted players as available."""
    i = APP.index("function dkAucApply()")
    assert "dkCrossOff();" in APP[i:i + 700]
    assert "dkState.taken = taken;" in APP


def test_the_budget_survives_a_reload_and_reaches_the_other_screen():
    assert 'const DK_AUC_KEY = "ff_auction";' in APP
    assert "auction: fa" in APP, "the budget never reaches the account sync"
    assert 'if ("auction" in d) put(DK_AUC_KEY, d.auction);' in APP, \
        "an older profile without the key would wipe the budget on sync"


def test_the_panel_refuses_to_predict_the_price():
    assert "what he is worth, not what he will go\n      for" in APP
    assert "no inflation curve here to fit" in APP


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
