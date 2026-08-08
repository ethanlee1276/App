# When you get home — the laptop checklist

Written 2026-08-07, revised 2026-08-08. Everything here needs the Mac,
because the container has no ledger, no route to the sports APIs, and no
browser you can look at.

Ordered so that each step is worth doing whether or not you get to the next
one. If you only do one thing, do §1.

**Push state: nothing outstanding.** Everything discussed is on
`claude/sports-betting-app-vhgmho`.

**Done since the first version:** the units rescale (§1 as written on the
7th) is complete — don't run it again. The loss-miner read below still
stands.

---

## 1. Pull, then two ingests — 15 minutes, do it first

Two days of work — real team logos on every sport, player faces on NFL, NBA,
WNBA and MLB, the preseason board, and a crash on the NFL offseason section
— is inert on your machine until you pull. The faces need more than a pull:
the photo URL is captured **during ingest**, so the table is empty until the
hoops seasons are re-read.

```
git pull
python3 ingest.py wnba --seasons 2025-2026
python3 ingest.py nba  --seasons 2025-2026
python3 ingest.py nfl
python3 launch.py
```

`ingest.py nfl` is the one that matters most and has never been run. Without
it there are no NFL team ratings, so `game_bets` is empty and the
moneyline/total/spread board cannot price at all — which is most of what the
NFL board is for during the three weeks its props are dark (§3a).

What you should see afterwards: photos instead of initials on NBA, WNBA and
MLB prop cards, real logos beside team names everywhere, and the offseason
coach-change rows rendering at all — they were throwing a TypeError and
taking that whole section down.

Anything that can't load a photo falls back to the team-coloured chip it drew
before, so a missing face is cosmetic, never a hole.

## 2. Read the loss miner before it prices anything

```
python3 -m engine.losspatterns
```

Writes nothing. It prints which slices it has convicted and what the veto
would block. The `home_runs` slice now closes, and its reading says 100% of
those are `longshot` bets with the block landing on recommendations. Decide
whether you want that veto live before anything runs `--apply`.

---

## 3. NFL — the part that changed today

I measured three things in the container this afternoon. Two of them move the
NFL plan.

### 3a. The prop board is empty for Weeks 1–3 (#83) — the real finding

Measured against the cached 2025 season, not predicted:

```
2025 week 1:    0 props,   0 players
2025 week 2:    0 props,   0 players
2025 week 3:    0 props,   0 players
2025 week 4:  235 props, 235 players
2025 week 5:  231 props, 231 players
```

Two lines cause it. `player_game_logs()` at `engine/sources/nflverse.py:184`
keeps only `0 < wk < upto_week` — one season, no cross-season carry anywhere
in the file. And `build_slate()` at `nflverse.py:379` skips any player with
`len(logs) < 3`. Week 1 has zero prior weeks, week 2 has one, week 3 has two.
Week 4 is the first with three.

For 2026, from the cached schedule:

| week | dates | props |
|---|---|---|
| 1 | Sep 9 – Sep 14 | none |
| 2 | Sep 17 – Sep 21 | none |
| 3 | Sep 24 – Sep 28 | none |
| 4 | Oct 1 – Oct 5 | appear |

**The NFL prop board would be dark for the first 23 days of the season.**

What still works in those weeks: `build_games()` needs only the schedule, and
the cached `games.csv` already carries real spread and total for all 16 Week 1
games. So the game-level board — moneyline, total, spread off team ratings —
and futures are unaffected. It is specifically the player props that vanish.

**DONE — you chose "build it with the reset gate", and it is built.** On the
2026 week-1 slate it now builds **293 props across all 32 teams**, up from
zero. `launch.py` passes `--carry` on every NFL refresh and it stands itself
down as soon as the season has three real games, so there is nothing to turn
off in October.

Two things the measurement changed, both written up in `docs/NFL_MODEL.md`:

* **The shrink is mild, not heavy.** Fitted on 2024 → 2025 weeks 1-3, the
  best `k` is 2 across every market — an 11% pull toward the positional mean
  on a 17-game log. My plan assumed a stale season needed heavy regression;
  measured, that is wrong in the expensive direction, costing 39% on
  receiving yards if taken all the way.
