"""The preservation contract for the Night Form redesign.

The redesign spec opens with a rule: *"this is a re-skin, not a rebuild.
Every number, chip, expander, disclaimer, empty state, and explanatory
paragraph currently on the site must still exist afterward. If a redesign
step would remove information, the redesign step is wrong."*

That rule needs teeth. Two layers give it teeth:

  1. `tools/inventory.mjs` renders all 24 views x 8 sports x 2 widths in a
     real browser and records every visible string, affordance and
     structural count into `docs/inventory-baseline.json` — 369 pages,
     2424 distinct strings. `--diff` reports anything that stopped
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
# Reworded 2026-08-04 at the owner's direction — the old lines were clipped
# slogans ("never money you can't afford to lose" had lost its verb) and
# read as nonsense to a fresh visitor. The CONTENT contract is unchanged:
# model-output-not-advice, graded in public, no model wins every night,
# 21+, bet responsibly, and the helpline. These pins now hold the clear
# wording to the same standard the old wording was held to.
VERBATIM = [
    "This site publishes a model's estimates. It is not betting advice.",
    "Every number here is a probability, not a promise.",
    "graded in public on the Record page",
    "No model wins every night",
    "be suspicious of anyone who claims theirs does",
    "You must be 21 or older to bet.",
    "never bet money you cannot afford to lose",
    "free and confidential help is available 24/7 in the US",
    "1-800-GAMBLER",
]


def test_the_honesty_copy_is_present_verbatim():
    """These are the lines a betting site is tempted to shrink. A redesign
    is the most likely moment for it to happen by accident.

    Compared with the apostrophe normalised, because the guard is about
    the WORDS. It fired correctly when the copy was set with a typographic
    apostrophe — the sentence was intact and only the glyph had changed —
    and pinning either form would make the next pass through the copy
    break it in whichever direction it went. Everything else here stays a
    literal match."""
    flat = FLAT.replace("\u2019", "'")
    missing = [s for s in VERBATIM if s.replace("\u2019", "'") not in flat]
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


def test_every_routable_view_is_actually_drawn_by_the_router():
    """A view in VIEW_ORDER that nothing renders is a blank page.

    FOUND ON THE LIVE SITE, by typing the URL. `paywall` and `checkout`
    were added as views and reached only by a button that rendered them
    first — the wall going up, or "See the plans". So the router switched
    to an empty <section> for anyone who navigated to #paywall directly
    or followed a link to it, and showed nothing at all. No error, no
    console message: an empty div is silent.

    Every view either has a render call in switchView, or is named below
    with the reason it does not need one. Adding a view now means
    choosing which.
    """
    # Drawn by the shared board render rather than a per-view call: these
    # are the sport boards, and `load()` fills them all at once.
    SHARED = {"recommended", "live", "edge", "scanner", "longshots",
              "futures", "trending", "players", "prop", "game"}

    i = APP.index("const VIEW_ORDER = [")
    literal = APP[i:APP.index("]", i)]
    views = re.findall(r'"([a-z]+)"', literal)
    assert len(views) > 20, "VIEW_ORDER did not parse — this test is blind"

    # TO THE NEXT TOP-LEVEL DECLARATION, not to the first `\n}` — the
    # function contains nested blocks that close at column 0's indent
    # depth, so the naive slice ended twenty lines in and reported every
    # view below that point as missing.
    # `_switchViewNow`, NOT `switchView`. The latter is a four-line
    # wrapper that picks a slide direction and hands off; the dispatch
    # lives in the one it calls. Slicing the wrapper found no render
    # calls at all and reported every view as missing, which is the shape
    # of a test that is measuring the wrong thing rather than a codebase
    # that is broken.
    j = APP.index("function _switchViewNow(")
    rest = APP[j + 10:]
    ends = [m.start() for m in re.finditer(r"\n(?:async )?function ", rest)]
    router = rest[:ends[0]] if ends else rest
    missing = [v for v in views
               if v not in SHARED and f'name === "{v}"' not in router]
    assert not missing, (
        f"these views are routable and nothing draws them: {missing}. "
        "Add a render call in switchView, or add the view to SHARED here "
        "with the reason it does not need one.")


# --- the view list ----------------------------------------------------------
#  weather + alerts joined 2026-08-12 (Ethan's Zeno sidebar render:
#  "I like all the page options it offers so let's follow suit").
VIEWS = ["weather", "alerts",
         "recommended", "live", "edge", "scanner", "longshots",
         "trending", "players", "rosters", "standings", "record", "intel",
         "fantasy", "ufc", "why", "about"]


def test_every_view_still_exists():
    """The spec's nav list names ten. Losing one of the other six during a
    restyle would be silent — nothing links to `game` from the nav at all.
    "parlays" left this list 2026-08-11 ON PURPOSE (Ethan: "ditch the
    parlay zone screen but keep the same rules") — the tickets moved to
    Parlay Mode on Home, and test_parlays.py owns that contract; the
    assert below keeps the CONTENT alive rather than the dead page."""
    for v in VIEWS:
        assert f'"{v}"' in APP, f"{v} dropped out of VIEW_ORDER"
        assert f'id="view-{v}"' in HTML, f"#view-{v} dropped out of the shell"
    assert 'id="view-game"' in HTML, "the per-game board lost its container"
    assert 'id="parlays-body"' in HTML, "the parlay tickets lost their container"


def test_every_routable_view_is_in_VIEW_ORDER():
    """Parse the list, don't grep for the name.

    `test_every_view_still_exists` above asserts `f'"{v}"' in APP` — true
    for any name that appears ANYWHERE in a 14,000-line file. "mybets"
    appears a dozen times (STANDALONE_MODES, the brand table, the sync
    keys), so that check stayed green for weeks while `mybets` was missing
    from VIEW_ORDER entirely. A substring test over a whole file cannot
    tell you which list a string is in.

    What the omission cost: `switchView` computes the slide direction as
    `VIEW_ORDER.indexOf(target) - VIEW_ORDER.indexOf(current)`, and a
    missing name gives -1 — not "unknown" but "left of everything". So
    My Bets always animated in from the LEFT, as though you had gone
    backwards, while its own neighbours Record and The Lab came from the
    right. Measured in a browser before and after.

    The view still switched, which is why nothing caught it: the whole
    symptom is a 200ms animation pointing the wrong way.
    """
    order = re.search(r"const VIEW_ORDER = \[(.*?)\];", APP, re.S)
    assert order, "VIEW_ORDER is gone or no longer a flat literal"
    names = [s.strip().strip('"') for s in order.group(1).split(",") if s.strip()]
    assert len(names) == len(set(names)), "a view is listed twice"

    routable = set(re.findall(r'id="view-([a-z0-9_-]+)"', HTML))
    missing = sorted(routable - set(names))
    assert not missing, (
        f"routable but absent from VIEW_ORDER, so they animate backwards: "
        f"{missing}")

    phantom = sorted(set(names) - routable)
    assert not phantom, (
        f"in VIEW_ORDER with no #view-* container — switchView would throw "
        f"on null: {phantom}")


def test_the_record_is_a_standalone_page_not_a_sport_tab():
    """Promoted by request: the Record holds the receipts for every sport
    plus the whole learning loop, and it was buried twelfth in each
    sport's tab row. It now enters through the switcher's own "The Book"
    group like Prediction Mkts and Fantasy do — and the tab row must NOT
    grow it back, or the site has two doors disagreeing about what kind
    of page it is."""
    assert 'data-sport="record"' in HTML, "the switcher lost The Book"
    # The group's NAME moved with the Zeno sidebar (2026-08-12): "The
    # Book" items live under My Tools now (data-group="tools"). The
    # contract this test protects is unchanged and asserted above/below:
    # Results enters as a standalone tool, never a per-sport tab.
    assert 'data-group="tools"' in HTML
    assert '<button class="nav-btn" data-view="record"' not in HTML, \
        "Record is back in the per-sport tab row"
    assert '"record"' in APP.split("STANDALONE_MODES = ")[1][:120], \
        "record is not a standalone mode"
    # The front door opens on the WHOLE record — the cross-sport scope
    # where the learning ladder reads unscoped.
    assert '_recordScope = "all"' in APP
    # And the masthead ROI link routes through the same standalone door.
    assert 'enterStandaloneMode("record")' in APP


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
    # Membership, not the exact list — the same principle the wnba check
    # below states. NBA's exclusions grew "weather" on 2026-08-12 (an
    # indoor league can't have a weather page), and the equality form of
    # this assert read that as the Long Shots rule breaking.
    nba = [l for l in block.splitlines() if l.strip().startswith("nba:")]
    assert nba and '"longshots"' in nba[0], "NBA's Long Shots exclusion is gone"
    # Membership rather than the exact list: the WNBA also has no futures
    # board, and an equality check fails whenever an unrelated tab joins the
    # exclusion, which looks like this preservation rule breaking when it
    # has not.
    wnba = [l for l in block.splitlines() if l.strip().startswith("wnba:")]
    assert wnba and '"longshots"' in wnba[0], "WNBA's Long Shots exclusion is gone"
    # §9.1 caps UFC at two legs in one fight and every permitted construction
    # needs a method/distance market we do not price. A tab that can only ever
    # say so is worse than no tab.
    for sport in ("ufc", "polymarket", "fantasy"):
        line = [l for l in block.splitlines() if l.strip().startswith(f"{sport}:")]
        assert line and '"parlays"' in line[0], (
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


def test_the_generated_inventory_matches_the_baseline_it_is_generated_from():
    """`docs/INVENTORY.md` says "generated, do not hand-edit" at the top and
    is the readable half of the §1 contract — the half anyone actually
    opens. It is generated from `docs/inventory-baseline.json`, but by a
    script someone has to remember to run, and re-harvesting the baseline
    is the memorable step.

    Nobody ran it. The baseline moved to 369 pages and 24 views while the
    document went on describing 266 pages and 17, so eight whole views —
    futures, injuries, weather, alerts, bankroll, lab, memes, mybets —
    were absent from the contract that is supposed to say what must
    survive. A preservation net that silently stops listing what it covers
    is the exact failure `tools/inventory_doc.py` was written to prevent,
    turned on the tool itself.

    So make it a property of the repo rather than of someone's memory: the
    document must be what the generator produces from the checked-in
    baseline, on this machine, with no browser and no harvest."""
    import importlib.util
    import tempfile

    src = os.path.join(ROOT, "tools", "inventory_doc.py")
    spec = importlib.util.spec_from_file_location("inventory_doc", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with tempfile.TemporaryDirectory() as tmp:
        # Point the generator at scratch, never at the repo: a test that
        # rewrites the file it is checking always passes.
        mod.OUT = os.path.join(tmp, "INVENTORY.md")
        mod.main()
        fresh = open(mod.OUT, encoding="utf-8").read()

    committed = _read("docs", "INVENTORY.md")
    assert fresh == committed, (
        "docs/INVENTORY.md is stale against docs/inventory-baseline.json — "
        "run: python3 tools/inventory_doc.py")


def test_no_test_reads_the_live_board_or_the_real_database():
    """Three separate tests passed here and failed on the machine that runs
    the builds, all for the same reason: they read state that belongs to a
    machine rather than to the repo.

      * test_why_empty_scope shelled out and read whatever board was on disk
      * test_mlb_quality asserted a hard pick count from a pipeline that
        consults a locally-fitted calibration file
      * test_why_pick copied the REAL board aside, edited it, and put it back
        — on the machine that runs the builds, with launch.py possibly
        mid-refresh
      * test_prop_page read web/data/recommendations.json for its `logs`
        array, so it was green on the laptop and red in every clone

    Each looked like a code defect and was really a difference in tonight's
    games. A test is allowed to touch these paths; it is not allowed to touch
    them without building its own copy first, and tempfile is the tell.

    THE FOURTH ONE SLIPPED THROUGH THIS GUARD, which is why the scan is no
    longer one line at a time. test_prop_page named the path on one line and
    opened it on the next:

        path = os.path.join(ROOT, "web", "data", "recommendations.json")
        rows = json.load(open(path, encoding="utf-8"))["recommendations"]

    Neither line carries both halves, so a per-line AND matched nothing —
    and splitting a long call over two lines is the normal way to write it,
    not a way to dodge the check. So a name bound to a live path is now
    followed to wherever it is read.
    """
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    # The path has to be USED, not merely mentioned. A test that asserts a
    # string is absent from launch.py's source names the path without ever
    # opening it, and flagging that is noise that gets a guard switched off.
    live = re.compile(r'"web",\s*"data"|web/data|DEFAULT_DB|calibration\.json')
    uses = re.compile(r'open\(|read_text|json\.load|connect\(|cwd=_?ROOT')
    # `x = <a live path>` — the binding that carries the path to the read.
    binds = re.compile(r'^\s*(\w+)\s*=\s*(.+)$')
    offenders = {}
    for name in sorted(os.listdir(here)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        src = open(os.path.join(here, name), encoding="utf-8").read()
        lines = src.splitlines()
        hits = [ln for ln in lines if live.search(ln) and uses.search(ln)]
        # Names bound to a live path, then read somewhere else in the file.
        # The lookbehind keeps a variable called `path` from matching the
        # `path` inside `os.path.join`, which flagged three innocent lines.
        carriers = [re.compile(r'(?<![\w.])' + re.escape(m.group(1)) + r'\b')
                    for ln in lines
                    if (m := binds.match(ln)) and live.search(m.group(2))]
        hits += [ln for ln in lines
                 if uses.search(ln) and any(c.search(ln) for c in carriers)
                 and not (binds.match(ln) and live.search(ln))]
        if not hits:
            continue
        # A fixture of its own is the licence. tempfile/mkdtemp means the
        # test wrote the thing it is about to read; calibrate.disabled()
        # means it switched the machine-local input off deliberately.
        if ("tempfile" in src or "mkdtemp" in src
                or "calibrate.disabled" in src or "calibrate import" in src):
            continue
        offenders[name] = "touches live data with no fixture of its own"
    assert not offenders, (
        "these tests read machine-local state directly, so they measure the "
        "machine: " + "; ".join(f"{k} — {v}" for k, v in offenders.items()))


def test_no_test_file_strands_tests_below_its_runner():
    """A test that never runs is worse than no test: it reports success.

    Every file here ends with an `if __name__ == "__main__"` block that
    collects `globals()` and runs it. Anything appended BELOW that block is
    defined after the block has already executed, so it is silently skipped
    while the file prints a confident pass count. Eleven tests in
    test_parlays.py sat there — every test of the ranking and the slate cap —
    plus eight more across four other files, all green, none running.

    Checked for the whole suite at once, because the failure mode is
    invisible from inside the file it happens in.

    FOUND BY THE PARSE TREE, after the grep version accused this very
    file. It located the runner with the FIRST occurrence of the marker
    string, and the marker appeared here as a string literal inside this
    test — so every test written below this one read as stranded, and the
    fix on offer was to keep reordering tests around a false positive.
    `ast` finds the real `if` statement at module level and nothing that
    merely quotes it.
    """
    import ast
    here = os.path.dirname(os.path.abspath(__file__))

    def runner_line(tree):
        """Line of the module-level `if __name__ == "__main__":`, if any."""
        for node in tree.body:
            if not isinstance(node, ast.If):
                continue
            t = node.test
            if (isinstance(t, ast.Compare)
                    and isinstance(t.left, ast.Name)
                    and t.left.id == "__name__"
                    and any(isinstance(c, ast.Constant) and c.value == "__main__"
                            for c in t.comparators)):
                return node.lineno
        return None

    stranded = {}
    for name in sorted(os.listdir(here)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        src = open(os.path.join(here, name), encoding="utf-8").read()
        tree = ast.parse(src, filename=name)
        line = runner_line(tree)
        if line is None:
            continue
        after = [n.name for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name.startswith("test_") and n.lineno > line]
        if after:
            stranded[name] = after
    assert not stranded, (
        "tests defined below the __main__ runner never execute: "
        + "; ".join(f"{k}: {', '.join(v)}" for k, v in stranded.items()))


def test_no_bare_abs_against_abs_assertion_survives():
    """`assert abs(a) < abs(b)` passes on a last-decimal difference.

    Task #84, the sidebias flake class. That shape says "this effect is
    smaller than that one" and accepts 0.4999 against 0.5000 as proof —
    which is the signature of a real effect and of float noise alike, so
    the test goes green either way and goes red on a rounding change
    nobody made deliberately.

    Every one of the eight in this repo was MEASURED before a margin was
    set, and the margins came from the measurements rather than from
    taste: the tightest genuine gap was 0.913 against 1.217, the widest
    0.218 against 3.287. A 10% floor therefore sits well inside every
    real effect here and well outside the last-decimal band.

    READ WITH `ast`, NOT `grep`, and the difference is the whole test. A
    line-regex flagged `abs(a - 1) < 1e-6 and abs(b - 1) < 1e-9` in
    test_rescale.py and test_team_context.py — two absolute-tolerance
    checks sharing a line, where the right-hand side of each comparison
    is a constant. Both are correct as written. What makes the flake is
    an abs() *as the thing being compared against*, and only the parse
    tree can tell that from an abs() that merely appears later on the
    line. A guard with false positives gets switched off.

    It lives with the other cross-file shape checks because no individual
    test can assert that its neighbours are not flaky.
    """
    import ast
    here = os.path.dirname(os.path.abspath(__file__))

    def is_bare_abs(node):
        """A direct `abs(...)` call, with nothing done to it.

        `abs(x) * 0.9`, `abs(x) + 0.05` and `abs(x) / 2` are BinOps, so
        they fall through here — which is exactly the licence: a margin
        makes the comparison say something a last decimal cannot satisfy.
        """
        return (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "abs")

    bare = []
    for name in sorted(os.listdir(here)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        src = open(os.path.join(here, name), encoding="utf-8").read()
        for node in ast.walk(ast.parse(src, filename=name)):
            if not isinstance(node, ast.Assert):
                continue
            for cmp_ in [n for n in ast.walk(node.test)
                         if isinstance(n, ast.Compare)]:
                ops = cmp_.ops
                if len(ops) != 1 or not isinstance(
                        ops[0], (ast.Lt, ast.Gt, ast.LtE, ast.GtE)):
                    continue
                if is_bare_abs(cmp_.left) and is_bare_abs(cmp_.comparators[0]):
                    bare.append(f"{name}:{cmp_.lineno}")
    assert not bare, (
        "bare abs-vs-abs assertions pass on a last-decimal difference; "
        "measure both values and give the comparison a margin (task "
        "#84): " + ", ".join(bare))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
