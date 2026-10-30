"""League headlines → web/data/news.json. See engine/sources/news.py
for what may be shown and why — the policy lives beside the parser.

Run: python3 news_build.py [--out web/data/news.json]
"""

import argparse
import json
import os
from pathlib import Path

from engine.sources import news


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/news.json")
    args = ap.parse_args()
    built = news.build_all()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Keep yesterday's headlines over a blank page: a league whose every
    # feed failed this time (offline dev box, a publisher's hiccup) keeps
    # the headlines it had — and the file is written anyway, with why each
    # feed failed, so `curl …/data/news.json` answers what went wrong. It
    # used to return without writing, which left a file from 2026-09-01
    # with no headlines and no reason for two months (the page hides any
    # headline older than four days, so old ones never pass for news).
    if out.exists():
        try:
            old = json.loads(out.read_text())
        except (OSError, ValueError):
            old = {}
        for sport, rows in ((old or {}).get("sports") or {}).items():
            if sport not in built["sports"] and rows:
                built["sports"][sport] = rows
    if built.get("errors"):
        print("news: " + "; ".join(f"{s} {src}: {why}" for s, d in built["errors"].items()
                                   for src, why in d.items())[:600])
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(built, indent=1))
    os.replace(tmp, out)
    n = sum(len(v) for v in built["sports"].values())
    print(f"news: {n} headline(s) across {len(built['sports'])} sport(s)")


if __name__ == "__main__":
    main()