* **The offseason reset warns instead of discarding.** Discarding a mover
  leaves nothing to project from, so he drops off the board — the exact
  problem being fixed. Level-matched, movers are not consistently worse, and
  fitting them separately returns the same `k = 2`. So 105 flagged movers
  keep their baseline and say so on the card. `DISCARD_ON_RESET` is there to
  revisit it when there is enough data.

Nothing here needs you. Run it if you want to see it:

```
python3 nfl_build.py 2026 1 --carry --injuries --depth
```

Without `--odds` every edge reads +0.0% — the proxy line is derived from our
own baseline, so the model is pricing against itself. That is pre-existing
and expected; real edges need real book lines.

### 3b. The dress rehearsal can happen tonight, not Aug 24 (#41 corrected)

Task #41 says to rehearse against "a real preseason slate." That is not
reachable. The cached nflverse `games.csv` holds 7,548 games and its
`game_type` values are `REG/WC/DIV/CON/SB` only — **zero preseason rows**.
Preseason is not in this data source at all.

But 2026 Week 1 is already in there with real market lines on all 16 games,
so the rehearsal can run now:

```
python3 nfl_build.py 2026 1 --games-only
```

That one is verified — I ran it here this afternoon and it printed all 16
games with spreads, totals and roofs. The full build is the one to try on
your machine:

```
python3 nfl_build.py 2026 1 --injuries --depth --out /tmp/nfl2026wk1.json
```

Expect it to stop at the props with a `player_stats_2026.csv` 404 — that file
cannot exist until games are played, and that is §3a again rather than a
separate fault. What you are checking is that the games, injuries and depth
layers all come through, and that the game-level bets price.

Note the message it prints blames "GitHub release access is blocked by this
environment's egress policy" when the actual error is a plain 404. Cosmetic,
but it will send you chasing a network problem that isn't there.

### 3c. `launch.py` will not touch NFL until Sep 2

`_current_nfl_week()` at `launch.py:224` only calls a week current if the
nearest game is within 7 days. Week 1 opens Wed Sep 9, so the NFL board stays
on its existing data until **Sep 2**, then starts refreshing nightly. That is
correct behaviour, not a bug — but it means between now and Sep 2 the only way
to exercise NFL is `nfl_build.py` by hand, as in §3b.

### 3d. Two things to confirm during the rehearsal

- The NFL journal writes `move_delta` and `move_steam`. The movement capture
  from `c8657de` went in on the shared ledger path so it should, but it has
  never run on an NFL slate.
- `python3 nflguard.py` should read **TOO EARLY** until Week 1 settles. That
  is the correct output, not a failure.

### 3e. The stopping rule is already armed

No action — recording it so the NFL section is complete. `MARKET_TIER` in
`engine/quality.py` is entirely NFL markets and `TIER_MIN_EDGE`/`TIER_SHRINK`
are shared, so NFL prices through the identical gate that MLB's +12-point
over-claim inverted. `nflguard.py` watches cumulative calibration z at
boundary 2.5, looks after each date once 25 bets settle, first crossing wins.
Against a real 12-point gap at 15 bets/week it catches 96% of seasons, median
105 bets, week 7. Against an 8-point gap, 64%. Against 5 points, 30% — and 5
points already inverts the window. **Silence means not catastrophically
dishonest. It does not mean honest.**

`watch.py` runs it nightly for NFL and CFB, so a crossing reaches you as a
notification rather than something you have to remember to check.

---

## 3f. College — the conference feed went quiet (#93)

Found by `--audit cfb` on the 8th, and it is not an audit problem. ESPN's
groups endpoint stopped returning conferences while the teams endpoint on the
same host answered fine. Conference feeds `attention_tier`, which is how the
CFB model decides whether the market is looking hard at a game — so with the
live feed gone, the whole sport resolves through a **twelve-row built-in
table**, and `cfbdata`'s own header says that table exists to be overridden
because "conferences in this sport move around constantly." Post-realignment,
its `Pac-12` entry is close to fiction.

