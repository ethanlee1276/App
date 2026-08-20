"""The waterfall is checked before it is drawn — executed, not read.

A derivation display is persuasive furniture: rows, a bar, a running
total, an answer. That is exactly what makes it dangerous. Drop a factor
from the display and it still looks like arithmetic; a reader has no way
to tell a chain that reaches its answer from one that stops short and
prints the answer anyway.

So `chainHTML` refuses. `chainCloses` multiplies the recorded steps back
out, and if they do not reach the projection that shipped the section
says so instead of drawing it. A static assertion that the string
`chainCloses(c)` appears in the file proves nothing about whether it
returns false for a broken chain — so this runs it.

The other half executed here is the SIDE of the comps. The stored comp
rate is always the over's; quoting it under an under pick prints the
record upside down, which is the single most damaging error this page
could make, because it would look right.

tests/test_chain.py holds the engine side and needs no Node.

Run directly: `python3 tests/test_chainrender.py`
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil as _shutil                                    # noqa: E402
if not _shutil.which("node"):
    print("SKIP node is not installed; this file executes the derivation "
          "renderer rather than reading it. `apt install -y nodejs`")
    print("\n0 tests passed.")
    raise SystemExit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("{", i)
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(f"{name} has unbalanced braces")


def _const(name):
    i = APP.index(f"const {name} = ")
    j = APP.index("{", i) if "{" in APP[i:i + 40] else -1
    if j < 0:
        return APP[i:APP.index(";", i) + 1]
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 2]
    raise AssertionError(f"{name} has unbalanced braces")


_STUBS = """
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function icon(n) { return `<i data-i="${n}"></i>`; }
function pct(v) { return (Number(v) * 100).toFixed(1) + "%"; }
"""


def _run(script):
    src = (_STUBS
           + _const("CHAIN_FLAT") + "\n" + _const("CHAIN_WINDOWS") + "\n"
           + "\n".join(_fn(n) for n in (
               "chainProduct", "chainCloses", "chainStepRow", "chainHTML",
               "checksHTML", "compsHTML"))
           + "\n" + script)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def _chain():
    from engine import pipeline
    out = pipeline.run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    recs = sorted(out["recommendations"],
                  key=lambda r: -sum(1 for s in r["chain"]["steps"]
                                     if abs(s["mult"] - 1) >= 0.02))
    return recs[0]


_REC = None


def rec():
    global _REC
    if _REC is None:
        _REC = _chain()
    return _REC


# ---------------------------------------------------------------- guard

def test_the_guard_agrees_with_the_engine_on_a_real_chain():
    from engine import chain
    c = rec()["chain"]
    got = _run(f"const c = {json.dumps(c)};"
               "console.log(JSON.stringify([chainProduct(c), chainCloses(c)]));")
    assert got[1] is True
    assert abs(got[0] - chain.product(c)) < 1e-6, (got[0], chain.product(c))


def test_the_guard_rejects_a_chain_with_a_factor_removed():
    """The failure mode the whole section is built against."""
    c = rec()["chain"]
    moved = [i for i, s in enumerate(c["steps"]) if abs(s["mult"] - 1) >= 0.02]
    assert moved, "no step on this pick moved enough to make the test real"
    broken = {**c, "steps": [s for i, s in enumerate(c["steps"])
                             if i != moved[0]]}
    assert _run(f"console.log(JSON.stringify(chainCloses({json.dumps(broken)})));") \
        is False


def test_a_chain_that_does_not_close_is_withheld_rather_than_drawn():
    c = rec()["chain"]
    moved = [i for i, s in enumerate(c["steps"]) if abs(s["mult"] - 1) >= 0.02]
    broken = {**c, "steps": [s for i, s in enumerate(c["steps"])
                             if i != moved[0]]}
    html = _run("console.log(JSON.stringify(chainHTML(" +
                json.dumps({"chain": broken, "line": 50}) + ")));")
    assert "do not multiply back" in html
    assert "ch-row" not in html, "a broken chain still drew its waterfall"


# ---------------------------------------------------------------- the ledger

def test_the_running_total_ends_on_the_projection():
    """What a reader follows down the right-hand column has to arrive
    where the card said it would."""
    r = rec()
    html = _run("console.log(JSON.stringify(chainHTML(" +
                json.dumps({"chain": r["chain"], "line": r["line"]}) + ")));")
    import re
    runs = re.findall(r'class="ch-run">([-−\d.]+)<', html)
    assert runs, "no running totals rendered"
    mean = float(r["chain"]["mean"])
    assert abs(float(runs[-1]) - mean) < 0.06, (runs[-1], mean)
    assert abs(float(runs[0]) - float(r["chain"]["base"]["value"])) < 0.06


def test_flat_factors_get_no_row_but_are_still_named():
    """Six blank rows would bury the two factors that did the work; simply
    dropping them would hide that the model looked."""
    r = rec()
    c = r["chain"]
    flat = [s for s in c["steps"] if abs(s["mult"] - 1) < 0.005]
    assert flat, "this pick has no flat step — pick another fixture"
    html = _run("console.log(JSON.stringify(chainHTML(" +
                json.dumps({"chain": c, "line": r["line"]}) + ")));")
    assert html.count('class="ch-row') == len(c["steps"]) - len(flat)
    assert "looked and changed nothing" in html
    for s in flat:
        assert s["label"].lower() in html, s["label"]


def test_the_direction_follows_the_multiplier_both_ways():
    base = {"base": {"value": 100.0, "label": "Form blend", "weights": {},
                     "sample_games": 10}, "mean": 100.0, "steps": []}
    up = {**base, "steps": [{"key": "matchup", "label": "Matchup", "mult": 1.2,
                             "why": ""}], "mean": 120.0}
    down = {**base, "steps": [{"key": "matchup", "label": "Matchup", "mult": 0.8,
                               "why": ""}], "mean": 80.0}
    got = _run("console.log(JSON.stringify(["
               + f"chainHTML({json.dumps({'chain': up, 'line': 100})}),"
               + f"chainHTML({json.dumps({'chain': down, 'line': 100})})]));")
    assert "raised it 20.0%" in got[0] and "i class=\"up\"" in got[0]
    assert "cut it 20.0%" in got[1] and "i class=\"down\"" in got[1]


# ---------------------------------------------------------------- gates

def test_a_failed_condition_reads_as_failed_and_says_why_it_matters():
    cs = [{"key": "edge", "label": "Edge over the price", "passed": False,
           "value": "+0.4%", "limit": "+2.0% or better"},
          {"key": "juice", "label": "Price worth laying", "passed": True,
           "value": "-110", "limit": "-350 or better"}]
    html = _run("console.log(JSON.stringify(checksHTML(" +
                json.dumps({"checks": cs}) + ")));")
    assert 'class="ck-row no"' in html and 'class="ck-row ok"' in html
    assert "1 of 2 not met" in html


def test_all_clear_says_what_recommended_means():
    cs = [{"key": "edge", "label": "Edge", "passed": True, "value": "+4%",
           "limit": "+2% or better"}]
    html = _run("console.log(JSON.stringify(checksHTML(" +
                json.dumps({"checks": cs}) + ")));")
    assert "All 1 met" in html
    assert "not a feeling about the matchup" in html


# ---------------------------------------------------------------- comps

def test_an_under_pick_is_quoted_from_the_under():
    """THE ERROR THAT WOULD LOOK RIGHT. The stored rate is the over's, so
    an under pick must be shown its complement — otherwise a 30% record is
    published as a 70% one, on the page about honesty."""
    c = {"n": 400, "hit_rate": 0.70, "push": 0, "own": 0,
         "form_lo": 1.0, "form_hi": 2.0}
    got = _run("console.log(JSON.stringify(["
               + f"compsHTML({json.dumps({'comps': c, 'side': 'OVER', 'hit_prob': 0.70})}),"
               + f"compsHTML({json.dumps({'comps': c, 'side': 'UNDER', 'hit_prob': 0.30})})]));")
    assert ">70%</b> of 400" in got[0] and "to the over" in got[0], got[0]
    assert ">30%</b> of 400" in got[1] and "to the under" in got[1], got[1]


def test_a_stored_side_rate_wins_over_the_complement():
    """The engine sides it already; the front end's arithmetic is only the
    fallback for a payload that predates that."""
    c = {"n": 400, "hit_rate": 0.70, "side_rate": 0.42, "push": 0, "own": 0,
         "form_lo": 1.0, "form_hi": 2.0}
    html = _run("console.log(JSON.stringify(compsHTML(" +
                json.dumps({"comps": c, "side": "UNDER", "hit_prob": 0.40}) + ")));")
    assert ">42%</b> of 400" in html, html


def test_a_disagreement_is_flagged_as_a_flag_and_not_a_verdict():
    c = {"n": 400, "hit_rate": 0.70, "push": 0, "own": 0,
         "form_lo": 1.0, "form_hi": 2.0}
    got = _run("console.log(JSON.stringify(["
               + f"compsHTML({json.dumps({'comps': c, 'side': 'OVER', 'hit_prob': 0.50})}),"
               + f"compsHTML({json.dumps({'comps': c, 'side': 'OVER', 'hit_prob': 0.69})})]));")
    assert "disagree by more than eight points" in got[0]
    assert "a flag, not a verdict" in got[0]
    assert "agree here" in got[1]


def test_no_comps_draws_nothing():
    assert _run("console.log(JSON.stringify(compsHTML({})));") == ""
    assert _run("console.log(JSON.stringify(checksHTML({})));") == ""
    assert _run("console.log(JSON.stringify(chainHTML({})));") == ""


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print("all good" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
