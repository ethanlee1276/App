"""The parlay journal — §11 logging and §13 site publication.

The Parlay Zone has been publishing tickets with no record of whether they
were right. That is the same failure the settle guard was just built to
prevent, one step earlier: a number on a page that nothing can check.

Four decisions shape this module, and each of them is a choice that could
have gone the other way.

**Its own tables, not ``bets``.** §13 is explicit that the parlay record is
reported separately and never blended, and a ticket does not fit the singles
row anyway — it has N legs, each with its own price and its own closing
line, and §11 says leg-level CLV is the only honest parlay CLV. Putting
tickets in ``bets`` would blend them by construction and lose the legs.

**Legs settle by joining the singles journal, not by grading again.** §14:
a ticket arrives only after every leg has independently earned a place on
the board as a single, so every leg is already journaled and already graded.
Joining means one grading path rather than two that can disagree — and the
parlay bucket inherits the premature-settle guard for free. A second grader
here would have quietly reintroduced the bug we just spent a day removing.

**Every published ticket is journaled, including the ones we declined.**
§12 says "no qualifying parlay" should be the most common output by a wide
margin, and on this board it is. Recording only the tickets that cleared
would measure the gates on the handful of nights they said yes. Recording
the declines is the only way to ever learn whether the no was right, and it
is what makes the 100-ticket probation bar reachable this decade.

**No fabricated price.** §11 wants ``quoted_dec`` — what you paid — and
``correlation_tax`` tracked by book. We have neither: no odds feed we ingest
carries same-game-parlay prices, and an SGP price is not derivable from the
leg prices, which is precisely why the Zone publishes a required price
instead of a quote. So ``quoted_dec`` stays NULL until a real quote is ever
recorded, grading runs against an explicitly-labelled ``assumed_dec``, and
``price_basis`` says which it was. The by-book tax table §11 asks for is
built and will stay empty until real quotes exist — an empty table that
says why is worth more than a full one built from our own assumption.

Nothing here touches the bankroll. §13 puts parlays on probation: graded,
never staked. Tickets carry a flat one-unit NOTIONAL so ROI means something
and a zero real stake so the account does not move.
"""

from __future__ import annotations

import datetime
import json
import math
import sqlite3
from pathlib import Path

from .db import column_exists_or_raise

#: §13's promotion bar. A hundred graded tickets before anything is staked,
#: and the singles board has to clear its own bar first.
PROBATION_TICKETS = 100

#: The t-statistic §13 requires on flat-stake P&L before promotion.
PROMOTION_Z = 2.0

#: Every ticket is graded at one flat unit. §13 stakes nothing, but a record
#: with no notional has no ROI, and "positive flat-stake ROI" is the first
#: of the three promotion conditions.
NOTIONAL_UNITS = 1.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS parlays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, sport TEXT, date TEXT,
    legs_key TEXT,
    parlay_type TEXT, n_legs INTEGER,
    grade TEXT, qualified INTEGER DEFAULT 0, was_play INTEGER DEFAULT 0,
    naive_product_dec REAL,
    quoted_dec REAL,
    assumed_dec REAL,
    price_basis TEXT,
    book TEXT,
    source TEXT DEFAULT 'edge',
    correlation_tax REAL,
    modeled_joint REAL, implied_joint REAL,
    independent_joint REAL,
    edge_points REAL, threshold_points REAL,
    dominance_ratio REAL,
    singles_alternative_ev REAL,
    conditional_reasoning TEXT,
    clash_screen_result TEXT,
    stake_units REAL DEFAULT 0,
    notional_units REAL DEFAULT 1.0,
    status TEXT DEFAULT 'open',
    legs_won INTEGER, legs_lost INTEGER, legs_void INTEGER,
    pnl_units REAL,
    singles_pnl_units REAL,
    loss_code TEXT, loss_codes TEXT,
    settled_ts TEXT,
    UNIQUE (sport, date, legs_key)
);

CREATE TABLE IF NOT EXISTS parlay_legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parlay_id INTEGER, leg_no INTEGER,
    player TEXT, team TEXT, market TEXT, side TEXT, line REAL,
    odds INTEGER, book TEXT, p_final REAL,
    status TEXT DEFAULT 'open', actual REAL, closing_line REAL, clv REAL,
    UNIQUE (parlay_id, leg_no)
);
"""


def ensure_schema(conn) -> None:
    """Create the parlay tables if they are not there yet.

    Called at the top of every public function rather than from
    ``ledger.connect``, so this module stays a leaf: ledger knows nothing
    about parlays and there is no import cycle to unpick later.
    """
    conn.executescript(SCHEMA)
    # WHICH BOARD THE LEGS CAME FROM, added 2026-09-06 when the screen
    # learned to run over Most Likely as well as the edge board. `book`
    # is the SPORTSBOOK and was never this; without a column of its own
    # the two records would land in one table and every ROI in the
    # report would answer a question nobody asked — the same failure
    # `ledger.BOOK` against `category='likely'` exists to prevent on the
    # singles side.
    #
    # DEFAULT 'edge' RATHER THAN NULL: every row written before today
    # came from the edge board, and calling that unknown would put the
    # whole existing record into a bucket labelled "we are not sure".
    #
    # The read is a fast path, not a lock: `ensure_schema` runs per
    # request on a threaded server, so two requests on the first pass
    # after a deploy can both read `parlays` without `source` and both
    # ALTER it (the race that 500'd the feed and billing, nightly
    # 2026-10-27). The loser swallows the duplicate — and still runs the
    # backfill, because the winner's DEFAULT only covers rows written
    # after it. A lock must still raise (audit 2026-09-30, F-10).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(parlays)")}
    if "source" not in cols:
        try:
            conn.execute("ALTER TABLE parlays ADD COLUMN source TEXT "
                         "DEFAULT 'edge'")
        except sqlite3.OperationalError as exc:
            column_exists_or_raise(exc)
        conn.execute("UPDATE parlays SET source='edge' WHERE source IS NULL")
    # EACH LEG'S SOURCE AND THE BOOK'S CHANCE FOR IT (2026-11-16), so the
    # record can say which source a leg came from (the Most Likely board, the
    # Edge picks or another priced prop: engine/gameparlays.SOURCE_RANK) and
    # how far our number sat from the market's. NULL on a leg journaled
    # before: that is "before we kept it", which is what it is. The same
    # race-tolerant ALTER as `source` above.
    # …and OUR OWN CHANCE BEFORE THE LEARNED CORRECTION (`p_raw`, engine/legfit,
    # 2026-11-16), so the correction is always learned on our number and
    # never on top of itself; NULL where none applied (`p_final` is ours).
    legcols = {r[1] for r in conn.execute("PRAGMA table_info(parlay_legs)")}
    for col, kind in (("pool", "TEXT"), ("fair", "REAL"), ("p_raw", "REAL")):
        if col not in legcols:
            try:
                conn.execute(f"ALTER TABLE parlay_legs ADD COLUMN {col} {kind}")
            except sqlite3.OperationalError as exc:
                column_exists_or_raise(exc)
    # WHETHER A GAME'S TICKET WAS IN THE SET ITS REPORT CARRIED AT THE START
    # (`at_start`, 2026-11-19; `mark_at_start`): 1 it was, 0 an earlier
    # version replaced before the start, NULL not known (a game still to
    # play, or one whose starting set was never kept). The same race-tolerant
    # ALTER as `source` above.
    if "at_start" not in cols:
        try:
            conn.execute("ALTER TABLE parlays ADD COLUMN at_start INTEGER")
        except sqlite3.OperationalError as exc:
            column_exists_or_raise(exc)
    conn.commit()


# --- identity ---------------------------------------------------------------
def legs_key(legs: list[dict]) -> str:
    """A stable identity for a ticket, independent of leg order.

    A slate is rebuilt every 60 seconds. Without this the same ticket would
    journal afresh on every refresh and the record would count one night's
    single observation several hundred times.
    """
    parts = sorted(
        f"{(l.get('player') or '').strip().lower()}|{l.get('market') or ''}|"
        f"{(l.get('side') or '').upper()}|{float(l.get('line') or 0):g}"
        for l in legs)
    return "::".join(parts)


# --- logging ----------------------------------------------------------------
def log_board(conn, board: dict, sport: str | None = None,
              date: str | None = None) -> int:
    """Journal the tickets on one built board. Returns rows newly written.

    Takes the whole ``parlays`` payload the Zone renders, so the journal
    records exactly what the reader was shown — not a recomputation that
    could drift from it.

    Only rank 1 is journaled. The shortlist below it exists so the page can
    show its work; treating four constructions off one slate as four
    observations would quadruple the sample without quadrupling the
    evidence, since they share legs and therefore share their outcome.
    """
    ensure_schema(conn)
    tickets = board.get("tickets") or []
    if not tickets:
        return 0
    t = tickets[0]
    sport = sport or t.get("sport") or board.get("sport") or ""
    date = date or board.get("date") or ""
    if not sport or not date:
        return 0
    legs = t.get("legs") or []
    if len(legs) < 2:
        return 0

    key = legs_key(legs)
    if conn.execute("SELECT 1 FROM parlays WHERE sport=? AND date=? AND "
                    "legs_key=?", (sport, date, key)).fetchone():
        return 0

    naive = float(t.get("naive_product_dec") or 0.0)
    # The price this ticket is GRADED at. Not a quote — see the module
    # docstring. The likely case is the naive product less the mid-point of
    # the best- and worst-case correlation taxes the doc tabulates, which is
    # the same number the card publishes as its likely price.
    tax = _assumed_tax(t)
    assumed = naive * (1.0 - tax) if naive else 0.0
    books = {(l.get("book") or "").strip() for l in legs if l.get("book")}

    cur = conn.execute(
        "INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs,"
        " grade, qualified, was_play, naive_product_dec, quoted_dec,"
        " assumed_dec, price_basis, book, correlation_tax, modeled_joint,"
        " implied_joint, independent_joint, edge_points, threshold_points,"
        " dominance_ratio, singles_alternative_ev, conditional_reasoning,"
        " clash_screen_result, stake_units, notional_units, source, status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open')",
        (datetime.datetime.now().isoformat(timespec="seconds"), sport, date,
         key, t.get("parlay_type") or "A", len(legs), t.get("grade") or "short",
         1 if t.get("qualified") else 0, 1 if t.get("slate_play") else 0,
         round(naive, 4) or None,
         None,                       # quoted_dec: no real SGP quote exists
         round(assumed, 4) or None,
         "assumed_likely_case", "|".join(sorted(books)) or None,
         round(tax, 4),
         t.get("modeled_joint"),
         round(1.0 / assumed, 4) if assumed else None,
         t.get("independent_joint"),
         t.get("edge_at_ceiling_points"), t.get("threshold_points"),
         _dominance(t), t.get("singles_alternative_same_stake"),
         _reasoning(t), t.get("clash_screen"),
         # THE BOARD, READ OFF THE PAYLOAD RATHER THAN PASSED IN. `screen`
         # stamps `pool` on what it returns, so the journal records which
         # screen actually produced the ticket instead of trusting a
         # caller to remember which one it invoked. A payload with no
         # pool predates the split and is edge by definition.
         0.0, NOTIONAL_UNITS, board.get("pool") or "edge"))
    pid = cur.lastrowid
    for i, l in enumerate(legs, start=1):
        conn.execute(
            "INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market,"
            " side, line, odds, book, p_final, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,'open')",
            (pid, i, l.get("player"), l.get("team"), l.get("market"),
             l.get("side"), l.get("line"), l.get("odds"), l.get("book"),
             l.get("p_final")))
    conn.commit()
    return 1


def _assumed_tax(t: dict) -> float:
    """Mid-point of the doc's best- and worst-case SGP taxes.

    Grading at the best case would flatter the record with a price no book
    offers; grading at the worst case would bury it under one. The midpoint
    is the honest guess, and ``price_basis`` records that it IS a guess.
    """
    best = float(t.get("correlation_tax_best_case") or 0.0)
    worst = float(t.get("correlation_tax_worst_case") or 0.0)
    return (best + worst) / 2.0 if (best or worst) else 0.0


def _dominance(t: dict) -> float | None:
    """EV_parlay / EV_singles, §11's ``dominance_ratio``."""
    alt = t.get("singles_alternative_same_stake")
    par = t.get("ev_parlay_at_required")
    try:
        alt, par = float(alt), float(par)
    except (TypeError, ValueError):
        return None
    return round(par / alt, 3) if alt else None


