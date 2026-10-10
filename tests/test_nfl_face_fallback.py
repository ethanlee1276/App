"""An NFL face is found by a loose name, and by ESPN id when the roster has no photo.

Ethan, 2026-09-14: "We are missing head shots for a lot of NFL players."
Two gaps: the face map was keyed on the roster's exact spelling while the
board asks with the stats feed's spelling (suffixes, accents, a middle
initial), and a roster row with an `espn_id` but no `headshot_url` had a
face ESPN serves by id and we never asked for it.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import nflverse                           # noqa: E402

SRC = (ROOT / "engine" / "sources" / "nflverse.py").read_text()


def test_exact_name_wins():
    assert nflverse.face_for({"Josh Allen": "u1"}, "Josh Allen") == "u1"


def test_a_suffix_or_accent_no_longer_loses_the_face():
    faces = {"Kenneth Walker III": "u2", "Ronald Acuña Jr.": "u3"}
    assert nflverse.face_for(faces, "Kenneth Walker") == "u2"
    assert nflverse.face_for(faces, "Ronald Acuna") == "u3"


def test_no_match_is_still_no_face():
    assert nflverse.face_for({"Josh Allen": "u1"}, "Someone Else") == ""
    assert nflverse.face_for({"Josh Allen": "u1"}, "") == ""


def test_the_roster_falls_back_to_espn_by_id():
    keep = nflverse.load_rosters
    nflverse.load_rosters = lambda season: [
        {"full_name": "A Photo", "headshot_url": "https://x/a.png", "espn_id": "1"},
        {"full_name": "B Idonly", "headshot_url": "", "espn_id": "4241389"},
        {"full_name": "C Nothing", "headshot_url": "", "espn_id": ""},
    ]
    try:
        got = nflverse.headshot_map(2026)
    finally:
        nflverse.load_rosters = keep
    assert got["A Photo"] == "https://x/a.png", "a real URL is never replaced"
    assert got["B Idonly"] == nflverse.ESPN_HEADSHOT.format(pid="4241389")
    assert "C Nothing" not in got


def test_the_board_uses_the_loose_lookup():
    assert "headshot=face_for(headshots, spec.player)" in SRC
    assert "headshot=headshots.get(spec.player" not in SRC


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
