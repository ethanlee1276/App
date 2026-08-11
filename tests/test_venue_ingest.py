"""The venue intake pipeline — synthetic sheets in, named variants out.

The chat pipeline recompresses and lags, so renders travel as files:
drop into web/img/venues/incoming/, run tools/venues_ingest.py. These
tests build tiny synthetic renders (solid lighting glows over dark
tiles) and prove the slicer finds the grid, the classifier reads the
LIGHTING rather than the playing surface, neutral lands on steel, the
octagon maps to its rotation slots, and a re-run can only upgrade.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from tools.venues_ingest import (classify, ingest, slice_tiles,  # noqa: E402
                                 target_name)


def _tile(rgb, size=(300, 200)):
    """A dark tile lit from above in one colour — the render shape the
    classifier was built for: colour in the rig, dim bowl below. The
    body sits just over the slicer's brightness floor, the way a real
    render's crowd and field always do (a pure-black body is a fixture
    artifact no camera produces)."""
    im = Image.new("RGB", size, (26, 26, 30))
    top = Image.new("RGB", (size[0], size[1] // 3), rgb)
    im.paste(top, (0, 0))
    return im


def _sheet(colors, cols=3, pad=14):
    tw, th = 300, 200
    rows = (len(colors) + cols - 1) // cols
    im = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad) + pad),
                   (0, 0, 0))
    for i, c in enumerate(colors):
        x = pad + (i % cols) * (tw + pad)
        y = pad + (i // cols) * (th + pad)
        im.paste(_tile(c), (x, y))
    return im


def test_the_slicer_finds_the_grid_and_leaves_singles_whole():
    sheet = _sheet([(200, 30, 30), (30, 60, 200), (200, 160, 30),
                    (140, 40, 220), (30, 180, 60)])
    assert len(slice_tiles(sheet)) == 5
    assert len(slice_tiles(_tile((200, 200, 210)))) == 1


def test_the_classifier_reads_lighting_not_the_floor():
    # A green-lit tile over an amber "wood floor" must read green — the
    # bug the first hue pass had on the basketball sheet.
    t = _tile((40, 200, 70))
    floor = Image.new("RGB", (300, 80), (190, 140, 80))
    t.paste(floor, (0, 120))
    assert classify(t) == "green"
    assert classify(_tile((205, 205, 215))) == "steel"     # neutral light
    assert classify(_tile((150, 40, 230))) == "violet"
    assert classify(_tile((230, 150, 30))) == "gold"


def test_ingest_names_families_and_octagon_slots_and_only_upgrades():
    with tempfile.TemporaryDirectory() as td:
        inc, var = Path(td) / "in", Path(td) / "out"
        inc.mkdir()
        _sheet([(200, 30, 30), (30, 60, 200)]).save(inc / "baseball-colors.png")
        _tile((205, 205, 215), (1000, 660)).save(inc / "football-neutral.png")
        _tile((140, 40, 220)).save(inc / "octagon-purple.png")
        _tile((30, 60, 200)).save(inc / "mystery.png")      # no family
        report = ingest(inc, var)
        names = sorted(p.name for p in var.glob("*.jpg"))
        assert names == ["baseball-blue.jpg", "baseball-red.jpg",
                         "football-steel.jpg", "octagon-1.jpg"]
        assert any(r.startswith("SKIP mystery.png") for r in report)
        # Small tiles get the 2x lift; big singles never upscale.
        assert Image.open(var / "baseball-red.jpg").width == 584
        assert Image.open(var / "football-steel.jpg").width == 1000
        # A re-run with a SMALLER source refuses to downgrade.
        _tile((205, 205, 215), (400, 260)).save(inc / "football-neutral.png")
        report = ingest(inc, var)
        assert any(r.startswith("KEEP football-steel.jpg") for r in report)
        assert Image.open(var / "football-steel.jpg").width == 1000


def test_target_names_stay_on_the_site_contract():
    assert target_name("baseball", "violet") == "baseball-violet.jpg"
    assert target_name("octagon", "steel") == "octagon-6.jpg"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
