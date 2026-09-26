"""The paywall shows the one record, as the ribbon.

Ethan, 2026-09-22, with the pooled ribbon circled on the Record page:
"ok make sure we are updating the paywall site too with the new info.
i also want the paywall site to show this as well."

Two things were wrong. The paywall read the record file raw, so once
the site seated the pooled book (adoptPooledRecord) every page but
the one asking for money had moved on. And it showed four stat tiles
where the rest of the site shows the ribbon. Now it adopts the same
record, leads its results strip with the same ribbon — the model's
tile only; Zeno's book is his, not the product — and keeps beneath it
what the ribbon does not say: the win rate against the break-even
our prices require, and the units staked to earn the number.
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


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 1]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const MINUS = "\\u2212";
      {_const("PROOF_RATE_FLOOR")}
      {_fn("zenoMoney")}
      {_fn("recordRibbonsHTML")}
      {_fn("adoptPooledRecord")}
      {_fn("pwResultsHTML")}
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


def test_the_paywall_reads_the_same_record_as_every_other_page():
    body = _fn("renderPaywall")
    assert "if (r.ok) rec = adoptPooledRecord(await r.json());" in body, "the paywall reads the file raw and quotes the edge book"
    i = body.index("host.innerHTML = paywallHTML(rec, _pwStatus);")
    assert "sweepRings(host);" in body[i:i + 120], "the ring does not sweep on the wall"


def test_the_results_strip_leads_with_the_ribbon_and_keeps_what_it_lacks():
    body = _fn("pwResultsHTML")
    # Ethan, 2026-09-26: "we need to display the new combined record here
    # too on the paywall" — the combined line leads with its split, then
    # the model's tile, then Zeno's, as on the Record page.
    assert ("const ribbon = recordRibbonsHTML({ combined: rec && rec.combined, zeno: rec && rec.zeno }, o,\n"
            "                                   (rec && rec.recent) || []);") in body
    assert '<div class="hd-stats rec-ribbons pw-ribbon">${ribbon}</div>' in body
    assert '<div class="pw-stats pw-stats-two">' in body
    assert 'stat(o.settled, `graded' not in body and '"record")' not in body and '"net, flat stakes"' not in body, \
        "the ribbon says these; a tile restating them makes the reader meet a number twice"
    assert "o.settled >= PROOF_RATE_FLOOR" in body and "o.units_staked" in body
    assert ".pw-results .rec-ribbons { margin: 0 0 12px; text-align: left; }" in CSS
    assert ".pw-results .pw-stats-two { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in CSS


def test_the_wall_prints_the_pooled_book_then_zenos():
    got = _node("""
      const file = { overall: { settled: 40, wins: 20, losses: 20, pushes: 0, net_units: -1, roi: -0.025, units_staked: 40, win_rate: .5, breakeven: .524 },
        recent: [{ status: "won" }],
        pooled: { overall: { settled: 60, wins: 35, losses: 24, pushes: 1, net_units: 7.6, roi: 0.017, units_staked: 445.2, win_rate: .593, breakeven: .529 },
                  recent: [{ status: "won" }, { status: "won" }, { status: "lost" }] },
        zeno: { overall: { settled: 38, wins: 21, losses: 17, profit: 412.5, staked: 2140 }, recent: [{ result: "won" }] } };
      const rec = adoptPooledRecord(file);
      return { html: pwResultsHTML(rec), thin: pwResultsHTML({ overall: { settled: 3, wins: 2, losses: 1, breakeven: .52, units_staked: 3 } }),
               none: pwResultsHTML({ overall: { settled: 0 } }) };""")
    if got is None:
        print("  SKIP node not installed"); return
    h = got["html"]
    assert "35-24-1" in h and "+1.7% ROI" in h and "+7.6u · 60 settled" in h, "the pooled book, not the edge book"
    assert "20-20" not in h, "the edge book's own record must not leak onto the wall"
    assert h.count('class="hd-ribbon"') == 2 and "Zeno · his own book" in h, "the model's, then Zeno's (no combined in this file)"
    assert h.index("Model") < h.index("Zeno · his own book"), "the model's tile before his"
    assert 'data-pc="59"' in h and '<i class="w">W</i><i class="w">W</i><i class="l">L</i>' in h
    assert "59.3%" in h and "52.9% needed at our prices" in h and "445.2u" in h and "+7.60u" in h
    assert "hd-ribbon" in got["thin"] and "52.0%" in got["thin"] and "needed at the prices we took" in got["thin"], \
        "a thin sample still shows the ribbon and the bar, never a rate"
    assert got["none"] == ""


def test_the_wall_leads_with_the_combined_line_and_its_split():
    got = _node("""
      const file = { overall: { settled: 40, wins: 20, losses: 20, net_units: -1, roi: -0.025, units_staked: 40 },
        pooled: { overall: { settled: 2112, wins: 1236, losses: 867, pushes: 9, net_units: 4.3, roi: 0.008, units_staked: 521.5,
                             win_rate: .588, breakeven: .57 }, recent: [] },
        zeno: { overall: { settled: 1389, wins: 221, losses: 1141, pushes: 27, profit: 8001.64, roi: 0.2607, staked: 30692.9,
                           net_units: 800.16 }, unit_dollars: 10, recent: [] },
        combined: { settled: 3501, wins: 1457, losses: 2008, pushes: 36, net_units: 804.46, roi: 0.223, units_staked: 3590.8,
                    unit_dollars: 10, split: { model: { net_units: 4.3 }, zeno: { net_units: 800.16 } } } };
      return pwResultsHTML(adoptPooledRecord(file));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got.count('class="hd-ribbon"') == 3
    assert got.index("Everything we’ve bet") < got.index("Model") < got.index("Zeno · his own book")
    assert "1457-2008-36" in got and "model +4.3u · Zeno +800.2u (1u = $10)" in got, "the split rides the tile"
    assert "the model’s win rate" in got and "the model staked to earn" in got, "the stats beneath are the model's"


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
