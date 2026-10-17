"""The hit tracker is drawn before the reader scrolls down to it.

Ethan, 2026-10-14, with a pick page that read "The hit tracker didn't load.
Try again in a moment.": "Also we are running into issues where the hit
tracker won't load or takes forever too load. It should be snappy and
basically be loaded already when you scroll down too go view it."

Measured on a full-size database before the fix: the hit tracker itself
built in about 30 ms, and every request for it spent ten times that asking
statsapi for the league's rosters to find his photo (and up to thirty-one
requests of thirty seconds each when the cache had aged out); a name the
book prints without its accent read every plate appearance on file; the
page waited for his role chart and tonight's matchup — a cold matchup two
seconds — before it drew the one that leads; it asked for nothing until
the reader had scrolled to within a screen of it; and one dropped request
(a deploy's restart, a phone's connection) left it dead for the visit.

What is pinned, offline:

  * KEPT AND BUILT ONCE (engine/charts.answer_json): a built chart is
    kept fifteen minutes as the bytes the endpoint sends, per database
    file; however many ask at once, one builds; "still being filled" and
    ``{}`` are never kept; the kept answers stay under their cap; the
    database is opened only to build; the endpoint answers through it;
  * NO WIRE ON A PAGE'S REQUEST (engine/rosters.face_map,
    mlbstats.cached_active_rosters): his photo is read off the rosters the
    last fetch cached, whatever their age, hydrated or per club, and
    statsapi is never asked — while the build's own fetch still refreshes
    them; a baseball chart carries his photo off his own person id;
  * A SPELLING WITHOUT ITS ACCENT (engine/mlb/charts._resolve): the folded
    names are read once per database file (off the names' own index), and
    never kept for a database in memory;
  * ONE LEAGUE TABLE BUILD (engine/matchview._memo): the requests that
    want the same table wait for the one building it;
  * THE PAGE (js/carrychart.js): a request that fails on the wire or with
    a 5xx is asked again three times, a refusal is not, two asks for one
    chart are one request; the first chart on a page is asked for as the
    page opens and one further down a list as it nears the screen; his
    own chart is drawn the moment it is in, with places kept on the
    switch for his role and the matchup, which join it without the chart
    being drawn again; a chart that did not load says so with a button
    that asks again; while it loads, its shape shimmers;
  * IN A BROWSER (opt-in, QB_BROWSER_TESTS=1): all of that on a page, with
    the slot three thousand pixels down and nothing scrolled.

Run directly: `python3 tests/test_the_hit_tracker_is_there_when_you_get_to_it.py`
"""
import importlib.util
import inspect
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import charts as CH, db as D, matchview as MV, rosters as RO, statlogs as SL  # noqa: E402
from engine.mlb import charts as MC  # noqa: E402
from engine.mlb.sources import mlbstats as MS  # noqa: E402

