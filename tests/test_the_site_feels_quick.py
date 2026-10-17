"""The site feels quick (Ethan, 2026-10-09).

"the site feel super laggy and not feeling snappy or quick" — then,
more exactly: "all the logos and headshots take a while to load and all
our renders will take a while to load", and "Switching pages will also
take a couple seconds and feel laggy, like going sport to sport".

Measured first, in Chromium at phone width with the processor slowed
four times, before anything was changed. The ranked causes, each pinned
here so it cannot quietly come back:

  * THE PAGE'S OWN HOUSEKEEPING. Four observers answered every change
    anywhere on the page; three swept the whole document each time and
    one measured every wide table, forcing the browser to lay the page
    out again mid-render. A dozen tab taps spent 1.4 s of 7 s there.
    Now: one pass per frame over what changed (domSettled / settleNow),
    and the table fades read their widths after layout (ResizeObserver).
  * THE ONE-SECOND TICK rewrote the freshness chip and the stale bar
    every second whether or not a word had changed — a 40 ms stall each
    second a game was on. Now written only when the text changes.
  * FORCED LAYOUTS on every tab switch and strip draw: the retired nav
    underline and the games strip's arrows. Now: skipped while hidden,
    and measured once on the next frame.
  * DATE FORMATTERS built per row (formatGameDate, tzTime, likelyWhen,
    the kickoff offset in likelyStarted). Now remembered.
  * A SPORT SWITCH threw the board away: skeleton, light copy, full
    board and two draws again on every return. Now the league you left
    is kept in memory and drawn at once, then revalidated like a poll.
  * EVERY BOARD PAGE redrew on every load, on screen or not. Now only
    the page on screen draws; the rest draw when opened or when idle.
  * THE RENDERS: every stadium card first asked for a team photo that
    has never existed (on the box, Caddy answers that with the whole
    index.html, cached a week), and phones pulled the 1600px file. Now
    straight to the render, and an 800px copy on a narrow screen.
  * THE FACES: the gamecast drew ESPN's full ~200 KB headshot at 28px,
    forty to a box score. Now through ESPN's own resize, as the boards do.

Run directly: `python3 tests/test_the_site_feels_quick.py`
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
VARIANTS = ROOT / "web" / "img" / "venues" / "variants"


def _fn(name, src=APP, kind="function"):
    """One top-level function's source, brace-matched from its body."""
    i = src.index(f"{kind} {name}(")
    j = src.index(") {", i) + 2
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(f"{name} has unbalanced braces")


def _node(prog):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# --- the housekeeping ---------------------------------------------------------
def test_one_settle_pass_per_frame_replaces_the_document_wide_sweeps():
    watch = _fn("watchSectionSubs")
    assert "new MutationObserver(domSettled)" in watch
    assert "new MutationObserver(() => enhanceSectionSubs())" not in APP, "the whole-page sweep per mutation is back"
    settled = _fn("domSettled")
    assert "requestAnimationFrame(settleNow)" in settled and "if (_settle.queued" in settled, "one pass per frame"
    # Caught by the crawl: renderLongShots rewrites `#longshots-sub` itself,
    # so the sweep has to start above the element that changed.
    assert "_settle.roots.add(t.parentElement || t);" in settled
    now = _fn("settleNow")
    assert "!all.some((o) => o !== el && o.contains(el))" in now, "a subtree inside another is swept once"
    for call in ("enhanceSectionSubs(root);", "armSortable(root);", "watchWideTables(root);"):
        assert call in now, call
    assert "_settle.obs.takeRecords();" in now, "the pass must not chase its own writes"
    # The sortable headers and the table fades lost their own observers.
    assert "armSortable(document), 120" not in APP
    assert "new MutationObserver(all).observe(document.body" not in APP


def test_the_table_fade_reads_widths_after_layout():
    watch = _fn("watchWideTables")
    assert "new ResizeObserver(" in watch and "_wide.ro.observe(el);" in watch
    assert "_wide.seen.has(el)" in watch, "each table is observed once"
    assert "wideTableSync(el); continue;" in watch, "no ResizeObserver: measured once, never broken"
    sync = _fn("wideTableSync")
    assert 'el.classList.toggle("rank-more", el.scrollLeft + el.clientWidth < el.scrollWidth - 4);' in sync


