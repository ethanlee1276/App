"""Each game's parlays: four 3-leg parlays and three 2-leg touchdown parlays (2026-11-14).

Ethan, 2026-11-14, of the research reports he writes for himself ("Nabers 5+
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

THE LEGS. Only numbers the board already prices for a reader: the game's
Most Likely picks, its Edge picks, and every other prop it priced at a named
book (engine/twoleg's legs and `priced_legs` — each a real price, none
started, none held), at LEG_FLOOR or better
(his reports' bar: "they sit under the 65% hit-rate floor, so they don't
qualify for the parlay"; ours is a little lower, and every leg shows its
own chance). Never a past-the-cap row (Ethan, 09-01: "not a parlay leg"),
never a man the board already dropped for an injury, and never a tackle,
sack or kicking prop (Ethan, 2026-11-14: "i dont wanna use tackle picks or
anything like that. and not kicker points either" — parlays.NO_PARLAY_MARKETS,
refused where every leg is made, twoleg._leg).

NO CONFLICTS. Every pair of legs passes the clash taxonomy
(engine/parlays.relate): no player twice, no quarterback against his own
receiver, no quarterback and a back of one team (they want opposite
scripts), no two unders. And no leg that needs points beside one that needs
a quiet game (`script_need`, the board's own game-script view, js/app.js
scriptNeed): a quarterback's yards and a touchdown want points. Two legs
that want opposite leads (a back's carries want his team ahead, a
receiver's catches want it chasing) share a ticket the way his own reports
pair them, priced as unrelated and said (OPPOSED_SCRIPT_RHO).
One exception his reports make and the doctrine does not: two teammates'
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

FOUR A GAME, FOUR IDEAS. The likeliest first; each next one shares at most
MAX_SHARED leg with every ticket before it.

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

import itertools

#: The leagues this runs for: every board with player props.
SPORTS = ("nfl", "cfb", "nba", "cbb", "wnba", "nhl", "mlb")
#: Tickets a game posts.
THREE_PER_GAME = 4
SCORER_PER_GAME = 3
#: The least chance a 3-leg ticket's leg may have.
LEG_FLOOR = 0.60
#: The least chance a scorer leg may have, by league.
SCORER_FLOOR = {"nfl": 0.25, "cfb": 0.30, "nhl": 0.25}
#: How many legs of a game are tried (the likeliest), and scorers.
MAX_POOL, MAX_SCORERS = 14, 8
#: A ticket's least price is this much over our fair price: the edge a
#: ticket must leave at the book's price to be worth taking.
TAKE_EDGE = 0.05
#: Each next ticket of a game shares at most this many legs with every
#: ticket before it — and when that leaves fewer than a game's four, a
#: second pass lets a ticket differ from the others by one leg.
MAX_SHARED = 1
#: No leg rides on more than this many of a game's tickets.
MAX_USES = 2
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
#: three-leg tickets across 13 games, where he asked for four a game. The
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
SOURCES = {"three": "game_three", "scorers": "game_td"}
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
        leg = T._leg(r, r.get("hit_prob"), "priced")
        if leg and not T._started(leg, now):
            out.append(leg)
    return out


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


def legs_for(board: dict, sport: str, now=None) -> list[dict]:
    """The board's priced picks as legs — Most Likely, Edge, the Most Likely
    rows its seat caps dropped (`pool_legs`) and every other prop it priced
    at a named book (`priced_legs`), the more likely copy of a pick kept —
    at LEG_FLOOR or better."""
    from . import twoleg as T
    got: dict = {}
    for get in (T.likely_legs, T.edge_legs, pool_legs, priced_legs):
        try:
            rows = get(board, sport, now)
        except Exception:                                    # noqa: BLE001
            rows = []
        for leg in rows:
            # Player props only: a game line's leg journals and grades on
            # another path, and his reports' tickets are props.
            if not leg or leg.get("_game_leg") or float(leg.get("p") or 0) < LEG_FLOOR:
                continue
            leg = _norm_side(leg)
            k = (leg.get("player"), leg.get("market"), str(leg.get("side") or "").upper(), leg.get("line"))
            if k not in got or leg["p"] > got[k]["p"]:
                got[k] = leg
    return list(got.values())


def scorer_legs(board: dict, sport: str, now=None) -> list[dict]:
    """Every priced scorer of the slate as a leg: the touchdown model's
    whole field (`td_field`), college's, or hockey's goal props — each at
    the league's SCORER_FLOOR or better, still to play."""
    from . import twoleg as T
    markets = SCORER_MARKETS.get(sport) or ()
    if not markets:
        return []
    floor = SCORER_FLOOR.get(sport, 0.25)
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
    return out


