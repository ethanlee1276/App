#!/usr/bin/env python3
"""The droplet checks from docs/WHEN_YOU_ARE_HOME.md, as commands.

WHY THIS EXISTS. Ethan, 2026-09-16, after running five blocks from that
file successfully: *"i couldnt get that last command to work"* — the
FILLER check, which is a thirty-line `python3 - <<'PY'` heredoc. A
heredoc pasted into an interactive shell is a dozen ways to fail that
have nothing to do with the question being asked: a stray `^C`, a
terminal that eats a blank line, a client that reflows long lines, a
paste that arrives while the previous command is still printing. The
five that worked were all ONE LINE.

So the checks live here and the runbook says `python3 homecheck.py
filler`. The code is the same code, under test, and a fix to it is a
`git pull` rather than a new thing to paste.

READ-ONLY, ALL OF IT. Nothing here writes, journals, fetches a price or
takes a lock, so every subcommand is safe on the production box
mid-cycle. The one repair in that file (`repair_inverted_likely_sides`)
is deliberately NOT here — a writing command should look different from
a reading one.

    python3 homecheck.py filler        # FILLER: did the -110 filler die?
    python3 homecheck.py exchange      # KX-2: what the Kalshi tickers look like
    python3 homecheck.py head          # which commit this box is running
    python3 homecheck.py all           # every read-only check, in order

Each check prints a header and then its own lines, so the whole output
can be pasted back as one block.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: Leagues with a game board, in the order the runbook reads them.
SPORTS = ("mlb", "nfl", "cfb")


def head() -> list:
    """Which commit is deployed. EVERY OTHER CHECK DEPENDS ON THIS ONE:
    a before-picture read as an after-picture is the single most common
    way one of these runs wastes a morning."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h %ad %s", "--date=short"],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as exc:                                  # noqa: BLE001
        out = f"(could not read git: {type(exc).__name__}: {exc})"
    return [f"HEAD: {out}"]


def _board(sport: str):
    """This league's published board, through the same three lookups
    every other droplet tool uses.

    `launch.BOARD_FILES` because a board is NOT named after its league
    (the NFL writes `recommendations.json`), `lightboard.light_path`
    because the light copy is the small one, and `gate.board_source`
    because `web/data` is the PUBLIC copy and the paywall strips it —
    the mistake that made PIN-3 report a confident zero for five boards.
    """
    import launch
    from engine import gate, lightboard
    path = gate.board_source(lightboard.light_path(launch.BOARD_FILES[sport]))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def filler() -> list:
    """FILLER. Game rows priced at -110 with no book behind them.

    A total or team total the engine invented a price for, rather than
    one a book posted. `59becc8` took it out of the totals and `70ee99f`
    out of team totals, so on a box running either or later every count
    below should be zero.
    """
    out = ["FILLER — game rows at a filler price with no book",
           "  expect 0 at a filler price on all three leagues "
           "(59becc8 and 70ee99f)"]
    for sport in SPORTS:
        try:
            board = _board(sport)
        except Exception as exc:                              # noqa: BLE001
            out.append(f"  {sport:4} cannot read board — "
                       f"{type(exc).__name__}: {exc}")
            continue
        rows = board.get("game_bets") or []
        unbooked = [r for r in rows if not str(r.get("book") or "").strip()]
        bad = [r for r in unbooked if r.get("odds") in (-110, 110)]
        # AND WHETHER ANY OF THEM IS BEING RECOMMENDED, which is the
        # question the filler count leaves open. Ethan's 2026-09-16 run
        # read "nfl 80 game rows | 32 name no book | 0 at a filler
        # price" — the filler is dead, and 32 rows still carry a price
        # nobody is named as posting. #207 made `pipeline` set
        # `recommended = False` on exactly those, so this number should
        # be zero; if it is not, that guard is not reaching them.
        pushed = [r for r in unbooked if r.get("recommended")]
        by_mkt: dict = {}
        for r in bad:
            key = r.get("bet_type")
            by_mkt[key] = by_mkt.get(key, 0) + 1
        out.append(f"  {sport:4} {len(rows):3d} game rows | "
                   f"{len(unbooked):3d} name no book | "
                   f"{len(bad):3d} at a filler price {by_mkt or ''}")
        if pushed:
            out.append(f"       !! {len(pushed)} of those unbooked rows are "
                       f"still RECOMMENDED — #207's guard is not reaching "
                       f"them")
    return out


