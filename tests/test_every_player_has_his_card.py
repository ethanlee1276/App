"""Every league's chart leads with his card, the hit page's: his photo.

Ethan, 2026-10-14, beside the hit tracker's card (Teoscar Hernández at the
plate) and the carry chart's game header (no one in it): "why do baseball
players have cool ass photos of themselves but no one else does, fix
that". Pinned here:

  * EVERY CHART BUT THE HIT PAGE'S (which keeps its own) opens on his card
    (js/carrychart.js `playerHero`), under the switch on a pick page and
    over the game's own header: his club's mark and name, his photo, his
    name with his position and number, the season, and five numbers of his
    season, each league's own (football's in the frame, the rest from each
    module's `heroTiles`); a fighter has no club, so his record stands
    where its mark would;
  * THE PHOTO IS THE BEST HIS LEAGUE PUBLISHES: an action shot where it
    files one under his id (MLB's and the NHL's, built by engine/photos off
    the id in his headshot's address), else his cut-out headshot on his
    club's colour asked for at the card's size and then whole, and his
    initials under both — never a second round photo, which stepped the
    header's face list a second time and cost the header its photo (the
    face test's browser half caught it); each failure steps to the next,
    and once the list is spent his initials show;
  * THE BOX CHECK (photocheck.py) ASKS FOR WHAT THE CARD ASKS FOR, in the
    same order and at the same size as the page (visuals.js
    `facePreview`, run here beside its Python twin), and says which photo
    each league's cards draw;
  * A NAME NEVER BREAKS MID-WORD (the card read "HERNÁNDE / Z" and "WILLIA /
    MS"): every hero name carries its longest word's letters (`--nl`) and
    the size comes down with them;
  * BROWSER HALF, opt-in (`QB_BROWSER_TESTS=1`): a pick page's carry chart
    opens on his card with the cut-out on, a dead action shot steps to the
    cut-out, and no name on any card overflows its column at 360px.

Run directly: `python3 tests/test_every_player_has_his_card.py`
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

from engine import charts as CH, photos                          # noqa: E402

WEB = ROOT / "web"
CC_JS = (WEB / "js" / "carrychart.js").read_text(encoding="utf-8")
CC_CSS = (WEB / "css" / "carrychart.css").read_text(encoding="utf-8")
MODS = {f: (WEB / "js" / f"chart-{f}.js").read_text(encoding="utf-8")
        for f in ("hoops", "mlb", "nhl", "kicks", "role", "ufc", "matchup")}

NHL_FACE = "https://assets.nhle.com/mugs/nhl/20252026/EDM/8478402.png"
MLB_FACE = "https://img.mlbstatic.com/mlb-photos/image/upload/w_180,q_auto/v1/people/660271/headshot/67/current"
ESPN_FACE = "https://a.espncdn.com/i/headshots/nfl/players/full/4430737.png"


def _carries(face="", action=""):
    line = {"n": 16, "yds": 53, "ypc": 3.3, "td": 1, "long": 12, "first": 3}
    game = {"id": "g5", "week": 5, "date": "2026-10-12", "opp": "BUF", "home": True, "team": "LA", "score": [34, 37],
            "line": line, "carries": [{"q": 1, "clk": "10:00", "dn": 1, "ds": 10, "yl": 60, "y": 4, "h": "LG",
                                       "sc": False, "td": False, "fl": False, "fd": False, "band": "short"}]}
    return {"player": "Kyren Williams", "sport": "nfl", "holes": True, "seasons": [2026, 2025], "season": 2026,
            "team": "LA", "position": "RB", "jersey": "23", "games": [game, dict(game, id="g4", week=4)],
            "season_line": {"n": 70, "yds": 288.4, "ypc": 4.12, "td": 3, "long": 22, "first": 14},
            "bands": {}, "by_hole": [], "by_zone": [], "by_down": [], "kinds": {}, "ngs": {},
            "face": face, "action": action}


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const teamMarkIn = (lg, a, px) => `<i class="mark" data-px="${px}">${a}</i>`, teamNameIn = (lg, a) => a, lockScroll = () => {};
      const TEAMS = { LA: { name: "Los Angeles Rams", nick: "Rams", loc: "Los Angeles", primary: "#003594" },
                      EDM: { name: "Edmonton Oilers", nick: "Oilers", loc: "Edmonton", primary: "#041e42" } };
      const teamsIn = () => TEAMS;
      const venuePhotoTag = (sport, home) => `<img class="venue-photo" data-home="${home}">`;
      const facePreview = (u, px) => `${u}?w=${px * 2}`;
      const window = {};
    """
    prog = (f"{stubs}\n{CC_JS}\n" + "\n".join(MODS.values())
            + f"\nconsole.log(JSON.stringify((() => {{ const T = window.QBCarry._t; {js} }})()));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink()
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_football_card_is_the_hit_pages_with_his_cut_out_on_his_colour():
    got = _node(f"""
      const cut = T.playerHero({json.dumps(_carries(ESPN_FACE))}, "nfl", "carries");
      const act = T.playerHero({json.dumps(_carries(ESPN_FACE, "https://x/action.jpg"))}, "nfl", "carries");
      const none = T.playerHero({json.dumps(_carries())}, "nfl", "carries");
      return {{ cut, act, none }};""")
    if got is None:
        print("      (skipped: no node)")
        return
    c = got["cut"]
    for want in ('class="cc-hero mb-hero ph-hero"', "--ta:#003594", 'data-home="LA"', "2026 season",
                 ">Los Angeles<", '<b style="--nl:4">Rams</b>', "<small>Kyren</small>", '<b style="--nl:8">Williams</b>',
                 "RB  #23", 'style="--n:5"'):
        assert want in c, want
    tiles = re.findall(r'<div class="mb-ht"><b>(.*?)</b><span>(.*?)</span></div>', c)
    assert tiles == [("2", "Games"), ("70", "Carries"), ("288", "Yards"), ("4.1", "YPC"), ("3", "TD")], tiles
    # His cut-out, on his colour with his club's mark behind him, at the card's size first.
    assert 'class="cc-act cut" data-ph>' in c and '<span class="ph-mark" aria-hidden="true"><i class="mark" data-px="96">LA</i>' in c
    assert f'src="{ESPN_FACE}?w=320"' in c, "asked for at the card's size"
    assert c.index("cc-act") < c.index('class="cc-face'), "his initials under the photo"
    face = lambda h: h[h.index('<div class="mb-hero-face">'):h.index('<div class="mb-hero-who">')]  # noqa: E731
    assert face(c).count("<img") == 1, "under the photo his initials, never a second photo"
    # An action shot leads where there is one; no photo at all leaves his initials.
    assert 'class="cc-act" data-ph>' in got["act"] and 'src="https://x/action.jpg"' in got["act"]
    assert "cc-act" not in got["none"] and ">KW<" in got["none"] and "<img" not in face(got["none"])


def test_every_leagues_card_has_its_own_five():
    got = _node("""
      const D = T.DRAW;
      return {
        hoops: D.shots.heroTiles({ season_line: { games: 12, ppg: 27.25, fg_pct: 0.582, fg3_pct: 0.351, ft_pct: 0.81 } }),
        skater: D.shotmap.heroTiles({ season_line: { games: 30, goals: 14, sog_pg: 3.42, sh_pct: 0.137, ixg: 11.6 } }),
        goalie: D.saves.heroTiles({ season_line: { games: 20, sv_pct: 0.9134, ga: 48, gsax: 6.24, shots_pg: 28.9 } }),
        kicks: D.kicks.heroTiles({ season_line: { fg_pct: 0.9, fgm: 18, fga: 20, long: 56, fg50: 3, fga50: 4, xp_pct: 1 } }),
        fights: D.fights.heroTiles({ season_line: { n: 6, w: 4, l: 1, d: 1, ko_w: 2, sub_w: 0 } }),
        side: D.fights.heroSide({ season_line: { n: 6, w: 4, l: 1, d: 1 } }),
        role: D.role.heroTiles({ sport: "nfl", lead: "snap_share", season_line: { games: 5, avg: { snap_share: 0.71 },
          last3: { snap_share: 0.78 }, last5: { snap_share: 0.71 }, high: { snap_share: 0.9 }, low: {} },
          metrics: [{ key: "snap_share", name: "Snap share", short: "Snaps", unit: "pct" }] }),
        football: [T.heroTiles("routes", { games: [1, 2, 3], season_line: { tgt: 27, rec: 19, yds: 221.6, td: 2 } }),
                   T.heroTiles("passes", { games: [1], season_line: { cmp: 22, att: 31, yds: 268, td: 2, int: 1 } })],
      };""")
    if got is None:
        return
    assert got["hoops"] == [["Games", 12], ["PPG", "27.3"], ["FG%", "58%"], ["3PT%", "35%"], ["FT%", "81%"]], got["hoops"]
    assert got["skater"] == [["Games", 30], ["Goals", 14], ["SOG/gm", "3.4"], ["SH%", "14%"], ["xG", "11.6"]], got["skater"]
    assert got["goalie"] == [["Games", 20], ["SV%", ".913"], ["GA", 48], ["GSAx", "+6.2"], ["Shots/gm", "28.9"]], got["goalie"]
    assert got["kicks"] == [["FG%", "90%"], ["FG", "18/20"], ["Long", 56], ["50+", "3/4"], ["XP%", "100%"]], got["kicks"]
    assert got["fights"] == [["Fights", 6], ["KO/TKO", 2], ["Subs", 0], ["Decisions", 2]], got["fights"]
    assert "<small>Record</small>" in got["side"] and ">4-1-1</b>" in got["side"], "his record where a club's mark would be"
    assert [k for k, _v in got["role"]] == ["Games", "Snaps", "Last 3", "Last 5", "High"], got["role"]
    assert got["football"][0] == [["Games", 3], ["Targets", 27], ["Rec", 19], ["Yards", 222], ["TD", 2]]
    assert got["football"][1] == [["Games", 1], ["Cmp/Att", "22/31"], ["Yards", 268], ["TD", 2], ["INT", 1]]


def test_the_photo_steps_from_the_action_shot_to_the_cut_out_to_his_face():
    got = _node(f"""
      const st = {{}};
      T.heroPhoto({json.dumps(_carries(ESPN_FACE, "https://x/action.jpg"))}, "nfl", st);
      const act = {{ dataset: {{ ph: "" }}, cls: new Set(["cc-act"]), gone: false,
                    classList: {{ add(c) {{ act.cls.add(c); }}, toggle(c, on) {{ on ? act.cls.add(c) : act.cls.delete(c); }} }},
                    remove() {{ act.gone = true; }} }};
      const img = {{ tagName: "IMG", src: "https://x/action.jpg", closest: (q) => (q === ".cc-act" ? act : null) }};
      const seen = [];
      T.faceStep("error", img, st); seen.push([img.src, act.cls.has("cut")]);
      T.faceStep("error", img, st); seen.push([img.src, act.cls.has("cut")]);
      T.faceStep("load", img, st); const loaded = [st.ph.ok, act.cls.has("on")];
      const st2 = {{}};
      T.heroPhoto({json.dumps(_carries(ESPN_FACE))}, "nfl", st2);
      T.faceStep("error", img, st2); T.faceStep("error", img, st2);
      return {{ list: st.ph.list, seen, loaded, spent: [st2.ph.ok, act.gone],
               redraw: T.heroPhoto({json.dumps(_carries(ESPN_FACE))}, "nfl", st2) }};""")
    if got is None:
        return
    assert got["list"] == [{"u": "https://x/action.jpg", "cut": False}, {"u": ESPN_FACE + "?w=320", "cut": True},
                           {"u": ESPN_FACE, "cut": True}]
    assert got["seen"] == [[ESPN_FACE + "?w=320", True], [ESPN_FACE, True]], "the action shot, then his cut-out"
    assert got["loaded"] == [True, True]
    assert got["spent"] == [False, True], "the list spent: his initials show"
    assert "cc-act" not in got["redraw"] and "cc-face" in got["redraw"], "a redraw does not ask again"


def test_a_name_is_sized_by_its_longest_word_never_broken():
    got = _node("""return [T.nameLen("St. Brown"), T.nameLen("Hernández"), T.nameLen("Ty"), T.nameLen("")];""")
    if got is None:
        return
    assert got == [5, 9, 4, 4], got
    for sel in (".mb-hero-who b", ".cc-hero-name b"):
        rule = CC_CSS[CC_CSS.index(sel + " {"):]
        rule = rule[:rule.index("}")]
        assert "var(--nl" in rule and "overflow-wrap: normal" in rule, sel
    assert ".cc-hero { position: relative;" in CC_CSS and "container-type: inline-size; }" in CC_CSS
    assert '<b style="--nl:${Q.h.nameLen(last)}">' in MODS["mlb"] and '<b style="--nl:${Q.h.nameLen(nick)}">' in MODS["mlb"]
    assert '<b style="--nl:${Q.h.nameLen(lastName)}">' in MODS["ufc"]


def test_every_chart_but_the_hit_page_leads_with_the_card():
    i = CC_JS.index("  function render() {")
    body = CC_JS[i:CC_JS.index("\n  function settle(box)", i)]
    assert "const card = playerHero(d, sport, S.kind);" in body
    assert "(C.inline ? barRow + card + hero : head + card + hero + barRow)" in body
    assert body.index("if (P && P.page) {") < body.index("const card = playerHero("), "the hit page keeps its own"
    for sel in (".mb-hero-face .cc-act.cut {", ".mb-hero-face .cc-act.cut .ph-mark {", "repeat(var(--n, 5), minmax(0, 1fr))"):
        assert sel in CC_CSS, sel
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CC_CSS), "tokens only"
    for f, src in MODS.items():
        assert "onclick" not in src and "onerror" not in src and not re.search(r"on(error|load)\s*=", src), f


