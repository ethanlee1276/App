"""The preservation contract for the Night Form redesign.

The redesign spec opens with a rule: *"this is a re-skin, not a rebuild.
Every number, chip, expander, disclaimer, empty state, and explanatory
paragraph currently on the site must still exist afterward. If a redesign
step would remove information, the redesign step is wrong."*

That rule needs teeth. Two layers give it teeth:

  1. `tools/inventory.mjs` renders all 17 views x 8 sports x 2 widths in a
     real browser and records every visible string, affordance and
     structural count into `docs/inventory-baseline.json` — 256 pages,
     3472 distinct strings. `--diff` reports anything that stopped
     rendering. That is the full net, and it needs a browser.

  2. This file, which runs in the ordinary suite with no browser. It pins
     the things that must never move regardless of how the visuals change:
     the verbatim honesty copy, the view list, the per-league nav
     configuration, and the shape of the baseline itself.

Layer 2 exists because layer 1 is only run deliberately. A redesign commit
that quietly drops the responsible-gambling line should fail `run_tests.py`,
not wait for someone to remember to re-harvest.

**Three corrections to the spec's own §1 inventory, all found by reading the
code rather than the site.** They are recorded here as tests so they cannot
be re-lost:

  - The spec lists **10** nav sections. The app has **17** views. `game`,
    `intel`, `fantasy`, `ufc`, `why` and `about` are missing from it
    entirely — and `game` is a whole per-game board with 87 components and
    51 strings nothing else on the site renders.
  - The spec says "WNBA omits Long Shots". **NBA omits it too**, and CFB
    omits Long Shots, Trending, Players *and* Rosters.
  - §1.6 and §1.9 are marked "not captured — inventory from the codebase".
    They are now captured, generated, in `docs/INVENTORY.md`.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")
# Source wraps at the margin, so "No model wins every night" is split across
# two lines in the file and reads as one sentence on the page. Match against
# collapsed whitespace, the same normalisation tools/inventory.mjs applies —
# otherwise this test pins the line-wrapping rather than the copy.
FLAT = re.sub(r"\s+", " ", HTML)
BASELINE = os.path.join(ROOT, "docs", "inventory-baseline.json")


# --- copy that may never be quietly shrunk ----------------------------------
# Spec §1.1 and §9: "stays verbatim and stays at current or greater
# prominence. Do not let a visual pass quietly shrink any of it."
VERBATIM = [
    "See the math. Know if it's working. Stay in the game.",
    "Model output, not betting advice",
    "every number is a probability, never a promise",
    "every pick is journaled and graded on the Record page",
    "No model wins every night",
    "anyone who says otherwise is selling something.",
    "21+. Please bet responsibly",
    "never money you can't afford to lose",
    "Problem gambling help: call or text",
    "1-800-GAMBLER",
    "(US, 24/7)",
]


def test_the_honesty_copy_is_present_verbatim():
    """These are the lines a betting site is tempted to shrink. A redesign
    is the most likely moment for it to happen by accident."""
    missing = [s for s in VERBATIM if s not in FLAT]
    assert not missing, f"honesty copy lost: {missing}"


def test_the_responsible_gambling_line_is_not_hidden():
    """Prominence, not just presence. `display:none`, `visibility:hidden`,
    `aria-hidden` or a zero opacity on this block would pass the test above
    while removing the line from the page."""
    i = HTML.index("1-800-GAMBLER")
    block = HTML[max(0, i - 700):i + 200]
    for bad in ("display:none", "display: none", "visibility:hidden",
                "visibility: hidden", 'aria-hidden="true"', "opacity:0",
                "opacity: 0"):
        assert bad not in block, f"the 1-800-GAMBLER block carries {bad}"


# --- the view list ----------------------------------------------------------
VIEWS = ["recommended", "live", "edge", "scanner", "longshots", "parlays",
         "trending", "players", "rosters", "standings", "record", "intel",
         "fantasy", "ufc", "why", "about"]


def test_every_view_still_exists():
    """The spec's nav list names ten. Losing one of the other six during a
    restyle would be silent — nothing links to `game` from the nav at all."""
    for v in VIEWS:
        assert f'"{v}"' in APP, f"{v} dropped out of VIEW_ORDER"
        assert f'id="view-{v}"' in HTML, f"#view-{v} dropped out of the shell"
    assert 'id="view-game"' in HTML, "the per-game board lost its container"


def test_the_game_board_is_still_reachable():
    """It has no nav tab — it is opened from a venue card and addressed as
    #game/<date>_<away>@<home>. A redesign that rebuilds the venue cards
    can orphan an entire page without touching it."""
    assert 'h.startsWith("game/")' in APP, "the #game/ route is gone"
    assert "function openGame(" in APP
    assert "const gameId = (g)" in APP, "the game id format changed"


# --- per-league nav configuration -------------------------------------------
def test_the_per_league_nav_configuration_is_intact():
    """The spec records only "WNBA omits Long Shots". The real table is
    wider, and a redesign that "simplifies" the nav to one list would give
    CFB four tabs that can only ever say "no data"."""
    block = APP[APP.index("const HIDDEN_VIEWS = {"):]
    block = block[:block.index("};")]
    assert 'nba: ["longshots"]' in block, "NBA's Long Shots exclusion is gone"
    assert 'wnba: ["longshots"]' in block, "WNBA's Long Shots exclusion is gone"
    # §9.1 caps UFC at two legs in one fight and every permitted construction
    # needs a method/distance market we do not price. A tab that can only ever
    # say so is worse than no tab.
    for sport in ("ufc", "polymarket", "fantasy"):
        assert f'{sport}: ["parlays"]' in block, (
            f"{sport}'s Parlay Zone exclusion is gone")
    for v in ("longshots", "trending", "players", "rosters"):
        assert v in block.split("cfb:")[1], f"CFB's {v} exclusion is gone"


def test_long_shots_survives_where_it_is_supposed_to():
    """Ethan asked for this one by name. It is a real page on five sports
    and it is hidden on three by design — both halves have to hold."""
    assert 'id="view-longshots"' in HTML
    assert '"longshots"' in APP
    inv = json.load(open(BASELINE, encoding="utf-8"))
    have = {k.split("|")[1] for k, v in inv["pages"].items()
            if k.split("|")[2] == "longshots" and v["strings"]}
    assert len(have) >= 5, f"Long Shots only renders for {sorted(have)}"


# --- the baseline itself ----------------------------------------------------
def test_the_baseline_exists_and_covers_everything():
    """A preservation net with a hole in it is worse than none, because it
    reports success over the part it cannot see."""
    assert os.path.exists(BASELINE), "run: node tools/inventory.mjs --out " + BASELINE
    inv = json.load(open(BASELINE, encoding="utf-8"))
    assert set(VIEWS) <= set(inv["views"]), "the baseline skips views"
    assert "game" in inv["views"], "the baseline skips the per-game board"
    assert len(inv["sports"]) == 8, f"only {len(inv['sports'])} sports harvested"
    assert 1280 in inv["widths"] and 390 in inv["widths"], \
        "the baseline is not measuring both a desktop and a phone"


def test_the_baseline_is_big_enough_to_be_the_real_site():
    """A truncated or half-failed harvest would still be valid JSON and
    would still diff clean against itself, so the harvest needs its own
    sanity check.

    Measured PER PAGE, not as a global total. The first version asserted
    ">= 3000 strings" and broke the moment the sample slate was regenerated
    with fewer picks — 2632 across 256 pages is obviously a real site, and
    the test was pinning how many bets the fixture happened to contain
    rather than whether the harvest worked. Density is the property that
    actually distinguishes a rendered page from an empty one."""
    inv = json.load(open(BASELINE, encoding="utf-8"))
    pages = inv["pages"]
    assert len(pages) >= 240, f"only {len(pages)} pages in the baseline"
    blank = [k for k, v in pages.items() if not v["strings"]]
    assert len(blank) < len(pages) * 0.1, \
        f"{len(blank)} pages harvested empty — the fixture server was probably down"
    live = [v for v in pages.values() if v["strings"]]
    thin = [n for n in (len(v["strings"]) for v in live) if n < 20]
    assert len(thin) < len(live) * 0.2, \
        f"{len(thin)} of {len(live)} pages rendered under 20 strings"
    assert min(len(v["classes"]) for v in live) >= 10, \
        "a page rendered with almost no markup — the stylesheet or JS failed"


def test_the_baseline_records_counts_not_just_presence():
    """Sets lose multiplicity. A page with eight `why?` chips that drops to
    one still contains the string "why?", so a set-difference reports
    nothing lost. The counts are what catch that."""
    inv = json.load(open(BASELINE, encoding="utf-8"))
    some = next(v for v in inv["pages"].values() if v["strings"])
    assert "counts" in some, "re-harvest: the baseline predates structural counts"
    for k in ("why", "card", "chip", "metric", "reason", "section"):
        assert k in some["counts"], f"the baseline does not count {k}"


def test_the_why_chips_are_counted_across_the_site():
    """Spec §1.2 calls these "a core differentiator" and requires every
    instance to survive. They are generated in JS and attached to section
    titles, so they are invisible to a grep of the markup."""
    assert 'btn.textContent = "why?"' in APP, "the why? chip stopped being built"
    inv = json.load(open(BASELINE, encoding="utf-8"))
    total = sum(v.get("counts", {}).get("why", 0)
                for k, v in inv["pages"].items() if k.startswith("1280|"))
    assert total >= 50, f"only {total} why? chips render across the desktop site"


def test_no_test_file_strands_tests_below_its_runner():
    """A test that never runs is worse than no test: it reports success.

    Every file here ends with an `if __name__ == "__main__"` block that
    collects `globals()` and runs it. Anything appended BELOW that block is
    defined after the block has already executed, so it is silently skipped
    while the file prints a confident pass count. Eleven tests in
    test_parlays.py sat there — every test of the ranking and the slate cap —
    plus eight more across four other files, all green, none running.

    Grep-level rule, checked for the whole suite at once, because the failure
    mode is invisible from inside the file it happens in.
    """
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    stranded = {}
    for name in sorted(os.listdir(here)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        src = open(os.path.join(here, name), encoding="utf-8").read()
        marker = 'if __name__ == "__main__"'
        if marker not in src:
            continue
        after = re.findall(r"^def (test_\w+)", src[src.index(marker):], re.M)
        if after:
            stranded[name] = after
    assert not stranded, (
        "tests defined below the __main__ runner never execute: "
        + "; ".join(f"{k}: {', '.join(v)}" for k, v in stranded.items()))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
