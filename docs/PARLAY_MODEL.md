# PARLAY INSTRUCTION SET — All Sports
### Companion module to: NFL v2 · Scalpy 2.0 (MLB) · CFB Website Edition · Scalpy 3.0 (NBA) · WNBA Website Edition · Scalpy MMA 1.0

---

## 0) OPERATING DOCTRINE

**A parlay is not a bet type. It is a pricing structure.** It is only ever correct when the structure is mispriced — never because you like three plays.

This module inherits the entire decision spine from the six sport engines: EV-first, de-vig, humility clamp, approval gate, unified grade, fractional Kelly, CLV as scoreboard. Nothing here overrides those. **A parlay leg that would not be a bet on its own is never a bet inside a parlay.** That single sentence eliminates roughly 90% of the tickets anyone wants to build.

### 0.1 What your own engines already say

| Engine | Existing position |
|---|---|
| Scalpy 2.0 (MLB) | "Singles are the default. Parlays are the exception, and only when correlation genuinely helps." |
| Scalpy MMA 1.0 §11.2 | "Parlaying heavy favorites — the single most common way MMA bettors lose money." Bans 3+ fight parlays. |
| Scalpy 3.0 §7.4 | Bans 4+ legs: "the tax exceeds any realistic edge." |
| CFB §8 | "Same-game correlation only when price beats correlated fair value." |
| NFL §9 | "Positively correlated straight bets are one bet wearing two jerseys." |

**This module does not soften any of that.** It formalizes it into a gate system so the model can execute it consistently instead of judging case by case.

### 0.2 The three-leg cap

Hard ceiling: **3 legs. Never 4.** Two legs is the preferred structure and should be the majority of anything published.

Why the cap exists, in numbers. Three independent legs at −110, priced multiplicatively:

```
Single at −110, true 50%:    EV = 0.50 × 0.909 − 0.50        = −4.55%
3-leg at true product, 50%:  EV = 0.125 × 5.96 − 0.875       = −12.5%
```

Vig compounds. A 3-leg ticket of coin flips costs you nearly **three times** what one coin flip costs. Each additional leg multiplies your exposure to the book's margin, and it multiplies your exposure to your own model error — which is the larger of the two dangers.

### 0.3 The uncomfortable truth the model must state out loud

**If three legs are genuinely independent and the book prices them multiplicatively, betting them as three singles strictly dominates the parlay.** Same edge, lower variance, faster bankroll growth, and one bad leg doesn't kill the other two.

This is not an opinion. It follows directly from Kelly: diversifying a fixed edge across independent bets raises expected log growth. There is no configuration of independent legs where the parlay is the better instrument.

**Therefore a parlay is only ever justified by one of four things:**

| Type | Justification | Frequency |
|---|---|---|
| **A — Correlated (SGP)** | The book's correlation model understates true correlation by more than its tax | Rare, and the only structurally sharp parlay |
| **B — Cross-game, true product** | All legs independently +EV, book pays true multiplicative price, you accept worse variance for a specific reason | Uncommon |
| **C — Promo / boost / bonus bet** | The promotion changes the price enough to flip the math | Situational |
| **D — Account health** | Deliberate recreational camouflage per EDGEKEEPER §2.2 (product mix, 10% weight) | Budgeted cost, not a bet |

Type D deserves emphasis because it is the one place a **−EV parlay is correct on purpose.** EDGEKEEPER scores "zero parlays, zero SGPs, zero live bets" as a non-recreational profile flag. A small, cheap, occasional parlay is camouflage that buys account longevity. Book it against a marketing budget line, not the betting bankroll, and never pretend it's a play.

---

## 1) THE MATH — RUN THIS EVERY TIME

### 1.1 Never multiply probabilities

```
WRONG:  P(A ∩ B ∩ C) = P(A) × P(B) × P(C)
RIGHT:  P(A ∩ B ∩ C) = P(A) × P(B|A) × P(C|A,B)
```

Independence is a claim about the world, and inside one game it is almost always false. Scalpy 3.0 §7.2 already establishes the baseline: **any two overs in the same game carry roughly +0.10 correlation** through shared pace and script exposure. There is no such thing as an uncorrelated same-game pair.