def _reasoning(t: dict) -> str:
    """§11's ``conditional_reasoning`` — why P(B|A) != P(B), in words.

    Assembled from the pair mechanisms the screen already wrote, because a
    ticket logged without them records that we thought the legs correlated
    but not what we thought the mechanism was, and the mechanism is the only
    part a post-mortem can argue with.
    """
    out = []
    for p in t.get("pairs") or []:
        # rho_priced, not rho: the priced number is the one the joint was
        # actually built from (estimates are shrunk, measurements are not),
        # so it is the one a post-mortem should be arguing with.
        rho = p.get("rho_priced", p.get("rho"))
        if rho is None:
            continue
        tag = " (measured)" if p.get("rho_measured") else ""
        pair = f"{p.get('a') or '?'} x {p.get('b') or '?'}"
        out.append(f"{pair} rho {float(rho):+.2f}{tag}: "
                   f"{p.get('mechanism') or ''}".strip())
    return " · ".join(out)


# --- two-leg tickets (engine/twoleg, the Parlays page) ---------------------------------
def log_twoleg(conn, two_leg: dict, sport: str, date: str) -> int:
    """Journal every two-leg ticket a board posted, both pools. Returns rows
    newly written; a ticket already journaled for its day is left alone, so
    a board rebuilt every minute counts each ticket once.

    Every posted ticket is a pick (``qualified``), graded at the price the
    card shows (``assumed_dec``, with ``price_basis`` saying how it was
    reached), one unit notional so its ROI reads, and its real stake beside
    that: the rule's half unit when both legs are staked singles, else 0."""
    ensure_schema(conn)
    if not isinstance(two_leg, dict) or not sport or not date:
        return 0
    from .twoleg import SOURCES
    wrote = 0
    for pool, source in SOURCES.items():
        for t in ((two_leg.get(pool) or {}).get("tickets") or []):
            legs = t.get("legs") or []
            if len(legs) != 2:
                continue
            key = legs_key(legs)
            if conn.execute("SELECT 1 FROM parlays WHERE sport=? AND date=? AND legs_key=?",
                            (sport, date, key)).fetchone():
                continue
            books = {(l.get("book") or "").strip() for l in legs if l.get("book")}
            cur = conn.execute(
                "INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified,"
                " was_play, naive_product_dec, quoted_dec, assumed_dec, price_basis, book, correlation_tax,"
                " modeled_joint, implied_joint, independent_joint, conditional_reasoning, stake_units,"
                " notional_units, source, status) VALUES (?,?,?,?,?,2,?,1,0,?,NULL,?,?,?,?,?,?,?,?,?,?,?,'open')",
                (datetime.datetime.now().isoformat(timespec="seconds"), sport, date, key,
                 t.get("kind") or "two_game", t.get("kind_label") or "",
                 t.get("naive_dec"), t.get("price_dec"), t.get("price_basis") or "",
                 "|".join(sorted(books)) or None,
                 round(1.0 - float(t["price_dec"]) / float(t["naive_dec"]), 4)
                 if t.get("price_dec") and t.get("naive_dec") else None,
                 t.get("joint"), round(1.0 / float(t["price_dec"]), 4) if t.get("price_dec") else None,
                 t.get("independent"), t.get("why") or "",
                 float(t.get("stake_units") or 0.0), NOTIONAL_UNITS, source))
            for i, l in enumerate(legs, start=1):
                conn.execute(
                    "INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, odds, book,"
                    " p_final, status) VALUES (?,?,?,?,?,?,?,?,?,?,'open')",
                    (cur.lastrowid, i, l.get("player"), l.get("team"), l.get("market"), l.get("side"),
                     l.get("line"), l.get("odds"), l.get("book"), l.get("p")))
            wrote += 1
    if wrote:
        conn.commit()
    return wrote


# --- each game's parlays (engine/gameparlays) -----------------------------------------
#: The paper bucket a game parlay's legs are journaled in when the board
#: did not journal them itself (a scorer off the whole touchdown field):
#: outside every headline book (ledger.RECOMMENDED_CATEGORIES), graded by
#: the same settle pass as everything else, so every ticket can settle.
PARLAY_LEG_CATEGORY = "parlay_leg"


#: The lists a game's kept set holds its tickets in (engine/reportkeep keeps the
#: game's `game_parlays` entry as the board had it): posted, and on paper.
KEPT_LISTS = ("threes", "twos", "scorers", "paper_threes", "paper_twos")


def mark_at_start(conn, sport: str, dates, game: str, kept: dict) -> int:
    """ONE SET A GAME ON THE RECORD: THE ONE ITS REPORT CARRIED AT THE START
    (2026-11-19). Ethan, asked whether the parlay record should count only the
    parlays posted at the start: "Yes."

    The board posts a game's parlays afresh as lines and news move, and the
    journal keeps every version it posted (a week of them for the NFL: 36 for
    one game), so the record counted each game's tickets several times over,
    most of them replaced before anyone could bet them at the start. A started
    game's set is the one engine/reportkeep kept (its `game_parlays` entry as
    the board had it at the start, ``kept``): each of the game's journaled
    tickets in it is marked 1, every other version of the game 0, and the
    record (`game_parlay_record`, `report_game_parlays`, the two-leg hold)
    counts the 1s. A kept set that held no ticket held none: every version 0.

    ``dates`` are the days the game's tickets may be journaled under (the
    board's date, the NFL's week, and the game's own day); the first marking
    stands. Returns the rows marked."""
    from .gameparlays import SOURCES
    days = sorted({str(d) for d in (dates or ()) if d})
    if not sport or not game or not days or not isinstance(kept, dict):
        return 0
    keys = sorted({legs_key(t.get("legs") or []) for k in KEPT_LISTS for t in kept.get(k) or []
                   if isinstance(t, dict) and len(t.get("legs") or []) >= 2})
    srcs = sorted(set(SOURCES.values()))
    mark = (f"CASE WHEN legs_key IN ({','.join('?' * len(keys))}) THEN 1 ELSE 0 END" if keys else "0")
    cur = conn.execute(
        f"UPDATE parlays SET at_start = {mark} WHERE sport=? AND grade=? AND at_start IS NULL "
        f"AND source IN ({','.join('?' * len(srcs))}) AND date IN ({','.join('?' * len(days))})",
        (*keys, sport, game, *srcs, *days))
    return cur.rowcount or 0


def mark_started_games(conn, gp: dict, sport: str, date: str) -> int:
    """Every started game a board carries kept (engine/reportkeep marks its
    entry `kept`) marked on the journal (`mark_at_start`). Run on the board as
    built, before any filter: a kept ticket's legs may have no row under the
    board's date once the board has moved on to the next day."""
    ensure_schema(conn)
    n = 0
    for x in (gp or {}).get("games") or []:
        if isinstance(x, dict) and x.get("kept"):
            n += mark_at_start(conn, sport, (date, str(x.get("date") or "")[:10]),
                               x.get("game") or f"{x.get('away')}@{x.get('home')}", x)
    if n:
        conn.commit()
    return n


def mark_from_archive(conn, where=None, sports=None) -> int:
    """The starting sets of finished games already archived (engine/reportarchive
    keeps each one's kept set under "parlays", with its board's label), marked
    on the journal: the games that started before the journal marked them as
    they started. Never raises; returns the rows marked."""
    from . import reportarchive
    if where is None:
        from .gate import FULL_DIR
        where = FULL_DIR
    root = Path(where) / reportarchive.DIR
    n = 0
    try:
        ensure_schema(conn)
        for league in sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []:
            if sports and league not in sports:
                continue
            for day_dir in sorted(p for p in (root / league).iterdir() if p.is_dir()):
                for f in sorted(day_dir.glob("*@*.json.gz")):
                    away, _, home = f.name[:-len(".json.gz")].partition("@")
                    doc = reportarchive.load(league, day_dir.name, away, home, where)
                    kept = (doc or {}).get("parlays")
                    if isinstance(kept, dict):
                        n += mark_at_start(conn, league, (doc.get("label"), day_dir.name),
                                           kept.get("game") or f"{doc.get('away') or away}@{doc.get('home') or home}",
                                           kept)
        if n:
            conn.commit()
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ parlay journal: starting sets not marked from the archive ({type(exc).__name__}: {exc})")
    return n


def log_game_parlays(conn, gp: dict, sport: str, date: str) -> int:
    """Journal every ticket a board's game parlays posted (engine/gameparlays:
    two or three three-leg tickets and three scorer pairs a game), each under its
    own source, tracked at a stake of nothing, graded at the least price
    its card says to take it at. Returns tickets newly written; a ticket
    already journaled for its day is left alone."""
    ensure_schema(conn)
    if not isinstance(gp, dict) or not sport or not date:
        return 0
    from .gameparlays import SOURCES
    wrote = 0
    for x in gp.get("games") or []:
        # A started game's tickets, kept on the board after the start
        # (engine/reportkeep): journaled before it, or not at all.
        if isinstance(x, dict) and x.get("kept"):
            continue
        for kind, source in SOURCES.items():
            # A league's three-leg tickets on paper (engine/parlayhold) are
            # journaled and graded as ever: the record keeps learning on them.
            keys = (("threes", "paper_threes") if kind == "three" else ("twos", "paper_twos") if kind == "two"
                    else ("scorers",))
            for t in [t for k in keys for t in x.get(k) or []]:
                legs = t.get("legs") or []
                if len(legs) < 2:
                    continue
                key = legs_key(legs)
                if conn.execute("SELECT 1 FROM parlays WHERE sport=? AND date=? AND legs_key=?",
                                (sport, date, key)).fetchone():
                    continue
                books = {(l.get("book") or "").strip() for l in legs if l.get("book")}
                take = t.get("take_dec")
                cur = conn.execute(
                    "INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified,"
                    " was_play, naive_product_dec, quoted_dec, assumed_dec, price_basis, book, correlation_tax,"
                    " modeled_joint, implied_joint, independent_joint, conditional_reasoning, stake_units,"
                    " notional_units, source, status) VALUES (?,?,?,?,?,?,?,1,0,?,NULL,?,?,?,NULL,?,?,?,?,0,?,?,'open')",
                    (datetime.datetime.now().isoformat(timespec="seconds"), sport, date, key,
                     "same_game", len(legs), x.get("game") or "", t.get("naive_dec"), take,
                     "the least price the card says to take it at: our fair price and 5%",
                     "|".join(sorted(books)) or None, t.get("joint"),
                     round(1.0 / float(take), 4) if take else None, t.get("independent"),
                     "; ".join(t.get("links") or []) or (t.get("script") or ""),
                     NOTIONAL_UNITS, source))
                for i, l in enumerate(legs, start=1):
                    conn.execute(
                        "INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, odds, book,"
                        " p_final, status, pool, fair, p_raw) VALUES (?,?,?,?,?,?,?,?,?,?,'open',?,?,?)",
                        (cur.lastrowid, i, l.get("player"), l.get("team"), l.get("market"),
                         str(l.get("side") or "").upper() or None,
                         l.get("line") if l.get("line") is not None else 0.5, l.get("odds"), l.get("book"),
                         l.get("p"), l.get("pool") or None, l.get("fair"), l.get("p_raw")))
                wrote += 1
    if wrote:
        conn.commit()
    return wrote


