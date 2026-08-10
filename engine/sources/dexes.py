"""Solana DEX data for Rocket Radar — free, keyless, poll-based.

The build spec (docs/MEMECOIN_MODEL.md) is written around a streaming
stack: PumpPortal WebSockets, Helius gRPC, paid Birdeye tiers. This repo
is a poll-and-rebuild site with a 60-second refresh loop and a rule that
broad coverage rides free feeds. So Rocket Radar runs on the two free
keyless providers the spec itself names as the cheap layer, and the
firehose tier is deliberately parked (see the doc's implementation map):

  DexScreener (api.dexscreener.com) — free, no key. 300 req/min on the
    pair endpoints, 60 req/min on profiles/boosts. One batch call returns
    up to 30 tokens' pairs: price, liquidity, FDV, buy/sell counts,
    volume and price change per window, pair age, socials, and whether
    someone is PAYING to promote the token (boosts — which this model
    treats as a risk signal, not a quality one).
  GeckoTerminal (api.geckoterminal.com) — free, no key, ~30 req/min. Its
    pool objects carry the one thing DexScreener's free tier lacks:
    UNIQUE BUYERS AND SELLERS per window, which the spec ranks above raw
    volume ("genuine virality shows broad, accelerating wallet count, not
    just volume from a few wallets — that's wash trading").

Neither Phantom nor Axiom exposes a public API — the spec's own first
finding — so their discovery feeds are reconstructed from these primary
sources, which is what Axiom-style terminals are themselves built on.

Every parser here is PURE and fixture-tested; every fetch goes through
the shared caching layer with short TTLs. The sandbox cannot reach either
host (403 at the proxy, same as statsapi and Savant, both of which work
on the machine that runs the builds) — `launch.py --memes` is the probe
that verifies live shape, and it says so loudly when zero pools parse.
"""

from __future__ import annotations

from ..sources.fetch import fetch_text, DataUnavailable

import json

DEX_BASE = "https://api.dexscreener.com"
GT_BASE = "https://api.geckoterminal.com/api/v2"

#: Meme coins move in minutes; a cached snapshot older than this is a
#: painting of a market that no longer exists. Still cached, because the
#: 60-second site refresh must not turn into 60 requests a minute.
HOT_TTL = 55
#: Discovery lists (trending/new/boosts) can be a little staler.
DISCOVERY_TTL = 120


def _get_json(url: str, cache_name: str, ttl: int):
    text = fetch_text(url, cache_name, ttl=ttl)
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise DataUnavailable(f"{url} returned non-JSON "
                              f"({len(text or '')} bytes)") from exc


# --- fetches (thin, cached) --------------------------------------------------
def fetch_new_pools(page: int = 1):
    """GeckoTerminal's newest Solana pools — the 'New Pairs' column."""
    return _get_json(f"{GT_BASE}/networks/solana/new_pools?page={page}",
                     f"gt_new_pools_{page}.json", DISCOVERY_TTL)


def fetch_trending_pools(page: int = 1):
    """GeckoTerminal's trending Solana pools — the momentum cohort."""
    return _get_json(f"{GT_BASE}/networks/solana/trending_pools?page={page}",
                     f"gt_trending_{page}.json", DISCOVERY_TTL)


def fetch_top_boosts():
    """DexScreener's most-boosted tokens. Boosts are PAID promotion —
    a discovery source and a risk flag in the same payload."""
    return _get_json(f"{DEX_BASE}/token-boosts/top/v1",
                     "dex_boosts_top.json", DISCOVERY_TTL)


def fetch_pairs_for(mints: list[str], chain: str = "solana"):
    """DexScreener pair snapshots for up to 30 mints in ONE request."""
    batch = ",".join(mints[:30])
    return _get_json(f"{DEX_BASE}/tokens/v1/{chain}/{batch}",
                     f"dex_pairs_{hash(batch) & 0xffffffff:x}.json", HOT_TTL)


