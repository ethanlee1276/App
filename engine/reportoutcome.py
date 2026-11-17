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
TICKETS = {"threes": "game_three", "scorers": "game_td"}
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


def tickets(conn, sport: str, date, home: str, away: str) -> dict:
    """The game's tickets on the record, by kind: each one's verdict and its legs'.
    ``date`` is a day or several (_dates)."""
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    days = _dates(date)
    if "parlays" not in have or "parlay_legs" not in have or not days:
        return {}
    out: dict = {}
    for kind, source in TICKETS.items():
        rows = conn.execute(f"SELECT id, status FROM parlays WHERE sport=? AND date IN ({','.join('?' * len(days))}) "
                            "AND grade=? AND source=? ORDER BY id",
                            (sport, *days, f"{away}@{home}", source)).fetchall()
        got = []
        for pid, status in rows:
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
                got.append({"status": _status(status), "legs": legs})
        if got:
            out[kind] = got
    return out


def of_game(conn, sport: str, date: str, g: dict, report: dict | None = None) -> dict:
    """{"picks": [...], "tickets": {"threes": [...], "scorers": [...]}} for one
    game, each part only when the record holds some; {} when it holds none."""
    home, away = str((g or {}).get("home") or ""), str((g or {}).get("away") or "")
    if not sport or not date or not home or not away:
        return {}
    out: dict = {}
    ps = picks(conn, sport, date, home, away, names_in(report) if report else ())
    if ps:
        out["picks"] = ps
    ts = tickets(conn, sport, date, home, away)
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
    legs with theirs: {"DAY|AWAY|HOME": {"picks": [...], "threes": [...],
    "scorers": [...], "held": n}}, a game the record holds nothing for as {}
    and one not archived left out. The archive says which board label the
    game's rows are filed under (its "label"; the NFL's is the week) and which
    players its report names (a pick with no club on its row).

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
            ts = tickets(conn, sport, days, home, away)
            game = {"picks": [{k: v for k, v in p.items() if k != "book"}
                              for p in picks(conn, sport, days, home, away, names_in(doc.get("report")),
                                             books=REPORT_BOOKS)],
                    "threes": ts.get("threes") or [], "scorers": ts.get("scorers") or []}
            if not member:
                held = 0
                for part in ("picks", "threes", "scorers"):
                    keep = [x for x in game[part] if x.get("status") in SETTLED]
                    held += len(game[part]) - len(keep)
                    game[part] = keep
                game["held"] = held
            out[key] = {k: v for k, v in game.items() if v}
    finally:
        conn.close()
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
