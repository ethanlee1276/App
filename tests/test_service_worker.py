"""The service worker's cache name has to change when the shell does.

sw.js carries `const VERSION = "..."`, and `activate` deletes every cache
whose key is not that string. So the name IS the cache-busting mechanism:
change the shell, change the name, and the old bundle is deleted on the
next visit.

server.py rewrites that line with a hash of the shell on the way out, so
nobody has to remember to bump it — which matters, because the file's own
header records that bumping it by hand was missed twice, once through the
2026-08-19 fix for the phone drawer that would not open.

**IT NEVER RAN IN PRODUCTION.** The Caddyfile proxied only `/api/*` to the
app and served everything else off disk, so `/sw.js` went out with the
literal in the file — `qb-v4` — unchanged, on every deploy, since the day
it was written. `activate` deletes caches that are not VERSION; with
VERSION frozen it deleted nothing, ever. Network-first limits the damage
on a good connection, and on a phone that drops one request for
styles.css the fallback is whatever that cache happens to hold.

THIS IS THE THIRD TIME. `seal_on_boot` was written into `server.main()`
while production runs `launch.py`. The CSP was set by the app while Caddy
served the document. Same shape every time: *the app fixes it on the way
out* is not true of a file the app never sees.

    python3 tests/test_service_worker.py
"""

import hashlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CADDY = os.path.join(ROOT, "deploy", "Caddyfile")
SW = os.path.join(ROOT, "web", "sw.js")


def _read(p):
    return open(p, encoding="utf-8").read()


def _decomment(text):
    """The Caddyfile's comments quote the bug at length, including the
    literal `qb-v4` and the words this test looks for."""
    return re.sub(r"(?m)^\s*#.*$", "", text)


# --- the route ---------------------------------------------------------------
def test_the_worker_is_served_by_the_app_and_not_off_disk():
    conf = _decomment(_read(CADDY))
    m = re.search(r"handle\s+/sw\.js\s*\{([^}]*\{[^}]*\}[^}]*)\}", conf, re.S)
    assert m, (
        "/sw.js is not routed to the app, so server.py's VERSION rewrite "
        "never runs and the cache name is frozen at whatever is typed in "
        "the file")
    assert "reverse_proxy" in m.group(1)


def test_the_route_comes_before_the_catch_all():
    """Caddy's `handle` blocks are mutually exclusive and ordered. A
    /sw.js block after the catch-all would never be reached."""
    conf = _decomment(_read(CADDY))
    assert conf.index("handle /sw.js") < conf.index("handle {"), (
        "the catch-all file_server comes first and swallows /sw.js")


def test_the_worker_is_still_told_not_to_cache_itself():
    conf = _decomment(_read(CADDY))
    i = conf.index("path /sw.js")
    assert "no-cache" in conf[i:i + 200], (
        "a worker cached for a year keeps serving its own old shell, and "
        "the fix is the exact thing the cache stops arriving")


def test_the_brand_files_revalidate_like_the_shell_does():
    """`@shell` covers the document, the scripts and the styles — and
    nothing else, so every image went out with NO Cache-Control at all
    and the decision fell to browser heuristics. That is the same
    sentence the Caddyfile already writes about app.js, where iOS acted
    on it: a phone kept its old JS under a freshly-fetched index.html and
    six pages were unreachable.

    It bites hardest on the mark. The header logo and the tab icon
    changed twice on 2026-08-23; a phone holding the old copy shows a
    retired logo under a deploy that replaced it, which reads as a deploy
    that did not work.

    Named one by one rather than `/*.png` on purpose — web/img is 18MB of
    board art that changes with the data and has no business
    revalidating on every visit."""
    conf = _decomment(_read(CADDY))
    i = conf.index("@brand path")
    line = conf[i:conf.index("\n", i)]
    for f in ("/logo-qb.png", "/favicon.svg", "/icon-192.png",
              "/apple-touch-icon.png", "/manifest.webmanifest"):
        assert f in line, f"{f} can go stale on a phone after a deploy"
    assert "no-cache" in conf[i:i + 260], "the matcher sets no policy"
    # …and it must not have become a blunt instrument.
    assert "/*.png" not in line and "/img/*" not in line, (
        "the board art is being revalidated on every visit")


def test_the_deploy_installs_the_caddyfile():
    """The routing fix is worthless if the box keeps its old copy, and
    the manual `sudo cp` in the Caddyfile header is exactly the step that
    gets done once and never again."""
    sh = _read(os.path.join(ROOT, "deploy", "deploy.sh"))
    assert "/etc/caddy/Caddyfile" in sh, "the deploy never installs it"
    assert "caddy validate" in sh, (
        "an invalid Caddyfile installed unchecked takes the site down")
    assert "cmp -s" in sh, "it reloads caddy on every deploy regardless"