### 1.2 The correlation tax

```
Naive product        = Π(dec_i)
Book's quoted price  = dec_quoted
Correlation tax      = 1 − (dec_quoted / Π(dec_i))
```

Typical effective hold on a 3-leg SGP: **15–30%** (Scalpy 3.0 §4.3). Compare that to 4.3–4.8% on sides and totals. You are paying between three and six times the normal margin for the privilege.

### 1.3 The two tests every ticket must pass

**Test 1 — The Price Test.**
```
implied_joint = 1 / dec_quoted
modeled_joint = P(A) × P(B|A) × P(C|A,B)

Require:  modeled_joint − implied_joint ≥ threshold
```

| Legs | Threshold |
|---|---|
| 2 legs | ≥ 5.0 percentage points |
| 3 legs | ≥ 6.0 percentage points |
| 3 legs in a HIGH/EXTREME volatility sport (CFB, MMA) | ≥ 8.0 percentage points |

**Test 2 — The Dominance Test.**
```
EV_parlay   = modeled_joint × (dec_quoted − 1) − (1 − modeled_joint)
EV_singles  = Σ EV_i  at best available price per leg, across all books

Require:  EV_parlay > EV_singles × 1.25
```

The 1.25 multiplier is a variance premium. The parlay must not merely win the EV comparison — it must win it by enough to justify carrying three times the variance and a single point of failure. **If it only ties, bet the singles.** Scalpy 3.0 §7.1 already flags this as "the decision most bettors skip." It is now mandatory.

### 1.4 The worked example the model should internalize

Three legs, each individually approved, post-clamp probabilities 0.68 / 0.65 / 0.62, all in the same game, all positively correlated.

```
Independent joint          = 0.68 × 0.65 × 0.62      = 0.2740  → fair +265
Correlation-adjusted joint = 0.68 × 0.69 × 0.66      = 0.3097  → fair +223
Book's typical SGP quote                              ≈ +180   → implied 0.357

modeled 0.3097 − implied 0.357 = −4.7 points  →  ❌ NO BET
```

For this ticket to clear the 6-point threshold the book would have to offer **+300 or better** on legs whose correlated fair price is +223. Books do not do that. **This is the normal outcome. Publishing "no qualifying parlay" is the system working**, exactly as it is on the singles side.

### 1.5 CLV for parlays

You cannot get a closing parlay price. **Grade every leg's CLV individually and log it against the ticket.** A parlay whose legs collectively beat the close is a good process outcome even when the ticket loses. A parlay that cashes on legs that all lost to the close is a bad win — flag it `CORRELATION_ERROR` or `LUCKY_WIN` per Scalpy 3.0 §12 conventions.

---

## 2) THE SEVEN GATES

Every candidate ticket runs this sequence in order. Fail any gate, kill the ticket. No overrides.

**Gate 1 — Standalone eligibility.**
Every leg must independently clear its sport's approval gate as a single bet: post-clamp edge threshold, grade ≥ 70 (B+ or better), volatility rating acceptable, data freshness verified. **A leg that exists only to complete a ticket is disqualified.**

**Gate 2 — Clash screen.**
Run the full taxonomy in §3. Any Type 1 (mutually exclusive) or Type 4 (blowout) clash is an automatic kill.

**Gate 3 — Correlation sign.**
Estimate ρ for all three pairs. **Net correlation must be positive.** Never build a ticket containing a negatively correlated pair — that is paying a tax for the privilege of betting against yourself.

**Gate 4 — Joint probability.**
Compute via the conditional chain, never the product. Document each conditional and the reasoning behind it.

**Gate 5 — Price test.**
Per §1.3 Test 1.

**Gate 6 — Dominance test.**
Per §1.3 Test 2.

**Gate 7 — Exposure.**
The ticket counts as **one bet** against per-slate bet-count caps, but at **full maximum loss** against bankroll exposure caps. Correlated legs also count against the underlying game's exposure cap.

---

## 3) CLASH TAXONOMY