def test_the_action_shot_is_built_off_the_id_in_his_headshot():
    assert photos.action_url("nhl", NHL_FACE) == "https://assets.nhle.com/mugs/actionshots/1296x729/8478402.jpg"
    assert photos.action_url("mlb", MLB_FACE) == \
        "https://img.mlbstatic.com/mlb-photos/image/upload/w_480,q_auto:best/v1/people/660271/action/hero/current"
    for sport, face in (("nfl", ESPN_FACE), ("nba", ESPN_FACE), ("cfb", ESPN_FACE), ("ufc", ESPN_FACE),
                        ("nhl", ""), ("nhl", "https://example.com/8478402.png"), ("mlb", "")):
        assert photos.action_url(sport, face) == "", (sport, face)


def test_every_chart_answer_carries_his_action_shot():
    from engine import statlogs
    old_face, old_kinds = statlogs.face, dict(CH.KINDS)
    statlogs.face = lambda conn, sport, player: NHL_FACE if sport == "nhl" else ""
    CH.KINDS["probe"] = (("nhl", "nfl"), lambda conn, sport, player, season: {"player": player, "position": "C", "jersey": "97"},
                         lambda conn, sport: True)
    try:
        nhl = CH.answer(None, "probe", "nhl", "Connor McDavid")
        nfl = CH.answer(None, "probe", "nfl", "Kyren Williams")
    finally:
        statlogs.face = old_face
        CH.KINDS.clear()
        CH.KINDS.update(old_kinds)
    assert nhl["face"] == NHL_FACE and nhl["action"] == "https://assets.nhle.com/mugs/actionshots/1296x729/8478402.jpg"
    assert nfl["action"] == "", "a league with no action shot sends none"


