"""Real addresses — /mlb, /player/juan-soto, /game/ne-sea-0909, /pick/…

Ethan, 2026-08-25: *"Give the site places — entity pages and real URLs …
links unfurl correctly in texts."*

Three things have to hold, and they are in different files, which is
why this file exists rather than a few lines added to three others:

  * the SLUGS have to mean the same thing in Python and in JavaScript,
    or Copy link emits an address the server cannot resolve;
  * the preview text for a PICK must never carry the pick. This module
    reads the private board — it has to, or a permalink breaks for
    exactly the picks worth sharing — so the discipline is in what it
    prints, and that discipline needs a test that fails loudly;
  * a path that is not a route must keep falling through to the static
    handler and the real 404.

Run directly: `python3 tests/test_routes.py`
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import routes                                    # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")
CADDY = _read("deploy", "Caddyfile")
SERVER = _read("server.py")


# --- the slugs, both spellings ----------------------------------------------

NAMES = ["Juan Soto", "José Ramírez", "Ronald Acuña Jr.", "T.J. Watt",
         "De'Von Achane", "Amon-Ra St. Brown", "  padded  ", "O'Neil Cruz"]


def _node():
    return shutil.which("node") or shutil.which("nodejs")


def test_the_two_slugify_implementations_agree():
    """Copy link is written in JavaScript and resolved in Python. A
    disagreement about one apostrophe is a link that 404s for the only
    people who ever click it — the ones it was sent to.

    Run in NODE against the real function lifted out of app.js, not
    eyeballed. Where node is missing the shapes are compared instead,
    and the test says which of the two it did.
    """
    want = [routes.slugify(n) for n in NAMES]
    node = _node()
    if not node:
        # The weaker check, named as such: the same normalisation, the
        # same class of kept characters, the same trim.
        fn = APP[APP.index("function slugify(text)"):]
        fn = fn[:fn.index("\n}")]
        assert 'normalize("NFD")' in fn and "\\u0300-\\u036f" in fn
        assert "[^A-Za-z0-9]+" in fn and "toLowerCase()" in fn
        return
    src = APP[APP.index("function slugify(text)"):]
    src = src[:src.index("\n}") + 2]
    prog = src + "\nconsole.log(JSON.stringify(%s.map(slugify)));" % json.dumps(NAMES)
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True,
                         timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == want, "the slugs have drifted apart"


def test_a_pick_slug_is_the_player_and_the_market_and_nothing_else():
    """The side and the line are the PICK. In the address they would be
    published in the share text itself, in every group chat the link is
    forwarded to, before anybody clicked anything."""
    row = {"player": "Juan Soto", "market": "home_runs", "side": "OVER",
           "line": 0.5, "odds": 320}
    slug = routes.pick_slug(row)
    assert slug == "juan-soto-home-runs"
    for leak in ("over", "0-5", "320"):
        assert leak not in slug


def test_a_game_slug_names_the_meeting_not_just_the_teams():
    g = {"away": "NE", "home": "SEA", "date": "2026-09-09"}
    assert routes.game_slug(g) == "ne-sea-0909"
    assert routes.game_slug(dict(g, game_number=2)) == "ne-sea-0909-g2"
    # A doubleheader's second game is a different game, different
    # lineups, different prices — and it must not share an address.
    assert routes.game_slug(dict(g, game_number=2)) != routes.game_slug(g)


# --- the gate, applied to preview text ---------------------------------------

def _tree(files):
    """A throwaway tree, and it has to be shaped `<root>/web/data`.

    `gate.board_source` derives the private directory from the public
    one — `…/web/data` → `…/data/built` — and falls back to the repo's
    real data/built for anything else. A fixture in a bare temp dir
    therefore reads THIS MACHINE'S boards, which is how the first cut of
    this file passed while testing nothing. Returns the web/ path.
    """
    tmp = tempfile.mkdtemp(prefix="qbroutes")
    data = os.path.join(tmp, "web", "data")
    os.makedirs(data)
    for name, doc in files.items():
        with open(os.path.join(data, name), "w") as fh:
            json.dump(doc, fh)
    return os.path.join(tmp, "web")


def test_a_pick_preview_never_carries_the_pick():
    """THE ONE THAT MATTERS. `find_pick` reads the private copy, so this
    function can see the product. A preview card reading "Juan Soto OVER
    0.5 home runs, +11% edge" is the paid board published to anyone who
    can guess a slug, one row at a time."""
    row = {"player": "Juan Soto", "team": "NYY", "opponent": "BOS",
           "market": "home_runs", "market_label": "Home Runs",
           "side": "OVER", "line": 0.5, "odds": 320, "book": "DraftKings",
           "projection": 0.71, "hit_prob": 0.41, "edge": 0.113,
           "stake_units": 1.4, "ev": 0.09}
    web = _tree({"recommendations.json": {"recommendations": [row]}})
    try:
        meta = routes.pick_meta("juan-soto-home-runs", web)
        blob = (meta["title"] + " " + meta["description"]).lower()
        assert "juan soto" in blob and "home runs" in blob, \
            "the preview does not even name what it is"
        assert "bos" in blob or "nyy" in blob, "no matchup in the preview"
        for leak in ("over", "0.5", "320", "0.71", "41%", "11", "1.4",
                     "draftkings", "edge", "projection", "stake"):
            assert leak not in blob, f"the preview leaks {leak!r}"
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


def test_the_pick_resolver_has_exactly_one_caller():
    """`find_pick` returns the whole row. A second caller is a second
    place to print it, and this is the file that would not notice."""
    src = _read("engine", "routes.py")
    assert src.count("find_pick(") == 2, \
        "find_pick has grown a caller — check what it prints"
    # …and nothing outside this module reaches for it.
    hits = []
    for base, _dirs, files in os.walk(ROOT):
        if any(p in base for p in (".git", "node_modules", "__pycache__")):
            continue
        for f in files:
            if not f.endswith(".py") or f in ("routes.py", "test_routes.py"):
                continue
            try:
                body = open(os.path.join(base, f), encoding="utf-8").read()
            except OSError:
                continue
            if "find_pick(" in body:
                hits.append(f)
    assert not hits, f"find_pick is called from {hits}"


def test_a_player_page_works_for_somebody_nobody_priced():
    """The rosters are free files carrying every player in every league
    we ingest. A player page that only worked for tonight's board would
    be a board page with a different name."""
    web = _tree({"rosters_nfl.json": {"teams": {"NO": {"players": [
        {"player": "Chris Olave", "team": "NO", "position": "WR"}]}}}})
    try:
        meta = routes.player_meta("chris-olave", web)
        assert "Chris Olave" in meta["title"]
        assert meta["sport"] == "nfl"
        assert meta["hash"] == "player/nfl/chris-olave"
    finally:
        shutil.rmtree(os.path.dirname(web), ignore_errors=True)


# --- what is and is not a route ----------------------------------------------

def test_an_unknown_path_is_not_a_route():
    """It has to keep falling through to the static handler, which is
    what serves the real files and the real 404. A router that swallowed
    unknown paths would turn every typo into a soft landing on the
    board."""
    for path in ("/nope", "/", "/player", "/player/x/y/z", "/deep/er/still",
                 "/checkout", "/paywall", "/signup"):
        assert routes.resolve(path) is None, f"{path} resolved to something"


def test_every_section_names_a_view_the_app_actually_has():
    """A table that can invent a destination is a table that will."""
    order = APP[APP.index("const VIEW_ORDER = ["):]
    order = order[:order.index("];")]
    sports = ["mlb", "nfl", "nba", "wnba", "cfb"]
    for name, (kind, target, label, desc) in routes.SECTIONS.items():
        assert label and desc, f"{name} has no preview text"
        if kind == "sport":
            assert target in sports, f"{name} names a league we do not build"
        else:
            assert f'"{target}"' in order, f"{name} points at a view that is gone"


def test_the_proxy_and_the_table_name_the_same_sections():
    """Caddy has to hand these paths to the app or the preview tags
    never get written — the page would still work, off disk, unfurling
    as the generic site card in every text message."""
    block = CADDY[CADDY.index("handle /mlb /nfl"):]
    block = block[:block.index("{")]
    listed = set(re.findall(r"/([a-z]+)", block))
    assert listed == set(routes.SECTIONS), \
        f"the Caddyfile and SECTIONS disagree: {listed ^ set(routes.SECTIONS)}"
    assert "handle /player/* /game/* /pick/*" in CADDY


def test_a_real_file_beats_a_route():
    """/privacy.html is a page on disk. If a route ever claimed a name a
    file also uses, the file is what every existing link expects."""
    i = SERVER.index("def _entity_page")
    body = SERVER[i:SERVER.index("\n    def _static", i)]
    assert 'if "." in path.rsplit("/", 1)[-1]' in body, \
        "an asset path would be answered with a page of HTML"
    assert "target.is_file()" in body and "return False" in body


# --- the document ------------------------------------------------------------

def test_the_preview_block_is_marked_in_the_page_itself():
    assert routes.META_OPEN in HTML and routes.META_CLOSE in HTML
    head = HTML.index(routes.META_OPEN)
    tail = HTML.index(routes.META_CLOSE)
    block = HTML[head:tail]
    for tag in ("<title>", "og:title", "og:description", "canonical", "og:url"):
        assert tag in block, f"{tag} is outside the block that gets swapped"
    # The icon and manifest tags are the same on every page; re-emitting
    # them per entity is one more thing to drift.
    assert 'rel="manifest"' not in block and 'rel="icon"' not in block


def test_every_relative_asset_resolves_from_the_root():
    """The one line that makes two-segment addresses possible. Without
    it `css/styles.css` at /player/juan-soto resolves to
    /player/css/styles.css, and the page arrives unstyled with no
    script — a 404 nobody sees, on the links most likely to be a
    stranger's first visit."""
    assert '<base href="/" />' in HTML
    assert HTML.index('<base href="/" />') < HTML.index('href="css/styles.css"')


