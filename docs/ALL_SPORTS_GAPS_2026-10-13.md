# Every sport against the NFL — where our data could do more (2026-10-13)

Ethan, 2026-10-13: *"Figure out where we can use our data more and find
more tools and useful information to help with picks for all sports.
There's gotta be more that we are missing. We worked so hard on nfl so ik
CFB and mlb and nba and ufc is missing stuff."*

Each line is one of five things:

* **Built today**: in the code, tested, on the box within five minutes
  of the push.
* **Box run**: a measurement that needs the box's data; the command is in
  `docs/WHEN_YOU_ARE_HOME.md` under the letter given.
* **Your call**: a decision that costs credits or changes a rule you set.
* **Parked**: possible with our data, waiting on a measurement first.
* **Not possible**: the data does not exist, or no feed we can reach has it.

The rule for all of it is the one the NFL work followed: a new piece of
data is shown first, measured second, and only then allowed to move a
number. Nothing below changes a price without a measurement behind it.

---

## College football

The full checklist is `docs/CFB_PARITY.md`; this is what changed today
and what is still open.

| | Status |
|---|---|
| A receiver thrown at who caught nothing is a 0, not a missing game | **Built today** (step 53, M). The college play file names the target on 78% of 2025's incompletions and 92% of 2026's. Measured on the board's own players before it shipped: the error falls in both seasons for catches and yards |
| How many past voids the play file now shows were thrown at | **Box run** (M, `cfbzeros.py`) |
| Grade a college receiving bet when the play file shows he was thrown at | **Your call** (H). Today a college receiver with no box-score line is voided, by your 2026-09-14 rule |
| The college fits that are built and waiting for data: lineup step, new-QB step, touchdowns-follow-the-total, scout flags, position widths | **Box run**, weekly by themselves; each prints x1.00 (no change) until college's own games pass the NFL's bar. Read-only checks in `CFB_PARITY.md` |
| A college target COUNT | **Not possible** honestly: the feed leaves some incompletions unnamed, so a count would be short |
| Next Gen Stats, FTN charting, PFR advanced, air yards per target | **Not possible**: NFL-only data |

## NBA (opening night is about a week out)

| | Status |
|---|---|
| Where each player plays now (current rosters) | **Built today** (step 54, N). A summer move no longer counts as his old club's player; he gets a prop after three games for the new one |
| A price from a game his team is not in | **Built today**: refused and counted. Every prop now carries its team |
| The injury board in the build | **Built today**: out or doubtful means no bet and the card says so; day-to-day or questionable is held on the Edge board and on Most Likely, as the NFL and NHL hold. The model doc called this "the one gap worth money" |
| A teammate's card says who is out, and his share of the team's stat in the games that player sat | **Built today**: evidence only, from our own logs (`engine/nba/onoff`) |
| Should a teammate's NUMBER move when a regular sits? | **Box run** (O, `nbavacancy.py`). The minutes model has an empty slot for the minutes a vacancy opens; the books raise teammates' lines when a star sits; if our number runs low in those games, our card leans under on exactly those lines. The bar is written in the script before the first run |
| Points + rebounds, points + assists, rebounds + assists markets | **Your call**. Built from columns we already store, like PRA, but each market costs credits on every game pulled (the API bills per market) |
| Steals, blocks, turnovers | **Parked**: the box scores we ingest do not carry them yet (minutes, points, rebounds, assists, threes); the ingest would need the columns first |
| The grade's "freshness" piece tops out at 0.9 because "there is no availability feed" | **Parked**: there is one now. Leave the cap until the injury board has a few weeks of record behind it |
| Confirmed starting lineups, referee assignments | **Not possible**: no feed we can reach publishes them |

## MLB (postseason now; the regular season is over)

| | Status |
|---|---|
| Why the profit calendar stopped at September | **Box run** (I, waiting on your paste) |
| Line movement's predictive value (`movecheck.py`) | **Parked**: movement adjusts the MLB grade today on a signal that has not been measured (MLB_MODEL #80). Spring is the time to measure it |
| Pitch-level reads: velocity drop, shelved pitch, arsenal vs a hitter's weakness by pitch type | **Parked**: built and journaled as evidence (`velo_delta`, `arsenal`); priced only when `stakecheck --info` says so |
| Alternate-line ladders | **Parked**: the odds feed carries MLB main lines; ladders cost credits |
| Defence (OAA), catcher pop time, travel fatigue | **Not possible yet**: no free feed we can reach |
| Public bet percentages | **Not possible**: no source |

## UFC

| | Status |
|---|---|
| Where each fight's line opened and where it is now | **Built today** (step 56, P). The build has stored every book's price on every paid pull since 2026-08-10, and nothing read it. Every pick and pass card now says it, and which way it moved for the pick. Evidence only: the grade's movement piece stays empty until it is measured |
| Does our UFC number know anything the price does not? Did our picks beat the close? | **Box run** (P). The same information test and closing-line read the NFL record has had since August, on the UFC picks journaled since then |
| Method props (KO, submission, decision) at real prices | **Parked**: the odds feed carries only the moneyline for MMA. The card already shows our fair price for every method to shop by hand |
| Round props and "goes the distance" | **Parked**: needs finish times per fight, which ufcstats fight pages carry and our dossiers do not yet. A box-side pull could add them |
| Camp reports, referee assignments | **Not possible**: no structured source |

## Every sport

| | Status |
|---|---|
| Does each sport's number know anything the price does not? | **Box run** (P's second command, every sport in one go). The August test said: across the record, no (AUC 0.479 for our claimed edge). Re-running it per sport says where that is still true |
| A last look before kickoff: pull or flag a pick whose line moved a point against it | **Your call** (H), after L's read of the repaired closes |

---

The lettered blocks (M, N, O, P) are at the top of
`docs/WHEN_YOU_ARE_HOME.md`; the numbered steps (53 to 56) explain each.
