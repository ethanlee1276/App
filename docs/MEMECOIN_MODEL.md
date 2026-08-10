# Rocket Radar — Solana Meme Coin Tracker (Website Edition, 2026)

> Canonical spec for the meme-coin tracker, distilled from the operator's
> "Rocket Radar: Solana Meme Coin Tracker Build Specification" PDF plus
> the research behind it. The engine implements the free-tier slice of
> it; the **Implementation Map** at the bottom says exactly which signal
> lives where in code, which are partial, and which are parked behind
> paid firehose feeds. When the code and this document disagree, that is
> a bug — file it. Run `python3 launch.py --memes` for a live probe.

This page is deliberately NOT a sport. It journals nothing, it grades
nothing, it recommends nothing, and it never touches the sports ledger
or the learning ladder. It is a radar screen — and per the spec, the
danger channel is drawn as loudly as the momentum channel.

---

## 1. The Honest Frame — Base Rates Before Signals

These numbers render at the top of the page, above every score, because
they are the most important thing on it:

- **~1.4%** of pump.fun tokens ever "graduate" (complete their bonding
  curve and reach a real DEX listing). The overwhelming default outcome
  of a new meme coin is death.
- **60%** of meme-coin traders lose money; only about **3%** ever clear
  $1,000 in profit.
- **82.8%** of high-return Solana meme tokens show evidence of
  artificial growth patterns — coordinated wallets, manufactured volume
  (arXiv:2507.01963, the study the wash rule is lifted from).
- **41.4%** of Solana meme-coin DEX volume is wash trading (VanEck
  research).
- The **median rug pull completes in under an hour** from launch, and
  the median holding time across meme trades is roughly **62 seconds**.

The spec's own conclusion, quoted because it is the design brief: *"a
tracker's genuine value is filtering scams and enforcing disciplined
exits, not predicting moonshots."* Everything below is built to that
sentence.

## 2. The Two Hard Rules (enforced structurally, not by convention)

1. **Momentum and risk are two scores that never blend.** One number
   that averages "it's igniting" with "you can't get out" hides the
   danger inside the excitement. `momentum_score` and `risk_score` are
   separate functions with separate outputs, and the tests pin that no
   composite of the two exists anywhere.
2. **Risk is a GATE, not a discount.** A coin with RiskScore ≥ 60 never
   appears on the rocket list, no matter its momentum. The full board
   still shows it (dimmed, with reasons on hover) because "filtered out"
   and "never seen" must not look identical. The exit channel ignores
   the gate entirely — a dangerous coin crashing is exactly what the
   danger channel is for.

A third rule rides along from the research: **no classic TA.** RSI,
MACD, Bollinger bands are built for markets with meaningful multi-period
structure; on sub-minute meme charts they are mostly noise. Order flow —
who is buying, how many distinct wallets, and whether the rate of change
is itself increasing — is the model.

## 3. Data Sources

**Neither Phantom nor Axiom exposes a public API** — the spec's own
first finding. Their discovery columns are reconstructed from the
primary sources those terminals themselves sit on:

| Source | Cost | What it contributes |
|---|---|---|
| **GeckoTerminal** (`api.geckoterminal.com`) | free, keyless, ~30 rpm | New-pools + trending-pools discovery, and the free tier's crown jewel: **unique buyers and sellers per window** — the anti-wash signal raw volume cannot fake cheaply |
| **DexScreener** (`api.dexscreener.com`) | free, keyless, 300 rpm (pairs) | Batched pair snapshots (30 mints per call): price, liquidity, FDV, per-window volume and price change, buy/sell counts, pair age, socials, and the **paid-boost flag** |
| **Our own snapshot tape** (`data/cache/memecoin_history.jsonl`) | free | Per-coin sightings each refresh; prunes at 6 h. No free endpoint hands out per-minute history, so **acceleration — the core "igniting" signal — comes from our own polling**, exactly like the sports line-movement tape |

The firehose tier the spec prices out (PumpPortal WebSockets, Helius
gRPC/LaserStream, Solana Tracker, Birdeye paid tiers) is **parked**, not
forgotten — the map in §7 lists every signal that needs it.

DexScreener boosts are read twice: once as a discovery roster (boosted
tokens are tokens someone wants seen) and once as a **risk point** —
paid promotion is a signal, just not the one the promoter intends.

## 4. Indicators (built, free tier)

Per coin, `engine/memecoins.py::indicators` computes:

- **Volume acceleration** — second derivative of 5-minute volume across
  our last three sightings, per minute². `None` below three sightings:
  zero would claim "steady" about a coin nobody has watched long enough
  to say.
- **Unique-buyer growth** — same second derivative over GeckoTerminal's
  distinct buying wallets. Broad, accelerating wallet count is genuine
  virality; volume from a few wallets is wash trading.
- **Buy/sell pressure trend** — the 5-minute buys-per-sell ratio minus
  the 1-hour ratio. Positive = pressure building *now*.
