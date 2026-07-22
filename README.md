# 🏈 Gridiron Edge — AI-Powered NFL Prop Engine

An NFL player-prop analytics engine that ingests player form, defensive matchups,
weather and injuries, projects each prop, prices it against the sportsbook line,
and surfaces only the bets where the model believes the book is **mispriced** —
with a plain-English explanation for every pick.

This repository is the **working brain** of that platform. It runs end-to-end
today on realistic sample data, with clean seams where live data sources plug in.

> ⚠️ **Model output, not betting advice.** The bundled slate uses illustrative,
> fictional numbers. Gamble responsibly. 21+.

![dashboard](docs/dashboard.png)

---

## Quick start

No dependencies — just Python 3.9+.

```bash
# 1. Generate recommendations from the sample slate
python3 generate.py

# 2. Launch the dashboard (live API recalculates on every request)
python3 server.py
# → open http://localhost:8000
```

Tighten the model from the CLI or the UI sliders:

```bash
python3 generate.py --min-confidence 7 --min-edge 4
```

---

## How it works

Each prop flows through a pipeline of small, independently testable stages:

```
 slate (stats + lines + weather + injuries)
        │
        ▼
  ┌─────────────┐   recent-form blend: last 1/3/5/10, season,
  │  form.py    │   career, opponent history → base mean + variance + trend
  └─────────────┘
        │
        ▼
  ┌─────────────┐   opponent defense vs position, game script
  │ matchup.py  │   (spread), game total → multiplier
  └─────────────┘
        │
  ┌─────────────┐   wind / rain / snow / cold → per-market multiplier
  │ weather.py  │
  └─────────────┘
        │
  ┌─────────────┐   own-player injury flag + knock-on effects
  │ injuries.py │   (elite CB out → WR up, LT out → QB down, DT out → RB up)
  └─────────────┘
        │
        ▼
  ┌─────────────┐   final projected mean + std (variance floors keep it honest)
  │projection.py│
  └─────────────┘
        │
        ▼
  ┌─────────────┐   best line across books → hit probability (normal model)
  │ betting.py  │   → de-vigged edge → EV → 0–10 confidence → fractional-Kelly stake
  └─────────────┘
        │
        ▼
  ┌─────────────┐   min-confidence / min-edge / injury-hold rules
  │  rules.py   │
  └─────────────┘
        │
        ▼
  ┌─────────────┐   headline + one-line summary + ranked "why" bullets
  │ explain.py  │
  └─────────────┘
```

### The betting math

- **Hit probability** — the projection is a Normal(μ, σ). For an *Over L*,
  `P(hit) = P(X > L) = 1 − Φ((L − μ)/σ)`, computed with `math.erf` (no numpy needed).
- **Edge** — the book's two-way price is **de-vigged** so the implied
  probabilities sum to 1.0; `edge = P(model) − P(book)`.
- **Line shopping** — across DraftKings, FanDuel, BetMGM, Caesars and ESPN BET
  the engine picks the most bettor-friendly number, breaking ties on price.
- **Confidence (0–10)** — driven by edge, discounted for thin samples and high
  variance, so a big edge on two games of data does **not** score like a big
  edge on a full season.
- **Stake** — quarter-Kelly, capped, for bankroll safety.

### Betting discipline (rules engine)

- Only recommend above a confidence **and** edge threshold.
- **Hold any prop whose own player is QUESTIONABLE / DOUBTFUL / GTD** until
  inactives confirm status — even when the raw edge looks great. (See Rashee
  Rice in the sample slate: +9% edge, still benched.)

---

## Project layout

```
engine/
  models.py       dataclasses for players, defenses, weather, injuries, lines
  statmath.py     normal CDF, weighted mean, std (stdlib only)
  odds.py         American odds, de-vig, EV, best-line shopping
  form.py         recent-form blending + trend detection
  weather.py      weather → per-market multipliers
  injuries.py     own-player flags + knock-on matchup effects
  matchup.py      defense-vs-position + game-script adjustments
  projection.py   assembles the final mean + std
  betting.py      hit prob, edge, confidence, stake, grade
  rules.py        recommend / hold decisions
  explain.py      human-readable reasoning
  pipeline.py     orchestrates the whole slate
data/
  sample_slate.json   illustrative slate (7 props across 3 games)
web/                  dashboard (vanilla HTML/CSS/JS, no build step)
generate.py           CLI → writes web/data/recommendations.json
server.py             stdlib web server + live /api/recommendations
```

---

## The road to live data

The engine is deliberately decoupled from its data sources by one seam:
`engine/data_loader.py` produces a `Slate`. Everything downstream is real math.
To go live, replace the sample loader with adapters for:

| Concern            | Suggested source                                             |
|--------------------|--------------------------------------------------------------|
| 3–5 yrs of stats   | **nflverse** (`nfl_data_py`) — free play-by-play & weekly data |
| Sportsbook lines   | **The Odds API** or a books aggregator (7-book comparison)   |
| Weather            | Open-Meteo / a weather API keyed by stadium + kickoff        |
| Injuries           | Official injury reports + a news feed for game-time decisions |

Planned next phases (not yet built):

1. **Historical database** — persist the full per-player metric set (air yards,
   time to throw, YAC, route participation, target share, red-zone usage …) and
   team offense/defense splits described in the project vision.
2. **Learned coefficients** — replace the hand-tuned weather/matchup multipliers
   with values fit on the historical database (gradient-boosted or ridge model).
3. **Live recalculation** — re-run projections on injury news and line moves;
   detect steam / reverse line movement and closing-line value.
4. **Correlation & parlay rules**, referee tendencies, travel/rest, and
   market-vs-model sentiment.

---

## Testing the model quickly

```bash
python3 generate.py            # see the ranked slate in your terminal
python3 -m pytest              # (add tests under tests/ as the model grows)
```
