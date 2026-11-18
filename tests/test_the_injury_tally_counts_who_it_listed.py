"""The injury report's tally counts the players it listed; a miss is said as one
(2026-11-18, step YE).

College basketball's "How our reports did" read "The injury report — 0% —
0 of 5 right; 5 regulars sat without being on it", and every college game
with a miss wore a red "Injury report 0 of 1" chip. Nothing had been listed:
ESPN's college injury board runs sparse (schools have no reporting duty; it
held no college row on 18 November), and a regular who sits off the report is
a wrong in the record's pair (engine/reportgrade._injury_summary). The share
is now of the players the report listed, the misses said beside it, here, in
the tile and chips the Record page draws, and in the line each report section
opens on (engine/reportrecord.track_lines).

    python3 tests/test_the_injury_tally_counts_who_it_listed.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
RP = (JS / "reportpicks.js").read_text(encoding="utf-8")

from engine import reportrecord as RR                                           # noqa: E402


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 2]


def _node(prog: str):
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return None
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _harness() -> str:
    i = RP.index("const RP_KINDS = ")
    kinds = RP[i:RP.index("];\n", i) + 3]
    return "\n".join([
        _fn(APP, "escapeHtml"), _fn(APP, "pluralWord"), _fn(APP, "plural"),
        "const escapeAttr = escapeHtml; const teamName = (t) => t; const formatGameDate = (d) => d || \"\";",
        kinds, _fn(RP, "rpShare"), _fn(RP, "rpListed"), _fn(RP, "rpCalibHTML"), _fn(RP, "rpTotalsHTML"),
        _fn(RP, "rpFactRowHTML"),
    ])


def test_the_tile_and_the_chips_count_who_it_listed():
    got = _node(_harness() + """
      const text = (h) => h.replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim();
      const tile = (h) => { const m = h.match(/rpk-fact-k">The injury report<\\/span>([\\s\\S]*?)<\\/div>/); return m ? text(m[1]) : null; };
      const chips = (h) => (h.match(/<span class="rpk-fact-chip[^"]*">[^<]*<\\/span>/g) || [])
        .filter((c) => /Injury|regular/.test(c)).map((c) => [/lost/.test(c) ? "lost" : /won/.test(c) ? "won" : "", text(c)]);
      const college = rpTotalsHTML({games: 26, injuries: [0, 5], missed: 5, call: [16, 22]});
      const nba = rpTotalsHTML({games: 13, injuries: [34, 36], missed: 2});
      const none = rpTotalsHTML({games: 3, injuries: [0, 0], missed: 0});
      const game = {date: "2026-11-17", away: "UNLV", home: "KU", final: {away: 61, home: 80}};
      console.log(JSON.stringify({
        college: tile(college), nba: tile(nba), none: tile(none),
        missOnly: chips(rpFactRowHTML({...game, injuries: [0, 1], missed: 1})),
        both: chips(rpFactRowHTML({...game, injuries: [2, 3], missed: 1})),
        clean: chips(rpFactRowHTML({...game, injuries: [2, 2], missed: 0})),
      }));""")
    if got is None:
        return
    assert got["college"] == "5 missed 5 regulars sat without being on it", got["college"]
    assert got["nba"] == "100% 34 of 34 right; 2 regulars sat without being on it", got["nba"]
    assert got["none"] is None, "nothing listed and nothing missed: no tile"
    assert got["missOnly"] == [["lost", "1 regular sat off the report"]], got["missOnly"]
    assert got["both"] == [["won", "Injury report 2 of 2"], ["lost", "1 regular sat off the report"]], got["both"]
    assert got["clean"] == [["won", "Injury report 2 of 2"]], got["clean"]


def test_each_report_section_opens_on_the_same_count():
    base = {"games": 26, "since": "2026-11-16", "through": "2026-11-17"}
    tail = ", on 26 finished college basketball games since Nov 16."
    lines = RR.track_lines(dict(base, injuries=[0, 12], missed=12), "cbb")
    assert lines["injuries"] == "Our injury report so far: 12 regulars sat who were not on it" + tail, lines
    lines = RR.track_lines(dict(base, injuries=[30, 33], missed=3), "cbb")
    assert lines["injuries"] == ("Our injury report so far: 30 of 30 right (100%), with 3 regulars who sat and were "
                                 "not on it" + tail), lines
    assert "injuries" not in RR.track_lines(dict(base, injuries=[0, 5], missed=5), "cbb"), "five are too few to say"


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
