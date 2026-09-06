"""The likelihood board is shelved by the kind of bet, not one flat list.

Ethan, 2026-08-30: "i made the site and im getting confused on it... a
normal better is going to be looking for bets that are most likely to
hit and probably not thinking about the edge a prop has. for someone
betting nfl, they wanna find good props and td props, so lets lay it out
that way."

Two separate faults, and they had different shapes.

THE BOARD was every market interleaved by probability. That sort is
correct — it is the whole point of the page — and the GROUPING was
missing, so a person shopping for touchdowns had to re-derive the group
by eye on every visit, on every slate.

THE MENU listed six rows under "Betting" in an order that said nothing,
with Value Bets (then "Player Props") above Most Likely. `boards.guide()`
has ordered these by evidence since the day it was written — likelihood
first, the staking board last, because its edge claim tests at 0.468 —
and the navigation had never been told. A menu that leads with the
weakest board is pointing people at it.

THE SHELVES ARE NOT ORDERED BY AUC AND THIS FILE PINS THAT. Receptions
rank 0.770 and touchdowns 0.721; sorting on that gap would present a
difference nothing here has shown is real, which is the same error as
reading a non-monotone ROI column as an edge. The figure is shown as
information. The order is what a bettor came to buy.

Run directly: `python3 tests/test_board_shelves.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import boards
from engine.likely import RANK_AUC


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# --- the shape ------------------------------------------------------------
def test_football_leads_with_touchdowns():
    """What Ethan asked for, in the position he asked for it."""
    sh = boards.shelves("nfl")
    assert sh[0]["key"] == "touchdowns", [x["key"] for x in sh]
    assert sh[0]["markets"] == ["anytime_td"]


def test_college_football_gets_the_same_shelves():
    assert ([s["key"] for s in boards.shelves("cfb")]
            == [s["key"] for s in boards.shelves("nfl")])


def test_every_ranked_market_has_a_shelf():
    """A market that ranks but has nowhere to sit would vanish from the
    board — an empty page rather than an error."""
    shelved = {m for s in boards.shelves("nfl") for m in s["markets"]}
    assert set(RANK_AUC) <= shelved, set(RANK_AUC) - shelved


def test_the_shelves_are_not_sorted_by_auc():
    """The load-bearing one. If someone "improves" this by sorting on
    measured strength, receptions lead and the reason is noise."""
    got = [s["rank_auc"] for s in boards.shelves("nfl")]
    assert got != sorted(got, reverse=True), got


def test_a_shelf_reports_its_weakest_market_not_its_average():
    """A shelf is only as trustworthy as the worst row under it."""
    rec = [s for s in boards.shelves("nfl") if s["key"] == "receiving"][0]
    assert rec["rank_auc"] == min(RANK_AUC["receptions"], RANK_AUC["rec_yds"])


def test_the_figures_come_from_the_fitted_values():
    """Not typed into a template. A copy is a number that rots at the
    next refit — the mistake engine/boards was written to stop."""
    td = [s for s in boards.shelves("nfl") if s["key"] == "touchdowns"][0]
    assert td["rank_auc"] == RANK_AUC["anytime_td"]


# --- rows land on the right shelf -----------------------------------------
def _rows():
    return [
        {"player": "A", "market": "anytime_td"},
        {"player": "B", "market": "receptions"},
        {"player": "C", "market": "rec_yds"},
        {"player": "D", "market": "rush_yds"},
    ]


def test_rows_are_dealt_to_their_shelf():
    got = {s["key"]: [r["player"] for r in s["rows"]]
           for s in boards.shelves("nfl", _rows())}
    assert got == {"touchdowns": ["A"], "receiving": ["B", "C"],
                   "rushing": ["D"]}, got


def test_an_empty_shelf_is_dropped_rather_than_drawn_blank():
    assert "passing" not in {s["key"]
                             for s in boards.shelves("nfl", _rows())}


def test_no_row_is_lost_when_a_market_has_no_shelf():
    """The failure mode that looks like a working page. A new market
    with no shelf must land somewhere visible, not disappear."""
    rows = _rows() + [{"player": "E", "market": "sacks"}]
    out = boards.shelves("nfl", rows)
    assert sum(len(s["rows"]) for s in out) == len(rows)
    other = [s for s in out if s["key"] == "other"]
    assert other and [r["player"] for r in other[0]["rows"]] == ["E"]


def test_passing_the_rows_is_optional():
    """Without rows this is just the shape, which is what a page renders
    before a slate loads."""
    assert all("rows" not in s for s in boards.shelves("nfl"))


# --- it reaches the page --------------------------------------------------
def test_the_payload_carries_the_shelves():
    src = _src("engine", "pipeline.py")
    assert '"board_shelves": _boards.shelves("nfl", _likely)' in src


def test_the_board_and_its_shelves_are_built_from_one_list():
    """Calling the builder twice would let the page and its layout
    disagree about the same slate."""
    src = _src("engine", "pipeline.py")
    # THE CONTRACT, NOT THE CALL STRING. This matched
    # `_likely_board(results, ls, ls_watch)` exactly and went red when a
    # `census=` kwarg was added — a change that leaves the contract
    # untouched. What matters is that the builder runs ONCE and both
    # consumers read that one result.
    assert src.count("_likely_board(") == 2          # the def and one call
    assert '"most_likely": _likely,' in src
    assert '_boards.shelves("nfl", _likely)' in src


def test_the_renderer_draws_shelves():
    src = _src("web", "js", "app.js")
    assert "function likelyShelf(sh)" in src
    assert "state.data.board_shelves || []" in src


def test_it_falls_back_to_the_flat_list_on_an_older_payload():
    """A droplet serving yesterday's JSON must not render an empty page."""
    src = _src("web", "js", "app.js")
    # Re-anchored 2026-09-02: the shelves now pass the render gate
    # (showableLikelyRow) before drawing, so the assignment gained a
    # filter chain — and the home preview gained an identical-looking
    # assignment, so the anchor starts inside renderLikely itself. The
    # fallback it guards is unchanged.
    fn = src.index("function renderLikely()")
    body = src[fn:src.index("\nfunction ", fn + 10)]
    assert "const shelves = (state.data.board_shelves || [])" in body
    assert 'rows.map(likelyCard).join("")' in body, \
        "the flat-list fallback left renderLikely"


