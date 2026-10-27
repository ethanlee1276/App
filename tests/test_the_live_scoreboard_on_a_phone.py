"""The live scoreboard on a phone: the crest, the score and the name each keep
their own room.

Ethan, 2026-10-20, 8:41 PM, a screenshot of the 76ers @ Knicks live page at
the half with the scoreboard circled: "Ok keep going and fix this visual
issue". The 76ers crest sat under the "54", and the Knicks crest ran off
the card's edge.

Two causes, on the NBA and NHL pages alike:

* the watch buttons (Watch Peacock · YouTube TV · Gamecast) sat in the
  clock's column, so that column was as wide as the three buttons, 260px
  of a 340px card on a phone, and each side was left 32px for a 56px crest
  and the score. They are the card's last row now, under the clock and both
  sides. Football's and baseball's header had them in its middle block too,
  stacked beside the live state on a phone, and moves them the same way;
* the phone's 36px crest rule sized the picture inside the mark, but
  `teamMark` writes its size on the mark's wrapper (width:56px, inline),
  which only an important rule outranks. On a phone the crest now takes
  what the score leaves, up to 36px, so the digits never sit on it.

Football's and baseball's header became the same board on 2026-10-27
(Ethan, circling the NBA's: "We want all of these too look like nba for all
sports"), so the browser half measures the football, college and baseball
boards with the same geometry as the basketball and hockey ones.

Offline; the browser half is opt-in (QB_BROWSER_TESTS=1) and aborts every
request that leaves the page's own server.

Run directly: `python3 tests/test_the_live_scoreboard_on_a_phone.py`
"""
import json
from _app import styles_css  # noqa: E402  (styles.css and every room's own sheet)
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import test_the_live_trackers as FB              # noqa: E402
from tests import test_the_nba_live_page as NBA             # noqa: E402
from tests import test_the_nhl_live_page as NHL             # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

APP = app_js()
STYLES = styles_css()
SHEETS = {"hc": (ROOT / "web" / "css" / "hoopscast.css").read_text(encoding="utf-8"),
          "rc": (ROOT / "web" / "css" / "rinkcast.css").read_text(encoding="utf-8"),
          # Football's and baseball's, the same board since 2026-10-27 (pbpBoardHTML).
          "pbp-sb": (ROOT / "web" / "css" / "detail.css").read_text(encoding="utf-8")}

# A stand-in for app.js's watchHTML: the page draws whatever it returns.
WATCH = 'globalThis.watchHTML = (d, lg, cls) => `<div class="watch ${cls}"><a class="watch-main">Watch</a></div>`;'


def _render(mod, league, doc):
    return mod._node(f"""{WATCH}
      const host = {{ innerHTML: "", dataset: {{}}, querySelector: () => null, addEventListener: () => {{}} }};
      Q.render(host, {{ d: {json.dumps(doc)}, league: "{league}", stripHTML: "", back: "",
                       boardGame: null, faces: {{}}, wire: () => {{}} }});
      return host.innerHTML;""")


def _phone_block(css: str) -> str:
    # detail.css has phone rules of its own before the board's.
    at = "@media (max-width: 720px) {\n  .pbp-hero {"
    i = css.index(at) if at in css else css.index("@media (max-width: 720px) {")
    return css[i:css.index("\n}\n", i)]


# --- the markup ----------------------------------------------------------------------
def test_the_watch_row_is_the_scoreboards_last_row_not_the_clocks():
    for p, mod, league in (("hc", NBA, "nba"), ("rc", NHL, "nhl")):
        html = _render(mod, league, mod._deep())
        if html is None:
            return
        board = html[html.index(f'class="card {p}-score"'):html.index(f'class="card {p}-stage')]
        mid = board[board.index(f'class="{p}-mid"'):board.index(f'<div class="{p}-side home">')]
        assert "watch" not in mid, f"{league}: the buttons set the clock column's width"
        assert board.index(f'<div class="{p}-side home">') < board.index(f'class="watch pbp-watch {p}-watch"'), league
        # Only while the game is on.
        assert "pbp-watch" not in _render(mod, league, mod._deep(state="final")), league


def test_the_football_and_baseball_header_puts_it_last_too():
    board = APP[APP.index("function pbpBoardHTML("):APP.index("async function renderPbpPage(")]
    mid = board[board.index('<div class="pbp-sb-mid">'):board.index('${side("home")}')]
    assert "watchHTML" not in mid
    clock = APP[APP.index("function pbpBoardMidHTML("):APP.index("function pbpBoardHTML(")]
    assert "watchHTML" not in clock
    assert board.index('${side("home")}') < board.index('lv.state === "live" ? watchHTML(d, league, "pbp-watch") : ""')


