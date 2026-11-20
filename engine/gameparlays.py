"""Each game's parlays: its two strongest picks together, two or three 3-leg parlays and three
2-leg touchdown parlays (2026-11-14; the two-leg tickets and the tickets' own bar, 2026-11-18;
two three-leg tickets on every game at least, 2026-11-19, THREELEG1).

Ethan, 2026-11-14, of the research reports they write for themselves ("Nabers 5+
receptions (max -250) + Skattebo 12+ rush attempts (max -200) + Daniels 25+
rush yds (max -250). Modeled joint hit rate is ~32-33% with mildly positive
correlation, so the fair price is ≈ +205. Bet only at +210 or better"):
"we need to make 3-leg or 2-leg same game parlays. Like, we do the parlay
things, but we throw like 8 legs in it and it's unrealistic ... We need to
be making 2-leg touchdown parlays for each games as well ... making sure no
legs have conflicts and backups". Then: "for each game, when it comes to
every sport, I want you to make 4 3-leg parlays ... do the same shit that
the report's doing. I want to make 4 3-leg parlays and 3 2-leg touchdown
parlays for each game."

WHAT HIS REPORTS DO, AND SO WHAT THIS DOES, game by game:

THE LEGS ARE THE REPORT'S OWN PICKS (GPLEGS1, 2026-11-17; `from_report`).
A game's three-leg tickets are rebuilt inside its report from the picks the
report shows and no other leg (Ethan: "how are we hitting so many picks
without winning any parlays, but we're still using those picks?"), each leg
the board's own number for that pick: the board's priced picks (the game's
Most Likely picks, its Edge picks, and every other prop it priced at a named
book: engine/twoleg's legs and `priced_legs`, each a real price, none
started, none held) narrowed to the report's, at LEG_FLOOR or better
(their reports' bar: "they sit under the 65% hit-rate floor, so they don't
qualify for the parlay"; ours is a little lower, and every leg shows its
own chance). Never a past-the-cap row (Ethan, 09-01: "not a parlay leg"),
never a man the board already dropped for an injury, and never a tackle,
sack or kicking prop (Ethan, 2026-11-14: "i dont wanna use tackle picks or
anything like that. and not kicker points either" — parlays.NO_PARLAY_MARKETS,
refused where every leg is made, twoleg._leg).

NO CONFLICTS. Every pair of legs passes the clash taxonomy
(engine/parlays.relate): no player twice, no quarterback against his own
receiver, no quarterback and a back of one team (they want opposite
scripts), no two teammates on one stat's pie (two unders share a ticket
otherwise: they want the same quiet game, PARLAYWIN1). And no leg that
needs points beside one that needs a quiet game (`script_need`, the
board's own game-script view, js/app.js
scriptNeed): a quarterback's yards and a touchdown want points. Two legs
that want opposite leads (a back's carries want his team ahead, a
receiver's catches want it chasing) share a ticket the way his own reports
pair them, priced as unrelated and said (OPPOSED_SCRIPT_RHO).
One exception their reports make and the doctrine does not: two teammates'
catches may share a ticket (the doctrine's "possession pie") at their
measured correlation, and the ticket says both need the same passing game.

THE CHANCE. All three legs hit, by the Gaussian copula the parlay screen
uses (parlays.joint_three) with each pair's correlation; beside it the
chance as if the legs were independent.

THE PRICE. A book prices a same-game parlay with its own correlation, which
no feed we buy carries, so a ticket says three things: our fair price
(1 / our chance), the legs' prices multiplied (what independent legs would
pay — a book pays less), and the least a book must pay for the ticket to
be worth it at our chance (TAKE_EDGE over fair: "bet only at +210 or
better").

THREE A GAME, THREE IDEAS. The likeliest first; each next one shares at most
MAX_SHARED leg with every ticket before it.

A BAR EVERY TICKET CLEARS (GPWIN1, 2026-11-18; `tickets_of`). Three picks
have to all hit: at the 68% the NBA's report picks hit, three together come in
about three times in ten, and a night's picks at 4 of 5 still lose every
ticket holding the one miss. A three-leg ticket is posted ahead of the fill
only when our own chance for it clears THREE_FLOOR. GPWIN1 also led each game
with its two strongest picks as a two-leg ticket (source `game_two`); Ethan
asked for three three-leg parlays and three scorer pairs a game and no others
on 20 November (ZR), and the two-leg tickets are retired (RETIRED).

BOTH SIDES OF THE GAME (2026-11-16). A ticket whose legs are all one club's
is taken only when it is clearly the stronger read than the best two-club
ticket that could take its place, and no more than ONE_SIDED_MAX of a
game's tickets are one club's while a two-club ticket is there. A game whose
other club has nothing good enough posts what it has, and every one-club
ticket says why it is one club's (`choose`).

BACKUPS AND CAVEATS. Each leg names the next-best leg that fits the other
two ("if Skattebo sits, Likely 4+ catches"); a ticket says what script it
needs and how likely the lines make it, and flags a leg listed
questionable.

THE TOUCHDOWN PAIRS. Two scorers from one game, from every quoted scorer
the touchdown model priced (`td_field`, engine/pipeline; college's own),
each at SCORER_FLOOR or better: one from each side (a shootout lifts both) or
two from one side (they share its touchdowns, priced at the measured
negative link). In football the scorers are chosen and the pairs ranked on
our research (`research`: the matchup, his usage, the breakout and
good-matchup reads, the game script), never on the prices alone (Ethan,
2026-11-14). Hockey's analog is two goal scorers; basketball has no
scorer market, and its games say so.

TRACKED, NEVER STAKED. The record (engine/twoleg's study): same-game pairs
lost 9.5% over 213 while two-game pairs made 11.1%; the books' same-game
cut has cost more than the link between two of our picks has paid. So every
ticket here is journaled and graded (engine/parlayledger, sources
`game_three` and `game_td`) with a stake of nothing until its own record
clears the parlay probation, and the card says so.

Standard library only. Never raises out of ``attach``.
"""
from __future__ import annotations

import datetime as dt
import itertools
import re

#: The leagues this runs for: every board with player props.
SPORTS = ("nfl", "cfb", "nba", "cbb", "wnba", "nhl", "mlb")
#: THREE THREE-LEG PLAYER-PROP PARLAYS AND THREE TWO-LEG SCORER PARLAYS A GAME
#: (ZR, 2026-11-20). Ethan: "i want 3 3 leg player prop parlays and 3 2 leg td
#: prop parlays", and "We should be making the 3 best parlays possible with the
#: data we have including the game report with the best possible props we
#: have". A game posts three of each wherever its props can make them: the
#: report's own picks first, then its game's best props (`tickets_of`, the
#: scorer pairs' fill in `build_game`), each leg the report did not pick named
#: on its card. The two-leg player-prop tickets (GPWIN1) are no longer built
#: (RETIRED): their record stays in the journal.
THREE_PER_GAME = 3
THREE_MIN = 3
SCORER_PER_GAME = 3
#: The ticket kinds no longer built (engine/parlayledger leaves them off the
#: record; the journal keeps every one).
RETIRED = ("two",)
#: The least chance a three-leg ticket must have by our own numbers to be
#: posted ahead of the fill: three picks at 63%. Under it a ticket is one we
#: expect to lose three times in four. It was 30% while a ticket's chance
#: carried the legs' link (`link_weight`, PARLAYWIN1): the same legs, said
#: without it.
THREE_FLOOR = 0.25
#: The least chance a 3-leg ticket's leg may have.
LEG_FLOOR = 0.60
#: The least chance a leg may have when it fills a game up to THREE_MIN, under
#: LEG_FLOOR (THREELEG2, 2026-11-19): the first builds after THREELEG1 left
#: games short (the NHL's twelve made 22 tickets, the NBA's four made 3),
#: because a game with three or four props at 60% has no two tickets that fit.
#: A leg under LEG_FLOOR rides only a filling ticket, and its card names it;
#: since PARLAYWIN1 it is one of the report's own picks (`from_report`).
FILL_LEG_FLOOR = 0.50
#: THE FILL'S ONE PROP FROM OUTSIDE THE REPORT (PARLAYWIN1, 2026-11-19). A prop
#: the report did not pick may fill a game's tickets at this chance or better,
#: and no ticket carries more than FILL_OUTSIDE_MAX of them: the tickets that
#: lost on the record carried two or three (16 November's NBA: "PP-", "-P-",
#: "--P"), and with none the NFL's Thursday game and college football's made
#: no three-leg ticket at all, their picks making no three that fit.
FILL_OTHER_FLOOR = 0.55
FILL_OUTSIDE_MAX = 1
#: The least chance by our numbers a ticket may have when it fills a game up to
#: THREE_MIN (`tickets_of`): a longer ticket, said so on its card, one we
#: expect to hit about one time in seven. Step YP lowered it to 12.5% (three
#: legs at FILL_LEG_FLOOR) for the NHL's two short games and college
#: basketball's one; the heartbeat then said what stopped them (conflicts: no
#: three of their props fit together at any chance), so the lower floor only
#: let longer tickets in, and it is 15% again (PARLAYWIN1).
LONG_FLOOR = 0.15
#: LONG_FLOOR as the notes say it ("15%").
LONG_WORDS = f"{LONG_FLOOR * 100:g}%"
#: The least chance a scorer leg may have, by league.
SCORER_FLOOR = {"nfl": 0.25, "cfb": 0.30, "nhl": 0.25}
#: THREE SCORER PAIRS A GAME (ZR, 2026-11-20; Ethan: "3 2 leg td prop
#: parlays"). A game whose research makes fewer than SCORER_PER_GAME pairs
#: fills them with its next scorers (`stand_ins`): in football a scorer with a
#: red-zone role and a weaker research case, then one under SCORER_FLOOR down
#: to this; in hockey one under SCORER_FLOOR down to this. A pair takes as few
#: of them as it can, and each is named on its card. Never a player the
#: matchup read says to avoid, or a football scorer with no red-zone role.
SCORER_FILL_FLOOR = {"nfl": 0.20, "cfb": 0.22, "nhl": 0.18}
#: How many legs of a game are tried (the likeliest), and scorers.
MAX_POOL, MAX_SCORERS = 14, 8
#: A ticket's least price is this much over our fair price: the edge a
#: ticket must leave at the book's price to be worth taking.
TAKE_EDGE = 0.05
#: Each next ticket of a game shares at most this many legs with every
#: ticket before it — and when that leaves fewer than a game's three, a
#: second pass lets a ticket differ from the others by one leg.
MAX_SHARED = 1
#: No leg rides on more than this many of a game's tickets.
MAX_USES = 2
#: BOTH SIDES OF THE GAME (Ethan, 2026-11-16, of the 49ers' game: "a lot of
#: these parlays we are making are very one sided as in a lot of picks for
#: both td and player props are for one team only and we need too fix that.
#: I understand if all the data points too one side so that's fine but we
#: just need to make sure"). Ranked on the chance alone, a game's likeliest
#: legs are usually one club's busiest players, and "built to win together"
#: (`choose`) keeps the next tickets on the same script, so a game's four
#: tickets could all be one club's when the other's were a point or two
#: behind. A one-club ticket is now taken only when it is SIDE_EDGE likelier
#: than the best two-club ticket that fits in its place (a scorer pair ranked
#: on its research: SIDE_RESEARCH more research points), and at most
#: ONE_SIDED_MAX of a game's tickets are one club's while a two-club ticket
#: fits. When none fits, the other club has nothing good enough here, and
#: the game posts what it has; each one-club ticket says which it was.
SIDE_EDGE = 0.04
SIDE_RESEARCH = 3
ONE_SIDED_MAX = 1
#: THE BAR, SET BY THE RECORD (Ethan, 2026-11-16, asked whether 4 points and 3
#: research points was the right bar: "idk whatever is best"). What is best is
#: what the record shows, so the record sets it: `fit_side_bar`, after each
#: settle pass (engine/maintenance), splits every settled game parlay into
#: one-club and two-club tickets by its legs' teams and compares how each hit
#: against the chance it was posted at. One-club tickets hitting below their
#: posted chance more than two-club ones do need a bigger edge to be taken;
#: hitting above it, a smaller one. The comparison is shrunk toward "no
#: difference" by SIDE_PRIOR_N tickets, it waits for SIDE_MIN_N of each kind
#: to settle (until then the bar is SIDE_EDGE and SIDE_RESEARCH), and the bar
#: never leaves SIDE_EDGE_RANGE / SIDE_RESEARCH_RANGE. ONE_SIDED_MAX stays.
SIDE_MIN_N = 30
SIDE_PRIOR_N = 60
SIDE_EDGE_RANGE = (0.02, 0.10)
SIDE_RESEARCH_RANGE = (2, 6)
SIDE_BAR_FILE = "side_bar.json"

#: THE LINK BETWEEN A TICKET'S LEGS, AS THE RECORD MEASURED IT (PARLAYWIN1,
#: 2026-11-19; Ethan: "if the three-leg parlays aren't working and aren't
#: making money, then we're not making good selections ... make those better").
#: A pair of legs we read as moving together (`pair_link`: one passing game
#: feeds both, a fast game lifts both) raised the ticket's chance. The record
#: of every ticket graded (parlayledger.calibration, 19 November) says they do
#: not: the 1,321 tickets priced with a positive link hit 382, against 443 the
#: link said and 407 the legs alone said, so the link took our number further
#: from the truth (z -3.7 with it, -1.5 without). A ticket's chance counts a
#: positive link at this weight: 0 until the record shows the legs we link hit
#: together more often than unrelated legs would (`fit_link_weight`, nightly).
#: A link that pulls the legs apart (opposite scripts) is always counted.
LINK_FILE = "gameparlays_link.json"
LINK_WEIGHT_DEFAULT = 0.0
#: Tickets priced with a positive link the fit waits for, and the prior it
#: shrinks the measured weight toward LINK_WEIGHT_DEFAULT with.
LINK_MIN_N, LINK_PRIOR_N = 200, 400
#: TWO TEAMMATES ON ONE TICKET, priced at the same-game floor for catches
#: and at none for touchdowns. The doctrine's possession-pie number
#: (parlays.MEASURED, −0.56) is a PARTIAL correlation: two receivers with
#: the team's passing yards held fixed. That is the right number for "which
#: of the two gets the yards" and the wrong one for "do both clear their
#: lines", which rides on the passing game too (raw, the same pairs move
#: +0.70 together). So the ticket is priced on the floor every same-game pair
#: of overs carries, and says both need the same passing game. Two scorers
#: of one team share its touchdowns and rise with them: priced as unrelated.
SAME_TEAM_CATCH_RHO = 0.10
SAME_TEAM_SCORER_RHO = 0.0
#: TWO LEGS THAT WANT OPPOSITE LEADS, priced instead of refused (2026-11-14).
#: A back's carries want his team ahead and a receiver's catches want it
#: chasing, so the first cut never put them on one ticket — and so refused
#: the ticket in Ethan's own report this docstring opens with: Nabers 5+
#: receptions with Skattebo 12+ rush attempts (two Giants) and Daniels 25+
#: rushing, "~32-33% with mildly positive correlation ... bet only at +210
#: or better". The rule left the NFL's first board under it with 13
#: three-leg tickets across 13 games, where they asked for four a game. The
#: script pulls the pair apart about as much as the shared pace ties it
#: together (the measured run-game script, +0.36 between a back's carries
#: and his team's lead, against the +0.10 every same-game pair of overs
#: carries), so it is priced as unrelated, never as linked, and the ticket
#: says the scripts pull apart. Not measured as a pair. A leg that needs
#: points beside one that needs a quiet game is still refused.
OPPOSED_SCRIPT_RHO = 0.0
#: A close game, for a ticket whose legs want opposite leads: within one
#: score either way.
CLOSE_GAME = {"nfl": 7.0, "cfb": 7.0}
#: The scoring markets, by league: what a "touchdown parlay" is in each.
SCORER_MARKETS = {"nfl": ("anytime_td",), "cfb": ("anytime_td",), "nhl": ("anytime_goal", "goals")}
#: The journal's books (engine/parlayledger `source`).
SOURCES = {"three": "game_three", "two": "game_two", "scorers": "game_td"}
#: What a league's scorer pair is called on its cards.
SCORER_WORDS = {"nfl": "touchdown", "cfb": "touchdown", "nhl": "goal scorer"}
#: Markets whose rows say their side "Yes" for an over.
_YES = ("YES", "Y")


# --- the legs ---------------------------------------------------------------------------
def _norm_side(leg: dict) -> dict:
    """A scorer's "Yes" read as the over the taxonomy expects."""
    if str(leg.get("side") or "").strip().upper() in _YES:
        leg = dict(leg, side="Over")
    return leg


#: Statuses that keep a man off every ticket.
_OUT = ("OUT", "DOUBTFUL", "IR", "SUSPENDED")


