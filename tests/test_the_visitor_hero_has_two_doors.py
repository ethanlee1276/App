"""A visitor's first screen carries two buttons: the trial and the record.

Ethan's product audit, 2026-09-23, item 7: the homepage a stranger sees
should lead with the trial and the record. With the paywall on, that
page is the wall, and its hero said the right things but offered no
door until the plans far below.

The trial button goes TO THE PLAN CARD, never straight into checkout:
the card says "card required, becomes $X a month on day N" before the
click, and a hero button that skipped it would be the silent conversion
that card exists to refuse.
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


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_fn("pwHeroCtaHTML")}
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


def test_two_doors_the_trial_first_then_the_record():
    got = _node("""return { trial: pwHeroCtaHTML(3), none: pwHeroCtaHTML(0) };""")
    if got is None:
        print("  SKIP node not installed"); return
    for h in got.values():
        assert h.index('class="btn primary pw-cta-go"') < h.index('class="btn ghost pw-cta-rec" href="#record"')
        assert 'data-act="pwToPlans"' in h, "to the card with the fine print, not into checkout"
        assert "coStart" not in h
        assert ">See the record</a>" in h
    assert "Start 3 days free</button>" in got["trial"]
    assert "See the plans</button>" in got["none"] and "free" not in got["none"], \
        "no trial on offer, no trial promised"


def test_the_hero_carries_them_and_only_offers_the_trial_it_can_grant():
    body = APP[APP.index("function paywallHTML("):]
    body = body[:body.index("\n}\n")]
    hero = body[body.index('<section class="pw-hero">'):body.index("</section>", body.index('<section class="pw-hero">'))]
    assert "${pwHeroCtaHTML(trialOK ? trialDays : 0)}" in hero
    assert hero.index("pw-sub") < hero.index("pwHeroCtaHTML") < hero.index("pwResultsHTML(rec)"), \
        "the promise, the two doors, then the receipts"
    assert "const trialOK = trialDays > 0" in body, "the same eligibility the plan card reads"


def test_the_trial_button_scrolls_to_the_plans():
    go = APP[APP.index("window.pwToPlans = function () {"):]
    go = go[:go.index("};") + 2]
    assert 'document.querySelector(".pw-plans")' in go and "scrollIntoView(" in go
    assert ".pw-cta { display: flex; flex-wrap: wrap; gap: 10px;" in CSS
    assert ".pw-cta .btn { min-height: 44px;" in CSS, "a thumb-sized target"


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