This is the section that answers "picks clashing with other picks." Seven types, each with a fixed disposition.

### Type 1 — Mutually exclusive
Legs that cannot both win. Not a correlation problem, a logic problem.
> KO victory + fight goes the distance · team under + that team's star way over · pitcher records 21+ outs + his team's F5 under by a blowout margin

**Disposition: automatic kill.** These should never reach a human.

### Type 2 — Script clash
Legs requiring opposite game scripts. Each is fine alone; together one must fail.
> Own QB passing over + own RB rushing over (trailing script vs leading script) · favorite ML + own team's total under while the opponent's total is over

**Disposition: kill.** Sign is reliably negative.

### Type 3 — Possession-pie clash
Legs competing for a finite shared resource: targets, shots, rebounds, plate appearances, carries.
> Two teammates' receiving yards overs · two bigs both rebounds over (Scalpy 3.0: ρ −0.20 to −0.35) · two high-usage teammates both points over

**Disposition: kill for 3-leg tickets.** Permitted only in a 2-leg ticket when the shared pool is *expanding* (a pace-up spot, a vacancy that grew the pie) and you can document why. Default is reject.

### Type 4 — Blowout clash
One leg needs a lopsided result; another needs starters on the field in the fourth quarter.
> Favorite −13.5 + that favorite's RB rushing over · big favorite cover + any starter prop in CFB (where starters get pulled earlier and harder than the NFL) · WNBA star points over + her team as a big favorite — your own WNBA doc calls this **"the classic WNBA parlay trap"**

**Disposition: automatic kill.** This is the most common clash in every sport and the one bettors most consistently miss, because both legs feel like "backing the good team."

### Type 5 — Single point of failure
Multiple legs depending on the same player's availability or usage.
> Same player, two props · a QB's passing yards + his WR's receiving yards + his TE's receptions

**Disposition:** same-player multi-prop is **banned outright** (Scalpy 3.0 §7.4 — "if he sits, everything dies"). Two legs sharing one player's availability is permitted at most once per ticket, and only when the player is confirmed active with a Minutes/Usage Grade of A.

### Type 6 — Hidden duplicate
Legs that are near-restatements of each other. Not incoherent — the opposite problem. The ticket looks like three bets and is really about 1.3.
> Team total over + game total over (ρ +0.55 to +0.70) · player points over + his team total over + game total over

**Disposition:** allowed but **the correlation must be priced, not celebrated.** If two legs correlate above +0.50, treat the ticket as a 2-leg for threshold purposes and require the higher bar. Never count near-duplicates as diversification.

### Type 7 — Direct opposition
Two legs where one player's success is literally the other's failure.
> Hitter total bases over + the opposing starter's strikeouts over · a receiver's yards over + the opposing defense's under

**Disposition: kill.** Strong negative correlation.

---

## 4) NFL

**Anchor rule:** the anchor leg must be a Tier 1 volume market (receptions, pass attempts, carries, completions). Never anchor a ticket on a Tier 3 market (anytime TD, longest reception) — those are the legs that turn a good process into a lottery ticket.

### 4.1 Correlation priors

Marked ⓢ where your engines state the direction; ρ magnitudes are estimates requiring backtest against your own play-by-play history.

| Pairing | ρ | Note |
|---|---|---|
| QB pass yds over ↔ WR1 rec yds over ⓢ | +0.35 to +0.50 | Strongest usable NFL correlation |
| QB pass yds over ↔ own team total over | +0.30 to +0.45 | |
| Team total over ↔ game total over | +0.55 to +0.70 | Type 6 duplicate — count as one |
| RB rush attempts over ↔ own team ML/spread ⓢ | +0.35 to +0.50 | Leading teams run |
| Underdog covers ↔ underdog pass-catcher overs | +0.20 to +0.35 | Trailing → passing volume |
| Both teams' overs (pace link) ⓢ | +0.15 to +0.30 | |
| QB pass TDs ↔ his WR anytime TD | +0.25 to +0.40 | Both Tier 3 — rarely eligible |
| WR1 over ↔ WR2 over, same team ⓢ | −0.10 to +0.10 | Type 3 — reject by default |
| Own QB pass over ↔ own RB rush over | −0.15 to −0.30 | Type 2 script clash |
| Favorite covers ≥10 ↔ that favorite's starter overs | −0.15 to −0.30 | Type 4 |
| QB pass under ↔ his WR over ⓢ | incoherent | Type 7 — auto-kill |