# --- the touchdown pairs' research ------------------------------------------------------------
#: TOUCHDOWN PAIRS FROM OUR RESEARCH, NOT THE PRICES (2026-11-14). Ethan:
#: "make sure we are making the TD parlays based off reaseerach we do and the
#: breakout canidates and game scripts and all of that and not just based off
#: the player lines". The pairs were the game's likeliest priced scorers,
#: paired by their joint chance — the touchdown model's number, which leans
#: on the points the lines expect and the share the player already has, so
#: the pairs read like the shortest prices on the board. Now each football
#: scorer is first read on the research the site already writes (the case
#: his own words make: "where the lions do bad and bills do good ... figure
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
            script, why = 1, (f"{team} favoured by {margin:g} — a leading team runs the ball, at the goal "
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
    lines += [x for x in mine if "defence ranks" in x]
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
            no("no matchup read on him" if not read else "his read says avoid" if read.get("read") == "avoid"
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


# --- why each leg: the read, the model's own reasons ------------------------------------------
#: The touchdown model's footnotes about its own mechanics — true, and
#: nothing a reader weighs a leg on (engine/touchdowns.td_probability).
_FOOTNOTES = ("Running back:", "Team total:", "Quarterback:", "Depth receiver:", "Share of team TDs from",
              "Scout: ", "Usage is ")
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
    reasons = [str(x) for x in (row or {}).get("reasons") or [] if x
               and not any(str(x).startswith(f) for f in _FOOTNOTES)]
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
    return legs


def _game_of(leg: dict, games: list) -> dict | None:
    pair = {leg.get("home"), leg.get("away")} - {"", None} or {leg.get("team"), leg.get("opponent")} - {"", None}
    for g in games or []:
        if isinstance(g, dict) and {g.get("home"), g.get("away")} == pair:
            return g
    return None


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
        put("points", s, "points — a quarterback's yards rise with his team's score" if up
            else "a low-scoring game for his team")
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
        return False, 0.0, "the same player twice — if he sits, both legs die", ""
    try:
        rel = P.relate(sport, a, b)
    except Exception:                                        # noqa: BLE001
        return False, 0.0, "the pair could not be read", ""
    caveat = ""
    rho = float(rel.rho)
    why = plain(rel.mechanism)
    if rel.verdict in ("kill", "duplicate"):
        same_team = (a.get("team") or "_a") == (b.get("team") or "_b")
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
    for l in legs:
        st = str(l.get("injury_status") or l.get("own_status") or "").upper()
        if st in ("QUESTIONABLE", "GTD", "DAY-TO-DAY"):
            caveats.append(f"{l.get('player')} is listed questionable — confirm he plays before you bet it")
    # CAN A BOOK PAY IT? The most generous same-game price a book plausibly
    # quotes is the legs' product less the doctrine's best-case cut
    # (parlays.BEST_CASE_SGP_TAX); a ticket that needs more than that is
    # read for its read, not bet — his reports' "below that, there is no
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
            "playable": playable, "staked": False, "stake_units": 0.0}


def _leg_id(l: dict) -> tuple:
    return (l.get("player"), l.get("market"), str(l.get("side") or "").upper(), l.get("line"))


#: What a published leg keeps: the card's words, the journal's keys, and a
#: scorer's research (`research`).
LEG_KEYS = ("player", "team", "opponent", "home", "away", "position", "market", "market_label", "side",
            "line", "odds", "book", "p", "why", "injury_status", "game_date", "research", "research_of",
            "research_points")


def slim(leg: dict) -> dict:
    """A leg as the board publishes it (LEG_KEYS)."""
    return {k: leg.get(k) for k in LEG_KEYS if leg.get(k) not in (None, "", [])}


def choose(tickets: list[dict], n: int, rank=None) -> list[dict]:
    """The likeliest first (or by ``rank``, a sort key — the scorer pairs'
    research, `_by_research`); each next one shares at most MAX_SHARED legs
    with every ticket already chosen, and no leg rides on more than
    MAX_USES of them. A second pass, when the first leaves fewer than
    ``n``, lets a ticket share all but one leg."""
    ranked = sorted(tickets, key=rank or (lambda t: (-t["joint"], -(t.get("ev_at_naive") or -9))))
    out: list = []
    uses: dict = {}
    for shared in (MAX_SHARED, None):
        for t in ranked:
            if len(out) >= n:
                return out
            if t in out:
                continue
            ids = {_leg_id(l) for l in t["legs"]}
            limit = shared if shared is not None else len(ids) - 1
            if any(len(ids & {_leg_id(l) for l in c["legs"]}) > limit for c in out):
                continue
            if any(uses.get(i, 0) >= MAX_USES for i in ids):
                continue
            out.append(t)
            for i in ids:
                uses[i] = uses.get(i, 0) + 1
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
    head = (f"Parlay {n}" if kind == "three" else f"{SCORER_WORDS.get(sport, 'Scorer').capitalize()} pair {n}")
    price = (f"{joint:.0%} by our numbers ({float(t.get('independent') or 0):.0%} if the legs were unrelated) · "
             f"fair {t.get('fair_words')} · take it at {t.get('take_words')} or better")
    if t.get("naive_words"):
        price += f" · the legs' own prices multiplied pay {t['naive_words']}, and a book's same-game price pays less"
    legs = [{"pick": pick_words(l), "player": l.get("player"), "team": l.get("team"),
             "price": " ".join(x for x in (_odds_words(l.get("odds")), l.get("book") or "") if x),
             "chance": round(float(l.get("p") or 0), 4), "why": list(l.get("why") or []),
             # A scorer's research case, out of RESEARCH_MAX (`research_scorers`).
             **({"research": int(l["research"]), "research_of": int(l.get("research_of") or RESEARCH_MAX)}
                if l.get("research") is not None else {})}
            for l in t.get("legs") or []]
    script = ""
    if t.get("script"):
        script = f"What it needs: {t['script']}"
        if t.get("script_chance") is not None:
            script += f" — about {float(t['script_chance']):.0%} likely by the lines"
    backs = [f"If {b['for']} is out or his number moves: {pick_words(b['leg'])} "
             f"({_odds_words(b['leg'].get('odds'))}, {float(b['leg'].get('p') or 0):.0%})"
             for b in t.get("backups") or []]
    out = {"title": head, "price_line": price, "legs": legs, "script": script,
           "links": list(t.get("links") or []), "backups": backs, "caveats": list(t.get("caveats") or []),
           "joint": joint, "fair": t.get("fair"), "take": t.get("take")}
    # THE TOUCHDOWN RULE ON A PAIR (decision 1 under RUN_NEXT 00f, Ethan's
    # NFL Bet checking method: an anytime touchdown at 45%, or 40% with a
    # red-zone role). The floor stays where it is; a pair whose two scorers
    # are both 40% or better says so, and one that isn't says that too.
    if kind != "three" and legs and sport in TD_RULE_SPORTS:
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


def build_game(sport: str, game: dict, legs: list[dict], scorers: list[dict],
               priced: int | None = None) -> dict:
    """A game's four 3-leg tickets and three scorer pairs, and why there
    are fewer when there are. ``priced`` is how many priced scorers the game
    had before the research read them (`research_scorers`)."""
    pool = sorted(legs, key=lambda l: -float(l["p"]))[:MAX_POOL]
    memo: dict = {}
    threes = [t for t in (ticket(sport, list(c), game, memo) for c in itertools.combinations(pool, 3)) if t]
    chosen = choose(threes, THREE_PER_GAME)
    for t in chosen:
        t["backups"] = [{"for": b["for"], "leg": slim(b["leg"])} for b in backups(sport, t, pool, game)]
        t["legs"] = [slim(l) for l in t["legs"]]
    out = {"game": game_label(game), "home": game.get("home"), "away": game.get("away"),
           "date": game.get("date") or "", "kickoff": game.get("kickoff") or "",
           "threes": chosen, "legs_read": len(pool), "threes_considered": len(threes)}
    if len(chosen) < THREE_PER_GAME:
        out["threes_note"] = (f"{len(chosen)} of {THREE_PER_GAME}: this game has {len(pool)} pick(s) at "
                              f"{LEG_FLOOR:.0%} or better, and only {len(threes)} three-leg combination(s) of "
                              f"them without a conflict")
    if sport in SCORER_MARKETS:
        researched = sport in RESEARCH_SPORTS
        # THE RESEARCH FIRST (RESEARCH_SPORTS): the strongest cases are the
        # scorers tried, and the pairs are ranked on them; our chance breaks
        # ties. Hockey ranks on the chance.
        sc = sorted(scorers, key=(lambda l: (-int(l.get("research") or 0), -float(l["p"]))) if researched
                    else (lambda l: -float(l["p"])))[:MAX_SCORERS]
        pairs = [t for t in (ticket(sport, list(c), game, memo) for c in itertools.combinations(sc, 2)) if t]
        if researched:
            for t in pairs:
                t["research"] = sum(int(l.get("research") or 0) for l in t["legs"])
        out["scorers"] = choose(pairs, SCORER_PER_GAME, rank=_by_research if researched else None)
        for t in out["scorers"]:
            t["legs"] = [slim(l) for l in t["legs"]]
        out["scorers_read"] = len(sc)
        if researched:
            out["scorers_priced"] = len(sc) if priced is None else int(priced)
        if len(out["scorers"]) < SCORER_PER_GAME:
            floor = f"{SCORER_FLOOR.get(sport, 0.25):.0%}"
            if researched:
                n_priced = out["scorers_priced"]
                out["scorers_note"] = (
                    f"{len(out['scorers'])} of {SCORER_PER_GAME}: {len(sc)} of the {n_priced} priced "
                    f"scorer(s) in this game at {floor} or better carry a research case — a red-zone role "
                    f"and {RESEARCH_MIN} or more of the {RESEARCH_MAX} research points (his team's expected "
                    f"points, the defence he faces, his usage and red-zone work, the matchup read and the "
                    f"game script)")
            else:
                out["scorers_note"] = (f"{len(out['scorers'])} of {SCORER_PER_GAME}: {len(sc)} priced "
                                       f"{SCORER_WORDS.get(sport, 'scorer')}(s) in this game at "
                                       f"{floor} or better")
    else:
        out["scorers"] = []
        out["scorers_note"] = "No scorer market in this league — basketball's books post no anytime scorer"
    return out


def build(board: dict, sport: str, now=None) -> dict:
    """{"sport", "date", "games": [...], "counts"} for every game on the
    board still to play."""
    sp = str(sport or "").lower()
    games = [g for g in board.get("games") or [] if isinstance(g, dict) and g.get("home") and g.get("away")]
    legs = enrich(legs_for(board, sp, now), board)
    priced = enrich(scorer_legs(board, sp, now), board)
    # THE RESEARCH READS EVERY PRICED SCORER (`research_scorers`): the ones it
    # makes a case for are the touchdown pairs' legs.
    census: dict = {}
    scorers, _ = research_scorers(priced, board, games, sp, census)
    by_game: dict = {}

    def slot(g):
        return by_game.setdefault(game_label(g), {"g": g, "legs": [], "scorers": [], "priced": 0})
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
    out_games = []
    for g in games:
        x = by_game.get(game_label(g))
        if not x:
            continue
        out_games.append(build_game(sp, x["g"], x["legs"], x["scorers"], priced=x["priced"]))
    return {"sport": sp, "date": board.get("date") or "", "games": out_games,
            "take_edge": TAKE_EDGE, "leg_floor": LEG_FLOOR,
            "counts": {"games": len(out_games), "threes": sum(len(x["threes"]) for x in out_games),
                       "scorers": sum(len(x["scorers"]) for x in out_games)},
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


def summary(gp: dict) -> str:
    """The build log's line."""
    c = (gp or {}).get("counts") or {}
    return (f"  Game parlays: {c.get('threes', 0)} three-leg and {c.get('scorers', 0)} scorer pair(s) "
            f"across {c.get('games', 0)} game(s)")


def journal_rows(gp: dict) -> list[dict]:
    """Every leg of every posted ticket, for the paper bucket the tickets
    grade from (engine/parlayledger, `parlay_leg`)."""
    seen, out = set(), []
    for x in (gp or {}).get("games") or []:
        for t in (x.get("threes") or []) + (x.get("scorers") or []):
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
