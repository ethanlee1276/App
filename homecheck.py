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


#: Stuck reasons a re-ingest actually fixes. "player has no log" is a
#: name-map or a DNP, "game not found" is usually a postponement that
#: wants a void, and neither is helped by fetching the day again —
#: printing a command for those would send the next reader in a circle.
_REINGEST_FIXES = ("day barely ingested", "no results ingested")


def _game_days(conn, ids) -> list:
    """The distinct CALENDAR days behind a set of stuck bet ids."""
    if not ids:
        return []
    out = set()
    # Chunked: SQLite's variable limit is 999 and a stuck list can be
    # longer than that — 143 today, and a bad week would be more.
    ids = [i for i in ids if i is not None]
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for r in conn.execute(
                f"SELECT DISTINCT game_day FROM bets WHERE id IN ({marks})",
                chunk):
            if r[0]:
                out.add(str(r[0]))
    return sorted(out)


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


def edge() -> list:
    """EDGE. Does the book we actually stake make money? (read-only)

    Ethan, 2026-09-19, after the stale book's promotion verdict came
    back "hold" for every sport with three of the four measured
    NEGATIVE: the question that decides what to build next is not why
    college has no edge bets, it is whether the edge bets we DO place
    are worth placing.

    Nothing else prints this plainly. The Record page shows a verdict
    gated below the ledger's own sample bar, which is right for a public
    page and useless for deciding where to spend a week. This is the
    same numbers ungated, per sport, with the sample beside each so a
    thin one cannot be mistaken for evidence.

    CUT BY GRADE as well, because the edge book is not one selector. A
    sharp-anchored card, a model card and (since today) a promoted
    stale flag all land in `main`, and pooling them hides which one is
    carrying the book — or sinking it.
    """
    out = ["EDGE — does the staked book make money, per sport",
           "  category main+paper, stake above zero, since the record epoch"]
    conn, why = _journal_ro()
    if conn is None:
        return out + [f"  {why}"]
    try:
        from engine import ledger as _l
        def _line(name, p):
            n = p.get("settled", 0)
            if not n:
                out.append(f"  {name:6} nothing settled")
                return
            roi = (p.get("roi") or 0.0) * 100
            clv = p.get("avg_clv")
            thin = "" if n >= 100 else f"   !! {n} settled — too thin to call"
            out.append(
                f"  {name:6} {p.get('wins',0)}-{p.get('losses',0)}"
                f"-{p.get('pushes',0)}  {n:5} settled  ROI {roi:+6.2f}%  "
                f"net {p.get('net_units',0):+7.2f}u on "
                f"{p.get('units_staked',0):.1f}u"
                + (f"  CLV {clv:+.2f}" if clv is not None else "  CLV n/a")
                + thin)
        for sp in _l.TRACKED_SPORTS:
            _line(sp, _l.performance(conn, sp, since=_l.RECORD_EPOCH))
        _line("ALL", _l.performance(conn, since=_l.RECORD_EPOCH))
        out.append("")
        out.append("  by grade — which selector earned it")
        rows = conn.execute(
            "SELECT grade, COUNT(*) n, SUM(status='won') w, "
            "SUM(status='lost') l, COALESCE(SUM(pnl_units),0) u, "
            "COALESCE(SUM(CASE WHEN status='push' THEN 0 ELSE stake_units "
            "END),0) s FROM bets WHERE category IN ('main','paper') "
            "AND stake_units > 0 AND status IN ('won','lost','push') "
            "AND date >= ? GROUP BY grade ORDER BY n DESC",
            (_l.RECORD_EPOCH,)).fetchall()
        if not rows:
            out.append("    (nothing settled in the edge book yet)")
        for r in rows:
            roi = (r["u"] / r["s"] * 100) if r["s"] else 0.0
            out.append(f"    {str(r['grade'] or '(none)'):12} "
                       f"{r['w']}-{r['l']}  {r['n']:5} rows  ROI {roi:+6.2f}%")
        # The promotion ladder beside it: where the next selector is.
        out.append("")
        out.append("  stale-line book — the promotion ladder")
        v = _l.stale_verdict(conn, since=_l.RECORD_EPOCH)
        if not v:
            out.append("    (no settled flags yet)")
        for sp, e in sorted(v.items(), key=lambda kv: -kv[1]["n"]):
            mark = "PROMOTE" if e["verdict"] == "promote" else "hold   "
            out.append(f"    {sp:5} {mark} {e['n']:5} flags  "
                       f"hit {e['hit_rate']*100:.1f}% vs {e['break_even']*100:.1f}% "
                       f"break-even  z {e['z']:+.2f}  ROI {e['roi']*100:+.2f}%")
            out.append(f"          {e['why']}")
    except Exception as exc:                                  # noqa: BLE001
        out.append(f"  journal unreadable — {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return out


def data() -> list:
    """DATA. What we store, whether any model reads it, and how fast we
    are on injury news. (read-only)

    Ethan, 2026-09-19: "figure out what data we need to source and what
    we can use to make all of our edge bets and all of our most likely
    bets better. I know it's out there."

    Some of it is already here. `engine.datause` registers twelve
    signals by hand and reports them all healthy; the table audit asks
    the DATABASE instead, which cannot forget a store nobody
    registered — and the first run found `injury_events` written every
    night and selected from by nothing.

    The second half measures that store: for every filing, did the
    player's own line move after we first saw the news, and by how
    much. A positive lead is the edge. A negative one says the market
    knew first and the fix is a faster feed, not a better model.
    """
    out = ["DATA — what we store, and whether it earns its keep"]
    try:
        from engine.datause import table_report
        out += table_report().splitlines()
    except Exception as exc:                                  # noqa: BLE001
        out.append(f"  table audit failed — {type(exc).__name__}: {exc}")
    conn, why = _history_ro()
    if conn is None:
        return out + [f"  {why}"]
    try:
        from engine.injurylag import report as _lag
        out += _lag(conn).splitlines()
    except Exception as exc:                                  # noqa: BLE001
        out.append(f"  injury lag failed — {type(exc).__name__}: {exc}")
    finally:
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
    stuck_ids: dict = {}
    if hconn is not None:
        try:
            from engine import ledger
            import datetime as _dt
            for row in ledger.why_open(conn, hconn, _dt.date.today().isoformat()):
                key = (str(row.get("sport") or "?"), str(row.get("reason") or "?"))
                stuck[key] = stuck.get(key, 0) + 1
                stuck_ids.setdefault(key, []).append(row.get("id"))
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
        # THE OTHER BOOKS THE PAGE DRAWS, since 2026-09-19. This map
        # was the three headline sections only, so every other category
        # printed "never on the Record page" — which was true that
        # morning and stopped being true the same afternoon. A check
        # that keeps asserting a fixed bug is worse than one that never
        # noticed it: Ethan read "NOTHING UFC HAS SETTLED REACHES THE
        # RECORD PAGE" hours after the UFC card was wired to draw.
        try:
            from engine.ledger import SHADOW_SECTIONS as _SHADOW
            shown.update({c: f"{key} (also tracked, never staked)"
                          for key, _l, cats in _SHADOW for c in cats})
        except ImportError:
            pass
        # Two books with a section of their own rather than a slot in
        # either map — see `recPotdSection` and `recUfcSection`.
        shown.setdefault("potd", "Pick of the Day")
        shown.setdefault("ufc", "the UFC card")
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
                # A BENCHED LEAGUE IS THE INTENDED CASE, NOT THE BUG.
                # Ethan, 2026-09-21: "I don't want wnba Past bet or new
                # bet on the record page." Every graded row being off
                # the page is what he asked for, and a check that keeps
                # shouting about a thing somebody decided on teaches
                # whoever reads it to skip the line that matters.
                try:
                    from engine.ledger import is_benched as _benched
                except ImportError:                     # pragma: no cover
                    _benched = lambda _s: False         # noqa: E731
                if _benched(sport):
                    out.append(f"          benched \u2014 kept off the Record "
                               f"page on purpose, still graded here "
                               f"({done} settled)")
                else:
                    out.append(f"       !! NOTHING {sport.upper()} HAS SETTLED "
                               f"REACHES THE RECORD PAGE \u2014 every graded "
                               f"row is in a shadow book, so the page shows "
                               f"this league no record at all")
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
            # AND THE COMMAND THAT CLEARS IT, ready to paste.
            #
            # Ethan, 2026-09-19: 143 NFL bets on "day barely ingested".
            # The check named the cause and left him to work out which
            # days and what to type, which is most of the work. The
            # dates come from `game_day`, the CALENDAR day — the NFL
            # journals week labels like "2026-W01" and `ingest.py`
            # wants days, so printing `date` here would hand him a
            # command that cannot run.
            if reason not in _REINGEST_FIXES:
                continue
            ids = stuck_ids.get((sport, reason)) or []
            days = _game_days(conn, ids)
            if not days:
                out.append("               (no calendar day stamped on these "
                           "rows — nothing to re-ingest by date)")
                continue
            out.append(f"               python3 ingest.py {sport} --dates "
                       + ",".join(days))
            out.append("               then: python3 launch.py --settle all")
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


def bench() -> list:
    """BENCH. What benching a league did to the record it left.

    Ethan, 2026-09-21: "Are roi and record should be better now that
    wnba is removed" — and the honest answer was that nobody had
    measured it. WNBA came off the record page because he asked for it,
    not because it was shown to be losing. If it was winning, benching
    it made the headline WORSE, and there was no way to see that.

    THE COMPARISON IS THE POINT, not WNBA's number on its own. A
    benched league's ROI read beside nothing is a number without a
    verdict; read beside the book with and without it, it says plainly
    what the bench bought or cost.

    FEWER BETS IS NOT A BETTER RECORD, which is why the settled counts
    are printed as loudly as the ROI. A book that improved by shedding
    a third of its sample has a prettier number and a weaker claim, and
    a check that showed only the ROI would be selling the first while
    hiding the second.

    UNITS, NOT DOLLARS. `bench_existing` zeroes `stake_dollars` when it
    moves a row — that is what takes the league off the money — so a
    benched league's dollar ROI has no denominator left and is not
    reconstructible. Units, wins, losses and `pnl_units` are untouched,
    and units are the honest measure of a book anyway.
    """
    from engine import ledger
    out = ["BENCH — what the bench did to the record it left"]
    benched = tuple(ledger.BENCHED_SPORTS)
    if not benched:
        return out + ["  no league is benched — nothing to measure"]
    out.append(f"  benched: {', '.join(benched)}   "
               f"(units only; benched dollars are zeroed by design)")
    conn, why = _journal_ro()
    if conn is None:
        return out + [f"  {why}"]

    BOOK = ledger.BOOK
    BENCH = (ledger.BENCH_CATEGORY,)

    def line(tag, p):
        roi = p.get("roi")
        return (f"  {tag:24} {p['settled']:5d} settled  "
                f"{p['wins']}-{p['losses']}"
                + (f"-{p['pushes']}" if p.get("pushes") else "")
                + f"  {p['net_units']:+8.2f}u  "
                + (f"ROI {roi * 100:+6.2f}%" if roi is not None
                   else "ROI    —   ")
                + f"  ({p.get('units_staked', 0):.1f}u staked)")

    try:
        now = ledger.performance(conn)
        was = ledger.performance(conn, category=BOOK + BENCH,
                                 exclude_sports=())
        out.append("")
        out.append("  THE EDGE BOOK — the headline, with and without them")
        out.append(line("now (benched out)", now))
        out.append(line("with them back in", was))
        # The verdict, said rather than left to be worked out.
        if not was["settled"]:
            # AN EMPTY BOOK IS NOT AN UNCHANGED ONE. Printing "ROI
            # unchanged by 0.00 points" over nothing reads as a measured
            # finding, and this check exists because an unmeasured claim
            # was being taken for one.
            out.append("       → nothing has settled in either book yet "
                       "— the bench has not cost or saved anything "
                       "that can be measured")
        elif now.get("roi") is not None and was.get("roi") is not None:
            pts = (now["roi"] - was["roi"]) * 100
            lost = was["settled"] - now["settled"]
            verb = "better" if pts > 0 else ("worse" if pts < 0 else "unchanged")
            out.append(f"       → the bench made the headline ROI {verb} "
                       f"by {abs(pts):.2f} points, on {lost} fewer settled "
                       f"bets")
            if pts < 0:
                out.append("       !! IT IS WINNING. Benching cost the "
                           "record rather than saved it — emptying "
                           "`ledger.BENCHED_SPORTS` puts it back")

        out.append("")
        out.append("  EACH BENCHED LEAGUE, ON ITS OWN")
        for sp in benched:
            out.append(line(sp + " (edge)",
                            ledger.performance(conn, sp, category=BENCH)))
            # The other books it still writes to, graded and unpublished.
            for cat, label in (("likely", "most likely"),
                               ("likely_live", "most likely (staked)"),
                               ("potd", "pick of the day"),
                               ("longshot", "long shots"),
                               ("stale", "stale flags"),
                               ("form", "form sampler"),
                               ("loose", "looser gates")):
                p = ledger.performance(conn, sp, category=cat)
                if p["settled"] or p["open"]:
                    out.append(line(f"{sp} {label}", p))

        out.append("")
        out.append("  EVERY LEAGUE, so a benched one is compared rather "
                   "than assumed")
        for sp in ledger.TRACKED_SPORTS:
            off = ledger.is_benched(sp)
            p = ledger.performance(conn, sp,
                                   category=BENCH if off else BOOK)
            if p["settled"] or p["open"]:
                out.append(line(sp + (" (benched)" if off else ""), p))
    except Exception as exc:                                  # noqa: BLE001
        out.append(f"  unavailable — {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return out


def sizing() -> list:
    """SIZING. What to stake on the likelihood board, and what it buys.

    Ethan, 2026-09-21: *"we need to figure out what unit sizes and money
    sizes makes the most sense and make the most money and highest roi
    on the most likley bets."*

    THE FIRST COLUMN ANSWERS HALF OF IT BY BEING CONSTANT. A flat stake
    cannot change ROI — net over staked scales together — so the replay
    below prints the same percentage on every row, deliberately. Size
    decides the money and the drawdown. Which rows get taken decides the
    percentage, and that is `live_verdict`'s job, not this one.

    The recommendation and every input behind it come from
    `engine.likelysize`; this prints them so a stake on the board can be
    traced to the rows that set it.
    """
    from engine import likelysize as size
    from engine import ledger
    out = ["SIZING — what to stake on the likelihood board",
           "  a flat stake cannot change ROI; it changes the money and "
           "the drawdown"]
    conn, why = _journal_ro()
    if conn is None:
        return out + [f"  {why}"]
    try:
        live = [sp for sp in ledger.LIKELY_LIVE_SPORTS
                if not ledger.is_benched(sp)]
        if not live:
            return out + ["  no league's board is staked"]
        for sp in live:
            rows = size._rows(conn, sp)
            m = size.measure(rows)
            rec = size.recommend(m)
            out.append("")
            out.append(f"  {sp.upper()}  —  {m['n']} settled across "
                       f"{m['slates']} slates (paper rows included: same "
                       f"picks, and ROI does not care what they cost)")
            if not m["n"]:
                out.append("        nothing staked has settled yet; the "
                           f"stake holds at the floor of {size.FLOOR_U}u")
                continue
            out.append(f"        hit {m['hit']:.1%} · ROI {m['roi']:+.2%} "
                       f"· average payout {m['b']:.2f} per unit")
            out.append(f"        NOW {size.FLOOR_U}u  →  "
                       f"RECOMMENDED {rec['units']}u")
            # Wrapped by hand: this is the sentence that justifies real
            # money, and a 300-character line in a terminal is not read.
            words, line = rec["why"].split(), "       "
            for w in words:
                if len(line) + len(w) + 1 > 76:
                    out.append(line)
                    line = "       "
                line += " " + w
            out.append(line)
            out.append("")
            out.append("        if it kept doing what it has done:")
            out.append("          size     net       ROI      worst run   "
                       "one bad night")
            for r in size.replay(rows, sorted({0.25, 0.5, rec["units"],
                                               1.0, 2.0})):
                out.append(
                    f"          {r['units']:>4}u  {r['net_units']:+8.2f}u  "
                    f"{r['roi'] * 100:+6.2f}%  {r['max_drawdown_u']:+8.2f}u   "
                    f"{r['if_a_slate_all_lost_u']:+8.1f}u")
            out.append(f"        the last column is the biggest slate "
                       f"this board has had ({m['slate_max']} rows) "
                       f"losing in full \u2014")
            out.append("        the loss the ROI column cannot show you.")
    except Exception as exc:                                  # noqa: BLE001
        out.append(f"  unavailable — {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return out


def shelves() -> list:
    """SHELVES. Which markets the record says to stop staking.

    Ethan, 2026-09-21: "what makes people the most money without losing
    the most money alongside increasing and boosting our ROI record."

    A FLAT STAKE CANNOT MOVE ROI. The only thing that raises the
    percentage is taking fewer, better bets, and this is the table that
    says which ones to stop taking. See `engine/shelfstop.py` for the
    two bars a shelf has to fail before it is cut.
    """
    from engine import shelfstop
    out = ["SHELVES — which markets the record says to stop staking",
           f"  two bars: {shelfstop.MIN_N}+ settled, two standard errors "
           f"clear of zero on the losing side, AND surviving",
           f"  false-discovery control at q<{shelfstop.FDR_ALPHA} over "
           f"every shelf judged"]
    conn, why = _journal_ro()
    if conn is None:
        return out + [f"  {why}"]
    try:
        d = shelfstop.decide(shelfstop.measure(conn))
        rows = sorted(d["shelves"], key=lambda r: (r["z"] is None, r["z"]))
        if not rows:
            return out + ["  nothing settled in the money book yet"]
        out.append(f"  {d['tested']} of {len(rows)} shelves had enough rows "
                   f"to judge")
        out.append("")
        out.append("   sport market            n     ROI       z    verdict")
        for r in rows:
            z = "   —  " if r["z"] is None else f"{r['z']:+6.2f}"
            mark = {"stop": " <<< STOP", "review": " (watch)"}.get(
                r["verdict"], "")
            out.append(f"   {r['sport']:5} {r['market']:15} {r['n']:5} "
                       f"{r['roi'] * 100:+7.2f}%  {z}  {r['verdict']}{mark}")
        if d["stopped"]:
            out.append("")
            out.append("  STOPPED — these are refused on the next build:")
            for x in d["stopped"]:
                out.append(f"    {x['sport']} {x['market']}: {x['why']}")
        else:
            out.append("")
            out.append("  nothing is stopped. A shelf losing on its own z "
                       "but not past the control reads (watch) —")
            out.append("  that is a shelf to look at, not one the record "
                       "has convicted.")
    except Exception as exc:                                  # noqa: BLE001
        out.append(f"  unavailable \u2014 {type(exc).__name__}: {exc}")
    finally:
        conn.close()
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
    "edge": (edge, "EDGE: does the staked book make money, and which "
                   "selector earned it", True),
    "bench": (bench, "BENCH: what benching a league did to the record it "
                     "left", True),
    "sizing": (sizing, "SIZING: what to stake on the likelihood board, and "
                       "what it buys", True),
    "shelves": (shelves, "SHELVES: which markets the record says to stop "
                         "staking", True),
    "data": (data, "DATA: what we store, whether a model reads it, and "
                   "how fast we are on injury news", True),
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
