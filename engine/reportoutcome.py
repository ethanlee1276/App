"""How a finished game's picks and parlays did, read off the record (2026-11-16).

Ethan, 2026-11-16, on the finished Patriots at Lions page: "this page as well
should have if the game report was correct or not and go over all that was
right and wrong with the game report along if the parlays and picks did good."

The game's page grades the picks and tickets it still shows (js/app.js
pickResult, ticketResult). A game that started before its report was kept
(engine/reportkeep, 16 November) shows none of them: the board took them down
at the start. The record kept every one and graded it on the box score:

  * the picks, in the journal's books a game's page shows (BOOKS), each once
    (a report's pick is a Most Likely pick too; the first book names it);
  * the game's tickets (engine/parlayledger.log_game_parlays: sources
    `game_three` and `game_td`, `grade` the game's AWAY@HOME), each with its
    legs.

`of_game` reads them back for one finished game, read-only, and `attach` puts
them on each finished report as KEY from the report stage
(gamereport.keep_started), so the page says how they did whether or not it
still holds them, and the archive keeps it with the report
(engine/reportarchive). Read again on every build: a pick graded after the
first build past the final is counted on the next.

Standard library only; `attach` never raises.
"""
from __future__ import annotations

KEY = "outcome"
#: The record's books a game's page shows a pick from, the report's own
#: first: one pick in two books is counted once, under the first.
BOOKS = ("report", "likely", "board", "main", "paper", "longshot")
#: The journal's game markets (engine/ledger.GAME_MARKETS): a club or the
#: game in place of a player.
GAME_MARKETS = ("moneyline", "total", "spread", "team_total")
#: The tickets' sources (engine/gameparlays.SOURCES), by the page's names.
TICKETS = {"twos": "game_two", "threes": "game_three", "scorers": "game_td"}
#: A verdict the record has given; anything else is still open.
SETTLED = ("won", "lost", "push", "void")
#: A guard on one game's list, never a cut a real game reaches.
MAX_PICKS = 80
#: The report's own book (engine/reportbets.CATEGORY): the picks a game report posted, which
#: Report Picks lists (for_games). The game's page reads every book a pick of its can be in.
REPORT_BOOKS = ("report",)
#: Games one ask may name (for_games): the page asks a screenful at a time.
MAX_GAMES = 40


def _connect(path=None):
    """The journal, read-only; None when there is none."""
    import sqlite3
    from pathlib import Path
    if path is None:
        from . import ledger
        path = ledger.DEFAULT_DB
    p = Path(str(path))
    if not p.exists():
        return None
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)


def _dates(date) -> tuple:
    """One day or several, each once, the empties dropped: a game's journal rows are filed
    under its board's label (the NFL's week, "2026-W11") or under its own day."""
    seq = date if isinstance(date, (list, tuple)) else (date,)
    return tuple(dict.fromkeys(str(d) for d in seq if d))


def _status(s) -> str:
    s = str(s or "").lower()
    return s if s in SETTLED else "pending"


def _num(x):
    try:
        return None if x is None or x == "" else round(float(x), 2)
    except (TypeError, ValueError):
        return None


def names_in(report) -> set:
    """Every player a report names anywhere (normalized): a pick with no club
    on its row is this game's when the report names its player."""
    from .gameresults import norm
    out: set = set()

    def walk(x, depth=0):
        if depth > 12:
            return
        if isinstance(x, dict):
            if x.get("player"):
                out.add(norm(x["player"]))
            for v in x.values():
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x:
                walk(v, depth + 1)
    walk(report)
    out.discard("")
    return out


