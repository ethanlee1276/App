"""Feed text never becomes markup, and a feed URL is only ever an http(s) link.

Audit 2026-09-30, D-4 (roadmap #18). `teamName`, `nflName` and `teamNameIn`
returned the raw input when a code missed the team table, into `<strong>`,
`<b>` and subtitles — so an odd code in a feed was HTML. And a dozen links
took a feed's URL through escapeAttr only: that stops a quote breaking the
attribute, not a `javascript:` URL as the whole value. CSP blocks inline
script today; this does not lean on it.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _line(start):
    i = APP.index(start)
    return APP[i:APP.index("\n", i)]


def _node(src, expr):
    if not shutil.which("node"):
        return None
    p = os.path.join(tempfile.mkdtemp(), "x.js")
    Path(p).write_text(src + f"\nprocess.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", p], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    return json.loads(out.stdout)


def test_safe_href_passes_only_http_and_escapes_it():
    got = _node(_fn("safeHref"), "[" + ",".join([
        "safeHref('https://x.com/a?b=1&c=2')", "safeHref('http://x.com')",
        "safeHref('javascript:alert(1)')", "safeHref(' JavaScript:alert(1)')",
        "safeHref('data:text/html,<b>')", "safeHref('//evil.com')",
        "safeHref('https://x.com/\"onmouseover=\"x')", "safeHref(null)", "safeHref('')",
        "safeHref('vbscript:x')"]) + "]")
    if got is None:
        return
    assert got[0] == "https://x.com/a?b=1&amp;c=2"
    assert got[1] == "http://x.com"
    assert got[2:6] == ["#"] * 4
    assert "&quot;" in got[6] and '"' not in got[6]
    assert got[7:] == ["#"] * 3


def test_every_templated_href_goes_through_safe_href():
    # Ask's source chips check the scheme themselves, one line up
    # (askSourcesHTML: "Only an http(s) address becomes a link").
    left = [m.start() for m in re.finditer(r'href="\$\{(?:escapeAttr|escapeHtml)\(', APP)
            if "askSourcesHTML" not in APP[APP.rfind("\nfunction ", 0, m.start()):m.start()][:40]]
    assert not left, f"{len(left)} link(s) take a feed URL on trust"
    assert len(re.findall(r'href="\$\{safeHref\(', APP)) >= 11
    assert "/^https?:\\/\\//i.test(String(s.url" in _fn("askSourcesHTML")


def test_a_missed_team_code_is_text_not_markup():
    src = ("const state={sport:'nfl'};const activeTeams=()=>({KC:{nick:'Chiefs'}});"
           "const teamsForSport=()=>({});const nflMap=()=>({});\n"
           + _line("const teamName = ") + "\n" + _line("const teamsIn = ") + "\n"
           + _line("const teamNameIn = ") + "\n" + _line("const nflName = "))
    bad = "<img src=x onerror=alert(1)>"
    got = _node(src, f"[teamName('KC'), teamName({bad!r}), teamNameIn('mlb', {bad!r}),"
                     f" nflName({bad!r}), teamName('W&M'), teamName(undefined)]")
    if got is None:
        return
    assert got[0] == "Chiefs"
    for g in got[1:4]:
        assert "<" not in g and ">" not in g, g
    assert got[4] == "W&M", "an ampersand is left for the caller's escaper"
    assert got[5] == ""


def test_the_top_bar_icons_refuse_a_non_http_link():
    body = _fn("barLink")
    assert 'safeHref(url) === "#"' in body


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
