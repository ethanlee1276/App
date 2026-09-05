"""Clicking a recommendation shows how its price has moved.

Ethan, 2026-08-19, with a Polymarket screenshot: "add where we can click
on the trade it's recommending and it will pull up a chart of the live
odds just how Kalshi or Polymarket does it."

Both venues' adapters have written a 10-minute price snapshot on every
refresh since they shipped — `kalshi_snapshots` and `pm_snaps`. Nothing
had ever read them back. This is that read-back, the payload that carries
it, and the rules that keep the chart honest.

THE HONESTY PROBLEM IS SPECIFIC AND WORTH NAMING. Polymarket can draw a
market's whole life because it IS the market. We can only draw what we
watched. So:

  * no interpolation and no backfill — an order book cannot be
    reconstructed, and a smooth line through hours nobody recorded is a
    picture of a market that did not exist;
  * a gap in the record draws as a gap (`connectNulls: false`);
  * fewer than two observed buckets gets NO chart, because one point is
    not a line and a single dot invites "it has been flat";
  * and the caption says the window is ours, so nobody reads the left
    edge as the market's open.

Run directly: `python3 tests/test_price_tape.py`
"""

import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import pm_build                                                 # noqa: E402
from engine import predmarket as pm                             # noqa: E402
from engine.db import connect                                   # noqa: E402
from engine.sources import kalshi as kx                         # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()


# --- the read-backs ----------------------------------------------------------
def _kalshi_conn(prices, start=1000.0, step=700.0):
    conn = connect(":memory:")
    for i, p in enumerate(prices):
        kx.store_snapshot(conn, [{"ticker": "T1", "prob": p, "spread_cents": 4,
                                  "volume_24h": 100, "open_interest": 9,
                                  "title": "x"}], now=start + i * step)
    return conn


def test_the_kalshi_tape_comes_back_oldest_first():
    conn = _kalshi_conn([0.50, 0.53, 0.58])
    got = kx.price_series(conn, "T1", hours=24, now=3200.0)
    assert [round(p["prob"], 2) for p in got] == [0.50, 0.53, 0.58]
    assert got == sorted(got, key=lambda p: p["ts"]), "not chronological"


def test_the_window_is_a_window():
    conn = _kalshi_conn([0.50, 0.53, 0.58])
    assert kx.price_series(conn, "T1", hours=24, now=10 ** 9) == [], \
        "an ancient snapshot answered a question about today"


def test_a_market_we_never_watched_has_no_history_rather_than_a_flat_line():
    conn = _kalshi_conn([0.5])
    assert kx.price_series(conn, "NEVER-SEEN", hours=24, now=3200.0) == []


def test_the_polymarket_tape_reads_back_the_same_way():
    conn = connect(":memory:")
    for i, y in enumerate([0.41, 0.44, 0.39]):
        pm.store_snapshot(conn, [{"slug": "s1", "question": "q", "yes": y,
                                  "vol24": 10, "liquidity": 5,
                                  "end_date": "2026-09-01"}],
                          now=1000.0 + i * 700)
    got = pm.price_series(conn, "s1", hours=24, now=3200.0)
    assert [round(p["prob"], 2) for p in got] == [0.41, 0.44, 0.39]


# --- what the build hangs on a row ------------------------------------------
def test_a_row_gets_its_tape_and_an_unwatched_row_does_not():
    conn = _kalshi_conn([0.50, 0.53, 0.58, 0.55])
    rows = [{"ticker": "T1"}, {"ticker": "T2"}]
    assert pm_build._attach_tape(conn, rows, kx.price_series, "ticker",
                                 now=3900.0) == 1
    assert len(rows[0]["tape"]) == 4
    assert rows[0]["tape"][0][0] < rows[0]["tape"][-1][0]
    assert "tape" not in rows[1]


def test_one_observation_is_not_a_line():
    """The rule that keeps a brand-new market from claiming a history. A
    chart drawn through a single dot reads as "it has been flat here",
    which is precisely what one observation cannot tell you."""
    conn = _kalshi_conn([0.62])
    rows = [{"ticker": "T1"}]
    assert pm_build._attach_tape(conn, rows, kx.price_series, "ticker",
                                 now=1500.0) == 0
    assert "tape" not in rows[0]


# --- the board row carries it through ---------------------------------------
def test_the_board_projection_does_not_drop_the_tape():
    """`pmVenueRows` rebuilds every payload row into a board row, and
    anything the projection forgets does not exist downstream. It forgot
    the tape in the first cut, which drew no chart and threw no error."""
    fn = APP[APP.index("function pmVenueRows("):]
    fn = fn[:fn.index("\nconst PM_BOARD_SHOWN")]
    assert fn.count("tape:") >= 2, \
        "a venue's rows lost the price history on the way to the panel"


