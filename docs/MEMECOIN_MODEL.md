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
| **Solana public RPC** (`api.mainnet-beta.solana.com`) | free, keyless | `getTokenSupply` + `getTokenLargestAccounts` in one batched POST per mint: **holder concentration** — the one Phantom/Axiom holder metric reachable without a paid indexer. First 20 coins in discovery order, 10-minute cache, because the public RPC's rate limits are real |
| **RugCheck** (`api.rugcheck.xyz`) | free, keyless | Per-mint on-chain audit: **mint authority** (dev can print supply), **freeze authority** (the honeypot switch), **LP locked %**, and RugCheck's own danger-level findings. Tri-state — active / renounced / *unmeasured* — and unmeasured never scores as safe. First 15 coins, 15-minute cache (renouncing is one irreversible transaction; nothing flips fast) |
| **Our own snapshot tape** (`data/cache/memecoin_history.jsonl`) | free | Per-coin sightings each refresh; prunes at 6 h. No free endpoint hands out per-minute history, so **acceleration — the core "igniting" signal — comes from our own polling**, exactly like the sports line-movement tape. Also feeds the page's per-coin sparkline |

The firehose tier the spec prices out (PumpPortal WebSockets, Helius
gRPC/LaserStream, Solana Tracker, Birdeye paid tiers) is **parked**, not
forgotten — the map in §7 lists every signal that needs it.

**Scan cadence — and why it is 15 seconds, not 5.** The launcher runs a
dedicated meme loop (`MEMES_LIVE_S = 15`, its own thread beside the UFC
live poller): every tick refreshes prices/volume/txns via DexScreener
(TTL 12s → 2 batch calls per tick ≈ 8/min against a 300/min budget) and
every ~25s the discovery feed — GT new + trending, the coins-moving-in-
and-out signal — refreshes (TTL 25s → ~4.8/min against GT's ~30/min
TOTAL free budget, which also carries the unique-buyer counts). At the
5-second cadence the operator first asked for, discovery alone would
spend 24 of GT's 30 calls per minute; the first 429 turns "faster" into
"frozen". Every tick lays a snapshot on the tape, so acceleration — the
ignition signal — sharpens 4x versus the old 60-second ride-along. The
page re-pulls the board on a matching ~20s clock, never while a live
chart is open (the candle iframe is the venue's own stream and already
moves second-by-second — that IS the 5-second view).

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
- **Holder concentration** — from the RPC's twenty largest token
  accounts, with the caveat that makes the number honest:
  `getTokenLargestAccounts` returns token *accounts*, not people, and
  for a live coin the largest account is almost always the pool's own
  vault (or the pump.fun bonding curve) — market structure, not an
  insider. Exact vault→pool mapping needs a curated list of AMM
  authority addresses this repo will not hand-maintain (a wrong base58
  constant misclassifies silently), so the parser reports **both
  readings**: `top1_share` (raw largest, usually the pool),
  `top10_ex1_share` (accounts 2–11 — the headline "top-10 holders"
  number, labelled on the page as excluding the largest account), and
  `second_share` (the biggest plausible single wallet). Unmeasured is
  `None`, never zero — "we couldn't look" and "perfectly dispersed"
  must not be the same value.

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
| Freeze authority ACTIVE (RugCheck) | +40 | the dev can freeze your tokens — the honeypot switch |
| Mint authority ACTIVE (RugCheck) | +30 | supply can be printed at will |
| LP < 50% locked (RugCheck) | +20 | unlocked liquidity can be pulled at any moment |
| Each RugCheck danger-level finding (≤3) | +10 | their audit, named on the card |
| Top-10 accounts (pool excluded) > 30% | +20 | the spec's insider-concentration flag |
| One non-pool account > 15% | +15 | a single seller can crater it |
| Paid DexScreener boost | +10 | someone is paying to be seen |
| No socials at all | +10 | no identity to burn |

**Exit signals** (the "about to crash" channel, spec priority order,
free-tier subset): liquidity leaving → buy/sell ratio flipping under 1
(distribution) → volume rising while unique buyers fade (a few wallets
selling into thinning demand) → price and buyer momentum rolling over
together (divergence).

## 6. Where It Lives

**Charts, two kinds, honestly labelled.** The card sparkline is OUR
tape — one point per launcher refresh, up to six hours, no external
bytes. The "Live chart" button opens the venue's own embeddable candle
chart for the coin's primary pool (DexScreener when we have the pair
address, GeckoTerminal's pool embed otherwise) in a single dock — the
same live candles an Axiom terminal shows, because they come from the
same place. One iframe at a time by design; sixty live embeds is a
tab-killer. Every address is base58-validated before it touches an
`onclick` or an iframe `src` — token feeds are attacker-controlled
strings.

**The page is organized as rooms** (the site's shared sub-tab pattern):
**Charts** first — a coin-picker terminal that auto-opens the top
coin's live chart, so the page lands on candles, not a menu — then
**Rocket list**, **Danger channel**, and **Full board** (tiles, the
holder column, gated rows dimmed-not-hidden). The base-rates strip
stays above the tab bar in every room: it is the one block a visitor
must not be able to route around. A chart click from any room walks
you to the Charts room — a chart opening in a hidden panel is a click
that did nothing.

| Piece | File |
|---|---|
| Fetches + pure parsers (GT pools, DS pairs/boosts) | `engine/sources/dexes.py` |
| Holder concentration (Solana RPC, batched, LP caveat) | `engine/sources/solrpc.py` |
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
**carry-tracking** (a coin that leaves trending stays on the scan while
its tape lives — a dying coin leaves trending at exactly the moment the
exit signals matter most), batched enrichment, snapshot tape,
volume/price/buyer acceleration, pressure trend, vol spike, liq/MC,
wash flag, LP-drop proxy, holder concentration (top-10 ex-pool +
single-whale, with the §4 caveat), **mint/freeze authority + LP lock +
named dangers via RugCheck** (tri-state; unmeasured never reads safe),
boost and no-socials risk points, cohort-percentile MomentumScore,
gated RiskScore with reasons, exit channel, "new" badges from first
sighting on our tape, per-coin sparklines, per-coin live venue chart
embeds, the base-rates honesty block, the full dimmed-not-hidden board.

**Parked — each needs the paid firehose tier, and each absence is
stated on the page rather than silently scored as safe:**

| Parked signal | What it needs |
|---|---|
| Smart-money wallet scoring (following wallets with real hit rates) | indexed wallet P&L (Birdeye/Nansen-class, paid) |
| Holder velocity (net new holders/min) and exact LP-vault exclusion | token-holder snapshots per minute (Helius gRPC); curated AMM authority lists |
| Bundle & sniper detection (same-block coordinated buys) | block-level tx streams (PumpPortal/LaserStream) |
| Dev-wallet sell alerts | creator-wallet tracing (Helius webhooks) |
| Bonding-curve stage tracking (pump.fun internals) | PumpPortal WebSocket firehose |

**Never building:** RSI/MACD/Bollinger overlays (noise at this
timescale, per §2), any buy-signal framing, any journaling of coins
into the betting ledger, any blend of momentum and risk into one score.
