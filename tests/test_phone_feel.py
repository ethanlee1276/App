"""Swipe between sports, pull to refresh, a light buzz.

Ethan, 2026-09-05: "the swipe between sports pull to refresh and light
buzz". The three decisions run for real in node (skipped without it):
where a swipe goes and when it does not, what a pull has earned, and
which settled bet earns a buzz. The wiring is pinned: passive touch
listeners, swipes owned by things that scroll sideways, the pull only
at the top of a board, the browser's own reload-on-pull switched off on
touch screens, a buzz on a slip add and never on a remove, and no buzz
at all without a motor or under reduced motion.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n(function", "\ndocument.")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index("\n", i)] if name != "SWIPE_VIEWS" else APP[i:APP.index("];", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join([_const("SWIPE_MIN_X"), _const("BUZZ"), _const("SETTLE_BUZZ")]
                    + [_fn(n) for n in ("buzz", "swipeTarget", "ptrPhase", "settleChanges")])
    prog = f"""
      let navigator = {{}}, window = {{}};
      {src}
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


def test_a_swipe_moves_one_league_and_never_around_the_end():
    got = _node("""
      const s = ["nfl", "cfb", "mlb"];
      return {
        left: swipeTarget(-90, 5, s, "nfl"), right: swipeTarget(90, -5, s, "cfb"),
        end: swipeTarget(-90, 0, s, "mlb"), start: swipeTarget(90, 0, s, "nfl"),
        short: swipeTarget(-40, 0, s, "nfl"), tall: swipeTarget(-120, 60, s, "nfl"),
        unknown: swipeTarget(-90, 0, s, "ufc"), none: swipeTarget(-90, 0, [], "nfl"),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["left"] == "cfb" and got["right"] == "nfl", got
    assert got["end"] is None and got["start"] is None, "no wrapping around the row"
    assert got["short"] is None and got["tall"] is None, "a short or a mostly-vertical drag is a scroll, not a swipe"
    assert got["unknown"] is None and got["none"] is None


def test_a_pull_earns_the_refresh_only_at_the_top_and_past_the_threshold():
    got = _node("""return [ptrPhase(30, true), ptrPhase(72, true), ptrPhase(120, true), ptrPhase(120, false), ptrPhase(-10, true), ptrPhase(0, true)];""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["pull", "ready", "ready", "idle", "idle", "idle"], got


def test_a_settled_bet_buzzes_once_and_the_first_draw_never_does():
    got = _node("""
      const row = (p, st) => ({ player: p, market: "hits", category: "main", status: st });
      const a = settleChanges(null, [row("A", "tracking"), row("B", "won_pending")]);
      const b = settleChanges(a.next, [row("A", "cleared"), row("B", "won_pending"), row("C", "busted")]);
      const c = settleChanges(b.next, [row("A", "cleared"), row("B", "won_pending"), row("C", "busted")]);
      const d = settleChanges(c.next, [row("A", "cleared"), row("B", "lost_pending"), row("C", "dead")]);
      return { first: a.fire, second: b.fire, same: c.fire, later: d.fire, keys: [...b.next.keys()] };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["first"] == [], "nothing to announce on the first draw"
    assert got["second"] == ["win"], "A cleared; B was already won; C arrived settled"
    assert got["same"] == []
    assert got["later"] == ["loss", "loss"]
    assert got["keys"] == ["A|hits|main", "B|hits|main", "C|hits|main"]


def test_no_buzz_without_a_motor_or_under_reduced_motion():
    got = _node("""
      const out = {};
      out.noMotor = buzz("tap");
      navigator.vibrate = (p) => { out.last = p; return true; };
      out.tap = buzz("tap"); out.tapPattern = out.last;
      out.win = buzz("win"); out.winPattern = out.last;
      out.unknown = buzz("nope");
      window.matchMedia = () => ({ matches: true });
      out.still = buzz("win");
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["noMotor"] is False and got["unknown"] is False
    assert got["tap"] is True and got["tapPattern"] == [12]
    assert got["win"] is True and got["winPattern"] == [30, 40, 30]
    assert got["still"] is False, "reduced motion means no buzz"


def test_the_wiring_is_passive_owned_and_scoped_to_boards():
    i = APP.index('document.addEventListener("touchstart"')
    seg = APP[i:APP.index("(function initNewLook()", i)]
    assert seg.count("{ passive: true }") == 4, "every touch listener is passive — a scroll must never wait on it"
    assert "owned: swipeOwned(e.target)" in seg and "atTop: window.scrollY <= 0" in seg
    assert "if (s.owned || !t || !onBoard) return;" in seg, "a swipe from a strip, a chip row or a dialog is theirs"
    assert 'if (s.phase === "ready" && onBoard && !state.static) {' in seg
    assert "await load(true);" in seg and "tfToast(`Refreshed · ${tzTime(Date.now())}`);" in seg
    assert 'Math.abs(dx) > SWIPE_MAX_Y ? "idle" : ptrPhase(dy, true)' in seg, "a sideways drag is not a pull"
    owned = _fn("swipeOwned")
    for sel in (".games-scroller", ".std-chips", ".sb-chips", "#pk-overlay", "#tour-overlay", "input, textarea"):
        assert sel in owned, sel
    assert 'o === "auto" || o === "scroll"' in owned, "anything that scrolls sideways owns its swipes"
    views = _const("SWIPE_VIEWS")
    for v in ("prop", "game", "pbp", "messages", "mybets"):
        assert f'"{v}"' not in views, v
    assert '"recommended"' in views and '"live"' in views
    assert "@media (pointer: coarse) { html { overscroll-behavior-y: contain; } }" in CSS
    assert "#ptr.ready, #ptr.busy" in CSS


def test_the_slip_and_the_tracker_buzz_where_they_should():
    st = _fn("slipToggle")
    assert st.count('buzz("tap");') == 1
    assert st.index("s.legs.splice(i, 1);") < st.index('buzz("tap");'), "a removal is silent; the add buzzes"
    i = APP.index("function renderLivePicks() {")
    assert APP[i:i + 120].count("buzzOnSettle(((state.data || {}).live_picks) || []);") == 1
    bs = _fn("buzzOnSettle")
    assert 'buzz(fire.includes("win") ? "win" : "loss")' in bs


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
