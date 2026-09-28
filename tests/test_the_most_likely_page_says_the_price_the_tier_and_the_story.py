"""The Most Likely page, five changes (Ethan, 2026-09-28: "Is there any way
too make this page any better?" … "Do them all"):

1. The controls in one pinned strip; on a phone the lede and the first
   explainer pill step aside and the tier chips and view toggle share a row.
2. The price to take on every card: our chance as an American price.
3. "Same story as …" on picks that ride together — same team, same side,
   same half of the offence.
4. The tier in words under the ring.
5. The record check says what it counts ("too new (9 of 20)").

Run directly: `python3 tests/test_the_most_likely_page_says_the_price_the_tier_and_the_story.py`
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


def _node(prog):
    path = os.path.join(tempfile.mkdtemp(), "t.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    return json.loads(subprocess.run(["node", path], capture_output=True, text=True, check=True).stdout)


def test_the_price_to_take():
    if not shutil.which("node"):
        return
    prog = ("const american = (o) => (o > 0 ? `+${o}` : `−${Math.abs(o)}`); const escapeAttr = (s) => s;\n"
            + _fn("obFairAmerican") + _fn("obImplied") + _fn("obPriceHTML")
            + "\nconsole.log(JSON.stringify([obFairAmerican(0.55), obFairAmerican(0.43), obFairAmerican(0.5),"
              " obPriceHTML({model_prob: 0.55, odds: -130}), obPriceHTML({model_prob: 0.61, odds: -125}),"
              " obPriceHTML({model_prob: 0.43, odds: 110}), obPriceHTML({model_prob: 0.6})]));")
    f55, f43, f50, odunze, loveland, swift, none = _node(prog)
    assert (f55, f43, f50) == (-122, 133, -100)
    assert "take at −122 or better" in odunze and 'class="ob-fair wait"' in odunze
    assert "good price · fair −156" in loveland and 'class="ob-fair good"' in loveland
    assert "take at +133 or better" in swift, "a +110 touchdown at 43% needs +133"
    assert none == ""


def test_picks_that_ride_together():
    if not shutil.which("node"):
        return
    rows = [{"player": "Colston Loveland", "team": "CHI", "game": "PHI@CHI", "market": "receptions", "side": "UNDER"},
            {"player": "Colston Loveland", "team": "CHI", "game": "PHI@CHI", "market": "rec_yds", "side": "UNDER"},
            {"player": "Luther Burden III", "team": "CHI", "game": "PHI@CHI", "market": "receptions", "side": "UNDER"},
            {"player": "Rome Odunze", "team": "CHI", "game": "PHI@CHI", "market": "receptions", "side": "UNDER"},
            {"player": "D'Andre Swift", "team": "CHI", "game": "PHI@CHI", "market": "rec_yds", "side": "OVER"},
            {"player": "Kalif Raymond", "team": "CHI", "game": "PHI@CHI", "market": "receptions", "side": "OVER"},
            {"player": "Saquon Barkley", "team": "PHI", "game": "PHI@CHI", "market": "rush_yds", "side": "OVER"}]
    head = APP[APP.index("const OB_STORY"):APP.index("let _obStoryCache")]
    prog = ("const escapeAttr = (s) => s; const icon = () => ''; const teamName = (t) => ({CHI: 'Bears', PHI: 'Eagles'})[t];\n"
            f"const ROWS = {json.dumps(rows)}; const oneBoardRows = () => ROWS;\n" + head + "let _obStoryCache = null;\n"
            + _fn("obStoryKey") + _fn("obStories") + _fn("obStoryHTML")
            + "\nconsole.log(JSON.stringify(ROWS.map(obStoryHTML)));")
    out = _node(prog)
    assert "Same story as 2 others" in out[0] and "Rides with Luther Burden III, Rome Odunze" in out[0]
    assert "Bears’ passing game going under" in out[0]
    assert "Same story as 2 others" in out[2] and "Same story as 2 others" in out[3]
    assert "Same story as Raymond" in out[4], "the two overs ride together, apart from the unders"
    assert out[6] == "", "a lone run-game over has no story partner"


def test_the_card_carries_the_price_the_tier_and_the_story():
    card = _fn("obCardHTML")
    assert "${obStoryHTML(r)}" in card and "${obPriceHTML(r)}" in card
    assert 'escapeHtml(OB_TIER_WORD[r.tier] || "Worth a look")' in card
    assert 'const OB_TIER_WORD = { top: "Top pick", strong: "Strong", look: "Worth a look" };' in APP
    for sel in (".ob-fair.wait", ".ob-fair.good", ".ob-tierword.tier-top", ".ob-story", ".ob-ringcol"):
        assert sel in CSS, sel


def test_the_controls_scroll_with_the_page_and_a_phone_starts_on_the_picks():
    board = _fn("oneBoardHTML")
    assert '<div class="ob-sticky">' in board
    assert ".ob-sticky { position: static;" in CSS
    tail = CSS[CSS.rindex("THE MOST LIKELY PAGE, 2026-09-28"):]
    assert "position: sticky" not in tail, "the filters must not follow the page"
    tail = CSS[CSS.rindex("THE MOST LIKELY PAGE, 2026-09-28"):]
    assert ".ob-lede { display: none; }" in tail and ".ob-pills .ob-pill:first-child { display: none; }" in tail
    assert ".ob-bar { flex-wrap: nowrap; overflow-x: auto;" in tail


def test_the_record_check_says_what_it_counts():
    fn = _fn("obRecordLabel")
    assert "Record: too new (${s.n} of ${s.need})" in fn
    assert "Record: picks like it hit ${Math.round(s.rate * 100)}% of ${s.n}" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
