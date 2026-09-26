"""The server stops parsing 18MB boards; the build hands it the bytes.

The 2026-09-26 outage, off the droplet: the server process reached 1.4GB
within four minutes of every restart and the kernel killed it every ten
minutes for two hours (anon-rss 420-840MB at each kill, the builds tiny
beside it). Two things in the server parsed the private boards, which
are 10-18MB of JSON now:

  * `server.board_bytes` — every member board request parsed the whole
    board, built a trimmed second copy and serialised it, per board, per
    rebuild, several at once, outside any lock;
  * Ask's `board_at` — every league's board parsed and kept whole.

Now `gate.publish` writes the served bytes beside the full copy (the
build already holds the board), the server reads those when they are at
least as new and parses only as a fallback, one at a time, handing the
memory back after; and Ask keeps a slim copy.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gate, served as S                                  # noqa: E402
from engine import askbot as AB                                      # noqa: E402


def _board():
    row = {"player": "A", "market": "rec_yds", "side": "over", "line": 40.5,
           "alt_lines": [{"line": 30.5}], "rung_probs": [0.7]}
    return {"sport": "nfl", "most_likely": [row], "recommendations": [dict(row, player="B")],
            "board_shelves": [{"key": "all", "title": "All", "rows": [row]}],
            "player_stats": {"A": {"rec_yds": [1, 2, 3]}}, "games": []}


def _tree():
    root = Path(tempfile.mkdtemp())
    public = root / "web" / "data" / "recommendations.json"
    _, full = gate.publish(_board(), public)
    return Path(full)


def test_publish_writes_the_served_bytes_beside_the_full_copy():
    full = _tree()
    side = gate.served_sidecar(full)
    assert side.name == "recommendations.json.served" and side.is_file()
    assert side.stat().st_mtime_ns >= full.stat().st_mtime_ns, "written after the full copy"
    got = json.loads(side.read_text())
    assert got == json.loads(json.dumps(S.served(json.loads(full.read_text()))))
    assert "alt_lines" not in side.read_text() and "\n" not in side.read_text()
    assert gate.full_board_file("recommendations.json.served") is None, "never handed out by URL"


def _server_with(full: Path):
    import server
    orig = (gate.full_board_file, gate.full_board)
    gate.full_board_file = lambda name: full if name == full.name else None
    calls = []

    def parse(name):
        calls.append(name)
        return json.loads(full.read_text())
    gate.full_board = parse
    server._BOARD_CACHE.clear()
    return server, calls, orig


def test_the_server_serves_the_sidecar_without_parsing():
    full = _tree()
    server, calls, orig = _server_with(full)
    try:
        body, _mt, etag = server.board_bytes(full.name)
    finally:
        gate.full_board_file, gate.full_board = orig
    assert calls == [], "no parse when the build's bytes are there"
    assert body == gate.served_sidecar(full).read_bytes() and etag


def test_a_stale_sidecar_is_not_trusted():
    full = _tree()
    side = gate.served_sidecar(full)
    old = time.time() - 3600
    os.utime(side, (old, old))
    server, calls, orig = _server_with(full)
    try:
        body, _mt, _etag = server.board_bytes(full.name)
    finally:
        gate.full_board_file, gate.full_board = orig
    assert calls == [full.name], "the full copy is newer: built from it"
    assert json.loads(body) == S.served(json.loads(full.read_text()))


def test_the_fallback_parses_one_board_at_a_time_and_gives_memory_back():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    i = src.index("def board_bytes(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "with _PARSE_LOCK:" in body and "release_memory()" in body
    assert body.index("gate.served_sidecar(path)") < body.index("gate.full_board(name)")
    S.release_memory()                                   # never raises


def test_ask_keeps_a_slim_copy_parsed_once_at_a_time():
    full = _tree()
    AB._BOARDS.clear()
    got = AB.board_at(full)
    assert "player_stats" not in got and "board_shelves" not in got
    assert "alt_lines" not in json.dumps(got) and got["recommendations"][0]["player"] == "B"
    assert AB.board_at(full) is got, "cached until the file changes"
    assert "with _BOARDS_PARSE:" in (ROOT / "engine" / "askbot.py").read_text()


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