def journal_game_parlay_legs(conn, board: dict, sport: str) -> int:
    """Every leg of a board's game parlays on paper (PARLAY_LEG_CATEGORY),
    so each ticket's legs have rows the settle pass grades. A leg the
    board's own books already hold is journaled here too, under this
    bucket: the ticket reads this bucket first, and a pick is one row a
    bucket (ledger.log_most_likely's own rule)."""
    from . import ledger as L
    from .gameparlays import journal_rows
    rows = journal_rows(board.get("game_parlays") or {})
    if not rows:
        return 0
    return L.log_most_likely(conn, {"sport": sport, "date": board.get("date") or "",
                                    "games": board.get("games") or [], "most_likely": rows},
                             depth=None, category=PARLAY_LEG_CATEGORY, grade_label="Parlay leg")


def report_game_parlays(conn, recent: int = 12) -> dict:
    """Each game's parlays on the record (engine/gameparlays): the three-leg
    tickets and the scorer pairs, each apart, the way `report_twoleg`
    reports its pools — each game's set at its start (`mark_at_start`)."""
    from .gameparlays import SOURCES
    return report_twoleg(conn, recent, sources=SOURCES, where=AT_START)


def report_twoleg(conn, recent: int = 12, sources: dict | None = None, where: str = "") -> dict:
    """The Record page's two-leg parlays, each pool apart and never blended
    with the singles: graded, won, the notional units and ROI (one unit a
    ticket), the units really staked and what they returned, by kind and by
    league, and the newest graded tickets with their legs. ``sources`` is
    another {pool: source} to report the same way (each game's parlays), and
    ``where`` a condition on the rows (each game's set at its start)."""
    ensure_schema(conn)
    if sources is None:
        from .twoleg import SOURCES as sources
    out = {}
    for pool, source in sources.items():
        rows = conn.execute(f"SELECT * FROM parlays WHERE source=?{f' AND {where}' if where else ''} "
                            "ORDER BY date, id", (source,)).fetchall()
        graded = [r for r in rows if r["status"] in ("won", "lost")]

        def tally(rs):
            n = len(rs)
            net = sum(float(r["pnl_units"] or 0.0) for r in rs)
            st = sum(float(r["stake_units"] or 0.0) for r in rs)
            st_net = sum(float(r["pnl_units"] or 0.0) * float(r["stake_units"] or 0.0)
                         / float(r["notional_units"] or NOTIONAL_UNITS) for r in rs)
            return {"graded": n, "wins": sum(1 for r in rs if r["status"] == "won"),
                    "losses": sum(1 for r in rs if r["status"] == "lost"),
                    "net_units": round(net, 2), "roi": round(net / n, 4) if n else None,
                    "staked_units": round(st, 2), "staked_net": round(st_net, 2),
                    "staked_roi": round(st_net / st, 4) if st else None}
        block = tally(graded)
        block["open"] = sum(1 for r in rows if r["status"] == "open")
        block["z"] = _z([float(r["pnl_units"] or 0.0) for r in graded])
        block["by_kind"] = {k: tally([r for r in graded if r["parlay_type"] == k])
                            for k in sorted({r["parlay_type"] for r in graded})}
        block["by_sport"] = {k: tally([r for r in graded if r["sport"] == k])
                             for k in sorted({r["sport"] for r in graded})}
        news = []
        for r in sorted(graded, key=lambda r: (r["date"], r["id"]), reverse=True)[:recent]:
            legs = conn.execute("SELECT player, market, side, line, odds, status FROM parlay_legs "
                                "WHERE parlay_id=? ORDER BY leg_no", (r["id"],)).fetchall()
            news.append({"sport": r["sport"], "date": r["date"], "kind": r["parlay_type"],
                         "status": r["status"], "price_dec": r["assumed_dec"],
                         "pnl_units": r["pnl_units"], "staked": float(r["stake_units"] or 0) > 0,
                         "legs": [dict(x) for x in legs]})
        block["recent"] = news
        out[pool] = block
    return out


#: The newest tickets a league's record lists, each kind.
GAME_RECORD_RECENT = 8


def _leg_tally(legs: list) -> dict:
    ps = [float(l["p_final"]) for l in legs if l["p_final"] is not None]
    fs = [float(l["fair"]) for l in legs if l["fair"] is not None]
    return {"graded": len(legs), "won": sum(1 for l in legs if l["status"] == "won"),
            "chance": round(sum(ps) / len(ps), 3) if ps else None,
            "fair": round(sum(fs) / len(fs), 3) if fs else None}


def unique_legs(tickets: list, legs: list) -> list:
    """Each bet once among ``legs``: its game's day, the game, the player, the
    market, the side and the line, the first copy journaled (`legs_once`)."""
    meta = {t["id"]: (str(t["date"] or ""), str(t["grade"] or "")) for t in tickets}
    first: dict = {}
    for l in legs:
        k = (*meta.get(l["parlay_id"], ("", "")), str(l["player"] or "").strip().lower(),
             str(l["market"] or ""), str(l["side"] or "").upper(), l["line"])
        first.setdefault(k, l)
    return list(first.values())


def legs_once(tickets: list, legs: list) -> tuple[dict, dict]:
    """EACH LEG COUNTED ONCE, in all and by source (2026-11-16).

    A game's tickets share their legs, and every rebuild before the
    start can journal another ticket over the same ones, so a tally of legs
    per ticket counts one player's one bet up to a dozen times: the bets we
    were surest of (they ride the most tickets) weigh the most. Asking
    whether our chances hold is asking it of each bet once: its game's day,
    the game, the player, the market, the side and the line, the first copy
    journaled.

    ``by_pool`` splits them by the source the leg came from
    (engine/gameparlays.SOURCE_RANK: the Most Likely board, the Edge picks,
    any other priced prop); a leg journaled before the source was kept is
    "before". Each with the chance we gave and, where kept, the book's."""
    uniq = unique_legs(tickets, legs)
    pools: dict = {}
    for l in uniq:
        pools.setdefault(l["pool"] or "before", []).append(l)
    return _leg_tally(uniq), {k: _leg_tally(v) for k, v in sorted(pools.items())}


#: The tickets the game parlays' record counts: each game's set at its start
#: (`mark_at_start`, 2026-11-19).
AT_START = "at_start = 1"


def game_parlay_record(conn, recent: int = GAME_RECORD_RECENT) -> dict:
    """THE GAME REPORTS' PARLAYS, LEAGUE BY LEAGUE (2026-11-16). Ethan: "you did
    not put the 'parlays for this game' on the record page. We wanna see if the
    legs and the parlays we recommend are hitting so each sport needs to have a
    record of that on the record page."

    ``{league: {kind: block}}`` for each game's three-leg parlays ("three"), its
    two-leg ones ("two": its two strongest picks, GPWIN1) and its scorer pairs
    ("scorers") (engine/gameparlays.SOURCES), each block:

      * the tickets: graded, won, lost, units at one unit a ticket and ROI, open,
        our average chance on them (`modeled_joint`) and the tickets that lost
        by one leg (`one_away`);
      * the legs: graded, won, lost and our average chance on them (`p_final`),
        in all and by market (most legs first);
      * the newest graded tickets, each with its game and every leg's result.

    A leg is graded when it won or lost (a void or a push is neither). Every
    league in the journal, less the bench, as every figure on the page is.

    ONE SET A GAME (2026-11-19, `mark_at_start`): the tickets each game's
    report carried when it started, and no version the board replaced before
    then; ``not_counted`` says how many graded versions were left out."""
    ensure_schema(conn)
    from .gameparlays import SOURCES
    try:
        from .ledger import is_benched
    except Exception:                                        # noqa: BLE001
        def is_benched(_sp):
            return False
    out: dict = {}
    for kind, source in SOURCES.items():
        tickets = conn.execute(f"SELECT * FROM parlays WHERE source=? AND {AT_START} ORDER BY date, id",
                               (source,)).fetchall()
        before = dict(conn.execute(
            "SELECT lower(sport), count(*) FROM parlays WHERE source=? AND status IN ('won','lost') "
            "AND at_start IS NOT 1 GROUP BY lower(sport)", (source,)).fetchall())
        by_sport: dict = {}
        for t in tickets:
            sp = str(t["sport"] or "").lower()
            if sp and not is_benched(sp):
                by_sport.setdefault(sp, []).append(t)
        for sp, rows in by_sport.items():
            graded = [t for t in rows if t["status"] in ("won", "lost")]
            ids = [t["id"] for t in graded]
            legs = []
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                legs += conn.execute(
                    f"SELECT parlay_id, leg_no, player, market, side, line, odds, p_final, status, actual, pool, fair "
                    f"FROM parlay_legs WHERE parlay_id IN ({','.join('?' * len(chunk))}) ORDER BY parlay_id, leg_no",
                    chunk).fetchall()
            done = [l for l in legs if l["status"] in ("won", "lost")]
            net = sum(float(t["pnl_units"] or 0.0) for t in graded)
            joint = [float(t["modeled_joint"]) for t in graded if t["modeled_joint"] is not None]
            leg_p = [float(l["p_final"]) for l in done if l["p_final"] is not None]
            # By market, each bet once, as the legs' own line above them counts
            # them (18 November 2026: "109 of 180 legs" over "Rebounds 110 of
            # 202", the market rows counting every ticket a leg rode).
            markets: dict = {}
            for l in unique_legs(graded, done):
                m = markets.setdefault(str(l["market"] or ""), {"market": str(l["market"] or ""), "won": 0,
                                                                 "graded": 0, "_p": []})
                m["graded"] += 1
                m["won"] += l["status"] == "won"
                if l["p_final"] is not None:
                    m["_p"].append(float(l["p_final"]))
            mk = []
            for m in sorted(markets.values(), key=lambda m: (-m["graded"], m["market"])):
                ps = m.pop("_p")
                mk.append(dict(m, chance=round(sum(ps) / len(ps), 3) if ps else None))
            legs_of: dict = {}
            for l in legs:
                legs_of.setdefault(l["parlay_id"], []).append(
                    {"player": l["player"], "market": l["market"], "side": l["side"], "line": l["line"],
                     "odds": l["odds"], "status": l["status"],
                     **({"actual": l["actual"]} if l["actual"] is not None else {})})
            news = []
            for t in sorted(graded, key=lambda t: (t["date"], t["id"]), reverse=True)[:recent]:
                news.append({"date": t["date"], "game": t["grade"] or "", "status": t["status"],
                             "price_dec": t["assumed_dec"], "pnl_units": t["pnl_units"],
                             "chance": t["modeled_joint"], "legs": legs_of.get(t["id"], [])})
            wins = sum(1 for t in graded if t["status"] == "won")
            once, by_pool = legs_once(graded, done)
            out.setdefault(sp, {})[kind] = {
                "graded": len(graded), "wins": wins, "losses": len(graded) - wins,
                # The graded versions left out: replaced before their game
                # started, or from a game whose starting set was never kept.
                "not_counted": int(before.get(sp) or 0),
                "net_units": round(net, 2), "roi": round(net / len(graded), 4) if graded else None,
                "open": sum(1 for t in rows if t["status"] == "open"),
                "since": str(rows[0]["date"] or "") if rows else "",
                "chance": round(sum(joint) / len(joint), 3) if joint else None,
                "one_away": sum(1 for t in graded if t["status"] == "lost" and int(t["legs_lost"] or 0) == 1),
                "legs": {"graded": len(done), "won": sum(1 for l in done if l["status"] == "won"),
                         "lost": sum(1 for l in done if l["status"] == "lost"),
                         "chance": round(sum(leg_p) / len(leg_p), 3) if leg_p else None,
                         "once": once, "by_pool": by_pool},
                "markets": mk, "recent": news}
    # A league's three-leg tickets on paper (engine/parlayhold) say so on
    # their record: still graded here, posted nowhere until they hit 25%.
    # Its two-leg tickets the same, on their own hold (GPWIN1).
    try:
        from . import parlayhold
        for sp, kinds in out.items():
            for kind, legs in (("three", 3), ("two", 2)):
                h = parlayhold.held(sp, legs=legs)
                if h and kind in kinds:
                    kinds[kind]["paper"] = {"since": h.get("since"), "note": parlayhold.words(h)}
    except Exception:                                        # noqa: BLE001
        pass
    return out


