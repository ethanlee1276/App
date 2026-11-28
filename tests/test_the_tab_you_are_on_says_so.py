"""v5 motion: the tab you are on says so.

Ethan, 2026-09-22: "more animations and more design features … feel
like a real sportsbook app made by a real company." The phone's tab
bar marked the active tab with a colour and nothing else. Now its icon
lifts a hair and a dot lands under its label, both on the ladder's
--dur-base and the workhorse curve, both zeroed by the universal
reduced-motion block; the centre disc, already raised, keeps still;
the More tab counts as on while its sheet is open.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _phone():
    i = DECLS.index(".tb-item { display: flex; flex-direction: column;")
    start = DECLS.rfind("@media (max-width: 760px) {", 0, i)
    return DECLS[start:DECLS.index("\n}\n", i) + 3]


def test_the_active_tab_lifts_its_icon_and_lands_a_dot():
    p = _phone()
    assert ".tb-item > svg { transition: transform var(--dur-base) var(--ease-out); }" in p
    assert ".tb-item.active > svg { transform: translateY(-2px); }" in p
    i = p.index(".tb-item::after {")
    rule = p[i:p.index("}", i)]
    for piece in ('content: ""', "position: absolute", "width: 4px; height: 4px", "background: currentColor",
                  "transform: scale(0)", "transition: transform var(--dur-base) var(--ease-out)"):
        assert piece in rule, piece
    assert '.tb-item.active::after, .tb-item[aria-expanded="true"]::after { transform: scale(1); }' in p, \
        "the dot lands on the active tab, and on More while its sheet is open"
    assert ".tb-center::after { display: none; }" in p, "the raised disc keeps still"


def test_the_ride_is_the_ladders_and_stops_under_reduced_motion():
    p = _phone()
    for line in p.splitlines():
        if ".tb-item" in line and "transition:" in line:
            assert "var(--dur-base)" in line and "var(--ease-out)" in line, line
    assert re.search(r"\*,\s*\*::before", DECLS), "the universal reduced-motion block covers ::after too"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
