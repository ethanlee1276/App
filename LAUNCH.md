# 🚀 Launch Guide — running the website with **live** data

This is the simple, copy-paste version. If you can open a terminal and paste a
line, you can do this. We'll test with **MLB tonight** since games are on, then
the same steps work for NFL in the fall.

> **What "live" means here:** live scores + the current inning, outs and base
> runners (the little diamond), tonight's real lineups and probable pitchers,
> the model's projections for each prop, and — if you add one free key — real
> sportsbook lines including in-play prices.

---

## What you need first (one time)

- **Python 3** — check by pasting this into a terminal:
  ```bash
  python3 --version
  ```
  If you see a version number (3.9 or higher), you're good. If it says "command
  not found," install Python from <https://www.python.org/downloads/> and try
  again.
- **The code** — you already have this folder. Open a terminal **inside it**
  (the folder that has `server.py` in it). Everything below is run from there.

There is **nothing to `pip install`** for the core app. It's all built in.

---

## 🔑 API keys — the complete list (spoiler: just one, and it's optional)

Everything that makes the site *work* is **free and needs no key**: live scores,
innings/outs/bases, lineups, probable pitchers, weather, NFL schedules, ESPN
scores, and the model's own projections. So you can test tonight with **zero
keys**.

There is exactly **one** optional key:

| Key | What it's for | Needed? | Where to get it |
|-----|---------------|---------|-----------------|
| `ODDS_API_KEY` | Real sportsbook lines (DraftKings/FanDuel/etc.) + in-play odds | **Optional** — only if you want real book lines instead of the model's fair prices | Free at <https://the-odds-api.com> (~1 min signup) |

That's it. No other keys exist in this app. MLB, weather, NFL and live scores are
all open feeds.

**To add the key** (only if you want real lines) — one time:
```bash
cp secrets.local.example secrets.local     # make your local key file (gitignored)
# then open secrets.local and paste your key after ODDS_API_KEY=
```
The app reads it automatically after that — no re-typing.

---

## ⭐ The easy way — one command

```bash
python3 launch.py
```

That's it. On startup it grabs the **newest live data for both NFL and MLB**,
then opens the site at <http://localhost:8000>. It keeps the data fresh in the
background every 90 seconds while it runs, so live scores stay current during
games. Any league that's out of season or unreachable is skipped automatically —
the site still comes up. Press **Ctrl+C** to stop.

- Want real sportsbook lines too? `export ODDS_API_KEY=your_key` first (see the
  odds section below), then `python3 launch.py`.
- Don't want the background polling? `python3 launch.py --refresh 0`.

> **One thing to know for the game-level bets.** Player props and live scores
> work immediately. The **moneyline / spread / total / team-total** picks also
> need team-strength ratings, which come from past scores — so run this **once**
> so the model has them:
> ```bash
> python3 ingest.py mlb --dates 2026-06-06,2026-06-13,2026-06-20   # a few recent dates
> python3 ingest.py nfl                                            # in the fall
> ```
> Without it those game bets show ~0 edge (the model just matches the book) —
> that's expected, not a bug.

The step-by-step below does the same thing by hand if you'd rather see each part.

---

## 🟢 Test it RIGHT NOW with MLB (no key, all free)

Three commands. Do them in order.

### Step 1 — Build tonight's live MLB slate

Replace the date with **today's date** in `YYYY-MM-DD` form. Tonight that's:

```bash
python3 mlb_build.py 2026-07-23 --out web/data/mlb_recommendations.json
```

This reaches out to the free MLB Stats API and pulls **tonight's real games** —
scores, current inning, outs, who's on base, starting lineups, probable
pitchers — runs them through the model, and saves the result to a file the
website reads.

You'll see it print the games it found. If a game is in progress you'll see a
score and inning; if it hasn't started yet you'll see the matchup and first
pitch time.

> **If this step errors** with something about connection/blocked host, your
> network is blocking `statsapi.mlb.com`. Try again on a normal home/phone
> network (not a locked-down work/school VPN). Everything else still works — the
> site will just show the built-in sample game until the build succeeds.

