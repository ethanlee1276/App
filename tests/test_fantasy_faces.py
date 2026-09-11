"""Faces on the fantasy page — Ethan, 2026-08-18, twice in one day:
"Make sure all spots have head shots" and then, after the dossier and
mock draft shipped, "Make sure you have the headshots in the new
fantasy shit."

The stamping half (fantasy_build writes r.headshot onto every board) is
pinned in test_mockdraft. This file pins the RENDERING half — the spots
that historically had the field and never drew it:

  * The draft kit's three row kinds (overall board, position tiers,
    sleepers) each hand the avatar r.headshot. The kit had carried the
    stamp since the first sweep and rendered plain text anyway.
  * The dossier takes its face from ANY source row that has one. The
    boards are stamped by different ingests, so the first row to match
    a NAME is often not the one carrying the headshot.
  * The full player page prefers the server's face (player_assets via
    /api/players/fantasy) and falls back to the boards'.
  * The Sleeper roster list falls back to the dossier lookup when the
    player has no usage row — a bench player is still a face.

Run directly: `python3 tests/test_fantasy_faces.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"),
           encoding="utf-8").read()


def _kit_region():
    i = APP.index("const boardRow = (r, i)")
    return APP[i:APP.index("const sleepers = ", i) + 900]


def test_all_three_kit_row_kinds_draw_the_face():
    region = _kit_region()
    n = region.count("headshot: r.headshot")
    assert n >= 3, f"only {n} of the kit's 3 row kinds hand the avatar a face"


def test_the_kit_identity_cells_are_flexed_and_styled():
    region = _kit_region()
    assert region.count('class="dl-main dl-id"') == 2, \
        "board and sleeper rows keep the avatar in its own lane"
    assert ".dl-id { display: flex;" in CSS
    # The tier rows give the 18px face its own grid lane instead.
    assert "grid-template-columns: 22px 18px minmax(0, 1fr) 44px" in CSS


def test_the_dossier_takes_a_face_from_any_source():
    i = APP.index("function _ffDossierInfo(")
    body = APP[i:APP.index("function ffDossierHTML(", i)]
    assert "sources.find((s) => s.headshot)" in body, \
        "the face must come from whichever board knows it"


def test_the_full_page_prefers_the_servers_face():
    assert "headshot: p.headshot || info.headshot" in APP


def test_the_sleeper_roster_falls_back_to_the_dossier_lookup():
    assert ('headshot: (r.u || {}).headshot '
            "|| _ffDossierInfo(r.name).headshot") in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
