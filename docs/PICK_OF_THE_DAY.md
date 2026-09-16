# Pick of the Day — what it selects on, and what that is worth

Ethan, 2026-09-15, twice. First: "find 1 pick that is guaranteed to hit
... between -190 and +190 so we can basically have a 'one props doubles
money' type of hit." Then, after seeing what the first version selected
on: "maybe the pick of the day should not go off of our 70% model thing
... We shouldn't use that 70%" and "I want it to be a 50-50 money flip,
basically, either from 80% to 100% flip of your money. And we need to
look at other pro sports bettors' logic and models ... So we need to
figure out the models they're using and implement that."

This file is the measurement behind the second version. The code is
`engine/potd.py`; its header carries the same numbers, and this is the
working that produced them.

---

## 1. What the band can physically contain

Ethan said it twice on 2026-09-15 and the second time was the clearer
one:

> maybe the pick of the day should not go off of our 70% model thing …
> I want it to be a 50-50 money flip, basically, either from 80% to 100%
> flip of your money

> I guess I should reword that … I just wanted it to be a guaranteed for
> the day like I'm putting 100 bucks on it. I wanna make at least $70 if
> that makes sense … I feel like my wording is kind of fucked up a little
> bit.

The reworded spec is a **floor on the winnings**, not a window, and it is
the better spec. $70 on $100 is a payout of **0.70 units**, which is
**-142** (-143 pays $69.93 and misses by seven cents), which is the
market claiming at most **58.8%**.

That ceiling is arithmetic, not opinion. No price inside this band can
imply more than 58.8%, so **a main-market favourite inside this band
cannot be a heavy favourite.** `tests/test_potd.py` executes this rather
than asserting it, because every other decision in the module follows
from it.

## 2. What that costs, replayed on our own history

`data/history.db` holds 4,431 completed games carrying a two-way closing
moneyline (NFL 2021-26, CFB 2022-26). De-vig both sides, take the safer
one, one pick per slate:

| floor | league | picks | won | hit rate | price implied | ROI | sd above the price |
|---|---|---|---|---|---|---|---|
| **$70 (-143)** | NFL | 109 | 56 | **51.4%** | 55.4% | -7.1% | -0.86 |
| **$70 (-143)** | CFB | 242 | 122 | **50.4%** | 52.0% | -4.4% | -0.50 |
| $80 (-125) | NFL | 82 | 44 | 53.7% | 54.6% | -1.7% | -0.16 |
| $80 (-125) | CFB | 150 | 80 | 53.3% | 53.8% | -1.1% | -0.11 |
| $60 (-167) | NFL | 109 | 58 | 53.2% | 59.8% | -11.5% | -1.41 |
| $60 (-167) | CFB | 242 | 134 | 55.4% | 56.9% | -3.4% | -0.49 |
| $53 (-190) | NFL | 109 | 72 | 66.1% | 62.5% | +5.3% | +0.77 |
| $53 (-190) | CFB | 242 | 150 | 62.0% | 60.3% | +3.1% | +0.52 |
| any price | NFL | 110 | 94 | 85.5% | 84.7% | -0.3% | +0.22 |
| any price | CFB | 325 | 266 | 81.8% | 80.1% | +1.7% | +0.84 |

Three readings, and all three matter.

**The floor decides how much favourite you may buy, and the market
prices that almost exactly.** Every row's hit rate tracks its own implied
probability within a few points. That is what an efficient market looks
like from the inside.

**The trade is real and it is steep.** Ethan's $70 floor costs about ten
to fifteen points of hit rate against a $53 floor (-190), and no
selector can buy them back — nobody sells a 65% outcome for 70 cents.
That is his call and `potd.MIN_PAYOUT` is the one constant that reverses
it.

**Nothing here is an edge.** Every row lands within one and a half
standard deviations of what the price already said. Swept across floors
from -110 to -350 in both leagues, the largest figure was +1.17 sd on
108 NFL picks — one good season inside noise. Picking the safest side is
not a strategy; it is buying the favourite at the favourite's price.

**And none of this table is what the selector does.** It buys a
disagreement, not a favourite (§3). The band only says which prices may
be shopped, which is why the plus-money end is left open to +190 and
`MIN_FAIR` — the pick must be likelier to win than lose by the fair we
trust — does the work of keeping it a favourite.

## 3. So the pick has to be a disagreement, which is also what pros do

Strip the marketing off the public +EV method — Unabated, OddsJam,
Outlier, Sharp Lines all describe the same three steps — and it is:

1. Take a **sharp book's** two-way price. Pinnacle is the reference
   because it runs a 2-3% margin and does not limit winners, so its
   number is the one priced by the sharpest money.
