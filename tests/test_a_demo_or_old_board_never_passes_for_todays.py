"""Audit item 2: a demo or old board never passes for today's.

Ethan's product audit, 2026-09-23: the public page read "Sample data" in
a corner badge over a slate dated August 17 — thirty-six days old — on a
site that calls itself real-time. A visitor concludes the thing is not
active. Now the banner names both cases: a demo board (built from the
sample slate) and an old slate (a real board whose newest game is a week
or more behind today, however fresh the build). Dates here are computed
from today, so the test cannot age.
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


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _run(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const REAL_BOARDS = ["schedule-only"];
      const STANDALONE_MODES = ["fantasy", "intel"];
      const REFERENCE_VIEWS = ["about"];
      const state = {{ view: "recommended" }};
      const escapeHtml = (s) => String(s);
      const icon = () => "<i></i>";
      const formatGameDate = (s) => "DATE(" + s + ")";
      {_fn("boardIsReal")}
      {_fn("slateNotice")}
      {_fn("slateNoticeHTML")}
      const et = (daysAgo) => {{
        const t = new Date(Date.now() - daysAgo * 86400000);
        return new Intl.DateTimeFormat("en-CA", {{ timeZone: "America/New_York" }}).format(t);
      }};
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_two_cases_and_everything_that_is_neither():
    got = _run("""
      const live = (games, extra) => ({ generated_from: "live-oddsapi", games, ...(extra || {}) });
      const out = {
        demo: slateNotice({ generated_from: "sample-slate", games: [{ date: et(0) }] }),
        old: slateNotice(live([{ date: et(40) }, { date: et(36) }])),
        today: slateNotice(live([{ date: et(0) }])),
        sunday: slateNotice(live([{ date: et(3) }])),
        tomorrow: slateNotice(live([{ date: et(-1) }])),
        sched: slateNotice({ generated_from: "schedule-only", games: [{ date: et(2) }] }),
        notBuilt: slateNotice({ date: "", status: "not built" }),
        offseason: slateNotice(live([{ date: et(90) }], { status: "offseason" })),
        noGames: slateNotice(live([])),
      };
      state.view = "fantasy"; out.standalone = slateNotice({ generated_from: "sample-slate" });
      state.view = "about"; out.reference = slateNotice({ generated_from: "sample-slate" });
      out.demoHTML = slateNoticeHTML({ kind: "demo" });
      out.oldHTML = slateNoticeHTML(out.old);
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["demo"] == {"kind": "demo"}, "a sample board is not called a demo"
    assert got["old"]["kind"] == "old" and got["old"]["days"] == 36, got["old"]
    for k in ("today", "sunday", "tomorrow", "sched", "notBuilt", "offseason", "noGames", "standalone", "reference"):
        assert got[k] is None, f"{k}: a notice where there is nothing wrong"
    assert "Demo board." in got["demoHTML"] and "not today’s slate" in got["demoHTML"] and "nothing here is a pick" in got["demoHTML"]
    assert 'href="#record"' in got["demoHTML"], "the record is the real thing — say where it is"
    flat = " ".join(got["oldHTML"].split())
    assert "36 days ago." in flat and "nothing below is today’s" in flat


def test_the_bar_orders_them_after_the_connection_and_before_the_age():
    i = APP.index("function renderStaleBar(ageMs, ago)")
    body = APP[i:APP.index("\n}\n", i)]
    assert body.index("wireDown()") < body.index("slateNotice(state.data)") < body.index("STALE_LOUD_MS"), \
        "offline and unreachable still outrank it; a demo board outranks the age"
    assert 'notice.kind === "demo"' in body and "if (!bad && notice)" in body


def test_the_corner_badge_says_demo():
    fn = _fn("renderDataSource")
    assert '"Live data" : "Demo data"' in fn and "Sample data" not in fn.split("//")[0] + fn[fn.index("el.innerHTML"):]
    assert "not today’s board" in fn


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