def test_the_host_is_not_a_card_grid_any_more():
    """It holds sections now, each with its own grid. Leaving `.cards` on
    the host made every shelf a single grid cell."""
    src = _src("web", "index.html")
    assert '<div class="cards" id="likely">' not in src
    assert '<div id="likely"></div>' in src



def test_the_jump_bar_puts_every_shelf_one_tap_from_the_top():
    """Ethan, 2026-09-02, circling a shelf head halfway down his phone:
    "we should put home run and hits and shit like that all at the top
    so we can not have too scroll and just click. Do the same thing for
    nfl and CFB and nba and wnba too." The chips are built from the
    SAME shelves array every sport publishes — no market name typed in
    the template, so each league grows its own chips and a new shelf
    arrives with one."""
    src = _src("web", "js", "app.js")
    fn = src.index("function renderLikely()")
    body = src[fn:src.index("\nfunction likelyShelf", fn)]
    assert 'data-jump="shelf-${escapeAttr(sh.key || "")}"' in body
    assert "scrollIntoView" in body
    assert "shelves.length > 1" in body, "one shelf needs no bar"
    shelf = src[src.index("function likelyShelf(sh)"):]
    shelf = shelf[:shelf.index("\nfunction ", 10)]
    assert 'id="shelf-${escapeAttr(sh.key || "")}"' in shelf
    for word in ("Home Runs", "Touchdowns", "Hits"):
        assert word not in body, f"{word} hardcoded — chips must be data-driven"

# --- the menu -------------------------------------------------------------
def _betting_group():
    src = _src("web", "index.html")
    at = src.index('data-group="research"')
    return src[at:src.index('data-fold="library"', at)]


def _order(group):
    import re
    return re.findall(r'data-(?:view|subtab)="([a-z]+)"', group)


def test_most_likely_outgrew_the_betting_menu():
    """It LED the group until 2026-08-31; the drawer rework promoted it
    (and Long Shots) to the always-open tier above every fold — Ethan's
    nightly six. Leading a folded group would now be a demotion."""
    html = _src("web", "index.html")
    pages = html[html.index('data-group="pages"'):html.index("sb-fold")]
    order = _order(pages)
    assert "likely" in order and "longshots" in order, order
    assert order.index("likely") < order.index("longshots")
    assert 'data-view="likely"' not in _betting_group()


def test_the_staking_board_sits_below_the_two_that_do_not_stake():
    """Same claim, new geometry: the two no-stake boards are tier-1;
    the staking board stays behind the Betting fold below them."""
    html = _src("web", "index.html")
    assert html.index('data-view="likely"') < html.index('data-view="edge"')
    assert html.index('data-view="longshots"') < html.index('data-view="edge"')
    assert 'data-view="edge"' in _betting_group()


