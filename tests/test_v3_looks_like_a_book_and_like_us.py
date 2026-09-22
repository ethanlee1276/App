"""v3: the sportsbook genre's pieces, in Qellys clothes.

Ethan, 2026-09-22: "we want our app to look kind of like a sportsbook
app but also like our own" — then "Build it all." The brief in
docs/VISUAL_REDESIGN.md names what was borrowed: the league carousel
of crests, odds pills on the game card, the price pill beside our
number on a pick row, the win-probability bar on a live card, the
record as a ribbon with a ring and form dots, the riding tray as our
slip, and the Pick of the Day as a hero on its venue render. The rule
under all of it: nothing invented — every bar, dot and pill is drawn
from a number the board already holds, and is not drawn otherwise.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


PHONE = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".sportbar-in .sport-btn { flex: 0 0 auto;")):]
PHONE = PHONE[:PHONE.index("\n}\n") + 3]


def test_the_league_strip_is_a_carousel_of_crests_on_phones_and_still_wraps():
    assert ".sportbar-in .sport-btn::before { content: attr(data-sport);" in PHONE, "the crest is the code, from the button's own attribute"
    assert "border-radius: 50%" in PHONE
    # The ring is an inset outline: 2px stays a stripe weight for borders
    # (tests/test_hairlines.py), and the crest keeps its size when active.
    assert "outline: 2px solid transparent; outline-offset: -2px;" in PHONE
    assert ".sportbar-in .sport-btn.active::before { outline-color: var(--gold);" in PHONE
    assert "box-shadow: var(--glow); }" in PHONE, "the glow is the token's"
    # It still wraps: the base rule is untouched and nothing in the phone block scrolls it.
    base = CSS[CSS.index(".sportbar-in {"):]
    base = base[:base.index("}")]
    assert "flex-wrap: wrap" in base and "overflow" not in base
    assert "overflow" not in PHONE[PHONE.index(".sportbar-in { padding: 6px 8px 2px; }"):PHONE.index(".sportbar-in .sport-btn.active::before")]


def test_odds_cells_are_pills_and_the_team_column_is_not():
    assert ".gc-mk { display: grid; gap: 2px; min-width: 0; padding: 5px 6px;" in CSS
    assert "border-radius: var(--radius); background: var(--bg); }" in CSS
    assert ".gc-mk-teams { text-align: left; border: 0; background: transparent; padding-left: 0; }" in CSS


def test_a_pick_row_puts_the_price_in_a_pill_beside_our_number():
    row = _fn("deckPickRow")
    assert 'const price = r.odds != null ? `<span class="hd-o">${american(r.odds)}</span>` : "";' in row
    assert 'const sub = [where, r.book || ""]' in row, "the sub-line no longer repeats the price"
    assert "isFinite(p) && p > 0 && p < 1" in row, "a certainty is not a forecast"
    assert '<span class="hd-p" title="chance to hit">' in row
    assert 'const nums = price || num ? `<div class="hd-num">${price}${num}</div>` : "";' in row
    assert ".hd-o {" in CSS and ".hd-p {" in CSS and ".hd-num {" in CSS


def test_the_live_card_draws_a_win_probability_bar_only_from_a_read_clock():
    card = _fn("deckGameHTML")
    assert "const wp = lv.win_prob && lv.win_prob.home_win_prob != null ? lv.win_prob : null;" in card
    assert 'class="hd-wp"' in card and "${wpBar}" in card
    assert "% to win" in card
    assert "Math.round(wp.home_win_prob * 100)" in card
    assert ".hd-wp { height: 4px;" in CSS
    # the number's provenance travels on the bar
    assert 'wp.basis || "score and clock"' in card


def test_the_record_is_a_ribbon_with_a_ring_and_form_dots_from_its_own_rows():
    rec = _fn("deckRecordHTML")
    assert 'dots(rec.recent, "status")' in rec, "the model's last five are the record's own settled rows"
    assert 'dots(z.recent, "result")' in rec, "Zeno's last five are his tickets"
    assert "const rate = (t) => ((t.wins || 0) + (t.losses || 0)) ? (t.wins || 0) / ((t.wins || 0) + (t.losses || 0)) : 0;" in rec, \
        "the ring is wins over decisions, pushes out"
    assert "if (ov.settled) {" in rec and "if (zo.settled) {" in rec, "no ribbon over nothing"
    assert '<i class="${w ? "w" : l ? "l" : "p"}">' in rec
    assert ".hd-ribbon {" in CSS and ".hd-ring {" in CSS and ".hd-form i.l { background: var(--bad); }" in CSS
    assert "  --grad-ring: conic-gradient(var(--good) 0 calc(var(--pc) * 1%), var(--border) calc(var(--pc) * 1%) 100%);" in CSS, \
        "the arc is a token declared on the ring, where --pc lives"
    assert "  --pc: 0;" in CSS and "background: var(--grad-ring); }" in CSS


def test_the_riding_tray_is_our_slip_phones_only_and_never_on_the_live_tab():
    assert 'id="riding-tray"' in HTML and 'class="riding-tray" hidden' in HTML
    tray = _fn("renderRidingTray")
    assert "tray.dataset.n = String(n);" in tray
    assert "${trackerBetText(first)}" in tray, "the Live tab's sentence, not a second one"
    assert 'tray.onclick = () => switchView("live", true);' in tray
    sync = _fn("ridingTraySync")
    assert 'const shown = Number(tray.dataset.n) > 0 && !["live", "pbp"].includes(state.view);' in sync
    assert 'document.body.classList.toggle("has-tray", shown);' in sync
    router = _fn("_switchViewNow")
    i = router.index("state.view = name;")
    assert 'if (typeof ridingTraySync === "function") ridingTraySync();' in router[i:i + 200], "synced right after the view moves"
    deck = _fn("renderHomeDeck")
    assert "renderRidingTray(riding);" in deck
    assert ".riding-tray { display: none; }" in CSS[:CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }"))]
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert ".riding-tray { position: fixed; left: 16px; right: 16px; z-index: 54;" in phone
    assert "body.has-tray { padding-bottom: 150px; }" in phone, "the page clears the tray"


def test_the_pick_of_the_day_is_a_hero_on_its_own_venue_render():
    potd = APP[APP.index("async function renderPickOfTheDay("):]
    potd = _strip(potd[:potd.index("\nfunction ", 10)])
    assert "const potdFam = VENUE_FAMILY[state.sport];" in potd
    assert "const potdArt = potdFam ? absoluteSrc(venueSrc(`img/venues/variants/${potdFam}-${venueVariant(potdTeam)}.jpg`)) : \"\";" in potd, \
        "the same render the stadium strip would pick, as an absolute URL; none for a sport without a family"
    # Chromium resolves a url() that arrives through a custom property
    # against the stylesheet — a relative path would paint css/img/…
    helper = _fn("absoluteSrc")
    assert "return new URL(rel, document.baseURI).href;" in helper and "catch (e) { return rel; }" in helper
    assert '[pick.odds != null ? american(pick.odds) + (pick.book ? ` at ${escapeHtml(pick.book)}` : "") : escapeHtml(pick.book || ""),' in potd, \
        "an unpriced pick is not the word undefined"
    assert 'matchup].filter(Boolean).join(" · ")' in potd, "no leading separator when the price is missing"
    assert '<div class="card potd-hero${potdArt ? " has-art" : ""}"' in potd
    assert "--potd-art:url(${potdArt})" in potd
    assert ".potd-hero.has-art { padding-top: 84px; background-image: var(--grad-potd-fade), var(--potd-art); }" in CSS
    assert "  --potd-art: none;" in CSS and "  --grad-potd-fade: linear-gradient(180deg, color-mix(in oklab, var(--panel) 25%, transparent)," in CSS
    assert ".potd-hero strong { font-family: var(--font-display);" in CSS, "the headline in the book's voice"


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
