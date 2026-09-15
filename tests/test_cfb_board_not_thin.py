"""The college scorer shelf shows twenty rows, not twenty minus the refusals.

Ethan, 2026-09-08, straight after the NFL board was widened: "do all
those checks on college football to make sure none of the [rows] for
the most likely [are] thin either."

Three checks, and college failed the first one for the same reason the
NFL did — a page's shelf size deciding what the BOARD is offered.

ONE — THE SCORER MENU. `CFB_WATCH_LIMIT` is twenty, the slate ratio
(college plays sixty-eight games on a Saturday to the NFL's sixteen),
and its own note calls it "how many most-likely scorers the board
carries". It was applied in `build_cfb_td_longshots`, truncating the
ranked menu before `likely.admissible` had seen a row — so the board's
bars came out of the twenty: the -250 price cap, an injury hold, a
proxy quote, the 55% floor. The top of a probability ranking is exactly
where the chalk is, so on a college Saturday the twenty most likely
scorers are the rows most likely to be refused AS chalk, and the
twenty-first, priced inside the cap and perfectly showable, was never
handed in. How many rows that costs on a real Saturday is not knowable
from here and is what `likely_census_by_kind` reports (`td`: offered
against shown); what is certain is that the seats were being spent
before the bar rather than by it. The menu leaves the builder whole now
and twenty is the board's `limit` — rows that survive.

It matters because the window is narrow. On this repo's own college
fixture the shown number clears the 55% floor only between about -250
and -130 — 0.546 at -320, 0.547 at +110 — so between Ethan's price cap
above and the floor below there is roughly one band of prices in which
a college scorer can appear at all, and twenty seats spent on chalk is
most of the shelf.

TWO — THE MONEYLINES. Fixed for both leagues on 2026-09-08: a row that
ranks on the market's number is no longer refused for the MODEL
disagreeing with that number. College was hit harder than the NFL —
401 of 1,066 eligible favourites (38%) against 207 of 681 (30%) —
because its ratings disagree with the close more often. Pinned here
through the college build's own card shape, since that measurement's
own test uses the NFL's.

THREE — THE CENSUS. `cfb_build` publishes `likely_census_by_kind`
beside the flat one, so a thin college board says which kind of row
died. Pinned in tests/test_likely_census_by_kind.py.

Run directly: `python3 tests/test_cfb_board_not_thin.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import db as DB                                   # noqa: E402
from engine import gamebets as G, likely as K                 # noqa: E402
from engine.cfb import tds as T                               # noqa: E402
from engine.sources import oddsapi as oa                      # noqa: E402

BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()

#: Sixteen a side, so the ranked menu is longer than the shelf even
#: after the value picks are deduped out of it. A real college roster is
#: deeper still; this is the smallest fixture that can tell "truncated
#: before the bar" from "refused by the bar".
PER_TEAM = 16

#: One real price each. Spelled out rather than computed, because a
#: price between -100 and +100 does not exist and a generated ladder
#: walks straight through that dead zone — the first cut quoted twenty
#: eight players and priced eight, which looked exactly like the defect
#: under test.
PRICES = (-320, -300, -280, -260, -240, -220, -200, -180,
          -160, -140, -120, 105, 125, 145, 165, 185)


def _hist(season=2025):
    """Two deep rosters. Shares only mean something against the whole
    team's volume, so every man carries yardage."""
    conn = DB.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    for team in ("UGA", "CLEM"):
        for i in range(PER_TEAM):
            name = f"{team} Player {i}"
            car, ry = (14 - i * 0.8), (70 - i * 4)
            rec, recy = (5 - i * 0.3), (60 - i * 3)
            for g in range(1, 7):
                for market, val in (("carries", max(car, 0.2)),
                                    ("rush_yds", max(ry, 2.0)),
                                    ("receptions", max(rec, 0.2)),
                                    ("rec_yds", max(recy, 2.0))):
                    conn.execute(
                        "INSERT INTO player_game_logs (sport, season, period, "
                        "game_id, player, team, market, value) VALUES "
                        "('cfb', ?, ?, ?, ?, ?, ?, ?)",
                        (season, f"2025-10-{g:02d}", f"g{g}", name, team,
                         market, val))
    conn.commit()
    return conn