def test_the_box_check_sizes_a_photo_the_way_the_page_does():
    import photocheck as PC
    nfl = "https://static.www.nfl.com/image/upload/f_auto,q_auto/league/gainwell"
    nba = "https://cdn.nba.com/headshots/nba/latest/260x190/2544.png"
    urls = [nfl, MLB_FACE, ESPN_FACE, nba, NHL_FACE, ""]
    mine = [PC.face_preview(u, PC.CARD_PX) for u in urls]
    assert mine[0] == "https://static.www.nfl.com/image/upload/f_auto,q_auto,w_320/league/gainwell", mine[0]
    # In the photo's own shape since 2026-10-28: asked for a square, ESPN's
    # combiner stretched the face to it (tests/test_no_face_is_stretched.py).
    assert mine[2] == "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430737.png&w=438&h=320"
    assert mine[3] == nba and mine[4] == NHL_FACE and mine[5] == ""
    assert "facePreview(full, 160)" in CC_JS, "the card's size, as the page asks for it"
    node = shutil.which("node")
    if not node:
        print("      (skipped the page's half: no node)")
        return
    vis = (WEB / "js" / "visuals.js").read_text(encoding="utf-8")
    part = vis[vis.index("const FACE_TRANSFORM = "):vis.index("function playerAvatar(")]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(part + f"\nconsole.log(JSON.stringify({json.dumps(urls)}.map((u) => facePreview(u, 160))));")
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink()
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == mine, (json.loads(out.stdout), mine)


