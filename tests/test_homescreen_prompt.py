"""The "add this to your home screen" sheet.

Ethan, 2026-08-21: *"we also need to add a little popup on the moible site
only after someone logs into there account that tells them too add
qellysbook to there homescreen so its like a real app."*

Everything it needs was already shipped — manifest, icons, service worker,
`apple-mobile-web-app-capable`, safe-area insets. What was missing was
anybody ever mentioning it.

THREE BROWSERS, THREE HONEST ANSWERS. Android/Chrome fires
`beforeinstallprompt`, so there is a button that really installs. iOS
Safari has no such event and never will, so it gets told exactly which two
taps to make. Anything else gets pointed at its own menu. Drawing an
install button that cannot install on iOS would be the easy version and
a lie.

AND IT ASKS ONCE. Dismissed is remembered. Already installed, it never
appears. Neither of those is politeness — a prompt that reappears is a
prompt people learn to close without reading, which costs the install it
was asking for.

    python3 tests/test_homescreen_prompt.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "js", "app.js")
CSS = os.path.join(ROOT, "web", "css", "styles.css")


def _src():
    return open(APP, encoding="utf-8").read()


def _code():
    s = re.sub(r"/\*.*?\*/", " ", _src(), flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", s)


def _fn(src, name):
    m = re.search(r"(?:function %s\s*\(|%s\s*=\s*(?:async\s+)?function\s*\()"
                  % (name, re.escape(name)), src)
    assert m, name + " is not in app.js"
    # Step over the parameter list first: `say = () => {}` is a default
    # value containing braces, and starting the brace match at the first
    # `{` after the name lands one character into the signature.
    depth, i = 0, src.index("(", m.end() - 1)
    for j in range(i, len(src)):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                i = src.index("{", j)
                break
    depth, seen = 0, False
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
            seen = True
        elif src[j] == "}":
            depth -= 1
            if seen and depth == 0:
                return src[m.start():j + 1]
    raise AssertionError(name + " never closes")


# --- when it appears --------------------------------------------------------
def test_it_is_armed_by_signing_in():
    code = _code()
    auth = code[code.index("acctAuth = async function"):]
    auth = auth[:auth.index("\n};")]
    assert "a2hsArm()" in auth, (
        'Ethan asked for it "after someone logs into there account" and '
        "nothing arms it there")


def test_signing_in_arms_it_whether_or_not_the_account_is_new():
    """A returning customer on a new phone is exactly who wants this, and
    they never sign up again."""
    code = _code()
    auth = code[code.index("acctAuth = async function"):]
    auth = auth[:auth.index("\n};")]
    i = auth.index("a2hsArm()")
    before = auth[max(0, i - 200):i]
    assert 'mode === "signup"' not in before.split("\n")[-1], (
        "arming is gated on sign-up, so signing in never offers it")


def test_it_is_spent_on_both_landings():
    """The entitled sign-in RELOADS. Armed on one page load, it has to be
    picked up on the next, or the one person who paid never sees it."""
    code = _code()
    assert "a2hsTick()" in _fn(code, "acctLandAfterAuth"), (
        "the in-place landing never shows it")
    boot = code[code.rindex("paidReturnWait()"):]
    assert "a2hsTick()" in boot[:1200], (
        "the reloading landing never shows it")


# --- when it does not -------------------------------------------------------
def test_it_never_appears_on_a_desktop():
    """Ethan: "on the moible site only". A narrow desktop window is not a
    phone and has no home screen to add anything to — the coarse-pointer
    test is what tells a finger from a mouse."""
    body = _fn(_code(), "a2hsMobile")
    assert "pointer: coarse" in body, (
        "width alone, so a dragged-narrow desktop window gets it")
    assert "max-width" in body


def test_it_never_appears_when_it_is_already_installed():
    body = _fn(_code(), "a2hsInstalled")
    assert "display-mode: standalone" in body, "Android/Chrome unhandled"
    assert "navigator.standalone" in body, (
        "iOS unhandled — it does not implement display-mode for this")
    tick = _fn(_code(), "a2hsTick")
    assert "a2hsInstalled()" in tick


def test_a_no_is_remembered():
    tick = _fn(_code(), "a2hsTick")
    assert "A2HS_KEY" in tick
    dismiss = _fn(_code(), "a2hsDismiss")
    assert "A2HS_KEY" in dismiss and '"off"' in dismiss, (
        "dismissing does not stick, so it comes back on the next sign-in")


def test_installing_it_also_stops_the_asking():
    code = _code()
    i = code.index('addEventListener("appinstalled"')
    assert "A2HS_KEY" in code[i:i + 250], (
        "somebody who installs it from the browser's own menu keeps being "
        "asked to")


def test_every_storage_access_is_guarded():
    """A private window throws on `localStorage`, and these run at boot
    and during sign-in. An uncaught throw in either place is a blank site
    or a sign-in that appears to fail."""
    code = _code()
    for m in re.finditer(r"localStorage\.\w+\(A2HS_", code):
        head = code[max(0, m.start() - 260):m.start()]
        assert "try {" in head, (
            "unguarded localStorage at offset %d" % m.start())


# --- what it says -----------------------------------------------------------
def test_ios_is_told_the_two_taps_and_not_given_a_dead_button():
    body = _fn(_code(), "a2hsHTML")
    assert "Add to Home Screen" in body and "Share" in body, (
        "iOS has no beforeinstallprompt; without the instructions the "
        "sheet asks for something it does not say how to do")
    assert "a2hsIOS()" in body


def test_the_real_install_button_only_exists_when_it_can_install():
    body = _fn(_code(), "a2hsHTML")
    assert "canInstall" in body
    i = body.index("canInstall")
    assert "a2hsInstall(this)" in body[i:], (
        "the install button is drawn outside the check that it works")


def test_the_captured_event_is_not_left_to_go_stale():
    """Chrome fires it once. Using it twice throws, and the second sheet
    would sit there doing nothing."""
    body = _fn(_code(), "a2hsInstall")
    assert "_a2hsEvent = null" in body


def test_the_prompt_is_captured_rather_than_left_to_chrome():
    code = _code()
    i = code.index('addEventListener("beforeinstallprompt"')
    head = code[i:i + 200]
    assert "preventDefault()" in head, (
        "without this Chrome shows its own mini-infobar and the event is "
        "gone by the time there is a reason to use it")


# --- the shell --------------------------------------------------------------
def test_it_does_not_cover_the_navigation():
    """A sheet that hides the tab bar while asking a favour is a sheet
    people close angrily."""
    css = open(CSS, encoding="utf-8").read()
    rule = css[css.index(".a2hs {"):]
    rule = rule[:rule.index("}")]
    assert "bottom:" in rule and "64px" in rule, (
        "the sheet sits on the bottom edge, over the tab bar")
    assert "safe-area-inset-bottom" in rule, (
        "on a notched phone this lands under the home indicator — the "
        "same class of bug as the topbar being cut off")


def test_it_clears_the_bottom_edge_on_a_walled_page_too():
    css = open(CSS, encoding="utf-8").read()
    assert "body.walled .a2hs" in css, (
        "the tab bar is hidden behind the wall, so the sheet floats above "
        "nothing")


def test_the_entrance_animates_nothing_that_costs_layout():
    css = open(CSS, encoding="utf-8").read()
    rule = css[css.index(".a2hs {"):]
    rule = rule[:rule.index("}")]
    m = re.search(r"transition:\s*([^;]+);", rule)
    assert m, "no transition at all"

    def _ms(text):
        """The duration in milliseconds, through the token if it is one.
        Durations are tokens here (tests/test_motion.py bans a bare `.22s`
        in a transition), so reading the literal would only ever measure
        the spelling."""
        tok = re.search(r"var\((--dur-[\w-]+)\)", text)
        if tok:
            d = re.search(r"%s:\s*([\d.]+)(ms|s)" % tok.group(1), css)
            assert d, "undefined duration token %s" % tok.group(1)
            return float(d.group(1)) * (1 if d.group(2) == "ms" else 1000)
        lit = re.search(r"([\d.]+)(ms|s)\b", text)
        return float(lit.group(1)) * (1 if lit.group(2) == "ms" else 1000) \
            if lit else 0.0

    for part in m.group(1).split(","):
        prop = part.strip().split()[0]
        assert prop in ("opacity", "transform"), (
            "%s is a layout property and janks on a phone" % prop)
        assert _ms(part) <= 300, part


def test_reduced_motion_is_respected():
    css = open(CSS, encoding="utf-8").read()
    i = css.index(".a2hs {")
    assert "prefers-reduced-motion" in css[i:i + 1400]


# --- the thing it is asking for has to work ---------------------------------
def test_the_site_is_actually_installable():
    """Asking somebody to install a page with no manifest wastes the one
    time they will say yes."""
    man = os.path.join(ROOT, "web", "manifest.webmanifest")
    assert os.path.exists(man)
    import json
    m = json.load(open(man, encoding="utf-8"))
    assert m.get("display") == "standalone"
    assert m.get("start_url") and m.get("icons")
    sizes = {i["sizes"] for i in m["icons"]}
    assert "192x192" in sizes and "512x512" in sizes, (
        "Chrome refuses to offer an install without both")
    for ic in m["icons"]:
        assert os.path.exists(os.path.join(ROOT, "web", ic["src"])), ic["src"]
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    assert 'rel="manifest"' in html
    assert "apple-mobile-web-app-capable" in html, (
        "iOS opens it in a Safari tab with the address bar, which is the "
        "one thing the sheet promises it will not do")


def test_the_icon_the_sheet_shows_is_one_that_exists():
    body = _fn(_code(), "a2hsHTML")
    m = re.search(r'src="/([\w.-]+)"', body)
    assert m, "the sheet shows no icon"
    assert os.path.exists(os.path.join(ROOT, "web", m.group(1))), m.group(1)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
