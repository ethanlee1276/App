"""The page's own script as the tests read it: app.js and every room it loads
on first use, the rooms first.

Since 2026-10-24 a page that only some visits open lives in its own file,
fetched the first time it opens (app.js loadRoom): Rocket Radar, the Fantasy
room, the Record page, the game, pick and play-by-play pages, the account
pages and the rest of the More menu. Moving code there changes when it
arrives, not what it does, so a test that read app.js for a page reads
`app_js()` and keeps reading the same code wherever it now lives.

The rooms are read off app.js's own stubs (`roomCall(..., "js/record.js",
...)`), so a room added later is read here without touching this file.

Not a test module: `run_tests.py` collects `test_*.py`, so this is imported,
never collected.
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "web" / "js"


def rooms() -> list:
    """The room files, in the order app.js names them."""
    app = (JS / "app.js").read_text(encoding="utf-8")
    return list(dict.fromkeys(re.findall(r'roomCall\(\w+, "\w+", "js/([a-z0-9_-]+\.js)"', app)))


def app_js() -> str:
    """Every room, then app.js."""
    return "\n".join((JS / f).read_text(encoding="utf-8") for f in rooms() + ["app.js"])


_FILE: list = []


def app_js_file() -> str:
    """`app_js()` written to a temporary file, for a node harness that reads
    its source from a path. One file per test process, removed at exit."""
    if not _FILE:
        import atexit
        import os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".js", prefix="qb_app_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(app_js())
        atexit.register(lambda: os.path.exists(path) and os.unlink(path))
        _FILE.append(path)
    return _FILE[0]


def section(start: str, end: str) -> str:
    """From ``start`` to the next ``end`` inside the same file — the slice a
    test used to take of app.js. A page that moved to a room keeps its own
    code in the original order, but a marker's old neighbour may have stayed
    in app.js (or moved to another room): then a function is read whole and
    any other section runs to the end of its file."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _windows import block
    for f in rooms() + ["app.js"]:
        src = (JS / f).read_text(encoding="utf-8")
        i = src.find(start)
        if i < 0:
            continue
        j = src.find(end, i + 1)
        if j >= 0:
            return src[i:j]
        return block(src, start) if re.match(r"(async )?function ", start) else src[i:]
    raise ValueError(f"not in app.js or any room: {start!r}")


def _statement_end(src: str, i: int) -> int:
    """Where the top-level statement starting at ``i`` ends: a function's
    closing brace, or a declaration's semicolon at depth 0. Strings,
    templates (with their ``${}``) and comments are skipped; a regular
    expression holding a lone bracket would fool it, and none here does."""
    depth, j, n = 0, i, len(src)
    is_fn = bool(re.match(r"(async )?function", src[i:i + 15]))
    seen_paren_close, opened_body = False, False
    stack = []                       # template nesting: depth at each ${
    while j < n:
        c = src[j]
        if c in "\"'":
            j += 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
        elif c == "`":
            j += 1
            while j < n and src[j] != "`":
                if src[j] == "\\":
                    j += 1
                elif src.startswith("${", j):
                    stack.append(depth)
                    depth += 1
                    j += 1
                    break
                j += 1
            else:
                pass
            if j < n and src[j] == "{" and stack and stack[-1] == depth - 1:
                j += 1
                continue
        elif src.startswith("//", j):
            j = src.find("\n", j)
            j = n if j < 0 else j
        elif src.startswith("/*", j):
            j = src.find("*/", j + 2) + 1
        elif c in "([{":
            depth += 1
            if c == "{" and is_fn and seen_paren_close and depth == 1:
                opened_body = True
        elif c in ")]}":
            depth -= 1
            if c == "}" and stack and depth == stack[-1]:
                stack.pop()
                # back inside the template literal: find its end or next ${
                j += 1
                while j < n and src[j] != "`":
                    if src[j] == "\\":
                        j += 1
                    elif src.startswith("${", j):
                        stack.append(depth)
                        depth += 1
                        j += 1
                        break
                    j += 1
            if c == ")" and depth == 0:
                seen_paren_close = True
            if c == "}" and depth == 0 and opened_body:
                return j + 1
        elif c == ";" and depth == 0 and not is_fn:
            return j + 1
        j += 1
    return n


def decl(name: str) -> str:
    """One top-level declaration, whole, from app.js or whichever room holds
    it now: ``function name`` (async too), or ``const|let|var name = …;``."""
    for f in rooms() + ["app.js"]:
        src = (JS / f).read_text(encoding="utf-8")
        m = re.search(r"^(?:async )?function " + re.escape(name) + r"\b|^(?:const|let|var) "
                      + re.escape(name) + r"\b", src, re.M)
        if m:
            return src[m.start():_statement_end(src, m.start())]
    raise ValueError(f"no top-level declaration of {name!r} in app.js or any room")
