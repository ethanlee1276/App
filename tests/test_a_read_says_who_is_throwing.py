"""A player read says when his quarterback is out, and what that did.

Ethan, 2026-09-28, on Colston Loveland with Caleb Williams out: "are we
using that in our picks … I don't see it displayed here like it's a factor
for these players." engine/qbchange prices it where measured (receivers'
yards and catches behind a downgrade); tight ends, backs and touchdowns
are shown and left alone. The read now says which.

Run directly: `python3 tests/test_a_read_says_who_is_throwing.py`
"""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
QB = (ROOT / "engine" / "qbchange.py").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    depth, j = 0, APP.index("{", i)
    for k in range(j, len(APP)):
        depth += {"{": 1, "}": -1}.get(APP[k], 0)
        if depth == 0:
            return APP[i:k + 1]


def test_the_read_card_draws_it():
    assert "${scanQbLine(x)}" in _fn("scanReadHTML")


def test_the_words_match_what_was_measured():
    assert '("rec_yds", "WR", "downgrade"): 0.897' in QB and '("receptions", "WR", "downgrade"): 0.912' in QB
    fn = _fn("scanQbLine")
    assert "about 10% of their yards and 9% of their catches" in fn


def test_each_position_gets_its_own_sentence():
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    prog = "const escapeHtml = (s) => String(s);\n" + _fn("scanQbLine") + """
const state = {data: {qb_changes: [{team: "CHI", starter: "Caleb Williams", status: "OUT",
  replacement: "Tyson Bagent", tier: "downgrade", headline: "Caleb Williams (OUT) — Tyson Bagent starts"}]}};
const out = {
  te: scanQbLine({team: "CHI", pos: "TE", player: "Colston Loveland"}),
  wr: scanQbLine({team: "CHI", pos: "WR", player: "Luther Burden III"}),
  qb: scanQbLine({team: "CHI", pos: "QB", player: "Tyson Bagent"}),
  other: scanQbLine({team: "PHI", pos: "WR", player: "A. J. Brown"})};
console.log(JSON.stringify(out));
"""
    got = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-400:]
    import json
    o = json.loads(got.stdout)
    assert "Tyson Bagent starts" in o["te"] and "tight ends’" in o["te"] and "left alone" in o["te"]
    assert "taken off his numbers" in o["wr"]
    assert "Starting in place of Caleb Williams" in o["qb"]
    assert o["other"] == "", "the other team's players are not told about CHI's quarterback"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
