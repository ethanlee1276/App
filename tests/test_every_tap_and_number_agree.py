"""Every Most Likely pick, on every page that shows it, says the same thing —
and a tap on it opens that pick.

Ethan, 2026-09-25, after a day whose two worst reports were the same kind:
a card reading 75% beside a note saying under 55% (Jameson Williams), and a
tap on Geno Smith's under 1.5 passing touchdowns opening another of his
picks. "I wanna make sure everything is dialed in with what we have been
working on."

THE CRAWL. A board built to be awkward — one quarterback with three picks
(two on the same stat, one of them locked with its chance fallen under the
bar), an alternate-line rung that borrows the main line's charts, an
anytime scorer with no line, a locked pick carrying today's price, and a
matchup read that names its pick — is served to the real page in a real
browser. On the Most Likely page, the home page, Tonight and the game page,
every door to a pick is read and tapped:

  * the row or card shows the pick's own price, chance and number;
  * the page the tap opens is that pick — its side, number, stat, price,
    chance — on the Most Likely board, never another of the player's.

RUNS WHEREVER A BROWSER DOES: Node's Playwright (the global install) and a
Chromium. Where either is missing — the droplet — it says so and skips, as
the other browser tests do; the source checks below always run.
"""
import datetime
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


# --- the board ----------------------------------------------------------------
def _today() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                           # noqa: BLE001
        return datetime.date.today().isoformat()


def _row(player, pos, market, label, side, line, odds, prob, **kw):
    r = {"kind": "prop", "player": player, "team": "SEA", "opponent": "ARI", "position": pos,
         "market": market, "market_label": label, "side": side, "line": line, "odds": odds,
         "book": kw.pop("book", "FanDuel"), "model_prob": prob, "first_prob": prob,
         "rung": "main", "main_line": line, "main_side": side, "bettable": True,
         "game_date": _today(), "kickoff": "20:15", "since": f"{_today()}T12:00:00Z",
         "projection": kw.pop("projection", 1.0), "recent_values": kw.pop("recent", [1, 2, 1, 0, 1]),
         "reasons": [], "warnings": []}
    r.update(kw)
    return r


def _edge(player, pos, market, label, side, line, odds, recent, projection):
    return {"player": player, "team": "SEA", "opponent": "ARI", "position": pos, "market": market,
            "market_label": label, "side": side, "line": line, "odds": odds, "book": "DraftKings",
            "has_market": True, "recent_values": recent, "projection": projection,
            "hit_prob": 0.55, "fair_prob": 0.5, "edge": 0.01, "ev_per_unit": 0.01,
            "game_date": _today(), "game_kickoff": "20:15", "reasons": [], "warnings": [],
            "recommended": False, "grade": "Pass", "confidence": 6.0, "quality": 60,
            "all_lines": [{"book": "DraftKings", "line": line, "over_odds": -110, "under_odds": -110}]}


YDS = [245, 231, 210, 262, 199]
ML = [
    # One quarterback, three picks — two on passing touchdowns.
    _row("Geno Smith", "QB", "pass_yds", "Pass Yards", "OVER", 199.5, -190, 0.71,
         book="DraftKings", rung="alt", main_line=229.5, main_side="OVER", projection=241.0,
         recent=YDS),
    _row("Geno Smith", "QB", "pass_td", "Pass TDs", "UNDER", 1.5, -180, 0.66, projection=1.2),
    _row("Geno Smith", "QB", "pass_td", "Pass TDs", "OVER", 0.5, -600, 0.47, first_prob=0.62,
         locked=True, lock_why="floor", now_listed=True, now_odds=-650, now_book="DraftKings",
         lock_note="Our chance at this number is now 47%, down from 62% when it went up."),
    # A rung that borrows the main line's charts.
    _row("Jaxon Smith-Njigba", "WR", "rec_yds", "Receiving Yards", "OVER", 49.5, -210, 0.64,
         rung="alt", main_line=65.5, main_side="OVER", projection=71.0, recent=[80, 55, 90, 62, 71]),
    # An anytime scorer — no line at all.
    dict(_row("Kenneth Walker", "RB", "anytime_td", "Anytime TD", "yes", None, -150, 0.58,
              recent=[1, 0, 2, 1, 1]), kind="td"),
    # A locked pick with today's price beside the posted one.
    _row("DK Metcalf", "WR", "rec_yds", "Receiving Yards", "OVER", 55.5, -170, 0.62, first_prob=0.64,
         locked=True, lock_why="number moved", now_listed=True, now_odds=-160, now_book="BetMGM",
         lock_note="The books have moved the line since this went up. This is the number we posted.",
         projection=68.0, recent=[70, 61, 88, 45, 77]),
]
EDGE = [
    _edge("Geno Smith", "QB", "pass_yds", "Pass Yards", "OVER", 229.5, -110, YDS, 241.0),
    _edge("Geno Smith", "QB", "pass_td", "Pass TDs", "OVER", 1.5, 140, [1, 2, 1, 0, 1], 1.2),
    _edge("Jaxon Smith-Njigba", "WR", "rec_yds", "Receiving Yards", "OVER", 65.5, -115,
          [80, 55, 90, 62, 71], 71.0),
]
WATCH = [dict(_edge("Kenneth Walker", "RB", "anytime_td", "Anytime TD", "OVER", 0.5, 120,
                    [1, 0, 2, 1, 1], 0.7))]