# --- the stylesheets -------------------------------------------------------------------
def test_the_row_spans_the_card():
    assert ".hc-watch { grid-column: 1 / -1; margin-top: 0; }" in SHEETS["hc"]
    assert ".rc-watch { grid-column: 1 / -1; margin-top: 0; }" in SHEETS["rc"]
    assert ".pbp-hero > .pbp-watch { grid-column: 1 / -1; margin-top: 0; }" in STYLES


def test_the_crest_gives_way_to_the_score_on_a_phone():
    # The size the important rule has to outrank (tests/test_logos.py pins it).
    vis = (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")
    assert "width:${size}px;height:${size}px" in vis[vis.index("function teamMark("):]
    for p, css in SHEETS.items():
        phone = _phone_block(css)
        assert f"grid-template-columns: minmax(0, 36px) 1fr;" in phone, p
        assert f"grid-template-columns: 1fr minmax(0, 36px);" in phone, p
        assert (f".{p}-crest > .team-mark-wrap {{ display: block; width: 100% !important; "
                "height: auto !important; aspect-ratio: 1 / 1; }") in phone, p
        # The rule that never reached the wrapper is gone, and so is the
        # floor that grew the score's column to the names' unwrapped line.
        assert f".{p}-crest svg, .{p}-crest img" not in css, p
        assert "minmax(max-content" not in css, p
        # The clock's column is capped: a long word wraps there, not into the sides.
        assert re.search(rf"\.{p}-mid \{{ min-width: \d+px; max-width: \d+px;", phone), p


# --- the scoreboard in a browser (opt-in) ---------------------------------------------
GEOM = """(sel) => {
  const box = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return {l: r.left, r: r.right, t: r.top, b: r.bottom}; };
  const sb = document.querySelector(sel.score);
  const out = {mid: box(sb.querySelector(sel.mid)), watch: box(sb.querySelector('.pbp-watch')), sides: {},
               page: document.scrollingElement.scrollWidth};
  for (const ha of ['away', 'home']) {
    const s = sb.querySelector(sel.side + '.' + ha), pts = s.querySelector(sel.pts), nick = s.querySelector(sel.nick);
    const rng = document.createRange(); rng.selectNodeContents(pts);
    const ink = rng.getBoundingClientRect();
    out.sides[ha] = {side: box(s), crest: box(s.querySelector(sel.crest + ' > .team-mark-wrap')), nick: box(nick),
                     ink: {l: ink.left, r: ink.right, t: ink.top, b: ink.bottom}, whole: nick.scrollWidth <= nick.clientWidth + 1};
  }
  return out;
}"""


def _meet(a, b):
    return a["l"] < b["r"] - 0.5 and b["l"] < a["r"] - 0.5 and a["t"] < b["b"] - 0.5 and b["t"] < a["b"] - 0.5


def _college(fb):
    """The football doc as a college game: Mississippi State at Alabama, the
    longest school on the board beside a short one."""
    raw = json.dumps(fb).replace('"DAL"', '"ALA"').replace('"TB"', '"MSST"')
    d = json.loads(raw)
    d.update({"league": "cfb", "event_id": "e10", "home_name": "Alabama Crimson Tide",
              "away_name": "Mississippi State Bulldogs", "records": {"ALA": "6-1", "MSST": "3-4"}})
    return d


#: The college board's identities ride in its board file (pbpCfbTeamsWarm).
CFB_TEAMS = {"ALA": {"id": "333", "name": "Alabama Crimson Tide", "nick": "Alabama", "primary": "#9e1b32", "alt": "#ffffff"},
             "MSST": {"id": "344", "name": "Mississippi State Bulldogs", "nick": "Mississippi St",
                      "primary": "#5d1725", "alt": "#c1c6c8"}}


def _mlb():
    return {"league": "mlb", "event_id": "e11", "home": "NYY", "away": "BOS", "home_name": "New York Yankees",
            "away_name": "Boston Red Sox", "tv": ["FOX"], "records": {"BOS": "88-74", "NYY": "94-68"},
            "live": {"state": "live", "home_score": 4, "away_score": 13, "period": "Top 7", "outs": 2,
                     "balls": 1, "strikes": 2, "bases": [1, 3]},
            "current": {"half": "T", "inning": 7, "batter": "Rafael Devers", "pitcher": "Gerrit Cole", "pitches": 4},
            "events": [{"kind": "atbat", "at_bat": i, "inning": 7, "half": "T", "batter": "Rafael Devers",
                        "pitcher": "Gerrit Cole", "event": "single", "away_score": 13, "home_score": 4}
                       for i in range(40, 46)]}


def _nba(variant):
    d = NBA._deep()
    d["tv"] = ["Peacock"]
    swap = {"opening": {"LAL": "PHI", "BOS": "NYK"}, "late": {"LAL": "MIN", "BOS": "POR"}}[variant]
    d["away"], d["home"] = swap["LAL"], swap["BOS"]
    for p in d["plays"]:
        p["team"] = swap.get(p["team"], p["team"])
    for b in d["box"]:
        b["team"] = swap[b["team"]]
    d["linescores"] = {swap[k]: v for k, v in d["linescores"].items()}
    if variant == "opening":                     # Ethan's screenshot: the half, both clubs 0-0
        d["records"] = {"PHI": "0-0", "NYK": "0-0"}
        d["live"].update({"home_score": 58, "away_score": 54, "hold": "Halftime"})
        d.pop("situation", None)
    else:                                        # three figures, the ball, the longest names, every mark
        d["records"] = {"MIN": "48-34", "POR": "21-61"}
        d["live"].update({"home_score": 118, "away_score": 121, "period": "Q4", "clock": "0:42"})
    return d


def test_the_scoreboards_in_a_browser_from_320_to_1280():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    nhl = NHL._deep()
    nhl["tv"] = ["ESPN"]
    fb = FB._fb_doc()
    fb["event_id"], fb["tv"] = "e9", ["NBC"]
    # Football's longest nickname, two figures, the ball (TB's drive).
    fb["live"].update({"away_score": 24, "home_score": 17})
    cases = [("nba", "opening", _nba("opening")), ("nba", "late", _nba("late")), ("nhl", "nhl", nhl),
             ("nfl", "football", fb), ("cfb", "college", _college(fb)), ("mlb", "baseball", _mlb())]
    board = {"score": ".pbp-hero", "mid": ".pbp-sb-mid", "side": ".pbp-sb-side", "pts": ".pbp-sb-pts",
             "crest": ".pbp-sb-crest", "nick": ".pbp-sb-nick"}
    sels = {"nba": {"score": ".hc-score", "mid": ".hc-mid", "side": ".hc-side", "pts": ".hc-pts", "crest": ".hc-crest", "nick": ".hc-nick"},
            "nhl": {"score": ".rc-score", "mid": ".rc-mid", "side": ".rc-side", "pts": ".rc-pts", "crest": ".rc-crest", "nick": ".rc-nick"},
            "nfl": board, "cfb": board, "mlb": board}
    # The names each board must show whole, from 360px up: the opening's
    # 76ers and Knicks, and football's longest nickname beside a short one.
    whole = {"opening", "football"}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                def open_page(width, league, doc):
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    # Nothing leaves the machine: fonts are the site's own, logos are refused.
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    ev = doc["event_id"]
                    page.route(f"**/data/pbp/{league}_{ev}.json*", serve(doc))
                    page.route(f"**/data/live_{league}.json*", serve({"games": [
                        {"event_id": ev, "home": doc["home"], "away": doc["away"], "live": doc["live"]}]}))
                    page.route("**/data/cfb.json*", serve({"games": [], "teams": CFB_TEAMS}))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/{league}/{ev}", wait_until="load")
                    return ctx, page, errors

                for width in (320, 360, 390, 430, 721, 1280):
                    for league, name, doc in cases:
                        ctx, page, errors = open_page(width, league, doc)
                        sel = sels[league]
                        page.wait_for_selector(sel["score"], timeout=15000)
                        if league == "cfb":
                            # Drawn again once the board file's identities land.
                            for _ in range(100):
                                if page.evaluate("(() => [...document.querySelectorAll('.pbp-sb-nick')]"
                                                 ".map((e) => e.textContent).join('|'))()") == "Mississippi St|Alabama":
                                    break
                                page.wait_for_timeout(100)
                            else:
                                raise AssertionError(f"college at {width}px: the schools never replaced the full names")
                        g = page.evaluate(GEOM, sel)
                        at = f"{name} at {width}px"
                        for ha, s in g["sides"].items():
                            assert not _meet(s["crest"], s["ink"]), f"{at}: the {ha} crest sits on the score"
                            assert not _meet(s["crest"], s["nick"]), f"{at}: the {ha} crest sits on the name"
                            assert s["side"]["l"] - 0.5 <= s["ink"]["l"] and s["ink"]["r"] <= s["side"]["r"] + 0.5, \
                                f"{at}: the {ha} score runs out of its side"
                            for part in ("crest", "ink", "nick"):
                                assert not _meet(s[part], g["mid"]), f"{at}: the {ha} {part} runs into the clock"
                                assert s[part]["b"] <= g["watch"]["t"] + 0.5, f"{at}: the watch row is not under the {ha} {part}"
                            if name in whole and width >= 360:
                                assert s["whole"], f"{at}: the {ha} name is cut"
                        if width == 390:
                            assert all(round(s["crest"]["r"] - s["crest"]["l"]) == 36 for s in g["sides"].values()), at
                        assert g["page"] <= width, f"{at}: the page scrolls sideways"
                        if league in ("nfl", "cfb", "mlb"):
                            w = page.evaluate("(() => { const h = document.querySelector('.pbp-hero');"
                                              " return [h.scrollWidth, h.clientWidth]; })()")
                            assert w[0] <= w[1] + 1, f"{at}: the board is wider than its card"
                        assert not errors, errors
                        ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
