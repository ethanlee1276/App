"""An NHL skater's forward line never overwrites his betting line.

Found 2026-10-15 in Ethan's catch-up paste (BA, AQ): the NHL build printed
"NHL journal skipped: Error binding parameter 8: type 'dict' is not
supported", and the NHL Pick of the Day read "the selector could not run on
this board — unhashable type: 'dict'". Both were one line in nhl_build.py:
the line combination (unit, linemates, shared ice) was written to
`r["line"]`, the key that holds the BETTING line every later reader
prices, journals and shows. Once the shift charts filled, every skater on a
line carried a dict there, so the journal refused the whole batch and no
NHL pick reached the record.

Run directly: `python3 tests/test_an_nhl_line_combination_never_overwrites_the_betting_line.py`
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nhl_build                                                 # noqa: E402
from engine import ledger                                        # noqa: E402

LINES = {"EDM": {"forwards": [{"players": ["Connor McDavid", "Zach Hyman", "Leon Draisaitl"], "together": 0.71}],
                 "defence": [{"players": ["Evan Bouchard", "Mattias Ekholm"], "together": 0.64}]}}


def _rows():
    return [{"player": "Connor McDavid", "team": "EDM", "opponent": "CGY", "market": "points", "side": "OVER",
             "line": 1.5, "odds": -120, "book": "DraftKings", "model_prob": 0.61, "hit_prob": 0.61,
             "implied_prob": 0.545, "projection": 1.7, "game_date": "2026-10-15"},
            {"player": "Evan Bouchard", "team": "EDM", "opponent": "CGY", "market": "shots_on_goal",
             "side": "OVER", "line": 2.5, "odds": -110, "book": "FanDuel", "model_prob": 0.58, "hit_prob": 0.58,
             "implied_prob": 0.524, "projection": 2.9, "game_date": "2026-10-15"}]


def test_the_slot_goes_beside_the_line_not_over_it():
    rows = _rows()
    nhl_build.attach_line_slots(rows, LINES)
    assert [r["line"] for r in rows] == [1.5, 2.5]
    assert rows[0]["line_slot"]["unit"] == "F1" and rows[0]["line_slot"]["mates"] == ["Zach Hyman", "Leon Draisaitl"]
    assert rows[1]["line_slot"]["unit"] == "D1"
    assert rows[0]["line_unit"] == "EDM-F1" and rows[1]["line_unit"] == "EDM-D1"
    assert any(s.startswith("Line: F1 with Zach Hyman and Leon Draisaitl") for s in rows[0]["reasons"])


def test_a_skater_on_no_line_is_left_as_he_was():
    rows = [dict(_rows()[0], player="Nobody")]
    nhl_build.attach_line_slots(rows, LINES)
    assert rows[0]["line"] == 1.5 and "line_slot" not in rows[0] and "line_unit" not in rows[0]


def test_rows_with_their_slot_reach_the_journal():
    rows = _rows()
    nhl_build.attach_line_slots(rows, LINES)
    conn = ledger.connect(Path(tempfile.mkdtemp()) / "ledger.db")
    n = ledger.log_most_likely(conn, {"sport": "nhl", "date": "2026-10-15", "games": [], "most_likely": rows},
                               depth=None, category="board", grade_label="Top pick")
    assert n == 2, n
    got = sorted(r[0] for r in conn.execute("SELECT line FROM bets WHERE sport='nhl'"))
    assert got == [1.5, 2.5], got


def test_the_pick_of_the_day_key_stays_hashable():
    rows = _rows()
    nhl_build.attach_line_slots(rows, LINES)
    keys = {ledger.potd_row_key(r) for r in rows}
    assert len(keys) == 2


def test_nothing_in_the_build_writes_a_slot_into_line():
    src = (ROOT / "nhl_build.py").read_text()
    assert 'r["line"] = slot' not in src and 'rd["line"] = slot' not in src
    assert 'r["line_slot"] = slot' in src and 'rd["line_slot"] = slot' in src


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