def priced_legs(board: dict, sport: str, now=None) -> list[dict]:
    """Every prop the board priced at a named book as a leg, at our own
    chance for its side, inside the Most Likely board's price cap.

    WHY (2026-11-14). The legs were the board's posted picks alone, Most
    Likely and Edge, and the first NFL board built that way, and again with
    the opposite-script pairs allowed (OPPOSED_SCRIPT_RHO), counted 13 and
    then 14 three-leg tickets across 13 games, where Ethan asked for four a
    game: about six posted picks a game clear LEG_FLOOR, and few trios of
    six pass the clash rules. Every other prop on the board carries our
    chance at a real price too (its prop card shows it), and his own
    tickets are built from exactly those: "Nabers 5+ receptions (max -250)
    + Skattebo 12+ rush attempts (max -200)". The Most Likely cap still
    holds (likely.HEAVIEST_PRICE, -250: past it a leg is "not a parlay
    leg", Ethan 09-01), as do the floor, a real book, the injury report and
    a game still to play."""
    from . import twoleg as T
    from .likely import HEAVIEST_PRICE
    from .stakeplan import priced_out
    out = []
    for r in board.get("recommendations") or []:
        if not isinstance(r, dict) or r.get("has_market") is False or r.get("_game_leg"):
            continue
        if str(r.get("book") or "").strip().lower() in ("", "proxy"):
            continue
        if str(r.get("injury_status") or "").strip().upper() in _OUT:
            continue
        try:
            if int(float(r.get("odds"))) < HEAVIEST_PRICE:
                continue                                # past the cap: never a parlay leg
        except (TypeError, ValueError):
            continue
        if priced_out("edge", r.get("odds")):
            continue                                    # the Edge book's long-price limit, as edge_legs
        if not credible_row(r):
            continue                                    # the Edge path's own refusal (`credible_row`)
        leg = T._leg(r, r.get("hit_prob"), "priced")
        if leg and not T._started(leg, now):
            out.append(leg)
    return out


def credible_row(r: dict) -> bool:
    """Would the Edge path stand behind this priced row's number?

    WHY FOOTBALL'S LEGS SAID 68% AND HIT 50% (Ethan, 2026-11-16: "go look
    into why footballs stated chances run 10 to 30 points too high"). On the
    record, 16 Nov: NFL legs hit 49.9% of the time against the 68.4% we
    stated (receptions 34% against 71%), college's 56.2% against 71.2%
    (passing yards 31% against 76%). Yet the Most Likely picks those legs are
    meant to be, in the same 60-75% band, hit what they said (NFL 65.7%
    stated, 65.9% hit, 1,259 picks).

    The difference was this source. Every priced prop joined the leg pool on
    14 November, at its tempered chance, `hit_prob`, which the Edge path pulls
    halfway to the book's fair price (betting.temper_edge). For a main line
    near even money to show 60%, the raw model must say 70% or more against a
    book at about 52%: twenty points apart, where the Edge path's own rule
    (MAX_CREDIBLE_EDGE, ten points) calls the number "a data error, not
    alpha" and refuses the pick. The board kept the row, at its 60-75%, and
    the parlays took it as a leg. Our number beat the line on fewer than half
    of football's props (receptions 47%, college passing yards 42%), so a
    leg twenty points off the market was our error nearly every time.

    The same test the Edge path applies, on the row it applied it to: no
    refusal among its reasons (betting.REFUSAL_REASONS), and the raw read
    within MAX_CREDIBLE_EDGE of the fair price where the row carries both."""
    from .betting import MAX_CREDIBLE_EDGE, REFUSAL_REASONS
    for reason in r.get("reasons") or []:
        if any(str(reason).startswith(x[:40]) for x in REFUSAL_REASONS):
            return False
    raw, fair = r.get("raw_prob"), r.get("fair_prob")
    if raw in (None, "", 0, 0.0) or fair in (None, ""):
        return True
    try:
        return abs(float(raw) - float(fair)) <= MAX_CREDIBLE_EDGE
    except (TypeError, ValueError):
        return False


#: WHICH COPY OF A LEG SPEAKS for it when two sources price the same bet:
#: the Most Likely board's (its 60-75% claims hit what they said on the
#: record), then the Edge picks', then any other priced prop's. The higher
#: number used to win, and the higher of two estimates of one bet is the
#: one more likely to be wrong upward.
SOURCE_RANK = {"likely": 0, "edge": 1, "priced": 2}


def _speaks_first(leg: dict, held: dict) -> bool:
    a, b = SOURCE_RANK.get(leg.get("pool"), 9), SOURCE_RANK.get(held.get("pool"), 9)
    return a < b or (a == b and float(leg["p"]) > float(held["p"]))


def pool_legs(board: dict, sport: str, now=None) -> list[dict]:
    """The Most Likely rows the board's seat caps dropped, as legs.

    WHY (2026-11-14). With every priced prop's posted number in the pool
    (`priced_legs`) the NFL board counted 28 three-leg tickets across 13
    games: a posted number is mostly a main line at about -110, where our
    tempered chance rarely reaches LEG_FLOOR. Ethan's legs are a prop's
    likeliest number on its alternate ladder ("Nabers 5+ receptions (max
    -250)"), which is exactly what the Most Likely board computes for every
    prop it ranks (likely.rungs, held to its floor, its -250 cap and its
    credibility bar) and then seats eight a market. The rest ride on the
    board for the Pick of the Day (`potd.POOL_KEY`) until `potd.attach`
    takes them; read here, they cost nothing more to price."""
    from . import twoleg as T
    from .potd import POOL_KEY
    out = []
    for r in board.get(POOL_KEY) or []:
        if not isinstance(r, dict) or r.get("bettable") is False or r.get("_game_leg"):
            continue
        if str(r.get("injury_status") or "").strip().upper() in _OUT:
            continue
        leg = T._leg(r, r.get("model_prob"), "likely")
        if leg and not T._started(leg, now):
            out.append(leg)
    return out


def game_started(g: dict, now=None) -> bool:
    """A game of the board's own list under way or over: its live block (or
    flag) says so, or its own kickoff by the clock (rules.clock_says_started)."""
    from .rules import clock_says_started
    g = g if isinstance(g, dict) else {}
    live = g.get("live")
    state = str(live.get("state") or "") if isinstance(live, dict) else ("live" if live is True else "")
    if state in ("live", "final") or g.get("final") is True or g.get("started") is True:
        return True
    return clock_says_started(g.get("date") or "", g.get("kickoff") or g.get("commence_time") or "", now=now)


def still_to_play(legs: list, board: dict, now=None) -> list:
    """THE BOARD'S OWN GAMES SAY WHICH LEGS ARE STILL TO PLAY (GPWIN2,
    2026-11-18). Each source drops a leg by the kickoff on its row
    (engine/twoleg `_started`), and a row with no kickoff never starts:
    hockey's rows carried none, so a started game's tickets were built again
    from its pre-game legs and journaled as versions (Tuesday's 7 pm games
    have two-leg tickets the board only began making at 8:17 pm Eastern).
    The board's games list carries every game's kickoff and live state, as
    the singles journal reads it (engine/ledger._kickoff_map), so a leg of a
    game it says has started is no leg, whatever its row says."""
    games = [g for g in (board or {}).get("games") or [] if isinstance(g, dict)]
    if not games:
        return list(legs or [])
    out = []
    for leg in legs or []:
        # A doubleheader is two games of one pair: the leg stands while either
        # is still to play, and its own row's kickoff tells game one's apart.
        mine = _games_of(leg, games)
        if mine and all(game_started(g, now) for g in mine):
            continue
        out.append(leg)
    return out


def legs_for(board: dict, sport: str, now=None, floor: float = LEG_FLOOR) -> list[dict]:
    """The board's priced picks as legs — Most Likely, Edge, the Most Likely
    rows its seat caps dropped (`pool_legs`) and every other prop it priced
    at a named book whose number the Edge path stands behind (`priced_legs`,
    `credible_row`), one copy of a pick kept, the most trusted source's
    (`SOURCE_RANK`) — at ``floor`` or better (LEG_FLOOR; FILL_LEG_FLOOR for
    the legs a game's fill may take), of a game still to play
    (`still_to_play`)."""
    from . import legfit
    from . import twoleg as T
    from .stakeplan import market_benched
    got: dict = {}
    # THE LEAGUE'S LEARNED CORRECTION (engine/legfit, 2026-11-16; Ethan:
    # "yes"): each leg's chance pulled toward the book's by the share its
    # league's record supports, before the floor, so a leg that only cleared
    # it on an overstated number is no leg. 0 until the record has spoken.
    # FOOTCAL2 (2026-11-17; Ethan: "recalibrate football too"): and moved by
    # the shift its legs built the current way have earned, where the books
    # agreed with an overstated number and the pull alone could not move it.
    w, shift = legfit.w_for(sport, "three"), legfit.shift_for(sport, "three")
    for get in (T.likely_legs, T.edge_legs, pool_legs, priced_legs):
        try:
            rows = get(board, sport, now)
        except Exception:                                    # noqa: BLE001
            rows = []
        for leg in rows:
            if leg:
                # Its market's own shift rides on top (legfit._market_fits, GPWIN1).
                leg = legfit.apply(leg, sport, "three", w, shift)
            # Player props only: a game line's leg journals and grades on
            # another path, and their reports' tickets are props.
            if not leg or leg.get("_game_leg") or float(leg.get("p") or 0) < floor:
                continue
            leg = _norm_side(leg)
            # A MARKET BENCHED FOR LOSING MONEY IS NO PARLAY LEG (PARLAYWIN1;
            # stakeplan.MARKET_BENCH: the NFL's quarterback completions and the
            # NBA's points, benched 18 November at 44-53 and 63-71): a bet the
            # record will not stake is no leg to stake a ticket on.
            if market_benched(sport, leg.get("market")):
                continue
            k = (leg.get("player"), leg.get("market"), str(leg.get("side") or "").upper(), leg.get("line"))
            if k not in got or _speaks_first(leg, got[k]):
                got[k] = leg
    return still_to_play(list(got.values()), board, now)


def scorer_legs(board: dict, sport: str, now=None, floor: float | None = None) -> list[dict]:
    """Every priced scorer of the slate as a leg: the touchdown model's
    whole field (`td_field`), college's, or hockey's goal props — each at
    ``floor`` or better (the league's SCORER_FLOOR unless given), still to play."""
    from . import twoleg as T
    markets = SCORER_MARKETS.get(sport) or ()
    if not markets:
        return []
    floor = SCORER_FLOOR.get(sport, 0.25) if floor is None else float(floor)
    from . import legfit
    w, shift = legfit.w_for(sport, "scorers"), legfit.shift_for(sport, "scorers")   # as legs_for's
    seen, out = set(), []
    rows = list(board.get("td_field") or []) + list(board.get("longshot_watch") or []) \
        + [r for r in board.get("most_likely") or [] if r.get("market") in markets] \
        + [r for r in board.get("recommendations") or [] if r.get("market") in markets]
    for r in rows:
        if not isinstance(r, dict) or r.get("market") not in markets:
            continue
        if str(r.get("injury_status") or "").upper() in ("OUT", "DOUBTFUL", "IR"):
            continue
        p = r.get("model_prob") if r.get("model_prob") is not None else r.get("hit_prob")
        leg = T._leg(dict(r, side=r.get("side") or "Over", line=r.get("line") if r.get("line") is not None else 0.5),
                     p, "scorer")
        if leg:
            leg = legfit.apply(leg, sport, "scorers", w, shift)
        if not leg or leg["p"] < floor:
            continue
        leg = _norm_side(leg)
        if str(leg.get("side") or "").upper().startswith("U"):
            continue
        if not leg.get("game_date"):
            leg["game_date"] = r.get("game_date") or board.get("date") or ""
        k = (leg["player"], leg["market"])
        if k in seen or T._started(leg, now):
            continue
        seen.add(k)
        out.append(leg)
    return still_to_play(out, board, now)


# --- the touchdown pairs' research ------------------------------------------------------------
#: TOUCHDOWN PAIRS FROM OUR RESEARCH, NOT THE PRICES (2026-11-14). Ethan:
#: "make sure we are making the TD parlays based off reaseerach we do and the
#: breakout canidates and game scripts and all of that and not just based off
#: the player lines". The pairs were the game's likeliest priced scorers,
#: paired by their joint chance — the touchdown model's number, which leans
#: on the points the lines expect and the share the player already has, so
#: the pairs read like the shortest prices on the board. Now each football
#: scorer is first read on the research the site already writes (the case
#: their own words make: "where the lions do bad and bills do good ... figure
#: out ... could have breakout games and get tds"):
#:
#:   the matchup   engine/matchpicks.td_matchup, the one the matchup picks and
#:                 the one Most Likely board's scorer check read: his team's
#:                 expected points, the defence at his position (the run
#:                 defence for a back or a quarterback), his expected
#:                 red-zone chances and red-zone trips both ways, 0–8;
#:   his usage     his share of the targets or the carries, 0–2 (the
#:                 touchdown scenarios' bars, engine/tdscenarios);
#:   the read      the matchup scan's verdict on him — a breakout candidate
#:                 +2, a good matchup +1, a tough one −1, and a player the
#:                 scan says to avoid is never a leg;
#:   the script    the spread: a back on a side favoured by SCRIPT_FAVORITE
#:                 or more +1 (a leading team runs, at the goal line too),
#:                 on a side that trails by SCRIPT_BIG_DOG or more −1; a
#:                 receiver or tight end in a shootout by the total +1.
#:
#: A scorer is a leg only with a red-zone role (RED_ZONE_CHANCES' "ok" bar —
#: Zay Flowers on the scenario shelf: "it says 0.0 redzone chances expected
#: yet we display this pick") and RESEARCH_MIN of the 13 points; scorers and
#: pairs are ranked on the research first and our chance second. The chance
#: a pair shows is still the model's and the copula's, unmoved: the record
#: has not shown a soft defence adding to a receiver's touchdown chance past
#: the game total (engine/tdmatchfit), so the research CHOOSES the pairs and
#: the journal (`game_td`) says how they do. Hockey's goal-scorer pairs have
#: no scan read and are ranked on the chance as before.
RESEARCH_SPORTS = ("nfl", "cfb")
RESEARCH_MIN = 4
RESEARCH_MAX = 13
READ_POINTS = {"breakout": 2, "good": 1, "neutral": 0, "tough": -1}
SCRIPT_FAVORITE = 3.0
SCRIPT_BIG_DOG = 7.0
#: The reasons a researched scorer leg shows: the case (the read, the
#: defence, the script), then his own (`why_lines`), then the rest.
RESEARCH_WHY = 5


