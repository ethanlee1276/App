"""Copy the report, share the game (js/report.js).

Ethan, 2026-10-20: "I want you too do all of it besides D" — copying and
sharing the game report among it. Two quiet buttons over the report's
contents:

  * "Copy the report" puts the whole report on the clipboard as plain
    text, in the page's reading order — the clipboard first on a phone
    too, the share sheet only where there is no clipboard;
  * "Share this game" sends the game, its kickoff, its line and the game
    page's clean link — the public facts and nothing of the report, which
    is paid: whoever a share is forwarded to reads it before anybody has
    paid for anything (the rule app.js pickSlug keeps for picks);
  * neither is drawn for a reader without the report (the locked teaser).

Run directly: `python3 tests/test_the_report_copies_and_shares.py`
"""
import json
import os
import shutil
import subprocess
import sys
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))


class _Fixture:
    """The research report's own fixture (its board and its report),
    imported on first use the way the suite shares a sibling's fixture."""

    def __getattr__(self, name):
        import test_the_game_report_reads_like_the_research as research
        return getattr(research, name)


T = _Fixture()

REPORT_JS = os.path.join(ROOT, "web", "js", "report.js")
REPORT_CSS = open(os.path.join(ROOT, "web", "css", "report.css"), encoding="utf-8").read()
APP = app_js()
URL = "https://qellysbook.com/game/gb-det-1025"


def _node(body: str, rep: dict):
    node = shutil.which("node")
    if not node:
        return None
    script = (
        "const vm = require('vm'); const fs = require('fs');"
        "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
        "const clicks = []; const copied = []; const shared = [];"
        "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, setTimeout: () => 0,"
        " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
        " teamName: (t) => t, playerAvatar: (p) => '<i class=av></i>',"
        " document: { addEventListener: (type, fn) => clicks.push(fn) },"
        " navigator: { clipboard: { writeText: async (t) => { copied.push(t); } } } };"
        "vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(REPORT_JS)}, 'utf8'), ctx);"
        "const R = ctx.window.QBReport;"
        f"const rep = {json.dumps(rep, ensure_ascii=False)};"
        "const click = (attr, game) => { const b = { dataset: attr === 'copy' ? { grCopy: game } : { grShare: game },"
        " textContent: 'x' }; const e = { target: { closest: () => b }, preventDefault() {} };"
        " clicks.forEach((fn) => fn(e)); return b; };"
        + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_report_carries_its_public_share_facts():
    rep = T._report()
    assert rep["when"] == "Sunday, Oct. 25, 4:25 PM ET", rep["when"]
    assert rep["line"] == "DET by 3 at home, total 52.5", rep["line"]


def test_two_buttons_over_the_report_and_none_on_the_locked_teaser():
    got = _node("process.stdout.write(JSON.stringify({full: R.html(rep, {url: "
                f"{json.dumps(URL)}}}), locked: R.html(null, null)}}));", T._report())
    if got is None:
        print("      (skipped: no Node)")
        return
    assert 'data-gr-copy="GB@DET">Copy the report</button>' in got["full"]
    assert 'data-gr-share="GB@DET">Share this game</button>' in got["full"]
    assert got["full"].index('class="gr-tools"') < got["full"].index('class="card gr-card"')
    assert "data-gr-" not in got["locked"]
    assert ".gr-tools { display: flex; flex-wrap: wrap; gap: 8px;" in REPORT_CSS


def test_copy_puts_the_whole_report_on_the_clipboard_in_reading_order():
    rep = T._report()
    got = _node("R.html(rep, {url: " + json.dumps(URL) + "}); click('copy', 'GB@DET');"
                "setImmediate(() => process.stdout.write(JSON.stringify({copied})));", rep)
    if got is None:
        print("      (skipped: no Node)")
        return
    assert len(got["copied"]) == 1
    text = got["copied"][0]
    assert text.startswith("Packers at Lions — Sunday, Oct. 25, 4:25 PM ET\nThe Qellys Book game report\n"), text[:120]
    at = -1
    for s in rep["sections"]:
        i = text.index(s["title"].upper())
        assert i > at, s["title"]
        at = i
    # Every list item and every player's verdict is in it.
    for s in rep["sections"]:
        for b in s["blocks"]:
            if b["type"] == "list":
                for item in b["items"]:
                    assert f"• {item}" in text, item
            if b["type"] == "verdicts":
                for v in b["items"]:
                    assert f"• {v['title']} — {v['label']}" in text, v["title"]
    assert text.endswith("\n\n" + URL)
    for bad in ("undefined", "[object", "NaN"):
        assert bad not in text, bad


def test_share_sends_the_public_facts_and_the_link_and_nothing_of_the_report():
    rep = T._report()
    got = _node("R.html(rep, {url: " + json.dumps(URL) + "});"
                "ctx.navigator.share = async (p) => { shared.push(p); };"
                "click('share', 'GB@DET');"
                "setImmediate(() => process.stdout.write(JSON.stringify({shared, teaser: R.teaser(rep)})));", rep)
    if got is None:
        print("      (skipped: no Node)")
        return
    assert got["shared"] == [{"title": "Packers at Lions", "url": URL,
                              "text": "Packers at Lions — Sunday, Oct. 25, 4:25 PM ET. DET by 3 at home, "
                                      "total 52.5. Our full game report is on Qellys Book."}], got["shared"]
    # Nothing paid: no player the report reads, no read, no simulator chance.
    board = T._board()
    for rd in board.get("scan_reads", {}).values():
        for r in rd.get("players") or []:
            assert r["player"] not in got["teaser"], r["player"]
    for paid in ("%", "FAVORABLE", "breakout", "simulator"):
        assert paid not in got["teaser"], paid


def test_without_a_share_sheet_share_copies_the_facts_and_the_link():
    rep = T._report()
    got = _node("R.html(rep, {url: " + json.dumps(URL) + "}); click('share', 'GB@DET');"
                "setImmediate(() => process.stdout.write(JSON.stringify({copied})));", rep)
    if got is None:
        print("      (skipped: no Node)")
        return
    assert got["copied"] == ["Packers at Lions — Sunday, Oct. 25, 4:25 PM ET. DET by 3 at home, total 52.5. "
                             "Our full game report is on Qellys Book.\n" + URL], got["copied"]


def test_the_game_page_hands_the_report_its_clean_link():
    call = APP[APP.index("const reportHTML = gameReportHTML("):]
    call = call[:call.index(";")]
    assert 'url: cleanURL("game", gameSlug(g))' in call, call
    assert 'scripts: report && simCard ? simCard : ""' in call, call


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
