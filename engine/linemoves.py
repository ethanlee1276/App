"""Line-movement tracking: opening vs current lines and steam detection.

Every time real odds are attached to a slate, a timestamped snapshot of each
book's line is appended to ``data/cache/line_history.jsonl``. Over repeated
runs that builds a movement history the analyzer reads:

  * per book: opening line, current line, delta, and when it last moved;
  * per prop: consensus move (median across books), direction, and a **steam**
    flag — several books moving the same direction by a real amount within a
    short window, the classic footprint of sharp money.

Reverse line movement (line moving against the public) additionally needs
public betting percentages, which have no free feed — documented as future
work. The analysis functions are pure and unit-tested; recording is one
append per run.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .sources.fetch import CACHE_DIR

HISTORY_PATH = CACHE_DIR / "line_history.jsonl"


def start_epoch(kickoff, date=None, clock_tz: str | None = None) -> float | None:
    """A game's start as a UNIX timestamp, or None when it cannot be known.

    Same rule as ``losspatterns.minutes_until``, for the same reason: a
    full ISO stamp with a Z or offset is usable, a bare local clock like
    "13:00" is not. Guessing a timezone onto a bare clock would silently
    decide which snapshots count as pre-game, and a wrong guess there is
    worse than no cut at all.

    A BARE CLOCK IS READ ONLY WHEN THE CALLER NAMES ITS ZONE. ``date`` +
    ``clock_tz`` turn "20:15" on "2026-09-28" into an instant; the caller
    passes a zone only for a feed whose clock is documented — nflverse's
    `gametime` is US Eastern. Without that, every NFL snapshot carried no
    start at all (the NFL game's kickoff IS a bare clock), no snapshot
    was ever cut as in-play, and on 2026-09-29 the close check found the
    week-3 "closes" were in-game lines: Barner's receiving under 19.5
    "closing" at 69.5 on a final of 69, Burrow 255.5 → 349.5, Saquon's
    receiving yards 7.5 → 79.5 — the one board's picks that "lost the
    close" hit 12% because the close was the result.
    """
    if not kickoff:
        return None
    import datetime as _dt
    import re as _re
    try:
        start = _dt.datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        start = None
    if start is not None and start.tzinfo is not None:
        return start.timestamp()
    m = _re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", str(kickoff).strip())
    if not (m and date and clock_tz):
        return None                 # a naive stamp is a clock, not an instant
    try:
        from zoneinfo import ZoneInfo
        day = _dt.date.fromisoformat(str(date)[:10])
        start = _dt.datetime(day.year, day.month, day.day, int(m.group(1)),
                             int(m.group(2)), tzinfo=ZoneInfo(clock_tz))
    except Exception:                                         # noqa: BLE001
        return None
    return start.timestamp()


# --- recording --------------------------------------------------------------
def record_snapshots(props, ts: float | None = None,
                     path: str | Path | None = None,
                     slate=None, clock_tz: str | None = None) -> int:
    """Append one row per (prop, book) with the current line. Skips proxy
    lines — only real book numbers are worth tracking.

    ``slate`` (when given) stamps each row with its game's start time, so
    the close-picker can tell a pre-game price from an in-play one. The
    odds adapter's own docstring is why this matters: *"during a live
    game the event-odds endpoint returns current (in-play) prices"* — on
    a staggered slate a late pull re-prices the games already underway,
    and without a start stamp the last of those snapshots became the
    "close" for a game that had been running for two hours.
    """
    ts = ts if ts is not None else time.time()
    path = Path(path) if path else HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a") as fh:
        for prop in props:
            start = None
            if slate is not None:
                try:
                    _g = slate.game_for(prop)
                    # ``clock_tz``: the zone of a bare-clock kickoff, from
                    # a caller that knows it (see `start_epoch`).
                    start = start_epoch(getattr(_g, "kickoff", None),
                                        getattr(_g, "date", None), clock_tz)
                except Exception:                  # noqa: BLE001
                    start = None       # a slate that cannot locate its own
                                       # game must not cost the snapshot
            for ln in prop.lines:
                if ln.book == "proxy":
                    continue
                # BOTH SIDES. The under price was never written, and the
                # whole snapshot history is over-only as a result — so
                # `--clv` rebuilt a close for 113 bets and every single one
                # of them was an OVER, with the under half of the book
                # invisible rather than unprofitable.
                #
                # The line object has carried `under_odds` all along
                # (models.py) and the odds_history table has a column for
                # it (db.py). Only this writer dropped it.
                #
                # This does not recover the past: those rows are on disk
                # without an under price and cannot be rebuilt. It starts
                # the clock for UNDER bets from here.
                row = {
                    "ts": ts, "player": prop.player, "market": prop.market,
                    "book": ln.book, "line": ln.line,
                    "over_odds": ln.over_odds,
                    "under_odds": getattr(ln, "under_odds", None),
                }
                if start is not None:
                    row["start_ts"] = start
                fh.write(json.dumps(row) + "\n")
                n += 1
    return n



def record_fight_snapshots(fights: list[dict], ts: float | None = None,
                           path: str | Path | None = None) -> int:
    """Append h2h snapshots for a card of fights — the store UFC never had.

    UFC_MODEL §4 has read "no per-fight movement history is stored yet"
    since it was written, and the reason is mundane: `ufc_build` calls
    `fetch_event_odds` by hand instead of going through
    `apply_odds_to_slate`, and the snapshot recorder lives inside the
    latter. Every card's prices were fetched, used, and forgotten.

    Each fight is `{"a", "b", "commence", "books": {book: (a_odds,
    b_odds)}}`. Two rows per book — one per fighter — in the exact shape
    `record_snapshots` writes, so `analyze`, `closing_lines`, `booksharp`
    and the opener helper below all read fight history with zero changes:
    player = the fighter, market = "moneyline", line = 0.5 (the journal's
    own convention for a fight), over_odds = his price, under_odds = his
    opponent's, because "under 0.5 wins" IS the opponent winning and the
    two-sided price is what de-vigging needs.
    """
    ts = ts if ts is not None else time.time()
    path = Path(path) if path else HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a") as fh:
        for f in fights or []:
            start = start_epoch(f.get("commence"))
            for book, (ao, bo) in (f.get("books") or {}).items():
                for me, mine, theirs in ((f.get("a"), ao, bo),
                                         (f.get("b"), bo, ao)):
                    if not me or not mine:
                        continue
                    row = {"ts": ts, "player": me, "market": "moneyline",
                           "book": book, "line": 0.5,
                           "over_odds": mine, "under_odds": theirs}
                    if start is not None:
                        row["start_ts"] = start
                    fh.write(json.dumps(row) + "\n")
                    n += 1
    return n


def opening_odds(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """The FIRST recorded price per (player, market) — the opener.

    UFC §11 wants the opener stored so "beat the open" is answerable next
    to "beat the close". It is derived the same way the close is — from
    the snapshot history — rather than banked as a column, because the
    banked-close column is the one that spent months wrong (task: the
    2,065-row repair) while the rebuilt-from-history number stayed right.
    Where several books are quoted in the earliest snapshot, the median,
    same as `closing_lines`.
    """
    earliest: dict = {}
    for r in rows:
        try:
            ts = float(r["ts"])
            key = (r["player"], r["market"])
        except (KeyError, TypeError, ValueError):
            continue
        cur = earliest.get(key)
        if cur is None or ts < cur[0]:
            earliest[key] = (ts, [r])
        elif ts == cur[0]:
            cur[1].append(r)
    out: dict = {}
    for key, (ts, snaps) in earliest.items():
        odds = sorted(o for o in (s.get("over_odds") for s in snaps)
                      if o is not None)
        if odds:
            out[key] = {"ts": ts, "odds": odds[len(odds) // 2],
                        "books": len(odds)}
    return out

def _pregame_only(items: list[dict]) -> list[dict]:
    """Drop snapshots taken at or after the game started.

    The start comes from the rows themselves, so one game has one start
    even when only some of its snapshots carry the stamp (rows recorded
    before this stamp existed carry none). No stamp anywhere = no cut:
    legacy history keeps reading exactly as it always has rather than
    being retroactively reinterpreted.
    """
    starts = [float(r["start_ts"]) for r in items
              if r.get("start_ts") is not None]
    if not starts:
        return items
    start = min(starts)
    pre = [r for r in items if float(r.get("ts", 0)) < start]
    # Every bet was placed on a pre-game price, so a key with nothing
    # pre-game is a slate we only ever saw in play — it has no close to
    # report, and inventing one from a live number is the bug being fixed.
    return pre


#: The zone the slate day is read in. Every league on the board journals
#: its bets under the US Eastern date (the NFL's Sunday, MLB's slate), and
#: the day a snapshot belongs to is its GAME's day, not the machine's.
SLATE_TZ = "America/New_York"


#: What the two close readers read off a snapshot, and all they keep.
_LINE_KEYS = ("ts", "line", "start_ts", "book")
_ODDS_KEYS = ("ts", "line", "start_ts", "over_odds", "under_odds")


def _slim(r: dict, keys: tuple) -> dict:
    """The fields a close is cut from, never the whole snapshot.

    THE SETTLE LANE'S MEMORY (2026-10-07). Both close readers grouped every
    snapshot row whole — ~530 MB on a 400,000-row file, by the note in
    tests/test_history_stream.py — and the settle chore was killed by the
    kernel on the box beside the daily pass. The grouping now keeps only
    the keys `_pregame_legs`, the line median and `_price_close` read, so
    every close comes out exactly as before."""
    return {k: r[k] for k in keys if k in r}


class _CloseIndex(dict):
    """A close index that also names the keys whose close was cut at a
    RECORDED start (`stamped`) — a close proven pre-game, which the settle
    path prefers over a harvested price nothing proves (audit P0-2)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.stamped: set = set()
        #: ``{key: the close every row gave}`` for a key whose rows held a
        #: copy (`_Copies`): what a reader without the check banked, so a
        #: repair can tell a close that came from a copy.
        self.copied: dict = {}
        #: ``{(player, market, ts): (the other players)}``: each copy left out.
        self.twins: dict = {}


def _loose(n: str) -> str:
    """First initial and surname of an already normalized name: the key the
    odds adapter's loose fallback joins on (`oddsapi._name_key_loose`)."""
    parts = n.split()
    return f"{parts[0][:1]} {parts[-1]}" if parts else ""


#: How near the quotes a player is judged to own must sit to his own reads
#: (`_Copies`): a tenth of the line, at least a point and a half. A line
#: moves less than that between one pull and the next. Near is not enough
#: on its own: in the real Week 1, A.J. Brown's own 64.5 sat within it of
#: the 62.0 that was St. Brown's, so the NEAREST own read decides (`_place`).
_OWN_SHARE, _OWN_FLOOR = 0.10, 1.5
#: And how far off a man's own reads must sit for the set to be plainly not
#: his, owner found or not: twice as far, so a line that really moved
#: between two reads of the owner's own is never taken for another man's.
_FAR_SHARE, _FAR_FLOOR = 0.20, 3.0
#: Ten points of chance on the over count as one of line, so a 0.5 line (a
#: touchdown, a home run), the same for every man, is told apart by price.
_CHANCE_WEIGHT = 10.0


def _read_of(quotes) -> tuple | None:
    """A quote set's middle line and middle over price, as a chance: what
    two reads of one market are compared on (`_Copies`). The sportsbooks'
    quotes, an exchange's only when none quoted, as the close is read."""
    from .odds import implied_or_none, is_exchange
    rows = []
    for q in quotes or ():
        book, line, over = (str(q).split("|") + ["", "", ""])[:3]
        try:
            rows.append((book, float(line), implied_or_none(over, parse=lambda x: int(float(x)))))
        except ValueError:
            continue
    rows = [r for r in rows if not is_exchange(r[0])] or rows
    if not rows:
        return None
    chances = [c for _b, _l, c in rows if c is not None]
    return _median([ln for _b, ln, _c in rows]), (_median(chances) if chances else None)


def _gap(a, b) -> float | None:
    """How far apart two reads of one market sit (`_read_of`), or None."""
    if a is None or b is None:
        return None
    d = abs(a[0] - b[0])
    if a[1] is not None and b[1] is not None:
        d += abs(a[1] - b[1]) * _CHANCE_WEIGHT
    return d


def _place(read, refs: dict) -> tuple:
    """Whose quotes a copied set was, and which names lose it: ``(owner,
    losers)``. ``refs`` is ``{name: [quote sets of his own]}``. The owner is
    the one name whose own read sits nearest the set and near enough to be
    his, and every other name loses it. With no owner (no name's own read is
    near, or two sit as near) only a name whose own reads sit too far off to
    be his loses it; the rest keep it, the rows cannot say whose it was."""
    if read is None:
        return None, ()
    gaps = {}
    for name, sets in refs.items():
        got = [g for g in (_gap(read, _read_of(q)) for q in sets if q) if g is not None]
        gaps[name] = min(got) if got else None
    near = max(_OWN_FLOOR, _OWN_SHARE * abs(read[0]))
    far = max(_FAR_FLOOR, _FAR_SHARE * abs(read[0]))
    scored = sorted((g, n) for n, g in gaps.items() if g is not None)
    if scored and scored[0][0] <= near and (len(scored) == 1 or scored[1][0] - scored[0][0] > 1e-9):
        owner = scored[0][1]
        return owner, tuple(n for n in refs if n != owner)
    return None, tuple(n for n, g in gaps.items() if g is not None and g > far)


class _Copies:
    """QUOTES FILED UNDER TWO PLAYERS AT ONCE (2026-11-06).

    From 22 August the odds adapter could hand one player's lines to another
    whose own were missing from a pull, when the two shared a first initial
    and a surname (`oddsapi`'s loose fallback), and until 15 September
    nothing checked that the price came from the player's own game. The
    snapshot writer recorded those lines under both names, from the same
    pull, at the same instant. Ethan's NFL repair of 6 November showed it:
    A.J. Brown and Amon-Ra St. Brown ("a brown", both), in different games,
    at the same four books on the same four numbers, both closing at 62.0.

    A copy is exact (every book, line and price, the one pull's timestamp),
    so it is found exactly: two names that share that loose key, at one
    instant in one market, with identical quote sets.

    THE OWNER KEEPS HIS QUOTES. One of those names was quoted by the books
    and the others were handed his lines; the rows do not say which, but
    each name's own reads do (a read of his own is a quote set no other name
    shares). The owner is the name whose latest read of his own before the
    pull, or failing that his first after it, sits nearest the copied set
    and near enough to be his (`_place`). Only the others lose the read. In
    the real Week 1 the set was St. Brown's Sunday quotes, handed to A.J.
    Brown's prop four days after A.J. Brown had played the Wednesday opener:
    St. Brown's own reads sat beside it, nearer than A.J. Brown's own 64.5
    from before his game, so A.J. Brown loses it and his close is that 64.5.
    When no name's own reads can say, a name whose own reads sit plainly
    elsewhere still loses it, and the rest keep it (two men whose every read
    is the same quotes, as OKC's Jalen and Jaylin Williams would be if the
    books never quoted the bench man): leaving it out for them would take a
    real close from the man it belongs to, to keep a wrong one from a man
    the books never quoted. The first version of this check (the same day)
    left a copy out for every name, and so took the owner's own reads too:
    a star whose every pull also went to an unquoted namesake on the slate
    would have had his real closes cleared.

    ONE PULL AT A TIME, FOR THE BOX'S MEMORY. A copy only ever shares its
    pull's timestamp, and a pull's rows are written to the file together
    (`record_snapshots`), so each pull is judged when the stream moves past
    it and then forgotten, but for each name's latest read of his own (one
    quote set per name and market). A few pulls are held open at once
    (``KEEP``), because two builds can append to the file at the same time
    and interleave. A copy no earlier read decides waits for each name's
    next read of his own and is judged at the end (`found`)."""

    KEEP = 8
    #: Copies held for a later read, at most. Past this the oldest half is
    #: judged on what has been read so far: a pair the rows can never place
    #: would otherwise hold one for every pull of a season.
    WAITING = 20000

    def __init__(self):
        self._open: dict = {}
        self._order: list = []
        self._found: dict = {}
        #: ``{(name, market): quote set}``: each name's latest read of his own.
        self._last: dict = {}
        #: Copies no earlier read decided, ``(ts, market, names, read, {name: earlier set})``,
        #: the ``(name, market)`` they need a later read of, and that read once seen.
        self._waiting: list = []
        self._watch: set = set()
        self._after: dict = {}
        #: Whether a copy was judged while one of its names had no read of
        #: his own yet in what was read: a read that starts partway through
        #: the file (`day_start`) cannot then tell it would place it as the
        #: whole file does, and is done again from further back.
        self.unsure = False

    def add(self, name: str, r: dict) -> None:
        try:
            ts = float(r["ts"])
            q = f"{r.get('book') or ''}|{float(r['line']):g}|{r.get('over_odds')}|{r.get('under_odds')}"
        except (KeyError, TypeError, ValueError):
            return
        pull = self._open.get(ts)
        if pull is None:
            pull = self._open[ts] = {}
            self._order.append(ts)
            if len(self._order) > self.KEEP:
                self._judge(self._order.pop(0))
        pull.setdefault((r.get("market"), _loose(name)), {}).setdefault(name, []).append(q)

    def _judge(self, ts: float) -> None:
        for (market, _key), by in (self._open.pop(ts, None) or {}).items():
            sets: dict = {}
            for name, quotes in by.items():
                sets.setdefault(tuple(sorted(quotes)), []).append(name)
            for qs, names in sets.items():
                if len(names) == 1:
                    k = (names[0], market)
                    self._last[k] = qs                 # a read of his own
                    if k in self._watch and k not in self._after:
                        self._after[k] = qs
                    continue
                names = sorted(names)
                before = {n: self._last.get((n, market)) for n in names}
                if any(v is None for v in before.values()):
                    self.unsure = True
                read = _read_of(qs)
                owner, losers = _place(read, {n: [q] for n, q in before.items()})
                if owner is None:
                    self._waiting.append((ts, market, names, read, before))
                    self._watch.update((n, market) for n in names)
                    if len(self._waiting) > self.WAITING:
                        self._settle(self.WAITING // 2)
                    continue
                self._flag(ts, market, names, losers)
                self._last[(owner, market)] = qs

    def _flag(self, ts: float, market, names: list, losers) -> None:
        for n in losers:
            self._found[(n, market, ts)] = tuple(x for x in names if x != n)

    def _settle(self, upto: int) -> None:
        """Judge the oldest waiting copies on every read seen so far."""
        for ts, market, names, read, before in self._waiting[:upto]:
            _who, losers = _place(read, {n: [before.get(n), self._after.get((n, market))] for n in names})
            self._flag(ts, market, names, losers)
        del self._waiting[:upto]

    def found(self) -> dict:
        """``{(player, market, ts): (the other players)}``: every read left
        out, a name's copy of another's quotes (never the owner's own)."""
        for ts in self._order:
            self._judge(ts)
        self._order = []
        self._settle(len(self._waiting))
        return self._found


def _uncopied(key: tuple, rows: list, twins: dict) -> list:
    """``rows`` of one (player, market, ...) key without its copies."""
    if not twins:
        return rows
    return [r for r in rows if (key[0], key[1], float(r["ts"])) not in twins]


def _slate_day(r: dict) -> str:
    """The day a snapshot is filed under.

    A row stamped with its game's start files under that start's Eastern
    date — the slate day the bet was journaled under. A 9:10 p.m. Eastern
    first pitch is 01:10 UTC the next day, and the machine's clock (UTC on
    the box) filed its whole pre-game run under the wrong day, where no
    bet ever looked (audit 2026-09-30, P1-4).

    An unstamped row keeps the machine-local day it always had: history
    written before the stamp is not reinterpreted.
    """
    import datetime as _dt
    st = r.get("start_ts")
    if st is not None:
        from zoneinfo import ZoneInfo
        return _dt.datetime.fromtimestamp(float(st), ZoneInfo(SLATE_TZ)).strftime("%Y-%m-%d")
    return _dt.datetime.fromtimestamp(float(r["ts"])).strftime("%Y-%m-%d")


def _pregame_legs(items: list[dict]) -> list[tuple]:
    """``[(start, pre-game rows)]``, one per game in the group, earliest first.

    `_pregame_only` cuts every row at the EARLIEST start in the group, so on
    a doubleheader every pre-game price of game two — all taken after game
    one's first pitch — was dropped, and game two had no close at all. Each
    stamped row is cut at its OWN game's start here. Unstamped rows belong
    to the first game and are cut at it, which is what `_pregame_only` did.
    No stamp anywhere: one game, no cut — legacy history reads as before.
    """
    starts = sorted({float(r["start_ts"]) for r in items
                     if r.get("start_ts") is not None})
    if not starts:
        return [(None, items)]
    first = starts[0]
    out = []
    for s in starts:
        pre = []
        for r in items:
            own = r.get("start_ts")
            own = float(own) if own is not None else first
            if own == s and float(r.get("ts", 0)) < s:
                pre.append(r)
        out.append((s, pre))
    return out


def stream_history(path: str | Path | None = None):
    """Every snapshot, one at a time, without holding the file in memory.

    THE GIGABYTE. `load_history` below reads the whole file with
    `read_text()` — one string — then `.splitlines()` for a second full
    copy, then parses every line into a dict and keeps all of them. That is
    the right shape for the callers that genuinely need the whole list
    (`closing_lines_by_date`; `booksharp` streams), and it is a catastrophe
    for the ones that immediately throw almost all of it away.

    `nfl_build` was the worst case: `todays_rows(load_history())` twice per
    run, materialising every sport's entire snapshot history to keep the
    handful of rows recorded since local midnight. Measured on the droplet
    2026-09-03 with `--memtrace`, on a machine with 1 GB:

        odds        75    1324    +1147   <-- the biggest peak
        pipeline    73    1602     +278

    1,425 MB of a 1,602 MB peak, in two stages whose resident size went
    DOWN. The tell was in the log all along: an NFL build printing ten
    lines of MLB line movement, because the history it loaded was every
    sport's and the filter came afterwards.

    `todays_rows` and the other filters take any iterable, so this drops
    straight in and only the KEPT rows are ever held.
    """
    path = Path(path) if path else HISTORY_PATH
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


#: How far before the cut `stream_since` starts reading: the builds append
#: in real time, so a line's place in the file is its time to within
#: seconds; an hour more covers any writer that ran late.
SINCE_MARGIN_S = 3600.0


def _ts_after(fh, offset: int) -> float:
    """The `ts` of the first whole line at or after ``offset`` (the line
    the offset falls inside is skipped), inf at the end of the file."""
    fh.seek(offset)
    if offset:
        fh.readline()
    for _ in range(8):
        raw = fh.readline()
        if not raw:
            return float("inf")
        try:
            return float(json.loads(raw).get("ts") or 0)
        except (ValueError, TypeError, AttributeError):
            continue
    return 0.0


def _seek_since(fh, target: float) -> None:
    """Put the binary file ``fh`` at the start of a line at most 64 KB
    before the first one stamped ``target`` or later, by halving the byte
    range: the file is append-only in time order (every writer stamps a row
    with the moment it writes it, `record_snapshots`)."""
    fh.seek(0, 2)
    lo, hi = 0, fh.tell()
    while hi - lo > 65536:
        mid = (lo + hi) // 2
        if _ts_after(fh, mid) < target:
            lo = mid
        else:
            hi = mid
    fh.seek(lo)
    if lo:
        fh.readline()


def since_offset(ts: float, path: str | Path | None = None):
    """The byte `stream_since` (and `stream_wanted`'s ``since``) starts a
    read from ``ts`` at; None with no file."""
    path = Path(path) if path else HISTORY_PATH
    try:
        with path.open("rb") as fh:
            _seek_since(fh, float(ts) - SINCE_MARGIN_S)
            return fh.tell()
    except OSError:
        return None


def stream_since(ts: float, path: str | Path | None = None):
    """The snapshots from about ``ts`` on, without parsing the file's past.

    EVERY BUILD PARSED EVERY LINE TO KEEP TODAY'S. `todays_rows(
    stream_history())` hands the whole history — every sport since the file
    began — to `json.loads` and then keeps the rows since midnight; the NFL
    build did it twice, the NBA and MLB builds once each, and the NFL's
    "odds" stage ran 148 seconds on cached odds (box run, 2026-10-17). The
    file is append-only in time order, so the first line at ``ts`` less
    SINCE_MARGIN_S is found by halving the byte range, and only the lines
    after it are read. The caller's own filter still runs on what comes
    back, so the answer is the old one."""
    path = Path(path) if path else HISTORY_PATH
    if not path.exists():
        return
    with path.open("rb") as fh:
        _seek_since(fh, float(ts) - SINCE_MARGIN_S)
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue


def stream_today(path: str | Path | None = None, now: float | None = None):
    """`stream_since` local midnight — what `todays_rows` keeps, read fast."""
    import datetime as _dt
    now = now if now is not None else time.time()
    midnight = _dt.datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    return stream_since(midnight, path)


# THE FILE'S DAY INDEX (2026-11-08). The settle pass read the snapshot file
# from SNAPSHOT_LEAD_DAYS before the first day it serves (`ledger.
# _PassSnapshots`), in case a game's snapshot had been taken that long
# before it. On Saturday 7 November that meant reading from 15 October for
# bets from the 29th: 30% of the file, and 83 of the grade's 90 seconds,
# every pass. The index says where the first row filed under each slate day
# (`_slate_day`) begins, so the read starts at the first row of the days it
# serves (and never before the lead did). It is read off the file itself, a
# line at a time, and picks up where it stopped, since the file only grows.
# It can always be built again, and nothing but that read uses it.
DAY_INDEX_VERSION = 1
#: The bytes of the file the index reads in one call at most, so its first
#: build is spread over a few settle passes instead of holding one up.
DAY_INDEX_BUDGET = 64 * 1024 * 1024
#: How much of the file before a day's first row the read takes as well:
#: each player's earlier quotes of his own, by which `_Copies` places a
#: copied set (a copy those cannot place has the read done the old way).
DAY_INDEX_LEAD_S = 2 * 86400.0
_FP_BYTES = 4096
_START_TAG, _TS_TAG = b'"start_ts": ', b'"ts": '


def day_index_path(path: str | Path | None = None) -> Path:
    """Where the day index of the snapshot file at ``path`` is kept."""
    path = Path(path) if path else HISTORY_PATH
    return path.with_name(path.stem + ".days.json")


def _fingerprint(fh, lo: int, hi: int) -> str:
    import hashlib
    lo = max(0, lo)
    fh.seek(lo)
    return hashlib.sha1(fh.read(max(0, hi - lo))).hexdigest()


def _epoch_day_exact(t: float, stamped: bool) -> str:
    import datetime as _dt
    if stamped:
        from zoneinfo import ZoneInfo
        return _dt.datetime.fromtimestamp(float(t), ZoneInfo(SLATE_TZ)).strftime("%Y-%m-%d")
    return _dt.datetime.fromtimestamp(float(t)).strftime("%Y-%m-%d")


def _epoch_day(t: float, stamped: bool, memo: dict) -> str:
    """`_slate_day`'s day for an epoch: a game start's in the slate's zone,
    a row's own stamp's in the machine's. Every zone's day turns on a
    quarter hour, so a quarter hour's day is worked out once; an epoch
    within a millisecond of a quarter's edge is worked out on its own."""
    q = int(t // 900)
    if 0.001 < t - q * 900 < 899.999:
        key = (stamped, q)
        d = memo.get(key)
        if d is None:
            d = memo[key] = _epoch_day_exact(q * 900 + 450, stamped)
        return d
    return _epoch_day_exact(t, stamped)


def _number_after(raw: bytes, tag: bytes):
    i = raw.find(tag)
    if i < 0:
        return None
    j = i + len(tag)
    k, e = raw.find(b",", j), raw.find(b"}", j)
    if k < 0 or 0 <= e < k:
        k = e
    if k < 0:
        return None
    try:
        return float(raw[j:k])
    except ValueError:
        return None


def _line_day(raw: bytes, memo: dict):
    """The day `_slate_day` files this line's row under, or None for a line
    no reader takes. A flat row in `record_snapshots`' own shape is read off
    its text; any other line is parsed and asked."""
    if b"\\" not in raw and raw.count(b"{") == 1:
        n = raw.count(b'"start_ts"')
        if n == 1:
            st = _number_after(raw, _START_TAG)
            if st is not None:
                return _epoch_day(st, True, memo)
        elif n == 0 and b"start_ts" not in raw and raw.count(b'"ts"') == 1:
            ts = _number_after(raw, _TS_TAG)
            if ts is not None:
                return _epoch_day(ts, False, memo)
    try:
        r = json.loads(raw)
        return _slate_day(r) if isinstance(r, dict) else None
    except Exception:                                  # noqa: BLE001 — no reader takes it either
        return None


def day_offsets(path: str | Path | None = None,
                budget: int | None = DAY_INDEX_BUDGET) -> dict | None:
    """``{"first": {day: byte offset}, "end", "size", "done"}``: where the
    first row filed under each slate day begins, over the file's first
    ``end`` bytes, brought up to date from where it last stopped, by at most
    ``budget`` bytes (None: to the end); ``done`` once it reached the end.
    None with no file. An index that no longer matches its file (another
    file in its place, one cut short or written over) is built again from
    the start. A last line still being written is left for the next call."""
    import os
    path = Path(path) if path else HISTORY_PATH
    ipath = day_index_path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return None
    try:
        held = json.loads(ipath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        held = None
    memo: dict = {}
    try:
        with path.open("rb") as fh:
            end = held.get("end") if isinstance(held, dict) else None
            first = held.get("first") if isinstance(held, dict) else None
            fresh = not (held.get("v") == DAY_INDEX_VERSION
                         and isinstance(end, int) and 0 <= end <= size
                         and isinstance(first, dict)
                         and all(isinstance(o, int) and 0 <= o < end for o in first.values())
                         and held.get("head") == _fingerprint(fh, 0, min(end, _FP_BYTES))
                         and held.get("tail") == _fingerprint(fh, end - _FP_BYTES, end)
                         ) if isinstance(held, dict) else True
            if fresh:
                held, end = {"v": DAY_INDEX_VERSION, "first": {}}, 0
            first = held["first"]
            stop = size if budget is None else min(size, end + max(0, int(budget)))
            fh.seek(end)
            pos = end
            while pos < stop:
                raw = fh.readline()
                if not raw.endswith(b"\n"):
                    break
                day = _line_day(raw, memo)
                if day is not None and day not in first:
                    first[day] = pos
                pos += len(raw)
            moved = fresh or pos != end
            if moved:
                held["end"] = pos
                held["head"] = _fingerprint(fh, 0, min(pos, _FP_BYTES))
                held["tail"] = _fingerprint(fh, pos - _FP_BYTES, pos)
    except OSError:
        return None
    if moved:
        tmp = ipath.with_name(f"{ipath.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(held, sort_keys=True), encoding="utf-8")
            os.replace(tmp, ipath)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
    out = dict(held)
    out["size"], out["done"] = size, stop >= size
    return out


def day_start(days, path: str | Path | None = None,
              budget: int | None = DAY_INDEX_BUDGET, index: dict | None = None):
    """Where a read of every row filed under these ``days`` starts (a day as
    a string: it and every later day): the first of their first rows, less
    DAY_INDEX_LEAD_S of the file before it. A day with no row yet has its
    rows after the index's end, which the read reaches anyway. None until
    the index has reached the end of the file (`day_offsets`): the caller
    then reads as it did."""
    path = Path(path) if path else HISTORY_PATH
    held = index if index is not None else day_offsets(path, budget)
    if not held or not held.get("done"):
        return None
    first = held["first"]
    if isinstance(days, str):
        offs = [o for d, o in first.items() if d >= days]
    else:
        offs = [first[d] for d in set(days) if d in first]
    o = min(offs + [held["end"]])
    try:
        with path.open("rb") as fh:
            t = _ts_after(fh, o)
            if t == float("inf"):
                return o
            _seek_since(fh, t - DAY_INDEX_LEAD_S)
            return min(fh.tell(), o)
    except OSError:
        return None


def stream_wanted(want, path: str | Path | None = None, siblings: bool = False,
                  since: float | None = None, start: int | None = None):
    """The snapshots of these ``{(normalized player, market)}`` only, one
    at a time, parsing a line only when its text says it may be wanted.

    THE SETTLE PASS READ THE WHOLE FILE UP TO THREE TIMES, AND PARSED EVERY
    LINE EACH TIME. `stream_history` hands every line to `json.loads` and
    `ledger._wanted_rows` throws nearly all of them away after. On
    2026-10-15 the box's settle step took 502 of a cycle's 504 seconds,
    a second settle ran beside it, and every board build (each settles
    at its end) ran out its 600 seconds: the NFL's ten times in seven
    hours on a game day. A line's market and player are read off its text
    first (two `str.find`s), and only a line an open bet asks about is
    parsed. A line not in the plain shape is parsed, so nothing wanted is
    ever lost; the caller's own filter still runs on what comes back, so
    the answer is exactly the old one.

    ``siblings`` also keeps every player who shares a wanted player's first
    initial and surname (2026-11-06): the close readers need both halves of
    a copy to see it (`_Copies`), and the man whose quotes were copied may
    hold no bet at all.

    ``since`` (an epoch) starts the read where `stream_since` would, so the
    lines stamped before it, less SINCE_MARGIN_S, are never read at all
    (the settle pass, `ledger._PassSnapshots`, 2026-11-08). ``start`` (a
    byte offset at a line's start, `day_start`) starts it there instead."""
    import io
    from .sources.oddsapi import normalize_name
    path = Path(path) if path else HISTORY_PATH
    if not path.exists():
        return
    markets = {m for _p, m in want}
    people = {n for n, _m in want}
    kin = {_loose(n) for n in people} if siblings else set()
    names: dict = {}
    # `record_snapshots`' own `json.dumps` shape. Inline rather than a
    # helper: a call per field per line was half the read's time. A field
    # not found, or one holding an escape, is not judged from the text.
    mtag, ptag, slash = '"market": "', '"player": "', "\\"
    with path.open("rb") as bfh:
        if start is not None:
            bfh.seek(int(start))
        elif since is not None:
            _seek_since(bfh, float(since) - SINCE_MARGIN_S)
        fh = io.TextIOWrapper(bfh, encoding="utf-8")
        for raw in fh:
            i = raw.find(mtag)
            if i >= 0:
                i += 11
                m = raw[i:raw.find('"', i)]
                if m not in markets and slash not in m:
                    continue
            i = raw.find(ptag)
            if i >= 0:
                i += 11
                who = raw[i:raw.find('"', i)]
                n = names.get(who)
                if n is None:
                    n = names[who] = normalize_name(who) if slash not in who else None
                if n is not None and n not in people and not (kin and _loose(n) in kin):
                    continue
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


def load_history(path: str | Path | None = None) -> list[dict]:
    """Every snapshot, as a list. Prefer `stream_history` where the caller
    filters it down — see the note there about a gigabyte."""
    return list(stream_history(path))


def closing_lines_by_date(rows: list[dict]) -> dict:
    """``{(normalized player, market, YYYY-MM-DD): closing line}`` — the last
    pre-game snapshot of each slate day (`_slate_day`), medianed across the
    books quoted at that final instant. A doubleheader also carries
    ``(…, leg)`` keys, and the index's ``stamped`` set names the closes cut
    at a recorded start.

    This is the free CLV source for the journal: each day's last recorded
    snapshot is the nearest thing to that night's close, and it accrues on
    every paid pull with no extra spend. (On fixed-line markets like 0.5 HR
    the line never moves, so CLV there reads 0 — honest, if unexciting.)"""
    acc = LineCloses()
    for r in rows:
        acc.add(r)
    return acc.index()


class LineCloses:
    """`closing_lines_by_date` a row at a time: ``add`` each snapshot, then
    ``index``. The function is this class's loop, so the two cannot differ;
    the settle pass feeds one read of the file to this, `OddsCloses` and the
    same-book closes together (`ledger._PassSnapshots`)."""

    def __init__(self):
        from .sources.oddsapi import normalize_name
        self._norm = normalize_name
        self.grouped: dict[tuple, list[dict]] = {}
        self.copies = _Copies()

    def add(self, r: dict) -> None:
        try:
            float(r["ts"])
            date = _slate_day(r)
            name = self._norm(r["player"])
            key = (name, r["market"], date)
            float(r["line"])                       # reject unusable rows early
            self.grouped.setdefault(key, []).append(_slim(r, _LINE_KEYS))
            self.copies.add(name, r)
        except (KeyError, TypeError, ValueError):
            return

    def index(self) -> dict:
        return _line_index(self.grouped, self.copies)


def _line_index(grouped: dict, copies) -> dict:
    """`closing_lines_by_date`'s answer from its grouped rows."""
    from .odds import is_exchange
    out = _CloseIndex()
    # ANOTHER PLAYER'S QUOTES ARE NOBODY'S CLOSE (2026-11-06, `_Copies`).
    out.twins = twins = copies.found()
    out.unsure = copies.unsure

    def _legs(key, items, drop):
        # A price quoted after first pitch is not a closing line — see
        # _pregame_only. Without this cut the last in-play re-price of a
        # staggered slate became the "close", and every CLV computed off
        # it was fiction dressed as evidence.
        #
        # One close per GAME (`_pregame_legs`): the plain key is the first
        # game's, as it always was; a doubleheader also files each game
        # under ``key + (leg,)`` so a leg-two bet reads its own. A copy is
        # left out inside its game, so the games keep their numbers.
        legs = _pregame_legs(items)
        got = []
        for n, (start, pre) in enumerate(legs, 1):
            pre = _uncopied(key, pre, drop)
            if not pre:
                continue
            last = max(float(r["ts"]) for r in pre)
            at = [r for r in pre if float(r["ts"]) == last]
            # THE SPORTSBOOKS' LINES, an exchange's only when none quoted
            # (2026-11-05). An exchange posts a ladder under its main
            # market (`odds.is_exchange`), and its rungs went into this
            # median beside the sportsbooks' one number each: the NBA's
            # receipts carried closes at twice a pick's line. The board
            # never prices off a rung, and neither does the close.
            books = [r for r in at if not is_exchange(r.get("book") or "")]
            got.append((n, start, _median([float(r["line"]) for r in (books or at)])))
        return got, len(legs)

    for key, items in grouped.items():
        got, nlegs = _legs(key, items, twins)
        for n, start, val in got:
            if n == 1:
                out[key] = val
                if start is not None:
                    out.stamped.add(key)
            if nlegs > 1:
                out[key + (n,)] = val
        if twins and len(_uncopied(key, items, twins)) != len(items):
            every, _n = _legs(key, items, None)
            out.copied[key] = next((v for n, _s, v in every if n == 1), None)
    return out


def closing_books_by_date(rows) -> dict:
    """``{(normalized player, market, YYYY-MM-DD[, leg]): (ts, [(book, line), ...])}``:
    the quotes at the instant `closing_lines_by_date` medians, each book
    named. For a person checking a close (``launch.py --repair-close-lines``,
    its dry run); nothing that settles reads it. Same rows, same day, same
    pre-game cut, the same copies left out (`_Copies`), so the books listed
    are the ones the close came from. ``.left`` names, for each key, every
    pre-game read left out as a copy and whose name it was filed under too:
    ``{key: [(ts, (other players))]}``."""
    from .sources.oddsapi import normalize_name

    grouped: dict = {}
    copies = _Copies()
    for r in rows:
        try:
            float(r["ts"])
            date = _slate_day(r)
            name = normalize_name(r["player"])
            key = (name, r["market"], date)
            float(r["line"])
            grouped.setdefault(key, []).append(_slim(r, _LINE_KEYS))
            copies.add(name, r)
        except (KeyError, TypeError, ValueError):
            continue
    twins = copies.found()
    out = _CloseIndex()
    out.twins = twins
    out.left = {}
    for key, items in grouped.items():
        legs = _pregame_legs(items)
        for n, (_start, pre) in enumerate(legs, 1):
            left = sorted({(float(r["ts"]), twins[(key[0], key[1], float(r["ts"]))]) for r in pre
                           if (key[0], key[1], float(r["ts"])) in twins})
            pre = _uncopied(key, pre, twins)
            if left and n == 1:
                out.left[key] = left
            if not pre:
                continue
            last = max(float(r["ts"]) for r in pre)
            at = sorted((str(r.get("book") or "?"), float(r["line"])) for r in pre if float(r["ts"]) == last)
            if n == 1:
                out[key] = (last, at)
            if len(legs) > 1:
                out[key + (n,)] = (last, at)
    return out


def closing_odds_by_date(rows: list[dict]) -> dict:
    """``{(player, market, YYYY-MM-DD, line): {"over": px, "under": px}}``

    BOTH SIDES, and that is the fix rather than a nicety. This returned
    the OVER price alone, and `ledger._settle_all` looked it up with a key
    carrying no side — so every UNDER bet in the journal recorded the
    OVER's closing price as its own.

    HOW IT SHOWED, 2026-08-09, on 55 bets with a close: mean CLV +3.58%
    at t = +2.0, which reads as edge — while the internal check ran
    backwards. Win rate when we "beat the close" was 41.2%; when we did
    not, 61.9%. Beating the close is supposed to PREDICT winning. Half the
    book was being scored against the opposite side of its own market, so
    for those bets the measurement was inverted by construction.

    The snapshots have carried `under_odds` since the table was created
    (db.py). Nothing read it.

    THE LINE IS PART OF THE KEY, and that is the second half of the same
    bug. A price is only comparable to a price AT THE SAME LINE. Without
    it, a bet taken on Over 1.5 was scored against whatever line the book
    happened to be quoting at close — and when a line drops to 0.5 the
    over price shortens hard, which recorded as large POSITIVE value
    exactly when the market had moved AGAINST the over.

    That inverted the bets where the line moved most, which is precisely
    where the information is. Measured 2026-08-09 on 116 rebuilt closes:
    win rate 30.8% when we "beat the close" against 49.0% when we did
    not — an 18-point inversion at 2.0 SE, after the side fix had already
    landed.

    Fixed-line markets (home runs, quoted 0.5 every night) are unaffected
    and keep every row. A moved line now produces no close for that bet
    rather than a fabricated one, which costs coverage and buys a number
    that means what it says.

    Same close-picking discipline otherwise: pre-game snapshots only, last
    instant of the day, median across the books quoted at it. A side with
    no usable price comes back None rather than absent, so a caller can
    tell "no quote" from "no snapshot".
    """
    acc = OddsCloses()
    for r in rows:
        acc.add(r)
    return acc.index()


class OddsCloses:
    """`closing_odds_by_date` a row at a time, as `LineCloses` is for the
    lines: the function is this class's loop."""

    def __init__(self):
        from .sources.oddsapi import normalize_name
        self._norm = normalize_name
        self.grouped: dict[tuple, list[dict]] = {}
        self.copies = _Copies()

    def add(self, r: dict) -> None:
        try:
            float(r["ts"])                         # reject unusable rows early
            # A row is usable if EITHER side is quoted. Requiring the over
            # was what made the under invisible.
            if r.get("over_odds") in (None, "") and \
                    r.get("under_odds") in (None, ""):
                return
            date = _slate_day(r)
            ln = round(float(r["line"]), 1)
            name = self._norm(r["player"])
            self.grouped.setdefault(
                (name, r["market"], date, ln),
                []).append(_slim(r, _ODDS_KEYS))
            self.copies.add(name, r)
        except (KeyError, TypeError, ValueError):
            return

    def index(self) -> dict:
        return _odds_index(self.grouped, self.copies)


def _odds_index(grouped: dict, copies) -> dict:
    """`closing_odds_by_date`'s answer from its grouped rows."""
    out = _CloseIndex()
    # Another player's quotes are nobody's close (`_Copies`, 2026-11-06).
    out.twins = twins = copies.found()
    out.unsure = copies.unsure
    for key, items in grouped.items():
        # Per game, as `closing_lines_by_date`: the plain key is the first
        # game's close, and a doubleheader adds ``key + (leg,)``.
        legs = _pregame_legs(items)
        for n, (start, pre) in enumerate(legs, 1):
            pre = _uncopied(key, pre, twins)
            if not pre:
                continue
            val = _price_close(pre)
            if n == 1:
                out[key] = val
                if start is not None:
                    out.stamped.add(key)
            if len(legs) > 1:
                out[key + (n,)] = val
    return out


def _price_close(items: list[dict]) -> dict:
    """``{"over", "under"}`` medians at the last instant among ``items``."""
    last = max(float(r["ts"]) for r in items)
    at_close = [r for r in items if float(r["ts"]) == last]

    def _side(col):
        vals = []
        for r in at_close:
            v = r.get(col)
            if v in (None, ""):
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            # A LEGAL AMERICAN PRICE HAS |odds| >= 100. There is no
            # such quote as -5: the range between -100 and +100 does
            # not exist, and a number landing there is a number that
            # got into a price column, not a price.
            #
            # Found 2026-08-09 in the CLV worst decile — two closes
            # recorded as -5, which `american_to_decimal` reads as
            # decimal 21.0, a 4.8% longshot. Each produced a CLV
            # around -45 points on its own and together they were a
            # fifth of the reported mean.
            if abs(v) < 100:
                continue
            vals.append(v)
        return _median(vals) if vals else None

    return {"over": _side("over_odds"), "under": _side("under_odds")}


def todays_rows(rows: list[dict], now: float | None = None) -> list[dict]:
    """Only snapshots taken since local midnight.

    Movement is meaningful within ONE day's board. MLB plays every day, so
    without this cut yesterday's price on the same player/market chains onto
    today's and fabricates "movement" between two different games."""
    import datetime as _dt
    now = now if now is not None else time.time()
    midnight = _dt.datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    return [r for r in rows if float(r.get("ts", 0)) >= midnight]


#: Points a prop's own tape keeps. The page draws a sparkline; past this
#: the picture is the same and the board file is bigger.
SERIES_MAX = 48


def _payout(odds) -> float:
    o = float(odds)
    return o / 100.0 if o > 0 else 100.0 / abs(o)


def prop_series(rows: list[dict], player: str, market: str,
                side: str = "OVER", limit: int = SERIES_MAX) -> list[dict]:
    """``[{ts, line, odds, book, books}]`` — one point per snapshot
    instant: the consensus (median) line across the books quoting then,
    and the best price for ``side`` among the books at that line.

    Ethan, 2026-09-05: "line movement on prop page". The snapshots have
    been written on every real odds pull since the movement engine
    shipped, and the card has stamped "Market with/against pick" off
    them since August; nothing drew the line itself. This is the
    read-back, side-aware for the reason `analyze` is: an UNDER's price
    is the under price, and reading the over's for it would draw the
    other bet.

    Oldest first. Past ``limit`` the tape is thinned to an even spread
    that always keeps the first and the last point — the open and the
    now are the two a reader asks about. Proxies were never written, so
    every point is a real book number; a side nobody quoted at that
    instant leaves the price None rather than a fabricated −110.
    """
    want_under = str(side or "OVER").upper() == "UNDER"
    by_ts: dict = {}
    for r in rows:
        if r.get("player") != player or r.get("market") != market:
            continue
        try:
            ts, line = float(r["ts"]), float(r["line"])
        except (KeyError, TypeError, ValueError):
            continue
        px = r.get("under_odds") if want_under else r.get("over_odds")
        by_ts.setdefault(ts, []).append((line, px, r.get("book")))
    out: list[dict] = []
    for ts in sorted(by_ts):
        snaps = by_ts[ts]
        lines = sorted(ln for ln, _p, _b in snaps)
        med = lines[len(lines) // 2]
        at = [(px, b) for ln, px, b in snaps
              if ln == med and px is not None and float(px) != 0]
        best = max(at, key=lambda pb: _payout(pb[0])) if at else (None, None)
        out.append({"ts": ts, "line": med, "odds": best[0], "book": best[1],
                    "books": len(snaps)})
    if len(out) > limit:
        step = (len(out) - 1) / (limit - 1)
        keep = sorted({round(i * step) for i in range(limit)} | {0, len(out) - 1})
        out = [out[i] for i in keep][:limit]
    return out


def attach_series(recs: list[dict], rows: list[dict]) -> int:
    """Hang today's tape on every priced pick that has one. Returns how
    many got one, so the build can say so. Two points is the floor for
    the reason the line tape's is: one point is not a line."""
    n = 0
    for rec in recs:
        if rec.get("has_market") is False:
            continue
        side = rec.get("side")
        if side not in ("OVER", "UNDER"):
            continue
        series = prop_series(rows, rec.get("player", ""), rec.get("market", ""), side)
        if len(series) < 2:
            continue
        rec["line_series"] = series
        n += 1
    return n


def closing_lines(rows: list[dict], before_ts: float | None = None
                  ) -> dict[tuple[str, str], float]:
    """Latest recorded line per ``(player, market)`` — the closing number.

    Beating the closing line is the industry's best available evidence that a
    bet was actually +EV, and unlike a true edge measurement it needs no paid
    historical odds: we simply keep snapshotting until the game starts and take
    the last one. Where several books are quoted at the same instant we take the
    median, so one outlier book can't define the close.

    ``before_ts`` restricts to snapshots at or before a cutoff (e.g. first
    pitch), so a stale post-game snapshot can't masquerade as the close.
    """
    latest: dict[tuple[str, str], float] = {}
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        try:
            ts = float(r["ts"])
            key = (r["player"], r["market"])
        except (KeyError, TypeError, ValueError):
            continue
        if before_ts is not None and ts > before_ts:
            continue
        grouped.setdefault(key, []).append(r)

    for key, items in grouped.items():
        items = _pregame_only(items)
        if not items:
            continue
        last_ts = max(float(r["ts"]) for r in items)
        at_close = [float(r["line"]) for r in items
                    if float(r["ts"]) == last_ts and r.get("line") is not None]
        if at_close:
            latest[key] = _median(at_close)
    return latest


# --- analysis (pure) --------------------------------------------------------
@dataclass
class BookMove:
    book: str
    open: float
    current: float
    delta: float
    last_move_ts: float
    #: When this book FIRST left its opening number. `last_move_ts` says
    #: when it stopped moving, which is the wrong end for attribution:
    #: §4 asks who moved first, because "the first mover took the smart
    #: money; the rest are copying".
    first_move_ts: float = 0.0
    open_odds: int | None = None       # over-side price at open
    current_odds: int | None = None
    prob_delta: float = 0.0            # implied-prob shift of the over side


@dataclass
class MoveReport:
    player: str
    market: str
    open: float          # consensus (median) opening line
    current: float       # consensus current line
    delta: float
    direction: str       # "up" | "down"
    steam: bool
    books: list[BookMove] = field(default_factory=list)
    prob_delta: float = 0.0            # consensus implied-prob shift (over)
    open_odds: int | None = None       # consensus over price at open
    current_odds: int | None = None
    #: FIRST-MOVER ATTRIBUTION (§4). The book that left its opening
    #: number first among those that moved with the eventual direction,
    #: and how far ahead of the next one it was.
    #:
    #: EVIDENCE ONLY. Nothing prices from this, and that is deliberate
    #: rather than unfinished: `engine/quality.apply_movement` already
    #: gives movement veto power over the board — it can set grade="Pass"
    #: and stake 0 — on a signal whose predictive value has never been
    #: measured. `movecheck.py` exists to settle that, and until it says
    #: something, adding a second unmeasured movement signal to the grade
    #: would repeat the mistake with more confidence.
    first_mover: str | None = None
    first_mover_lead_s: float = 0.0
    #: True when the first mover is one of the sharp books. That is the
    #: case §4 actually cares about; a recreational book moving first is
    #: usually a stale line being corrected, not information arriving.
    first_mover_sharp: bool = False


def lineup_release_move(rows: list[dict], player: str, market: str,
                        line: float | None, side: str,
                        posted_ts: float) -> dict | None:
    """The move across the lineup-card boundary, from OUR side's view.

    §4 calls this baseball's unique tell: "If a number moved against your
    position right after lineups confirmed, the market just priced
    information — a star's rest day, a platoon swap, a lefty-heavy
    lineup — that your inputs may have missed."

    Returns None when the boundary cannot be straddled — no reading
    before, or none after. That is the common case early on and it is a
    real answer: a prop we only ever saw once tells us nothing about what
    the card did to it, and inventing a zero would bury the signal under
    props that were never observed.

    SIGN CONVENTION, which is the whole thing. `delta` is in implied
    probability of OUR side, so negative always means the market moved
    AGAINST us — our number got longer after the card posted. An OVER and
    an UNDER on the same prop must produce opposite signs from the same
    two prices, and getting that backwards would flag exactly the wrong
    half of the board.
    """
    want_under = (side or "OVER").upper() == "UNDER"
    key_line = round(float(line), 1) if line is not None else None
    before: list[tuple] = []
    after: list[tuple] = []
    for r in rows:
        if r.get("player") != player or r.get("market") != market:
            continue
        if key_line is not None and r.get("line") is not None \
                and round(float(r["line"]), 1) != key_line:
            continue
        px = r.get("under_odds") if want_under else r.get("over_odds")
        p = _implied(px)
        if p is None or r.get("ts") is None:
            continue
        (after if float(r["ts"]) >= posted_ts else before).append(
            (float(r["ts"]), p, r.get("book")))
    if not before or not after:
        return None
    # Last reading before the card, first after it — the tightest pair
    # that straddles the boundary. Using the whole day's median either
    # side would fold in movement that has nothing to do with the card.
    before.sort()
    after.sort()
    p0 = _median([p for ts, p, _b in before if ts == before[-1][0]])
    p1 = _median([p for ts, p, _b in after if ts == after[0][0]])
    return {
        "before": round(p0, 4), "after": round(p1, 4),
        "delta": round(p1 - p0, 4),
        "against_us": (p1 - p0) < 0,
        "gap_s": round(after[0][0] - before[-1][0], 1),
        "books_before": len({b for _t, _p, b in before if _t == before[-1][0]}),
        "books_after": len({b for _t, _p, b in after if _t == after[0][0]}),
    }


def _is_sharp(book: str) -> bool:
    """Is this one of the books §4 says shapes the truth?

    Matched loosely on purpose: the snapshots carry display names
    ("Pinnacle"), `oddsapi.SHARP_BOOKS` carries API keys ("pinnacle"),
    and a strict comparison between the two silently answers False
    forever — the most expensive kind of wrong, because it looks like a
    finding about the market.

    ONE DEFINITION NOW, in `engine.odds.is_sharp_book`. This copy and
    `booksharp.compare_to_the_list`'s were identical, and the shopping
    guard that refuses to quote a sharp price needed a third — three
    copies of a predicate that must agree is a drift waiting to happen,
    and the drift would show up as a report naming a book the shop had
    already stopped avoiding.
    """
    from .odds import is_sharp_book
    return is_sharp_book(book)


def _implied(odds) -> float | None:
    """American odds → implied probability (vig included)."""
    from .odds import implied_or_none
    return implied_or_none(odds, parse=int)


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def analyze(rows: list[dict], min_move: float = 0.5, steam_books: int = 2,
            window_s: float = 3600.0, now: float | None = None,
            min_prob_move: float = 0.02) -> list[MoveReport]:
    """Collapse the snapshot history into per-prop movement reports.

    Movement lives in two places: the LINE (yardage props re-price by moving
    the number) and the PRICE (many MLB props sit on a fixed 0.5 / 1.5 line
    and re-price through the juice — the line never moves, the odds do).
    Both are tracked; ``min_prob_move`` is the implied-probability shift on
    the over side that counts as a real price move.

    Consecutive identical snapshots are deduped, so re-recording an unchanged
    board (e.g. from a cached response) never fabricates movement.
    """
    now = now if now is not None else time.time()

    # (player, market, book) -> time-ordered [(ts, line, over_odds)]
    series: dict[tuple, list[tuple]] = {}
    for r in rows:
        key = (r["player"], r["market"], r["book"])
        series.setdefault(key, []).append(
            (float(r["ts"]), float(r["line"]), r.get("over_odds")))

    per_prop: dict[tuple, list[BookMove]] = {}
    for (player, market, book), pts in series.items():
        pts.sort(key=lambda p: p[0])
        dedup: list[tuple] = []
        for ts, line, odds in pts:
            if not dedup or dedup[-1][1] != line or dedup[-1][2] != odds:
                dedup.append((ts, line, odds))
        open_line, current = dedup[0][1], dedup[-1][1]
        p0, p1 = _implied(dedup[0][2]), _implied(dedup[-1][2])
        # The FIRST departure from the opening number. dedup has already
        # collapsed unchanged re-records, so index 1 is by construction
        # the first real change — no threshold here, because a book that
        # nudges a half-cent and then leaps is still the book that moved
        # first, and thresholding would hand the credit to whoever moved
        # loudest instead.
        first_ts = dedup[1][0] if len(dedup) > 1 else 0.0
        per_prop.setdefault((player, market), []).append(BookMove(
            book=book, open=open_line, current=current,
            delta=current - open_line,
            last_move_ts=dedup[-1][0] if len(dedup) > 1 else 0.0,
            first_move_ts=first_ts,
            open_odds=dedup[0][2], current_odds=dedup[-1][2],
            prob_delta=(p1 - p0) if p0 is not None and p1 is not None else 0.0,
        ))

    reports = []
    for (player, market), books in per_prop.items():
        delta = _median([b.current for b in books]) - _median([b.open for b in books])
        prob_delta = _median([b.prob_delta for b in books])
        if (abs(delta) < 1e-9 and abs(prob_delta) < min_prob_move
                and not any(abs(b.delta) >= min_move for b in books)):
            continue  # nothing moved
        # Direction: the line move wins when there is one; otherwise the
        # price move (over shortening = "up", drifting = "down").
        direction = ("up" if delta >= 0 else "down") if abs(delta) >= 1e-9 \
            else ("up" if prob_delta >= 0 else "down")
        sign = 1 if direction == "up" else -1
        movers = [
            b for b in books
            if (sign * b.delta >= min_move or sign * b.prob_delta >= min_prob_move)
            and (now - b.last_move_ts) <= window_s
        ]
        # WHO WENT FIRST, among the books that moved WITH the eventual
        # direction. A book that moved the other way and got dragged back
        # is not the first mover of this move; it is noise that happens to
        # be early, and crediting it would invert the whole signal.
        with_dir = [b for b in books
                    if b.first_move_ts > 0
                    and (sign * b.delta > 0 or sign * b.prob_delta > 0)]
        with_dir.sort(key=lambda b: b.first_move_ts)
        first_mover = with_dir[0].book if with_dir else None
        # The lead is only meaningful against a SECOND mover. One book
        # moving alone has no lead over anybody, and reporting a huge one
        # would read as a strong signal when it is an absent comparison.
        lead = (with_dir[1].first_move_ts - with_dir[0].first_move_ts
                if len(with_dir) > 1 else 0.0)
        odds_open = [b.open_odds for b in books if b.open_odds is not None]
        odds_cur = [b.current_odds for b in books if b.current_odds is not None]
        reports.append(MoveReport(
            player=player, market=market,
            open=round(_median([b.open for b in books]), 1),
            current=round(_median([b.current for b in books]), 1),
            delta=round(delta, 1),
            direction=direction,
            steam=len(movers) >= steam_books,
            books=books,
            prob_delta=round(prob_delta, 4),
            open_odds=int(_median([float(o) for o in odds_open])) if odds_open else None,
            current_odds=int(_median([float(o) for o in odds_cur])) if odds_cur else None,
            first_mover=first_mover,
            first_mover_lead_s=round(lead, 1),
            first_mover_sharp=bool(
                first_mover and _is_sharp(first_mover)),
        ))
    reports.sort(key=lambda r: (r.steam, abs(r.delta), abs(r.prob_delta)),
                 reverse=True)
    return reports


def _fmt_odds(o) -> str:
    return f"{int(o):+d}" if o is not None else "?"


def _describe(r: MoveReport) -> str:
    """Human-readable "what moved": the line when it moved, else the price."""
    if abs(r.delta) >= 1e-9:
        return f"line {r.open:g} → {r.current:g}"
    return f"Over price {_fmt_odds(r.open_odds)} → {_fmt_odds(r.current_odds)}"


def summary_lines(reports: list[MoveReport], limit: int = 10) -> list[str]:
    out = []
    for r in reports[:limit]:
        arrow = "▲" if r.direction == "up" else "▼"
        steam = "  🔥 STEAM" if r.steam else ""
        # WHO WENT FIRST. §4: "Which book moved first matters — the first
        # mover took the smart money; the rest are copying." It was
        # computed, tested, and then read by nothing at all — the
        # data-use audit reported it INERT, which was fair. A sharp book
        # leading is the case §4 cares about, so it is called out; a
        # recreational book leading usually means a stale number being
        # corrected and is shown plainly.
        first = ""
        if r.first_mover:
            lead = (f", {r.first_mover_lead_s / 60:.0f}m clear"
                    if r.first_mover_lead_s >= 60 else "")
            first = (f"  [{'SHARP ' if r.first_mover_sharp else ''}"
                     f"{r.first_mover} first{lead}]")
        out.append(f"  {arrow} {r.player} {r.market}: {_describe(r)}"
                   f"{steam}{first}")
    return out


# --- the signal: movement vs OUR pick ---------------------------------------
def annotate_recommendations(recs: list[dict], reports: list[MoveReport],
                             price: bool = True) -> int:
    """Stamp each recommendation with how the market has moved relative to
    the side WE like since our first recorded snapshot.

    "up" always means toward the Over (line raised, or the over price
    shortening), so a move agrees with an OVER pick and fights an UNDER pick.
    Agreement becomes a reason ("the market is moving our way" — the same
    direction sharp money shows up as); disagreement becomes a warning, which
    is the honest thing to show when books are actively re-pricing away from
    our number. NOT informational: this calls quality.apply_movement, which
    moves the quality score (±4, or ±7 on steam), can raise the letter, and
    REJECTS the pick outright if the drop puts it under 70. It never raises
    the stake. Said plainly because the reverse was written here for a while,
    and a reader who believes movement is inert will not go looking for it
    when a pick he expected disappears off the board.

    Returns how many recommendations got a movement stamp.
    """
    from .sources.oddsapi import normalize_name

    idx = {(normalize_name(r.player), r.market): r for r in reports}
    n = 0
    for rec in recs:
        if rec.get("has_market") is False:
            continue
        side = rec.get("side")
        if side not in ("OVER", "UNDER"):
            continue
        rep = idx.get((normalize_name(rec.get("player", "")),
                       rec.get("market", "")))
        if not rep:
            continue
        with_us = (rep.direction == "up") == (side == "OVER")
        last_move = max((b.last_move_ts for b in rep.books), default=0.0)
        rec["line_move"] = {
            "open": rep.open, "current": rep.current, "delta": rep.delta,
            "open_odds": rep.open_odds, "current_odds": rep.current_odds,
            "prob_delta": rep.prob_delta, "direction": rep.direction,
            "steam": rep.steam, "verdict": "with" if with_us else "against",
            # Age of the newest book move, so an alert can be classified
            # Live / Chase / Stale instead of showing a move already missed.
            "moved_ago_min": round((time.time() - last_move) / 60.0)
                             if last_move else None,
            # WHO LED, carried onto the pick so it can be JOURNALED and
            # therefore mined. §4 says the first mover took the smart
            # money and the rest are copying — if that is true, picks a
            # sharp book led against should lose more often than picks a
            # recreational book drifted on, and that is a question the
            # loss miner can answer once the column has rows.
            #
            # Journaling is not pricing. Nothing here moves a grade: the
            # movement engine ALREADY vetoes picks on an unmeasured
            # signal (#80), and a second one would repeat that mistake.
            # This only makes the evidence collectable.
            "first_mover": rep.first_mover,
            "first_mover_sharp": rep.first_mover_sharp,
        }
        rec["move_first_sharp"] = (
            1.0 if rep.first_mover_sharp else 0.0) if rep.first_mover else None
        what = _describe(rep)
        steam_txt = " (steam — several books moved together)" if rep.steam else ""
        if with_us:
            rec.setdefault("reasons", []).append(
                f"Market moving toward the {side.title()} — {what} since "
                f"our first snapshot{steam_txt}")
        else:
            rec.setdefault("warnings", []).append(
                f"Market moving against the {side.title()} — {what} since "
                f"our first snapshot{steam_txt}")
        # §4/§10: movement is 15% of the unified quality grade. With-steam
        # raises the score; sharp movement against drops it — below 70 the
        # pick is rejected (fresh sharp money beats a stale model input).
        #
        # `price=False` is the evidence-only mode, for the boards where a
        # human has not yet approved movement as a pricing input. It keeps
        # every stamp — line_move, first mover, the reason/warning — and
        # skips only this call, because the difference between "the card
        # says the market moved against us" and "the pick vanished off the
        # board" is exactly the difference between evidence and pricing.
        if price:
            from .quality import apply_movement
            apply_movement(rec, with_us, rep.steam)
        n += 1
    return n