def test_the_swapped_document_is_the_app_not_a_landing_page():
    route = routes.resolve("/record")
    doc = routes.document(route, HTML)
    assert "Track record" in doc[:doc.index("</head>")]
    assert 'id="view-record"' in doc, "the app's own markup is gone"
    assert doc.count("<base href=\"/\" />") == 1
    assert "__QB_ROUTE__" in doc
    hint = json.loads(re.search(r"__QB_ROUTE__ = (\{.*?\});", doc).group(1))
    assert hint["hash"] == "record"


def test_the_hint_cannot_close_the_script_it_rides_in():
    """The one injection a JSON blob in a <script> still has: a slug
    containing `</script>` would end the element early and everything
    after it becomes markup."""
    doc = routes.document({"hash": "player/x</script><img src=x>",
                           "sport": "", "kind": "player"}, HTML)
    assert "</script><img" not in doc
    assert "<\\/script>" in doc


def test_the_preview_image_is_absolute_on_an_entity_page():
    """A scraper is not a browser: most resolve a relative image against
    the page URL without reading <base>, so `og-card-v2.png` at
    /player/juan-soto is fetched from /player/ and the link unfurls with
    no picture at all."""
    block = routes.meta_block(routes.resolve("/record"))
    m = re.search(r'og:image" content="([^"]+)"', block)
    assert m and m.group(1).startswith("https://qellysbook.com/")