# --- the rewrite itself ------------------------------------------------------
def test_the_version_in_the_file_is_a_placeholder_not_the_mechanism():
    src = _read(SW)
    m = re.search(r'const VERSION = "([^"]*)";', src)
    assert m, "no VERSION line for server.py to rewrite"
    assert "qb-" in m.group(1)


def test_the_hash_covers_every_file_the_worker_precaches():
    """If the hash misses a file in SHELL, changing that file leaves the
    cache name alone and the stale copy survives the deploy."""
    import server
    shell = server._sw_shell(_read(SW))
    listed = re.findall(r'"(/[^"]*)"', _read(SW).split("const SHELL = [")[1]
                        .split("]")[0])
    names = {os.path.basename(p) for p in listed if p not in ("/",)}
    got = {os.path.basename(str(p)) for p in shell}
    missing = names - got
    assert not missing, (
        "sw.js precaches %s and the hash does not cover them" % sorted(missing))


def test_changing_the_shell_changes_the_name():
    """The whole property, measured rather than asserted.

    AGAINST A COPY, not the real web tree. The first version of this
    appended a line to `web/css/styles.css` and restored it afterwards,
    which is fine in a serial run and a landmine in a parallel one: three
    dozen tests read that file, and any of them running during the
    window would have seen a stylesheet nobody wrote. `sw_body` takes the
    web directory as an argument precisely so it can be pointed
    somewhere else.
    """
    import shutil
    import server
    tmp = tempfile.mkdtemp(prefix="qb-shell-")
    try:
        web = os.path.join(tmp, "web")
        shutil.copytree(os.path.join(ROOT, "web"), web)
        webp = __import__("pathlib").Path(web)
        v1 = re.search(r'const VERSION = "([^"]*)";',
                       server.sw_body(webp).decode()).group(1)
        css = os.path.join(web, "css", "styles.css")
        with open(css, "ab") as fh:
            fh.write(b"\n/* a change to the shell */\n")
        v2 = re.search(r'const VERSION = "([^"]*)";',
                       server.sw_body(webp).decode()).group(1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert v1 != v2, (
        "the shell changed and the cache name did not — every phone keeps "
        "the old bundle")


def test_the_rewrite_does_not_change_anything_else():
    import server
    out = server.sw_body().decode()
    src = _read(SW)
    assert len(out.splitlines()) == len(src.splitlines())
    a = re.sub(r'const VERSION = "[^"]*";', "", out)
    b = re.sub(r'const VERSION = "[^"]*";', "", src)
    assert a == b, "the rewrite touched more than the VERSION line"


# --- what the worker does ----------------------------------------------------
def test_authenticated_and_live_responses_are_never_cached():
    """Caching an authenticated response is how one user is served
    another user's page; caching a board is how somebody bets a price
    that no longer exists."""
    src = _read(SW)
    assert 'url.pathname.startsWith("/api/")' in src
    assert 'url.pathname.startsWith("/data/")' in src


def test_it_is_network_first():
    src = _read(SW)
    i = src.index("e.respondWith(")
    body = src[i:i + 600]
    assert body.index("fetch(req)") < body.index("caches.match"), (
        "cache-first: a phone would be served last night's prices in a "
        "window with no address bar to hint anything is wrong")


def test_activate_deletes_every_other_cache():
    src = _read(SW)
    i = src.index('addEventListener("activate"')
    body = src[i:i + 400]
    assert "caches.delete" in body and "!== VERSION" in body


# --- end to end --------------------------------------------------------------
def test_a_running_server_serves_a_hashed_version():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    d = tempfile.mkdtemp(prefix="qb-sw-")
    env = dict(os.environ)
    env.update({"QB_ACCOUNTS_DB": os.path.join(d, "a.db"), "QB_PAYWALL": ""})
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    base = "http://127.0.0.1:%d" % port
    try:
        end = time.time() + 40
        got = None
        while time.time() < end:
            try:
                with urllib.request.urlopen(base + "/sw.js", timeout=10) as r:
                    got = r.read().decode()
                break
            except Exception:                                # noqa: BLE001
                time.sleep(0.25)
        assert got, "the server never served /sw.js"
        v = re.search(r'const VERSION = "([^"]*)";', got).group(1)
        assert v != "qb-v4", (
            "the served worker carries the literal from the file — the "
            "rewrite did not happen")
        assert re.match(r"^qb-[0-9a-f]{12}$", v), v
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok  %s" % fn.__name__)
    print()
    print("%d tests passed." % len(fns))
