"""A room's stylesheet holds only rules its own pages can match.

2026-10-24 (Ethan: "keep going and finish everything"): the rules only the
Record page, the detail pages, the account pages or the More menu's pages
can match moved out of styles.css into css/record.css, css/detail.css,
css/account.css and css/more.css, loaded with their room (app.js loadRoom):
styles.css, the sheet every first visit waits for, 73.1 -> 56.6 KB gz. The
move was checked by screenshots of every room page, each in a fresh browser,
before and after: identical.

The rule that keeps it safe, held here for every later edit: each selector
in a room's sheet needs a class that the room's own script draws and nothing
else does — not app.js, not another room, not any other script, page or
server template (a class built at run time from a prefix counts as drawn by
whoever builds it). A class two rooms draw stays in styles.css: otherwise
whichever page opened first would show the other without it. If this
fails, the class named is now drawn somewhere else: move its rules back to
styles.css (or into that room too).

Run directly: `python3 tests/test_a_rooms_styles_are_its_own.py`
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _app import room_sheets  # noqa: E402

ROOMS = ("record", "detail", "account", "more")


def _read(p):
    try:
        return open(p, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        return ""


def _words(t):
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_-]*", t))


def _prefixes(t):
    out = set(re.findall(r"([A-Za-z_][A-Za-z0-9_-]*-)\$\{", t))
    for attr in re.findall(r'class="([^"]*)"', t):
        out |= set(re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_-]*)\$\{", attr))
    out |= set(re.findall(r"[\"']([A-Za-z_][A-Za-z0-9_-]*-)[\"']\s*\+", t))
    return out


#: Each file's words and run-time class prefixes, read once.
SOURCES = {}
for f in (glob.glob(os.path.join(ROOT, "web", "js", "*.js")) + glob.glob(os.path.join(ROOT, "web", "*.html"))
          + glob.glob(os.path.join(ROOT, "engine", "**", "*.py"), recursive=True)
          + [os.path.join(ROOT, "server.py"), os.path.join(ROOT, "launch.py")]):
    t = _read(f)
    SOURCES[os.path.relpath(f, ROOT)] = (_words(t), tuple(_prefixes(t)))


def _drawn_elsewhere(c, room):
    mine = f"web/js/{room}.js"
    for f, (words, prefixes) in SOURCES.items():
        if f != mine and (c in words or c.startswith(prefixes)):
            return f
    return None


def _required(sel):
    s = re.sub(r"\[[^\]]*\]", "", sel)
    while True:
        t = re.sub(r":(?:not|has|is|where)\([^()]*\)", "", s)
        if t == s:
            return set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", t))
        s = t


def _selectors(css):
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", body):
        sel = " ".join(m.group(1).split())
        if sel.startswith("@") or not sel:
            continue
        out += [s.strip() for s in sel.split(",") if s.strip()]
    return out


def test_every_room_has_its_sheet_and_loads_it():
    assert set(f"{r}.css" for r in ROOMS) <= set(room_sheets()), room_sheets()
    for r in ROOMS:
        assert os.path.getsize(os.path.join(ROOT, "web", "css", f"{r}.css")) > 1000, r


def test_every_rule_in_a_rooms_sheet_needs_a_class_only_that_room_draws():
    bad = []
    for r in ROOMS:
        own = SOURCES[f"web/js/{r}.js"][0]
        cache = {}
        for sel in _selectors(_read(os.path.join(ROOT, "web", "css", f"{r}.css"))):
            req = _required(sel)
            ok = False
            for c in req:
                if c not in own:
                    continue
                if c not in cache:
                    cache[c] = _drawn_elsewhere(c, r)
                if cache[c] is None:
                    ok = True
                    break
            if not ok:
                where = {c: cache.get(c) or _drawn_elsewhere(c, r) for c in req}
                bad.append((f"css/{r}.css", sel, where))
    assert not bad, bad[:8]


def test_nothing_in_a_rooms_sheet_is_also_left_in_styles_css():
    sheet = _read(os.path.join(ROOT, "web", "css", "styles.css"))
    sheet_rules = set(re.findall(r"(?m)^([^\s@/{}][^{}]*\{[^{}]*\})", re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)))
    for r in ROOMS:
        room = re.sub(r"/\*.*?\*/", "", _read(os.path.join(ROOT, "web", "css", f"{r}.css")), flags=re.S)
        dup = [x for x in re.findall(r"(?m)^([^\s@/{}][^{}]*\{[^{}]*\})", room) if x in sheet_rules]
        assert not dup, (r, dup[:3])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
