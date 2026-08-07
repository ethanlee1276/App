# The two Routines

**Both are scheduled and live as of 2026-08-07.**

| | trigger | schedule (UTC) | local |
|---|---|---|---|
| nightly code health | `trig_0132CD3JgU6TJTijmBjCWuf1` | `0 11 * * *` | 7:00 AM ET |
| weekly deep sweep | `trig_01T6HVdd3VN7SceXshHa7SM7` | `0 12 * * 0` | 8:00 AM ET Sundays |

Both fire a fresh session per run, with push notification on. The prompts
below are what was created, verbatim.

## The four sessions of "blocked by approval" were my mistake

This file previously said `create_trigger` sat behind an account-level
approval nobody could clear, on the evidence of
`MCP error -32003: MCP tool call requires approval` across four sessions.

That was wrong, and the way it was wrong is worth keeping. **I was calling
the tool under the wrong server name.** The MCP server is named for a UUID
— `mcp__bf7c680d-5fdc-5ef4-b4a0-abadb619bf0a__*` — and I kept calling
`mcp__Claude_Code_Remote__*`, a name that reads like the right one and does
not exist. An unmatched tool name matches no allow-rule, falls through to
"requires approval", and in a session with nowhere to show a prompt comes
back as -32003.

`.claude/settings.local.json` had already allowed
`mcp__bf7c680d-5fdc-5ef4-b4a0-abadb619bf0a__create_trigger` the whole time.
Called by its real name, the read-only `list_triggers` returned an empty
list immediately.

The lesson is the one this repo keeps relearning: **an error message
describing a permission is not evidence that a permission is missing.** I
read the message, believed it, wrote it down as fact, and repeated it three
more times without once checking the name I was calling. Four sessions of
"waiting on approval" were four sessions of a typo.

## Why they are worth having at all

A Routine can do one thing GitHub Actions cannot: **fix what it finds and
push the fix.** Actions can only go red. That difference is the entire
argument for scheduling these, and it is why the nightly one's job is
mostly "if the suite is red, make it green".

Everything a Routine could check *without* fixing is already covered by
`.github/workflows/nightly.yml`, which has been running since 2026-08-02
on the same 7am-ET schedule.

## What a fired session can and cannot see

Both prompts say this, and it is the thing that goes wrong if omitted. A
Routine fires into a **fresh clone** in a remote container:

* `data/history.db`, `data/ledger.db` and `web/data/` are gitignored, so
  the bet journal, the stats and the built slates are **not there**.
  `doctor.py`'s data checks correctly report "not my machine". That is
  right behaviour, not a finding.
* `statsapi.mlb.com` and the odds APIs are **not reachable**. Anything
  needing a live slate — `sim_reconcile.py`, a real build — cannot run.
  Its absence is not a failure either.

A session that forgets this reports the environment as broken every night,
and a report that is wrong every night is one nobody opens.

---

## Routine 1 — Nightly code health check

**Schedule:** `0 11 * * *` (UTC; 7:00 AM Eastern)
**Mode:** fresh session per firing · push notification on