### Step 2 — Start the website in live mode

```bash
python3 server.py --live
```

You'll see:

```
Gridiron Edge running (LIVE data) → http://localhost:8000
  MLB: web/data/mlb_recommendations.json (ready)
```

The `--live` flag is the important part — it tells the site to show the file you
just built instead of the practice/sample data.

### Step 3 — Open it and switch to MLB

1. Open your web browser and go to **<http://localhost:8000>**
2. Click the **⚾ MLB** button up top (next to 🏈 NFL).

You should now see **tonight's real games**. On any game that's in progress
you'll see the red **LIVE** dot, the live score, the inning, and the little
**base diamond** lighting up which bases have runners — all updating from the
real feed.

That's it. That's the live test. 🎉

---

## 🔄 Keeping scores fresh during a live game

The website **auto-refreshes every 30 seconds** on its own while a game is live,
but it can only show what's in the file. To pull **new** scores from MLB, re-run
the build. Easiest way — leave the server running in its terminal, open a
**second** terminal in the same folder, and run this loop:

```bash
while true; do
  python3 mlb_build.py 2026-07-23 --out web/data/mlb_recommendations.json
  sleep 60
done
```

That rebuilds tonight's slate every 60 seconds. The website picks up the new
file automatically — you don't touch the browser. Press **Ctrl+C** in that
second terminal to stop the loop. (MLB scores are free and unlimited, so
refreshing once a minute is totally fine.)

---

## 💰 Size bets to YOUR bankroll (optional, no setup)

On the **Recommended** tab there's a **💰 Bankroll** box. Type in your bankroll
(say `500`) and your unit size (say `1` for 1%). Every pick then shows the exact
dollar amount to bet, sized to your roll. It remembers it in your browser, so
you only do this once.

---

## 🎰 Add real sportsbook lines (optional, one free key)

The steps above use the model's own fair prices. To compare against **real**
DraftKings / FanDuel / BetMGM / theScore Bet lines — including live in-play prices:

1. Get a **free** API key at <https://the-odds-api.com> (takes a minute).
2. Run the build with your key and the `--odds` flag:
   ```bash
   export ODDS_API_KEY=your_key_here
   python3 mlb_build.py 2026-07-23 --odds --out web/data/mlb_recommendations.json
   ```
3. Start the server the same way (`python3 server.py --live`).

Now each pick shows the real book line next to the model's number, and the
"edge" is the genuine gap between them.

> **Heads up on the free odds tier:** it allows ~500 requests/month, so do
> **not** put the `--odds` build in the 60-second loop — you'd burn through it in
> a few hours. Use the free score-only loop for live scores, and run the
> `--odds` build by hand every so often when you want to refresh the lines.

---

## 🏈 Doing the same for NFL

Identical idea, different builder. In the NFL season:

```bash
python3 nfl_build.py 2026 5 --out web/data/recommendations.json   # season 2026, week 5
python3 server.py --live                                          # then open the site, stay on 🏈 NFL
```

Add `--odds` (with the same free key) for real NFL prop lines. Live NFL scores
come from ESPN's free scoreboard, so the same rebuild-loop trick works.

---

## Cheat sheet

| I want to… | Command |
|---|---|
| **Launch everything, live (easiest)** | `python3 launch.py` |
| Real book lines too | `export ODDS_API_KEY=…` then `python3 launch.py` |
| Team ratings for game bets (once) | `python3 ingest.py mlb --dates <recent dates>` · `python3 ingest.py nfl` |
| Just try the app, no data | `python3 generate.py && python3 server.py` |
| Build one sport by hand | `python3 mlb_build.py <today> --out web/data/mlb_recommendations.json` then `python3 server.py --live` |
| Stop it | **Ctrl+C** in its terminal |

**Simplest path:** `python3 launch.py` refreshes both leagues and serves in one
step. The by-hand route works too — just remember to build first, **then** start
the server **with `--live`** (without `--live` you'd see the practice game).

21+. Model output, not betting advice. Please bet responsibly.
