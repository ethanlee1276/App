"""The pieces a store wrapper needs are in place and agree with each other.

Audit 2026-09-30, O27 (roadmap #45). No build is submitted; whether a store
accepts the app is a human call (docs/APP_STORES.md). What is pinned here
is everything that can be wrong silently: an Android TWA whose package,
host or start URL disagrees with the site's manifest; an assetlinks file
with a bad fingerprint (the app then opens with a browser bar); a signing
key one `git add -A` from the repo; and a Caddy rule that serves the
ownership file as anything but JSON.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TWA = json.loads((ROOT / "deploy" / "twa" / "twa-manifest.json").read_text())
MAN = json.loads((ROOT / "web" / "manifest.webmanifest").read_text())

from tools import assetlinks  # noqa: E402

FP = ":".join(["AB"] * 32)


def test_the_wrapper_and_the_manifest_agree():
    assert TWA["host"] == "qellysbook.com"
    assert TWA["startUrl"] == MAN["start_url"]
    assert TWA["themeColor"] == MAN["theme_color"] and TWA["backgroundColor"] == MAN["background_color"]
    assert TWA["webManifestUrl"].endswith("/manifest.webmanifest")
    assert TWA["maskableIconUrl"].endswith("/icon-maskable-512.png")
    assert (ROOT / "web" / "icon-maskable-512.png").exists()
    assert "signingKey" in TWA and "password" not in json.dumps(TWA).lower()


def test_the_manifest_carries_what_a_store_build_reads():
    for k in ("id", "lang", "start_url", "scope", "display", "icons"):
        assert MAN.get(k), k
    assert MAN["prefer_related_applications"] is False
    purposes = {i.get("purpose") for i in MAN["icons"] if i["sizes"] == "512x512"}
    assert {"any", "maskable"} <= purposes


def test_assetlinks_states_the_package_and_refuses_a_bad_print():
    doc = assetlinks.statement([FP.lower()])
    t = doc[0]["target"]
    assert t["package_name"] == TWA["packageId"] and t["sha256_cert_fingerprints"] == [FP]
    assert doc[0]["relation"] == ["delegate_permission/common.handle_all_urls"]
    for bad in ([], ["AB:CD"], [FP + ":00"], ["not-a-print"]):
        try:
            assetlinks.statement(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "assetlinks.py"), "nope"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "not a SHA-256" in r.stdout


def test_no_placeholder_ownership_file_ships():
    f = ROOT / "web" / ".well-known" / "assetlinks.json"
    if f.exists():                      # only ever written from a real key
        doc = json.loads(f.read_text())
        prints = doc[0]["target"]["sha256_cert_fingerprints"]
        assert prints and FP not in prints, "a test fingerprint was committed"


def test_signing_keys_never_reach_the_repo():
    ign = (ROOT / ".gitignore").read_text().splitlines()
    for pat in ("*.keystore", "*.jks", "deploy/twa/*.aab"):
        assert pat in ign, pat
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True).stdout.splitlines()
    assert not [t for t in tracked if t.endswith((".keystore", ".jks"))]


def test_caddy_serves_the_ownership_file_as_json():
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()
    assert "@assetlinks path /.well-known/assetlinks.json" in caddy
    assert 'header @assetlinks Content-Type "application/json"' in caddy


def test_the_doc_says_what_is_a_guess():
    doc = (ROOT / "docs" / "APP_STORES.md").read_text()
    assert "No build has been submitted" in doc and "[Guessing]" in doc
    assert "has not been read for this" in doc, "the unread Play policy is said, not implied"
    assert "P45-a" in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text()


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