- **Price acceleration** — from the tape when it exists; before that, a
  window proxy (5-minute change vs the hour's pace restated per five
  minutes — positive means parabolic onset).
- **Vol spike** — m5 volume vs its share of the hour (1.0 = steady).
- **Liq/MC, Vol/MC, pair age** — structure and lifecycle context.
- **Wash flag** — volume spike > 500% while price moves < 5%: volume
  with no one in it (thresholds verbatim from arXiv:2507.01963).
- **LP-drop proxy** — liquidity down > 20% since our last sighting. The
  spec ranks liquidity removal as the single most destructive event a
  holder can experience, and this is the free tier's only eye on it.

## 5. Scoring

**MomentumScore (0–100), cohort-relative.** *"A raw $50k volume means
nothing without context"* — every component is a percentile against the
live board, and a coin's velocity is measured against its own history.
Weights, restated because they are NOT the spec's table: the spec
assigns smart-money 25%, holder velocity 10%, social 5% — all
firehose-tier inputs this build does not have. Their 40 points are
redistributed across the order-flow signals we do measure, preserving
the spec's ordering (acceleration and unique buyers on top):

| Component | Weight | Spec's own weight |
|---|---|---|
| Volume acceleration | 30% | 25% |
| Unique-buyer growth | 30% | 20% |
| Buy/sell pressure trend | 25% | 15% |
| Price acceleration | 15% | (part of momentum 25%) |

Missing components score at the cohort median, not zero — a coin seen
once must not be punished for our tape being short.

**RiskScore (0–100), higher = more dangerous, with reasons attached:**

| Flag | Points | Why |
|---|---|---|
| Liquidity < $5,000 | +40 | exit-impossible for anyone but the dev |
| Liq/MC < 3% | +25 | spec's threshold: one sell craters it |
| Wash-trade signature | +30 | the arXiv rule above |
| Liquidity down >20% since last sighting | +40 | LP pull in progress |
| Age < 30 minutes | +15 | median rug dies inside an hour |
| Paid DexScreener boost | +10 | someone is paying to be seen |
| No socials at all | +10 | no identity to burn |

**Exit signals** (the "about to crash" channel, spec priority order,
free-tier subset): liquidity leaving → buy/sell ratio flipping under 1
(distribution) → volume rising while unique buyers fade (a few wallets
selling into thinning demand) → price and buyer momentum rolling over
together (divergence).

## 6. Where It Lives

| Piece | File |
|---|---|
| Fetches + pure parsers (GT pools, DS pairs/boosts) | `engine/sources/dexes.py` |
| Tape, indicators, both scores, gate, exits, board | `engine/memecoins.py` |
| Discovery → enrich → score → `web/data/memecoins.json` | `memes_build.py` |
| Launcher: refresh each cycle + `--memes` probe + doctor rows | `launch.py` |
| The page (nav "Meme Coins", `#memes`) | `web/index.html`, `web/js/app.js::renderMemes` |
| Tests (fixtures, both hard rules, wash thresholds, tape pruning) | `tests/test_memecoins.py` |

The sandbox that wrote the parsers cannot reach either provider (403 at
the proxy — the same story as statsapi and Savant, both of which work on
the machine that runs the builds). `python3 launch.py --memes` is the
live-shape probe: zero coins with both sources declining means the
machine can't reach the feeds; zero coins with clean fetches means a
payload shape moved and `engine/sources/dexes.py` needs a look.

## 7. Implementation Map — built vs parked

**Built, free tier:** discovery (GT new + trending + DS boost roster),
batched enrichment, snapshot tape, volume/price/buyer acceleration,
pressure trend, vol spike, liq/MC, wash flag, LP-drop proxy, boost and
no-socials risk points, cohort-percentile MomentumScore, gated
RiskScore with reasons, exit channel, the base-rates honesty block, the
full dimmed-not-hidden board.

**Parked — each needs the paid firehose tier, and each absence is
stated on the page rather than silently scored as safe:**

| Parked signal | What it needs |
|---|---|
| Smart-money wallet scoring (following wallets with real hit rates) | indexed wallet P&L (Birdeye/Nansen-class, paid) |
| Holder velocity (net new holders/min) | token-holder snapshots per minute (Helius gRPC) |
| Bundle & sniper detection (same-block coordinated buys) | block-level tx streams (PumpPortal/LaserStream) |
| Dev-wallet sell alerts | creator-wallet tracing (Helius webhooks) |
| Bonding-curve stage tracking (pump.fun internals) | PumpPortal WebSocket firehose |
| Mint/freeze authority + honeypot checks | RugCheck/GoPlus API (blocked here; probe-able on the laptop) |

**Never building:** RSI/MACD/Bollinger overlays (noise at this
timescale, per §2), any buy-signal framing, any journaling of coins
into the betting ledger, any blend of momentum and risk into one score.