def exchange(fetch=None) -> list:
    """KX-2. What this box's Kalshi tickers actually look like.

    THE ONE THAT FETCHES. Everything else here reads a file; this calls
    the exchange. It is keyless and costs no credits, but it writes into
    the shared fetch cache — so run this script as the build user, not
    as root, or the cache entries come back root-owned and every later
    build silently falls back to a stale copy. That is not hypothetical:
    6,098 such files had accumulated by 2026-09-16.

        sudo -u qellys python3 homecheck.py exchange

    ``fetch`` is injected so the tests stay offline, the same seam
    `kalshi.fetch_sports_markets` already takes its parser through. A
    test that reaches the real exchange is a test that fails when the
    network does and tells you nothing about this function either way.
    """
    from engine import exchangefair
    from engine.sources import kalshi
    out = ["EXCHANGE — Kalshi game markets, six rows per sport"]
    if os.geteuid() == 0:
        out.append("  !! RUNNING AS ROOT. This writes cache files and they "
                   "will come back root-owned; re-run with "
                   "`sudo -u qellys python3 homecheck.py exchange`.")
    try:
        markets, meta = (fetch or (
            lambda: kalshi.fetch_sports_markets(kalshi.parse_markets)))()
    except Exception as exc:                                  # noqa: BLE001
        return out + [f"  the feed did not answer — "
                      f"{type(exc).__name__}: {exc}"]
    out.append(f"  series report: {meta}")
    for sport in ("nfl", "mlb"):
        mine = [m for m in markets if kalshi.sport_of(m) in (None, sport)]
        usable = [m for m in mine if not exchangefair.quality(m)]
        out.append(f"  === {sport}: {len(usable)} usable of {len(mine)} ===")
        for m in usable[:6]:
            out.append("    " + json.dumps(
                {k: m.get(k) for k in
                 ("ticker", "event_ticker", "title", "subtitle")},
                ensure_ascii=False))
    return out


#: Subcommand name -> (function, one-line description). `all` runs every
#: entry whose third field is True — `exchange` is excluded because it is
#: the only one that touches the network and the only one that cares
#: which user is running it.
CHECKS = {
    "head": (head, "which commit this box is running", True),
    "filler": (filler, "FILLER: game rows at -110 with no book", True),
    "exchange": (exchange, "KX-2: Kalshi ticker shapes (FETCHES; "
                           "run as the build user)", False),
}


def run(name: str) -> int:
    if name == "all":
        names = [k for k, v in CHECKS.items() if v[2]]
    elif name in CHECKS:
        names = [name]
    else:
        print(f"unknown check {name!r}. Available:")
        for key, (_fn, desc, _auto) in CHECKS.items():
            print(f"  {key:10s} {desc}")
        print("  all        every read-only check, in order")
        return 2
    for i, key in enumerate(names):
        if i:
            print()
        try:
            for line in CHECKS[key][0]():
                print(line)
        except Exception as exc:                              # noqa: BLE001
            # ONE CHECK'S FAILURE IS NOT THE RUN'S. `all` exists so a
            # person pastes one command and gets everything; a traceback
            # in the middle would take the rest of the output with it.
            print(f"{key}: FAILED — {type(exc).__name__}: {exc}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        print("\nchecks:")
        for key, (_fn, desc, _auto) in CHECKS.items():
            print(f"  {key:10s} {desc}")
        print("  all        every read-only check, in order")
        return 0
    return run(argv[0])


if __name__ == "__main__":
    sys.exit(main())
