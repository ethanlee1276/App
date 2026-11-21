"""No two page scripts declare the same global name.

Every file in web/js is a classic script, so a top-level `function x()` or
`const x` lands in one shared global scope, and a later file's `function x`
silently REPLACES an earlier one. 2026-10-26: the Live tab's members strip
in js/chat.js declared `async function mbLoad()` — the name of My Bets'
loader in app.js. The moment the chat room loaded, every `mbLoad()` on the
site got a Promise instead of the saved bets: My Bets, the Live tab's open
bets and the game chat's own sheet all threw, and the chat sheet half-drew
(Ethan: "the buttons to get to the game chat page are buggy and glitch out
and throw errors sometimes").

The one sanctioned overlap is app.js's lazy-load stub — `function x(...a)
{ return roomCall(x, ...) }` — which its room file replaces on purpose.

    python3 tests/test_no_two_scripts_share_a_global_name.py
"""
import collections
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(ROOT, "web", "js")
DECL = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(|^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", re.M)


def _declared():
    seen = collections.defaultdict(set)
    for f in sorted(glob.glob(os.path.join(JS, "*.js"))):
        src = open(f, encoding="utf-8").read()
        for m in DECL.finditer(src):
            seen[m.group(1) or m.group(2)].add(os.path.basename(f))
    return seen


def _stub(app, name):
    return re.search(rf"^function {re.escape(name)}\(\.\.\.a\) {{ return roomCall\({re.escape(name)},", app, re.M)


def test_every_shared_name_is_a_room_stub_and_nothing_else():
    app = open(os.path.join(JS, "app.js"), encoding="utf-8").read()
    clash = {n: sorted(f) for n, f in _declared().items() if len(f) > 1 and not _stub(app, n)}
    assert not clash, f"two scripts declare one global name, so the later replaces the earlier: {clash}"


def test_the_check_sees_a_clash_when_there_is_one():
    seen = collections.defaultdict(set)
    for name, src in (("a.js", "function mbLoad() {\n}\n"), ("b.js", "async function mbLoad() {\n}\n")):
        for m in DECL.finditer(src):
            seen[m.group(1) or m.group(2)].add(name)
    assert seen["mbLoad"] == {"a.js", "b.js"}


def test_the_strip_keeps_its_own_names():
    chat = open(os.path.join(JS, "chat.js"), encoding="utf-8").read()
    assert "async function lvmLoad(" in chat and "function mbLoad(" not in chat


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