def _f(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _margin(team: str, game: dict | None):
    """The points the lines expect ``team`` to win by (negative: lose by),
    off the game's home spread."""
    sp = _f((game or {}).get("spread"))
    if sp is None or not team:
        return None
    if team == (game or {}).get("home"):
        return -sp
    if team == (game or {}).get("away"):
        return sp
    return None


def research(leg: dict, read: dict | None, game: dict | None, sport: str) -> dict | None:
    """{"score", "points", "head", "tail", "red_zone"} — our research case
    for one football scorer, out of RESEARCH_MAX, with its lines (``head``
    the case, ``tail`` the rest) — or None when there is none: no matchup
    read on him, a read that says to avoid him, or a position the readings
    do not cover."""
    from .matchpicks import td_matchup
    from .tdscenarios import TARGET_SHARE, CARRY_SHARE, _pts
    if not read or read.get("read") == "avoid":
        return None
    pos = str(read.get("pos") or read.get("position") or leg.get("position") or "").upper()
    if pos not in ("QB", "RB", "FB", "WR", "TE"):
        return None
    td = read.get("td") or {}
    team = leg.get("team") or read.get("team") or ""
    opp = leg.get("opponent") or read.get("opp") or ""
    scan = (game or {}).get("scan") or {}
    units, rz = scan.get("units") or {}, scan.get("redzone") or {}
    u = read.get("usage") or {}
    row = {"position": pos, "team": team, "opponent": opp,
           "implied_total": td.get("implied_total") if td.get("implied_total") is not None
           else leg.get("implied_total"),
           "rz_chances": td.get("rz_chances") if td.get("rz_chances") is not None else leg.get("rz_chances")}
    m = td_matchup(row, units.get(opp), rz.get(team), rz.get(opp), int(scan.get("n_teams") or 32), u)
    pts = dict(m["points"])
    lines = []
    label = str(read.get("label") or "").strip()
    rp = READ_POINTS.get(str(read.get("read") or ""), 0)
    # A TOUGH DRAW FOR YARDS IS NOT ONE FOR TOUCHDOWNS when he is his team's
    # go-to scorer (engine/readlogic, rule 3: "Tough for yards — still the
    # go-to scorer").
    if rp < 0 and ((read.get("scoring") or {}).get("go_to")):
        rp = 0
    if label and rp > 0:
        lines.append(label)
    if pos in ("WR", "TE"):
        pts["usage"] = _pts(_f(u.get("tgt_share")), TARGET_SHARE)
    elif pos in ("RB", "FB"):
        pts["usage"] = _pts(_f(u.get("carry_share")), CARRY_SHARE)
    else:
        pts["usage"] = 0                           # a quarterback's share is not his touchdown case
    pts["read"] = rp
    # THE SCRIPT, off the spread and the total.
    script, why = 0, ""
    margin = _margin(team, game)
    total = _f((game or {}).get("total"))
    if pos in ("RB", "FB") and margin is not None:
        if margin >= SCRIPT_FAVORITE:
            script, why = 1, (f"{team} favored by {margin:g} — a leading team runs the ball, at the goal "
                              f"line too")
        elif margin <= -SCRIPT_BIG_DOG:
            script, why = -1, f"{team} a {abs(margin):g}-point underdog — a trailing team runs less"
    elif pos in ("WR", "TE") and total is not None and total >= HIGH_TOTAL.get(sport, 47.0):
        script, why = 1, f"a {total:g}-point total — a shootout, and both sides throw to score"
    pts["script"] = script
    score = sum(pts.values())
    # THE LINES, the case first: the read, the defence and the script — what
    # the touchdown model's own reasons never say — then the rest of the
    # matchup (his red-zone chances, his share, the points the lines expect,
    # the trips), which the leg's own reasons may already carry.
    mine = list(m.get("lines") or [])
    lines += [x for x in mine if "defense ranks" in x]
    if why:
        lines.append(why)
    tail = [x for x in mine if "red-zone chances" in x]
    tail += [x for x in mine if x not in lines and x not in tail]
    return {"score": int(score), "points": pts, "head": lines, "tail": tail,
            "red_zone": pts.get("red_zone", 0)}


def research_scorers(scorers: list[dict], board: dict, games: list, sport: str,
                     census: dict | None = None) -> tuple[list, int]:
    """The scorers our research makes a case for, each with its ``research``
    stamped and its research lines first in ``why`` — and how many priced
    scorers it read. Hockey (no scan read) passes through unread.
    ``census`` is filled with why each one turned away was (the picks audit
    prints it: engine/pickaudit)."""
    if sport not in RESEARCH_SPORTS:
        return scorers, len(scorers)
    reads = reads_by_player(board)
    out = []

    def no(why):
        if census is not None:
            census[why] = census.get(why, 0) + 1
    for leg in scorers:
        read = reads.get((_key(leg.get("player")), leg.get("team") or ""))
        r = research(leg, read, _game_of(leg, games), sport)
        if not r:
            no("no matchup read on the player" if not read else "the read says avoid" if read.get("read") == "avoid"
               else "a position the readings do not cover")
            continue
        if not r["red_zone"]:
            no("no red-zone role (under 0.9 expected red-zone chances)")
            continue
        if r["score"] < RESEARCH_MIN:
            no(f"under {RESEARCH_MIN} of the {RESEARCH_MAX} research points")
            continue
        leg["research"] = r["score"]
        leg["research_of"] = RESEARCH_MAX
        leg["research_points"] = r["points"]
        old = [str(x) for x in leg.get("why") or []]
        # His red-zone work said once: the model's own line ("Red-zone touch
        # share ~38% (3.1 expected chances)") or the matchup's.
        has_rz = any(x.startswith(("Red-zone", "Goal-line")) for x in old)
        why: list = []
        for x in r["head"] + old + [t for t in r["tail"] if not (has_rz and "red-zone chances" in t)]:
            if x and x not in why:
                why.append(x)
        leg["why"] = why[:RESEARCH_WHY]
        out.append(leg)
    return out, len(scorers)


def _by_research(t: dict) -> tuple:
    """A scorer pair's rank: its research, then our chance it hits."""
    return (-sum(int(l.get("research") or 0) for l in t["legs"]), -t["joint"],
            -(t.get("ev_at_naive") or -9))


def scorer_rank(researched: bool):
    """A scorer pair's rank: the fewest stand-in scorers first (`stand_ins`),
    then its research (football) or our chance (hockey)."""
    if researched:
        return lambda t: (int(t.get("stand_ins") or 0),) + _by_research(t)
    return lambda t: (int(t.get("stand_ins") or 0), -t["joint"], -(t.get("ev_at_naive") or -9))


def stand_ins(priced: list[dict], chosen: list[dict], board: dict, games: list, sport: str) -> list[dict]:
    """The scorers a game's pairs may fill with (SCORER_FILL_FLOOR), each with
    why on its leg (``stand_in``): in football a priced scorer the research
    turned away only for its points ("weaker"), or one under SCORER_FLOOR with
    a red-zone role and a research case ("longer"); in hockey one under
    SCORER_FLOOR ("longer"). ``chosen`` are the scorers the research took."""
    floor = SCORER_FLOOR.get(sport, 0.25)
    took = {_leg_id(l) for l in chosen}
    reads = reads_by_player(board) if sport in RESEARCH_SPORTS else {}
    out = []
    for leg in priced:
        if _leg_id(leg) in took:
            continue
        short = float(leg.get("p") or 0) < floor
        if sport in RESEARCH_SPORTS:
            read = reads.get((_key(leg.get("player")), leg.get("team") or ""))
            r = research(leg, read, _game_of(leg, games), sport)
            if not r or not r["red_zone"]:
                continue
            if not short and r["score"] >= RESEARCH_MIN:
                continue                               # the research's own: a scorer it took
            leg["research"], leg["research_of"], leg["research_points"] = r["score"], RESEARCH_MAX, r["points"]
            why: list = []
            for x in r["head"] + [str(y) for y in leg.get("why") or []] + r["tail"]:
                if x and x not in why:
                    why.append(x)
            leg["why"] = why[:RESEARCH_WHY]
        elif not short:
            continue
        leg["stand_in"] = "longer" if short else "weaker"
        out.append(leg)
    return out


def _stand_in_caveat(leg: dict, sport: str) -> str:
    """What a pair says of a scorer it filled with (`stand_ins`)."""
    words = f"{SCORER_PER_GAME} {SCORER_WORDS.get(sport, 'scorer')} pairs"
    if leg.get("stand_in") == "weaker":
        return (f"{leg.get('player')} has a weaker research case ({int(leg.get('research') or 0)} of "
                f"{RESEARCH_MAX} points, under the {RESEARCH_MIN} a pair is built from): added so the game has {words}")
    return (f"{leg.get('player')} is a longer shot ({float(leg.get('p') or 0):.0%}, under the "
            f"{SCORER_FLOOR.get(sport, 0.25):.0%} a pair is built from): added so the game has {words}")


# --- why each leg: the read, the model's own reasons ------------------------------------------
#: The touchdown model's footnotes about its own mechanics — true, and
#: nothing a reader weighs a leg on (engine/touchdowns.td_probability).
_FOOTNOTES = ("Running back:", "Team total:", "Quarterback:", "Depth receiver:", "Share of team TDs from",
              "Scout: ", "Usage is ",
              # The projection's arithmetic (engine/projection), not a reason
              # a reader weighs (Ethan's screenshot, 2026-11-15).
              "Usage bridge:")
#: The reasons a leg shows.
WHY_N = 3


def _key(name) -> str:
    return " ".join(str(name or "").lower().replace(".", "").split())


def reads_by_player(board: dict) -> dict:
    """{(player key, team): read} from every game's scan reads."""
    out: dict = {}
    for game in ((board or {}).get("scan_reads") or {}).values():
        for x in (game or {}).get("players") or []:
            if isinstance(x, dict) and x.get("player"):
                out[(_key(x["player"]), x.get("team") or "")] = x
    return out


def rows_by_pick(board: dict) -> dict:
    """{(player key, market, SIDE, line): the board row} — Most Likely,
    Edge and every scorer — so a leg can say the reasons its own row says."""
    out: dict = {}
    for k in ("most_likely", "recommendations", "td_field", "longshot_watch"):
        for r in (board or {}).get(k) or []:
            if not isinstance(r, dict) or not r.get("player"):
                continue
            side = str(r.get("side") or "Over").strip().upper()
            side = "OVER" if side in _YES else side
            line = r.get("line") if r.get("line") is not None else 0.5
            out.setdefault((_key(r["player"]), r.get("market"), side, line), r)
    return out


def why_lines(leg: dict, row: dict | None, read: dict | None, n: int = WHY_N) -> list[str]:
    """Why this leg, best first: for a scorer, his red-zone and goal-line
    work, what the defence gives up to his position, the weather and the
    points his team is expected to score (Ethan's touchdown reads: "the
    Commanders ... one of the worst in the league against guarding tight
    ends ... a rainy game and they were probably going to run more ...
    he's a good red zone usage"); for any other leg, the matchup read's
    reasons on the leg's side, then the model's own."""
    up = not str(leg.get("side") or "").strip().upper().startswith(("U", "NO"))
    from .refusals import is_refusal
    # A gate's refusal of the Edge pick is no reason for the leg (engine/refusals).
    reasons = [str(x) for x in (row or {}).get("reasons") or [] if x
               and not any(str(x).startswith(f) for f in _FOOTNOTES) and not is_refusal(x)]
    said: list = []
    scorer = leg.get("market") in ("anytime_td", "anytime_goal", "goals")
    if scorer:
        said += [x for x in reasons if x.startswith(("Goal-line work", "Red-zone"))]
        if read:
            said += [str(x) for x in (read.get("notes") or []) + (read.get("pro") or [])
                     if "touchdowns to" in str(x)]
            said += [str(x) for x in read.get("pro") or [] if "rain" in str(x).lower() or "snow" in str(x).lower()]
        said += [x for x in reasons if not x.startswith(("Goal-line work", "Red-zone", "Team implied"))]
        said += [x for x in reasons if x.startswith("Team implied")]
    else:
        if read:
            said += [str(x) for x in ((read.get("pro") if up else read.get("con")) or [])]
        said += reasons
    out, seen = [], set()
    for x in said:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
        if len(out) >= n:
            break
    return out


def enrich(legs: list[dict], board: dict) -> list[dict]:
    """Each leg with its reasons (``why``) and its listing, off the board's
    own rows and reads."""
    rows, reads = rows_by_pick(board), reads_by_player(board)
    for leg in legs:
        side = str(leg.get("side") or "").strip().upper()
        row = rows.get((_key(leg.get("player")), leg.get("market"), "OVER" if side in _YES else side,
                        leg.get("line") if leg.get("line") is not None else 0.5))
        read = reads.get((_key(leg.get("player")), leg.get("team") or ""))
        leg["why"] = why_lines(leg, row, read)
        st = (row or {}).get("injury_status") or (read or {}).get("own_status") or ""
        if st:
            leg["injury_status"] = str(st).upper()
        # The player's face, where the board has one: a ticket's card draws it beside the leg (js/report.js).
        face = (row or {}).get("headshot") or (read or {}).get("headshot") or ""
        if face:
            leg["headshot"] = str(face)
    return legs


def _games_of(leg: dict, games: list) -> list:
    """Every game of the leg's pair (two on a doubleheader)."""
    pair = {leg.get("home"), leg.get("away")} - {"", None} or {leg.get("team"), leg.get("opponent")} - {"", None}
    return [g for g in games or [] if isinstance(g, dict) and {g.get("home"), g.get("away")} == pair]


def _game_of(leg: dict, games: list) -> dict | None:
    mine = _games_of(leg, games)
    return mine[0] if mine else None


# --- the game script (js/app.js scriptNeed, the board's own view) --------------------------
_RUSH = ("rush_yds", "rush_att", "carries", "rush_attempts", "rush_rec_yds")
_CATCH = ("receptions", "rec_yds", "targets")
_PASS = ("pass_yds", "pass_att", "pass_cmp", "completions", "pass_td", "pass_tds", "pass_rush_yds")
_TD = ("anytime_td", "first_td", "anytime_scorer")
_K = ("strikeouts", "pitcher_strikeouts")
_OUTS = ("outs", "pitching_outs")
_BAT = ("hits", "total_bases", "home_runs", "runs", "rbi", "rbis", "hits_runs_rbis", "singles", "doubles")
_HOOP = ("pts", "points", "reb", "rebounds", "ast", "assists", "fg3m", "threes", "pra",
         "pts_reb_ast", "pts_reb", "pts_ast", "reb_ast")


def script_need(leg: dict, game: dict | None) -> dict:
    """What a leg needs from the game: ``margin`` +1 the home side ahead,
    −1 the away side; ``points`` +1 a high-scoring game, −1 a low one; 0
    no lean — and why, in words. The page's game-script view
    (js/app.js scriptNeed) in Python, so a ticket never carries two legs
    the board itself would call a clash. One reading of ours: a
    quarterback's rushing yards lean nowhere — he scrambles when his team
    trails and when he is blitzed (Ethan's reports: "Daniels' rushing holds
    in A, B and C")."""
    out = {"margin": 0, "points": 0, "why_margin": "", "why_points": ""}
    if not game:
        return out
    mkt = str(leg.get("market") or "").lower()
    up = not str(leg.get("side") or "").strip().upper().startswith(("U", "NO"))
    team = leg.get("team") or ""
    t = 1 if team == game.get("home") else -1 if team == game.get("away") else 0
    s = 1 if up else -1

    def put(axis, d, why):
        if d:
            out[axis] = 1 if d > 0 else -1
            out["why_" + axis] = why
    if leg.get("_game_leg"):
        if mkt in ("moneyline", "spread", "run_line", "puck_line", "ml"):
            put("margin", t, f"{team} winning")
        elif "total" in mkt and "team_total" not in mkt:
            put("points", s, "points on the board" if up else "a low-scoring game")
        return out
    if mkt in _RUSH and str(leg.get("position") or "").upper() == "QB":
        return out
    if mkt in _RUSH:
        put("margin", s * t, f"{team} ahead — leading teams run" if up else f"{team} not ahead")
    elif mkt in _CATCH:
        put("margin", -s * t, f"{team} chasing or trading scores — teams throw when behind" if up
            else f"{team} ahead — a leading team throws less late")
    elif mkt in _PASS:
        put("points", s, "points — a quarterback's yards rise with the team's score" if up
            else "a low-scoring game for the team")
    elif mkt in _TD:
        put("points", s, "points — a touchdown is points" if up else "a low-scoring game")
    elif mkt in _K:
        put("points", -s, "a quiet night for the other lineup" if up else "the other lineup hitting")
    elif mkt in _OUTS:
        put("margin", s * t, f"{team} ahead — a winning starter stays in" if up else f"{team} behind")
    elif mkt in _BAT:
        put("points", s, "runs — bats move with the scoring" if up else "a low-scoring game")
    elif mkt in _HOOP:
        put("points", s, "a fast, high-scoring game" if up else "a slow, low-scoring game")
    return out


def _phi(z: float) -> float:
    import math
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


#: The spread of outcomes the board's script view reads (engine/gamebets).
SCRIPT_SD = 13.5
#: A high-scoring football game, by league (the page's GS_HIGH_TOTAL and college's).
HIGH_TOTAL = {"nfl": 47.0, "cfb": 56.0}


def script_words(needs: list[dict], game: dict | None, sport: str) -> tuple[str, float | None]:
    """(the script a ticket's legs share in words, how likely the lines
    make it — football only, else None)."""
    if not game:
        return "", None
    leads = {n["margin"] for n in needs if n["margin"]}
    mixed = len(leads) > 1                 # two legs want opposite leads (OPPOSED_SCRIPT_RHO)
    m = 0 if mixed else next(iter(leads), 0)
    p = next((n["points"] for n in needs if n["points"]), 0)
    home, away = game.get("home") or "", game.get("away") or ""
    bits = []
    if mixed:
        bits.append("a close game — its legs want opposite leads")
    elif m:
        bits.append(f"{home if m > 0 else away} ahead")
    if p:
        bits.append("a high-scoring game" if p > 0 else "a low-scoring game")
    said = " and ".join(bits) if bits else "any script — none of the legs leans on how the game goes"
    chance = None
    try:
        spread, total = float(game.get("spread")), float(game.get("total"))
    except (TypeError, ValueError):
        spread = total = None
    if sport in HIGH_TOTAL and spread is not None and total is not None and (m or p or mixed):
        mean = -spread                                      # the home margin the line expects
        c_m = (_phi(mean / SCRIPT_SD) if m > 0 else 1.0 - _phi(mean / SCRIPT_SD)) if m else 1.0
        if mixed:
            close = CLOSE_GAME.get(sport, 7.0)
            c_m = _phi((close - mean) / SCRIPT_SD) - _phi((-close - mean) / SCRIPT_SD)
        hi = 1.0 - _phi((HIGH_TOTAL[sport] - total) / SCRIPT_SD)
        c_p = (hi if p > 0 else 1.0 - hi) if p else 1.0
        chance = round(c_m * c_p, 3)
    return said, chance


# --- one ticket -------------------------------------------------------------------------------
def _dec(odds) -> float | None:
    from .twoleg import _dec as d
    return d(odds)


def pair_link(sport: str, a: dict, b: dict, game: dict | None) -> tuple:
    """(fits, correlation, why, caveat) for two legs of one ticket."""
    from . import parlays as P
    from .twoleg import plain
    if (a.get("player") or "_a") == (b.get("player") or "_b"):
        return False, 0.0, "the same player twice — if that player sits, both legs die", ""
    try:
        rel = P.relate(sport, a, b)
    except Exception:                                        # noqa: BLE001
        return False, 0.0, "the pair could not be read", ""
    caveat = ""
    rho = float(rel.rho)
    why = plain(rel.mechanism)
    if rel.verdict in ("kill", "duplicate"):
        # The two exceptions below are for two teammates' OVERS; two teammates
        # under on one pie stay apart (parlays.relate_prior, PARLAYWIN1).
        same_team = ((a.get("team") or "_a") == (b.get("team") or "_b")
                     and P._side_up(a) and P._side_up(b))
        fam = {P._family(a), P._family(b)}
        if rel.clash == 3 and same_team and fam == {"catch"}:
            caveat = (f"{a.get('player')} and {b.get('player')} both need {a.get('team')}'s passing game — "
                      f"one big day can take the other's catches")
            rho, why = SAME_TEAM_CATCH_RHO, "one passing game feeds both"
        elif rel.clash == 3 and same_team and fam <= {"td", "nhlgoal"}:
            caveat = (f"{a.get('player')} and {b.get('player')} share {a.get('team')}'s scoring — "
                      f"both need {a.get('team')} to score more than once")
            rho, why = SAME_TEAM_SCORER_RHO, ""
        else:
            return False, rho, why, ""
    na, nb = script_need(a, game), script_need(b, game)
    if na["margin"] * nb["margin"] < 0:
        opposed = (f"{a.get('player')} needs {na['why_margin']}; {b.get('player')} needs "
                   f"{nb['why_margin']} — the scripts pull apart, so a close game suits this ticket best")
        caveat = "; ".join(x for x in (caveat, opposed) if x)
        rho, why = min(rho, OPPOSED_SCRIPT_RHO), "opposite scripts — priced as unrelated, not linked"
    if na["points"] * nb["points"] < 0:
        return False, rel.rho, (f"{a.get('player')} needs {na['why_points']}; {b.get('player')} needs "
                                f"{nb['why_points']}"), ""
    return True, max(-0.9, min(0.9, rho)), why, caveat


#: The scorer markets in a reader's words.
_SCORE_WORDS = {"anytime_td": "to score a touchdown", "anytime_goal": "to score a goal", "goals": "to score a goal"}


def pick_words(leg: dict) -> str:
    """"Malik Nabers over 4.5 receptions", "Cam Skattebo to score a
    touchdown", "Giants −2.5" — a leg as the card says it."""
    mkt = str(leg.get("market") or "")
    who = str(leg.get("player") or "")
    if mkt in _SCORE_WORDS:
        return f"{who} {_SCORE_WORDS[mkt]}"
    if leg.get("_game_leg"):
        return who
    side = str(leg.get("side") or "").strip().lower()
    line = leg.get("line")
    try:
        line_w = f"{float(line):g}" if line is not None else ""
    except (TypeError, ValueError):
        line_w = str(line)
    label = str(leg.get("market_label") or mkt.replace("_", " ")).lower()
    return " ".join(x for x in (who, side, line_w, label) if x)


def _odds_words(odds) -> str:
    try:
        o = int(float(odds))
    except (TypeError, ValueError):
        return ""
    return f"+{o}" if o > 0 else str(o)


def _price_words(dec: float) -> str:
    from .twoleg import american
    a = american(dec)
    return f"+{a}" if a > 0 else str(a)


def ticket(sport: str, legs: list[dict], game: dict | None, memo: dict | None = None) -> dict | None:
    """One parlay of two or three legs, or None when any pair conflicts.
    ``memo`` keeps each pair's link for the game (a pair is asked about in
    every trio it sits in)."""
    from . import parlays as P
    from .twoleg import american
    rhos, whys, caveats = {}, [], []
    weight = link_weight()
    for (i, a), (j, b) in itertools.combinations(enumerate(legs), 2):
        mk = (_leg_id(a), _leg_id(b))
        if memo is not None and mk in memo:
            fits, rho, why, cav = memo[mk]
        else:
            fits, rho, why, cav = pair_link(sport, a, b, game)
            if memo is not None:
                memo[mk] = (fits, rho, why, cav)
        if not fits:
            return None
        if rho > 0:
            rho *= weight                                   # the record's word on a positive link (LINK_FILE)
        rhos[(i, j)] = rho
        if cav:
            caveats.append(cav)
        if why and abs(rho) >= 0.10:
            whys.append(f"{a.get('player')} and {b.get('player')}: {why}")
    ps = [float(l["p"]) for l in legs]
    indep = 1.0
    for p in ps:
        indep *= p
    if len(legs) == 2:
        joint = P.joint_two(ps[0], ps[1], rhos[(0, 1)])
    else:
        joint = P.joint_three(tuple(ps), (rhos[(0, 1)], rhos[(0, 2)], rhos[(1, 2)]))
    if not joint or joint <= 0:
        return None
    decs = [_dec(l.get("odds")) for l in legs]
    naive = None
    if all(decs):
        naive = 1.0
        for d in decs:
            naive *= d
    fair = 1.0 / joint
    take = fair * (1.0 + TAKE_EDGE)
    needs = [script_need(l, game) for l in legs]
    said, chance = script_words(needs, game, sport)
    # Which way the whole ticket needs the game to go (`choose`: the tickets
    # a game posts are built to win together).
    lean_m = sum(n["margin"] for n in needs)
    lean_p = sum(n["points"] for n in needs)
    for l in legs:
        st = str(l.get("injury_status") or l.get("own_status") or "").upper()
        if st in ("QUESTIONABLE", "GTD", "DAY-TO-DAY"):
            caveats.append(f"{l.get('player')} is listed questionable — confirm they play before you bet it")
    # CAN A BOOK PAY IT? The most generous same-game price a book plausibly
    # quotes is the legs' product less the doctrine's best-case cut
    # (parlays.BEST_CASE_SGP_TAX); a ticket that needs more than that is
    # read for its read, not bet — their reports' "below that, there is no
    # edge, so pass or play singles".
    playable = None
    if naive:
        best = naive * (1.0 - P.BEST_CASE_SGP_TAX.get(len(legs), 0.12))
        playable = best >= take
        if not playable:
            caveats.append(f"The legs' own prices multiplied pay {_price_words(naive)}, short of the "
                           f"{_price_words(take)} this needs once a book takes its same-game cut — pass, or "
                           f"play the legs as singles, unless your book pays {_price_words(take)} or better")
    return {"legs": legs, "joint": round(joint, 4), "independent": round(indep, 4),
            "fair": american(fair), "fair_words": _price_words(fair),
            "take": american(take), "take_words": _price_words(take),
            "naive": american(naive) if naive else None,
            "naive_words": _price_words(naive) if naive else "",
            "naive_dec": round(naive, 4) if naive else None, "take_dec": round(take, 4),
            "ev_at_naive": round(joint * naive - 1.0, 4) if naive else None,
            "script": said, "script_chance": chance, "links": whys, "caveats": caveats,
            "need_margin": (lean_m > 0) - (lean_m < 0), "need_points": (lean_p > 0) - (lean_p < 0),
            "playable": playable, "staked": False, "stake_units": 0.0}


def _leg_id(l: dict) -> tuple:
    return (l.get("player"), l.get("market"), str(l.get("side") or "").upper(), l.get("line"))


#: What a published leg keeps: the card's words, the journal's keys, and a
#: scorer's research (`research`).
LEG_KEYS = ("player", "team", "opponent", "home", "away", "position", "market", "market_label", "side",
            "line", "odds", "book", "p", "why", "injury_status", "game_date", "research", "research_of",
            "research_points", "headshot",
            # Where the leg came from (SOURCE_RANK) and the book's chance for it:
            # the journal keeps both (parlayledger.log_game_parlays) so the
            # record can say which source's legs hit what they said.
            "pool", "fair",
            # Our own chance before the league's learned correction and the
            # share it was pulled by (engine/legfit), journaled so the
            # correction is learned on our number, never on itself.
            "p_raw", "fit_w", "fit_shift")


def slim(leg: dict) -> dict:
    """A leg as the board publishes it (LEG_KEYS)."""
    return {k: leg.get(k) for k in LEG_KEYS if leg.get(k) not in (None, "", [])}


def pulls_apart(t: dict, chosen: list) -> bool:
    """Whether ``t`` needs the game to go the other way from a ticket
    already chosen — one side ahead against the other, or points against a
    low score (`script_need`, summed over its legs)."""
    m, p = t.get("need_margin") or 0, t.get("need_points") or 0
    for c in chosen:
        cm, cp = c.get("need_margin") or 0, c.get("need_points") or 0
        if (m and cm and m != cm) or (p and cp and p != cp):
            return True
    return False


#: Said on a ticket the game could only fill by letting it pull against the
#: others.
APART_NOTE = ("This ticket needs the game to go a different way from the other tickets here, so it wins "
              "in a different game from them")


def _clubs(t: dict) -> set:
    """The clubs a ticket's legs belong to."""
    return {l.get("team") for l in t.get("legs") or [] if l.get("team")}


def one_club(t: dict) -> bool:
    """Whether every leg of a ticket is one club's."""
    return len(_clubs(t)) == 1 and len(t.get("legs") or []) >= 2


def _research_of(t: dict) -> int:
    return sum(int(l.get("research") or 0) for l in t.get("legs") or [])


def side_reason(t: dict, alt: dict | None, researched: bool = False) -> str:
    """Why a one-club ticket is posted (`choose`): the other club had no
    ticket that fitted, or this one is clearly the stronger read."""
    club = next(iter(_clubs(t)), "")
    # "Both legs here are NYG's", "Every leg here is NYG's": a two-leg ticket read "Both legs here is".
    every = "Both legs here are" if len(t.get("legs") or []) == 2 else "Every leg here is"
    if alt is None:
        return (f"{every} {club}'s: no ticket with the other side's picks fits this game "
                f"(none clears {LEG_FLOOR:.0%} and the rules with these)")
    if researched:
        return (f"{every} {club}'s: its research case is {_research_of(t) - _research_of(alt)} points "
                f"stronger than the best pair with a scorer from each side")
    return (f"{every} {club}'s: {(float(t['joint']) - float(alt['joint'])) * 100:.0f} points likelier "
            f"than the best ticket with both sides")


def side_record(conn) -> dict:
    """{kind: {"one"|"two": {"n", "won", "expected"}}} over every settled game
    parlay (engine/parlayledger: sources game_three and game_td, won or lost),
    a ticket one-club when its legs carry one team. ``expected`` is the sum
    of the chances the tickets were posted at."""
    rows = conn.execute(
        "SELECT p.id, p.source, p.status, p.modeled_joint, l.team FROM parlays p "
        "JOIN parlay_legs l ON l.parlay_id = p.id WHERE p.source IN (?, ?) AND p.status IN ('won', 'lost')",
        (SOURCES["three"], SOURCES["scorers"])).fetchall()
    tickets: dict = {}
    for pid, src, status, joint, team in rows:
        t = tickets.setdefault(pid, {"src": src, "won": status == "won", "joint": joint, "teams": set()})
        if team:
            t["teams"].add(str(team))
    out: dict = {}
    for t in tickets.values():
        if t["joint"] is None or not t["teams"]:
            continue
        kind = "three" if t["src"] == SOURCES["three"] else "scorers"
        g = out.setdefault(kind, {}).setdefault("one" if len(t["teams"]) == 1 else "two",
                                                 {"n": 0, "won": 0, "expected": 0.0})
        g["n"] += 1
        g["won"] += int(t["won"])
        g["expected"] = round(g["expected"] + float(t["joint"]), 4)
    return out


def fit_side_bar(conn, write: bool = True) -> dict:
    """The one-club bar the record supports (see SIDE_MIN_N): {"three":
    {"bar", "fitted", "why", ...}, "scorers": {...}, "record": side_record}.
    Written to the models directory (SIDE_BAR_FILE) for `side_bar`."""
    import datetime as _dt
    rec = side_record(conn)
    out: dict = {"fitted_at": _dt.datetime.now().isoformat(timespec="seconds"), "record": rec}
    for kind, base, (lo, hi) in (("three", SIDE_EDGE, SIDE_EDGE_RANGE), ("scorers", SIDE_RESEARCH, SIDE_RESEARCH_RANGE)):
        one, two = (rec.get(kind) or {}).get("one") or {}, (rec.get(kind) or {}).get("two") or {}
        n1, n2 = int(one.get("n") or 0), int(two.get("n") or 0)
        e1, e2 = float(one.get("expected") or 0), float(two.get("expected") or 0)
        if n1 < SIDE_MIN_N or n2 < SIDE_MIN_N or e1 <= 0 or e2 <= 0 or not two.get("won"):
            out[kind] = {"bar": base, "fitted": False,
                         "why": f"waiting on the record: {n1} one-club and {n2} two-club ticket(s) settled, "
                                f"{SIDE_MIN_N} of each needed"}
            continue
        q = (one["won"] / e1) / (two["won"] / e2)
        qs = 1.0 + (q - 1.0) * n1 / (n1 + SIDE_PRIOR_N)
        if kind == "three":
            bar = round(min(max(SIDE_EDGE + (e1 / n1) * (1.0 - qs), lo), hi), 3)
        else:
            bar = int(min(max(SIDE_RESEARCH + round((1.0 - qs) * 10), lo), hi))
        out[kind] = {"bar": bar, "fitted": True, "q": round(q, 3), "q_shrunk": round(qs, 3),
                     "why": f"one-club tickets hit {one['won'] / e1:.0%} of their posted chance over {n1}, "
                            f"two-club {two['won'] / e2:.0%} over {n2}"}
    if write:
        import json as _json
        import os as _os
        from . import modelstate
        p = modelstate.path(SIDE_BAR_FILE)
        _os.makedirs(_os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(out, f, indent=1, sort_keys=True)
        _os.replace(tmp, p)
    return out


def fit_link_weight(conn, write: bool = True) -> dict:
    """The weight a positive link between two legs carries in a ticket's
    chance, as the record supports it (LINK_FILE): from every graded ticket
    priced with a positive link (parlayledger.calibration's positive_rho),
    the share of the link's lift over the unrelated legs that came true,
    shrunk toward LINK_WEIGHT_DEFAULT by LINK_PRIOR_N and held to 0..1.
    Written to the models directory for `link_weight`."""
    import datetime as _dt
    from . import parlayledger as PL
    pos = (PL.calibration(conn) or {}).get("positive_rho") or {}
    n, won = int(pos.get("n") or 0), float(pos.get("won") or 0)
    em, ei = float(pos.get("expected") or 0), float(pos.get("expected_independent") or 0)
    out = {"fitted_at": _dt.datetime.now().isoformat(timespec="seconds"), "n": n, "won": int(won),
           "expected": em, "expected_independent": ei}
    if n < LINK_MIN_N or em <= ei:
        out.update(weight=LINK_WEIGHT_DEFAULT, fitted=False,
                   why=f"waiting on the record: {n} ticket(s) priced with a positive link settled, "
                       f"{LINK_MIN_N} needed")
    else:
        raw = min(max((won - ei) / (em - ei), 0.0), 1.0)
        w = LINK_WEIGHT_DEFAULT + (raw - LINK_WEIGHT_DEFAULT) * n / (n + LINK_PRIOR_N)
        out.update(weight=round(w, 3), raw=round(raw, 3), fitted=True,
                   why=f"{n} tickets priced with a positive link hit {int(won)}: the link said "
                       f"{em:.0f}, the legs alone {ei:.0f}")
    if write:
        import json as _json
        import os as _os
        from . import modelstate
        path = modelstate.path(LINK_FILE)
        _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(out, f, indent=1, sort_keys=True)
        _os.replace(tmp, path)
    return out


_LINK: dict = {}
#: Why the link's fit on file could not be read, in this process; None when it
#: was read or there is none yet. The build log says it beside the weight.
LINK_ERROR: str | None = None


def link_weight() -> float:
    """The weight in force (`fit_link_weight`): the record's fit where one
    is on file, else LINK_WEIGHT_DEFAULT; read once per change of the file.
    No file is the ordinary state before the first fit, and quiet; a file
    that cannot be read gives the default too, so it is SAID: printed once a
    process and kept in LINK_ERROR, which the build log shows."""
    global LINK_ERROR
    try:
        import json as _json
        import os as _os
        from . import modelstate
        path = modelstate.path(LINK_FILE)
        try:
            key = (path, _os.stat(path).st_mtime_ns)
        except FileNotFoundError:
            LINK_ERROR = None
            return LINK_WEIGHT_DEFAULT
        if _LINK.get("key") != key:
            with open(path, encoding="utf-8") as f:
                _LINK.update(key=key, data=_json.load(f))
        w = float((_LINK.get("data") or {}).get("weight", LINK_WEIGHT_DEFAULT))
        LINK_ERROR = None
        return min(max(w, 0.0), 1.0)
    except Exception as exc:                                 # noqa: BLE001
        why = f"{type(exc).__name__}: {exc}"
        if LINK_ERROR != why:
            print(f"  ⚠️ the parlay legs' link weight could not be read ({why}); {LINK_WEIGHT_DEFAULT} is in force")
        LINK_ERROR = why
        return LINK_WEIGHT_DEFAULT


_SIDE_BAR: dict = {}
#: Why the fit on file could not be read, in this process; None when it was
#: read or there is none yet. The build log says it beside the bar (`summary`).
SIDE_BAR_ERROR: str | None = None


def _leg_fit_census(sport: str) -> dict:
    try:
        from . import legfit
        return legfit.census(sport)
    except Exception as exc:                                 # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def side_bar() -> tuple:
    """(edge, research points, fitted) in force: the record's fit
    (`fit_side_bar`) where one is on file, else SIDE_EDGE and SIDE_RESEARCH;
    always inside the ranges. Read once per change of the file. No file is
    the ordinary state before the first fit, and quiet; a file that cannot be
    read gives the defaults too, so it is SAID: printed once a process and
    kept in SIDE_BAR_ERROR, which the build log shows."""
    global SIDE_BAR_ERROR
    try:
        import json as _json
        import os as _os
        from . import modelstate
        p = modelstate.path(SIDE_BAR_FILE)
        try:
            key = (p, _os.stat(p).st_mtime_ns)
        except FileNotFoundError:
            SIDE_BAR_ERROR = None
            return SIDE_EDGE, SIDE_RESEARCH, False
        if _SIDE_BAR.get("key") != key:
            with open(p, encoding="utf-8") as f:
                _SIDE_BAR.update(key=key, data=_json.load(f))
        d = _SIDE_BAR["data"]
        three, pairs = d.get("three") or {}, d.get("scorers") or {}
        e = min(max(float(three["bar"]), SIDE_EDGE_RANGE[0]), SIDE_EDGE_RANGE[1]) if three.get("fitted") else SIDE_EDGE
        r = (int(min(max(int(pairs["bar"]), SIDE_RESEARCH_RANGE[0]), SIDE_RESEARCH_RANGE[1]))
             if pairs.get("fitted") else SIDE_RESEARCH)
        SIDE_BAR_ERROR = None
        return e, r, bool(three.get("fitted") or pairs.get("fitted"))
    except Exception as exc:                                 # noqa: BLE001
        why = f"{type(exc).__name__}: {exc}"
        if SIDE_BAR_ERROR != why:
            print(f"  ⚠️ the one-club bar's fit could not be read ({why}); the defaults are in force")
        SIDE_BAR_ERROR = why
        return SIDE_EDGE, SIDE_RESEARCH, False


def choose(tickets: list[dict], n: int, rank=None, researched: bool = False,
           shared: tuple = (MAX_SHARED, None), keep=None) -> list[dict]:
    """``n`` of ``tickets`` (`_choose`), and with ``keep`` the tickets the game
    posted last build first, in their order (`ident`).

    A POSTED TICKET STAYS UNTIL A LEG BREAKS (ZQ, 2026-11-20). Ethan, on rows
    reading "Parlays 0 of 28" and "1 of 42": "why do we have 30 parlays being
    made per game?? There should only be 3 parlays made per game". Every build
    chose a game's tickets afresh, so a line moving a point reordered them and
    the board posted another set: one NFL game posted 19 versions of its
    three-leg tickets between Thursday and Sunday. A ticket posted last build
    is posted again while it is still one this build would make (each leg
    still a leg here, at a real book and its floor, the ticket clearing its own
    and fitting the others: in ``tickets``), at the books' current numbers;
    only the places it leaves are chosen afresh. A one-club ticket stays while
    it is still the likelier read at all (it was posted clearly the likelier,
    SIDE_EDGE). Never fewer tickets than a fresh choice makes, nor more that
    pull against the others (APART_NOTE: the tickets are built to win
    together first)."""
    got = _choose(tickets, n, rank, researched, shared)
    if keep:
        mine = _choose(tickets, n, rank, researched, shared, keep)
        apart = lambda ts: sum(APART_NOTE in (t.get("caveats") or []) for t in ts)   # noqa: E731
        if len(mine) >= len(got) and apart(mine) <= apart(got):
            return mine
    return got


def ident(t: dict) -> tuple:
    """A ticket's identity from one build to the next: each leg's player,
    market and side, the line left out. A line the books move is the same bet
    at the book's new number; a different player, market or side is another."""
    return tuple(sorted((str(l.get("player") or ""), str(l.get("market") or ""),
                         str(l.get("side") or "").upper()) for l in t.get("legs") or [] if isinstance(l, dict)))


def _choose(tickets: list[dict], n: int, rank=None, researched: bool = False,
            shared: tuple = (MAX_SHARED, None), keep=()) -> list[dict]:
    """The likeliest first (or by ``rank``, a sort key — the scorer pairs'
    research, `_by_research`); each next one shares at most MAX_SHARED legs
    with every ticket already chosen, and no leg rides on more than
    MAX_USES of them. A second pass, when the first leaves fewer than
    ``n``, lets a ticket share all but one leg. ``shared`` is those passes:
    (0,) for tickets that may share no leg at all.

    BUILT TO WIN TOGETHER (Ethan's NFL Bet checking chats, 2026-10-25: "can
    both of these tickets hit in both situations? … We want to make sure both
    tickets win"; 2026-11-08: "I don't want to build them to where if one
    parlay wins, the other parlay can't win"). No ticket that pulls the game
    the other way from one already chosen (`pulls_apart`) — until the game
    has no other way to fill its tickets, and then the ticket says so.

    BOTH SIDES (SIDE_EDGE): a ticket all of one club's is taken only when no
    two-club ticket fits in its place, or it is clearly the stronger read
    than the best one that does and fewer than ONE_SIDED_MAX one-club
    tickets are chosen; it says which (`side_reason`). ``researched``: the
    tickets are scorer pairs ranked on their research, and the stronger read
    is SIDE_RESEARCH more research points. ``keep``: the identities posted
    last build (`choose`), tried first in their order."""
    ranked = sorted(tickets, key=rank or (lambda t: (-t["joint"], -(t.get("ev_at_naive") or -9))))
    held: set = set()
    if keep:
        where = {}
        for i, k in enumerate(keep):
            where.setdefault(tuple(tuple(x) for x in k), i)
        first: dict = {}
        for t in ranked:
            i = where.get(ident(t))
            if i is not None and i not in first:
                first[i] = t
        held = {id(t) for t in first.values()}
        ranked = [first[i] for i in sorted(first)] + [t for t in ranked if id(t) not in held]
    edge, rbar, _fitted = side_bar()

    def clearly(t: dict, alt: dict) -> bool:
        if researched:
            return _research_of(t) - _research_of(alt) >= rbar
        return float(t["joint"]) - float(alt["joint"]) >= edge - 1e-9

    def still_ahead(t: dict, alt: dict) -> bool:
        # A posted one-club ticket: kept while it is the likelier read at all.
        if id(t) not in held:
            return False
        if researched:
            return _research_of(t) > _research_of(alt)
        return float(t["joint"]) > float(alt["joint"])

    def pick(together: bool) -> tuple:
        out: list = []
        uses: dict = {}
        why: dict = {}

        def fits(t: dict, limit) -> bool:
            ids = {_leg_id(l) for l in t["legs"]}
            lim = limit if limit is not None else len(ids) - 1
            if any(len(ids & {_leg_id(l) for l in c["legs"]}) > lim for c in out):
                return False
            if any(uses.get(i, 0) >= MAX_USES for i in ids):
                return False
            return not (together and pulls_apart(t, out))
        # The posted tickets first, under the loosest pass they could have been
        # posted in (the last of ``shared``), so a new ticket that fits a
        # stricter pass never takes a place one of them still holds.
        stages = ([(shared[-1], True)] if held else []) + [(lim, False) for lim in shared]
        for lim, only_held in stages:
            for t in ranked:
                if len(out) >= n:
                    return out, why
                if only_held and id(t) not in held:
                    continue
                if t in out or not fits(t, lim):
                    continue
                if one_club(t):
                    alt = next((m for m in ranked if m not in out and not one_club(m) and fits(m, lim)), None)
                    if alt is not None and (sum(map(one_club, out)) >= ONE_SIDED_MAX
                                            or not (clearly(t, alt) or still_ahead(t, alt))):
                        continue
                    why[id(t)] = side_reason(t, alt, researched)
                out.append(t)
                for i in {_leg_id(l) for l in t["legs"]}:
                    uses[i] = uses.get(i, 0) + 1
        return out, why
    together, why_t = pick(True)
    loose, why_l = pick(False) if len(together) < n else (together, why_t)
    side = lambda t, why: (dict(t, caveats=list(t.get("caveats") or []) + [why[id(t)]], one_club=True)  # noqa: E731
                           if id(t) in why else t)
    if len(together) >= len(loose):
        return [side(t, why_t) for t in together]
    # The game cannot fill its tickets so they all win together: the old
    # choice, and each ticket that pulls against an earlier one says so.
    out: list = []
    for t in loose:
        c = side(t, why_l)
        out.append(dict(c, caveats=list(c.get("caveats") or []) + [APART_NOTE]) if pulls_apart(t, out) else c)
    return out


def backups(sport: str, t: dict, pool: list[dict], game: dict | None) -> list[dict]:
    """For each leg, the likeliest leg off the ticket that fits the other
    legs in its place: {"for", "leg"}."""
    out = []
    ids = {_leg_id(l) for l in t["legs"]}
    for i, leg in enumerate(t["legs"]):
        rest = [l for j, l in enumerate(t["legs"]) if j != i]
        best = None
        for cand in sorted(pool, key=lambda l: -float(l["p"])):
            if _leg_id(cand) in ids:
                continue
            if all(pair_link(sport, cand, r, game)[0] for r in rest):
                best = cand
                break
        if best is not None:
            out.append({"for": leg.get("player"), "leg": best})
    return out


# --- one game ---------------------------------------------------------------------------------
def card(t: dict, n: int, kind: str, sport: str = "") -> dict:
    """One ticket as the report and the Parlays page draw it: a title, the
    price line, each leg in words with its price and why, the script it
    needs, how the legs link, the backups and the caveats."""
    joint = float(t.get("joint") or 0)
    head = (f"Parlay {n}" if kind == "three" else f"Two-leg parlay {n}" if kind == "two"
            else f"{SCORER_WORDS.get(sport, 'Scorer').capitalize()} pair {n}")
    # The legs-unrelated chance only where it differs from ours (a link counted,
    # `link_weight`): said beside an equal number it is the same number twice.
    indep = float(t.get("independent") or 0)
    price = (f"{joint:.0%} by our numbers"
             + (f" ({indep:.0%} if the legs were unrelated)" if f"{indep:.0%}" != f"{joint:.0%}" else "")
             + f" · fair {t.get('fair_words')} · take it at {t.get('take_words')} or better")
    # Said once: a ticket no book is likely to pay enough for says so among its caveats, with both prices (`ticket`).
    if t.get("naive_words") and not any("own prices multiplied pay" in str(c) for c in t.get("caveats") or []):
        price += f" · the legs' own prices multiplied pay {t['naive_words']}, and a book's same-game price pays less"
    from .gameresults import bet_of
    legs = [{"pick": pick_words(l), "player": l.get("player"), "team": l.get("team"),
             # The leg itself, graded on a finished game's page (engine/gameresults).
             **({"bet": bet_of(l)} if bet_of(l) else {}),
             "price": " ".join(x for x in (_odds_words(l.get("odds")), l.get("book") or "") if x),
             "chance": round(float(l.get("p") or 0), 4), "why": list(l.get("why") or []),
             **({"headshot": l["headshot"]} if l.get("headshot") else {}),
             # A scorer's research case, out of RESEARCH_MAX (`research_scorers`).
             **({"research": int(l["research"]), "research_of": int(l.get("research_of") or RESEARCH_MAX)}
                if l.get("research") is not None else {})}
            for l in t.get("legs") or []]
    script = ""
    if t.get("script"):
        script = f"What it needs: {t['script']}"
        if t.get("script_chance") is not None:
            script += f" — about {float(t['script_chance']):.0%} likely by the lines"
    backs = [f"If {b['for']} is out or that number moves: {pick_words(b['leg'])} "
             f"({_odds_words(b['leg'].get('odds'))}, {float(b['leg'].get('p') or 0):.0%})"
             for b in t.get("backups") or []]
    out = {"title": head, "price_line": price, "legs": legs, "script": script,
           "links": list(t.get("links") or []), "backups": backs, "caveats": list(t.get("caveats") or []),
           "joint": joint, "fair": t.get("fair"), "take": t.get("take")}
    # THE TOUCHDOWN RULE ON A PAIR (decision 1 under RUN_NEXT 00f, Ethan's
    # NFL Bet checking method: an anytime touchdown at 45%, or 40% with a
    # red-zone role). The floor stays where it is; a pair whose two scorers
    # are both 40% or better says so, and one that isn't says that too.
    if kind not in ("three", "two") and legs and sport in TD_RULE_SPORTS:
        low = [l for l in legs if float(l.get("chance") or 0) < TD_RULE_PAIR]
        out["td_rule"] = not low
        out["rule_note"] = (f"Both scorers are {TD_RULE_PAIR:.0%} or better — our touchdown rule" if not low else
                            f"Below our touchdown rule ({TD_RULE_PAIR:.0%} a scorer): "
                            + ", ".join(f"{l.get('player')} {float(l.get('chance') or 0):.0%}" for l in low))
    return out


#: The touchdown rule's fallback (likelyboard.TD_RULE_FALLBACK): each scorer
#: on a pair at 40% or better. Football, where the rule was written.
TD_RULE_PAIR = 0.40
TD_RULE_SPORTS = ("nfl", "cfb")


def game_label(game: dict) -> str:
    return f"{game.get('away')}@{game.get('home')}"


def tickets_of(sport: str, game: dict, legs: list[dict], memo: dict | None = None,
               extra: list[dict] | None = None, picks: set | None = None, posted: dict | None = None) -> dict:
    """A game's three-leg tickets (``threes``) from ``legs``, each with its
    backups from the same legs; those that clear THREE_FLOOR first. Beside them
    what the notes count: the legs tried (``pool``), the trios without a
    conflict (``threes_fit``) and how many of those clear the bar
    (``threes_clear``).

    EVERY GAME ITS THREE (THREELEG1, 2026-11-19, and ZR, 2026-11-20; Ethan: "i
    want 3 3 leg player prop parlays", "the 3 best parlays possible with the
    data we have including the game report with the best possible props we
    have"). When fewer than THREE_MIN clear THREE_FLOOR from ``legs``, the game
    fills up to it from ``legs`` and then ``extra`` (a report's game's other
    priced props, not its picks: `from_report`), the fewest such legs first:
    one prop the report did not pick beside two of its picks, down to
    LONG_FLOOR; then the Most Likely board's picks for the game in the picks'
    places, on a ticket that clears THREE_FLOOR (`board_pick`); and last the
    game's best props, any of them, down to LONG_FLOOR. Each filled ticket says
    so on its card (`_fill_caveats`); ``wider`` counts the legs the fill could
    try and ``filled`` the tickets it made. ``extra`` may hold legs down to
    FILL_LEG_FLOOR (THREELEG2), and ``picks`` the report's picks among
    ``legs`` and ``extra`` (by `_leg_id`), when a pick under LEG_FLOOR rides in
    ``extra``: the fill takes the picks first and names every other leg.
    ``posted``: the game's tickets as the last build posted them ({kind:
    [identity]}, `posted_for`), each posted again while it is still one of
    these (`choose`)."""
    pool = sorted(legs, key=lambda l: -float(l["p"]))[:MAX_POOL]
    memo = {} if memo is None else memo
    keep = (posted or {}).get("threes")
    threes = [t for t in (ticket(sport, list(c), game, memo) for c in itertools.combinations(pool, 3)) if t]
    strong3 = [t for t in threes if float(t["joint"]) >= THREE_FLOOR]
    chosen = choose(strong3, THREE_PER_GAME, keep=keep)
    in_pool = {_leg_id(l) for l in pool}
    own = set(picks) if picks is not None else in_pool
    # THE REPORT'S OWN PICKS FIRST INTO THE FILL'S POOL (PARLAYWIN1, 2026-11-19).
    # Every ticket takes two of them (FILL_OUTSIDE_MAX), and sorted by chance
    # alone a game's other props at 60% and better took the MAX_POOL places
    # ahead of its picks at 50-60% (a hockey game prices a hundred props, the
    # NFL's Sunday games forty once bought), leaving it nothing to build from.
    # …then the Most Likely board's picks for the game (`board_pick`), then its other props.
    more = sorted((l for l in extra or [] if _leg_id(l) not in in_pool),
                  key=lambda l: (_leg_id(l) not in own, not board_pick(l), -float(l["p"])))
    wider = pool + more[:max(0, MAX_POOL - len(pool))]
    filled = board_filled = props_filled = 0
    fill_fit = fill_clear = None
    if len(chosen) < THREE_MIN:
        outside = lambda t: sum(_leg_id(l) not in own for l in t["legs"])            # noqa: E731
        every = [t for t in (ticket(sport, list(c), game, memo) for c in itertools.combinations(wider, 3)) if t]
        # No more than FILL_OUTSIDE_MAX legs the report did not pick on a ticket.
        trios = [t for t in every if outside(t) <= FILL_OUTSIDE_MAX]
        cands = [t for t in trios if float(t["joint"]) >= LONG_FLOOR]
        # What a game short of its three says it had (the heartbeat's reasons
        # and its note's `_uses_words`): every trio of its legs without a
        # conflict, whoever's legs (the last level tries them all, ZR), and
        # those at LONG_FLOOR.
        fill_fit = len(every)
        fill_clear = sum(1 for t in every if float(t["joint"]) >= LONG_FLOOR)
        rank = lambda t: (outside(t), -float(t["joint"]), -(t.get("ev_at_naive") or -9))  # noqa: E731
        got = choose(cands, THREE_MIN, rank=rank, keep=keep)
        # Each wider level adds to what the one before it made, never in its
        # place: a ticket of the report's picks stays while the places it leaves
        # are filled (behind the game's posted tickets, `choose`).
        held = lambda made: list(keep or []) + [ident(t) for t in made]             # noqa: E731
        stands = lambda l: _leg_id(l) in own or board_pick(l)                       # noqa: E731
        if len(got) < THREE_MIN:
            # THE MOST LIKELY BOARD'S PICKS STAND IN (BOARDFILL1, 2026-11-19;
            # Ethan, the day Sunday's props were bought on the Thursday: "I want
            # parlays ... for the games this weekend on Sunday"). Five of the
            # eleven Sunday games made no ticket: their reports carried 15 player
            # picks and 5 of them legs (the rest scorers, tackles and the like,
            # never a leg), and a ticket takes two of the report's. The game's
            # Most Likely picks its card had no room for are the board's own
            # numbers, which hit what they claim (the NFL's 62.2% said, 61.7%
            # hit, 2,036 picks): at LEG_FLOOR or better they may take the report's
            # picks' places, on a ticket that clears THREE_FLOOR, each one named.
            board3 = [t for t in every if outside(t) > FILL_OUTSIDE_MAX and all(stands(l) for l in t["legs"])
                      and float(t["joint"]) >= THREE_FLOOR]
            wide = choose(cands + board3, THREE_MIN, rank=rank, keep=held(got)) if board3 else got
            if len(wide) > len(got):
                got = wide
        if len(got) < THREE_MIN:
            # THE GAME'S BEST PROPS, LAST (ZR, 2026-11-20: "the 3 best parlays
            # possible ... with the best possible props we have"). A game whose
            # report and Most Likely picks still make fewer than three takes
            # any of its props the fill could try, the report's picks first and
            # the fewest of the others, down to LONG_FLOOR; each leg named.
            rest = [t for t in every if outside(t) > FILL_OUTSIDE_MAX and float(t["joint"]) >= LONG_FLOOR]
            wide = choose(cands + rest, THREE_MIN, rank=rank, keep=held(got)) if rest else got
            if len(wide) > len(got):
                got = wide
        if len(got) > len(chosen):
            chosen = got
            for t in chosen:
                said = _fill_caveats(t, own)
                if said:
                    t["caveats"] = list(t.get("caveats") or []) + said
                    t["filled"] = True
                    filled += 1
                    # How it was made up (FILL_KINDS), journaled with it, so the
                    # record says how each kind of filled ticket does apart.
                    if outside(t) > FILL_OUTSIDE_MAX:
                        if all(stands(l) for l in t["legs"]):
                            board_filled += 1
                            t["fill"] = "board"
                        else:
                            props_filled += 1
                            t["fill"] = "props"
                    elif outside(t):
                        t["fill"] = "one"
    for t in chosen:
        t["backups"] = [{"for": b["for"], "leg": slim(b["leg"])} for b in backups(sport, t, wider, game)]
        t["legs"] = [slim(l) for l in t["legs"]]
    return {"threes": chosen, "pool": len(pool), "threes_fit": len(threes), "threes_clear": len(strong3),
            "wider": len(wider), "filled": filled,
            # Tickets the Most Likely board's picks stood in on (`board_pick`), and
            # tickets the game's other props made up (ZR).
            "board_filled": board_filled, "props_filled": props_filled,
            "fill_fit": fill_fit, "fill_clear": fill_clear,
            # The report's own picks among the legs a ticket could take (a ticket takes two at least).
            "wider_own": sum(1 for l in wider if _leg_id(l) in own)}


#: HOW A FILLED TICKET WAS MADE UP (ZR, 2026-11-20), journaled with it
#: (engine/parlayledger ``fill``) so the record says how each kind does apart:
#: one prop the report did not pick beside two of its picks ("one"), the Most
#: Likely board's picks standing in ("board"), the game's best props, last
#: ("props"), and a scorer pair with a stand-in scorer ("stand_in"). A ticket
#: of the report's own picks carries none.
FILL_KINDS = ("one", "board", "props", "stand_in")


def board_pick(leg: dict) -> bool:
    """A leg that is the Most Likely board's own pick (a seat of the board's or
    one its seat caps dropped: pool "likely") at LEG_FLOOR or better: the legs
    that may stand in for a report's picks (`tickets_of`, BOARDFILL1)."""
    try:
        return leg.get("pool") == "likely" and float(leg.get("p") or 0) >= LEG_FLOOR
    except (TypeError, ValueError):
        return False


def _fill_caveats(t: dict, own: set) -> list[str]:
    """What a ticket filling its game up to THREE_MIN says on its card: the legs
    that are not the report's picks (the Most Likely board's picks for the
    game, and any other prop), and that it is a longer ticket when it is
    under THREE_FLOOR. Nothing for a ticket of the picks that clears it."""
    out = []
    outside = [l for l in t["legs"] if _leg_id(l) not in own]
    likely = [l for l in outside if board_pick(l)]
    board = [l for l in outside if not board_pick(l)]
    if likely:
        named = _and([f"{pick_words(l)} ({float(l.get('p') or 0):.0%})" for l in likely])
        out.append(f"{named} {'is not one of' if len(likely) == 1 else 'are not'} this report's picks: "
                   f"{'a Most Likely pick' if len(likely) == 1 else 'Most Likely picks'} for this game the "
                   f"report's card did not list, added so the game has {THREE_MIN} three-leg parlays")
    if board:
        named = _and([f"{pick_words(l)} ({float(l.get('p') or 0):.0%})" for l in board])
        out.append(f"{named} {'is not one of' if len(board) == 1 else 'are not'} this report's picks: "
                   f"{'a prop' if len(board) == 1 else 'props'} the board priced, added so the game has "
                   f"{THREE_MIN} three-leg parlays")
    low = [l for l in t["legs"] if float(l.get("p") or 0) < LEG_FLOOR]
    if low:
        named = _and([f"{pick_words(l)} ({float(l.get('p') or 0):.0%})" for l in low])
        out.append(f"{named} {'is' if len(low) == 1 else 'are'} under the {LEG_FLOOR:.0%} a leg is built to: "
                   f"this game had too few props that high to make {THREE_MIN} three-leg parlays")
    joint = float(t.get("joint") or 0)
    if joint < THREE_FLOOR:
        out.append(f"A longer ticket: {joint * 100:.1f}% by our numbers, under the {THREE_FLOOR:.0%} a three-leg "
                   f"parlay is built to — this game had no stronger one to make up its {THREE_MIN}")
    return out


def _uses_words(made: dict) -> str:
    """What else stops a game short when more of its trios reach LONG_FLOOR
    than it made: a leg rides on MAX_USES tickets at most (`choose`)."""
    n = len(made.get("threes") or [])
    return f" with no leg on more than {MAX_USES} tickets" if n and int(made.get("fill_clear") or 0) > n else ""


def _and(words: list) -> str:
    """"A", "A and B", "A, B and C"."""
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + f" and {words[-1]}" if words else ""


def _threes_note(made: dict, whose: str = "this game's priced props") -> str:
    """Why a game has fewer than THREE_MIN three-leg tickets: too few legs, or
    none of the ones it has fit together and reach LONG_FLOOR."""
    n, wider = len(made["threes"]), made.get("wider", made["pool"])
    head = f"{n} of {THREE_MIN}: "
    if wider < 3:
        return (head + f"a three-leg parlay takes three legs at {LEG_FLOOR:.0%} or better, and {whose} "
                f"{'make' if wider != 1 else 'makes'} {wider}")
    return (head + f"the {wider} legs at {LEG_FLOOR:.0%} or better in {whose} make no "
            f"{'more ' if n else ''}three that fit together without a conflict and reach {LONG_WORDS} "
            f"by our numbers{_uses_words(made)}")


def build_game(sport: str, game: dict, legs: list[dict], scorers: list[dict],
               priced: int | None = None, pairs_out: dict | None = None, spare: list | None = None) -> dict:
    """A game's three three-leg tickets and three scorer pairs, and why there
    are fewer when there are. ``priced`` is how many priced scorers the game
    had before the research read them (`research_scorers`); ``spare`` its
    scorers that only fill (`stand_ins`). ``pairs_out`` is given every scorer
    pair the game could post, under its label, so the report stage can choose
    them again with the posted ones first (`report_only`)."""
    memo: dict = {}
    made = tickets_of(sport, game, legs, memo)
    chosen, n_threes, n_pool = made["threes"], made["threes_fit"], made["pool"]
    out = {"game": game_label(game), "home": game.get("home"), "away": game.get("away"),
           "date": game.get("date") or "", "kickoff": game.get("kickoff") or "",
           "threes": chosen, "legs_read": n_pool, "threes_considered": n_threes}
    if len(chosen) < THREE_MIN:
        out["threes_note"] = _threes_note(made)
    if sport in SCORER_MARKETS:
        researched = sport in RESEARCH_SPORTS
        rank = scorer_rank(researched)
        # THE RESEARCH FIRST (RESEARCH_SPORTS): the strongest cases are the
        # scorers tried, and the pairs are ranked on them; our chance breaks
        # ties. Hockey ranks on the chance.
        by_leg = (lambda l: (-int(l.get("research") or 0), -float(l["p"]))) if researched \
            else (lambda l: (-float(l["p"]),))
        sc = sorted(scorers, key=by_leg)[:MAX_SCORERS]

        def pairs_of(legs_: list, fill: set) -> list:
            # Every pair of ``legs_`` that fits, its research summed; one with a
            # scorer from ``fill`` counts and names it (`stand_ins`).
            out_ = []
            for c in itertools.combinations(legs_, 2):
                t = ticket(sport, list(c), game, memo)
                if not t:
                    continue
                if researched:
                    t["research"] = sum(int(l.get("research") or 0) for l in t["legs"])
                n = sum(_leg_id(l) in fill for l in t["legs"])
                if n:
                    t["stand_ins"] = n
                    t["fill"] = "stand_in"                  # journaled: the record says how they did apart
                    t["caveats"] = list(t.get("caveats") or []) + [_stand_in_caveat(l, sport) for l in t["legs"]
                                                                   if _leg_id(l) in fill]
                out_.append(t)
            return out_
        pairs = pairs_of(sc, set())
        got = choose(pairs, SCORER_PER_GAME, rank=rank, researched=researched)
        if len(got) < SCORER_PER_GAME and spare:
            # THREE A GAME (ZR): its next scorers fill, the fewest on a pair, each named (`stand_ins`).
            extra = sorted(spare, key=lambda l: (l.get("stand_in") != "weaker",) + by_leg(l))[:MAX_SCORERS]
            pairs = pairs_of(sc + extra, {_leg_id(l) for l in extra})
            wide = choose(pairs, SCORER_PER_GAME, rank=rank, researched=researched)
            if len(wide) > len(got):
                got = wide
        if pairs_out is not None:
            pairs_out[game_label(game)] = pairs
        out["scorers"] = [dict(t, legs=[slim(l) for l in t["legs"]]) for t in got]
        out["scorers_read"] = len(sc)
        if researched:
            out["scorers_priced"] = len(sc) if priced is None else int(priced)
        if len(out["scorers"]) < SCORER_PER_GAME:
            floor = f"{SCORER_FLOOR.get(sport, 0.25):.0%}"
            fill_floor = f"{SCORER_FILL_FLOOR.get(sport, SCORER_FLOOR.get(sport, 0.25)):.0%}"
            if researched:
                n_priced = out["scorers_priced"]
                out["scorers_note"] = (
                    f"{len(out['scorers'])} of {SCORER_PER_GAME}: {len(sc)} of the {n_priced} priced "
                    f"scorer(s) in this game at {floor} or better carry a research case — a red-zone role "
                    f"and {RESEARCH_MIN} or more of the {RESEARCH_MAX} research points (the team's expected "
                    f"points, the defense faced, usage and red-zone work, the matchup read and the "
                    f"game script) — and {len(spare or [])} more with a red-zone role down to {fill_floor} "
                    f"could fill")
            else:
                out["scorers_note"] = (f"{len(out['scorers'])} of {SCORER_PER_GAME}: {len(sc)} priced "
                                       f"{SCORER_WORDS.get(sport, 'scorer')}(s) in this game at "
                                       f"{floor} or better, and {len(spare or [])} more down to {fill_floor}")
    else:
        out["scorers"] = []
        out["scorers_note"] = "No scorer market in this league — basketball's books post no anytime scorer"
    return out


# --- a game still to play with no priced prop (THREELEG3) ------------------------------------
# EVERY GAME ITS ENTRY (THREELEG3, 2026-11-19; Ethan the same day: "I want those
# for every single game"). The NFL's Thursday board held thirteen games and posted
# parlays on three: a game had an entry only when a leg at LEG_FLOOR or a priced
# scorer fell in it, and the books' player props are bought for tonight's games
# and, in the two weekly leagues, the next day's (engine/oddsbudget
# DAY_BEFORE_LEAGUES), so Sunday's ten had nothing to build from and their
# reports dropped the parlays section without a word. A game whose props all sat
# under LEG_FLOOR had no entry either, so the fill down to FILL_LEG_FLOOR never
# reached it. Every game still to play has its entry now; one with no priced
# prop says when its props are bought (`props_note`), and its report says so in
# one line.
#: Why a game still to play has no priced prop (`props_note`).
PROPS_WAIT, PROPS_NONE = "props_not_bought", "no_props_priced"
#: How far ahead the buying schedule speaks for (`props_note`): a board holds
#: the coming week, and a game further out says only that nothing is priced.
PROPS_WAIT_MAX_DAYS = 10


#: A GAME WHOSE PROPS ARE BOUGHT, BY COUNT (EARLYPROPS1, 2026-11-19). The NFL's
#: far pull bought Sunday's props on the Thursday, about 36 a game, and the
#: games still read "bought from three days before it ... once the books post
#: them", ten of them, because a game inside its buying days that was short of
#: its tickets kept the calendar's word whatever was on file (step YQ's stray prop
#: or two). From this many priced props a game's are bought: short of its three,
#: it says the real reason (`_report_note`).
PROPS_BOUGHT_MIN = 10


def _priced_counts(board: dict, games: list) -> dict:
    """Each game's (`game_label`) player props a book has priced, counted once
    each: a row of the board's at a real book, the proxy line's aside."""
    seen: dict = {}
    for key in ("recommendations", "most_likely"):
        for r in board.get(key) or []:
            if not isinstance(r, dict) or r.get("has_market") is False or r.get("_game_leg"):
                continue
            if str(r.get("book") or "").strip().lower() in ("", "proxy"):
                continue
            g = _game_of(r, games)
            if g:
                seen.setdefault(game_label(g), set()).add(
                    (r.get("player"), r.get("market"), str(r.get("side") or "").upper(), r.get("line")))
    return {k: len(v) for k, v in seen.items()}


def _slate_today(now=None) -> str:
    """Today's slate (ISO date, Eastern, rolled at 5 AM: engine/slateday). A
    naive ``now`` is UTC, as the builders' clock reads it
    (losspatterns.minutes_until)."""
    from .slateday import baseball_day
    if isinstance(now, (int, float)) and not isinstance(now, bool):
        from .oddsbudget import slate_day
        return slate_day(float(now))
    if isinstance(now, dt.datetime):
        from zoneinfo import ZoneInfo
        aware = now if now.tzinfo is not None else now.replace(tzinfo=dt.timezone.utc)
        return baseball_day(aware.astimezone(ZoneInfo("America/New_York")))
    return baseball_day()


#: When a league's props are first bought, in words (engine/oddsbudget.buy_ahead_days).
_LEAD_WORDS = {0: "on its game day", 1: "the day before it", 2: "from two days before it",
               3: "from three days before it"}


def props_note(sport: str, game: dict, now=None) -> tuple[str, str]:
    """Why a game still to play has no priced prop, and when it will: (reason,
    words). The NFL buys a game's props from three days before it (EARLYPROPS1:
    Sunday's from Thursday), college football the day before it, the rest on
    its day (engine/oddsbudget.buy_ahead_days). Further out, it says the day
    they are first bought; inside the NFL's far days the books may not have
    posted them yet; the day before, and on the day, no book has priced one."""
    from .oddsbudget import buy_ahead_days
    lead = buy_ahead_days(sport)
    try:
        day = dt.date.fromisoformat(str(game.get("date") or "")[:10])
        ahead = (day - dt.date.fromisoformat(_slate_today(now))).days
    except ValueError:
        day, ahead = None, 0
    words = _LEAD_WORDS.get(lead, f"from {lead} days before it")
    if day is not None and lead + 1 <= ahead <= PROPS_WAIT_MAX_DAYS:
        when = day - dt.timedelta(days=lead)
        return PROPS_WAIT, (f"the books' player props for this game are bought {words}, on {when.strftime('%A')}, "
                            f"and its parlays are built from them then")
    if day is not None and 2 <= ahead <= lead:
        return PROPS_WAIT, (f"the books' player props for this game are bought {words}, and its parlays are "
                            f"built from them once the books post them")
    return PROPS_NONE, ("no book has priced a player prop in this game yet, and its parlays are built from "
                        "them once one does")


def _wait_note(n: int, words: str) -> str:
    """A game short of THREE_MIN while its props are still to be bought: how
    many it has, and when the rest come (`props_note`)."""
    return f"{n} of {THREE_MIN}: {words}" if n else words


def build(board: dict, sport: str, now=None) -> dict:
    """{"sport", "date", "games": [...], "counts"} for every game on the
    board still to play."""
    sp = str(sport or "").lower()
    games = [g for g in board.get("games") or [] if isinstance(g, dict) and g.get("home") and g.get("away")]
    legs = enrich(legs_for(board, sp, now), board)
    # Every priced scorer down to the fill's floor (SCORER_FILL_FLOOR): those at
    # SCORER_FLOOR are the research's to read, the rest only fill (`stand_ins`).
    floor = SCORER_FLOOR.get(sp, 0.25)
    every_scorer = enrich(scorer_legs(board, sp, now, floor=min(floor, SCORER_FILL_FLOOR.get(sp, floor))), board)
    priced = [l for l in every_scorer if float(l.get("p") or 0) >= floor]
    # THE RESEARCH READS EVERY PRICED SCORER (`research_scorers`): the ones it
    # makes a case for are the touchdown pairs' legs.
    census: dict = {}
    scorers, _ = research_scorers(priced, board, games, sp, census)
    spare = stand_ins(every_scorer, scorers, board, games, sp) if sp in SCORER_MARKETS else []
    by_game: dict = {}

    def slot(g):
        return by_game.setdefault(game_label(g), {"g": g, "legs": [], "scorers": [], "spare": [], "priced": 0})
    for leg in legs:
        g = _game_of(leg, games)
        if g:
            slot(g)["legs"].append(leg)
    for leg in priced:
        g = _game_of(leg, games)
        if g:
            slot(g)["priced"] += 1
    for leg in scorers:
        g = _game_of(leg, games)
        if g:
            slot(g)["scorers"].append(leg)
    for leg in spare:
        g = _game_of(leg, games)
        if g:
            slot(g)["spare"].append(leg)
    out_games = []
    priced_n = _priced_counts(board, games)
    scorer_pairs: dict = {}
    for g in games:
        x = by_game.get(game_label(g))
        if not x:
            # Every game still to play has its entry (THREELEG3): its report's
            # picks and the game's props under LEG_FLOOR fill it (`from_report`).
            if game_started(g, now):
                continue
            x = slot(g)
        e = build_game(sp, x["g"], x["legs"], x["scorers"], priced=x["priced"], pairs_out=scorer_pairs,
                       spare=x["spare"])
        why, words = props_note(sp, g, now)
        n_priced = priced_n.get(game_label(g), 0)
        if not (x["legs"] or x["priced"]) and not n_priced:
            # No prop priced at all: when they come, said once (`props_note`).
            e.update(no_props=why, props_note=words, threes_note=words)
            e.pop("scorers_note", None)
        elif why == PROPS_WAIT and len(e["threes"]) < THREE_MIN and n_priced < PROPS_BOUGHT_MIN:
            # A prop or two on file, the game's own not bought yet (19 November:
            # nine of the NFL's Sunday games read "too few props" on a Thursday).
            # A game whose props are bought (PROPS_BOUGHT_MIN) is short for a
            # reason of its own, and its report says it (`from_report`).
            e.update(no_props=why, props_note=words, threes_note=_wait_note(len(e["threes"]), words))
        out_games.append(e)
    # Every scorer pair each game could post, for the report stage (`report_only`): working state.
    if scorer_pairs:
        board[SCORER_PAIRS_KEY] = scorer_pairs
    else:
        board.pop(SCORER_PAIRS_KEY, None)
    return {"sport": sp, "date": board.get("date") or "", "games": out_games,
            "take_edge": TAKE_EDGE, "leg_floor": LEG_FLOOR, "three_floor": THREE_FLOOR,
            "counts": {"games": len(out_games), "threes": sum(len(x["threes"]) for x in out_games),
                       # Games with no prop priced yet (`props_note`), each kind.
                       "no_props": {k: n for k in (PROPS_WAIT, PROPS_NONE)
                                    if (n := sum(1 for x in out_games if x.get("no_props") == k))},
                       "paper_threes": sum(len(x.get("paper_threes") or []) for x in out_games),
                       "scorers": sum(len(x["scorers"]) for x in out_games),
                       # Tickets that filled a game up to THREE_MIN (`tickets_of`), and
                       # scorer pairs up to SCORER_PER_GAME (`stand_ins`).
                       "filled_threes": sum(1 for x in out_games for t in x["threes"] if t.get("filled")),
                       "filled_scorers": sum(1 for x in out_games for t in x["scorers"] if t.get("stand_ins")),
                       # One-club tickets (`choose`), each saying why it is one.
                       "one_club_threes": sum(one_club(t) for x in out_games for t in x["threes"]),
                       "one_club_scorers": sum(one_club(t) for x in out_games for t in x["scorers"]),
                       # The one-club bar in force (`side_bar`): the record's, or the defaults.
                       "side_bar": dict(zip(("edge", "research", "fitted"), side_bar()),
                                         **({"error": SIDE_BAR_ERROR} if SIDE_BAR_ERROR else {})),
                       # The weight a positive link between legs carries (`link_weight`).
                       "link_weight": dict({"weight": link_weight()}, **({"error": LINK_ERROR} if LINK_ERROR else {})),
                       # The legs' learned correction in force (engine/legfit), each kind.
                       "leg_fit": _leg_fit_census(sp)},
            # WHY A PRICED SCORER WAS NO LEG (`research_scorers`), football only.
            **({"research_census": dict(sorted(census.items(), key=lambda kv: -kv[1])),
                "scorers_priced": len(priced), "scorers_researched": len(scorers)}
               if sp in RESEARCH_SPORTS else {}),
            "note": ("Every ticket here is tracked and graded on the record, staked at nothing: same-game "
                     "parlays have lost money on our record so far, because a book's same-game price "
                     "takes more than the link between our picks has paid. Take one only at its price "
                     "or better.")}


def attach(board: dict, sport: str) -> dict:
    """Hang each game's parlays on the board as `game_parlays` (a paid
    key, engine/gate.PAID_KEYS). Never raises.

    ONCE, WHILE THE POOL IS THERE. College football builds them before its
    report and again from the parlay hook after `potd.attach` has taken the
    Most Likely pool (`pool_legs`); the second pass would build from fewer
    legs and replace the first. A build made with the pool stands."""
    from .potd import POOL_KEY
    if str(sport or "").lower() not in SPORTS:
        return board
    have = board.get("game_parlays")
    if isinstance(have, dict) and have.get("pooled") and POOL_KEY not in board:
        return board
    # THE REPORTS' TICKETS STAND (GPLEGS1): once a board's reports have built
    # its three-leg tickets from their own picks (`report_only` marks it), a
    # later pass of this hook (college's, after its report) builds nothing.
    if isinstance(have, dict) and have.get("from_reports"):
        return board
    try:
        board["game_parlays"] = build(board, sport)
        if POOL_KEY in board:
            board["game_parlays"]["pooled"] = True
    except Exception as exc:                                 # noqa: BLE001
        board["game_parlays"] = {"sport": sport, "games": [], "note": f"the game parlays did not build: {exc}"}
    return board


def for_game(board: dict, home: str, away: str) -> dict | None:
    """One game's parlays off a built board, or None."""
    for x in ((board or {}).get("game_parlays") or {}).get("games") or []:
        if x.get("home") == home and x.get("away") == away:
            return x
    return None


# --- the report's own picks are the legs ------------------------------------------------------
# THE PARLAYS ARE MADE OF THE REPORT'S PICKS (GPLEGS1; Ethan, 2026-11-17, two
# screenshots of How our reports did, Monday's NBA: picks 4 of 5 and parlays 0
# of 3, picks 6 of 7 and parlays 1 of 6: "how are we hitting so many picks
# without winning any parlays, but we're still using those picks? That doesn't
# make any sense, so fix that").
#
# They were not using those picks. A game's tickets were built before its
# report, from every prop the board priced at 60% or better (`legs_for`), and
# on the record more than half their legs were no pick of the report's: 50 of
# Monday's 90 NBA legs, all 495 of the NFL's week. The report's own picks hit
# 41 of 62 that night (75% as legs), the others 62%; Rockets at Heat's four
# picks on its tickets all hit, and each ticket lost on a leg the report never
# picked (Bam Adebayo over 0.5 threes twice). Built from the picks alone, that
# night's tickets would have hit 7 of 25 where they hit 4 of 30.
#
# So a game's three-leg tickets are built inside its report, once the report's
# picks are known (engine/gamereport.finish), from those picks and no other
# leg: the same leg (its chance with the league's learned correction, the 60%
# floor, the -250 cap, the injury report, the clash rules, the two sides),
# only now the report's picks first. A report whose picks make fewer than two
# tickets fills them from the game's other priced props (THREELEG1), each saying
# so, and a game no report rebuilt posts none (`report_only`). The scorer pairs are the touchdown
# research's own and are built with the board; `report_only` only puts the ones a game posted last
# build first (ZQ, below).
#: What a game's entry says its three-leg legs are (`from_report`).
LEGS_FROM_REPORT = "report"
#: Why a game no report rebuilt posts no three-leg ticket (`report_only`).
NO_REPORT_NOTE = "the parlays use only a game report's own picks, and this game's report did not build"
#: The legs of the board this process last read (`_board_legs`): read once a build, not once a game.
_BOARD_LEGS: dict = {}


# --- a posted ticket stays until a leg breaks (ZQ) ----------------------------------------------
# Ethan, 2026-11-20, on How our reports did rows reading "Parlays 0 of 28" and
# "1 of 42": "why do we have 30 parlays being made per game?? There should only
# be 3 parlays made per game". Each build chose a game's tickets afresh, and a
# line moving a point reordered them: the board posted another set, the journal
# kept every one, and a reader who bet Thursday's tickets found others on
# Saturday. The tickets a game posted last build are tried first (`choose`
# ``keep``) and posted again while each is still one this build would make;
# only a place one leaves is filled afresh. The report stage reads them from
# the file engine/reportkeep writes at the end of every report stage (each game
# still to play, as the board posted it), before any report is written.
#: Where the report stage puts each game's tickets as the last build posted
#: them (`posted_from`): an underscore key, the build's own working state, which
#: engine/gate.publish never writes.
POSTED_KEY = "_gp_posted"
#: Every scorer pair each game could post this build (`build`), for
#: `report_only` to choose again with the posted ones first: working state too.
SCORER_PAIRS_KEY = "_gp_scorer_pairs"
#: The kinds a game posts and the lists its entry holds each in (a size on
#: paper keeps its own list).
POSTED_LISTS = {"threes": ("threes", "paper_threes"), "scorers": ("scorers",)}


def posted_from(kept_file) -> dict:
    """{game key (reportlog.game_key): {kind: [identity, ...]}}: each game still
    to play as the last build posted its tickets, in order, read from the file
    engine/reportkeep keeps. {} with no file; never raises."""
    try:
        from .reportlog import read
        games = read(kept_file).get("games")
    except Exception:                                        # noqa: BLE001
        return {}
    out: dict = {}
    for k, rec in (games.items() if isinstance(games, dict) else ()):
        gp = rec.get("parlays") if isinstance(rec, dict) else None
        if not isinstance(gp, dict):
            continue
        out[k] = {kind: [ident(t) for name in lists for t in gp.get(name) or []
                         if isinstance(t, dict) and len(t.get("legs") or []) >= 2]
                  for kind, lists in POSTED_LISTS.items()}
    return out


def posted_for(board: dict, game: dict) -> dict:
    """The game's tickets as the last build posted them ({kind: [identity]}),
    when the report stage has read them (POSTED_KEY); {} otherwise."""
    from .reportlog import game_key
    posted = (board or {}).get(POSTED_KEY)
    return (posted.get(game_key(game or {})) or {}) if isinstance(posted, dict) else {}


def _turnover(x: dict, mine: dict) -> tuple[int, int]:
    """(posted again, replaced): how many of the tickets the game posted last
    build it posts again now, by identity, and how many it no longer posts."""
    kept = gone = 0
    for kind, lists in POSTED_LISTS.items():
        now = {ident(t) for name in lists for t in x.get(name) or [] if isinstance(t, dict)}
        for k in mine.get(kind) or []:
            if tuple(tuple(v) for v in k) in now:
                kept += 1
            else:
                gone += 1
    return kept, gone


def _pick_key(b: dict) -> tuple:
    """A pick or a leg as one bet: who, the market, the side, the line."""
    from .gameresults import norm
    side = str((b or {}).get("side") or "").upper()
    side = {"YES": "OVER", "Y": "OVER", "NO": "UNDER", "N": "UNDER"}.get(side, side)
    line = (b or {}).get("line")
    try:
        line = None if line in (None, "") else round(float(line), 2)
    except (TypeError, ValueError):
        line = None
    return (norm(str((b or {}).get("player") or "")), str((b or {}).get("market") or "").lower(), side, line)


def _player_pick(b) -> bool:
    """A report's pick on a player's line (engine/reportbets.bets_of): not a game bet, which a report's
    item flags ``game: True`` and its listed row ``kind: "game"``. A row lifted onto the board carries its
    game's label under ``game`` ("WAS@NYG", reportbets.attach): a label is no flag, and read as one it
    dropped every pick of the report."""
    return (isinstance(b, dict) and bool(b.get("market")) and b.get("game") is not True
            and b.get("kind") != "game")


def _board_legs(board: dict, sport: str, now=None, floor: float = FILL_LEG_FLOOR) -> list[dict]:
    """Every leg the board offers down to ``floor`` (FILL_LEG_FLOOR: `legs_for`,
    `enrich`), read once a build and shared by its reports: the same rows, so
    the same legs. A report's tickets that clear THREE_FLOOR take the ones at
    LEG_FLOOR. At floor 0 (`_picks_priced`, the heartbeat's count of a short
    game's picks) every priced leg at its corrected chance."""
    recs = board.get("recommendations")
    key = (id(board), id(recs), len(recs or []), sport, floor)
    got = _BOARD_LEGS.get(floor)
    if not got or got.get("key") != key:
        legs = legs_for(board, sport, now, floor=floor)
        got = _BOARD_LEGS[floor] = {"key": key, "legs": enrich(legs, board) if floor else legs}
    return got["legs"]


def _picks_priced(board: dict, sport: str, game: dict, want: set, now=None) -> int:
    """How many of a report's picks (`_pick_key`s) the board prices as legs at
    any chance, before the fill's floor: the heartbeat's word on a game short
    of picks (PARLAYWIN1), priced but under 50% once corrected (engine/legfit),
    or not priced at all. Never raises."""
    try:
        return len(want & {_pick_key(l) for l in _board_legs(board, sport, now, floor=0.0)
                           if _game_of(l, [game])})
    except Exception:                                        # noqa: BLE001
        return 0


#: What became of a report's player pick as a parlay leg (`_picks_census`).
PICK_FATES = ("strong", "fill", "low", "no_parlay", "benched", "other_line", "matchup_only", "scorer_only",
              "refused_out", "refused_book", "refused_price", "refused_edge", "refused", PROPS_WAIT, "absent")


def _refused_why(rows: list) -> str:
    """Why no leg source will use the rows that hold a pick, as a fate: the
    player is ruled out (``refused_out``), no real book prices it
    (``refused_book``: not bettable, a proxy, no price), its price is past the
    cap or the long-price limit (``refused_price``: likely.HEAVIEST_PRICE,
    stakeplan.priced_out), or its number is one the Edge path refuses
    (``refused_edge``: `credible_row`); ``refused`` for anything else.

    A ROW WITH A REAL PRICE SPEAKS FIRST (20 November 2026). A pick is held by
    every list that carries it (Most Likely, the pool, the priced props), and
    the first cut said "no real book" when any one of those rows was a
    projection with no market or the proxy stand-in, ahead of the reason its
    priced row was turned down: the NFL's census read 16 of 42 picks
    refused_book. "No real book" now means none of its rows has a real price;
    a ruled-out player is said first whatever the rows."""
    from .likely import HEAVIEST_PRICE
    from .stakeplan import priced_out
    why, priced = set(), False
    for r in rows or []:
        if str(r.get("injury_status") or "").strip().upper() in _OUT:
            why.add("out")
            continue
        try:
            odds = int(float(r.get("odds")))
        except (TypeError, ValueError):
            odds = None
        if (odds is None or r.get("bettable") is False or r.get("has_market") is False
                or str(r.get("book") or "").strip().lower() in ("", "proxy")):
            continue                                     # says nothing of a priced row's reason
        priced = True
        if odds < HEAVIEST_PRICE or priced_out("edge", odds):
            why.add("price")
        elif not credible_row(r):
            why.add("edge")
    if rows and not priced:
        why.add("book")
    return next((f"refused_{w}" for w in ("out", "book", "price", "edge") if w in why), "refused")


def _book_gap(row: dict) -> str:
    """What a row lacks for a real price (`_refused_why`'s ``refused_book``),
    first by this order: the proxy stand-in, no book, no market behind the
    number, a book that cannot be bet, no price."""
    book = str(row.get("book") or "").strip().lower()
    if book == "proxy":
        return "proxy"
    if not book:
        return "no_book"
    if row.get("has_market") is False:
        return "no_market"
    if row.get("bettable") is False:
        return "not_bettable"
    try:
        int(float(row.get("odds")))
    except (TypeError, ValueError):
        return "no_odds"
    return "other"


def _picks_census(board: dict, sport: str, game: dict, picks: list, now=None,
                  book_why: dict | None = None) -> dict:
    """What became of each of a report's player picks as a parlay leg, as counts
    (PICKLEGS1, 2026-11-19: three Sunday games' reports carried 12 picks and the
    board priced 3 of them as legs, and nothing said what the other nine were).
    No pick rides here; the heartbeat adds a league's up (launch._board_counts):

      strong        a leg at LEG_FLOOR or better, what a ticket is made of;
      fill          a leg the fill may take (FILL_LEG_FLOOR up to LEG_FLOOR);
      low           priced as a leg, under FILL_LEG_FLOOR once corrected (legfit);
      no_parlay     a market no parlay carries (tackles, sacks, kicking);
      benched       a market benched from stakes (stakeplan.MARKET_BENCH);
      other_line    the board's legs carry the player's market and side at
                    another number only;
      matchup_only  a matchup pick's own row and no leg source's
                    (board["matchup_picks"]);
      scorer_only   a scorer the touchdown field prices and no leg source does;
      refused…      a row a leg source holds and will not use, by why
                    (`_refused_why`): ruled out, no real book, past the price
                    cap, a number the Edge path refuses, or anything else;
      props_not_bought  no real book because the game's props are not bought
                    yet (fewer than PROPS_BOUGHT_MIN priced, the builder's own
                    rule): Monday night's on a Friday, which says nothing of
                    the pick (20 November 2026: the NFL read 19 of 47 picks
                    "no real book" with Monday's game still to buy);
      absent        on none of the board's lists by this number.

    ``book_why``, when given, counts each ``refused_book`` pick by the list
    that held it and what its row lacked (`_book_gap`), "recommendations:
    no_market" and the like: the NFL read 19 of 47 picks refused_book with
    its games' props bought (20 November 2026), and the count said no more.

    {} when the report has no player pick. Never raises."""
    try:
        from .parlays import parlay_market
        from .potd import POOL_KEY
        from .stakeplan import market_benched
        want = {_pick_key(b) for b in picks or [] if _player_pick(b)}
        want.discard(("", "", "", None))
        if not want:
            return {}
        legs = {}
        for l in _board_legs(board, sport, now, floor=0.0):
            if _game_of(l, [game]):
                k = _pick_key(l)
                legs[k] = max(float(l.get("p") or 0), legs.get(k, 0.0))
        loose = {k[:3] for k in legs}

        def keys(rows):
            return {_pick_key(r) for r in rows or [] if isinstance(r, dict)}
        held: dict = {}
        first_list: dict = {}
        for lst in ("most_likely", POOL_KEY, "recommendations"):
            for r in board.get(lst) or []:
                if isinstance(r, dict) and _pick_key(r) in want:
                    held.setdefault(_pick_key(r), []).append(r)
                    first_list.setdefault(_pick_key(r), (lst, r))
        matchup = set()
        for g in board.get("matchup_picks") or []:
            if isinstance(g, dict):
                matchup |= keys(g.get("td")) | keys(g.get("props"))
        field = {k[:2] for k in keys(board.get("td_field")) | keys(board.get("longshot_watch"))}
        unbought = _priced_counts(board, [game]).get(game_label(game), 0) < PROPS_BOUGHT_MIN
        out: dict = {}
        for k in want:
            if k in legs:
                fate = "strong" if legs[k] >= LEG_FLOOR else "fill" if legs[k] >= FILL_LEG_FLOOR else "low"
            elif not parlay_market(k[1]):
                fate = "no_parlay"
            elif market_benched(sport, k[1]):
                fate = "benched"
            elif k[:3] in loose:
                fate = "other_line"
            elif k in held:
                fate = _refused_why(held[k])
                if fate == "refused_book" and unbought:
                    fate = PROPS_WAIT
                if fate == "refused_book" and book_why is not None:
                    lst, row = first_list[k]
                    label = f"{'pool' if lst == POOL_KEY else lst}:{_book_gap(row)}"
                    book_why[label] = book_why.get(label, 0) + 1
            elif k in matchup:
                fate = "matchup_only"
            elif k[:2] in field:
                fate = "scorer_only"
            else:
                fate = "absent"
            out[fate] = out.get(fate, 0) + 1
        return out
    except Exception:                                        # noqa: BLE001
        return {}


def _report_note(n_ok: int, n_picks: int, made: dict) -> str:
    """Why a game's report made fewer than THREE_MIN three-leg tickets, after
    "No three-leg parlay:" when it made none: its own picks (``n_ok`` of
    ``n_picks`` clearing LEG_FLOOR) and every other prop of the game's the fill
    could try (`tickets_of`) were too few, or none of them fit together."""
    n, wider = len(made["threes"]), int(made.get("wider", n_ok))
    more = max(0, wider - n_ok)
    head = f"{n} of {THREE_MIN}: " if n else ""
    picks = "it has no pick on a player's line" if not n_picks else \
        (f"{n_ok} of its {n_picks} pick{'' if n_picks == 1 else 's'} {'is' if 1 in (n_ok, n_picks) else 'are'} "
         f"at {LEG_FLOOR:.0%} or better")
    whose = (f"this report's picks ({picks})"
             + (f" and the {more} more the game could add (the report's other picks at {FILL_LEG_FLOOR:.0%} or "
                f"better, the board's other props at {FILL_OTHER_FLOOR:.0%} or better)" if more else ""))
    if wider < 3:
        got = f"only {wider} leg{'' if wider == 1 else 's'}" if wider else "none"
        return head + f"a three-leg parlay takes three legs, and {whose} make {got}"
    return (head + f"{whose} make no {'more ' if n else ''}three that fit together without a conflict and "
            f"reach {LONG_WORDS} by our numbers{_uses_words(made)}")


def from_report(board: dict, sport: str, game: dict, picks: list, now=None) -> dict | None:
    """Rebuild one game's three-leg tickets on the board from its report's own
    picks (``picks``: engine/reportbets.bets_of, what the report shows), in
    place, and return the game's entry; None where the board has none. A
    started game's kept entry (engine/reportkeep) is left as it was.

    THE REPORT'S PICKS FIRST, THREE TICKETS A GAME (THREELEG1, 2026-11-19;
    ZR, 2026-11-20). The tickets are the report's picks (GPLEGS1); where they
    make fewer than THREE_MIN, the game's other priced props fill the rest
    (`tickets_of` ``extra``), each such ticket naming the legs the report did
    not pick: one other prop a ticket beside two of the report's picks; where
    the report has too few picks a parlay can use, the Most Likely board's
    picks for the game in their place (`board_pick`, BOARDFILL1); and last the
    game's best props, around whatever picks it has."""
    sp = str(sport or "").lower()
    if sp not in SPORTS or not isinstance(board.get("game_parlays"), dict):
        return None
    x = for_game(board, (game or {}).get("home"), (game or {}).get("away"))
    if x is None or x.get("kept"):
        return x
    want = {_pick_key(b) for b in picks or [] if _player_pick(b)}
    want.discard(("", "", "", None))
    # The game's priced props down to FILL_LEG_FLOOR (THREELEG2): its picks at
    # LEG_FLOOR make the tickets that clear THREE_FLOOR; the rest only fill.
    mine = [l for l in _board_legs(board, sp, now) if _game_of(l, [game])]
    legs = [l for l in mine if _pick_key(l) in want and float(l.get("p") or 0) >= LEG_FLOOR]
    picked = {_leg_id(l) for l in mine if _pick_key(l) in want}
    strong = {_leg_id(l) for l in legs}
    # THE FILL TAKES THE REPORT'S OWN PICKS FIRST, AND ANOTHER PROP ONLY AT
    # FILL_OTHER_FLOOR, ONE A TICKET AT MOST (PARLAYWIN1, 2026-11-19). A pick
    # under LEG_FLOOR is still the report's (the NBA's and NHL's Most Likely
    # picks priced at 45-60% hit 63% and 61% on the record, above what we said);
    # a prop the report never picked hit 62% as a leg against 75% for its picks
    # (step WH), so it rides only beside two of the report's (`tickets_of`).
    extra = [l for l in mine if _leg_id(l) not in strong
             and (_leg_id(l) in picked or float(l.get("p") or 0) >= FILL_OTHER_FLOOR)]
    # The tickets it posted last build first, each while it is still one of these (ZQ, `choose`).
    made = tickets_of(sp, game, legs, extra=extra, picks=picked, posted=posted_for(board, game))
    chosen, n_threes, n_pool = made["threes"], made["threes_fit"], made["pool"]
    x["threes"] = chosen
    x.pop("paper_threes", None)
    x.pop("threes_paper", None)
    x.update(legs_read=n_pool, threes_considered=n_threes, legs_from=LEGS_FROM_REPORT, report_picks=len(want),
             legs_wider=int(made.get("wider") or 0),
             # The report's own picks among them: a ticket takes two at least (the heartbeat's "few_picks").
             legs_own=int(made.get("wider_own") or 0))
    if len(chosen) < THREE_MIN and int(made.get("wider_own") or 0) < 2:
        # …and how many of its picks the board prices at any chance (`_picks_priced`).
        x["picks_priced"] = _picks_priced(board, sp, game, want, now)
    else:
        x.pop("picks_priced", None)
    # What became of each of its picks as a leg, as counts (`_picks_census`),
    # and of those no real book prices, which list held each and what it lacked.
    book_why: dict = {}
    fates = _picks_census(board, sp, game, picks, now, book_why=book_why)
    if fates:
        x["pick_fates"] = fates
    else:
        x.pop("pick_fates", None)
    if book_why:
        x["pick_book_why"] = book_why
    else:
        x.pop("pick_book_why", None)
    # What a game short of its three had to fill from (`tickets_of`): counts, no leg.
    for k in ("fill_fit", "fill_clear"):
        if made.get(k) is None:
            x.pop(k, None)
        else:
            x[k] = int(made[k])
    x.pop("rebuild_error", None)
    if made["filled"]:
        x["threes_filled"] = made["filled"]
    else:
        x.pop("threes_filled", None)
    for key, k in (("threes_board_filled", "board_filled"), ("threes_props_filled", "props_filled")):
        if made.get(k):
            x[key] = int(made[k])
        else:
            x.pop(key, None)
    # A game with no prop priced yet keeps the build's word on when they come
    # (THREELEG3, `props_note`), as does one short of its three while its props
    # are still to be bought; a prop priced since, and the game is read again.
    waiting = bool(x.get("no_props")) and (not made.get("wider") or (
        x["no_props"] == PROPS_WAIT and len(chosen) < THREE_MIN))
    if not waiting:
        x.pop("no_props", None)
        x.pop("props_note", None)
    if waiting:
        x["threes_note"] = _wait_note(len(chosen), x.get("props_note") or "")
    elif len(chosen) < THREE_MIN:
        x["threes_note"] = _report_note(n_pool, len(want), made)
        if props_note(sp, game, now)[0] == PROPS_WAIT:
            # Its props bought days ahead (EARLYPROPS1): the books post more as it nears.
            x["threes_note"] += ("; the books post more of this game's props as it nears, and its parlays "
                                 "are read again as they do")
    else:
        x.pop("threes_note", None)
    return x


def report_only(board: dict) -> int:
    """After a board's reports: a game no report rebuilt (`from_report`) posts
    no three-leg ticket, since its legs would be no report's picks, and every
    count is read again. A started game's kept entry stands. Returns the games
    cleared.

    And each game's scorer pairs are chosen again with the ones it posted last
    build first (ZQ, `choose`), from every pair it could post this build
    (SCORER_PAIRS_KEY); each game the last build posted for says how many of
    those it posts again and how many it replaced (``posted_kept``,
    ``posted_replaced``: counts for the heartbeat)."""
    gp = (board or {}).get("game_parlays")
    if not isinstance(gp, dict):
        return 0
    n = 0
    posted = board.get(POSTED_KEY) if isinstance(board.get(POSTED_KEY), dict) else {}
    pairs = board.pop(SCORER_PAIRS_KEY, None) or {}
    researched = str(gp.get("sport") or "").lower() in RESEARCH_SPORTS
    for x in gp.get("games") or []:
        if not isinstance(x, dict) or x.get("kept"):
            continue
        if x.get("legs_from") != LEGS_FROM_REPORT:
            if x.get("threes"):
                n += 1
            x["threes"] = []
            x["legs_from"] = LEGS_FROM_REPORT
            x["threes_note"] = NO_REPORT_NOTE
        mine = posted.get(f"{x.get('away')}@{x.get('home')}|{str(x.get('date') or '')[:10]}")
        if not isinstance(mine, dict):
            x.pop("posted_kept", None)
            x.pop("posted_replaced", None)
            continue
        cands = pairs.get(game_label(x))
        if mine.get("scorers") and cands:
            x["scorers"] = [dict(t, legs=[slim(l) for l in t["legs"]])
                            for t in choose(cands, SCORER_PER_GAME, rank=scorer_rank(researched),
                                            researched=researched, keep=mine["scorers"])]
            # Never fewer than the build chose (`choose`); a game short of its three says how many it has.
            note = str(x.get("scorers_note") or "")
            if len(x["scorers"]) >= SCORER_PER_GAME:
                x.pop("scorers_note", None)
            elif re.match(r"\d+ of \d+: ", note):
                x["scorers_note"] = f"{len(x['scorers'])} of {SCORER_PER_GAME}: {note.split(': ', 1)[1]}"
        x["posted_kept"], x["posted_replaced"] = _turnover(x, mine)
    board.pop(POSTED_KEY, None)
    gp["from_reports"] = True
    c = gp.get("counts")
    if isinstance(c, dict):
        live = [x for x in gp.get("games") or [] if isinstance(x, dict)]
        c["threes"] = sum(len(x.get("threes") or []) for x in live)
        c["paper_threes"] = sum(len(x.get("paper_threes") or []) for x in live)
        c["one_club_threes"] = sum(one_club(t) for x in live for t in x.get("threes") or [])
        c["scorers"] = sum(len(x.get("scorers") or []) for x in live)
        c["filled_scorers"] = sum(1 for x in live for t in x.get("scorers") or [] if t.get("stand_ins"))
        c["one_club_scorers"] = sum(one_club(t) for x in live for t in x.get("scorers") or [])
        c["from_report"] = sum(x.get("legs_from") == LEGS_FROM_REPORT for x in live)
    return n


def summary(gp: dict) -> str:
    """The build log's line."""
    c = (gp or {}).get("counts") or {}
    return (f"  Game parlays: {c.get('threes', 0)} three-leg and {c.get('scorers', 0)} scorer pair(s) "
            f"across {c.get('games', 0)} game(s); one club's alone: {c.get('one_club_threes', 0)} three-leg, "
            f"{c.get('one_club_scorers', 0)} pair(s)" + _bar_words(c.get("side_bar")))


def _bar_words(sb) -> str:
    """The one-club bar in force, for the build log (`side_bar`)."""
    if not isinstance(sb, dict) or sb.get("edge") is None:
        return ""
    if sb.get("error"):
        why = f"the defaults: its fit could not be read ({sb['error']})"
    else:
        why = "set by the record" if sb.get("fitted") else f"the defaults until {SIDE_MIN_N} of each settle"
    return (f"; one-club bar {float(sb['edge']) * 100:.0f} points, {int(sb.get('research') or 0)} research "
            f"points ({why})")


def journal_rows(gp: dict) -> list[dict]:
    """Every leg of every posted ticket, for the paper bucket the tickets
    grade from (engine/parlayledger, `parlay_leg`)."""
    seen, out = set(), []
    for x in (gp or {}).get("games") or []:
        # A started game's tickets, kept after its start (engine/reportkeep):
        # their legs were journaled before it, or not at all.
        if isinstance(x, dict) and x.get("kept"):
            continue
        # Tickets on paper too (`paper_threes`): graded like every other.
        for t in (x.get("threes") or []) + (x.get("paper_threes") or []) + (x.get("scorers") or []):
            for l in t.get("legs") or []:
                k = _leg_id(l)
                if k in seen or l.get("_game_leg"):
                    continue
                seen.add(k)
                out.append({"player": l.get("player"), "team": l.get("team"), "opponent": l.get("opponent"),
                            "market": l.get("market"), "side": l.get("side"), "line": l.get("line"),
                            "odds": l.get("odds"), "book": l.get("book"), "model_prob": l.get("p"),
                            "game_date": l.get("game_date"), "home": l.get("home"), "away": l.get("away"),
                            "position": l.get("position") or ""})
    return out