_spec = importlib.util.spec_from_file_location("hit_fixture", ROOT / "tests" / "test_mlb_hit_tracker_and_pitch_chart.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

CC_JS = (ROOT / "web" / "js" / "carrychart.js").read_text(encoding="utf-8")
MLB_JS = (ROOT / "web" / "js" / "chart-mlb.js").read_text(encoding="utf-8")
ROLE_JS = (ROOT / "web" / "js" / "chart-role.js").read_text(encoding="utf-8")
MATCH_JS = (ROOT / "web" / "js" / "chart-matchup.js").read_text(encoding="utf-8")
CC_CSS = (ROOT / "web" / "css" / "carrychart.css").read_text(encoding="utf-8")


def _tmpdb():
    d = tempfile.mkdtemp()
    path = Path(d) / "history.db"
    D.connect(path).close()
    return d, path


# --- kept and built once ------------------------------------------------------------------
def test_a_built_chart_is_kept_and_built_once():
    d, path = _tmpdb()
    real, built = CH.answer, []

    def fake(conn, kind, sport, player, season=None, opp="", fam=""):
        built.append((kind, player, opp))
        return {"player": player, "kind": kind, "games": [{"id": 1}]}
    CH.forget()
    CH.answer = fake
    try:
        a = CH.answer_json(path, "spray", "mlb", "Aaron Judge")
        b = CH.answer_json(path, "spray", "mlb", "Aaron Judge", opp="DET", fam="spray")
        assert a == b and json.loads(a)["player"] == "Aaron Judge"
        assert built == [("spray", "Aaron Judge", "")], "kept; the opponent is no part of a hit tracker's answer"
        CH.answer_json(path, "matchup", "mlb", "Aaron Judge", opp="DET", fam="spray")
        CH.answer_json(path, "matchup", "mlb", "Aaron Judge", opp="DET", fam="spray")
        CH.answer_json(path, "matchup", "mlb", "Aaron Judge", opp="BOS", fam="spray")
        assert [b[2] for b in built[1:]] == ["DET", "BOS"], "the matchup is kept per opponent"
        CH.answer_json(path, "spray", "mlb", "Aaron Judge", season=2025)
        assert len(built) == 4, "and a hitter's chart per season"
        # Another database is another answer (a test's, a restored copy).
        d2, path2 = _tmpdb()
        try:
            CH.answer_json(path2, "spray", "mlb", "Aaron Judge")
        finally:
            shutil.rmtree(d2, ignore_errors=True)
        assert len(built) == 5
        # Fifteen minutes, then built again.
        keep = CH.ANSWER_TTL
        CH.ANSWER_TTL = -1
        try:
            CH.answer_json(path, "spray", "mlb", "Juan Soto")
            CH.answer_json(path, "spray", "mlb", "Juan Soto")
        finally:
            CH.ANSWER_TTL = keep
        assert [b[1] for b in built[5:]] == ["Juan Soto", "Juan Soto"]
        assert CH.ANSWER_TTL == 15 * 60
    finally:
        CH.answer = real
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_still_being_filled_and_nothing_on_file_are_never_kept():
    d, path = _tmpdb()
    real, built = CH.answer, []
    CH.forget()
    try:
        for out in ({"filling": True}, {}):
            CH.answer = lambda *a, out=out, **k: (built.append(1), dict(out))[1]
            assert json.loads(CH.answer_json(path, "spray", "mlb", "Aaron Judge")) == out
            assert json.loads(CH.answer_json(path, "spray", "mlb", "Aaron Judge")) == out
        assert len(built) == 4, "both can change within the minute"
    finally:
        CH.answer = real
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_one_build_however_many_ask_at_once():
    d, path = _tmpdb()
    real, built = CH.answer, []

    def slow(*a, **k):
        built.append(1)
        time.sleep(0.4)
        return {"player": "Aaron Judge", "games": [{"id": 1}]}
    CH.forget()
    CH.answer = slow
    got = []
    try:
        ts = [threading.Thread(target=lambda: got.append(CH.answer_json(path, "spray", "mlb", "Aaron Judge")))
              for _ in range(5)]
        [t.start() for t in ts]
        [t.join(10) for t in ts]
    finally:
        CH.answer = real
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)
    assert len(got) == 5 and len(set(got)) == 1
    assert built == [1], f"built {len(built)} times for five readers"


def test_the_kept_answers_stay_under_their_cap_and_the_database_is_opened_only_to_build():
    d, path = _tmpdb()
    real, keep_cap, real_connect = CH.answer, CH.ANSWER_CAP, D.connect
    opened = []
    CH.forget()
    CH.answer = lambda conn, kind, sport, player, *a, **k: {"player": player, "pad": "x" * 1400, "games": [1]}
    CH.ANSWER_CAP = 12000            # eight of these ~1.4 KB answers fit; an answer over 1.5 KB is never kept

    def counting(*a, **k):
        opened.append(1)
        return real_connect(*a, **k)
    D.connect = counting
    try:
        for i in range(9):
            CH.answer_json(path, "spray", "mlb", f"P{i}")
        assert len(opened) == 9
        assert CH._BYTES[0] <= CH.ANSWER_CAP and len(CH._KEPT) == 8
        assert not any(k[3] == "P0" for k in CH._KEPT), "the oldest read out first"
        CH.answer_json(path, "spray", "mlb", "P8")
        assert len(opened) == 9, "a kept answer opens nothing"
        CH.answer_json(path, "spray", "mlb", "P0")
        assert len(opened) == 10, "the one read out is built again"
        CH.answer = lambda *a, **k: {"player": "Big", "pad": "x" * 2000, "games": [1]}
        CH.answer_json(path, "spray", "mlb", "Big")
        assert not any(k[3] == "Big" for k in CH._KEPT), "one answer never crowds out the rest"
    finally:
        CH.answer, CH.ANSWER_CAP, D.connect = real, keep_cap, real_connect
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)