### 4.2 Permitted 3-leg constructions
1. **The passing-game stack.** QB pass yds over + WR1 rec yds over + that team's total over. Only when the game total is ≥ 47 and the spread is inside 7 (no blowout risk either direction).
2. **The trailing-dog stack.** Dog +points + dog QB pass attempts over + dog WR receptions over. The strongest NFL construction because the script that makes leg 1 win *causes* legs 2 and 3.
3. **The shootout.** Game total over + both teams' leading receivers' receptions over. Requires both defenses bottom-10 in pass DVOA and a dome or wind <8mph.

### 4.3 Banned
- Any construction pairing a favorite laying ≥10 with that favorite's skill-position overs
- QB from team A + RB from team A in the same ticket
- Three Tier 3 legs (TDs, longest) in any combination
- Any leg on a player with an unresolved injury designation at ticket build time

### 4.4 Weather override
Wind ≥ 15mph kills all passing-stack constructions outright regardless of edge — the distribution widens faster than the correlation helps. Per NFL §7 wind bands.

---

## 5) MLB

**The lineup rule dominates everything.** Per Scalpy 2.0 §2, no hitter leg is eligible until the lineup is confirmed and the batting-order slot is known. **A parlay containing an unconfirmed hitter is not a conditional parlay — it is not a bet.** Unlike a single, you cannot re-grade one leg of a ticket after posting.

### 5.1 Correlation priors

| Pairing | ρ | Note |
|---|---|---|
| SP strikeouts over ↔ opposing team total under | +0.20 to +0.35 | Cleanest MLB correlation |
| SP outs recorded over ↔ his team ML | +0.20 to +0.35 | Managers leave winners in |
| Hitter total bases over ↔ own team total over | +0.30 to +0.45 | |
| Two hitters, same lineup, both TB over | +0.20 to +0.35 | Shared opposing pitcher and innings |
| F5 under ↔ full-game under | +0.55 to +0.70 | Type 6 duplicate |
| HR prop ↔ game total over | +0.20 to +0.35 | Both Tier 3-ish; size accordingly |
| Leadoff runs scored ↔ 3-hole RBI | +0.25 to +0.40 | Underused, genuinely correlated |
| SP strikeouts over ↔ game total over | −0.15 to −0.30 | Type 2 |
| Hitter TB over ↔ opposing SP K over | −0.25 to −0.40 | Type 7 — auto-kill |
| Two hitters facing the same elite SP, both over | Suppressed jointly | Reject |

### 5.2 Permitted 3-leg constructions
1. **The pitcher stack.** SP strikeouts over + SP outs over + opposing team total under. Highly correlated, and books frequently price the K/outs pair as if independent. **This is the single best 3-leg construction in your entire system** — one player, one mechanism, three markets, all moving together.
2. **The lineup stack.** Two consecutive hitters' TB overs + own team total over, against a weak starter with a park factor ≥ +3% and a confirmed lineup.
3. **The F5 pairing** (2 legs preferred). F5 under + SP strikeouts over. Do not add the full-game under — that's a Type 6 duplicate that adds tax without adding information.

### 5.3 Banned
- Any hitter leg without a confirmed lineup
- Legs from both sides of the same game's run-scoring environment (one team's total over + other team's total under)
- Bullpen-dependent legs (team total unders in games where the starter is on a short leash) combined with anything
- Three hitter legs across three different games — that's a Type B cross-game parlay with no correlation to exploit; bet the singles

### 5.4 Weather and park override
Wind blowing out ≥12mph or a roof status change invalidates every total-linked leg on the ticket. Re-run the gates from Gate 1 — do not patch a leg.

---

## 6) COLLEGE FOOTBALL