# --- settling ---------------------------------------------------------------
def settle(conn) -> dict:
    """Grade every open ticket whose legs have all settled as singles.

    No grading happens here. Each leg's verdict is read off the singles
    journal, which means the parlay record can never disagree with the
    record its own legs are in, and every guard protecting the singles
    settler protects this too.
    """
    ensure_schema(conn)
    from .ledger import _bet_clv
    # A leg with no row in any book gets its paper row first; the singles
    # settle grades it off the box on its next pass (`journal_missing_legs`).
    journal_missing_legs(conn)
    graded, waiting = [], 0
    for p in conn.execute("SELECT * FROM parlays WHERE status='open' "
                          "ORDER BY date, id").fetchall():
        legs = conn.execute("SELECT * FROM parlay_legs WHERE parlay_id=? "
                            "ORDER BY leg_no", (p["id"],)).fetchall()
        if not legs:
            continue
        resolved, pending, missing = [], False, []
        for leg in legs:
            b, verdict = _resolve_leg(conn, p, leg)
            if b is None:
                missing.append(leg)
                continue
            if b["status"] == "open":
                pending = True
                break
            resolved.append((leg, verdict))
        if pending or (missing and not _voids_missing(p, resolved)):
            waiting += 1
            continue
        resolved += [(leg, _no_row_verdict(leg)) for leg in missing]

        for leg, b in resolved:
            conn.execute(
                "UPDATE parlay_legs SET status=?, actual=?, closing_line=?, "
                "clv=? WHERE id=?",
                (b["status"], b["actual"], b["closing_line"],
                 _bet_clv(b), leg["id"]))

        graded.append(_grade_ticket(conn, p, resolved))
    conn.commit()
    return {"settled": len(graded), "waiting": waiting, "tickets": graded}


def resettle(conn) -> dict:
    """Re-audit SETTLED tickets against their legs' CURRENT singles verdicts.

    The settle above promises "the parlay record can never disagree with the
    record its own legs are in" — and then only ever reads OPEN tickets, so
    the promise held exactly until a settled single moved. Singles move for
    two legitimate reasons: ``resettle_mismatches`` re-grades one that was
    settled off partial data (the premature-settle repairs), and
    ``--repair-premature`` can reopen one outright. A ticket killed by a leg
    that later healed to a win stayed lost forever, wearing a
    LEG_ONE_KILLED_IT code about a loss that no longer exists.

    Mirrors the singles repair pass exactly: legs re-read, tickets whose leg
    verdicts moved re-graded in place, a ticket with a leg back OPEN
    reopened so the ordinary settle can take it again. Idempotent; a clean
    table is a no-op. No bankroll to restate — tickets are notional (§13).
    """
    ensure_schema(conn)
    from .ledger import _bet_clv
    fixed, reopened = [], 0
    for p in conn.execute("SELECT * FROM parlays WHERE status IN "
                          "('won','lost','void') ORDER BY date, id").fetchall():
        legs = conn.execute("SELECT * FROM parlay_legs WHERE parlay_id=? "
                            "ORDER BY leg_no", (p["id"],)).fetchall()
        if not legs:
            continue
        resolved, back_open, missing = [], False, []
        for leg in legs:
            b, verdict = _resolve_leg(conn, p, leg)
            if b is None:
                missing.append(leg)
                continue
            if b["status"] == "open":
                back_open = True
                break
            resolved.append((leg, verdict))
        # The settle's own rule for a leg with no row (`_no_row_verdict`), so the
        # two never disagree: void beside legs that graded, open on its own.
        back_open = back_open or bool(missing and not _voids_missing(p, resolved))
        if not back_open:
            resolved += [(leg, _no_row_verdict(leg)) for leg in missing]
        if back_open:
            # A leg was reopened (repair-premature). The ticket's verdict
            # rests on a bet that no longer has one — reopen it too and let
            # the ordinary settle grade it when the leg really lands.
            conn.execute(
                "UPDATE parlays SET status='open', pnl_units=NULL, "
                "legs_won=NULL, legs_lost=NULL, legs_void=NULL, "
                "singles_pnl_units=NULL, loss_code=NULL, loss_codes=NULL, "
                "settled_ts=NULL WHERE id=?", (p["id"],))
            conn.execute("UPDATE parlay_legs SET status='open', actual=NULL, "
                         "closing_line=NULL, clv=NULL WHERE parlay_id=?",
                         (p["id"],))
            reopened += 1
            continue
        moved = [leg for leg, b in resolved
                 if (leg["status"] or "open") != b["status"]]
        if not moved:
            continue
        for leg, b in resolved:
            conn.execute(
                "UPDATE parlay_legs SET status=?, actual=?, closing_line=?, "
                "clv=? WHERE id=?",
                (b["status"], b["actual"], b["closing_line"],
                 _bet_clv(b), leg["id"]))
        was = p["status"]
        out = _grade_ticket(conn, p, resolved)
        if out["status"] != was:
            fixed.append({**out, "was": was})
    conn.commit()
    return {"fixed": fixed, "reopened": reopened}


#: The singles books a two-leg ticket's legs were taken from (engine/twoleg),
#: and a game parlay's (engine/gameparlays): its own paper bucket first,
#: which holds every leg it posted.
TWO_LEG_CATS = {"two_edge": ("main", "paper"), "two_likely": ("likely", "likely_live", "board"),
                "game_three": (PARLAY_LEG_CATEGORY,), "game_two": (PARLAY_LEG_CATEGORY,),
                "game_td": (PARLAY_LEG_CATEGORY,)}


def _matching_bet(conn, p, leg):
    """The singles-journal row this leg was taken from.

    Matched on the same four fields that identify a bet in the singles
    journal's own unique key, minus the category — a leg is always a 'main'
    pick, since §14 requires it to have earned the board on its own.

    A TWO-LEG TICKET'S LEGS (engine/twoleg, 2026-10-31) come from its own
    pool's books — an Edge pick or a Most Likely pick — and are matched on
    the side and line too where they agree, since one player's market can
    sit on both boards at different numbers.
    """
    cats = TWO_LEG_CATS.get(p["source"] if "source" in p.keys() else "")
    if not cats:
        return conn.execute(
            "SELECT * FROM bets WHERE sport=? AND date=? AND player=? AND market=?"
            " AND category='main'",
            (p["sport"], p["date"], leg["player"], leg["market"])).fetchone()
    marks = ",".join("?" * len(cats))
    base = (f"SELECT * FROM bets WHERE sport=? AND date=? AND player=? AND market=? "
            f"AND category IN ({marks})")
    args = [p["sport"], p["date"], leg["player"], leg["market"], *cats]
    exact = conn.execute(base + " AND UPPER(COALESCE(side,''))=? AND ABS(COALESCE(line,0)-?)<1e-6 "
                         "ORDER BY id", args + [str(leg["side"] or "").upper(), float(leg["line"] or 0)]).fetchone()
    return exact or conn.execute(base + " ORDER BY id", args).fetchone()


#: Which way each side wants the number: up for an over (and a scorer's
#: "yes", line 0.5), down for an under.
_UP_SIDES, _DOWN_SIDES = ("OVER", "YES"), ("UNDER", "NO")


def _no_row_verdict(leg) -> dict:
    """A LEG WITH NO ROW TO GRADE FROM (STUCKLEGS1, 2026-11-17). A ticket's legs
    are journaled on paper first (`journal_game_parlay_legs`), and the paper
    journal refuses a game already under way; a board built just before a
    start and journaled just after it wrote its tickets and not their legs,
    and those tickets waited on the box score for good (Ethan's How our
    reports did, 17 November: nine of the Magic at Celtics tickets, six to
    nineteen of every NFL game of the 15th, two days on). A leg with no row
    never gets one. So once every other leg of its ticket has graded (the
    game is over), it voids, as a book voids a leg it cannot settle, and the
    ticket is graded on the rest; a ticket none of whose legs has a row
    waits, as nothing says its game is over. `journal_built_boards` journals
    no new ticket without its legs' rows (`_with_leg_rows`)."""
    return {"status": "void", "actual": None, "closing_line": None, "line": leg["line"],
            "side": leg["side"], "odds": leg["odds"]}


def _game_line_bet(conn, p, leg):
    """A GAME LINE ON A GAME PARLAY (STUCKLEGS1). The first three-leg tickets
    (14 to 16 November) could take a club to win, and a game leg is never
    journaled on paper (gameparlays.journal_rows passes it by: it grades on
    the game's own path). Its verdict is the game's, off the same bet in any
    book: the journal writes a moneyline as the club at OVER 0.5
    (ledger.game_row_keys). Graded on nothing, it voided, and a ticket whose
    club lost could read won (the Ravens' on 16 November). A moneyline only:
    the only game line a ticket ever carried. The settled row first."""
    if str(leg["market"] or "").lower() != "moneyline":
        return None
    src = p["source"] if "source" in p.keys() else None
    if src not in NO_ROW_VOID_SOURCES:
        return None
    team = (leg["team"] if "team" in leg.keys() else None) or str(leg["player"] or "").replace(" ML", "").strip()
    if not team:
        return None
    return conn.execute("SELECT * FROM bets WHERE sport=? AND date=? AND player=? AND market='moneyline' "
                        "ORDER BY CASE WHEN status='open' THEN 1 ELSE 0 END, id",
                        (p["sport"], p["date"], team)).fetchone()


