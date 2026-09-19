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
    python3 homecheck.py grading       # GRADING: is every league's book settling?
    python3 homecheck.py record        # RECORD: does the page's file carry every league?
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


def _history_ro():
    """The results database, opened READ-ONLY, or ``(None, why)``.

    Same reasoning as `_journal_ro`: `db.connect()` runs the schema on
    first use, and this file promises every check is safe mid-cycle.
    """
    import sqlite3
    from engine import db
    path = db.DEFAULT_DB
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except Exception as exc:                                  # noqa: BLE001
        return None, f"cannot open {path} read-only — {type(exc).__name__}: {exc}"
    conn.row_factory = sqlite3.Row
    return conn, ""


def record() -> list:
    """RECORD. What the published record.json holds, against the journal.

    Ethan, 2026-09-19, with `grading` showing cfb 285 likely + 8 main +
    1 longshot settled — all three in books the Record page renders —
    and the page showing him nothing.

    EVERY LAYER BETWEEN THE TWO IS GENERIC, which is why this check
    exists rather than another guess. `TRACKED_SPORTS` includes cfb;
    `book_records` groups by sport with no league list; the scope chips
    loop `d.tracked_sports` and deliberately list a sport with nothing
    journaled rather than hide it; `recBookSections` indexes
    `br[scope]`. Nothing in that chain can single a league out.

    So the remaining question is not what the code does but what the
    FILE says, and whether it is the file the page is being served. This
    reads the published artifact and prints, per sport, what a reader
    would find in it — beside what the journal holds, so the two can
    disagree out loud instead of in a browser.
    """
    import datetime as _dt
    import json as _json
    from pathlib import Path as _P
    out = ["RECORD — what the published record.json holds, per sport",
           "  the artifact the Record page renders, against the journal"]
    try:
        from engine import gate
        path = gate.board_source(_P("web/data/record.json"))
        with open(path, encoding="utf-8") as fh:
            doc = _json.load(fh)
    except Exception as exc:                                  # noqa: BLE001
        return out + [f"  cannot read record.json — "
                      f"{type(exc).__name__}: {exc}"]
    out.append(f"  read: {path}")
    stamp = str(doc.get("generated_at") or "")
    age = ""
    try:
        made = _dt.datetime.fromisoformat(stamp)
        hrs = (_dt.datetime.now() - made).total_seconds() / 3600.0
        age = f"  ({hrs:.1f}h old)"
        if hrs > 6:
            age += "   !! STALE — the page is rendering an old export"
    except ValueError:
        pass
    out.append(f"  generated_at {stamp or '(none)'}{age}")
    out.append(f"  record_epoch {doc.get('record_epoch')}  "
               f"— rows before this date are NOT in the public record")
    tracked = list(doc.get("tracked_sports") or [])
    out.append(f"  tracked_sports {tracked}")

    by_sport = doc.get("by_sport") or {}
    books = doc.get("book_records") or {}
    # The quarantined books, per sport, added 2026-09-19 with the fix
    # that put them on the page. Printed here so "is college showing
    # every bet it placed?" can be answered from the terminal instead
    # of by scrolling the site.
    shadow = doc.get("shadow_books") or {}
    jc = (doc.get("journaled") or {}).get("by_sport") or {}
    conn, why = _journal_ro()
    if why:
        out.append(f"  {why}")
    for sp in sorted(set(tracked) | set(by_sport) | set(books) | set(shadow)):
        entry = (by_sport.get(sp) or {}).get("overall") or {}
        mine = books.get(sp) or {}
        # W-L, NOT SETTLED. `book_records` counts pushes in their own
        # `push` field, so `w + l` is the GRADED count and a pushed bet
        # is deliberately outside it — the ROI denominator excludes it
        # too. The number is labelled here because the reconciliation
        # below has to count the same thing, and once did not.
        shown = ", ".join(
            f"{k} {(b.get('w', 0) + b.get('l', 0))}"
            + (f" (+{b['push']} push)" if b.get("push") else "")
            for k, b in sorted(mine.items())
        ) or "(no book sections)"
        out.append(f"  {sp:5} by_sport settled {entry.get('settled', 0):5}  "
                   f"open {entry.get('open', 0):4}  |  books W-L: {shown}")
        mine_s = shadow.get(sp) or {}
        if mine_s:
            out.append("        also tracked, never staked: " + ", ".join(
                f"{k} {(b.get('w', 0) + b.get('l', 0))}"
                + (f" (+{b['push']} push)" if b.get("push") else "")
                for k, b in sorted(mine_s.items())))
        chip = jc.get(sp)
        if chip is not None:
            out.append(f"        scope chip reads "
                       f"{chip.get('settled', 0) + chip.get('open', 0)} "
                       f"({chip.get('settled', 0)} settled, "
                       f"{chip.get('open', 0)} open)")
        elif "journaled" not in doc:
            out.append("        !! no `journaled` key — this file predates "
                       "the chip-count fix; the chips are falling back to "
                       "the staked edge book and will under-read")
        if conn is None:
            continue
        # THE JOURNAL'S OWN ANSWER, beside it. A league the journal has
        # graded into a rendered book and the artifact does not carry is
        # the exact shape of Ethan's report, and no amount of reading
        # the front end finds it.
        try:
            from engine.ledger import BOOK_SECTIONS, RECORD_EPOCH
            cats = tuple(c for _k, _l, cs in BOOK_SECTIONS for c in cs)
            marks = ",".join("?" * len(cats))
            # WON AND LOST ONLY, to match the `w + l` printed above.
            #
            # This counted pushes too, and the sum it was compared
            # against never could. Ethan's run on 2026-09-19 therefore
            # reported "journal 1733 graded, file 1724 — 9 row(s) did
            # not reach the page" for the MLB, and all nine rows were on
            # the page: they were his pushed bets, sitting in the
            # `push` field the comparison did not read. A check that
            # invents a discrepancy is worse than no check — it sends
            # the next reader hunting an export bug that is not there,
            # which is exactly what it did.
            n = conn.execute(
                f"SELECT COUNT(*) FROM bets WHERE sport=? AND date >= ? "
                f"AND status IN ('won','lost') "
                f"AND category IN ({marks})",
                (sp, RECORD_EPOCH, *cats)).fetchone()[0]
        except Exception as exc:                              # noqa: BLE001
            out.append(f"         journal unreadable — "
                       f"{type(exc).__name__}: {exc}")
            continue
        if n and not mine:
            out.append(f"       !! the journal has graded {n} {sp} bet(s) into "
                       f"books the Record page renders, and the published "
                       f"file carries NONE of them — the export is the gap, "
                       f"not the journal")
        elif n:
            drawn = sum(b.get("w", 0) + b.get("l", 0) for b in mine.values())
            if drawn < n:
                out.append(f"       !! journal {n} W-L, file {drawn} — "
                           f"{n - drawn} graded row(s) did not reach the page")
    if conn is not None:
        conn.close()
    return out


