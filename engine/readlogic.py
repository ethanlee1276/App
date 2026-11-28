"""How a matchup read adds its reasons up — one rule for every league (2026-11-14).

Ethan, 2026-11-14: "I feel like with our matchup reports as well, we're kind
of judging too many things off too many factors. Like, for example, this
Duke versus Miami game, Duke's running back has 17 touchdowns, and yet we're
marking him as a bad matchup. But I feel like he's probably their go-to guy
to score. ... yes, Miami's defense is ranked 5th in rushing, but that
doesn't mean that he won't have a single opportunity to score, because the
total's high in that game and it's expecting both teams to score. ... We
need to be more logical with our picks and with our reports and what we're
saying. So we need to go through and audit all of that for every sport".

WHAT THE AUDIT FOUND. Every league's read (engine/gamescan for football,
engine/nba/scan, engine/nhl/scan, engine/mlb/scan) counted its reasons a
point each, so two numbers about ONE thing counted twice:

  * an NFL back's defence by the rushing yards and again by the touchdowns
    it allows to backs; a college back's by its run EPA and again by its
    stuff rate;
  * a basketball defence once for each stat it holds a player down in
    (points and rebounds: two);
  * a hockey defence by the shots and again by the chances it allows;
  * a starting pitcher by the slugging he allows a hitter's side and again
    by his expected ERA.

One strong defence could carry a read to "avoid" by itself, and nothing a
player does himself — the carries he gets, the touchdowns he scores — could
stop it. And the college read never heard the lines at all: its scan was
handed no implied points, so "the total's high" could not count either way.

THREE RULES, kept here so the leagues cannot drift apart again:

1. ONE VOTE A FAMILY (`score`). Each reason is about one thing — the defence
   he faces, the opposing goalie or pitcher, the points the lines expect, a
   blowout, the weather, the schedule, his own role moving, a teammate out,
   the park, the umpire. A family votes once, the way most of its reasons
   lean; a reason given no family votes alone, as before.

2. A FEATURED PLAYER IS NEVER "AVOID" (`ladder`). His share of the work is
   what he is and the books set their lines on it (gamescan._label,
   2026-11-12); the matchup decides how well it goes, not whether he plays.
   A back with most of his team's carries, a receiver with a fifth of its
   targets, a starting quarterback, a starter's minutes, a skater who
   shoots three times a night, a bat at the top of the order: the read can
   call it tough, never a man to avoid — and it takes one more family
   against him than against anyone else to call it tough (Sheppard at
   Miami, 2026-11-14: one stingy run defense is a stingy run defense, not
   an unfavorable workhorse). The bar is the same both ways: a read leans
   tough on as many families as it needs to lean good.

3. SCORING IS ITS OWN QUESTION (`mark_scorers`, football). A run defence
   ranked 5th gives up fewer yards a carry; it does not take the goal-line
   carries from the back who gets them, and the touchdown board prices
   exactly that — his share of his team's touchdowns times the points the
   lines expect. A read that runs against his team's go-to scorer says
   both ("Tough for yards — still the go-to scorer"), and the short
   version does not list him among the men who could have a hard day.

Standard library only. Nothing here moves a number: the reads choose a
side among numbers that already clear every bar (engine/likely.READ_SEATS).
"""
from __future__ import annotations

# The families a reason can belong to.
DEFENSE = "defense"          # the defence he faces: its ranks, what it allows his position
GOALIE = "goalie"            # the goalie he shoots at
PITCHER = "pitcher"          # the starter he bats against (or a pitcher's opponents' bats)
POINTS = "points"            # the points (goals, runs) the lines expect his team to score
PACE = "pace"                # how many possessions the game should have
BLOWOUT = "blowout"          # a spread wide enough to take a starter's late minutes
WEATHER = "weather"          # the forecast's measured step on his market
SCHEDULE = "schedule"        # rest: back-to-backs, third games in four nights
ROLE = "role"                # his own role moving: minutes, usage, ice time
TEAMMATES = "teammates"      # a teammate out, and what it opens
OWN_TEAM = "own_team"        # his own team's unit (its run blocking, its run game)
TRENCHES = "trenches"        # a front against a line, a pass rush against protection
PARK = "park"                # the ballpark
UMPIRE = "umpire"            # the plate umpire's zone
PLATOON = "platoon"          # his split against tonight's hand
CONTACT = "contact"          # his own contact quality (xSLG, barrels)
LINEUP = "lineup"            # where he bats
BULLPEN = "bullpen"          # the pens' workloads
SPECIAL_TEAMS = "special_teams"  # the power play

