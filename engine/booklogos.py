"""The sportsbooks' own icons for the Bet it sheet — fetched ON THE BOX.

Ethan, 2026-10-07: "Can you maybe use real Sportsbook logos for that bet
it page?" The machine the code is written on cannot reach the internet,
so the icons cannot be committed from there; the box can, so this runs
there and writes them where the page already looks:

    cd /srv/qellys && sudo -u qellys python3 -m engine.booklogos

For each book it tries the site's own `apple-touch-icon.png` (the square
icon the book ships for phone home screens — its mark, at 180px), then
Google's icon service for the same domain. What arrives is checked to be
a PNG of a plausible size and saved as `web/img/books/<key>.png`;
`manifest.json` beside them lists the keys that have a file and where
each came from, and the page reads that list when the sheet opens, so
nothing in the code changes when a file lands. Run it again any time;
it overwrites.

A mark is a trademark used here to name the book a link goes to, the
way every odds-comparison page does. A book that returns nothing usable
keeps its coloured initials on the sheet; the report says which.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "web" / "img" / "books"

#: key (as the page's BOOKS table names it) → the book's own domain.
BOOK_DOMAINS = {
    "draftkings": "sportsbook.draftkings.com",
    "fanduel": "sportsbook.fanduel.com",
    "betmgm": "sports.betmgm.com",
    "caesars": "sportsbook.caesars.com",
    "fanatics": "sportsbook.fanatics.com",
    "thescorebet": "thescore.bet",
    "hardrock": "hardrock.bet",
    "betrivers": "betrivers.com",
    "ballybet": "ballybet.com",
    "betparx": "betparx.com",
    "fliff": "getfliff.com",
    "windcreek": "windcreekcasino.com",
    "novig": "novig.us",
    "prophetx": "prophetx.co",
    "bet365": "bet365.com",
    "kalshi": "kalshi.com",
    "polymarket": "polymarket.com",
}
#: More doors for a book whose own domain gave nothing usable (2026-10-07
#: on the box: Fanatics' sportsbook domain gave Google's blank globe).
MORE_DOMAINS = {
    "fanatics": ("fanaticsbetting.com", "fanatics.com"),
    "thescorebet": ("thescore.com",),
}
PNG_SIG = b"\x89PNG\r\n\x1a\n"
#: Every image a browser draws in an <img>, by its first bytes. On the box
#: theScore and Kalshi answered with real icons that were not PNGs.
SIGS = ((PNG_SIG, "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF87a", "gif"),
        (b"GIF89a", "gif"), (b"\x00\x00\x01\x00", "ico"))
EXTS = ("png", "jpg", "gif", "webp", "ico")
MIN_BYTES = 600          # Google's placeholder globe and a 16px favicon are smaller
AGENT = "Mozilla/5.0 (compatible; QellysBook/1.0; +https://qellysbook.com)"


def candidates(domain: str) -> list[str]:
    """Where a book's square icon usually is, best first."""
    return [f"https://{domain}/apple-touch-icon.png",
            f"https://{domain}/apple-touch-icon-180x180.png",
            f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
            "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON"
            f"&fallback_opts=TYPE,SIZE,URL&url=https://{domain}&size=128"]


def _get(url: str, timeout: float = 12.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "image/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def kind(raw: bytes) -> str:
    """The image's file extension from its first bytes, or "" if it is not one."""
    if not raw:
        return ""
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    for sig, ext in SIGS:
        if raw.startswith(sig):
            return ext
    return ""


def usable(raw: bytes) -> bool:
    """A real image, big enough to be a mark and not a placeholder."""
    return bool(kind(raw)) and len(raw) >= MIN_BYTES


def fetch_all(out_dir: Path = OUT_DIR, get=_get, domains: dict | None = None) -> dict:
    """Fetch every book's icon; write the files and the manifest; return the manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    got: dict = {}
    misses: dict = {}
    for key, domain in (domains or BOOK_DOMAINS).items():
        last = ""
        urls = [u for d in (domain, *MORE_DOMAINS.get(key, ())) for u in candidates(d)]
        for url in urls:
            try:
                raw = get(url)
            except Exception as exc:                            # noqa: BLE001
                last = f"{url} → {type(exc).__name__}"
                continue
            if not usable(raw):
                last = f"{url} → {len(raw)} bytes, not a usable image"
                continue
            ext = kind(raw)
            for old in EXTS:                     # one file per book, whatever it was before
                (out_dir / f"{key}.{old}").unlink(missing_ok=True)
            (out_dir / f"{key}.{ext}").write_bytes(raw)
            got[key] = {"from": url, "bytes": len(raw), "file": f"{key}.{ext}"}
            break
        else:
            misses[key] = last
    manifest = {"keys": sorted(got), "icons": got, "missing": misses,
                "files": {k: got[k]["file"] for k in sorted(got)},
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> int:
    try:
        m = fetch_all()
    except PermissionError as exc:
        # The folder was made by root (a pull or an earlier run as root), so
        # the qellys user cannot write into it. One command fixes it.
        print(f"Cannot write {exc.filename}: the folder belongs to another user.\n"
              f"Fix it once, then run this again:\n"
              f"  sudo chown -R qellys:qellys {OUT_DIR}")
        return 1
    for k in m["keys"]:
        print(f"  ok   {k:<12} {m['icons'][k]['bytes']:>6} B  {m['icons'][k]['from']}")
    for k, why in m["missing"].items():
        print(f"  --   {k:<12} {why}")
    print(f"{len(m['keys'])} icons in {OUT_DIR}; {len(m['missing'])} missing. "
          "The sheet shows an icon the next time it opens.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
