#!/usr/bin/env python3
"""Run the engine over a slate and write recommendations JSON for the web UI.

Usage:
    python3 generate.py                       # uses data/sample_slate.json
    python3 generate.py path/to/slate.json
    python3 generate.py --min-confidence 7    # tighten the rules
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.pipeline import run_slate
from engine.rules import RuleConfig
from engine import gate

ROOT = Path(__file__).parent
DEFAULT_SLATE = ROOT / "data" / "sample_slate.json"
OUT = ROOT / "web" / "data" / "recommendations.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate NFL prop recommendations.")
    ap.add_argument("slate", nargs="?", default=str(DEFAULT_SLATE),
                    help="Path to a slate JSON file.")
    ap.add_argument("--min-confidence", type=float, default=6.0)
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    config = RuleConfig(min_confidence=args.min_confidence, min_edge=args.min_edge)
    result = run_slate(args.slate, config)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gate.publish(result, out_path)

    c = result["counts"]
    print(f"Analyzed {c['props_analyzed']} props → {c['recommended']} recommended")
    print(f"Wrote {out_path}")
    for r in result["recommendations"]:
        flag = "✅" if r["recommended"] else "  "
        print(f"  {flag} {r['grade']:>11}  conf {r['confidence']:>4}  "
              f"edge {r['edge']:+.1%}  {r['headline']}")


if __name__ == "__main__":
    main()
