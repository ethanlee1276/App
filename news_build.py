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
    # Keep yesterday's headlines over a blank page: every feed failing
    # (offline dev box, ESPN hiccup) publishes nothing rather than
    # overwriting a good file with an empty one.
    if not built["sports"] and out.exists():
        print("news: every feed unavailable — kept the existing file")
        return
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(built, indent=1))
    os.replace(tmp, out)
    n = sum(len(v) for v in built["sports"].values())
    print(f"news: {n} headline(s) across {len(built['sports'])} sport(s)")


if __name__ == "__main__":
    main()
