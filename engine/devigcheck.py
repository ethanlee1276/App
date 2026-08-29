"""Is the de-vig actually running on the live board?

The tests prove the arithmetic. They cannot prove the FEED cooperates,
and that is where this breaks if it breaks. The market-sum method needs
to see a game's whole scorer board: if the odds feed returns twelve
players where the book lists thirty, the sum comes in low, the measured
hold comes in low, and the correction under-does itself — silently, in
the direction that inflates edge. Nothing in a unit test can catch that,
because the input is the feed.

So this reads the board that actually shipped and reports, per pick:
what vig it priced against, where that number came from, and whether the
answer is plausible for the market. Three things can be true of a pick
and only one of them is good:

    measured:<book>   the game's own board set the price. Working.
    assumed           too thin to measure, on the standing 6%. Not
                      broken — it is what ran before any of this — but
                      it is the optimistic bound of a range, not a
                      number, and the card says so.
    two-way           both sides quoted, so the de-vig is exact and none
                      of this applies. Best case.

AND A MEASURED VIG CAN STILL BE WRONG. A number well under what the
market is known to charge is evidence of a short board, not a generous
book, so it is flagged rather than trusted. The floors below are
deliberately far under the published ranges: they are a truncation
alarm, not a claim about what the hold should be.

Reads a published board JSON. No database, no API key, no credits.

    python3 -m engine.devigcheck web/data/recommendations.json
    python3 -m engine.devigcheck web/data/cfb.json

Standard library only.
"""

from __future__ import annotations

import json

#: Below this a MEASURED overround is more likely a truncated board than
#: a generous book, and gets flagged. Set well under the published
#: ranges (the NFL handbook says anytime-TD runs 22-35%, the CFB one
#: 28-40% in power conferences and 35-50% in the Group of Five) so that
#: only an obviously short board trips it. Raising these to the middle
#: of those ranges would be asserting the handbooks as fact, which the
#: rest of this work has not found to be safe.
SUSPICIOUS_VIG = {"nfl": 0.10, "cfb": 0.15}
SUSPICIOUS_DEFAULT = 0.10


def rows_of(board: dict) -> list:
    """Every priced touchdown row on the board, picks and watch alike.

    The watch is included on purpose: it takes every quoted scorer at a
    sane price, so it is a wider sample of what the feed returned than
    the handful of picks that survived the edge bar.
    """
    out = []
    for key, kind in (("long_shots", "pick"), ("longshot_watch", "watch")):
        for r in board.get(key) or []:
            if isinstance(r, dict):
                out.append(dict(r, _kind=kind))
    return out


def board_state(board: dict) -> tuple[str, str]:
    """``(state, why)`` for a board with no touchdown rows on it.

    An empty board is not one condition, and reporting it as one is how a
    check gets ignored. A slate whose prop menus have not posted has
    nothing to price and nothing is wrong; a board that pulled odds and
    still found nothing is a different question; a locked board is a
    third. The first cut called all of them "NO BOARD", which told the
    reader nothing and looked like an alarm.
    """
    if board.get("locked"):
        return "LOCKED", (board.get("locked_reason")
                          or "the board is locked, so nothing was priced")
    if board.get("generated_from") == "schedule-only":
        return "NO ODDS YET", (
            "schedule-only board: no odds were pulled, so there is no "
            "scorer market to de-vig. Normal before prop menus post — "
            "they land Thursday or Friday in college and midweek in the "
            "NFL. Nothing to check until then")
    if not (board.get("games") or []):
        return "NO GAMES", "no games on this slate"
    c = board.get("td_census") or {}
    if c:
        # The build published its own reason, so use it instead of
        # listing what the reason might have been.
        if not c.get("games_quoted"):
            return "NO SCORER PULL", (
                f"no game's scorer market was pulled — {c.get('quotes_note') or ''}"
                ". A game qualifies with a real spread AND total and a "
                "kickoff inside the pull window; outside that there is "
                "nothing to de-vig")
        if not c.get("quoted_players"):
            note = c.get("quotes_note") or "the feed returned an empty market"
            return "NO SCORER PULL", (
                f"{c['games_quoted']} game(s) pulled but no player came "
                f"back priced — {note}")
        parts = [f"{c['quoted_players']} player(s) quoted"]
        if c.get("no_usage"):
            parts.append(f"{c['no_usage']} had no usage logs")
        if c.get("outside_window"):
            parts.append(f"{c['outside_window']} sat outside the odds window")
        if c.get("usage_season"):
            parts.append(f"roles from {c['usage_season']}")
        return "PRICED, NONE KEPT", (
            "the scorer market was pulled and nothing survived to the "
            "board: " + ", ".join(parts))
    return "NO TD MARKET", (
        "the board was priced but published no touchdown rows. Either no "
        "game qualified for a scorer pull (a real spread AND total, and "
        "kickoff inside the pull window), or the pull returned nothing. "
        "Rebuild to publish the census that says which")


def _sport_of(board: dict) -> str:
    """The NFL payload carries no `sport` key, so infer where needed."""
    got = (board.get("sport") or "").lower()
    if got:
        return got
    date = str(board.get("date") or "")
    # "2026-W01" is the NFL board's season-week stamp; nothing else uses it.
    return "nfl" if "-W" in date else ""