# --- pure parsers ------------------------------------------------------------
def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_gt_pools(payload) -> list[dict]:
    """GeckoTerminal pool objects → flat rows keyed by MINT.

    The mint lives in `relationships.base_token.data.id` as
    "solana_<mint>" — the attributes block does not carry it, and the
    pool ADDRESS is not the token: one token trades in many pools, and
    everything downstream keys by mint so pools can be aggregated.
    """
    out = []
    for pool in ((payload or {}).get("data") or []):
        at = pool.get("attributes") or {}
        rel = ((pool.get("relationships") or {})
               .get("base_token") or {}).get("data") or {}
        mint = str(rel.get("id") or "")
        mint = mint.split("_", 1)[1] if "_" in mint else mint
        if not mint:
            continue
        tx = at.get("transactions") or {}
        row = {
            "mint": mint,
            "name": str(at.get("name") or "").split(" / ")[0].strip(),
            "pool": at.get("address"),
            "price_usd": _f(at.get("base_token_price_usd")),
            "fdv": _f(at.get("fdv_usd")),
            "market_cap": _f(at.get("market_cap_usd")),
            "liquidity": _f(at.get("reserve_in_usd")),
            "created_at": at.get("pool_created_at"),
            "price_change": {w: _f((at.get("price_change_percentage")
                                    or {}).get(w))
                             for w in ("m5", "h1", "h6", "h24")},
            "volume": {w: _f((at.get("volume_usd") or {}).get(w))
                       for w in ("m5", "h1", "h6", "h24")},
        }
        # The free tier's crown jewel: unique buyers/sellers per window.
        for w in ("m5", "m15", "m30", "h1", "h24"):
            t = tx.get(w) or {}
            if t:
                row[f"tx_{w}"] = {
                    "buys": t.get("buys"), "sells": t.get("sells"),
                    "buyers": t.get("buyers"), "sellers": t.get("sellers"),
                }
        out.append(row)
    return out


def parse_dex_pairs(payload) -> dict:
    """DexScreener pairs → {mint: aggregated row}.

    ONE TOKEN, MANY POOLS. Liquidity and volume are summed across the
    token's pools; price/FDV/age come from the PRIMARY pool (largest
    liquidity), which is the spec's own dedupe rule. Boost status rides
    along because paid promotion is a signal — just not the one the
    promoter intends.
    """
    pairs = payload if isinstance(payload, list) else \
        ((payload or {}).get("pairs") or [])
    by_mint: dict = {}
    for p in pairs or []:
        mint = ((p.get("baseToken") or {}).get("address") or "").strip()
        if not mint:
            continue
        by_mint.setdefault(mint, []).append(p)
    out: dict = {}
    for mint, ps in by_mint.items():
        ps.sort(key=lambda p: _f((p.get("liquidity") or {}).get("usd")) or 0,
                reverse=True)
        prime = ps[0]
        socials = ((prime.get("info") or {}).get("socials") or [])
        out[mint] = {
            "mint": mint,
            "symbol": (prime.get("baseToken") or {}).get("symbol", ""),
            "name": (prime.get("baseToken") or {}).get("name", ""),
            "price_usd": _f(prime.get("priceUsd")),
            "fdv": _f(prime.get("fdv")),
            "market_cap": _f(prime.get("marketCap")),
            "liquidity": sum(_f((p.get("liquidity") or {}).get("usd")) or 0
                             for p in ps),
            "pools": len(ps),
            "dex": prime.get("dexId", ""),
            "pair_created_at": prime.get("pairCreatedAt"),
            "price_change": {w: _f((prime.get("priceChange") or {}).get(w))
                             for w in ("m5", "h1", "h6", "h24")},
            "volume": {w: sum(_f((p.get("volume") or {}).get(w)) or 0
                              for p in ps)
                       for w in ("m5", "h1", "h6", "h24")},
            "txns": {w: {
                "buys": sum(int((p.get("txns") or {}).get(w, {})
                                .get("buys") or 0) for p in ps),
                "sells": sum(int((p.get("txns") or {}).get(w, {})
                                 .get("sells") or 0) for p in ps),
            } for w in ("m5", "h1", "h6", "h24")},
            "has_socials": bool(socials),
            "boosted": bool((prime.get("boosts") or {}).get("active")),
            "url": prime.get("url", ""),
        }
    return out


def parse_boosts(payload) -> list[str]:
    """Solana mints from a boosts list — the PAID-promotion roster."""
    return [str(b.get("tokenAddress") or "")
            for b in (payload or [])
            if b.get("chainId") == "solana" and b.get("tokenAddress")]
