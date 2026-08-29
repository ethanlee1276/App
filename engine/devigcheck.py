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

THE PUBLIC FILE IS THE PAYWALLED COPY. engine/gate strips every priced
row out of what web/data/ serves and keeps the real board in data/built/,
so pointing this at the public path reports "locked" and learns nothing —
which is what the first two live runs did. When the file it is given is
locked, it reads the private copy instead and says which one it used,
because reading the unredacted board is a deliberate act and should be
visible in the output rather than silent.

Standard library only.
"""

from __future__ import annotations

import json

#: Players the reference book must list before a MEASURED vig is
#: trustworthy. THE DIRECT EVIDENCE for the failure this exists to catch:
#: if the feed returns a fraction of a game's scorers, the sum comes in
#: low and so does the hold, silently, in the direction that inflates
#: edge. A real anytime-touchdown board runs 20-40 deep; six is the floor
#: for measuring at all (devig.MIN_PRICED) and anything near it is a
#: board we are seeing part of.
#:
#: Provisional. It should be set from the distribution of board sizes the
#: live feed actually returns, which the report prints — not from a guess
#: about what books do.
MIN_BOARD = 12

#: Below this a MEASURED overround is too small to be a real book.
#:
#: RECALIBRATED against live data, downward, and that correction matters.
#: The first cut set these from the handbooks' published ranges — 22-35%
#: for NFL anytime-TD, 28-50% for college — and picked floors "well
#: under" them at 10% and 15%. Then the fitter measured the NFL market at
#: 16.1% average hold over 3,890 settled closes, and the first live
#: college board came back at 14.1-24.1%. Both published ranges are high,
#: so a floor derived from them flagged an ordinary board as truncated on
#: the very first run.
#:
#: A check that cries wolf is a check that gets ignored, so these are now
#: set where only an implausible number trips them, and board size does
#: the real work above.
SUSPICIOUS_VIG = {"nfl": 0.05, "cfb": 0.05}
SUSPICIOUS_DEFAULT = 0.05


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
        # Reaching here means `load` could not follow to the private copy,
        # so this is the paywalled payload and it carries no priced rows
        # by design. Saying "locked: subscription" and stopping reads as
        # a finding about the board; it is a finding about which file was
        # opened.
        return "PAYWALLED COPY", (
            "engine/gate strips every priced row from what web/data/ "
            "serves, so this file cannot show whether the de-vig ran. "
            "The real board is data/built/<name>.json — point this there, "
            "or run it from the repo root so it can follow on its own")
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
           "unknown": 0, "books": {}, "suspicious": [], "short": [],
           "unverified": [], "vigs": [], "listed": [], "floor": floor}
    for r in rows:
        src = str(r.get("vig_source") or "")
        vig = r.get("vig")
        if src.startswith("measured"):
            got["measured"] += 1
            book = src.partition(":")[2] or "?"
            got["books"][book] = got["books"].get(book, 0) + 1
            listed = int(r.get("vig_listed") or 0)
            if listed:
                got["listed"].append(listed)
            else:
                # A MEASURED VIG WITH NO BOARD SIZE CANNOT BE JUDGED, and
                # passing it would defeat the field's whole purpose. This
                # happened on the first run after the field shipped: the
                # rows were built by the previous code, so every one read
                # "measured" with nothing behind it and the check said
                # READY on evidence it did not have.
                got["unverified"].append(r)
            if isinstance(vig, (int, float)):
                got["vigs"].append(float(vig))
            # Board size first: it is the fact. A small vig is only a
            # hint, and on live data it fired on an ordinary board.
            if listed and listed < MIN_BOARD:
                got["short"].append(r)
            elif listed and isinstance(vig, (int, float)) and vig < floor:
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
    got["fallback_detail"] = fallback_detail(board)
    if got["vigs"]:
        v = sorted(got["vigs"])
        got["vig_min"], got["vig_max"] = v[0], v[-1]
        got["vig_median"] = v[len(v) // 2]
    if got["listed"]:
        b = sorted(got["listed"])
        got["listed_min"], got["listed_max"] = b[0], b[-1]
        got["listed_median"] = b[len(b) // 2]
    return got


#: What a game's own census says went wrong, in words that name the fix.
WHY_TEXT = {
    "thin": "the feed listed too few players to measure a hold",
    "no margin": "the listed prices summed BELOW the scorers the game line "
                 "supports, so no margin was visible to strip",
    "unsolved": "the exponent could not be placed on that board",
}


def fallback_detail(board: dict) -> list:
    """Per-game reasons a board fell back, from the build's own census.

    "Every row fell back to the assumption" is a symptom, not a
    diagnosis. Thin prop menus, a missing game line and a wiring fault
    all look identical from the published rows, and they need three
    different fixes — so the build now records which, and this reads it
    rather than leaving the reader to guess.
    """
    c = board.get("td_census") or {}
    if not c:
        return ["this board carries no build census, so it predates that "
                "field — rebuild and re-run to see which games could not "
                "be measured and why"]
    if not c.get("games"):
        return []
    out = []
    if c.get("no_line"):
        out.append(f"{c['no_line']} game(s) had no usable spread and total, "
                   f"so there was no way to say how many scorers to expect")
    for b in (c.get("boards") or [])[:8]:
        why = WHY_TEXT.get(b.get("why"), b.get("why", ""))
        out.append(
            f"{b.get('game','?')}: {b.get('book','?')} listed "
            f"{b.get('listed', 0)} player(s) summing {b.get('sum', 0):.2f} "
            f"against {b.get('scorers', 0):.2f} expected scorers — {why}")
    extra = len(c.get("boards") or []) - 8
    if extra > 0:
        out.append(f"...and {extra} more game(s) the same way")
    return out


def census_lines(c: dict) -> list:
    """How wide the board was, from whichever census the build wrote.

    THE TWO SPORTS RECORD DIFFERENT THINGS AND THAT IS FINE; reading only
    one shape was not. The NFL pipeline counts GAMES it tried to measure
    (games / measured / unmeasurable / no_line) because that is where its
    de-vig can fail; the college build counts QUOTED PLAYERS and why they
    were dropped (quoted_players / no_usage / outside_window) because
    that is where its board thins out. The first cut keyed on "games"
    alone, so the college board — the one actually live — printed
    nothing on the run where it finally passed.

    Prints whichever facts are present rather than insisting both sports
    describe themselves the same way.
    """
    if not c:
        return []
    out = []
    games = c.get("games") or c.get("games_quoted")
    if games:
        parts = []
        for key, label in (("measured", "measured"),
                           ("unmeasurable", "too thin"),
                           ("no_line", "without a game line")):
            if key in c:
                parts.append(f"{c[key]} {label}")
        detail = f"  ({', '.join(parts)})" if parts else ""
        out.append(f"  games with a scorer market: {games}{detail}")
    if c.get("quoted_players"):
        parts = []
        for key, label in (("no_usage", "without usage logs"),
                           ("transfers", "found under a former school"),
                           ("outside_window", "outside the odds window")):
            if c.get(key):
                parts.append(f"{c[key]} {label}")
        detail = f"  ({', '.join(parts)})" if parts else ""
        out.append(f"  quoted players: {c['quoted_players']}{detail}")
    if c.get("usage_season"):
        out.append(f"  roles built from {c['usage_season']} logs")
    return ["" ] + out if out else []


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
    if got["unverified"]:
        why.append(
            f"{len(got['unverified'])} row(s) report a measured vig with no "
            f"board size behind it — this board was built before that field "
            f"shipped, so nothing here can say whether the feed returned a "
            f"whole scorer market or part of one. Rebuild, then re-run")
    if got["short"]:
        why.append(
            f"{len(got['short'])} row(s) were priced off a board of fewer "
            f"than {MIN_BOARD} players — a real anytime-touchdown market "
            f"runs 20-40 deep, so the feed is likely returning part of "
            f"that game's scorer list. A SHORT BOARD under-states the "
            f"hold, which inflates edge")
    if got["suspicious"]:
        why.append(
            f"{len(got['suspicious'])} row(s) measured a vig under "
            f"{got['floor']:.0%} off a full-looking board — too small to "
            f"be a real book, so something upstream of the sum is wrong")
    if not got["measured"] and not got["two_way"]:
        why.append("no row got a measured vig — every one fell back to the "
                   "standing assumption")
    if got["assumed"]:
        why.append(f"{got['assumed']} row(s) fell back to the assumption")
        # Only when something DID fall back. A fully measured board has
        # no fallback to explain, and telling it its census is missing
        # would be noise on the one outcome we are hoping to see.
        for line in got.get("fallback_detail") or []:
            why.append(line)
    state = "READY" if not got["suspicious"] and not got["short"] \
        and not got["unverified"] and not got["unknown"] \
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
    lines += census_lines(board.get("td_census") or {})
    if got["books"]:
        books = ", ".join(f"{b} x{n}" for b, n in sorted(
            got["books"].items(), key=lambda kv: -kv[1]))
        lines += ["", f"  reference book(s): {books}"]
    if got.get("vigs"):
        lines.append(f"  measured overround: {got['vig_min']:.1%} low / "
                     f"{got['vig_median']:.1%} median / {got['vig_max']:.1%} "
                     f"high")
    if got.get("listed"):
        lines.append(f"  reference board size: {got['listed_min']} low / "
                     f"{got['listed_median']} median / {got['listed_max']} "
                     f"high  (a real scorer market runs 20-40)")
    for label, bucket in (("SHORT BOARDS (fewer than "
                           f"{MIN_BOARD} players listed)", got["short"]),
                          ("IMPLAUSIBLE VIG (under "
                           f"{got['floor']:.0%} off a full board)",
                           got["suspicious"])):
        if not bucket:
            continue
        lines += ["", f"  {label}:"]
        for r in bucket[:10]:
            lines.append(f"    {r.get('player','?'):<24} "
                         f"{r.get('odds', 0):>+6} "
                         f"vig {float(r.get('vig') or 0):>6.1%}  "
                         f"listed {int(r.get('vig_listed') or 0):>3}  "
                         f"{r.get('vig_source','')}")
    lines += ["", f"  {state}"]
    lines += [f"    - {w}" for w in why]
    return lines


def full_copy_of(path):
    """The private board behind a paywalled public one, or None.

    Resolved the same way `gate.publish` writes it — root-relative from
    the public path — rather than by jumping to a global directory, so a
    checkout that is not this one reads its own boards.
    """
    from pathlib import Path
    public = Path(path)
    # web/data/<name>.json -> <root>/data/built/<name>.json
    root = public.resolve().parent.parent.parent
    full = root / "data" / "built" / public.name
    return full if full.is_file() else None


def load(path) -> tuple[dict, str, str]:
    """``(board, path actually read, note)``.

    Follows a locked public board to its private copy. A board that is
    locked with no private copy behind it is reported as such rather than
    analysed, since the redacted payload carries no priced rows at all
    and would otherwise read as a clean empty board.
    """
    with open(path) as fh:
        board = json.load(fh)
    if not board.get("locked"):
        return board, str(path), ""
    full = full_copy_of(path)
    if not full:
        return board, str(path), (
            "this is the PUBLIC copy, which engine/gate strips of every "
            "priced row — and no private copy was found beside it. Run "
            "this against data/built/<name>.json instead")
    with open(full) as fh:
        board = json.load(fh)
    return board, str(full), ("the public copy is paywalled, so this read "
                              "the private board behind it")


def _main(argv) -> int:                          # pragma: no cover
    if not argv:
        print("usage: python3 -m engine.devigcheck <board.json> [more.json]")
        return 2
    worst = 0
    for path in argv:
        try:
            board, read, note = load(path)
        except (OSError, ValueError) as exc:
            print(f"\n{path}\n  cannot read: {exc}")
            worst = max(worst, 2)
            continue
        print(f"\n{path}")
        if note:
            print(f"  note: {note}")
        if read != str(path):
            print(f"  reading: {read}")
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
