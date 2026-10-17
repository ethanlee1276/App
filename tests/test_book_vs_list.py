"""The sharp-book list is checked in public, executed rather than read.

`engine/booksharp.compare_to_the_list` describes itself as "the point of
the whole module": the ranking is interesting, but the question worth
asking is whether the hand-written sharp list — the one
`engine.odds.is_sharp_book` consults before we will quote a book as a
reference price — is backed by our own snapshots. It has shipped to the
browser in `bookreport.json.vs_list` on every build for weeks. No page
ever named the field, so the answer arrived in the browser and stopped
there. `engine/feedaudit.py` is what noticed.

Both halves run here, against each other. The producer is the real
Python function; the consumer is the real `bookVsListHTML` lifted out of
app.js and executed in Node. That pairing is deliberate: what actually
broke was a FIELD NAME contract, and a test that stubbed either side
would be checking my fixture rather than the wiring.

Four properties, in the order they matter:

  * a book we call sharp and that prices in the bottom half is NAMED —
    the only finding here that should change anybody's mind;
  * the line still renders when nothing is wrong, because a check that
    disappears when it passes is not believed when it fails;
  * below a floor it says the sample is thin instead of splitting a
    three-row table into halves;
  * and it survives a build older than the field.

Run directly: `python3 tests/test_book_vs_list.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if not shutil.which("node"):
    print("SKIP node is not installed; this file EXECUTES the renderer "
          "rather than reading it. `apt install -y nodejs`")
    print("\n0 tests passed.")
    raise SystemExit(0)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

_STUBS = """
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
"""


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("{", i)
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(f"{name} has unbalanced braces")


def _const(name):
    needle = f"const {name} = "
    assert needle in APP, f"{name} is gone from app.js"
    i = APP.index(needle)
    return APP[i:APP.index(";", i) + 1]


def render(vs):
    """The real renderer, on the real payload shape."""
    src = (_STUBS + _const("VS_MIN_BOOKS") + "\n"
           + "\n".join(_fn(n) for n in ("pluralWord", "plural",
                                        "bookVsListHTML"))
           + f"\nconsole.log(JSON.stringify(bookVsListHTML({json.dumps(vs)})));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def measured(*books):
    """`{book: {...}}` in the shape `measure()` returns, sharpest first.

    Only the two keys `compare_to_the_list` reads are filled, and they
    are read from it rather than invented here — `weight` is what makes
    a book ranked at all, `mae_pts` is what it is ranked ON.
    """
    return {b: {"weight": 1.0, "mae_pts": float(i)}
            for i, b in enumerate(books)}


def _vs(*books):
    from engine.booksharp import compare_to_the_list
    return compare_to_the_list(measured(*books))


# ------------------------------------------------- the finding that bites

def test_a_book_we_call_sharp_that_prices_badly_is_named():
    """The one finding on this line that should change somebody's mind.

    Pinnacle is on the hand-written list. Put it LAST of six and the
    page has to say so by name — this is the whole reason the block is
    not just "the list checks out" boilerplate.
    """
    vs = _vs("draftkings", "fanduel", "betmgm", "caesars", "espnbet",
             "pinnacle")
    assert vs["asserted_but_not"] == ["pinnacle"], vs
    out = render(vs)
    assert "pinnacle" in out, out
    assert "bottom half" in out
    assert "our own snapshots do not" in out
    # Singular verb for one book: "pinnacle prices in the bottom half".
    assert "prices in" in out and "price in" not in out.replace("prices in", "")
    assert "call it sharp" in out


def test_two_bad_books_read_as_a_sentence_not_as_a_shrug():
    """`SHARP_BOOKS` holds one name today and `is_sharp_book` matches it
    as a SUBSTRING, so a regional key is asserted-sharp too. That is the
    real predicate, and it is the only honest way to get two books into
    the bad list without inventing a second sharp book that the shop
    would not actually consult."""
    vs = _vs("draftkings", "fanduel", "betmgm", "caesars", "pinnacle",
             "pinnacle_us")
    assert vs["asserted_but_not"] == ["pinnacle", "pinnacle_us"], vs
    out = render(vs)
    assert "pinnacle, pinnacle_us" in out, out
    assert "price in" in out, "plural subject took the singular verb"
    assert "call them sharp" in out
    assert "(s)" not in out


# ------------------------------------------------- it speaks when it passes

def test_the_line_still_renders_when_the_list_checks_out():
    """A check nobody ever sees pass is a check nobody believes when it
    fails. Pinnacle sharpest of six: nothing is wrong, and the page says
    so rather than going blank."""
    vs = _vs("pinnacle", "draftkings", "fanduel", "betmgm", "caesars",
             "espnbet")
    assert not vs["asserted_but_not"], vs
    out = render(vs)
    assert out, "the block vanished on the passing case"
    assert "top half" in out
    assert "bottom half" not in out


def test_a_book_outside_the_list_in_the_measured_top_three_is_named():
    vs = _vs("draftkings", "pinnacle", "fanduel", "betmgm", "caesars")
    assert vs["sharp_but_unnamed"], vs
    out = render(vs)
    for book in vs["sharp_but_unnamed"]:
        assert book in out, (book, out)
    assert "not on that list" in out


# ------------------------------------------------- what it refuses to claim

def test_a_table_too_thin_to_halve_says_so_instead():
    """Three ranked books split into "halves" is one book and two, and
    calling the third one badly priced is a stronger claim than five
    snapshots can carry."""
    vs = _vs("pinnacle", "draftkings", "fanduel")
    out = render(vs)
    assert "too thin" in out, out
    assert "3 books" in out, out
    assert "bottom half" not in out and "top half" not in out


def test_a_build_older_than_the_field_renders_nothing():
    """The droplet serves whatever the last build wrote. A payload with
    no `vs_list` at all must not throw and must not print an empty
    claim."""
    for missing in (None, {}, {"n_ranked": 0}):
        assert render(missing) == "", missing


# ------------------------------------------------- the wiring itself

def test_the_card_actually_calls_it():
    """The defect was never in the arithmetic — it was that nothing on
    the page named the field. Assert the call, and assert it sits inside
    the card rather than somewhere the card never reaches."""
    i = APP.index('<div id="bookreport-card">')
    card = APP[i:APP.index("</div>`);", i)]
    assert "${bookVsListHTML(d.vs_list)}" in card, \
        "the card does not name vs_list, which is the bug this fixes"


def test_the_report_and_the_page_read_the_same_keys():
    """The contract that broke. Every key the renderer reads has to be a
    key the producer writes — checked against the real function's real
    output, not against a fixture I wrote to match."""
    vs = _vs("pinnacle", "draftkings", "fanduel", "betmgm", "caesars")
    body = _fn("bookVsListHTML")
    for key in ("n_ranked", "asserted_sharp", "asserted_but_not",
                "sharp_but_unnamed"):
        assert f"vs.{key}" in body, f"the page stopped reading {key}"
        assert key in vs, f"the build stopped writing {key}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
