# What a better NFL moneyline equation is worth — 2026-09-07

**Status: measured, not proposed. Five arms on one set of games.**

Ethan: "Can we Create arithmetic equations to figure out the outcome nfl
moneylines. We can use math for anything and this is one of them I feel
like."

Yes — and there already are. This is what they are, what each is worth
against the closing moneyline, and what the two most standard upgrades to
them are worth. The answer to the question underneath is at the end.

---

## 1. The equations that ship

A team's rating is its scoring margin, shrunk toward zero while the sample
is small (`engine/teamrates.py`):

    net = (points for − points against) / games  ×  games / (games + 6)

on this season's games once the league averages four a team, pooled with
last season's until then (`ratings_for_season`). The matchup is a normal
curve over the difference (`engine/gamebets.nfl_win_prob`):

    margin      = net_home − net_away + 1.6          # 1.6 points of home field
    P(home win) = Φ(margin / 13.5)                   # 13.5 = SD of an NFL final margin

That probability is compared with the book's de-vigged price, the
disagreement is shrunk by a MEASURED fraction (`engine/gamecal.py`), and
what survives is the edge the card prints.

---

## 2. What they are worth

Walked forward over 2021–25 — ratings from games strictly before each
week, ordered by season and then week — on **the same 1,181 quoted
games** for every arm, against nflverse's closing moneyline:

| arm | what it is | AUC | Brier | log-loss | slope of our disagreement ± se |
|---|---|---|---|---|---|
| **M** | the closing market's own fair probability | **0.724** | **0.210** | **0.607** | — |
| A | cumulative rating (every game a team ever played) | 0.633 | 0.235 | 0.663 | −0.174 ± 0.108 |
| **B** | **`ratings_for_season` — what the build ships** | **0.683** | **0.222** | **0.635** | **−0.057 ± 0.135** |
| C | B + opponent adjustment (the college fix), H = 1.6 | 0.685 | 0.222 | 0.635 | −0.082 ± 0.139 |
| D | C with home field fitted jointly (+2.21) | 0.684 | 0.223 | 0.635 | −0.087 ± 0.138 |

AUC: the chance a random winner is ranked above a random loser (0.50 is a
coin flip). Brier and log-loss: lower is better. The slope is
`engine.gamecal`'s question — regress the outcome on our disagreement
with the market, in log-odds, with the market's own number as a fixed
offset: 1.0 would mean our disagreement is exactly right, 0 that it is
noise. All three fits are within one standard error of zero and their
point estimates are negative.

One more column, plainer: when the shipped model leans off the close, the
game goes the **market's** way 60% of the time (40.4% of 1,181 went ours).

Reproduce: arm B is `python3 -m engine.gamerank --sport nfl`; arm C is
`gamerank.measure_nfl(conn, adjusted=True)`; the slopes are
`python3 -m engine.gamecal --sport nfl`. (`measure_nfl` on its own floor
quotes 1,356 games at 0.677 — the figure the board carries; the table
above holds the quoted set fixed across arms, which is the only way to
compare them.)

---

## 3. What the table says

**The best equation we have is a worse predictor of NFL winners than the
closing line** — 0.683 against 0.724, Brier 0.222 against 0.210 — and
**where it disagrees with the line, the disagreement carries nothing.**
That is the calibration store's finding restated on the right model: the
adopted shrink on every NFL game market is zero.

**More arithmetic on the same inputs does not help.** Opponent adjustment
lifted college football from 0.708 to 0.752, because a Sun Belt schedule
and an SEC schedule are not comparable numbers. It lifts the NFL by
0.002, because an NFL schedule is close to balanced and the plain average
was never far from the adjusted one. A fitted home field (+2.2, against
the 1.6 assumed) changes nothing either. These are the two upgrades
anybody would reach for first, and they are now measured refusals rather
than open questions.

**The two walks that produced the site's earlier figures were not
walk-forwards.** An NFL week label repeats every season; the walk sorted
on it alone and priced 2021's second week having seen 2025's first, and
the schedule closes were keyed on it alone so 65 games read another
season's line. Fixed the same day (`ORDER BY season, period`,
`gamebacktest.close_for`). The board's figure had also been arm A's — a
model the build does not ship — and is now arm B's.

---

## 4. So where would NFL moneyline money come from?

Not from a better formula over points scored and allowed; the market has
that formula and more. The honest candidates are things the closing line
does not contain, or prices between books, and each one is measurable
before it is believed:

1. **Bet the open, not the close.** The close is the market's final
   answer; the open has less in it. The CLV framework exists
   (`engine/clvboard.py`, `engine/lineledger.py`) — the test is whether
   our number beats the OPENING moneyline and the close then moves toward
   us. Nothing here has measured that yet.
2. **Price disagreement between books**, which needs no model opinion at
   all (`gamebets.price_moneyline_sharp`). Its limit is which books the
   odds budget fetches.
3. **An input the rating cannot see: the starting quarterback.** The one
   known single factor that moves an NFL line by several points, and
   invisible to any function of past scores. nflverse carries historical
   starters. This is a new input, not more arithmetic — and it is the
   only thing in this list that could raise arm B's number rather than
   route around it.

What would NOT be honest is to keep fitting curves to the same two
columns and call the noise an edge. This document exists so that nobody
has to re-learn that.
