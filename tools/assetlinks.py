"""Write web/.well-known/assetlinks.json for the Android app (roadmap #45).

A Trusted Web Activity shows the site full-screen, with no browser bar,
only when the site vouches for the app: Chrome fetches
https://qellysbook.com/.well-known/assetlinks.json and checks that the
app's package name and signing-certificate fingerprint are listed there.
Get either one wrong and the app still opens, but with a browser address
bar across the top, which is the first thing a store reviewer reports.

The fingerprint is PUBLIC by design (anyone can read it off the installed
app), so the file is committed like any other page. It is not a secret,
and it is not in the repo until there is a real key to describe. Run it
on the laptop after `bubblewrap init` makes the upload key, or with the
SHA-256 that Play Console shows under App signing:

    python3 tools/assetlinks.py AB:CD:...:EF            # 32 bytes, colon-separated
    python3 tools/assetlinks.py AB:..:EF 12:..:34       # upload key + Play's key

then commit web/.well-known/assetlinks.json and deploy.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TWA = ROOT / "deploy" / "twa" / "twa-manifest.json"
OUT = ROOT / "web" / ".well-known" / "assetlinks.json"
_FP = re.compile(r"^(?:[0-9A-F]{2}:){31}[0-9A-F]{2}$")


def package_id() -> str:
    return json.loads(TWA.read_text())["packageId"]


def statement(fingerprints: list[str]) -> list[dict]:
    """The Digital Asset Links statement; raises ValueError on a bad print."""
    fps = [f.strip().upper() for f in fingerprints]
    if not fps:
        raise ValueError("give at least one SHA-256 certificate fingerprint")
    for f in fps:
        if not _FP.match(f):
            raise ValueError(f"not a SHA-256 fingerprint (32 colon-separated hex bytes): {f!r}")
    return [{"relation": ["delegate_permission/common.handle_all_urls"],
             "target": {"namespace": "android_app", "package_name": package_id(),
                        "sha256_cert_fingerprints": fps}}]


def main(argv: list[str]) -> int:
    try:
        doc = statement(argv)
    except ValueError as exc:
        print(f"assetlinks: {exc}")
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} for {doc[0]['target']['package_name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