**Resolved, and the answer is that this feed cannot give us conferences at
all.** Your three runs settled it. The host was never down; every shape
returned valid JSON. The shape dump showed why nothing came out:

```
{status, groups: [ {name, abbreviation, children: [
    {name, abbreviation, teams: [ {id, name, abbreviation, logos, ...} ]}
]} ]}
```

Two facts, neither guessable:

- **The group nodes carry no id.** Only teams do. So `{group_id: name}` —
  what this module has asked this endpoint for since it was written — was
  never buildable from it.
- **The four children are NCAA divisions**, not conferences: FBS, FCS,
  Division II, Division III. There is no conference node anywhere in the
  tree. And the team lists paginate at 25, so the 100 rows it returns are a
  page, not a roster.

**I shipped a bug on the way here and your output caught it.** For one
commit I read those division labels as conferences and wired them into
`parse_scoreboard`. That would have told `attention_tier` that Alabama's
conference is "FBS" — dropping every power-five school out of the power set
and pricing the SEC as though nobody was watching it. Reverted; conference
resolution is back on `conferenceId` and the built-in table, exactly as
before any of this. A test now fails if that map is wired into naming again.

So the honest state: **CFB conference resolution is unchanged and still runs
on the twelve-row checked-in table.** What was gained is knowing the live
feed cannot replace it, instead of assuming it was temporarily broken. The
audit still needs a D-I filter and still does not have one — a paginated
list is worse than none, so it audits all 756 and says so.

I also removed a `conf` field I had added to the team payload on the guess
that ESPN ships `conferenceId` there. It doesn't, nothing read it, and it was
riding along on 756 rows to the browser.

`limit=900` was the last idea and it did not lift the pagination — still 25
per division. So the endpoint is a dead end and the build has stopped asking
it: `fetch_conferences` made four requests per cache miss to be told again
what three runs already established. `assets.py --conferences` still probes
on demand, so re-checking after any ESPN change is one command, not a code
edit.

**Nothing here needs you any more.** It is closed, with one real thing left
over that this feed can no longer answer:

### Is the built-in conference table still right? (open)

`CONFERENCE_IDS` in `engine/sources/cfbdata.py` is twelve rows and it is now
the *only* source for a game's conference. It still lists `Pac-12`, which
after realignment is two schools rather than a conference — and conference
feeds `attention_tier`, which decides how much of an edge to believe based on
how hard the market was looking.

Neither feed can answer this alone. CFBD knows which conference each school
is in and knows nothing about ESPN's numeric ids; the ESPN scoreboard stamps
every team with a `conferenceId` and never says what it is called. One school
in both gives one row of `{conferenceId: name}`, and a busy Saturday gives
most of the table.

```
python3 assets.py --conf-table 2025-11-01
```

Read-only, cache bypassed, changes nothing. Pick a **past Saturday in
season** — the more games, the more of the twelve rows get covered. It joins
the two feeds and prints each id as `matches`, `RENAMED -> x`, `NEW -> x`, or
`not on this slate`.

Send it. `RENAMED` and `NEW` rows are the table rotting and I will correct
them; `not on this slate` proves nothing either way, so a second run on a
different date fills in what the first missed.

If CFBD's rows turn out not to carry a conference, the probe dumps their
shape rather than guessing — that is the one habit worth keeping from the
four rounds this cost on the groups feed.

CFB opens in about three weeks, so this is the one dated item on the list.

Also worth a run while you are there, now that the audit filters to schools
that can actually reach a D-I board:

```
python3 assets.py --audit --sport cfb
```

The first line says which filter applied. If it reads *"the teams feed
carries no conference marker"* then ESPN does not ship that field and I need
a different way to tell a Big Ten school from a JUCO — the 92 misses in the
last run were all NAIA and D-II schools that render the monogram chip and
have never been on your board.

---

## 3g. Check the keys — one command, safe to paste