def picks(conn, sport: str, date, home: str, away: str, names=(), books=BOOKS) -> list:
    """The game's picks on the record, each once: a player's whose club is one
    of the two (or, with no club on the row, one the report names), and the
    game bets on either club or on the game. ``date`` is a day or several
    (_dates); ``books`` the journal's books read, the first naming a pick in two."""
    from .gameresults import norm
    days = _dates(date)
    books = tuple(books or BOOKS)
    if not days:
        return []
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    team = "team" if "team" in cols else "NULL"
    marks = ",".join("?" * len(books))
    rows = conn.execute(
        f"SELECT player, market, side, line, odds, status, actual, category, {team} FROM bets "
        f"WHERE sport=? AND date IN ({','.join('?' * len(days))}) AND category IN ({marks}) ORDER BY id",
        (sport, *days, *books)).fetchall()
    clubs = {str(home or ""), str(away or "")} - {""}
    game = f"{away}@{home}"
    names = set(names or ())
    seen: dict = {}
    for player, market, side, line, odds, status, actual, book, club in rows:
        m = str(market or "").lower()
        who = str(player or "")
        if not who or not m:
            continue
        if m in GAME_MARKETS:
            if who not in clubs and who.replace(" ", "") != game:
                continue
        elif club:
            if str(club) not in clubs:
                continue
        elif norm(who) not in names:
            continue
        k = (norm(who), m, str(side or "").upper(), _num(line))
        rank = books.index(book) if book in books else len(books)
        if k in seen and seen[k][0] <= rank:
            continue
        row = {"player": who, "market": m, "side": str(side or "").upper(), "line": _num(line),
               "status": _status(status), "book": book}
        if club:
            row["team"] = str(club)
        if m in GAME_MARKETS:
            row["game"] = True
            if who in clubs:
                row["team"] = who
        if odds not in (None, ""):
            try:
                row["odds"] = int(odds)
            except (TypeError, ValueError):
                pass
        a = _num(actual)
        if a is not None and row["status"] in ("won", "lost", "push"):
            row["actual"] = a
        seen[k] = (rank, row)
    out = [r for _rank, r in seen.values()]
    return out[:MAX_PICKS]


def tickets(conn, sport: str, date, home: str, away: str, with_key: bool = False,
            start_only: bool = False) -> dict:
    """The game's tickets on the record, by kind: each one's verdict and its legs'.
    ``date`` is a day or several (_dates); ``with_key`` gives each its journal key
    (engine/parlayledger.legs_key), which names the same ticket on the report;
    ``start_only`` keeps only the set its report carried at the start, as the
    Record counts them (parlayledger.mark_at_start): none for a game whose set
    was never kept."""
    from .parlayledger import AT_START
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    days = _dates(date)
    if "parlays" not in have or "parlay_legs" not in have or not days:
        return {}
    only = ""
    if start_only:
        if "at_start" not in {r[1] for r in conn.execute("PRAGMA table_info(parlays)")}:
            return {}
        only = f" AND {AT_START}"
    out: dict = {}
    for kind, source in TICKETS.items():
        rows = conn.execute(f"SELECT id, status, legs_key FROM parlays WHERE sport=? "
                            f"AND date IN ({','.join('?' * len(days))}) AND grade=? AND source=?{only} ORDER BY id",
                            (sport, *days, f"{away}@{home}", source)).fetchall()
        got = []
        for pid, status, key in rows:
            legs = []
            for player, team, market, side, line, st, actual in conn.execute(
                    "SELECT player, team, market, side, line, status, actual FROM parlay_legs "
                    "WHERE parlay_id=? ORDER BY leg_no", (pid,)).fetchall():
                leg = {"player": player or "", "market": str(market or "").lower(),
                       "side": str(side or "").upper(), "line": _num(line), "status": _status(st)}
                if team:
                    leg["team"] = team
                a = _num(actual)
                if a is not None and leg["status"] in ("won", "lost", "push"):
                    leg["actual"] = a
                legs.append(leg)
            if len(legs) >= 2:
                got.append({"status": _status(status), "legs": legs, **({"key": key or ""} if with_key else {})})
        if got:
            out[kind] = got
    return out


def of_game(conn, sport: str, date: str, g: dict, report: dict | None = None) -> dict:
    """{"picks": [...], "tickets": {"twos": [...], "threes": [...], "scorers": [...]}} for one
    game, each part only when the record holds some; {} when it holds none. The tickets are
    the set its report carried at the start, never the versions the board replaced before it
    (ZP, 2026-11-20: a game kept before 16 November read "1 of 42")."""
    home, away = str((g or {}).get("home") or ""), str((g or {}).get("away") or "")
    if not sport or not date or not home or not away:
        return {}
    out: dict = {}
    ps = picks(conn, sport, date, home, away, names_in(report) if report else ())
    if ps:
        out["picks"] = ps
    ts = tickets(conn, sport, date, home, away, start_only=True)
    if ts:
        out["tickets"] = ts
    return out


