"""The copy of the site's code a phone downloads, without its comments.

The site audit, 2026-09-24 (docs/AUDIT_2026-09-24.md, M-2). A first visit
downloads about 1.1 MB compressed before any board, and most of it is
explanation: `app.js` is 727 KB gzipped and 404 KB without its comments,
`styles.css` 177 KB and 62 KB. The comments are this codebase's memory
and stay in the repository; the browser has no use for them.

WHAT IT DOES. `build()` writes comment-stripped copies of the shell's
scripts and stylesheet under `web/min/` at the same paths (`web/min/js/
app.js` beside `web/js/app.js`), and Caddy serves the trimmed copy when
one exists (deploy/Caddyfile, `@trimmed`). `deploy/autoupdate.py` clears
them before it pulls — so between the pull and the rebuild Caddy falls
back to the new originals, never to an old trimmed copy under a new page —
and rebuilds them after.

WHY A TOKENIZER AND NOT A REGEX. `//` sits inside URLs in strings, `/*`
can sit inside a regular expression, and a template literal can hold a
whole second template in its `${}`. So the stripper walks the source the
way the language does — strings, templates (nested), regular expressions,
comments — and removes only the comments. A block comment that spanned a
line break becomes a line break, so automatic semicolon insertion reads
the code exactly as before.

WHAT PROVES IT. `tests/test_the_served_code_is_the_same_code.py` parses
the original and the trimmed copy with TypeScript's parser and requires
the two programs to print identically — every token, in order — on every
file this ships. A construct this tokenizer misreads fails the gate here,
before it can reach the box. On the box, anything it cannot read with
certainty (an unterminated string, a regex running into a line break)
raises, and `build()` writes nothing for that file: the page is served
the original, never a guess.

Standard library only; the droplet has no Node.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The shell files served trimmed: the page's own code, not vendor bundles
#: (already minified) and not the small team tables.
FILES = ("js/app.js", "js/visuals.js", "css/styles.css")

#: Where the trimmed copies go, under the web root, mirroring the paths.
MIN_DIR = "min"

#: After these, a `/` starts a regular expression rather than dividing.
_REGEX_AFTER_PUNCT = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_AFTER_WORD = {"return", "typeof", "case", "do", "else", "in", "of", "new",
                     "delete", "void", "throw", "instanceof", "yield", "await"}


class Unreadable(ValueError):
    """The source has a shape this tokenizer will not guess at."""


def _is_word(c: str) -> bool:
    return c.isalnum() or c in "_$"


def _string_end(src: str, i: int) -> int:
    q, j, n = src[i], i + 1, len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == q:
            return j + 1
        if c == "\n":
            raise Unreadable(f"line break inside a string at offset {i}")
        j += 1
    raise Unreadable(f"unterminated string at offset {i}")


def _regex_end(src: str, i: int) -> int:
    j, n, in_class = i + 1, len(src), False
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "\n":
            raise Unreadable(f"line break inside a regular expression at offset {i}")
        if in_class:
            if c == "]":
                in_class = False
        elif c == "[":
            in_class = True
        elif c == "/":
            j += 1
            while j < n and _is_word(src[j]):
                j += 1
            return j
        j += 1
    raise Unreadable(f"unterminated regular expression at offset {i}")


def strip_js(src: str) -> str:
    """``src`` without its comments. Raises `Unreadable` rather than guess."""
    out: list = []
    i, n = 0, len(src)
    # What a `/` would follow: "" at the start, a punctuation character, or
    # the last word (identifier, keyword or number).
    prev = ""
    # Contexts above plain code: "t" is template text, and an int is the
    # brace depth inside a template's `${ }`.
    stack: list = []
    while i < n:
        if stack and stack[-1] == "t":
            c = src[i]
            if c == "\\":
                out.append(src[i:i + 2])
                i += 2
            elif c == "`":
                out.append(c)
                stack.pop()
                prev = ")"                      # a template is a value
                i += 1
            elif src.startswith("${", i):
                out.append("${")
                stack.append(0)
                prev = "("
                i += 2
            else:
                out.append(c)
                i += 1
            continue
        c = src[i]
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j               # the line break stays
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise Unreadable(f"unterminated comment at offset {i}")
            out.append("\n" if "\n" in src[i:j] else " ")
            i = j + 2
            continue
        if c in "'\"":
            j = _string_end(src, i)
            out.append(src[i:j])
            prev = ")"
            i = j
            continue
        if c == "`":
            out.append(c)
            stack.append("t")
            i += 1
            continue
        if c == "/":
            regex = (prev == "" or prev in _REGEX_AFTER_PUNCT
                     or prev in _REGEX_AFTER_WORD)
            if regex:
                j = _regex_end(src, i)
                out.append(src[i:j])
                prev = ")"
                i = j
            else:
                out.append(c)
                prev = "/"
                i += 1
            continue
        if _is_word(c):
            j = i + 1
            while j < n and _is_word(src[j]):
                j += 1
            # A number's decimal point and exponent sign stay with it.
            word = src[i:j]
            out.append(word)
            prev = word
            i = j
            continue
        if c == "{" and stack and isinstance(stack[-1], int):
            stack[-1] += 1
        elif c == "}" and stack and isinstance(stack[-1], int):
            if stack[-1] == 0:
                stack.pop()                     # back into the template text
                out.append(c)
                i += 1
                continue
            stack[-1] -= 1
        out.append(c)
        if not c.isspace():
            prev = c
        i += 1
    if stack:
        raise Unreadable("a template literal is still open at the end of the file")
    return "".join(out)


def strip_css(src: str) -> str:
    """``src`` without its comments, strings untouched. A comment between
    two word characters becomes a space, so nothing is joined."""
    out: list = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"":
            j = _string_end(src, i)
            out.append(src[i:j])
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise Unreadable(f"unterminated comment at offset {i}")
            before = out[-1][-1:] if out else ""
            after = src[j + 2:j + 3]
            if before and after and _is_word(before) and _is_word(after):
                out.append(" ")
            i = j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _tidy(text: str) -> str:
    """Trailing spaces off every line and runs of blank lines to one. Safe in
    both languages only OUTSIDE strings and templates — so it is applied to
    CSS alone; JavaScript keeps its whitespace exactly (template literals
    carry the page's HTML, blank lines included)."""
    lines = [ln.rstrip() for ln in text.split("\n")]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(ln)
    return "\n".join(out)


def trimmed(rel: str, src: str) -> str:
    """The served text for one shell file."""
    if rel.endswith(".js"):
        return strip_js(src)
    return _tidy(strip_css(src))


def clear(web: Path) -> None:
    """Remove every trimmed copy, so the originals are what is served."""
    root = Path(web) / MIN_DIR
    for rel in FILES:
        try:
            (root / rel).unlink()
        except FileNotFoundError:
            pass


def build(web: Path) -> list:
    """Write the trimmed copies. One line per file: what it saved, or why
    it was left to the original."""
    web = Path(web)
    notes = []
    for rel in FILES:
        src_path, dst = web / rel, web / MIN_DIR / rel
        try:
            src = src_path.read_text(encoding="utf-8")
            text = trimmed(rel, src)
            # A trimmed copy that lost most of the file is a misread, not a
            # saving: the largest measured cut is 65% (the stylesheet).
            if len(text) < 0.25 * len(src):
                raise Unreadable(f"trimmed to {len(text)} of {len(src)} characters")
        except (OSError, Unreadable) as exc:
            try:
                dst.unlink()
            except FileNotFoundError:
                pass
            notes.append(f"{rel}: served as written — {exc}")
            continue
        # UNCHANGED IS LEFT ALONE. The updater runs this every five minutes;
        # rewriting an identical file would move its mtime, Caddy's ETag
        # with it, and every phone would download the script again.
        try:
            if dst.read_text(encoding="utf-8") == text:
                notes.append(f"{rel}: current")
                continue
        except (OSError, UnicodeDecodeError):
            pass
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
        notes.append(f"{rel}: {len(src) // 1024} KB -> {len(text) // 1024} KB")
    return notes


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--web", default=str(Path(__file__).resolve().parents[1] / "web"))
    ap.add_argument("--clear", action="store_true", help="remove the trimmed copies")
    args = ap.parse_args(argv)
    if args.clear:
        clear(Path(args.web))
        print("trimmed copies cleared; the originals are served")
        return 0
    for line in build(Path(args.web)):
        print(line)
    return 0


if __name__ == "__main__":                              # python3 -m engine.shrink
    raise SystemExit(main())