def test_the_recommendation_itself_is_clickable():
    """The desk's rows ARE "the trade it's recommending", and they were
    the one row shape on the page with no way in."""
    desk = APP[APP.index("function deskSectionHTML("):]
    desk = desk[:desk.index("\nfunction ", 10)]
    assert "_pmPick" in desk, "the recommendation rows open nothing"
    assert "r.ticker ?" in desk, \
        "a weather row with no ticker must not open an empty panel"
    # And the board's own rows, not just their View button.
    row = APP[APP.index("function pmBoardRowHTML("):]
    row = row[:row.index("\nfunction ", 10)]
    assert "kx-row openable" in row and "_pmPick" in row


# --- the honesty rules, in the code that draws ------------------------------
def test_a_gap_in_the_record_draws_as_a_gap():
    tape = VIS[VIS.index('} else if (kind === "tape") {'):]
    tape = tape[:tape.index('} else if (kind === "radar")')]
    assert "connectNulls: false" in tape, \
        "a break in our recording would be drawn as a straight line through it"
    assert "smooth: false" in tape, \
        "a smoothed curve invents prices between the ones we saw"


def test_both_sides_are_drawn_and_labelled_at_the_end():
    """The render shows two lines labelled at the right edge; a binary
    market has two sides and showing one is half an answer."""
    tape = VIS[VIS.index('} else if (kind === "tape") {'):]
    tape = tape[:tape.index('} else if (kind === "radar")')]
    assert "endLabel" in tape
    # One helper, called once per side.
    assert "const line = (" in tape, "the line builder is gone"
    assert "line(yesName" in tape and "line(noName" in tape, \
        "only one side is plotted"


def test_the_caption_says_the_window_is_ours():
    fn = APP[APP.index("function pmTapeHTML("):]
    fn = fn[:fn.index("\nfunction ", 10)]
    assert "our own tape" in fn
    assert "not when the\n      market opened" in fn or "market opened" in fn
    # And the no-history case says so rather than drawing nothing.
    assert "pm-tape-none" in fn and "long enough" in fn


def test_the_fallback_draws_the_real_series_not_a_placeholder():
    """ECharts is a megabyte loaded lazily. On a slow phone the SVG is
    what a reader gets, so it plots the same two real series to scale."""
    fn = APP[APP.index("function pmTapeSVG("):]
    fn = fn[:fn.index("\nfunction ", 10)]
    assert "var(--good)" in fn and "var(--bad)" in fn
    assert "1 - v" in fn, "the fallback draws only one side"


def test_the_mounts_cannot_cancel_each_other():
    """Found while wiring this up: three enhancement mounts chained bare,
    and the first to throw silently cancelled the rest — the chart never
    upgraded, nothing errored, and the SVG fallback made it look like a
    rendering choice rather than dead code."""
    i = APP.index("async function renderIntel()")
    fn = APP[i:APP.index("\n/* =====", i)]
    assert "for (const mount of" in fn and "try {" in fn, \
        "the intel mounts are chained again"


def test_a_screenshot_waits_for_the_chart_to_finish_drawing():
    """THE DATA WAS RIGHT AND THE PICTURE WAS WRONG, and the difference
    was the clock. The tape's chart object held 111 points ending at the
    live price with the axis pinned, while three screenshots of it showed
    a line stopping short — because ECharts eases its lines in and the
    shots were taken inside that window. Measured afterwards on a
    synthetic 111-point tape: 4 of 10 sampled points carried a line pixel
    at 80ms, 5 at 150ms, 6 at 250ms, all 10 by 500ms.

    So `--shots` waits, and the wait has to stay ahead of the animation.
    Raise `animationDuration` without raising the settle and the contact
    sheet quietly goes back to photographing half-drawn charts — which
    reads as a layout regression, which is the one thing that tool must
    never invent."""
    rc = open(os.path.join(ROOT, "rendercheck.py"), encoding="utf-8").read()
    m = re.search(r"const ANIM_SETTLE_MS = (\d+);", rc)
    assert m, "rendercheck no longer settles before a screenshot"
    settle = int(m.group(1))
    durations = [int(d) for d in re.findall(r"animationDuration:\s*(\d+)", VIS)]
    assert durations, "no chart animation duration found to check against"
    assert settle > max(durations), (
        f"screenshots settle for {settle}ms but a chart animates for "
        f"{max(durations)}ms — the contact sheet will catch it mid-draw")