def board() -> dict:
    game = {"home": "SEA", "away": "ARI", "date": _today(), "kickoff": "20:15", "spread": -3.5,
            "favorite": "SEA", "total": 44.5, "roof": "outdoors", "surface": "grass",
            "home_ml": -170, "away_ml": 145, "live": None,
            "weather": {"dome": False, "temp_f": 60, "wind_mph": 5, "measured": True, "forecast": True}}
    return {"date": _today(), "generated_from": "live-oddsapi", "games": [game],
            "recommendations": EDGE, "longshot_watch": WATCH, "long_shots": [], "game_bets": [],
            "most_likely": ML,
            "board_shelves": [
                {"key": "passing", "title": "Passing", "markets": ["pass_yds", "pass_td"], "row_ix": [0, 1, 2]},
                {"key": "receiving", "title": "Catches & receiving yards",
                 "markets": ["rec_yds"], "row_ix": [3, 5]},
                {"key": "touchdowns", "title": "Touchdown scorers", "markets": ["anytime_td"], "row_ix": [4]}],
            "likely_census": {}, "scan_reads": {"ARI@SEA": {"players": [
                {"player": "Geno Smith", "team": "SEA", "position": "QB", "read": "tough",
                 "label": "Tough matchup", "lean": ["pass_yds", "pass_td"], "pro": [],
                 "con": ["ARI gives up the fewest passing touchdowns"], "notes": [],
                 "pick": {k: ML[1][k] for k in ("player", "team", "market", "market_label", "side",
                                                 "line", "odds", "book", "model_prob")}}],
                "microscope": []}}}


def pid(r) -> str:
    return "|".join([r["player"], r["market"], r["side"], "" if r["line"] is None else str(r["line"])])


