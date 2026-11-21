"""Two feeds, one answer: is this player available?

Left open by 91c270e and stated plainly there: "the ESPN injury feed that
powers the Injuries page is a SECOND source of truth for the same
question, and nothing reconciles it against the roster. If a player is on
the ESPN board and not designated by Sleeper, the roster will still call
him active."

That is the whole bug. The site was showing two answers to one question
on two different pages and letting the reader notice.

WHAT EACH FEED IS, because they are not redundant:

    Sleeper       the ROSTER. Every player on every team, with a weekly
                  `injury_status` when the club files one. Complete, and
                  sometimes late.
    ESPN          the injury REPORT. Only players with a filing, but with
                  the body part, the side, a return date and a comment —
                  and often first.

So ESPN is better at "what is wrong with him" and Sleeper is better at
"who exists". The merge takes availability from whichever is more
pessimistic and detail from whichever has it.

THE MERGE ONLY EVER ADDS SEVERITY. It can move a player from available to
out; it can never move one from out to available. That asymmetry is
deliberate and it is the whole safety property:

  * pricing a player who does not play is a loss every time;
  * withholding a player who does play costs one missed bet.

A stale "Out" therefore cannot be cleared by this module, only by the
feed that filed it. `espninjuries.current_rows` keeps the NEWEST filing
per player, so a returned player's latest ESPN row is a clearance notice
— which contributes nothing here, leaving Sleeper's answer to stand on
its own. That is how a player comes back: not by one feed overruling the
other, but by neither of them objecting.

NOTHING IS RESOLVED SILENTLY. Every merged row records which feeds spoke
and whether they disagreed, so a contradiction is visible on the page
instead of being averaged away behind it.

Pure functions, standard library. No I/O, no network.
"""

from __future__ import annotations

#: How bad a designation is. Higher wins a disagreement. Only the ORDER
#: matters — these are ranks, not probabilities, and nothing multiplies
#: them.
#:
#: "Day-To-Day" sits with questionable rather than with out: it is ESPN's
#: way of saying a player is carrying something and is expected to play,
#: which is exactly what a questionable tag means for our purposes.
SEVERITY = {
    "": 0, "active": 0, "probable": 0,
    "questionable": 1, "day-to-day": 1, "day to day": 1, "gtd": 1,
    "doubtful": 2,
    "out": 3, "inactive": 3,
    "injured reserve": 4, "ir": 4, "physically unable to perform": 4,
    "pup": 4, "non football injury": 4, "nfi": 4, "suspension": 4,
    "suspended": 4, "reserve/covid-19": 4,
}

#: At or above this a player is not playing.
OUT_AT = 3
#: At this rank he is flagged but expected to play.
FLAG_AT = 1


def severity(status: str) -> int:
    """Rank a designation from either feed. Unknown words rank 0.

    Ranking an unrecognised status as 0 rather than guessing high is the
    conservative choice HERE, precisely because the merge is
    severity-only: a status we cannot read contributes nothing instead of
    silently benching a player on a word nobody mapped.
    """
    return SEVERITY.get((status or "").strip().lower(), 0)


def _norm(name: str) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(name or "")


def espn_index(rows, team_abbr=None) -> dict:
    """``{(TEAM, normalised player): row}`` from parsed ESPN injury rows.

    ``rows`` should already be `espninjuries.current_rows` output — one
    filing per player, newest kept. Rows are indexed by TEAM as well as
    name because two players share a name often enough that a
    name-only join would move one man's knee onto another's.

    A team name that does not map is DROPPED, not guessed. ESPN writes
    full club names ("Detroit Lions") and the roster keys on
    abbreviations; a fuzzy match here would attach a real injury to the
    wrong club, which is worse than missing it.
    """
    from .sources.espninjuries import is_return
    if team_abbr is None:
        from .sources.oddsapi import TEAM_ABBR as team_abbr
    out: dict[tuple, dict] = {}
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        # A clearance notice is not a designation. Carrying it would let
        # an "Active" row look like something the merge should act on.
        if is_return(r):
            continue
        team = team_abbr.get((r.get("team") or "").strip())
        player = _norm(r.get("player", ""))
        if not team or not player:
            continue
        out[(team, player)] = r
    return out


