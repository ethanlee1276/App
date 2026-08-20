"""The mock draft's arithmetic, executed rather than read.

`tests/test_mockdraft.py` pins the simulator's shape into the page; this
file RUNS the three pure functions the whole thing stands on — the snake
order, the positional-need discipline, and the starters'-PPG judge — by
slicing them out of app.js and evaluating them in node. A drafted-roster
grade that quietly misordered the snake would still render beautifully,
which is exactly why reading the source is not enough here.

Run directly: `python3 tests/test_mockdraft_logic.py`
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Same SKIP convention as test_live_situation.py / test_venue_ingest.py:
# run_tests.py prints the reason and names the file, so coverage that
# stops happening is visible rather than silent.
import shutil as _shutil                                     # noqa: E402
if not _shutil.which("node"):
    print("SKIP node is not installed; the assertions here execute the "
          "draft arithmetic rather than read it. `apt install -y nodejs`")
    print("\n0 tests passed.")
    raise SystemExit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
// Slice the pure functions out by their declarations — no DOM needed.
function grab(name, end) {
  const i = src.indexOf(name);
  if (i < 0) throw new Error("missing: " + name);
  const j = src.indexOf(end, i);
  return src.slice(i, j + end.length);
}
const code = [
  // Formats: the line-up, caps and share bands the rest reads from.
  grab("const MOCK_FORMATS = {", "\n};"),
  "let _mockFormat = 'ppr';",
  grab("function _mockFmt(", "\n}"),
  grab("const MOCK_SLOTS", ";"),
  // The caps the need curve now enforces — a room that only ever
  // SOFTENED finished with six quarterbacks.
  grab("const MOCK_ROSTER_CAP", ";"),
  grab("const MOCK_FLEX", ";"),
  grab("function _mockPicker(", "\n}"),
  grab("function _mockNeedCounts(", "\n}"),
  grab("function _mockLineup(", "\n}"),
  grab("function _mockStartersPPG(", "\n}"),
].join("\n");
eval(code);

const out = {};
// The snake over 12 teams, three rounds.
out.snake = [];
for (let p = 0; p < 36; p++) out.snake.push(_mockPicker(p, 12));

// Need discipline: a room holding one QB, asked about a second. Counts
// rather than a roster array — the Monte Carlo carries counts, and
// rebuilding a roster per simulated pick was the whole cost of the loop.
const qbCounts = { QB: 1, RB: 0, WR: 0, TE: 0 };
out.qb_early = _mockNeedCounts(qbCounts, "QB", 3);
out.qb_late = _mockNeedCounts(qbCounts, "QB", 10);
out.rb_always = _mockNeedCounts(qbCounts, "RB", 3);

// The judge: a full roster with a known best lineup.
const roster = [
  { position: "QB", proj: 20 }, { position: "QB", proj: 18 },
  { position: "RB", proj: 15 }, { position: "RB", proj: 14 },
  { position: "RB", proj: 13 },
  { position: "WR", proj: 16 }, { position: "WR", proj: 12 },
  { position: "WR", proj: 11 },
  { position: "TE", proj: 10 }, { position: "TE", proj: 9 },
];
// Starters: QB 20 + RB 15+14 + WR 16+12 + TE 10 + FLEX 13+11 = 111.
out.ppg = _mockStartersPPG(roster);
// No quarterback drafted: the slot scores zero, never borrows.
out.no_qb = _mockStartersPPG(roster.filter((p) => p.position !== "QB"));
console.log(JSON.stringify(out));
"""


def _run():
    node = _shutil.which("node")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(_HARNESS)
        path = fh.name
    try:
        res = subprocess.run(
            [node, path, os.path.join(ROOT, "web", "js", "app.js")],
            capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def test_the_snake_reverses_every_round_and_covers_every_room():
    r = _run()
    first, second, third = (r["snake"][i * 12:(i + 1) * 12] for i in range(3))
    assert first == list(range(12))
    assert second == list(range(11, -1, -1)), "round two must reverse"
    assert third == first, "round three snakes back"
    # The turn (picks 12 and 13) belongs to the same room — the snake's
    # signature, and the reason slot 12 is not a punishment.
    assert r["snake"][11] == r["snake"][12] == 11


def test_a_room_holding_a_quarterback_waits_on_the_second():
    r = _run()
    assert r["qb_early"] < 0.2, "a second QB in round 3 must be starved"
    # The bench rounds RELAX the onesie rule; they do not lift it. This
    # asserted 1.0 until 2026-08-20, when 300 measured drafts showed what
    # full late appetite does: rooms finished carrying 1.85 quarterbacks
    # each, where a twelve-team league runs about 1.3. A second
    # quarterback is a bench luxury in round ten as well as round three —
    # just a likelier one.
    assert r["qb_early"] < r["qb_late"] < 0.5, \
        "a second QB must stay a luxury all draft, and ease late"
    assert r["rb_always"] == 1.0


def test_the_judge_fields_the_best_legal_lineup():
    r = _run()
    assert abs(r["ppg"] - 111) < 1e-9, r["ppg"]
    # 111 minus the QB slot's 20 — an empty slot scores zero, and the
    # bench never smuggles a second flex in to cover it.
    assert abs(r["no_qb"] - 91) < 1e-9, r["no_qb"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