2. **Remove the vig** to get a fair probability.
3. Bet only where a book you can actually reach prices that outcome
   **worse than the sharp fair**.

The edge is the gap between two books. It is never the gap between a
model and the world.

We already had this machinery for the Edge board
(`betting.sharp_anchor_for`, `gamebets.sharp_anchor_two_way`,
`odds.devig_two_way`, `odds.consensus_fair`). What we did not have was a
surface that selected on it *alone*. That is what the rebuild is.

### The evidence ladder

| tier | the fair comes from | why it ranks here |
|---|---|---|
| `exchange` | a regulated exchange's two-sided order book | **nothing is assumed** — see below |
| `sharp` | a sharp book's own two-way de-vig | the professional method, unmodified |
| `market` | the de-vigged consensus of ≥3 books | line-shopping; the market's own opinion |
| `model` | our number alone | **refused** — see below |

**Why the exchange outranks the sharp book.** Step two of the method —
remove the vig — is the step that needs an *assumption*: de-vigging
Pinnacle means assuming how its margin is spread across the two sides,
and `odds.devig_two_way` splits it proportionally while the
favourite-longshot literature says books do not price that way. An
exchange has no margin to strip. Two people take opposite sides of a
contract at a price they both chose, so the mid **is** the probability.

We were already pulling it and not using it: `engine/sources/kalshi`
fetches a CFTC-regulated exchange, keyless, in all fifty states, and
already parsed the book, matched a market to one of our games and knew
which side the YES contract paid on. It fed the Prediction Desk and
nothing else. `engine/exchangefair` hangs it on the rows that can use it.

Three guards, because a number from an exchange only beats a book's if
the book behind it is real: a **two-sided book** (never a last trade),
**tight** (`MAX_SPREAD_CENTS` 4 — a 10-cent book puts the truth five
points either side of the mid and `MIN_EV` asks for two), and **liquid**
(`MIN_LIQUIDITY`, which is a floor against the obviously thin and is
*not* a measured figure; `kalshi.price_series` is the tape that will
eventually set it).

Only the **moneyline**. Kalshi lists who wins; it does not list our run
line, and letting a win probability settle a spread is the silent
coercion this codebase keeps finding in its own history.

`potd.rank_key` sorts on the **tier first**, then the edge, then the
payout. That inversion is the point: sorting on edge size hands every
day to the loudest disagreement, and the loudest disagreements come from
the weakest witness.

## 3b. Where the candidates come from, and what was starving them

`potd.build` reads `result["most_likely"]` — the Most Likely board's
output. That board has its own product bars:

| bar | value | what it asks |
|---|---|---|
| `likely.MIN_PROB` | 0.55 | is this **most likely**? |
| `likely.MIN_RANK_AUC` | 0.60 | can this market rank at all? |
| `likely.HEAVIEST_PRICE` | -250 | is this price worth staking? |

**The first of those was cutting exactly the rows this feature wants.**
No in-band price can imply more than 58.8% (§1), so the candidates
nearest the band are the ones sitting closest to `likely`'s 55% floor —
and a 53% sharp-anchored price at +100 is +6% EV, which is precisely
this product. Selecting on another board's product bar answered the
wrong question.

Since 2026-09-15 a **reserve** row — one `likely` ships from below its
own floor, labelled, so its page is never blank — can be the day's pick,
**but only on a sharp or market witness**. What is not waived:

- The model tier is still refused outright (§4).
- The reserve band is measured **at a loss** on the model's own ranking:
  45-60% went **-7.68%** over 184 settled rows (`likely.RESERVE_MIN_PROB`).
  That figure is why this is not a general loosening — these rows are
  admitted on *a sharper book's disagreement*, never on our number.
- The card says `from_reserve` in as many words, so a reader is told the
  row did not clear the board's bar and what got it here instead.

Whether that basis pays is **untested here**, and the potd book's own CLV
is what will answer it (§7).

A useful property falls out of this: the reserve only fires on **thin**
shelves, so on a full board the widening changes nothing. It helps
precisely on the quiet days, which are exactly the days this feature was
otherwise showing "nothing cleared the bar".

## 3c. Seeing it on a real board

`potd_report.py` runs the selector over a published board and prints the
funnel. Read-only — it opens the JSON, never writes, never fetches a
price — so it is safe on the production box mid-cycle.

```bash
python3 potd_report.py                      # every board in web/data
python3 potd_report.py nfl cfb --rows 10     # with the near misses
python3 potd_report.py --dir /srv/qellys/web/data
```

It answers the question no test can: whether a real Tuesday board
carries anything for these rules to bite on. "68 rows considered, 61
outside the band, 0 picks" is not a bug report — it is the name of the
gate to argue with.

## 3d. The ladder lever, and why it stopped being the lever

