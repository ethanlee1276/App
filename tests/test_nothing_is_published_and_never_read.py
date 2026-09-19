"""Every key the export publishes is read by something.

THE RECURRING BUG OF THIS CODEBASE, caught by a rule instead of by
Ethan. On 2026-09-19 alone, six things were computed correctly, written
into a payload, and read by nothing:

  * `stale_verdicts` — a shadow book's promotion verdict, recomputed on
    every export since it was written. Its own docstring said the acting
    half was "a separate change"; the change was never made, so college
    could not be seen climbing toward the bar.
  * `shadow_books` / `journaled` — did not exist, because the books and
    counts they carry had no reader either.
  * the UFC book — 18 graded fights drawn by a section that sat one line
    below the return that hid it.
  * the exchange census and `boards_unreadable` — same shape.

Each was found by Ethan asking why a page was empty. That is the wrong
detector. A key with no reader is a fact this file can check, and the
check costs nothing.

THE RULE: every key `ledger.export_json` writes must appear in something
that consumes the file — the front end, the server, the runbook checks —
or be named in `PUBLISHED_FOR_OTHERS` with the reason. The allow-list is
deliberately small and each entry has to say who reads it, so "nothing
reads this" can never again be the quiet default.

Run directly: `python3 tests/test_nothing_is_published_and_never_read.py`
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]

#: Keys published for a consumer that is not one of the files scanned
#: below. Each needs a reason naming the reader — an entry with no
#: reader is the bug this file exists to catch.
PUBLISHED_FOR_OTHERS: dict = {
    # (empty — every key currently published has a reader in the files
    # scanned below. Add here only with the reader named.)
}

#: What counts as reading the file.
READERS = ("web/js/app.js", "launch.py", "server.py", "homecheck.py")


def _export_keys() -> list:
    """The top-level keys `export_json` writes into record.json."""
    src = (ROOT / "engine" / "ledger.py").read_text()
    i = src.index("def export_json(")
    nxt = re.search(r"\ndef [a-z_]+\(", src[i + 10:])
    body = src[i:i + 10 + (nxt.start() if nxt else len(src))]
    return sorted(set(re.findall(r'^\s+"([a-z_0-9]+)":', body, re.M)))


def _strip_comments(text: str, js: bool) -> str:
    """Comments removed, so PROSE cannot satisfy this check.

    Found by mutation, 2026-09-19: deleting the only line that read
    `clv_coverage` left the check passing, because `recCoverageNote`'s
    comment above it still named the key. A guard against "computed and
    never placed" that a sentence can satisfy is the same bug wearing a
    test's clothes.
    """
    if js:
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"(?m)//.*$", " ", text)
    else:
        text = re.sub(r"(?s)([\"']{3}).*?\1", " ", text)
        text = re.sub(r"(?m)#.*$", " ", text)
    return text


def _readers() -> str:
    out = []
    for rel in READERS:
        p = ROOT / rel
        if p.exists():
            out.append(_strip_comments(p.read_text(), rel.endswith(".js")))
    return "\n".join(out)


def _unread(keys, hay) -> list:
    return [k for k in keys
            if f".{k}" not in hay and f'"{k}"' not in hay and f"'{k}'" not in hay]


def test_every_published_key_has_a_reader():
    keys = _export_keys()
    assert len(keys) > 30, f"only {len(keys)} keys found — the parse broke"
    dead = [k for k in _unread(keys, _readers())
            if k not in PUBLISHED_FOR_OTHERS]
    assert not dead, (
        "published by export_json and read by nothing: " + ", ".join(dead)
        + "\n\nEither wire it to a reader, or add it to "
          "PUBLISHED_FOR_OTHERS naming who reads it. A value computed on "
          "every export and rendered nowhere is the bug that cost Ethan "
          "four rounds of reading the journal on 2026-09-19.")


def test_the_allow_list_carries_a_reason_for_every_entry():
    """An allow-list that can be extended with a bare key is just a
    slower version of the bug."""
    for key, why in PUBLISHED_FOR_OTHERS.items():
        assert isinstance(why, str) and len(why) > 20, \
            f"{key} is allowed with no reader named: {why!r}"


def test_the_allow_list_does_not_hide_a_key_that_has_a_reader():
    """A stale entry would let a key go dead later without a failure."""
    hay = _readers()
    for key in PUBLISHED_FOR_OTHERS:
        assert _unread([key], hay), \
            f"{key} IS read by a scanned file — drop it from the allow-list"


def test_the_check_would_have_caught_this_sessions_bugs():
    """The rule has to be strong enough to have fired. Each of these was
    published and unread on the morning of 2026-09-19."""
    keys = _export_keys()
    for key in ("stale_verdicts", "shadow_books", "journaled"):
        assert key in keys, f"{key} is no longer exported — re-read this test"
    hay = _readers()
    assert not _unread(["stale_verdicts", "shadow_books", "journaled"], hay), \
        "one of the keys fixed on 2026-09-19 has gone unread again"


def test_a_key_with_no_reader_is_actually_detected():
    """MUTATION, inline: the rule must fail on a planted dead key, or it
    is a test that can only pass."""
    assert _unread(["a_key_nothing_reads_xyzzy"], _readers()) == \
        ["a_key_nothing_reads_xyzzy"]



def test_a_comment_naming_the_key_does_not_count_as_reading_it():
    """MUTATION, 2026-09-19. Deleting the one line that read
    `clv_coverage` left this check green, because the comment above it
    still said the word."""
    js = "/* we should really render d.some_key_zz one day */\nfoo();"
    assert _unread(["some_key_zz"], _strip_comments(js, js=True)) == \
        ["some_key_zz"]
    py = '# some_key_zz is published for the front end\nx = 1\n'
    assert _unread(["some_key_zz"], _strip_comments(py, js=False)) == \
        ["some_key_zz"]


def test_real_code_still_counts_as_reading_it():
    js = "const v = d.some_key_zz || {};"
    assert _unread(["some_key_zz"], _strip_comments(js, js=True)) == []

if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
