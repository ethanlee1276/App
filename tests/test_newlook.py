"""THE NEW LOOK — Ethan's render, shipped 2026-08-11, pinned here.

"go new look. i want everything you see besides the balance chip thing,
and the bet slip thing … copy my render and ship it fully. make sure to
do mobile as well."

What this file guards, in order of how much it matters:

1. THE LINE WE DID NOT CROSS. The render was drawn in the visual language
   of a sportsbook. The two elements Ethan excluded — the balance chip
   and the bet slip — are exactly the two that would make this site LOOK
   like it holds money. It never does: no "Place Bet", no deposits, no
   balance, no "To Win". If one of these strings ever ships, the page
   has started impersonating a book.

2. THE SHELL. One slim bar; every destination in a sidebar that IS the
   phone drawer (one element, two positions — never two copies to drift
   apart); the rail on Home only; the dashboard fed by the same payloads
   the board and the Record page already read.

3. THE SYSTEM UNDER THE SKIN. Glow and gradients are legal now, but only
   through the tokens, so every light on the site is the same light.
   High Confidence Mode is a REAL filter wired into the same gate every
   card list passes through — never a marketing toggle.

Run directly: `python3 tests/test_newlook.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "web/css/styles.css"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()


def _strip_comments(s):
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    return re.sub(r"<!--.*?-->", " ", s, flags=re.S)


def test_no_sportsbook_cosplay_ever():
    """The excluded-by-Ethan list, plus everything else that would imply
    this site holds money. Checked against the words a USER sees."""
    visible = _strip_comments(HTML) + _strip_comments(APP)
    for phrase in ("Place Bet", "place bet", "To Win $", "Deposit",
                   ">Balance<", "your balance", "Cash Out", "cash out"):
        assert phrase not in visible, f"sportsbook cosplay shipped: {phrase!r}"
    # And the bankroll page says out loud what it is not.
    i = HTML.index('id="view-bankroll"')
    assert "never holds a balance" in HTML[i:i + 1200]


def test_the_sidebar_is_the_drawer_not_a_second_menu():
    """One element, two positions. The phone drawer is the SAME #sidebar
    the desktop shows — transformed in, behind the same #menu-toggle and
    body.menu-open machinery — so the two can never disagree about what
    the site contains."""
    assert HTML.count('id="sidebar"') == 1
    i = CSS.index(".sidebar { position: fixed;")
    media = CSS.rindex("@media", 0, i)
    assert "max-width: 900px" in CSS[media:media + 40], "the drawer breakpoint moved"
    assert "body.menu-open .sidebar { transform: translateX(0)" in CSS
    # The bar's own nav hides on phones — the drawer carries everything.
    i = CSS.index("@media (max-width: 760px) {", CSS.index("NEW LOOK — 2026-08-11"))
    assert ".nav { display: none; }" in CSS[i:i + 900]


def test_every_destination_survived_the_redesign():
    """Nothing Ethan could reach before is more than one sidebar tap away
    now. Counted by the same data attributes the router binds."""
    sb = HTML[HTML.index('id="sidebar"'):HTML.index("</aside>")]
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba", "ufc", "intel",
                  "fantasy", "memes", "record", "lab", "mybets", "why", "about"):
        assert f'data-sport="{sport}"' in sb, f"{sport} fell out of the sidebar"
    for view in ("recommended", "live", "edge", "longshots", "parlays",
                 "futures", "standings", "trending", "players", "rosters",
                 "injuries", "scanner"):
        assert f'data-view="{view}"' in sb, f"{view} fell out of the sidebar"


def test_the_rail_belongs_to_home_only():
    """The render puts insights and live-now beside the dashboard. On
    every other page the content gets the room back."""
    fn = APP[APP.index("function syncRail("):]
    fn = fn[:fn.index("\n}")]
    assert 'state.view === "recommended"' in fn
    assert APP.count("syncRail") >= 3          # def + switchView + boot


def test_high_confidence_mode_is_a_real_filter():
    """The render's toggle, wired to the journal's own grade bands: ON
    filters the board and the Top Picks strip to quality >= 80 (A/A+) —
    inside passesFilters, the ONE gate every card list already passes
    through, so no list can forget to respect it."""
    fn = APP[APP.index("function passesFilters("):]
    fn = fn[:fn.index("\n}")]
    assert "hcmOn()" in fn and "80" in fn
    tp = APP[APP.index("function renderTopPicks("):]
    tp = tp[:tp.index("\n}")]
    assert "hcmOn()" in tp
    assert 'role="switch"' in HTML                 # a switch, announced as one


def test_glow_and_gradients_go_through_the_tokens():
    """The pivot legalized light — as a SYSTEM. Any raw gradient in the
    chrome outside the token definitions is freelancing. (The venue art
    in visuals.js draws its own skies; this audits the stylesheet.)"""
    # Every gradient must be DEFINED on a custom property (--grad-*,
    # --skeleton, …) — a gradient written directly into a rule is
    # freelancing outside the system.
    body = _strip_comments(CSS)
    for line in body.splitlines():
        if "gradient(" not in line:
            continue
        assert re.match(r"\s*--[a-z-]+:", line), f"raw gradient: {line.strip()[:70]}"


def test_the_dashboard_reads_the_real_journal():
    """The performance panel is the render's best idea and it must never
    become decoration: it fetches the SAME record.json the Record page
    renders, shows losses in red, and links to the full record."""
    fn = APP[APP.index("async function renderHomePerf("):]
    fn = fn[:fn.index("\n}")]
    assert 'fetch("data/record.json"' in fn
    assert "net_units" in fn and "roi" in fn
    assert 'href="#record"' in fn
    # No invented numbers: an empty journal renders NOTHING, not zeros.
    assert "host.innerHTML = \"\"" in fn.replace("''", '""')


def test_the_top_game_ribbon_is_earned_not_asserted():
    """The render's TOP GAME badge. Ours goes to the game with the most
    recommended bets tonight — one game, only when something is actually
    recommended."""
    fn = APP[APP.index("function renderGames("):]
    fn = fn[:fn.index("\n}")]
    assert "gameBetCount(g)" in fn
    assert "topN > 0" in fn


def test_the_greeting_never_fakes_a_name():
    """"Good evening, Alex" in the render — powered by the real account
    here, and a plain welcome when there is none. No placeholder names."""
    fn = APP[APP.index("function renderGreeting("):]
    fn = fn[:fn.index("\n}")]
    assert "acctState" in fn
    assert "Alex" not in APP, "the render's placeholder name shipped"


def test_the_wordmark_is_gold_and_the_interface_is_violet():
    """One gold element — the Qellys mark — on a violet interface. The
    render's split, pinned so neither leaks into the other's job."""
    i = CSS.index(".qmark", CSS.index("NEW LOOK — 2026-08-11"))
    assert "var(--gold)" in CSS[i:i + 200]
    i = CSS.index("--brand:", CSS.index("NEW LOOK — 2026-08-11"))
    assert "#8D5BF2" in CSS[i:i + 40]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