def test_the_rail_fade_measures_once_a_frame():
    i = APP.index('sb.classList.toggle("sb-more"')
    block = APP[i - 700:i + 200]
    assert "if (queued) return;" in block and "requestAnimationFrame(() => {" in block


def test_the_marks_and_sorting_still_reach_every_render():
    """The enhancers did not change, only their scope: a view's title is
    re-read whole because the page's name is decided per view."""
    now = _fn("settleNow")
    assert 'const v = root.closest(".view");' in now and "views.forEach((v) => markPageTitles(v));" in now
    marks = _fn("markPageTitles")
    assert 'if (root && root.matches && root.matches(".view")) views.push(root);' in marks


# --- the one-second tick ------------------------------------------------------
def test_the_freshness_chip_is_written_only_when_it_changes():
    body = _fn("updateAgo")
    assert "if (chip !== el._chipHTML) { el._chipHTML = chip; el.innerHTML = chip; }" in body
    assert "if (title !== el._chipTitle) { el._chipTitle = title; el.title = title; }" in body
    assert "el.innerHTML = (state.livePolling" not in body


def test_the_stale_bar_has_one_writer_that_skips_a_repeat():
    bar = _fn("renderStaleBar")
    assert "host.innerHTML" not in bar, "every write goes through staleWrite"
    assert bar.count("staleWrite(host, ") == 10
    write = _fn("staleWrite")
    assert "if (host._staleHTML === html) return;" in write
    notice = _fn("slateNotice")
    assert "now - slateNotice._today.at > 30000" in notice, "today's date asked twice a minute, not every second"


# --- forced layouts -----------------------------------------------------------
def test_a_hidden_underline_is_not_measured():
    body = _fn("moveIndicator")
    assert 'moveIndicator._drawn = getComputedStyle(ind).display !== "none";' in body
    assert body.index("if (!moveIndicator._drawn) return;") < body.index("active.offsetLeft")


def test_the_strip_arrows_are_measured_once_on_the_frame():
    body = _fn("syncStripArrows")
    assert "if (syncStripArrows._queued) return;" in body
    assert "requestAnimationFrame(() => { syncStripArrows._queued = false; syncStripArrowsNow(); });" in body
    now = _fn("syncStripArrowsNow")
    assert "el.scrollWidth > el.clientWidth + 8" in now, "the measurement itself is unchanged"


def test_the_counter_reads_the_ladder_once_and_a_quiet_redraw_counts_nothing():
    body = _fn("countNumbers")
    assert "if (!els.length) return;" in body
    assert body.index("if (!els.length) return;") < body.index("getComputedStyle"), \
        "no style read when nothing counts"
    assert "if (countNumbers._slow == null) {" in body
    assert 'els.forEach((el) => { el.dataset.counted = "1"; });' in body
    sweep = _fn("sweepRings")
    assert "countNumbers._quiet = true;" in sweep and 'host.classList.contains("hd-still")' in sweep
    deck = _fn("renderHomeDeck", kind="async function")
    assert "const quiet = still || !!state.quiet;" in deck and 'if (quiet) host.classList.add("hd-still");' in deck