# --- the app's half ----------------------------------------------------------

def test_the_clean_url_is_adopted_before_the_chrome_is_drawn():
    """/mlb has to have switched the league before applySport runs, or
    the page comes up wearing the NFL's tabs over baseball's board."""
    i = APP.index("\nadoptCleanURL();")
    j = APP.index("\napplySport();")
    assert i < j


def test_both_hash_entry_points_route_entities():
    """A cold load never fires hashchange and a hashchange is not a cold
    load, so a route registered in one of the two is a link that works
    only when you were already on the site."""
    assert APP.count("if (entityRoute(h)) return;") == 2
    assert APP.count('h.startsWith("prop/")') == 2, "both legacy entry points"


def test_old_links_still_open():
    """#game/2026-09-09_NE@SEA and #prop/Juan Soto|home_runs|OVER|0.5 are
    in somebody's messages already. Both resolvers take either
    spelling."""
    fn = APP[APP.index("const findGame = "):]
    fn = fn[:fn.index(";\n")]
    assert "gameId(g) === gid" in fn and "gameSlug(g) === gid" in fn
    fn = APP[APP.index("function findProp(id)"):]
    fn = fn[:fn.index("\n}")]
    assert "propId(x) === id" in fn and "pickSlug(x) === id" in fn


def test_a_sub_routed_page_keeps_its_own_address():
    """The bug this guard replaces: the prop branch wrote
    `#pick/juan-soto-…` and then fell through to a line that saw
    `location.hash !== "#prop"` and replaced the id with a bare `#prop`
    — so every pick link flattened itself before it could be copied, and
    refreshing one landed on "That pick is not on tonight's board" for a
    pick that was."""
    assert "const subRouted = (name === \"prop\" && state.propId)" in APP
    assert "if (!subRouted && location.hash !== `#${name}`)" in APP


