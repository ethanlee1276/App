"""One token block per theme, fixed colours as tokens, shared percents
(audit V-24 / D-1..D-3, roadmap #50). No visual change.

Phase 5 left three bare `:root` blocks, two light blocks, raw hex in rules
and ~35 local percent helpers. On 2026-10-02 the blocks were merged; the
computed value of every custom property was compared before and after,
in both themes, at 390 and 1440 wide and at 1x and 2x density: no
difference. Pinned here so they do not drift apart again.

Run directly: `python3 tests/test_one_root_and_shared_percents.py`
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
NC = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

FIXED = ("--ink-on-gold", "--ink-warm", "--ink-neutral", "--qbot-ground",
         "--night", "--night-2", "--night-3", "--night-text")


def test_one_bare_root_and_one_light_block():
    assert len(re.findall(r"(?m)^:root \{", NC)) == 1, "a second bare :root crept back"
    assert len(re.findall(r'(?m)^:root\[data-theme="light"\] \{', NC)) == 1
    # Media-scoped overrides are the deliberate exceptions.
    assert "@media (min-resolution: 2dppx) {\n  :root { --hairline: 0.5px; }" in NC


def test_fixed_colours_are_the_same_in_both_themes():
    i = NC.index(":root {")
    dark = NC[i:NC.index("\n}", i)]
    j = NC.index(':root[data-theme="light"] {')
    light = NC[j:NC.index("\n}", j)]
    for tok in FIXED:
        assert re.search(rf"^\s*{tok}:\s*#[0-9A-F]{{6}};", dark, re.M), tok
        assert f"{tok}:" not in light, f"{tok} is re-themed; it was a fixed colour"


def test_no_rule_carries_those_colours_raw():
    rules = NC[NC.index("\n}", NC.index(":root {")):]
    for hexv in ("#1c1204", "#14120e", "#141414", "#0b0a08", "#070b16", "#08101f",
                 "#05060f", "#dfe4f5"):
        assert hexv not in rules.lower(), hexv


def test_the_shared_percents_and_no_exact_local_copy():
    for name in ("pctOr", "pct0", "pct0Or", "pctRound", "pctRoundOr", "pctRoundZ"):
        assert f"\nconst {name} = " in APP, name
    exact = re.compile(r"^[ \t]+const pct\w* = \(?(\w)\)? => \(?(?:\1 == null \? \"—\" : )?"
                       r"`\$\{(?:\(\1 \* 100\)\.toFixed\([01]\)|Math\.round\(\1 \* 100\))\}%`\)?;$", re.M)
    left = [m.group(0).strip() for m in exact.finditer(APP)]
    # Two stay local on purpose: node harnesses (test_your_own_account_health,
    # test_the_paywall_shows_the_one_record) run those functions standalone.
    assert len(left) == 2, left


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
