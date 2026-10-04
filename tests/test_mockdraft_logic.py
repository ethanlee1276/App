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
  // The settings the format is composed from (2026-09-08): scoring,
  // roster, and the helpers that turn them into slots, bonus and caps.
  grab("const MOCK_SCORING = {", "};"),
  grab("const MOCK_DRAFT_TYPES = {", "};"),
  grab("const MOCK_SHEETS = {", "};"),
  grab("const MOCK_CLOCKS = [", "];"),
  grab("const MOCK_TEAMS_RANGE = [", "];"),
  grab("const MOCK_ROSTER_MAX = {", "};"),
  grab("const MOCK_DEFAULT_CFG = {", "} };"),
  grab("function _mockCleanCfg(", "\n}"),
  grab("function _mockLoadCfg(", "\n}"),
  "var _mockCfg = _mockLoadCfg();",
  grab("function _mockCfgSlots(", "\n}"),
  grab("function _mockCfgBonus(", "\n}"),
  grab("function _mockCfgFormatKey(", "\n}"),
  grab("function _mockCfgLabel(", "\n}"),
  grab("function _mockCfgRounds(", "\n}"),
  grab("function _mockRosterLine(", "\n}"),
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
// The snake over 12 teams, three rounds — and the two other orders a
// league can run, asked for by name.
out.snake = [];
for (let p = 0; p < 36; p++) out.snake.push(_mockPicker(p, 12));
out.linear = [];
for (let p = 0; p < 24; p++) out.linear.push(_mockPicker(p, 12, "linear"));
out.rr3 = [];
for (let p = 0; p < 60; p++) out.rr3.push(_mockPicker(p, 12, "3rr"));
// The default format the settings compose: PPR, one QB, two RB, two WR,
// one TE, two flex — the same line-up the judge below is scored on.
out.fmt_slots = _mockFmt().slots;
out.fmt_bonus = _mockFmt().bonus;

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


def test_the_other_two_orders_are_what_a_league_means_by_them():
    """Linear is the same order every round. Third-round reversal is the
    snake except round three runs the way round two did, so the seat
    that picked last in round one gets 2.01 AND 3.01 — from round four
    on it alternates as a snake does."""
    r = _run()
    assert r["linear"] == list(range(12)) * 2
    rounds = [r["rr3"][i * 12:(i + 1) * 12] for i in range(5)]
    fwd, rev = list(range(12)), list(range(11, -1, -1))
    assert rounds == [fwd, rev, rev, fwd, rev], rounds
    # Seat 12's first four picks: 1.12, 2.01, 3.01, 4.12.
    mine = [p for p in range(48) if r["rr3"][p] == 11]
    assert mine == [11, 12, 24, 47], mine


def test_the_settings_compose_the_default_format():
    r = _run()
    assert r["fmt_slots"] == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "SFLEX": 0}
    # Full PPR on a PPR board: nothing added or taken back per catch.
    assert r["fmt_bonus"] == {"RB": 0, "WR": 0, "TE": 0, "QB": 0}


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
