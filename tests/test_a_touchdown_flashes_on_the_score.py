"""A touchdown flashes on the live football score, at the top and in the bar.

Ethan, 2026-11-16, asked whether he wanted a touchdown flash on the score at
the top of the live page: "Yes". detail.js gpTouchdownSeen runs once a draw
on the football page (gpFootballHTML), after the TV delay's hold and the
spoiler veil, so it reads the score the reader is shown. When one side's
score rises by six or more between two draws, and a touchdown not seen
before is among the plays (or no plays are on file), that side's score
pulses gold with TOUCHDOWN over it for GP_TD_MS, at the top (pbpBoardHTML,
announced to a screen reader) and in the bar that stays when you scroll
(gpCompactHTML). Never on opening a game or coming back to it, never for a
draw while the tab was hidden, never a field goal, never two field goals
from a feed catching up. A redraw mid-flash carries the animation on from
where it was (--td-t) instead of starting it again. With reduced motion it
is a tint and a fade, no movement.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


SB = _Harness("test_every_sport_gets_the_basketball_scoreboard")
GPT = _Harness("test_the_game_page_wears_the_team_colours")

#: One game's draws, in Node: `seen(...)` is one draw of the page.
GAME = r"""
  // The page's own attribute escaper (app.js), which this harness stubs no copy of.
  if (typeof escapeAttr === "undefined") globalThis.escapeAttr = (v) => escapeHtml(v);
  const doc = (a, h, plays, state) => ({ league: "nfl", event_id: "401", home: "CIN", away: "PIT",
    live: { state: state || "live", away_score: a, home_score: h, period: "Q2", clock: "4:10" },
    plays: plays || [], records: { CIN: "5-5", PIT: "6-4" }, generated_at: "x", tv: [] });
  const fg = { id: "1", event: "Field Goal Good", scoring: true };
  const td = (id) => ({ id, event: "Passing Touchdown", scoring: true });
  const seen = (d, t) => { const f = gpTouchdownSeen("nfl", d, d.live, t); return f ? { side: f.side, start: f.start } : null; };