def test_a_player_page_keeps_his_name_in_the_address():
    """Same flattening the prop page had, from the other side: the
    Players view would write `#players` over `#player/chris-olave` on
    the way in, so the one URL worth copying survived until the render
    finished. And typing in the box clears it — a search is not a
    player page, and an address claiming to link to whoever was open
    before is worse than a generic one."""
    assert '`#player/${encodeURIComponent(state.playerSlug)}`' in APP
    assert '(name === "players" && state.playerSlug)' in APP
    i = APP.index('document.getElementById("player-search").addEventListener("input"')
    body = APP[i:i + 600]
    assert 'state.playerSlug = ""' in body
    assert 'history.replaceState(null, "", "#players")' in body


def test_the_players_render_cannot_be_overwritten_by_its_own_slow_lookup():
    """A deep link renders before the board has landed, so it takes the
    league-search path — and its two requests come back AFTER renderAll
    has drawn the real profile from the board. The late write replaced
    it with "No players match", for a player who was on the board.
    Measured in Chromium on the route that made player pages linkable."""
    i = APP.index("async function renderPlayers()")
    body = APP[i:APP.index("\nfunction profileHTML", i)]
    assert "const seq = ++_playersSeq;" in body
    assert body.count("if (seq !== _playersSeq) return;") >= 3, \
        "an await without a token check is a render that can lose a race"


def test_the_share_control_emits_the_clean_url_not_the_address_bar():
    """The address bar shows the app's hash spelling of the same place,
    and a hash is the half a scraper never sees."""
    fn = APP[APP.index("function copyLink(kind, slug, btn)"):]
    fn = fn[:fn.index("\n}")]
    assert "cleanURL(kind, slug)" in fn
    assert "navigator.share" in fn and "navigator.clipboard" in fn
    for surface in ('shareBtn("pick", pickSlug(r))',
                    'shareBtn("game", gameSlug(g))',
                    'shareBtn("player", slugify(r.player))'):
        assert surface in APP, f"no share control on {surface}"


def test_a_player_page_is_the_players_view_with_his_name_in_it():
    """Not a new page: the profile card already draws the headshot, the
    game logs and the form windows. What it never had was an address."""
    fn = APP[APP.index("function openPlayerRoute(slug)"):]
    fn = fn[:fn.index("\n}")]
    assert "state.search = name" in fn
    assert 'switchView("players")' in fn


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