#: The key ladder every league shares, best first.
KEYS = ("breakout", "good", "neutral", "tough", "avoid")

#: THE MATCHUP ITSELF (step ACY, 23 November 2026; football since step ACW):
#: the families that are the opponent a player faces — its defence, the goalie
#: he shoots at, the starter he bats against and how that starter's hand meets
#: his bat, how often it hands his team power plays. A verdict none of them
#: carried is the night's, not the opponent's (the schedule, the pace, the
#: points the lines expect, a blowout, his own role), and in every league it
#: says "spot", not "matchup" — Ethan, 23 November, on a "tough matchup" beside
#: a defence giving up the 2nd-most: "It doesn't really make much sense compared
#: to the data we're giving out."
MATCHUP_FAMILIES = frozenset({DEFENSE, GOALIE, PITCHER, PLATOON, SPECIAL_TEAMS})
#: A spot's label, as football's reads say it (engine/gamescan.SPOT_LABELS).
SPOT_LABELS = {"good": "Good spot", "tough": "Tough spot", "avoid": "Avoid"}


def score(pro, con, fam: dict | None = None) -> int:
    """The read's count, one vote a family: each family scores +1 when
    more of its reasons are for him than against, −1 the other way, 0 when
    they tie. ``fam`` maps a reason's text to its family; a reason with no
    family is its own and votes alone (every league's count before this)."""
    fam = fam or {}
    net: dict = {}
    for text in pro or []:
        k = fam.get(text) or ("pro", text)
        net[k] = net.get(k, 0) + 1
    for text in con or []:
        k = fam.get(text) or ("con", text)
        net[k] = net.get(k, 0) - 1
    return sum(1 if v > 0 else -1 if v < 0 else 0 for v in net.values())


def carried_by(key: str, pro, con, fam: dict | None) -> list[str]:
    """The families whose vote went the verdict's way, one vote a family as
    `score` counts them: for a good or breakout read the families more for
    him than against, for a tough or avoid read the other way. A reason with
    no family is no family's."""
    sign = 1 if key in ("breakout", "good") else -1 if key in ("tough", "avoid") else 0
    if not sign:
        return []
    net: dict = {}
    for text in pro or []:
        f = (fam or {}).get(text)
        if f:
            net[f] = net.get(f, 0) + 1
    for text in con or []:
        f = (fam or {}).get(text)
        if f:
            net[f] = net.get(f, 0) - 1
    return sorted(f for f, v in net.items() if v * sign > 0)


def mark_spot(read: dict, fam: dict | None) -> dict:
    """A good, tough or avoid read the opponent did not carry (no family in
    MATCHUP_FAMILIES among `carried_by`) takes SPOT_LABELS' word and carries
    ``spot``; every read carries ``drivers``, the families that carried it —
    what the reports and the cards read, as football's reads have since step
    ACW. Returns the read."""
    key = str(read.get("read") or "")
    drivers = carried_by(key, read.get("pro"), read.get("con"), fam)
    read["drivers"] = drivers
    if key in SPOT_LABELS and drivers and not set(drivers) & MATCHUP_FAMILIES:
        read["label"] = SPOT_LABELS[key]
        read["spot"] = True
        # What carried it, in its own words (step AHZ): the texts on its side whose family carried the read.
        side = read.get("pro") if key == "good" else read.get("con")
        why = [t for t in side or [] if (fam or {}).get(t) in drivers]
        if why:
            read["spot_why"] = why
    return read


def ladder(n: int, *, featured: bool = False, breakout_ok: bool = False,
           good_at: int = 1, breakout_at: int = 2) -> str:
    """The read's key from its count. ``good_at`` and ``breakout_at`` are
    the league's own bars (football leans on one family, the others on
    two); a breakout needs ``breakout_ok`` (the volume to use the spot).

    THE SAME BAR BOTH WAYS (Ethan, 2026-11-14, a screenshot of two won
    parlays on Duke's Nate Sheppard, 63 rushing yards and a touchdown by
    the second quarter: "based off our game reports, one of these players
    was unfavorable which was wrong"). A read leans "tough" on as many
    families as "good" needs (``good_at``) and "avoid" on as many as a
    breakout (``breakout_at``). Every league but football had leaned good
    on two families and tough on one, since each league's first read: one
    reason against a player outweighed one for him.

    A FEATURED PLAYER NEEDS ONE MORE (rule 2). His share of the work keeps
    him on the field in a bad spot, so one family against him — Sheppard's
    was Miami's run defense ranked 5th, the only reason his read had — says
    a stingy defense, not an unfavorable player: he reads neutral with the
    reason shown. Two against him read tough; he is never "avoid"."""
    if n >= breakout_at and breakout_ok:
        return "breakout"
    if n >= good_at:
        return "good"
    if n > -(good_at + (1 if featured else 0)):
        return "neutral"
    if n <= -breakout_at and not featured:
        return "avoid"
    return "tough"


