"""Every control names an action the page has; no control carries code.

The site audit, 2026-09-24 (M-4). The content policy allowed inline script
because ninety-three controls carried their code in `onclick=` (and
`onchange=`, `onkeydown=`, an image's `onload=`/`onerror=`). They now name
an action — `data-act`, `data-change`, `data-key`, `data-onload`,
`data-onerr` — and one listener per event runs it from a list (app.js
`ACTS`/`CHANGES`/`KEYS`, visuals.js `IMG_ERR`). The policy refuses inline
script (tests/test_public_server.py holds that and the no-handler rule).

What this file holds is the failure the change could introduce: a control
naming an action that is not on the list does nothing, silently — the
same shape as the `renderCards` call the same audit found. So every name
used is registered, and every registered action calls something that
exists.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
#: The pages app.js loads on first use, whose actions it registers (2026-10-24).
LAZY = (ROOT / "web" / "js" / "memes.js").read_text(encoding="utf-8")
VIS = (ROOT / "web" / "js" / "visuals.js").read_text(encoding="utf-8")
PAGES = APP + VIS + (ROOT / "web" / "index.html").read_text(encoding="utf-8")
#: Every page module too (2026-10-25): the sign-up screen moved to
#: js/account.js with a "Look around first" button whose action was never
#: registered, and the scan above read app.js alone, so nothing said so.
ROOMS = "".join(f.read_text(encoding="utf-8") for f in sorted((ROOT / "web" / "js").glob("*.js"))
                if f.name not in ("app.js", "visuals.js"))


def _table(src, name):
    i = src.index(f"const {name} = {{")
    body = src[i:src.index("\n};", i)]
    return body, set(re.findall(r"^  (\w+): ", body, re.M))


def test_every_named_action_is_registered():
    for attr, (src, table) in {"data-act": (APP, "ACTS"), "data-change": (APP, "CHANGES"),
                               "data-key": (APP, "KEYS"), "data-onerr": (VIS, "IMG_ERR")}.items():
        _, names = _table(src, table)
        used = set(re.findall(rf'{attr}="(\w+)"', PAGES + (ROOMS if attr == "data-act" else "")))
        assert used, attr
        missing = used - names
        assert not missing, f"{attr} names nothing: {sorted(missing)}"
    # The avatar's error action is chosen in code; both choices exist.
    assert 'const swap = small === opts.headshot ? "remove" : "swapFull";' in VIS
    assert set(re.findall(r'data-onload="([\w-]+)"', PAGES)) <= {"art-on", "vp-on"}


def test_every_registered_action_calls_something_that_exists():
    body, names = _table(APP, "ACTS")
    called, acts_of = set(), {}
    for line in body.splitlines():
        act = re.match(r"^  (\w+): ", line)
        here = {fn for fn in re.findall(r"(?<![.\w])(\w+)\(", line) if fn not in {"if", "return", "e", "el"}}
        here |= set(re.findall(r"window\.(\w+)\(", line))
        called |= here
        for fn in here:
            if act:
                acts_of.setdefault(fn, set()).add(act.group(1))
    files = {f.name: f.read_text(encoding="utf-8") for f in sorted((ROOT / "web" / "js").glob("*.js"))
             if f.name not in ("app.js", "visuals.js")}
    for fn in sorted(called):
        pat = rf"(?:function {fn}\(|window\.{fn} = |const {fn} = |let {fn} = )"
        if re.search(pat, APP + VIS + LAZY):
            continue
        # A page's own file may hold an action's function (2026-11-18: the profit calendar moved to
        # js/record.js) when only that file draws the controls that name it: the function is there
        # whenever its button is.
        homes = {name for name, src in files.items() if re.search(pat, src)}
        assert homes, f"ACTS calls {fn}, which is defined nowhere"
        for act in acts_of.get(fn, ()):
            drawn = {name for name, src in files.items() if f'data-act="{act}"' in src}
            assert f'data-act="{act}"' not in PAGES and drawn <= homes, \
                f"{act} is drawn by {sorted(drawn - homes) or 'app.js'}, but {fn} lives in {sorted(homes)}"


def test_one_listener_per_event_and_the_images_are_caught_in_capture():
    assert 'document.addEventListener("click", (e) => _runAct(ACTS, "data-act", e));' in APP
    assert 'document.addEventListener("change", (e) => _runAct(CHANGES, "data-change", e));' in APP
    assert 'document.addEventListener("keydown", (e) => _runAct(KEYS, "data-key", e));' in APP
    i = VIS.index('document.addEventListener("error"')
    assert "}, true);" in VIS[i:i + 300], "error does not bubble; only a capture listener sees it"
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert html.index("js/boot.js") < html.index("</head>"), "the pre-paint flag still runs before paint"


if __name__ == "__main__":
    import sys
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