A -400 read is outside the band by the widest margin available. But the
same book quotes the same player at other numbers — 34.5 rushing yards
at -115 instead of 24.5 at -400 — so the read is not unbettable, it is
unbettable **at that price**. Converting a strong read into a band-legal
price is what a lot of pick services are actually doing when they post
"Team -7.5" instead of "Team ML -400".

On 2026-09-15 `potd_report` counted the prize on production: **23 of 44
price-refused rows had a rung inside the band**, unreached.

```
  Ketel Marte total_bases at -245 → 1.5 at -105 (FanDuel)
  Drake Baldwin total_bases at -235 → 1.5 at +125 (DraftKings)
  Spencer Jones total_bases at -180 → 1.5 at +140 (Fanatics)
```

**Every one of those is a player prop, and §3f closed the day's pick to
player props.** So the count that justified the work is now counting
rows the selector will not take under any price.

**And there is no game ladder to walk.** `alt_lines` is populated only
by the prop feeds (`oddsapi.ALT_ODDS_TO_MARKET` and its per-sport
cousins); the game markets this feature now selects on are bought as
`h2h`, `spreads`, `totals` — main lines and nothing else.
`alternate_spreads` and `alternate_totals` are never requested from the
API. Walking the ladder from `potd.choose` today would be machinery over
an empty source.

**What it would take, and it is a purchase decision rather than a
wiring one.** Buying `alternate_spreads` and `alternate_totals` for the
focus leagues is new credits against a budget that already puts MLB on a
limited allowance (`engine/sources/oddsapi` — NFL and CFB first). The
question to answer before spending them is the same one §3d always
asked, re-pointed at game rows: **how often is a game row refused on
price when an alternate number would have been in the band?**
`potd_report` cannot answer that until the alternates are bought, which
is the circularity — so the honest order is to buy one league's
alternates for a fortnight, count, and decide.

`likely.rungs` and `likely._best_rung` (split 2026-09-15 so the
derivation and the choice are separate) are ready for the day that data
exists. Nothing else about the ladder is wired, and this file should not
say otherwise again.

## 3e. One pick for the DAY, not one per league

Everything above chooses a pick **per sport**, and that was never what
was asked for. Ethan, 2026-09-15: *"a model that picks one pick for the
pick of the day."* Singular. What the site actually did was show the MLB
reader MLB's best and the NFL reader NFL's best, and call both of them
the Pick of the Day.

`potd.day_top_pick` is the cross-league layer, and it is **a comparison,
not a second model.** §3's `rank_key` already orders picks on three
quantities that know nothing about which sport produced them:

| ranked on | league-specific? |
|---|---|
| which witness stands behind the fair | no — the ladder is the same everywhere |
| the edge, in probability points | no |
| what the price pays | no |

So the cross-league answer is that same comparator over a longer list. A
cross-sport bar invented at this layer would be a second set of numbers
to keep honest, fitted to nothing.

**Three refusals do real work.**

A *qualifying* pick always beats a *below-bar* one, whatever the tiers
say. §3b's reserve means `build` publishes its best available when
nothing clears, so a below-bar row is on the board by design — letting
one outrank a pick that cleared every gate would quietly undo the gates,
and it would look identical from here.

A pick is refused unless its board is **dated today**. Every league
publishes on its own schedule, and one out of season leaves a perfectly
well-formed pick on disk from whenever it last ran. Nothing about that
card looks wrong; only its date says so. Same shape as the stale-price
ceiling in §3.

A qualifying pick is refused unless it is **the one that league already
locked**. `ledger.log_pick_of_the_day` writes the first qualifying pick
of each journal day and refuses every later one, precisely so a sport
cannot churn picks until settle time and have the record keep whichever
happened to be showing. `ledger.locked_potd_keys` reads that lock and
`day_top_pick` honours it.

> **This was missing for the first three hours.** Shipped without it,
> the cross-league layer ranked whatever was on the boards at the moment
> the cycle ran — so the day's headline could have been an MLB bet at
> noon and, after that bet lost, an NFL one at eight, with nothing
> recording the first claim. Choosing after seeing how the day is going,
> which is the exact failure the per-league rule exists to prevent,
> reintroduced one layer up.
>
> It reads the existing lock rather than defining a second one: two
> locks that can disagree is worse than none, because the disagreement
> is invisible from the page. And `potd_row_key` is lifted out of the
> journal writer so the writer and the matcher cannot disagree about a
> negated spread or a moneyline rewritten as OVER 0.5.
>
> **Failing closed.** A ledger that cannot be read yields `{}`, which
> refuses every qualifying pick and publishes nothing — because an
> unlocked claim looks identical on the page and cannot be graded
> afterwards.

