"""A Most Likely row says how likely in a word, under its number.

Ethan's product audit, 2026-09-23, item 9: "A user should never have to
figure out: 'Is 64% good?'" — with bands at 52, 58, 63 and 68.

What this file holds:

  * THE BANDS ARE THE AUDIT'S, read off the rounded percent the row
    prints, so the word can never disagree with the number beside it.
  * THE WORDS ARE NOT: Lean and Play are already the edge board's grades
    (on net edge — `gradeClass`), and Premium reads as a price plan. One
    word meaning two things on two boards is the audit's own item 18.
  * MOST LIKELY ONLY. The edge board gets no tier: its edge ranks no
    better than a coin flip on the site's own test.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_fn("probTier")}
      {_fn("probTierHTML")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_word_follows_the_percent_the_row_prints():
    got = _node("""
      const w = (p) => (probTier(p) || { word: null }).word;
      const ps = [0.514, 0.515, 0.52, 0.574, 0.58, 0.62, 0.624, 0.625, 0.674, 0.675, 0.72, 0.95];
      return { words: ps.map(w), shown: ps.map((p) => Number((p * 100).toFixed(0))),   // the row's own rounding
               bad: [w(null), w(undefined), w("x"), w(0.3)] };""")
    if got is None:
        print("  SKIP node not installed"); return
    pairs = list(zip(got["shown"], got["words"]))
    assert pairs == [(51, None), (52, "Slight"), (52, "Slight"), (57, "Slight"), (58, "Solid"),
                     (62, "Solid"), (62, "Solid"), (63, "Strong"), (67, "Strong"), (68, "Top"),
                     (72, "Top"), (95, "Top")], pairs
    assert got["bad"] == [None, None, None, None], "no number, no word"


def test_no_word_collides_with_the_edge_boards_grades():
    got = _node("""return [0.55, 0.60, 0.65, 0.70].map((p) => probTier(p).word);""")
    if got is None:
        print("  SKIP node not installed"); return
    grades = re.search(r"const gradeClass = \(g\) => \(\{(.*?)\}\[g\]", APP, re.S).group(1)
    grade_words = set(re.findall(r'"([A-Za-z+ ]+)":', grades))
    assert {"Lean", "Play", "Strong Play", "Pass"} <= grade_words
    assert not set(got) & grade_words, "one word, two meanings, two boards"
    assert "Premium" not in got, "reads as a price plan"


def test_the_word_sits_in_the_pill_and_explains_itself():
    got = _node("""
      return { strong: probTierHTML({ model_prob: 0.64 }),
               unranked: probTierHTML({ model_prob: 0.64, ranked: false }),
               none: probTierHTML({}), nil: probTierHTML(null) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["strong"].startswith('<i class="ml-tier t-strong" title="Strong: 63–67% by the figure this row')
    assert "How likely, not how good the price is" in got["strong"]
    assert got["strong"].endswith(">Strong</i>")
    assert got["unranked"] == "", "a lean row already says lean"
    assert got["none"] == "" and got["nil"] == ""


def test_the_most_likely_rows_and_cards_carry_it_and_nothing_else_does():
    row = _fn("likelyRow")
    assert '<span class="ml-pct hd-p">${pct}${probTierHTML(r)}</span>' in row
    card = _fn("likelyCard")
    assert '<span class="grade lk-pct">${pct(r.model_prob)}${probTierHTML(r)}</span>' in card
    calls = [m.start() for m in re.finditer(r"(?<!function )probTierHTML\(r\)", _strip(APP))]
    assert len(calls) == 2, "the likely row and the likely card — no edge row, no scanner"
    # Defined once; read by probTierHTML (the row and the card) and by the
    # pick page as the Most Likely board opens it — its head and its "Why
    # it's likely" card (2026-09-23), which is that board's surface too.
    assert _strip(APP).count("probTier(") == 4, "defined once, read by the likely surfaces only"
    page = APP[APP.index("function renderPropPage()"):APP.index("function invNorm(")]
    assert "const tier = lk ? probTier(lk.model_prob) : null;" in page
    why = _fn("whyLikelyHTML")
    assert "const t = probTier(p);" in why


def test_the_word_is_styled_under_the_number():
    assert ".ml-pct, .lk-pct { display: inline-flex; flex-direction: column; align-items: center;" in CSS
    rule = CSS[CSS.index(".ml-tier {"):CSS.index("}", CSS.index(".ml-tier {"))]
    assert "text-transform: uppercase" in rule and "font-size: var(--fs-2xs)" in rule
    assert ".ml-tier.t-slight { color: var(--text-mute); opacity: 1; }" in CSS, \
        "the weakest band is the quietest"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