def _other_book_bet(conn, p, leg):
    """THE SAME PROP IN ANOTHER BOOK, SETTLED (STUCKLEGS1). A game parlay's leg
    grades from its own paper row; where that row was never written (the paper
    journal refused a game already under way) or is still open, the player's
    same market that day in any of our books, settled, holds the number the
    box gave (`actual`), and `_own_verdict` grades the leg on its own side and
    line from it, as it does any row taken at another line. The row at the
    leg's own side and line first. Never a book graded on another path
    (ledger.GRADED_ELSEWHERE: exchange tickers, fights), never a game line
    (`_game_line_bet` reads those as they stand)."""
    src = p["source"] if "source" in p.keys() else None
    if src not in NO_ROW_VOID_SOURCES or str(leg["market"] or "").lower() == "moneyline":
        return None
    from .ledger import GRADED_ELSEWHERE
    shut = (PARLAY_LEG_CATEGORY, *GRADED_ELSEWHERE)
    marks = ",".join("?" * len(shut))
    return conn.execute(
        f"SELECT * FROM bets WHERE sport=? AND date=? AND player=? AND market=? AND status IN ('won','lost','push','void') "
        f"AND COALESCE(category,'') NOT IN ({marks}) "
        f"ORDER BY CASE WHEN UPPER(COALESCE(side,''))=? AND ABS(COALESCE(line,0)-?)<1e-6 THEN 0 ELSE 1 END, id",
        (p["sport"], p["date"], leg["player"], leg["market"], *shut,
         str(leg["side"] or "").upper(), float(leg["line"] or 0))).fetchone()


def _resolve_leg(conn, p, leg) -> tuple:
    """(the row a leg grades from, its verdict): its own paper row (`_matching_bet`,
    graded on its own side and line, `_own_verdict`); else, for a game parlay, a
    game line's own bet in any book (`_game_line_bet`, that bet's verdict as it
    stands) or the same prop settled in another book (`_other_book_bet`, graded
    on the leg's own line); (None, None) with none of them (`_no_row_verdict`).
    A paper row still open waits unless another book has settled the same prop.
    The verdict is None while the row is open."""
    b = _matching_bet(conn, p, leg)
    if b is not None and b["status"] != "open":
        return b, _own_verdict(leg, b)
    if b is None:
        g = _game_line_bet(conn, p, leg)
        if g is not None:
            return g, ({k: g[k] for k in g.keys()} if g["status"] != "open" else None)
    o = _other_book_bet(conn, p, leg)
    if o is not None:
        return o, _own_verdict(leg, o)
    return b, None


def journal_missing_legs(conn, days: int = 21, today=None) -> int:
    """A GAME PARLAY'S LEG WITH NO ROW IN ANY BOOK GETS ITS PAPER ROW (STUCKLEGS1).

    A ticket's legs are journaled on paper before it (`journal_game_parlay_legs`),
    and the paper journal refuses a game already under way, so a board built just
    before a start and journaled just after it wrote tickets whose legs had no
    row. `_no_row_verdict` voided those beside the graded legs, and a leg on a
    player who played was voided with them: six Magic at Celtics tickets of 16
    November went void on Derrick White's assists and Jalen Suggs's rebounds,
    both of whom played. Each such leg now gets the paper row it should have had,
    on the ticket's own day and stamped with the ticket's own journal time, and
    the singles settle grades it off the box like any other (a player who did not
    play voids by the no-show rules). Open tickets and those graded with a void
    leg in the last ``days``; a game line never (it grades on the game,
    `_game_line_bet`); a football week's ticket only where its other legs' rows
    give the day. Idempotent: returns the rows written."""
    ensure_schema(conn)
    from .ledger import GAME_MARKETS, GRADED_ELSEWHERE, _ISO_DAY_RE
    since = ((today or datetime.date.today()) - datetime.timedelta(days=days)).isoformat()
    marks = ",".join("?" * len(NO_ROW_VOID_SOURCES))
    shut = ",".join("?" * len(GRADED_ELSEWHERE))
    added = 0
    for p in conn.execute(f"SELECT * FROM parlays WHERE source IN ({marks}) AND COALESCE(ts,'') >= ? "
                          f"AND (status='open' OR COALESCE(legs_void,0) > 0) ORDER BY id",
                          (*NO_ROW_VOID_SOURCES, since)).fetchall():
        lost, seen = [], []
        for leg in conn.execute("SELECT * FROM parlay_legs WHERE parlay_id=? ORDER BY leg_no",
                                (p["id"],)).fetchall():
            if str(leg["market"] or "").lower() in GAME_MARKETS:
                continue
            rows = conn.execute(f"SELECT game_day FROM bets WHERE sport=? AND date=? AND player=? AND market=? "
                                f"AND COALESCE(category,'') NOT IN ({shut})",
                                (p["sport"], p["date"], leg["player"], leg["market"], *GRADED_ELSEWHERE)).fetchall()
            if rows:
                seen += [str(r["game_day"]) for r in rows if r["game_day"]]
            else:
                lost.append(leg)
        if not lost:
            continue
        day = str(p["date"] or "")
        if not _ISO_DAY_RE.match(day):
            day = min(d for d in seen if _ISO_DAY_RE.match(d)) if any(_ISO_DAY_RE.match(d) for d in seen) else ""
        if not day:
            continue
        for leg in lost:
            added += conn.execute(
                "INSERT OR IGNORE INTO bets (game_day, ts, sport, date, player, market, side, line, book, odds, "
                "hit_prob, grade, stake_units, stake_dollars, status, category, team) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?, 'Parlay leg', 0.1, 0, 'open', ?, ?)",
                (day, p["ts"], p["sport"], p["date"], leg["player"], leg["market"], str(leg["side"] or "").upper(),
                 leg["line"], leg["book"] or "", leg["odds"], leg["p_final"], PARLAY_LEG_CATEGORY,
                 leg["team"])).rowcount
    if added:
        conn.commit()
    return added


def waiting(conn, days: int = 2, today=None) -> list[dict]:
    """GAME PARLAYS STILL OPEN `days` AFTER THEIR DATE, AND WHAT EACH LEG WAITS ON
    (STUCKLEGS1). Read-only: each leg as the next settle reads it (`_resolve_leg`):
    graded (and from which book), open (its row not graded yet), or no row in any
    book. `python3 -m engine.parlayledger waiting`."""
    ensure_schema(conn)
    cut = ((today or datetime.date.today()) - datetime.timedelta(days=days)).isoformat()
    marks = ",".join("?" * len(NO_ROW_VOID_SOURCES))
    out = []
    for p in conn.execute(f"SELECT * FROM parlays WHERE status='open' AND source IN ({marks}) "
                          f"ORDER BY date, id", NO_ROW_VOID_SOURCES).fetchall():
        legs, seen = [], []
        for leg in conn.execute("SELECT * FROM parlay_legs WHERE parlay_id=? ORDER BY leg_no",
                                (p["id"],)).fetchall():
            own = _matching_bet(conn, p, leg)
            row, verdict = _resolve_leg(conn, p, leg)
            for r in (own, row):
                if r is not None and "game_day" in r.keys() and r["game_day"]:
                    seen.append(str(r["game_day"])[:10])
            if verdict is not None:
                mine = own is not None and own["id"] == row["id"]
                state = f"graded: {verdict['status']}" + ("" if mine else f" (from the {row['category']} book)")
            elif row is not None:
                state = f"open: its row #{row['id']} ({row['category']}, {row['date']}) has not graded"
            else:
                state = "no row: nothing in any book to grade it from"
            legs.append({"player": leg["player"], "market": leg["market"], "side": leg["side"] or "",
                         "line": leg["line"], "state": state})
        # The day it was played: a calendar date as filed; a football week's
        # label ("2026-W11") by its legs' rows' game day, else the day journaled.
        day = str(p["date"] or "")
        if "-W" in day or len(day) != 10:
            day = min(seen) if seen else str(p["ts"] or "")[:10]
        if day and day <= cut:
            out.append({"id": p["id"], "sport": p["sport"], "date": p["date"], "day": day,
                        "game": p["grade"] or "", "source": p["source"], "legs": legs})
    return out


#: The tickets whose legs ride on their own paper bucket (engine/gameparlays): only
#: there is a leg with no row a journaling gap. A Parlay Zone leg earned the board
#: as a single, so a missing single is an error upstream, and its ticket waits.
NO_ROW_VOID_SOURCES = ("game_three", "game_two", "game_td")


def _voids_missing(p, resolved: list) -> bool:
    """Whether a ticket's legs with no row void (`_no_row_verdict`): a game
    parlay's, and only beside a leg that has graded."""
    source = p["source"] if "source" in p.keys() else None
    return bool(resolved) and source in NO_ROW_VOID_SOURCES


def _has_leg_row(conn, sport: str, date: str, leg: dict) -> bool:
    """Whether the paper bucket holds a row this leg grades from (`_matching_bet`'s own
    match: the day, the player and the market)."""
    return conn.execute("SELECT 1 FROM bets WHERE sport=? AND date=? AND player=? AND market=? AND category=? "
                        "LIMIT 1", (sport, date, leg.get("player"), leg.get("market"),
                                    PARLAY_LEG_CATEGORY)).fetchone() is not None


def _with_leg_rows(conn, gp: dict, sport: str, date: str) -> tuple[dict, int]:
    """The board's game parlays with only the tickets every leg of which has a row on
    paper to grade from (`_no_row_verdict`), and how many were left out."""
    out, dropped = dict(gp), 0
    games = []
    for x in gp.get("games") or []:
        if not isinstance(x, dict):
            continue
        y = dict(x)
        for k in ("twos", "paper_twos", "threes", "paper_threes", "scorers"):
            keep = [t for t in x.get(k) or [] if all(_has_leg_row(conn, sport, date, l) for l in t.get("legs") or [])]
            dropped += len(x.get(k) or []) - len(keep)
            if k in x:
                y[k] = keep
        games.append(y)
    out["games"] = games
    return out, dropped


def _own_verdict(leg, b) -> dict:
    """THE LEG'S OWN VERDICT, on its own side and line (2026-11-16).

    The singles journal keys a pick without its line (ledger.PICK_KEY_SQL:
    the first price journaled is the claim), so one player's "catches over
    1.5" on one ticket and "over 3.5" on a rebuild's are one row there, the
    first; and `_matching_bet` falls back to the first row of the player's
    market when no row has the leg's side and line. Until today that row's
    verdict was the leg's, whatever line it was taken at: an over 3.5 on a
    night of two catches graded won off the over 1.5's row.

    Now: the row's own verdict when it is this leg's bet (same side, same
    line); otherwise the leg is graded on its own line from the number the
    row settled on (`actual`, the player's real line in the box), a push
    reading void; a void row (he did not play) voids the leg; and a leg
    with no number to grade it on is voided, not given another bet's
    verdict. Never the other row's close or price: those are its line's."""
    row = {k: b[k] for k in b.keys()} if hasattr(b, "keys") else dict(b)

    def _num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    # A side or line either record left blank (the oldest tickets and
    # singles carry none) is the other's: those legs were always the row's.
    row_side, row_line = str(row.get("side") or "").upper(), _num(row.get("line"))
    side = str(leg["side"] or "").upper() or row_side
    line = _num(leg["line"])
    line = row_line if line is None else line
    same = ((not row_side or row_side == side)
            and (row_line is None or (line is not None and abs(row_line - line) < 1e-6)))
    if same:
        return row
    own = {**row, "side": side or row.get("side"), "line": line, "odds": leg["odds"] or row.get("odds"),
           "closing_line": None}
    status, actual = row.get("status"), row.get("actual")
    if status not in ("won", "lost", "push"):
        return {**own, "status": "void"}
    if actual is None or line is None or side not in _UP_SIDES + _DOWN_SIDES:
        return {**own, "status": "void", "actual": actual}
    a = float(actual)
    if abs(a - line) < 1e-9:
        verdict = "void"
    elif side in _UP_SIDES:
        verdict = "won" if a > line else "lost"
    else:
        verdict = "won" if a < line else "lost"
    return {**own, "status": verdict}