Below-bar leans are exempt from the lock and that is not an oversight:
nothing journals them, nothing records them, so there is no lock to
match — and the page still has to show the strongest thing available on
a day when no league cleared its bar.

**Where it runs.** Not in a build — no build can see the other boards.
`launch._write_day_top_pick` runs once per refresh cycle, after every
board has had its turn, and writes `web/data/day_top_pick.json`.

> **A board's file is not named after its league,** and three separate
> readers assumed it was on the day this shipped. The NFL writes
> `recommendations.json` and MLB `mlb_recommendations.json`; only cfb,
> nba and wnba match their own code. The writer opened
> `web/data/{sport}.json`, so the two leagues at the top of
> `SPORT_PRIORITY` were invisible to it and the day's top pick could
> only ever have come from college football or the hoops boards. The
> `FileNotFoundError` underneath swallowed it as "a league this box does
> not publish".
>
> `launch.BOARD_FILES` is the registry, and everything reads it now.
> `potd_report.py` had the same bug against the *light* copies
> (`recommendations_picks.json`, not `nfl_picks.json`) and had been
> silently reporting on three leagues out of five since it shipped. The
page draws it as **one line inside the Pick of the Day card**, not as a
block of its own: `tests/test_board_order.py` measured that the picks
already start at 848px on an 844px phone fold, so a second card above
them pushes the product off the first screen.

**It is paid.** `pick_of_the_day` is in `gate.PAID_KEYS`, and this file
is that same object promoted to the top level with nothing else in it to
strip, so it is registered in `PAID_FILES` and fetched through
`paidFetch`. Registered free it would have handed the headline pick to
everyone while looking like an ordinary new board.

**Seeing it on the box.** `python3 potd_report.py --top` prints the
board's answer beside the locked one, the journaled picks, and a banner
when the two disagree. That disagreement is ordinary — a league has
moved off the pick it journaled this morning — and is the single thing
most likely to look like a broken feature when it is a working one.

### What it still cannot tell you

**The day's top pick has no record of its own.** It is always one of the
per-league picks, so it is already counted in the `potd` book — but
which league won on a given day is nowhere on disk, because
`day_top_pick.json` is overwritten every cycle. The winner's tier is not
recoverable from the journal row either (`bets` carries odds and edge,
not `evidence`), so it cannot be recomputed after the fact.

Storing it is a small per-day pointer. What it should point AT is a real
question and not a detail: the cross-league winner can legitimately
change during the morning as more leagues journal their picks — a league
that builds at 6am cannot be outranked by one that has not run yet — so
"first cycle wins" would systematically favour whichever league builds
first, while "last cycle wins" means the reader at 6am saw a headline
that is not the one recorded. Both are defensible and they record
different things.

### What it is not called, and why

The first draft of this feature was `lock_of_the_day` end to end, and it
would have put those four words on the page. **"lock of the day" is on
the banned list** `tests/test_potd_card.py` keeps — see §9 — precisely so
the page cannot promise a paying reader a certainty.

That test did not catch it. It read the two renderers that existed when
it was written, and this was a third. Both halves are fixed: the feature
is named for a comparative the ranking can actually support (*the
highest-ranked pick on the site today*), and the banned list now checks
every pick renderer plus a guard that **fails when a new one appears**.
That guard immediately found two more renderers nobody had been checking
— both already clean, which is the point: nothing had been holding them
that way.

## 3f. Game markets only — the day's pick is not a player prop

Ethan, 2026-09-15: "i do want the pick of the day to be moneylines and
spreads only for all sports i think ... feels like relying on one player
is more volitole and risky instead of relying on a whole team." He then
added totals. `potd.disqualify` asks it first, off `ledger.is_game_row`.

**His stated reason is half right and it is the weaker half.** A single
bet's variance is p(1−p) whatever the bet is about, so a 60% player prop
and a 60% moneyline are exactly as bumpy. What a player really carries
is *estimation* error nobody can see from a projection: ejected, pulled
after four innings, rested, a hamstring on the first drive.

**The deciding reason is the evidence ladder.** `exchangefair.MARKETS`
is `("moneyline",)` — the exchange lists game winners and nothing else —
and a sharp book's player-prop coverage is thin to absent. So a player
prop is structurally stuck near the bottom of `potd.EVIDENCE`, and
`shortfall` refuses a model-only row outright (§4). The selector was
choosing the day's headline out of a pool most of which could never meet
the standard it holds them to. On the MLB board of 2026-09-15: **52
rows, 0 sharp, 0 market, 0 exchange.**

Props keep every board they had — Most Likely, Long Shots, the props
scanner. They stop being eligible for the day's name.

## 3g. The card leads with the call

