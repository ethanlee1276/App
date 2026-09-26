"""The record's headline reads Lifetime, or the last 90, 30 or 7 days.

Ethan's product audit, 2026-09-23, item 5: "Then allow users to open:
Lifetime → 90 Days → 30 Days → NFL → MLB → NBA → Props → Game Lines."
The sports were already a click away (the scope bar) and so were the
markets (the splits room). The windows lived only on the running P&L,
deep in a room, while the headline at the top of the page always read
the whole record.

Three rules this file holds:

  * ONE STATE. The headline and the running P&L read the same
    `_recRange` through the same helpers, so the number at the top and
    the chart under it can never be reading different windows.
  * FROM THE SCOPE'S OWN CURVE. A window is cut from the days the scope
    in view already ships — every sport has its windows, and the engine
    runs no extra scan.
  * ONLY WHAT MOVES SAYS IT MOVED. A note under the ribbon names the
    window and says everything else is the whole record; a window with
    nothing settled keeps the whole record on the ribbon and says so.
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


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      let _recRange = "all";
      {_fn("recRanges")}
      {_fn("recRangesFor")}
      {_fn("recRangeKey")}
      {_fn("recRangeFrom")}
      {_fn("recRangeTotals")}
      {_fn("recordWindowHTML")}
      {_fn("recWinDate")}
      const ago = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);
      const day = (n, w, l, n2, u) => ({{ date: ago(n), w, l, n: n2, staked: w + l, day_u: u }});
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


def test_a_window_is_offered_only_when_it_is_not_the_whole_record():
    got = _node("""
      const keys = (c) => recRangesFor(c).map(([k]) => k);
      return { young: keys([day(48, 1, 0, 1, 0.9), day(1, 0, 1, 1, -1)]),
               old: keys([day(120, 1, 0, 1, 0.9), day(1, 0, 1, 1, -1)]),
               one: keys([day(3, 1, 0, 1, 0.9)]), none: keys([]), nil: keys(null),
               labels: recRanges().map(([, , l]) => l) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["labels"] == ["Lifetime", "90 days", "30 days", "7 days"], "the audit's words, in its order"
    assert got["young"] == ["all", "1m", "1w"], "48 days of record: the 90 days would BE the record"
    assert got["old"] == ["all", "3m", "1m", "1w"]
    assert got["one"] == got["none"] == got["nil"] == ["all"]


def test_a_stale_choice_falls_back_to_lifetime_and_the_window_starts_n_days_back():
    got = _node("""
      const avail = recRangesFor([day(48, 1, 0, 1, 0.9), day(1, 0, 1, 1, -1)]);
      _recRange = "3m"; const stale = recRangeKey(avail);
      _recRange = "1m"; const kept = recRangeKey(avail);
      return { stale, kept, all: recRangeFrom(avail, "all"), month: recRangeFrom(avail, "1m"),
               want: ago(30), bogus: recRangeFrom(avail, "nope") };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["stale"] == "all", "a window this scope cannot fill does not linger"
    assert got["kept"] == "1m"
    assert got["all"] == "" and got["bogus"] == "", "no Date math on Infinity"
    assert got["month"] == got["want"]


def test_a_windows_headline_is_its_own_days():
    got = _node("""
      // Each day's units are rounded; the running total is not. The day
      // before the window closed the running total at +4.004; the last
      // day in it at +6.467 — a net of +2.46 over the window.
      const cum = (row, c) => ({ ...row, cum_u: c });
      const curve = [cum(day(45, 4, 1, 5, 4.00), 4.004),
                     cum(day(20, 3, 1, 5, 1.73), 5.736), cum(day(10, 2, 2, 4, -0.18), 5.556),
                     cum(day(2, 1, 0, 1, 0.91), 6.467)];
      const bare = curve.map(({ cum_u, ...p }) => p);
      return { t: recRangeTotals(curve, ago(30)), bare: recRangeTotals(bare, ago(30)),
               whole: recRangeTotals(curve, ""),
               old: recRangeTotals([{ date: ago(3), n: 2, day_u: 1 }], ago(30)),
               none: recRangeTotals(curve, ago(1)), nil: recRangeTotals(null, ago(30)),
               quiet: recRangeTotals([day(2, 0, 0, 0, 0)], ago(30)) };""")
    if got is None:
        print("  SKIP node not installed"); return
    t = got["t"]
    assert (t["wins"], t["losses"], t["settled"], t["pushes"]) == (6, 3, 10, 1), t
    assert t["net_units"] == 2.46 and t["units_staked"] == 9, "the running total's own difference"
    assert abs(t["roi"] - 2.46 / 9) < 1e-9, "ROI on stake at risk — the verdict's own definition"
    assert got["whole"]["net_units"] == 6.47 and got["whole"]["settled"] == 15, "from the start, no base to subtract"
    assert got["bare"]["net_units"] == 2.46, "an older curve without cum_u falls back to the days' own units"
    assert got["old"] is None, "a curve without w/l cannot state a window's record"
    assert got["none"] is None and got["nil"] is None and got["quiet"] is None


def test_the_bar_lights_one_chip_and_hides_when_there_is_no_choice():
    got = _node("""
      const avail = recRangesFor([day(120, 1, 0, 1, 0.9), day(1, 0, 1, 1, -1)]);
      return { html: recordWindowHTML(avail, "1m"), lone: recordWindowHTML([["all", Infinity, "Lifetime"]], "all"),
               date: recWinDate("2026-08-24") };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert 'role="group" aria-label="Time window"' in got["html"]
    chips = re.findall(r'data-win="([^"]+)"\s+aria-pressed="(true|false)">([^<]+)<', got["html"])
    assert chips == [("all", "false", "Lifetime"), ("3m", "false", "90 days"),
                     ("1m", "true", "30 days"), ("1w", "false", "7 days")], chips
    assert got["html"].count("rec-win active") == 1
    assert got["lone"] == "", "one choice is not a choice"
    assert got["date"] == "Aug 24"


def test_the_headline_reads_the_window_from_the_scopes_own_curve():
    body = _fn("renderRecord")
    assert "const avail = recRangesFor(src.curve);" in body, "the scope in view's curve, not the pooled one"
    assert "const rk = recRangeKey(avail);" in body and "const from = recRangeFrom(avail, rk);" in body
    assert "const winO = from ? recRangeTotals(src.curve, from) : null;" in body
    assert "recordRibbonsHTML(d, { ...winO, label: `Model · last ${winDays} days` }," in body
    assert '(src.recent || []).filter((r) => String((r || {}).date || "") >= from))' in body, \
        "the form dots are the window's own"
    assert ": recordRibbonsHTML(d, o, src.recent);" in body, "no window, or an empty one: the whole record"
    j = body.rindex("host.innerHTML = scopeBar + winBar")
    tail = body[j:j + 400]
    assert tail.index("rec-ribbons") < tail.index("winNote") < tail.index("_recordRooms("), \
        "scopes, windows, headline, the note, then the rooms"
    assert "Everything else here is the whole record." in body
    assert "headline is the whole record." in body, "an empty window says the ribbon did not move"
    assert 'tile(ov.label || "Model · graded in public", wl(ov),' in _fn("recordRibbonsHTML")


def test_the_chart_and_the_headline_share_one_window():
    ra = _fn("recAnalytics")
    assert "const avail = recRangesFor(curve);" in ra and "const rk = recRangeKey(avail);" in ra
    assert "const from = recRangeFrom(avail, rk);" in ra
    assert "RANGES = [" not in ra, "no second list of windows to drift from the first"
    bind = _fn("bindRecordScopes")
    assert 'host.querySelectorAll(".rec-win").forEach((b) =>' in bind
    assert 'window._recSetRange(b.dataset.win || "all")' in bind, "the chart's own setter — one state"
    assert 'window._recSetRange = (k) => { _recRange = k; renderRecord(); };' in APP


def test_the_window_bar_is_quieter_than_the_scope_bar():
    assert ".rec-windows { display: flex; flex-wrap: wrap; gap: 6px; margin: -4px 0 12px; }" in CSS
    rule = CSS[CSS.index(".rec-win {"):CSS.index("}", CSS.index(".rec-win {"))]
    assert "var(--hairline) solid var(--border)" in rule and "min-height: 30px" in rule
    assert ".rec-win.active {" in CSS and ".rec-win-note {" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
