"""The service worker's cache name is derived now, because typing it failed twice.

sw.js has always carried the rule in its own docstring — "bump VERSION on
any shell change" — and the file also records that the rule was missed
once already: v1 served two shell deploys' worth of pre-redesign copies
before anyone noticed. It was then missed again. `qb-v3` was set on
2026-08-18 and sat there through 2,149 lines of index.html, styles.css,
app.js and visuals.js, including the 2026-08-19 fix for the phone drawer
that would not open.

WHY THAT MATTERS EVEN THOUGH THE WORKER IS NETWORK-FIRST. It is: a
healthy phone gets fresh files and the cache never answers. But the cache
is the fallback for every request the network loses, and phones lose
requests. One dropped styles.css hands back the previous stylesheet
inside an installed PWA — no address bar, no reload button, no hint that
anything is old — and the result is indistinguishable from a fix that was
never deployed. That is a bad way to find out, and it is exactly the
report this came in as.

So server.py stamps the line on the way out with a hash of the files
SHELL lists, read from sw.js so the two can never drift apart. Change any
cached file and the cache name changes by itself; `activate` deletes
every other cache on the next launch. No discipline required, which is
the point — the rule that needed remembering is the rule that broke.

Run directly: `python3 tests/test_sw_version.py`
"""

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server                                            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SW = (ROOT / "web" / "sw.js").read_text(encoding="utf-8")


def _version(body: str) -> str:
    m = re.search(r'const VERSION = "([^"]*)";', body)
    assert m, "sw.js has no VERSION line for the server to stamp"
    return m.group(1)


def test_the_served_worker_is_not_the_typed_version():
    """If the stamp ever stops applying, the served file falls back to a
    literal that nobody will remember to change — silently."""
    served = _version(server.sw_body().decode())
    assert served != _version(SW), \
        "the served worker still carries the typed version — the stamp is not running"
    assert re.fullmatch(r"qb-[0-9a-f]{12}", served), \
        f"the stamped version is not a content hash: {served!r}"


def test_the_hash_covers_exactly_what_the_worker_caches():
    """A hash over the wrong files is worse than no hash: it changes when
    it should not and holds still when it should not."""
    listed = server._sw_shell(SW)
    names = {p.name for p in listed}
    assert "styles.css" in names and "app.js" in names and "index.html" in names, \
        f"the shell hash is missing the files most likely to change: {sorted(names)}"
    # Every entry in SHELL that exists on disk is covered — nothing is
    # cached by the worker that the version does not describe.
    urls = re.findall(r'"([^"]+)"', re.search(r"const SHELL = \[(.*?)\];", SW, re.S).group(1))
    on_disk = [u for u in urls
               if (ROOT / "web" / ("index.html" if u == "/" else u.lstrip("/"))).is_file()]
    assert len(listed) == len(on_disk), \
        f"{len(on_disk)} shell files exist, {len(listed)} are hashed"


def test_changing_a_shell_file_changes_the_cache_name():
    """The whole mechanism, exercised against a copy so the real web root
    is never touched."""
    with tempfile.TemporaryDirectory() as tmp:
        web = Path(tmp) / "web"
        shutil.copytree(ROOT / "web", web, symlinks=True,
                        ignore=shutil.ignore_patterns("data", "img", "venues",
                                                      "vendor", "*.png", "*.jpg"))
        before = _version(server.sw_body(web).decode())
        css = web / "css" / "styles.css"
        css.write_text(css.read_text(encoding="utf-8") + "\n/* a change */\n",
                       encoding="utf-8")
        after = _version(server.sw_body(web).decode())
    assert before != after, \
        "styles.css changed and the cache name did not — a stale bundle survives the deploy"


def test_an_unchanged_shell_keeps_its_name():
    """The other half. A version that moves on every request would evict
    the cache constantly and make the offline fallback useless."""
    a = _version(server.sw_body().decode())
    b = _version(server.sw_body().decode())
    assert a == b, f"the cache name is not stable across reads: {a} then {b}"


def test_the_typed_literal_is_never_a_downgrade():
    """Served by anything other than server.py — a bare file server, a
    local checkout — the literal is what runs. It must be ahead of the
    last one that shipped, or that path re-serves an older cache."""
    typed = _version(SW)
    assert typed != "qb-v3", "the literal is still the version that shipped stale"
    assert re.fullmatch(r"qb-v\d+", typed), \
        f"the fallback literal should stay a simple bump: {typed!r}"
    assert int(typed.split("v")[-1]) >= 4, f"the literal went backwards: {typed}"


def test_activate_still_deletes_every_other_cache():
    """The stamp only helps because of this: a new name is worthless if
    the old cache is left in place to answer from."""
    i = SW.index('addEventListener("activate"')
    block = SW[i:i + 400]
    assert "caches.keys()" in block and "caches.delete" in block, \
        "activate no longer clears old caches — a new version stops evicting the old one"
    assert "k !== VERSION" in block, \
        "activate no longer keys its cleanup on VERSION"


def test_the_worker_is_served_through_the_stamp():
    """End to end: the path the browser actually asks for."""
    from http.server import ThreadingHTTPServer
    import threading
    import urllib.request

    class Quiet(server.Handler):
        def log_message(self, *a, **kw):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    srv.live_mode = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/sw.js"
        with urllib.request.urlopen(url, timeout=10) as r:
            body = r.read().decode()
            ctype = r.headers.get("Content-Type", "")
    finally:
        srv.shutdown()
    assert "javascript" in ctype, f"/sw.js is served as {ctype!r}"
    assert _version(body) == _version(server.sw_body().decode()), \
        "the handler served an unstamped worker"
    assert "const SHELL" in body, "the stamp mangled the file"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print("all good" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