def test_the_menu_order_matches_the_guide_it_never_read():
    """`boards.guide()` is "ordered by how much evidence stands behind
    them". The menu is now the same order for the three bet boards."""
    want = [b["key"] for b in boards.guide()]
    assert want == ["most_likely", "long_shots", "recommendations"], want
    # The three no longer share a group — likely and longshots are
    # tier-1 rows above the Betting fold (2026-08-31) — but their
    # DOCUMENT order still tells the guide's story: most evidence first.
    html = _src("web", "index.html")
    seen = sorted(("likely", "longshots", "edge"),
                  key=lambda k: html.index(f'data-view="{k}"'))
    assert seen == ["likely", "longshots", "edge"], seen


def test_the_two_prop_boards_no_longer_share_a_name():
    """"Player Props" described the market type, and Most Likely is
    player props too — the label said nothing that told them apart."""
    group = _betting_group()
    assert "Player Props" not in group
    assert "Value Bets" in group


def test_the_long_shot_hint_is_not_baseball_only():
    """"home-run darts" on a menu that also serves two football
    leagues, where these are touchdown prices."""
    assert "home-run darts" not in _betting_group()


# --- and they are on the page people actually land on ---------------------
# Ethan, 2026-08-30: "why are we not showing any of those bets on the main
# page... thats bets the user is really looking for." The shelves were
# built and then left entirely behind a menu row, so the landing page's
# only answer to "what should I bet" stayed the board with the weakest
# evidence behind it.
def test_the_main_page_has_a_host_for_the_likelihood_board():
    assert '<div id="likely-top"></div>' in _src("web", "index.html")


def test_it_is_drawn_by_its_own_renderer():
    assert "function renderLikelyTop()" in _src("web", "js", "app.js")


def test_the_renderer_runs_before_the_room_grouping():
    """`groupRecommended` reads what the renderers wrote to decide which
    rooms exist. A host filled after it is sorted into no room."""
    src = _src("web", "js", "app.js")
    assert (src.index("  renderLikelyTop();")
            < src.index("  groupRecommended();"))


def test_the_block_is_placed_in_the_boards_room():
    """In REC_ROOMS, which is the order a reader sees — not the DOM."""
    src = _src("web", "js", "app.js")
    at = src.index('["board", "Tonight')
    room = src[at:src.index('["gamebets"', at)]
    assert '"likely-top"' in room, room


def test_it_sits_above_the_slider_filtered_edge_cards():
    """The whole point of the placement. A normal bettor is shopping for
    what hits, and was only ever offered where the price is wrong."""
    src = _src("web", "js", "app.js")
    at = src.index('["board", "Tonight')
    room = src[at:src.index('["gamebets"', at)]
    assert room.index('"likely-top"') < room.index('"cards"')
    assert room.index('"likely-top"') < room.index('"rec-controls"')


def test_the_stadiums_lead_then_the_likelihood_board_then_everything():
    """Ethan's final order, 2026-08-31: "the stadiums should always be
    first the follows the most likely to hit." Venues set the scene, the
    board with the strongest evidence is the first read, and the edge
    strip stays demoted below the fold. The room order IS the page
    order."""
    src = _src("web", "js", "app.js")
    at = src.index('["board", "Tonight')
    room = src[at:src.index('["gamebets"', at)]
    assert room.index('"games-head"') < room.index('"likely-top"')
    assert room.index('"games-outer"') < room.index('"likely-top"')
    # ONE CONTIGUOUS PICKS-AND-RECORD AREA (Ethan, 2026-08-31 evening:
    # "just one area on the main page showing the picks and our record").
    # Likely picks, the summary tiles, the actual bet cards, the record —
    # in that order, with nothing between them. The strip is GONE from
    # the room: it duplicated best-bets and was the confusion by name.
    # …and refined the same night: "We should have the performance
    # under the top picks." Picks, then the proof, then the edge
    # summary beside the cards it counts.
    # …and once more, from his screenshot circling the four tool tiles:
    # "We should show this at the top of the page." The launcher row
    # opens the page; the venues follow it.
    order = ['"quick-tools"', '"games-head"',
             '"likely-top"', '"home-perf"', '"stats"', '"best-bets"']
    idx = [room.index(k) for k in order]
    assert idx == sorted(idx), order
    assert '"top-picks"' not in room, "the duplicate strip is back"


