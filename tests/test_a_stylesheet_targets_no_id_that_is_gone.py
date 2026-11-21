"""Every id our stylesheets target is an id something still renders.

Found by the nightly sweep on 2026-11-12, two at once, and they are the
two halves of the same defect:

  * `#slip-send-slot .fr-note` — the send slot's element and all five of
    its JS readers went out with Parlay Mode and the slip (50709a15,
    2026-10-31). The selector stayed, sharing a rule with the live
    `.fr-send .fr-note`, so the rule kept working and the dead half of
    it kept parsing.
  * `#preseason-board { scroll-margin-top: 76px }` — the element went
    out with the NFL preseason surface (ddb8f850, 2026-08-25).
    tests/test_preseason_retired.py pinned the removal carefully: the
    block, the renderers, the fetch, the launcher, the gate. It did not
    pin the CSS, because nobody thinks of a stylesheet as part of a
    surface, and an orphaned scroll-margin-top has no symptom whatever.

WHY AN ID AND NOT A CLASS. The repo already learned the class version of
this lesson twice — `.sb-foot-links` outliving the footer
(test_touchtargets.py) and `.stat-v` outliving the stat (test_number_type
.py) — and both times the fix was a named assertion about the one dead
selector, which cannot catch the next one. The reason it stayed named is
that classes are routinely BUILT: `"xb-c" + i`, `"tier-" + tier`,
`"tone-" + (n < 0 ? "neg" : "pos")`. A sweep over class names reports a
hundred live classes as dead and teaches you to ignore it.

Ids are not built that way here — they are written whole, in markup or
in a `getElementById`, which is what makes enumeration possible for ids
and not for classes. So this file does the enumerable half properly:
every id in a selector in every stylesheet we wrote, required to appear
somewhere that renders or queries it. If a future id IS constructed, it
belongs in CONSTRUCTED below with the line that builds it, not in a
loosened search.

Source-level and store-free, like the rest of the CSS hygiene checks:
the verdict must not depend on whether the machine running it has a
built slate, a database or a network. web/data/ is gitignored, so
walking it would make this pass on the laptop and fail in a clone, which
is the bug class this suite has been bitten by three times.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Same two exclusions the other CSS walks use, for the same reasons:
# web/data/ is build output and gitignored; web/vendor/ is shipped as
# downloaded, and apexcharts' own ids are not ours to account for.
_SKIP = ("data", "vendor")

# Ids a stylesheet targets that are assembled at runtime rather than
# written whole. Empty today. Add an entry as `id: "where it is built"`
# rather than relaxing the search — the point of the check is that the
# list of exceptions is readable.
CONSTRUCTED: dict = {}


def _css_files():
    out = []
    for base, dirs, files in os.walk(os.path.join(ROOT, "web")):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for name in sorted(files):
            if name.endswith(".css"):
                out.append(os.path.join(base, name))
    return out


def _rendering_files():
    """Everywhere an id can be written: the pages, the page code, the
    manifests, and the Python that serves or emits markup."""
    out = []
    for base, dirs, files in os.walk(os.path.join(ROOT, "web")):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for name in sorted(files):
            if name.endswith((".html", ".js", ".json", ".webmanifest")):
                out.append(os.path.join(base, name))
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py"):
            out.append(os.path.join(ROOT, name))
    for base, _dirs, files in os.walk(os.path.join(ROOT, "engine")):
        for name in sorted(files):
            if name.endswith(".py"):
                out.append(os.path.join(base, name))
    return out


def _blank_comments(css):
    """Drop comment bodies, keeping the line count so a failure names a
    line you can open. A selector quoted in a comment is prose."""
    return re.sub(r"/\*.*?\*/",
                  lambda m: "\n" * m.group(0).count("\n"), css, flags=re.S)


# The text before each `{`, which is where a selector lives. Skips
# at-rules (@media, @supports) and declarations.
_RULE = re.compile(r"(?:^|[}\n])\s*([^{}@;/][^{}@;]*?)\s*\{")
_ID = re.compile(r"#(-?[_a-zA-Z][\w-]*)")


def _ids_in_stylesheets():
    found = []
    for path in _css_files():
        raw = open(path, encoding="utf-8").read()
        body = _blank_comments(raw)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        for m in _RULE.finditer(body):
            selector = m.group(1)
            line = body[:m.start(1)].count("\n") + 1
            for name in sorted(set(_ID.findall(selector))):
                found.append((name, rel, line, " ".join(selector.split())))
    return found


def test_every_id_a_stylesheet_targets_is_one_something_renders():
    haystack = "\n".join(
        open(p, encoding="utf-8", errors="ignore").read()
        for p in _rendering_files())
    dead = []
    for name, rel, line, selector in _ids_in_stylesheets():
        if name in CONSTRUCTED:
            continue
        # Bounded on both sides, so `#pm-title` is not called live by
        # `pm-d-title` — the rename that caused the tap-target defect
        # test_touchtargets.py was written for.
        if not re.search(r'["\'`\s=]' + re.escape(name)
                         + r'["\'`\s<>,.:)\]]', haystack):
            dead.append(f"{rel}:{line}  #{name}  in  {selector}")
    assert not dead, (
        "a stylesheet targets an id nothing renders — the rule is dead "
        "and silent:\n  " + "\n  ".join(dead))


def test_the_two_retirements_that_left_css_behind_stay_gone():
    """The specific pair, named so the enumeration above cannot be
    'simplified' into passing. Both elements are already pinned as gone
    by their own files; this pins the stylesheet half."""
    css = "\n".join(open(p, encoding="utf-8").read() for p in _css_files())
    assert "#slip-send-slot" not in css, \
        "the retired slip send slot has a rule again"
    assert "#preseason-board" not in _blank_comments(css), \
        "the retired preseason anchor has a rule again"


def test_the_walk_reads_every_stylesheet_and_finds_real_ids():
    """The check above is only as good as its two walks, and both are
    walks that silently return whatever they find: if the CSS walk
    returned nothing, or the rendering walk returned everything, the
    test would pass green and blind. Pin that both have substance and
    that the enumeration agrees with a walk done independently."""
    sheets = {os.path.relpath(p, ROOT).replace(os.sep, "/")
              for p in _css_files()}
    ours = set()
    for base, dirs, files in os.walk(os.path.join(ROOT, "web")):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for name in files:
            if name.endswith(".css"):
                rel = os.path.relpath(os.path.join(base, name), ROOT)
                ours.add(rel.replace(os.sep, "/"))
    assert sheets == ours, "the CSS walk and a plain walk disagree"
    assert "web/css/styles.css" in sheets

    # _RULE reads only the text before a `{`, so a selector it fails to
    # recognise disappears from the check with no symptom. Cross it
    # against a scan that cannot miss one — every `#name` anywhere in the
    # stylesheets, minus the hex colours, which is the only other thing
    # `#` introduces in CSS. The two agree at 45 ids today.
    ids = {name for name, _r, _l, _s in _ids_in_stylesheets()}
    hexish = re.compile(r"^[0-9a-fA-F]{3,8}$")
    everywhere = set()
    for path in _css_files():
        everywhere.update(_ID.findall(
            _blank_comments(open(path, encoding="utf-8").read())))
    named = {i for i in everywhere if not hexish.match(i)}
    assert not named - ids, (
        "_RULE missed a selector; these ids are styled and unchecked: "
        + ", ".join(sorted(named - ids)))
    assert not ids - named, (
        "an id reads as a hex colour (#faded and the like), so the filter "
        "above would hide it: " + ", ".join(sorted(ids - named)))
    assert len(ids) > 30, \
        f"only {len(ids)} ids found in the stylesheets — is _RULE broken?"
    # Live ids, each written whole in markup or queried by name.
    for live in ("cards", "view-pbp", "cc-overlay"):
        assert live in ids, f"#{live} is styled but the walk missed it"

    rendering = {os.path.relpath(p, ROOT).replace(os.sep, "/")
                 for p in _rendering_files()}
    for needed in ("web/index.html", "web/js/app.js", "server.py"):
        assert needed in rendering, f"{needed} is not searched for ids"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    # run_tests.py reads the count off this line; a file without it
    # scores zero and is still drawn green (test_touchtargets.py).
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