def test_the_box_check_asks_for_his_card_in_order_and_says_what_it_draws():
    import photocheck as PC
    from engine import db
    conn = db.connect(":memory:")
    for g in ("1", "2", "3"):
        conn.execute("INSERT INTO player_game_logs VALUES ('nhl', 2026, '2026-10-0' || ?, ?, 'Connor McDavid', 'EDM', "
                     "'CGY', 'C', 1, 'points', 2)", (g, g))
    conn.execute("INSERT INTO player_game_logs VALUES ('nhl', 2026, '2026-10-01', '1', 'No Face', 'EDM', 'CGY', 'C', 1, "
                 "'points', 0)")
    conn.execute("INSERT INTO player_assets VALUES ('nhl', 'Connor McDavid', '', ?, '2026-10-03')", (NHL_FACE,))
    conn.execute("INSERT INTO ufc_fights (fighter, fighter_id, comp_id, date) VALUES ('Alex Pereira', '4705658', 'c1', "
                 "'2026-10-04')")
    asked = []

    def get(url):
        asked.append(url)
        return ("actionshots" not in url, "200 image/png 9 b")
    lines = PC.report(conn, ("nhl", "ufc", "wnba"), get=get)
    action = "https://assets.nhle.com/mugs/actionshots/1296x729/8478402.jpg"
    fighter = "https://a.espncdn.com/i/headshots/mma/players/full/4705658.png"
    assert asked == [action, NHL_FACE, PC.face_preview(fighter, 160), fighter], asked
    text = "\n".join(lines)
    assert "Connor McDavid" in text and "No Face" not in text, "only a regular with a face"
    assert "→ the cards draw: whole for 1 of 1" in text, "the action shot missing, his headshot"
    assert "→ the cards draw: card size for 1 of 1" in text, "the fighter's at the card's size"
    assert "WNBA\n   no regular with a face on file: every card draws his initials" in text
    asked.clear()
    lines = PC.report(conn, ("nhl",), get=lambda u: (asked.append(u) or (True, "200 image/jpeg 1 b")))
    assert asked == [action, NHL_FACE] and "→ the cards draw: action for 1 of 1" in "\n".join(lines)
    src = (ROOT / "photocheck.py").read_text(encoding="utf-8")
    assert "mode=ro" in src and "INSERT" not in src and "UPDATE " not in src, "reads, never writes"


