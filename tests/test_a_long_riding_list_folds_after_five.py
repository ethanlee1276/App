"""A long list of riding bets folds after five rows.

Ethan, 2026-09-25, three screenshots of Home with 109 riding bets between
the edge box and everything under it: "maybe showing, like, five edge
bets, then condensing it to a menu with an arrow pointing down, showing to
click more and kind of fade it in ... I gotta scroll through so many edge
bets to get down to the other stuff."

`foldRowsHTML` (app.js) shows FOLD_AFTER rows and puts the rest behind a
<details> whose summary reads "Show N more", with a chevron that turns and
a body that fades in (styles.css .row-fold); nothing is removed, the crawl
still reads every row, and one extra row is not worth a fold. Used where
riding rows are drawn: the Home edge box, the Picks branch, the Tonight
deck.
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _fold(n):
    if not shutil.which("node"):
        return None
    prog = ("const FOLD_AFTER = 5;\n" + _fn("foldRowsHTML")
            + f"\nconsole.log(JSON.stringify(foldRowsHTML(Array.from({{length: {n}}}, (_, i) => '<r>' + i + '</r>'), {{what: 'riding'}})));")
    path = os.path.join(tempfile.mkdtemp(), "f.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    return json.loads(out.stdout)


def test_five_show_and_the_rest_fold_with_a_count():
    assert "const FOLD_AFTER = 5;" in APP
    got = _fold(9)
    if got is None:
        return
    head, tail = got.split("<details", 1)
    assert head.count("<r>") == 5 and tail.count("<r>") == 4, got
    assert "Show 4 more riding" in tail and "Show fewer" in tail and "row-fold-chev" in tail
    assert 'class="row-fold"' in tail and 'class="row-fold-body"' in tail


def test_a_short_list_and_one_extra_row_do_not_fold():
    for n in (3, 5, 6):
        got = _fold(n)
        if got is None:
            return
        assert "<details" not in got and got.count("<r>") == n, (n, got)


def test_every_riding_list_uses_it():
    assert APP.count('foldRowsHTML(ridden.map(ridingRow), { what: "riding" })') == 2, "Home edge box and the Picks branch"
    assert 'foldRowsHTML(riding.map(ridingRow), { what: "riding" })' in APP, "the Tonight deck"
    assert "ridden.map(ridingRow).join" not in APP and "riding.map(ridingRow).join" not in APP


def test_the_fold_is_styled_and_still_under_reduced_motion():
    i = CSS.index(".row-fold > summary")
    block = CSS[i:i + 1600]
    assert "var(--brand)" in block and "var(--dur-slow)" in block and "var(--ease-out)" in block
    assert ".row-fold[open] > summary .row-fold-chev" in block, "the chevron turns"
    assert "@keyframes rowFoldIn" in block and "opacity: 0" in block, "the rows fade in"
    assert "@media (prefers-reduced-motion: reduce) { .row-fold-body { animation: none; }" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
