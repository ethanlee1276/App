"""The fantasy player dossier — Ethan, 2026-08-18: "we should be able
too click on players and it will show us useful fantasy information for
that player."

The disciplines pinned here:

  * EVERY SURFACE IS A DOOR. Usage rows, trade cards, the kit's board,
    tiers and sleepers, the rankings table and its disagreement rows,
    camp rows, the waiver pulse and the mock draft all carry the
    data-dossier hook — a page where SOME names open and some silently
    don't teaches the reader to stop tapping.
  * ONE BINDING, at the document. The fantasy page re-renders constantly;
    a per-render binding stacks listeners and a per-element one dies
    with the innerHTML.
  * SECTIONS ONLY WHERE THE DATA IS. A dossier heading over an empty
    panel is a guess wearing a title — absent surfaces are omitted, and
    a player nobody's board knows says so in one sentence.
  * THE CROSS-OFF KEEPS ITS ATTRIBUTE. The kit rows' data-ffp belongs to
    the Sleeper draft-sync (normalised names, crossed off when taken);
    the dossier rides data-dossier beside it, raw name, and neither may
    absorb the other.

Run directly: `python3 tests/test_ffdossier.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()


def test_every_fantasy_surface_is_a_door():
    n = APP.count('data-dossier="${escapeAttr(')
    assert n >= 9, f"only {n} surfaces carry the hook"
    # The named ones, by their anchoring class.
    for anchor in ('class="ff-who" data-dossier',
                   'class="card-id" data-dossier',
                   'class="os-team mk-idrow" data-dossier',
                   'class="dl-main" data-dossier',
                   'class="rank-name" data-dossier',
                   'class="rank-fight-row" data-dossier',
                   'class="mk-id" data-dossier'):
        assert anchor in APP, f"{anchor} lost its door"


def test_the_kit_cross_off_and_the_dossier_coexist():
    assert APP.count('data-ffp="${escapeHtml(ffNorm(r.player))}" '
                     'data-dossier="${escapeAttr(r.player)}"') == 3, \
        "the three kit rows must carry BOTH attributes"


def test_one_binding_at_the_document():
    i = APP.index("function openFfDossier(")
    block = APP[APP.index("The fantasy player dossier"):
                APP.index("/* ---------------- Mock draft simulator ")]
    assert 'document.addEventListener("click"' in block
    assert 'closest("[data-dossier]")' in block.replace("&& e.target.", "")
    # And NOT rebound inside the fantasy renderer.
    j = APP.index("host.innerHTML = _ffLead")
    assert "data-dossier" not in APP[j:j + 2400].split("subtabbedHTML")[0]


def test_sections_render_only_where_the_data_is():
    i = APP.index("function ffDossierHTML(")
    body = APP[i:APP.index("async function _ffDossierCharts", i)]
    assert "if (k && k.proj != null)" in body
    assert "const bs = info.buy || info.sell;" in body
    assert "if (info.camp)" in body and "if (info.move)" in body
    assert "No fantasy read on him this season" in body, \
        "the empty dossier must say so instead of showing bare headings"


def test_the_charts_degrade_honestly_without_a_db():
    i = APP.index("async function _ffDossierCharts(")
    body = APP[i:APP.index("function openFfDossier", i)]
    # THE API, NOT THE CALL'S EXACT CHARACTERS. This pinned
    # `leagueLogs(name)` and so went red when the call gained the league
    # it should always have named — a change that FIXED a real bug (a
    # dossier opened from the MLB board asked the baseball endpoint for a
    # wide receiver). The contract is the API and the player.
    assert "leagueLogs(name" in body, \
        "the charts must ride the same log API the search uses"
    # And fantasy is always football, whatever tab the reader came from.
    assert 'leagueLogs(name, "nfl")' in body, \
        "the dossier inherits whichever league the visitor was browsing"
    assert "No game logs on this machine" in body


def test_the_overlay_closes_three_ways():
    block = APP[APP.index("The fantasy player dossier"):
                APP.index("/* ---------------- Mock draft simulator ")]
    assert "e.target === ov" in block, "scrim tap must close"
    assert 'closest(".ffd-close")' in block, "the button must close"
    # THE BEHAVIOUR, NOT THE CHARACTERS. This pinned the exact string
    # `Escape") closeFfDossier()`, so it broke when a second dialog
    # started sharing the handler — a change that made Escape close MORE
    # things, which is the direction this test wants.
    esc = [l for l in block.splitlines()
           if 'e.key === "Escape"' in l and "closeFfDossier()" in l]
    assert esc, "Escape no longer closes the dossier"


def test_the_dossier_is_styled():
    for sel in ("#ffd-overlay {", ".ffd-card {", ".ffd-stats {",
                ".ffd-sect + .ffd-sect {", "[data-dossier] { cursor: pointer"):
        assert sel in CSS, f"{sel} is unstyled"
    assert "body.ffd-open { overflow: hidden; }" in CSS, \
        "the page must not scroll under the sheet"


# ------------------------------------------------- the Dynamic Island

def _css():
    return open(os.path.join(ROOT, "web", "css", "styles.css"),
                encoding="utf-8").read()


def _rule(sel):
    css = _css()
    i = css.index(sel + " {")
    return css[i:css.index("}", i)]


def test_the_sheet_can_never_be_drawn_under_the_island():
    """Ethan, 2026-09-09, with a photo of Cam Skattebo's profile: the
    name, the team, the bio row and the close button all sitting under
    the status bar and the Dynamic Island.

    THE FIX IS THE CONTAINING BLOCK, and it took three goes to get there.

    First I padded the overlay, reasoning that a flex container whose
    content box starts below the island cannot place a child above it.
    Measured: it clamps nothing. A flex item taller than its container
    overflows straight past the container's padding — a 5000px card under
    a 200px-padded overlay sat at top −4068.

    Second I subtracted the inset from the card's `max-height` in `dvh`,
    because `vh` on iOS is the LARGE viewport and a bottom-anchored sheet
    sized in it overflows off the top. That was right about the units and
    still left the sheet's size a calculation that had to come out
    correct on a device I cannot run.

    This is neither. `top` and `bottom` give the overlay a DEFINITE
    height — the visible area minus the island — and a percentage
    max-height on the card resolves against exactly that box. The card
    cannot be taller than the room under the island because there is no
    arithmetic left to get wrong, and no viewport unit involved at all.
    """
    for sel in ("#ffd-overlay", "#pk-overlay"):
        rule = _rule(sel)
        assert "top: env(safe-area-inset-top" in rule, \
            f"{sel} still starts at the top of the screen"
        assert "bottom: 0" in rule and "inset: 0" not in rule, \
            f"{sel} is back to inset:0, which puts the island inside it"


def test_no_sheet_is_sized_against_a_viewport_it_cannot_measure():
    """A percentage of the overlay is the whole point. Any `vh` or `dvh`
    here is a return to sizing against something iOS defines differently
    from what is on screen."""
    import re
    css = _css()
    for m in re.finditer(r"max-height:\s*([^;]+);", css):
        head = css.rfind("{", 0, m.start())
        sel = css[css.rfind("}", 0, head) + 1:head].strip().splitlines()[-1].strip()
        if "ffd-card" in sel or "pk-card" in sel:
            assert "vh" not in m.group(1), (sel, m.group(1))
            assert "%" in m.group(1), (sel, m.group(1))


def test_the_home_indicator_is_still_accounted_for():
    """It always was — the bottom inset was in the padding and the top
    was not. Regressing it while fixing the other end would be a poor
    trade."""
    for sel in (".ffd-card", ".pk-card"):
        assert "env(safe-area-inset-bottom" in _rule(sel), sel


def test_the_island_is_cleared_in_a_real_browser():
    """The property, executed, with an island substituted for the `env`
    that Chromium reports as zero — INCLUDING the overflow case, which is
    the one my first fix passed by inspection and failed in fact.

    Opt-in like the other browser tests: `QB_BROWSER_TESTS=1`.
    """
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck

    chromium = os.environ.get(
        "CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    srv, port = rendercheck._serve()
    ISLAND = 59
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage",
                           "--disable-gpu"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            page = browser.new_page(viewport={"width": 430, "height": 932},
                                    is_mobile=True, has_touch=True)
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
            page.wait_for_timeout(1200)
            page.add_style_tag(content=f"#ffd-overlay{{top:{ISLAND}px}}")
            got = page.evaluate("""(island) => {
              // BUILT BY HAND, because the overlay is created on the
              // first open and this fixture has no fantasy payload to
              // open one from. The geometry is the claim; the contents
              // are not. Same ids and classes, so the same CSS applies.
              const ov = document.createElement('div');
              ov.id = 'ffd-overlay';
              ov.className = 'open';
              ov.innerHTML = '<div class="ffd-card ffd-full">'
                + '<div style="height:4000px">tall</div></div>';
              document.body.appendChild(ov);
              const r = ov.querySelector('.ffd-card').getBoundingClientRect();
              return { top: Math.round(r.top), height: Math.round(r.height),
                       island: island };
            }""", ISLAND)
            browser.close()
    finally:
        srv.shutdown()
    assert got["top"] >= got["island"], (
        "content four thousand pixels tall pushed the sheet under the "
        f"island: {got}")
    # …and it is a SHEET, not a takeover: some of the dimmed page shows.
    assert got["top"] > got["island"], got

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