def test_the_endpoint_answers_through_the_kept_answers():
    import server
    src = inspect.getsource(server.Handler._players_chart)
    assert "charts.answer_json(_hdb.DEFAULT_DB, kind, sport, player," in src
    assert "charts.answer(conn" not in src
    d, path = _tmpdb()
    keep = D.DEFAULT_DB
    sent = []
    CH.forget()
    try:
        F._conn(path).close()
        D.DEFAULT_DB = path
        h = object.__new__(server.Handler)
        h._send = lambda code, body, ext=".json": sent.append((code, body))
        for _ in range(2):
            h._players_chart({"kind": ["spray"], "sport": ["mlb"], "player": ["Aaron Judge"]})
    finally:
        D.DEFAULT_DB = keep
        CH.forget()
        shutil.rmtree(d, ignore_errors=True)
    assert sent[0][0] == 200 and sent[0][1] == sent[1][1]
    assert json.loads(sent[0][1])["season_line"]["hr"] == 1


# --- no wire on a page's request --------------------------------------------------------------
HYDRATED = {"teams": [{"id": 147, "abbreviation": "NYY", "roster": {"roster": [
    {"person": {"fullName": "Aaron Judge", "id": 592450}, "position": {"abbreviation": "RF"},
     "jerseyNumber": "99", "status": {"description": "Active"}}]}}]}
UNHYDRATED = {"teams": [{"id": 147, "abbreviation": "NYY"}, {"id": 158, "abbreviation": "MIL"}]}
PER_CLUB = {"roster": [{"person": {"fullName": "Christian Yelich", "id": 592885}, "position": {"abbreviation": "LF"},
                        "jerseyNumber": "22", "status": {"description": "Active"}}]}


def _cache(files: dict, age_s: float):
    d = tempfile.mkdtemp()
    for name, body in files.items():
        p = Path(d) / name
        p.write_text(json.dumps(body))
        t = time.time() - age_s
        os.utime(p, (t, t))
    return d


def _no_wire():
    asked = []

    def urlopen(*a, **k):
        asked.append(getattr(a[0], "full_url", a[0]))
        raise OSError("the page's request may not go to the wire")
    return asked, urlopen


def test_a_pages_photo_is_read_off_the_cached_rosters_and_never_asks():
    asked, urlopen = _no_wire()
    keep_dir, keep_open = MS.CACHE_DIR, MS.urllib.request.urlopen
    for files, who, pid in (({"mlb_active_rosters.json": HYDRATED}, "Aaron Judge", 592450),
                            ({"mlb_active_rosters.json": UNHYDRATED, "mlb_roster_158.json": PER_CLUB},
                             "Christian Yelich", 592885)):
        d = _cache(files, age_s=3 * 86400)            # three days old: long past the six hours
        RO._FACE_MEMO.clear()
        try:
            MS.CACHE_DIR, MS.urllib.request.urlopen = Path(d), urlopen
            faces = RO.face_map(None, "mlb")
            assert faces.get(RO._norm_key(who)) == MS.headshot_url(pid), (who, faces)
            conn = D.connect(":memory:")
            assert SL.face(conn, "mlb", who) == MS.headshot_url(pid)
            assert MS.cached_active_rosters() and asked == [], asked
        finally:
            MS.CACHE_DIR, MS.urllib.request.urlopen = keep_dir, keep_open
            RO._FACE_MEMO.clear()
            shutil.rmtree(d, ignore_errors=True)
    # Nothing cached is no faces — and still no request.
    d = tempfile.mkdtemp()
    try:
        MS.CACHE_DIR, MS.urllib.request.urlopen = Path(d), urlopen
        assert MS.cached_active_rosters() == {} and RO.face_map(None, "mlb") == {} and asked == []
    finally:
        MS.CACHE_DIR, MS.urllib.request.urlopen = keep_dir, keep_open
        RO._FACE_MEMO.clear()
        shutil.rmtree(d, ignore_errors=True)


