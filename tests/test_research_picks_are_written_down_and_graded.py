"""Research picks are written down before kickoff and graded after.

Ethan, 2026-10-04: "do all of it" — an owner-only box where a report's
picks are pasted before the games, so every week's research grades itself
(engine/researchlog, engine/scancard). Checks: one pick a line reads every
way a report writes it; a bad line says why and stores nothing; posting a
pick again keeps the first copy; the scorecard merges the box with the
claims file, each pick once; the server door is the owner token and only
that; the page offers the box only inside the owner's panel.

Run directly: `python3 tests/test_research_picks_are_written_down_and_graded.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import researchlog as R                                  # noqa: E402
from engine import scancard as S                                     # noqa: E402


def test_one_pick_a_line_reads_the_way_reports_write():
    text = """TD scan | Chase Brown | CIN | anytime td | over | 0.5 | 60-62% | -145
    Deep scan | Tee Higgins | cin | Receptions | O | 4.5 | 67% | +106
    Odds card | Tee Higgins | CIN | catches | over | 3.5 | 0.75 | -
    # a comment line is skipped
    Bad | Nobody | CIN | punts | over | 2.5 | 50% | -110
    Bad | Nobody | CIN | receptions | sideways | 2.5 | 50% | -110"""
    claims, errors = R.parse(text)
    assert [c["market"] for c in claims] == ["anytime_td", "receptions", "receptions"]
    assert claims[0]["prob"] == 0.61 and claims[0]["price"] == -145 and claims[0]["side"] == "OVER"
    assert claims[1]["team"] == "CIN" and claims[1]["price"] == 106
    assert claims[2]["prob"] == 0.75 and claims[2]["price"] is None
    assert len(errors) == 2 and "punts" in errors[0]["error"] and "over or under" in errors[1]["error"]


def test_a_pick_posted_again_keeps_its_first_copy():
    store = Path(tempfile.mkdtemp()) / "r.json"
    first, _ = R.parse("TD scan | Chase Brown | CIN | td | over | 0.5 | 54% | +105")
    again, _ = R.parse("TD scan | Chase Brown | CIN | td | over | 0.5 | 61% | -145")
    assert R.add(first, 2026, 5, store, now="2026-10-11T12:00:00")["added"] == 1
    got = R.add(again, 2026, 5, store, now="2026-10-11T18:00:00")
    assert got["added"] == 0 and got["kept_first"] == 1 and got["week_total"] == 1
    stored = R.load(2026, 5, store)
    assert stored[0]["prob"] == 0.54 and stored[0]["logged_at"] == "2026-10-11T12:00:00"
    assert R.load(2026, 6, store) == []


def test_the_scorecard_merges_the_box_with_the_file():
    store = Path(tempfile.mkdtemp()) / "r.json"
    picks, _ = R.parse("TD scan CIN-JAX 1 | Chase Brown | CIN | td | over | 0.5 | 54% | +105\n"
                       "New source | Tee Higgins | CIN | receptions | over | 4.5 | 60% | +100")
    R.add(picks, 2026, 4, store)
    got = S.claims_for(2026, 4, store=store)
    assert len(got) == 37, "the file's 36 and one new pick; the duplicate counted once"
    assert S.claims_for(2026, 9, store=store) == []


def test_the_door_is_the_owner_token_and_nothing_else():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    i = src.index("def _owner_refused(self)")
    body = src[i:src.index("def _tailfade_get", i)]
    assert "owner_token_ok" in body and "503" in body and "403" in body
    assert "self._account(" not in body, "no signed-in account can write research picks"
    assert body.count("if self._owner_refused():") == 2, "both the write and the read"
    assert "web" not in str(R.STORE.relative_to(ROOT)).split(os.sep)[0], "the store is not public"


def test_the_box_lives_in_the_owners_panel_only():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    i = js.index("function zenoOwnerHTML(tix)")
    panel = js[i:js.index("\nfunction ", i + 10)]
    assert panel.index("if (!tix.owner)") < panel.index("researchBoxHTML()"), \
        "the box renders after the owner check, never for a visitor"
    assert '"/api/research"' in js and '"X-Owner-Token": zenoOwnerToken()' in js


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
