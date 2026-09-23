"""The phone tab bar is five destinations and the fifth is More.

Ethan, 2026-09-22, on the Figma mock: "I like what you sent." The mock
put Home · Picks · Live · Results · More on the bar and everything else
behind More as pills grouped Bet · Follow · Research · Proof. Two things
here must never drift: the phone must not LOSE a destination the sidebar
has (the sheet is built from the sidebar's own buttons, and this test
checks the map covers them), and the tour card must not come back on a
phone, where the bar and the sheet are the tour.
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


def _strip_js_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n(function")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip_js_comments(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    j = APP.index(";\n", i)
    return APP[i:j + 1]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("MORE_GROUPS")}
      {_const("TAB_BAR_VIEWS")}
      {_const("TAB_BAR_TOOLS")}
      {_fn("moreSelector")}
      {_fn("tourDue")}
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


def _bar():
    bar = HTML[HTML.index('<nav class="tabbar"'):]
    return bar[:bar.index("</nav>")]


def _sidebar():
    sb = HTML[HTML.index('<aside class="sidebar"'):HTML.index("</aside>")]
    return re.sub(r"<!--.*?-->", "", sb, flags=re.S)


def _sidebar_destinations():
    """The same rule as app.js's sidebarDestinations(): every button
    that opens a view, a tool page or a sub-tab."""
    out = set()
    for m in re.finditer(r"<button\b([^>]*)>", _sidebar()):
        attrs = m.group(1)
        v = re.search(r'data-view="([^"]+)"', attrs)
        s = re.search(r'data-subtab="([^"]+)"', attrs)
        t = re.search(r'data-sport="([^"]+)"', attrs)
        if v:
            out.add(f"view:{v.group(1)}")
        elif s:
            out.add(f"subtab:{s.group(1)}")
        elif t and 'data-kind="tool"' in attrs:
            out.add(f"sport:{t.group(1)}")
    return out


def test_five_tabs_and_the_fifth_is_more():
    bar = _bar()
    items = re.findall(r'<button class="tb-item[^"]*"', bar)
    assert len(items) == 5, items
    views = re.findall(r'data-view="([a-z]+)"', bar)
    assert views == ["recommended", "tonight", "live"], views
    assert 'data-sport="record" data-kind="tool"' in bar
    assert 'id="tb-more"' in bar and "More</button>" in bar
    assert "Picks</button>" in bar, "the tonight page under its plain name"
    assert 'id="tb-search"' not in bar, "search moved into the sheet"
    assert 'aria-controls="more-sheet"' in bar


def test_search_kept_its_id_inside_the_sheet():
    sheet = HTML[HTML.index('id="more-sheet"'):]
    sheet = sheet[:sheet.index("</div>\n\n")]
    assert 'id="tb-search"' in sheet
    assert 'id="more-groups"' in sheet
    assert HTML.index('id="more-scrim"') < HTML.index('id="more-sheet"')
    body = _fn("moreSheetInit")
    assert 'getElementById("tb-more")' in body
    assert 'scrim.addEventListener("click", () => moreSheetOpen(false))' in body
    assert 'e.key === "Escape"' in body


def test_the_sheet_loses_no_sidebar_destination():
    got = _node("""
      const refs = [].concat(...MORE_GROUPS.map(([, r]) => r));
      const sel = Object.fromEntries(refs.map((r) => [r, moreSelector(r)]));
      return { refs, sel, views: TAB_BAR_VIEWS, tools: TAB_BAR_TOOLS,
               titles: MORE_GROUPS.map(([t]) => t) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["titles"] == ["Picks", "Odds", "Research", "My Book", "Proof"]  # the audit's groups, 2026-09-23
    on_bar = {f"view:{v}" for v in got["views"]} | {f"sport:{t}" for t in got["tools"]}
    bar = _bar()
    for v in got["views"]:
        assert f'data-view="{v}"' in bar, v
    for t in got["tools"]:
        assert f'data-sport="{t}"' in bar, t
    refs = set(got["refs"])
    assert len(got["refs"]) == len(refs), "a destination listed twice"
    sidebar = _sidebar_destinations()
    missing = sidebar - refs - on_bar
    assert not missing, f"sidebar destinations a phone cannot reach: {sorted(missing)}"
    dangling = refs - sidebar
    assert not dangling, f"More pills with no sidebar button behind them: {sorted(dangling)}"
    # The selector really points into the sidebar, at that attribute.
    assert got["sel"]["view:edge"] == '#sidebar [data-view="edge"]'
    assert got["sel"]["sport:lab"] == '#sidebar [data-sport="lab"]'
    assert got["sel"]["subtab:gamebets"] == '#sidebar [data-subtab="gamebets"]'
    assert "view:likely" in got["refs"], "Top Picks is the board people come for"


def test_a_pill_is_the_sidebar_button_it_stands_for():
    body = _fn("moreSheetBuild")
    assert "document.querySelector(moreSelector(ref))" in body
    assert "if (!src || src.hidden) return;" in body, "hidden there, hidden here"
    assert "pill.textContent = morePillLabel(src);" in body
    assert 'pill.addEventListener("click", () => { moreSheetOpen(false); src.click(); });' in body
    lab = _fn("morePillLabel")
    assert 'querySelectorAll("svg, .sb-badge")' in lab
    assert 'sidebarDestinations' in APP and "#sidebar button[data-view], #sidebar button[data-sport], #sidebar button[data-subtab]" in _fn("sidebarDestinations")


def test_the_sheet_opens_over_the_bar_and_closes_on_any_view_change():
    assert ".more-sheet, .more-scrim { display: none; }" in CSS
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert ".more-sheet { display: block; position: fixed; left: 0; right: 0; bottom: 0; z-index: 58;" in phone
    assert ".more-scrim { display: block; position: fixed; inset: 0; z-index: 57;" in phone
    assert ".tabbar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 56;" in phone
    assert ".more-scrim[hidden], .more-sheet[hidden] { display: none; }" in phone
    assert "body.more-open .more-sheet { transform: translateY(0); }" in phone
    op = _fn("moreSheetOpen")
    assert "moreSheetBuild();" in op, "rebuilt on open — fresh badges, the lit pill"
    assert "sheet.hidden = false; scrim.hidden = false;" in op
    assert 'document.body.classList.add("more-open")' in op
    router = _fn("_switchViewNow")
    assert 'if (document.body.classList.contains("more-open")) moreSheetOpen(false);' in router


def test_the_tour_never_opens_on_a_phone():
    got = _node("""
      const base = { stored: "", hash: "", isStatic: false, view: "recommended", standalone: ["about"], wall: [] };
      return { desk: tourDue({ ...base, coarse: false }), phone: tourDue({ ...base, coarse: true }),
               unsaid: tourDue(base) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["desk"] is True and got["unsaid"] is True
    assert got["phone"] is False
    maybe = _fn("tourMaybe")
    assert "coarse: isPhone()" in maybe
    assert 'matchMedia("(max-width: 760px)").matches' in _fn("isPhone")


def test_the_theme_switch_moves_into_the_sheet_on_phones():
    """One fewer control in a top bar that had five. The sheet's button
    proxies the real toggle, so the theme is still switched in one place."""
    sheet = HTML[HTML.index('id="more-sheet"'):]
    sheet = sheet[:sheet.index("</div>\n\n")]
    assert 'id="more-theme"' in sheet
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert "#theme-toggle { display: none; }" in phone
    assert "#theme-toggle { display: none; }" not in CSS[:CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }"))], \
        "desktop keeps its toggle"
    init = _fn("moreSheetInit")
    assert 'const real = document.getElementById("theme-toggle");' in init
    assert "if (real) real.click(); else toggleTheme();" in init
    build = _fn("moreSheetBuild")
    assert 'theme.textContent = `Switch to ${cur === "dark" ? "light" : "dark"} mode`;' in build, \
        "the button says where it goes, not where it is"


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