Ethan, 2026-09-15: the card "should say whether to bet". It did not. It
opened with the bet in words, a fair, an edge and a payout, and left the
one question a reader arrives with — *do I put money on this today?* —
to be inferred from the colour of a 3px border and a sentence six lines
below the fold. A lean and the day's pick wore the same furniture.

`potd.verdict` is the single definition:

| state | call | stake |
|---|---|---|
| a qualifying pick | **BET** | `STAKE_UNITS`, 1.0 |
| a below-bar lean | **NO BET**, with the bar it missed | 0 |
| no pick at all | **NO BET**, with the board's note | 0 |

**A lean gets the same call as an empty board**, because that is already
what the product does with it — `ledger.log_pick_of_the_day` refuses to
journal one, so nothing about it is on the record.

**The stake is flat, not a Kelly fraction.** This feature publishes one
pick a day chosen on the strength of the witness rather than the size of
the edge, and `rank_key` already rounds the edge to whole points before
sorting; sizing on differences the selector will not treat as ranked
would swing the stake threefold on noise. Flat is also the shape the
record below the card is kept in, so the two agree.

**Derived over the published payload, never over the board's rows.**
`relock` can turn a card that cleared into a card showing nothing at
all, and `day_top_pick` can crown a below-bar lean from a league whose
own board published "no bet" about that very row. Both recompute; `build`
has one exit so the call cannot be attached to two outcomes and
forgotten on the third. The page draws the verdict and nothing else.

The no-bet state is deliberately **not** painted red. Declining to bet
is not a loss, and drawing it as one pushes a reader toward the action
on exactly the day the engine has said not to.

## 3h. Spreads and totals, and the bar that was keeping them out

Ethan's game-markets call (§3f) named moneylines, spreads and totals.
For a day it delivered **moneylines only**, and the cause was in two
places a step apart. Written down because the shape recurs: a fact
discarded early, then a bar asked of the wrong rows late.

**The real one: the sharp anchor was dropped on the way to the row.**
`gamebets.price_spread_sharp` and `price_total_sharp` de-vig a sharp
book's two-way pair at a matching number and hand back a card whose
`win_prob` has been REWRITTEN to that fair (`_sharpify` — the same
rewrite `price_moneyline_sharp` does). `likely.from_game_bet` built its
row and did not carry `sharp_anchored` across. `potd.evidence` then fell
through to `prob_source`, which `ranking_number` sets to `"model"` for
any market with no `GAME_RANK_MARKET` entry — every spread and every
total — and `shortfall` refused the row:

> only our own model disputes this price

**That sentence was false about the row.** The number disputing the
price was Pinnacle's. The evidence had not been weighed and found
wanting; it had been thrown away two functions earlier.

**The second one: the ranking bar was asked of somebody else's number.**
`MIN_RANK_AUC` is `likely.rank_auc` — OUR pricer replayed over stored
closes, which reads 0.49–0.50 on spreads and totals in both football
leagues (§the header table in `engine/likely`). It now applies to the
tiers where our model IS the witness. The model tier is refused outright
two checks earlier; the `market` tier keeps the bar, because a de-vigged
consensus is a number we compute from a field we choose; the exchange
and sharp tiers are exempt.

**And ranking is the wrong question for this feature anyway.** A board
that sorts by probability needs to know a market can be ordered. This
selector buys a PRICE DISAGREEMENT, and a 50/50 outcome bought at +100
is +EV whether or not anybody can say which side lands. A spread sits
near 50% by construction — the book moves the number until the money
splits — which is exactly why nothing ranks it and exactly why it can
still be mispriced.

**What did not move.** The model tier is still refused. `MIN_EV` still
wants 2% against the sharp fair. `MIN_FAIR` still wants the pick
likelier to win than lose by that fair, which on a spread is a real cut
rather than a formality — half of them sit under it. And
`ranking_number` is untouched: which number the Most Likely board SORTS
on, and whether a spread ships there labelled a lean, is Ethan's
2026-09-02 call and this does not reach it.

**NOT MEASURED, AND THAT IS THE HONEST CAVEAT.** The sharp-anchor method
has been replayed on moneylines (§8) and never on spreads or totals,
because no sharp spread or total pair is stored to replay —
`potd_backtest.py` inherits the same gap. These markets are opened on
the METHOD's logic, not on a measurement of them. Storing a sharp
spread/total pair in `odds_history` is what would close it, and it is
the same nightly harvest that closed the moneyline gap.

## 3i. The ceiling: a gap too big to trust is not a pick

