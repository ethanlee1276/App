"""A failed fetch says so; it never borrows the empty-ledger copy.

Audit 2026-09-30, V-2 / D-6 / V-12 / O19 (roadmap #24). With every data
fetch failing, the Record said "No graded picks yet", the Lab "No backtests
published yet", Memes "No meme-coin data yet", Intel forced a green "Live
data" badge over zeros, and the phone chip read a green "4m". A subscriber
would conclude the site had no record. Now:

  * fetchJSON tells FAILED (throw, gateway, 5xx) from NOT BUILT (404);
  * a failed view draws outageHTML — what could not load, when it last
    did, Retry, Status — and never its empty copy;
  * the standalone badge follows the fetch result;
  * the phone chip reads "Updated 3m · LIVE" / "· DEMO" and turns amber
    the moment any fetch on the page has failed.
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
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[i - 6:i] == "async ":
        i -= 6
    return APP[i:APP.index("\n}\n", i) + 2]


def _node(src, expr):
    if not shutil.which("node"):
        return None
    p = os.path.join(tempfile.mkdtemp(), "o.js")
    Path(p).write_text(src + f"\n(async () => {{ process.stdout.write(JSON.stringify(await ({expr}))); }})();")
    out = subprocess.run(["node", p], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    return json.loads(out.stdout)


def test_failed_and_not_built_are_different_answers():
    src = ("const _lastGood = new Map();\n" + _fn("fetchJSON")
           + "\nconst R = (status, body) => async () => ({ ok: status < 300, status, json: async () => body });")
    got = _node(src, "(async () => [...await Promise.all([fetchJSON(R(200, {a: 1}), 'k'),"
                     " fetchJSON(R(404)), fetchJSON(R(502)), fetchJSON(R(500)),"
                     " fetchJSON(async () => { throw new Error('net'); })]), _lastGood.has('k')])()")
    if got is None:
        return
    ok, missing, gateway, server, thrown, remembered = got
    assert ok["data"] == {"a": 1} and ok["failed"] is False and remembered
    assert missing["data"] is None and missing["failed"] is False, "a 404 is 'not built yet'"
    for r in (gateway, server, thrown):
        assert r["data"] is None and r["failed"] is True


def test_the_outage_card_says_what_when_and_what_to_do():
    src = ("const _lastGood = new Map([['record', Date.now() - 180000]]);\n"
           "const icon = () => '<i></i>';\n"
           "const escapeHtml = (s) => String(s).replace(/[&<>\"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n"
           "const ageText = (s) => Math.round(s / 60) + ' min';\n" + _fn("outageHTML"))
    got = _node(src, "Promise.resolve([outageHTML('the record', 'record'), outageHTML('the Lab', 'x')])")
    if got is None:
        return
    seen, never = got
    assert "Couldn’t load the record" in seen and "3 min ago" in seen
    assert "data-retry" in seen and 'href="#status"' in seen and 'role="status"' in seen
    assert "not an empty result" in seen
    assert "Nothing from it has loaded in this visit." in never


def test_every_silent_view_draws_the_outage_card():
    for name, what in (("renderLab", "the Lab’s backtests"), ("renderRecord", "the record"),
                       ("renderIntel", "the prediction-market boards"),
                       ("renderMemes", "the meme-coin board"), ("renderFantasy", "the NFL usage board"),
                       ("renderFutures", "the season projections"), ("renderUFC", "the UFC card"),
                       ("renderWhy", "the live record")):
        body = _fn(name)
        assert f'outageHTML("{what}"' in body, f"{name} still reads a failed fetch as an empty one"
    # The empty copy is reached only when the fetch did NOT fail.
    rec = _fn("renderRecord")
    assert rec.index('outageHTML("the record"') < rec.index("No graded picks yet")
    lab = _fn("renderLab")
    assert lab.index("if (got.failed)") < lab.index("No backtests published yet")


def test_the_badge_follows_the_fetch():
    body = _fn("setStandaloneSource")
    assert "ok = true" in body and "Couldn’t load" in body
    for name in ("renderIntel", "renderMemes", "renderUFC"):
        assert re.search(r'setStandaloneSource\([^;]*, false\)', _fn(name)), name


def test_the_phone_chip_says_updated_and_live_or_demo_and_goes_amber():
    body = _fn("updateAgo")
    assert "`Updated ${ago}`" in body and '"LIVE" : "DEMO"' in body
    assert 'el.classList.toggle("failing", wireDown().length > 0)' in body
    assert ".live-refresh.failing {" in CSS


def test_retry_reruns_the_view():
    i = APP.index('closest("[data-retry]")')
    assert "renderAll()" in APP[i:i + 300]


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
