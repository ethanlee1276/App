"""Who could shine / who could struggle: ranked by one rule, numbered.

Ethan, 2026-09-26, the list circled: "are these ranked? Or just scattered
in there." They were sorted by pick-or-not, then tier, then reason count,
with ties in game order and no number shown. `scanRanked` (app.js) now
orders by the read's tier, its net case (reasons for minus against; the
struggle list the other way), our chance on his side, then his name — and
each row carries its rank.
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _rank(rows, shine=True):
    if not shutil.which("node"):
        return None
    prog = _fn("scanStrength") + _fn("scanRanked") + \
        f"\nconsole.log(JSON.stringify(scanRanked({json.dumps(rows)}, {str(shine).lower()}).map((x) => x.player)));"
    path = os.path.join(tempfile.mkdtemp(), "r.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    return json.loads(out.stdout)


def test_tier_then_net_case_then_our_chance_then_name():
    rows = [
        {"player": "Good, big case", "read": "good", "pro": ["a", "b", "c", "d"], "con": []},
        {"player": "Breakout, thin", "read": "breakout", "pro": ["a"], "con": []},
        {"player": "Breakout, strong", "read": "breakout", "pro": ["a", "b", "c"], "con": ["x"]},
        {"player": "Breakout, strong, 71%", "read": "breakout", "pro": ["a", "b", "c"], "con": ["x"],
         "pick": {"model_prob": 0.71}},
        {"player": "Breakout, strong, TD 64%", "read": "breakout", "pro": ["a", "b"], "con": [],
         "td": {"model_prob": 0.64}},
        {"player": "Aaron tie", "read": "good", "pro": ["a"], "con": []},
        {"player": "Zed tie", "read": "good", "pro": ["a"], "con": []},
    ]
    got = _rank(rows)
    if got is None:
        return
    assert got == ["Breakout, strong, 71%", "Breakout, strong, TD 64%", "Breakout, strong", "Breakout, thin",
                   "Good, big case", "Aaron tie", "Zed tie"], got


def test_the_struggle_list_ranks_the_case_against():
    rows = [{"player": "Tough, many", "read": "tough", "pro": [], "con": ["a", "b", "c"]},
            {"player": "Avoid, one", "read": "avoid", "pro": [], "con": ["a"]},
            {"player": "Avoid, three", "read": "avoid", "pro": ["p"], "con": ["a", "b", "c", "d"]}]
    got = _rank(rows, shine=False)
    if got is None:
        return
    assert got == ["Avoid, three", "Avoid, one", "Tough, many"], got


def test_each_row_carries_its_number_through_the_fold():
    top = _fn("renderScanTop")
    assert "scanRanked(rows.filter((x) => x.read === \"breakout\" || x.read === \"good\"), true)" in top
    assert "row(x, i + SCAN_TOP_N, up)" in top, "the fold keeps counting"
    assert "· ranked</span>" in top
    row = _fn("scanTopRowHTML")
    assert '<span class="sct-rank${rank <= 3 ? " top" : ""}">${rank}</span>' in row
    assert ".sct-rank.top { color: var(--brand); }" in CSS and ".sct-row.ranked {" in CSS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