def _games():
    return [{"home": "UGA", "away": "CLEM", "date": "2026-08-30",
             "kickoff": "2026-08-30T20:00:00Z", "spread": -13.5, "total": 55.5,
             "weather": {"dome": False, "wind_mph": 5, "temp_f": 78}}]


def _quotes():
    """Every man on both rosters priced inside the watch window."""
    out = {}
    for team in ("UGA", "CLEM"):
        for i in range(PER_TEAM):
            price = PRICES[i]
            out[oa.normalize_name(f"{team} Player {i}")] = [
                {"book": "DraftKings", "yes_odds": price,
                 "no_odds": -int(price * 0.85) if price > 0 else int(-price * 0.8)}]
    return {0: out}


# --- one: the menu leaves the builder whole ----------------------------------
def test_the_ranked_menu_is_not_truncated_before_the_board_sees_it():
    _rows, census, watch = T.build_cfb_td_longshots(
        _hist(), _games(), _quotes(), 2026)
    assert census["quoted_players"] == 2 * PER_TEAM, census
    assert len(watch) > T.CFB_WATCH_LIMIT, \
        f"the menu is still cut to the shelf's size: {len(watch)} rows"
    probs = [w["model_prob"] for w in watch]
    assert probs == sorted(probs, reverse=True), "the menu is not ranked"


def test_the_page_shelf_keeps_its_size_and_the_board_is_offered_everything():
    """The slice moved to where the page's key is published; the board
    call above it gets the whole list."""
    assert 'out["longshot_watch"] = watch[:_tds.CFB_WATCH_LIMIT]' in BUILD
    call = BUILD[BUILD.index('out["most_likely"] = _likely('):]
    call = call[:call.index("census_by_kind=_ml_kinds)") + 30]
    assert "rows, watch, sport=\"cfb\"" in call, call
    assert "watch[:" not in call, "the board is still handed a sliced menu"
    assert "limit=_player_limit" in call


def test_the_boards_player_cap_is_the_scorer_shelfs_number_while_it_is_alone():
    """`likely.LIMIT` is 40 across every player market a sport can rank.
    College can rank one, so its player half IS the scorer shelf and
    carries that shelf's number — until a college prop market is
    measured, when the cap reads the board's own again."""
    src = BUILD[BUILD.index("            # HOW MANY PLAYER ROWS COLLEGE SHOWS."):]
    src = src[:src.index('out["most_likely"]')]
    assert "_player_limit = (_tds.CFB_WATCH_LIMIT" in src
    assert "if len(_unmeasured) == len(_pm) else _K_LIMIT)" in src
    # The premise, checked rather than asserted in prose: today every
    # college prop market is unmeasured and anytime_td ranks.
    from engine.cfb.props import MARKETS
    assert not any(K.rankable(m, "cfb") for m in MARKETS), sorted(MARKETS)
    assert K.rankable("anytime_td", "cfb") and T.CFB_WATCH_LIMIT < K.LIMIT


# --- one, at the board ------------------------------------------------------
def _watch(player, prob, odds=-180):
    return {"player": player, "team": "UGA", "opponent": "CLEM",
            "book": "DraftKings", "odds": odds, "model_prob": prob,
            "implied_prob": round(min(0.98, prob + 0.02), 4),
            "ev_per_unit": -0.02, "reasons": ["because"],
            "recent_values": [1, 0, 1], "game_date": "2026-09-12"}


def _menu():
    """The Saturday shape: the twenty likeliest scorers are all chalk the
    board refuses, and the showable rows sit just behind them."""
    chalk = [_watch(f"Chalk {i}", 0.72 - i * 0.001, odds=-300)
             for i in range(T.CFB_WATCH_LIMIT)]
    good = [_watch(f"Showable {i}", 0.62 - i * 0.001) for i in range(8)]
    return chalk + good


def test_the_chalk_at_the_top_no_longer_costs_the_showable_rows_their_seats():
    old: dict = {}
    board = K.build([], None, _menu()[:T.CFB_WATCH_LIMIT], sport="cfb",
                    limit=T.CFB_WATCH_LIMIT, census=old)
    assert board == [], "this fixture does not reproduce the complaint"
    assert old == {"heavier than -250 — chalk, not a pick": T.CFB_WATCH_LIMIT}, old

    census: dict = {}
    kinds: dict = {}
    board = K.build([], None, _menu(), sport="cfb", limit=T.CFB_WATCH_LIMIT,
                    census=census, census_by_kind=kinds)
    assert [r["player"] for r in board] == [f"Showable {i}" for i in range(8)]
    assert census == {"heavier than -250 — chalk, not a pick": T.CFB_WATCH_LIMIT}
    assert kinds["td"]["offered"] == T.CFB_WATCH_LIMIT + 8
    assert kinds["td"]["kept"] == 8 and kinds["td"]["shown"] == 8


