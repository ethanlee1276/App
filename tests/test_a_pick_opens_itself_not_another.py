"""A tap on a Most Likely pick opens that pick — never another of the
player's.

Ethan, 2026-09-25: "we will show a most likely bet, so I click on the prop
to get a deeper dive on the prop itself and it will pull up a different
prop. I tried too click on Geno Smith under 1.5 TD passed and it pulled up
Geno Smith over 199 passing yards."

Two lookups could do it. The pick page re-found its Most Likely row by
player and market (`likelyFor`, the first match), and the matchup scan's
door fell back to "his first Most Likely pick" — any market — when the
exact row it named missed. Now every Most Likely door names its row by its
exact id (`likelyOpen`, `likelyDoor`), `openProp` keeps that id
(`state.propLikelyId`) and the page draws that row over its own market's
prop, and the scan's door never leaves the market it named.
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


YDS = {"player": "Geno Smith", "team": "SEA", "kind": "prop", "market": "pass_yds",
       "market_label": "Pass Yards", "side": "OVER", "line": 199.5, "odds": -190, "model_prob": 0.71}
TD = {"player": "Geno Smith", "team": "SEA", "kind": "prop", "market": "pass_td",
      "market_label": "Pass TDs", "side": "UNDER", "line": 1.5, "odds": -180, "model_prob": 0.66}


def _node(js, ml):
    if not shutil.which("node"):
        return None
    prog = ("var escapeAttr=(s)=>String(s==null?'':s);"
            f"var state={{data:{{most_likely:{json.dumps(ml)}, recommendations: []}}}};"
            "var gameBetOpenable=()=>false, gameBetId=()=>'', propOpenable=()=>true, slugify=(s)=>s;\n"
            + "".join(_fn(n) for n in ("propId", "likelyOpen", "scanPickRow", "scanDoor"))
            + f"\nconsole.log(JSON.stringify((() => {{ {js} }})()));")
    path = os.path.join(tempfile.mkdtemp(), "d.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def test_the_row_door_names_the_row_it_is_on():
    got = _node("return [likelyOpen(%s), likelyOpen(%s)];" % (json.dumps(YDS), json.dumps(TD)), [YDS, TD])
    if got is None:
        return
    assert got == [' data-open="likely:Geno Smith|pass_yds|OVER|199.5"',
                   ' data-open="likely:Geno Smith|pass_td|UNDER|1.5"'], got


def test_the_scan_door_never_leaves_the_market_it_named():
    # The read names his passing-TD pick, but at a line the board no longer
    # carries (a locked or moved number): the door still opens a TD pick.
    read = {"player": "Geno Smith", "team": "SEA", "lean": ["pass_yds", "pass_td"],
            "pick": {"player": "Geno Smith", "market": "pass_td", "side": "UNDER", "line": 0.5}}
    got = _node("return scanDoor(%s);" % json.dumps(read), [YDS, TD])
    if got is None:
        return
    assert "pass_td|UNDER|1.5" in got["attrs"], got
    assert "Pass TDs" in got["what"]
    # With no pick named, his first Most Likely pick on a leaned market is fine.
    got = _node("return scanDoor(%s);" % json.dumps(dict(read, pick=None)), [YDS, TD])
    assert "pass_yds" in got["attrs"], got


def test_the_page_draws_the_tapped_row():
    op = _fn("openProp")
    assert "const lkRow = opts.likely ? findLikelyProp(id) : null;" in op
    assert "state.propLikelyId = lkRow ? propId(lkRow) : null;" in op
    page = _fn("renderPropPage")
    assert "findLikelyProp(state.propLikelyId)" in page
    assert "r.market !== lkRow.market" in page, "never another of his props under the pick"
    assert "const lk = state.propLikely ? (lkRow || likelyFor(r)) : betPickFor(r);" in page


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
