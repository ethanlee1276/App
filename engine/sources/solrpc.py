"""Solana public RPC — holder concentration for Rocket Radar.

The one Phantom/Axiom holder metric the FREE tier can honestly reach:
`getTokenLargestAccounts` returns a mint's twenty largest token accounts
and `getTokenSupply` the denominator, both on the public mainnet RPC,
keyless. That is enough for "the top wallets hold X% of supply" — the
insider-concentration flag — without the paid indexers everything else
in the holder family needs (holder velocity, sniper bundles, dev-wallet
tracing all remain parked; see docs/MEMECOIN_MODEL.md §7).

THE LP CAVEAT, stated here because the numbers are wrong without it:
`getTokenLargestAccounts` returns token ACCOUNTS, not people. For a
live meme coin the single largest account is almost always the trading
pool's own vault (or the pump.fun bonding curve) — market structure,
not an insider. Mapping every vault to its pool exactly needs a curated
list of AMM authority addresses, which this repo will not hand-maintain
(a wrong base58 constant misclassifies silently — worse than the
approximation it replaces). So the parser reports BOTH readings:

  top1_share       largest single account / supply (usually the pool)
  top10_ex1_share  accounts 2..11 / supply — the headline "top-10
                   holders" number, labelled on the page as excluding
                   the largest account
  second_share     account #2 alone — the biggest plausible WALLET

`getTokenSupply` + `getTokenLargestAccounts` ride ONE batched JSON-RPC
POST per mint, cached ten minutes — concentration moves slower than
price, and the public RPC's rate limits are real.

The shared fetch layer is GET-only, so this module carries its own POST
with the same discipline as fetch_json: parse first, cache second, and
a poisoned cache entry costs one request to recover from, not the TTL.
Fixture-tested; the sandbox cannot reach the RPC (403 at the proxy,
same as every other live feed here) — `launch.py --memes` is the probe.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request

from .fetch import CACHE_DIR, DataUnavailable

RPC_URL = "https://api.mainnet-beta.solana.com"
#: Concentration drifts in minutes, not seconds; the public RPC is shared.
HOLDER_TTL = 600

#: Measured on Ethan's machine, first live run: twenty back-to-back
#: batch POSTs every 15 seconds = HTTP 429 on all twenty, forever —
#: because a FAILED lookup writes no cache, so the live loop re-fired
#: the whole burst every tick. Three mechanisms stop that:
#:   PACE_S      a breath between actual requests (cache hits are free)
#:   first-429   the caller stops the run's remaining lookups (fuel off)
#:   COOLDOWN_S  a file stamp that stands ALL lookups down for a window,
#:               file-based because every build tick is a fresh process.
PACE_S = 0.5
COOLDOWN_S = 180
_COOLDOWN = CACHE_DIR / "sol_rpc_cooldown"


def _cooling() -> float | None:
    """Seconds of cooldown remaining, or None when clear."""
    try:
        age = time.time() - _COOLDOWN.stat().st_mtime
    except OSError:
        return None
    return COOLDOWN_S - age if age < COOLDOWN_S else None


def _note_429() -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _COOLDOWN.write_text(str(time.time()))
    except OSError:
        pass

#: A Solana address, so a mint from a third-party feed can be trusted in
#: a URL, a filename and an onclick before anything downstream sees it.
B58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{25,50}$")


def _rpc_batch(calls: list[tuple[str, list]], cache_name: str,
               ttl: int = HOLDER_TTL, timeout: int = 30):
    """One JSON-RPC batch POST, parse-first-cache-second."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            path.unlink(missing_ok=True)
    left = _cooling()
    if left is not None:
        raise DataUnavailable(
            f"Solana RPC cooling down after a 429 — retries in {left:.0f}s",
            status=429)
    payload = [{"jsonrpc": "2.0", "id": i, "method": m, "params": p}
               for i, (m, p) in enumerate(calls)]
    req = urllib.request.Request(
        RPC_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    time.sleep(PACE_S)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001 — stale cache beats no answer
        if getattr(exc, "code", None) == 429:
            _note_429()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                path.unlink(missing_ok=True)
        raise DataUnavailable(f"Solana RPC: {exc}",
                              status=getattr(exc, "code", None)) from exc
    path.write_text(text, encoding="utf-8")
    return data


def fetch_holder_slice(mint: str):
    """Supply + twenty largest accounts for one mint, one request."""
    if not B58.match(mint or ""):
        raise DataUnavailable(f"not a plausible mint: {mint!r}")
    return _rpc_batch([("getTokenSupply", [mint]),
                       ("getTokenLargestAccounts", [mint])],
                      f"sol_holders_{mint}.json")


def parse_holder_slice(payload) -> dict | None:
    """Batch response → the three shares, or None when unanswerable.

    None, not zeros: "we could not measure concentration" and "supply is
    perfectly dispersed" must never look identical downstream — the same
    NULL-is-load-bearing rule every journaled dimension here follows.
    """
    by_id = {r.get("id"): r for r in (payload or [])
             if isinstance(r, dict)}
    supply = (((by_id.get(0) or {}).get("result") or {})
              .get("value") or {}).get("amount")
    largest = (((by_id.get(1) or {}).get("result") or {}).get("value")) or []
    try:
        total = int(supply)
    except (TypeError, ValueError):
        return None
    if total <= 0 or not largest:
        return None
    amounts = []
    for acct in largest:
        try:
            amounts.append(int(acct.get("amount")))
        except (TypeError, ValueError):
            continue
    if not amounts:
        return None
    amounts.sort(reverse=True)
    share = lambda xs: round(sum(xs) / total, 4)      # noqa: E731
    return {
        "top1_share": share(amounts[:1]),
        "top10_ex1_share": share(amounts[1:11]),
        "second_share": share(amounts[1:2]) if len(amounts) > 1 else None,
        "n_accounts": len(amounts),
    }
