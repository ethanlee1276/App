"""The phone home leads with what is live.

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


def test_the_deck_is_the_first_thing_on_the_home_view_and_the_board_folds_under_it():
    view = HTML[HTML.index('id="view-recommended"'):]
    view = re.sub(r"<!--.*?-->", "", view, flags=re.S)
    first = re.search(r"<(div|section|p|h\d)\b[^>]*>", view[view.index(">") + 1:])
    assert first and 'id="home-deck"' in first.group(0), first.group(0) if first else None
    assert '<div id="home-deck" hidden></div>' in view
    # The fold hides every child of the view but the deck — a structural
    # rule, because subtabbedDOM regroups the zones into panels at load
    # and a wrapper div in the markup broke its insertBefore (measured
    # 2026-09-22: four page errors and the crash note on every load).
    assert "body.home-folded #view-recommended > :not(#home-deck) { display: none; }" in CSS
    assert 'class="home-rest"' not in HTML
    assert "body.has-deck #rail-live { display: none; }" in CSS, "the rail's Live now is the strip, twice"
    assert 'document.body.classList.toggle("has-deck", any);' in _fn("renderHomeDeck")
    # Desktop: a grid with the live strip and the door spanning it. Phone: one column.
    assert "#home-deck { display: grid; grid-template-columns: 1fr 1fr;" in CSS
    assert '#home-deck .hd-sec[data-sec="live"], #home-deck .hd-fold { grid-column: 1 / -1; }' in CSS
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert "#home-deck { display: block;" in phone
    assert "#home-deck[hidden] { display: none; }" in phone
    home = _fn("renderRecommended")
    assert "renderHomeDeck();" in home[:300], "drawn before the zones below it"
    deck = _fn("renderHomeDeck")
    assert "isPhone()" not in deck, "the deck is the home at every width now"
    assert "applyHomeFold(any);" in deck
    fold = _fn("applyHomeFold")
    assert 'document.body.classList.toggle("home-folded", !!deckShown && homeFolded());' in fold, \
        "nothing to fold under when the deck is empty"
    assert 'localStorage.getItem(HOME_FOLD_KEY) !== "open"' in _fn("homeFolded"), "folded until opened"


def test_the_order_is_live_riding_tonight_record_zeno():
    got = _node("return HOME_DECK_ORDER;")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["live", "riding", "tonight", "record", "zeno"], got
    deck = _fn("renderHomeDeck")
    assert 'const body = HOME_DECK_ORDER.map((k) => sections[k] || "").join("");' in deck
    assert "const any = !!body.trim();" in deck and "host.hidden = !any;" in deck, "five empty sections is no deck at all"
    for k in ("live", "riding", "tonight", "record", "zeno"):
        assert f'data-sec="{k}"' in APP, k


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
    assert got["live"] == [["nfl", "GB", 2], ["nfl", "KC", 0], ["mlb", "LAD", 0]], got["live"]
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
    assert "if (now !== _deckStamp) { renderHomeDeck(); return; }" in arm, "redraw only when a score moved"


def test_every_printed_number_is_an_earned_one():
    rec = _fn("deckRecordHTML")
    assert "if (ov.settled) {" in rec and "if (zo.settled) {" in rec, "no tile over nothing"
    assert "rec.overall || {}" in rec and "rec.zeno || {}" in rec
    assert "zenoTicketRow(r, false)" in rec, "Zeno's open tickets are the record page's own rows"
    tonight = _fn("deckTonightHTML")
    assert 'String(call) === "bet"' in tonight, "a NO BET day has no Pick of the Day hero"
    assert ".filter(showableLikelyRow)" in tonight, "the board's own gate"
    assert 'if (!showPotd && !likely.length) return "";' in tonight
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
    for sel in (".hd-row {", ".hd-card {", ".hd-strip {", ".hd-stat {", ".hd-row.openable {", ".tn-full {"):
        assert sel in CSS[:phone_at], sel
    deck = _fn("deckTonightHTML")
    assert "potdHeroHTML(d)" in deck, "one hero, drawn by one function"


def test_the_render_instrument_measures_the_board_with_the_fold_open():
    """rendercheck's Dashboard claims are about the board under the deck
    (quick tools, the perf grid). Folded, they measured DRIFT on a
    page that was fine — so the instrument opens the fold first."""
    src = (ROOT / "rendercheck.py").read_text()
    assert "localStorage.setItem('qb.home.fold', 'open')" in src
    assert src.index("qb.home.fold") < src.index("await p.goto(`http://127.0.0.1:${PORT}/${s.url}`"), \
        "set before the page boots, not after"
    assert 'const HOME_FOLD_KEY = "qb.home.fold";' in APP, "the same key the page reads"


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
