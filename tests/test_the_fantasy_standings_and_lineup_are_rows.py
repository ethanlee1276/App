"""v5: the Fantasy standings and lineup are the book's rows.

Rendered at 390 with a real-shaped league, both were tables that ran off
the phone: the standings lost the points-against column behind any team
name longer than two words (34px over), and the lineup lost both of its
point columns (82px over) and printed Sleeper's slot key "SUPER_FLEX".
Each is the book's row now — the standings: rank, the whole team name,
points for and against under it, the record on the right, yours marked;
the lineup: the slot, the player and his position, the projection on the
right with the PPR base beneath it.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    m = re.search(r"^(async )?function " + name + r"\(", APP, re.M)
    assert m, name
    i = m.start()
    return APP[i:APP.index("\n}\n", i) + 2]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const icon = (n) => `<i class="ic-${{n}}"></i>`;
      {_const("MOCK_SLEEPER_SLOT")}
      {_fn("ffStandingsHTML")}
      {_fn("ldSwapsHTML")}
      {_fn("ffLineupHTML")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_standings_are_rows_with_the_whole_name_and_yours_marked():
    got = _node("""return { html: ffStandingsHTML({ me_roster_id: 2, standings: [
        { rank: 1, roster_id: 1, team: "The Pacheco Protection Program", wins: 9, losses: 4, ties: 0, points_for: "1623.46", points_against: "1480.12" },
        { rank: 2, roster_id: 2, team: "Kelce Grammer", wins: 8, losses: 4, ties: 1, points_for: "1582.26", points_against: "1502.82" } ] }),
      one: ffStandingsHTML({ standings: [{ rank: 1, team: "Solo" }] }) };""")
    if got is None:
        print("  SKIP node not installed"); return
    h = " ".join(got["html"].split())
    assert "<table" not in h, "the table is back"
    assert h.count('class="hd-row ff-row') == 2 and '<div class="hd-card ff-rows">' in h
    assert "<b>The Pacheco Protection Program</b>" in h, "the whole name, never truncated"
    assert "PF 1623.46 · PA 1480.12" in h and '<span class="hd-state"><b>9-4</b></span>' in h
    assert '<div class="hd-row ff-row ld-mine">' in h and '<b>Kelce Grammer <span class="hd-chip">you</span></b>' in h
    assert "<b>8-4-1</b>" in h, "a tie is kept"
    assert h.count("ld-mine") == 1 and h.count(">you<") == 1
    assert got["one"] == "", "one team is not a table"


def test_the_lineup_is_rows_with_the_slot_in_words():
    got = _node("""return { html: ffLineupHTML({ league: "Qellys Dynasty", lineup: { total: 142.6, exact: true, note: "n",
        starters: [
          { slot: "QB", player: "Jayden Daniels", position: "QB", points: 22.4, base_ppr: 21.1 },
          { slot: "SUPER_FLEX", player: "Josh Allen", position: "QB", points: 23.9, base_ppr: 23.1, thin: true },
          { slot: "FLEX", player: null, position: "" } ],
        current: { total: 131.2 }, swaps: [] } }) };""")
    if got is None:
        print("  SKIP node not installed"); return
    h = " ".join(got["html"].split())
    assert "<table" not in h and "SUPER_FLEX" not in h, "the table, or Sleeper's key, is back"
    assert h.count('<div class="hd-row ff-row">') == 3
    assert '<span class="ld-slot">SFLEX</span>' in h and '<span class="ld-slot">QB</span>' in h
    assert "<b>Josh Allen <span class=\"hd-chip warn\">thin sample</span></b>" in h
    assert '<span class="hd-state"><b>23.9</b> <span class="hd-vs">PPR base 23.1</span></span>' in h
    assert "— nobody eligible" in h and '<b>—</b> <span class="hd-vs">PPR base —</span>' in h
    assert "142.6 projected points" in h and "Nothing to change" in h, "the total and the swaps survive"


def test_the_rows_are_styled():
    for rule in (".ld-slot { flex: 0 0 52px; font-family: var(--font-mono);",
                 ".ff-row .hd-what b .hd-chip, .ff-row .hd-what b .rank-none { display: inline-block;",
                 ".ff-row.ld-mine { background: var(--panel-2);"):
        assert rule in CSS, rule
    assert APP.count('class="rank-scroll"') >= 3, "the ranking tables keep their own wrapper"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