def summarise(board: dict) -> dict:
    """Counts by vig source, plus whatever looks wrong."""
    sport = _sport_of(board)
    floor = SUSPICIOUS_VIG.get(sport, SUSPICIOUS_DEFAULT)
    rows = rows_of(board)
    got = {"sport": sport, "date": board.get("date", ""),
           # The NFL board stamps `built_at`, the others `generated_at`.
           # Printing "?" for a board that plainly says when it was built
           # is the check looking broken instead of the board.
           "generated_at": (board.get("generated_at")
                            or board.get("built_at") or ""),
           "rows": len(rows), "measured": 0, "assumed": 0, "two_way": 0,
           "unknown": 0, "books": {}, "suspicious": [], "vigs": [],
           "floor": floor}
    for r in rows:
        src = str(r.get("vig_source") or "")
        vig = r.get("vig")
        if src.startswith("measured"):
            got["measured"] += 1
            book = src.partition(":")[2] or "?"
            got["books"][book] = got["books"].get(book, 0) + 1
            if isinstance(vig, (int, float)):
                got["vigs"].append(float(vig))
                if vig < floor:
                    got["suspicious"].append(r)
        elif src == "two-way":
            got["two_way"] += 1
        elif src in ("assumed",) or src.startswith("journal"):
            got["assumed"] += 1
        else:
            # No field at all means the board predates this, or the row
            # never went through `build_pick` — either way it is not
            # evidence that the de-vig ran.
            got["unknown"] += 1
    if not rows:
        got["empty"] = board_state(board)
    if got["vigs"]:
        v = sorted(got["vigs"])
        got["vig_min"], got["vig_max"] = v[0], v[-1]
        got["vig_median"] = v[len(v) // 2]
    return got


def verdict(got: dict) -> tuple[str, list]:
    """``(READY | CHECK | NOT WIRED, reasons)``.

    "CHECK" is not "broken". A board of thin markets legitimately falls
    back, and a board that predates the field legitimately has none —
    both need a human to look rather than a green light or an alarm.
    """
    why = []
    if not got["rows"]:
        state, reason = got.get("empty", ("NO BOARD", "nothing priced"))
        return state, [reason]
    if got["unknown"] == got["rows"]:
        return "NOT WIRED", [
            "no row carries a vig source: the published board predates "
            "this, or was built before the last deploy"]
    if got["unknown"]:
        why.append(f"{got['unknown']} row(s) carry no vig source at all")
    if got["suspicious"]:
        why.append(
            f"{len(got['suspicious'])} row(s) measured a vig under "
            f"{got['floor']:.0%}, which reads as a SHORT BOARD rather than "
            f"a generous book — the feed may be truncating that game's "
            f"scorer list, and a short board under-states the hold")
    if not got["measured"] and not got["two_way"]:
        why.append("no row got a measured vig — every one fell back to the "
                   "standing assumption")
    if got["assumed"]:
        why.append(f"{got['assumed']} row(s) fell back to the assumption "
                   f"(too thin to measure, or no game line)")
    state = "READY" if not got["suspicious"] and not got["unknown"] \
        and (got["measured"] or got["two_way"]) else "CHECK"
    return state, why or ["every priced row got a real de-vig"]


def report_lines(board: dict) -> list:
    got = summarise(board)
    state, why = verdict(got)
    lines = [
        f"  board: {got['sport'] or '?'}  {got['date']}  "
        f"built {got['generated_at'] or '?'}",
        f"  {got['rows']} priced touchdown row(s)",
        "",
        f"    measured off the game's own board : {got['measured']}",
        f"    exact (both sides quoted)         : {got['two_way']}",
        f"    fell back to the assumption       : {got['assumed']}",
        f"    no vig source at all              : {got['unknown']}",
    ]
    if got["books"]:
        books = ", ".join(f"{b} x{n}" for b, n in sorted(
            got["books"].items(), key=lambda kv: -kv[1]))
        lines += ["", f"  reference book(s): {books}"]
    if got.get("vigs"):
        lines.append(f"  measured overround: {got['vig_min']:.1%} low / "
                     f"{got['vig_median']:.1%} median / {got['vig_max']:.1%} "
                     f"high")
    if got["suspicious"]:
        lines += ["", "  SHORT-BOARD SUSPECTS (measured vig under "
                      f"{got['floor']:.0%}):"]
        for r in got["suspicious"][:10]:
            lines.append(f"    {r.get('player','?'):<24} "
                         f"{r.get('odds', 0):>+6} "
                         f"vig {float(r.get('vig') or 0):>6.1%}  "
                         f"{r.get('vig_source','')}")
    lines += ["", f"  {state}"]
    lines += [f"    - {w}" for w in why]
    return lines


def _main(argv) -> int:                          # pragma: no cover
    if not argv:
        print("usage: python3 -m engine.devigcheck <board.json> [more.json]")
        return 2
    worst = 0
    for path in argv:
        try:
            with open(path) as fh:
                board = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"\n{path}\n  cannot read: {exc}")
            worst = max(worst, 2)
            continue
        print(f"\n{path}")
        for line in report_lines(board):
            print(line)
        state, _ = verdict(summarise(board))
        # A slate with no odds yet is not a failure, and exiting nonzero
        # on it would train the reader to ignore this.
        # A slate with no odds yet is not a failure, and exiting nonzero
        # on it would train the reader to ignore this.
        worst = max(worst, {"READY": 0, "NO ODDS YET": 0, "LOCKED": 0,
                            "NO GAMES": 0, "CHECK": 1,
                            "NO SCORER PULL": 1, "PRICED, NONE KEPT": 1,
                            }.get(state, 2))
    return worst


if __name__ == "__main__":                       # pragma: no cover
    import sys
    raise SystemExit(_main(sys.argv[1:]))
