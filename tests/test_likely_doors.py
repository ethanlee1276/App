"""A Most Likely card is a door to the prop page.

Ethan, 2026-09-02, on the Most Likely page: "we should be able too click
on these players and it takes us too a more detailed stat bar graph and
shit with more data and the versus button."

Source-level pins on web/js/app.js, the same way the other door tests
read the page: the card and the shelf row carry the door, the prop page
carries the versus block, and a card-wide player-page door does not
swallow the card's own controls.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(HERE, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(js, name):
    i = js.index(f"function {name}(")
    j = js.index("\nfunction ", i + 1)
    return js[i:j]


def test_the_most_likely_card_is_a_door():
    js = _js()
    card = _fn(js, "likelyCard")
    assert '<article class="card longshot"${likelyDoor(r)}>' in card
    door = _fn(js, "likelyDoor")
    assert "data-prop=" in door and "data-player-page=" in door
    assert "propOpenable(r) && findProp(id)" in door
    assert 'tabindex="0" role="link"' in door


def test_the_shelf_row_opens_the_same_pick():
    js = _js()
    row = _fn(js, "likelyRow")
    assert "${likelyOpen(r)}" in row and 'data-goto="likely"' not in row
    assert js.count('host.querySelectorAll("[data-open]")') == 2
    assert "function openFrom(spec)" in js
    opn = _fn(js, "openFrom")
    assert "openProp(target)" in opn and "openPlayerRoute(target)" in opn


def test_the_prop_page_carries_the_versus_block():
    js = _js()
    page = _fn(js, "renderPropPage")
    assert 'vsBlockHTML(r.player, state.sport, r.opponent || "")' in page
    assert "Versus" in page


def test_a_card_wide_player_door_yields_to_its_own_controls():
    js = _js()
    i = js.index('e.target.closest("[data-player-page]")')
    block = js[i:i + 400]
    assert 'closest("a, button, input, label, select, .chip")' in block


def test_every_door_reads_as_one():
    css = open(os.path.join(HERE, "web", "css", "styles.css"), encoding="utf-8").read()
    assert re.search(r"\[data-prop\],\s*\[data-player-page\],\s*\[data-open\]\s*\{\s*cursor:\s*pointer", css)


def test_the_row_identity_matches_the_prop_it_came_from():
    """`likely.from_prop` must keep player, market, side and line exactly,
    because that is the id the door looks the prop up by."""
    from engine import likely as L
    row = {"player": "Amon-Ra St. Brown", "team": "DET", "opponent": "NO",
           "market": "rec_yds", "market_label": "Receiving Yards",
           "side": "OVER", "line": 77.5, "book": "FanDuel", "odds": -114,
           "hit_prob": 0.56, "fair_prob": 0.50, "projection": 93.7,
           "ev_per_unit": 0.02, "has_market": True, "reasons": ["x"],
           "recent_values": [80, 60, 90, 50], "date": "2026-09-13"}
    got = L.from_prop(row, lambda m: True)
    assert got is not None
    assert (got["player"], got["market"], got["side"], got["line"]) == \
        (row["player"], row["market"], row["side"], row["line"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
