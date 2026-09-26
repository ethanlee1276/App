"""The trimmed shell a phone downloads is the same program, without comments.

The site audit, 2026-09-24 (M-2): a first visit cost about 1.1 MB
compressed before any board, and `app.js` alone was 727 KB of which 44%
was comments. `engine/shrink.py` writes comment-stripped copies under
`web/min/`, Caddy serves them when they exist (`@trimmed`), and the
updater clears them before new code lands and rebuilds them after.

A comment stripper that misreads one regular expression serves a broken
site, so this file's first test is the proof, not a spot check: every
shipped script is parsed by TypeScript twice — as written and as trimmed —
and the two programs must print identically. The stylesheet is compared
token by token.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import shrink                                        # noqa: E402

PRINT = r"""
const ts = require(process.argv[2]);
const fs = require("fs");
const out = [];
for (const f of process.argv.slice(3)) {
  const sf = ts.createSourceFile(f, fs.readFileSync(f, "utf8"), ts.ScriptTarget.ES2022, false, ts.ScriptKind.JS);
  const bad = (sf.parseDiagnostics || []).map((d) => String(d.messageText));
  out.push({ bad, text: bad.length ? "" : ts.createPrinter({ removeComments: true }).printFile(sf) });
}
process.stdout.write(JSON.stringify(out));
"""


def _typescript():
    node = shutil.which("node")
    if not node:
        return None, None
    try:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:                                               # noqa: BLE001
        return node, None
    path = os.path.join(root, "typescript")
    return node, (path if os.path.isdir(path) else None)


def test_every_shipped_script_is_the_same_program_trimmed():
    node, ts = _typescript()
    if not ts:
        print("  SKIP node or typescript not installed")
        return
    d = Path(tempfile.mkdtemp())
    for rel in shrink.FILES:
        if not rel.endswith(".js"):
            continue
        src = (ROOT / "web" / rel).read_text(encoding="utf-8")
        a, b = d / "a.js", d / "b.js"
        a.write_text(src, encoding="utf-8")
        b.write_text(shrink.trimmed(rel, src), encoding="utf-8")
        prog = d / "print.js"
        prog.write_text(PRINT)
        out = subprocess.run([node, str(prog), ts, str(a), str(b)], capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr
        (orig, trim) = json.loads(out.stdout)
        assert not orig["bad"] and not trim["bad"], (rel, orig["bad"][:2], trim["bad"][:2])
        assert orig["text"] == trim["text"], f"{rel}: the trimmed copy is a different program"
        assert len(b.read_text()) < 0.8 * len(src), rel
    shutil.rmtree(d)


def _css_tokens(css: str) -> list:
    toks = re.findall(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|[\w.#%-]+|\S', css, re.S)
    return [t for t in toks if not t.startswith("/*")]


def test_the_stylesheet_keeps_every_token():
    src = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    out = shrink.trimmed("css/styles.css", src)
    assert _css_tokens(out) == _css_tokens(src)
    assert "/*" not in out and len(out) < 0.7 * len(src)


def test_the_tokenizer_reads_what_a_regex_cannot():
    cases = {
        'const u = "https://x.y/*not*/"; // gone': 'const u = "https://x.y/*not*/"; ',
        "const r = /\\/\\*[^/]*\\//g; /* gone */ f(r);": "const r = /\\/\\*[^/]*\\//g;   f(r);",
        "a = b / c / d; // x": "a = b / c / d; ",
        "if (x) return /ab+c/.test(s);": "if (x) return /ab+c/.test(s);",
        "t = `a ${b ? `in ${c /* x */}` : '}'} // not a comment`;":
            "t = `a ${b ? `in ${c  }` : '}'} // not a comment`;",
        "x = 1 /*\n*/ + 2": "x = 1 \n + 2",
        "q = [1, /[/]/.source]": "q = [1, /[/]/.source]",
    }
    for src, want in cases.items():
        assert shrink.strip_js(src) == want, (src, shrink.strip_js(src))
    for bad in ('x = "open', "x = `open ${y}", "x = (1, /open\n)"):
        try:
            shrink.strip_js(bad)
        except shrink.Unreadable:
            continue
        raise AssertionError(f"guessed at {bad!r}")
    assert shrink.strip_css("a/**/b{c:d}") == "a b{c:d}" and shrink.strip_css(".a/*x*/.b{}") == ".a.b{}"
    assert shrink.strip_css('p::after{content:"/* kept */"}') == 'p::after{content:"/* kept */"}'


def _web(app='const a = 1; // note\n'):
    web = Path(tempfile.mkdtemp())
    for rel in shrink.FILES:
        (web / rel).parent.mkdir(parents=True, exist_ok=True)
        (web / rel).write_text(app if rel.endswith("app.js") else
                               ("/* c */ body{margin:0}" if rel.endswith(".css") else "let v = 2; /* c */"))
    return web


def test_build_writes_once_leaves_a_misread_to_the_original_and_clears():
    web = _web()
    notes = shrink.build(web)
    target = web / "min" / "js" / "app.js"
    assert target.read_text() == "const a = 1; \n" and all("KB" in n for n in notes), notes
    stamp = target.stat().st_mtime_ns
    time.sleep(0.01)
    assert all(n.endswith(": current") for n in shrink.build(web)), "an unchanged file is not rewritten"
    assert target.stat().st_mtime_ns == stamp, "or its ETag moves and every phone downloads it again"
    (web / "js" / "app.js").write_text('const a = "unclosed;\n')
    notes = shrink.build(web)
    assert not target.exists() and any("served as written" in n for n in notes), notes
    shrink.clear(web)
    assert not any((web / "min" / rel).exists() for rel in shrink.FILES)


def test_the_updater_clears_before_new_code_and_builds_after():
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def g(cwd, *a):
        return subprocess.run(("git", "-C", str(cwd)) + a, env=env, check=True, capture_output=True, text=True)
    origin = Path(tempfile.mkdtemp())
    g(origin, "init", "-b", "main")
    (origin / "engine").mkdir()
    (origin / "engine" / "__init__.py").write_text("")
    shutil.copy(ROOT / "engine" / "shrink.py", origin / "engine" / "shrink.py")
    web = _web()
    shutil.copytree(web, origin / "web")
    (origin / ".gitignore").write_text("data/autoupdate.json\nweb/min/\n__pycache__/\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "one")
    clone = Path(tempfile.mkdtemp()) / "repo"
    subprocess.run(("git", "clone", str(origin), str(clone)), env=env, check=True, capture_output=True)
    bindir = Path(tempfile.mkdtemp())
    (bindir / "systemctl").write_text("#!/bin/sh\nexit 0\n")
    os.chmod(bindir / "systemctl", 0o755)

    def run():
        subprocess.run((sys.executable, str(ROOT / "deploy" / "autoupdate.py"), "--repo", str(clone)),
                       env={**env, "PATH": f"{bindir}{os.pathsep}{env['PATH']}"},
                       check=True, capture_output=True, text=True)
        return json.loads((clone / "data" / "autoupdate.json").read_text())
    state = run()
    trimmed = clone / "web" / "min" / "js" / "app.js"
    assert state["ok"] and trimmed.read_text() == "const a = 1; \n", state
    assert run()["note"] == "up to date", "a run that changed nothing says nothing more"
    (origin / "web" / "js" / "app.js").write_text("const a = 2; /* two */\n")
    g(origin, "add", "."); g(origin, "commit", "-m", "two")
    state = run()
    assert "restarted" in state["note"] and trimmed.read_text() == "const a = 2;  \n", state


def test_caddy_serves_the_trimmed_copy_only_when_it_exists():
    conf = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    i = conf.index("@trimmed {")
    block = conf[i:conf.index("rewrite @trimmed /min{path}", i)]
    assert "path /js/app.js /js/visuals.js /css/styles.css" in block and "file /min{path}" in block
    assert conf.index("rewrite @trimmed /min{path}") < conf.index("try_files {path} /index.html")
    shell = conf[conf.index("@shell path"):]
    assert "/min/*" in shell[:shell.index("\n")], "the trimmed copies revalidate like the originals"
    assert "web/min/" in (ROOT / ".gitignore").read_text()
    for rel in shrink.FILES:
        assert f"/{rel}" in block, rel


if __name__ == "__main__":
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