# --- the crawl ----------------------------------------------------------------
CRAWL = r"""
const { chromium } = require("playwright");
const fs = require("fs");
const [base, boardPath, exe] = process.argv.slice(2);
const body = fs.readFileSync(boardPath, "utf8");
const DOORS = '.view.active [data-open^="likely:"], .view.active [data-prop][data-likely="1"]';
// Every text node, spaced: a row's price and chance sit in sibling pills
// with no space between them, and textContent would run them together.
const TXT = `(el) => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const a = [];
  while (w.nextNode()) a.push(w.currentNode.nodeValue); return a.join(" ").replace(/\\s+/g, " "); }`;
const SURFACES = {
  likely: () => switchView("likely", true),
  home: () => switchView("recommended", true),
  tonight: () => switchView("tonight", true),
  game: () => openGame(gameSlug(state.data.games[0])),
};
(async () => {
  const b = await chromium.launch({ executablePath: exe || undefined, args: ["--no-sandbox"] });
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce",
                                   serviceWorkers: "block" });
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", (e) => errs.push(String((e && e.stack) || e).slice(0, 600)));
  await p.route("**/data/recommendations*.json*", (r) => r.fulfill({ status: 200,
    contentType: "application/json", headers: { "Last-Modified": new Date().toUTCString() }, body }));
  await p.addInitScript(() => { try { localStorage.setItem("qb.tour", "done"); } catch (e) {} });
  await p.goto(base + "/index.html#nfl", { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => typeof state !== "undefined" && state.data && state.sport === "nfl"
    && (state.data.most_likely || []).length, null, { timeout: 45000 });
  await p.evaluate(() => { state.quiet = true; });
  const out = {};
  for (const [name, go] of Object.entries(SURFACES)) {
    await p.evaluate(go);
    await p.waitForTimeout(250);
    const doors = await p.evaluate(([sel, txt]) => {
      const T = eval(txt);
      return [...document.querySelectorAll(sel)].map((el) => {
        // THE DOOR ITSELF: a row button, a card, a chip — each carries the
        // pick it opens, and its surroundings may carry other picks.
        return { id: el.dataset.open ? el.dataset.open.slice(7) : el.dataset.prop, text: T(el),
                 cls: String(el.className || "") };
      });
    }, [DOORS, TXT]);
    for (let i = 0; i < doors.length; i++) {
      await p.evaluate(go);
      await p.waitForTimeout(150);
      doors[i].opened = await p.evaluate(async ([sel, i, txt]) => {
        const T = eval(txt);
        const el = [...document.querySelectorAll(sel)][i];
        if (!el) return null;
        el.click();
        await new Promise((r) => setTimeout(r, 250));
        const q = (s) => { const e = document.querySelector(s); return e ? T(e) : ""; };
        return { view: state.view, pick: q("#prop-body .pp-card .pick"), player: q("#prop-body .pp-card .player"),
                 board: q("#prop-body .pp-board"), body: q("#prop-body").slice(0, 4000) };
      }, [DOORS, i, TXT]);
    }
    out[name] = doors;
  }
  console.log(JSON.stringify({ out, errs }));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _node_playwright():
    node = shutil.which("node")
    if not node:
        return None, None
    root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() \
        if shutil.which("npm") else ""
    env = dict(os.environ, NODE_PATH=os.pathsep.join(filter(None, [root, os.environ.get("NODE_PATH", "")])))
    ok = subprocess.run([node, "-e", "require('playwright')"], env=env, capture_output=True).returncode == 0
    return (node, env) if ok else (None, None)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass


def _serve():
    handler = functools.partial(_Quiet, directory=os.path.join(ROOT, "web"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def crawl():
    node, env = _node_playwright()
    if not node or not os.path.exists(CHROMIUM):
        return None
    d = tempfile.mkdtemp()
    bpath, spath = os.path.join(d, "board.json"), os.path.join(d, "crawl.js")
    with open(bpath, "w", encoding="utf-8") as fh:
        json.dump(board(), fh)
    with open(spath, "w", encoding="utf-8") as fh:
        fh.write(CRAWL)
    srv = _serve()
    try:
        res = subprocess.run([node, spath, f"http://127.0.0.1:{srv.server_address[1]}", bpath, CHROMIUM],
                             env=env, capture_output=True, text=True, timeout=240)
    finally:
        srv.shutdown()
    assert res.returncode == 0, res.stderr[-1500:]
    return json.loads(res.stdout.strip().splitlines()[-1])


def _minus(s: str) -> str:
    return (s or "").replace("−", "-")


def _odds(o) -> str:
    return f"+{o}" if o > 0 else str(o)


def _pct(p) -> re.Pattern:
    return re.compile(rf"(?<![\d.]){round(p * 100)}(\.\d)?%")


_RESULT: dict = {}


def _result():
    if "r" not in _RESULT:
        _RESULT["r"] = crawl()
    return _RESULT["r"]


# --- the checks ----------------------------------------------------------------
def test_every_surface_draws_every_pick_it_should():
    got = _result()
    if got is None:
        print("      (skipped: no Node Playwright or Chromium here)")
        return
    assert not got["errs"], got["errs"][:3]
    ids = {pid(r) for r in ML}
    seen = {name: {d["id"] for d in doors} for name, doors in got["out"].items()}
    assert seen["likely"] == ids, ("the Most Likely page", ids - seen["likely"], seen["likely"] - ids)
    assert pid(ML[1]) in seen["home"] and pid(ML[2]) in seen["home"], seen["home"]
    assert ids <= seen["game"], ("the game page", ids - seen["game"])
    assert pid(ML[2]) not in seen["tonight"], "a pick under the bar is not one of tonight's top picks"


def test_every_door_shows_its_own_pick():
    got = _result()
    if got is None:
        return
    rows = {pid(r): r for r in ML}
    for name, doors in got["out"].items():
        for d in doors:
            r = rows.get(d["id"])
            assert r is not None, (name, d["id"], "a door that names no pick on the board")
            text = _minus(d["text"])
            # The parlay-builder chips name a pick and its chance, not its price.
            if "gs-chip" not in d.get("cls", ""):
                assert _odds(r["odds"]) in text, (name, d["id"], "price", text[:200])
            assert _pct(r["model_prob"]).search(text), (name, d["id"], "chance", text[:200])
            if r["line"] is not None:
                assert str(r["line"]) in text, (name, d["id"], "number", text[:200])


def test_every_tap_opens_that_pick():
    got = _result()
    if got is None:
        return
    rows = {pid(r): r for r in ML}
    for name, doors in got["out"].items():
        for d in doors:
            r, o = rows[d["id"]], d["opened"] or {}
            where = (name, d["id"])
            assert o.get("view") == "prop", (where, "did not open the pick page", o)
            pick = o["pick"].lower()
            if r["line"] is None:
                assert "anytime td · yes" in pick, (where, o["pick"])
            else:
                assert f"{r['side'].lower()} {r['line']} {r['market_label'].lower()}" in pick, (where, o["pick"])
            assert _odds(r["odds"]) in _minus(o["player"]), (where, "price", o["player"])
            assert o["board"].startswith("Most Likely"), (where, o["board"])
            assert _pct(r["model_prob"]).search(o["body"]), (where, "chance")


# --- the source, always --------------------------------------------------------
def test_the_fixture_is_the_awkward_one():
    """Two picks on one stat for one player, one of them locked under the
    bar; a borrowed-chart rung; a line-less scorer; a locked pick with
    today's price — the cases the two reports of 2026-09-25 were made of."""
    geno_td = [r for r in ML if r["player"] == "Geno Smith" and r["market"] == "pass_td"]
    assert len(geno_td) == 2 and any(r.get("locked") and r["model_prob"] < 0.55 for r in geno_td)
    assert any(r["rung"] == "alt" for r in ML) and any(r["line"] is None for r in ML)
    assert any(r.get("locked") and r.get("now_listed") and r["model_prob"] >= 0.55 for r in ML)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