class Reasons:
    """A read's reasons as it gathers them: ``pro``, ``con`` and the family
    of each, so a league's read says ``r.pro(text, DEFENSE)`` where it used
    to say ``pro.append(text)``. The lists stay plain lists of sentences —
    what every page and test reads."""

    def __init__(self):
        self.pro: list = []
        self.con: list = []
        self.fam: dict = {}

    def add(self, sign: int, text: str, family: str | None) -> None:
        if not text or not sign:
            return
        (self.pro if sign > 0 else self.con).append(text)
        if family:
            self.fam[text] = family

    def for_(self, text: str, family: str | None = None) -> None:
        self.add(1, text, family)

    def against(self, text: str, family: str | None = None) -> None:
        self.add(-1, text, family)

    def score(self) -> int:
        return score(self.pro, self.con, self.fam)


# --- rule 3: the go-to scorer (football) ---------------------------------------------------
#: A football read is his team's go-to scorer when his touchdown chance is
#: the best on his team among the game's reads and at least this.
GO_TO_PROB = 0.35
#: The positions whose touchdowns the scorer boards price.
SCORER_POS = ("RB", "FB", "WR", "TE")
#: What the label says, by position, when the read runs against a go-to scorer.
STILL_SCORES = {"RB": "Tough for yards — still the go-to scorer",
                "FB": "Tough for yards — still the go-to scorer",
                "WR": "Tough for yards — still the go-to scorer",
                "TE": "Tough for yards — still the go-to scorer"}


def _prob(x: dict):
    td = x.get("td") if isinstance(x, dict) else None
    try:
        return float(td.get("model_prob")) if isinstance(td, dict) and td.get("model_prob") is not None else None
    except (TypeError, ValueError):
        return None


def mark_scorers(scan_reads: dict) -> int:
    """Each game's go-to scorers, by team: the read with his team's best
    touchdown chance (``td``, engine/gamescan.stamp_touchdowns) when it is
    GO_TO_PROB or more. Stamps ``scoring`` on that read — his chance, the
    points the lines expect, the board's red-zone chances — and, when the
    read runs against him, says both in the label. Returns reads marked."""
    n = 0
    for game in (scan_reads or {}).values():
        best: dict = {}
        for x in (game or {}).get("players") or []:
            if not isinstance(x, dict) or str(x.get("pos") or "").upper() not in SCORER_POS:
                continue
            x.pop("scoring", None)
            p = _prob(x)
            if p is None:
                continue
            t = x.get("team") or ""
            if t not in best or p > best[t][0]:
                best[t] = (p, x)
        for t, (p, x) in best.items():
            if p < GO_TO_PROB:
                continue
            td = x.get("td") or {}
            x["scoring"] = {"go_to": True, "prob": round(p, 4),
                            "implied": td.get("implied_total"), "rz_chances": td.get("rz_chances")}
            if x.get("read") in ("tough", "avoid"):
                x["label"] = STILL_SCORES.get(str(x.get("pos") or "").upper(), x.get("label"))
            n += 1
    return n


def scoring_words(x: dict, team_words: str = "") -> str:
    """"His team's likeliest scorer by our touchdown numbers (48%), with
    Duke expected to score about 21" — the sentence a go-to scorer's card
    carries. "" for any other read."""
    s = (x or {}).get("scoring") or {}
    if not s.get("go_to"):
        return ""
    who = team_words or str(x.get("team") or "the team")
    # "Duke's", but "Lions'" (a plural nickname: "Lions's" on 2026-11-15).
    poss = f"{who}'" if who.endswith("s") and not who.endswith("ss") else f"{who}'s"
    text = f"{poss} likeliest scorer by our touchdown numbers ({float(s['prob']):.0%})"
    try:
        imp = float(s.get("implied")) if s.get("implied") is not None else None
    except (TypeError, ValueError):
        imp = None
    if imp:
        text += f", with {who} expected to score about {imp:.0f}"
    return text