def _grade_ticket(conn, p, resolved: list) -> dict:
    """Settle one ticket from its legs' verdicts.

    Void legs drop out and the ticket reprices on what is left, which is
    what a book does. Below two legs there is no parlay left to grade, so
    the ticket voids rather than silently becoming a single.
    """
    from .odds import american_to_decimal
    won = [b for _, b in resolved if b["status"] == "won"]
    lost = [b for _, b in resolved if b["status"] == "lost"]
    void = [b for _, b in resolved if b["status"] not in ("won", "lost")]
    live = [b for _, b in resolved if b["status"] in ("won", "lost")]

    # Flat-stake P&L of the same legs bet separately — §11.1's TAX_TOO_HIGH
    # needs it, and it is the single most useful column in the table: it
    # answers "would we have been better off not doing this" with a number.
    singles_pnl = 0.0
    for b in live:
        dec = american_to_decimal(b["odds"] or -110)
        singles_pnl += (dec - 1.0) if b["status"] == "won" else -1.0

    notional = float(p["notional_units"] or NOTIONAL_UNITS)
    if len(live) < 2:
        status, pnl, codes = "void", 0.0, []
    elif lost:
        status, pnl = "lost", -notional
        codes = _loss_codes(conn, p, won, lost, singles_pnl)
    else:
        # A REAL QUOTE BEATS AN ASSUMPTION, ALWAYS. `assumed_dec` is the
        # naive product less the mid-point of a tax band the doc GUESSES
        # at — 15 to 30 points, and which end you are on is the whole
        # difference between a good ticket and a dead one. Once somebody
        # has recorded what a book actually offered, grading against the
        # guess would be throwing away the only real number on the row.
        price = float(p["quoted_dec"] or p["assumed_dec"] or 0.0)
        if void:
            # Reprice on the surviving legs at the same tax. A quoted
            # ticket keeps its OWN measured tax rather than the assumed
            # band — the book already told us what it charges on these
            # legs, and a leg voiding does not change that.
            naive = math.prod(american_to_decimal(b["odds"] or -110)
                              for b in live)
            tax = float(p["correlation_tax"] or 0.0)
            if p["quoted_dec"] and p["naive_product_dec"]:
                tax = 1.0 - (float(p["quoted_dec"])
                             / float(p["naive_product_dec"]))
            price = naive * (1.0 - tax)
        status, pnl, codes = "won", notional * (price - 1.0), []

    conn.execute(
        "UPDATE parlays SET status=?, pnl_units=?, legs_won=?, legs_lost=?, "
        "legs_void=?, singles_pnl_units=?, loss_code=?, loss_codes=?, "
        "settled_ts=? WHERE id=?",
        (status, round(pnl, 4), len(won), len(lost), len(void),
         round(singles_pnl, 4), codes[0] if codes else None,
         json.dumps(codes) if codes else None,
         datetime.datetime.now().isoformat(timespec="seconds"), p["id"]))
    return {"id": p["id"], "sport": p["sport"], "date": p["date"],
            "status": status, "pnl_units": round(pnl, 4),
            "legs_won": len(won), "legs_lost": len(lost),
            "singles_pnl_units": round(singles_pnl, 4),
            "loss_codes": codes}


def _loss_codes(conn, p, won, lost, singles_pnl: float) -> list[str]:
    """§11.1's post-mortem codes, and only the ones actually computable.

    CLASH_MISSED is deliberately never assigned. Deciding that a Type 2/3/4
    clash slipped through is a judgement about the mechanism, not something
    the outcome can tell you — a ticket can lose with no clash at all and
    win with one. Auto-stamping it would fill the column with a conclusion
    nobody reached.
    """
    codes = []
    if len(lost) == 1 and won:
        codes.append("LEG_ONE_KILLED_IT")
    if singles_pnl > 0:
        codes.append("TAX_TOO_HIGH")
    return codes


#: CORRELATION_ERROR IS NOT ASSIGNED PER TICKET, and was until 2026-08-23.
#:
#: The old rule was `won and lost and the ticket priced rho +` — which,
#: on a two-leg ticket, is the definition of "exactly one leg missed".
#: The first real record made that visible: LEG_ONE_KILLED_IT 10,
#: CORRELATION_ERROR 10, the same ten tickets counted twice under two
#: names, one of which reads as a diagnosis. And a split is the MOST
#: LIKELY single outcome even when a positive correlation is priced
#: perfectly — rho +0.38 does not mean the legs land together, it means
#: they land together slightly more often than chance.
#:
#: This is the argument CLASH_MISSED already carries three lines up: a
#: judgement about the mechanism is not something one outcome can tell
#: you. Whether the correlation is wrong is an AGGREGATE question, and
#: `calibration()` answers it properly — observed ticket wins against the
#: modeled joint, and against the independent joint, over every ticket
#: that claimed the legs move together.


def calibration(conn) -> dict:
    """Did the legs hit at the probability we gave them, and did the
    tickets hit at the joint we priced?

    THE ONE DIAGNOSTIC THAT SEPARATES THE TWO WAYS A PARLAY MODEL CAN BE
    WRONG, and until 2026-08-23 nothing computed it — so a record could
    only ever say "we lost", never which half lost it.

      THE MARGINALS. Every leg carries `p_final`, the prop model's own
      probability. Sum them and you have how many legs SHOULD have won.
      If the legs come in under that, the parlay is downstream of a
      miscalibrated prop model and no amount of correlation work touches
      it — the singles board is making the same mistake.

      THE JOINT. Every ticket carries `modeled_joint` (our number, with
      the correlation in it) and `independent_joint` (the same legs
      multiplied as if unrelated). If the legs hit at their p_final but
      the TICKETS come in under the modeled joint, the marginals are
      fine and the correlation is what is wrong.

    And the third case, which the numbers can distinguish and a person
    cannot: if the observed rate sits at or below the INDEPENDENT joint
    while we priced a positive correlation, then the legs we said move
    together do not, and the prior has the wrong sign rather than the
    wrong size.

    z is a standard normal on a sum of independent Bernoullis — the legs
    inside one ticket are not independent of each other, so the ticket-level
    z is the honest one and the leg-level z is slightly optimistic about
    its own error bars. Reported anyway because the SIGN and the SIZE of
    the gap are what matter here, not the last decimal of significance.
    """
    ensure_schema(conn)

    def _z(actual: int, ps: list) -> float | None:
        var = sum(p * (1.0 - p) for p in ps)
        if var <= 0:
            return None
        return round((actual - sum(ps)) / math.sqrt(var), 2)

    legs = conn.execute(
        "SELECT l.p_final AS p, l.status AS st FROM parlay_legs l "
        "JOIN parlays p ON p.id = l.parlay_id "
        "WHERE l.p_final IS NOT NULL AND l.status IN ('won','lost') "
        "AND p.status IN ('won','lost')").fetchall()
    lp = [float(r["p"]) for r in legs]
    lw = sum(1 for r in legs if r["st"] == "won")

    tick = conn.execute(
        "SELECT modeled_joint AS m, independent_joint AS i, status AS st "
        "FROM parlays WHERE status IN ('won','lost') "
        "AND modeled_joint IS NOT NULL").fetchall()
    tm = [float(r["m"]) for r in tick]
    ti = [float(r["i"]) for r in tick if r["i"] is not None]
    tw = sum(1 for r in tick if r["st"] == "won")

    # Only the tickets where we actually claimed the legs move together.
    pos = [r for r in tick
           if r["i"] is not None and float(r["m"]) > float(r["i"])]
    pm = [float(r["m"]) for r in pos]
    pi = [float(r["i"]) for r in pos]
    pw = sum(1 for r in pos if r["st"] == "won")

    return {
        "legs": {"n": len(lp), "won": lw,
                 "expected": round(sum(lp), 2),
                 "z": _z(lw, lp)},
        "tickets": {"n": len(tm), "won": tw,
                    "expected": round(sum(tm), 2),
                    "expected_independent": round(sum(ti), 2) if ti else None,
                    "z": _z(tw, tm)},
        "positive_rho": {"n": len(pm), "won": pw,
                         "expected": round(sum(pm), 2),
                         "expected_independent": round(sum(pi), 2),
                         "z": _z(pw, pm),
                         "z_independent": _z(pw, pi)},
    }


# --- reporting --------------------------------------------------------------
def report(conn, source: str = "edge") -> dict:
    """The Record page's parlay bucket. Never blended with singles (§13),
    and never blended ACROSS BOARDS either — `source` picks which screen's
    record is being read. See `ensure_schema` for why the column exists.

    COALESCE'd rather than compared straight, because every row written
    before the column existed carries NULL and all of them are edge."""
    ensure_schema(conn)
    rows = conn.execute("SELECT * FROM parlays WHERE status IN "
                        "('won','lost','void') AND COALESCE(source,'edge')=? "
                        "ORDER BY date, id", (source,)).fetchall()
    graded = [r for r in rows if r["status"] in ("won", "lost")]
    pnl = [float(r["pnl_units"] or 0.0) for r in graded]
    staked = sum(float(r["notional_units"] or NOTIONAL_UNITS) for r in graded)
    net = sum(pnl)
    roi = (net / staked) if staked else 0.0
    clv = _leg_clv(conn)
    # §13'S BAR IS ABOUT TICKETS THIS MODULE WOULD STAKE, and until now it
    # was measured over every graded row — which includes rank 1 off every
    # slate the screen REFUSED. That let refusals count toward the hundred
    # and let their P&L set the ROI condition, so the module could have
    # been held back by the losses of bets it declined to make, or, worse,
    # promoted on the strength of grading its own rejects. Promotion is
    # judged on the recommended rows only; the blended numbers stay in the
    # report beside them, because hiding them would be the opposite
    # mistake.
    rec_rows = [r for r in graded if r["qualified"]]
    rec_pnl = [float(r["pnl_units"] or 0.0) for r in rec_rows]
    rec_staked = sum(float(r["notional_units"] or NOTIONAL_UNITS)
                     for r in rec_rows)
    rec_roi = (sum(rec_pnl) / rec_staked) if rec_staked else 0.0
    rec_z = _z(rec_pnl)
    out = {
        "graded": len(graded),
        "open": conn.execute("SELECT COUNT(*) FROM parlays WHERE "
                             "status='open'").fetchone()[0],
        "voided": sum(1 for r in rows if r["status"] == "void"),
        "wins": sum(1 for r in graded if r["status"] == "won"),
        "losses": sum(1 for r in graded if r["status"] == "lost"),
        "net_units": round(net, 2),
        "roi": round(roi, 4),
        "z": _z(pnl),
        "avg_leg_clv": clv["avg"],
        "leg_clv_n": clv["n"],
        # §13's bar, reported as three conditions rather than one verdict —
        # a module that fails promotion should say WHICH test it failed.
        "probation": True,
        "promotion": {
            "tickets_required": PROBATION_TICKETS,
            # Recommended tickets only — see the note where rec_rows is
            # built. `tickets_graded_all` is the blended count, kept so a
            # reader can see the difference rather than infer it.
            "tickets_have": len(rec_rows),
            "tickets_graded_all": len(graded),
            "roi_positive": rec_roi > 0,
            "roi": round(rec_roi, 4),
            "z": rec_z,
            "clv_non_negative": (clv["avg"] is not None and clv["avg"] >= 0),
            "z_clears": (rec_z or 0.0) >= PROMOTION_Z,
            "z_required": PROMOTION_Z,
            "note": ("Parlays are graded, never staked, until 100 graded "
                     "tickets clear positive flat-stake ROI, aggregate "
                     "leg-level CLV at or above zero, and z of at least 2 — "
                     "and the singles board clears its own bar first. Only "
                     "tickets the screen recommended count toward that; the "
                     "constructions it refused are graded too, to test the "
                     "no, and are reported apart. Everything here is a "
                     "tracked observation worth nothing."),
        },
        "calibration": calibration(conn),
        # THE SPLIT THAT WAS MISSING. log_board journals rank 1 from every
        # slate whether or not the screen qualified it, so a record read
        # whole is mostly constructions the model DECLINED. Reporting
        # those together buries the only rows that are the model's
        # recommendation under the ones that are its rejects.
        "by_qualified": _by_qualified(conn),
        "by_grade": _split(conn, "grade"),
        "by_sport": _split(conn, "sport"),
        "by_type": _split(conn, "parlay_type"),
        "loss_codes": _loss_code_tally(conn),
        "tax_by_book": _tax_by_book(conn),
        "singles_comparison": _singles_comparison(graded),
        # THE SAME QUESTION, ASKED OF THE RECOMMENDATIONS ONLY. "Singles
        # were better, the structure is costing money" is a verdict on
        # the SCREEN, and answering it over rows the screen declined
        # convicts it of somebody else's tickets.
        "singles_comparison_recommended": _singles_comparison(
            [r for r in graded if r["qualified"]]),
        "recent": _recent(conn),
    }
    return out