**Highest bar in the system.** CFB baseline volatility exceeds the NFL at every tier (CFB §8), the injury information is worst, and December is a different sport. Threshold for a 3-leg ticket is **8 points**, not 6.

### 6.1 The scheme-sign rule

Per CFB §8, a big favorite covering correlates with the Under for methodical, clock-draining teams and with the Over for tempo teams. **The model must identify which favorite it has before assigning a sign.** Getting this backwards is the most expensive CFB parlay error, because the correlation is genuinely strong in both directions — you are not near zero, you are on the wrong side of a large number.

Required input before any favorite-linked ticket: adjusted tempo (plays per game, seconds per play), run/pass identity by down, and 4th-down aggressiveness.

### 6.2 Correlation priors

| Pairing | ρ | Note |
|---|---|---|
| Dog covers ↔ game total over ⓢ | +0.20 to +0.35 | Kept pace by scoring |
| QB props ↔ own team total ⓢ | +0.35 to +0.50 | |
| Methodical favorite covers ↔ under ⓢ | +0.20 to +0.35 | Scheme-dependent |
| Tempo favorite covers ↔ over ⓢ | +0.20 to +0.35 | Same pairing, opposite sign |
| Team total over ↔ game total over | +0.55 to +0.70 | Type 6 |
| Favorite covers ≥17 ↔ that favorite's starter props | −0.30 to −0.50 | Type 4, **larger than the NFL** — CFB starters get pulled earlier |
| Option/grinder success ↔ opponent volume props ⓢ | −0.30 to −0.45 | Most extreme possession suppression in the system |

### 6.3 Permitted 3-leg constructions
1. **The low-attention side stack.** Two sides + one total, all from Tier 1 low-attention games (G5, weeknight), all independently ≥ +2.5% post-haircut. This is a **Type B** cross-game parlay — permitted only under §7.2 rules, and only because CFB's Tier 1 inversion means these are your genuinely softest numbers.
2. **The dog-shootout stack.** Dog +points + game total over + dog QB passing yards over. Requires the dog to be a pass-first offense; verify identity, don't assume.

### 6.4 Banned outright
- **Every December ticket** until participation, opt-outs, and coaching status are verified for all teams involved (CFB §2.4). Bowl season is where CFB parlays go to die.
- Any ticket where a starting QB is unconfirmed on any leg (CFB §2.3)
- Any construction combining a favorite laying ≥17 with that team's player props
- Marquee-game legs in multi-leg tickets — those are the sport's sharpest numbers (Tier 3); if you have no edge on the single you have none in the parlay

### 6.5 Slate discipline
Max **one** parlay per Saturday, counted inside the 12% slate cap. With 60+ games available, the temptation is structural. So is the rule against it.

---

## 7) NBA

**Scalpy 3.0 §7 governs. This section adds only what §7 does not already cover.** Do not re-derive — use the existing correlation prior table, SGP tiers, and banned constructions verbatim.

### 7.1 Reconciling the 3-leg cap with existing tiers
- **SAFE** (§7.3): 2 legs, both p ≥ 0.68, both Minutes Grade A, spread ≤ 8, ρ ≥ 0, combined no shorter than −200. **This remains the preferred structure.**
- **BALANCED**: 2–3 legs, anchor ≥ 0.68, others ≥ 0.62, Minutes Grade A/B, documented positive correlation.
- **POP**: 3 legs max, one high-ceiling leg, two anchors ≥ 0.65, and the modeled joint must beat the SGP-implied joint by ≥6 points.

The new 3-leg hard cap is already satisfied by all three tiers. **No change needed to Scalpy 3.0 §7** other than adding the Dominance Test (§1.3 Test 2) as a mandatory Gate 6 and the seven-gate sequence as the execution order.

### 7.2 The Type B question
Scalpy 3.0 addresses SGPs but not cross-game parlays. Ruling: **cross-game NBA parlays are permitted only at true multiplicative pricing, with all legs Minutes Grade A, and only when a documented reason exists that is not "more payout"** — a promo, a boost, or an account-health placement. Otherwise the Dominance Test kills them, correctly.