def test_the_demoted_strip_says_what_it_is():
    """Two pick sections on one page must name their difference. The
    strip is the EDGE board's shelf and says so."""
    src = _src("web", "js", "app.js")
    assert "Qellys’ edge picks" in src
    assert "where our number beats the price" in src


def test_the_likelihood_hero_wears_the_top_picks_name():
    """Ethan, 2026-08-31: "the most likely too hit should be labeled as
    our top picks, the we label what we WERE labeling as our top picks
    as our most edge picks." The crown follows the promotion: the board
    with the strongest evidence carries the site's headline name, and
    the subtitle keeps saying what the ranking actually is."""
    src = _src("web", "js", "app.js")
    at = src.index("function renderLikelyTop")
    block = src[at:at + 2400]
    assert "Qellys’ top picks" in block
    assert "most likely to hit" in block
    assert "Most likely to hit\n" not in block, "old title lingering"


def test_the_preview_reuses_the_shelves_rather_than_refiltering():
    """A second "top picks" filter is how two pages end up disagreeing
    about the same player."""
    src = _src("web", "js", "app.js")
    at = src.index("function renderLikelyTop()")
    body = src[at:src.index("function renderLikely()", at)]
    assert "state.data.board_shelves" in body
    assert "LIKELY_TOP_N" in body


def test_the_preview_links_through_to_the_full_board():
    src = _src("web", "js", "app.js")
    at = src.index("function renderLikelyTop()")
    body = src[at:src.index("function renderLikely()", at)]
    assert 'switchView("likely"' in body


def test_the_preview_carries_the_same_trust_line_as_the_full_page():
    """It says what it is and where it is recorded, in the same words —
    a shelf on the landing page must not become an unlabelled claim."""
    src = _src("web", "js", "app.js")
    at = src.index("function renderLikelyTop()")
    body = src[at:src.index("function renderLikely()", at)]
    assert 'boardGuide("most_likely")' in body


def test_an_empty_board_explains_itself_or_draws_nothing():
    """Re-anchored 2026-08-31. The old rule — empty board, no section —
    read as "the page is not loading" the night MLB/WNBA launched with
    an unmeasured rank store (Ethan's words, verbatim). Now: a sport
    whose build ships likely_census gets the heading and the census's
    own reason; a sport with no likelihood pipeline at all still draws
    nothing."""
    src = _src("web", "js", "app.js")
    at = src.index("function renderLikelyTop()")
    body = src[at:src.index("function renderLikely()", at)]
    assert "state.data.likely_census === undefined" in body
    assert 'host.innerHTML = "";' in body, "the no-pipeline arm must survive"
    assert "likelyEmptyWhy(state.data.likely_census)" in body


# --- the preview is rows, the depth is one tap away ------------------------
def test_the_home_preview_draws_rows_not_posters():
    """Ethan's screen recording, 2026-08-31: "this area takes up way too
    much space, I have to scroll so much down to see all the picks."
    Measured: each full card is nearly a phone screen, and the preview
    drew nine; the compact rows brought the whole section to 0.47
    screens. The full cards still exist — on the Top Picks page, where
    depth is the point."""
    src = _src("web", "js", "app.js")
    assert "function likelyRow(r)" in src
    i = src.index("function renderLikelyTop()")
    body = src[i:src.index("\nfunction ", i + 10)]
    assert "likelyRow" in body, "the preview lost its compact rows"
    assert "likelyCard" not in body, "the posters came back to the preview"
    # The full page keeps the full cards.
    j = src.index("function renderLikely()")
    full = src[j:src.index("\nfunction ", j + 10)]
    assert "likelyShelf" in full


def test_a_preview_row_is_a_door_not_a_dead_control():
    src = _src("web", "js", "app.js")
    assert 'data-goto="likely"' in src
    assert 'switchView("likely", true)' in src


def test_the_tonight_tab_leads_with_most_likely():
    """Ethan: "tonight's bets page should be the most likely to hit
    bets. Think about how your average better would think this app
    would be layed out." A bettor tapping Tonight asks who hits — then
    what we would stake."""
    src = _src("web", "js", "app.js")
    i = src.index("function renderTonight()")
    body = src[i:src.index("\nfunction ", i + 10)]
    # The reader moved into tonightPick (2026-09-05, Tonight across every
    # sport) — one reader for both pages; the tab's ORDER is still here.
    j = src.index("function tonightPick(")
    assert "d.most_likely" in src[j:src.index("\nfunction ", j + 10)]
    assert body.index("Most likely to hit tonight") \
        < body.index("Our edge bets")
    assert 'boardGuide("most_likely")' in body, "the trust line travels"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