def test_the_builds_own_fetch_still_refreshes_them():
    asked, urlopen = _no_wire()
    keep_dir, keep_open = MS.CACHE_DIR, MS.urllib.request.urlopen
    d = _cache({"mlb_active_rosters.json": HYDRATED}, age_s=3 * 86400)
    try:
        MS.CACHE_DIR, MS.urllib.request.urlopen = Path(d), urlopen
        out = MS.fetch_active_rosters()
        assert asked and "statsapi" in str(asked[0]), "an aged cache is refetched on the build's path"
        assert [p["name"] for p in out["NYY"]] == ["Aaron Judge"], "and the old file answers when the wire fails"
        assert RO._faces(None, "mlb") and len(asked) == 2, "_faces asks unless told not to"
        RO._faces(None, "mlb", offline=True)
        assert len(asked) == 2
    finally:
        MS.CACHE_DIR, MS.urllib.request.urlopen = keep_dir, keep_open
        shutil.rmtree(d, ignore_errors=True)
    src = inspect.getsource(RO.face_map)
    assert "_faces(conn, sport, offline=True)" in src


def test_a_baseball_chart_carries_his_photo_off_his_own_id():
    conn = F._conn()
    assert MC.hits_chart(conn, "Aaron Judge")["face"] == MS.headshot_url(F.JUDGE)
    assert MC.pitches_chart(conn, "Gerrit Cole")["face"] == MS.headshot_url(F.COLE)


# --- a spelling without its accent --------------------------------------------------------------
def _accented(path=":memory:"):
    conn = D.connect(path)
    jr = (677594, "Julio Rodríguez")
    plays = [F._play(0, "top", jr, (600, "Seth Lugo"), "Single", "single", [F._pitch(1, "X")])]
    pas, pitches = MC.fold({"allPlays": plays}, {"game_pk": 778000, "date": "2026-09-02", "home": "KC",
                                                 "away": "SEA", "type": "R"})
    D.upsert_mlb_pa(conn, pas)
    D.upsert_mlb_pitches(conn, pitches)
    return conn


def test_the_folded_names_are_read_once_per_database_file():
    d = tempfile.mkdtemp()
    MC._FOLDED.clear()
    try:
        conn = _accented(str(Path(d) / "history.db"))
        seen = []
        conn.set_trace_callback(seen.append)
        assert MC._resolve(conn, "Julio Rodriguez", "batter") == (677594, "Julio Rodríguez")
        scans = [q for q in seen if "SELECT DISTINCT batter FROM mlb_pa" in q]
        assert len(scans) == 1, "the names alone, off their own index"
        assert not any("SELECT DISTINCT batter_id, batter FROM mlb_pa" in q and "WHERE" not in q for q in seen), \
            "never every plate appearance on file"
        seen.clear()
        assert MC._resolve(conn, "julio rodriguez", "batter") == (677594, "Julio Rodríguez")
        assert not [q for q in seen if "SELECT DISTINCT batter FROM mlb_pa" in q], "kept for the next ask"
        assert MC._resolve(conn, "Nobody Here", "batter") == (None, "")
        assert MC.FOLDED_TTL == 10 * 60
    finally:
        MC._FOLDED.clear()
        shutil.rmtree(d, ignore_errors=True)
    mem = _accented()
    assert MC._resolve(mem, "Julio Rodriguez", "batter") == (677594, "Julio Rodríguez")
    assert not MC._FOLDED, "a database in memory is never kept"


# --- one league table build ---------------------------------------------------------------------
def test_one_league_table_build_however_many_ask():
    d, path = _tmpdb()
    built, got = [], []

    def build():
        built.append(1)
        time.sleep(0.3)
        return {"table": 1}

    def one():
        conn = sqlite3.connect(str(path))
        try:
            got.append(MV._memo(conn, ("test-table", 2026), build))
        finally:
            conn.close()
    try:
        ts = [threading.Thread(target=one) for _ in range(4)]
        [t.start() for t in ts]
        [t.join(10) for t in ts]
    finally:
        for k in [k for k in MV._MEMO if "test-table" in k]:
            MV._MEMO.pop(k, None)
        shutil.rmtree(d, ignore_errors=True)
    assert built == [1] and got == [{"table": 1}] * 4