**Measured on the droplet, 2026-09-16, first honest replay of the
product** (`potd_backtest.py mlb`, after the replay was fixed to call
production's own gate):

| the edge it was chosen for | picks | won | net | ROI |
|---|---|---|---|---|
| under 4% | 9 | 8 | +6.42u | **+71.4%** |
| 4–7% | 9 | 7 | +4.23u | **+47.1%** |
| 7–15% (suspect) | 27 | 13 | −1.95u | **−7.2%** |

`backtest_sharp_anchor`, over every price disagreement on the board
rather than one a day, had already said the same thing on the same data:
`<4%` +29.3%, `4–8%` +17.0%, `8–15%` **−16.8%**. Two samples, two
selectors, one direction.

**Twenty-seven of the forty-five picks — sixty per cent — came from the
losing bucket**, and `rank_key` is why: within a tier it sorts by the
biggest edge, so every day goes to the loudest disagreement available.
Its own docstring already knew that was dangerous — *"the loudest
disagreements come from the weakest witness"* — but applied the thought
ACROSS tiers and never WITHIN one.

**THE STRONGER ARGUMENT IS NOT THE BACKTEST.** `gamebets._sharpify`
already sets `grade = "Pass"` and `stake_units = 0.0` on any sharp gap
past `SHARP_SUSPECT_EV`, and writes the reason onto the card: a
disagreement that size usually means the sharp side repriced on news
(scratch, injury, weather) and the soft quote is stale. **The edge board
stakes nothing on these.** This feature took them at a full unit and led
the front page with them — one product, two answers to whether the same
price can be trusted. That is a contradiction to remove whatever a
45-bet sample says.

So `potd.MAX_EV` IS `gamebets.SHARP_SUSPECT_EV`, imported rather than
restated, and `shortfall` refuses past it.

**A QUALITY BAR, NOT A HARD REFUSAL.** The bet is real and placeable, so
a day whose only candidate is a suspect gap shows it as a lean with the
reason attached rather than going blank.

**WHAT THIS DOES NOT CLAIM.** 45 picks is not a verdict on the feature —
the headline was +19.4% ± 14.1%, 1.4 standard errors from zero, which is
encouraging and not established. The bucket split is a stronger signal
than the headline because it replicates, but 9/9/27 are small numbers.
What is NOT in doubt is the inconsistency, and that is what was fixed.

**AND IT SURFACED A BAD FIXTURE.** Every test in `tests/test_potd.py`
was built on a row with a 60% sharp fair against −110 — a 7.6-point
disagreement with the sharpest book in the world, +14.5% EV, a bet the
rest of the site refuses to stake. Eight tests failed the moment the
ceiling landed. The fixture is now 55% (+5.0%), an ordinary
sharp-anchor row.

### 3i-b. The ceiling narrows the price band to +114, and that is Ethan's call

**Not a side effect worth burying.** `MIN_FAIR` wants the pick likelier
to win than lose (50%). `MAX_EV` wants the edge no wider than 7%. Those
two meet:

    EV at the 50% floor = 0.50 × (1 + payout) − 1

At +114 that is exactly 7.0%. At +115 it is 7.5% — so **above +114 no
bet can be both at-or-above the fair floor and at-or-below the trust
ceiling.** Every price from +115 to `MAX_ODDS` (+190) is now unreachable:
a row there either implies under 50% (refused by `MIN_FAIR`) or carries
over 7% (refused by `MAX_EV`).

**The effective band is −142 … +114, not −142 … +190.** `MAX_ODDS` still
reads 190 and is no longer the binding constraint on the plus side.
Pinned in `tests/test_potd_band_collision.py` so it cannot drift
silently: if either bar moves, the test names the new crossing point.

**WHY IT IS LEFT STANDING.** Both bars are defensible on their own and
the collision only removes prices where the two disagree about the same
row. A +150 dog at a 7%-or-less edge implies a fair near 43% — refused by
`MIN_FAIR`, a bar that predates this work. A +150 dog at a 50%+ fair
implies a 25% edge — the exact shape `_sharpify` grades Pass. Neither
kind was ever a pick the rest of the site would stake.

**WHAT WOULD CHANGE IT.** Dropping `MIN_FAIR` below 50% for
sharp-anchored rows reopens the plus side, and the argument for that is
that a price disagreement does not care which side is favoured. It is
not made here because `MIN_FAIR` is Ethan's product bar — "the pick
should be more likely to win than lose" — and moving it is his call, not
a consequence of a measurement.

## 4. Why our own model is not allowed to be the evidence

Not a style preference. `likely.GAME_RANK_MEASURED` against
`likely.GAME_RANK_MARKET`:

| market | our model | the market's own de-vigged number |
|---|---|---|
| NFL moneyline (1,420 games) | 0.677 | **0.722** |
| CFB moneyline (3,011 games) | 0.752 | **0.791** |
| spreads, totals, team totals | 0.492-0.504 | — |

The market ranks winners better than we do, and on the derived markets
we cannot rank at all. A pick chosen because *our* number disagrees with
the price is a pick chosen by the weaker of the two opinions in the
room. `potd.shortfall` returns "only our own model disputes this price"
and the row is shown as a near miss, never as the day's pick.

## 5. What the EV floor actually asks for

`MIN_EV` is 0.02 units. Across the band that works out to about **one
point** of disagreement with the price (0.7 to 1.2 points —
`tests/test_potd.py` solves for it rather than quoting it). That is the size
of gap a genuine sharp-versus-soft difference produces. A floor that
needed ten points would only ever be cleared by our own model being
wrong, which is the failure this rebuild exists to stop
(`betting.MAX_CREDIBLE_EDGE` is the same lesson from the other side).

`MIN_FAIR` is 0.50: a +EV underdog is a fine bet and a bad thing to name
the day after.

## 6. The de-vig method barely matters here — measured, 2026-09-15

The literature argues constantly about multiplicative vs additive vs
power vs Shin. They diverge on longshots — that is the whole
favourite-longshot-bias argument — and converge in the middle of the
board. This section used to stop there, with "about a point at the
plus-money end and well under one everywhere else". That was right, and
it was an adjective. `engine/bookvig.assumption_points` is now the
number: the spread between proportional, additive and power on one real
pair, swept across this band.

| book's margin | worst in band | side taken (fair ≥ 0.50) | vs the 2-point EV floor |
|---|---|---|---|
| 1.00 an exchange | 0.00 pts | 0.00 pts | 0% |
| 1.01 | 0.24 | 0.13 | 12% |
| 1.02 | 0.48 | 0.26 | 24% |
| 1.03 Pinnacle | 0.70 | 0.39 | 35% |
| 1.05 a soft book | 1.18 | 0.66 | 59% |

**Why it collapses here and not elsewhere**, which is the part worth
keeping: all three methods must return two numbers summing to one, so at
a true 50/50 they *cannot* disagree, whatever the margin. The gap is
driven by distance from even money, not by the size of the vig — and
§1's arithmetic pins this band near even money by construction. The same
sum on a +900 touchdown longshot moves 3.66 points, which is why
`engine/devig` takes the question seriously one board over and this file
does not.

`odds.devig_two_way` is multiplicative and stays that way here.

**What this cost.** The measurement was taken while building an exchange
*detector* — auto-promoting any near-zero-vig book (Novig, ProphetX) to
the top of the evidence ladder on the theory that a venue with no margin
needs no de-vig assumption. The premise did not survive its own
measurement: at these sizes the assumption is worth a third of the
minimum edge, which does not buy a whole tier. The detector was not
built. What shipped instead is the measurement and a census of what each
book charges — `engine/bookvig`, `book_margins.py` — and the exchange
tier keeps its place on a different argument (whose number it is, not
how the margin comes off), which `engine/booksharp` is where to test.

## 7. How we find out whether any of this is real

**Not from the win-loss record.** The industry's own rule of thumb is
500-1,000 graded plays before a record means anything; at one pick a day
that is three years.

**From closing-line value.** CLV grades the *decision* at kickoff,
accrues on every pick including the losers, and is the metric the sharp
side actually keeps. The `potd` book flows into
`clvboard.scoreboard(conn, category="potd")` for free. If these picks do
not beat the close, this module is wrong and that page will say so.

**Verified end to end**, because a wiring break here would fail no other
test — the picks would journal, the record page would fill, and the one
number that answers "is the sharp anchor finding anything" would quietly
stay empty. A pick taken at -110 and closing at -135 reads back as
**+5.07 points of price CLV**, `ready: false`, `thin: true`, and nothing
in the `main`, `paper` or `likely` books
(`test_the_book_reaches_the_clv_scoreboard_and_nothing_elses`).

**Price CLV is the instrument that matters here**, not line CLV. A 3.5
receptions line closes at 3.5 on a market that moved plenty; the price
is what moved, and `clvboard` has measured both since 2026-09-02.

## 7b. And from replaying the selector itself

CLV grades the decision; it does not say what the product returned.
`potd_backtest.py` does, and it is the only thing here that grades the
**product** rather than the method underneath it:

```
python3 potd_backtest.py mlb
python3 potd_backtest.py --all
```

It replays every stored day: builds the moneyline rows from the
harvested sharp pair and the shopped soft price, runs them through
`potd.disqualify`, `potd.shortfall` and `potd.rank_key` **as they ship**,
takes the one qualifying pick a day the way `ledger.log_pick_of_the_day`
locks it, and settles against the final score.

**Why it can disagree with `backtest_sharp_anchor`, and why this is the
number that matters.** That replay takes every disagreement it can find
— a few hundred bets a season. This takes one a day, ranked on the
witness before the edge. Same pool, different sample, and on this box's
MLB data the pool's returns run *backwards* in EV (§2): under 4% EV
returned +29.3%, over 8% returned −16.8%. Inheriting the method's
headline for the product would be assuming the answer.

**It settles the leans separately**, under `IF THE LEANS HAD BEEN BET
TOO`. That is the live product question — Ethan wants a pick every
single day — priced rather than argued. The leans are not in the
headline because the product does not bet them and
`log_pick_of_the_day` refuses to journal them; if that block is
positive over a real sample, a second labelled tier is arguable, and if
it is negative the current behaviour is already right.

**What it cannot see**, all four stated in `engine/potdbacktest`'s own
header rather than only here: moneylines only (the only market with both
a sharp pair and a soft price stored); no exchange tier (Kalshi is read
live and never stored, and it ranks *above* sharp, so a day this gives
to a sharp row may in production go to an exchange row); close against
close (soft books have mostly converged by then — the live board acts
earlier); and `bettable` assumed, so the count of days with a pick is an
upper bound. It is a floor with the reasons written down.

**Every ROI it prints carries a standard error beside it.** One pick a
day is a small sample by construction, and an ROI quoted alone invites a
reader to treat +9% over 90 bets as a fact about the world.

## 8. The gap that closed, and the one still open

**Closed: Pinnacle closes exist now.** This section used to read "there
are no stored Pinnacle closes anywhere, so the sharp-anchor strategy has
never been measured on our own data". The nightly harvest has since
filled `odds_history` on production, and on 2026-09-15
`backtest_sharp_anchor` answered for the first time:

```
MLB · 741 games with both a Pinnacle pair and a soft price
  203 bets, 110 won (54.2%), net +19.93u, ROI +9.8%
  EV buckets:  <4% → +29.3%    4-8% → +17.0%    8-15% → -16.8%
```

**Read the buckets before the headline.** +9.8% is about 1.4 standard
errors from zero on 203 bets — encouraging, not established. And the
buckets run **backwards**: the biggest claimed edges lost money. That is
the signature of a stale or mis-joined price rather than of a real edge,
and it is the reason `potd.rank_key` ranks on the witness before the
edge size and why §3's ceiling on "suspicious" EV exists. Each bucket is
59-74 bets, so the ordering itself is not established either.

**This box is not that box.** `data/history.db` here holds 64
`odds_history` rows, so `backtest_sharp_anchor` and `potd_backtest.py`
both return zero priced games locally and say so in their own funnels.
Both numbers come from the droplet.

**Still open: the product has not been replayed over a real sample.**
`potd_backtest.py` (§7b) is the instrument and it is only as long as the
harvest. A fortnight of nightly Pinnacle moneyline closes per league is
what turns its output from a shape into a measurement.

**Still open: no game-market alternate ladder.** §3d — the lever that
would turn a price-refused game row into a band-legal one needs
`alternate_spreads` and `alternate_totals`, which are never bought.

## 9. What the page may not say

No bet is guaranteed. The disagreement was raised once and Ethan's call
stands on everything else — the band, the daily cadence, the showcase
framing. What the page may not do is promise a paying reader a
certainty, because the first loss then reads as a lie rather than as
variance. `tests/test_potd_card.py::test_neither_surface_promises_a_certainty`
holds that line, and its banned list is why the module is named for a
pick rather than for a lock.

## 10. Sources

The public method, as described by the tools that sell it:

- <https://unabated.com/articles/finding-positive-ev-wagers-step-by-step-guide>
- <https://help.outlier.bet/en/articles/8208129-how-to-devig-odds-comparing-the-methods>
- <https://8rainstation.com/blog/understanding-positive-ev-betting-exploring-multiple-devigging-options>
- <https://picktheodds.app/en/blog/sharp-sportsbooks-what-they-are-and-how-to-use-them-to-find-edges>
- <https://www.pinnacleoddsdropper.com/blog/closing-line-value>
- <https://www.boydsbets.com/closing-line-value/>

Derivative markets (first-half, team totals, alternate rungs) as the
place where soft books are laziest — the next thing to mine once the
main-market anchor is measured:

- <https://www.predictem.com/betting/strategy/betting-derivatives/>
- <https://oddsindex.com/guides/first-half-totals-strategy>

Reverse line movement, which we do NOT use: profitable in some
published samples, explicitly not profitable in college-football totals
over 2005-2016 (Journal of Economics and Finance,
<https://link.springer.com/article/10.1007/s12197-019-09479-3>). It needs
ticket-vs-handle splits we do not buy, and the evidence is mixed enough
that it is not worth one pick a day.
