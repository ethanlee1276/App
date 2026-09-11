"""RugCheck — the free rug-pull audit the risk gate was missing.

Until this module, the two worst switches a meme-coin dev holds were in
the doc's PARKED table: **mint authority** (the dev can print more
supply at will) and **freeze authority** (the dev can freeze YOUR
tokens — the honeypot switch). Both are on-chain facts, and RugCheck
(rugcheck.xyz) exposes them keyless per mint, along with how much of
the liquidity pool is locked and its own named risk findings:

    https://api.rugcheck.xyz/v1/tokens/{mint}/report

TRI-STATE, NOT BOOLEAN, and it is load-bearing: `True` means the
authority is ACTIVE (danger), `False` means RENOUNCED (the switch is
off), and `None` means the field was absent from the payload — and an
absent field must never read as safe. The same NULL rule every
journaled dimension in this repo follows; a shape drift at RugCheck
degrades us to "unmeasured", never to "all clear".

Authorities flip rarely (renouncing is one irreversible transaction),
so the cache TTL is long and the lookups cover the head of the board
rather than all sixty coins — this feed's rate limits are undocumented,
and the meme loop ticks every 15 seconds.

Fixture-tested; the sandbox cannot reach the host (403 at the proxy,
like every live feed here) — `launch.py --memes` is the probe, and a
"rugcheck: N lookup(s) declined" note names the outage.
"""

from __future__ import annotations

from .fetch import DEFAULT_AGENT, fetch_json, DataUnavailable
from .solrpc import B58

RUG_BASE = "https://api.rugcheck.xyz/v1"
#: Renouncing an authority is one irreversible transaction; fifteen
#: minutes of cache cannot miss anything that matters.
RUG_TTL = 900


def fetch_report(mint: str):
    if not B58.match(mint or ""):
        raise DataUnavailable(f"not a plausible mint: {mint!r}")
    return fetch_json(f"{RUG_BASE}/tokens/{mint}/report",
                      f"rug_{mint}.json", ttl=RUG_TTL,
                      user_agent=DEFAULT_AGENT)


def _authority(payload: dict, token: dict, key: str):
    """ACTIVE / RENOUNCED / UNKNOWN for one authority key.

    Key present with a null-ish value = renounced (False). Key absent
    everywhere = the API did not answer the question (None) — scored as
    nothing, shown as nothing, never as safe.
    """
    for holder in (payload, token):
        if key in holder:
            return bool(holder.get(key))
    return None


def parse_report(payload) -> dict | None:
    """RugCheck's report → the fields the risk gate consumes."""
    if not isinstance(payload, dict):
        return None
    token = payload.get("token") if isinstance(payload.get("token"), dict) \
        else {}
    out = {
        "mint_auth": _authority(payload, token, "mintAuthority"),
        "freeze_auth": _authority(payload, token, "freezeAuthority"),
        "lp_locked_pct": None,
        "dangers": [],
    }
    # LP lock: the best-locked market speaks for the token — a coin with
    # one locked pool and one stray micro-pool is not "unlocked".
    best = None
    for m in (payload.get("markets") or []):
        if not isinstance(m, dict):
            continue
        lp = m.get("lp") if isinstance(m.get("lp"), dict) else {}
        try:
            pct = float(lp.get("lpLockedPct"))
        except (TypeError, ValueError):
            continue
        best = pct if best is None else max(best, pct)
    out["lp_locked_pct"] = best
    # RugCheck's own named findings — only the ones IT calls danger.
    for r in (payload.get("risks") or []):
        if isinstance(r, dict) and str(r.get("level", "")).lower() == "danger":
            name = str(r.get("name") or "").strip()
            if name:
                out["dangers"].append(name[:60])
    if (out["mint_auth"] is None and out["freeze_auth"] is None
            and out["lp_locked_pct"] is None and not out["dangers"]):
        return None            # the payload answered nothing we asked
    return out