def _by_qualified(conn) -> dict:
    """Plays and rejects, counted apart.

    `qualified` is the screen's verdict on the ticket; `was_play` is
    §10.2's one-per-slate winner among the qualified. A ticket that is
    neither is a construction the page showed to say what tonight
    offered — the Zone ranks even when nothing clears — and grading it
    beside a recommendation measures the wrong thing.

    `recommended` is the two yes-buckets added up, and it is the one a
    reader actually wants: it is every ticket the screen put its name to.
    It is computed HERE rather than by adding two ROIs on the page,
    because ROIs do not add — they have to be re-divided by the notional
    the two buckets staked between them, and the page not having that
    number is how a weighted average becomes a mean of two percentages.
    """
    out = {}
    for label, where in (("play", "was_play=1"),
                         ("qualified", "qualified=1 AND was_play=0"),
                         ("recommended", "qualified=1"),
                         ("not_qualified", "qualified=0")):
        r = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(status='won'),0) w, "
            "COALESCE(SUM(pnl_units),0) u, COALESCE(SUM(notional_units),0) s "
            f"FROM parlays WHERE status IN ('won','lost') AND {where}"
        ).fetchone()
        out[label] = {"graded": r["n"], "wins": r["w"],
                      "losses": r["n"] - r["w"],
                      "net_units": round(r["u"], 2),
                      "staked_units": round(r["s"], 2),
                      "roi": round(r["u"] / r["s"], 4) if r["s"] else 0.0}
    return out


def _z(pnl: list[float]) -> float | None:
    """t-statistic on per-ticket flat-stake P&L — §13's third condition.

    Needs at least two tickets and some variance; a run of identical results
    has no standard error and reporting an infinite z would be worse than
    reporting none.
    """
    n = len(pnl)
    if n < 2:
        return None
    mean = sum(pnl) / n
    var = sum((x - mean) ** 2 for x in pnl) / (n - 1)
    if var <= 0:
        return None
    return round(mean / math.sqrt(var / n), 2)


def _leg_clv(conn) -> dict:
    """Aggregate leg-level CLV — §11: the only honest parlay CLV.

    Averaged across legs rather than tickets on purpose. A ticket's CLV is
    not a single number, and inventing one by summing line moves across
    different markets would add yards to strikeouts.
    """
    rows = conn.execute(
        "SELECT l.clv FROM parlay_legs l JOIN parlays p ON p.id=l.parlay_id "
        "WHERE l.clv IS NOT NULL AND p.status IN ('won','lost')").fetchall()
    vals = [float(r[0]) for r in rows]
    return {"avg": round(sum(vals) / len(vals), 3) if vals else None,
            "n": len(vals)}


def _split(conn, column: str) -> list[dict]:
    """Graded record broken out by one column, best ROI first."""
    rows = conn.execute(
        f"SELECT {column} AS k, COUNT(*) n, "
        "COALESCE(SUM(status='won'), 0) w, "
        "COALESCE(SUM(pnl_units), 0) u, "
        "COALESCE(SUM(notional_units), 0) s "
        f"FROM parlays WHERE status IN ('won','lost') GROUP BY {column}"
    ).fetchall()
    out = [{"key": r["k"] or "?", "graded": r["n"], "wins": r["w"],
            "net_units": round(r["u"], 2),
            "roi": round(r["u"] / r["s"], 4) if r["s"] else 0.0}
           for r in rows]
    out.sort(key=lambda d: -d["roi"])
    return out


def _loss_code_tally(conn) -> list[dict]:
    """How the losses happened, counted across every code that applied.

    Codes are not exclusive — a 3-leg where two cash and one misses is both
    LEG_ONE_KILLED_IT and, usually, TAX_TOO_HIGH — so this counts each code
    separately rather than partitioning the losses.
    """
    tally: dict[str, int] = {}
    for r in conn.execute("SELECT loss_codes FROM parlays WHERE loss_codes "
                          "IS NOT NULL").fetchall():
        try:
            for c in json.loads(r[0]) or []:
                tally[c] = tally.get(c, 0) + 1
        except (ValueError, TypeError):
            continue
    return sorted(({"code": k, "n": v} for k, v in tally.items()),
                  key=lambda d: -d["n"])


def _tax_by_book(conn) -> dict:
    """§11: track the correlation tax by book.

    This is the durable, product-level edge the doc rates above any single
    ticket: the same ticket is +EV at a book taxing 18% and dead at one
    taxing 26%, and nothing about our model tells us which book we are at.

    It measured nothing for months, because it divides by `quoted_dec` and
    no feed we ingest carries SGP prices — an SGP price is not derivable
    from the leg prices. `record_quote` is the way that column gets filled:
    somebody reads the price their book is actually offering and types it
    in. So this table is not a survey of the market, it is a record of the
    tickets a person went and looked up, and it is worth exactly as much
    as that sample is representative.
    """
    rows = conn.execute(
        "SELECT book, COUNT(*) n, AVG(1.0 - quoted_dec / naive_product_dec) t "
        "FROM parlays WHERE quoted_dec IS NOT NULL AND naive_product_dec > 0 "
        "GROUP BY book").fetchall()
    books = [{"book": r["book"] or "?", "n": r["n"],
              "avg_tax": round(r["t"], 4)} for r in rows]
    # THE NOTE HAS TO TRACK THE TABLE. It spent months correctly saying
    # this was empty; the day it stops being empty, the same sentence
    # becomes a lie sitting under a column of real numbers. Whoever reads
    # the report should not have to work out which half to believe.
    if books:
        note = ("Measured from quotes recorded with `parlayledger quote`. "
                "Each row is one book's average cut against the naive leg "
                "product on tickets we actually priced there — not every "
                "ticket, only the ones somebody went and looked up.")
    else:
        note = ("Empty until a real same-game-parlay quote is recorded. No "
                "odds feed we ingest carries SGP prices and an SGP price is "
                "not derivable from the leg prices, so every ticket here is "
                "graded against an assumed tax — averaging that assumption "
                "by book would measure nothing but our own table. Record one "
                "with `python3 -m engine.parlayledger quote <id> <odds>`.")
    return {"books": books, "note": note}


def _singles_comparison(graded: list) -> dict:
    """The question §13 wants on every card, answered across the record.

    Not a footnote. If flat singles on the same legs beat the tickets, the
    honest reading is that the structure is costing money, and that should
    be one number on the page rather than something you reconstruct.
    """
    if not graded:
        return {"n": 0, "parlay_units": 0.0, "singles_units": 0.0,
                "singles_better": None}
    par = sum(float(r["pnl_units"] or 0.0) for r in graded)
    sing = sum(float(r["singles_pnl_units"] or 0.0) for r in graded)
    # HOW MUCH BETTER, NOT JUST WHETHER. `singles_better` is a bare sign
    # test, and on the first real record it was true while singles lost
    # 15.32u against the tickets' 15.98u — so a report reading only the
    # flag announced "the legs were fine and wrapping them was the
    # mistake" about legs that had lost fifteen units. The structure cost
    # 0.66u of the 15.98u; the legs cost the rest. `structure_cost` is
    # that difference, and `legs_cost` is what the legs lost on their
    # own, so the two can be weighed instead of ranked.
    return {"n": len(graded), "parlay_units": round(par, 2),
            "singles_units": round(sing, 2), "singles_better": sing > par,
            "structure_cost": round(sing - par, 2),
            "legs_cost": round(-sing, 2) if sing < 0 else 0.0}


def _recent(conn, limit: int = 15) -> list[dict]:
    out = []
    for p in conn.execute(
            "SELECT * FROM parlays WHERE status IN ('won','lost','void') "
            "ORDER BY date DESC, id DESC LIMIT ?", (limit,)).fetchall():
        legs = conn.execute(
            "SELECT player, market, side, line, odds, status, clv "
            "FROM parlay_legs WHERE parlay_id=? ORDER BY leg_no",
            (p["id"],)).fetchall()
        out.append({
            "date": p["date"], "sport": p["sport"],
            "parlay_type": p["parlay_type"], "grade": p["grade"],
            "was_play": bool(p["was_play"]),
            "status": p["status"], "pnl_units": p["pnl_units"],
            "singles_pnl_units": p["singles_pnl_units"],
            "loss_codes": json.loads(p["loss_codes"] or "[]"),
            "assumed_american": _american(p["assumed_dec"]),
            "price_basis": p["price_basis"],
            "legs": [dict(l) for l in legs],
        })
    return out


def _american(dec) -> int | None:
    try:
        dec = float(dec)
    except (TypeError, ValueError):
        return None
    if dec <= 1.0:
        return None
    return round((dec - 1) * 100) if dec >= 2.0 else round(-100 / (dec - 1))