```
Nightly health check for Qellys Book (repo ethanlee1276/App, branch
claude/sports-betting-app-vhgmho).

IMPORTANT — know what you can and cannot see. The databases
(data/history.db, data/ledger.db) and web/data/ are gitignored, so this
fresh clone does NOT have Ethan's real bet journal, stats, or built
slates. doctor.py knows this and its data checks will report "no X on this
machine". That is correct behaviour, NOT a finding. Never report on data
you do not have, and never suggest he re-ingest or re-settle based on this
session — the real-data check runs on his laptop inside `python3
launch.py`.

Egress note: statsapi.mlb.com and the odds APIs are NOT reachable from
this environment. Anything needing a live slate (sim_reconcile.py, a real
build) cannot run here. Do not report their absence as a failure.

What you ARE checking is the code.

1. git checkout claude/sports-betting-app-vhgmho && git pull origin
   claude/sports-betting-app-vhgmho
2. Run: python3 doctor.py --code-only   (the six data checks correctly say
   "not my machine" on a fresh clone, and six warnings a night teaches you
   to stop reading the run). Note the verdict.
3. If the test suite fails, this is the whole job. Diagnose it, fix it,
   add or correct tests, run python3 run_tests.py until green, commit,
   push. A red suite on the working branch is the one thing worth waking
   someone for.
   Before assuming the code is wrong, check whether the TEST is: a test
   that reads a real store, a real database, or the network will pass here
   and fail on his laptop, or the reverse. That class of bug has bitten
   this repo three times — test_prose.py fell through to a paid API call,
   and test_doctor_learning.py read the live learning stores. If a test's
   verdict depends on machine state, isolate it.
4. If the suite is green, do a short code-health sweep and fix ONLY what
   is unambiguous:
   - Python modules that fail to import across engine/ and *_build.py
   - Dead code you can prove is dead: a CSS selector matching no element,
     a var() fallback for a token that exists, a function nothing calls
   - CSS comment blocks that reopen (test_comments_are_balanced covers
     this — check it still covers everything)
   Anything needing a judgement call: do NOT fix it. Write it down and
   report it.
5. Commit anything you changed with a message explaining the reasoning,
   not just the change, ending with:
   Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
   Push with: git push -u origin claude/sports-betting-app-vhgmho
   Never push to another branch. Never open a pull request.

Report back ONLY if something was wrong or you changed something. If the
suite was green and the sweep found nothing, say exactly that in one line
and stop — a nightly "all clear" every morning trains him to stop reading
them.

Never put a model identifier in a commit message or any file in the repo.
```

---

## Routine 2 — Weekly deep sweep

**Schedule:** `0 12 * * 0` (UTC; 8:00 AM Eastern, Sundays)
**Mode:** fresh session per firing · push notification on

Chosen by Ethan on 2026-08-05 over a chore-nag and a calibration watch.
Its job is precisely the half the nightly Routine is **forbidden** from
touching: the judgement calls. It reports; it does not autonomously
rewrite the models.

```
Weekly deep sweep for Qellys Book (repo ethanlee1276/App, branch
claude/sports-betting-app-vhgmho).

Same visibility limits as the nightly run, and they matter more here
because this session is asked to form opinions. This is a fresh clone:
no ledger.db, no history.db, no web/data/, and no route to
statsapi.mlb.com or the odds APIs. Never report missing data as a finding
and never recommend an ingest or a settle from this session.

The nightly run fixes what is unambiguous and is explicitly told to write
down anything needing judgement rather than touching it. This is where
those get looked at. You are REPORTING, not re-architecting: do not change
a model constant, a threshold, or a pricing path. Fix only documentation
and comments, and only where the code is unambiguously the source of
truth.

1. git checkout claude/sports-betting-app-vhgmho && git pull
2. python3 run_tests.py — if red, stop and say so; the nightly Routine
   owns that and duplicating the fix risks two sessions pushing at once.
3. python3 mapcheck.py — the implementation maps' ✅ rows against the
   code they cite. It only checks that cited files and symbols still
   EXIST; it cannot tell whether the code does what the row claims. That
   second question is yours. Spot-check three or four ✅ rows per model
   doc against the actual implementation and report any that overstate.
4. Backlog vs reality. Read the pending tasks and the "still open" notes
   in docs/COMPETITIVE_RECIPE.md. Report:
   - anything marked pending that the code shows is finished
   - anything marked done whose evidence you cannot find
   - anything blocked on a condition that has since cleared
5. Read the last week of commits (git log --since="7 days ago"). Report
   any change that shipped WITHOUT a test, and any constant that moved
   without its comment moving with it. This repo's convention is that a
   number carries the measurement that set it; a number that lost its
   provenance is the finding.
6. Report ONE digest, ordered by what would cost the most if left. Say
   plainly when a week found nothing — that is a real answer, and padding
   it teaches him to skim.

Commit only documentation fixes, with reasoning, ending:
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Push with: git push -u origin claude/sports-betting-app-vhgmho
Never push elsewhere. Never open a pull request. Never put a model
identifier in a commit or any file.
```

---

## The mechanised part, which needs no permission

