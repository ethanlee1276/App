"""The drawer is two tiers: the nightly six, then folded reference.

Ethan, 2026-08-31: "The site is just feeling super confusing and hard
to like navigate" — then "Go" on the proposal: the five things a bettor
uses nightly big and first, everything else folded under group heads.

Measured in Chromium at 390×844 before touching anything: 27 visible
rows, 1292px of drawer — 1.53 phone screens. After: 21 rows, 1051px,
1.25 screens, and everything above the first fold head is tier-1:

    Dashboard · Top Picks · Long Shots · Live Now · My Bets · Record

Four groups fold beneath them — Betting, Library, My Book, Proof —
each a single line until opened, remembered per reader (qb_sb_folds).
Every destination survives; nothing was deleted, only weighted.

Run directly: `python3 tests/test_drawer_tiers.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as f:
    HTML = f.read()

SIDEBAR = HTML[HTML.index('class="sidebar"'):HTML.index('id="sb-hcm"')]
TIER1 = SIDEBAR[SIDEBAR.index('data-group="pages"'):SIDEBAR.index("sb-fold")]


def _labels(seg):
    rows = re.findall(
        r'<button[^>]*class="(?:nav|sport)-btn sb-item[^"]*"[^>]*>(.*?)</button>',
        seg, re.S)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", r)).strip()
            for r in rows]


def test_the_nightly_six_lead_and_nothing_else_does():
    assert _labels(TIER1) == ["Dashboard", "Top Picks", "Long Shots",
                              "Live Now", "My Bets", "Record"], _labels(TIER1)


def test_every_group_below_the_tier_ships_folded():
    """A fold that ships open is a tier-1 row wearing a heading. All
    four reference groups start shut; the reader's own toggle is what
    opens them, and qb_sb_folds is what remembers it."""
    for fold in ("research", "library", "tools", "proof"):
        i = SIDEBAR.index(f'data-fold="{fold}"')
        assert 'aria-expanded="false"' in SIDEBAR[i:i + 240], fold
        assert f'data-group="{fold}" hidden' in SIDEBAR, fold


def test_every_destination_survived_the_rework():
    """The preservation rule: weighting is never deleting. Every view
    and tool page reachable before is reachable now."""
    for view in ("recommended", "live", "likely", "longshots", "edge",
                 "scanner", "futures", "injuries", "weather", "trending",
                 "rosters", "players", "standings", "alerts", "streak",
                 "bankroll"):
        assert f'data-view="{view}"' in SIDEBAR, view
    for tool in ("mybets", "record", "lab", "methodology", "status",
                 "why", "about"):
        assert f'data-sport="{tool}"' in SIDEBAR, tool


def test_the_promoted_rows_left_their_old_groups():
    """A row in two places is the duplication the home page just paid
    to remove, moved into the menu."""
    for grp, gone in (("research", 'data-view="likely"'),
                      ("research", 'data-view="longshots"'),
                      ("tools", 'data-sport="mybets"'),
                      ("proof", 'data-sport="record"')):
        i = SIDEBAR.index(f'data-group="{grp}"')
        j = SIDEBAR.find("sb-fold", i)
        assert gone not in SIDEBAR[i:j if j != -1 else len(SIDEBAR)], \
            (grp, gone)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