def grading() -> list:
    """GRADING. Is each league's book actually settling, and if not, why.

    Ethan, 2026-09-18: "CFB still hasn't graded any edge bets or most
    likely bets."

    A bet that cannot settle does not announce itself.
    `settle_from_history` says so in its own docstring — "bets whose
    games haven't been ingested yet simply stay open" — and an open bet
    waiting on Saturday's kickoff looks exactly like an open bet waiting
    on a results feed that stopped landing in August. One resolves
    itself; the other never will, and both read as a quiet book.

    THE REASONS COME FROM `ledger.why_open`, not from a second opinion
    written here. That function already classifies every open bet whose
    day is done — "no results ingested", "player has no log", "market not
    ingested", "game not found" — and it is what `doctor.py` reads. The
    gap this check closes is not that nothing knew: it is that the thing
    that knew was in a command nobody runs daily, which is the same
    shape as every other finding in this file.

    THE SETTLED COUNT IS PRINTED BESIDE IT, because "0 open past the
    window" means nothing on its own. A league that has graded 400 bets
    and a league that has never graded one can both be quiet today.
    """
    out = ["GRADING — is each league's book settling, and if not, why",
           "  settled vs open, and the reason every stuck bet is stuck"]
    conn, why = _journal_ro()
    if why:
        return out + [f"  {why}"]
    hconn, hwhy = _history_ro()
    if hwhy:
        out.append(f"  {hwhy}")
    try:
        counts = conn.execute(
            "SELECT sport, status, COUNT(*) n FROM bets GROUP BY sport, status"
        ).fetchall()
    except Exception as exc:                                  # noqa: BLE001
        conn.close()
        return out + [f"  journal unreadable — {type(exc).__name__}: {exc}"]

    by_sport: dict = {}
    for r in counts:
        by_sport.setdefault(str(r["sport"]), {})[str(r["status"])] = r["n"]

    stuck: dict = {}
    if hconn is not None:
        try:
            from engine import ledger
            import datetime as _dt
            for row in ledger.why_open(conn, hconn, _dt.date.today().isoformat()):
                key = (str(row.get("sport") or "?"), str(row.get("reason") or "?"))
                stuck[key] = stuck.get(key, 0) + 1
        except Exception as exc:                              # noqa: BLE001
            out.append(f"  why_open failed — {type(exc).__name__}: {exc}")

    # WHICH SLATES THE JOURNAL ACTUALLY HOLDS, per league.
    #
    # Ethan, 2026-09-19: "can we still fill the record page with all the
    # bets that we have made since week zero". The answer is exactly the
    # set of rows in this table and nothing else — `docs/BACKUPS.md` is
    # explicit that only the journal and the accounts are backed up and
    # "everything else regenerates from the pipeline", so there is no
    # archive of a past board to reconstruct a pick from. A bet the
    # journal never recorded cannot be recovered, and inventing one now
    # from an old board would be choosing what we would have bet after
    # seeing the result.
    #
    # So the honest question is not "can we grade the season" but "how
    # many days of it did we write down", and that is what this prints.
    slates: dict = {}
    try:
        for r in conn.execute(
                "SELECT sport, date, COUNT(*) n FROM bets "
                "GROUP BY sport, date ORDER BY sport, date"):
            slates.setdefault(str(r["sport"]), []).append((str(r["date"]),
                                                           r["n"]))
    except Exception as exc:                                  # noqa: BLE001
        out.append(f"  slate breakdown unavailable — "
                   f"{type(exc).__name__}: {exc}")

    # WHICH BOOK, because that is the question the Record page answers.
    #
    # Ethan, 2026-09-18: "CFB still hasn't graded any edge bets or most
    # likely bets" — and the 2026-09-19 run came back `cfb 446 settled`.
    # Both are true. `ledger.BOOK_SECTIONS` is Edge (main/paper), Most
    # Likely (likely) and Long Shots (longshot), and `book_records` says
    # in as many words that "sections a sport has never journaled are
    # simply absent". Everything else in the journal — `stale` flags,
    # `potd`, `loose` — is measured and never shown as a section. So a
    # league can settle hundreds of bets into the shadow books and put
    # nothing at all on the page, and a per-SPORT total cannot tell that
    # apart from a healthy record.
    books: dict = {}
    try:
        from engine.ledger import BOOK_SECTIONS
        shown = {c: key for key, _, cats in BOOK_SECTIONS for c in cats}
        for r in conn.execute(
                "SELECT sport, category, status, COUNT(*) n FROM bets "
                "GROUP BY sport, category, status"):
            books.setdefault(str(r["sport"]), {}).setdefault(
                str(r["category"]), {})[str(r["status"])] = r["n"]
    except Exception as exc:                                  # noqa: BLE001
        shown = {}
        out.append(f"  book breakdown unavailable — "
                   f"{type(exc).__name__}: {exc}")

    SETTLED = ("won", "lost", "push", "void")
    for sport in sorted(by_sport):
        st = by_sport[sport]
        done = sum(st.get(k, 0) for k in SETTLED)
        openn = st.get("open", 0)
        out.append(f"  {sport:5} {done:5d} settled  |  {openn:5d} open"
                   + (f"   ({', '.join(f'{k} {st[k]}' for k in SETTLED if st.get(k))})"
                      if done else ""))
        # The books, and whether each one reaches the Record page.
        mine_books = books.get(sport) or {}
        if mine_books:
            on_page = 0
            for cat in sorted(mine_books):
                st = mine_books[cat]
                done = sum(st.get(k, 0) for k in SETTLED)
                sec = shown.get(cat)
                where = (f"Record page \u2192 {sec}" if sec
                         else "shadow book, never on the Record page")
                if sec and done:
                    on_page += done
                out.append(f"          {cat:10} {done:6d} settled  "
                           f"{st.get('open', 0):5d} open   {where}")
            # ONLY WHEN THERE IS SOMETHING TO MISPLACE. A league that has
            # graded nothing at all is the `HAS NEVER GRADED` case below;
            # saying its graded rows are in the wrong book would be
            # describing rows that do not exist.
            if done and not on_page:
                out.append(f"       !! NOTHING {sport.upper()} HAS SETTLED "
                           f"REACHES THE RECORD PAGE \u2014 every graded row is "
                           f"in a shadow book, so the page shows this league "
                           f"no record at all")
        days = slates.get(sport) or []
        if days:
            out.append(f"          {len(days)} slate(s) journaled, "
                       f"{days[0][0]} \u2192 {days[-1][0]}")
            if len(days) <= 6:
                for d, n in days:
                    out.append(f"            {d:12} {n:5d} bet(s)")
        mine = {r: n for (sp, r), n in stuck.items() if sp == sport}
        for reason, n in sorted(mine.items(), key=lambda x: -x[1]):
            out.append(f"          {n:4d} stuck past the settle window — {reason}")
        # THE LOUD CASE. A league that has never graded anything is not a
        # quiet week; it is a book that has never closed a bet, and if
        # its stuck rows blame the ingest then nothing it holds will ever
        # grade on its own.
        if not done and openn:
            out.append(f"       !! {sport.upper()} HAS NEVER GRADED A BET "
                       f"({openn} open, 0 settled) — this is not a quiet "
                       f"week, it is a book that has never closed one")
        if mine.get("no results ingested"):
            out.append(f"       !! {mine['no results ingested']} {sport} bet(s) "
                       f"are waiting on results that were never stored — the "
                       f"ingest is the fix, not the settler; these will not "
                       f"grade on their own")
    if not by_sport:
        out.append("  the journal holds no bets at all")
    conn.close()
    if hconn is not None:
        hconn.close()
    return out


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

    AND WHICH BOOKS THE TAB EVEN DRAWS, because without that the two
    numbers do not appear to reconcile and a healthy league reads as a
    hole. Ethan's 2026-09-18 run showed `nfl 39 tracked` over
    `journal: 101 open` — a 62-row gap, and not one row missing: 59 of
    those are `stale`, the shadow book that measures line-staleness at a
    zero stake, and the Live tab has never drawn it. `TRACKER_CATEGORIES`
    is main/longshot/likely, plus the Pick of the Day on its own key, and
    nothing else. So every line now says whether it is a book the tab
    draws, and the arithmetic is printed rather than left to be done from
    memory.

    THE SHOUT COUNTS ONLY THOSE BOOKS, for the same reason. Reading the
    whole open count made a league whose only open rows are measurement
    rows look like a broken tracker — a false alarm on the honest state
    of a quiet day.
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
        # The books the Live tab draws, straight off the engine's own
        # tuples rather than a copy of them here — a second list would
        # drift the first time a book is added and this check would go on
        # calling the new one invisible.
        from engine.livepicks import (POTD_TRACKER_CATEGORIES,
                                      TRACKER_CATEGORIES)
        shown_books = set(TRACKER_CATEGORIES) | set(POTD_TRACKER_CATEGORIES)
        shown = sum(r["n"] for r in openrows
                    if str(r["category"]) in shown_books)
        # ON THE BOARD'S DATE, which is the number the tracker can
        # actually reach: the right-hand side of the reconciliation.
        reachable = sum(r["n"] for r in openrows
                        if str(r["category"]) in shown_books
                        and str(r["date"]) == date)
        out.append(f"       journal: {total} open {sport} bet(s) — "
                   f"{shown} in the books the Live tab draws")
        for r in openrows:
            cat = str(r["category"])
            on_date = str(r["date"]) == date
            if cat not in shown_books:
                note = "   measurement book, never on the tab"
            elif on_date:
                note = "   shown  <- the board's date"
            else:
                note = "   !! a shown book under another date — INVISIBLE"
            out.append(f"         {str(r['date']):12} "
                       f"{cat:16} {r['n']:3d}{note}")
        drawn = len(rows) + len(potd)
        out.append(f"       reconciles: {drawn} drawn "
                   f"({len(rows)} tracked + {len(potd)} pick of the day) "
                   f"vs {reachable} reachable"
                   + ("" if drawn == reachable else "   !! THESE DISAGREE"))
        # TWO DIFFERENT FAILURES, AND THEY NEED SAYING SEPARATELY.
        #
        # The first draft of this shouted only on `reachable and not
        # drawn`, which is a dead guard for the case the check was
        # WRITTEN for: rows filed under a date the tracker cannot match
        # have `reachable == 0`, so the one condition could never fire on
        # them. Both are named now.
        invisible = shown - reachable
        if invisible:
            out.append(f"       !! {invisible} row(s) in books the tab draws "
                       f"are filed under a date that is NOT the board's — "
                       f"`open_bets_for` matches it exactly, so they are "
                       f"invisible on the Live tab and will stay that way")
        if reachable and not drawn:
            out.append("       !! the journal holds bets in books the tab "
                       "draws, on the board's OWN date, and the board "
                       "tracks none of them — the tracker itself is not "
                       "working")
        # AN OPEN ROW FROM A SLATE THAT IS OVER, in a book the tab never
        # draws: not a tracking problem, and not nothing either — nothing
        # downstream will ever close it. Ethan's 2026-09-18 run carried
        # one, an NFL `stale` flag still open under 2026-W01 a week on.
        # Shown books under an old date get the louder line above instead
        # of being counted twice here.
        stranded = sum(r["n"] for r in openrows
                       if str(r["date"]) != date
                       and str(r["category"]) not in shown_books)
        if stranded:
            out.append(f"       note: {stranded} measurement row(s) still "
                       f"open under a past slate — a settling gap, not a "
                       f"tracking one")
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
    "grading": (grading, "GRADING: is each league's book settling, and why not",
                True),
    "record": (record, "RECORD: what the published record.json holds", True),
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