def for_games(sport: str, keys, member: bool = True, path=None, where=None) -> dict:
    """EVERY FINISHED GAME'S PICKS AND PARLAYS, EACH WON OR LOST (2026-11-17).

    Ethan, on Report Picks' "How our reports did": "I wanna be able too see
    each parlay and pick on this page along side and x or checkmark if the
    whole parlay hit and if the individual picks hit".

    For each archived game named in ``keys`` ((day, away, home), the page's
    rows; MAX_GAMES of them), the report's own picks (REPORT_BOOKS) and the
    game's tickets off the record, each with its verdict and each ticket's
    legs with theirs: {"DAY|AWAY|HOME": {"picks": [...], "twos": [...],
    "threes": [...], "scorers": [...], "held": n}} (the two-leg tickets from
    18 November, GPWIN1), a game the record holds nothing for as {}
    and one not archived left out. The archive says which board label the
    game's rows are filed under (its "label"; the NFL's is the week) and which
    players its report names (a pick with no club on its row).

    THE REPORT'S OWN TICKETS. The board posts a game's parlays and pairs
    afresh as lines and news move, and the record journals every
    version it posts (a week of them, for the NFL: 36 for one game). The
    archive keeps the set the report carried at the start ("parlays",
    engine/reportkeep), so those are the game's tickets here, in the report's
    order, and only those; a game whose set was never kept (before 16
    November) lists none, said so ("unkept"). A kind the league had on paper
    at the start was never posted: its kept tickets are under "paper" ({kind:
    [...]}) and the kinds are named in "on_paper" (`_own_tickets`).

    What has settled is public, as every settled row is (server._record_day:
    "the evidence the subscription is sold on"); a pick or ticket still
    waiting on its box score is a member's, and ``held`` tells the rest how
    many there are."""
    from . import reportarchive
    want = []
    for k in list(keys or [])[:MAX_GAMES]:
        try:
            day, away, home = (str(x) for x in k)
        except (TypeError, ValueError):
            continue
        doc = reportarchive.load(sport, day, away, home, where)
        if doc:
            want.append((f"{day}|{away}|{home}", day, away, home, doc))
    out: dict = {}
    if not want:
        return out
    conn = _connect(path)
    if conn is None:
        return out
    try:
        for key, day, away, home, doc in want:
            days = (doc.get("label"), day)
            ts = tickets(conn, sport, days, home, away, with_key=True)
            game = {"picks": [{k: v for k, v in p.items() if k != "book"}
                              for p in picks(conn, sport, days, home, away, names_in(doc.get("report")),
                                             books=REPORT_BOOKS)]}
            game.update(_own_tickets(ts, doc.get("parlays")))
            if not member:
                held = 0
                for part in ("picks", *TICKETS):
                    keep = [x for x in game.get(part) or [] if x.get("status") in SETTLED]
                    held += len(game.get(part) or []) - len(keep)
                    game[part] = keep
                for kind, lst in list((game.get("paper") or {}).items()):
                    keep = [x for x in lst if x.get("status") in SETTLED]
                    held += len(lst) - len(keep)
                    game["paper"][kind] = keep
                if game.get("paper"):
                    game["paper"] = {k: v for k, v in game["paper"].items() if v}
                for kind, lst in list((game.get("earlier") or {}).items()):
                    keep = [x for x in lst if x.get("status") in SETTLED]
                    held += len(lst) - len(keep)
                    game["earlier"][kind] = keep
                if game.get("earlier"):
                    game["earlier"] = {k: v for k, v in game["earlier"].items() if v}
                game["held"] = held
            out[key] = {k: v for k, v in game.items() if v}
    finally:
        conn.close()
    return out


#: Where a kept set holds a kind its league had on paper (the holds of 17-20 November, since retired).
PAPER_OF = {"threes": "paper_threes", "twos": "paper_twos"}