def test_the_cap_still_caps_what_the_board_shows():
    """Twenty-eight scorers all clear the bar; the shelf shows its twenty
    and the census says nothing was refused — the count is a cap, not a
    refusal, and the two must not read alike."""
    menu = [_watch(f"Scorer {i}", 0.70 - i * 0.001) for i in range(28)]
    census: dict = {}
    kinds: dict = {}
    board = K.build([], None, menu, sport="cfb", limit=T.CFB_WATCH_LIMIT,
                    census=census, census_by_kind=kinds)
    assert len(board) == T.CFB_WATCH_LIMIT and census == {}
    assert kinds["td"]["kept"] == 28 and kinds["td"]["shown"] == T.CFB_WATCH_LIMIT


# --- two: the college moneyline ---------------------------------------------
def _cfb_card(wp_home=0.47, home_ml=-220, away_ml=200):
    """A college moneyline in the shape `cfb_build.to_game_bet` ships:
    the shared card is `gamebets.moneyline_to_dict`'s, with the college
    verdict's own numbers written over it.

    `wp_home` is passed rather than read off `cfb_win_prob`, because the
    college curve is installed at build time from that box's own history
    (`engine.cfb.ratings.install`) and the suite must not read the box it
    runs on. The number is the fixture: our ratings make this close to a
    coin flip while the book makes the home side a 67% favourite."""
    import engine.gamecal as gamecal
    real = gamecal.shrink_for
    gamecal.shrink_for = lambda sport, market: 0.0
    try:
        card = G.moneyline_to_dict(
            G.price_moneyline("UGA", "CLEM", wp_home, home_ml, away_ml,
                              sport="cfb"))
    finally:
        gamecal.shrink_for = real
    # `book` the way `cfb_build._book_for_side` fills it on the real
    # path: a football game price the board cannot attribute is refused
    # (2026-09-09, tests/test_game_price_names_its_book.py).
    card.update({"home": "UGA", "away": "CLEM", "matchup": "CLEM @ UGA",
                 "date": "2026-09-12", "live": False, "started": False,
                 "book": "DraftKings",
                 "conditional": False, "grade": "Pass", "recommended": False})
    return card


def test_a_college_moneyline_is_not_refused_for_the_models_disagreement():
    card = _cfb_card()
    assert abs(card["engine_raw_prob"] - card["fair_prob"]) > 0.10, \
        "this fixture is not exercising a model that disagrees"
    census: dict = {}
    board = K.build([], game_bets=[dict(card)], sport="cfb", census=census)
    assert len(board) == 1 and census == {}, (board, census)
    row = board[0]
    assert row["prob_source"] == "market" and row["ranked"] is True
    assert row["rank_auc"] == K.GAME_RANK_MARKET["cfb"]["moneyline"]
    assert "own rating has this side at" in row["rank_note"]
    assert "does not bar the row" in row["rank_note"]


def test_the_college_card_carries_what_the_flip_needs():
    """A card the college build backs from the short end flips to the
    favourite, which needs the OTHER side's price on the row. College's
    moneyline card is `moneyline_to_dict`'s, so it has both by name —
    checked here because a college dog card with no other price is
    refused as "the other side's price is missing" and vanishes."""
    card = _cfb_card()
    for key in ("home_odds", "away_odds", "team", "engine_raw_prob"):
        assert card.get(key) is not None, key
    row = K.from_game_bet(dict(card), "cfb")
    assert row["flipped"] is True and row["team"] == "UGA"
    assert row["odds"] == card["home_odds"], "the flipped side kept the dog's price"


def test_the_droplet_gets_a_college_command_for_all_three():
    checks = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()
    at = checks.index("## 8e. The college Most Likely board (2026-09-08)")
    body = checks[at:checks.index("\n## ", at + 10)]
    assert "web/data/cfb.json" in body and "likely_census_by_kind" in body
    assert "401 of 1,066" in body, "the college measurement is not written down"
    assert "offered` at twenty exactly" in body, "no way to spot a stale deploy"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