### 7.3 Blowout override
Per §9 of Scalpy 3.0: any prop in a game with P(blowout) > 25% drops one full Minutes Grade. **Inside a parlay, apply this before Gate 1, not after.** A leg that degrades to Grade C on blowout risk is ineligible, and one ineligible leg kills the ticket.

---

## 8) WNBA

**Minutes are the whole ticket.** Per the WNBA engine, minutes are the king input and role volatility makes players unbettable regardless of modeled edge. In a 3-leg ticket you are making three simultaneous minutes assumptions. **Every leg requires a Usage Stability Score in the top band.** No exceptions, no "he's probably fine."

### 8.1 The trap, stated explicitly
Your WNBA doc names it: **star points over + her team as a big favorite.** The blowout compresses her fourth quarter. It feels like backing the best team two ways; it is a Type 4 clash and it is the most common losing WNBA ticket. **Any spread ≥ 9 disqualifies star-prop legs on the favorite.**

### 8.2 Correlation priors

| Pairing | ρ | Note |
|---|---|---|
| Star points over ↔ own team total over ⓢ | +0.30 to +0.45 | |
| Guard assists over ↔ teammate points over ⓢ | +0.15 to +0.30 | Same possessions completing |
| Pace-up game: both team totals ⓢ | +0.30 to +0.45 | |
| Any two same-game overs (baseline) | +0.10 | Shared pace/script |
| Two teammates, both points over ⓢ | −0.05 to +0.10 | Type 3 — reject in 3-leg |
| Two bigs, both rebounds over | −0.20 to −0.35 | Type 3 cannibalization |
| Star points over ↔ own team big favorite ⓢ | −0.20 to −0.35 | **Type 4 — the trap** |

### 8.3 Permitted 3-leg constructions
1. **The PRA stack.** Two Tier 1 PRA/rebounds/assists overs + own team total over, spread inside 7, both players Minutes Grade A. PRA is preferred because it aggregates away single-category noise — the same property that makes it your best single market makes it your best leg.
2. **The vacancy stack.** A confirmed absence, plus the two players whose usage demonstrably absorbs it (per your on/off mapping), plus that team's total. **Highest-edge WNBA construction available**, because books are slowest to reprice role redistribution and your injury-ripple work is the league's biggest edge. Requires the absence to be confirmed, not probable.

### 8.4 Banned
- Any leg on a player with a volatile Usage Stability Score
- Star props on any favorite laying ≥ 9
- Tier 3 legs (made threes, steals, blocks, first basket) in any multi-leg ticket — these are EXTREME volatility markets and have no place inside a compounding structure
- Cross-game WNBA parlays entirely — the league plays too few simultaneous games for genuine independence to be worth the tax

---

## 9) UFC / MMA

### 9.1 The conflict with your existing engine, resolved

Scalpy MMA 1.0 §11.2 bans **any parlay of 3+ fights**, and §13.2 caps you at **1 bet per fight**. A 3-leg UFC parlay therefore cannot be built across fights without contradicting your own engine.

**Ruling: the UFC parlay ceiling is 2 legs, same fight.** This is deliberate and it is correct. Do not raise it to match the other sports. A 3-leg ticket exists in UFC only as a same-fight construction (ML + method + round group) and that construction is banned in §9.4 below.

A same-fight correlated parlay counts as **one bet** against the 1-bet-per-fight cap.

### 9.2 The direct-price rule (this is the whole section)

Per §11.1: **"Fighter to win by KO" is usually a better price than parlaying "win" + "no distance," because the parlay applies vig twice.** Before building any same-fight ticket the model must:

```
1. Price the equivalent direct market (method of victory, round group)
2. Price the parlay construction
3. Take the better number
4. Log both — this comparison is a required audit field
```

In practice the direct market wins most of the time. **Most correctly-identified MMA correlations should be expressed as a single method bet, not a parlay.** The parlay is the fallback for when the book's method menu is thin or badly priced.

