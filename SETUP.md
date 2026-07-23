# Setup — getting real data flowing

The app runs immediately on bundled sample data with **zero setup**:

```bash
python3 generate.py && python3 server.py     # → http://localhost:8000
```

Everything below is only needed to run on **real** NFL/MLB data. None of it needs
paid infrastructure except the odds feed (which has a free tier). All Python is
standard-library only — there is nothing to `pip install` for the core app.

> Some managed/sandboxed networks block the hosts below (GitHub release assets,
> `statsapi.mlb.com`, `api.the-odds-api.com`). Run these on a normal network, or
> drop the cached CSVs described here.

---

## 0. One-time optional dependency (only for exports)

The core app needs nothing. To *export* nflverse data to the local CSVs used as a
fallback, install the community package once:

```bash
pip install nfl_data_py        # only for the CSV exports in steps 1–2
```

The MLB and odds feeds are plain HTTP — no package needed.

---

## 1. NFL — games (works anywhere, no key)

NFL schedules/weather/spreads live in a public git tree, so this ingests the last
five seasons right away:

```bash
python3 ingest.py nfl            # default = last 5 completed seasons
python3 ingest.py status         # confirm: ~1,700 games ingested
```

## 2. NFL — player logs (release-gated → local CSV)

Weekly player stats live in GitHub release assets. Where those are reachable,
step 1 already pulled them. Where they're blocked, export once to the cache:

```python
import nfl_data_py as nfl
for yr in range(2021, 2026):
    nfl.import_weekly_data([yr]).to_csv(f"data/cache/player_stats_{yr}.csv", index=False)
```

Optional feeds (same pattern, drop into `data/cache/`):

| File                                   | Export                                   |
|----------------------------------------|------------------------------------------|
| `data/cache/injuries_<year>.csv`       | `nfl.import_injuries([year])`            |
| `data/cache/depth_charts_<year>.csv`   | `nfl.import_depth_charts([year])`        |

Then re-run `python3 ingest.py nfl` — the player-log layer fills in on top of the
games.

## 3. MLB — schedule, lineups, logs, weather (free, no key)

The MLB Stats API and Open-Meteo are free and keyless. Build a live slate or
ingest a date's games/logs:

```bash
python3 mlb_build.py 2026-06-20                      # today's live slate
python3 ingest.py mlb --dates 2026-06-19,2026-06-20  # persist into the DB
```

Optional Statcast (expected-stats regression) from Baseball Savant — export once:

```
data/cache/savant_expected_batter_<year>.csv
  ← https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=batter&year=<year>&csv=true
```

## 4. Sportsbook odds (free tier, one key) — both sports

Get a free key at <https://the-odds-api.com>, then:

```bash
export ODDS_API_KEY=your_key
python3 nfl_build.py 2025 5 --odds        # NFL player props across all books
python3 mlb_build.py 2026-06-20 --odds    # MLB player props across all books
```

During a live game the same call returns **in-play** prices, so this is also how
live lines flow in. The same `--odds` call also pulls each game's **moneyline**
(the `h2h` market) in the same request — no extra quota.

### Moneyline picks need two things

The moneyline model prices a team's win probability against the book's line, so
it needs both:

1. **Real moneyline prices** — come free with `--odds` (above).
2. **Team strength ratings** — computed automatically from the scores already in
   your history DB, so make sure you've ingested games:

   ```bash
   python3 ingest.py nfl                      # NFL team ratings
   python3 ingest.py mlb --dates 2026-06-19,2026-06-20   # MLB team ratings
   ```

With both in place, the build prints `N moneyline(s) priceable` and the site's
**Moneyline picks** section fills in. Without ingested games the ratings are
league-average (0), so the model matches the book and shows no edge — that's
expected, not a bug.

---

## 5. Prove it has edge

With the data in place:

```bash
python3 validate.py --seasons 2021-2025   # ingest → backtest → ECE / ROI report
```

Every stage prints `PASS` with real calibration/ROI numbers, or a `BLOCKED` line
telling you exactly which step above to complete.

## 6. Track your bets + size to your bankroll

```bash
python3 ledger.py bankroll --set 1000 --unit 1   # your roll, 1%/unit
python3 ledger.py log --sport nfl                 # record recommended picks
python3 ledger.py settle --sport nfl --actuals results.json
python3 ledger.py report                          # record · ROI · bankroll · CLV
```

On the **website**, open the Recommended tab and enter your bankroll + unit % in
the Bankroll control — every pick then shows its exact dollar stake, sized to your
roll (persisted in your browser; shareable via `?bankroll=1000&unit=1`).

---

## Quick reference — what needs what

| Capability                     | Needs                                   |
|--------------------------------|-----------------------------------------|
| App + sample slate + dashboard | nothing                                 |
| Bankroll sizing (website)      | nothing                                 |
| 5 yrs NFL games                | open network (git tree)                 |
| NFL player logs / injuries / depth | release access **or** local CSVs    |
| MLB schedule / lineups / logs / weather | `statsapi.mlb.com` + `open-meteo` |
| MLB Statcast                   | Baseball Savant CSV                     |
| Real odds / live lines         | free Odds API key                       |
| Moneyline picks (real edge)    | free Odds API key **+** ingested games  |
