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
    cols = {r[1] for r in conn.execute("PRAGMA table_info(parlays)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE parlays ADD COLUMN source TEXT "
                     "DEFAULT 'edge'")
        conn.execute("UPDATE parlays SET source='edge' WHERE source IS NULL")
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


def log_slate_play(conn, sport: str, date: str, legs: list[dict]) -> int:
    """Mark the ticket §10.2's cross-sport arbitration left standing.

    Journaled separately from the ticket itself because the arbitration runs
    after every board is built, and the winner is not known while any single
    board is being written. Nothing is staked either way — this records which
    ONE ticket the operating rule would have allowed, so the record can later
    be read both ways: how the screen did, and how the policy did.
    """
    ensure_schema(conn)
    cur = conn.execute(
        "UPDATE parlays SET was_play=1 WHERE sport=? AND date=? AND legs_key=?",
        (sport, date, legs_key(legs)))
    conn.commit()
    return cur.rowcount


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
    graded, waiting = [], 0
    for p in conn.execute("SELECT * FROM parlays WHERE status='open' "
                          "ORDER BY date, id").fetchall():
        legs = conn.execute("SELECT * FROM parlay_legs WHERE parlay_id=? "
                            "ORDER BY leg_no", (p["id"],)).fetchall()
        if not legs:
            continue
        resolved, pending = [], False
        for leg in legs:
            b = _matching_bet(conn, p, leg)
            if b is None or b["status"] == "open":
                pending = True
                break
            resolved.append((leg, b))
        if pending:
            waiting += 1
            continue

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
        resolved, back_open = [], False
        for leg in legs:
            b = _matching_bet(conn, p, leg)
            if b is None or b["status"] == "open":
                back_open = True
                break
            resolved.append((leg, b))
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


def _matching_bet(conn, p, leg):
    """The singles-journal row this leg was taken from.

    Matched on the same four fields that identify a bet in the singles
    journal's own unique key, minus the category — a leg is always a 'main'
    pick, since §14 requires it to have earned the board on its own.
    """
    return conn.execute(
        "SELECT * FROM bets WHERE sport=? AND date=? AND player=? AND market=?"
        " AND category='main'",
        (p["sport"], p["date"], leg["player"], leg["market"])).fetchone()


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


def _priced_positive_correlation(p) -> bool:
    """Did this ticket claim a positive correlation between its legs?

    Read back off the reasoning text the screen wrote, which is where the
    rhos were recorded. No longer used to stamp a loss code — see the note
    above — but kept because it is the only reader of that text and the
    aggregate check may want it when a ticket has no stored joint.
    """
    text = p["conditional_reasoning"] or ""
    return "rho +" in text


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
        print("  python3 -m engine.parlayledger quote <id> <+340|-120> "
              "[--book dk]")
        print("      record what a book actually offered on one ticket\n")
        return 0
    cmd, rest = argv[0], argv[1:]
    conn = _ledger.connect()
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