### 9.3 Permitted 2-leg constructions
| Construction | Valid when |
|---|---|
| Fighter wins + NO distance | Genuine finisher vs. a finishable opponent; both verified from the finish-rate model |
| Fighter wins + YES distance | Grinder/decision merchant vs. a durable opponent with no submission losses |
| Fighter by KO + under total rounds | Finishes cluster early in his history — verify the round distribution, don't assume |
| Weight-miss opponent + R2/R3 finish | Cut-collapse timing per §6; requires confirmed weigh-in observation |

### 9.4 Banned
- **Any 3-leg construction.** Same fight or across fights.
- **Parlaying favorites.** Four −400 favorites hit together ~41% of the time. §11.2 calls this the single most common way MMA bettors lose money.
- Contradicting same-fight props (KO + distance)
- Any leg involving a debutant or a short-notice replacement (§11.2)
- Any fighter priced worse than −300 (§13.2)
- Any construction implying a fighter probability above **88%** — the hard cap from §7. Four-ounce gloves mean nobody is safer than that, and a parlay is where an 88% cap gets violated by accident through multiplication.

### 9.5 Card discipline
2–3 bets per card total, and a parlay consumes one of them. Betting more converts a potential edge into a guaranteed vig payment (§11.3).

---

## 10) STAKING & EXPOSURE

### 10.1 Kelly for parlays

Compute Kelly on the **joint probability at the quoted price**, then halve the sport's normal fraction. Variance is materially higher and the estimate is built on three stacked model outputs rather than one.

| Sport | Singles fraction | Parlay fraction |
|---|---|---|
| NBA | ¼ Kelly | ⅛ Kelly |
| NFL / MLB / CFB / WNBA | ¼ Kelly | ⅛ Kelly |
| UFC | ⅕ Kelly | ⅒ Kelly |

### 10.2 Hard caps

- **Max 1.0% of bankroll** on any parlay, regardless of what Kelly returns
- **Max 1 parlay per slate**, across all sports
- Parlay counts as **one bet** against per-slate bet-count caps (NBA 4, MMA 3)
- Parlay counts at **full stake** against slate exposure caps (NBA 8%, CFB 12%, MMA 6%)
- Correlated legs also count against the underlying **game** exposure cap
- **Drawdown rule: parlays are suspended entirely** during any active drawdown circuit-breaker. When stakes are halved, parlays go to zero — not half. The drawdown state is the state in which you are most likely to reach for variance, and that is precisely when it is most expensive.

### 10.3 Promo handling
Per Scalpy 3.0 §13.4: **never boost an SGP.** The underlying price is already taxed 15–30%, so the boost is applied to a worse baseline. Boosts go on the longest-odds bet you would already place on merit. Bonus bets (stake not returned) are worth ~65–75% of face and belong at +200 to +400 — which is the one place a 2-leg parlay is a natural fit.

---

## 11) LOGGING

Every ticket logs to the same schema as singles, with a `bet_type = parlay` column and these additional fields:

| Field | Why |
|---|---|
| `legs[]` — each with market, line, price, book, p_final, individual CLV | Leg-level CLV is the only honest parlay CLV |
| `naive_product_dec` | Baseline |
| `quoted_dec` | What you paid |
| `correlation_tax` | 1 − (quoted / naive) — track this by book over time |
| `modeled_joint` | Your number |
| `implied_joint` | 1 / quoted |
| `edge_points` | modeled − implied |
| `conditional_reasoning` | Text: why P(B\|A) ≠ P(B) |
| `dominance_ratio` | EV_parlay / EV_singles |
| `clash_screen_result` | Which types were checked and cleared |
| `singles_alternative_ev` | What you gave up |
| `parlay_type` | A / B / C / D |

**Track `correlation_tax` by book.** Over a few hundred tickets this tells you which book prices correlation most generously, and that is a durable, product-level edge worth more than any individual ticket.

