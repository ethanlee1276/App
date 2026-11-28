"""No page on this site prints "4 row(s)" at a reader.

Ethan, 2026-09-09, live for the NFL opener: *"there is no bugs or
glitches or visual problems with both the mobile app and site"*.

`(s)` is a programmer's shrug. It says the author knew the count could be
one, and decided the reader could do the grammar. Fifty-odd of them were
on the site — the board, the Record page, the CSV import, the draft room
— and two render functions had already grown their own private `plural`
helper rather than type it out, which is the tell that the shape was
wanted everywhere and owned nowhere. `plural`/`pluralWord` in app.js are
now the one place it lives.

WHY A WORD LIST AND NOT A PATTERN. `(s)` in JavaScript is usually a
function call on a parameter named `s` — `escapeHtml(s)`, `String(s)`,
`.test(s)`, `(s) => ...` — and no regex separates those from copy without
a parser. So this bans the specific NOUNS that appeared in prose. None of
them is a function anywhere in this file, the list is exact rather than
clever, and a new noun is one line to add.

The CLI tools are deliberately out of scope. `launch.py` printing
"3 game(s)" into a terminal on the droplet is a log line read by one
person who wrote it; this is about what a stranger reads on a phone.

    python3 tests/test_plural_copy.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _strip_comments(js):
    """Comments quote the copy they replaced — that history is worth
    keeping, and it is not what a reader sees."""
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", js, flags=re.S))


# Nouns that showed up in rendered copy. Every one of them is a word, not
# a callable, so `word(s)` in code can only be the shrug.
NOUNS = (
    "bet", "pick", "prop", "game", "row", "ticket", "market", "player",
    "team", "book", "price", "day", "win", "fight", "fighter", "trade",
    "cycle", "flag", "signal", "event", "night", "week", "card", "leg",
    "player-week", "unit", "share", "league", "note", "line",
)
_SHRUG = re.compile(r"\b(" + "|".join(map(re.escape, NOUNS)) + r")\(s\)",
                    re.IGNORECASE)
_ES = re.compile(r"\b(loss|match|box|class)\(es\)", re.IGNORECASE)


def _hits(text):
    out = []
    for m in list(_SHRUG.finditer(text)) + list(_ES.finditer(text)):
        line = text.count("\n", 0, m.start()) + 1
        a = max(0, m.start() - 50)
        out.append((line, text[a:m.end() + 20].replace("\n", " ")))
    return out


def test_app_js_never_prints_the_shrug():
    hits = _hits(_strip_comments(_read("web", "js", "app.js")))
    assert not hits, "app.js still shrugs at the reader:\n" + "\n".join(
        f"  line {n}: …{c}…" for n, c in hits[:12])


def test_the_html_shell_never_prints_it_either():
    """The static shell is what somebody sees before any JS has run."""
    hits = _hits(_read("web", "index.html"))
    assert not hits, "index.html still shrugs at the reader:\n" + "\n".join(
        f"  line {n}: …{c}…" for n, c in hits[:12])


def test_the_helpers_exist_and_take_an_explicit_irregular():
    """English does not always add an s. `loss` needs `losses` handed to
    it, so the helper takes one rather than guessing and printing
    "1 losss" the day somebody relies on the default."""
    js = _read("web", "js", "app.js")
    assert "function pluralWord(n, one, many) {" in js
    assert "function plural(n, one, many) {" in js
    i = js.index("function pluralWord(n, one, many) {")
    body = js[i:js.index("\n}", i)]
    assert "many || one" in body, "an irregular plural cannot be passed in"
    assert "Number(n) === 1" in body, \
        'a string "1" off a dataset attribute would read as plural'


def test_the_two_private_copies_did_not_outlive_the_shared_one():
    """Both predate the helper and both are still correct where they sit
    — this is here so that if either is ever deleted in favour of the
    shared pair, nobody has to wonder whether it was on purpose."""
    js = _strip_comments(_read("web", "js", "app.js"))
    private = js.count("const plural = (n,")
    assert private <= 2, \
        f"{private} private plural helpers — the shared one is at the top of the file"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