# --- the browser, opt-in --------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div id="host" style="width:360px"></div>
<script>
  const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const teamMarkIn = () => "", teamNameIn = (lg, a) => a, lockScroll = () => {{}};
  window.fetch = async (q) => ({{ ok: true, json: async () => (q.includes("/carries") ? window.CHART : {{}}) }});
</script>
<script>{js}</script></body></html>"""
PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def test_in_a_browser_the_card_draws_steps_and_never_overflows():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
        if os.path.exists(chromium):
            kw["executable_path"] = chromium
        browser = pw.chromium.launch(**kw)
        try:
            for action in ("", "data:image/png;base64,bm90IGFuIGltYWdl"):
                page = browser.new_page(viewport={"width": 390, "height": 900})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.set_content(PAGE.format(css=CC_CSS, js=CC_JS))
                d = _carries(PNG, action)
                d["player"] = "Christian Hernández-Williamson"
                page.evaluate("(c) => { window.CHART = c; document.getElementById('host').innerHTML ="
                              " '<div class=\"cc-slot\" data-cc=\"x\" data-lg=\"nfl\" data-mkt=\"rush_yds\" data-pos=\"RB\"></div>';"
                              " window.QBCarry.mount(document.querySelector('.cc-slot')); }", d)
                page.wait_for_selector(".cc-slot .ph-hero .cc-act.cut.on", timeout=5000)
                assert page.evaluate("getComputedStyle(document.querySelector('.ph-hero .cc-face')).display") == "none"
                assert page.evaluate("document.querySelector('.ph-hero').compareDocumentPosition("
                                     "document.querySelector('.cc-hero:not(.ph-hero)')) & 4"), "his card over the game's"
                over = page.evaluate("""[...document.querySelectorAll('.mb-hero-who b, .cc-hero-name b')]
                    .filter((b) => b.scrollWidth > b.parentElement.clientWidth + 1).map((b) => b.textContent)""")
                assert not over, over
                assert page.evaluate("document.scrollingElement.scrollWidth") <= 390
                assert not errors, errors
                page.close()
        finally:
            browser.close()


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