def merge_row(row: dict, espn: dict | None) -> dict:
    """One roster row reconciled against its ESPN filing, if any.

    Returns a NEW dict; the input is not mutated. When there is no ESPN
    filing the row comes back with its provenance stamped and nothing
    else changed — "Sleeper alone said so" is information too.
    """
    merged = dict(row)
    mine = severity(row.get("injury_status") or row.get("status") or "")
    # A roster-level flag (IR, PUP, suspended) that carries no weekly
    # designation still means unavailable, and `unavailable` already
    # encodes it. Do not let a severity of 0 talk us out of it.
    if row.get("unavailable") and mine < OUT_AT:
        mine = OUT_AT

    if not espn:
        merged["injury_sources"] = ["sleeper"]
        merged["injury_conflict"] = False
        return merged

    theirs = severity(espn.get("status") or "")
    merged["injury_sources"] = ["sleeper", "espn"]
    # A DISAGREEMENT NEEDS TWO CLAIMS. Sleeper saying nothing while ESPN
    # files an "Out" is not a contradiction — it is the exact gap this
    # module was built to close, and flagging it would raise an alarm on
    # every player the merge helps, which is most of them.
    #
    # And it has to be a disagreement about the ANSWER, not the wording:
    # Questionable versus Day-To-Day is one verdict in two vocabularies.
    # So both feeds must have spoken, and they must land on opposite
    # sides of "is he playing".
    both_spoke = mine > 0 and theirs > 0
    merged["injury_conflict"] = both_spoke and (mine >= OUT_AT) != (theirs >= OUT_AT)

    if theirs > mine:
        # ESPN is the more pessimistic read; adopt its designation.
        merged["status"] = espn.get("status") or merged.get("status") or ""
        merged["injury_status"] = espn.get("status") or ""
        merged["injury_source"] = "espn"
    else:
        merged["injury_source"] = "sleeper"

    worst = max(mine, theirs)
    merged["unavailable"] = bool(merged.get("unavailable")) or worst >= OUT_AT
    merged["questionable"] = worst == FLAG_AT
    # DETAIL always comes from ESPN when it has any, whoever won the
    # availability call. "Out" tells a bettor to fade him; "Out — knee,
    # right" tells him whether to expect it next week too. Sleeper's
    # `injury_body_part` is a bare word and loses to a fuller phrase.
    what = espn.get("injury")
    if what and len(str(what)) > len(str(merged.get("injury") or "")):
        merged["injury"] = str(what)
    for src, dst in (("side", "injury_side"), ("return_date", "return_date"),
                     ("comment", "injury_note"), ("date", "injury_filed")):
        if espn.get(src):
            merged[dst] = espn[src]
    return merged


def apply(payload: dict, rows, team_abbr=None) -> dict:
    """Merge an ESPN injury board into a `rosters.build_rosters` payload.

    Returns the payload with every player row reconciled and a
    ``injury_merge`` block describing what happened — how many players
    ESPN knew about that the roster called available, how many filings
    could not be matched to a rostered player, and how many contradicted.

    The unmatched count is the one worth watching: it is the honest
    measure of how well the two feeds' names line up, and a number that
    creeps upward means the join is rotting rather than the league
    getting healthier.
    """
    idx = espn_index(rows, team_abbr)
    if not payload or not payload.get("teams"):
        return payload
    seen: set = set()
    added = conflicts = 0
    for team, block in (payload.get("teams") or {}).items():
        merged_rows = []
        for row in (block.get("players") or []):
            key = (team, _norm(row.get("player", "")))
            espn = idx.get(key)
            if espn is not None:
                seen.add(key)
            before = bool(row.get("unavailable"))
            new = merge_row(row, espn)
            if new.get("unavailable") and not before:
                added += 1
            if new.get("injury_conflict"):
                conflicts += 1
            merged_rows.append(new)
        block["players"] = merged_rows
        block["unavailable"] = sum(1 for r in merged_rows if r["unavailable"])
    payload["injury_merge"] = {
        "espn_filings": len(idx),
        "matched": len(seen),
        "unmatched": sorted(
            f"{t} {(idx[(t, n)] or {}).get('player', n)}"
            for (t, n) in idx if (t, n) not in seen)[:40],
        "unmatched_count": len(idx) - len(seen),
        "newly_unavailable": added,
        "conflicts": conflicts,
    }
    return payload
