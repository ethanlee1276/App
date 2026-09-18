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
    python3 homecheck.py live          # LIVE: does the Live tab have bets to draw?
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


def _journal_ro():
    """The bet journal, opened READ-ONLY, or ``(None, why)``.

    NOT `ledger.connect()`, which is the obvious call and the wrong one
    here twice over. It runs the migrations and the schema script on the
    first connection in a process — writes, taking the exclusive lock on
    the file the refresher and the settler are both using — and this
    script's docstring promises every subcommand is safe mid-cycle. A
    `mode=ro` URI cannot take that lock and cannot be talked into it.

    AND IT IS THE RIGHT FILE. `db.connect()` opens history.db, which has
    no `bets` table; that swap cost Ethan a runbook command on
    2026-09-16 and came back as a raw sqlite error with no hint which
    database it was complaining about. The path is named in the failure
    line below for that reason.
    """
    import sqlite3
    from engine import ledger
    path = ledger.DEFAULT_DB
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except Exception as exc:                                  # noqa: BLE001
        return None, f"cannot open {path} read-only — {type(exc).__name__}: {exc}"
    conn.row_factory = sqlite3.Row
    return conn, ""


def live() -> list:
    """LIVE. What each league's Live tab has to draw, beside what the
    journal actually holds for that league.

    Ethan, 2026-09-18, during Lions-Bills: "we have a live nfl game right
    now and it's not showing any live edge or most likely bets in the
    live tab." The front end's half of that was a league selector that
    moved the games and not the bets. This is the OTHER half, and it is
    not answerable from a browser: whether the NFL board has any tracked
    rows to draw at all.

    THE TWO NUMBERS SIDE BY SIDE ARE THE POINT. `live_picks` is what the
    build put on the board; the journal lines under it are what is open
    in that sport, grouped by the `date` each row is filed under. The
    tracker matches those EXACTLY (`livepicks.open_bets_for`:
    `WHERE sport=? AND date=?`) against the board's own `date` — which
    for football is a WEEK LABEL, "2026-W03", not a day. A journal full
    of open bets under one label and a board carrying another is a
    tracker that finds nothing and says nothing, and that is invisible
    from the page: it reads exactly like a quiet night.
    """
    out = ["LIVE — the open-bet tracker, per league",
           "  board's live_picks/live_potd, against the journal's open rows"]
    conn, why = _journal_ro()
    if why:
        out.append(f"  {why}")
    for sport in SPORTS:
        try:
            board = _board(sport)
        except Exception as exc:                              # noqa: BLE001
            out.append(f"  {sport:4} cannot read board — "
                       f"{type(exc).__name__}: {exc}")
            continue
        rows = board.get("live_picks") or []
        potd = board.get("live_potd") or []
        date = str(board.get("date") or "")
        n_live = sum(1 for r in rows if r.get("phase") == "live")
        n_likely = sum(1 for r in rows if r.get("category") == "likely")
        out.append(f"  {sport:4} board date {(date or '(none)'):12} | "
                   f"{len(rows):3d} tracked ({n_live} live, {n_likely} likely)"
                   f" | {len(potd)} pick of the day")
        err = board.get("live_picks_error")
        if err:
            # The build wrote its own failure into the board so the page
            # could show it; print it here rather than leaving a zero to
            # be read as a quiet night.
            out.append(f"       !! live_picks_error: {err}")
        if conn is None:
            continue
        try:
            openrows = conn.execute(
                "SELECT date, category, COUNT(*) n FROM bets "
                "WHERE status='open' AND sport=? "
                "GROUP BY date, category ORDER BY date DESC, category",
                (sport,)).fetchall()
        except Exception as exc:                              # noqa: BLE001
            out.append(f"       journal unreadable — "
                       f"{type(exc).__name__}: {exc}")
            continue
        total = sum(r["n"] for r in openrows)
        out.append(f"       journal: {total} open {sport} bet(s)")
        for r in openrows:
            mark = "   <- the board's date" if str(r["date"]) == date else ""
            out.append(f"         {str(r['date']):12} "
                       f"{str(r['category']):16} {r['n']:3d}{mark}")
        if total and not rows and not potd:
            out.append("       !! the journal holds open bets and the board "
                       "tracks NONE — no line above is marked as the "
                       "board's date, so the tracker's exact match on it "
                       "found nothing")
    if conn is not None:
        conn.close()
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
    "live": (live, "LIVE: what the Live tab has to draw, per league", True),
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