# --- the date helpers ---------------------------------------------------------
def test_the_remembered_dates_read_exactly_as_before():
    prog = """
      const tzOpts = (o) => Object.assign({ timeZone: "America/New_York" }, o);
      """ + _fn("formatGameDate") + _fn("tzTime") + _fn("likelyWhen") + _fn("likelyStarted") + """
      const days = ["2026-10-09", "2026-10-12", "2026-01-04", "2026-10-09"];
      const plainDate = (s) => { const m = /^(\\d{4})-(\\d{2})-(\\d{2})/.exec(s);
        return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }); };
      const t = Date.parse("2026-10-09T17:05:00Z");
      const plainTime = (x, o) => new Date(x).toLocaleTimeString(undefined, tzOpts(o || { hour: "numeric", minute: "2-digit" }));
      const out = {
        dates: days.map((d) => formatGameDate(d) === plainDate(d)),
        times: [tzTime(t) === plainTime(t), tzTime(t) === plainTime(t),
                tzTime(t, { hour: "2-digit", minute: "2-digit" }) === plainTime(t, { hour: "2-digit", minute: "2-digit" }),
                tzTime(t, {}) === plainTime(t, {})],
        when: likelyWhen("2026-10-09T17:05:00Z") === likelyWhen("2026-10-09T17:05:00Z"),
        // A bare Eastern kickoff on two dates either side of the clock change.
        started: [likelyStarted({ kickoff: "13:00", game_date: "2020-10-04" }),
                  likelyStarted({ kickoff: "13:00", game_date: "2099-11-08" })],
        offs: [...likelyStarted._off.entries()],
      };
      console.log(JSON.stringify(out));
    """
    got = _node(prog)
    if got is None:
        print("  SKIP node not installed"); return
    assert all(got["dates"]), got
    assert all(got["times"]), got
    assert got["when"]
    assert got["started"] == [True, False]
    assert dict(got["offs"]) == {"2020-10-04": "-04:00", "2099-11-08": "-05:00"}, "EDT then EST, remembered per date"


# --- switching sports ---------------------------------------------------------
def _league_run(script):
    import test_open_bets_vanish as H
    src = (H._STUBS
           + H._fn("normalizeSlate") + "\n" + H._fn("refreshLikelyPrices") + "\n"
           + H._fn("locksAwayWhatWeHold") + "\n" + H._fn("lightNameFor") + "\n"
           + H._board_mem() + "\n" + H._fn("_loadNow", kind="async function") + "\n"
           + """
const PAINTS = [], SENT = [];
let SKELETONS = 0;
showSkeleton = () => { SKELETONS++; };
renderAll = () => PAINTS.push((state.data || {}).date || "");
fetch = async (url, opts) => {
  SENT.push((opts && opts.headers && opts.headers["If-None-Match"]) || "");
  const step = PLAN.shift();
  if (!step) throw new Error("fetch beyond the plan: " + url);
  return { ok: step.ok !== false, status: step.status || 200,
           headers: { get: (h) => (step.headers || {})[h] || null }, json: async () => step.body };
};
""" + script)
    return _node(src)


