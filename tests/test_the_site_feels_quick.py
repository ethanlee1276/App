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
    from PIL import Image
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
    import venues_ingest as V
    from PIL import Image
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
