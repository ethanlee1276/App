#!/usr/bin/env python3
"""Run the hypothesis lab: the LLM proposes, the arithmetic disposes.

    python3 hypotheses.py                # propose (one paid API call) + test
    python3 hypotheses.py --show         # current hypotheses and verdicts
    python3 hypotheses.py --retest       # free: re-try everything stored
    python3 hypotheses.py --dry-run      # print the evidence pack, call nothing

This is the ONLY command in the entire learning loop that spends money:
one structured-output request to claude-opus-5 (roughly a cent or two per
run at current prices — the exact token usage prints after each call).
Everything downstream is the same free arithmetic as the rest of the
ladder: proposals are validated against the miner's own menu, tried by
the same calibration z + false-discovery tribunal, re-tried every settle
pass, and enforced only through the veto gate every sport already
consults.

Setup: add ``ANTHROPIC_API_KEY=sk-ant-...`` to secrets.local (gitignored,
same file as the odds keys). Optional: ``QELLYS_LLM_MODEL=...`` to
override the model.
"""

from __future__ import annotations

import argparse
import json

from engine import hypotheses as hyp
from engine import ledger

# claude-opus-5, per million tokens — used only for the printed estimate.
PRICE_IN, PRICE_OUT = 5.00, 25.00


def _print_store(store: dict) -> None:
    hyps = store.get("hypotheses") or []
    if not hyps:
        print("No hypotheses stored yet — run `python3 hypotheses.py` "
              "with an ANTHROPIC_API_KEY in secrets.local.")
    for h in hyps:
        dims = ", ".join(f"{d}={v}" for d, v in (h.get("dims") or {}).items())
        scope = f"{h['sport']}:{h.get('market') or 'all markets'}"
        mark = {"confirmed": "✓", "rejected": "✗",
                "collecting": "…"}.get(h.get("status"), "?")
        print(f"  {mark} [{scope}] {dims}")
        print(f"     {h.get('claim', '')}")
        if h.get("reading"):
            print(f"     {h['reading']}"
                  + ("  ← VETOING PICKS" if h.get("action") == "close" else ""))
        elif h.get("status") == "collecting":
            print(f"     collecting: {h.get('n', 0)}/{hyp.MIN_N} matching "
                  "graded bets")
    watch = store.get("watchlist") or []
    if watch:
        print("\n  watchlist (not testable in the miner's dimensions):")
        for w in watch:
            print(f"   · {w}")


def main() -> None:
    ap = argparse.ArgumentParser(description="The hypothesis lab.")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--retest", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the evidence pack and exit — no API call")
    args = ap.parse_args()

    lconn = ledger.connect()
    if args.show:
        _print_store(hyp.load())
        return
    if args.retest:
        store = hyp.retest(lconn)
        print("Retested against the current journal:\n")
        _print_store(store)
        return
    if args.dry_run:
        print(json.dumps(hyp.evidence_pack(lconn), indent=1))
        return

    try:
        store = hyp.propose(lconn)
    except hyp.HypothesisUnavailable as e:
        print(f"hypothesis lab unavailable: {e}")
        return
    usage = store.get("usage") or {}
    cost = (usage.get("input_tokens", 0) * PRICE_IN
            + usage.get("output_tokens", 0) * PRICE_OUT) / 1_000_000
    print(f"Model: {store.get('model')}  "
          f"tokens in/out: {usage.get('input_tokens', 0):,}/"
          f"{usage.get('output_tokens', 0):,}  (~${cost:.3f})\n")
    _print_store(store)
    print("\nEvery stored hypothesis is re-tested free on each settle "
          "pass; confirmed hot closures veto picks through the same gate "
          "as the miner.")


if __name__ == "__main__":
    main()