### 11.1 Loss codes
Extend the existing set with: `CORRELATION_ERROR` (the legs weren't as correlated as modeled) · `CLASH_MISSED` (a Type 2/3/4 slipped through) · `LEG_ONE_KILLED_IT` (two legs cashed, one specific failure recurring) · `TAX_TOO_HIGH` (post-hoc: singles would have won).

---

## 12) OUTPUT FORMAT

```
PARLAY — [Sport] — [Type A/B/C/D] — [2 or 3 legs]

LEG 1  [market, line, price, book]   p_final X.XXX   grade XX   CLV logged
LEG 2  [market, line, price, book]   p_final X.XXX   grade XX   CLV logged
LEG 3  [market, line, price, book]   p_final X.XXX   grade XX   CLV logged

CORRELATION
  Pair 1↔2   ρ +0.XX   [one-line mechanism]
  Pair 1↔3   ρ +0.XX   [one-line mechanism]
  Pair 2↔3   ρ +0.XX   [one-line mechanism]

CLASH SCREEN   Types 1–7 checked · [cleared / flagged: ___]

JOINT
  Independent product   0.XXXX  (+XXX)
  Conditional chain     0.XXXX  (+XXX)   ← the number that matters
  Book implied          0.XXXX  (+XXX)
  Edge                  +X.X points   [threshold: X.X]

DOMINANCE
  EV parlay    +X.X%
  EV singles   +X.X%
  Ratio        X.XX   [required: >1.25]

STAKE   X.XXu   (⅛ Kelly, capped at 1.0% bankroll)
RISK    [the honest case against — which leg is most likely to kill it and why]
```

**If no ticket qualifies: "No qualifying parlay at current numbers."** On a 12-game NBA slate or a 60-game Saturday, publishing that sentence is the system working. It should be the most common parlay output you print — by a wide margin.

---

## 13) SITE PUBLICATION RULES

Parlays enter the site under the **same probation architecture** already used for CFB and WNBA.

**Probation bar:** parlays are **graded, not staked** until **100 graded tickets** clear all of: positive flat-stake ROI · aggregate leg-level CLV ≥ 0 · z ≥ 2. Until then every published ticket is a tracked observation, journals to the Record page, and stakes nothing.

**Why this bar and not a softer one.** The Record page currently shows **−14.0% ROI across 154 settled bets** on singles. Adding a compounding-variance product on top of a book that hasn't yet demonstrated an edge on its simplest markets is the exact failure mode the probation system was built to prevent. **Singles must clear their own promotion bar before parlays leave probation.** Gate the parlay module behind the singles module — not behind a calendar.

**Display requirements:**
- Every published ticket shows the singles-alternative EV alongside the parlay EV. If singles were better, say so on the card.
- The correlation tax is displayed as a number on every ticket. Users should see what the structure costs them.
- Parlay record is reported **separately** from singles on the Record page, never blended. Blending them hides which product works.
- The existing responsible-gambling messaging applies unchanged and at equal or greater prominence.

---

## 14) THE ONE-PARAGRAPH SUMMARY FOR THE MODEL

You do not build parlays. You **screen** them. A candidate ticket arrives only after every leg has independently earned a place on the board as a single. You then ask one question: does a real, positive, mechanically explainable correlation exist that the book has priced as weaker than it is, by more than six points, and by enough to beat betting these same legs separately by 25%? Almost always the answer is no, and you say so. When the answer is yes, you take two legs before three, you stake it at half your normal fraction, you cap it at one percent, you log the leg-level closing line value, and you never, ever add a fourth leg.

---

## APPENDIX — Calibration backlog

These correlation magnitudes need fitting against your own play-by-play history before they carry real weight. Everything marked ⓢ has a direction stated in your engines; the ρ values are professional estimates, not measured constants.

**Priority order for backtesting** (highest expected value first):
1. MLB pitcher stack — K over ↔ outs over ↔ opposing team total under. Best construction in the system; measure the true joint.
2. NFL trailing-dog stack — dog cover ↔ dog pass attempts ↔ dog receptions.
3. WNBA vacancy stack — measure actual usage absorption from your on/off maps rather than assuming it.
4. CFB scheme-sign — split favorites by adjusted tempo and measure the cover↔total correlation separately for each group. Getting this sign right is worth more than every other CFB correlation combined.
5. Book-level correlation tax — which book is cheapest on SGP pricing, by sport and leg count.
