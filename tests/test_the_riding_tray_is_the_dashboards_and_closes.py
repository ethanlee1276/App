"""The riding tray lives on the dashboard only, and it closes.

Ethan, 2026-09-23, with the floating "2 bets riding" pill circled over
the Record page's calibration rows: "I don't like this at all. Only show
it on the main dashboard page, and put a little x on it so people can
close it out."

It floated over every page but Live. Now it shows on the dashboard
(`recommended`) alone, and carries an × that closes it for the rest of
the visit. It was one <button>, which cannot hold a second button, so
the tray is a region holding two: the door to Live and the ×.
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
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _run():
    node = shutil.which("node")
    if not node:
        return None
    prog = """
      const store = {}; const sessionStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
      const window = {};
      const handlers = {};
      function el(cls) { return { className: cls, onclick: null }; }
      const tray = { dataset: {}, hidden: true, _html: "", buttons: {},
        set innerHTML(h) { this._html = h; this.buttons = { ".rt-open": el("rt-open"), ".rt-x": el("rt-x") }; },
        get innerHTML() { return this._html; },
        querySelector(s) { return this.buttons[s]; } };
      const body = { cls: new Set(), classList: { toggle(c, on) { on ? body.cls.add(c) : body.cls.delete(c); } } };
      const document = { getElementById: (id) => (id === "riding-tray" ? tray : null), body };
      const state = { view: "recommended" };
      let went = null;
      const switchView = (v) => { went = v; };
      const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
      const escapeHtml = (s) => String(s);
      const trackerBetText = (r) => `${r.player} OVER ${r.line} Hits`;
    """ + _fn("ridingTrayClosed") + _fn("ridingTraySync") + _fn("renderRidingTray") + """
      const out = {};
      renderRidingTray([{ player: "Spencer Torkelson", line: 0.5, current: 0, market: "hits" }, { player: "B", line: 1 }]);
      out.home = { hidden: tray.hidden, pad: body.cls.has("has-tray"), html: tray.innerHTML };
      for (const v of ["record", "live", "likely", "edge", "mybets", "pbp"]) { state.view = v; ridingTraySync(); out[v] = tray.hidden; }
      state.view = "recommended"; ridingTraySync(); out.back = tray.hidden;
      tray.querySelector(".rt-open").onclick(); out.went = went;
      tray.querySelector(".rt-x").onclick();
      out.closed = { hidden: tray.hidden, pad: body.cls.has("has-tray"), stored: store["qb.trayClosed"] };
      renderRidingTray([{ player: "C", line: 1 }]); out.afterRedraw = tray.hidden;
      window._qbTrayClosed = false; ridingTraySync(); out.nextLoadSameVisit = tray.hidden;
      delete store["qb.trayClosed"]; ridingTraySync(); out.newVisit = tray.hidden;
      renderRidingTray([]); out.empty = tray.hidden;
      console.log(JSON.stringify(out));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_it_shows_on_the_dashboard_and_nowhere_else():
    got = _run()
    if got is None:
        print("  SKIP node not installed"); return
    assert got["home"]["hidden"] is False and got["home"]["pad"], "not on the dashboard"
    for v in ("record", "live", "likely", "edge", "mybets", "pbp"):
        assert got[v] is True, f"the tray floats over {v}"
    assert got["back"] is False, "back on the dashboard, it returns"
    assert got["went"] == "live", "the pill still opens the Live tab"
    assert got["empty"] is True, "no bets, no tray"


def test_the_x_closes_it_for_the_rest_of_the_visit():
    got = _run()
    if got is None:
        print("  SKIP node not installed"); return
    assert got["closed"] == {"hidden": True, "pad": False, "stored": "1"}, got["closed"]
    assert got["afterRedraw"] is True, "a refresh of the bets reopened a closed tray"
    assert got["nextLoadSameVisit"] is True, "the visit forgot it was closed"
    assert got["newVisit"] is False, "a new visit brings it back"


def test_the_markup_is_two_buttons_in_a_region():
    assert '<div id="riding-tray" class="riding-tray" hidden role="region" aria-label="Bets riding"></div>' in HTML
    assert '<button type="button" id="riding-tray"' not in HTML, "a button cannot hold the ×"
    tray = _fn("renderRidingTray")
    assert '<button type="button" class="rt-open"' in tray and '<button type="button" class="rt-x" aria-label="Close">&times;</button>' in tray
    for rule in (".rt-open { display: flex;", ".rt-x { flex: 0 0 auto; width: 32px; height: 32px;"):
        assert rule in CSS, rule


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
