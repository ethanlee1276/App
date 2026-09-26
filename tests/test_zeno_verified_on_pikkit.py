"""Zeno's picks say where to verify them: his Pikkit page, everywhere.

Ethan, 2026-09-26: "here is the link to my pikkit page we users can use it
to verrify my charts and picks and record and we need to plaster
everywhere that all picks are verified on pikkit."

EVERYWHERE HIS RECORD OR BETS ARE: his tile on the record strip (Record,
Home, the landing page), his page, the Record page's Zeno card, the Home
Zeno strip, the paywall's feature card and its "Don't take our word for
it" box, and the page's subtitle. ONLY THERE: the model's picks are not
bets at a book, so they are not on Pikkit — they are verified by this
site's own timestamped, graded record, and the model's tile never claims
otherwise.
"""
import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
URL = "https://links.pikkit.com/user/QellysBook"


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_the_link_is_his_and_opens_safely():
    assert f'const PIKKIT_URL = "{URL}";' in APP
    badge = _fn("pikkitBadgeHTML")
    assert 'href="${PIKKIT_URL}" target="_blank" rel="noopener noreferrer"' in badge
    assert "Zeno’s picks verified on Pikkit" in badge


def test_it_is_everywhere_his_record_is():
    assert 'pikkitBadgeHTML("check it on Pikkit")' in _fn("recordRibbonsHTML"), "his tile"
    assert 'pikkitBadgeHTML("Every Zeno pick is verified on Pikkit")' in APP[APP.index("async function renderZeno("):]
    assert "pikkitBadgeHTML()" in _fn("recZenoSection"), "the Record page's card"
    deck = APP[APP.index("async function deckRecordHTML("):APP.index("\n}\n", APP.index("async function deckRecordHTML("))]
    assert deck.count("pikkitBadgeHTML()") == 2, "the Home strip, open or locked"
    assert "posted as he places them — verified on Pikkit" in APP, "the plan line"
    assert "Every one is verified on Pikkit, synced from his sportsbooks" in APP, "the feature card"
    assert "Every Zeno pick is verified on Pikkit." in APP and "Zeno’s record on Pikkit &#8599;" in APP, "the proof box"
    assert "every one verified on Pikkit" in HTML, "his page's subtitle"


def test_only_his_tile_carries_it_never_the_models_or_a_readers():
    if not shutil.which("node"):
        return
    prog = ('const MINUS="\\u2212"; const escapeHtml=(x)=>String(x==null?"":x); const iconMark=()=>"";\n'
            f'const PIKKIT_URL="{URL}";\n' + _fn("pikkitBadgeHTML") + _fn("zenoMoney") + _fn("recordRibbonsHTML")
            + "\nconst z={overall:{settled:1389,wins:221,losses:1141,pushes:27,profit:8001.64,roi:0.2607,staked:30692.9,net_units:800.16}};"
            "\nconsole.log(JSON.stringify({zeno: recordRibbonsHTML({zeno:z},{},[]),"
            " model: recordRibbonsHTML({}, {settled:10,wins:6,losses:4,roi:0.05,net_units:0.5}, []),"
            " you: recordRibbonsHTML({zeno:{...z, label:'You · logged by hand'}},{},[])}));")
    path = os.path.join(tempfile.mkdtemp(), "p.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    got = json.loads(subprocess.run(["node", path], capture_output=True, text=True, check=True).stdout)
    assert URL in got["zeno"] and "verified on Pikkit" in got["zeno"]
    assert "Pikkit" not in got["model"], "the model's picks are not on Pikkit and never say so"
    assert "Pikkit" not in got["you"], "a reader's own book is not his"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
