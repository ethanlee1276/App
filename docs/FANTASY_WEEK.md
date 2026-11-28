# This week in fantasy points

Ethan, 2026-10-22: *"with all this new data added for nfl with how we do
the offense and defense and game scripts and all the data from our game
reports. We need to make sure we are using that data correctly for
fantasy ... make sure we wrap that into it how it should be"*.

Before this, every league desk (the lineup, the head-to-head and the trade
finder, on Sleeper, ESPN and Yahoo) valued a player at his **season
average**. It never looked at the matchup, the game script, the weather or
who was out around him. A player on a bye was worth his average, so the
optimiser would start him.

The code is `engine/fantasyweek.py`. The NFL build writes
`fantasy_week.json` beside the board on every build (`nfl_build.py`), paid
in full (`gate.PAID_FILES`).

## What a player's week is made of

| Part | Where it comes from |
|---|---|
| Passing, rushing and receiving yards, catches, passing TDs, interceptions, kicking points | The prop board's own projection for each stat, the chain every pick is built on: form, his measured role, the defence against his position, the game script, the weather, his quarterback or a teammate out, team pace and pass rate, and the record's correction for him |
| Rushing and receiving touchdowns | The touchdown model (`pipeline.td_chances`), run over **every** skill player, not just the ones a book quotes. Calibrated exactly as the touchdown board is; where a book quotes him, pulled toward the book's price the same way |
| A part the board has no line for (a receiver's catches, a back's receiving) | His own season average in it. The card says which parts. Measured: see below |
| Whether he plays | Out, IR, PUP or suspended: zero. Questionable or doubtful: the practice report's measured chance (`engine/practice`), else nflverse's table: a questionable player played 64.6% of the time (51.8% after a week of no practice, 70.2% after a full one), a doubtful one 1.1%. His week counts at that chance, and the card shows both numbers |
| A bye | Zero |
| The range on the card | Where eight weeks in ten land: the measured 10th and 90th percentiles. Not a normal band, because fantasy points lean high |
| The spread under the head-to-head's win chance | Measured: how far weeks land from projections like these |
| Why | The chain steps that moved his number (who is out around him, the matchup, team tendency, weather, role), the matchup scan's read, and a role change |

## Who reads it

- **The league desk.** The lineup and the head-to-head are scored on this
  week, under your league's own scoring. Byes and players ruled out count
  as zero, and so does anyone Sleeper lists on IR, Out, PUP or suspended.
  A player the week's board doesn't carry stays on his season average, and
  the card says so. **Trades stay on season averages**, because a trade is
  a rest-of-season question. "Best pickups this week" is the best of the
  week that nobody in your league rosters.
- **The Fantasy page.** A new "This week" room comes first: every player,
  by position, with the matchup, the script, the chance he plays, the
  range, his touchdown chance and the reasons. Tap any name.
- **The player panel.** "This week" now shows his week off the board, and
  it stays on the full profile. Before this, the full profile replaced the
  card and the start/sit call disappeared.
- **Ask.** Start/sit and projected-points answers read the same week.

Guards:
- A week whose games are over isn't read: the desk falls back to season
  averages and says why until the next board is built.
- A head-to-head for a different week is scored on season averages.
- Non-members see the season-average desk with a note about what the week
  adds.

## Measured

`python3 fantasyweekfit.py` walks 2023–2025 forward, weeks 4–17. Each
week's slate is built from the weeks before it, priced, and added up the
same way, then scored against nflverse's own PPR on the same players
(10,445 player-weeks):

| | Start/sit pairs right: week / season avg | t | Miss a week: week / season avg |
|---|---:|---:|---:|
| QB | 61.1% / 61.0% | 0.2 | 6.37 / 6.40 |
| RB | 75.6% / 74.8% | 4.3 | 4.49 / 4.69 |
| WR | 71.0% / 70.0% | 5.4 | 5.02 / 5.20 |
| TE | 71.8% / 70.5% | 4.3 | 3.65 / 3.81 |
| All | **72.3% / 71.3%** | **3.9** | **4.66 / 4.83** |

Byes and players ruled out aren't in those numbers (a player who sat
scored neither way), and that's where a season-average lineup lost a whole
starter.

- **The fill** (season averages for the parts the board is silent on)
  took pairs from 72.1% to 72.3%, and cut a back's weekly shortfall from
  1.45 points to 0.74.
- **No level correction.** The projection runs a little under what players
  score (the board's numbers are medians). Shifting or scaling each
  position made the miss worse in all three held-out seasons, and moved
  flex calls by under 0.3 points.
- **Touchdowns.** Without the usage maps, backs scored 1.51× the
  touchdowns the model implied, tight ends 1.44× and quarterbacks 0.75×
  (rushing). The live model takes 70% of a player's share from his
  expected-points share, which that run couldn't see, so no scale is set
  in the code. The box's run replays the usage maps week by week, and it
  saves a position's scale only if it beat no scale on every held-out
  season.

## On the box

Measure with the box's own usage maps and save the result. It spends no
credits, takes about ten minutes and uses about 650 MB:

    cd /srv/qellys && sudo -u qellys nice -n 10 python3 fantasyweekfit.py --save 2>&1 | tail -70

After the next NFL build, check the week:

    cd /srv/qellys && sudo -u qellys python3 -c "from engine import fantasyweek as F; d=F.load(); print(F.summary_line(d)); print('week', d.get('week'), '· this week:', F.current(d), '· byes:', d.get('byes'))"
