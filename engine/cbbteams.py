"""College basketball's teams — conferences, and the book's names for them.

Three hundred and sixty-five Division I schools is the table that rots the
moment a conference reshuffles, so, as for college football
(`engine.cfbteams`), nothing here is a hand-written list of schools:

  * a school's CODE comes off ESPN's scoreboard (`espnhoops.team_key`:
    ESPN's code for a Division I school, ``espn:{id}`` for a small school);
  * its IDENTITY (name, colours, logo) rides in the board, built from the
    same scoreboard (`cbbespn.teams_from_games`);
  * the BOOK'S SPELLING of it is harvested from our own builds, the way
    college football's is, and kept here so the closing-line harvest can join
    a price to a bet (`remember` / `load`).

What IS written down is the conferences: ESPN's ids, which are the
scoreboard's own ``conferenceId`` values (read off two seasons of ESPN's
scoreboards, 2025-26 and 2026-27; every Division I school carried one of
these and no other school carried any). A conference's name changes far less
often than its members, and a new id prints as its number rather than
breaking anything.
"""

from __future__ import annotations

from . import cfbteams as _cfbteams
from . import feedstate as _feedstate

#: ``{ESPN conference id: (short name, full name)}`` — 2026-27.
CONFERENCES = {
    "1": ("America East", "America East Conference"),
    "2": ("ACC", "Atlantic Coast Conference"),
    "3": ("A-10", "Atlantic 10 Conference"),
    "4": ("Big East", "Big East Conference"),
    "5": ("Big Sky", "Big Sky Conference"),
    "6": ("Big South", "Big South Conference"),
    "7": ("Big Ten", "Big Ten Conference"),
    "8": ("Big 12", "Big 12 Conference"),
    "9": ("Big West", "Big West Conference"),
    "10": ("CAA", "Coastal Athletic Association"),
    "11": ("CUSA", "Conference USA"),
    "12": ("Ivy", "Ivy League"),
    "13": ("MAAC", "Metro Atlantic Athletic Conference"),
    "14": ("MAC", "Mid-American Conference"),
    "16": ("MEAC", "Mid-Eastern Athletic Conference"),
    "18": ("MVC", "Missouri Valley Conference"),
    "19": ("NEC", "Northeast Conference"),
    "20": ("OVC", "Ohio Valley Conference"),
    "21": ("Pac-12", "Pac-12 Conference"),
    "22": ("Patriot", "Patriot League"),
    "23": ("SEC", "Southeastern Conference"),
    "24": ("SoCon", "Southern Conference"),
    "25": ("Southland", "Southland Conference"),
    "26": ("SWAC", "Southwestern Athletic Conference"),
    "27": ("Sun Belt", "Sun Belt Conference"),
    "29": ("WCC", "West Coast Conference"),
    "30": ("UAC", "United Athletic Conference"),
    "44": ("Mountain West", "Mountain West Conference"),
    "45": ("Horizon", "Horizon League"),
    "46": ("ASUN", "Atlantic Sun Conference"),
    "49": ("Summit", "Summit League"),
    "62": ("American", "American Conference"),
}

#: The five leagues the books post the most college player props on (and
#: the national TV windows sit in): the order a pull buys games in leans on
#: them (`priority`). Not a judgement of quality — a fact about the market.
POWER = frozenset({"2", "4", "7", "8", "23"})

#: Beside the other feed state, like college football's two files.
STATE_PATH = _feedstate.path("cbb_teams.json")

#: ``{ESPN team id: code}`` for every Division I school a scoreboard has
#: named (`remember_ids`). A summary's team carries no conference id, so
#: `espnhoops.team_key` could not tell a Division I school there from a
#: small one; the scoreboard can, and this is what it learned.
IDS_PATH = _feedstate.path("cbb_ids.json")


def conference(conf_id) -> str:
    """A conference's short name, or its id when it is new to this table."""
    c = str(conf_id or "").strip()
    return CONFERENCES.get(c, (c, c))[0] if c else ""


def conference_name(conf_id) -> str:
    c = str(conf_id or "").strip()
    return CONFERENCES.get(c, (c, c))[1] if c else ""


#: THE STANDINGS FEED'S OWN LABELS for its conference tables, read off the
#: box's first college table (2026-11-13: "acc", "atl10", "belt", "Metro"
#: ...), to the scoreboard's conference ids. Without it every conference
#: showed twice, the schools a slate had named under "ACC" and the rest
#: under "acc" (`conference_of_feed`).
FEED_LABELS = {
    "acc": "2", "aeast": "1", "atl10": "3", "belt": "27", "big10": "7", "big12": "8",
    "bige": "4", "bigw": "9", "bsky": "5", "bsou": "6", "col": "10", "hor": "45",
    "ivy": "12", "land": "25", "meac": "16", "midam": "14", "mvc": "18", "mwest": "44",
    "neast": "19", "ovc": "20", "pac12": "21", "pat": "22", "sec": "23", "south": "24",
    "summ": "49", "swac": "26", "usa": "11", "wcc": "29", "metro": "13",
    "american": "62", "asun": "46", "uac": "30",
}


