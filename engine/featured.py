"""FEATURED GAMES: LIONS GAMES, THURSDAY NIGHTS AND MONDAY NIGHTS (FEATURED1, 2026-11-19).

Ethan: "the main game reports that I want to focus on is any game reports that
has to do with a Lions game, any game reports on a Thursday night, or any game
reports on a Monday night. Those are the three main ones that we need to have
dialed in completely and have a separate record for."

WHICH GAMES (`tags`). An NFL game the Lions play in; one that kicks off on a
Thursday night; one that kicks off on a Monday night. Night is the Eastern
clock from NIGHT_FROM on, so Thanksgiving's day games are not Thursday nights
(the Lions' Thanksgiving game is a Lions game all the same). One game can be
two of them: the Lions on a Monday night is both, and counts in both.

DIALED IN (engine/gamereport). A featured game's report ranks a deeper card
(gamereport.CARD_MAX_FEATURED picks, against four), so its picks cover more of
the game and its parlays have more of the report's own picks to be built from;
and it says at its top what it is and how the reports on games like it have
done (`badge`).

THEIR OWN RECORD (`record`). Every finished featured game the archive holds
(engine/reportarchive), counted apart from the rest:

  * the report's own picks (its book, engine/reportoutcome.picks), won, lost
    and pushed, and the units at one unit a pick at the price it was posted at;
  * the tickets its report carried at the start, the ones the league's parlay
    record counts (parlayledger.AT_START), by kind, at the units the record
    grades them at;
  * who we said would win, right or wrong;

for all of them, for each kind of game, and for each game. Counts only, as
the reports' record is (engine/reportrecord): what has settled is public, a
pick or ticket still waiting on its box score is a count. Served beside the
league's record (/api/report_record) and drawn on the Record and Report Picks
pages. Never raises: a missing archive or journal is an empty record."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

#: The leagues whose games can be featured: Thursday and Monday nights are the
#: NFL's own nights, and the Lions are an NFL club.
SPORTS = ("nfl",)
#: The Lions' code on the NFL's boards.
TEAM = "DET"
#: Night on the Eastern clock: a kickoff from 6 PM on. Thursday Night Football
#: and Monday Night Football kick off from 7:15 to 8:30 PM; Thanksgiving's day
#: games at 12:30 and 4:30 are not Thursday nights.
NIGHT_FROM = 18
#: The kinds, in the order they are said.
TAGS = ("lions", "thursday", "monday")
WORDS = {"lions": "Lions game", "thursday": "Thursday night", "monday": "Monday night"}
PLURAL = {"lions": "Lions games", "thursday": "Thursday nights", "monday": "Monday nights"}
_NIGHTS = {3: "thursday", 0: "monday"}
#: The ticket kinds a featured game's record counts (engine/reportoutcome.TICKETS).
KINDS = ("threes", "twos", "scorers")
KIND_WORDS = {"threes": "three-leg parlays", "twos": "two-leg parlays", "scorers": "touchdown pairs"}


def _eastern(date, kickoff) -> tuple:
    """(the game's day, its kickoff hour) on the Eastern clock: the NFL's board
    writes nflverse's "20:15" (Eastern) beside the date, a feed may write a UTC
    stamp. The hour is None where there is no kickoff to read."""
    k = str(kickoff or "").strip()
    if "T" in k:
        try:
            from .sources.cfbdata import to_eastern
            et = to_eastern(k)
        except Exception:                                    # noqa: BLE001
            et = None
        if et is not None:
            return et.date(), et.hour
        k = ""
    try:
        day = _dt.date.fromisoformat(str(date or "")[:10])
    except ValueError:
        return None, None
    try:
        hour = int(k.split(":")[0]) if k else None
    except ValueError:
        hour = None
    return day, hour


def tags(sport, date="", kickoff="", home="", away="") -> list:
    """The kinds of featured game this is, in TAGS order; [] for any other."""
    if str(sport or "").lower() not in SPORTS:
        return []
    out = []
    if TEAM in {str(home or "").upper(), str(away or "").upper()}:
        out.append("lions")
    day, hour = _eastern(date, kickoff)
    night = _NIGHTS.get(day.weekday()) if day else None
    if night and (hour is None or hour >= NIGHT_FROM):
        out.append(night)
    return out


def of_game(g, sport) -> list:
    """`tags` for a board's game row."""
    g = g if isinstance(g, dict) else {}
    return tags(sport, g.get("date"), g.get("kickoff") or g.get("commence_time"), g.get("home"), g.get("away"))


def words(kinds) -> str:
    """"Lions game · Monday night"."""
    return " · ".join(WORDS[t] for t in TAGS if t in (kinds or ()))


# --- the record -------------------------------------------------------------------------------
def _block() -> dict:
    return {"games": 0, "picks": [0, 0, 0], "units": 0.0, "open": 0,
            "tickets": {k: [0, 0, 0.0] for k in KINDS}, "tickets_open": 0, "call": [0, 0]}


def _win_units(odds) -> float | None:
    """What one unit wins at an American price; None with no price."""
    try:
        o = int(float(odds))
    except (TypeError, ValueError):
        return None
    if o >= 100:
        return o / 100.0
    if o <= -100:
        return 100.0 / -o
    return None


def _add(block: dict, game: dict) -> None:
    block["games"] += 1
    for i in range(3):
        block["picks"][i] += game["picks"][i]
    block["units"] = round(block["units"] + game["units"], 2)
    block["open"] += game["open"]
    for k in KINDS:
        w, lost, u = game["tickets"].get(k) or (0, 0, 0.0)
        t = block["tickets"][k]
        t[0] += w
        t[1] += lost
        t[2] = round(t[2] + u, 2)
    block["tickets_open"] += game["tickets_open"]
    if game.get("call"):
        block["call"][0] += bool(game["call"].get("right"))
        block["call"][1] += 1


def _picks_of(conn, sport: str, row: dict, doc: dict) -> tuple:
    """([won, lost, pushed], units, open) for the game's own report picks."""
    from .reportoutcome import REPORT_BOOKS, names_in, picks
    day = str(row.get("date") or "")[:10]
    days = tuple(x for x in (doc.get("label"), day) if x)
    tally, units, still = [0, 0, 0], 0.0, 0
    for p in picks(conn, sport, days, row.get("home"), row.get("away"), names_in(doc.get("report")),
                   books=REPORT_BOOKS) if conn is not None and days else []:
        st = p.get("status")
        if st == "won":
            tally[0] += 1
            u = _win_units(p.get("odds"))
            units += u if u is not None else 0.0
        elif st == "lost":
            tally[1] += 1
            units -= 1.0
        elif st == "push":
            tally[2] += 1
        elif st != "void":
            still += 1
    return tally, round(units, 2), still


def _tickets_of(conn, sport: str, games: list) -> dict:
    """{game index: {"tickets": {kind: [won, lost, units]}, "open": n}} for the
    games' tickets at the start (parlayledger.AT_START), in one read."""
    from .parlayledger import AT_START
    from .reportoutcome import TICKETS
    out: dict = {}
    if conn is None or not games:
        return out
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(parlays)")}
    except Exception:                                        # noqa: BLE001
        return out
    if "at_start" not in have:
        return out
    kind_of = {src: kind for kind, src in TICKETS.items()}
    where: dict = {}
    for i, (row, doc) in enumerate(games):
        for d in {doc.get("label"), str(row.get("date") or "")[:10]} - {None, ""}:
            where[(f"{row.get('away')}@{row.get('home')}", str(d))] = i
    grades = sorted({g for g, _d in where})
    srcs = sorted(kind_of)
    for grade, d, src, status, pnl in conn.execute(
            f"SELECT grade, date, source, status, pnl_units FROM parlays WHERE lower(sport)=? AND {AT_START} "
            f"AND grade IN ({','.join('?' * len(grades))}) AND source IN ({','.join('?' * len(srcs))})",
            (sport, *grades, *srcs)).fetchall():
        i = where.get((grade, str(d)))
        if i is None:
            continue
        x = out.setdefault(i, {"tickets": {}, "open": 0})
        st = str(status or "").lower()
        if st in ("won", "lost"):
            t = x["tickets"].setdefault(kind_of[src], [0, 0, 0.0])
            t[0 if st == "won" else 1] += 1
            t[2] = round(t[2] + float(pnl or 0.0), 2)
        elif st == "open":
            x["open"] += 1
    return out


def _fingerprint(where, sport: str, path) -> tuple:
    """What the record is read from, as it stands: the archive's index, and the
    journal's report picks and starting tickets (count, open, won, newest)."""
    from .reportarchive import DIR
    from .reportrecord import INDEX
    try:
        st = (Path(where) / DIR / sport / INDEX).stat()
        idx = (st.st_size, st.st_mtime_ns)
    except OSError:
        idx = None
    from .reportoutcome import _connect
    conn = _connect(path)
    if conn is None:
        return idx, None
    try:
        bets = conn.execute("SELECT count(*), sum(status='open'), sum(status='won'), max(id) FROM bets "
                            "WHERE sport=? AND category='report'", (sport,)).fetchone()
        try:
            tix = conn.execute("SELECT count(*), sum(status='open'), sum(status='won'), max(id) FROM parlays "
                               "WHERE lower(sport)=? AND at_start=1", (sport,)).fetchone()
        except Exception:                                    # noqa: BLE001
            tix = None
        return idx, tuple(bets or ()), tuple(tix or ())
    except Exception:                                        # noqa: BLE001
        return idx, None
    finally:
        conn.close()


_MEMO: dict = {}


def record(where=None, sport: str = "nfl", path=None) -> dict:
    """THE FEATURED GAMES' OWN RECORD: {"sport", "all": block, "kinds": {kind:
    block}, "games": [row, ...] newest first, "words", "plural", "order"}; a
    block is {"games", "picks": [won, lost, pushed], "units", "open", "tickets":
    {kind: [won, lost, units]}, "tickets_open", "call": [right, of]}. {} for a
    league with no featured games, or none finished yet. Read again only when
    the archive's index or the journal moved (`_fingerprint`)."""
    sport = str(sport or "").lower()
    if sport not in SPORTS:
        return {}
    try:
        if where is None:
            from .gate import FULL_DIR
            where = FULL_DIR
        key = (str(where), sport, str(path or ""))
        fp = _fingerprint(where, sport, path)
        hit = _MEMO.get(key)
        if hit and hit[0] == fp:
            return hit[1]
        out = _record(where, sport, path)
        _MEMO[key] = (fp, out)
        return out
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ the featured games' record not read ({type(exc).__name__}: {exc})")
        return {}


def _maybe(row: dict) -> bool:
    """Could this archived game be featured, by its teams and its day alone?
    (Its kickoff, in its document, says for certain.)"""
    if TEAM in {str(row.get("home") or "").upper(), str(row.get("away") or "").upper()}:
        return True
    try:
        return _dt.date.fromisoformat(str(row.get("date") or "")[:10]).weekday() in _NIGHTS
    except ValueError:
        return False


def _record(where, sport: str, path) -> dict:
    from . import reportarchive, reportrecord
    from .reportoutcome import _connect
    rows = [r for r in reportrecord.rows(where, sport, write=False) if _maybe(r)]
    found = []
    for r in rows:
        doc = reportarchive.load(sport, str(r.get("date") or "")[:10], r.get("away"), r.get("home"), where) or {}
        kinds = tags(sport, doc.get("date") or r.get("date"), doc.get("kickoff"), r.get("home"), r.get("away"))
        if kinds:
            found.append((r, doc, kinds))
    if not found:
        return {}
    conn = _connect(path)
    try:
        tix = _tickets_of(conn, sport, [(r, doc) for r, doc, _k in found])
        games = []
        for i, (r, doc, kinds) in enumerate(found):
            tally, units, still = _picks_of(conn, sport, r, doc)
            t = tix.get(i) or {}
            games.append({"date": str(r.get("date") or "")[:10], "game": r.get("game") or f"{r['away']}@{r['home']}",
                          "away": r.get("away"), "home": r.get("home"), "names": r.get("names") or {},
                          "final": r.get("final") or {}, "kinds": kinds, "call": r.get("call") or None,
                          "picks": tally, "units": units, "open": still,
                          "tickets": {k: t["tickets"][k] for k in KINDS if k in t.get("tickets", {})},
                          "tickets_open": int(t.get("open") or 0)})
    finally:
        if conn is not None:
            conn.close()
    every, by_kind = _block(), {k: _block() for k in TAGS}
    for g in games:
        _add(every, g)
        for k in g["kinds"]:
            _add(by_kind[k], g)
    reportrecord.named(sport, games)
    return {"sport": sport, "all": every, "kinds": {k: v for k, v in by_kind.items() if v["games"]},
            "games": games, "order": list(TAGS), "words": WORDS, "plural": PLURAL, "kind_words": KIND_WORDS}


# --- the report's line ------------------------------------------------------------------------
def _signed(u: float) -> str:
    return f"{'+' if u > 0 else '−' if u < 0 else ''}{abs(u):.1f}"


def line(block: dict, kind: str | None = None) -> str:
    """One sentence on a block: "Thursday nights so far, 3 games: the reports'
    picks 9-6 (+1.8 units at one unit a pick); three-leg parlays 1 of 4."
    "" for a block with nothing graded."""
    if not block or not block.get("games"):
        return ""
    who = PLURAL.get(kind or "", "Featured games")
    w, lost, p = block["picks"]
    parts = []
    if w + lost:
        parts.append(f"the reports' picks {w}-{lost}{f'-{p}' if p else ''} "
                     f"({_signed(block['units'])} units at one unit a pick)")
    for k in KINDS:
        tw, tl, _u = block["tickets"].get(k) or (0, 0, 0.0)
        if tw + tl:
            parts.append(f"{KIND_WORDS[k]} {tw} of {tw + tl}")
    cr, cn = block.get("call") or (0, 0)
    if cn:
        parts.append(f"who wins {cr} of {cn}")
    if not parts:
        return ""
    n = block["games"]
    return f"{who} so far, {n} finished game{'s' if n != 1 else ''}: " + "; ".join(parts) + "."


def badge(sport: str, g: dict, where=None, path=None) -> dict | None:
    """What a featured game's report says at its top: {"kinds", "words",
    "lines"}: its kinds, in words, and how the reports on each kind of game
    have done so far (`line`). None for a game that is not featured."""
    kinds = of_game(g, sport)
    if not kinds:
        return None
    rec = record(where, sport, path)
    lines = [x for x in (line((rec.get("kinds") or {}).get(k) or {}, k) for k in kinds) if x]
    return {"kinds": kinds, "words": words(kinds), "lines": lines}
