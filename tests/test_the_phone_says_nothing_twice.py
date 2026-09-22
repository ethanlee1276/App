"""v4, slice one: the phone says nothing twice.

Ethan, 2026-09-22, with three screenshots of his phone: "there's a lot
of repeats … it still kinda looks like the same old website." The
repeats he circled: the league crest said its code inside the circle
and again beneath it; the More sheet was thirty identical pills; Record
sat in the sheet and on the tab bar as Results; the home's Riding
section was the tray's rows over again. Each is pinned here as a rule,
not a screenshot.
"""
import json
import re
import subprocess
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
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    depth = 0
    for j in range(i, len(APP)):
        if APP[j] in "[{": depth += 1
        elif APP[j] in "]}":
            depth -= 1
            if depth == 0: return APP[i:j + 1] + ";"
    raise AssertionError(name)


def _node(js):
    try:
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return None
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


PHONE = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".sportbar-in .sport-btn { flex: 0 0 auto;")):]
PHONE = PHONE[:PHONE.index("\n}\n") + 3]
SHEET = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]


# --- the crest ---------------------------------------------------------------
def test_every_league_button_has_a_glyph_and_the_glyphs_are_drawn():
    leagues = re.findall(r'<button class="sport-btn[^"]*" data-sport="([a-z]+)" data-kind="league"', HTML)
    assert leagues, "no league buttons in the strip"
    got = _node(f"""
      const ICON_PATHS = (() => {{ {_const("ICON_PATHS")} return ICON_PATHS; }})();
      {_const("LEAGUE_GLYPH")}
      console.log(JSON.stringify({{ glyphs: LEAGUE_GLYPH, drawn: Object.keys(ICON_PATHS) }}));""")
    if got is None:
        print("  SKIP node not installed"); return
    for lg in leagues:
        assert lg in got["glyphs"], f"{lg} has no crest glyph"
        assert got["glyphs"][lg] in got["drawn"], f"{lg}'s glyph {got['glyphs'][lg]!r} is not in ICON_PATHS"
    assert {"football", "baseball", "basketball", "octagon"} <= set(got["drawn"])


def test_the_crest_is_inert_and_built_once():
    body = _fn("leagueCrests")
    assert 'querySelectorAll(\'.sportbar-in .sport-btn[data-kind="league"]\')' in body
    assert 'if (b.querySelector(".crest")) return;' in body, "a second call would stack crests"
    assert 's.setAttribute("aria-hidden", "true");' in body, "the crest must not become part of the button's name"
    assert "s.innerHTML = icon(g, 22);" in body and "b.prepend(s);" in body
    assert "textContent" not in body, "the label is the button's own text, untouched"
    wiring = APP[APP.index("adoptCleanURL();"):APP.index("initHeaderTuck();")]
    assert "leagueCrests();" in wiring, "the crests are not built at boot"


def test_the_code_is_said_once_on_phones_and_the_desktop_keeps_text_tabs():
    assert "attr(data-sport)" not in CSS, "the circle prints the code again"
    assert ".sportbar-in .sport-btn .crest { display: none; }" in CSS[:CSS.index("@media (max-width: 760px) {", CSS.index(".sportbar-in .sport-btn { flex: 0 0 auto;"))]
    assert ".sportbar-in .sport-btn .crest svg { width: 22px; height: 22px; }" in PHONE
    assert ".sportbar-in .sport-btn.active .crest { outline-color: var(--gold);" in PHONE


# --- the sheet ---------------------------------------------------------------
def test_a_sheet_row_carries_the_sidebar_buttons_own_mark():
    body = _fn("moreSheetBuild")
    i = body.index("pill.textContent = morePillLabel(src);")
    j = body.index('const ico = src.querySelector(".sb-ico");')
    assert i < j, "the icon is cloned before the label is set, so the label would erase it"
    assert "if (ico) pill.prepend(ico.cloneNode(true));" in body
    assert ".more-pills { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }" in SHEET
    assert ".more-pill svg { width: 18px; height: 18px; flex: 0 0 auto; color: var(--brand-2); }" in SHEET
    assert "border-radius: 999px" not in SHEET[SHEET.index(".more-pill {"):SHEET.index(".more-pill.active {")], "still a pill"


def test_results_is_on_the_tab_bar_so_the_sheet_does_not_list_it():
    got = _node(f"""
      {_const("MORE_GROUPS")}
      {_const("TAB_BAR_TOOLS")}
      console.log(JSON.stringify({{ refs: [].concat(...MORE_GROUPS.map(([, r]) => r)), tools: TAB_BAR_TOOLS }}));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert "record" in got["tools"]
    assert "sport:record" not in got["refs"], "Record is listed twice: the tab bar's Results and a sheet row"
    for ref in got["refs"]:
        kind, name = ref.split(":")
        assert not (kind == "sport" and name in got["tools"]), f"{ref} is on the bar already"


# --- the riding rows ---------------------------------------------------------
def test_the_riding_section_yields_to_the_tray_on_phones():
    assert '#home-deck .hd-sec[data-sec="riding"] { display: none; }' in SHEET
    # …and only on phones: the base grid still places it, the deck still fills it.
    base = CSS[:CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }"))]
    assert '[data-sec="riding"] { display: none; }' not in base
    assert 'deckFill(host, "riding", deckRidingHTML(riding));' in _fn("renderHomeDeck")


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