# --- what the book actually offered -----------------------------------------
def record_quote(conn, parlay_id: int, american: str,
                 book: str | None = None) -> dict:
    """Record the same-game-parlay price a book really quoted.

    THE ONE NUMBER THIS MODULE HAS NEVER HAD. No odds feed we ingest
    carries SGP quotes and an SGP price is not derivable from the leg
    prices — the whole point of the correlation tax is that only the book
    knows it. So every ticket has been graded against `assumed_dec`: the
    naive product less the MID-POINT of a 15-to-30-point band the doc
    guesses at. Which end of that band a book actually sits on is the
    entire difference between a ticket worth taking and a dead one, and
    until now nothing could tell us.

    With real quotes two things start working that cannot work without
    them. Grading runs on money instead of an assumption. And
    `_tax_by_book` — written months ago and measuring nothing since,
    because it divides by a column that was always NULL — starts filling
    in what each book charges. That table is the parlay edge: the same
    ticket is +EV at a book taxing 18% and dead at one taxing 26%.

    AMERICAN ODDS WITH AN EXPLICIT SIGN, and a bare number is refused.
    "340" is +340 to a bettor and 340.0 to a parser, and the two differ
    by a factor of a hundred. A price entered wrong is worse than no
    price, because the tax table cannot tell it is wrong.

    A ticket already graded against the assumption is REOPENED rather
    than rescored here — the settle pass owns that arithmetic, and a
    second copy of it living in a recorder is the one that drifts.
    """
    from .odds import american_to_decimal
    ensure_schema(conn)
    txt = str(american).strip()
    if not txt or txt[0] not in "+-":
        raise ValueError(
            f"{american!r}: give the book's price with its sign (+340, -120). "
            f"A bare number is +340 to a bettor and 340.0 to a parser.")
    try:
        odds = int(txt)
    except ValueError:
        raise ValueError(f"{american!r} is not American odds") from None
    if -100 < odds < 100:
        raise ValueError(f"{odds:+d} is not a price a book can post")

    row = conn.execute("SELECT id, naive_product_dec, status, quoted_dec "
                       "FROM parlays WHERE id=?", (parlay_id,)).fetchone()
    if row is None:
        raise KeyError(f"no ticket with id {parlay_id}")

    dec = american_to_decimal(odds)
    naive = float(row["naive_product_dec"] or 0.0)
    tax = (1.0 - dec / naive) if naive else None
    # A QUOTE ABOVE THE NAIVE PRODUCT IS A NEGATIVE TAX, which is a boost
    # or a typo and never an ordinary SGP price. Recorded either way —
    # refusing it would lose a real promo — but said out loud, because a
    # boost averaged into the by-book tax table makes that book look
    # cheaper than it is on the tickets you would actually take.
    boosted = tax is not None and tax < 0
    reopened = row["status"] in ("won", "lost", "void")
    conn.execute(
        "UPDATE parlays SET quoted_dec=?, price_basis='quoted', "
        "correlation_tax=COALESCE(?, correlation_tax)"
        + (", book=?" if book else "")
        + (", status='open', pnl_units=NULL, singles_pnl_units=NULL, "
           "legs_won=NULL, legs_lost=NULL, legs_void=NULL" if reopened else "")
        + " WHERE id=?",
        ((round(dec, 4), None if tax is None else round(tax, 4), book,
          parlay_id) if book else
         (round(dec, 4), None if tax is None else round(tax, 4), parlay_id)))
    conn.commit()
    return {"id": parlay_id, "quoted_dec": round(dec, 4), "american": odds,
            "naive_product_dec": naive or None,
            "correlation_tax": None if tax is None else round(tax, 4),
            "boosted": boosted, "reopened": reopened,
            "book": book, "replaced": row["quoted_dec"] is not None}


def awaiting_quote(conn, limit: int = 40) -> list[dict]:
    """Tickets with no recorded price, newest first — the work list.

    Every ticket, not just the qualified ones: the by-book tax table is
    about what a BOOK charges, and a ticket the screen refused is priced
    by the same book on the same kind of legs. Refusing to record those
    would measure the tax only where we happened to like the ticket.
    """
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT id, sport, date, parlay_type, n_legs, grade, qualified, "
        "naive_product_dec, status, COALESCE(source,'edge') source "
        "FROM parlays WHERE quoted_dec IS NULL "
        "ORDER BY date DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# --- board hook -------------------------------------------------------------
BOARD_FILES = {
    "nfl": "web/data/recommendations.json",
    "mlb": "web/data/mlb_recommendations.json",
    "cfb": "web/data/cfb.json",
    "nba": "web/data/nba.json",
    "wnba": "web/data/wnba.json",
    "ufc": "web/data/ufc.json",
    "cbb": "web/data/cbb.json",
    # Hockey has no two-leg page; its game parlays journal from here.
    "nhl": "web/data/nhl.json",
}


def journal_built_boards(conn, root) -> dict:
    """Journal every board on disk that carries a Parlay Zone.

    Runs after the boards are written rather than inside each builder, for
    the same reason §10.2's arbitration does: the tickets are only all known
    once every league has finished, and a per-builder hook would have each
    sport writing to the journal at a different point in the refresh with no
    way to tell a full night from a half-built one.
    """
    from . import gate

    root = Path(root)
    wrote, skipped = 0, []
    for sport, rel in BOARD_FILES.items():
        # THE PRIVATE COPY. `parlays` is a paid key, so with QB_PAYWALL=1
        # the board on the public path carries an empty parlay zone —
        # `{}`, which is still a dict, so this walked straight past the
        # isinstance guard and journaled nothing. Every ticket this site
        # published since the paywall went on went ungraded, silently,
        # in the ledger the whole product is sold on. Found by sweeping
        # every reader of web/data/ after the same bug turned up in
        # arbitrate_slate and parlaycheck.
        path = gate.board_source(root / rel)
        if not path.exists():
            continue
        try:
            board = json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            skipped.append(f"{sport}: {exc}")
            continue
        # BOTH POOLS. `log_board` reads which screen produced a payload off
        # the payload itself, so these land in their own `source` rows and
        # the two records stay apart — see `ensure_schema`. Journaling one
        # and not the other is how a board gets built, shown and never
        # graded, which is the failure the paywall comment above records.
        for key in ("parlays", "likely_parlays"):
            pz = board.get(key)
            if not isinstance(pz, dict):
                continue
            try:
                wrote += log_board(conn, pz, sport=sport,
                                   date=pz.get("date") or board.get("date") or "")
            except sqlite3.Error as exc:
                skipped.append(f"{sport}/{key}: {exc}")
        # THE TWO-LEG PARLAYS (engine/twoleg, the Parlays page, 2026-10-31):
        # every posted ticket, both pools, journaled the same way.
        tl = board.get("two_leg")
        if isinstance(tl, dict):
            try:
                wrote += log_twoleg(conn, tl, sport, tl.get("date") or board.get("date") or "")
            except sqlite3.Error as exc:
                skipped.append(f"{sport}/two_leg: {exc}")
        # EACH GAME'S PARLAYS (engine/gameparlays, 2026-11-14): the legs on
        # paper first, so every ticket's legs have rows to settle from,
        # then the tickets.
        gp = board.get("game_parlays")
        if isinstance(gp, dict) and gp.get("games"):
            try:
                journal_game_parlay_legs(conn, board, sport)
                # ONLY A TICKET WHOSE LEGS HAVE ROWS (STUCKLEGS1): a leg the paper
                # journal refused (its game under way) would leave it waiting for good.
                day = board.get("date") or gp.get("date") or ""
                # Each started game's set at the start, marked on the board as built.
                mark_started_games(conn, gp, sport, day)
                gp_ok, _left = _with_leg_rows(conn, gp, sport, day)
                wrote += log_game_parlays(conn, gp_ok, sport, day)
            except sqlite3.Error as exc:
                skipped.append(f"{sport}/game_parlays: {exc}")
        # EVERY BET THE GAME REPORTS POST (engine/reportbets, 2026-11-16), in
        # the record's report book, from the same private copy.
        from . import reportbets
        if board.get(reportbets.KEY):
            try:
                reportbets.journal(conn, board, sport)
            except sqlite3.Error as exc:
                skipped.append(f"{sport}/{reportbets.KEY}: {exc}")
    return {"journaled": wrote, "skipped": skipped}


# --- the terminal on the box that holds the ledger ---------------------------
def _cli(argv: list[str]) -> int:
    """`python3 -m engine.parlayledger quote|open`.

    A COMMAND RATHER THAN A PAGE, and deliberately for now. The person
    placing these bets is the person who can see the book's SGP price,
    and that is one person with a terminal. A form on the site is the
    right answer once more than one reader is entering quotes; building
    it first would be building the harder half of a feature whose easy
    half has never once been used.
    """
    from . import ledger as _ledger
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip().splitlines()[0])
        print("\n  python3 -m engine.parlayledger open [--limit N]")
        print("      tickets with no recorded price, newest first\n")
        print("  python3 -m engine.parlayledger waiting [--days N]")
        print("      game parlays still open N days (2) after their date, and what each leg waits on\n")
        print("  python3 -m engine.parlayledger quote <id> <+340|-120> "
              "[--book dk]")
        print("      record what a book actually offered on one ticket\n")
        return 0
    cmd, rest = argv[0], argv[1:]
    conn = _ledger.connect()
    if cmd == "waiting":
        days = int(rest[rest.index("--days") + 1]) if "--days" in rest else 2
        rows = waiting(conn, days)
        if not rows:
            print(f"\n  No game parlay is still open {days} day(s) after its date.\n")
            return 0
        print(f"\n  {len(rows)} game parlay(s) still open {days} day(s) after their date\n")
        for t in rows:
            print(f"    #{t['id']}  {t['sport']}  {t['day']}  {t['game']}  ({t['source']})")
            for l in t["legs"]:
                print(f"        {l['player']} {l['market']} {l['side']} {l['line']}: {l['state']}")
        from collections import Counter
        why = Counter(l["state"].split(":")[0] for t in rows for l in t["legs"])
        print("\n  " + ", ".join(f"{n} {k}" for k, n in why.most_common()) + "\n")
        return 0
    if cmd == "open":
        limit = int(rest[rest.index("--limit") + 1]) if "--limit" in rest else 40
        rows = awaiting_quote(conn, limit)
        if not rows:
            print("\n  Every ticket in the journal carries a recorded price.\n")
            return 0
        print(f"\n  {len(rows)} ticket(s) with no recorded price\n")
        print(f"    {'id':>5}  {'date':<11}{'sport':<6}{'src':<7}{'legs':>5}"
              f"  {'grade':<9}{'naive':>8}  status")
        for r in rows:
            naive = r["naive_product_dec"]
            print(f"    {r['id']:>5}  {r['date'] or '':<11}{r['sport'] or '':<6}"
                  f"{r['source']:<7}{r['n_legs'] or 0:>5}  "
                  f"{(r['grade'] or ''):<9}"
                  f"{(f'{naive:.2f}' if naive else '—'):>8}  {r['status']}")
        print(f"\n  Record one with:  python3 -m engine.parlayledger quote "
              f"{rows[0]['id']} +340 --book dk\n")
        return 0
    if cmd == "quote":
        if len(rest) < 2:
            print("  quote <id> <+340|-120> [--book dk]")
            return 2
        book = rest[rest.index("--book") + 1] if "--book" in rest else None
        try:
            got = record_quote(conn, int(rest[0]), rest[1], book)
        except (ValueError, KeyError) as exc:
            print(f"  {exc}")
            return 2
        tax = got["correlation_tax"]
        print(f"\n  ticket {got['id']}  quoted {got['american']:+d} "
              f"(decimal {got['quoted_dec']})")
        if got["naive_product_dec"]:
            print(f"  naive product {got['naive_product_dec']:.2f}  ->  "
                  f"correlation tax {tax:+.1%}")
        if got["boosted"]:
            print("  ** THE QUOTE IS ABOVE THE NAIVE PRODUCT — a negative tax.")
            print("  ** That is a boost or a typo, never an ordinary SGP price.")
            print("  ** Recorded, because a real promo is worth keeping; check")
            print("  ** it, because a boost averaged into the by-book table")
            print("  ** makes that book look cheaper than it is.")
        if got["replaced"]:
            print("  (a price was already recorded on this ticket; replaced)")
        if got["reopened"]:
            print("  It was already graded against the assumed price, so it is")
            print("  reopened — the next settle pass regrades it on this one.")
        print()
        return 0
    print(f"  unknown command {cmd!r}")
    return 2


if __name__ == "__main__":                                # pragma: no cover
    import sys as _sys
    raise SystemExit(_cli(_sys.argv[1:]))