"""


def _run(body):
    return SB._node(GAME + body)


def test_a_touchdown_seen_happen_flashes_the_scoring_side():
    got = _run("""
      const out = [];
      out.push(seen(doc(0, 3, [fg]), 1000));                       // the page opens: never a flash
      out.push(seen(doc(7, 3, [fg, td("2")]), 6000));               // PIT score a touchdown, seen happen
      out.push(gpTdFor({ event_id: "401" }, "nfl", "away", 7000), gpTdFor({ event_id: "401" }, "nfl", "home", 7000));
      out.push(gpTdFor({ event_id: "401" }, "nfl", "away", 6000 + GP_TD_MS + 1));
      return out;
    """)
    first, flash, away_ms, home_ms, after = got
    assert first is None, "opening a game never flashes"
    assert flash == {"side": "away", "start": 6000}, flash
    assert away_ms == 1000 and home_ms is None, (away_ms, home_ms)
    assert after is None, "gone after GP_TD_MS"


def test_a_field_goal_a_return_a_hidden_tab_and_a_new_game_do_not_flash():
    got = _run("""
      const out = [];
      seen(doc(0, 0), 0);
      out.push(seen(doc(0, 3, [fg]), 5000));                        // a field goal
      out.push(seen(doc(7, 3, [fg, td("2")]), 5000 + GP_TD_FRESH_MS + 1));   // back after two minutes away
      globalThis.document = { hidden: true };
      out.push(seen(doc(14, 3, [fg, td("2"), td("3")]), 5000 + GP_TD_FRESH_MS + 5000));   // a hidden tab
      globalThis.document = { hidden: false };
      out.push(gpTouchdownSeen("nfl", { ...doc(21, 3), event_id: "402" }, doc(21, 3).live, 5000 + GP_TD_FRESH_MS + 9000));
      out.push(seen(doc(0, 9), 1));                                 // the first game again: a new visit to it
      return out;
    """)
    assert got == [None, None, None, None, None], got


def test_two_field_goals_from_a_feed_catching_up_do_not_flash_but_a_bare_feed_does():
    got = _run("""
      seen(doc(0, 0, [fg]), 0);
      const two_fgs = seen(doc(6, 0, [fg, { id: "4", event: "Field Goal Good", scoring: true }]), 20000);
      GP_TD.key = "";
      seen(doc(0, 0), 0);
      const bare = seen(doc(0, 7), 20000);                          // no plays on file: six points in one draw
      return [two_fgs, bare];
    """)
    assert got[0] is None, "six points with no new touchdown on file is not one"
    assert got[1] and got[1]["side"] == "home", got


def test_a_touchdown_on_file_before_the_score_waits_for_the_score():
    got = _run("""
      seen(doc(0, 3, [fg]), 0);
      const early = seen(doc(0, 3, [fg, td("2")]), 5000);           // the play is in, the scoreboard not yet
      const then = seen(doc(7, 3, [fg, td("2")]), 10000);            // the score lands
      const again = seen(doc(7, 3, [fg, td("2")]), 15000);           // a redraw: the same flash, not a new one
      return [early, then, again];
    """)
    early, then, again = got
    assert early is None and then == {"side": "away", "start": 10000} and again == then, got


def test_the_score_at_the_top_and_the_bar_wear_it_and_a_redraw_carries_on():
    top = _run("""
      seen(doc(0, 3, [fg]), Date.now() - 6000);
      const d = doc(7, 3, [fg, td("2")]);
      GP_TD.flash = { key: "nfl:401", side: "away", start: Date.now() - 1200 };
      return pbpBoardHTML(d, "nfl", d.live);
    """)
    away = top[top.index('pbp-sb-side away'):top.index('<div class="pbp-sb-mid">')]
    home = top[top.index('pbp-sb-side home'):]
    assert "gp-td" in away and "gp-td" not in home, "the scoring side alone"
    t = int(re.search(r'--td-t:-(\d+)ms', away).group(1))
    assert 1200 <= t < 2500, ("a redraw starts the animation where it was", t)
    assert '<span class="gp-td-word" role="status" aria-label="Touchdown, ' in away, "said to a screen reader at the top"
    team = away[away.index('<div class="pbp-sb-team">'):away.index('<b class="pbp-sb-pts">')]
    assert "gp-td-word" in team, "over the club's name block, clear of the clock"
    bar = GPT._node("""
      GP_TD.key = "nfl:401"; GP_TD.flash = { key: "nfl:401", side: "home", start: Date.now() - 300 };
      const d = { away: "MIN", home: "DET", event_id: "401" };
      const lv = { state: "live", period: "Q4", clock: "1:17", home_score: 21, away_score: 17 };
      return gpCompactHTML(d, "nfl", lv, [["plays", "Plays"]], "plays");
    """)
    if bar is None:
        return
    assert re.search(r'<span class="gp-c-side home gp-td" style="--td-t:-\d+ms">', bar), bar[:400]
    assert '<span class="gp-c-side away">' in bar
    assert '<span class="gp-td-word" aria-hidden="true">Touchdown</span>' in bar, "the bar shows it, the top says it"


def test_it_runs_once_a_draw_after_the_tv_hold_and_the_veil():
    page = DETAIL[DETAIL.index("async function renderPbpPage("):]
    assert page.index("tvPick(") < page.index("spoiledG(league") < page.index("gpFootballHTML("), \
        "the copy on the screen, and never a veiled game"
    fb = DETAIL[DETAIL.index("function gpFootballHTML(o) {"):]
    assert fb.index("gpTouchdownSeen(league, d, lv);") < fb.index("const field = gpFieldHTML(d, league, lv);")
    assert DETAIL.count("gpTouchdownSeen(") == 2, "defined once, seen once a draw"


def test_the_styles_pulse_and_fall_back_to_a_tint_without_motion():
    css = CSS[CSS.index("/* A touchdown, flashed"):]
    assert ".gp .gp-td .pbp-sb-pts, .gp-c-side.gp-td > b { animation: gp-td-pulse 1.5s ease-out 3 both;" in css
    assert css.count("animation-delay: var(--td-t, 0ms);") >= 3
    rm = css[css.index("@media (prefers-reduced-motion: reduce) {"):]
    assert "animation: gp-td-tint 4.5s linear both;" in rm and ".gp-td-word { animation-name: gp-td-fade; }" in rm
    assert "box-shadow" not in css[:css.index("@media (prefers-reduced-motion: reduce) {") + 400]


def test_in_a_browser_the_word_sits_over_the_name_clear_of_the_clock_at_390():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    from playwright.sync_api import sync_playwright
    html = _run("""
      const d = doc(7, 3, [fg, td("2")]);
      GP_TD.flash = { key: "nfl:401", side: "away", start: Date.now() };
      return pbpBoardHTML(d, "nfl", d.live);
    """)
    page_html = (f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                 f'<style>{(ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")}\n{CSS}</style></head>'
                 f'<body><section class="view gp-on" id="view-pbp" style="display:block">'
                 f'<div class="gp">{html}</div></section></body></html>')
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 390, "height": 500})
        p.set_content(page_html)
        p.wait_for_timeout(700)
        box = p.evaluate("""(() => {
          const r = (q) => { const b = document.querySelector(q).getBoundingClientRect(); return [b.left, b.right, b.top, b.bottom]; };
          return { w: r('.pbp-sb-side.away .gp-td-word'), team: r('.pbp-sb-side.away .pbp-sb-team'),
                   mid: r('.pbp-sb-mid'), vw: innerWidth,
                   op: getComputedStyle(document.querySelector('.gp-td-word')).opacity };
        })()""")
        b.close()
    w, team, mid = box["w"], box["team"], box["mid"]
    assert w[1] <= mid[0] + 1, ("in its own half: never over the clock", box)
    assert w[0] >= 0 and w[1] <= box["vw"], ("on the screen at 390", box)
    assert team[2] - 2 <= (w[2] + w[3]) / 2 <= team[3] + 2, ("over the club's name block", box)
    assert float(box["op"]) > 0.5, ("it shows", box)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