`mapcheck.py` is step 3 of the weekly sweep, extracted so it runs whether
or not a Routine ever fires. It parses every implementation map, pulls the
backticked files and symbols out of each ✅ row, and checks they still
exist — 133 rows in about two seconds. It runs in CI on every push and
every night.

It is deliberately the dumb half. It cannot tell whether `engine/rules.py`
really implements a forcing rule; it can tell you the constant that row
names was renamed three weeks ago. Nobody was ever going to check that by
hand, and the maps are what get believed.

`lineupwatch.py` is the other one — and unlike the two Routines above it
must run on the laptop, not in a fired session, because a fired session
can reach neither `statsapi.mlb.com` nor the odds feed.

§5 holds every MLB hitter prop until its lineup is posted, and the parlay
screen fails closed on it. So an afternoon board carries one leg per game
— the starting pitcher — no same-game pair exists anywhere on the slate,
and the Parlay Zone has nothing to offer but cross-game constructions that
§0.3 proves singles beat. A 1pm build and a 5pm build are different boards
from the same data, and remembering which one you are looking at is
exactly the chore that should not depend on remembering.

    python3 lineupwatch.py --check      # report, never build
    python3 lineupwatch.py              # build if cards have posted
    python3 lineupwatch.py --watch      # poll until the slate is set

The design rests on one asymmetry: **lineups are free, rebuilds are not.**
Cards come from `statsapi.mlb.com`, which is unmetered; only the rebuild
spends Odds API credits. So it polls as often as is useful (`--every`,
floored at the boxscore cache's own 5-minute TTL — below that it re-reads
one file and learns nothing) and builds as rarely as is useful:

* `--min-gap` (25m) — cards trickle out over an hour or more. Rebuilding
  on each one spends a day's credits to reach the board one build at the
  end would have produced.
* `--max-builds` (3) — a ceiling per run, so a pathological night cannot
  drain the budget. Checked BEFORE the gap, or a run at its ceiling
  reports a wait that will never end.

The trigger is cards posted **since the board was built**, never an
absolute count — otherwise every poll after the first rebuilds forever.
`decide()` is pure and tested without a network or a clock; the API half
is a thin wrapper on purpose.

Run it once when you sit down, or leave `--watch` going through the
afternoon. Either way the board you read is the board the cards support.


---

## The Mac-side runner, which is not a Routine

`tools/install-nightly.sh` installs a launchd agent that runs
`tools/nightly.sh` at 06:00 local. That script runs `launch.py` (ingest,
settle, rebuild, `doctor.py` against **real** data) and then `watch.py`.

It is not a fallback for the Routines and never was. The division is about
where the data lives:

| | GitHub Actions | Routine | launchd on the Mac |
|---|---|---|---|
| sees the code | yes | yes | yes |
| sees `ledger.db` | no | no | **yes** |
| can reach the sports APIs | no | no | **yes** |
| can fix and push | no | **yes** | no |

So the Routines maintain the code, and the Mac-side runner is the only one
of the three that can say anything about the model. Both are wanted.

One consequence of how the triggers were created: they store no MCP
connectors, so a fired session has no `mcp__*` tools — including the GitHub
ones. That is fine here because both prompts push with plain `git`, which
the fired session's credentials already cover. It would matter if a prompt
were ever rewritten to use the GitHub MCP tools.

launchd rather than cron for one reason that matters on a laptop: a
`StartCalendarInterval` job runs when the machine **wakes** if it was
asleep at the scheduled hour. A cron job shut out at 6am is simply skipped,
and skipped ingest is the failure this is meant to prevent — it has already
happened once, on 7-27/7-28/7-30.

    bash tools/install-nightly.sh              # 06:00 local
    bash tools/install-nightly.sh --at 04:30   # some other hour
    bash tools/install-nightly.sh --now        # run it once, now
    bash tools/install-nightly.sh --remove

`watch.py` prints nothing on a quiet night and sends no notification. That
silence is the design: a nightly ping that says "all fine" every day gets
swiped away, and then so does the one that mattered.

## Turning the Routines off

    list_triggers                       # ids, schedules, next run
    delete_trigger trig_...             # permanent
    update_trigger trig_... enabled:false   # keeps the run history

Or from claude.ai's Routines UI.