def _norm(text) -> str:
    return " ".join(str(text or "").lower().replace("-", " ").split())


def conference_of_feed(group_id="", group_name="", label="") -> str:
    """The board's short name for the conference table the standings feed
    filed a school under: by the group's id where it is a conference id the
    scoreboard uses, then its full name, then the feed's own label; the
    label itself when none of them is known (a new conference prints as
    ESPN calls it rather than vanishing)."""
    gid = str(group_id or "").strip()
    if gid in CONFERENCES:
        return CONFERENCES[gid][0]
    name = _norm(group_name)
    if name:
        for short, full in CONFERENCES.values():
            if name in (_norm(full), _norm(short)):
                return short
    lab = str(label or "").strip()
    cid = FEED_LABELS.get(lab.lower())
    if cid:
        return CONFERENCES[cid][0]
    for short, full in CONFERENCES.values():
        if _norm(lab) in (_norm(short), _norm(full)):
            return short
    return lab


def is_division_one(code: str) -> bool:
    """A code the scoreboard gave a Division I school (`espnhoops.team_key`)."""
    return bool(code) and not str(code).startswith("espn:")


def priority(game: dict) -> tuple:
    """How much one game is worth buying player prices for, as a sort key
    (smaller first): a ranked team in it (the higher the better), two power
    conference schools, one, a conference game, then the tip.

    WHY THIS ORDER. A college night is 60 to 150 games and the books post
    player props on a fraction of them — the ranked teams and the power
    conferences, the games on national TV. Buying a game the books did not
    price spends credits on an empty answer; buying them in this order buys
    the priced ones first, inside the budget's count
    (`oddsbudget.affordable_events`), which is the rule college football's
    pull follows with its attention tiers."""
    ranks = [r for r in (game.get("home_rank"), game.get("away_rank")) if r]
    power = sum(1 for side in ("home", "away") if str(game.get(f"{side}_conf") or "") in POWER)
    return (0 if ranks else 1, min(ranks) if ranks else 99, -power,
            0 if game.get("conference_game") else 1, str(game.get("kickoff") or ""))


def load(path: str | None = None) -> dict:
    """``{book's spelling: code}`` — the names our own builds resolved."""
    return _cfbteams.load(path or STATE_PATH)


def remember(pairs: dict, path: str | None = None) -> int:
    """Merge ``{book spelling: code}``; the number of new names learned."""
    return _cfbteams.remember(pairs, path or STATE_PATH)


def load_ids(path: str | None = None) -> dict:
    """``{ESPN team id: code}`` — the Division I schools seen so far."""
    return _cfbteams.load_ids(path or IDS_PATH)


def remember_ids(pairs: dict, path: str | None = None) -> int:
    """Merge ``{ESPN team id: code}``; the number of new ids learned."""
    return _cfbteams.remember_ids(pairs, path or IDS_PATH)


#: Every Division I school's card as the scoreboards have shown it — name,
#: colours, logo, conference, ESPN id — kept across builds (`remember_cards`)
#: so the pages that list schools a night's slate does not (the standings'
#: 365, the rosters, a team page opened from a link) can name and colour
#: them. A tonight's-only table answers for sixty schools at most.
CARDS_PATH = _feedstate.path("cbb_cards.json")

#: What a kept card holds: identity only. A rank is the week's, not the
#: school's, and rides on tonight's games alone.
CARD_KEYS = ("name", "nick", "loc", "short", "abbr", "primary", "secondary",
             "logo", "conf", "id")


def cards(path: str | None = None) -> dict:
    """``{code: card}`` — every school a build has seen; ``{}`` if none."""
    import json
    try:
        with open(path or CARDS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    got = (data or {}).get("teams") if isinstance(data, dict) else None
    return {str(k): {kk: v.get(kk) for kk in CARD_KEYS if v.get(kk)}
            for k, v in (got or {}).items() if k and isinstance(v, dict)}


def remember_cards(teams: dict, path: str | None = None) -> int:
    """Merge tonight's ``{code: card}`` (`cbbespn.teams_from_games`) into the
    kept cards; the number of schools new or changed. Never raises: a card
    file that cannot be written costs the next page a colour, not a build.
    But its 0 is also what a night of known schools answers, so a failure
    prints "college basketball team cards not kept (<error>)" into the
    build's log, which no quiet night does."""
    import json
    import os
    path = path or CARDS_PATH
    try:
        kept = cards(path)
        changed = 0
        for code, t in (teams or {}).items():
            if not code or not isinstance(t, dict):
                continue
            card = {k: t.get(k) for k in CARD_KEYS if t.get(k)}
            if card and kept.get(code) != card:
                kept[code] = card
                changed += 1
        if not changed:
            return 0
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"teams": dict(sorted(kept.items()))}, fh, separators=(",", ":"))
        os.replace(tmp, path)
        return changed
    except Exception as exc:                                # noqa: BLE001
        print(f"⚠️  college basketball team cards not kept ({exc})")
        return 0
