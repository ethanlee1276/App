"""An empty play rail says which kind of empty it is.

Ethan, 2026-09-09, asked what else would make the site feel better as
traffic grows. This is the oldest item on that list — failures that read
as ordinary empty results — and the live card was the cleanest example
left in the product.

With no plays, `playsHTML` returned "" and the card drew nothing at all.
Not a sentence, not a shrug: the rail was simply absent, which reads as
"this game has no play-by-play" whether the game had not kicked off, the
feed was unreachable, or the game was past the fetch cap. Three
situations, one silence, and only one of them is the reader's own
patience.

Both builds have always known which it was. `attach_plays` returns a note
saying so and both builders print it TO THE LOG, where no customer has
ever read it. The state is now on each GAME and the wording is in the
page.
"""

import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    return open(os.path.join(HERE, *parts), encoding="utf-8").read()


def _fn(js, name):
    i = js.index(f"function {name}(")
    return js[i:js.index("\nfunction ", i + 1)]


def _nocomments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def _states(pysrc, fname):
    """Every plays_state a builder can assign, read from the AST.

    Grepping the file would count the ones named in the comment that
    explains them — the trap this suite keeps walking into.
    """
    tree = ast.parse(pysrc)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == fname)
    out = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                    and t.slice.value == "plays_state"
                    and isinstance(node.value, ast.Constant)):
                out.add(node.value.value)
    return out


def test_both_builders_say_why_each_game_has_no_plays():
    mlb = _states(_read("live_build.py"), "attach_plays")
    assert {"idle", "capped", "ok", "unreachable"} <= mlb, mlb
    other = _states(_read("livescore_build.py"), "attach_plays")
    assert {"idle", "capped", "ok", "unreachable", "no_source"} <= other, other


def test_a_feed_that_failed_is_not_reported_as_no_plays():
    """The one that matters: the score keeps updating while the rail is
    empty, and the reader has no way to tell the feed broke."""
    js = _nocomments(_read("web", "js", "app.js"))
    i = js.index("const PLAYS_EMPTY = {")
    table = js[i:js.index("};", i)]
    assert "unreachable:" in table and "could not reach" in table.lower()
    assert "capped:" in table and "no_source:" in table
    assert "ok:" in table, "a real empty rail still needs its own words"


def test_the_rail_renders_the_reason_instead_of_nothing():
    fn = _nocomments(_fn(_read("web", "js", "app.js"), "playsHTML"))
    assert "PLAYS_EMPTY[" in fn, "the table is never consulted"
    assert "plays_state" in fn
    assert re.search(r"why\s*\?", fn), "the reason is looked up and dropped"


def test_a_game_that_has_not_started_stays_quiet():
    """`idle` deliberately has no sentence — the card already says the
    game has not started, and repeating it on every scheduled game is
    noise on the busiest screen we have."""
    js = _nocomments(_read("web", "js", "app.js"))
    table = js[js.index("const PLAYS_EMPTY = {"):]
    table = table[:table.index("};")]
    assert "idle:" not in table, "idle was given a sentence it does not need"


def test_an_older_payload_is_not_given_an_invented_reason():
    """A droplet serving a live file built before this shipped carries no
    `plays_state`. The rail must fall back to silence, not to a sentence
    about data that does not exist."""
    fn = _nocomments(_fn(_read("web", "js", "app.js"), "playsHTML"))
    assert re.search(r'return\s+why\s*\?.*:\s*""', fn, re.S), \
        "an unknown state does not fall back to silence"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