_LINE_PROBE = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2];
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium',
                    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', undefined]) {
  if (path === null) continue;
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const p = await b.newPage({ viewport: { width: 1280, height: 1000 } });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0, 140)));
await p.goto(`http://127.0.0.1:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(2000);

// A tape with a SHAPE WE CHOSE: 111 points ten minutes apart that ramp
// from 20% to 80% and fall back to 35%. None of the site's own data is
// involved — the question is only whether the chart draws what it was
// handed.
await p.evaluate(async () => {
  const N = 111, STEP = 600;
  const t0 = Math.floor(Date.now() / 1000) - (N - 1) * STEP;
  const pts = [];
  for (let i = 0; i < N; i++) {
    const f = i / (N - 1);
    const v = f < 0.6 ? 0.20 + (f / 0.6) * 0.60 : 0.80 - ((f - 0.6) / 0.4) * 0.45;
    pts.push([t0 + i * STEP, +v.toFixed(4)]);
  }
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:20px;top:20px;width:520px;height:260px;z-index:9';
  const plot = document.createElement('div');
  plot.style.cssText = 'width:100%;height:100%';
  plot.setAttribute('data-echart-tape', JSON.stringify(
    { points: pts, yes_label: 'Yes', no_label: 'No' }));
  host.appendChild(plot);
  document.body.appendChild(host);
  await mountEChartsPanels(document.body);
});
await p.waitForTimeout(2500);              // well past animationDuration

const out = await p.evaluate(() => {
  const el = document.querySelector('[data-echart-tape]');
  const chart = window.echarts && window.echarts.getInstanceByDom(el);
  if (!chart) return { error: 'the tape never upgraded to a chart' };
  const yes = chart.getOption().series[0].data;
  const cv = el.querySelector('canvas');
  const g = cv.getContext('2d');
  const dpr = cv.width / cv.getBoundingClientRect().width;
  // ASK THE CANVAS, NOT THE OPTION OBJECT. convertToPixel is ECharts'
  // own data-to-screen map, so this reads the pixel where the library
  // says the point belongs and checks a line was actually painted there.
  const probes = [];
  for (let k = 0; k < 10; k++) {
    const i = Math.round(k * (yes.length - 1) / 9);
    const [x, y] = chart.convertToPixel({ seriesIndex: 0 }, yes[i]);
    let hit = null, best = 1e9;
    for (let dy = -6; dy <= 6; dy++) {
      const px = g.getImageData(Math.round(x * dpr), Math.round((y + dy) * dpr), 1, 1).data;
      if (px[3] > 40 && px[0] + px[1] + px[2] > 90 && Math.abs(dy) < best) {
        best = Math.abs(dy); hit = [px[0], px[1], px[2], dy];
      }
    }
    probes.push({ i, value: yes[i][1], hit });
  }
  return { seriesLen: yes.length, first: yes[0][1], last: yes[yes.length - 1][1],
           good: getComputedStyle(document.documentElement)
                   .getPropertyValue('--good').trim(), probes };
});
console.log(JSON.stringify({ out, errs }));
await b.close();
"""


def _have_node() -> bool:
    try:
        r = subprocess.run(
            ["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
            capture_output=True, cwd=ROOT, timeout=30)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def test_the_line_is_drawn_where_the_data_says_it_is():
    """The claim the option object cannot make. Everything about the
    chart's configuration can be right while the drawing is wrong, and
    the only way to tell them apart is to read the canvas.

    Opt in with QB_BROWSER_TESTS=1 — same reason as the other browser
    halves: Chromium inside the full suite crashed on a busy container,
    and a flaky test teaches people to ignore a real one."""
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return

    sys.path.insert(0, ROOT)
    import rendercheck
    srv, port = rendercheck._serve()
    script = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                         dir=ROOT) as fh:
            fh.write(_LINE_PROBE)
            script = fh.name
        proc = subprocess.run(["node", script, str(port)], cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
    finally:
        if script:
            os.unlink(script)
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr[-1500:]
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    out = res["out"]
    assert not out.get("error"), out["error"]
    assert out["seriesLen"] == 111, f"the chart kept {out['seriesLen']} of 111 points"
    assert abs(out["first"] - 20) < 0.6 and abs(out["last"] - 35) < 0.6, \
        f"the series does not start and end where the data does: {out['first']} → {out['last']}"

    want = tuple(int(out["good"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    missed = [p for p in out["probes"] if not p["hit"]]
    assert not missed, (
        "the line is not painted where the data says it is, at "
        + ", ".join(f"point {p['i']} ({p['value']}%)" for p in missed)
        + ". If every point is missing, the chart drew nothing; if the "
        "LAST ones are missing, the screenshot beat the animation.")
    for p in out["probes"]:
        r, g, bl, _dy = p["hit"]
        assert abs(r - want[0]) < 26 and abs(g - want[1]) < 26 and abs(bl - want[2]) < 26, \
            (f"point {p['i']} ({p['value']}%) is painted rgb({r},{g},{bl}), "
             f"not the Yes colour rgb{want}")
    assert not res["errs"], f"page errors: {res['errs']}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
