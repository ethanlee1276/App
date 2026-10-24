"""The pieces a store submission reads agree with each other (2026-10-24).

Ethan: "make sure we're ready to go. To go onto an app store and the Google
Play store." docs/APP_STORES.md carries the checklist; this holds the parts
of it that can go wrong without anyone noticing:

  - the iOS shell (deploy/ios) is the same app as the Play one, announces
    itself the way boot.js listens for, opens the store app, and its Apple
    key settings are the ones the box reads (engine/webpush.apns_config);
  - the app opens where a person expects: a league the link names, else the
    league they were last on, else the one in season — never baseball all
    winter because a start address said so;
  - the manifest no longer describes pages the store app leaves out, and the
    notification badge is a real silhouette (white on clear), which is all
    Android draws of it.

Run directly: `python3 tests/test_ready_for_the_stores.py`
"""
import json
import os
import re
import struct
import subprocess
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
READ = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()  # noqa: E731
IOS = json.loads(READ("deploy", "ios", "capacitor.config.json"))
TWA = json.loads(READ("deploy", "twa", "twa-manifest.json"))
MAN = json.loads(READ("web", "manifest.webmanifest"))
APP = READ("web", "js", "app.js")


def test_the_ios_shell_is_the_same_app_and_announces_itself():
    assert IOS["appId"] == TWA["packageId"] == "com.qellysbook.app"
    assert IOS["server"]["url"].startswith("https://" + TWA["host"] + "/") and "app=ios" in IOS["server"]["url"]
    ua = IOS["appendUserAgent"]
    rx = re.search(r"/QellysApp\\/\[\\d\.\]\+ \\\(ios\\\)/", READ("web", "js", "boot.js"))
    assert rx, "boot.js listens for the shell's user agent"
    assert re.search(r"QellysApp/[\d.]+ \(ios\)", "Mozilla/5.0 (iPhone) AppleWebKit Mobile " + ua)
    assert IOS["webDir"] == "www" and os.path.exists(os.path.join(ROOT, "deploy", "ios", "www", "index.html"))
    assert "PushNotifications" in IOS["plugins"]


def test_the_apple_key_settings_are_the_ones_the_box_reads():
    readme = READ("deploy", "ios", "README.md")
    from engine import webpush
    src = READ("engine", "webpush.py")
    names = re.findall(r'"(QB_APNS_[A-Z_]+)"', src)
    assert set(names) >= {"QB_APNS_KEY_FILE", "QB_APNS_KEY_ID", "QB_APNS_TEAM_ID", "QB_APNS_TOPIC", "QB_APNS_ENV"}
    for n in set(names):
        assert n in readme, f"the README never says to set {n}"
    assert "QB_APNS_TOPIC=com.qellysbook.app" in readme and "sudo ./deploy/setenv.sh" in readme
    assert webpush.apns_config({}) is None


def _start(search="", kept=None, when="2026-10-24"):
    at = APP.index("function startSport(today) {")
    fn = APP[at:APP.index("\n}\n", at) + 2]
    js = """
const store = new Map(%s);
global.location = { search: %s };
global.localStorage = { getItem: (k) => store.has(k) ? store.get(k) : null };
%s
console.log(startSport(new Date(%s + "T12:00:00")));
""" % (json.dumps([["qb.sport", kept]] if kept else []), json.dumps(search), fn, json.dumps(when))
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_the_app_opens_where_a_person_expects():
    assert _start("?sport=nhl", kept="mlb") == "nhl", "a link that names a league wins"
    assert _start("?sport=nfl", kept="mlb") == "nfl"
    assert _start("", kept="nba") == "nba", "then the league you were last on"
    assert _start("", kept="bogus", when="2026-10-24") == "nfl"
    for when, want in (("2026-09-01", "nfl"), ("2027-01-20", "nfl"), ("2027-02-20", "nba"),
                       ("2027-03-30", "mlb"), ("2027-07-04", "mlb"), ("2027-08-31", "mlb")):
        assert _start("", when=when) == want, (when, want)
    at = APP.index("function applySport() {")
    assert 'localStorage.setItem("qb.sport", state.sport)' in APP[at:at + 600]
    assert MAN["start_url"] == "/#recommended" and "sport=" not in json.dumps(MAN["shortcuts"])
    assert TWA["startUrl"] == "/?app=play#recommended"


