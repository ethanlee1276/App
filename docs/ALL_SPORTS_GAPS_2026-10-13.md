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

**Brought up to date 2026-10-14** (Ethan: "save all codes and ideas"):
the rows built since the 13th say so, with their runbook step; a fifth
kind of line, **Idea**, is something offered and not built, waiting on a
yes in block H of `docs/WHEN_YOU_ARE_HOME.md`. One row was wrong: MLB's
defence, catcher pop time and travel were "not possible"; Savant publishes
the first two on the site we already read, and travel comes from our own
schedule.

---

## College football

The full checklist is `docs/CFB_PARITY.md`; this is what changed today
and what is still open.

| | Status |
|---|---|
| A receiver thrown at who caught nothing is a 0, not a missing game | **Built today** (step 53, M). The college play file names the target on 78% of 2025's incompletions and 92% of 2026's. Measured on the board's own players before it shipped: the error falls in both seasons for catches and yards |
| How many past voids the play file now shows were thrown at | **Box run** (M, `cfbzeros.py`) |
| Grade a college receiving bet when the play file shows he was thrown at | **Built today** (step 59, R), your call answered. A receiving bet on a man with no box-score line waits for the play file: thrown at is graded at zero, absent from it is voided as before, and past grades stay as they were |
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
| Points + rebounds, points + assists, rebounds + assists markets | **Built today** (step 60, S), your call answered. Priced, graded and named like PRA; 16 credits an NBA event instead of 13; the WNBA's request is unchanged |
| Most Likely for PRA and the three combos | **Built 2026-10-14** (steps 75 and 77; AG, AI), your call answered ("Ya do the self tuneung"). The walk adds the parts up, so all four are measured, and each is shelved only if it clears the floor; the calibration and player-memory fits read them too |
| Steals, blocks, turnovers | **Built 2026-10-14** (step 75, AG): the ingest stores them, the board prices them (three more credits an NBA event), read only from games whose box score stored them |
| The grade's "freshness" piece tops out at 0.9 because "there is no availability feed" | **Parked**: there is one now. Leave the cap until the injury board has a few weeks of record behind it |
| Confirmed starting lineups, referee assignments | **Not possible**: no feed we can reach publishes them |

## MLB (postseason now; the regular season is over)

| | Status |
|---|---|
| Why the profit calendar stopped at September | **Box run** (I, waiting on your paste) |
| Line movement's predictive value (`movecheck.py`) | **Parked**: movement adjusts the MLB grade today on a signal that has not been measured (MLB_MODEL #80). Spring is the time to measure it |
| Pitch-level reads: velocity drop, shelved pitch, arsenal vs a hitter's weakness by pitch type | **Parked**: built and journaled as evidence (`velo_delta`, `arsenal`); priced only when `stakecheck --info` says so |
| Alternate-line ladders | **Parked**: the odds feed carries MLB main lines; ladders cost credits |
| MLB's own expected stats, barrels, runs and steals, the park, every at-bat's video, his action photo on the hit page | **Built 2026-10-14** (step 84, AP); Savant's three files refresh every six hours and keep their last good copy (step 87, AR) |
| RBI, runs, hits + runs + RBI, walks, stolen bases | **Idea, for the winter** (H). All five are in the MLB game log the box already pulls every night (we keep five of its fields). Each costs odds credits and is measured before it is posted. MLB is down to the World Series, so they pay off next season |
| Sprint speed and catcher pop time (stolen bases), team defence (hits allowed), bat speed and squared-up rate (2024 on) | **Idea, for the winter** (H). Savant publishes all of them on the site we already read. Corrected 2026-10-14: this row said no free feed had defence or pop time |
| Travel and rest | **Idea, for the winter** (H): worked out from the schedule and ballparks we already hold; no new source |
| Public bet percentages | **Not possible**: no free feed, and scraping is off the table |

## UFC

| | Status |
|---|---|
| Where each fight's line opened and where it is now | **Built today** (step 56, P). The build has stored every book's price on every paid pull since 2026-08-10, and nothing read it. Every pick and pass card now says it, and which way it moved for the pick. Evidence only: the grade's movement piece stays empty until it is measured |
| Does our UFC number know anything the price does not? Did our picks beat the close? | **Box run** (P). The same information test and closing-line read the NFL record has had since August, on the UFC picks journaled since then |
| Method props (KO, submission, decision) at real prices | **Parked**: the odds feed carries only the moneyline for MMA. The card already shows our fair price for every method to shop by hand |
| Round props and "goes the distance" | **Built 2026-10-14** (step 76, AH): over and under 1.5 and 2.5 rounds and the round it ends in, off the finish times on file, as fair numbers to shop by hand (the odds feed carries only the moneyline) |
| Past voids that look like the midnight bug (a result saved before the bell read as a draw after midnight UTC) | **Built 2026-10-14** (step 90, AT), your call answered: a read-only list of every UFC void, each fight read again from ESPN, and what the ones that look like the bug would have graded. No grade changes |
| A Pick of the Day for the fight card | **Your call** (H). Every other league that names a pick now records it (steps 85 and 86); UFC has none, and its Record page has no section for one |
| Camp reports, referee assignments | **Not possible**: no structured source |

## Every sport

| | Status |
|---|---|
| Does each sport's number know anything the price does not? | **Box run** (P's second command, every sport in one go). The August test said: across the record, no (AUC 0.479 for our claimed edge). Re-running it per sport says where that is still true |
| A last look before kickoff: pull or flag a pick whose line moved a point against it | **Your call** (H), after L's read of the repaired closes |

---

The lettered blocks (M, N, O, P, and AG to AT since) are at the top of
`docs/WHEN_YOU_ARE_HOME.md`; the numbered steps (53 to 56, then 75 to
90) explain each, and block H holds every call and idea waiting on you.