**Run 2026-08-08: all four present and correctly named.** Anthropic 108
chars, CFBD 64 chars and answering, and two Odds keys — one with ~11k
credits, one spent. Details in §7. Re-run this whenever a layer goes quiet.

```
python3 keycheck.py
```

It reports each variable NAME, whether something is set, how long it is, and
what the provider says when asked. **It never prints a key** — not the value,
not a prefix, not the last four characters, and anything a provider echoes
back in an error is scrubbed before printing. Paste the whole output.

It costs nothing. The Odds API is asked for `/sports`, which does not count
against quota and returns your remaining balance in a header — so the check
that proves a key works also tells you what is left on it, per key. CFBD gets
one small request. **Anthropic is checked for presence only**, because every
call to that API costs money and a validation that bills you is not a
diagnostic.

The names are exact and case-sensitive, and this is the failure worth ruling
out — a key set under a name the code does not read is invisible to it:

```
ANTHROPIC_API_KEY=...
ODDS_API_KEY=...
ODDS_API_KEY_2=...        # the second plan; _3, _4 … also read
CFBD_API_KEY=...
```

One `NAME=value` per line, no `export`, no quotes. Every consumer degrades
politely when its key is missing — the college board just runs without a
preseason prior, the odds layer just falls back to proxy lines — which is
correct behaviour and exactly why a missing key can sit unnoticed for a
month.

---

## 4. Website visuals

The design queue is empty — all four items shipped, each with a before/after
number in its commit. What's left is one decision and one look.

### 4a. The one decision: split `--text-mute` (#82)

`--text-mute` measures APCA **Lc 15** on every dark ground — the point of
invisibility — and it is used **108 times**, on things people need to read:
`.section-title`, `.tile .k` (the label on every metric tile), `.matchup
.away`, `.pick .book`, `.game-sub.starters`.

Be exact about the standard: this is *not* the "WCAG flatters dark pairs"
case from the manual. It measures 2.57:1 in WCAG terms, which fails AA for
large text (3.0) as well as normal (4.5). Both algorithms agree it is too
faint.

It cannot simply be made lighter. The tiers by OKLCH lightness:

```
--text       L 0.919    Lc 90
--text-dim   L 0.708    Lc 51   (already under its own 60 target)
--text-mute  L 0.441    Lc 15
```

Reaching Lc 60 needs `--text-mute` at L 0.761, which is **brighter than
`--text-dim`**. The hierarchy inverts. What each target costs:

```
Lc 30 (decorative)   L 0.566   #7B766D
Lc 45 (large/bold)   L 0.670   #9A958C
Lc 60 (secondary)    L 0.761   #B6B1A8   <- passes --text-dim
```

The real fault is one token doing two jobs — decorative furniture, and
readable secondary content. The repair is to split it and decide which of the
108 sites go in which tier. **A suggested shape, not a decision:**
`--text-mute` stays quiet at ~L 0.57 (Lc 30), a new `--text-quiet` at ~L 0.67
(Lc 45) takes the readable labels, and `--text-dim` probably wants to come up
too.

Also under target: `--bad` at Lc 36, below the 45 large/bold bar. Negative-EV
and error text is set in it.

```
python3 contrast.py --wcag     # the whole table, writes nothing
```

`tests/test_contrast.py` is a ratchet, not a standard: it pins today's numbers
and fails if any pair gets fainter. So the decision stays open instead of
quietly getting worse while nobody looks.

### 4b. The one look: seven changes you have not seen on a real screen

All shipped, all test-pinned, none eyeballed by you. Run `python3 launch.py`
and look at a board page and the Record page at both phone and desktop width:

- `afa618b` — real minus signs (U+2212) on every number, chosen by measured
  font metrics. Check dates still read `2026-08-07` with hyphens; that
  regression happened once and the guard is a preceding-character rule.
- `8795028` — the dark neutrals moved onto hue 84, the same hue as the rest of
  the palette. Backgrounds should read very slightly warm rather than blue.
- `4c20069` — nav indicator and confidence bars now animate on `transform`
  instead of `width`/`left`. Should feel identical but smoother; watch the
  nav underline as you switch tabs.