# --- the page --------------------------------------------------------------------------------------
def _body(name):
    i = CC_JS.index(f"  function {name}(")
    return CC_JS[i:CC_JS.index("\n  }\n", i)]


def test_the_page_asks_again_when_the_wire_fails():
    assert "const RETRY_MS = [800, 2500, 5000];" in CC_JS and "const ASK_MS = 25000;" in CC_JS
    get = _body("get")
    assert "new AbortController()" in get and "setTimeout(() => ctl.abort(), ASK_MS)" in get
    assert "if (r.status < 500 && r.status !== 408 && r.status !== 429) return null;" in get, "a refusal is an answer"
    ask = _body("ask")
    assert "if (cached && FLIGHT.has(q)) return FLIGHT.get(q);" in ask
    assert "if (data && !data.filling) CACHE.set(q" in ask


def test_the_first_chart_on_a_page_is_asked_for_as_it_opens():
    mount = _body("mount")
    assert 'if (page.querySelector(".cc-slot") === el || typeof IntersectionObserver !== "function") return probe(c);' \
        in mount
    assert 'rootMargin: "1600px 0px"' in mount


def test_his_own_chart_draws_the_moment_it_is_in():
    probe = _body("probe")
    assert "c.cand.forEach((k) => need(k));" in probe, "each drawing is fetched beside its data"
    assert "const own = c.cand.every((k, i) => LATE[k] || ds[i] !== undefined);" in probe
    assert "if (!all && !(own && !wait && c.cand.some((k, i) => !LATE[k] && vol(k, ds[i]) > 0))) return;" in probe
    assert "choose(!all);" in probe and "return rebar(c);" in probe
    assert "const ds = c.cand.map(() => undefined), wait = LATE[MEM.get(c.key)];" in probe, \
        "a reader who chose his role or the matchup on this pick waits for it"
    assert "if (ds.every((x) => x === null)) c.kinds = null;" in probe
    assert 'cc-chip cc-pend" aria-hidden="true"' in _body("kindBar")
    rebar = _body("rebar")
    assert "at.outerHTML = html;" in rebar and "render()" not in rebar, "the chart under the switch is not redrawn"


def test_a_chart_that_did_not_load_says_so_and_asks_again():
    assert "data-retry>Try again</button>" in _body("fail")
    land = _body("land")
    assert "if (data === null) return fail(c);" in land
    assert "if (!ok && !DRAW[S.kind]) return fail(c);" in land, "never drawn as another chart"
    assert 'if (hit(e, "[data-retry]")) return c.cand && !c.kinds ? probe(c) : load(c, c.last == null ? null : c.last);' \
        in CC_JS
    assert "c.last = season;" in _body("load")
    assert "Try again in a moment" not in CC_JS


