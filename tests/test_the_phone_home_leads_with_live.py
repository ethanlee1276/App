"""The home leads with the Pick of the Day, then what is live.

Ethan, 2026-09-22, choosing the home screen's job for the redesign:
"Live first." The Figma mock he approved orders the phone home Live now
→ Riding → Tonight's picks → The record → Zeno's picks. This pins that
order, the rules that keep every printed number an earned one, and the
one cost rule — the strip reads the fast scoreboards, never the boards.
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

HTML = (ROOT / "web" / "index.html").read_text()
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head)
            break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 1]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("HOME_DECK_ORDER")}
      {_const("HOME_DECK_ADOPTS")}
      {_fn("deckLiveGames")}
      {_fn("deckRidingRows")}
      {_fn("deckFirstWord")}
      {_fn("deckQuietLine")}
      {_fn("deckStateWord")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_deck_is_the_first_thing_on_the_home_view_and_adopts_the_board():
    """Home v2 (2026-09-22): the deck ARRANGES the home. It owns Live
    now, Riding, The record and Zeno's picks, and adopts the stadium
    strip, the Pick of the Day card, the Most Likely shelves, Best
    bets and the quick tools — same renderers, same information, the
    mock's order. Nothing folds: Ethan, on the folded version, "I don't
    like how you got rid of my stadiums and I don't like how I can't
    see the most likely to hit picks and edge picks on the main page."
    """
    view = HTML[HTML.index('id="view-recommended"'):]
    view = re.sub(r"<!--.*?-->", "", view, flags=re.S)
    first = re.search(r"<(div|section|p|h\d)\b[^>]*>", view[view.index(">") + 1:])
    assert first and 'id="home-deck"' in first.group(0), first.group(0) if first else None
    assert '<div id="home-deck" hidden></div>' in view
    got = _node("return HOME_DECK_ADOPTS;")
    if got is not None:
        assert list(got) == ["hero", "games", "likely", "edge", "tools"], got
        assert got["hero"] == ["potd-zone"], "the Pick of the Day is the hero (v4, the prototype's order)"
        assert got["games"] == ["games-head", "slate-horizon", "games-outer"], "the stadium strip, whole"
        assert got["likely"] == ["likely-top"] and got["edge"] == ["best-bets"] \
            and got["tools"] == ["quick-tools"]
        for ids in got.values():
            for z in ids:
                assert f'id="{z}"' in view, z
    adopt = _fn("deckAdopt")
    assert "if (el && el.parentElement !== s) s.appendChild(el);" in adopt, \
        "moved once; a redraw finds them already home"
    skel = _fn("deckSkeleton")
    assert "if (host.dataset.built) return;" in skel, "built once, so adopted zones survive a redraw"
    deck = _fn("renderHomeDeck")
    assert "deckSkeleton(host);" in deck and "deckAdopt(host);" in deck
    assert "isPhone()" not in deck, "the deck is the home at every width"
    for gone in ("home-folded", "hd-fold", "HOME_FOLD_KEY", "applyHomeFold"):
        assert gone not in APP and gone not in CSS, gone
    assert "qb.home.fold" not in (ROOT / "rendercheck.py").read_text()
    # Desktop: every section spans the row but The record and Zeno's picks; phone: one column.
    assert "#home-deck { display: grid; grid-template-columns: 1fr 1fr;" in CSS
    assert "#home-deck .hd-sec { grid-column: 1 / -1; min-width: 0; }" in CSS
    assert '#home-deck .hd-sec[data-sec="record"], #home-deck .hd-sec[data-sec="zeno"] { grid-column: auto; }' in CSS
    assert '#home-deck .hd-sec[data-sec="hero"]:not(:has(#potd-zone > *)),' in CSS \
        and '#home-deck .hd-sec[data-sec="likely"]:not(:has(#likely-top > *)),' in CSS, \
        "an adopted section with nothing drawn takes no room"
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert "#home-deck { display: block;" in phone
    home = _fn("renderRecommended")
    assert "renderHomeDeck();" in home[:300], "drawn before the zones below it"


def test_the_order_is_hero_live_riding_tonight_record_zeno():
    got = _node("return HOME_DECK_ORDER;")
    if got is None:
        print("  SKIP node not installed"); return
    # The picks before the games since the site audit, 2026-09-24 (Visual 1).
    assert got == ["hero", "live", "riding", "likely", "edge", "games", "record", "zeno", "tools"], got
    skel = _fn("deckSkeleton")
    assert "host.innerHTML = HOME_DECK_ORDER.map((k) =>" in skel
    assert '`<section class="hd-sec" data-sec="${k}" hidden></section>`' in skel
    fill = _fn("deckFill")
    assert "s.hidden = !html;" in fill, "an owned section with nothing to say is not drawn"
    deck = _fn("renderHomeDeck")
    for k in ("riding", "live", "record", "zeno"):
        assert f'deckFill(host, "{k}",' in deck, k


def test_live_games_only_ours_first_and_the_quiet_night_says_what_it_knows():
    got = _node("""
      const g = (a, h, st) => ({ away: a, home: h, live: { state: st } });
      const list = [{ sport: "nfl", g: g("KC", "LAC", "live") }, { sport: "mlb", g: g("NYY", "BOS", "final") },
                    { sport: "nfl", g: g("GB", "CHI", "live") }, { sport: "mlb", g: g("LAD", "SF", "live") },
                    { sport: "nfl", g: g("SEA", "SF", "scheduled") }];
      const riding = [{ phase: "live", game: { away: "GB", home: "CHI" } }, { phase: "live", game: { away: "GB", home: "CHI" } },
                      { phase: "live", game: { away: "LAD", home: "SF" } }];
      const live = deckLiveGames(list, riding, "nfl");
      const rows = deckRidingRows([{ phase: "live", a: 1 }, { phase: "upcoming" }, { phase: "final" }, { phase: "live", a: 2 }]);
      return { live: live.map((x) => [x.sport, x.g.away, x.riding]), rows: rows.map((r) => r.a),
               quietFull: deckQuietLine({ league: "MLB", sport: "mlb", first: "7:05 PM ET", queued: 3 }),
               quietOne: deckQuietLine({ league: "NFL", sport: "nfl", first: "", queued: 1 }),
               quietBare: deckQuietLine({ league: "NBA", sport: "nba", first: "", queued: 0 }),
               tip: deckFirstWord("wnba"), ufc: deckFirstWord("ufc"), cfb: deckFirstWord("cfb"),
               words: ["cleared", "won_pending", "busted", "lost_pending", "dead", "push_pending", "live", undefined]
                 .map((s) => deckStateWord({ status: s })) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["live"] == [["nfl", "GB", 2], ["nfl", "KC", 0]], \
        "the league you are on only: no baseball on the NFL page (Ethan, 2026-09-23)"
    assert got["rows"] == [1, 2]
    assert got["quietFull"] == "No MLB games live. First pitch 7:05 PM ET. 3 bets queued."
    assert got["quietOne"] == "No NFL games live. 1 bet queued."
    assert got["quietBare"] == "No NBA games live."
    assert got["tip"] == "Tip-off" and got["ufc"] == "First bout" and got["cfb"] == "Kickoff"
    assert got["words"] == [["Won", "good"], ["Won", "good"], ["Gone", "bad"], ["Gone", "bad"],
                            ["Gone", "bad"], ["Push", ""], ["Tracking", ""], ["Tracking", ""]]


def test_the_strip_reads_the_fast_scoreboards_never_the_boards():
    fast = _fn("fetchFastLiveAll")
    assert "Object.entries(LIVE_FAST)" in fast
    assert "LIVE_FEEDS" not in fast, "the boards are megabytes; the strip shows scores"
    assert 'boardFetch(url, { cache: "no-store" })' in fast
    live = _fn("deckLiveHTML")
    assert "await fetchFastLiveAll()" in live
    assert "deckLiveGames(fast, riding, state.sport)" in live
    assert 'filter((r) => r.phase === "upcoming").length' in live, "queued = journaled and not started"
    game = _fn("deckGameHTML")
    assert "liveHoldWord(lv)" in game and 'live-dot${hold ? " paused" : ""}' in game, \
        "a delayed game says so on the home too"
    arm = _fn("armDeckLive")
    assert "if (now !== _deckStamp) { renderHomeDeck({ still: true }); return; }" in arm, \
        "redraw only when a score moved, and in place (test_the_numbers_count_up_and_the_dot_pings)"


def test_every_printed_number_is_an_earned_one():
    # v5: the tiles come from recordRibbonsHTML, shared with the Record page
    rec = _fn("recordRibbonsHTML")
    assert "if (ov.settled) {" in rec and "if (zo.settled) {" in rec, "no tile over nothing"
    assert "ov = ov || {};" in rec and ".zeno || {}" in rec
    deck = _fn("deckRecordHTML")
    assert "recordRibbonsHTML(rec, rec.overall, rec.recent)" in deck
    assert "zenoTicketRow(r, false)" in deck, "Zeno's open tickets are the record page's own rows"
    assert "function deckTonightHTML(" not in APP, \
        "the deck adopts the board's Pick of the Day card and shelves; it does not redraw them thinner"
    row = _fn("deckPickRow")
    assert "isFinite(p) && p > 0 && p < 1" in row, "a certainty is not a forecast"
    riding = _fn("deckRidingHTML")
    assert "trackerBetText(r)" in riding, "the Live tab's sentence, not a second one"
    assert 'r.market !== "moneyline"' in riding, "a moneyline has no progress to show"


def test_the_picks_page_is_the_same_rows_with_doors():
    """Figma frame D: the Pick of the Day as a hero, then rows a thumb
    can scan — each one a door to the prop page — with the board's full
    cards under one fold rather than gone."""
    tonight = APP[APP.index("function renderTonight() {"):]
    tonight = _strip(tonight[:tonight.index("\nfunction ", 10)])
    assert "${potdHeroHTML(d)}" in tonight
    assert 'ml.map((r) => deckPickRow(r, { door: likelyOpen(r) }))' in tonight
    assert "door: propAttrs(r)" in tonight and 'small: "edge"' in tonight
    assert "r.has_market === false ? null" in tonight, "no edge printed over a pick with no price"
    assert tonight.index("potdHeroHTML") < tonight.index("Most likely to hit tonight") < tonight.index("Our edge bets")
    assert '<details class="tn-full"><summary>' in tonight and "props.map(cardHTML)" in tonight
    hero = _fn("potdHeroHTML")
    assert 'String(call) === "bet"' in hero
    assert 'return "";' in hero
    row = _fn("deckPickRow")
    assert 'const tag = door ? "button" : "div";' in row, "a row is a button exactly when it opens something"
    # The rows serve every width, so their styles live outside the phone block.
    phone_at = CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }"))
    for sel in (".hd-row {", ".hd-card {", ".hd-strip {", ".hd-ribbon {", ".hd-num {", ".hd-row.openable {", ".tn-full {"):
        assert sel in CSS[:phone_at], sel


