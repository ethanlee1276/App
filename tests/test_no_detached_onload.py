"""An image that loads after its card was replaced must not crash the page.

Ethan, 2026-08-25, and again 2026-09-08 with a screenshot of the MLB
home page: "Sorry — part of this page failed to draw. Anything that
looks empty below may not be empty; it may be this. (TypeError: null is
not an object (evaluating 'this.parentNode.classList'))"

THE MECHANISM. An `<img onload=...>` handler is asynchronous, and this
site re-renders whole containers — the thirty-second refresh, a sport
switch, the deferred second half of the MLB board. A photo that
finishes loading after its card was replaced fires `onload` on a
DETACHED node. `parentNode` is null, `null.classList` throws, and the
global handler in `crashNote` reports it — correctly, since it cannot
know the throw came from a corpse's callback rather than from a render.
So the reader is told the page failed to draw while looking at a page
that drew perfectly.

WHY IT CAME BACK. The 2026-08-25 fix guarded the two `onload` sites in
app.js and never reached the three in visuals.js. Those three are on
every team logo, every league mark and every player headshot — which is
to say on every card of every board — so the banner returned on the next
screenshot. Guarding three more call sites by hand would leave the same
trap set for the fourth.

So the guard lives in ONE place now, `visuals.artOn`, and this file
holds two things: that the helper is actually guarded, and that no
inline handler anywhere in our own JavaScript reaches for `parentNode`
on its own again.

Run directly: `python3 tests/test_no_detached_onload.py`
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def _our_sources():
    """Every file we WROTE that can carry an inline handler.

    `web/vendor/` is excluded on purpose: those are third-party bundles
    we do not edit, and holding them to our rule would only teach the
    next reader to add exceptions until the check means nothing.
    """
    out = []
    js = os.path.join(WEB, "js")
    for name in sorted(os.listdir(js)):
        if name.endswith(".js"):
            out.append(os.path.join(js, name))
    for name in sorted(os.listdir(WEB)):
        if name.endswith(".html"):
            out.append(os.path.join(WEB, name))
    return out


#: An inline handler attribute (`onload="..."`, `onerror='...'`) whose
#: body mentions `parentNode`. The attribute form is what matters: these
#: run with `this` bound to an element that may already be off the page.
INLINE_PARENT = re.compile(r"""on[a-z]+\s*=\s*(["'])((?:(?!\1).)*parentNode(?:(?!\1).)*)\1""")


def test_no_inline_handler_reaches_for_its_parent():
    """The rule, enforced on the source rather than on three call sites.

    A per-site guard is only as good as the next person remembering to
    write it, and the record says that does not happen: the same defect
    shipped twice, the second time at five sites of which three were
    missed. `artOn` is the one place allowed to touch a parent, so an
    inline handler that names `parentNode` at all is the smell.
    """
    bad = []
    for path in _our_sources():
        src = open(path, encoding="utf-8").read()
        for m in INLINE_PARENT.finditer(src):
            line = src[:m.start()].count("\n") + 1
            bad.append(f"{os.path.relpath(path, ROOT)}:{line}  {m.group(2)[:70]}")
    assert not bad, (
        "an inline handler dereferences parentNode; call artOn(this, cls) "
        "instead — it is guarded, these are not:\n  " + "\n  ".join(bad))


def test_every_onload_that_adds_a_class_goes_through_the_helper():
    """The positive half of the rule. The check above would also pass on
    a file that stopped adding the class at all, which would put the
    drawn fallback back underneath every real photo."""
    seen = 0
    for path in _our_sources():
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(r"""onload\s*=\s*(["'])((?:(?!\1).)*)\1""", src):
            body = m.group(2)
            if "classList" in body or "artOn(" in body:
                seen += 1
                assert body.strip().startswith("artOn("), \
                    f"{os.path.relpath(path, ROOT)}: {body[:70]}"
    assert seen >= 5, f"the onload sites went missing entirely ({seen} found)"


def test_the_helper_is_defined_before_the_page_that_uses_it_loads():
    """`artOn` lives in visuals.js and app.js's handlers call it, so the
    order in index.html is load-bearing."""
    html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    v = html.index("js/visuals.js")
    a = html.index("js/app.js")
    assert v < a, "app.js loads before the file that defines artOn"


# --- and the helper actually survives a detached node -----------------------
def _node(js):
    """Run `artOn` in node against a stub DOM, or skip where node is not
    installed (the same doctrine as the other JS tests here)."""
    node = shutil.which("node")
    if not node:
        return None
    src = open(os.path.join(WEB, "js", "visuals.js"), encoding="utf-8").read()
    i = src.index("function artOn(")
    fn = src[i:src.index("\n}", i) + 2]
    prog = "%s\nconsole.log(JSON.stringify((() => { %s })()));" % (fn, js)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True,
                             timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_detached_image_does_not_throw():
    """THE CRASH ETHAN SCREENSHOTTED, reproduced and then not thrown.

    A node whose card was replaced has `parentNode === null`. The old
    code read `.classList` off that and the page apologised for itself.
    """
    got = _node("""
      const added = [];
      const parent = { classList: { add: (c) => added.push(c) } };
      let threw = null;
      try { artOn({ parentNode: null }, 'art-on'); } catch (e) { threw = String(e); }
      let threwNull = null;
      try { artOn(null, 'art-on'); } catch (e) { threwNull = String(e); }
      // …and a node still on the page is marked exactly as before.
      artOn({ parentNode: parent }, 'art-on');
      return { threw, threwNull, added };
    """)
    if got is None:
        return                       # node absent: the source checks stand
    assert got["threw"] is None, got["threw"]
    assert got["threwNull"] is None, got["threwNull"]
    assert got["added"] == ["art-on"], got["added"]


def test_a_parent_that_is_not_an_element_is_also_survived():
    """A fragment has a parentNode but no classList. Cheap to guard and
    the kind of thing that only shows up in someone's browser."""
    got = _node("""
      let threw = null;
      try { artOn({ parentNode: {} }, 'art-on'); } catch (e) { threw = String(e); }
      return { threw };
    """)
    if got is None:
        return
    assert got["threw"] is None, got["threw"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
