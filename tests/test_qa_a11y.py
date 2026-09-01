"""Every visible form control has an accessible name (QA audit, 2026-09-01).

Four inputs — bankroll, unit %, roster search, player search — had a
placeholder or a title and no name a screen reader announces. A
placeholder disappears the moment you type; a label does not.

Run directly: `python3 tests/test_qa_a11y.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_visible_input_in_the_shell_has_an_accessible_name():
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    missing = []
    for tag, attrs in re.findall(r'<(input|select|textarea)\b([^>]*)>', html):
        if 'type="hidden"' in attrs:
            continue
        idm = re.search(r'\bid="([^"]+)"', attrs)
        labelled = bool(idm and re.search(r'<label[^>]*for="%s"' % re.escape(idm.group(1)), html))
        wrapped = bool(idm and re.search(r'<label[^>]*>\s*<%s[^>]*id="%s"' % (tag, re.escape(idm.group(1))), html))
        if not (labelled or wrapped or "aria-label" in attrs or "aria-labelledby" in attrs):
            missing.append(idm.group(1) if idm else attrs[:50])
    assert not missing, missing


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