def test_the_manifest_describes_only_what_every_build_shows():
    words = (MAN["description"] + " " + " ".join(MAN["categories"])).lower()
    for gone in ("meme", "coin", "crypto", "finance", "prediction"):
        assert gone not in words, gone
    assert all(s.get("icons") for s in MAN["shortcuts"]), "Play's launcher shortcuts need an icon each"


def _png_rgba(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    bit, ctype = data[24], data[25]
    assert (bit, ctype) == (8, 6), "an 8-bit RGBA badge"
    i, idat = 8, b""
    while i < len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        if kind == b"IDAT":
            idat += data[i + 8:i + 8 + n]
        i += 12 + n
    raw, rows, stride, prev = zlib.decompress(idat), [], w * 4, bytearray(w * 4)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            b, c = prev[x], prev[x - 4] if x >= 4 else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, rows


def test_the_badge_is_a_white_silhouette_on_clear():
    icon = next(i for i in MAN["icons"] if i.get("purpose") == "monochrome")
    w, h, rows = _png_rgba(os.path.join(ROOT, "web", icon["src"]))
    assert (w, h) == (96, 96) and icon["sizes"] == "96x96"
    px = [row[i:i + 4] for row in rows for i in range(0, len(row), 4)]
    clear = sum(1 for p in px if p[3] == 0)
    inked = [p for p in px if p[3] > 200]
    assert 0.3 < clear / len(px) < 0.9, "a silhouette, not a filled square"
    assert inked and all(p[0] > 240 and p[1] > 240 and p[2] > 240 for p in inked), "white where it is drawn"
    assert 'badge: "/icon-badge-96.png"' in READ("web", "sw.js")



def test_a_shared_slip_and_the_icon_badge_are_wired():
    st = MAN["share_target"]
    assert st["action"] == "/share-slip" and st["method"] == "POST" and st["enctype"] == "multipart/form-data"
    assert st["params"]["files"][0]["name"] == "slip"
    sw = READ("web", "sw.js")
    at = sw.index('pathname !== "/share-slip"')
    body = sw[at:at + 900]
    assert sw.index('self.addEventListener("fetch", (e) => {\n  const req = e.request;\n  if (req.method !== "POST"') > \
        sw.index('if (req.method !== "GET") return;'), "its own listener, after the one that leaves writes alone"
    assert "12 * 1024 * 1024" in body and "/^image\\//" in body and 'Response.redirect("/?shared=slip#ask", 303)' in body
    assert 'k !== VERSION && k !== "qb-shared"' in sw, "an update must not drop a slip mid-share"
    at = APP.index("async function sharedSlipIn() {")
    fn = APP[at:APP.index("\n}\n", at)]
    assert 'box.delete("/shared-slip")' in fn and "askSlipSend(new File(" in fn and 'switchView("ask")' in fn
    assert "\nsharedSlipIn();\n" in APP
    at = APP.index("function faviconBadge() {")
    assert "navigator.setAppBadge(open)" in APP[at:at + 900] and "navigator.clearAppBadge()" in APP[at:at + 900]


PNG_1PX = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def test_in_a_browser_a_shared_slip_lands_in_ask():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import rendercheck
    srv, port = rendercheck._serve()
    origin = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context()
                page = ctx.new_page()
                page.goto(origin + "/index.html", wait_until="load")
                page.evaluate("navigator.serviceWorker.ready.then(() => true)")
                page.reload(wait_until="load")          # the worker now controls the page
                page.wait_for_timeout(800)
                sent = page.evaluate("""async (bytes) => {
                    const fd = new FormData();
                    fd.append("slip", new Blob([new Uint8Array(bytes)], { type: "image/png" }), "slip.png");
                    const r = await fetch("/share-slip", { method: "POST", body: fd });
                    const box = await caches.open("qb-shared");
                    const kept = await box.match("/shared-slip");
                    return { url: r.url, kept: kept ? kept.headers.get("Content-Type") : null,
                             size: kept ? (await kept.blob()).size : 0 };
                }""", list(PNG_1PX))
                page.goto(origin + "/index.html?shared=slip#ask", wait_until="load")
                page.wait_for_timeout(1500)
                after = page.evaluate("""async () => ({ left: !!(await (await caches.open("qb-shared")).match("/shared-slip")),
                    view: (document.querySelector(".view.active") || {}).id || "", search: location.search })""")
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert sent["url"].endswith("/?shared=slip#ask") or "shared=slip" in sent["url"], sent
    assert sent["kept"] == "image/png" and sent["size"] == len(PNG_1PX), sent
    assert after == {"left": False, "view": "view-ask", "search": ""}, after

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
