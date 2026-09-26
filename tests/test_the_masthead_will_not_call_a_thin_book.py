"""v5: the masthead will not call a thin book.

Rendered on the sample board, the sidebar of every desktop page read
"Running ROI +90.9%" — off one settled pick. The Record page will not
call a book that thin, and the wall prints no rate off it; the masthead
was the one place on the site a 1-0 book wore a percentage. Under the
engine's own floor it leads with the record and says how far the sample
has to go. At the floor and above, nothing changes.
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
    m = re.search(r"^(async )?function " + name + r"\(", APP, re.M)
    assert m, name
    i = m.start()
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      let _recMinGraded = 30;
      const els = {{ "standing-record": {{ innerHTML: "" }}, "mb-rec": {{ textContent: "", cls: new Set(), classList: {{ toggle(c, on) {{ on ? this.s.add(c) : this.s.delete(c); }}, s: new Set() }} }} }};
      const document = {{ getElementById: (id) => els[id] }};
      let REC = null;
      const loadRecordOnce = async () => REC;
      {_fn("renderStandingRecord")}
      (async () => {{ {js} }})().then((r) => console.log(JSON.stringify(r)));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_under_the_floor_the_record_leads_and_no_roi_is_printed():
    got = _node("""
      const shot = () => ({ html: els["standing-record"].innerHTML.replace(/\\s+/g, " "), brief: els["mb-rec"].textContent, neg: els["mb-rec"].classList.s.has("neg") });
      REC = { min_graded: 30, overall: { settled: 1, wins: 1, losses: 0, pushes: 0, roi: 0.909, net_units: 0.91, units_staked: 1, open: 2 } };
      await renderStandingRecord(); const thin = shot();
      REC = { min_graded: 30, overall: { settled: 30, wins: 14, losses: 16, pushes: 0, roi: -0.12, net_units: -3.6, units_staked: 30 } };
      await renderStandingRecord(); const atFloor = shot();
      REC = { overall: { settled: 160, wins: 92, losses: 66, pushes: 2, roi: 0.095, net_units: 15.2, units_staked: 160 } };
      await renderStandingRecord(); const fed = shot();
      REC = { overall: { settled: 0 } };
      await renderStandingRecord(); const none = shot();
      return { thin, atFloor, fed, none };""")
    if got is None:
        print("  SKIP node not installed"); return
    t = got["thin"]
    assert "Running ROI" not in t["html"] and "%" not in t["html"], "a 1-0 book wears a percentage"
    assert "<b>1-0-0</b>" in t["html"] and "1 settled · 30 needed before the ROI means anything · 2 open" in t["html"]
    assert t["brief"] == "1-0  ·  1 of 30" and not t["neg"]
    a = got["atFloor"]
    assert "Running ROI" in a["html"] and "-12.0%" in a["html"] and "14-16-0" in a["html"], "at the floor the ROI prints, losing or not"
    assert a["brief"] == "-12.0%  ·  14-16" and a["neg"]
    f = got["fed"]
    assert "+9.5%" in f["html"] and "+15.20u on 160.0u staked" in f["html"] and "92-66-2" in f["html"]
    assert f["brief"] == "+9.5%  ·  92-66-2"
    assert "no settled picks yet" in got["none"]["html"]


def test_the_floor_is_the_engines_own():
    fn = _fn("renderStandingRecord")
    assert "const need = rec.min_graded || _recMinGraded;" in fn, "the floor is retyped, or missing"
    assert "const thin = o.settled < need;" in fn
    assert not re.search(r"settled\s*<\s*\d", fn), "a hard-coded floor"


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
