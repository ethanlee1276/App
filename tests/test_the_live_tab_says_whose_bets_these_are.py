"""The Live tab's bets belong to the league its games belong to.

Ethan, 2026-09-18, with the Lions game on: "we have a live nfl game
right now and it's not showing any live edge or most likely bets in the
live tab. Instead, it's showing mlb bets."

Nothing was stale, mis-filed or mis-queried. THE TAB HAD TWO LEAGUE
SELECTORS AND ONLY ONE OF THEM MOVED THE PAGE. The chip row above the
game cards set `_liveChip`, which filters those cards and is read by
nothing else; the bets below — the open-bet panels, the Most Likely
panel, the Pick of the Day frame, the sweat zone — all read
`state.data`, which is the board the SPORTBAR button loaded. Tapping
NFL drew the Lions over a list of baseball bets, and every panel was
faithfully reporting a league the reader had just left.

The coupling already ran the other way (`_liveChipSport` makes the chip
follow the sport button), so it was a control that could only ever be
half-obeyed. Two things keep it fixed, and this file holds both:

  1. A league chip switches the LEAGUE, through the sportbar button
     rather than a second copy of the switch.
  2. Every bets panel prints the league it is speaking for. "All" is a
     real state that cannot be satisfied — one board loads at a time —
     so the label is what makes it legible rather than wrong-looking,
     and it is what stops the next bug of this shape from being silent.

THESE RUN THE RENDERERS. A grep for "leagueTag" is satisfied by a
variable that is defined and never interpolated, which is precisely the
dead-guard shape this repo keeps finding in its own work.

Run directly: `python3 tests/test_the_live_tab_says_whose_bets_these_are.py`
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    """One top-level function, `async` prefix included."""
    i = APP.index(f"function {name}(")
    if APP[max(0, i - 6):i] == "async ":
        i -= 6
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def _node(js):
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- the chip is a league switch --------------------------------------------
def tap_chip(chip, sport="mlb", bar=("mlb", "nfl", "cfb")):
    """Draw the Live board on `sport`, then tap `chip`.

    Returns what the tap did: which sportbar buttons it clicked, where
    `state.sport` and the two chip variables ended up, and how many
    times the board redrew itself locally.
    """
    js = f"""
    const state = {{ sport: {json.dumps(sport)}, view: "live", data: {{}} }};
    const LIVE_FEEDS = {{ mlb: "m.json", nfl: "n.json", cfb: "c.json" }};
    const LEAGUE_LABEL = {{ mlb: "MLB", nfl: "NFL", cfb: "CFB" }};
    const SPORT_META = {{ mlb: {{ logo: "" }}, nfl: {{ logo: "" }}, cfb: {{ logo: "" }} }};
    const SPORT_CODES = ["mlb", "nfl", "cfb", "nba", "wnba"];
    let _liveChip = "all", _liveChipSport = null, _liveFeedState = {{}};
    {_fn("escapeHtml")}
    const icon = () => "";
    const liveFeedWhyHTML = () => "";
    const liveCardHTML = () => "<div class='lb-card'></div>";
    // One game per league, so every chip exists and the reader is
    // looking at a genuinely mixed slate.
    const GAMES = [
      {{ sport: "mlb", g: {{ home: "NYY", away: "BOS" }} }},
      {{ sport: "nfl", g: {{ home: "BUF", away: "DET" }} }},
      {{ sport: "cfb", g: {{ home: "OSU", away: "MICH" }} }},
    ];
    async function fetchAllLive() {{ return GAMES; }}
    async function pressureWarm() {{}}
    function renderSweatZone() {{}}
    const betsDrawnFor = [];
    function renderLivePicks() {{ betsDrawnFor.push(state.sport); }}

    const mkChip = (code) => {{
      const h = [];
      return {{ dataset: {{ chip: code }}, _h: h,
               addEventListener: (_ev, fn) => h.push(fn),
               click: () => h.forEach((fn) => fn()) }};
    }};
    let chips = [];
    let redraws = 0;
    const host = {{ innerHTML: "",
      querySelectorAll: (sel) => (sel === ".lb-chip" ? chips : []) }};

    // The sportbar. Its button is the real switcher, so the stub does
    // what the real handler does: move state.sport and reload, which on
    // the live tab redraws the board and the bets.
    const clicked = [];
    const bar = {json.dumps(list(bar))};
    const sportBtn = (code) => bar.includes(code) ? {{
      click: () => {{ clicked.push(code); state.sport = code;
                     renderLivePicks(); renderLiveBoard(); }} }} : null;
    const document = {{
      getElementById: (id) => (id === "live-board" ? host : null),
      querySelector: (sel) => {{
        const m = /data-sport="([a-z]+)"/.exec(sel);
        return m ? sportBtn(m[1]) : null;
      }} }};

    {_fn("renderLiveBoard")}
    const _real = renderLiveBoard;
    async function _wrapped() {{
      redraws += 1;
      chips = ["all", "mlb", "nfl", "cfb"].map(mkChip);
      return _real();
    }}
    // Count redraws without changing what the source does: the wrapper
    // stands in only for the recursive call the chip handler makes.
    globalThis.renderLiveBoard = _wrapped;
    _wrapped().then(() => {{
      chips.find((c) => c.dataset.chip === {json.dumps(chip)}).click();
      return new Promise((r) => setTimeout(r, 0));
    }}).then(() => console.log(JSON.stringify({{
      clicked, sport: state.sport, chip: _liveChip,
      chipSport: _liveChipSport, redraws, betsDrawnFor }})));
    """
    return _node(js)


def test_tapping_a_league_chip_moves_the_whole_tab_not_half_of_it():
    """The bug, in one assertion. On MLB, tapping NFL used to leave
    state.sport on baseball — which is what every bets panel reads."""
    r = tap_chip("nfl", sport="mlb")
    assert r["clicked"] == ["nfl"], (
        "the chip did not go through the sportbar button, so the league "
        f"never changed: {r}")
    assert r["sport"] == "nfl", (
        "the games moved to the NFL and the bets stayed on baseball — "
        f"this is Ethan's screenshot: {r}")


def test_the_bets_are_redrawn_for_the_league_that_was_chosen():
    """Switching without redrawing the bets is the same failure one
    frame later."""
    r = tap_chip("nfl", sport="mlb")
    assert "nfl" in r["betsDrawnFor"], (
        f"the bets panels were never redrawn for the new league: {r}")


def test_the_chip_still_lands_on_the_league_that_was_tapped():
    """The follow rule (`_liveChipSport`) re-derives the chip from
    state.sport on every draw. If the switch and the rule disagree the
    chip springs back and the tap looks broken."""
    r = tap_chip("nfl", sport="mlb")
    assert r["chip"] == "nfl", f"the chip sprang back: {r}"
    assert r["chipSport"] == "nfl", (
        f"the chip's remembered league was left behind: {r}")


def test_all_stays_a_filter_and_changes_no_league():
    """Bets cannot be all-league — one board is loaded at a time — so
    'All' must not pretend to switch. It filters the cards and leaves
    the reader where they were."""
    r = tap_chip("all", sport="mlb")
    assert r["clicked"] == [], f"'All' switched the league: {r}"
    assert r["sport"] == "mlb", f"'All' moved the board: {r}"
    assert r["chip"] == "all", r


def test_tapping_the_league_you_are_already_on_does_not_reload_it():
    """A no-op tap that reloads an 8MB board is a tap that makes the
    page stutter for nothing."""
    r = tap_chip("mlb", sport="mlb")
    assert r["clicked"] == [], f"re-tapping the current league reloaded it: {r}"
    assert r["sport"] == "mlb", r


def test_a_league_with_no_button_in_the_bar_still_filters_the_cards():
    """The nav setting can hide a league's button. Falling through to
    the old behaviour beats doing nothing at all."""
    r = tap_chip("nfl", sport="mlb", bar=("mlb", "cfb"))
    assert r["clicked"] == [], r
    assert r["chip"] == "nfl", (
        f"the cards were not filtered either, so the tap did nothing: {r}")


# --- every bets panel names its league --------------------------------------
def draw_bets(sport="nfl", rows=(), potd=(), elsewhere=0):
    """`renderLivePicks` in node against the real source."""
    data = {"live_picks": list(rows), "live_potd": list(potd),
            "open_elsewhere": elsewhere, "long_shots": [], "games": []}
    js = f"""
    const state = {{ sport: {json.dumps(sport)}, view: "live",
                    data: {json.dumps(data)} }};
    const LEAGUE_LABEL = {{ mlb: "MLB", nfl: "NFL", cfb: "CFB" }};
    {_fn("escapeHtml")}
    {_fn("emptySlate")}
    const icon = () => "";
    const iconMark = () => "";
    const american = (o) => String(o);
    const teamName = (t) => String(t || "");
    const betMark = () => "";
    const ridingAttrs = () => "";
    const placedStamp = () => "";
    const gameLine = () => "";
    const situationLine = () => "";
    const progressBar = () => "";
    const winProb = () => "";
    const marketWord = (m) => String(m);
    const pluralWord = (n, w) => (n === 1 ? w : w + "s");
    const plural = (n, w) => `${{n}} ${{n === 1 ? w : w + "s"}}`;
    const whenLabel = () => "today";
    const buzzOnSettle = () => {{}};
    const liveTrackerRows = (r) => r;
    const tonightSignals = () => ({{ props: [], sharpBets: [], modelBets: [] }});
    const _els = {{ "live-picks": {{ innerHTML: "" }} }};
    const document = {{ getElementById: (id) => _els[id] || null }};
    {_fn("trackerBetText")}
    {_fn("isLikelyBook")}
    {_fn("renderLivePicks")}
    renderLivePicks();
    console.log(JSON.stringify(_els["live-picks"].innerHTML));
    """
    return _node(js)


ROW = {"player": "Josh Allen", "market": "pass_yds", "market_label": "Pass Yds",
       "side": "OVER", "line": 240.5, "odds": -115, "stake_units": 1.0,
       "phase": "live", "status": "tracking", "category": "main",
       "game": {"home": "BUF", "away": "DET"}}
LIKELY = dict(ROW, category="likely", player="Amon-Ra St. Brown")


def test_an_empty_tab_says_which_league_is_empty():
    """"No open bets on today's card" was true of a league the reader
    could not name. It is the sentence Ethan read while holding an NFL
    game and a baseball board."""
    html = draw_bets("nfl")
    assert "NFL" in html, (
        "the empty tab does not say which league it is empty for:\n" + html)


def test_every_panel_carries_the_league_it_is_speaking_for():
    html = draw_bets("nfl", rows=[ROW, LIKELY])
    # Three headers — edge, Most Likely, and the tag itself must be in
    # the markup rather than only in the prose.
    assert html.count("lb-of-league") >= 2, (
        "a bets panel is drawn with no league on it:\n" + html)
    assert "NFL" in html, html


def test_the_pick_of_the_day_frame_names_its_league_too():
    """It is the one bet the page is named after and the one most likely
    to be read alone."""
    html = draw_bets("nfl", potd=[ROW])
    i = html.index("Pick of the Day")
    assert "lb-of-league" in html[i:i + 260], (
        "the Pick of the Day frame carries no league:\n" + html[i:i + 400])


def test_the_league_is_the_loaded_board_not_the_chip():
    """The chip can be 'all'; a board cannot. Reading the label off the
    chip would print 'ALL' over one league's bets, which is the original
    bug with a new coat of paint."""
    assert "_liveChip" not in _fn("renderLivePicks"), (
        "renderLivePicks reads the game-card filter — it must name the "
        "league whose BOARD is loaded, which is state.sport")
    html = draw_bets("mlb", rows=[ROW])
    assert "MLB" in html and ">NFL<" not in html, html


def test_an_empty_panel_names_the_league_as_well_as_a_full_one():
    """The empty line is the one that gets read on the night this went
    wrong — a reader with no rows has nothing else to go on."""
    html = draw_bets("cfb", rows=[ROW])     # edge only, Most Likely empty
    assert "No open CFB Most Likely bets" in html, html


def test_a_league_with_no_label_falls_back_to_its_code():
    """WNBA and the rest are in LEAGUE_LABEL; a league that is not must
    still print something rather than 'undefined'."""
    html = draw_bets("xfl", rows=[ROW])
    assert "XFL" in html, html
    assert "undefined" not in html, html


def test_the_tag_has_a_style_to_render_with():
    """An unstyled span inherits the section title's uppercase 800
    weight and reads as part of the heading — which is the one thing it
    must not do."""
    assert ".lb-of-league" in CSS, \
        "the league tag is drawn with no rule behind it"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