def _own_tickets(ts: dict, kept) -> dict:
    """The game's tickets as the report carried them at the start, in its order.

    ONE SET A GAME, AND NONE WHERE IT WAS NOT KEPT (ZP, 2026-11-20). Ethan, on
    rows reading "Parlays 0 of 28" and "1 of 42": "why do we have 30 parlays
    being made per game?? There should only be 3 parlays made per game". A game
    whose starting set was never kept (before 16 November), or whose kept set
    the record never journaled, listed every version the board posted as lines
    moved, none of them known to be the report's at the start and none counted
    on the Record; and a kept game counted the versions replaced before it
    ("earlier"). Neither is listed now: a game with no kept set says so
    ("unkept") when the record holds tickets for it.

    A KIND ITS LEAGUE HAD ON PAPER WAS NEVER POSTED (GPWIN2, 2026-11-18). The
    NBA's three-leg tickets went on paper on 17 November (9 of their last 100
    hit): built and graded, posted nowhere, and kept at the start under
    ``paper_threes``. Read only from ``threes``, that night's kept sets held
    nothing, so each game fell to "every version" and listed every ticket the
    board had built that day, the ones before the report's picks made them
    too, as the report's: 2 of 19 beside picks that hit 16 of 21. The kept
    set's paper tickets are its own here, under "paper", and the kinds it held
    on paper are named ("on_paper"), so the page can say they were never posted."""
    from .parlayledger import legs_key
    strip = lambda t: {k: v for k, v in t.items() if k != "key"}       # noqa: E731
    keys = lambda lst: [legs_key(t.get("legs") or []) for t in lst or []    # noqa: E731
                        if isinstance(t, dict) and len(t.get("legs") or []) >= 2]
    kept = kept if isinstance(kept, dict) else {}
    wanted = {kind: keys(kept.get(kind)) for kind in TICKETS}
    paper = {kind: keys(kept.get(PAPER_OF[kind])) for kind in PAPER_OF}
    named = {k for ks in (*wanted.values(), *paper.values()) for k in ks}
    on_record = {t.get("key") for kind in TICKETS for t in ts.get(kind) or []}
    # No set kept at the start (before 16 November), or one the record never
    # journaled: none listed. A kept set that held no ticket held none.
    if not kept or (named and not named & on_record):
        return {"unkept": True} if on_record else {}
    out: dict = {}
    held: dict = {}
    for kind in TICKETS:
        allk = ts.get(kind) or []
        order = {k: i for i, k in enumerate(wanted[kind])}
        out[kind] = [strip(t) for t in sorted((t for t in allk if t.get("key") in order),
                                              key=lambda t: order[t["key"]])]
        pk = {k: i for i, k in enumerate(paper.get(kind) or [])}
        mine = [strip(t) for t in sorted((t for t in allk if t.get("key") in pk), key=lambda t: pk[t["key"]])]
        if mine:
            held[kind] = mine
    if held:
        out["paper"] = held
    # THE VERSIONS POSTED EARLIER AND REPLACED BEFORE THE GAME (step ABB, 21 November 2026). Ethan, on the
    # 76ers at Bucks report: "I put in a bet that is no longer being recorded or shown in the game reports
    # ... it's losing me money, but then you're recording that we're winning money." Until that night a
    # game's parlays could change during its day, and only the set at the start was listed. Every other
    # version the record journaled for the game is listed too, apart ("earlier"), each with its mark;
    # never counted in the game's own tallies. From that night a posted parlay never changes
    # (engine/gameparlays.hold_posted), so a game posted after it has none.
    earlier: dict = {}
    for kind in TICKETS:
        # A kind its league had on paper that day was never posted, its versions no more than its kept ones.
        if kept.get(f"{kind}_paper"):
            continue
        named_k = set(wanted[kind]) | set(paper.get(kind) or [])
        rest = [strip(t) for t in ts.get(kind) or [] if t.get("key") not in named_k]
        if rest:
            earlier[kind] = rest
    if earlier:
        out["earlier"] = earlier
    on_paper = [kind for kind in PAPER_OF if kept.get(f"{kind}_paper")]
    if on_paper:
        out["on_paper"] = on_paper
    return out


def market_words(games: dict) -> dict:
    """The reader's word for every market these games' picks and legs name
    (engine/markets.label: "rush_yds" is "Rushing Yards"), so the page says
    them as the Record does whether or not it has read the record's own list."""
    from . import markets
    seen: set = set()
    for g in (games or {}).values():
        for p in (g or {}).get("picks") or []:
            seen.add(str(p.get("market") or ""))
        for kind in TICKETS:
            for t in (g or {}).get(kind) or []:
                for leg in t.get("legs") or []:
                    seen.add(str(leg.get("market") or ""))
    seen.discard("")
    return {m: markets.label(m) for m in sorted(seen)}


def attach(result: dict, reports: list, sport: str, path=None) -> int:
    """Each finished game's report given its picks and tickets off the record
    (KEY; taken off when the record holds none). Returns the reports given
    one; never raises."""
    try:
        date = str((result or {}).get("date") or "")
        games = {f"{g.get('away')}@{g.get('home')}|{str(g.get('date') or '')[:10]}": g
                 for g in (result or {}).get("games") or [] if isinstance(g, dict)}
        done = []
        for r in reports or []:
            if not isinstance(r, dict):
                continue
            g = games.get(f"{r.get('away')}@{r.get('home')}|{str(r.get('date') or '')[:10]}")
            if g and str((g.get("live") or {}).get("state") or "") == "final":
                done.append((r, g))
            else:
                r.pop(KEY, None)
        if not done or not date or not sport:
            return 0
        conn = _connect(path)
        if conn is None:
            return 0
        n = 0
        try:
            for r, g in done:
                got = of_game(conn, sport, date, g, r)
                if got:
                    r[KEY] = got
                    n += 1
                else:
                    r.pop(KEY, None)
        finally:
            conn.close()
        return n
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ finished games' picks not read off the record ({type(exc).__name__}: {exc})")
        return 0