def test_the_league_you_left_is_drawn_at_once_and_only_revalidated():
    got = _league_run("""
(async () => {
  PLAN = [{ body: { date: "NFL-1", games: [] }, headers: { ETag: "e-nfl" } }];
  await _loadNow(false);
  state.sport = "mlb";
  PLAN = [{ body: { date: "MLB-1", games: [] }, headers: { ETag: "e-mlb" } }];
  await _loadNow(false);
  const before = { paints: PAINTS.length, skeletons: SKELETONS };
  state.sport = "nfl";
  PLAN = [{ status: 304, headers: {} }];
  const p = _loadNow(false);
  const atOnce = PAINTS.slice(before.paints);      // drawn before the wire answered
  await p;
  console.log(JSON.stringify({ before, atOnce, after: PAINTS.slice(before.paints),
    skeletons: SKELETONS, sent: SENT, held: state.data.date, boardFor: _boardFor, size: _boardMem.size }));
})();
""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["before"] == {"paints": 2, "skeletons": 2}, got
    assert got["atOnce"] == ["NFL-1"], f"the league you came back to was not drawn at once: {got}"
    assert got["after"] == ["NFL-1"], "a 304 under a board drawn from memory draws nothing twice"
    assert got["skeletons"] == 2, "no skeleton flashes over a board held in memory"
    assert got["sent"][-1] == "e-nfl", "revalidated with the tag it was built under"
    assert got["held"] == "NFL-1" and got["boardFor"] == "/api/recommendations"


def test_a_changed_board_replaces_the_one_from_memory():
    got = _league_run("""
(async () => {
  PLAN = [{ body: { date: "NFL-1", games: [] }, headers: { ETag: "e1" } }];
  await _loadNow(false);
  state.sport = "mlb";
  PLAN = [{ body: { date: "MLB-1", games: [] } }];
  await _loadNow(false);
  state.sport = "nfl";
  PLAN = [{ body: { date: "NFL-2", games: [] }, headers: { ETag: "e2" } }];
  await _loadNow(false);
  console.log(JSON.stringify({ paints: PAINTS, held: state.data.date }));
})();
""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["paints"][-2:] == ["NFL-1", "NFL-2"], got
    assert got["held"] == "NFL-2"


def test_the_memory_holds_three_leagues_and_one_account():
    got = _node(r"""
      let _acctUser = { signed_in: true, email: "a@example.com" };
      """ + APP[APP.index("const BOARD_MEM_MAX = "):APP.index("async function _loadNow(")] + r"""
      const m = (k) => ({ api: "/api/" + k });
      ["nfl", "mlb", "nba", "cfb"].forEach((k) => boardMemPut(m(k), { date: k }, 1));
      const kept = ["nfl", "mlb", "nba", "cfb"].map((k) => !!boardMemGet(m(k)));
      boardMemPut(m("nhl"), { date: "x", light: true }, 1);           // a light copy is never held
      boardMemPut(m("wnba"), { status: "not built" }, 1);              // nor an empty board
      const light = [!!boardMemGet(m("nhl")), !!boardMemGet(m("wnba"))];
      _acctUser = { signed_in: false };
      const other = !!boardMemGet(m("cfb"));
      console.log(JSON.stringify({ kept, light, other, size: _boardMem.size }));
    """)
    if got is None:
        print("  SKIP node not installed"); return
    assert got["kept"] == [False, True, True, True], "three at most, the oldest dropped first"
    assert got["light"] == [False, False]
    assert got["other"] is False, "signing out never shows the signed-in board"
    assert "IN MEMORY ONLY, never storage" in APP[APP.index("const BOARD_MEM_MAX") - 1600:APP.index("const BOARD_MEM_MAX")]
    assert "localStorage" not in APP[APP.index("const BOARD_MEM_MAX = "):APP.index("async function _loadNow(")]


# --- the pages off screen -----------------------------------------------------
def test_an_off_screen_page_draws_when_opened_or_when_idle():
    block = APP[APP.index("const OFFSCREEN_PAGES = ["):APP.index("function renderAll() {")]
    got = _node(r"""
      const state = {};
      const views = { "view-recommended": true, "view-edge": false, "view-likely": false };
      const hosts = { "edge-board": "view-edge", "likely": "view-likely", "home-thing": "view-recommended" };
      const document = { getElementById: (id) => hosts[id] ? { closest: () => ({ id: hosts[id],
        classList: { contains: (c) => c === "active" && views[hosts[id]] } }) } : null };
      const DRAWN = [];
      const renderTonight = () => {}, renderEdgeBoard = () => DRAWN.push("edge"), renderProps = () => {},
            renderScanner = () => {}, renderLongShots = () => {}, renderLikely = () => DRAWN.push("likely"),
            renderTrending = () => {}, renderPlayers = () => {};
      """ + block + r"""
      drawOrDefer("home-thing", () => DRAWN.push("home"));
      drawOrDefer("edge-board", () => DRAWN.push("edge"));
      drawOrDefer("likely", () => DRAWN.push("likely"), true);
      const first = DRAWN.slice();
      const stale = [..._stalePages.keys()];
      drawStale("edge");
      const opened = DRAWN.slice();
      drawOrDefer("edge-board", () => DRAWN.push("edge-idle"));
      idleStale();
      setTimeout(() => console.log(JSON.stringify({ first, stale, opened, idle: DRAWN.slice(), left: _stalePages.size })), 400);
    """)
    if got is None:
        print("  SKIP node not installed"); return
    assert got["first"] == ["home"], "only the page on screen draws during the load"
    assert got["stale"] == ["edge-board"], "the visit-drawn page is skipped, not queued"
    assert got["opened"] == ["home", "edge"], "opening a stale page draws it"
    assert got["idle"][-1] == "edge-idle" and got["left"] == 0, "an idle moment draws what is left"


# --- the renders --------------------------------------------------------------
def test_every_render_has_a_phone_copy():
    # Pillow is the one non-stdlib package in this repo and it is not
    # installed anywhere but a laptop that has run the venue intake
    # tool. Imported unconditionally it does not fail this assertion —
    # it fails the FILE, taking the other eighteen speed tests with it,
    # which is the exact shape of the outage test_venue_ingest.py's
    # docstring was written about. The skip is indented, so run_tests.py
    # reads it as one test bowing out rather than the file bowing out
    # (its ^SKIP is anchored at line start).
    try:
        from PIL import Image
    except ImportError:
        print("  SKIP Pillow not installed"); return
    jpgs = sorted(VARIANTS.glob("*.jpg")) + [ROOT / "web" / "img" / "venues" / "ufc-hero.jpg"]
    assert len(jpgs) >= 31
    for jpg in jpgs:
        small = jpg.with_name(f"{jpg.stem}@800.webp")
        assert small.exists(), f"{small.name} missing — run tools/venues_ingest.py or its _small()"
        im = Image.open(small)
        assert im.width <= 800 and im.format == "WEBP", small.name
        full = jpg.with_suffix(".webp") if jpg.with_suffix(".webp").exists() else jpg
        assert small.stat().st_size < full.stat().st_size, f"{small.name} is not lighter than the full file"


def test_a_narrow_screen_asks_for_the_phone_copy():
    i = APP.index("const VENUE_SMALL_MQ")
    src = APP[i:APP.index("\n};\n", i) + 4]
    got = _node(f"""
      const VENUE_ART_V = "v";
      let NARROW = true;
      const matchMedia = (q) => ({{ matches: NARROW && q === "(max-width: 900px)" }});
      {src}
      const phone = [venueSrc("img/venues/variants/football-gold.jpg"), venueSrc("img/venues/ufc-hero.jpg")];
      NARROW = false;
      const desk = [venueSrc("img/venues/variants/football-gold.jpg"), venueSrc("img/venues/ufc-hero.jpg")];
      console.log(JSON.stringify({{ phone, desk }}));
    """)
    if got is None:
        print("  SKIP node not installed"); return
    assert got["phone"] == ["img/venues/variants/football-gold@800.webp?v=v", "img/venues/ufc-hero@800.webp?v=v"]
    assert got["desk"] == ["img/venues/variants/football-gold.webp?v=v", "img/venues/ufc-hero.jpg?v=v"]


def test_a_card_asks_for_a_team_photo_only_when_one_ships():
    m = re.search(r"const VENUE_TEAM_PHOTOS = new Set\((\[.*?\])\);", APP, re.S)
    assert m, "the team-photo list is gone"
    listed = set(json.loads(m.group(1)))
    on_disk = {f"{p.parent.name}/{p.stem}" for p in (ROOT / "web" / "img" / "venues").glob("*/*.jpg")
               if p.parent.name not in ("variants", "incoming")}
    assert listed == on_disk, (
        f"VENUE_TEAM_PHOTOS and web/img/venues/<sport>/ disagree: listed {sorted(listed)}, "
        f"on disk {sorted(on_disk)} — name a dropped-in photo in the set, or the card never asks for it")
    tag = _fn("venuePhotoTag")
    assert "VENUE_TEAM_PHOTOS.has(`${sport}/${home}`)" in tag
    assert 'src="${own || render}"' in tag, "no team photo: straight to the render"
    readme = (ROOT / "web" / "img" / "venues" / "README.md").read_text(encoding="utf-8")
    assert "VENUE_TEAM_PHOTOS" in readme, "the drop-in slot's instructions must name the list"


def test_the_ingest_tool_writes_the_phone_copy():
    # Same reason as above, and the guard has to wrap the venues_ingest
    # import too: that module does `from PIL import Image` at the top,
    # so it is the import that raises on a stdlib-only machine, before
    # any PIL line in this function is reached.
    try:
        import venues_ingest as V
        from PIL import Image
    except ImportError:
        print("  SKIP Pillow not installed"); return
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "football-gold.jpg"
        img = Image.new("RGB", (1600, 900), (40, 60, 90))
        img.save(out, quality=87)
        V._webp(img, out)
        small = Path(d) / "football-gold@800.webp"
        assert (Path(d) / "football-gold.webp").exists() and small.exists()
        assert Image.open(small).size == (800, 450)


# --- the faces and the hosts --------------------------------------------------
def test_the_gamecast_faces_ride_espns_resize():
    import test_gamecast as G
    got = G._node("""
      globalThis.facePreview = (u, px) => u.indexOf("a.espncdn.com") >= 0 ? "SMALL-" + px : u;
      const d = { home: "DAL", away: "TB", box: [{ team: "TB", groups: [{ name: "passing",
        labels: ["C/ATT", "YDS"], rows: [{ name: "Baker Mayfield", id: "16757", stats: ["3/4", "37"] }] }] }] };
      QBGamecast.setTeam("TB");
      return { box: QBGamecast.panel("box", { d, league: "nfl", faces: {}, boardGame: null }) };
    """)
    if got is None:
        print("  SKIP node not installed"); return
    box = got["box"]
    assert 'src="SMALL-40"' in box, "the face is not asked for at its drawn size"
    assert 'data-full="https://a.espncdn.com/i/headshots/nfl/players/full/16757.png"' in box
    assert 'data-onerr="swapFull"' in box, "the full file is the first fallback"


def test_the_picture_hosts_are_warmed_in_the_head():
    head = HTML[:HTML.index("</head>")]
    assert '<link rel="preconnect" href="https://a.espncdn.com" />' in head
    for host in ("static.www.nfl.com", "img.mlbstatic.com", "cdn.nba.com", "assets.nhle.com"):
        assert f'<link rel="dns-prefetch" href="https://{host}" />' in head, host
    assert head.index('rel="preconnect"') < head.index('href="css/styles.css"'), "before the stylesheet blocks"



# --- the first visit to a league (2026-10-09, "now make the first visit to a
# sport faster too … everything needs to be faster") -------------------------
def test_a_refused_paid_file_is_not_asked_for_again_and_twins_share_one_request():
    got = _node(r"""
      let _acctUser = null;
      const CALLS = [];
      const boardFetch = async (url, opts) => {
        CALLS.push(url + (opts && opts.cache ? " [" + opts.cache + "]" : ""));
        await new Promise((r) => setTimeout(r, 5));
        const denied = url.startsWith("/api/board/");
        return new Response(denied ? "{}" : JSON.stringify({ url }), { status: denied ? 401 : 200 });
      };
      """ + _fn("boardMemWho") + APP[APP.index("let _paidDenied = null;"):APP.index("async function paidFetch(")] + _fn("paidFetch", kind="async function") + r"""
      (async () => {
        const [a, b] = await Promise.all([paidFetch("kalshi.json"), paidFetch("kalshi.json")]);
        const both = [(await a.json()).url, (await b.json()).url];
        const first = CALLS.slice();
        await paidFetch("feed.json");
        const after = CALLS.slice(first.length);
        _acctUser = { signed_in: true, email: "x@example.com" };
        await paidFetch("feed.json");
        const signedIn = CALLS.slice(first.length + after.length);
        console.log(JSON.stringify({ first, both, after, signedIn }));
      })();
    """)
    if got is None:
        print("  SKIP node not installed"); return
    assert got["first"] == ["/api/board/kalshi.json", "data/kalshi.json [no-cache]"], \
        f"two callers at once must share one trip, revalidated: {got['first']}"
    assert got["both"] == ["data/kalshi.json", "data/kalshi.json"], "each caller reads its own copy"
    assert got["after"] == ["data/feed.json [no-cache]"], "a refusal is remembered: no second detour"
    assert got["signedIn"][0] == "/api/board/feed.json", "signing in asks the entitled endpoint again"


def test_the_injury_board_is_one_request_for_every_caller():
    body = _fn("loadInjuryBoard", kind="async function")
    assert "if (_injBoardAsk) return _injBoardAsk;" in body
    assert 'boardFetch("data/injuries.json", { cache: "no-cache" })' in body
    assert 'boardFetch("data/record.json?t=" + Date.now())' not in APP, "the record revalidates instead"


def test_the_whole_board_is_asked_for_before_the_light_copy_is_read():
    body = _fn("_loadNow", kind="async function")
    ask = body.index("const fullAsk = fetch(")
    lite = body.index("const lr = await paidFetch(lightName);")
    wait = body.index("const res = await fullAsk;")
    assert ask < lite < wait, "the full board waits on the light copy again"
    assert "fullAsk.catch(() => {});" in body


def test_an_idle_light_copy_draws_the_first_visit_at_once():
    got = _league_run("""
(async () => {
  PLAN = [{ body: { date: "NFL-1", games: [] }, headers: { ETag: "e1" } }];
  await _loadNow(false);
  const skel = SKELETONS;
  paidFetch = async (name) => ({ ok: true, status: 200, headers: { get: () => null },
    json: async () => ({ date: "MLB-LIGHT", light: true, games: [] }), clone() { return this; } });
  await prefetchLight("mlb");
  state.sport = "mlb";
  PLAN = [{ body: { date: "MLB-FULL", games: [] } }];
  const before = PAINTS.length;
  const p = _loadNow(false);
  const atOnce = PAINTS.slice(before);
  await p;
  console.log(JSON.stringify({ atOnce, after: PAINTS.slice(before), skeletons: SKELETONS - skel,
    light: state.lightBoard, held: state.data.date, lightLeft: _lightMem.size }));
})();
""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["atOnce"] == ["MLB-LIGHT"], f"the light copy fetched while idle was not drawn at once: {got}"
    assert got["after"] == ["MLB-LIGHT", "MLB-FULL"] and got["held"] == "MLB-FULL"
    assert got["skeletons"] == 0, "no skeleton over a league whose light copy is in hand"
    assert got["light"] is False and got["lightLeft"] == 0, "the whole board replaces and releases the light copy"


def test_the_idle_fetch_is_polite():
    soon = _fn("prefetchLeaguesSoon")
    assert "c.saveData" in soon and "2g" in soon, "never on a data saver or 2G"
    assert "await prefetchLight(s);" in soon, "one league at a time"
    assert "s === state.sport" in soon and "b.hidden" in soon, "only the leagues on the bar, not this one"
    assert "prefetchLeaguesSoon();" in _fn("_loadNow", kind="async function")


def test_nfl_faces_ask_for_the_size_nfls_host_was_seen_to_serve():
    vis = (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")
    i = vis.index("function facePreview(")
    src = vis[vis.index("const FACE_TRANSFORM = "):vis.index("const FACE_TRANSFORM = ") + 1200]
    src = src[:src.index(";", src.index("const FACE_TRANSFORM_NFL")) + 1]
    body = vis[i:vis.index("\n}\n", i) + 2]
    esp = vis[vis.index("function espnFacePreview("):vis.index("function facePreview(")]
    got = _node(src + esp + body + r"""
      console.log(JSON.stringify({
        nfl: facePreview("https://static.www.nfl.com/image/upload/f_auto,q_auto/league/abc123", 40),
        mlb: facePreview("https://img.mlbstatic.com/mlb-photos/image/upload/w_180,q_auto/v1/people/1/headshot/67/current", 56) }));
    """)
    if got is None:
        print("  SKIP node not installed"); return
    assert got["nfl"] == "https://static.www.nfl.com/image/upload/f_auto,q_auto,w_80/league/abc123", got
    assert ",c_fill,g_face/" in got["mlb"], "MLB keeps the crop its own account verified"


def test_the_big_public_files_are_written_compact():
    """rosters_cfb.json was 22.6 MB on the box, two spaces of indentation on
    every line; record.json (1.5 MB) is read on the first screen. Compact
    JSON is the same data, ~40% fewer bytes to download and parse."""
    for path, needle in (("rosters_build.py", 'json.dumps(blob, separators=(",", ":"))'),
                         ("engine/ledger.py", '_json.dumps(out, separators=(",", ":"))'),
                         ("ufc_live_build.py", 'json.dumps(blob, separators=(",", ":"))')):
        src = (ROOT / path).read_text(encoding="utf-8")
        assert needle in src, f"{path} writes its public file pretty-printed again"


def test_the_first_screen_reads_a_slim_record_beside_the_full_one():
    """The record was the heaviest thing Home downloads (170 KB on the wire
    on the box, 2026-10-09), and over half of it was sections only the
    Record page draws. export_json writes record_head.json beside it
    without them; the first-screen readers ask for that, and fall back to
    the full file if the slim one is missing (an old export)."""
    sys.path.insert(0, str(ROOT))
    from engine import ledger
    d = tempfile.mkdtemp()
    try:
        conn = ledger.connect(os.path.join(d, "l.db"))
        conn.execute(
            "INSERT INTO bets (sport,date,player,market,side,line,odds,grade,"
            "stake_units,status,category,pnl_units,hit_prob) VALUES "
            "('nfl','2026-10-04','A','receptions','OVER',4.5,-110,'B',0.5,"
            "'won','main',0.45,0.6)")
        conn.commit()
        out = os.path.join(d, "record.json")
        ledger.export_json(conn, out)
        full = json.loads(open(out, encoding="utf-8").read())
        head = json.loads(open(os.path.join(d, "record_head.json"),
                               encoding="utf-8").read())
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert not set(head) & set(ledger.RECORD_PAGE_ONLY), \
        "the slim record carries a Record-page-only section"
    # Everything else is the same, value for value: the slim copy is a
    # subset, never a second version of the numbers.
    for k, v in head.items():
        assert full.get(k) == v, f"record_head.json disagrees with record.json on {k}"
    assert set(full) - set(head) <= set(ledger.RECORD_PAGE_ONLY)
    fn = _fn("loadRecordOnce", kind="async function")
    assert fn.index('"data/record_head.json"') < fn.index('"data/record.json"'), \
        "the first screen no longer asks for the slim copy first"
    assert "!res.ok" in fn, "no fallback to the full record when the slim one is missing"


def test_the_sections_left_out_are_read_only_on_the_record_page():
    """THE HALF THAT KEEPS THIS HONEST. A section left out of the slim copy
    and then read by a first-screen reader would draw as empty — a page
    saying "no data" about data that exists. So every left-out key may be
    read only inside the Record page's own functions, which fetch the
    whole record.json themselves."""
    sys.path.insert(0, str(ROOT))
    from engine.ledger import RECORD_PAGE_ONLY
    record_page = {"renderRecord", "_recordRooms", "recBookSections"}
    for js in sorted((ROOT / "web" / "js").glob("*.js")):
        src = js.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
        code = re.sub(r"(?m)^\s*//.*$", "", code)
        starts = [(m.start(), m.group(1)) for m in re.finditer(
            r"^(?:async )?function\s*\*?\s*([A-Za-z0-9_$]+)\s*\(", code, re.M)]
        for k in RECORD_PAGE_ONLY:
            for m in re.finditer(r"\b" + re.escape(k) + r"\b", code):
                owner = None
                for s, n in starts:
                    if s > m.start():
                        break
                    owner = n
                assert owner in record_page, \
                    (f"{js.name}: {k} is read in {owner}(), which may be handed the "
                     "slim record — keep it in the slim copy or read the full file there")
    rec = _fn("renderRecord", kind="async function")
    assert 'boardFetch("data/record.json"' in rec, \
        "the Record page stopped reading the full record"


def test_the_slim_record_is_a_free_file():
    """It is a strict subset of record.json, which is free; gated, it would
    resolve to a private copy nothing ever rewrites (the 2026-09-14 frozen
    record)."""
    sys.path.insert(0, str(ROOT))
    from engine import gate
    assert gate.is_free("record_head.json")
    assert "record_head.json" in gate.KNOWN_BOARDS


def test_board_reads_revalidate_instead_of_changing_their_address():
    """A `?t=<now>` on a data read makes every visit a new URL, so the
    browser can never answer it with a 304 — the college rosters were
    988 KB on the wire each time (the box, 2026-10-09). The two left are
    deliberate: the error-path fallback board (no-store, one read after
    a failure) and the UFC fight poller (a live file the Caddy fast rule
    does not cover)."""
    busted = re.findall(r'(?:board)?[fF]etch\(\s*[`"]([^`"]*\?(?:t|_)=)', APP)
    assert sorted(busted) == ["${meta.fallback}?_=", "data/ufc_live.json?t="], busted
    for name in ("rosters_${key}", "standings_${key}", "news", "bookreport",
                 "streak", "memerecord", "heartbeat"):
        assert re.search(r'boardFetch\([`"]data/' + re.escape(name)
                         + r'\.json[`"], \{ cache: "no-cache" \}\)', APP), \
            f"data/{name}.json is no longer a revalidating read"

if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
