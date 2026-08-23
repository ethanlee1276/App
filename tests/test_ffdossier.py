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
                APP.index("Mock draft simulator")]
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
                APP.index("Mock draft simulator")]
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