def test_while_it_loads_its_shape_shimmers():
    assert '<i class="cc-sk cc-sk-hero"></i>' in CC_JS and 'class="cc-wait" role="status"' in CC_JS
    for sel in (".cc-sk {", ".cc-sk-hero", ".cc-sk-fig", ".cc-chip.cc-pend", ".cc-fail", "var(--skeleton)",
                "animation: shimmer"):
        assert sel in CC_CSS, sel
    i = CC_CSS.index(".cc-chip.cc-pend")
    assert "@media (prefers-reduced-motion: reduce)" in CC_CSS[i:i + 900]
    import re
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"
    assert "onclick" not in CC_JS and "onerror" not in CC_JS and not re.search(r"on(error|load)\s*=", CC_JS)


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
      const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {};
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n(async () => {{ const T = window.QBCarry._t; T.RETRY_MS.splice(0, 3, 5, 5, 5); {js} }})()"
            ".then((v) => console.log(JSON.stringify(v)), (e) => { console.error(e); process.exit(1); });")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_in_node_a_dropped_request_is_asked_again_and_a_refusal_is_not():
    got = _node("""
      const run = async (plan, who, cached) => {
        const calls = [];
        globalThis.fetch = async (q) => {
          const step = plan[Math.min(calls.length, plan.length - 1)];
          calls.push(q);
          if (step === "drop") throw new TypeError("Failed to fetch");
          if (typeof step === "number") return { ok: false, status: step, json: async () => ({}) };
          return { ok: true, status: 200, json: async () => ({ player: who, games: [1] }) };
        };
        const d = await T.ask("spray", "mlb", who, null, cached);
        return { n: calls.length, d };
      };
      const out = {};
      out.recovers = await run(["drop", 502, "ok"], "A", false);
      out.refused = await run([404], "B", false);
      out.gives_up = await run([503], "C", false);
      out.limit = await run([408, 429, "ok"], "D", false);
      // Two asks for one chart at once are one request.
      let n = 0;
      globalThis.fetch = async () => { n++; await new Promise((r) => setTimeout(r, 20));
                                       return { ok: true, status: 200, json: async () => ({ games: [1] }) }; };
      const [a, b] = await Promise.all([T.ask("spray", "mlb", "E", null, true), T.ask("spray", "mlb", "E", null, true)]);
      out.once = { n, same: a === b };
      return out;""")
    if got is None:
        return
    assert got["recovers"] == {"n": 3, "d": {"player": "A", "games": [1]}}
    assert got["refused"] == {"n": 1, "d": None}, "a refusal is an answer"
    assert got["gives_up"] == {"n": 4, "d": None}, "three more tries, then the chart says so"
    assert got["limit"]["n"] == 3 and got["limit"]["d"]["player"] == "D", "a timeout or a slow-down is asked again"
    assert got["once"] == {"n": 1, "same": True}


# --- the browser, opt-in --------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div class="view">
  <div style="height:3000px">the top of the pick page</div>
  <div class="cc-slot" data-cc="Aaron Judge" data-lg="mlb" data-mkt="batter_hits" data-pos="RF" data-opp="DET"></div>
  <div style="height:9000px"></div>
  <div class="cc-slot" data-cc="Juan Soto" data-lg="mlb" data-mkt="batter_hits" data-pos="RF" data-opp="DET"></div>
  <div style="height:600px"></div>
</div>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = (lg, a) => `<i>${{a}}</i>`, teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  window.ASKED = []; window.FAILS = {fails}; window.T0 = performance.now();
  window.fetch = (q) => {{
    const k = /kind=(\\w+)/.exec(q)[1], who = decodeURIComponent(/player=([^&]+)/.exec(q)[1]).replace(/\\+/g, " ");
    window.ASKED.push(k + ":" + who);
    if ((window.FAILS[k] || 0) > 0) {{ window.FAILS[k]--; return Promise.resolve({{ ok: false, status: 502 }}); }}
    const data = k === "spray" ? window.CHART : k === "role" ? window.ROLE : window.MATCH;
    return new Promise((ok) => setTimeout(() => {{
      if (k === "role") window.ROLE_AT = performance.now() - window.T0;
      ok({{ ok: true, status: 200, json: async () => data }});
    }}, k === "role" ? 1500 : 30));
  }};
</script>
<script>{js}</script>
<script>
  window.QBCarry._t.RETRY_MS.splice(0, 3, {retry});
  window.go = (c, r, m) => {{
    window.CHART = c; window.ROLE = r; window.MATCH = m;
    document.querySelectorAll(".cc-slot").forEach((el) => window.QBCarry.mount(el));
  }};
