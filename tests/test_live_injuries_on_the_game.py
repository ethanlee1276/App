"""Live injuries on a game's page, as Real shows them.

Ethan, 2026-10-25, on Real: "It has live injuries." ESPN's game summary
carries each side's injury list and keeps it current; the deep file now
carries it (`injuries_live`, engine/sources/espnplays.summary_injuries), and
each status that comes onto it AFTER the box first looked at the game is
stamped with when (livescore_build._injuries_since) — the page's "new".

THE FIRST LOOK IS THE BASELINE. A deep file first written in the third
quarter must not call the whole pregame list new, so the first write
stamps nothing.

    python3 tests/test_live_injuries_on_the_game.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import espnplays                           # noqa: E402
import livescore_build as LS                                    # noqa: E402

PAYLOAD = {"injuries": [
    {"team": {"abbreviation": "PIT"}, "injuries": [
        {"athlete": {"displayName": "T.J. Watt"}, "status": "Questionable",
         "details": {"type": "Hamstring", "side": "Left"}},
        {"athlete": {"displayName": "Nobody"}, "status": ""}]},
    {"team": {"abbreviation": "NO"}, "injuries": [
        {"athlete": {"displayName": "Alvin Kamara"}, "type": {"description": "out"},
         "details": {"type": "Ankle", "side": "Not Specified"}}]},
    "junk"]}


def test_the_list_is_read_as_fields():
    got = espnplays.summary_injuries(PAYLOAD, "nfl")
    assert got == [{"team": "PIT", "player": "T.J. Watt", "status": "Questionable", "detail": "Left Hamstring"},
                   {"team": "NO", "player": "Alvin Kamara", "status": "Out", "detail": "Ankle"}], got
    assert espnplays.summary_injuries({}, "nfl") == [] and espnplays.summary_injuries(None, "nfl") == []


def _write(path, rows):
    doc = {"injuries_live": [dict(r) for r in rows]}
    LS._injuries_since(doc, path)
    Path(path).write_text(json.dumps(doc))
    return doc["injuries_live"]


def test_the_first_look_stamps_nothing_and_a_later_status_is_new():
    base = espnplays.summary_injuries(PAYLOAD, "nfl")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "nfl_1.json"
        first = _write(path, base)
        assert not any(r.get("seen") for r in first), "the whole pregame list called new"
        again = _write(path, base)
        assert not any(r.get("seen") for r in again), "nothing changed, nothing new"
        hurt = base + [{"team": "PIT", "player": "Najee Harris", "status": "Questionable", "detail": "Knee"}]
        later = _write(path, hurt)
        assert [r["player"] for r in later if r.get("seen")] == ["Najee Harris"]
        stamp = later[-1]["seen"]
        still = _write(path, hurt)
        assert still[-1]["seen"] == stamp, "the stamp is when it first appeared, not the last pass"
        changed = [dict(r, status="Out") if r["player"] == "T.J. Watt" else r for r in hurt]
        assert any(r["player"] == "T.J. Watt" and r.get("seen") for r in _write(path, changed)), \
            "a status that changed is news too"


def test_the_deep_file_carries_it_and_the_page_draws_the_new_ones():
    src = (ROOT / "livescore_build.py").read_text()
    assert '("injuries_live", lambda: espnplays.summary_injuries(payload, league))' in src
    w = src[src.index("def write_pbp("):src.index("def _injuries_since(")]
    assert "_injuries_since(doc, out)" in w and w.index("_injuries_since(doc, out)") < w.index("os.replace(tmp, out)")
    detail = (ROOT / "web" / "js" / "detail.js").read_text()
    assert "${pbpNewInjuriesHTML(d)}" in detail
    fn = detail[detail.index("function pbpNewInjuriesHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert ".filter((r) => r && r.seen)" in fn and "escapeHtml(r.player)" in fn and "escapeHtml(r.status)" in fn


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
