"""A browser downloads the board without what no page reads.

The site audit, 2026-09-24 (docs/AUDIT_2026-09-24.md, M-3): every prop
row carried its whole alternate ladder (`alt_lines`, `alt_sharp_lines`,
`rung_probs`) to every phone, and `board_shelves` repeated every Most
Likely row in full. `engine/served.py` cuts both from the two copies a
browser can get — the public file `gate.publish` writes and the
subscriber copy `server.board_bytes` serves — and the private copy the
droplet's tools read keeps everything.

The failure this could introduce is a page drawing a shelf with no rows,
so the page's rebuild is run here, in Node, against the served board, and
must give back exactly the shelves the build wrote.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boards, gate, served as S                     # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _row(player, market, line, p):
    return {"player": player, "market": market, "side": "over", "line": line,
            "prob": p, "odds": -150,
            "alt_lines": [{"line": line + 1, "over_odds": 120, "book": "fanduel"}],
            "alt_sharp_lines": [{"line": line + 1, "over_odds": 115}],
            "rung_probs": {str(line + 1): 0.41}}


def _board():
    ml = [_row("A. Hitter", "batter_hits", 0.5, 0.71),
          _row("B. Slugger", "batter_home_runs", 0.5, 0.33),
          _row("C. Hitter", "batter_hits", 1.5, 0.52)]
    return {"date": "2026-09-24", "most_likely": ml,
            "recommendations": [_row("A. Hitter", "batter_hits", 0.5, 0.71)],
            "game": {"nested": [{"alt_lines": [1], "keep": 1}]},
            "board_shelves": boards.shelves("mlb", ml)}


def test_the_ladders_leave_and_the_private_copy_keeps_them():
    board = _board()
    out = S.served(board)
    text = json.dumps(out)
    for key in S.DROP_KEYS:
        assert f'"{key}"' not in text, key
    assert out["game"]["nested"] == [{"keep": 1}], "dropped at any depth"
    assert "alt_lines" in board["most_likely"][0], "the caller's board is untouched"
    assert out["most_likely"][0]["prob"] == 0.71 and len(out["recommendations"]) == 1


def test_the_shelves_travel_as_positions():
    board = _board()
    assert board["board_shelves"], "the fixture has shelves"
    out = S.served(board)
    for sh in out["board_shelves"]:
        assert "rows" not in sh and isinstance(sh["row_ix"], list), sh
    cut = len(json.dumps(out)) / len(json.dumps(board))
    assert cut < 0.6, f"served is {cut:.0%} of the board"


def test_a_shelf_with_a_row_the_board_lacks_is_left_as_it_was():
    board = _board()
    board["board_shelves"].append({"key": "odd", "title": "Odd", "rows": [{"player": "Nobody"}]})
    odd = S.served(board)["board_shelves"][-1]
    assert odd["rows"] == [{"player": "Nobody"}] and "row_ix" not in odd


def test_the_page_rebuilds_exactly_the_shelves_the_build_wrote():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    i = APP.index("function boardShelves(")
    fn = APP[i:APP.index("\n}\n", i) + 2]
    board = _board()
    want = S._drop(board)["board_shelves"]
    prog = (f"const state = {{}};\n{fn}\n"
            f"const d = {json.dumps(S.served(board))};\n"
            "process.stdout.write(JSON.stringify(boardShelves(d)));")
    got = json.loads(subprocess.run([node, "-e", prog], capture_output=True, text=True,
                                    timeout=60, check=True).stdout)
    for g, w in zip(got, want):
        assert g["rows"] == w["rows"] and g["title"] == w["title"], (g, w)
    assert len(got) == len(want)


def test_both_ways_a_board_reaches_a_browser_are_served():
    root = Path(tempfile.mkdtemp())
    public = root / "web" / "data" / "fixture_board.json"
    board = _board()
    _, full = gate.publish(board, public)
    pub, priv = public.read_text(), Path(full).read_text()
    assert "alt_lines" not in pub and '"row_ix"' in pub, "the public file"
    assert "\n" not in pub.strip(), "no indentation on the wire"
    assert "alt_lines" in json.loads(priv)["most_likely"][0], "the private copy keeps them"
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    i = src.index("def board_bytes(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "served(payload)" in body, "the subscriber copy"


def test_no_page_reads_what_was_cut():
    for js in (ROOT / "web" / "js").glob("*.js"):
        text = js.read_text(encoding="utf-8")
        for key in S.DROP_KEYS:
            assert key not in text, f"{js.name} reads {key}; it is not served"
    assert "state.data.board_shelves" not in APP, "shelves are read through boardShelves"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