- `9205827` — five box-shadow transitions removed (the shadows themselves were
  already gone, so these were animating nothing).
- `5dc3c82` — apostrophes curled in copy, and only in copy.
- `55640ae` — one span on the Edge Board was painting a green the palette does
  not own.
- `d1f0cc5` — the contrast measurement itself; nothing visual changed.

If any of it looks wrong, the number that justified it is in the commit
message, so we can argue with the measurement rather than with taste.

---

## 5. Infrastructure — two things that only need a terminal

### 5a. Install the nightly job

```
bash tools/install-nightly.sh --now      # run once, read the log
tail -40 logs/nightly-$(date +%F).log
bash tools/install-nightly.sh            # then schedule for 06:00
```

Runs `launch.py` then `watch.py`. **`watch.py` prints nothing on a quiet
night — that silence is the design**, not a broken install. The log is how you
tell the difference.

### 5b. Approve `update_trigger` (#79)

The two Routines have a silent-push-failure hole: a run can do its work and
fail to push without saying so. The prompt fix is written up in
`docs/ROUTINES.md` under "Amendment after run #1".

It needs approving from the **Claude Code desktop app or CLI on the Mac** —
web and mobile have nowhere to show the permission prompt. Or paste both
prompts into the claude.ai Routines UI by hand, which needs no approval.

---

## 6. Diagnostics sweep — five minutes, all read-only

```
python3 barcheck.py     # why a higher edge bar cannot fix the over-claim
python3 movecheck.py    # expect NOTHING TO MEASURE YET — correct
python3 nflguard.py     # expect TOO EARLY — correct
python3 watch.py --all
python3 gapcheck.py     # expect "cannot be answered yet"
python3 assets.py --conferences        # §3f — the one I need output from
python3 assets.py --probe --sport nba  # confirms the face resize
```

None of these write anything. Three of them are supposed to decline to answer
right now, and knowing which three is the point of running them.

The two `assets.py` runs are new. `--probe --sport nba` should show the
combiner at ~15KB against ~274KB raw — that measurement is already in hand
and the run is just a regression check. `--conferences` is the one carrying
real information.

---

## 7. The Odds API keys (#76) — now answerable in ten seconds

**Measured 2026-08-08 by `keycheck.py`:**

```
ODDS_API_KEY     10,965 credits left,  9,035 used
ODDS_API_KEY_2            0 left,     20,000 used   — SPENT
```

Both keys are live and correctly named; the second one's plan is simply
exhausted, and the ring skips a spent key automatically, so nothing is
broken. Between them you are running on ~11k credits until the second
plan resets.

That also settles the leak question below without any guesswork. Open
`secrets.local` and see which line the key starting `5dc51e48` is on:

- it is **`ODDS_API_KEY_2`** → do nothing at all. That key has zero credits;
  someone holding it can spend nothing.
- it is **`ODDS_API_KEY`** → that is the one with 10,965 credits on it.
  Regenerate at your leisure, keep the old line in the file, and add the new
  one — the ring skips dead keys.

Original write-up follows, still accurate on everything else.



Not a blocker, and I previously wrote it up as though it were. It is a quota
credential, not a payment method: the worst case is someone spending credits,
and if the leaked one is your exhausted key the worst case is nothing.

Verified: `git grep` and `git log --all -S` both return zero — the key never
reached the repo or its history. `secrets.local` and its variants are
gitignored at `.gitignore:29-31`.

Open `secrets.local` and check whether `5dc51e48…` is the dead key or the live
one. Dead → do nothing, just don't top that one up. Live → regenerate at your
leisure. Your two-key setup is already the design: `oddsapi.py:284-305` reads
a ring (`ODDS_API_KEY`, `ODDS_API_KEY_2..n`, or `ODDS_API_KEYS` comma-
separated), `get_api_key()` returns the first with credits left, and line 427
swaps to the next key and retries the same call when one comes back exhausted.
Keep both in there, dead one included — the ring skips it.