def test_every_home_section_wears_the_decks_head_and_the_league_select_yields():
    """v4 (2026-09-22): the adopted zones' own titles were the old page's
    voice inside the new order. On the home they wear the deck's head;
    the sub-line keeps its words. And the games row's league select was
    the crest strip again, so the phone home hides it."""
    assert "#home-deck .section-title { display: block; margin: 0 0 10px; color: var(--text-dim);" in CSS
    i = CSS.index("#home-deck .section-title {")
    rule = CSS[i:CSS.index("}", i)]
    assert "text-transform: uppercase" in rule and "letter-spacing: .12em" in rule
    sub = CSS[CSS.index("#home-deck .section-title .sub {"):]
    sub = sub[:sub.index("}")]
    assert "display: block" in sub and "text-transform: none" in sub, "the sub-line is kept, one line down"
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert "#home-deck #games-sport { display: none; }" in phone
    wide = CSS[:CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }"))]
    assert "#games-sport { display: none" not in wide, "the desktop's Game Lines room keeps its select"


def test_the_pick_of_the_day_is_the_hero_in_the_prototypes_dress():
    """Eyebrow, verdict pill, the headline in Bodoni, mono price line —
    CSS on the card's own pieces. The headline's inline size is gone,
    because an inline style beat the token's size and the hero read as a
    card. Bodoni rides its own token: Ethan's August render set the
    display face to Archivo Narrow, and he chose Bodoni for this one
    headline (2026-09-22), so nothing else that reads --font-display
    moves."""
    potd = APP[APP.index("async function renderPickOfTheDay("):]
    potd = potd[:potd.index("\nfunction ", 10)]
    assert '<strong class="potd-bet">${text}</strong>' in potd
    assert 'style="font-size:var(--fs-lg)">${text}' not in potd
    assert ".potd-hero .player { font-size: var(--fs-2xs); font-weight: 800; letter-spacing: .14em;" in CSS
    # Named by the strip's two states, so test_potd_verdict's anchor on
    # the strip's own rule (`.potd-call {`) stays the first in the sheet.
    assert ".potd-hero .potd-call.is-bet, .potd-hero .potd-call.is-pass { display: inline-flex; align-self: flex-start;" in CSS, \
        "a pill, not a bar: the card is a flex column and stretches its items"
    assert ".potd-hero .potd-bet { font-family: var(--font-headline); font-size: var(--fs-2xl);" in CSS
    block = CSS.index("NEW LOOK — 2026-08-11")
    assert '--font-headline: "Bodoni Moda",' in CSS[:block], "the headline token is Bodoni, declared once in the base tokens"
    light = CSS.index(':root[data-theme="light"]', block)   # the light block AFTER the new-look tokens, not the first in the sheet
    assert "--font-headline:" not in CSS[block:light], "the new-look block must not override it the way it overrides --font-display"
    assert ".potd-hero .potd-bet + span { font-family: var(--font-mono); }" in CSS
    assert ".potd-hero.has-art { padding-top: 124px;" in CSS, "the art has room to be seen"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
