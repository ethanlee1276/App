"""The Prediction Market page, to Ethan's three renders (2026-09-26: "here
is 3 renders for the 3 different page we have for the prediction pages.
match these renders for all 3 pages.")

One shell for the three rooms: the hero (eyebrow, the title with its gold
second word, the venues' cards), the room pills, the room, and a rail of
the live flow and the venues on Board and Flow; "Does it work?" runs full
width. Flow gets the render's league chips and sort; the proof room its
callout, badge tiles and banded table.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_shell_wraps_the_three_rooms():
    i = APP.index("async function renderIntel()")
    fn = APP[i:APP.index("\n/* =====", i)]
    assert 'subtabbedHTML("intel"' in fn and "pmxHeroHTML()" in fn and "pmxRailHTML(d)" in fn
    assert "pmxBindRooms(host)" in fn and "bindSubtabs(host)" in fn
    hero = _fn("pmxHeroHTML")
    assert "Prediction <span>Market</span>" in hero and "img/predict/pm-hero@800.webp" in hero
    assert ".pmx-art { position: absolute; inset: 0 0 0 auto; width: 64%;" in CSS and "mask-image: var(--grad-pmx-art);" in CSS, "the banner is the hero's right side, faded into it"
    # "we should make this a little smaller" (2026-09-26): a band, not a poster
    assert "min-height: clamp(150px, 14vw, 200px); align-items: center; }" in CSS
    assert "clamp(120px, 18vw, 238px)" not in CSS
    assert "pmxDoor(\"kalshi\"" in _fn("pmxRailHTML"), "the venues' doors are in the rail's market tools"
    assert "EXTERNAL_MARKET_LINKS" in _fn("pmxDoor"), "venue doors go through the review switch"
    assert '.pmx[data-tab="proof"] .pmx-rail' in CSS, "the proof room runs full width"
    # the sticky rail scrolls on its own rather than waiting for the page's end
    assert ".pmx-rail { max-height: calc(100vh - 100px); overflow-y: auto; overscroll-behavior: contain;" in CSS
    # and it fades at its foot while more is below, rather than cutting a card into a black bar
    assert ".pmx-rail.more-below { -webkit-mask-image: var(--grad-rail-fade); mask-image: var(--grad-rail-fade); }" in CSS
    assert 'pmxRailFade(host.querySelector(".pmx-rail"));' in APP
    assert "max-height: none; overflow: visible; }" in CSS, "stacked under the page, it is just part of it"


def test_flow_has_league_chips_and_a_sort():
    flow = _fn("pmxFlowHTML")
    assert 'data-act="pmFlowLeague"' in flow and 'data-change="pmFlowSort"' in flow
    assert "pmFlowLeague: (el, a) => window._pmFlowLeague(a)," in APP
    assert "pmFlowSort: (el) => window._pmFlowSort(el.value)," in APP
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    prog = _fn("pmFlowLeague") + """
      const cases = [{slug: "nfl-buf-kc-2026-09-28"}, {slug: "ncaaf-osu-mich-2026-11-28"},
        {slug: "fed-oct", market: "Will the Fed cut?"}, {slug: "x", market: "UFC Fight Night: A vs. B"},
        {slug: "y", market: "Who wins the World Series?"}, {slug: "z", market: "Super Bowl champion"}];
      console.log(JSON.stringify(cases.map(pmFlowLeague)));"""
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30, check=True).stdout
    assert json.loads(out) == ["nfl", "cfb", "other", "ufc", "mlb", "nfl"]


def test_the_card_line_is_our_own_tape_or_nothing():
    spark = _fn("pmxFlowSpark")
    assert "m.tape" in spark and "pts.length < 2" in spark, "no tape, no line"
    card = _fn("pmxFlowCardHTML")
    assert "tracked, not recommended" in card and "recommended (signal proven — 0.1u)" in card


def test_the_rail_is_polymarket_flow_and_the_doors():
    rail = _fn("pmxRailHTML")
    assert "· Polymarket" in rail and "Kalshi" not in rail.split("pmx-tools")[0].replace("Kalshi publishes", ""), \
        "the live flow is Polymarket's alone"
    assert 'data-act="pmxRoom" data-arg="flow"' in rail and 'data-act="pmxRoom" data-arg="proof"' in rail


def test_the_proof_room_wears_the_render():
    assert 'class="card pmx-verdict' in _fn("intelVerdict")
    card = _fn("intelReportCard")
    assert "pmxBadgeTile(" in card and "pm-band-head" in card and "Flag report card" in card


def test_the_prediction_page_shows_no_league_chrome():
    """Ethan, 2026-09-27: "We should not be showing this stuff on the
    prediction page" — the sports slate's stale bar and the league row."""
    assert 'const OFF_LEAGUE_VIEWS = ["intel", "memes"];' in APP
    assert 'document.body.classList.toggle("off-league", OFF_LEAGUE_VIEWS.includes(name));' in APP
    assert "body.off-league .sportbar { display: none; }" in CSS
    i = APP.index("function renderStaleBar(")
    bar = APP[i:APP.index("\n}\n", i)]
    off = bar.index("OFF_LEAGUE_VIEWS.includes(state.view)")
    assert bar.index("wireDown()") < off, "a connection failure still shows everywhere"
    assert off < bar.index("slateNotice(state.data)") < bar.index("withholdAfterMs()"), \
        "the slate's demo, stale and withheld bars never reach a page off the league"
    i = APP.index("function updateAgo(")
    assert 'OFF_LEAGUE_VIEWS.includes(state.view) ? "hidden" : ""' in APP[i:i + 900], "nor does the slate's age chip"


def test_the_board_stacks_on_a_phone_instead_of_squeezing():
    """Ethan, 2026-09-27, on the phone board: "is all squished and very
    ugly". `.pmx .pm-layout`'s two columns outranked the board's own
    stacking rule, and the phone row placed its model % in a grid area the
    template did not have."""
    i = CSS.index(".pmx .pm-layout { grid-template-columns: minmax(0, 1fr) minmax(240px, 300px); }")
    tail = CSS[i:]
    assert "@media (max-width: 1100px) {\n  .pmx .pm-layout { grid-template-columns: minmax(0, 1fr); }" in tail
    assert ".pmx .pm-detail:has(.pm-d-empty) { display: none; }" in tail
    areas = re.search(r'\.pmx \.pm-table \.kx-row \{[^}]*grid-template-areas: ([^;]*);', tail).group(1)
    for area in ("sport", "title", "view", "k", "n", "m", "e", "meter"):
        assert re.search(rf'(?<![\w-]){area}(?![\w-])', areas), f"{area} has a place in the phone row"
    for k, word in (("k", "YES"), ("n", "NO"), ("m", "OURS"), ("e", "GAP")):
        assert f'.pmx .pm-table .kx-{k}::before {{ content: "{word}"; }}' in tail


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
