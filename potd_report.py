#!/usr/bin/env python3
"""What the Pick of the Day saw, chose, and refused — on a real board.

Ethan, 2026-09-15: "I wanna make sure we access all the data we can and
all the tools we can to dish out the best picks of the day possible."

THE QUESTION THIS ANSWERS is the one no test can. The suite proves the
selector obeys its rules; it cannot say whether a real Tuesday board
carries anything for those rules to bite on. If the answer on the
droplet is "68 rows considered, 61 outside the band, 7 with only our own
model behind them, 0 picks", that is not a bug — it is the pool being
wrong, and it names which gate to argue with.

READ-ONLY. It opens the published board JSON, runs `potd.choose` over
it, and prints. Nothing is written, nothing is journaled, no price is
fetched, so it is safe to run on the production box mid-cycle.

    python3 potd_report.py                    # every board in web/data
    python3 potd_report.py nfl cfb            # just these
    python3 potd_report.py --dir /srv/qellys/web/data
    python3 potd_report.py nfl --rows 12      # show the near misses

WHY IT LIVES AT THE ROOT rather than under engine/: it is a droplet
tool, in the same family as `stale_lines.py` and `shopping_value.py`,
and those are where a person looks for it.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import potd                                       # noqa: E402

#: Boards that carry a `most_likely` list. Same spelling the builds use.
BOARDS = ("mlb", "nfl", "cfb", "nba", "wnba")


def board_paths(sport: str, where: str) -> list:
    """Every file that might carry this league’s board, best first.

    THE BUG THIS EXISTS FOR, and it is the third instance of the same
    one in a day. A board’s file is NOT named after its league: the NFL
    writes `recommendations.json` and MLB `mlb_recommendations.json`;
    only cfb, nba and wnba happen to match their own code. This tool
    looked for `{sport}_picks.json`, so it silently skipped the two
    leagues at the top of SPORT_PRIORITY — and its "no board found"
    message only fires when NOTHING is found, so with college football
    present it reported happily and said nothing about the other two.

    `launch.BOARD_FILES` is the registry every other reader uses and
    `lightboard.light_path` is the one definition of the light copy’s
    name, so both are asked rather than guessed at. The light copy is
    preferred because it is small and carries `pick_of_the_day` whole
    (`lightboard.DROP_TOP` drops only `player_stats`); the full board is
    the fallback for a box that has not written one yet.

    AND EVERY CANDIDATE GOES THROUGH `gate.board_source`, which is the
    bug Ethan hit on 2026-09-15. `web/data` is the PUBLIC copy, and
    `most_likely` is on `gate.PAID_KEYS` — so on the droplet, with the
    paywall on, this tool read five leagues off five stripped boards and
    printed “the board carries no Most Likely rows at all” five times,
    on a box whose journal held a locked pick made that morning. It
    reported honestly on nothing, which is exactly the shape
    `board_source`’s own docstring names five prior victims of.

    `board_source` falls back to the public path when there is no
    private copy, so a dev box with the paywall off is unaffected.
    """
    out = []
    try:
        import launch
        from engine import lightboard
        rel = launch.BOARD_FILES.get(sport)
        if rel:
            name = os.path.basename(rel)
            out.append(os.path.join(where, os.path.basename(
                lightboard.light_path(name))))
            out.append(os.path.join(where, name))
    except Exception:                                         # noqa: BLE001
        # A checkout without the launcher importable still gets the
        # conventional names rather than nothing at all.
        pass
    out.append(os.path.join(where, f"{sport}_picks.json"))
    out.append(os.path.join(where, f"{sport}.json"))
    try:
        from engine import gate
        out = [str(gate.board_source(p)) for p in out]
    except Exception:                                         # noqa: BLE001
        # Same reasoning as above: a checkout that cannot import the
        # gate still reads SOMETHING rather than nothing. It will be the
        # public copy, which is the pre-2026-09-15 behaviour and is
        # correct on any box with the paywall off.
        pass
    seen, uniq = set(), []
    for path in out:
        if path not in seen:
            seen.add(path)
            uniq.append(path)
    return uniq


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:                                  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"}


def _bet_name(row: dict) -> str:
    """How this tool SPELLS a bet: "TOR Moneyline", "OVER 8 Total",
    "LAA +1.5 Spread".

    Split out of `_one_line` below when the published card wanted the
    same spelling without the fair and the EV beside it. Every trap in
    here was a real line off Ethan’s board on 2026-09-15, and a second
    copy of the join would step into all of them again.
    """
    market = str(row.get("market") or "")
    who = row.get("player") or row.get("team") or "?"
    what = row.get("market_label") or row.get("market") or ""
    side = str(row.get("side") or "").strip()
    line = row.get("line")
    # A GAME TOTAL'S `player` IS NOT A NAME. It holds the journal key —
    # "Over 51.5" — so leading with it and then printing the side and the
    # line prints the number three times:
    #
    #     Over 51.5 OVER 51.5 Total      (Ethan's board, 2026-09-15)
    #     Over 8 OVER 8.0 Total          (…and inconsistently formatted)
    #
    # `renderPickOfTheDay` in web/js/app.js already refuses it, in that
    # file's own words: "a game total's [player] holds the journal key, so
    # neither is a name to print". This is the same rule, in the tool that
    # reads the same board.
    if market == "total":
        who = ""
    # A MONEYLINE HAS NO LINE AND SAYS ITS MARKET ONCE. `player` is the
    # journal key "TOR ML" and `line` is the 0.0 every moneyline row
    # carries, so the join read "TOR ML 0.0 Moneyline" — a number that
    # means nothing beside a market named twice. Same board, same night.
    if market == "moneyline":
        line = None
        if who.upper().endswith(" ML"):
            who = who[:-3].strip()
    # THE LINE, ONCE. A game spread carries the signed number as its side
    # ("+1.5") and the same number again as `line`, so the naive join
    # reads "LAA +1.5 1.5 Spread" — the same bug Ethan caught on the card
    # (2026-09-15), in this tool's own copy of the join.
    try:
        if line is not None and abs(float(side)) == abs(float(line)):
            line = None
    except (TypeError, ValueError):
        pass
    # 8.0 AND 8 ARE THE SAME TOTAL. `line` arrives as a float from the
    # board and as an int from some makers, and a card reading "Over 8
    # OVER 8.0" is the join showing its seams.
    if isinstance(line, float) and line.is_integer():
        line = int(line)
    side = side.upper()
    return " ".join(str(x) for x in (who, side, line, what)
                    if x is not None and str(x).strip())


def _one_line(row: dict) -> str:
    """A candidate in a line: who, at what, on whose say-so."""
    odds = row.get("odds")
    fair = potd.fair_prob(row)
    ev = potd.edge(row)
    bits = [_bet_name(row),
            f"{odds:+d}" if isinstance(odds, (int, float)) else str(odds),
            f"{potd.evidence(row)} fair {fair:.1%}" if fair is not None else "no fair",
            f"{ev:+.1%} EV" if ev is not None else "no EV"]
    if row.get("reserve"):
        bits.append("[reserve]")
    return "  ".join(str(b) for b in bits)


def _ladders(payload: dict) -> dict:
    """``{(player, market): [rung, ...]}`` off the recommendation rows.

    The Most Likely rows do not carry the ladder; the Edge board's rows
    in the SAME published file do (`pipeline._rec_to_dict`), and the two
    are keyed the same way. Read-only: nothing here prices a rung, it
    only asks what numbers exist.
    """
    out: dict = {}
    for r in (payload.get("recommendations") or []):
        if not isinstance(r, dict):
            continue
        alts = r.get("alt_lines") or []
        if alts:
            out[(str(r.get("player") or ""), str(r.get("market") or ""))] = alts
    return out


def _ladder_note(rows, payload) -> list:
    """Lines saying how many band-refused rows have a band-legal rung."""
    ladders = _ladders(payload)
    if not ladders:
        return []
    refused = [r for r in rows
               if potd.disqualify(r) == "the payout is outside the even-money band"]
    if not refused:
        return []
    reachable, examples = 0, []
    for r in refused:
        key = (str(r.get("player") or ""), str(r.get("market") or ""))
        hit = None
        for ln in ladders.get(key) or []:
            for side in ("over_odds", "under_odds"):
                if potd.in_band(ln.get(side)):
                    hit = (ln.get("line"), ln.get(side), ln.get("book"))
                    break
            if hit:
                break
        if hit:
            reachable += 1
            if len(examples) < 3:
                examples.append(
                    f"{key[0]} {key[1]} at {r.get('odds')} → "
                    f"{hit[0]} at {hit[1]:+d} ({hit[2]})")
    if not reachable:
        return [f"  Ladder      {len(refused)} row(s) refused on price, none "
                f"with a rung inside the band — nothing to recover here."]
    out = [f"  Ladder      {reachable} of {len(refused)} price-refused row(s) "
           f"HAVE a rung inside the band, unreached today:"]
    out.extend(f"    {e}" for e in examples)
    return out


def _exchange_lines(payload: dict, tiers: dict) -> list:
    """Why the TOP rung of the ladder is empty, in the tool that shows it
    empty.

    THE ANSWER WAS ALREADY ON DISK. `exchangefair.attach_to_board` runs in
    every build and writes its funnel into the board as
    `exchange_fair_census` — how many markets it could use, how many rows
    it priced, and the quality reason for each market it threw away. It
    also returns a one-line summary, which each build PRINTS, and which
    the launcher swallows on a successful cycle: `journalctl` for "line
    ledger" comes back empty on a box whose line ledger is demonstrably
    writing, and this hook is relayed exactly the same way.

    So the state on 2026-09-15 was a report saying "0 exchange" five times
    beside a census, in the same file, explaining it — and no way to see
    the second without opening the JSON by hand. That is the same failure
    as the Most Likely board reading empty: the fact was not missing, the
    reader was.

    Silent when the tier landed rows, because then there is nothing to
    explain; silent on a board with no exchange census at all, which is
    every board built before the hook existed.
    """
    err = payload.get("exchange_fair_error")
    census = payload.get("exchange_fair_census")
    if tiers.get("exchange"):
        return []                       # the tier worked; nothing to say
    if err:
        return [f"  Exchange    the feed did not answer — {err}",
                "              (Kalshi is keyless and costs no credits, so "
                "this is the venue or the network, not the budget)"]
    if not isinstance(census, dict) or not census:
        return ["  Exchange    this board carries no exchange census — the "
                "build's `exchangefair` hook did not run or did not reach "
                "the board file."]
    try:
        from engine.exchangefair import NO_MATCH, NO_SIDE
    except Exception:                                         # noqa: BLE001
        NO_MATCH = "no exchange market for this game"
        NO_SIDE = "the exchange priced this game but not this side"
    seen = census.get("rows", 0)
    usable = census.get("usable markets", 0)
    unmatched = census.get(NO_MATCH, 0)
    wrong_side = census.get(NO_SIDE, 0)
    # ROW REASONS AND MARKET REASONS ARE DIFFERENT JOBS, and the first cut
    # of this printed them in one list under a heading that said "markets
    # refused" — so "4 no exchange market for this game", which is about
    # ROWS and is the whole answer, sat in the middle of eighteen market
    # widths. Ethan's 2026-09-15 output is the example: MLB read 62 usable
    # markets and 0 of 4 rows priced, and the reason was buried.
    # COUNTS ONLY. `attach` now carries two SAMPLE LISTS back as well
    # (see below), and formatting a list with "{n} {k}" would print
    # "['Angels vs Mariners'] unmatched market titles" in among the book
    # widths — a number about our own logging, in the place a reader is
    # looking for a number about the exchange.
    # QUALITY AND MATCHING ARE DIFFERENT STEPS, and this line is about
    # the first one. A market that failed to MATCH passed quality — it
    # is inside the `usable` count — so printing it here is a false
    # statement about the exchange's book. Ethan's 2026-09-16 MLB run is
    # the example: "14 neither the title nor the ticker names both
    # clubs" sat among twenty-odd book widths and read as a venue
    # problem when it is ours.
    try:
        from engine.sources.kalshi import MATCH_REASONS
    except Exception:                                         # noqa: BLE001
        MATCH_REASONS = ()
    skip = {"rows", "attached", "usable markets", "games on the board",
            "markets matched to a game", NO_MATCH, NO_SIDE, *MATCH_REASONS}
    why = ", ".join(f"{n} {k}" for k, n in sorted(census.items())
                    if isinstance(n, int) and k not in skip)
    unmatched_markets = ", ".join(
        f"{census[k]} {k}" for k in MATCH_REASONS if census.get(k))
    out = [f"  Exchange    0 of {seen} moneyline row(s) priced  ·  "
           f"{usable} usable market(s)"]
    # THE HEADLINE FIRST, ALWAYS — it was conditional on there being no
    # market refusals, which is exactly backwards: a board with refusals
    # is the one that needs telling which of them mattered.
    if not seen:
        out.append("              no moneyline rows on this board to price — "
                   "the exchange lists game winners and nothing else, so a "
                   "board of player props can never reach this tier.")
    elif unmatched and unmatched >= seen:
        out.append(f"              every row ({unmatched}) matched no market, "
                   f"with {usable} usable — this is OUR name matching, not "
                   f"the venue's liquidity.")
    elif unmatched:
        out.append(f"              {unmatched} of {seen} row(s) matched no "
                   f"market; the rest were priced but did not attach.")
    elif wrong_side:
        # A DIFFERENT DIAGNOSIS WITH A DIFFERENT FIX. The exchange DID
        # price these games — `kalshi.yes_team` could not say which club
        # the YES pays on, or the row is on a side the contract does not
        # name. Sending a reader to the name matching for this would be
        # sending them to the wrong file.
        out.append(f"              the exchange priced {wrong_side} of these "
                   f"{seen} game(s) but not the side the row takes — this is "
                   f"`kalshi.yes_team`, not the name matching.")
    elif usable:
        out.append("              markets were usable but none reached a row "
                   "on this board.")
    # BOTH SPELLINGS, SIDE BY SIDE. "Every row matched no market" is as
    # true of a naming mismatch as of a board a day stale, and the only
    # way to tell from a report is to read what each side called the
    # game. Ethan's 2026-09-16 NFL output — nine rows, 58 usable, zero
    # matched — could have been either, and cost a morning for it.
    titles = census.get("unmatched market titles") or []
    mine = census.get("board matchups") or []
    if titles and not tiers.get("exchange"):
        out.append(f"              exchange says:  {'; '.join(titles)}")
        out.append(f"              the board says: {'; '.join(mine) or '(no games)'}"
                   f"   [{census.get('games on the board', 0)} game(s) on the "
                   f"board, {census.get('markets matched to a game', 0)} "
                   f"market(s) matched one]")
    if why:
        out.append(f"              markets refused on quality: {why}")
    if unmatched_markets:
        out.append(f"              markets that passed quality and matched no "
                   f"game: {unmatched_markets}")
    return out


def _published_call(payload: dict) -> list:
    """What the PAGE is telling a reader to do, read off the card.

    Everything else in this report is a fresh re-derivation over the
    board’s rows, and that is the right thing for a diagnosis — but it
    is not always what is on screen. `ledger.relock_potd` re-points the
    published card at the pick this sport locked hours earlier, so the
    card can be showing a bet at a price the live rows would now refuse,
    or showing nothing at all while the rows below it still offer a
    lean. An operator asking "what does the site say right now" was
    getting the answer to a different question.

    `potd.verdict` is not recomputed here. The card carries its own
    (`potd.build`, `potd.relock`), and a report that derived a second
    one would be the second definition this whole feature has spent two
    days removing.

    Returns [] for a board built before the verdict shipped — a report
    that invents "NO BET" out of a missing field would be worse than one
    that says nothing about it.
    """
    card = payload.get("pick_of_the_day")
    if not isinstance(card, dict):
        return []
    v = card.get("verdict")
    if not isinstance(v, dict) or not v.get("call"):
        return []
    pick = card.get("pick") if isinstance(card.get("pick"), dict) else {}
    marks = []
    if pick.get("locked"):
        marks.append("locked earlier today")
    if pick.get("off_board"):
        marks.append("read back from the journal")
    if card.get("relocked"):
        marks.append(str(card["relocked"]))
    tail = f"   [{'; '.join(marks)}]" if marks else ""
    if str(v["call"]) == "bet":
        where = _bet_name(pick) if pick else "?"
        odds = v.get("odds", pick.get("odds"))
        book = str(v.get("book") or pick.get("book") or "").strip()
        price = f" ({odds:+d})" if isinstance(odds, int) else ""
        at = f" at {book}" if book else ""
        return [f"  PUBLISHED   BET {v.get('stake'):g}u on "
                f"{where}{at}{price}{tail}"]
    why = str(v.get("why") or "").strip() or "nothing cleared the bar"
    return [f"  PUBLISHED   NO BET — {why}{tail}"]


def report(payload: dict, sport: str, rows_shown: int = 5) -> str:
    if payload.get("_error"):
        return f"{sport.upper()}: could not read the board — {payload['_error']}"
    rows = [r for r in (payload.get("most_likely") or []) if isinstance(r, dict)]
    pick, near, census = potd.choose(rows)
    out = [f"{sport.upper()}  ·  board built {payload.get('built_at', '?')}  ·  "
           f"{len(rows)} row(s) considered"]
    out.extend(_published_call(payload))

    if not rows:
        out.append("  The board carries no Most Likely rows at all — the pool "
                   "is empty before this feature is even asked.")
        return "\n".join(out)

    # WHERE THE ROWS WENT, biggest gate first. This is the whole point:
    # a day with no pick should say which bar was binding rather than
    # shrugging, exactly as `likely.build`'s own funnel does.
    out.append(f"  Band        {potd.MIN_ODDS:+d} to {potd.MAX_ODDS:+d} "
               f"(pays {potd.MIN_PAYOUT:.2f}u to {potd.MAX_PAYOUT:.2f}u)  ·  "
               f"EV floor {potd.MIN_EV:.0%}  ·  fair floor {potd.MIN_FAIR:.0%}")
    # WHOSE OPINION THIS BOARD IS MADE OF, before any bar is applied.
    #
    # Ethan's MLB card, 2026-09-15, read "only our own model disputes
    # this price" — and the useful question is not why that ONE row was
    # refused, it is whether ANY row on that board had a sharper witness.
    # "68 rows: 0 sharp, 0 market, 68 model" says the sharp prices are
    # not arriving at all, which is a pull problem and not a selector
    # one, and no amount of arguing with the bars would have found it.
    tiers: dict = {}
    for r in rows:
        tiers[potd.evidence(r)] = tiers.get(potd.evidence(r), 0) + 1
    spread = ", ".join(f"{tiers.get(t, 0)} {t}" for t in potd.EVIDENCE)
    out.append(f"  Evidence    {spread}")
    if not tiers.get("sharp") and not tiers.get("market"):
        out.append("              NO sharp or market witness anywhere on this "
                   "board — every row is our own number, so the selector "
                   "cannot take any of them. Check the odds pull for this "
                   "league before touching a bar.")
    out.extend(_exchange_lines(payload, tiers))
    # WHAT AN ALTERNATE-LINE PURCHASE COULD ADDRESS (#253). Printed only
    # when something WAS refused on price — on a board where nothing was,
    # the answer is a line of zeroes and the report is long enough.
    try:
        from engine.potd import price_gap, price_gap_lines
        _gap = price_gap(rows)
        if _gap.get("refused_on_price"):
            out.extend(price_gap_lines(_gap))
    except Exception as _exc:                                 # noqa: BLE001
        out.append(f"  Alternate lines  could not be counted — {_exc}")

    if census:
        out.append("  Refused:")
        for why, n in sorted(census.items(), key=lambda kv: -kv[1]):
            out.append(f"    {n:>4}  {why}")

    if pick is not None:
        out.append(f"  PICK        {_one_line(pick)}")
    elif near is not None:
        out.append(f"  no pick     best available: {_one_line(near)}")
        out.append(f"              ({potd.shortfall(near)}) — shown, not recorded")
    else:
        out.append("  no pick     and nothing in the band at a real price to show")

    # WHAT THE ALTERNATE LADDER COULD RECOVER, which is the one lever
    # this feature has not pulled yet and the reason to measure before
    # building it.
    #
    # A -400 read is outside the band by the widest margin available, and
    # the same book quotes the same team at other numbers — a -1.5 spread
    # at -130, say — so the read is not unbettable, it is unbettable AT
    # THAT PRICE. `likely._best_rung` already walks that ladder, but it
    # picks the rung with the highest PROBABILITY subject to the Most
    # Likely board's bars, and `likely._row_from` then drops `alt_lines`
    # from the row it emits. So the ladder never reaches this module.
    #
    # It IS still in the published board, on the recommendation rows
    # (`pipeline._rec_to_dict`). This counts, WITHOUT PRICING ANYTHING,
    # how many band-refused rows have a rung that would have been in the
    # band — which is the number that says whether wiring it through is
    # worth a new pricing path or is chasing nothing.
    out.extend(_ladder_note(rows, payload))

    # The near misses, so a reader can see what one gate away looks like.
    misses = [r for r in rows if not potd.disqualify(r) and potd.shortfall(r)]
    if misses and rows_shown:
        misses.sort(key=potd.rank_key)
        out.append(f"  In the band but short ({len(misses)}):")
        for r in misses[:rows_shown]:
            out.append(f"    {_one_line(r)}")
            out.append(f"        {potd.shortfall(r)}")
    return "\n".join(out)


def top_report(boards: dict, today: str, locked) -> str:
    """The cross-league layer, board answer beside locked answer.

    TWO RUNS, AND THE GAP BETWEEN THEM IS THE POINT. `potd.day_top_pick`
    with no lock says what the boards would choose right now; with the
    lock it says what may actually be published. When those differ, a
    league has moved off the pick it journaled this morning — which is
    ordinary and correct, and is also the single thing most likely to
    make somebody think the feature is broken when it is working.
    """
    from engine import potd
    lines = [f"DAY TOP PICK  ·  {today}"]
    live = potd.day_top_pick(boards, today)
    held = potd.day_top_pick(boards, today, locked=locked)
    lines.append(f"  boards say : {potd.top_pick_line(live)[len('top pick: '):]}")
    lines.append(f"  locked     : {potd.top_pick_line(held)[len('top pick: '):]}")
    if locked is None:
        lines.append("  (no ledger on this box — the locked line is the "
                     "board line)")
    elif not locked:
        lines.append("  NOTHING IS LOCKED TODAY. Every league’s pick was "
                     "below its bar, or no build has journaled yet — either "
                     "way nothing qualifying can be published.")
    else:
        lines.append("  locked picks in the journal today:")
        for sport in sorted(locked):
            player, market, side, line = locked[sport]
            lines.append(f"    {sport:<5} {player} {side} {line} {market}")
    same = ((live.get("sport"), (live.get("pick") or {}).get("player"))
            == (held.get("sport"), (held.get("pick") or {}).get("player")))
    if not same:
        lines.append("  ⚠️  THE TWO DISAGREE — a league is showing a "
                     "different pick than the one it locked. The locked "
                     "line is what the site publishes.")
    census = held.get("census") or {}
    if census:
        lines.append("  why each league contributed nothing:")
        for why in sorted(census):
            lines.append(f"    {why}")
    return "\n".join(lines)


def load_boards(where: str, sports) -> dict:
    """``{sport: board}`` for the cross-league report."""
    out = {}
    for sport in sports:
        path = next((p for p in board_paths(sport, where)
                     if os.path.exists(p)), None)
        if path is not None:
            out[sport] = _load(path)
    return out


def read_lock(today: str):
    """Today’s journaled picks, or None when there is no ledger here.

    None and {} MEAN DIFFERENT THINGS and the report says which: None is
    "this box has no journal to ask", {} is "asked, nothing locked". The
    second is a real answer about the day; the first is a missing tool.
    """
    try:
        from engine import ledger
        with ledger.connect() as conn:
            return ledger.locked_potd_keys(conn, today)
    except Exception:                                         # noqa: BLE001
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sports", nargs="*", help="leagues to report (default: all found)")
    ap.add_argument("--dir", default=os.path.join("web", "data"),
                    help="where the *_picks.json boards live")
    ap.add_argument("--rows", type=int, default=5,
                    help="how many near misses to print per board (0 for none)")
    ap.add_argument("--top", action="store_true",
                    help="the cross-league day top pick, board vs locked")
    args = ap.parse_args(argv)

    if args.top:
        import datetime as _dt
        today = _dt.date.today().isoformat()
        sports = [s.lower() for s in args.sports] or list(BOARDS)
        print(top_report(load_boards(args.dir, sports), today,
                         read_lock(today)))
        return 0

    wanted = [s.lower() for s in args.sports] or list(BOARDS)
    found, absent = 0, []
    for sport in wanted:
        path = next((p for p in board_paths(sport, args.dir)
                     if os.path.exists(p)), None)
        if path is None:
            # A league that simply is not in season is not an error — but
            # it is NAMED at the end rather than skipped in silence, which
            # is how this tool hid two leagues from its own reader.
            absent.append(sport)
            continue
        found += 1
        print(report(_load(path), sport, args.rows))
        print()
    if absent:
        print(f"No board on disk for: {', '.join(absent)} "
              f"(not in season, or that build has not run).")
        print()
    if not found:
        looked = os.path.join(args.dir, "*_picks.json")
        have = sorted(os.path.basename(p) for p in glob.glob(looked))
        print(f"No board found for {', '.join(wanted)} in {args.dir!r}.")
        print(f"  Present: {', '.join(have) if have else '(nothing)'}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