</script></body></html>"""


def _browser_payloads():
    """His hit tracker off the fixture, and his role and tonight's matchup in
    the shapes the server answers them (engine/role, engine/matchview)."""
    d = MC.hits_chart(F._conn(), "Aaron Judge")
    d.update(position="RF", jersey="99", kind="spray", face="")
    y = d["season"]
    metrics = [{"key": "pa", "name": "Plate appearances", "short": "PA", "unit": "n"},
               {"key": "spot", "name": "Spot in the order", "short": "Spot", "unit": "spot"}]
    avg = {"pa": 4.0, "spot": 2.0}
    role = {"player": "Aaron Judge", "sport": "mlb", "seasons": [y], "season": y, "season_label": str(y),
            "team": "NYY", "position": "", "lead": "pa", "metrics": metrics, "kind": "role", "face": "",
            "season_line": {"n": 3, "games": 3, "avg": avg, "high": avg, "low": avg, "last3": avg, "last5": avg,
                            "starts": 3, "start_known": 3},
            "splits": {},
            "games": [{"id": f"{y}-10-0{i}", "period": f"{y}-10-0{i}", "date": f"{y}-10-0{i}", "team": "NYY",
                       "opp": "DET", "home": True, "start": True, "v": dict(avg), "score": [4.0, 2.0]}
                      for i in (1, 2, 3)]}
    zone = lambda key, name, n: {"key": key, "name": name, "n": n, "share": 0.5, "rn": 40, "raw": 0.4,
                                 "rate": 0.41, "league": 0.39, "diff": 0.02}
    match = {"player": "Aaron Judge", "sport": "mlb", "family": "hitter", "season": y, "seasons": [y], "newest": y,
             "his_season": y, "opp": "DET", "asked": "DET", "k": 30,
             "zones": [zone("heart", "Heart of the zone", 300), zone("down", "Down in the zone", 280)],
             "fit": 0.01, "overall": {"rate": 0.4, "league": 0.39, "n": 580, "rank": 12, "of": 30},
             "season_line": {"n": 580}, "games": [], "left": "Where their staff pitches", "right": "His slugging",
             "unit": "slugging", "fmt": "slg", "good": 1, "tested": False, "kind": "matchup", "face": ""}
    return d, role, match


def test_in_a_browser_the_hit_tracker_is_drawn_before_the_reader_gets_there():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    payloads = list(_browser_payloads())
    js = "\n".join((CC_JS, MLB_JS, ROLE_JS, MATCH_JS))
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_content(PAGE.format(css=CC_CSS, js=js, fails='{"matchup": 1}', retry="300, 300, 300"))
            page.evaluate("([c, r, m]) => window.go(c, r, m)", payloads)
            # Nothing scrolled: his chart is asked for and drawn, three thousand pixels down.
            page.wait_for_selector(".cc-slot .mb-hero", timeout=3000)
            assert page.evaluate("window.scrollY") == 0
            assert page.evaluate("window.ROLE_AT === undefined"), "drawn before his role chart came back"
            assert page.evaluate("document.querySelectorAll('.cc-slot .cc-pend').length") >= 1, \
                "a place kept on the switch"
            page.evaluate("window.HERO = document.querySelector('.cc-slot .mb-hero')")
            page.wait_for_function("document.querySelector(\"[data-ck='role']\") && "
                                   "document.querySelector(\"[data-ck='matchup']\") && "
                                   "!document.querySelector('.cc-pend')", timeout=5000)
            assert page.evaluate("document.querySelector('.cc-slot .mb-hero') === window.HERO"), \
                "his role and the matchup joined the switch without the chart being drawn again"
            asked = page.evaluate("window.ASKED")
            assert asked.count("matchup:Aaron Judge") == 2, "the dropped matchup was asked again"
            assert not any("Juan Soto" in a for a in asked), "a slot further down waits until it nears the screen"
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_function("window.ASKED.some((a) => a === 'spray:Juan Soto')", timeout=3000)
            # The switch works with what joined it.
            page.click(".cc-slot [data-ck='matchup']")
            assert not errors, errors

            # Nothing comes back at all: it says so, and Try again asks again.
            page = browser.new_page(viewport={"width": 390, "height": 800})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_content(PAGE.format(css=CC_CSS, js=js, fails='{"spray": 99, "role": 99, "matchup": 99}',
                                         retry="5, 5, 5"))
            page.evaluate("([c, r, m]) => window.go(c, r, m)", payloads)
            page.wait_for_selector(".cc-slot .cc-fail [data-retry]", timeout=3000)
            assert "didn’t load" in page.evaluate("document.querySelector('.cc-slot .cc-fail').textContent")
            page.evaluate("window.FAILS = {}")
            page.click(".cc-slot [data-retry]")
            page.wait_for_selector(".cc-slot .mb-hero", timeout=5000)
            assert not errors, errors
        finally:
            browser.close()


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
